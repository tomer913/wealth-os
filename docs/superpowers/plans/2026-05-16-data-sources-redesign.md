# Data Sources Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Connectors page into a "Data sources" page with grouped sections, a multi-step wizard for adding/editing sources, an upload modal, and stats bar — driven entirely by `ConnectorTypeDef` metadata with no hardcoded per-type logic.

**Architecture:** Backend adds `flow_type`, `supports_auto_scrape`, `supports_manual_upload` to `ConnectorTypeDef`; frontend reads these at runtime to drive sections (Investment / Budget / Price & FX), wizard flow (investment vs budget), and card actions (Run vs Upload). The existing `ConnectorsPage.tsx` is rewritten in-place preserving all API calls, run history drawer, delete confirm, and scraper logic. Wizard replaces the old flat form modal. Upload modal replaces `UploadSection`. Stats bar is new.

**Tech Stack:** Python/FastAPI (dataclass update), React 18, TypeScript, TailwindCSS, react-i18next, @tanstack/react-query

---

## File Map

| File | Action | What changes |
|---|---|---|
| `backend/app/connectors/connector_registry.py` | MODIFY | Add 3 new fields to `ConnectorTypeDef`; update all 11 registry entries |
| `backend/app/main.py` | NO CHANGE | Already reads from CONNECTOR_REGISTRY; auto-updated |
| `client/src/i18n/locales/en/common.json` | MODIFY | Add `dataSources` block; update `nav.connectors` key |
| `client/src/i18n/locales/he/common.json` | MODIFY | Add `dataSources` block in Hebrew; update `nav.connectors` key |
| `client/src/types/index.ts` | MODIFY | Add `flow_type`, `supports_auto_scrape`, `supports_manual_upload` to `ConnectorType` interface |
| `client/src/pages/ConnectorsPage.tsx` | REWRITE | Full redesign: sections, wizard, upload modal, stats bar; preserve all API logic |

---

## Task 1: Backend — Add new fields to ConnectorTypeDef

**Files:**
- Modify: `backend/app/connectors/connector_registry.py`

- [ ] **Step 1: Add 3 new fields to the dataclass**

Replace the `ConnectorTypeDef` dataclass in `backend/app/connectors/connector_registry.py`:

```python
@dataclass
class ConnectorTypeDef:
    type: str
    display_name: str
    description: str
    category: str                             # 'automatic' | 'manual_upload' | 'scraper'
    flow_type: str                            # 'investment' | 'budget' | 'both'
    supports_multi_asset: bool
    requires_asset_selection_on_upload: bool
    supported_file_types: list
    asset_linking: str
    supports_auto_scrape: bool   # has credential-based auto sync (scheduler can run it)
    supports_manual_upload: bool # supports file upload via upload endpoint
    schedule_default: str = "daily"
```

- [ ] **Step 2: Update all 11 registry entries**

Replace the entire `CONNECTOR_REGISTRY` dict in `backend/app/connectors/connector_registry.py`:

```python
CONNECTOR_REGISTRY: dict = {
    "ib_flex": ConnectorTypeDef(
        type="ib_flex",
        display_name="Interactive Brokers",
        description="Fetches trades and positions via IB Flex Query API. No gateway required.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="auto_by_description",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "kraken": ConnectorTypeDef(
        type="kraken",
        display_name="Kraken Exchange",
        description="Fetches crypto trades via Kraken REST API.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="auto_by_description",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "cexio": ConnectorTypeDef(
        type="cexio",
        display_name="CEX.IO Exchange",
        description="Fetches crypto trades via CEX.IO API.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="auto_by_description",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "ecb_fx": ConnectorTypeDef(
        type="ecb_fx",
        display_name="ECB FX Rates",
        description="Fetches daily FX rates from European Central Bank.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="none",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "yahoo_prices": ConnectorTypeDef(
        type="yahoo_prices",
        display_name="Yahoo Finance Prices",
        description="Fetches daily asset prices from Yahoo Finance.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="none",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "isracard": ConnectorTypeDef(
        type="isracard",
        display_name="Isracard",
        description="Scrapes Isracard credit card transactions via GitHub Actions. ⚠️ Broken — SMS 2FA added. Use isracard_xlsx.",
        category="scraper",
        flow_type="budget",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="account_linked",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "cal_scraper": ConnectorTypeDef(
        type="cal_scraper",
        display_name="CAL Card",
        description="Scrapes CAL credit card transactions via GitHub Actions.",
        category="scraper",
        flow_type="budget",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="account_linked",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "fibi_bank": ConnectorTypeDef(
        type="fibi_bank",
        display_name="הבינלאומי FIBI",
        description="העלה קובץ XLS או PDF מהבנק הבינלאומי.",
        category="manual_upload",
        flow_type="both",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=["pdf", "xls", "xlsx"],
        asset_linking="auto_by_description",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
    "mizrachi_bank": ConnectorTypeDef(
        type="mizrachi_bank",
        display_name="מזרחי טפחות",
        description="העלה קובץ PDF ממזרחי טפחות.",
        category="manual_upload",
        flow_type="both",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=["pdf"],
        asset_linking="auto_by_description",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
    "btb_pdf": ConnectorTypeDef(
        type="btb_pdf",
        display_name="BTB - Be The Bank",
        description="Upload monthly PDF portfolio reports from Be The Bank (btbisrael.co.il). No credentials required.",
        category="manual_upload",
        flow_type="investment",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=True,
        supported_file_types=["pdf"],
        asset_linking="user_selected",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
    "isracard_xlsx": ConnectorTypeDef(
        type="isracard_xlsx",
        display_name="ישראכרט - העלאת קובץ",
        description="העלה קובץ Excel חודשי מאתר ישראכרט. מחליף את הסקרייפר האוטומטי שנשבר.",
        category="manual_upload",
        flow_type="budget",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=False,
        supported_file_types=["xlsx", "xls"],
        asset_linking="none",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
}
```

- [ ] **Step 3: Verify syntax**

```bash
cd backend && python3 -c "from app.connectors.connector_registry import CONNECTOR_REGISTRY; print(len(CONNECTOR_REGISTRY), 'entries')"
```
Expected: `11 entries`

- [ ] **Step 4: Commit**

```bash
git add backend/app/connectors/connector_registry.py
git commit -m "feat: add flow_type + supports_auto_scrape + supports_manual_upload to ConnectorTypeDef"
```

---

## Task 2: i18n — Add dataSources strings and update nav

**Files:**
- Modify: `client/src/i18n/locales/en/common.json`
- Modify: `client/src/i18n/locales/he/common.json`

