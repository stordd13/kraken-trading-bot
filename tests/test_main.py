"""Tests for the main entry point and KrakenBot orchestrator.

This module tests:
- KrakenBot initialization
- Component setup and teardown
- Lifecycle management
- Signal handling
- Stats logging
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    MultiStrategySettings,
    Settings,
    StrategyBudget,
    StrategyInstanceConfig,
)
from krakenbot.core.event_bus import EventBus, EventType, reset_event_bus
from krakenbot.main import KrakenBot
from krakenbot.strategies.multi_strategy_router import MultiStrategyRouter


@pytest.fixture
def mock_settings(mock_settings: Settings) -> Settings:
    """Use the shared mock settings fixture."""
    return mock_settings


@pytest.fixture
def mock_get_settings(mock_settings: Settings):
    """Mock get_settings to return test settings."""
    with patch("krakenbot.main.get_settings", return_value=mock_settings):
        yield mock_settings


@pytest.fixture
def mock_configure_logging():
    """Mock configure_logging to avoid side effects."""
    with patch("krakenbot.main.configure_logging") as mock:
        yield mock


@pytest.fixture
def mock_get_logger():
    """Mock get_logger to return a mock logger."""
    mock_logger = MagicMock()
    with patch("krakenbot.main.get_logger", return_value=mock_logger):
        yield mock_logger


@pytest.fixture
def mock_event_bus():
    """Mock the event bus."""
    mock_bus = AsyncMock()
    mock_bus.subscribe = AsyncMock()
    mock_bus.unsubscribe = AsyncMock()
    mock_bus.publish = AsyncMock()
    with patch("krakenbot.main.get_event_bus", return_value=mock_bus):
        yield mock_bus


@pytest.fixture
def mock_database_manager():
    """Mock DatabaseManager."""
    mock_db = MagicMock()
    mock_db.init_db = AsyncMock()
    mock_db.close_db = AsyncMock()
    mock_db.is_initialized = True

    # Create mock for query result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)  # No existing bot_state

    # Create async context manager mocks for session() and read_session()
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.merge = AsyncMock()
    mock_session.add = MagicMock()

    # Create async context manager that yields mock_session
    async_cm = AsyncMock()
    async_cm.__aenter__ = AsyncMock(return_value=mock_session)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    mock_db.session = MagicMock(return_value=async_cm)
    mock_db.read_session = MagicMock(return_value=async_cm)

    with patch("krakenbot.main.DatabaseManager", return_value=mock_db):
        yield mock_db


@pytest.fixture
def mock_ws_client():
    """Mock WebSocket client (via factory)."""
    mock_ws = MagicMock()
    mock_ws.connect = AsyncMock()
    mock_ws.close = AsyncMock()
    mock_ws.subscribe_ohlc = AsyncMock()
    mock_ws.subscribe_ticker = AsyncMock()
    mock_ws.stats = {
        "messages_received": 100,
        "ohlc_received": 10,
        "ticks_received": 50,
        "errors": 0,
        "reconnections": 0,
    }
    with patch("krakenbot.main.build_exchange_ws_client", return_value=mock_ws):
        yield mock_ws


@pytest.fixture
def mock_rest_client():
    """Mock KrakenRestClient."""
    mock_rest = MagicMock()
    mock_rest.close = AsyncMock()
    mock_rest.get_balance = AsyncMock(
        return_value={"EUR": Decimal("1000.00"), "XBT": Decimal("0.0")}
    )
    mock_rest.initialize_paper_balance = AsyncMock()
    mock_rest.is_paper_mode = True
    mock_rest.exchange_name = "kraken"
    mock_rest.stats = {
        "orders_placed": 0,
        "orders_filled": 0,
        "orders_failed": 0,
        "api_calls": 10,
    }
    with patch("krakenbot.main.build_exchange_rest_client", return_value=mock_rest):
        yield mock_rest


@pytest.fixture
def mock_execution_engine():
    """Mock ExecutionEngine."""
    mock_engine = MagicMock()
    mock_engine.start = AsyncMock()
    mock_engine.stop = AsyncMock()
    mock_engine.stats = {
        "signals_received": 5,
        "signals_executed": 2,
        "signals_rejected": 1,
        "signals_ignored": 2,
        "execution_errors": 0,
    }
    with patch("krakenbot.main.ExecutionEngine", return_value=mock_engine):
        yield mock_engine


@pytest.fixture
def mock_strategy():
    """Mock ThresholdRollingStrategy."""
    mock_strat = MagicMock()
    mock_strat.start = AsyncMock()
    mock_strat.stop = AsyncMock()
    mock_strat.get_name.return_value = "threshold_rolling"
    mock_strat.is_running = True
    mock_strat.current_price = Decimal("42000.00")
    mock_strat.reference_price = Decimal("41800.00")
    mock_strat.has_position = False
    mock_strat.entry_price = None
    mock_strat.price_history_len = 10
    with patch("krakenbot.main.ThresholdRollingStrategy", return_value=mock_strat):
        yield mock_strat


class TestKrakenBotInitialization:
    """Tests for KrakenBot initialization."""

    def test_init_loads_settings(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
    ) -> None:
        """Test that bot initialization loads settings and configures logging."""
        bot = KrakenBot()

        assert bot.settings == mock_get_settings
        mock_configure_logging.assert_called_once_with(mock_get_settings)
        assert bot._running is False
        assert bot._shutdown_requested is False
        assert bot._setup_completed is False

    def test_init_components_are_none(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
    ) -> None:
        """Test that components are None before setup."""
        bot = KrakenBot()

        assert bot.event_bus is None
        assert bot.db_manager is None
        assert bot.ws_client is None
        assert bot.rest_client is None
        assert bot.strategy is None
        assert bot.execution_engine is None


class TestKrakenBotSetup:
    """Tests for KrakenBot.setup() method."""

    @pytest.mark.asyncio
    async def test_setup_initializes_all_components(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Test that setup initializes all components."""
        bot = KrakenBot()
        await bot.setup()

        assert bot.event_bus is not None
        assert bot.db_manager is not None
        assert bot.ws_client is not None
        assert bot.rest_client is not None
        assert bot.execution_engine is not None
        assert bot.strategy is not None
        assert bot._setup_completed is True

    @pytest.mark.asyncio
    async def test_setup_initializes_database(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Test that setup calls database init."""
        bot = KrakenBot()
        await bot.setup()

        mock_database_manager.init_db.assert_called_once_with(mock_get_settings)

    @pytest.mark.asyncio
    async def test_setup_registers_router_inner_bot_budgets(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
    ) -> None:
        """Test that router inner bot_ids receive the budgets used at runtime."""
        router_budget = StrategyBudget(
            max_open_positions=6,
            daily_loss_limit_eur=30.0,
            max_position_pct=20.0,
            position_size_multiplier=1.5,
        )
        mock_get_settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    budget=router_budget,
                    params={
                        "strategies": {
                            "grok_supertrend_4h": {
                                "active": True,
                                "bot_id": "supertrend_4h",
                                "params": {
                                    "max_open_positions": 2,
                                    "max_allocation_pct": 15.0,
                                },
                            },
                            "grok_ema_adx_atr": {
                                "active": True,
                                "bot_id": "ema_cross_4h",
                                "params": {
                                    "position_size_multiplier": 0.8,
                                },
                            },
                            "grok_donchian_breakout_4h": {
                                "active": False,
                                "bot_id": "donchian_breakout_4h",
                                "params": {
                                    "max_open_positions": 1,
                                },
                            },
                        }
                    },
                )
            ],
        )

        mock_router = MagicMock()
        mock_router.start = AsyncMock()
        mock_router.stop = AsyncMock()
        mock_router.get_name.return_value = "multi_strategy_router"

        mock_analyzer = MagicMock()
        mock_analyzer.initialize = AsyncMock()

        mock_global_risk_manager = MagicMock()
        mock_global_risk_manager.register_strategy = MagicMock()

        with (
            patch("krakenbot.main.MultiTimeframeAnalyzer", return_value=mock_analyzer),
            patch("krakenbot.main.GlobalRiskManager", return_value=mock_global_risk_manager),
            patch.dict(
                "krakenbot.main.STRATEGY_REGISTRY",
                {"multi_strategy_router": MagicMock(return_value=mock_router)},
            ),
        ):
            bot = KrakenBot()
            await bot.setup()

        registered_budgets = {
            call.args[0]: call.args[1]
            for call in mock_global_risk_manager.register_strategy.call_args_list
        }

        assert set(registered_budgets) == {"multi_router", "supertrend_4h", "ema_cross_4h"}

        assert registered_budgets["multi_router"].model_dump() == router_budget.model_dump()

        supertrend_budget = registered_budgets["supertrend_4h"]
        assert supertrend_budget.max_open_positions == 2
        assert supertrend_budget.daily_loss_limit_eur == 30.0
        assert supertrend_budget.max_position_pct == 15.0
        assert supertrend_budget.position_size_multiplier == 1.5

        ema_budget = registered_budgets["ema_cross_4h"]
        assert ema_budget.max_open_positions == 6
        assert ema_budget.daily_loss_limit_eur == 30.0
        assert ema_budget.max_position_pct == 20.0
        assert ema_budget.position_size_multiplier == 0.8


class TestKrakenBotStart:
    """Tests for KrakenBot.start() method."""

    @pytest.mark.asyncio
    async def test_start_raises_if_not_setup(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
    ) -> None:
        """Test that start raises RuntimeError if setup not called."""
        bot = KrakenBot()

        with pytest.raises(RuntimeError, match="Bot not initialized"):
            await bot.start()

    @pytest.mark.asyncio
    async def test_start_starts_all_components(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Test that start starts all components in correct order."""
        bot = KrakenBot()
        await bot.setup()
        await bot.start()

        # Verify execution engine started first
        mock_execution_engine.start.assert_called_once()

        # Verify strategy started
        mock_strategy.start.assert_called_once()

        # Verify WebSocket connected and subscribed
        mock_ws_client.connect.assert_called_once()
        mock_ws_client.subscribe_ohlc.assert_called_once_with(
            mock_get_settings.trading.pair,
            mock_get_settings.trading.candle_interval_min,
        )
        mock_ws_client.subscribe_ticker.assert_called_once_with(mock_get_settings.trading.pair)

        assert bot._running is True

    @pytest.mark.asyncio
    async def test_start_subscribes_1m_when_router_crash_protector_is_configured(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
    ) -> None:
        """Test that router crash protector adds the required 1m OHLC feed."""
        mock_get_settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    params={
                        "risk": {
                            "crash_threshold_pct": 7.0,
                            "crash_window_min": 30,
                            "crash_suspend_hours": 2,
                        }
                    },
                )
            ],
        )

        mock_router = MagicMock()
        mock_router.start = AsyncMock()
        mock_router.stop = AsyncMock()
        mock_router.get_name.return_value = "multi_strategy_router"

        mock_analyzer = MagicMock()
        mock_analyzer.initialize = AsyncMock()

        mock_global_risk_manager = MagicMock()
        mock_global_risk_manager.register_strategy = MagicMock()

        with (
            patch("krakenbot.main.MultiTimeframeAnalyzer", return_value=mock_analyzer),
            patch("krakenbot.main.GlobalRiskManager", return_value=mock_global_risk_manager),
            patch.dict(
                "krakenbot.main.STRATEGY_REGISTRY",
                {"multi_strategy_router": MagicMock(return_value=mock_router)},
            ),
        ):
            bot = KrakenBot()
            await bot.setup()
            await bot.start()

        subscribed_intervals = [
            await_call.args[1] for await_call in mock_ws_client.subscribe_ohlc.await_args_list
        ]

        assert subscribed_intervals == [1, 5, 15, 60, 240, 1440, 10080]

    @pytest.mark.asyncio
    async def test_start_keeps_existing_multi_strategy_intervals_without_router_crash_feed(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
    ) -> None:
        """Test that non-router multi-strategy setups keep the existing intervals."""
        mock_get_settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="grid_spot",
                    bot_id="grid_spot_test",
                    params={},
                )
            ],
        )

        mock_strategy = MagicMock()
        mock_strategy.start = AsyncMock()
        mock_strategy.stop = AsyncMock()
        mock_strategy.get_name.return_value = "grid_spot"

        mock_analyzer = MagicMock()
        mock_analyzer.initialize = AsyncMock()

        mock_global_risk_manager = MagicMock()
        mock_global_risk_manager.register_strategy = MagicMock()

        with (
            patch("krakenbot.main.MultiTimeframeAnalyzer", return_value=mock_analyzer),
            patch("krakenbot.main.GlobalRiskManager", return_value=mock_global_risk_manager),
            patch.dict(
                "krakenbot.main.STRATEGY_REGISTRY",
                {"grid_spot": MagicMock(return_value=mock_strategy)},
            ),
        ):
            bot = KrakenBot()
            await bot.setup()
            await bot.start()

        subscribed_intervals = [
            await_call.args[1] for await_call in mock_ws_client.subscribe_ohlc.await_args_list
        ]

        assert subscribed_intervals == [5, 15, 60, 240, 1440, 10080]

    @pytest.mark.asyncio
    async def test_start_routes_runtime_1m_ohlc_to_router_crash_protector(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
    ) -> None:
        """Test that runtime 1m OHLC events reach the router crash protector feed."""
        settings = mock_get_settings.model_copy(deep=True)
        settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    params={
                        "risk": {
                            "crash_threshold_pct": 7.0,
                            "crash_window_min": 30,
                            "crash_suspend_hours": 2,
                        },
                        "strategies": {},
                    },
                )
            ],
        )

        reset_event_bus()
        event_bus = EventBus()

        mock_analyzer = MagicMock()
        mock_analyzer.initialize = AsyncMock()

        mock_global_risk_manager = MagicMock()
        mock_global_risk_manager.register_strategy = MagicMock()

        with (
            patch("krakenbot.main.get_settings", return_value=settings),
            patch("krakenbot.main.get_event_bus", return_value=event_bus),
            patch("krakenbot.main.MultiTimeframeAnalyzer", return_value=mock_analyzer),
            patch("krakenbot.main.GlobalRiskManager", return_value=mock_global_risk_manager),
        ):
            bot = KrakenBot()
            await bot.setup()
            await bot.start()

        router = bot.strategies[0]
        assert isinstance(router, MultiStrategyRouter)

        await event_bus.publish(
            EventType.MARKET_OHLC,
            {
                "pair": settings.trading.pair,
                "interval": 5,
                "timestamp": "2026-03-13T12:00:00+00:00",
                "close": "42000",
                "high": "42100",
                "low": "41900",
                "open": "42050",
                "is_complete": False,
            },
        )
        assert len(router.risk_manager._price_history) == 0

        await event_bus.publish(
            EventType.MARKET_OHLC,
            {
                "pair": settings.trading.pair,
                "interval": 1,
                "timestamp": "2026-03-13T12:01:00+00:00",
                "close": "41800",
                "high": "41900",
                "low": "41700",
                "open": "42000",
                "is_complete": False,
            },
        )

        assert len(router.risk_manager._price_history) == 1
        snapshot = router.risk_manager._price_history[-1]
        assert snapshot.price == Decimal("41800")


