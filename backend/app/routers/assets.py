from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.asset import Asset
from app.models.transaction import Transaction
from app.schemas.asset import AssetCreate, AssetListResponse, AssetRead, AssetUpdate
from app.utils.enums import AssetBehavior, AssetCategory, AssetStatus

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/", response_model=AssetListResponse)
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
):
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

    return AssetListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=max(1, -(-total // limit)),  # ceiling division
    )


@router.post("/", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(payload: AssetCreate, db: AsyncSession = Depends(get_db)):
    data = payload.model_dump()
    # Map extra_data → metadata column via model attribute name
    if "extra_data" in data:
        data["extra_data"] = data.pop("extra_data")
    asset = Asset(**data)
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(asset_id: UUID, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: UUID, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Block delete if transactions exist
    count_q = select(func.count(Transaction.id)).where(Transaction.asset_id == asset_id)
    txn_count = (await db.execute(count_q)).scalar_one()
    if txn_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete — this asset has {txn_count} transaction{'s' if txn_count != 1 else ''}. Remove them first.",
        )

    await db.delete(asset)
