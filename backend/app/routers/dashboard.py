"""
routers/dashboard.py

GET /dashboard/{portfolio_id}

Returns the latest performance snapshot aggregated across all assets,
filtered by the requested view. Full implementation wired in Phase 3.

Dashboard filter views (from CLAUDE.md):
  full           – All active assets
  ex_real_estate – category != real_estate
  liquid         – account.is_liquid = true
  income         – account.is_income_generating = true
  funds          – asset_behavior = FUND
  alternatives   – category = alternatives
"""
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.snapshot import PerformanceSnapshot
from app.models.account import Account
from app.models.asset import Asset
from app.schemas.snapshot import PerformanceSnapshotRead
from app.utils.enums import AssetBehavior, AssetCategory

DashboardView = Literal[
    "full", "ex_real_estate", "liquid", "income", "funds", "alternatives"
]

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/{portfolio_id}", response_model=List[PerformanceSnapshotRead])
async def get_dashboard(
    portfolio_id: UUID,
    view: DashboardView = Query("full", description="Dashboard filter view"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the latest performance snapshot per asset for the given portfolio,
    applying the requested dashboard filter view.
    """
    # Base: latest snapshot per asset for this portfolio
    q = (
        select(PerformanceSnapshot)
        .join(Asset, PerformanceSnapshot.asset_id == Asset.id)
        .where(PerformanceSnapshot.portfolio_id == portfolio_id)
        .where(Asset.status == "active")
        .where(PerformanceSnapshot.is_stale == False)  # noqa: E712
    )

    if view == "ex_real_estate":
        q = q.where(Asset.category != AssetCategory.REAL_ESTATE.value)

    elif view == "liquid":
        q = (
            q.join(Account, PerformanceSnapshot.account_id == Account.id)
            .where(Account.is_liquid == True)  # noqa: E712
        )

    elif view == "income":
        q = (
            q.join(Account, PerformanceSnapshot.account_id == Account.id)
            .where(Account.is_income_generating == True)  # noqa: E712
        )

    elif view == "funds":
        q = q.where(Asset.asset_behavior == AssetBehavior.FUND.value)

    elif view == "alternatives":
        q = q.where(Asset.category == AssetCategory.ALTERNATIVES.value)

    # "full" – no additional filter

    q = q.order_by(PerformanceSnapshot.snapshot_date.desc())
    result = await db.execute(q)
    return result.scalars().all()
