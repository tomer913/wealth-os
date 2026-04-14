"""classification_log: add excluded column

Revision ID: 008_classification_log_excluded
Revises: 007_accounts_bool_defaults
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "008_classification_log_excluded"
down_revision = "007_accounts_bool_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "classification_log",
        sa.Column(
            "excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("classification_log", "excluded")
