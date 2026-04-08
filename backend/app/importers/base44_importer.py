"""
importers/base44_importer.py - Import Base44 JSON exports into Wealth OS

Imports data belonging to TARGET_PORTFOLIO_ID only (Tomer Portfolio Clean).
Supports multiple transaction batch files via --transactions flag (space-separated).
Truncates all tables before importing to ensure a clean state.

Usage:
    python -m app.importers.base44_importer \
        --portfolios   Portfolios.json \
        --accounts     Accounts.json \
        --assets       Assets.json \
        --transactions Transactions.json Transactions__1_.json Transactions__2_.json Transactions__3_.json \
        --valuations   Valuations.json \
        --fx-rates     FX_Rates.json \
        [--dry-run]
"""

import argparse
import json
import logging
import uuid
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.portfolio import Portfolio
from app.models.account import Account
from app.models.asset import Asset
from app.models.transaction import Transaction
from app.models.valuation import ManualValuation
from app.models.fx_rate import FXRate
from app.utils.enums import ECONOMIC_TYPE_NORMALIZE, EconomicType

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

TARGET_PORTFOLIO_ID = "69c48b47734576357923ff08"  # Tomer Portfolio Clean


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_multi(paths: List[str]) -> list:
    """Load and merge multiple JSON batch files, deduplicating by 'id'."""
    seen = set()
    result = []
    for path in paths:
        rows = load_json(path)
        for row in rows:
            rid = row.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                result.append(row)
    log.info("  Loaded %d unique rows from %d file(s)", len(result), len(paths))
    return result


def only_target(data: list, field: str = "portfolio_id") -> list:
    return [r for r in data if r.get(field) == TARGET_PORTFOLIO_ID]


def parse_metadata(raw) -> Optional[dict]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"raw": raw}
    return None


def to_decimal(val) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def to_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        try:
            return date.fromisoformat(str(val)[:10])
        except ValueError:
            return None


def b44_to_uuid(b44_id: str) -> uuid.UUID:
    namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
    return uuid.uuid5(namespace, b44_id)


def normalize_economic_type(raw: Optional[str]) -> Optional[str]:
    """
    Normalize Base44's mixed economic_type values to canonical EconomicType.
    Handles both old snake_case and new UPPERCASE variants.
    Returns the canonical string value or None if unrecognized.
    """
    if not raw:
        return None
    normalized = ECONOMIC_TYPE_NORMALIZE.get(raw)
    if normalized:
        return normalized.value
    log.warning("  [warn] Unknown economic_type '%s' — stored as-is", raw)
    return raw


# ── Lookup maps ────────────────────────────────────────────────────────────────

ACCOUNT_TYPE_MAP = {
    "pension":              "pension_account",
    "pension_account":      "pension_account",
    "alternative":          "alternative_account",
    "alternative_account":  "alternative_account",
    "real_estate":          "real_estate_account",
    "real_estate_account":  "real_estate_account",
    "real_estate_pipeline": "real_estate_account",
    "brokerage":            "brokerage",
    "investment_account":   "brokerage",
    "crypto":               "brokerage",
    "crypto_exchange":      "brokerage",
    "cash":                 "cash",
    "bank_cash_account":    "cash",
}

ACCOUNT_CATEGORY_MAP = {
    "pension":              "pension",
    "pension_account":      "pension",
    "alternative":          "alternatives",
    "alternative_account":  "alternatives",
    "real_estate":          "real_estate",
    "real_estate_account":  "real_estate",
    "real_estate_pipeline": "real_estate",
    "brokerage":            "securities",
    "investment_account":   "securities",
    "crypto":               "crypto",
    "crypto_exchange":      "crypto",
    "cash":                 "cash",
}

ASSET_CATEGORY_MAP = {
    "pension":          "pension",
    "alternative":      "alternatives",
    "alternatives":     "alternatives",
    "collectibles":     "alternatives",
    "real_estate":      "real_estate",
    "real estate":      "real_estate",       # Base44 uses space in some records
    "realestate":       "real_estate",
    "stocks":           "securities",
    "etf":              "securities",
    "securities":       "securities",
    "crypto":           "crypto",
    "cash":             "cash",
    "debt_income":      "debt_income",
    "special_income":   "special_income",
    "solar":            "special_income",
    "energy_income":    "special_income",    # asset_class used by solar assets
}


# ── Truncate ───────────────────────────────────────────────────────────────────

