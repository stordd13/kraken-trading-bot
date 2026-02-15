"""add_sortino_ratio_to_backtest_runs

Revision ID: a7b8c9d0e1f2
Revises: 5127885ea921
Create Date: 2026-01-31 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = '5127885ea921'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sortino_ratio column to backtest_runs table."""
    op.add_column(
        'backtest_runs',
        sa.Column(
            'sortino_ratio',
            sa.DECIMAL(precision=10, scale=4),
            nullable=False,
            server_default='0',
            comment='Sortino ratio (downside volatility)',
        ),
    )


def downgrade() -> None:
    """Remove sortino_ratio column from backtest_runs table."""
    op.drop_column('backtest_runs', 'sortino_ratio')
