"""Tests of ``scripts/audit/reconstruct_1w.py`` — the pure layer (step 1), adverse first.

Every function under test is pure (no DB, no network, no clock): the cases are synthetic candles and stamp lists.
Each test was written with its adverse case and observed **red** against a skeleton that does not implement the
module (agent rule 1, ``CLAUDE.md``); targeted mutants of the implementation were then observed red on the tests
that pin one specific defect (off-by-one, order dependence, NULL propagation, row count).

Expected values are derived from the texts, never from the implementation (agent rule 3):

* brief ``agent/agent_reconstruction_1w.md`` § 2 — the method: for the week stamped ``S`` (Monday 00:00, period
  end), the 7 daily rows stamped ``S − 6 d … S`` (« end-stamped : le row stampé mardi 00:00 est le lundi ») ;
  ``open`` of the first day, ``close`` of the last, ``high`` max, ``low`` min, ``volume`` Σ, ``trades_count`` Σ if
  the 7 are non NULL (else NULL) ; exactly 7 rows, otherwise the week is **non reconstructible** ;
* brief § 1 — the 8 missing stamps, identical on the three pairs ;
* brief § 3.1 — ``source_sha256`` : sha of the 7 serialised daily rows, fixed order (independent of input order) ;
* protocol ``docs/protocole_c3.md`` v2.1 § A.8 — « Sur les 194 périodes hebdomadaires de ``(2021-03-01, T]``,
  **188 sont présentes, soit 96,9 %, sous les 97 % de D1** … le trou maximal, 7 jours » ; RESEARCH_LOG
  « Adoption » — ``T = 2024-11-22T04:48:00Z`` ;
* ``scripts/binance_vision_import.py:176-177`` — the Vision monthly URL scheme ; ``:136-141`` — ms / µs open time,
  stored stamp = open time + interval.

The D1 reading is pinned to the chain's own rule (``c3_select.d1_for_pair``) on a synthetic four-series coverage
whose three other series are complete — a conforming healthy witness (agent rule 2).
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

import c3_common as cc
import c3_select
import reconstruct_1w as r1w

D = Decimal
DAY = timedelta(days=1)
WEEK = timedelta(days=7)
#: A missing stamp of the brief (§ 1), a Monday 00:00 UTC.
S = datetime(2022, 6, 6, tzinfo=UTC)

#: Brief § 1, copied verbatim — the reference the constant is pinned to.
BRIEF_MISSING_TEXT = (
    "2022-06-06  2022-07-04  2022-09-05  2022-10-03  2022-11-07  2022-12-05  2025-02-03  2025-03-03"
)
BRIEF_MISSING = tuple(
    datetime.fromisoformat(token).replace(tzinfo=UTC) for token in BRIEF_MISSING_TEXT.split()
)
#: Protocol v2.1 § A.3 / § A.8 — window of the first campaign, and its declared anchor.
PROTOCOL_START = datetime(2021, 3, 1, tzinfo=UTC)
PROTOCOL_END = datetime(2026, 6, 29, tzinfo=UTC)
PROTOCOL_T = datetime(2024, 11, 22, 4, 48, tzinfo=UTC)

#: Seven daily rows for the week ``S`` — (stamp offset from S in days, open, high, low, close, volume, trades).
#: The max high (130.5) is on the third day, the min low (88.25) on the fourth, so neither is a border value.
_DAYS = (
    (-6, "100.00000000", "105.00000000", "99.00000000", "104.00000000", "1.50000000", 10),
    (-5, "104.00000000", "110.00000000", "103.00000000", "108.00000000", "2.25000000", 20),
    (-4, "108.00000000", "130.50000000", "107.00000000", "125.00000000", "3.00000000", 30),
    (-3, "125.00000000", "126.00000000", "88.25000000", "90.00000000", "4.00000001", 40),
    (-2, "90.00000000", "95.00000000", "89.00000000", "94.00000000", "0.50000000", 50),
    (-1, "94.00000000", "97.00000000", "93.00000000", "96.00000000", "1.00000000", 60),
    (0, "96.00000000", "99.00000000", "95.00000000", "98.75000000", "0.75000000", 70),
)


def _candle(
    stamp: datetime,
    o: str,
    h: str,
    lo: str,
    c: str,
    v: str,
    trades: int | None = 1,
    vwap: str | None = None,
) -> r1w.Candle:
    return r1w.Candle(
        timestamp=stamp,
        open=D(o),
        high=D(h),
        low=D(lo),
        close=D(c),
        volume=D(v),
        trades_count=trades,
        vwap=None if vwap is None else D(vwap),
    )


def _week_rows(week: datetime = S) -> list[r1w.Candle]:
    return [_candle(week + k * DAY, o, h, lo, c, v, t) for k, o, h, lo, c, v, t in _DAYS]


# ---------------------------------------------------------------------------
# Constants pinned to the texts (agent rule 3: the text is the reference, the code is pinned to it)
# ---------------------------------------------------------------------------


def test_expected_missing_is_the_brief_list() -> None:
    assert r1w.EXPECTED_MISSING == BRIEF_MISSING
    assert all(s.weekday() == 0 and s.time() == datetime.min.time() for s in BRIEF_MISSING)


def test_window_and_anchor_are_the_protocol_values() -> None:
    assert (r1w.WINDOW_START, r1w.WINDOW_END) == (PROTOCOL_START, PROTOCOL_END)
    assert r1w.ANCHOR_DECLARED == PROTOCOL_T
    # The anchor is recomputed by the chain's function, never read: 70 % of 1946 days = 1362.2 d.
    assert cc.anchor_of(r1w.WINDOW_START, r1w.WINDOW_END) == PROTOCOL_T


def test_grid_helpers_are_reused_by_identity() -> None:
    assert r1w.WEEK_MINUTES is cc.WEEK_MINUTES
    assert r1w.EXCHANGE == "binance"
    assert r1w.PAIRS == ("BTC/USDT", "ETH/USDT", "SOL/USDT")
    assert r1w.SOURCE_INTERVAL == 1440
    assert r1w.METHOD == "agg_1d_v1"


# ---------------------------------------------------------------------------
# Source stamps — the end-stamped off-by-one
# ---------------------------------------------------------------------------


def test_source_stamps_are_s_minus_6_days_to_s() -> None:
    """Brief § 2 : stamps ``S − 6 j … S`` ; the row stamped Tuesday 00:00 is Monday's candle."""
    expected = tuple(
        datetime(2022, m, d, tzinfo=UTC)
        for m, d in ((5, 31), (6, 1), (6, 2), (6, 3), (6, 4), (6, 5), (6, 6))
    )
    got = r1w.source_stamps(S)
    assert got == expected
    assert got[0].weekday() == 1  # Tuesday 00:00 = end of the week's Monday
    assert S - WEEK not in got  # the previous Monday stamp closes the *previous* week's Sunday


