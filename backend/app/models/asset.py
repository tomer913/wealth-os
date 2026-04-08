import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.account import Account
    from app.models.transaction import Transaction
    from app.models.valuation import ManualValuation
    from app.models.snapshot import PerformanceSnapshot
    from app.models.position import Position


class Asset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", name="uq_asset_symbol"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"),
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    symbol: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    asset_behavior: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    asset_type: Mapped[Optional[str]] = mapped_column(String(50))
    sub_type: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    lifecycle_stage: Mapped[str] = mapped_column(String(50), default="operational")
    exchange: Mapped[Optional[str]] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ILS")
    country: Mapped[Optional[str]] = mapped_column(String(100))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    price_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pricing_mode: Mapped[str] = mapped_column(String(50), default="manual_valuation")
    is_manual: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_data: Mapped[Optional[Dict]] = mapped_column("metadata", JSONB)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="assets")
    account: Mapped[Optional["Account"]] = relationship("Account", back_populates="assets")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="asset")
    valuations: Mapped[List["ManualValuation"]] = relationship(
        "ManualValuation", back_populates="asset", cascade="all, delete-orphan",
        order_by="desc(ManualValuation.valuation_date)",
    )
    snapshots: Mapped[List["PerformanceSnapshot"]] = relationship(
        "PerformanceSnapshot", back_populates="asset", cascade="all, delete-orphan"
    )
    position: Mapped[Optional["Position"]] = relationship(
        "Position", back_populates="asset", uselist=False
    )
