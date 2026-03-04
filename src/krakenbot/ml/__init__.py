"""Machine Learning module for KrakenBot.

Provides ML-based signal enhancement for rule-based trading strategies.
The ML pipeline acts as an overlay (enhancer) on existing strategies,
NOT as a standalone signal generator.

Submodules:
    config: ML configuration (MLSettings, MLFeatureSettings)
    features: Feature store and external data fetching
    models: LightGBM model skeletons (vol forecaster, regime predictor, signal filter)
    inference: MLSignalEnhancer for real-time signal filtering
    monitoring: Drift detection for model health
"""

from krakenbot.ml.config import MLFeatureSettings, MLSettings

__all__ = [
    "MLFeatureSettings",
    "MLSettings",
]
