"""Tests for runtime-aligned strategies.yaml validation."""

from __future__ import annotations

import logging

import pytest

from krakenbot.config.settings import (
    MultiStrategySettings,
    StrategyInstanceConfig,
)


class TestStrategiesYamlRuntimeValidation:
    """Tests for strategies.yaml validation against runtime behavior."""

    def test_validate_all_fails_on_active_unsupported_router_inner_strategy(
        self,
        mock_settings,
    ) -> None:
        """Active router inner strategies unsupported by runtime must fail fast."""
        settings = mock_settings.model_copy(deep=True)
        settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    params={
                        "strategies": {
                            "grok_donchian_breakout_4h": {
                                "active": True,
                                "bot_id": "donchian_breakout_4h",
                                "params": {},
                            }
                        }
                    },
                )
            ],
        )

        with pytest.raises(ValueError, match="grok_donchian_breakout_4h"):
            settings.validate_all()

    def test_validate_all_warns_on_router_inner_fields_ignored_by_runtime(
        self,
        mock_settings,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Fields ignored by MultiStrategyRouter should be surfaced explicitly."""
        settings = mock_settings.model_copy(deep=True)
        settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    params={
                        "strategies": {
                            "grok_supertrend_4h": {
                                "active": True,
                                "bot_id": "supertrend_4h",
                                "params": {},
                                "pairs": ["XBT/USDC", "ETH/USDC"],
                            }
                        }
                    },
                )
            ],
        )

        with caplog.at_level(logging.WARNING):
            settings.validate_all()

        assert "grok_supertrend_4h" in caplog.text
        assert "ignored runtime fields" in caplog.text
        assert "pairs" in caplog.text
