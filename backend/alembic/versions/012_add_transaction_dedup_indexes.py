"""add_transaction_dedup_indexes

Revision ID: 012_add_transaction_dedup_indexes
Revises: 011_portfolio_members_email_display
Create Date: 2026-04-25

Two-tier dedup strategy for the transactions table:
  Tier 1 — connector dedup: unique on external_reference_id (partial, NOT NULL)
  Tier 2 — manual entry dedup: unique on natural key (partial, NULL ref id)
"""
from alembic import op

revision = "012_add_transaction_dedup_indexes"
down_revision = "011_portfolio_members_email_display"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop any existing plain index on external_reference_id
    op.execute("DROP INDEX IF EXISTS ix_transactions_external_reference_id")

    # ── Tier 1: connector dedup ─────────────────────────────────────────────
    # One row per exchange trade ID; covers PROC-xxx bank rows and KRAKEN-xxx etc.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS transactions_connector_dedup
        ON transactions (external_reference_id)
        WHERE external_reference_id IS NOT NULL
    """)

    # ── Tier 2: manual entry dedup ──────────────────────────────────────────
    # Before adding the index, remove existing true duplicates (NULL ext ref only).
    # NULL = NULL is false in SQL so we must IS-NULL-guard both sides.
    op.execute("""
        DELETE FROM transactions t1
        USING transactions t2
        WHERE t1.id > t2.id
          AND t1.portfolio_id = t2.portfolio_id
          AND t1.external_reference_id IS NULL
          AND t2.external_reference_id IS NULL
          AND (t1.asset_id = t2.asset_id
               OR (t1.asset_id IS NULL AND t2.asset_id IS NULL))
          AND t1.date = t2.date
          AND t1.type = t2.type
          AND (t1.quantity = t2.quantity
               OR (t1.quantity IS NULL AND t2.quantity IS NULL))
          AND (t1.total_amount = t2.total_amount
               OR (t1.total_amount IS NULL AND t2.total_amount IS NULL))
    """)

    # PostgreSQL treats each NULL as distinct in unique indexes, so two rows
    # with NULL asset_id won't conflict — this index only fires when both
    # asset_id and quantity are non-NULL (i.e. real securities/crypto trades).
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS transactions_manual_dedup
        ON transactions (
            portfolio_id,
            asset_id,
            date,
            type,
            quantity,
            total_amount
        )
        WHERE external_reference_id IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS transactions_manual_dedup")
    op.execute("DROP INDEX IF EXISTS transactions_connector_dedup")
