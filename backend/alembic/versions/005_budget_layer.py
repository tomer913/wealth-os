"""add budget layer: categories, plans, actuals, rules, classification log

Revision ID: 005_budget_layer
Revises: 004_raw_data_layer
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '005_budget_layer'
down_revision = '004_raw_data_layer'
branch_labels = None
depends_on = None

PORTFOLIO_ID = '53f8f313-98e8-5de3-bd64-55826cbd82bb'


def upgrade() -> None:
    # ── budget_categories ─────────────────────────────────────────────────────
    op.create_table(
        'budget_categories',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('parent_id', UUID(as_uuid=True),
                  sa.ForeignKey('budget_categories.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('name_en', sa.Text, nullable=True),
        sa.Column('category_type', sa.Text, nullable=False),
        sa.Column('icon', sa.Text, nullable=True),
        sa.Column('color', sa.Text, nullable=True),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_budget_categories_portfolio_type',
                    'budget_categories', ['portfolio_id', 'category_type'])

    # ── budget_plans ──────────────────────────────────────────────────────────
    op.create_table(
        'budget_plans',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('category_id', UUID(as_uuid=True),
                  sa.ForeignKey('budget_categories.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('year', sa.Integer, nullable=False),
        sa.Column('plan_type', sa.Text, nullable=False,
                  server_default='fixed_monthly'),
        sa.Column('monthly_amount', sa.Numeric(18, 4), nullable=True),
        sa.Column('annual_amount', sa.Numeric(18, 4), nullable=True),
        sa.Column('monthly_overrides', JSONB, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('portfolio_id', 'category_id', 'year',
                            name='uq_budget_plans_category_year'),
    )

    # ── budget_actuals ────────────────────────────────────────────────────────
    op.create_table(
        'budget_actuals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('category_id', UUID(as_uuid=True),
                  sa.ForeignKey('budget_categories.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('year', sa.Integer, nullable=False),
        sa.Column('month', sa.Integer, nullable=False),
        sa.Column('actual_amount', sa.Numeric(18, 4), nullable=False,
                  server_default='0'),
        sa.Column('transaction_count', sa.Integer, nullable=False,
                  server_default='0'),
        sa.Column('last_updated', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('portfolio_id', 'category_id', 'year', 'month',
                            name='uq_budget_actuals_category_month'),
    )
    op.create_index('ix_budget_actuals_period',
                    'budget_actuals', ['portfolio_id', 'year', 'month'])

    # ── budget_category_rules ─────────────────────────────────────────────────
    op.create_table(
        'budget_category_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('portfolio_id', UUID(as_uuid=True),
                  sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('category_id', UUID(as_uuid=True),
                  sa.ForeignKey('budget_categories.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('priority', sa.Integer, nullable=False, server_default='100'),
        sa.Column('status', sa.Text, nullable=False, server_default='suggested'),
        sa.Column('conditions', JSONB, nullable=False),
        sa.Column('confidence', sa.Float, nullable=False, server_default='1.0'),
        sa.Column('source', sa.Text, nullable=False, server_default='manual'),
        sa.Column('ai_reasoning', sa.Text, nullable=True),
        sa.Column('match_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_matched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_budget_rules_portfolio_priority',
                    'budget_category_rules', ['portfolio_id', 'priority'])
    op.create_index('ix_budget_rules_status',
                    'budget_category_rules', ['status'])

    # ── classification_log ────────────────────────────────────────────────────
    op.create_table(
        'classification_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('raw_transaction_id', UUID(as_uuid=True),
                  sa.ForeignKey('raw_transactions.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('category_id', UUID(as_uuid=True),
                  sa.ForeignKey('budget_categories.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('rule_id', UUID(as_uuid=True),
                  sa.ForeignKey('budget_category_rules.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('method', sa.Text, nullable=False),
        sa.Column('confidence', sa.Float, nullable=False, server_default='1.0'),
        sa.Column('ai_model', sa.Text, nullable=True),
        sa.Column('ai_prompt_tokens', sa.Integer, nullable=True),
        sa.Column('ai_completion_tokens', sa.Integer, nullable=True),
        sa.Column('needs_review', sa.Boolean, nullable=False,
                  server_default='false'),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_classification_log_needs_review',
                    'classification_log', ['needs_review', 'created_at'])

    # ── Seed categories ───────────────────────────────────────────────────────
    _seed_categories(op)


def _seed_categories(op):
    """Seed initial budget categories for the main portfolio."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    def cat(name, category_type, name_en=None, color=None, sort_order=0):
        return {
            'portfolio_id': PORTFOLIO_ID,
            'name': name,
            'name_en': name_en,
            'category_type': category_type,
            'color': color,
            'sort_order': sort_order,
            'is_active': True,
            'created_at': now,
        }

    income_cats = [
        cat('כנרת', 'income', 'Kinneret Salary', '#10b981', 0),
        cat('תומר', 'income', 'Tomer Salary', '#059669', 1),
        cat('שכירות כוכב', 'income', 'Kochav Rental', '#34d399', 2),
        cat('שכירות באר שבע', 'income', 'Beer Sheva Rental', '#6ee7b7', 3),
        cat('שכירות תל אביב', 'income', 'Tel Aviv Rental', '#a7f3d0', 4),
        cat('משרד הביטחון', 'income', 'Defense Ministry', '#3b82f6', 5),
        cat('מענק ילדים', 'income', "Children's Grant", '#60a5fa', 6),
        cat('מתנות וארועים', 'income', 'Gifts & Events Income', '#93c5fd', 7),
        cat('חשמל סולארי', 'income', 'Solar Electricity', '#fbbf24', 8),
    ]

    fixed_cats = [
        cat('משכנתא כוכב יאיר', 'expense', 'Kochav Yair Mortgage', '#ef4444', 0),
        cat('משכנתא תל אביב', 'expense', 'Tel Aviv Mortgage', '#f87171', 1),
        cat('משכנתא באר שבע', 'expense', 'Beer Sheva Mortgage', '#fca5a5', 2),
        cat('הלוואה טפחות', 'expense', 'Tefahot Loan', '#dc2626', 3),
        cat('הלוואה בינלאומי', 'expense', 'International Loan', '#b91c1c', 4),
        cat('הלוואה רכב', 'expense', 'Car Loan', '#991b1b', 5),
        cat('הלוואה גג סולארי', 'expense', 'Solar Roof Loan', '#7f1d1d', 6),
        cat('הלוואה ישראכארט', 'expense', 'Isracard Loan', '#450a0a', 7),
    ]

    variable_cats = [
        cat('קניות', 'expense', 'Shopping', '#8b5cf6', 10),
        cat('רכב תומר', 'expense', "Tomer's Car", '#7c3aed', 11),
        cat('דלק', 'expense', 'Fuel', '#6d28d9', 12),
        cat('טיולים', 'expense', 'Travel', '#5b21b6', 13),
        cat('תחזוקה דירות', 'expense', 'Apartment Maintenance', '#4c1d95', 14),
        cat('שידרוגים בית', 'expense', 'Home Upgrades', '#f59e0b', 15),
        cat('תרומות', 'expense', 'Donations', '#d97706', 16),
        cat('חוגים', 'expense', 'Activities & Classes', '#b45309', 17),
        cat('בילויים ומסעדות', 'expense', 'Dining & Entertainment', '#92400e', 18),
        cat('ביגוד והנעלה', 'expense', 'Clothing & Footwear', '#78350f', 19),
        cat('תקשורת', 'expense', 'Communication', '#06b6d4', 20),
        cat('גינון וניקיון', 'expense', 'Gardening & Cleaning', '#0891b2', 21),
        cat('מתנות ואירועים', 'expense', 'Gifts & Events', '#0e7490', 22),
        cat('ביטוחים', 'expense', 'Insurance', '#155e75', 23),
        cat('חשמל', 'expense', 'Electricity', '#164e63', 24),
        cat('מים וגז', 'expense', 'Water & Gas', '#f97316', 25),
        cat('ארנונה', 'expense', 'Property Tax', '#ea580c', 26),
        cat('שתיה', 'expense', 'Beverages', '#c2410c', 27),
        cat('קוסמטיקה', 'expense', 'Cosmetics', '#9a3412', 28),
        cat('מזומן', 'expense', 'Cash', '#7c2d12', 29),
        cat('שונות', 'expense', 'Miscellaneous', '#64748b', 30),
        cat('קייטנות ומחנות', 'expense', 'Camps & Day Camps', '#475569', 31),
    ]

    saving_cats = [
        cat('חיסכון', 'saving', 'Savings', '#14b8a6', 0),
        cat('חסכון ילדים', 'saving', "Children's Savings", '#0d9488', 1),
    ]

    all_cats = income_cats + fixed_cats + variable_cats + saving_cats
    if all_cats:
        op.bulk_insert(
            sa.table(
                'budget_categories',
                sa.column('portfolio_id', sa.Text),
                sa.column('name', sa.Text),
                sa.column('name_en', sa.Text),
                sa.column('category_type', sa.Text),
                sa.column('color', sa.Text),
                sa.column('sort_order', sa.Integer),
                sa.column('is_active', sa.Boolean),
                sa.column('created_at', sa.Text),
            ),
            all_cats,
        )


def downgrade() -> None:
    op.drop_index('ix_classification_log_needs_review')
    op.drop_table('classification_log')
    op.drop_index('ix_budget_rules_status')
    op.drop_index('ix_budget_rules_portfolio_priority')
    op.drop_table('budget_category_rules')
    op.drop_index('ix_budget_actuals_period')
    op.drop_table('budget_actuals')
    op.drop_table('budget_plans')
    op.drop_index('ix_budget_categories_portfolio_type')
    op.drop_table('budget_categories')
