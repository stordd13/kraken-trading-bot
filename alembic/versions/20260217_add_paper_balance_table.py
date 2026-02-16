"""add paper_balance table

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-02-17 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add paper_balance table for persistent paper trading balance."""
    op.create_table(
        "paper_balance",
        sa.Column(
            "currency",
            sa.String(20),
            primary_key=True,
            comment="Currency symbol (e.g., USDC, BTC)",
        ),
        sa.Column(
            "amount",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Current paper balance",
        ),
        sa.Column(
            "initial_amount",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Initial real balance snapshot from Kraken",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Record creation timestamp",
        ),
        comment="Persistent paper trading balance with initial snapshot",
    )


def downgrade() -> None:
    """Remove paper_balance table."""
    op.drop_table("paper_balance")
