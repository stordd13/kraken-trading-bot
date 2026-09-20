"""Rejeu diagnostic grid — ``scripts/audit/rejeu_signatures.py`` **and** ``rejeu_common.py``.

The frozen list of new test files (prespec § I-A.14) has no separate file for the shared module,
so its canonicalisation and its numeric helpers are covered here: ``canon`` on the shapes of
zero the artifact really contains (``"0E-30"``, ``"0"``, ``0.0``, ``0``), ``canon_tolerant``,
the determinism of ``sig`` under key reordering, the ``first_difference`` paths, ``dec`` on the
Decimal-valued strings of the ``liquidation`` block, ``cycles_of``, ``daily_returns``,
``cagr_from_returns`` on a known curve, ``nnz`` and ``ols_beta``.

The signature tests prove the four properties section A.1 hangs on: two byte-identical entries
collide, a one-cent difference in a single ``equity_daily`` value splits them on ``sig_exact``,
a ``"0"`` against a ``"0E-30"`` in ``liquidation`` does **not** split them (that is the whole
point of the canonicalisation), and a NaN raises instead of splitting silently.

Defect traps, not the happy path: a failed job (``"error"``), an absent ``liquidation`` block
(the false green ``flag_segment`` produces), a flat segment with ``positions == 0`` and its
``null`` costs, ``sharpe_ratio`` at ``None``, Decimals exported as strings. No database, no
network: every fixture is synthetic and lives in ``tmp_path``.
"""

# ruff: noqa: E402
from __future__ import annotations

import copy
from datetime import datetime
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
from typing import Any

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

import rejeu_common as rc
import rejeu_signatures as rs

B4_FILE = _project_root / "results" / "B4_P7_phase1_cross_validate.json"
NOW = "2026-09-19T12:00:00+00:00"

#: Per-segment shifts, so that no two segments of a fixture carry the same block.
SEGMENT_SHIFT = {"all": 0.0, "train": 0.11, "test": 0.22}
SEGMENT_POSITION_SHIFT = {"all": 0, "train": -1, "test": -2}
SEGMENT_TRIM = {"all": 0, "train": 1, "test": 2}

#: The seven rejection causes of the C2 contract.
CAUSES = (
    "ambiguous_sell_fill",
    "below_min_order",
    "incoherent_sell_fill",
    "insufficient_cash",
    "insufficient_inventory",
    "unmatched_position_id",
    "unmatched_sell_fills",
)


# ---------------------------------------------------------------------------
# Synthetic campaign fixtures (shape verified against results/c2_replay/P6_grid_rerun.json)
# ---------------------------------------------------------------------------


def _metrics(*, net_pnl: float = 45.67, sharpe: float | None = None) -> dict[str, Any]:
    """The 24 keys of METRICS_VERSION 2, with the undefined ratios left at ``None``."""
    return {
        "metrics_version": 2,
        "total_trades": 57,
        "winning_trades": 30,
        "losing_trades": 27,
        "win_rate": 52.63157894736842,
        "total_return_pct": 4.57,
        "sharpe_ratio": sharpe,
        "sortino_ratio": None,
        "max_drawdown_pct_daily": 3.21,
        "max_drawdown_pct_engine": 4.02,
        "profit_factor": None,
        "calmar_ratio": None,
        "net_pnl": net_pnl,
        "total_fees": 3.14,
        "total_pnl": net_pnl,
        "unrealized_pnl": -15.310009211802027,
        "starting_balance": 1000.0,
        "ending_balance": 1000.0 + net_pnl,
        "duration_days": 1096.0,
        "average_holding_time_minutes": 5760.0,
        "gross_profit_net": 80.0,
        "gross_loss_net": 34.33,
        "pf_excluded_trades": 0,
        "n_daily_returns": 1096,
    }


