"""
engine/xirr.py

Calculates XIRR (Extended Internal Rate of Return) for an asset.

Sign convention (investor perspective):
  NEGATIVE = money leaving investor  (BUY, DEPOSIT, INVESTMENT_OUTFLOW)
  POSITIVE = money returning         (SELL, INCOME, WITHDRAWAL)
  POSITIVE = current_value as terminal cashflow on snapshot_date
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional
import logging

from app.engine.model_resolver import classify_transaction

log = logging.getLogger(__name__)
ZERO = Decimal("0")


@dataclass
class CashflowEntry:
    dt: date
    amount: float   # signed
    label: str = ""


@dataclass
class XirrResult:
    xirr_pct: Optional[Decimal]
    cashflow_count: int = 0
    first_cashflow_date: Optional[date] = None
    last_cashflow_date: Optional[date] = None
    confidence: str = "low"
    warning: Optional[str] = None


def _npv(rate: float, cfs: List[CashflowEntry]) -> float:
    t0 = cfs[0].dt
    total = 0.0
    for cf in cfs:
        years = (cf.dt - t0).days / 365.0
        try:
            total += cf.amount / ((1 + rate) ** years)
        except (ZeroDivisionError, OverflowError):
            return float("inf")
    return total


def _dnpv(rate: float, cfs: List[CashflowEntry]) -> float:
    t0 = cfs[0].dt
    total = 0.0
    for cf in cfs:
        years = (cf.dt - t0).days / 365.0
        if years == 0:
            continue
        try:
            total += -years * cf.amount / ((1 + rate) ** (years + 1))
        except (ZeroDivisionError, OverflowError):
            pass
    return total


def _solve_xirr(cfs: List[CashflowEntry], max_iter: int = 100, tol: float = 1e-6) -> Optional[float]:
    if len(cfs) < 2:
        return None
    if not any(c.amount > 0 for c in cfs) or not any(c.amount < 0 for c in cfs):
        return None
    for guess in [0.1, 0.0, -0.1, 0.5, -0.5]:
        rate = guess
        for _ in range(max_iter):
            try:
                npv = _npv(rate, cfs)
                d = _dnpv(rate, cfs)
                if abs(d) < 1e-12:
                    break
                new_rate = rate - npv / d
                if abs(new_rate - rate) < tol:
                    if -0.999 < new_rate < 100.0:
                        return new_rate
                    break
                rate = new_rate
            except (ValueError, OverflowError, ZeroDivisionError):
                break
    return None


def build_xirr_cashflows(
    transactions: list,
    current_value_ils: Optional[Decimal],
    snapshot_date: date,
    asset_currency: str = "ILS",
    fx_rate: Decimal = Decimal("1"),
) -> List[CashflowEntry]:
    entries: List[CashflowEntry] = []
    for tx in transactions:
        flags = classify_transaction(tx)
        if not flags.include_in_xirr:
            continue
        if hasattr(tx, "total_amount"):
            amount = tx.total_amount
            tx_currency = tx.currency or asset_currency
            tx_date = tx.transaction_date
        else:
            amount = tx.get("total_amount") or tx.get("cashflow_amount")
            tx_currency = tx.get("currency") or asset_currency
            tx_date = tx.get("transaction_date") or tx.get("date")
        if amount is None or tx_date is None:
            continue
        amount_d = abs(Decimal(str(amount)))
        if tx_currency != "ILS":
            amount_d *= fx_rate
        entries.append(CashflowEntry(
            dt=tx_date,
            amount=float(amount_d) * flags.xirr_sign,
            label=f"{getattr(tx, 'economic_type', '')} {getattr(tx, 'type', '')}".strip(),
        ))
    if current_value_ils is not None and current_value_ils > ZERO:
        entries.append(CashflowEntry(dt=snapshot_date, amount=float(current_value_ils), label="terminal_value"))
    entries.sort(key=lambda e: e.dt)
    return entries


def calc_xirr(cashflows: List[CashflowEntry], min_days: int = 30) -> XirrResult:
    result = XirrResult(xirr_pct=None)
    if not cashflows:
        result.warning = "no cashflows"
        return result
    non_terminal = [c for c in cashflows if c.label != "terminal_value"]
    result.cashflow_count = len(non_terminal)
    if non_terminal:
        result.first_cashflow_date = non_terminal[0].dt
        result.last_cashflow_date = non_terminal[-1].dt
    days_span = (cashflows[-1].dt - cashflows[0].dt).days
    if days_span < min_days:
        result.warning = f"holding period too short ({days_span} days)"
        return result
    total_invested = sum(abs(c.amount) for c in cashflows if c.amount < 0)
    if total_invested > 0:
        date_amounts = {}
        for c in non_terminal:
            date_amounts[c.dt] = date_amounts.get(c.dt, 0) + abs(c.amount)
        if date_amounts and max(date_amounts.values()) > total_invested * 0.5:
            result.warning = "aggregated_cashflow_may_distort_xirr"
    rate = _solve_xirr(cashflows)
    if rate is None:
        result.warning = (result.warning or "") + " | solver did not converge"
        return result
    result.xirr_pct = Decimal(str(round(rate, 6)))
    if result.cashflow_count >= 5 and days_span >= 365 and not result.warning:
        result.confidence = "high"
    elif result.cashflow_count >= 2 and days_span >= 90:
        result.confidence = "medium"
    return result


def calc_asset_xirr(
    transactions: list,
    current_value_ils: Optional[Decimal],
    snapshot_date: date,
    asset_currency: str = "ILS",
    fx_rate: Decimal = Decimal("1"),
) -> XirrResult:
    """One-call convenience used by snapshot_builder."""
    return calc_xirr(build_xirr_cashflows(transactions, current_value_ils, snapshot_date, asset_currency, fx_rate))
