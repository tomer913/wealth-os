"""
Daily report builder — assembles a ReportData from the DB for a given portfolio.

All queries here are pure data fetching with no formatting.
Formatting is the responsibility of NotificationChannel.format().
"""
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.notifications.base import (
    BudgetSummary,
    ConnectorResult,
    PortfolioSummary,
    ReportData,
    SystemSummary,
    TransactionSummary,
)

log = logging.getLogger(__name__)

ZERO = Decimal("0")


async def build_daily_report(
    db: AsyncSession,
    portfolio_id: UUID,
    as_of: date | None = None,
) -> ReportData:
    """
    Build a ReportData for the given portfolio and date.
    as_of defaults to today.
    """
    if as_of is None:
        as_of = date.today()

    # IL time label for the report header
    now_il = datetime.now(timezone.utc).astimezone(
        __import__("zoneinfo").ZoneInfo("Asia/Jerusalem")
    )
    date_str = as_of.strftime("%Y-%m-%d")
    time_str = now_il.strftime("%H:%M")

    connectors  = await _connector_results(db, portfolio_id, as_of)
    txn_summary = await _transaction_summaries(db, portfolio_id, as_of)
    needs_review = await _needs_review_count(db, portfolio_id, as_of)
    budget      = await _budget_summary(db, portfolio_id, as_of)
    portfolio   = await _portfolio_summary(db, portfolio_id, as_of)
    system      = _system_summary(connectors, as_of)

    return ReportData(
        date=date_str,
        time=time_str,
        portfolio_id=str(portfolio_id),
        connectors=connectors,
        transactions=txn_summary,
        needs_review_count=needs_review,
        budget=budget,
        portfolio=portfolio,
        system=system,
    )


# ── Connector results ─────────────────────────────────────────────────────────

async def _connector_results(
    db: AsyncSession, portfolio_id: UUID, as_of: date
) -> list:
    from app.models.connector import Connector, ConnectorRun

    today_start = datetime.combine(as_of, datetime.min.time()).replace(tzinfo=timezone.utc)

    # Latest run per connector for today
    subq = (
        select(
            ConnectorRun.connector_id,
            func.max(ConnectorRun.started_at).label("latest_start"),
        )
        .where(ConnectorRun.started_at >= today_start)
        .group_by(ConnectorRun.connector_id)
        .subquery()
    )

    q = (
        select(Connector, ConnectorRun)
        .join(ConnectorRun, ConnectorRun.connector_id == Connector.id)
        .join(
            subq,
            and_(
                subq.c.connector_id == ConnectorRun.connector_id,
                subq.c.latest_start == ConnectorRun.started_at,
            ),
        )
        .where(Connector.portfolio_id == portfolio_id)
        .order_by(Connector.name)
    )

    rows = (await db.execute(q)).all()

    results = []
    for connector, run in rows:
        results.append(ConnectorResult(
            name=connector.name,
            type=connector.type,
            status=run.status or "unknown",
            duration_ms=run.duration_ms or 0,
            transactions_created=run.transactions_created or 0,
            transactions_skipped=run.transactions_skipped or 0,
            prices_updated=run.prices_updated or 0,
            fx_rates_updated=run.fx_rates_updated or 0,
            valuations_created=run.valuations_created or 0,
            assets_created=run.assets_created or 0,
            error_message=run.error_message,
        ))

    return results


# ── Transaction summaries ─────────────────────────────────────────────────────

async def _transaction_summaries(
    db: AsyncSession, portfolio_id: UUID, as_of: date
) -> list:
    from app.models.transaction import Transaction

    q = (
        select(
            Transaction.source,
            Transaction.currency,
            func.count(Transaction.id).label("cnt"),
            func.sum(func.abs(Transaction.total_amount)).label("vol"),
            func.array_agg(Transaction.type.distinct()).label("types"),
        )
        .where(
            and_(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_date == as_of,
            )
        )
        .group_by(Transaction.source, Transaction.currency)
        .order_by(func.count(Transaction.id).desc())
    )

    rows = (await db.execute(q)).all()
    summaries = []
    for row in rows:
        types = [t for t in (row.types or []) if t] or []
        summaries.append(TransactionSummary(
            source=row.source or "unknown",
            count=row.cnt or 0,
            volume=float(row.vol or 0),
            currency=row.currency or "ILS",
            types=types[:5],
        ))
    return summaries


