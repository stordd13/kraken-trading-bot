"""Rejeu diagnostic grid — effet, gates ponctuels et bootstrap (prespec § C, § E.3, § F).

Everything here is synthetic: the § C / § E.3 / § F contract is a pure function of an equity path,
a benchmark NAV path and a handful of metric fields, so no DB and no campaign run are needed. The
fixtures are built to trap the defects the pre-specification names, not the happy path:

* a ``liquidation`` block that is absent (``cycles`` unmeasurable — it must NOT read as "below
  coverage", which would pretend the quantity was measured);
* an entry carrying ``"error"`` (§ I-A.3 should have stopped the run: it is a violation here);
* ``positions == 0`` with ``spread_pct`` / ``timestamp`` at ``null`` and Decimals exported as
  strings, the real shape of a flat segment;
* ``sharpe_ratio`` at ``None`` (descriptive, never compared to a threshold);
* a NaN in the equity path (no Δ published, status ``NOT_ESTIMABLE``);
* a config below 25 cycles (``BELOW_COVERAGE``, still inside ``J_calc``, with no published Δ);
* a degenerate bootstrap replication (counted and reported, never silently dropped).

The two searched matchings, the two frozen no-match cases, the strict / inclusive edges of G1 and
G2, the fact that G3 never enters ``passes_gates``, the bit-for-bit reproducibility of the
bootstrap and its invariance to the chunk size, and ``LB_j = Δ̂_j - q_FWE`` for every ``j`` are
each pinned by their own test.
"""

# ruff: noqa: E402
from __future__ import annotations

from decimal import Decimal
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

from p7_grids import GRID_ATR_GRID, expand_grid
import rejeu_common as rc
import rejeu_effect as eff

N_POINTS = rc.SEGMENT_POINTS["all"]
N_RETURNS = rc.SEGMENT_RETURNS["all"]

#: The real BTC block of the post-C2 reference: 4h clean, 1d/1w insufficient by an internal hole.
WARMUP_W1 = {
    "4h": {"interval": 240, "required": 14, "loaded": 91, "extended_by": 0,
           "stale_by_candles": 0, "largest_gap_candles": 0, "sufficient": True,
           "first": "2023-03-17T00:00:00+00:00", "last": "2023-04-01T00:00:00+00:00"},
    "1d": {"interval": 1440, "required": 50, "loaded": 88, "extended_by": 0,
           "stale_by_candles": 0, "largest_gap_candles": 163, "sufficient": False,
           "first": "2022-07-25T00:00:00+00:00", "last": "2023-04-01T00:00:00+00:00"},
    "1w": {"interval": 10080, "required": 50, "loaded": 50, "extended_by": 19,
           "stale_by_candles": 0, "largest_gap_candles": 23, "sufficient": False,
           "first": "2021-10-18T00:00:00+00:00", "last": "2023-03-27T00:00:00+00:00"},
}
#: The real SOL block: 4h never loaded, staleness unknown.
WARMUP_W2 = {
    "4h": {"interval": 240, "required": 14, "loaded": 0, "extended_by": 0,
           "stale_by_candles": None, "largest_gap_candles": 0, "sufficient": False,
           "first": None, "last": None},
    "1d": {"interval": 1440, "required": 50, "loaded": 50, "extended_by": 0,
           "stale_by_candles": 183, "largest_gap_candles": 0, "sufficient": False,
           "first": "2021-01-01T00:00:00+00:00", "last": "2022-09-29T00:00:00+00:00"},
    "1w": {"interval": 10080, "required": 50, "loaded": 50, "extended_by": 0,
           "stale_by_candles": 25, "largest_gap_candles": 0, "sufficient": False,
           "first": "2020-01-06T00:00:00+00:00", "last": "2022-09-26T00:00:00+00:00"},
}
WARMUP_W0 = {
    tf: dict(block, sufficient=True, largest_gap_candles=0, stale_by_candles=0, loaded=200)
    for tf, block in WARMUP_W1.items()
}


# ---------------------------------------------------------------------------
# Synthetic paths
# ---------------------------------------------------------------------------


def _walk(seed: int, *, drift: float, amplitude: float, points: int = N_POINTS) -> list[float]:
    """A deterministic, always positive NAV path that moves every day, both ways."""
    rng = np.random.default_rng(seed)
    steps = drift + amplitude * rng.standard_normal(points - 1)
    nav = float(rc.CAPITAL) * np.cumprod(1.0 + steps)
    return [float(rc.CAPITAL)] + [round(float(v), 8) for v in nav]


def _bench_nav() -> list[float]:
    return _walk(7, drift=0.0008, amplitude=0.02)


def _config_nav(seed: int = 3, *, drift: float = 0.0001, amplitude: float = 0.004) -> list[float]:
    return _walk(seed, drift=drift, amplitude=amplitude)


def _liquidation(positions: int = 4) -> dict[str, Any]:
    """The real 18-key shape: Decimals as strings, and nulls everywhere on a flat segment."""
    flat = positions == 0
    return {
        "buy_fees": "1.4250",
        "sell_fees": "1.599524923912797317873778012",
        "net_pnl_lot_basis": "45.72240532242140320815638471",
        "residual_net_proceeds": "0",
        "avg_holding_minutes": 0.0 if flat else 108008.75,
        "positions": positions,
        "trades": 0 if flat else positions,
        "residual_trade_btc": "0",
        "dust_written_off_btc": "-6E-31",
        "inventory_divergence_btc": "0E-30",
        "pnl": "-15.31000921180202696374768378",
        "fees": "0.2120049894441051955795797399",
        "gross_usdc": "84.80199577764207823183189597",
        "timestamp": None if flat else "2026-04-01T00:00:00+00:00",
        "reference_price": None if flat else "68240.16000000",
        "price": None if flat else "68212.863936000000",
        "spread_pct": None if flat else "0.0002",
        "slippage_pct": None if flat else "0.0002",
    }


