# Wealth OS — Data Model

## Overview

All tables are in a single PostgreSQL schema on Supabase.
UUIDs are used for all primary keys (gen_random_uuid()).
All timestamps are timezone-aware.

---

## Entity Relationship (simplified)

```
portfolios
  └── accounts (1:many)
  └── assets (1:many)
        └── transactions (1:many)
        └── manual_valuations (1:many)
        └── asset_price_history (1:many)
        └── performance_snapshots (1:many)
  └── connectors (1:many)
        └── connector_runs (1:many)
  └── performance_snapshots (1:many)
fx_rates (standalone — no portfolio FK)
```

---

## Tables

### `portfolios`
The top-level container. Everything belongs to a portfolio.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| name | VARCHAR(200) | e.g. "Tomer Portfolio Clean" |
| base_currency | VARCHAR(10) | Default: "ILS" |
| description | TEXT | Optional |
| is_default | BOOLEAN | |
| owner_id | VARCHAR | For future multi-user support |

**Your main portfolio:** `53f8f313-98e8-5de3-bd64-55826cbd82bb`

---

### `accounts`
Brokerage accounts, bank accounts, pension funds — containers for assets.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| portfolio_id | UUID FK | |
| name | VARCHAR(200) | e.g. "Interactive Brokers Israel" |
| symbol | VARCHAR(100) | Unique identifier |
| account_type | VARCHAR(50) | brokerage, bank, pension, etc. |
| category | VARCHAR(50) | Matches asset categories |
| currency | VARCHAR(10) | Base currency of account |
| institution | VARCHAR | e.g. "Interactive Brokers" |
| status | VARCHAR(20) | **Free string** — legacy data has 'imported' |
| cash_balance | NUMERIC(18,4) | Current cash in account |
| extra_data | JSONB | Stored as `metadata` column in DB |
| include_in_portfolio | BOOLEAN | |

**Note:** `extra_data` in Python maps to `metadata` column in DB (SQLAlchemy MetaData collision).

---

### `assets`
Individual investable assets — stocks, properties, crypto, pension funds, etc.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| portfolio_id | UUID FK | |
| account_id | UUID FK | Optional — which account holds this |
| name | VARCHAR(300) | Full name |
| symbol | VARCHAR(100) | Unique per portfolio |
| asset_behavior | VARCHAR(50) | **MARKET / MANUAL / FUND / CASH_OR_DEBT / REAL_ESTATE / LOAN** |
| category | VARCHAR(50) | real_estate, pension, securities, alternatives, cash, crypto, etc. |
| asset_type | VARCHAR(50) | security, fund, property, etc. |
| status | VARCHAR(20) | **Free string** — 'active', 'inactive', 'closed', 'imported' |
| currency | VARCHAR(10) | Native currency |
| exchange | VARCHAR(50) | e.g. NASDAQ, TASE |
| current_price | NUMERIC(18,6) | **Hot cache** — latest price only, updated by Yahoo connector |
| price_updated_at | TIMESTAMP | When current_price was last updated |
| pricing_mode | VARCHAR(50) | manual_valuation, market_price, transaction_based |
| is_manual | BOOLEAN | False = connector-managed |
| extra_data | JSONB | Stored as `metadata` column. May contain `quantity`, `units`, `current_value` |

**Critical:** `extra_data["quantity"]` is used by the engine as a fallback for position size when transaction quantities are missing.

---

