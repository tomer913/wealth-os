"""
BankProcessor — classifies raw bank transactions and writes to transactions table.

Sources handled: mizrachi_bank, fibi_bank, leumi_bank
Dedup key: 'PROC-{external_ref_id}'

Classification logic:
  Priority 1 — op_type codes (from extra_raw, mainly FIBI)
  Priority 2 — Hebrew keyword matching on description
  Fallback    — EXPENSE/general with app_context='budget'

app_context field:
  'wealth_os' for BUY / SELL
  'budget'    for everything else
"""
import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.processors.base import BaseProcessor, ProcessResult

log = logging.getLogger(__name__)

# ─── op_type → (type, domain) ────────────────────────────────────────────────
OP_TYPE_MAP: Dict[int, Tuple[str, str]] = {
    466: ("BUY", "securities"),
    416: ("SELL", "securities"),
    222: ("INCOME", "government"),
    293: ("FINANCING_OUTFLOW", "loan"),
    290: ("FINANCING_OUTFLOW", "loan"),
    245: ("EXPENSE", "loan"),
    295: ("EXPENSE", "loan"),
    495: ("EXPENSE", "loan"),
    272: None,  # transfer — direction from amount sign (handled specially)
}

# ─── Keyword rules — ordered, first match wins ────────────────────────────────
# Each entry: (regex_pattern, type, domain, is_internal_transfer)
KEYWORD_RULES: List[Tuple[str, str, str, bool]] = [
    # Securities
    (r"קניית|נע.קניה", "BUY", "securities", False),
    (r"מכירת|נע.מכירה|מכירה של", "SELL", "securities", False),
    # Real estate / loans
    (r"טפחות.+לווים", "FINANCING_OUTFLOW", "real_estate", False),
    (r"הלוואה|הלואה", "FINANCING_OUTFLOW", "loan", False),
    (r"ריבית על הלוואה", "EXPENSE", "loan", False),
    # Credit cards / general expenses
    (r"הרשאה כאל|ויזה כא.ל|ישראכרט|מסטרקרד|הרשאה מקס", "EXPENSE", "general", False),
    # Bank fees
    (r"עמלת פעולה|עמלה", "EXPENSE", "bank", False),
    # Tax
    (r"מס רווחי הון", "EXPENSE", "tax", False),
    # Salary
    (r"קסלמן|סיסקו|מת.ש", "INCOME", "salary", False),
    # Government income
    (r"משהב.ט|אגף השיקום|קיצבת ילד", "INCOME", "government", False),
    # Pension
    (r"מגדל חב|מגדל מקפת|מיטב דש|אקסלנס", "INCOME", "pension", False),
    # Interest income
    (r"ריבית עו.ש", "INCOME", "interest", False),
    # Internal transfers
    (r"העברה באינטרנט|העברה מהחשבון|העברה לח.נוסף", "TRANSFER", "transfer", True),
    # Credit from bank
    (r"זיכוי.+בנק|זכוי מבנק", "INCOME", "transfer", False),
]

_COMPILED_RULES = [
    (re.compile(pattern, re.UNICODE), tx_type, domain, is_internal)
    for pattern, tx_type, domain, is_internal in KEYWORD_RULES
]

WEALTH_OS_TYPES = {"BUY", "SELL"}


def _classify(description: str, amount: Decimal, extra_raw: Optional[Dict]) -> Dict[str, Any]:
    """Return classification dict for a raw bank row."""
    # Priority 1: op_type codes
    op_type = int(extra_raw.get("op_type", 0)) if extra_raw else 0
    if op_type and op_type in OP_TYPE_MAP:
        rule = OP_TYPE_MAP[op_type]
        if rule is None:
            # op_type 272 — transfer, direction from amount
            tx_type = "INCOME" if amount >= 0 else "EXPENSE"
            return {
                "type": tx_type,
                "domain": "transfer",
                "is_internal_transfer": True,
                "app_context": "budget",
            }
        tx_type, domain = rule
        return {
            "type": tx_type,
            "domain": domain,
            "is_internal_transfer": False,
            "app_context": "wealth_os" if tx_type in WEALTH_OS_TYPES else "budget",
        }

    # Priority 2: keyword matching
    for pattern, tx_type, domain, is_internal in _COMPILED_RULES:
        if pattern.search(description):
            return {
                "type": tx_type,
                "domain": domain,
                "is_internal_transfer": is_internal,
                "app_context": "wealth_os" if tx_type in WEALTH_OS_TYPES else "budget",
            }

    # Fallback
    return {
        "type": "EXPENSE",
        "domain": "general",
        "is_internal_transfer": False,
        "app_context": "budget",
    }


class BankProcessor(BaseProcessor):
    processor_name = "bank_processor"
    sources = ["mizrachi_bank", "fibi_bank", "leumi_bank"]

    async def process_batch(
        self,
        rows: list,
        db: AsyncSession,
        portfolio_id: UUID,
    ) -> ProcessResult:
        from app.models.transaction import Transaction
        from app.utils.uuid7 import uuid7
        import uuid as uuid_mod
        from datetime import timezone

        written = 0
        skipped = 0

        for row in rows:
            dedup_key = f"PROC-{row.external_ref_id}"

            # Check dedup
            exists_q = select(Transaction.id).where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.external_reference_id == dedup_key,
            )
            existing = (await db.execute(exists_q)).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            clf = _classify(row.description, row.amount, row.extra_raw)

            tx = Transaction(
                id=uuid_mod.uuid4(),
                portfolio_id=portfolio_id,
                transaction_date=row.raw_date.date(),
                type=clf["type"],
                domain=clf["domain"],
                is_internal_transfer=clf["is_internal_transfer"],
                total_amount=abs(row.amount),
                cashflow_amount=row.amount,
                currency=row.currency,
                notes=row.description,
                source=row.source,
                external_reference_id=dedup_key,
                status="confirmed",
            )
            db.add(tx)
            written += 1

        await db.flush()
        return ProcessResult(rows_written=written, rows_skipped=skipped)
