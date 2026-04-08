from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/", response_model=List[AccountRead])
async def list_accounts(
    portfolio_id: Optional[UUID] = Query(None),
    is_liquid: Optional[bool] = Query(None),
    is_income_generating: Optional[bool] = Query(None),
    include_in_portfolio: Optional[bool] = Query(None, description="Filter by portfolio inclusion"),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Account)
    if portfolio_id:
        q = q.where(Account.portfolio_id == portfolio_id)
    if is_liquid is not None:
        q = q.where(Account.is_liquid == is_liquid)
    if is_income_generating is not None:
        q = q.where(Account.is_income_generating == is_income_generating)
    if include_in_portfolio is not None:
        q = q.where(Account.include_in_portfolio == include_in_portfolio)
    if status:
        q = q.where(Account.status == status)
    result = await db.execute(q.order_by(Account.name))
    return result.scalars().all()


@router.post("/", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(payload: AccountCreate, db: AsyncSession = Depends(get_db)):
    account = Account(**payload.model_dump())
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(account_id: UUID, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    db: AsyncSession = Depends(get_db),
):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.flush()
    await db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: UUID, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await db.delete(account)
