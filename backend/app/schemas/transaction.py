from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from app.utils.enums import EconomicType, TransactionDomain, TransactionSource, TransactionStatus, TransactionType

class TransactionBase(BaseModel):
    date: date
    effective_date: Optional[date] = None
    type: TransactionType
    economic_type: Optional[EconomicType] = None
    domain: Optional[TransactionDomain] = None
    subtype: Optional[str] = Field(None, max_length=100)
    total_amount: Optional[Decimal] = None
    cashflow_amount: Optional[Decimal] = None
    currency: str = Field("ILS", max_length=10)
    fees: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    quantity: Optional[Decimal] = None
    price_per_unit: Optional[Decimal] = None
    units_delta: Decimal = Decimal("0")
    from_account_id: Optional[UUID] = None
    to_account_id: Optional[UUID] = None
    is_internal_transfer: bool = False
    status: TransactionStatus = TransactionStatus.CONFIRMED
    source: TransactionSource = TransactionSource.MANUAL
    notes: Optional[str] = None
    external_reference_id: Optional[str] = Field(None, max_length=200)

    @model_validator(mode="after")
    def validate_amounts(self) -> "TransactionBase":
        if self.total_amount is None and self.cashflow_amount is None:
            raise ValueError("At least one of total_amount or cashflow_amount must be provided")
        return self

class TransactionCreate(TransactionBase):
    portfolio_id: UUID
    account_id: Optional[UUID] = None
    asset_id: Optional[UUID] = None

class TransactionUpdate(BaseModel):
    date: Optional[date] = None
    effective_date: Optional[date] = None
    economic_type: Optional[EconomicType] = None
    domain: Optional[TransactionDomain] = None
    total_amount: Optional[Decimal] = None
    cashflow_amount: Optional[Decimal] = None
    fees: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    status: Optional[TransactionStatus] = None
    notes: Optional[str] = None

class TransactionRead(TransactionBase):
    id: UUID
    portfolio_id: UUID
    account_id: Optional[UUID] = None
    asset_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
