from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.valuation import ManualValuation
from app.schemas.valuation import ManualValuationCreate, ManualValuationRead, ManualValuationUpdate

router = APIRouter(prefix="/valuations", tags=["valuations"])


@router.get("/", response_model=List[ManualValuationRead])
async def list_valuations(
    asset_id: Optional[UUID] = Query(None),
    portfolio_id: Optional[UUID] = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(ManualValuation)
    if asset_id:
        q = q.where(ManualValuation.asset_id == asset_id)
    if portfolio_id:
        q = q.where(ManualValuation.portfolio_id == portfolio_id)
    q = q.order_by(ManualValuation.date.desc()).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=ManualValuationRead, status_code=status.HTTP_201_CREATED)
async def create_valuation(payload: ManualValuationCreate, db: AsyncSession = Depends(get_db)):
    valuation = ManualValuation(**payload.model_dump())
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
