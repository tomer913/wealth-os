"""
BaseConnector — interface all connectors must implement.

Architecture:
  - Subclasses implement fetch() which returns a list of raw row dicts.
  - The base run() method writes those rows to raw_transactions (dedup via
    external_ref_id + source unique constraint) and returns a ConnectorResult.
  - Non-bank connectors (FX, prices, IB) that still write directly to domain
    tables override run() directly as before.
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

    Bank-style connectors implement fetch() and get the run() logic for free.
    Other connectors (FX, prices, IB) override run() directly.
    """

    # Override in subclass
    CONNECTOR_TYPE: str = "base"
    DISPLAY_NAME: str = "Base Connector"
    DESCRIPTION: str = ""
    CONFIG_FIELDS: List[Dict[str, Any]] = []

    # Set to True in bank-style connectors that use fetch() + raw_transactions
    WRITES_RAW: bool = False
    # Source name written to raw_transactions.source (defaults to CONNECTOR_TYPE)
    RAW_SOURCE: str = ""

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
        self.asset_filter = asset_filter
        self.auto_create_assets = auto_create_assets
        self.db = db

    async def run(self) -> ConnectorResult:
        """
        Default implementation for WRITES_RAW connectors:
        calls fetch() and upserts rows into raw_transactions.
        Non-raw connectors must override this method.
        """
        if not self.WRITES_RAW:
            raise NotImplementedError(
                f"{self.__class__.__name__} must override run() or set WRITES_RAW=True"
            )
        return await self._run_raw()

    async def _run_raw(self) -> ConnectorResult:
        """Fetch rows and write to raw_transactions with dedup."""
        from datetime import datetime, timezone
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.models.raw_layer import RawTransaction
        from app.utils.uuid7 import uuid7

        source = self.RAW_SOURCE or self.CONNECTOR_TYPE

        rows = await self.fetch()
        created = 0
        skipped = 0

        for row in rows:
            stmt = pg_insert(RawTransaction).values(
                id=uuid7(),
                portfolio_id=self.portfolio_id,
                source=source,
                raw_date=row["raw_date"],
                description=row["description"],
                amount=row["amount"],
                currency=row["currency"],
                reference=row.get("reference"),
                extra_raw=row.get("extra_raw"),
                external_ref_id=row["external_ref_id"],
                imported_at=datetime.now(timezone.utc),
            ).on_conflict_do_nothing(
                constraint="uq_raw_transactions_source_ref"
            )
            result = await self.db.execute(stmt)
            if result.rowcount:
                created += 1
            else:
                skipped += 1

        await self.db.commit()

        return ConnectorResult(
            records_fetched=len(rows),
            transactions_created=created,
            transactions_skipped=skipped,
        )

    async def fetch(self) -> List[Dict[str, Any]]:
        """
        Bank-style connectors implement this.
        Returns list of dicts with keys:
          raw_date, description, amount, currency, reference,
          external_ref_id, extra_raw (optional)
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement fetch()"
        )

    def should_include_symbol(self, symbol: str) -> bool:
        if self.asset_filter is None:
            return True
        return symbol in self.asset_filter

    async def resolve_or_create_asset(
        self, symbol: str, meta: Optional[Dict[str, Any]] = None
    ) -> Optional[UUID]:
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
