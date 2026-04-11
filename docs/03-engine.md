# Wealth OS — Calculation Engine

## Overview

The engine is a pure Python calculation layer that takes raw data (transactions, valuations, prices) and produces portfolio performance metrics. It has no side effects during calculation — it reads from DB, computes in memory, and returns results. Persistence is handled by the snapshot builder after computation.

**Location:** `backend/app/engine/`

---

## CalcModel — Asset Calculation Models

Every asset is assigned a `CalcModel` based on its `asset_behavior` field. The model determines which calculation strategy is used.

```python
class CalcModel(Enum):
    MARKET               # Stocks, ETFs, crypto — price × quantity
    FUND                 # Pension, keren hishtalmut — total fund value
    REAL_ESTATE          # Operational property — manual appraisal
    REAL_ESTATE_PIPELINE # Under construction — conservative (invested capital)
    MANUAL               # Whisky, land — manual valuation only
    ENERGY_INCOME        # Solar panels — same as MANUAL
    CASH_OR_DEBT         # BTB, deposits, loans — balance calculation
```

### Model assignment (`model_resolver.py`)

```
asset_behavior = MARKET              → CalcModel.MARKET
asset_behavior = FUND                → CalcModel.FUND
asset_behavior = REAL_ESTATE         → CalcModel.REAL_ESTATE or REAL_ESTATE_PIPELINE
asset_behavior = MANUAL              → CalcModel.MANUAL
asset_behavior = CASH_OR_DEBT        → CalcModel.CASH_OR_DEBT
asset_behavior = ENERGY_INCOME       → CalcModel.ENERGY_INCOME
```

### Your portfolio breakdown
| Category | Assets | Model |
|----------|--------|-------|
| Real estate | Apartments, land | REAL_ESTATE / REAL_ESTATE_PIPELINE |
| Pension | Migdal, Phoenix funds | FUND |
| Securities | CSCO, MSFT, VWRA, IBO1 | MARKET |
| Crypto | BTC, ETH | MARKET |
| Alternatives | BTB, Whisky | CASH_OR_DEBT / MANUAL |
| Solar | Solar panels | ENERGY_INCOME |
| Cash | IBI כספית | CASH_OR_DEBT |

---

## Current Value Calculation (`current_value.py`)

### MARKET model priority chain

```
1. ManualValuation (latest on or before snapshot_date)
   → Used when: user manually entered a value, or Base44 bootstrap
   → Confidence: high (user entry) / medium (b44_snapshot)

2. asset_price_history price × quantity
   → Price lookup: query asset_price_history WHERE date <= snapshot_date
   → Quantity: from extra_data["quantity"] OR computed from transactions
   → Confidence: medium
   
3. asset.current_price × quantity (fallback)
   → Uses hot cache on asset table
   → Confidence: medium

4. asset.current_price alone (no quantity known)
   → Unit price only — not portfolio value
   → Confidence: low
   → Warning: "no valuation or quantity — current_price is unit price only"

5. None
   → Warning: "no valuation, quantity, or price found"
```

### Quantity computation from transactions
When `extra_data["quantity"]` is not set, the engine sums transaction quantities:
```python
net_quantity = sum(qty for BUY/VEST/ALLOCATION transactions)
             - sum(qty for SELL transactions)
```
Only used if net_quantity > 0.

### FUND model priority chain
```
1. ManualValuation → value_ils
2. asset.current_price (treated as total fund value, not unit price)
3. None
```

### REAL_ESTATE model priority chain
```
1. ManualValuation → value_ils
2. extra_data["estimated_value"] or ["property_value"] or ["current_value"]
3. Sum of invested capital (cost basis as proxy) — low confidence
4. None
```

### REAL_ESTATE_PIPELINE (under construction)
```
Conservative: max(ManualValuation, invested_capital)
Never exceeds contract_price
Used for: properties not yet delivered
```

### MANUAL model (whisky, land, collectibles)
```
1. ManualValuation → value_ils
2. extra_data["current_value"] (Base44 snapshot fallback)
3. Invested capital (cost basis proxy) — low confidence
4. None
```

### CASH_OR_DEBT (BTB, deposits, money market)
```
1. ManualValuation → value_ils
2. Computed balance: sum(deposits + income) - sum(withdrawals + expenses + fees)
3. None
```

### ENERGY_INCOME (solar)
Same logic as MANUAL — requires manual valuation entries.

---

## FX Rate Lookup

All values are ultimately converted to ILS.

```python
def get_fx_rate(db, from_currency, to_currency, as_of_date):
    # 1. Query fx_rates WHERE date <= as_of_date
    # 2. Order by date DESC, take most recent
    # 3. Fallback: return 1.0 with warning if no rate found
```