### `transactions`
Every financial event — buys, sells, income, expenses, transfers.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| portfolio_id | UUID FK | |
| account_id | UUID FK | Optional |
| asset_id | UUID FK | Optional — some transactions aren't asset-specific |
| transaction_date | DATE | Python attribute mapped from `date` DB column |
| effective_date | DATE | Optional settlement date |
| type | VARCHAR(50) | buy, sell, income, expense, deposit, withdrawal, dividend, etc. |
| economic_type | VARCHAR(50) | **BUY, SELL, INCOME, EXPENSE, FINANCING_INFLOW, etc.** — critical for XIRR |
| domain | VARCHAR(50) | **Free string** — real_estate, securities, crypto, loan, solar, etc. |
| total_amount | NUMERIC(18,4) | Total value of transaction |
| cashflow_amount | NUMERIC(18,4) | Normalized cashflow for XIRR calculation |
| currency | VARCHAR(10) | |
| quantity | NUMERIC(18,8) | Units bought/sold |
| price_per_unit | NUMERIC(18,6) | |
| units_delta | NUMERIC(18,8) | Net change in position (not used by engine currently) |
| fees | NUMERIC(18,4) | |
| tax | NUMERIC(18,4) | |
| status | VARCHAR(20) | **Free string** — confirmed, pending, cancelled, **imported** |
| source | VARCHAR(50) | manual, import, connector |
| is_internal_transfer | BOOLEAN | |
| external_reference_id | VARCHAR(200) | Broker reference — used for deduplication |

**Known legacy data issues:**
- `status = 'imported'` — from Base44 import, not in enum
- `domain = 'loan'` — not in TransactionDomain enum
- `quantity = null` — many IB transactions imported without quantity

---

### `manual_valuations`
Point-in-time valuations for assets that don't have market prices.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| portfolio_id | UUID FK | |
| asset_id | UUID FK | |
| account_id | UUID FK | Optional |
| valuation_date | DATE | Python attribute mapped from `date` DB column |
| market_value | NUMERIC(18,4) | Value in native currency |
| currency | VARCHAR(10) | |
| fx_rate_to_ils | NUMERIC(10,6) | FX rate at valuation time |
| value_ils | NUMERIC(18,4) | Computed: market_value × fx_rate |
| valuation_method | VARCHAR(50) | **Free string** — manual, appraisal, broker_estimate, model, **derived** |
| confidence_level | VARCHAR(20) | low, medium, high |
| valuation_source | VARCHAR(100) | e.g. "b44_snapshot", "manual" |
| is_estimated | BOOLEAN | |
| source | VARCHAR(50) | manual, import, connector |

**Note:** `valuation_method` is a free string in Read schemas because legacy data contains `'derived'` which is not in the ValuationMethod enum.

**Input to engine** — the engine reads from this table but never writes to it.

---

### `fx_rates`
Daily exchange rates. Used by engine to convert asset values to ILS.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| fx_date | DATE | Python attribute mapped from `date` DB column |
| from_currency | VARCHAR(10) | e.g. "USD" |
| to_currency | VARCHAR(10) | e.g. "ILS" |
| rate | NUMERIC(12,6) | How many `to_currency` per 1 `from_currency` |
| source | VARCHAR(50) | ecb, manual, etc. |

**Unique constraint:** `(date, from_currency, to_currency)`
**Populated by:** ECB FX connector (frankfurter.app API)

---

### `asset_price_history`
Historical daily prices per asset. Permanent record — never overwritten.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| asset_id | UUID FK | |
| portfolio_id | UUID FK | Denormalized for easy query |
| price_date | DATE | |
| price | NUMERIC(18,6) | Closing price |
| currency | VARCHAR(10) | Native currency of price |
| source | VARCHAR(50) | yahoo, tase, coingecko, manual |
| open | NUMERIC(18,6) | Optional OHLC |
| high | NUMERIC(18,6) | |
| low | NUMERIC(18,6) | |
| volume | NUMERIC(24,4) | |

**Unique constraint:** `(asset_id, price_date, source)`
**Populated by:** Yahoo prices connector
**Read by:** Engine `_get_asset_price()` — queries most recent price on or before snapshot_date

---

### `performance_snapshots`
Computed portfolio results — one row per asset per date.
**Output of the engine** — written by snapshot builder, read by dashboard.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| portfolio_id | UUID FK | |
| asset_id | UUID FK | |
| account_id | UUID FK | Optional |
| snapshot_date | DATE | |
| invested_capital | NUMERIC(18,4) | Cost basis in ILS |
| current_value | NUMERIC(18,4) | Current value (native currency) |
| value_ils | NUMERIC(18,4) | Current value in ILS |
| total_return | NUMERIC(18,4) | Absolute gain/loss in ILS |
| total_return_pct | NUMERIC(10,6) | Return as decimal (0.209 = 20.9%) |
| annual_return_pct | NUMERIC(10,6) | Annualized return |
| xirr_return_pct | NUMERIC(10,6) | XIRR |
| model_used | VARCHAR(50) | Which CalcModel was used |
| is_stale | BOOLEAN | True if prices have changed since last build |
| currency | VARCHAR(10) | Default "ILS" |