- [ ] **Step 1: Update nav key in en/common.json**

In `client/src/i18n/locales/en/common.json`, change the `nav.connectors` entry:

```json
"connectors": "Data sources"
```

- [ ] **Step 2: Add dataSources block to en/common.json**

Add this as a top-level key in `client/src/i18n/locales/en/common.json` (alongside existing keys):

```json
"dataSources": {
  "title": "Data sources",
  "activeSources": "Active sources",
  "lastSync": "Last sync",
  "addSource": "Add source",
  "sendReport": "Send report",
  "sections": {
    "investment": "Investment sources",
    "budget": "Budget sources",
    "feeds": "Price & FX feeds"
  },
  "badges": {
    "autoSync": "auto sync",
    "manualUpload": "manual upload",
    "active": "active",
    "uploaded": "uploaded",
    "failed": "failed",
    "invalidCredentials": "invalid credentials",
    "notConfigured": "not configured",
    "uploadPending": "upload pending"
  },
  "actions": {
    "run": "Run",
    "edit": "Edit",
    "delete": "Delete",
    "uploadStatement": "Upload statement"
  },
  "wizard": {
    "investment": {
      "title": "Add investment source",
      "step1": "Choose provider",
      "step2": "Link asset",
      "step2MultiAsset": "This source manages multiple assets automatically.",
      "step3": "Connect",
      "credentialsEncrypted": "Credentials stored encrypted"
    },
    "budget": {
      "title": "Add budget source",
      "step1": "Choose provider",
      "step2": "Connection method",
      "step2Auto": "Auto sync (recommended)",
      "step2AutoDesc": "Enter credentials — synced daily automatically",
      "step2Manual": "Manual upload",
      "step2ManualDesc": "Upload statement files yourself each period. No credentials needed.",
      "step3": "Name it & save",
      "manualNote": "No credentials needed. Upload statement files from the data sources page after saving.",
      "autoNote": "Credentials stored encrypted. Syncs daily at 07:00."
    },
    "edit": {
      "title": "Edit data source",
      "typeLockedWarning": "Connector type cannot be changed. Create a new data source if you need a different provider.",
      "credentialsPlaceholder": "Leave blank to keep existing credentials"
    },
    "common": {
      "name": "Name",
      "namePlaceholder": "e.g. ישראכרט 5177",
      "back": "Back",
      "next": "Next",
      "save": "Save",
      "cancel": "Cancel"
    }
  },
  "upload": {
    "title": "Upload statement",
    "accepts": "Accepts",
    "periodFrom": "From",
    "periodTo": "To",
    "periodOptional": "Period covered by this file (optional — auto-detected if possible)",
    "chooseFile": "Choose file",
    "dragDrop": "Drag & drop or browse",
    "asset": "Asset",
    "uploading": "Uploading...",
    "success": {
      "transactions": "transactions imported",
      "autoClassified": "Auto-classified",
      "needsReview": "Needs review",
      "viewRules": "View in Budget Rules"
    }
  },
  "lastSyncTime": "Last sync: {{time}}",
  "lastUploadTime": "Last upload: {{time}}",
  "neverSynced": "Never synced",
  "neverUploaded": "Never uploaded"
}
```

- [ ] **Step 3: Update nav key in he/common.json**

In `client/src/i18n/locales/he/common.json`, change `nav.connectors`:

```json
"connectors": "מקורות נתונים"
```

- [ ] **Step 4: Add dataSources block to he/common.json**

Add this as a top-level key in `client/src/i18n/locales/he/common.json`:

```json
"dataSources": {
  "title": "מקורות נתונים",
  "activeSources": "מקורות פעילים",
  "lastSync": "סנכרון אחרון",
  "addSource": "הוסף מקור",
  "sendReport": "שלח דוח",
  "sections": {
    "investment": "מקורות השקעה",
    "budget": "מקורות תקציב",
    "feeds": "עדכוני מחירים ומט\"ח"
  },
  "badges": {
    "autoSync": "סנכרון אוטומטי",
    "manualUpload": "העלאה ידנית",
    "active": "פעיל",
    "uploaded": "הועלה",
    "failed": "נכשל",
    "invalidCredentials": "פרטי גישה שגויים",
    "notConfigured": "לא מוגדר",
    "uploadPending": "ממתין להעלאה"
  },
  "actions": {
    "run": "הפעל",
    "edit": "ערוך",
    "delete": "מחק",
    "uploadStatement": "העלה דף חשבון"
  },
  "wizard": {
    "investment": {
      "title": "הוסף מקור השקעה",
      "step1": "בחר ספק",
      "step2": "קשר נכס",
      "step2MultiAsset": "מקור זה מנהל מספר נכסים באופן אוטומטי.",
      "step3": "התחבר",
      "credentialsEncrypted": "פרטי הגישה מאוחסנים מוצפנים"
    },
    "budget": {
      "title": "הוסף מקור תקציב",
      "step1": "בחר ספק",
      "step2": "שיטת חיבור",
      "step2Auto": "סנכרון אוטומטי (מומלץ)",
      "step2AutoDesc": "הזן פרטי גישה — מסתנכרן יומית באופן אוטומטי",
      "step2Manual": "העלאה ידנית",
      "step2ManualDesc": "העלה קבצי דפי חשבון בעצמך בכל תקופה. אין צורך בפרטי גישה.",
      "step3": "תן שם ושמור",
      "manualNote": "אין צורך בפרטי גישה. העלה קבצים מדף מקורות הנתונים לאחר השמירה.",
      "autoNote": "פרטי הגישה מאוחסנים מוצפנים. מסתנכרן יומית ב-07:00."
    },
    "edit": {
      "title": "ערוך מקור נתונים",
      "typeLockedWarning": "לא ניתן לשנות את סוג המחבר. צור מקור נתונים חדש אם אתה צריך ספק אחר.",
      "credentialsPlaceholder": "השאר ריק כדי לשמור על פרטי הגישה הקיימים"
    },
    "common": {
      "name": "שם",
      "namePlaceholder": "לדוגמה: ישראכרט 5177",
      "back": "חזור",
      "next": "הבא",
      "save": "שמור",
      "cancel": "ביטול"
    }
  },
  "upload": {
    "title": "העלה דף חשבון",
    "accepts": "מקבל",
    "periodFrom": "מתאריך",
    "periodTo": "עד תאריך",
    "periodOptional": "התקופה המכוסה בקובץ (אופציונלי — יזוהה אוטומטית אם אפשרי)",
    "chooseFile": "בחר קובץ",
    "dragDrop": "גרור ושחרר או עיין",
    "asset": "נכס",
    "uploading": "מעלה...",
    "success": {
      "transactions": "עסקאות יובאו",
      "autoClassified": "סווגו אוטומטית",
      "needsReview": "ממתינות לבדיקה",
      "viewRules": "צפה בכללי תקציב"
    }
  },
  "lastSyncTime": "סנכרון אחרון: {{time}}",
  "lastUploadTime": "העלאה אחרונה: {{time}}",
  "neverSynced": "מעולם לא סונכרן",
  "neverUploaded": "מעולם לא הועלה"
}
```

