"""Behavioral tests for GrokGridATRAdaptiveV4.bear_protection_mode (P7).

Covers:
- Default (mode unset): both internal flags follow YAML — back-compat.
- "none": both flags forced False, no pause regardless of regime.
- "1w_only": pause on 1w strong_bear, ignore 1d strong_bear.
- "1d_only": pause on 1d strong_bear, ignore 1w strong_bear.
- Invalid mode raises ValueError.
- Existing positions are NOT panic-sold in any mode (no SELL signal emitted).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4


def _ohlc(price: str, *, interval: int | str = "4h", ts: datetime | None = None) -> dict:
    return {
        "pair": "XBT/EUR",
        "interval": interval,
        "timeframe": str(interval),
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": "10.0",
        "timestamp": ts or datetime.now(UTC),
    }


@pytest.fixture
def mock_analyzer() -> MagicMock:
    analyzer = MagicMock()
    analyzer.get_atr.return_value = Decimal("2000")
    analyzer.get_regime.return_value = "neutral"
    analyzer.get_supertrend.return_value = None
    analyzer.update = MagicMock()
    return analyzer


def _make_strategy(
    mock_settings,
    mock_analyzer: MagicMock,
    *,
    bear_protection_mode: str | None = None,
    pause_1w_strong_bear: bool = True,
) -> GrokGridATRAdaptiveV4:
    """Helper to build a strategy with controlled bear-protection knobs."""
    event_bus = AsyncMock()
    event_bus.subscribe = AsyncMock()
    event_bus.publish = AsyncMock()
    db_manager = MagicMock()
    params: dict = {
        "grid_levels": 12,
        "min_spacing_pct": 0.015,
        "max_spacing_pct": 0.05,
        "atr_period": 14,
        "atr_multiplier": 4.0,
        "recalc_hours": 6,
        "order_size_usdc": 10,
        "max_allocation_pct": 10.0,
        "pause_1w_strong_bear": pause_1w_strong_bear,
    }
    if bear_protection_mode is not None:
        params["bear_protection_mode"] = bear_protection_mode
    s = GrokGridATRAdaptiveV4(
        mock_settings,
        event_bus,
        db_manager,
        bot_id="grid_atr_v4_bp",
        strategy_params=params,
        analyzer=mock_analyzer,
    )
    s._skip_db_sync = True
    s._running = True
    return s


# ---------------------------------------------------------------------------
# Init: flag coherence
# ---------------------------------------------------------------------------


class TestBearProtectionModeFlags:
    """Top-level mode must set internal flags coherently."""

    def test_mode_none_unset_keeps_yaml_flags(self, mock_settings, mock_analyzer) -> None:
        """No mode param → YAML flags untouched (default pause_1w=True, 1d=False)."""
        s = _make_strategy(mock_settings, mock_analyzer)
        assert s.pause_1w_strong_bear is True
        assert s.bear_protection_1d_enabled is False

    def test_mode_none_yaml_pause_false_kept(self, mock_settings, mock_analyzer) -> None:
        """No mode + YAML pause_1w=False → flag stays False (no override)."""
        s = _make_strategy(mock_settings, mock_analyzer, pause_1w_strong_bear=False)
        assert s.pause_1w_strong_bear is False
        assert s.bear_protection_1d_enabled is False

    def test_mode_none_string_forces_both_false(self, mock_settings, mock_analyzer) -> None:
        """mode='none' → both flags forced False, overriding YAML pause_1w=True."""
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="none")
        assert s.pause_1w_strong_bear is False
        assert s.bear_protection_1d_enabled is False

    def test_mode_1w_only(self, mock_settings, mock_analyzer) -> None:
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="1w_only")
        assert s.pause_1w_strong_bear is True
        assert s.bear_protection_1d_enabled is False

    def test_mode_1d_only_overrides_yaml_pause(self, mock_settings, mock_analyzer) -> None:
        """mode='1d_only' forces pause_1w=False even if YAML had it True."""
        s = _make_strategy(
            mock_settings,
            mock_analyzer,
            bear_protection_mode="1d_only",
            pause_1w_strong_bear=True,
        )
        assert s.pause_1w_strong_bear is False
        assert s.bear_protection_1d_enabled is True

    def test_invalid_mode_raises(self, mock_settings, mock_analyzer) -> None:
        with pytest.raises(ValueError, match="Invalid bear_protection_mode"):
            _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="bogus")


# ---------------------------------------------------------------------------
# Runtime: pause behavior on strong_bear regimes
# ---------------------------------------------------------------------------


class TestBearProtectionPauseRuntime:
    """Verify that the configured mode gates new grid orders correctly."""

    @pytest.mark.asyncio
    async def test_mode_none_no_pause_in_1w_strong_bear(self, mock_settings, mock_analyzer) -> None:
        """mode='none' + 1w strong_bear → grid still initializes (no pause)."""

        def regime_side_effect(tf: str) -> str:
            return "strong_bear" if tf == "1w" else "neutral"

        mock_analyzer.get_regime.side_effect = regime_side_effect
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="none")

        await s._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))

        assert s._grid_initialized is True
        assert s._paused is False

    @pytest.mark.asyncio
    async def test_mode_none_no_pause_in_1d_strong_bear(self, mock_settings, mock_analyzer) -> None:
        """mode='none' + 1d strong_bear → grid still initializes (no pause)."""

        def regime_side_effect(tf: str) -> str:
            return "strong_bear" if tf == "1d" else "neutral"

        mock_analyzer.get_regime.side_effect = regime_side_effect
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="none")

        await s._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))

        assert s._grid_initialized is True
        assert s._paused is False

    @pytest.mark.asyncio
    async def test_mode_1w_only_pauses_on_1w_not_1d(self, mock_settings, mock_analyzer) -> None:
        """mode='1w_only' pauses on 1w strong_bear and ignores 1d strong_bear."""
        # First: 1w strong_bear → must pause
        mock_analyzer.get_regime.side_effect = lambda tf: "strong_bear" if tf == "1w" else "neutral"
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="1w_only")
        await s._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        assert s._grid_initialized is False
        assert s._paused is True

        # Reset and try 1d strong_bear only → must NOT pause
        s2 = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="1w_only")
        mock_analyzer.get_regime.side_effect = lambda tf: "strong_bear" if tf == "1d" else "neutral"
        await s2._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        assert s2._grid_initialized is True
        assert s2._paused is False

    @pytest.mark.asyncio
    async def test_mode_1d_only_pauses_on_1d_not_1w(self, mock_settings, mock_analyzer) -> None:
        """mode='1d_only' pauses on 1d strong_bear and ignores 1w strong_bear."""
        # 1d strong_bear → must pause
        mock_analyzer.get_regime.side_effect = lambda tf: "strong_bear" if tf == "1d" else "neutral"
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="1d_only")
        await s._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        assert s._grid_initialized is False
        assert s._paused is True

        # 1w strong_bear only → must NOT pause (mode='1d_only' forced pause_1w=False)
        s2 = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="1d_only")
        mock_analyzer.get_regime.side_effect = lambda tf: "strong_bear" if tf == "1w" else "neutral"
        await s2._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        assert s2._grid_initialized is True
        assert s2._paused is False

    @pytest.mark.asyncio
    async def test_pause_resumes_when_regime_changes(self, mock_settings, mock_analyzer) -> None:
        """1d_only mode: pause on strong_bear, then resume when regime turns neutral."""
        # Start in strong_bear
        regime_state = {"1d": "strong_bear"}
        mock_analyzer.get_regime.side_effect = lambda tf: regime_state.get(tf, "neutral")
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="1d_only")

        await s._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        assert s._paused is True
        assert s._grid_initialized is False

        # Regime flips to neutral on next candle → grid initializes
        regime_state["1d"] = "neutral"
        await s._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, 4, tzinfo=UTC)))
        assert s._paused is False
        assert s._grid_initialized is True

    @pytest.mark.asyncio
    async def test_existing_positions_not_panic_sold(self, mock_settings, mock_analyzer) -> None:
        """When pause kicks in mid-run, no SELL signal is emitted for open positions.

        The grid pause must only block NEW order emission. Existing positions
        keep their pre-existing sell levels (handled by the order book on the
        live side, or by the backtest engine's order matching).
        """
        # Initialize grid in neutral regime first
        mock_analyzer.get_regime.return_value = "neutral"
        s = _make_strategy(mock_settings, mock_analyzer, bear_protection_mode="1d_only")
        await s._handle_ohlc(_ohlc("83000", ts=datetime(2026, 4, 1, tzinfo=UTC)))
        assert s._grid_initialized is True

        # Now flip 1d to strong_bear and emit a candle
        mock_analyzer.get_regime.side_effect = lambda tf: "strong_bear" if tf == "1d" else "neutral"

        # Patch _emit_grid_signal to capture any signal emission attempts
        emitted: list = []

        async def _capture(level) -> None:
            emitted.append(level)

        s._emit_grid_signal = _capture  # type: ignore[assignment]

        await s._handle_ohlc(_ohlc("80000", ts=datetime(2026, 4, 1, 4, tzinfo=UTC)))

        # No new orders emitted during pause; existing grid_levels dict still intact
        assert emitted == []
        assert s._paused is True
