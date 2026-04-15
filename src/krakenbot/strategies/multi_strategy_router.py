"""Multi-Strategy Router — orchestrator for all internal strategies.

The router is the ONLY BaseStrategy registered in the EventBus. It owns
the 7 inner strategies + GeminiGlobalRiskManager internally.

Flow:
    EventBus MARKET_OHLC → Router._handle_ohlc()
        → dispatch to 7 strategies (on_ohlc + generate_signal)
        → collect signals
        → GeminiGlobalRiskManager.process_signal() on each
        → emit processed signals to ExecutionEngine via EventBus

    EventBus TRADE_ORDER_FILLED → Router._handle_trade_filled()
        → route to the source strategy via signal.strategy (bot_id)

The inner strategies do NOT subscribe to EventBus themselves. The router
calls their methods directly, acting as a manual dispatcher.

Params (from strategies.yaml, section 'multi_strategy_router'):
    risk: dict          — GeminiGlobalRiskManager config
    capital_usdc: float — estimated total capital (for risk sizing)
    strategies: dict    — per-strategy enable/disable + params
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.core.event_bus import EventType
from krakenbot.core.logger import get_logger
from krakenbot.indicators.multi_pair_registry import MultiPairAnalyzerRegistry, normalize_pair
from krakenbot.strategies.base import BaseStrategy, TradingSignal
from krakenbot.strategies.gemini_global_risk_manager import GeminiGlobalRiskManager
from krakenbot.strategies.gemini_retour_moyenne import GeminiRetourMoyenne
from krakenbot.strategies.gemini_scalping_volatilite import GeminiScalpingVolatilite
from krakenbot.strategies.gemini_suivi_tendance_momentum import GeminiSuiviTendanceMomentum
from krakenbot.strategies.grok_adaptive_dca_weekly import GrokAdaptiveDCAWeekly
from krakenbot.strategies.grok_donchian_breakout_4h import GrokDonchianChannelBreakoutV1
from krakenbot.strategies.grok_ema_adx_atr import GrokEMA27_125_ADX_ATR
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4
from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus

logger = get_logger(__name__)

_ZERO = Decimal("0")

# Registry of inner strategy classes keyed by their canonical name
_INNER_STRATEGY_CLASSES: dict[str, type[BaseStrategy]] = {
    "gemini_scalping_volatilite": GeminiScalpingVolatilite,
    "gemini_suivi_tendance_momentum": GeminiSuiviTendanceMomentum,
    "gemini_retour_moyenne": GeminiRetourMoyenne,
    "grok_grid_atr_adaptive_v4": GrokGridATRAdaptiveV4,
    "grok_supertrend_4h": GrokSuperTrend4hRegime,
    "grok_ema_adx_atr": GrokEMA27_125_ADX_ATR,
    "grok_adaptive_dca_weekly": GrokAdaptiveDCAWeekly,
    "grok_donchian_breakout_4h": GrokDonchianChannelBreakoutV1,
}


class _RiskOverlayEventBusProxy:
    """Proxy TRADE_SIGNAL emissions through the router risk overlay."""

    def __init__(
        self,
        router: MultiStrategyRouter,
        strategy: BaseStrategy,
        event_bus: EventBus,
    ) -> None:
        self._router = router
        self._strategy = strategy
        self._event_bus = event_bus

    async def publish(self, event_type: str | EventType, data: dict[str, Any]) -> None:
        """Publish events, applying router risk overlay to trade signals."""
        if event_type == EventType.TRADE_SIGNAL and isinstance(data, dict):
            signal = data.get("signal")
            if isinstance(signal, TradingSignal):
                processed = self._router._apply_risk_overlay(signal)
                if processed and processed.should_trade:
                    await self._router._publish_processed_signal(self._strategy, processed, data)
                return

        await self._event_bus.publish(event_type, data)

    def __getattr__(self, name: str) -> Any:
        """Delegate any non-overridden attribute to the real event bus."""
        return getattr(self._event_bus, name)


class MultiStrategyRouter(BaseStrategy):
    """Orchestrator that dispatches OHLC to inner strategies and applies risk overlay.

    This is the single entry point registered in the EventBus.
    Inner strategies are managed entirely by the router — they never
    subscribe to the EventBus directly.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        bot_id: str | None = None,
        strategy_params: dict[str, Any] | None = None,
        analyzer: Any | None = None,
    ) -> None:
        """Initialize the router with inner strategies + risk manager.

        Args:
            settings: Application settings.
            event_bus: Event bus (router subscribes, inner strategies don't).
            db_manager: Database manager.
            bot_id: Router's own bot_id (default "multi_router").
            strategy_params: Config dict containing:
                - risk: {} — GeminiGlobalRiskManager config
                - capital_usdc: float — estimated total capital
                - strategies: {name: {active: bool, params: {}, bot_id: str}}
            analyzer: Shared MultiTimeframeAnalyzer.
        """
        super().__init__(
            settings,
            event_bus,
            db_manager,
            bot_id=bot_id,
            strategy_params=strategy_params,
            analyzer=analyzer,
        )

        params = strategy_params or {}

        # Total capital for risk calculations
        self.capital_usdc = Decimal(str(params.get("capital_usdc", 1000)))

        # Initialize risk manager
        risk_config = params.get("risk", {})
        self.risk_manager = GeminiGlobalRiskManager(config=risk_config)

        # Multi-pair analyzer registry (passed from main.py via strategy_params)
        self._analyzer_registry: MultiPairAnalyzerRegistry | None = params.pop(
            "_analyzer_registry", None
        )
        # Primary pair for crash protector (only tracks BTC)
        self._primary_pair = normalize_pair(settings.trading.pair)

        # Initialize inner strategies
        self._inner_strategies: list[BaseStrategy] = []
        self._strategy_by_bot_id: dict[str, BaseStrategy] = {}
        self._strategy_pair: dict[str, str] = {}  # bot_id -> normalized pair

        strategies_config: dict[str, Any] = params.get("strategies", {})
        self._init_inner_strategies(settings, event_bus, db_manager, strategies_config)

        self.logger.info(
            "multi_strategy_router_initialized",
            bot_id=self.bot_id,
            capital_usdc=float(self.capital_usdc),
            inner_strategies=[s.bot_id for s in self._inner_strategies],
            risk_config=self.risk_manager.get_config(),
        )

    def _init_inner_strategies(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        strategies_config: dict[str, Any],
    ) -> None:
        """Instantiate inner strategies from config.

        Each entry in strategies_config:
            name: {active: true/false, bot_id: "...", params: {...}}

        Strategies with active=false are skipped.
        """
        for name, strat_cfg in strategies_config.items():
            if not isinstance(strat_cfg, dict):
                continue

            if not strat_cfg.get("active", True):
                self.logger.info("inner_strategy_skipped", name=name, reason="inactive")
                continue

            # Support 'class' field for multi-pair: allows unique YAML keys
            # (e.g., "supertrend_btc") with class: grok_supertrend_4h
            class_name = strat_cfg.get("class", name)
            cls = _INNER_STRATEGY_CLASSES.get(class_name)
            if cls is None:
                self.logger.warning(
                    "inner_strategy_unknown",
                    name=name,
                    class_name=class_name,
                    available=list(_INNER_STRATEGY_CLASSES.keys()),
                )
                continue

            strat_bot_id = strat_cfg.get("bot_id", name)
            strat_params = strat_cfg.get("params", {})

            # Resolve pair for this strategy (multi-pair dispatch)
            strat_pair = normalize_pair(
                strat_params.get("pair", settings.trading.pair)
            )

            # Use pair-specific analyzer if registry available
            strat_analyzer = (
                self._analyzer_registry.get_or_create(strat_pair)
                if self._analyzer_registry
                else self.analyzer
            )

            try:
                strategy = cls(
                    settings=settings,
                    event_bus=event_bus,
                    db_manager=db_manager,
                    bot_id=strat_bot_id,
                    strategy_params=strat_params,
                    analyzer=strat_analyzer,
                )
                # Mark as running so they process data (but they don't subscribe to EventBus)
                strategy._running = True  # noqa: SLF001

                self._inner_strategies.append(strategy)
                self._strategy_by_bot_id[strat_bot_id] = strategy
                self._strategy_pair[strat_bot_id] = strat_pair

                self.logger.info(
                    "inner_strategy_initialized",
                    name=name,
                    bot_id=strat_bot_id,
                    pair=strat_pair,
                    config=strategy.get_config(),
                )
            except Exception as e:
                self.logger.error(
                    "inner_strategy_init_error",
                    name=name,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=e,
                )

    # ------------------------------------------------------------------
    # BaseStrategy interface (router-level)
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Dispatch tick to all inner strategies."""
        for strategy in self._inner_strategies:
            try:
                await strategy.on_tick(tick_data)
            except Exception as e:
                self.logger.error(
                    "inner_tick_error",
                    bot_id=strategy.bot_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """No-op — the router dispatches in _handle_ohlc override."""

    async def generate_signal(self) -> TradingSignal | None:
        """No-op — signals are collected in _handle_ohlc override."""
        return None

    # ------------------------------------------------------------------
    # Core dispatch: override _handle_ohlc
    # ------------------------------------------------------------------

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Override base _handle_ohlc to dispatch to inner strategies.

        For each inner strategy:
        1. Call its _handle_ohlc() (which runs on_ohlc + generate_signal internally)
           BUT we intercept signals before they hit EventBus.

        Actually, the inner strategies that override _handle_ohlc
        (grid, supertrend, ema_cross, dca, scalping, tendance, retour_moyenne)
        publish signals directly to EventBus in their own _handle_ohlc.

        To intercept: we temporarily collect signals by subscribing to
        TRADE_SIGNAL before dispatching, then unsubscribing after.

        SIMPLER APPROACH: We call each strategy's on_ohlc() + generate_signal()
        directly, and for strategies with custom _handle_ohlc (grid), we let
        them emit directly since risk manager processes at signal level anyway.

        FINAL DESIGN:
        - Strategies with standard flow (base _handle_ohlc): call on_ohlc + generate_signal
        - Strategies with custom _handle_ohlc override (grid): call their _handle_ohlc directly
          (they emit signals to EventBus — risk manager will wrap at execution level)
        - For standard-flow strategies: we collect signal, apply risk, then emit
        """
        if not self._running:
            return

        try:
            ohlc_pair = normalize_pair(data.get("pair", ""))
            tf = data.get("timeframe", data.get("interval"))
            close = data.get("close")
            ts = data.get("timestamp")

            # Update per-pair analyzer from live candles
            if self._analyzer_registry and tf is not None:
                self._analyzer_registry.update(
                    ohlc_pair,
                    {
                        "open": data.get("open"),
                        "high": data.get("high"),
                        "low": data.get("low"),
                        "close": close,
                        "volume": data.get("volume", 0),
                    },
                    int(tf) if not isinstance(tf, str) else {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}.get(tf, 0),
                )

            # Update crash protector price history on 1m candles (primary pair only)
            if tf in ("1m", 1, "1") and close is not None and ts is not None:
                if ohlc_pair == self._primary_pair:
                    from datetime import UTC, datetime

                    price = Decimal(str(close))
                    timestamp = (
                        ts
                        if isinstance(ts, datetime)
                        else datetime.fromisoformat(ts)
                        if isinstance(ts, str)
                        else datetime.fromtimestamp(ts, tz=UTC)
                    )
                    self.risk_manager.update_price(price, timestamp)

                    # Check crash protector
                    if self.risk_manager.check_crash_protector(timestamp):
                        await self._handle_crash(price)

            # Dispatch to each inner strategy — only if pair matches
            for strategy in self._inner_strategies:
                strategy_pair = self._strategy_pair.get(strategy.bot_id, "")
                if strategy_pair and ohlc_pair and strategy_pair != ohlc_pair:
                    continue  # Skip: this candle is not for this strategy's pair
                try:
                    await self._dispatch_to_strategy(strategy, data)
                except Exception as e:
                    self.logger.error(
                        "inner_ohlc_dispatch_error",
                        bot_id=strategy.bot_id,
                        pair=ohlc_pair,
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=e,
                    )

        except Exception as e:
            self.logger.error(
                "router_ohlc_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=e,
            )

    async def _dispatch_to_strategy(
        self,
        strategy: BaseStrategy,
        ohlc_data: dict[str, Any],
    ) -> None:
        """Dispatch OHLC to a single inner strategy and process its signal.

        Strategies that override _handle_ohlc (grid, supertrend, ema_cross,
        dca_weekly, scalping, tendance, retour_moyenne) have their own
        timeframe filtering and signal emission logic.

        We call their on_ohlc() + generate_signal() for simple strategies,
        but for strategies with custom _handle_ohlc, we need to use their
        override. The trick: we call on_ohlc() to update state, then
        generate_signal() to get the signal, then apply risk overlay.

        For grid strategy (which emits multiple signals in _handle_ohlc),
        we let it use its custom _handle_ohlc but signals go direct to EventBus.
        The ExecutionEngine will handle them.
        """
        has_custom_handle = type(strategy)._handle_ohlc is not BaseStrategy._handle_ohlc

        if has_custom_handle:
            original_event_bus = strategy.event_bus
            strategy.event_bus = _RiskOverlayEventBusProxy(self, strategy, self.event_bus)
            try:
                await strategy._handle_ohlc(ohlc_data)  # noqa: SLF001
            finally:
                strategy.event_bus = original_event_bus
        else:
            # Standard flow: on_ohlc + generate_signal
            await strategy.on_ohlc(ohlc_data)
            signal = await strategy.generate_signal()
            if signal and signal.should_trade:
                processed = self._apply_risk_overlay(signal)
                if processed:
                    await self._publish_processed_signal(
                        strategy,
                        processed,
                        {"signal": processed, "strategy": strategy.get_name()},
                    )

    def _apply_risk_overlay(self, signal: TradingSignal) -> TradingSignal | None:
        """Apply GeminiGlobalRiskManager to a signal.

        Uses the pair-specific analyzer for ATR stop-loss calculation.

        Args:
            signal: Raw signal from an inner strategy.

        Returns:
            Risk-processed signal, or None if rejected.
        """
        # Use pair-specific analyzer if available, fall back to default
        signal_analyzer = (
            self._analyzer_registry.get(signal.pair)
            if self._analyzer_registry
            else None
        ) or self.analyzer

        if signal_analyzer is None:
            return signal

        return self.risk_manager.process_signal(
            signal=signal,
            capital=self.capital_usdc,
            analyzer=signal_analyzer,
        )

    async def _publish_processed_signal(
        self,
        strategy: BaseStrategy,
        signal: TradingSignal,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Publish a risk-processed signal to the shared event bus."""
        event_payload = dict(payload or {})
        event_payload["signal"] = signal
        event_payload.setdefault("strategy", strategy.get_name())

        await self.event_bus.publish(EventType.TRADE_SIGNAL, event_payload)
        self.logger.info(
            "router_signal_emitted",
            bot_id=strategy.bot_id,
            signal_type=signal.signal_type.value,
            price=float(signal.price),
            reason=signal.reason,
        )

    # ------------------------------------------------------------------
    # Crash handling
    # ------------------------------------------------------------------

    async def _handle_crash(self, current_price: Decimal) -> None:
        """Handle crash protector activation.

        Generates SELL signals for 50% of open positions across all strategies.
        """
        # Collect open positions from all inner strategies
        open_positions = self._collect_open_positions()
        if not open_positions:
            return

        pair = self.settings.trading.pair
        crash_sells = self.risk_manager.generate_crash_sells(open_positions, current_price, pair)

        for signal in crash_sells:
            await self.event_bus.publish(
                EventType.TRADE_SIGNAL,
                {"signal": signal, "strategy": signal.strategy},
            )

        if crash_sells:
            self.logger.warning(
                "router_crash_sells_emitted",
                count=len(crash_sells),
                price=float(current_price),
            )

            # Telegram notification (fire-and-forget)
            from krakenbot.notifications.telegram import get_notifier

            notifier = get_notifier()
            if notifier:
                import asyncio
                from datetime import UTC, datetime, timedelta

                # Compute drop percentage from price history
                window_start = datetime.now(UTC) - timedelta(
                    minutes=self.risk_manager.crash_window_min
                )
                window_prices = [
                    s for s in self.risk_manager._price_history if s.timestamp >= window_start
                ]
                if window_prices:
                    max_price = max(s.price for s in window_prices)
                    drop_pct = float((max_price - current_price) / max_price * 100)
                else:
                    drop_pct = 0.0

                asyncio.create_task(
                    notifier.send_crash_protector(
                        drop_pct=f"-{drop_pct:.1f}%",
                        action=f"Closing {len(crash_sells)} positions",
                        suspend_hours=self.risk_manager.crash_suspend_hours,
                    )
                )

    def _collect_open_positions(self) -> list[dict[str, Any]]:
        """Collect open positions from all inner strategies for crash protector.

        Returns a flat list of position dicts with bot_id, position_id, amount_btc.
        """
        positions: list[dict[str, Any]] = []

        for strategy in self._inner_strategies:
            # Each strategy may have different position tracking
            # We use a duck-typing approach: check for common attributes
            bot_id = strategy.bot_id

            # Single-position strategies (supertrend, ema_cross)
            pos = getattr(strategy, "_position", None)
            if pos is not None:
                entry = getattr(pos, "entry_price", _ZERO)
                amount_usdc = getattr(pos, "amount_usdc", _ZERO)
                pid = getattr(pos, "position_id", 0)
                if entry > _ZERO:
                    positions.append(
                        {
                            "bot_id": bot_id,
                            "position_id": pid,
                            "amount_btc": float(amount_usdc / entry),
                            "entry_price": float(entry),
                        }
                    )

            # Multi-position strategies (scalping, tendance, retour_moyenne)
            open_list = getattr(strategy, "_open_positions", None)
            if open_list:
                for p in open_list:
                    entry = getattr(p, "entry_price", None) or getattr(p, "avg_entry_price", _ZERO)
                    amount_usdc = getattr(p, "amount_usdc", None) or getattr(p, "total_usdc", _ZERO)
                    pid = getattr(p, "position_id", 0)
                    if entry and entry > _ZERO:
                        positions.append(
                            {
                                "bot_id": bot_id,
                                "position_id": pid,
                                "amount_btc": float(
                                    Decimal(str(amount_usdc)) / Decimal(str(entry))
                                ),
                                "entry_price": float(entry),
                            }
                        )

            # Grid strategy: positions tracked differently
            active_positions = getattr(strategy, "_active_positions", None)
            if active_positions and isinstance(active_positions, dict):
                for pid, gp in active_positions.items():
                    entry = getattr(gp, "entry_price", _ZERO)
                    amount_usdc = getattr(gp, "order_amount_usdc", _ZERO)
                    if entry > _ZERO:
                        positions.append(
                            {
                                "bot_id": bot_id,
                                "position_id": pid,
                                "amount_btc": float(amount_usdc / entry),
                                "entry_price": float(entry),
                            }
                        )

        return positions

    # ------------------------------------------------------------------
    # Trade filled: route to source strategy
    # ------------------------------------------------------------------

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
        """Route trade fill to the source inner strategy.

        The base class _handle_trade_filled already filters by bot_id.
        But here we need to route to inner strategies, not to the router itself.
        """
        # This won't be called for inner strategies because the base
        # _handle_trade_filled checks trade_strategy == self.bot_id.
        # We override it as a no-op — routing is done in _handle_trade_filled_override.
        pass

    async def _handle_trade_filled(self, data: dict[str, Any]) -> None:
        """Override to route trade fills to inner strategies by bot_id.

        The EventBus sends ALL fills here (router is the subscribed strategy).
        We find the matching inner strategy and forward the fill.
        """
        if not self._running:
            return

        trade_strategy = data.get("strategy", "")

        # Find matching inner strategy
        target = self._strategy_by_bot_id.get(trade_strategy)
        if target is None:
            # Maybe it matches get_name() instead of bot_id
            for s in self._inner_strategies:
                if s.get_name() == trade_strategy:
                    target = s
                    break

        if target is None:
            # Not for any of our inner strategies — ignore
            return

        try:
            reference_price_str = data.get("reference_price")
            reference_price: Decimal | None = None
            if reference_price_str and reference_price_str != "0":
                reference_price = Decimal(reference_price_str)

            await target.on_trade_filled(
                trade_id=data["trade_id"],
                pair=data["pair"],
                side=data["side"],
                amount=Decimal(data["amount"]),
                price=Decimal(data["price"]),
                fee=Decimal(data["fee"]),
                reference_price=reference_price,
                position_id=data.get("position_id"),
            )

            self.logger.debug(
                "trade_fill_routed",
                trade_id=data["trade_id"],
                target_bot_id=target.bot_id,
                side=data["side"],
                price=data["price"],
            )
        except Exception as e:
            self.logger.error(
                "trade_fill_routing_error",
                error=str(e),
                error_type=type(e).__name__,
                trade_id=data.get("trade_id"),
                target=trade_strategy,
                exc_info=e,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the router — subscribe to events.

        Inner strategies are NOT started (they don't subscribe to EventBus).
        They are marked _running=True at init and receive data via dispatch.
        """
        await super().start()
        self.logger.info(
            "multi_strategy_router_started",
            inner_count=len(self._inner_strategies),
            strategies=[s.bot_id for s in self._inner_strategies],
        )

    async def stop(self) -> None:
        """Stop the router — unsubscribe from events, stop inner strategies."""
        # Mark inner strategies as stopped
        for strategy in self._inner_strategies:
            strategy._running = False  # noqa: SLF001
            self.logger.info("inner_strategy_stopped", bot_id=strategy.bot_id)

        await super().stop()
        self.logger.info("multi_strategy_router_stopped")

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return strategy name."""
        return "multi_strategy_router"

    def get_config(self) -> dict[str, Any]:
        """Return router + inner strategies configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "capital_usdc": float(self.capital_usdc),
            "risk_manager": self.risk_manager.get_config(),
            "inner_strategies": {s.bot_id: s.get_config() for s in self._inner_strategies},
            "strategy_count": len(self._inner_strategies),
        }
