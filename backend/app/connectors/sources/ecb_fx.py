"""
ECB FX Rates Connector
Fetches daily exchange rates from the European Central Bank.
Free, no API key required.

Rates fetched: USD/ILS, GBP/ILS, EUR/ILS (and any others configured)
ECB publishes EUR-based rates — we cross-calculate via EUR.
"""
import httpx
from datetime import date, timezone, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register


ECB_URL = "https://api.frankfurter.app/latest"
# Using frankfurter.app — free, no auth, wraps ECB data


@register
class ECBFxConnector(BaseConnector):
    CONNECTOR_TYPE = "ecb_fx"
    DISPLAY_NAME = "ECB FX Rates"
    DESCRIPTION = "Fetches daily exchange rates from the European Central Bank. Free, no API key required."
    CONFIG_FIELDS = [
        {
            "key": "base_currency",
            "label": "Base currency",
            "type": "text",
            "default": "ILS",
            "hint": "All rates will be expressed as X per 1 ILS",
        },
        {
            "key": "currencies",
            "label": "Currencies to fetch",
            "type": "text",
            "default": "USD,EUR,GBP",
            "hint": "Comma-separated list",
        },
    ]

    async def run(self) -> ConnectorResult:
        result = ConnectorResult()

        base = self.config.get("base_currency", "ILS")
        currencies_str = self.config.get("currencies", "USD,EUR,GBP")
        currencies = [c.strip() for c in currencies_str.split(",")]

        # Fetch from Frankfurter (ECB data)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                ECB_URL,
                params={"from": base, "to": ",".join(currencies)},
            )
            response.raise_for_status()
            data = response.json()

        rates = data.get("rates", {})
        rate_date = date.fromisoformat(data.get("date", str(date.today())))

        result.records_fetched = len(rates)

        for currency, rate in rates.items():
            updated = await self._upsert_fx_rate(
                from_currency=base,
                to_currency=currency,
                rate=Decimal(str(rate)),
                rate_date=rate_date,
            )
            if updated:
                result.fx_rates_updated += 1

        await self.db.flush()
        result.checkpoint = {"last_date": str(rate_date)}
        return result

    async def _upsert_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
        rate_date: date,
    ) -> bool:
        """Insert or update FX rate. Returns True if a new record was created."""
        from app.models.fx_rate import FxRate

        # Check if rate for this date already exists
        q = select(FxRate).where(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.fx_date == rate_date,
        )
        existing = (await self.db.execute(q)).scalar_one_or_none()

        if existing:
            existing.rate = rate
            existing.source = "ecb"
            return False
        else:
            fx = FxRate(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=rate,
                fx_date=rate_date,
                source="ecb",
            )
            self.db.add(fx)
            return True
