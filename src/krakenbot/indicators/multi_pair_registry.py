"""Per-pair analyzer registry for multi-pair trading.

Each trading pair gets its own MultiTimeframeAnalyzer instance with independent
indicator state. This prevents cross-contamination (e.g., BTC RSI affected by
ETH candles).

Usage:
    registry = MultiPairAnalyzerRegistry()
    registry.get_or_create("BTC/USDC")
    registry.get_or_create("ETH/USDC")
    await registry.initialize_all(db_manager, exchange="binance")

    # Route candles
    registry.update("BTC/USDC", candle_data, interval=240)

    # Get pair-specific analyzer
    btc_analyzer = registry.get("BTC/USDC")
    atr = btc_analyzer.get_atr(14, "4h")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from krakenbot.core.logger import get_logger
from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer

if TYPE_CHECKING:
    from krakenbot.core.database import DatabaseManager

logger = get_logger(__name__)


def normalize_pair(pair: str) -> str:
    """Normalize trading pair: XBT -> BTC.

    The canonical internal format is BTC/USDC. The XBT variant is
    only used by the Kraken legacy connector.
    """
    return pair.replace("XBT/", "BTC/")


class MultiPairAnalyzerRegistry:
    """Registry mapping trading pair -> dedicated MultiTimeframeAnalyzer.

    Each pair gets its own analyzer instance with independent indicator state.
    Safe for single-process async usage (no locking needed).
    """

    def __init__(self, **analyzer_kwargs: Any) -> None:
        """Store default analyzer construction params.

        Args:
            **analyzer_kwargs: Passed to MultiTimeframeAnalyzer constructor
                (ema_fast_period, ema_slow_period, atr_period, etc.).
        """
        self._analyzer_kwargs = analyzer_kwargs
        self._analyzers: dict[str, MultiTimeframeAnalyzer] = {}

    def get_or_create(self, pair: str) -> MultiTimeframeAnalyzer:
        """Get analyzer for pair, creating if not yet registered.

        Args:
            pair: Trading pair (e.g., "BTC/USDC"). Normalized internally.

        Returns:
            The MultiTimeframeAnalyzer for this pair.
        """
        normalized = normalize_pair(pair)
        if normalized not in self._analyzers:
            self._analyzers[normalized] = MultiTimeframeAnalyzer(**self._analyzer_kwargs)
            logger.info("analyzer_created_for_pair", pair=normalized)
        return self._analyzers[normalized]

    def get(self, pair: str) -> MultiTimeframeAnalyzer | None:
        """Get analyzer without creating. Returns None if not registered."""
        return self._analyzers.get(normalize_pair(pair))

    def update(self, pair: str, candle_data: dict[str, Any], interval: int) -> None:
        """Route candle to the correct pair's analyzer.

        Args:
            pair: Trading pair of the candle.
            candle_data: Dict with open, high, low, close, volume.
            interval: Candle interval in minutes.
        """
        analyzer = self.get(pair)
        if analyzer is not None:
            analyzer.update(candle_data, interval)

    async def initialize_all(
        self,
        db_manager: DatabaseManager,
        exchange: str = "binance",
    ) -> None:
        """Warm up all registered analyzers from historical DB data.

        Args:
            db_manager: Database manager for queries.
            exchange: Exchange to filter data by.
        """
        for pair, analyzer in self._analyzers.items():
            logger.info("analyzer_warmup_starting", pair=pair, exchange=exchange)
            await analyzer.initialize(db_manager, pair=pair, exchange=exchange)
            logger.info("analyzer_warmup_complete", pair=pair)

    @property
    def pairs(self) -> list[str]:
        """List of registered trading pairs."""
        return list(self._analyzers.keys())

    def __len__(self) -> int:
        return len(self._analyzers)

    def __contains__(self, pair: str) -> bool:
        return normalize_pair(pair) in self._analyzers
