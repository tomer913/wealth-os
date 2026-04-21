"""
auth.py — Clerk JWT verification and portfolio access control.

When CLERK_JWKS_URL is not set (local dev), auth is bypassed
and a dev placeholder user is returned.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

log = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL")

# ── JWKS cache (1 hour TTL) ────────────────────────────────────────────────────
_jwks_cache: Optional[dict] = None
_jwks_fetched_at: Optional[datetime] = None


async def _get_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = datetime.now(timezone.utc)
    if (
        _jwks_cache is not None
        and _jwks_fetched_at is not None
        and (now - _jwks_fetched_at).total_seconds() < 3600
    ):
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(CLERK_JWKS_URL)  # type: ignore[arg-type]
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        log.info("JWKS refreshed from Clerk")
        return _jwks_cache


# ── get_current_user dependency ───────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    FastAPI dependency — returns {user_id, email, org_id}.

    Dev mode: if CLERK_JWKS_URL is not configured, returns a bypass user.
    Production: verifies Clerk JWT and returns claims.
    """
    if not CLERK_JWKS_URL:
        # Local dev — skip auth, return placeholder
        return {"user_id": "dev_user", "email": "dev@local", "org_id": None}

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        jwks = await _get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return {
            "user_id": payload.get("sub"),
            "email": payload.get("email"),
            "org_id": payload.get("org_id"),
        }
    except JWTError as exc:
        log.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Role hierarchy ────────────────────────────────────────────────────────────

_ROLE_RANK = {"viewer": 0, "editor": 1, "owner": 2}


# ── verify_portfolio_access helper ────────────────────────────────────────────

async def verify_portfolio_access(
    db: AsyncSession,
    portfolio_id: UUID,
    user_id: str,
    org_id: Optional[str] = None,
    required_role: str = "viewer",
):
    """
    Verify portfolio access via portfolio_members table.

    Dev mode: only checks existence (no auth).
    Production: user must be in portfolio_members with >= required_role.
    org_id support: org members also checked.

    required_role: "viewer" (default), "editor", or "owner".
    """
    from app.models.portfolio import Portfolio
    from app.models.portfolio_member import PortfolioMember

    if not CLERK_JWKS_URL:
        portfolio = await db.get(Portfolio, portfolio_id)
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        return portfolio

    user_ids = [user_id]
    if org_id:
        user_ids.append(org_id)

    min_rank = _ROLE_RANK.get(required_role, 0)

    q = (
        select(Portfolio)
        .join(PortfolioMember, PortfolioMember.portfolio_id == Portfolio.id)
        .where(
            Portfolio.id == portfolio_id,
            PortfolioMember.user_id.in_(user_ids),
        )
    )
    if min_rank >= 2:
        q = q.where(PortfolioMember.role == "owner")
    elif min_rank >= 1:
        q = q.where(PortfolioMember.role.in_(["editor", "owner"]))

    result = await db.execute(q)
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Portfolio not found or access denied",
        )
    return portfolio
