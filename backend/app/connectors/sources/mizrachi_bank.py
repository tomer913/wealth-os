"""
Mizrachi Bank connector.

Fetches bank transactions from Bank Mizrachi-Tefahot and writes them
to raw_transactions. The BankProcessor handles classification into
domain transactions.

fetch() must be implemented with the actual bank API/scraping logic.
"""
import logging
from typing import Any, Dict, List

from app.connectors.base import BaseConnector
from app.connectors.registry import register

log = logging.getLogger(__name__)


@register
class MizrachiBankConnector(BaseConnector):
    CONNECTOR_TYPE = "mizrachi_bank"
    DISPLAY_NAME = "Mizrachi Tefahot Bank"
    DESCRIPTION = "Fetches bank transactions from Bank Mizrachi-Tefahot"
    WRITES_RAW = True
    RAW_SOURCE = "mizrachi_bank"

    CONFIG_FIELDS = [
        {"name": "username", "label": "Username", "type": "text", "required": True},
        {"name": "password", "label": "Password", "type": "password", "required": True},
        {"name": "account_number", "label": "Account Number", "type": "text", "required": False},
    ]

    async def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetch raw bank transactions from Mizrachi.
        Returns list of dicts with keys:
          raw_date, description, amount, currency, reference,
          external_ref_id, extra_raw
        """
        # TODO: implement actual Mizrachi bank API / scraping integration
        log.info("MizrachiBankConnector.fetch() — not yet implemented, returning empty")
        return []