def truncate_all(db: Session):
    """
    Truncate all import tables in reverse FK dependency order.
    Uses TRUNCATE ... CASCADE to handle any remaining constraints.
    """
    log.info("=== Truncating all tables ===")
    tables = [
        "transactions",
        "manual_valuations",
        "fx_rates",
        "assets",
        "accounts",
        "portfolios",
    ]
    for table in tables:
        db.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        log.info("  Truncated: %s", table)
    db.flush()
    log.info("  All tables cleared")


# ── Importers ──────────────────────────────────────────────────────────────────

def import_portfolios(data: list, db: Session, id_map: dict) -> int:
    data = [r for r in data if r["id"] == TARGET_PORTFOLIO_ID]
    count = 0
    for row in data:
        new_id = b44_to_uuid(row["id"])
        id_map["portfolios"][row["id"]] = new_id
        db.add(Portfolio(
            id=new_id,
            name=row["name"],
            base_currency=row.get("base_currency", "ILS"),
            description=row.get("description"),
            is_default=row.get("is_default", False),
        ))
        count += 1
        log.info("  [+] Portfolio: %s", row["name"])
    return count


def import_accounts(data: list, db: Session, id_map: dict) -> int:
    data = only_target(data)
    count = 0
    for row in data:
        new_id = b44_to_uuid(row["id"])
        id_map["accounts"][row["id"]] = new_id
        portfolio_id = id_map["portfolios"].get(row.get("portfolio_id", ""))
        if not portfolio_id:
            log.warning("  [skip] Account %s - portfolio not found", row["name"])
            continue
        meta = parse_metadata(row.get("metadata"))
        symbol = (meta or {}).get("symbol") or "ACC_" + row["name"].upper().replace(" ", "_")[:40]
        is_liquid = bool((meta or {}).get("is_liquid", False))
        is_income_generating = bool((meta or {}).get("is_income_generating", False))
        custodian = (meta or {}).get("custodian") or row.get("institution") or None
        b44_type = row.get("type") or row.get("account_role") or ""
        account_type = ACCOUNT_TYPE_MAP.get(b44_type, "brokerage")
        cat_raw = ((meta or {}).get("category") or "").lower()
        category = ACCOUNT_CATEGORY_MAP.get(cat_raw) or ACCOUNT_CATEGORY_MAP.get(b44_type, "securities")
        clean_meta = {k: v for k, v in (meta or {}).items()
                      if k not in ("symbol", "is_liquid", "is_income_generating")}
        db.add(Account(
            id=new_id,
            portfolio_id=portfolio_id,
            name=row["name"],
            symbol=symbol,
            account_type=account_type,
            category=category,
            currency=row.get("currency") or row.get("base_currency", "ILS"),
            institution=row.get("institution") or row.get("institution_name") or None,
            custodian=custodian,
            is_liquid=is_liquid,
            is_income_generating=is_income_generating,
            include_in_portfolio=row.get("include_in_portfolio", True),
            status=row.get("status", "active"),
            cash_balance=to_decimal(row.get("cash_balance")) or Decimal("0"),
            opening_balance=to_decimal(row.get("opening_balance")),
            extra_data=clean_meta if clean_meta else None,
            notes=row.get("notes"),
        ))
        count += 1
        log.info("  [+] Account: %s (%s)", row["name"], symbol)
    return count


