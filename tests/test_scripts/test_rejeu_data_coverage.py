"""Rejeu diagnostic grid — tests of ``scripts/audit/rejeu_data_coverage.py`` (prespec D.1 / D.2).

The counting is a pure function over ``(timestamp, interval)`` rows, so every rule of section D
is exercised on synthetic rows and no test needs the database. Four fixtures carry the load:

* a **full pair** (BTC-like) — 288 5 m candles a day over the 1096 window days;
* a pair with the **271-day hole** that reproduces SOL, rebuilt candle-for-candle so that its
  four reported counts equal the ones measured in the DB (237504 / 4948 / 825 / 116);
* a pair with **one 5 m candle a day** — ``days_5m`` scores 1096/1096 while
  ``days_5m_complete`` scores 0, which is what makes BTC's admissibility evidence rather than
  an assumption (prespec D.2, last paragraph);
* a pair that **starts late**, failing the ``first_last`` clause alone.

The midnight decision is pinned on its own: a stamp of exactly ``D+1 00:00`` closes day ``D``,
so the candle stamped at the window's end is *inside* the window and the one stamped at its
start is *outside* it. The defect traps are the ones a real fetch can produce: a naive
timestamp, rows outside the window, rows carrying an interval the schema does not report, an
empty fetch, and a weekly series with holes.

The single DB-touching test is skipped behind a socket probe (127.0.0.1:5433 then 5432), like
``tests/test_scripts/test_run_p6_determinism.py``.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
import functools
import hashlib
from pathlib import Path
import socket
import sys

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

import rejeu_common as rc
import rejeu_data_coverage as dc

START = rc.WINDOW_START
END = rc.WINDOW_END
PLUS_TWO = timezone(timedelta(hours=2))
FIRST_DAY = date(2023, 4, 1)
LAST_DAY = date(2026, 3, 31)

#: The two weekly candles absent from BOTH pairs, as **end** stamps. The pre-specification
#: names them 2025-01-27 / 2025-02-24, which are the *open* Mondays of the same two weeks.
MISSING_WEEK_END_STAMPS = (
    datetime(2025, 2, 3, tzinfo=UTC),
    datetime(2025, 3, 3, tzinfo=UTC),
)
MISSING_WEEK_OPEN_DAYS = (date(2025, 1, 27), date(2025, 2, 24))

#: SOL: first 5 m candle in window, measured in the DB (prespec D.3).
SOL_FIRST_STAMP = datetime(2023, 12, 28, 8, 5, tzinfo=UTC)
SOL_FIRST_DAY = date(2023, 12, 28)
SOL_GAP_DAYS = 271
SOL_COVERED_DAYS = 825
#: SOL: the four ``counts_by_interval`` values measured in the DB on 2026-09-20.
SOL_DB_COUNTS = {"5": 237504, "240": 4948, "1440": 825, "10080": 116}
#: BTC: same, a full pair.
BTC_DB_COUNTS = {"5": 315648, "240": 6576, "1440": 1096, "10080": 155}


# ---------------------------------------------------------------------------
# Synthetic rows
# ---------------------------------------------------------------------------


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=UTC)


def _rows_5m_day(day: date, k_from: int = 1, k_to: int = 288) -> list[tuple[datetime, int]]:
    """5 m stamps of one day: ``k`` in 1..288 gives ``D 00:05`` .. ``D+1 00:00``."""
    base = _midnight(day)
    return [(base + timedelta(minutes=5 * k), 5) for k in range(k_from, k_to + 1)]


@functools.cache
def _rows_5m(first: date, last: date, per_day: int = 288) -> tuple[tuple[datetime, int], ...]:
    out: list[tuple[datetime, int]] = []
    day = first
    while day <= last:
        out.extend(_rows_5m_day(day, 1, per_day))
        day += timedelta(days=1)
    return tuple(out)


@functools.cache
def _rows_4h(first: date, last: date, per_day: int = 6) -> tuple[tuple[datetime, int], ...]:
    out: list[tuple[datetime, int]] = []
    day = first
    while day <= last:
        base = _midnight(day)
        out.extend((base + timedelta(hours=4 * k), 240) for k in range(7 - per_day, 7))
        day += timedelta(days=1)
    return tuple(out)


@functools.cache
def _rows_1d(first: date, last: date) -> tuple[tuple[datetime, int], ...]:
    """One daily candle per day, stamped at the day's end (``D+1 00:00``)."""
    out: list[tuple[datetime, int]] = []
    day = first
    while day <= last:
        out.append((_midnight(day) + timedelta(days=1), 1440))
        day += timedelta(days=1)
    return tuple(out)


