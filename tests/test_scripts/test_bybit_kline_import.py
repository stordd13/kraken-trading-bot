"""Bybit historical kline import: resume cursor, pagination, stop condition, dry-run, batching."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

_ENV_BEFORE = dict(os.environ)
from scripts.bybit_kline_import import (  # noqa: E402
    DEFAULT_SINCE,
    PAGE_LIMIT,
    format_table,
    import_pair_interval,
    parse_args,
    resolve_since,
)

# the script's load_dotenv() must not leak .env into other tests (BYBIT_TRADE_* etc.)
os.environ.clear()
os.environ.update(_ENV_BEFORE)


def _dt(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _candle(ts: datetime, interval: int) -> dict[str, Any]:
    return {
        "timestamp": ts,
        "pair": "BTC/USDC",
        "interval": interval,
        "open": Decimal("1"),
        "high": Decimal("1"),
        "low": Decimal("1"),
        "close": Decimal("1"),
        "volume": Decimal("0"),
        "vwap": None,
    }


class FakeRest:
    """Bybit-like: candles from `since` (open time) onward, ascending, `limit` per call."""

    def __init__(self, first_open: datetime, n: int, interval: int) -> None:
        step = timedelta(minutes=interval)
        self.series = [_candle(first_open + step * (i + 1), interval) for i in range(n)]
        self.interval = interval
        self.calls: list[datetime | None] = []

    async def fetch_ohlcv(self, pair, interval, since=None, limit=1000):
        self.calls.append(since)
        first_end = since + timedelta(minutes=interval)
        return [c for c in self.series if c["timestamp"] >= first_end][:limit]


def _db() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    result = MagicMock()
    result.rowcount = -1  # unknown → insert_candles counts the batch
    session.execute = AsyncMock(return_value=result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.session.return_value = cm
    return db, session


class TestResolveSince:
    def test_resume_from_max_when_history_present(self) -> None:
        bounds = (_dt(2025, 6, 11, 10), _dt(2026, 9, 11, 7, 4))
        since, resumed = resolve_since(bounds, DEFAULT_SINCE, 1, force_full=False)
        assert (since, resumed) == (_dt(2026, 9, 11, 7, 4), True)

    def test_resume_weekly_first_candle_five_days_after_opening(self) -> None:
        bounds = (_dt(2025, 6, 16), _dt(2026, 9, 7))  # first EU 1w candle closes 2025-06-16
        since, resumed = resolve_since(bounds, DEFAULT_SINCE, 10080, force_full=False)
        assert (since, resumed) == (_dt(2026, 9, 7), True)

    def test_leading_hole_triggers_full_scan(self) -> None:
        # collector wrote rows since 2026-09-09 but the 2025 history was never imported
        bounds = (_dt(2026, 9, 9, 13, 8), _dt(2026, 9, 11, 7, 4))
        since, resumed = resolve_since(bounds, DEFAULT_SINCE, 1, force_full=False)
        assert (since, resumed) == (DEFAULT_SINCE, False)

    def test_no_data_uses_default_floored(self) -> None:
        since, resumed = resolve_since(None, _dt(2025, 6, 1, 12, 34), 240, force_full=False)
        assert (since, resumed) == (_dt(2025, 6, 1, 12, 0), False)

    def test_force_full_ignores_bounds(self) -> None:
        bounds = (_dt(2025, 6, 16), _dt(2026, 9, 7))
        since, resumed = resolve_since(bounds, _dt(2025, 6, 4), 10080, force_full=True)
        assert (since, resumed) == (_dt(2025, 6, 2), False)  # Monday


class TestImportPairInterval:
    async def test_pagination_and_stop_reached_now(self) -> None:
        # 2 500 closed 1m candles → 3 pages; last page reaches the last closed candle
        first_open = _dt(2026, 9, 1)
        rest = FakeRest(first_open, 2500, 1)
        now = first_open + timedelta(minutes=2500, seconds=30)
        db, session = _db()

        stats = await import_pair_interval(
            rest, db, "bybit", "BTC/USDC", 1, since=first_open, resumed=False, now=now
        )

        assert stats.pages == 3 and stats.fetched == 2500 and stats.inserted == 2500
        assert stats.stop_reason == "reached_now"
        assert rest.calls == [
            first_open,
            first_open + timedelta(minutes=PAGE_LIMIT),
            first_open + timedelta(minutes=2 * PAGE_LIMIT),
        ]
        assert stats.first_ts == first_open + timedelta(minutes=1)
        assert stats.last_ts == first_open + timedelta(minutes=2500)
        assert session.execute.call_count == 3  # one batch of 1000 / 1000 / 500
        assert len(stats.last_responses) == 2 and stats.last_responses[-1]["candles"] == 500

    async def test_short_page_then_empty_is_end_of_history(self) -> None:
        first_open = _dt(2026, 9, 1)
        rest = FakeRest(first_open, 1200, 60)
        now = first_open + timedelta(hours=5000)  # far in the future → REST decides the end
        db, _ = _db()

        stats = await import_pair_interval(
            rest, db, "bybit", "BTC/USDC", 60, since=first_open, resumed=False, now=now
        )

        assert stats.pages == 3 and stats.stop_reason == "empty"
        assert stats.last_responses[0]["candles"] == 200
        assert stats.last_responses[1]["candles"] == 0
        assert stats.last_responses[1]["since"] == (first_open + timedelta(hours=1200)).isoformat()

    async def test_dry_run_only_estimates(self) -> None:
        first_open = _dt(2026, 9, 1)
        rest = FakeRest(first_open, 10, 1)
        stats = await import_pair_interval(
            rest,
            None,
            "bybit",
            "BTC/USDC",
            1,
            since=first_open,
            resumed=False,
            now=first_open + timedelta(minutes=2500),
            dry_run=True,
        )
        assert stats.stop_reason == "dry_run" and stats.pages == 0 and rest.calls == []
        assert stats.estimated_calls == 3

    async def test_already_current(self) -> None:
        rest = FakeRest(_dt(2026, 9, 1), 5, 1)
        stats = await import_pair_interval(
            rest, None, "bybit", "BTC/USDC", 1,
            since=_dt(2026, 9, 1, 0, 5), resumed=True, now=_dt(2026, 9, 1, 0, 5, 30),
        )  # fmt: skip
        assert stats.stop_reason == "already_current" and rest.calls == []

    async def test_misaligned_candle_raises(self) -> None:
        rest = MagicMock()
        rest.fetch_ohlcv = AsyncMock(return_value=[_candle(_dt(2026, 9, 1, 0, 0, 30), 1)])
        with pytest.raises(ValueError, match="misaligned"):
            await import_pair_interval(
                rest, _db()[0], "bybit", "BTC/USDC", 1,
                since=_dt(2026, 9, 1), resumed=False, now=_dt(2026, 9, 2),
            )  # fmt: skip

    async def test_not_advancing_stops(self) -> None:
        rest = MagicMock()
        rest.fetch_ohlcv = AsyncMock(return_value=[_candle(_dt(2026, 9, 1, 0, 0), 1)])
        stats = await import_pair_interval(
            rest, _db()[0], "bybit", "BTC/USDC", 1,
            since=_dt(2026, 9, 1), resumed=False, now=_dt(2026, 9, 2),
        )  # fmt: skip
        assert stats.stop_reason == "not_advancing" and stats.pages == 1


def test_parse_args_defaults() -> None:
    args = parse_args([])
    assert args.since == DEFAULT_SINCE and not args.force_full and not args.dry_run
    assert parse_args(["--since", "2025-07-01T00:00:00"]).since == _dt(2025, 7, 1)


def test_format_table_smoke() -> None:
    from scripts.bybit_kline_import import ImportStats

    text = format_table([ImportStats("BTC/USDC", 1, _dt(2025, 6, 1), False, pages=3)], 12.3)
    assert "BTC/USDC" in text and "total: pages=3" in text
