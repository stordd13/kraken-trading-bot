"""Targeted integration regressions for runtime, paper, and backtest alignment.

These tests intentionally cover known cross-component defects without
implementing the business fixes in this ticket.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from krakenbot.config.settings import (
    MultiStrategySettings,
    MultiTimeframeSettings,
    StrategyBudget,
    StrategyInstanceConfig,
    TradingMode,
)
from krakenbot.connectors.kraken_rest import KrakenRestClient
from krakenbot.core.event_bus import EventBus
from krakenbot.execution.engine import ExecutionEngine
from krakenbot.execution.order_manager import OrderManager
from krakenbot.main import KrakenBot
from krakenbot.models.base import BotStatus, OrderStatus, PositionStatus, SignalType, TradeSide
from krakenbot.models.trades import BotState, Trade
from krakenbot.strategies.base import BaseStrategy, TradingSignal
from krakenbot.strategies.gemini_global_risk_manager import GeminiGlobalRiskManager
from krakenbot.strategies.multi_strategy_router import MultiStrategyRouter


class _FakeOrder:
    """Minimal order object used by OrderManager paper fill tests."""

    def __init__(
        self,
        *,
        pair: str = "XBT/USDC",
        side: TradeSide = TradeSide.BUY,
        amount: Decimal = Decimal("0.001"),
        price: Decimal = Decimal("41500"),
        signal_metadata: dict | None = None,
    ) -> None:
        self.id = uuid.uuid4()
        self.order_id = f"paper-{uuid.uuid4().hex[:8]}"
        self.bot_id = "test-bot"
        self.pair = pair
        self.side = side
        self.amount = amount
        self.price = price
        self.filled_amount = Decimal("0")
        self.filled_price: Decimal | None = None
        self.fee = Decimal("0")
        self.status = OrderStatus.PENDING
        self.strategy = "test-bot"
        self.signal_metadata = signal_metadata
        self.expires_at = None

    @property
    def is_pending(self) -> bool:
        return self.status == OrderStatus.PENDING

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED


class _CapturedSession:
    """Capture objects added during ExecutionEngine lifecycle helpers."""

    def __init__(self) -> None:
        self.open_positions: list[object] = []
        self.trade_records: dict[uuid.UUID, Trade] = {}

    def add(self, obj: object) -> None:
        self.open_positions.append(obj)

    async def execute(self, _stmt: object) -> SimpleNamespace:
        open_position = self.open_positions[0] if self.open_positions else None
        return SimpleNamespace(scalar_one_or_none=lambda: open_position)

    async def get(self, _model: object, obj_id: uuid.UUID) -> Trade | None:
        return self.trade_records.get(obj_id)


class _BacktestStrategySpy:
    """Backtest strategy stub exposing on_trade_filled()."""

    def __init__(self) -> None:
        self.fills: list[dict[str, object]] = []

    async def on_trade_filled(self, **kwargs: object) -> None:
        self.fills.append(kwargs)


class _PositionAssigningStrategy(BaseStrategy):
    """Minimal strategy that assigns a deterministic position_id on fill."""

    def __init__(
        self,
        settings: object,
        event_bus: EventBus,
        db_manager: object,
        *,
        bot_id: str,
        assigned_position_id: int,
    ) -> None:
        super().__init__(settings, event_bus, db_manager, bot_id=bot_id)
        self.assigned_position_id = assigned_position_id
        self._position = None

    async def on_tick(self, tick_data: dict[str, object]) -> None:
        return None

    async def on_ohlc(self, ohlc_data: dict[str, object]) -> None:
        return None

    async def generate_signal(self) -> TradingSignal | None:
        return None

    def get_name(self) -> str:
        return "position_assigning_strategy"

    def get_config(self) -> dict[str, object]:
        return {"name": self.get_name()}

    async def on_trade_filled(
        self,
        trade_id: str,
        pair: str,
        side: str,
        amount: Decimal,
        price: Decimal,
        fee: Decimal,
        reference_price: Decimal | None,
        position_id: int | None,
    ) -> None:
        if side == "buy":
            self._position = SimpleNamespace(position_id=self.assigned_position_id)


class _FakeTopLevelStrategy:
    """Top-level strategy stub used to exercise KrakenBot assembly logic."""

    def __init__(
        self,
        *,
        settings: object,
        event_bus: object,
        db_manager: object,
        bot_id: str,
        strategy_params: dict[str, object] | None = None,
        analyzer: object | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.db_manager = db_manager
        self.bot_id = bot_id
        self.strategy_params = strategy_params or {}
        self.analyzer = analyzer

    def get_name(self) -> str:
        return "multi_strategy_router"


class _CustomHandleRoutingStrategy(BaseStrategy):
    """Custom-handler inner strategy used to exercise router interception."""

    async def on_tick(self, tick_data: dict[str, object]) -> None:
        return None

    async def on_ohlc(self, ohlc_data: dict[str, object]) -> None:
        return None

    async def generate_signal(self) -> TradingSignal | None:
        return None

    def get_name(self) -> str:
        return "custom_handle_routing_strategy"

    def get_config(self) -> dict[str, object]:
        return {"name": self.get_name()}

    async def _handle_ohlc(self, data: dict[str, object]) -> None:
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/USDC",
            price=Decimal("50000"),
            confidence=0.9,
            reason="custom-handle-integration",
            strategy=self.bot_id,
            timestamp=datetime.now(UTC),
            metadata={"order_type": "limit", "limit_price": "49950"},
        )
        await self.event_bus.publish(
            "trade.signal",
            {"signal": signal, "strategy": self.get_name()},
        )


def _load_backtest_engine() -> type:
    """Import BacktestEngine without requiring scripts/ to be a package."""

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    scripts_path = str(scripts_dir)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    return importlib.import_module("backtest").BacktestEngine


def _make_trade(
    *,
    side: TradeSide,
    pair: str = "XBT/USDC",
    amount: Decimal = Decimal("0.001"),
    price: Decimal = Decimal("42000"),
    fee: Decimal = Decimal("0.05"),
    strategy: str = "test-bot",
) -> Trade:
    """Build a Trade model for execution lifecycle tests."""

    from krakenbot.models.base import TradeStatus

    return Trade(
        id=uuid.uuid4(),
        timestamp=datetime.now(UTC),
        pair=pair,
        side=side,
        amount=amount,
        price=price,
        fee=fee,
        fee_currency=pair.split("/")[1],
        strategy=strategy,
        status=TradeStatus.FILLED,
        order_id=f"order-{uuid.uuid4().hex[:8]}",
    )


def _make_order_manager(settings: object) -> tuple[OrderManager, MagicMock]:
    """Build an OrderManager with paper-mode collaborators stubbed out."""

    rest_client = MagicMock()
    rest_client.is_paper_mode = True
    rest_client._paper_balance = {
        "USDC": Decimal("1000"),
        "XBT": Decimal("1"),
    }
    rest_client._paper_orders = {}
    rest_client.cancel_order = AsyncMock()
    rest_client.persist_paper_balance = AsyncMock()

    order_manager = OrderManager(
        rest_client=rest_client,
        db_manager=MagicMock(),
        event_bus=AsyncMock(),
        settings=settings,
    )
    order_manager._update_order_in_db = AsyncMock()
    order_manager._publish_fill_event = AsyncMock()
    return order_manager, rest_client


def _make_signal(
    *,
    signal_type: SignalType,
    price: Decimal,
    strategy: str = "test-bot",
    pair: str = "XBT/USDC",
    metadata: dict | None = None,
) -> TradingSignal:
    """Build a TradingSignal for integration tests."""

    return TradingSignal(
        signal_type=signal_type,
        pair=pair,
        price=price,
        confidence=0.9,
        reason="integration-test",
        strategy=strategy,
        timestamp=datetime.now(UTC),
        metadata=metadata or {},
    )


class TestP0PaperTrading:
    """P0 regressions in paper runtime execution."""

    @pytest.mark.asyncio
    async def test_paper_balance_normalization_keeps_initialized_balance_sellable(
        self,
        mock_settings,
    ) -> None:
        """A paper balance seeded from Kraken must remain usable on XBT sells."""

        settings = mock_settings.model_copy(deep=True)
        settings.trading.mode = TradingMode.PAPER
        settings.trading.pair = "XBT/USDC"

        with patch("ccxt.async_support.kraken"):
            client = KrakenRestClient(settings, EventBus(), MagicMock())

        client._fetch_real_balance = AsyncMock(
            return_value={
                "BTC": Decimal("0.25"),
                "USDC": Decimal("1000"),
            }
        )
        client._save_paper_balance_to_db = AsyncMock()
        client._save_trade = AsyncMock()
        client.persist_paper_balance = AsyncMock()
        client.update_last_price("XBT/USDC", Decimal("42000"))

        await client.initialize_paper_balance(force_reset=True)

        trade = await client.place_market_order(
            "XBT/USDC",
            TradeSide.SELL,
            Decimal("0.1"),
            strategy="paper-bot",
        )

        assert trade.side == TradeSide.SELL
        assert trade.amount == Decimal("0.1")

    @pytest.mark.asyncio
    async def test_paper_balance_initialization_merges_btc_and_xbt_aliases(
        self,
        mock_settings,
    ) -> None:
        """Paper init must merge Kraken BTC/XBT aliases before SELL checks."""

        settings = mock_settings.model_copy(deep=True)
        settings.trading.mode = TradingMode.PAPER
        settings.trading.pair = "XBT/USDC"

        with patch("ccxt.async_support.kraken"):
            client = KrakenRestClient(settings, EventBus(), MagicMock())

        client._fetch_real_balance = AsyncMock(
            return_value={
                "BTC": Decimal("0.10"),
                "XBT": Decimal("0.15"),
                "USDC": Decimal("1000"),
            }
        )
        client._save_paper_balance_to_db = AsyncMock()
        client._save_trade = AsyncMock()
        client.persist_paper_balance = AsyncMock()
        client.update_last_price("XBT/USDC", Decimal("42000"))

        await client.initialize_paper_balance(force_reset=True)

        trade = await client.place_market_order(
            "XBT/USDC",
            TradeSide.SELL,
            Decimal("0.20"),
            strategy="paper-bot",
        )

        final_balance = client.get_paper_balance()

        assert trade.side == TradeSide.SELL
        assert trade.amount == Decimal("0.20")
        assert final_balance["BTC"] == Decimal("0.05")
        assert "XBT" not in final_balance

    @pytest.mark.asyncio
    async def test_paper_limit_fill_requires_same_pair(self, mock_settings) -> None:
        """An unrelated pair candle must not fill a pending paper order."""

        settings = mock_settings.model_copy(deep=True)
        settings.trading.pair = "XBT/USDC"
        settings.trading.candle_interval_min = 5

        order_manager, rest_client = _make_order_manager(settings)
        pending_order = _FakeOrder(pair="XBT/USDC", price=Decimal("41500"))
        order_manager._pending_orders[pending_order.order_id] = pending_order

        await order_manager.on_ohlc(
            {
                "pair": "ETH/USDC",
                "interval": 5,
                "timeframe": "5m",
                "low": Decimal("3500"),
                "high": Decimal("3600"),
            }
        )
        await order_manager.check_pending_orders()

        assert pending_order.order_id in order_manager._pending_orders
        assert rest_client._paper_balance["USDC"] == Decimal("1000")

    @pytest.mark.asyncio
    async def test_paper_limit_fill_requires_execution_timeframe(self, mock_settings) -> None:
        """A non-trigger timeframe candle must not fill a pending paper order."""

        settings = mock_settings.model_copy(deep=True)
        settings.trading.pair = "XBT/USDC"
        settings.trading.candle_interval_min = 5
        settings.multi_timeframe = MultiTimeframeSettings(trigger_timeframe=5)

        order_manager, rest_client = _make_order_manager(settings)
        pending_order = _FakeOrder(pair="XBT/USDC", price=Decimal("41500"))
        order_manager._pending_orders[pending_order.order_id] = pending_order

        await order_manager.on_ohlc(
            {
                "pair": "XBT/USDC",
                "interval": 1440,
                "timeframe": "1d",
                "low": Decimal("41000"),
                "high": Decimal("43000"),
            }
        )
        await order_manager.check_pending_orders()

        assert pending_order.order_id in order_manager._pending_orders
        assert rest_client._paper_balance["XBT"] == Decimal("1")


class TestP0RuntimeLifecycle:
    """P0 regressions in runtime orchestration and position lifecycle."""

    @pytest.mark.asyncio
    async def test_multi_strategy_runtime_subscribes_1m_for_crash_protector(
        self,
        mock_settings,
    ) -> None:
        """The live runtime must subscribe to 1m candles to activate crash protection."""

        settings = mock_settings.model_copy(deep=True)
        settings.trading.mode = TradingMode.PAPER
        settings.trading.pair = "XBT/USDC"
        settings.multi_timeframe = MultiTimeframeSettings(
            trigger_timeframe=5,
            zone_timeframe=15,
            trend_timeframe=60,
        )
        settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    budget=StrategyBudget(),
                    params={"strategies": {}},
                )
            ],
        )

        with (
            patch("krakenbot.main.get_settings", return_value=settings),
            patch("krakenbot.main.configure_logging"),
            patch("krakenbot.main.get_logger", return_value=MagicMock()),
        ):
            bot = KrakenBot()

        bot._setup_completed = True
        bot.execution_engine = MagicMock(start=AsyncMock())
        bot.analyzer = MagicMock(initialize=AsyncMock())
        bot.rest_client = MagicMock(is_paper_mode=False)
        bot.ws_client = MagicMock(
            connect=AsyncMock(),
            subscribe_ohlc=AsyncMock(),
            subscribe_ticker=AsyncMock(),
        )
        bot.event_bus = MagicMock(subscribe=AsyncMock())
        bot.order_manager = MagicMock(load_pending_from_db=AsyncMock(), on_ohlc=AsyncMock())
        bot.db_manager = MagicMock()
        bot._reconcile_positions_with_exchange = AsyncMock()
        bot._init_bot_state = AsyncMock()

        router = MagicMock()
        router.start = AsyncMock()
        router.get_name.return_value = "multi_strategy_router"
        bot.strategies = [router]

        await bot.start()

        subscribed_intervals = [
            call.args[1] for call in bot.ws_client.subscribe_ohlc.await_args_list
        ]
        assert 1 in subscribed_intervals

    @pytest.mark.asyncio
    async def test_position_id_lifecycle_closes_the_open_position_record(
        self,
        mock_settings,
    ) -> None:
        """A strategy-assigned BUY fill position_id must be the same one closed on SELL."""

        settings = mock_settings.model_copy(deep=True)
        event_bus = EventBus()
        engine = ExecutionEngine(settings, event_bus, MagicMock(), MagicMock())
        session = _CapturedSession()
        strategy = _PositionAssigningStrategy(
            settings,
            event_bus,
            MagicMock(),
            bot_id="router-inner-bot",
            assigned_position_id=7,
        )
        strategy._running = True

        bot_state = BotState(
            bot_id="router-inner-bot",
            strategy="router-inner-bot",
            status=BotStatus.RUNNING,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            daily_trades_count=0,
        )

        buy_signal = _make_signal(
            signal_type=SignalType.BUY,
            strategy="router-inner-bot",
            price=Decimal("42000"),
            metadata={"reference_price": "42000"},
        )
        buy_trade = _make_trade(
            side=TradeSide.BUY,
            strategy="router-inner-bot",
            price=Decimal("42000"),
            fee=Decimal("0.04"),
        )

        await strategy._handle_trade_filled(
            {
                "trade_id": str(buy_trade.id),
                "pair": buy_trade.pair,
                "side": "buy",
                "amount": str(buy_trade.amount),
                "price": str(buy_trade.price),
                "fee": str(buy_trade.fee),
                "strategy": "router-inner-bot",
                "reference_price": "42000",
                "signal_metadata": buy_signal.metadata,
            }
        )

        await engine._handle_buy_trade(session, bot_state, buy_trade, buy_signal)

        created_position = session.open_positions[0]

        sell_trade = _make_trade(
            side=TradeSide.SELL,
            strategy="router-inner-bot",
            price=Decimal("43000"),
            fee=Decimal("0.05"),
        )
        session.trade_records[sell_trade.id] = sell_trade
        sell_signal = _make_signal(
            signal_type=SignalType.SELL,
            strategy="router-inner-bot",
            price=Decimal("43000"),
            metadata={"position_id": 7},
        )

        await engine._handle_sell_trade(session, bot_state, sell_trade, sell_signal)

        assert created_position.position_id == 7
        assert created_position.status == PositionStatus.CLOSED
        assert created_position.exit_trade_id == sell_trade.id


class TestP1IntegrationGaps:
    """P1 regressions that still need coverage before fixes land."""

    def test_router_inner_bot_ids_receive_budget_registration(self, mock_settings) -> None:
        """Per-strategy budgets must be registered for the router's inner bot_ids."""

        settings = mock_settings.model_copy(deep=True)
        settings.trading.pair = "XBT/USDC"
        settings.multi_strategy = MultiStrategySettings(
            enabled=True,
            strategies=[
                StrategyInstanceConfig(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    budget=StrategyBudget(
                        max_open_positions=10,
                        daily_loss_limit_eur=50.0,
                        max_position_pct=90.0,
                        position_size_multiplier=1.0,
                    ),
                    params={
                        "strategies": {
                            "grok_supertrend_4h": {
                                "active": True,
                                "bot_id": "supertrend_4h",
                                "params": {},
                            },
                            "grok_ema_adx_atr": {
                                "active": True,
                                "bot_id": "ema_cross_4h",
                                "params": {},
                            },
                        }
                    },
                )
            ],
        )

        with (
            patch("krakenbot.main.get_settings", return_value=settings),
            patch("krakenbot.main.configure_logging"),
            patch("krakenbot.main.get_logger", return_value=MagicMock()),
        ):
            bot = KrakenBot()

        bot.event_bus = MagicMock()
        bot.db_manager = MagicMock()
        bot.global_risk_manager = MagicMock()

        with (
            patch("krakenbot.main.MultiTimeframeAnalyzer", return_value=MagicMock()),
            patch.dict(
                "krakenbot.main.STRATEGY_REGISTRY",
                {"multi_strategy_router": _FakeTopLevelStrategy},
            ),
        ):
            bot._setup_strategies()

        registered_bot_ids = {
            call.args[0] for call in bot.global_risk_manager.register_strategy.call_args_list
        }
        assert {"supertrend_4h", "ema_cross_4h"}.issubset(registered_bot_ids)

    @pytest.mark.asyncio
    async def test_runtime_and_backtest_apply_same_position_size_to_risk_processed_signal(
        self,
        mock_settings,
    ) -> None:
        """The same risk-processed signal should size identically in runtime and backtest."""

        settings = mock_settings.model_copy(deep=True)
        settings.trading.pair = "XBT/USDC"
        settings.trading.default_order_amount_eur = 100.0

        raw_signal = _make_signal(
            signal_type=SignalType.BUY,
            strategy="grok_supertrend_4h",
            price=Decimal("50000"),
            metadata={
                "order_type": "limit",
                "limit_price": "49950",
                "order_size_usdc": 200.0,
                "position_size_multiplier": 2.0,
            },
        )
        analyzer = MagicMock()
        analyzer.get_atr.return_value = Decimal("5000")

        risk_manager = GeminiGlobalRiskManager()
        processed_signal = risk_manager.process_signal(raw_signal, Decimal("1000"), analyzer)
        assert processed_signal is not None

        runtime_engine = ExecutionEngine(settings, EventBus(), MagicMock(), MagicMock())
        runtime_amount = await runtime_engine._calculate_order_amount(
            processed_signal.pair,
            TradeSide.BUY,
            processed_signal.price,
            processed_signal,
        )
        runtime_notional = runtime_amount * processed_signal.price

        BacktestEngine = _load_backtest_engine()
        backtest_engine = BacktestEngine(
            settings,
            MagicMock(),
            strategy_name="grok_supertrend_4h",
            candle_interval=240,
        )
        backtest_engine.strategy = _BacktestStrategySpy()

        await backtest_engine.execute_signal(
            processed_signal,
            processed_signal.price,
            is_limit_fill=False,
        )

        backtest_notional = backtest_engine.metrics.trades[-1].amount_usdc
        assert runtime_notional == backtest_notional

    @pytest.mark.asyncio
    async def test_router_custom_handle_ohlc_applies_gemini_risk_overlay(
        self,
        mock_settings,
    ) -> None:
        """Custom inner handlers must still emit risk-processed router signals."""

        analyzer = MagicMock()
        analyzer.get_atr.return_value = Decimal("5000")
        event_bus = EventBus()
        router = MultiStrategyRouter(
            settings=mock_settings,
            event_bus=event_bus,
            db_manager=MagicMock(),
            bot_id="multi_router",
            strategy_params={"capital_usdc": 1000, "strategies": {}},
            analyzer=analyzer,
        )

        custom_strategy = _CustomHandleRoutingStrategy(
            mock_settings,
            event_bus,
            MagicMock(),
            bot_id="supertrend_4h",
        )
        custom_strategy._running = True  # noqa: SLF001

        router._inner_strategies = [custom_strategy]  # noqa: SLF001
        router._strategy_by_bot_id = {custom_strategy.bot_id: custom_strategy}  # noqa: SLF001
        router._running = True  # noqa: SLF001

        published_payloads: list[dict[str, object]] = []

        async def _capture_signal(data: dict[str, object]) -> None:
            published_payloads.append(data)

        await event_bus.subscribe("trade.signal", _capture_signal)

        await router._handle_ohlc(
            {
                "pair": "XBT/USDC",
                "interval": 240,
                "timestamp": "2026-03-14T00:00:00+00:00",
                "close": "50000",
            }
        )

        assert len(published_payloads) == 1
        published_signal = published_payloads[0]["signal"]
        assert isinstance(published_signal, TradingSignal)
        assert "risk_stop_loss" in published_signal.metadata
        assert "risk_position_size_btc" in published_signal.metadata
