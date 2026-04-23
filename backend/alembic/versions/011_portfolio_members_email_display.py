"""portfolio_members: add email, display_name, invited_at, accepted_at

Revision ID: 011_portfolio_members_email_display
Revises: 010_auth_portfolio_members
Create Date: 2026-04-23
"""
import sqlalchemy as sa
from alembic import op

revision = "011_portfolio_members_email_display"
down_revision = "010_auth_portfolio_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolio_members",
        sa.Column("email", sa.VARCHAR(), nullable=True))
    op.add_column("portfolio_members",
        sa.Column("display_name", sa.VARCHAR(), nullable=True))
    op.add_column("portfolio_members",
        sa.Column("invited_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=True))
    op.add_column("portfolio_members",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("portfolio_members", "accepted_at")
    op.drop_column("portfolio_members", "invited_at")
    op.drop_column("portfolio_members", "display_name")
    op.drop_column("portfolio_members", "email")
