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

# ─── economic_type mappings ────────────────────────────────────────────────────

TYPE_TO_ECONOMIC_TYPE: Dict[str, str] = {
    "BUY":               "BUY",
    "SELL":              "SELL",
    "INCOME":            "INCOME",
    "EXPENSE":           "EXPENSE",
    "TRANSFER":          "TRANSFER",
    "FINANCING_OUTFLOW": "FINANCING_OUTFLOW",
    "DIVIDEND":          "INCOME",
    "FEE":               "EXPENSE",
}

# Domain overrides (more specific than type alone)
DOMAIN_TO_ECONOMIC_TYPE: Dict[str, str] = {
    "salary":      "INCOME",
    "pension":     "INCOME",
    "interest":    "INCOME",
    "government":  "INCOME",
    "tax":         "EXPENSE",
    "bank":        "EXPENSE",
    "credit_card": "EXPENSE",
    "loan":        "FINANCING_OUTFLOW",
    "real_estate": "FINANCING_OUTFLOW",
}

# ─── op_type → (type, domain) ────────────────────────────────────────────────
OP_TYPE_MAP: Dict[int, Optional[Tuple[str, str]]] = {
    466: ("BUY",               "securities"),
    416: ("SELL",              "securities"),
    222: ("INCOME",            "government"),
    293: ("FINANCING_OUTFLOW", "loan"),
    290: ("FINANCING_OUTFLOW", "loan"),
    245: ("EXPENSE",           "loan"),
    295: ("EXPENSE",           "loan"),
    495: ("EXPENSE",           "loan"),
    272: None,  # transfer — direction from amount sign (handled specially)
}

# ─── Keyword rules — ordered, first match wins ────────────────────────────────
# Each entry: (regex_pattern, type, domain, is_internal_transfer)
KEYWORD_RULES: List[Tuple[str, str, str, bool]] = [
    # Securities (BUY/SELL — checked before credit card to avoid mis-match)
    (r"קניית|נע.קניה",             "BUY",              "securities",  False),
    (r"מכירת|נע.מכירה|מכירה של",   "SELL",             "securities",  False),
    # Real estate / loans
    (r"טפחות.+לווים",               "FINANCING_OUTFLOW", "real_estate", False),
    (r"הלוואה|הלואה",               "FINANCING_OUTFLOW", "loan",        False),
    (r"ריבית על הלוואה",            "EXPENSE",          "loan",        False),
    # Credit cards (domain credit_card, not general)
    (r"הרשאה כאל|הרשאה ישראכרט|הרשאה מקס|ויזה כא.ל|ישראכרט|מסטרקרד",
                                    "EXPENSE",          "credit_card", False),
    # VAT refund / charge
    (r"זיכוי.חיוב ממע|חיוב.זיכוי ממע",
                                    "EXPENSE",          "vat",         False),
    # Bank fees
    (r"עמלת פעולה|עמלה|החזר עמלה", "EXPENSE",          "bank",        False),
    # Tax
    (r"מס רווחי הון",               "EXPENSE",          "tax",         False),
    # FX purchase
    (r"רכישת מטח",                  "EXPENSE",          "fx",          False),
    # Salary
    (r"קסלמן|סיסקו|מת.ש מיל",      "INCOME",           "salary",      False),
    # Government income
    (r"משהב.ט|אגף השיקום|קיצבת ילד","INCOME",           "government",  False),
    # Pension
    (r"מגדל חב|מגדל מקפת|מיטב דש|אקסלנס",
                                    "INCOME",           "pension",     False),
    # Interest income
    (r"ריבית עו.ש",                 "INCOME",           "interest",    False),
    # Open-banking / bank-to-bank credit
    (r"תשלום בנקאות פתוחה",         "TRANSFER",         "transfer",    True),
    # Internal transfers
    (r"העברה באינטרנט|העברה מהחשבון|העברה לח.נוסף",
                                    "TRANSFER",         "transfer",    True),
    # Credit from bank
    (r"זיכוי.+בנק|זכוי מבנק",      "INCOME",           "transfer",    False),
]

_COMPILED_RULES = [
    (re.compile(pattern, re.UNICODE), tx_type, domain, is_internal)
    for pattern, tx_type, domain, is_internal in KEYWORD_RULES
]

WEALTH_OS_TYPES = {"BUY", "SELL"}

# Descriptions to skip entirely (balance / header rows from parser)
SKIP_KEYWORDS = ("יתרה", "יתרה קודמת", "יתרה לתאריך")


