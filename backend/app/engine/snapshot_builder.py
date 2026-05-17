"""
engine/snapshot_builder.py

The orchestrator — manages the full calculation flow for a portfolio snapshot.

Flow per asset:
  1. resolve_model(asset)
  2. load transactions
  3. calc_current_value()
  4. calc_cost_basis()
  5. convert all amounts to ILS
  6. calc derived metrics (total_return, annualized, equity, ltv)
  7. calc_asset_xirr()
  8. score_confidence()
  9. collect warnings

Then aggregates:
  asset snapshots → category snapshots → portfolio snapshot

Usage:
    from app.engine.snapshot_builder import build_portfolio_snapshot
    result = build_portfolio_snapshot(portfolio_id, db, snapshot_date=date.today())
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.model_resolver import resolve_model, CalcModel
from app.engine.current_value import calc_current_value, get_asset_transactions
from app.engine.cost_basis import (
    calc_cost_basis,
    calc_total_return,
    calc_total_return_pct,
    calc_annualized_return,
    calc_equity_value,
    calc_ltv,
)
from app.engine.xirr import calc_asset_xirr

log = logging.getLogger(__name__)
ZERO = Decimal("0")
ONE  = Decimal("1")


# ── Result containers ──────────────────────────────────────────────────────────

@dataclass
class AssetSnapshotResult:
    asset_id: UUID
    asset_symbol: str
    asset_name: str
    category: str
    model_used: CalcModel
    snapshot_date: date

    # Value
    current_value_native: Optional[Decimal] = None
    current_value_ils: Optional[Decimal] = None
    currency: str = "ILS"
    fx_rate_used: Decimal = ONE
    value_source: str = "none"

    # Capital (native currency)
    gross_invested_capital: Decimal = ZERO
    net_invested_capital: Decimal = ZERO

    # Capital (ILS)
    gross_invested_capital_ils: Decimal = ZERO
    net_invested_capital_ils: Decimal = ZERO

    # Debt / equity (ILS)
    debt_balance_ils: Decimal = ZERO
    equity_value_ils: Optional[Decimal] = None
    ltv: Optional[Decimal] = None

    # Cashflow breakdown (ILS)
    net_cashflow_ils: Decimal = ZERO
    realized_income_ils: Decimal = ZERO
    operating_expenses_ils: Decimal = ZERO
    financing_cost_ils: Decimal = ZERO

    # Returns
    total_return_ils: Optional[Decimal] = None
    total_return_pct: Optional[Decimal] = None
    annualized_return_pct: Optional[Decimal] = None
    xirr_pct: Optional[Decimal] = None

    # Dates
    first_investment_date: Optional[date] = None
    last_transaction_date: Optional[date] = None

    # Quality
    confidence: str = "low"
    warnings: List[str] = field(default_factory=list)


@dataclass
class CategorySnapshotResult:
    category: str
    snapshot_date: date
    current_value_ils: Decimal = ZERO
    gross_invested_capital_ils: Decimal = ZERO
    net_cashflow_ils: Decimal = ZERO
    total_return_ils: Decimal = ZERO
    total_return_pct: Optional[Decimal] = None
    asset_count: int = 0


@dataclass
class PortfolioSnapshotResult:
    portfolio_id: UUID
    snapshot_date: date
    total_value_ils: Decimal = ZERO
    total_invested_ils: Decimal = ZERO
    total_return_ils: Decimal = ZERO
    total_return_pct: Optional[Decimal] = None
    total_debt_ils: Decimal = ZERO
    net_equity_ils: Decimal = ZERO
    asset_snapshots: List[AssetSnapshotResult] = field(default_factory=list)
    category_snapshots: List[CategorySnapshotResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ── FUND valuation-only baseline ───────────────────────────────────────────────

def _fund_baseline_capital(asset, db: Session, snapshot_date: date) -> Decimal:
    """
    For FUND assets with tracking_level=valuation_only:
    use the earliest known valuation as invested_capital baseline.
    """
    from app.models.valuation import ManualValuation

    meta = asset.extra_data or {}
    if meta.get("tracking_level") != "valuation_only":
        return ZERO

    first_val = (
        db.query(ManualValuation)
        .filter(
            ManualValuation.asset_id == asset.id,
            ManualValuation.valuation_date <= snapshot_date,
        )
        .order_by(ManualValuation.valuation_date.asc())
        .first()
    )
    return first_val.market_value if (first_val and first_val.market_value) else ZERO


# ── Per-asset snapshot ─────────────────────────────────────────────────────────

def build_asset_snapshot(asset, db: Session, snapshot_date: date) -> AssetSnapshotResult:
    model = resolve_model(asset)
    result = AssetSnapshotResult(
        asset_id=asset.id,
        asset_symbol=asset.symbol or "",
        asset_name=asset.name or "",
        category=asset.category or model.value,
        model_used=model,
        snapshot_date=snapshot_date,
        currency=asset.currency or "ILS",
    )

    log.info("  [%s] %s — %s", model.value, asset.symbol, asset.name)

    # Step 1: transactions
    transactions = get_asset_transactions(db, asset.id, snapshot_date)

    # Step 2: current value
    cv = calc_current_value(asset, db, snapshot_date)
    result.current_value_native = cv.value_native
    result.current_value_ils    = cv.value_ils
    result.fx_rate_used         = cv.fx_rate_used or ONE
    result.value_source         = cv.value_source
    if cv.warning:
        result.warnings.append(f"current_value: {cv.warning}")

    # Step 3: cost basis
    cb = calc_cost_basis(asset, transactions, model, snapshot_date)

    # FUND override
    if model == CalcModel.FUND and cb.gross_invested_capital == ZERO:
        baseline = _fund_baseline_capital(asset, db, snapshot_date)
        if baseline > ZERO:
            cb.gross_invested_capital = baseline
            cb.net_invested_capital   = baseline
            result.warnings.append("fund_valuation_only: invested_capital from first valuation")

    result.gross_invested_capital = cb.gross_invested_capital
    result.net_invested_capital   = cb.net_invested_capital
    result.first_investment_date  = cb.first_investment_date
    result.last_transaction_date  = cb.last_transaction_date
    result.warnings.extend(cb.warnings)

    # Step 4: convert to ILS
    fx = result.fx_rate_used
    result.gross_invested_capital_ils = cb.gross_invested_capital * fx
    result.net_invested_capital_ils   = cb.net_invested_capital * fx
    result.debt_balance_ils           = cb.debt_balance * fx
    result.net_cashflow_ils           = cb.net_cashflow * fx
    result.realized_income_ils        = cb.realized_income * fx
    result.operating_expenses_ils     = cb.operating_expenses * fx
    result.financing_cost_ils         = cb.financing_cost * fx

    # Step 5: derived metrics
    result.equity_value_ils = calc_equity_value(result.current_value_ils, result.debt_balance_ils)
    result.ltv              = calc_ltv(result.debt_balance_ils, result.current_value_ils)

    if model == CalcModel.FUND:
        # FUND return: (current_value - net_invested) / net_invested
        # Uses net_invested so partial withdrawals don't distort the yield display.
        # Requires at least one transaction — pension/securities with only manual
        # valuations and no transaction history show null (can't calculate return).
        cur_val = result.current_value_ils
        net_inv = result.net_invested_capital_ils
        if cur_val is not None and net_inv and net_inv > ZERO and len(transactions) > 0:
            diff = cur_val - net_inv
            result.total_return_ils = diff
            result.total_return_pct = diff / net_inv
        # else: total_return_ils and total_return_pct remain None
    else:
        result.total_return_ils = calc_total_return(
            result.current_value_ils,
            result.net_cashflow_ils,
            result.gross_invested_capital_ils,
        )
        result.total_return_pct = calc_total_return_pct(
            result.total_return_ils,
            result.gross_invested_capital_ils,
        )

    result.annualized_return_pct = calc_annualized_return(
        result.total_return_pct,
        result.first_investment_date,
        snapshot_date,
    )

    # Step 6: XIRR
    xirr = calc_asset_xirr(
        transactions=transactions,
        current_value_ils=result.current_value_ils,
        snapshot_date=snapshot_date,
        asset_currency=result.currency,
        fx_rate=fx,
    )
    result.xirr_pct = xirr.xirr_pct
    if xirr.warning:
        result.warnings.append(f"xirr: {xirr.warning}")

    # For pension/securities FUND assets, prefer XIRR return when available
    if model == CalcModel.FUND and result.xirr_pct is not None:
        cat = (getattr(asset, "category", None) or "").lower()
        if cat in ("pension", "securities", "mutual_fund", "etf"):
            result.total_return_pct = result.xirr_pct

    # Step 7: pipeline sanity check
    if model == CalcModel.REAL_ESTATE_PIPELINE:
        if result.current_value_ils and result.gross_invested_capital_ils > ZERO:
            if result.current_value_ils > result.gross_invested_capital_ils * Decimal("1.5"):
                result.warnings.append("pipeline_value_may_be_overstated")

    # Step 8: confidence
    result.confidence = _score_confidence(result, cv.confidence, xirr.confidence)

    return result


# ── Confidence scoring ─────────────────────────────────────────────────────────

def _score_confidence(snap: AssetSnapshotResult, cv_conf: str, xirr_conf: str) -> str:
    if snap.current_value_ils is None or cv_conf == "low":
        return "low"
    if (
        cv_conf == "high"
        and snap.gross_invested_capital_ils > ZERO
        and snap.first_investment_date is not None
        and len(snap.warnings) == 0
    ):
        return "high"
    if cv_conf in ("high", "medium") and snap.gross_invested_capital_ils > ZERO:
        return "medium"
    return "low"


# ── Category aggregation ───────────────────────────────────────────────────────

def _aggregate_categories(snaps: List[AssetSnapshotResult], snapshot_date: date) -> List[CategorySnapshotResult]:
    buckets: Dict[str, List[AssetSnapshotResult]] = defaultdict(list)
    for s in snaps:
        buckets[s.category].append(s)

    results = []
    for cat, items in buckets.items():
        c = CategorySnapshotResult(category=cat, snapshot_date=snapshot_date)
        c.asset_count                 = len(items)
        c.current_value_ils           = sum((s.current_value_ils or ZERO) for s in items)
        c.gross_invested_capital_ils  = sum(s.gross_invested_capital_ils for s in items)
        c.net_cashflow_ils            = sum(s.net_cashflow_ils for s in items)
        c.total_return_ils            = sum((s.total_return_ils or ZERO) for s in items)
        c.total_return_pct            = calc_total_return_pct(c.total_return_ils, c.gross_invested_capital_ils)
        results.append(c)

    return sorted(results, key=lambda c: c.current_value_ils, reverse=True)


# ── Main entry point ───────────────────────────────────────────────────────────

def build_portfolio_snapshot(
    portfolio_id,
    db: Session,
    snapshot_date: Optional[date] = None,
) -> PortfolioSnapshotResult:
    """
    Build a complete portfolio snapshot for all active assets.

    Args:
        portfolio_id:  UUID of the portfolio
        db:            Active SQLAlchemy session
        snapshot_date: Date to snapshot (default: today)

    Returns:
        PortfolioSnapshotResult
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    from app.models.asset import Asset

    log.info("=== Portfolio snapshot: %s as of %s ===", portfolio_id, snapshot_date)

    assets = (
        db.query(Asset)
        .filter(Asset.portfolio_id == portfolio_id, Asset.status == "active")
        .all()
    )
    log.info("  Active assets: %d", len(assets))

    result = PortfolioSnapshotResult(portfolio_id=portfolio_id, snapshot_date=snapshot_date)

    for asset in assets:
        try:
            snap = build_asset_snapshot(asset, db, snapshot_date)
            result.asset_snapshots.append(snap)
        except Exception as e:
            log.error("  [ERROR] %s: %s", getattr(asset, "symbol", "?"), e)
            result.warnings.append(f"asset {getattr(asset, 'symbol', '?')} failed: {e}")

    result.category_snapshots = _aggregate_categories(result.asset_snapshots, snapshot_date)

    result.total_value_ils    = sum((s.current_value_ils or ZERO) for s in result.asset_snapshots)
    result.total_invested_ils = sum(s.gross_invested_capital_ils for s in result.asset_snapshots)
    result.total_debt_ils     = sum(s.debt_balance_ils for s in result.asset_snapshots)
    result.net_equity_ils     = result.total_value_ils - result.total_debt_ils
    result.total_return_ils   = sum((s.total_return_ils or ZERO) for s in result.asset_snapshots)
    result.total_return_pct   = calc_total_return_pct(result.total_return_ils, result.total_invested_ils)

    log.info("  Total value    ILS: %s", result.total_value_ils)
    log.info("  Total invested ILS: %s", result.total_invested_ils)
    log.info("  Total return   ILS: %s", result.total_return_ils)
    log.info("  Return %%:          %s", result.total_return_pct)
    log.info("  Warnings:          %d", len(result.warnings))
    log.info("=== Done ===")

    return result
