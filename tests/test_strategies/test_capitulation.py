"""Tests for capitulation strategy module.

This module tests the CapitulationStrategy including:
- Capitulation entry detection (all 4 conditions)
- Entry rejection when any condition is missing
- Cooldown enforcement between BUY signals
- SELL signals: trailing stop, take profit, timeout
- Hourly change tracking and std dev calculation
- Position tracking via on_trade_filled()
- add_position() and close_position() (backtest compatibility)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.config.settings import (
    CapitulationSettings,
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
from krakenbot.core.event_bus import EventBus
from krakenbot.indicators.multi_timeframe import (
    MarketRegime,
    MultiTimeframeAnalysis,
    TimeframeZone,
)
from krakenbot.models.base import SignalType
from krakenbot.strategies.capitulation import CapitulationPosition, CapitulationStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def capitulation_settings() -> Settings:
    """Create settings for capitulation strategy testing."""
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
            pair="XBT/USDC",
            default_order_amount_eur=100.0,
            candle_interval_min=15,
        ),
        strategy=StrategySettings(
            name="capitulation",
            buy_threshold_pct=-1.0,
            sell_threshold_pct=2.0,
            lookback_periods=50,
        ),
        capitulation=CapitulationSettings(
            rsi_1h_threshold=20.0,
            rsi_5m_threshold=15.0,
            volume_spike_multiplier=3.0,
            trailing_stop_pct=2.0,
            max_profit_target_pct=15.0,
            max_holding_minutes=2880,
            cooldown_hours=4,
        ),
        multi_strategy=MultiStrategySettings(enabled=False),
        multi_timeframe=MultiTimeframeSettings(trigger_timeframe=5),
        order=OrderSettings(limit_buy_offset_pct=0.05),
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


def _make_analysis(
    *,
    rsi_1h: float | None = 15.0,
    rsi_5m: float | None = 10.0,
    volume_ratio_5m: float = 5.0,
    rsi_15m: float | None = 20.0,
    volume_ratio_15m: float = 2.0,
) -> MultiTimeframeAnalysis:
    """Build a MultiTimeframeAnalysis with sensible defaults for testing."""
    return MultiTimeframeAnalysis(
        regime=MarketRegime.STRONG_BEAR,
        zone_15m=TimeframeZone.OVERSOLD,
        zone_5m=TimeframeZone.OVERSOLD,
        trend_strength=0.0,
        volatility_atr=Decimal("500"),
        volatility_pct=0.5,
        volume_ratio_5m=volume_ratio_5m,
        volume_ratio_15m=volume_ratio_15m,
        rsi_5m=rsi_5m,
        rsi_15m=rsi_15m,
        rsi_1h=rsi_1h,
        recommended_buy_threshold=-2.0,
        recommended_sell_threshold=3.0,
        recommended_position_size_pct=2.0,
        recommended_max_positions=3,
    )


@pytest.fixture
def mock_analyzer() -> MagicMock:
    """Create a mock MultiTimeframeAnalyzer that returns extreme values."""
    analyzer = MagicMock()
    analyzer.analyze.return_value = _make_analysis()
    analyzer.update = MagicMock()
    return analyzer


@pytest.fixture
def strategy(
    capitulation_settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
    mock_analyzer: MagicMock,
) -> CapitulationStrategy:
    """Create capitulation strategy for testing."""
    strat = CapitulationStrategy(
        capitulation_settings,
        mock_event_bus,
        mock_db_manager,
        analyzer=mock_analyzer,
    )
    strat._skip_db_sync = True
    return strat


def _populate_crash_data(strategy: CapitulationStrategy) -> None:
    """Populate hourly closes/changes simulating a 24h crash from 100 to 80.

    25 hourly closes: 100, 99.17, 98.33, ..., 80.
    24 hourly pct changes (each ~ -0.84%).
    """
    start_price = Decimal("100")
    end_price = Decimal("80")
    n_closes = 25
    step = (end_price - start_price) / (n_closes - 1)

    strategy._hourly_closes.clear()
    strategy._hourly_changes.clear()

    prev: Decimal | None = None
    for i in range(n_closes):
        close = start_price + step * i
        strategy._hourly_closes.append(close)
        if prev is not None and prev > 0:
            pct = float((close - prev) / prev * 100)
            strategy._hourly_changes.append(pct)
        prev = close


# ---------------------------------------------------------------------------
# Tests: Initialization
# ---------------------------------------------------------------------------


class TestCapitulationStrategyInitialization:
    """Tests for CapitulationStrategy initialization."""

    def test_initialization(self, strategy: CapitulationStrategy) -> None:
        """Test strategy initializes with correct config from settings."""
        assert strategy.rsi_1h_threshold == 20.0
        assert strategy.rsi_5m_threshold == 15.0
        assert strategy.volume_spike_multiplier == 3.0
        assert strategy.trailing_stop_pct == Decimal("2.0")
        assert strategy.max_profit_target_pct == Decimal("15.0")
        assert strategy.max_holding_minutes == 2880
        assert strategy.cooldown_hours == 4
        assert strategy.pair == "XBT/USDC"

    def test_initial_state(self, strategy: CapitulationStrategy) -> None:
        """Test strategy starts with empty internal state."""
        assert strategy.current_price is None
        assert strategy.open_positions_count == 0
        assert strategy._last_buy_time is None
        assert len(strategy._hourly_closes) == 0
        assert len(strategy._hourly_changes) == 0

    def test_get_name(self, strategy: CapitulationStrategy) -> None:
        """Test strategy name."""
        assert strategy.get_name() == "capitulation"

    def test_get_config(self, strategy: CapitulationStrategy) -> None:
        """Test strategy config retrieval."""
        config = strategy.get_config()
        assert config["name"] == "capitulation"
        assert config["rsi_1h_threshold"] == 20.0
        assert config["rsi_5m_threshold"] == 15.0
        assert config["volume_spike_multiplier"] == 3.0
        assert config["trailing_stop_pct"] == 2.0
        assert config["max_profit_target_pct"] == 15.0
        assert config["max_holding_minutes"] == 2880
        assert config["cooldown_hours"] == 4


# ---------------------------------------------------------------------------
# Tests: Entry (BUY) signal - all 4 conditions met
# ---------------------------------------------------------------------------


class TestCapitulationEntryDetection:
    """Tests for capitulation BUY signal when all conditions are met."""

    @pytest.mark.asyncio
    async def test_entry_all_conditions_met(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test BUY signal when all 4 conditions are satisfied.

        Conditions:
        1. 24h drop > 2 sigma of hourly changes
        2. RSI 1h < 20
        3. Volume 5m > 3x average
        4. RSI 5m < 15
        """
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.pair == "XBT/USDC"
        assert signal.confidence == 0.95
        assert "CAPITULATION BUY" in signal.reason
        assert signal.metadata["order_type"] == "limit"
        assert "limit_price" in signal.metadata

    @pytest.mark.asyncio
    async def test_entry_limit_price_offset(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test the limit price is offset below current price."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        # limit_buy_offset_pct = 0.05 => limit_price = 80 * (1 - 0.0005) = 79.96
        expected_limit = float(Decimal("80") * (Decimal("1") - Decimal("0.05") / Decimal("100")))
        assert signal.metadata["limit_price"] == pytest.approx(expected_limit, rel=1e-6)

    @pytest.mark.asyncio
    async def test_entry_metadata_contains_indicators(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that BUY signal metadata includes all indicator values."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert "drop_24h_pct" in signal.metadata
        assert "sigma_multiplier" in signal.metadata
        assert "rsi_1h" in signal.metadata
        assert "rsi_5m" in signal.metadata
        assert "volume_ratio_5m" in signal.metadata
        assert signal.metadata["sigma_multiplier"] >= 2.0


# ---------------------------------------------------------------------------
# Tests: Entry rejection (missing conditions)
# ---------------------------------------------------------------------------


class TestCapitulationEntryRejection:
    """Tests for entry rejection when any single condition is not met."""

    @pytest.mark.asyncio
    async def test_no_entry_insufficient_hourly_data(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test no BUY when fewer than 12 hourly candles available."""
        # Only add 10 hourly changes (need >= 12)
        for i in range(11):
            strategy._hourly_closes.append(Decimal("100") - Decimal(str(i)))
        for _ in range(10):
            strategy._hourly_changes.append(-1.0)

        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_drop_less_than_2_sigma(
        self,
        strategy: CapitulationStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no BUY when 24h drop is below 2 standard deviations."""
        # Populate with gentle changes (small drop, high std dev)
        strategy._hourly_closes.clear()
        strategy._hourly_changes.clear()

        # 25 closes with small net drop and large variance
        for i in range(25):
            price = Decimal("100") + Decimal(str((-1) ** i * 2))
            strategy._hourly_closes.append(price)
        for i in range(24):
            # Alternating +/-2% changes => high std dev, small net drop
            strategy._hourly_changes.append((-1) ** i * 2.0)

        strategy._current_price = Decimal("98")  # Tiny net drop
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_rsi_1h_too_high(
        self,
        strategy: CapitulationStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no BUY when RSI 1h >= threshold (20)."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        # RSI 1h = 25, above threshold of 20
        mock_analyzer.analyze.return_value = _make_analysis(rsi_1h=25.0)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_rsi_1h_none(
        self,
        strategy: CapitulationStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no BUY when RSI 1h is None (not enough data)."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        mock_analyzer.analyze.return_value = _make_analysis(rsi_1h=None)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_volume_spike_too_low(
        self,
        strategy: CapitulationStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no BUY when volume ratio < volume_spike_multiplier (3.0)."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        # Volume ratio = 2.0, below threshold of 3.0
        mock_analyzer.analyze.return_value = _make_analysis(volume_ratio_5m=2.0)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_rsi_5m_too_high(
        self,
        strategy: CapitulationStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no BUY when RSI 5m >= threshold (15)."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        # RSI 5m = 18, above threshold of 15
        mock_analyzer.analyze.return_value = _make_analysis(rsi_5m=18.0)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_rsi_5m_none(
        self,
        strategy: CapitulationStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no BUY when RSI 5m is None."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        mock_analyzer.analyze.return_value = _make_analysis(rsi_5m=None)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_analyzer_returns_none(
        self,
        strategy: CapitulationStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test no BUY when analyzer.analyze() returns None."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        mock_analyzer.analyze.return_value = None

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_no_current_price(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test no signal when current price is not set."""
        _populate_crash_data(strategy)
        # _current_price left as None

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_no_entry_max_positions_reached(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test no BUY when max_open_positions is reached."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)

        # Fill up positions to the max
        for _ in range(strategy.max_open_positions):
            strategy.add_position(
                entry_price=Decimal("90"),
                amount_usdc=Decimal("100"),
            )

        signal = await strategy.generate_signal()

        assert signal is None


# ---------------------------------------------------------------------------
# Tests: Cooldown
# ---------------------------------------------------------------------------


class TestCapitulationCooldown:
    """Tests for cooldown enforcement between BUY signals."""

    @pytest.mark.asyncio
    async def test_no_buy_within_cooldown(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test no BUY when last buy was within cooldown_hours (4h)."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Simulate a recent buy 2 hours ago (cooldown is 4h)
        strategy._last_buy_time = now - timedelta(hours=2)

        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_buy_allowed_after_cooldown(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test BUY is allowed after cooldown period expires."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Last buy was 5 hours ago (cooldown is 4h)
        strategy._last_buy_time = now - timedelta(hours=5)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    @pytest.mark.asyncio
    async def test_buy_allowed_no_previous_buy(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test BUY is allowed when no previous buy has been recorded."""
        _populate_crash_data(strategy)
        strategy._current_price = Decimal("80")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._last_buy_time = None

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY


# ---------------------------------------------------------------------------
# Tests: SELL signals (trailing stop, take profit, timeout)
# ---------------------------------------------------------------------------


class TestCapitulationSellSignals:
    """Tests for SELL signal generation: trailing stop, take profit, timeout."""

    @pytest.mark.asyncio
    async def test_trailing_stop_sell(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test SELL via trailing stop: price drops trailing_stop_pct from high."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Add a position: entry at 100, highest seen 110
        strategy._open_positions.append(
            CapitulationPosition(
                entry_price=Decimal("100"),
                entry_time=now - timedelta(hours=1),
                amount_btc=Decimal("0.01"),
                amount_usdc=Decimal("1"),
                position_id=1,
                highest_price=Decimal("110"),
            )
        )

        # Price dropped from 110 to 107 => drop = 3/110 = 2.727% >= 2.0%
        strategy._current_price = Decimal("107")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "trailing_stop"
        assert signal.metadata["order_type"] == "market"
        assert signal.confidence == 0.95

    @pytest.mark.asyncio
    async def test_no_trailing_stop_if_price_not_above_entry(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test trailing stop does NOT trigger if highest_price <= entry_price."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Position where highest == entry (price never rose above entry)
        strategy._open_positions.append(
            CapitulationPosition(
                entry_price=Decimal("100"),
                entry_time=now - timedelta(hours=1),
                amount_btc=Decimal("0.01"),
                amount_usdc=Decimal("1"),
                position_id=1,
                highest_price=Decimal("100"),
            )
        )

        # Price drops to 97 - but since highest == entry, trailing stop check is skipped
        strategy._current_price = Decimal("97")

        # No hourly data => no BUY either
        signal = await strategy.generate_signal()

        assert signal is None

    @pytest.mark.asyncio
    async def test_take_profit_sell(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test SELL via take profit: profit >= max_profit_target_pct (15%)."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        strategy._open_positions.append(
            CapitulationPosition(
                entry_price=Decimal("100"),
                entry_time=now - timedelta(hours=2),
                amount_btc=Decimal("0.01"),
                amount_usdc=Decimal("1"),
                position_id=1,
                highest_price=Decimal("100"),
            )
        )

        # Price = 115 => profit = 15% >= 15% (take profit threshold)
        strategy._current_price = Decimal("115")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "take_profit"
        assert signal.metadata["order_type"] == "limit"
        assert signal.confidence == 0.9
        assert signal.metadata["limit_price"] == 115.0

    @pytest.mark.asyncio
    async def test_timeout_sell(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test SELL via timeout: held > max_holding_minutes (2880 = 48h)."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Position held for 3000 minutes (> 2880)
        strategy._open_positions.append(
            CapitulationPosition(
                entry_price=Decimal("100"),
                entry_time=now - timedelta(minutes=3000),
                amount_btc=Decimal("0.01"),
                amount_usdc=Decimal("1"),
                position_id=1,
                highest_price=Decimal("100"),
            )
        )

        # Price = 101 (small profit, not enough for take_profit or trailing stop)
        strategy._current_price = Decimal("101")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "timeout"
        assert signal.metadata["order_type"] == "market"
        assert signal.confidence == 0.7

    @pytest.mark.asyncio
    async def test_trailing_stop_priority_over_take_profit(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test trailing stop fires before take profit in priority order."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Position entry at 100, highest 120
        strategy._open_positions.append(
            CapitulationPosition(
                entry_price=Decimal("100"),
                entry_time=now - timedelta(hours=1),
                amount_btc=Decimal("0.01"),
                amount_usdc=Decimal("1"),
                position_id=1,
                highest_price=Decimal("120"),
            )
        )

        # Price = 117 => profit = 17% (>= 15% take profit)
        # drop_from_high = (120-117)/120 = 2.5% >= 2% trailing stop
        # Trailing stop should fire first due to priority order
        strategy._current_price = Decimal("117")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "trailing_stop"

    @pytest.mark.asyncio
    async def test_sell_signal_metadata(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test SELL signal metadata contains all expected fields."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        strategy._open_positions.append(
            CapitulationPosition(
                entry_price=Decimal("100"),
                entry_time=now - timedelta(minutes=3000),
                amount_btc=Decimal("0.01"),
                amount_usdc=Decimal("1"),
                position_id=42,
                highest_price=Decimal("100"),
            )
        )

        strategy._current_price = Decimal("101")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.metadata["position_id"] == 42
        assert signal.metadata["amount_btc"] == 0.01
        assert signal.metadata["entry_price"] == 100.0
        assert "profit_pct" in signal.metadata
        assert "holding_time_minutes" in signal.metadata

    @pytest.mark.asyncio
    async def test_no_sell_when_no_exit_condition(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test no SELL when position doesn't meet any exit condition."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Position held for 60 min, small profit, no trailing stop trigger
        strategy._open_positions.append(
            CapitulationPosition(
                entry_price=Decimal("100"),
                entry_time=now - timedelta(minutes=60),
                amount_btc=Decimal("0.01"),
                amount_usdc=Decimal("1"),
                position_id=1,
                highest_price=Decimal("100"),
            )
        )

        # Price = 105 => 5% profit (below 15% take profit)
        # No trailing stop (highest == entry, no drop from high)
        # 60min < 2880 timeout
        strategy._current_price = Decimal("105")

        signal = await strategy.generate_signal()

        # Should be None (no sell conditions, and no buy conditions either)
        assert signal is None


# ---------------------------------------------------------------------------
# Tests: Hourly change tracking (std dev calculation)
# ---------------------------------------------------------------------------


class TestHourlyChangeTracking:
    """Tests for hourly close tracking and standard deviation calculation."""

    @pytest.mark.asyncio
    async def test_on_ohlc_tracks_hourly_closes(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that 1h complete candles are tracked in _hourly_closes."""
        ohlc_data = {
            "pair": "XBT/USDC",
            "close": "50000.00",
            "high": "50500.00",
            "interval": 60,
            "is_complete": True,
        }

        await strategy.on_ohlc(ohlc_data)

        assert len(strategy._hourly_closes) == 1
        assert strategy._hourly_closes[0] == Decimal("50000.00")

    @pytest.mark.asyncio
    async def test_on_ohlc_calculates_pct_change(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that pct changes are calculated between consecutive hourly closes."""
        ohlc_1 = {
            "pair": "XBT/USDC",
            "close": "100",
            "high": "101",
            "interval": 60,
            "is_complete": True,
        }
        ohlc_2 = {
            "pair": "XBT/USDC",
            "close": "98",
            "high": "100",
            "interval": 60,
            "is_complete": True,
        }

        await strategy.on_ohlc(ohlc_1)
        await strategy.on_ohlc(ohlc_2)

        assert len(strategy._hourly_changes) == 1
        assert strategy._hourly_changes[0] == pytest.approx(-2.0, rel=1e-6)

    @pytest.mark.asyncio
    async def test_on_ohlc_ignores_incomplete_candle(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that incomplete 1h candles are not tracked."""
        ohlc_data = {
            "pair": "XBT/USDC",
            "close": "50000.00",
            "high": "50500.00",
            "interval": 60,
            "is_complete": False,
        }

        await strategy.on_ohlc(ohlc_data)

        assert len(strategy._hourly_closes) == 0

    @pytest.mark.asyncio
    async def test_on_ohlc_ignores_non_hourly_for_tracking(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that non-hourly candles do not add to hourly tracking."""
        ohlc_data = {
            "pair": "XBT/USDC",
            "close": "50000.00",
            "high": "50500.00",
            "interval": 5,
            "is_complete": True,
        }

        await strategy.on_ohlc(ohlc_data)

        assert len(strategy._hourly_closes) == 0

    @pytest.mark.asyncio
    async def test_on_ohlc_ignores_other_pairs(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that OHLC for other pairs is ignored."""
        ohlc_data = {
            "pair": "ETH/USDC",
            "close": "3000.00",
            "high": "3050.00",
            "interval": 60,
            "is_complete": True,
        }

        await strategy.on_ohlc(ohlc_data)

        assert len(strategy._hourly_closes) == 0

    @pytest.mark.asyncio
    async def test_hourly_closes_maxlen(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that hourly closes deque respects maxlen of 25."""
        for i in range(30):
            ohlc_data = {
                "pair": "XBT/USDC",
                "close": str(100 + i),
                "high": str(101 + i),
                "interval": 60,
                "is_complete": True,
            }
            await strategy.on_ohlc(ohlc_data)

        assert len(strategy._hourly_closes) == 25
        assert len(strategy._hourly_changes) == 24

    def test_std_dev_calculation_in_check_entry(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that _check_entry_conditions correctly computes std dev.

        Populate with known values and verify that the sigma calculation
        correctly rejects or accepts the entry.
        """
        # Uniform hourly changes of -1% each => std_dev = 0
        # (all the same, so variance = 0 => should return None)
        strategy._hourly_closes.clear()
        strategy._hourly_changes.clear()

        for i in range(25):
            strategy._hourly_closes.append(Decimal("100") * Decimal("0.99") ** i)
        for _ in range(24):
            strategy._hourly_changes.append(-1.0)

        strategy._current_price = strategy._hourly_closes[-1]

        result = strategy._check_entry_conditions()

        # std_dev = 0 because all changes are identical => should be None
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Position tracking via on_trade_filled()
# ---------------------------------------------------------------------------


class TestCapitulationOnTradeFilled:
    """Tests for position tracking via on_trade_filled()."""

    @pytest.mark.asyncio
    async def test_buy_trade_opens_position(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that a buy trade creates a new position."""
        await strategy.on_trade_filled(
            trade_id="test-trade-001",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            fee=Decimal("0.50"),
            reference_price=None,
            position_id=None,
        )

        assert strategy.open_positions_count == 1
        pos = strategy.open_positions[0]
        assert pos.entry_price == Decimal("50000")
        assert pos.amount_btc == Decimal("0.01")
        assert pos.highest_price == Decimal("50000")
        assert pos.position_id == 1

    @pytest.mark.asyncio
    async def test_buy_trade_sets_last_buy_time(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that a buy trade updates _last_buy_time."""
        assert strategy._last_buy_time is None

        await strategy.on_trade_filled(
            trade_id="test-trade-001",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            fee=Decimal("0.50"),
            reference_price=None,
            position_id=None,
        )

        assert strategy._last_buy_time is not None

    @pytest.mark.asyncio
    async def test_buy_trade_increments_position_id(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that each buy trade gets an incrementing position ID."""
        for i in range(3):
            await strategy.on_trade_filled(
                trade_id=f"test-trade-{i}",
                pair="XBT/USDC",
                side="buy",
                amount=Decimal("0.01"),
                price=Decimal("50000"),
                fee=Decimal("0.50"),
                reference_price=None,
                position_id=None,
            )

        assert strategy.open_positions_count == 3
        ids = [p.position_id for p in strategy.open_positions]
        assert ids == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_sell_trade_closes_position(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that a sell trade closes the matching position."""
        # Open a position first
        await strategy.on_trade_filled(
            trade_id="buy-001",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            fee=Decimal("0.50"),
            reference_price=None,
            position_id=None,
        )
        assert strategy.open_positions_count == 1

        # Close it
        await strategy.on_trade_filled(
            trade_id="sell-001",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.01"),
            price=Decimal("52000"),
            fee=Decimal("0.50"),
            reference_price=None,
            position_id=1,
        )

        assert strategy.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_sell_trade_ignores_none_position_id(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that sell trade with position_id=None is a no-op."""
        strategy.add_position(entry_price=Decimal("50000"), amount_usdc=Decimal("100"))

        await strategy.on_trade_filled(
            trade_id="sell-001",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.01"),
            price=Decimal("52000"),
            fee=Decimal("0.50"),
            reference_price=None,
            position_id=None,
        )

        # Position should still be there
        assert strategy.open_positions_count == 1

    @pytest.mark.asyncio
    async def test_sell_trade_ignores_unknown_position_id(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that sell with non-matching position_id does nothing."""
        strategy.add_position(entry_price=Decimal("50000"), amount_usdc=Decimal("100"))

        await strategy.on_trade_filled(
            trade_id="sell-001",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.01"),
            price=Decimal("52000"),
            fee=Decimal("0.50"),
            reference_price=None,
            position_id=999,  # Does not exist
        )

        assert strategy.open_positions_count == 1


# ---------------------------------------------------------------------------
# Tests: add_position() and close_position() (backtest compatibility)
# ---------------------------------------------------------------------------


class TestBacktestCompatibility:
    """Tests for add_position() and close_position() backtest helpers."""

    def test_add_position_creates_position(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test add_position creates a CapitulationPosition."""
        pid = strategy.add_position(
            entry_price=Decimal("50000"),
            amount_usdc=Decimal("500"),
        )

        assert pid == 1
        assert strategy.open_positions_count == 1

        pos = strategy.open_positions[0]
        assert pos.entry_price == Decimal("50000")
        assert pos.amount_usdc == Decimal("500")
        assert pos.amount_btc == Decimal("500") / Decimal("50000")
        assert pos.highest_price == Decimal("50000")

    def test_add_position_with_custom_time(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test add_position with explicit entry_time."""
        custom_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        pid = strategy.add_position(
            entry_price=Decimal("60000"),
            amount_usdc=Decimal("300"),
            entry_time=custom_time,
        )

        pos = strategy.open_positions[0]
        assert pos.entry_time == custom_time
        assert pid == 1

    def test_add_position_increments_ids(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test that add_position increments position IDs."""
        pid1 = strategy.add_position(Decimal("50000"), Decimal("100"))
        pid2 = strategy.add_position(Decimal("51000"), Decimal("200"))
        pid3 = strategy.add_position(Decimal("52000"), Decimal("300"))

        assert pid1 == 1
        assert pid2 == 2
        assert pid3 == 3
        assert strategy.open_positions_count == 3

    def test_close_position_removes_position(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test close_position removes and returns the position."""
        pid = strategy.add_position(Decimal("50000"), Decimal("100"))

        closed = strategy.close_position(pid)

        assert closed is not None
        assert closed.position_id == pid
        assert closed.entry_price == Decimal("50000")
        assert strategy.open_positions_count == 0

    def test_close_position_returns_none_for_unknown_id(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test close_position returns None when ID not found."""
        strategy.add_position(Decimal("50000"), Decimal("100"))

        closed = strategy.close_position(999)

        assert closed is None
        assert strategy.open_positions_count == 1

    def test_close_position_correct_one_among_many(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test close_position removes only the targeted position."""
        pid1 = strategy.add_position(Decimal("50000"), Decimal("100"))
        pid2 = strategy.add_position(Decimal("51000"), Decimal("200"))
        pid3 = strategy.add_position(Decimal("52000"), Decimal("300"))

        closed = strategy.close_position(pid2)

        assert closed is not None
        assert closed.entry_price == Decimal("51000")
        assert strategy.open_positions_count == 2
        remaining_ids = [p.position_id for p in strategy.open_positions]
        assert pid2 not in remaining_ids
        assert pid1 in remaining_ids
        assert pid3 in remaining_ids


# ---------------------------------------------------------------------------
# Tests: on_tick + trailing stop tracking
# ---------------------------------------------------------------------------


class TestOnTick:
    """Tests for on_tick price and trailing stop tracking."""

    @pytest.mark.asyncio
    async def test_on_tick_updates_current_price(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test on_tick updates current price."""
        tick = {"pair": "XBT/USDC", "price": "55000.00"}

        await strategy.on_tick(tick)

        assert strategy.current_price == Decimal("55000.00")

    @pytest.mark.asyncio
    async def test_on_tick_ignores_other_pair(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test on_tick ignores data for a different pair."""
        tick = {"pair": "ETH/USDC", "price": "3000.00"}

        await strategy.on_tick(tick)

        assert strategy.current_price is None

    @pytest.mark.asyncio
    async def test_on_tick_updates_highest_price(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test on_tick updates highest_price for trailing stop tracking."""
        strategy.add_position(Decimal("50000"), Decimal("100"))

        tick = {"pair": "XBT/USDC", "price": "55000.00"}
        await strategy.on_tick(tick)

        pos = strategy.open_positions[0]
        assert pos.highest_price == Decimal("55000.00")

    @pytest.mark.asyncio
    async def test_on_tick_does_not_lower_highest_price(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test on_tick does not decrease highest_price."""
        strategy.add_position(Decimal("50000"), Decimal("100"))

        # Price goes up
        await strategy.on_tick({"pair": "XBT/USDC", "price": "55000.00"})
        # Price goes down
        await strategy.on_tick({"pair": "XBT/USDC", "price": "53000.00"})

        pos = strategy.open_positions[0]
        assert pos.highest_price == Decimal("55000.00")


# ---------------------------------------------------------------------------
# Tests: reset_state()
# ---------------------------------------------------------------------------


class TestResetState:
    """Tests for reset_state method."""

    def test_reset_clears_all_state(
        self,
        strategy: CapitulationStrategy,
    ) -> None:
        """Test reset_state clears all internal state."""
        # Set up some state
        strategy.add_position(Decimal("50000"), Decimal("100"))
        strategy._current_price = Decimal("55000")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._last_buy_time = datetime.now(UTC)
        strategy._hourly_closes.append(Decimal("50000"))
        strategy._hourly_changes.append(-1.0)

        strategy.reset_state()

        assert strategy.open_positions_count == 0
        assert strategy.current_price is None
        assert strategy._current_timestamp is None
        assert strategy._last_buy_time is None
        assert len(strategy._hourly_closes) == 0
        assert len(strategy._hourly_changes) == 0
        assert strategy._next_position_id == 1