**FX rates are populated by:** ECB FX connector (frankfurter.app)
**Rates stored:** USD→ILS, EUR→ILS, GBP→ILS (configurable)

---

## Asset Price Lookup

```python
def _get_asset_price(db, asset, as_of_date):
    # 1. Query asset_price_history WHERE asset_id = X AND date <= as_of_date
    # 2. Order by date DESC, take most recent
    # 3. Fallback: asset.current_price (hot cache)
    # 4. Returns None if neither exists
```

This enables historical snapshots — asking "what was my portfolio worth on March 1st?" uses the March 1st price from history, not today's price.

---

## Cost Basis Calculation (`cost_basis.py`)

```python
def calc_cost_basis(transactions, model):
    # Sum of all BUY-type transactions (investment outflows)
    # Excludes: income, dividends, loan proceeds
    # Includes: purchase price + fees
```

### Transaction classification
Each transaction is classified by `economic_type`:

| Economic Type | affects_invested_capital | affects_income | reduces_invested_capital |
|---------------|--------------------------|----------------|--------------------------|
| BUY | ✓ | | |
| INVESTMENT_OUTFLOW | ✓ | | |
| SELL | | | ✓ |
| INVESTMENT_INFLOW | | | ✓ |
| INCOME | | ✓ | |
| EXPENSE | | | |
| FINANCING_INFLOW | ✓ (loan) | | |
| FINANCING_OUTFLOW | | | ✓ (repayment) |

---

## XIRR Calculation (`xirr.py`)

XIRR (Extended Internal Rate of Return) = annualized return accounting for timing of cashflows.

```
For each asset:
  cashflows = [(-invested_amount, date_invested), ..., (current_value, today)]
  xirr = Newton-Raphson iteration to find rate r where NPV = 0
```

**Sign convention (from portfolio perspective):**
- Money out (BUY, expense) = negative cashflow
- Money in (SELL, income, current_value) = positive cashflow

**Fallback:** If XIRR fails to converge (e.g. insufficient data, all same date), returns None.

---

## Snapshot Builder (`snapshot_builder.py`)

Orchestrates the full portfolio computation.

```python
def build_portfolio_snapshot(portfolio_id, db, snapshot_date):
    assets = get_all_active_assets(portfolio_id)
    
    for asset in assets:
        snap = build_asset_snapshot(asset, db, snapshot_date)
    
    category_snapshots = aggregate_by_category(asset_snapshots)
    
    portfolio_totals = {
        total_value_ils:    sum(asset.value_ils),
        total_invested_ils: sum(asset.cost_basis),
        total_debt_ils:     sum(asset.debt_balance),  # mortgages, loans
        net_equity_ils:     total_value - total_debt,
        total_return_ils:   total_value - total_invested,
        total_return_pct:   total_return / total_invested,
    }
    
    return PortfolioSnapshotResult
```

### Persistence
After computation, the router persists to `performance_snapshots`:
```python
for snap in result.asset_snapshots:
    # Delete existing row for this asset + date (upsert pattern)
    # Insert new row with computed values
db.commit()
```

**Multiple runs same day:** Last run wins. The delete+insert ensures no duplicate rows.

---

## Snapshot API

### Rebuild (slow — runs engine)
```
POST /api/v1/snapshots/rebuild
Body: { portfolio_id, as_of_date? }

- Runs full engine in thread pool (sync engine, async API)
- Saves results to performance_snapshots
- Returns snapshot JSON
- Used by: "Build Snapshot" button, scheduled ETL
```

### Latest (fast — reads from DB)
```
GET /api/v1/snapshots/latest?portfolio_id=...

- Reads performance_snapshots table directly
- Groups by latest snapshot_date
- Returns same JSON format as rebuild
- Used by: dashboard on page load
- Returns null if no snapshot has been built
```

---

## Confidence Scoring

Every asset snapshot has a confidence level: `high`, `medium`, or `low`.

| Condition | Confidence |
|-----------|------------|
| Manual valuation + invested capital known + no warnings | high |
| Manual valuation OR market price with quantity | medium |
| Price only (no quantity) OR cost basis fallback | low |
| No data at all | low |

Low confidence assets show warnings in the snapshot that help identify data quality issues.

---

## Common Warnings

| Warning | Cause | Fix |
|---------|-------|-----|
| "no valuation or quantity — current_price is unit price only" | MARKET asset has price but no quantity or ManualValuation | Add transactions with quantity OR add ManualValuation |
| "no valuation or transactions found" | Asset has no data at all | Add transactions or ManualValuation |
| "FX rate not found: USD→ILS" | No FX rates in DB for that date | Run ECB FX connector |
| "engine error: ..." | Unexpected exception during calculation | Check logs |
