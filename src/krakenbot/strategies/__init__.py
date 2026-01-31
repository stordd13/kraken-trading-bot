"""Trading strategies for KrakenBot.

This package contains all trading strategies that generate signals
based on market data analysis.

Available strategies:
- ThresholdStrategy: Simple mean reversion based on price thresholds
- TechnicalIndicatorStrategy: RSI + MACD + Bollinger Bands with confluence
"""

from krakenbot.strategies.base import BaseStrategy, TradingSignal
from krakenbot.strategies.technical_indicator import TechnicalIndicatorStrategy
from krakenbot.strategies.threshold import ThresholdStrategy

__all__ = [
    # Base classes
    "BaseStrategy",
    # Strategies
    "ThresholdStrategy",
    "TechnicalIndicatorStrategy",
    "TradingSignal",
]
