"""
CEX.io Crypto Exchange Connector

Fetches:
  - Trade history  → raw_transactions (dedup on external_ref_id)
  - Balances       → asset.extra_data quantity update / auto-create assets
  - Live prices    → asset.current_price + asset_price_history

Authentication: HMAC-SHA256 with nonce + username + api_key signature.
Rate limit: ~0.5 req/s for private endpoints (enforced with asyncio.sleep).
"""
import asyncio
import hashlib
import hmac
import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register
from app.utils.uuid7 import uuid7

log = logging.getLogger(__name__)

CEXIO_BASE = "https://cex.io"

CEXIO_PAIRS: List[tuple[str, str]] = [
    ("BTC", "USD"), ("ETH", "USD"), ("LTC", "USD"), ("XRP", "USD"),
    ("ADA", "USD"), ("SOL", "USD"), ("DOT", "USD"), ("LINK", "USD"),
    ("DOGE", "USD"), ("AVAX", "USD"), ("MATIC", "USD"), ("ATOM", "USD"),
    ("BTC", "EUR"), ("ETH", "EUR"),
]

CEXIO_SKIP_ASSETS = {
    "USD", "EUR", "GBP", "GHS", "USDT", "USDC", "DAI",
}


def _cexio_sign(api_secret: str, nonce: str, username: str, api_key: str) -> str:
    """Generate CEX.io HMAC-SHA256 signature (uppercase hex)."""
    message = nonce + username + api_key
    return hmac.new(
        api_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest().upper()


@register
class CexioConnector(BaseConnector):
    CONNECTOR_TYPE = "cexio"
    DISPLAY_NAME = "CEX.io"
    DESCRIPTION = "Fetches trade history, balances, and live prices from CEX.io crypto exchange."
    CONFIG_FIELDS = [
        {
            "key": "api_key",
            "label": "API Key",
            "type": "text",
            "default": "",
            "hint": "Get API keys at cex.io/trade/profile — needs: Account Balance, Open Orders, Archived Orders",
        },
        {
            "key": "api_secret",
            "label": "API Secret",
            "type": "password",
            "default": "",
            "hint": "The secret shown once when creating the API key",
        },
        {
            "key": "username",
            "label": "Username (email)",
            "type": "text",
            "default": "",
            "hint": "Your CEX.io account email address",
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
        log.info("CEX.io connector starting — config keys present: %s", list(self.config.keys()))
        api_key = self.config.get("api_key", "")
        api_secret = self.config.get("api_secret", "")
        username = self.config.get("username", "")
        log.info("CEX.io has api_key: %s  has api_secret: %s  has username: %s  key_prefix: %s",
                 bool(api_key), bool(api_secret), bool(username),
                 (api_key[:8] + "...") if api_key else "<empty>")

        if not api_key or not api_secret or not username:
            msg = "CEX.io: api_key, api_secret, and username are required — check that CONNECTOR_ENCRYPTION_KEY matches and credentials were saved"
            log.error(msg)
            result.warnings.append(msg)
            return result

        try:
            await self._fetch_trades(api_key, api_secret, username, result)
            await asyncio.sleep(0.5)
            await self._fetch_balances(api_key, api_secret, username, result)
            await asyncio.sleep(0.5)
            await self._fetch_prices(result)
            await self.db.flush()
        except Exception as exc:
            log.exception("CEX.io connector failed: %s", exc)
            result.warnings.append(f"CEX.io error: {exc}")

        log.info("CEX.io run finished — fetched=%d created=%d skipped=%d prices=%d",
                 result.records_fetched, result.transactions_created,
                 result.transactions_skipped, result.prices_updated)
        return result

    # ── Private API helper ─────────────────────────────────────────────────────

    def _auth_params(self, api_key: str, api_secret: str, username: str) -> Dict[str, str]:
        nonce = str(int(time.time() * 1000))
        signature = _cexio_sign(api_secret, nonce, username, api_key)
        return {"key": api_key, "signature": signature, "nonce": nonce}

    async def _private_post(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        api_secret: str,
        username: str,
        path: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params = self._auth_params(api_key, api_secret, username)
        if extra:
            params.update(extra)

        resp = await client.post(
            f"{CEXIO_BASE}{path}",
            data=params,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"CEX.io API error: {data['error']}")
        return data

    # ── Tier 3 fuzzy link helper ───────────────────────────────────────────────

    async def _link_or_insert_raw(
        self,
        real_id: str,
        asset_id: Optional[UUID],
        trade_date: "date",
        trade_type: str,
        vol: float,
        raw_values: Dict[str, Any],
        result: ConnectorResult,
    ) -> bool:
        """Returns True if a new raw row was created."""
        from app.models.raw_layer import RawTransaction
        from app.models.transaction import Transaction
        from sqlalchemy import update, func

        # Tier 1: already linked by exchange ID in transactions
        existing_q = select(Transaction.id).where(
            Transaction.portfolio_id == self.portfolio_id,
            Transaction.external_reference_id == real_id,
        )
        if (await self.db.execute(existing_q)).scalar_one_or_none():
            result.transactions_skipped += 1
            return False

        # Tier 3: fuzzy match on manual transaction
        if asset_id:
            tolerance = Decimal("0.000001")
            vol_dec = Decimal(str(vol))
            manual_q = select(Transaction.id).where(
                Transaction.portfolio_id == self.portfolio_id,
                Transaction.asset_id == asset_id,
                Transaction.transaction_date == trade_date,
                Transaction.type == trade_type.upper(),
                Transaction.quantity.isnot(None),
                func.abs(Transaction.quantity - vol_dec) < tolerance,
                Transaction.external_reference_id.is_(None),
            ).limit(1)
            manual_id = (await self.db.execute(manual_q)).scalar_one_or_none()

            if manual_id:
                await self.db.execute(
                    update(Transaction)
                    .where(Transaction.id == manual_id)
                    .values(external_reference_id=real_id, source="cexio")
                )
                log.info("Linked manual import %s → %s", manual_id, real_id)
                result.transactions_skipped += 1
                return False

        # No match — insert new raw_transaction
        stmt = (
            pg_insert(RawTransaction)
            .values(**raw_values)
            .on_conflict_do_nothing(constraint="uq_raw_transactions_source_ref")
        )
        res = await self.db.execute(stmt)
        if res.rowcount:
            result.transactions_created += 1
            return True
        else:
            result.transactions_skipped += 1
            return False

    # ── Trade history ──────────────────────────────────────────────────────────

    async def _fetch_trades(
        self, api_key: str, api_secret: str, username: str, result: ConnectorResult
    ) -> None:
        from app.models.connector import ConnectorRun, Connector
        from datetime import date as date_type

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
        linked_count = 0
        created_count = 0

        async with httpx.AsyncClient(timeout=30) as client:
            for base, quote in CEXIO_PAIRS:
                if not self.should_include_symbol(base):
                    continue

                extra: Dict[str, Any] = {"limit": 100}
                if last_trade_time:
                    extra["dateFrom"] = int(last_trade_time) + 1

                await asyncio.sleep(0.5)
                try:
                    data = await self._private_post(
                        client, api_key, api_secret, username,
                        f"/api/archived_orders/{base}/{quote}",
                        extra=extra,
                    )
                except Exception as exc:
                    log.warning("CEX.io trade fetch failed for %s/%s: %s", base, quote, exc)
                    continue

                orders = data if isinstance(data, list) else data.get("data", [])
                if not orders:
                    continue

                result.records_fetched += len(orders)

                for order in orders:
                    real_id = f"CEXIO-{order.get('id', '')}"
                    trade_ts = float(order.get("time", order.get("lastTxTime", 0)))
                    trade_dt = datetime.fromtimestamp(trade_ts, tz=timezone.utc)
                    trade_date: date_type = trade_dt.date()
                    trade_type = order.get("type", "buy").lower()
                    amount_str = order.get("amount", order.get("ta", "0"))
                    price_str = order.get("price", order.get("fa", "0"))
                    vol = float(amount_str)
                    price = float(price_str)
                    cost = vol * price
                    fee = float(order.get("fee", order.get("tradingFeeTaker", "0")))
                    signed_amount = -cost if trade_type == "buy" else cost

                    if newest_trade_time is None or trade_ts > newest_trade_time:
                        newest_trade_time = trade_ts

                    asset_id: Optional[UUID] = None
                    if self.should_include_symbol(base):
                        asset_id = await self.resolve_or_create_asset(
                            base,
                            meta={
                                "name": f"{base} (CEX.io)",
                                "category": "crypto",
                                "asset_behavior": "MARKET",
                                "currency": "USD",
                            },
                        )

                    created = await self._link_or_insert_raw(
                        real_id=real_id,
                        asset_id=asset_id,
                        trade_date=trade_date,
                        trade_type=trade_type,
                        vol=vol,
                        raw_values=dict(
                            id=uuid7(),
                            portfolio_id=self.portfolio_id,
                            source="cexio",
                            raw_date=trade_dt,
                            description=f"CEX.io {trade_type.upper()} {vol} {base} @ {price} {quote}",
                            amount=signed_amount,
                            currency=quote,
                            reference=str(order.get("id", "")),
                            external_ref_id=real_id,
                            extra_raw={
                                "order_id": str(order.get("id", "")),
                                "pair": f"{base}/{quote}",
                                "type": trade_type,
                                "vol": str(vol),
                                "price": str(price),
                                "cost": str(cost),
                                "fee": str(fee),
                                "symbol": base,
                                "account_id": str(account_id) if account_id else None,
                            },
                            imported_at=datetime.now(timezone.utc),
                        ),
                        result=result,
                    )
                    if created:
                        created_count += 1

        await self.db.commit()

        log.info("CEX.io trades: linked=%d new_raw=%d skipped=%d",
                 linked_count, created_count, result.transactions_skipped)

        if newest_trade_time:
            result.checkpoint = {"last_trade_time": newest_trade_time}

    # ── Balances ───────────────────────────────────────────────────────────────

    async def _fetch_balances(
        self, api_key: str, api_secret: str, username: str, result: ConnectorResult
    ) -> None:
        from app.models.asset import Asset

        async with httpx.AsyncClient(timeout=30) as client:
            data = await self._private_post(
                client, api_key, api_secret, username, "/api/balance/"
            )

        balances: Dict[str, Any] = data if isinstance(data, dict) else {}

        for symbol, info in balances.items():
            if symbol in CEXIO_SKIP_ASSETS:
                continue
            if not isinstance(info, dict):
                continue

            available = Decimal(str(info.get("available", 0)))
            orders = Decimal(str(info.get("orders", 0)))
            balance = available + orders
            if balance == 0:
                continue

            if not self.should_include_symbol(symbol):
                continue

            asset_q = select(Asset).where(
                Asset.portfolio_id == self.portfolio_id,
                Asset.symbol == symbol,
            )
            asset = (await self.db.execute(asset_q)).scalar_one_or_none()

            if not asset and self.auto_create_assets:
                asset = Asset(
                    portfolio_id=self.portfolio_id,
                    symbol=symbol,
                    name=f"{symbol} (CEX.io)",
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
                extra["cexio_balance"] = str(balance)
                asset.extra_data = extra
                if not asset.category:
                    asset.category = "crypto"
                if asset.asset_behavior not in ("MARKET",):
                    asset.asset_behavior = "MARKET"

    # ── Live prices ────────────────────────────────────────────────────────────

    async def _fetch_prices(self, result: ConnectorResult) -> None:
        from app.models.asset import Asset
        from app.models.price_history import AssetPriceHistory

        q = select(Asset).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.category == "crypto",
            Asset.status == "active",
        )
        assets = (await self.db.execute(q)).scalars().all()
        if not assets:
            return

        today = date.today()
        now = datetime.now(timezone.utc)

        async with httpx.AsyncClient(timeout=30) as client:
            for asset in assets:
                symbol = asset.symbol
                pair_found = any(b == symbol for b, _ in CEXIO_PAIRS)
                if not pair_found:
                    continue

                quote = "USD"
                await asyncio.sleep(0.3)
                try:
                    resp = await client.get(
                        f"{CEXIO_BASE}/api/ticker/{symbol}/{quote}"
                    )
                    resp.raise_for_status()
                    ticker = resp.json()
                except Exception as exc:
                    log.warning("CEX.io price fetch failed for %s: %s", symbol, exc)
                    continue

                if ticker.get("error"):
                    log.warning("CEX.io ticker error for %s: %s", symbol, ticker["error"])
                    continue

                try:
                    price = Decimal(str(ticker["last"]))
                    high = Decimal(str(ticker["high"])) if ticker.get("high") else None
                    volume = Decimal(str(ticker["volume"])) if ticker.get("volume") else None
                except (KeyError, Exception) as exc:
                    log.warning("CEX.io price parse error for %s: %s", symbol, exc)
                    continue

                asset.current_price = price
                asset.price_updated_at = now

                stmt = (
                    pg_insert(AssetPriceHistory)
                    .values(
                        asset_id=asset.id,
                        portfolio_id=self.portfolio_id,
                        price_date=today,
                        price=price,
                        currency=quote,
                        source="cexio",
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
