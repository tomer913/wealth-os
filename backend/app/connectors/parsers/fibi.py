"""
First International Bank of Israel (FIBI) — XLSX and PDF statement parsers.

XLSX layout (typical export from FIBI online banking):
  Row 1-N: headers in Hebrew
  Expected columns (order may vary):
    תאריך          → date
    תיאור / פרטים  → description
    סכום           → amount (negative = debit, positive = credit)
    מטבע           → currency
    אסמכתא        → reference
    קוד פעולה      → op_type (e.g. 466=BUY, 416=SELL)

PDF layout: same fields extracted via text parsing (fallback).

Returns list of dicts compatible with BaseConnector raw row format:
  raw_date, description, amount, currency, reference, external_ref_id, extra_raw
"""
import hashlib
import io
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_DATE_RE = re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})")
_AMOUNT_RE = re.compile(r"-?[\d,]+\.\d{2}")

# Hebrew column name → normalized key mapping
_COL_MAP = {
    # Transaction date — preferred
    "תאריך": "date", "תאריך פעולה": "date",
    # Value date — separate key so it doesn't overwrite transaction date
    "תאריך ערך": "value_date",
    # Description
    "תיאור": "description", "פרטים": "description", "תיאור פעולה": "description",
    # Amount variants
    "סכום": "amount", 'סכום בש"ח': "amount", "סכום הפעולה": "amount",
    "חובה": "debit", "זכות": "credit",
    # Currency
    "מטבע": "currency",
    # Reference
    "אסמכתא": "reference", "מספר אסמכתא": "reference",
    # Op / transaction code (FIBI uses 'סו"פ', others use 'קוד פעולה')
    'סו"פ': "op_type", "קוד פעולה": "op_type", "קוד": "op_type",
    # Balance (ignored)
    "יתרה": "balance",
}


