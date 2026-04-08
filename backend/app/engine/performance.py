"""
engine/performance.py
---------------------
Core calculation engine for portfolio performance.

Central function: calc_position_return(asset, transactions, current_value, fx_context)
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────────────────

class AssetBehavior(str, Enum):
    MARKET = "MARKET"
    FUND = "FUND"
    MANUAL = "MANUAL"
    REAL_ESTATE = "REAL_ESTATE"
    REAL_ESTATE_PIPELINE = "REAL_ESTATE_PIPELINE"
    ENERGY_INCOME = "ENERGY_INCOME"
    NO_RETURN = "NO_RETURN"


class EconomicType(str, Enum):
    INVESTMENT = "investment"
    ACQUISITION_COST = "acquisition_cost"
    RENTAL_INCOME = "rental_income"
    DIVIDEND = "dividend"
    INTEREST_INCOME = "interest_income"
    OTHER_INCOME = "other_income"
    OPERATING_EXPENSE = "operating_expense"
    LOAN_DRAWDOWN = "loan_drawdown"
    PRINCIPAL_PAYMENT = "principal_payment"
    INTEREST_PAYMENT = "interest_payment"
    SALE_PROCEEDS = "sale_proceeds"
    REVALUATION = "revaluation"


# Economic types that are part of cost basis
COST_BASIS_TYPES = {
    EconomicType.INVESTMENT,
    EconomicType.ACQUISITION_COST,
}

# Economic types that are income (positive cashflows)
INCOME_TYPES = {
    EconomicType.RENTAL_INCOME,
    EconomicType.DIVIDEND,
    EconomicType.INTEREST_INCOME,
    EconomicType.OTHER_INCOME,
}

# Economic types that are operating expenses
EXPENSE_TYPES = {
    EconomicType.OPERATING_EXPENSE,
    EconomicType.INTEREST_PAYMENT,
}

# Economic types EXCLUDED from IRR (balance sheet movements)
IRR_EXCLUDED_TYPES = {
    EconomicType.PRINCIPAL_PAYMENT,   # reduces debt, not P&L
    EconomicType.LOAN_DRAWDOWN,       # money received as loan, not income
    EconomicType.REVALUATION,         # non-cash event
}


# ──────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────

@dataclass
class TxRecord:
    date: date
    economic_type: str
    cashflow_amount: Decimal       # signed: negative = outflow, positive = inflow
    currency: str = "ILS"
    total_amount: Optional[Decimal] = None


@dataclass
class PerformanceResult:
    asset_id: str
    model_used: str
    invested_capital: Decimal
    current_value: Decimal
    total_return: Decimal
    total_return_pct: Optional[Decimal]
    annual_return_pct: Optional[Decimal]
    xirr_return_pct: Optional[Decimal]
    total_income: Decimal
    total_expenses: Decimal
    net_cashflow: Decimal
    error: Optional[str] = None


# ──────────────────────────────────────────────────────
# MODEL RESOLVER
# ──────────────────────────────────────────────────────

def resolve_model(asset_behavior: str, lifecycle_stage: str = "operational") -> AssetBehavior:
    """
    Determine which calculation model to use for an asset.
    """
    try:
        behavior = AssetBehavior(asset_behavior)
    except ValueError:
        logger.warning(f"Unknown asset_behavior: {asset_behavior}, defaulting to MANUAL")
        return AssetBehavior.MANUAL

    # Pipeline assets always use pipeline model regardless of behavior field
    if lifecycle_stage in ("pipeline", "pre_completion"):
        if behavior in (AssetBehavior.REAL_ESTATE, AssetBehavior.REAL_ESTATE_PIPELINE):
            return AssetBehavior.REAL_ESTATE_PIPELINE

    return behavior


# ──────────────────────────────────────────────────────
# INVESTED CAPITAL
# ──────────────────────────────────────────────────────

def compute_invested_capital(
    transactions: list[TxRecord],
    model: AssetBehavior,
    manual_baseline: Optional[Decimal] = None,
) -> Decimal:
    """
    Compute invested capital (cost basis) based on model.

    Rules by model:
    - MARKET: sum of buy transactions (cost basis per share * quantity)
    - FUND: manual baseline OR sum of contributions
    - REAL_ESTATE: purchase price + acquisition costs (tax, lawyer, broker, initial renovation)
    - REAL_ESTATE_PIPELINE: actual equity paid to date ONLY
    - MANUAL: purchase price + acquisition costs
    - ENERGY_INCOME: initial investment
    """
    if model == AssetBehavior.FUND and manual_baseline is not None:
        # For funds, a periodic valuation baseline is preferred
        # over trying to sum every historical contribution
        return manual_baseline

    total = Decimal("0")
    for tx in transactions:
        eco = tx.economic_type
        if eco in (EconomicType.INVESTMENT.value, EconomicType.ACQUISITION_COST.value):
            # Outflows are negative in cashflow_amount; for cost basis we want positive
            total += abs(tx.cashflow_amount) if tx.cashflow_amount else (tx.total_amount or Decimal("0"))

    return total


# ──────────────────────────────────────────────────────
# INCOME & EXPENSES
# ──────────────────────────────────────────────────────

def compute_income_and_expenses(transactions: list[TxRecord]) -> tuple[Decimal, Decimal]:
    """
    Returns (total_income, total_expenses).
    Income: rent, dividends, interest income, other income
    Expenses: operating expenses, interest payments
    Principal payments are EXCLUDED (balance sheet).
    """
    total_income = Decimal("0")
    total_expenses = Decimal("0")

    for tx in transactions:
        eco = tx.economic_type
        cf = abs(tx.cashflow_amount) if tx.cashflow_amount else Decimal("0")

        if eco in [e.value for e in INCOME_TYPES]:
            total_income += cf
        elif eco in [e.value for e in EXPENSE_TYPES]:
            total_expenses += cf

    return total_income, total_expenses


# ──────────────────────────────────────────────────────
# XIRR
# ──────────────────────────────────────────────────────

def build_irr_cashflows(
    transactions: list[TxRecord],
    current_value: Decimal,
    snapshot_date: date,
) -> list[tuple[date, Decimal]]:
    """
    Build cashflow series for XIRR calculation.

    Rules:
    - Include: investment outflows, income, operating expenses, interest payments
    - Exclude: principal payments (balance sheet), loan drawdowns, revaluations
    - Terminal value: current_value as positive inflow at snapshot_date
    """
    cashflows = []

    for tx in transactions:
        eco = tx.economic_type
        if eco in [e.value for e in IRR_EXCLUDED_TYPES]:
            continue
        cf = tx.cashflow_amount
        if cf is not None and cf != 0:
            cashflows.append((tx.date, cf))

    # Add terminal value
    if current_value > 0:
        cashflows.append((snapshot_date, current_value))

    # Sort by date
    cashflows.sort(key=lambda x: x[0])
    return cashflows


def xirr(cashflows: list[tuple[date, Decimal]], guess: float = 0.1) -> Optional[float]:
    """
    Calculate XIRR (internal rate of return for irregular cashflows).
    Uses Newton-Raphson method.
    Returns annualized rate or None if no solution found.
    """
    if len(cashflows) < 2:
        return None

    # Need both positive and negative cashflows for IRR to make sense
    amounts = [float(cf[1]) for cf in cashflows]
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    dates = [cf[0] for cf in cashflows]
    base_date = dates[0]
    days = [(d - base_date).days for d in dates]

    def npv(rate):
        return sum(
            amounts[i] / ((1 + rate) ** (days[i] / 365.0))
            for i in range(len(amounts))
        )

    def dnpv(rate):
        return sum(
            -amounts[i] * (days[i] / 365.0) / ((1 + rate) ** (days[i] / 365.0 + 1))
            for i in range(len(amounts))
        )

    rate = guess
    for _ in range(100):
        f = npv(rate)
        df = dnpv(rate)
        if abs(df) < 1e-12:
            break
        new_rate = rate - f / df
        if abs(new_rate - rate) < 1e-7:
            return new_rate
        rate = new_rate

    return None


# ──────────────────────────────────────────────────────
# ANNUALIZED RETURN
# ──────────────────────────────────────────────────────

def compute_annualized_return(
    invested_capital: Decimal,
    current_value: Decimal,
    first_investment_date: Optional[date],
    snapshot_date: date,
) -> Optional[Decimal]:
    """
    Simple annualized return: (current_value / invested_capital) ^ (1/years) - 1
    """
    if not first_investment_date or invested_capital <= 0:
        return None

    days = (snapshot_date - first_investment_date).days
    if days <= 0:
        return None

    years = days / 365.25
    ratio = float(current_value) / float(invested_capital)
    if ratio <= 0:
        return None

    try:
        annualized = ratio ** (1 / years) - 1
        return Decimal(str(round(annualized, 6)))
    except Exception:
        return None


# ──────────────────────────────────────────────────────
# MAIN CALCULATION FUNCTION
# ──────────────────────────────────────────────────────

def calc_position_return(
    asset_id: str,
    asset_behavior: str,
    lifecycle_stage: str,
    transactions: list[TxRecord],
    current_value: Decimal,
    snapshot_date: date,
    manual_baseline: Optional[Decimal] = None,
) -> PerformanceResult:
    """
    Master calculation function.

    Args:
        asset_id: asset identifier
        asset_behavior: from AssetBehavior enum
        lifecycle_stage: operational | pipeline | speculative | etc.
        transactions: list of TxRecord for this asset
        current_value: current market or manual value
        snapshot_date: date of this calculation
        manual_baseline: for FUND assets, a baseline valuation (optional)

    Returns:
        PerformanceResult
    """
    model = resolve_model(asset_behavior, lifecycle_stage)

    # Pipeline special case: current_value IS invested_capital
    if model == AssetBehavior.REAL_ESTATE_PIPELINE:
        invested_capital = compute_invested_capital(transactions, model)
        # For pipeline, current value = invested capital (conservative)
        effective_value = invested_capital
        total_return = Decimal("0")
        total_return_pct = Decimal("0")
        income, expenses = compute_income_and_expenses(transactions)
        return PerformanceResult(
            asset_id=asset_id,
            model_used=model.value,
            invested_capital=invested_capital,
            current_value=effective_value,
            total_return=total_return,
            total_return_pct=total_return_pct,
            annual_return_pct=None,
            xirr_return_pct=None,
            total_income=income,
            total_expenses=expenses,
            net_cashflow=income - expenses,
        )

    # No return model
    if model == AssetBehavior.NO_RETURN:
        return PerformanceResult(
            asset_id=asset_id,
            model_used=model.value,
            invested_capital=Decimal("0"),
            current_value=current_value,
            total_return=Decimal("0"),
            total_return_pct=None,
            annual_return_pct=None,
            xirr_return_pct=None,
            total_income=Decimal("0"),
            total_expenses=Decimal("0"),
            net_cashflow=Decimal("0"),
        )

    # Compute invested capital
    invested_capital = compute_invested_capital(transactions, model, manual_baseline)

    # Income and expenses
    total_income, total_expenses = compute_income_and_expenses(transactions)
    net_cashflow = total_income - total_expenses

    # Total return
    total_return = current_value - invested_capital
    total_return_pct = (
        Decimal(str(round(float(total_return) / float(invested_capital), 6)))
        if invested_capital > 0
        else None
    )

    # First investment date for annualized return
    investment_txs = [t for t in transactions if t.economic_type in (
        EconomicType.INVESTMENT.value, EconomicType.ACQUISITION_COST.value
    )]
    first_date = min((t.date for t in investment_txs), default=None)

    # Annualized return
    annual_return_pct = compute_annualized_return(
        invested_capital, current_value, first_date, snapshot_date
    )

    # XIRR (skip for speculative/no-cashflow assets)
    xirr_result = None
    if model not in (AssetBehavior.MANUAL,) or total_income > 0:
        cashflows = build_irr_cashflows(transactions, current_value, snapshot_date)
        raw_xirr = xirr(cashflows)
        if raw_xirr is not None:
            xirr_result = Decimal(str(round(raw_xirr, 6)))

    return PerformanceResult(
        asset_id=asset_id,
        model_used=model.value,
        invested_capital=invested_capital,
        current_value=current_value,
        total_return=total_return,
        total_return_pct=total_return_pct,
        annual_return_pct=annual_return_pct,
        xirr_return_pct=xirr_result,
        total_income=total_income,
        total_expenses=total_expenses,
        net_cashflow=net_cashflow,
    )
