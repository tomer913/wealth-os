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


# Our symbol → Yahoo Finance ticker
YAHOO_SYMBOL_MAP: dict = {
    # Crypto
    "BTC":   "BTC-USD",
    "ETH":   "ETH-USD",
    "DOGE":  "DOGE-USD",
    "FLOKI": "FLOKI-USD",
    "PEPE":  "PEPE-USD",
    "INJ":   "INJ-USD",
    "GRT":   "GRT-USD",
    "SOL":   "SOL-USD",
    "ADA":   "ADA-USD",
    # ETFs — London Stock Exchange
    "VWRA":  "VWRA.L",
    "IB01":  "IB01.L",
    "IBO1":  "IB01.L",   # common typo variant
    # US stocks (same symbol)
    "MSFT":  "MSFT",
    "CSCO":  "CSCO",
    "AAPL":  "AAPL",
}

# Symbols to skip entirely — not on Yahoo Finance
SKIP_SYMBOLS: set = {
    "LUMI", "BABY",
    "TA90",                          # TASE, not on Yahoo
    "USD.ILS", "ILS.USD",            # FX — handled by ECB connector
    "MIGDAL_CASH", "IBI_CASH",       # FUND assets — no market price
    "MEITAV_CASH", "CASH_FIBI",
    "CASH_MIZRAHI",
}


def to_yahoo_symbol(symbol: str) -> str | None:
    """Map an internal symbol to a Yahoo Finance ticker, or None if it should be skipped."""
    if symbol in SKIP_SYMBOLS:
        return None
    if symbol in YAHOO_SYMBOL_MAP:
        return YAHOO_SYMBOL_MAP[symbol]
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
        import logging as _log
        log = _log.getLogger(__name__)

        config_symbols_raw = self.config.get("symbols", "")
        if config_symbols_raw:
            # Config may store a comma-string OR a list (depends on how it was saved)
            if isinstance(config_symbols_raw, list):
                raw_symbols = [str(s).strip() for s in config_symbols_raw if str(s).strip()]
            else:
                raw_symbols = [s.strip() for s in str(config_symbols_raw).split(",") if s.strip()]
            # Skip symbols that aren't on Yahoo
            symbols = [s for s in raw_symbols if s not in SKIP_SYMBOLS]
            skipped = set(raw_symbols) - set(symbols)
            if skipped:
                log.info("Skipping configured symbols not on Yahoo: %s", skipped)
            return symbols

        q = select(Asset.symbol).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.asset_behavior == "MARKET",
            Asset.status == "active",
        )
        all_symbols = (await self.db.execute(q)).scalars().all()

        symbols = [s for s in all_symbols if s not in SKIP_SYMBOLS]

        if self.asset_filter:
            symbols = [s for s in symbols if s in self.asset_filter]

        return list(symbols)

    async def _fetch_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        import logging as _log
        log = _log.getLogger(__name__)

        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError("yfinance not installed. Add 'yfinance' to requirements.txt")

        # Map internal symbol → Yahoo ticker, skip anything with no mapping
        yahoo_symbols: Dict[str, str] = {}
        for s in symbols:
            yahoo = to_yahoo_symbol(s)
            if yahoo is None:
                log.info("Skipping %s — not on Yahoo Finance", s)
                continue
            yahoo_symbols[s] = yahoo

        if not yahoo_symbols:
            return {}

        unique_yahoo = list(set(yahoo_symbols.values()))
        log.info("Fetching Yahoo prices for: %s", unique_yahoo)

        tickers = yf.Tickers(" ".join(unique_yahoo))

        results: Dict[str, Dict] = {}
        reverse_map = {v: k for k, v in yahoo_symbols.items()}

        for yahoo_sym, internal_sym in reverse_map.items():
            try:
                ticker = tickers.tickers.get(yahoo_sym)
                if not ticker:
                    log.warning("No ticker data for %s (%s)", yahoo_sym, internal_sym)
                    continue
                info = ticker.fast_info
                price = getattr(info, "last_price", None)
                currency = getattr(info, "currency", "USD")
                if price:
                    results[internal_sym] = {"price": price, "currency": currency}
                    log.debug("%s (%s): %s %s", internal_sym, yahoo_sym, price, currency)
                else:
                    log.warning("No price returned for %s (%s)", yahoo_sym, internal_sym)
            except Exception as exc:
                log.warning("Failed to fetch %s (%s): %s", yahoo_sym, internal_sym, exc)

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
