import pytest
from datetime import date
from app.connectors.parsers.btb import _parse_report_date, _extract_amount, _extract_pct, _parse_btb_text

# Real text as extracted by pdfplumber from the April 2026 BTB PDF.
# RTL Hebrew — words are reversed, values appear BEFORE their labels.
SAMPLE_TEXT = """2026 לירפא שדוחל ישיא ישדוח ח"וד
₪408,207.85 תיחכונ הרתי
8.49% תועקשהה קיתב תעצוממ תיביר
0.53% )סמ ירחא וטנ( םדוקה שדוחב תיבירמ חוור
₪242.60 םיישדוח לוהינ ימד
₪412.33 תואוולהל הנימז הרתי
₪0.00 הכישמל הנימז הרתי
13.72% םויה דע )וטנ( תיביטקפא תיביר
₪530,000.00 תודקפה
₪150,000.00 ןובשחהמ ךשמנ
₪39,152.55 םויה דע וטורב תיביר
₪4,980.19 זזוקש סמ"""


def test_parse_report_date_april_2026():
    assert _parse_report_date(SAMPLE_TEXT) == date(2026, 4, 30)


def test_parse_report_date_january():
    # ראוני = ינואר reversed; שדוחל = לחודש reversed
    text = '2026 ראוני שדוחל ישיא ישדוח ח"וד'
    assert _parse_report_date(text) == date(2026, 1, 31)


def test_parse_report_date_missing_returns_none():
    assert _parse_report_date("some random text") is None


def test_extract_current_value():
    assert _extract_amount(SAMPLE_TEXT, "תיחכונ הרתי") == 408207.85


def test_extract_deposits():
    assert _extract_amount(SAMPLE_TEXT, "תודקפה") == 530000.00


def test_extract_withdrawn():
    assert _extract_amount(SAMPLE_TEXT, "ןובשחהמ ךשמנ") == 150000.00


def test_extract_gross_interest():
    assert _extract_amount(SAMPLE_TEXT, "םויה דע וטורב תיביר") == 39152.55


def test_extract_tax():
    assert _extract_amount(SAMPLE_TEXT, "זזוקש סמ") == 4980.19


def test_extract_net_return_pct():
    assert _extract_pct(SAMPLE_TEXT, "םויה דע )וטנ( תיביטקפא תיביר") == 13.72


def test_extract_avg_rate():
    assert _extract_pct(SAMPLE_TEXT, "תועקשהה קיתב תעצוממ תיביר") == 8.49


def test_extract_last_month_return():
    assert _extract_pct(SAMPLE_TEXT, ")סמ ירחא וטנ( םדוקה שדוחב תיבירמ חוור") == 0.53


def test_extract_mgmt_fee():
    assert _extract_amount(SAMPLE_TEXT, "םיישדוח לוהינ ימד") == 242.60


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
