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

## Authentication (Clerk)

Multi-tenant SaaS auth added April 2026.

| Item | Detail |
|---|---|
| Provider | Clerk |
| Frontend pkg | `@clerk/clerk-react` |
| Token verification | RS256 JWT via JWKS endpoint |
| Dev bypass | Set `auth_enabled: false` in `features.ts` **or** leave `VITE_CLERK_PUBLISHABLE_KEY` unset |

### Environment variables

**Vercel (frontend):**
- `VITE_CLERK_PUBLISHABLE_KEY` — from Clerk dashboard

**Railway (backend):**
- `CLERK_SECRET_KEY` — from Clerk dashboard
- `CLERK_JWKS_URL` — `https://[your-clerk-domain]/.well-known/jwks.json`

When `CLERK_JWKS_URL` is not set, backend auth is bypassed (dev mode).

### Data migration for existing portfolio
After first Clerk sign-in, get your `user_id` from the Clerk dashboard and run:
```sql
UPDATE portfolios SET owner_id = 'user_YOUR_CLERK_ID'
WHERE id = '53f8f313-98e8-5de3-bd64-55826cbd82bb';
```

### Key files
- `backend/app/auth.py` — `get_current_user` dep + `verify_portfolio_access` helper
- `backend/alembic/versions/010_auth_portfolio_members.py` — `last_accessed_at`, `portfolio_members` table
- `client/src/components/auth/ProtectedRoute.tsx` — wraps all app routes
- `client/src/pages/SignInPage.tsx` — Clerk UI + Face ID/Passkey button
- `client/src/pages/SetupPage.tsx` — new-user onboarding (creates first portfolio)

### Clerk MAU
Free tier = 10,000 MAU (unique users/month). Current usage: ~2 MAU (Tomer + wife).

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

### Scraper credentials architecture
- Card credentials (username/password/card6) are stored **encrypted in the DB** via the Connectors UI
- `GET /api/v1/connectors/{id}/credentials/` — returns decrypted credentials to the scraper; auth: `X-Scraper-Token`
- GitHub Actions workflow receives only `CONNECTOR_ID`; no card secrets stored in GitHub
- `scraper/index.js` fetches from API when `CONNECTOR_ID` is set; falls back to env vars for local testing

### Connector Registry
See `backend/app/connectors/CONNECTORS.md` for full connector type documentation.
All connector types, their properties, asset-linking strategies, and file upload support
are defined in `backend/app/connectors/connector_registry.py` (`CONNECTOR_REGISTRY` dict)
and documented in `CONNECTORS.md`. When adding a new connector type, update **both** files.

Key properties per type:
- `category`: `automatic` | `manual_upload` | `scraper`
- `requires_asset_selection_on_upload`: if true, frontend shows asset dropdown at upload time
- `supported_file_types`: list of accepted extensions for manual_upload types

### Notification System

Channel-agnostic daily report — send to Telegram, email, Slack, or any future channel with zero changes to report logic.

**Architecture:**
```
build_daily_report() → ReportData
notification_router.deliver_report(ReportData)
  → TelegramChannel (if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set)
  → EmailChannel    (if RESEND_API_KEY set)      [stub — not yet implemented]
  → SlackChannel    (if SLACK_WEBHOOK_URL set)   [stub — not yet implemented]
```

**File locations:**
- `backend/app/utils/daily_report.py` — builds ReportData from DB (no formatting)
- `backend/app/utils/notifications/base.py` — dataclasses + NotificationChannel ABC
- `backend/app/utils/notifications/telegram.py` — Telegram implementation
- `backend/app/utils/notifications/email.py` — Email stub (Resend)
- `backend/app/utils/notifications/slack.py` — Slack stub
- `backend/app/utils/notification_router.py` — delivers to all configured channels

**To add a new channel:** create `notifications/yourchannel.py`, implement 3 methods, add to `CHANNELS` list in `notification_router.py`. Zero other changes needed.

**Scheduler:** runs at **07:15 IL** after the 07:10 snapshot rebuild.

**Environment variables (set in Railway):**
```
TELEGRAM_BOT_TOKEN = <from @BotFather>
TELEGRAM_CHAT_ID   = <your personal chat ID — send /start to @userinfobot>
# Future channels (uncomment when implementing):
# RESEND_API_KEY    = for email reports via Resend
# REPORT_EMAIL_TO   = recipient address
# REPORT_EMAIL_FROM = verified sender address
# SLACK_WEBHOOK_URL = Incoming Webhook URL from api.slack.com/apps
```

### FIBI bank import
- **Primary:** XLS export from FIBI online banking — parsed by `parse_fibi_xlsx()` in `backend/app/connectors/parsers/fibi.py`
- Sheet: `"Activities"`, rows 7+ are transactions; columns 3/4 = credit/debit, col 5 = description, col 7 = op code, col 8 = date
- Op codes mapped via `FIBI_OP_CODE_MAP`; fund codes in description matched via `FIBI_ASSET_MAP`
- Paired interest dedup: op=245 (credit mirror) dropped when matched by op=295 (real outflow) on same date + amount
- **Fallback:** PDF parser (`parse_fibi_pdf`) kept for old files
- Upload handler (`POST /api/v1/connectors/upload/`) accepts `.xls`, `.xlsx`, and `.pdf`; XLS/XLSX written to temp file, then parsed
- `xlrd>=2.0.1` required in both `backend/requirements.txt` and root `requirements.txt` (Railway uses the root one)
