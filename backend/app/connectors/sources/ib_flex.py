"""
IB Flex Query Connector
Fetches trade history and cash transactions from Interactive Brokers
via the Flex Web Service API. No gateway required — pure HTTP.

Two-step flow:
  1. POST SendRequest → get reference code
  2. GET GetStatement with reference code → get XML data

Incremental sync via checkpoint:
  - First run: fetches last 365 days, then walks back year by year
  - Subsequent runs: fetches from last_trade_date to today
  - Deduplication via TradeID / TransactionID as external_reference_id
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register

log = logging.getLogger(__name__)

SEND_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
FETCH_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
USER_AGENT = "Python/3.12 WealthOS/1.0"

# IB transaction type → our TransactionType
IB_TYPE_MAP = {
    "BUY": "buy",
    "SELL": "sell",
    "DIV": "dividend",
    "DIVCGL": "dividend",
    "DIVCGS": "dividend",
    "DIVNRA": "dividend",
    "INTEREST": "income",
    "DEPWD": "deposit",
    "WITHDRAWAL": "withdrawal",
    "FEES": "expense",
    "WITHHOLDING": "expense",
    "OTHER": "income",
}

# IB transaction type → our EconomicType
IB_ECONOMIC_MAP = {
    "BUY": "BUY",
    "SELL": "SELL",
    "DIV": "INCOME",
    "DIVCGL": "INCOME",
    "INTEREST": "INCOME",
    "DEPWD": "DEPOSIT",
    "WITHDRAWAL": "WITHDRAWAL",
    "FEES": "EXPENSE",
    "WITHHOLDING": "EXPENSE",
}

# IB AssetClass → our category
IB_ASSET_CLASS_MAP = {
    "STK": "securities",
    "ETF": "etf",
    "BOND": "securities",
    "OPT": "securities",
    "FUT": "securities",
    "CASH": "cash",
    "CRYPTO": "crypto",
    "FUND": "mutual_fund",
}


@register
class IBFlexConnector(BaseConnector):
    CONNECTOR_TYPE = "ib_flex"
    DISPLAY_NAME = "Interactive Brokers (Flex)"
    DESCRIPTION = "Fetches trade history and positions from Interactive Brokers via Flex Web Service. No gateway required."
    CONFIG_FIELDS = [
        {
            "key": "token",
            "label": "Flex Web Service Token",
            "type": "password",
            "default": "",
            "hint": "23-digit token from IB Portal → Performance & Reports → Flex Queries → Flex Web Service Configuration",
        },
        {
            "key": "query_id",
            "label": "Flex Query ID",
            "type": "text",
            "default": "",
            "hint": "Query ID shown in Flex Queries list (e.g. 1466664)",
        },
        {
            "key": "account_id",
            "label": "IB Account ID",
            "type": "text",
            "default": "",
            "hint": "Your IB account number (e.g. U18804332)",
        },
    ]

    async def run(self) -> ConnectorResult:
        result = ConnectorResult()

        token = self.config.get("token", "").strip()
        query_id = self.config.get("query_id", "").strip()

        if not token or not query_id:
            raise ValueError("IB Flex connector requires 'token' and 'query_id' in config")

        # Determine date range
        checkpoint = self.config.get("_checkpoint", {})
        last_date_str = checkpoint.get("last_trade_date")

        if last_date_str:
            # Incremental: fetch from last known date to today
            from_date = date.fromisoformat(last_date_str) - timedelta(days=1)  # 1 day overlap
            to_date = date.today()
            date_ranges = [(from_date, to_date)]
            log.info("IB Flex incremental sync: %s to %s", from_date, to_date)
        else:
            # First run: fetch in yearly chunks going back up to 5 years
            today = date.today()
            date_ranges = []
            for i in range(5):
                td = today - timedelta(days=365 * i)
                fd = today - timedelta(days=365 * (i + 1))
                date_ranges.append((fd, td))
            log.info("IB Flex first run: fetching %d year(s) of history", len(date_ranges))

        latest_trade_date = None

        for from_date, to_date in date_ranges:
            log.info("  Fetching IB Flex: %s to %s", from_date, to_date)
            xml_data = await self._fetch_flex_xml(token, query_id, from_date, to_date)

            if not xml_data:
                log.info("  No data for range %s to %s", from_date, to_date)
                if last_date_str is None:
                    break  # No more historical data
                continue

            batch_result = await self._process_xml(xml_data)
            result.records_fetched += batch_result.records_fetched
            result.transactions_created += batch_result.transactions_created
            result.transactions_skipped += batch_result.transactions_skipped
            result.assets_created += batch_result.assets_created

            if batch_result.checkpoint and batch_result.checkpoint.get("last_trade_date"):
                d = date.fromisoformat(batch_result.checkpoint["last_trade_date"])
                if latest_trade_date is None or d > latest_trade_date:
                    latest_trade_date = d

            # Small delay between requests to be respectful
            await asyncio.sleep(1)

        if latest_trade_date:
            result.checkpoint = {"last_trade_date": str(latest_trade_date)}

        return result

    async def _fetch_flex_xml(
        self, token: str, query_id: str, from_date: date, to_date: date
    ) -> Optional[str]:
        """Two-step IB Flex Web Service call. Returns XML string or None."""
        headers = {"User-Agent": USER_AGENT}
        fd = from_date.strftime("%Y%m%d")
        td = to_date.strftime("%Y%m%d")

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            # Step 1: Request report generation
            resp = await client.get(
                SEND_URL,
                params={"t": token, "q": query_id, "v": "3", "fd": fd, "td": td},
                headers=headers,
            )
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            status = root.find("Status")
            ref_code = root.find("ReferenceCode")

            if status is None or status.text != "Success":
                error = root.find("ErrorMessage")
                msg = error.text if error is not None else resp.text
                # "No data in date range" is not an error
                if "No data" in msg or "no data" in msg.lower():
                    return None
                raise ValueError(f"IB Flex SendRequest failed: {msg}")

            reference_code = ref_code.text
            log.info("  IB reference code: %s", reference_code)

            # Step 2: Fetch the report (may need a few seconds to generate)
            for attempt in range(5):
                await asyncio.sleep(2 + attempt)
                fetch_resp = await client.get(
                    FETCH_URL,
                    params={"t": token, "q": reference_code, "v": "3"},
                    headers=headers,
                )
                fetch_resp.raise_for_status()

                # Check if still processing
                if "<Status>Processing</Status>" in fetch_resp.text:
                    log.info("  Report still generating, waiting...")
                    continue

                return fetch_resp.text

        return None

    async def _process_xml(self, xml_data: str) -> ConnectorResult:
        """Parse XML and create transactions + update positions."""
        result = ConnectorResult()
        root = ET.fromstring(xml_data)

        latest_date = None

        # Process Trades
        for trade in root.iter("Trade"):
            try:
                processed = await self._process_trade(trade)
                result.records_fetched += 1
                if processed == "created":
                    result.transactions_created += 1
                elif processed == "skipped":
                    result.transactions_skipped += 1
                elif processed == "asset_created":
                    result.transactions_created += 1
                    result.assets_created += 1

                trade_date_str = trade.get("tradeDate") or trade.get("reportDate")
                if trade_date_str:
                    try:
                        td = date.fromisoformat(trade_date_str[:10])
                        if latest_date is None or td > latest_date:
                            latest_date = td
                    except ValueError:
                        pass

            except Exception as e:
                log.warning("  Failed to process trade: %s — %s", trade.get("tradeID"), e)

        # Process Cash Transactions (dividends, interest, deposits)
        for cash_tx in root.iter("CashTransaction"):
            try:
                processed = await self._process_cash_transaction(cash_tx)
                result.records_fetched += 1
                if processed == "created":
                    result.transactions_created += 1
                elif processed == "skipped":
                    result.transactions_skipped += 1

                tx_date_str = cash_tx.get("dateTime", "")[:10]
                if tx_date_str:
                    try:
                        td = date.fromisoformat(tx_date_str)
                        if latest_date is None or td > latest_date:
                            latest_date = td
                    except ValueError:
                        pass

            except Exception as e:
                log.warning("  Failed to process cash tx: %s — %s", cash_tx.get("transactionID"), e)

        # Process Open Positions (update asset quantities in extra_data)
        positions_updated = 0
        for position in root.iter("OpenPosition"):
            try:
                updated = await self._process_open_position(position)
                if updated:
                    positions_updated += 1
            except Exception as e:
                log.warning("  Failed to process position: %s — %s", position.get("symbol"), e)

        if positions_updated:
            log.info("  Updated %d open positions", positions_updated)

        await self.db.flush()

        if latest_date:
            result.checkpoint = {"last_trade_date": str(latest_date)}

        return result

    async def _process_trade(self, trade: ET.Element) -> str:
        """Process a single trade. Returns 'created', 'skipped', or 'asset_created'."""
        from sqlalchemy import select
        from app.models.transaction import Transaction

        trade_id = trade.get("tradeID") or trade.get("ibExecID", "")
        symbol = trade.get("symbol", "").strip()
        if not symbol or not trade_id:
            return "skipped"

        # Deduplication
        ext_ref = f"IB-{trade_id}"
        existing = (await self.db.execute(
            select(Transaction).where(Transaction.external_reference_id == ext_ref)
        )).scalar_one_or_none()
        if existing:
            return "skipped"

        # Parse fields
        trade_date_str = (trade.get("tradeDate") or trade.get("dateTime", ""))[:10]
        if not trade_date_str:
            return "skipped"

        trade_date = date.fromisoformat(trade_date_str)
        buy_sell = trade.get("buySell", "").upper()  # BUY or SELL
        quantity = Decimal(str(trade.get("quantity", "0") or "0"))
        price = Decimal(str(trade.get("tradePrice", "0") or "0"))
        trade_money = Decimal(str(trade.get("tradeMoney", "0") or "0"))  # qty × price
        net_cash = Decimal(str(trade.get("netCash", "0") or "0"))  # after commissions
        commission = Decimal(str(abs(float(trade.get("ibCommission", "0") or "0"))))
        currency = trade.get("currencyPrimary", "USD")
        exchange = trade.get("exchange", "")
        asset_class = trade.get("assetClass", "STK")
        description = trade.get("description", "")

        # Resolve or create asset
        category = IB_ASSET_CLASS_MAP.get(asset_class, "securities")
        asset_id = await self.resolve_or_create_asset(symbol, {
            "name": description or symbol,
            "category": category,
            "asset_behavior": "MARKET",
            "currency": currency,
            "exchange": exchange,
        })

        if not asset_id:
            return "skipped"

        txn_type = "buy" if buy_sell == "BUY" else "sell"
        economic_type = "BUY" if buy_sell == "BUY" else "SELL"

        # For buys: total_amount is positive (money out)
        # For sells: total_amount is positive (money in)
        total_amount = abs(trade_money) if trade_money != 0 else abs(quantity * price)

        from app.models.transaction import Transaction
        txn = Transaction(
            portfolio_id=self.portfolio_id,
            asset_id=asset_id,
            transaction_date=trade_date,
            type=txn_type,
            economic_type=economic_type,
            domain="securities",
            quantity=abs(quantity),
            price_per_unit=price if price > 0 else None,
            total_amount=total_amount,
            cashflow_amount=net_cash if net_cash != 0 else None,
            fees=commission,
            currency=currency,
            status="confirmed",
            source="connector",
            external_reference_id=ext_ref,
        )
        self.db.add(txn)

        was_created = await self._check_if_asset_was_new(asset_id)
        return "asset_created" if was_created else "created"

    async def _process_cash_transaction(self, cash_tx: ET.Element) -> str:
        """Process dividends, interest, deposits."""
        from sqlalchemy import select
        from app.models.transaction import Transaction

        tx_id = cash_tx.get("transactionID", "")
        if not tx_id:
            return "skipped"

        ext_ref = f"IB-CASH-{tx_id}"
        existing = (await self.db.execute(
            select(Transaction).where(Transaction.external_reference_id == ext_ref)
        )).scalar_one_or_none()
        if existing:
            return "skipped"

        tx_type_raw = (cash_tx.get("type") or cash_tx.get("subCategory", "OTHER")).upper()
        txn_type = IB_TYPE_MAP.get(tx_type_raw, "income")
        economic_type = IB_ECONOMIC_MAP.get(tx_type_raw, "INCOME")

        date_str = (cash_tx.get("dateTime") or cash_tx.get("date", ""))[:10]
        if not date_str:
            return "skipped"

        amount = Decimal(str(cash_tx.get("amount", "0") or "0"))
        currency = cash_tx.get("currencyPrimary", "USD")
        symbol = (cash_tx.get("symbol") or "").strip()
        description = cash_tx.get("description", "")

        # Try to link to asset if symbol present
        asset_id = None
        if symbol:
            asset_id = await self.resolve_or_create_asset(symbol, {
                "name": description or symbol,
                "category": "securities",
                "asset_behavior": "MARKET",
                "currency": currency,
            })

        txn = Transaction(
            portfolio_id=self.portfolio_id,
            asset_id=asset_id,
            transaction_date=date.fromisoformat(date_str),
            type=txn_type,
            economic_type=economic_type,
            total_amount=abs(amount),
            cashflow_amount=amount,
            currency=currency,
            status="confirmed",
            source="connector",
            external_reference_id=ext_ref,
            notes=description[:200] if description else None,
        )
        self.db.add(txn)
        return "created"

    async def _process_open_position(self, position: ET.Element) -> bool:
        """Update asset extra_data with current quantity from IB position."""
        from sqlalchemy import select
        from app.models.asset import Asset

        symbol = (position.get("symbol") or "").strip()
        quantity_str = position.get("position") or position.get("quantity", "0")

        if not symbol:
            return False

        try:
            quantity = float(quantity_str or "0")
        except ValueError:
            return False

        q = select(Asset).where(
            Asset.portfolio_id == self.portfolio_id,
            Asset.symbol == symbol,
        )
        asset = (await self.db.execute(q)).scalar_one_or_none()
        if not asset:
            return False

        # Update quantity in extra_data — engine reads this for value calculation
        extra = asset.extra_data or {}
        extra["quantity"] = quantity
        extra["ib_position_value"] = float(position.get("positionValue") or "0")
        extra["ib_mark_price"] = float(position.get("markPrice") or "0")
        extra["ib_cost_basis"] = float(position.get("costBasisMoney") or "0")
        extra["ib_updated_at"] = str(date.today())
        asset.extra_data = extra
        return True

    _new_asset_ids: set = set()

    async def _check_if_asset_was_new(self, asset_id) -> bool:
        """Track if an asset was newly created in this run."""
        if not hasattr(self, "_created_asset_ids"):
            self._created_asset_ids = set()
        if asset_id not in self._created_asset_ids:
            self._created_asset_ids.add(asset_id)
            return False
        return False
