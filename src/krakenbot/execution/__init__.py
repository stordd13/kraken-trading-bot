"""Execution module for trading order management.

This module provides the core execution infrastructure for the KrakenBot,
including risk management validation and order execution.

Components:
    - RiskManager: Validates orders against configured risk limits
    - RiskCheckResult: Result of risk validation checks
    - ExecutionEngine: Orchestrates signal processing and order execution

Example:
    >>> from krakenbot.execution import RiskManager, ExecutionEngine, RiskCheckResult
    >>>
    >>> # Create risk manager
    >>> risk_manager = RiskManager(settings, db_manager)
    >>>
    >>> # Check an order
    >>> result = await risk_manager.check_order(
    ...     pair="XBT/EUR",
    ...     side=TradeSide.BUY,
    ...     amount=Decimal("0.001"),
    ...     price=Decimal("42000"),
    ...     balance={"EUR": Decimal("1000")}
    ... )
    >>>
    >>> # Create and start execution engine
    >>> engine = ExecutionEngine(settings, event_bus, db_manager, rest_client)
    >>> await engine.start()
"""

from krakenbot.execution.engine import ExecutionEngine
from krakenbot.execution.risk import RiskCheckResult, RiskManager

__all__ = [
    "ExecutionEngine",
    "RiskCheckResult",
    "RiskManager",
]
