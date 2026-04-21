import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.asset import Asset
    from app.models.transaction import Transaction
    from app.models.snapshot import PerformanceSnapshot


class Portfolio(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "portfolios"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ILS")
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[Optional[str]] = mapped_column(String(100))  # Clerk user_id
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── Relationships ──────────────────────────────────────────────────────────
    accounts: Mapped[List["Account"]] = relationship(
        "Account", back_populates="portfolio", cascade="all, delete-orphan"
    )
    assets: Mapped[List["Asset"]] = relationship(
        "Asset", back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="portfolio", cascade="all, delete-orphan"
    )
    snapshots: Mapped[List["PerformanceSnapshot"]] = relationship(
        "PerformanceSnapshot", back_populates="portfolio", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Portfolio id={self.id} name={self.name!r}>"
