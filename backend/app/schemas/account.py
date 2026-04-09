from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from app.utils.enums import AccountStatus, AccountType, AssetCategory
from pydantic import BaseModel, Field


class AccountBase(BaseModel):
    name: str = Field(..., max_length=200)
    symbol: str = Field(..., max_length=100)
    account_type: Optional[AccountType] = None
    category: Optional[AssetCategory] = None
    currency: str = Field("ILS", max_length=10)
    institution: Optional[str] = None
    custodian: Optional[str] = None
    is_liquid: bool = False
    is_income_generating: bool = False
    include_in_portfolio: bool = True
    status: AccountStatus = AccountStatus.ACTIVE
    cash_balance: Decimal = Decimal("0")
    opening_balance: Optional[Decimal] = None
    extra_data: Optional[Dict[str, Any]] = Field(None, alias="metadata")
    notes: Optional[str] = None
    model_config = {"from_attributes": True, "populate_by_name": True}


class AccountCreate(AccountBase):
    portfolio_id: UUID


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    custodian: Optional[str] = None
    is_liquid: Optional[bool] = None
    is_income_generating: Optional[bool] = None
    include_in_portfolio: Optional[bool] = None
    status: Optional[AccountStatus] = None
    cash_balance: Optional[Decimal] = None
    extra_data: Optional[Dict[str, Any]] = Field(None, alias="metadata")
    notes: Optional[str] = None
    


class AccountRead(AccountBase):
    id: UUID
    portfolio_id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True, "populate_by_name": True}
  


# Extends AccountRead with server-computed position count
class AccountReadWithCount(AccountRead):
    position_count: int = 0
