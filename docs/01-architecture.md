# Wealth OS — Architecture

## Overview

Wealth OS is a personal portfolio management system that tracks investments across multiple asset classes (real estate, stocks, crypto, pension, alternatives), computes performance metrics, and fetches live market data via connectors.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                          │
│   React 18 + Vite + TypeScript + React Query + Zustand          │
│   Deployed: Vercel (wealth-os-xi-dun.vercel.app)                │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS REST API
┌────────────────────────────▼────────────────────────────────────┐
│                      BACKEND (FastAPI)                           │
│   Python 3.12 + SQLAlchemy 2.0 + Alembic                        │
│   Deployed: Railway (web-production-a53d1.up.railway.app)        │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │   Routers   │  │    Engine    │  │      Connectors        │ │
│  │  /assets    │  │ model_resolver│  │  ecb_fx (FX rates)    │ │
│  │  /accounts  │  │ current_value│  │  yahoo_prices (stocks) │ │
│  │  /txns      │  │ cost_basis   │  │  kraken (future)       │ │
│  │  /snapshots │  │ xirr         │  │  cexio (future)        │ │
│  │  /connectors│  │ snapshot_bld │  │  BaseConnector         │ │
│  └─────────────┘  └──────────────┘  └────────────────────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │ SQLAlchemy async
┌────────────────────────────▼────────────────────────────────────┐
│                    DATABASE (PostgreSQL)                          │
│   Supabase — Session Pooler URL (IPv4, port 5432)               │
│   Project UUID: 53f8f313-98e8-5de3-bd64-55826cbd82bb            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18 | UI framework |
| Vite | latest | Build tool |
| TypeScript | 5.x | Type safety |
| React Query | 5.x | Server state, caching |
| Zustand | 4.x | Client state (portfolio selector, category filter, snapshot cache) |
| Tailwind CSS | 3.x | Styling |
| Recharts | 2.x | Charts (donut, area) |
| Axios | 1.x | HTTP client with interceptors |
| React Router | 6.x | Client-side routing |

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12.9 | Runtime |
| FastAPI | 0.100+ | API framework |
| SQLAlchemy | 2.0 | ORM (async) |
| Alembic | latest | DB migrations |
| Pydantic | 2.x | Validation schemas |
| APScheduler | (planned) | ETL scheduling |
| httpx | 0.27 | Async HTTP for connectors |
| yfinance | 0.2.40+ | Yahoo Finance prices |
| cryptography | latest | Connector API key encryption |

### Infrastructure
| Service | Purpose |
|---------|---------|
| Railway | Backend hosting (auto-deploy from GitHub main) |
| Vercel | Frontend hosting (auto-deploy from GitHub main) |
| Supabase | PostgreSQL database |
| GitHub | Source control (tomer913/wealth-os) |

---

## Repository Structure

```
wealth-os/                          ← monorepo root
├── backend/                        ← FastAPI backend
│   ├── app/
│   │   ├── main.py                 ← FastAPI app, router registration
│   │   ├── database.py             ← SQLAlchemy async engine + SessionLocal
│   │   ├── models/                 ← SQLAlchemy ORM models
│   │   ├── schemas/                ← Pydantic request/response schemas
│   │   ├── routers/                ← FastAPI route handlers
│   │   ├── engine/                 ← Calculation engine
│   │   │   ├── model_resolver.py   ← Determines CalcModel per asset
│   │   │   ├── current_value.py    ← Computes current value per model
│   │   │   ├── cost_basis.py       ← Cost basis + return calculations
│   │   │   ├── xirr.py             ← XIRR calculation
│   │   │   └── snapshot_builder.py ← Orchestrates full portfolio snapshot
│   │   ├── connectors/             ← ETL connector package
│   │   │   ├── base.py             ← BaseConnector abstract class
│   │   │   ├── registry.py         ← Connector type registry
│   │   │   └── sources/            ← Connector implementations
│   │   └── utils/
│   │       ├── enums.py            ← All enum definitions
│   │       └── encryption.py       ← Fernet encryption for API keys
│   ├── alembic/                    ← DB migrations
│   └── requirements.txt
├── client/                         ← React frontend
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts           ← Axios instance with interceptors
│   │   │   └── portfolio.ts        ← All API functions
│   │   ├── components/
│   │   │   ├── layout/             ← AppShell, Sidebar, CategoryFilter,
│   │   │   │                         PortfolioSelector, BuildSnapshotButton
│   │   │   └── shared/             ← Modal, Form, MetadataEditor
│   │   ├── config/
│   │   │   ├── constants.ts        ← DEFAULT_PORTFOLIO_ID (neutral, no circular deps)
│   │   │   └── features.ts         ← Feature flags
│   │   ├── hooks/
│   │   │   └── usePortfolio.ts     ← React Query hooks
│   │   ├── pages/                  ← One file per page
│   │   ├── store/
│   │   │   └── index.ts            ← Zustand store
│   │   ├── types/
│   │   │   └── index.ts            ← TypeScript interfaces
│   │   └── utils/
│   │       └── format.ts           ← formatILS, formatPct, categoryLabel
│   ├── vercel.json                 ← SPA rewrite rules
│   └── vite-env.d.ts               ← ImportMeta env type declarations
├── docs/                           ← This documentation
├── CLAUDE.md                       ← Claude AI development guide
└── railway.toml                    ← Railway deployment config
```

