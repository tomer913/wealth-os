import logging as _logging
import os
import traceback
import uuid
from datetime import date as date_type, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
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
from app.utils.encryption import (
    SENSITIVE_KEYS, decrypt_config, encrypt_config, get_config_keys, mask_config,
)

router = APIRouter(prefix="/connectors", tags=["connectors"])
_log = _logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_read(connector: Connector, latest_run: ConnectorRun | None = None) -> ConnectorRead:
    # Decrypt config to get real keys and masked values for the edit form
    try:
        decrypted = decrypt_config(connector.config)
        real_keys = list(decrypted.keys())
        config_display = mask_config(decrypted)
    except Exception:
        real_keys = get_config_keys(connector.config)
        config_display = None

    data = ConnectorRead(
        id=connector.id,
        portfolio_id=connector.portfolio_id,
        name=connector.name,
        type=connector.type,
        config_keys=real_keys,
        config_display=config_display,
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
        data.last_run_started_at = latest_run.started_at
        data.last_run_summary = {
            "transactions_created": latest_run.transactions_created,
            "assets_created": latest_run.assets_created,
            "fx_rates_updated": latest_run.fx_rates_updated,
            "prices_updated": latest_run.prices_updated,
            "duration_ms": latest_run.duration_ms,
        }
    return data


def _normalize_fibi_row(row: dict) -> dict:
    """Map parse_fibi_xlsx() output keys to the upload handler's raw row format."""
    d = row["date"]
    raw_date = datetime(d.year, d.month, d.day) if isinstance(d, date_type) else d
    extra = row.get("extra_data") or {}
    return {
        "raw_date": raw_date,
        "description": row["description"],
        "amount": row["amount"],
        "currency": "ILS",
        "reference": extra.get("reference") or None,
        "extra_raw": extra,
        "external_ref_id": row["reference_id"],
    }


# ── Connector CRUD ────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ConnectorRead])
async def list_connectors(
    portfolio_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if portfolio_id:
        await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"))
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
    current_user: dict = Depends(get_current_user),
):
    await verify_portfolio_access(db, portfolio_id, current_user["user_id"], current_user.get("org_id"), required_role="editor")
    if not os.environ.get("CONNECTOR_ENCRYPTION_KEY"):
        raise HTTPException(
            status_code=500,
            detail=(
                "CONNECTOR_ENCRYPTION_KEY is not configured. "
                "Add this environment variable in Railway before saving connectors."
            ),
        )
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
async def get_connector(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(db, connector.portfolio_id, current_user["user_id"], current_user.get("org_id"))
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
    current_user: dict = Depends(get_current_user),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(db, connector.portfolio_id, current_user["user_id"], current_user.get("org_id"), required_role="editor")

    data = payload.model_dump(exclude_unset=True)
    if "config" in data:
        # Decrypt existing config, then smart-merge:
        # sensitive fields only update if non-empty in the request
        existing = decrypt_config(connector.config)
        new_fields: dict = data["config"]
        for k, v in new_fields.items():
            if k in SENSITIVE_KEYS:
                if v:  # only overwrite sensitive field if user typed a new value
                    existing[k] = v
            else:
                existing[k] = v  # always update non-sensitive
        data["config"] = encrypt_config(existing)
        _log.info("Connector %s config updated — keys: %s", connector_id, list(existing.keys()))

    for field, value in data.items():
        setattr(connector, field, value)

    await db.flush()
    await db.refresh(connector)
    return _to_read(connector)


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(db, connector.portfolio_id, current_user["user_id"], current_user.get("org_id"), required_role="editor")
    await db.delete(connector)


# ── Trigger run ───────────────────────────────────────────────────────────────

@router.post("/{connector_id}/run", response_model=TriggerRunResponse)
async def trigger_run(
    connector_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(db, connector.portfolio_id, current_user["user_id"], current_user.get("org_id"), required_role="editor")
    if not connector.is_active:
        raise HTTPException(status_code=400, detail="Connector is disabled")

    # Create run record immediately with status=running so the UI reflects it at once
    run = ConnectorRun(
        id=uuid.uuid4(),
        connector_id=connector_id,
        portfolio_id=connector.portfolio_id,
        status="running",
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
        status="running",
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

            await db.flush()

            # Decrypt config; auto-migrate plain text configs to encrypted format
            config = decrypt_config(connector.config)
            _log.info("Connector run %s: type=%s config_keys=%s has_api_key=%s",
                      run_id, connector.type, list(config.keys()), bool(config.get("api_key")))

            if "_encrypted" not in connector.config and os.environ.get("CONNECTOR_ENCRYPTION_KEY"):
                try:
                    connector.config = encrypt_config(config)
                    await db.flush()
                    _log.info("Auto-migrated connector %s to encrypted format", connector_id)
                except Exception as mig_err:
                    _log.warning("Auto-migration failed for %s: %s", connector_id, mig_err)

            handler = await get_connector_handler(connector.type)

            if not handler:
                raise ValueError(f"Unknown connector type: {connector.type}")

            result = await handler.run(
                config=config,
                portfolio_id=connector.portfolio_id,
                asset_filter=connector.asset_filter,
                auto_create_assets=connector.auto_create_assets,
                db=db,
                connector_id=uuid.UUID(connector_id),
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
                    # CardScraperError carries github_run_url even on failure
                    if hasattr(e, "checkpoint") and e.checkpoint:
                        run.checkpoint = e.checkpoint
                if connector:
                    # Store only the first line so the card summary stays concise
                    connector.last_error = str(e).split("\n")[0]
                await err_db.commit()


# ── Bulk re-encryption ───────────────────────────────────────────────────────

@router.post("/migrate-encryption/")
async def migrate_encryption(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Re-encrypt all plain-text connector configs with the current encryption key."""
    if not os.environ.get("CONNECTOR_ENCRYPTION_KEY"):
        raise HTTPException(status_code=400, detail="CONNECTOR_ENCRYPTION_KEY is not set")

    connectors = (await db.execute(select(Connector))).scalars().all()
    migrated = 0
    skipped = 0
    errors = 0

    for c in connectors:
        if "_encrypted" in c.config:
            skipped += 1
            continue
        try:
            plain = decrypt_config(c.config)
            c.config = encrypt_config(plain)
            migrated += 1
        except Exception as e:
            _log.warning("migrate-encryption: failed for %s: %s", c.id, e)
            errors += 1

    await db.commit()
    _log.info("migrate-encryption: migrated=%d skipped=%d errors=%d", migrated, skipped, errors)
    return {"migrated": migrated, "already_encrypted": skipped, "errors": errors}


# ── Connector test (diagnostics) ─────────────────────────────────────────────

import logging as _logging
_log = _logging.getLogger(__name__)


@router.get("/{connector_id}/test")
async def test_connector_credentials(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Diagnostic endpoint — decrypts config and makes a real API call to verify
    credentials. Returns raw response (or error) without touching any DB data.
    """
    import httpx, hashlib, hmac, base64, time
    from urllib.parse import urlencode

    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(db, connector.portfolio_id,
                                      current_user["user_id"], current_user.get("org_id"))

    config = decrypt_config(connector.config)

    diag: dict = {
        "connector_type": connector.type,
        "config_keys_stored": list(connector.config.keys()),
        "config_keys_decrypted": list(config.keys()),
        "has_api_key": bool(config.get("api_key")),
        "has_api_secret": bool(config.get("api_secret")),
        "api_key_prefix": (config.get("api_key", "")[:8] + "...") if config.get("api_key") else "<empty>",
        "raw_stored_api_key_prefix": (connector.config.get("api_key", "")[:8] + "...") if connector.config.get("api_key") else "<empty>",
        "api_response": None,
        "error": None,
    }

    try:
        if connector.type == "kraken":
            api_key = config.get("api_key", "")
            api_secret = config.get("api_secret", "")
            if not api_key or not api_secret:
                diag["error"] = "Missing credentials after decryption"
                return diag

            nonce = str(int(time.time() * 1000))
            endpoint = "/0/private/Balance"
            post_data = urlencode({"nonce": nonce})
            message = endpoint.encode() + hashlib.sha256((nonce + post_data).encode()).digest()
            signature = base64.b64encode(
                hmac.new(base64.b64decode(api_secret), message, hashlib.sha512).digest()
            ).decode()

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://api.kraken.com{endpoint}",
                    content=post_data,
                    headers={
                        "API-Key": api_key,
                        "API-Sign": signature,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
            data = resp.json()
            diag["api_response"] = {
                "status_code": resp.status_code,
                "error": data.get("error"),
                "result_keys": list(data.get("result", {}).keys()) if isinstance(data.get("result"), dict) else None,
            }

        elif connector.type == "cexio":
            api_key = config.get("api_key", "")
            api_secret = config.get("api_secret", "")
            username = config.get("username", "")
            if not api_key or not api_secret or not username:
                diag["error"] = f"Missing credentials after decryption: api_key={bool(api_key)} api_secret={bool(api_secret)} username={bool(username)}"
                diag["has_username"] = bool(username)
                return diag

            nonce = str(int(time.time() * 1000))
            message = nonce + username + api_key
            signature = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest().upper()

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://cex.io/api/balance/",
                    data={"key": api_key, "signature": signature, "nonce": nonce},
                )
            data = resp.json()
            diag["has_username"] = bool(username)
            diag["api_response"] = {
                "status_code": resp.status_code,
                "error": data.get("error") if isinstance(data, dict) else None,
                "result_keys": [k for k in (data.keys() if isinstance(data, dict) else [])][:20],
            }

        else:
            diag["error"] = f"No test implementation for connector type '{connector.type}'"

    except Exception as exc:
        _log.exception("Connector test failed for %s", connector_id)
        diag["error"] = str(exc)

    return diag


# ── Credentials endpoint (scraper auth, not Clerk) ───────────────────────────

@router.get("/{connector_id}/credentials/")
async def get_connector_credentials(
    connector_id: UUID,
    x_scraper_token: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the GitHub Actions scraper to retrieve decrypted credentials.
    Authentication: X-Scraper-Token (same token as /ingest/).
    Never logs credential values.
    """
    if SCRAPER_SECRET and x_scraper_token != SCRAPER_SECRET:
        raise HTTPException(status_code=401, detail="Invalid scraper token")

    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    config = decrypt_config(connector.config)
    _log.info("Credentials fetched for connector %s", connector_id)

    company = config.get("company") or connector.type.replace("_scraper", "")
    username = config.get("username", "")
    password = config.get("password", "")
    national_id = config.get("national_id", "")
    raw_cards: list = config.get("cards", [])

    # If no cards are configured yet, synthesise a single entry from the company creds
    if not raw_cards and (username or password):
        raw_cards = [{"name": company, "enabled": True}]

    response_cards = []
    for card in raw_cards:
        if not card.get("enabled", True):
            continue
        entry: dict = {
            "name": card.get("name", ""),
            "card6": card.get("card6") or None,
            "username": username,
            "password": password,
        }
        if national_id:
            entry["national_id"] = national_id
        response_cards.append(entry)

    return {
        "company": company,
        "connector_id": str(connector_id),
        "cards": response_cards,
    }


# ── Connector status ─────────────────────────────────────────────────────────

_STUCK_AFTER_SECONDS = 20 * 60  # 20 minutes


@router.get("/{connector_id}/status/")
async def get_connector_status(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Live status of a connector — is it running, stuck, or idle?
    Also auto-fails runs stuck in 'running'/'pending' for > 20 minutes.
    """
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(
            db, connector.portfolio_id,
            current_user["user_id"], current_user.get("org_id"),
        )

    run_q = (
        select(ConnectorRun)
        .where(ConnectorRun.connector_id == connector_id)
        .order_by(ConnectorRun.created_at.desc())
        .limit(1)
    )
    latest_run = (await db.execute(run_q)).scalar_one_or_none()

    # Stuck-run detection: auto-fail runs that have been 'running' too long
    if latest_run and latest_run.status in ("running", "pending") and latest_run.started_at:
        started = latest_run.started_at
        if started.tzinfo is None:
            from datetime import timezone as _tz
            started = started.replace(tzinfo=_tz.utc)
        age = (datetime.now(timezone.utc) - started).total_seconds()
        if age > _STUCK_AFTER_SECONDS:
            latest_run.status = "failed"
            latest_run.error_message = "Run timed out — connector may have crashed or the server restarted"
            latest_run.finished_at = datetime.now(timezone.utc)
            latest_run.duration_ms = int(age * 1000)
            connector.last_error = "Run timed out after 20 minutes"
            await db.commit()

    is_running = bool(latest_run and latest_run.status in ("running", "pending"))

    result: dict = {"connector_id": str(connector_id), "is_running": is_running}

    if latest_run:
        run_data = {
            "id": str(latest_run.id),
            "status": latest_run.status,
            "triggered_by": latest_run.triggered_by,
            "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
            "finished_at": latest_run.finished_at.isoformat() if latest_run.finished_at else None,
            "records_fetched": latest_run.records_fetched,
            "transactions_created": latest_run.transactions_created,
            "error_message": latest_run.error_message,
        }
        if is_running:
            result["current_run"] = run_data
        else:
            result["last_run"] = run_data

    return result


# ── GitHub Secrets push ───────────────────────────────────────────────────────

_GITHUB_REPO = "tomer913/wealth-os"


@router.post("/{connector_id}/secrets")
async def push_github_secrets(
    connector_id: UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Push credential secrets to GitHub Actions.
    Body: flat dict of { SECRET_NAME: secret_value }.
    Empty values are silently skipped.
    Requires GITHUB_TOKEN env var with actions:write + secrets:write.
    """
    import base64
    import os as _os

    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(
            db, connector.portfolio_id,
            current_user["user_id"], current_user.get("org_id"),
            required_role="editor",
        )

    github_token = _os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured on this server")

    secrets = {k: v for k, v in payload.items() if v}
    if not secrets:
        return {"saved": [], "failed": [], "skipped": "no non-empty values provided"}

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        from nacl.public import SealedBox, PublicKey
    except ImportError:
        raise HTTPException(status_code=500, detail="pynacl is not installed — run pip install pynacl")

    saved = []
    failed = []

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch the repo's public key (needed to encrypt each secret)
        key_resp = await client.get(
            f"https://api.github.com/repos/{_GITHUB_REPO}/actions/public-key",
            headers=headers,
        )
        if key_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Could not fetch GitHub public key: {key_resp.status_code} {key_resp.text}",
            )
        key_data = key_resp.json()
        key_id = key_data["key_id"]
        public_key_bytes = base64.b64decode(key_data["key"])

        box = SealedBox(PublicKey(public_key_bytes))

        for secret_name, secret_value in secrets.items():
            encrypted_b64 = base64.b64encode(
                box.encrypt(secret_value.encode("utf-8"))
            ).decode("utf-8")

            put_resp = await client.put(
                f"https://api.github.com/repos/{_GITHUB_REPO}/actions/secrets/{secret_name}",
                headers=headers,
                json={"encrypted_value": encrypted_b64, "key_id": key_id},
            )
            if put_resp.status_code in (201, 204):
                saved.append(secret_name)
            else:
                _log.error("Failed to push secret %s: %s %s", secret_name, put_resp.status_code, put_resp.text)
                failed.append(secret_name)

    return {"saved": saved, "failed": failed}


# ── Run history ───────────────────────────────────────────────────────────────

@router.get("/{connector_id}/runs", response_model=ConnectorRunListResponse)
async def list_runs(
    connector_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    if connector.portfolio_id:
        await verify_portfolio_access(db, connector.portfolio_id, current_user["user_id"], current_user.get("org_id"))

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
async def get_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    run = await db.get(ConnectorRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.portfolio_id:
        await verify_portfolio_access(db, run.portfolio_id, current_user["user_id"], current_user.get("org_id"))
    return run


# ── File upload endpoint ──────────────────────────────────────────────────────

@router.post("/upload/")
async def upload_bank_statement(
    file: UploadFile = File(...),
    connector_id: UUID = Form(...),
    asset_id: Optional[str] = Form(None),  # required when requires_asset_selection_on_upload
    run_processors: bool = Form(default=True),  # set False for all but the last file in multi-upload
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept a statement file, parse it, write results.
    Routing and validation are driven entirely by CONNECTOR_REGISTRY — no
    hardcoded type lists. New connector types only need a registry entry.

    asset_id: required for connectors where requires_asset_selection_on_upload=True
              (e.g. btb_pdf). Ignored for auto_by_description connectors.
              Falls back to connector.config['asset_id'] for backward compatibility.
    """
    from app.connectors.connector_registry import get_connector_type

    connector = await db.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    await verify_portfolio_access(
        db, connector.portfolio_id,
        current_user["user_id"], current_user.get("org_id"),
        required_role="editor",
    )

    type_def = get_connector_type(connector.type)
    if not type_def or type_def.category != "manual_upload":
        raise HTTPException(
            status_code=400,
            detail=f"Connector type '{connector.type}' does not support file upload",
        )

    portfolio_id = connector.portfolio_id
    file_bytes = await file.read()
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in type_def.supported_file_types:
        allowed = ", ".join(f".{e}" for e in type_def.supported_file_types)
        raise HTTPException(
            status_code=400,
            detail=f"{connector.name} accepts {allowed} only",
        )

    # Resolve asset_id: form field wins; fall back to connector config for backward compat
    resolved_asset_id = asset_id
    if not resolved_asset_id and connector.config:
        config = decrypt_config(connector.config)
        resolved_asset_id = config.get("asset_id")

    if type_def.requires_asset_selection_on_upload and not resolved_asset_id:
        raise HTTPException(
            status_code=422,
            detail=f"asset_id is required for connector type '{connector.type}'. "
                   "Select the linked asset in the upload form.",
        )

    _log.info(
        "upload: connector_id=%s type=%s filename=%s asset_id=%s",
        connector_id, connector.type, filename, resolved_asset_id,
    )

    started_at = datetime.now(timezone.utc)

    # ── BTB PDF — upsert manual valuation + income transaction ────────────────
    if connector.type == "btb_pdf":
        try:
            from app.connectors.parsers.btb import parse_btb_pdf
            parsed = parse_btb_pdf(file_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Could not parse BTB report: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Failed to read PDF: {exc}") from exc

        _log.info(
            "BTB parsed: date=%s value=%.2f net_return=%.2f%%",
            parsed["report_date"], parsed["current_value"], parsed["net_return_pct"],
        )

        from app.models.transaction import Transaction
        from app.models.valuation import ManualValuation

        try:
            import uuid as _uuid
            btb_asset_id = _uuid.UUID(resolved_asset_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"Invalid asset_id: {resolved_asset_id!r}")

        report_date = parsed["report_date"]
        month_label = report_date.strftime("%B %Y")
        notes = (
            f"BTB {month_label} — "
            f"net return {parsed['net_return_pct']}%, "
            f"avg rate {parsed['avg_interest_rate']}%"
        )

        try:
            existing_val = (await db.execute(
                select(ManualValuation).where(
                    ManualValuation.asset_id == btb_asset_id,
                    ManualValuation.valuation_date == report_date,
                )
            )).scalar_one_or_none()

            if existing_val:
                existing_val.market_value = parsed["current_value"]
                existing_val.value_ils = parsed["current_value"]
                existing_val.source = "btb_pdf"
                existing_val.notes = notes
                valuation_action = "updated"
            else:
                db.add(ManualValuation(
                    portfolio_id=portfolio_id,
                    asset_id=btb_asset_id,
                    valuation_date=report_date,
                    market_value=parsed["current_value"],
                    currency="ILS",
                    fx_rate_to_ils=1.0,
                    value_ils=parsed["current_value"],
                    valuation_method="manual",
                    confidence_level="high",
                    source="btb_pdf",
                    notes=notes,
                ))
                valuation_action = "created"

            ext_ref = f"btb_{report_date.isoformat()}_monthly_income"
            existing_tx = (await db.execute(
                select(Transaction).where(Transaction.external_reference_id == ext_ref)
            )).scalar_one_or_none()

            if not existing_tx:
                income_amount = round(
                    parsed["last_month_return_pct"] * parsed["current_value"] / 100, 4
                )
                db.add(Transaction(
                    portfolio_id=portfolio_id,
                    asset_id=btb_asset_id,
                    transaction_date=report_date,
                    type="income",
                    economic_type="INCOME",
                    domain="alternatives",
                    total_amount=income_amount,
                    currency="ILS",
                    source="btb_pdf",
                    external_reference_id=ext_ref,
                    status="confirmed",
                ))
                tx_action = "created"
            else:
                tx_action = "skipped"

            await db.flush()

        except HTTPException:
            raise
        except Exception as exc:
            await db.rollback()
            _log.error("BTB DB error: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"DB write failed: {exc}") from exc

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
            records_fetched=1,
            valuations_created=1 if valuation_action == "created" else 0,
        )
        db.add(run)
        connector.last_run_at = finished_at
        connector.last_error = None
        await db.commit()

        _log.info("BTB upload done: valuation=%s tx=%s", valuation_action, tx_action)

        return {
            "connector_type": "btb_pdf",
            "connector_name": connector.name,
            "report_date": report_date.isoformat(),
            "current_value": parsed["current_value"],
            "net_invested": parsed["net_invested"],
            "last_month_return_pct": parsed["last_month_return_pct"],
            "net_return_pct": parsed["net_return_pct"],
            "avg_interest_rate": parsed["avg_interest_rate"],
            "gross_interest": parsed["gross_interest"],
            "tax_withheld": parsed["tax_withheld"],
            "mgmt_fee": parsed["mgmt_fee"],
            "valuation": valuation_action,
            "transaction": tx_action,
        }

    # ── Isracard XLSX — parse, insert raw_transactions, run BudgetProcessor ──────
    if connector.type == "isracard_xlsx":
        try:
            from app.connectors.parsers.isracard import parse_isracard_xlsx
            config = decrypt_config(connector.config) if connector.config else {}
            card_last4 = config.get("card_last4", "")
            parsed_rows = parse_isracard_xlsx(file_bytes, card_last4=card_last4)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Failed to parse Isracard file: {exc}") from exc

        from app.models.raw_layer import RawTransaction
        from app.utils.uuid7 import uuid7
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        raw_created = 0
        raw_skipped = 0
        min_date = None
        max_date = None
        total_ils = 0.0
        total_usd = 0.0

        for row in parsed_rows:
            stmt = pg_insert(RawTransaction).values(
                id=uuid7(),
                portfolio_id=portfolio_id,
                source="isracard_xlsx",
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
                raw_created += 1
                # Track date range and totals from newly inserted rows only
                row_date = row["raw_date"].date() if hasattr(row["raw_date"], "date") else row["raw_date"]
                if min_date is None or row_date < min_date:
                    min_date = row_date
                if max_date is None or row_date > max_date:
                    max_date = row_date
                amt = abs(float(row["amount"]))
                if row.get("currency") == "USD":
                    total_usd += amt
                else:
                    total_ils += amt
            else:
                raw_skipped += 1

        # Commit raw_transactions before running processors (they use a fresh session)
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
            records_fetched=len(parsed_rows),
            transactions_created=raw_created,
            transactions_skipped=raw_skipped,
        )
        db.add(run)
        connector.last_run_at = finished_at
        connector.last_error = None
        await db.commit()

        # Run BudgetProcessor only (credit card — no asset linking, no bank processor needed).
        # BudgetProcessor reads raw_transactions directly and classifies into budget_actuals.
        budget_classified = 0
        budget_needs_review = 0
        if run_processors:
            try:
                from app.processors.budget_processor import BudgetProcessor

                # .run() returns a ProcessorRun ORM object — use .rows_written (not .ai_classified)
                budget_run = await BudgetProcessor().run(
                    portfolio_id=portfolio_id,
                    triggered_by="manual_upload",
                )
                budget_classified = budget_run.rows_written or 0

                # Count needs_review from classification_log for today
                from app.database import AsyncSessionLocal
                from app.models.budget import ClassificationLog
                from app.models.raw_layer import RawTransaction as RT
                async with AsyncSessionLocal() as count_db:
                    from sqlalchemy import and_, func, select
                    today_start = started_at.replace(hour=0, minute=0, second=0, microsecond=0)
                    nr_q = (
                        select(func.count(ClassificationLog.id))
                        .join(RT, RT.id == ClassificationLog.raw_transaction_id)
                        .where(
                            and_(
                                RT.portfolio_id == portfolio_id,
                                RT.source == "isracard_xlsx",
                                ClassificationLog.needs_review == True,
                                ClassificationLog.processed_at >= today_start,
                            )
                        )
                    )
                    budget_needs_review = (await count_db.execute(nr_q)).scalar_one() or 0
                _log.info(
                    "Isracard budget processor: classified=%d needs_review=%d",
                    budget_classified, budget_needs_review,
                )
            except Exception as exc:
                _log.error("BudgetProcessor failed after Isracard upload: %s", exc, exc_info=True)

        _log.info(
            "Isracard upload done: raw=%d/%d budget_classified=%d needs_review=%d",
            raw_created, raw_skipped, budget_classified, budget_needs_review,
        )

        return {
            "connector_type": "isracard_xlsx",
            "connector_name": connector.name,
            # Backward-compat fields (shown in existing upload result UI)
            "created": raw_created,
            "skipped": raw_skipped,
            "total": len(parsed_rows),
            # Enhanced fields
            "raw_created": raw_created,
            "raw_skipped": raw_skipped,
            "budget_classified": budget_classified,
            "budget_needs_review": budget_needs_review,
            "date_range": (
                f"{min_date} to {max_date}"
                if min_date and max_date else "—"
            ),
            "total_ils": round(total_ils, 2),
            "total_usd": round(total_usd, 2),
        }

    # ── Bank connectors (fibi_bank, mizrachi_bank) — write to raw_transactions ─
    try:
        if connector.type == "mizrachi_bank":
            from app.connectors.parsers.mizrachi import parse_mizrachi_pdf
            rows = parse_mizrachi_pdf(file_bytes)

        else:  # fibi_bank
            if ext in ("xls", "xlsx"):
                import os as _os
                import tempfile
                from app.connectors.parsers.fibi import parse_fibi_xlsx
                with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name
                try:
                    parsed_fibi = parse_fibi_xlsx(tmp_path, str(portfolio_id))
                finally:
                    _os.unlink(tmp_path)
                rows = [_normalize_fibi_row(r) for r in parsed_fibi]
            else:  # pdf
                from app.connectors.parsers.fibi import parse_fibi_pdf
                rows = parse_fibi_pdf(file_bytes)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}") from exc

    from app.models.raw_layer import RawTransaction
    from app.utils.uuid7 import uuid7
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    created = 0
    skipped = 0
    for row in rows:
        stmt = pg_insert(RawTransaction).values(
            id=uuid7(),
            portfolio_id=portfolio_id,
            source=connector.type,
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
    connector.last_run_at = finished_at
    connector.last_error = None
    await db.commit()

    # Optionally skip processors (set run_processors=False for all but the last file
    # in a multi-file upload to avoid running the pipeline multiple times).
    if run_processors:
        try:
            from app.processors.bank_processor import BankProcessor
            from app.processors.budget_processor import BudgetProcessor
            # Step 1 — BankProcessor: raw_transactions → domain transactions
            await BankProcessor().run(
                portfolio_id=portfolio_id,
                triggered_by="manual_upload",
            )
            # Step 2 — BudgetProcessor: raw_transactions → budget_actuals
            await BudgetProcessor().run(
                portfolio_id=portfolio_id,
                triggered_by="manual_upload",
            )
        except Exception as exc:
            _log.warning("Post-upload processors failed: %s", exc)

    return {
        "connector_type": connector.type,
        "connector_name": connector.name,
        "created": created,
        "skipped": skipped,
        "total": len(rows),
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


# ── Manual report trigger ──────────────────────────────────────────────────────

@router.post("/send-daily-report/")
async def send_daily_report(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Manually trigger the daily notification report for all portfolios.
    Builds a ReportData snapshot from current DB state and delivers it
    to all configured channels (Telegram, etc.).
    """
    from datetime import date
    from app.models.portfolio import Portfolio
    from app.utils.daily_report import build_daily_report
    from app.utils.notification_router import deliver_report
    from sqlalchemy import select

    portfolios = (await db.execute(select(Portfolio))).scalars().all()
    if not portfolios:
        raise HTTPException(status_code=404, detail="No portfolios found")

    delivered = 0
    for portfolio in portfolios:
        report = await build_daily_report(db, portfolio.id, as_of=date.today())
        await deliver_report(report)
        delivered += 1

    return {"status": "ok", "portfolios": delivered}
