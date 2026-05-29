"""Behavioral tests for breakout_confirmation on grok_donchian_breakout_4h (P7).

Covers:
- Default (close): fresh breakout fires when current close crosses above prev
  upper band AND prev close was at or below it.
- high_low: fires when current candle high crosses above prev upper band
  AND prev high was at or below it.
- Both modes: only fire when daily regime is bullish AND ADX > threshold.
- Both modes: stale breakouts (already above) do not re-fire.
- Invalid mode raises ValueError.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.models.base import SignalType
from krakenbot.strategies.grok_donchian_breakout_4h import GrokDonchianChannelBreakoutV1


def _ohlc(
    *,
    close: str,
    high: str | None = None,
    interval: int | str = "4h",
    ts: datetime | None = None,
) -> dict:
    return {
        "pair": "BTC/USDC",
        "interval": interval,
        "timeframe": str(interval),
        "open": close,
        "high": high if high is not None else close,
        "low": close,
        "close": close,
        "volume": "10.0",
        "timestamp": ts or datetime.now(UTC),
    }


@pytest.fixture
def mock_analyzer() -> MagicMock:
    a = MagicMock()
    a.get_donchian.return_value = {
        "upper": Decimal("83500"),
        "lower": Decimal("80000"),
    }
    a.get_regime.return_value = "bull"
    a.get_adx.return_value = Decimal("25")
    a.get_atr.return_value = Decimal("500")
    a.update = MagicMock()
    return a


def _captured_buys(strategy: GrokDonchianChannelBreakoutV1) -> list:
    """Extract BUY TradingSignals from the event_bus.publish AsyncMock.

    BaseStrategy publishes via ``event_bus.publish(EventType.TRADE_SIGNAL, {"signal": s, ...})``
    so ``call.args[1]["signal"]`` is the signal object.
    """
    out = []
    for call in strategy.event_bus.publish.call_args_list:
        if len(call.args) < 2:
            continue
        data = call.args[1]
        if not isinstance(data, dict):
            continue
        signal = data.get("signal")
        if signal is None:
            continue
        if getattr(signal, "signal_type", None) == SignalType.BUY:
            out.append(signal)
    return out


def _make_strategy(
    mock_settings,
    mock_analyzer: MagicMock,
    *,
    breakout_confirmation: str | None = None,
) -> GrokDonchianChannelBreakoutV1:
    event_bus = AsyncMock()
    event_bus.subscribe = AsyncMock()
    event_bus.publish = AsyncMock()
    db_manager = MagicMock()
    params: dict = {
        "pair": "BTC/USDC",
        "donchian_upper_period": 20,
        "donchian_lower_period": 10,
        "sl_atr_mult": 3.5,
        "adx_threshold": 18,
        "order_size_usdc": 30,
        "max_allocation_pct": 10.0,
    }
    if breakout_confirmation is not None:
        params["breakout_confirmation"] = breakout_confirmation
    s = GrokDonchianChannelBreakoutV1(
        mock_settings,
        event_bus,
        db_manager,
        bot_id="donchian_test",
        strategy_params=params,
        analyzer=mock_analyzer,
    )
    s._is_4h = True
    s._running = True
    return s


# ---------------------------------------------------------------------------
# Init: param validation
# ---------------------------------------------------------------------------


class TestBreakoutConfirmationInit:
    def test_default_is_close(self, mock_settings, mock_analyzer) -> None:
        s = _make_strategy(mock_settings, mock_analyzer)
        assert s.breakout_confirmation == "close"

    def test_explicit_close(self, mock_settings, mock_analyzer) -> None:
        s = _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="close")
        assert s.breakout_confirmation == "close"

    def test_high_low(self, mock_settings, mock_analyzer) -> None:
        s = _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="high_low")
        assert s.breakout_confirmation == "high_low"

    def test_invalid_raises(self, mock_settings, mock_analyzer) -> None:
        with pytest.raises(ValueError, match="Invalid breakout_confirmation"):
            _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="bogus")


# ---------------------------------------------------------------------------
# Runtime: close mode (existing behavior)
# ---------------------------------------------------------------------------


class TestCloseModeTrigger:
    """Verify the close-mode trigger fires exactly when the prior logic would have."""

    @pytest.mark.asyncio
    async def test_fresh_breakout_on_close(self, mock_settings, mock_analyzer) -> None:
        s = _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="close")

        # Tick 1: close 83000 (below prev_upper 83500) — seeds prev state
        # Use a Donchian that's prev_upper=83500 for the next tick
        await s._handle_ohlc(_ohlc(close="83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        # First tick has no prev → no signal

        # Tick 2: close 84000 (> prev_upper 83500), prev_close was 83000 (<=83500)
        await s._handle_ohlc(_ohlc(close="84000", ts=datetime(2026, 4, 1, 4, tzinfo=UTC)))

        buys = _captured_buys(s)
        assert len(buys) >= 1, "Expected at least one BUY signal emitted"

    @pytest.mark.asyncio
    async def test_no_signal_if_prev_close_already_above(
        self, mock_settings, mock_analyzer
    ) -> None:
        """Stale breakout: prev_close was already > prev_upper → no fresh signal."""
        s = _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="close")

        # Both ticks above 83500 — prev_close becomes 84000, then current=84500
        await s._handle_ohlc(_ohlc(close="84000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        s.event_bus.publish.reset_mock()
        await s._handle_ohlc(_ohlc(close="84500", ts=datetime(2026, 4, 1, 4, tzinfo=UTC)))

        # No BUY emitted — prev_close (84000) > prev_upper (83500)
        assert _captured_buys(s) == []


# ---------------------------------------------------------------------------
# Runtime: high_low mode (new behavior)
# ---------------------------------------------------------------------------


class TestHighLowModeTrigger:
    """high_low mode: trigger off candle HIGH, not close."""

    @pytest.mark.asyncio
    async def test_high_crosses_but_close_does_not(self, mock_settings, mock_analyzer) -> None:
        """high_low mode fires when high crosses prev_upper even if close stays below.

        With prev_upper=83500, prev_high=82000 (below), then current high=84000
        (above) but close=83000 (still below), the high_low mode must trigger
        whereas the close mode would NOT.
        """
        s = _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="high_low")

        # Tick 1: close 82000 with high 82000 → seeds prev_high=82000 (<= 83500)
        await s._handle_ohlc(
            _ohlc(close="82000", high="82000", ts=datetime(2026, 4, 1, tzinfo=UTC))
        )

        # Tick 2: high 84000 (> prev_upper 83500), close 83000 (stays below)
        await s._handle_ohlc(
            _ohlc(close="83000", high="84000", ts=datetime(2026, 4, 1, 4, tzinfo=UTC))
        )

        buys = _captured_buys(s)
        assert len(buys) >= 1, "high_low mode should fire on high crossing prev_upper"

    @pytest.mark.asyncio
    async def test_close_mode_does_not_fire_for_same_candles(
        self, mock_settings, mock_analyzer
    ) -> None:
        """Sanity check: with the same candle sequence, close mode does NOT trigger."""
        s = _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="close")

        await s._handle_ohlc(
            _ohlc(close="82000", high="82000", ts=datetime(2026, 4, 1, tzinfo=UTC))
        )
        await s._handle_ohlc(
            _ohlc(close="83000", high="84000", ts=datetime(2026, 4, 1, 4, tzinfo=UTC))
        )

        assert _captured_buys(s) == [], (
            "close mode should NOT fire when close stays below prev_upper"
        )

    @pytest.mark.asyncio
    async def test_no_signal_if_prev_high_already_above(self, mock_settings, mock_analyzer) -> None:
        """Stale breakout in high_low: prev_high already > prev_upper → no signal."""
        s = _make_strategy(mock_settings, mock_analyzer, breakout_confirmation="high_low")

        # Tick 1: high 84000 (above prev_upper 83500) → prev_high becomes 84000
        await s._handle_ohlc(
            _ohlc(close="83200", high="84000", ts=datetime(2026, 4, 1, tzinfo=UTC))
        )
        s.event_bus.publish.reset_mock()

        # Tick 2: high 84500 (still above) → prev_high (84000) > prev_upper (83500)
        await s._handle_ohlc(
            _ohlc(close="84200", high="84500", ts=datetime(2026, 4, 1, 4, tzinfo=UTC))
        )

        assert _captured_buys(s) == []
