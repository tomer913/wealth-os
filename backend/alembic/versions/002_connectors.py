"""add connectors and connector_runs tables

Revision ID: 002_connectors
Revises: 001_initial_schema
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '002_connectors'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── connectors ────────────────────────────────────────────────────────────
    op.create_table(
        'connectors',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('type', sa.String(50), nullable=False, index=True),
        # config stores encrypted API keys + connector-specific settings
        # encryption handled at application layer, not DB layer
        sa.Column('config', JSONB, nullable=False, server_default='{}'),
        sa.Column('asset_filter', JSONB, nullable=True),
        sa.Column('auto_create_assets', sa.Boolean,
                  nullable=False, server_default='true'),
        sa.Column('schedule', sa.String(50),
                  nullable=False, server_default='daily'),
        sa.Column('is_active', sa.Boolean,
                  nullable=False, server_default='true'),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )

    # ── connector_runs ────────────────────────────────────────────────────────
    op.create_table(
        'connector_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('connector_id', UUID(as_uuid=True),
                  sa.ForeignKey('connectors.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Execution status
        sa.Column('status', sa.String(20), nullable=False,
                  server_default='pending'),
        # pending | running | success | failed | partial
        sa.Column('triggered_by', sa.String(20), nullable=False,
                  server_default='scheduler'),
        # scheduler | manual | api

        # Timing
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer, nullable=True),

        # Results summary
        sa.Column('records_fetched', sa.Integer, nullable=True),
        sa.Column('transactions_created', sa.Integer, nullable=True),
        sa.Column('transactions_skipped', sa.Integer, nullable=True),
        sa.Column('valuations_created', sa.Integer, nullable=True),
        sa.Column('assets_created', sa.Integer, nullable=True),
        sa.Column('fx_rates_updated', sa.Integer, nullable=True),
        sa.Column('prices_updated', sa.Integer, nullable=True),

        # Error details
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_traceback', sa.Text, nullable=True),

        # Resumable pagination state
        sa.Column('checkpoint', JSONB, nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # Indexes for common queries
    op.create_index('ix_connector_runs_status',
                    'connector_runs', ['status'])
    op.create_index('ix_connector_runs_started_at',
                    'connector_runs', ['started_at'])


def downgrade() -> None:
    op.drop_table('connector_runs')
    op.drop_table('connectors')
