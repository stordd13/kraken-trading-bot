"""Periodic OHLC gap backfill for the collector (APScheduler).

One cron job (``SCHEDULER_DAILY_BACKFILL_CRON``, default 03:30 UTC — after the
nightly Bybit EU WebSocket closes observed between 01:00 and 02:40 UTC) runs
:func:`krakenbot.data.backfill.backfill_gaps` for the current exchange: internal
gaps of the last ``SCHEDULER_BACKFILL_DAYS`` days plus the tail gap, for every
configured pair × interval.  Exchange-agnostic: the REST client is injected by
the collector (built through ``build_exchange_rest_client``), this module holds
no exchange literal and never imports from ``scripts/``.

Every run writes ``TaskExecutionLog`` rows (one per gap, plus one run row with
``pair="*"`` / ``interval=0`` so zero-gap runs stay observable) and publishes
one ``SCHEDULER_TASK_SUCCESS`` or ``SCHEDULER_TASK_FAILED`` event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import time
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

from krakenbot.core.event_bus import EventType
from krakenbot.data.backfill import BackfillSummary, backfill_gaps
from krakenbot.models.scheduled_tasks import TaskExecutionLog

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.connectors.exchange import ExchangeRestClient
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus

logger = structlog.get_logger()

JOB_ID = "gap_backfill"
RUN_ROW_PAIR = "*"
RUN_ROW_INTERVAL = 0


class TaskScheduler:
    """Schedules the periodic gap backfill inside the collector.

    Attributes:
        settings: Application settings.
        event_bus: Event bus for ``SCHEDULER_TASK_*`` events.
        db_manager: Database manager (gap detection, inserts, execution log).
        rest_client: Exchange REST client **owned by the caller** (the collector
            builds it with ``read_only=True`` and closes it on shutdown).
        scheduler: APScheduler instance.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        rest_client: ExchangeRestClient,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.db_manager = db_manager
        self.rest_client = rest_client

        self.scheduler = AsyncIOScheduler(
            timezone=settings.scheduler.timezone,
            job_defaults={
                "coalesce": True,  # a missed run is executed once, not N times
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
        )

        logger.info(
            "task_scheduler_initialized",
            exchange=settings.exchange_name,
            timezone=settings.scheduler.timezone,
            enabled=settings.scheduler.enabled,
            cron=settings.scheduler.daily_backfill_cron,
            lookback_days=settings.scheduler.backfill_days,
        )

    async def start(self) -> None:
        """Register the gap-backfill job and start the scheduler (no-op if disabled)."""
        if not self.settings.scheduler.enabled:
            logger.info("task_scheduler_disabled")
            return

        self.scheduler.add_job(
            self.run_backfill,
            trigger=CronTrigger.from_crontab(
                self.settings.scheduler.daily_backfill_cron,
                timezone=self.settings.scheduler.timezone,
            ),
            id=JOB_ID,
            name=f"Gap backfill ({self.settings.exchange_name})",
            replace_existing=True,
        )
        self.scheduler.start()

        logger.info(
            "task_scheduler_started",
            num_jobs=len(self.scheduler.get_jobs()),
            job_id=JOB_ID,
            cron=self.settings.scheduler.daily_backfill_cron,
            exchange=self.settings.exchange_name,
            pairs=self.settings.scheduler.pairs,
            intervals=self.settings.scheduler.intervals,
        )

    async def stop(self) -> None:
        """Stop the scheduler, waiting for a running job. The REST client is not closed here."""
        if self.scheduler.running:
            logger.info("task_scheduler_stopping")
            self.scheduler.shutdown(wait=True)
            logger.info("task_scheduler_stopped")

    async def run_backfill(self) -> BackfillSummary | None:
        """One scheduled run: detect + fill gaps, log rows, publish one event. Never raises."""
        sched = self.settings.scheduler
        exchange = self.settings.exchange_name
        started_at = datetime.now(UTC)
        t0 = time.monotonic()

        logger.info(
            "scheduled_backfill_starting",
            task_id=JOB_ID,
            exchange=exchange,
            pairs=sched.pairs,
            intervals=sched.intervals,
            lookback_days=sched.backfill_days,
        )

        try:
            summary = await backfill_gaps(
                self.rest_client,
                self.db_manager,
                exchange,
                sched.pairs,
                sched.intervals,
                lookback=timedelta(days=sched.backfill_days),
                batch_size=sched.batch_size,
            )
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(
                "scheduled_backfill_failed",
                task_id=JOB_ID,
                exchange=exchange,
                error=error_msg,
                duration_s=round(time.monotonic() - t0, 1),
            )
            await self._write_logs(started_at, None, error_msg)
            await self.event_bus.publish(
                EventType.SCHEDULER_TASK_FAILED,
                {"task_id": JOB_ID, "exchange": exchange, "error": error_msg},
            )
            return None

        duration_s = round(time.monotonic() - t0, 1)
        await self._write_logs(started_at, summary, None)
        await self.event_bus.publish(
            EventType.SCHEDULER_TASK_SUCCESS,
            {
                "task_id": JOB_ID,
                "exchange": exchange,
                "gaps_found": summary.gaps_found,
                "gaps_filled": summary.gaps_filled,
                "candles_inserted": summary.candles_inserted,
                "failures": [
                    {
                        "pair": r.gap.pair,
                        "interval": r.gap.interval,
                        "start": r.gap.start.isoformat(),
                        "error": r.error,
                    }
                    for r in summary.failures
                ],
            },
        )
        logger.info(
            "scheduled_backfill_completed",
            task_id=JOB_ID,
            exchange=exchange,
            gaps_found=summary.gaps_found,
            gaps_filled=summary.gaps_filled,
            candles_inserted=summary.candles_inserted,
            failures=len(summary.failures),
            duration_s=duration_s,
        )
        return summary

    async def _write_logs(
        self,
        started_at: datetime,
        summary: BackfillSummary | None,
        run_error: str | None,
    ) -> None:
        """Persist one ``TaskExecutionLog`` row per gap plus the run row. Never raises."""
        completed_at = datetime.now(UTC)
        rows: list[TaskExecutionLog] = []
        if summary is not None:
            for r in summary.results:
                rows.append(
                    TaskExecutionLog(
                        task_id=JOB_ID,
                        pair=r.gap.pair,
                        interval=r.gap.interval,
                        started_at=started_at,
                        completed_at=completed_at,
                        status="failed" if r.error else "success",
                        candles_fetched=r.inserted,
                        error_message=r.error,
                    )
                )
            if summary.failures:
                run_status = "partial" if summary.gaps_filled else "failed"
            else:
                run_status = "success"
            run_candles = summary.candles_inserted
            run_message: str | None = (
                f"{len(summary.failures)} gap(s) failed" if summary.failures else None
            )
        else:
            run_status, run_candles, run_message = "failed", 0, run_error

        rows.append(
            TaskExecutionLog(
                task_id=JOB_ID,
                pair=RUN_ROW_PAIR,
                interval=RUN_ROW_INTERVAL,
                started_at=started_at,
                completed_at=completed_at,
                status=run_status,
                candles_fetched=run_candles,
                error_message=run_message,
            )
        )
        try:
            async with self.db_manager.session() as session:
                session.add_all(rows)
        except Exception as e:
            logger.error(
                "scheduled_backfill_log_write_error",
                task_id=JOB_ID,
                error=str(e),
                error_type=type(e).__name__,
            )