def _metrics(
    values: list[float], *, total_trades: int, net_pnl: float, total_fees: float,
    sharpe: float | None = 0.93,
) -> dict[str, Any]:
    return {
        "metrics_version": 2,
        "total_trades": total_trades,
        "winning_trades": total_trades,
        "losing_trades": 0,
        "win_rate": 1.0,
        "total_return_pct": (values[-1] - values[0]) / values[0] * 100.0,
        "sharpe_ratio": sharpe,
        "sortino_ratio": 1.49,
        "max_drawdown_pct_daily": 2.04,
        "max_drawdown_pct_engine": 2.57,
        "profit_factor": None,
        "calmar_ratio": 0.73,
        "net_pnl": net_pnl,
        "total_fees": total_fees,
        "total_pnl": net_pnl + total_fees,
        "unrealized_pnl": -15.310009211802027,
        "starting_balance": 1000.0,
        "ending_balance": 1000.0 + net_pnl,
        "duration_days": 1096.0,
        "average_holding_time_minutes": 5776.98,
        "gross_profit_net": 61.13,
        "gross_loss_net": 15.41,
        "pf_excluded_trades": 0,
        "n_daily_returns": N_RETURNS,
    }


def _entry(
    *,
    pair: str = "BTC/USDC",
    params: dict[str, Any] | None = None,
    values: list[float] | None = None,
    total_trades: int = 57,
    positions: int = 4,
    net_pnl: float = 45.72,
    total_fees: float = 3.02,
    warmup: dict[str, Any] | None = None,
    sharpe: float | None = 0.93,
    total_return_pct: float | None = None,
    with_liquidation: bool = True,
) -> dict[str, Any]:
    values = values if values is not None else _config_nav()
    metrics = _metrics(
        values, total_trades=total_trades, net_pnl=net_pnl, total_fees=total_fees, sharpe=sharpe
    )
    if total_return_pct is not None:
        metrics["total_return_pct"] = total_return_pct
    entry: dict[str, Any] = {
        "strategy": rc.STRATEGY,
        "pair": pair,
        "exchange": rc.EXCHANGE,
        "fees": rc.FEES_MODEL,
        "metrics_version": 2,
        "replay_version": 2,
        "params": params or {"min_spacing_pct": 0.015, "atr_multiplier": 1.5,
                             "bear_protection_mode": "none"},
        "phase": "1",
        "window_idx": None,
        "equity_daily": {
            "all": {"start": rc.WINDOW_START.isoformat(), "end": rc.WINDOW_END.isoformat(),
                    "values": values}
        },
        "warmup": {"all": warmup if warmup is not None else WARMUP_W1},
        "train": metrics,
        "test": metrics,
        "all": metrics,
    }
    if with_liquidation:
        entry["liquidation"] = {"all": _liquidation(positions)}
    return entry


def _ctx(bench: list[float] | None = None, **kwargs: Any) -> eff.PairContext:
    bench = bench if bench is not None else _bench_nav()
    ctx = eff.PairContext(
        pair=kwargs.pop("pair", "BTC/USDC"),
        pair_index=0,
        admissible=kwargs.pop("admissible", True),
        warmup=kwargs.pop("warmup", "W1"),
        benchmark_comparable=kwargs.pop("benchmark_comparable", True),
        bench_nav=bench,
    )
    ctx.bench_returns = rc.daily_returns(bench)
    return ctx


# ---------------------------------------------------------------------------
# § C — cycles and coverage
# ---------------------------------------------------------------------------


def test_cycles_is_total_trades_minus_liquidated_positions() -> None:
    ctx = _ctx()
    result = eff.analyse_config("k", _entry(total_trades=57, positions=4), ctx)
    assert result.payload["cycles"] == 53  # the post-C2 BTC reference: 57 - 4


def test_cycles_on_a_flat_segment_reads_the_null_shape() -> None:
    """``positions == 0`` exports null spread / timestamp and ``trades == 0`` — never a crash."""
    ctx = _ctx()
    entry = _entry(total_trades=30, positions=0)
    assert entry["liquidation"]["all"]["spread_pct"] is None
    result = eff.analyse_config("k", entry, ctx)
    assert result.payload["cycles"] == 30


def test_missing_liquidation_block_is_not_estimable_not_below_coverage() -> None:
    """The false green of § I: an absent block makes ``cycles`` unmeasurable, not small."""
    ctx = _ctx()
    result = eff.analyse_config("k", _entry(with_liquidation=False), ctx)
    assert result.payload["cycles"] is None
    assert result.payload["status"] == rc.STATUS_NOT_ESTIMABLE
    assert result.payload["first_failing_gate"] == eff.REASON_NOT_ESTIMABLE


def test_below_25_cycles_is_below_coverage_with_no_published_delta() -> None:
    ctx = _ctx()
    entry = _entry(total_trades=28, positions=4)  # 24 cycles, one under the frozen filter
    result = eff.analyse_config("k", entry, ctx)
    assert result.payload["cycles"] == rc.CYCLES_MIN - 1
    assert result.payload["status"] == rc.STATUS_BELOW_COVERAGE
    assert result.payload["first_failing_gate"] == eff.REASON_COVERAGE
    assert result.payload["delta_dd"] is None and result.payload["delta_sigma"] is None
    assert result.payload["lambda_dd"] is None and result.payload["lambda_sigma"] is None
    assert result.payload["passes_gates"] is False
    assert result.payload["gates"] == {"G1": None, "G2": None, "G4": None}
    # ... and it stays in the correction family (§ F.4: no -inf padding, no filtering here)
    assert result.computable is True
    assert result.payload["nnz"] is not None
    assert result.payload["beta_hat"] is not None


def test_coverage_table_is_the_four_by_four_by_three_grid() -> None:
    entries = {
        f"k{i}": _entry(params=params, total_trades=30 + i, positions=4)
        for i, params in enumerate(expand_grid(GRID_ATR_GRID))
    }
    analysis = eff.analyse_pair("BTC/USDC", entries, admissible=True, benchmark=_benchmark_block())
    rows = eff.coverage_rows(analysis)
    assert len(rows) == 48
    assert len({(r["min_spacing_pct"], r["atr_multiplier"], r["bear_protection_mode"])
                for r in rows}) == 48
    assert rows[0]["cycles"] == 26 and rows[0]["below"] is False
    assert sum(1 for r in rows if r["below"]) == 0


