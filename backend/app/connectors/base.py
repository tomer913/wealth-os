"""
BaseConnector — interface all connectors must implement.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ConnectorResult:
    """Standardized result returned by every connector run."""
    records_fetched: int = 0
    transactions_created: int = 0
    transactions_skipped: int = 0
    valuations_created: int = 0
    assets_created: int = 0
    fx_rates_updated: int = 0
    prices_updated: int = 0
    checkpoint: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "records_fetched": self.records_fetched,
            "transactions_created": self.transactions_created,
            "transactions_skipped": self.transactions_skipped,
            "valuations_created": self.valuations_created,
            "assets_created": self.assets_created,
            "fx_rates_updated": self.fx_rates_updated,
            "prices_updated": self.prices_updated,
            "checkpoint": self.checkpoint,
        }


class BaseConnector(ABC):
    """
    Base class for all connectors.

    Each connector handles one external data source:
    - ECB FX rates
    - Yahoo Finance prices
    - Kraken trades
    - CEX.IO trades
    - IB CSV import
    etc.
    """

    # Override in subclass
    CONNECTOR_TYPE: str = "base"
    DISPLAY_NAME: str = "Base Connector"
    DESCRIPTION: str = ""
    # Fields required in config (shown in UI form)
    CONFIG_FIELDS: List[Dict[str, Any]] = []

    def __init__(
        self,
        config: Dict[str, Any],
        portfolio_id: UUID,
        asset_filter: Optional[List[str]],
        auto_create_assets: bool,
        db: AsyncSession,
    ):
        self.config = config
        self.portfolio_id = portfolio_id
        self.asset_filter = asset_filter  # None = fetch all
        self.auto_create_assets = auto_create_assets
        self.db = db

    @abstractmethod
    async def run(self) -> ConnectorResult:
        """
        Execute the connector. Must be implemented by all subclasses.
        Returns a ConnectorResult with counts and checkpoint.
        """
        ...

    def should_include_symbol(self, symbol: str) -> bool:
        """Check if this symbol should be processed based on asset_filter."""
        if self.asset_filter is None:
            return True
        return symbol in self.asset_filter

    async def resolve_or_create_asset(
        self, symbol: str, meta: Optional[Dict[str, Any]] = None
    ) -> Optional[UUID]:
        """
        Find an existing asset by symbol in this portfolio,
        or create a new one if auto_create_assets is enabled.
        Returns asset UUID or None.
        """
        from sqlalchemy import select
        from app.models.asset import Asset

        q = select(Asset).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.symbol == symbol,
        )
        asset = (await self.db.execute(q)).scalar_one_or_none()

        if asset:
            return asset.id

        if not self.auto_create_assets:
            return None

        # Auto-create with provided metadata or defaults
        new_asset = Asset(
            portfolio_id=self.portfolio_id,
            symbol=symbol,
            name=meta.get("name", symbol) if meta else symbol,
            category=meta.get("category") if meta else None,
            asset_behavior=meta.get("asset_behavior", "MARKET") if meta else "MARKET",
            currency=meta.get("currency", "USD") if meta else "USD",
            exchange=meta.get("exchange") if meta else None,
            sector=meta.get("sector") if meta else None,
            pricing_mode="market_price",
            is_manual=False,
            status="active",
        )
        self.db.add(new_asset)
        await self.db.flush()
        await self.db.refresh(new_asset)
        return new_asset.id