def import_assets(data: list, db: Session, id_map: dict) -> int:
    """
    Issue #1 fix: assets without portfolio_id in metadata are treated as
    belonging to TARGET_PORTFOLIO_ID (demo portfolio has 0 assets, so any
    asset without an explicit portfolio reference is ours).
    """
    filtered = []
    for row in data:
        # Skip explicit demo portfolio assets
        if row.get("portfolio_id") and row["portfolio_id"] != TARGET_PORTFOLIO_ID:
            continue
        meta = parse_metadata(row.get("metadata"))
        meta_pid = (meta or {}).get("portfolio_id")
        if meta_pid and meta_pid != TARGET_PORTFOLIO_ID:
            continue
        # Accept: explicit match, metadata match, or no portfolio reference at all
        filtered.append(row)

    log.info("  Assets after filter: %d / %d", len(filtered), len(data))
    count = 0
    skipped = 0
    for row in filtered:
        new_id = b44_to_uuid(row["id"])
        id_map["assets"][row["id"]] = new_id
        meta = parse_metadata(row.get("metadata"))
        # Resolve portfolio_id: explicit field → metadata field → default to target
        raw_pid = row.get("portfolio_id") or (meta or {}).get("portfolio_id") or TARGET_PORTFOLIO_ID
        portfolio_id = id_map["portfolios"].get(raw_pid)
        if not portfolio_id:
            log.warning("  [skip] Asset %s - portfolio not in id_map", row.get("name"))
            skipped += 1
            continue
        # Resolve linked account via symbol
        account_id = None
        linked_sym = (meta or {}).get("linked_account_symbol")
        if linked_sym:
            acc = db.query(Account).filter(Account.symbol == linked_sym).first()
            if acc:
                account_id = acc.id
            else:
                log.warning("  [warn] Asset %s - linked account '%s' not found", row.get("symbol"), linked_sym)
        raw_category = (row.get("asset_class") or "").lower()
        if meta:
            raw_category = ((meta or {}).get("category") or raw_category).lower()
        category = ASSET_CATEGORY_MAP.get(raw_category, "securities")
        # Fix 1: lifecycle_stage — read from metadata first, fallback to "operational"
        lifecycle_stage = (meta or {}).get("lifecycle_stage") or "operational"

        # Fix 2: for MARKET assets, store Base44 snapshot market_value in extra_data
        # so current_value.py can use it as total position value (not just unit price)
        # This is populated later by import_snapshots() after assets are created
        clean_meta = {k: v for k, v in (meta or {}).items()
                      if k not in ("current_value", "portfolio_id", "linked_account_symbol")}
        db.add(Asset(
            id=new_id,
            portfolio_id=portfolio_id,
            account_id=account_id,
            name=row["name"],
            symbol=row["symbol"],
            asset_behavior=row.get("asset_behavior", "MANUAL"),
            category=category,
            asset_type=row.get("type"),
            sub_type=(meta or {}).get("sub_type"),
            status="active" if row.get("is_active", True) else "inactive",
            lifecycle_stage=lifecycle_stage,
            exchange=row.get("exchange"),
            currency=row.get("currency", "ILS"),
            country=row.get("country"),
            sector=row.get("sector"),
            current_price=to_decimal(row.get("current_price")),
            pricing_mode=row.get("pricing_mode", "manual_valuation"),
            is_manual=row.get("is_manual", True),
            extra_data=clean_meta if clean_meta else None,
        ))
        count += 1
        log.info("  [+] Asset: %s (%s) [%s]", row["name"], row["symbol"], category)
    log.info("  Assets: %d imported, %d skipped", count, skipped)
    return count


def import_transactions(data: list, db: Session, id_map: dict) -> int:
    """
    Issue #2 fix: normalize economic_type to canonical EconomicType values.
    Issue #3 fix: data is pre-merged from multiple batch files by caller.
    """
    data = only_target(data)
    count = 0
    skipped = 0
    for row in data:
        new_id = b44_to_uuid(row["id"])
        portfolio_id = id_map["portfolios"].get(row.get("portfolio_id", ""))
        if not portfolio_id:
            skipped += 1
            continue
        asset_id = None
        if row.get("asset_id"):
            asset_id = id_map["assets"].get(row["asset_id"])
            if asset_id is None:
                log.warning("  [skip] Transaction %s - asset_id '%s' not in id_map",
                            row["id"], row["asset_id"])
                skipped += 1
                continue
        account_id = id_map["accounts"].get(row.get("account_id", "")) if row.get("account_id") else None
        txn_date = to_date(row.get("date"))
        if not txn_date:
            log.warning("  [skip] Transaction %s - no valid date", row["id"])
            skipped += 1
            continue
        db.add(Transaction(
            id=new_id,
            portfolio_id=portfolio_id,
            account_id=account_id,
            asset_id=asset_id,
            transaction_date=txn_date,
            effective_date=to_date(row.get("effective_date")),
            type=row.get("type", "other"),
            economic_type=normalize_economic_type(row.get("economic_type")),
            domain=row.get("domain"),
            subtype=row.get("subtype"),
            total_amount=to_decimal(row.get("total_amount")),
            cashflow_amount=to_decimal(row.get("cashflow_amount")),
            currency=row.get("currency", "ILS"),
            fees=to_decimal(row.get("fees")) or Decimal("0"),
            tax=to_decimal(row.get("tax")) or Decimal("0"),
            quantity=to_decimal(row.get("quantity")),
            price_per_unit=to_decimal(row.get("price_per_unit")),
            units_delta=to_decimal(row.get("units_delta")) or Decimal("0"),
            from_account_id=id_map["accounts"].get(row["from_account_id"]) if row.get("from_account_id") else None,
            to_account_id=id_map["accounts"].get(row["to_account_id"]) if row.get("to_account_id") else None,
            is_internal_transfer=row.get("is_internal_transfer", False),
            status=row.get("status", "confirmed"),
            source="import",
            notes=row.get("notes"),
            external_reference_id=row.get("external_reference_id") or row.get("external_ref"),
        ))
        count += 1
    log.info("  Transactions: %d imported, %d skipped", count, skipped)
    return count


