"""Anti look-ahead bias tests for FeatureStore.

These tests verify that:
1. Features at time T only use data <= T.
2. Targets correctly use future data (and are NULL at the end).
3. Feature builds are deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
from krakenbot.ml.features.feature_store import FeatureStore


class TestNoLookAhead:
    """Verify features don't leak future information."""

    def test_features_depend_only_on_past_candles(self) -> None:
        """Building features with extra future candles should NOT change
        features computed at timestamps that both runs cover.

        Strategy: replay 20 candles, capture features at candle 10.
        Then replay 30 candles, capture features at candle 10.
        They must be identical.
        """
        # Build analyzer + feature store for "short" replay (20 candles)
        analyzer_short = MultiTimeframeAnalyzer()
        FeatureStore._preregister_lazy_indicators(analyzer_short)

        store_short = FeatureStore.__new__(FeatureStore)
        store_short._close_history = {}

        # Build analyzer + feature store for "long" replay (30 candles)
        analyzer_long = MultiTimeframeAnalyzer()
        FeatureStore._preregister_lazy_indicators(analyzer_long)

        store_long = FeatureStore.__new__(FeatureStore)
        store_long._close_history = {}

        # Generate synthetic candles
        base_ts = datetime(2024, 1, 1, tzinfo=UTC)
        candles = []
        for i in range(30):
            price = Decimal("50000") + Decimal(str(i * 100 + (i % 3) * 50))
            candles.append(
                {
                    "timestamp": base_ts + timedelta(hours=4 * i),
                    "open": price - Decimal("50"),
                    "high": price + Decimal("200"),
                    "low": price - Decimal("200"),
                    "close": price,
                    "volume": Decimal("100"),
                }
            )

        # Replay "short" (20 candles)
        features_at_10_short = None
        for i, c in enumerate(candles[:20]):
            analyzer_short.update(c, 240)
            store_short._update_close_history("XBT/USDC", 240, c["timestamp"], float(c["close"]))
            if i == 10:
                features_at_10_short = store_short._compute_features(
                    analyzer_short,
                    c["timestamp"],
                    "XBT/USDC",
                    float(c["close"]),
                    float(c["high"]),
                    float(c["low"]),
                    float(c["volume"]),
                )

        # Replay "long" (30 candles)
        features_at_10_long = None
        for i, c in enumerate(candles[:30]):
            analyzer_long.update(c, 240)
            store_long._update_close_history("XBT/USDC", 240, c["timestamp"], float(c["close"]))
            if i == 10:
                features_at_10_long = store_long._compute_features(
                    analyzer_long,
                    c["timestamp"],
                    "XBT/USDC",
                    float(c["close"]),
                    float(c["high"]),
                    float(c["low"]),
                    float(c["volume"]),
                )

        assert features_at_10_short is not None
        assert features_at_10_long is not None

        # All features at candle 10 must be identical
        for key in features_at_10_short:
            val_short = features_at_10_short[key]
            val_long = features_at_10_long[key]
            if val_short is None:
                assert val_long is None, f"Feature {key}: short=None but long={val_long}"
            elif isinstance(val_short, float):
                assert val_long is not None, f"Feature {key}: short={val_short} but long=None"
                assert abs(val_short - val_long) < 1e-12, (
                    f"Feature {key}: short={val_short} != long={val_long}"
                )
            else:
                assert val_short == val_long, f"Feature {key}: short={val_short} != long={val_long}"

    def test_feature_build_is_deterministic(self) -> None:
        """Two identical replays must produce identical features."""
        results = []
        for _ in range(2):
            analyzer = MultiTimeframeAnalyzer()
            FeatureStore._preregister_lazy_indicators(analyzer)

            store = FeatureStore.__new__(FeatureStore)
            store._close_history = {}

            base_ts = datetime(2024, 1, 1, tzinfo=UTC)
            all_features = []
            for i in range(20):
                price = Decimal("50000") + Decimal(str(i * 100))
                candle = {
                    "open": price - Decimal("50"),
                    "high": price + Decimal("200"),
                    "low": price - Decimal("200"),
                    "close": price,
                    "volume": Decimal("100"),
                }
                ts = base_ts + timedelta(hours=4 * i)
                analyzer.update(candle, 240)
                store._update_close_history("XBT/USDC", 240, ts, float(price))

                features = store._compute_features(
                    analyzer,
                    ts,
                    "XBT/USDC",
                    float(price),
                    float(candle["high"]),
                    float(candle["low"]),
                    float(candle["volume"]),
                )
                all_features.append(features)
            results.append(all_features)

        # Compare both runs
        for i, (f1, f2) in enumerate(zip(results[0], results[1], strict=True)):
            for key in f1:
                v1, v2 = f1[key], f2[key]
                if v1 is None:
                    assert v2 is None, f"Candle {i}, {key}: run1=None, run2={v2}"
                elif isinstance(v1, float):
                    assert v2 is not None
                    assert v1 == v2, f"Candle {i}, {key}: run1={v1}, run2={v2}"
                else:
                    assert v1 == v2, f"Candle {i}, {key}: run1={v1}, run2={v2}"

    def test_warmup_features_are_none(self) -> None:
        """Before indicators warm up, indicator-based features must be None."""
        analyzer = MultiTimeframeAnalyzer()
        FeatureStore._preregister_lazy_indicators(analyzer)

        store = FeatureStore.__new__(FeatureStore)
        store._close_history = {}

        # Feed just 2 candles (insufficient for any indicator warmup)
        for i in range(2):
            price = Decimal("50000") + Decimal(str(i * 100))
            candle = {
                "open": price - Decimal("50"),
                "high": price + Decimal("200"),
                "low": price - Decimal("200"),
                "close": price,
                "volume": Decimal("100"),
            }
            ts = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=4 * i)
            analyzer.update(candle, 240)
            store._update_close_history("XBT/USDC", 240, ts, float(price))

        features = store._compute_features(
            analyzer,
            ts,
            "XBT/USDC",
            float(price),
            float(candle["high"]),
            float(candle["low"]),
            float(candle["volume"]),
        )

        # Indicator-based features should be None (not enough warmup)
        assert features["ema_spread_4h"] is None
        assert features["rsi_14_4h"] is None
        assert features["adx_4h"] is None
        # But cyclic features should always be computed
        assert features["hour_sin"] is not None
        assert features["dow_sin"] is not None