def test_coverage_table_shows_a_missing_cell_as_truncated() -> None:
    entries = {"k0": _entry(params=expand_grid(GRID_ATR_GRID)[0], total_trades=30, positions=4)}
    analysis = eff.analyse_pair("BTC/USDC", entries, admissible=True, benchmark=_benchmark_block())
    rows = eff.coverage_rows(analysis)
    assert len(rows) == 48
    assert sum(1 for r in rows if r["cycles"] is None) == 47
    assert all(r["below"] for r in rows if r["cycles"] is None)


# ---------------------------------------------------------------------------
# § E.3 — the two matchings, by search on the constructed static blends
# ---------------------------------------------------------------------------


def test_static_blend_is_the_closed_form_not_a_rebalanced_series() -> None:
    nav = [Decimal("1000"), Decimal("1200"), Decimal("900")]
    blend = eff.blend_values(nav, Decimal("0.25"))
    assert blend == [Decimal("1000"), Decimal("1050"), Decimal("975")]


def test_lambda_dd_finds_the_unique_crossing_with_a_small_residual() -> None:
    curve = eff.dd_curve(_bench_nav())
    assert curve[0] == 0.0
    assert all(b >= a - 1e-12 for a, b in zip(curve, curve[1:], strict=False))  # monotone (§ E.3)
    target = curve[300]
    match = eff.match_lambda(curve, target)
    assert match.lam == pytest.approx(0.300)
    assert match.residual == 0.0
    assert match.crossings == 1  # proved unique for the static blend
    between = (curve[300] + curve[301]) / 2
    match = eff.match_lambda(curve, between)
    assert match.lam == pytest.approx(0.301)
    assert match.residual < 0.01
    assert match.approximate is False


def test_lambda_sigma_counts_the_crossings_and_keeps_the_smallest() -> None:
    """Monotonicity is NOT proved for σ: the count is reported, the smallest λ is retained."""
    curve = [0.0, 0.5, 1.5, 0.4, 1.6, 2.0] + [3.0] * (eff.LAMBDA_COUNT - 6)
    match = eff.match_lambda(curve, 1.0)
    assert match.lam == pytest.approx(0.002)  # the smallest crossing, not the last one
    assert match.crossings == 3
    assert eff.count_crossings(curve, 1.0) == 3


def test_sigma_curve_is_increasing_enough_to_match_on_the_real_blend() -> None:
    curve = eff.sigma_curve(_bench_nav())
    assert curve[0] == 0.0
    target = curve[500]
    match = eff.match_lambda(curve, target)
    assert match.lam == pytest.approx(0.500)
    assert match.crossings == 1


def test_no_match_above_the_full_notional_gives_lambda_one() -> None:
    curve = eff.dd_curve(_bench_nav())
    match = eff.match_lambda(curve, curve[-1] * 2.0)
    assert match.lam == 1.0
    assert match.label == eff.MATCH_ABOVE_BH
    assert match.residual == pytest.approx(0.5)
    assert match.approximate is True  # descriptive only


def test_no_match_at_zero_target_gives_the_pure_cash_comparator() -> None:
    curve = eff.dd_curve(_bench_nav())
    match = eff.match_lambda(curve, 0.0)
    assert match.lam == 0.0
    assert match.label == eff.MATCH_PURE_CASH
    assert match.residual == 0.0


def test_delta_is_cagr_of_the_config_minus_cagr_of_the_blend() -> None:
    ctx = _ctx()
    values = _config_nav()
    result = eff.analyse_config("k", _entry(values=values), ctx)
    expected = rc.cagr_from_returns(rc.daily_returns(values)) - eff.blend_cagr(
        ctx.bench_nav or [], result.payload["lambda_dd"]
    )
    assert result.payload["delta_dd"] == pytest.approx(expected, abs=1e-12)


def test_mdd_reference_path_goes_through_the_decimal_routine() -> None:
    """``max_drawdown_pct`` is Decimal-only: a float sequence must raise, ours must not."""
    from krakenbot.backtest_metrics import max_drawdown_pct

    with pytest.raises(TypeError):
        max_drawdown_pct([1000.0, 900.0])
    assert eff.mdd_of_values([1000.0, 900.0]) == pytest.approx(10.0)


def test_vectorised_mdd_matches_the_decimal_routine() -> None:
    nav = _bench_nav()
    navs = [Decimal(str(v)) for v in nav]
    series = [nav] + [
        [float(v) for v in eff.blend_values(navs, Decimal(str(lam)))] for lam in (0.1, 0.5, 1.0)
    ]
    check = eff.mdd_equivalence(series)
    assert check["verified"] is True
    assert check["max_relative_residual"] <= eff.MDD_EQUIVALENCE_TOL
    assert check["n_series"] == 4
    assert check["time_decimal_sec"] > 0 and check["time_numpy_sec"] > 0


# ---------------------------------------------------------------------------
# § D.4 — warmup classes
# ---------------------------------------------------------------------------


def test_warmup_classes_are_exhaustive() -> None:
    assert eff.warmup_class(WARMUP_W0) == "W0"
    assert eff.warmup_class(WARMUP_W1) == "W1"
    assert eff.warmup_class(WARMUP_W2) == "W2"
    stale = {tf: dict(block) for tf, block in WARMUP_W1.items()}
    stale["1d"]["stale_by_candles"] = 3  # a stale timeframe is never W1
    assert eff.warmup_class(stale) == "W2"
    short = {tf: dict(block) for tf, block in WARMUP_W1.items()}
    short["1w"]["loaded"] = 10  # loaded < required for another reason than the hole
    assert eff.warmup_class(short) == "W2"
    assert eff.warmup_class(None) == "W2"
    assert eff.warmup_class({"4h": WARMUP_W1["4h"]}) == "W2"


