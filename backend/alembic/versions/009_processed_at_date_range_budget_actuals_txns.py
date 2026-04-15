"""classification_log: add processed_at; processor_runs: date_from/date_to; budget_actual_transactions table

Revision ID: 009_processed_at_date_range_budget_actuals_txns
Revises: 008_classification_log_excluded
Create Date: 2026-04-15
"""
from alembic import op

revision = "009_processed_at_date_range_budget_actuals_txns"
down_revision = "008_classification_log_excluded"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. classification_log.processed_at — set by engine on every run
    op.execute(
        "ALTER TABLE classification_log "
        "ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ"
    )

    # 2. processor_runs — audit trail for date-range reruns
    op.execute(
        "ALTER TABLE processor_runs "
        "ADD COLUMN IF NOT EXISTS date_from DATE, "
        "ADD COLUMN IF NOT EXISTS date_to DATE"
    )

    # 3. budget_actual_transactions — idempotent junction: one row per raw_transaction
    op.execute("""
        CREATE TABLE IF NOT EXISTS budget_actual_transactions (
            raw_transaction_id  UUID PRIMARY KEY
                                REFERENCES raw_transactions(id) ON DELETE CASCADE,
            budget_actual_id    UUID NOT NULL
                                REFERENCES budget_actuals(id) ON DELETE CASCADE,
            amount              NUMERIC(18,4) NOT NULL,
            categorized_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_bat_budget_actual_id
        ON budget_actual_transactions(budget_actual_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS budget_actual_transactions")
    op.execute("ALTER TABLE processor_runs DROP COLUMN IF EXISTS date_to")
    op.execute("ALTER TABLE processor_runs DROP COLUMN IF EXISTS date_from")
    op.execute("ALTER TABLE classification_log DROP COLUMN IF EXISTS processed_at")
