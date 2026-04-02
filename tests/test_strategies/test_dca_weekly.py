"""Tests for GrokAdaptiveDCAWeekly multi-pair and fill-timing behavior.

Tests:
- Signal generation on ETH/USDC and SOL/USDC pairs
- _last_buy_week set on fill (not signal)
- Independent instances don't share week state
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    LogLevel,
    RiskManagementSettings,
    Settings,
    StrategySettings,
    TradingMode,
    TradingSettings,
)
from krakenbot.models.base import SignalType
from krakenbot.strategies.grok_adaptive_dca_weekly import GrokAdaptiveDCAWeekly

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Monday 2025-01-06 00:00 UTC (ISO week 2, weekday 0)
_MONDAY = datetime(2025, 1, 6, 0, 0, 0, tzinfo=UTC)


def _make_settings(pair: str = "XBT/USDC") -> Settings:
    """Build minimal Settings with the given trading pair."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        log_level=LogLevel.DEBUG,
        log_json=False,
        kraken=KrakenSettings(api_key="k", api_secret="s"),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/test",
        ),
        risk=RiskManagementSettings(),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair=pair,
            default_order_amount_eur=100.0,
        ),
        strategy=StrategySettings(),
    )


def _mock_analyzer(
    rsi_1d: float = 50.0,
    ema200_1d: float = 40000.0,
    regime_1w: str = "neutral",
    regime_1d: str = "neutral",
) -> MagicMock:
    """Create a mock MultiTimeframeAnalyzer."""
    analyzer = MagicMock()
    analyzer.get_rsi = MagicMock(return_value=rsi_1d)
    analyzer.get_ema = MagicMock(return_value=ema200_1d)

    def _get_regime(tf: str) -> str:
        return regime_1w if tf == "1w" else regime_1d

    analyzer.get_regime = MagicMock(side_effect=_get_regime)
    return analyzer


def _mock_event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


def _mock_db_manager() -> MagicMock:
    manager = MagicMock()

    @asynccontextmanager
    async def _read_session() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    manager.read_session = _read_session
    return manager


def _make_strategy(pair: str = "XBT/USDC", bot_id: str | None = None) -> GrokAdaptiveDCAWeekly:
    """Instantiate a DCA strategy wired to mocks."""
    settings = _make_settings(pair)
    strategy = GrokAdaptiveDCAWeekly(
        settings=settings,
        event_bus=_mock_event_bus(),
        db_manager=_mock_db_manager(),
        bot_id=bot_id,
        analyzer=_mock_analyzer(),
    )
    # Pre-set state so generate_signal() can fire
    strategy._is_daily = True
    strategy._current_price = Decimal("3000")
    strategy._current_timestamp = _MONDAY
    return strategy


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDCAWeeklyMultiPair:
    """Signal generation works on any pair, not just BTC."""

    @pytest.mark.asyncio
    async def test_dca_weekly_eth_generates_signal(self) -> None:
        """ETH/USDC DCA emits a BUY signal on Monday."""
        strategy = _make_strategy(pair="ETH/USDC")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.pair == "ETH/USDC"
        assert signal.metadata["order_type"] == "limit"

    @pytest.mark.asyncio
    async def test_dca_weekly_sol_generates_signal(self) -> None:
        """SOL/USDC DCA emits a BUY signal on Monday."""
        strategy = _make_strategy(pair="SOL/USDC")
        strategy._current_price = Decimal("150")

        signal = await strategy.generate_signal()

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.pair == "SOL/USDC"


class TestDCAWeeklyFillTiming:
    """_last_buy_week must be set on fill, not on signal."""

    @pytest.mark.asyncio
    async def test_dca_weekly_week_flag_set_on_fill_not_signal(self) -> None:
        """Signal sets _pending_week_key; fill commits _last_buy_week."""
        strategy = _make_strategy()

        # Before signal
        assert strategy._last_buy_week is None
        assert strategy._pending_week_key is None

        signal = await strategy.generate_signal()
        assert signal is not None

        # After signal: pending is set, but last_buy_week is NOT
        assert strategy._pending_week_key is not None
        assert strategy._last_buy_week is None

        # Simulate fill
        await strategy.on_trade_filled(
            trade_id="bt-1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            fee=Decimal("0.10"),
            reference_price=None,
            position_id=None,
        )

        # After fill: last_buy_week committed, pending cleared
        assert strategy._last_buy_week is not None
        assert strategy._pending_week_key is None

    @pytest.mark.asyncio
    async def test_dca_weekly_different_pairs_independent(self) -> None:
        """Buying BTC on Monday does not block ETH the same Monday."""
        btc_strategy = _make_strategy(pair="XBT/USDC", bot_id="dca_btc")
        eth_strategy = _make_strategy(pair="ETH/USDC", bot_id="dca_eth")

        # Both emit signals
        btc_signal = await btc_strategy.generate_signal()
        eth_signal = await eth_strategy.generate_signal()
        assert btc_signal is not None
        assert eth_signal is not None

        # Fill BTC only
        await btc_strategy.on_trade_filled(
            trade_id="bt-1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            fee=Decimal("0.10"),
            reference_price=None,
            position_id=None,
        )

        # BTC week is locked
        assert btc_strategy._last_buy_week is not None
        # ETH is still independent — not locked
        assert eth_strategy._last_buy_week is None
