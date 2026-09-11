"""fill_gap / backfill_gaps / insert_candles with a scripted REST client and a mock DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.data import backfill
from krakenbot.data.backfill import (
    Gap,
    backfill_gaps,
    candle_to_row,
    fill_gap,
    insert_candles,
)


def _dt(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _candle(
    ts: datetime, interval: int = 1, volume: str = "1.5", vwap: str | None = "100.1"
) -> dict:
    return {
        "timestamp": ts,
        "pair": "BTC/USDC",
        "interval": interval,
        "open": Decimal("100"),
        "high": Decimal("101"),
        "low": Decimal("99"),
        "close": Decimal("100.5"),
        "volume": Decimal(volume),
        "vwap": Decimal(vwap) if vwap is not None else None,
    }


def _series(start: datetime, n: int, interval: int = 1) -> list[dict]:
    return [_candle(start + timedelta(minutes=interval * i), interval) for i in range(n)]


class FakeRest:
    """Returns the candles of a scripted series from `since` (open time) onward, `limit` at a time."""

    def __init__(self, series: list[dict], interval: int = 1) -> None:
        self.series = sorted(series, key=lambda c: c["timestamp"])
        self.interval = interval
        self.calls: list[dict[str, Any]] = []

    async def fetch_ohlcv(self, pair, interval, since=None, limit=1000):
        self.calls.append({"pair": pair, "interval": interval, "since": since, "limit": limit})
        first_end = since + timedelta(minutes=interval)
        page = [c for c in self.series if c["timestamp"] >= first_end][:limit]
        return page


def _db(rowcount: int | None = None) -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    result = MagicMock()
    result.rowcount = rowcount if rowcount is not None else -1
    session.execute = AsyncMock(return_value=result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.session.return_value = cm
    return db, session


@pytest.fixture
def captured_inserts():
    """Patch insert_candles: record the rows of every call, return their count."""
    calls: list[list[dict]] = []

    async def _fake_insert(session, rows, *, batch_size=1000):
        calls.append(list(rows))
        return len(rows)

    with patch.object(backfill, "insert_candles", _fake_insert):
        yield calls


def _inserted_rows(calls: list[list[dict]]) -> list[dict]:
    return [row for batch in calls for row in batch]


class TestInsertCandles:
    async def test_batches_and_rowcount(self) -> None:
        _, session = _db(rowcount=1000)
        rows = [candle_to_row(c, "anyx") for c in _series(_dt(2026, 1, 1), 2500)]
        inserted = await insert_candles(session, rows, batch_size=1000)
        assert session.execute.call_count == 3
        assert inserted == 3000  # rowcount mocked to 1000 per statement
        stmt = session.execute.call_args_list[0].args[0]
        assert "ON CONFLICT" in str(stmt.compile(compile_kwargs={"literal_binds": False}))

    async def test_unknown_rowcount_falls_back_to_batch_len(self) -> None:
        _, session = _db(rowcount=-1)
        rows = [candle_to_row(c, "anyx") for c in _series(_dt(2026, 1, 1), 3)]
        assert await insert_candles(session, rows) == 3

    def test_candle_to_row_flat_candle(self) -> None:
        row = candle_to_row(_candle(_dt(2026, 1, 1), volume="0", vwap=None), "anyx")
        assert row["exchange"] == "anyx"
        assert row["volume"] == Decimal("0")
        assert row["vwap"] is None
        assert row["trades_count"] is None


class TestFillGap:
    async def test_single_missing_candle(self, captured_inserts) -> None:
        gap = Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 5))
        rest = FakeRest(_series(_dt(2026, 9, 11, 1, 0), 10))
        db, _ = _db()

        res = await fill_gap(rest, db, gap, "anyx")

        assert rest.calls[0]["since"] == _dt(2026, 9, 11, 1, 4)  # open time of the missing candle
        assert res.pages == 1 and res.inserted == 1 and res.error is None
        rows = _inserted_rows(captured_inserts)
        assert [r["timestamp"] for r in rows] == [_dt(2026, 9, 11, 1, 5)]  # out-of-gap rows dropped
        assert rows[0]["exchange"] == "anyx"
        assert rows[0]["vwap"] == Decimal("100.1")

    async def test_pagination_advances_from_last_timestamp(self, captured_inserts) -> None:
        start, end = _dt(2026, 9, 9, 14, 8), _dt(2026, 9, 9, 18, 12)  # 245 candles
        gap = Gap("BTC/USDC", 1, start, end)
        rest = FakeRest(_series(_dt(2026, 9, 9, 13, 0), 400))
        db, _ = _db()

        res = await fill_gap(rest, db, gap, "anyx", fetch_limit=100)

        assert res.pages == 3 and res.stop_reason == "completed"
        assert rest.calls[0]["since"] == start - timedelta(minutes=1)
        assert rest.calls[1]["since"] == start + timedelta(minutes=99)  # last ts of page 1
        assert res.inserted == 245
        timestamps = [r["timestamp"] for r in _inserted_rows(captured_inserts)]
        assert len(timestamps) == 245 and timestamps[0] == start and timestamps[-1] == end

    async def test_empty_batch_stops(self) -> None:
        gap = Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 5))
        rest = FakeRest([])
        db, session = _db()
        res = await fill_gap(rest, db, gap, "anyx")
        assert res.stop_reason == "empty_batch" and res.inserted == 0
        session.execute.assert_not_called()

    async def test_not_advancing_stops(self) -> None:
        gap = Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 9))
        stuck = MagicMock()
        stuck.fetch_ohlcv = AsyncMock(return_value=[_candle(_dt(2026, 9, 11, 1, 4))])  # <= since
        db, _ = _db()
        res = await fill_gap(stuck, db, gap, "anyx")
        assert res.stop_reason == "not_advancing" and res.pages == 1

    async def test_max_iterations_guard(self) -> None:
        gap = Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 9))
        endless = MagicMock()
        # always one candle *before* the gap but after since → advances by 1 s forever
        counter = {"n": 0}

        async def _fetch(pair, interval, since=None, limit=1000):
            counter["n"] += 1
            return [_candle(since + timedelta(seconds=1))]

        endless.fetch_ohlcv = _fetch
        db, _ = _db()
        res = await fill_gap(endless, db, gap, "anyx", fetch_limit=1)
        assert res.stop_reason == "max_iterations"
        assert counter["n"] == 5 + 2  # ceil(5/1) + MAX_EXTRA_PAGES

    async def test_misaligned_candle_raises(self) -> None:
        gap = Gap("BTC/USDC", 5, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 5))
        bad = MagicMock()
        bad.fetch_ohlcv = AsyncMock(return_value=[_candle(_dt(2026, 9, 11, 1, 5), interval=5)])
        good_res = await fill_gap(bad, _db(rowcount=1)[0], gap, "anyx")
        assert good_res.inserted == 1
        bad.fetch_ohlcv = AsyncMock(return_value=[_candle(_dt(2026, 9, 11, 1, 6), interval=5)])
        gap2 = Gap("BTC/USDC", 5, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 10))
        with pytest.raises(ValueError, match="misaligned"):
            await fill_gap(bad, _db()[0], gap2, "anyx")


class TestBackfillGaps:
    @staticmethod
    def _db_with_gaps(lag_rows, max_rows, rowcount=1):
        db, session = _db(rowcount=rowcount)
        read_session = AsyncMock()
        results = []
        for rows in (lag_rows, max_rows):
            r = MagicMock()
            r.all.return_value = rows
            results.append(r)
        read_session.execute = AsyncMock(side_effect=results)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=read_session)
        cm.__aexit__ = AsyncMock(return_value=False)
        db.read_session.return_value = cm
        return db, session

    async def test_dry_run_never_fetches_or_writes(self) -> None:
        lag = [("BTC/USDC", 1, _dt(2026, 9, 11, 1, 4), _dt(2026, 9, 11, 1, 6))]
        mx = [("BTC/USDC", 1, _dt(2026, 9, 9), _dt(2026, 9, 11, 1, 6))]
        db, session = self._db_with_gaps(lag, mx)
        rest = MagicMock()
        rest.fetch_ohlcv = AsyncMock()

        summary = await backfill_gaps(
            rest, db, "anyx", ["BTC/USDC"], [1], now=_dt(2026, 9, 11, 1, 6, 30), dry_run=True
        )

        assert summary.gaps_found == 1 and summary.gaps_filled == 0
        assert summary.candles_inserted == 0
        rest.fetch_ohlcv.assert_not_called()
        session.execute.assert_not_called()

    async def test_one_failing_gap_does_not_stop_the_run(self) -> None:
        lag = [
            ("BTC/USDC", 1, _dt(2026, 9, 11, 1, 4), _dt(2026, 9, 11, 1, 6)),
            ("SOL/USDC", 1, _dt(2026, 9, 11, 1, 4), _dt(2026, 9, 11, 1, 6)),
        ]
        mx = [
            ("BTC/USDC", 1, _dt(2026, 9, 9), _dt(2026, 9, 11, 1, 6)),
            ("SOL/USDC", 1, _dt(2026, 9, 9), _dt(2026, 9, 11, 1, 6)),
        ]
        db, _ = self._db_with_gaps(lag, mx)

        async def _fetch(pair, interval, since=None, limit=1000):
            if pair == "BTC/USDC":
                raise RuntimeError("boom")
            return [{**_candle(_dt(2026, 9, 11, 1, 5)), "pair": "SOL/USDC"}]

        rest = MagicMock()
        rest.fetch_ohlcv = _fetch
        summary = await backfill_gaps(
            rest, db, "anyx", ["BTC/USDC", "SOL/USDC"], [1], now=_dt(2026, 9, 11, 1, 6, 30)
        )
        assert summary.gaps_found == 2 and summary.gaps_filled == 1
        assert [f.gap.pair for f in summary.failures] == ["BTC/USDC"]
        assert "boom" in summary.failures[0].error
        assert summary.candles_inserted == 1
