"""Unit tests for ``strategy_params_override`` on BacktestEngine / GridBacktester.

These verify the surgical change added in P7 Phase B.1 without requiring a
real database: we only exercise the param-resolution helpers, not the
full backtest pipeline.
"""

# ruff: noqa: E402
from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from scripts.backtest import BacktestEngine, GridBacktester


def _settings_with(strategies: list[dict]) -> MagicMock:
    """Build a minimal mock Settings with the given strategy entries.

    Each entry: ``{"name": "...", "bot_id": "...", "params": {...}}``.
    """
    ms = MagicMock()
    ms.multi_strategy = MagicMock()
    ms.multi_strategy.enabled = True
    strat_objs = []
    for s in strategies:
        m = MagicMock()
        m.name = s["name"]
        m.bot_id = s.get("bot_id", s["name"])
        m.params = s.get("params")
        strat_objs.append(m)
    ms.multi_strategy.strategies = strat_objs
    return ms


# ---------------------------------------------------------------------------
# BacktestEngine._load_strategy_params
# ---------------------------------------------------------------------------


class TestEngineLoadStrategyParams:
    def test_no_override_returns_yaml_params(self) -> None:
        settings = _settings_with(
            [{"name": "grok_supertrend_4h", "params": {"atr_period": 10, "atr_multiplier": 3.0}}]
        )
        engine = BacktestEngine(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="grok_supertrend_4h",
        )
        out = engine._load_strategy_params("grok_supertrend_4h")
        assert out == {"atr_period": 10, "atr_multiplier": 3.0}

    def test_override_merges_on_top_of_yaml(self) -> None:
        settings = _settings_with(
            [{"name": "grok_supertrend_4h", "params": {"atr_period": 10, "atr_multiplier": 3.0}}]
        )
        engine = BacktestEngine(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="grok_supertrend_4h",
            strategy_params_override={"atr_period": 14},
        )
        out = engine._load_strategy_params("grok_supertrend_4h")
        # YAML value overridden
        assert out["atr_period"] == 14
        # Untouched YAML value preserved
        assert out["atr_multiplier"] == 3.0

    def test_override_adds_new_keys(self) -> None:
        settings = _settings_with([{"name": "x", "params": {"a": 1}}])
        engine = BacktestEngine(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="x",
            strategy_params_override={"b": 2},
        )
        out = engine._load_strategy_params("x")
        assert out == {"a": 1, "b": 2}

    def test_override_when_yaml_missing(self) -> None:
        """If the YAML has no entry, the override alone is used."""
        settings = _settings_with([])
        engine = BacktestEngine(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="x",
            strategy_params_override={"a": 1, "b": 2},
        )
        out = engine._load_strategy_params("x")
        assert out == {"a": 1, "b": 2}

    def test_no_override_no_yaml_returns_none(self) -> None:
        settings = _settings_with([])
        engine = BacktestEngine(
            settings, db_manager=MagicMock(), fee_model="kraken", strategy_name="x"
        )
        assert engine._load_strategy_params("x") is None


# ---------------------------------------------------------------------------
# BacktestEngine._load_inner_strategy_params (router path)
# ---------------------------------------------------------------------------


class TestEngineLoadInnerStrategyParams:
    def test_no_override_returns_inner_yaml(self) -> None:
        settings = _settings_with(
            [
                {
                    "name": "multi_strategy_router",
                    "params": {
                        "strategies": {
                            "grok_supertrend_4h": {
                                "params": {"atr_period": 10, "atr_multiplier": 3.0}
                            }
                        }
                    },
                }
            ]
        )
        engine = BacktestEngine(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="grok_supertrend_4h",
        )
        out = engine._load_inner_strategy_params("grok_supertrend_4h")
        assert out == {"atr_period": 10, "atr_multiplier": 3.0}

    def test_override_merges_on_top_of_inner_yaml(self) -> None:
        settings = _settings_with(
            [
                {
                    "name": "multi_strategy_router",
                    "params": {
                        "strategies": {
                            "grok_supertrend_4h": {
                                "params": {"atr_period": 10, "atr_multiplier": 3.0}
                            }
                        }
                    },
                }
            ]
        )
        engine = BacktestEngine(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="grok_supertrend_4h",
            strategy_params_override={"atr_multiplier": 2.5},
        )
        out = engine._load_inner_strategy_params("grok_supertrend_4h")
        assert out == {"atr_period": 10, "atr_multiplier": 2.5}


# ---------------------------------------------------------------------------
# GridBacktester._load_grid_strategy_params
# ---------------------------------------------------------------------------


class TestGridBacktesterLoadParams:
    def test_no_override_returns_grid_yaml(self) -> None:
        settings = _settings_with(
            [
                {
                    "name": "multi_strategy_router",
                    "params": {
                        "strategies": {
                            "grok_grid_atr_adaptive_v4": {
                                "bot_id": "grid_atr_v4",
                                "params": {"grid_levels": 12, "atr_multiplier": 4.0},
                            }
                        }
                    },
                }
            ]
        )
        bt = GridBacktester(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="grok_grid_atr_adaptive_v4",
        )
        # __init__ already loaded params; check that the result matches
        assert bt._strategy_params == {"grid_levels": 12, "atr_multiplier": 4.0}

    def test_override_merges_on_top_of_grid_yaml(self) -> None:
        settings = _settings_with(
            [
                {
                    "name": "multi_strategy_router",
                    "params": {
                        "strategies": {
                            "grok_grid_atr_adaptive_v4": {
                                "bot_id": "grid_atr_v4",
                                "params": {"grid_levels": 12, "atr_multiplier": 4.0},
                            }
                        }
                    },
                }
            ]
        )
        bt = GridBacktester(
            settings,
            db_manager=MagicMock(),
            fee_model="kraken",
            strategy_name="grok_grid_atr_adaptive_v4",
            strategy_params_override={"atr_multiplier": 2.5, "bear_protection_mode": "1d_only"},
        )
        assert bt._strategy_params["grid_levels"] == 12  # untouched
        assert bt._strategy_params["atr_multiplier"] == 2.5  # overridden
        assert bt._strategy_params["bear_protection_mode"] == "1d_only"  # added
