"""add raw data layer: raw_transactions, service_checkpoints, processor_runs

Revision ID: 004_raw_data_layer
Revises: 003_asset_price_history
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '004_raw_data_layer'
down_revision = '003_asset_price_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── raw_transactions ──────────────────────────────────────────────────────
    op.create_table(
        'raw_transactions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('raw_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('amount', sa.Numeric(18, 4), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False),
        sa.Column('reference', sa.Text, nullable=True),
        sa.Column('extra_raw', JSONB, nullable=True),
        sa.Column('external_ref_id', sa.Text, nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('source', 'external_ref_id',
                            name='uq_raw_transactions_source_ref'),
    )
    # cursor index for processor consumption
    op.create_index(
        'ix_raw_transactions_cursor',
        'raw_transactions',
        ['portfolio_id', 'source', 'id'],
    )
    # fast lookup by portfolio
    op.create_index(
        'ix_raw_transactions_portfolio',
        'raw_transactions',
        ['portfolio_id'],
    )

    # ── service_checkpoints ───────────────────────────────────────────────────
    op.create_table(
        'service_checkpoints',
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('last_raw_id', UUID(as_uuid=True), nullable=True),
        sa.Column('last_processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('service_name', 'portfolio_id'),
    )

    # ── processor_runs ────────────────────────────────────────────────────────
    op.create_table(
        'processor_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('processor_name', sa.String(100), nullable=False, index=True),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False,
                  server_default='pending'),
        sa.Column('triggered_by', sa.String(20), nullable=False,
                  server_default='scheduler'),
        sa.Column('checkpoint_from', UUID(as_uuid=True), nullable=True),
        sa.Column('checkpoint_to', UUID(as_uuid=True), nullable=True),
        sa.Column('rows_read', sa.Integer, nullable=True),
        sa.Column('rows_written', sa.Integer, nullable=True),
        sa.Column('rows_skipped', sa.Integer, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_traceback', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        'ix_processor_runs_portfolio_name',
        'processor_runs',
        ['portfolio_id', 'processor_name', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_processor_runs_portfolio_name')
    op.drop_table('processor_runs')
    op.drop_table('service_checkpoints')
    op.drop_index('ix_raw_transactions_portfolio')
    op.drop_index('ix_raw_transactions_cursor')
    op.drop_table('raw_transactions')
