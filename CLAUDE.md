# Wealth OS — Project Context for Claude Code

## What this project is
Personal portfolio management system replacing a Base44 app. Tracks investments, computes performance snapshots, and will serve a client-side dashboard.

GitHub: `tomer913/wealth-os`
Deployed on: Railway (project: zealous-charisma)

---

## Stack

| Layer | Tech |
|---|---|
| Runtime | Python 3.12.9 |
| API framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Database | PostgreSQL on Supabase |
| Deployment | Railway |

---

## Database

- **Supabase project ID:** `sqgcoqqqyyahthvedmnr`
- **Connection:** IPv4-compatible pooler on port `6543` (not 5432)
- **Migration:** single Alembic migration `001_initial_schema`

### Tables
- `portfolios`
- `accounts`
- `assets`
- `transactions`
- `manual_valuations`
- `fx_rates`
- `performance_snapshots`
- `positions`
- `raw_transactions` — immutable connector log (UUID v7 PK, dedup by source+external_ref_id)
- `service_checkpoints` — processor cursor per (service_name, portfolio_id)
- `processor_runs` — audit log for processor executions

### Critical naming quirks
- `metadata` column is mapped as `extra_data` — avoids SQLAlchemy namespace conflict
- Date columns are renamed to avoid Python builtin conflicts: `transaction_date`, `valuation_date`, `fx_date`

---

## Portfolio

- **Name:** Tomer Portfolio Clean
- **Base44 ID:** `69c48b47734576357923ff08`
- **UUID:** `53f8f313-98e8-5de3-bd64-55826cbd82bb`

---

## Engine modules (all completed)

| Module | Purpose |
|---|---|
| `model_resolver` | Resolves asset models |
| `current_value` | Computes current portfolio value |
| `cost_basis` | Computes cost basis per position |
| `xirr` | Calculates internal rate of return |
| `snapshot_builder` | Builds full portfolio snapshots |

Key endpoint: `POST /api/v1/snapshots/rebuild` — returns full portfolio snapshot.

Positions and `performance_snapshots` are **computed**, not imported.

---

## Data import

- Importer at `app/importers/base44_importer.py`
- Uses deterministic UUID5 conversion for safe re-runs
- Data import is complete

---

## Current phase

Backend is fully deployed and operational. Frontend dashboard is built.
Now adding **raw data layer** (April 2026):
- `raw_transactions` — immutable append-only log written by bank connectors
- `service_checkpoints` — processor consumer offsets
- `processor_runs` — audit log for processor executions
- `BankProcessor` — classifies raw bank rows into domain transactions
- Scheduler chain: 07:00 connectors → 07:05 BankProcessor → 07:10 snapshots

---

## Conventions

- Use virtual environments consistently
- Prefer clean file rewrites over incremental patches
- Work directly in terminal on Mac
- API routes live under `/api/v1/`

---

## Infrastructure to be aware of

- Railway handles deployment — check `railway.toml` or `Procfile` for start commands
- Supabase is DB only (no auth, no edge functions used)
- Environment variables for DB connection are set in Railway dashboard
- Do not commit secrets or `.env` files
