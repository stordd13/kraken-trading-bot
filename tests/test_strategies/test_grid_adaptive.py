"""Tests for GridAdaptiveStrategy.

Tests cover:
- Range calculation via ATR
- ATR high -> wide range, ATR low -> tight range
- Periodic recalculation every N hours
- min_spacing_pct respected
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
            "recalculate_hours": 4,
            "order_amount_usdc": 25,
            "min_spacing_pct": 0.5,
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
        assert strategy.recalculate_hours == 4
        assert strategy.min_spacing_pct == Decimal("0.5")
        assert strategy.allow_short is False
        assert strategy.grid_levels == 8
        assert strategy.order_amount_usdc == Decimal("25")

    def test_get_name(self, strategy: GridAdaptiveStrategy) -> None:
        assert strategy.get_name() == "grid_adaptive"

    def test_get_config(self, strategy: GridAdaptiveStrategy) -> None:
        config = strategy.get_config()
        assert config["atr_multiplier"] == 3.0
        assert config["recalculate_hours"] == 4
        assert config["min_spacing_pct"] == 0.5
        assert config["allow_short"] is False

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
        """Low ATR -> tighter range."""
        strategy._current_atr = Decimal("200")
        strategy._update_range_from_atr(Decimal("50000"))
        # 200 * 3 = 600 per side -> 1200 total -> 2.4%
        # Spacing = 2.4% / 8 = 0.3% -> below min_spacing_pct (0.5%)
        # Should be clamped to min_spacing_pct
        assert strategy.grid_spacing_pct >= strategy.min_spacing_pct

    def test_min_spacing_pct_enforced(self, strategy: GridAdaptiveStrategy) -> None:
        """When ATR gives spacing below min, min is used."""
        # Very low ATR -> tiny spacing
        strategy._current_atr = Decimal("50")
        strategy._update_range_from_atr(Decimal("50000"))

        assert strategy.grid_spacing_pct == strategy.min_spacing_pct
        # Range adjusted: 0.5% * 8 = 4.0%
        assert strategy.range_size_pct == Decimal("4.0")

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
        strategy._last_recalc_time = now - timedelta(hours=5)
        strategy._current_timestamp = now
        assert strategy._should_recalculate() is True

    def test_should_not_recalculate_too_soon(self, strategy: GridAdaptiveStrategy) -> None:
        """No recalculate before interval."""
        now = datetime.now(UTC)
        strategy._last_recalc_time = now - timedelta(hours=2)
        strategy._current_timestamp = now
        assert strategy._should_recalculate() is False

    def test_should_recalculate_exactly_at_boundary(self, strategy: GridAdaptiveStrategy) -> None:
        """Recalculate at exactly 4 hours."""
        now = datetime.now(UTC)
        strategy._last_recalc_time = now - timedelta(hours=4)
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
# on_ohlc feeds analyzer
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
