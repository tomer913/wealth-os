"""add asset_price_history table

Revision ID: 003_asset_price_history
Revises: 002_connectors
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '003_asset_price_history'
down_revision = '002_connectors'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'asset_price_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('asset_id', UUID(as_uuid=True),
                  sa.ForeignKey('assets.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('price_date', sa.Date, nullable=False, index=True),
        sa.Column('price', sa.Numeric(18, 6), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('open', sa.Numeric(18, 6), nullable=True),
        sa.Column('high', sa.Numeric(18, 6), nullable=True),
        sa.Column('low', sa.Numeric(18, 6), nullable=True),
        sa.Column('volume', sa.Numeric(24, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('asset_id', 'price_date', 'source',
                            name='uq_asset_price_history'),
    )
    op.create_index('ix_asset_price_history_date',
                    'asset_price_history', ['price_date'])


def downgrade() -> None:
    op.drop_index('ix_asset_price_history_date')
    op.drop_table('asset_price_history')