def import_valuations(data: list, db: Session, id_map: dict) -> int:
    """Issue #5 fix: JSON 'date' field correctly mapped to valuation_date."""
    data = only_target(data)
    count = 0
    skipped = 0
    for row in data:
        new_id = b44_to_uuid(row["id"])
        portfolio_id = id_map["portfolios"].get(row.get("portfolio_id", ""))
        asset_id = id_map["assets"].get(row.get("asset_id", "")) if row.get("asset_id") else None
        if not portfolio_id or not asset_id:
            skipped += 1
            continue
        # Issue #5: field is 'date' in JSON, maps to valuation_date in model
        val_date = to_date(row.get("date") or row.get("valuation_date"))
        if not val_date:
            skipped += 1
            continue
        db.add(ManualValuation(
            id=new_id,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            account_id=id_map["accounts"].get(row["account_id"]) if row.get("account_id") else None,
            valuation_date=val_date,
            market_value=to_decimal(row.get("market_value")) or Decimal("0"),
            currency=row.get("currency", "ILS"),
            fx_rate_to_ils=to_decimal(row.get("fx_rate_to_ils")) or Decimal("1"),
            value_ils=to_decimal(row.get("value_ils")),
            valuation_method=row.get("valuation_method", "manual"),
            confidence_level=row.get("confidence_level", "medium"),
            valuation_source=row.get("valuation_source"),
            is_estimated=row.get("is_estimated", False),
            notes=row.get("notes") or "",
            source="import",
        ))
        count += 1
    log.info("  Valuations: %d imported, %d skipped", count, skipped)
    return count


def import_fx_rates(data: list, db: Session) -> int:
    """
    Issue #4 fix: handle two FX rate schemas:
      Old: from_currency / to_currency / date (may be null)
      New: base_currency / target_currency / rate_date
    FX rates with no date get today's date as fallback.
    """
    from datetime import date as date_cls
    count = 0
    skipped = 0
    for row in data:
        new_id = b44_to_uuid(row["id"])
        from_currency = row.get("from_currency") or row.get("base_currency")
        to_currency = row.get("to_currency") or row.get("target_currency")
        if not from_currency or not to_currency:
            log.warning("  [skip] FX rate %s - missing currency fields", row.get("id"))
            skipped += 1
            continue
        # Issue #4: old schema has date=null, new schema has rate_date
        fx_date = to_date(row.get("rate_date") or row.get("date"))
        if not fx_date:
            # Crypto rates like BTC/ETH have no date — use created_date as fallback
            fx_date = to_date(row.get("created_date")) or date_cls.today()
            log.warning("  [warn] FX %s->%s has no date, using %s", from_currency, to_currency, fx_date)
        db.add(FXRate(
            id=new_id,
            fx_date=fx_date,
            from_currency=from_currency,
            to_currency=to_currency,
            rate=to_decimal(row.get("rate")) or Decimal("1"),
            source=row.get("source", "import"),
        ))
        count += 1
        log.info("  [+] FX: %s->%s @ %s on %s", from_currency, to_currency, row.get("rate"), fx_date)
    log.info("  FX rates: %d imported, %d skipped", count, skipped)
    return count


