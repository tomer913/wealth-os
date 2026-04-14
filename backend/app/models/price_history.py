import uuid
from datetime import date as date_type, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class AssetPriceHistory(Base):
    """One closing price per asset per date per source."""
    __tablename__ = "asset_price_history"
    __table_args__ = (
        UniqueConstraint("asset_id", "price_date", "source", name="uq_asset_price_history"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    price_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=True)
    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
