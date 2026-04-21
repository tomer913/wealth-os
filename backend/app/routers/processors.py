"""
Processor router — exposes processor run history and manual trigger.
"""
import uuid as _uuid
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.raw_layer import ProcessorRun

router = APIRouter(prefix="/processors", tags=["processors"])


class ProcessorRunRequest(BaseModel):
    processor_name: str
    portfolio_id: UUID
    date_from: Optional[date_type] = None
    date_to: Optional[date_type] = None


async def _create_pending_run(
    processor_name: str, portfolio_id: UUID, db: AsyncSession
) -> Tuple[UUID, ProcessorRun]:
    """Create a ProcessorRun with status='pending', flush, and return (run_id, record)."""
    run_id = _uuid.uuid4()
    proc_run = ProcessorRun(
        id=run_id,
        processor_name=processor_name,
        portfolio_id=portfolio_id,
        status="pending",
        triggered_by="manual",
    )
    db.add(proc_run)
    await db.flush()
    await db.commit()
    return run_id, proc_run


@router.get("/runs/", response_model=list[dict])
async def list_processor_runs(
    portfolio_id: Optional[UUID] = Query(None),
    processor_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List recent processor runs, optionally filtered by portfolio and/or processor."""
    if portfolio_id:
        await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    q = select(ProcessorRun).order_by(ProcessorRun.created_at.desc()).limit(limit)
    if portfolio_id:
        q = q.where(ProcessorRun.portfolio_id == portfolio_id)
    if processor_name:
        q = q.where(ProcessorRun.processor_name == processor_name)

    runs = (await db.execute(q)).scalars().all()
    return [
        {
            "id": str(r.id),
            "processor_name": r.processor_name,
            "portfolio_id": str(r.portfolio_id),
            "status": r.status,
            "triggered_by": r.triggered_by,
            "checkpoint_from": str(r.checkpoint_from) if r.checkpoint_from else None,
            "checkpoint_to": str(r.checkpoint_to) if r.checkpoint_to else None,
            "rows_read": r.rows_read,
            "rows_written": r.rows_written,
            "rows_skipped": r.rows_skipped,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat(),
            "date_from": r.date_from.isoformat() if r.date_from else None,
            "date_to": r.date_to.isoformat() if r.date_to else None,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_processor_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single processor run by ID."""
    run = await db.get(ProcessorRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Processor run not found")
    if run.portfolio_id:
        await verify_portfolio_access(db, run.portfolio_id, current_user["user_id"], current_user.get("org_id"))
    return {
        "id": str(run.id),
        "processor_name": run.processor_name,
        "portfolio_id": str(run.portfolio_id),
        "status": run.status,
        "triggered_by": run.triggered_by,
        "checkpoint_from": str(run.checkpoint_from) if run.checkpoint_from else None,
        "checkpoint_to": str(run.checkpoint_to) if run.checkpoint_to else None,
        "rows_read": run.rows_read,
        "rows_written": run.rows_written,
        "rows_skipped": run.rows_skipped,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
        "error_traceback": run.error_traceback,
        "created_at": run.created_at.isoformat(),
    }


@router.post("/bank/run")
async def trigger_bank_processor(
    portfolio_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger BankProcessor for a portfolio (runs in background)."""
    import asyncio
    from app.processors.bank_processor import BankProcessor

    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    run_id, proc_run = await _create_pending_run("bank_processor", portfolio_id, db)
    processor = BankProcessor()
    asyncio.create_task(processor.run(portfolio_id, triggered_by="manual", run_id=run_id))
    return {"status": "started", "run_id": str(run_id), "processor": "bank_processor"}


@router.post("/bank/reset-checkpoint")
async def reset_bank_checkpoint(
    portfolio_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Reset BankProcessor checkpoint to replay all raw transactions."""
    from app.processors.bank_processor import BankProcessor

    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    processor = BankProcessor()
    await processor.reset_checkpoint(portfolio_id)
    return {"status": "reset", "processor": "bank_processor", "portfolio_id": str(portfolio_id)}


@router.post("/budget/run")
async def trigger_budget_processor(
    portfolio_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger BudgetProcessor for a portfolio (runs in background)."""
    import asyncio
    from app.processors.budget_processor import BudgetProcessor

    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    run_id, proc_run = await _create_pending_run("budget_processor", portfolio_id, db)
    processor = BudgetProcessor()
    asyncio.create_task(processor.run(portfolio_id, triggered_by="manual", run_id=run_id))
    return {"status": "started", "run_id": str(run_id), "processor": "budget_processor"}


@router.post("/budget/reset-checkpoint")
async def reset_budget_checkpoint(
    portfolio_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Reset BudgetProcessor checkpoint to reclassify all raw transactions."""
    from app.processors.budget_processor import BudgetProcessor

    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
    processor = BudgetProcessor()
    await processor.reset_checkpoint(portfolio_id)
    return {"status": "reset", "processor": "budget_processor", "portfolio_id": str(portfolio_id)}


@router.post("/run")
async def trigger_processor(
    body: ProcessorRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Generic: trigger any processor by name. Returns run_id for polling.
    Body: { processor_name, portfolio_id, date_from?, date_to? }
    If date_from/date_to supplied: date-range rerun (ignores/doesn't advance checkpoint).
    """
    import asyncio

    await verify_portfolio_access(db, body.portfolio_id, current_user["user_id"], current_user.get("org_id"))

    if body.processor_name == "bank_processor":
        from app.processors.bank_processor import BankProcessor
        processor = BankProcessor()
    elif body.processor_name == "budget_processor":
        from app.processors.budget_processor import BudgetProcessor
        processor = BudgetProcessor()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown processor: {body.processor_name}")

    run_id, _ = await _create_pending_run(body.processor_name, body.portfolio_id, db)
    asyncio.create_task(
        processor.run(
            body.portfolio_id,
            triggered_by="manual",
            run_id=run_id,
            date_from=body.date_from,
            date_to=body.date_to,
        )
    )
    return {"status": "started", "run_id": str(run_id), "processor": body.processor_name}


@router.post("/reset-checkpoint")
async def reset_processor_checkpoint(
    processor_name: str = Query(...),
    portfolio_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generic: reset checkpoint for any processor by name."""
    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))

    if processor_name == "bank_processor":
        from app.processors.bank_processor import BankProcessor
        processor = BankProcessor()
    elif processor_name == "budget_processor":
        from app.processors.budget_processor import BudgetProcessor
        processor = BudgetProcessor()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown processor: {processor_name}")

    await processor.reset_checkpoint(portfolio_id)
    return {"status": "reset", "processor": processor_name, "portfolio_id": str(portfolio_id)}