def _rows_1w(
    *, omit: tuple[datetime, ...] = MISSING_WEEK_END_STAMPS, not_before: datetime | None = None
) -> list[tuple[datetime, int]]:
    stamps = dc.expected_weekly_stamps(START, END)
    return [
        (stamp, 10080)
        for stamp in stamps
        if stamp not in omit and (not_before is None or stamp >= not_before)
    ]


@functools.cache
def _full_pair() -> tuple[tuple[datetime, int], ...]:
    """A pair with no hole at all — the BTC-like reference."""
    return (
        *_rows_5m(FIRST_DAY, LAST_DAY),
        *_rows_4h(FIRST_DAY, LAST_DAY),
        *_rows_1d(FIRST_DAY, LAST_DAY),
        *_rows_1w(),
    )


@functools.cache
def _sol_like(*, holed_4h: bool = True) -> tuple[tuple[datetime, int], ...]:
    """SOL rebuilt candle-for-candle: nothing before 2023-12-28 08:05, then complete.

    ``holed_4h=False`` is the counterfactual the pre-specification's "four clauses out of five"
    implies — a 4 h series that would cover the whole window despite the 5 m hole.
    """
    partial_from = (SOL_FIRST_STAMP - _midnight(SOL_FIRST_DAY)) // timedelta(minutes=5)
    five_min = [
        *_rows_5m_day(SOL_FIRST_DAY, partial_from, 288),
        *_rows_5m(SOL_FIRST_DAY + timedelta(days=1), LAST_DAY),
    ]
    four_h = (
        [
            *_rows_4h(SOL_FIRST_DAY, SOL_FIRST_DAY, per_day=4),
            *_rows_4h(SOL_FIRST_DAY + timedelta(days=1), LAST_DAY),
        ]
        if holed_4h
        else list(_rows_4h(FIRST_DAY, LAST_DAY))
    )
    return (
        *five_min,
        *four_h,
        *_rows_1d(SOL_FIRST_DAY, LAST_DAY),
        *_rows_1w(not_before=datetime(2024, 1, 1, tzinfo=UTC)),
    )


# ---------------------------------------------------------------------------
# Day attribution — the decision, pinned
# ---------------------------------------------------------------------------


def test_day_of_midnight_closes_the_previous_day() -> None:
    assert dc.day_of(datetime(2026, 4, 1, tzinfo=UTC)) == date(2026, 3, 31)
    assert dc.day_of(datetime(2023, 4, 1, tzinfo=UTC)) == date(2023, 3, 31)
    assert dc.day_of(datetime(2023, 4, 1, 0, 5, tzinfo=UTC)) == date(2023, 4, 1)
    assert dc.day_of(datetime(2023, 4, 1, 23, 55, tzinfo=UTC)) == date(2023, 4, 1)
    assert dc.day_of(datetime(2023, 4, 2, tzinfo=UTC)) == date(2023, 4, 1)


def test_day_of_normalises_a_non_utc_stamp() -> None:
    other = datetime(2026, 4, 1, 2, tzinfo=PLUS_TWO)
    assert other.astimezone(UTC) == datetime(2026, 4, 1, tzinfo=UTC)
    assert dc.day_of(other) == date(2026, 3, 31)