def _liquidation(*, positions: int = 4, divergence: str = "0E-30") -> dict[str, Any]:
    """The 18 keys, Decimals as strings. ``positions == 0`` is the flat segment: nulls."""
    if positions == 0:
        return {
            "buy_fees": "0",
            "sell_fees": "0",
            "net_pnl_lot_basis": "0",
            "residual_net_proceeds": "0",
            "avg_holding_minutes": None,
            "positions": 0,
            "trades": 0,
            "residual_trade_btc": "0",
            "dust_written_off_btc": "0",
            "inventory_divergence_btc": "0",
            "pnl": "0",
            "fees": "0",
            "gross_usdc": "0",
            "timestamp": None,
            "reference_price": None,
            "price": None,
            "spread_pct": None,
            "slippage_pct": None,
        }
    return {
        "buy_fees": "31.2250",
        "sell_fees": "32.33068945797205359577104471",
        "net_pnl_lot_basis": "170.1648702743373715953189638",
        "residual_net_proceeds": "0",
        "avg_holding_minutes": 147708.78787878787,
        "positions": positions,
        "trades": positions,
        "residual_trade_btc": "0",
        "dust_written_off_btc": "-6E-31",
        "inventory_divergence_btc": divergence,
        "pnl": "-15.310009211802027",
        "fees": "1.505323163732906950966591125",
        "gross_usdc": "602.1292654931627803866364500",
        "timestamp": "2026-04-01T00:00:00+00:00",
        "reference_price": "68240.16000000",
        "price": "68212.863936000000",
        "spread_pct": "0.0002",
        "slippage_pct": "0.0002",
    }


