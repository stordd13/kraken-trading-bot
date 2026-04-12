"""Market data models for OHLC and tick data.

This module defines the database models for storing market data:
- OHLCData: Candlestick data (hypertable for TimescaleDB)
- TickData: Individual trade ticks
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, TIMESTAMP, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from krakenbot.core.database import Base
from krakenbot.models.base import TradeSide


class OHLCData(Base):
    """OHLC (Open-High-Low-Close) candlestick data model.

    This table stores candlestick data from the Kraken exchange.
    It is designed to be converted to a TimescaleDB hypertable
    for efficient time-series storage and queries.

    Attributes:
        timestamp: Candle open timestamp (UTC, primary key).
        pair: Trading pair (e.g., "XBT/EUR").
        interval: Candle interval in minutes.
        open: Opening price.
        high: Highest price during interval.
        low: Lowest price during interval.
        close: Closing price.
        volume: Total volume traded during interval.
        vwap: Volume-weighted average price.
        trades_count: Number of trades during interval.
    """

    __tablename__ = "market_data_ohlc"

    # Primary key: composite of timestamp, pair, and interval
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        primary_key=True,
        nullable=False,
        comment="Candle open timestamp (UTC)",
    )
    pair: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
        comment="Trading pair (e.g., XBT/EUR)",
    )
    interval: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        nullable=False,
        comment="Candle interval in minutes",
    )
    exchange: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
        default="kraken",
        server_default="kraken",
        comment="Exchange source (kraken, binance)",
    )

    # OHLC values
    open: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Opening price",
    )
    high: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Highest price during interval",
    )
    low: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Lowest price during interval",
    )
    close: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Closing price",
    )

    # Volume and additional data
    volume: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        default=Decimal("0"),
        comment="Total volume traded during interval",
    )
    vwap: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=True,
        comment="Volume-weighted average price",
    )
    trades_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of trades during interval",
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_ohlc_pair_timestamp", "pair", "timestamp"),
        Index("ix_ohlc_timestamp_desc", timestamp.desc()),
        {
            "comment": "OHLC candlestick data (TimescaleDB hypertable)",
        },
    )

    def __repr__(self) -> str:
        """Return string representation of OHLC data."""
        return (
            f"OHLCData(timestamp={self.timestamp!r}, pair={self.pair!r}, "
            f"interval={self.interval}, exchange={self.exchange!r}, "
            f"OHLC=({self.open}, {self.high}, {self.low}, {self.close}), "
            f"volume={self.volume})"
        )

    @property
    def price_change(self) -> Decimal:
        """Calculate price change (close - open).

        Returns:
            Price change as Decimal.
        """
        return self.close - self.open

    @property
    def price_change_pct(self) -> Decimal:
        """Calculate price change as percentage.

        Returns:
            Price change percentage.
        """
        if self.open == 0:
            return Decimal("0")
        return ((self.close - self.open) / self.open) * 100

    @property
    def is_bullish(self) -> bool:
        """Check if candle is bullish (close > open).

        Returns:
            True if bullish.
        """
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """Check if candle is bearish (close < open).

        Returns:
            True if bearish.
        """
        return self.close < self.open


class TickData(Base):
    """Individual trade tick data model.

    This table stores individual trade ticks from the exchange.
    Useful for detailed analysis and strategy backtesting.

    Attributes:
        timestamp: Tick timestamp (UTC, primary key with pair).
        pair: Trading pair.
        price: Trade price.
        volume: Trade volume.
        side: Trade side (buy or sell).
        trade_id: Exchange trade ID (if available).
    """

    __tablename__ = "market_data_ticks"

    # Primary key: composite of timestamp and pair (with microsecond precision)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        primary_key=True,
        nullable=False,
        comment="Tick timestamp (UTC)",
    )
    pair: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
        comment="Trading pair",
    )
    # Use trade_id as part of primary key to handle multiple trades at same timestamp
    sequence: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        nullable=False,
        default=0,
        comment="Sequence number for multiple trades at same timestamp",
    )

    # Trade data
    price: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Trade price",
    )
    volume: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Trade volume",
    )
    side: Mapped[TradeSide] = mapped_column(
        Enum(TradeSide, native_enum=False, length=10),
        nullable=False,
        comment="Trade side (buy/sell)",
    )

    # Optional exchange metadata
    trade_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Exchange trade ID",
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_ticks_pair_timestamp", "pair", "timestamp"),
        Index("ix_ticks_timestamp_desc", timestamp.desc()),
        {
            "comment": "Individual trade tick data",
        },
    )

    def __repr__(self) -> str:
        """Return string representation of tick data."""
        return (
            f"TickData(timestamp={self.timestamp!r}, pair={self.pair!r}, "
            f"price={self.price}, volume={self.volume}, side={self.side.value})"
        )

    @property
    def value(self) -> Decimal:
        """Calculate trade value (price * volume).

        Returns:
            Trade value as Decimal.
        """
        return self.price * self.volume
