"""
Isracard — monthly XLSX statement parser.

File exported from Isracard online banking (פירוט עסקאות).

Sheet layout (0-indexed rows):
  Rows 0-N:   metadata headers — number varies by month (extra EUR summary row
              pushes everything down one row in some statements)
  Row  N+1:   column headers row — identified by 'תאריך רכישה' in column 0
  Rows N+2+:  transaction data (stop at first non-date row)

Columns (0-indexed):
  0  תאריך רכישה   Purchase date (DD.MM.YY)
  1  שם בית עסק    Merchant name
  2  סכום עסקה     Original transaction amount
  3  מטבע עסקה     Original currency (₪ / $)
  4  סכום חיוב     Charge amount  ← USE THIS as amount
  5  מטבע חיוב     Charge currency (₪ / $)
  6  מס' שובר      Voucher / reference number
  7  פירוט נוסף    Details (installment info, הוראת קבע, אתר חו"ל)

Amount sign convention:
  positive → expense (credit card charge)
  negative → refund / credit

External ref ID format: f"isracard_{YYYY-MM-DD}_{voucher}"
"""
import io
import logging
import re
from datetime import datetime
from typing import Any, Dict, List

log = logging.getLogger(__name__)

_INSTALL_RE  = re.compile(r'תשלום\s+(\d+)\s+מתוך\s+(\d+)')
_DATE_RE     = re.compile(r'^\d{2}\.\d{2}\.\d{2}$')

_CURRENCY_MAP = {
    '₪':   'ILS',
    'ILS': 'ILS',
    '$':   'USD',
    'USD': 'USD',
    'EUR': 'EUR',
}


def parse_isracard_xlsx(file_bytes: bytes, card_last4: str = '') -> List[Dict[str, Any]]:
    """
    Parse an Isracard monthly XLSX statement.

    Args:
        file_bytes:  Raw .xlsx / .xls bytes.
        card_last4:  Optional card suffix for dedup key enrichment (e.g. '5177').

    Returns:
        List of raw-transaction dicts ready for insertion into raw_transactions
        via the upload endpoint:
          raw_date, description, amount, currency, reference, external_ref_id, extra_raw
    """
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("pandas is required: pip install pandas")

    try:
        df = pd.read_excel(
            io.BytesIO(file_bytes),
            sheet_name='פירוט עסקאות',
            header=None,
            engine='openpyxl',
        )
    except Exception as exc:
        raise ValueError(f"Cannot read Isracard XLSX: {exc}") from exc

    # Detect header row dynamically — find 'תאריך רכישה' in column 0.
    # The exact position shifts when the file contains an extra currency summary row.
    header_row = None
    for idx in range(len(df)):
        cell = str(df.iloc[idx, 0]).strip()
        if 'תאריך רכישה' in cell:
            header_row = idx
            break

    if header_row is None:
        raise ValueError(
            "Could not find header row with 'תאריך רכישה' in Isracard file. "
            "Check that the sheet name is 'פירוט עסקאות' and the file is a valid export."
        )

    data_start = header_row + 1
    print(f"=== ISRACARD header_row={header_row} data_start={data_start}", flush=True)

    rows: List[Dict[str, Any]] = []

    for i in range(data_start, len(df)):
        raw_date_val = df.iloc[i, 0]

        # Stop at first non-date row (totals / legal text)
        date_str = str(raw_date_val).strip() if raw_date_val is not None else ''
        if not _DATE_RE.match(date_str):
            log.debug("isracard parser: stopping at row %d (non-date: %r)", i, date_str)
            break

        try:
            tx_date = datetime.strptime(date_str, '%d.%m.%y').date()
        except ValueError:
            log.warning("isracard parser: unparseable date %r at row %d — skipping", date_str, i)
            continue

        merchant      = str(df.iloc[i, 1] or '').strip()
        orig_amount   = _to_float(df.iloc[i, 2])
        orig_currency = _map_currency(df.iloc[i, 3])
        charge_amount = _to_float(df.iloc[i, 4])
        charge_currency = _map_currency(df.iloc[i, 5])
        voucher       = str(df.iloc[i, 6] or '').strip().rstrip('.0')
        details       = str(df.iloc[i, 7] or '').strip()

        # Installment detection
        install_m = _INSTALL_RE.search(details)
        install_current = int(install_m.group(1)) if install_m else None
        install_total   = int(install_m.group(2)) if install_m else None

        is_standing_order = 'הוראת קבע' in details
        is_foreign_site   = 'אתר חו"ל' in details or "אתר חו'" in details

        extra_raw = {
            'voucher':               voucher,
            'transaction_amount':    orig_amount,
            'transaction_currency':  orig_currency,
            'is_standing_order':     is_standing_order,
            'is_foreign_site':       is_foreign_site,
            'installment_current':   install_current,
            'installment_total':     install_total,
        }
        if card_last4:
            extra_raw['card_last4'] = card_last4

        ref_suffix = f"{card_last4}_{voucher}" if card_last4 else voucher
        external_ref_id = f"isracard_{tx_date.isoformat()}_{ref_suffix}"

        rows.append({
            'raw_date':        datetime(tx_date.year, tx_date.month, tx_date.day),
            'description':     merchant,
            'amount':          charge_amount,    # positive = expense, negative = refund
            'currency':        charge_currency,
            'reference':       voucher or None,
            'external_ref_id': external_ref_id,
            'extra_raw':       extra_raw,
        })

    log.info("parse_isracard_xlsx: extracted %d transactions", len(rows))
    return rows


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        import pandas as pd
        if pd.isna(val):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(str(val).replace(',', '').strip())
    except (ValueError, TypeError):
        return 0.0


def _map_currency(val: Any) -> str:
    s = str(val or '').strip()
    return _CURRENCY_MAP.get(s, 'ILS')
