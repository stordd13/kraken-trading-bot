"""Trading strategies for KrakenBot.

This package contains all trading strategies that generate signals
based on market data analysis.

All strategies share a single MultiTimeframeAnalyzer instance that provides
a common data layer with indicators (MACD, RSI, ATR, ADX, Bollinger, SuperTrend,
EMA) across all timeframes (5m to 1w). Use analyzer.get_*() methods to query
any indicator on any timeframe.

Available strategies:
- ThresholdRollingStrategy: Rolling mean reversion with multi-position support
- AdaptiveStrategy: Adaptive thresholds based on market regime
- CapitulationStrategy: Crash bounce detection with high conviction
- BearShortStrategy: Margin shorts in bear markets
- GridSpotStrategy: Grid trading with limit orders
- GridAdaptiveStrategy: ATR-based adaptive grid trading
- TrendFollowingStrategy: EMA cross trend riding
"""

from krakenbot.strategies.base import BaseStrategy, TradingSignal

__all__ = [
    "BaseStrategy",
    "TradingSignal",
]
