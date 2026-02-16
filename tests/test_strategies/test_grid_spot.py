"""Tests for GridSpotStrategy.

Tests cover:
- Grid initialization: correct levels, symmetric around price
- BUY/SELL fill handling via on_trade_filled
- Rebalance: triggers when price deviates from center
- Grid metrics: profit, pairs completed, efficiency
- Backtest compatibility: add_position, close_position
- generate_signal always returns None
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    LogLevel,
    MultiStrategySettings,
    MultiTimeframeSettings,
    OrderSettings,
    RiskManagementSettings,
    Settings,
    StrategySettings,
    TradingMode,
    TradingSettings,
)
from krakenbot.strategies.grid_spot import GridSpotStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Create settings for grid spot testing."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        log_level=LogLevel.DEBUG,
        log_json=False,
        kraken=KrakenSettings(api_key="test_key", api_secret="test_secret"),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/test",
            echo=False,
            pool_size=2,
            max_overflow=2,
        ),
        risk=RiskManagementSettings(
            max_position_pct=5.0,
            daily_loss_limit_eur=50.0,
            max_open_positions=10,
            min_trade_interval_sec=60,
            emergency_stop_loss_pct=10.0,
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="XBT/USDC",
            default_order_amount_eur=15.0,
            candle_interval_min=5,
        ),
        strategy=StrategySettings(
            name="grid_spot",
            buy_threshold_pct=-1.0,
            sell_threshold_pct=2.0,
            lookback_periods=5,
            max_holding_minutes=120,
        ),
        multi_strategy=MultiStrategySettings(enabled=False),
        multi_timeframe=MultiTimeframeSettings(trigger_timeframe=5),
        order=OrderSettings(limit_buy_offset_pct=0.05),
    )


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_db_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def strategy(
    settings: Settings,
    mock_event_bus: AsyncMock,
    mock_db_manager: MagicMock,
) -> GridSpotStrategy:
    """Create GridSpotStrategy for testing."""
    s = GridSpotStrategy(
        settings,
        mock_event_bus,
        mock_db_manager,
        strategy_params={
            "grid_levels": 10,
            "grid_spacing_pct": 2.0,
            "range_size_pct": 20.0,
            "rebalance_threshold_pct": 5.0,
            "order_amount_usdc": 30,
        },
    )
    s._skip_db_sync = True
    return s


def _ohlc(
    price: str,
    *,
    high: str | None = None,
    low: str | None = None,
    ts: datetime | None = None,
) -> dict:
    """Build an OHLC candle dict."""
    return {
        "pair": "XBT/USDC",
        "interval": 5,
        "open": price,
        "high": high or price,
        "low": low or price,
        "close": price,
        "volume": "10.0",
        "is_complete": True,
        "timestamp": ts or datetime.now(UTC),
    }


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestGridSpotInitialization:
    """Tests for GridSpotStrategy initialization."""

    def test_default_params(self, strategy: GridSpotStrategy) -> None:
        assert strategy.grid_levels == 10
        assert strategy.grid_spacing_pct == Decimal("2.0")
        assert strategy.range_size_pct == Decimal("20.0")
        assert strategy.rebalance_threshold_pct == Decimal("5.0")
        assert strategy.order_amount_usdc == Decimal("30")

    def test_get_name(self, strategy: GridSpotStrategy) -> None:
        assert strategy.get_name() == "grid_spot"

    def test_get_config(self, strategy: GridSpotStrategy) -> None:
        config = strategy.get_config()
        assert config["grid_levels"] == 10
        assert config["grid_spacing_pct"] == 2.0
        assert config["range_size_pct"] == 20.0
        assert config["completed_pairs"] == 0
        assert config["total_grid_profit"] == 0.0

    def test_initial_state(self, strategy: GridSpotStrategy) -> None:
        assert strategy.current_price is None
        assert strategy.open_positions_count == 0
        assert strategy._grid_initialized is False
        assert strategy._completed_pairs == 0
        assert strategy._total_grid_profit == Decimal("0")


# ---------------------------------------------------------------------------
# Grid initialization
# ---------------------------------------------------------------------------


class TestGridInitialization:
    """Tests for grid level calculation."""

    def test_grid_levels_count(self, strategy: GridSpotStrategy) -> None:
        """Grid creates correct number of levels."""
        orders = strategy.initialize_grid(Decimal("50000"))
        # Some levels might land exactly on price and be skipped
        assert len(orders) >= strategy.grid_levels - 1

    def test_grid_symmetric(self, strategy: GridSpotStrategy) -> None:
        """Grid has buy levels below and sell levels above price."""
        orders = strategy.initialize_grid(Decimal("50000"))
        buy_orders = [o for o in orders if o.side == "buy"]
        sell_orders = [o for o in orders if o.side == "sell"]

        assert len(buy_orders) > 0
        assert len(sell_orders) > 0

        # All buy prices below current
        for o in buy_orders:
            assert o.price < Decimal("50000")

        # All sell prices above current
        for o in sell_orders:
            assert o.price > Decimal("50000")

    def test_grid_range(self, strategy: GridSpotStrategy) -> None:
        """Grid levels are within the expected range."""
        price = Decimal("50000")
        orders = strategy.initialize_grid(price)
        prices = [o.price for o in orders]

        expected_low = price * Decimal("0.9")  # -10%
        expected_high = price * Decimal("1.1")  # +10%

        for p in prices:
            assert p >= expected_low - Decimal("1")
            assert p <= expected_high + Decimal("1")

    def test_grid_sets_center(self, strategy: GridSpotStrategy) -> None:
        """initialize_grid sets the center price."""
        strategy.initialize_grid(Decimal("50000"))
        assert strategy._grid_center == Decimal("50000")
        assert strategy._grid_initialized is True

    def test_grid_orders_stored(self, strategy: GridSpotStrategy) -> None:
        """Grid orders are stored in _grid_orders dict."""
        orders = strategy.initialize_grid(Decimal("50000"))
        assert len(strategy._grid_orders) == len(orders)
        for o in orders:
            key = f"{o.side}_{o.price}"
            assert key in strategy._grid_orders

    def test_grid_orders_all_pending(self, strategy: GridSpotStrategy) -> None:
        """All initial orders are pending."""
        orders = strategy.initialize_grid(Decimal("50000"))
        for o in orders:
            assert o.status == "pending"

    def test_grid_amount_usdc(self, strategy: GridSpotStrategy) -> None:
        """All orders have the configured USDC amount."""
        orders = strategy.initialize_grid(Decimal("50000"))
        for o in orders:
            assert o.amount_usdc == Decimal("30")


# ---------------------------------------------------------------------------
# generate_signal always returns None
# ---------------------------------------------------------------------------


class TestGridGenerateSignal:
    """Grid manages its own signals, generate_signal returns None."""

    @pytest.mark.asyncio
    async def test_generate_signal_returns_none(self, strategy: GridSpotStrategy) -> None:
        signal = await strategy.generate_signal()
        assert signal is None

    @pytest.mark.asyncio
    async def test_generate_signal_none_even_with_price(self, strategy: GridSpotStrategy) -> None:
        strategy._current_price = Decimal("50000")
        signal = await strategy.generate_signal()
        assert signal is None


# ---------------------------------------------------------------------------
# on_ohlc
# ---------------------------------------------------------------------------


class TestGridOnOhlc:
    """Tests for on_ohlc price updates."""

    @pytest.mark.asyncio
    async def test_on_ohlc_updates_price(self, strategy: GridSpotStrategy) -> None:
        await strategy.on_ohlc(_ohlc("50000"))
        assert strategy._current_price == Decimal("50000")

    @pytest.mark.asyncio
    async def test_on_ohlc_updates_timestamp(self, strategy: GridSpotStrategy) -> None:
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        await strategy.on_ohlc(_ohlc("50000", ts=ts))
        assert strategy._current_timestamp == ts


# ---------------------------------------------------------------------------
# _handle_ohlc (integration)
# ---------------------------------------------------------------------------


class TestGridHandleOhlc:
    """Tests for _handle_ohlc override."""

    @pytest.mark.asyncio
    async def test_first_ohlc_initializes_grid(self, strategy: GridSpotStrategy) -> None:
        """First candle initializes the grid."""
        strategy._running = True
        await strategy._handle_ohlc(_ohlc("50000"))
        assert strategy._grid_initialized is True
        assert len(strategy._grid_orders) > 0

    @pytest.mark.asyncio
    async def test_not_running_does_nothing(self, strategy: GridSpotStrategy) -> None:
        """_handle_ohlc does nothing when not running."""
        strategy._running = False
        await strategy._handle_ohlc(_ohlc("50000"))
        assert not strategy._grid_initialized

    @pytest.mark.asyncio
    async def test_second_ohlc_does_not_reinitialize(self, strategy: GridSpotStrategy) -> None:
        """After init, subsequent candles don't reinitialize."""
        strategy._running = True
        await strategy._handle_ohlc(_ohlc("50000"))
        first_orders = dict(strategy._grid_orders)

        await strategy._handle_ohlc(_ohlc("50100"))
        assert strategy._grid_orders == first_orders


