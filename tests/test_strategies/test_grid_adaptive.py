"""Tests for GridAdaptiveStrategy.

Tests cover:
- Range calculation via ATR
- ATR high -> wide range, ATR low -> tight range
- Periodic recalculation every N hours
- min_spacing_pct respected
- max_spacing_pct cap
- Profitability floor (MIN_PROFITABLE_SPACING)
- Directional pause (SMA50 deviation)
- Inherits grid functionality from GridSpotStrategy
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
from krakenbot.indicators.multi_timeframe import (
    MarketRegime,
    MultiTimeframeAnalysis,
    TimeframeZone,
)
from krakenbot.strategies.grid_adaptive import GridAdaptiveStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis(
    *,
    volatility_atr: Decimal = Decimal("1000"),
) -> MultiTimeframeAnalysis:
    """Build a MultiTimeframeAnalysis with configurable ATR."""
    return MultiTimeframeAnalysis(
        regime=MarketRegime.NEUTRAL,
        zone_15m=TimeframeZone.NEUTRAL,
        zone_5m=TimeframeZone.NEUTRAL,
        trend_strength=0.3,
        volatility_atr=volatility_atr,
        volatility_pct=1.2,
        volume_ratio_5m=1.0,
        volume_ratio_15m=1.0,
        rsi_5m=50.0,
        rsi_15m=50.0,
        rsi_1h=50.0,
        recommended_buy_threshold=-1.0,
        recommended_sell_threshold=2.0,
        recommended_stop_loss_pct=5.0,
        recommended_position_size_pct=5.0,
        recommended_max_positions=5,
    )


def _make_analyzer_mock(
    analysis: MultiTimeframeAnalysis | None = None,
) -> MagicMock:
    """Return an analyzer mock."""
    analyzer = MagicMock()
    analyzer.analyze.return_value = analysis
    analyzer.update = MagicMock()
    return analyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Create settings for grid adaptive testing."""
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
            max_open_positions=8,
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
            name="grid_adaptive",
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
def mock_analyzer() -> MagicMock:
    return _make_analyzer_mock(_make_analysis())


@pytest.fixture
def strategy(
    settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
    mock_analyzer: MagicMock,
) -> GridAdaptiveStrategy:
    """Create GridAdaptiveStrategy for testing."""
    s = GridAdaptiveStrategy(
        settings,
        mock_event_bus,
        mock_db_manager,
        strategy_params={
            "grid_levels": 8,
            "atr_multiplier": 3.0,
            "recalculate_hours": 6,
            "order_amount_usdc": 25,
            "min_spacing_pct": 1.5,
            "max_spacing_pct": 4.0,
            "directional_pause_pct": 25.0,
            "allow_short": False,
        },
        analyzer=mock_analyzer,
    )
    s._skip_db_sync = True
    return s


def _ohlc(price: str, *, interval: int = 5, ts: datetime | None = None) -> dict:
    """Build an OHLC candle dict."""
    return {
        "pair": "XBT/USDC",
        "interval": interval,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "10.0",
        "is_complete": True,
        "timestamp": ts or datetime.now(UTC),
    }


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestGridAdaptiveInit:
    """Tests for initialization."""

    def test_default_params(self, strategy: GridAdaptiveStrategy) -> None:
        assert strategy.atr_multiplier == Decimal("3.0")
        assert strategy.recalculate_hours == 6
        assert strategy.min_spacing_pct == Decimal("1.5")
        assert strategy.max_spacing_pct == Decimal("4.0")
        assert strategy.directional_pause_pct == Decimal("25.0")
        assert strategy.allow_short is False
        assert strategy.grid_levels == 8
        assert strategy.order_amount_usdc == Decimal("25")

    def test_get_name(self, strategy: GridAdaptiveStrategy) -> None:
        assert strategy.get_name() == "grid_adaptive"

    def test_get_config(self, strategy: GridAdaptiveStrategy) -> None:
        config = strategy.get_config()
        assert config["atr_multiplier"] == 3.0
        assert config["recalculate_hours"] == 6
        assert config["min_spacing_pct"] == 1.5
        assert config["max_spacing_pct"] == 4.0
        assert config["directional_pause_pct"] == 25.0
        assert config["allow_short"] is False
        assert config["grid_paused"] is False

    def test_inherits_grid_spot(self, strategy: GridAdaptiveStrategy) -> None:
        """GridAdaptive inherits from GridSpotStrategy."""
        from krakenbot.strategies.grid_spot import GridSpotStrategy

        assert isinstance(strategy, GridSpotStrategy)


