"""Add budget_name to budget_plans.

Revision ID: 006_budget_name
Revises: 005_budget_layer
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '006_budget_name'
down_revision = '005_budget_layer'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'budget_plans',
        sa.Column('budget_name', sa.Text(), nullable=True, server_default='ראשי'),
    )


def downgrade() -> None:
    op.drop_column('budget_plans', 'budget_name')
