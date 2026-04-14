"""
ECB FX Rates Connector
Fetches daily exchange rates via frankfurter.app (ECB data).
Free, no API key required.

Fetches last 30 days of rates and inserts one row per date per currency pair.
ON CONFLICT DO NOTHING — historical rates are never overwritten.
"""
import httpx
from datetime import date, timedelta
from decimal import Decimal

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register

# Range endpoint: GET /start_date..end_date?from=USD&to=ILS,EUR,GBP
# Response: { "rates": { "2025-03-01": { "ILS": 3.65, ... }, ... } }
ECB_RANGE_URL = "https://api.frankfurter.app/{start}..{end}"


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
        targets = [c.strip() for c in currencies_str.split(",") if c.strip() and c.strip() != base]

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        url = ECB_RANGE_URL.format(start=start_date, end=end_date)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, params={"from": base, "to": ",".join(targets)})
            response.raise_for_status()
            data = response.json()

        # data["rates"] = { "2025-03-01": { "ILS": 3.65, "EUR": 0.92 }, ... }
        rates_by_date = data.get("rates", {})
        result.records_fetched = sum(len(v) for v in rates_by_date.values())

        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.models.fx_rate import FXRate

        last_date = None
        for date_str, rate_map in sorted(rates_by_date.items()):
            rate_date = date.fromisoformat(date_str)
            last_date = rate_date

            for currency, rate in rate_map.items():
                stmt = (
                    pg_insert(FXRate)
                    .values(
                        from_currency=base,
                        to_currency=currency,
                        rate=Decimal(str(rate)),
                        fx_date=rate_date,
                        source="ecb",
                    )
                    .on_conflict_do_nothing(constraint="uq_fx_rate")
                )
                res = await self.db.execute(stmt)
                if res.rowcount:
                    result.fx_rates_updated += 1

        await self.db.flush()
        if last_date:
            result.checkpoint = {"last_date": str(last_date)}
        return result
