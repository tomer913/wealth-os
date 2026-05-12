# BTB Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Be The Bank (BTB) monthly PDF upload connector that parses portfolio summary fields, upserts a manual valuation + monthly income transaction, and appears as a third option in the existing upload section alongside Mizrachi and FIBI.

**Architecture:** New parser at `backend/app/connectors/parsers/btb.py` extracts labeled Hebrew fields via pdfplumber + regex. New dedicated router `backend/app/routers/btb.py` (registered with prefix `/api/v1`) serves `POST /connectors/btb/upload/` — it upserts a `ManualValuation` row and inserts an `INCOME` `Transaction` (idempotent via `external_reference_id` check). Frontend extends the existing `UploadSection` with a static BTB entry (not DB-driven) that dispatches to a dedicated `uploadBTBReport()` API call and renders a valuation summary result; bank connectors keep their existing transaction-count display.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, pdfplumber (already in requirements), React 18, TypeScript, Axios

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/connectors/parsers/btb.py` | **CREATE** | PDF text extraction + field parsing |
| `backend/tests/__init__.py` | **CREATE** | test package root |
| `backend/tests/parsers/__init__.py` | **CREATE** | parsers test package |
| `backend/tests/parsers/test_btb.py` | **CREATE** | parser unit tests |
| `backend/app/routers/btb.py` | **CREATE** | upload endpoint + DB upsert logic |
| `backend/app/main.py` | **MODIFY** | register btb router |
| `client/src/api/portfolio.ts` | **MODIFY** | add `uploadBTBReport()` + `BTBUploadResult` type |
| `client/src/pages/ConnectorsPage.tsx` | **MODIFY** | extend `UploadSection` with BTB option |

---

## Task 1: BTB PDF Parser (TDD)

**Files:**
- Create: `backend/app/connectors/parsers/btb.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/parsers/__init__.py`
- Create: `backend/tests/parsers/test_btb.py`

- [ ] **Step 1: Create test package init files**

```bash
touch backend/tests/__init__.py backend/tests/parsers/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/parsers/test_btb.py`:

```python
import pytest
from datetime import date
from app.connectors.parsers.btb import _parse_report_date, _extract_amount, _extract_pct, _parse_btb_text

# Mirrors the April 2026 report structure. Numbers match the spec test values.
SAMPLE_TEXT = """
דו"ח חודשי אישי לחודש אפריל 2026
יתרה נוכחית ₪408,207.85
הפקדות ₪530,000.00
נמשך מהחשבון ₪150,000.00
ריבית ברוטו עד היום ₪39,152.55
מס שקוזז ₪4,980.19
ריבית אפקטיבית (נטו) עד היום 13.72%
ריבית ממוצעת בתיק ההשקעות 8.49%
רווח מריבית בחודש הקודם (נטו אחרי מס) 0.53%
דמי ניהול חודשיים ₪242.60
"""


def test_parse_report_date_april_2026():
    assert _parse_report_date(SAMPLE_TEXT) == date(2026, 4, 30)


def test_parse_report_date_january():
    text = 'דו"ח חודשי אישי לחודש ינואר 2026'
    assert _parse_report_date(text) == date(2026, 1, 31)


def test_parse_report_date_missing_returns_none():
    assert _parse_report_date("some random text") is None


def test_extract_current_value():
    assert _extract_amount(SAMPLE_TEXT, "יתרה נוכחית") == 408207.85


def test_extract_deposits():
    assert _extract_amount(SAMPLE_TEXT, "הפקדות") == 530000.00


def test_extract_withdrawn():
    assert _extract_amount(SAMPLE_TEXT, "נמשך מהחשבון") == 150000.00


def test_extract_gross_interest():
    assert _extract_amount(SAMPLE_TEXT, "ריבית ברוטו עד היום") == 39152.55


def test_extract_tax():
    assert _extract_amount(SAMPLE_TEXT, "מס שקוזז") == 4980.19


def test_extract_net_return_pct():
    assert _extract_pct(SAMPLE_TEXT, "ריבית אפקטיבית (נטו) עד היום") == 13.72


