"""Tests for multi-timeframe analysis module.

This module tests the MultiTimeframeAnalyzer including:
- MarketRegime detection (BULL/BEAR/NEUTRAL) based on EMA spread
- TimeframeZone classification (OVERSOLD/OVERBOUGHT/NEUTRAL) based on RSI + Bollinger
- Adaptive buy/sell threshold calculations
- Warmup behavior (analyze returns None before enough data)
- update() routing to correct indicators per timeframe
- analyze() returning valid MultiTimeframeAnalysis when warmed up
- Position sizing recommendations
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from krakenbot.indicators.multi_timeframe import (
    MarketRegime,
    MultiTimeframeAnalysis,
    MultiTimeframeAnalyzer,
    TimeframeZone,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle(
    close: Decimal,
    high: Decimal | None = None,
    low: Decimal | None = None,
    volume: Decimal = Decimal("1.0"),
) -> dict:
    """Build a minimal candle dict for update().

    Args:
        close: Close price.
        high: High price (defaults to close + 50).
        low: Low price (defaults to close - 50).
        volume: Volume.

    Returns:
        Dict with open/high/low/close/volume keys.
    """
    if high is None:
        high = close + Decimal("50")
    if low is None:
        low = close - Decimal("50")
    return {
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _feed_steady_candles(
    analyzer: MultiTimeframeAnalyzer,
    price: Decimal,
    count: int,
    interval: int,
    *,
    volume: Decimal = Decimal("1.0"),
) -> None:
    """Feed *count* candles at a fixed price into *analyzer*.

    Args:
        analyzer: The analyzer to feed.
        price: Constant close price.
        count: Number of candles.
        interval: Candle interval (5, 15, or 60).
        volume: Volume per candle.
    """
    for _ in range(count):
        analyzer.update(_make_candle(price, volume=volume), interval)


def _build_warmed_up_analyzer(
    *,
    warmup: int = 5,
    ema_fast: int = 3,
    ema_slow: int = 5,
    atr_period: int = 3,
    rsi_period: int = 5,
    bb_period: int = 5,
    regime_neutral_threshold: float = 0.5,
    price_1h: Decimal = Decimal("50000"),
    price_15m: Decimal = Decimal("50000"),
    price_5m: Decimal = Decimal("50000"),
) -> MultiTimeframeAnalyzer:
    """Return an analyzer that has passed the warmup gate.

    Uses small periods so that warmup can be satisfied with few candles.

    Args:
        warmup: warmup_candles_1h.
        ema_fast: Fast EMA period.
        ema_slow: Slow EMA period.
        atr_period: ATR period.
        rsi_period: RSI period.
        bb_period: Bollinger Bands period.
        regime_neutral_threshold: Neutral threshold for regime classification.
        price_1h: Steady price for 1h candles.
        price_15m: Steady price for 15m candles.
        price_5m: Steady price for 5m candles.

    Returns:
        A warmed-up MultiTimeframeAnalyzer.
    """
    analyzer = MultiTimeframeAnalyzer(
        ema_fast_period=ema_fast,
        ema_slow_period=ema_slow,
        atr_period=atr_period,
        rsi_period=rsi_period,
        bb_period=bb_period,
        regime_neutral_threshold=regime_neutral_threshold,
        warmup_candles_1h=warmup,
    )
    # Feed enough data so all indicators are ready.
    # The slowest indicator is ema_slow (period=5) or rsi (period+1=6 candles).
    # Feed a generous number to be safe.
    feed_count = max(warmup, ema_slow, rsi_period + 1, bb_period) + 5
    _feed_steady_candles(analyzer, price_1h, feed_count, 60)
    _feed_steady_candles(analyzer, price_15m, feed_count, 15)
    _feed_steady_candles(analyzer, price_5m, feed_count, 5)
    return analyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def small_analyzer() -> MultiTimeframeAnalyzer:
    """Analyzer with small periods (not yet warmed up)."""
    return MultiTimeframeAnalyzer(
        ema_fast_period=3,
        ema_slow_period=5,
        atr_period=3,
        rsi_period=5,
        bb_period=5,
        regime_neutral_threshold=0.5,
        warmup_candles_1h=10,
    )


@pytest.fixture
def warmed_analyzer() -> MultiTimeframeAnalyzer:
    """Analyzer that has already passed warmup with neutral state."""
    return _build_warmed_up_analyzer()


# ===========================================================================
# MarketRegime detection
# ===========================================================================


class TestMarketRegimeDetection:
    """Tests for _classify_regime and regime detection via analyze()."""

    def test_neutral_regime_when_ema_spread_small(self) -> None:
        """Regime is NEUTRAL when EMA spread is within threshold."""
        analyzer = MultiTimeframeAnalyzer(
            ema_fast_period=3,
            ema_slow_period=5,
            regime_neutral_threshold=0.5,
            warmup_candles_1h=1,
        )
        # An EMA spread of 0.0 (identical prices) should yield NEUTRAL.
        assert analyzer._classify_regime(0.0) == MarketRegime.NEUTRAL
        assert analyzer._classify_regime(0.3) == MarketRegime.NEUTRAL
        assert analyzer._classify_regime(-0.3) == MarketRegime.NEUTRAL

    def test_bull_regime_when_ema_spread_positive(self) -> None:
        """Regime is BULL when EMA spread exceeds threshold."""
        analyzer = MultiTimeframeAnalyzer(regime_neutral_threshold=0.5)
        assert analyzer._classify_regime(0.6) == MarketRegime.BULL
        assert analyzer._classify_regime(0.9) == MarketRegime.BULL

    def test_strong_bull_regime(self) -> None:
        """Regime is STRONG_BULL when EMA spread > 2 * threshold."""
        analyzer = MultiTimeframeAnalyzer(regime_neutral_threshold=0.5)
        assert analyzer._classify_regime(1.1) == MarketRegime.STRONG_BULL
        assert analyzer._classify_regime(3.0) == MarketRegime.STRONG_BULL

    def test_bear_regime_when_ema_spread_negative(self) -> None:
        """Regime is BEAR when EMA spread is below -threshold."""
        analyzer = MultiTimeframeAnalyzer(regime_neutral_threshold=0.5)
        assert analyzer._classify_regime(-0.6) == MarketRegime.BEAR
        assert analyzer._classify_regime(-0.9) == MarketRegime.BEAR

    def test_strong_bear_regime(self) -> None:
        """Regime is STRONG_BEAR when EMA spread < -2 * threshold."""
        analyzer = MultiTimeframeAnalyzer(regime_neutral_threshold=0.5)
        assert analyzer._classify_regime(-1.1) == MarketRegime.STRONG_BEAR
        assert analyzer._classify_regime(-5.0) == MarketRegime.STRONG_BEAR

    def test_regime_boundary_exactly_at_threshold(self) -> None:
        """Boundary: spread exactly at threshold is still NEUTRAL."""
        analyzer = MultiTimeframeAnalyzer(regime_neutral_threshold=0.5)
        # Spread == +0.5 -> NOT > threshold, so NEUTRAL
        assert analyzer._classify_regime(0.5) == MarketRegime.NEUTRAL
        assert analyzer._classify_regime(-0.5) == MarketRegime.NEUTRAL

    def test_regime_detected_via_analyze(self) -> None:
        """Regime is reflected in the analysis result after feeding diverging EMAs."""
        # Feed rising prices so fast EMA > slow EMA => BULL or STRONG_BULL
        analyzer = MultiTimeframeAnalyzer(
            ema_fast_period=3,
            ema_slow_period=5,
            atr_period=3,
            rsi_period=5,
            bb_period=5,
            regime_neutral_threshold=0.5,
            warmup_candles_1h=5,
        )
        # Feed 5 steady candles first for baseline
        for _ in range(5):
            analyzer.update(_make_candle(Decimal("50000")), 60)
        # Now feed rising prices to push fast EMA above slow EMA
        for i in range(10):
            price = Decimal("50000") + Decimal(str(i * 500))
            analyzer.update(_make_candle(price), 60)
        # Feed 15m and 5m so analysis doesn't fail
        _feed_steady_candles(analyzer, Decimal("50000"), 15, 15)
        _feed_steady_candles(analyzer, Decimal("50000"), 15, 5)

        result = analyzer.analyze()
        assert result is not None
        assert result.regime in (MarketRegime.BULL, MarketRegime.STRONG_BULL)


# ===========================================================================
# TimeframeZone classification
# ===========================================================================


class TestTimeframeZoneClassification:
    """Tests for _classify_zone (RSI + Bollinger logic)."""

    def test_neutral_zone_when_rsi_is_none(self) -> None:
        """Zone is NEUTRAL if RSI is not available."""
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer._classify_zone(None, None) == TimeframeZone.NEUTRAL

    def test_oversold_zone_from_low_rsi(self) -> None:
        """Zone is OVERSOLD when RSI < 30."""
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer._classify_zone(25.0, None) == TimeframeZone.OVERSOLD
        assert analyzer._classify_zone(10.0, None) == TimeframeZone.OVERSOLD

    def test_overbought_zone_from_high_rsi(self) -> None:
        """Zone is OVERBOUGHT when RSI > 70."""
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer._classify_zone(75.0, None) == TimeframeZone.OVERBOUGHT
        assert analyzer._classify_zone(90.0, None) == TimeframeZone.OVERBOUGHT

    def test_neutral_zone_in_middle_rsi(self) -> None:
        """Zone is NEUTRAL when RSI between 30 and 70 and no BB signal."""
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer._classify_zone(50.0, None) == TimeframeZone.NEUTRAL
        assert analyzer._classify_zone(30.0, None) == TimeframeZone.NEUTRAL
        assert analyzer._classify_zone(70.0, None) == TimeframeZone.NEUTRAL

    def test_oversold_from_bollinger_percent_b(self) -> None:
        """Zone is OVERSOLD when RSI neutral but percent_b < 0."""
        analyzer = MultiTimeframeAnalyzer()

        class MockBB:
            percent_b = -0.1

        assert analyzer._classify_zone(45.0, MockBB()) == TimeframeZone.OVERSOLD

    def test_overbought_from_bollinger_percent_b(self) -> None:
        """Zone is OVERBOUGHT when RSI neutral but percent_b > 1."""
        analyzer = MultiTimeframeAnalyzer()

        class MockBB:
            percent_b = 1.2

        assert analyzer._classify_zone(55.0, MockBB()) == TimeframeZone.OVERBOUGHT

    def test_neutral_from_bollinger_within_bands(self) -> None:
        """Zone remains NEUTRAL when percent_b is between 0 and 1."""
        analyzer = MultiTimeframeAnalyzer()

        class MockBB:
            percent_b = 0.5

        assert analyzer._classify_zone(50.0, MockBB()) == TimeframeZone.NEUTRAL

    def test_rsi_takes_priority_over_bollinger(self) -> None:
        """RSI extremes override Bollinger: RSI < 30 => OVERSOLD regardless of BB."""
        analyzer = MultiTimeframeAnalyzer()

        class MockBB:
            percent_b = 1.5  # Would be overbought

        # RSI is oversold, should win
        assert analyzer._classify_zone(20.0, MockBB()) == TimeframeZone.OVERSOLD


# ===========================================================================
# Adaptive thresholds
# ===========================================================================


class TestAdaptiveThresholds:
    """Tests for _calc_adaptive_thresholds."""

    def test_neutral_regime_low_volatility(self) -> None:
        """Neutral regime with normal vol returns base-like thresholds."""
        analyzer = MultiTimeframeAnalyzer()
        buy, sell, sl = analyzer._calc_adaptive_thresholds(MarketRegime.NEUTRAL, volatility_pct=1.5)
        # regime_mult=1.0, vol_mult=1.5/1.5=1.0 => buy=-1*1*1=-1, sell=2*1*1=2, sl=5*1*1=5
        assert buy == pytest.approx(-1.0, abs=0.01)
        assert sell == pytest.approx(2.0, abs=0.01)
        assert sl == pytest.approx(5.0, abs=0.01)

    def test_bull_regime_tighter_buy_wider_sell(self) -> None:
        """Bull regime: tighter buy (closer to 0), wider sell, wider stop-loss."""
        analyzer = MultiTimeframeAnalyzer()
        buy, sell, sl = analyzer._calc_adaptive_thresholds(MarketRegime.BULL, volatility_pct=1.5)
        # regime_mult=0.85, sell_regime_mult=1.3, sl_regime_mult=1.2, vol_mult=1.0
        assert buy == pytest.approx(-1.0 * 0.85 * 1.0, abs=0.01)
        assert sell == pytest.approx(2.0 * 1.3 * 1.0, abs=0.01)
        assert sl == pytest.approx(5.0 * 1.2 * 1.0, abs=0.01)

    def test_strong_bull_tightest_buy(self) -> None:
        """Strong bull: even tighter buy, widest sell, widest stop-loss."""
        analyzer = MultiTimeframeAnalyzer()
        buy, sell, sl = analyzer._calc_adaptive_thresholds(
            MarketRegime.STRONG_BULL, volatility_pct=1.5
        )
        # regime_mult=0.7, sell_regime_mult=1.5, sl_regime_mult=1.5
        assert buy == pytest.approx(-1.0 * 0.7 * 1.0, abs=0.01)
        assert sell == pytest.approx(2.0 * 1.5 * 1.0, abs=0.01)
        assert sl == pytest.approx(5.0 * 1.5 * 1.0, abs=0.01)

    def test_bear_regime_wider_buy_tighter_sell(self) -> None:
        """Bear regime: wider buy (bigger drop needed), tighter sell, tighter stop-loss."""
        analyzer = MultiTimeframeAnalyzer()
        buy, sell, sl = analyzer._calc_adaptive_thresholds(MarketRegime.BEAR, volatility_pct=1.5)
        # regime_mult=1.5, sell_regime_mult=0.8, sl_regime_mult=0.8
        assert buy == pytest.approx(-1.0 * 1.5 * 1.0, abs=0.01)
        assert sell == pytest.approx(2.0 * 0.8 * 1.0, abs=0.01)
        assert sl == pytest.approx(5.0 * 0.8 * 1.0, abs=0.01)

    def test_strong_bear_widest_buy(self) -> None:
        """Strong bear: widest buy, tightest sell, tightest stop-loss."""
        analyzer = MultiTimeframeAnalyzer()
        buy, sell, sl = analyzer._calc_adaptive_thresholds(
            MarketRegime.STRONG_BEAR, volatility_pct=1.5
        )
        # regime_mult=2.0, sell_regime_mult=0.6, sl_regime_mult=0.6
        assert buy == pytest.approx(-1.0 * 2.0 * 1.0, abs=0.01)
        assert sell == pytest.approx(2.0 * 0.6 * 1.0, abs=0.01)
        assert sl == pytest.approx(5.0 * 0.6 * 1.0, abs=0.01)

    def test_high_volatility_widens_thresholds(self) -> None:
        """Higher volatility widens both buy and sell thresholds."""
        analyzer = MultiTimeframeAnalyzer()
        buy_low, sell_low, _ = analyzer._calc_adaptive_thresholds(
            MarketRegime.NEUTRAL, volatility_pct=0.75
        )
        buy_high, sell_high, _ = analyzer._calc_adaptive_thresholds(
            MarketRegime.NEUTRAL, volatility_pct=3.0
        )
        # vol 0.75 => vol_mult = 0.75/1.5 = 0.5
        # vol 3.0  => vol_mult = 3.0/1.5 = 2.0
        assert buy_high < buy_low  # More negative = wider buy
        assert sell_high > sell_low  # Larger = wider sell

    def test_volatility_multiplier_clamped(self) -> None:
        """Volatility multiplier is clamped between 0.5 and 2.0."""
        analyzer = MultiTimeframeAnalyzer()
        # Very low vol
        buy_lo, sell_lo, _ = analyzer._calc_adaptive_thresholds(
            MarketRegime.NEUTRAL, volatility_pct=0.01
        )
        # Very high vol
        buy_hi, sell_hi, _ = analyzer._calc_adaptive_thresholds(
            MarketRegime.NEUTRAL, volatility_pct=100.0
        )
        # Both should be clamped; vol_mult floors at 0.5, caps at 2.0
        # buy = -1 * 1.0 * 0.5 = -0.5 (clamped) vs -1 * 1.0 * 2.0 = -2.0
        assert buy_lo == pytest.approx(-0.5, abs=0.01)
        assert buy_hi == pytest.approx(-2.0, abs=0.01)

    def test_thresholds_clamped_to_safe_range(self) -> None:
        """Buy clamped to [-5, -0.3], sell clamped to [0.5, 10], stop-loss to [1.5, 15]."""
        analyzer = MultiTimeframeAnalyzer()
        buy, sell, sl = analyzer._calc_adaptive_thresholds(MarketRegime.NEUTRAL, volatility_pct=1.5)
        assert -5.0 <= buy <= -0.3
        assert 0.5 <= sell <= 10.0
        assert 1.5 <= sl <= 15.0


# ===========================================================================
# Warmup behavior
# ===========================================================================


class TestWarmup:
    """Tests for warmup gating -- analyze() returns None until enough data."""

    def test_analyze_returns_none_before_warmup(
        self, small_analyzer: MultiTimeframeAnalyzer
    ) -> None:
        """analyze() returns None with fewer than warmup_candles_1h candles."""
        # Feed fewer candles than warmup (10)
        _feed_steady_candles(small_analyzer, Decimal("50000"), 5, 60)
        _feed_steady_candles(small_analyzer, Decimal("50000"), 20, 15)
        _feed_steady_candles(small_analyzer, Decimal("50000"), 20, 5)
        assert small_analyzer.analyze() is None

    def test_is_ready_false_before_warmup(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """is_ready is False before warmup threshold is reached."""
        _feed_steady_candles(small_analyzer, Decimal("50000"), 5, 60)
        assert small_analyzer.is_ready is False

    def test_analyze_returns_none_ema_not_ready(self) -> None:
        """analyze() returns None if candle count met but EMA not ready.

        This happens when warmup_candles_1h < ema_slow_period.
        """
        analyzer = MultiTimeframeAnalyzer(
            ema_fast_period=3,
            ema_slow_period=50,
            warmup_candles_1h=5,
        )
        # Feed 5 candles (meets warmup) but slow EMA needs 50
        _feed_steady_candles(analyzer, Decimal("50000"), 5, 60)
        assert analyzer.analyze() is None

    def test_analyze_returns_result_after_warmup(self) -> None:
        """analyze() returns a result once warmup is fully satisfied."""
        analyzer = _build_warmed_up_analyzer()
        result = analyzer.analyze()
        assert result is not None
        assert isinstance(result, MultiTimeframeAnalysis)

    def test_is_ready_true_after_warmup(self) -> None:
        """is_ready becomes True once warmup and EMA readiness are met."""
        analyzer = _build_warmed_up_analyzer()
        assert analyzer.is_ready is True


# ===========================================================================
# update() routing
# ===========================================================================


class TestUpdateRouting:
    """Tests that update() routes candles to the correct indicator set."""

    def test_update_60_increments_1h_count(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """Interval=60 candles increment 1h candle counter only."""
        small_analyzer.update(_make_candle(Decimal("50000")), 60)
        assert small_analyzer.candle_counts["1h"] == 1
        assert small_analyzer.candle_counts["15m"] == 0
        assert small_analyzer.candle_counts["5m"] == 0

    def test_update_15_increments_15m_count(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """Interval=15 candles increment 15m candle counter only."""
        small_analyzer.update(_make_candle(Decimal("50000")), 15)
        assert small_analyzer.candle_counts["15m"] == 1
        assert small_analyzer.candle_counts["1h"] == 0
        assert small_analyzer.candle_counts["5m"] == 0

    def test_update_5_increments_5m_count(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """Interval=5 candles increment 5m candle counter only."""
        small_analyzer.update(_make_candle(Decimal("50000")), 5)
        assert small_analyzer.candle_counts["5m"] == 1
        assert small_analyzer.candle_counts["1h"] == 0
        assert small_analyzer.candle_counts["15m"] == 0

    def test_update_unknown_interval_ignored(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """Unknown interval (e.g. 30) does not change any counter."""
        small_analyzer.update(_make_candle(Decimal("50000")), 30)
        counts = small_analyzer.candle_counts
        assert counts["1h"] == 0
        assert counts["15m"] == 0
        assert counts["5m"] == 0

    def test_update_stores_last_close_per_timeframe(
        self, small_analyzer: MultiTimeframeAnalyzer
    ) -> None:
        """update() stores last close price per timeframe."""
        small_analyzer.update(_make_candle(Decimal("50000")), 60)
        small_analyzer.update(_make_candle(Decimal("49000")), 15)
        small_analyzer.update(_make_candle(Decimal("48000")), 5)
        assert small_analyzer._last_close_1h == Decimal("50000")
        assert small_analyzer._last_close_15m == Decimal("49000")
        assert small_analyzer._last_close_5m == Decimal("48000")

    def test_update_60_feeds_ema_and_atr(self) -> None:
        """1h candles update EMA (fast/slow), RSI, and ATR indicators."""
        analyzer = MultiTimeframeAnalyzer(
            ema_fast_period=3,
            ema_slow_period=3,
            atr_period=3,
            rsi_period=3,
            warmup_candles_1h=3,
        )
        for _ in range(5):
            analyzer.update(_make_candle(Decimal("50000")), 60)
        # After 5 candles with period=3, EMAs should be ready
        assert analyzer._ema_fast_1h.is_ready is True
        assert analyzer._ema_slow_1h.is_ready is True
        assert analyzer._atr_1h.is_ready is True
        assert analyzer._rsi_1h.is_ready is True

    def test_update_15_feeds_rsi_and_bb(self) -> None:
        """15m candles update RSI and Bollinger Bands indicators."""
        analyzer = MultiTimeframeAnalyzer(
            rsi_period=3,
            bb_period=3,
        )
        for _ in range(5):
            analyzer.update(_make_candle(Decimal("50000")), 15)
        assert analyzer._rsi_15m.is_ready is True
        assert analyzer._bb_15m.is_ready is True

    def test_update_5_feeds_rsi_and_bb(self) -> None:
        """5m candles update RSI and Bollinger Bands indicators."""
        analyzer = MultiTimeframeAnalyzer(
            rsi_period=3,
            bb_period=3,
        )
        for _ in range(5):
            analyzer.update(_make_candle(Decimal("50000")), 5)
        assert analyzer._rsi_5m.is_ready is True
        assert analyzer._bb_5m.is_ready is True

    def test_update_tracks_volume(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """Volume is tracked in deques for 5m and 15m timeframes."""
        small_analyzer.update(_make_candle(Decimal("50000"), volume=Decimal("10")), 15)
        small_analyzer.update(_make_candle(Decimal("50000"), volume=Decimal("20")), 5)
        assert len(small_analyzer._volume_15m) == 1
        assert small_analyzer._volume_15m[-1] == Decimal("10")
        assert len(small_analyzer._volume_5m) == 1
        assert small_analyzer._volume_5m[-1] == Decimal("20")


# ===========================================================================
# Full analyze() output
# ===========================================================================


class TestAnalyzeOutput:
    """Tests for analyze() returning a valid MultiTimeframeAnalysis."""

    def test_analyze_returns_all_fields(self, warmed_analyzer: MultiTimeframeAnalyzer) -> None:
        """analyze() returns a result with all expected fields populated."""
        result = warmed_analyzer.analyze()
        assert result is not None

        # Regime and zones
        assert isinstance(result.regime, MarketRegime)
        assert isinstance(result.zone_15m, TimeframeZone)
        assert isinstance(result.zone_5m, TimeframeZone)

        # Numeric fields
        assert isinstance(result.trend_strength, float)
        assert isinstance(result.volatility_atr, Decimal)
        assert isinstance(result.volatility_pct, float)
        assert isinstance(result.volume_ratio_5m, float)
        assert isinstance(result.volume_ratio_15m, float)

        # Thresholds
        assert result.recommended_buy_threshold < 0
        assert result.recommended_sell_threshold > 0

        # Position sizing
        assert result.recommended_position_size_pct > 0
        assert result.recommended_max_positions > 0

    def test_analyze_steady_prices_neutral_regime(
        self, warmed_analyzer: MultiTimeframeAnalyzer
    ) -> None:
        """Steady prices produce NEUTRAL regime and near-zero trend strength."""
        result = warmed_analyzer.analyze()
        assert result is not None
        assert result.regime == MarketRegime.NEUTRAL
        assert result.trend_strength < 0.1  # Essentially zero

    def test_analyze_rsi_values_populated(self) -> None:
        """RSI values per timeframe are populated in the analysis."""
        # Use alternating prices so RSI converges near 50 rather than 100
        analyzer = MultiTimeframeAnalyzer(
            ema_fast_period=3,
            ema_slow_period=5,
            atr_period=3,
            rsi_period=5,
            bb_period=5,
            regime_neutral_threshold=0.5,
            warmup_candles_1h=5,
        )
        feed_count = 15
        for i in range(feed_count):
            # Alternate between two prices to create balanced gains/losses
            price = Decimal("50000") if i % 2 == 0 else Decimal("50100")
            for interval in (60, 15, 5):
                analyzer.update(_make_candle(price), interval)

        result = analyzer.analyze()
        assert result is not None
        assert result.rsi_1h is not None
        assert 30.0 <= result.rsi_1h <= 70.0
        assert result.rsi_15m is not None
        assert result.rsi_5m is not None

    def test_analyze_volume_ratio_default(self) -> None:
        """Volume ratio is ~1.0 when all volumes are equal."""
        analyzer = _build_warmed_up_analyzer()
        result = analyzer.analyze()
        assert result is not None
        assert result.volume_ratio_5m == pytest.approx(1.0, abs=0.01)
        assert result.volume_ratio_15m == pytest.approx(1.0, abs=0.01)

    def test_analyze_metadata_is_dict(self, warmed_analyzer: MultiTimeframeAnalyzer) -> None:
        """metadata field is a dict (empty by default)."""
        result = warmed_analyzer.analyze()
        assert result is not None
        assert isinstance(result.metadata, dict)


# ===========================================================================
# Position sizing recommendations
# ===========================================================================


class TestPositionSizing:
    """Tests for adaptive position sizing and max positions."""

    def test_position_size_higher_in_bull(self) -> None:
        """Bull regime yields larger position size than bear."""
        analyzer = MultiTimeframeAnalyzer()
        size_bull = analyzer._calc_adaptive_position_size(MarketRegime.BULL, volatility_pct=1.5)
        size_bear = analyzer._calc_adaptive_position_size(MarketRegime.BEAR, volatility_pct=1.5)
        assert size_bull > size_bear

    def test_position_size_lower_in_high_vol(self) -> None:
        """Higher volatility yields smaller position size."""
        analyzer = MultiTimeframeAnalyzer()
        size_low_vol = analyzer._calc_adaptive_position_size(
            MarketRegime.NEUTRAL, volatility_pct=0.5
        )
        size_high_vol = analyzer._calc_adaptive_position_size(
            MarketRegime.NEUTRAL, volatility_pct=3.0
        )
        assert size_low_vol > size_high_vol

    def test_position_size_clamped(self) -> None:
        """Position size is clamped between 1.0 and 10.0."""
        analyzer = MultiTimeframeAnalyzer()
        # Strong bull, very low vol => high size => should be clamped at 10
        size = analyzer._calc_adaptive_position_size(MarketRegime.STRONG_BULL, volatility_pct=0.01)
        assert 1.0 <= size <= 10.0
        # Strong bear, very high vol => low size => should be clamped at 1
        size = analyzer._calc_adaptive_position_size(MarketRegime.STRONG_BEAR, volatility_pct=100.0)
        assert 1.0 <= size <= 10.0

    def test_max_positions_bull_vs_bear(self) -> None:
        """Max positions is higher in bull than in bear."""
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer._calc_adaptive_max_positions(MarketRegime.STRONG_BULL) == 7
        assert analyzer._calc_adaptive_max_positions(MarketRegime.BULL) == 5
        assert analyzer._calc_adaptive_max_positions(MarketRegime.NEUTRAL) == 4
        assert analyzer._calc_adaptive_max_positions(MarketRegime.BEAR) == 3
        assert analyzer._calc_adaptive_max_positions(MarketRegime.STRONG_BEAR) == 2

    def test_position_sizing_in_analysis(self) -> None:
        """Position sizing fields are present in full analysis output."""
        analyzer = _build_warmed_up_analyzer()
        result = analyzer.analyze()
        assert result is not None
        assert 1.0 <= result.recommended_position_size_pct <= 10.0
        assert 2 <= result.recommended_max_positions <= 7


# ===========================================================================
# Volume ratio helper
# ===========================================================================


class TestVolumeRatio:
    """Tests for _calc_volume_ratio."""

    def test_volume_ratio_with_single_entry(self) -> None:
        """Returns 1.0 when fewer than 2 volumes are available."""
        from collections import deque

        analyzer = MultiTimeframeAnalyzer()
        volumes: deque[Decimal] = deque([Decimal("100")])
        assert analyzer._calc_volume_ratio(volumes) == 1.0

    def test_volume_ratio_empty(self) -> None:
        """Returns 1.0 for empty deque."""
        from collections import deque

        analyzer = MultiTimeframeAnalyzer()
        volumes: deque[Decimal] = deque()
        assert analyzer._calc_volume_ratio(volumes) == 1.0

    def test_volume_ratio_uniform(self) -> None:
        """Returns ~1.0 when all volumes are equal."""
        from collections import deque

        analyzer = MultiTimeframeAnalyzer()
        volumes: deque[Decimal] = deque([Decimal("10")] * 5)
        assert analyzer._calc_volume_ratio(volumes) == pytest.approx(1.0, abs=0.01)

    def test_volume_ratio_spike(self) -> None:
        """Returns > 1.0 when latest volume is above average."""
        from collections import deque

        analyzer = MultiTimeframeAnalyzer()
        volumes: deque[Decimal] = deque(
            [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("30")]
        )
        # avg = (10+10+10+30)/4 = 15; ratio = 30/15 = 2.0
        assert analyzer._calc_volume_ratio(volumes) == pytest.approx(2.0, abs=0.01)

    def test_volume_ratio_drop(self) -> None:
        """Returns < 1.0 when latest volume is below average."""
        from collections import deque

        analyzer = MultiTimeframeAnalyzer()
        volumes: deque[Decimal] = deque(
            [Decimal("30"), Decimal("30"), Decimal("30"), Decimal("10")]
        )
        # avg = (30+30+30+10)/4 = 25; ratio = 10/25 = 0.4
        assert analyzer._calc_volume_ratio(volumes) == pytest.approx(0.4, abs=0.01)

    def test_volume_ratio_zero_average(self) -> None:
        """Returns 1.0 when average is zero (all zero volumes)."""
        from collections import deque

        analyzer = MultiTimeframeAnalyzer()
        volumes: deque[Decimal] = deque([Decimal("0"), Decimal("0")])
        assert analyzer._calc_volume_ratio(volumes) == 1.0


# ===========================================================================
# Candle counts property
# ===========================================================================


class TestCandleCounts:
    """Tests for the candle_counts property."""

    def test_initial_counts_are_zero(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """All candle counts start at 0."""
        counts = small_analyzer.candle_counts
        assert counts == {"1h": 0, "15m": 0, "5m": 0}

    def test_counts_accumulate_correctly(self, small_analyzer: MultiTimeframeAnalyzer) -> None:
        """Candle counts accumulate per timeframe."""
        _feed_steady_candles(small_analyzer, Decimal("50000"), 3, 60)
        _feed_steady_candles(small_analyzer, Decimal("50000"), 7, 15)
        _feed_steady_candles(small_analyzer, Decimal("50000"), 12, 5)
        counts = small_analyzer.candle_counts
        assert counts["1h"] == 3
        assert counts["15m"] == 7
        assert counts["5m"] == 12
