"""
main.py – Wealth OS FastAPI application.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    # Startup: nothing needed – Alembic manages schema
    yield
    # Shutdown: dispose async engine
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
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
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


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
