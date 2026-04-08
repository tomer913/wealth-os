import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.asset import Asset
    from app.models.transaction import Transaction
    from app.models.valuation import ManualValuation
    from app.models.snapshot import PerformanceSnapshot
    from app.models.position import Position


class Account(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", name="uq_account_symbol"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identity ───────────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    symbol: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # ── Classification ─────────────────────────────────────────────────────────
    account_type: Mapped[Optional[str]] = mapped_column(String(50))
    # brokerage | pension_account | real_estate_account | alternative_account | cash

    category: Mapped[Optional[str]] = mapped_column(String(50))
    # securities | real_estate | pension | alternatives | cash

    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ILS")

    # ── Institution ────────────────────────────────────────────────────────────
    institution: Mapped[Optional[str]] = mapped_column(String(200))
    custodian: Mapped[Optional[str]] = mapped_column(String(200))

    # ── Flags (promoted from metadata – used for dashboard filters) ────────────
    is_liquid: Mapped[bool] = mapped_column(Boolean, default=False)
    is_income_generating: Mapped[bool] = mapped_column(Boolean, default=False)
    include_in_portfolio: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── State ──────────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active | inactive | archived

    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    opening_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))

    # ── Extensible ─────────────────────────────────────────────────────────────
    extra_data: Mapped[Optional[Dict]] = mapped_column("metadata", JSONB)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ── Relationships ──────────────────────────────────────────────────────────
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="accounts")

    assets: Mapped[List["Asset"]] = relationship("Asset", back_populates="account")

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        foreign_keys="Transaction.account_id",
        back_populates="account",
    )
    valuations: Mapped[List["ManualValuation"]] = relationship(
        "ManualValuation", back_populates="account"
    )
    snapshots: Mapped[List["PerformanceSnapshot"]] = relationship(
        "PerformanceSnapshot", back_populates="account"
    )
    positions: Mapped[List["Position"]] = relationship("Position", back_populates="account")

    def __repr__(self) -> str:
        return f"<Account id={self.id} symbol={self.symbol!r}>"
