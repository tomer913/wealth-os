"""
Yahoo Finance Price Connector
Fetches current prices for stocks, ETFs, and crypto.
Free, no API key required. Uses yfinance library.

Updates asset.current_price in the assets table.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register


# Symbol mapping: our symbol → Yahoo Finance symbol
# Add mappings here for TASE securities and non-standard symbols
SYMBOL_MAP = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    # TASE securities use .TA suffix on Yahoo
    # e.g. "1143783": "1143783.TA"
}


def to_yahoo_symbol(symbol: str) -> str:
    """Convert internal symbol to Yahoo Finance format."""
    if symbol in SYMBOL_MAP:
        return SYMBOL_MAP[symbol]
    # TASE numeric securities
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

        # Get symbols to fetch
        symbols = await self._get_symbols()
        if not symbols:
            result.warnings.append("No MARKET assets found in portfolio")
            return result

        result.records_fetched = len(symbols)

        # Fetch prices using yfinance
        prices = await self._fetch_prices(symbols)

        # Update asset prices in DB
        for symbol, price_data in prices.items():
            updated = await self._update_asset_price(symbol, price_data)
            if updated:
                result.prices_updated += 1

        await self.db.flush()
        return result

    async def _get_symbols(self) -> List[str]:
        """Get list of symbols to fetch — from config or auto-discover from portfolio."""
        from app.models.asset import Asset

        # If config has explicit symbols, use those
        config_symbols = self.config.get("symbols", "")
        if config_symbols:
            return [s.strip() for s in config_symbols.split(",") if s.strip()]

        # Auto-discover all MARKET assets in this portfolio
        q = select(Asset.symbol).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.asset_behavior == "MARKET",
            Asset.status == "active",
        )
        symbols = (await self.db.execute(q)).scalars().all()

        # Apply asset_filter if set
        if self.asset_filter:
            symbols = [s for s in symbols if s in self.asset_filter]

        return list(symbols)

    async def _fetch_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch prices from Yahoo Finance. Returns {symbol: {price, currency, name}}"""
        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError(
                "yfinance not installed. Add 'yfinance' to requirements.txt"
            )

        # Map to Yahoo symbols
        yahoo_symbols = {s: to_yahoo_symbol(s) for s in symbols}
        unique_yahoo = list(set(yahoo_symbols.values()))

        # Batch download
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
                pass  # Skip failed symbols, don't fail entire run

        return results

    async def _update_asset_price(
        self, symbol: str, price_data: Dict
    ) -> bool:
        """Update asset.current_price. Returns True if updated."""
        from datetime import datetime, timezone
        from app.models.asset import Asset

        q = select(Asset).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.symbol == symbol,
        )
        asset = (await self.db.execute(q)).scalar_one_or_none()
        if not asset:
            return False

        asset.current_price = Decimal(str(price_data["price"]))
        asset.price_updated_at = datetime.now(timezone.utc)
        return True
