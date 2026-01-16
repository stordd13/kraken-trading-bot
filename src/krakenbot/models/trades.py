"""Trade and bot state models.

This module defines the database models for:
- Trade: Historical trade records
- BotState: Persistent bot state and positions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DECIMAL, TIMESTAMP, Enum, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from krakenbot.core.database import Base
from krakenbot.models.base import BotStatus, TradeSide, TradeStatus

if TYPE_CHECKING:
    pass


def utc_now() -> datetime:
    """Get current UTC datetime.

    Returns:
        Current datetime with UTC timezone.
    """
    return datetime.now(timezone.utc)


class Trade(Base):
    """Historical trade record model.

    This table stores all trades executed by the bot, including
    paper trades and live trades.

    Attributes:
        id: Unique trade identifier (UUID).
        timestamp: Trade execution timestamp.
        pair: Trading pair.
        side: Trade side (buy/sell).
        amount: Trade amount in base currency.
        price: Execution price.
        fee: Trading fee.
        fee_currency: Currency of the fee.
        strategy: Strategy name that generated the trade.
        pnl: Profit/Loss for this trade (calculated on sell).
        status: Trade status.
        order_id: Exchange order ID (if live trade).
        notes: Additional notes or metadata.
        created_at: Record creation timestamp.
    """

    __tablename__ = "trades_history"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique trade identifier",
    )

    # Trade details
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
        comment="Trade execution timestamp (UTC)",
    )
    pair: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Trading pair (e.g., XBT/EUR)",
    )
    side: Mapped[TradeSide] = mapped_column(
        Enum(TradeSide, native_enum=False, length=10),
        nullable=False,
        index=True,
        comment="Trade side (buy/sell)",
    )
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Trade amount in base currency",
    )
    price: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Execution price",
    )
    fee: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        default=Decimal("0"),
        comment="Trading fee",
    )
    fee_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="EUR",
        comment="Currency of the fee",
    )

    # Strategy and P&L
    strategy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Strategy name",
    )
    pnl: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=True,
        comment="Profit/Loss (calculated on sell)",
    )

    # Status and exchange info
    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus, native_enum=False, length=20),
        nullable=False,
        default=TradeStatus.PENDING,
        index=True,
        comment="Trade status",
    )
    order_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Exchange order ID",
    )

    # Metadata
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Additional notes",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        comment="Record creation timestamp",
    )

    # Indexes
    __table_args__ = (
        Index("ix_trades_pair_timestamp", "pair", "timestamp"),
        Index("ix_trades_strategy_timestamp", "strategy", "timestamp"),
        Index("ix_trades_status_timestamp", "status", "timestamp"),
        {
            "comment": "Historical trade records",
        },
    )

    def __repr__(self) -> str:
        """Return string representation of trade."""
        return (
            f"Trade(id={self.id!r}, pair={self.pair!r}, "
            f"side={self.side.value}, amount={self.amount}, "
            f"price={self.price}, status={self.status.value})"
        )

    @property
    def value(self) -> Decimal:
        """Calculate trade value (amount * price).

        Returns:
            Trade value in quote currency.
        """
        return self.amount * self.price

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy trade.

        Returns:
            True if buy.
        """
        return self.side == TradeSide.BUY

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell trade.

        Returns:
            True if sell.
        """
        return self.side == TradeSide.SELL

    @property
    def is_filled(self) -> bool:
        """Check if trade is filled.

        Returns:
            True if filled.
        """
        return self.status == TradeStatus.FILLED


class BotState(Base):
    """Persistent bot state model.

    This table stores the current state of each trading bot,
    including position information and P&L tracking.

    Attributes:
        bot_id: Unique bot identifier.
        strategy: Strategy name.
        status: Bot status.
        last_signal_at: Timestamp of last signal.
        last_trade_at: Timestamp of last trade.
        position_size: Current position size in base currency.
        entry_price: Average entry price of current position.
        daily_pnl: Realized P&L for current day (resets at midnight UTC).
        total_pnl: Total realized P&L.
        daily_trades_count: Number of trades today.
        error_message: Last error message (if status is ERROR).
        updated_at: Last update timestamp.
        created_at: Bot creation timestamp.
    """

    __tablename__ = "bot_state"

    # Primary key
    bot_id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        comment="Unique bot identifier",
    )

    # Strategy and status
    strategy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Strategy name",
    )
    status: Mapped[BotStatus] = mapped_column(
        Enum(BotStatus, native_enum=False, length=20),
        nullable=False,
        default=BotStatus.INITIALIZING,
        index=True,
        comment="Bot status",
    )

    # Position information
    position_size: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        default=Decimal("0"),
        comment="Current position size in base currency",
    )
    entry_price: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=True,
        comment="Average entry price",
    )

    # P&L tracking
    daily_pnl: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        default=Decimal("0"),
        comment="Daily realized P&L",
    )
    total_pnl: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        default=Decimal("0"),
        comment="Total realized P&L",
    )

    # Activity tracking
    daily_trades_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Number of trades today",
    )
    last_signal_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Last signal timestamp",
    )
    last_trade_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Last trade timestamp",
    )

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message",
    )

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        comment="Last update timestamp",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        comment="Bot creation timestamp",
    )

    # Indexes
    __table_args__ = (
        Index("ix_bot_state_status", "status"),
        Index("ix_bot_state_strategy", "strategy"),
        {
            "comment": "Persistent bot state and positions",
        },
    )

    def __repr__(self) -> str:
        """Return string representation of bot state."""
        return (
            f"BotState(bot_id={self.bot_id!r}, strategy={self.strategy!r}, "
            f"status={self.status.value}, position_size={self.position_size}, "
            f"daily_pnl={self.daily_pnl}, total_pnl={self.total_pnl})"
        )

    @property
    def has_position(self) -> bool:
        """Check if bot has an open position.

        Returns:
            True if position_size > 0.
        """
        return self.position_size > Decimal("0")

    @property
    def is_running(self) -> bool:
        """Check if bot is running.

        Returns:
            True if status is RUNNING.
        """
        return self.status == BotStatus.RUNNING

    @property
    def is_stopped(self) -> bool:
        """Check if bot is stopped.

        Returns:
            True if status is STOPPED.
        """
        return self.status == BotStatus.STOPPED

    @property
    def has_error(self) -> bool:
        """Check if bot has an error.

        Returns:
            True if status is ERROR.
        """
        return self.status == BotStatus.ERROR

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L based on current price.

        Args:
            current_price: Current market price.

        Returns:
            Unrealized P&L amount.
        """
        if not self.has_position or self.entry_price is None:
            return Decimal("0")
        return (current_price - self.entry_price) * self.position_size


