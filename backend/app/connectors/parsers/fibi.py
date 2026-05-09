"""
First International Bank of Israel (FIBI) — XLS and PDF statement parsers.

XLS layout (export from FIBI online banking, sheet name "Activities"):
  Rows 0-4:  metadata headers (account number, date range, etc.)
  Row 5:     column headers (Hebrew)
  Row 6:     opening balance row
  Rows 7+:   actual transaction data

  Columns (0-indexed):
    0  —  empty (always NaN)
    1  יתרה          Balance        (ignore for amount)
    2  תאריך ערך     Value date
    3  זכות          Credit         (positive inflow)
    4  חובה          Debit          (positive, negate for amount)
    5  תאור          Description
    6  אסמכתא        Reference number
    7  סוג פעולה     Op code        (e.g. '466')
    8  תאריך         Transaction date  ← USE THIS as the canonical date

PDF layout: same fields via text extraction (legacy fallback).
"""
import hashlib
import io
import logging
import re
from datetime import date as date_type
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_DATE_RE = re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})")
_AMOUNT_RE = re.compile(r"-?[\d,]+\.\d{2}")

# ── XLS constants ─────────────────────────────────────────────────────────────

FIBI_OP_CODE_MAP: Dict[str, str] = {
    '466': 'BUY',               # נע-קניה   — kaspit fund purchase
    '416': 'SELL',              # נע-מכירה  — kaspit fund sale
    '240': 'FINANCING_INFLOW',  # הלוואה - תשלום קרן — loan disbursement
    '293': 'FINANCING_OUTFLOW', # הלואה-תשלום — loan principal repayment
    '290': 'FINANCING_OUTFLOW', # הלוואה - תשלום קרן
    '495': 'EXPENSE',           # ריבית על הלוואה — loan interest charged
    '245': 'EXPENSE',           # הלוואה - תשלום ריבית
    '295': 'EXPENSE',           # הלוואה - תשלום ריבית
    '222': 'INCOME',            # משהב"ט-תגמולים / אגף השיקום
    '272': 'TRANSFER',          # העברה מהחשבון
    '212': 'INCOME',            # מענק מיוחד מהבנק
}

FIBI_ASSET_MAP: Dict[str, Dict[str, str]] = {
    '510351': {
        'symbol': 'IBI_CASH',
        'asset_id': '3d28abc7-8bb2-55ec-b6c4-d351b54bdeea',
        'domain': 'securities',
    },
    '514078': {
        'symbol': 'CASH_FIBI',
        'asset_id': '4c324483-e8ef-4ebf-ae4d-ca4e51f69ca8',
        'domain': 'securities',
    },
}

_FIBI_ACCOUNT_ID = 'd34d0d6a-6f5c-4ebc-a305-f0dcc619d5e0'
_FIBI_SOURCE = 'fibi_bank'


# ── XLS parser ────────────────────────────────────────────────────────────────

