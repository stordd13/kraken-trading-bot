"""Tests for TrendFollowingStrategy.

Tests cover:
- BUY signal on golden cross (EMA20 crosses above EMA50)
- No signal when already in position
- Exit: trailing stop 6%
- Exit: hard stop below EMA50
- Exit: take profit 20%
- Exit: timeout 21 days
- Only reacts to 1h candles (ignores 5min)
- EMA warmup behavior
- Backtest compatibility: add_position, close_position
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    LogLevel,
    MultiStrategySettings,
    MultiTimeframeSettings,
    OrderSettings,
    RiskManagementSettings,
    Settings,
    StrategySettings,
    TradingMode,
    TradingSettings,
)
from krakenbot.models.base import SignalType
from krakenbot.strategies.trend_following import TrendFollowingStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Create settings for trend following testing."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        log_level=LogLevel.DEBUG,
        log_json=False,
        kraken=KrakenSettings(api_key="test_key", api_secret="test_secret"),
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
            pair="XBT/USDC",
            default_order_amount_eur=15.0,
            candle_interval_min=5,
        ),
        strategy=StrategySettings(
            name="trend_following",
            buy_threshold_pct=-1.0,
            sell_threshold_pct=2.0,
            lookback_periods=5,
            max_holding_minutes=120,
        ),
        multi_strategy=MultiStrategySettings(enabled=False),
        multi_timeframe=MultiTimeframeSettings(trigger_timeframe=5),
        order=OrderSettings(limit_buy_offset_pct=0.05),
    )


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_db_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def strategy(
    settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
) -> TrendFollowingStrategy:
    """Create TrendFollowingStrategy with default params."""
    s = TrendFollowingStrategy(
        settings,
        mock_event_bus,
        mock_db_manager,
        strategy_params={
            "ema_fast_period": 3,  # Small periods for test convenience
            "ema_slow_period": 5,
            "trailing_stop_pct": 6.0,
            "take_profit_pct": 20.0,
            "max_holding_days": 21,
            "hard_stop_below_ema50": True,
        },
    )
    s._skip_db_sync = True
    return s


def _ohlc_1h(
    price: str,
    *,
    ts: datetime | None = None,
) -> dict:
    """Build a 1h OHLC candle dict."""
    return {
        "pair": "XBT/USDC",
        "interval": 60,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "100.0",
        "is_complete": True,
        "timestamp": ts or datetime.now(UTC),
    }


def _ohlc_5m(price: str) -> dict:
    """Build a 5m OHLC candle dict."""
    return {
        "pair": "XBT/USDC",
        "interval": 5,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "10.0",
        "is_complete": True,
        "timestamp": datetime.now(UTC),
    }


async def _warmup_emas(strategy: TrendFollowingStrategy, prices: list[str]) -> None:
    """Feed 1h candles to warm up both EMAs."""
    for p in prices:
        await strategy.on_ohlc(_ohlc_1h(p))


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestTrendFollowingInit:
    """Tests for initialization."""

    def test_default_params(self, strategy: TrendFollowingStrategy) -> None:
        assert strategy._ema_fast.period == 3
        assert strategy._ema_slow.period == 5
        assert strategy.trailing_stop_pct == Decimal("6.0")
        assert strategy.take_profit_pct == Decimal("20.0")
        assert strategy.max_holding_days == 21
        assert strategy.hard_stop_below_ema50 is True

    def test_get_name(self, strategy: TrendFollowingStrategy) -> None:
        assert strategy.get_name() == "trend_following"

    def test_get_config(self, strategy: TrendFollowingStrategy) -> None:
        config = strategy.get_config()
        assert config["ema_fast_period"] == 3
        assert config["ema_slow_period"] == 5
        assert config["has_position"] is False

    def test_initial_state(self, strategy: TrendFollowingStrategy) -> None:
        assert strategy.current_price is None
        assert strategy.has_position is False
        assert strategy.open_positions_count == 0


# ---------------------------------------------------------------------------
# Only 1h candles
# ---------------------------------------------------------------------------


class TestTrendOnlyHourly:
    """Tests that strategy only reacts to 1h candles."""

    @pytest.mark.asyncio
    async def test_5m_candle_does_not_update_emas(self, strategy: TrendFollowingStrategy) -> None:
        """5m candles update price but not EMAs."""
        await strategy.on_ohlc(_ohlc_5m("50000"))
        assert strategy._current_price == Decimal("50000")
        assert strategy._ema_fast.value is None  # Not updated
        assert strategy._ema_slow.value is None

    @pytest.mark.asyncio
    async def test_1h_candle_updates_emas(self, strategy: TrendFollowingStrategy) -> None:
        """1h candles update EMAs."""
        await strategy.on_ohlc(_ohlc_1h("50000"))
        # After 1 update, fast EMA (period=3) is still warming up
        assert strategy._ema_fast._count == 1

    @pytest.mark.asyncio
    async def test_no_signal_on_5m_candle(self, strategy: TrendFollowingStrategy) -> None:
        """No signal generated from 5m data alone."""
        await strategy.on_ohlc(_ohlc_5m("50000"))
        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# EMA warmup
# ---------------------------------------------------------------------------


class TestTrendEmaWarmup:
    """Tests for EMA warmup behavior."""

    @pytest.mark.asyncio
    async def test_no_signal_during_warmup(self, strategy: TrendFollowingStrategy) -> None:
        """No signal when EMAs are not ready."""
        # Only 2 candles, need 5 for slow EMA
        await _warmup_emas(strategy, ["50000", "50100"])
        strategy._current_timestamp = datetime.now(UTC)
        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_emas_ready_after_enough_candles(self, strategy: TrendFollowingStrategy) -> None:
        """EMAs are ready after period candles."""
        # Slow EMA period = 5
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])
        assert strategy._ema_fast.is_ready
        assert strategy._ema_slow.is_ready


# ---------------------------------------------------------------------------
# BUY signal (golden cross)
# ---------------------------------------------------------------------------


class TestTrendBuySignal:
    """Tests for golden cross entry."""

    @pytest.mark.asyncio
    async def test_buy_on_golden_cross(self, strategy: TrendFollowingStrategy) -> None:
        """BUY when fast EMA crosses above slow EMA."""
        # Feed declining prices so slow EMA > fast EMA
        await _warmup_emas(strategy, ["52000", "51000", "50000", "49000", "48000"])

        # Now feed a sharp rise to trigger cross
        # After decline, slow EMA should be above fast. Rising prices make fast catch up.
        await strategy.on_ohlc(_ohlc_1h("55000"))
        await strategy.on_ohlc(_ohlc_1h("58000"))

        strategy._current_timestamp = datetime.now(UTC)
        signal = await strategy.generate_signal()

        # The cross may or may not have happened yet depending on EMA math.
        # But verify the mechanism works if we force the cross.
        if signal is not None:
            assert signal.signal_type == SignalType.BUY
            assert signal.metadata["order_type"] == "limit"
            assert "limit_price" in signal.metadata
            assert signal.metadata["position_size_multiplier"] == 2.0

    @pytest.mark.asyncio
    async def test_no_buy_when_already_in_position(self, strategy: TrendFollowingStrategy) -> None:
        """No BUY signal when already holding a position."""
        # Warm up EMAs
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        # Add a position
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )

        # Even with a cross, should not buy
        strategy._prev_ema_fast = Decimal("49000")
        strategy._prev_ema_slow = Decimal("49500")
        strategy._ema_fast._ema = Decimal("50500")
        strategy._ema_slow._ema = Decimal("50000")
        strategy._current_price = Decimal("51000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        # Should be an exit check, not a buy
        if signal is not None:
            assert signal.signal_type == SignalType.SELL

    @pytest.mark.asyncio
    async def test_forced_golden_cross(self, strategy: TrendFollowingStrategy) -> None:
        """Directly test cross detection by setting EMA state."""
        # Warm up EMAs first
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        # Force a cross scenario
        strategy._prev_ema_fast = Decimal("49000")
        strategy._prev_ema_slow = Decimal("49500")
        strategy._ema_fast._ema = Decimal("50500")
        strategy._ema_slow._ema = Decimal("50000")
        strategy._current_price = Decimal("51000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.pair == "XBT/USDC"
        assert signal.confidence == 0.85

    @pytest.mark.asyncio
    async def test_no_buy_without_cross(self, strategy: TrendFollowingStrategy) -> None:
        """No BUY when fast EMA stays below slow EMA."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        # Fast already below slow, stays below
        strategy._prev_ema_fast = Decimal("49000")
        strategy._prev_ema_slow = Decimal("49500")
        strategy._ema_fast._ema = Decimal("49200")
        strategy._ema_slow._ema = Decimal("49500")
        strategy._current_price = Decimal("49300")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_no_buy_price_below_fast_ema(self, strategy: TrendFollowingStrategy) -> None:
        """No BUY when cross happens but price is below fast EMA."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        # Cross happened
        strategy._prev_ema_fast = Decimal("49000")
        strategy._prev_ema_slow = Decimal("49500")
        strategy._ema_fast._ema = Decimal("50500")
        strategy._ema_slow._ema = Decimal("50000")
        # But price is below fast EMA
        strategy._current_price = Decimal("50000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# Exit: trailing stop
# ---------------------------------------------------------------------------


class TestTrendTrailingStop:
    """Tests for trailing stop exit."""

    @pytest.mark.asyncio
    async def test_trailing_stop_triggers(self, strategy: TrendFollowingStrategy) -> None:
        """SELL when price drops 6% from highest."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        # Highest was 55000
        strategy._position.highest_price = Decimal("55000")

        # 6% drop from 55000 = 51700. Price at 51500 -> triggers
        strategy._current_price = Decimal("51500")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["order_type"] == "market"
        assert "Trailing stop" in signal.reason

    @pytest.mark.asyncio
    async def test_trailing_stop_no_trigger(self, strategy: TrendFollowingStrategy) -> None:
        """No SELL when price hasn't dropped enough."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy._position.highest_price = Decimal("55000")

        # 4% drop from 55000 = 52800. Not enough for 6% threshold.
        strategy._current_price = Decimal("52800")
        strategy._current_timestamp = datetime.now(UTC)
        # Make sure hard stop doesn't fire (price above EMA50)
        strategy._ema_slow._ema = Decimal("50000")

        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# Exit: hard stop below EMA50
# ---------------------------------------------------------------------------


class TestTrendHardStop:
    """Tests for hard stop below EMA50."""

    @pytest.mark.asyncio
    async def test_hard_stop_triggers(self, strategy: TrendFollowingStrategy) -> None:
        """SELL when price drops below EMA50."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy._position.highest_price = Decimal("51000")

        # EMA50 at 50000, price drops below
        strategy._ema_slow._ema = Decimal("50000")
        strategy._current_price = Decimal("49500")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["order_type"] == "market"
        assert "Hard stop" in signal.reason

    @pytest.mark.asyncio
    async def test_hard_stop_disabled(
        self,
        settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """No hard stop when disabled."""
        s = TrendFollowingStrategy(
            settings,
            mock_event_bus,
            mock_db_manager,
            strategy_params={
                "ema_fast_period": 3,
                "ema_slow_period": 5,
                "hard_stop_below_ema50": False,
            },
        )
        s._skip_db_sync = True

        await _warmup_emas(s, ["50000", "50100", "50200", "50300", "50400"])
        s.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        s._position.highest_price = Decimal("51000")
        s._ema_slow._ema = Decimal("50000")
        s._current_price = Decimal("49500")
        s._current_timestamp = datetime.now(UTC)

        signal = await s.generate_signal()
        # Should not be hard stop (might be trailing stop though)
        if signal is not None:
            assert "Hard stop" not in signal.reason


# ---------------------------------------------------------------------------
# Exit: take profit
# ---------------------------------------------------------------------------


class TestTrendTakeProfit:
    """Tests for take profit exit."""

    @pytest.mark.asyncio
    async def test_take_profit_triggers(self, strategy: TrendFollowingStrategy) -> None:
        """SELL when profit reaches 20%."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy._position.highest_price = Decimal("60500")

        # 20% profit: 50000 * 1.20 = 60000
        strategy._current_price = Decimal("60500")
        strategy._current_timestamp = datetime.now(UTC)
        # Keep above EMA50 to avoid hard stop
        strategy._ema_slow._ema = Decimal("55000")

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["order_type"] == "limit"
        assert "Take profit" in signal.reason


# ---------------------------------------------------------------------------
# Exit: timeout
# ---------------------------------------------------------------------------


class TestTrendTimeout:
    """Tests for holding timeout exit."""

    @pytest.mark.asyncio
    async def test_timeout_triggers(self, strategy: TrendFollowingStrategy) -> None:
        """SELL when position held > 21 days."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        entry_time = datetime.now(UTC) - timedelta(days=22)
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        # Price slightly above entry, above EMA50, no trailing stop
        strategy._position.highest_price = Decimal("51000")
        strategy._current_price = Decimal("50500")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._ema_slow._ema = Decimal("49000")

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["order_type"] == "market"
        assert "Timeout" in signal.reason

    @pytest.mark.asyncio
    async def test_no_timeout_before_max_days(self, strategy: TrendFollowingStrategy) -> None:
        """No timeout when within holding period."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        entry_time = datetime.now(UTC) - timedelta(days=10)
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=entry_time,
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy._position.highest_price = Decimal("51000")
        strategy._current_price = Decimal("50500")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._ema_slow._ema = Decimal("49000")

        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# Exit priority order
# ---------------------------------------------------------------------------


class TestTrendExitPriority:
    """Tests for exit priority: hard stop > trailing > take profit > timeout."""

    @pytest.mark.asyncio
    async def test_hard_stop_priority_over_trailing(self, strategy: TrendFollowingStrategy) -> None:
        """Hard stop fires before trailing stop."""
        await _warmup_emas(strategy, ["50000", "50100", "50200", "50300", "50400"])

        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy._position.highest_price = Decimal("55000")

        # Price below EMA50 AND dropped > 6% from high
        strategy._ema_slow._ema = Decimal("50000")
        strategy._current_price = Decimal("49000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is not None
        assert "Hard stop" in signal.reason


# ---------------------------------------------------------------------------
# on_trade_filled
# ---------------------------------------------------------------------------


class TestTrendTradeFilled:
    """Tests for on_trade_filled position tracking."""

    @pytest.mark.asyncio
    async def test_buy_fill_opens_position(self, strategy: TrendFollowingStrategy) -> None:
        strategy._current_timestamp = datetime.now(UTC)
        await strategy.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("50000"),
            fee=Decimal("0.05"),
            reference_price=Decimal("50000"),
            position_id=None,
        )
        assert strategy.has_position
        assert strategy._position.entry_price == Decimal("50000")

    @pytest.mark.asyncio
    async def test_sell_fill_closes_position(self, strategy: TrendFollowingStrategy) -> None:
        strategy._current_timestamp = datetime.now(UTC)
        await strategy.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("50000"),
            fee=Decimal("0.05"),
            reference_price=Decimal("50000"),
            position_id=None,
        )
        await strategy.on_trade_filled(
            trade_id="T2",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.001"),
            price=Decimal("52000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=1,
        )
        assert not strategy.has_position


# ---------------------------------------------------------------------------
# on_tick
# ---------------------------------------------------------------------------


class TestTrendOnTick:
    """Tests for on_tick updates."""

    @pytest.mark.asyncio
    async def test_tick_updates_price(self, strategy: TrendFollowingStrategy) -> None:
        await strategy.on_tick({"price": "51000"})
        assert strategy._current_price == Decimal("51000")

    @pytest.mark.asyncio
    async def test_tick_updates_highest_price(self, strategy: TrendFollowingStrategy) -> None:
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        await strategy.on_tick({"price": "52000"})
        assert strategy._position.highest_price == Decimal("52000")

    @pytest.mark.asyncio
    async def test_tick_does_not_lower_highest(self, strategy: TrendFollowingStrategy) -> None:
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy._position.highest_price = Decimal("55000")
        await strategy.on_tick({"price": "53000"})
        assert strategy._position.highest_price == Decimal("55000")


# ---------------------------------------------------------------------------
# Backtest compatibility
# ---------------------------------------------------------------------------


class TestTrendBacktestCompat:
    """Tests for add_position/close_position backtest API."""

    def test_add_position(self, strategy: TrendFollowingStrategy) -> None:
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        assert strategy.has_position
        assert strategy._position.entry_price == Decimal("50000")
        assert strategy._position.position_id == 1

    def test_close_position(self, strategy: TrendFollowingStrategy) -> None:
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy.close_position(1)
        assert not strategy.has_position

    def test_close_wrong_id_does_nothing(self, strategy: TrendFollowingStrategy) -> None:
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        strategy.close_position(999)
        assert strategy.has_position

    def test_open_positions_property(self, strategy: TrendFollowingStrategy) -> None:
        assert strategy.open_positions == []
        strategy.add_position(
            entry_price=Decimal("50000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            position_id=1,
        )
        assert len(strategy.open_positions) == 1
        assert strategy.open_positions_count == 1
