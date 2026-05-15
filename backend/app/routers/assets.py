from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.asset import Asset
from app.models.transaction import Transaction
from sqlalchemy import text
from app.schemas.asset import (
    AssetCreate, AssetListResponse, AssetListResponseEnriched,
    AssetRead, AssetReadEnriched, AssetUpdate,
)
from app.utils.enums import AssetBehavior, AssetCategory, AssetStatus

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/", response_model=AssetListResponseEnriched)
async def list_assets(
    portfolio_id: Optional[UUID] = Query(None),
    account_id: Optional[UUID] = Query(None),
    category: Optional[AssetCategory] = Query(None),
    asset_behavior: Optional[AssetBehavior] = Query(None),
    status: Optional[AssetStatus] = Query(None),
    search: Optional[str] = Query(None, description="Search by name or symbol"),
    page: int = Query(1, ge=1),
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if portfolio_id:
        await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    q = select(Asset)
    if portfolio_id:
        q = q.where(Asset.portfolio_id == portfolio_id)
    if account_id:
        q = q.where(Asset.account_id == account_id)
    if category:
        q = q.where(Asset.category == category.value)
    if asset_behavior:
        q = q.where(Asset.asset_behavior == asset_behavior.value)
    if status:
        q = q.where(Asset.status == status.value)
    if search:
        term = f"%{search.lower()}%"
        q = q.where(
            (func.lower(Asset.name).like(term)) |
            (func.lower(Asset.symbol).like(term))
        )

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginated results
    offset = (page - 1) * limit
    q = q.order_by(Asset.name).offset(offset).limit(limit)
    result = await db.execute(q)
    items = result.scalars().all()

    # ── Enrich with latest snapshot values and computed net_quantity ──────────
    snap_lookup: dict = {}
    qty_lookup: dict = {}

    if portfolio_id and items:
        # Latest snapshot per asset (DISTINCT ON is PostgreSQL-specific)
        snap_rows = await db.execute(
            text("""
                SELECT DISTINCT ON (asset_id)
                    asset_id::text,
                    current_value,
                    invested_capital,
                    total_return_pct
                FROM performance_snapshots
                WHERE portfolio_id = :pid
                ORDER BY asset_id, snapshot_date DESC
            """),
            {"pid": str(portfolio_id)},
        )
        snap_lookup = {row.asset_id: row for row in snap_rows}

        # Net quantity per asset from transaction history
        qty_rows = await db.execute(
            text("""
                SELECT
                    asset_id::text,
                    SUM(CASE WHEN UPPER(type) IN
                            ('BUY','VEST','ALLOCATION','BONUS','SWAP_IN','EXTERNAL_DEPOSIT')
                        THEN COALESCE(quantity, 0) ELSE 0 END) -
                    SUM(CASE WHEN UPPER(type) IN
                            ('SELL','EXTERNAL_WITHDRAWAL','WITHDRAWAL')
                        THEN COALESCE(quantity, 0) ELSE 0 END) AS net_quantity
                FROM transactions
                WHERE portfolio_id = :pid
                AND quantity IS NOT NULL
                GROUP BY asset_id
            """),
            {"pid": str(portfolio_id)},
        )
        qty_lookup = {
            row.asset_id: float(row.net_quantity)
            for row in qty_rows
            if row.net_quantity is not None
        }

    enriched_items = []
    for asset in items:
        base = AssetRead.model_validate(asset)
        asset_id_str = str(asset.id)
        snap = snap_lookup.get(asset_id_str)
        enriched_items.append(AssetReadEnriched(
            **base.model_dump(),
            snapshot_current_value=float(snap.current_value) if snap and snap.current_value else None,
            snapshot_invested_capital=float(snap.invested_capital) if snap and snap.invested_capital else None,
            snapshot_total_return_pct=float(snap.total_return_pct) if snap and snap.total_return_pct else None,
            net_quantity=qty_lookup.get(asset_id_str),
        ))

    return AssetListResponseEnriched(
        items=enriched_items,
        total=total,
        page=page,
        limit=limit,
        pages=max(1, -(-total // limit)),
    )


@router.post("/", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = payload.model_dump()
    if data.get("portfolio_id"):
        await verify_portfolio_access(db, data["portfolio_id"], current_user["user_id"], current_user.get("org_id"))
    # Map extra_data → metadata column via model attribute name
    if "extra_data" in data:
        data["extra_data"] = data.pop("extra_data")
    asset = Asset(**data)
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.portfolio_id:
        await verify_portfolio_access(db, asset.portfolio_id, current_user["user_id"], current_user.get("org_id"))
    return asset


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.portfolio_id:
        await verify_portfolio_access(db, asset.portfolio_id, current_user["user_id"], current_user.get("org_id"))
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.portfolio_id:
        await verify_portfolio_access(db, asset.portfolio_id, current_user["user_id"], current_user.get("org_id"))

    # Block delete if transactions exist
    count_q = select(func.count(Transaction.id)).where(Transaction.asset_id == asset_id)
    txn_count = (await db.execute(count_q)).scalar_one()
    if txn_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete — this asset has {txn_count} transaction{'s' if txn_count != 1 else ''}. Remove them first.",
        )

    await db.delete(asset)
