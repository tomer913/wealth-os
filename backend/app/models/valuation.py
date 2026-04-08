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


class ManualValuation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "manual_valuations"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"),
    )

    valuation_date: Mapped[date_type] = mapped_column("date", Date, nullable=False, index=True)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ILS")
    fx_rate_to_ils: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=1.0)
    value_ils: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))

    valuation_method: Mapped[str] = mapped_column(String(50), default="manual")
    confidence_level: Mapped[str] = mapped_column(String(20), default="medium")
    valuation_source: Mapped[Optional[str]] = mapped_column(String(100))
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="manual")

    asset: Mapped["Asset"] = relationship("Asset", back_populates="valuations")
    account: Mapped[Optional["Account"]] = relationship("Account", back_populates="valuations")