- [ ] **Step 5: Commit**

```bash
git add client/src/i18n/locales/en/common.json client/src/i18n/locales/he/common.json
git commit -m "feat: add dataSources i18n strings + rename nav to Data sources"
```

---

## Task 3: TypeScript types

**Files:**
- Modify: `client/src/types/index.ts`

- [ ] **Step 1: Add new fields to ConnectorType interface in ConnectorsPage.tsx**

The `ConnectorType` interface is currently defined locally in `ConnectorsPage.tsx`. Add the three new fields. Find the existing `interface ConnectorType` in `ConnectorsPage.tsx` (around line 66) and update it:

```typescript
interface ConnectorType {
  type: string
  display_name: string
  description: string
  category: 'automatic' | 'manual_upload' | 'scraper'
  flow_type: 'investment' | 'budget' | 'both'
  supports_multi_asset: boolean
  requires_asset_selection_on_upload: boolean
  supported_file_types: string[]
  asset_linking: string
  supports_auto_scrape: boolean
  supports_manual_upload: boolean
  schedule_default: string
  config_fields: { key: string; label: string; type: string; default: string; hint: string }[]
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd client && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors (or only pre-existing errors, none from our change)

- [ ] **Step 3: Commit**

```bash
git add client/src/pages/ConnectorsPage.tsx
git commit -m "feat: add flow_type + supports_auto/manual fields to ConnectorType interface"
```

---

## Task 4: Frontend — Main page layout, stats bar, section structure

**Files:**
- Modify: `client/src/pages/ConnectorsPage.tsx`

This task rewrites the top-level `ConnectorsPage` component and section layout. Preserve all existing API functions (`getConnectors`, `createConnector`, `updateConnector`, `deleteConnector`, `triggerRun`, `getConnectorRuns`, `pushSecrets`) and utility functions (`isScraperType`, `getCompany`, `buildSecretsPayload`, `formatRelative`, `formatDuration`, `formatElapsed`). Preserve `RunHistoryDrawer`, `LoadingCards` sub-components.

- [ ] **Step 1: Add section-grouping helpers after the existing utility functions**

After `formatRelative` (~line 191) add these constants and helper:

```typescript
// ─── Section grouping ──────────────────────────────────────────────────────────

const FEED_TYPES = new Set(['ecb_fx', 'yahoo_prices'])

function getSectionKey(type: string, typeDef: ConnectorType | undefined): 'investment' | 'budget' | 'feeds' {
  if (FEED_TYPES.has(type)) return 'feeds'
  const ft = typeDef?.flow_type
  if (ft === 'budget' || ft === 'both') return 'budget'
  return 'investment'
}

function getStatusBadge(c: ConnectorRead, typeDef: ConnectorType | undefined): {
  label: string
  color: 'green' | 'red' | 'yellow' | 'orange' | 'gray'
} {
  if (!c.is_active) return { label: 'notConfigured', color: 'gray' }
  const s = c.last_run_status
  if (!s && !c.last_run_at) {
    return typeDef?.supports_manual_upload
      ? { label: 'uploadPending', color: 'orange' }
      : { label: 'notConfigured', color: 'gray' }
  }
  if (s === 'success') return {
    label: typeDef?.supports_manual_upload ? 'uploaded' : 'active',
    color: 'green',
  }
  if (s === 'failed') return { label: 'failed', color: 'red' }
  if (s === 'skipped') return { label: 'invalidCredentials', color: 'yellow' }
  return { label: 'notConfigured', color: 'gray' }
}

const BADGE_COLORS = {
  green:  'bg-emerald-50 text-emerald-700',
  red:    'bg-rose-50 text-rose-700',
  yellow: 'bg-amber-50 text-amber-700',
  orange: 'bg-orange-50 text-orange-700',
  gray:   'bg-gray-100 text-gray-500',
}
```

- [ ] **Step 2: Rewrite the main ConnectorsPage component body**

Replace the entire `export default function ConnectorsPage()` body (keep existing API query setup) with the new layout. The component state and queries at the top stay — only the JSX changes.

Add these state variables to the existing component state block (after `runningIds`):

```typescript
const [wizardOpen, setWizardOpen] = useState(false)
const [wizardMode, setWizardMode] = useState<'investment' | 'budget'>('investment')
const [uploadTarget, setUploadTarget] = useState<ConnectorRead | null>(null)
```

Replace the existing `return (...)` JSX inside `ConnectorsPage` with:

```tsx
const tc = useTranslation('common').t

// Group connectors into sections
const investSources = connectors.filter(c => {
  const td = connectorTypes.find(t => t.type === c.type)
  return getSectionKey(c.type, td) === 'investment'
})
const budgetSources = connectors.filter(c => {
  const td = connectorTypes.find(t => t.type === c.type)
  return getSectionKey(c.type, td) === 'budget'
})
const feedSources = connectors.filter(c => {
  const td = connectorTypes.find(t => t.type === c.type)
  return getSectionKey(c.type, td) === 'feeds'
})

const activeSources = connectors.filter(c => c.is_active && c.last_run_status === 'success').length
const lastSyncAt = connectors
  .map(c => c.last_run_at)
  .filter(Boolean)
  .sort()
  .at(-1)

