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
is processed in **one transaction**::

    CREATE TEMP TABLE b4_stage ON COMMIT DROP AS SELECT <shifted rows of the window>;
    DELETE FROM market_data_ohlc WHERE <window>;
    INSERT INTO market_data_ohlc SELECT * FROM b4_stage ON CONFLICT DO NOTHING;

Windows run from the newest to the oldest, so the target ``T + interval`` of a
row is always vacated before it is needed.  ``ON CONFLICT DO NOTHING`` is the
"WS wins" policy: a Vision row whose target is already occupied by an
end-stamped row is dropped and counted as a collision.  Every committed window
is appended to a JSONL ledger; a re-run skips windows already in the ledger.

Modes
-----
``--dry-run`` (default) counts rows and collisions per window without writing
and compares the per-series totals with the manifest (exit code 1 on any
mismatch → STOP, escalate).  ``--execute`` performs the migration; it refuses
to run through the SSH tunnel (``localhost:5433``) and requires
``--i-have-a-fresh-backup``.

Usage (server, tmux, collector stopped — see skills/database.md)::

    poetry run python scripts/audit/b4_restamp_binance.py --dry-run
    poetry run python scripts/audit/b4_restamp_binance.py --execute --i-have-a-fresh-backup \
        --ledger ~/b4_restamp_ledger.jsonl
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
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
    compare_tally,
    done_windows,
    label,
    read_ledger,
    restamp_windows,
)

DEFAULT_MANIFEST = ROOT / "results" / "b4_binance_stamp_boundaries.json"
MAX_ROWS_HARD_LIMIT = 5000  # skills/database.md: never more than 5000 rows per statement

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
SQL_STAGE = f"""
CREATE TEMP TABLE b4_stage ON COMMIT DROP AS
SELECT timestamp + make_interval(mins => interval) AS timestamp, pair, interval, exchange,
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
        help="JSONL resume ledger (windows already executed are skipped).",
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
    """Return an error message when the invocation must be refused."""
    if args.max_rows_per_tx <= 0 or args.max_rows_per_tx > MAX_ROWS_HARD_LIMIT:
        return f"--max-rows-per-tx must be in 1..{MAX_ROWS_HARD_LIMIT}"
    if not args.boundaries.exists():
        return f"manifest not found: {args.boundaries}"
    if is_tunnel_url(url):
        if args.execute:
            return "refusing --execute through the SSH tunnel (port 5433): run on the server"
        if not args.allow_tunnel:
            return "DATABASE_URL points to the tunnel (5433): add --allow-tunnel for a dry-run"
    if args.execute and not args.i_have_a_fresh_backup:
        return "--execute requires --i-have-a-fresh-backup"
    return None


def select_series(manifest: BoundaryManifest, args: argparse.Namespace) -> list[SeriesBoundary]:
    out = []
    for s in manifest.series:
        if args.pairs and s.pair not in args.pairs:
            continue
        if args.intervals and s.interval not in args.intervals:
            continue
        if s.last_open_stamped_ts is None or s.expected_restamps == 0:
            continue
        out.append(s)
    return out


async def run_window(
    conn: asyncpg.Connection,
    s: SeriesBoundary,
    w_start: datetime,
    w_end: datetime,
    execute: bool,
) -> LedgerEntry:
    params = (TARGET_EXCHANGE, s.pair, s.interval, w_start, w_end, s.last_open_stamped_ts)
    t0 = time.perf_counter()
    if not execute:
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
    async with conn.transaction():
        await conn.execute(SQL_STAGE, *params)
        staged = int(await conn.fetchval("SELECT COUNT(*) FROM b4_stage"))
        deleted = _count(await conn.execute(SQL_DELETE, *params))
        if deleted != staged:
            raise RuntimeError(
                f"{s.pair} {label(s.interval)} window {w_start}: staged {staged} != deleted {deleted}"
            )
        inserted = _count(await conn.execute(SQL_INSERT))
    return LedgerEntry(
        s.pair,
        s.interval,
        w_start,
        w_end,
        staged,
        deleted,
        inserted,
        staged - inserted,
        time.perf_counter() - t0,
        False,
    )


def format_tallies(tallies: list[SeriesTally], manifest: BoundaryManifest, dry_run: bool) -> str:
    lines = [
        "=" * 100,
        f"  B4.1 re-stamp {'DRY-RUN' if dry_run else 'EXECUTE'} — exchange='{TARGET_EXCHANGE}' "
        f"manifest={manifest.generated_at.isoformat()}",
        "=" * 100,
        f"  {'Series':<14} {'windows':>7} {'staged':>9} {'audit':>9} {'deleted':>9} "
        f"{'inserted':>9} {'collisions':>10} {'audit':>6}  Status",
    ]
    ok_all = True
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
        f"→ {'MATCH' if ok_all else 'MISMATCH — STOP'}"
    )
    return "\n".join(lines)


async def _async_main(args: argparse.Namespace) -> int:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    err = validate(args, url)
    if err:
        print(f"REFUSED: {err}")
        return 2
    manifest = BoundaryManifest.load(args.boundaries)
    series = select_series(manifest, args)
    already = done_windows(read_ledger(args.ledger)) if args.execute else set()
    print(
        f"mode={'EXECUTE' if args.execute else 'DRY-RUN'} series={len(series)} "
        f"max_rows_per_tx={args.max_rows_per_tx} ledger={args.ledger} resumed_windows={len(already)}"
    )

    conn = await asyncpg.connect(url, timeout=30)
    tallies: list[SeriesTally] = []
    started = datetime.now(UTC)
    try:
        await conn.execute("SET statement_timeout = '0'")
        await conn.execute("SET lock_timeout = '30s'")
        if not args.execute:
            await conn.execute("SET default_transaction_read_only = on")
        for s in series:
            tally = SeriesTally(s.pair, s.interval)
            tallies.append(tally)
            # windows already executed still count towards the tally (from the ledger)
            for e in read_ledger(args.ledger) if args.execute else []:
                if e.pair == s.pair and e.interval == s.interval and not e.dry_run:
                    tally.add(e)
            windows = restamp_windows(
                s.min_ts,
                s.last_open_stamped_ts,
                s.interval,
                args.max_rows_per_tx,  # type: ignore[arg-type]
            )
            skipped = 0
            t_series = time.perf_counter()
            for w_start, w_end in windows:
                if (s.pair, s.interval, w_start.isoformat()) in already:
                    skipped += 1
                    continue
                entry = await run_window(conn, s, w_start, w_end, args.execute)
                if args.execute:
                    append_ledger(args.ledger, entry)
                tally.add(entry)
                if entry.collisions:
                    print(
                        f"  collision(s) {s.pair} {label(s.interval)} window {w_start.isoformat()}: "
                        f"{entry.collisions} Vision row(s) dropped (existing end-stamped rows win)"
                    )
            print(
                f"  {s.pair} {label(s.interval)}: windows={len(windows)} skipped={skipped} "
                f"staged={tally.staged} collisions={tally.collisions} "
                f"({time.perf_counter() - t_series:.1f}s)"
            )
        if args.execute:
            print("  VACUUM ANALYZE market_data_ohlc …")
            await conn.execute("VACUUM ANALYZE market_data_ohlc")
    finally:
        await conn.close()

    print()
    print(format_tallies(tallies, manifest, not args.execute))
    print(f"  started={started.isoformat()} finished={datetime.now(UTC).isoformat()}")
    mismatch = any(compare_tally(t, manifest.get(t.pair, t.interval)) for t in tallies)  # type: ignore[arg-type]
    return 1 if mismatch else 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