def import_snapshots(data: list, db: Session, id_map: dict) -> int:
    """
    Import Base44 asset-level snapshots as ManualValuation rows.

    Accepts any snapshot file(s) including historical batches.
    For each asset, keeps only the LATEST snapshot by date so we always
    get the most recent position value regardless of which file is passed.

    Only imports scope_type='asset_position' with market_value > 0.
    """
    # Filter to asset_position with value
    data = [r for r in data
            if r.get("scope_type") == "asset_position"
            and r.get("asset_id")
            and (r.get("market_value") or 0) > 0]

    # Keep only the latest snapshot per asset_id
    latest: dict = {}
    for row in data:
        aid = row["asset_id"]
        d = row.get("snapshot_date") or row.get("date") or ""
        existing_d = latest[aid].get("snapshot_date") or latest[aid].get("date") or "" if aid in latest else ""
        if aid not in latest or d > existing_d:
            latest[aid] = row
    data = list(latest.values())
    log.info("  Snapshots: %d unique assets (latest per asset)", len(data))
    for row in data:
        asset_id = id_map["assets"].get(row["asset_id"])
        if not asset_id:
            log.warning("  [snap skip] asset_id %s not in id_map", row.get("asset_id", "")[:8])
            skipped += 1
            continue

        asset = db.get(Asset, asset_id)
        if not asset:
            log.warning("  [snap skip] asset_id %s not found in DB", str(asset_id)[:8])
            skipped += 1
            continue

        market_value = to_decimal(row.get("market_value"))
        if not market_value or market_value <= Decimal("0"):
            skipped += 1
            continue

        val_date = to_date(row.get("snapshot_date") or row.get("date"))
        if not val_date:
            skipped += 1
            continue

        portfolio_id = id_map["portfolios"].get(TARGET_PORTFOLIO_ID)
        if not portfolio_id:
            skipped += 1
            continue

        # Deterministic UUID — include market_value to handle same asset/date with different values
        snap_key = f"b44_snap_{row['asset_id']}_{val_date}_{market_value}"
        new_id = b44_to_uuid(snap_key)

        if db.get(ManualValuation, new_id):
            skipped += 1
            continue

        # Resolve FX rate
        currency = asset.currency or "ILS"
        fx_rate = Decimal("1")
        if currency != "ILS":
            from app.models.fx_rate import FXRate
            from sqlalchemy import and_
            fx_row = (
                db.query(FXRate)
                .filter(
                    and_(
                        FXRate.from_currency == currency,
                        FXRate.to_currency == "ILS",
                        FXRate.fx_date <= val_date,
                    )
                )
                .order_by(FXRate.fx_date.desc())
                .first()
            )
            if fx_row:
                fx_rate = fx_row.rate

        value_ils = market_value * fx_rate

        db.add(ManualValuation(
            id=new_id,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            account_id=None,
            valuation_date=val_date,
            market_value=market_value,
            currency=currency,
            fx_rate_to_ils=fx_rate,
            value_ils=value_ils,
            valuation_method="manual",
            confidence_level="medium",
            valuation_source="b44_snapshot",
            is_estimated=False,
            notes="Imported from Base44 snapshot",
            source="import",
        ))
        count += 1
        log.info("  [snap→val] %s  %s %s  (ILS %s) on %s",
                 asset.symbol, currency, market_value, value_ils, val_date)

    log.info("  Snapshot valuations: %d imported, %d skipped", count, skipped)
    return count


# ── Main runner ────────────────────────────────────────────────────────────────

def run(args):
    db = SessionLocal()
    id_map = {"portfolios": {}, "accounts": {}, "assets": {}}
    try:
        log.info("=== Wealth OS Import - Tomer Portfolio Clean ===")

        if not args.dry_run:
            truncate_all(db)
        else:
            log.info("=== DRY RUN - skipping truncate ===")

        if args.portfolios:
            import_portfolios(load_json(args.portfolios), db, id_map)

        if args.accounts:
            import_accounts(load_json(args.accounts), db, id_map)

        if args.assets:
            import_assets(load_json(args.assets), db, id_map)

        if args.transactions:
            # Issue #3: support multiple batch files
            txn_data = load_json_multi(args.transactions)
            import_transactions(txn_data, db, id_map)

        if args.valuations:
            db.flush()  # flush assets/accounts before valuation FK lookups
            import_valuations(load_json(args.valuations), db, id_map)

        if args.fx_rates:
            import_fx_rates(load_json(args.fx_rates), db)

        if args.snapshots:
            db.flush()
            snap_data = load_json_multi(args.snapshots)
            import_snapshots(snap_data, db, id_map)

        if args.dry_run:
            log.info("=== DRY RUN - rolling back, nothing written ===")
            db.rollback()
        else:
            log.info("=== Committing ===")
            db.commit()
            log.info("=== Import complete ===")

    except Exception as e:
        db.rollback()
        log.error("Import failed: %s", e)
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Import Base44 -> Wealth OS")
    parser.add_argument("--portfolios",    help="Portfolios.json")
    parser.add_argument("--accounts",      help="Accounts.json")
    parser.add_argument("--assets",        help="Assets.json")
    parser.add_argument("--transactions",  nargs="+", help="Transaction batch files (space-separated)")
    parser.add_argument("--valuations",    help="Valuations.json")
    parser.add_argument("--fx-rates",      dest="fx_rates", help="FX_Rates.json")
    parser.add_argument("--snapshots",     nargs="+", help="Snapshot batch files (space-separated, latest per asset used)")
    parser.add_argument("--dry-run",       action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
