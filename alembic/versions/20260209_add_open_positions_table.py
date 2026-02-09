"""add_open_positions_table

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-02-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add open_positions table for multi-position tracking."""
    op.create_table(
        "open_positions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Unique position identifier",
        ),
        sa.Column(
            "bot_id",
            sa.String(100),
            nullable=False,
            comment="Bot instance identifier (strategy_name + instance_id)",
        ),
        sa.Column(
            "strategy",
            sa.String(50),
            nullable=False,
            comment="Strategy name",
        ),
        sa.Column(
            "position_id",
            sa.Integer(),
            nullable=False,
            comment="Strategy-assigned position ID (unique per bot)",
        ),
        sa.Column(
            "pair",
            sa.String(20),
            nullable=False,
            comment="Trading pair",
        ),
        sa.Column(
            "entry_price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Entry price",
        ),
        sa.Column(
            "amount_btc",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Position size in base currency",
        ),
        sa.Column(
            "reference_price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Reference price that triggered entry",
        ),
        sa.Column(
            "entry_time",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Position entry timestamp",
        ),
        sa.Column(
            "entry_trade_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="FK to trades_history (BUY trade)",
        ),
        sa.Column(
            "exit_trade_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="FK to trades_history (SELL trade)",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
            comment="Position status (open, closed, cancelled)",
        ),
        sa.Column(
            "closed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Position close timestamp",
        ),
        sa.Column(
            "pnl",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Realized P&L on close",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Record creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        comment="Open positions for multi-position strategies",
    )

    # Create indexes
    op.create_index("ix_open_positions_bot_id", "open_positions", ["bot_id"])
    op.create_index("ix_open_positions_strategy", "open_positions", ["strategy"])
    op.create_index("ix_open_positions_pair", "open_positions", ["pair"])
    op.create_index("ix_open_positions_status", "open_positions", ["status"])
    op.create_index(
        "ix_open_positions_bot_status", "open_positions", ["bot_id", "status"]
    )
    op.create_index(
        "ix_open_positions_bot_position", "open_positions", ["bot_id", "position_id"]
    )


def downgrade() -> None:
    """Remove open_positions table."""
    op.drop_index("ix_open_positions_bot_position", table_name="open_positions")
    op.drop_index("ix_open_positions_bot_status", table_name="open_positions")
    op.drop_index("ix_open_positions_status", table_name="open_positions")
    op.drop_index("ix_open_positions_pair", table_name="open_positions")
    op.drop_index("ix_open_positions_strategy", table_name="open_positions")
    op.drop_index("ix_open_positions_bot_id", table_name="open_positions")
    op.drop_table("open_positions")
