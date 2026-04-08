"""
engine/model_resolver.py

Two responsibilities:
  1. resolveModel(asset)        → which calculation model applies to this asset
  2. classifyTransaction(tx)    → which financial flags apply to this transaction

These are the foundation of the entire engine. Every other module depends on them.
Import from here only — never re-implement this logic elsewhere.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Calculation Models ─────────────────────────────────────────────────────────

class CalcModel(str, Enum):
    """
    The calculation model assigned to an asset.
    Determines which rules apply in current_value, cost_basis, xirr etc.
    """
    MARKET              = "MARKET"              # stocks, ETF, crypto
    FUND                = "FUND"                # pension, insurance, keren hishtalmut
    REAL_ESTATE         = "REAL_ESTATE"         # operational RE with cashflows
    REAL_ESTATE_PIPELINE = "REAL_ESTATE_PIPELINE"  # under construction / pre-delivery
    MANUAL              = "MANUAL"              # whisky, land, alternatives
    ENERGY_INCOME       = "ENERGY_INCOME"       # solar / special income
    CASH_OR_DEBT        = "CASH_OR_DEBT"        # BTB, money market, deposits, p2p loans


# ── Transaction Classification Flags ──────────────────────────────────────────

@dataclass
class TxFlags:
    """
    Derived boolean flags for a transaction.
    The engine uses these flags — never raw economic_type strings — for calculations.

    Design principle: economic_type tells you WHAT happened,
    flags tell you HOW it affects each financial metric.
    """
    # Capital tracking
    affects_invested_capital: bool = False   # increases cost basis
    reduces_invested_capital: bool = False   # sale proceeds reduce net invested

    # Cashflow (money actually returned to / from investor)
    affects_cashflow: bool = False           # enters net_cashflow calculation
    cashflow_sign: int = 0                   # +1 inflow, -1 outflow, 0 no cashflow

    # Value
    affects_current_value: bool = False      # revaluation event (no cash)

    # Income buckets
    affects_income: bool = False             # dividends, rent, interest, bonus
    affects_operating_expense: bool = False  # maintenance, insurance, storage
    affects_financing_cost: bool = False     # interest payments, early repayment fees

    # Debt
    affects_debt: bool = False               # loan_in increases, principal_payment decreases
    debt_sign: int = 0                       # +1 increases debt, -1 decreases debt

    # XIRR inclusion
    include_in_xirr: bool = False            # whether this tx enters the cashflow series
    xirr_sign: int = 0                       # +1 = inflow to investor, -1 = outflow from investor

    # Audit
    warning: Optional[str] = None            # set if classification is uncertain


# ── resolveModel ───────────────────────────────────────────────────────────────

def resolve_model(asset) -> CalcModel:
    """
    Determine the calculation model for an asset.

    Args:
        asset: SQLAlchemy Asset ORM object, or any object/dict with these fields:
               asset_behavior, asset_type, lifecycle_stage, category, sub_type

    Returns:
        CalcModel enum value

    Priority order matters — more specific rules come first.
    """
    # Support both ORM objects and plain dicts
    def get(attr, default=None):
        if isinstance(asset, dict):
            return (asset.get(attr) or default)
        return (getattr(asset, attr, None) or default)

    behavior       = (get("asset_behavior") or "").upper()
    asset_type     = (get("asset_type") or "").lower()
    lifecycle      = (get("lifecycle_stage") or "").lower()
    category       = (get("category") or "").lower()
    sub_type       = (get("sub_type") or "").lower()
    pricing_mode   = (get("pricing_mode") or "").lower()

    # ── 1. Energy / Solar ──────────────────────────────────────────────────
    if sub_type in ("solar", "energy") or asset_type == "solar" or category == "special_income":
        return CalcModel.ENERGY_INCOME

    # ── 2. Cash / Debt instruments ─────────────────────────────────────────
    if asset_type in ("cash", "debt", "money_market", "p2p_lending", "deposit"):
        return CalcModel.CASH_OR_DEBT
    if category in ("cash", "debt_income") and behavior != "MARKET":
        return CalcModel.CASH_OR_DEBT

    # ── 3. Real estate — split by lifecycle ───────────────────────────────
    if asset_type == "real_estate":
        if lifecycle in ("pipeline", "pre_completion"):
            return CalcModel.REAL_ESTATE_PIPELINE
        # operational / stabilized / speculative / exited / paused / unknown
        return CalcModel.REAL_ESTATE

    # ── 4. MARKET assets (stocks, ETF, crypto) ────────────────────────────
    if behavior == "MARKET":
        return CalcModel.MARKET

    # ── 5. FUND assets (pension, insurance, keren hishtalmut) ─────────────
    if behavior == "FUND":
        return CalcModel.FUND
    if asset_type in ("fund", "pension", "insurance", "etf_fund"):
        return CalcModel.FUND
    if pricing_mode == "derived_from_transactions" and category == "pension":
        return CalcModel.FUND

    # ── 6. MANUAL assets (whisky, land, collectibles) ─────────────────────
    if behavior == "MANUAL":
        return CalcModel.MANUAL

    # ── 7. Fallback ────────────────────────────────────────────────────────
    # If we reach here, we couldn't determine the model — default to MANUAL
    # and let the engine emit a warning.
    return CalcModel.MANUAL


# ── classifyTransaction ────────────────────────────────────────────────────────

def classify_transaction(tx) -> TxFlags:
    """
    Derive financial flags from a transaction's economic_type and type fields.

    Args:
        tx: SQLAlchemy Transaction ORM object, or dict with:
            economic_type, type, is_internal_transfer

    Returns:
        TxFlags dataclass with all relevant boolean flags set.

    Rule: economic_type drives the logic. The 'type' field is used only
    as a fallback or to resolve ambiguity within an economic_type.
    """
    def get(attr, default=None):
        if isinstance(tx, dict):
            return (tx.get(attr) or default)
        return (getattr(tx, attr, None) or default)

    economic_type  = (get("economic_type") or "").upper()
    tx_type        = (get("type") or "").lower()
    is_transfer    = bool(get("is_internal_transfer", False))

    flags = TxFlags()

    # Internal transfers don't affect any financial metric
    if is_transfer:
        return flags

    # ── BUY / Investment outflow ───────────────────────────────────────────
    if economic_type in ("BUY", "INVESTMENT_OUTFLOW"):
        flags.affects_invested_capital = True
        flags.include_in_xirr = True
        flags.xirr_sign = -1  # money leaving investor's pocket
        return flags

    # ── SELL / Investment inflow ───────────────────────────────────────────
    if economic_type in ("SELL", "INVESTMENT_INFLOW"):
        flags.reduces_invested_capital = True
        flags.affects_cashflow = True
        flags.cashflow_sign = +1
        flags.include_in_xirr = True
        flags.xirr_sign = +1  # money returning to investor
        return flags

    # ── DEPOSIT ────────────────────────────────────────────────────────────
    if economic_type == "DEPOSIT":
        flags.affects_invested_capital = True
        flags.include_in_xirr = True
        flags.xirr_sign = -1
        return flags

    # ── WITHDRAWAL ─────────────────────────────────────────────────────────
    if economic_type == "WITHDRAWAL":
        flags.reduces_invested_capital = True
        flags.affects_cashflow = True
        flags.cashflow_sign = +1
        flags.include_in_xirr = True
        flags.xirr_sign = +1
        return flags

    # ── INCOME (dividends, rent, interest, bonus, vest) ───────────────────
    if economic_type == "INCOME":
        flags.affects_cashflow = True
        flags.cashflow_sign = +1
        flags.affects_income = True
        flags.include_in_xirr = True
        flags.xirr_sign = +1
        return flags

    # ── EXPENSE (fees, storage, maintenance, insurance, management) ────────
    if economic_type == "EXPENSE":
        flags.affects_cashflow = True
        flags.cashflow_sign = -1
        flags.affects_operating_expense = True
        flags.include_in_xirr = True
        flags.xirr_sign = -1
        return flags

    # ── FINANCING_INFLOW (loan received, mortgage drawdown) ───────────────
    if economic_type == "FINANCING_INFLOW":
        # Loan in: increases debt, does NOT count as income or invested capital
        flags.affects_debt = True
        flags.debt_sign = +1
        # Not in XIRR — it's a liability event, not an investment event
        return flags

    # ── FINANCING_OUTFLOW (loan repayment) ────────────────────────────────
    # Must distinguish principal vs interest:
    # - principal_payment: reduces debt, NOT expense, NOT in XIRR
    # - interest_payment / early_repayment_fee: IS financing cost, IS in XIRR
    if economic_type == "FINANCING_OUTFLOW":
        if tx_type in ("principal_payment", "loan_payment"):
            # Pure debt reduction — no P&L impact
            flags.affects_debt = True
            flags.debt_sign = -1
        else:
            # Interest payment or early repayment fee — real cost
            flags.affects_cashflow = True
            flags.cashflow_sign = -1
            flags.affects_financing_cost = True
            flags.include_in_xirr = True
            flags.xirr_sign = -1
        return flags

    # ── REVALUATION (no cash, just updates current_value) ─────────────────
    if economic_type == "REVALUATION":
        flags.affects_current_value = True
        return flags

    # ── Unknown / unmapped ─────────────────────────────────────────────────
    flags.warning = f"unrecognized economic_type='{get('economic_type')}' type='{tx_type}'"
    return flags


# ── Convenience helpers ────────────────────────────────────────────────────────

def is_acquisition_cost(tx) -> bool:
    """
    Returns True if this transaction is part of cost basis
    (purchase tax, lawyer fee, broker fee, initial renovation).
    These are INVESTMENT_OUTFLOW with specific subtypes.
    """
    def get(attr, default=None):
        if isinstance(tx, dict):
            return tx.get(attr) or default
        return getattr(tx, attr, None) or default

    economic_type = (get("economic_type") or "").upper()
    tx_type = (get("type") or "").lower()
    subtype = (get("subtype") or "").lower()

    if economic_type not in ("BUY", "INVESTMENT_OUTFLOW", "EXPENSE"):
        return False

    acquisition_subtypes = {
        "purchase_tax", "acquisition_cost", "lawyer_fee", "broker_fee",
        "notary_fee", "renovation_initial", "stamp_duty"
    }
    return tx_type in acquisition_subtypes or subtype in acquisition_subtypes


def get_first_investment_date(transactions: list):
    """
    Returns the date of the first transaction that affects invested_capital.
    Used for annualized return calculation.
    """
    dates = []
    for tx in transactions:
        flags = classify_transaction(tx)
        if flags.affects_invested_capital:
            d = None
            if isinstance(tx, dict):
                d = tx.get("transaction_date") or tx.get("date")
            else:
                d = getattr(tx, "transaction_date", None) or getattr(tx, "date", None)
            if d:
                dates.append(d)
    return min(dates) if dates else None
