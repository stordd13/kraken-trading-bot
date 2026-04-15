"""Technical indicators for trading strategies."""

from krakenbot.indicators.adx import ADXIndicator
from krakenbot.indicators.atr import ATRIndicator
from krakenbot.indicators.bollinger import BollingerBandsIndicator, BollingerBandsResult
from krakenbot.indicators.donchian import DonchianIndicator
from krakenbot.indicators.ema import EMAIndicator
from krakenbot.indicators.ichimoku import IchimokuIndicator
from krakenbot.indicators.macd import MACDIndicator, MACDResult
from krakenbot.indicators.multi_pair_registry import (
    MultiPairAnalyzerRegistry,
    normalize_pair,
)
from krakenbot.indicators.multi_timeframe import (
    MarketRegime,
    MultiTimeframeAnalysis,
    MultiTimeframeAnalyzer,
    TimeframeZone,
)
from krakenbot.indicators.rsi import RSIIndicator
from krakenbot.indicators.supertrend import SuperTrendIndicator
from krakenbot.indicators.vwap import VWAPIndicator

__all__ = [
    "ADXIndicator",
    "ATRIndicator",
    "BollingerBandsIndicator",
    "BollingerBandsResult",
    "DonchianIndicator",
    "EMAIndicator",
    "IchimokuIndicator",
    "MACDIndicator",
    "MACDResult",
    "MarketRegime",
    "MultiPairAnalyzerRegistry",
    "MultiTimeframeAnalysis",
    "MultiTimeframeAnalyzer",
    "RSIIndicator",
    "SuperTrendIndicator",
    "TimeframeZone",
    "VWAPIndicator",
]
