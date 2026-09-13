"""Pure helpers for the B4.1 Binance timestamp audit and re-stamp (no I/O, no DB).

Shared by ``b4_timestamp_audit.py`` (read-only classification) and
``b4_restamp_binance.py`` (migration).  Everything that can be unit-tested
without a database lives here: window votes, boundary detection, the boundary
manifest (JSON source of truth of the migration perimeter), window generation
for the migration and the resume ledger.

Conventions
-----------
* ``interval`` is in minutes (DB column), ``step = timedelta(minutes=interval)``.
* An *open-stamped* row has ``timestamp = open_time``; an *end-stamped* row has
  ``timestamp = open_time + interval`` (the project standard, see
  ``krakenbot.data.backfill``).  Re-stamping = ``timestamp := timestamp + step``.
* A "window vote" compares Binance closes with the reference exchange (Bybit)
  closes: if the closest Bybit close sits at ``T + interval`` the Binance row is
  open-stamped, if it sits at ``T`` it is end-stamped.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Literal

from krakenbot.data.backfill import floor_to_grid

PAIRS: list[str] = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
INTERVALS: list[int] = [1, 5, 15, 60, 240, 1440, 10080]
INTERVAL_LABEL: dict[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
    10080: "1w",
}
#: The only exchange whose rows this tooling may ever read for re-stamp / write.
TARGET_EXCHANGE = "binance"
#: Weekly candles open Monday 00:00 UTC; epoch 0 is Thursday → +4 days (see backfill._WEEK_ANCHOR_S).
WEEK_ANCHOR_S = 4 * 86_400

Verdict = Literal["open", "end", "tie"]


def label(interval: int) -> str:
    return INTERVAL_LABEL.get(interval, f"{interval}m")


def grid_anchor_seconds(interval: int) -> int:
    """Epoch offset of the candle grid (Monday anchoring for 1w, 0 otherwise)."""
    return WEEK_ANCHOR_S if interval == 10080 else 0


def _iso(ts: datetime | None) -> str | None:
    return None if ts is None else ts.astimezone(UTC).isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    ts = datetime.fromisoformat(value)
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


# ---------------------------------------------------------------------------
# Classification: window votes and boundary detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WindowVote:
    """Row votes aggregated over one time window (e.g. one ISO week)."""

    window_start: datetime
    n_open: int
    n_end: int
    n_tie: int = 0

    @property
    def total(self) -> int:
        return self.n_open + self.n_end + self.n_tie

    @property
    def verdict(self) -> Verdict:
        if self.n_open > self.n_end:
            return "open"
        if self.n_end > self.n_open:
            return "end"
        return "tie"


def summarize_votes(votes: Iterable[WindowVote]) -> dict[str, int]:
    """Number of windows per verdict (``{"open": .., "end": .., "tie": ..}``)."""
    out = {"open": 0, "end": 0, "tie": 0}
    for v in votes:
        out[v.verdict] += 1
    return out


def assess_votes(
    votes: Sequence[WindowVote], expect: Verdict, min_rows: int = 3, strict: bool = False
) -> list[str]:
    """Problems that make the series inconsistent with the ``expect`` convention.

    Pre-migration (``strict=False``): a window whose verdict differs from
    ``expect`` is only *decisive* when it holds at least ``min_rows`` voting
    rows — single-row windows (1w) flip on the exchange spread whenever two
    consecutive closes are nearly equal.  Post-migration (``strict=True``,
    GATE 1 decision a): **every** window must vote ``expect``, whatever its
    size; a single residual window is a STOP.  In both modes the row-level
    majority over the whole overlap must agree with ``expect``.
    """
    problems: list[str] = []
    if not votes:
        return ["no window to classify"]
    rows_open = sum(v.n_open for v in votes)
    rows_end = sum(v.n_end for v in votes)
    majority: Verdict = "open" if rows_open > rows_end else "end" if rows_end > rows_open else "tie"
    if majority != expect:
        problems.append(f"row majority is '{majority}' (open={rows_open} end={rows_end})")
    offending = [v for v in votes if v.verdict != expect and (strict or v.total >= min_rows)]
    if offending:
        problems.append(
            f"{len(offending)} {'residual' if strict else 'decisive'} window(s) vote against "
            f"'{expect}': "
            + ", ".join(
                f"{v.window_start.date()}({v.n_open}/{v.n_end}/{v.n_tie})" for v in offending
            )
        )
    return problems


def find_switch(votes: Sequence[WindowVote]) -> tuple[WindowVote | None, WindowVote | None]:
    """Locate the open→end switch in chronologically sorted window votes.

    Returns ``(last_open_window, first_end_window_after_it)``.  When every
    window votes open the second element is ``None`` (no switch: the whole
    series is open-stamped); when no window votes open the first is ``None``.
    """
    ordered = sorted(votes, key=lambda v: v.window_start)
    last_open = None
    for v in ordered:
        if v.verdict == "open":
            last_open = v
    first_end = None
    for v in ordered:
        if v.verdict == "end" and (last_open is None or v.window_start > last_open.window_start):
            first_end = v
            break
    return last_open, first_end


def refine_boundary(
    row_votes: Sequence[tuple[datetime, Verdict]], min_run: int = 3
) -> datetime | None:
    """Exact last open-stamped timestamp from per-row votes sorted by timestamp.

    The boundary is the last row *before* the first run of at least ``min_run``
    consecutive ``"end"`` votes (ties do not break a run).  Returns ``None``
    when no such run exists (the rows are entirely open-stamped).
    """
    run = 0
    run_start_idx = -1
    for idx, (_, vote) in enumerate(row_votes):
        if vote == "end":
            if run == 0:
                run_start_idx = idx
            run += 1
            if run >= min_run:
                return row_votes[run_start_idx - 1][0] if run_start_idx > 0 else None
        elif vote == "open":
            run = 0
    return None


# ---------------------------------------------------------------------------
# Boundary manifest (JSON source of truth of the migration perimeter)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SeriesBoundary:
    """Audit result for one ``(pair, interval)`` series of the target exchange."""

    pair: str
    interval: int
    rows: int
    min_ts: datetime
    max_ts: datetime
    #: Last open-stamped timestamp = upper bound (inclusive) of the migration perimeter.
    last_open_stamped_ts: datetime | None
    #: First end-stamped timestamp found after the boundary, if any.
    first_end_stamped_ts: datetime | None
    expected_restamps: int
    expected_collisions: int
    #: ``(prev, next)`` LAG pairs around each internal gap (original timestamps).
    gaps: list[tuple[datetime, datetime]] = field(default_factory=list)
    #: Consecutive ``(T, T+interval)`` rows with identical OHLCV and volume > 0.
    dup_signature_volume_gt0: int = 0
    window_verdicts: dict[str, int] = field(default_factory=dict)
    #: Rows the close alone cannot classify before the migration (two candidate reference
    #: closes within 0.1 %, e.g. near-equal weekly closes) plus any row that voted against the
    #: expectation; the post-migration replay must find each of them voting *end* at ``T + interval``.
    recheck_rows: list[datetime] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.pair}:{self.interval}"

    @property
    def step(self) -> timedelta:
        return timedelta(minutes=self.interval)

    @property
    def expected_rows_after(self) -> int:
        return self.rows - self.expected_collisions

    def to_json(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "interval": self.interval,
            "label": label(self.interval),
            "rows": self.rows,
            "min_ts": _iso(self.min_ts),
            "max_ts": _iso(self.max_ts),
            "last_open_stamped_ts": _iso(self.last_open_stamped_ts),
            "first_end_stamped_ts": _iso(self.first_end_stamped_ts),
            "expected_restamps": self.expected_restamps,
            "expected_collisions": self.expected_collisions,
            "expected_rows_after": self.expected_rows_after,
            "gaps": [[_iso(p), _iso(n)] for p, n in self.gaps],
            "dup_signature_volume_gt0": self.dup_signature_volume_gt0,
            "window_verdicts": dict(self.window_verdicts),
            "recheck_rows": [_iso(t) for t in self.recheck_rows],
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> SeriesBoundary:
        return cls(
            pair=d["pair"],
            interval=int(d["interval"]),
            rows=int(d["rows"]),
            min_ts=_parse_ts(d["min_ts"]),  # type: ignore[arg-type]
            max_ts=_parse_ts(d["max_ts"]),  # type: ignore[arg-type]
            last_open_stamped_ts=_parse_ts(d.get("last_open_stamped_ts")),
            first_end_stamped_ts=_parse_ts(d.get("first_end_stamped_ts")),
            expected_restamps=int(d["expected_restamps"]),
            expected_collisions=int(d["expected_collisions"]),
            gaps=[(_parse_ts(p), _parse_ts(n)) for p, n in d.get("gaps", [])],  # type: ignore[misc]
            dup_signature_volume_gt0=int(d.get("dup_signature_volume_gt0", 0)),
            window_verdicts={k: int(v) for k, v in d.get("window_verdicts", {}).items()},
            recheck_rows=[_parse_ts(t) for t in d.get("recheck_rows", [])],  # type: ignore[misc]
        )


@dataclass(slots=True)
class BoundaryManifest:
    generated_at: datetime
    method: str
    exchange: str
    reference_exchange: str
    db_totals: dict[str, int]
    series: list[SeriesBoundary] = field(default_factory=list)

    def get(self, pair: str, interval: int) -> SeriesBoundary | None:
        for s in self.series:
            if s.pair == pair and s.interval == interval:
                return s
        return None

    @property
    def total_restamps(self) -> int:
        return sum(s.expected_restamps for s in self.series)

    @property
    def total_collisions(self) -> int:
        return sum(s.expected_collisions for s in self.series)

    def to_json(self) -> dict[str, Any]:
        return {
            "generated_at": _iso(self.generated_at),
            "method": self.method,
            "exchange": self.exchange,
            "reference_exchange": self.reference_exchange,
            "db_totals": dict(self.db_totals),
            "total_restamps": self.total_restamps,
            "total_collisions": self.total_collisions,
            "series": [s.to_json() for s in self.series],
        }

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> BoundaryManifest:
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            generated_at=_parse_ts(d["generated_at"]),  # type: ignore[arg-type]
            method=d["method"],
            exchange=d["exchange"],
            reference_exchange=d["reference_exchange"],
            db_totals={k: int(v) for k, v in d["db_totals"].items()},
            series=[SeriesBoundary.from_json(s) for s in d["series"]],
        )


def shifted_gaps(
    gaps: Iterable[tuple[datetime, datetime]], interval: int
) -> list[tuple[datetime, datetime]]:
    """The same LAG gaps expressed on re-stamped timestamps (both ends + interval)."""
    step = timedelta(minutes=interval)
    return [(p + step, n + step) for p, n in gaps]


# ---------------------------------------------------------------------------
# Migration: window generation (descending) and resume ledger
# ---------------------------------------------------------------------------


def restamp_windows(
    min_ts: datetime, boundary: datetime, interval: int, max_rows: int
) -> list[tuple[datetime, datetime]]:
    """Half-open ``[w_start, w_end)`` windows on *original* timestamps, newest first.

    Each window holds at most ``max_rows`` candles of ``interval`` minutes and
    is aligned on the candle grid.  Processing them from the newest to the
    oldest guarantees that the target timestamp ``T + interval`` of every row
    has already been vacated by the time it is needed (non-deferrable PK).
    The union of the windows covers exactly ``[min_ts, boundary]``.
    """
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    if boundary < min_ts:
        return []
    step = timedelta(minutes=interval)
    span = step * max_rows
    lower = floor_to_grid(min_ts, interval)
    w_end = floor_to_grid(boundary, interval) + step  # exclusive: includes the boundary row
    windows: list[tuple[datetime, datetime]] = []
    while w_end > lower:
        w_start = max(w_end - span, lower)
        windows.append((w_start, w_end))
        w_end = w_start
    return windows


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One processed window (DB progress row and JSONL mirror line)."""

    pair: str
    interval: int
    window_start: datetime
    window_end: datetime
    staged: int
    deleted: int
    inserted: int
    collisions: int
    seconds: float
    dry_run: bool
    #: Plan identity — a resume must run with the very same values (window grid).
    max_rows: int = 0
    boundary: datetime | None = None
    manifest_generated_at: datetime | None = None

    @property
    def window(self) -> tuple[datetime, datetime]:
        return (self.window_start, self.window_end)

    @property
    def window_key(self) -> tuple[str, int, str, str]:
        return (
            self.pair,
            self.interval,
            _iso(self.window_start) or "",
            _iso(self.window_end) or "",
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "interval": self.interval,
            "window_start": _iso(self.window_start),
            "window_end": _iso(self.window_end),
            "staged": self.staged,
            "deleted": self.deleted,
            "inserted": self.inserted,
            "collisions": self.collisions,
            "seconds": round(self.seconds, 3),
            "dry_run": self.dry_run,
            "max_rows": self.max_rows,
            "boundary": _iso(self.boundary),
            "manifest_generated_at": _iso(self.manifest_generated_at),
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> LedgerEntry:
        return cls(
            pair=d["pair"],
            interval=int(d["interval"]),
            window_start=_parse_ts(d["window_start"]),  # type: ignore[arg-type]
            window_end=_parse_ts(d["window_end"]),  # type: ignore[arg-type]
            staged=int(d["staged"]),
            deleted=int(d["deleted"]),
            inserted=int(d["inserted"]),
            collisions=int(d["collisions"]),
            seconds=float(d["seconds"]),
            dry_run=bool(d["dry_run"]),
            max_rows=int(d.get("max_rows", 0)),
            boundary=_parse_ts(d.get("boundary")),
            manifest_generated_at=_parse_ts(d.get("manifest_generated_at")),
        )


def check_resume_plan(
    plan: Sequence[tuple[datetime, datetime]],
    done: Sequence[LedgerEntry],
    max_rows: int,
    boundary: datetime,
    manifest_generated_at: datetime,
) -> list[str]:
    """Refuse a resume whose committed windows do not match the current plan.

    ``done`` are the windows already committed for one series (DB progress rows).
    They must carry the same plan identity (``max_rows``, ``boundary``, manifest)
    and form the newest-first **prefix** of ``plan`` — any other shape means the
    remaining original rows are not exactly ``[min_ts, w_start_of_last_done)``
    and re-running a window would shift already shifted rows.
    """
    problems: list[str] = []
    for e in done:
        if e.max_rows != max_rows:
            problems.append(
                f"window {e.window_start.isoformat()} was run with max_rows={e.max_rows}, now {max_rows}"
            )
        if e.boundary != boundary:
            problems.append(
                f"window {e.window_start.isoformat()} was run with boundary={e.boundary}, now {boundary}"
            )
        if e.manifest_generated_at != manifest_generated_at:
            problems.append(
                f"window {e.window_start.isoformat()} was run with manifest {e.manifest_generated_at}, "
                f"now {manifest_generated_at}"
            )
    done_windows_set = {e.window for e in done}
    if len(done_windows_set) != len(done):
        problems.append("duplicate progress rows for the same window")
    prefix = list(plan[: len(done_windows_set)])
    if set(prefix) != done_windows_set:
        unknown = sorted(done_windows_set - set(plan))
        problems.append(
            f"{len(done_windows_set)} committed window(s) are not the newest-first prefix of the plan"
            + (f" (unknown windows: {[w[0].isoformat() for w in unknown][:3]})" if unknown else "")
        )
    return problems


def remaining_region_end(plan: Sequence[tuple[datetime, datetime]], n_done: int) -> datetime | None:
    """Exclusive upper bound of the still-unprocessed original rows, ``None`` when all done.

    Before any window is processed every original row is ``< plan[0][1]``
    (= boundary + interval); after the newest ``n_done`` windows have been
    committed their rows sit at ``> plan[n_done-1][0]`` and the untouched
    originals are exactly those ``< plan[n_done-1][0]``.
    """
    if not plan or n_done >= len(plan):
        return None
    return plan[0][1] if n_done == 0 else plan[n_done - 1][0]


def read_ledger(path: Path) -> list[LedgerEntry]:
    """Committed windows recorded by a previous ``--execute`` run (JSONL, may not exist)."""
    if not path.exists():
        return []
    entries: list[LedgerEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(LedgerEntry.from_json(json.loads(line)))
    return entries


def append_ledger(path: Path, entry: LedgerEntry) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_json()) + "\n")


