"""portfolio_member_invite_fields

Revision ID: 014_portfolio_member_invite_fields
Revises: 013_budget_category_rules_dedup
Create Date: 2026-04-26

Add email + accepted_at to portfolio_members for invitation flow.
Make user_id nullable so pending invites can be stored before the
invitee has a Clerk account.
"""
from alembic import op
import sqlalchemy as sa

revision = "014_portfolio_member_invite_fields"
down_revision = "013_budget_category_rules_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("portfolio_members", "user_id",
                    existing_type=sa.String(100), nullable=True)

    op.add_column("portfolio_members",
                  sa.Column("email", sa.String(255), nullable=True))

    op.add_column("portfolio_members",
                  sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))

    # Existing owner rows are implicitly accepted — stamp them now.
    op.execute("UPDATE portfolio_members SET accepted_at = now() WHERE role = 'owner'")

    # Back-fill owner memberships for any portfolio created before the
    # auto-insert logic was added (idempotent thanks to NOT EXISTS guard).
    op.execute("""
        INSERT INTO portfolio_members
            (id, portfolio_id, user_id, role, accepted_at, created_at, updated_at)
        SELECT gen_random_uuid(), p.id, p.owner_id, 'owner', now(), now(), now()
        FROM portfolios p
        WHERE p.owner_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM portfolio_members pm
              WHERE pm.portfolio_id = p.id AND pm.role = 'owner'
          )
    """)


def downgrade() -> None:
    op.drop_column("portfolio_members", "accepted_at")
    op.drop_column("portfolio_members", "email")
    op.alter_column("portfolio_members", "user_id",
                    existing_type=sa.String(100), nullable=False)