def test_extract_avg_rate():
    assert _extract_pct(SAMPLE_TEXT, "ריבית ממוצעת בתיק ההשקעות") == 8.49


def test_extract_last_month_return():
    assert _extract_pct(SAMPLE_TEXT, "רווח מריבית בחודש הקודם (נטו אחרי מס)") == 0.53


def test_extract_mgmt_fee():
    assert _extract_amount(SAMPLE_TEXT, "דמי ניהול חודשיים") == 242.60


def test_parse_btb_text_full_report():
    result = _parse_btb_text(SAMPLE_TEXT)
    assert result["report_date"] == date(2026, 4, 30)
    assert result["current_value"] == 408207.85
    assert result["total_deposits"] == 530000.00
    assert result["total_withdrawn"] == 150000.00
    assert result["gross_interest"] == 39152.55
    assert result["tax_withheld"] == 4980.19
    assert result["net_return_pct"] == 13.72
    assert result["avg_interest_rate"] == 8.49
    assert result["last_month_return_pct"] == 0.53
    assert result["mgmt_fee"] == 242.60
    assert result["net_invested"] == 380000.00  # 530000 - 150000


def test_parse_btb_text_raises_on_missing_date():
    with pytest.raises(ValueError, match="report month"):
        _parse_btb_text("no date here ₪408,207.85")
```

- [ ] **Step 3: Run tests — confirm they fail**

```bash
cd backend
python -m pytest tests/parsers/test_btb.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'app.connectors.parsers.btb'`

- [ ] **Step 4: Implement the parser**

Create `backend/app/connectors/parsers/btb.py`:

```python
"""
Be The Bank (BTB Israel) — monthly PDF portfolio report parser.

The PDF is a 1-page Hebrew RTL report with labeled fields.
pdfplumber extracts the full text; one regex per field label finds the value.

Returns a single dict (not a list of rows) — the PDF is a snapshot, not a
list of transactions.
"""
import calendar
import io
import logging
import re
from datetime import date as date_type
from typing import Optional

log = logging.getLogger(__name__)

_HEBREW_MONTHS = {
    'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'אפריל': 4,
    'מאי': 5, 'יוני': 6, 'יולי': 7, 'אוגוסט': 8,
    'ספטמבר': 9, 'אוקטובר': 10, 'נובמבר': 11, 'דצמבר': 12,
}

# Matches: דו"ח חודשי אישי לחודש אפריל 2026
_TITLE_RE = re.compile(
    r'לחודש\s+(' + '|'.join(_HEBREW_MONTHS) + r')\s+(\d{4})'
)


def _parse_report_date(text: str) -> Optional[date_type]:
    """Return last calendar day of the month/year found in the report title."""
    m = _TITLE_RE.search(text)
    if not m:
        return None
    month = _HEBREW_MONTHS[m.group(1)]
    year = int(m.group(2))
    last_day = calendar.monthrange(year, month)[1]
    return date_type(year, month, last_day)


def _extract_amount(text: str, label: str) -> float:
    """Find label then return the ₪ amount that follows within ~120 chars."""
    pattern = rf"{re.escape(label)}[^₪\d]{{0,120}}₪?\s*([\d,]+\.?\d*)"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return float(m.group(1).replace(',', ''))
    return 0.0


def _extract_pct(text: str, label: str) -> float:
    """Find label then return the % value that follows within ~120 chars."""
    pattern = rf"{re.escape(label)}[^%\d]{{0,120}}([\d]+\.?[\d]*)%"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return float(m.group(1))
    return 0.0