def done_windows(entries: Iterable[LedgerEntry]) -> set[tuple[str, int, str, str]]:
    """Keys of windows already executed for real (dry-run entries are ignored)."""
    return {e.window_key for e in entries if not e.dry_run}


@dataclass(slots=True)
class SeriesTally:
    """Per-series totals of a migration run, compared against the manifest."""

    pair: str
    interval: int
    windows: int = 0
    staged: int = 0
    deleted: int = 0
    inserted: int = 0
    collisions: int = 0

    def add(self, entry: LedgerEntry) -> None:
        self.windows += 1
        self.staged += entry.staged
        self.deleted += entry.deleted
        self.inserted += entry.inserted
        self.collisions += entry.collisions


def compare_tally(tally: SeriesTally, expected: SeriesBoundary) -> list[str]:
    """Mismatches between a run's totals and the audit manifest (empty = exact match)."""
    problems: list[str] = []
    if tally.staged != expected.expected_restamps:
        problems.append(f"restamps {tally.staged} != audit {expected.expected_restamps}")
    if tally.collisions != expected.expected_collisions:
        problems.append(f"collisions {tally.collisions} != audit {expected.expected_collisions}")
    if tally.staged != tally.deleted:
        problems.append(f"staged {tally.staged} != deleted {tally.deleted}")
    if tally.inserted + tally.collisions != tally.staged:
        problems.append(
            f"inserted {tally.inserted} + collisions {tally.collisions} != staged {tally.staged}"
        )
    return problems