def _entry(
    pair: str,
    *,
    values: list[float] | None = None,
    divergence: str = "0E-30",
    net_pnl: float = 45.67,
    positions: int = 4,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    curve = list(values if values is not None else [1000.0, 1001.5, 1002.25, 999.0, 1045.67])
    # Every block differs per segment (as in the real artifact: 1097 / 769 / 330 points), so a
    # segment mix-up inside the payload builder cannot pass unnoticed.
    metrics = {seg: _metrics(net_pnl=net_pnl + SEGMENT_SHIFT[seg]) for seg in rc.SEGMENTS}
    liquidation = {
        seg: _liquidation(
            positions=max(positions + SEGMENT_POSITION_SHIFT[seg], 0), divergence=divergence
        )
        for seg in rc.SEGMENTS
    }
    curves = {seg: curve[: len(curve) - SEGMENT_TRIM[seg]] for seg in rc.SEGMENTS}
    rejections = {
        seg: {
            "unit": "(order, cause)",
            "by_cause": dict.fromkeys(CAUSES, SEGMENT_TRIM[seg]),
            "events": dict.fromkeys(CAUSES, SEGMENT_TRIM[seg]),
        }
        for seg in rc.SEGMENTS
    }
    warmup = {
        tf: {
            "interval": tf,
            "required": 50,
            "loaded": 91,
            "extended_by": 0,
            "stale_by_candles": 0,
            "largest_gap_candles": 0,
            "sufficient": True,
            "first": "2023-01-01T00:00:00+00:00",
            "last": "2023-04-01T00:00:00+00:00",
        }
        for tf in ("4h", "1d", "1w")
    }
    return {
        "strategy": rc.STRATEGY,
        "pair": pair,
        "exchange": "binance",
        "fees": "bybit",
        "metrics_version": 2,
        "replay_version": 2,
        "pair_costs_file": "config/pair_costs_b4.json",
        "pair_costs": {"spread": "0.0002", "slippage": "0.0002"},
        "min_order_usdc": 5.0,
        "effective_params": {
            "strategy_class": "GrokGridATRAdaptiveV4Strategy",
            "passed_params": params or {},
            "params": {"max_spacing_pct": {"value": "0.05", "source": "class_default"}},
        },
        "params": params
        or {"min_spacing_pct": 0.015, "atr_multiplier": 1.5, "bear_protection_mode": "none"},
        "phase": "1",
        "window_idx": None,
        "period": {
            "start": "2023-04-01T00:00:00+00:00",
            "end": "2026-04-01T00:00:00+00:00",
            "split": "2025-05-07T04:48:00+00:00",
        },
        "dca_counters": None,
        "liquidation": liquidation,
        "equity_daily": {
            seg: {"start": "2023-04-01", "end": "2026-04-01", "values": curves[seg]}
            for seg in rc.SEGMENTS
        },
        "rejections": rejections,
        "warmup": {seg: copy.deepcopy(warmup) for seg in rc.SEGMENTS},
        "train": metrics["train"],
        "test": metrics["test"],
        "all": metrics["all"],
    }


def _campaign(**entries: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(entry) for key, entry in entries.items()}


def _write(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# rejeu_common — canonicalisation
# ---------------------------------------------------------------------------


def test_canon_collapses_the_decimal_zeros_but_not_the_float_zero() -> None:
    """``"0E-30"`` and ``"0"`` share one image; ``0.0`` keeps its own.

    Constat on the shared module: ``canon(0)`` is ``"0"`` too, so the int zero and the
    Decimal-valued string ``"0"`` DO collide — the inline comment of prespec A.1 ("0, 0.0 et
    \"0\" ne collisionnent jamais") is true only of the float against the other two. No field
    of the artifact changes type between two runs, so this collision is harmless here.
    """
    assert rc.canon("0E-30") == "0"
    assert rc.canon("0") == "0"
    assert rc.canon(0.0) == "0.0"
    assert rc.canon(0) == "0"
    assert rc.canon(0.0) != rc.canon(0)
    assert rc.canon(0.0) != rc.canon("0")
    assert rc.canon(0) == rc.canon("0")  # constat, cf. the docstring


def test_canon_keeps_the_dust_and_the_nulls_verbatim() -> None:
    assert rc.canon("-6E-31") == "-0.0000000000000000000000000000006"
    assert rc.canon(None) == "null"
    assert rc.canon("bybit") == "bybit"
    assert rc.canon(True) == "True" and rc.canon(1) == "1"
    assert rc.canon(Decimal("0E-30")) == "0"
    assert rc.canon([{"a": "0E-30"}]) == [{"a": "0"}]


def test_canon_tolerant_rounds_floats_and_quantises_decimals() -> None:
    """Ten significant digits on floats, 1e-12 on Decimals.

    Constat: the quantisation of a negative dust value keeps its sign (``"-0"``), so
    ``"-6E-31"`` and ``"0"`` do NOT collide even in the tolerant tier. The exact tier is the
    number of record, so this only under-merges the secondary count.
    """
    assert rc.canon_tolerant(1.0000000000001) == rc.canon_tolerant(1.0)
    assert rc.canon_tolerant(1.000001) != rc.canon_tolerant(1.0)
    assert rc.canon_tolerant("0E-30") == "0"
    assert rc.canon_tolerant("1.0000000000004") == "1"
    assert rc.canon_tolerant("-6E-31") == "-0"  # constat, cf. the docstring
    assert rc.canon_tolerant(None) == "null"


def test_sig_is_invariant_to_key_order_and_reacts_to_values() -> None:
    left = {"b": {"y": [1.0, 2.0], "x": "0E-30"}, "a": 1}
    right = {"a": 1, "b": {"x": "0", "y": [1.0, 2.0]}}
    assert rc.dumps_canonical(rc.canon(left)) == rc.dumps_canonical(rc.canon(right))
    assert rc.sig(left) == rc.sig(right)
    assert rc.sig_tolerant(left) == rc.sig_tolerant(right)
    moved = {"a": 1, "b": {"x": "0.0000001", "y": [1.0, 2.0]}}
    assert rc.sig(moved) != rc.sig(left)


def test_first_difference_paths() -> None:
    assert rc.first_difference({"a": {"b": 1}}, {"a": {"b": 1}}) is None
    assert rc.first_difference({"a": {"b": 1}}, {"a": {"b": 2}}) == "$.a.b"
    assert rc.first_difference({"a": {"b": 1}}, {"a": {}}) == "$.a.b"
    assert rc.first_difference({"a": [1, 2]}, {"a": [1, 3]}) == "$.a[1]"
    assert rc.first_difference([1, 2], [1, 2, 3]) == "$[len]"
    assert rc.first_difference("x", 1) == "$"


# ---------------------------------------------------------------------------
# rejeu_common — numeric helpers
# ---------------------------------------------------------------------------


def test_dec_on_the_decimal_strings_of_the_liquidation_block() -> None:
    assert rc.dec("0E-30") == Decimal("0E-30")
    assert rc.dec("-6E-31") == Decimal("-6E-31")
    assert rc.dec(0.1) == Decimal("0.1")  # via str(), like b4_flags._dec
    assert rc.dec(None) is None
    assert rc.dec("not-a-number") is None
    assert rc.dec([1]) is None


def test_cycles_of_is_total_trades_minus_liquidated_positions() -> None:
    entry = _entry("BTC/USDC", positions=4)
    assert rc.cycles_of(entry, "all") == 57 - 4
    entry["liquidation"] = {}
    assert rc.cycles_of(entry, "all") is None
    assert rc.cycles_of({"all": {}}, "all") is None


def test_daily_returns_from_the_exported_nav() -> None:
    """n NAV points give n-1 returns; a non-positive previous NAV gives NaN, never a fake 0."""
    returns = rc.daily_returns([100.0, 110.0, 99.0])
    assert returns == pytest.approx([0.1, -0.1])
    assert rc.daily_returns([1000.0]) == []
    assert len(rc.daily_returns([1000.0] * 1097)) == 1096
    assert math.isnan(rc.daily_returns([0.0, 10.0])[0])


def test_cagr_from_returns_on_a_known_curve() -> None:
    """A curve compounding to +50 % over exactly one year is 50 %/yr."""
    daily = 1.5 ** (1 / 365) - 1
    assert rc.cagr_from_returns([daily] * 365, days=365.0) == pytest.approx(50.0, abs=1e-9)
    assert rc.cagr_from_returns([0.0] * 1096) == pytest.approx(0.0, abs=1e-12)


def test_nnz_counts_the_days_the_nav_moved() -> None:
    assert rc.nnz([0.0, 1e-13, 0.5, -0.2]) == 2
    assert rc.nnz([]) == 0


def test_ols_beta_is_the_slope_through_the_origin() -> None:
    assert rc.ols_beta([2.0, 4.0, -6.0], [1.0, 2.0, -3.0]) == pytest.approx(2.0)
    assert rc.ols_beta([1.0, 2.0], [0.0, 0.0]) is None


# ---------------------------------------------------------------------------
# rejeu_signatures — the payload of section A.2
# ---------------------------------------------------------------------------


def test_payload_carries_exactly_the_frozen_fields() -> None:
    payload = rs.signature_payload(_entry("BTC/USDC"), "k")
    assert set(payload) == {"metrics", "equity_daily", "liquidation", "rejections"}
    assert set(payload["metrics"]) == set(rc.SEGMENTS)
    assert payload["equity_daily"]["all"] == [1000.0, 1001.5, 1002.25, 999.0, 1045.67]
    assert "timestamp" not in payload["liquidation"]["all"]
    assert "reference_price" not in payload["liquidation"]["all"]
    assert len(payload["liquidation"]["all"]) == 16
    assert set(payload["rejections"]["all"]) == set(CAUSES)
    assert payload["metrics"]["all"]["sharpe_ratio"] is None
    # each segment carries its own block — a mix-up would show here
    assert [len(payload["equity_daily"][seg]) for seg in ("all", "train", "test")] == [5, 4, 3]
    assert payload["liquidation"]["train"]["positions"] == 3
    assert payload["rejections"]["test"]["below_min_order"] == 2
    assert payload["metrics"]["train"] != payload["metrics"]["all"]


def test_two_byte_identical_entries_collide() -> None:
    a = _entry("BTC/USDC", params={"min_spacing_pct": 0.015, "atr_multiplier": 1.5})
    b = _entry("BTC/USDC", params={"min_spacing_pct": 0.030, "atr_multiplier": 3.0})
    assert rs.signatures_of(rs.signature_payload(a, "a")) == rs.signatures_of(
        rs.signature_payload(b, "b")
    )
    block = rs.pair_block({"a": a, "b": b})
    assert block["n_configs"] == 2
    assert block["n_classes_exact"] == 1
    assert block["classes_exact"][0]["members"] == ["a", "b"]
    assert block["first_differences"] == []


def test_a_one_cent_difference_in_one_equity_value_splits_the_class() -> None:
    base = [1000.0, 1001.5, 1002.25, 999.0, 1045.67]
    nudged = list(base)
    nudged[2] += 0.01
    a = _entry("BTC/USDC", values=base)
    b = _entry("BTC/USDC", values=nudged)
    sig_a, _ = rs.signatures_of(rs.signature_payload(a, "a"))
    sig_b, _ = rs.signatures_of(rs.signature_payload(b, "b"))
    assert sig_a != sig_b
    block = rs.pair_block({"a": a, "b": b})
    assert block["n_classes_exact"] == 2
    assert block["first_differences"] == [{"a": "a", "b": "b", "path": "$.equity_daily.all[2]"}]


def test_zero_against_0e30_in_liquidation_does_not_split_the_class() -> None:
    """The whole point of ``canon``: dust noise is not a behavioural difference."""
    a = _entry("BTC/USDC", divergence="0")
    b = _entry("BTC/USDC", divergence="0E-30")
    assert (
        a["liquidation"]["all"]["inventory_divergence_btc"]
        != (b["liquidation"]["all"]["inventory_divergence_btc"])
    )
    exact_a, tol_a = rs.signatures_of(rs.signature_payload(a, "a"))
    exact_b, tol_b = rs.signatures_of(rs.signature_payload(b, "b"))
    assert exact_a == exact_b
    assert tol_a == tol_b
    assert rs.pair_block({"a": a, "b": b})["n_classes_exact"] == 1


def test_the_excluded_fields_never_move_a_signature() -> None:
    reference = rs.signatures_of(rs.signature_payload(_entry("BTC/USDC"), "ref"))
    mutated = _entry("BTC/USDC")
    mutated["params"] = {"min_spacing_pct": 0.03}
    mutated["effective_params"]["params"]["max_spacing_pct"] = {"value": "9", "source": "x"}
    mutated["period"] = {"start": "1970-01-01T00:00:00+00:00"}
    mutated["warmup"]["all"]["4h"]["loaded"] = 0
    mutated["liquidation"]["all"] = dict(mutated["liquidation"]["all"])
    mutated["liquidation"]["all"]["timestamp"] = "1999-01-01T00:00:00+00:00"
    mutated["liquidation"]["all"]["reference_price"] = "1.0"
    assert rs.signatures_of(rs.signature_payload(mutated, "m")) == reference
    # ... but a liquidation field that IS in the payload does move it.
    mutated["liquidation"]["all"]["price"] = "1.0"
    assert rs.signatures_of(rs.signature_payload(mutated, "m")) != reference


def test_a_flat_segment_with_positions_zero_and_null_costs_is_signable() -> None:
    entry = _entry("SOL/USDC", positions=0)
    payload = rs.signature_payload(entry, "flat")
    assert payload["liquidation"]["all"]["spread_pct"] is None
    assert payload["liquidation"]["all"]["trades"] == 0
    exact, tolerant = rs.signatures_of(payload)
    assert len(exact) == 64 and len(tolerant) == 64
    assert "timestamp" not in payload["liquidation"]["all"]  # excluded by A.2
    assert rc.canon(payload["liquidation"]["all"])["price"] == "null"


# ---------------------------------------------------------------------------
# rejeu_signatures — the defect traps
# ---------------------------------------------------------------------------


def test_a_nan_raises_instead_of_splitting_silently() -> None:
    """Section A.1: a NaN or an Inf raises, at BOTH layers — never a silent class split.

    The shared module used to let one through: ``rc.canon`` maps a float to ``repr(float(x))``
    **before** ``json.dumps`` runs, so a NaN arrived as the string ``"nan"`` and
    ``allow_nan=False`` never fired — NaN and Inf then landed in two different classes. The
    guard now lives in ``canon`` / ``canon_tolerant`` themselves (recorded in the pre-spec as a
    pre-launch implementation correction); ``rejeu_signatures.check_finite`` keeps its own,
    earlier and with a JSON path in the message.
    """
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(rc.NonFiniteValueError):
            rc.sig({"v": bad})
        with pytest.raises(rc.NonFiniteValueError):
            rc.sig_tolerant({"v": bad})
    # the Decimal-string road: Decimal("NaN") parses, so it needs the guard too
    for bad_str in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(rc.NonFiniteValueError):
            rc.sig({"v": bad_str})

    entry = _entry("BTC/USDC", values=[1000.0, float("nan"), 1002.0])
    with pytest.raises(rs.PayloadError, match="non-finite"):
        rs.signature_payload(entry, "nan-entry")
    with pytest.raises(rs.PayloadError, match=r"\$\.b\[1\]"):
        rs.check_finite({"a": 1.0, "b": [0.0, float("inf")]})
    with pytest.raises(rs.PayloadError):
        rs.check_finite({"liquidation": {"pnl": "NaN"}})


def test_a_failed_job_raises_instead_of_being_skipped() -> None:
    """``collect_flags`` skips an ``"error"`` entry silently — here it must be loud."""
    entry = {"strategy": rc.STRATEGY, "pair": "BTC/USDC", "error": "boom", "traceback": "..."}
    with pytest.raises(rs.PayloadError, match="failed job"):
        rs.signature_payload(entry, "dead")
    with pytest.raises(rs.PayloadError, match="failed job"):
        rs.b4_payload(entry, "dead")


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("liquidation", "liquidation[train] missing"),
        ("equity_daily", "equity_daily[train] missing"),
        ("rejections", "rejections[train] missing"),
    ],
)
def test_an_absent_block_raises(block: str, expected: str) -> None:
    """The false green: ``flag_segment`` returns ``[]`` on an absent liquidation block."""
    entry = _entry("BTC/USDC")
    del entry[block]
    with pytest.raises(rs.PayloadError, match=expected.replace("[", r"\[").replace("]", r"\]")):
        rs.signature_payload(entry, "k")


