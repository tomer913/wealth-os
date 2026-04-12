"""
scheduler.py — Daily ETL scheduler for Wealth OS.

Uses APScheduler with AsyncIOScheduler.
Runs inside the FastAPI process — extractable to a separate service later.

Daily chain (Israel time):
  07:00 — Run all active connectors (FX rates, prices, bank raw import)
  07:05 — Run BankProcessor for all portfolios (classify raw → transactions)
  07:10 — Rebuild snapshot for each portfolio
"""
import logging
from datetime import datetime, timezone, date
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)

# Single scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Asia/Jerusalem")
    return _scheduler


def start_scheduler():
    """Start the scheduler and register all jobs. Called at app startup."""
    scheduler = get_scheduler()

    # 07:00 — Run all active connectors
    scheduler.add_job(
        run_connectors,
        trigger=CronTrigger(hour=7, minute=0, timezone="Asia/Jerusalem"),
        id="daily_connectors",
        name="Daily connectors — raw import",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 07:05 — Run BankProcessor for all portfolios
    scheduler.add_job(
        run_bank_processors,
        trigger=CronTrigger(hour=7, minute=5, timezone="Asia/Jerusalem"),
        id="daily_bank_processor",
        name="Daily bank processor — classify raw → transactions",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 07:10 — Rebuild snapshot for each portfolio
    scheduler.add_job(
        run_snapshots,
        trigger=CronTrigger(hour=7, minute=10, timezone="Asia/Jerusalem"),
        id="daily_snapshots",
        name="Daily snapshots — rebuild portfolio snapshots",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    log.info(
        "Scheduler started — 07:00 connectors, 07:05 bank processor, "
        "07:10 snapshots (Asia/Jerusalem)"
    )


def stop_scheduler():
    """Stop the scheduler gracefully. Called at app shutdown."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")


async def run_connectors():
    """
    07:00 job — Run all active connectors.
    FX rates first, then prices, then bank raw importers.
    Returns the set of portfolio IDs that had connectors run.
    """
    log.info("=== Connectors started at %s ===", datetime.now(timezone.utc).isoformat())

    from app.database import AsyncSessionLocal
    from app.models.connector import Connector
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        q = select(Connector).where(
            Connector.is_active == True,
            Connector.schedule.in_(["daily", "hourly"]),
        ).order_by(Connector.portfolio_id, Connector.type)

        connectors = (await db.execute(q)).scalars().all()

        if not connectors:
            log.info("No active connectors found — skipping")
            return set()

        log.info("Found %d active connectors", len(connectors))

        TYPE_ORDER = {
            "ecb_fx": 0,
            "yahoo_prices": 1,
            "tase_prices": 2,
            "kraken": 3,
            "cexio": 4,
            "ib_flex": 5,
            "mizrachi_bank": 6,
            "fibi_bank": 7,
            "leumi_bank": 8,
        }
        sorted_connectors = sorted(connectors, key=lambda c: TYPE_ORDER.get(c.type, 99))

        portfolios_updated = set()
        success_count = 0
        fail_count = 0

        for connector in sorted_connectors:
            try:
                log.info("Running connector: %s (%s)", connector.name, connector.type)
                await _run_single_connector(connector.id)
                portfolios_updated.add(connector.portfolio_id)
                success_count += 1
            except Exception as e:
                log.error("Connector %s failed: %s", connector.name, e)
                fail_count += 1

        log.info("Connectors complete — %d success, %d failed", success_count, fail_count)
        return portfolios_updated


async def run_bank_processors():
    """
    07:05 job — Run BankProcessor for all portfolios.
    """
    log.info("=== BankProcessor started at %s ===", datetime.now(timezone.utc).isoformat())

    from app.database import AsyncSessionLocal
    from app.models.portfolio import Portfolio
    from app.processors.bank_processor import BankProcessor
    from sqlalchemy import select

    processor = BankProcessor()

    async with AsyncSessionLocal() as db:
        portfolios = (await db.execute(select(Portfolio))).scalars().all()

    for portfolio in portfolios:
        try:
            log.info("BankProcessor running for portfolio %s", portfolio.id)
            await processor.run(portfolio.id, triggered_by="scheduler")
        except Exception as e:
            log.error("BankProcessor failed for portfolio %s: %s", portfolio.id, e)

    log.info("=== BankProcessor complete ===")


async def run_snapshots(portfolio_ids=None):
    """
    07:10 job — Rebuild snapshot for each portfolio.
    If portfolio_ids is None, rebuilds all portfolios.
    """
    log.info("=== Snapshots started at %s ===", datetime.now(timezone.utc).isoformat())

    if portfolio_ids is None:
        from app.database import AsyncSessionLocal
        from app.models.portfolio import Portfolio
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            portfolios = (await db.execute(select(Portfolio))).scalars().all()
            portfolio_ids = [p.id for p in portfolios]

    for portfolio_id in portfolio_ids:
        try:
            log.info("Rebuilding snapshot for portfolio %s", portfolio_id)
            await _rebuild_portfolio_snapshot(portfolio_id)
        except Exception as e:
            log.error("Snapshot rebuild failed for portfolio %s: %s", portfolio_id, e)

    log.info("=== Snapshots complete ===")


async def run_daily_etl():
    """
    Full daily ETL — connectors → bank processor → snapshots.
    Called by manual trigger endpoint.
    """
    log.info("=== Daily ETL started at %s ===", datetime.now(timezone.utc).isoformat())
    portfolios_updated = await run_connectors()
    await run_bank_processors()
    await run_snapshots(list(portfolios_updated) if portfolios_updated else None)
    log.info("=== Daily ETL complete ===")


async def _run_single_connector(connector_id):
    """Run a single connector by ID. Reuses existing router logic."""
    import uuid
    import traceback
    from datetime import datetime, timezone
    from app.database import AsyncSessionLocal
    from app.models.connector import Connector, ConnectorRun
    from app.utils.encryption import decrypt_config
    from app.connectors.registry import get_connector_handler

    async with AsyncSessionLocal() as db:
        connector = await db.get(Connector, connector_id)
        if not connector:
            raise ValueError(f"Connector {connector_id} not found")

        # Create run record
        run = ConnectorRun(
            id=uuid.uuid4(),
            connector_id=connector_id,
            portfolio_id=connector.portfolio_id,
            status="running",
            triggered_by="scheduler",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        try:
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

            finished = datetime.now(timezone.utc)
            run.status = "success"
            run.finished_at = finished
            run.duration_ms = int((finished - run.started_at).total_seconds() * 1000)
            run.records_fetched = result.get("records_fetched", 0)
            run.transactions_created = result.get("transactions_created", 0)
            run.transactions_skipped = result.get("transactions_skipped", 0)
            run.assets_created = result.get("assets_created", 0)
            run.fx_rates_updated = result.get("fx_rates_updated", 0)
            run.prices_updated = result.get("prices_updated", 0)
            run.checkpoint = result.get("checkpoint")

            connector.last_run_at = finished
            connector.last_error = None
            await db.commit()

            log.info(
                "  ✓ %s — %dms, txns: +%d, prices: +%d, fx: +%d",
                connector.name,
                run.duration_ms,
                run.transactions_created or 0,
                run.prices_updated or 0,
                run.fx_rates_updated or 0,
            )

        except Exception as e:
            await db.rollback()
            async with AsyncSessionLocal() as err_db:
                run = await err_db.get(ConnectorRun, run.id)
                connector = await err_db.get(Connector, connector_id)
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
            raise


async def _rebuild_portfolio_snapshot(portfolio_id):
    """Trigger snapshot rebuild for a portfolio after connectors run."""
    import asyncio
    from app.routers.snapshots import _run_rebuild

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        _run_rebuild,
        portfolio_id,
        date.today(),
        None,
    )
    log.info(
        "  ✓ Snapshot rebuilt — value: ₪%s, assets: %d",
        f"{result['summary']['total_value_ils']:,.0f}",
        result['summary']['asset_count'],
    )
    return result


async def trigger_manual_etl(portfolio_id=None):
    """
    Manually trigger the ETL job outside the schedule.
    Called from API endpoint for testing or manual runs.
    """
    log.info("Manual ETL triggered for portfolio: %s", portfolio_id or "all")
    await run_daily_etl()