# ---------------------------------------------------------------------------
# Audit v2: reference-window inclusion rules and coverage sensitivity
# ---------------------------------------------------------------------------


def is_intraday(interval: int) -> bool:
    return interval < 1440


@dataclass(frozen=True, slots=True)
class WindowStatus:
    """A weekly window vote with its inclusion decision (audit v2)."""

    vote: WindowVote
    coverage: float | None
    excluded_reason: str | None = None

    @property
    def included(self) -> bool:
        return self.excluded_reason is None


def classify_windows(
    votes: Sequence[WindowVote],
    first_traded_week: datetime | None,
    coverage_by_week: dict[datetime, float],
    floor: float,
    apply_coverage: bool,
) -> list[WindowStatus]:
    """Apply the two general inclusion rules of the v2 audit to weekly windows.

    Rule A — the first week in which the reference exchange traded the pair on
    this timeframe (first reference row with ``volume > 0``) is the listing
    ramp-up (and, for 1w, a partial candle by construction): excluded, together
    with any earlier window.
    Rule B — when ``apply_coverage`` (intraday timeframes per the GATE 3 spec,
    every timeframe with ``--coverage-scope all``): windows whose reference 1m
    coverage (share of the week's minutes with traded volume) is below
    ``floor`` are excluded.  Windows without a coverage figure count as 0.
    """
    out: list[WindowStatus] = []
    for v in sorted(votes, key=lambda x: x.window_start):
        cov = coverage_by_week.get(v.window_start)
        reason = None
        if first_traded_week is not None and v.window_start <= first_traded_week:
            reason = "listing week (rule A)"
        elif apply_coverage and (cov or 0.0) < floor:
            reason = f"coverage {100 * (cov or 0.0):.1f} % < floor {100 * floor:.0f} % (rule B)"
        out.append(WindowStatus(v, cov, reason))
    return out


