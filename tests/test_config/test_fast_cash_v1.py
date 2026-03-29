"""Regression tests for the active fast-cash deployment profile."""

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


def test_fast_cash_v1_profile_matches_operational_plan() -> None:
    """The active router config should stay aligned with the fast-cash v1 plan."""
    yaml_data = _load_strategies_yaml()

    assert yaml_data["deployment_profile"]["name"] == "fast-cash-v1"
    assert yaml_data["deployment_profile"]["trading_pair"] == "XBT/USDC"
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

    assert active_inner == {"grok_grid_atr_adaptive_v4", "grok_supertrend_4h"}
    assert inner["grok_ema_adx_atr"]["active"] is False
    assert inner["grok_adaptive_dca_weekly"]["active"] is False

    grid_params = inner["grok_grid_atr_adaptive_v4"]["params"]
    assert grid_params["order_size_usdc"] == 10
    assert grid_params["max_allocation_pct"] == 10.0

    supertrend_config = inner["grok_supertrend_4h"]
    supertrend_params = supertrend_config["params"]
    # order_size_usdc removed: sizing controlled by 1% rule via position_size_multiplier
    assert "order_size_usdc" not in supertrend_params
    assert supertrend_params["max_allocation_pct"] == 10.0
    assert "pairs" not in supertrend_config


def test_fast_cash_v1_active_router_config_has_no_runtime_alignment_issues() -> None:
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
