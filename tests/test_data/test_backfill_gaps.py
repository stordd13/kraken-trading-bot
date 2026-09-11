"""Gap detection: pure grid helpers, LAG rows → gaps, tail gap, detect_gaps with a fake session."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.data import backfill
from krakenbot.data.backfill import (
    Gap,
    detect_gaps,
    fetch_max_timestamps,
    fetch_timestamp_bounds,
    floor_to_grid,
    internal_gaps_from_rows,
    is_grid_aligned,
    last_closed_timestamp,
    tail_gap,
)

T = datetime(2026, 9, 11, 1, 6, 30, tzinfo=UTC)  # Friday


def _dt(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _read_session_db(rows_per_call: list[list[tuple]]) -> tuple[MagicMock, AsyncMock]:
    """DatabaseManager mock whose read_session().execute() returns scripted rows."""
    session = AsyncMock()
    results = []
    for rows in rows_per_call:
        r = MagicMock()
        r.all.return_value = rows
        results.append(r)
    session.execute = AsyncMock(side_effect=results)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.read_session.return_value = cm
    return db, session


class TestGrid:
    @pytest.mark.parametrize(
        ("now", "interval", "expected"),
        [
            (_dt(2026, 9, 11, 1, 6, 30), 1, _dt(2026, 9, 11, 1, 6)),
            (_dt(2026, 9, 11, 1, 6, 0), 1, _dt(2026, 9, 11, 1, 6)),
            (_dt(2026, 9, 11, 1, 6, 30), 5, _dt(2026, 9, 11, 1, 5)),
            (_dt(2026, 9, 11, 7, 4, 30), 240, _dt(2026, 9, 11, 4, 0)),
            (_dt(2026, 9, 11, 7, 4, 30), 1440, _dt(2026, 9, 11, 0, 0)),
            # 1w anchored on Monday 00:00 UTC (2026-09-07), not on the epoch Thursday
            (_dt(2026, 9, 11, 7, 4, 30), 10080, _dt(2026, 9, 7, 0, 0)),
            (_dt(2026, 9, 7, 0, 0, 0), 10080, _dt(2026, 9, 7, 0, 0)),
        ],
    )
    def test_floor_to_grid(self, now: datetime, interval: int, expected: datetime) -> None:
        assert floor_to_grid(now, interval) == expected
        assert last_closed_timestamp(now, interval) == expected

    def test_weekly_anchor_is_monday(self) -> None:
        for weeks in range(1, 60):
            assert floor_to_grid(_dt(2026, 9, 7) + timedelta(weeks=weeks), 10080).weekday() == 0

    def test_is_grid_aligned(self) -> None:
        assert is_grid_aligned(_dt(2026, 9, 11, 1, 5), 1)
        assert is_grid_aligned(_dt(2026, 9, 11, 1, 5), 5)
        assert not is_grid_aligned(_dt(2026, 9, 11, 1, 6), 5)
        assert not is_grid_aligned(_dt(2026, 9, 11, 1, 5, 0, 500), 1)
        assert is_grid_aligned(_dt(2026, 9, 7), 10080)
        assert not is_grid_aligned(_dt(2026, 9, 10), 10080)  # a Thursday (epoch-aligned)

    def test_naive_datetime_treated_as_utc(self) -> None:
        assert floor_to_grid(datetime(2026, 9, 11, 1, 6, 30), 1) == _dt(2026, 9, 11, 1, 6)

    def test_invalid_interval(self) -> None:
        with pytest.raises(ValueError):
            floor_to_grid(T, 0)


class TestGapDataclass:
    def test_missing_count(self) -> None:
        assert Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 5)).missing == 1
        assert Gap("BTC/USDC", 1, _dt(2026, 9, 9, 14, 8), _dt(2026, 9, 9, 18, 12)).missing == 245
        assert Gap("BTC/USDC", 60, _dt(2026, 9, 9, 15), _dt(2026, 9, 9, 18)).missing == 4


class TestInternalGaps:
    def test_single_missing_minute(self) -> None:
        rows = [("BTC/USDC", 1, _dt(2026, 9, 11, 1, 4), _dt(2026, 9, 11, 1, 6))]
        assert internal_gaps_from_rows(rows) == [
            Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 5))
        ]

    @pytest.mark.parametrize(
        ("interval", "prev", "nxt", "start", "end", "missing"),
        [
            (1, _dt(2026, 9, 9, 14, 7), _dt(2026, 9, 9, 18, 13), _dt(2026, 9, 9, 14, 8), _dt(2026, 9, 9, 18, 12), 245),
            (5, _dt(2026, 9, 9, 14, 5), _dt(2026, 9, 9, 18, 15), _dt(2026, 9, 9, 14, 10), _dt(2026, 9, 9, 18, 10), 49),
            (15, _dt(2026, 9, 9, 14, 0), _dt(2026, 9, 9, 18, 15), _dt(2026, 9, 9, 14, 15), _dt(2026, 9, 9, 18, 0), 16),
            (60, _dt(2026, 9, 9, 14, 0), _dt(2026, 9, 9, 19, 0), _dt(2026, 9, 9, 15, 0), _dt(2026, 9, 9, 18, 0), 4),
        ],
    )  # fmt: skip
    def test_long_hole(self, interval, prev, nxt, start, end, missing) -> None:
        (gap,) = internal_gaps_from_rows([("SOL/USDC", interval, prev, nxt)])
        assert (gap.start, gap.end, gap.missing) == (start, end, missing)

    def test_contiguous_rows_are_not_gaps(self) -> None:
        # Defensive: SQL only returns real gaps, but a contiguous row must be ignored anyway
        rows = [("BTC/USDC", 1, _dt(2026, 9, 11, 1, 4), _dt(2026, 9, 11, 1, 5))]
        assert internal_gaps_from_rows(rows) == []

    def test_no_rows(self) -> None:
        assert internal_gaps_from_rows([]) == []


class TestTailGap:
    def test_tail_gap_excludes_in_progress_candle(self) -> None:
        # now = 01:06:30 → last closed 1m candle is 01:06; 01:07 is in progress
        gap = tail_gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 4), T)
        assert gap == Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 6))

    def test_current_series_has_no_tail_gap(self) -> None:
        assert tail_gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 6), T) is None

    def test_future_candle_is_ignored(self) -> None:
        assert tail_gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 7), T) is None

    def test_no_baseline(self) -> None:
        assert tail_gap("BTC/USDC", 1, None, T) is None

    def test_daily_tail(self) -> None:
        gap = tail_gap("ETH/USDC", 1440, _dt(2026, 9, 9), _dt(2026, 9, 11, 7, 4))
        assert gap == Gap("ETH/USDC", 1440, _dt(2026, 9, 10), _dt(2026, 9, 11))


class TestDetectGaps:
    async def test_combines_internal_and_tail(self) -> None:
        lag_rows = [("BTC/USDC", 1, _dt(2026, 9, 11, 1, 4), _dt(2026, 9, 11, 1, 6))]
        max_rows = [
            ("BTC/USDC", 1, _dt(2026, 9, 9), _dt(2026, 9, 11, 1, 6)),
            ("BTC/USDC", 5, _dt(2026, 9, 9), _dt(2026, 9, 11, 0, 55)),
        ]
        db, session = _read_session_db([lag_rows, max_rows])

        gaps = await detect_gaps(db, "anyx", ["BTC/USDC"], [1, 5], now=_dt(2026, 9, 11, 1, 6, 30))

        assert gaps == [
            Gap("BTC/USDC", 1, _dt(2026, 9, 11, 1, 5), _dt(2026, 9, 11, 1, 5)),
            # settle margin (15 s): last closed 5m candle at 01:06:15 is 01:05
            Gap("BTC/USDC", 5, _dt(2026, 9, 11, 1, 0), _dt(2026, 9, 11, 1, 5)),
        ]
        # exchange comes from the caller, never from a literal
        params = session.execute.call_args_list[0].args[1]
        assert params["exchange"] == "anyx"
        assert params["pairs"] == ["BTC/USDC"]
        assert params["intervals"] == [1, 5]
        assert "since" not in params

    async def test_lookback_adds_since_param(self) -> None:
        db, session = _read_session_db([[], []])
        now = _dt(2026, 9, 11, 1, 6, 30)
        await detect_gaps(db, "anyx", ["BTC/USDC"], [1], now=now, lookback=timedelta(days=3))
        stmt, params = session.execute.call_args_list[0].args
        assert params["since"] == now - timedelta(days=3)
        assert "timestamp >= :since" in str(stmt)

    async def test_no_rows_no_gaps(self) -> None:
        db, _ = _read_session_db([[], []])
        assert await detect_gaps(db, "anyx", ["BTC/USDC"], [1], now=T) == []

    async def test_fetch_max_timestamps_fills_missing_keys(self) -> None:
        rows = [("BTC/USDC", 1, _dt(2026, 9, 9, 13, 8), _dt(2026, 9, 11, 1, 6))]
        db, _ = _read_session_db([rows])
        res = await fetch_max_timestamps(db, "anyx", ["BTC/USDC", "ETH/USDC"], [1])
        assert res == {("BTC/USDC", 1): _dt(2026, 9, 11, 1, 6), ("ETH/USDC", 1): None}

    async def test_fetch_timestamp_bounds(self) -> None:
        rows = [("BTC/USDC", 1, _dt(2026, 9, 9, 13, 8), _dt(2026, 9, 11, 1, 6))]
        db, _ = _read_session_db([rows])
        res = await fetch_timestamp_bounds(db, "anyx", ["BTC/USDC", "ETH/USDC"], [1])
        assert res == {
            ("BTC/USDC", 1): (_dt(2026, 9, 9, 13, 8), _dt(2026, 9, 11, 1, 6)),
            ("ETH/USDC", 1): None,
        }


def test_no_exchange_literal_in_backfill_module() -> None:
    source = inspect.getsource(backfill)
    code_only = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(("#", '"""', "*"))
    )
    # docstrings mention Bybit/Binance/Kraken on purpose; executable code must not
    body = code_only.split('"""')
    executable = "".join(body[0::2])
    for literal in ('"kraken"', '"binance"', '"bybit"', "'kraken'", "'binance'", "'bybit'"):
        assert literal not in executable
