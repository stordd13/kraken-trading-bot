"""Pure-logic tests for scripts/audit/b4_stamp_lib.py (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

from b4_stamp_lib import (  # noqa: E402
    BoundaryManifest,
    LedgerEntry,
    SeriesBoundary,
    SeriesTally,
    WindowVote,
    append_ledger,
    assess_votes,
    compare_tally,
    done_windows,
    find_switch,
    read_ledger,
    refine_boundary,
    restamp_windows,
    shifted_gaps,
    summarize_votes,
)

T0 = datetime(2025, 6, 30, tzinfo=UTC)
WEEK = timedelta(days=7)


def _votes(pattern: str) -> list[WindowVote]:
    out = []
    for i, ch in enumerate(pattern):
        n_open, n_end = {"o": (90, 10), "e": (10, 90), "t": (50, 50)}[ch]
        out.append(WindowVote(T0 + WEEK * i, n_open, n_end, 0))
    return out


class TestVotes:
    def test_verdict(self) -> None:
        assert WindowVote(T0, 3, 1).verdict == "open"
        assert WindowVote(T0, 1, 3).verdict == "end"
        assert WindowVote(T0, 2, 2, 5).verdict == "tie"
        assert WindowVote(T0, 2, 2, 5).total == 9

    def test_summary(self) -> None:
        assert summarize_votes(_votes("ooeet")) == {"open": 2, "end": 2, "tie": 1}

    def test_find_switch_all_open(self) -> None:
        last_open, first_end = find_switch(_votes("oooo"))
        assert last_open is not None and last_open.window_start == T0 + WEEK * 3
        assert first_end is None

    def test_find_switch_middle(self) -> None:
        last_open, first_end = find_switch(_votes("ooeee"))
        assert last_open is not None and last_open.window_start == T0 + WEEK
        assert first_end is not None and first_end.window_start == T0 + WEEK * 2

    def test_find_switch_ignores_unsorted_input_and_earlier_end(self) -> None:
        votes = list(reversed(_votes("eooe")))  # an early 'end' week is noise, not a switch
        last_open, first_end = find_switch(votes)
        assert last_open is not None and last_open.window_start == T0 + WEEK * 2
        assert first_end is not None and first_end.window_start == T0 + WEEK * 3

    def test_assess_votes(self) -> None:
        assert assess_votes(_votes("oooo"), "open") == []
        # single-row windows flipping on the exchange spread are not decisive
        noisy = _votes("ooo") + [WindowVote(T0 + WEEK * 3, 0, 1, 0)]
        assert assess_votes(noisy, "open") == []
        # a full-size window against the expectation is decisive
        assert any("decisive" in p for p in assess_votes(_votes("ooe"), "open"))
        # row majority must agree with the expectation
        assert any("majority" in p for p in assess_votes(_votes("ee"), "open"))
        assert assess_votes([], "end") == ["no window to classify"]
        assert assess_votes(_votes("eee"), "end") == []

    def test_assess_votes_strict_post_migration(self) -> None:
        # GATE 1 decision a: after the migration a single residual window (even 1 row) is a STOP
        noisy = _votes("eee") + [WindowVote(T0 + WEEK * 3, 1, 0, 0)]
        assert assess_votes(noisy, "end") == []
        problems = assess_votes(noisy, "end", strict=True)
        assert len(problems) == 1 and "residual" in problems[0]
        tie = _votes("eee") + [WindowVote(T0 + WEEK * 3, 0, 0, 1)]
        assert any("residual" in p for p in assess_votes(tie, "end", strict=True))
        assert assess_votes(_votes("eeee"), "end", strict=True) == []

    def test_find_switch_no_open(self) -> None:
        last_open, first_end = find_switch(_votes("ee"))
        assert last_open is None and first_end is not None


class TestRefineBoundary:
    def _rows(self, pattern: str) -> list[tuple[datetime, str]]:
        m = {"o": "open", "e": "end", "t": "tie"}
        return [(T0 + timedelta(hours=i), m[ch]) for i, ch in enumerate(pattern)]

    def test_all_open(self) -> None:
        assert refine_boundary(self._rows("oooo")) is None

    def test_first_run_of_end(self) -> None:
        # noise 'e' at index 2 is not a run of 3; the run starts at index 5 → boundary = index 4
        assert refine_boundary(self._rows("ooeooeee")) == T0 + timedelta(hours=4)

    def test_tie_does_not_break_run(self) -> None:
        assert refine_boundary(self._rows("ooetee")) == T0 + timedelta(hours=1)

    def test_run_at_start(self) -> None:
        assert refine_boundary(self._rows("eeeo")) is None


class TestRestampWindows:
    def test_descending_and_covering(self) -> None:
        min_ts = datetime(2021, 1, 1, tzinfo=UTC)
        boundary = datetime(2021, 1, 1, 10, 30, tzinfo=UTC)  # 631 candles of 1m
        w = restamp_windows(min_ts, boundary, 1, 100)
        assert len(w) == 7
        assert w[0] == (datetime(2021, 1, 1, 8, 51, tzinfo=UTC), boundary + timedelta(minutes=1))
        assert w[-1] == (min_ts, datetime(2021, 1, 1, 0, 31, tzinfo=UTC))
        for (s1, e1), (s2, e2) in zip(w, w[1:], strict=False):
            assert e2 == s1 and s1 < e1 and s2 < e2  # contiguous, newest first
        assert all((e - s) <= timedelta(minutes=100) for s, e in w)

    def test_single_window(self) -> None:
        min_ts = datetime(2021, 1, 4, tzinfo=UTC)
        boundary = datetime(2026, 3, 30, tzinfo=UTC)
        w = restamp_windows(min_ts, boundary, 10080, 4000)
        assert w == [(min_ts, boundary + timedelta(minutes=10080))]

    def test_weekly_grid_monday_anchored(self) -> None:
        min_ts = datetime(2021, 1, 4, tzinfo=UTC)  # Monday
        boundary = datetime(2021, 3, 1, tzinfo=UTC)  # Monday, 9 weeks
        w = restamp_windows(min_ts, boundary, 10080, 4)
        assert [s.weekday() for s, _ in w] == [0, 0, 0]
        assert w[-1][0] == min_ts

    def test_empty_and_invalid(self) -> None:
        assert restamp_windows(T0, T0 - WEEK, 1, 10) == []
        with pytest.raises(ValueError):
            restamp_windows(T0, T0, 1, 0)


def _series() -> SeriesBoundary:
    return SeriesBoundary(
        pair="BTC/USDC",
        interval=60,
        rows=100,
        min_ts=datetime(2021, 1, 1, tzinfo=UTC),
        max_ts=datetime(2021, 1, 5, 3, tzinfo=UTC),
        last_open_stamped_ts=datetime(2021, 1, 5, 3, tzinfo=UTC),
        first_end_stamped_ts=None,
        expected_restamps=100,
        expected_collisions=0,
        gaps=[(datetime(2021, 1, 2, tzinfo=UTC), datetime(2021, 1, 2, 5, tzinfo=UTC))],
        dup_signature_volume_gt0=2,
        window_verdicts={"open": 1, "end": 0, "tie": 0},
        recheck_rows=[datetime(2021, 1, 3, 5, tzinfo=UTC)],
    )


class TestManifest:
    def test_round_trip(self, tmp_path: Path) -> None:
        m = BoundaryManifest(
            generated_at=T0,
            method="test",
            exchange="binance",
            reference_exchange="bybit",
            db_totals={"binance": 100, "bybit": 5},
            series=[_series()],
        )
        p = tmp_path / "m.json"
        m.dump(p)
        back = BoundaryManifest.load(p)
        assert back.generated_at == T0 and back.db_totals == {"binance": 100, "bybit": 5}
        s = back.get("BTC/USDC", 60)
        assert s is not None and s.to_json() == _series().to_json()
        assert s.expected_rows_after == 100 and s.key == "BTC/USDC:60"
        assert back.get("ETH/USDC", 60) is None
        assert back.total_restamps == 100 and back.total_collisions == 0

    def test_shifted_gaps(self) -> None:
        s = _series()
        assert shifted_gaps(s.gaps, 60) == [
            (datetime(2021, 1, 2, 1, tzinfo=UTC), datetime(2021, 1, 2, 6, tzinfo=UTC))
        ]


class TestLedger:
    def _entry(self, start: datetime, dry_run: bool = False) -> LedgerEntry:
        return LedgerEntry("BTC/USDC", 60, start, start + WEEK, 10, 10, 10, 0, 0.5, dry_run)

    def test_append_read_done(self, tmp_path: Path) -> None:
        p = tmp_path / "ledger.jsonl"
        assert read_ledger(p) == []
        append_ledger(p, self._entry(T0))
        append_ledger(p, self._entry(T0 + WEEK, dry_run=True))
        entries = read_ledger(p)
        assert len(entries) == 2 and entries[0] == self._entry(T0)
        assert done_windows(entries) == {("BTC/USDC", 60, T0.isoformat(), (T0 + WEEK).isoformat())}

    def test_tally_and_compare(self) -> None:
        t = SeriesTally("BTC/USDC", 60)
        t.add(LedgerEntry("BTC/USDC", 60, T0, T0 + WEEK, 60, 60, 60, 0, 1.0, False))
        t.add(LedgerEntry("BTC/USDC", 60, T0 - WEEK, T0, 40, 40, 40, 0, 1.0, False))
        assert t.windows == 2 and t.staged == 100
        assert compare_tally(t, _series()) == []
        t.collisions = 1
        t.inserted = 99
        problems = compare_tally(t, _series())
        assert any("collisions 1 != audit 0" in p for p in problems)
        t.staged = 99
        assert any("restamps 99 != audit 100" in p for p in compare_tally(t, _series()))


class TestResumePlan:
    def _plan(self):
        from b4_stamp_lib import restamp_windows

        return restamp_windows(T0, T0 + timedelta(hours=99), 60, 30)  # 4 windows, newest first

    def _done(self, *idx: int, max_rows: int = 30, boundary=None, gen=T0) -> list[LedgerEntry]:
        from b4_stamp_lib import check_resume_plan  # noqa: F401 (import smoke)

        plan = self._plan()
        b = boundary or T0 + timedelta(hours=99)
        return [
            LedgerEntry("BTC/USDC", 60, *plan[i], 30, 30, 30, 0, 1.0, False, max_rows, b, gen)
            for i in idx
        ]

    def test_prefix_ok(self) -> None:
        from b4_stamp_lib import check_resume_plan, remaining_region_end

        plan = self._plan()
        b = T0 + timedelta(hours=99)
        assert check_resume_plan(plan, [], 30, b, T0) == []
        assert check_resume_plan(plan, self._done(0), 30, b, T0) == []
        assert check_resume_plan(plan, self._done(0, 1), 30, b, T0) == []
        assert remaining_region_end(plan, 0) == b + timedelta(hours=1)
        assert remaining_region_end(plan, 2) == plan[1][0]
        assert remaining_region_end(plan, 4) is None

    def test_plan_identity_mismatch(self) -> None:
        from b4_stamp_lib import check_resume_plan

        plan = self._plan()
        b = T0 + timedelta(hours=99)
        assert any(
            "max_rows" in p for p in check_resume_plan(plan, self._done(0, max_rows=20), 30, b, T0)
        )
        assert any(
            "boundary" in p for p in check_resume_plan(plan, self._done(0, boundary=T0), 30, b, T0)
        )
        assert any(
            "manifest" in p
            for p in check_resume_plan(plan, self._done(0, gen=T0 + WEEK), 30, b, T0)
        )

    def test_non_prefix_and_duplicates(self) -> None:
        from b4_stamp_lib import check_resume_plan

        plan = self._plan()
        b = T0 + timedelta(hours=99)
        assert any("prefix" in p for p in check_resume_plan(plan, self._done(1), 30, b, T0))
        assert any("prefix" in p for p in check_resume_plan(plan, self._done(0, 2), 30, b, T0))
        assert any("duplicate" in p for p in check_resume_plan(plan, self._done(0, 0), 30, b, T0))
