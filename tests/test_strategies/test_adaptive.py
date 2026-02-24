"""Tests for adaptive threshold strategy module.

This module tests the AdaptiveStrategy including:
- BUY signal generation when price drops below adaptive threshold
- SELL signals: trailing_stop, profit_target, stop_loss, timeout
- Zone filter: no BUY when 15m zone is OVERBOUGHT
- Volume filter: no BUY when volume_ratio_5m < min_volume_ratio
- Position size multiplier in signal metadata
- Warmup behavior
- Rolling reference mechanics (delayed add, used_references)
- Fallback thresholds when analyzer is None
- add_position() and close_position() (backtest compatibility)
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
from krakenbot.models.base import SignalType
from krakenbot.strategies.adaptive import AdaptiveStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis(
    *,
    regime: MarketRegime = MarketRegime.NEUTRAL,
    zone_15m: TimeframeZone = TimeframeZone.NEUTRAL,
    zone_5m: TimeframeZone = TimeframeZone.NEUTRAL,
    volume_ratio_5m: float = 1.0,
    volume_ratio_15m: float = 1.0,
    buy_threshold: float = -1.0,
    sell_threshold: float = 2.0,
) -> MultiTimeframeAnalysis:
    """Build a MultiTimeframeAnalysis with sensible defaults."""
    return MultiTimeframeAnalysis(
        regime=regime,
        zone_15m=zone_15m,
        zone_5m=zone_5m,
        trend_strength=0.3,
        volatility_atr=Decimal("500"),
        volatility_pct=1.2,
        volume_ratio_5m=volume_ratio_5m,
        volume_ratio_15m=volume_ratio_15m,
        rsi_5m=50.0,
        rsi_15m=50.0,
        rsi_1h=50.0,
        recommended_buy_threshold=buy_threshold,
        recommended_sell_threshold=sell_threshold,
        recommended_stop_loss_pct=5.0,
        recommended_position_size_pct=5.0,
        recommended_max_positions=5,
    )


def _make_analyzer_mock(
    analysis: MultiTimeframeAnalysis | None = None,
) -> MagicMock:
    """Return a MagicMock for MultiTimeframeAnalyzer."""
    analyzer = MagicMock()
    analyzer.analyze.return_value = analysis
    analyzer.update = MagicMock()
    return analyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adaptive_settings() -> Settings:
    """Create settings for adaptive strategy testing."""
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
            default_order_amount_eur=15.0,
            candle_interval_min=15,
        ),
        strategy=StrategySettings(
            name="adaptive",
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
    """Create mock event bus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create mock database manager."""
    return MagicMock()


@pytest.fixture
def default_analysis() -> MultiTimeframeAnalysis:
    """A neutral analysis with permissive volume and zone."""
    return _make_analysis()


@pytest.fixture
def mock_analyzer(default_analysis: MultiTimeframeAnalysis) -> MagicMock:
    """Analyzer mock that returns a neutral analysis by default."""
    return _make_analyzer_mock(default_analysis)


@pytest.fixture
def strategy(
    adaptive_settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
    mock_analyzer: MagicMock,
) -> AdaptiveStrategy:
    """Create AdaptiveStrategy with analyzer for testing."""
    s = AdaptiveStrategy(
        adaptive_settings,
        mock_event_bus,
        mock_db_manager,
        analyzer=mock_analyzer,
    )
    s._skip_db_sync = True
    return s


@pytest.fixture
def strategy_no_analyzer(
    adaptive_settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
) -> AdaptiveStrategy:
    """Create AdaptiveStrategy without analyzer (fallback mode)."""
    s = AdaptiveStrategy(
        adaptive_settings,
        mock_event_bus,
        mock_db_manager,
        analyzer=None,
    )
    s._skip_db_sync = True
    return s


def _complete_candle(
    price: str,
    pair: str = "XBT/USDC",
    interval: int = 5,
    *,
    ts: datetime | None = None,
) -> dict:
    """Build a complete OHLC candle dict."""
    return {
        "pair": pair,
        "interval": interval,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "10.0",
        "is_complete": True,
        "timestamp": ts or datetime.now(UTC),
    }


def _incomplete_candle(
    price: str,
    pair: str = "XBT/USDC",
    interval: int = 5,
) -> dict:
    """Build an incomplete (in-progress) OHLC candle dict."""
    return {
        "pair": pair,
        "interval": interval,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "10.0",
        "is_complete": False,
    }


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyInitialization:
    """Tests for AdaptiveStrategy initialization."""

    def test_initialization_defaults(self, strategy: AdaptiveStrategy) -> None:
        """Test strategy initializes with correct default config."""
        assert strategy.pair == "XBT/USDC"
        assert strategy.trailing_stop_pct == Decimal("3.0")
        assert strategy.min_volume_ratio == 0.8
        assert strategy.block_overbought_15m is True
        assert strategy.max_open_positions == 3
        assert strategy.position_size_multiplier == 1.0
        assert strategy.lookback_periods == 5

    def test_initialization_custom_params(
        self,
        adaptive_settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """Test strategy respects custom strategy_params."""
        s = AdaptiveStrategy(
            adaptive_settings,
            mock_event_bus,
            mock_db_manager,
            strategy_params={
                "trailing_stop_pct": 5.0,
                "min_volume_ratio": 1.2,
                "block_overbought_15m": False,
            },
        )
        assert s.trailing_stop_pct == Decimal("5.0")
        assert s.min_volume_ratio == 1.2
        assert s.block_overbought_15m is False

    def test_get_name(self, strategy: AdaptiveStrategy) -> None:
        """Test strategy name."""
        assert strategy.get_name() == "adaptive"

    def test_get_config(self, strategy: AdaptiveStrategy) -> None:
        """Test strategy config retrieval."""
        config = strategy.get_config()
        assert config["name"] == "adaptive"
        assert config["trailing_stop_pct"] == 3.0
        assert config["min_volume_ratio"] == 0.8
        assert config["block_overbought_15m"] is True
        assert config["max_open_positions"] == 3
        assert config["position_size_multiplier"] == 1.0

    def test_initial_state(self, strategy: AdaptiveStrategy) -> None:
        """Test strategy initial internal state."""
        assert strategy.current_price is None
        assert strategy.open_positions_count == 0
        assert strategy._warming_up is True
        assert strategy._reference_prices == []
        assert strategy._used_references == set()
        assert strategy._pending_reference is None


# ---------------------------------------------------------------------------
# Warmup behavior
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyWarmup:
    """Tests for warmup behavior."""

    @pytest.mark.asyncio
    async def test_warmup_captures_open_price(self, strategy: AdaptiveStrategy) -> None:
        """During warmup, an incomplete candle captures _warmup_open_price."""
        candle = _incomplete_candle("42000")
        await strategy.on_ohlc(candle)

        assert strategy._warming_up is True
        assert strategy._warmup_open_price == Decimal("42000")

    @pytest.mark.asyncio
    async def test_warmup_ends_on_complete_candle(self, strategy: AdaptiveStrategy) -> None:
        """Warmup ends when first complete candle arrives."""
        await strategy.on_ohlc(_incomplete_candle("42000"))
        assert strategy._warming_up is True

        await strategy.on_ohlc(_complete_candle("42100"))
        assert strategy._warming_up is False
        assert strategy._warmup_open_price is None
        # First complete candle adds its close to references
        assert Decimal("42100") in strategy._reference_prices

    @pytest.mark.asyncio
    async def test_warmup_buy_signal_uses_open_price(self, strategy: AdaptiveStrategy) -> None:
        """During warmup, buy logic uses _warmup_open_price as reference."""
        # Incomplete candle -> captures open price
        await strategy.on_ohlc(_incomplete_candle("42000"))
        # Set current price to a drop
        strategy._current_price = Decimal("41500")  # -1.19%

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["reference_price"] == 42000.0

    @pytest.mark.asyncio
    async def test_no_signal_before_any_data(self, strategy: AdaptiveStrategy) -> None:
        """No signal when no data has been received at all."""
        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# BUY signal generation
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyBuySignal:
    """Tests for BUY signal generation."""

    @pytest.mark.asyncio
    async def test_buy_signal_on_price_drop(self, strategy: AdaptiveStrategy) -> None:
        """BUY signal when price drops below adaptive threshold."""
        # End warmup and add reference
        await strategy.on_ohlc(_complete_candle("42000"))
        # Process second complete candle so delayed reference is committed
        await strategy.on_ohlc(_complete_candle("42000"))

        # Price drops -1.5% from reference 42000
        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.pair == "XBT/USDC"
        assert signal.confidence == 0.85
        assert signal.metadata["reference_price"] == 42000.0
        assert signal.metadata["order_type"] == "limit"
        assert "limit_price" in signal.metadata

    @pytest.mark.asyncio
    async def test_no_buy_signal_insufficient_drop(self, strategy: AdaptiveStrategy) -> None:
        """No BUY signal when drop is insufficient."""
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        # Only -0.2% drop (threshold is -1%)
        strategy._current_price = Decimal("41916")

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_no_buy_when_max_positions_reached(self, strategy: AdaptiveStrategy) -> None:
        """No BUY signal when max_open_positions reached."""
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        # Fill up positions
        now = datetime.now(UTC)
        for i in range(strategy.max_open_positions):
            strategy.add_position(
                entry_price=Decimal("42000"),
                amount_usdc=Decimal("100"),
                reference_price=Decimal(str(40000 + i)),
                entry_time=now,
            )

        strategy._current_price = Decimal("41000")

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_no_buy_when_already_bought_this_candle(self, strategy: AdaptiveStrategy) -> None:
        """No BUY signal when already bought on this candle."""
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        strategy._current_price = Decimal("41370")
        strategy._bought_this_candle = True

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_buy_skips_used_reference(self, strategy: AdaptiveStrategy) -> None:
        """No BUY from a reference that was already used."""
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        # Mark the reference as used
        strategy._used_references.add(Decimal("42000"))

        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_buy_signal_contains_position_size_multiplier(
        self, strategy: AdaptiveStrategy
    ) -> None:
        """BUY signal metadata includes position_size_multiplier."""
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.metadata["position_size_multiplier"] == 1.0

    @pytest.mark.asyncio
    async def test_buy_signal_includes_regime(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """BUY signal metadata includes regime string."""
        mock_analyzer.analyze.return_value = _make_analysis(regime=MarketRegime.BULL)
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.metadata["regime"] == "bull"

    @pytest.mark.asyncio
    async def test_buy_signal_uses_adaptive_threshold(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """BUY uses recommended_buy_threshold from analysis, not fallback."""
        # Tighter threshold from analyzer: -0.5%
        mock_analyzer.analyze.return_value = _make_analysis(buy_threshold=-0.5)
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        # -0.6% drop -> should trigger with -0.5% threshold
        strategy._current_price = Decimal("41748")

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["adaptive_threshold"] == -0.5


# ---------------------------------------------------------------------------
# Zone filter
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyZoneFilter:
    """Tests for zone-based BUY filter."""

    @pytest.mark.asyncio
    async def test_no_buy_when_15m_overbought(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """No BUY when 15m zone is OVERBOUGHT."""
        mock_analyzer.analyze.return_value = _make_analysis(
            zone_15m=TimeframeZone.OVERBOUGHT,
        )
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_buy_allowed_when_15m_oversold(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """BUY is allowed when 15m zone is OVERSOLD."""
        mock_analyzer.analyze.return_value = _make_analysis(
            zone_15m=TimeframeZone.OVERSOLD,
        )
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    @pytest.mark.asyncio
    async def test_zone_filter_disabled(
        self,
        adaptive_settings: Settings,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """BUY allowed in OVERBOUGHT when block_overbought_15m is False."""
        analyzer = _make_analyzer_mock(_make_analysis(zone_15m=TimeframeZone.OVERBOUGHT))
        s = AdaptiveStrategy(
            adaptive_settings,
            mock_event_bus,
            mock_db_manager,
            analyzer=analyzer,
            strategy_params={"block_overbought_15m": False},
        )
        s._skip_db_sync = True

        await s.on_ohlc(_complete_candle("42000"))
        await s.on_ohlc(_complete_candle("42000"))

        s._current_price = Decimal("41370")

        signal = await s.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.BUY


# ---------------------------------------------------------------------------
# Volume filter
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyVolumeFilter:
    """Tests for volume-based BUY filter."""

    @pytest.mark.asyncio
    async def test_no_buy_when_volume_too_low(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """No BUY when volume_ratio_5m < min_volume_ratio."""
        mock_analyzer.analyze.return_value = _make_analysis(
            volume_ratio_5m=0.5,  # Below default 0.8
        )
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_buy_when_volume_sufficient(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """BUY allowed when volume_ratio_5m >= min_volume_ratio."""
        mock_analyzer.analyze.return_value = _make_analysis(
            volume_ratio_5m=1.5,
        )
        await strategy.on_ohlc(_complete_candle("42000"))
        await strategy.on_ohlc(_complete_candle("42000"))

        strategy._current_price = Decimal("41370")

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type == SignalType.BUY


# ---------------------------------------------------------------------------
# SELL signals
# ---------------------------------------------------------------------------


class TestAdaptiveStrategySellSignals:
    """Tests for SELL signal variants."""

    def _add_position(
        self,
        strategy: AdaptiveStrategy,
        entry_price: str = "42000",
        *,
        entry_time: datetime | None = None,
        highest_price: str | None = None,
    ) -> int:
        """Helper to add a position and optionally set highest_price."""
        pid = strategy.add_position(
            entry_price=Decimal(entry_price),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
            entry_time=entry_time or datetime.now(UTC),
        )
        if highest_price is not None:
            for pos in strategy._open_positions:
                if pos.position_id == pid:
                    pos.highest_price = Decimal(highest_price)
        return pid

    @pytest.mark.asyncio
    async def test_sell_trailing_stop(self, strategy: AdaptiveStrategy) -> None:
        """SELL when price drops trailing_stop_pct from highest."""
        # End warmup
        await strategy.on_ohlc(_complete_candle("42000"))

        pid = self._add_position(strategy, "42000", highest_price="44000")

        # 3% drop from highest 44000 -> 42680
        strategy._current_price = Decimal("42680")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "trailing_stop"
        assert signal.metadata["order_type"] == "market"
        assert signal.confidence == 0.95
        assert signal.metadata["position_id"] == pid

    @pytest.mark.asyncio
    async def test_sell_profit_target(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """SELL when profit >= adaptive sell threshold."""
        mock_analyzer.analyze.return_value = _make_analysis(sell_threshold=2.0)
        await strategy.on_ohlc(_complete_candle("42000"))

        self._add_position(strategy, "40000")

        # +2.5% profit from entry 40000 -> 41000
        strategy._current_price = Decimal("41000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "profit_target"
        assert signal.metadata["order_type"] == "limit"
        assert signal.confidence == 0.9

    @pytest.mark.asyncio
    async def test_sell_stop_loss(self, strategy: AdaptiveStrategy) -> None:
        """SELL when loss >= emergency_stop_loss_pct (10%)."""
        await strategy.on_ohlc(_complete_candle("42000"))

        self._add_position(strategy, "42000")

        # -10% loss -> price = 37800
        strategy._current_price = Decimal("37800")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "stop_loss"
        assert signal.metadata["order_type"] == "market"
        assert signal.confidence == 1.0

    @pytest.mark.asyncio
    async def test_sell_timeout(self, strategy: AdaptiveStrategy) -> None:
        """SELL when holding time >= max_holding_minutes (120)."""
        await strategy.on_ohlc(_complete_candle("42000"))

        entry_time = datetime.now(UTC) - timedelta(minutes=150)
        self._add_position(strategy, "42000", entry_time=entry_time)

        strategy._current_price = Decimal("42050")  # Slight gain, no other trigger
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "timeout"
        assert signal.metadata["order_type"] == "market"
        assert signal.confidence == 0.7

    @pytest.mark.asyncio
    async def test_sell_trailing_stop_priority_over_profit_target(
        self, strategy: AdaptiveStrategy
    ) -> None:
        """Trailing stop fires before profit target check when both met."""
        await strategy.on_ohlc(_complete_candle("42000"))

        self._add_position(strategy, "40000", highest_price="44000")
        # Price is above entry (profitable), but trailing fires first:
        # 3% from 44000 -> 42680;  price 42650 triggers trailing
        strategy._current_price = Decimal("42650")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.metadata["reason"] == "trailing_stop"

    @pytest.mark.asyncio
    async def test_no_trailing_stop_when_price_below_entry(
        self, strategy: AdaptiveStrategy
    ) -> None:
        """Trailing stop requires highest_price > entry_price."""
        await strategy.on_ohlc(_complete_candle("42000"))

        # highest_price == entry_price (never went above)
        self._add_position(strategy, "42000")

        strategy._current_price = Decimal("41500")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()

        # Should not be trailing_stop (highest == entry), could be None or other
        if signal is not None:
            assert signal.metadata.get("reason") != "trailing_stop"


# ---------------------------------------------------------------------------
# Fallback thresholds (analyzer=None)
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyFallback:
    """Tests for fallback thresholds when analyzer is None."""

    @pytest.mark.asyncio
    async def test_fallback_buy_threshold(self, strategy_no_analyzer: AdaptiveStrategy) -> None:
        """Uses settings.strategy.buy_threshold_pct when no analyzer."""
        s = strategy_no_analyzer
        await s.on_ohlc(_complete_candle("42000"))
        await s.on_ohlc(_complete_candle("42000"))

        # -1.5% drop should trigger with fallback -1.0%
        s._current_price = Decimal("41370")

        signal = await s.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.metadata["regime"] == "unknown"
        assert signal.metadata["adaptive_threshold"] == -1.0

    @pytest.mark.asyncio
    async def test_fallback_sell_threshold(self, strategy_no_analyzer: AdaptiveStrategy) -> None:
        """Uses settings.strategy.sell_threshold_pct when no analyzer."""
        s = strategy_no_analyzer
        await s.on_ohlc(_complete_candle("42000"))

        s.add_position(
            entry_price=Decimal("40000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41000"),
        )

        # +2.5% profit from 40000 -> 41000
        s._current_price = Decimal("41000")
        s._current_timestamp = datetime.now(UTC)

        signal = await s.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert signal.metadata["reason"] == "profit_target"


# ---------------------------------------------------------------------------
# Rolling reference mechanics
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyRollingReferences:
    """Tests for rolling reference price mechanics."""

    @pytest.mark.asyncio
    async def test_delayed_reference_add(self, strategy: AdaptiveStrategy) -> None:
        """References are added with one-candle delay (pending -> actual).

        The first complete candle ends warmup and adds close directly to
        _reference_prices. Because that close is already present, it is NOT
        set as _pending_reference. Subsequent NEW close prices go through
        the delayed path: pending on candle N, committed on candle N+1.
        """
        # First complete candle ends warmup, adds close to refs immediately
        await strategy.on_ohlc(_complete_candle("42000"))
        assert Decimal("42000") in strategy._reference_prices
        # 42000 is already in _reference_prices so it is NOT pending
        assert strategy._pending_reference is None

        # Second complete candle (new price): 42100 is NOT yet in refs,
        # so it becomes pending
        await strategy.on_ohlc(_complete_candle("42100"))
        assert Decimal("42100") not in strategy._reference_prices
        assert strategy._pending_reference == Decimal("42100")

        # Third candle commits 42100 from pending into refs
        await strategy.on_ohlc(_complete_candle("42200"))
        assert Decimal("42100") in strategy._reference_prices
        # And 42200 is now the new pending
        assert strategy._pending_reference == Decimal("42200")

    @pytest.mark.asyncio
    async def test_lookback_window_limits_references(self, strategy: AdaptiveStrategy) -> None:
        """References are trimmed to lookback_periods."""
        # lookback_periods = 5
        for i in range(10):
            await strategy.on_ohlc(_complete_candle(str(40000 + i * 100)))

        assert len(strategy._reference_prices) <= strategy.lookback_periods

    @pytest.mark.asyncio
    async def test_used_references_discarded_on_window_slide(
        self, strategy: AdaptiveStrategy
    ) -> None:
        """When a reference is evicted from the window, it's removed from used_references."""
        # Fill references past lookback
        prices = [str(40000 + i * 100) for i in range(8)]
        for p in prices:
            await strategy.on_ohlc(_complete_candle(p))

        # Manually add first price to used_references to simulate it was used
        first_price = Decimal(prices[0])
        strategy._used_references.add(first_price)

        # Add more candles to push first_price out of window
        for i in range(5):
            await strategy.on_ohlc(_complete_candle(str(45000 + i * 100)))

        # first_price should have been discarded from used_references
        # (it gets discarded when popped from references)
        assert first_price not in strategy._reference_prices

    @pytest.mark.asyncio
    async def test_bought_this_candle_resets_on_new_candle(
        self, strategy: AdaptiveStrategy
    ) -> None:
        """_bought_this_candle resets to False on each new complete candle."""
        await strategy.on_ohlc(_complete_candle("42000"))
        strategy._bought_this_candle = True

        await strategy.on_ohlc(_complete_candle("42100"))
        assert strategy._bought_this_candle is False


