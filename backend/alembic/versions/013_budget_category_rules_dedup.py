"""budget_category_rules_dedup

Revision ID: 013_budget_category_rules_dedup
Revises: 012_add_transaction_dedup_indexes
Create Date: 2026-04-26

Deduplicate budget_category_rules and add a partial unique index on
(portfolio_id, category_id, conditions::text) WHERE status != 'deleted'
so that re-runs of the budget processor cannot create duplicate suggested rules.
"""
from alembic import op

revision = "013_budget_category_rules_dedup"
down_revision = "012_add_transaction_dedup_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove existing duplicates — keep the row with the lowest id (earliest).
    op.execute("""
        DELETE FROM budget_category_rules a
        USING budget_category_rules b
        WHERE a.id > b.id
          AND a.portfolio_id = b.portfolio_id
          AND a.category_id = b.category_id
          AND a.conditions::text = b.conditions::text
          AND a.status = b.status
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_category_rules_conditions
        ON budget_category_rules (
            portfolio_id,
            category_id,
            (conditions::text)
        )
        WHERE status != 'deleted'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_budget_category_rules_conditions")
