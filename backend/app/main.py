"""
main.py – Wealth OS FastAPI application.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import connectors as connectors_router
from app.connectors import registry as connector_registry

from app.config import settings
from app.routers import (
    accounts,
    assets,
    dashboard,
    portfolios,
    snapshots,
    transactions,
    valuations,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    from app.scheduler import start_scheduler
    start_scheduler()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    from app.scheduler import stop_scheduler
    stop_scheduler()

    from app.database import async_engine
    await async_engine.dispose()


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(portfolios.router, prefix="/api/v1")
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(assets.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(valuations.router, prefix="/api/v1")
app.include_router(snapshots.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(connectors_router.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/api/v1/connector-types")
async def list_connector_types():
    return connector_registry.list_connector_types()


@app.post("/api/v1/scheduler/run-now")
async def trigger_etl_now():
    """Manually trigger the daily ETL job immediately. Useful for testing."""
    from app.scheduler import trigger_manual_etl
    import asyncio
    asyncio.create_task(trigger_manual_etl())
    return {"status": "triggered", "message": "ETL job started in background"}


@app.get("/api/v1/scheduler/status")
async def scheduler_status():
    """Check scheduler status and next run time."""
    from app.scheduler import get_scheduler
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return {
        "running": scheduler.running,
        "jobs": jobs,
    }
