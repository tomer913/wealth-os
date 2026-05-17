"""
engine/cost_basis.py

Calculates the capital-side metrics for an asset:
  - invested_capital     (gross + net)
  - debt_balance
  - net_cashflow         (money the asset has returned)
  - realized_income
  - operating_expenses
  - financing_cost

Design principles:
  - Never re-implement transaction classification here — always use classify_transaction()
  - principal_payment is NOT an expense and NOT in cashflow
  - acquisition costs (tax, lawyer, broker) ARE part of cost basis
  - loan drawdowns are NOT invested capital — they're debt
  - All amounts stored in native currency; caller converts to ILS if needed

Usage:
    from app.engine.cost_basis import calc_cost_basis

    result = calc_cost_basis(asset, transactions, model)
    print(result.gross_invested_capital, result.net_cashflow)
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, List
import logging

from app.engine.model_resolver import (
    CalcModel,
    TxFlags,
    classify_transaction,
    is_acquisition_cost,
    get_first_investment_date,
)

log = logging.getLogger(__name__)

ZERO = Decimal("0")


# ── Result container ───────────────────────────────────────────────────────────

@dataclass
class CostBasisResult:
    """
    Capital-side metrics for a single asset, in the asset's native currency.
    The snapshot_builder converts these to ILS using FX rates.
    """
    # Invested capital
    gross_invested_capital: Decimal = ZERO
    """Total capital deployed — sum of all BUY/DEPOSIT/INVESTMENT_OUTFLOW amounts.
    Never reduced by sales. Used for gross return calculations."""

    net_invested_capital: Decimal = ZERO
    """Gross invested minus sale proceeds returned. Used for net P&L and dashboard display."""

    # Cashflow (money the asset has returned to the investor)
    net_cashflow: Decimal = ZERO
    """Sum of all inflows from the asset (income, sale proceeds, withdrawals)
    minus all outflows that are NOT part of the initial investment
    (operating expenses, financing costs). Positive = asset has returned money."""

    # Income breakdown
    realized_income: Decimal = ZERO
    """Dividends, rent, interest, bonus, vest — positive cashflows that are income."""

    operating_expenses: Decimal = ZERO
    """Maintenance, storage, insurance, management fees. Stored as positive number."""

    financing_cost: Decimal = ZERO
    """Interest payments, early repayment fees. Stored as positive number.
    Principal payments are NOT here — they reduce debt_balance instead."""

    # Debt
    debt_balance: Decimal = ZERO
    """Outstanding debt: loan_in drawdowns minus principal payments.
    Can be 0 if no financing or fully repaid."""

    # Dates
    first_investment_date: Optional[date] = None
    """Date of first transaction that affected invested_capital. Used for annualized return."""

    last_transaction_date: Optional[date] = None
    """Date of most recent transaction."""

    # Audit
    transaction_count: int = 0
    warnings: List[str] = field(default_factory=list)


# ── Model-specific overrides ───────────────────────────────────────────────────

# Economic types that represent money going INTO a FUND / CASH_OR_DEBT asset
_NET_INFLOW_TYPES  = frozenset({"BUY", "DEPOSIT", "INVESTMENT_OUTFLOW", "ALLOCATION"})
# Economic types that represent money coming OUT of a FUND / CASH_OR_DEBT asset
_NET_OUTFLOW_TYPES = frozenset({"SELL", "WITHDRAWAL", "INVESTMENT_INFLOW"})

# tx.type (uppercased) fallbacks — used when economic_type is missing/empty
_TYPE_INFLOW_TYPES  = frozenset({"BUY", "ALLOCATION", "EXTERNAL_DEPOSIT", "VEST", "BONUS", "SWAP_IN", "DEPOSIT"})
_TYPE_OUTFLOW_TYPES = frozenset({"SELL", "WITHDRAWAL", "EXTERNAL_WITHDRAWAL", "SWAP_OUT"})


def _calc_net_invested(transactions: list) -> tuple:
    """
    Return (gross_inflows, net_invested) for FUND / CASH_OR_DEBT assets.

    invested_capital = sum(inflows) - sum(outflows), floored at 0.
    Uses tx.type (uppercased) as the primary signal — economic_type can be
    mis-set (e.g. SELL → INVESTMENT_OUTFLOW) causing sells to inflate the total.
    Falls back to economic_type only when tx.type is unrecognised.
    """
    inflows = ZERO
    outflows = ZERO
    for tx in transactions:
        tx_type = (
            (tx.type or "").upper()
            if hasattr(tx, "type")
            else (tx.get("type") or "").upper()
        )
        eco = (
            (tx.economic_type or "").upper()
            if hasattr(tx, "economic_type")
            else (tx.get("economic_type") or "").upper()
        )
        raw = (
            tx.total_amount if hasattr(tx, "total_amount") else tx.get("total_amount")
        ) or ZERO
        amount = abs(Decimal(str(raw)))

        if tx_type in _TYPE_INFLOW_TYPES:
            inflows += amount
        elif tx_type in _TYPE_OUTFLOW_TYPES:
            outflows += amount
        elif eco in _NET_INFLOW_TYPES:
            inflows += amount
        elif eco in _NET_OUTFLOW_TYPES:
            outflows += amount
    return inflows, max(inflows - outflows, ZERO)


def _apply_fund_rules(result: CostBasisResult, asset, transactions: list) -> CostBasisResult:
    """
    FUND: invested_capital = net cash still in the fund (inflows − outflows).

    Replaces the flags-based gross/net computed in the main loop so that
    SELL/WITHDRAWAL transactions properly reduce the displayed invested capital.
    """
    gross, net = _calc_net_invested(transactions)
    result.gross_invested_capital = gross
    result.net_invested_capital = net
    return result


def _apply_cash_or_debt_rules(result: CostBasisResult, asset, transactions: list) -> CostBasisResult:
    """
    CASH_OR_DEBT (BTB, money-market, deposits, P2P loans):
    same net-invested logic as FUND.
    """
    gross, net = _calc_net_invested(transactions)
    result.gross_invested_capital = gross
    result.net_invested_capital = net
    return result


def _apply_pipeline_rules(result: CostBasisResult, asset, transactions: list) -> CostBasisResult:
    """
    REAL_ESTATE_PIPELINE: only actual payments count.
    Warn if any future installments were accidentally booked.
    """
    meta = asset.extra_data or {} if hasattr(asset, "extra_data") else {}
    contract_price = Decimal(str(meta.get("contract_price", 0) or 0))
    if contract_price > ZERO and result.gross_invested_capital > contract_price:
        result.warnings.append(
            f"pipeline_overcapitalized: invested_capital ({result.gross_invested_capital}) "
            f"exceeds contract_price ({contract_price}) — check for future installments booked early"
        )
    return result


def _apply_real_estate_rules(result: CostBasisResult, asset, transactions: list) -> CostBasisResult:
    """
    REAL_ESTATE: validate debt consistency.
    """
    if result.debt_balance < ZERO:
        result.warnings.append(
            f"debt_reconciliation_failed: debt_balance is negative ({result.debt_balance}) "
            "— principal payments may exceed loan drawdowns"
        )
        result.debt_balance = ZERO
    return result


# ── Main calculator ────────────────────────────────────────────────────────────

def calc_cost_basis(
    asset,
    transactions: list,
    model: CalcModel,
    as_of: Optional[date] = None,
) -> CostBasisResult:
    """
    Calculate all capital-side metrics for an asset from its transaction history.

    Args:
        asset:        SQLAlchemy Asset ORM object (used for metadata/model overrides)
        transactions: List of Transaction ORM objects, pre-filtered to this asset and as_of date.
                      Must be ordered by transaction_date ascending.
        model:        CalcModel from resolve_model(asset)
        as_of:        Snapshot date (informational only — filtering is done by caller)

    Returns:
        CostBasisResult in asset's native currency
    """
    result = CostBasisResult()

    if not transactions:
        return result

    sale_proceeds = ZERO  # tracked separately to compute net_invested_capital

    for tx in transactions:
        flags: TxFlags = classify_transaction(tx)
        result.transaction_count += 1

        # Get transaction amount — use total_amount, fallback to cashflow_amount
        if hasattr(tx, "total_amount"):
            amount = tx.total_amount
        else:
            amount = tx.get("total_amount") or tx.get("cashflow_amount")

        if amount is None:
            if flags.warning:
                result.warnings.append(f"tx {getattr(tx, 'id', '?')}: {flags.warning}")
            continue

        amount = abs(Decimal(str(amount)))

        # Track last transaction date
        tx_date = getattr(tx, "transaction_date", None) or getattr(tx, "date", None)
        if tx_date and (result.last_transaction_date is None or tx_date > result.last_transaction_date):
            result.last_transaction_date = tx_date

        # ── Invested capital ───────────────────────────────────────────────
        if flags.affects_invested_capital:
            result.gross_invested_capital += amount

        if flags.reduces_invested_capital:
            # Sale proceeds — tracked for net_invested_capital calculation
            sale_proceeds += amount

        # ── Cashflow ───────────────────────────────────────────────────────
        if flags.affects_cashflow:
            result.net_cashflow += amount * flags.cashflow_sign

        # ── Income breakdown ───────────────────────────────────────────────
        if flags.affects_income:
            result.realized_income += amount

        if flags.affects_operating_expense:
            result.operating_expenses += amount

        if flags.affects_financing_cost:
            result.financing_cost += amount

        # ── Debt ───────────────────────────────────────────────────────────
        if flags.affects_debt:
            result.debt_balance += amount * flags.debt_sign

        # ── Warnings from classifier ───────────────────────────────────────
        if flags.warning:
            result.warnings.append(f"tx {getattr(tx, 'id', '?')}: {flags.warning}")

    # Net invested = gross minus what's been returned via sales/withdrawals
    result.net_invested_capital = result.gross_invested_capital - sale_proceeds

    # First investment date
    result.first_investment_date = get_first_investment_date(transactions)

    # Debt floor at zero (can't be negative)
    if result.debt_balance < ZERO:
        result.debt_balance = ZERO

    # ── Model-specific post-processing ────────────────────────────────────
    if model == CalcModel.FUND:
        result = _apply_fund_rules(result, asset, transactions)

    elif model == CalcModel.CASH_OR_DEBT:
        result = _apply_cash_or_debt_rules(result, asset, transactions)

    elif model == CalcModel.REAL_ESTATE_PIPELINE:
        result = _apply_pipeline_rules(result, asset, transactions)

    elif model == CalcModel.REAL_ESTATE:
        result = _apply_real_estate_rules(result, asset, transactions)

    return result


# ── Derived metrics (computed from CostBasisResult + CurrentValueResult) ───────

def calc_total_return(
    current_value_ils: Optional[Decimal],
    net_cashflow_ils: Decimal,
    invested_capital_ils: Decimal,
) -> Optional[Decimal]:
    """
    total_return = current_value + net_cashflow - invested_capital

    All values must be in the same currency (ILS).
    Returns None if current_value is unknown.
    """
    if current_value_ils is None:
        return None
    return current_value_ils + net_cashflow_ils - invested_capital_ils


def calc_total_return_pct(
    total_return: Optional[Decimal],
    invested_capital: Decimal,
) -> Optional[Decimal]:
    """
    total_return_pct = total_return / invested_capital

    Returns None if invested_capital <= 0 (avoids division by zero).
    """
    if total_return is None:
        return None
    if invested_capital <= ZERO:
        return None
    return total_return / invested_capital


def calc_annualized_return(
    total_return_pct: Optional[Decimal],
    first_investment_date: Optional[date],
    snapshot_date: Optional[date] = None,
) -> Optional[Decimal]:
    """
    Annualized return using CAGR formula:
        annualized = (1 + total_return_pct) ^ (365 / days_held) - 1

    Requirements:
      - first_investment_date must be known
      - total_return_pct must be known
      - days_held must be > 30 (too short to annualize meaningfully)

    Returns None if any requirement is not met.
    """
    if total_return_pct is None or first_investment_date is None:
        return None

    if snapshot_date is None:
        snapshot_date = date.today()

    days_held = (snapshot_date - first_investment_date).days
    if days_held < 30:
        return None

    try:
        base = float(1 + total_return_pct)
        if base <= 0:
            return None
        exponent = 365.0 / days_held
        annualized = base ** exponent - 1
        return Decimal(str(round(annualized, 6)))
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def calc_equity_value(
    current_value: Optional[Decimal],
    debt_balance: Decimal,
) -> Optional[Decimal]:
    """equity_value = current_value - debt_balance"""
    if current_value is None:
        return None
    return max(current_value - debt_balance, ZERO)


def calc_ltv(
    debt_balance: Decimal,
    current_value: Optional[Decimal],
) -> Optional[Decimal]:
    """ltv = debt_balance / current_value"""
    if current_value is None or current_value <= ZERO:
        return None
    if debt_balance <= ZERO:
        return ZERO
    return debt_balance / current_value
