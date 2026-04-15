"""
Budget layer models.

budget_categories     — hierarchical category tree (user-defined)
budget_plans          — annual plan per category
budget_actuals        — auto-populated monthly actuals by BudgetProcessor
budget_category_rules — classification rules evaluated in priority order
classification_log    — every classification decision logged
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer,
    Numeric, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.raw_layer import RawTransaction


class BudgetCategory(Base):
    __tablename__ = "budget_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # expense | income | saving | investment
    category_type: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
    children: Mapped[List["BudgetCategory"]] = relationship(
        "BudgetCategory", foreign_keys=[parent_id], back_populates="parent",
    )
    parent: Mapped[Optional["BudgetCategory"]] = relationship(
        "BudgetCategory", foreign_keys=[parent_id], back_populates="children",
        remote_side=[id],
    )
    plans: Mapped[List["BudgetPlan"]] = relationship(
        "BudgetPlan", back_populates="category", cascade="all, delete-orphan",
    )
    actuals: Mapped[List["BudgetActual"]] = relationship(
        "BudgetActual", back_populates="category", cascade="all, delete-orphan",
    )
    rules: Mapped[List["BudgetCategoryRule"]] = relationship(
        "BudgetCategoryRule", back_populates="category", cascade="all, delete-orphan",
    )


class BudgetPlan(Base):
    __tablename__ = "budget_plans"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "category_id", "year",
                         name="uq_budget_plans_category_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    # fixed_monthly | annual_pool | one_time
    plan_type: Mapped[str] = mapped_column(Text, nullable=False, default="fixed_monthly")
    monthly_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    annual_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    # {"3": 25000, "12": 30000} — month number → override amount
    monthly_overrides: Mapped[Optional[Dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    budget_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="ראשי")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
    category: Mapped["BudgetCategory"] = relationship("BudgetCategory", back_populates="plans")


class BudgetActual(Base):
    __tablename__ = "budget_actuals"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "category_id", "year", "month",
                         name="uq_budget_actuals_category_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
    category: Mapped["BudgetCategory"] = relationship("BudgetCategory", back_populates="actuals")
    actual_transactions: Mapped[List["BudgetActualTransaction"]] = relationship(
        "BudgetActualTransaction", back_populates="budget_actual", cascade="all, delete-orphan",
    )


class BudgetCategoryRule(Base):
    __tablename__ = "budget_category_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    # suggested | active | inactive | conflict | deleted
    status: Mapped[str] = mapped_column(Text, default="suggested")
    # {"operator": "AND", "rules": [...]}
    conditions: Mapped[Dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # manual | ai_generated | user_confirmed
    source: Mapped[str] = mapped_column(Text, default="manual")
    ai_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    last_matched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    portfolio: Mapped["Portfolio"] = relationship("Portfolio")
    category: Mapped["BudgetCategory"] = relationship("BudgetCategory", back_populates="rules")


class ClassificationLog(Base):
    __tablename__ = "classification_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    raw_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_transactions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_category_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    # rule | ai | manual | unclassified
    method: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    ai_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )
    # Set ONLY by human manual review — engine never overwrites this.
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Set on every engine run (first classification or rerun) — human review never sets this.
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    raw_transaction: Mapped["RawTransaction"] = relationship("RawTransaction")
    category: Mapped[Optional["BudgetCategory"]] = relationship("BudgetCategory")
    rule: Mapped[Optional["BudgetCategoryRule"]] = relationship("BudgetCategoryRule")


class BudgetActualTransaction(Base):
    """
    Idempotent junction between raw_transactions and budget_actuals.
    PK = raw_transaction_id — exactly one row per raw transaction.
    Upsert replaces the previous categorization; recalculate budget_actuals after.
    """
    __tablename__ = "budget_actual_transactions"

    raw_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_transactions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    budget_actual_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_actuals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    categorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    raw_transaction: Mapped["RawTransaction"] = relationship("RawTransaction")
    budget_actual: Mapped["BudgetActual"] = relationship(
        "BudgetActual", back_populates="actual_transactions",
    )
