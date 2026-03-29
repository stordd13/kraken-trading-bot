"""Unit tests for FeatureStore."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import math

from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
from krakenbot.ml.features.feature_store import FeatureStore


class TestGetFeaturesDict:
    """Test MultiTimeframeAnalyzer.get_features_dict() method."""

    def test_returns_none_when_not_warmed_up(self) -> None:
        """All features should be None before warmup completes."""
        analyzer = MultiTimeframeAnalyzer()
        features = analyzer.get_features_dict("4h")

        # All should be None except regime (which depends on EMAs)
        assert features["rsi_14"] is None
        assert features["atr_ratio"] is None
        assert features["adx"] is None
        assert features["macd_hist_norm"] is None
        assert features["bb_width"] is None

    def test_returns_values_after_warmup(self) -> None:
        """After sufficient candles, features should have non-None values."""
        analyzer = MultiTimeframeAnalyzer()
        FeatureStore._preregister_lazy_indicators(analyzer)

        # Feed 60 candles to warm up (more than default warmup periods)
        base_price = Decimal("50000")
        for i in range(60):
            close = base_price + Decimal(str(i * 100))
            candle = {
                "open": close - Decimal("50"),
                "high": close + Decimal("200"),
                "low": close - Decimal("200"),
                "close": close,
                "volume": Decimal("100"),
            }
            analyzer.update(candle, 240)  # 4h candles

        features = analyzer.get_features_dict("4h")

        # Core features should now have values
        assert features["rsi_14"] is not None
        assert features["adx"] is not None
        assert isinstance(features["rsi_14"], float)
        assert 0 <= features["rsi_14"] <= 100

    def test_feature_keys_are_stable(self) -> None:
        """Feature dict should always contain the expected keys."""
        analyzer = MultiTimeframeAnalyzer()
        FeatureStore._preregister_lazy_indicators(analyzer)
        features = analyzer.get_features_dict("4h")

        expected_keys = {
            "ema_spread",
            "rsi_14",
            "atr_ratio",
            "adx",
            "macd_hist_norm",
            "bb_width",
            "bb_pctb",
            "supertrend_dist",
            "supertrend_dir",
            "regime",
            "volume_ratio",
            "vwap_deviation",
        }
        assert set(features.keys()) == expected_keys


class TestCyclicFeatures:
    """Test cyclic feature computation."""

    def test_hour_sin_cos_at_midnight(self) -> None:
        """At hour 0, sin should be 0 and cos should be 1."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        hour_sin = math.sin(2 * math.pi * ts.hour / 24)
        hour_cos = math.cos(2 * math.pi * ts.hour / 24)
        assert abs(hour_sin) < 1e-10
        assert abs(hour_cos - 1.0) < 1e-10

    def test_hour_sin_cos_at_noon(self) -> None:
        """At hour 12, sin should be ~0 and cos should be -1."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        hour_sin = math.sin(2 * math.pi * ts.hour / 24)
        hour_cos = math.cos(2 * math.pi * ts.hour / 24)
        assert abs(hour_sin) < 1e-10
        assert abs(hour_cos - (-1.0)) < 1e-10

    def test_hour_sin_cos_at_6am(self) -> None:
        """At hour 6, sin should be 1 and cos should be ~0."""
        ts = datetime(2024, 1, 1, 6, 0, 0, tzinfo=UTC)
        hour_sin = math.sin(2 * math.pi * ts.hour / 24)
        hour_cos = math.cos(2 * math.pi * ts.hour / 24)
        assert abs(hour_sin - 1.0) < 1e-10
        assert abs(hour_cos) < 1e-10


class TestRealizedVolatility:
    """Test realized volatility computation."""

    def test_returns_none_with_insufficient_data(self) -> None:
        """Should return None when not enough close history."""
        store = FeatureStore.__new__(FeatureStore)
        store._close_history = {}
        assert store._compute_realized_vol("XBT/USDC", 240, 6) is None

    def test_returns_zero_for_constant_prices(self) -> None:
        """Constant prices should give zero (or near-zero) volatility."""
        store = FeatureStore.__new__(FeatureStore)
        store._close_history = {}
        pair = "XBT/USDC"
        key = (pair, 240)
        from collections import deque

        store._close_history[key] = deque(maxlen=200)
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        for _i in range(10):
            store._close_history[key].append((ts, 50000.0))

        vol = store._compute_realized_vol(pair, 240, 6)
        assert vol is not None
        assert vol == 0.0

    def test_returns_positive_for_varying_prices(self) -> None:
        """Varying prices should give positive volatility."""
        store = FeatureStore.__new__(FeatureStore)
        store._close_history = {}
        pair = "XBT/USDC"
        key = (pair, 240)
        from collections import deque

        store._close_history[key] = deque(maxlen=200)
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        prices = [50000, 51000, 49500, 52000, 48000, 53000, 50500, 51500]
        for p in prices:
            store._close_history[key].append((ts, float(p)))

        vol = store._compute_realized_vol(pair, 240, 6)
        assert vol is not None
        assert vol > 0


class TestPreregisterLazyIndicators:
    """Test that lazy indicator pre-registration works."""

    def test_preregister_creates_indicators(self) -> None:
        """Pre-registering should create lazy indicators for all feature TFs."""
        analyzer = MultiTimeframeAnalyzer()
        FeatureStore._preregister_lazy_indicators(analyzer)

        # After pre-registration, these should exist (though not ready yet)
        for tf in ["1h", "4h", "1d"]:
            tf_ind = analyzer._indicators.get(tf, {})
            assert 20 in tf_ind.get("ema", {}), f"EMA(20) not registered for {tf}"
            assert 50 in tf_ind.get("ema", {}), f"EMA(50) not registered for {tf}"
            assert len(tf_ind.get("supertrend", {})) > 0, f"SuperTrend not registered for {tf}"
            assert len(tf_ind.get("vwap", {})) > 0, f"VWAP not registered for {tf}"
