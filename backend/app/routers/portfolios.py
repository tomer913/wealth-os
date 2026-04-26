import logging
import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.portfolio import Portfolio
from app.models.portfolio_member import PortfolioMember
from app.schemas.portfolio import (
    PendingInvitationRead,
    PortfolioCreate, PortfolioRead, PortfolioUpdate,
    PortfolioMemberInvite, PortfolioMemberRead, PortfolioMemberUpdate,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("/", response_model=List[PortfolioRead])
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return portfolios where the current user is an accepted member."""
    from app.auth import CLERK_JWKS_URL
    if not CLERK_JWKS_URL:
        result = await db.execute(select(Portfolio).order_by(Portfolio.created_at))
        return result.scalars().all()

    result = await db.execute(
        select(Portfolio)
        .join(PortfolioMember, PortfolioMember.portfolio_id == Portfolio.id)
        .where(
            PortfolioMember.user_id == current_user["user_id"],
            PortfolioMember.accepted_at.isnot(None),
        )
        .order_by(Portfolio.created_at)
    )
    return result.scalars().all()


@router.get("/pending-invitations/", response_model=List[PendingInvitationRead])
async def list_pending_invitations(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return pending (unaccepted) portfolio invitations for the current user."""
    from app.auth import CLERK_JWKS_URL
    if not CLERK_JWKS_URL:
        return []

    rows = (await db.execute(
        select(PortfolioMember, Portfolio.name.label("portfolio_name"))
        .join(Portfolio, Portfolio.id == PortfolioMember.portfolio_id)
        .where(
            PortfolioMember.user_id == current_user["user_id"],
            PortfolioMember.accepted_at.is_(None),
            PortfolioMember.role != "owner",
        )
    )).all()

    return [
        PendingInvitationRead(
            member_id=row.PortfolioMember.id,
            portfolio_id=row.PortfolioMember.portfolio_id,
            portfolio_name=row.portfolio_name,
            role=row.PortfolioMember.role,
            invited_by=row.PortfolioMember.invited_by,
            created_at=row.PortfolioMember.created_at,
        )
        for row in rows
    ]


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

    if data.get("owner_id"):
        member = PortfolioMember(
            portfolio_id=portfolio.id,
            user_id=data["owner_id"],
            role="owner",
            accepted_at=datetime.now(timezone.utc),
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
        db, portfolio_id, current_user["user_id"], current_user.get("org_id"),
        required_role="owner",
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
    from app.models.transaction import Transaction

    portfolio = await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id"),
        required_role="owner",
    )

    txn_count = (await db.execute(
        select(func.count()).select_from(Transaction).where(
            Transaction.portfolio_id == portfolio_id
        )
    )).scalar() or 0

    if txn_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Portfolio has {txn_count} transactions. Remove all data before deleting.",
        )

    await db.delete(portfolio)


# ── Member management ──────────────────────────────────────────────────────────

@router.get("/{portfolio_id}/members/", response_model=List[PortfolioMemberRead])
async def list_members(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await verify_portfolio_access(
        db, portfolio_id, current_user["user_id"], current_user.get("org_id")
    )
    members = (await db.execute(
        select(PortfolioMember).where(PortfolioMember.portfolio_id == portfolio_id)
        .order_by(PortfolioMember.created_at)
    )).scalars().all()
    return members


@router.post("/{portfolio_id}/members/", response_model=PortfolioMemberRead, status_code=status.HTTP_201_CREATED)
async def invite_member(
    portfolio_id: UUID,
    payload: PortfolioMemberInvite,
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
            PortfolioMember.email == payload.email,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email has already been invited",
        )

    # Best-effort Clerk user lookup by email
    user_id: Optional[str] = None
    clerk_secret = os.getenv("CLERK_SECRET_KEY")
    if clerk_secret:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.clerk.com/v1/users",
                    params={"email_address[]": payload.email, "limit": 1},
                    headers={"Authorization": f"Bearer {clerk_secret}"},
                )
                if resp.status_code == 200:
                    users = resp.json()
                    if users:
                        user_id = users[0]["id"]
        except Exception as exc:
            log.warning("Clerk user lookup failed for %s: %s", payload.email, exc)

    if user_id:
        dupe = (await db.execute(
            select(PortfolioMember).where(
                PortfolioMember.portfolio_id == portfolio_id,
                PortfolioMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        if dupe:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member",
            )

    member = PortfolioMember(
        portfolio_id=portfolio_id,
        user_id=user_id,
        email=payload.email,
        role=payload.role,
        invited_by=current_user["user_id"],
        accepted_at=None,
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


@router.patch("/{portfolio_id}/members/{member_id}", response_model=PortfolioMemberRead)
async def update_member(
    portfolio_id: UUID,
    member_id: UUID,
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
            PortfolioMember.id == member_id,
        )
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.user_id == current_user["user_id"] and member.role == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot change their own role")
    if payload.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot promote to owner")
    member.role = payload.role
    await db.flush()
    await db.refresh(member)
    return member


@router.delete("/{portfolio_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    portfolio_id: UUID,
    member_id: UUID,
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
            PortfolioMember.id == member_id,
        )
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.user_id == current_user["user_id"] and member.role == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot remove themselves")
    await db.delete(member)


@router.post("/{portfolio_id}/members/accept/", response_model=PortfolioMemberRead)
async def accept_invitation(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    member = (await db.execute(
        select(PortfolioMember).where(
            PortfolioMember.portfolio_id == portfolio_id,
            PortfolioMember.user_id == current_user["user_id"],
            PortfolioMember.accepted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    member.accepted_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(member)
    return member
