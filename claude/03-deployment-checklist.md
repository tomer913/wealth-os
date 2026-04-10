# Skill: FastAPI + Vite Deployment Checklist

Use this when deploying a new FastAPI + React/Vite app to Railway + Vercel.

## Railway (FastAPI backend)

### Required files
```python
# main.py — CORS must allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later with auth
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoint (Railway uses this for readiness checks)
@app.get("/health")
async def health():
    return {"status": "ok"}
```

### Required env vars in Railway
- `DATABASE_URL` — use Supabase **Session Pooler** URL (port 5432), NOT Direct Connection (IPv6 incompatible with Railway)
- `ENVIRONMENT` — `production`
- Any secrets (`SECRET_KEY`, `SUPABASE_URL`, etc.)

### Supabase connection URL format
```
postgresql://postgres.{ref}:{password}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
```
NOT: `postgresql://postgres:{password}@db.{ref}.supabase.co:5432/postgres` (IPv6 only)

---

## Vercel (Vite/React frontend)

### Required files
```json
// client/vercel.json — WITHOUT this, direct URLs return 404
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

```typescript
// client/src/vite-env.d.ts — WITHOUT this, TypeScript build fails
/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_PORTFOLIO_ID: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

### Vercel project settings
- **Root Directory:** `client` (not repo root)
- **Framework:** Vite (auto-detected)
- **Env vars:** `VITE_API_URL`, `VITE_PORTFOLIO_ID`

### Required env vars in Vercel
All `VITE_*` vars must be set in Vercel dashboard — `.env` file is gitignored and not deployed.

---

## Axios client setup (auth-ready)
```typescript
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: 30_000,
  maxRedirects: 5,  // follows FastAPI trailing slash redirects
})

// Auth interceptor — add token here when ready
apiClient.interceptors.request.use((config) => {
  // TODO: const token = getToken(); config.headers.Authorization = `Bearer ${token}`
  return config
})
```

---

## Common deployment failures and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| Vercel 404 on `/accounts` etc. | Missing `vercel.json` SPA rewrite | Add `vercel.json` with rewrites |
| TypeScript build error `Property 'env' does not exist on type 'ImportMeta'` | Missing `vite-env.d.ts` | Add the type declaration file |
| Backend 500 on list endpoint | Pydantic field named `metadata` collides with SQLAlchemy | Rename to `extra_data` |
| Frontend gets 307 redirect | FastAPI redirects `/accounts` → `/accounts/` | Add trailing slash to all API calls |
| CORS blocked after redirect | 307 redirect goes to `http://` not `https://` | Use trailing slashes to avoid redirect |
| DB connection fails on Railway | Using Direct Connection URL (IPv6) | Use Session Pooler URL (IPv4) |
| `422 Unprocessable Content` | Leading space in UUID from env var | Add `.trim()` to env var reads |
