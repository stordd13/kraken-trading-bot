"""Model drift detection for ML pipeline.

Monitors feature distributions and model performance over time.
Alerts when retraining may be needed.

Phase 2+ implementation — skeleton only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DriftDetector:
    """Detect data drift and model performance degradation.

    Compares recent feature distributions against training distributions.
    Tracks prediction accuracy over rolling windows.

    Drift types monitored:
        - Feature drift: KL divergence of feature distributions
        - Prediction drift: shift in model confidence distribution
        - Performance drift: declining accuracy on realized outcomes
    """

    def __init__(self, reference_window_days: int = 90) -> None:
        """Initialize the drift detector.

        Args:
            reference_window_days: Days of data to use as reference distribution.
        """
        self._reference_window_days = reference_window_days
        self._reference_stats: dict[str, Any] = {}
        self._last_check: datetime | None = None

    def set_reference(self, features: Any) -> None:
        """Compute reference statistics from training data.

        Args:
            features: Training feature DataFrame to use as baseline.
        """
        raise NotImplementedError("Phase 2+: drift detection not yet implemented")

    def check_feature_drift(self, recent_features: Any) -> dict[str, float]:
        """Check for feature distribution drift.

        Args:
            recent_features: Recent feature DataFrame to compare against reference.

        Returns:
            Dict of feature_name → drift_score (KL divergence).
            Values > 0.1 suggest meaningful drift.
        """
        raise NotImplementedError("Phase 2+: drift detection not yet implemented")

    def check_prediction_drift(self, recent_predictions: Any) -> float:
        """Check for prediction confidence distribution drift.

        Returns:
            Overall drift score (0-1). Values > 0.2 suggest retraining.
        """
        raise NotImplementedError("Phase 2+: drift detection not yet implemented")

    def should_retrain(self) -> bool:
        """Whether drift levels suggest model retraining is needed."""
        raise NotImplementedError("Phase 2+: drift detection not yet implemented")