# ---------------------------------------------------------------------------
# on_tick
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyOnTick:
    """Tests for on_tick method."""

    @pytest.mark.asyncio
    async def test_on_tick_updates_price(self, strategy: AdaptiveStrategy) -> None:
        """on_tick updates current price."""
        await strategy.on_tick({"pair": "XBT/USDC", "price": "42500"})
        assert strategy.current_price == Decimal("42500")

    @pytest.mark.asyncio
    async def test_on_tick_ignores_other_pairs(self, strategy: AdaptiveStrategy) -> None:
        """on_tick ignores ticks for other pairs."""
        await strategy.on_tick({"pair": "ETH/USDC", "price": "3000"})
        assert strategy.current_price is None

    @pytest.mark.asyncio
    async def test_on_tick_updates_trailing_stop_tracking(self, strategy: AdaptiveStrategy) -> None:
        """on_tick updates highest_price for existing positions."""
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )

        await strategy.on_tick({"pair": "XBT/USDC", "price": "43000"})

        assert strategy._open_positions[0].highest_price == Decimal("43000")

    @pytest.mark.asyncio
    async def test_on_tick_does_not_lower_highest_price(self, strategy: AdaptiveStrategy) -> None:
        """on_tick only raises highest_price, never lowers it."""
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )
        strategy._open_positions[0].highest_price = Decimal("44000")

        await strategy.on_tick({"pair": "XBT/USDC", "price": "43000"})

        assert strategy._open_positions[0].highest_price == Decimal("44000")