def parse_fibi_xlsx(file_path: str, portfolio_id: str) -> List[Dict[str, Any]]:
    """
    Parse a FIBI bank XLS export file and return a list of raw transaction dicts
    ready for insertion into raw_transactions via the ingest pipeline.

    Args:
        file_path: Path to the .xls file downloaded from FIBI online banking
        portfolio_id: UUID string of the active portfolio

    Returns:
        List of transaction dicts in raw_transaction ingest format
    """
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas is required: pip install pandas")

    ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else 'xls'
    engine = 'openpyxl' if ext == 'xlsx' else 'xlrd'

    try:
        df = pd.read_excel(file_path, sheet_name='Activities', header=None, engine=engine)
    except Exception as exc:
        log.error("parse_fibi_xlsx: failed to read %s (engine=%s): %s", file_path, engine, exc)
        raise

    if len(df) <= 7:
        log.warning("parse_fibi_xlsx: file has only %d rows, need >7", len(df))
        return []

    # Rows 0-6 are metadata / header / opening balance — skip them
    data = df.iloc[7:].reset_index(drop=True)

    raw_txns: List[Dict[str, Any]] = []
    for _, row in data.iterrows():
        cells = list(row)
        if len(cells) < 9:
            continue

        # Column 8: canonical transaction date
        tx_date = _parse_date_cell(cells[8])
        if tx_date is None:
            continue

        # Column 2: value date (stored in extra_data only)
        value_date = _parse_date_cell(cells[2])

        # Column 3: credit (inflow), column 4: debit (outflow, stored as positive)
        credit = _parse_amount(cells[3])
        debit  = _parse_amount(cells[4])
        amount = credit - debit  # positive = income/inflow, negative = expense/outflow

        # Column 5: description (Hebrew, correct encoding in XLS)
        description = _cell_str(cells[5])

        # Column 6: reference number
        reference = _cell_str(cells[6])

        # Column 7: op code (integer stored as float in XLS, e.g. 466.0)
        op_code = _cell_str(cells[7])

        # Column 1: balance (do not use for amount; store for audit)
        balance_raw = _safe_float(cells[1])
        balance: Optional[float] = balance_raw if balance_raw != 0.0 else None

        # Transaction type from op code map
        transaction_type = FIBI_OP_CODE_MAP.get(op_code, 'EXPENSE')

        # Asset matching: check if a known fund code appears in the description
        asset_id: Optional[str] = None
        asset_symbol: Optional[str] = None
        domain = 'securities' if transaction_type in ('BUY', 'SELL') else 'banking'

        for fund_code, info in FIBI_ASSET_MAP.items():
            if fund_code in description:
                asset_id = info['asset_id']
                asset_symbol = info['symbol']
                domain = info['domain']
                break

        # Stable dedup key
        reference_id = f"fibi_{tx_date.isoformat()}_{op_code}_{reference}_{amount:.2f}"

        raw_txns.append({
            'date': tx_date,
            'amount': amount,
            'description': description,
            'reference_id': reference_id,
            'source': _FIBI_SOURCE,
            'account_id': _FIBI_ACCOUNT_ID,
            'asset_id': asset_id,
            'asset_symbol': asset_symbol,
            'transaction_type': transaction_type,
            'domain': domain,
            'op_code': op_code,
            'extra_data': {
                'op_code': op_code,
                'reference': reference,
                'value_date': value_date.isoformat() if value_date else None,
                'balance': balance,
            },
        })

    raw_txns = _dedup_paired_interest(raw_txns)
    log.info("parse_fibi_xlsx: extracted %d transactions from %s", len(raw_txns), file_path)
    return raw_txns


def _parse_amount(val: Any) -> float:
    """Parse a credit/debit XLS cell to float, handling comma-formatted strings and spaces."""
    s = str(val).strip()
    if s in ('', 'nan', 'none'):
        return 0.0
    try:
        return float(s.replace(',', ''))
    except ValueError:
        return 0.0


def _cell_str(val: Any) -> str:
    """Convert an XLS cell to a clean string, stripping trailing .0 from floats."""
    if val is None:
        return ''
    try:
        import pandas as pd
        if pd.isna(val):
            return ''
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if s == 'nan':
        return ''
    # Excel stores integer op codes as floats (e.g. 466.0) — strip the .0
    if s.endswith('.0') and s[:-2].lstrip('-').isdigit():
        s = s[:-2]
    return s


def _parse_date_cell(val: Any) -> Optional[date_type]:
    """Parse an XLS cell value (datetime/date/Timestamp/string) to a Python date."""
    if val is None:
        return None
    try:
        import pandas as pd
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date_type):
        return val
    try:
        import pandas as pd
        return pd.Timestamp(val).date()
    except Exception:
        return None