def parse_fibi_xlsx(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse a FIBI bank XLSX statement and return raw transaction rows.
    """
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl is required: pip install openpyxl")

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active

    rows_iter = list(ws.iter_rows(values_only=True))
    if not rows_iter:
        return []

    # Find header row: first row that contains a recognized Hebrew column name
    header_row_idx = None
    col_map: Dict[int, str] = {}

    for idx, row in enumerate(rows_iter):
        matched = 0
        candidate_map: Dict[int, str] = {}
        for col_idx, cell in enumerate(row):
            cell_str = str(cell).strip() if cell is not None else ""
            if cell_str in _COL_MAP:
                candidate_map[col_idx] = _COL_MAP[cell_str]
                matched += 1
        if matched >= 2:
            header_row_idx = idx
            col_map = candidate_map
            break

    if header_row_idx is None:
        log.warning("parse_fibi_xlsx: could not find header row — attempting positional parse")
        return _parse_xlsx_positional(rows_iter)

    results = []
    for row in rows_iter[header_row_idx + 1:]:
        tx = _extract_xlsx_row(row, col_map)
        if tx:
            results.append(tx)

    log.info("parse_fibi_xlsx: extracted %d rows", len(results))
    return results


def _extract_xlsx_row(row: tuple, col_map: Dict[int, str]) -> Optional[Dict[str, Any]]:
    """Extract one transaction from an XLSX row using the column map."""
    fields: Dict[str, Any] = {}
    for col_idx, field_name in col_map.items():
        if col_idx < len(row):
            fields[field_name] = row[col_idx]

    # Date
    raw_date = _parse_date(fields.get("date"))
    if raw_date is None:
        return None

    description = str(fields.get("description", "")).strip() or "Unknown"

    # Amount: prefer "amount" column; fall back to debit/credit
    amount_raw = fields.get("amount")
    if amount_raw is not None:
        amount = _parse_amount_val(amount_raw)
    else:
        debit = _parse_amount_val(fields.get("debit", 0))
        credit = _parse_amount_val(fields.get("credit", 0))
        amount = credit - debit

    if amount == 0 and fields.get("amount") is None and fields.get("debit") is None:
        return None

    currency = str(fields.get("currency", "ILS")).strip() or "ILS"
    reference = str(fields.get("reference", "")).strip() or None
    op_type = fields.get("op_type")

    ref_src = f"{raw_date.date()}|{description}|{amount}"
    external_ref_id = hashlib.sha256(ref_src.encode()).hexdigest()[:32]

    extra: Dict[str, Any] = {}
    if op_type is not None:
        try:
            extra["op_type"] = int(op_type)
        except (ValueError, TypeError):
            extra["op_type"] = op_type

    return {
        "raw_date": raw_date,
        "description": description,
        "amount": amount,
        "currency": currency,
        "reference": reference,
        "external_ref_id": external_ref_id,
        "extra_raw": extra or None,
    }


def _parse_xlsx_positional(rows: list) -> List[Dict[str, Any]]:
    """
    Fallback: assume columns are [date, description, amount, currency] by position.
    Used when no Hebrew headers are detected (e.g. English export).
    """
    results = []
    for row in rows:
        if len(row) < 3:
            continue
        raw_date = _parse_date(row[0])
        if raw_date is None:
            continue
        description = str(row[1]).strip() if row[1] else "Unknown"
        amount = _parse_amount_val(row[2])
        currency = str(row[3]).strip() if len(row) > 3 and row[3] else "ILS"

        ref_src = f"{raw_date.date()}|{description}|{amount}"
        external_ref_id = hashlib.sha256(ref_src.encode()).hexdigest()[:32]

        results.append({
            "raw_date": raw_date,
            "description": description,
            "amount": amount,
            "currency": currency,
            "reference": None,
            "external_ref_id": external_ref_id,
            "extra_raw": None,
        })
    return results


def parse_fibi_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse a FIBI bank PDF statement.

    FIBI PDF columns (Hebrew RTL layout):
      תאריך | תיאור | זכות | חובה | יתרה | אסמכתא | סו"פ | תאריך ערך

    Strategy:
      1. pdfplumber extract_tables()  — best for structured tables
      2. pdfplumber extract_text()    — line parser as fallback
      3. pypdf extract_text()         — last resort
    """
    log.info("=== FIBI PARSER CALLED === bytes=%d", len(file_bytes))
    log.info("parse_fibi_pdf: parsing %d bytes", len(file_bytes))

    # ── Primary: pdfplumber table extraction ─────────────────────────────────
    try:
        import pdfplumber
        rows = _parse_pdf_pdfplumber(file_bytes)
        if rows:
            log.info("parse_fibi_pdf: %d rows via pdfplumber tables", len(rows))
            return rows
        # Tables empty — try pdfplumber text
        rows = _parse_pdf_pdfplumber_text(file_bytes)
        if rows:
            log.info("parse_fibi_pdf: %d rows via pdfplumber text", len(rows))
            return rows
        log.warning("parse_fibi_pdf: pdfplumber returned 0 rows, trying pypdf")
    except ImportError:
        log.debug("pdfplumber not installed, falling back to pypdf")
    except Exception as exc:
        log.warning("pdfplumber failed (%s), falling back to pypdf", exc)

    # ── Fallback: pypdf text extraction ───────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# pdfplumber helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_pdf_pdfplumber(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Extract tables with pdfplumber and parse each using column name detection."""
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
    """Extract plain text with pdfplumber, then parse line by line."""
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
    """
    Parse one pdfplumber table.  Finds the header row by matching Hebrew
    column names in _COL_MAP, then processes every data row.
    """
    if not table:
        return []

    # Detect header row (need at least 2 recognised column names)
    col_map: Dict[int, str] = {}
    header_idx: Optional[int] = None
    for i, row in enumerate(table):
        candidate: Dict[int, str] = {}
        for j, cell in enumerate(row or []):
            cell_str = str(cell).strip() if cell else ""
            # pdfplumber may return RTL Hebrew in reversed visual order
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
        # Log what we DID find so the caller can diagnose column name mismatches
        log.warning(
            "  no header row found in table with %d rows. "
            "First row cells: %s",
            len(table),
            [str(c).strip() for c in (table[0] or [])] if table else [],
        )
        return []

    results: List[Dict[str, Any]] = []
    for row in table[header_idx + 1:]:
        tx = _extract_table_row(row or [], col_map, page_num)
        if tx:
            results.append(tx)
    return results


def _extract_table_row(
    row: list,
    col_map: Dict[int, str],
    page_num: int,
) -> Optional[Dict[str, Any]]:
    """Build one raw transaction dict from a pdfplumber table row."""
    fields: Dict[str, Any] = {}
    for j, key in col_map.items():
        if j < len(row) and row[j] is not None:
            val = str(row[j]).strip()
            if val and val not in ("nan", "None"):
                fields[key] = val

    raw_date = _parse_date(fields.get("date"))
    if raw_date is None:
        return None

    # RTL Hebrew arrives in reversed visual order from pdfplumber — un-reverse it
    raw_desc = str(fields.get("description", "")).strip()
    description = raw_desc[::-1] if raw_desc else ""
    if not description:
        return None

    # Skip header/summary rows that contain balance keywords
    _SKIP_WORDS = ("יתרה", "ח-ן", "חשבון", "תנועות", "סה\"כ", "סיכום", "פרטים")
    if any(w in description for w in _SKIP_WORDS):
        return None

    credit = _parse_amount_val(fields.get("credit"))
    debit  = _parse_amount_val(fields.get("debit"))

    if credit == 0.0 and debit == 0.0:
        combined = fields.get("amount")
        if not combined:
            return None
        amount = _parse_amount_val(combined)
    else:
        amount = credit - debit  # credit > 0 → income; debit > 0 → expense

    if amount == 0.0:
        return None

    reference = str(fields.get("reference", "")).strip() or None
    op_type_raw = str(fields.get("op_type", "")).strip()

    # Dedup key uses reference when available (more stable than hash of description)
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


# ─────────────────────────────────────────────────────────────────────────────
# Line-based parser (pypdf / pdfplumber text fallback)
# ─────────────────────────────────────────────────────────────────────────────

# FIBI transaction code is a 3-digit number that starts with 4 or 5
_OP_TYPE_RE = re.compile(r"\b([45]\d{2})\b")
# Balance column values tend to be large integers (>= 5 digits); we skip those
_BALANCE_RE = re.compile(r"\b\d{5,}[,\d]*\.\d{2}\b")


def _parse_pdf_lines_fibi(lines: List[str], page_num: int) -> List[Dict[str, Any]]:
    """
    Line-by-line parser for FIBI text extraction.

    For each line that starts with a date, extracts:
      - description (text between the first and last dates on the line)
      - credit OR debit (the smallest non-balance amount)
      - reference (integer-looking token after amounts)
      - op_type (3-digit code starting with 4 or 5)
    """
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

        # Collect all decimal amounts
        all_amounts = _AMOUNT_RE.findall(line)
        if not all_amounts:
            continue

        # Remove the balance (typically the largest amount / last position)
        parsed_amounts = [_parse_amount_val(a) for a in all_amounts]
        balance_candidates = [a for a in parsed_amounts if a > 10000]
        non_balance = [a for a in parsed_amounts if a not in balance_candidates or a == 0]

        if not non_balance and parsed_amounts:
            # All amounts look like balances — take the smallest as the transaction
            non_balance = [min(parsed_amounts)]

        # The transaction amount: credit → positive, debit → negative
        # We can't always tell from text alone; use the first non-balance amount
        amount = non_balance[0] if non_balance else parsed_amounts[0]

        # Strip date, all amounts, and trailing noise from line to get description
        working = _DATE_RE.sub(" ", line)
        for a in all_amounts:
            working = working.replace(a, " ")
        # Remove op_type code and reference number
        op_match = _OP_TYPE_RE.search(working)
        op_type: Optional[int] = None
        if op_match:
            op_type = int(op_match.group(1))
            working = working[:op_match.start()] + working[op_match.end():]
        # What remains should be the description (and possibly a reference number)
        ref_match = re.search(r"\b(\d{5,12})\b", working)
        reference: Optional[str] = None
        if ref_match:
            reference = ref_match.group(1)
            working = working[:ref_match.start()] + working[ref_match.end():]
        # RTL Hebrew arrives reversed — un-reverse the remaining text portion
        description = re.sub(r"\s+", " ", working).strip()[::-1]

        if not description and i + 1 < len(lines):
            description = lines[i + 1][::-1]
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_date(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    # openpyxl may return date objects
    try:
        from datetime import date as date_type
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
