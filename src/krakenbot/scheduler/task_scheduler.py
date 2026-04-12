"""Task scheduler for scheduled OHLC data collection.

This module implements scheduled tasks using APScheduler for continuous
data collection from Kraken API.
"""

from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

from krakenbot.config.settings import Settings
from krakenbot.connectors.kraken.rest import KrakenRestClient
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import EventBus, EventType
from krakenbot.models.scheduled_tasks import TaskExecutionLog

logger = structlog.get_logger()


class TaskScheduler:
    """Task scheduler for automated OHLC data collection.

    This class manages scheduled tasks for fetching OHLC data at different
    intervals (1min, 5min, 15min, 1h) to maintain a continuous historical
    database and work around Kraken API retention limits.

    Attributes:
        settings: Application settings.
        event_bus: Event bus for publishing task events.
        db_manager: Database manager for storing data.
        scheduler: APScheduler instance.
        rest_client: Kraken REST API client.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
    ):
        """Initialize task scheduler.

        Args:
            settings: Application settings.
            event_bus: Event bus for publishing events.
            db_manager: Database manager.
        """
        self.settings = settings
        self.event_bus = event_bus
        self.db_manager = db_manager

        # Initialize APScheduler
        self.scheduler = AsyncIOScheduler(
            timezone=settings.scheduler.timezone,
            job_defaults={
                "coalesce": True,  # If job missed, run once (not multiple times)
                "max_instances": 1,  # Only one instance of each job at a time
                "misfire_grace_time": 300,  # 5 minutes grace period for misfires
            },
        )

        # Initialize Kraken REST client (will be set in start())
        self.rest_client: KrakenRestClient | None = None

        logger.info(
            "task_scheduler_initialized",
            timezone=settings.scheduler.timezone,
            enabled=settings.scheduler.enabled,
        )

    async def start(self) -> None:
        """Start the task scheduler.

        Initializes REST client, registers all scheduled tasks, and starts
        the scheduler.
        """
        if not self.settings.scheduler.enabled:
            logger.info("task_scheduler_disabled")
            return

        # Initialize REST client
        self.rest_client = KrakenRestClient(
            settings=self.settings,
            event_bus=self.event_bus,
            db_manager=self.db_manager,
        )

        # Register all scheduled tasks
        await self._register_tasks()

        # Start scheduler
        self.scheduler.start()

        logger.info(
            "task_scheduler_started",
            num_jobs=len(self.scheduler.get_jobs()),
        )

    async def stop(self) -> None:
        """Stop the task scheduler gracefully.

        Waits for running jobs to complete before shutting down.
        """
        if self.scheduler.running:
            logger.info("task_scheduler_stopping")
            self.scheduler.shutdown(wait=True)
            logger.info("task_scheduler_stopped")

        # Close REST client
        if self.rest_client:
            await self.rest_client.close()

    async def _register_tasks(self) -> None:
        """Register daily OHLC backfill task for all intervals.

        A single daily job fetches the last N days of data for ALL configured
        intervals (1min, 5min, 15min, 1h). This ensures uniform data coverage
        across all intervals.
        """
        days = self.settings.scheduler.backfill_days

        for interval in self.settings.scheduler.intervals:
            self.scheduler.add_job(
                self._fetch_ohlc_task,
                trigger=CronTrigger.from_crontab(
                    self.settings.scheduler.daily_backfill_cron,
                    timezone=self.settings.scheduler.timezone,
                ),
                args=[interval, days],
                id=f"daily_ohlc_{interval}min",
                name=f"Daily {interval}min OHLC Backfill ({days}d)",
            )
            logger.info(
                "registered_scheduled_task",
                task_id=f"daily_ohlc_{interval}min",
                interval=interval,
                days=days,
                cron=self.settings.scheduler.daily_backfill_cron,
            )

    async def _fetch_ohlc_task(
        self,
        interval: int,
        days: int,
    ) -> None:
        """Wrapper task for OHLC data fetching with error handling.

        This method is called by APScheduler for each scheduled job.
        It fetches OHLC data for all configured pairs at the specified
        interval, logs execution details, and publishes events.

        Args:
            interval: Candle interval in minutes (1, 5, 15, 60).
            days: Number of days to fetch.
        """
        task_id = f"ohlc_{interval}min"

        logger.info(
            "scheduled_task_starting",
            task_id=task_id,
            interval=interval,
            days=days,
            pairs=self.settings.scheduler.pairs,
        )

        # Fetch data for each configured pair
        for pair in self.settings.scheduler.pairs:
            log_entry = await self._create_task_log(task_id, pair, interval)

            try:
                # Import here to avoid circular dependency
                from scripts.fetch_ohlc import fetch_ohlc_with_resume

                # Fetch OHLC data with resume capability
                total_candles = await fetch_ohlc_with_resume(
                    rest_client=self.rest_client,
                    db_manager=self.db_manager,
                    pair=pair,
                    interval=interval,
                    days=days,
                    resume=True,  # Always resume from last timestamp
                    batch_size=self.settings.scheduler.batch_size,
                )

                # Update log entry with success
                await self._complete_task_log(
                    log_entry=log_entry,
                    status="success",
                    candles_fetched=total_candles,
                )

                # Publish success event
                await self.event_bus.publish(
                    EventType.SCHEDULER_TASK_SUCCESS,
                    {
                        "task_id": task_id,
                        "pair": pair,
                        "interval": interval,
                        "candles_fetched": total_candles,
                    },
                )

                logger.info(
                    "scheduled_task_completed",
                    task_id=task_id,
                    pair=pair,
                    interval=interval,
                    candles_fetched=total_candles,
                )

            except Exception as e:
                error_msg = str(e)

                # Update log entry with failure
                await self._complete_task_log(
                    log_entry=log_entry,
                    status="failed",
                    error_message=error_msg,
                )

                # Publish failure event
                await self.event_bus.publish(
                    EventType.SCHEDULER_TASK_FAILED,
                    {
                        "task_id": task_id,
                        "pair": pair,
                        "interval": interval,
                        "error": error_msg,
                    },
                )

                logger.error(
                    "scheduled_task_failed",
                    task_id=task_id,
                    pair=pair,
                    interval=interval,
                    error=error_msg,
                )

                # Don't re-raise - let scheduler continue with other tasks

    async def _create_task_log(
        self,
        task_id: str,
        pair: str,
        interval: int,
    ) -> TaskExecutionLog:
        """Create task execution log entry.

        Args:
            task_id: Unique task identifier.
            pair: Trading pair.
            interval: OHLC interval in minutes.

        Returns:
            Created TaskExecutionLog instance.
        """
        log_entry = TaskExecutionLog(
            task_id=task_id,
            pair=pair,
            interval=interval,
            started_at=datetime.now(UTC),
            status="running",
        )

        async with self.db_manager.session() as session:
            session.add(log_entry)
            await session.commit()
            await session.refresh(log_entry)

        return log_entry

    async def _complete_task_log(
        self,
        log_entry: TaskExecutionLog,
        status: str,
        candles_fetched: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Update task execution log with completion status.

        Args:
            log_entry: Task execution log entry to update.
            status: Final status ('success' or 'failed').
            candles_fetched: Number of candles fetched.
            error_message: Error message if failed.
        """
        async with self.db_manager.session() as session:
            # Re-attach to session
            await session.merge(log_entry)

            log_entry.completed_at = datetime.now(UTC)
            log_entry.status = status
            log_entry.candles_fetched = candles_fetched
            if error_message:
                log_entry.error_message = error_message

            await session.commit()