class BacktestRun(Base):
    """Backtest run results model.

    This table stores the results of strategy backtests for
    visualization and comparison.

    Attributes:
        id: Unique backtest run identifier (UUID).
        run_name: Human-readable name for this backtest.
        strategy: Strategy name that was tested.
        pair: Trading pair used in backtest.
        start_time: Backtest period start.
        end_time: Backtest period end.
        starting_balance: Initial balance.
        ending_balance: Final balance.
        total_trades: Number of trades executed.
        winning_trades: Number of winning trades.
        losing_trades: Number of losing trades.
        win_rate: Win rate (0-1).
        total_pnl: Total profit/loss.
        total_fees: Total fees paid.
        net_pnl: Net profit/loss (total_pnl - total_fees).
        total_return_pct: Total return percentage.
        max_drawdown: Maximum drawdown amount.
        max_drawdown_pct: Maximum drawdown percentage.
        sharpe_ratio: Sharpe ratio.
        profit_factor: Profit factor (total_wins / total_losses).
        average_win: Average winning trade amount.
        average_loss: Average losing trade amount.
        created_at: When this backtest was run.
    """

    __tablename__ = "backtest_runs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique backtest run identifier",
    )

    # Backtest metadata
    run_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable backtest name",
    )
    strategy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Strategy name",
    )
    pair: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Trading pair (e.g., XBT/USDC)",
    )

    # Time period
    start_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
        comment="Backtest period start (UTC)",
    )
    end_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="Backtest period end (UTC)",
    )

    # Balance metrics
    starting_balance: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Initial balance",
    )
    ending_balance: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Final balance",
    )

    # Trade statistics
    total_trades: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Total number of trades",
    )
    winning_trades: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Number of winning trades",
    )
    losing_trades: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Number of losing trades",
    )
    win_rate: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=5, scale=4),
        nullable=False,
        default=Decimal("0"),
        comment="Win rate (0-1)",
    )

    # P&L metrics
    total_pnl: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Total profit/loss",
    )
    total_fees: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Total fees paid",
    )
    net_pnl: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Net profit/loss (total_pnl - total_fees)",
    )
    total_return_pct: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=10, scale=4),
        nullable=False,
        comment="Total return percentage",
    )

    # Risk metrics
    max_drawdown: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Maximum drawdown amount",
    )
    max_drawdown_pct: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=10, scale=4),
        nullable=False,
        comment="Maximum drawdown percentage",
    )
    sharpe_ratio: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=10, scale=4),
        nullable=False,
        comment="Sharpe ratio",
    )
    profit_factor: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=10, scale=4),
        nullable=False,
        comment="Profit factor (total_wins / total_losses)",
    )
    average_win: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Average winning trade amount",
    )
    average_loss: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Average losing trade amount",
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
        comment="When this backtest was run",
    )

    # Indexes
    __table_args__ = (
        Index("ix_backtest_runs_strategy_created", "strategy", "created_at"),
        Index("ix_backtest_runs_pair_created", "pair", "created_at"),
        {
            "comment": "Backtest run results for strategy analysis",
        },
    )

    def __repr__(self) -> str:
        """Return string representation of backtest run."""
        return (
            f"BacktestRun(id={self.id!r}, run_name={self.run_name!r}, "
            f"strategy={self.strategy!r}, pair={self.pair!r}, "
            f"net_pnl={self.net_pnl}, total_return_pct={self.total_return_pct})"
        )