# ---------------------------------------------------------------------------
# on_trade_filled
# ---------------------------------------------------------------------------


class TestGridTradeFilled:
    """Tests for on_trade_filled grid pair logic."""

    @pytest.mark.asyncio
    async def test_buy_fill_opens_position(self, strategy: GridSpotStrategy) -> None:
        """BUY fill creates a grid position."""
        strategy._current_timestamp = datetime.now(UTC)
        await strategy.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.0006"),
            price=Decimal("49000"),
            fee=Decimal("0.05"),
            reference_price=Decimal("50000"),
            position_id=None,
        )
        assert strategy.open_positions_count == 1
        pos = strategy._grid_positions[0]
        assert pos.entry_price == Decimal("49000")

    @pytest.mark.asyncio
    async def test_buy_fill_places_sell_at_upper_level(self, strategy: GridSpotStrategy) -> None:
        """BUY fill places a paired SELL order at upper level."""
        strategy._current_timestamp = datetime.now(UTC)
        await strategy.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.0006"),
            price=Decimal("49000"),
            fee=Decimal("0.05"),
            reference_price=Decimal("50000"),
            position_id=None,
        )
        # Expected sell level = 49000 * 1.02 = 49980
        expected_sell = Decimal("49980.0")
        assert f"sell_{expected_sell}" in strategy._grid_orders

    @pytest.mark.asyncio
    async def test_sell_fill_records_profit(self, strategy: GridSpotStrategy) -> None:
        """SELL fill records profit from the pair."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        # Simulate a buy fill first
        await strategy.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("49000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=None,
        )
        assert strategy.open_positions_count == 1

        # Now sell at the sell level (49000 * 1.02 = 49980)
        await strategy.on_trade_filled(
            trade_id="T2",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.001"),
            price=Decimal("49980"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=1,
        )

        assert strategy._completed_pairs == 1
        assert strategy._total_grid_profit > Decimal("0")
        assert strategy.open_positions_count == 0

    @pytest.mark.asyncio
    async def test_sell_fill_places_buy_at_lower_level(self, strategy: GridSpotStrategy) -> None:
        """SELL fill places a paired BUY at lower level."""
        now = datetime.now(UTC)
        strategy._current_timestamp = now

        await strategy.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("50000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=None,
        )

        sell_price = Decimal("51000")
        await strategy.on_trade_filled(
            trade_id="T2",
            pair="XBT/USDC",
            side="sell",
            amount=Decimal("0.001"),
            price=sell_price,
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=1,
        )

        # Buy at lower: 51000 * 0.98 = 49980
        expected_buy = Decimal("49980.0")
        assert f"buy_{expected_buy}" in strategy._grid_orders


# ---------------------------------------------------------------------------
# Rebalance
# ---------------------------------------------------------------------------


class TestGridRebalance:
    """Tests for grid rebalance logic."""

    def test_should_rebalance_true(self, strategy: GridSpotStrategy) -> None:
        """Rebalance triggers when deviation exceeds threshold."""
        strategy._grid_center = Decimal("50000")
        # 6% above center -> should trigger (threshold is 5%)
        assert strategy._should_rebalance(Decimal("53000")) is True

    def test_should_rebalance_false(self, strategy: GridSpotStrategy) -> None:
        """No rebalance when within threshold."""
        strategy._grid_center = Decimal("50000")
        # 2% above center -> should not trigger
        assert strategy._should_rebalance(Decimal("51000")) is False

    def test_should_rebalance_below(self, strategy: GridSpotStrategy) -> None:
        """Rebalance also triggers when price drops below threshold."""
        strategy._grid_center = Decimal("50000")
        # 6% below center
        assert strategy._should_rebalance(Decimal("47000")) is True

    def test_should_rebalance_no_center(self, strategy: GridSpotStrategy) -> None:
        """No rebalance if center is not set."""
        assert strategy._should_rebalance(Decimal("50000")) is False

    @pytest.mark.asyncio
    async def test_rebalance_reinitializes(self, strategy: GridSpotStrategy) -> None:
        """Rebalance reinitializes grid around new center."""
        strategy.initialize_grid(Decimal("50000"))
        old_center = strategy._grid_center

        await strategy._rebalance_grid(Decimal("55000"))

        assert strategy._grid_center == Decimal("55000")
        assert strategy._grid_center != old_center
        assert strategy._rebalance_count == 1


# ---------------------------------------------------------------------------
# Backtest compatibility
# ---------------------------------------------------------------------------


class TestGridBacktestCompat:
    """Tests for add_position and close_position."""

    def test_add_position(self, strategy: GridSpotStrategy) -> None:
        now = datetime.now(UTC)
        strategy.add_position(
            entry_price=Decimal("49000"),
            entry_time=now,
            amount_btc=Decimal("0.001"),
            position_id=1,
            sell_level=Decimal("49980"),
        )
        assert strategy.open_positions_count == 1
        assert strategy._grid_positions[0].entry_price == Decimal("49000")
        assert strategy._grid_positions[0].sell_level == Decimal("49980")

    def test_close_position_returns_profit(self, strategy: GridSpotStrategy) -> None:
        now = datetime.now(UTC)
        strategy.add_position(
            entry_price=Decimal("49000"),
            entry_time=now,
            amount_btc=Decimal("0.001"),
            position_id=1,
            sell_level=Decimal("49980"),
        )
        profit = strategy.close_position(
            position_id=1,
            sell_price=Decimal("49980"),
            fee=Decimal("0.05"),
        )
        assert profit > Decimal("0")
        assert strategy.open_positions_count == 0
        assert strategy._completed_pairs == 1

    def test_close_unknown_position(self, strategy: GridSpotStrategy) -> None:
        profit = strategy.close_position(
            position_id=999,
            sell_price=Decimal("50000"),
            fee=Decimal("0.01"),
        )
        assert profit == Decimal("0")

    def test_open_positions_returns_copy(self, strategy: GridSpotStrategy) -> None:
        now = datetime.now(UTC)
        strategy.add_position(
            entry_price=Decimal("49000"),
            entry_time=now,
            amount_btc=Decimal("0.001"),
            position_id=1,
            sell_level=Decimal("49980"),
        )
        positions = strategy.open_positions
        positions.clear()
        assert strategy.open_positions_count == 1


# ---------------------------------------------------------------------------
# Min profit on paired sell
# ---------------------------------------------------------------------------


class TestGridMinProfit:
    """Tests for minimum profit check on paired sell orders."""

    @pytest.mark.asyncio
    async def test_sell_level_respects_min_profit(self) -> None:
        """When spacing is tiny, sell level is bumped to min profitable."""
        settings = Settings(
            app_name="KrakenBot-Test",
            environment="testing",
            log_level=LogLevel.DEBUG,
            log_json=False,
            kraken=KrakenSettings(api_key="test_key", api_secret="test_secret"),
            database=DatabaseSettings(
                url="postgresql+asyncpg://test:test@localhost:5432/test",
                echo=False,
                pool_size=2,
                max_overflow=2,
            ),
            risk=RiskManagementSettings(
                max_position_pct=5.0,
                daily_loss_limit_eur=50.0,
                max_open_positions=10,
                min_trade_interval_sec=60,
                emergency_stop_loss_pct=10.0,
            ),
            trading=TradingSettings(
                mode=TradingMode.PAPER,
                pair="XBT/USDC",
                default_order_amount_eur=15.0,
                candle_interval_min=5,
            ),
            strategy=StrategySettings(
                name="grid_spot",
                buy_threshold_pct=-1.0,
                sell_threshold_pct=2.0,
                lookback_periods=5,
                max_holding_minutes=120,
            ),
            multi_strategy=MultiStrategySettings(enabled=False),
            multi_timeframe=MultiTimeframeSettings(trigger_timeframe=5),
            order=OrderSettings(limit_buy_offset_pct=0.05),
        )
        bus = AsyncMock()
        bus.subscribe = AsyncMock()
        bus.unsubscribe = AsyncMock()
        bus.publish = AsyncMock()
        db = MagicMock()

        # Very small spacing: 0.1% (below 0.64% threshold)
        s = GridSpotStrategy(
            settings,
            bus,
            db,
            strategy_params={
                "grid_levels": 10,
                "grid_spacing_pct": 0.1,
                "range_size_pct": 20.0,
                "rebalance_threshold_pct": 5.0,
                "order_amount_usdc": 30,
            },
        )
        s._skip_db_sync = True
        s._current_timestamp = datetime.now(UTC)

        await s.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("50000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=None,
        )

        pos = s._grid_positions[0]
        # Min profitable = 50000 * 1.0064 = 50320
        # Normal spacing would give 50000 * 1.001 = 50050 (too low)
        assert pos.sell_level >= Decimal("50320")

    @pytest.mark.asyncio
    async def test_sell_level_unchanged_when_spacing_sufficient(
        self, strategy: GridSpotStrategy
    ) -> None:
        """When spacing (2%) is above min profit, sell level is unchanged."""
        strategy._current_timestamp = datetime.now(UTC)
        await strategy.on_trade_filled(
            trade_id="T1",
            pair="XBT/USDC",
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("50000"),
            fee=Decimal("0.05"),
            reference_price=None,
            position_id=None,
        )

        pos = strategy._grid_positions[0]
        # Normal spacing: 50000 * 1.02 = 51000 (well above min)
        expected_sell = Decimal("51000.0")
        assert pos.sell_level == expected_sell


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestGridProperties:
    """Tests for grid property accessors."""

    def test_pending_orders(self, strategy: GridSpotStrategy) -> None:
        strategy.initialize_grid(Decimal("50000"))
        pending = strategy.pending_orders
        assert len(pending) > 0
        for o in pending:
            assert o.status == "pending"

    def test_pending_buy_orders_sorted(self, strategy: GridSpotStrategy) -> None:
        strategy.initialize_grid(Decimal("50000"))
        buys = strategy.pending_buy_orders
        assert len(buys) > 0
        # Should be sorted descending
        for i in range(len(buys) - 1):
            assert buys[i].price >= buys[i + 1].price

    def test_pending_sell_orders_sorted(self, strategy: GridSpotStrategy) -> None:
        strategy.initialize_grid(Decimal("50000"))
        sells = strategy.pending_sell_orders
        assert len(sells) > 0
        # Should be sorted ascending
        for i in range(len(sells) - 1):
            assert sells[i].price <= sells[i + 1].price

    def test_grid_profit_initially_zero(self, strategy: GridSpotStrategy) -> None:
        assert strategy.grid_profit == Decimal("0")

    def test_completed_pairs_initially_zero(self, strategy: GridSpotStrategy) -> None:
        assert strategy.completed_pairs == 0

    def test_grid_efficiency_zero_when_no_orders(self, strategy: GridSpotStrategy) -> None:
        assert strategy.grid_efficiency == 0.0
