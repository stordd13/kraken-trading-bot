"""Tests for SuperTrend 4h debug: regime filter and diagnostic logging."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ohlc_4h(price: str, *, ts: datetime | None = None) -> dict:
    """Build a 4h OHLC candle dict."""
    return {
        "pair": "XBT/EUR",
        "interval": "4h",
        "timeframe": "4h",
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "10.0",
        "timestamp": ts or datetime.now(UTC),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_analyzer() -> MagicMock:
    """Analyzer with controlled SuperTrend, regime, and ATR values."""
    analyzer = MagicMock()
    analyzer.get_supertrend.return_value = {
        "supertrend": Decimal("80000"),
        "direction": 1,  # UP
    }
    analyzer.get_regime.return_value = "bull"
    analyzer.get_atr.return_value = Decimal("2000")
    analyzer.update = MagicMock()
    return analyzer


@pytest.fixture
def strategy(mock_settings, mock_analyzer) -> GrokSuperTrend4hRegime:
    """SuperTrend 4h strategy ready for testing."""
    event_bus = AsyncMock()
    event_bus.subscribe = AsyncMock()
    event_bus.publish = AsyncMock()
    db_manager = MagicMock()
    s = GrokSuperTrend4hRegime(
        mock_settings,
        event_bus,
        db_manager,
        bot_id="supertrend_4h",
        strategy_params={
            "st_atr_period": 10,
            "st_multiplier": 3.0,
            "sl_atr_mult": 3.5,
            "order_size_usdc": 50,
            "max_allocation_pct": 15.0,
        },
        analyzer=mock_analyzer,
    )
    s._running = True
    return s


# ---------------------------------------------------------------------------
# Test: regime filter blocks entries correctly
# ---------------------------------------------------------------------------


class TestSuperTrendRegimeFilter:
    """Verify regime filter blocks BUY in non-bull regimes."""

    @pytest.mark.asyncio
    async def test_no_buy_in_bear_regime(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Bear regime blocks BUY even if ST direction is UP."""
        mock_analyzer.get_regime.return_value = "bear"
        strategy._is_4h = True
        strategy._current_price = Decimal("83000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_no_buy_in_neutral_regime(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Neutral regime blocks BUY."""
        mock_analyzer.get_regime.return_value = "neutral"
        strategy._is_4h = True
        strategy._current_price = Decimal("83000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_no_buy_in_strong_bear_regime(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Strong bear regime blocks BUY."""
        mock_analyzer.get_regime.return_value = "strong_bear"
        strategy._is_4h = True
        strategy._current_price = Decimal("83000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# Test: BUY signal fires in correct conditions
# ---------------------------------------------------------------------------


class TestSuperTrendBullEntry:
    """Verify BUY signals fire when conditions are met."""

    @pytest.mark.asyncio
    async def test_buy_in_bull_regime(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Bull regime + ST UP + price > ST value → BUY signal."""
        mock_analyzer.get_regime.return_value = "bull"
        mock_analyzer.get_supertrend.return_value = {
            "supertrend": Decimal("80000"),
            "direction": 1,
        }
        mock_analyzer.get_atr.return_value = Decimal("2000")

        strategy._is_4h = True
        strategy._current_price = Decimal("83000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type.value == "buy"

    @pytest.mark.asyncio
    async def test_buy_in_strong_bull_regime(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Strong bull regime also allows BUY."""
        mock_analyzer.get_regime.return_value = "strong_bull"
        mock_analyzer.get_supertrend.return_value = {
            "supertrend": Decimal("80000"),
            "direction": 1,
        }
        mock_analyzer.get_atr.return_value = Decimal("2000")

        strategy._is_4h = True
        strategy._current_price = Decimal("83000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is not None
        assert signal.signal_type.value == "buy"

    @pytest.mark.asyncio
    async def test_no_buy_when_st_direction_down(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """ST direction DOWN blocks BUY even in bull regime."""
        mock_analyzer.get_regime.return_value = "bull"
        mock_analyzer.get_supertrend.return_value = {
            "supertrend": Decimal("85000"),
            "direction": -1,
        }
        strategy._is_4h = True
        strategy._current_price = Decimal("83000")
        strategy._current_timestamp = datetime.now(UTC)

        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# Test: diagnostic logging
# ---------------------------------------------------------------------------


class TestSuperTrendDiagnosticLogging:
    """Verify strategy_tick log fires on every 4h candle."""

    @pytest.mark.asyncio
    async def test_4h_candle_produces_strategy_tick_log(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Every 4h candle must produce a strategy_tick log entry."""
        strategy.logger = MagicMock()
        await strategy._handle_ohlc(_ohlc_4h("83000"))

        call_args_list = strategy.logger.info.call_args_list
        tick_calls = [c for c in call_args_list if c[0][0] == "strategy_tick"]
        assert len(tick_calls) >= 1, (
            f"Expected strategy_tick log, got events: {[c[0][0] for c in call_args_list]}"
        )

    @pytest.mark.asyncio
    async def test_filtered_entry_produces_log(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Regime rejection produces a supertrend_entry_filtered log."""
        mock_analyzer.get_regime.return_value = "bear"
        strategy.logger = MagicMock()
        await strategy._handle_ohlc(_ohlc_4h("83000"))

        call_args_list = strategy.logger.info.call_args_list
        filtered_calls = [c for c in call_args_list if c[0][0] == "supertrend_entry_filtered"]
        assert len(filtered_calls) >= 1, (
            f"Expected supertrend_entry_filtered log, got events: "
            f"{[c[0][0] for c in call_args_list]}"
        )

    @pytest.mark.asyncio
    async def test_non_4h_candle_skips_signal(
        self,
        strategy: GrokSuperTrend4hRegime,
        mock_analyzer: MagicMock,
    ) -> None:
        """Non-4h candles should not produce strategy_tick logs."""
        strategy.logger = MagicMock()
        ohlc_1h = _ohlc_4h("83000")
        ohlc_1h["interval"] = "1h"
        ohlc_1h["timeframe"] = "1h"
        await strategy._handle_ohlc(ohlc_1h)

        call_args_list = strategy.logger.info.call_args_list
        tick_calls = [c for c in call_args_list if c[0][0] == "strategy_tick"]
        assert len(tick_calls) == 0
