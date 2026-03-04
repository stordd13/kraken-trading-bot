"""ML configuration models.

Loaded from the ``ml:`` section of ``strategies.yaml``.
When absent or ``enabled: false``, the entire ML pipeline is disabled
and the bot operates in pure rule-based mode.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MLFeatureSettings(BaseModel):
    """Feature engineering configuration."""

    lookback_candles: int = Field(
        default=240,
        description="Number of candles to consider for rolling features",
    )
    external_data: bool = Field(
        default=True,
        description="Whether to fetch and use external data (Fear & Greed, etc.)",
    )
    fear_greed_api: str = Field(
        default="https://api.alternative.me/fng/",
        description="Fear & Greed Index API endpoint",
    )


class MLSettings(BaseModel):
    """Top-level ML configuration.

    Parsed from the ``ml:`` section of ``strategies.yaml``.
    """

    enabled: bool = Field(
        default=False,
        description="Enable ML inference pipeline",
    )
    mode: str = Field(
        default="enhancer",
        description="ML mode: 'enhancer' (overlay on rules)",
    )
    confidence_threshold: float = Field(
        default=0.62,
        ge=0.5,
        le=0.95,
        description="Minimum model confidence to accept/modify a signal",
    )
    retrain_every: str = Field(
        default="30d",
        description="Retrain interval (e.g., '30d', '7d')",
    )
    fallback_on_error: bool = Field(
        default=True,
        description="If True, ML errors fall back to pure rule-based signals",
    )
    models_dir: str = Field(
        default="models/",
        description="Directory for saved model files",
    )
    features: MLFeatureSettings = Field(
        default_factory=MLFeatureSettings,
        description="Feature engineering settings",
    )
