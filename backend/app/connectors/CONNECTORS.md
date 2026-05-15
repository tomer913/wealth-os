# Connector Type Registry

This file documents all supported connector types in Wealth OS.
It is read by Claude AI at the start of every session and serves as
both human documentation and AI reference.

## Connector Type Properties

Each connector type defines:
- `type`: internal enum key (used in DB `connectors.type` column)
- `display_name`: shown in UI dropdown
- `description`: shown in UI when creating connector
- `category`: `automatic` | `manual_upload` | `scraper`
- `supports_multi_asset`: whether one connector manages multiple assets
- `requires_asset_selection_on_upload`: user must pick an asset at upload time (not at connector-creation time)
- `supported_file_types`: for `manual_upload` connectors only
- `asset_linking`: how assets are linked — `auto_by_description` | `user_selected` | `account_linked` | `none`
- `schedule_default`: suggested cron schedule

---

## Registry

### Automatic Connectors

| type | display_name | supports_multi_asset | asset_linking | schedule_default |
|------|-------------|---------------------|---------------|-----------------|
| ib_flex | Interactive Brokers | true | auto_by_description | daily |
| kraken | Kraken Exchange | true | auto_by_description | daily |
| cexio | CEX.IO Exchange | true | auto_by_description | daily |
| ecb_fx | ECB FX Rates | true | none | daily |
| yahoo_prices | Yahoo Finance Prices | true | none | daily |

### Scraper Connectors

| type | display_name | supports_multi_asset | asset_linking | schedule_default | notes |
|------|-------------|---------------------|---------------|-----------------|-------|
| isracard | Isracard Scraper | false | account_linked | daily | ⚠️ BROKEN — Isracard added SMS 2FA. Use `isracard_xlsx` instead. Do not run automatically. |
| cal_scraper | CAL Card | false | account_linked | daily | |

### Manual Upload Connectors

| type | display_name | supports_multi_asset | requires_asset_selection_on_upload | supported_file_types | asset_linking |
|------|-------------|---------------------|-----------------------------------|---------------------|---------------|
| fibi_bank | הבינלאומי FIBI | true | false | pdf, xls, xlsx | auto_by_description |
| mizrachi_bank | מזרחי טפחות | true | false | pdf | auto_by_description |
| btb_pdf | BTB - Be The Bank | false | true | pdf | user_selected |
| isracard_xlsx | ישראכרט - העלאת קובץ | false | false | xlsx, xls | none |

**`isracard_xlsx`** replaces the broken `isracard` scraper. After inserting raw_transactions it
automatically runs `BudgetProcessor` to classify transactions into budget categories and returns
`budget_classified` and `budget_needs_review` in the upload response.

**`requires_asset_selection_on_upload = true`** means the user picks an asset from a dropdown
in the upload modal each time they upload. The asset_id is sent as a form field with the file.
This is used for single-asset connectors where asset identity is not determinable from the file content.

---

## Adding a New Connector Type

1. Add entry to this table
2. Add entry to `CONNECTOR_REGISTRY` in `backend/app/connectors/connector_registry.py`
3. If automated: implement connector class in `backend/app/connectors/sources/` and import in `registry.py`
4. If manual_upload: implement parser in `backend/app/connectors/parsers/` and add routing in the upload endpoint in `backend/app/routers/connectors.py`
5. The `GET /api/v1/connector-types` endpoint automatically reflects the registry — no separate update needed

## Asset Linking Strategies

### auto_by_description
Asset is determined by matching fund codes or keywords in the transaction description.
Examples: FIBI matches fund codes (514078 → CASH_FIBI), Mizrachi matches Hebrew keywords.
No asset selection required from the user — handled entirely by the parser.

### user_selected
User picks asset from a dropdown at upload time.
The selected `asset_id` is sent as a form field with the upload request.
Used for single-asset manual connectors like BTB where the file doesn't contain enough
information to identify the target asset automatically.

### account_linked
Asset linked to a specific account, configured once at connector setup.
Used for credit card scrapers.

### none
Connector doesn't link to assets (FX rate feeds, price feeds).
