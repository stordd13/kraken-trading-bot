"""B4.1 — Re-stamp Binance rows from open time to period end (SERVER ONLY).

Moves every ``exchange='binance'`` row inside the audited perimeter from
``timestamp = open_time`` to ``timestamp = open_time + interval`` (the project
standard, see ``krakenbot.data.backfill``).  The perimeter comes exclusively
from the boundary manifest written by ``b4_timestamp_audit.py``
(``last_open_stamped_ts`` per series) — nothing is hard-coded here.

Mechanics ("staging per window, newest first")
-----------------------------------------------
The PK ``(timestamp, pair, interval, exchange)`` is not deferrable, so a plain
``UPDATE … SET timestamp = timestamp + interval`` fails on transient duplicate
keys.  Each window ``[w_start, w_end)`` of at most ``--max-rows-per-tx`` candles
(original timestamps) is processed in **one transaction**::

    CREATE TEMP TABLE b4_stage (LIKE market_data_ohlc) ON COMMIT DROP;
    INSERT INTO b4_stage SELECT <rows of the window, timestamp + interval>;
    DELETE FROM market_data_ohlc WHERE <window>;
    INSERT INTO market_data_ohlc SELECT * FROM b4_stage ON CONFLICT DO NOTHING;
    INSERT INTO <progress table> (window, counts, plan identity);

Windows run from the newest to the oldest, so the target ``T + interval`` of a
row is always vacated before it is needed.  ``ON CONFLICT DO NOTHING`` is the
"WS wins" policy: a Vision row whose target is already occupied by an
end-stamped row is dropped and counted as a collision — but any collision
beyond the manifest's ``expected_collisions`` **rolls the window back and stops
the run** (GATE 1 decision 2: a collision the audit did not predict is a
mismatch, not something to absorb).

Safety / resume
---------------
* Progress is recorded **inside the window transaction** in an ordinary table
  (``--progress-table``, default ``b4_restamp_progress``): a committed window is
  never re-run, whatever happens to the process, the shell, ``$HOME`` or the
  JSONL mirror (``--ledger``, human-readable copy appended after each commit).
* Before writing anything, every selected series is pre-flighted: the committed
  windows must carry the same plan identity (``max_rows``, boundary, manifest
  stamp) and be the newest-first prefix of the plan, and the untouched original
  rows must count exactly ``expected_restamps - already staged`` — otherwise
  the run is refused (exit 2) without touching the DB.
* In-transaction guards: the slot ``w_end`` must be free before a window is
  staged (an occupied slot means the window was already shifted), ``deleted``
  must equal ``staged``, and unexpected collisions abort.
* A session advisory lock prevents two ``--execute`` instances from
  interleaving.  ``--execute`` is refused through the SSH tunnel (port 5433)
  and without ``--i-have-a-fresh-backup``.

Modes
-----
``--dry-run`` (default) counts rows and collisions per window without writing
and compares the per-series totals with the manifest (exit 1 on any mismatch);
``--dry-run --explain`` additionally validates the execute-path SQL on the
server with ``EXPLAIN`` (plans only, an empty session-local temp table, no
write).  ``--execute`` performs the migration.  Exit codes: 0 match, 1 tally
mismatch, 2 refused before any write, 3 stopped mid-run (window rolled back).

Usage (server, tmux, collector stopped — see skills/database.md)::

    poetry run python scripts/audit/b4_restamp_binance.py --dry-run --explain
    poetry run python scripts/audit/b4_restamp_binance.py --execute --i-have-a-fresh-backup \\
        --ledger ~/b4_restamp_ledger.jsonl
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import sys
import time

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "audit"))

from b4_stamp_lib import (
    TARGET_EXCHANGE,
    BoundaryManifest,
    LedgerEntry,
    SeriesBoundary,
    SeriesTally,
    append_ledger,
    check_resume_plan,
    compare_tally,
    done_windows,
    label,
    read_ledger,
    remaining_region_end,
    restamp_windows,
)

DEFAULT_MANIFEST = ROOT / "results" / "b4_binance_stamp_boundaries.json"
MAX_ROWS_HARD_LIMIT = 5000  # skills/database.md: never more than 5000 rows per statement
ADVISORY_LOCK_KEY = 0xB4_0001  # session-level lock shared by every --execute instance
PROGRESS_EVERY = 50  # windows between two progress lines on long series
LOCK_RETRIES = 3
_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

_WHERE = (
    "exchange = $1 AND pair = $2 AND interval = $3 "
    "AND timestamp >= $4 AND timestamp < $5 AND timestamp <= $6"
)
SQL_COUNT_WINDOW = f"SELECT COUNT(*) FROM market_data_ohlc WHERE {_WHERE}"
SQL_COUNT_COLLISIONS = f"""
SELECT COUNT(*) FROM market_data_ohlc a
WHERE {_WHERE}
  AND EXISTS (SELECT 1 FROM market_data_ohlc b
              WHERE b.exchange = a.exchange AND b.pair = a.pair AND b.interval = a.interval
                AND b.timestamp = a.timestamp + make_interval(mins => a.interval)
                AND b.timestamp > $6)
