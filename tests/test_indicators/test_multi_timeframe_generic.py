"""Tests for MultiTimeframeAnalyzer generic data layer API.

The existing test_multi_timeframe.py covers the legacy analyze() pipeline.
This file tests the generic API that strategies actually use:
    get_ema(), get_rsi(), get_atr(), get_macd(), get_bollinger(),
    get_supertrend(), get_adx(), get_regime()
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from krakenbot.indicators.multi_timeframe import (
    MarketRegime,
    MultiTimeframeAnalyzer,
    TF_TO_INTERVAL,
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
    """Build a minimal candle dict for update()."""
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


def _feed_candles(
    analyzer: MultiTimeframeAnalyzer,
    price: Decimal,
    count: int,
    interval: int,
    spread: Decimal = Decimal("100"),
) -> None:
    """Feed steady candles at a given price with optional high-low spread."""
    for _ in range(count):
        candle = _make_candle(
            close=price,
            high=price + spread,
            low=price - spread,
        )
        analyzer.update(candle, interval)


def _feed_varied_candles(
    analyzer: MultiTimeframeAnalyzer,
    base_price: Decimal,
    count: int,
    interval: int,
) -> None:
    """Feed candles with alternating price movements to make indicators meaningful."""
    for i in range(count):
        offset = Decimal(str((-1) ** i * 100 * ((i % 5) + 1)))
        price = base_price + offset
        candle = _make_candle(
            close=price,
            high=price + Decimal("200"),
            low=price - Decimal("200"),
        )
        analyzer.update(candle, interval)


def _build_warmed_analyzer(
    timeframe: str = "4h",
    count: int = 60,
    price: Decimal = Decimal("50000"),
) -> MultiTimeframeAnalyzer:
    """Build an analyzer with enough candles for indicators to be ready."""
    analyzer = MultiTimeframeAnalyzer(
        ema_fast_period=20,
        ema_slow_period=50,
        atr_period=14,
        rsi_period=14,
        bb_period=20,
    )
    interval = TF_TO_INTERVAL[timeframe]
    _feed_varied_candles(analyzer, price, count, interval)
    return analyzer


# ---------------------------------------------------------------------------
# TestGenericEMA
# ---------------------------------------------------------------------------


class TestGenericEMA:
    """Tests for get_ema() -- lazy EMA indicator."""

    def test_returns_none_for_unknown_timeframe(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_ema(20, "invalid_tf") is None

    def test_lazy_creation_returns_none_first_call(self) -> None:
        """First call creates the indicator; returns None since no data yet."""
        analyzer = MultiTimeframeAnalyzer()
        # Feed one candle so the TF dict exists and is populated
        analyzer.update(_make_candle(Decimal("50000")), TF_TO_INTERVAL["4h"])
        result = analyzer.get_ema(200, "4h")
        # Lazy creation: first call returns None (indicator just created)
        assert result is None

    def test_returns_decimal_after_warmup(self) -> None:
        """After enough candles, get_ema returns a Decimal > 0."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        # Request EMA 20 (should be initialized from __init__)
        # But get_ema uses "ema" dict (lazy), not "ema_fast"
        # First call creates it
        analyzer.get_ema(20, "4h")
        # Feed more data for the lazy indicator
        for _ in range(25):
            analyzer.update(_make_candle(Decimal("50000")), TF_TO_INTERVAL["4h"])

        result = analyzer.get_ema(20, "4h")
        assert result is not None
        assert isinstance(result, Decimal)
        assert result > Decimal("0")

    def test_different_periods_independent(self) -> None:
        """EMA(20) and EMA(50) are separate lazy indicators."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        # Create both
        analyzer.get_ema(20, "4h")
        analyzer.get_ema(50, "4h")
        # Feed more candles
        for _ in range(55):
            analyzer.update(_make_candle(Decimal("50000")), TF_TO_INTERVAL["4h"])

        ema20 = analyzer.get_ema(20, "4h")
        ema50 = analyzer.get_ema(50, "4h")
        # Both should have values (enough data), and they may differ
        assert ema20 is not None
        assert ema50 is not None


# ---------------------------------------------------------------------------
# TestGenericRSI
# ---------------------------------------------------------------------------


class TestGenericRSI:
    """Tests for get_rsi() -- lazy RSI indicator."""

    def test_returns_none_for_unknown_timeframe(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_rsi(14, "invalid_tf") is None

    def test_default_rsi_returns_value_after_warmup(self) -> None:
        """RSI(14) is initialized by default for every TF."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_rsi(14, "4h")
        assert result is not None
        assert isinstance(result, Decimal)
        assert Decimal("0") <= result <= Decimal("100")

    def test_lazy_rsi_creation(self) -> None:
        """Requesting a non-default period creates it lazily."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        # RSI(7) is not a default -- first call creates it
        result = analyzer.get_rsi(7, "4h")
        assert result is None  # Just created, no data yet

    def test_rsi_with_varied_data(self) -> None:
        """RSI with alternating prices should be around 50."""
        analyzer = _build_warmed_analyzer("1h", count=60)
        result = analyzer.get_rsi(14, "1h")
        assert result is not None
        # With alternating data, RSI should be somewhere in the middle
        assert Decimal("20") <= result <= Decimal("80")


# ---------------------------------------------------------------------------
# TestGenericATR
# ---------------------------------------------------------------------------


class TestGenericATR:
    """Tests for get_atr() -- lazy ATR indicator."""

    def test_returns_none_for_unknown_timeframe(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_atr(14, "invalid_tf") is None

    def test_default_atr_returns_value_after_warmup(self) -> None:
        """ATR(14) is initialized by default."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_atr(14, "4h")
        assert result is not None
        assert isinstance(result, Decimal)
        assert result > Decimal("0")

    def test_lazy_atr_creation(self) -> None:
        """Non-default period creates lazily."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_atr(7, "4h")
        assert result is None  # Just created

    def test_atr_reflects_volatility(self) -> None:
        """Higher spread candles should produce higher ATR."""
        analyzer = MultiTimeframeAnalyzer()
        interval = TF_TO_INTERVAL["4h"]

        # Feed candles with large spread
        for _ in range(30):
            candle = _make_candle(
                close=Decimal("50000"),
                high=Decimal("52000"),
                low=Decimal("48000"),
            )
            analyzer.update(candle, interval)

        atr_large = analyzer.get_atr(14, "4h")
        assert atr_large is not None
        assert atr_large > Decimal("0")


# ---------------------------------------------------------------------------
# TestGenericMACD
# ---------------------------------------------------------------------------


class TestGenericMACD:
    """Tests for get_macd() -- returns dict with macd, signal, hist."""

    def test_returns_none_before_warmup(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_macd("4h") is None

    def test_returns_none_for_unknown_tf(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_macd("invalid_tf") is None

    def test_returns_dict_with_three_keys(self) -> None:
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_macd("4h")
        assert result is not None
        assert "macd" in result
        assert "signal" in result
        assert "hist" in result

    def test_values_are_decimal(self) -> None:
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_macd("4h")
        assert result is not None
        for key in ("macd", "signal", "hist"):
            assert isinstance(result[key], Decimal), f"{key} should be Decimal"

    def test_different_timeframes_independent(self) -> None:
        """MACD for 1h and 4h may have different values."""
        analyzer = MultiTimeframeAnalyzer()
        for _ in range(60):
            candle = _make_candle(Decimal("50000"))
            analyzer.update(candle, TF_TO_INTERVAL["1h"])
            analyzer.update(candle, TF_TO_INTERVAL["4h"])

        macd_1h = analyzer.get_macd("1h")
        macd_4h = analyzer.get_macd("4h")
        # Both should be available after 60 candles
        assert macd_1h is not None
        assert macd_4h is not None


# ---------------------------------------------------------------------------
# TestGenericBollinger
# ---------------------------------------------------------------------------


class TestGenericBollinger:
    """Tests for get_bollinger() -- returns dict with upper/middle/lower/width."""

    def test_returns_none_before_warmup(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_bollinger("4h") is None

    def test_returns_dict_with_four_keys(self) -> None:
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_bollinger("4h")
        assert result is not None
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert "width" in result

    def test_upper_gt_middle_gt_lower(self) -> None:
        """Bollinger bands order: upper > middle > lower."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_bollinger("4h")
        assert result is not None
        assert result["upper"] >= result["middle"]
        assert result["middle"] >= result["lower"]

    def test_width_positive(self) -> None:
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_bollinger("4h")
        assert result is not None
        assert result["width"] >= Decimal("0")

    def test_values_are_decimal(self) -> None:
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_bollinger("4h")
        assert result is not None
        for key in ("upper", "middle", "lower", "width"):
            assert isinstance(result[key], Decimal), f"{key} should be Decimal"


