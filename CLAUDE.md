# CLAUDE.md — Wealth OS Development Guide

This file is read by Claude AI at the start of every development session.
It contains everything needed to continue development without re-explaining the project.

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

## Roadmap (as of April 2026)

**Next sprint:**
- [ ] Historical portfolio value chart (use performance_snapshots by date)
- [ ] APScheduler for daily ETL automation
- [ ] Kraken connector (transactions)
- [ ] CEX.IO connector (transactions)

**Later:**
- [ ] Demo portfolio clone (anonymized copy of real portfolio)
- [ ] Auth (Clerk integration — interceptor placeholder ready in api/client.ts)
- [ ] Reports page
- [ ] Budget app (separate app, shared connectors package)
- [ ] Israeli bank connectors (scraper or Salt aggregation service)

---

## Known Issues / Tech Debt

1. **ENGS quantity negative** — `-80` in transaction sum, means more sells than buys imported. Data issue from Base44 importer.
2. **Some assets have 0 transactions** — AAPL, GOOGL, SOL, VOO, NVDA were never imported. Need to add manually or via IB CSV import.
3. **performance_snapshots debt column** — `total_debt_ils` is hardcoded as 0 in GET /latest endpoint. Real debt comes from engine which reads REAL_ESTATE mortgage transactions. Fix: include debt from actual performance_snapshot rows.
4. **Dashboard chart** — still shows category breakdown, not time-series. Fix: query performance_snapshots GROUP BY snapshot_date after enough historical data builds up.
5. **TASE prices** — TASE numeric symbols (e.g. 1143783) tried as `1143783.TA` on Yahoo. Some may not resolve. Need TASE API credentials from openapi.tase.co.il.

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
