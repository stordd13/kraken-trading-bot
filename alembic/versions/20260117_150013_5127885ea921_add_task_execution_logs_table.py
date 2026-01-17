"""add_task_execution_logs_table

Revision ID: 5127885ea921
Revises: 809cc689cf5c
Create Date: 2026-01-17 15:00:13.679906
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5127885ea921'
down_revision: Union[str, None] = '809cc689cf5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration."""
    op.create_table(
        'task_execution_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.String(100), nullable=False, comment="Unique task identifier (e.g., 'daily_ohlc_1min')"),
        sa.Column('pair', sa.String(20), nullable=False, comment="Trading pair (e.g., 'XBT/USDC')"),
        sa.Column('interval', sa.Integer(), nullable=False, comment="OHLC interval in minutes"),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False, comment="When task started execution"),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True, comment="When task completed (NULL if failed or still running)"),
        sa.Column('status', sa.String(20), nullable=False, server_default='running', comment="Task status: running, success, failed"),
        sa.Column('candles_fetched', sa.Integer(), nullable=False, server_default='0', comment="Number of candles fetched in this execution"),
        sa.Column('error_message', sa.Text(), nullable=True, comment="Error message if task failed"),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create indexes
    op.create_index('ix_task_logs_task_started', 'task_execution_logs', ['task_id', 'started_at'])
    op.create_index('ix_task_logs_pair_interval', 'task_execution_logs', ['pair', 'interval'])
    op.create_index(op.f('ix_task_execution_logs_task_id'), 'task_execution_logs', ['task_id'])
    op.create_index(op.f('ix_task_execution_logs_started_at'), 'task_execution_logs', ['started_at'])


def downgrade() -> None:
    """Revert migration."""
    op.drop_index(op.f('ix_task_execution_logs_started_at'), table_name='task_execution_logs')
    op.drop_index(op.f('ix_task_execution_logs_task_id'), table_name='task_execution_logs')
    op.drop_index('ix_task_logs_pair_interval', table_name='task_execution_logs')
    op.drop_index('ix_task_logs_task_started', table_name='task_execution_logs')
    op.drop_table('task_execution_logs')
