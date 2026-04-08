"""Initial schema - Wealth OS

Revision ID: 001
Create Date: 2026-04-05
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid
def upgrade():

    # ──────────────────────────────────────────
    # PORTFOLIOS
    # ──────────────────────────────────────────
    op.create_table(
        "portfolios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_currency", sa.String(10), nullable=False, default="ILS"),
        sa.Column("description", sa.Text),
        sa.Column("is_default", sa.Boolean, default=False),
        sa.Column("owner_id", sa.String(100)),  # auth user id
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ──────────────────────────────────────────
    # ACCOUNTS
    # ──────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),

        # Identity
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("symbol", sa.String(100), nullable=False),   # e.g. ACC_MIGDAL_PENSION

        # Classification
        sa.Column("account_type", sa.String(50)),   # brokerage, pension_account, real_estate_account, alternative_account, cash
        sa.Column("category", sa.String(50)),        # securities, real_estate, pension, alternatives, cash
        sa.Column("currency", sa.String(10), nullable=False, default="ILS"),

        # Institution
        sa.Column("institution", sa.String(200)),
        sa.Column("custodian", sa.String(200)),

        # Flags – PROMOTED from metadata (important for dashboard filters)
        sa.Column("is_liquid", sa.Boolean, default=False),
        sa.Column("is_income_generating", sa.Boolean, default=False),
        sa.Column("include_in_portfolio", sa.Boolean, default=True),

        # State
        sa.Column("status", sa.String(20), default="active"),   # active | inactive | archived
        sa.Column("cash_balance", sa.Numeric(18, 4), default=0),
        sa.Column("opening_balance", sa.Numeric(18, 4)),

        # Extensible
        sa.Column("metadata", JSONB),   # type-specific fields (warehouse address, RE details, etc.)
        sa.Column("notes", sa.Text),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("portfolio_id", "symbol", name="uq_account_symbol"),
    )
    op.create_index("ix_accounts_portfolio_id", "accounts", ["portfolio_id"])
    op.create_index("ix_accounts_symbol", "accounts", ["symbol"])

    # ──────────────────────────────────────────
    # ASSETS
    # ──────────────────────────────────────────
    op.create_table(
        "assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="SET NULL")),

        # Identity
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("symbol", sa.String(100), nullable=False),   # e.g. AAPL, PT_MATOSINHOS_F0204

        # Classification – REAL columns (not buried in metadata)
        sa.Column("asset_behavior", sa.String(50), nullable=False),
        # MARKET | FUND | MANUAL | REAL_ESTATE | REAL_ESTATE_PIPELINE | ENERGY_INCOME | NO_RETURN

        sa.Column("category", sa.String(50)),
        # securities | crypto | real_estate | pension | alternatives | debt_income | special_income | cash

        sa.Column("asset_type", sa.String(50)),     # security | crypto | pension | alternative | real_estate
        sa.Column("sub_type", sa.String(100)),       # ETF | stock | whisky_cask | apartment | pension_fund | etc.

        # Lifecycle
        sa.Column("status", sa.String(20), default="active"),
        # active | inactive | archived

        sa.Column("lifecycle_stage", sa.String(50), default="operational"),
        # operational | pipeline | pre_completion | stabilized | speculative | exited | paused

        # Market data (MARKET behavior only)
        sa.Column("exchange", sa.String(50)),
        sa.Column("currency", sa.String(10), nullable=False, default="ILS"),
        sa.Column("country", sa.String(100)),
        sa.Column("sector", sa.String(100)),
        sa.Column("current_price", sa.Numeric(18, 6)),
        sa.Column("price_updated_at", sa.DateTime(timezone=True)),
        sa.Column("pricing_mode", sa.String(50), default="manual_valuation"),
        # market_price | manual_valuation | derived_from_transactions

        # Flags
        sa.Column("is_manual", sa.Boolean, default=True),

        # Extensible
        sa.Column("metadata", JSONB),   # provider, policy_number, cask details, RE details, etc.

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("portfolio_id", "symbol", name="uq_asset_symbol"),
    )
    op.create_index("ix_assets_portfolio_id", "assets", ["portfolio_id"])
    op.create_index("ix_assets_symbol", "assets", ["symbol"])
    op.create_index("ix_assets_behavior", "assets", ["asset_behavior"])
    op.create_index("ix_assets_category", "assets", ["category"])

    # ──────────────────────────────────────────
    # TRANSACTIONS
    # ──────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="SET NULL")),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL")),

        # Timing
        sa.Column("date", sa.Date, nullable=False),           # transaction date
        sa.Column("effective_date", sa.Date),                 # value date if different

        # Type taxonomy (CRITICAL for correct IRR)
        sa.Column("type", sa.String(50), nullable=False),
        # buy | sell | expense | income | transfer | loan | valuation

        sa.Column("economic_type", sa.String(50)),
        # investment | acquisition_cost | rental_income | dividend | interest_income |
        # other_income | operating_expense | loan_drawdown | principal_payment |
        # interest_payment | sale_proceeds | revaluation

        sa.Column("domain", sa.String(50)),
        # whisky | real_estate | securities | crypto | pension | btb | solar | general

        sa.Column("subtype", sa.String(100)),   # free-form detail label

        # Amounts
        sa.Column("total_amount", sa.Numeric(18, 4)),       # absolute amount
        sa.Column("cashflow_amount", sa.Numeric(18, 4)),    # signed: negative = outflow, positive = inflow
        sa.Column("currency", sa.String(10), nullable=False, default="ILS"),
        sa.Column("fees", sa.Numeric(18, 4), default=0),
        sa.Column("tax", sa.Numeric(18, 4), default=0),

        # Position data (MARKET assets)
        sa.Column("quantity", sa.Numeric(18, 8)),
        sa.Column("price_per_unit", sa.Numeric(18, 6)),
        sa.Column("units_delta", sa.Numeric(18, 8), default=0),

        # Transfer fields
        sa.Column("from_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("to_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("is_internal_transfer", sa.Boolean, default=False),

        # Status
        sa.Column("status", sa.String(20), default="confirmed"),
        # confirmed | pending | cancelled

        sa.Column("source", sa.String(50), default="manual"),
        # manual | import | connector

        sa.Column("notes", sa.Text),
        sa.Column("external_reference_id", sa.String(200)),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_transactions_portfolio_id", "transactions", ["portfolio_id"])
    op.create_index("ix_transactions_asset_id", "transactions", ["asset_id"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_index("ix_transactions_economic_type", "transactions", ["economic_type"])

    # ──────────────────────────────────────────
    # MANUAL VALUATIONS
    # ──────────────────────────────────────────
    op.create_table(
        "manual_valuations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id")),

        sa.Column("date", sa.Date, nullable=False),
        sa.Column("market_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, default="ILS"),
        sa.Column("fx_rate_to_ils", sa.Numeric(10, 6), default=1.0),
        sa.Column("value_ils", sa.Numeric(18, 4)),

        sa.Column("valuation_method", sa.String(50), default="manual"),
        # manual | appraisal | broker_estimate | model

        sa.Column("confidence_level", sa.String(20), default="medium"),
        # low | medium | high

        sa.Column("valuation_source", sa.String(100)),   # who provided it
        sa.Column("is_estimated", sa.Boolean, default=False),
        sa.Column("notes", sa.Text),
        sa.Column("source", sa.String(50), default="manual"),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_valuations_asset_id", "manual_valuations", ["asset_id"])
    op.create_index("ix_valuations_date", "manual_valuations", ["date"])

    # ──────────────────────────────────────────
    # FX RATES
    # ──────────────────────────────────────────
    op.create_table(
        "fx_rates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("from_currency", sa.String(10), nullable=False),
        sa.Column("to_currency", sa.String(10), nullable=False),
        sa.Column("rate", sa.Numeric(12, 6), nullable=False),
        sa.Column("source", sa.String(50), default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("date", "from_currency", "to_currency", name="uq_fx_rate"),
    )
    op.create_index("ix_fx_rates_date", "fx_rates", ["date"])

    # ──────────────────────────────────────────
    # PERFORMANCE SNAPSHOTS
    # ──────────────────────────────────────────
    op.create_table(
        "performance_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE")),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id")),

        sa.Column("snapshot_date", sa.Date, nullable=False),

        # Capital & Value
        sa.Column("invested_capital", sa.Numeric(18, 4)),       # total outflows (cost basis)
        sa.Column("current_value", sa.Numeric(18, 4)),          # current market/manual value
        sa.Column("currency", sa.String(10), default="ILS"),
        sa.Column("value_ils", sa.Numeric(18, 4)),              # converted to ILS

        # Returns
        sa.Column("total_return", sa.Numeric(18, 4)),           # current_value - invested_capital
        sa.Column("total_return_pct", sa.Numeric(10, 6)),       # total_return / invested_capital
        sa.Column("annual_return_pct", sa.Numeric(10, 6)),      # annualized simple return
        sa.Column("xirr_return_pct", sa.Numeric(10, 6)),        # XIRR (time-weighted IRR)

        # Cashflow summary
        sa.Column("total_income", sa.Numeric(18, 4)),           # cumulative income received
        sa.Column("total_expenses", sa.Numeric(18, 4)),         # cumulative operating expenses
        sa.Column("net_cashflow", sa.Numeric(18, 4)),           # income - expenses

        # Meta
        sa.Column("model_used", sa.String(50)),                  # which calculation model was applied
        sa.Column("notes", sa.Text),
        sa.Column("is_stale", sa.Boolean, default=False),       # needs rebuild

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("portfolio_id", "asset_id", "snapshot_date", name="uq_snapshot"),
    )
    op.create_index("ix_snapshots_portfolio_id", "performance_snapshots", ["portfolio_id"])
    op.create_index("ix_snapshots_asset_id", "performance_snapshots", ["asset_id"])
    op.create_index("ix_snapshots_date", "performance_snapshots", ["snapshot_date"])

    # ──────────────────────────────────────────
    # POSITIONS (optional – derived state for MARKET assets)
    # ──────────────────────────────────────────
    op.create_table(
        "positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id")),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),

        sa.Column("quantity", sa.Numeric(18, 8), nullable=False, default=0),
        sa.Column("avg_cost", sa.Numeric(18, 6)),               # average cost per unit
        sa.Column("cost_basis_total", sa.Numeric(18, 4)),       # total cost basis
        sa.Column("currency", sa.String(10)),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.UniqueConstraint("portfolio_id", "account_id", "asset_id", name="uq_position"),
    )


def downgrade():
    op.drop_table("positions")
    op.drop_table("performance_snapshots")
    op.drop_table("fx_rates")
    op.drop_table("manual_valuations")
    op.drop_table("transactions")
    op.drop_table("assets")
    op.drop_table("accounts")
    op.drop_table("portfolios")
