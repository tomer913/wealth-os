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


@router.get("/latest", summary="Get latest cached snapshot from DB (fast)")
async def get_latest_snapshot(
    portfolio_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    from app.models.asset import Asset
    from sqlalchemy import func as sqlfunc

    latest_date_q = select(sqlfunc.max(PerformanceSnapshot.snapshot_date)).where(
        PerformanceSnapshot.portfolio_id == portfolio_id
    )
    latest_date = (await db.execute(latest_date_q)).scalar_one_or_none()
    if not latest_date:
        return None

    q = (
        select(PerformanceSnapshot, Asset)
        .join(Asset, Asset.id == PerformanceSnapshot.asset_id)
        .where(
            PerformanceSnapshot.portfolio_id == portfolio_id,
            PerformanceSnapshot.snapshot_date == latest_date,
        )
    )
    rows = (await db.execute(q)).all()
    if not rows:
        return None

    asset_snapshots = []
    category_buckets: dict = {}
    total_value = total_invested = total_return = total_debt = 0.0

    for ps, asset in rows:
        val = float(ps.value_ils or 0)
        invested = float(ps.invested_capital or 0)
        ret = float(ps.total_return or 0)
        cat = asset.category or "other"

        asset_snapshots.append({
            "symbol": asset.symbol, "name": asset.name, "category": cat,
            "model": ps.model_used or "unknown",
            "current_value_ils": val,
            "total_return_pct": float(ps.total_return_pct) if ps.total_return_pct else None,
            "xirr_pct": float(ps.xirr_return_pct) if ps.xirr_return_pct else None,
            "confidence": "medium", "warnings": [],
        })
        total_value += val
        total_invested += invested
        total_return += ret

        if cat not in category_buckets:
            category_buckets[cat] = {"current_value_ils": 0.0, "gross_invested_ils": 0.0,
                                     "total_return_ils": 0.0, "asset_count": 0}
        category_buckets[cat]["current_value_ils"] += val
        category_buckets[cat]["gross_invested_ils"] += invested
        category_buckets[cat]["total_return_ils"] += ret
        category_buckets[cat]["asset_count"] += 1

    categories = [
        {"category": cat, **data,
         "total_return_pct": (data["total_return_ils"] / data["gross_invested_ils"])
                              if data["gross_invested_ils"] > 0 else None}
        for cat, data in sorted(category_buckets.items(),
                                key=lambda x: x[1]["current_value_ils"], reverse=True)
    ]

    return {
        "status": "ok", "mode": "portfolio",
        "snapshot_date": str(latest_date),
        "portfolio_id": str(portfolio_id),
        "built_at": latest_date.isoformat() + "T08:00:00",
        "summary": {
            "total_value_ils": total_value,
            "total_invested_ils": total_invested,
            "total_return_ils": total_return,
            "total_return_pct": (total_return / total_invested) if total_invested > 0 else None,
            "total_debt_ils": total_debt,
            "net_equity_ils": total_value - total_debt,
            "asset_count": len(asset_snapshots),
            "warnings": 0,
        },
        "categories": categories,
        "assets": asset_snapshots,
    }


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

            # ── Persist to performance_snapshots table ──────────────────────
            from app.models.snapshot import PerformanceSnapshot
            from sqlalchemy import and_

            for snap in result.asset_snapshots:
                if snap.asset_id is None:
                    continue
                # Upsert: delete existing snapshot for this asset+date, insert new
                existing = db.query(PerformanceSnapshot).filter(
                    and_(
                        PerformanceSnapshot.asset_id == snap.asset_id,
                        PerformanceSnapshot.snapshot_date == as_of_date,
                    )
                ).first()
                if existing:
                    db.delete(existing)
                    db.flush()

                ps = PerformanceSnapshot(
                    portfolio_id=portfolio_id,
                    asset_id=snap.asset_id,
                    snapshot_date=as_of_date,
                    value_ils=snap.current_value_ils,
                    current_value=snap.current_value_ils,
                    invested_capital=snap.gross_invested_capital_ils,
                    total_return=snap.total_return_ils,
                    total_return_pct=snap.total_return_pct,
                    xirr_return_pct=snap.xirr_pct,
                    model_used=snap.model_used.value if snap.model_used else None,
                    currency="ILS",
                    is_stale=False,
                )
                db.add(ps)
            db.commit()
            log.info("Persisted %d asset snapshots to performance_snapshots", len(result.asset_snapshots))
            # ────────────────────────────────────────────────────────────────

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
