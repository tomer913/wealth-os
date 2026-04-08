from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.asset import Asset
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate
from app.utils.enums import AssetBehavior, AssetCategory, AssetStatus

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/", response_model=List[AssetRead])
async def list_assets(
    portfolio_id: Optional[UUID] = Query(None),
    account_id: Optional[UUID] = Query(None),
    category: Optional[AssetCategory] = Query(None),
    asset_behavior: Optional[AssetBehavior] = Query(None),
    status: Optional[AssetStatus] = Query(None, description="Filter by lifecycle status"),
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
    result = await db.execute(q.order_by(Asset.name))
    return result.scalars().all()


@router.post("/", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(payload: AssetCreate, db: AsyncSession = Depends(get_db)):
    asset = Asset(**payload.model_dump())
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
    await db.delete(asset)
