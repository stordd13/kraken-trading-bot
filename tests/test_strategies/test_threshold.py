"""Tests for threshold strategy module.

This module tests the ThresholdStrategy including:
- Tick processing and price updates
- OHLC processing and history building
- Signal generation for BUY, SELL, and HOLD
- Position state management
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    LogLevel,
    RiskManagementSettings,
    Settings,
    StrategySettings,
    TradingMode,
    TradingSettings,
)
from krakenbot.core.event_bus import EventBus
from krakenbot.models.base import SignalType
from krakenbot.models.trades import BotState
from krakenbot.strategies.threshold import ThresholdStrategy


@pytest.fixture
def threshold_settings() -> Settings:
    """Create settings for threshold strategy testing."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        log_level=LogLevel.DEBUG,
        log_json=False,
        kraken=KrakenSettings(
            api_key="test_key",
            api_secret="test_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/test",
            echo=False,
            pool_size=2,
            max_overflow=2,
        ),
        risk=RiskManagementSettings(
            max_position_pct=5.0,
            daily_loss_limit_eur=50.0,
            max_open_positions=3,
            min_trade_interval_sec=60,
            emergency_stop_loss_pct=10.0,
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="XBT/EUR",
            default_order_amount_eur=15.0,
            candle_interval_min=15,
        ),
        strategy=StrategySettings(
            name="threshold",
            buy_threshold_pct=-1.0,
            sell_threshold_pct=2.0,
            lookback_periods=5,  # Smaller for testing
        ),
    )


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    """Create mock event bus."""
    bus = AsyncMock(spec=EventBus)
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create mock database manager with read_session."""
    manager = MagicMock()

    @asynccontextmanager
    async def mock_read_session() -> AsyncGenerator[AsyncMock, None]:
        session = AsyncMock()
        session.execute = AsyncMock()
        yield session

    manager.read_session = mock_read_session
    return manager


@pytest.fixture
def strategy(
    threshold_settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
) -> ThresholdStrategy:
    """Create threshold strategy for testing."""
    return ThresholdStrategy(threshold_settings, mock_event_bus, mock_db_manager)


class TestThresholdStrategyInitialization:
    """Tests for ThresholdStrategy initialization."""

    def test_initialization(self, strategy: ThresholdStrategy) -> None:
        """Test strategy initializes with correct config."""
        assert strategy.buy_threshold_pct == -1.0
        assert strategy.sell_threshold_pct == 2.0
        assert strategy.lookback_periods == 5
        assert strategy.pair == "XBT/EUR"

    def test_initial_state(self, strategy: ThresholdStrategy) -> None:
        """Test strategy initial internal state."""
        assert strategy.current_price is None
        assert strategy.reference_price is None
        assert strategy.price_history_len == 0
        assert strategy.has_position is False
        assert strategy.entry_price is None

    def test_get_name(self, strategy: ThresholdStrategy) -> None:
        """Test strategy name."""
        assert strategy.get_name() == "threshold"

    def test_get_config(self, strategy: ThresholdStrategy) -> None:
        """Test strategy config retrieval."""
        config = strategy.get_config()

        assert config["name"] == "threshold"
        assert config["buy_threshold_pct"] == -1.0
        assert config["sell_threshold_pct"] == 2.0
        assert config["lookback_periods"] == 5
        assert config["pair"] == "XBT/EUR"


class TestThresholdStrategyOnTick:
    """Tests for on_tick method."""

    @pytest.mark.asyncio
    async def test_on_tick_updates_price(self, strategy: ThresholdStrategy) -> None:
        """Test on_tick updates current price."""
        tick_data = {
            "timestamp": datetime.now(timezone.utc),
            "pair": "XBT/EUR",
            "price": "42000.00",
            "volume": "0.5",
            "side": "buy",
        }

        await strategy.on_tick(tick_data)

        assert strategy.current_price == Decimal("42000.00")

    @pytest.mark.asyncio
    async def test_on_tick_ignores_other_pairs(
        self,
        strategy: ThresholdStrategy,
    ) -> None:
        """Test on_tick ignores ticks for other pairs."""
        tick_data = {
            "timestamp": datetime.now(timezone.utc),
            "pair": "ETH/EUR",  # Different pair
            "price": "2500.00",
            "volume": "1.0",
            "side": "buy",
        }

        await strategy.on_tick(tick_data)

        assert strategy.current_price is None

    @pytest.mark.asyncio
    async def test_on_tick_handles_string_price(
        self,
        strategy: ThresholdStrategy,
    ) -> None:
        """Test on_tick handles string prices correctly."""
        tick_data = {
            "pair": "XBT/EUR",
            "price": "42123.45678901",
        }

        await strategy.on_tick(tick_data)

        assert strategy.current_price == Decimal("42123.45678901")


class TestThresholdStrategyOnOhlc:
    """Tests for on_ohlc method."""

    @pytest.mark.asyncio
    async def test_on_ohlc_builds_history(self, strategy: ThresholdStrategy) -> None:
        """Test on_ohlc builds price history."""
        ohlc_data = {
            "timestamp": datetime.now(timezone.utc),
            "pair": "XBT/EUR",
            "open": "42000.00",
            "high": "42500.00",
            "low": "41800.00",
            "close": "42300.00",
            "volume": "10.5",
        }

        await strategy.on_ohlc(ohlc_data)

        assert strategy.price_history_len == 1

    @pytest.mark.asyncio
    async def test_on_ohlc_calculates_reference_price(
        self,
        strategy: ThresholdStrategy,
    ) -> None:
        """Test on_ohlc calculates reference price after enough data."""
        # Add enough OHLC data to fill lookback period (5)
        prices = [
            Decimal("42000"),
            Decimal("42100"),
            Decimal("42200"),
            Decimal("42300"),
            Decimal("42400"),
        ]

        for i, price in enumerate(prices):
            ohlc_data = {
                "timestamp": datetime.now(timezone.utc),
                "pair": "XBT/EUR",
                "open": str(price),
                "high": str(price + 100),
                "low": str(price - 100),
                "close": str(price),
                "volume": "10.0",
            }
            await strategy.on_ohlc(ohlc_data)

        # Reference should be average of all prices
        expected_reference = sum(prices) / len(prices)
        assert strategy.reference_price == expected_reference

    @pytest.mark.asyncio
    async def test_on_ohlc_no_reference_before_lookback(
        self,
        strategy: ThresholdStrategy,
    ) -> None:
        """Test on_ohlc doesn't calculate reference before enough data."""
        # Add fewer OHLC data than lookback period (5)
        for i in range(3):
            ohlc_data = {
                "pair": "XBT/EUR",
                "close": "42000.00",
            }
            await strategy.on_ohlc(ohlc_data)

        assert strategy.reference_price is None

    @pytest.mark.asyncio
    async def test_on_ohlc_ignores_other_pairs(
        self,
        strategy: ThresholdStrategy,
    ) -> None:
        """Test on_ohlc ignores data for other pairs."""
        ohlc_data = {
            "pair": "ETH/EUR",  # Different pair
            "close": "2500.00",
        }

        await strategy.on_ohlc(ohlc_data)

        assert strategy.price_history_len == 0

    @pytest.mark.asyncio
    async def test_on_ohlc_maintains_lookback_window(
        self,
        strategy: ThresholdStrategy,
    ) -> None:
        """Test on_ohlc maintains fixed lookback window size."""
        # Add more data than lookback period (5)
        for i in range(10):
            ohlc_data = {
                "pair": "XBT/EUR",
                "close": str(42000 + i * 100),
            }
            await strategy.on_ohlc(ohlc_data)

        # Should only keep last 5
        assert strategy.price_history_len == 5