def test_a_missing_metric_segment_or_by_cause_raises() -> None:
    entry = _entry("BTC/USDC")
    del entry["test"]
    with pytest.raises(rs.PayloadError, match="metrics segment 'test'"):
        rs.signature_payload(entry, "k")
    entry = _entry("BTC/USDC")
    entry["rejections"] = {seg: {"unit": "(order, cause)"} for seg in rc.SEGMENTS}
    with pytest.raises(rs.PayloadError, match="by_cause"):
        rs.signature_payload(entry, "k")


def test_group_by_pair_keeps_the_frozen_perimeter_and_names_what_it_drops() -> None:
    results = _campaign(
        btc=_entry("BTC/USDC"),
        sol=_entry("SOL/USDC"),
        eth=_entry("ETH/USDC"),
    )
    results["other"] = {"strategy": "grok_supertrend_4h", "pair": "BTC/USDC"}
    results["scalar"] = "not an entry"
    grouped, outside = rs.group_by_pair(results)
    assert sorted(grouped) == ["BTC/USDC", "SOL/USDC"]
    assert list(grouped["BTC/USDC"]) == ["btc"]
    assert outside == ["eth", "other", "scalar"]  # nothing disappears silently


# ---------------------------------------------------------------------------
# rejeu_signatures — classes, first differences, artifact
# ---------------------------------------------------------------------------