def week_excluded(
    week_start: datetime,
    first_traded_week: datetime | None,
    coverage_by_week: dict[datetime, float],
    floor: float,
    apply_coverage: bool,
) -> str | None:
    """Same rules as :func:`classify_windows` for a single week (row-level re-checks)."""
    if first_traded_week is not None and week_start <= first_traded_week:
        return "listing week (rule A)"
    cov = coverage_by_week.get(week_start, 0.0)
    if apply_coverage and cov < floor:
        return f"coverage {100 * cov:.1f} % < floor {100 * floor:.0f} % (rule B)"
    return None


def sensitivity_table(
    statuses: Sequence[WindowStatus],
    expect: Verdict,
    floors: Sequence[float],
) -> list[tuple[float, int, int, int]]:
    """``(floor, included, excluded_by_coverage, included_offending)`` per candidate floor.

    Rule A exclusions are kept fixed; only the coverage floor varies over the
    windows the coverage rule applies to.
    """
    rows: list[tuple[float, int, int, int]] = []
    for floor in floors:
        included = 0
        excluded_cov = 0
        offending = 0
        for s in statuses:
            if s.excluded_reason and "rule A" in s.excluded_reason:
                continue
            if (s.coverage or 0.0) < floor:
                excluded_cov += 1
                continue
            included += 1
            if s.vote.verdict != expect:
                offending += 1
        rows.append((floor, included, excluded_cov, offending))
    return rows