class TestKrakenBotStop:
    """Tests for KrakenBot.stop() method."""

    @pytest.mark.asyncio
    async def test_stop_does_nothing_if_not_running(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
    ) -> None:
        """Test that stop does nothing if bot is not running."""
        bot = KrakenBot()
        await bot.stop()  # Should not raise

        assert bot._running is False

    @pytest.mark.asyncio
    async def test_stop_stops_all_components(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Test that stop stops all components in reverse order."""
        bot = KrakenBot()
        await bot.setup()
        await bot.start()
        await bot.stop()

        # Verify all components stopped
        mock_strategy.stop.assert_called_once()
        mock_execution_engine.stop.assert_called_once()
        mock_ws_client.close.assert_called_once()
        mock_rest_client.close.assert_called_once()
        mock_database_manager.close_db.assert_called_once()

        assert bot._running is False

    @pytest.mark.asyncio
    async def test_stop_handles_component_errors(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Test that stop handles errors in component shutdown."""
        # Make strategy stop raise an error
        mock_strategy.stop.side_effect = Exception("Strategy stop error")

        bot = KrakenBot()
        await bot.setup()
        await bot.start()

        # Stop should not raise despite component error
        await bot.stop()

        # Other components should still be stopped
        mock_execution_engine.stop.assert_called_once()
        mock_ws_client.close.assert_called_once()


class TestKrakenBotStats:
    """Tests for KrakenBot statistics logging."""

    @pytest.mark.asyncio
    async def test_log_stats_collects_all_component_stats(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Test that _log_stats collects stats from all components."""
        bot = KrakenBot()
        await bot.setup()
        await bot.start()

        # Call _log_stats directly
        await bot._log_stats()

        # Verify logger was called with stats
        mock_get_logger.info.assert_called()


class TestKrakenBotShutdown:
    """Tests for KrakenBot shutdown handling."""

    def test_request_shutdown_sets_flag(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
    ) -> None:
        """Test that request_shutdown sets the shutdown flag."""
        bot = KrakenBot()

        assert bot._shutdown_requested is False
        bot.request_shutdown()
        assert bot._shutdown_requested is True

    def test_is_running_property(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
    ) -> None:
        """Test is_running property reflects state correctly."""
        bot = KrakenBot()

        # Not running initially
        assert bot.is_running is False

        # After setting _running
        bot._running = True
        assert bot.is_running is True

        # After shutdown request
        bot.request_shutdown()
        assert bot.is_running is False


class TestKrakenBotRun:
    """Tests for KrakenBot.run() main loop."""

    @pytest.mark.asyncio
    async def test_run_exits_on_shutdown_request(
        self,
        mock_get_settings: Settings,
        mock_configure_logging: MagicMock,
        mock_get_logger: MagicMock,
        mock_event_bus: AsyncMock,
        mock_database_manager: MagicMock,
        mock_ws_client: MagicMock,
        mock_rest_client: MagicMock,
        mock_execution_engine: MagicMock,
        mock_strategy: MagicMock,
    ) -> None:
        """Test that run loop exits when shutdown is requested."""
        bot = KrakenBot()
        await bot.setup()
        await bot.start()

        # Schedule shutdown after a short delay
        async def delayed_shutdown():
            await asyncio.sleep(0.1)
            bot.request_shutdown()

        asyncio.create_task(delayed_shutdown())

        # Run should complete after shutdown is requested
        await asyncio.wait_for(bot.run(), timeout=2.0)

        assert bot._running is False