"""
SQL_CREATE_STAGE = "CREATE TEMP TABLE b4_stage (LIKE market_data_ohlc) ON COMMIT DROP"
SQL_CREATE_STAGE_EXPLAIN = "CREATE TEMP TABLE b4_stage (LIKE market_data_ohlc)"
SQL_STAGE = f"""
INSERT INTO b4_stage (timestamp, pair, interval, exchange,
                      open, high, low, close, volume, vwap, trades_count)
SELECT timestamp + make_interval(mins => interval), pair, interval, exchange,
       open, high, low, close, volume, vwap, trades_count
FROM market_data_ohlc WHERE {_WHERE}
"""
SQL_DELETE = f"DELETE FROM market_data_ohlc WHERE {_WHERE}"
SQL_INSERT = """
INSERT INTO market_data_ohlc (timestamp, pair, interval, exchange,
                              open, high, low, close, volume, vwap, trades_count)
SELECT timestamp, pair, interval, exchange, open, high, low, close, volume, vwap, trades_count
FROM b4_stage
ON CONFLICT (timestamp, pair, interval, exchange) DO NOTHING
"""
SQL_SLOT_OCCUPIED = (
    "SELECT COUNT(*) FROM market_data_ohlc "
    "WHERE exchange = $1 AND pair = $2 AND interval = $3 AND timestamp = $4"
)
SQL_COUNT_BEFORE = (
    "SELECT COUNT(*) FROM market_data_ohlc "
    "WHERE exchange = $1 AND pair = $2 AND interval = $3 AND timestamp < $4"
)
SQL_TABLE_EXISTS = "SELECT to_regclass($1) IS NOT NULL"


def sql_create_progress(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    pair text NOT NULL,
    interval integer NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    staged integer NOT NULL,
    deleted integer NOT NULL,
    inserted integer NOT NULL,
    collisions integer NOT NULL,
    seconds double precision NOT NULL,
    max_rows integer NOT NULL,
    boundary timestamptz NOT NULL,
    manifest_generated_at timestamptz NOT NULL,
    done_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (pair, interval, window_start, window_end)
)
"""


def sql_insert_progress(table: str) -> str:
    return (
        f"INSERT INTO {table} (pair, interval, window_start, window_end, staged, deleted, "
        "inserted, collisions, seconds, max_rows, boundary, manifest_generated_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)"
    )


def sql_read_progress(table: str) -> str:
    return (
        f"SELECT pair, interval, window_start, window_end, staged, deleted, inserted, collisions, "
        f"seconds, max_rows, boundary, manifest_generated_at FROM {table} "
        "WHERE pair = $1 AND interval = $2 ORDER BY window_start DESC"
    )


