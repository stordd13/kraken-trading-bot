"""add_backtest_runs_table

Revision ID: 809cc689cf5c
Revises: 001
Create Date: 2026-01-16 14:29:08.723670
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '809cc689cf5c'
down_revision: str | None = '001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - add backtest_runs table."""
    op.create_table(
        'backtest_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False, comment="Unique backtest run identifier"),
        sa.Column('run_name', sa.String(100), nullable=False, comment="Human-readable backtest name"),
        sa.Column('strategy', sa.String(50), nullable=False, comment="Strategy name"),
        sa.Column('pair', sa.String(20), nullable=False, comment="Trading pair (e.g., XBT/USDC)"),
        sa.Column('start_time', sa.TIMESTAMP(timezone=True), nullable=False, comment="Backtest period start (UTC)"),
        sa.Column('end_time', sa.TIMESTAMP(timezone=True), nullable=False, comment="Backtest period end (UTC)"),
        sa.Column('starting_balance', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Initial balance"),
        sa.Column('ending_balance', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Final balance"),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0', comment="Total number of trades"),
        sa.Column('winning_trades', sa.Integer(), nullable=False, server_default='0', comment="Number of winning trades"),
        sa.Column('losing_trades', sa.Integer(), nullable=False, server_default='0', comment="Number of losing trades"),
        sa.Column('win_rate', sa.DECIMAL(precision=5, scale=4), nullable=False, server_default='0', comment="Win rate (0-1)"),
        sa.Column('total_pnl', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Total profit/loss"),
        sa.Column('total_fees', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Total fees paid"),
        sa.Column('net_pnl', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Net profit/loss (total_pnl - total_fees)"),
        sa.Column('total_return_pct', sa.DECIMAL(precision=10, scale=4), nullable=False, comment="Total return percentage"),
        sa.Column('max_drawdown', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Maximum drawdown amount"),
        sa.Column('max_drawdown_pct', sa.DECIMAL(precision=10, scale=4), nullable=False, comment="Maximum drawdown percentage"),
        sa.Column('sharpe_ratio', sa.DECIMAL(precision=10, scale=4), nullable=False, comment="Sharpe ratio"),
        sa.Column('profit_factor', sa.DECIMAL(precision=10, scale=4), nullable=False, comment="Profit factor (total_wins / total_losses)"),
        sa.Column('average_win', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Average winning trade amount"),
        sa.Column('average_loss', sa.DECIMAL(precision=18, scale=8), nullable=False, comment="Average losing trade amount"),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now(), comment="When this backtest was run"),
        comment="Backtest run results for strategy analysis"
    )

    # Create indexes
    op.create_index('ix_backtest_runs_strategy', 'backtest_runs', ['strategy'])
    op.create_index('ix_backtest_runs_pair', 'backtest_runs', ['pair'])
    op.create_index('ix_backtest_runs_start_time', 'backtest_runs', ['start_time'])
    op.create_index('ix_backtest_runs_created_at', 'backtest_runs', ['created_at'])
    op.create_index('ix_backtest_runs_strategy_created', 'backtest_runs', ['strategy', 'created_at'])
    op.create_index('ix_backtest_runs_pair_created', 'backtest_runs', ['pair', 'created_at'])


def downgrade() -> None:
    """Revert migration - drop backtest_runs table."""
    op.drop_index('ix_backtest_runs_pair_created', table_name='backtest_runs')
    op.drop_index('ix_backtest_runs_strategy_created', table_name='backtest_runs')
    op.drop_index('ix_backtest_runs_created_at', table_name='backtest_runs')
    op.drop_index('ix_backtest_runs_start_time', table_name='backtest_runs')
    op.drop_index('ix_backtest_runs_pair', table_name='backtest_runs')
    op.drop_index('ix_backtest_runs_strategy', table_name='backtest_runs')
    op.drop_table('backtest_runs')
