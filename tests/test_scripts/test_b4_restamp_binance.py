"""b4_restamp_binance.py: guards, window plan, DB progress resume, manifest comparison (mock DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

from b4_stamp_lib import (  # noqa: E402
    BoundaryManifest,
    LedgerEntry,
    SeriesBoundary,
    read_ledger,
    restamp_windows,
)

_ENV_BEFORE = dict(os.environ)
import b4_restamp_binance as restamp  # noqa: E402

# the script's load_dotenv() must not leak .env into other tests
os.environ.clear()
os.environ.update(_ENV_BEFORE)

T0 = datetime(2021, 1, 1, tzinfo=UTC)
GEN = datetime(2026, 9, 13, tzinfo=UTC)
URL = "postgresql+asyncpg://u:p@localhost:5432/krakenbot"


def _series(pair: str = "BTC/USDC", interval: int = 60, rows: int = 100) -> SeriesBoundary:
    step = timedelta(minutes=interval)
    return SeriesBoundary(
        pair=pair,
        interval=interval,
        rows=rows,
        min_ts=T0,
        max_ts=T0 + step * (rows - 1),
        last_open_stamped_ts=T0 + step * (rows - 1),
        first_end_stamped_ts=None,
        expected_restamps=rows,
        expected_collisions=0,
    )


def _manifest(tmp_path: Path, *series: SeriesBoundary) -> Path:
    m = BoundaryManifest(GEN, "test", "binance", "bybit", {"binance": 100}, list(series))
    p = tmp_path / "manifest.json"
    m.dump(p)
    return p


def _timestamps(n: int, interval: int, start: datetime = T0) -> list[datetime]:
    return [start + timedelta(minutes=interval) * i for i in range(n)]


class _FakeConn:
    """Stateful asyncpg stand-in: an in-memory binance series + progress table."""

    def __init__(
        self,
        timestamps: list[datetime],
        collide_at: set[datetime] | None = None,
        progress: list[LedgerEntry] | None = None,
        crash_after_commits: int | None = None,
    ) -> None:
        self.ts = set(timestamps)
        self.collide_at = collide_at or set()  # end-stamped rows outside the perimeter
        self.progress: list[LedgerEntry] = list(progress or [])
        self.executed: list[str] = []
        self.closed = False
        self.in_tx = False
        self.commits = 0
        self.crash_after_commits = crash_after_commits
        self._snapshot: tuple[set[datetime], list[LedgerEntry]] | None = None
        self._stage: list[datetime] = []

    # -- helpers -----------------------------------------------------------
    def _in_window(self, params: tuple) -> list[datetime]:
        _, _, interval, ws, we, boundary = params
        return sorted(t for t in self.ts if ws <= t < we and t <= boundary)

    # -- asyncpg surface ---------------------------------------------------
    async def execute(self, sql: str, *params: object) -> str:
        sql = sql.lstrip()
        head = sql.split()[0]
        self.executed.append(head if head != "INSERT" else "INSERT " + sql.split()[2])
        if sql.startswith("INSERT INTO b4_stage"):
            step = timedelta(minutes=int(params[2]))  # type: ignore[arg-type]
            self._stage = [t + step for t in self._in_window(params)]  # type: ignore[arg-type]
            return f"INSERT 0 {len(self._stage)}"
        if sql.startswith("DELETE"):
            rows = self._in_window(params)  # type: ignore[arg-type]
            self.ts -= set(rows)
            return f"DELETE {len(rows)}"
        if sql.startswith("INSERT INTO market_data_ohlc"):
            inserted = 0
            for t in self._stage:
                if t in self.ts or t in self.collide_at:
                    continue
                self.ts.add(t)
                inserted += 1
            return f"INSERT 0 {inserted}"
        if sql.startswith("INSERT INTO b4_restamp_progress"):
            self.progress.append(
                LedgerEntry(
                    params[0],
                    params[1],
                    params[2],
                    params[3],
                    params[4],
                    params[5],  # type: ignore[arg-type]
                    params[6],
                    params[7],
                    params[8],
                    False,
                    params[9],
                    params[10],
                    params[11],  # type: ignore[arg-type]
                )
            )
            return "INSERT 0 1"
        return "OK"

    async def fetchval(self, sql: str, *params: object) -> object:
        sql = sql.lstrip()
        if "pg_try_advisory_lock" in sql:
            return True
        if "to_regclass" in sql:
            return bool(self.progress)
        if "EXISTS" in sql:  # collisions in dry-run
            step = timedelta(minutes=int(params[2]))  # type: ignore[arg-type]
            return len([t for t in self._in_window(params) if t + step in self.collide_at])  # type: ignore[arg-type]
        if "timestamp = $4" in sql:  # slot occupied
            return 1 if params[3] in self.ts or params[3] in self.collide_at else 0
        if "timestamp < $4" in sql:  # pre-flight remaining originals
            return len([t for t in self.ts if t < params[3]])  # type: ignore[operator]
        return len(self._in_window(params))  # type: ignore[arg-type]

    async def fetch(self, sql: str, *params: object) -> list:
        sql = sql.lstrip()
        if sql.startswith("EXPLAIN"):
            return [("Seq Scan (fake plan)",)]
        if "FROM b4_restamp_progress" in sql:
            rows = [e for e in self.progress if e.pair == params[0] and e.interval == params[1]]
            return [
                {
                    "pair": e.pair,
                    "interval": e.interval,
                    "window_start": e.window_start,
                    "window_end": e.window_end,
                    "staged": e.staged,
                    "deleted": e.deleted,
                    "inserted": e.inserted,
                    "collisions": e.collisions,
                    "seconds": e.seconds,
                    "max_rows": e.max_rows,
                    "boundary": e.boundary,
                    "manifest_generated_at": e.manifest_generated_at,
                }
                for e in sorted(rows, key=lambda e: e.window_start, reverse=True)
            ]
        return []

    def transaction(self) -> MagicMock:
        conn = self

        class _Tx:
            async def __aenter__(self_inner) -> None:
                conn.in_tx = True
                conn._snapshot = (set(conn.ts), list(conn.progress))

            async def __aexit__(self_inner, exc_type, exc, tb) -> bool:
                conn.in_tx = False
                if exc_type is not None:  # rollback
                    conn.ts, conn.progress = conn._snapshot  # type: ignore[assignment]
                    return False
                conn.commits += 1
                if (
                    conn.crash_after_commits is not None
                    and conn.commits >= conn.crash_after_commits
                ):
                    raise KeyboardInterrupt("simulated crash right after COMMIT")
                return False

        return _Tx()  # type: ignore[return-value]

    async def close(self) -> None:
        self.closed = True


async def _run(conn: _FakeConn, argv: list[str], monkeypatch) -> int:
    monkeypatch.setenv("DATABASE_URL", URL)
    with patch.object(restamp.asyncpg, "connect", AsyncMock(return_value=conn)):
        return await restamp._async_main(restamp.parse_args(argv))


# ---------------------------------------------------------------------------
# validate / select_series
# ---------------------------------------------------------------------------


class TestValidate:
    def test_refuses_execute_through_tunnel(self, tmp_path: Path) -> None:
        args = restamp.parse_args(["--execute", "--boundaries", str(_manifest(tmp_path))])
        err = restamp.validate(args, "postgresql://u:p@localhost:5433/krakenbot")
        assert err is not None and "tunnel" in err

    def test_dry_run_through_tunnel_needs_flag(self, tmp_path: Path) -> None:
        m = str(_manifest(tmp_path))
        url = "postgresql://u:p@localhost:5433/krakenbot"
        assert "allow-tunnel" in (
            restamp.validate(restamp.parse_args(["--boundaries", m]), url) or ""
        )
        assert (
            restamp.validate(restamp.parse_args(["--boundaries", m, "--allow-tunnel"]), url) is None
        )

    def test_execute_needs_backup_flag_and_no_explain(self, tmp_path: Path) -> None:
        m = str(_manifest(tmp_path))
        url = "postgresql://u:p@localhost:5432/krakenbot"
        assert "backup" in (
            restamp.validate(restamp.parse_args(["--execute", "--boundaries", m]), url) or ""
        )
        args = restamp.parse_args(["--execute", "--i-have-a-fresh-backup", "--boundaries", m])
        assert restamp.validate(args, url) is None
        assert args.execute and not args.dry_run
        args = restamp.parse_args(
            ["--execute", "--i-have-a-fresh-backup", "--explain", "--boundaries", m]
        )
        assert "explain" in (restamp.validate(args, url) or "")

    def test_batch_bound_manifest_and_table_name(self, tmp_path: Path) -> None:
        url = "postgresql://u:p@localhost:5432/krakenbot"
        m = str(_manifest(tmp_path))
        args = restamp.parse_args(["--boundaries", m, "--max-rows-per-tx", "6000"])
        assert "max-rows-per-tx" in (restamp.validate(args, url) or "")
        args = restamp.parse_args(["--boundaries", str(tmp_path / "nope.json")])
        assert "not found" in (restamp.validate(args, url) or "")
        args = restamp.parse_args(["--boundaries", m, "--progress-table", "x; DROP TABLE y"])
        assert "progress-table" in (restamp.validate(args, url) or "")


class TestSelectSeries:
    def test_filters_and_skips_empty_perimeter(self, tmp_path: Path) -> None:
        empty = _series("SOL/USDC", 5)
        empty.expected_restamps = 0
        m = BoundaryManifest.load(
            _manifest(
                tmp_path,
                _series("BTC/USDC", 60),
                _series("ETH/USDC", 60),
                _series("BTC/USDC", 1),
                empty,
            )
        )
        mp = str(tmp_path / "manifest.json")
        sel, err = restamp.select_series(
            m, restamp.parse_args(["--pairs", "BTC/USDC", "--boundaries", mp])
        )
        assert err is None and [(s.pair, s.interval) for s in sel] == [
            ("BTC/USDC", 60),
            ("BTC/USDC", 1),
        ]
        sel, err = restamp.select_series(
            m, restamp.parse_args(["--intervals", "60", "5", "--boundaries", mp])
        )
        assert err is None and [(s.pair, s.interval) for s in sel] == [
            ("BTC/USDC", 60),
            ("ETH/USDC", 60),
        ]

    def test_unknown_filters_are_refused(self, tmp_path: Path) -> None:
        m = BoundaryManifest.load(_manifest(tmp_path, _series()))
        mp = str(tmp_path / "manifest.json")
        _, err = restamp.select_series(
            m, restamp.parse_args(["--pairs", "BTC", "--boundaries", mp])
        )
        assert err is not None and "unknown pair" in err
        _, err = restamp.select_series(
            m, restamp.parse_args(["--intervals", "7", "--boundaries", mp])
        )
        assert err is not None and "unknown interval" in err
        only = _series("SOL/USDC", 5)
        only.expected_restamps = 0
        m2 = BoundaryManifest.load(_manifest(tmp_path, only))
        _, err = restamp.select_series(m2, restamp.parse_args(["--boundaries", mp]))
        assert err == "no series selected"


async def test_unknown_pair_exit_code_2(tmp_path: Path, monkeypatch) -> None:
    conn = _FakeConn(_timestamps(100, 60))
    rc = await _run(
        conn, ["--pairs", "BTC", "--boundaries", str(_manifest(tmp_path, _series()))], monkeypatch
    )
    assert rc == 2 and not conn.closed  # refused before connecting


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------


async def test_dry_run_matches_manifest(tmp_path: Path, monkeypatch) -> None:
    conn = _FakeConn(_timestamps(100, 60))
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--boundaries",
        str(_manifest(tmp_path, _series())),
        "--max-rows-per-tx",
        "30",
        "--ledger",
        str(ledger),
        "--explain",
    ]
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 0
    assert "DELETE" not in conn.executed and "INSERT market_data_ohlc" not in conn.executed
    assert "CREATE" in conn.executed and "DROP" in conn.executed  # --explain temp table, dropped
    assert not ledger.exists() and conn.closed


async def test_dry_run_mismatch_returns_2_before_writes(tmp_path: Path, monkeypatch) -> None:
    conn = _FakeConn(_timestamps(90, 60))  # manifest says 100 → pre-flight refuses
    rc = await _run(
        conn,
        [
            "--boundaries",
            str(_manifest(tmp_path, _series())),
            "--ledger",
            str(tmp_path / "l.jsonl"),
        ],
        monkeypatch,
    )
    assert rc == 2


async def test_dry_run_collision_mismatch_returns_1(tmp_path: Path, monkeypatch) -> None:
    top = T0 + timedelta(hours=99)
    conn = _FakeConn(_timestamps(100, 60), collide_at={top + timedelta(hours=1)})
    rc = await _run(
        conn,
        [
            "--boundaries",
            str(_manifest(tmp_path, _series())),
            "--ledger",
            str(tmp_path / "l.jsonl"),
        ],
        monkeypatch,
    )
    assert rc == 1  # 1 collision found, audit says 0


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


async def test_execute_shifts_everything_and_records_progress(tmp_path: Path, monkeypatch) -> None:
    conn = _FakeConn(_timestamps(100, 60))
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, _series())),
        "--max-rows-per-tx",
        "30",
        "--ledger",
        str(ledger),
    ]
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 0
    assert conn.ts == set(_timestamps(100, 60, T0 + timedelta(hours=1)))  # every row at +1h
    assert len(conn.progress) == 4 and [e.staged for e in conn.progress] == [30, 30, 30, 10]
    assert conn.progress[0].window_start == T0 + timedelta(hours=70)  # newest first
    entries = read_ledger(ledger)
    assert [e.window for e in entries] == [e.window for e in conn.progress]
    assert entries[0].max_rows == 30 and entries[0].manifest_generated_at == GEN
    assert conn.executed[-1] == "VACUUM"


async def test_execute_resumes_from_db_progress_not_from_file(tmp_path: Path, monkeypatch) -> None:
    manifest = _manifest(tmp_path, _series())
    s = _series()
    plan = restamp_windows(s.min_ts, s.last_open_stamped_ts, 60, 30)  # type: ignore[arg-type]
    # the newest window (rows 90..99) was committed by a previous run; its JSONL line was lost
    done = LedgerEntry(
        "BTC/USDC", 60, *plan[0], 30, 30, 30, 0, 1.0, False, 30, s.last_open_stamped_ts, GEN
    )
    conn = _FakeConn(
        _timestamps(70, 60) + _timestamps(30, 60, T0 + timedelta(hours=71)), progress=[done]
    )
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(manifest),
        "--max-rows-per-tx",
        "30",
        "--ledger",
        str(ledger),
    ]
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 0
    assert conn.ts == set(_timestamps(100, 60, T0 + timedelta(hours=1)))
    assert len(conn.progress) == 4
    entries = read_ledger(ledger)
    assert entries[0].window == plan[0]  # the lost line was re-mirrored from the DB
    assert len(entries) == 4


async def test_execute_refuses_resume_with_other_batch_size(tmp_path: Path, monkeypatch) -> None:
    s = _series()
    plan = restamp_windows(s.min_ts, s.last_open_stamped_ts, 60, 30)  # type: ignore[arg-type]
    done = LedgerEntry(
        "BTC/USDC", 60, *plan[0], 30, 30, 30, 0, 1.0, False, 30, s.last_open_stamped_ts, GEN
    )
    conn = _FakeConn(
        _timestamps(70, 60) + _timestamps(30, 60, T0 + timedelta(hours=71)), progress=[done]
    )
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, s)),
        "--max-rows-per-tx",
        "20",
        "--ledger",
        str(tmp_path / "l.jsonl"),
    ]
    before = set(conn.ts)
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 2 and conn.ts == before and len(conn.progress) == 1


async def test_execute_refuses_non_prefix_progress(tmp_path: Path, monkeypatch) -> None:
    s = _series()
    plan = restamp_windows(s.min_ts, s.last_open_stamped_ts, 60, 30)  # type: ignore[arg-type]
    done = LedgerEntry(
        "BTC/USDC", 60, *plan[1], 30, 30, 30, 0, 1.0, False, 30, s.last_open_stamped_ts, GEN
    )
    conn = _FakeConn(_timestamps(100, 60), progress=[done])  # second window claimed done, first not
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, s)),
        "--max-rows-per-tx",
        "30",
        "--ledger",
        str(tmp_path / "l.jsonl"),
    ]
    before = set(conn.ts)
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 2 and conn.ts == before


async def test_execute_refuses_when_db_state_differs_from_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    conn = _FakeConn(_timestamps(99, 60))  # one row short of the audit
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, _series())),
        "--ledger",
        str(tmp_path / "l.jsonl"),
    ]
    before = set(conn.ts)
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 2 and conn.ts == before and not conn.progress


async def test_execute_crash_after_commit_is_resumable_without_double_shift(
    tmp_path: Path, monkeypatch
) -> None:
    conn = _FakeConn(_timestamps(100, 60), crash_after_commits=2)
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, _series())),
        "--max-rows-per-tx",
        "30",
        "--ledger",
        str(ledger),
    ]
    with pytest.raises(KeyboardInterrupt):
        await _run(conn, argv, monkeypatch)
    assert len(conn.progress) == 2 and len(read_ledger(ledger)) == 1  # 2nd COMMIT not mirrored
    conn.crash_after_commits = None
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 0
    assert conn.ts == set(_timestamps(100, 60, T0 + timedelta(hours=1)))  # no double shift, no loss
    assert len(conn.progress) == 4 and len(read_ledger(ledger)) == 4


async def test_execute_unexpected_collision_rolls_back_and_stops(
    tmp_path: Path, monkeypatch
) -> None:
    top = T0 + timedelta(hours=99)
    conn = _FakeConn(_timestamps(100, 60), collide_at={top + timedelta(hours=1)})  # audit said 0
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, _series())),
        "--ledger",
        str(ledger),
    ]
    before = set(conn.ts)
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 3
    assert conn.ts == before and not conn.progress and not ledger.exists()  # rolled back
    assert "VACUUM" not in conn.executed


async def test_execute_allowed_collision_is_counted(tmp_path: Path, monkeypatch) -> None:
    s = _series()
    s.expected_collisions = 1
    top = T0 + timedelta(hours=99)
    conn = _FakeConn(_timestamps(100, 60), collide_at={top + timedelta(hours=1)})
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, s)),
        "--ledger",
        str(ledger),
    ]
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 0
    e = read_ledger(ledger)[0]
    assert (e.staged, e.deleted, e.inserted, e.collisions) == (100, 100, 99, 1)


async def test_execute_occupied_slot_guard(tmp_path: Path, monkeypatch) -> None:
    # a stray end-stamped row sits inside the perimeter's target grid (not at the top): the window
    # that would shift into it must stop before deleting anything
    stray = T0 + timedelta(hours=70)  # target slot of window [T0+40h, T0+70h) with max_rows=30
    conn = _FakeConn(_timestamps(100, 60), collide_at={stray})
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(_manifest(tmp_path, _series())),
        "--max-rows-per-tx",
        "30",
        "--ledger",
        str(ledger),
    ]
    rc = await _run(conn, argv, monkeypatch)
    assert rc == 3
    assert len(conn.progress) == 1  # only the newest window committed


async def test_refused_invocation_exit_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5433/krakenbot")
    args = restamp.parse_args(
        ["--execute", "--i-have-a-fresh-backup", "--boundaries", str(_manifest(tmp_path))]
    )
    with patch.object(restamp.asyncpg, "connect", AsyncMock()) as connect:
        assert await restamp._async_main(args) == 2
    connect.assert_not_awaited()


def test_count_parsing_and_tunnel_detection() -> None:
    assert restamp._count("DELETE 123") == 123
    assert restamp._count("INSERT 0 45") == 45
    assert restamp.is_tunnel_url("postgresql://u:p@localhost:5433/krakenbot")
    assert not restamp.is_tunnel_url("postgresql://u:p@localhost:5432/krakenbot")