def _safe_float(val: Any) -> float:
    """Convert a cell value to float, returning 0.0 on blank/NaN/error."""
    if val is None:
        return 0.0
    try:
        import pandas as pd
        if pd.isna(val):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _dedup_paired_interest(txns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove paired interest rows that cancel each other out.

    FIBI sometimes emits two rows on the same date with the same absolute amount:
      op=245  +amount  (credit leg — looks like income)
      op=295  -amount  (debit leg  — the real outflow)

    Keep only the op=295 row (the actual expense); drop the op=245 mirror.
    """
    pairs_245: Dict[tuple, List[int]] = {}  # (date, abs_amount) → row indices
    pairs_295: set = set()                  # (date, abs_amount) keys for op=295 rows

    for i, tx in enumerate(txns):
        if tx['op_code'] == '245':
            key = (tx['date'], round(abs(tx['amount']), 2))
            pairs_245.setdefault(key, []).append(i)
        elif tx['op_code'] == '295':
            key = (tx['date'], round(abs(tx['amount']), 2))
            pairs_295.add(key)

    to_remove: set = set()
    for key, indices in pairs_245.items():
        if key in pairs_295:
            to_remove.update(indices)

    if to_remove:
        log.info("parse_fibi_xlsx: dedup removed %d op=245 paired interest row(s)", len(to_remove))

    return [tx for i, tx in enumerate(txns) if i not in to_remove]


# ── PDF parser (legacy fallback) ──────────────────────────────────────────────

def fix_rtl_text(text: str) -> str:
    """Fix RTL Hebrew display order using python-bidi when available."""
    try:
        from bidi.algorithm import get_display
        return get_display(text)
    except ImportError:
        return " ".join(reversed(text.strip().split()))


# Hebrew column name → normalized key mapping (used by PDF path)
_COL_MAP = {
    "תאריך": "date", "תאריך פעולה": "date",
    "תאריך ערך": "value_date",
    "תיאור": "description", "פרטים": "description", "תיאור פעולה": "description",
    "סכום": "amount", 'סכום בש"ח': "amount", "סכום הפעולה": "amount",
    "חובה": "debit", "זכות": "credit",
    "מטבע": "currency",
    "אסמכתא": "reference", "מספר אסמכתא": "reference",
    'סו"פ': "op_type", "קוד פעולה": "op_type", "קוד": "op_type",
    "יתרה": "balance",
}


def parse_fibi_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse a FIBI bank PDF statement.

    Strategy:
      1. pdfplumber extract_tables()
      2. pdfplumber extract_text()
      3. pypdf extract_text()
    """
    log.info("=== FIBI PARSER CALLED === bytes=%d", len(file_bytes))
    log.info("parse_fibi_pdf: parsing %d bytes", len(file_bytes))

    try:
        import pdfplumber
        rows = _parse_pdf_pdfplumber(file_bytes)
        if rows:
            log.info("parse_fibi_pdf: %d rows via pdfplumber tables", len(rows))
            return rows
        rows = _parse_pdf_pdfplumber_text(file_bytes)
        if rows:
            log.info("parse_fibi_pdf: %d rows via pdfplumber text", len(rows))
            return rows
        log.warning("parse_fibi_pdf: pdfplumber returned 0 rows, trying pypdf")
    except ImportError:
        log.debug("pdfplumber not installed, falling back to pypdf")
    except Exception as exc:
        log.warning("pdfplumber failed (%s), falling back to pypdf", exc)

    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(
            "No PDF library available. Install pdfplumber: pip install pdfplumber"
        )

    reader = PdfReader(io.BytesIO(file_bytes))
    log.info("FIBI pypdf fallback: %d page(s)", len(reader.pages))
    rows = []
    for page_num, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        log.info("  pypdf page %d: %d lines, first 5: %s",
                 page_num + 1, len(lines), lines[:5])
        page_rows = _parse_pdf_lines_fibi(lines, page_num)
        log.info("  pypdf page %d: extracted %d transaction(s)", page_num + 1, len(page_rows))
        rows.extend(page_rows)

    log.info("parse_fibi_pdf: %d rows via pypdf text (%d pages)", len(rows), len(reader.pages))
    return rows


# ── pdfplumber helpers ────────────────────────────────────────────────────────

def _parse_pdf_pdfplumber(file_bytes: bytes) -> List[Dict[str, Any]]:
    import pdfplumber
    rows: List[Dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        log.info("FIBI pdfplumber: %d page(s)", len(pdf.pages))
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables() or []
            log.info("  page %d: %d table(s) found", page_num + 1, len(tables))
            for t_idx, table in enumerate(tables):
                log.info("  table %d: %d row(s), first row: %s",
                         t_idx, len(table), table[0] if table else "empty")
                page_rows = _parse_pdfplumber_table(table, page_num)
                log.info("  table %d: extracted %d transaction(s)", t_idx, len(page_rows))
                rows.extend(page_rows)
    return rows


def _parse_pdf_pdfplumber_text(file_bytes: bytes) -> List[Dict[str, Any]]:
    import pdfplumber
    rows: List[Dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            log.info("  pdfplumber text page %d: %d lines, first 5: %s",
                     page_num + 1, len(lines), lines[:5])
            page_rows = _parse_pdf_lines_fibi(lines, page_num)
            log.info("  pdfplumber text page %d: extracted %d transaction(s)",
                     page_num + 1, len(page_rows))
            rows.extend(page_rows)
    return rows


def _parse_pdfplumber_table(table: list, page_num: int) -> List[Dict[str, Any]]:
    if not table:
        return []

    col_map: Dict[int, str] = {}
    header_idx: Optional[int] = None
    for i, row in enumerate(table):
        candidate: Dict[int, str] = {}
        for j, cell in enumerate(row or []):
            cell_str = str(cell).strip() if cell else ""
            mapped = _COL_MAP.get(cell_str) or _COL_MAP.get(cell_str[::-1])
            if mapped:
                candidate[j] = mapped
        log.debug("  row %d candidate col_map: %s", i, candidate)
        if len(candidate) >= 2:
            col_map = candidate
            header_idx = i
            log.info("  header row found at index %d: col_map=%s", i, col_map)
            break

    if header_idx is None:
        log.warning(
            "  no header row found in table with %d rows. First row cells: %s",
            len(table),
            [str(c).strip() for c in (table[0] or [])] if table else [],
        )
        return []

    results: List[Dict[str, Any]] = []
    for row_idx, row in enumerate(table[header_idx + 1:]):
        if row_idx < 3:
            log.info("  RAW ROW[%d] (%d cells): %s",
                     row_idx, len(row or []),
                     [(i, repr(c)) for i, c in enumerate(row or [])])
        tx = _extract_table_row(row or [], col_map, page_num)
        if tx:
            results.append(tx)
    return results


def _extract_table_row(
    row: list,
    col_map: Dict[int, str],
    page_num: int,
) -> Optional[Dict[str, Any]]:
    fields: Dict[str, Any] = {}
    for j, key in col_map.items():
        if j < len(row) and row[j] is not None:
            val = str(row[j]).strip()
            if val and val not in ("nan", "None"):
                fields[key] = val

    log.info("  FIELDS: %s", fields)
    raw_date = _parse_date(fields.get("date"))
    if raw_date is None:
        return None

    raw_desc = str(fields.get("description", "")).strip()
    description = fix_rtl_text(raw_desc) if raw_desc else ""
    if not description:
        return None

    _SKIP_WORDS = ("יתרה", "ח-ן", "חשבון", "תנועות", "סה\"כ", "סיכום", "פרטים")
    if any(w in description for w in _SKIP_WORDS):
        return None

    credit = _parse_amount_val(fields.get("credit"))
    debit = _parse_amount_val(fields.get("debit"))

    if credit == 0.0 and debit == 0.0:
        combined = fields.get("amount")
        if not combined:
            return None
        amount = _parse_amount_val(combined)
    else:
        amount = credit - debit

    if amount == 0.0:
        return None

    reference = str(fields.get("reference", "")).strip() or None
    op_type_raw = str(fields.get("op_type", "")).strip()

    date_str = raw_date.strftime("%d/%m/%Y")
    ref_key = (
        f"FIBI-{date_str}-{reference}-{amount:.2f}"
        if reference
        else f"FIBI-{raw_date.date()}|{description}|{amount}"
    )
    external_ref_id = hashlib.sha256(ref_key.encode()).hexdigest()[:32]

    extra: Dict[str, Any] = {"page": page_num}
    if op_type_raw:
        try:
            extra["op_type"] = int(op_type_raw)
        except ValueError:
            pass

    return {
        "raw_date": raw_date,
        "description": description,
        "amount": amount,
        "currency": "ILS",
        "reference": reference,
        "external_ref_id": external_ref_id,
        "extra_raw": extra,
    }


# ── Line-based parser (pypdf / pdfplumber text fallback) ─────────────────────

_OP_TYPE_RE = re.compile(r"\b([45]\d{2})\b")
_BALANCE_RE = re.compile(r"\b\d{5,}[,\d]*\.\d{2}\b")


def _parse_pdf_lines_fibi(lines: List[str], page_num: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for i, line in enumerate(lines):
        date_match = _DATE_RE.search(line)
        if not date_match:
            continue

        try:
            raw_date = datetime(
                int(date_match.group(3)),
                int(date_match.group(2)),
                int(date_match.group(1)),
            )
        except ValueError:
            continue

        all_amounts = _AMOUNT_RE.findall(line)
        if not all_amounts:
            continue

        parsed_amounts = [_parse_amount_val(a) for a in all_amounts]
        balance_candidates = [a for a in parsed_amounts if a > 10000]
        non_balance = [a for a in parsed_amounts if a not in balance_candidates or a == 0]

        if not non_balance and parsed_amounts:
            non_balance = [min(parsed_amounts)]

        amount = non_balance[0] if non_balance else parsed_amounts[0]

        working = _DATE_RE.sub(" ", line)
        for a in all_amounts:
            working = working.replace(a, " ")
        op_match = _OP_TYPE_RE.search(working)
        op_type: Optional[int] = None
        if op_match:
            op_type = int(op_match.group(1))
            working = working[:op_match.start()] + working[op_match.end():]
        ref_match = re.search(r"\b(\d{5,12})\b", working)
        reference: Optional[str] = None
        if ref_match:
            reference = ref_match.group(1)
            working = working[:ref_match.start()] + working[ref_match.end():]
        description = fix_rtl_text(re.sub(r"\s+", " ", working).strip())

        if not description and i + 1 < len(lines):
            description = fix_rtl_text(lines[i + 1])
        if not description:
            description = "Unknown"

        if amount == 0:
            continue

        date_str = raw_date.strftime("%d/%m/%Y")
        ref_key = (
            f"FIBI-{date_str}-{reference}-{amount:.2f}"
            if reference
            else f"FIBI-{raw_date.date()}|{description}|{amount}"
        )
        external_ref_id = hashlib.sha256(ref_key.encode()).hexdigest()[:32]

        extra: Dict[str, Any] = {"page": page_num}
        if op_type:
            extra["op_type"] = op_type

        rows.append({
            "raw_date": raw_date,
            "description": description,
            "amount": amount,
            "currency": "ILS",
            "reference": reference,
            "external_ref_id": external_ref_id,
            "extra_raw": extra,
        })

    return rows


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        if isinstance(val, date_type):
            return datetime(val.year, val.month, val.day)
    except Exception:
        pass
    s = str(val).strip()
    m = _DATE_RE.match(s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _parse_amount_val(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0
