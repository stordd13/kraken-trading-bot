"""C2: strict identity mode of ``scripts/audit/c1_equity_probe.py`` (the master confinement
invariant of the replay chantier) and its negative tests.

The strict mode must see everything ``compare-ab`` ignores by construction: the moving metrics
(Sharpe, PF, MaxDD…), the C1 trade field ``buy_fee_alloc``, the grid ``liquidation`` block, the
fee model and campaign costs. Only the capture metadata (``git_head``, ``engine_file``,
``source_fingerprints``) may differ, and only the C2 blocks may be added.
"""

# ruff: noqa: E402
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "audit"))

import c1_equity_probe as probe


def _capture(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "engine": "BacktestEngine",
        "strategy": "grok_supertrend_4h",
        "pair": "BTC/USDC",
        "exchange": "binance",
        "period": {"start": "2023-04-01T00:00:00+00:00", "end": "2026-04-01T00:00:00+00:00"},
        "interval": 5,
        "capital": "1000",
        "fees": "bybit",
        "pair_costs_file": None,
        "min_order_usdc": 1.0,
        "git_head": "51be3e8",
        "probe_version": 1,
        "engine_file": "/wt/scripts/backtest.py",
        "metrics": {
            "metrics_version": 2,
            "total_trades": 46,
            "net_pnl": 19.314423,
            "sharpe_ratio": 0.454305,
            "profit_factor": 1.383178,
            "max_drawdown_pct_daily": 2.279494,
        },
        "trades": [{"n": 1, "side": "buy", "price": "30000"}],
        "trades_full": [
            {"n": 1, "side": "buy", "price": "30000", "buy_fee_alloc": None},
            {"n": 2, "side": "sell", "price": "31000", "buy_fee_alloc": "0.05"},
        ],
        "equity_curve": [
            ["2023-04-01T04:00:00+00:00", "1000"],
            ["2023-04-01T08:00:00+00:00", "1001"],
        ],
        "balances": {"usdc": "1019.31", "crypto": "0"},
        "metrics_extra": {"max_drawdown": "23.65", "average_win": "4.4", "average_loss": "-1.6"},
        "liquidation": {"inventory_divergence_btc": "0", "net_pnl_lot_basis": "1.52"},
    }
    base.update(overrides)
    return base


def test_strict_identity_holds_and_ignores_only_the_capture_metadata() -> None:
    old = _capture()
    new = _capture(git_head="abc1234", engine_file="/branch/scripts/backtest.py")
    new["source_fingerprints"] = {"backtest": {"path": "x", "sha256": "y"}}
    assert probe.compare_strict(old, new) == []
    # the C2 blocks may be added, nothing else
    new["rejections"] = {"unit": "(order, cause)", "by_cause": {}, "events": {}}
    new["warmup"] = {"4h": {"required": 14, "loaded": 90, "sufficient": True}}
    new["replay_version"] = 2
    assert probe.compare_strict(old, new) == []


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (lambda c: c["metrics"].__setitem__("sharpe_ratio", 0.5), "$.metrics.sharpe_ratio"),
        (lambda c: c["metrics"].__setitem__("profit_factor", None), "$.metrics.profit_factor"),
        (
            lambda c: c["trades_full"][1].__setitem__("buy_fee_alloc", "0.06"),
            "$.trades_full[1].buy_fee_alloc",
        ),
        (
            lambda c: c["liquidation"].__setitem__("net_pnl_lot_basis", "1.53"),
            "$.liquidation.net_pnl_lot_basis",
        ),
        (
            lambda c: c["equity_curve"].append(["2023-04-01T12:00:00+00:00", "1002"]),
            "$.equity_curve",
        ),
        (lambda c: c["balances"].__setitem__("usdc", "1019.32"), "$.balances.usdc"),
        (lambda c: c.__setitem__("fees", "binance"), "$.fees"),
        (lambda c: c.__setitem__("min_order_usdc", 5.0), "$.min_order_usdc"),
        (
            lambda c: c["metrics_extra"].__setitem__("max_drawdown", "23.66"),
            "$.metrics_extra.max_drawdown",
        ),
    ],
)
def test_strict_mode_detects_every_altered_value(mutate, expected_path: str) -> None:
    old = _capture()
    new = copy.deepcopy(old)
    mutate(new)
    violations = probe.compare_strict(old, new)
    assert len(violations) == 1 and violations[0].startswith(expected_path), violations
    # the legacy compare-ab mode is blind to a moving metric: this is why strict mode exists
    if expected_path == "$.metrics.sharpe_ratio":
        assert probe.compare_identity(old, new) == []


def test_strict_mode_refuses_unknown_additions_and_disappeared_keys() -> None:
    old = _capture()
    extra = copy.deepcopy(old)
    extra["surprise"] = 1
    assert probe.compare_strict(old, extra) == [
        "new top-level key 'surprise' is not an allowed addition"
    ]
    missing = copy.deepcopy(old)
    del missing["liquidation"]
    assert probe.compare_strict(old, missing) == [
        "key 'liquidation' disappeared from the new capture"
    ]
    # a metric key removed inside a block is caught too (compare-ab would auto-ignore it)
    dropped = copy.deepcopy(old)
    del dropped["metrics"]["max_drawdown_pct_daily"]
    assert probe.compare_strict(old, dropped) == [
        "$.metrics.max_drawdown_pct_daily: missing on one side"
    ]


def test_compare_ab_strict_cli_exit_codes(tmp_path: Path) -> None:
    old = _capture()
    same = _capture(git_head="other")
    altered = copy.deepcopy(old)
    altered["metrics"]["sharpe_ratio"] = 0.9
    paths = {}
    for name, payload in (("old", old), ("same", same), ("altered", altered)):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = str(p)
    assert probe.main(["compare-ab", paths["old"], paths["same"], "--strict"]) == 0
    assert (
        probe.main(["compare-ab", paths["old"], paths["altered"]]) == 0
    )  # legacy mode: moving key
    assert probe.main(["compare-ab", paths["old"], paths["altered"], "--strict"]) == 1


def test_source_fingerprints_cover_engine_and_strategy_modules(tmp_path: Path) -> None:
    class _Strategy:
        pass

    class _Engine:
        strategy = _Strategy()

    engine_file = tmp_path / "backtest.py"
    engine_file.write_text("x = 1\n", encoding="utf-8")
    fp = probe.source_fingerprints(_Engine(), str(engine_file))
    assert set(fp) == {"backtest", "strategy"}
    assert len(fp["backtest"]["sha256"]) == 64
    assert fp["strategy"]["path"].endswith("test_c1_equity_probe.py")