@pytest.mark.parametrize(
    "stamp",
    [
        datetime(2022, 6, 7, tzinfo=UTC),  # a Tuesday
        datetime(2022, 6, 6, 1, 0, tzinfo=UTC),  # Monday, not 00:00
    ],
)
def test_source_stamps_refuse_a_non_week_stamp(stamp: datetime) -> None:
    with pytest.raises(r1w.NotReconstructibleError):
        r1w.source_stamps(stamp)


def test_source_stamps_refuse_a_naive_datetime() -> None:
    with pytest.raises(ValueError):
        r1w.source_stamps(datetime(2022, 6, 6))


# ---------------------------------------------------------------------------
# Aggregation — method agg_1d_v1
# ---------------------------------------------------------------------------


def test_aggregate_week_ohlcv_and_trades() -> None:
    rebuilt = r1w.aggregate_week(S, _week_rows())
    assert rebuilt.timestamp == S
    assert rebuilt.open == D("100")  # first day (stamp S − 6 d)
    assert rebuilt.close == D("98.75")  # last day (stamp S)
    assert rebuilt.high == D("130.5")
    assert rebuilt.low == D("88.25")
    # 1.5 + 2.25 + 3 + 4.00000001 + 0.5 + 1 + 0.75
    assert rebuilt.volume == D("13.00000001")
    assert rebuilt.trades_count == 280  # 10 + 20 + … + 70
    assert rebuilt.vwap is None  # default policy "null"


def test_aggregate_week_ignores_input_order() -> None:
    """``open`` is the open of the first *stamp*, not of the first row handed in."""
    rows = list(reversed(_week_rows()))
    rebuilt = r1w.aggregate_week(S, rows)
    assert (rebuilt.open, rebuilt.close) == (D("100"), D("98.75"))


def test_trades_count_null_propagates() -> None:
    rows = _week_rows()
    rows[4] = _candle(S - 2 * DAY, "90", "95", "89", "94", "0.5", None)
    assert r1w.aggregate_week(S, rows).trades_count is None


def test_vwap_policies() -> None:
    """Brief § 2 (c) : weighted = Σ(vwap_d·vol_d)/Σvol_d. Six days at vwap 10 vol 1, the last at vwap 20 vol 4 :
    (60 + 80) / 10 = 14."""
    rows = [
        _candle(
            stamp, "1", "1", "1", "1", "4" if stamp == S else "1", 1, "20" if stamp == S else "10"
        )
        for stamp in (S - k * DAY for k in range(7))
    ]
    assert r1w.aggregate_week(S, rows, vwap_policy="null").vwap is None
    assert r1w.aggregate_week(S, rows, vwap_policy="weighted").vwap == D("14")
    rows[2] = _candle(rows[2].timestamp, "1", "1", "1", "1", "1", 1, None)
    assert r1w.aggregate_week(S, rows, vwap_policy="weighted").vwap is None
    with pytest.raises(ValueError):
        r1w.aggregate_week(S, rows, vwap_policy="mean")


