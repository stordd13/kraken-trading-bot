"""Fee-model selection contract of BacktestEngine / GridBacktester (B4.2, no DB)."""

# ruff: noqa: E402
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from krakenbot.config.settings import FEE_MODEL_NAMES, ExchangeFees
from scripts.backtest import BacktestEngine, GridBacktester, PairCosts, resolve_fee_model


def _grid_settings() -> SimpleNamespace:
    return SimpleNamespace(
        multi_strategy=SimpleNamespace(
            enabled=True,
            strategies=[
                SimpleNamespace(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    params={
                        "strategies": {
                            "grok_grid_atr_adaptive_v4": {
                                "bot_id": "grid_atr_v4",
                                "params": {"order_size_usdc": 25},
                            }
                        }
                    },
                )
            ],
        ),
        trading=SimpleNamespace(pair="BTC/USDC", default_order_amount_eur=50),
        exchange_fees=ExchangeFees(maker=Decimal("0.5"), taker=Decimal("0.5")),
    )


def _fields(fees: ExchangeFees) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return fees.maker, fees.taker, fees.spread, fees.slippage


class TestResolveFeeModel:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("bybit", ExchangeFees.bybit_defaults()),
            ("binance", ExchangeFees.binance_defaults(use_bnb=True)),
            ("kraken", ExchangeFees.kraken_defaults()),
            ("BYBIT", ExchangeFees.bybit_defaults()),
        ],
    )
    def test_name_maps_to_factory(self, name: str, expected: ExchangeFees) -> None:
        fees, label = resolve_fee_model(name)
        assert _fields(fees) == _fields(expected)
        assert label == name.strip().lower()

    def test_names_constant(self) -> None:
        assert FEE_MODEL_NAMES == ("bybit", "binance", "kraken")

    def test_none_is_an_explicit_error(self) -> None:
        with pytest.raises(ValueError, match="fee_model is required") as exc:
            resolve_fee_model(None)
        for name in FEE_MODEL_NAMES:
            assert name in str(exc.value)

    def test_unknown_name_lists_choices(self) -> None:
        with pytest.raises(ValueError, match="Unknown fee model 'ftx'") as exc:
            resolve_fee_model("ftx")
        assert "bybit" in str(exc.value)

    def test_instance_passthrough_is_custom(self) -> None:
        custom = ExchangeFees(maker=Decimal("0.0003"), taker=Decimal("0.0007"))
        fees, label = resolve_fee_model(custom)
        assert fees is custom
        assert label == "custom"

    def test_other_types_are_type_errors(self) -> None:
        with pytest.raises(TypeError):
            resolve_fee_model(0.001)  # type: ignore[arg-type]


class TestEngineContract:
    def test_missing_fee_model_is_a_type_error(self) -> None:
        with pytest.raises(TypeError, match="fee_model"):
            BacktestEngine(MagicMock(), MagicMock())  # type: ignore[call-arg]
        with pytest.raises(TypeError, match="fee_model"):
            GridBacktester(_grid_settings(), MagicMock())  # type: ignore[call-arg]

    def test_none_fee_model_is_a_value_error(self) -> None:
        with pytest.raises(ValueError, match="fee_model is required"):
            BacktestEngine(MagicMock(), MagicMock(), fee_model=None)  # type: ignore[arg-type]

    @pytest.mark.parametrize("name", FEE_MODEL_NAMES)
    def test_engines_resolve_names(self, name: str) -> None:
        expected = ExchangeFees.from_name(name)
        signal = BacktestEngine(MagicMock(), MagicMock(), fee_model=name)
        grid = GridBacktester(_grid_settings(), MagicMock(), fee_model=name)
        assert _fields(signal.fees) == _fields(expected)
        assert _fields(grid.fees) == _fields(expected)
        assert signal.fee_model_name == grid.fee_model_name == name

    def test_fee_model_is_decoupled_from_exchange(self) -> None:
        """exchange= selects the OHLC data source only (B4.2 doctrine)."""
        signal = BacktestEngine(MagicMock(), MagicMock(), fee_model="bybit", exchange="binance")
        grid = GridBacktester(_grid_settings(), MagicMock(), fee_model="bybit", exchange="binance")
        assert signal.exchange == grid.exchange == "binance"
        assert signal.fees.taker == grid.fees.taker == Decimal("0.0025")
        assert signal.fees.maker == grid.fees.maker == Decimal("0.0010")

    def test_binance_reproduces_the_pre_b4_2_flat_model(self) -> None:
        """Iso-fees replay: 'binance' == binance_defaults(use_bnb=True), maker == taker."""
        engine = BacktestEngine(MagicMock(), MagicMock(), fee_model="binance", exchange="binance")
        assert engine.fees.maker == engine.fees.taker == Decimal("0.00075")
        assert engine.fees.maker.as_tuple() == engine.fees.taker.as_tuple()

    def test_kraken_reproduces_the_bare_exchange_fees(self) -> None:
        engine = BacktestEngine(MagicMock(), MagicMock(), fee_model="kraken", exchange="kraken")
        bare = ExchangeFees()
        assert [f.as_tuple() for f in _fields(engine.fees)] == [f.as_tuple() for f in _fields(bare)]

    def test_engines_ignore_settings_exchange_fees(self) -> None:
        """Gate e: settings.exchange_fees is the live/paper connector model, never read here."""
        settings = _grid_settings()
        signal = BacktestEngine(settings, MagicMock(), fee_model="bybit")
        grid = GridBacktester(settings, MagicMock(), fee_model="bybit")
        assert signal.fees.maker == grid.fees.maker == Decimal("0.0010")
        assert settings.exchange_fees.maker == Decimal("0.5")

    def test_instance_injection(self) -> None:
        custom = ExchangeFees(maker=Decimal("0.0001"), taker=Decimal("0.0002"))
        engine = BacktestEngine(MagicMock(), MagicMock(), fee_model=custom)
        assert engine.fees is custom
        assert engine.fee_model_name == "custom"

    def test_grid_backtester_rejects_pair_costs(self) -> None:
        """GridBacktester consumes no spread/slippage: accepting the kwarg would be a no-op."""
        with pytest.raises(TypeError, match="pair_costs"):
            GridBacktester(
                _grid_settings(),
                MagicMock(),
                fee_model="bybit",
                pair_costs={"BTC/USDC": PairCosts(Decimal("0.0001"), Decimal("0.0001"))},
            )
