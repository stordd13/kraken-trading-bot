"""Tests for bear short strategy module.

This module tests the BearShortStrategy including:
- Entry conditions (all 5 required)
- Entry rejection when any condition is missing
- SELL/BUY signal generation for short open/close
- Stop-loss, regime change, profit target, trailing stop, timeout exits
- Position tracking via on_trade_filled()
- add_position() and close_position() (backtest compatibility)
- on_tick lowest_price tracking
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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
from krakenbot.indicators.multi_timeframe import (
    MarketRegime,
    MultiTimeframeAnalysis,
    TimeframeZone,
)
from krakenbot.models.base import SignalType
from krakenbot.strategies.bear_short import BearShortStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bear_short_settings() -> Settings:
    """Create settings for bear short strategy testing."""
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
            pair="BTC/USDC",
            default_order_amount_eur=100.0,
            candle_interval_min=15,
        ),
        strategy=StrategySettings(
            name="bear_short",
            buy_threshold_pct=-1.0,
            sell_threshold_pct=2.0,
            lookback_periods=50,
        ),
        multi_strategy=MultiStrategySettings(enabled=False),
        multi_timeframe=MultiTimeframeSettings(trigger_timeframe=5),
        order=OrderSettings(limit_buy_offset_pct=0.05),
    )


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    """Create mock event bus."""
    bus = AsyncMock()
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


def _make_analysis(
    *,
    regime: MarketRegime = MarketRegime.BEAR,
    rsi_15m: float | None = 65.0,
    volume_ratio_5m: float = 1.5,
    ema_fast_1h: float = 42000.0,
    rsi_5m: float | None = 50.0,
    rsi_1h: float | None = 40.0,
) -> MultiTimeframeAnalysis:
    """Build a MultiTimeframeAnalysis for bear short testing."""
    return MultiTimeframeAnalysis(
        regime=regime,
        zone_15m=TimeframeZone.OVERBOUGHT,
        zone_5m=TimeframeZone.NEUTRAL,
        trend_strength=-0.3,
        volatility_atr=Decimal("500"),
        volatility_pct=1.2,
        volume_ratio_5m=volume_ratio_5m,
        volume_ratio_15m=1.0,
        rsi_5m=rsi_5m,
        rsi_15m=rsi_15m,
        rsi_1h=rsi_1h,
        recommended_buy_threshold=-2.0,
        recommended_sell_threshold=3.0,
        recommended_stop_loss_pct=3.0,
        recommended_position_size_pct=5.0,
        recommended_max_positions=3,
        metadata={"ema_fast_1h": ema_fast_1h, "ema_slow_1h": 41000.0},
    )


@pytest.fixture
def mock_analyzer() -> MagicMock:
    """Create mock MultiTimeframeAnalyzer."""
    analyzer = MagicMock()
    # Default: BEAR regime, RSI 15m=65, price above EMA20
    analyzer.analyze.return_value = _make_analysis()
    analyzer.update = MagicMock()
    return analyzer


@pytest.fixture
def strategy(
    bear_short_settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
    mock_analyzer: MagicMock,
) -> BearShortStrategy:
    """Create BearShortStrategy for testing."""
    s = BearShortStrategy(
        bear_short_settings,
        mock_event_bus,
        mock_db_manager,
        analyzer=mock_analyzer,
    )
    s._skip_db_sync = True
    return s


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestBearShortStrategyInitialization:
    """Tests for BearShortStrategy initialization."""

    def test_initialization_defaults(self, strategy: BearShortStrategy) -> None:
        """Test strategy initializes with correct default config."""
        assert strategy.pair == "BTC/USDC"
        assert strategy.profit_target_bear_pct == Decimal("2.0")
        assert strategy.profit_target_strong_bear_pct == Decimal("3.0")
        assert strategy.stop_loss_pct == Decimal("2.0")
        assert strategy.trailing_stop_pct == Decimal("1.0")
        assert strategy.min_profit_for_trailing_pct == Decimal("1.5")
        assert strategy.max_holding_minutes == 48 * 60
        assert strategy.leverage == 2

    def test_initial_state(self, strategy: BearShortStrategy) -> None:
        """Test strategy starts with empty internal state."""
        assert strategy.current_price is None
        assert strategy.open_positions_count == 0
        assert strategy._shorted_this_candle is False

    def test_get_name(self, strategy: BearShortStrategy) -> None:
        """Test strategy name."""
        assert strategy.get_name() == "bear_short"

    def test_get_config(self, strategy: BearShortStrategy) -> None:
        """Test strategy config retrieval."""
        config = strategy.get_config()
        assert config["name"] == "bear_short"
        assert config["profit_target_bear_pct"] == 2.0
        assert config["profit_target_strong_bear_pct"] == 3.0
        assert config["stop_loss_pct"] == 2.0
        assert config["trailing_stop_pct"] == 1.0
        assert config["leverage"] == 2
        assert config["max_holding_minutes"] == 2880


# ---------------------------------------------------------------------------
# Tests: Entry (SELL) signal - all conditions met
# ---------------------------------------------------------------------------


class TestBearShortEntrySignals:
    """Tests for short entry signal generation."""

    @pytest.mark.asyncio
    async def test_entry_all_conditions_met(self, strategy: BearShortStrategy) -> None:
        """Test SELL signal when all entry conditions are met.

        Conditions:
        1. Regime is BEAR or STRONG_BEAR
        2. RSI 15m > 60 (overbought in bear)
        3. Price > EMA20 1h (rally into resistance)
        4. Volume ratio 5m >= 1.0
        5. Max positions not exceeded
        6. One short per candle
        """
        # Price at 43000, above EMA20 1h (42000)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.pair == "BTC/USDC"
        assert signal.confidence == 0.85
        assert signal.metadata["mode"] == "margin"
        assert signal.metadata["is_short_open"] is True
        assert signal.metadata["leverage"] == 2
        assert signal.metadata["order_type"] == "market"

    @pytest.mark.asyncio
    async def test_entry_strong_bear_regime(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test SELL signal also fires in STRONG_BEAR regime."""
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.STRONG_BEAR)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["regime"] == "strong_bear"

    @pytest.mark.asyncio
    async def test_entry_metadata_contains_indicators(self, strategy: BearShortStrategy) -> None:
        """Test that SELL signal metadata includes all indicator values."""
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert "rsi_15m" in signal.metadata
        assert "regime" in signal.metadata
        assert signal.metadata["rsi_15m"] == 65.0


