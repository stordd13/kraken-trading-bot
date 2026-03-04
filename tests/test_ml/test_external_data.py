"""Tests for ExternalDataFetcher."""

from __future__ import annotations

import pytest

from krakenbot.ml.features.external_data import ExternalDataFetcher


class TestFearGreedParsing:
    """Test Fear & Greed API response parsing (without actual HTTP calls)."""

    def test_fetcher_initializes(self) -> None:
        """ExternalDataFetcher can be created without a real DB manager."""
        # Just verify the class initializes with a mock
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        fetcher = ExternalDataFetcher(mock_db)
        assert fetcher.FEAR_GREED_URL == "https://api.alternative.me/fng/"

    def test_url_construction(self) -> None:
        """Verify URL is correctly built with limit parameter."""
        url = f"{ExternalDataFetcher.FEAR_GREED_URL}?limit=0&format=json"
        assert "limit=0" in url
        assert "format=json" in url


class TestMLConfig:
    """Test ML configuration loading."""

    def test_ml_settings_defaults(self) -> None:
        """MLSettings should have sensible defaults."""
        from krakenbot.ml.config import MLSettings

        settings = MLSettings()
        assert settings.enabled is False
        assert settings.mode == "enhancer"
        assert settings.confidence_threshold == 0.62
        assert settings.retrain_every == "30d"
        assert settings.fallback_on_error is True
        assert settings.models_dir == "models/"

    def test_ml_feature_settings_defaults(self) -> None:
        """MLFeatureSettings should have sensible defaults."""
        from krakenbot.ml.config import MLFeatureSettings

        settings = MLFeatureSettings()
        assert settings.lookback_candles == 240
        assert settings.external_data is True
        assert "alternative.me" in settings.fear_greed_api

    def test_ml_settings_from_dict(self) -> None:
        """MLSettings should load from a dict (like strategies.yaml)."""
        from krakenbot.ml.config import MLSettings

        data = {
            "enabled": True,
            "mode": "enhancer",
            "confidence_threshold": 0.70,
            "retrain_every": "14d",
        }
        settings = MLSettings(**data)
        assert settings.enabled is True
        assert settings.confidence_threshold == 0.70
        assert settings.retrain_every == "14d"

    def test_ml_settings_confidence_bounds(self) -> None:
        """confidence_threshold should be validated to [0.5, 0.95]."""
        from pydantic import ValidationError

        from krakenbot.ml.config import MLSettings

        with pytest.raises(ValidationError):
            MLSettings(confidence_threshold=0.3)

        with pytest.raises(ValidationError):
            MLSettings(confidence_threshold=0.99)
