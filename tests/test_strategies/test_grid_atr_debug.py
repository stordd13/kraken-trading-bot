"""Tests for Grid ATR V4 debug fixes: spacing cap and diagnostic logging."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ohlc(
    price: str,
    *,
    interval: int | str = "4h",
    ts: datetime | None = None,
) -> dict:
    """Build a complete OHLC candle dict."""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_analyzer() -> MagicMock:
    """Analyzer returning controlled ATR and regime values."""
    analyzer = MagicMock()
    analyzer.get_atr.return_value = Decimal("2000")
    analyzer.get_regime.return_value = "neutral"
    analyzer.get_supertrend.return_value = None
    analyzer.update = MagicMock()
    return analyzer


@pytest.fixture
def strategy(mock_settings, mock_analyzer) -> GrokGridATRAdaptiveV4:
    """Grid ATR V4 strategy with max_spacing_pct = 5%."""
    event_bus = AsyncMock()
    event_bus.subscribe = AsyncMock()
    event_bus.publish = AsyncMock()
    db_manager = MagicMock()
    s = GrokGridATRAdaptiveV4(
        mock_settings,
        event_bus,
        db_manager,
        bot_id="grid_atr_v4",
        strategy_params={
            "grid_levels": 12,
            "min_spacing_pct": 0.015,
            "max_spacing_pct": 0.05,
            "atr_period": 14,
            "atr_multiplier": 4.0,
            "recalc_hours": 6,
            "order_size_usdc": 10,
            "max_allocation_pct": 10.0,
        },
        analyzer=mock_analyzer,
    )
    s._skip_db_sync = True
    s._running = True
    return s


# ---------------------------------------------------------------------------
# Test: spacing is capped
# ---------------------------------------------------------------------------


class TestGridSpacingCap:
    """Verify _calculate_spacing enforces max_spacing_pct."""

    def test_spacing_capped_at_max(self, strategy: GrokGridATRAdaptiveV4) -> None:
        """High ATR ($5000) → spacing must not exceed 5%."""
        spacing = strategy._calculate_spacing(Decimal("5000"), Decimal("83000"))
        # Without cap: 5000 * 4.0 / 83000 = 24.1%
        assert spacing == Decimal("0.05")

    def test_spacing_uses_atr_when_within_bounds(self, strategy: GrokGridATRAdaptiveV4) -> None:
        """ATR giving spacing within [1.5%, 5%] is used as-is."""
        spacing = strategy._calculate_spacing(Decimal("600"), Decimal("83000"))
        expected = Decimal("600") * Decimal("4.0") / Decimal("83000")
        assert spacing == expected

    def test_spacing_floor_enforced(self, strategy: GrokGridATRAdaptiveV4) -> None:
        """Very low ATR → spacing = min_spacing_pct (1.5%)."""
        spacing = strategy._calculate_spacing(Decimal("100"), Decimal("83000"))
        assert spacing == Decimal("0.015")

    def test_spacing_with_zero_price(self, strategy: GrokGridATRAdaptiveV4) -> None:
        """Price <= 0 returns min_spacing_pct."""
        assert strategy._calculate_spacing(Decimal("1000"), Decimal("0")) == Decimal("0.015")


# ---------------------------------------------------------------------------
# Test: grid levels are coherent
# ---------------------------------------------------------------------------


class TestGridLevelsCentered:
    """Grid levels must be around current price, not 50% below."""

    def test_buy_levels_below_sell_levels_above(self, strategy: GrokGridATRAdaptiveV4) -> None:
        """BUY levels below price, SELL levels above."""
        price = Decimal("83000")
        spacing = Decimal("0.03")
        levels = strategy._build_grid(price, spacing, "neutral")

        for level in levels:
            if level.side == "buy":
                assert level.price < price
            else:
                assert level.price > price

    def test_max_distance_with_capped_spacing(self, strategy: GrokGridATRAdaptiveV4) -> None:
        """With 5% spacing and 6 levels per side, max distance = 30%."""
        price = Decimal("83000")
        # Force spacing to cap
        spacing = strategy._calculate_spacing(Decimal("5000"), price)
        assert spacing == Decimal("0.05")

        levels = strategy._build_grid(price, spacing, "neutral")
        for level in levels:
            distance_pct = abs(level.price - price) / price
            # 6 levels × 5% = 30% max
            assert distance_pct <= Decimal("0.31"), (
                f"Level {level.price} is {float(distance_pct) * 100:.1f}% from price {price}"
            )


# ---------------------------------------------------------------------------
# Test: grid recalculation
# ---------------------------------------------------------------------------


class TestGridRecalc:
    """Grid recalculation should recenter on current price."""

    @pytest.mark.asyncio
    async def test_recalc_recenters_grid(
        self,
        strategy: GrokGridATRAdaptiveV4,
        mock_analyzer: MagicMock,
    ) -> None:
        """After price moves from 50K→83K, grid recenters on 83K."""
        old_price = Decimal("50000")
        spacing = strategy._calculate_spacing(Decimal("1000"), old_price)
        strategy._build_grid(old_price, spacing, "neutral")
        assert strategy._grid_center == old_price

        new_price = Decimal("83000")
        now = datetime.now(UTC)
        new_spacing = strategy._calculate_spacing(Decimal("2000"), new_price)
        await strategy._recalculate_grid(new_price, new_spacing, "neutral", now)

        assert strategy._grid_center == new_price

    @pytest.mark.asyncio
    async def test_recalc_timer_triggers(
        self,
        strategy: GrokGridATRAdaptiveV4,
        mock_analyzer: MagicMock,
    ) -> None:
        """Grid recalculates after recalc_hours (6h) have passed."""
        mock_analyzer.get_regime.return_value = "neutral"
        mock_analyzer.get_atr.return_value = Decimal("1000")

        t0 = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
        await strategy._handle_ohlc(_ohlc("83000", ts=t0))
        assert strategy._grid_initialized is True
        assert strategy._grid_center == Decimal("83000")

        # 7 hours later, price moved to 85K → triggers recalc
        t1 = t0 + timedelta(hours=7)
        await strategy._handle_ohlc(_ohlc("85000", ts=t1))
        assert strategy._grid_center == Decimal("85000")


# ---------------------------------------------------------------------------
# Test: get_config includes max_spacing_pct
# ---------------------------------------------------------------------------


class TestGridConfig:
    def test_get_config_has_max_spacing_pct(self, strategy: GrokGridATRAdaptiveV4) -> None:
        """get_config() must include the new max_spacing_pct param."""
        config = strategy.get_config()
        assert "max_spacing_pct" in config
        assert config["max_spacing_pct"] == 0.05
