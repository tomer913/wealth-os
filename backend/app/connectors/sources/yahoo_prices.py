"""
Yahoo Finance Price Connector
Fetches current prices for stocks, ETFs, and crypto.
Free, no API key required. Uses yfinance library.

Writes to:
  - asset.current_price        (hot cache — always updated)
  - asset_price_history        (one row per asset per date, ON CONFLICT DO NOTHING)

Does NOT write to raw_transactions — prices bypass the raw layer entirely.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register


# Symbol mapping: our symbol → Yahoo Finance symbol
SYMBOL_MAP = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}


def to_yahoo_symbol(symbol: str) -> str:
    if symbol in SYMBOL_MAP:
        return SYMBOL_MAP[symbol]
    if symbol.isdigit():
        return f"{symbol}.TA"
    return symbol


@register
class YahooPricesConnector(BaseConnector):
    CONNECTOR_TYPE = "yahoo_prices"
    DISPLAY_NAME = "Yahoo Finance Prices"
    DESCRIPTION = "Fetches current market prices for stocks, ETFs, and crypto. Free, no API key required."
    CONFIG_FIELDS = [
        {
            "key": "symbols",
            "label": "Symbols to fetch",
            "type": "text",
            "default": "",
            "hint": "Comma-separated. Leave empty to auto-fetch all MARKET assets in portfolio.",
        },
    ]

    async def run(self) -> ConnectorResult:
        result = ConnectorResult()

        symbols = await self._get_symbols()
        if not symbols:
            result.warnings.append("No MARKET assets found in portfolio")
            return result

        result.records_fetched = len(symbols)

        prices = await self._fetch_prices(symbols)

        today = date.today()
        for symbol, price_data in prices.items():
            updated = await self._update_asset_price(symbol, price_data, today)
            if updated:
                result.prices_updated += 1

        await self.db.flush()
        return result

    async def _get_symbols(self) -> List[str]:
        from app.models.asset import Asset

        config_symbols = self.config.get("symbols", "")
        if config_symbols:
            return [s.strip() for s in config_symbols.split(",") if s.strip()]

        q = select(Asset.symbol).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.asset_behavior == "MARKET",
            Asset.status == "active",
        )
        symbols = (await self.db.execute(q)).scalars().all()

        if self.asset_filter:
            symbols = [s for s in symbols if s in self.asset_filter]

        return list(symbols)

    async def _fetch_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError("yfinance not installed. Add 'yfinance' to requirements.txt")

        yahoo_symbols = {s: to_yahoo_symbol(s) for s in symbols}
        unique_yahoo = list(set(yahoo_symbols.values()))

        tickers = yf.Tickers(" ".join(unique_yahoo))

        results = {}
        reverse_map = {v: k for k, v in yahoo_symbols.items()}

        for yahoo_sym, internal_sym in reverse_map.items():
            try:
                ticker = tickers.tickers.get(yahoo_sym)
                if not ticker:
                    continue
                info = ticker.fast_info
                price = getattr(info, "last_price", None)
                currency = getattr(info, "currency", "USD")
                if price:
                    results[internal_sym] = {
                        "price": price,
                        "currency": currency,
                    }
            except Exception:
                pass

        return results

    async def _update_asset_price(self, symbol: str, price_data: Dict, today: date) -> bool:
        """
        Update asset.current_price (hot cache) and insert into asset_price_history
        (permanent record). Returns True if current_price was updated.
        """
        from app.models.asset import Asset
        from app.models.price_history import AssetPriceHistory
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        q = select(Asset).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.symbol == symbol,
        )
        asset = (await self.db.execute(q)).scalar_one_or_none()
        if not asset:
            return False

        price = Decimal(str(price_data["price"]))
        currency = price_data["currency"]

        # 1. Hot cache — always overwrite with latest price
        asset.current_price = price
        asset.price_updated_at = datetime.now(timezone.utc)

        # 2. Price history — one row per day, skip if already recorded
        stmt = pg_insert(AssetPriceHistory).values(
            asset_id=asset.id,
            portfolio_id=self.portfolio_id,
            price_date=today,
            price=price,
            currency=currency,
            source="yahoo",
        ).on_conflict_do_nothing(constraint="uq_asset_price_history")
        await self.db.execute(stmt)

        return True