def test_classes_are_ordered_and_first_differences_walk_the_neighbours() -> None:
    results = {
        "c_key": _entry("BTC/USDC", net_pnl=3.0),
        "a_key": _entry("BTC/USDC", net_pnl=1.0),
        "b_key": _entry("BTC/USDC", net_pnl=2.0),
    }
    block = rs.pair_block(results)
    assert block["n_classes_exact"] == 3
    assert [klass["members"][0] for klass in block["classes_exact"]] == ["a_key", "b_key", "c_key"]
    assert block["first_differences"] == [
        {"a": "a_key", "b": "b_key", "path": "$.metrics.all.ending_balance"},
        {"a": "b_key", "b": "c_key", "path": "$.metrics.all.ending_balance"},
    ]


def test_build_report_has_the_frozen_schema_and_the_caveat(tmp_path: Path) -> None:
    results = _campaign(btc=_entry("BTC/USDC"), sol=_entry("SOL/USDC"))
    report = rs.build_report(results, now=datetime.fromisoformat(NOW))
    assert set(report) == {
        "generated_at",
        "base_sha",
        "prespec",
        "caveat",
        "fields_included",
        "fields_excluded",
        "pairs",
        "b4_retro",
    }
    assert report["generated_at"] == NOW
    assert report["base_sha"] == rc.BASE_SHA
    assert report["caveat"] == rc.INDISCERNIBILITY_CAVEAT
    assert report["prespec"]["path"] == "docs/rejeu_grid_prespec.md"
    assert sorted(report["pairs"]) == ["BTC/USDC", "SOL/USDC"]
    block = report["pairs"]["BTC/USDC"]
    assert set(block) == {
        "n_configs",
        "n_classes_exact",
        "n_classes_tolerant",
        "classes_exact",
        "classes_tolerant",
        "first_differences",
    }
    assert report["b4_retro"] == {
        "file": None,
        "reference": {"BTC/USDC": 45, "SOL/USDC": 48},
        "pairs": {},
    }
    assert rc.INDISCERNIBILITY_CAVEAT in rs.render_markdown(report)
    assert rc.INDISCERNIBILITY_CAVEAT in rs.render(report)


