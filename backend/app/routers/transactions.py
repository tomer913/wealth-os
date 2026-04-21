from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate
from app.utils.enums import EconomicType, TransactionStatus

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/", response_model=List[TransactionRead])
async def list_transactions(
    portfolio_id: Optional[UUID] = Query(None),
    asset_id: Optional[UUID] = Query(None),
    account_id: Optional[UUID] = Query(None),
    economic_type: Optional[EconomicType] = Query(None),
    status: Optional[TransactionStatus] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if portfolio_id:
        await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    q = select(Transaction)
    if portfolio_id:
        q = q.where(Transaction.portfolio_id == portfolio_id)
    if asset_id:
        q = q.where(Transaction.asset_id == asset_id)
    if account_id:
        q = q.where(Transaction.account_id == account_id)
    if economic_type:
        q = q.where(Transaction.economic_type == economic_type.value)
    if status:
        q = q.where(Transaction.status == status.value)
    if date_from:
        q = q.where(Transaction.transaction_date >= date_from)
    if date_to:
        q = q.where(Transaction.transaction_date <= date_to)
    q = q.order_by(Transaction.transaction_date.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = payload.model_dump()
    if data.get("portfolio_id"):
        await verify_portfolio_access(db, data["portfolio_id"], current_user["user_id"], current_user.get("org_id"))
    txn = Transaction(**data)
    db.add(txn)
    await db.flush()
    await db.refresh(txn)
    return txn


@router.get("/{transaction_id}", response_model=TransactionRead)
async def get_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    txn = await db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.portfolio_id:
        await verify_portfolio_access(db, txn.portfolio_id, current_user["user_id"], current_user.get("org_id"))
    return txn


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: UUID,
    payload: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    txn = await db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.portfolio_id:
        await verify_portfolio_access(db, txn.portfolio_id, current_user["user_id"], current_user.get("org_id"))
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(txn, field, value)
    await db.flush()
    await db.refresh(txn)
    return txn


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    txn = await db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.portfolio_id:
        await verify_portfolio_access(db, txn.portfolio_id, current_user["user_id"], current_user.get("org_id"))
    await db.delete(txn)
