"""
engine/current_value.py

Calculates current_value for an asset based on its CalcModel.

Each model has its own priority chain — the engine tries sources in order
and stops at the first valid result. Every result includes:
  - value_native     (in asset's own currency)
  - value_ils        (converted to portfolio base currency ILS)
  - fx_rate_used
  - value_source     (what data source produced this value)
  - confidence       (high / medium / low)
  - warning          (optional explanation if fallback was used)

Usage:
    from app.engine.model_resolver import resolve_model
    from app.engine.current_value import calc_current_value

    result = calc_current_value(asset, db, snapshot_date)
    print(result.value_ils, result.confidence)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
import logging

from sqlalchemy.orm import Session

from app.engine.model_resolver import CalcModel, resolve_model, classify_transaction

log = logging.getLogger(__name__)

ZERO = Decimal("0")
ONE  = Decimal("1")


# ── Result container ───────────────────────────────────────────────────────────

@dataclass
class CurrentValueResult:
    value_native: Optional[Decimal]     # in asset's native currency
    value_ils: Optional[Decimal]        # converted to ILS
    currency: str                       # native currency code
    fx_rate_used: Decimal               # rate applied (1.0 if already ILS)
    value_source: str                   # e.g. "manual_valuation", "market_price", "cost_basis_fallback"
    model_used: CalcModel
    confidence: str                     # "high" | "medium" | "low"
    warning: Optional[str] = None


# ── FX helper ──────────────────────────────────────────────────────────────────

def get_fx_rate(db: Session, from_currency: str, to_currency: str, as_of: date) -> Decimal:
    """
    Look up FX rate from the fx_rates table.
    Priority: exact date → most recent prior date → 1.0 fallback with warning.
    """
    if from_currency == to_currency:
        return ONE

    from app.models.fx_rate import FXRate
    from sqlalchemy import and_

    # Try exact date first, then walk back up to 30 days
    rate_row = (
        db.query(FXRate)
        .filter(
            and_(
                FXRate.from_currency == from_currency,
                FXRate.to_currency == to_currency,
                FXRate.fx_date <= as_of,
            )
        )
        .order_by(FXRate.fx_date.desc())
        .first()
    )

    if rate_row:
        return rate_row.rate

    log.warning("FX rate not found: %s→%s as of %s — using 1.0", from_currency, to_currency, as_of)
    return ONE


def to_ils(amount: Decimal, currency: str, db: Session, as_of: date) -> tuple:
    """Returns (value_ils, fx_rate_used)."""
    if currency == "ILS":
        return amount, ONE
    fx = get_fx_rate(db, currency, "ILS", as_of)
    return amount * fx, fx


# ── Price history helper ───────────────────────────────────────────────────────

def _get_asset_price(db: Session, asset, as_of: date):
    """
    Return the most recent price for an asset on or before as_of.
    Priority: AssetPriceHistory row → asset.current_price hot cache.
    Returns a Decimal/float or None.
    """
    try:
        from app.models.price_history import AssetPriceHistory
        ph = (
            db.query(AssetPriceHistory)
            .filter(
                AssetPriceHistory.asset_id == asset.id,
                AssetPriceHistory.price_date <= as_of,
            )
            .order_by(AssetPriceHistory.price_date.desc())
            .first()
        )
        if ph and ph.price:
            return ph.price
    except Exception:
        pass
    return asset.current_price


# ── Valuation helper ───────────────────────────────────────────────────────────

def get_latest_valuation(db: Session, asset_id, as_of: date):
    """Returns the most recent ManualValuation on or before as_of date."""
    from app.models.valuation import ManualValuation
    return (
        db.query(ManualValuation)
        .filter(
            ManualValuation.asset_id == asset_id,
            ManualValuation.valuation_date <= as_of,
        )
        .order_by(ManualValuation.valuation_date.desc())
        .first()
    )


# ── Transaction helpers ────────────────────────────────────────────────────────

def get_asset_transactions(db: Session, asset_id, as_of: date) -> list:
    """All transactions for an asset up to and including as_of date."""
    from app.models.transaction import Transaction
    return (
        db.query(Transaction)
        .filter(
            Transaction.asset_id == asset_id,
            Transaction.transaction_date <= as_of,
        )
        .order_by(Transaction.transaction_date)
        .all()
    )


def sum_invested_capital(transactions: list) -> Decimal:
    """Sum of all amounts that constitute cost basis (BUY, DEPOSIT, INVESTMENT_OUTFLOW)."""
    total = ZERO
    for tx in transactions:
        flags = classify_transaction(tx)
        if flags.affects_invested_capital:
            amount = tx.total_amount if hasattr(tx, "total_amount") else tx.get("total_amount")
            if amount:
                total += abs(Decimal(str(amount)))
    return total


# ── Model-specific calculators ─────────────────────────────────────────────────

def _calc_market(asset, db: Session, as_of: date) -> CurrentValueResult:
    """
    MARKET: stocks, ETF, crypto.

    Priority:
    1. latest ManualValuation         — user-entered value OR Base44 bootstrap snapshot
    2. quantity × current_price       — if quantity is known in extra_data
    3. current_price alone            — unit price only (low confidence)

    The user's manually entered value always wins.
    Base44 bootstrap snapshots are stored as ManualValuation rows with
    valuation_source='b44_snapshot' and will be superseded automatically
    when the user enters a newer value.
    """
    currency = asset.currency or "ILS"

    # Priority 1: latest manual valuation (covers both user entries and b44 bootstrap)
    val = get_latest_valuation(db, asset.id, as_of)
    if val and val.market_value:
        value_native = val.market_value
        value_ils = val.value_ils or (value_native * (val.fx_rate_to_ils or ONE))
        source = "manual_valuation" if val.valuation_source != "b44_snapshot" else "b44_snapshot_valuation"
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=val.currency or currency,
            fx_rate_used=val.fx_rate_to_ils or ONE,
            value_source=source,
            model_used=CalcModel.MARKET,
            confidence="high" if val.valuation_source != "b44_snapshot" else "medium",
        )

    # Priority 2: quantity × current_price
    # quantity comes from extra_data OR computed from transaction history
    # price comes from asset_price_history by date, fallback to asset.current_price
    current_price = _get_asset_price(db, asset, as_of)
    extra = asset.extra_data or {}
    quantity = extra.get("quantity") or extra.get("units")

    if not quantity:
        # Compute net quantity from transactions (sum of buys - sells)
        from app.models.transaction import Transaction
        from sqlalchemy import func as sqlfunc
        buy_types = ("buy", "vest", "allocation", "swap_in", "external_deposit")
        sell_types = ("sell", "swap_out", "external_withdrawal")
        txns = get_asset_transactions(db, asset.id, as_of)
        net = ZERO
        for tx in txns:
            qty = tx.quantity
            if not qty:
                continue
            qty = Decimal(str(qty))
            if tx.type in buy_types:
                net += qty
            elif tx.type in sell_types:
                net -= qty
        if net > ZERO:
            quantity = net

    if current_price and quantity:
        value_native = Decimal(str(current_price)) * Decimal(str(quantity))
        value_ils, fx = to_ils(value_native, currency, db, as_of)
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="market_price_x_quantity",
            model_used=CalcModel.MARKET,
            confidence="medium",
        )

    # Priority 3: current_price alone (unit price — no position size known)
    if current_price:
        value_native = Decimal(str(current_price))
        value_ils, fx = to_ils(value_native, currency, db, as_of)
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="market_price_unit_only",
            model_used=CalcModel.MARKET,
            confidence="low",
            warning="no valuation or quantity — current_price is unit price only",
        )

    return CurrentValueResult(
        value_native=None, value_ils=None, currency=currency,
        fx_rate_used=ONE, value_source="none",
        model_used=CalcModel.MARKET, confidence="low",
        warning="no valuation, quantity, or price found for MARKET asset",
    )


def _calc_fund(asset, db: Session, as_of: date) -> CurrentValueResult:
    """
    FUND: Kaspit / money-market funds, pension, keren hishtalmut.

    Value = current account balance in ILS. Changes from:
      - Manual valuations entered by the user (exact)
      - BUY/SELL transactions since last valuation (estimated delta)

    Priority:
      1. Latest ManualValuation (value_ils)
         + delta from BUY/SELL transactions AFTER the valuation date
            → confidence 'high' if no post-valuation txns
            → confidence 'medium' if txns exist (estimated)
      2. asset.current_price (Base44 snapshot)  → medium
      3. Sum of BUY/SELL transactions            → low
    """
    from app.models.transaction import Transaction

    currency = asset.currency or "ILS"

    # ── Step 1: Latest manual valuation ──────────────────────────────────────
    val = get_latest_valuation(db, asset.id, as_of)
    if val and (val.value_ils or val.market_value):
        # Prefer the pre-converted ILS value; fall back to market_value × fx
        if val.value_ils:
            base_value = Decimal(str(val.value_ils))
        else:
            base_value = Decimal(str(val.market_value)) * (
                Decimal(str(val.fx_rate_to_ils)) if val.fx_rate_to_ils else ONE
            )

        base_date = val.valuation_date

        # ── Look for BUY/SELL transactions AFTER the valuation ────────────
        post_txns = (
            db.query(Transaction)
            .filter(
                Transaction.asset_id == asset.id,
                Transaction.transaction_date > base_date,
                Transaction.transaction_date <= as_of,
                Transaction.economic_type.in_([
                    "BUY", "SELL", "DEPOSIT", "WITHDRAWAL",
                    "INVESTMENT_OUTFLOW", "INVESTMENT_INFLOW",
                ]),
            )
            .all()
        )

        if post_txns:
            delta = ZERO
            for tx in post_txns:
                eco = (tx.economic_type or "").upper()
                amount = abs(Decimal(str(tx.total_amount))) if tx.total_amount else ZERO
                if eco in ("BUY", "DEPOSIT", "INVESTMENT_OUTFLOW"):
                    delta += amount
                elif eco in ("SELL", "WITHDRAWAL", "INVESTMENT_INFLOW"):
                    delta -= amount

            estimated = base_value + delta
            log.info(
                "FUND %s: base=%s + delta=%s = %s (%d post-valuation txns)",
                asset.symbol, base_value, delta, estimated, len(post_txns),
            )
            return CurrentValueResult(
                value_native=estimated,
                value_ils=estimated,
                currency=currency,
                fx_rate_used=ONE,
                value_source="fund_estimated",
                model_used=CalcModel.FUND,
                confidence="medium",
                warning=(
                    f"Estimated: last valuation {base_date} + {len(post_txns)} "
                    f"transaction(s). Add a new valuation for exact value."
                ),
            )

        # No post-valuation transactions — valuation is current
        return CurrentValueResult(
            value_native=base_value,
            value_ils=base_value,
            currency=currency,
            fx_rate_used=val.fx_rate_to_ils or ONE,
            value_source="fund_valuation",
            model_used=CalcModel.FUND,
            confidence="high",
        )

    # ── Step 2: Base44 snapshot in asset.current_price ───────────────────────
    if asset.current_price:
        value_native = Decimal(str(asset.current_price))
        value_ils, fx = to_ils(value_native, currency, db, as_of)
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="asset_current_price_snapshot",
            model_used=CalcModel.FUND,
            confidence="medium",
            warning="no manual valuation — using Base44 snapshot price",
        )

    # ── Step 3: Transaction balance (rough estimate) ──────────────────────────
    txns = get_asset_transactions(db, asset.id, as_of)
    balance = ZERO
    for tx in txns:
        eco = (tx.economic_type or "").upper()
        amount = abs(Decimal(str(tx.total_amount))) if tx.total_amount else ZERO
        if eco in ("BUY", "DEPOSIT", "INVESTMENT_OUTFLOW"):
            balance += amount
        elif eco in ("SELL", "WITHDRAWAL", "INVESTMENT_INFLOW"):
            balance -= amount

    if balance != ZERO:
        value_ils, fx = to_ils(balance, currency, db, as_of)
        return CurrentValueResult(
            value_native=balance,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="fund_transactions",
            model_used=CalcModel.FUND,
            confidence="low",
            warning=(
                "No valuation found — using transaction sum. "
                "Add a manual valuation for accurate value."
            ),
        )

    return CurrentValueResult(
        value_native=None, value_ils=None, currency=currency,
        fx_rate_used=ONE, value_source="none",
        model_used=CalcModel.FUND, confidence="low",
        warning="no valuation or transactions found for FUND asset",
    )


def _calc_real_estate(asset, db: Session, as_of: date) -> CurrentValueResult:
    """
    REAL_ESTATE: operational property.
    Priority: latest ManualValuation → estimated_value in extra_data → purchase_price fallback
    """
    currency = asset.currency or "ILS"

    # Primary: latest manual valuation
    val = get_latest_valuation(db, asset.id, as_of)
    if val and val.market_value:
        value_native = val.market_value
        value_ils = val.value_ils or (value_native * (val.fx_rate_to_ils or ONE))
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=val.currency or currency,
            fx_rate_used=val.fx_rate_to_ils or ONE,
            value_source="manual_valuation",
            model_used=CalcModel.REAL_ESTATE,
            confidence="high",
        )

    # Fallback: estimated_value or property_value from metadata
    meta = asset.extra_data or {}
    estimated = meta.get("estimated_value") or meta.get("property_value") or meta.get("current_value")
    if estimated:
        value_native = Decimal(str(estimated))
        value_ils, fx = to_ils(value_native, currency, db, as_of)
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="metadata_estimated_value",
            model_used=CalcModel.REAL_ESTATE,
            confidence="medium",
            warning="no manual valuation — using metadata estimated value",
        )

    # Last resort: invested capital (purchase price as proxy)
    transactions = get_asset_transactions(db, asset.id, as_of)
    invested = sum_invested_capital(transactions)
    if invested > ZERO:
        value_ils, fx = to_ils(invested, currency, db, as_of)
        return CurrentValueResult(
            value_native=invested,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="cost_basis_fallback",
            model_used=CalcModel.REAL_ESTATE,
            confidence="low",
            warning="no valuation — using invested capital as current value proxy",
        )

    return CurrentValueResult(
        value_native=None, value_ils=None, currency=currency,
        fx_rate_used=ONE, value_source="none",
        model_used=CalcModel.REAL_ESTATE, confidence="low",
        warning="no valuation or transactions found",
    )


def _calc_real_estate_pipeline(asset, db: Session, as_of: date) -> CurrentValueResult:
    """
    REAL_ESTATE_PIPELINE: conservative — current_value = max(manual_valuation, invested_capital).
    Never use future contract price or expected delivery value.
    """
    currency = asset.currency or "ILS"

    transactions = get_asset_transactions(db, asset.id, as_of)
    invested = sum_invested_capital(transactions)

    # Check for explicit manual valuation
    val = get_latest_valuation(db, asset.id, as_of)
    val_amount = val.market_value if (val and val.market_value) else ZERO

    # Conservative rule: use whichever is higher, but never exceed contract_price
    meta = asset.extra_data or {}
    contract_price = Decimal(str(meta.get("contract_price", 0) or 0))

    if val_amount > ZERO:
        # Sanity check: warn if valuation seems overstated
        warning = None
        if contract_price > ZERO and val_amount > contract_price:
            warning = "pipeline_value_may_be_overstated: valuation exceeds contract_price"

        value_native = max(val_amount, invested)
        value_ils_val = val.value_ils if val else None
        if not value_ils_val:
            value_ils_val, fx = to_ils(value_native, val.currency if val else currency, db, as_of)
        else:
            fx = val.fx_rate_to_ils or ONE

        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils_val,
            currency=val.currency if val else currency,
            fx_rate_used=fx,
            value_source="pipeline_manual_valuation",
            model_used=CalcModel.REAL_ESTATE_PIPELINE,
            confidence="medium",
            warning=warning,
        )

    # No valuation: use invested capital (what we've actually paid so far)
    if invested > ZERO:
        value_ils, fx = to_ils(invested, currency, db, as_of)
        return CurrentValueResult(
            value_native=invested,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="invested_capital_conservative",
            model_used=CalcModel.REAL_ESTATE_PIPELINE,
            confidence="medium",
        )

    return CurrentValueResult(
        value_native=ZERO, value_ils=ZERO, currency=currency,
        fx_rate_used=ONE, value_source="zero_no_payments_yet",
        model_used=CalcModel.REAL_ESTATE_PIPELINE, confidence="high",
    )


def _calc_manual(asset, db: Session, as_of: date) -> CurrentValueResult:
    """
    MANUAL: whisky casks, land, collectibles.
    Priority: latest ManualValuation → asset metadata current_value → invested_capital fallback
    """
    currency = asset.currency or "ILS"

    # Primary: latest manual valuation
    val = get_latest_valuation(db, asset.id, as_of)
    if val and val.market_value:
        value_native = val.market_value
        value_ils = val.value_ils or (value_native * (val.fx_rate_to_ils or ONE))
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=val.currency or currency,
            fx_rate_used=val.fx_rate_to_ils or ONE,
            value_source="manual_valuation",
            model_used=CalcModel.MANUAL,
            confidence="high",
        )

    # Fallback: current_value from metadata (Base44 snapshot)
    meta = asset.extra_data or {}
    meta_val = meta.get("current_value")
    if meta_val:
        value_native = Decimal(str(meta_val))
        value_ils, fx = to_ils(value_native, currency, db, as_of)
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="metadata_current_value",
            model_used=CalcModel.MANUAL,
            confidence="medium",
            warning="no manual valuation — using metadata snapshot value",
        )

    # Last resort: invested capital
    transactions = get_asset_transactions(db, asset.id, as_of)
    invested = sum_invested_capital(transactions)
    if invested > ZERO:
        value_ils, fx = to_ils(invested, currency, db, as_of)
        return CurrentValueResult(
            value_native=invested,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="cost_basis_fallback",
            model_used=CalcModel.MANUAL,
            confidence="low",
            warning="no valuation — using invested capital as current value proxy",
        )

    return CurrentValueResult(
        value_native=None, value_ils=None, currency=currency,
        fx_rate_used=ONE, value_source="none",
        model_used=CalcModel.MANUAL, confidence="low",
        warning="no valuation or transactions found for MANUAL asset",
    )


def _calc_energy_income(asset, db: Session, as_of: date) -> CurrentValueResult:
    """
    ENERGY_INCOME: solar panels.
    Priority: latest ManualValuation → metadata current_value → invested_capital
    """
    # Same logic as MANUAL but with different model tag
    result = _calc_manual(asset, db, as_of)
    result.model_used = CalcModel.ENERGY_INCOME
    return result


def _calc_cash_or_debt(asset, db: Session, as_of: date) -> CurrentValueResult:
    """
    CASH_OR_DEBT: BTB, money market, deposits, P2P loans.
    Priority: latest ManualValuation → deposits - withdrawals + accrued income
    """
    currency = asset.currency or "ILS"

    # Primary: latest manual valuation
    val = get_latest_valuation(db, asset.id, as_of)
    if val and val.market_value:
        value_native = val.market_value
        value_ils = val.value_ils or (value_native * (val.fx_rate_to_ils or ONE))
        return CurrentValueResult(
            value_native=value_native,
            value_ils=value_ils,
            currency=val.currency or currency,
            fx_rate_used=val.fx_rate_to_ils or ONE,
            value_source="manual_valuation",
            model_used=CalcModel.CASH_OR_DEBT,
            confidence="high",
        )

    # Fallback: deposits - withdrawals + income
    transactions = get_asset_transactions(db, asset.id, as_of)
    balance = ZERO
    for tx in transactions:
        flags = classify_transaction(tx)
        amount = tx.total_amount if hasattr(tx, "total_amount") else tx.get("total_amount")
        if not amount:
            continue
        amount = Decimal(str(amount))
        if flags.affects_invested_capital:
            balance += amount
        elif flags.reduces_invested_capital:
            balance -= amount
        elif flags.affects_income:
            balance += amount
        elif flags.affects_operating_expense or flags.affects_financing_cost:
            balance -= amount

    if balance > ZERO:
        value_ils, fx = to_ils(balance, currency, db, as_of)
        return CurrentValueResult(
            value_native=balance,
            value_ils=value_ils,
            currency=currency,
            fx_rate_used=fx,
            value_source="transaction_balance",
            model_used=CalcModel.CASH_OR_DEBT,
            confidence="medium",
            warning="no manual valuation — derived from transaction history",
        )

    return CurrentValueResult(
        value_native=None, value_ils=None, currency=currency,
        fx_rate_used=ONE, value_source="none",
        model_used=CalcModel.CASH_OR_DEBT, confidence="low",
        warning="no valuation or transactions found",
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def calc_current_value(asset, db: Session, snapshot_date: Optional[date] = None) -> CurrentValueResult:
    """
    Calculate the current value of an asset as of snapshot_date.

    Args:
        asset:          SQLAlchemy Asset ORM object
        db:             Active database session
        snapshot_date:  Date to calculate as of (defaults to today)

    Returns:
        CurrentValueResult with value_native, value_ils, confidence, source, warning
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    model = resolve_model(asset)

    calculators = {
        CalcModel.MARKET:               _calc_market,
        CalcModel.FUND:                 _calc_fund,
        CalcModel.REAL_ESTATE:          _calc_real_estate,
        CalcModel.REAL_ESTATE_PIPELINE: _calc_real_estate_pipeline,
        CalcModel.MANUAL:               _calc_manual,
        CalcModel.ENERGY_INCOME:        _calc_energy_income,
        CalcModel.CASH_OR_DEBT:         _calc_cash_or_debt,
    }

    calculator = calculators.get(model, _calc_manual)

    try:
        result = calculator(asset, db, snapshot_date)
    except Exception as e:
        log.error("calc_current_value failed for asset %s (model=%s): %s", getattr(asset, "id", "?"), model, e)
        result = CurrentValueResult(
            value_native=None, value_ils=None,
            currency=getattr(asset, "currency", "ILS") or "ILS",
            fx_rate_used=ONE, value_source="error",
            model_used=model, confidence="low",
            warning=f"engine error: {e}",
        )

    if result.warning:
        log.warning("Asset %s (%s) [%s]: %s", getattr(asset, "symbol", "?"), getattr(asset, "name", "?"), model, result.warning)

    return result