# ── Needs-review count ────────────────────────────────────────────────────────

async def _needs_review_count(
    db: AsyncSession, portfolio_id: UUID, as_of: date
) -> int:
    from app.models.budget import ClassificationLog
    from app.models.raw_layer import RawTransaction

    today_start = datetime.combine(as_of, datetime.min.time()).replace(tzinfo=timezone.utc)

    q = (
        select(func.count(ClassificationLog.id))
        .join(RawTransaction, RawTransaction.id == ClassificationLog.raw_transaction_id)
        .where(
            and_(
                RawTransaction.portfolio_id == portfolio_id,
                ClassificationLog.needs_review == True,
                ClassificationLog.processed_at >= today_start,
            )
        )
    )
    return (await db.execute(q)).scalar_one() or 0


# ── Budget summary ────────────────────────────────────────────────────────────

async def _budget_summary(
    db: AsyncSession, portfolio_id: UUID, as_of: date
) -> BudgetSummary:
    from app.models.budget import (
        BudgetActual,
        BudgetCategory,
        BudgetPlan,
        ClassificationLog,
    )
    from app.models.raw_layer import RawTransaction

    year  = as_of.year
    month = as_of.month
    month_label = as_of.strftime("%B %Y")
    today_start = datetime.combine(as_of, datetime.min.time()).replace(tzinfo=timezone.utc)

    # Income vs expense actuals and planned
    actuals_q = (
        select(
            BudgetCategory.category_type,
            func.sum(BudgetActual.actual_amount).label("total_actual"),
        )
        .join(BudgetCategory, BudgetCategory.id == BudgetActual.category_id)
        .where(
            and_(
                BudgetActual.portfolio_id == portfolio_id,
                BudgetActual.year == year,
                BudgetActual.month == month,
            )
        )
        .group_by(BudgetCategory.category_type)
    )
    actuals_rows = (await db.execute(actuals_q)).all()
    actual_by_type: dict = {row.category_type: float(row.total_actual or 0)
                             for row in actuals_rows}

    planned_q = (
        select(
            BudgetCategory.category_type,
            func.sum(BudgetPlan.monthly_amount).label("total_planned"),
        )
        .join(BudgetCategory, BudgetCategory.id == BudgetPlan.category_id)
        .where(
            and_(
                BudgetPlan.portfolio_id == portfolio_id,
                BudgetPlan.year == year,
            )
        )
        .group_by(BudgetCategory.category_type)
    )
    planned_rows = (await db.execute(planned_q)).all()
    planned_by_type: dict = {row.category_type: float(row.total_planned or 0)
                              for row in planned_rows}

    # Top expense categories
    top_q = (
        select(BudgetCategory.name, BudgetActual.actual_amount)
        .join(BudgetCategory, BudgetCategory.id == BudgetActual.category_id)
        .where(
            and_(
                BudgetActual.portfolio_id == portfolio_id,
                BudgetActual.year == year,
                BudgetActual.month == month,
                BudgetCategory.category_type == "expense",
            )
        )
        .order_by(BudgetActual.actual_amount.desc())
        .limit(5)
    )
    top_rows = (await db.execute(top_q)).all()
    top_categories = [
        {"name": row.name, "amount": float(row.actual_amount or 0)}
        for row in top_rows
    ]

    # Today's classification breakdown
    method_q = (
        select(
            ClassificationLog.method,
            func.count(ClassificationLog.id).label("cnt"),
        )
        .join(RawTransaction, RawTransaction.id == ClassificationLog.raw_transaction_id)
        .where(
            and_(
                RawTransaction.portfolio_id == portfolio_id,
                ClassificationLog.processed_at >= today_start,
            )
        )
        .group_by(ClassificationLog.method)
    )
    method_rows = (await db.execute(method_q)).all()
    by_method: dict = {row.method: row.cnt for row in method_rows}

    new_today       = sum(by_method.values())
    auto_classified = by_method.get("rule", 0)
    ai_classified   = by_method.get("ai", 0)

    # Needs review count for the month
    needs_review_q = (
        select(func.count(ClassificationLog.id))
        .join(RawTransaction, RawTransaction.id == ClassificationLog.raw_transaction_id)
        .where(
            and_(
                RawTransaction.portfolio_id == portfolio_id,
                ClassificationLog.needs_review == True,
            )
        )
    )
    needs_review = (await db.execute(needs_review_q)).scalar_one() or 0

    return BudgetSummary(
        month=month_label,
        total_income=actual_by_type.get("income", 0),
        total_income_planned=planned_by_type.get("income", 0),
        total_expenses=actual_by_type.get("expense", 0),
        total_expenses_planned=planned_by_type.get("expense", 0),
        top_categories=top_categories,
        new_today=new_today,
        auto_classified=auto_classified,
        ai_classified=ai_classified,
        needs_review=needs_review,
    )


