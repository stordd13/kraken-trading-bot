"""Tests for margin order functionality in KrakenRestClient.

This module tests:
- Paper margin SELL opens short, locks collateral
- Paper margin BUY closes short, releases collateral + PnL
- Insufficient margin rejected
- No matching position to close raises error
- Margin balance and position helpers
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.kraken.rest import KrakenRestClient
from krakenbot.core.event_bus import EventBus, reset_event_bus
from krakenbot.core.exceptions import InsufficientBalanceError, OrderExecutionError
from krakenbot.models.base import TradeSide


@pytest.fixture
def mock_paper_settings() -> Settings:
    """Create mock settings for paper trading."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="XBT/USDC",
        ),
    )


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for testing."""
    reset_event_bus()
    return EventBus()


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager with async session context manager."""
    manager = MagicMock()

    # Create async context manager mock for session
    session_mock = MagicMock()
    session_mock.add = MagicMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_mock)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    manager.session.return_value = session_cm

    return manager


@pytest.fixture
def paper_client(
    mock_paper_settings: Settings,
    event_bus: EventBus,
    mock_db_manager: MagicMock,
) -> KrakenRestClient:
    """Create a REST client in paper mode."""
    with patch("ccxt.async_support.kraken"):
        client = KrakenRestClient(mock_paper_settings, event_bus, mock_db_manager)
        # Set a known price for paper trading
        client.update_last_price("XBT/USDC", Decimal("42000"))
        return client


class TestPaperMarginSell:
    """Tests for opening short positions via paper margin SELL."""

    @pytest.mark.asyncio
    async def test_sell_opens_short(self, paper_client: KrakenRestClient) -> None:
        """Test that SELL in paper mode opens a short and locks margin."""
        initial_used = paper_client._paper_margin_used

        trade = await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.SELL,
            amount=Decimal("0.01"),
            strategy="margin_test",
            leverage=2,
        )

        assert trade is not None
        assert trade.side == TradeSide.SELL
        assert trade.trading_mode == "margin"
        assert trade.order_id.startswith("paper-margin-")

        # Margin should be locked: (0.01 * 42000) / 2 = 210
        expected_margin = (Decimal("0.01") * Decimal("42000")) / 2
        assert paper_client._paper_margin_used == initial_used + expected_margin
        assert len(paper_client._paper_margin_positions) == 1

    @pytest.mark.asyncio
    async def test_sell_locks_correct_collateral(self, paper_client: KrakenRestClient) -> None:
        """Test that margin collateral is calculated correctly with leverage."""
        await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.SELL,
            amount=Decimal("0.005"),
            strategy="margin_test",
            leverage=2,
        )

        # Collateral = (0.005 * 42000) / 2 = 105
        expected_collateral = Decimal("105")
        assert paper_client._paper_margin_used == expected_collateral

    @pytest.mark.asyncio
    async def test_sell_rejected_insufficient_margin(self, paper_client: KrakenRestClient) -> None:
        """Test that SELL is rejected when margin is insufficient."""
        # Default paper margin balance is 500, try to short too much
        # 0.1 BTC * 42000 / 2 = 2100 > 500
        with pytest.raises(InsufficientBalanceError):
            await paper_client.place_margin_order(
                pair="XBT/USDC",
                side=TradeSide.SELL,
                amount=Decimal("0.1"),
                strategy="margin_test",
                leverage=2,
            )


class TestPaperMarginBuy:
    """Tests for closing short positions via paper margin BUY."""

    @pytest.mark.asyncio
    async def test_buy_closes_short(self, paper_client: KrakenRestClient) -> None:
        """Test that BUY closes an existing short position."""
        # Open short first
        await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.SELL,
            amount=Decimal("0.01"),
            strategy="margin_test",
            leverage=2,
        )
        assert len(paper_client._paper_margin_positions) == 1

        # Close short (price drops)
        paper_client.update_last_price("XBT/USDC", Decimal("41000"))
        trade = await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.01"),
            strategy="margin_test",
            leverage=2,
        )

        assert trade is not None
        assert trade.side == TradeSide.BUY
        assert trade.trading_mode == "margin"
        assert len(paper_client._paper_margin_positions) == 0
        assert paper_client._paper_margin_used == Decimal("0")

    @pytest.mark.asyncio
    async def test_buy_applies_pnl_profit(self, paper_client: KrakenRestClient) -> None:
        """Test that PnL is correctly applied on profitable close."""
        initial_balance = paper_client._paper_margin_balance

        # Open short at 42000
        await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.SELL,
            amount=Decimal("0.01"),
            strategy="margin_test",
            leverage=2,
        )

        # Close at 41000 (profit: entry - exit = 1000 per BTC)
        paper_client.update_last_price("XBT/USDC", Decimal("41000"))
        await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.01"),
            strategy="margin_test",
            leverage=2,
        )

        # PnL = (42000 - 41000) * 0.01 - fee
        # fee = 0.01 * 41000 * 0.0026 = 1.066
        pnl = (Decimal("42000") - Decimal("41000")) * Decimal("0.01")
        fee = Decimal("0.01") * Decimal("41000") * Decimal("0.0026")
        expected_balance = initial_balance + pnl - fee
        assert paper_client._paper_margin_balance == expected_balance

    @pytest.mark.asyncio
    async def test_buy_no_matching_position_raises(self, paper_client: KrakenRestClient) -> None:
        """Test that BUY without a matching position raises error."""
        with pytest.raises(OrderExecutionError, match="No matching margin position"):
            await paper_client.place_margin_order(
                pair="XBT/USDC",
                side=TradeSide.BUY,
                amount=Decimal("0.01"),
                strategy="margin_test",
                leverage=2,
            )


class TestMarginBalanceHelpers:
    """Tests for margin balance and position helper methods."""

    @pytest.mark.asyncio
    async def test_get_margin_balance_initial(self, paper_client: KrakenRestClient) -> None:
        """Test initial margin balance values."""
        balance = await paper_client.get_margin_balance()

        assert balance["total_margin"] == Decimal("500.00")
        assert balance["used_margin"] == Decimal("0")
        assert balance["available_margin"] == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_get_margin_balance_after_open(self, paper_client: KrakenRestClient) -> None:
        """Test margin balance reflects locked collateral."""
        await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.SELL,
            amount=Decimal("0.01"),
            strategy="margin_test",
            leverage=2,
        )

        balance = await paper_client.get_margin_balance()

        expected_used = (Decimal("0.01") * Decimal("42000")) / 2
        assert balance["used_margin"] == expected_used
        assert balance["available_margin"] == balance["total_margin"] - expected_used

    @pytest.mark.asyncio
    async def test_get_open_margin_positions_empty(self, paper_client: KrakenRestClient) -> None:
        """Test no open positions initially."""
        positions = await paper_client.get_open_margin_positions()

        assert positions == []

    @pytest.mark.asyncio
    async def test_get_open_margin_positions_after_short(
        self, paper_client: KrakenRestClient
    ) -> None:
        """Test open positions list after opening a short."""
        await paper_client.place_margin_order(
            pair="XBT/USDC",
            side=TradeSide.SELL,
            amount=Decimal("0.01"),
            strategy="margin_test",
            leverage=2,
        )

        positions = await paper_client.get_open_margin_positions()

        assert len(positions) == 1
        assert positions[0]["pair"] == "XBT/USDC"
        assert positions[0]["amount"] == Decimal("0.01")
        assert positions[0]["strategy"] == "margin_test"
