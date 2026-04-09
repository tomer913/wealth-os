# Wealth OS — Frontend

React dashboard for your investment portfolio. Connects to the Railway FastAPI backend.

---

## Prerequisites

You need Node.js installed. Check if you have it:
```bash
node --version   # should be v18 or higher
npm --version
```

If not installed, download from https://nodejs.org (choose "LTS" version).

---

## First-time setup

```bash
# 1. Go into the project folder
cd wealth-os

# 2. Install all dependencies (only needed once)
npm install

# 3. Create your environment file
cp .env.example .env
```

Now open `.env` in any text editor and set your Railway URL:
```
VITE_API_URL=https://zealous-charisma.railway.app   # your actual Railway URL
VITE_PORTFOLIO_ID=53f8f313-98e8-5de3-bd64-55826cbd82bb
```

---

## Running locally

```bash
npm run dev
```

Open http://localhost:3000 in your browser.

---

## Project structure

```
src/
├── api/
│   ├── client.ts          # axios instance (auth interceptors live here)
│   └── portfolio.ts       # all API call functions
├── components/
│   └── layout/
│       ├── AppShell.tsx   # sidebar + topbar + filter wrapper
│       ├── Sidebar.tsx    # dark sidebar with nav + rebuild button
│       └── CategoryFilter.tsx  # chip filter bar
├── hooks/
│   └── usePortfolio.ts    # React Query hooks (useSnapshot, useRebuildSnapshot…)
├── pages/
│   ├── DashboardPage.tsx  # main dashboard
│   └── PlaceholderPages.tsx  # stubs for Assets, Accounts, Txns
├── store/
│   └── index.ts           # Zustand — category filter + snapshot cache
├── types/
│   └── index.ts           # TypeScript types matching API response shapes
├── utils/
│   └── format.ts          # ILS formatting, dates, percentages
├── App.tsx                # router
└── main.tsx               # entry point
```

---

## Deploying to Vercel

```bash
# 1. Install Vercel CLI
npm install -g vercel

# 2. From the wealth-os folder
vercel

# Follow the prompts. When asked about environment variables, add:
# VITE_API_URL = your Railway URL
# VITE_PORTFOLIO_ID = your portfolio UUID
```

Every time you push to GitHub, Vercel auto-deploys.

---

## Adding auth later (Clerk — recommended)

When you're ready to add login:

```bash
npm install @clerk/clerk-react
```

1. Wrap `<App />` in `<ClerkProvider>` in `main.tsx`
2. In `src/api/client.ts`, uncomment the interceptor lines and use `useAuth().getToken()`
3. In `AppShell.tsx`, wrap the `<Route>` tree in `<SignedIn>` + redirect to `<SignIn>` if not authenticated

That's it — everything else stays the same because all API calls already go through the single `apiClient`.

---

## CORS — important

Your Railway FastAPI needs to allow requests from your frontend domain.
Make sure your backend has:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://your-vercel-app.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```
