"""LightGBM market regime predictor.

Predicts the market regime 24h ahead (5 classes: strong_bear → strong_bull).
Replaces the rule-based get_regime() when confidence is high enough.

Phase 2 implementation — skeleton only.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RegimePredictor:
    """Predict market regime 24h ahead using LightGBM multiclass.

    Trained on historical features from ml_features table.
    Target: target_regime_24h (5 classes from MarketRegime enum).
    Includes Fear & Greed Index as a feature.

    Usage in enhancer pipeline:
        regime, confidence = regime_predictor.predict(features)
        → overrides get_regime() if confidence > threshold
    """

    REGIME_CLASSES: list[str] = [
        "strong_bear",
        "bear",
        "neutral",
        "bull",
        "strong_bull",
    ]

    def __init__(self, model_path: Path | None = None) -> None:
        """Initialize the regime predictor.

        Args:
            model_path: Path to saved LightGBM model file.
        """
        self._model: Any = None
        self._model_path = model_path
        self._feature_names: list[str] = []

    def load(self, path: Path | None = None) -> None:
        """Load a trained model from disk."""
        raise NotImplementedError("Phase 2: LightGBM regime predictor not yet implemented")

    def train(
        self,
        features: Any,
        targets: Any,
        *,
        val_features: Any | None = None,
        val_targets: Any | None = None,
    ) -> dict[str, float]:
        """Train the regime predictor (multiclass classification).

        Returns:
            Dict of training metrics (accuracy, f1_macro, log_loss).
        """
        raise NotImplementedError("Phase 2: LightGBM regime predictor not yet implemented")

    def predict(self, features: dict[str, float | None]) -> tuple[str, float] | None:
        """Predict market regime 24h ahead.

        Args:
            features: Feature dict from FeatureStore.get_features().

        Returns:
            Tuple of (regime_string, confidence) or None if model not loaded.
            Confidence is the probability of the predicted class (0-1).
        """
        raise NotImplementedError("Phase 2: LightGBM regime predictor not yet implemented")

    def predict_proba(self, features: dict[str, float | None]) -> dict[str, float] | None:
        """Get probability distribution over all regime classes.

        Returns:
            Dict mapping regime_class → probability, or None.
        """
        raise NotImplementedError("Phase 2: LightGBM regime predictor not yet implemented")

    def save(self, path: Path | None = None) -> None:
        """Save trained model to disk."""
        raise NotImplementedError("Phase 2: LightGBM regime predictor not yet implemented")

    @property
    def is_ready(self) -> bool:
        """Whether the model is loaded and ready for inference."""
        return self._model is not None

    @property
    def trained_at(self) -> datetime | None:
        """Timestamp when the model was last trained."""
        return None
