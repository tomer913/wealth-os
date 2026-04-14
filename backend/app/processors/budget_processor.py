"""
BudgetProcessor — classifies raw transactions into budget categories.

Sources: bank + credit card sources
Flow per raw_transaction:
  1. Load active rules ordered by priority asc, match_count desc
  2. Run RuleEngine.evaluate() — if confidence >= threshold → categorize
  3. Else call AIClassifier (if ANTHROPIC_API_KEY set) — if AI confidence >= threshold
     → categorize, auto-generate suggested rule
  4. Else → log as unclassified, needs_review=True
  5. Upsert budget_actuals
  6. Update rule.match_count + last_matched_at if rule fired
  7. Write classification_log entry
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.processors.base import BaseProcessor, ProcessResult
from app.processors.rule_engine import RuleEngine, RULE_CONFIDENCE_THRESHOLD
from app.processors.ai_classifier import AI_CONFIDENCE_THRESHOLD

log = logging.getLogger(__name__)

_rule_engine = RuleEngine()


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
            BudgetActual, BudgetCategory, BudgetCategoryRule, ClassificationLog,
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

        written = 0
        skipped = 0

        for row in rows:
            # Skip if already classified
            existing_q = select(ClassificationLog.id).where(
                ClassificationLog.raw_transaction_id == row.id,
            )
            if (await db.execute(existing_q)).scalar_one_or_none():
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

            # ── Step 1: rule engine ─────────────────────────────────────────
            matched_rule, rule_confidence = _rule_engine.evaluate(tx_dict, active_rules)
            if matched_rule and rule_confidence >= RULE_CONFIDENCE_THRESHOLD:
                category_id = matched_rule.category_id
                rule_matched = matched_rule
                method = "rule"
                confidence = rule_confidence
                needs_review = False
                matched_rule.match_count += 1
                matched_rule.last_matched_at = datetime.now(timezone.utc)

            # ── Step 2: AI fallback ─────────────────────────────────────────
            elif os.environ.get("ANTHROPIC_API_KEY"):
                log.info(
                    "AI classifier invoked for: %s (amount=%.2f %s)",
                    row.description, float(row.amount), row.currency,
                )
                try:
                    from app.processors.ai_classifier import AIClassifier
                    classifier = AIClassifier()
                    ai_cat_id, ai_conf, ai_reason = await classifier.classify(
                        tx_dict, categories, db
                    )
                    ai_model = "claude-haiku-4-5-20251001"
                    ai_prompt_tokens = getattr(classifier, "_last_prompt_tokens", None)
                    ai_completion_tokens = getattr(classifier, "_last_completion_tokens", None)

                    log.info(
                        "AI result: cat_id=%s confidence=%.2f reason=%s",
                        ai_cat_id, ai_conf, ai_reason,
                    )

                    if ai_cat_id and ai_conf >= AI_CONFIDENCE_THRESHOLD:
                        category_id = ai_cat_id
                        method = "ai"
                        confidence = ai_conf
                        needs_review = False

                        # Auto-generate a suggested rule
                        conditions = await classifier.generate_rule(
                            tx_dict, ai_cat_id, next(
                                (c.name for c in categories if c.id == ai_cat_id), ""
                            )
                        )
                        if conditions:
                            new_rule = BudgetCategoryRule(
                                id=uuid.uuid4(),
                                portfolio_id=portfolio_id,
                                category_id=ai_cat_id,
                                name=f"AI: {row.description[:60]}",
                                priority=200,
                                status="suggested",
                                conditions=conditions,
                                confidence=ai_conf,
                                source="ai_generated",
                                ai_reasoning=ai_reason,
                            )
                            db.add(new_rule)
                    else:
                        log.info(
                            "AI confidence %.2f below threshold %.2f — marking needs_review",
                            ai_conf, AI_CONFIDENCE_THRESHOLD,
                        )

                except Exception as e:
                    log.warning("AI classifier failed for row %s: %s", row.id, e, exc_info=True)

            # ── Step 3: Write classification log ────────────────────────
            if needs_review and not os.environ.get("ANTHROPIC_API_KEY"):
                log.debug("ANTHROPIC_API_KEY not set — skipping AI, marking needs_review")────
            log_entry = ClassificationLog(
                id=uuid.uuid4(),
                raw_transaction_id=row.id,
                category_id=category_id,
                rule_id=rule_matched.id if rule_matched else None,
                method=method,
                confidence=confidence,
                ai_model=ai_model,
                ai_prompt_tokens=ai_prompt_tokens,
                ai_completion_tokens=ai_completion_tokens,
                needs_review=needs_review,
            )
            db.add(log_entry)

            # ── Step 4: Upsert budget_actuals ───────────────────────────────
            if category_id and row.raw_date:
                year = row.raw_date.year
                month = row.raw_date.month
                amount = abs(row.amount)

                stmt = pg_insert(BudgetActual).values(
                    id=uuid.uuid4(),
                    portfolio_id=portfolio_id,
                    category_id=category_id,
                    year=year,
                    month=month,
                    actual_amount=amount,
                    transaction_count=1,
                    last_updated=datetime.now(timezone.utc),
                ).on_conflict_do_update(
                    constraint="uq_budget_actuals_category_month",
                    set_={
                        "actual_amount": BudgetActual.actual_amount + amount,
                        "transaction_count": BudgetActual.transaction_count + 1,
                        "last_updated": datetime.now(timezone.utc),
                    },
                )
                await db.execute(stmt)

            written += 1

        await db.flush()
        return ProcessResult(rows_written=written, rows_skipped=skipped)
