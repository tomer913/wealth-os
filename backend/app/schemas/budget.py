"""Budget layer Pydantic schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── BudgetCategory ─────────────────────────────────────────────────────────────

class BudgetCategoryBase(BaseModel):
    name: str
    name_en: Optional[str] = None
    category_type: str  # expense | income | saving | investment
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0
    parent_id: Optional[UUID] = None
    is_active: bool = True


class BudgetCategoryCreate(BudgetCategoryBase):
    pass


class BudgetCategoryUpdate(BaseModel):
    name: Optional[str] = None
    name_en: Optional[str] = None
    category_type: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    parent_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class BudgetCategoryRead(BudgetCategoryBase):
    id: UUID
    portfolio_id: UUID
    created_at: datetime
    children: List["BudgetCategoryRead"] = []

    model_config = {"from_attributes": True}


BudgetCategoryRead.model_rebuild()


# ── BudgetPlan ─────────────────────────────────────────────────────────────────

class BudgetPlanBase(BaseModel):
    category_id: UUID
    year: int
    plan_type: str = "fixed_monthly"  # fixed_monthly | annual_pool | one_time
    monthly_amount: Optional[Decimal] = None
    annual_amount: Optional[Decimal] = None
    monthly_overrides: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    budget_name: Optional[str] = "ראשי"


class BudgetPlanCreate(BudgetPlanBase):
    pass


class BudgetPlanUpdate(BaseModel):
    plan_type: Optional[str] = None
    monthly_amount: Optional[Decimal] = None
    annual_amount: Optional[Decimal] = None
    monthly_overrides: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    budget_name: Optional[str] = None


class BudgetPlanRead(BudgetPlanBase):
    id: UUID
    portfolio_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── BudgetActual ───────────────────────────────────────────────────────────────

class BudgetActualRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    category_id: UUID
    year: int
    month: int
    actual_amount: Decimal
    transaction_count: int
    last_updated: datetime

    model_config = {"from_attributes": True}


# ── BudgetCategoryRule ─────────────────────────────────────────────────────────

class BudgetRuleBase(BaseModel):
    category_id: UUID
    name: str
    priority: int = 100
    status: str = "suggested"
    conditions: Dict[str, Any]
    confidence: float = 1.0
    source: str = "manual"
    ai_reasoning: Optional[str] = None


class BudgetRuleCreate(BudgetRuleBase):
    pass


class BudgetRuleUpdate(BaseModel):
    category_id: Optional[UUID] = None
    name: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None


class BudgetRuleRead(BudgetRuleBase):
    id: UUID
    portfolio_id: UUID
    match_count: int
    last_matched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    category_name: Optional[str] = None  # denormalized for UI

    model_config = {"from_attributes": True}


class BudgetRuleTestResult(BaseModel):
    count: int
    sample: List[Dict[str, Any]]  # up to 5 matching raw transactions


# ── ClassificationLog ──────────────────────────────────────────────────────────

class ClassificationLogRead(BaseModel):
    id: UUID
    raw_transaction_id: UUID
    category_id: Optional[UUID] = None
    rule_id: Optional[UUID] = None
    method: str
    confidence: float
    ai_model: Optional[str] = None
    ai_prompt_tokens: Optional[int] = None
    ai_completion_tokens: Optional[int] = None
    needs_review: bool
    excluded: bool = False
    reviewed_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    created_at: datetime
    # Denormalized for UI
    raw_description: Optional[str] = None
    raw_amount: Optional[Decimal] = None
    raw_date: Optional[datetime] = None
    raw_source: Optional[str] = None
    category_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Budget summary ─────────────────────────────────────────────────────────────

class BudgetSummaryRow(BaseModel):
    category_id: UUID
    category_name: str
    category_type: str
    plan_amount: Optional[Decimal] = None   # None if no plan defined
    actual_amount: Decimal = Decimal("0")
    variance: Optional[Decimal] = None     # plan - actual
    variance_pct: Optional[float] = None  # variance / plan
    transaction_count: int = 0
    has_override: bool = False             # True if monthly_overrides used this month
