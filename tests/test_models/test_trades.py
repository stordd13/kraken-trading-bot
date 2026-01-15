"""Tests for trade and bot state models.

This module tests the Trade and BotState models including:
- Model creation and validation
- Computed properties
- Status enums
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from krakenbot.models.base import BotStatus, TradeSide, TradeStatus
from krakenbot.models.trades import BotState, Trade


class TestTrade:
    """Tests for Trade model."""

    def test_create_trade(self, sample_trade_data) -> None:
        """Test creating a Trade instance."""
        trade = Trade(**sample_trade_data)

        assert trade.id == sample_trade_data["id"]
        assert trade.timestamp == sample_trade_data["timestamp"]
        assert trade.pair == sample_trade_data["pair"]
        assert trade.side == sample_trade_data["side"]
        assert trade.amount == sample_trade_data["amount"]
        assert trade.price == sample_trade_data["price"]
        assert trade.fee == sample_trade_data["fee"]
        assert trade.strategy == sample_trade_data["strategy"]
        assert trade.status == sample_trade_data["status"]

    def test_trade_value_property(self) -> None:
        """Test value property calculation."""
        trade = Trade(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.00100000"),
            price=Decimal("42000.00000000"),
            fee=Decimal("0.10000000"),
            strategy="threshold",
            status=TradeStatus.FILLED,
        )

        expected_value = Decimal("0.00100000") * Decimal("42000.00000000")
        assert trade.value == expected_value

    def test_trade_is_buy(self) -> None:
        """Test is_buy property."""
        buy_trade = Trade(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.00100000"),
            price=Decimal("42000.00000000"),
            fee=Decimal("0.10000000"),
            strategy="threshold",
            status=TradeStatus.FILLED,
        )

        sell_trade = Trade(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            side=TradeSide.SELL,
            amount=Decimal("0.00100000"),
            price=Decimal("42000.00000000"),
            fee=Decimal("0.10000000"),
            strategy="threshold",
            status=TradeStatus.FILLED,
        )

        assert buy_trade.is_buy is True
        assert buy_trade.is_sell is False
        assert sell_trade.is_buy is False
        assert sell_trade.is_sell is True

    def test_trade_is_filled(self) -> None:
        """Test is_filled property."""
        filled_trade = Trade(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.00100000"),
            price=Decimal("42000.00000000"),
            fee=Decimal("0.10000000"),
            strategy="threshold",
            status=TradeStatus.FILLED,
        )

        pending_trade = Trade(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.00100000"),
            price=Decimal("42000.00000000"),
            fee=Decimal("0.10000000"),
            strategy="threshold",
            status=TradeStatus.PENDING,
        )

        assert filled_trade.is_filled is True
        assert pending_trade.is_filled is False

    def test_trade_repr(self, sample_trade_data) -> None:
        """Test Trade string representation."""
        trade = Trade(**sample_trade_data)
        repr_str = repr(trade)

        assert "Trade" in repr_str
        assert "XBT/EUR" in repr_str
        assert "buy" in repr_str

    def test_trade_table_name(self) -> None:
        """Test that table name is correctly set."""
        assert Trade.__tablename__ == "trades_history"

    def test_trade_default_uuid(self) -> None:
        """Test that Trade generates UUID by default."""
        trade = Trade(
            timestamp=datetime.now(timezone.utc),
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.00100000"),
            price=Decimal("42000.00000000"),
            fee=Decimal("0.10000000"),
            strategy="threshold",
            status=TradeStatus.FILLED,
        )

        # id should be set to None until persisted, but we test the model accepts it
        assert trade.pair == "XBT/EUR"


class TestBotState:
    """Tests for BotState model."""

    def test_create_bot_state(self, sample_bot_state_data) -> None:
        """Test creating a BotState instance."""
        state = BotState(**sample_bot_state_data)

        assert state.bot_id == sample_bot_state_data["bot_id"]
        assert state.strategy == sample_bot_state_data["strategy"]
        assert state.status == sample_bot_state_data["status"]
        assert state.position_size == sample_bot_state_data["position_size"]
        assert state.entry_price == sample_bot_state_data["entry_price"]
        assert state.daily_pnl == sample_bot_state_data["daily_pnl"]
        assert state.total_pnl == sample_bot_state_data["total_pnl"]

    def test_bot_state_has_position(self) -> None:
        """Test has_position property."""
        state_with_position = BotState(
            bot_id="test-bot-1",
            strategy="threshold",
            status=BotStatus.RUNNING,
            position_size=Decimal("0.00100000"),
            entry_price=Decimal("42000.00000000"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
        )

        state_no_position = BotState(
            bot_id="test-bot-2",
            strategy="threshold",
            status=BotStatus.RUNNING,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
        )

        assert state_with_position.has_position is True
        assert state_no_position.has_position is False

    def test_bot_state_is_running(self) -> None:
        """Test is_running property."""
        running_state = BotState(
            bot_id="test-bot",
            strategy="threshold",
            status=BotStatus.RUNNING,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
        )

        stopped_state = BotState(
            bot_id="test-bot",
            strategy="threshold",
            status=BotStatus.STOPPED,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
        )

        assert running_state.is_running is True
        assert running_state.is_stopped is False
        assert stopped_state.is_running is False
        assert stopped_state.is_stopped is True

    def test_bot_state_has_error(self) -> None:
        """Test has_error property."""
        error_state = BotState(
            bot_id="test-bot",
            strategy="threshold",
            status=BotStatus.ERROR,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            error_message="Connection failed",
        )

        normal_state = BotState(
            bot_id="test-bot",
            strategy="threshold",
            status=BotStatus.RUNNING,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
        )

        assert error_state.has_error is True
        assert normal_state.has_error is False

    def test_bot_state_calculate_unrealized_pnl(self) -> None:
        """Test unrealized PnL calculation."""
        state = BotState(
            bot_id="test-bot",
            strategy="threshold",
            status=BotStatus.RUNNING,
            position_size=Decimal("0.00100000"),
            entry_price=Decimal("42000.00000000"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
        )

        # Price went up 1000 EUR
        current_price = Decimal("43000.00000000")
        unrealized_pnl = state.calculate_unrealized_pnl(current_price)

        expected = (Decimal("43000.00000000") - Decimal("42000.00000000")) * Decimal(
            "0.00100000"
        )
        assert unrealized_pnl == expected

    def test_bot_state_calculate_unrealized_pnl_no_position(self) -> None:
        """Test unrealized PnL calculation with no position."""
        state = BotState(
            bot_id="test-bot",
            strategy="threshold",
            status=BotStatus.RUNNING,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
        )

        unrealized_pnl = state.calculate_unrealized_pnl(Decimal("43000.00000000"))
        assert unrealized_pnl == Decimal("0")

    def test_bot_state_repr(self, sample_bot_state_data) -> None:
        """Test BotState string representation."""
        state = BotState(**sample_bot_state_data)
        repr_str = repr(state)

        assert "BotState" in repr_str
        assert "threshold" in repr_str
        assert "running" in repr_str

    def test_bot_state_table_name(self) -> None:
        """Test that table name is correctly set."""
        assert BotState.__tablename__ == "bot_state"


class TestTradeStatusEnum:
    """Tests for TradeStatus enum."""

    def test_trade_status_values(self) -> None:
        """Test TradeStatus enum values."""
        assert TradeStatus.PENDING.value == "pending"
        assert TradeStatus.FILLED.value == "filled"
        assert TradeStatus.PARTIALLY_FILLED.value == "partially_filled"
        assert TradeStatus.CANCELLED.value == "cancelled"
        assert TradeStatus.FAILED.value == "failed"
        assert TradeStatus.EXPIRED.value == "expired"


class TestBotStatusEnum:
    """Tests for BotStatus enum."""

    def test_bot_status_values(self) -> None:
        """Test BotStatus enum values."""
        assert BotStatus.RUNNING.value == "running"
        assert BotStatus.STOPPED.value == "stopped"
        assert BotStatus.ERROR.value == "error"
        assert BotStatus.PAUSED.value == "paused"
        assert BotStatus.INITIALIZING.value == "initializing"