def _parse_btb_text(text: str) -> dict:
    """
    Parse all fields from pdfplumber-extracted text.

    Raises ValueError if the report month/year cannot be found.
    """
    report_date = _parse_report_date(text)
    if report_date is None:
        raise ValueError("Could not find report month/year in PDF text")

    total_deposits = _extract_amount(text, "הפקדות")
    total_withdrawn = _extract_amount(text, "נמשך מהחשבון")

    return {
        'report_date': report_date,
        'current_value': _extract_amount(text, "יתרה נוכחית"),
        'total_deposits': total_deposits,
        'total_withdrawn': total_withdrawn,
        'gross_interest': _extract_amount(text, "ריבית ברוטו עד היום"),
        'tax_withheld': _extract_amount(text, "מס שקוזז"),
        'net_return_pct': _extract_pct(text, "ריבית אפקטיבית (נטו) עד היום"),
        'avg_interest_rate': _extract_pct(text, "ריבית ממוצעת בתיק ההשקעות"),
        'last_month_return_pct': _extract_pct(text, "רווח מריבית בחודש הקודם (נטו אחרי מס)"),
        'mgmt_fee': _extract_amount(text, "דמי ניהול חודשיים"),
        'net_invested': round(total_deposits - total_withdrawn, 4),
    }


def parse_btb_pdf(file_bytes: bytes) -> dict:
    """
    Parse a BTB monthly portfolio report PDF.

    Args:
        file_bytes: Raw bytes of the PDF file.

    Returns:
        Dict with report_date (date) and all numeric fields (float).

    Raises:
        RuntimeError: pdfplumber not installed.
        ValueError: required fields not found in the PDF.
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber is required: pip install pdfplumber")

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    log.debug("parse_btb_pdf: extracted %d chars", len(text))
    result = _parse_btb_text(text)
    log.info(
        "parse_btb_pdf: report_date=%s current_value=%.2f",
        result['report_date'], result['current_value'],
    )
    return result
```

- [ ] **Step 5: Run tests — confirm all pass**

```bash
cd backend
python -m pytest tests/parsers/test_btb.py -v
```
Expected: 13/13 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/connectors/parsers/btb.py \
        backend/tests/__init__.py \
        backend/tests/parsers/__init__.py \
        backend/tests/parsers/test_btb.py
git commit -m "feat: BTB PDF parser — Hebrew field extraction + unit tests"
```

---

## Task 2: BTB Upload Endpoint

**Files:**
- Create: `backend/app/routers/btb.py`
- Modify: `backend/app/main.py` (add 2 lines)

- [ ] **Step 1: Create the router**

Create `backend/app/routers/btb.py`:

```python
"""
BTB (Be The Bank) upload endpoint.

POST /api/v1/connectors/btb/upload/
  Accepts monthly PDF, parses it, then:
    1. Upserts ManualValuation for the BTB asset (same date → update).
    2. Inserts INCOME Transaction for last month's net return (idempotent).
  Returns parsed summary as JSON.
