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
        assert settings.bybit.ws_url == "wss://stream.bybit.eu/v5/public/spot"
        assert settings.bybit.ws_ping_interval_seconds == 20
        assert settings.bybit.ws_pong_timeout_seconds == 10
        assert settings.bybit.ws_watchdog_warn_seconds == 600
        assert settings.bybit.ws_watchdog_zombie_seconds == 1800
        assert settings.bybit.ws_watchdog_resubscribe_alert_count == 3

    def test_bybit_watchdog_zombie_must_exceed_warn(self) -> None:
        with pytest.raises(ValidationError, match="ZOMBIE_SECONDS must be greater"):
            BybitSettings(
                ws_watchdog_warn_seconds=900, ws_watchdog_zombie_seconds=900, _env_file=None
            )
        bybit = BybitSettings(
            ws_watchdog_warn_seconds=300, ws_watchdog_zombie_seconds=600, _env_file=None
        )
        assert (bybit.ws_watchdog_warn_seconds, bybit.ws_watchdog_zombie_seconds) == (300, 600)

    def test_bybit_pong_timeout_must_be_below_ping_interval(self) -> None:
        with pytest.raises(ValidationError, match="PONG_TIMEOUT_SECONDS must be smaller"):
            BybitSettings(ws_ping_interval_seconds=10, ws_pong_timeout_seconds=10, _env_file=None)

    def test_scheduler_pairs_default_is_exchange_agnostic(self) -> None:
        settings = Settings(environment="testing", exchange_name="bybit", _env_file=None)
        assert settings.scheduler.pairs == ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
        assert "XBT" not in "".join(settings.scheduler.pairs)

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
        # read-only key present, trade key missing -> live must fail on the TRADE key
        settings.bybit = BybitSettings(
            api_key=SecretStr("ro"), api_secret=SecretStr("ro"), _env_file=None
        )
        with pytest.raises(ValueError, match="BYBIT_TRADE_API_KEY"):
            settings.validate_all()

    def test_bybit_credentials_by_role(self) -> None:
        bybit = BybitSettings(
            api_key=SecretStr("ro-k"),
            api_secret=SecretStr("ro-s"),
            trade_api_key=SecretStr("tr-k"),
            trade_api_secret=SecretStr("tr-s"),
            _env_file=None,
        )
        assert bybit.credentials("readonly") == ("ro-k", "ro-s")
        assert bybit.credentials("trade") == ("tr-k", "tr-s")
        assert BybitSettings(_env_file=None).credentials("readonly") == ("", "")
        with pytest.raises(ValueError, match="BYBIT_TRADE_API_KEY"):
            BybitSettings(api_key=SecretStr("ro-k"), _env_file=None).credentials("trade")


class TestBybitFees:
    def test_bybit_defaults(self) -> None:
        fees = ExchangeFees.bybit_defaults()
        assert fees.maker == Decimal("0.0010")
        assert fees.taker == Decimal("0.0025")
        assert fees.spread == Decimal("0.0002")
        assert fees.slippage == Decimal("0.0002")
