"""ML Signal Enhancer — the main inference pipeline.

Orchestrates all 3 LightGBM models to enhance trading signals:
    1. VolForecaster → adjusts ATR stops + grid spacing
    2. RegimePredictor → overrides regime if confidence high enough
    3. SignalFilter → accepts/rejects the signal

Integration point:
    generate_signal() → TradingSignal
        ↓
    MLSignalEnhancer.evaluate(signal, features)
        → vol_forecast → adjusts ATR + spacing
        → regime → override if confidence > threshold
        → signal_quality → accept/reject
        ↓
    GeminiGlobalRiskManager (1% rule + crash protector)
        ↓
    ExecutionEngine

Phase 2 implementation — skeleton only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from krakenbot.ml.config import MLSettings
    from krakenbot.ml.features.feature_store import FeatureStore
    from krakenbot.ml.models.lightgbm.regime_predictor import RegimePredictor
    from krakenbot.ml.models.lightgbm.signal_filter import SignalFilter
    from krakenbot.ml.models.lightgbm.vol_forecaster import VolForecaster
    from krakenbot.strategies.base import TradingSignal

logger = structlog.get_logger(__name__)


class MLSignalEnhancer:
    """Orchestrates ML models to enhance trading signals.

    When ml.enabled=false or all models fail, signals pass through unmodified
    (fallback to pure rule-based behavior).
    """

    def __init__(
        self,
        settings: MLSettings,
        feature_store: FeatureStore,
        vol_forecaster: VolForecaster | None = None,
        regime_predictor: RegimePredictor | None = None,
        signal_filter: SignalFilter | None = None,
    ) -> None:
        """Initialize the enhancer with ML settings and models.

        Args:
            settings: ML configuration from strategies.yaml.
            feature_store: Feature store instance for retrieving features.
            vol_forecaster: Volatility forecaster model (optional).
            regime_predictor: Regime predictor model (optional).
            signal_filter: Signal quality filter model (optional).
        """
        self._settings = settings
        self._feature_store = feature_store
        self._vol_forecaster = vol_forecaster
        self._regime_predictor = regime_predictor
        self._signal_filter = signal_filter

    async def evaluate(
        self,
        signal: TradingSignal,
    ) -> tuple[TradingSignal, dict[str, Any]]:
        """Evaluate and potentially modify a trading signal.

        Args:
            signal: The original trading signal from a strategy.

        Returns:
            Tuple of (possibly modified signal, ml_metadata dict).
            If ML rejects the signal, signal_type is changed to HOLD.
            ml_metadata contains model predictions and confidence scores.
        """
        raise NotImplementedError("Phase 2: ML signal enhancer not yet implemented")

    @property
    def is_ready(self) -> bool:
        """Whether at least one ML model is loaded and ready."""
        models = [self._vol_forecaster, self._regime_predictor, self._signal_filter]
        return any(m is not None and m.is_ready for m in models)

    @property
    def enabled(self) -> bool:
        """Whether ML enhancement is enabled in settings."""
        return self._settings.enabled
