from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from app.utils.enums import ConfidenceLevel, ValuationMethod


class ManualValuationBase(BaseModel):
    valuation_date: date = Field(..., alias="date")
    market_value: Decimal
    currency: str = Field("ILS", max_length=10)
    fx_rate_to_ils: Decimal = Decimal("1.0")
    value_ils: Optional[Decimal] = None
    valuation_method: str = "manual"
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    valuation_source: Optional[str] = Field(None, max_length=100)
    is_estimated: bool = False
    notes: Optional[str] = None
    source: str = Field("manual", max_length=50)

    model_config = {"from_attributes": True, "populate_by_name": True}

    @model_validator(mode="after")
    def compute_value_ils(self) -> "ManualValuationBase":
        if self.value_ils is None and self.market_value and self.fx_rate_to_ils:
            self.value_ils = self.market_value * self.fx_rate_to_ils
        return self


class ManualValuationCreate(ManualValuationBase):
    portfolio_id: UUID
    asset_id: UUID
    account_id: Optional[UUID] = None


class ManualValuationUpdate(BaseModel):
    date: Optional[date] = None
    market_value: Optional[Decimal] = None
    fx_rate_to_ils: Optional[Decimal] = None
    value_ils: Optional[Decimal] = None
    valuation_method: Optional[str] = None
    confidence_level: Optional[ConfidenceLevel] = None
    valuation_source: Optional[str] = None
    is_estimated: Optional[bool] = None
    notes: Optional[str] = None


class ManualValuationRead(ManualValuationBase):
    id: UUID
    portfolio_id: UUID
    asset_id: UUID
    account_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class ManualValuationListResponse(BaseModel):
    items: List[ManualValuationRead]
    total: int
    page: int
    limit: int
    pages: int
