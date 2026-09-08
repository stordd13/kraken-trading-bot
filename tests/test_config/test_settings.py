"""Tests for runtime-aligned strategies.yaml validation."""

from __future__ import annotations

from decimal import Decimal
import logging

from pydantic import SecretStr, ValidationError
import pytest

from krakenbot.config.settings import (
    BybitSettings,
    ExchangeFees,
    MultiStrategySettings,
    Settings,
    StrategyInstanceConfig,
    TradingMode,
    TradingSettings,
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
                            "nonexistent_strategy_xyz": {
                                "active": True,
                                "bot_id": "fake_strategy",
                                "params": {},
                            }
                        }
                    },
                )
            ],
        )

        with pytest.raises(ValueError, match="nonexistent_strategy_xyz"):
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


class TestExchangeNameRequired:
    """exchange_name has no default since B1 (server incident 2026-09-07)."""

    def test_missing_exchange_name_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EXCHANGE_NAME", raising=False)
        with pytest.raises(ValidationError, match="exchange_name"):
            Settings(environment="testing", _env_file=None)

    def test_unknown_exchange_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exchange_name"):
            Settings(environment="testing", exchange_name="ftx", _env_file=None)

    def test_bybit_exchange_name_loads_bybit_settings(self) -> None:
        settings = Settings(environment="testing", exchange_name="bybit", _env_file=None)
        assert settings.exchange_name == "bybit"
        assert settings.bybit.hostname == "bybit.eu"
        assert settings.bybit.recv_window == 5000
        assert settings.bybit.account_type == "UNIFIED"

    def test_env_var_selects_exchange(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXCHANGE_NAME", "bybit")
        assert Settings(environment="testing", _env_file=None).exchange_name == "bybit"

    def test_live_mode_requires_keys_of_selected_exchange(self) -> None:
        settings = Settings(
            environment="testing",
            exchange_name="bybit",
            trading=TradingSettings.model_construct(mode=TradingMode.LIVE, confirm_live="yes"),
            _env_file=None,
        )
        settings.bybit = BybitSettings(api_key=SecretStr(""), api_secret=SecretStr(""))
        with pytest.raises(ValueError, match="BYBIT_API_KEY"):
            settings.validate_all()


class TestBybitFees:
    def test_bybit_defaults(self) -> None:
        fees = ExchangeFees.bybit_defaults()
        assert fees.maker == Decimal("0.0010")
        assert fees.taker == Decimal("0.0025")
        assert fees.spread == Decimal("0.0002")
        assert fees.slippage == Decimal("0.0002")
