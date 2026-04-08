"""
utils/enums.py – Single source of truth for all system enums.
Import from here everywhere else; never redefine inline.
"""
from enum import Enum


# ── Asset ──────────────────────────────────────────────────────────────────────

class AssetBehavior(str, Enum):
    """Determines which calculation model is applied to an asset."""
    MARKET = "MARKET"                               # stocks, ETF, crypto – market price feed
    FUND = "FUND"                                   # pension, insurance, keren hishtalmut
    MANUAL = "MANUAL"                               # whisky casks, land, alternatives
    REAL_ESTATE = "REAL_ESTATE"                     # operational RE with cashflows
    REAL_ESTATE_PIPELINE = "REAL_ESTATE_PIPELINE"   # under construction
    ENERGY_INCOME = "ENERGY_INCOME"                 # solar / special income assets
    NO_RETURN = "NO_RETURN"                         # placeholder / not tracked


class AssetCategory(str, Enum):
    SECURITIES = "securities"       # stocks, ETF
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"
    PENSION = "pension"             # pension, bituach menahalim, keren hishtalmut
    ALTERNATIVES = "alternatives"   # whisky, art, collectibles
    DEBT_INCOME = "debt_income"     # BTB, loans
    SPECIAL_INCOME = "special_income"  # solar
    CASH = "cash"


class AssetStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class LifecycleStage(str, Enum):
    OPERATIONAL = "operational"
    PIPELINE = "pipeline"
    PRE_COMPLETION = "pre_completion"
    STABILIZED = "stabilized"
    SPECULATIVE = "speculative"
    EXITED = "exited"
    PAUSED = "paused"


class PricingMode(str, Enum):
    MARKET_PRICE = "market_price"
    MANUAL_VALUATION = "manual_valuation"
    DERIVED_FROM_TRANSACTIONS = "derived_from_transactions"


# ── Account ────────────────────────────────────────────────────────────────────

class AccountType(str, Enum):
    BROKERAGE = "brokerage"
    PENSION_ACCOUNT = "pension_account"
    REAL_ESTATE_ACCOUNT = "real_estate_account"
    ALTERNATIVE_ACCOUNT = "alternative_account"
    CASH = "cash"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


# ── Transaction ────────────────────────────────────────────────────────────────

class TransactionType(str, Enum):
    """
    Granular subtype used for display and filtering.
    Maps from Base44 'type' field.
    """
    BUY = "buy"
    SELL = "sell"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    DIVIDEND = "dividend"
    INCOME = "income"
    EXPENSE = "expense"
    ALLOCATION = "allocation"
    VEST = "vest"
    BONUS = "bonus"
    LOAN_IN = "loan_in"
    LOAN_PAYMENT = "loan_payment"
    INTEREST_PAYMENT = "interest_payment"
    EXTERNAL_DEPOSIT = "external_deposit"
    EXTERNAL_WITHDRAWAL = "external_withdrawal"
    SWAP_IN = "swap_in"
    TRANSFER = "transfer"
    VALUATION = "valuation"
    OTHER = "other"