return (
  <div className="p-6 pb-20 md:pb-6">

    {/* Header */}
    <div className="flex items-center justify-between mb-6">
      <div>
        <h2 className="text-[16px] font-semibold text-gray-900">{tc('dataSources.title')}</h2>
        <p className="text-[12px] text-gray-400 mt-0.5">
          {connectors.length} {tc('dataSources.title').toLowerCase()} configured
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleSendReport}
          disabled={reportToast === 'sending'}
          className="flex items-center gap-1.5 px-3 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors">
          {reportToast === 'sending'
            ? <svg className="animate-spin" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>
            : <span>📱</span>}
          {reportToast === 'sent' ? 'Sent!' : reportToast === 'error' ? 'Failed' : tc('dataSources.sendReport')}
        </button>
      </div>
    </div>

    {/* Report toast */}
    {reportToast === 'sent' && (
      <div className="mb-4 flex items-center gap-2 px-4 py-2.5 bg-emerald-50 border border-emerald-100 rounded-xl text-[13px] text-emerald-700 font-medium">
        📱 Report sent to Telegram!
      </div>
    )}
    {reportToast === 'error' && (
      <div className="mb-4 flex items-center gap-2 px-4 py-2.5 bg-rose-50 border border-rose-100 rounded-xl text-[13px] text-rose-700 font-medium">
        Failed to send report — check Railway logs
      </div>
    )}

    {/* Stats bar */}
    <div className="grid grid-cols-2 gap-3 mb-6">
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3">
        <div className="text-[11px] text-gray-400 font-medium uppercase tracking-wide">{tc('dataSources.activeSources')}</div>
        <div className="text-[22px] font-bold text-gray-900 mt-0.5">
          {activeSources} <span className="text-[14px] font-normal text-gray-400">/ {connectors.length}</span>
        </div>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3">
        <div className="text-[11px] text-gray-400 font-medium uppercase tracking-wide">{tc('dataSources.lastSync')}</div>
        <div className="text-[14px] font-semibold text-gray-900 mt-0.5" dir="ltr">
          {lastSyncAt ? formatRelative(lastSyncAt) : tc('dataSources.neverSynced')}
        </div>
      </div>
    </div>

    {isLoading ? <LoadingCards /> : (
      <div className="space-y-8">
        {/* Investment sources */}
        <SourceSection
          title={tc('dataSources.sections.investment')}
          emoji="📈"
          badge={tc('dataSources.badges.autoSync')}
          sources={investSources}
          connectorTypes={connectorTypes}
          onAdd={() => { setWizardMode('investment'); setWizardOpen(true) }}
          onEdit={openEdit}
          onDelete={(c) => { setDeleteTarget(c); setDeleteError('') }}
          onRun={(c) => runMut.mutate(c.id)}
          onUpload={(c) => setUploadTarget(c)}
          onHistory={(c) => setHistoryTarget(c)}
          runningIds={runningIds}
        />
        {/* Budget sources */}
        <SourceSection
          title={tc('dataSources.sections.budget')}
          emoji="💳"
          badge={tc('dataSources.badges.manualUpload')}
          sources={budgetSources}
          connectorTypes={connectorTypes}
          onAdd={() => { setWizardMode('budget'); setWizardOpen(true) }}
          onEdit={openEdit}
          onDelete={(c) => { setDeleteTarget(c); setDeleteError('') }}
          onRun={(c) => runMut.mutate(c.id)}
          onUpload={(c) => setUploadTarget(c)}
          onHistory={(c) => setHistoryTarget(c)}
          runningIds={runningIds}
        />
        {/* Price & FX feeds */}
        {feedSources.length > 0 && (
          <SourceSection
            title={tc('dataSources.sections.feeds')}
            emoji="🌍"
            sources={feedSources}
            connectorTypes={connectorTypes}
            onAdd={null}
            onEdit={openEdit}
            onDelete={(c) => { setDeleteTarget(c); setDeleteError('') }}
            onRun={(c) => runMut.mutate(c.id)}
            onUpload={(c) => setUploadTarget(c)}
            onHistory={(c) => setHistoryTarget(c)}
            runningIds={runningIds}
          />
        )}
      </div>
    )}

    {/* Wizard modal */}
    <AddWizardModal
      open={wizardOpen}
      mode={wizardMode}
      editTarget={editTarget}
      connectorTypes={connectorTypes}
      accounts={accounts}
      onClose={closeModal}
      onSave={handleSubmit}
      isSaving={isSaving}
    />

    {/* Upload modal */}
    {uploadTarget && (
      <UploadModal
        connector={uploadTarget}
        connectorTypes={connectorTypes}
        onClose={() => setUploadTarget(null)}
        onSuccess={() => { setUploadTarget(null); qc.invalidateQueries({ queryKey: ['connectors'] }) }}
      />
    )}

    {/* Run history drawer */}
    {historyTarget && (
      <RunHistoryDrawer connector={historyTarget} onClose={() => setHistoryTarget(null)} />
    )}

    {/* Delete confirmation */}
    <ConfirmDialog
      open={!!deleteTarget}
      title={deleteTarget ? `Delete "${deleteTarget.name}"?` : ''}
      message={deleteError || 'This will also delete all run history for this connector.'}
      confirmLabel="Delete" danger
      onConfirm={() => {
        if (!deleteTarget) return
        setDeleteError('')
        deleteMut.mutate(deleteTarget.id, {
          onError: (err: unknown) => {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
            setDeleteError(detail ?? 'Cannot delete connector')
          },
        })
      }}
      onCancel={() => { setDeleteTarget(null); setDeleteError('') }}
    />
  </div>
)
```

- [ ] **Step 3: Add SourceSection component**

Add after `formatRelative` function (before the main component), a new `SourceSection` component:

```tsx
function SourceSection({
  title, emoji, badge, sources, connectorTypes, onAdd, onEdit, onDelete, onRun, onUpload, onHistory, runningIds,
}: {
  title: string
  emoji: string
  badge?: string
  sources: ConnectorRead[]
  connectorTypes: ConnectorType[]
  onAdd: (() => void) | null
  onEdit: (c: ConnectorRead) => void
  onDelete: (c: ConnectorRead) => void
  onRun: (c: ConnectorRead) => void
  onUpload: (c: ConnectorRead) => void
  onHistory: (c: ConnectorRead) => void
  runningIds: Set<string>
}) {
  const tc = useTranslation('common').t
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[18px]">{emoji}</span>
          <h3 className="text-[14px] font-semibold text-gray-800">{title}</h3>
          {badge && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 font-medium uppercase tracking-wide">
              {badge}
            </span>
          )}
        </div>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="flex items-center gap-1.5 text-[12px] font-medium text-teal-600 hover:text-teal-700 transition-colors">
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5.5 1v9M1 5.5h9"/></svg>
            {tc('dataSources.addSource')}
          </button>
        )}
      </div>
      {sources.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-200 p-6 text-center">
          <p className="text-[13px] text-gray-400">
            {onAdd ? (
              <>No sources yet. <button type="button" onClick={onAdd} className="text-teal-600 hover:underline">{tc('dataSources.addSource')}</button></>
            ) : 'No feeds configured.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {sources.map(c => {
            const td = connectorTypes.find(t => t.type === c.type)
            return (
              <DataSourceCard
                key={c.id}
                connector={c}
                typeDef={td}
                isRunning={runningIds.has(c.id) || c.last_run_status === 'running'}
                onEdit={() => onEdit(c)}
                onDelete={() => onDelete(c)}
                onRun={() => onRun(c)}
                onUpload={() => onUpload(c)}
                onHistory={() => onHistory(c)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd client && npx tsc --noEmit 2>&1 | head -30
```
Expected: errors only about missing `DataSourceCard`, `AddWizardModal`, `UploadModal` (added in later tasks)

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/ConnectorsPage.tsx
git commit -m "feat: data sources page layout — stats bar + three grouped sections"
```

---

## Task 5: Frontend — DataSourceCard (redesigned connector card)

**Files:**
- Modify: `client/src/pages/ConnectorsPage.tsx`

- [ ] **Step 1: Add DataSourceCard component**

Add `DataSourceCard` in `ConnectorsPage.tsx` after the `SourceSection` component:

```tsx
function DataSourceCard({
  connector: c, typeDef, isRunning, onEdit, onDelete, onRun, onUpload, onHistory,
}: {
  connector: ConnectorRead
  typeDef: ConnectorType | undefined
  isRunning: boolean
  onEdit: () => void
  onDelete: () => void
  onRun: () => void
  onUpload: () => void
  onHistory: () => void
}) {
  const tc = useTranslation('common').t
  const { label, color } = getStatusBadge(c, typeDef)
  const isManual = typeDef?.supports_manual_upload && !typeDef?.supports_auto_scrape

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 flex items-center gap-3">
      {/* Status dot */}
      <div className={clsx('w-2 h-2 rounded-full flex-shrink-0', {
        'bg-emerald-400': color === 'green',
        'bg-rose-400':    color === 'red',
        'bg-amber-400':   color === 'yellow',
        'bg-orange-400':  color === 'orange',
        'bg-gray-300':    color === 'gray',
      })} />

      {/* Name + details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-gray-900 truncate">{c.name}</span>
          <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', BADGE_COLORS[color])}>
            {tc(`dataSources.badges.${label}`)}
          </span>
          {!c.is_active && (
            <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-400">disabled</span>
          )}
        </div>
        <div className="text-[11px] text-gray-400 mt-0.5 flex items-center gap-2">
          <span className="font-mono" dir="ltr">{c.type}</span>
          {c.last_run_at && (
            <><span>·</span><span dir="ltr">{formatRelative(c.last_run_at)}</span></>
          )}
          {c.last_error && (
            <><span>·</span><span className="text-rose-500 truncate max-w-[200px]">{c.last_error}</span></>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1 flex-shrink-0">
        {isRunning ? (
          <span className="text-[11px] text-gray-400 px-2">Running…</span>
        ) : (
          <>
            {typeDef?.supports_manual_upload && (
              <button type="button" onClick={onUpload}
                className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium text-teal-600 border border-teal-200 rounded-lg hover:bg-teal-50 transition-colors">
                <svg width="11" height="11" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6.5 9V2M3 5l3.5-3.5L10 5"/><path d="M1 11h11"/></svg>
                {tc('dataSources.actions.uploadStatement')}
              </button>
            )}
            {typeDef?.supports_auto_scrape && (
              <button type="button" onClick={onRun} title={tc('dataSources.actions.run')}
                className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-teal-600 hover:bg-teal-50 transition-colors">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 2l9 4.5-9 4.5V2z"/></svg>
              </button>
            )}
          </>
        )}
        <button type="button" onClick={onHistory} title="Run history"
          className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="6.5" cy="6.5" r="5"/><path d="M6.5 3.5v3l2 1.5"/></svg>
        </button>
        <button type="button" onClick={onEdit} title={tc('dataSources.actions.edit')}
          className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-teal-600 hover:bg-teal-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 2l2 2-6 6H3V8l6-6z"/></svg>
        </button>
        <button type="button" onClick={onDelete} title={tc('dataSources.actions.delete')}
          className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-rose-500 hover:bg-rose-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h9M5 4V3h3v1M4 4l.5 6h4l.5-6"/></svg>
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Remove the old ConnectorCard function**

Delete the old `function ConnectorCard({...})` block (lines ~760–900 in original) — it is fully replaced by `DataSourceCard`.

- [ ] **Step 3: TypeScript check**

```bash
cd client && npx tsc --noEmit 2>&1 | head -20
```
Expected: only errors about missing `AddWizardModal` and `UploadModal`

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/ConnectorsPage.tsx
git commit -m "feat: DataSourceCard with status badge + action buttons driven by ConnectorType metadata"
```

---

## Task 6: Frontend — Add/Edit wizard modal

**Files:**
- Modify: `client/src/pages/ConnectorsPage.tsx`

The wizard is a modal with 3 steps. `mode='investment'` shows provider → (optional link asset) → credentials. `mode='budget'` shows provider → (optional connection method) → name & save. When `editTarget` is set, step 1 is locked.

- [ ] **Step 1: Add wizard state to ConnectorsPage**

Add these state variables inside `ConnectorsPage` (after `uploadTarget`):

```typescript
// Wizard internal state — lifted to parent so openEdit can pre-fill
const [wizStep, setWizStep] = useState<1 | 2 | 3>(1)
const [wizType, setWizType] = useState('')      // selected connector type key
const [wizMethod, setWizMethod] = useState<'auto' | 'manual'>('auto') // budget step 2
const [wizName, setWizName] = useState('')
const [wizConfig, setWizConfig] = useState<Record<string, string>>({})
```

Update `openEdit` to pre-fill wizard state (replace the existing `openEdit` function body):

```typescript
function openEdit(connector: ConnectorRead) {
  setEditTarget(connector)
  setWizType(connector.type)
  setWizName(connector.name)
  setWizConfig({})
  setWizStep(1)
  const td = connectorTypes.find(t => t.type === connector.type)
  const section = getSectionKey(connector.type, td)
  setWizardMode(section === 'budget' ? 'budget' : 'investment')
  setWizardOpen(true)
}
```

Update `closeModal` to also reset wizard state:

```typescript
function closeModal() {
  setWizardOpen(false)
  setEditTarget(null)
  setWizStep(1)
  setWizType('')
  setWizName('')
  setWizConfig({})
}
```

- [ ] **Step 2: Add AddWizardModal component**

Add `AddWizardModal` after `DataSourceCard`. This component handles both investment and budget wizard flows:

```tsx
// Credential fields per connector type
const CREDENTIAL_FIELDS: Record<string, { key: string; label: string; sensitive: boolean }[]> = {
  ib_flex:  [
    { key: 'query_id', label: 'Flex Query ID', sensitive: false },
    { key: 'token',    label: 'Flex Web Service Token', sensitive: true },
    { key: 'account_id', label: 'IB Account ID', sensitive: false },
  ],
  kraken:   [
    { key: 'api_key',    label: 'API Key',    sensitive: false },
    { key: 'api_secret', label: 'API Secret', sensitive: true },
  ],
  cexio:    [
    { key: 'api_key',    label: 'API Key',      sensitive: false },
    { key: 'api_secret', label: 'API Secret',   sensitive: true },
    { key: 'username',   label: 'Username',     sensitive: false },
  ],
  isracard: [
    { key: 'username', label: 'ID number (username)', sensitive: false },
    { key: 'password', label: 'Password',              sensitive: true },
  ],
  cal_scraper: [
    { key: 'username', label: 'Username', sensitive: false },
    { key: 'password', label: 'Password', sensitive: true },
  ],
}

function AddWizardModal({
  open, mode, editTarget, connectorTypes, accounts, onClose, onSave, isSaving,
}: {
  open: boolean
  mode: 'investment' | 'budget'
  editTarget: ConnectorRead | null
  connectorTypes: ConnectorType[]
  accounts: Account[]
  onClose: () => void
  onSave: (payload: Record<string, unknown>) => void
  isSaving: boolean
}) {
  const tc = useTranslation('common').t
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [selectedType, setSelectedType] = useState(editTarget?.type ?? '')
  const [connMethod, setConnMethod] = useState<'auto' | 'manual'>('auto')
  const [name, setName] = useState(editTarget?.name ?? '')
  const [config, setConfig] = useState<Record<string, string>>({})

  // Reset when modal opens
  useEffect(() => {
    if (!open) return
    setStep(1)
    setSelectedType(editTarget?.type ?? '')
    setName(editTarget?.name ?? '')
    setConfig({})
    setConnMethod('auto')
  }, [open, editTarget])

  const typeDef = connectorTypes.find(t => t.type === selectedType)
  const isEditing = !!editTarget

  // Filter provider options by mode
  const providers = connectorTypes.filter(t => {
    if (mode === 'investment') return t.flow_type === 'investment' && !FEED_TYPES.has(t.type)
    return t.flow_type === 'budget' || t.flow_type === 'both'
  })

  // Determine if step 2 is needed
  const needsStep2 = (() => {
    if (mode === 'investment') return typeDef && !typeDef.supports_multi_asset  // link asset
    // budget: show connection method only if type supports both or auto_scrape only
    return typeDef && typeDef.supports_auto_scrape
  })()

  const credFields = CREDENTIAL_FIELDS[selectedType] ?? []
  const isManualOnly = typeDef?.supports_manual_upload && !typeDef?.supports_auto_scrape

  function handleNext() {
    if (step === 1) {
      if (!name) setName(typeDef?.display_name ?? selectedType)
      setStep(needsStep2 ? 2 : 3)
    } else if (step === 2) {
      setStep(3)
    }
  }

  function handleBack() {
    if (step === 3) setStep(needsStep2 ? 2 : 1)
    else if (step === 2) setStep(1)
  }

  function handleSave() {
    const isManual = mode === 'budget' && connMethod === 'manual'
    const effectiveType = isEditing ? editTarget.type :
      (mode === 'budget' && connMethod === 'manual' && selectedType === 'isracard')
        ? 'isracard_xlsx'
        : selectedType

    const payload: Record<string, unknown> = {
      name,
      type: effectiveType,
      schedule: 'daily',
      is_active: true,
      config: Object.fromEntries(Object.entries(config).filter(([, v]) => v !== '')),
    }
    onSave(payload)
  }

  if (!open) return null

  const title = isEditing
    ? tc('dataSources.wizard.edit.title')
    : mode === 'investment'
      ? tc('dataSources.wizard.investment.title')
      : tc('dataSources.wizard.budget.title')

  const stepLabel = (() => {
    if (step === 1) return mode === 'investment'
      ? tc('dataSources.wizard.investment.step1')
      : tc('dataSources.wizard.budget.step1')
    if (step === 2) return mode === 'investment'
      ? tc('dataSources.wizard.investment.step2')
      : tc('dataSources.wizard.budget.step2')
    return mode === 'investment'
      ? tc('dataSources.wizard.investment.step3')
      : tc('dataSources.wizard.budget.step3')
  })()

  return (
    <Modal open={open} onClose={onClose} title={title} width="max-w-lg">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-5">
        {[1, 2, 3].map(n => {
          const active = n === step
          const done = n < step
          const visible = n === 1 || needsStep2 || n === 3
          if (!visible && n === 2) return null
          return (
            <div key={n} className="flex items-center gap-2">
              {n > 1 && <div className="h-px w-6 bg-gray-200" />}
              <div className={clsx('w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold',
                active ? 'bg-teal-600 text-white' : done ? 'bg-teal-100 text-teal-600' : 'bg-gray-100 text-gray-400')}>
                <span dir="ltr">{n}</span>
              </div>
              {active && <span className="text-[12px] text-gray-600 font-medium">{stepLabel}</span>}
            </div>
          )
        })}
      </div>

      {/* Edit lock warning */}
      {isEditing && step === 1 && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-100 rounded-lg text-[12px] text-amber-700">
          {tc('dataSources.wizard.edit.typeLockedWarning')}
        </div>
      )}

      {/* Step 1 — Provider grid */}
      {step === 1 && (
        <div className="grid grid-cols-2 gap-2">
          {providers.map(t => (
            <button
              key={t.type}
              type="button"
              disabled={isEditing}
              onClick={() => { setSelectedType(t.type); if (!name) setName(t.display_name) }}
              className={clsx(
                'text-start p-3 rounded-xl border-2 transition-colors',
                isEditing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:border-teal-300',
                selectedType === t.type ? 'border-teal-500 bg-teal-50' : 'border-gray-200 bg-white',
              )}>
              <div className="text-[13px] font-semibold text-gray-900" dir={t.display_name.match(/[֐-׿]/) ? 'rtl' : 'ltr'}>
                {t.display_name}
              </div>
              <div className="text-[11px] text-gray-400 mt-0.5 line-clamp-2">{t.description}</div>
            </button>
          ))}
        </div>
      )}

      {/* Step 2 — Investment: link asset info / Budget: connection method */}
      {step === 2 && mode === 'investment' && typeDef && (
        <div className="space-y-3">
          {typeDef.supports_multi_asset ? (
            <p className="text-[13px] text-gray-600 bg-blue-50 rounded-lg p-3">
              {tc('dataSources.wizard.investment.step2MultiAsset')}
            </p>
          ) : (
            <p className="text-[13px] text-gray-500">Link a specific asset to this source (optional).</p>
          )}
        </div>
      )}
      {step === 2 && mode === 'budget' && (
        <div className="space-y-3">
          <label className={clsx('flex items-start gap-3 p-3 rounded-xl border-2 cursor-pointer transition-colors',
            connMethod === 'auto' ? 'border-teal-500 bg-teal-50' : 'border-gray-200')}>
            <input type="radio" name="connMethod" value="auto" checked={connMethod === 'auto'}
              onChange={() => setConnMethod('auto')} className="mt-0.5" />
            <div>
              <div className="text-[13px] font-semibold text-gray-900">{tc('dataSources.wizard.budget.step2Auto')}</div>
              <div className="text-[12px] text-gray-500 mt-0.5">{tc('dataSources.wizard.budget.step2AutoDesc')}</div>
            </div>
          </label>
          <label className={clsx('flex items-start gap-3 p-3 rounded-xl border-2 cursor-pointer transition-colors',
            connMethod === 'manual' ? 'border-teal-500 bg-teal-50' : 'border-gray-200')}>
            <input type="radio" name="connMethod" value="manual" checked={connMethod === 'manual'}
              onChange={() => setConnMethod('manual')} className="mt-0.5" />
            <div>
              <div className="text-[13px] font-semibold text-gray-900">{tc('dataSources.wizard.budget.step2Manual')}</div>
              <div className="text-[12px] text-gray-500 mt-0.5">{tc('dataSources.wizard.budget.step2ManualDesc')}</div>
            </div>
          </label>
        </div>
      )}

      {/* Step 3 — Credentials + name */}
      {step === 3 && (
        <div className="space-y-4">
          {/* Name */}
          <div className="space-y-1">
            <label className="text-[12px] font-medium text-gray-700">{tc('dataSources.wizard.common.name')}</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={tc('dataSources.wizard.common.namePlaceholder')}
              className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400" />
          </div>

          {/* Credential fields (only for auto method) */}
          {(connMethod === 'auto' || mode === 'investment') && !isManualOnly && credFields.map(f => (
            <div key={f.key} className="space-y-1">
              <label className="text-[12px] font-medium text-gray-700">{f.label}</label>
              <input
                type={f.sensitive ? 'password' : 'text'}
                value={config[f.key] ?? ''}
                onChange={e => setConfig(c => ({ ...c, [f.key]: e.target.value }))}
                placeholder={isEditing ? tc('dataSources.wizard.edit.credentialsPlaceholder') : ''}
                className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 font-mono" />
            </div>
          ))}

          {/* Info note */}
          {(connMethod === 'manual' || isManualOnly) ? (
            <p className="text-[12px] text-gray-500 bg-blue-50 rounded-lg p-3">
              {tc('dataSources.wizard.budget.manualNote')}
            </p>
          ) : credFields.length > 0 ? (
            <p className="text-[11px] text-gray-400">
              🔒 {tc('dataSources.wizard.investment.credentialsEncrypted')}
            </p>
          ) : null}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-100">
        <button type="button" onClick={step === 1 ? onClose : handleBack}
          className="px-4 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
          {step === 1 ? tc('dataSources.wizard.common.cancel') : tc('dataSources.wizard.common.back')}
        </button>
        {step < 3 ? (
          <button type="button" onClick={handleNext} disabled={step === 1 && !selectedType}
            className="px-4 py-2 text-[13px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50">
            {tc('dataSources.wizard.common.next')}
          </button>
        ) : (
          <button type="button" onClick={handleSave} disabled={isSaving || !name}
            className="px-4 py-2 text-[13px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-60">
            {isSaving ? 'Saving…' : tc('dataSources.wizard.common.save')}
          </button>
        )}
      </div>
    </Modal>
  )
}
```

- [ ] **Step 3: Update handleSubmit to work with wizard payload**

Replace the existing `handleSubmit` function in the main component with:

```typescript
function handleSubmit(payload: Record<string, unknown>) {
  if (editTarget) {
    updateMut.mutate({ id: editTarget.id, payload })
  } else {
    createMut.mutate(payload)
  }
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd client && npx tsc --noEmit 2>&1 | head -20
```
Expected: only error about missing `UploadModal`

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/ConnectorsPage.tsx
git commit -m "feat: multi-step Add/Edit data source wizard with investment + budget flows"
```

---

## Task 7: Frontend — Upload statement modal

**Files:**
- Modify: `client/src/pages/ConnectorsPage.tsx`

Replace the existing `UploadSection` component (which shows a standalone upload section at the bottom) with `UploadModal` (a modal triggered by the "Upload statement" button on each card). The `UploadSection` is removed entirely.

- [ ] **Step 1: Add UploadModal component**

Add `UploadModal` in `ConnectorsPage.tsx` after `AddWizardModal`:

```tsx
function UploadModal({
  connector, connectorTypes, onClose, onSuccess,
}: {
  connector: ConnectorRead
  connectorTypes: ConnectorType[]
  onClose: () => void
  onSuccess: () => void
}) {
  const tc = useTranslation('common').t
  const typeDef = connectorTypes.find(t => t.type === connector.type)
  const needsAsset = typeDef?.requires_asset_selection_on_upload ?? false
  const acceptAttr = typeDef?.supported_file_types.map(e => `.${e}`).join(',') ?? '.pdf'

  const [file, setFile] = useState<File | null>(null)
  const [assetId, setAssetId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: assetList } = useQuery({
    queryKey: ['assets'],
    queryFn: () => getAssets({ limit: 500 }),
    enabled: needsAsset,
  })
  const assets = assetList?.items ?? []

  const canUpload = !!file && (!needsAsset || !!assetId)

  async function handleUpload() {
    if (!file || !canUpload) return
    setUploading(true)
    setError(null)
    try {
      const res = await uploadConnectorFile(connector.id, file, needsAsset ? assetId : undefined)
      setResult(res)
      onSuccess()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e)
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setUploading(false)
    }
  }

  const title = `${tc('dataSources.upload.title')} — ${connector.name}`

  return (
    <Modal open onClose={onClose} title={title} width="max-w-md">
      {result ? (
        /* Success state */
        <div className="space-y-4">
          <div className="text-center py-4">
            <div className="text-[32px] mb-2">✅</div>
            {'raw_created' in result ? (
              <>
                <div className="text-[16px] font-bold text-gray-900">
                  <span dir="ltr">{(result as Record<string, unknown>).raw_created as number}</span> {tc('dataSources.upload.success.transactions')}
                </div>
                {'budget_classified' in result && (
                  <div className="text-[13px] text-gray-500 mt-1">
                    {tc('dataSources.upload.success.autoClassified')}: <span dir="ltr">{(result as Record<string, unknown>).budget_classified as number}</span>
                    {' · '}
                    {tc('dataSources.upload.success.needsReview')}: <span dir="ltr">{(result as Record<string, unknown>).budget_needs_review as number}</span>
                  </div>
                )}
                {'date_range' in result && (result as Record<string, unknown>).date_range !== '—' && (
                  <div className="text-[12px] text-gray-400 mt-1" dir="ltr">{(result as Record<string, unknown>).date_range as string}</div>
                )}
              </>
            ) : 'created' in result ? (
              <div className="text-[16px] font-bold text-gray-900">
                <span dir="ltr">{result.created}</span> {tc('dataSources.upload.success.transactions')}
              </div>
            ) : 'report_date' in result ? (
              <>
                <div className="text-[14px] font-semibold text-gray-900">
                  BTB report — <span dir="ltr">{result.report_date}</span>
                </div>
                <div className="text-[13px] text-gray-600 mt-1" dir="ltr">
                  ₪{result.current_value.toLocaleString('en-IL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </>
            ) : null}
          </div>
          <button type="button" onClick={onClose}
            className="w-full px-4 py-2 text-[13px] font-medium border border-gray-200 rounded-lg hover:bg-gray-50">
            Close
          </button>
        </div>
      ) : (
        /* Upload form */
        <div className="space-y-4">
          {/* File type hint */}
          <p className="text-[12px] text-gray-500">
            {tc('dataSources.upload.accepts')}: <span dir="ltr" className="font-mono">{acceptAttr}</span>
          </p>

          {/* Asset picker (if required) */}
          {needsAsset && (
            <div className="space-y-1">
              <label className="text-[12px] font-medium text-gray-700">{tc('dataSources.upload.asset')}</label>
              <select value={assetId} onChange={e => setAssetId(e.target.value)}
                className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400">
                <option value="">— select asset —</option>
                {assets.map(a => (
                  <option key={a.id} value={a.id}>{a.name} ({a.symbol})</option>
                ))}
              </select>
            </div>
          )}

          {/* File input */}
          <div className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center hover:border-teal-300 transition-colors">
            {file ? (
              <div className="space-y-2">
                <div className="text-[13px] font-medium text-gray-700" dir="ltr">{file.name}</div>
                <div className="text-[11px] text-gray-400">{(file.size / 1024).toFixed(0)} KB</div>
                <button type="button" onClick={() => setFile(null)}
                  className="text-[11px] text-rose-500 hover:underline">Remove</button>
              </div>
            ) : (
              <label className="cursor-pointer block">
                <div className="text-[13px] text-gray-500">{tc('dataSources.upload.dragDrop')}</div>
                <input type="file" accept={acceptAttr} className="hidden"
                  onChange={e => setFile(e.target.files?.[0] ?? null)} />
                <div className="mt-2 inline-flex px-3 py-1.5 text-[12px] font-medium text-teal-600 border border-teal-200 rounded-lg hover:bg-teal-50">
                  {tc('dataSources.upload.chooseFile')}
                </div>
              </label>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="text-[12px] text-rose-600 bg-rose-50 rounded-lg px-3 py-2">{error}</div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 px-4 py-2 text-[13px] font-medium border border-gray-200 rounded-lg hover:bg-gray-50">
              Cancel
            </button>
            <button type="button" onClick={handleUpload} disabled={!canUpload || uploading}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-[13px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50">
              {uploading ? (
                <><svg className="animate-spin" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>{tc('dataSources.upload.uploading')}</>
              ) : (
                <><svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round"><path d="M6.5 9V2M3 5l3.5-3.5L10 5"/><path d="M1 11h11"/></svg>Upload</>
              )}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}
```

- [ ] **Step 2: Remove old UploadSection**

Delete the entire `function UploadSection({...})` block (~lines 1023–1250 in original). It is fully replaced by `UploadModal`.

Also remove `<UploadSection ... />` from the main component JSX (already removed in Task 4's JSX rewrite).

- [ ] **Step 3: TypeScript check — must be clean**

```bash
cd client && npx tsc --noEmit 2>&1
```
Expected: no errors

- [ ] **Step 4: Run parser tests to ensure no backend regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v 2>&1 | tail -5
```
Expected: 14 passed

- [ ] **Step 5: Commit and push**

```bash
git add client/src/pages/ConnectorsPage.tsx
git commit -m "feat: upload statement modal — replaces UploadSection, inline on each card"
git push
```

---

## Self-Review

**Spec coverage check:**

| Part | Task |
|---|---|
| Part 1: Update ConnectorTypeDef | Task 1 ✓ |
| Part 2: Rename page to "Data sources" | Task 2 (nav key), Task 4 (title) ✓ |
| Part 3: Three grouped sections | Task 4 (SourceSection, grouping) ✓ |
| Part 4: Add data source wizard | Task 6 (AddWizardModal) ✓ |
| Part 5: Edit data source | Task 6 (editTarget pre-fill, type-locked) ✓ |
| Part 6: Upload statement modal | Task 7 (UploadModal) ✓ |
| Part 7: Summary stats bar | Task 4 (stats grid) ✓ |
| Part 8: Send report button | Task 4 (preserved from existing) ✓ |
| Part 9: i18n | Task 2 ✓ |

**No placeholder scan:** All steps have concrete code. No TBD/TODO.

**Type consistency:**
- `ConnectorType` extended in Task 3, used in Tasks 4/5/6/7 ✓
- `getStatusBadge` returns `{ label, color }` used in Task 5 `DataSourceCard` ✓
- `BADGE_COLORS` defined in Task 4, used in Task 5 ✓
- `getSectionKey` defined in Task 4, used in Tasks 4/5 ✓
- `FEED_TYPES` defined in Task 4, used in Tasks 4/6 ✓
- `UploadResult` imported from `../api/portfolio` — already exported ✓
- `uploadConnectorFile` imported in Task 7 — already imported in file ✓
- `getAssets` imported in Task 7 — already imported in file ✓
