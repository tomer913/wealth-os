"""
Raw data layer models.

raw_transactions  — immutable append-only log written by connectors
service_checkpoints — consumer offset per processor per portfolio
processor_runs    — audit log for processor executions
"""
import uuid
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio


class RawTransaction(Base):
    """
    Immutable append-only record written by connectors.
    UUID v7 PK gives time-ordering and acts as a consumer cursor.
    """
    __tablename__ = "raw_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        # Default set in Python, not server_default, so we can use uuid7()
        default=uuid.uuid4,  # overridden at insert time by connector base
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    # Raw transaction data
    raw_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source-specific fields (op_type, category codes, etc.)
    extra_raw: Mapped[Optional[Dict]] = mapped_column(JSONB, nullable=True)

    # Dedup key — unique per source
    external_ref_id: Mapped[str] = mapped_column(Text, nullable=False)

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("source", "external_ref_id", name="uq_raw_transactions_source_ref"),
        Index("ix_raw_transactions_cursor", "portfolio_id", "source", "id"),
    )

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")


class ServiceCheckpoint(Base):
    """
    Consumer offset per processor per portfolio.
    last_raw_id = NULL means replay from beginning.
    """
    __tablename__ = "service_checkpoints"

    service_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Last UUID v7 successfully processed (NULL = start from beginning)
    last_raw_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")


class ProcessorRun(Base):
    """Audit log for each processor execution."""
    __tablename__ = "processor_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    processor_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # pending | running | success | failed | partial
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # scheduler | manual | api
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduler")

    # Checkpoint window processed in this run
    checkpoint_from: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    checkpoint_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Counts
    rows_read: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rows_written: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rows_skipped: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Error details
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Date range for reruns (NULL = checkpoint-based run)
    date_from: Mapped[Optional[date_type]] = mapped_column(Date(), nullable=True)
    date_to: Mapped[Optional[date_type]] = mapped_column(Date(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
