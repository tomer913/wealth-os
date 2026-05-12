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
