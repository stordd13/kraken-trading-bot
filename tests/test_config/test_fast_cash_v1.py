"""Regression tests for the active multi-pair deployment profile."""

from __future__ import annotations

from pathlib import Path

import yaml

from krakenbot.config.settings import (
    MultiStrategySettings,
    StrategyInstanceConfig,
    _validate_router_runtime_alignment,
)


def _load_strategies_yaml() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    return yaml.safe_load((repo_root / "strategies.yaml").read_text())


def test_multi_pair_profile_matches_operational_plan() -> None:
    """The active router config should stay aligned with the multi-pair plan."""
    yaml_data = _load_strategies_yaml()

    assert yaml_data["deployment_profile"]["name"] == "multi-pair-v1"
    assert yaml_data["deployment_profile"]["trading_pairs"] == [
        "BTC/USDC",
        "ETH/USDC",
        "SOL/USDC",
    ]
    assert yaml_data["ml"]["enabled"] is False
    assert yaml_data["global_max_open_positions"] == 8
    assert yaml_data["global_daily_loss_limit_eur"] == 15.0
    assert yaml_data["global_max_portfolio_exposure_pct"] == 25.0

    router = next(
        strategy
        for strategy in yaml_data["strategies"]
        if strategy["name"] == "multi_strategy_router" and strategy["enabled"] is True
    )

    assert router["budget"]["max_open_positions"] == 8
    assert router["budget"]["daily_loss_limit_eur"] == 15.0
    assert router["budget"]["max_position_pct"] == 25.0
    assert router["params"]["capital_usdc"] == 1000

    inner = router["params"]["strategies"]
    active_inner = {name for name, config in inner.items() if config.get("active")}

    # BTC strategies active: grid, supertrend, donchian
    assert active_inner == {"grid_atr_btc", "supertrend_btc", "donchian_btc"}

    # BTC inactive strategies still present
    assert inner["ema_cross_btc"]["active"] is False
    assert inner["dca_btc"]["active"] is False

    # Multi-pair: ETH/SOL strategies exist but inactive
    assert inner["supertrend_eth"]["active"] is False
    assert inner["donchian_sol"]["active"] is False

    # All active BTC strategies have pair: BTC/USDC
    for name in active_inner:
        assert inner[name]["params"]["pair"] == "BTC/USDC"

    # ETH strategies have pair: ETH/USDC
    assert inner["supertrend_eth"]["params"]["pair"] == "ETH/USDC"

    # Class field maps to real strategy class
    assert inner["grid_atr_btc"]["class"] == "grok_grid_atr_adaptive_v4"
    assert inner["supertrend_btc"]["class"] == "grok_supertrend_4h"
    assert inner["donchian_btc"]["class"] == "grok_donchian_breakout_4h"

    grid_params = inner["grid_atr_btc"]["params"]
    assert grid_params["order_size_usdc"] == 10
    assert grid_params["max_allocation_pct"] == 10.0

    supertrend_params = inner["supertrend_btc"]["params"]
    assert supertrend_params["max_allocation_pct"] == 10.0


def test_multi_pair_active_router_config_has_no_runtime_alignment_issues() -> None:
    """The active router config should not rely on fields ignored by the runtime."""
    yaml_data = _load_strategies_yaml()

    multi_strategy = MultiStrategySettings(
        enabled=yaml_data["enabled"],
        strategies=[StrategyInstanceConfig(**strategy) for strategy in yaml_data["strategies"]],
        global_max_open_positions=yaml_data["global_max_open_positions"],
        global_daily_loss_limit_eur=yaml_data["global_daily_loss_limit_eur"],
        global_max_portfolio_exposure_pct=yaml_data["global_max_portfolio_exposure_pct"],
    )

    errors, warnings = _validate_router_runtime_alignment(multi_strategy)

    assert errors == []
    assert warnings == []
