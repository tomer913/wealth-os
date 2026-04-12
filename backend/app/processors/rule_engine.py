"""
RuleEngine — evaluates budget_category_rules against raw transactions.

Rules are evaluated in priority order (lowest priority number first).
For equal priority, higher match_count wins (popular rules win ties).
Only rules with status='active' are considered.

Supported condition ops:
  contains, not_contains, eq, neq, gt, lt, between, starts_with, regex
All string ops are case-insensitive.

Transaction dict keys used in evaluation:
  description, amount, source, economic_type, domain, currency
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

RULE_CONFIDENCE_THRESHOLD = 0.75


class RuleEngine:

    def evaluate(
        self,
        transaction: Dict[str, Any],
        rules: list,
    ) -> Tuple[Optional[Any], float]:
        """
        Evaluate rules in priority order.
        Returns (matching_rule, confidence) or (None, 0.0).
        Only active rules are checked.
        """
        active = [r for r in rules if r.status == "active"]
        # Sort: priority asc, then match_count desc for tie-breaking
        active.sort(key=lambda r: (r.priority, -r.match_count))

        for rule in active:
            try:
                if self._evaluate_rule(transaction, rule):
                    return rule, rule.confidence
            except Exception as e:
                log.warning("Rule %s evaluation error: %s", rule.id, e)

        return None, 0.0

    def _evaluate_rule(self, transaction: Dict[str, Any], rule) -> bool:
        """Evaluate a single rule's conditions against a transaction dict."""
        conditions = rule.conditions
        if not conditions:
            return False

        operator = conditions.get("operator", "AND").upper()
        rules_list = conditions.get("rules", [])

        if not rules_list:
            return False

        results = [self._eval_condition(transaction, cond) for cond in rules_list]

        if operator == "AND":
            return all(results)
        else:  # OR
            return any(results)

    def _eval_condition(self, tx: Dict[str, Any], cond: Dict[str, Any]) -> bool:
        field = cond.get("field", "")
        op = cond.get("op", "")
        value = cond.get("value")

        raw = tx.get(field)
        if raw is None:
            return False

        # Normalise to string for string ops
        is_str_op = op in ("contains", "not_contains", "starts_with", "regex", "eq", "neq")
        if is_str_op:
            raw_str = str(raw).lower()
            val_str = str(value).lower() if value is not None else ""

        if op == "contains":
            return val_str in raw_str
        elif op == "not_contains":
            return val_str not in raw_str
        elif op == "starts_with":
            return raw_str.startswith(val_str)
        elif op == "regex":
            return bool(re.search(val_str, raw_str, re.IGNORECASE | re.UNICODE))
        elif op == "eq":
            return raw_str == val_str
        elif op == "neq":
            return raw_str != val_str
        elif op == "gt":
            return Decimal(str(raw)) > Decimal(str(value))
        elif op == "lt":
            return Decimal(str(raw)) < Decimal(str(value))
        elif op == "between":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                return False
            val = Decimal(str(raw))
            return Decimal(str(value[0])) <= val <= Decimal(str(value[1]))
        else:
            log.debug("Unknown condition op: %s", op)
            return False

    async def test_rule(
        self,
        conditions: Dict[str, Any],
        portfolio_id: UUID,
        db: AsyncSession,
        lookback_days: int = 90,
    ):
        """
        Test a rule (before saving) against recent raw_transactions.
        Returns a BudgetRuleTestResult.
        """
        from app.models.raw_layer import RawTransaction
        from app.schemas.budget import BudgetRuleTestResult

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        q = (
            select(RawTransaction)
            .where(
                RawTransaction.portfolio_id == portfolio_id,
                RawTransaction.imported_at >= cutoff,
            )
            .order_by(RawTransaction.id.desc())
            .limit(2000)
        )
        rows = (await db.execute(q)).scalars().all()

        # Create a fake rule object to reuse _evaluate_rule
        class _FakeRule:
            conditions = conditions
            status = "active"
            id = "test"
            match_count = 0

        fake = _FakeRule()
        matched = []
        for row in rows:
            tx_dict = {
                "description": row.description,
                "amount": float(row.amount),
                "source": row.source,
                "economic_type": (row.extra_raw or {}).get("economic_type", ""),
                "domain": (row.extra_raw or {}).get("domain", ""),
                "currency": row.currency,
            }
            try:
                if self._evaluate_rule(tx_dict, fake):
                    matched.append({
                        "id": str(row.id),
                        "date": row.raw_date.isoformat(),
                        "description": row.description,
                        "amount": float(row.amount),
                        "currency": row.currency,
                        "source": row.source,
                    })
            except Exception:
                pass

        return BudgetRuleTestResult(
            count=len(matched),
            sample=matched[:5],
        )
