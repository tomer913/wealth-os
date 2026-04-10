# Wealth OS — Project Context

## Stack
- **Frontend:** Vite + React 18 + TypeScript, deployed on Vercel (`wealth-os-xi-dun.vercel.app`)
- **Backend:** FastAPI + SQLAlchemy 2.0 + Python 3.12, deployed on Railway (`web-production-a53d1.up.railway.app`)
- **Database:** PostgreSQL on Supabase
- **GitHub:** `tomer913/wealth-os`, branch `main`, monorepo with `backend/` and `client/` folders

## Key IDs
- Portfolio UUID: `53f8f313-98e8-5de3-bd64-55826cbd82bb`
- Railway service: `web-production-a53d1.up.railway.app`
- Vercel app: `wealth-os-xi-dun.vercel.app`

## Frontend structure
```
client/src/
├── api/
│   ├── client.ts          # Single axios instance — ALL API calls go through here
│   └── portfolio.ts       # All endpoint functions (getAccounts, rebuildSnapshot…)
├── components/
│   ├── layout/            # AppShell, Sidebar, CategoryFilter
│   └── shared/            # Modal, ConfirmDialog, Form fields, MetadataEditor
├── hooks/
│   └── usePortfolio.ts    # React Query hooks
├── pages/                 # One file per page
├── store/
│   └── index.ts           # Zustand — selectedCategories, snapshot cache
├── types/
│   └── index.ts           # TypeScript types matching API response shapes
└── utils/
    └── format.ts          # formatILS, formatPct, categoryLabel, gainClass
```

## API response shapes (actual field names)
```typescript
// Snapshot: POST /api/v1/snapshots/rebuild
SnapshotSummary {
  total_value_ils, total_invested_ils, total_return_ils,
  total_return_pct,  // decimal e.g. 0.209 — multiply ×100 for display
  total_debt_ils, net_equity_ils, asset_count
}
CategorySummary { category, current_value_ils, gross_invested_ils, total_return_ils, total_return_pct, asset_count }
AssetResult { symbol, name, category, current_value_ils, total_return_pct, xirr_pct, cost_basis_ils?, total_return_ils? }

// Account: GET /api/v1/accounts/  (note trailing slash required)
Account {
  id, name, symbol, account_type, category, currency,
  institution, custodian, is_liquid, is_income_generating,
  include_in_portfolio, status, cash_balance, opening_balance,
  extra_data,  // JSONB — NOT "metadata" (naming collision with SQLAlchemy)
  notes, portfolio_id, created_at, updated_at,
  position_count  // server-computed via LEFT JOIN on assets
}
```

## Critical conventions
1. **Trailing slashes** — FastAPI redirects `/accounts` → `/accounts/`. Always use trailing slash in API calls.
2. **No `metadata` field name** — SQLAlchemy has a built-in `MetaData` class. All JSONB extra fields use `extra_data` as Python attribute, mapped to `metadata` DB column.
3. **Return percentages** — API returns decimals (0.209). Multiply ×100 before displaying.
4. **Auth-ready** — axios interceptor in `client.ts` has TODO comments. Adding Clerk: one line in the interceptor, wrap routes in `<ProtectedRoute>`.
5. **Category filter** — stored in Zustand `selectedCategories: string[]`. Empty = "All". All dashboard widgets read from filtered selectors in `store/index.ts`.
6. **CORS** — backend `main.py` has `allow_origins=["*"]` for now.
7. **`extra_data` in schemas** — always use `extra_data: Optional[Dict[str, Any]] = None` in Pydantic schemas, never `metadata`.

## Category names (from API)
`real_estate`, `pension`, `securities` (displays as "Stocks"), `alternatives`, `cash`, `crypto`, `mutual_fund`, `etf`, `energy_income`

## Deployment
- Push to `main` → Railway auto-redeploys backend, Vercel auto-redeploys frontend
- Vercel env vars: `VITE_API_URL`, `VITE_PORTFOLIO_ID`
- Railway env vars: `DATABASE_URL` (Supabase session pooler URL), `ENVIRONMENT=production`
