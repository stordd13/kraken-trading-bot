"""Rejeu diagnostic grid — the reconstructed full-notional benchmark (prespec § E.2 / E.4).

The construction and the comparability tests are pure functions over a list of end-stamped
candles, so the whole § E contract is driven here by synthetic series: a clean 1096-day series
(1097 NAV points anchored at 1000), a series whose first candle arrives 271 days late (the SOL
case: **not** buildable, and re-anchoring is forbidden), series with holes (forward-filled marks
counted), a daily crash below the ``log1p`` domain, non-finite returns, and a window that does not
carry 1096 returns.

The defects the tests are there to trap, not the happy path: a benchmark that silently loses its
terminal liquidation (the grid pays one, § E.2), a NAV that no longer lives on the frozen daily
grid, a non-buildable pair exporting metrics anyway, ``n_daily_returns`` drifting off 1096, a
NaN/Inf slipping into the returns, and a 5 m / 1 d provenance mismatch being counted as "checked".

The one DB-backed test is skipped when the tunnel (127.0.0.1:5433) and the local Postgres are both
unreachable, like ``test_c2_replay_fidelity_db.py``.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import socket
import sys

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

import rejeu_benchmark as rb
import rejeu_common as rc

START = rc.WINDOW_START
END = rc.WINDOW_END
SPREAD = Decimal("0.0002")
SLIPPAGE = Decimal("0.0002")
TAKER = Decimal("0.0025")  # ExchangeFees.from_name("bybit").taker
ANCHOR_CLOSE = Decimal("30000")


def _db_reachable() -> bool:
    for port in (5433, 5432):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            continue
    return False


def _close(index: int) -> Decimal:
    """A deterministic saw-toothed path: it moves every day, both ways, and never crashes."""
    return ANCHOR_CLOSE + Decimal(index % 97) * Decimal("10")


def _series(
    *, start: datetime = START, days: int = rc.WINDOW_DAYS, offset_days: int = 0
) -> list[rb.Candle]:
    """One end-stamped daily candle per grid instant, the anchor candle included."""
    return [
        rb.Candle(start + timedelta(days=offset_days + i), _close(offset_days + i))
        for i in range(days + 1 - offset_days)
    ]


def _report(candles: list[rb.Candle], **kwargs: object) -> rb.PairReport:
    params: dict = {
        "start": START,
        "end": END,
        "spread": SPREAD,
        "slippage": SLIPPAGE,
        "taker": TAKER,
    }
    params.update(kwargs)
    return rb.build_pair_report(candles, **params)


def _qty(entry_close: Decimal, capital: Decimal = rc.CAPITAL) -> Decimal:
    return capital * (Decimal("1") - TAKER) / (entry_close * (Decimal("1") + SPREAD + SLIPPAGE))


# ---------------------------------------------------------------------------
# § E.2 — construction
# ---------------------------------------------------------------------------


def test_clean_series_gives_1097_nav_points_anchored_at_1000() -> None:
    payload = _report(_series()).payload

    assert payload["buildable"] is True
    assert payload["reason"] is None
    assert len(payload["nav"]) == rc.SEGMENT_POINTS["all"] == 1097
    assert payload["nav"][0] == float(rc.CAPITAL) == 1000.0
    assert len(payload["returns"]) == rc.SEGMENT_RETURNS["all"] == 1096
    assert payload["metrics"]["n_daily_returns"] == 1096
    # the entry cost is paid inside the first daily return, not before the anchor
    assert payload["nav"][1] < 1000.0
    assert payload["comparability"]["comparable"] is True
    assert payload["comparability"]["ff_days"] == 0


def test_entry_is_the_anchor_close_moved_by_spread_and_slippage() -> None:
    candles = _series()
    payload = _report(candles).payload

    assert payload["entry_price"] == float(ANCHOR_CLOSE * (Decimal("1") + SPREAD + SLIPPAGE))
    assert payload["exit_price"] == float(
        candles[-1].close * (Decimal("1") - SPREAD - SLIPPAGE)
    )
    assert payload["costs_charged"] == {
        "taker": "0.0025",
        "spread": "0.0002",
        "slippage": "0.0002",
    }


def test_terminal_liquidation_is_one_extra_point_that_lowers_the_last_nav() -> None:
    candles = _series()
    build = rb.build_full_notional(
        candles, start=START, end=END, spread=SPREAD, slippage=SLIPPAGE, taker=TAKER
    )
    round_trip = (Decimal("1") - SPREAD - SLIPPAGE) * (Decimal("1") - TAKER)

    # the liquidation is stamped at end, AFTER the mark carrying the same stamp
    assert build.points[-1].timestamp == END and build.points[-2].timestamp == END
    assert build.points[-2].equity == _qty(ANCHOR_CLOSE) * candles[-1].close
    assert float(build.points[-1].equity) == pytest.approx(
        float(build.points[-2].equity * round_trip), rel=1e-15
    )
    assert build.points[-1].equity < build.points[-2].equity

    nav = _report(candles).payload["nav"]
    # the last point of an instant wins: the exported NAV ends on the liquidation, not the mark
    assert nav[-1] == float(build.points[-1].equity)
    assert nav[-1] < float(build.points[-2].equity)


def test_a_late_first_candle_is_not_buildable_and_exports_no_metrics() -> None:
    payload = _report(_series(offset_days=271)).payload

    assert payload["buildable"] is False
    assert "271.0 days after start" in payload["reason"]
    assert "§ E.2" in payload["reason"]
    assert payload["nav"] is None and payload["returns"] is None and payload["metrics"] is None
    assert payload["entry_price"] is None and payload["exit_price"] is None
    comparability = payload["comparability"]
    assert comparability["comparable"] is False
    assert comparability["candle_at_start"] is False
    # the late candle fills its own bucket: the 270 grid instants before it are forward-filled
    assert comparability["ff_days"] == 270
    # a series that does not exist satisfies none of the return-side tests
    assert comparability["n_daily_returns_ok"] is False
    assert comparability["all_finite"] is False
    assert comparability["min_return_ok"] is False


def test_first_candle_within_24h_is_buildable_but_has_no_candle_at_start() -> None:
    """§ E.2 looks forward (first candle ``> start`` within 24 h), § E.4 looks backward (a candle
    at ``start`` or in the 24 h before). Both are recorded literally: the fallback builds, and it
    is the E.4 test — not the construction — that refuses the pair."""
    payload = _report(_series(offset_days=1)).payload

    assert payload["buildable"] is True
    assert payload["entry_price"] == float(_close(1) * (Decimal("1") + SPREAD + SLIPPAGE))
    assert payload["comparability"]["candle_at_start"] is False
    assert payload["comparability"]["comparable"] is False
    assert "no candle stamped at start" in payload["reason"]


def test_no_candle_at_all_is_not_buildable() -> None:
    payload = _report([]).payload

    assert payload["buildable"] is False
    assert payload["reason"] == "no daily candle stamped at or after start"
    assert payload["comparability"]["ff_days"] == rc.WINDOW_DAYS


# ---------------------------------------------------------------------------
# § E.4 — comparability
# ---------------------------------------------------------------------------


def test_holes_are_counted_as_forward_filled_marks() -> None:
    candles = _series()
    holed = [c for i, c in enumerate(candles) if i not in {10, 11, 500}]

    comparability = _report(holed).payload["comparability"]
    assert comparability["ff_days"] == 3
    assert comparability["ff_ok"] is True
    assert comparability["comparable"] is True  # 3 <= 31, the § D tolerance


def test_a_hole_over_the_tolerance_blocks_comparability() -> None:
    candles = _series()
    holed = [c for i, c in enumerate(candles) if not 100 <= i < 100 + rc.FF_DAYS_MAX + 9]

    payload = _report(holed).payload
    assert payload["comparability"]["ff_days"] == rc.FF_DAYS_MAX + 9 == 40
    assert payload["comparability"]["ff_ok"] is False
    assert payload["comparability"]["comparable"] is False
    assert payload["reason"] == "not comparable: ff_days 40 > 31"
    # the NAV is still built and still 1097 points long: the marks are forward-filled
    assert len(payload["nav"]) == rc.SEGMENT_POINTS["all"]


def test_forward_filled_days_counts_grid_instants_not_missing_candles() -> None:
    grid = [START + timedelta(days=i) for i in range(4)]
    two_in_one_bucket = [
        rb.Candle(START + timedelta(days=1, hours=6), Decimal("1")),
        rb.Candle(START + timedelta(days=1, hours=12), Decimal("2")),
    ]
    assert rb.forward_filled_days(two_in_one_bucket, grid) == 2  # k = 2 and k = 3 are empty
    assert rb.forward_filled_days([], grid) == 3
    full = [rb.Candle(t, Decimal("1")) for t in grid]
    assert rb.forward_filled_days(full, grid) == 0  # the candle at grid[0] fills no bucket


def test_a_daily_crash_below_the_log1p_domain_blocks_comparability() -> None:
    candles = _series()
    crash = int(len(candles) / 2)
    candles[crash] = rb.Candle(candles[crash].timestamp, candles[crash].close * Decimal("0.3"))

    payload = _report(candles).payload
    assert min(payload["returns"]) < rc.MIN_RETURN_DOMAIN
    assert payload["comparability"]["min_return_ok"] is False
    assert payload["comparability"]["all_finite"] is True
    assert payload["comparability"]["comparable"] is False
    assert "log1p domain" in payload["reason"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_returns_are_not_comparable(bad: float) -> None:
    returns = [0.001] * rc.SEGMENT_RETURNS["all"]
    returns[7] = bad

    comparability = rb.comparability_block(_series(), start=START, end=END, returns=returns)
    assert comparability["all_finite"] is False
    assert comparability["comparable"] is False


def test_a_window_without_1096_returns_is_not_comparable() -> None:
    short_end = START + timedelta(days=10)
    candles = _series(days=10)

    report = rb.build_pair_report(
        candles, start=START, end=short_end, spread=SPREAD, slippage=SLIPPAGE, taker=TAKER
    )
    payload = report.payload
    assert payload["buildable"] is True
    assert payload["metrics"]["n_daily_returns"] == 10
    assert payload["comparability"]["n_daily_returns_ok"] is False
    assert payload["comparability"]["comparable"] is False
    assert f"n_daily_returns != {rc.SEGMENT_RETURNS['all']}" in payload["reason"]


def test_missing_candle_at_end_blocks_comparability() -> None:
    payload = _report(_series()[:-1]).payload

    assert payload["comparability"]["candle_at_end"] is False
    assert payload["comparability"]["comparable"] is False
    assert "no candle stamped at end" in payload["reason"]


def test_comparability_without_a_series() -> None:
    comparability = rb.comparability_block(_series(), start=START, end=END, returns=None)

    assert comparability["n_daily_returns_ok"] is False
    assert comparability["all_finite"] is False
    assert comparability["min_return_ok"] is False
    assert comparability["comparable"] is False
    assert sorted(comparability) == sorted(rb.COMPARABILITY_KEYS)


# ---------------------------------------------------------------------------
# § E.4 — provenance cross-check (reported, NOT blocking)
# ---------------------------------------------------------------------------


def test_midnight_crosscheck_counts_mismatches_and_skips_missing_stamps() -> None:
    midnights = [START + timedelta(days=i) for i in range(1, 5)]
    daily = {t: Decimal("100") for t in midnights}
    five_min = {midnights[0]: Decimal("100.0"), midnights[1]: Decimal("101")}  # third/fourth absent

    mismatches, checked, stamps = rb.midnight_crosscheck(daily, five_min, midnights)
    assert (mismatches, checked) == (1, 2)  # "100.0" == Decimal("100"), 101 differs
    assert stamps == [midnights[1]]


def test_the_crosscheck_never_blocks_comparability() -> None:
    candles = _series()
    five_min = {c.timestamp: c.close * Decimal("2") for c in candles}  # every midnight mismatches

    payload = _report(candles, five_min_closes=five_min).payload
    comparability = payload["comparability"]
    assert comparability["midnight_crosscheck_checked"] == rc.SEGMENT_POINTS["all"] - 2 == 1095
    assert comparability["midnight_crosscheck_mismatches"] == 1095
    assert comparability["comparable"] is True
    assert payload["reason"] is None


# ---------------------------------------------------------------------------
# Historical descriptors (§ E.1) — descriptive, never a threshold
# ---------------------------------------------------------------------------


def test_historical_descriptors_are_copied_verbatim(tmp_path: Path) -> None:
    path = tmp_path / "C1_benchmarks_v2.json"
    path.write_text(
        json.dumps(
            {
                "buy_and_hold": {
                    "BTC/USDC": {
                        "sharpe_ratio": 0.847,
                        "max_drawdown_pct_daily": 49.65,
                        "total_return_pct": 137.51,
                        "n_daily_returns": 1096,
                        "entry_price": 28038.941092,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    descriptors = rb.historical_descriptors(path, "BTC/USDC")
    assert descriptors is not None
    assert descriptors["sharpe_ratio"] == 0.847
    assert descriptors["total_return_pct"] == 137.51
    assert descriptors["n_daily_returns"] == 1096
    assert "entry_price" not in descriptors  # only the four frozen descriptors travel
    assert rb.historical_descriptors(path, "ETH/USDC") is None
    assert rb.historical_descriptors(tmp_path / "absent.json", "BTC/USDC") is None


def test_unreadable_historical_file_is_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    assert rb.historical_descriptors(path, "BTC/USDC") is None


# ---------------------------------------------------------------------------
# Artefact (frozen schema, determinism, self-checks)
# ---------------------------------------------------------------------------


def _payload(now: datetime = datetime(2026, 9, 19, tzinfo=UTC)) -> dict:
    reports = {
        "BTC/USDC": _report(_series()),
        "SOL/USDC": _report(_series(offset_days=271)),
    }
    costs = {
        "BTC/USDC": rb.PairCosts(spread=SPREAD, slippage=SLIPPAGE),
        "SOL/USDC": rb.PairCosts(spread=Decimal("0.0011"), slippage=SLIPPAGE),
    }
    return rb.build_payload(
        reports,
        now=now,
        pair_costs_file=rc.PROJECT_ROOT / "config" / rc.PAIR_COSTS_BASENAME,
        pair_costs=costs,
    )


def test_payload_follows_the_frozen_schema() -> None:
    payload = _payload()

    assert sorted(payload) == sorted(
        [
            "generated_at",
            "base_sha",
            "prespec",
            "exchange",
            "fees_model",
            "pair_costs_file",
            "pair_costs",
            "capital",
            "rf",
            "window",
            "pairs",
        ]
    )
    assert payload["exchange"] == rc.EXCHANGE == "binance"
    assert payload["fees_model"] == rc.FEES_MODEL == "bybit"
    assert payload["capital"] == "1000" and payload["rf"] == 0
    assert payload["pair_costs_file"] == "config/pair_costs_b4.json"
    assert payload["pair_costs"]["SOL/USDC"] == {"spread": "0.0011", "slippage": "0.0002"}
    assert payload["window"] == {"start": START.isoformat(), "end": END.isoformat()}
    assert payload["base_sha"] == rc.BASE_SHA
    assert payload["prespec"]["path"] == "docs/rejeu_grid_prespec.md"
    assert len(payload["prespec"]["sha256"]) == 64
    assert list(payload["pairs"]) == list(rc.PAIRS)
    for block in payload["pairs"].values():
        assert sorted(block) == sorted(rb.PAIR_KEYS)
        assert sorted(block["comparability"]) == sorted(rb.COMPARABILITY_KEYS)
        if block["metrics"] is not None:
            assert sorted(block["metrics"]) == sorted(rb.METRIC_KEYS)


def test_the_artefact_is_deterministic(tmp_path: Path) -> None:
    now = datetime(2026, 9, 19, 12, 30, tzinfo=UTC)
    first = rc.write_json(tmp_path / "a.json", _payload(now))
    second = rc.write_json(tmp_path / "b.json", _payload(now))

    assert first == second
    assert (tmp_path / "a.json").read_text(encoding="utf-8") == (
        tmp_path / "b.json"
    ).read_text(encoding="utf-8")
    # allow_nan=False: a NaN in the exported NAV would raise instead of travelling silently
    rc.dumps_canonical(rc.read_json(tmp_path / "a.json"))


def test_structural_violations_only_fire_on_the_instrument() -> None:
    payload = _payload()
    assert rb.structural_violations(payload) == []  # SOL not buildable is a RESULT, not a defect

    short = _payload()
    short["pairs"]["BTC/USDC"]["nav"] = short["pairs"]["BTC/USDC"]["nav"][:-1]
    assert "nav has 1096 points" in rb.structural_violations(short)[0]

    unanchored = _payload()
    unanchored["pairs"]["BTC/USDC"]["nav"][0] = 999.0
    assert "the anchor is 1000.0" in rb.structural_violations(unanchored)[0]


def test_markdown_renders_both_pairs_and_the_mismatch_list() -> None:
    candles = _series()
    five_min = {candles[10].timestamp: candles[10].close * Decimal("2")}
    reports = {
        "BTC/USDC": _report(candles, five_min_closes=five_min),
        "SOL/USDC": _report(_series(offset_days=271)),
    }
    payload = rb.build_payload(
        reports,
        now=datetime(2026, 9, 19, tzinfo=UTC),
        pair_costs_file=rc.PROJECT_ROOT / "config" / rc.PAIR_COSTS_BASENAME,
        pair_costs={
            "BTC/USDC": rb.PairCosts(spread=SPREAD, slippage=SLIPPAGE),
            "SOL/USDC": rb.PairCosts(spread=Decimal("0.0011"), slippage=SLIPPAGE),
        },
    )
    markdown = rb.render_markdown(payload, reports)

    assert "| BTC/USDC |" in markdown and "| SOL/USDC |" in markdown
    assert "271.0 days after start" in markdown
    assert candles[10].timestamp.isoformat() in markdown
    assert "\n".join(rb.render_lines(payload)).startswith("benchmark binance / fees bybit")


def test_a_malformed_now_is_a_usage_error() -> None:
    assert rb.main(["--now", "not-a-stamp"]) == 2


# ---------------------------------------------------------------------------
# DB-backed (skipped when neither the tunnel nor a local Postgres answers)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _db_reachable(), reason="Database not reachable")
async def test_btc_daily_series_under_the_engine_bounds_db() -> None:
    from dotenv import load_dotenv

    load_dotenv(_project_root / ".env")
    from krakenbot.config.settings import ExchangeFees, Settings
    from krakenbot.core.database import DatabaseManager

    db_manager = DatabaseManager()
    await db_manager.init_db(Settings())
    try:
        candles = await rb.load_daily_candles(db_manager, "BTC/USDC", start=START, end=END)
        five_min = await rb.load_closes_at(
            db_manager, "BTC/USDC", rb.FIVE_MIN_INTERVAL, rb.interior_midnights(START, END)[:30]
        )
    finally:
        await db_manager.close_db()

    # ``>= start`` keeps the anchor candle, ``<= end`` the terminal one (debt 15(c) repaired)
    assert candles[0].timestamp == START and candles[-1].timestamp == END
    assert len(candles) == rc.SEGMENT_POINTS["all"]

    payload = rb.build_pair_report(
        candles,
        start=START,
        end=END,
        spread=SPREAD,
        slippage=SLIPPAGE,
        taker=ExchangeFees.from_name(rc.FEES_MODEL).taker,
        five_min_closes=five_min,
    ).payload
    assert payload["buildable"] is True
    assert payload["comparability"]["ff_days"] == 0
    assert payload["comparability"]["comparable"] is True
    assert len(payload["nav"]) == rc.SEGMENT_POINTS["all"]
    assert payload["metrics"]["n_daily_returns"] == rc.SEGMENT_RETURNS["all"]
    # end-stamping (B4.1): the 5 m close of J 00:00 is the 1 d close of J 00:00
    assert payload["comparability"]["midnight_crosscheck_checked"] == 30
    assert payload["comparability"]["midnight_crosscheck_mismatches"] == 0