**Unique constraint:** `(portfolio_id, asset_id, snapshot_date)`
**Multiple runs same day:** Delete + insert (last run wins)

---

### `connectors`
ETL connector configuration — one row per connected data source.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| portfolio_id | UUID FK | |
| name | VARCHAR(200) | Display name e.g. "Kraken BTC" |
| type | VARCHAR(50) | ecb_fx, yahoo_prices, kraken, cexio, etc. |
| config | JSONB | **Encrypted** API keys + settings |
| asset_filter | JSONB | null = all assets, ["BTC","ETH"] = specific |
| auto_create_assets | BOOLEAN | Create new assets when connector sees unknown symbols |
| schedule | VARCHAR(50) | daily, hourly, manual |
| is_active | BOOLEAN | |
| last_run_at | TIMESTAMP | |
| last_error | TEXT | Last error message if failed |

**Security:** Sensitive config fields (api_key, api_secret, password, token) are encrypted at rest using Fernet symmetric encryption. Key stored in Railway env var `CONNECTOR_ENCRYPTION_KEY`.

---

### `connector_runs`
Execution history — one row per connector run.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| connector_id | UUID FK | |
| portfolio_id | UUID FK | Denormalized |
| status | VARCHAR(20) | pending, running, success, failed, partial |
| triggered_by | VARCHAR(20) | scheduler, manual, api |
| started_at | TIMESTAMP | |
| finished_at | TIMESTAMP | |
| duration_ms | INTEGER | |
| records_fetched | INTEGER | Raw records from source |
| transactions_created | INTEGER | |
| transactions_skipped | INTEGER | Duplicates |
| assets_created | INTEGER | Auto-discovered new assets |
| fx_rates_updated | INTEGER | |
| prices_updated | INTEGER | |
| error_message | TEXT | |
| error_traceback | TEXT | Full stack trace |
| checkpoint | JSONB | Resumable state e.g. `{"since": 1700000000}` |

---

## Important Conventions

### 1. `extra_data` vs `metadata`
Python attribute is always `extra_data`. DB column is always `metadata` (legacy name). SQLAlchemy mapped with `mapped_column("metadata", JSONB)`.

```python
# Correct
asset.extra_data = {"quantity": 100}

# Wrong — will conflict with SQLAlchemy MetaData class
asset.metadata = {"quantity": 100}
```

### 2. Date column aliases
Several models have Python attributes that differ from DB column names:
- `Transaction.transaction_date` → DB column `date`
- `ManualValuation.valuation_date` → DB column `date`
- `FXRate.fx_date` → DB column `date`

This avoids shadowing Python's built-in `date`.

### 3. Enums vs free strings in Read schemas
Read schemas use `str` for fields where legacy imported data has values outside the enum:

| Field | Enum values | Legacy values found |
|-------|-------------|---------------------|
| `Transaction.status` | confirmed, pending, cancelled | **imported** |
| `Transaction.domain` | real_estate, securities, ... | **loan** |
| `ManualValuation.valuation_method` | manual, appraisal, ... | **derived** |
| `Asset.status` | active, inactive, closed | **imported** |

**Rule:** Create/Update schemas keep enums for validation. Read schemas use `str`.

### 4. Return percentages
API returns decimals. Multiply × 100 for display:
```typescript
// API: total_return_pct = 0.209
// Display: "20.9%"
const displayPct = summary.total_return_pct * 100
```

### 5. Trailing slashes
All FastAPI endpoints require trailing slash to avoid 307 redirects:
```typescript
// Correct
apiClient.get('/api/v1/assets/')

// Wrong — causes 307 redirect which may break CORS
apiClient.get('/api/v1/assets')
```
