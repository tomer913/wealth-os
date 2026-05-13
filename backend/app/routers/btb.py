"""
BTB (Be The Bank) upload endpoint.

POST /api/v1/connectors/btb/upload/
  Accepts monthly PDF, parses it, then:
    1. Upserts ManualValuation for the BTB asset (same date → update).
    2. Inserts INCOME Transaction for last month's net return (idempotent).
  Returns parsed summary as JSON.
"""
import logging
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, verify_portfolio_access
from app.database import get_db
from app.models.transaction import Transaction
from app.models.valuation import ManualValuation

router = APIRouter(prefix="/connectors/btb", tags=["btb"])
log = logging.getLogger(__name__)

_BTB_ASSET_ID = uuid.UUID("f8b355d3-920d-5ee4-b9dd-a24efd5bd545")


@router.post("/upload/")
async def upload_btb_report(
    file: UploadFile = File(...),
    portfolio_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Parse a BTB monthly PDF, upsert valuation, insert income transaction."""
    await verify_portfolio_access(
        db, portfolio_id,
        current_user["user_id"], current_user.get("org_id"),
        required_role="editor",
    )

    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="BTB connector accepts PDF files only")

    file_bytes = await file.read()

    try:
        from app.connectors.parsers.btb import parse_btb_pdf
        parsed = parse_btb_pdf(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse BTB report: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to read PDF: {exc}") from exc

    log.info(
        "BTB parsed OK: portfolio=%s date=%s current_value=%.2f net_return=%.2f%% avg_rate=%.2f%%",
        portfolio_id, parsed["report_date"], parsed["current_value"],
        parsed["net_return_pct"], parsed["avg_interest_rate"],
    )

    report_date = parsed["report_date"]

    # ── Upsert ManualValuation ────────────────────────────────────────────────
    month_label = report_date.strftime("%B %Y")
    notes = (
        f"BTB {month_label} — "
        f"net return {parsed['net_return_pct']}%, "
        f"avg rate {parsed['avg_interest_rate']}%"
    )

    try:
        existing_val = (await db.execute(
            select(ManualValuation).where(
                ManualValuation.asset_id == _BTB_ASSET_ID,
                ManualValuation.valuation_date == report_date,
            )
        )).scalar_one_or_none()

        if existing_val:
            existing_val.market_value = parsed["current_value"]
            existing_val.value_ils = parsed["current_value"]
            existing_val.source = "btb_pdf"
            existing_val.notes = notes
            valuation_action = "updated"
            log.info("BTB: updating existing valuation id=%s", existing_val.id)
        else:
            new_val = ManualValuation(
                portfolio_id=portfolio_id,
                asset_id=_BTB_ASSET_ID,
                valuation_date=report_date,
                market_value=parsed["current_value"],
                currency="ILS",
                fx_rate_to_ils=1.0,
                value_ils=parsed["current_value"],
                valuation_method="manual",
                confidence_level="high",
                source="btb_pdf",
                notes=notes,
            )
            db.add(new_val)
            valuation_action = "created"
            log.info("BTB: inserting new valuation for date=%s asset=%s", report_date, _BTB_ASSET_ID)

        # ── Insert Income Transaction (idempotent) ────────────────────────────
        ext_ref = f"btb_{report_date.isoformat()}_monthly_income"
        existing_tx = (await db.execute(
            select(Transaction).where(Transaction.external_reference_id == ext_ref)
        )).scalar_one_or_none()

        if not existing_tx:
            income_amount = round(
                parsed["last_month_return_pct"] * parsed["current_value"] / 100, 4
            )
            db.add(Transaction(
                portfolio_id=portfolio_id,
                asset_id=_BTB_ASSET_ID,
                transaction_date=report_date,
                type="income",           # TransactionType.INCOME
                economic_type="INCOME",  # EconomicType.INCOME
                domain="alternatives",
                total_amount=income_amount,
                currency="ILS",
                source="btb_pdf",
                external_reference_id=ext_ref,
                status="confirmed",
            ))
            tx_action = "created"
            log.info("BTB: inserting income transaction ext_ref=%s amount=%.4f", ext_ref, income_amount)
        else:
            tx_action = "skipped"
            log.info("BTB: income transaction already exists ext_ref=%s", ext_ref)

        await db.flush()   # surfaces any DB constraint errors before commit
        await db.commit()

    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        log.error("BTB upload DB error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"DB write failed: {exc}") from exc

    log.info(
        "BTB upload done: portfolio=%s date=%s value=%.2f valuation=%s tx=%s",
        portfolio_id, report_date, parsed["current_value"], valuation_action, tx_action,
    )

    return {
        "report_date": report_date.isoformat(),
        "current_value": parsed["current_value"],
        "net_invested": parsed["net_invested"],
        "last_month_return_pct": parsed["last_month_return_pct"],
        "net_return_pct": parsed["net_return_pct"],
        "avg_interest_rate": parsed["avg_interest_rate"],
        "gross_interest": parsed["gross_interest"],
        "tax_withheld": parsed["tax_withheld"],
        "mgmt_fee": parsed["mgmt_fee"],
        "valuation": valuation_action,
        "transaction": tx_action,
    }
