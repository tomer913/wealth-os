"""
Kraken Crypto Exchange Connector

Fetches:
  - Trade history  → raw_transactions (dedup on external_ref_id)
  - Balances       → asset.extra_data quantity update / auto-create assets
  - Live prices    → asset.current_price + asset_price_history

Authentication: HMAC-SHA512 via API-Key + API-Sign headers.
Rate limit: 1 req/s for private endpoints (enforced with asyncio.sleep).
"""
import asyncio
import base64
import hashlib
import hmac
import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register
from app.utils.uuid7 import uuid7

log = logging.getLogger(__name__)

KRAKEN_BASE = "https://api.kraken.com"

# Kraken internal asset codes → canonical symbol
KRAKEN_ASSET_MAP: Dict[str, str] = {
    "XXBT": "BTC", "XBT": "BTC",
    "XETH": "ETH", "ETH": "ETH",
    "XLTC": "LTC", "LTC": "LTC",
    "XXRP": "XRP", "XRP": "XRP",
    "ADA":  "ADA",
    "SOL":  "SOL",
    "DOT":  "DOT",
    "MATIC":"MATIC",
    "LINK": "LINK",
    "UNI":  "UNI",
    "AVAX": "AVAX",
    "ATOM": "ATOM",
    "ALGO": "ALGO",
}

# Kraken quote codes → ISO currency
KRAKEN_QUOTE_MAP: Dict[str, str] = {
    "ZUSD": "USD", "USD": "USD",
    "ZEUR": "EUR", "EUR": "EUR",
    "ZGBP": "GBP", "GBP": "GBP",
    "ZCAD": "CAD", "CAD": "CAD",
}

# Kraken symbol → public pair for Ticker endpoint
KRAKEN_TICKER_PAIRS: Dict[str, str] = {
    "BTC":   "XXBTZUSD",
    "ETH":   "XETHZUSD",
    "LTC":   "XLTCZUSD",
    "XRP":   "XXRPZUSD",
    "ADA":   "ADAUSD",
    "SOL":   "SOLUSD",
    "DOT":   "DOTUSD",
    "MATIC": "MATICUSD",
    "LINK":  "LINKUSD",
    "UNI":   "UNIUSD",
    "AVAX":  "AVAXUSD",
    "ATOM":  "ATOMUSD",
    "ALGO":  "ALGOUSD",
}

# Skip fiat and stablecoins in balance fetch
KRAKEN_SKIP_ASSETS = {
    "ZUSD", "ZEUR", "ZGBP", "ZCAD", "USDT", "USDC", "DAI", "KFEE",
    "USD", "EUR", "GBP", "CAD",
}


def _kraken_sign(api_secret: str, endpoint: str, nonce: str, post_data: str) -> str:
    """Generate Kraken HMAC-SHA512 signature."""
    message = endpoint.encode() + hashlib.sha256(
        (nonce + post_data).encode()
    ).digest()
    return base64.b64encode(
        hmac.new(
            base64.b64decode(api_secret),
            message,
            hashlib.sha512,
        ).digest()
    ).decode()


def _parse_pair(pair: str) -> tuple[str, str]:
    """
    Decompose a Kraken pair string into (base_symbol, quote_currency).
    e.g. "XXBTZUSD" → ("BTC", "USD"), "ADAUSD" → ("ADA", "USD")
    """
    # Try 4-char prefix first (e.g. XXBT, XETH), then 3-char (e.g. ADA, SOL)
    for prefix_len in (4, 3):
        prefix = pair[:prefix_len]
        if prefix in KRAKEN_ASSET_MAP:
            base = KRAKEN_ASSET_MAP[prefix]
            quote_raw = pair[prefix_len:]
            quote = KRAKEN_QUOTE_MAP.get(quote_raw, quote_raw[-3:] if len(quote_raw) >= 3 else quote_raw)
            return base, quote
    # Fallback: assume last 3 chars are quote currency
    return pair[:-3], pair[-3:]


