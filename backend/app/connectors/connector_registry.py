"""
Connector Type Registry — single source of truth for connector type metadata.
See CONNECTORS.md for full documentation and adding-new-connector instructions.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConnectorTypeDef:
    type: str
    display_name: str
    description: str
    category: str                             # 'automatic' | 'manual_upload' | 'scraper'
    flow_type: str                            # 'investment' | 'budget' | 'both'
    supports_multi_asset: bool
    requires_asset_selection_on_upload: bool  # user picks asset in upload modal
    supported_file_types: list
    asset_linking: str                        # 'auto_by_description' | 'user_selected' | 'account_linked' | 'none'
    supports_auto_scrape: bool                # has credential-based auto sync (scheduler can run it)
    supports_manual_upload: bool              # supports file upload via upload endpoint
    schedule_default: str = "daily"


CONNECTOR_REGISTRY: dict = {
    # ── Automatic connectors ─────────────────────────────────────────────────
    "ib_flex": ConnectorTypeDef(
        type="ib_flex",
        display_name="Interactive Brokers",
        description="Fetches trades and positions via IB Flex Query API. No gateway required.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="auto_by_description",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "kraken": ConnectorTypeDef(
        type="kraken",
        display_name="Kraken Exchange",
        description="Fetches crypto trades via Kraken REST API.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="auto_by_description",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "cexio": ConnectorTypeDef(
        type="cexio",
        display_name="CEX.IO Exchange",
        description="Fetches crypto trades via CEX.IO API.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="auto_by_description",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "ecb_fx": ConnectorTypeDef(
        type="ecb_fx",
        display_name="ECB FX Rates",
        description="Fetches daily FX rates from European Central Bank.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="none",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "yahoo_prices": ConnectorTypeDef(
        type="yahoo_prices",
        display_name="Yahoo Finance Prices",
        description="Fetches daily asset prices from Yahoo Finance.",
        category="automatic",
        flow_type="investment",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="none",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    # ── Scraper connectors ───────────────────────────────────────────────────
    "isracard": ConnectorTypeDef(
        type="isracard",
        display_name="Isracard",
        description="Scrapes Isracard credit card transactions via GitHub Actions. ⚠️ Broken — SMS 2FA added. Use isracard_xlsx.",
        category="scraper",
        flow_type="budget",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="account_linked",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    "cal_scraper": ConnectorTypeDef(
        type="cal_scraper",
        display_name="CAL Card",
        description="Scrapes CAL credit card transactions via GitHub Actions.",
        category="scraper",
        flow_type="budget",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=False,
        supported_file_types=[],
        asset_linking="account_linked",
        supports_auto_scrape=True,
        supports_manual_upload=False,
    ),
    # ── Manual upload connectors ─────────────────────────────────────────────
    "fibi_bank": ConnectorTypeDef(
        type="fibi_bank",
        display_name="הבינלאומי FIBI",
        description="העלה קובץ XLS או PDF מהבנק הבינלאומי.",
        category="manual_upload",
        flow_type="both",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=["pdf", "xls", "xlsx"],
        asset_linking="auto_by_description",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
    "mizrachi_bank": ConnectorTypeDef(
        type="mizrachi_bank",
        display_name="מזרחי טפחות",
        description="העלה קובץ PDF ממזרחי טפחות.",
        category="manual_upload",
        flow_type="both",
        supports_multi_asset=True,
        requires_asset_selection_on_upload=False,
        supported_file_types=["pdf"],
        asset_linking="auto_by_description",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
    "btb_pdf": ConnectorTypeDef(
        type="btb_pdf",
        display_name="BTB - Be The Bank",
        description="Upload monthly PDF portfolio reports from Be The Bank (btbisrael.co.il). No credentials required.",
        category="manual_upload",
        flow_type="investment",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=True,
        supported_file_types=["pdf"],
        asset_linking="user_selected",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
    "isracard_xlsx": ConnectorTypeDef(
        type="isracard_xlsx",
        display_name="ישראכרט - העלאת קובץ",
        description="העלה קובץ Excel חודשי מאתר ישראכרט. מחליף את הסקרייפר האוטומטי שנשבר.",
        category="manual_upload",
        flow_type="budget",
        supports_multi_asset=False,
        requires_asset_selection_on_upload=False,
        supported_file_types=["xlsx", "xls"],
        asset_linking="none",
        supports_auto_scrape=False,
        supports_manual_upload=True,
    ),
}


def get_connector_type(type_key: str) -> Optional[ConnectorTypeDef]:
    """Return the ConnectorTypeDef for a type key, or None if unknown."""
    return CONNECTOR_REGISTRY.get(type_key)


def get_upload_connector_types() -> list:
    """Return all manual_upload connector type definitions."""
    return [c for c in CONNECTOR_REGISTRY.values() if c.category == "manual_upload"]
