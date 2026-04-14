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
    # Date
    "תאריך": "date", "תאריך ערך": "date", "תאריך פעולה": "date",
    # Description
    "תיאור": "description", "פרטים": "description", "תיאור פעולה": "description",
    # Amount
    "סכום": "amount", "סכום בש\"ח": "amount", "סכום הפעולה": "amount",
    "חובה": "debit", "זכות": "credit",
    # Currency
    "מטבע": "currency",
    # Reference
    "אסמכתא": "reference", "מספר אסמכתא": "reference",
    # Op type (FIBI-specific)
    "קוד פעולה": "op_type", "קוד": "op_type",
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
    Parse a FIBI bank PDF statement. Delegates to the same heuristic
    line parser used by the Mizrachi PDF parser, with FIBI-specific
    column indicator keywords.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is required: pip install pypdf")

    reader = PdfReader(io.BytesIO(file_bytes))
    rows: List[Dict[str, Any]] = []

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        rows.extend(_parse_pdf_lines(lines, page_num))

    log.info("parse_fibi_pdf: extracted %d rows from %d pages", len(rows), len(reader.pages))
    return rows


def _parse_pdf_lines(lines: List[str], page_num: int) -> List[Dict[str, Any]]:
    rows = []
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

        amounts = _AMOUNT_RE.findall(line)
        desc_candidate = _DATE_RE.sub("", line)
        for a in amounts:
            desc_candidate = desc_candidate.replace(a, "")
        desc_candidate = re.sub(r"[|,\-\s]+$", "", desc_candidate).strip()

        if not desc_candidate and i + 1 < len(lines):
            desc_candidate = lines[i + 1]

        description = desc_candidate or "Unknown"

        if amounts:
            # First signed amount wins; FIBI PDFs often include sign
            amount = _parse_amount_val(amounts[0])
        else:
            continue

        if amount == 0:
            continue

        # Try to detect op_type from line
        op_match = re.search(r"\b(4\d{2})\b", line)
        extra: Dict[str, Any] = {"page": page_num}
        if op_match:
            extra["op_type"] = int(op_match.group(1))

        ref_src = f"{raw_date.date()}|{description}|{amount}"
        external_ref_id = hashlib.sha256(ref_src.encode()).hexdigest()[:32]

        rows.append({
            "raw_date": raw_date,
            "description": description,
            "amount": amount,
            "currency": "ILS",
            "reference": None,
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
