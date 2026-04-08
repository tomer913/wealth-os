# Wealth OS – Portfolio Management System
## CLAUDE.md – Project Instructions & Architecture

---

## Project Goal

Build a production-grade **Wealth Operating System** – a multi-asset personal portfolio tracker with:
- Full control over business logic and calculations
- Reliable performance engine (snapshot-based)
- Multi-asset-class support with different return models per asset type
- Clean API-first architecture

This is **not a trading platform**. It is a Wealth OS: net worth visibility, performance tracking, allocation analysis.

---

## Tech Stack

| Layer      | Technology         | Hosting        |
|------------|--------------------|----------------|
| Backend    | FastAPI + Python   | Railway/Render |
| Database   | PostgreSQL         | Supabase       |
| Frontend   | Next.js            | Vercel         |
| ORM        | SQLAlchemy + Alembic |              |
| Auth       | Supabase Auth      |                |

---

## Architecture Principles

1. **Thin UI** – Frontend is display + CRUD only. No financial logic in the frontend.
2. **All logic in backend** – return calculations, cost basis, FX conversion, snapshots.
3. **Snapshot-first** – UI reads from pre-computed `performance_snapshots`. Never compute on render.
4. **JSON-first + extensible schema** – `metadata JSONB` column on assets and accounts for type-specific fields.
5. **No single return model** – Different asset types use different calculation models.

---

## Project Structure

```
wealth-os/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── portfolio.py
│   │   │   ├── account.py
│   │   │   ├── asset.py
│   │   │   ├── transaction.py
│   │   │   ├── valuation.py
│   │   │   ├── fx_rate.py
│   │   │   ├── snapshot.py
│   │   │   └── position.py
│   │   ├── schemas/
│   │   │   ├── portfolio.py
│   │   │   ├── account.py
│   │   │   ├── asset.py
│   │   │   ├── transaction.py
│   │   │   ├── valuation.py
│   │   │   └── snapshot.py
│   │   ├── routers/
│   │   │   ├── portfolios.py
│   │   │   ├── accounts.py
│   │   │   ├── assets.py
│   │   │   ├── transactions.py
│   │   │   ├── valuations.py
│   │   │   ├── snapshots.py
│   │   │   └── dashboard.py
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── model_resolver.py      # resolveModel(asset) -> AssetModel enum
│   │   │   ├── cost_basis.py          # computeInvestedCapital(asset, transactions)
│   │   │   ├── current_value.py       # resolveCurrentValue(asset, valuations, prices)
│   │   │   ├── performance.py         # calcPositionReturn(...)
│   │   │   ├── xirr.py                # XIRR calculation
│   │   │   ├── fx.py                  # FX conversion utilities
│   │   │   └── snapshot_builder.py    # buildSnapshot(portfolio_id, date)
│   │   ├── importers/
│   │   │   ├── base44_importer.py     # Import from Base44 JSON exports
│   │   │   └── csv_importer.py
│   │   └── utils/
│   │       ├── taxonomy.py            # Transaction type taxonomy
│   │       └── enums.py               # All system enums
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
└── frontend/   (Next.js – separate repo or monorepo)
```

---

## Data Models

### Asset Behavior Enum (CRITICAL)
```python
class AssetBehavior(str, Enum):
    MARKET = "MARKET"               # stocks, ETF, crypto – market price feed
    FUND = "FUND"                   # pension, insurance, keren hishtalmut
    MANUAL = "MANUAL"               # whisky casks, land, alternatives
    REAL_ESTATE = "REAL_ESTATE"     # operational real estate with cashflows
    REAL_ESTATE_PIPELINE = "REAL_ESTATE_PIPELINE"  # under construction
    ENERGY_INCOME = "ENERGY_INCOME" # solar / special income assets
    NO_RETURN = "NO_RETURN"         # pure placeholder / not tracked
```

### Asset Category Enum
```python
class AssetCategory(str, Enum):
    SECURITIES = "securities"       # stocks, ETF
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"
    PENSION = "pension"             # pension, bituach menahalim, keren hishtalmut
    ALTERNATIVES = "alternatives"   # whisky, art, collectibles
    DEBT_INCOME = "debt_income"     # BTB, loans
    SPECIAL_INCOME = "special_income"  # solar
    CASH = "cash"
```

### Transaction Economic Type (CRITICAL for IRR)
```python
class EconomicType(str, Enum):
    # Capital in
    INVESTMENT = "investment"           # initial capital outflow
    ACQUISITION_COST = "acquisition_cost"  # purchase tax, lawyer, broker – part of cost basis
    
    # Income
    RENTAL_INCOME = "rental_income"
    DIVIDEND = "dividend"
    INTEREST_INCOME = "interest_income"
    OTHER_INCOME = "other_income"
    
    # Operating expenses
    OPERATING_EXPENSE = "operating_expense"  # maintenance, insurance, storage
    
    # Financing – MUST distinguish principal vs interest
    LOAN_DRAWDOWN = "loan_drawdown"          # money received from loan
    PRINCIPAL_PAYMENT = "principal_payment"  # reduces debt, NOT expense
    INTEREST_PAYMENT = "interest_payment"    # IS expense
    
    # Capital out
    SALE_PROCEEDS = "sale_proceeds"
    
    # Non-cashflow
    REVALUATION = "revaluation"              # valuation event, no cash
```

---

## Engine Logic

### Model Resolution
```python
def resolve_model(asset: Asset) -> AssetBehavior:
    """
    Determines calculation model for an asset.
    Priority: explicit asset_behavior field > inferred from type/category
    """
    if asset.asset_behavior:
        return AssetBehavior(asset.asset_behavior)
    # fallback inference logic...
```

### Invested Capital Rules by Model