"""
import logging
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.transaction import Transaction
from app.models.valuation import ManualValuation

router = APIRouter(prefix="/connectors/btb", tags=["btb"])
log = logging.getLogger(__name__)

_BTB_ASSET_ID = uuid.UUID("f8b355d3-920d-5ee4-b9dd-a24efd5bd545")


@router.post("/upload/")
async def upload_btb_report(
    file: UploadFile = File(...),
    portfolio_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Parse a BTB monthly PDF, upsert valuation, insert income transaction."""
    await verify_portfolio_access(
        db, portfolio_id,
        current_user["user_id"], current_user.get("org_id"),
        required_role="editor",
    )

    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="BTB connector accepts PDF files only")

    file_bytes = await file.read()

    try:
        from app.connectors.parsers.btb import parse_btb_pdf
        parsed = parse_btb_pdf(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse BTB report: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read PDF: {exc}") from exc

    report_date = parsed["report_date"]

    # ── Upsert ManualValuation ────────────────────────────────────────────────
    month_label = report_date.strftime("%B %Y")
    notes = (
        f"BTB {month_label} — "
        f"net return {parsed['net_return_pct']}%, "
        f"avg rate {parsed['avg_interest_rate']}%"
    )

    existing_val = (await db.execute(
        select(ManualValuation).where(
            ManualValuation.asset_id == _BTB_ASSET_ID,
            ManualValuation.valuation_date == report_date,
        )
    )).scalar_one_or_none()

    if existing_val:
        existing_val.market_value = parsed["current_value"]
        existing_val.value_ils = parsed["current_value"]
        existing_val.notes = notes
        valuation_action = "updated"
    else:
        db.add(ManualValuation(
            portfolio_id=portfolio_id,
            asset_id=_BTB_ASSET_ID,
            valuation_date=report_date,
            market_value=parsed["current_value"],
            currency="ILS",
            fx_rate_to_ils=1.0,
            value_ils=parsed["current_value"],
            valuation_method="manual",
            confidence_level="high",
            source="btb_pdf",
            notes=notes,
        ))
        valuation_action = "created"

    # ── Insert Income Transaction (idempotent) ────────────────────────────────
    ext_ref = f"btb_{report_date.isoformat()}_monthly_income"
    existing_tx = (await db.execute(
        select(Transaction).where(Transaction.external_reference_id == ext_ref)
    )).scalar_one_or_none()

    if not existing_tx:
        income_amount = round(
            parsed["last_month_return_pct"] * parsed["current_value"] / 100, 4
        )
        db.add(Transaction(
            portfolio_id=portfolio_id,
            asset_id=_BTB_ASSET_ID,
            transaction_date=report_date,
            type="INCOME",
            economic_type="income",
            domain="alternatives",
            total_amount=income_amount,
            currency="ILS",
            source="btb_pdf",
            external_reference_id=ext_ref,
            status="confirmed",
        ))
        tx_action = "created"
    else:
        tx_action = "skipped"

    await db.commit()

    log.info(
        "BTB upload: portfolio=%s date=%s value=%.2f valuation=%s tx=%s",
        portfolio_id, report_date, parsed["current_value"], valuation_action, tx_action,
    )

    return {
        "report_date": report_date.isoformat(),
        "current_value": parsed["current_value"],
        "net_invested": parsed["net_invested"],
        "last_month_return_pct": parsed["last_month_return_pct"],
        "net_return_pct": parsed["net_return_pct"],
        "avg_interest_rate": parsed["avg_interest_rate"],
        "gross_interest": parsed["gross_interest"],
        "tax_withheld": parsed["tax_withheld"],
        "mgmt_fee": parsed["mgmt_fee"],
        "valuation": valuation_action,
        "transaction": tx_action,
    }
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add two lines:

```python
# After line: from app.routers import connectors as connectors_router
from app.routers import btb as btb_router

# After line: app.include_router(connectors_router.router, prefix="/api/v1")
app.include_router(btb_router.router, prefix="/api/v1")
```

- [ ] **Step 3: Verify endpoint is registered**

```bash
cd backend
uvicorn app.main:app --port 8001 &
sleep 3
curl -s http://localhost:8001/openapi.json | python -m json.tool | grep -A1 "btb"
kill %1
```
Expected output includes: `"/api/v1/connectors/btb/upload/"`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/btb.py backend/app/main.py
git commit -m "feat: BTB upload endpoint — upsert valuation + idempotent income transaction"
```

---

## Task 3: Frontend API Function

**Files:**
- Modify: `client/src/api/portfolio.ts`

- [ ] **Step 1: Add BTBUploadResult type and uploadBTBReport function**

In `client/src/api/portfolio.ts`, add after the existing `uploadBankStatement` function:

```typescript
export interface BTBUploadResult {
  report_date: string           // "2026-04-30"
  current_value: number
  net_invested: number
  last_month_return_pct: number
  net_return_pct: number
  avg_interest_rate: number
  gross_interest: number
  tax_withheld: number
  mgmt_fee: number
  valuation: 'created' | 'updated'
  transaction: 'created' | 'skipped'
}

export async function uploadBTBReport(
  portfolioId: string,
  file: File,
): Promise<BTBUploadResult> {
  const form = new FormData()
  form.append('portfolio_id', portfolioId)
  form.append('file', file)
  const { data } = await apiClient.post('/api/v1/connectors/btb/upload/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd client
npx tsc --noEmit 2>&1
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add client/src/api/portfolio.ts
git commit -m "feat: add uploadBTBReport API function + BTBUploadResult type"
```

---

## Task 4: Frontend UploadSection — Add BTB Option

**Files:**
- Modify: `client/src/pages/ConnectorsPage.tsx`

- [ ] **Step 1: Update the import line**

Find this line near the top of `ConnectorsPage.tsx`:

```typescript
import { DEFAULT_PORTFOLIO_ID, uploadBankStatement } from '../api/portfolio'
```

Replace with:

```typescript
import { DEFAULT_PORTFOLIO_ID, uploadBankStatement, uploadBTBReport, BTBUploadResult } from '../api/portfolio'
```

- [ ] **Step 2: Add types and BTB static entry above UploadSection**

Find the line `const UPLOAD_TYPES = ['mizrachi_bank', 'fibi_bank']` and add the following directly below it:

```typescript
// BTB is a static upload option — it has no Connector DB record.
// UploadOption is a minimal shape shared by DB connectors and the BTB entry.
interface UploadOption {
  id: string
  name: string
  type: string
  portfolio_id: string
}

const BTB_STATIC: UploadOption = {
  id: '__btb__',
  name: 'BTB - Be The Bank',
  type: 'btb',
  portfolio_id: DEFAULT_PORTFOLIO_ID,
}

type BankResult = { kind: 'bank'; created: number; skipped: number; total: number }
type BTBResult  = { kind: 'btb' } & BTBUploadResult
type AnyResult  = BankResult | BTBResult
```

- [ ] **Step 3: Replace the UploadSection function body**

Find the entire `function UploadSection(...)` from line 982 to its closing `}` (around line 1079) and replace with:

```typescript
function UploadSection({ connectors, onUploaded }: { connectors: ConnectorRead[]; onUploaded: () => void }) {
  const bankOptions: UploadOption[] = connectors
    .filter(c => UPLOAD_TYPES.includes(c.type) && c.is_active)
    .map(c => ({ id: c.id, name: c.name, type: c.type, portfolio_id: c.portfolio_id }))
  const allOptions: UploadOption[] = [...bankOptions, BTB_STATIC]

  const [selectedId, setSelectedId] = useState('')
  const [file, setFile]             = useState<File | null>(null)
  const [result, setResult]         = useState<AnyResult | null>(null)
  const [error, setError]           = useState<string | null>(null)
  const [uploading, setUploading]   = useState(false)
  const fileRef = useMemo(() => ({ current: null as HTMLInputElement | null }), [])

  const selected   = allOptions.find(c => c.id === selectedId) ?? allOptions[0] ?? null
  const isBTB      = selected?.type === 'btb'
  const acceptAttr = isBTB ? '.pdf' : '.pdf,.xls,.xlsx'

  async function handleUpload() {
    if (!file || !selected) return
    setUploading(true)
    setResult(null)
    setError(null)
    try {
      if (isBTB) {
        const res = await uploadBTBReport(selected.portfolio_id, file)
        setResult({ kind: 'btb', ...res })
      } else {
        const res = await uploadBankStatement(selected.type, selected.portfolio_id, file)
        setResult({ kind: 'bank', ...res })
      }
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      onUploaded()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e)
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setUploading(false)
    }
  }

  if (allOptions.length === 0) return null

  return (
    <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h3 className="text-[14px] font-semibold text-gray-900 mb-1">Upload bank statement</h3>
      <p className="text-[12px] text-gray-400 mb-4">Manually import a PDF or XLSX export from your bank</p>

      <div className="flex flex-wrap items-end gap-3">
        {/* Connector picker */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-gray-500 font-medium">Bank</label>
          <select
            value={selectedId || selected?.id || ''}
            onChange={e => setSelectedId(e.target.value)}
            className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-teal-400"
          >
            {allOptions.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        {/* File picker — accept changes based on selected bank */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-gray-500 font-medium">File</label>
          <input
            type="file"
            accept={acceptAttr}
            ref={el => { fileRef.current = el }}
            onChange={e => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null) }}
            className="text-[13px] text-gray-700 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-gray-200 file:text-[12px] file:bg-white file:text-gray-600 hover:file:bg-gray-50 cursor-pointer"
          />
        </div>

        {/* Upload button */}
        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="flex items-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-[13px] font-medium rounded-lg disabled:opacity-50 transition-colors"
        >
          {uploading ? (
            <svg className="animate-spin" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>
          ) : (
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round"><path d="M6.5 9V2M3 5l3.5-3.5L10 5"/><path d="M1 11h11"/></svg>
          )}
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </div>

      {/* Result — bank: transaction counts */}
      {result?.kind === 'bank' && (
        <div className="mt-3 flex items-center gap-2 text-[12px] text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 6.5l3 3 6-6"/></svg>
          <span>
            <strong>{result.created}</strong> new transactions imported,{' '}
            <strong>{result.skipped}</strong> already existed
            {result.total > 0 && ` (${result.total} total in file)`}
          </span>
        </div>
      )}

      {/* Result — BTB: valuation summary */}
      {result?.kind === 'btb' && (
        <div className="mt-3 text-[12px] text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2 space-y-1">
          <div className="flex items-center gap-2 font-medium">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 6.5l3 3 6-6"/></svg>
            BTB report uploaded — {result.report_date}
          </div>
          <div className="ml-5 grid grid-cols-2 gap-x-6 gap-y-0.5 text-gray-700">
            <span>Current value</span>
            <span className="font-medium">
              ₪{result.current_value.toLocaleString('he-IL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span>Net invested</span>
            <span className="font-medium">
              ₪{result.net_invested.toLocaleString('he-IL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span>Last month return</span>
            <span className="font-medium">{result.last_month_return_pct}%</span>
            <span>Net return to date</span>
            <span className="font-medium">{result.net_return_pct}%</span>
          </div>
        </div>
      )}

      {error && (
        <div className="mt-3 text-[12px] text-rose-600 bg-rose-50 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd client
npx tsc --noEmit 2>&1
```
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/ConnectorsPage.tsx
git commit -m "feat: add BTB to upload section — static entry, polymorphic result display"
```

---

## Task 5: End-to-End Verification

- [ ] **Step 1: Run all parser tests**

```bash
cd backend
python -m pytest tests/parsers/test_btb.py -v
```
Expected: 13/13 PASS

- [ ] **Step 2: Verify endpoint route in OpenAPI**

```bash
cd backend
uvicorn app.main:app --port 8001 &
sleep 3
curl -s http://localhost:8001/openapi.json | python -m json.tool | grep "btb"
kill %1
```
Expected: `"/api/v1/connectors/btb/upload/"` in output

- [ ] **Step 3: Start frontend, open Connectors page**

```bash
cd client && npm run dev
```
Open the Connectors page. In the Upload section:
- Dropdown should show `BTB - Be The Bank` as an option alongside Mizrachi/FIBI
- Selecting BTB should set the file picker to accept `.pdf` only
- Selecting Mizrachi or FIBI should revert to `.pdf,.xls,.xlsx`

- [ ] **Step 4: Upload a real BTB PDF and verify result display**

Upload the April 2026 PDF. Expected success banner shows:
- "BTB report uploaded — 2026-04-30"
- Current value: ₪408,207.85
- Net invested: ₪380,000.00
- Last month return: 0.53%
- Net return to date: 13.72%

- [ ] **Step 5: Upload same PDF again — verify idempotency**

Upload the same file. Expected:
- Same success banner (no error)
- Backend response: `"valuation": "updated"`, `"transaction": "skipped"`

- [ ] **Step 6: Push**

```bash
git push
```

---

## Regex Fallback Note

If the actual BTB PDF has a different text layout than the sample (e.g., value appears *before* the label due to RTL reversal), the `_extract_amount` / `_extract_pct` regexes will return `0.0` silently. To diagnose: add a temporary `log.debug("full text: %s", text)` in `parse_btb_pdf` and check the Railway logs after the first real upload. Adjust the label patterns in `btb.py` accordingly and re-run the unit tests.
