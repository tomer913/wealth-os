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
    model_config = {"from_attributes": True}


# Paginated response wrapper
class AssetListResponse(BaseModel):
    items: List[AssetRead]
    total: int
    page: int
    limit: int
    pages: int
