from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

class PortfolioBase(BaseModel):
    name: str = Field(..., max_length=200)
    base_currency: str = Field("ILS", max_length=10)
    description: Optional[str] = None
    is_default: bool = False
    owner_id: Optional[str] = None

class PortfolioCreate(PortfolioBase):
    pass

class PortfolioUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    base_currency: Optional[str] = Field(None, max_length=10)
    description: Optional[str] = None
    is_default: Optional[bool] = None

class PortfolioRead(PortfolioBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
