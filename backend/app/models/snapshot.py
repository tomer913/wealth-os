import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.account import Account
    from app.models.asset import Asset


class PerformanceSnapshot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "asset_id", "snapshot_date", name="uq_snapshot"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), index=True,
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"),
    )

    snapshot_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)

    invested_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    current_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(10), default="ILS")
    value_ils: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))

    total_return: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    total_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    annual_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    xirr_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))

    total_income: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    total_expenses: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    net_cashflow: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))

    model_used: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="snapshots")
    asset: Mapped[Optional["Asset"]] = relationship("Asset", back_populates="snapshots")
    account: Mapped[Optional["Account"]] = relationship("Account", back_populates="snapshots")
