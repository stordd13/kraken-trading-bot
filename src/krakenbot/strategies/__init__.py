"""Trading strategies for KrakenBot.

This package contains all trading strategies that generate signals
based on market data analysis.

Available strategies:
- ThresholdStrategy: Simple mean reversion based on price thresholds
"""

from krakenbot.strategies.base import BaseStrategy, TradingSignal
from krakenbot.strategies.threshold import ThresholdStrategy

__all__ = [
    # Base classes
    "BaseStrategy",
    "TradingSignal",
    # Strategies
    "ThresholdStrategy",
]