def test_window_bounds_follow_the_stamp_attribution() -> None:
    """The stamp at ``end`` is in the window (it closes 2026-03-31); the one at ``start`` is not."""
    rows = [
        (START, 5),  # closes 2023-03-31 -> outside
        (END, 5),  # closes 2026-03-31 -> inside
    ]
    measure = dc.measure_pair(rows)
    assert measure["counts_by_interval"]["5"] == 1
    assert measure["days_5m"] == 1
    assert measure["first_covered_day"] == "2026-03-31"
    assert measure["last_covered_day"] == "2026-03-31"
    assert measure["max_gap_days"] == 1095


def test_naive_timestamp_is_a_defect_not_an_assumption() -> None:
    with pytest.raises(ValueError, match="naive timestamp"):
        dc.measure_pair([(datetime(2024, 1, 1, 12, 0), 5)])


def test_rows_outside_the_window_are_ignored() -> None:
    rows = [
        (datetime(2023, 3, 20, 12, tzinfo=UTC), 5),
        (datetime(2026, 5, 1, 12, tzinfo=UTC), 5),
        (datetime(2024, 6, 1, 12, tzinfo=UTC), 5),
    ]
    measure = dc.measure_pair(rows)
    assert measure["counts_by_interval"]["5"] == 1
    assert measure["first_covered_day"] == "2024-06-01"


def test_unreported_intervals_are_ignored() -> None:
    rows = [
        (datetime(2024, 6, 1, 12, tzinfo=UTC), 60),
        (datetime(2024, 6, 1, 12, tzinfo=UTC), 15),
        (datetime(2024, 6, 1, 12, tzinfo=UTC), 1),
    ]
    measure = dc.measure_pair(rows)
    assert measure["counts_by_interval"] == {"5": 0, "240": 0, "1440": 0, "10080": 0}
    assert measure["days_5m"] == 0


# ---------------------------------------------------------------------------
# The weekly grid
# ---------------------------------------------------------------------------


def test_expected_weekly_grid_is_the_mondays_of_the_window() -> None:
    stamps = dc.expected_weekly_stamps(START, END)
    assert len(stamps) == 157
    assert stamps[0] == datetime(2023, 4, 3, tzinfo=UTC)
    assert stamps[-1] == datetime(2026, 3, 30, tzinfo=UTC)
    assert {s.weekday() for s in stamps} == {0}
    assert {(s.hour, s.minute, s.second) for s in stamps} == {(0, 0, 0)}
    assert all(START < s <= END for s in stamps)


def test_missing_1w_stamps_are_end_stamps_of_the_two_named_weeks() -> None:
    """The prespec names 2025-01-27 / 2025-02-24; those are the *open* Mondays of the gap."""
    measure = dc.measure_pair(_rows_1w())
    assert measure["counts_by_interval"]["10080"] == 155
    assert measure["missing_1w_stamps"] == [s.isoformat() for s in MISSING_WEEK_END_STAMPS]
    for end_stamp, open_day in zip(MISSING_WEEK_END_STAMPS, MISSING_WEEK_OPEN_DAYS, strict=True):
        assert (end_stamp - timedelta(days=7)).date() == open_day


# ---------------------------------------------------------------------------
# The four pair shapes
# ---------------------------------------------------------------------------


def test_full_pair_is_admissible_on_the_five_clauses() -> None:
    measure = dc.measure_pair(_full_pair())
    assert measure["days_5m"] == 1096
    assert measure["days_5m_complete"] == 1096
    assert measure["days_4h"] == 1096
    assert measure["max_gap_days"] == 0
    assert measure["first_covered_day"] == "2023-04-01"
    assert measure["last_covered_day"] == "2026-03-31"
    assert measure["median_daily_completeness_5m"] == 1.0
    assert measure["days_below_90pct"] == 0
    assert measure["days_below_50pct"] == 0
    assert measure["counts_by_interval"] == BTC_DB_COUNTS
    assert measure["missing_1w_stamps"] == [s.isoformat() for s in MISSING_WEEK_END_STAMPS]
    assert measure["clauses"] == dict.fromkeys(dc.CLAUSE_KEYS, True)
    assert measure["admissible"] is True


