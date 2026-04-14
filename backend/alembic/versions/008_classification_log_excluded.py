"""classification_log: add excluded column

Revision ID: 008_classification_log_excluded
Revises: 007_accounts_bool_defaults
Create Date: 2026-04-14
"""
from alembic import op

revision = "008_classification_log_excluded"
down_revision = "007_accounts_bool_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS is safe to run even if column was added manually in production
    op.execute(
        "ALTER TABLE classification_log "
        "ADD COLUMN IF NOT EXISTS excluded BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.drop_column("classification_log", "excluded")
