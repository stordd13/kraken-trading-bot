"""add_trading_mode_columns

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-02-16 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add trading_mode column to open_positions, trades_history, and orders."""
    op.add_column(
        "open_positions",
        sa.Column(
            "trading_mode",
            sa.String(10),
            nullable=False,
            server_default="spot",
            comment="Trading mode: spot or margin",
        ),
    )
    op.add_column(
        "trades_history",
        sa.Column(
            "trading_mode",
            sa.String(10),
            nullable=False,
            server_default="spot",
            comment="Trading mode: spot or margin",
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "trading_mode",
            sa.String(10),
            nullable=False,
            server_default="spot",
            comment="Trading mode: spot or margin",
        ),
    )


def downgrade() -> None:
    """Remove trading_mode columns."""
    op.drop_column("orders", "trading_mode")
    op.drop_column("trades_history", "trading_mode")
    op.drop_column("open_positions", "trading_mode")