def test_main_writes_the_artifact_and_prints_the_caveat_verbatim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    campaign = _write(
        tmp_path / "P7_phase1_grid.json",
        _campaign(btc=_entry("BTC/USDC"), sol=_entry("SOL/USDC"), eth=_entry("ETH/USDC")),
    )
    out = tmp_path / "signatures.json"
    md = tmp_path / "signatures.md"
    code = rs.main([str(campaign), "--output", str(out), "--markdown", str(md), "--now", NOW])
    assert code == 0
    printed = capsys.readouterr().out
    assert rc.INDISCERNIBILITY_CAVEAT in printed
    assert "hors périmètre gelé" in printed and "eth" in printed
    assert "fichier non lu" in printed
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["pairs"]["SOL/USDC"]["n_configs"] == 1
    assert "| BTC/USDC | 1 | 1 | 1 |" in md.read_text(encoding="utf-8")


def test_main_is_deterministic_byte_for_byte(tmp_path: Path) -> None:
    campaign = _write(
        tmp_path / "campaign.json",
        _campaign(
            btc=_entry("BTC/USDC"),
            btc2=_entry("BTC/USDC", net_pnl=9.0),
            sol=_entry("SOL/USDC"),
        ),
    )
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    assert rs.main([str(campaign), "--output", str(first), "--now", NOW]) == 0
    assert rs.main([str(campaign), "--output", str(second), "--now", NOW]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_main_returns_2_on_a_broken_input(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    assert rs.main([str(missing), "--output", str(tmp_path / "o.json")]) == 2
    broken = _write(
        tmp_path / "broken.json",
        {"dead": {"strategy": rc.STRATEGY, "pair": "BTC/USDC", "error": "boom"}},
    )
    assert rs.main([str(broken), "--output", str(tmp_path / "o.json")]) == 2
    not_object = _write(tmp_path / "list.json", [1, 2, 3])
    assert rs.main([str(not_object), "--output", str(tmp_path / "o.json")]) == 2
    good = _write(tmp_path / "good.json", _campaign(btc=_entry("BTC/USDC")))
    assert rs.main([str(good), "--output", str(tmp_path / "o.json"), "--now", "not-a-date"]) == 2


# ---------------------------------------------------------------------------
# rejeu_signatures — the retroactive B4 reading (section A.3)
# ---------------------------------------------------------------------------


def _b4_entry(pair: str, *, net_pnl: float) -> dict[str, Any]:
    """The pre-C1/C2 shape: no equity_daily, no rejections, no warmup, no metrics_version."""
    entry = _entry(pair, net_pnl=net_pnl)
    for block in ("equity_daily", "rejections", "warmup", "metrics_version", "replay_version"):
        entry.pop(block, None)
    return entry


def test_b4_payload_ignores_the_blocks_that_file_never_had() -> None:
    payload = rs.b4_payload(_b4_entry("BTC/USDC", net_pnl=1.0), "k")
    assert set(payload) == {"metrics", "liquidation"}
    assert "timestamp" not in payload["liquidation"]["all"]


def test_b4_block_counts_classes_and_records_when_it_was_not_read(tmp_path: Path) -> None:
    results = {
        "btc_a": _b4_entry("BTC/USDC", net_pnl=1.0),
        "btc_b": _b4_entry("BTC/USDC", net_pnl=1.0),
        "btc_c": _b4_entry("BTC/USDC", net_pnl=2.0),
        "sol_a": _b4_entry("SOL/USDC", net_pnl=1.0),
    }
    block = rs.b4_block(results, "results/B4_P7_phase1_cross_validate.json")
    assert block["pairs"]["BTC/USDC"] == {"n_configs": 3, "n_classes_exact": 2}
    assert block["pairs"]["SOL/USDC"] == {"n_configs": 1, "n_classes_exact": 1}
    assert block["reference"] == {"BTC/USDC": 45, "SOL/USDC": 48}
    assert rs.b4_block(None, None)["pairs"] == {}


def test_b4_agreement_is_reported_never_asserted(tmp_path: Path) -> None:
    campaign = _write(tmp_path / "campaign.json", _campaign(btc=_entry("BTC/USDC")))
    b4 = _write(
        tmp_path / "b4.json",
        {
            "btc_a": _b4_entry("BTC/USDC", net_pnl=1.0),
            "sol_a": _b4_entry("SOL/USDC", net_pnl=1.0),
        },
    )
    out = tmp_path / "signatures.json"
    code = rs.main([str(campaign), "--b4", str(b4), "--output", str(out), "--now", NOW])
    assert code == 0, "a disagreement with the pre-registered reference is a constat, not a fail"
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["b4_retro"]["pairs"]["BTC/USDC"]["n_classes_exact"] == 1
    assert rs.b4_agreements(report) == [("BTC/USDC", 1, 45, False), ("SOL/USDC", 1, 48, False)]
    assert "DÉSACCORD" in "\n".join(rs.render(report))


@pytest.mark.skipif(not B4_FILE.exists(), reason="B4 cross-validate artifact absent")
def test_the_real_b4_file_reproduces_the_pre_registered_45_and_48() -> None:
    """Section A.3's pre-registered reference, recomputed from the committed artifact."""
    block = rs.b4_block(rc.read_json(B4_FILE), "results/B4_P7_phase1_cross_validate.json")
    assert block["pairs"]["BTC/USDC"]["n_configs"] == 48
    assert block["pairs"]["SOL/USDC"]["n_configs"] == 48
    assert block["pairs"]["BTC/USDC"]["n_classes_exact"] == 45
    assert block["pairs"]["SOL/USDC"]["n_classes_exact"] == 48