def test_sol_like_hole_reproduces_the_measured_counts() -> None:
    measure = dc.measure_pair(_sol_like())
    assert measure["counts_by_interval"] == SOL_DB_COUNTS
    assert measure["days_5m"] == SOL_COVERED_DAYS
    assert measure["days_5m_complete"] == SOL_COVERED_DAYS
    assert measure["days_4h"] == SOL_COVERED_DAYS
    assert measure["max_gap_days"] == SOL_GAP_DAYS
    assert measure["first_covered_day"] == SOL_FIRST_DAY.isoformat()
    assert measure["last_covered_day"] == "2026-03-31"
    # 271 empty days + the partial first day (192/288 = 66.7 %) are below 90 %.
    assert measure["days_below_50pct"] == SOL_GAP_DAYS
    assert measure["days_below_90pct"] == SOL_GAP_DAYS + 1
    assert measure["admissible"] is False
    assert len(measure["missing_1w_stamps"]) == 157 - SOL_DB_COUNTS["10080"]
    assert measure["missing_1w_stamps"][-2:] == [s.isoformat() for s in MISSING_WEEK_END_STAMPS]


def test_sol_like_hole_fails_every_clause_when_the_4h_series_is_holed_too() -> None:
    """Measured reality: 4 h stops where 5 m stops, so five clauses fail, not the expected four."""
    clauses = dc.measure_pair(_sol_like(holed_4h=True))["clauses"]
    assert clauses == dict.fromkeys(dc.CLAUSE_KEYS, False)


def test_sol_like_hole_fails_four_clauses_when_only_the_5m_series_is_holed() -> None:
    """The counterfactual behind the prespec's "inadmissible sur quatre clauses sur cinq"."""
    clauses = dc.measure_pair(_sol_like(holed_4h=False))["clauses"]
    assert clauses["days_4h"] is True
    assert [c for c in dc.CLAUSE_KEYS if not clauses[c]] == [
        "days_5m",
        "days_5m_complete",
        "max_gap_days",
        "first_last",
    ]


def test_one_candle_a_day_scores_full_days_5m_but_zero_completeness() -> None:
    """Why ``days_5m_complete`` exists: presence alone would score a perfect 1096/1096."""
    rows = [*_rows_5m(FIRST_DAY, LAST_DAY, per_day=1), *_rows_4h(FIRST_DAY, LAST_DAY)]
    measure = dc.measure_pair(rows)
    assert measure["days_5m"] == 1096
    assert measure["days_5m_complete"] == 0
    assert measure["max_gap_days"] == 0
    assert measure["clauses"]["days_5m"] is True
    assert measure["clauses"]["days_4h"] is True
    assert measure["clauses"]["max_gap_days"] is True
    assert measure["clauses"]["first_last"] is True
    assert measure["clauses"]["days_5m_complete"] is False
    assert measure["admissible"] is False
    assert measure["median_daily_completeness_5m"] == round(1 / 288, 9)
    assert measure["days_below_50pct"] == 1096


def test_a_pair_that_starts_late_fails_only_the_first_last_clause() -> None:
    late = FIRST_DAY + timedelta(days=2)
    rows = [
        *_rows_5m(late, LAST_DAY),
        *_rows_4h(late, LAST_DAY),
        *_rows_1d(late, LAST_DAY),
        *_rows_1w(),
    ]
    measure = dc.measure_pair(rows)
    assert measure["days_5m"] == 1094
    assert measure["days_5m_complete"] == 1094
    assert measure["days_4h"] == 1094
    assert measure["max_gap_days"] == 2
    assert measure["first_covered_day"] == "2023-04-03"
    assert [c for c in dc.CLAUSE_KEYS if not measure["clauses"][c]] == ["first_last"]
    assert measure["admissible"] is False