def test_pair_keeps_the_strictest_warmup_class() -> None:
    entries = [_entry(warmup=WARMUP_W1), _entry(warmup=WARMUP_W2)]
    assert eff.pair_warmup_class(entries) == ("W2", 2)
    assert eff.pair_warmup_class([_entry(warmup=WARMUP_W1)]) == ("W1", 1)


def test_w2_pair_makes_every_config_descriptive() -> None:
    ctx = _ctx(warmup="W2")
    result = eff.analyse_config("k", _entry(warmup=WARMUP_W2), ctx)
    assert result.payload["status"] == rc.STATUS_DESCRIPTIF
    assert result.payload["first_failing_gate"] == eff.REASON_WARMUP_W2
    assert result.payload["delta_dd"] is None


def test_inadmissible_pair_wins_over_every_other_clause() -> None:
    ctx = _ctx(admissible=False)
    result = eff.analyse_config("k", _entry(total_trades=5, positions=4), ctx)
    assert result.payload["status"] == rc.STATUS_DESCRIPTIF
    assert result.payload["first_failing_gate"] == eff.REASON_NOT_ADMISSIBLE


def test_no_benchmark_stops_before_coverage() -> None:
    ctx = _ctx(benchmark_comparable=False)
    result = eff.analyse_config("k", _entry(total_trades=5, positions=4), ctx)
    assert result.payload["status"] == rc.STATUS_NO_BENCHMARK
    assert result.payload["first_failing_gate"] == eff.REASON_NO_BENCHMARK
    assert result.computable is False


# ---------------------------------------------------------------------------
# § F.3 / § F.6 — point gates and eligibility
# ---------------------------------------------------------------------------


def test_g1_is_strict_and_g2_is_inclusive_on_their_thresholds() -> None:
    ctx = _ctx()
    on_edge = eff.analyse_config(
        "k", _entry(net_pnl=0.0, total_return_pct=rc.G2_MIN_RETURN_PCT), ctx
    )
    assert on_edge.payload["gates"]["G1"] is False  # net_pnl > 0 is strict
    assert on_edge.payload["gates"]["G2"] is True  # total_return_pct >= 6.0 is inclusive
    assert on_edge.payload["first_failing_gate"] == "G1"
    below = eff.analyse_config(
        "k", _entry(net_pnl=1e-9, total_return_pct=rc.G2_MIN_RETURN_PCT - 1e-9), ctx
    )
    assert below.payload["gates"]["G1"] is True
    assert below.payload["gates"]["G2"] is False
    assert below.payload["first_failing_gate"] == "G2"


def test_point_gates_fire_exactly_on_their_thresholds() -> None:
    """G1 strict, G2 inclusive, G4 strict on both matchings — and no fourth gate exists."""
    both = {"dd": 1e-12, "sigma": 1e-12}
    assert eff.point_gates(net_pnl=1e-12, total_return_pct=6.0, deltas=both) == {
        "G1": True, "G2": True, "G4": True
    }
    assert eff.point_gates(net_pnl=0.0, total_return_pct=6.0, deltas=both)["G1"] is False
    assert eff.point_gates(net_pnl=1.0, total_return_pct=5.999999, deltas=both)["G2"] is False
    zero = {"dd": 0.0, "sigma": 1.0}
    assert eff.point_gates(net_pnl=1.0, total_return_pct=6.0, deltas=zero)["G4"] is False
    one_side = {"dd": 1.0, "sigma": -1e-12}
    assert eff.point_gates(net_pnl=1.0, total_return_pct=6.0, deltas=one_side)["G4"] is False
    missing = {"dd": 1.0, "sigma": None}
    assert eff.point_gates(net_pnl=1.0, total_return_pct=6.0, deltas=missing)["G4"] is False
    assert eff.first_failing_point_gate({"G1": True, "G2": False, "G4": False}) == "G2"
    assert eff.first_failing_point_gate({"G1": True, "G2": True, "G4": True}) is None


def test_g4_needs_both_deltas_strictly_positive() -> None:
    ctx = _ctx()
    # A config that tracks a flat cash line: Δ against a matched blend is <= 0.
    flat = [float(rc.CAPITAL)] * N_POINTS
    result = eff.analyse_config("k", _entry(values=flat), ctx)
    assert result.payload["status"] == rc.STATUS_NOT_ESTIMABLE  # nnz 0 < 110
    assert result.payload["first_failing_gate"] == eff.REASON_NOT_ESTIMABLE
    losing = eff.analyse_config("k", _entry(values=_config_nav(11, drift=-0.0005)), ctx)
    assert losing.payload["status"] == rc.STATUS_ELIGIBLE
    assert losing.payload["delta_dd"] < 0
    assert losing.payload["gates"]["G4"] is False


def test_fee_multiple_is_exported_but_never_a_gate() -> None:
    ctx = _ctx()
    winner = _entry(values=_config_nav(5, drift=0.0006), net_pnl=40.0, total_fees=20.0)
    result = eff.analyse_config("k", winner, ctx)
    assert result.payload["fee_multiple"] == pytest.approx(2.0)  # far below G3's 10x
    assert result.payload["fee_multiple"] < rc.G3_FEE_MULTIPLE
    assert set(result.payload["gates"]) == {"G1", "G2", "G4"}  # G3 is not a gate
    assert result.payload["passes_gates"] is True
    assert all(result.payload["gates"].values())


def test_fee_multiple_is_none_when_no_fee_was_paid() -> None:
    result = eff.analyse_config("k", _entry(total_fees=0.0), _ctx())
    assert result.payload["fee_multiple"] is None
    assert result.payload["passes_gates"] in (True, False)  # never blocked by the missing ratio


def test_nnz_below_the_activity_floor_is_not_estimable() -> None:
    values = list(_config_nav())
    for i in range(1, N_POINTS):  # only 50 days move, the rest is forward-filled flat
        if i > 50:
            values[i] = values[50]
    result = eff.analyse_config("k", _entry(values=values), _ctx())
    assert result.payload["nnz"] < rc.NNZ_MIN
    assert result.payload["status"] == rc.STATUS_NOT_ESTIMABLE
    assert result.payload["delta_dd"] is None