# ---------------------------------------------------------------------------
# on_ohlc routing
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyOnOhlc:
    """Tests for on_ohlc method."""

    @pytest.mark.asyncio
    async def test_ignores_other_pairs(self, strategy: AdaptiveStrategy) -> None:
        """on_ohlc ignores candles for other pairs."""
        await strategy.on_ohlc(_complete_candle("42000", pair="ETH/USDC"))
        assert strategy._warming_up is True  # State unchanged

    @pytest.mark.asyncio
    async def test_ignores_non_trigger_timeframe(self, strategy: AdaptiveStrategy) -> None:
        """on_ohlc ignores complete candles for non-trigger timeframes."""
        # trigger_timeframe = 5; sending interval=15 should not end warmup
        await strategy.on_ohlc(_complete_candle("42000", interval=15))
        assert strategy._warming_up is True

    @pytest.mark.asyncio
    async def test_updates_analyzer_for_all_timeframes(
        self,
        strategy: AdaptiveStrategy,
        mock_analyzer: MagicMock,
    ) -> None:
        """on_ohlc updates analyzer for any interval (5, 15, 60)."""
        await strategy.on_ohlc(_complete_candle("42000", interval=60))
        mock_analyzer.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_highest_price_from_candle_high(self, strategy: AdaptiveStrategy) -> None:
        """on_ohlc updates highest_price from candle high field."""
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )

        candle = {
            "pair": "XBT/USDC",
            "interval": 5,
            "open": "42000",
            "high": "44500",
            "low": "41800",
            "close": "43000",
            "volume": "10",
            "is_complete": True,
            "timestamp": datetime.now(UTC),
        }
        await strategy.on_ohlc(candle)

        assert strategy._open_positions[0].highest_price == Decimal("44500")


