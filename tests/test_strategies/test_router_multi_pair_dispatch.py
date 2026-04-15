"""Tests for MultiStrategyRouter multi-pair dispatch filtering.

Validates that:
- BTC candles only reach BTC-configured strategies
- ETH candles only reach ETH-configured strategies
- Crash protector only tracks primary pair (BTC)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.indicators.multi_pair_registry import MultiPairAnalyzerRegistry
from krakenbot.strategies.multi_strategy_router import MultiStrategyRouter


def _make_router(
    mock_settings: MagicMock,
    strategies_config: dict | None = None,
) -> MultiStrategyRouter:
    """Build a MultiStrategyRouter with multi-pair config."""
    registry = MultiPairAnalyzerRegistry()
    registry.get_or_create("BTC/USDC")
    registry.get_or_create("ETH/USDC")

    if strategies_config is None:
        strategies_config = {
            "supertrend_btc": {
                "active": True,
                "class": "grok_supertrend_4h",
                "bot_id": "supertrend_4h_btc",
                "params": {"pair": "BTC/USDC"},
            },
            "supertrend_eth": {
                "active": True,
                "class": "grok_supertrend_4h",
                "bot_id": "supertrend_4h_eth",
                "params": {"pair": "ETH/USDC"},
            },
        }

    event_bus = MagicMock()
    event_bus.publish = AsyncMock()
    event_bus.subscribe = MagicMock()
    db_manager = MagicMock()

    router = MultiStrategyRouter(
        settings=mock_settings,
        event_bus=event_bus,
        db_manager=db_manager,
        bot_id="multi_router",
        strategy_params={
            "capital_usdc": 10000,
            "risk": {},
            "strategies": strategies_config,
            "_analyzer_registry": registry,
        },
        analyzer=registry.get_or_create("BTC/USDC"),
    )
    return router


class TestRouterMultiPairDispatch:
    """Pair filtering in _handle_ohlc."""

    @pytest.mark.asyncio
    async def test_btc_candle_reaches_only_btc_strategy(self, mock_settings: MagicMock) -> None:
        """A BTC/USDC candle should only be dispatched to BTC strategies."""
        router = _make_router(mock_settings)
        router._running = True

        # Mock _dispatch_to_strategy to track which strategies receive data
        dispatched: list[str] = []

        async def tracking_dispatch(strategy, data):
            dispatched.append(strategy.bot_id)

        router._dispatch_to_strategy = tracking_dispatch

        await router._handle_ohlc(
            {
                "pair": "BTC/USDC",
                "timeframe": 240,
                "open": 84000,
                "high": 85000,
                "low": 83000,
                "close": 84500,
                "volume": 100,
            }
        )

        assert "supertrend_4h_btc" in dispatched
        assert "supertrend_4h_eth" not in dispatched

    @pytest.mark.asyncio
    async def test_eth_candle_reaches_only_eth_strategy(self, mock_settings: MagicMock) -> None:
        """An ETH/USDC candle should only be dispatched to ETH strategies."""
        router = _make_router(mock_settings)
        router._running = True

        dispatched: list[str] = []

        async def tracking_dispatch(strategy, data):
            dispatched.append(strategy.bot_id)

        router._dispatch_to_strategy = tracking_dispatch

        await router._handle_ohlc(
            {
                "pair": "ETH/USDC",
                "timeframe": 240,
                "open": 3400,
                "high": 3500,
                "low": 3300,
                "close": 3450,
                "volume": 500,
            }
        )

        assert "supertrend_4h_eth" in dispatched
        assert "supertrend_4h_btc" not in dispatched

    @pytest.mark.asyncio
    async def test_xbt_pair_normalizes_to_btc(self, mock_settings: MagicMock) -> None:
        """XBT/USDC candles should be normalized to BTC/USDC for dispatch."""
        router = _make_router(mock_settings)
        router._running = True

        dispatched: list[str] = []

        async def tracking_dispatch(strategy, data):
            dispatched.append(strategy.bot_id)

        router._dispatch_to_strategy = tracking_dispatch

        await router._handle_ohlc(
            {
                "pair": "XBT/USDC",
                "timeframe": 240,
                "open": 84000,
                "high": 85000,
                "low": 83000,
                "close": 84500,
                "volume": 100,
            }
        )

        assert "supertrend_4h_btc" in dispatched
        assert "supertrend_4h_eth" not in dispatched

    @pytest.mark.asyncio
    async def test_unknown_pair_reaches_no_strategy(self, mock_settings: MagicMock) -> None:
        """A candle for an unconfigured pair should not reach any strategy."""
        router = _make_router(mock_settings)
        router._running = True

        dispatched: list[str] = []

        async def tracking_dispatch(strategy, data):
            dispatched.append(strategy.bot_id)

        router._dispatch_to_strategy = tracking_dispatch

        await router._handle_ohlc(
            {
                "pair": "SOL/USDC",
                "timeframe": 240,
                "open": 140,
                "high": 150,
                "low": 135,
                "close": 145,
                "volume": 1000,
            }
        )

        assert dispatched == []


class TestRouterCrashProtectorPairScope:
    """Crash protector only tracks the primary pair (BTC)."""

    @pytest.mark.asyncio
    async def test_crash_protector_ignores_eth_candles(self, mock_settings: MagicMock) -> None:
        """1m ETH candles should NOT update crash protector price history."""
        router = _make_router(mock_settings)
        router._running = True

        # Prevent actual dispatch
        router._dispatch_to_strategy = AsyncMock()

        # Send an ETH 1m candle
        await router._handle_ohlc(
            {
                "pair": "ETH/USDC",
                "timeframe": 1,
                "open": 3400,
                "high": 3500,
                "low": 3300,
                "close": 3450,
                "volume": 500,
                "timestamp": 1700000000,
            }
        )

        assert len(router.risk_manager._price_history) == 0

    @pytest.mark.asyncio
    async def test_crash_protector_tracks_primary_pair_candles(
        self, mock_settings: MagicMock
    ) -> None:
        """1m candles for the primary pair should update crash protector."""
        router = _make_router(mock_settings)
        router._running = True

        # Prevent actual dispatch
        router._dispatch_to_strategy = AsyncMock()

        # Primary pair is derived from settings.trading.pair (XBT/EUR → BTC/EUR)
        primary_pair = router._primary_pair

        await router._handle_ohlc(
            {
                "pair": primary_pair,
                "timeframe": 1,
                "open": 84000,
                "high": 85000,
                "low": 83000,
                "close": 84500,
                "volume": 100,
                "timestamp": 1700000000,
            }
        )

        assert len(router.risk_manager._price_history) == 1


class TestRouterStrategyPairMapping:
    """Verify _strategy_pair dict is built correctly."""

    def test_strategy_pair_mapping_from_config(self, mock_settings: MagicMock) -> None:
        router = _make_router(mock_settings)
        assert router._strategy_pair["supertrend_4h_btc"] == "BTC/USDC"
        assert router._strategy_pair["supertrend_4h_eth"] == "ETH/USDC"

    def test_class_field_resolves_strategy(self, mock_settings: MagicMock) -> None:
        """The 'class' field should resolve the correct strategy class."""
        router = _make_router(mock_settings)
        # Both strategies should be grok_supertrend_4h instances
        for strat in router._inner_strategies:
            assert (
                "supertrend" in strat.get_name().lower()
                or "supertrend" in type(strat).__name__.lower()
            )
