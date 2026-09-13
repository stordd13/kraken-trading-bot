"""b4_restamp_binance.py: guards, window plan, ledger resume, manifest comparison (mock DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

from b4_stamp_lib import (  # noqa: E402
    BoundaryManifest,
    LedgerEntry,
    SeriesBoundary,
    append_ledger,
    read_ledger,
)

_ENV_BEFORE = dict(os.environ)
import b4_restamp_binance as restamp  # noqa: E402

# the script's load_dotenv() must not leak .env into other tests
os.environ.clear()
os.environ.update(_ENV_BEFORE)

T0 = datetime(2021, 1, 1, tzinfo=UTC)


def _series(pair: str = "BTC/USDC", interval: int = 60, rows: int = 100) -> SeriesBoundary:
    return SeriesBoundary(
        pair=pair,
        interval=interval,
        rows=rows,
        min_ts=T0,
        max_ts=T0 + timedelta(minutes=interval) * (rows - 1),
        last_open_stamped_ts=T0 + timedelta(minutes=interval) * (rows - 1),
        first_end_stamped_ts=None,
        expected_restamps=rows,
        expected_collisions=0,
    )


def _manifest(tmp_path: Path, *series: SeriesBoundary) -> Path:
    m = BoundaryManifest(T0, "test", "binance", "bybit", {"binance": 100}, list(series))
    p = tmp_path / "manifest.json"
    m.dump(p)
    return p


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

    def test_execute_needs_backup_flag(self, tmp_path: Path) -> None:
        m = str(_manifest(tmp_path))
        url = "postgresql://u:p@localhost:5432/krakenbot"
        assert "backup" in (
            restamp.validate(restamp.parse_args(["--execute", "--boundaries", m]), url) or ""
        )
        args = restamp.parse_args(["--execute", "--i-have-a-fresh-backup", "--boundaries", m])
        assert restamp.validate(args, url) is None
        assert args.execute and not args.dry_run

    def test_batch_bound_and_missing_manifest(self, tmp_path: Path) -> None:
        url = "postgresql://u:p@localhost:5432/krakenbot"
        args = restamp.parse_args(
            ["--boundaries", str(_manifest(tmp_path)), "--max-rows-per-tx", "6000"]
        )
        assert "max-rows-per-tx" in (restamp.validate(args, url) or "")
        args = restamp.parse_args(["--boundaries", str(tmp_path / "nope.json")])
        assert "not found" in (restamp.validate(args, url) or "")


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
        args = restamp.parse_args(
            ["--pairs", "BTC/USDC", "--boundaries", str(tmp_path / "manifest.json")]
        )
        assert [(s.pair, s.interval) for s in restamp.select_series(m, args)] == [
            ("BTC/USDC", 60),
            ("BTC/USDC", 1),
        ]
        args = restamp.parse_args(
            ["--intervals", "60", "5", "--boundaries", str(tmp_path / "manifest.json")]
        )
        assert [(s.pair, s.interval) for s in restamp.select_series(m, args)] == [
            ("BTC/USDC", 60),
            ("ETH/USDC", 60),
        ]


class _FakeConn:
    """Minimal asyncpg stand-in: counts per window from an in-memory series."""

    def __init__(self, timestamps: list[datetime], collide_at: set[datetime] | None = None) -> None:
        self.ts = sorted(timestamps)
        self.collide_at = collide_at or set()
        self.executed: list[str] = []
        self.closed = False

    def _in_window(self, params: tuple) -> list[datetime]:
        _, _, _, ws, we, boundary = params
        return [t for t in self.ts if ws <= t < we and t <= boundary]

    async def execute(self, sql: str, *params: object) -> str:
        sql = sql.lstrip()
        self.executed.append(sql.split()[0])
        if sql.startswith("DELETE"):
            rows = self._in_window(params)  # type: ignore[arg-type]
            self.ts = [t for t in self.ts if t not in rows]
            return f"DELETE {len(rows)}"
        if sql.startswith("INSERT"):
            n = self._staged - len([t for t in self._staged_ts if t in self.collide_at])
            return f"INSERT 0 {n}"
        if sql.startswith("CREATE TEMP"):
            self._staged_ts = self._in_window(params)  # type: ignore[arg-type]
            self._staged = len(self._staged_ts)
        return "SET"

    async def fetchval(self, sql: str, *params: object) -> int:
        sql = sql.lstrip()
        if "b4_stage" in sql:
            return self._staged
        if "EXISTS" in sql:
            return len([t for t in self._in_window(params) if t in self.collide_at])  # type: ignore[arg-type]
        return len(self._in_window(params))  # type: ignore[arg-type]

    def transaction(self) -> MagicMock:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=None)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    async def close(self) -> None:
        self.closed = True


def _timestamps(n: int, interval: int) -> list[datetime]:
    return [T0 + timedelta(minutes=interval) * i for i in range(n)]


async def test_dry_run_matches_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/krakenbot")
    conn = _FakeConn(_timestamps(100, 60))
    ledger = tmp_path / "ledger.jsonl"
    with patch.object(restamp.asyncpg, "connect", AsyncMock(return_value=conn)):
        rc = await restamp._async_main(
            restamp.parse_args(
                [
                    "--boundaries",
                    str(_manifest(tmp_path, _series())),
                    "--max-rows-per-tx",
                    "30",
                    "--ledger",
                    str(ledger),
                ]
            )
        )
    assert rc == 0
    assert "DELETE" not in conn.executed and "INSERT" not in conn.executed
    assert not ledger.exists()  # dry-run never writes the ledger
    assert conn.closed


async def test_dry_run_mismatch_returns_1(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/krakenbot")
    conn = _FakeConn(_timestamps(90, 60))  # manifest says 100
    with patch.object(restamp.asyncpg, "connect", AsyncMock(return_value=conn)):
        rc = await restamp._async_main(
            restamp.parse_args(
                [
                    "--boundaries",
                    str(_manifest(tmp_path, _series())),
                    "--ledger",
                    str(tmp_path / "l.jsonl"),
                ]
            )
        )
    assert rc == 1


async def test_execute_writes_ledger_and_resumes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/krakenbot")
    manifest = _manifest(tmp_path, _series())
    ledger = tmp_path / "ledger.jsonl"
    # pretend the newest window (rows 70..99 → [T0+70h, T0+100h)) was already committed
    done = LedgerEntry(
        "BTC/USDC",
        60,
        T0 + timedelta(hours=70),
        T0 + timedelta(hours=100),
        30,
        30,
        30,
        0,
        1.0,
        False,
    )
    append_ledger(ledger, done)
    conn = _FakeConn(_timestamps(70, 60))  # those 30 rows are already gone from the "DB"
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
    with patch.object(restamp.asyncpg, "connect", AsyncMock(return_value=conn)):
        rc = await restamp._async_main(restamp.parse_args(argv))
    assert rc == 0
    entries = read_ledger(ledger)
    assert len(entries) == 4  # 1 resumed + 3 new windows (30, 30, 10 rows)
    assert [e.staged for e in entries[1:]] == [30, 30, 10]
    assert entries[1].window_start == T0 + timedelta(hours=40)  # newest first
    assert conn.executed.count("DELETE") == 3 and conn.executed.count("INSERT") == 3
    assert conn.executed[-1] == "VACUUM"


async def test_execute_counts_collisions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/krakenbot")
    s = _series()
    s.expected_collisions = 1
    manifest = _manifest(tmp_path, s)
    top = T0 + timedelta(hours=99)
    conn = _FakeConn(_timestamps(100, 60), collide_at={top})
    ledger = tmp_path / "ledger.jsonl"
    argv = [
        "--execute",
        "--i-have-a-fresh-backup",
        "--boundaries",
        str(manifest),
        "--ledger",
        str(ledger),
    ]
    with patch.object(restamp.asyncpg, "connect", AsyncMock(return_value=conn)):
        rc = await restamp._async_main(restamp.parse_args(argv))
    assert rc == 0
    e = read_ledger(ledger)[0]
    assert (e.staged, e.deleted, e.inserted, e.collisions) == (100, 100, 99, 1)


def test_refused_invocation_exit_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5433/krakenbot")
    rc = restamp.main(
        ["--execute", "--i-have-a-fresh-backup", "--boundaries", str(_manifest(tmp_path))]
    )
    assert rc == 2


def test_count_parsing() -> None:
    assert restamp._count("DELETE 123") == 123
    assert restamp._count("INSERT 0 45") == 45
    assert restamp.is_tunnel_url("postgresql://u:p@localhost:5433/krakenbot")
    assert not restamp.is_tunnel_url("postgresql://u:p@localhost:5432/krakenbot")
