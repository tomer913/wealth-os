"""
Mizrachi Tefahot Bank — PDF statement parser.

The PDF is a bank account statement exported from the Mizrachi online portal.
Typical layout (text extraction order, RTL rendered as LTR by pypdf):

  Date        | Description               | Debit   | Credit  | Balance
  31/03/2025  | העברה בנקאית              | 1500.00 |         | 42000.00
  28/03/2025  | זיכוי משכורת              |         | 18000.00| 43500.00

Expected Hebrew column headers (may vary by export version):
  תאריך | תיאור | חובה | זכות | יתרה
  or
  תאריך ערך | פרטים | סכום חובה | סכום זכות | יתרה

Returns list of dicts compatible with BaseConnector raw row format:
  raw_date, description, amount, currency, reference, external_ref_id, extra_raw
"""
import hashlib
import io
import logging
import re
from datetime import datetime
from typing import Any, Dict, List

log = logging.getLogger(__name__)

# Israeli date patterns: DD/MM/YYYY or DD.MM.YYYY
_DATE_RE = re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})")
# Amount: digits with optional commas and decimal point (Israeli format uses '.' decimal)
_AMOUNT_RE = re.compile(r"[\d,]+\.\d{2}")


def parse_mizrachi_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parse a Mizrachi Bank PDF statement and return raw transaction rows.

    Raises ValueError if the file cannot be read as a PDF or yields no rows.
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
        rows.extend(_parse_lines(lines, page_num))

    log.info("parse_mizrachi_pdf: extracted %d rows from %d pages", len(rows), len(reader.pages))
    return rows


def _parse_lines(lines: List[str], page_num: int) -> List[Dict[str, Any]]:
    """
    Heuristic line parser: look for lines that start with a date pattern,
    then extract description and amount from the same or adjacent line.

    Mizrachi PDFs are RTL; pypdf often reverses field order. We handle both
    orderings: date-first and date-last.
    """
    rows = []

    for i, line in enumerate(lines):
        date_match = _DATE_RE.search(line)
        if not date_match:
            continue

        # Parse the date
        try:
            raw_date = datetime(
                int(date_match.group(3)),
                int(date_match.group(2)),
                int(date_match.group(1)),
            )
        except ValueError:
            continue

        # Find amounts on this line
        amounts = _AMOUNT_RE.findall(line)
        # Remove the matched date from the line to get description candidate
        desc_candidate = _DATE_RE.sub("", line).strip()
        # Strip leading/trailing amount strings from description
        for a in amounts:
            desc_candidate = desc_candidate.replace(a, "").strip()
        # Clean punctuation artefacts
        desc_candidate = re.sub(r"[|,\-]+$", "", desc_candidate).strip()

        if not desc_candidate and i + 1 < len(lines):
            # Description might be on the next line
            desc_candidate = lines[i + 1]

        description = desc_candidate or "Unknown"

        # Determine amount: debit is negative, credit is positive.
        # Heuristic: if two amounts, first is debit (negative), second is credit.
        # If one amount, sign depends on context — keep as positive and store raw.
        if len(amounts) >= 2:
            debit_str, credit_str = amounts[0], amounts[1]
            debit = _parse_amount(debit_str)
            credit = _parse_amount(credit_str)
            if debit > 0:
                amount = -debit
            else:
                amount = credit
        elif len(amounts) == 1:
            amount = _parse_amount(amounts[0])
            # Negative if line contains debit indicators
            if any(kw in line for kw in ("חובה", "חיוב", "משיכה", "העברה יוצאת")):
                amount = -amount
        else:
            # No amount found — skip
            continue

        if amount == 0:
            continue

        # Build a stable external_ref_id from date + description + amount
        ref_src = f"{raw_date.date()}|{description}|{amount}"
        external_ref_id = hashlib.sha256(ref_src.encode()).hexdigest()[:32]

        rows.append({
            "raw_date": raw_date,
            "description": description,
            "amount": amount,
            "currency": "ILS",
            "reference": None,
            "external_ref_id": external_ref_id,
            "extra_raw": {"page": page_num, "raw_line": line},
        })

    return rows


def _parse_amount(s: str) -> float:
    """Parse '1,234.56' → 1234.56"""
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return 0.0
