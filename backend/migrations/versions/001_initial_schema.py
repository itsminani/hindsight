"""initial schema: every table from docs/data-model.md.

Generated with "alembic revision --autogenerate", then reviewed by hand.

Revision ID: 001
Revises: 
Create Date: 2026-11-14 00:27:45.489465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables, constraints and indexes."""
    op.create_table('users',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('idempotency_keys',
    sa.Column('user_id', sa.Text(), nullable=False),
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('request_hash', sa.Text(), nullable=False),
    sa.Column('response_status', sa.Integer(), nullable=False),
    sa.Column('response_body', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_idempotency_keys_user_id_users')),
    sa.PrimaryKeyConstraint('user_id', 'key', name=op.f('pk_idempotency_keys'))
    )
    op.create_table('plans',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('owner_id', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('credits_available', sa.Integer(), server_default='0', nullable=False),
    sa.Column('credits_held', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('personal', 'shared')", name=op.f('ck_plans_kind')),
    sa.CheckConstraint('credits_available >= 0', name=op.f('ck_plans_credits_available_not_negative')),
    sa.CheckConstraint('credits_held >= 0', name=op.f('ck_plans_credits_held_not_negative')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_plans_owner_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_plans'))
    )
    op.create_index(op.f('ix_plans_owner_id'), 'plans', ['owner_id'], unique=False)
    op.create_index('uq_plans_one_personal_per_owner', 'plans', ['owner_id'], unique=True, postgresql_where=sa.text("kind = 'personal'"))
    op.create_table('portfolios',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('owner_id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_portfolios_owner_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_portfolios'))
    )
    op.create_index(op.f('ix_portfolios_owner_id'), 'portfolios', ['owner_id'], unique=False)
    op.create_table('plan_members',
    sa.Column('user_id', sa.Text(), nullable=False),
    sa.Column('plan_id', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('owner', 'member')", name=op.f('ck_plan_members_role')),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], name=op.f('fk_plan_members_plan_id_plans')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_plan_members_user_id_users')),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_plan_members'))
    )
    op.create_index(op.f('ix_plan_members_plan_id'), 'plan_members', ['plan_id'], unique=False)
    op.create_table('positions',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('portfolio_id', sa.Text(), nullable=False),
    sa.Column('ticker', sa.Text(), nullable=False),
    sa.Column('shares', sa.Integer(), nullable=False),
    sa.Column('buy_date', sa.Date(), nullable=False),
    sa.Column('sell_date', sa.Date(), nullable=True),
    sa.CheckConstraint('sell_date IS NULL OR sell_date >= buy_date', name=op.f('ck_positions_sell_after_buy')),
    sa.CheckConstraint('shares > 0', name=op.f('ck_positions_shares_positive')),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], name=op.f('fk_positions_portfolio_id_portfolios'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_positions'))
    )
    op.create_index(op.f('ix_positions_portfolio_id'), 'positions', ['portfolio_id'], unique=False)
    op.create_table('reports',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('portfolio_id', sa.Text(), nullable=False),
    sa.Column('requested_by', sa.Text(), nullable=False),
    sa.Column('plan_id', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='pending', nullable=False),
    sa.Column('credits_held', sa.Integer(), nullable=False),
    sa.Column('credits_charged', sa.Integer(), server_default='0', nullable=False),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('pending', 'done', 'failed')", name=op.f('ck_reports_status')),
    sa.CheckConstraint('credits_charged >= 0', name=op.f('ck_reports_credits_charged_not_negative')),
    sa.CheckConstraint('credits_held >= 0', name=op.f('ck_reports_credits_held_not_negative')),
    sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], name=op.f('fk_reports_plan_id_plans')),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], name=op.f('fk_reports_portfolio_id_portfolios')),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name=op.f('fk_reports_requested_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reports'))
    )
    op.create_index(op.f('ix_reports_portfolio_id'), 'reports', ['portfolio_id'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('report_id', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='queued', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('run_after', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name=op.f('ck_jobs_status')),
    sa.ForeignKeyConstraint(['report_id'], ['reports.id'], name=op.f('fk_jobs_report_id_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs')),
    sa.UniqueConstraint('report_id', name=op.f('uq_jobs_report_id'))
    )
    op.create_index('ix_jobs_status_run_after', 'jobs', ['status', 'run_after'], unique=False)
    op.create_table('report_items',
    sa.Column('report_id', sa.Text(), nullable=False),
    sa.Column('position_id', sa.Text(), nullable=False),
    sa.Column('sold_for', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('worth_today', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('difference', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.ForeignKeyConstraint(['position_id'], ['positions.id'], name=op.f('fk_report_items_position_id_positions')),
    sa.ForeignKeyConstraint(['report_id'], ['reports.id'], name=op.f('fk_report_items_report_id_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('report_id', 'position_id', name=op.f('pk_report_items'))
    )


def downgrade() -> None:
    """Drop everything, children first (reverse order of creation)."""
    op.drop_table('report_items')
    op.drop_index('ix_jobs_status_run_after', table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_reports_portfolio_id'), table_name='reports')
    op.drop_table('reports')
    op.drop_index(op.f('ix_positions_portfolio_id'), table_name='positions')
    op.drop_table('positions')
    op.drop_index(op.f('ix_plan_members_plan_id'), table_name='plan_members')
    op.drop_table('plan_members')
    op.drop_index(op.f('ix_portfolios_owner_id'), table_name='portfolios')
    op.drop_table('portfolios')
    op.drop_index('uq_plans_one_personal_per_owner', table_name='plans', postgresql_where=sa.text("kind = 'personal'"))
    op.drop_index(op.f('ix_plans_owner_id'), table_name='plans')
    op.drop_table('plans')
    op.drop_table('idempotency_keys')
    op.drop_table('users')