def _drop(rows: list[r1w.Candle], index: int) -> list[r1w.Candle]:
    return rows[:index] + rows[index + 1 :]


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param(_drop(_week_rows(), 3), id="six-rows"),
        pytest.param(_week_rows() + [_candle(S + DAY, "1", "1", "1", "1", "1")], id="eight-rows"),
        pytest.param(_drop(_week_rows(), 3) + [_week_rows()[2]], id="duplicate-stamp"),
        pytest.param(
            _drop(_week_rows(), 3)
            + [_candle(S - 3 * DAY + timedelta(hours=1), "1", "1", "1", "1", "1")],
            id="off-grid-stamp",
        ),
        pytest.param(
            _drop(_week_rows(), 6) + [_candle(S - WEEK, "1", "1", "1", "1", "1")],
            id="previous-monday-instead-of-s",
        ),
    ],
)
def test_aggregate_week_refuses_anything_but_the_seven_grid_rows(rows: list[r1w.Candle]) -> None:
    with pytest.raises(r1w.NotReconstructibleError):
        r1w.aggregate_week(S, rows)


def test_aggregate_week_refuses_a_null_price() -> None:
    rows = _week_rows()
    rows[4] = r1w.Candle(S - 2 * DAY, D("90"), D("95"), None, D("94"), D("0.5"), 50)
    with pytest.raises(r1w.NotReconstructibleError):
        r1w.aggregate_week(S, rows)


def test_aggregate_week_refuses_a_non_week_stamp() -> None:
    with pytest.raises(r1w.NotReconstructibleError):
        r1w.aggregate_week(S + DAY, _week_rows())


