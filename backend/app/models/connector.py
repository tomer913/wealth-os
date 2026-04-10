import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio


class Connector(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "connectors"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Encrypted config — API keys stored encrypted at app layer
    # Format: {"api_key": "enc:...", "api_secret": "enc:...", "since_timestamp": 0}
    config: Mapped[Dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Optional filter — null means fetch all symbols
    asset_filter: Mapped[Optional[Dict]] = mapped_column(JSONB, nullable=True)

    auto_create_assets: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule: Mapped[str] = mapped_column(String(50), default="daily")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
    runs: Mapped[List["ConnectorRun"]] = relationship(
        "ConnectorRun",
        back_populates="connector",
        order_by="desc(ConnectorRun.created_at)",
        cascade="all, delete-orphan",
    )


class ConnectorRun(Base):
    __tablename__ = "connector_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connectors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Execution status: pending | running | success | failed | partial
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # triggered_by: scheduler | manual | api
    triggered_by: Mapped[str] = mapped_column(String(20), default="scheduler")

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Results summary
    records_fetched: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transactions_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transactions_skipped: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valuations_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assets_created: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fx_rates_updated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prices_updated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Error details
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Resumable state — stores last processed offset/timestamp
    checkpoint: Mapped[Optional[Dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    connector: Mapped["Connector"] = relationship("Connector", back_populates="runs")
