"""
First International Bank of Israel (FIBI) connector.

Fetches bank transactions from FIBI and writes them to raw_transactions.
The BankProcessor handles classification into domain transactions.

FIBI transactions include op_type codes (e.g. 466=BUY, 416=SELL, etc.)
stored in extra_raw for the processor to use.
"""
import logging
from typing import Any, Dict, List

from app.connectors.base import BaseConnector
from app.connectors.registry import register

log = logging.getLogger(__name__)


@register
class FibiBankConnector(BaseConnector):
    CONNECTOR_TYPE = "fibi_bank"
    DISPLAY_NAME = "First International Bank of Israel (FIBI)"
    DESCRIPTION = "Fetches bank transactions from FIBI"
    WRITES_RAW = True
    RAW_SOURCE = "fibi_bank"

    CONFIG_FIELDS = [
        {"name": "username", "label": "Username", "type": "text", "required": True},
        {"name": "password", "label": "Password", "type": "password", "required": True},
        {"name": "account_number", "label": "Account Number", "type": "text", "required": False},
    ]

    async def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetch raw bank transactions from FIBI.
        Returns list of dicts with keys:
          raw_date, description, amount, currency, reference,
          external_ref_id, extra_raw (should include op_type if available)

        Example extra_raw: {"op_type": 466, "branch": "123", "account": "456"}
        """
        # TODO: implement actual FIBI bank API / scraping integration
        log.info("FibiBankConnector.fetch() — not yet implemented, returning empty")
        return []