# ---------------------------------------------------------------------------
# ATR-based range calculation
# ---------------------------------------------------------------------------


class TestGridAdaptiveATRRange:
    """Tests for ATR-based range computation."""

    def test_update_range_from_atr(self, strategy: GridAdaptiveStrategy) -> None:
        """Range is computed from ATR * multiplier."""
        strategy._current_atr = Decimal("1000")
        strategy._update_range_from_atr(Decimal("50000"))

        # Half range = 1000 * 3.0 = 3000
        # Total range = 6000 -> 6000/50000*100 = 12%
        expected_range = Decimal("12.0")
        assert abs(strategy.range_size_pct - expected_range) < Decimal("0.1")

        # Spacing = 12% / 8 levels = 1.5%
        expected_spacing = Decimal("1.5")
        assert abs(strategy.grid_spacing_pct - expected_spacing) < Decimal("0.1")

    def test_high_atr_wide_range(self, strategy: GridAdaptiveStrategy) -> None:
        """High ATR -> wider range."""
        strategy._current_atr = Decimal("2000")
        strategy._update_range_from_atr(Decimal("50000"))
        wide_range = strategy.range_size_pct

        strategy._current_atr = Decimal("500")
        strategy._update_range_from_atr(Decimal("50000"))
        tight_range = strategy.range_size_pct

        assert wide_range > tight_range

    def test_low_atr_tight_range(self, strategy: GridAdaptiveStrategy) -> None:
        """Low ATR -> tighter range, clamped to min_spacing."""
        strategy._current_atr = Decimal("200")
        strategy._update_range_from_atr(Decimal("50000"))
        # 200 * 3 = 600 per side -> 1200 total -> 2.4%
        # Spacing = 2.4% / 8 = 0.3% -> below min_spacing_pct (1.5%)
        assert strategy.grid_spacing_pct >= strategy.min_spacing_pct

    def test_min_spacing_pct_enforced(self, strategy: GridAdaptiveStrategy) -> None:
        """When ATR gives spacing below min, min is used."""
        strategy._current_atr = Decimal("50")
        strategy._update_range_from_atr(Decimal("50000"))

        assert strategy.grid_spacing_pct == strategy.min_spacing_pct
        # Range adjusted: 1.5% * 8 = 12.0%
        assert strategy.range_size_pct == Decimal("12.0")

    def test_max_spacing_pct_enforced(self, strategy: GridAdaptiveStrategy) -> None:
        """When ATR gives spacing above max, max is used."""
        # Very high ATR: 5000 * 3 = 15000 -> 30000 total -> 60% range
        # Spacing = 60% / 8 = 7.5% -> above max_spacing_pct (4.0%)
        strategy._current_atr = Decimal("5000")
        strategy._update_range_from_atr(Decimal("50000"))

        assert strategy.grid_spacing_pct == strategy.max_spacing_pct
        # Range adjusted: 4.0% * 8 = 32.0%
        assert strategy.range_size_pct == Decimal("32.0")

    def test_profitability_floor(
        self,
        settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        """Profitability floor (0.64%) overrides min_spacing if min_spacing is lower."""
        s = GridAdaptiveStrategy(
            settings,
            mock_event_bus,
            mock_db_manager,
            strategy_params={
                "grid_levels": 8,
                "atr_multiplier": 3.0,
                "min_spacing_pct": 0.3,  # Below profitability floor
                "max_spacing_pct": 4.0,
            },
            analyzer=mock_analyzer,
        )
        s._skip_db_sync = True

        # Very low ATR
        s._current_atr = Decimal("50")
        s._update_range_from_atr(Decimal("50000"))

        # Should use profitability floor (0.64%), not min_spacing (0.3%)
        assert s.grid_spacing_pct == Decimal("0.64")

    def test_no_update_when_no_atr(self, strategy: GridAdaptiveStrategy) -> None:
        """No range update when ATR is None."""
        old_range = strategy.range_size_pct
        strategy._current_atr = None
        strategy._update_range_from_atr(Decimal("50000"))
        assert strategy.range_size_pct == old_range

    def test_no_update_when_price_zero(self, strategy: GridAdaptiveStrategy) -> None:
        """No range update when price is 0."""
        old_range = strategy.range_size_pct
        strategy._current_atr = Decimal("1000")
        strategy._update_range_from_atr(Decimal("0"))
        assert strategy.range_size_pct == old_range


# ---------------------------------------------------------------------------
# ATR from analyzer
# ---------------------------------------------------------------------------


class TestGridAdaptiveATRSource:
    """Tests for getting ATR from analyzer."""

    def test_get_atr_from_analyzer(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """ATR comes from analyzer.analyze().volatility_atr."""
        mock_analyzer.analyze.return_value = _make_analysis(volatility_atr=Decimal("1500"))
        atr = strategy._get_atr()
        assert atr == Decimal("1500")

    def test_get_atr_none_when_no_analyzer(
        self,
        settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """ATR is None when no analyzer."""
        s = GridAdaptiveStrategy(
            settings,
            mock_event_bus,
            mock_db_manager,
            analyzer=None,
        )
        assert s._get_atr() is None

    def test_get_atr_none_when_analysis_none(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """ATR is None when analyzer returns None."""
        mock_analyzer.analyze.return_value = None
        assert strategy._get_atr() is None


# ---------------------------------------------------------------------------
# Periodic recalculation
# ---------------------------------------------------------------------------


class TestGridAdaptiveRecalculation:
    """Tests for periodic grid recalculation."""

    def test_should_recalculate_after_interval(self, strategy: GridAdaptiveStrategy) -> None:
        """Recalculate when enough time has passed."""
        now = datetime.now(UTC)
        strategy._last_recalc_time = now - timedelta(hours=7)
        strategy._current_timestamp = now
        assert strategy._should_recalculate() is True

    def test_should_not_recalculate_too_soon(self, strategy: GridAdaptiveStrategy) -> None:
        """No recalculate before interval."""
        now = datetime.now(UTC)
        strategy._last_recalc_time = now - timedelta(hours=3)
        strategy._current_timestamp = now
        assert strategy._should_recalculate() is False

    def test_should_recalculate_exactly_at_boundary(self, strategy: GridAdaptiveStrategy) -> None:
        """Recalculate at exactly 6 hours."""
        now = datetime.now(UTC)
        strategy._last_recalc_time = now - timedelta(hours=6)
        strategy._current_timestamp = now
        assert strategy._should_recalculate() is True

    def test_no_recalculate_without_last_time(self, strategy: GridAdaptiveStrategy) -> None:
        """No recalculate if _last_recalc_time is None."""
        strategy._last_recalc_time = None
        strategy._current_timestamp = datetime.now(UTC)
        assert strategy._should_recalculate() is False

    @pytest.mark.asyncio
    async def test_recalculate_updates_range(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """Recalculation updates range when ATR changes significantly."""
        strategy._current_price = Decimal("50000")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._grid_initialized = True
        strategy._grid_center = Decimal("50000")

        # Set initial range
        strategy._current_atr = Decimal("500")
        strategy._update_range_from_atr(Decimal("50000"))
        old_range = strategy.range_size_pct

        # ATR changed a lot -> new range
        mock_analyzer.analyze.return_value = _make_analysis(volatility_atr=Decimal("2000"))
        await strategy._recalculate_grid()

        # Range should have changed
        assert strategy.range_size_pct != old_range

    @pytest.mark.asyncio
    async def test_recalculate_skips_small_change(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """Recalculation skips when ATR change is < 10%."""
        strategy._current_price = Decimal("50000")
        strategy._current_timestamp = datetime.now(UTC)
        strategy._grid_initialized = True
        strategy._grid_center = Decimal("50000")

        # Set initial range
        strategy._current_atr = Decimal("1000")
        strategy._update_range_from_atr(Decimal("50000"))
        initial_rebalance_count = strategy._rebalance_count

        # ATR barely changed
        mock_analyzer.analyze.return_value = _make_analysis(
            volatility_atr=Decimal("1050")  # 5% change
        )
        await strategy._recalculate_grid()

        # Rebalance should NOT have been called (change < 10%)
        assert strategy._rebalance_count == initial_rebalance_count


# ---------------------------------------------------------------------------
# Directional pause
# ---------------------------------------------------------------------------


class TestGridAdaptiveDirectionalPause:
    """Tests for directional pause based on SMA50 deviation."""

    def test_no_pause_with_insufficient_data(self, strategy: GridAdaptiveStrategy) -> None:
        """No pause when fewer than 50 hourly prices."""
        strategy._current_price = Decimal("80000")
        # Only 10 prices
        for _ in range(10):
            strategy._hourly_prices.append(Decimal("50000"))
        strategy._check_directional_pause()
        assert strategy._grid_paused is False

    def test_pause_when_price_far_above_sma50(self, strategy: GridAdaptiveStrategy) -> None:
        """Grid pauses when price >25% above SMA50."""
        # SMA50 = 50000
        for _ in range(50):
            strategy._hourly_prices.append(Decimal("50000"))
        strategy._current_price = Decimal("65000")  # 30% above
        strategy._check_directional_pause()
        assert strategy._grid_paused is True

    def test_pause_when_price_far_below_sma50(self, strategy: GridAdaptiveStrategy) -> None:
        """Grid pauses when price >25% below SMA50."""
        for _ in range(50):
            strategy._hourly_prices.append(Decimal("50000"))
        strategy._current_price = Decimal("35000")  # 30% below
        strategy._check_directional_pause()
        assert strategy._grid_paused is True

    def test_no_pause_when_within_threshold(self, strategy: GridAdaptiveStrategy) -> None:
        """Grid does not pause when within 25% of SMA50."""
        for _ in range(50):
            strategy._hourly_prices.append(Decimal("50000"))
        strategy._current_price = Decimal("55000")  # 10% above
        strategy._check_directional_pause()
        assert strategy._grid_paused is False

    def test_resume_when_price_returns(self, strategy: GridAdaptiveStrategy) -> None:
        """Grid resumes when price comes back within threshold."""
        for _ in range(50):
            strategy._hourly_prices.append(Decimal("50000"))

        # Pause
        strategy._current_price = Decimal("65000")
        strategy._check_directional_pause()
        assert strategy._grid_paused is True

        # Resume
        strategy._current_price = Decimal("52000")
        strategy._check_directional_pause()
        assert strategy._grid_paused is False

    def test_pause_disabled_when_zero(
        self,
        settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        """Directional pause disabled when directional_pause_pct = 0."""
        s = GridAdaptiveStrategy(
            settings,
            mock_event_bus,
            mock_db_manager,
            strategy_params={
                "grid_levels": 8,
                "directional_pause_pct": 0.0,
            },
            analyzer=mock_analyzer,
        )
        s._skip_db_sync = True

        for _ in range(50):
            s._hourly_prices.append(Decimal("50000"))
        s._current_price = Decimal("80000")  # 60% above
        s._check_directional_pause()
        assert s._grid_paused is False

    def test_sma50_calculation(self, strategy: GridAdaptiveStrategy) -> None:
        """SMA50 correctly averages 50 prices."""
        for i in range(50):
            strategy._hourly_prices.append(Decimal(str(49000 + i * 40)))
        sma = strategy._get_sma50()
        assert sma is not None
        # Average of 49000, 49040, ..., 49960
        expected = Decimal("49000") + Decimal("49") * Decimal("40") / Decimal("2")
        assert abs(sma - expected) < Decimal("1")

    def test_sma50_none_with_insufficient_data(self, strategy: GridAdaptiveStrategy) -> None:
        """SMA50 returns None with fewer than 50 prices."""
        for _ in range(30):
            strategy._hourly_prices.append(Decimal("50000"))
        assert strategy._get_sma50() is None


# ---------------------------------------------------------------------------
# on_ohlc feeds analyzer + tracks hourly prices
# ---------------------------------------------------------------------------


class TestGridAdaptiveOnOhlc:
    """Tests for on_ohlc feeding analyzer."""

    @pytest.mark.asyncio
    async def test_on_ohlc_feeds_analyzer(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """on_ohlc calls analyzer.update for all intervals."""
        await strategy.on_ohlc(_ohlc("50000", interval=5))
        mock_analyzer.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_ohlc_feeds_all_intervals(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """on_ohlc feeds 5m, 15m, and 1h candles."""
        await strategy.on_ohlc(_ohlc("50000", interval=5))
        await strategy.on_ohlc(_ohlc("50000", interval=15))
        await strategy.on_ohlc(_ohlc("50000", interval=60))
        assert mock_analyzer.update.call_count == 3

    @pytest.mark.asyncio
    async def test_on_ohlc_updates_price(self, strategy: GridAdaptiveStrategy) -> None:
        """on_ohlc updates current price via parent."""
        await strategy.on_ohlc(_ohlc("50000"))
        assert strategy._current_price == Decimal("50000")

    @pytest.mark.asyncio
    async def test_on_ohlc_tracks_1h_prices(self, strategy: GridAdaptiveStrategy) -> None:
        """1h candles are tracked for SMA50."""
        await strategy.on_ohlc(_ohlc("50000", interval=60))
        assert len(strategy._hourly_prices) == 1
        assert strategy._hourly_prices[0] == Decimal("50000")

    @pytest.mark.asyncio
    async def test_on_ohlc_ignores_5m_for_sma(self, strategy: GridAdaptiveStrategy) -> None:
        """5m candles are NOT tracked for SMA50."""
        await strategy.on_ohlc(_ohlc("50000", interval=5))
        assert len(strategy._hourly_prices) == 0


# ---------------------------------------------------------------------------
# _handle_ohlc integration
# ---------------------------------------------------------------------------


class TestGridAdaptiveHandleOhlc:
    """Tests for _handle_ohlc with ATR-based init."""

    @pytest.mark.asyncio
    async def test_first_ohlc_initializes_with_atr(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """First candle initializes grid with ATR-based range."""
        mock_analyzer.analyze.return_value = _make_analysis(volatility_atr=Decimal("1000"))
        strategy._running = True

        await strategy._handle_ohlc(_ohlc("50000"))

        assert strategy._grid_initialized is True
        # Range should reflect ATR, not default fixed range
        # ATR=1000, mult=3 -> half_range=3000 -> total=6000 -> 12%
        assert abs(strategy.range_size_pct - Decimal("12.0")) < Decimal("1")

    @pytest.mark.asyncio
    async def test_handle_ohlc_without_analyzer(
        self,
        settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Grid still initializes without analyzer (uses default range)."""
        s = GridAdaptiveStrategy(
            settings,
            mock_event_bus,
            mock_db_manager,
            analyzer=None,
            strategy_params={"grid_levels": 8, "order_amount_usdc": 25},
        )
        s._skip_db_sync = True
        s._running = True

        await s._handle_ohlc(_ohlc("50000"))
        assert s._grid_initialized is True

    @pytest.mark.asyncio
    async def test_paused_grid_does_not_initialize(
        self, strategy: GridAdaptiveStrategy, mock_analyzer: MagicMock
    ) -> None:
        """Grid does not initialize when directional pause is active."""
        mock_analyzer.analyze.return_value = _make_analysis(volatility_atr=Decimal("1000"))
        strategy._running = True

        # Fill SMA50 data and set price far from SMA
        for _ in range(50):
            strategy._hourly_prices.append(Decimal("50000"))

        # Price 40% above SMA50 -> should pause
        await strategy._handle_ohlc(_ohlc("70000"))

        assert strategy._grid_paused is True
        assert strategy._grid_initialized is False
