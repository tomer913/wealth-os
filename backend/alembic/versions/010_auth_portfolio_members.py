"""auth: add last_accessed_at to portfolios, portfolio_members table, owner default index

Revision ID: 010_auth_portfolio_members
Revises: 009_processed_at_date_range_budget_actuals_txns
Create Date: 2026-04-20
"""
import sqlalchemy as sa
from alembic import op

revision = "010_auth_portfolio_members"
down_revision = "009_processed_at_date_range_budget_actuals_txns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── portfolios: add last_accessed_at ──────────────────────────────────────
    op.add_column(
        "portfolios",
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Partial unique index: only one is_default per owner ───────────────────
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS portfolios_owner_default
        ON portfolios (owner_id)
        WHERE is_default = true
    """)

    # ── portfolio_members table ───────────────────────────────────────────────
    op.create_table(
        "portfolio_members",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("portfolio_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("invited_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("portfolio_id", "user_id", name="uq_portfolio_members_portfolio_user"),
    )
    op.create_index("ix_portfolio_members_portfolio_id", "portfolio_members", ["portfolio_id"])
    op.create_index("ix_portfolio_members_user_id", "portfolio_members", ["user_id"])

    # ── Back-fill owner membership for existing portfolios ────────────────────
    op.execute("""
        INSERT INTO portfolio_members (id, portfolio_id, user_id, role, created_at, updated_at)
        SELECT gen_random_uuid(), id, owner_id, 'owner', now(), now()
        FROM portfolios
        WHERE owner_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("portfolio_members")
    op.execute("DROP INDEX IF EXISTS portfolios_owner_default")
    op.drop_column("portfolios", "last_accessed_at")
