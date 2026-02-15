"""Multi-timeframe analysis with market regime detection.

This module provides a shared analyzer that combines indicators across
multiple timeframes (5m, 15m, 1h) to produce adaptive trading parameters.

Components:
    - MarketRegime: Bull/Bear/Neutral classification from 1h EMA crossover
    - TimeframeZone: Oversold/Neutral/Overbought from RSI + Bollinger per timeframe
    - MultiTimeframeAnalysis: Aggregated analysis with recommended thresholds
    - MultiTimeframeAnalyzer: Main class, one instance shared across strategies
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from krakenbot.core.logger import get_logger
from krakenbot.indicators.atr import ATRIndicator
from krakenbot.indicators.bollinger import BollingerBandsIndicator
from krakenbot.indicators.ema import EMAIndicator
from krakenbot.indicators.rsi import RSIIndicator

if TYPE_CHECKING:
    from krakenbot.core.database import DatabaseManager

logger = get_logger(__name__)


class MarketRegime(str, Enum):
    """Market regime classification based on 1h EMA crossover."""

    STRONG_BEAR = "strong_bear"
    BEAR = "bear"
    NEUTRAL = "neutral"
    BULL = "bull"
    STRONG_BULL = "strong_bull"


class TimeframeZone(str, Enum):
    """Timeframe zone classification based on RSI + Bollinger."""

    OVERSOLD = "oversold"
    NEUTRAL = "neutral"
    OVERBOUGHT = "overbought"


@dataclass
class MultiTimeframeAnalysis:
    """Aggregated multi-timeframe analysis result.

    Contains market regime, zone classification per timeframe,
    and recommended adaptive trading parameters.

    Attributes:
        regime: Current market regime (1h EMA-based).
        zone_15m: Zone classification for 15m timeframe.
        zone_5m: Zone classification for 5m timeframe.
        trend_strength: EMA spread as percentage (0 = flat, >0 = trending).
        volatility_atr: Current ATR value (absolute).
        volatility_pct: ATR as percentage of current price.
        volume_ratio_5m: Current 5m volume / 20-candle average.
        volume_ratio_15m: Current 15m volume / 20-candle average.
        rsi_5m: Current 5m RSI value.
        rsi_15m: Current 15m RSI value.
        rsi_1h: Current 1h RSI value.
        recommended_buy_threshold: Adaptive buy threshold (negative %).
        recommended_sell_threshold: Adaptive sell threshold (positive %).
        recommended_stop_loss_pct: Adaptive stop-loss (positive %).
        recommended_position_size_pct: Adaptive position size (% of portfolio).
        recommended_max_positions: Adaptive max positions.
    """

    regime: MarketRegime
    zone_15m: TimeframeZone
    zone_5m: TimeframeZone
    trend_strength: float
    volatility_atr: Decimal
    volatility_pct: float
    volume_ratio_5m: float
    volume_ratio_15m: float
    rsi_5m: float | None
    rsi_15m: float | None
    rsi_1h: float | None
    recommended_buy_threshold: float
    recommended_sell_threshold: float
    recommended_stop_loss_pct: float
    recommended_position_size_pct: float
    recommended_max_positions: int
    metadata: dict[str, Any] = field(default_factory=dict)


class MultiTimeframeAnalyzer:
    """Shared multi-timeframe analyzer.

    One instance is created in main.py and passed to all strategies
    via the `analyzer` parameter. Processes candles from all timeframes
    and provides adaptive analysis.

    Usage:
        1. Call initialize() at startup to load historical candles
        2. Call update() on each OHLC event
        3. Call analyze() to get current analysis (or None if warming up)
    """

    def __init__(
        self,
        ema_fast_period: int = 20,
        ema_slow_period: int = 50,
        atr_period: int = 14,
        rsi_period: int = 14,
        bb_period: int = 20,
        regime_neutral_threshold: float = 0.5,
        warmup_candles_1h: int = 50,
    ) -> None:
        """Initialize multi-timeframe analyzer.

        Args:
            ema_fast_period: Fast EMA period for 1h trend.
            ema_slow_period: Slow EMA period for 1h trend.
            atr_period: ATR period for volatility.
            rsi_period: RSI period for all timeframes.
            bb_period: Bollinger Bands period.
            regime_neutral_threshold: EMA spread % threshold for neutral.
            warmup_candles_1h: Min 1h candles before analysis is valid.
        """
        self._regime_neutral_threshold = regime_neutral_threshold
        self._warmup_candles_1h = warmup_candles_1h

        # 1h indicators (trend detection)
        self._ema_fast_1h = EMAIndicator(period=ema_fast_period)
        self._ema_slow_1h = EMAIndicator(period=ema_slow_period)
        self._rsi_1h = RSIIndicator(period=rsi_period)
        self._atr_1h = ATRIndicator(period=atr_period)

        # 15m indicators (zone detection)
        self._rsi_15m = RSIIndicator(period=rsi_period)
        self._bb_15m = BollingerBandsIndicator(period=bb_period)

        # 5m indicators (trigger)
        self._rsi_5m = RSIIndicator(period=rsi_period)
        self._bb_5m = BollingerBandsIndicator(period=bb_period)

        # Volume tracking (deques for rolling average)
        self._volume_5m: deque[Decimal] = deque(maxlen=20)
        self._volume_15m: deque[Decimal] = deque(maxlen=20)

        # Candle counts
        self._candle_count_1h: int = 0
        self._candle_count_15m: int = 0
        self._candle_count_5m: int = 0

        # Last close prices per timeframe
        self._last_close_1h: Decimal | None = None
        self._last_close_15m: Decimal | None = None
        self._last_close_5m: Decimal | None = None

    async def initialize(self, db_manager: DatabaseManager, pair: str = "XBT/USDC") -> None:
        """Load historical candles from database for warmup.

        Fetches the most recent candles per timeframe from market_data_ohlc
        and feeds them to the indicators.

        Args:
            db_manager: Database manager for queries.
            pair: Trading pair to load data for.
        """
        from sqlalchemy import select

        from krakenbot.models.market_data import OHLCData

        for interval, count in [(60, 100), (15, 100), (5, 100)]:
            try:
                async with db_manager.read_session() as session:
                    result = await session.execute(
                        select(OHLCData)
                        .where(OHLCData.pair == pair)
                        .where(OHLCData.interval == interval)
                        .order_by(OHLCData.timestamp.asc())
                        .limit(count)
                    )
                    candles = result.scalars().all()

                    for candle in candles:
                        self.update(
                            {
                                "open": candle.open,
                                "high": candle.high,
                                "low": candle.low,
                                "close": candle.close,
                                "volume": candle.volume,
                            },
                            interval,
                        )

                    logger.info(
                        "mtf_warmup_loaded",
                        interval=interval,
                        candles=len(candles),
                    )
            except Exception as e:
                logger.warning(
                    "mtf_warmup_error",
                    interval=interval,
                    error=str(e),
                )

    def update(self, candle_data: dict[str, Any], interval: int) -> None:
        """Update indicators for a specific timeframe.

        Routes candle data to the correct set of indicators.

        Args:
            candle_data: OHLC data with keys: open, high, low, close, volume.
            interval: Candle interval in minutes (5, 15, or 60).
        """
        close = Decimal(str(candle_data["close"]))
        high = Decimal(str(candle_data["high"]))
        low = Decimal(str(candle_data["low"]))
        volume = Decimal(str(candle_data.get("volume", 0)))

        if interval == 60:
            self._ema_fast_1h.update(close)
            self._ema_slow_1h.update(close)
            self._rsi_1h.update(close)
            self._atr_1h.update(high, low, close)
            self._last_close_1h = close
            self._candle_count_1h += 1
        elif interval == 15:
            self._rsi_15m.update(close)
            self._bb_15m.update(close)
            self._volume_15m.append(volume)
            self._last_close_15m = close
            self._candle_count_15m += 1
        elif interval == 5:
            self._rsi_5m.update(close)
            self._bb_5m.update(close)
            self._volume_5m.append(volume)
            self._last_close_5m = close
            self._candle_count_5m += 1

    def analyze(self) -> MultiTimeframeAnalysis | None:
        """Generate multi-timeframe analysis.

        Returns None if not enough data (< warmup_candles_1h for 1h).

        Returns:
            MultiTimeframeAnalysis with all parameters, or None.
        """
        # Check warmup
        if self._candle_count_1h < self._warmup_candles_1h:
            return None
        if not self._ema_fast_1h.is_ready or not self._ema_slow_1h.is_ready:
            return None
        if self._last_close_1h is None:
            return None

        # 1. Determine market regime from 1h EMA crossover
        ema_fast = self._ema_fast_1h.value
        ema_slow = self._ema_slow_1h.value
        if ema_fast is None or ema_slow is None:
            return None

        ema_spread_pct = float((ema_fast - ema_slow) / ema_slow * Decimal("100"))
        regime = self._classify_regime(ema_spread_pct)
        trend_strength = abs(ema_spread_pct)

        # 2. ATR volatility
        atr_value = self._atr_1h.value or Decimal("0")
        volatility_pct = (
            float(atr_value / self._last_close_1h * Decimal("100"))
            if self._last_close_1h > Decimal("0")
            else 0.0
        )

        # 3. Zone classifications
        zone_15m = self._classify_zone(self._rsi_15m.value, self._bb_15m.value)
        zone_5m = self._classify_zone(self._rsi_5m.value, self._bb_5m.value)

        # 4. Volume ratios
        volume_ratio_5m = self._calc_volume_ratio(self._volume_5m)
        volume_ratio_15m = self._calc_volume_ratio(self._volume_15m)

        # 5. Adaptive thresholds
        buy_threshold, sell_threshold, stop_loss = self._calc_adaptive_thresholds(
            regime, volatility_pct
        )

        # 6. Adaptive position sizing
        position_size_pct = self._calc_adaptive_position_size(regime, volatility_pct)
        max_positions = self._calc_adaptive_max_positions(regime)

        analysis = MultiTimeframeAnalysis(
            regime=regime,
            zone_15m=zone_15m,
            zone_5m=zone_5m,
            trend_strength=trend_strength,
            volatility_atr=atr_value,
            volatility_pct=volatility_pct,
            volume_ratio_5m=volume_ratio_5m,
            volume_ratio_15m=volume_ratio_15m,
            rsi_5m=self._rsi_5m.value,
            rsi_15m=self._rsi_15m.value,
            rsi_1h=self._rsi_1h.value,
            recommended_buy_threshold=buy_threshold,
            recommended_sell_threshold=sell_threshold,
            recommended_stop_loss_pct=stop_loss,
            recommended_position_size_pct=position_size_pct,
            recommended_max_positions=max_positions,
            metadata={
                "ema_fast_1h": float(ema_fast) if ema_fast else None,
                "ema_slow_1h": float(ema_slow) if ema_slow else None,
            },
        )
        self._last_analysis = analysis
        return analysis

    def _classify_regime(self, ema_spread_pct: float) -> MarketRegime:
        """Classify market regime from EMA spread.

        Args:
            ema_spread_pct: (EMA_fast - EMA_slow) / EMA_slow * 100.

        Returns:
            MarketRegime classification.
        """
        threshold = self._regime_neutral_threshold

        if ema_spread_pct > threshold * 2:
            return MarketRegime.STRONG_BULL
        elif ema_spread_pct > threshold:
            return MarketRegime.BULL
        elif ema_spread_pct < -threshold * 2:
            return MarketRegime.STRONG_BEAR
        elif ema_spread_pct < -threshold:
            return MarketRegime.BEAR
        else:
            return MarketRegime.NEUTRAL

    def _classify_zone(self, rsi_value: float | None, bb_value: Any) -> TimeframeZone:
        """Classify zone from RSI + Bollinger Bands.

        Args:
            rsi_value: RSI value for this timeframe.
            bb_value: Bollinger Bands result for this timeframe.

        Returns:
            TimeframeZone classification.
        """
        if rsi_value is None:
            return TimeframeZone.NEUTRAL

        # RSI-based classification
        if rsi_value < 30:
            return TimeframeZone.OVERSOLD
        elif rsi_value > 70:
            return TimeframeZone.OVERBOUGHT

        # Bollinger Bands refinement
        if bb_value is not None and hasattr(bb_value, "percent_b"):
            pb = bb_value.percent_b
            if pb is not None:
                if pb < 0.0:
                    return TimeframeZone.OVERSOLD
                elif pb > 1.0:
                    return TimeframeZone.OVERBOUGHT

        return TimeframeZone.NEUTRAL

    def _calc_volume_ratio(self, volumes: deque[Decimal]) -> float:
        """Calculate current volume relative to rolling average.

        Args:
            volumes: Deque of recent volumes.

        Returns:
            Ratio of latest volume to average (1.0 = average).
        """
        if len(volumes) < 2:
            return 1.0

        current = volumes[-1]
        avg = sum(volumes) / Decimal(str(len(volumes)))

        if avg <= Decimal("0"):
            return 1.0

        return float(current / avg)

    def _calc_adaptive_thresholds(
        self, regime: MarketRegime, volatility_pct: float
    ) -> tuple[float, float, float]:
        """Calculate adaptive buy/sell/stop-loss thresholds.

        In bull markets: tighter buy thresholds (buy dips sooner),
        wider sell thresholds (let profits run), wider stop-loss (let breathe).
        In bear markets: wider buy thresholds (wait for bigger drops),
        tighter sell thresholds (take profits sooner), tighter stop-loss (cut fast).

        Args:
            regime: Current market regime.
            volatility_pct: ATR as % of price.

        Returns:
            Tuple of (buy_threshold, sell_threshold, stop_loss_pct) in percentage.
        """
        # Base thresholds
        base_buy = -1.0  # -1%
        base_sell = 2.0  # +2%
        base_stop_loss = 5.0  # 5%

        # BUY regime multiplier
        regime_mult = {
            MarketRegime.STRONG_BULL: 0.7,  # Buy dips sooner
            MarketRegime.BULL: 0.85,
            MarketRegime.NEUTRAL: 1.0,
            MarketRegime.BEAR: 1.5,  # Wait for bigger drops
            MarketRegime.STRONG_BEAR: 2.0,  # Require deep dip (-6%)
        }[regime]

        # SELL regime multiplier
        sell_regime_mult = {
            MarketRegime.STRONG_BULL: 1.5,  # Let profits run
            MarketRegime.BULL: 1.3,
            MarketRegime.NEUTRAL: 1.0,
            MarketRegime.BEAR: 0.8,  # Take profits sooner
            MarketRegime.STRONG_BEAR: 0.6,
        }[regime]

        # STOP-LOSS regime multiplier (tighter in bear = cut losses fast)
        stop_loss_regime_mult = {
            MarketRegime.STRONG_BULL: 1.5,  # Let positions breathe
            MarketRegime.BULL: 1.2,
            MarketRegime.NEUTRAL: 1.0,
            MarketRegime.BEAR: 0.8,  # Cut losses sooner
            MarketRegime.STRONG_BEAR: 0.6,  # Cut losses fast
        }[regime]

        # Volatility multiplier (higher vol = wider thresholds)
        vol_mult = max(0.5, min(2.0, volatility_pct / 1.5))

        buy_threshold = base_buy * regime_mult * vol_mult
        sell_threshold = base_sell * sell_regime_mult * vol_mult
        stop_loss = base_stop_loss * stop_loss_regime_mult * vol_mult

        # Clamp to reasonable ranges
        buy_threshold = max(-5.0, min(-0.3, buy_threshold))
        sell_threshold = max(0.5, min(10.0, sell_threshold))
        stop_loss = max(1.5, min(15.0, stop_loss))

        return buy_threshold, sell_threshold, stop_loss

    def _calc_adaptive_position_size(self, regime: MarketRegime, volatility_pct: float) -> float:
        """Calculate adaptive position size as % of portfolio.

        Higher in low volatility + bull, lower in high volatility + bear.

        Args:
            regime: Current market regime.
            volatility_pct: ATR as % of price.

        Returns:
            Recommended position size percentage.
        """
        base_size = 5.0  # 5% base

        regime_mult = {
            MarketRegime.STRONG_BULL: 1.2,
            MarketRegime.BULL: 1.1,
            MarketRegime.NEUTRAL: 1.0,
            MarketRegime.BEAR: 0.8,
            MarketRegime.STRONG_BEAR: 0.6,
        }[regime]

        # Inverse volatility: lower position in high vol
        vol_mult = max(0.5, min(1.5, 1.5 / max(volatility_pct, 0.5)))

        size = base_size * regime_mult * vol_mult
        return max(1.0, min(10.0, size))

    def _calc_adaptive_max_positions(self, regime: MarketRegime) -> int:
        """Calculate adaptive max positions based on regime.

        More conservative in bear markets.

        Args:
            regime: Current market regime.

        Returns:
            Recommended maximum number of open positions.
        """
        return {
            MarketRegime.STRONG_BULL: 7,
            MarketRegime.BULL: 5,
            MarketRegime.NEUTRAL: 4,
            MarketRegime.BEAR: 3,
            MarketRegime.STRONG_BEAR: 2,
        }[regime]

    @property
    def is_ready(self) -> bool:
        """Check if analyzer has enough data for analysis."""
        return (
            self._candle_count_1h >= self._warmup_candles_1h
            and self._ema_fast_1h.is_ready
            and self._ema_slow_1h.is_ready
        )

    @property
    def candle_counts(self) -> dict[str, int]:
        """Get candle counts per timeframe."""
        return {
            "1h": self._candle_count_1h,
            "15m": self._candle_count_15m,
            "5m": self._candle_count_5m,
        }
