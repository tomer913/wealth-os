"""
Isracard XLSX — manual monthly upload connector.

Replaces the broken isracard scraper (Isracard added SMS 2FA).
Users upload the monthly XLSX export from the Isracard website.
The upload endpoint handles parsing, raw_transaction insertion, and
immediately triggers BudgetProcessor for classification.
"""
import logging

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register

log = logging.getLogger(__name__)


@register
class IsracardXlsxConnector(BaseConnector):
    CONNECTOR_TYPE = "isracard_xlsx"
    DISPLAY_NAME = "ישראכרט - העלאת קובץ"
    DESCRIPTION = "העלה קובץ Excel חודשי מאתר ישראכרט. מחליף את הסקרייפר האוטומטי שנשבר."
    CONFIG_FIELDS = [
        {
            "key": "card_last4",
            "label": "4 ספרות אחרונות של הכרטיס",
            "type": "text",
            "default": "",
            "hint": "e.g. 5177 — used in dedup key to distinguish multiple cards",
        },
    ]

    async def run(self) -> ConnectorResult:
        log.info("IsracardXlsxConnector: manual-upload-only connector, no automated sync")
        return ConnectorResult()
