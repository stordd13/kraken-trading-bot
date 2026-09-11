"""TaskScheduler: injected exchange client, single cron job, run logging and events."""

from __future__ import annotations

from datetime import UTC, datetime
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.core.event_bus import EventType
from krakenbot.data.backfill import BackfillSummary, Gap, GapResult
from krakenbot.scheduler import task_scheduler as ts_module
from krakenbot.scheduler.task_scheduler import JOB_ID, RUN_ROW_PAIR, TaskScheduler


def _settings(exchange: str = "bybit", enabled: bool = True) -> MagicMock:
    s = MagicMock()
    s.exchange_name = exchange
    s.scheduler.enabled = enabled
    s.scheduler.timezone = "UTC"
    s.scheduler.daily_backfill_cron = "30 3 * * *"
    s.scheduler.backfill_days = 3
    s.scheduler.pairs = ["BTC/USDC", "ETH/USDC"]
    s.scheduler.intervals = [1, 60]
    s.scheduler.batch_size = 1000
    return s


def _db() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    session.add_all = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.session.return_value = cm
    return db, session


def _bus() -> MagicMock:
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


class TestLifecycle:
    async def test_start_registers_single_job_with_settings_cron(self) -> None:
        rest = MagicMock()
        rest.close = AsyncMock()
        sched = TaskScheduler(_settings(), _bus(), _db()[0], rest)
        await sched.start()
        try:
            jobs = sched.scheduler.get_jobs()
            assert [j.id for j in jobs] == [JOB_ID]
            assert "hour='3'" in str(jobs[0].trigger) and "minute='30'" in str(jobs[0].trigger)
        finally:
            await sched.stop()
        rest.close.assert_not_called()  # the collector owns the client

    async def test_disabled_registers_nothing(self) -> None:
        sched = TaskScheduler(_settings(enabled=False), _bus(), _db()[0], MagicMock())
        await sched.start()
        assert not sched.scheduler.running
        assert sched.scheduler.get_jobs() == []
        await sched.stop()

    @pytest.mark.parametrize("exchange", ["kraken", "binance", "bybit"])
    async def test_run_passes_current_exchange_and_client_to_backfill(self, exchange: str) -> None:
        rest = MagicMock()
        db, _ = _db()
        summary = BackfillSummary(exchange=exchange, now=datetime.now(UTC), dry_run=False)
        with patch.object(ts_module, "backfill_gaps", AsyncMock(return_value=summary)) as bf:
            sched = TaskScheduler(_settings(exchange), _bus(), db, rest)
            await sched.run_backfill()
        args, kwargs = bf.call_args
        assert args[0] is rest and args[1] is db and args[2] == exchange
        assert args[3] == ["BTC/USDC", "ETH/USDC"] and args[4] == [1, 60]
        assert kwargs["lookback"].days == 3 and kwargs["batch_size"] == 1000


class TestRunLoggingAndEvents:
    async def test_success_writes_rows_and_publishes(self) -> None:
        gap = Gap(
            "BTC/USDC",
            1,
            datetime(2026, 9, 11, 1, 5, tzinfo=UTC),
            datetime(2026, 9, 11, 1, 5, tzinfo=UTC),
        )
        summary = BackfillSummary(
            exchange="bybit",
            now=datetime.now(UTC),
            dry_run=False,
            results=[
                GapResult(gap=gap, fetched=3, inserted=1, pages=1, stop_reason="completed"),
                GapResult(
                    gap=Gap("ETH/USDC", 60, gap.start, gap.start), error="boom", stop_reason="error"
                ),
            ],
        )
        db, session = _db()
        bus = _bus()
        with patch.object(ts_module, "backfill_gaps", AsyncMock(return_value=summary)):
            sched = TaskScheduler(_settings(), bus, db, MagicMock())
            result = await sched.run_backfill()

        assert result is summary
        rows = session.add_all.call_args.args[0]
        assert [(r.pair, r.interval, r.status, r.candles_fetched) for r in rows] == [
            ("BTC/USDC", 1, "success", 1),
            ("ETH/USDC", 60, "failed", 0),
            (RUN_ROW_PAIR, 0, "partial", 1),
        ]
        assert all(r.task_id == JOB_ID for r in rows)
        assert rows[1].error_message == "boom"
        event_type, payload = bus.publish.call_args.args
        assert event_type == EventType.SCHEDULER_TASK_SUCCESS
        assert payload["gaps_found"] == 2 and payload["gaps_filled"] == 1
        assert payload["failures"][0]["pair"] == "ETH/USDC"

    async def test_zero_gap_run_still_writes_run_row(self) -> None:
        summary = BackfillSummary(exchange="bybit", now=datetime.now(UTC), dry_run=False)
        db, session = _db()
        with patch.object(ts_module, "backfill_gaps", AsyncMock(return_value=summary)):
            await TaskScheduler(_settings(), _bus(), db, MagicMock()).run_backfill()
        rows = session.add_all.call_args.args[0]
        assert len(rows) == 1 and rows[0].pair == RUN_ROW_PAIR and rows[0].status == "success"

    async def test_detection_error_publishes_failed_without_raising(self) -> None:
        db, session = _db()
        bus = _bus()
        with patch.object(
            ts_module, "backfill_gaps", AsyncMock(side_effect=RuntimeError("db down"))
        ):
            result = await TaskScheduler(_settings(), bus, db, MagicMock()).run_backfill()
        assert result is None
        rows = session.add_all.call_args.args[0]
        assert len(rows) == 1 and rows[0].status == "failed" and "db down" in rows[0].error_message
        event_type, payload = bus.publish.call_args.args
        assert event_type == EventType.SCHEDULER_TASK_FAILED and "db down" in payload["error"]

    async def test_log_write_error_is_swallowed(self) -> None:
        summary = BackfillSummary(exchange="bybit", now=datetime.now(UTC), dry_run=False)
        db = MagicMock()
        db.session.side_effect = RuntimeError("no db")
        with patch.object(ts_module, "backfill_gaps", AsyncMock(return_value=summary)):
            assert (
                await TaskScheduler(_settings(), _bus(), db, MagicMock()).run_backfill() is summary
            )


def test_scheduler_has_no_exchange_literal_and_no_scripts_import() -> None:
    source = inspect.getsource(ts_module)
    assert "scripts" not in source.replace("scripts/", "")  # docstring mentions ``scripts/`` only
    assert "KrakenRestClient" not in source
    executable = "".join(source.split('"""')[0::2])
    for literal in ('"kraken"', '"binance"', '"bybit"'):
        assert literal not in executable