# ---------------------------------------------------------------------------
# Tests: Entry rejection
# ---------------------------------------------------------------------------


class TestBearShortEntryRejection:
    """Tests for entry rejection when any condition is not met."""

    @pytest.mark.asyncio
    async def test_no_entry_neutral_regime(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no SELL when regime is NEUTRAL."""
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.NEUTRAL)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_bull_regime(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no SELL when regime is BULL."""
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.BULL)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_strong_bull_regime(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no SELL when regime is STRONG_BULL."""
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.STRONG_BULL)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_rsi_15m_too_low(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no SELL when RSI 15m <= 60 (not overbought)."""
        mock_analyzer.analyze.return_value = _make_analysis(rsi_15m=55.0)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_rsi_15m_none(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no SELL when RSI 15m is None."""
        mock_analyzer.analyze.return_value = _make_analysis(rsi_15m=None)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_price_below_ema(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no SELL when price <= EMA20 1h (no rally to short)."""
        # EMA20 1h = 42000, price = 41000 (below)
        mock_analyzer.analyze.return_value = _make_analysis(ema_fast_1h=42000.0)
        strategy._current_price = Decimal("41000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_volume_too_low(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no SELL when volume ratio < min_volume_ratio."""
        mock_analyzer.analyze.return_value = _make_analysis(volume_ratio_5m=0.5)
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_max_positions_reached(
        self,
        strategy: BearShortStrategy,
    ) -> None:
        """Test no SELL when max_open_positions is reached."""
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        # Fill up positions to the max (entry at current price = no exit conditions)
        for _ in range(strategy.max_open_positions):
            strategy.add_position(
                entry_price=Decimal("43000"),
                amount_usdc=Decimal("100"),
                entry_time=datetime.now(UTC),
            )

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_already_shorted_this_candle(
        self,
        strategy: BearShortStrategy,
    ) -> None:
        """Test no SELL when already shorted this candle."""
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._shorted_this_candle = True

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_no_current_price(self, strategy: BearShortStrategy) -> None:
        """Test no signal when current price is not set."""
        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_analyzer_returns_none(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no signal when analyzer returns None."""
        mock_analyzer.analyze.return_value = None
        strategy._current_price = Decimal("43000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None


# ---------------------------------------------------------------------------
# Tests: Exit signals
# ---------------------------------------------------------------------------


class TestBearShortExitSignals:
    """Tests for short exit (close) signal generation."""

    @pytest.mark.asyncio
    async def test_stop_loss_exit(self, strategy: BearShortStrategy) -> None:
        """Test BUY signal when stop-loss triggers (price moved UP)."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Open short at 42000
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=1),
        )

        # Price rose 2.1% to 42882 (stop-loss at 2%)
        strategy._current_price = Decimal("42882")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["mode"] == "margin"
        assert signal.metadata["is_short_close"] is True
        assert signal.metadata["reason"] == "stop_loss"
        assert signal.metadata["order_type"] == "market"
        assert signal.confidence == 1.0

    @pytest.mark.asyncio
    async def test_regime_change_exit(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test BUY signal when regime changes to bullish."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=1),
        )

        # Regime changed to BULL
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.BULL)
        strategy._current_price = Decimal("42000")  # Break-even

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["reason"] == "regime_change"
        assert signal.confidence == 0.95

    @pytest.mark.asyncio
    async def test_regime_change_neutral_exit(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test BUY signal when regime changes to NEUTRAL."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=1),
        )

        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.NEUTRAL)
        strategy._current_price = Decimal("42000")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.metadata["reason"] == "regime_change"

    @pytest.mark.asyncio
    async def test_profit_target_bear(self, strategy: BearShortStrategy) -> None:
        """Test BUY signal when profit target reached (2% for BEAR)."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=1),
        )

        # Price dropped 2.1% to 41118 (profit target at 2%)
        strategy._current_price = Decimal("41118")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["reason"] == "profit_target"
        assert signal.confidence == 0.9

    @pytest.mark.asyncio
    async def test_profit_target_strong_bear(
        self,
        strategy: BearShortStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test BUY signal with higher profit target (3% for STRONG_BEAR)."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.STRONG_BEAR)

        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=1),
        )

        # 2.5% profit: not enough for STRONG_BEAR (needs 3%)
        strategy._current_price = Decimal("40950")

        signal = await strategy.generate_signal()

        # No exit at 2.5%, need 3%
        assert signal is None

    @pytest.mark.asyncio
    async def test_trailing_stop_exit(self, strategy: BearShortStrategy) -> None:
        """Test BUY signal via trailing stop after min profit reached."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Open short at 42000
        pid = strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=2),
        )

        # Simulate: price dropped to lowest 41000 (profit_at_low = 2.38% > 1.5%)
        pos = strategy._open_positions[0]
        pos.lowest_price = Decimal("41000")

        # Now price bounced back to 41420 (rise_from_low = 420/41000 = 1.02% >= 1.0%)
        strategy._current_price = Decimal("41420")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["reason"] == "trailing_stop"
        assert signal.metadata["position_id"] == pid

    @pytest.mark.asyncio
    async def test_trailing_stop_not_triggered_below_min_profit(
        self, strategy: BearShortStrategy
    ) -> None:
        """Test trailing stop does NOT trigger if min profit not reached."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=1),
        )

        # Lowest price: 41700 (profit_at_low = 0.71% < 1.5%)
        pos = strategy._open_positions[0]
        pos.lowest_price = Decimal("41700")

        strategy._current_price = Decimal("41800")

        signal = await strategy.generate_signal()

        # No trailing stop because not enough profit at low
        assert signal is None

    @pytest.mark.asyncio
    async def test_timeout_exit(self, strategy: BearShortStrategy) -> None:
        """Test BUY signal via timeout (held > max_holding_minutes)."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Position held for 49 hours (> 48h = 2880 min)
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=49),
        )

        # Small profit, not enough for profit target or trailing
        strategy._current_price = Decimal("41900")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["reason"] == "timeout"
        assert signal.metadata["order_type"] == "market"
        assert signal.confidence == 0.7

    @pytest.mark.asyncio
    async def test_stop_loss_priority_over_regime_change(
        self, strategy: BearShortStrategy, mock_analyzer: MagicMock
    ) -> None:
        """Test stop-loss fires before regime change in priority order."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=1),
        )

        # Regime changed to BULL AND stop-loss triggered
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.BULL)
        strategy._current_price = Decimal("42900")  # +2.14% => stop-loss

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.metadata["reason"] == "stop_loss"

    @pytest.mark.asyncio
    async def test_no_exit_when_no_conditions(self, strategy: BearShortStrategy) -> None:
        """Test no exit when position doesn't meet any exit condition."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Recent position, small profit, BEAR regime
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(minutes=60),
        )

        # Price = 41800, profit = 0.48% (below all thresholds)
        strategy._current_price = Decimal("41800")

        signal = await strategy.generate_signal()

        # No exit, but also no new entry (already have a position and
        # conditions may or may not be met for a second entry)
        # The key assertion is that there's no exit signal
        if signal is not None:
            assert signal.signal_type != SignalType.BUY or "is_short_close" not in signal.metadata

    @pytest.mark.asyncio
    async def test_close_signal_metadata(self, strategy: BearShortStrategy) -> None:
        """Test close signal metadata contains all expected fields."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        pid = strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            entry_time=now - timedelta(hours=49),
        )

        strategy._current_price = Decimal("41900")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.metadata["position_id"] == pid
        assert "amount_btc" in signal.metadata
        assert "entry_price" in signal.metadata
        assert "profit_pct" in signal.metadata
        assert "holding_time_minutes" in signal.metadata
        assert signal.metadata["entry_price"] == 42000.0


# ---------------------------------------------------------------------------
# Tests: on_trade_filled
# ---------------------------------------------------------------------------


class TestBearShortOnTradeFilled:
    """Tests for position tracking via on_trade_filled()."""

    @pytest.mark.asyncio
    async def test_sell_trade_opens_short(self, strategy: BearShortStrategy) -> None:
        """Test that a sell trade creates a new short position."""
        await strategy.on_trade_filled(
            trade_id="test-001",
            pair="BTC/USDC",
            side="sell",
            amount=Decimal("0.01"),
            price=Decimal("42000"),
            fee=Decimal("1.09"),
            reference_price=None,
            position_id=None,
        )

        assert strategy.open_positions_count == 1
        pos = strategy.open_positions[0]
        assert pos.entry_price == Decimal("42000")
        assert pos.lowest_price == Decimal("42000")
        assert pos.position_id == 1

    @pytest.mark.asyncio
    async def test_buy_trade_closes_short(self, strategy: BearShortStrategy) -> None:
        """Test that a buy trade closes the matching short position."""
        # Open first
        await strategy.on_trade_filled(
            trade_id="sell-001",
            pair="BTC/USDC",
            side="sell",
            amount=Decimal("0.01"),
            price=Decimal("42000"),
            fee=Decimal("1.09"),
            reference_price=None,
            position_id=None,
        )
        assert strategy.open_positions_count == 1

        # Close by position_id
        await strategy.on_trade_filled(
            trade_id="buy-001",
            pair="BTC/USDC",
            side="buy",
            amount=Decimal("0.01"),
            price=Decimal("41000"),
            fee=Decimal("1.07"),
            reference_price=None,
            position_id=1,
        )

        assert strategy.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_buy_trade_ignores_none_position_id(self, strategy: BearShortStrategy) -> None:
        """Test that buy trade with position_id=None is a no-op."""
        strategy.add_position(entry_price=Decimal("42000"), amount_usdc=Decimal("100"))

        await strategy.on_trade_filled(
            trade_id="buy-001",
            pair="BTC/USDC",
            side="buy",
            amount=Decimal("0.01"),
            price=Decimal("41000"),
            fee=Decimal("1.07"),
            reference_price=None,
            position_id=None,
        )

        assert strategy.open_positions_count == 1


# ---------------------------------------------------------------------------
# Tests: Backtest compatibility
# ---------------------------------------------------------------------------


class TestBearShortBacktestCompat:
    """Tests for add_position() and close_position() backtest helpers."""

    def test_add_position_creates_short(self, strategy: BearShortStrategy) -> None:
        """Test add_position creates a ShortPosition."""
        pid = strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("500"),
        )

        assert pid == 1
        assert strategy.open_positions_count == 1

        pos = strategy.open_positions[0]
        assert pos.entry_price == Decimal("42000")
        assert pos.amount_usdc == Decimal("500")
        assert pos.lowest_price == Decimal("42000")

    def test_add_position_with_custom_time(self, strategy: BearShortStrategy) -> None:
        """Test add_position with explicit entry_time."""
        custom_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        pid = strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("300"),
            entry_time=custom_time,
        )

        pos = strategy.open_positions[0]
        assert pos.entry_time == custom_time
        assert pid == 1

    def test_add_position_increments_ids(self, strategy: BearShortStrategy) -> None:
        """Test that add_position increments position IDs."""
        pid1 = strategy.add_position(Decimal("42000"), Decimal("100"))
        pid2 = strategy.add_position(Decimal("41000"), Decimal("200"))
        pid3 = strategy.add_position(Decimal("40000"), Decimal("300"))

        assert pid1 == 1
        assert pid2 == 2
        assert pid3 == 3
        assert strategy.open_positions_count == 3

    def test_close_position_removes_position(self, strategy: BearShortStrategy) -> None:
        """Test close_position removes and returns the position."""
        pid = strategy.add_position(Decimal("42000"), Decimal("100"))

        closed = strategy.close_position(pid)

        assert closed is not None
        assert closed.position_id == pid
        assert closed.entry_price == Decimal("42000")
        assert strategy.open_positions_count == 0

    def test_close_position_returns_none_for_unknown_id(self, strategy: BearShortStrategy) -> None:
        """Test close_position returns None when ID not found."""
        strategy.add_position(Decimal("42000"), Decimal("100"))

        closed = strategy.close_position(999)

        assert closed is None
        assert strategy.open_positions_count == 1

    def test_close_position_correct_one_among_many(self, strategy: BearShortStrategy) -> None:
        """Test close_position removes only the targeted position."""
        pid1 = strategy.add_position(Decimal("42000"), Decimal("100"))
        pid2 = strategy.add_position(Decimal("41000"), Decimal("200"))
        pid3 = strategy.add_position(Decimal("40000"), Decimal("300"))

        closed = strategy.close_position(pid2)

        assert closed is not None
        assert closed.entry_price == Decimal("41000")
        assert strategy.open_positions_count == 2
        remaining_ids = [p.position_id for p in strategy.open_positions]
        assert pid2 not in remaining_ids
        assert pid1 in remaining_ids
        assert pid3 in remaining_ids


# ---------------------------------------------------------------------------
# Tests: on_tick + lowest price tracking
# ---------------------------------------------------------------------------


class TestBearShortOnTick:
    """Tests for on_tick price and trailing stop tracking."""

    @pytest.mark.asyncio
    async def test_on_tick_updates_current_price(self, strategy: BearShortStrategy) -> None:
        """Test on_tick updates current price."""
        tick = {"pair": "BTC/USDC", "price": "41000.00"}

        await strategy.on_tick(tick)

        assert strategy.current_price == Decimal("41000.00")

    @pytest.mark.asyncio
    async def test_on_tick_ignores_other_pair(self, strategy: BearShortStrategy) -> None:
        """Test on_tick ignores data for a different pair."""
        tick = {"pair": "ETH/USDC", "price": "3000.00"}

        await strategy.on_tick(tick)

        assert strategy.current_price is None

    @pytest.mark.asyncio
    async def test_on_tick_updates_lowest_price(self, strategy: BearShortStrategy) -> None:
        """Test on_tick updates lowest_price for trailing stop tracking."""
        strategy.add_position(Decimal("42000"), Decimal("100"))

        tick = {"pair": "BTC/USDC", "price": "41000.00"}
        await strategy.on_tick(tick)

        pos = strategy.open_positions[0]
        assert pos.lowest_price == Decimal("41000.00")

    @pytest.mark.asyncio
    async def test_on_tick_does_not_raise_lowest_price(self, strategy: BearShortStrategy) -> None:
        """Test on_tick does not increase lowest_price (only tracks new lows)."""
        strategy.add_position(Decimal("42000"), Decimal("100"))

        # Price drops
        await strategy.on_tick({"pair": "BTC/USDC", "price": "41000.00"})
        # Price bounces up
        await strategy.on_tick({"pair": "BTC/USDC", "price": "41500.00"})

        pos = strategy.open_positions[0]
        assert pos.lowest_price == Decimal("41000.00")


# ---------------------------------------------------------------------------
# Tests: reset_state
# ---------------------------------------------------------------------------


class TestBearShortResetState:
    """Tests for reset_state method."""

    def test_reset_clears_all_state(self, strategy: BearShortStrategy) -> None:
        """Test reset_state clears all internal state."""
        strategy.add_position(Decimal("42000"), Decimal("100"))
        strategy._current_price = Decimal("41000")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._shorted_this_candle = True

        strategy.reset_state()

        assert strategy.open_positions_count == 0
        assert strategy.current_price is None
        assert strategy._current_timestamp is None
        assert strategy._shorted_this_candle is False
        assert strategy._next_position_id == 1