def test_candle_refuses_float_and_naive_stamp() -> None:
    with pytest.raises(TypeError):
        r1w.Candle(S, 100.0, D("1"), D("1"), D("1"), D("1"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        r1w.Candle(datetime(2022, 6, 6), D("1"), D("1"), D("1"), D("1"), D("1"))


# ---------------------------------------------------------------------------
# source_sha256 — replayable proof
# ---------------------------------------------------------------------------


def test_source_sha256_is_stable_and_order_independent() -> None:
    rows = _week_rows()
    digest = r1w.source_sha256("BTC/USDT", rows)
    assert len(digest) == 64 and int(digest, 16) >= 0
    assert r1w.source_sha256("BTC/USDT", list(rows)) == digest
    assert r1w.source_sha256("BTC/USDT", list(reversed(rows))) == digest
    assert r1w.source_sha256("BTC/USDT", rows[3:] + rows[:3]) == digest


def test_source_sha256_changes_with_a_value_or_the_pair() -> None:
    rows = _week_rows()
    digest = r1w.source_sha256("BTC/USDT", rows)
    altered = list(rows)
    altered[3] = _candle(S - 3 * DAY, "125", "126", "88.25", "90.00000001", "4.00000001", 40)
    assert r1w.source_sha256("BTC/USDT", altered) != digest
    assert r1w.source_sha256("ETH/USDT", rows) != digest


# ---------------------------------------------------------------------------
# Comparison — control (c)
# ---------------------------------------------------------------------------


def test_compare_week_identical_is_empty() -> None:
    rebuilt = r1w.aggregate_week(S, _week_rows())
    assert r1w.compare_week(rebuilt, rebuilt) == []


def test_compare_week_reports_each_column_by_kind() -> None:
    rebuilt = r1w.aggregate_week(S, _week_rows())
    stored = r1w.Candle(S, D("100"), D("130.5"), D("88.25"), D("98.76"), D("13.00000001"), 281)
    mismatches = r1w.compare_week(stored, rebuilt)
    assert [(m.column, m.kind) for m in mismatches] == [
        ("close", "ohlcv"),
        ("trades_count", "trades_count"),
    ]
    close = mismatches[0]
    assert (close.stamp, close.vision, close.rebuilt) == (S, "98.76", "98.75000000")


# ---------------------------------------------------------------------------
# Weekly grid, missing stamps, D1
# ---------------------------------------------------------------------------


def test_expected_week_stamps_on_the_campaign_window() -> None:
    """2021-03-01 → 2026-06-29 = 1946 days = 278 weeks : 278 Monday stamps in ``(start, end]`` (brief § 2 (c) :
    « ≈ 270 par paire » present = 278 − 8)."""
    grid = r1w.expected_week_stamps(PROTOCOL_START, PROTOCOL_END)
    assert len(grid) == 278
    assert grid[0] == datetime(2021, 3, 8, tzinfo=UTC) and grid[-1] == PROTOCOL_END
    assert all(s.weekday() == 0 and s.time() == datetime.min.time() for s in grid)
    assert len(grid) == cc.weekly_stamps_in(PROTOCOL_START, PROTOCOL_END)


def test_missing_week_stamps_splits_missing_and_off_grid() -> None:
    start, end = datetime(2022, 5, 1, tzinfo=UTC), datetime(2022, 7, 31, tzinfo=UTC)
    grid = [datetime(2022, 5, 2, tzinfo=UTC) + k * WEEK for k in range(13)]
    present = [s for s in grid if s != S] + [
        datetime(2022, 6, 14, tzinfo=UTC),  # a Tuesday: off grid
        datetime(2022, 4, 25, tzinfo=UTC),  # before the window: ignored
    ]
    missing, off_grid = r1w.missing_week_stamps(present, start, end)
    assert missing == [S]
    assert off_grid == [datetime(2022, 6, 14, tzinfo=UTC)]


def _present_without(stamps: tuple[datetime, ...]) -> list[datetime]:
    return [s for s in r1w.expected_week_stamps(PROTOCOL_START, PROTOCOL_END) if s not in stamps]


def test_d1_week_reproduces_the_protocol_figure() -> None:
    """Protocol § A.8 v2.1 : 188/194 = 96,9 % < 97 %, longest gap 7 days → D1 fails."""
    d1 = r1w.d1_week(_present_without(BRIEF_MISSING), start=PROTOCOL_START, end=PROTOCOL_T)
    assert (d1["covered_units"], d1["expected_units"]) == (188, 194)
    assert d1["ratio"] == 188 / 194
    assert d1["longest_gap_days"] == 7.0
    assert d1["ok"] is False


def test_d1_week_after_reconstruction_is_194_of_194() -> None:
    """Brief § 3.2 : after the write, D1 1 w on the prefix = 194/194."""
    d1 = r1w.d1_week(_present_without(()), start=PROTOCOL_START, end=PROTOCOL_T)
    assert (d1["covered_units"], d1["expected_units"], d1["ok"]) == (194, 194, True)


def test_evaluated_period_coverage() -> None:
    """``(T, 2026-06-29]`` : first stamp 2024-11-25, last 2026-06-29 = 581 days = 83 weeks → 84 stamps ; the two
    2025 stamps of the brief fall there → 82/84."""
    cov = r1w.d1_week(_present_without(BRIEF_MISSING), start=PROTOCOL_T, end=PROTOCOL_END)
    assert (cov["covered_units"], cov["expected_units"]) == (82, 84)


def _complete_block(start: datetime, end: datetime, interval: int) -> dict[str, object]:
    """A conforming, complete coverage block (agent rule 2: the healthy witness satisfies every clause)."""
    units = cc.expected_units(start, end, interval)
    expected = cc.expected_candles(start, end, interval)
    return {
        "expected": expected,
        "observed": expected,
        "covered_units": units,
        "expected_units": units,
        "unit": cc.coverage_unit(interval),
        "missing_stamps": [],
        "longest_gap_days": 0.0,
        "first_day": start.date().isoformat(),
        "last_day": end.date().isoformat(),
    }


@pytest.mark.parametrize("missing", [BRIEF_MISSING, (), BRIEF_MISSING[:3]])
def test_d1_week_is_the_rule_of_c3_select(missing: tuple[datetime, ...]) -> None:
    """``d1_week`` must read exactly what ``c3_select.d1_for_pair`` reads for the 1 w series."""
    present = _present_without(missing)
    coverage = {str(iv): _complete_block(PROTOCOL_START, PROTOCOL_T, iv) for iv in (5, 240, 1440)}
    coverage["10080"] = r1w.week_coverage_block(present, start=PROTOCOL_START, end=PROTOCOL_T)
    prefix_days = (PROTOCOL_T - PROTOCOL_START).total_seconds() / 86400.0
    chain = c3_select.d1_for_pair(
        coverage, start=PROTOCOL_START, end=PROTOCOL_T, prefix_days=prefix_days, where="t"
    )["per_interval"]["10080"]
    ours = r1w.d1_week(present, start=PROTOCOL_START, end=PROTOCOL_T)
    for key in ("covered_units", "expected_units", "ratio", "longest_gap_days", "ok"):
        assert ours[key] == chain[key], key


# ---------------------------------------------------------------------------
# Vision probe — pure part
# ---------------------------------------------------------------------------


def test_vision_months_are_the_opening_and_closing_months() -> None:
    assert r1w.vision_months_for_week(S) == [(2022, 5), (2022, 6)]  # 2022-05-30 → 2022-06-05
    assert r1w.vision_months_for_week(datetime(2025, 3, 3, tzinfo=UTC)) == [(2025, 2), (2025, 3)]
    assert r1w.vision_months_for_week(datetime(2022, 6, 13, tzinfo=UTC)) == [(2022, 6)]


def test_straddling_weeks_are_those_ending_in_another_month() -> None:
    """A week straddles when its Monday (``S − 7 d``) and its Sunday (``S − 1 d``) are in different months : the
    2023-01-02 week ends on 2023-01-01 (straddles), the 2022-06-13 week is all June."""
    stamps = [
        datetime(2022, 12, 26, tzinfo=UTC),  # 12-19 → 12-25
        datetime(2023, 1, 2, tzinfo=UTC),  # 12-26 → 01-01
        datetime(2022, 6, 13, tzinfo=UTC),  # 06-06 → 06-12
        S,  # 05-30 → 06-05
    ]
    assert r1w.straddling_weeks(stamps) == [datetime(2023, 1, 2, tzinfo=UTC), S]


def test_vision_url_follows_the_importer_scheme() -> None:
    assert r1w.vision_url("BTC/USDT", 2022, 5) == (
        "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1w/BTCUSDT-1w-2022-05.zip"
    )


def _ms(stamp: datetime) -> int:
    return int(stamp.timestamp()) * 1000


def test_vision_week_rows_end_stamps_and_keeps_the_raw_row() -> None:
    """Importer ``:136-141`` : ``row[0]`` is the open time (ms, or µs for 2025+ files), stored stamp = open + 1 w."""
    line_a = [
        str(_ms(datetime(2022, 5, 23, tzinfo=UTC))),
        "1",
        "2",
        "0.5",
        "1.5",
        "10",
        "0",
        "0",
        "7",
        "0",
        "0",
        "0",
    ]
    line_b = [
        str(_ms(datetime(2022, 5, 30, tzinfo=UTC)) * 1000),
        "3",
        "4",
        "2",
        "3.5",
        "20",
        "0",
        "0",
        "9",
        "0",
        "0",
        "0",
    ]
    csv_bytes = ("\n".join(",".join(line) for line in (line_a, line_b)) + "\n").encode()
    rows = r1w.vision_week_rows(csv_bytes, "BTC/USDT")
    assert [r["stamp"] for r in rows] == [datetime(2022, 5, 30, tzinfo=UTC), S]
    assert rows[1]["raw"] == line_b


# ---------------------------------------------------------------------------
# Output and import hygiene
# ---------------------------------------------------------------------------


def test_write_json_strict_refuses_a_non_native_value(tmp_path: Path) -> None:
    """Debt 22 : no ``default=str`` — a Decimal that was not converted must raise, not be stringified silently."""
    with pytest.raises(TypeError):
        r1w.write_json_strict(tmp_path / "x.json", {"volume": D("1")})
    digest = r1w.write_json_strict(tmp_path / "y.json", {"volume": "1"})
    assert len(digest) == 64
    assert json.loads((tmp_path / "y.json").read_text(encoding="utf-8")) == {"volume": "1"}


def test_import_does_not_mutate_environ() -> None:
    """Rule B4.2 : ``.env`` is loaded in ``main``, never at import (probe of ``test_scripts_env_purity``)."""
    probe = (
        "import importlib, json, os, sys\n"
        "root = sys.argv[1]\n"
        "sys.path[:0] = [root + '/scripts/audit', root + '/scripts', root + '/src', root]\n"
        "before = dict(os.environ)\n"
        "importlib.import_module('reconstruct_1w')\n"
        "print(json.dumps(sorted(k for k in os.environ if before.get(k) != os.environ[k])))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    proc = subprocess.run(
        [sys.executable, "-c", probe, str(_PROJECT_ROOT)],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []


# ===========================================================================
# Step 2 — write guards, provenance, model and migration (brief § 3, amended plan)
# ===========================================================================
#
# Expected values come from brief § 3.1 (table ``ohlc_derived`` : columns, types, comment), § 3.2 (the write
# replays control (c) before writing — one OHLCV mismatch aborts ; any target already present aborts ; 24 OHLC rows
# then 24 provenance rows, in one transaction) and Bruno's gate of 24/09 (plain INSERT, ``--vwap-policy`` explicit).
# The synthetic state below is a conforming witness (agent rule 2) : its weekly rows are the exact aggregates of its
# daily rows, the 8 brief stamps are missing, nothing is derived yet.

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
PROVENANCE = {"git_sha": "a" * 40, "script_sha256": "b" * 64}
NOTE = "docs/RESEARCH_LOG.md — entrée 13"
#: Brief § 3.1, table comment (the Markdown backticks around the table name are formatting, not content).
BRIEF_TABLE_COMMENT = (
    "Rows de market_data_ohlc non observées, dérivées par agrégation. Une row ici ⟺ la row OHLC "
    "correspondante n'est pas une donnée d'exchange."
)


def _synthetic_state(missing: tuple[datetime, ...] = BRIEF_MISSING) -> r1w.WriteState:
    daily: dict[str, dict[datetime, r1w.Candle]] = {}
    weekly: dict[str, dict[datetime, r1w.Candle]] = {}
    for index, pair in enumerate(r1w.PAIRS):
        days: dict[datetime, r1w.Candle] = {}
        stamp, k = PROTOCOL_START - WEEK, 0
        while stamp <= PROTOCOL_END:
            base = D(100 + 1000 * index + k % 97)
            days[stamp] = r1w.Candle(
                stamp,
                base,
                base + D("5.5"),
                base - D("3.25"),
                base + D("1.125"),
                D("10.00000001") + D(k % 7),
                100 + k % 13,
            )
            stamp, k = stamp + DAY, k + 1
        daily[pair] = days
        weekly[pair] = {
            week: r1w.aggregate_week(week, [days[s] for s in r1w.source_stamps(week)])
            for week in r1w.expected_week_stamps(PROTOCOL_START, PROTOCOL_END)
            if week not in missing
        }
    return r1w.WriteState(
        weekly=weekly, daily=daily, derived_keys=frozenset(), derived_table_exists=True
    )


@pytest.fixture(scope="module")
def healthy_state() -> r1w.WriteState:
    return _synthetic_state()


def _variant(state: r1w.WriteState, **changes: object) -> r1w.WriteState:
    weekly = {pair: dict(series) for pair, series in state.weekly.items()}
    daily = {pair: dict(series) for pair, series in state.daily.items()}
    fields = {
        "weekly": weekly,
        "daily": daily,
        "derived_keys": state.derived_keys,
        "derived_table_exists": state.derived_table_exists,
    }
    fields.update(changes)
    return r1w.WriteState(**fields)  # type: ignore[arg-type]


def _plan(state: r1w.WriteState, policy: str = "null") -> r1w.WritePlan:
    return r1w.plan_write(
        state, vwap_policy=policy, note=NOTE, provenance=PROVENANCE, created_at=NOW
    )


def test_plan_write_builds_24_ohlc_rows_and_24_provenance_rows(
    healthy_state: r1w.WriteState,
) -> None:
    plan = _plan(healthy_state)
    assert len(plan.ohlc_rows) == 24 and len(plan.provenance_rows) == 24
    keys = {(row["pair"], row["timestamp"]) for row in plan.ohlc_rows}
    assert keys == {(pair, stamp) for pair in r1w.PAIRS for stamp in BRIEF_MISSING}
    assert {(row["pair"], row["timestamp"]) for row in plan.provenance_rows} == keys
    # One row checked against the method's text (brief § 2), from the daily rows directly.
    row = next(r for r in plan.ohlc_rows if r["pair"] == "ETH/USDT" and r["timestamp"] == S)
    days = [healthy_state.daily["ETH/USDT"][S + k * DAY] for k in range(-6, 1)]
    assert row["interval"] == 10080 and row["exchange"] == "binance"
    assert row["open"] == days[0].open and row["close"] == days[-1].close
    assert row["high"] == max(d.high for d in days) and row["low"] == min(d.low for d in days)
    assert row["volume"] == sum((d.volume for d in days), D(0))
    assert row["trades_count"] == sum(d.trades_count for d in days)
    assert row["vwap"] is None


def test_provenance_rows_carry_the_brief_columns(healthy_state: r1w.WriteState) -> None:
    """Brief § 3.1 : method ``agg_1d_v1``, source_interval 1440, the 7 daily stamps in ISO, the replayable sha,
    the vwap policy, the script sha, the git sha, created_at, and a note referencing the RESEARCH_LOG."""
    plan = _plan(healthy_state)
    prov = next(r for r in plan.provenance_rows if r["pair"] == "SOL/USDT" and r["timestamp"] == S)
    days = [healthy_state.daily["SOL/USDT"][S + k * DAY] for k in range(-6, 1)]
    assert prov["interval"] == 10080 and prov["exchange"] == "binance"
    assert prov["method"] == "agg_1d_v1" and prov["source_interval"] == 1440
    assert prov["source_stamps"] == [(S + k * DAY).isoformat() for k in range(-6, 1)]
    assert prov["source_sha256"] == r1w.source_sha256("SOL/USDT", days)
    assert prov["vwap_policy"] == "null"
    assert (prov["git_sha"], prov["script_sha256"]) == (
        PROVENANCE["git_sha"],
        PROVENANCE["script_sha256"],
    )
    assert (prov["created_at"], prov["note"]) == (NOW, NOTE)


def test_plan_write_reports_d1_before(healthy_state: r1w.WriteState) -> None:
    plan = _plan(healthy_state)
    assert {
        pair: (d["covered_units"], d["expected_units"]) for pair, d in plan.d1_before.items()
    } == dict.fromkeys(r1w.PAIRS, (188, 194))


def test_plan_write_refuses_an_ohlcv_mismatch(healthy_state: r1w.WriteState) -> None:
    """Brief § 3.2 : control (c) is replayed before writing ; one OHLCV mismatch → abort."""
    state = _variant(healthy_state)
    week = datetime(2023, 5, 8, tzinfo=UTC)
    stored = state.weekly["BTC/USDT"][week]
    state.weekly["BTC/USDT"][week] = r1w.Candle(
        week,
        stored.open,
        stored.high,
        stored.low,
        stored.close + D("0.00000001"),
        stored.volume,
        stored.trades_count,
    )
    with pytest.raises(r1w.WriteRefusedError) as exc:
        _plan(state)
    assert exc.value.code == 1
    assert any("(c)" in reason and "BTC/USDT" in reason for reason in exc.value.reasons)


def test_plan_write_refuses_a_target_already_in_ohlc(healthy_state: r1w.WriteState) -> None:
    state = _variant(healthy_state)
    target = BRIEF_MISSING[0]
    days = [state.daily["ETH/USDT"][s] for s in r1w.source_stamps(target)]
    state.weekly["ETH/USDT"][target] = r1w.aggregate_week(target, days)
    with pytest.raises(r1w.WriteRefusedError) as exc:
        _plan(state)
    assert exc.value.code == 1


def test_plan_write_refuses_a_target_already_derived(healthy_state: r1w.WriteState) -> None:
    state = _variant(healthy_state, derived_keys=frozenset({("SOL/USDT", BRIEF_MISSING[7])}))
    with pytest.raises(r1w.WriteRefusedError) as exc:
        _plan(state)
    assert exc.value.code == 1


def test_plan_write_refuses_a_six_of_seven_target(healthy_state: r1w.WriteState) -> None:
    state = _variant(healthy_state)
    del state.daily["BTC/USDT"][BRIEF_MISSING[3] - 2 * DAY]
    with pytest.raises(r1w.WriteRefusedError) as exc:
        _plan(state)
    assert exc.value.code == 1


def test_plan_write_refuses_without_the_provenance_table(healthy_state: r1w.WriteState) -> None:
    with pytest.raises(r1w.WriteRefusedError) as exc:
        _plan(_variant(healthy_state, derived_table_exists=False))
    assert exc.value.code == 2


def test_plan_write_refuses_an_unknown_vwap_policy(healthy_state: r1w.WriteState) -> None:
    with pytest.raises(r1w.WriteRefusedError) as exc:
        _plan(healthy_state, policy="mean")
    assert exc.value.code == 2


def test_numeric_fit_of_decimal_18_8() -> None:
    """``DECIMAL(18, 8)`` (``OHLCData``) : at most 8 decimals and 10 integer digits — beyond, Postgres rounds or
    overflows, and a derived row must never be rounded silently."""
    assert r1w.fits_numeric_18_8(D("9999999999.99999999"))
    assert r1w.fits_numeric_18_8(D("57102095.79500000"))
    assert not r1w.fits_numeric_18_8(D("1.123456789"))
    assert not r1w.fits_numeric_18_8(D("10000000000"))


def test_plan_write_refuses_a_value_that_does_not_fit(healthy_state: r1w.WriteState) -> None:
    state = _variant(healthy_state)
    target = BRIEF_MISSING[1]
    for stamp in r1w.source_stamps(target):
        d = state.daily["SOL/USDT"][stamp]
        state.daily["SOL/USDT"][stamp] = r1w.Candle(
            stamp, d.open, d.high, d.low, d.close, D("5000000000"), d.trades_count
        )
    with pytest.raises(r1w.WriteRefusedError) as exc:
        _plan(state)
    assert exc.value.code == 1


class _FakeConn:
    """Records every statement ; the write must not execute anything before the plan is accepted."""

    def __init__(self) -> None:
        self.executed: list[tuple[object, object]] = []

    async def execute(self, statement: object, parameters: object = None) -> None:
        self.executed.append((statement, parameters))


async def test_perform_write_refuses_a_mismatch_without_any_insert(
    healthy_state: r1w.WriteState,
) -> None:
    """Brief § 4 : ``write`` refuses when the control returns a mismatch (mock) — and nothing is executed."""
    state = _variant(healthy_state)
    week = datetime(2024, 1, 8, tzinfo=UTC)
    stored = state.weekly["SOL/USDT"][week]
    state.weekly["SOL/USDT"][week] = r1w.Candle(
        week,
        stored.open,
        stored.high + D("1"),
        stored.low,
        stored.close,
        stored.volume,
        stored.trades_count,
    )

    async def load(_conn: object) -> r1w.WriteState:
        return state

    conn = _FakeConn()
    with pytest.raises(r1w.WriteRefusedError):
        await r1w.perform_write(
            conn, load=load, vwap_policy="null", note=NOTE, provenance=PROVENANCE, created_at=NOW
        )
    assert conn.executed == []


async def test_perform_write_inserts_ohlc_then_provenance(healthy_state: r1w.WriteState) -> None:
    async def load(_conn: object) -> r1w.WriteState:
        return healthy_state

    conn = _FakeConn()
    plan = await r1w.perform_write(
        conn, load=load, vwap_policy="null", note=NOTE, provenance=PROVENANCE, created_at=NOW
    )
    assert [statement.table.name for statement, _ in conn.executed] == [  # type: ignore[attr-defined]
        "market_data_ohlc",
        "ohlc_derived",
    ]
    assert conn.executed[0][1] == plan.ohlc_rows and conn.executed[1][1] == plan.provenance_rows
    # Plain INSERT (gate 24/09) : no ON CONFLICT clause on either statement.
    assert all("ON CONFLICT" not in str(statement) for statement, _ in conn.executed)


def test_ohlc_derived_model_is_the_brief_table() -> None:
    from sqlalchemy import TIMESTAMP, Integer, String, Text
    from sqlalchemy.dialects.postgresql import JSONB

    from krakenbot.models.market_data import OHLCData, OHLCDerived

    table = OHLCDerived.__table__
    assert table.name == "ohlc_derived"
    assert [c.name for c in table.primary_key.columns] == [
        "timestamp",
        "pair",
        "interval",
        "exchange",
    ]
    for name in ("timestamp", "pair", "interval", "exchange"):  # « mêmes types que OHLCData »
        assert repr(table.c[name].type) == repr(OHLCData.__table__.c[name].type), name
    assert set(table.c.keys()) == {
        "timestamp",
        "pair",
        "interval",
        "exchange",
        "method",
        "source_interval",
        "source_stamps",
        "source_sha256",
        "vwap_policy",
        "script_sha256",
        "git_sha",
        "created_at",
        "note",
    }
    assert isinstance(table.c.method.type, String)
    assert isinstance(table.c.source_interval.type, Integer)
    assert isinstance(table.c.source_stamps.type, JSONB)
    assert (table.c.source_sha256.type.length, table.c.script_sha256.type.length) == (64, 64)
    assert table.c.git_sha.type.length == 40
    assert isinstance(table.c.vwap_policy.type, String)
    assert isinstance(table.c.created_at.type, TIMESTAMP) and table.c.created_at.type.timezone
    assert isinstance(table.c.note.type, Text)
    assert table.comment == BRIEF_TABLE_COMMENT
    assert not table.foreign_keys  # logical FK only : the target is a hypertable


def _load_migration() -> object:
    import importlib.util

    matches = sorted((_PROJECT_ROOT / "alembic" / "versions").glob("*_ohlc_derived_provenance.py"))
    assert len(matches) == 1, matches
    spec = importlib.util.spec_from_file_location("ohlc_derived_migration", matches[0])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_creates_only_the_provenance_table() -> None:
    """Brief § 3.1 : a new table only — no ALTER on ``market_data_ohlc`` ; downgrade drops it."""
    from unittest.mock import MagicMock

    from krakenbot.models.market_data import OHLCDerived

    migration = _load_migration()
    assert migration.down_revision == "c1ae7a1c0001"  # type: ignore[attr-defined]
    op = MagicMock()
    migration.op = op  # type: ignore[attr-defined]
    migration.upgrade()  # type: ignore[attr-defined]
    assert [call[0] for call in op.method_calls] == ["create_table"]
    args, kwargs = op.create_table.call_args
    assert args[0] == "ohlc_derived"
    columns = {c.name: c for c in args[1:] if hasattr(c, "type")}
    model = OHLCDerived.__table__
    assert set(columns) == set(model.c.keys())
    for name, column in columns.items():
        assert repr(column.type) == repr(model.c[name].type), name
        assert column.nullable == model.c[name].nullable, name
    pk = [a for a in args[1:] if a.__class__.__name__ == "PrimaryKeyConstraint"]
    assert len(pk) == 1 and list(pk[0]._pending_colargs) == [
        "timestamp",
        "pair",
        "interval",
        "exchange",
    ]
    assert kwargs.get("comment") == BRIEF_TABLE_COMMENT
    op.reset_mock()
    migration.downgrade()  # type: ignore[attr-defined]
    assert op.method_calls == [(("drop_table"), ("ohlc_derived",), {})]


@pytest.mark.parametrize(
    "argv",
    [
        ["write", "--output", "w.json", "--note", NOTE],  # no --vwap-policy
        ["write", "--output", "w.json", "--vwap-policy", "null"],  # no --note
        ["write", "--output", "w.json", "--vwap-policy", "mean", "--note", NOTE],
        [
            "write",
            "--output",
            "w.json",
            "--vwap-policy",
            "null",
            "--note",
            NOTE,
            "--allow-uncommitted",
        ],
    ],
)
def test_write_cli_requires_an_explicit_policy_and_note(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        r1w.parse_args(argv)
    assert exc.value.code == 2
