"""Tests for the RiskManager module.

This module tests all risk management functionality including:
- Balance validation
- Position size limits
- Daily loss limits
- Maximum open positions
- Trade interval checks
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.execution.risk import RiskCheckResult, RiskManager
from krakenbot.models.base import TradeSide, TradeStatus


# =============================================================================
# RiskCheckResult Tests
# =============================================================================


class TestRiskCheckResult:
    """Tests for the RiskCheckResult dataclass."""

    def test_init_approved(self) -> None:
        """Test creating an approved result."""
        result = RiskCheckResult(approved=True)

        assert result.approved is True
        assert result.rejected is False
        assert result.reasons == []

    def test_init_rejected(self) -> None:
        """Test creating a rejected result."""
        result = RiskCheckResult(approved=False, reasons=["Insufficient balance"])

        assert result.approved is False
        assert result.rejected is True
        assert "Insufficient balance" in result.reasons

    def test_add_reason_marks_rejected(self) -> None:
        """Test that adding a reason marks the result as rejected."""
        result = RiskCheckResult(approved=True)
        assert result.approved is True

        result.add_reason("Daily loss limit exceeded")

        assert result.approved is False
        assert result.rejected is True
        assert "Daily loss limit exceeded" in result.reasons

    def test_add_multiple_reasons(self) -> None:
        """Test adding multiple rejection reasons."""
        result = RiskCheckResult(approved=True)

        result.add_reason("Reason 1")
        result.add_reason("Reason 2")
        result.add_reason("Reason 3")

        assert len(result.reasons) == 3
        assert "Reason 1" in result.reasons
        assert "Reason 2" in result.reasons
        assert "Reason 3" in result.reasons

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        result = RiskCheckResult(approved=False, reasons=["Test reason"])

        result_dict = result.to_dict()

        assert result_dict["approved"] is False
        assert "Test reason" in result_dict["reasons"]


# =============================================================================
# RiskManager Tests
# =============================================================================


class TestRiskManager:
    """Tests for the RiskManager class."""

    @pytest.fixture
    def risk_manager(self, mock_settings: MagicMock) -> RiskManager:
        """Create a RiskManager instance for testing."""
        mock_db_manager = MagicMock()
        mock_db_manager.read_session = AsyncMock()
        return RiskManager(mock_settings, mock_db_manager)

    # -------------------------------------------------------------------------
    # Balance Check Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_balance_sufficient_for_buy(
        self, risk_manager: RiskManager
    ) -> None:
        """Test balance check passes with sufficient EUR for buy."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("1000.00"), "XBT": Decimal("0.0")}

        await risk_manager._check_balance(
            result=result,
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.01"),
            price=Decimal("42000"),
            balance=balance,
        )

        assert result.approved is True
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_check_balance_insufficient_for_buy(
        self, risk_manager: RiskManager
    ) -> None:
        """Test balance check fails with insufficient EUR for buy."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("100.00"), "XBT": Decimal("0.0")}

        await risk_manager._check_balance(
            result=result,
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.01"),
            price=Decimal("42000"),  # Requires 420 EUR
            balance=balance,
        )

        assert result.rejected is True
        assert any("Insufficient balance" in reason for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_check_balance_sufficient_for_sell(
        self, risk_manager: RiskManager
    ) -> None:
        """Test balance check passes with sufficient XBT for sell."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("0.0"), "XBT": Decimal("0.05")}

        await risk_manager._check_balance(
            result=result,
            pair="XBT/EUR",
            side=TradeSide.SELL,
            amount=Decimal("0.01"),
            price=Decimal("42000"),
            balance=balance,
        )

        assert result.approved is True
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_check_balance_insufficient_for_sell(
        self, risk_manager: RiskManager
    ) -> None:
        """Test balance check fails with insufficient XBT for sell."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("1000.00"), "XBT": Decimal("0.001")}

        await risk_manager._check_balance(
            result=result,
            pair="XBT/EUR",
            side=TradeSide.SELL,
            amount=Decimal("0.01"),  # Requires 0.01 XBT
            price=Decimal("42000"),
            balance=balance,
        )

        assert result.rejected is True
        assert any("Insufficient XBT" in reason for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_check_balance_missing_currency(
        self, risk_manager: RiskManager
    ) -> None:
        """Test balance check fails when currency is not in balance dict."""
        result = RiskCheckResult(approved=True)
        balance = {"USD": Decimal("1000.00")}  # No EUR

        await risk_manager._check_balance(
            result=result,
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.01"),
            price=Decimal("42000"),
            balance=balance,
        )

        assert result.rejected is True
        assert any("Insufficient balance" in reason for reason in result.reasons)

    # -------------------------------------------------------------------------
    # Position Size Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_position_size_within_limit(
        self, risk_manager: RiskManager
    ) -> None:
        """Test position size check passes when within limits."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("10000.00")}

        await risk_manager._check_position_size(
            result=result,
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),  # Order value: 42 EUR = 0.42% of 10000
            balance=balance,
        )

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_check_position_size_exceeds_limit(
        self, risk_manager: RiskManager
    ) -> None:
        """Test position size check fails when exceeding limit."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("1000.00")}

        await risk_manager._check_position_size(
            result=result,
            side=TradeSide.BUY,
            amount=Decimal("0.01"),
            price=Decimal("42000"),  # Order value: 420 EUR = 42% of 1000
            balance=balance,
        )

        assert result.rejected is True
        assert any("Position size too large" in reason for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_check_position_size_zero_portfolio(
        self, risk_manager: RiskManager
    ) -> None:
        """Test position size check fails with zero portfolio value."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("0")}

        await risk_manager._check_position_size(
            result=result,
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            balance=balance,
        )

        assert result.rejected is True
        assert any("zero or negative" in reason for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_check_position_size_skipped_for_sell(
        self, risk_manager: RiskManager
    ) -> None:
        """Test position size check is skipped for sell orders."""
        result = RiskCheckResult(approved=True)
        balance = {"EUR": Decimal("1000.00")}

        # Even with a very large sell that would fail for buy, sell should pass
        await risk_manager._check_position_size(
            result=result,
            side=TradeSide.SELL,
            amount=Decimal("0.1"),
            price=Decimal("42000"),  # Order value: 4200 EUR = 420% of 1000
            balance=balance,
        )

        assert result.approved is True

    # -------------------------------------------------------------------------
    # Daily Loss Limit Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_daily_loss_limit_ok(
        self, risk_manager: RiskManager
    ) -> None:
        """Test daily loss check passes when within limit."""
        result = RiskCheckResult(approved=True)

        with patch.object(
            risk_manager, "_get_daily_pnl", return_value=Decimal("-10.00")
        ):
            await risk_manager._check_daily_loss_limit(result)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_check_daily_loss_limit_exceeded(
        self, risk_manager: RiskManager
    ) -> None:
        """Test daily loss check fails when limit exceeded."""
        result = RiskCheckResult(approved=True)

        # Default limit is 50 EUR
        with patch.object(
            risk_manager, "_get_daily_pnl", return_value=Decimal("-60.00")
        ):
            await risk_manager._check_daily_loss_limit(result)

        assert result.rejected is True
        assert any("Daily loss limit" in reason for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_check_daily_loss_limit_exactly_at_limit(
        self, risk_manager: RiskManager
    ) -> None:
        """Test daily loss check fails when exactly at limit."""
        result = RiskCheckResult(approved=True)

        with patch.object(
            risk_manager, "_get_daily_pnl", return_value=Decimal("-50.00")
        ):
            await risk_manager._check_daily_loss_limit(result)

        assert result.rejected is True

    @pytest.mark.asyncio
    async def test_check_daily_loss_limit_positive_pnl(
        self, risk_manager: RiskManager
    ) -> None:
        """Test daily loss check passes with positive P&L."""
        result = RiskCheckResult(approved=True)

        with patch.object(
            risk_manager, "_get_daily_pnl", return_value=Decimal("100.00")
        ):
            await risk_manager._check_daily_loss_limit(result)

        assert result.approved is True

    # -------------------------------------------------------------------------
    # Max Open Positions Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_max_open_positions_ok(
        self, risk_manager: RiskManager
    ) -> None:
        """Test max positions check passes when under limit."""
        result = RiskCheckResult(approved=True)

        with patch.object(risk_manager, "_get_open_positions_count", return_value=1):
            await risk_manager._check_max_open_positions(result, TradeSide.BUY)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_check_max_open_positions_at_limit(
        self, risk_manager: RiskManager
    ) -> None:
        """Test max positions check fails at limit."""
        result = RiskCheckResult(approved=True)

        # Default limit is 3
        with patch.object(risk_manager, "_get_open_positions_count", return_value=3):
            await risk_manager._check_max_open_positions(result, TradeSide.BUY)

        assert result.rejected is True
        assert any("Max open positions" in reason for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_check_max_open_positions_exceeds_limit(
        self, risk_manager: RiskManager
    ) -> None:
        """Test max positions check fails when exceeding limit."""
        result = RiskCheckResult(approved=True)

        with patch.object(risk_manager, "_get_open_positions_count", return_value=5):
            await risk_manager._check_max_open_positions(result, TradeSide.BUY)

        assert result.rejected is True

    @pytest.mark.asyncio
    async def test_check_max_open_positions_sell_allowed(
        self, risk_manager: RiskManager
    ) -> None:
        """Test max positions check is skipped for sell orders."""
        result = RiskCheckResult(approved=True)

        # Even with many positions, sell should be allowed
        with patch.object(risk_manager, "_get_open_positions_count", return_value=10):
            await risk_manager._check_max_open_positions(result, TradeSide.SELL)

        assert result.approved is True

    # -------------------------------------------------------------------------
    # Trade Interval Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_trade_interval_ok(
        self, risk_manager: RiskManager
    ) -> None:
        """Test trade interval check passes when enough time has elapsed."""
        result = RiskCheckResult(approved=True)
        last_trade = datetime.now(timezone.utc) - timedelta(seconds=120)

        with patch.object(
            risk_manager, "_get_last_trade_time", return_value=last_trade
        ):
            await risk_manager._check_trade_interval(result)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_check_trade_interval_too_soon(
        self, risk_manager: RiskManager
    ) -> None:
        """Test trade interval check fails when trading too soon."""
        result = RiskCheckResult(approved=True)
        last_trade = datetime.now(timezone.utc) - timedelta(seconds=30)

        with patch.object(
            risk_manager, "_get_last_trade_time", return_value=last_trade
        ):
            await risk_manager._check_trade_interval(result)

        assert result.rejected is True
        assert any("Trade too soon" in reason for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_check_trade_interval_no_previous_trade(
        self, risk_manager: RiskManager
    ) -> None:
        """Test trade interval check passes with no previous trades."""
        result = RiskCheckResult(approved=True)

        with patch.object(risk_manager, "_get_last_trade_time", return_value=None):
            await risk_manager._check_trade_interval(result)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_check_trade_interval_exactly_at_minimum(
        self, risk_manager: RiskManager
    ) -> None:
        """Test trade interval check passes when exactly at minimum."""
        result = RiskCheckResult(approved=True)
        # Default minimum is 60 seconds
        last_trade = datetime.now(timezone.utc) - timedelta(seconds=60)

        with patch.object(
            risk_manager, "_get_last_trade_time", return_value=last_trade
        ):
            await risk_manager._check_trade_interval(result)

        assert result.approved is True

    # -------------------------------------------------------------------------
    # Full Order Check Integration Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_order_all_checks_pass(
        self, risk_manager: RiskManager
    ) -> None:
        """Test full order validation when all checks pass."""
        balance = {"EUR": Decimal("10000.00"), "XBT": Decimal("0.0")}

        with (
            patch.object(
                risk_manager, "_get_daily_pnl", return_value=Decimal("0")
            ),
            patch.object(risk_manager, "_get_open_positions_count", return_value=0),
            patch.object(risk_manager, "_get_last_trade_time", return_value=None),
        ):
            result = await risk_manager.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance=balance,
            )

        assert result.approved is True
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_check_order_multiple_failures(
        self, risk_manager: RiskManager
    ) -> None:
        """Test full order validation collects multiple failure reasons."""
        balance = {"EUR": Decimal("100.00")}  # Insufficient balance
        last_trade = datetime.now(timezone.utc) - timedelta(seconds=10)  # Too soon

        with (
            patch.object(
                risk_manager, "_get_daily_pnl", return_value=Decimal("-60")
            ),
            patch.object(risk_manager, "_get_open_positions_count", return_value=5),
            patch.object(
                risk_manager, "_get_last_trade_time", return_value=last_trade
            ),
        ):
            result = await risk_manager.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.1"),
                price=Decimal("42000"),  # 4200 EUR required
                balance=balance,
            )

        assert result.rejected is True
        # Should have multiple reasons
        assert len(result.reasons) >= 3

    @pytest.mark.asyncio
    async def test_check_order_sell_with_position(
        self, risk_manager: RiskManager
    ) -> None:
        """Test sell order validation with existing position."""
        balance = {"EUR": Decimal("1000.00"), "XBT": Decimal("0.01")}

        with (
            patch.object(
                risk_manager, "_get_daily_pnl", return_value=Decimal("0")
            ),
            patch.object(risk_manager, "_get_open_positions_count", return_value=1),
            patch.object(risk_manager, "_get_last_trade_time", return_value=None),
        ):
            result = await risk_manager.check_order(
                pair="XBT/EUR",
                side=TradeSide.SELL,
                amount=Decimal("0.01"),
                price=Decimal("42000"),
                balance=balance,
            )

        assert result.approved is True

    # -------------------------------------------------------------------------
    # Emergency Stop Loss Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_emergency_stop_loss_not_triggered(
        self, risk_manager: RiskManager
    ) -> None:
        """Test emergency stop loss not triggered with small loss."""
        entry_price = Decimal("42000")
        current_price = Decimal("41000")  # ~2.4% loss

        triggered = await risk_manager.check_emergency_stop_loss(
            entry_price, current_price
        )

        assert triggered is False

    @pytest.mark.asyncio
    async def test_emergency_stop_loss_triggered(
        self, risk_manager: RiskManager
    ) -> None:
        """Test emergency stop loss triggered with large loss."""
        entry_price = Decimal("42000")
        current_price = Decimal("37000")  # ~11.9% loss (> 10% default)

        triggered = await risk_manager.check_emergency_stop_loss(
            entry_price, current_price
        )

        assert triggered is True

    @pytest.mark.asyncio
    async def test_emergency_stop_loss_zero_entry_price(
        self, risk_manager: RiskManager
    ) -> None:
        """Test emergency stop loss returns False with zero entry price."""
        triggered = await risk_manager.check_emergency_stop_loss(
            Decimal("0"), Decimal("42000")
        )

        assert triggered is False

    # -------------------------------------------------------------------------
    # Helper Method Tests
    # -------------------------------------------------------------------------

    def test_get_risk_summary(self, risk_manager: RiskManager) -> None:
        """Test getting risk configuration summary."""
        summary = risk_manager.get_risk_summary()

        assert "max_position_pct" in summary
        assert "daily_loss_limit_eur" in summary
        assert "max_open_positions" in summary
        assert "min_trade_interval_sec" in summary
        assert "emergency_stop_loss_pct" in summary
        assert summary["max_position_pct"] == 5.0
        assert summary["daily_loss_limit_eur"] == 50.0
        assert summary["max_open_positions"] == 3