@register
class KrakenConnector(BaseConnector):
    CONNECTOR_TYPE = "kraken"
    DISPLAY_NAME = "Kraken"
    DESCRIPTION = "Fetches trade history, balances, and live prices from Kraken crypto exchange."
    CONFIG_FIELDS = [
        {
            "key": "api_key",
            "label": "API Key",
            "type": "text",
            "default": "",
            "hint": "Get API keys at kraken.com/u/security/api — needs: Query Funds, Query Ledger Entries",
        },
        {
            "key": "api_secret",
            "label": "API Secret",
            "type": "password",
            "default": "",
            "hint": "The private key shown once when creating the API key",
        },
        {
            "key": "account_id",
            "label": "Account ID",
            "type": "text",
            "default": "",
            "hint": "UUID of the account to assign trades to (from Accounts page)",
        },
    ]

    # ── Public entry point ─────────────────────────────────────────────────────

    async def run(self) -> ConnectorResult:
        result = ConnectorResult()

        # ── Credential diagnostics ────────────────────────────────────────────
        log.info("Kraken connector starting — config keys present: %s", list(self.config.keys()))
        api_key = self.config.get("api_key", "")
        api_secret = self.config.get("api_secret", "")
        log.info("Kraken has api_key: %s  has api_secret: %s  key_prefix: %s",
                 bool(api_key), bool(api_secret),
                 (api_key[:8] + "...") if api_key else "<empty>")

        if not api_key or not api_secret:
            msg = "Kraken: api_key and api_secret are required — check that CONNECTOR_ENCRYPTION_KEY matches and credentials were saved"
            log.error(msg)
            result.warnings.append(msg)
            return result

        try:
            await self._fetch_trades(api_key, api_secret, result)
            await asyncio.sleep(1)
            await self._fetch_balances(api_key, api_secret, result)
            await asyncio.sleep(1)
            await self._fetch_prices(result)
            await self.db.flush()
        except Exception as exc:
            log.exception("Kraken connector failed: %s", exc)
            result.warnings.append(f"Kraken error: {exc}")

        log.info("Kraken run finished — fetched=%d created=%d skipped=%d prices=%d",
                 result.records_fetched, result.transactions_created,
                 result.transactions_skipped, result.prices_updated)
        return result

    # ── Private API helper ─────────────────────────────────────────────────────

    async def _private_post(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        api_secret: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        nonce = str(int(time.time() * 1000))
        post_params: Dict[str, Any] = {"nonce": nonce, **(params or {})}
        post_data = urlencode(post_params)
        signature = _kraken_sign(api_secret, endpoint, nonce, post_data)

        resp = await client.post(
            f"{KRAKEN_BASE}{endpoint}",
            content=post_data,
            headers={
                "API-Key": api_key,
                "API-Sign": signature,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Kraken API error: {data['error']}")
        return data.get("result", {})

    # ── Trade history ──────────────────────────────────────────────────────────

    async def _fetch_trades(
        self, api_key: str, api_secret: str, result: ConnectorResult
    ) -> None:
        from app.models.raw_layer import RawTransaction
        from app.models.connector import ConnectorRun
        from app.models.connector import Connector

        # Read checkpoint from last successful run
        last_trade_time: Optional[float] = None
        ckpt_q = (
            select(ConnectorRun)
            .join(Connector, ConnectorRun.connector_id == Connector.id)
            .where(
                ConnectorRun.portfolio_id == self.portfolio_id,
                Connector.type == self.CONNECTOR_TYPE,
                ConnectorRun.status == "success",
                ConnectorRun.checkpoint.isnot(None),
            )
            .order_by(ConnectorRun.created_at.desc())
            .limit(1)
        )
        last_run = (await self.db.execute(ckpt_q)).scalar_one_or_none()
        if last_run and last_run.checkpoint:
            last_trade_time = last_run.checkpoint.get("last_trade_time")

        account_id_str = self.config.get("account_id")
        account_id = UUID(account_id_str) if account_id_str else None
        newest_trade_time: Optional[float] = last_trade_time

        async with httpx.AsyncClient(timeout=30) as client:
            offset = 0
            while True:
                params: Dict[str, Any] = {"ofs": offset}
                if last_trade_time:
                    params["start"] = int(last_trade_time) + 1

                await asyncio.sleep(1)  # Kraken rate limit
                log.info("Calling Kraken TradesHistory API (offset=%d, start=%s)...",
                         offset, params.get("start"))
                data = await self._private_post(
                    client, api_key, api_secret, "/0/private/TradesHistory", params
                )
                log.info("Kraken TradesHistory response keys: %s", list(data.keys()))

                trades: Dict[str, Any] = data.get("trades", {})
                if not trades:
                    break

                result.records_fetched += len(trades)

                for trade_id, trade in trades.items():
                    base_sym, quote_cur = _parse_pair(trade.get("pair", ""))
                    trade_ts = float(trade.get("time", 0))
                    trade_dt = datetime.fromtimestamp(trade_ts, tz=timezone.utc)
                    trade_type = trade.get("type", "buy")
                    cost = float(trade.get("cost", 0))
                    vol = float(trade.get("vol", 0))
                    price = float(trade.get("price", 0))
                    fee = float(trade.get("fee", 0))

                    # Sign: BUY = money out (negative), SELL = money in (positive)
                    amount = -cost if trade_type == "buy" else cost

                    if newest_trade_time is None or trade_ts > newest_trade_time:
                        newest_trade_time = trade_ts

                    # Resolve or auto-create asset
                    asset_id: Optional[UUID] = None
                    if self.should_include_symbol(base_sym):
                        asset_id = await self.resolve_or_create_asset(
                            base_sym,
                            meta={
                                "name": f"{base_sym} (Kraken)",
                                "category": "crypto",
                                "asset_behavior": "MARKET",
                                "currency": "USD",
                            },
                        )
                        if asset_id and not account_id:
                            # if no explicit account, store None (will link later)
                            pass

                    stmt = (
                        pg_insert(RawTransaction)
                        .values(
                            id=uuid7(),
                            portfolio_id=self.portfolio_id,
                            source="kraken",
                            raw_date=trade_dt,
                            description=f"Kraken {trade_type.upper()} {vol} {base_sym} @ {price} {quote_cur}",
                            amount=amount,
                            currency=quote_cur,
                            reference=trade.get("ordertxid"),
                            external_ref_id=f"KRAKEN-{trade_id}",
                            extra_raw={
                                "trade_id": trade_id,
                                "pair": trade.get("pair"),
                                "type": trade_type,
                                "vol": str(vol),
                                "price": str(price),
                                "cost": str(cost),
                                "fee": str(fee),
                                "symbol": base_sym,
                                "account_id": str(account_id) if account_id else None,
                            },
                            imported_at=datetime.now(timezone.utc),
                        )
                        .on_conflict_do_nothing(constraint="uq_raw_transactions_source_ref")
                    )
                    res = await self.db.execute(stmt)
                    if res.rowcount:
                        result.transactions_created += 1
                    else:
                        result.transactions_skipped += 1

                # Kraken returns max 50 per page; stop if we got fewer
                if len(trades) < 50:
                    break
                offset += len(trades)

        await self.db.commit()

        if newest_trade_time:
            result.checkpoint = {"last_trade_time": newest_trade_time}

    # ── Balances ───────────────────────────────────────────────────────────────

    async def _fetch_balances(
        self, api_key: str, api_secret: str, result: ConnectorResult
    ) -> None:
        from app.models.asset import Asset

        async with httpx.AsyncClient(timeout=30) as client:
            log.info("Calling Kraken Balance API...")
            balances = await self._private_post(
                client, api_key, api_secret, "/0/private/Balance"
            )
            log.info("Kraken Balance response: %d assets", len(balances))

        for kraken_sym, balance_str in balances.items():
            if kraken_sym in KRAKEN_SKIP_ASSETS:
                continue
            balance = Decimal(str(balance_str))
            if balance == 0:
                continue

            symbol = KRAKEN_ASSET_MAP.get(kraken_sym, kraken_sym)
            if not self.should_include_symbol(symbol):
                continue

            # Find or create asset
            asset_q = select(Asset).where(
                Asset.portfolio_id == self.portfolio_id,
                Asset.symbol == symbol,
            )
            asset = (await self.db.execute(asset_q)).scalar_one_or_none()

            if not asset and self.auto_create_assets:
                asset = Asset(
                    portfolio_id=self.portfolio_id,
                    symbol=symbol,
                    name=f"{symbol} (Kraken)",
                    asset_behavior="MARKET",
                    category="crypto",
                    currency="USD",
                    pricing_mode="market_price",
                    is_manual=False,
                    status="active",
                )
                self.db.add(asset)
                await self.db.flush()
                await self.db.refresh(asset)
                result.assets_created += 1

            if asset:
                extra = dict(asset.extra_data or {})
                extra["quantity"] = str(balance)
                extra["kraken_balance"] = str(balance)
                asset.extra_data = extra
                if not asset.category:
                    asset.category = "crypto"
                if asset.asset_behavior not in ("MARKET",):
                    asset.asset_behavior = "MARKET"

    # ── Live prices ────────────────────────────────────────────────────────────

    async def _fetch_prices(self, result: ConnectorResult) -> None:
        from app.models.asset import Asset
        from app.models.price_history import AssetPriceHistory

        # Find crypto assets in portfolio that have a known Kraken pair
        q = select(Asset).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.category == "crypto",
            Asset.status == "active",
        )
        assets = (await self.db.execute(q)).scalars().all()

        # Build pair list for assets we know about
        pair_to_asset: Dict[str, Asset] = {}
        for asset in assets:
            pair = KRAKEN_TICKER_PAIRS.get(asset.symbol)
            if pair:
                pair_to_asset[pair] = asset

        if not pair_to_asset:
            return

        pairs_str = ",".join(pair_to_asset.keys())
        today = date.today()
        now = datetime.now(timezone.utc)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{KRAKEN_BASE}/0/public/Ticker",
                params={"pair": pairs_str},
            )
            resp.raise_for_status()
            data = resp.json()

        ticker_data: Dict[str, Any] = data.get("result", {})

        for pair, ticker in ticker_data.items():
            # Kraken may return pair with slightly different key, find asset
            asset = pair_to_asset.get(pair)
            if not asset:
                # Try matching by base symbol
                for p, a in pair_to_asset.items():
                    if pair.startswith(p[:4]) or pair.endswith(pair[-3:]):
                        asset = a
                        break
            if not asset:
                continue

            try:
                price = Decimal(str(ticker["c"][0]))
                high = Decimal(str(ticker["h"][1])) if ticker.get("h") else None
                volume = Decimal(str(ticker["v"][1])) if ticker.get("v") else None
            except (KeyError, IndexError, Exception) as exc:
                log.warning("Kraken price parse error for %s: %s", pair, exc)
                continue

            # Hot-cache update
            asset.current_price = price
            asset.price_updated_at = now

            # Price history (one per day)
            stmt = (
                pg_insert(AssetPriceHistory)
                .values(
                    asset_id=asset.id,
                    portfolio_id=self.portfolio_id,
                    price_date=today,
                    price=price,
                    currency="USD",
                    source="kraken",
                    high=high,
                    volume=volume,
                )
                .on_conflict_do_update(
                    constraint="uq_asset_price_history",
                    set_={"price": price, "high": high, "volume": volume},
                )
            )
            await self.db.execute(stmt)
            result.prices_updated += 1
