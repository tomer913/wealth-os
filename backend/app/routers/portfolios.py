from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.portfolio import Portfolio
from app.models.portfolio_member import PortfolioMember
from app.schemas.portfolio import (
    PortfolioCreate, PortfolioRead, PortfolioUpdate,
    PortfolioMemberCreate, PortfolioMemberRead, PortfolioMemberUpdate,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("/", response_model=List[PortfolioRead])
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return portfolios owned by the current user (or dev bypass: all portfolios)."""
    from app.auth import CLERK_JWKS_URL
    q = select(Portfolio).order_by(Portfolio.created_at)
    if CLERK_JWKS_URL:
        q = q.where(Portfolio.owner_id == current_user["user_id"])
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: PortfolioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = payload.model_dump()
    from app.auth import CLERK_JWKS_URL
    if CLERK_JWKS_URL and not data.get("owner_id"):
        data["owner_id"] = current_user["user_id"]
    portfolio = Portfolio(**data)
    db.add(portfolio)
    await db.flush()

    # Auto-insert owner into portfolio_members
    if data.get("owner_id"):
        member = PortfolioMember(
            portfolio_id=portfolio.id,
            user_id=data["owner_id"],
            role="owner",
        )
        db.add(member)
        await db.flush()

    await db.refresh(portfolio)
    return portfolio


@router.get("/{portfolio_id}", response_model=PortfolioRead)
async def get_portfolio(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id")
    )


@router.patch("/{portfolio_id}", response_model=PortfolioRead)
async def update_portfolio(
    portfolio_id: UUID,
    payload: PortfolioUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    portfolio = await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id")
    )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(portfolio, field, value)
    await db.flush()
    await db.refresh(portfolio)
    return portfolio


@router.patch("/{portfolio_id}/select", response_model=PortfolioRead)
async def select_portfolio(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark portfolio as last accessed (for session restore on next login)."""
    portfolio = await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id")
    )
    portfolio.last_accessed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(portfolio)
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    portfolio = await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id"),
        required_role="owner",
    )
    await db.delete(portfolio)


# ── Member management ─────────────────────────────────────────────────────────

@router.get("/{portfolio_id}/members/", response_model=List[PortfolioMemberRead])
async def list_members(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    members = (await db.execute(
        select(PortfolioMember).where(PortfolioMember.portfolio_id == portfolio_id)
    )).scalars().all()
    return members


@router.post("/{portfolio_id}/members/", response_model=PortfolioMemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    portfolio_id: UUID,
    payload: PortfolioMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id"),
        required_role="owner",
    )
    existing = (await db.execute(
        select(PortfolioMember).where(
            PortfolioMember.portfolio_id == portfolio_id,
            PortfolioMember.user_id == payload.user_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")
    member = PortfolioMember(
        portfolio_id=portfolio_id,
        user_id=payload.user_id,
        role=payload.role,
        invited_by=current_user["user_id"],
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


@router.patch("/{portfolio_id}/members/{member_user_id}", response_model=PortfolioMemberRead)
async def update_member(
    portfolio_id: UUID,
    member_user_id: str,
    payload: PortfolioMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id"),
        required_role="owner",
    )
    member = (await db.execute(
        select(PortfolioMember).where(
            PortfolioMember.portfolio_id == portfolio_id,
            PortfolioMember.user_id == member_user_id,
        )
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.user_id == current_user["user_id"] and member.role == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot change their own role")
    member.role = payload.role
    await db.flush()
    await db.refresh(member)
    return member


@router.delete("/{portfolio_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    portfolio_id: UUID,
    member_user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id"),
        required_role="owner",
    )
    member = (await db.execute(
        select(PortfolioMember).where(
            PortfolioMember.portfolio_id == portfolio_id,
            PortfolioMember.user_id == member_user_id,
        )
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Owner cannot remove themselves")
    await db.delete(member)
