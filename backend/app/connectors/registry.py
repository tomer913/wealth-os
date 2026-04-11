"""
Connector registry — maps connector type strings to handler classes.
Add new connectors here as they're built.
"""
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import BaseConnector, ConnectorResult


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Type[BaseConnector]] = {}


def register(cls: Type[BaseConnector]) -> Type[BaseConnector]:
    """Decorator to register a connector class."""
    _REGISTRY[cls.CONNECTOR_TYPE] = cls
    return cls


def get_connector_class(connector_type: str) -> Optional[Type[BaseConnector]]:
    """Get connector class by type string."""
    return _REGISTRY.get(connector_type)


def list_connector_types() -> List[Dict[str, Any]]:
    """Return list of available connector types for UI display."""
    return [
        {
            "type": cls.CONNECTOR_TYPE,
            "display_name": cls.DISPLAY_NAME,
            "description": cls.DESCRIPTION,
            "config_fields": cls.CONFIG_FIELDS,
        }
        for cls in _REGISTRY.values()
    ]


async def get_connector_handler(
    connector_type: str,
) -> Optional["ConnectorHandler"]:
    """Get a callable handler for a connector type."""
    cls = get_connector_class(connector_type)
    if not cls:
        return None
    return ConnectorHandler(cls)


class ConnectorHandler:
    """Wraps a connector class to provide a standard run() interface."""

    def __init__(self, cls: Type[BaseConnector]):
        self.cls = cls

    async def run(
        self,
        config: Dict[str, Any],
        portfolio_id: UUID,
        asset_filter: Optional[List[str]],
        auto_create_assets: bool,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        instance = self.cls(
            config=config,
            portfolio_id=portfolio_id,
            asset_filter=asset_filter,
            auto_create_assets=auto_create_assets,
            db=db,
        )
        result = await instance.run()
        return result.to_dict()


# ── Import all connectors to trigger registration ─────────────────────────────
# Add imports here as new connectors are built

from app.connectors.sources import ecb_fx  # noqa: E402, F401
from app.connectors.sources import yahoo_prices  # noqa: E402, F401
from app.connectors.sources import ib_flex  # noqa: E402, F401
