"""
BudgetProcessor — classifies raw transactions into budget categories.

Sources: bank + credit card sources
Flow per batch:
  Phase 1 — rule engine pass (one DB query per row for existing log):
    For each raw_transaction:
      0. Skip if reviewed_at IS NOT NULL (human reviewed — never overwrite)
      1. Run RuleEngine.evaluate() — if confidence >= threshold → categorize
      2. Else → queue for AI
  Phase 2 — batch AI classification (20 transactions per API call):
      3. Call AIClassifier.classify_batch() for all unmatched rows
      4. Apply results; save suggested rules
  Phase 3 — DB writes:
      5. Upsert classification_log entry
      6. Upsert budget_actual_transactions (idempotent junction table)
      7. Recalculate budget_actuals.actual_amount = SUM of junction rows

On rerun: skip rows with reviewed_at IS NOT NULL (human reviewed).
          Re-classify all others; junction table + SUM ensures no double-counting.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.processors.base import BaseProcessor, ProcessResult
from app.processors.rule_engine import RuleEngine, RULE_CONFIDENCE_THRESHOLD
from app.processors.ai_classifier import AI_CONFIDENCE_THRESHOLD

log = logging.getLogger(__name__)

_rule_engine = RuleEngine()

AI_BATCH_SIZE = 20  # transactions per Claude API call


async def _recalculate_budget_actual(
    db: AsyncSession,
    actual_id: UUID,
    now: datetime,
) -> None:
    """Recalculate budget_actuals.actual_amount + transaction_count from junction totals."""
    from app.models.budget import BudgetActual, BudgetActualTransaction

    result = (await db.execute(
        select(
            func.sum(BudgetActualTransaction.amount).label("total"),
            func.count(BudgetActualTransaction.raw_transaction_id).label("cnt"),
        ).where(BudgetActualTransaction.budget_actual_id == actual_id)
    )).one()

    actual = await db.get(BudgetActual, actual_id)
    if actual:
        actual.actual_amount = result.total or Decimal(0)
        actual.transaction_count = result.cnt or 0
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
        active_rules = (await db.execute(
            select(BudgetCategoryRule)
            .where(
                BudgetCategoryRule.portfolio_id == portfolio_id,
                BudgetCategoryRule.status == "active",
            )
            .order_by(
                BudgetCategoryRule.priority.asc(),
                BudgetCategoryRule.match_count.desc(),
            )
        )).scalars().all()

        # Load all active categories (for AI classifier)
        categories = (await db.execute(
            select(BudgetCategory).where(
                BudgetCategory.portfolio_id == portfolio_id,
                BudgetCategory.is_active == True,
            )
        )).scalars().all()

        now = datetime.now(timezone.utc)
        written = 0
        skipped = 0
        rule_count = 0
        ai_count = 0
        review_count = 0
        rules_suggested = 0

        # ── Phase 1: run rule engine, collect per-row state ────────────────────
        # state dict keys: row, existing_log, tx_dict,
        #   category_id, method, confidence, rule_matched, needs_review,
        #   ai_model, ai_prompt_tokens, ai_completion_tokens, ai_result
        row_states: List[Dict[str, Any]] = []

        for row in rows:
            existing_log = (await db.execute(
                select(ClassificationLog).where(
                    ClassificationLog.raw_transaction_id == row.id,
                )
            )).scalar_one_or_none()

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

            state: Dict[str, Any] = {
                "row": row,
                "existing_log": existing_log,
                "tx_dict": tx_dict,
                "category_id": None,
                "method": "unclassified",
                "confidence": 0.0,
                "rule_matched": None,
                "needs_review": True,
                "ai_model": None,
                "ai_prompt_tokens": None,
                "ai_completion_tokens": None,
                "ai_result": None,
            }

            matched_rule, rule_confidence = _rule_engine.evaluate(tx_dict, active_rules)
            if matched_rule and rule_confidence >= RULE_CONFIDENCE_THRESHOLD:
                state["category_id"] = matched_rule.category_id
                state["rule_matched"] = matched_rule
                state["method"] = "rule"
                state["confidence"] = rule_confidence
                state["needs_review"] = False
                rule_count += 1
                matched_rule.match_count += 1
                matched_rule.last_matched_at = now

            row_states.append(state)

        # ── Phase 2: batch AI classify all unmatched rows ──────────────────────
        unmatched = [s for s in row_states if s["method"] == "unclassified"]

        if unmatched:
            if os.environ.get("ANTHROPIC_API_KEY"):
                log.info(
                    "Calling AI classifier for %d unmatched transactions (%d batches of %d)...",
                    len(unmatched),
                    (len(unmatched) + AI_BATCH_SIZE - 1) // AI_BATCH_SIZE,
                    AI_BATCH_SIZE,
                )
                from app.processors.ai_classifier import AIClassifier
                classifier = AIClassifier()

                for batch_start in range(0, len(unmatched), AI_BATCH_SIZE):
                    chunk = unmatched[batch_start:batch_start + AI_BATCH_SIZE]
                    tx_dicts = [s["tx_dict"] for s in chunk]

                    try:
                        ai_results = await classifier.classify_batch(tx_dicts, categories)
                    except Exception as e:
                        log.warning(
                            "AI batch failed (offset %d): %s", batch_start, e, exc_info=True
                        )
                        ai_results = [None] * len(chunk)

                    for state, ai_result in zip(chunk, ai_results):
                        if ai_result is None:
                            review_count += 1
                            continue

                        state["ai_model"] = "claude-haiku-4-5-20251001"
                        state["ai_prompt_tokens"] = ai_result.prompt_tokens or None
                        state["ai_completion_tokens"] = ai_result.completion_tokens or None

                        if (
                            ai_result.category_id
                            and ai_result.confidence >= AI_CONFIDENCE_THRESHOLD
                        ):
                            state["category_id"] = ai_result.category_id
                            state["method"] = "ai"
                            state["confidence"] = ai_result.confidence
                            state["needs_review"] = False
                            state["ai_result"] = ai_result
                            ai_count += 1
                        else:
                            log.info(
                                "AI confidence %.2f below threshold for: %s",
                                ai_result.confidence,
                                state["row"].description[:50],
                            )
                            review_count += 1

                    # Rate-limit buffer between batches (not after the last one)
                    if batch_start + AI_BATCH_SIZE < len(unmatched):
                        await asyncio.sleep(1)
            else:
                log.warning(
                    "AI classifier skipped — ANTHROPIC_API_KEY not set; "
                    "%d transactions sent to review queue",
                    len(unmatched),
                )
                review_count += len(unmatched)

        # ── Phase 3: write classification_log + budget_actuals ─────────────────
        for state in row_states:
            row = state["row"]
            existing_log = state["existing_log"]
            category_id: Optional[UUID] = state["category_id"]

            # Create or update classification_log
            if existing_log is None:
                log_entry = ClassificationLog(
                    id=uuid.uuid4(),
                    raw_transaction_id=row.id,
                )
                db.add(log_entry)
            else:
                log_entry = existing_log

            log_entry.category_id = category_id
            log_entry.rule_id = state["rule_matched"].id if state["rule_matched"] else None
            log_entry.method = state["method"]
            log_entry.confidence = state["confidence"]
            log_entry.ai_model = state["ai_model"]
            log_entry.ai_prompt_tokens = state["ai_prompt_tokens"]
            log_entry.ai_completion_tokens = state["ai_completion_tokens"]
            log_entry.needs_review = state["needs_review"]
            log_entry.processed_at = now

            # Save suggested rule from AI result
            ai_result = state["ai_result"]
            if ai_result and ai_result.suggested_rule:
                db.add(BudgetCategoryRule(
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
                ))
                rules_suggested += 1

            # Idempotent budget_actuals update
            if category_id and row.raw_date:
                year = row.raw_date.year
                month = row.raw_date.month
                amount = abs(row.amount)

                existing_bat = await db.get(BudgetActualTransaction, row.id)
                old_actual_id = existing_bat.budget_actual_id if existing_bat else None

                actual_id: UUID = (await db.execute(
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
                )).scalar_one()

                await db.execute(
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

                await _recalculate_budget_actual(db, actual_id, now)
                if old_actual_id and old_actual_id != actual_id:
                    await _recalculate_budget_actual(db, old_actual_id, now)

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