---

## Data Flow

### Dashboard load (fast path)
```
Browser → GET /api/v1/snapshots/latest?portfolio_id=...
        ← Reads performance_snapshots table (instant)
        ← Returns cached snapshot JSON
Browser renders dashboard immediately
```

### Build Snapshot (recompute)
```
User clicks "Build Snapshot" (or scheduled daily)
  → POST /api/v1/snapshots/rebuild
  → Engine runs (2-3 seconds):
      For each active asset:
        1. resolve_model(asset) → CalcModel
        2. calc_current_value() → value in ILS
        3. calc_cost_basis()    → invested capital
        4. calc_xirr()          → annualized return
      Aggregate by category → portfolio totals
  → Persist to performance_snapshots (one row per asset per date)
  → Return snapshot JSON
  ← Frontend updates Zustand store + React Query cache
```

### ETL connector run
```
Manual trigger (UI) or scheduled (APScheduler)
  → ConnectorRun record created (status: pending)
  → Background task executes connector:
      ECB FX: fetch rates → write to fx_rates table
      Yahoo:  fetch prices → write to asset.current_price
                           → write to asset_price_history
  → ConnectorRun updated (status: success/failed + counts)
  → User can then click "Build Snapshot" to use fresh data
```

---

## Feature Flags

Located at `client/src/config/features.ts`. Simple boolean config — flip to enable/disable pages and features without deploying.

```typescript
export const FEATURES = {
  dashboard: true,
  assets_page: true,
  accounts_page: true,
  transactions_page: true,
  valuations_page: true,
  connectors_page: true,
  fx_rates_page: false,    // ← flip to true to show in nav
  reports_page: false,
  // ...
}
```

**SaaS roadmap:** Move to backend per-portfolio/plan config. Frontend code doesn't change — just the source of truth.

---

## Deployment

### Backend (Railway)
- Auto-deploys on push to `main`
- Start command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Required env vars:
  - `DATABASE_URL` — Supabase Session Pooler URL (IPv4, NOT direct connection)
  - `ENVIRONMENT=production`
  - `CONNECTOR_ENCRYPTION_KEY` — Fernet key for connector API key encryption

### Frontend (Vercel)
- Auto-deploys on push to `main`
- Root directory: `client`
- Required env vars:
  - `VITE_API_URL=https://web-production-a53d1.up.railway.app`
  - `VITE_PORTFOLIO_ID=53f8f313-98e8-5de3-bd64-55826cbd82bb`
- `vercel.json` contains SPA rewrite: all routes → `index.html`

### Database migrations
```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

---

## Security Notes

- Connector API keys (Kraken, CEX.IO etc.) are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256)
- Encryption key stored in Railway env var `CONNECTOR_ENCRYPTION_KEY`
- CORS currently `allow_origins=["*"]` — tighten when adding auth
- Auth planned via Clerk — interceptor placeholder exists in `client/src/api/client.ts`