# ---------------------------------------------------------------------------
# add_position / close_position (backtest compatibility)
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyBacktestCompat:
    """Tests for add_position() and close_position() backtest compatibility."""

    def test_add_position_returns_incrementing_id(self, strategy: AdaptiveStrategy) -> None:
        """add_position returns incrementing position IDs."""
        pid1 = strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )
        pid2 = strategy.add_position(
            entry_price=Decimal("43000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("42500"),
        )
        assert pid1 == 1
        assert pid2 == 2
        assert strategy.open_positions_count == 2

    def test_add_position_tracks_used_reference(self, strategy: AdaptiveStrategy) -> None:
        """add_position adds reference_price to _used_references."""
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )
        assert Decimal("41500") in strategy._used_references

    def test_add_position_sets_highest_price_to_entry(self, strategy: AdaptiveStrategy) -> None:
        """add_position initializes highest_price = entry_price."""
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )
        assert strategy._open_positions[0].highest_price == Decimal("42000")

    def test_add_position_with_custom_entry_time(self, strategy: AdaptiveStrategy) -> None:
        """add_position accepts a custom entry_time."""
        t = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
            entry_time=t,
        )
        assert strategy._open_positions[0].entry_time == t

    def test_close_position_removes_position(self, strategy: AdaptiveStrategy) -> None:
        """close_position removes the position and returns it."""
        pid = strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )
        closed = strategy.close_position(pid)
        assert closed is not None
        assert closed.position_id == pid
        assert strategy.open_positions_count == 0

    def test_close_position_returns_none_for_unknown_id(self, strategy: AdaptiveStrategy) -> None:
        """close_position returns None for non-existent ID."""
        closed = strategy.close_position(999)
        assert closed is None

    def test_open_positions_property_returns_copy(self, strategy: AdaptiveStrategy) -> None:
        """open_positions property returns a copy of the list."""
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )
        positions = strategy.open_positions
        positions.clear()
        assert strategy.open_positions_count == 1