class RestampStop(RuntimeError):
    """Raised inside a window transaction: the window is rolled back and the run stops."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--boundaries", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--pairs", nargs="+", default=None, help="Restrict to these pairs.")
    ap.add_argument("--intervals", nargs="+", type=int, default=None, help="Restrict to these TFs.")
    ap.add_argument("--max-rows-per-tx", type=int, default=4000)
    ap.add_argument(
        "--ledger",
        type=Path,
        default=Path.home() / "b4_restamp_ledger.jsonl",
        help="JSONL mirror of the DB progress table (human-readable).",
    )
    ap.add_argument(
        "--progress-table",
        default="b4_restamp_progress",
        help="Ordinary table written inside each window transaction (resume source of truth).",
    )
    ap.add_argument(
        "--explain",
        action="store_true",
        help="Dry-run only: EXPLAIN the execute-path SQL on the first pending window of each series.",
    )
    ap.add_argument(
        "--i-have-a-fresh-backup",
        action="store_true",
        help="Required with --execute (pg_dump -Fc taken after the last Bybit import).",
    )
    ap.add_argument(
        "--allow-tunnel",
        action="store_true",
        help="Allow a DATABASE_URL on port 5433 (dry-run only, never for --execute).",
    )
    args = ap.parse_args(argv)
    if args.execute:
        args.dry_run = False
    return args


def _count(result: str) -> int:
    """asyncpg status tag ``'DELETE 123'`` / ``'INSERT 0 123'`` → 123."""
    return int(result.rsplit(" ", 1)[-1])


def is_tunnel_url(url: str) -> bool:
    return ":5433/" in url or url.rstrip("/").endswith(":5433")


def validate(args: argparse.Namespace, url: str) -> str | None:
    """Return an error message when the invocation must be refused (before any connection)."""
    if args.max_rows_per_tx <= 0 or args.max_rows_per_tx > MAX_ROWS_HARD_LIMIT:
        return f"--max-rows-per-tx must be in 1..{MAX_ROWS_HARD_LIMIT}"
    if not args.boundaries.exists():
        return f"manifest not found: {args.boundaries}"
    if not _IDENT.match(args.progress_table):
        return f"invalid --progress-table identifier: {args.progress_table!r}"
    if is_tunnel_url(url):
        if args.execute:
            return "refusing --execute through the SSH tunnel (port 5433): run on the server"
        if not args.allow_tunnel:
            return "DATABASE_URL points to the tunnel (5433): add --allow-tunnel for a dry-run"
    if args.execute and not args.i_have_a_fresh_backup:
        return "--execute requires --i-have-a-fresh-backup"
    if args.execute and args.explain:
        return "--explain is a dry-run option"
    return None


def select_series(
    manifest: BoundaryManifest, args: argparse.Namespace
) -> tuple[list[SeriesBoundary], str | None]:
    """Series to process, or an error when a filter names something the manifest lacks."""
    known_pairs = {s.pair for s in manifest.series}
    known_intervals = {s.interval for s in manifest.series}
    if args.pairs:
        unknown = [p for p in args.pairs if p not in known_pairs]
        if unknown:
            return [], f"unknown pair(s) {unknown}; manifest has {sorted(known_pairs)}"
    if args.intervals:
        unknown_i = [i for i in args.intervals if i not in known_intervals]
        if unknown_i:
            return [], f"unknown interval(s) {unknown_i}; manifest has {sorted(known_intervals)}"
    out = []
    for s in manifest.series:
        if args.pairs and s.pair not in args.pairs:
            continue
        if args.intervals and s.interval not in args.intervals:
            continue
        if s.last_open_stamped_ts is None or s.expected_restamps == 0:
            continue
        out.append(s)
    if not out:
        return [], "no series selected"
    return out, None


def _row_to_entry(r: asyncpg.Record) -> LedgerEntry:
    return LedgerEntry(
        r["pair"],
        int(r["interval"]),
        r["window_start"],
        r["window_end"],
        int(r["staged"]),
        int(r["deleted"]),
        int(r["inserted"]),
        int(r["collisions"]),
        float(r["seconds"]),
        False,
        int(r["max_rows"]),
        r["boundary"],
        r["manifest_generated_at"],
    )


async def read_progress(
    conn: asyncpg.Connection, table: str, s: SeriesBoundary
) -> list[LedgerEntry]:
    if not await conn.fetchval(SQL_TABLE_EXISTS, table):
        return []
    rows = await conn.fetch(sql_read_progress(table), s.pair, s.interval)
    return [_row_to_entry(r) for r in rows]


async def run_window_dry(
    conn: asyncpg.Connection, s: SeriesBoundary, w_start: datetime, w_end: datetime
) -> LedgerEntry:
    params = (TARGET_EXCHANGE, s.pair, s.interval, w_start, w_end, s.last_open_stamped_ts)
    t0 = time.perf_counter()
    staged = int(await conn.fetchval(SQL_COUNT_WINDOW, *params))
    collisions = int(await conn.fetchval(SQL_COUNT_COLLISIONS, *params))
    return LedgerEntry(
        s.pair,
        s.interval,
        w_start,
        w_end,
        staged,
        staged,
        staged - collisions,
        collisions,
        time.perf_counter() - t0,
        True,
    )


async def run_window_execute(
    conn: asyncpg.Connection,
    s: SeriesBoundary,
    w_start: datetime,
    w_end: datetime,
    *,
    is_top: bool,
    allowed_collisions: int,
    max_rows: int,
    manifest_generated_at: datetime,
    progress_table: str,
) -> LedgerEntry:
    """One window in one transaction; raises :class:`RestampStop` (→ rollback) on any anomaly."""
    params = (TARGET_EXCHANGE, s.pair, s.interval, w_start, w_end, s.last_open_stamped_ts)
    name = f"{s.pair} {label(s.interval)} window [{w_start.isoformat()}, {w_end.isoformat()})"
    t0 = time.perf_counter()
    async with conn.transaction():
        occupied = int(
            await conn.fetchval(SQL_SLOT_OCCUPIED, TARGET_EXCHANGE, s.pair, s.interval, w_end)
        )
        if occupied and not (is_top and allowed_collisions > 0):
            raise RestampStop(
                f"{name}: slot {w_end.isoformat()} already occupied — window already shifted?"
            )
        await conn.execute(SQL_CREATE_STAGE)
        staged = _count(await conn.execute(SQL_STAGE, *params))
        deleted = _count(await conn.execute(SQL_DELETE, *params))
        if deleted != staged:
            raise RestampStop(f"{name}: staged {staged} != deleted {deleted}")
        inserted = _count(await conn.execute(SQL_INSERT))
        collisions = staged - inserted
        if collisions > allowed_collisions:
            raise RestampStop(
                f"{name}: {collisions} collision(s) but the audit allows {allowed_collisions} — "
                "mismatch with the manifest"
            )
        seconds = time.perf_counter() - t0
        await conn.execute(
            sql_insert_progress(progress_table),
            s.pair,
            s.interval,
            w_start,
            w_end,
            staged,
            deleted,
            inserted,
            collisions,
            seconds,
            max_rows,
            s.last_open_stamped_ts,
            manifest_generated_at,
        )
    return LedgerEntry(
        s.pair,
        s.interval,
        w_start,
        w_end,
        staged,
        deleted,
        inserted,
        collisions,
        seconds,
        False,
        max_rows,
        s.last_open_stamped_ts,
        manifest_generated_at,
    )


async def explain_window(
    conn: asyncpg.Connection, s: SeriesBoundary, w_start: datetime, w_end: datetime
) -> list[str]:
    """Plan (never execute) the execute-path statements against the real schema."""
    params = (TARGET_EXCHANGE, s.pair, s.interval, w_start, w_end, s.last_open_stamped_ts)
    lines: list[str] = []
    await conn.execute("SET default_transaction_read_only = off")  # temp table creation
    try:
        await conn.execute(SQL_CREATE_STAGE_EXPLAIN)
        for title, sql, p in (
            ("stage", SQL_STAGE, params),
            ("delete", SQL_DELETE, params),
            ("insert", SQL_INSERT, ()),
        ):
            plan = await conn.fetch(f"EXPLAIN {sql}", *p)
            lines.append(f"      EXPLAIN {title}: " + " | ".join(r[0].strip() for r in plan[:3]))
    finally:
        await conn.execute("DROP TABLE IF EXISTS b4_stage")
        await conn.execute("SET default_transaction_read_only = on")
    return lines


def format_tallies(tallies: list[SeriesTally], manifest: BoundaryManifest, dry_run: bool) -> str:
    lines = [
        "=" * 100,
        f"  B4.1 re-stamp {'DRY-RUN' if dry_run else 'EXECUTE'} — exchange='{TARGET_EXCHANGE}' "
        f"manifest={manifest.generated_at.isoformat()}",
        "=" * 100,
        f"  {'Series':<14} {'windows':>7} {'staged':>9} {'audit':>9} {'deleted':>9} "
        f"{'inserted':>9} {'collisions':>10} {'audit':>6}  Status",
    ]
    ok_all = bool(tallies)
    for t in tallies:
        s = manifest.get(t.pair, t.interval)
        assert s is not None
        problems = compare_tally(t, s)
        ok_all &= not problems
        lines.append(
            f"  {t.pair + ' ' + label(t.interval):<14} {t.windows:>7} {t.staged:>9} "
            f"{s.expected_restamps:>9} {t.deleted:>9} {t.inserted:>9} {t.collisions:>10} "
            f"{s.expected_collisions:>6}  {'OK' if not problems else 'MISMATCH: ' + '; '.join(problems)}"
        )
    lines.append("  " + "-" * 98)
    lines.append(
        f"  total staged={sum(t.staged for t in tallies)} audit={manifest.total_restamps} "
        f"collisions={sum(t.collisions for t in tallies)} audit={manifest.total_collisions} "
        f"series={len(tallies)}/{len(manifest.series)} → {'MATCH' if ok_all else 'MISMATCH — STOP'}"
    )
    return "\n".join(lines)


async def _preflight(
    conn: asyncpg.Connection,
    s: SeriesBoundary,
    plan: list[tuple[datetime, datetime]],
    done: list[LedgerEntry],
    args: argparse.Namespace,
    manifest: BoundaryManifest,
) -> list[str]:
    """Checks that must pass before the first write of a series (also run in dry-run)."""
    assert s.last_open_stamped_ts is not None
    problems = check_resume_plan(
        plan, done, args.max_rows_per_tx, s.last_open_stamped_ts, manifest.generated_at
    )
    if problems:
        return problems
    region_end = remaining_region_end(plan, len(done))
    if region_end is None:
        return []
    remaining = int(
        await conn.fetchval(SQL_COUNT_BEFORE, TARGET_EXCHANGE, s.pair, s.interval, region_end)
    )
    expected = s.expected_restamps - sum(e.staged for e in done)
    if remaining != expected:
        return [
            f"untouched original rows (< {region_end.isoformat()}) = {remaining}, "
            f"audit expects {expected} (= {s.expected_restamps} - {sum(e.staged for e in done)} done)"
        ]
    return []


async def _async_main(args: argparse.Namespace) -> int:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    err = validate(args, url)
    if err:
        print(f"REFUSED: {err}")
        return 2
    manifest = BoundaryManifest.load(args.boundaries)
    series, err = select_series(manifest, args)
    if err:
        print(f"REFUSED: {err}")
        return 2
    print(
        f"mode={'EXECUTE' if args.execute else 'DRY-RUN'} series={len(series)} "
        f"max_rows_per_tx={args.max_rows_per_tx} manifest={manifest.generated_at.isoformat()} "
        f"progress_table={args.progress_table} ledger={args.ledger}"
    )

    conn = await asyncpg.connect(url, timeout=30)
    tallies: list[SeriesTally] = []
    started = datetime.now(UTC)
    rc = 0
    try:
        await conn.execute("SET statement_timeout = '0'")
        await conn.execute("SET lock_timeout = '30s'")
        if args.execute:
            if not await conn.fetchval("SELECT pg_try_advisory_lock($1)", ADVISORY_LOCK_KEY):
                print("REFUSED: another --execute holds the advisory lock")
                return 2
            await conn.execute(sql_create_progress(args.progress_table))
        else:
            await conn.execute("SET default_transaction_read_only = on")

        mirrored = done_windows(read_ledger(args.ledger)) if args.execute else set()
        for s in series:
            assert s.last_open_stamped_ts is not None
            name = f"{s.pair} {label(s.interval)}"
            plan = restamp_windows(
                s.min_ts, s.last_open_stamped_ts, s.interval, args.max_rows_per_tx
            )
            done = await read_progress(conn, args.progress_table, s)
            problems = await _preflight(conn, s, plan, done, args, manifest)
            if problems:
                print(f"REFUSED before any write — {name}:")
                for p in problems:
                    print(f"    - {p}")
                return 2
            tally = SeriesTally(s.pair, s.interval)
            tallies.append(tally)
            for e in done:
                tally.add(e)
                if args.execute and e.window_key not in mirrored:
                    append_ledger(args.ledger, e)  # committed but not mirrored (crash after COMMIT)
            pending = plan[len(done) :]
            if args.explain and pending:
                for line in await explain_window(conn, s, *pending[0]):
                    print(line)
            t_series = time.perf_counter()
            for idx, (w_start, w_end) in enumerate(pending, 1):
                if args.execute:
                    for attempt in range(1, LOCK_RETRIES + 1):
                        try:
                            entry = await run_window_execute(
                                conn,
                                s,
                                w_start,
                                w_end,
                                is_top=(w_start, w_end) == plan[0],
                                allowed_collisions=s.expected_collisions - tally.collisions,
                                max_rows=args.max_rows_per_tx,
                                manifest_generated_at=manifest.generated_at,
                                progress_table=args.progress_table,
                            )
                            break
                        except asyncpg.exceptions.LockNotAvailableError:
                            if attempt == LOCK_RETRIES:
                                raise
                            print(
                                f"    lock timeout on {name} {w_start.isoformat()}, retry {attempt}"
                            )
                            await asyncio.sleep(5)
                    append_ledger(args.ledger, entry)
                else:
                    entry = await run_window_dry(conn, s, w_start, w_end)
                tally.add(entry)
                if entry.collisions:
                    print(
                        f"    collision(s) {name} window {w_start.isoformat()}: {entry.collisions} "
                        "Vision row(s) dropped (existing end-stamped rows win)"
                    )
                if idx % PROGRESS_EVERY == 0 or idx == len(pending):
                    elapsed = time.perf_counter() - t_series
                    rate = idx / elapsed if elapsed else 0.0
                    eta = (len(pending) - idx) / rate if rate else 0.0
                    print(
                        f"    {name}: {idx}/{len(pending)} windows, {tally.staged} rows, "
                        f"{elapsed:.0f}s elapsed, {rate:.2f} win/s, ETA {eta:.0f}s"
                    )
            print(
                f"  {name}: plan={len(plan)} resumed={len(done)} run={len(pending)} "
                f"staged={tally.staged} collisions={tally.collisions} "
                f"({time.perf_counter() - t_series:.1f}s)"
            )
        if args.execute:
            print("  VACUUM ANALYZE market_data_ohlc …")
            t_vac = time.perf_counter()
            await conn.execute("VACUUM ANALYZE market_data_ohlc")
            print(f"  VACUUM ANALYZE done in {time.perf_counter() - t_vac:.0f}s")
    except RestampStop as exc:
        print(f"\nSTOP — window rolled back, nothing else touched: {exc}")
        rc = 3
    except Exception as exc:  # noqa: BLE001 — report context, the window transaction is rolled back
        print(f"\nSTOP — unexpected error ({type(exc).__name__}): {exc}")
        rc = 3
    finally:
        await conn.close()

    print()
    print(format_tallies(tallies, manifest, not args.execute))
    print(f"  started={started.isoformat()} finished={datetime.now(UTC).isoformat()}")
    if rc:
        return rc
    mismatch = not tallies or any(
        compare_tally(t, manifest.get(t.pair, t.interval))  # type: ignore[arg-type]
        for t in tallies
    )
    return 1 if mismatch else 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