def test_a_pair_that_ends_early_fails_only_the_first_last_clause() -> None:
    early = LAST_DAY - timedelta(days=1)
    rows = [*_rows_5m(FIRST_DAY, early), *_rows_4h(FIRST_DAY, early)]
    measure = dc.measure_pair(rows)
    assert measure["last_covered_day"] == "2026-03-30"
    assert measure["max_gap_days"] == 1
    assert [c for c in dc.CLAUSE_KEYS if not measure["clauses"][c]] == ["first_last"]


def test_empty_fetch_is_a_measured_zero_not_an_assumed_coverage() -> None:
    measure = dc.measure_pair([])
    assert measure["days_5m"] == 0
    assert measure["days_5m_complete"] == 0
    assert measure["days_4h"] == 0
    assert measure["max_gap_days"] == 1096
    assert measure["first_covered_day"] is None
    assert measure["last_covered_day"] is None
    assert measure["median_daily_completeness_5m"] == 0.0
    assert measure["days_below_50pct"] == 1096
    assert measure["days_below_90pct"] == 1096
    assert len(measure["missing_1w_stamps"]) == 157
    assert measure["clauses"] == dict.fromkeys(dc.CLAUSE_KEYS, False)
    assert measure["admissible"] is False


def test_uncovered_days_count_as_zero_in_the_median() -> None:
    """Documented convention: the median runs over all 1096 window days, a hole counting 0.0."""
    covered_from = LAST_DAY - timedelta(days=499)
    measure = dc.measure_pair(_rows_5m(covered_from, LAST_DAY))
    assert measure["days_5m"] == 500
    assert measure["median_daily_completeness_5m"] == 0.0
    assert measure["days_below_50pct"] == 1096 - 500


# ---------------------------------------------------------------------------
# Frozen shapes, determinism, rendering
# ---------------------------------------------------------------------------


def test_measure_pair_key_set_is_the_frozen_schema() -> None:
    measure = dc.measure_pair([])
    assert set(measure) == set(dc.PAIR_KEYS)
    assert list(measure["clauses"]) == list(dc.CLAUSE_KEYS)
    assert list(measure["counts_by_interval"]) == [str(i) for i in dc.INTERVALS_REPORTED]


