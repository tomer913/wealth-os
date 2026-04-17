import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.connector import Connector, ConnectorRun
from app.schemas.connector import (
    ConnectorCreate,
    ConnectorRead,
    ConnectorRunListResponse,
    ConnectorRunRead,
    ConnectorUpdate,
    TriggerRunResponse,
)
from app.utils.encryption import decrypt_config, encrypt_config, get_config_keys

router = APIRouter(prefix="/connectors", tags=["connectors"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_read(connector: Connector, latest_run: ConnectorRun | None = None) -> ConnectorRead:
    data = ConnectorRead(
        id=connector.id,
        portfolio_id=connector.portfolio_id,
        name=connector.name,
        type=connector.type,
        config_keys=get_config_keys(connector.config),
        asset_filter=connector.asset_filter,
        auto_create_assets=connector.auto_create_assets,
        schedule=connector.schedule,
        is_active=connector.is_active,
        last_run_at=connector.last_run_at,
        last_error=connector.last_error,
        created_at=connector.created_at,
        updated_at=connector.updated_at,
    )
    if latest_run:
        data.last_run_status = latest_run.status
        data.last_run_summary = {
            "transactions_created": latest_run.transactions_created,
            "assets_created": latest_run.assets_created,
            "fx_rates_updated": latest_run.fx_rates_updated,
            "prices_updated": latest_run.prices_updated,
            "duration_ms": latest_run.duration_ms,
        }
    return data


# ── Connector CRUD ────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ConnectorRead])
async def list_connectors(
    portfolio_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Connector)
    if portfolio_id:
        q = q.where(Connector.portfolio_id == portfolio_id)
    q = q.order_by(Connector.name)
    connectors = (await db.execute(q)).scalars().all()

    result = []
    for connector in connectors:
        # Get latest run for each connector
        run_q = (
            select(ConnectorRun)
            .where(ConnectorRun.connector_id == connector.id)
            .order_by(ConnectorRun.created_at.desc())
            .limit(1)
        )
        latest_run = (await db.execute(run_q)).scalar_one_or_none()
        result.append(_to_read(connector, latest_run))
    return result


@router.post("/", response_model=ConnectorRead, status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: ConnectorCreate,
    portfolio_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    # Encrypt sensitive config fields before storing
    encrypted_config = encrypt_config(payload.config)
    connector = Connector(
        portfolio_id=portfolio_id,
        name=payload.name,
        type=payload.type,
        config=encrypted_config,
        asset_filter=payload.asset_filter,
        auto_create_assets=payload.auto_create_assets,
        schedule=payload.schedule,
        is_active=payload.is_active,
    )
    db.add(connector)
    await db.flush()
    await db.refresh(connector)
    return _to_read(connector)


@router.get("/{connector_id}", response_model=ConnectorRead)
async def get_connector(connector_id: UUID, db: AsyncSession = Depends(get_db)):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    run_q = (
        select(ConnectorRun)
        .where(ConnectorRun.connector_id == connector_id)
        .order_by(ConnectorRun.created_at.desc())
        .limit(1)
    )
    latest_run = (await db.execute(run_q)).scalar_one_or_none()
    return _to_read(connector, latest_run)


@router.patch("/{connector_id}", response_model=ConnectorRead)
async def update_connector(
    connector_id: UUID,
    payload: ConnectorUpdate,
    db: AsyncSession = Depends(get_db),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    data = payload.model_dump(exclude_unset=True)
    if "config" in data:
        # Merge with existing config, encrypt new sensitive fields
        merged = {**connector.config, **data["config"]}
        data["config"] = encrypt_config(merged)

    for field, value in data.items():
        setattr(connector, field, value)

    await db.flush()
    await db.refresh(connector)
    return _to_read(connector)


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(connector_id: UUID, db: AsyncSession = Depends(get_db)):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    await db.delete(connector)


# ── Trigger run ───────────────────────────────────────────────────────────────

@router.post("/{connector_id}/run", response_model=TriggerRunResponse)
async def trigger_run(
    connector_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if not connector.is_active:
        raise HTTPException(status_code=400, detail="Connector is disabled")

    # Create run record immediately with pending status
    run = ConnectorRun(
        id=uuid.uuid4(),
        connector_id=connector_id,
        portfolio_id=connector.portfolio_id,
        status="pending",
        triggered_by="manual",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    run_id = run.id

    # Execute in background so API returns immediately
    background_tasks.add_task(
        _execute_connector_run,
        connector_id=str(connector_id),
        run_id=str(run_id),
    )

    return TriggerRunResponse(
        run_id=run_id,
        connector_id=connector_id,
        status="pending",
        message=f"Run started for connector '{connector.name}'",
    )


async def _execute_connector_run(connector_id: str, run_id: str):
    """Background task — executes the connector and updates the run record."""
    from app.database import AsyncSessionLocal
    from app.connectors.registry import get_connector_handler

    async with AsyncSessionLocal() as db:
        try:
            run = await db.get(ConnectorRun, uuid.UUID(run_id))
            connector = await db.get(Connector, uuid.UUID(connector_id))
            if not run or not connector:
                return

            # Mark as running
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.flush()

            # Decrypt config and execute
            config = decrypt_config(connector.config)
            handler = await get_connector_handler(connector.type)

            if not handler:
                raise ValueError(f"Unknown connector type: {connector.type}")

            result = await handler.run(
                config=config,
                portfolio_id=connector.portfolio_id,
                asset_filter=connector.asset_filter,
                auto_create_assets=connector.auto_create_assets,
                db=db,
            )

            # Update run — success
            finished = datetime.now(timezone.utc)
            run.status = "success"
            run.finished_at = finished
            run.duration_ms = int(
                (finished - run.started_at).total_seconds() * 1000
            )
            run.records_fetched = result.get("records_fetched", 0)
            run.transactions_created = result.get("transactions_created", 0)
            run.transactions_skipped = result.get("transactions_skipped", 0)
            run.valuations_created = result.get("valuations_created", 0)
            run.assets_created = result.get("assets_created", 0)
            run.fx_rates_updated = result.get("fx_rates_updated", 0)
            run.prices_updated = result.get("prices_updated", 0)
            run.checkpoint = result.get("checkpoint")

            # Update connector last_run
            connector.last_run_at = finished
            connector.last_error = None

            await db.commit()

        except Exception as e:
            await db.rollback()
            async with AsyncSessionLocal() as err_db:
                run = await err_db.get(ConnectorRun, uuid.UUID(run_id))
                connector = await err_db.get(Connector, uuid.UUID(connector_id))
                if run:
                    finished = datetime.now(timezone.utc)
                    run.status = "failed"
                    run.finished_at = finished
                    run.error_message = str(e)
                    run.error_traceback = traceback.format_exc()
                    if run.started_at:
                        run.duration_ms = int(
                            (finished - run.started_at).total_seconds() * 1000
                        )
                if connector:
                    connector.last_error = str(e)
                await err_db.commit()


# ── Run history ───────────────────────────────────────────────────────────────

@router.get("/{connector_id}/runs", response_model=ConnectorRunListResponse)
async def list_runs(
    connector_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    count_q = select(func.count(ConnectorRun.id)).where(
        ConnectorRun.connector_id == connector_id
    )
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * limit
    q = (
        select(ConnectorRun)
        .where(ConnectorRun.connector_id == connector_id)
        .order_by(ConnectorRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    runs = (await db.execute(q)).scalars().all()

    return ConnectorRunListResponse(
        items=runs,
        total=total,
        page=page,
        limit=limit,
        pages=max(1, -(-total // limit)),
    )


@router.get("/runs/{run_id}", response_model=ConnectorRunRead)
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(ConnectorRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── File upload endpoint ──────────────────────────────────────────────────────

UPLOAD_SUPPORTED = {"mizrachi_bank", "fibi_bank"}


@router.post("/upload/")
async def upload_bank_statement(
    file: UploadFile = File(...),
    connector_type: str = Form(...),
    portfolio_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a PDF or XLSX bank statement, parse it, and write to raw_transactions.
    Supported connector_type values: mizrachi_bank, fibi_bank.
    """
    if connector_type not in UPLOAD_SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Upload not supported for connector type '{connector_type}'. "
                   f"Supported: {sorted(UPLOAD_SUPPORTED)}",
        )

    # Look up connector record
    q = (
        select(Connector)
        .where(
            Connector.type == connector_type,
            Connector.portfolio_id == portfolio_id,
            Connector.is_active.is_(True),
        )
        .limit(1)
    )
    connector = (await db.execute(q)).scalar_one_or_none()
    if not connector:
        raise HTTPException(
            status_code=404,
            detail=f"No active connector of type '{connector_type}' found for this portfolio",
        )

    # Read file bytes
    file_bytes = await file.read()
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Parse based on connector type and file extension
    try:
        if connector_type == "mizrachi_bank":
            from app.connectors.parsers.mizrachi import parse_mizrachi_pdf
            if ext not in ("pdf",):
                raise HTTPException(status_code=400, detail="Mizrachi Bank accepts PDF files only")
            rows = parse_mizrachi_pdf(file_bytes)

        else:  # fibi_bank
            if ext == "xlsx":
                from app.connectors.parsers.fibi import parse_fibi_xlsx
                rows = parse_fibi_xlsx(file_bytes)
            elif ext == "pdf":
                from app.connectors.parsers.fibi import parse_fibi_pdf
                rows = parse_fibi_pdf(file_bytes)
            else:
                raise HTTPException(status_code=400, detail="FIBI Bank accepts PDF or XLSX files only")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}") from exc

    # Write rows to raw_transactions with same dedup logic as BaseConnector._run_raw
    from app.models.raw_layer import RawTransaction
    from app.utils.uuid7 import uuid7
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    source = connector_type
    started_at = datetime.now(timezone.utc)
    created = 0
    skipped = 0

    for row in rows:
        stmt = pg_insert(RawTransaction).values(
            id=uuid7(),
            portfolio_id=portfolio_id,
            source=source,
            raw_date=row["raw_date"],
            description=row["description"],
            amount=row["amount"],
            currency=row.get("currency", "ILS"),
            reference=row.get("reference"),
            extra_raw=row.get("extra_raw"),
            external_ref_id=row["external_ref_id"],
            imported_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing(constraint="uq_raw_transactions_source_ref")

        result = await db.execute(stmt)
        if result.rowcount:
            created += 1
        else:
            skipped += 1

    # Create connector_run audit record
    finished_at = datetime.now(timezone.utc)
    run = ConnectorRun(
        id=uuid.uuid4(),
        connector_id=connector.id,
        portfolio_id=portfolio_id,
        status="success",
        triggered_by="manual",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        records_fetched=len(rows),
        transactions_created=created,
        transactions_skipped=skipped,
    )
    db.add(run)

    # Update connector.last_run_at
    connector.last_run_at = finished_at
    connector.last_error = None

    await db.commit()

    return {
        "created": created,
        "skipped": skipped,
        "total": len(rows),
        "connector_name": connector.name,
        "source": source,
    }


# ── Ingest endpoint (for GitHub Actions scraper) ──────────────────────────────

import os as _os
from fastapi import Header

SCRAPER_SECRET = _os.environ.get("SCRAPER_SECRET", "")


@router.post("/ingest/")
async def ingest_raw_transactions(
    payload: dict,
    x_scraper_token: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the GitHub Actions credit card scraper.
    Body: { "source": "isracard", "transactions": [{ "date", "description",
            "amount", "currency", "identifier", "extra_data" }] }
    Protected by X-Scraper-Token header.
    """
    if SCRAPER_SECRET and x_scraper_token != SCRAPER_SECRET:
        raise HTTPException(status_code=401, detail="Invalid scraper token")

    source = payload.get("source", "")
    transactions = payload.get("transactions", [])
    portfolio_id_str = payload.get("portfolio_id")

    error_payload = payload.get("error")  # present when scraper failed

    if not source or not portfolio_id_str:
        raise HTTPException(status_code=422, detail="source and portfolio_id required")
    if not transactions and not error_payload:
        raise HTTPException(status_code=422, detail="transactions or error required")

    from app.models.raw_layer import RawTransaction
    from app.utils.uuid7 import uuid7
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import datetime, timezone
    import uuid as _uuid

    portfolio_id = _uuid.UUID(portfolio_id_str)
    now = datetime.now(timezone.utc)

    # ── Error path: scraper failed — record a failed ConnectorRun ─────────────
    if error_payload:
        connector_q = select(Connector).where(
            Connector.type == source,
            Connector.portfolio_id == portfolio_id,
        )
        connector = (await db.execute(connector_q)).scalar_one_or_none()
        if connector:
            error_msg = error_payload.get("message") or error_payload.get("errorType", "unknown error")
            run = ConnectorRun(
                id=_uuid.uuid4(),
                connector_id=connector.id,
                portfolio_id=portfolio_id,
                status="failed",
                triggered_by="scheduler",
                started_at=now,
                finished_at=now,
                duration_ms=0,
                records_fetched=0,
                transactions_created=0,
                transactions_skipped=0,
                error_message=f"[{error_payload.get('errorType', 'GENERIC')}] {error_msg}",
            )
            db.add(run)
            connector.last_run_at = now
            connector.last_error = error_msg
            await db.commit()
        return {
            "status": "error",
            "source": source,
            "error": error_payload.get("message"),
            "errorType": error_payload.get("errorType"),
        }

    # ── Success path: ingest transactions ─────────────────────────────────────
    created = 0
    skipped = 0

    for tx in transactions:
        raw_date_str = tx.get("date", "")
        try:
            raw_date = datetime.fromisoformat(raw_date_str)
        except Exception:
            from datetime import date
            raw_date = datetime.strptime(raw_date_str[:10], "%Y-%m-%d")

        stmt = pg_insert(RawTransaction).values(
            id=uuid7(),
            portfolio_id=portfolio_id,
            source=source,
            raw_date=raw_date,
            description=tx.get("description", ""),
            amount=tx.get("amount", 0),
            currency=tx.get("currency", "ILS"),
            reference=tx.get("reference"),
            extra_raw=tx.get("extra_data"),
            external_ref_id=str(tx.get("identifier", "")),
            imported_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing(constraint="uq_raw_transactions_source_ref")

        result = await db.execute(stmt)
        if result.rowcount:
            created += 1
        else:
            skipped += 1

    await db.commit()
    return {"status": "ok", "created": created, "skipped": skipped, "source": source}
