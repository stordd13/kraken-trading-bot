"""Main entry point for KrakenBot trading system.

This module orchestrates all components and provides the main execution loop.

Components orchestrated:
    - Database connection (TimescaleDB via SQLAlchemy)
    - Event bus for internal messaging
    - WebSocket client for real-time market data
    - REST client for order execution
    - Trading strategy (ThresholdStrategy)
    - Execution engine with risk management

Usage:
    # Paper trading (default)
    python -m krakenbot

    # With custom config via environment
    TRADING_MODE=paper python -m krakenbot

    # Live trading (requires explicit confirmation)
    TRADING_MODE=live TRADING_CONFIRM_LIVE=yes python -m krakenbot

Example:
    >>> import asyncio
    >>> from krakenbot.main import main
    >>> asyncio.run(main())
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import signal
import sys
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from krakenbot.config.settings import get_settings
from krakenbot.connectors.kraken_rest import KrakenRestClient
from krakenbot.connectors.kraken_ws import KrakenWebSocketClient
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import get_event_bus
from krakenbot.core.logger import configure_logging, get_logger
from krakenbot.execution.engine import ExecutionEngine
from krakenbot.models.base import BotStatus, PositionStatus
from krakenbot.models.trades import BotState, OpenPosition
from krakenbot.strategies.threshold_rolling import ThresholdRollingStrategy

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.event_bus import EventBus


class KrakenBot:
    """Main bot orchestrator.

    Coordinates all components of the trading system:
        - Database connection and lifecycle
        - Event bus for internal pub/sub messaging
        - WebSocket client for real-time market data
        - REST client for order execution
        - Trading strategy for signal generation
        - Execution engine for order processing

    The bot follows a specific initialization and shutdown order to ensure
    proper dependency management and graceful cleanup.

    Startup Order:
        1. Settings & Logging
        2. Event Bus
        3. Database Manager
        4. REST Client
        5. WebSocket Client
        6. Execution Engine
        7. Strategy

    Shutdown Order (reverse):
        1. Strategy
        2. Execution Engine
        3. WebSocket Client
        4. REST Client
        5. Database Manager

    Note:
        Data collection (scheduler) is handled by the separate collector service
        (krakenbot-collector). This bot focuses only on trading.

    Attributes:
        settings: Application configuration.
        logger: Structured logger instance.
        event_bus: Event bus for pub/sub communication.
        db_manager: Database connection manager.
        ws_client: Kraken WebSocket client.
        rest_client: Kraken REST API client.
        strategy: Trading strategy instance.
        execution_engine: Order execution engine.

    Example:
        >>> bot = KrakenBot()
        >>> await bot.setup()
        >>> await bot.start()
        >>> await bot.run()
        >>> await bot.stop()
    """

    def __init__(self) -> None:
        """Initialize the bot with configuration and logging."""
        # Load settings
        self.settings: Settings = get_settings()

        # Configure logging
        configure_logging(self.settings)
        self.logger = get_logger(__name__)

        # Components (initialized in setup)
        self.event_bus: EventBus | None = None
        self.db_manager: DatabaseManager | None = None
        self.ws_client: KrakenWebSocketClient | None = None
        self.rest_client: KrakenRestClient | None = None
        self.strategy: ThresholdRollingStrategy | None = None
        self.execution_engine: ExecutionEngine | None = None

        # State
        self._running: bool = False
        self._shutdown_requested: bool = False
        self._setup_completed: bool = False

    async def setup(self) -> None:
        """Initialize all components in the correct order.

        This method initializes all bot components ensuring proper
        dependency ordering. Components are initialized but not started.

        Raises:
            Exception: If any component fails to initialize.
        """
        self.logger.info(
            "krakenbot_initializing",
            mode=self.settings.trading.mode.value,
            pair=self.settings.trading.pair,
            strategy=self.settings.strategy.name,
            environment=self.settings.environment,
        )

        # Warn if live mode
        if self.settings.is_live_trading:
            self.logger.warning(
                "live_trading_enabled",
                message="LIVE TRADING MODE - REAL MONEY AT RISK",
                confirm_required=True,
            )
        else:
            self.logger.info(
                "paper_trading_enabled",
                message="PAPER TRADING MODE - No real money at risk",
                mode="simulation",
            )

        # 1. Initialize event bus
        self.event_bus = get_event_bus()
        self.logger.debug("event_bus_initialized")

        # 2. Initialize database manager
        self.db_manager = DatabaseManager()
        await self.db_manager.init_db(self.settings)
        self.logger.debug("database_initialized")

        # 3. Initialize REST client
        self.rest_client = KrakenRestClient(
            self.settings,
            self.event_bus,
            self.db_manager,
        )
        self.logger.debug("rest_client_initialized")

        # 4. Initialize WebSocket client
        self.ws_client = KrakenWebSocketClient(
            self.settings,
            self.event_bus,
            self.db_manager,
        )
        self.logger.debug("websocket_client_initialized")

        # 5. Initialize execution engine
        self.execution_engine = ExecutionEngine(
            self.settings,
            self.event_bus,
            self.db_manager,
            self.rest_client,
        )
        self.logger.debug("execution_engine_initialized")

        # 6. Initialize strategy (rolling reference threshold)
        self.strategy = ThresholdRollingStrategy(
            self.settings,
            self.event_bus,
            self.db_manager,
        )
        self.logger.debug("strategy_initialized")

        self._setup_completed = True

        components_list = [
            "event_bus",
            "database",
            "rest_client",
            "websocket_client",
            "execution_engine",
            "strategy",
        ]

        self.logger.info(
            "krakenbot_initialized",
            status="ready",
            components=components_list,
        )

    async def start(self) -> None:
        """Start all components in the correct order.

        Components must be started in a specific order to ensure
        dependencies are satisfied:
            1. Execution engine (must be ready before signals)
            2. Strategy (starts generating signals)
            3. WebSocket (connects and subscribes)

        Raises:
            RuntimeError: If setup() has not been called.
        """
        if not self._setup_completed:
            raise RuntimeError("Bot not initialized. Call setup() first.")

        self.logger.info("krakenbot_starting")

        # 1. Start execution engine (must be first to handle signals)
        await self.execution_engine.start()
        self.logger.debug("execution_engine_started")

        # 2. Reconcile positions with exchange (before strategy loads positions)
        await self._reconcile_positions_with_exchange()

        # 3. Start strategy
        await self.strategy.start()
        self.logger.debug("strategy_started")

        # 4. Initialize bot state in database (for dashboard)
        await self._init_bot_state()

        # 5. Connect WebSocket and subscribe to market data
        await self.ws_client.connect()
        await self.ws_client.subscribe_ohlc(
            self.settings.trading.pair,
            self.settings.trading.candle_interval_min,
        )
        await self.ws_client.subscribe_ticker(self.settings.trading.pair)
        self.logger.debug("websocket_connected_and_subscribed")

        self._running = True

        self.logger.info(
            "krakenbot_started",
            status="running",
            mode=self.settings.trading.mode.value,
            pair=self.settings.trading.pair,
            interval=f"{self.settings.trading.candle_interval_min}m",
            strategy=self.strategy.get_name(),
        )

    async def stop(self) -> None:
        """Stop all components gracefully in reverse order.

        Components are stopped in reverse order of startup to ensure
        proper cleanup and no orphaned connections.

        Stop Order:
            1. Strategy (stop generating signals)
            2. Execution engine (stop processing)
            3. WebSocket client (disconnect)
            4. REST client (close connections)
            5. Database manager (close pool)
        """
        if not self._running:
            self.logger.debug("krakenbot_not_running_on_stop")
            return

        self.logger.info("krakenbot_stopping")
        self._running = False

        # Mark bot as stopped in database first (while db is still open)
        if self.db_manager and self.strategy:
            await self._mark_bot_stopped()

        # Stop in reverse order

        # 1. Stop strategy
        if self.strategy:
            try:
                await self.strategy.stop()
                self.logger.debug("strategy_stopped")
            except Exception as e:
                self.logger.error(
                    "strategy_stop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # 2. Stop execution engine
        if self.execution_engine:
            try:
                await self.execution_engine.stop()
                self.logger.debug("execution_engine_stopped")
            except Exception as e:
                self.logger.error(
                    "execution_engine_stop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # 3. Close WebSocket
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

        # 4. Close REST client
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

        # 5. Close database
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

        self.logger.info("krakenbot_stopped")

    async def _reconcile_positions_with_exchange(self) -> None:
        """Reconcile open positions in DB with actual exchange balance.

        This method is called at startup to detect manual position closures
        that happened while the bot was stopped. It:
        1. Gets the actual BTC balance from Kraken
        2. Compares with sum of open positions in DB
        3. If exchange balance < DB positions, marks excess positions as CLOSED

        This prevents the bot from thinking it has positions that don't exist
        on the exchange, which would block new trades due to position limits.
        """
        if not self.rest_client or not self.db_manager:
            self.logger.warning("reconciliation_skipped_no_client")
            return

        try:
            # Get actual balance from exchange
            balances = await self.rest_client.get_balance()

            # Normalize XBT to BTC (Kraken uses XBT internally)
            btc_balance = balances.get("BTC", Decimal("0")) or balances.get("XBT", Decimal("0"))

            self.logger.info(
                "reconciliation_exchange_balance",
                btc_balance=float(btc_balance),
            )

            # Get sum of open positions from DB
            async with self.db_manager.session() as session:
                result = await session.execute(
                    select(func.sum(OpenPosition.amount_btc)).where(
                        OpenPosition.status == PositionStatus.OPEN
                    )
                )
                db_position_sum = result.scalar() or Decimal("0")

                self.logger.info(
                    "reconciliation_db_positions",
                    db_position_sum=float(db_position_sum),
                )

                # Compare: if exchange has less BTC than DB thinks we have,
                # some positions were closed manually
                if btc_balance < db_position_sum:
                    deficit = db_position_sum - btc_balance

                    self.logger.warning(
                        "reconciliation_deficit_detected",
                        deficit=float(deficit),
                        btc_balance=float(btc_balance),
                        db_position_sum=float(db_position_sum),
                        action="marking_oldest_positions_as_closed",
                    )

                    # Get oldest open positions to close (FIFO)
                    result = await session.execute(
                        select(OpenPosition)
                        .where(OpenPosition.status == PositionStatus.OPEN)
                        .order_by(OpenPosition.entry_time.asc())
                    )
                    open_positions = result.scalars().all()

                    # Mark positions as CLOSED until we account for the deficit
                    remaining_deficit = deficit
                    closed_count = 0

                    for pos in open_positions:
                        if remaining_deficit <= Decimal("0.00000001"):
                            break

                        # Mark position as CLOSED (manual closure)
                        pos.status = PositionStatus.CLOSED
                        pos.closed_at = datetime.now(UTC)
                        pos.pnl = Decimal("0")  # Unknown P&L for manual closure

                        remaining_deficit -= pos.amount_btc
                        closed_count += 1

                        self.logger.warning(
                            "reconciliation_position_closed",
                            position_id=pos.position_id,
                            amount_btc=float(pos.amount_btc),
                            entry_price=float(pos.entry_price),
                            reason="manual_closure_detected",
                        )

                    await session.commit()

                    self.logger.warning(
                        "reconciliation_completed",
                        positions_closed=closed_count,
                        remaining_open=len(open_positions) - closed_count,
                    )
                else:
                    self.logger.info(
                        "reconciliation_ok",
                        message="Exchange balance matches or exceeds DB positions",
                        btc_balance=float(btc_balance),
                        db_position_sum=float(db_position_sum),
                    )

        except Exception as e:
            self.logger.error(
                "reconciliation_failed",
                error=str(e),
                error_type=type(e).__name__,
                note="Continuing without reconciliation - positions may be out of sync",
            )

    async def run(self) -> None:
        """Main execution loop.

        Runs continuously, logging stats periodically and checking
        for shutdown requests. The loop exits when:
            - _running is set to False
            - _shutdown_requested is set to True
            - KeyboardInterrupt is received
            - An unhandled exception occurs

        Stats are logged every 60 seconds including:
            - WebSocket statistics (messages, OHLC, ticks, errors)
            - Execution statistics (signals received/executed/rejected)
            - Strategy state (current price, position status)
        """
        stats_interval_sec: int = 60
        last_stats_at: datetime = datetime.now(UTC)

        self.logger.info(
            "krakenbot_main_loop_started",
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
        """Log periodic statistics from all components.

        Collects and logs statistics from:
            - WebSocket client (connection stats, message counts)
            - Execution engine (signal processing stats)
            - Strategy (current state and prices)
        """
        stats: dict[str, Any] = {}

        # WebSocket stats
        if self.ws_client:
            stats["websocket"] = self.ws_client.stats

        # Execution stats
        if self.execution_engine:
            stats["execution"] = self.execution_engine.stats

        # REST client stats
        if self.rest_client:
            stats["rest_client"] = self.rest_client.stats

        # Strategy state
        if self.strategy:
            stats["strategy"] = {
                "name": self.strategy.get_name(),
                "running": self.strategy.is_running,
                "current_price": (
                    float(self.strategy.current_price) if self.strategy.current_price else None
                ),
                "reference_price": (
                    float(self.strategy.reference_price) if self.strategy.reference_price else None
                ),
                "has_position": self.strategy.has_position,
                "entry_price": (
                    float(self.strategy.entry_price) if self.strategy.entry_price else None
                ),
                "price_history_len": self.strategy.price_history_len,
            }

        self.logger.info(
            "periodic_stats",
            uptime_seconds=self._get_uptime_seconds(),
            **stats,
        )

        # Update heartbeat in database
        await self._update_bot_heartbeat()

    def _get_uptime_seconds(self) -> float:
        """Calculate bot uptime in seconds.

        Returns:
            Number of seconds since the bot was started.
        """
        if not hasattr(self, "_start_time"):
            self._start_time = datetime.now(UTC)
        return (datetime.now(UTC) - self._start_time).total_seconds()

    async def _init_bot_state(self) -> None:
        """Initialize bot state in database on startup.

        Creates or updates the BotState record to indicate the bot is running.
        This ensures the dashboard shows "RUNNING" immediately on startup,
        without waiting for the first trade to execute.
        """
        bot_id = self.get_bot_id()
        async with self.db_manager.session() as session:
            result = await session.execute(select(BotState).where(BotState.bot_id == bot_id))
            bot_state = result.scalar_one_or_none()

            if bot_state is None:
                bot_state = BotState(
                    bot_id=bot_id,
                    strategy=self.strategy.get_name(),
                    status=BotStatus.RUNNING,
                )
                session.add(bot_state)
                self.logger.info(
                    "bot_state_created",
                    bot_id=bot_id,
                    status="running",
                )
            else:
                bot_state.status = BotStatus.RUNNING
                bot_state.updated_at = datetime.now(UTC)
                self.logger.info(
                    "bot_state_updated",
                    bot_id=bot_id,
                    status="running",
                )

            await session.commit()

    async def _update_bot_heartbeat(self) -> None:
        """Update bot_state heartbeat in database.

        Called periodically to update the `updated_at` timestamp,
        indicating the bot is still alive.
        """
        try:
            bot_id = self.get_bot_id()
            async with self.db_manager.session() as session:
                result = await session.execute(select(BotState).where(BotState.bot_id == bot_id))
                bot_state = result.scalar_one_or_none()
                if bot_state:
                    bot_state.updated_at = datetime.now(UTC)
                    await session.commit()
        except Exception as e:
            self.logger.warning(
                "bot_heartbeat_update_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

    async def _mark_bot_stopped(self) -> None:
        """Mark bot as stopped in database.

        Called during shutdown to update the BotState status to STOPPED,
        ensuring the dashboard shows the correct state.
        """
        try:
            bot_id = self.get_bot_id()
            async with self.db_manager.session() as session:
                result = await session.execute(select(BotState).where(BotState.bot_id == bot_id))
                bot_state = result.scalar_one_or_none()
                if bot_state:
                    bot_state.status = BotStatus.STOPPED
                    bot_state.updated_at = datetime.now(UTC)
                    await session.commit()
                    self.logger.info(
                        "bot_state_stopped",
                        bot_id=bot_id,
                    )
        except Exception as e:
            self.logger.warning(
                "bot_state_stop_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

    def request_shutdown(self) -> None:
        """Request a graceful shutdown of the bot.

        Sets the shutdown flag which will cause the main loop to exit
        on its next iteration.
        """
        self.logger.info(
            "shutdown_requested",
            reason="external_request",
        )
        self._shutdown_requested = True

    @property
    def is_running(self) -> bool:
        """Check if the bot is currently running.

        Returns:
            True if the bot is running and not shutting down.
        """
        return self._running and not self._shutdown_requested

    def get_bot_id(self) -> str:
        """Generate unique bot_id for this instance.

        Combines strategy name with optional instance identifier to create
        a unique bot_id. This allows multiple instances of the same strategy
        to run simultaneously with different configurations.

        Returns:
            Unique bot identifier (e.g., "threshold_rolling" or "threshold_rolling_xbt_prod").
        """
        if self.strategy is None:
            return "unknown"
        base = self.strategy.get_name()
        instance_id = self.settings.trading.bot_instance_id
        if instance_id:
            return f"{base}_{instance_id}"
        return base


async def main() -> None:
    """Main entry point for the KrakenBot application.

    Creates the bot instance, sets up signal handlers, and runs
    the main execution loop.

    Signal Handlers:
        - SIGINT (Ctrl+C): Triggers graceful shutdown
        - SIGTERM (kill): Triggers graceful shutdown

    Exit Codes:
        - 0: Normal exit
        - 1: Fatal error occurred
    """
    # Create bot instance
    bot = KrakenBot()

    # Track startup time
    bot._start_time = datetime.now(UTC)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        logger = get_logger(__name__)
        logger.info(
            "signal_received",
            signal=sig.name,
        )
        bot.request_shutdown()

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            # Fall back to standard signal handling
            signal.signal(sig, lambda s, f: signal_handler(signal.Signals(s)))

    try:
        # Setup all components
        await bot.setup()

        # Start the bot
        await bot.start()

        # Run main loop
        await bot.run()

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
        if bot._running:
            await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
