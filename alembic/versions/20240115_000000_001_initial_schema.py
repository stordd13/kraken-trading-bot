"""Initial database schema with TimescaleDB support.

Revision ID: 001
Revises:
Create Date: 2024-01-15 00:00:00.000000

This migration:
1. Creates the TimescaleDB extension
2. Creates all tables (market_data_ohlc, market_data_ticks, trades_history, bot_state)
3. Converts market_data_ohlc to a TimescaleDB hypertable
4. Creates all necessary indexes
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - Create initial schema."""
    # ==========================================================================
    # 1. Enable TimescaleDB extension
    # ==========================================================================
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # ==========================================================================
    # 2. Create market_data_ohlc table
    # ==========================================================================
    op.create_table(
        "market_data_ohlc",
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Candle open timestamp (UTC)",
        ),
        sa.Column(
            "pair",
            sa.String(20),
            nullable=False,
            comment="Trading pair (e.g., XBT/EUR)",
        ),
        sa.Column(
            "interval",
            sa.Integer(),
            nullable=False,
            comment="Candle interval in minutes",
        ),
        sa.Column(
            "open",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Opening price",
        ),
        sa.Column(
            "high",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Highest price during interval",
        ),
        sa.Column(
            "low",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Lowest price during interval",
        ),
        sa.Column(
            "close",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Closing price",
        ),
        sa.Column(
            "volume",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Total volume traded during interval",
        ),
        sa.Column(
            "vwap",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Volume-weighted average price",
        ),
        sa.Column(
            "trades_count",
            sa.Integer(),
            nullable=True,
            comment="Number of trades during interval",
        ),
        sa.PrimaryKeyConstraint("timestamp", "pair", "interval"),
        comment="OHLC candlestick data (TimescaleDB hypertable)",
    )

    # Create indexes for OHLC table
    op.create_index(
        "ix_ohlc_pair_timestamp",
        "market_data_ohlc",
        ["pair", "timestamp"],
    )
    op.create_index(
        "ix_ohlc_timestamp_desc",
        "market_data_ohlc",
        [sa.text("timestamp DESC")],
    )

    # Convert to TimescaleDB hypertable
    op.execute("""
        SELECT create_hypertable(
            'market_data_ohlc',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        )
    """)

    # ==========================================================================
    # 3. Create market_data_ticks table
    # ==========================================================================
    op.create_table(
        "market_data_ticks",
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Tick timestamp (UTC)",
        ),
        sa.Column(
            "pair",
            sa.String(20),
            nullable=False,
            comment="Trading pair",
        ),
        sa.Column(
            "sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Sequence number for multiple trades at same timestamp",
        ),
        sa.Column(
            "price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Trade price",
        ),
        sa.Column(
            "volume",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Trade volume",
        ),
        sa.Column(
            "side",
            sa.String(10),
            nullable=False,
            comment="Trade side (buy/sell)",
        ),
        sa.Column(
            "trade_id",
            sa.String(50),
            nullable=True,
            comment="Exchange trade ID",
        ),
        sa.PrimaryKeyConstraint("timestamp", "pair", "sequence"),
        comment="Individual trade tick data",
    )

    # Create indexes for ticks table
    op.create_index(
        "ix_ticks_pair_timestamp",
        "market_data_ticks",
        ["pair", "timestamp"],
    )
    op.create_index(
        "ix_ticks_timestamp_desc",
        "market_data_ticks",
        [sa.text("timestamp DESC")],
    )

    # ==========================================================================
    # 4. Create trades_history table
    # ==========================================================================
    op.create_table(
        "trades_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Unique trade identifier",
        ),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Trade execution timestamp (UTC)",
        ),
        sa.Column(
            "pair",
            sa.String(20),
            nullable=False,
            comment="Trading pair (e.g., XBT/EUR)",
        ),
        sa.Column(
            "side",
            sa.String(10),
            nullable=False,
            comment="Trade side (buy/sell)",
        ),
        sa.Column(
            "amount",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Trade amount in base currency",
        ),
        sa.Column(
            "price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            comment="Execution price",
        ),
        sa.Column(
            "fee",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Trading fee",
        ),
        sa.Column(
            "fee_currency",
            sa.String(10),
            nullable=False,
            server_default="'EUR'",
            comment="Currency of the fee",
        ),
        sa.Column(
            "strategy",
            sa.String(50),
            nullable=False,
            comment="Strategy name",
        ),
        sa.Column(
            "pnl",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Profit/Loss (calculated on sell)",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="'pending'",
            comment="Trade status",
        ),
        sa.Column(
            "order_id",
            sa.String(100),
            nullable=True,
            comment="Exchange order ID",
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Additional notes",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Record creation timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Historical trade records",
    )

    # Create indexes for trades_history table
    op.create_index("ix_trades_history_timestamp", "trades_history", ["timestamp"])
    op.create_index("ix_trades_history_pair", "trades_history", ["pair"])
    op.create_index("ix_trades_history_side", "trades_history", ["side"])
    op.create_index("ix_trades_history_strategy", "trades_history", ["strategy"])
    op.create_index("ix_trades_history_status", "trades_history", ["status"])
    op.create_index(
        "ix_trades_pair_timestamp",
        "trades_history",
        ["pair", "timestamp"],
    )
    op.create_index(
        "ix_trades_strategy_timestamp",
        "trades_history",
        ["strategy", "timestamp"],
    )
    op.create_index(
        "ix_trades_status_timestamp",
        "trades_history",
        ["status", "timestamp"],
    )

    # ==========================================================================
    # 5. Create bot_state table
    # ==========================================================================
    op.create_table(
        "bot_state",
        sa.Column(
            "bot_id",
            sa.String(50),
            nullable=False,
            comment="Unique bot identifier",
        ),
        sa.Column(
            "strategy",
            sa.String(50),
            nullable=False,
            comment="Strategy name",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="'initializing'",
            comment="Bot status",
        ),
        sa.Column(
            "position_size",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Current position size in base currency",
        ),
        sa.Column(
            "entry_price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Average entry price",
        ),
        sa.Column(
            "daily_pnl",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Daily realized P&L",
        ),
        sa.Column(
            "total_pnl",
            sa.DECIMAL(precision=18, scale=8),
            nullable=False,
            server_default="0",
            comment="Total realized P&L",
        ),
        sa.Column(
            "daily_trades_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of trades today",
        ),
        sa.Column(
            "last_signal_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Last signal timestamp",
        ),
        sa.Column(
            "last_trade_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Last trade timestamp",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Last error message",
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Last update timestamp",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Bot creation timestamp",
        ),
        sa.PrimaryKeyConstraint("bot_id"),
        comment="Persistent bot state and positions",
    )

    # Create indexes for bot_state table
    op.create_index("ix_bot_state_status", "bot_state", ["status"])
    op.create_index("ix_bot_state_strategy", "bot_state", ["strategy"])


def downgrade() -> None:
    """Revert migration - Drop all tables."""
    # Drop tables in reverse order (respecting dependencies)
    op.drop_table("bot_state")
    op.drop_table("trades_history")
    op.drop_table("market_data_ticks")
    op.drop_table("market_data_ohlc")

    # Note: We don't drop the TimescaleDB extension as other databases might use it
