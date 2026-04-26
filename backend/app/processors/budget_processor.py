"""
BudgetProcessor — classifies raw transactions into budget categories.

Sources: bank + credit card sources
Flow per raw_transaction:
  0. Skip if reviewed_at IS NOT NULL (human has reviewed — never overwrite)
  1. Load active rules ordered by priority asc, match_count desc
  2. Run RuleEngine.evaluate() — if confidence >= threshold → categorize
  3. Else call AIClassifier (if ANTHROPIC_API_KEY set) — if AI confidence >= threshold
     → categorize, auto-generate suggested rule
  4. Else → log as unclassified, needs_review=True
  5. Upsert budget_actual_transactions (idempotent junction table)
  6. Recalculate budget_actuals.actual_amount = SUM of junction rows
  7. Update rule.match_count + last_matched_at if rule fired
  8. Write / update classification_log entry with processed_at = now()

On rerun: skip rows with reviewed_at IS NOT NULL (human reviewed).
          Re-classify all others; junction table + SUM ensures no double-counting.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.processors.base import BaseProcessor, ProcessResult
from app.processors.rule_engine import RuleEngine, RULE_CONFIDENCE_THRESHOLD
from app.processors.ai_classifier import AI_CONFIDENCE_THRESHOLD

log = logging.getLogger(__name__)

_rule_engine = RuleEngine()


async def _recalculate_budget_actual(
    db: AsyncSession,
    actual_id: UUID,
    now: datetime,
) -> None:
    """
    Recalculate budget_actuals.actual_amount and transaction_count
    from the sum of all budget_actual_transactions for this bucket.
    """
    from app.models.budget import BudgetActual, BudgetActualTransaction

    result = (await db.execute(
        select(
            func.sum(BudgetActualTransaction.amount).label("total"),
            func.count(BudgetActualTransaction.raw_transaction_id).label("cnt"),
        ).where(BudgetActualTransaction.budget_actual_id == actual_id)
    )).one()

    total = result.total or Decimal(0)
    cnt = result.cnt or 0

    actual = await db.get(BudgetActual, actual_id)
    if actual:
        actual.actual_amount = total
        actual.transaction_count = cnt
        actual.last_updated = now


class BudgetProcessor(BaseProcessor):
    processor_name = "budget_processor"
    sources = [
        "mizrachi_bank", "fibi_bank", "leumi_bank",
        "isracard", "cal", "max", "leumi_card", "amex",
    ]

    async def process_batch(
        self,
        rows: list,
        db: AsyncSession,
        portfolio_id: UUID,
    ) -> ProcessResult:
        from app.models.budget import (
            BudgetActual, BudgetActualTransaction, BudgetCategory,
            BudgetCategoryRule, ClassificationLog,
        )

        # Load all active rules once per batch
        rules_q = (
            select(BudgetCategoryRule)
            .where(
                BudgetCategoryRule.portfolio_id == portfolio_id,
                BudgetCategoryRule.status == "active",
            )
            .order_by(
                BudgetCategoryRule.priority.asc(),
                BudgetCategoryRule.match_count.desc(),
            )
        )
        active_rules = (await db.execute(rules_q)).scalars().all()

        # Load all active categories (for AI classifier)
        cats_q = select(BudgetCategory).where(
            BudgetCategory.portfolio_id == portfolio_id,
            BudgetCategory.is_active == True,
        )
        categories = (await db.execute(cats_q)).scalars().all()

        now = datetime.now(timezone.utc)
        written = 0
        skipped = 0
        rule_count = 0
        ai_count = 0
        review_count = 0
        rules_suggested = 0

        for row in rows:
            # ── Step 0: Skip rows that a human has reviewed ─────────────────
            existing_q = select(ClassificationLog).where(
                ClassificationLog.raw_transaction_id == row.id,
            )
            existing_log = (await db.execute(existing_q)).scalar_one_or_none()

            if existing_log is not None and existing_log.reviewed_at is not None:
                skipped += 1
                continue

            tx_dict = {
                "description": row.description,
                "amount": float(row.amount),
                "source": row.source,
                "currency": row.currency,
                "date": row.raw_date.isoformat() if row.raw_date else None,
                "economic_type": (row.extra_raw or {}).get("economic_type", ""),
                "domain": (row.extra_raw or {}).get("domain", ""),
            }

            category_id: Optional[UUID] = None
            rule_matched = None
            method = "unclassified"
            confidence = 0.0
            needs_review = True
            ai_model = None
            ai_prompt_tokens = None
            ai_completion_tokens = None

            # ── Step 1: Rule engine ─────────────────────────────────────────
            matched_rule, rule_confidence = _rule_engine.evaluate(tx_dict, active_rules)
            if matched_rule and rule_confidence >= RULE_CONFIDENCE_THRESHOLD:
                category_id = matched_rule.category_id
                rule_matched = matched_rule
                method = "rule"
                confidence = rule_confidence
                needs_review = False
                rule_count += 1
                matched_rule.match_count += 1
                matched_rule.last_matched_at = now

            # ── Step 2: AI fallback ─────────────────────────────────────────
            elif os.environ.get("ANTHROPIC_API_KEY"):
                log.info(
                    "No rule match for: %s (amount=%.2f %s)",
                    row.description[:50], float(row.amount), row.currency,
                )
                log.info("Calling AI classifier...")
                try:
                    from app.processors.ai_classifier import AIClassifier
                    classifier = AIClassifier()
                    ai_result = await classifier.classify(tx_dict, categories, db)
                    ai_model = "claude-haiku-4-5-20251001"
                    ai_prompt_tokens = ai_result.prompt_tokens or None
                    ai_completion_tokens = ai_result.completion_tokens or None

                    log.info(
                        "AI result: cat_id=%s confidence=%.2f reason=%s",
                        ai_result.category_id, ai_result.confidence, ai_result.reasoning,
                    )

                    if ai_result.category_id and ai_result.confidence >= AI_CONFIDENCE_THRESHOLD:
                        category_id = ai_result.category_id
                        method = "ai"
                        confidence = ai_result.confidence
                        needs_review = False
                        ai_count += 1

                        if ai_result.suggested_rule:
                            new_rule = BudgetCategoryRule(
                                id=uuid.uuid4(),
                                portfolio_id=portfolio_id,
                                category_id=ai_result.category_id,
                                name=f"AI: {row.description[:60]}",
                                priority=200,
                                status="suggested",
                                conditions=ai_result.suggested_rule,
                                confidence=ai_result.confidence,
                                source="ai_generated",
                                ai_reasoning=ai_result.reasoning,
                            )
                            db.add(new_rule)
                            rules_suggested += 1
                    else:
                        log.info(
                            "AI confidence %.2f below threshold %.2f — sending to review queue",
                            ai_result.confidence, AI_CONFIDENCE_THRESHOLD,
                        )
                        review_count += 1

                except Exception as e:
                    log.warning("AI classifier failed for row %s: %s", row.id, e, exc_info=True)
                    review_count += 1
            else:
                log.warning("AI classifier skipped — ANTHROPIC_API_KEY not set; sending to review queue")
                review_count += 1

            # ── Step 3: Create or update classification_log ─────────────────
            if existing_log is None:
                log_entry = ClassificationLog(
                    id=uuid.uuid4(),
                    raw_transaction_id=row.id,
                )
                db.add(log_entry)
            else:
                log_entry = existing_log

            log_entry.category_id = category_id
            log_entry.rule_id = rule_matched.id if rule_matched else None
            log_entry.method = method
            log_entry.confidence = confidence
            log_entry.ai_model = ai_model
            log_entry.ai_prompt_tokens = ai_prompt_tokens
            log_entry.ai_completion_tokens = ai_completion_tokens
            log_entry.needs_review = needs_review
            log_entry.processed_at = now  # always updated; reviewed_at is never touched here

            # ── Steps 4–6: Idempotent budget_actuals update ─────────────────
            if category_id and row.raw_date:
                year = row.raw_date.year
                month = row.raw_date.month
                amount = abs(row.amount)

                # Check if junction row already exists (detect category change on rerun)
                existing_bat = await db.get(BudgetActualTransaction, row.id)
                old_budget_actual_id = existing_bat.budget_actual_id if existing_bat else None

                # Step 4a: Get or create budget_actual row for this category/month
                actual_stmt = (
                    pg_insert(BudgetActual)
                    .values(
                        id=uuid.uuid4(),
                        portfolio_id=portfolio_id,
                        category_id=category_id,
                        year=year,
                        month=month,
                        actual_amount=Decimal(0),
                        transaction_count=0,
                        last_updated=now,
                    )
                    .on_conflict_do_update(
                        constraint="uq_budget_actuals_category_month",
                        set_={"last_updated": now},
                    )
                    .returning(BudgetActual.__table__.c.id)
                )
                actual_id: UUID = (await db.execute(actual_stmt)).scalar_one()

                # Step 4b: Upsert junction row (idempotent: one row per raw_transaction)
                bat_stmt = (
                    pg_insert(BudgetActualTransaction)
                    .values(
                        raw_transaction_id=row.id,
                        budget_actual_id=actual_id,
                        amount=amount,
                        categorized_at=now,
                    )
                    .on_conflict_do_update(
                        index_elements=["raw_transaction_id"],
                        set_={
                            "budget_actual_id": actual_id,
                            "amount": amount,
                            "categorized_at": now,
                        },
                    )
                )
                await db.execute(bat_stmt)

                # Step 4c: Recalculate new bucket from junction totals
                await _recalculate_budget_actual(db, actual_id, now)

                # Step 4d: If category changed (rerun), recalculate old bucket too
                if old_budget_actual_id and old_budget_actual_id != actual_id:
                    await _recalculate_budget_actual(db, old_budget_actual_id, now)

            written += 1

        await db.flush()
        log.info(
            "Batch done: %d by rules, %d by AI, %d to review queue, %d rules suggested",
            rule_count, ai_count, review_count, rules_suggested,
        )
        return ProcessResult(
            rows_written=written,
            rows_skipped=skipped,
            ai_classified=ai_count,
            rules_suggested=rules_suggested,
        )
