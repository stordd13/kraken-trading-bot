"""Rejeu diagnostic grid (§ I-A) — the fifteen campaign-validity assertions.

The campaign artifact is rebuilt synthetically but REALISTICALLY: 96 entries (two pairs x the
48 combos of ``expand_grid(GRID_ATR_GRID)``), the 22 top-level keys, three segments whose
metric dicts are produced by ``krakenbot.backtest_metrics.compute_metrics`` over a real daily
equity grid (1097 / 769 / 330 points), the 18-key liquidation blocks with their Decimals
exported as strings, warmup, rejections and ``effective_params`` in the shape of
``results/c2_replay/P6_grid_rerun.json``.

Order matters, and the negative cases are the point: ``collect_flags`` skips an entry carrying
``"error"`` and ``flag_segment`` returns ``[]`` on an absent ``liquidation`` block, so each of
those two defects is checked to (a) fail at its own assertion, (b) leave I-A.13 NOT evaluated,
and (c) be invisible to ``b4_flags`` — the false green the ordering exists to prevent. A flat
segment (``positions == 0``, null ``spread_pct``) must PASS: that clause is what stops a
legitimate flat segment from killing the run.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

import b4_flags
import p7_grids
import rejeu_common as rc
import rejeu_validate_campaign as rvc
import run_p7_grid_search as p7

from krakenbot.backtest_metrics import EquityPoint, MetricsResult, compute_metrics, daily_grid

NOW = "2026-09-19T12:00:00+00:00"
BEFORE = "2026-09-18T08:00:00+00:00"
PAIR_COSTS: dict[str, dict[str, str]] = {
    "BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"},
    "SOL/USDC": {"spread": "0.0011", "slippage": "0.0002"},
}
LIQUIDATION_PNL = -15.310009211802027  # BTC `all`, measured post-C2 — unrealized_pnl IS this


# ---------------------------------------------------------------------------
# Synthetic but realistic campaign
# ---------------------------------------------------------------------------


def _segment_bounds(segment: str) -> tuple[datetime, datetime]:
    split = rvc.recomputed_split()
    return {
        "all": (rc.WINDOW_START, rc.WINDOW_END),
        "train": (rc.WINDOW_START, split),
        "test": (split, rc.WINDOW_END),
    }[segment]


def _nav_path(n_points: int) -> list[Decimal]:
    """A deterministic NAV path anchored at 1000 with real drawdowns (LCG, no RNG import)."""
    values = [Decimal("1000")]
    state = 7
    for _ in range(1, n_points):
        state = (1103515245 * state + 12345) % 2147483648
        step = Decimal(state % 401 - 195) / Decimal(200000)  # roughly +-0.1 %
        values.append((values[-1] * (Decimal(1) + step)).quantize(Decimal("0.00000001")))
    return values


def _segment_metrics(segment: str) -> MetricsResult:
    start, end = _segment_bounds(segment)
    grid = daily_grid(start, end)
    navs = _nav_path(len(grid))
    points = [EquityPoint(t, v) for t, v in zip(grid[1:], navs[1:], strict=True)]
    return compute_metrics(points, [], start=start, end=end, starting_balance=Decimal("1000"))


def _metrics_dict(result: MetricsResult, *, unrealized: float) -> dict[str, Any]:
    nav_end = result.daily.nav[-1]
    duration = (result.daily.timestamps[-1] - result.daily.timestamps[0]).total_seconds() / 86400
    total, winning, losing = 57, 31, 26
    return {
        "metrics_version": 2,
        "total_trades": total,
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate": winning / total * 100,
        "total_return_pct": float(nav_end / Decimal("1000") - 1) * 100,
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "max_drawdown_pct_daily": result.max_drawdown_pct_daily,
        "max_drawdown_pct_engine": result.max_drawdown_pct_engine,
        "profit_factor": 1.42,
        "calmar_ratio": result.calmar_ratio,
        "net_pnl": float(nav_end - Decimal("1000")),
        "total_fees": 3.02,
        "total_pnl": float(nav_end - Decimal("1000")),
        "unrealized_pnl": unrealized,
        "starting_balance": 1000.0,
        "ending_balance": float(nav_end),
        "duration_days": duration,
        "average_holding_time_minutes": 108008.75,
        "gross_profit_net": 61.0,
        "gross_loss_net": 43.0,
        "pf_excluded_trades": 0,
        "n_daily_returns": result.n_daily_returns,
    }


def _liquidation(pair: str, *, positions: int, pnl: float, net_pnl: float) -> dict[str, Any]:
    costs = PAIR_COSTS[pair]
    block: dict[str, Any] = {
        "buy_fees": "1.4250",
        "sell_fees": "1.599524923912797317873778012",
        "net_pnl_lot_basis": str(net_pnl),
        "residual_net_proceeds": "0",
        "avg_holding_minutes": 108008.75,
        "positions": positions,
        "trades": positions,
        "residual_trade_btc": "0",
        "dust_written_off_btc": "-6E-31",
        "inventory_divergence_btc": "0E-30",
        "pnl": str(pnl),
        "fees": "0.2120049894441051955795797399",
        "gross_usdc": "84.80199577764207823183189597",
    }
    if positions == 0:
        block.update(
            {
                "timestamp": None,
                "reference_price": None,
                "price": None,
                "spread_pct": None,
                "slippage_pct": None,
            }
        )
    else:
        block.update(
            {
                "timestamp": "2026-04-01T00:00:00+00:00",
                "reference_price": "68240.16000000",
                "price": "68212.863936000000",
                "spread_pct": costs["spread"],
                "slippage_pct": costs["slippage"],
            }
        )
    return block


def _warmup(pair: str) -> dict[str, Any]:
    def timeframe(
        interval: int, required: int, loaded: int, gap: int, sufficient: bool, first: str, last: str
    ) -> dict[str, Any]:
        return {
            "interval": interval,
            "required": required,
            "loaded": loaded,
            "extended_by": 0,
            "stale_by_candles": 0,
            "largest_gap_candles": gap,
            "sufficient": sufficient,
            "first": first,
            "last": last,
        }

    gap_1d = 163 if pair == "BTC/USDC" else 40
    return {
        "4h": timeframe(240, 14, 91, 0, True, "2023-03-17T00:00:00+00:00",
                        "2023-04-01T00:00:00+00:00"),
        "1d": timeframe(1440, 50, 88, gap_1d, False, "2022-07-25T00:00:00+00:00",
                        "2023-04-01T00:00:00+00:00"),
        "1w": timeframe(10080, 50, 50, 23, False, "2021-10-18T00:00:00+00:00",
                        "2023-03-27T00:00:00+00:00"),
    }


def _rejections() -> dict[str, Any]:
    zeros = dict.fromkeys(sorted(rvc.REJECTION_CAUSES), 0)
    return {"unit": "(order, cause)", "by_cause": dict(zeros), "events": dict(zeros)}


def _effective_params(pair: str, params: dict[str, Any]) -> dict[str, Any]:
    def cell(value: Any, source: str = "class_default") -> dict[str, Any]:
        return {"value": value, "source": source}

    mode = params["bear_protection_mode"]
    return {
        "strategy_class": "GrokGridATRAdaptiveV4",
        "passed_params": {"pair": pair, **params},
        "params": {
            "grid_levels": cell(12),
            "min_spacing_pct": cell(str(Decimal(str(params["min_spacing_pct"]))), "override"),
            "max_spacing_pct": cell("0.05"),
            "atr_period": cell(14),
            "atr_multiplier": cell(str(Decimal(str(params["atr_multiplier"]))), "override"),
            "recalc_hours": cell(6),
            "bias_1d": cell("0.2"),
            # the class sets the flag from the mode; `source` stays class_default in the export
            "pause_1w_strong_bear": cell(rvc.PAUSE_1W_BY_MODE[mode]),
            "bear_protection_mode": cell(mode, "override"),
            "order_size_usdc": cell("25"),
            "max_allocation_pct": cell("20.0"),
            "pair": cell(pair, "passed"),
        },
    }


def _build_campaign() -> dict[str, Any]:
    per_segment = {segment: _segment_metrics(segment) for segment in rc.SEGMENTS}
    split = rvc.recomputed_split()
    results: dict[str, Any] = {}
    for pair in rc.PAIRS:
        metrics, liquidation, equity, warmup, rejections = {}, {}, {}, {}, {}
        for segment in rc.SEGMENTS:
            result = per_segment[segment]
            net_pnl = float(result.daily.nav[-1] - Decimal("1000"))
            metrics[segment] = _metrics_dict(result, unrealized=LIQUIDATION_PNL)
            liquidation[segment] = _liquidation(
                pair, positions=4, pnl=LIQUIDATION_PNL, net_pnl=net_pnl
            )
            equity[segment] = result.daily.to_dict()
            warmup[segment] = _warmup(pair)
            rejections[segment] = _rejections()
        template: dict[str, Any] = {
            "strategy": rc.STRATEGY,
            "pair": pair,
            "exchange": rc.EXCHANGE,
            "fees": rc.FEES_MODEL,
            "metrics_version": 2,
            "replay_version": 2,
            "pair_costs_file": "config/pair_costs_b4.json",
            "pair_costs": dict(PAIR_COSTS[pair]),
            "min_order_usdc": 5.0,
            "effective_params": None,
            "liquidation": liquidation,
            "equity_daily": equity,
            "rejections": rejections,
            "warmup": warmup,
            "dca_counters": None,
            "params": None,
            "phase": "1",
            "window_idx": None,
            "period": {
                "train_start": rc.WINDOW_START.isoformat(),
                "train_end": split.isoformat(),
                "test_start": split.isoformat(),
                "test_end": rc.WINDOW_END.isoformat(),
            },
            "train": metrics["train"],
            "test": metrics["test"],
            "all": metrics["all"],
        }
        for params in p7_grids.expand_grid(p7_grids.GRID_ATR_GRID):
            entry = dict(template)
            entry["params"] = dict(params)
            entry["effective_params"] = _effective_params(pair, params)
            results[p7.make_key(rc.STRATEGY, pair, params, "1")] = entry
    return results


@pytest.fixture(scope="session")
def campaign_text() -> str:
    """The clean campaign, serialised once: every test parses its own mutable copy."""
    return json.dumps(_build_campaign())


@pytest.fixture
def campaign(campaign_text: str) -> dict[str, Any]:
    return json.loads(campaign_text)


# ---------------------------------------------------------------------------
# Environment / side artifacts / harness
# ---------------------------------------------------------------------------


def _env(**overrides: Any) -> rvc.Environment:
    base: dict[str, Any] = {
        "git_head": "4" * 40,
        "base_sha": rc.BASE_SHA,
        "python": "3.11.9",
        "numpy": "2.4.1",
        "host": "test-host",
        "poetry_lock_sha256": "a" * 64,
        "engine_file_sha256": {"scripts/backtest.py": "b" * 64},
        "code_diff": "",
        "tests_diff": "A\ttests/test_scripts/test_rejeu_validate_campaign.py\n"
        "A\ttests/test_scripts/test_rejeu_effect.py\n",
        "porcelain": "",
    }
    base.update(overrides)
    return rvc.Environment(**base)


def _prespec_stub() -> dict[str, str]:
    return {"path": rvc.PRESPEC_RELPATH, "sha256": "c" * 64}


def _data_coverage(generated_at: str = BEFORE) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "base_sha": rc.BASE_SHA,
        "prespec": _prespec_stub(),
        "exchange": "binance",
        "window": {
            "start": rc.WINDOW_START.isoformat(),
            "end": rc.WINDOW_END.isoformat(),
            "days": rc.WINDOW_DAYS,
        },
        "pairs": {pair: {"admissible": pair == "BTC/USDC"} for pair in rc.PAIRS},
    }


def _benchmark(generated_at: str = BEFORE) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "base_sha": rc.BASE_SHA,
        "prespec": _prespec_stub(),
        "exchange": "binance",
        "fees_model": "bybit",
        "pair_costs_file": "config/pair_costs_b4.json",
        "pair_costs": {pair: dict(PAIR_COSTS[pair]) for pair in rc.PAIRS},
        "capital": "1000",
        "rf": 0,
        "window": {"start": rc.WINDOW_START.isoformat(), "end": rc.WINDOW_END.isoformat()},
        "pairs": {pair: {"buildable": pair == "BTC/USDC"} for pair in rc.PAIRS},
    }


def _write(
    directory: Path,
    results: dict[str, Any],
    *,
    coverage: dict[str, Any] | None = None,
    benchmark: dict[str, Any] | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "P7_phase1_grid.json"
    artifact.write_text(json.dumps(results), encoding="utf-8")
    (directory / "data_coverage.json").write_text(
        json.dumps(coverage if coverage is not None else _data_coverage()), encoding="utf-8"
    )
    (directory / "benchmark.json").write_text(
        json.dumps(benchmark if benchmark is not None else _benchmark()), encoding="utf-8"
    )
    return artifact


def _validate(artifact: Path, env: rvc.Environment | None = None) -> dict[str, Any]:
    ctx = rvc.build_context(artifact, env=env or _env())
    return rvc.build_payload(ctx, rvc.run_assertions(ctx), now=NOW)


def _row(payload: dict[str, Any], identifier: str) -> dict[str, Any]:
    return next(row for row in payload["assertions"] if row["id"] == identifier)


def _first_key(results: dict[str, Any], pair: str = "BTC/USDC") -> str:
    return sorted(key for key, entry in results.items() if entry.get("pair") == pair)[0]


# ---------------------------------------------------------------------------
# 1. The clean campaign passes
# ---------------------------------------------------------------------------


def test_clean_campaign_passes(tmp_path: Path, campaign: dict[str, Any]) -> None:
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == [], payload["failed"]
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert [row["id"] for row in payload["assertions"]] == [a[0] for a in rvc.ASSERTIONS]
    assert len(payload["assertions"]) == 15
    assert all(row["ok"] and not row["skipped"] for row in payload["assertions"])
    # the self-test really ran the admissible cagr cross-check, it was not silently skipped
    assert "SKIPPED on 0" in _row(payload, "I-A.10")["detail"]
    assert payload["control_diff"] == {
        "code_diff_empty": True,
        "tests_diff_only_new": True,
        "worktree_clean": True,
        "detail": payload["control_diff"]["detail"],
    }
    assert payload["environment"]["numpy"] == "2.4.1"
    assert payload["base_sha"] == rc.BASE_SHA


def test_key_set_is_rebuilt_not_hard_coded(campaign: dict[str, Any]) -> None:
    expected = rvc.expected_params_by_key()
    assert len(expected) == rc.N_CONFIGS_TOTAL == 96
    assert set(expected) == set(campaign)
    for key, params in expected.items():
        assert key.rsplit("_", 1)[-1] == p7.params_hash(params)


# ---------------------------------------------------------------------------
# 2. An entry carrying "error" — the first false green
# ---------------------------------------------------------------------------


def test_error_entry_fails_at_ia3_and_is_not_hidden(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    params = dict(campaign[key]["params"])
    campaign[key] = {
        "strategy": rc.STRATEGY,
        "pair": "BTC/USDC",
        "exchange": "binance",
        "fees": "bybit",
        "metrics_version": 2,
        "replay_version": 2,
        "pair_costs_file": "config/pair_costs_b4.json",
        "min_order_usdc": 5.0,
        "params": params,
        "phase": "1",
        "window_idx": None,
        "error": "RuntimeError: replay invariant broken",
        "traceback": "Traceback (most recent call last): ...",
    }
    # the false green this ordering exists to prevent: b4_flags sees nothing
    assert b4_flags.collect_flags(campaign) == []

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.3"]
    assert payload["exit_code"] == 2
    assert key in _row(payload, "I-A.3")["detail"]
    assert "RuntimeError" in _row(payload, "I-A.3")["detail"]
    flags_row = _row(payload, "I-A.13")
    assert flags_row["skipped"] is True and flags_row["ok"] is False
    assert "I-A.3" in flags_row["detail"]


# ---------------------------------------------------------------------------
# 3. A missing liquidation block — the second false green
# ---------------------------------------------------------------------------


def test_missing_liquidation_block_fails_at_ia8_not_silently(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    campaign[key]["liquidation"] = {
        segment: block
        for segment, block in campaign[key]["liquidation"].items()
        if segment != "all"
    }
    assert b4_flags.flag_segment(None, campaign[key]["all"]) == []  # the silent []
    assert b4_flags.collect_flags(campaign) == []

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.8"]
    assert _row(payload, "I-A.5")["ok"] is True
    # I-A.5 records the skipped cost clause instead of hiding it
    assert "without a liquidation block" in _row(payload, "I-A.5")["detail"]
    assert "liquidation" in _row(payload, "I-A.8")["detail"]
    assert _row(payload, "I-A.13")["skipped"] is True


# ---------------------------------------------------------------------------
# 4. A flat segment is legitimate and must NOT kill the run
# ---------------------------------------------------------------------------


def test_absent_liquidation_does_not_mask_a_malformed_warmup(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    """Each block is checked on its own: two defects on the same segment are both reported."""
    key = _first_key(campaign)
    campaign[key]["liquidation"].pop("all")
    campaign[key]["warmup"]["all"]["1w"].pop("largest_gap_candles")

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.8"]
    detail = _row(payload, "I-A.8")["detail"]
    assert "liquidation segments" in detail
    assert f"{key}/all/1w: warmup fields" in detail


def test_flat_segment_with_null_costs_passes(tmp_path: Path, campaign: dict[str, Any]) -> None:
    key = _first_key(campaign)
    entry = campaign[key]
    net_pnl = entry["test"]["ending_balance"] - entry["test"]["starting_balance"]
    entry["test"]["net_pnl"] = net_pnl
    entry["test"]["unrealized_pnl"] = 0.0
    entry["liquidation"]["test"] = _liquidation(
        "BTC/USDC", positions=0, pnl=0.0, net_pnl=net_pnl
    )
    flat = entry["liquidation"]["test"]
    assert flat["positions"] == 0 and flat["trades"] == 0
    assert flat["spread_pct"] is None and flat["slippage_pct"] is None
    assert flat["timestamp"] is None and flat["price"] is None and flat["reference_price"] is None

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == [], payload["failed"]
    assert payload["ok"] is True


def test_flat_segment_with_a_non_null_spread_fails(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    entry = campaign[key]
    net_pnl = entry["test"]["ending_balance"] - entry["test"]["starting_balance"]
    entry["test"]["net_pnl"] = net_pnl
    entry["test"]["unrealized_pnl"] = 0.0
    entry["liquidation"]["test"] = _liquidation("BTC/USDC", positions=0, pnl=0.0, net_pnl=net_pnl)
    entry["liquidation"]["test"]["spread_pct"] = "0.0002"

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.5"]
    assert "must be null on a flat segment" in _row(payload, "I-A.5")["detail"]


# ---------------------------------------------------------------------------
# 5-8. The four defects the brief names explicitly
# ---------------------------------------------------------------------------


def test_unrealized_pnl_zeroed_fails_at_ia11(tmp_path: Path, campaign: dict[str, Any]) -> None:
    key = _first_key(campaign)
    campaign[key]["all"]["unrealized_pnl"] = 0.0
    assert campaign[key]["liquidation"]["all"]["pnl"] == str(LIQUIDATION_PNL)

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.11"]
    detail = _row(payload, "I-A.11")["detail"]
    assert "unrealized_pnl" in detail and "TERMINAL LIQUIDATION" in detail


def test_effective_params_decimal_string_mismatch_fails_at_ia7(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    block = campaign[key]["effective_params"]["params"]
    block["max_spacing_pct"]["value"] = "0.050000001"

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.7"]
    assert "max_spacing_pct" in _row(payload, "I-A.7")["detail"]


def test_effective_params_pause_flag_mismatch_fails_at_ia7(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = next(
        k
        for k, entry in sorted(campaign.items())
        if entry["params"]["bear_protection_mode"] == "none"
    )
    campaign[key]["effective_params"]["params"]["pause_1w_strong_bear"]["value"] = True

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.7"]
    assert "pause_1w_strong_bear" in _row(payload, "I-A.7")["detail"]


def test_effective_params_source_is_never_asserted(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    for entry in campaign.values():
        for cell in entry["effective_params"]["params"].values():
            cell["source"] = "class_default"
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == []


def test_wrong_equity_daily_length_fails_at_ia9(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    campaign[key]["equity_daily"]["all"]["values"] = campaign[key]["equity_daily"]["all"][
        "values"
    ][:-1]

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.9"]
    detail = _row(payload, "I-A.9")["detail"]
    assert "1096 points, expected 1097" in detail and "1096 returns" in detail


def test_non_finite_equity_value_fails_at_ia9(tmp_path: Path, campaign: dict[str, Any]) -> None:
    key = _first_key(campaign)
    campaign[key]["equity_daily"]["train"]["values"][12] = float("inf")
    artifact = _write(tmp_path / "out", campaign)
    assert "Infinity" in artifact.read_text(encoding="utf-8")

    payload = _validate(artifact)
    assert payload["failed"] == ["I-A.9"]
    assert "non-finite" in _row(payload, "I-A.9")["detail"]


def test_sharpe_drift_of_1e_3_fails_the_self_test(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    campaign[key]["all"]["sharpe_ratio"] = campaign[key]["all"]["sharpe_ratio"] + 1e-3

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.10"]
    assert "sharpe_ratio" in _row(payload, "I-A.10")["detail"]


def test_sharpe_set_to_none_fails_the_self_test(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    campaign[key]["all"]["sharpe_ratio"] = None

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.10"]
    assert "None mismatch" in _row(payload, "I-A.10")["detail"]


def test_calmar_none_skips_the_cagr_cross_check_and_records_it(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    campaign[key]["all"]["calmar_ratio"] = None

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == []
    detail = _row(payload, "I-A.10")["detail"]
    assert "SKIPPED on 1" in detail and f"{key}/all" in detail


# ---------------------------------------------------------------------------
# The remaining assertions
# ---------------------------------------------------------------------------


def test_forbidden_selection_file_fails_at_ia1(tmp_path: Path, campaign: dict[str, Any]) -> None:
    artifact = _write(tmp_path / "out", campaign)
    (artifact.parent / "P7_phase1_selection.json").write_text("{}", encoding="utf-8")

    payload = _validate(artifact)
    assert payload["failed"] == ["I-A.1"]
    assert "P7_phase1_selection.json" in _row(payload, "I-A.1")["detail"]


def test_selected_for_paper_in_raw_text_fails_at_ia1(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    campaign["selected_for_paper"] = []
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.1"]
    assert "selected_for_paper" in _row(payload, "I-A.1")["detail"]


def test_missing_artifact_fails_at_ia1(tmp_path: Path) -> None:
    payload = _validate(tmp_path / "absent" / "P7_phase1_grid.json")
    assert payload["failed"] == ["I-A.1"]
    assert "absent" in _row(payload, "I-A.1")["detail"]


def test_truncated_campaign_fails_at_ia2(tmp_path: Path, campaign: dict[str, Any]) -> None:
    campaign.pop(_first_key(campaign))
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.2"]
    detail = _row(payload, "I-A.2")["detail"]
    assert "95 entries" in detail and "expected key(s) absent" in detail


def test_key_suffix_not_matching_params_hash_fails_at_ia2(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    campaign[key]["params"] = {
        "min_spacing_pct": 0.03,
        "atr_multiplier": 3.0,
        "bear_protection_mode": "1d_only",
    }
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.2"]
    assert "params_hash" in _row(payload, "I-A.2")["detail"]


def test_extra_top_level_key_fails_at_ia4(tmp_path: Path, campaign: dict[str, Any]) -> None:
    campaign[_first_key(campaign)]["selection_rank"] = 1
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.4"]
    assert "selection_rank" in _row(payload, "I-A.4")["detail"]


def test_wrong_fee_model_fails_at_ia5(tmp_path: Path, campaign: dict[str, Any]) -> None:
    campaign[_first_key(campaign)]["fees"] = "binance"
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.5"]
    assert "fees" in _row(payload, "I-A.5")["detail"]


def test_pair_costs_not_equal_to_the_file_fails_at_ia5(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    campaign[_first_key(campaign)]["pair_costs"] = {"spread": "0.0009", "slippage": "0.0002"}
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.5"]
    assert "pair_costs.spread" in _row(payload, "I-A.5")["detail"]


def test_pair_costs_decimal_exponent_form_still_passes(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    """The exported Decimals are STRINGS: 2E-4 and 0.0002 are the same number."""
    for key, entry in campaign.items():
        if entry["pair"] == "BTC/USDC":
            entry["pair_costs"] = {"spread": "2E-4", "slippage": "2E-4"}
            for segment in rc.SEGMENTS:
                entry["liquidation"][segment]["spread_pct"] = "2E-4"
                entry["liquidation"][segment]["slippage_pct"] = "2E-4"
            assert key  # keeps the loop explicit
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == []


def test_shifted_split_fails_at_ia6(tmp_path: Path, campaign: dict[str, Any]) -> None:
    entry = campaign[_first_key(campaign)]
    entry["period"]["train_end"] = "2025-05-07T00:00:00+00:00"
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.6"]
    assert "train_end" in _row(payload, "I-A.6")["detail"]
    assert rvc.recomputed_split() == datetime(2025, 5, 7, 4, 48, tzinfo=UTC)


def test_warmup_field_removed_fails_at_ia8(tmp_path: Path, campaign: dict[str, Any]) -> None:
    key = _first_key(campaign)
    campaign[key]["warmup"]["all"]["1w"].pop("extended_by")
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.8"]
    assert "warmup fields" in _row(payload, "I-A.8")["detail"]


def test_warmup_difference_inside_a_pair_is_reported_not_fatal(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    """Section D.4 resolves a warmup difference by the strictest W class: reported, not R0."""
    key = _first_key(campaign)
    campaign[key]["warmup"]["all"]["1d"]["largest_gap_candles"] = 999
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == []
    assert "warmup differs across configs" in _row(payload, "I-A.8")["detail"]
    assert "strictest W class" in _row(payload, "I-A.8")["detail"]


def test_broken_trade_counts_fail_at_ia11(tmp_path: Path, campaign: dict[str, Any]) -> None:
    campaign[_first_key(campaign)]["all"]["winning_trades"] = 30
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.11"]
    assert "winning" in _row(payload, "I-A.11")["detail"]


def test_inventory_divergence_beyond_dust_fails_at_ia12(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    campaign[_first_key(campaign)]["liquidation"]["all"]["inventory_divergence_btc"] = "1E-9"
    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.12"]
    assert "inventory_divergence_btc" in _row(payload, "I-A.12")["detail"]


def test_net_pnl_versus_lot_basis_flagged_at_ia12_before_b4_flags(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    key = _first_key(campaign)
    entry = campaign[key]
    entry["liquidation"]["all"]["net_pnl_lot_basis"] = str(entry["all"]["net_pnl"] + 1.0)
    # b4_flags would catch it too — but only at I-A.13, which must never be the first line
    assert b4_flags.collect_flags(campaign)

    payload = _validate(_write(tmp_path / "out", campaign))
    assert payload["failed"] == ["I-A.12"]
    assert _row(payload, "I-A.13")["skipped"] is True


def test_dirty_worktree_fails_at_ia14(tmp_path: Path, campaign: dict[str, Any]) -> None:
    payload = _validate(
        _write(tmp_path / "out", campaign), env=_env(porcelain=" M scripts/backtest.py\n")
    )
    assert payload["failed"] == ["I-A.14"]
    assert "porcelain" in _row(payload, "I-A.14")["detail"]
    assert payload["control_diff"]["worktree_clean"] is False


def test_code_diff_not_empty_fails_at_ia14(tmp_path: Path, campaign: dict[str, Any]) -> None:
    payload = _validate(
        _write(tmp_path / "out", campaign),
        env=_env(code_diff=" scripts/backtest.py | 4 ++--\n 1 file changed\n"),
    )
    assert payload["failed"] == ["I-A.14"]
    assert payload["control_diff"]["code_diff_empty"] is False


def test_modified_existing_test_fails_at_ia14(tmp_path: Path, campaign: dict[str, Any]) -> None:
    payload = _validate(
        _write(tmp_path / "out", campaign),
        env=_env(tests_diff="M\ttests/test_scripts/test_run_p6_determinism.py\n"),
    )
    assert payload["failed"] == ["I-A.14"]
    assert "outside the closed list" in _row(payload, "I-A.14")["detail"]
    assert payload["control_diff"]["tests_diff_only_new"] is False


def test_new_test_file_listed_as_modified_fails_at_ia14(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    payload = _validate(
        _write(tmp_path / "out", campaign),
        env=_env(tests_diff="M\ttests/test_scripts/test_rejeu_effect.py\n"),
    )
    assert payload["failed"] == ["I-A.14"]
    assert "not a pure addition" in _row(payload, "I-A.14")["detail"]


def test_missing_benchmark_fails_at_ia15(tmp_path: Path, campaign: dict[str, Any]) -> None:
    artifact = _write(tmp_path / "out", campaign)
    (artifact.parent / "benchmark.json").unlink()
    payload = _validate(artifact)
    assert payload["failed"] == ["I-A.15"]
    assert "benchmark.json" in _row(payload, "I-A.15")["detail"]


def test_benchmark_generated_after_the_campaign_fails_at_ia15(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    artifact = _write(
        tmp_path / "out", campaign, benchmark=_benchmark(generated_at="2027-01-01T00:00:00+00:00")
    )
    payload = _validate(artifact)
    assert payload["failed"] == ["I-A.15"]
    assert "AFTER the campaign artifact" in _row(payload, "I-A.15")["detail"]


def test_benchmark_costs_differing_from_the_campaign_fail_at_ia15(
    tmp_path: Path, campaign: dict[str, Any]
) -> None:
    benchmark = _benchmark()
    benchmark["pair_costs"]["SOL/USDC"] = {"spread": "0.0002", "slippage": "0.0002"}
    payload = _validate(_write(tmp_path / "out", campaign, benchmark=benchmark))
    assert payload["failed"] == ["I-A.15"]
    assert "SOL/USDC" in _row(payload, "I-A.15")["detail"]


# ---------------------------------------------------------------------------
# Determinism and the CLI
# ---------------------------------------------------------------------------


def test_same_inputs_give_the_same_bytes(tmp_path: Path, campaign: dict[str, Any]) -> None:
    artifact = _write(tmp_path / "out", campaign)
    first = rc.dumps_canonical(_validate(artifact))
    second = rc.dumps_canonical(_validate(artifact))
    assert first == second


def test_main_writes_the_frozen_schema_and_exits_zero(
    tmp_path: Path, campaign: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rvc, "collect_environment", lambda *a, **k: _env())
    artifact = _write(tmp_path / "out", campaign)
    output = tmp_path / "validation_campaign.json"
    markdown = tmp_path / "validation_campaign.md"
    code = rvc.main(
        [str(artifact), "--output", str(output), "--markdown", str(markdown), "--now", NOW]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(payload) == {
        "generated_at", "base_sha", "prespec", "artifact", "artifact_sha256", "ok", "exit_code",
        "assertions", "failed", "environment", "control_diff",
    }
    assert payload["generated_at"] == NOW
    assert payload["ok"] is True and payload["exit_code"] == 0
    assert set(payload["assertions"][0]) == {"id", "name", "ok", "skipped", "detail"}
    assert set(payload["environment"]) == {
        "git_head", "base_sha", "python", "numpy", "host", "poetry_lock_sha256",
        "engine_file_sha256",
    }
    assert set(payload["control_diff"]) == {
        "code_diff_empty", "tests_diff_only_new", "worktree_clean", "detail"
    }
    assert payload["artifact_sha256"] == rvc._sha256_file(artifact)
    text = markdown.read_text(encoding="utf-8")
    assert "§ I-A" in text and text.count("| I-A.") == 15


def test_main_exits_two_on_a_single_failure(
    tmp_path: Path, campaign: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rvc, "collect_environment", lambda *a, **k: _env())
    campaign[_first_key(campaign)]["all"]["unrealized_pnl"] = 0.0
    artifact = _write(tmp_path / "out", campaign)
    output = tmp_path / "validation_campaign.json"
    assert rvc.main([str(artifact), "--output", str(output), "--now", NOW]) == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is False and payload["exit_code"] == 2 and payload["failed"] == ["I-A.11"]


# ---------------------------------------------------------------------------
# The frozen shapes and the self-test, checked against REAL post-C1/C2 artifacts
# ---------------------------------------------------------------------------

_P6_GRID_RERUN = _project_root / "results" / "c2_replay" / "P6_grid_rerun.json"
_B4_P7 = _project_root / "results" / "B4_P7_phase1_cross_validate.json"


@pytest.mark.skipif(not _P6_GRID_RERUN.exists(), reason="post-C2 grid rerun artifact absent")
def test_frozen_shapes_match_a_real_post_c2_entry() -> None:
    data = json.loads(_P6_GRID_RERUN.read_text(encoding="utf-8"))
    entry = data["grok_grid_atr_adaptive_v4_BTC_USDC"]
    assert set(entry["all"]) == rvc.METRIC_KEYS and len(rvc.METRIC_KEYS) == 24
    assert set(entry["liquidation"]["all"]) == rvc.LIQUIDATION_KEYS
    assert len(rvc.LIQUIDATION_KEYS) == 18
    assert set(entry["warmup"]["all"]) == set(rvc.WARMUP_TIMEFRAMES)
    assert set(entry["warmup"]["all"]["4h"]) == rvc.WARMUP_FIELDS
    assert set(entry["rejections"]["all"]) == rvc.REJECTION_KEYS
    assert set(entry["rejections"]["all"]["by_cause"]) == rvc.REJECTION_CAUSES
    # `unrealized_pnl` carries the terminal liquidation P&L, it is not "approximately zero"
    assert entry["all"]["unrealized_pnl"] == float(entry["liquidation"]["all"]["pnl"])
    assert entry["all"]["unrealized_pnl"] == pytest.approx(-15.310009211802027)
    lengths = {seg: len(entry["equity_daily"][seg]["values"]) for seg in rc.SEGMENTS}
    assert lengths == rc.SEGMENT_POINTS


@pytest.mark.skipif(not _P6_GRID_RERUN.exists(), reason="post-C2 grid rerun artifact absent")
def test_self_test_reproduces_the_real_engine_metrics() -> None:
    """The instrument self-test against the real C1 engine output, not only the synthetic one."""
    data = json.loads(_P6_GRID_RERUN.read_text(encoding="utf-8"))
    checked = 0
    for entry in data.values():
        for segment in rc.SEGMENTS:
            grid, metrics = entry["equity_daily"][segment], entry[segment]
            probe = rvc.self_test_segment(grid["values"], grid["start"], grid["end"])
            assert probe is not None
            assert rvc._compare_optional(metrics["sharpe_ratio"], probe.sharpe) is None
            assert rvc._compare_optional(metrics["sortino_ratio"], probe.sortino) is None
            assert (
                rvc._compare_optional(metrics["max_drawdown_pct_daily"], probe.mdd_daily) is None
            )
            assert metrics["n_daily_returns"] == probe.n_defined
            identity = metrics["calmar_ratio"] * metrics["max_drawdown_pct_daily"]
            assert rvc._compare_optional(identity, probe.cagr) is None
            checked += 1
    assert checked == 9  # 3 pairs x 3 segments


@pytest.mark.skipif(not _B4_P7.exists(), reason="B4 P7 phase-1 artifact absent")
def test_rebuilt_keys_are_the_keys_a_real_runner_wrote() -> None:
    """``make_key`` + ``expand_grid`` reproduce the grid keys of a real P7 phase-1 file."""
    data = json.loads(_B4_P7.read_text(encoding="utf-8"))
    grid_keys = {k for k in data if k.startswith(f"{rc.STRATEGY}_")}
    assert set(rvc.expected_params_by_key()) <= grid_keys