class EconomicType(str, Enum):
    """
    CRITICAL for correct IRR / XIRR and P&L computation.
    This is the canonical single version — all Base44 variants are normalized
    to these values on import via ECONOMIC_TYPE_NORMALIZE in base44_importer.py.

    Sign convention (from portfolio perspective):
      OUTFLOW  = money leaving the portfolio (negative cashflow)
      INFLOW   = money entering the portfolio (positive cashflow)

    See engine/xirr.py for how each type is treated in cashflow calculations.
    """
    # ── Trades ──────────────────────────────────────────────────────────────
    BUY = "BUY"                         # asset purchase – investment outflow
    SELL = "SELL"                       # asset sale – investment inflow

    # ── Cash movements ──────────────────────────────────────────────────────
    DEPOSIT = "DEPOSIT"                 # cash into account – financing inflow
    WITHDRAWAL = "WITHDRAWAL"           # cash out of account – financing outflow

    # ── Income ──────────────────────────────────────────────────────────────
    INCOME = "INCOME"                   # dividends, interest, rental, bonus, vest

    # ── Expenses ────────────────────────────────────────────────────────────
    EXPENSE = "EXPENSE"                 # fees, taxes, storage, maintenance

    # ── Financing ───────────────────────────────────────────────────────────
    FINANCING_INFLOW = "FINANCING_INFLOW"       # loan received
    FINANCING_OUTFLOW = "FINANCING_OUTFLOW"     # loan repayment (principal + interest)

    # ── Capital deployments ─────────────────────────────────────────────────
    INVESTMENT_INFLOW = "INVESTMENT_INFLOW"     # capital returned / exit proceeds
    INVESTMENT_OUTFLOW = "INVESTMENT_OUTFLOW"   # capital deployed (non-trade)

    # ── Non-cashflow ────────────────────────────────────────────────────────
    REVALUATION = "REVALUATION"         # valuation event, no cash movement


# Normalization map: Base44 raw values → canonical EconomicType
# Used by the importer to unify the two naming conventions found in the data.
ECONOMIC_TYPE_NORMALIZE = {
    # Old snake_case style
    "investment_outflow":   EconomicType.INVESTMENT_OUTFLOW,
    "investment_inflow":    EconomicType.INVESTMENT_INFLOW,
    "financing_outflow":    EconomicType.FINANCING_OUTFLOW,
    "financing_inflow":     EconomicType.FINANCING_INFLOW,
    "operating_expense":    EconomicType.EXPENSE,
    "operating_income":     EconomicType.INCOME,
    "acquisition_cost":     EconomicType.EXPENSE,
    "rental_income":        EconomicType.INCOME,
    "dividend":             EconomicType.INCOME,
    "interest_income":      EconomicType.INCOME,
    "other_income":         EconomicType.INCOME,
    "loan_drawdown":        EconomicType.FINANCING_INFLOW,
    "principal_payment":    EconomicType.FINANCING_OUTFLOW,
    "interest_payment":     EconomicType.EXPENSE,
    "sale_proceeds":        EconomicType.SELL,
    "revaluation":          EconomicType.REVALUATION,
    # New uppercase style (already canonical, included for completeness)
    "BUY":                  EconomicType.BUY,
    "SELL":                 EconomicType.SELL,
    "DEPOSIT":              EconomicType.DEPOSIT,
    "WITHDRAWAL":           EconomicType.WITHDRAWAL,
    "INCOME":               EconomicType.INCOME,
    "EXPENSE":              EconomicType.EXPENSE,
    "FINANCING_INFLOW":     EconomicType.FINANCING_INFLOW,
    "FINANCING_OUTFLOW":    EconomicType.FINANCING_OUTFLOW,
    "INVESTMENT_INFLOW":    EconomicType.INVESTMENT_INFLOW,
    "INVESTMENT_OUTFLOW":   EconomicType.INVESTMENT_OUTFLOW,
    "REVALUATION":          EconomicType.REVALUATION,
}


class TransactionDomain(str, Enum):
    WHISKY = "whisky"
    REAL_ESTATE = "real_estate"
    SECURITIES = "securities"
    CRYPTO = "crypto"
    PENSION = "pension"
    BTB = "btb"
    SOLAR = "solar"
    GENERAL = "general"


class TransactionStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    CANCELLED = "cancelled"


class TransactionSource(str, Enum):
    MANUAL = "manual"
    IMPORT = "import"
    CONNECTOR = "connector"


# ── Valuation ──────────────────────────────────────────────────────────────────

class ValuationMethod(str, Enum):
    MANUAL = "manual"
    APPRAISAL = "appraisal"
    BROKER_ESTIMATE = "broker_estimate"
    MODEL = "model"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