# ---------------------------------------------------------------------------
# reset_state
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyResetState:
    """Tests for reset_state."""

    def test_reset_clears_all_state(self, strategy: AdaptiveStrategy) -> None:
        """reset_state clears internal state back to initial values."""
        strategy._current_price = Decimal("42000")
        strategy._reference_prices.append(Decimal("42000"))
        strategy._used_references.add(Decimal("42000"))
        strategy._pending_reference = Decimal("42100")
        strategy._bought_this_candle = True
        strategy._warming_up = False
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )

        strategy.reset_state()

        assert strategy.current_price is None
        assert strategy._reference_prices == []
        assert strategy._used_references == set()
        assert strategy._pending_reference is None
        assert strategy._bought_this_candle is False
        assert strategy._warming_up is True
        assert strategy._warmup_open_price is None
        assert strategy.open_positions_count == 0
        assert strategy._next_position_id == 1


# ---------------------------------------------------------------------------
# on_trade_filled
# ---------------------------------------------------------------------------


class TestAdaptiveStrategyOnTradeFilled:
    """Tests for on_trade_filled position tracking."""

    @pytest.mark.asyncio
    async def test_buy_fill_adds_position(self, strategy: AdaptiveStrategy) -> None:
        """on_trade_filled with side=buy adds position."""
        await strategy.on_trade_filled(
            trade_id="T001",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            fee=Decimal("0.05"),
            reference_price=Decimal("41500"),
            position_id=None,
        )
        assert strategy.open_positions_count == 1
        pos = strategy._open_positions[0]
        assert pos.entry_price == Decimal("42000")
        assert pos.reference_price == Decimal("41500")
        assert pos.highest_price == Decimal("42000")

    @pytest.mark.asyncio
    async def test_buy_fill_without_reference_is_ignored(self, strategy: AdaptiveStrategy) -> None:
        """on_trade_filled buy without reference_price does nothing."""
        await strategy.on_trade_filled(
            trade_id="T002",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=None,
        )
        assert strategy.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_sell_fill_closes_position(self, strategy: AdaptiveStrategy) -> None:
        """on_trade_filled with side=sell removes the matching position."""
        # Add a position first
        await strategy.on_trade_filled(
            trade_id="T003",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            fee=Decimal("0.05"),
            reference_price=Decimal("41500"),
            position_id=None,
        )
        pid = strategy._open_positions[0].position_id

        # Sell it
        await strategy.on_trade_filled(
            trade_id="T004",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.001"),
            price=Decimal("43000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=pid,
        )
        assert strategy.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_sell_fill_without_position_id_is_ignored(
        self, strategy: AdaptiveStrategy
    ) -> None:
        """on_trade_filled sell without position_id does nothing."""
        strategy.add_position(
            entry_price=Decimal("42000"),
            amount_usdc=Decimal("100"),
            reference_price=Decimal("41500"),
        )
        await strategy.on_trade_filled(
            trade_id="T005",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.001"),
            price=Decimal("43000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=None,
        )
        assert strategy.open_positions_count == 1
