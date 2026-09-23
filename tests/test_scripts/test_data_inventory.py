"""Tests of ``scripts/audit/data_inventory.py`` — the pure layer, adverse first.

Every function under test is pure (no DB, no clock, no network), so the cases are synthetic
stamp lists. Each test was written with its adverse case and observed **red** against a tree that
does not implement the module (agent rule 1, ``CLAUDE.md``): a green-at-birth test proves nothing.

The expected values are derived from the brief's text, never from the implementation:

* a hole is the pair (last stamp present, first stamp after) and carries ``missing =
  (next − prev) / step − 1`` candles — brief § « Les cinq faits », fact 1; its duration is the
  candle-free interval ``next − prev − step`` = ``missing × step`` (period-end stamps: the candle
  stamped ``next`` covers ``(next − step, next]``, ``PROJECT_CONTEXT.md`` § 6);
* the C2 warmup rule tolerates ``largest_gap_candles ≤ 1``: a hole of exactly **one** candle does
  not break a warmup, a hole of **two** does — brief fact 5 (« un trou d'une seule candle ne
  casse pas »), ``scripts/backtest.py`` ``_WARMUP_GAP_TOLERANCE = 1``;
* the earliest admissible window start after a blocking hole is
  ``S = first stamp after the hole + (required − 1) × interval`` when the ``required`` candles
  that follow are contiguous — brief fact 5;
* the weekly series steps by **7 days**, Monday-anchored at 00:00 UTC — brief § « Accès DB ».

The grid helpers (``WEEK_MINUTES``, ``longest_missing_run``, ``expected_candles``) must be the
``c3_common`` objects themselves, imported and not copied — pinned by identity.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

import c3_common as c3
import data_inventory as di

DAY = timedelta(days=1)
WEEK = timedelta(days=7)
H4 = timedelta(hours=4)
M5 = timedelta(minutes=5)

#: A Monday 00:00 UTC (2022-10-03 is a Monday).
MONDAY = datetime(2022, 10, 3, tzinfo=UTC)
T0 = datetime(2022, 10, 1, tzinfo=UTC)


def _grid(start: datetime, n: int, step: timedelta) -> list[datetime]:
    return [start + k * step for k in range(n)]


# ---------------------------------------------------------------------------
# Reuse by import, pinned by identity (brief: « réutiliser par import, jamais par copie »)
# ---------------------------------------------------------------------------


def test_grid_helpers_are_the_c3_common_objects() -> None:
    assert di.WEEK_MINUTES is c3.WEEK_MINUTES
    assert di.longest_missing_run is c3.longest_missing_run
    assert di.expected_candles is c3.expected_candles


def test_step_of_weekly_is_seven_days_not_a_minute_count() -> None:
    """Brief § « Accès DB » : 1 w = pas de 7 jours ancré au lundi, pas 7 × 1440 en arithmétique naïve."""
    assert di.step_of(di.WEEK_MINUTES) == WEEK
    assert di.step_of(1440) == DAY
    assert di.step_of(5) == M5


def test_warmup_gap_tolerance_is_the_c2_engine_value() -> None:
    """Fact 5 quotes the C2 rule ``largest_gap_candles ≤ 1`` (``scripts/backtest.py:309``)."""
    assert di.WARMUP_GAP_TOLERANCE == 1


# ---------------------------------------------------------------------------
# Holes from a list of stamps — the Python image of the SQL LAG
# ---------------------------------------------------------------------------


def test_one_missing_candle_is_a_hole_of_one_and_is_tolerated() -> None:
    """Fact 5: a hole of exactly one candle does not break a warmup."""
    stamps = _grid(T0, 3, DAY) + _grid(T0 + 4 * DAY, 3, DAY)  # T0+3d absent
    holes = di.holes_from_stamps(stamps, 1440)
    assert holes == [(T0 + 2 * DAY, T0 + 4 * DAY)]
    described = di.describe_hole(T0 + 2 * DAY, T0 + 4 * DAY, 1440)
    assert described["missing"] == 1
    assert described["days"] == 1.0
    assert di.is_blocking(described) is False


def test_two_missing_candles_is_a_blocking_hole() -> None:
    stamps = _grid(T0, 3, DAY) + _grid(T0 + 5 * DAY, 3, DAY)  # T0+3d and T0+4d absent
    holes = di.holes_from_stamps(stamps, 1440)
    assert holes == [(T0 + 2 * DAY, T0 + 5 * DAY)]
    described = di.describe_hole(T0 + 2 * DAY, T0 + 5 * DAY, 1440)
    assert described["missing"] == 2
    assert described["days"] == 2.0
    assert di.is_blocking(described) is True


def test_a_contiguous_series_has_no_hole() -> None:
    assert di.holes_from_stamps(_grid(T0, 10, H4), 240) == []


def test_empty_and_singleton_series_have_no_hole() -> None:
    assert di.holes_from_stamps([], 5) == []
    assert di.holes_from_stamps([T0], 5) == []


def test_unsorted_input_is_sorted_before_lagging() -> None:
    """The SQL orders by timestamp; a Python caller handing an unsorted list must get the same."""
    stamps = [T0 + 2 * DAY, T0, T0 + 5 * DAY, T0 + 1 * DAY]
    assert di.holes_from_stamps(stamps, 1440) == [(T0 + 2 * DAY, T0 + 5 * DAY)]


def test_edge_hole_between_first_and_second_stamp_is_reported() -> None:
    """A hole at the border of the series is a hole like any other (c3 review R3, 2nd pass)."""
    stamps = [T0, T0 + 3 * DAY, T0 + 4 * DAY]
    assert di.holes_from_stamps(stamps, 1440) == [(T0, T0 + 3 * DAY)]


def test_weekly_holes_step_by_seven_days() -> None:
    """Two consecutive Mondays absent → ``missing == 2``, ``days == 14``."""
    mondays = _grid(MONDAY, 3, WEEK) + _grid(MONDAY + 5 * WEEK, 2, WEEK)
    holes = di.holes_from_stamps(mondays, di.WEEK_MINUTES)
    assert holes == [(MONDAY + 2 * WEEK, MONDAY + 5 * WEEK)]
    described = di.describe_hole(MONDAY + 2 * WEEK, MONDAY + 5 * WEEK, di.WEEK_MINUTES)
    assert described["missing"] == 2
    assert described["days"] == 14.0
    assert described["on_grid"] is True


def test_weekly_stamp_off_monday_is_off_grid() -> None:
    """The weekly grid is Monday 00:00 UTC: a Thursday stamp is not on it."""
    thursday = MONDAY + 3 * DAY
    described = di.describe_hole(thursday, thursday + 2 * WEEK, di.WEEK_MINUTES)
    assert described["on_grid"] is False
    assert di.is_on_grid(MONDAY, di.WEEK_MINUTES) is True
    assert di.is_on_grid(thursday, di.WEEK_MINUTES) is False


def test_non_multiple_delta_has_no_missing_count() -> None:
    """A 4 h series whose two stamps are 6 h apart is off-grid: no candle count can be derived.

    The candle-free interval is still ``end − start − step`` = 2 h (the candle stamped ``end``
    covers ``(end − 4 h, end]``); the raw distance is ``span_days`` = 6 h.
    """
    described = di.describe_hole(T0, T0 + timedelta(hours=6), 240)
    assert described["missing"] is None
    assert described["on_grid"] is False
    assert described["days"] == round(2 / 24, 6)
    assert described["span_days"] == 0.25


def test_naive_timestamp_is_a_defect() -> None:
    with pytest.raises(ValueError):
        di.holes_from_stamps([datetime(2022, 10, 1), datetime(2022, 10, 2)], 1440)


def test_holes_agree_with_longest_missing_run_of_c3_common() -> None:
    """The largest hole equals the longest run of missing grid stamps counted by c3_common."""
    stamps = _grid(T0, 4, H4) + _grid(T0 + 7 * H4, 2, H4) + _grid(T0 + 10 * H4, 3, H4)
    holes = [di.describe_hole(a, b, 240) for a, b in di.holes_from_stamps(stamps, 240)]
    missing_stamps = di.missing_stamps_of(holes, 240)
    assert sorted(missing_stamps) == [T0 + 4 * H4, T0 + 5 * H4, T0 + 6 * H4, T0 + 9 * H4]
    assert c3.longest_missing_run(missing_stamps, 240) == max(h["missing"] for h in holes) == 3


# ---------------------------------------------------------------------------
# Grid counts — expected candles on [first, last]
# ---------------------------------------------------------------------------


def test_grid_count_closed_counts_both_ends() -> None:
    """``[first, last]`` on a daily grid of 10 stamps counts 10 (``(first, last]`` counts 9)."""
    first, last = T0, T0 + 9 * DAY
    assert c3.expected_candles(first, last, 1440) == 9
    assert di.grid_count_closed(first, last, 1440) == 10


def test_grid_count_closed_weekly_is_monday_anchored() -> None:
    assert di.grid_count_closed(MONDAY, MONDAY + 4 * WEEK, di.WEEK_MINUTES) == 5
    # a start that is not a Monday does not count itself
    assert di.grid_count_closed(MONDAY + DAY, MONDAY + 4 * WEEK, di.WEEK_MINUTES) == 4


def test_series_summary_missing_is_expected_minus_count() -> None:
    stamps = _grid(T0, 3, DAY) + _grid(T0 + 5 * DAY, 3, DAY)
    holes = [di.describe_hole(a, b, 1440) for a, b in di.holes_from_stamps(stamps, 1440)]
    summary = di.series_summary(
        first=stamps[0], last=stamps[-1], count=6, holes=holes, interval=1440
    )
    assert summary["expected"] == 8
    assert summary["missing"] == 2
    assert summary["holes_1"] == 0
    assert summary["holes_ge2"] == 1
    assert summary["largest_missing_run"] == 2


# ---------------------------------------------------------------------------
# Earliest admissible window start after a hole (fact 5)
# ---------------------------------------------------------------------------


def _holes(stamps: list[datetime], interval: int) -> list[dict]:
    return [di.describe_hole(a, b, interval) for a, b in di.holes_from_stamps(stamps, interval)]


def test_admissible_start_is_first_after_plus_required_minus_one_steps() -> None:
    """Brief fact 5: ``S = premier stamp après le trou + (required − 1) × intervalle``."""
    after = T0 + 10 * DAY
    stamps = _grid(T0, 3, DAY) + _grid(after, 300, DAY)
    holes = _holes(stamps, 1440)
    assert len(holes) == 1 and holes[0]["missing"] == 7
    starts = di.admissible_starts(holes, first=stamps[0], last=stamps[-1], interval=1440)
    assert starts[0] == {
        "14": after + 13 * DAY,
        "50": after + 49 * DAY,
        "200": after + 199 * DAY,
    }


def test_admissible_start_weekly_uses_seven_day_steps() -> None:
    after = MONDAY + 30 * WEEK
    mondays = _grid(MONDAY, 2, WEEK) + _grid(after, 250, WEEK)
    holes = _holes(mondays, di.WEEK_MINUTES)
    starts = di.admissible_starts(
        holes, first=mondays[0], last=mondays[-1], interval=di.WEEK_MINUTES
    )
    assert starts[0]["14"] == after + 13 * WEEK
    assert starts[0]["200"] == after + 199 * WEEK


def test_required_beyond_series_length_has_no_admissible_start() -> None:
    """Brief: ``required > longueur`` — nothing after the hole can satisfy it."""
    after = T0 + 10 * DAY
    stamps = _grid(T0, 3, DAY) + _grid(after, 20, DAY)  # 20 candles follow the hole
    holes = _holes(stamps, 1440)
    starts = di.admissible_starts(holes, first=stamps[0], last=stamps[-1], interval=1440)
    assert starts[0]["14"] == after + 13 * DAY
    assert starts[0]["50"] is None
    assert starts[0]["200"] is None


def test_a_one_candle_hole_inside_the_warmup_shifts_the_start_by_one_step() -> None:
    """Tolerated hole: the count of *loaded* candles must still reach ``required``, so the
    start moves one step later — it does not restart after the tolerated hole."""
    after = T0 + 10 * DAY
    tail = _grid(after, 5, DAY) + _grid(after + 6 * DAY, 100, DAY)  # after+5d absent (1 candle)
    stamps = _grid(T0, 3, DAY) + tail
    holes = _holes(stamps, 1440)
    assert [h["missing"] for h in holes] == [7, 1]
    starts = di.admissible_starts(holes, first=stamps[0], last=stamps[-1], interval=1440)
    # 14 loaded candles: 5 before the one-candle hole, 9 after → stamp after + 6d + 8d
    assert starts[0]["14"] == after + 6 * DAY + 8 * DAY
    assert starts[0]["14"] == after + 14 * DAY  # one step later than the contiguous formula


def test_a_two_candle_hole_inside_the_warmup_restarts_the_count_after_it() -> None:
    """Blocking hole: the ``required`` candles must follow the *later* hole."""
    after = T0 + 10 * DAY
    later = after + 7 * DAY  # after+5d, after+6d absent (2 candles)
    stamps = _grid(T0, 3, DAY) + _grid(after, 5, DAY) + _grid(later, 100, DAY)
    holes = _holes(stamps, 1440)
    assert [h["missing"] for h in holes] == [7, 2]
    starts = di.admissible_starts(holes, first=stamps[0], last=stamps[-1], interval=1440)
    assert starts[0]["14"] == later + 13 * DAY
    assert starts[1]["14"] == later + 13 * DAY
    assert starts[0]["50"] == later + 49 * DAY


def test_a_blocking_hole_at_the_very_end_has_no_admissible_start() -> None:
    """Edge hole: fewer than ``required`` candles remain after it."""
    stamps = _grid(T0, 100, DAY) + _grid(T0 + 105 * DAY, 3, DAY)
    holes = _holes(stamps, 1440)
    starts = di.admissible_starts(holes, first=stamps[0], last=stamps[-1], interval=1440)
    assert starts[0] == {"14": None, "50": None, "200": None}


def test_admissible_starts_of_an_empty_hole_list_is_empty() -> None:
    assert di.admissible_starts([], first=None, last=None, interval=1440) == []


def test_off_grid_hole_yields_no_admissible_start() -> None:
    holes = [di.describe_hole(T0, T0 + timedelta(hours=6), 240)]
    starts = di.admissible_starts(holes, first=T0, last=T0 + 100 * H4, interval=240)
    assert starts[0] == {"14": None, "50": None, "200": None}


# ---------------------------------------------------------------------------
# The USDC hole — one hole per series, and the cross-timeframe comparison (fact 2)
# ---------------------------------------------------------------------------


def test_usdc_hole_is_the_largest_hole_intersecting_the_zoom() -> None:
    zoom_start, zoom_end = datetime(2022, 1, 1, tzinfo=UTC), datetime(2023, 7, 1, tzinfo=UTC)
    inside = di.describe_hole(
        datetime(2022, 10, 5, tzinfo=UTC), datetime(2023, 3, 17, tzinfo=UTC), 1440
    )
    small = di.describe_hole(
        datetime(2022, 3, 1, tzinfo=UTC), datetime(2022, 3, 4, tzinfo=UTC), 1440
    )
    outside = di.describe_hole(
        datetime(2024, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC), 1440
    )
    assert di.usdc_hole([small, outside, inside], zoom_start, zoom_end) is inside
    assert di.usdc_hole([outside], zoom_start, zoom_end) is None
    assert di.usdc_hole([], zoom_start, zoom_end) is None


def test_usdc_hole_straddling_the_zoom_end_still_intersects() -> None:
    """SOL-like: the hole starts inside the zoom and ends long after it."""
    zoom_start, zoom_end = datetime(2022, 1, 1, tzinfo=UTC), datetime(2023, 7, 1, tzinfo=UTC)
    straddling = di.describe_hole(
        datetime(2022, 10, 5, tzinfo=UTC), datetime(2023, 12, 28, tzinfo=UTC), 1440
    )
    assert di.usdc_hole([straddling], zoom_start, zoom_end) is straddling


def test_same_event_within_one_own_interval_of_the_reference() -> None:
    """Fact 2: same bounds « à un intervalle près » — the tolerance is the timeframe's own step."""
    ref = di.describe_hole(
        datetime(2022, 10, 5, 3, 1, tzinfo=UTC), datetime(2023, 3, 17, 0, 1, tzinfo=UTC), 1
    )
    daily = di.describe_hole(
        datetime(2022, 10, 5, tzinfo=UTC), datetime(2023, 3, 18, tzinfo=UTC), 1440
    )
    weekly = di.describe_hole(
        datetime(2022, 10, 3, tzinfo=UTC), datetime(2023, 3, 20, tzinfo=UTC), 10080
    )
    assert di.same_event(daily, ref, 1440)["same_event"] is True
    assert di.same_event(weekly, ref, 10080)["same_event"] is True
    far = di.describe_hole(
        datetime(2022, 10, 5, tzinfo=UTC), datetime(2023, 3, 20, tzinfo=UTC), 1440
    )
    verdict = di.same_event(far, ref, 1440)
    assert verdict["same_event"] is False
    assert verdict["delta_after_minutes"] == 3 * 1440 - 1


# ---------------------------------------------------------------------------
# Determinism of the artifact
# ---------------------------------------------------------------------------


def test_build_artifact_is_deterministic_for_the_same_inputs() -> None:
    now = datetime(2026, 9, 22, 21, tzinfo=UTC)
    stamps = _grid(T0, 3, DAY) + _grid(T0 + 200 * DAY, 300, DAY)
    series = [
        {
            "exchange": "binance",
            "pair": "BTC/USDC",
            "interval": 1440,
            "first": stamps[0],
            "last": stamps[-1],
            "count": len(stamps),
            "holes": di.holes_from_stamps(stamps, 1440),
            "count_2022_2023": 0,
            "first_2022_2023": None,
            "last_2022_2023": None,
        }
    ]
    a = di.build_artifact(series, generated_at=now, vision=None)
    b = di.build_artifact(series, generated_at=now, vision=None)
    assert a == b
    assert a["generated_at"] == "2026-09-22T21:00:00+00:00"
    assert a["fact4_vision"]["skipped"] is True
