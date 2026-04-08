import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.account import Account
    from app.models.asset import Asset


class Transaction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transactions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), index=True,
    )
    asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), index=True,
    )

    transaction_date: Mapped[date_type] = mapped_column("date", Date, nullable=False, index=True)
    effective_date: Mapped[Optional[date_type]] = mapped_column(Date)

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    economic_type: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(50))
    subtype: Mapped[Optional[str]] = mapped_column(String(100))

    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    cashflow_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ILS")
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)

    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8))
    price_per_unit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    units_delta: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0)

    from_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id")
    )
    to_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id")
    )
    is_internal_transfer: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    source: Mapped[str] = mapped_column(String(50), default="manual")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    external_reference_id: Mapped[Optional[str]] = mapped_column(String(200))

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="transactions")
    account: Mapped[Optional["Account"]] = relationship(
        "Account", foreign_keys=[account_id], back_populates="transactions",
    )
    asset: Mapped[Optional["Asset"]] = relationship("Asset", back_populates="transactions")
    from_account: Mapped[Optional["Account"]] = relationship("Account", foreign_keys=[from_account_id])
    to_account: Mapped[Optional["Account"]] = relationship("Account", foreign_keys=[to_account_id])