def test_prespec_block_matches_the_committed_file() -> None:
    block = dc.prespec_block()
    path = _PROJECT_ROOT / dc.PRESPEC_RELPATH
    assert block == {
        "path": dc.PRESPEC_RELPATH,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_build_artifact_is_deterministic_and_carries_the_frozen_header() -> None:
    prespec = {"path": dc.PRESPEC_RELPATH, "sha256": "0" * 64}
    rows = {"BTC/USDC": list(_rows_5m(FIRST_DAY, FIRST_DAY)), "SOL/USDC": []}
    now = datetime(2026, 9, 19, 12, 30, tzinfo=PLUS_TWO)
    first = dc.build_artifact(rows, generated_at=now, prespec=prespec)
    second = dc.build_artifact(rows, generated_at=now, prespec=prespec)
    assert rc.dumps_canonical(first) == rc.dumps_canonical(second)
    assert set(first) == {"generated_at", "base_sha", "prespec", "exchange", "window", "pairs"}
    assert first["generated_at"] == "2026-09-19T10:30:00+00:00"  # normalised to UTC
    assert first["base_sha"] == rc.BASE_SHA
    assert first["exchange"] == "binance"
    assert first["window"] == {
        "start": START.isoformat(),
        "end": END.isoformat(),
        "days": rc.WINDOW_DAYS,
    }
    assert list(first["pairs"]) == ["BTC/USDC", "SOL/USDC"]


def test_artifact_round_trips_through_write_json(tmp_path: Path) -> None:
    prespec = {"path": dc.PRESPEC_RELPATH, "sha256": "0" * 64}
    artifact = dc.build_artifact(
        {"BTC/USDC": list(_full_pair()), "SOL/USDC": list(_sol_like())},
        generated_at=datetime(2026, 9, 19, tzinfo=UTC),
        prespec=prespec,
    )
    out = tmp_path / "data_coverage.json"
    digest = rc.write_json(out, artifact)
    assert rc.read_json(out) == artifact
    assert digest == rc.write_json(tmp_path / "again.json", artifact)
    assert artifact["pairs"]["BTC/USDC"]["admissible"] is True
    assert artifact["pairs"]["SOL/USDC"]["admissible"] is False


def test_render_markdown_shows_both_verdicts_and_the_missing_stamps() -> None:
    artifact = dc.build_artifact(
        {"BTC/USDC": list(_full_pair()), "SOL/USDC": list(_sol_like())},
        generated_at=datetime(2026, 9, 19, tzinfo=UTC),
        prespec={"path": dc.PRESPEC_RELPATH, "sha256": "0" * 64},
    )
    text = dc.render_markdown(artifact)
    assert "BTC/USDC" in text and "SOL/USDC" in text
    assert "**admissible**" in text and "**inadmissible**" in text
    assert "ÉCHEC" in text
    assert MISSING_WEEK_END_STAMPS[0].isoformat() in text
    assert f">= {rc.COVERAGE_MIN_DAYS}" in text
    assert f"<= {rc.MAX_GAP_DAYS}" in text


def test_measure_pair_reads_the_frozen_thresholds_from_rejeu_common() -> None:
    """A pair exactly at the floor passes; one candle short fails — no restated constant."""
    covered_from = LAST_DAY - timedelta(days=rc.COVERAGE_MIN_DAYS - 1)
    at_floor = dc.measure_pair(
        [*_rows_5m(covered_from, LAST_DAY), *_rows_4h(covered_from, LAST_DAY)]
    )
    assert at_floor["days_5m"] == rc.COVERAGE_MIN_DAYS
    assert at_floor["clauses"]["days_5m"] is True
    assert at_floor["clauses"]["days_5m_complete"] is True
    assert at_floor["clauses"]["days_4h"] is True
    one_short = dc.measure_pair(
        [
            *_rows_5m(covered_from + timedelta(days=1), LAST_DAY),
            *_rows_4h(covered_from + timedelta(days=1), LAST_DAY),
        ]
    )
    assert one_short["days_5m"] == rc.COVERAGE_MIN_DAYS - 1
    assert one_short["clauses"]["days_5m"] is False


def test_day_5m_complete_sits_exactly_on_the_frozen_minimum() -> None:
    exact = dc.measure_pair(_rows_5m(FIRST_DAY, LAST_DAY, per_day=rc.DAY_5M_COMPLETE_MIN))
    assert exact["days_5m_complete"] == 1096
    just_under = dc.measure_pair(_rows_5m(FIRST_DAY, LAST_DAY, per_day=rc.DAY_5M_COMPLETE_MIN - 1))
    assert just_under["days_5m"] == 1096
    assert just_under["days_5m_complete"] == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_defaults_point_at_the_frozen_artifact_path() -> None:
    args = dc.parse_args([])
    assert args.output == rc.PROJECT_ROOT / "results" / "rejeu_grid_20260919" / "data_coverage.json"
    assert args.markdown is None
    assert args.start == rc.WINDOW_START and args.end == rc.WINDOW_END
    assert args.generated_at.tzinfo is not None


def test_now_is_injectable_and_normalised() -> None:
    assert dc.parse_args(["--now", "2026-09-19T00:00:00+00:00"]).generated_at == datetime(
        2026, 9, 19, tzinfo=UTC
    )
    assert dc.parse_args(["--now", "2026-09-19T00:00:00"]).generated_at == datetime(
        2026, 9, 19, tzinfo=UTC
    )


def test_main_rejects_a_bad_now_before_touching_the_database() -> None:
    with pytest.raises(SystemExit) as excinfo:
        dc.main(["--now", "pas-une-date"])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# DB layer — skipped when the tunnel is down
# ---------------------------------------------------------------------------


def _db_reachable() -> bool:
    for port in (5433, 5432):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            continue
    return False


@pytest.mark.skipif(
    not _db_reachable(),
    reason="Database not reachable (tunnel down or no local Postgres).",
)
def test_fetch_rows_returns_tz_aware_stamps_of_the_requested_intervals() -> None:
    """Light contract check of the DB layer: a three-day slice, nothing counted here."""
    import asyncio

    from dotenv import load_dotenv

    load_dotenv(rc.PROJECT_ROOT / ".env")

    slice_start = datetime(2024, 6, 1, tzinfo=UTC)
    slice_end = datetime(2024, 6, 4, tzinfo=UTC)

    async def _run() -> list[tuple[datetime, int]]:
        settings = dc.Settings()
        db_manager = dc.DatabaseManager()
        await db_manager.init_db(settings)
        try:
            return await dc.fetch_rows(db_manager, "BTC/USDC", start=slice_start, end=slice_end)
        finally:
            await db_manager.close_db()

    rows = asyncio.run(_run())
    assert rows, "no BTC/USDC rows in the probe slice"
    assert all(isinstance(stamp, datetime) and stamp.tzinfo is not None for stamp, _ in rows)
    assert all(slice_start < stamp <= slice_end for stamp, _ in rows)
    assert {interval for _, interval in rows} <= set(dc.INTERVALS_REPORTED)
    assert sum(1 for _, interval in rows if interval == 5) == 3 * 288


@pytest.mark.slow
@pytest.mark.skipif(
    not _db_reachable(),
    reason="Database not reachable (tunnel down or no local Postgres).",
)
def test_measured_coverage_still_matches_the_pre_registration() -> None:
    """The whole window, from the DB, against the values section D.3 registered in advance.

    A failure here is not a bug in this script: it means the coverage of the simulated period
    moved (a backfill, a re-import), and section D.3 requires the rule to be re-examined with a
    human re-submission **before** the campaign — never after.
    """
    import asyncio

    from dotenv import load_dotenv

    load_dotenv(rc.PROJECT_ROOT / ".env")

    async def _run() -> dict[str, list[tuple[datetime, int]]]:
        settings = dc.Settings()
        db_manager = dc.DatabaseManager()
        await db_manager.init_db(settings)
        try:
            return {
                pair: await dc.fetch_rows(db_manager, pair) for pair in ("BTC/USDC", "SOL/USDC")
            }
        finally:
            await db_manager.close_db()

    measured = {pair: dc.measure_pair(rows) for pair, rows in asyncio.run(_run()).items()}

    btc = measured["BTC/USDC"]
    assert btc["days_5m"] == 1096
    assert btc["days_5m_complete"] == 1096
    assert btc["days_4h"] == 1096
    assert btc["max_gap_days"] == 0
    assert btc["first_covered_day"] == "2023-04-01"
    assert btc["admissible"] is True
    assert btc["counts_by_interval"] == BTC_DB_COUNTS

    sol = measured["SOL/USDC"]
    assert sol["days_5m"] == SOL_COVERED_DAYS
    assert sol["max_gap_days"] == SOL_GAP_DAYS
    assert sol["first_covered_day"] == SOL_FIRST_DAY.isoformat()
    assert sol["admissible"] is False
    assert sol["counts_by_interval"] == SOL_DB_COUNTS

    # The two weekly candles section D.1 announces, on BOTH pairs, as end stamps.
    expected_missing = [s.isoformat() for s in MISSING_WEEK_END_STAMPS]
    assert btc["missing_1w_stamps"] == expected_missing
    assert sol["missing_1w_stamps"][-2:] == expected_missing

    # The synthetic fixtures above are a faithful rebuild, field for field.
    assert measured["BTC/USDC"] == dc.measure_pair(_full_pair())
    assert measured["SOL/USDC"] == dc.measure_pair(_sol_like())
