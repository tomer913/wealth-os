from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from app.utils.enums import AssetBehavior, AssetCategory, AssetStatus, LifecycleStage, PricingMode


class AssetBase(BaseModel):
    name: str = Field(..., max_length=300)
    symbol: str = Field(..., max_length=100)
    asset_behavior: AssetBehavior
    category: Optional[AssetCategory] = None
    asset_type: Optional[str] = Field(None, max_length=50)
    sub_type: Optional[str] = Field(None, max_length=100)
    status: str = "active"
    lifecycle_stage: LifecycleStage = LifecycleStage.OPERATIONAL
    exchange: Optional[str] = Field(None, max_length=50)
    currency: str = Field("ILS", max_length=10)
    country: Optional[str] = Field(None, max_length=100)
    sector: Optional[str] = Field(None, max_length=100)
    current_price: Optional[Decimal] = None
    pricing_mode: PricingMode = PricingMode.MANUAL_VALUATION
    is_manual: bool = True
    extra_data: Optional[Dict[str, Any]] = None  # stored as "metadata" JSONB column


class AssetCreate(AssetBase):
    portfolio_id: UUID
    account_id: Optional[UUID] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    asset_behavior: Optional[AssetBehavior] = None
    category: Optional[AssetCategory] = None
    asset_type: Optional[str] = None
    sub_type: Optional[str] = None
    status: Optional[AssetStatus] = None
    lifecycle_stage: Optional[LifecycleStage] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    country: Optional[str] = None
    sector: Optional[str] = None
    current_price: Optional[Decimal] = None
    pricing_mode: Optional[PricingMode] = None
    is_manual: Optional[bool] = None
    account_id: Optional[UUID] = None
    extra_data: Optional[Dict[str, Any]] = None


class AssetRead(AssetBase):
    id: UUID
    portfolio_id: UUID
    account_id: Optional[UUID] = None
    price_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # Read schemas use str, not enums — DB may contain values added after enum was defined
    asset_behavior: Optional[str] = None
    category: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    pricing_mode: Optional[str] = None
    model_config = {"from_attributes": True, "populate_by_name": True}


class AssetReadEnriched(AssetRead):
    """AssetRead extended with latest snapshot values and computed net_quantity."""
    snapshot_current_value: Optional[float] = None     # latest snapshot current_value (ILS)
    snapshot_invested_capital: Optional[float] = None  # latest snapshot invested_capital (ILS)
    snapshot_total_return_pct: Optional[float] = None  # latest snapshot total_return_pct (0–1 scale)
    net_quantity: Optional[float] = None               # sum(buys) - sum(sells) from transactions


# Paginated response wrapper
class AssetListResponse(BaseModel):
    items: List[AssetRead]
    total: int
    page: int
    limit: int
    pages: int


class AssetListResponseEnriched(BaseModel):
    items: List[AssetReadEnriched]
    total: int
    page: int
    limit: int
    pages: int