class TestThresholdStrategyGenerateSignal:
    """Tests for generate_signal method."""

    @pytest.fixture
    def strategy_no_db(
        self,
        threshold_settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> ThresholdStrategy:
        """Create strategy with mocked _update_position_state."""
        strategy = ThresholdStrategy(threshold_settings, mock_event_bus, mock_db_manager)
        # Mock the db call to not interfere with our test state
        strategy._update_position_state = AsyncMock()
        return strategy

    @pytest.mark.asyncio
    async def test_generate_signal_returns_none_without_price(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test generate_signal returns None without current price."""
        strategy_no_db._reference_price = Decimal("42000")
        # current_price is None

        signal = await strategy_no_db.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_generate_signal_returns_none_without_reference(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test generate_signal returns None without reference price."""
        strategy_no_db._current_price = Decimal("42000")
        # reference_price is None

        signal = await strategy_no_db.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_generate_buy_signal_on_price_drop(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test BUY signal when price drops below threshold."""
        # Set up state: no position, price dropped -1.5% vs reference
        strategy_no_db._reference_price = Decimal("42000")
        strategy_no_db._current_price = Decimal("41370")  # -1.5% drop
        strategy_no_db._has_position = False
        strategy_no_db._entry_price = None

        signal = await strategy_no_db.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.pair == "XBT/EUR"
        assert signal.price == Decimal("41370")
        assert signal.confidence == 0.8
        assert "Price drop detected" in signal.reason
        assert signal.metadata["reference_price"] == 42000.0

    @pytest.mark.asyncio
    async def test_no_buy_signal_insufficient_drop(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test no BUY signal when drop is insufficient."""
        # Price only dropped -0.5% (threshold is -1%)
        strategy_no_db._reference_price = Decimal("42000")
        strategy_no_db._current_price = Decimal("41790")  # -0.5% drop
        strategy_no_db._has_position = False

        signal = await strategy_no_db.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_no_buy_signal_when_has_position(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test no BUY signal when already has position."""
        # Price dropped enough, but already have position
        strategy_no_db._reference_price = Decimal("42000")
        strategy_no_db._current_price = Decimal("41370")  # -1.5% drop
        strategy_no_db._has_position = True
        strategy_no_db._entry_price = Decimal("41500")

        signal = await strategy_no_db.generate_signal()

        # Should not generate BUY, but might generate SELL if profit target met
        # In this case, price is lower than entry, so HOLD
        assert signal is not None
        assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_generate_sell_signal_on_profit_target(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test SELL signal when profit target reached."""
        # Set up state: has position, price rose +2.5% vs entry
        strategy_no_db._reference_price = Decimal("42000")
        strategy_no_db._current_price = Decimal("41025")  # +2.5% vs entry of 40000
        strategy_no_db._has_position = True
        strategy_no_db._entry_price = Decimal("40000")

        signal = await strategy_no_db.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.pair == "XBT/EUR"
        assert signal.price == Decimal("41025")
        assert "Profit target reached" in signal.reason
        assert signal.metadata["entry_price"] == 40000.0

    @pytest.mark.asyncio
    async def test_no_sell_signal_insufficient_profit(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test no SELL signal when profit target not reached."""
        # Price only rose +1% (threshold is +2%)
        strategy_no_db._reference_price = Decimal("42000")
        strategy_no_db._current_price = Decimal("40400")  # +1% vs entry
        strategy_no_db._has_position = True
        strategy_no_db._entry_price = Decimal("40000")

        signal = await strategy_no_db.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_generate_hold_signal_no_conditions(
        self,
        strategy_no_db: ThresholdStrategy,
    ) -> None:
        """Test HOLD signal when no conditions are met."""
        # No position, but price hasn't dropped enough
        strategy_no_db._reference_price = Decimal("42000")
        strategy_no_db._current_price = Decimal("42100")  # Price up
        strategy_no_db._has_position = False

        signal = await strategy_no_db.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.HOLD
        assert signal.reason == "No trading conditions met"
        assert signal.confidence == 1.0


class TestThresholdStrategyPositionState:
    """Tests for position state management."""

    @pytest.mark.asyncio
    async def test_update_position_state_with_position(
        self,
        threshold_settings: Settings,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test _update_position_state loads position from DB."""
        # Create mock that returns a BotState with position
        mock_bot_state = MagicMock(spec=BotState)
        mock_bot_state.has_position = True
        mock_bot_state.entry_price = Decimal("41500.00")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_bot_state

        # Create mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_read_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        mock_db_manager = MagicMock()
        mock_db_manager.read_session = mock_read_session

        strategy = ThresholdStrategy(
            threshold_settings,
            mock_event_bus,
            mock_db_manager,
        )

        await strategy._update_position_state()

        assert strategy.has_position is True
        assert strategy.entry_price == Decimal("41500.00")

    @pytest.mark.asyncio
    async def test_update_position_state_no_position(
        self,
        threshold_settings: Settings,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test _update_position_state when no bot state exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def mock_read_session() -> AsyncGenerator[AsyncMock, None]:
            yield mock_session

        mock_db_manager = MagicMock()
        mock_db_manager.read_session = mock_read_session

        strategy = ThresholdStrategy(
            threshold_settings,
            mock_event_bus,
            mock_db_manager,
        )

        await strategy._update_position_state()

        assert strategy.has_position is False
        assert strategy.entry_price is None

    @pytest.mark.asyncio
    async def test_update_position_state_handles_error(
        self,
        threshold_settings: Settings,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test _update_position_state handles database errors gracefully."""

        @asynccontextmanager
        async def failing_read_session() -> AsyncGenerator[AsyncMock, None]:
            raise Exception("Database connection failed")
            yield AsyncMock()  # noqa: B901

        mock_db_manager = MagicMock()
        mock_db_manager.read_session = failing_read_session

        strategy = ThresholdStrategy(
            threshold_settings,
            mock_event_bus,
            mock_db_manager,
        )

        # Set some state that should be preserved on error
        strategy._has_position = True
        strategy._entry_price = Decimal("40000")

        # Should not raise
        await strategy._update_position_state()

        # State should be preserved (not reset)
        assert strategy.has_position is True
        assert strategy.entry_price == Decimal("40000")


class TestThresholdStrategyStateManagement:
    """Tests for strategy state management methods."""

    def test_set_position_state(self, strategy: ThresholdStrategy) -> None:
        """Test setting position state directly (for testing)."""
        strategy.set_position_state(
            has_position=True,
            entry_price=Decimal("41000.00"),
        )

        assert strategy.has_position is True
        assert strategy.entry_price == Decimal("41000.00")

    def test_set_position_state_no_position(self, strategy: ThresholdStrategy) -> None:
        """Test setting no position state."""
        strategy.set_position_state(has_position=False)

        assert strategy.has_position is False
        assert strategy.entry_price is None

    def test_reset_state(self, strategy: ThresholdStrategy) -> None:
        """Test resetting strategy state."""
        # Set up some state
        strategy._price_history = [Decimal("42000"), Decimal("42100")]
        strategy._current_price = Decimal("42200")
        strategy._reference_price = Decimal("42050")
        strategy._has_position = True
        strategy._entry_price = Decimal("41500")

        strategy.reset_state()

        assert strategy.price_history_len == 0
        assert strategy.current_price is None
        assert strategy.reference_price is None
        assert strategy.has_position is False
        assert strategy.entry_price is None


class TestThresholdStrategyIntegration:
    """Integration tests for full strategy flow."""

    @pytest.fixture
    def strategy_no_db(
        self,
        threshold_settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> ThresholdStrategy:
        """Create strategy with mocked _update_position_state."""
        strategy = ThresholdStrategy(threshold_settings, mock_event_bus, mock_db_manager)
        # Mock the db call to not interfere with our test state
        strategy._update_position_state = AsyncMock()
        return strategy

    @pytest.mark.asyncio
    async def test_full_buy_flow(self, strategy_no_db: ThresholdStrategy) -> None:
        """Test complete flow from data to BUY signal."""
        # Build up price history with stable prices
        for i in range(5):
            ohlc_data = {
                "pair": "XBT/EUR",
                "close": "42000.00",
            }
            await strategy_no_db.on_ohlc(ohlc_data)

        # Price drops via tick
        tick_data = {
            "pair": "XBT/EUR",
            "price": "41500.00",  # -1.19% drop
        }
        await strategy_no_db.on_tick(tick_data)

        # Ensure no position
        strategy_no_db.set_position_state(has_position=False)

        # Generate signal
        signal = await strategy_no_db.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    @pytest.mark.asyncio
    async def test_full_sell_flow(self, strategy_no_db: ThresholdStrategy) -> None:
        """Test complete flow from data to SELL signal."""
        # Build up price history
        for i in range(5):
            ohlc_data = {
                "pair": "XBT/EUR",
                "close": "42000.00",
            }
            await strategy_no_db.on_ohlc(ohlc_data)

        # Current price is above entry by +2.5%
        tick_data = {
            "pair": "XBT/EUR",
            "price": "41000.00",  # +2.5% vs entry of 40000
        }
        await strategy_no_db.on_tick(tick_data)

        # Set position with entry price
        strategy_no_db.set_position_state(
            has_position=True,
            entry_price=Decimal("40000.00"),
        )

        # Generate signal
        signal = await strategy_no_db.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL

    @pytest.mark.asyncio
    async def test_moving_average_updates(self, strategy: ThresholdStrategy) -> None:
        """Test moving average updates as new data comes in."""
        prices = [42000, 42100, 42200, 42300, 42400, 42500]

        for i, price in enumerate(prices):
            ohlc_data = {
                "pair": "XBT/EUR",
                "close": str(price),
            }
            await strategy.on_ohlc(ohlc_data)

            if i >= 4:  # After lookback period (5)
                # Reference should be average of last 5 prices
                expected = sum(Decimal(str(p)) for p in prices[i - 4 : i + 1]) / 5
                assert strategy.reference_price == expected