| Model | Invested Capital Includes |
|-------|--------------------------|
| MARKET | buy transactions (cost basis) |
| FUND | sum of contributions OR latest manual baseline |
| REAL_ESTATE | purchase price + acquisition_costs (tax, lawyer, broker, initial renovation) |
| REAL_ESTATE_PIPELINE | actual equity paid to date (NOT contract price, NOT future mortgage) |
| MANUAL | purchase price + ongoing carrying costs |
| ENERGY_INCOME | initial investment outflow |

### Current Value Rules by Model

| Model | Current Value Source |
|-------|---------------------|
| MARKET | current_price × quantity |
| FUND | latest manual_valuation |
| REAL_ESTATE | latest manual_valuation (property estimate) |
| REAL_ESTATE_PIPELINE | invested_capital (conservative – no speculative gain) |
| MANUAL | latest manual_valuation |
| ENERGY_INCOME | latest manual_valuation |

### XIRR – Critical Rules
- Use actual cashflow dates, never aggregate
- Include all outflows (negative) and inflows (positive)
- Terminal value = current_value as final inflow at today's date
- Exclude PRINCIPAL_PAYMENT from IRR cashflows (it's balance sheet, not P&L)
- Include INTEREST_PAYMENT as outflow

---

## Migration from Base44

### What exists in Base44 (confirmed from JSON exports)
- **Portfolios**: 2 portfolios, main one is "Tomer Portfolio Clean"
- **Assets**: 30+ assets across all categories
  - Pension/funds: 4 (Migdal x3, Phoenix x1)
  - Real estate: 5+ (Kochav Yair, TA, Beer Sheva, Ramat Gan pipeline, Porto pipeline)
  - Whisky casks: 3 (Linkwood, Staoisha, Ledaig)
  - Land: Binyamina agricultural
  - Market: AAPL, GOOGL, VOO, SOL, LUMI, + others
  - BTB, Meniyot Track, Solar
- **Accounts**: 15+ accounts (brokerages, pension, whisky warehouses, real estate)
- **Transactions**: 2000+ rows
- **Valuations**: pension + real estate manual valuations

### Base44 Schema Issues to Fix

| Issue | Fix |
|-------|-----|
| `metadata` stored as JSON string, not JSONB | Parse and store as proper JSONB |
| `asset_class` inconsistent (pension with `stocks` class) | Use `category` field as source of truth |
| `symbol` only on assets, not on accounts (buried in metadata) | Add `symbol` column to accounts table |
| `current_value` stored in asset metadata | Move to `manual_valuations` table |
| No `lifecycle_stage` field | Add to assets |
| Accounts missing `is_liquid`, `is_income_generating` as real columns | Promote from metadata to real columns |
| No cost_basis distinction for acquisition costs vs operating expenses | Use `economic_type` taxonomy strictly |

---

## Database Schema (Postgres / Supabase)

See: `alembic/versions/001_initial_schema.py`

Key tables:
- `portfolios`
- `accounts` – with `symbol`, `is_liquid`, `is_income_generating` as real columns
- `assets` – with `asset_behavior`, `category`, `lifecycle_stage` as real columns
- `transactions` – with `economic_type`, `domain` as real columns
- `manual_valuations`
- `fx_rates`
- `performance_snapshots`
- `positions` (optional derived state)

---

## Dashboard Filter Requirements

The dashboard MUST support these views:

| Filter | Logic |
|--------|-------|
| Full Portfolio | All active assets |
| Ex Real Estate | category != real_estate |
| Liquid Only | account.is_liquid = true |
| Income Generating | account.is_income_generating = true OR asset generates regular cashflows |
| Managed Funds | asset_behavior IN (FUND) |
| Alternatives | category = alternatives |

---

## Build Order (Phases)

### Phase 1 – Foundation
1. Postgres schema + Alembic migration
2. SQLAlchemy models
3. Pydantic schemas
4. Basic CRUD routers (portfolios, accounts, assets)

### Phase 2 – Data Migration
1. Base44 importer script (`importers/base44_importer.py`)
2. Map Base44 fields → new schema
3. Fix inconsistencies (metadata parsing, symbol promotion)
4. Validate all data loaded correctly

### Phase 3 – Engine
1. `model_resolver.py`
2. `cost_basis.py`
3. `current_value.py`
4. `xirr.py`
5. `performance.py`
6. `snapshot_builder.py`

### Phase 4 – API Routes
1. `GET /dashboard/{portfolio_id}` – summary with filter support
2. `GET /assets/{asset_id}/performance`
3. `POST /snapshots/rebuild`
4. `GET /valuations/{asset_id}`

### Phase 5 – Frontend (Next.js)
1. Dashboard page with filter tabs
2. Asset list with performance columns
3. Asset detail page
4. Manual valuation entry
5. Transaction entry

---

## Key Business Rules

1. **Pipeline real estate**: `current_value = invested_capital`. Never show unrealized gain until delivered.
2. **Pension funds**: Track by periodic valuation only. Do not require every monthly contribution.
3. **Whisky casks**: `current_value` from periodic third-party valuation. Storage + insurance are operating expenses that reduce net return.
4. **Acquisition costs** (purchase tax, lawyer, broker): Part of `invested_capital` / cost basis. Affects total return but NOT operating cashflow.
5. **Mortgage principal**: Balance sheet movement, NOT expense. Exclude from IRR cashflows.
6. **Mortgage interest**: IS expense. Include in IRR cashflows as outflow.
7. **XIRR timing**: Use actual dates. Never aggregate cashflows into single annual entries.

---

## Environment Variables (.env)

```
DATABASE_URL=postgresql://...
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SECRET_KEY=...
ENVIRONMENT=development
```
