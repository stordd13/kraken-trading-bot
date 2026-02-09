"""Base model definitions and common types.

This module provides shared types, enums, and mixins used across
all database models in the application.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from sqlalchemy import DECIMAL, TIMESTAMP, String
from sqlalchemy.orm import mapped_column

# Custom type annotations for SQLAlchemy columns
# Decimal type for monetary values (18 digits total, 8 decimal places)
DecimalMoney = Annotated[
    Decimal,
    mapped_column(DECIMAL(precision=18, scale=8), nullable=False),
]

# Decimal type for monetary values that can be null
DecimalMoneyNullable = Annotated[
    Decimal | None,
    mapped_column(DECIMAL(precision=18, scale=8), nullable=True),
]

# Timestamp type for all datetime columns (UTC)
TimestampUTC = Annotated[
    datetime,
    mapped_column(TIMESTAMP(timezone=True), nullable=False),
]

# Timestamp type that can be null
TimestampUTCNullable = Annotated[
    datetime | None,
    mapped_column(TIMESTAMP(timezone=True), nullable=True),
]

# Trading pair string (e.g., "XBT/EUR")
TradingPair = Annotated[
    str,
    mapped_column(String(20), nullable=False, index=True),
]

# Strategy name string
StrategyName = Annotated[
    str,
    mapped_column(String(50), nullable=False, index=True),
]


class TradeSide(str, Enum):
    """Side of a trade (buy or sell).

    Attributes:
        BUY: A buy/long order.
        SELL: A sell/short order.
    """

    BUY = "buy"
    SELL = "sell"


class TradeStatus(str, Enum):
    """Status of a trade order.

    Attributes:
        PENDING: Order submitted but not yet filled.
        FILLED: Order completely filled.
        PARTIALLY_FILLED: Order partially filled.
        CANCELLED: Order cancelled by user or system.
        FAILED: Order failed due to error.
        EXPIRED: Order expired without filling.
    """

    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"


class BotStatus(str, Enum):
    """Status of a trading bot.

    Attributes:
        RUNNING: Bot is actively trading.
        STOPPED: Bot is stopped (manual or planned).
        ERROR: Bot stopped due to error.
        PAUSED: Bot is temporarily paused.
        INITIALIZING: Bot is starting up.
    """

    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    PAUSED = "paused"
    INITIALIZING = "initializing"


class SignalType(str, Enum):
    """Type of trading signal.

    Attributes:
        BUY: Signal to enter a long position.
        SELL: Signal to exit a long position.
        HOLD: Signal to maintain current position.
    """

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class PositionStatus(str, Enum):
    """Status of an open position.

    Attributes:
        OPEN: Position is currently active.
        CLOSED: Position has been closed (sold).
        CANCELLED: Position was cancelled before execution.
    """

    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