def stability_plateau(
    table: Sequence[tuple[float, int, int, int]], chosen_floor: float, min_width: float = 0.30
) -> tuple[float | None, list[str]]:
    """Lowest floor from which no included window offends, and the problems if any.

    The verdict is *stable* when the offending count is 0 for every floor of a
    contiguous plateau reaching the highest tested floor, the plateau is at
    least ``min_width`` wide and the chosen floor lies inside it.
    """
    if not table:
        return None, ["no sensitivity data"]
    ordered = sorted(table)
    stable_from: float | None = None
    for floor, _inc, _exc, off in reversed(ordered):
        if off == 0:
            stable_from = floor
        else:
            break
    problems: list[str] = []
    if stable_from is None:
        problems.append("no floor gives a clean verdict (even the highest tested floor offends)")
        return None, problems
    width = ordered[-1][0] - stable_from
    if width < min_width:
        problems.append(
            f"stability plateau [{100 * stable_from:.0f} %, {100 * ordered[-1][0]:.0f} %] narrower "
            f"than {100 * min_width:.0f} points"
        )
    if chosen_floor < stable_from:
        problems.append(
            f"chosen floor {100 * chosen_floor:.0f} % is below the stability plateau "
            f"(from {100 * stable_from:.0f} %)"
        )
    return stable_from, problems
