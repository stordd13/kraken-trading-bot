"""Basic smoke tests for the 7 new strategies (Gemini + Grok).

Tests only get_name() and get_config() -- NOT trading logic
(that's the backtester's job).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.strategies.gemini_retour_moyenne import GeminiRetourMoyenne
from krakenbot.strategies.gemini_scalping_volatilite import GeminiScalpingVolatilite
from krakenbot.strategies.gemini_suivi_tendance_momentum import (
    GeminiSuiviTendanceMomentum,
)
from krakenbot.strategies.grok_adaptive_dca_weekly import GrokAdaptiveDCAWeekly
from krakenbot.strategies.grok_ema_adx_atr import GrokEMA27_125_ADX_ATR
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4
from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_deps(mock_settings: MagicMock) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Return (settings, event_bus, db_manager) mocks for strategy construction."""
    event_bus = MagicMock()
    event_bus.subscribe = MagicMock()
    event_bus.unsubscribe = MagicMock()
    db_manager = MagicMock()
    db_manager.session = AsyncMock()
    return mock_settings, event_bus, db_manager


# (class, expected_name)
STRATEGY_CLASSES = [
    (GeminiScalpingVolatilite, "gemini_scalping_volatilite"),
    (GeminiRetourMoyenne, "gemini_retour_moyenne"),
    (GeminiSuiviTendanceMomentum, "gemini_suivi_tendance_momentum"),
    (GrokGridATRAdaptiveV4, "grok_grid_atr_adaptive_v4"),
    (GrokSuperTrend4hRegime, "grok_supertrend_4h"),
    (GrokEMA27_125_ADX_ATR, "grok_ema_adx_atr"),
    (GrokAdaptiveDCAWeekly, "grok_adaptive_dca_weekly"),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStrategiesBasic:
    """Smoke tests for all 7 new strategies."""

    @pytest.mark.parametrize(
        "cls,expected_name",
        STRATEGY_CLASSES,
        ids=[name for _, name in STRATEGY_CLASSES],
    )
    def test_get_name_returns_expected(
        self,
        cls: type,
        expected_name: str,
        mock_deps: tuple,
    ) -> None:
        """get_name() returns the expected non-empty string."""
        settings, event_bus, db_manager = mock_deps
        strategy = cls(settings, event_bus, db_manager)
        name = strategy.get_name()
        assert isinstance(name, str)
        assert len(name) > 0
        assert name == expected_name

    @pytest.mark.parametrize(
        "cls,expected_name",
        STRATEGY_CLASSES,
        ids=[name for _, name in STRATEGY_CLASSES],
    )
    def test_get_config_returns_dict(
        self,
        cls: type,
        expected_name: str,
        mock_deps: tuple,
    ) -> None:
        """get_config() returns a non-empty dict."""
        settings, event_bus, db_manager = mock_deps
        strategy = cls(settings, event_bus, db_manager)
        config = strategy.get_config()
        assert isinstance(config, dict)
        assert len(config) > 0

    @pytest.mark.parametrize(
        "cls,expected_name",
        STRATEGY_CLASSES,
        ids=[name for _, name in STRATEGY_CLASSES],
    )
    def test_bot_id_defaults_to_name(
        self,
        cls: type,
        expected_name: str,
        mock_deps: tuple,
    ) -> None:
        """bot_id property falls back to get_name() when not explicitly set."""
        settings, event_bus, db_manager = mock_deps
        strategy = cls(settings, event_bus, db_manager)
        assert strategy.bot_id == expected_name

    @pytest.mark.parametrize(
        "cls,expected_name",
        STRATEGY_CLASSES,
        ids=[name for _, name in STRATEGY_CLASSES],
    )
    def test_custom_bot_id(
        self,
        cls: type,
        expected_name: str,
        mock_deps: tuple,
    ) -> None:
        """Custom bot_id overrides default."""
        settings, event_bus, db_manager = mock_deps
        strategy = cls(settings, event_bus, db_manager, bot_id="custom_bot")
        assert strategy.bot_id == "custom_bot"

    @pytest.mark.parametrize(
        "cls,expected_name",
        STRATEGY_CLASSES,
        ids=[name for _, name in STRATEGY_CLASSES],
    )
    def test_not_running_by_default(
        self,
        cls: type,
        expected_name: str,
        mock_deps: tuple,
    ) -> None:
        """Strategy is not running after construction."""
        settings, event_bus, db_manager = mock_deps
        strategy = cls(settings, event_bus, db_manager)
        assert strategy.is_running is False