def test_a_nan_in_the_equity_path_publishes_nothing() -> None:
    values = list(_config_nav())
    values[10] = float("nan")
    result = eff.analyse_config("k", _entry(values=values), _ctx())
    assert result.payload["status"] == rc.STATUS_NOT_ESTIMABLE
    assert result.computable is False
    assert result.payload["delta_dd"] is None and result.payload["lambda_dd"] is None


def test_a_daily_crash_below_the_log1p_domain_is_not_estimable() -> None:
    values = list(_config_nav())
    values[500] = values[499] * 0.4  # r = -0.6 < -0.5
    result = eff.analyse_config("k", _entry(values=values), _ctx())
    assert result.payload["status"] == rc.STATUS_NOT_ESTIMABLE
    assert result.computable is False


def test_a_curve_that_is_not_1096_returns_long_is_not_estimable() -> None:
    result = eff.analyse_config("k", _entry(values=_config_nav()[:500]), _ctx())
    assert result.payload["status"] == rc.STATUS_NOT_ESTIMABLE
    assert result.computable is False
    assert eff.returns_usable(rc.daily_returns(_config_nav()[:500])) is False


def test_sharpe_none_is_carried_and_never_compared() -> None:
    result = eff.analyse_config("k", _entry(sharpe=None), _ctx())
    assert result.payload["sharpe_ratio"] is None
    assert result.payload["status"] == rc.STATUS_ELIGIBLE  # no threshold reads the Sharpe


def test_an_entry_carrying_an_error_is_not_estimable_and_a_violation() -> None:
    entry = _entry()
    entry["error"] = "mp.TimeoutError"
    entry["traceback"] = "..."
    result = eff.analyse_config("k", entry, _ctx())
    assert result.payload["status"] == rc.STATUS_NOT_ESTIMABLE
    assert eff.ENTRY_ERROR_NOTE in result.notes


# ---------------------------------------------------------------------------
# § F.4 — bootstrap, simultaneous correction
# ---------------------------------------------------------------------------


def _bootstrap_inputs(n_configs: int = 3, n: int = 120) -> dict[str, Any]:
    rng = np.random.default_rng(99)
    bench = rng.normal(0.0008, 0.02, n)
    returns = np.column_stack(
        [rng.normal(0.0002 + 0.0001 * j, 0.004, n) for j in range(n_configs)]
    )
    keys = [f"cfg{j}" for j in range(n_configs)]
    delta_hat = {name: np.linspace(0.5, 1.5, n_configs) for name in rc.MATCHINGS}
    frozen = {name: np.full(n_configs, 0.2) for name in rc.MATCHINGS}
    return {
        "keys": keys,
        "returns": returns,
        "bench_returns": bench,
        "delta_hat": delta_hat,
        "frozen_lambda": frozen,
        "pair_index": 0,
        "block_lengths": [10, 21],
        "replications": 40,
    }


def test_bootstrap_is_reproducible_bit_for_bit() -> None:
    inputs = _bootstrap_inputs()
    first = eff.bootstrap_pair(**inputs, chunk_size=40)
    second = eff.bootstrap_pair(**inputs, chunk_size=40)
    assert first.q_fwe == second.q_fwe
    assert first.lb == second.lb
    assert first.se == second.se


def test_bootstrap_is_unchanged_by_the_chunk_size() -> None:
    """The chunks apply to the ALREADY drawn ``starts`` matrix, so no draw can move."""
    inputs = _bootstrap_inputs()
    whole = eff.bootstrap_pair(**inputs, chunk_size=40)
    split = eff.bootstrap_pair(**inputs, chunk_size=7)
    assert whole.q_fwe == split.q_fwe
    assert whole.lb == split.lb


def test_lb_is_delta_hat_minus_q_fwe_for_every_config() -> None:
    inputs = _bootstrap_inputs()
    outcome = eff.bootstrap_pair(**inputs, chunk_size=13)
    for label in ("10", "21"):
        for name in rc.MATCHINGS:
            quantile = outcome.q_fwe[label][name]
            for column, key in enumerate(inputs["keys"]):
                expected = float(inputs["delta_hat"][name][column]) - quantile
                assert outcome.lb[key][label][name] == pytest.approx(expected, abs=1e-12)
    assert set(outcome.lb) == set(inputs["keys"])  # produced for EVERY j of J_calc


def test_the_max_t_statistic_is_recentred_on_the_family() -> None:
    """``V*_b = max_j (Δ*_{b,j} - Δ̂_j)`` — one shared quantile, not one per config."""
    inputs = _bootstrap_inputs()
    outcome = eff.bootstrap_pair(**inputs, chunk_size=40)
    for label in outcome.q_fwe:
        for name in rc.MATCHINGS:
            spreads = {
                float(inputs["delta_hat"][name][column]) - outcome.lb[key][label][name]
                for column, key in enumerate(inputs["keys"])
            }
            assert len(spreads) == 1  # the same q_FWE for every config


def test_degenerate_replications_are_counted_not_dropped() -> None:
    inputs = _bootstrap_inputs(n_configs=2)
    inputs["returns"][17, 1] = -1.5  # log1p(-1.5) is NaN: Δ* is not finite whenever that date hits
    outcome = eff.bootstrap_pair(**inputs, chunk_size=20)
    assert outcome.degenerate["cfg1"] > 0
    assert outcome.degenerate["cfg0"] == 0
    assert all(math.isfinite(v) for values in outcome.q_fwe.values() for v in values.values())


def test_frozen_lambda_fallback_is_labelled() -> None:
    inputs = _bootstrap_inputs()
    outcome = eff.bootstrap_pair(**inputs, chunk_size=40, reestimate=False)
    assert outcome.mode == eff.LAMBDA_MODE_FROZEN
    assert all(cost == 0.0 for values in outcome.cost_sec.values() for cost in values.values())


def test_a_budget_of_zero_raises_before_publishing_anything() -> None:
    inputs = _bootstrap_inputs()
    with pytest.raises(eff.BudgetExceeded):
        eff.bootstrap_pair(**inputs, chunk_size=10, budget_sec=0.0)


