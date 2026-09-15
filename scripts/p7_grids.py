"""P7 parameter grids for the targeted grid search.

The dict keys MUST match the real strategy ``__init__`` param names (as read
from ``strategies.yaml``), since the values are merged into the per-job
``strategy_params_override`` dict that BacktestEngine / GridBacktester pass
through verbatim.

Mapping spec names → real kwargs (for reviewers tracking the spec):

- SuperTrend: ``atr_period``  → ``st_atr_period``,
              ``atr_multiplier`` → ``st_multiplier``
- Grid ATR V4: ``min_spacing_pct`` (fraction, not %; 0.015 = 1.5%),
               ``atr_multiplier_spacing`` → ``atr_multiplier``,
               ``bear_protection_mode``
- DCA Weekly: ``boost_multiplier`` → ``oversold_multiplier``,
              ``reduction_multiplier`` → ``bull_reduction``,
              ``rsi_oversold_threshold`` → ``rsi_oversold``
- Donchian: ``channel_period`` → ``donchian_upper_period``,
            ``breakout_confirmation``
"""

from __future__ import annotations

from itertools import product
from typing import Any

# ---------------------------------------------------------------------------
# Combos table — which (strategy, pair) combos each grid applies to
# ---------------------------------------------------------------------------

SUPERTREND_PAIRS: tuple[str, ...] = ("BTC/USDC", "ETH/USDC", "SOL/USDC")
GRID_ATR_PAIRS: tuple[str, ...] = ("BTC/USDC", "SOL/USDC")
DCA_WEEKLY_PAIRS: tuple[str, ...] = ("BTC/USDC",)
DONCHIAN_PAIRS: tuple[str, ...] = ("SOL/USDC",)

P7_COMBOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("grok_supertrend_4h", SUPERTREND_PAIRS),
    ("grok_grid_atr_adaptive_v4", GRID_ATR_PAIRS),
    ("grok_adaptive_dca_weekly", DCA_WEEKLY_PAIRS),
    ("grok_donchian_breakout_4h", DONCHIAN_PAIRS),
)


# ---------------------------------------------------------------------------
# Grids — keys are REAL strategy kwarg names
# ---------------------------------------------------------------------------

# 4 × 5 = 20 combos per pair
SUPERTREND_GRID: dict[str, list[Any]] = {
    "st_atr_period": [7, 10, 14, 20],
    "st_multiplier": [2.0, 2.5, 3.0, 3.5, 4.0],
}

# 4 × 4 × 3 = 48 combos per pair
# Note: min_spacing_pct is a FRACTION (0.015 = 1.5%), matching the strategy's
# internal Decimal usage. P7 phase 1 (Binance fees) swept 1.0/1.5/2.0/2.5 %; B4.3 GATE B
# re-floors the sweep for Bybit (maker/maker round trip 0.20 % vs 0.15 %: the 1.5 % floor
# was 10x the cycle cost, 2.0 % keeps that coverage): 1.0 % dropped (5x only), 1.5 % kept
# as the Binance-calibration witness, 3.0 % added. Production floor proposal: 2.0 %.
GRID_ATR_GRID: dict[str, list[Any]] = {
    "min_spacing_pct": [0.015, 0.020, 0.025, 0.030],
    "atr_multiplier": [1.5, 2.0, 2.5, 3.0],
    "bear_protection_mode": ["none", "1w_only", "1d_only"],
}

# 4 × 4 × 3 = 48 combos (BTC only)
DCA_GRID: dict[str, list[Any]] = {
    "oversold_multiplier": [1.5, 2.0, 2.5, 3.0],
    "bull_reduction": [0.3, 0.5, 0.7, 1.0],
    "rsi_oversold": [25, 30, 35],
}

# 4 × 2 = 8 combos (SOL only)
DONCHIAN_GRID: dict[str, list[Any]] = {
    "donchian_upper_period": [10, 15, 20, 30],
    "breakout_confirmation": ["close", "high_low"],
}


GRID_BY_STRATEGY: dict[str, dict[str, list[Any]]] = {
    "grok_supertrend_4h": SUPERTREND_GRID,
    "grok_grid_atr_adaptive_v4": GRID_ATR_GRID,
    "grok_adaptive_dca_weekly": DCA_GRID,
    "grok_donchian_breakout_4h": DONCHIAN_GRID,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def expand_grid(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Return the cartesian product of ``grid`` as a list of param dicts.

    Keys preserve their order from the input dict (relied on by tests and
    by ``make_params_hash`` so two equivalent grids produce identical
    hashes).
    """
    if not grid:
        return [{}]
    keys = list(grid.keys())
    values_lists = [grid[k] for k in keys]
    return [dict(zip(keys, combo, strict=True)) for combo in product(*values_lists)]


def build_phase1_combos() -> list[tuple[str, str, dict[str, Any]]]:
    """Build the full phase-1 job list as ``(strategy, pair, params)`` tuples.

    Returns 212 entries total: 60 SuperTrend + 96 Grid ATR + 48 DCA + 8 Donchian.
    """
    out: list[tuple[str, str, dict[str, Any]]] = []
    for strategy, pairs in P7_COMBOS:
        grid = GRID_BY_STRATEGY[strategy]
        for pair in pairs:
            for params in expand_grid(grid):
                out.append((strategy, pair, params))
    return out


def total_phase1_jobs() -> int:
    """Convenience: how many backtests phase 1 will run."""
    return len(build_phase1_combos())
