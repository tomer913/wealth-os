"""
utils/taxonomy.py – Transaction type taxonomy helpers.

Rules:
  - IRR_CASHFLOW_TYPES: economic types that represent real cash movement for XIRR
  - COST_BASIS_TYPES: economic types that increase invested capital
  - INCOME_TYPES: economic types that are income
  - EXPENSE_TYPES: economic types that are operating expenses
"""
from app.utils.enums import EconomicType

# These flow into XIRR calculations as real cashflows
IRR_CASHFLOW_TYPES: frozenset[EconomicType] = frozenset({
    EconomicType.INVESTMENT,
    EconomicType.ACQUISITION_COST,
    EconomicType.RENTAL_INCOME,
    EconomicType.DIVIDEND,
    EconomicType.INTEREST_INCOME,
    EconomicType.OTHER_INCOME,
    EconomicType.OPERATING_EXPENSE,
    EconomicType.LOAN_DRAWDOWN,
    # NOTE: PRINCIPAL_PAYMENT is intentionally EXCLUDED (balance sheet, not P&L)
    EconomicType.INTEREST_PAYMENT,
    EconomicType.SALE_PROCEEDS,
})

# These increase invested capital / cost basis
COST_BASIS_TYPES: frozenset[EconomicType] = frozenset({
    EconomicType.INVESTMENT,
    EconomicType.ACQUISITION_COST,
})

# Income types (positive cashflow to the investor)
INCOME_TYPES: frozenset[EconomicType] = frozenset({
    EconomicType.RENTAL_INCOME,
    EconomicType.DIVIDEND,
    EconomicType.INTEREST_INCOME,
    EconomicType.OTHER_INCOME,
    EconomicType.SALE_PROCEEDS,
    EconomicType.LOAN_DRAWDOWN,
})

# Expense / outflow types
EXPENSE_TYPES: frozenset[EconomicType] = frozenset({
    EconomicType.OPERATING_EXPENSE,
    EconomicType.INTEREST_PAYMENT,
})

# Non-cashflow events
NON_CASHFLOW_TYPES: frozenset[EconomicType] = frozenset({
    EconomicType.REVALUATION,
    EconomicType.PRINCIPAL_PAYMENT,
})


def is_irr_cashflow(economic_type: str) -> bool:
    try:
        return EconomicType(economic_type) in IRR_CASHFLOW_TYPES
    except ValueError:
        return False


def is_cost_basis(economic_type: str) -> bool:
    try:
        return EconomicType(economic_type) in COST_BASIS_TYPES
    except ValueError:
        return False


def cashflow_sign(economic_type: str) -> int:
    """
    Returns +1 for inflows (investor receives money),
    -1 for outflows (investor pays money),
     0 for non-cashflow events.
    """
    try:
        et = EconomicType(economic_type)
    except ValueError:
        return 0

    if et in NON_CASHFLOW_TYPES:
        return 0
    if et in INCOME_TYPES:
        return 1
    return -1
