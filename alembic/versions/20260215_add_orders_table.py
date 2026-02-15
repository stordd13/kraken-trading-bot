"""add_orders_table

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-02-15 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add orders table for limit order lifecycle tracking."""
    op.create_table(
        "orders",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Unique order identifier (internal)",
        ),
        sa.Column(
            "order_id",
            sa.String(100),
            nullable=False,
            unique=True,
            comment="Exchange order ID (Kraken ID or paper-xxx)",
        ),
        sa.Column(
            "bot_id",
            sa.String(100),
            nullable=False,
            comment="Bot instance identifier",
        ),
        sa.Column(
            "pair",
            sa.String(20),
            nullable=False,
            comment="Trading pair (e.g., XBT/USDC)",
        ),
        sa.Column(
            "side",
            sa.String(10),
            nullable=False,
            comment="Order side (buy/sell)",
        ),
        sa.Column(
            "order_type",
            sa.String(10),
            nullable=False,
            server_default="limit",
            comment="Order type (market/limit)",
        ),
        sa.Column(
            "amount",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Requested order amount in base currency",
        ),
        sa.Column(
            "price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Limit price (None for market orders)",
        ),
        sa.Column(
            "filled_amount",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Amount filled so far",
        ),
        sa.Column(
            "filled_price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Average fill price",
        ),
        sa.Column(
            "fee",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Total fees paid",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="Current order status",
        ),
        sa.Column(
            "strategy",
            sa.String(50),
            nullable=False,
            comment="Strategy name that placed this order",
        ),
        sa.Column(
            "signal_metadata",
            sa.JSON(),
            nullable=True,
            comment="JSON metadata from the trading signal",
        ),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="When the order should be auto-cancelled",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Order creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        comment="Limit order tracking for lifecycle management",
    )

    # Individual indexes
    op.create_index("ix_orders_order_id", "orders", ["order_id"], unique=True)
    op.create_index("ix_orders_bot_id", "orders", ["bot_id"])
    op.create_index("ix_orders_pair", "orders", ["pair"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_strategy", "orders", ["strategy"])

    # Composite indexes
    op.create_index("ix_orders_bot_status", "orders", ["bot_id", "status"])
    op.create_index("ix_orders_status_expires", "orders", ["status", "expires_at"])


def downgrade() -> None:
    """Remove orders table."""
    op.drop_index("ix_orders_status_expires", table_name="orders")
    op.drop_index("ix_orders_bot_status", table_name="orders")
    op.drop_index("ix_orders_strategy", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_pair", table_name="orders")
    op.drop_index("ix_orders_bot_id", table_name="orders")
    op.drop_index("ix_orders_order_id", table_name="orders")
    op.drop_table("orders")
