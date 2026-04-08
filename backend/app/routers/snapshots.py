from datetime import date
from typing import List, Optional
from uuid import UUID
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, SessionLocal
from app.models.snapshot import PerformanceSnapshot
from app.schemas.snapshot import PerformanceSnapshotRead, SnapshotRebuildRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/", response_model=List[PerformanceSnapshotRead])
async def list_snapshots(
    portfolio_id: Optional[UUID] = Query(None),
    asset_id: Optional[UUID] = Query(None),
    snapshot_date: Optional[date] = Query(None),
    is_stale: Optional[bool] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(PerformanceSnapshot)
    if portfolio_id:
        q = q.where(PerformanceSnapshot.portfolio_id == portfolio_id)
    if asset_id:
        q = q.where(PerformanceSnapshot.asset_id == asset_id)
    if snapshot_date:
        q = q.where(PerformanceSnapshot.snapshot_date == snapshot_date)
    if is_stale is not None:
        q = q.where(PerformanceSnapshot.is_stale == is_stale)
    q = q.order_by(PerformanceSnapshot.snapshot_date.desc()).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


def _run_rebuild(portfolio_id: UUID, as_of_date: date, asset_id: Optional[UUID]) -> dict:
    """
    Synchronous engine run — executed in a thread pool so it doesn't
    block the async event loop.
    Uses a separate sync SessionLocal (not the async session).
    """
    from app.engine.snapshot_builder import build_portfolio_snapshot, build_asset_snapshot
    from app.models.asset import Asset

    db = SessionLocal()
    try:
        if asset_id:
            # Single asset rebuild
            asset = db.get(Asset, asset_id)
            if not asset:
                raise ValueError(f"Asset {asset_id} not found")
            snap = build_asset_snapshot(asset, db, as_of_date)
            return {
                "status": "ok",
                "mode": "single_asset",
                "asset_symbol": snap.asset_symbol,
                "model_used": snap.model_used.value,
                "current_value_ils": float(snap.current_value_ils) if snap.current_value_ils else None,
                "gross_invested_ils": float(snap.gross_invested_capital_ils),
                "total_return_ils": float(snap.total_return_ils) if snap.total_return_ils else None,
                "total_return_pct": float(snap.total_return_pct) if snap.total_return_pct else None,
                "annualized_return_pct": float(snap.annualized_return_pct) if snap.annualized_return_pct else None,
                "xirr_pct": float(snap.xirr_pct) if snap.xirr_pct else None,
                "confidence": snap.confidence,
                "value_source": snap.value_source,
                "warnings": snap.warnings,
                "snapshot_date": str(as_of_date),
            }
        else:
            # Full portfolio rebuild
            result = build_portfolio_snapshot(portfolio_id, db, as_of_date)

            # Build category summary
            categories = [
                {
                    "category": c.category,
                    "current_value_ils": float(c.current_value_ils),
                    "gross_invested_ils": float(c.gross_invested_capital_ils),
                    "total_return_ils": float(c.total_return_ils),
                    "total_return_pct": float(c.total_return_pct) if c.total_return_pct else None,
                    "asset_count": c.asset_count,
                }
                for c in result.category_snapshots
            ]

            # Build asset summary
            assets = [
                {
                    "symbol": s.asset_symbol,
                    "name": s.asset_name,
                    "category": s.category,
                    "model": s.model_used.value,
                    "current_value_ils": float(s.current_value_ils) if s.current_value_ils else None,
                    "total_return_pct": float(s.total_return_pct) if s.total_return_pct else None,
                    "xirr_pct": float(s.xirr_pct) if s.xirr_pct else None,
                    "confidence": s.confidence,
                    "warnings": s.warnings,
                }
                for s in result.asset_snapshots
            ]

            return {
                "status": "ok",
                "mode": "portfolio",
                "snapshot_date": str(as_of_date),
                "portfolio_id": str(portfolio_id),
                "summary": {
                    "total_value_ils": float(result.total_value_ils),
                    "total_invested_ils": float(result.total_invested_ils),
                    "total_return_ils": float(result.total_return_ils),
                    "total_return_pct": float(result.total_return_pct) if result.total_return_pct else None,
                    "total_debt_ils": float(result.total_debt_ils),
                    "net_equity_ils": float(result.net_equity_ils),
                    "asset_count": len(result.asset_snapshots),
                    "warnings": len(result.warnings),
                },
                "categories": categories,
                "assets": assets,
            }
    finally:
        db.close()


@router.post(
    "/rebuild",
    status_code=status.HTTP_200_OK,
    summary="Run portfolio snapshot engine",
)
async def rebuild_snapshots(
    payload: SnapshotRebuildRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Runs the Wealth OS calculation engine for a portfolio or single asset.

    - If `asset_id` is provided: rebuilds snapshot for that asset only
    - If only `portfolio_id`: rebuilds all active assets in the portfolio
    - `as_of_date` defaults to today if not provided

    Returns full snapshot results inline (synchronous execution).
    """
    as_of_date = payload.as_of_date or date.today()

    log.info(
        "Snapshot rebuild requested: portfolio=%s asset=%s date=%s",
        payload.portfolio_id, payload.asset_id, as_of_date
    )

    try:
        # Run sync engine in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _run_rebuild,
            payload.portfolio_id,
            as_of_date,
            payload.asset_id,
        )
        return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error("Snapshot rebuild failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Engine error: {str(e)}"
        )
