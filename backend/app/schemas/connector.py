from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ── Connector schemas ─────────────────────────────────────────────────────────

class ConnectorCreate(BaseModel):
    name: str = Field(..., max_length=200)
    type: str = Field(..., max_length=50)
    config: Dict[str, Any] = Field(default_factory=dict)
    asset_filter: Optional[List[str]] = None
    auto_create_assets: bool = True
    schedule: str = Field("daily", max_length=50)
    is_active: bool = True


class ConnectorUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    asset_filter: Optional[List[str]] = None
    auto_create_assets: Optional[bool] = None
    schedule: Optional[str] = None
    is_active: Optional[bool] = None


class ConnectorRead(BaseModel):
    id: UUID
    portfolio_id: UUID
    name: str
    type: str
    # Safe config metadata: real keys + masked sensitive values for the edit form
    config_keys: List[str] = Field(default_factory=list)
    config_display: Optional[Dict[str, Any]] = None  # masked values for edit form
    asset_filter: Optional[List[str]] = None
    auto_create_assets: bool
    schedule: str
    is_active: bool
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Computed from latest run
    last_run_status: Optional[str] = None
    last_run_summary: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


# ── ConnectorRun schemas ──────────────────────────────────────────────────────

class ConnectorRunRead(BaseModel):
    id: UUID
    connector_id: UUID
    portfolio_id: UUID
    status: str
    triggered_by: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    records_fetched: Optional[int] = None
    transactions_created: Optional[int] = None
    transactions_skipped: Optional[int] = None
    valuations_created: Optional[int] = None
    assets_created: Optional[int] = None
    fx_rates_updated: Optional[int] = None
    prices_updated: Optional[int] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    checkpoint: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConnectorRunListResponse(BaseModel):
    items: List[ConnectorRunRead]
    total: int
    page: int
    limit: int
    pages: int


class TriggerRunResponse(BaseModel):
    run_id: UUID
    connector_id: UUID
    status: str
    message: str