# ── Portfolio summary ─────────────────────────────────────────────────────────

async def _portfolio_summary(
    db: AsyncSession, portfolio_id: UUID, as_of: date
) -> PortfolioSummary:
    from app.models.asset import Asset
    from app.models.snapshot import PerformanceSnapshot

    # Today's portfolio-level snapshot (asset_id IS NULL = portfolio total)
    today_snap = (await db.execute(
        select(PerformanceSnapshot.current_value)
        .where(
            and_(
                PerformanceSnapshot.portfolio_id == portfolio_id,
                PerformanceSnapshot.asset_id == None,
                PerformanceSnapshot.snapshot_date <= as_of,
            )
        )
        .order_by(PerformanceSnapshot.snapshot_date.desc())
        .limit(1)
    )).scalar_one_or_none()

    today_value = float(today_snap or 0)

    # Yesterday's value for daily change
    yesterday = as_of - timedelta(days=1)
    yesterday_snap = (await db.execute(
        select(PerformanceSnapshot.current_value)
        .where(
            and_(
                PerformanceSnapshot.portfolio_id == portfolio_id,
                PerformanceSnapshot.asset_id == None,
                PerformanceSnapshot.snapshot_date <= yesterday,
            )
        )
        .order_by(PerformanceSnapshot.snapshot_date.desc())
        .limit(1)
    )).scalar_one_or_none()

    yesterday_value = float(yesterday_snap or 0)
    daily_change = today_value - yesterday_value
    daily_change_pct = (daily_change / yesterday_value * 100) if yesterday_value else 0.0

    # Top gainer and loser from asset-level snapshots
    asset_snaps = (await db.execute(
        select(Asset.symbol, PerformanceSnapshot.total_return_pct)
        .join(Asset, Asset.id == PerformanceSnapshot.asset_id)
        .where(
            and_(
                PerformanceSnapshot.portfolio_id == portfolio_id,
                PerformanceSnapshot.asset_id != None,
                PerformanceSnapshot.snapshot_date == as_of,
                PerformanceSnapshot.total_return_pct != None,
            )
        )
        .order_by(PerformanceSnapshot.total_return_pct.desc())
    )).all()

    top_gainer_symbol = asset_snaps[0].symbol if asset_snaps else ""
    top_gainer_pct    = float((asset_snaps[0].total_return_pct or 0) * 100) if asset_snaps else 0.0
    top_loser_symbol  = asset_snaps[-1].symbol if asset_snaps else ""
    top_loser_pct     = float((asset_snaps[-1].total_return_pct or 0) * 100) if asset_snaps else 0.0

    return PortfolioSummary(
        total_value_ils=today_value,
        daily_change_ils=daily_change,
        daily_change_pct=daily_change_pct,
        top_gainer_symbol=top_gainer_symbol,
        top_gainer_pct=top_gainer_pct,
        top_loser_symbol=top_loser_symbol,
        top_loser_pct=top_loser_pct,
    )


# ── System summary ────────────────────────────────────────────────────────────

def _system_summary(connectors: list, as_of: date) -> SystemSummary:
    succeeded = sum(1 for c in connectors if c.status == "success")
    failed    = sum(1 for c in connectors if c.status == "failed")
    skipped   = sum(1 for c in connectors if c.status in ("skipped", "no_data"))
    total_ms  = sum(c.duration_ms for c in connectors)

    return SystemSummary(
        total_connectors=len(connectors),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        snapshot_rebuilt_at=as_of.strftime("%H:%M"),
        total_duration_seconds=total_ms / 1000,
    )
