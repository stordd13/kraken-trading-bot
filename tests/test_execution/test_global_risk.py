"""Tests for the GlobalRiskManager module.

This module tests the two-level risk management functionality including:
- Legacy mode delegation (multi_strategy_settings=None)
- Strategy registration with per-strategy budgets
- Global-level checks (balance, total positions, daily loss)
- Per-strategy checks (positions, daily loss per strategy)
- Global limits blocking all strategies
- Per-strategy limits blocking only the affected strategy
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import MultiStrategySettings, StrategyBudget
from krakenbot.execution.risk import GlobalRiskManager, RiskCheckResult
from krakenbot.models.base import TradeSide


# =============================================================================
# Helpers
# =============================================================================


def _make_db_manager(
    open_positions_count: int = 0,
    daily_pnl: Decimal = Decimal("0"),
    exposure_value: Decimal = Decimal("0"),
) -> MagicMock:
    """Create a mock DatabaseManager whose read_session returns predictable scalars.

    The mock session.execute() returns different scalars depending on call order:
    We use side_effect so each call to execute() returns the next value.
    However, GlobalRiskManager issues multiple independent queries within
    a single check_order call, so we provide a callable side_effect.
    """
    mock_result = MagicMock()
    # Default scalar value; individual tests override as needed
    mock_result.scalar.return_value = open_positions_count

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    db_manager = MagicMock()
    db_manager.read_session = MagicMock()
    db_manager.read_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    db_manager.read_session.return_value.__aexit__ = AsyncMock(return_value=False)

    return db_manager


def _make_multi_settings(
    enabled: bool = True,
    global_max_open_positions: int = 10,
    global_daily_loss_limit_eur: float = 50.0,
    global_max_portfolio_exposure_pct: float = 30.0,
) -> MultiStrategySettings:
    """Create a MultiStrategySettings instance for testing."""
    return MultiStrategySettings(
        enabled=enabled,
        strategies=[],
        global_max_open_positions=global_max_open_positions,
        global_daily_loss_limit_eur=global_daily_loss_limit_eur,
        global_max_portfolio_exposure_pct=global_max_portfolio_exposure_pct,
    )


# =============================================================================
# Legacy Mode Tests (multi_strategy_settings=None)
# =============================================================================


class TestGlobalRiskManagerLegacyMode:
    """Tests for GlobalRiskManager in legacy mode (multi_strategy disabled)."""

    @pytest.fixture
    def grm_legacy(self, mock_settings: MagicMock) -> GlobalRiskManager:
        """Create a GlobalRiskManager in legacy mode (no multi_strategy_settings)."""
        db_manager = _make_db_manager()
        return GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=None)

    def test_legacy_mode_multi_enabled_is_false(
        self, grm_legacy: GlobalRiskManager
    ) -> None:
        """Legacy mode should have _multi_enabled=False."""
        assert grm_legacy._multi_enabled is False

    @pytest.mark.asyncio
    async def test_legacy_mode_delegates_to_inner_risk_manager(
        self, grm_legacy: GlobalRiskManager
    ) -> None:
        """In legacy mode, check_order should delegate to the legacy RiskManager."""
        expected_result = RiskCheckResult(approved=True)

        with patch.object(
            grm_legacy._legacy_risk_manager,
            "check_order",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_check:
            result = await grm_legacy.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
            )

        mock_check.assert_awaited_once_with(
            "XBT/EUR",
            TradeSide.BUY,
            Decimal("0.001"),
            Decimal("42000"),
            {"EUR": Decimal("10000")},
        )
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_legacy_mode_sets_bot_id_when_provided(
        self, grm_legacy: GlobalRiskManager
    ) -> None:
        """In legacy mode, bot_id should be forwarded to the inner RiskManager."""
        expected_result = RiskCheckResult(approved=True)

        with (
            patch.object(
                grm_legacy._legacy_risk_manager,
                "set_bot_id",
            ) as mock_set_bot_id,
            patch.object(
                grm_legacy._legacy_risk_manager,
                "check_order",
                new_callable=AsyncMock,
                return_value=expected_result,
            ),
        ):
            await grm_legacy.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-threshold-001",
            )

        mock_set_bot_id.assert_called_once_with("bot-threshold-001")

    @pytest.mark.asyncio
    async def test_legacy_mode_disabled_multi_settings(
        self, mock_settings: MagicMock
    ) -> None:
        """MultiStrategySettings with enabled=False should behave like legacy."""
        db_manager = _make_db_manager()
        ms = _make_multi_settings(enabled=False)
        grm = GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=ms)

        assert grm._multi_enabled is False

        expected_result = RiskCheckResult(approved=True)
        with patch.object(
            grm._legacy_risk_manager,
            "check_order",
            new_callable=AsyncMock,
            return_value=expected_result,
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
            )

        assert result.approved is True


# =============================================================================
# Strategy Registration Tests
# =============================================================================


class TestRegisterStrategy:
    """Tests for GlobalRiskManager.register_strategy()."""

    @pytest.fixture
    def grm(self, mock_settings: MagicMock) -> GlobalRiskManager:
        """Create a GlobalRiskManager in multi-strategy mode."""
        db_manager = _make_db_manager()
        ms = _make_multi_settings(enabled=True)
        return GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=ms)

    def test_register_strategy_stores_budget(self, grm: GlobalRiskManager) -> None:
        """register_strategy should store the budget keyed by bot_id."""
        budget = StrategyBudget(
            max_open_positions=2,
            daily_loss_limit_eur=20.0,
            max_position_pct=3.0,
            position_size_multiplier=1.5,
        )

        grm.register_strategy("bot-aggressive-001", budget)

        assert "bot-aggressive-001" in grm._budgets
        assert grm._budgets["bot-aggressive-001"] is budget

    def test_register_strategy_creates_risk_manager(
        self, grm: GlobalRiskManager
    ) -> None:
        """register_strategy should create a per-strategy RiskManager with correct limits."""
        budget = StrategyBudget(
            max_open_positions=2,
            daily_loss_limit_eur=20.0,
            max_position_pct=3.0,
            position_size_multiplier=1.5,
        )

        grm.register_strategy("bot-aggressive-001", budget)

        assert "bot-aggressive-001" in grm._strategy_risk_managers
        rm = grm._strategy_risk_managers["bot-aggressive-001"]
        assert rm.bot_id == "bot-aggressive-001"
        assert rm.max_open_positions == 2
        assert rm.daily_loss_limit == Decimal("20.0")
        assert rm.max_position_pct == 3.0

    def test_register_multiple_strategies(self, grm: GlobalRiskManager) -> None:
        """Multiple strategies can be registered independently."""
        budget_a = StrategyBudget(max_open_positions=2, daily_loss_limit_eur=20.0)
        budget_b = StrategyBudget(max_open_positions=5, daily_loss_limit_eur=40.0)

        grm.register_strategy("bot-a", budget_a)
        grm.register_strategy("bot-b", budget_b)

        assert len(grm._budgets) == 2
        assert len(grm._strategy_risk_managers) == 2
        assert grm._strategy_risk_managers["bot-a"].max_open_positions == 2
        assert grm._strategy_risk_managers["bot-b"].max_open_positions == 5

    def test_get_risk_summary_includes_registered_strategies(
        self, grm: GlobalRiskManager
    ) -> None:
        """get_risk_summary should include registered strategy budgets."""
        budget = StrategyBudget(
            max_open_positions=2,
            daily_loss_limit_eur=20.0,
            max_position_pct=3.0,
            position_size_multiplier=1.5,
        )
        grm.register_strategy("bot-test", budget)

        summary = grm.get_risk_summary()

        assert summary["multi_strategy_enabled"] is True
        assert "bot-test" in summary["registered_strategies"]
        assert summary["budget_bot-test"]["max_positions"] == 2
        assert summary["budget_bot-test"]["daily_loss_limit"] == 20.0


# =============================================================================
# Global-Level Check Tests (multi-strategy enabled)
# =============================================================================


class TestGlobalLevelChecks:
    """Tests for global-level risk checks in multi-strategy mode."""

    @pytest.fixture
    def grm(self, mock_settings: MagicMock) -> GlobalRiskManager:
        """Create a GlobalRiskManager in multi-strategy mode."""
        db_manager = _make_db_manager()
        ms = _make_multi_settings(
            enabled=True,
            global_max_open_positions=5,
            global_daily_loss_limit_eur=100.0,
            global_max_portfolio_exposure_pct=30.0,
        )
        return GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=ms)

    @pytest.mark.asyncio
    async def test_global_balance_check_insufficient(
        self, grm: GlobalRiskManager
    ) -> None:
        """Global balance check should reject when balance is insufficient."""
        with (
            patch.object(
                grm, "_get_global_open_positions_count", new_callable=AsyncMock, return_value=0
            ),
            patch.object(
                grm, "_get_global_daily_pnl", new_callable=AsyncMock, return_value=Decimal("0")
            ),
            patch.object(
                grm, "_check_global_exposure", new_callable=AsyncMock
            ),
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.01"),
                price=Decimal("42000"),  # Requires 420 EUR
                balance={"EUR": Decimal("100")},  # Only 100 EUR
            )

        assert result.rejected is True
        assert any("Insufficient balance" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_global_max_positions_reached(
        self, grm: GlobalRiskManager
    ) -> None:
        """Global check should reject when total positions >= global max."""
        with (
            patch.object(
                grm, "_get_global_open_positions_count",
                new_callable=AsyncMock,
                return_value=5,  # == global_max_open_positions
            ),
            patch.object(
                grm, "_get_global_daily_pnl", new_callable=AsyncMock, return_value=Decimal("0")
            ),
            patch.object(
                grm, "_check_global_exposure", new_callable=AsyncMock
            ),
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
            )

        assert result.rejected is True
        assert any("Global max positions" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_global_max_positions_under_limit(
        self, grm: GlobalRiskManager
    ) -> None:
        """Global check should pass when total positions < global max."""
        with (
            patch.object(
                grm, "_get_global_open_positions_count",
                new_callable=AsyncMock,
                return_value=2,
            ),
            patch.object(
                grm, "_get_global_daily_pnl", new_callable=AsyncMock, return_value=Decimal("0")
            ),
            patch.object(
                grm, "_check_global_exposure", new_callable=AsyncMock
            ),
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
            )

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_global_daily_loss_limit_reached(
        self, grm: GlobalRiskManager
    ) -> None:
        """Global check should reject when daily loss >= global limit."""
        with (
            patch.object(
                grm, "_get_global_open_positions_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch.object(
                grm, "_get_global_daily_pnl",
                new_callable=AsyncMock,
                return_value=Decimal("-100"),  # == -global_daily_loss_limit_eur
            ),
            patch.object(
                grm, "_check_global_exposure", new_callable=AsyncMock
            ),
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
            )

        assert result.rejected is True
        assert any("Global daily loss limit" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_global_daily_loss_within_limit(
        self, grm: GlobalRiskManager
    ) -> None:
        """Global check should pass when daily loss is within limit."""
        with (
            patch.object(
                grm, "_get_global_open_positions_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch.object(
                grm, "_get_global_daily_pnl",
                new_callable=AsyncMock,
                return_value=Decimal("-30"),  # Under the 100 limit
            ),
            patch.object(
                grm, "_check_global_exposure", new_callable=AsyncMock
            ),
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
            )

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_global_checks_skipped_for_sell_orders(
        self, grm: GlobalRiskManager
    ) -> None:
        """Sell orders should skip global position/loss checks (only balance checked)."""
        with (
            patch.object(
                grm, "_get_global_open_positions_count",
                new_callable=AsyncMock,
                return_value=100,  # Way over limit
            ),
            patch.object(
                grm, "_get_global_daily_pnl",
                new_callable=AsyncMock,
                return_value=Decimal("-999"),  # Way over limit
            ),
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.SELL,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"BTC": Decimal("1.0")},
            )

        # Sell should pass because position/loss checks only apply to BUY
        assert result.approved is True


# =============================================================================
# Per-Strategy Level Check Tests
# =============================================================================


class TestPerStrategyChecks:
    """Tests for per-strategy risk checks in multi-strategy mode."""

    @pytest.fixture
    def grm_with_strategies(self, mock_settings: MagicMock) -> GlobalRiskManager:
        """Create a GlobalRiskManager with two registered strategies."""
        db_manager = _make_db_manager()
        ms = _make_multi_settings(
            enabled=True,
            global_max_open_positions=10,
            global_daily_loss_limit_eur=100.0,
        )
        grm = GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=ms)

        budget_a = StrategyBudget(
            max_open_positions=2,
            daily_loss_limit_eur=20.0,
            max_position_pct=3.0,
            position_size_multiplier=1.0,
        )
        budget_b = StrategyBudget(
            max_open_positions=5,
            daily_loss_limit_eur=40.0,
            max_position_pct=5.0,
            position_size_multiplier=1.0,
        )
        grm.register_strategy("bot-a", budget_a)
        grm.register_strategy("bot-b", budget_b)
        return grm

    @pytest.mark.asyncio
    async def test_per_strategy_positions_limit_reached(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """Per-strategy check should reject when strategy positions >= budget max."""
        strategy_result = RiskCheckResult(approved=False, reasons=["Max open positions reached: 2 >= 2"])

        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=2,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("0"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm_with_strategies._strategy_risk_managers["bot-a"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_result,
            ),
        ):
            result = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-a",
            )

        assert result.rejected is True
        assert any("[bot-a]" in r for r in result.reasons)
        assert any("Max open positions" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_per_strategy_daily_loss_limit_reached(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """Per-strategy check should reject when strategy daily loss >= budget limit."""
        strategy_result = RiskCheckResult(
            approved=False,
            reasons=["Daily loss limit reached: -20.00 EUR <= -20.00 EUR"],
        )

        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=1,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("-10"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm_with_strategies._strategy_risk_managers["bot-a"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_result,
            ),
        ):
            result = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-a",
            )

        assert result.rejected is True
        assert any("[bot-a]" in r and "Daily loss limit" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_per_strategy_checks_pass_when_within_budget(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """Per-strategy check should pass when within all budget limits."""
        strategy_result = RiskCheckResult(approved=True)

        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=1,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("0"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm_with_strategies._strategy_risk_managers["bot-a"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_result,
            ),
        ):
            result = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-a",
            )

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_unknown_bot_id_skips_per_strategy_checks(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """An unregistered bot_id should skip per-strategy checks (only global checks run)."""
        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=0,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("0"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
        ):
            result = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-unknown",
            )

        assert result.approved is True


# =============================================================================
# Global Limit Blocks All Strategies
# =============================================================================


class TestGlobalLimitBlocksAllStrategies:
    """Tests verifying that global limits block orders from ALL strategies."""

    @pytest.fixture
    def grm_with_strategies(self, mock_settings: MagicMock) -> GlobalRiskManager:
        """Create a GlobalRiskManager with two strategies and tight global limits."""
        db_manager = _make_db_manager()
        ms = _make_multi_settings(
            enabled=True,
            global_max_open_positions=3,
            global_daily_loss_limit_eur=50.0,
        )
        grm = GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=ms)

        budget_a = StrategyBudget(
            max_open_positions=5,
            daily_loss_limit_eur=30.0,
            max_position_pct=5.0,
            position_size_multiplier=1.0,
        )
        budget_b = StrategyBudget(
            max_open_positions=5,
            daily_loss_limit_eur=30.0,
            max_position_pct=5.0,
            position_size_multiplier=1.0,
        )
        grm.register_strategy("bot-a", budget_a)
        grm.register_strategy("bot-b", budget_b)
        return grm

    @pytest.mark.asyncio
    async def test_global_positions_limit_blocks_all_strategies(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """When global positions limit is reached, both strategies should be blocked."""
        strategy_result_ok = RiskCheckResult(approved=True)

        for bot_id in ("bot-a", "bot-b"):
            with (
                patch.object(
                    grm_with_strategies, "_get_global_open_positions_count",
                    new_callable=AsyncMock,
                    return_value=3,  # == global_max_open_positions
                ),
                patch.object(
                    grm_with_strategies, "_get_global_daily_pnl",
                    new_callable=AsyncMock, return_value=Decimal("0"),
                ),
                patch.object(
                    grm_with_strategies, "_check_global_exposure",
                    new_callable=AsyncMock,
                ),
                patch.object(
                    grm_with_strategies._strategy_risk_managers[bot_id],
                    "check_order",
                    new_callable=AsyncMock,
                    return_value=strategy_result_ok,
                ),
            ):
                result = await grm_with_strategies.check_order(
                    pair="XBT/EUR",
                    side=TradeSide.BUY,
                    amount=Decimal("0.001"),
                    price=Decimal("42000"),
                    balance={"EUR": Decimal("10000")},
                    bot_id=bot_id,
                )

            assert result.rejected is True, f"Expected {bot_id} to be blocked by global limit"
            assert any("Global max positions" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_global_daily_loss_blocks_all_strategies(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """When global daily loss limit is reached, both strategies should be blocked."""
        strategy_result_ok = RiskCheckResult(approved=True)

        for bot_id in ("bot-a", "bot-b"):
            with (
                patch.object(
                    grm_with_strategies, "_get_global_open_positions_count",
                    new_callable=AsyncMock, return_value=0,
                ),
                patch.object(
                    grm_with_strategies, "_get_global_daily_pnl",
                    new_callable=AsyncMock,
                    return_value=Decimal("-50"),  # == -global_daily_loss_limit_eur
                ),
                patch.object(
                    grm_with_strategies, "_check_global_exposure",
                    new_callable=AsyncMock,
                ),
                patch.object(
                    grm_with_strategies._strategy_risk_managers[bot_id],
                    "check_order",
                    new_callable=AsyncMock,
                    return_value=strategy_result_ok,
                ),
            ):
                result = await grm_with_strategies.check_order(
                    pair="XBT/EUR",
                    side=TradeSide.BUY,
                    amount=Decimal("0.001"),
                    price=Decimal("42000"),
                    balance={"EUR": Decimal("10000")},
                    bot_id=bot_id,
                )

            assert result.rejected is True, f"Expected {bot_id} to be blocked by global loss limit"
            assert any("Global daily loss limit" in r for r in result.reasons)


# =============================================================================
# Per-Strategy Limit Blocks Only That Strategy
# =============================================================================


class TestPerStrategyLimitBlocksOnlyThatStrategy:
    """Tests verifying that per-strategy limits block only the affected strategy."""

    @pytest.fixture
    def grm_with_strategies(self, mock_settings: MagicMock) -> GlobalRiskManager:
        """Create a GlobalRiskManager with two strategies and generous global limits."""
        db_manager = _make_db_manager()
        ms = _make_multi_settings(
            enabled=True,
            global_max_open_positions=20,
            global_daily_loss_limit_eur=200.0,
        )
        grm = GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=ms)

        # bot-a has tight limits
        budget_a = StrategyBudget(
            max_open_positions=1,
            daily_loss_limit_eur=10.0,
            max_position_pct=2.0,
            position_size_multiplier=1.0,
        )
        # bot-b has generous limits
        budget_b = StrategyBudget(
            max_open_positions=10,
            daily_loss_limit_eur=100.0,
            max_position_pct=10.0,
            position_size_multiplier=1.0,
        )
        grm.register_strategy("bot-a", budget_a)
        grm.register_strategy("bot-b", budget_b)
        return grm

    @pytest.mark.asyncio
    async def test_strategy_a_blocked_strategy_b_allowed(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """When bot-a hits its per-strategy limit, bot-b should still be allowed."""
        # bot-a's per-strategy check fails (positions limit)
        strategy_a_result = RiskCheckResult(
            approved=False,
            reasons=["Max open positions reached: 1 >= 1"],
        )
        # bot-b's per-strategy check passes
        strategy_b_result = RiskCheckResult(approved=True)

        # Check bot-a - should be rejected
        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=1,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("0"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm_with_strategies._strategy_risk_managers["bot-a"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_a_result,
            ),
        ):
            result_a = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-a",
            )

        # Check bot-b - should be approved
        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=1,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("0"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm_with_strategies._strategy_risk_managers["bot-b"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_b_result,
            ),
        ):
            result_b = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-b",
            )

        assert result_a.rejected is True
        assert any("[bot-a]" in r for r in result_a.reasons)

        assert result_b.approved is True
        assert len(result_b.reasons) == 0

    @pytest.mark.asyncio
    async def test_strategy_daily_loss_blocks_only_that_strategy(
        self, grm_with_strategies: GlobalRiskManager
    ) -> None:
        """When bot-a hits its daily loss limit, bot-b should still be allowed."""
        # bot-a's per-strategy check fails (daily loss)
        strategy_a_result = RiskCheckResult(
            approved=False,
            reasons=["Daily loss limit reached: -10.00 EUR <= -10.00 EUR"],
        )
        # bot-b's per-strategy check passes
        strategy_b_result = RiskCheckResult(approved=True)

        # Check bot-a - should be rejected
        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=0,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("-10"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm_with_strategies._strategy_risk_managers["bot-a"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_a_result,
            ),
        ):
            result_a = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-a",
            )

        # Check bot-b - should be approved
        with (
            patch.object(
                grm_with_strategies, "_get_global_open_positions_count",
                new_callable=AsyncMock, return_value=0,
            ),
            patch.object(
                grm_with_strategies, "_get_global_daily_pnl",
                new_callable=AsyncMock, return_value=Decimal("-10"),
            ),
            patch.object(
                grm_with_strategies, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm_with_strategies._strategy_risk_managers["bot-b"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_b_result,
            ),
        ):
            result_b = await grm_with_strategies.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-b",
            )

        assert result_a.rejected is True
        assert any("[bot-a]" in r and "Daily loss limit" in r for r in result_a.reasons)

        assert result_b.approved is True
        assert len(result_b.reasons) == 0


# =============================================================================
# Combined Global + Per-Strategy Failures
# =============================================================================


class TestCombinedFailures:
    """Tests for scenarios where both global and per-strategy checks fail."""

    @pytest.mark.asyncio
    async def test_both_global_and_per_strategy_failures_collected(
        self, mock_settings: MagicMock
    ) -> None:
        """When both global and per-strategy checks fail, all reasons are collected."""
        db_manager = _make_db_manager()
        ms = _make_multi_settings(
            enabled=True,
            global_max_open_positions=2,
            global_daily_loss_limit_eur=30.0,
        )
        grm = GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=ms)

        budget = StrategyBudget(
            max_open_positions=1,
            daily_loss_limit_eur=10.0,
            max_position_pct=3.0,
            position_size_multiplier=1.0,
        )
        grm.register_strategy("bot-x", budget)

        # Per-strategy also fails
        strategy_result = RiskCheckResult(
            approved=False,
            reasons=["Max open positions reached: 1 >= 1"],
        )

        with (
            patch.object(
                grm, "_get_global_open_positions_count",
                new_callable=AsyncMock,
                return_value=2,  # == global max
            ),
            patch.object(
                grm, "_get_global_daily_pnl",
                new_callable=AsyncMock,
                return_value=Decimal("-30"),  # == -global daily loss limit
            ),
            patch.object(
                grm, "_check_global_exposure",
                new_callable=AsyncMock,
            ),
            patch.object(
                grm._strategy_risk_managers["bot-x"],
                "check_order",
                new_callable=AsyncMock,
                return_value=strategy_result,
            ),
        ):
            result = await grm.check_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
                price=Decimal("42000"),
                balance={"EUR": Decimal("10000")},
                bot_id="bot-x",
            )

        assert result.rejected is True
        # Should have at least 3 reasons: global positions, global loss, per-strategy positions
        assert len(result.reasons) >= 3
        assert any("Global max positions" in r for r in result.reasons)
        assert any("Global daily loss limit" in r for r in result.reasons)
        assert any("[bot-x]" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_emergency_stop_loss_delegates(
        self, mock_settings: MagicMock
    ) -> None:
        """check_emergency_stop_loss should delegate to legacy RiskManager."""
        db_manager = _make_db_manager()
        grm = GlobalRiskManager(mock_settings, db_manager, multi_strategy_settings=None)

        with patch.object(
            grm._legacy_risk_manager,
            "check_emergency_stop_loss",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_stop:
            triggered = await grm.check_emergency_stop_loss(
                entry_price=Decimal("42000"),
                current_price=Decimal("37000"),
            )

        mock_stop.assert_awaited_once_with(Decimal("42000"), Decimal("37000"))
        assert triggered is True
