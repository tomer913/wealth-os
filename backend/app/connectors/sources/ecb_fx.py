"""
ECB FX Rates Connector
Fetches daily exchange rates via frankfurter.app (ECB data).
Free, no API key required.

Strategy: fetch USD/EUR/GBP rates with EUR as base,
then cross-calculate ILS rates using USD/ILS from Bank of Israel.
Simpler: just fetch with USD as base and get ILS directly.
"""
import httpx
from datetime import date
from decimal import Decimal

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register

# frankfurter.app supports EUR as base only for ECB data
# For USD base we use their API which supports many currencies
ECB_URL = "https://api.frankfurter.app/latest"


@register
class ECBFxConnector(BaseConnector):
    CONNECTOR_TYPE = "ecb_fx"
    DISPLAY_NAME = "ECB FX Rates"
    DESCRIPTION = "Fetches daily exchange rates. Free, no API key required."
    CONFIG_FIELDS = [
        {
            "key": "base_currency",
            "label": "Base currency",
            "type": "text",
            "default": "USD",
            "hint": "Base for rate calculation (USD recommended)",
        },
        {
            "key": "currencies",
            "label": "Target currencies",
            "type": "text",
            "default": "ILS,EUR,GBP",
            "hint": "Comma-separated list",
        },
    ]

    async def run(self) -> ConnectorResult:
        result = ConnectorResult()

        base = self.config.get("base_currency", "USD")
        currencies_str = self.config.get("currencies", "ILS,EUR,GBP")
        currencies = [c.strip() for c in currencies_str.split(",") if c.strip() != base]

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
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

    async def _upsert_fx_rate(self, from_currency, to_currency, rate, rate_date):
        from sqlalchemy import select
        from app.models.fx_rate import FXRate

        q = select(FXRate).where(
            FXRate.from_currency == from_currency,
            FXRate.to_currency == to_currency,
            FXRate.fx_date == rate_date,
        )
        print(f"DEBUG: [Connector] about to update from_currency: {from_currency}")
        existing = (await self.db.execute(q)).scalar_one_or_none()

        if existing:
            existing.rate = rate
            existing.source = "ecb"
            return False
        else:
            self.db.add(FXRate(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=rate,
                fx_date=rate_date,
                source="ecb",
            ))
            return True