def test_block_indices_are_circular_and_paired() -> None:
    starts = np.array([[0, 5], [3, 3]])
    idx = eff.block_indices(starts, 3, 6)
    assert idx.tolist() == [[0, 1, 2, 5, 0, 1], [3, 4, 5, 3, 4, 5]]
    counts = eff.date_counts(idx, 6)
    assert counts.sum(axis=1).tolist() == [6, 6]
    assert counts[0].tolist() == [2, 2, 1, 0, 0, 1]


def test_the_two_stage_inversion_agrees_with_the_full_grid_when_monotone() -> None:
    lams = eff.lambda_array()
    curve = np.asarray([lams * 10.0, lams**2 * 10.0])
    targets = np.asarray([[1.0, 7.3], [2.5, 9.99]])
    assert np.array_equal(
        eff.invert_curve(curve, targets, lams),
        eff.invert_curve_two_stage(curve, targets, lams),
    )


def test_inversion_returns_one_when_the_curve_never_reaches_the_target() -> None:
    lams = eff.lambda_array()
    curve = np.asarray([lams * 10.0])
    assert eff.invert_curve(curve, np.asarray([[11.0]]), lams).tolist() == [[1.0]]


def test_a_pair_over_the_degenerate_ceiling_is_declared_not_estimable(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ F.7 — more than 10 degenerate replications on one config kills the pair's inference."""
    entries = {
        f"k{i}": _entry(params=params, values=_config_nav(300 + i, drift=0.0004))
        for i, params in enumerate(expand_grid(GRID_ATR_GRID)[:3])
    }
    analysis = eff.analyse_pair("BTC/USDC", entries, admissible=True, benchmark=_benchmark_block())
    assert analysis.j_eligible  # the bootstrap would run
    fake = eff.BootstrapOutcome(
        q_fwe={"21": {"dd": 0.1, "sigma": 0.1}},
        lb={key: {"21": {"dd": 1.0, "sigma": 1.0}} for key in analysis.j_calc},
        se={key: {"21": {"dd": 0.5, "sigma": 0.5}} for key in analysis.j_calc},
        degenerate=dict.fromkeys(analysis.j_calc, rc.DEGENERATE_MAX + 1),
        cost_sec={"21": {"dd": 1.0, "sigma": 1.0}},
        mode=eff.LAMBDA_MODE_REESTIMATED,
    )
    monkeypatch.setattr(eff, "bootstrap_pair", lambda **kwargs: fake)
    eff.run_pair_bootstrap(
        analysis, block_lengths=[21], replications=40, chunk_size=40, reestimate=True,
        budget_sec=1.0,
    )
    assert analysis.not_estimable is True
    assert analysis.reason == eff.REASON_NOT_ESTIMABLE
    payload = next(r for r in analysis.results if r.eligible).payload
    assert payload["LB"]["21"]["dd"] == 1.0  # the numbers stay visible
    assert payload["degenerate_replications"] == rc.DEGENERATE_MAX + 1
    assert payload["LB_all_six_positive"] is False  # but cannot carry a candidat


def test_seed_stream_depends_on_pair_and_block_length() -> None:
    assert eff.stream_seed(0, 21) != eff.stream_seed(1, 21)
    assert eff.stream_seed(0, 21) != eff.stream_seed(0, 42)
    assert eff.stream_seed(0, 21) == eff.stream_seed(0, 21)


# ---------------------------------------------------------------------------
# End to end — the artefact
# ---------------------------------------------------------------------------


def _benchmark_block(nav: list[float] | None = None, comparable: bool = True) -> dict[str, Any]:
    nav = nav if nav is not None else _bench_nav()
    return {
        "buildable": True,
        "reason": None,
        "entry_price": 30000.0,
        "exit_price": 40000.0,
        "costs_charged": {"taker": "0.0025", "spread": "0.0002", "slippage": "0.0002"},
        "nav": nav,
        "returns": rc.daily_returns(nav),
        "metrics": {"sharpe_ratio": 0.84, "sortino_ratio": 1.1,
                    "max_drawdown_pct_daily": 49.65, "cagr_pct": 33.0, "calmar_ratio": 0.66,
                    "n_daily_returns": N_RETURNS, "total_return_pct": 137.51,
                    "sigma_daily": 0.02},
        "comparability": {"ff_days": 0, "ff_ok": True, "candle_at_start": True,
                          "candle_at_end": True, "n_daily_returns_ok": True, "all_finite": True,
                          "min_return_ok": True, "midnight_crosscheck_mismatches": 0,
                          "midnight_crosscheck_checked": 1095, "comparable": comparable},
        "historical_descriptors": None,
    }


def _campaign(tmp_path: Path) -> dict[str, Path]:
    """A full 96-entry campaign: BTC admissible and comparable, SOL inadmissible and W2."""
    grid = expand_grid(GRID_ATR_GRID)
    campaign: dict[str, Any] = {}
    for index, params in enumerate(grid):
        campaign[f"{rc.STRATEGY}_BTC_USDC_p1_{index:08x}"] = _entry(
            pair="BTC/USDC",
            params=params,
            values=_config_nav(100 + index, drift=0.0001 + index * 2e-5),
            total_trades=(28 if index == 0 else 30 + index),
            positions=4,
            net_pnl=40.0 + index,
            total_fees=3.0,
        )
        campaign[f"{rc.STRATEGY}_SOL_USDC_p1_{index:08x}"] = _entry(
            pair="SOL/USDC",
            params=params,
            values=_config_nav(500 + index, drift=0.0002),
            total_trades=40,
            positions=2,
            warmup=WARMUP_W2,
        )
    paths = {
        "campaign": tmp_path / "P7_phase1_grid.json",
        "benchmark": tmp_path / "benchmark.json",
        "coverage": tmp_path / "data_coverage.json",
        "validation": tmp_path / "validation_campaign.json",
        "output": tmp_path / "effect.json",
        "markdown": tmp_path / "effect.md",
    }
    paths["campaign"].write_text(json.dumps(campaign), encoding="utf-8")
    paths["benchmark"].write_text(
        json.dumps({
            "generated_at": "2026-09-19T00:00:00+00:00",
            "pairs": {
                "BTC/USDC": _benchmark_block(),
                "SOL/USDC": {"buildable": False, "reason": "first candle 271 days late",
                             "nav": None, "returns": None, "metrics": None,
                             "comparability": {"comparable": False}},
            },
        }),
        encoding="utf-8",
    )
    paths["coverage"].write_text(
        json.dumps({"pairs": {"BTC/USDC": {"admissible": True},
                              "SOL/USDC": {"admissible": False}}}),
        encoding="utf-8",
    )
    paths["validation"].write_text(json.dumps({"ok": True, "exit_code": 0}), encoding="utf-8")
    return paths


def _argv(paths: dict[str, Path], *extra: str) -> list[str]:
    return [
        "--campaign", str(paths["campaign"]),
        "--benchmark", str(paths["benchmark"]),
        "--coverage", str(paths["coverage"]),
        "--validation", str(paths["validation"]),
        "--output", str(paths["output"]),
        "--calibration", str(paths["campaign"].parent / "does-not-exist.json"),
        "--bootstrap-b", "40",
        "--block-lengths", "10,21",
        "--now", "2026-09-19T12:00:00+00:00",
        *extra,
    ]


@pytest.fixture(scope="module")
def campaign_run(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp_path = tmp_path_factory.mktemp("rejeu_effect")
    paths = _campaign(tmp_path)
    code = eff.main(_argv(paths, "--markdown", str(paths["markdown"])))
    return {"code": code, "paths": paths, "payload": json.loads(
        paths["output"].read_text(encoding="utf-8")
    )}


def test_artifact_carries_the_frozen_header(campaign_run: dict[str, Any]) -> None:
    payload = campaign_run["payload"]
    assert campaign_run["code"] == 0
    assert payload["generated_at"] == "2026-09-19T12:00:00+00:00"
    assert payload["base_sha"] == rc.BASE_SHA
    assert payload["prespec"]["path"] == eff.PRESPEC_RELPATH
    assert payload["B"] == 40 and payload["block_lengths"] == [10, 21]  # overrides are recorded
    assert payload["numpy_version"] == np.__version__
    assert payload["lambda_mode"] == eff.LAMBDA_MODE_REESTIMATED
    assert payload["lambda_mode_label"] is None
    assert set(payload["seeds"]) == {"BTC/USDC", "SOL/USDC"}
    assert payload["seeds"]["BTC/USDC"]["21"] == eff.stream_seed(0, 21)


def test_admissible_pair_publishes_bounds_and_gates(campaign_run: dict[str, Any]) -> None:
    block = campaign_run["payload"]["pairs"]["BTC/USDC"]
    assert block["admissible"] is True and block["warmup_class"] == "W1"
    assert block["benchmark_comparable"] is True
    assert block["n_J_calc"] == 48  # the correction family keeps the below-coverage curve
    assert len(block["J_eligible"]) == 47
    assert set(block["q_FWE"]) == {"10", "21"}
    assert block["se_ratio_max_min"] is None or block["se_ratio_max_min"] > 0
    for key in block["J_eligible"]:
        config = block["configs"][key]
        assert config["status"] == rc.STATUS_ELIGIBLE
        assert set(config["LB"]) == {"10", "21"}
        for label, values in config["LB"].items():
            for name in rc.MATCHINGS:
                expected = config[f"delta_{name}"] - block["q_FWE"][label][name]
                assert values[name] == pytest.approx(expected, abs=1e-9)
        assert config["se"]["21"] > 0
        assert config["jackknife_delta_dd"] is not None
        assert config["degenerate_replications"] == 0


def test_the_below_coverage_config_publishes_no_delta(campaign_run: dict[str, Any]) -> None:
    block = campaign_run["payload"]["pairs"]["BTC/USDC"]
    below = [key for key, c in block["configs"].items()
             if c["status"] == rc.STATUS_BELOW_COVERAGE]
    assert len(below) == 1
    config = block["configs"][below[0]]
    assert config["cycles"] == 24
    assert config["delta_dd"] is None and config["LB"] is None and config["se"] is None
    assert config["first_failing_gate"] == eff.REASON_COVERAGE
    assert below[0] in block["J_calc"] and below[0] not in block["J_eligible"]


def test_descriptive_pair_is_carried_without_any_bound(campaign_run: dict[str, Any]) -> None:
    block = campaign_run["payload"]["pairs"]["SOL/USDC"]
    assert block["admissible"] is False and block["warmup_class"] == "W2"
    assert block["benchmark_comparable"] is False
    assert block["n_J_calc"] == 0 and block["J_eligible"] == []
    assert block["q_FWE"] is None and block["not_estimable"] is True
    assert block["reason"] == eff.REASON_NOT_ADMISSIBLE
    assert all(c["status"] == rc.STATUS_DESCRIPTIF for c in block["configs"].values())
    assert all(c["delta_dd"] is None for c in block["configs"].values())
    # descriptive, but the raw metrics stay readable
    assert all(c["cycles"] == 38 for c in block["configs"].values())


def test_coverage_table_is_exported_for_both_pairs(campaign_run: dict[str, Any]) -> None:
    table = campaign_run["payload"]["coverage_table"]
    assert set(table) == {"BTC/USDC", "SOL/USDC"}
    assert len(table["BTC/USDC"]) == 48 and len(table["SOL/USDC"]) == 48
    assert sum(1 for row in table["BTC/USDC"] if row["below"]) == 1


def test_markdown_renders_the_report_line_and_the_mandated_statements(
    campaign_run: dict[str, Any]
) -> None:
    text = campaign_run["paths"]["markdown"].read_text(encoding="utf-8")
    assert "Couverture" in text and "λ_dd" in text and "Δ_dd" in text
    assert eff.RETROSPECTIVE_STATEMENT in text  # § E.3, obligatoire
    assert "largest_gap_candles` 163 / 23" in text  # § D.4 W1 qualifier, with the real gaps
    assert "entrée obligatoire de C3" in text
    assert "Configs perdues au filtre par cellule" in text  # § C.2 per-cell loss count


def test_rerun_is_byte_for_byte_identical(campaign_run: dict[str, Any], tmp_path: Path) -> None:
    paths = dict(campaign_run["paths"])
    paths["output"] = tmp_path / "effect_again.json"
    assert eff.main(_argv(paths)) == 0
    assert paths["output"].read_bytes() == campaign_run["paths"]["output"].read_bytes()


def test_a_campaign_that_did_not_validate_is_refused(tmp_path: Path) -> None:
    paths = _campaign(tmp_path)
    paths["validation"].write_text(
        json.dumps({"ok": False, "exit_code": 2, "failed": ["I-A.3"]}), encoding="utf-8"
    )
    paths["output"] = tmp_path / "refused.json"
    assert eff.main(_argv(paths)) == 2
    assert not paths["output"].exists()


def test_a_missing_input_is_a_usage_error(tmp_path: Path) -> None:
    paths = _campaign(tmp_path)
    paths["coverage"].unlink()
    paths["output"] = tmp_path / "missing.json"
    assert eff.main(_argv(paths)) == 2


def test_an_error_entry_makes_the_run_a_violation(tmp_path: Path) -> None:
    paths = _campaign(tmp_path)
    campaign = json.loads(paths["campaign"].read_text(encoding="utf-8"))
    victim = next(key for key, entry in campaign.items() if entry["pair"] == "BTC/USDC")
    campaign[victim] = {"strategy": rc.STRATEGY, "pair": "BTC/USDC",
                        "params": campaign[victim]["params"],
                        "error": "mp.TimeoutError", "traceback": "..."}
    paths["campaign"].write_text(json.dumps(campaign), encoding="utf-8")
    paths["output"] = tmp_path / "flagged.json"
    assert eff.main(_argv(paths)) == 1
    payload = json.loads(paths["output"].read_text(encoding="utf-8"))
    config = payload["pairs"]["BTC/USDC"]["configs"][victim]
    assert config["status"] == rc.STATUS_NOT_ESTIMABLE
    assert config["cycles"] is None


def test_the_frozen_lambda_fallback_is_recorded_in_the_artefact(tmp_path: Path) -> None:
    paths = _campaign(tmp_path)
    paths["output"] = tmp_path / "frozen.json"
    assert eff.main(_argv(paths, "--reestimation-budget-sec", "0")) == 0
    payload = json.loads(paths["output"].read_text(encoding="utf-8"))
    assert payload["lambda_mode"] == eff.LAMBDA_MODE_FROZEN
    assert payload["lambda_mode_label"] == eff.FROZEN_LABEL
    block = payload["pairs"]["BTC/USDC"]
    assert block["q_FWE"] is not None  # the bound exists, but it is a sensitivity analysis


# ---------------------------------------------------------------------------
# --calibrate
# ---------------------------------------------------------------------------


def test_calibration_writes_the_frozen_keys(tmp_path: Path) -> None:
    source = tmp_path / "P6_grid_rerun.json"
    source.write_text(
        json.dumps({f"{rc.STRATEGY}_BTC_USDC": _entry(values=_config_nav(21, drift=0.0002))}),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(
        json.dumps({"pairs": {"BTC/USDC": _benchmark_block()}}), encoding="utf-8"
    )
    output = tmp_path / "calibration.json"
    code = eff.main([
        "--calibrate",
        "--source", str(source),
        "--benchmark", str(benchmark),
        "--output", str(output),
        "--bootstrap-b", "40",
        "--block-lengths", "10,21,42",
        "--now", "2026-09-19T12:00:00+00:00",
    ])
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pair"] == "BTC/USDC"
    assert payload["mdd_vectorised"]["verified"] is True
    assert payload["mdd_vectorised"]["n_series"] == eff.LAMBDA_COUNT + 2
    assert set(payload["se_delta_single_config"]) == {"10", "21", "42"}
    assert set(payload["se_delta_single_config"]["21"]) == {"dd", "sigma"}
    assert payload["se_delta_single_config"]["21"]["dd"] > 0
    assert payload["reestimation_budget_sec"] == rc.LAMBDA_REESTIMATION_BUDGET_SEC
    assert payload["lambda_mode_planned"] == eff.LAMBDA_MODE_REESTIMATED
    assert set(payload["observed"]) == {
        "cagr_pct", "sigma_daily", "nnz", "lambda_dd", "lambda_sigma", "delta_dd", "delta_sigma"
    }
    assert payload["reference_disclosure"].startswith("Référence divulguée")


def test_calibration_writes_no_extrapolation_of_the_fwe_quantile(tmp_path: Path) -> None:
    """§ F.5 bans 1.645-3.1 x SE, "cannot detect under X" and "G2 is the binding constraint"."""
    source = tmp_path / "P6_grid_rerun.json"
    source.write_text(json.dumps({"k": _entry(values=_config_nav(21, drift=0.0002))}), "utf-8")
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(json.dumps({"pairs": {"BTC/USDC": _benchmark_block()}}), "utf-8")
    output = tmp_path / "calibration.json"
    assert eff.main([
        "--calibrate", "--source", str(source), "--benchmark", str(benchmark),
        "--output", str(output), "--bootstrap-b", "20", "--block-lengths", "10",
        "--now", "2026-09-19T12:00:00+00:00",
    ]) == 0
    text = output.read_text(encoding="utf-8")
    for banned in ("1.645", "3.1 ×", "q_FWE", "FWE", "mordante", "ne peut pas détecter"):
        assert banned not in text


def test_calibration_without_a_buildable_benchmark_is_a_usage_error(tmp_path: Path) -> None:
    source = tmp_path / "P6_grid_rerun.json"
    source.write_text(json.dumps({"k": _entry()}), encoding="utf-8")
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(
        json.dumps({"pairs": {"BTC/USDC": {"buildable": False, "nav": None}}}), encoding="utf-8"
    )
    assert eff.main([
        "--calibrate", "--source", str(source), "--benchmark", str(benchmark),
        "--output", str(tmp_path / "out.json"),
    ]) == 2
