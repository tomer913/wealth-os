from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PerformanceSnapshotRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    asset_id: Optional[UUID] = None
    account_id: Optional[UUID] = None
    snapshot_date: date

    # Capital & Value
    invested_capital: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    currency: str
    value_ils: Optional[Decimal] = None

    # Returns
    total_return: Optional[Decimal] = None
    total_return_pct: Optional[Decimal] = None
    annual_return_pct: Optional[Decimal] = None
    xirr_return_pct: Optional[Decimal] = None

    # Cashflow summary
    total_income: Optional[Decimal] = None
    total_expenses: Optional[Decimal] = None
    net_cashflow: Optional[Decimal] = None

    model_used: Optional[str] = None
    notes: Optional[str] = None
    is_stale: bool

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SnapshotRebuildRequest(BaseModel):
    portfolio_id: UUID
    asset_id: Optional[UUID] = None   # None = rebuild entire portfolio
    as_of_date: Optional[date] = None  # None = today
