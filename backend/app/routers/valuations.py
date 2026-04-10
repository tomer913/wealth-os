from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.valuation import ManualValuation
from app.schemas.valuation import (
    ManualValuationCreate,
    ManualValuationListResponse,
    ManualValuationRead,
    ManualValuationUpdate,
)

router = APIRouter(prefix="/valuations", tags=["valuations"])


@router.get("/", response_model=ManualValuationListResponse)
async def list_valuations(
    portfolio_id: Optional[UUID] = Query(None),
    asset_id: Optional[UUID] = Query(None),
    account_id: Optional[UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(ManualValuation)
    if portfolio_id:
        q = q.where(ManualValuation.portfolio_id == portfolio_id)
    if asset_id:
        q = q.where(ManualValuation.asset_id == asset_id)
    if account_id:
        q = q.where(ManualValuation.account_id == account_id)
    if date_from:
        q = q.where(ManualValuation.valuation_date >= date_from)
    if date_to:
        q = q.where(ManualValuation.valuation_date <= date_to)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * limit
    q = q.order_by(ManualValuation.valuation_date.desc()).offset(offset).limit(limit)
    items = (await db.execute(q)).scalars().all()

    return ManualValuationListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=max(1, -(-total // limit)),
    )


@router.post("/", response_model=ManualValuationRead, status_code=status.HTTP_201_CREATED)
async def create_valuation(payload: ManualValuationCreate, db: AsyncSession = Depends(get_db)):
    data = payload.model_dump(by_alias=False)
    valuation = ManualValuation(**data)
    db.add(valuation)
    await db.flush()
    await db.refresh(valuation)
    return valuation


@router.get("/{valuation_id}", response_model=ManualValuationRead)
async def get_valuation(valuation_id: UUID, db: AsyncSession = Depends(get_db)):
    v = await db.get(ManualValuation, valuation_id)
    if not v:
        raise HTTPException(status_code=404, detail="Valuation not found")
    return v


@router.patch("/{valuation_id}", response_model=ManualValuationRead)
async def update_valuation(
    valuation_id: UUID,
    payload: ManualValuationUpdate,
    db: AsyncSession = Depends(get_db),
):
    v = await db.get(ManualValuation, valuation_id)
    if not v:
        raise HTTPException(status_code=404, detail="Valuation not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(v, field, value)
    await db.flush()
    await db.refresh(v)
    return v


@router.delete("/{valuation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_valuation(valuation_id: UUID, db: AsyncSession = Depends(get_db)):
    v = await db.get(ManualValuation, valuation_id)
    if not v:
        raise HTTPException(status_code=404, detail="Valuation not found")
    await db.delete(v)
