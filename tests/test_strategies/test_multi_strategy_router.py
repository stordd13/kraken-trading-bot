"""Tests for MultiStrategyRouter risk-path behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from krakenbot.core.event_bus import EventBus, EventType
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal
from krakenbot.strategies.multi_strategy_router import MultiStrategyRouter


class _CustomHandleStrategy(BaseStrategy):
    """Inner strategy that emits directly from a custom _handle_ohlc()."""

    async def on_tick(self, tick_data: dict[str, object]) -> None:
        return None

    async def on_ohlc(self, ohlc_data: dict[str, object]) -> None:
        return None

    async def generate_signal(self) -> TradingSignal | None:
        return None

    def get_name(self) -> str:
        return "custom_router_inner"

    def get_config(self) -> dict[str, object]:
        return {}

    async def _handle_ohlc(self, data: dict[str, object]) -> None:
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/USDC",
            price=Decimal("50000"),
            confidence=0.9,
            reason="raw_inner_signal",
            strategy=self.bot_id,
            timestamp=datetime.now(UTC),
            metadata={"raw": True},
        )
        await self.event_bus.publish(
            EventType.TRADE_SIGNAL,
            {"signal": signal, "strategy": self.get_name()},
        )


class TestMultiStrategyRouterRiskPath:
    """Tests that the router remains the authority for risk processing."""

    @pytest.mark.asyncio
    async def test_custom_handle_ohlc_signals_are_risk_processed_before_publish(
        self,
        mock_settings,
    ) -> None:
        """Custom _handle_ohlc emitters must still pass through the router overlay."""
        event_bus = EventBus()
        router = MultiStrategyRouter(
            settings=mock_settings,
            event_bus=event_bus,
            db_manager=MagicMock(),
            bot_id="multi_router",
            strategy_params={"strategies": {}},
            analyzer=MagicMock(),
        )

        strategy = _CustomHandleStrategy(
            settings=mock_settings,
            event_bus=event_bus,
            db_manager=MagicMock(),
            bot_id="supertrend_4h",
            strategy_params={},
            analyzer=MagicMock(),
        )
        strategy._running = True  # noqa: SLF001

        router._inner_strategies = [strategy]  # noqa: SLF001
        router._strategy_by_bot_id = {strategy.bot_id: strategy}  # noqa: SLF001
        router._running = True  # noqa: SLF001

        emitted_payloads: list[dict[str, object]] = []

        async def _collect_signal(data: dict[str, object]) -> None:
            emitted_payloads.append(data)

        await event_bus.subscribe(EventType.TRADE_SIGNAL, _collect_signal)

        def _mark_risk(signal: TradingSignal) -> TradingSignal:
            return TradingSignal(
                signal_type=signal.signal_type,
                pair=signal.pair,
                price=signal.price,
                confidence=signal.confidence,
                reason=signal.reason,
                strategy=signal.strategy,
                timestamp=signal.timestamp,
                metadata={**signal.metadata, "risk_applied": True},
            )

        router._apply_risk_overlay = MagicMock(side_effect=_mark_risk)  # type: ignore[method-assign]

        await router._handle_ohlc(
            {
                "pair": "XBT/USDC",
                "interval": 240,
                "timestamp": "2026-03-14T00:00:00+00:00",
                "close": "50000",
            }
        )

        router._apply_risk_overlay.assert_called_once()  # type: ignore[attr-defined]
        assert len(emitted_payloads) == 1

        published_signal = emitted_payloads[0]["signal"]
        assert isinstance(published_signal, TradingSignal)
        assert published_signal.metadata["risk_applied"] is True
        assert published_signal.metadata["raw"] is True

    @pytest.mark.asyncio
    async def test_custom_handle_ohlc_signal_is_blocked_when_overlay_rejects(
        self,
        mock_settings,
    ) -> None:
        """A rejected custom-handler signal must not leak to the execution bus."""
        event_bus = EventBus()
        router = MultiStrategyRouter(
            settings=mock_settings,
            event_bus=event_bus,
            db_manager=MagicMock(),
            bot_id="multi_router",
            strategy_params={"strategies": {}},
            analyzer=MagicMock(),
        )

        strategy = _CustomHandleStrategy(
            settings=mock_settings,
            event_bus=event_bus,
            db_manager=MagicMock(),
            bot_id="supertrend_4h",
            strategy_params={},
            analyzer=MagicMock(),
        )
        strategy._running = True  # noqa: SLF001

        router._inner_strategies = [strategy]  # noqa: SLF001
        router._strategy_by_bot_id = {strategy.bot_id: strategy}  # noqa: SLF001
        router._running = True  # noqa: SLF001

        emitted_payloads: list[dict[str, object]] = []

        async def _collect_signal(data: dict[str, object]) -> None:
            emitted_payloads.append(data)

        await event_bus.subscribe(EventType.TRADE_SIGNAL, _collect_signal)
        router._apply_risk_overlay = MagicMock(return_value=None)  # type: ignore[method-assign]

        await router._handle_ohlc(
            {
                "pair": "XBT/USDC",
                "interval": 240,
                "timestamp": "2026-03-14T00:00:00+00:00",
                "close": "50000",
            }
        )

        router._apply_risk_overlay.assert_called_once()  # type: ignore[attr-defined]
        assert emitted_payloads == []
