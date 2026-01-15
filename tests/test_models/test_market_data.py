"""Tests for market data models.

This module tests the OHLCData and TickData models including:
- Model creation and validation
- Computed properties
- Index definitions
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData, TickData


class TestOHLCData:
    """Tests for OHLCData model."""

    def test_create_ohlc_data(self, sample_ohlc_data) -> None:
        """Test creating an OHLCData instance."""
        data = sample_ohlc_data[0]
        ohlc = OHLCData(**data)

        assert ohlc.timestamp == data["timestamp"]
        assert ohlc.pair == data["pair"]
        assert ohlc.interval == data["interval"]
        assert ohlc.open == data["open"]
        assert ohlc.high == data["high"]
        assert ohlc.low == data["low"]
        assert ohlc.close == data["close"]
        assert ohlc.volume == data["volume"]

    def test_ohlc_price_change(self) -> None:
        """Test price_change property calculation."""
        ohlc = OHLCData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            interval=15,
            open=Decimal("42000.00000000"),
            high=Decimal("42500.00000000"),
            low=Decimal("41800.00000000"),
            close=Decimal("42300.00000000"),
            volume=Decimal("10.00000000"),
        )

        assert ohlc.price_change == Decimal("300.00000000")

    def test_ohlc_price_change_negative(self) -> None:
        """Test price_change property with negative change."""
        ohlc = OHLCData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            interval=15,
            open=Decimal("42000.00000000"),
            high=Decimal("42500.00000000"),
            low=Decimal("41800.00000000"),
            close=Decimal("41900.00000000"),
            volume=Decimal("10.00000000"),
        )

        assert ohlc.price_change == Decimal("-100.00000000")

    def test_ohlc_price_change_pct(self) -> None:
        """Test price_change_pct property calculation."""
        ohlc = OHLCData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            interval=15,
            open=Decimal("42000.00000000"),
            high=Decimal("42500.00000000"),
            low=Decimal("41800.00000000"),
            close=Decimal("42420.00000000"),  # +1% change
            volume=Decimal("10.00000000"),
        )

        assert ohlc.price_change_pct == Decimal("1")

    def test_ohlc_price_change_pct_zero_open(self) -> None:
        """Test price_change_pct handles zero open price."""
        ohlc = OHLCData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            interval=15,
            open=Decimal("0"),
            high=Decimal("42500.00000000"),
            low=Decimal("0"),
            close=Decimal("42300.00000000"),
            volume=Decimal("10.00000000"),
        )

        assert ohlc.price_change_pct == Decimal("0")

    def test_ohlc_is_bullish(self) -> None:
        """Test is_bullish property."""
        ohlc_bullish = OHLCData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            interval=15,
            open=Decimal("42000.00000000"),
            high=Decimal("42500.00000000"),
            low=Decimal("41800.00000000"),
            close=Decimal("42300.00000000"),
            volume=Decimal("10.00000000"),
        )

        ohlc_bearish = OHLCData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            interval=15,
            open=Decimal("42000.00000000"),
            high=Decimal("42500.00000000"),
            low=Decimal("41800.00000000"),
            close=Decimal("41900.00000000"),
            volume=Decimal("10.00000000"),
        )

        assert ohlc_bullish.is_bullish is True
        assert ohlc_bullish.is_bearish is False
        assert ohlc_bearish.is_bullish is False
        assert ohlc_bearish.is_bearish is True

    def test_ohlc_repr(self, sample_ohlc_data) -> None:
        """Test OHLCData string representation."""
        ohlc = OHLCData(**sample_ohlc_data[0])
        repr_str = repr(ohlc)

        assert "OHLCData" in repr_str
        assert "XBT/EUR" in repr_str
        assert "42000" in repr_str

    def test_ohlc_table_name(self) -> None:
        """Test that table name is correctly set."""
        assert OHLCData.__tablename__ == "market_data_ohlc"


class TestTickData:
    """Tests for TickData model."""

    def test_create_tick_data(self, sample_tick_data) -> None:
        """Test creating a TickData instance."""
        data = sample_tick_data[0]
        tick = TickData(**data)

        assert tick.timestamp == data["timestamp"]
        assert tick.pair == data["pair"]
        assert tick.price == data["price"]
        assert tick.volume == data["volume"]
        assert tick.side == data["side"]

    def test_tick_value_property(self) -> None:
        """Test value property calculation."""
        tick = TickData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            sequence=0,
            price=Decimal("42000.00000000"),
            volume=Decimal("0.10000000"),
            side=TradeSide.BUY,
        )

        expected_value = Decimal("42000.00000000") * Decimal("0.10000000")
        assert tick.value == expected_value

    def test_tick_repr(self, sample_tick_data) -> None:
        """Test TickData string representation."""
        tick = TickData(**sample_tick_data[0])
        repr_str = repr(tick)

        assert "TickData" in repr_str
        assert "XBT/EUR" in repr_str
        assert "42000" in repr_str
        assert "buy" in repr_str

    def test_tick_table_name(self) -> None:
        """Test that table name is correctly set."""
        assert TickData.__tablename__ == "market_data_ticks"

    def test_tick_with_trade_id(self) -> None:
        """Test TickData with optional trade_id."""
        tick = TickData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            sequence=0,
            price=Decimal("42000.00000000"),
            volume=Decimal("0.10000000"),
            side=TradeSide.BUY,
            trade_id="TRADE-12345",
        )

        assert tick.trade_id == "TRADE-12345"

    def test_tick_without_trade_id(self) -> None:
        """Test TickData without trade_id."""
        tick = TickData(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            sequence=0,
            price=Decimal("42000.00000000"),
            volume=Decimal("0.10000000"),
            side=TradeSide.BUY,
        )

        assert tick.trade_id is None


class TestTradeSideEnum:
    """Tests for TradeSide enum."""

    def test_trade_side_values(self) -> None:
        """Test TradeSide enum values."""
        assert TradeSide.BUY.value == "buy"
        assert TradeSide.SELL.value == "sell"

    def test_trade_side_from_string(self) -> None:
        """Test creating TradeSide from string."""
        assert TradeSide("buy") == TradeSide.BUY
        assert TradeSide("sell") == TradeSide.SELL
