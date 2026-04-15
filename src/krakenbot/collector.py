"""Standalone data collector service for KrakenBot.

This module provides a standalone service that runs independently of the trading bot
to collect OHLC data continuously. It uses both:
- WebSocket for real-time data (latest candles)
- REST API scheduler for historical backfill (multi-interval)

The collector writes to the same database as the trading bot, using merge()
for deduplication via the composite primary key (timestamp, pair, interval).

Usage:
    # Run the collector service
    python -m krakenbot.collector

    # Or via systemctl (production)
    sudo systemctl start krakenbot-collector
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import signal
import sys
from typing import TYPE_CHECKING

from krakenbot.config.settings import get_settings
from krakenbot.connectors.exchange import (
    ExchangeRestClient,
    build_exchange_rest_client,
    build_exchange_ws_client,
)
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import get_event_bus
from krakenbot.core.logger import configure_logging, get_logger
from krakenbot.scheduler.task_scheduler import TaskScheduler

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.connectors.base_ws import BaseWebSocketClient
    from krakenbot.core.event_bus import EventBus


class DataCollector:
    """Standalone data collector service.

    This service runs independently of the trading bot and is responsible for:
    1. Real-time OHLC data collection via WebSocket
    2. Scheduled historical data backfill via REST API

    The service should run 24/7 to ensure continuous data collection.

    Attributes:
        settings: Application configuration.
        logger: Structured logger instance.
        event_bus: Event bus for internal messaging.
        db_manager: Database connection manager.
        ws_client: Exchange WebSocket client for real-time data.
        rest_client: Exchange REST API client for backfill.
        task_scheduler: Scheduler for periodic data collection tasks.
    """

    def __init__(self) -> None:
        """Initialize the data collector."""
        # Load settings
        self.settings: Settings = get_settings()

        # Configure logging
        configure_logging(self.settings)
        self.logger = get_logger(__name__)

        # Components (initialized in setup)
        self.event_bus: EventBus | None = None
        self.db_manager: DatabaseManager | None = None
        self.ws_client: BaseWebSocketClient | None = None
        self.rest_client: ExchangeRestClient | None = None
        self.task_scheduler: TaskScheduler | None = None

        # State
        self._running: bool = False
        self._shutdown_requested: bool = False
        self._setup_completed: bool = False

    async def setup(self) -> None:
        """Initialize all components.

        Raises:
            Exception: If any component fails to initialize.
        """
        self.logger.info(
            "collector_initializing",
            pairs=self.settings.scheduler.pairs,
            intervals=self.settings.scheduler.intervals,
            scheduler_enabled=self.settings.scheduler.enabled,
        )

        # 1. Initialize event bus
        self.event_bus = get_event_bus()
        self.logger.debug("event_bus_initialized")

        # 2. Initialize database manager
        self.db_manager = DatabaseManager()
        await self.db_manager.init_db(self.settings)
        self.logger.debug("database_initialized")

        # 3. Initialize REST client (for scheduled backfill)
        self.rest_client = build_exchange_rest_client(
            self.settings,
            self.event_bus,
            self.db_manager,
        )
        self.logger.debug("rest_client_initialized")

        # 4. Initialize WebSocket client (for real-time data)
        # Collector passes db_manager so the WS client persists candles to DB.
        self.ws_client = build_exchange_ws_client(
            self.settings,
            self.event_bus,
            self.db_manager,
            telegram_notifier=None,
        )
        self.logger.debug("websocket_client_initialized")

        # 5. Initialize task scheduler (for historical backfill)
        if self.settings.scheduler.enabled:
            self.task_scheduler = TaskScheduler(
                self.settings,
                self.event_bus,
                self.db_manager,
            )
            self.logger.debug("task_scheduler_initialized")

        self._setup_completed = True

        self.logger.info(
            "collector_initialized",
            status="ready",
            components=[
                "event_bus",
                "database",
                "rest_client",
                "websocket_client",
                "task_scheduler" if self.task_scheduler else None,
            ],
        )

    async def start(self) -> None:
        """Start all collector components.

        Raises:
            RuntimeError: If setup() has not been called.
        """
        if not self._setup_completed:
            raise RuntimeError("Collector not initialized. Call setup() first.")

        self.logger.info("collector_starting")

        # 1. Connect WebSocket and subscribe to market data
        await self.ws_client.connect()

        # Subscribe to OHLC for all configured pairs × all analysis timeframes
        # All 6 timeframes needed by MultiTimeframeAnalyzer per pair
        all_intervals = [5, 15, 60, 240, 1440, 10080]
        subscription_count = 0
        for pair in self.settings.scheduler.pairs:
            for interval in all_intervals:
                await self.ws_client.subscribe_ohlc(pair, interval)
                subscription_count += 1
            await self.ws_client.subscribe_ticker(pair)
            subscription_count += 1

        self.logger.debug(
            "websocket_connected_and_subscribed",
            pairs=self.settings.scheduler.pairs,
            intervals=all_intervals,
            subscription_count=subscription_count,
        )

        # 2. Start task scheduler (for REST API backfill)
        if self.task_scheduler:
            await self.task_scheduler.start()
            self.logger.debug("task_scheduler_started")

        self._running = True

        self.logger.info(
            "collector_started",
            status="running",
            pairs=self.settings.scheduler.pairs,
            intervals=self.settings.scheduler.intervals,
            scheduler_enabled=self.task_scheduler is not None,
        )

    async def stop(self) -> None:
        """Stop all components gracefully."""
        if not self._running:
            self.logger.debug("collector_not_running_on_stop")
            return

        self.logger.info("collector_stopping")
        self._running = False

        # Stop in reverse order

        # 1. Stop task scheduler
        if self.task_scheduler:
            try:
                await self.task_scheduler.stop()
                self.logger.debug("task_scheduler_stopped")
            except Exception as e:
                self.logger.error(
                    "task_scheduler_stop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # 2. Close WebSocket
        if self.ws_client:
            try:
                await self.ws_client.close()
                self.logger.debug("websocket_closed")
            except Exception as e:
                self.logger.error(
                    "websocket_close_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # 3. Close REST client
        if self.rest_client:
            try:
                await self.rest_client.close()
                self.logger.debug("rest_client_closed")
            except Exception as e:
                self.logger.error(
                    "rest_client_close_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # 4. Close database
        if self.db_manager:
            try:
                await self.db_manager.close_db()
                self.logger.debug("database_closed")
            except Exception as e:
                self.logger.error(
                    "database_close_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        self.logger.info("collector_stopped")

    async def run(self) -> None:
        """Main execution loop.

        Runs continuously, logging stats periodically and checking
        for shutdown requests.
        """
        stats_interval_sec: int = 300  # Log stats every 5 minutes
        last_stats_at: datetime = datetime.now(UTC)

        self.logger.info(
            "collector_main_loop_started",
            stats_interval_sec=stats_interval_sec,
        )

        try:
            while self._running and not self._shutdown_requested:
                # Sleep briefly to avoid busy-waiting
                await asyncio.sleep(1)

                # Log stats periodically
                now = datetime.now(UTC)
                elapsed = (now - last_stats_at).total_seconds()

                if elapsed >= stats_interval_sec:
                    await self._log_stats()
                    last_stats_at = now

        except asyncio.CancelledError:
            self.logger.info(
                "shutdown_requested",
                reason="task_cancelled",
            )
        except Exception as e:
            self.logger.error(
                "runtime_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=e,
            )
            raise
        finally:
            await self.stop()

    async def _log_stats(self) -> None:
        """Log periodic statistics from all components."""
        stats: dict = {}

        # WebSocket stats
        if self.ws_client:
            stats["websocket"] = self.ws_client.stats

        # REST client stats
        if self.rest_client:
            stats["rest_client"] = self.rest_client.stats

        # Scheduler stats (number of jobs, next run times)
        if self.task_scheduler and self.task_scheduler.scheduler.running:
            jobs = self.task_scheduler.scheduler.get_jobs()
            stats["scheduler"] = {
                "num_jobs": len(jobs),
                "jobs": [
                    {
                        "id": job.id,
                        "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    }
                    for job in jobs
                ],
            }

        self.logger.info(
            "collector_periodic_stats",
            uptime_seconds=self._get_uptime_seconds(),
            **stats,
        )

    def _get_uptime_seconds(self) -> float:
        """Calculate collector uptime in seconds."""
        if not hasattr(self, "_start_time"):
            self._start_time = datetime.now(UTC)
        return (datetime.now(UTC) - self._start_time).total_seconds()

    def request_shutdown(self) -> None:
        """Request a graceful shutdown."""
        self.logger.info(
            "shutdown_requested",
            reason="external_request",
        )
        self._shutdown_requested = True

    @property
    def is_running(self) -> bool:
        """Check if the collector is currently running."""
        return self._running and not self._shutdown_requested


async def main() -> None:
    """Main entry point for the data collector service."""
    # Create collector instance
    collector = DataCollector()

    # Track startup time
    collector._start_time = datetime.now(UTC)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        logger = get_logger(__name__)
        logger.info(
            "signal_received",
            signal=sig.name,
        )
        collector.request_shutdown()

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: signal_handler(signal.Signals(s)))

    try:
        # Setup all components
        await collector.setup()

        # Start the collector
        await collector.start()

        # Run main loop
        await collector.run()

    except KeyboardInterrupt:
        logger = get_logger(__name__)
        logger.info(
            "shutdown_requested",
            reason="keyboard_interrupt",
        )
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(
            "fatal_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=e,
        )
        sys.exit(1)
    finally:
        # Ensure cleanup happens
        if collector._running:
            await collector.stop()


if __name__ == "__main__":
    asyncio.run(main())
