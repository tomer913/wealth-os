"""
Budget router — categories, plans, actuals, rules, review queue.
All endpoints require ?portfolio_id= query param.
"""
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.budget import (
    BudgetActual, BudgetActualTransaction, BudgetCategory, BudgetCategoryRule,
    BudgetPlan, ClassificationLog,
)
from app.models.raw_layer import RawTransaction
from app.schemas.budget import (
    BudgetActualRead, BudgetCategoryCreate, BudgetCategoryRead, BudgetCategoryUpdate,
    BudgetPlanCreate, BudgetPlanRead, BudgetPlanUpdate,
    BudgetRuleCreate, BudgetRuleRead, BudgetRuleTestResult, BudgetRuleUpdate,
    BudgetSummaryRow, ClassificationLogRead,
)

router = APIRouter(prefix="/budget", tags=["budget"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pid(portfolio_id: UUID = Query(...)) -> UUID:
    return portfolio_id


async def _verified_pid(
    portfolio_id: UUID = Depends(_pid),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UUID:
    """Query-param dependency: verifies portfolio access and returns portfolio_id."""
    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    return portfolio_id


async def _recalculate_budget_actual(
    db: AsyncSession,
    actual_id: UUID,
    now: datetime,
) -> None:
    """Recalculate budget_actuals row from the sum of its junction rows."""
    from sqlalchemy import func
    result = (await db.execute(
        select(
            func.sum(BudgetActualTransaction.amount).label("total"),
            func.count(BudgetActualTransaction.raw_transaction_id).label("cnt"),
        ).where(BudgetActualTransaction.budget_actual_id == actual_id)
    )).one()
    actual = await db.get(BudgetActual, actual_id)
    if actual:
        actual.actual_amount = result.total or Decimal(0)
        actual.transaction_count = result.cnt or 0
        actual.last_updated = now


def _build_tree(cats: list) -> list:
    """Build nested category tree from flat list."""
    by_id = {c.id: c for c in cats}
    roots = []
    children_map: dict = {c.id: [] for c in cats}
    for c in cats:
        if c.parent_id and c.parent_id in by_id:
            children_map[c.parent_id].append(c)
        else:
            roots.append(c)

    def to_read(c) -> BudgetCategoryRead:
        r = BudgetCategoryRead.model_validate(c)
        r.children = [to_read(ch) for ch in sorted(children_map[c.id], key=lambda x: x.sort_order)]
        return r

    return [to_read(r) for r in sorted(roots, key=lambda x: x.sort_order)]


# ── Categories ─────────────────────────────────────────────────────────────────

@router.get("/categories/")
async def list_categories(
    portfolio_id: UUID = Depends(_verified_pid),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Return category tree. If year is provided, embed the budget plan for that year
    inside each category as 'plan' so the manage page needs only one API call.
    """
    q = select(BudgetCategory).where(
        BudgetCategory.portfolio_id == portfolio_id,
    ).order_by(BudgetCategory.sort_order)
    cats = (await db.execute(q)).scalars().all()

    # Load plans for requested year (if any)
    plan_by_cat: dict = {}
    if year:
        plans_q = select(BudgetPlan).where(
            BudgetPlan.portfolio_id == portfolio_id,
            BudgetPlan.year == year,
        )
        for p in (await db.execute(plans_q)).scalars().all():
            plan_by_cat[p.category_id] = {
                "id": str(p.id),
                "portfolio_id": str(p.portfolio_id),
                "category_id": str(p.category_id),
                "year": p.year,
                "plan_type": p.plan_type,
                "monthly_amount": float(p.monthly_amount) if p.monthly_amount is not None else None,
                "annual_amount": float(p.annual_amount) if p.annual_amount is not None else None,
                "monthly_overrides": p.monthly_overrides,
                "notes": p.notes,
                "budget_name": p.budget_name,
                "created_at": p.created_at.isoformat() if getattr(p, "created_at", None) else None,
            }

    def _sort_key(x) -> int:
        # Guard against NULL sort_order in existing DB rows
        return x.sort_order if x.sort_order is not None else 0

    def to_dict(c) -> dict:
        children_sorted = sorted(
            [ch for ch in cats if ch.parent_id == c.id],
            key=_sort_key,
        )
        return {
            "id": str(c.id),
            "portfolio_id": str(c.portfolio_id),
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "name": c.name,
            "name_en": c.name_en,
            "category_type": c.category_type,
            "icon": c.icon,
            "color": c.color,
            "sort_order": c.sort_order if c.sort_order is not None else 0,
            "is_active": c.is_active if c.is_active is not None else True,
            "created_at": c.created_at.isoformat() if getattr(c, "created_at", None) else None,
            "plan": plan_by_cat.get(c.id),
            "children": [to_dict(ch) for ch in children_sorted],
        }

    roots = sorted([c for c in cats if not c.parent_id], key=_sort_key)
    return [to_dict(r) for r in roots]


@router.post("/categories/", response_model=BudgetCategoryRead,
             status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: BudgetCategoryCreate,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    cat = BudgetCategory(id=uuid.uuid4(), portfolio_id=portfolio_id, **payload.model_dump())
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    r = BudgetCategoryRead.model_validate(cat)
    r.children = []
    return r


@router.patch("/categories/{cat_id}/", response_model=BudgetCategoryRead)
async def update_category(
    cat_id: UUID,
    payload: BudgetCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cat = await db.get(BudgetCategory, cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    await db.flush()
    await db.refresh(cat)
    r = BudgetCategoryRead.model_validate(cat)
    r.children = []
    return r


@router.delete("/categories/{cat_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    cat_id: UUID,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from sqlalchemy import update as sa_update
    cat = await db.get(BudgetCategory, cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Count transactions classified to this category
    tx_count = (
        await db.execute(
            select(func.count()).select_from(ClassificationLog).where(ClassificationLog.category_id == cat_id)
        )
    ).scalar_one()

    if tx_count > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Category has {tx_count} classified transactions. Delete with force=true to unclassify them.",
        )

    if tx_count > 0 and force:
        # Unclassify affected transactions so they re-enter the review queue
        await db.execute(
            sa_update(ClassificationLog)
            .where(ClassificationLog.category_id == cat_id)
            .values(category_id=None, needs_review=True, reviewed_at=None)
        )

    cat.is_active = False
    await db.flush()


# ── Plans ──────────────────────────────────────────────────────────────────────

@router.get("/plans/", response_model=List[BudgetPlanRead])
async def list_plans(
    portfolio_id: UUID = Depends(_verified_pid),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(BudgetPlan).where(BudgetPlan.portfolio_id == portfolio_id)
    if year:
        q = q.where(BudgetPlan.year == year)
    plans = (await db.execute(q)).scalars().all()
    return plans


@router.post("/plans/", response_model=BudgetPlanRead, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: BudgetPlanCreate,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    plan = BudgetPlan(id=uuid.uuid4(), portfolio_id=portfolio_id, **payload.model_dump())
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    return plan


@router.patch("/plans/{plan_id}/", response_model=BudgetPlanRead)
async def update_plan(
    plan_id: UUID,
    payload: BudgetPlanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    plan = await db.get(BudgetPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    await db.flush()
    await db.refresh(plan)
    return plan


@router.delete("/plans/{plan_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    plan = await db.get(BudgetPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    await db.delete(plan)


@router.post("/plans/generate-from-history/")
async def generate_plans_from_history(
    body: dict,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate budget plans for target_year based on average actuals from recent months.
    Body: { "target_year": 2026, "source_months": 6 }
    """
    from datetime import date
    target_year = int(body.get("target_year", date.today().year))
    source_months = int(body.get("source_months", 6))

    # Determine date range for source data
    today = date.today()
    cutoff_year = today.year
    cutoff_month = today.month - source_months
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1

    # Load actuals in range
    actuals_q = select(BudgetActual).where(
        BudgetActual.portfolio_id == portfolio_id,
        (BudgetActual.year > cutoff_year) |
        ((BudgetActual.year == cutoff_year) & (BudgetActual.month >= cutoff_month)),
    )
    actuals = (await db.execute(actuals_q)).scalars().all()

    # Aggregate per category
    from collections import defaultdict
    totals: dict = defaultdict(Decimal)
    counts: dict = defaultdict(int)
    for a in actuals:
        totals[a.category_id] += a.actual_amount
        counts[a.category_id] += 1

    created = 0
    updated = 0
    for cat_id, total in totals.items():
        avg_monthly = total / counts[cat_id]
        # Upsert plan
        existing_q = select(BudgetPlan).where(
            BudgetPlan.portfolio_id == portfolio_id,
            BudgetPlan.category_id == cat_id,
            BudgetPlan.year == target_year,
        )
        existing = (await db.execute(existing_q)).scalar_one_or_none()
        if existing:
            existing.monthly_amount = avg_monthly
            existing.plan_type = "fixed_monthly"
            updated += 1
        else:
            plan = BudgetPlan(
                id=uuid.uuid4(),
                portfolio_id=portfolio_id,
                category_id=cat_id,
                year=target_year,
                plan_type="fixed_monthly",
                monthly_amount=avg_monthly,
            )
            db.add(plan)
            created += 1

    await db.flush()
    return {"status": "ok", "created": created, "updated": updated, "target_year": target_year}


@router.post("/plans/import-from-year/")
async def import_plans_from_year(
    body: dict,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    """
    Copy plans from source_year to target_year.
    Body: { "source_year": 2025, "target_year": 2026 }
    """
    source_year = int(body.get("source_year"))
    target_year = int(body.get("target_year"))

    source_q = select(BudgetPlan).where(
        BudgetPlan.portfolio_id == portfolio_id,
        BudgetPlan.year == source_year,
    )
    source_plans = (await db.execute(source_q)).scalars().all()

    created = 0
    updated = 0
    for sp in source_plans:
        existing_q = select(BudgetPlan).where(
            BudgetPlan.portfolio_id == portfolio_id,
            BudgetPlan.category_id == sp.category_id,
            BudgetPlan.year == target_year,
        )
        existing = (await db.execute(existing_q)).scalar_one_or_none()
        if existing:
            existing.plan_type = sp.plan_type
            existing.monthly_amount = sp.monthly_amount
            existing.annual_amount = sp.annual_amount
            existing.monthly_overrides = None  # Don't copy overrides
            updated += 1
        else:
            plan = BudgetPlan(
                id=uuid.uuid4(),
                portfolio_id=portfolio_id,
                category_id=sp.category_id,
                year=target_year,
                plan_type=sp.plan_type,
                monthly_amount=sp.monthly_amount,
                annual_amount=sp.annual_amount,
            )
            db.add(plan)
            created += 1

    await db.flush()
    return {"status": "ok", "created": created, "updated": updated,
            "source_year": source_year, "target_year": target_year}


# ── Summary ────────────────────────────────────────────────────────────────────

@router.get("/summary/")
async def get_summary(
    portfolio_id: UUID = Depends(_verified_pid),
    year: int = Query(...),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all categories that have either a plan or actuals for the given period.
    month=None → annual aggregate (sum all months, compare to full-year plan).
    month=N   → monthly view for that specific month.
    Returns plain dicts with float values (avoids Decimal-as-string serialization).
    """
    # Load plans for year
    plans_q = select(BudgetPlan).where(
        BudgetPlan.portfolio_id == portfolio_id,
        BudgetPlan.year == year,
    )
    plans = {p.category_id: p for p in (await db.execute(plans_q)).scalars().all()}

    if month is not None:
        # Monthly mode: load actuals for specific month
        actuals_q = select(BudgetActual).where(
            BudgetActual.portfolio_id == portfolio_id,
            BudgetActual.year == year,
            BudgetActual.month == month,
        )
        monthly_actuals = {a.category_id: a for a in (await db.execute(actuals_q)).scalars().all()}
        actual_amount_map: dict = {
            cid: (float(a.actual_amount), a.transaction_count)
            for cid, a in monthly_actuals.items()
        }
    else:
        # Annual mode: aggregate all months for this year
        agg_q = select(
            BudgetActual.category_id,
            func.sum(BudgetActual.actual_amount).label("total_amount"),
            func.sum(BudgetActual.transaction_count).label("total_tx"),
        ).where(
            BudgetActual.portfolio_id == portfolio_id,
            BudgetActual.year == year,
        ).group_by(BudgetActual.category_id)
        actual_amount_map = {}
        for row in (await db.execute(agg_q)).all():
            actual_amount_map[row.category_id] = (float(row.total_amount or 0), int(row.total_tx or 0))

    # Load categories that appear in either
    cat_ids = set(plans.keys()) | set(actual_amount_map.keys())
    if not cat_ids:
        return []

    cats_q = select(BudgetCategory).where(BudgetCategory.id.in_(cat_ids))
    cats = {c.id: c for c in (await db.execute(cats_q)).scalars().all()}

    rows = []
    for cat_id in cat_ids:
        cat = cats.get(cat_id)
        if not cat:
            continue

        plan = plans.get(cat_id)
        actual_amount, tx_count = actual_amount_map.get(cat_id, (0.0, 0))

        # Resolve plan amount
        plan_amount: float | None = None
        has_override = False
        if plan:
            if plan.plan_type == "fixed_monthly" and plan.monthly_amount is not None:
                if month is not None:
                    overrides = plan.monthly_overrides or {}
                    if str(month) in overrides:
                        plan_amount = float(overrides[str(month)])
                        has_override = True
                    else:
                        plan_amount = float(plan.monthly_amount)
                else:
                    # Annual: base = monthly * 12, apply overrides
                    base = float(plan.monthly_amount) * 12
                    overrides = plan.monthly_overrides or {}
                    for m in range(1, 13):
                        if str(m) in overrides:
                            base = base - float(plan.monthly_amount) + float(overrides[str(m)])
                    plan_amount = base
            elif plan.plan_type == "annual_pool" and plan.annual_amount is not None:
                plan_amount = float(plan.annual_amount) if month is None else float(plan.annual_amount) / 12
            elif plan.plan_type == "one_time" and plan.annual_amount is not None:
                plan_amount = float(plan.annual_amount)

        variance: float | None = None
        variance_pct: float | None = None
        if plan_amount is not None:
            variance = plan_amount - actual_amount
            if plan_amount != 0:
                variance_pct = variance / plan_amount

        rows.append({
            "category_id": str(cat_id),
            "category_name": cat.name,
            "category_type": cat.category_type,
            "plan_amount": plan_amount,
            "actual_amount": actual_amount,
            "variance": variance,
            "variance_pct": variance_pct,
            "transaction_count": tx_count,
            "has_override": has_override,
        })

    type_order = {"income": 0, "expense": 1, "saving": 2, "investment": 3}
    rows.sort(key=lambda r: (type_order.get(r["category_type"], 9), r["category_name"]))
    return rows


# ── Rules ──────────────────────────────────────────────────────────────────────

def _rule_to_read(rule: BudgetCategoryRule, category_name: str = "") -> BudgetRuleRead:
    r = BudgetRuleRead.model_validate(rule)
    r.category_name = category_name
    return r


@router.get("/rules/", response_model=List[BudgetRuleRead])
async def list_rules(
    portfolio_id: UUID = Depends(_verified_pid),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    q = select(BudgetCategoryRule).where(
        BudgetCategoryRule.portfolio_id == portfolio_id,
    )
    if status_filter and status_filter != "all":
        q = q.where(BudgetCategoryRule.status == status_filter)
    else:
        q = q.where(BudgetCategoryRule.status != "deleted")
    q = q.order_by(BudgetCategoryRule.priority, BudgetCategoryRule.created_at.desc())
    rules = (await db.execute(q)).scalars().all()

    # Load category names
    cat_ids = {r.category_id for r in rules}
    cats = {}
    if cat_ids:
        cq = select(BudgetCategory).where(BudgetCategory.id.in_(cat_ids))
        cats = {c.id: c.name for c in (await db.execute(cq)).scalars().all()}

    return [_rule_to_read(r, cats.get(r.category_id, "")) for r in rules]


@router.post("/rules/", response_model=BudgetRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: BudgetRuleCreate,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    rule = BudgetCategoryRule(
        id=uuid.uuid4(), portfolio_id=portfolio_id, **payload.model_dump()
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    cat = await db.get(BudgetCategory, rule.category_id)
    return _rule_to_read(rule, cat.name if cat else "")


@router.patch("/rules/{rule_id}/", response_model=BudgetRuleRead)
async def update_rule(
    rule_id: UUID,
    payload: BudgetRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    rule = await db.get(BudgetCategoryRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.flush()
    await db.refresh(rule)
    cat = await db.get(BudgetCategory, rule.category_id)
    return _rule_to_read(rule, cat.name if cat else "")


@router.delete("/rules/{rule_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    rule = await db.get(BudgetCategoryRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.status = "deleted"
    await db.flush()


@router.post("/rules/{rule_id}/approve/", response_model=BudgetRuleRead)
async def approve_rule(rule_id: UUID, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    rule = await db.get(BudgetCategoryRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.status = "active"
    rule.source = "user_confirmed" if rule.source == "ai_generated" else rule.source
    await db.flush()
    await db.refresh(rule)
    cat = await db.get(BudgetCategory, rule.category_id)
    return _rule_to_read(rule, cat.name if cat else "")


@router.post("/rules/{rule_id}/test/", response_model=BudgetRuleTestResult)
async def test_rule(
    rule_id: UUID,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    rule = await db.get(BudgetCategoryRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    from app.processors.rule_engine import RuleEngine
    engine = RuleEngine()
    return await engine.test_rule(rule.conditions, portfolio_id, db)


@router.post("/rules/test-conditions/", response_model=BudgetRuleTestResult)
async def test_conditions(
    conditions: dict,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    """Test arbitrary conditions (before saving the rule)."""
    from app.processors.rule_engine import RuleEngine
    engine = RuleEngine()
    return await engine.test_rule(conditions, portfolio_id, db)


@router.post("/rules/reorder/", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_rules(
    updates: List[dict],
    db: AsyncSession = Depends(get_db),
):
    """Bulk update priorities. Body: [{"id": "...", "priority": 10}, ...]"""
    for item in updates:
        rule = await db.get(BudgetCategoryRule, UUID(item["id"]))
        if rule:
            rule.priority = int(item["priority"])
    await db.flush()


# ── Review queue ───────────────────────────────────────────────────────────────

@router.get("/review/", response_model=List[ClassificationLogRead])
async def get_review_queue(
    portfolio_id: UUID = Depends(_verified_pid),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Unclassified transactions needing human review."""
    q = (
        select(ClassificationLog)
        .join(RawTransaction, ClassificationLog.raw_transaction_id == RawTransaction.id)
        .where(
            RawTransaction.portfolio_id == portfolio_id,
            ClassificationLog.needs_review == True,
            ClassificationLog.reviewed_at == None,
        )
        .order_by(ClassificationLog.created_at.desc())
        .limit(limit)
    )
    logs = (await db.execute(q)).scalars().all()

    result = []
    for log_entry in logs:
        raw = await db.get(RawTransaction, log_entry.raw_transaction_id)
        cat = await db.get(BudgetCategory, log_entry.category_id) if log_entry.category_id else None
        item = ClassificationLogRead.model_validate(log_entry)
        if raw:
            item.raw_description = raw.description
            item.raw_amount = raw.amount
            item.raw_date = raw.raw_date
            item.raw_source = raw.source
        if cat:
            item.category_name = cat.name
        result.append(item)
    return result


def _extract_keyword(description: str) -> str:
    """Extract a meaningful search keyword from a bank transaction description."""
    import re
    text = description or ""
    # Remove ref codes like (י-12345), (1234), brackets with numbers
    text = re.sub(r'\([^)]*\d[^)]*\)', '', text)
    # Remove leading noise words common in Israeli bank transactions
    text = re.sub(r'^\s*(הרשאה|העברה|תשלום|חיוב|זיכוי|זכ|מש)\s*', '', text, flags=re.IGNORECASE)
    # Remove standalone numbers and date-like patterns
    text = re.sub(r'\b\d[\d/.-]*\b', '', text)
    # Strip trailing junk after dash/hyphen if remainder is short
    text = re.sub(r'\s*[-–]\s*\S{0,6}\s*$', '', text.strip())
    # Collapse whitespace and strip
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:50].strip() or description[:50]


@router.post("/review/{log_id}/categorize/")
async def categorize_review_item(
    log_id: UUID,
    body: dict,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually categorize a review-queue item.
    Body: { "category_id": "uuid", "generate_rule": true }
         or { "excluded": true }
    All steps run in one transaction — any failure rolls back everything.
    """
    category_id_raw: str = body.get("category_id") or ""
    generate_rule: bool = bool(body.get("generate_rule", False))
    is_excluded: bool = bool(body.get("excluded", False)) or category_id_raw == "exclude"

    log_entry = await db.get(ClassificationLog, log_id)
    if not log_entry:
        raise HTTPException(status_code=404, detail="Log entry not found")

    log.info(f"Categorizing {log_id} → {'exclude' if is_excluded else category_id_raw} (generate_rule={generate_rule})")

    now = datetime.now(timezone.utc)

    # ── Step 1: Update classification_log ────────────────────────────────────
    log_entry.reviewed_at = now
    log_entry.reviewed_by = "manual"
    log_entry.needs_review = False

    # ── Step 3: Handle exclusion ──────────────────────────────────────────────
    if is_excluded:
        log_entry.excluded = True
        log_entry.method = "excluded"

        # Remove junction row (if any) and recalculate affected bucket
        existing_bat = await db.get(BudgetActualTransaction, log_entry.raw_transaction_id)
        if existing_bat:
            old_actual_id = existing_bat.budget_actual_id
            await db.delete(existing_bat)
            await db.flush()
            await _recalculate_budget_actual(db, old_actual_id, now)
            log.info(f"Junction row deleted; recalculated budget_actual={old_actual_id}")

        await db.flush()
        log.info(f"log_id={log_id} marked as excluded")
        return {"success": True, "log_id": str(log_id), "excluded": True,
                "rule_created": False, "budget_actual_updated": False}

    # ── Steps 1–2: Classify ───────────────────────────────────────────────────
    if not category_id_raw:
        raise HTTPException(status_code=422, detail="category_id is required when not excluding")

    cat_id = UUID(category_id_raw)
    cat = await db.get(BudgetCategory, cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    log_entry.category_id = cat_id
    log_entry.method = "manual"
    log_entry.confidence = 1.0

    # ── Steps 2 & 4–5: Get raw_transaction, upsert budget_actuals ────────────
    raw_tx = await db.get(RawTransaction, log_entry.raw_transaction_id)
    budget_actual_updated = False

    if raw_tx and raw_tx.raw_date:
        year = raw_tx.raw_date.year
        month = raw_tx.raw_date.month
        amount = abs(raw_tx.amount)

        log.info(f"Budget actual update: {year}/{month:02d} category={cat_id} += {amount}")

        # Detect existing junction row (category change)
        existing_bat = await db.get(BudgetActualTransaction, log_entry.raw_transaction_id)
        old_actual_id = existing_bat.budget_actual_id if existing_bat else None

        # Step 4: Upsert budget_actuals (get-or-create the monthly bucket)
        actual_stmt = (
            pg_insert(BudgetActual)
            .values(
                id=uuid.uuid4(),
                portfolio_id=portfolio_id,
                category_id=cat_id,
                year=year,
                month=month,
                actual_amount=Decimal(0),
                transaction_count=0,
                last_updated=now,
            )
            .on_conflict_do_update(
                constraint="uq_budget_actuals_category_month",
                set_={"last_updated": now},
            )
            .returning(BudgetActual.__table__.c.id)
        )
        actual_id: UUID = (await db.execute(actual_stmt)).scalar_one()

        # Step 5: Upsert junction row (idempotent — prevents double-counting)
        bat_stmt = (
            pg_insert(BudgetActualTransaction)
            .values(
                raw_transaction_id=log_entry.raw_transaction_id,
                budget_actual_id=actual_id,
                amount=amount,
                categorized_at=now,
            )
            .on_conflict_do_update(
                index_elements=["raw_transaction_id"],
                set_={
                    "budget_actual_id": actual_id,
                    "amount": amount,
                    "categorized_at": now,
                },
            )
        )
        await db.execute(bat_stmt)

        # Recalculate new bucket from junction rows
        await _recalculate_budget_actual(db, actual_id, now)

        # Recalculate old bucket if category changed
        if old_actual_id and old_actual_id != actual_id:
            await _recalculate_budget_actual(db, old_actual_id, now)

        log.info(f"Budget actual updated: {year}/{month:02d} += {amount}")
        budget_actual_updated = True

    # ── Step 6: Generate suggested rule (keyword-based, no AI needed) ─────────
    rule_created = False
    if generate_rule and raw_tx and raw_tx.description:
        try:
            keyword = _extract_keyword(raw_tx.description)
            if keyword:
                new_rule = BudgetCategoryRule(
                    id=uuid.uuid4(),
                    portfolio_id=portfolio_id,
                    category_id=cat_id,
                    name=f"Auto: {raw_tx.description[:50]}",
                    priority=50,
                    status="suggested",
                    conditions={
                        "operator": "AND",
                        "rules": [
                            {"field": "description", "op": "contains", "value": keyword}
                        ],
                    },
                    confidence=1.0,
                    source="user_confirmed",
                )
                db.add(new_rule)
                rule_created = True
                log.info(f"Rule created: category={cat_id} keyword='{keyword}'")
        except Exception:
            log.exception("Rule generation failed (non-fatal, continuing)")

    # ── Step 7: Flush (get_db commits after return) ───────────────────────────
    await db.flush()
    log.info(f"log_id={log_id} categorized → {cat_id} rule_created={rule_created} ✓")

    # ── Step 8: Return response ───────────────────────────────────────────────
    return {
        "success": True,
        "log_id": str(log_id),
        "category_id": str(cat_id),
        "rule_created": rule_created,
        "budget_actual_updated": budget_actual_updated,
    }


# ── Bulk approve high-confidence review items ─────────────────────────────────

@router.post("/review/approve-bulk/")
async def approve_bulk_review(
    body: dict,
    portfolio_id: UUID = Depends(_verified_pid),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve all review-queue items whose confidence >= min_confidence and that
    already have a category assigned (AI classified but flagged for confirmation).
    Runs in a single flush so a failure leaves the DB consistent.
    """
    min_confidence = float(body.get("min_confidence", 0.9))

    q = (
        select(ClassificationLog)
        .join(RawTransaction, ClassificationLog.raw_transaction_id == RawTransaction.id)
        .where(
            RawTransaction.portfolio_id == portfolio_id,
            ClassificationLog.needs_review == True,
            ClassificationLog.reviewed_at == None,
            ClassificationLog.category_id != None,
            ClassificationLog.confidence >= min_confidence,
        )
    )
    entries = (await db.execute(q)).scalars().all()

    if not entries:
        return {"approved": 0, "total_amount": 0.0, "categories": {}}

    # Pre-load category names for the summary
    cat_ids = {e.category_id for e in entries if e.category_id}
    cats: dict = {}
    if cat_ids:
        cq = select(BudgetCategory).where(BudgetCategory.id.in_(cat_ids))
        cats = {c.id: c.name for c in (await db.execute(cq)).scalars().all()}

    now = datetime.now(timezone.utc)
    approved = 0
    total_amount = Decimal(0)
    cat_counts: dict = {}

    for log_entry in entries:
        cat_id = log_entry.category_id
        if not cat_id:
            continue

        # Mark reviewed
        log_entry.reviewed_at = now
        log_entry.reviewed_by = "bulk_approve"
        log_entry.needs_review = False

        raw_tx = await db.get(RawTransaction, log_entry.raw_transaction_id)
        if not raw_tx or not raw_tx.raw_date:
            approved += 1
            continue

        year = raw_tx.raw_date.year
        month = raw_tx.raw_date.month
        amount = abs(raw_tx.amount)
        total_amount += amount

        # Upsert monthly bucket
        actual_stmt = (
            pg_insert(BudgetActual)
            .values(
                id=uuid.uuid4(),
                portfolio_id=portfolio_id,
                category_id=cat_id,
                year=year,
                month=month,
                actual_amount=Decimal(0),
                transaction_count=0,
                last_updated=now,
            )
            .on_conflict_do_update(
                constraint="uq_budget_actuals_category_month",
                set_={"last_updated": now},
            )
            .returning(BudgetActual.__table__.c.id)
        )
        actual_id: UUID = (await db.execute(actual_stmt)).scalar_one()

        # Upsert junction row (idempotent)
        bat_stmt = (
            pg_insert(BudgetActualTransaction)
            .values(
                raw_transaction_id=log_entry.raw_transaction_id,
                budget_actual_id=actual_id,
                amount=amount,
                categorized_at=now,
            )
            .on_conflict_do_update(
                index_elements=["raw_transaction_id"],
                set_={
                    "budget_actual_id": actual_id,
                    "amount": amount,
                    "categorized_at": now,
                },
            )
        )
        await db.execute(bat_stmt)
        await _recalculate_budget_actual(db, actual_id, now)

        cat_name = cats.get(cat_id, str(cat_id))
        cat_counts[cat_name] = cat_counts.get(cat_name, 0) + 1
        approved += 1

    await db.flush()
    log.info("Bulk approved %d transactions (min_confidence=%.2f)", approved, min_confidence)

    return {
        "approved": approved,
        "total_amount": float(total_amount),
        "categories": cat_counts,
    }


# ── Classification log ─────────────────────────────────────────────────────────

@router.get("/classification-log/", response_model=List[ClassificationLogRead])
async def get_classification_log(
    portfolio_id: UUID = Depends(_verified_pid),
    method: Optional[str] = Query(None),
    needs_review: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(ClassificationLog)
        .join(RawTransaction, ClassificationLog.raw_transaction_id == RawTransaction.id)
        .where(RawTransaction.portfolio_id == portfolio_id)
        .order_by(ClassificationLog.created_at.desc())
        .limit(limit)
    )
    if method:
        q = q.where(ClassificationLog.method == method)
    if needs_review is not None:
        q = q.where(ClassificationLog.needs_review == needs_review)

    logs = (await db.execute(q)).scalars().all()
    result = []
    for log_entry in logs:
        raw = await db.get(RawTransaction, log_entry.raw_transaction_id)
        cat = await db.get(BudgetCategory, log_entry.category_id) if log_entry.category_id else None
        item = ClassificationLogRead.model_validate(log_entry)
        if raw:
            item.raw_description = raw.description
            item.raw_amount = raw.amount
            item.raw_date = raw.raw_date
            item.raw_source = raw.source
        if cat:
            item.category_name = cat.name
        result.append(item)
    return result


