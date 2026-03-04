"""Feature Store for ML pipeline.

Responsibilities:
    1. ``build_batch()``: Replay candles from DB, compute features, store to ml_features.
    2. ``update_incremental()``: Compute features for a single new candle (live mode).
    3. ``get_features()``: Return feature vector for a single timestamp.
    4. ``get_training_data()``: Return DataFrame of features + targets for training.

The FeatureStore does NOT own the MultiTimeframeAnalyzer — it creates a fresh one
for batch builds, or receives the shared one for incremental updates.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
import math
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
import structlog

from krakenbot.indicators.multi_timeframe import (
    MultiTimeframeAnalyzer,
)
from krakenbot.ml.db_models import MLExternalData, MLFeatureRow
from krakenbot.models.market_data import OHLCData

if TYPE_CHECKING:
    import pandas as pd

    from krakenbot.core.database import DatabaseManager

logger = structlog.get_logger(__name__)

# Timeframe intervals we load for feature computation
_FEATURE_INTERVALS: list[int] = [60, 240, 1440, 10080]

# Higher TFs sorted first on timestamp ties (same logic as backtest.py line 314)
_INTERVAL_ORDER: dict[int, int] = {10080: 0, 1440: 1, 240: 2, 60: 3}

# Timeframes used for feature extraction
_FEATURE_TFS: list[str] = ["1h", "4h", "1d"]


class FeatureStore:
    """ML feature computation and storage."""

    # Primary interval for feature rows (4h candle alignment)
    PRIMARY_INTERVAL: int = 240

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager
        # Rolling close prices for volatility computation: (pair, interval) -> deque
        self._close_history: dict[tuple[str, int], deque[tuple[datetime, float]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build_batch(
        self,
        pair: str,
        start_date: datetime,
        end_date: datetime,
        *,
        compute_targets: bool = True,
        batch_size: int = 500,
    ) -> int:
        """Replay candles from DB, compute features, upsert to ml_features.

        Creates a FRESH MultiTimeframeAnalyzer, warms it up, then
        iterates chronologically through all timeframes, emitting one
        feature row per 4h candle.

        Args:
            pair: Trading pair (e.g., "XBT/USDC").
            start_date: Start of feature period (UTC).
            end_date: End of feature period (UTC).
            compute_targets: Whether to compute forward-looking targets.
            batch_size: DB insert batch size.

        Returns:
            Number of feature rows written.
        """
        logger.info(
            "build_batch_start",
            pair=pair,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        # 1. Load candles with warmup
        warmup_start = start_date - timedelta(days=400)
        candle_sequence = await self._load_replay_sequence(pair, warmup_start, end_date)
        logger.info("candles_loaded", total=len(candle_sequence))

        # 2. Create fresh analyzer + pre-register lazy indicators
        analyzer = MultiTimeframeAnalyzer()
        self._preregister_lazy_indicators(analyzer)

        # 3. Reset close history for this build
        self._close_history = {}

        # 4. Replay chronologically
        rows: list[dict[str, Any]] = []
        for candle, interval in candle_sequence:
            ts = candle.timestamp
            close_f = float(candle.close)
            high_f = float(candle.high)
            low_f = float(candle.low)
            volume_f = float(candle.volume)

            # Update analyzer
            candle_dict = {
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            analyzer.update(candle_dict, interval)

            # Track close history for volatility
            self._update_close_history(pair, interval, ts, close_f)

            # Emit feature row on primary interval candles within date range
            if interval == self.PRIMARY_INTERVAL and ts >= start_date:
                features = self._compute_features(
                    analyzer,
                    ts,
                    pair,
                    close_f,
                    high_f,
                    low_f,
                    volume_f,
                )
                # Add external data (forward-fill from ml_external_data)
                fear_greed = await self._get_external_value("fear_greed", ts)
                features["fear_greed_index"] = fear_greed

                row = {
                    "timestamp": ts,
                    "pair": pair,
                    "interval": self.PRIMARY_INTERVAL,
                    "close_price": candle.close,
                    "volume": candle.volume,
                    **features,
                }
                rows.append(row)

                # Batch upsert
                if len(rows) >= batch_size:
                    await self._upsert_rows(rows)
                    rows = []

        # Flush remaining rows
        if rows:
            await self._upsert_rows(rows)

        total_rows = await self._count_rows(pair, start_date, end_date)
        logger.info("build_batch_features_done", pair=pair, rows=total_rows)

        # 5. Compute targets (second pass)
        if compute_targets:
            targets_filled = await self._compute_targets(pair, start_date, end_date)
            logger.info("build_batch_targets_done", pair=pair, targets_filled=targets_filled)

        return total_rows

    async def update_incremental(
        self,
        pair: str,
        analyzer: MultiTimeframeAnalyzer,
        candle_data: dict[str, Any],
        interval: int,
        timestamp: datetime,
    ) -> None:
        """Compute and store features for a single new candle.

        Called from the live trading loop. Uses the shared analyzer.

        Args:
            pair: Trading pair.
            analyzer: Shared MultiTimeframeAnalyzer (already warmed up).
            candle_data: OHLC dict with open, high, low, close, volume.
            interval: Candle interval in minutes.
            timestamp: Candle timestamp (UTC).
        """
        close_f = float(candle_data["close"])
        high_f = float(candle_data["high"])
        low_f = float(candle_data["low"])
        volume_f = float(candle_data.get("volume", 0))

        self._update_close_history(pair, interval, timestamp, close_f)

        if interval != self.PRIMARY_INTERVAL:
            return

        features = self._compute_features(
            analyzer,
            timestamp,
            pair,
            close_f,
            high_f,
            low_f,
            volume_f,
        )
        fear_greed = await self._get_external_value("fear_greed", timestamp)
        features["fear_greed_index"] = fear_greed

        row = {
            "timestamp": timestamp,
            "pair": pair,
            "interval": self.PRIMARY_INTERVAL,
            "close_price": Decimal(str(close_f)),
            "volume": Decimal(str(volume_f)),
            **features,
        }
        await self._upsert_rows([row])
        logger.debug("incremental_feature_stored", pair=pair, ts=timestamp.isoformat())

    async def get_features(
        self,
        timestamp: datetime,
        pair: str,
        interval: int = 240,
    ) -> dict[str, float | None] | None:
        """Retrieve a single feature vector from DB.

        Args:
            timestamp: Feature timestamp.
            pair: Trading pair.
            interval: Feature interval (default 240 = 4h).

        Returns:
            Dict of feature values, or None if not found.
        """
        async with self._db.read_session() as session:
            stmt = select(MLFeatureRow).where(
                MLFeatureRow.timestamp == timestamp,
                MLFeatureRow.pair == pair,
                MLFeatureRow.interval == interval,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None

            # Convert to dict, excluding PK and context columns
            feature_cols = [
                c.key
                for c in MLFeatureRow.__table__.columns
                if c.key not in ("timestamp", "pair", "interval", "close_price", "volume")
                and not c.key.startswith("target_")
                and c.key != "extra_features"
            ]
            return {col: getattr(row, col) for col in feature_cols}

    async def get_training_data(
        self,
        pair: str,
        start_date: datetime,
        end_date: datetime,
        interval: int = 240,
    ) -> pd.DataFrame:
        """Load features + targets as a DataFrame for model training.

        Only returns rows where target_return_4h is NOT NULL.

        Args:
            pair: Trading pair.
            start_date: Start of training period.
            end_date: End of training period.
            interval: Feature interval.

        Returns:
            DataFrame with features and targets.
        """
        import pandas as pd

        async with self._db.read_session() as session:
            stmt = (
                select(MLFeatureRow)
                .where(
                    MLFeatureRow.pair == pair,
                    MLFeatureRow.interval == interval,
                    MLFeatureRow.timestamp >= start_date,
                    MLFeatureRow.timestamp <= end_date,
                    MLFeatureRow.target_return_4h.is_not(None),
                )
                .order_by(MLFeatureRow.timestamp.asc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return pd.DataFrame()

        # Convert to list of dicts
        records = []
        for row in rows:
            record = {
                c.key: getattr(row, c.key)
                for c in MLFeatureRow.__table__.columns
                if c.key not in ("extra_features",)
            }
            records.append(record)

        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # Feature computation (CRITICAL: no look-ahead)
    # ------------------------------------------------------------------

    def _compute_features(
        self,
        analyzer: MultiTimeframeAnalyzer,
        timestamp: datetime,
        pair: str,
        close_price: float,
        high: float,
        low: float,
        volume: float,
    ) -> dict[str, Any]:
        """Extract all features from the current analyzer state.

        This method ONLY reads current indicator state. No future data
        access is possible because the analyzer is updated candle-by-candle
        in chronological order.
        """
        features: dict[str, Any] = {}

        # --- Trend & Regime (per timeframe) ---
        for tf in _FEATURE_TFS:
            tf_features = analyzer.get_features_dict(tf)

            features[f"ema_spread_{tf}"] = tf_features.get("ema_spread")
            features[f"rsi_14_{tf}"] = tf_features.get("rsi_14")
            features[f"regime_{tf}"] = tf_features.get("regime")

            if tf == "4h":
                features["supertrend_dist_4h"] = tf_features.get("supertrend_dist")
                st_dir = tf_features.get("supertrend_dir")
                features["supertrend_dir_4h"] = int(st_dir) if st_dir is not None else None
                features["macd_hist_4h"] = tf_features.get("macd_hist_norm")
                features["adx_4h"] = tf_features.get("adx")
                features["bb_width_4h"] = tf_features.get("bb_width")
                features["bb_pctb_4h"] = tf_features.get("bb_pctb")
                features["volume_ratio_4h"] = tf_features.get("volume_ratio")
                features["vwap_deviation_4h"] = tf_features.get("vwap_deviation")
                features["atr_ratio_4h"] = tf_features.get("atr_ratio")

            elif tf == "1h":
                features["macd_hist_1h"] = tf_features.get("macd_hist_norm")
                features["volume_ratio_1h"] = tf_features.get("volume_ratio")

            elif tf == "1d":
                features["adx_1d"] = tf_features.get("adx")
                features["atr_ratio_1d"] = tf_features.get("atr_ratio")

        # --- Volatility (from rolling close history) ---
        features["realized_vol_4h"] = self._compute_realized_vol(pair, 240, 6)
        features["realized_vol_24h"] = self._compute_realized_vol(pair, 60, 24)
        features["realized_vol_7d"] = self._compute_realized_vol(pair, 240, 42)

        # Parkinson volatility (high-low based, single candle)
        if high > 0 and low > 0 and high != low:
            features["parkinson_vol_4h"] = math.sqrt(math.log(high / low) ** 2 / (4 * math.log(2)))
        else:
            features["parkinson_vol_4h"] = None

        # --- Volume & Micro ---
        if close_price > 0:
            features["hl_ratio"] = (high - low) / close_price
        else:
            features["hl_ratio"] = None

        # --- Cyclic features ---
        features["hour_sin"] = math.sin(2 * math.pi * timestamp.hour / 24)
        features["hour_cos"] = math.cos(2 * math.pi * timestamp.hour / 24)
        features["dow_sin"] = math.sin(2 * math.pi * timestamp.weekday() / 7)
        features["dow_cos"] = math.cos(2 * math.pi * timestamp.weekday() / 7)
        features["month_sin"] = math.sin(2 * math.pi * timestamp.month / 12)
        features["month_cos"] = math.cos(2 * math.pi * timestamp.month / 12)

        return features

    # ------------------------------------------------------------------
    # Realized volatility
    # ------------------------------------------------------------------

    def _compute_realized_vol(self, pair: str, interval: int, window: int) -> float | None:
        """Compute realized volatility as std of log returns."""
        key = (pair, interval)
        history = self._close_history.get(key)
        if history is None or len(history) < window + 1:
            return None
        closes = [c for _, c in list(history)[-(window + 1) :]]
        log_returns = [
            math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0
        ]
        if len(log_returns) < 2:
            return None
        mean = sum(log_returns) / len(log_returns)
        variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
        return math.sqrt(variance)

    def _update_close_history(
        self, pair: str, interval: int, timestamp: datetime, close: float
    ) -> None:
        """Append close price to rolling history."""
        key = (pair, interval)
        if key not in self._close_history:
            self._close_history[key] = deque(maxlen=200)
        self._close_history[key].append((timestamp, close))

    # ------------------------------------------------------------------
    # Lazy indicator pre-registration
    # ------------------------------------------------------------------

    @staticmethod
    def _preregister_lazy_indicators(analyzer: MultiTimeframeAnalyzer) -> None:
        """Pre-register lazy indicators so they exist before warmup data flows.

        See MEMORY.md: lazy indicators return None on first call because
        they are created lazily. Pre-registering ensures they receive
        all candle updates from the start of replay.
        """
        for tf in _FEATURE_TFS:
            analyzer.get_ema(20, tf)
            analyzer.get_ema(50, tf)
            analyzer.get_supertrend(tf, atr_period=10, multiplier=3.0)
            analyzer.get_vwap(20, tf)

    # ------------------------------------------------------------------
    # Candle loading + replay sequence
    # ------------------------------------------------------------------

    async def _load_replay_sequence(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[tuple[OHLCData, int]]:
        """Load and interleave candles for all feature timeframes.

        Mirrors the logic in backtest.py _build_replay_sequence():
        sort by (timestamp, interval_order) with higher TFs first on ties.
        """
        sequence: list[tuple[OHLCData, int]] = []

        for interval in _FEATURE_INTERVALS:
            candles = await self._load_candles(pair, interval, start_time, end_time)
            for c in candles:
                sequence.append((c, interval))

        # Sort: timestamp ASC, higher timeframes first on ties
        sequence.sort(key=lambda x: (x[0].timestamp, _INTERVAL_ORDER.get(x[1], 99)))
        return sequence

    async def _load_candles(
        self,
        pair: str,
        interval: int,
        start_time: datetime,
        end_time: datetime,
    ) -> list[OHLCData]:
        """Load OHLC candles for a specific interval from DB."""
        async with self._db.read_session() as session:
            stmt = (
                select(OHLCData)
                .where(
                    OHLCData.pair == pair,
                    OHLCData.interval == interval,
                    OHLCData.timestamp >= start_time,
                    OHLCData.timestamp <= end_time,
                )
                .order_by(OHLCData.timestamp.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # External data lookup
    # ------------------------------------------------------------------

    async def _get_external_value(self, source: str, before: datetime) -> float | None:
        """Get the most recent external data value before a timestamp (forward-fill)."""
        async with self._db.read_session() as session:
            stmt = (
                select(MLExternalData.value)
                .where(
                    MLExternalData.source == source,
                    MLExternalData.timestamp <= before,
                )
                .order_by(MLExternalData.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row

    # ------------------------------------------------------------------
    # DB upsert
    # ------------------------------------------------------------------

    async def _upsert_rows(self, rows: list[dict[str, Any]]) -> None:
        """Batch upsert feature rows into ml_features."""
        if not rows:
            return
        async with self._db.session() as session:
            for row_data in rows:
                stmt = (
                    pg_insert(MLFeatureRow)
                    .values(**row_data)
                    .on_conflict_do_update(
                        index_elements=["timestamp", "pair", "interval"],
                        set_={
                            k: v
                            for k, v in row_data.items()
                            if k not in ("timestamp", "pair", "interval")
                        },
                    )
                )
                await session.execute(stmt)

    async def _count_rows(self, pair: str, start_date: datetime, end_date: datetime) -> int:
        """Count feature rows for a pair in a date range."""
        async with self._db.read_session() as session:
            stmt = text(
                "SELECT COUNT(*) FROM ml_features "
                "WHERE pair = :pair AND interval = :interval "
                "AND timestamp >= :start AND timestamp <= :end"
            )
            result = await session.execute(
                stmt,
                {
                    "pair": pair,
                    "interval": self.PRIMARY_INTERVAL,
                    "start": start_date,
                    "end": end_date,
                },
            )
            return result.scalar_one()

    # ------------------------------------------------------------------
    # Target computation (second pass, uses future data)
    # ------------------------------------------------------------------

    async def _compute_targets(
        self,
        pair: str,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """Compute forward-looking targets for all feature rows.

        This is a SEPARATE pass after features are built. It looks forward
        in the OHLC data to compute returns and regime classifications.

        Returns:
            Number of rows with targets filled.
        """
        # Load all 4h close prices for the extended range (need future data)
        target_end = end_date + timedelta(days=7)  # Extra 7d for 24h targets
        candles_4h = await self._load_candles(pair, 240, start_date, target_end)

        if not candles_4h:
            return 0

        # Build close price lookup: timestamp -> close_float
        close_lookup: dict[datetime, float] = {c.timestamp: float(c.close) for c in candles_4h}
        timestamps_sorted = sorted(close_lookup.keys())

        # Also need regime data: build analyzer for the full period
        # (features already computed, we just need regime at future timestamps)
        regime_lookup: dict[datetime, str | None] = {}
        analyzer = MultiTimeframeAnalyzer()
        self._preregister_lazy_indicators(analyzer)
        all_candles = await self._load_replay_sequence(
            pair,
            start_date - timedelta(days=400),
            target_end,
        )
        for candle, interval in all_candles:
            candle_dict = {
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            analyzer.update(candle_dict, interval)
            if interval == 240:
                regime_lookup[candle.timestamp] = analyzer.get_regime("4h")

        filled = 0
        async with self._db.session() as session:
            for i, ts in enumerate(timestamps_sorted):
                if ts < start_date or ts > end_date:
                    continue

                close_now = close_lookup[ts]
                if close_now <= 0:
                    continue

                updates: dict[str, Any] = {}

                # target_return_4h: next 4h candle
                ts_4h = _find_next_timestamp(timestamps_sorted, i, 1)
                if ts_4h and ts_4h in close_lookup:
                    updates["target_return_4h"] = close_lookup[ts_4h] / close_now - 1

                # target_return_24h: 6 candles ahead (6 * 4h = 24h)
                ts_24h = _find_next_timestamp(timestamps_sorted, i, 6)
                if ts_24h and ts_24h in close_lookup:
                    updates["target_return_24h"] = close_lookup[ts_24h] / close_now - 1

                # target_realized_vol_4h: vol of next candle's H/L
                if ts_4h and ts_4h in close_lookup:
                    next_candle = next((c for c in candles_4h if c.timestamp == ts_4h), None)
                    if next_candle and float(next_candle.high) > 0 and float(next_candle.low) > 0:
                        h = float(next_candle.high)
                        l_val = float(next_candle.low)
                        if h != l_val:
                            updates["target_realized_vol_4h"] = math.sqrt(
                                math.log(h / l_val) ** 2 / (4 * math.log(2))
                            )

                # target_regime_24h
                if ts_24h and ts_24h in regime_lookup:
                    updates["target_regime_24h"] = regime_lookup[ts_24h]

                if updates:
                    stmt = (
                        update(MLFeatureRow)
                        .where(
                            MLFeatureRow.timestamp == ts,
                            MLFeatureRow.pair == pair,
                            MLFeatureRow.interval == self.PRIMARY_INTERVAL,
                        )
                        .values(**updates)
                    )
                    await session.execute(stmt)
                    filled += 1

        return filled


def _find_next_timestamp(
    sorted_timestamps: list[datetime], current_idx: int, steps: int
) -> datetime | None:
    """Find timestamp N steps ahead in sorted list."""
    target_idx = current_idx + steps
    if target_idx < len(sorted_timestamps):
        return sorted_timestamps[target_idx]
    return None
