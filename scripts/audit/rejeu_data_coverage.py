"""Rejeu diagnostic grid — real in-window data coverage per pair (prespec section D.1 / D.2).

Measures, from the database and not from an engine artefact, what data actually exists for each
pair over the 1096 UTC days of ``[2023-04-01, 2026-04-01)`` on ``exchange='binance'``, then
applies the five frozen admissibility clauses of section D.2. The measurement is deliberately
independent of ``equity_daily``: the engine forward-fills the NAV through holes without a marker
and ``n_daily_returns`` is 1096 even across the SOL hole (prespec section J.2), so coverage can
never be read off a campaign entry.

Day attribution (decision, pinned by the tests)
-----------------------------------------------
The rows are **period-end stamped** (``timestamp = open_time + interval``, B4.1): a candle
stamped ``t`` covers ``(t - interval, t]``. Section D.1 counts a day ``D`` as carrying the
candles stamped in ``(D 00:00, D+1 00:00]``, so **a stamp of exactly midnight closes the
previous day**: the 5 m candle stamped ``2026-04-01T00:00Z`` belongs to ``2026-03-31`` and is
inside the window, while the one stamped ``2023-04-01T00:00Z`` belongs to ``2023-03-31`` and is
outside it. Equivalently ``day_of(t) = (t - 1 microsecond).date()``. The DB window is therefore
``timestamp > start AND timestamp <= end``, the engines' own bounds (contract, debt 15(c)).

Conventions that the pre-specification leaves open, fixed here and reported as such
-----------------------------------------------------------------------------------
* ``median_daily_completeness_5m`` is a **fraction in [0, 1]** (count / 288), taken over all
  1096 window days, an uncovered day counting as 0.0 — as do ``days_below_90pct`` and
  ``days_below_50pct``. Restricting the median to covered days would make it blind to a hole,
  which is the very thing section D.1 is measuring.
* ``missing_1w_stamps`` lists the **end stamps** absent from the weekly grid, in full ISO form.
  Weekly candles are Monday-anchored at 00:00 UTC (verified in the DB, both pairs), so the
  expected grid is every Monday 00:00 UTC in ``(start, end]`` — 157 stamps for this window.
  Section D.1 announces the two missing weekly candles as ``2025-01-27`` / ``2025-02-24``; those
  are the **open** Mondays of the two absent weeks, whose end stamps are ``2025-02-03`` and
  ``2025-03-03``. Same two weeks, same two pairs — only the label differs by one interval, and
  this artefact stays on the stamps the DB actually keys on.
* Rows carrying an interval outside ``(5, 240, 1440, 10080)`` are ignored; the DB primary key
  ``(timestamp, pair, interval, exchange)`` guarantees one row per stamp, so counts are raw.

Read-only, DB en lecture seule.

Usage::

    poetry run python scripts/audit/rejeu_data_coverage.py \\
        --output results/rejeu_grid_20260919/data_coverage.json \\
        --markdown results/rejeu_grid_20260919/data_coverage.md

Exit codes: 0 ok, 1 violation, 2 usage or input error.

Exit 1 ("violation") is reserved for the one case that leaves nothing downstream to decide:
**no pair is admissible** (prespec section D.3, ``D_UNMEASURABLE`` / ``D_NO_ADMISSIBLE_PAIR``).
The artefact is written either way — an inadmissible SOL is the pre-registered expectation, not
a failure of this script.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
import hashlib
from pathlib import Path
import statistics
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

from dotenv import load_dotenv  # noqa: E402
import rejeu_common as rc  # noqa: E402
from sqlalchemy import select  # noqa: E402

from krakenbot.config.settings import Settings  # noqa: E402
from krakenbot.core.database import DatabaseManager  # noqa: E402
from krakenbot.models.market_data import OHLCData  # noqa: E402

#: Intervals (minutes) reported by ``counts_by_interval`` — the frozen schema's four keys.
INTERVALS_REPORTED: tuple[int, ...] = (5, 240, 1440, 10080)
#: 5 m candles expected in a full UTC day.
EXPECTED_5M_PER_DAY = 1440 // 5
#: Completeness levels counted by ``days_below_90pct`` / ``days_below_50pct``.
COMPLETENESS_LEVELS: tuple[float, ...] = (0.90, 0.50)
#: Weekly candles are Monday-anchored at 00:00 UTC (verified in the DB on both pairs).
WEEKLY_ANCHOR_WEEKDAY = 0

PRESPEC_RELPATH = "docs/rejeu_grid_prespec.md"

_EPSILON = timedelta(microseconds=1)
_MEDIAN_DIGITS = 9

#: Exactly the keys the frozen schema gives to ``pairs["<PAIR>"]``.
PAIR_KEYS: tuple[str, ...] = (
    "days_5m",
    "days_5m_complete",
    "days_4h",
    "max_gap_days",
    "first_covered_day",
    "last_covered_day",
    "median_daily_completeness_5m",
    "days_below_90pct",
    "days_below_50pct",
    "counts_by_interval",
    "missing_1w_stamps",
    "clauses",
    "admissible",
)

#: Exactly the five clauses of section D.2, in the order the prespec writes them.
CLAUSE_KEYS: tuple[str, ...] = (
    "days_5m",
    "days_5m_complete",
    "days_4h",
    "max_gap_days",
    "first_last",
)


# ---------------------------------------------------------------------------
# Pure layer — counting over (timestamp, interval) rows
# ---------------------------------------------------------------------------


def _as_utc(stamp: datetime) -> datetime:
    """UTC image of a stamp; a naive datetime is a defect, never silently assumed UTC."""
    if stamp.tzinfo is None:
        raise ValueError(f"naive timestamp {stamp!r}: every stamp must be tz-aware UTC")
    return stamp.astimezone(UTC)


def day_of(stamp: datetime) -> date:
    """UTC day a period-end stamp belongs to: ``(D 00:00, D+1 00:00]`` -> ``D``.

    Midnight closes the previous day, so ``day_of(2026-04-01T00:00Z) == date(2026, 3, 31)``.
    """
    return (_as_utc(stamp) - _EPSILON).date()


def window_days(start: datetime, end: datetime) -> list[date]:
    """The UTC days of ``[start, end)``: ``start.date()`` .. ``end.date() - 1 day``."""
    total = (end - start).days
    if total <= 0:
        raise ValueError(f"empty window: {start.isoformat()} .. {end.isoformat()}")
    first = start.date()
    return [first + timedelta(days=i) for i in range(total)]


def expected_weekly_stamps(start: datetime, end: datetime) -> list[datetime]:
    """Every Monday 00:00 UTC stamp in ``(start, end]`` — the weekly grid of the window."""
    cursor = datetime.combine(start.date(), datetime.min.time(), tzinfo=UTC)
    cursor += timedelta(days=(WEEKLY_ANCHOR_WEEKDAY - cursor.weekday()) % 7)
    while cursor <= start:
        cursor += timedelta(days=7)
    out: list[datetime] = []
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(days=7)
    return out


def _longest_zero_run(days: Sequence[date], counts: Counter[date]) -> int:
    """Longest contiguous run of window days carrying no 5 m candle at all."""
    best = current = 0
    for day in days:
        if counts.get(day, 0) == 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def measure_pair(
    rows: Iterable[tuple[datetime, int]],
    *,
    start: datetime = rc.WINDOW_START,
    end: datetime = rc.WINDOW_END,
) -> dict[str, Any]:
    """Coverage of one pair over ``[start, end)`` from its ``(timestamp, interval)`` rows.

    Pure: no DB, no clock, no I/O. Rows outside ``(start, end]`` and rows carrying an
    unreported interval are ignored, so the caller may hand over a wider fetch.
    """
    days = window_days(start, end)
    counts_by_interval = {str(i): 0 for i in INTERVALS_REPORTED}
    per_day_5m: Counter[date] = Counter()
    days_with_4h: set[date] = set()
    weekly_seen: set[datetime] = set()

    for stamp, interval in rows:
        stamp = _as_utc(stamp)
        if not (start < stamp <= end):
            continue
        interval = int(interval)
        key = str(interval)
        if key not in counts_by_interval:
            continue
        counts_by_interval[key] += 1
        if interval == 5:
            per_day_5m[day_of(stamp)] += 1
        elif interval == 240:
            days_with_4h.add(day_of(stamp))
        elif interval == 10080:
            weekly_seen.add(stamp)

    completeness = [per_day_5m.get(day, 0) / EXPECTED_5M_PER_DAY for day in days]
    covered = [day for day in days if per_day_5m.get(day, 0) > 0]
    days_5m = len(covered)
    days_5m_complete = sum(1 for day in days if per_day_5m.get(day, 0) >= rc.DAY_5M_COMPLETE_MIN)
    days_4h = len(days_with_4h)
    max_gap = _longest_zero_run(days, per_day_5m)
    first_covered = covered[0] if covered else None
    last_covered = covered[-1] if covered else None
    missing_weekly = [
        stamp.isoformat()
        for stamp in expected_weekly_stamps(start, end)
        if stamp not in weekly_seen
    ]

    clauses = {
        "days_5m": days_5m >= rc.COVERAGE_MIN_DAYS,
        "days_5m_complete": days_5m_complete >= rc.COVERAGE_MIN_DAYS,
        "days_4h": days_4h >= rc.COVERAGE_MIN_DAYS,
        "max_gap_days": max_gap <= rc.MAX_GAP_DAYS,
        "first_last": (
            first_covered is not None
            and last_covered is not None
            and first_covered <= date.fromisoformat(rc.FIRST_COVERED_DAY_MAX)
            and last_covered >= date.fromisoformat(rc.LAST_COVERED_DAY_MIN)
        ),
    }
    return {
        "days_5m": days_5m,
        "days_5m_complete": days_5m_complete,
        "days_4h": days_4h,
        "max_gap_days": max_gap,
        "first_covered_day": first_covered.isoformat() if first_covered else None,
        "last_covered_day": last_covered.isoformat() if last_covered else None,
        "median_daily_completeness_5m": round(statistics.median(completeness), _MEDIAN_DIGITS),
        "days_below_90pct": sum(1 for c in completeness if c < COMPLETENESS_LEVELS[0]),
        "days_below_50pct": sum(1 for c in completeness if c < COMPLETENESS_LEVELS[1]),
        "counts_by_interval": counts_by_interval,
        "missing_1w_stamps": missing_weekly,
        "clauses": {key: clauses[key] for key in CLAUSE_KEYS},
        "admissible": all(clauses[key] for key in CLAUSE_KEYS),
    }


def prespec_block(root: Path = rc.PROJECT_ROOT, relpath: str = PRESPEC_RELPATH) -> dict[str, str]:
    """``{path, sha256}`` of the frozen pre-specification, as every artefact carries it."""
    path = Path(root) / relpath
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": relpath, "sha256": digest}


def build_artifact(
    rows_by_pair: dict[str, Iterable[tuple[datetime, int]]],
    *,
    generated_at: datetime,
    prespec: dict[str, str],
    start: datetime = rc.WINDOW_START,
    end: datetime = rc.WINDOW_END,
) -> dict[str, Any]:
    """The frozen ``data_coverage.json`` payload. Pure: the clock is injected."""
    return {
        "generated_at": _as_utc(generated_at).isoformat(),
        "base_sha": rc.BASE_SHA,
        "prespec": dict(prespec),
        "exchange": rc.EXCHANGE,
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": (end - start).days,
        },
        "pairs": {
            pair: measure_pair(rows, start=start, end=end) for pair, rows in rows_by_pair.items()
        },
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_markdown(artifact: dict[str, Any]) -> str:
    """Section D table: the measures, then the five clauses, then the missing weekly stamps."""
    window = artifact["window"]
    pairs: dict[str, Any] = artifact["pairs"]
    names = list(pairs)
    lines = [
        "# Rejeu diagnostic grid — couverture de données (§ D.1 / D.2)",
        "",
        f"Fenêtre `[{window['start']}, {window['end']})` — {window['days']} jours UTC, "
        f"exchange `{artifact['exchange']}`, convention end-stamped "
        "(une bougie stampée `t` couvre `(t − intervalle, t]`, minuit clôt la veille).",
        "",
        f"Généré le {artifact['generated_at']} · base_sha `{artifact['base_sha'][:12]}` · "
        f"prespec `{artifact['prespec']['sha256'][:16]}`",
        "",
        "## Mesures",
        "",
        "| Mesure | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]
    rows: tuple[tuple[str, str], ...] = (
        ("days_5m", "days_5m"),
        ("days_5m_complete (>= 144/288)", "days_5m_complete"),
        ("days_4h", "days_4h"),
        ("max_gap_days", "max_gap_days"),
        ("first_covered_day", "first_covered_day"),
        ("last_covered_day", "last_covered_day"),
        ("médiane complétude 5 m", "median_daily_completeness_5m"),
        ("jours < 90 %", "days_below_90pct"),
        ("jours < 50 %", "days_below_50pct"),
    )
    for label, key in rows:
        cells = ["—" if pairs[name][key] is None else str(pairs[name][key]) for name in names]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    for interval in INTERVALS_REPORTED:
        values = [pairs[name]["counts_by_interval"][str(interval)] for name in names]
        lines.append(f"| rows interval={interval} | " + " | ".join(str(v) for v in values) + " |")

    lines += [
        "",
        "## Clauses d'admissibilité (§ D.2, gelées)",
        "",
        "| Clause | Seuil | " + " | ".join(names) + " |",
        "|---|---|" + "---|" * len(names),
    ]
    thresholds = {
        "days_5m": f">= {rc.COVERAGE_MIN_DAYS}",
        "days_5m_complete": f">= {rc.COVERAGE_MIN_DAYS}",
        "days_4h": f">= {rc.COVERAGE_MIN_DAYS}",
        "max_gap_days": f"<= {rc.MAX_GAP_DAYS}",
        "first_last": f"<= {rc.FIRST_COVERED_DAY_MAX} et >= {rc.LAST_COVERED_DAY_MIN}",
    }
    for clause in CLAUSE_KEYS:
        marks = ["OK" if pairs[name]["clauses"][clause] else "ÉCHEC" for name in names]
        lines.append(f"| {clause} | {thresholds[clause]} | " + " | ".join(marks) + " |")
    verdicts = [
        "**admissible**" if pairs[name]["admissible"] else "**inadmissible**" for name in names
    ]
    lines.append("| **admissible** | les cinq | " + " | ".join(verdicts) + " |")

    lines += ["", "## Stamps 1 w manquants dans la fenêtre", ""]
    for name in names:
        missing = pairs[name]["missing_1w_stamps"]
        rendered = ", ".join(f"`{stamp}`" for stamp in missing) if missing else "aucun"
        lines.append(f"- **{name}** ({len(missing)}) : {rendered}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DB layer — fetches the rows and nothing else
# ---------------------------------------------------------------------------


async def fetch_rows(
    db_manager: DatabaseManager,
    pair: str,
    *,
    start: datetime = rc.WINDOW_START,
    end: datetime = rc.WINDOW_END,
    intervals: Sequence[int] = INTERVALS_REPORTED,
    exchange: str = rc.EXCHANGE,
) -> list[tuple[datetime, int]]:
    """``(timestamp, interval)`` of one pair over ``(start, end]``. Read-only, no counting here."""
    async with db_manager.read_session() as session:
        stmt = (
            select(OHLCData.timestamp, OHLCData.interval)
            .where(OHLCData.pair == pair)
            .where(OHLCData.exchange == exchange)
            .where(OHLCData.interval.in_(list(intervals)))
            .where(OHLCData.timestamp > start)
            .where(OHLCData.timestamp <= end)
            .order_by(OHLCData.timestamp.asc())
        )
        result = await session.execute(stmt)
        return [(row[0], int(row[1])) for row in result.all()]


async def collect(args: argparse.Namespace) -> dict[str, list[tuple[datetime, int]]]:
    """Fetch the rows of every frozen pair. The only place that touches the database."""
    settings = Settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    try:
        rows_by_pair: dict[str, list[tuple[datetime, int]]] = {}
        for pair in rc.PAIRS:
            rows = await fetch_rows(db_manager, pair, start=args.start, end=args.end)
            span = f"({args.start.isoformat()}, {args.end.isoformat()}]"
            print(f"  {pair}: {len(rows)} rows in {span}")
            rows_by_pair[pair] = rows
        return rows_by_pair
    finally:
        await db_manager.close_db()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_now(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rejeu diagnostic grid — data coverage per pair (prespec D.1/D.2)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=rc.PROJECT_ROOT / "results" / "rejeu_grid_20260919" / "data_coverage.json",
        help="Artifact path (default: results/rejeu_grid_20260919/data_coverage.json).",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional markdown rendering of the two tables.",
    )
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="ISO instant stamped as generated_at (default: now, UTC). Injected for determinism.",
    )
    args = parser.parse_args(argv)
    args.start = rc.WINDOW_START
    args.end = rc.WINDOW_END
    if args.now is None:
        args.generated_at = datetime.now(UTC)
    else:
        try:
            args.generated_at = _parse_now(args.now)
        except ValueError as exc:
            parser.error(f"--now: {exc}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        prespec = prespec_block()
    except OSError as exc:
        print(f"pre-specification unreadable: {exc}", file=sys.stderr)
        return 2

    # .env is loaded here, not at import time (B4.2 root fix of the .env leak).
    load_dotenv(rc.PROJECT_ROOT / ".env")
    try:
        rows_by_pair = asyncio.run(collect(args))
    except Exception as exc:  # noqa: BLE001 - a DB failure is an input error, not a violation
        print(f"database read failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    artifact = build_artifact(
        rows_by_pair,
        generated_at=args.generated_at,
        prespec=prespec,
        start=args.start,
        end=args.end,
    )
    digest = rc.write_json(args.output, artifact)
    print(f"data_coverage.json written: {args.output} (sha256 {digest[:16]})")
    for pair, measure in artifact["pairs"].items():
        failed = [c for c in CLAUSE_KEYS if not measure["clauses"][c]]
        verdict = "admissible" if measure["admissible"] else f"inadmissible ({', '.join(failed)})"
        print(
            f"  {pair}: days_5m {measure['days_5m']}, complete {measure['days_5m_complete']}, "
            f"4h {measure['days_4h']}, max_gap {measure['max_gap_days']}, "
            f"first {measure['first_covered_day']}, last {measure['last_covered_day']} -> {verdict}"
        )
    if args.markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(artifact), encoding="utf-8")
        print(f"markdown written: {args.markdown}")

    if not any(measure["admissible"] for measure in artifact["pairs"].values()):
        print(
            "VIOLATION: no admissible pair — prespec D.3 sends the family verdict to "
            "inconclusif (D_NO_ADMISSIBLE_PAIR).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
