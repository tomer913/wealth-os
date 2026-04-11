# CLAUDE.md — Wealth OS Development Guide

This file is read by Claude AI at the start of every development session.
It contains everything needed to continue development without re-explaining the project.

---

## Session Log

### April 11, 2026 (afternoon)
- APScheduler added — daily ETL at 07:00 Israel time (Asia/Jerusalem), runs all active connectors then auto-rebuilds snapshot
- `/api/v1/scheduler/status` and `/api/v1/scheduler/run-now` endpoints added to main.py
- IB Flex Query connector built (`ib_flex`) — fetches trades, cash transactions, open positions
  - No gateway required — pure HTTP two-step flow (SendRequest → GetStatement)
  - Incremental sync via checkpoint `last_trade_date` in connector_runs
  - Deduplication via IB TradeID → `external_reference_id = "IB-{tradeID}"`
  - Updates `extra_data["quantity"]` from OpenPositions (engine reads this for value calc)
  - XML field names: `quantity` (negative=sell), `currency`, `assetCategory`, `listingExchange`, `subCategory`
  - Query period: Last 365 Calendar Days (no fd/td override — IB doesn't support it for Activity queries)
- Fixed `CONNECTOR_ENCRYPTION_KEY` — made optional (plain JSON storage if env var not set)
- Fixed `railway.toml` — removed `[deploy.envs]` section which was wiping Railway env vars on every deploy
- Duplicate transactions found and cleaned up — IB connector duped trades already in manual imports
  - Deleted 14 import rows that had matching connector rows (same date/qty/amount)
- `formatCurrency(amount, currency)` added to `format.ts` — use for native currency amounts in transactions
- `useFilteredSummary` fixed — reads from `category.gross_invested_ils` not missing `asset.cost_basis_ils`
- Dashboard chart fixed — shows individual assets when single category selected (no more single dot)
- IB credentials (in Railway env vars): Token=279988901909582139737827, QueryID=1466664, Account=U18804332
- Connector run history shows in UI — check Connectors page after each run

### April 11, 2026 (morning)
- Build Snapshot button moved from sidebar bottom → topbar split button with date picker dropdown
- Added `GET /api/v1/snapshots/latest` — fast read from `performance_snapshots` table (no engine recompute)
- Dashboard now loads instantly (reads cached snapshot) instead of rebuilding on every page load
- `useRebuildSnapshot` hook accepts optional `asOfDate` string for historical snapshots
- Added `asset_price_history` table (migration 003) — permanent daily price record per asset
- Yahoo connector now writes to `asset_price_history` in addition to `asset.current_price`
- Engine `_get_asset_price()` reads from `asset_price_history` by date, fallback to `asset.current_price`
- Engine `_calc_market()` computes quantity from transactions when not in `extra_data`
- Snapshot builder now persists results to `performance_snapshots` table after each rebuild
- Connectors page added to Analysis nav in sidebar
- `requirements.txt` at ROOT of repo (not backend/) — Railway uses this one
- ECB FX connector: use `USD` as base (not ILS — not supported), fetch ILS/EUR/GBP as targets
- Fixed circular dependency: `constants.ts` (no deps) ← `store` ← `api/portfolio.ts`

### April 10, 2026
- Full frontend built: Dashboard, Assets, Accounts, Transactions, Valuations, Connectors pages
- Portfolio selector dropdown in topbar (switches portfolio, invalidates all queries)
- Global category chips filter all management pages (Assets, Accounts, Transactions, Valuations)
- Feature flags system in `client/src/config/features.ts`
- Server-side pagination on Assets (500/page) and Valuations (50/page)
- Client-side pagination on Transactions (50/page)
- Connector infrastructure: `connectors` + `connector_runs` tables, BaseConnector, registry
- ECB FX rates connector working
- Yahoo Finance prices connector working
- KPI card tooltips on dashboard explaining each metric
- All backend schemas use `str` not enums for legacy-data fields

---

## Project Identity

- **App:** Wealth OS — personal portfolio management system
- **Owner:** Tomer (tomerb)
- **GitHub:** tomer913/wealth-os (monorepo, branch: main)
- **Stack:** FastAPI + SQLAlchemy 2.0 + Python 3.12 (backend) / React 18 + Vite + TypeScript (frontend)

## URLs

| Service | URL |
|---------|-----|
| Frontend (Vercel) | https://wealth-os-xi-dun.vercel.app |
| Backend (Railway) | https://web-production-a53d1.up.railway.app |
| API Docs | https://web-production-a53d1.up.railway.app/docs |

## Key IDs

| Thing | Value |
|-------|-------|
| Main portfolio UUID | `53f8f313-98e8-5de3-bd64-55826cbd82bb` |
| Railway service | web-production-a53d1 (project: zealous-charisma) |

---

## Development Setup

```bash
# Backend
cd ~/projects/wealth-os/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend
cd ~/projects/wealth-os/client
npm run dev

# Run migration
cd backend && source venv/bin/activate && alembic upgrade head

# Deploy: just push to main — Railway and Vercel auto-deploy
git push origin main
```

---

## Critical Conventions (read these before writing any code)

### 1. Never name a Python field `metadata`
SQLAlchemy has a built-in `MetaData` class. Use `extra_data` instead.
The DB column is `metadata`, the Python attribute is `extra_data`.
```python
# Correct in model:
extra_data: Mapped[Optional[Dict]] = mapped_column("metadata", JSONB)

# Correct in schema:
extra_data: Optional[Dict[str, Any]] = None
```

### 2. Date column aliases
Python attributes differ from DB column names:
- `Transaction.transaction_date` → DB column `date`
- `ManualValuation.valuation_date` → DB column `date`
- `FXRate.fx_date` → DB column `date`

Schema must have: `model_config = {"from_attributes": True, "populate_by_name": True}`

### 3. Read schemas use `str` not enums
Legacy imported data has values outside enums (e.g. status='imported', domain='loan', valuation_method='derived').
Always use `str` in Read schemas for these fields.
Create/Update schemas keep enums for validation.

### 4. All API calls need trailing slash
```typescript
// Correct
apiClient.get('/api/v1/assets/')
// Wrong — causes 307 redirect
apiClient.get('/api/v1/assets')
```

### 5. Return percentages are decimals
API returns 0.209, display needs × 100 → 20.9%

### 6. Circular dependency: api ↔ store
`DEFAULT_PORTFOLIO_ID` lives in `client/src/config/constants.ts`
- `constants.ts` imports nothing
- `store/index.ts` imports from `constants.ts`
- `api/portfolio.ts` imports from `store` + `constants.ts`
- Never import `api/portfolio.ts` from `store/index.ts`

### 7. `pid()` function in api/portfolio.ts
All API calls use `pid()` to get the active portfolio ID dynamically from the Zustand store.
Never hardcode the portfolio UUID in API calls.

---

## File Locations

### Backend
```
backend/app/
├── main.py                    ← Register new routers here
├── models/                    ← One file per table
├── schemas/                   ← Pydantic schemas (separate Base/Create/Update/Read)
├── routers/                   ← FastAPI endpoints
├── engine/                    ← Calculation engine (DO NOT modify lightly)
│   ├── model_resolver.py      ← CalcModel assignment
│   ├── current_value.py       ← Value calculation per model
│   ├── cost_basis.py          ← Cost basis + return
│   ├── xirr.py                ← XIRR calculation
│   └── snapshot_builder.py    ← Orchestrator
├── connectors/                ← ETL connectors
│   ├── base.py                ← BaseConnector (inherit this)
│   ├── registry.py            ← Register new connectors here
│   └── sources/               ← Connector implementations
└── utils/
    ├── enums.py               ← All enums
    └── encryption.py          ← Fernet for connector API keys
```

### Frontend
```
client/src/
├── api/portfolio.ts           ← All API functions, uses pid()
├── components/layout/
│   ├── AppShell.tsx           ← Topbar, BuildSnapshotButton
│   ├── Sidebar.tsx            ← Nav, feature-flag filtered
│   ├── CategoryFilter.tsx     ← Global category chips
│   └── PortfolioSelector.tsx  ← Portfolio dropdown
├── components/shared/
│   ├── Modal.tsx              ← Modal, ConfirmDialog
│   ├── Form.tsx               ← Field, Input, Select, Textarea, FormGrid
│   └── MetadataEditor.tsx     ← Key-value pairs for extra_data
├── config/
│   ├── constants.ts           ← DEFAULT_PORTFOLIO_ID (no deps)
│   └── features.ts            ← Feature flags
├── hooks/usePortfolio.ts      ← React Query hooks
├── store/index.ts             ← Zustand: activePortfolioId, categories, snapshot
├── types/index.ts             ← TypeScript interfaces
└── utils/format.ts            ← formatILS, formatPct, categoryLabel, gainClass
```

---

## API Response Shapes

### Snapshot (GET /api/v1/snapshots/latest or POST /api/v1/snapshots/rebuild)
```typescript
{
  summary: {
    total_value_ils: number,
    total_invested_ils: number,
    total_return_ils: number,
    total_return_pct: number,    // decimal! 0.209 = 20.9%
    total_debt_ils: number,
    net_equity_ils: number,
    asset_count: number,
  },
  categories: [{ category, current_value_ils, gross_invested_ils, total_return_pct, asset_count }],
  assets: [{ symbol, name, category, current_value_ils, total_return_pct, xirr_pct }]
}
```

### Asset (GET /api/v1/assets/)
```typescript
{
  items: Asset[], total, page, limit, pages  // paginated
}
```

### Account (GET /api/v1/accounts/)
```typescript
Account[]  // includes position_count via LEFT JOIN
```

### Transaction (GET /api/v1/transactions/)
```typescript
Transaction[]  // transaction_date field (not 'date')
```

### ManualValuation (GET /api/v1/valuations/)
```typescript
{ items: ManualValuation[], total, page, limit, pages }  // paginated
```

---

## Pages Status

| Page | Status | Route |
|------|--------|-------|
| Dashboard | ✅ Live | / |
| Assets | ✅ Live | /assets |
| Accounts | ✅ Live | /accounts |
| Transactions | ✅ Live | /transactions |
| Valuations | ✅ Live | /valuations |
| Connectors | ✅ Live | /connectors |
| FX Rates | Placeholder | /fx-rates |
| Reports | Placeholder | /reports |

---

## Connectors Status

| Connector | Type | Status |
|-----------|------|--------|
| ECB FX Rates | ecb_fx | ✅ Working |
| Yahoo Finance Prices | yahoo_prices | ✅ Working |
| Kraken | kraken | 🔲 Not built |
| CEX.IO | cexio | 🔲 Not built |
| IB CSV import | ib_csv | 🔲 Not built |

---

## Roadmap (as of April 11, 2026)

**Next sprint — ETL:**
- [ ] APScheduler for daily ETL automation (runs connectors + snapshot at 07:00)
- [ ] Kraken connector (fetch trade history via API)
- [ ] CEX.IO connector (fetch trade history via API)
- [ ] IB CSV import connector (parse Interactive Brokers export)
- [ ] Historical portfolio value chart (query performance_snapshots by date — needs ~7 days of data first)

**Soon:**
- [ ] Demo portfolio clone (anonymized copy with scrambled amounts)
- [ ] Auth (Clerk integration — interceptor placeholder ready in api/client.ts)
- [ ] Portfolio creation from UI (currently only via DB/API)

**Later:**
- [ ] Reports page
- [ ] Budget app (separate app, shared connectors package)
- [ ] Israeli bank connectors (scraper or Salt aggregation service)
- [ ] TASE API for Israeli securities pricing (register at openapi.tase.co.il)
- [ ] AI feedback/recommendations engine

---

## Known Issues / Tech Debt

1. **ENGS quantity negative** — `-80` in transaction sum. More sells than buys imported from Base44. Data issue — needs manual fix.
2. **Some assets have 0 transactions** — AAPL, GOOGL, SOL, VOO, NVDA never imported. Need IB CSV import or manual entry.
3. **Dashboard chart shows category breakdown not time-series** — needs ~7 days of daily snapshots to build up history. Fix: query `performance_snapshots GROUP BY snapshot_date` once data exists.
4. **`total_debt_ils` hardcoded 0 in GET /latest** — real debt comes from engine. Fix: store debt in `performance_snapshots` or compute from mortgage transactions in the /latest endpoint.
5. **TASE numeric symbols** — tried as `1143783.TA` on Yahoo Finance. Some resolve, some don't. Need TASE API for reliable Israeli securities pricing.
6. **No scheduler yet** — connectors and snapshot must be triggered manually from UI. APScheduler setup is next sprint.
7. **`requirements.txt` at root** — Railway uses `/requirements.txt` not `/backend/requirements.txt`. Both exist. Keep them in sync.

---

## Deployment Checklist

If something breaks on Railway:
1. Check build logs — usually a Python import error or missing package in `requirements.txt` (root level, not backend/)
2. Check deploy logs — usually a DB connection error (use Session Pooler URL, not Direct Connection)
3. `requirements.txt` is at ROOT of repo — Railway uses this, not `backend/requirements.txt`

If something breaks on Vercel:
1. TypeScript build errors — fix locally first with `cd client && npx tsc --noEmit`
2. 404 on direct URL — check `client/vercel.json` has SPA rewrite
3. Env vars missing — check Vercel dashboard → Settings → Environment Variables
