"""
Be The Bank (BTB Israel) — monthly PDF portfolio report parser.

pdfplumber extracts RTL Hebrew text in reversed word order. Both Hebrew words
and multi-word field labels appear with characters in reverse order.
Values (₪ amounts, percentages) appear BEFORE their label on each line.

Example extracted line:
    ₪408,207.85 תיחכונ הרתי
    ← value    ← reversed label ("יתרה נוכחית" reversed)

Title line example:
    2026 לירפא שדוחל ישיא ישדוח ח"וד
    ← year ← reversed month ← reversed "לחודש"

Returns a single dict — the PDF is a snapshot, not a list of transactions.
"""
import calendar
import io
import logging
import re
from datetime import date as date_type
from typing import Optional

log = logging.getLogger(__name__)

# Hebrew month names as pdfplumber extracts them (each word reversed by RTL rendering)
_HEBREW_MONTHS = {
    'ראוני':   1,   # ינואר
    'יראורפ':  2,   # פברואר
    'ץרמ':     3,   # מרץ
    'לירפא':   4,   # אפריל
    'יאמ':     5,   # מאי
    'ינוי':    6,   # יוני
    'ילוי':    7,   # יולי
    'טסוגוא':  8,   # אוגוסט
    'רבמטפס':  9,   # ספטמבר
    'רבוטקוא': 10,  # אוקטובר
    'רבמבונ':  11,  # נובמבר
    'רבמצד':   12,  # דצמבר
}

# Title: "2026 לירפא שדוחל ישיא ישדוח ח"וד"
# Pattern: year, reversed-month, שדוחל (= לחודש reversed)
_TITLE_RE = re.compile(
    r'(\d{4})\s+(' + '|'.join(_HEBREW_MONTHS) + r')\s+שדוחל'
)


def _parse_report_date(text: str) -> Optional[date_type]:
    """Return last calendar day of the month/year found in the report title."""
    m = _TITLE_RE.search(text)
    if not m:
        return None
    year = int(m.group(1))
    month = _HEBREW_MONTHS[m.group(2)]
    last_day = calendar.monthrange(year, month)[1]
    return date_type(year, month, last_day)


def _extract_amount(text: str, reversed_label: str) -> float:
    """
    Find a ₪ amount that appears directly before reversed_label on the same line.
    Format in extracted text: '₪408,207.85 תיחכונ הרתי'
    """
    pattern = rf"₪([\d,]+\.?\d*)\s+{re.escape(reversed_label)}"
    m = re.search(pattern, text)
    if m:
        return float(m.group(1).replace(',', ''))
    return 0.0


def _extract_pct(text: str, reversed_label: str) -> float:
    """
    Find a percentage that appears directly before reversed_label on the same line.
    Format in extracted text: '13.72% םויה דע )וטנ( תיביטקפא תיביר'
    """
    pattern = rf"([\d.]+)%\s+{re.escape(reversed_label)}"
    m = re.search(pattern, text)
    if m:
        return float(m.group(1))
    return 0.0


def _parse_btb_text(text: str) -> dict:
    """
    Parse all fields from pdfplumber-extracted text (RTL-reversed).

    Raises ValueError if the report month/year cannot be found.
    """
    report_date = _parse_report_date(text)
    if report_date is None:
        raise ValueError("Could not find report month/year in PDF text")

    total_deposits = _extract_amount(text, "תודקפה")
    total_withdrawn = _extract_amount(text, "ןובשחהמ ךשמנ")

    return {
        'report_date': report_date,
        'current_value':        _extract_amount(text, "תיחכונ הרתי"),
        'total_deposits':       total_deposits,
        'total_withdrawn':      total_withdrawn,
        'gross_interest':       _extract_amount(text, "םויה דע וטורב תיביר"),
        'tax_withheld':         _extract_amount(text, "זזוקש סמ"),
        'net_return_pct':       _extract_pct(text, "םויה דע )וטנ( תיביטקפא תיביר"),
        'avg_interest_rate':    _extract_pct(text, "תועקשהה קיתב תעצוממ תיביר"),
        'last_month_return_pct':_extract_pct(text, ")סמ ירחא וטנ( םדוקה שדוחב תיבירמ חוור"),
        'mgmt_fee':             _extract_amount(text, "םיישדוח לוהינ ימד"),
        'net_invested':         round(total_deposits - total_withdrawn, 4),
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
