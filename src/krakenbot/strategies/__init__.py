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

New strategies (via MultiStrategyRouter):
- GeminiScalpingVolatilite: RSI+MACD scalping on 5m
- GeminiSuiviTendanceMomentum: EMA50/200 trend following on 1d/4h
- GeminiRetourMoyenne: Bollinger mean reversion with DCA on 15m
- GrokGridATRAdaptiveV4: ATR-based adaptive grid with directional bias
- GrokSuperTrend4hRegime: SuperTrend on 4h with daily regime filter
- GrokEMA27_125_ADX_ATR: EMA 27/125 crossover with ADX filter
- GrokAdaptiveDCAWeekly: Weekly adaptive DCA accumulation
- MultiStrategyRouter: Orchestrator for all inner strategies + risk manager
- GeminiGlobalRiskManager: Risk overlay (1% rule, ATR SL, crash protector)
"""

from krakenbot.strategies.base import BaseStrategy, TradingSignal
from krakenbot.strategies.gemini_global_risk_manager import GeminiGlobalRiskManager
from krakenbot.strategies.gemini_retour_moyenne import GeminiRetourMoyenne
from krakenbot.strategies.gemini_scalping_volatilite import GeminiScalpingVolatilite
from krakenbot.strategies.gemini_suivi_tendance_momentum import GeminiSuiviTendanceMomentum
from krakenbot.strategies.grok_adaptive_dca_weekly import GrokAdaptiveDCAWeekly
from krakenbot.strategies.grok_ema_adx_atr import GrokEMA27_125_ADX_ATR
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4
from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime
from krakenbot.strategies.multi_strategy_router import MultiStrategyRouter

__all__ = [
    "BaseStrategy",
    "GeminiGlobalRiskManager",
    "GeminiRetourMoyenne",
    "GeminiScalpingVolatilite",
    "GeminiSuiviTendanceMomentum",
    "GrokAdaptiveDCAWeekly",
    "GrokEMA27_125_ADX_ATR",
    "GrokGridATRAdaptiveV4",
    "GrokSuperTrend4hRegime",
    "MultiStrategyRouter",
    "TradingSignal",
]
