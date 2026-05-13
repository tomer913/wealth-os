"""
BTB (Be The Bank) — manual PDF upload connector.

This connector has no automated sync (no run()). Users upload the monthly
PDF report through the Connectors UI. The upload endpoint in
app/routers/connectors.py handles parsing and DB writes.

Registration here makes btb_pdf appear in the connector-types list so users
can create the connector via the UI.
"""
import logging

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register

log = logging.getLogger(__name__)


@register
class BTBPdfConnector(BaseConnector):
    CONNECTOR_TYPE = "btb_pdf"
    DISPLAY_NAME = "BTB - Be The Bank"
    DESCRIPTION = "Upload monthly PDF portfolio reports from Be The Bank (btbisrael.co.il). No credentials required — reports are uploaded manually."
    CONFIG_FIELDS = []  # no credentials needed — manual upload only

    async def run(self) -> ConnectorResult:
        log.info("BTBPdfConnector: manual-upload-only connector, no automated sync")
        return ConnectorResult()