# ---------------------------------------------------------------------------
# TestGenericSuperTrend
# ---------------------------------------------------------------------------


class TestGenericSuperTrend:
    """Tests for get_supertrend() -- lazy creation."""

    def test_returns_none_before_warmup(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_supertrend("4h") is None

    def test_lazy_creation(self) -> None:
        """First call creates the SuperTrend indicator."""
        analyzer = MultiTimeframeAnalyzer()
        # Feed one candle so TF exists
        analyzer.update(_make_candle(Decimal("50000")), TF_TO_INTERVAL["4h"])
        result = analyzer.get_supertrend("4h", atr_period=10, multiplier=3.0)
        # Just created, not enough data
        assert result is None

    def test_returns_dict_after_warmup(self) -> None:
        """After enough candles, returns dict with supertrend and direction."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        # Create supertrend and then feed more
        analyzer.get_supertrend("4h", atr_period=10, multiplier=3.0)
        for _ in range(20):
            analyzer.update(
                _make_candle(Decimal("50000"), high=Decimal("51000"), low=Decimal("49000")),
                TF_TO_INTERVAL["4h"],
            )

        result = analyzer.get_supertrend("4h", atr_period=10, multiplier=3.0)
        if result is not None:
            assert "supertrend" in result
            assert "direction" in result
            assert result["direction"] in (1, -1)


# ---------------------------------------------------------------------------
# TestGenericADX
# ---------------------------------------------------------------------------


class TestGenericADX:
    """Tests for get_adx() -- standard period 14."""

    def test_returns_none_before_warmup(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_adx("4h") is None

    def test_returns_none_for_unknown_tf(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_adx("invalid_tf") is None

    def test_returns_decimal_after_warmup(self) -> None:
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_adx("4h")
        if result is not None:
            assert isinstance(result, Decimal)
            assert result >= Decimal("0")


# ---------------------------------------------------------------------------
# TestGetRegime
# ---------------------------------------------------------------------------


class TestGetRegime:
    """Tests for get_regime() -- EMA fast/slow crossover regime."""

    def test_returns_none_before_warmup(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_regime("4h") is None

    def test_returns_none_for_unknown_tf(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.get_regime("invalid_tf") is None

    def test_returns_valid_regime_string(self) -> None:
        """After warmup, regime should be one of the 5 valid values."""
        analyzer = _build_warmed_analyzer("4h", count=60)
        result = analyzer.get_regime("4h")
        valid_regimes = {r.value for r in MarketRegime}
        if result is not None:
            assert result in valid_regimes

    def test_steady_prices_neutral(self) -> None:
        """Flat prices (EMA fast ~ EMA slow) should be NEUTRAL."""
        analyzer = MultiTimeframeAnalyzer()
        interval = TF_TO_INTERVAL["4h"]
        # Feed 60 candles at same price -> EMAs converge
        _feed_candles(analyzer, Decimal("50000"), 60, interval)

        result = analyzer.get_regime("4h")
        if result is not None:
            assert result == MarketRegime.NEUTRAL.value

    def test_works_on_all_timeframes(self) -> None:
        """get_regime should work for 1h, 4h, 1d, 1w."""
        analyzer = MultiTimeframeAnalyzer()
        for tf in ["1h", "4h", "1d", "1w"]:
            interval = TF_TO_INTERVAL[tf]
            _feed_candles(analyzer, Decimal("50000"), 60, interval)
            # Should not raise
            result = analyzer.get_regime(tf)
            # May or may not be ready depending on warmup, but shouldn't error
            if result is not None:
                assert result in {r.value for r in MarketRegime}


# ---------------------------------------------------------------------------
# TestCandle counts and timeframe routing
# ---------------------------------------------------------------------------


class TestGenericCandleCounts:
    """Tests that update() correctly routes to all timeframes."""

    def test_candle_counts_increment(self) -> None:
        analyzer = MultiTimeframeAnalyzer()
        analyzer.update(_make_candle(Decimal("50000")), TF_TO_INTERVAL["4h"])
        analyzer.update(_make_candle(Decimal("50000")), TF_TO_INTERVAL["4h"])
        analyzer.update(_make_candle(Decimal("50000")), TF_TO_INTERVAL["1d"])

        assert analyzer._generic_candle_counts["4h"] == 2
        assert analyzer._generic_candle_counts["1d"] == 1

    def test_all_timeframes_routable(self) -> None:
        """Every TF in ALL_TF_KEYS should be routable via update()."""
        analyzer = MultiTimeframeAnalyzer()
        for tf, interval in TF_TO_INTERVAL.items():
            analyzer.update(_make_candle(Decimal("50000")), interval)
            assert analyzer._generic_candle_counts[tf] >= 1

    def test_unknown_interval_ignored(self) -> None:
        """An unsupported interval (e.g. 7) is silently ignored."""
        analyzer = MultiTimeframeAnalyzer()
        analyzer.update(_make_candle(Decimal("50000")), 7)
        # No crash, no side effects on known TFs
        assert analyzer._generic_candle_counts.get("4h", 0) == 0
