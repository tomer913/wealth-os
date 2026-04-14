"""accounts: set server defaults for is_liquid and is_income_generating

Revision ID: 007_accounts_bool_defaults
Revises: 006_budget_name
Create Date: 2026-04-14
"""
from alembic import op

revision = '007_accounts_bool_defaults'
down_revision = '006_budget_name'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE accounts
            ALTER COLUMN is_liquid SET DEFAULT false,
            ALTER COLUMN is_income_generating SET DEFAULT false
    """)
    # Backfill existing NULLs
    op.execute("""
        UPDATE accounts
        SET
            is_liquid = false
        WHERE is_liquid IS NULL
    """)
    op.execute("""
        UPDATE accounts
        SET
            is_income_generating = false
        WHERE is_income_generating IS NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE accounts
            ALTER COLUMN is_liquid DROP DEFAULT,
            ALTER COLUMN is_income_generating DROP DEFAULT
    """)
