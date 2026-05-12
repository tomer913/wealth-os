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