def _classify(description: str, amount: Decimal, extra_raw: Optional[Dict]) -> Dict[str, Any]:
    """Return classification dict for a raw bank row."""
    # Priority 1: op_type codes
    op_type = int(extra_raw.get("op_type", 0)) if extra_raw else 0
    if op_type and op_type in OP_TYPE_MAP:
        rule = OP_TYPE_MAP[op_type]
        if rule is None:
            # op_type 272 — transfer, direction from amount sign
            tx_type = "INCOME" if amount >= 0 else "EXPENSE"
            return {
                "type": tx_type,
                "domain": "transfer",
                "economic_type": "TRANSFER",
                "is_internal_transfer": True,
                "app_context": "budget",
            }
        tx_type, domain = rule
        economic_type = (
            DOMAIN_TO_ECONOMIC_TYPE.get(domain)
            or TYPE_TO_ECONOMIC_TYPE.get(tx_type, tx_type)
        )
        return {
            "type": tx_type,
            "domain": domain,
            "economic_type": economic_type,
            "is_internal_transfer": False,
            "app_context": "wealth_os" if tx_type in WEALTH_OS_TYPES else "budget",
        }

    # Priority 2: keyword matching
    for pattern, tx_type, domain, is_internal in _COMPILED_RULES:
        if pattern.search(description):
            economic_type = (
                DOMAIN_TO_ECONOMIC_TYPE.get(domain)
                or TYPE_TO_ECONOMIC_TYPE.get(tx_type, tx_type)
            )
            return {
                "type": tx_type,
                "domain": domain,
                "economic_type": economic_type,
                "is_internal_transfer": is_internal,
                "app_context": "wealth_os" if tx_type in WEALTH_OS_TYPES else "budget",
            }

    # Fallback
    return {
        "type": "EXPENSE",
        "domain": "general",
        "economic_type": "EXPENSE",
        "is_internal_transfer": False,
        "app_context": "budget",
    }


# ─── BUY/SELL → asset symbol matching ────────────────────────────────────────

DESCRIPTION_TO_SYMBOL: Dict[str, str] = {
    "ibi.כספית":        "IBI_CASH",
    "כספית שק כש":      "IBI_CASH",
    "ibi":              "IBI_CASH",
    "מגדל כסשק לאקונ":  "MIGDAL_CASH",
    "מגדל כסשק":        "MIGDAL_CASH",
}


async def _find_asset_id(
    description: str,
    portfolio_id: UUID,
    db: AsyncSession,
) -> Optional[UUID]:
    """Return asset.id for a BUY/SELL row by matching description keywords, or None."""
    from app.models.asset import Asset

    desc_lower = description.lower()
    for keyword, symbol in DESCRIPTION_TO_SYMBOL.items():
        if keyword.lower() in desc_lower:
            asset = (await db.execute(
                select(Asset).where(
                    Asset.symbol.ilike(f"%{symbol}%"),
                    Asset.portfolio_id == portfolio_id,
                )
            )).scalar_one_or_none()
            if asset:
                log.info("Linked '%s' to asset %s", description[:40], symbol)
                return asset.id
            break
    return None


# ─── Processor ────────────────────────────────────────────────────────────────

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
        from sqlalchemy import text

        written = 0
        skipped = 0

        for row in rows:
            # Skip balance / header rows from the parser
            desc = row.description or ""
            if any(kw in desc for kw in SKIP_KEYWORDS):
                log.debug("Skipping balance row: %s", desc[:60])
                skipped += 1
                continue

            dedup_key = f"PROC-{row.external_ref_id}"
            clf = _classify(desc, row.amount, row.extra_raw)

            # BUY/SELL: try to link to a known asset
            asset_id = None
            if clf["type"] in WEALTH_OS_TYPES:
                asset_id = await _find_asset_id(desc, portfolio_id, db)

            values = dict(
                id=uuid_mod.uuid4(),
                portfolio_id=portfolio_id,
                transaction_date=row.raw_date.date(),
                type=clf["type"],
                economic_type=clf["economic_type"],
                domain=clf["domain"],
                is_internal_transfer=clf["is_internal_transfer"],
                total_amount=abs(row.amount),
                cashflow_amount=row.amount,
                currency=row.currency,
                notes=desc,
                source=row.source,
                external_reference_id=dedup_key,
                status="confirmed",
                asset_id=asset_id,
            )

            stmt = (
                pg_insert(Transaction)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["external_reference_id"],
                    index_where=text("external_reference_id IS NOT NULL"),
                )
            )
            result = await db.execute(stmt)
            if result.rowcount:
                written += 1
            else:
                skipped += 1

        await db.flush()
        return ProcessResult(rows_written=written, rows_skipped=skipped)
