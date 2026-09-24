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
