"""ML feature store database models.

Two tables:
    - ``ml_features``: computed technical + derived features per (timestamp, pair, interval).
      TimescaleDB hypertable on timestamp.
    - ``ml_external_data``: external data (Fear & Greed, etc.) per (timestamp, source).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, TIMESTAMP, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from krakenbot.core.database import Base


class MLFeatureRow(Base):
    """ML feature vector for a single candle.

    Composite primary key: (timestamp, pair, interval).
    Designed as a TimescaleDB hypertable on ``timestamp``.
    All feature columns are nullable (None = indicator not warmed up).
    Target columns are NULL in live mode, computed retrospectively for training.
    """

    __tablename__ = "ml_features"

    # --- Primary key ---
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        primary_key=True,
        nullable=False,
        comment="Candle open timestamp (UTC)",
    )
    pair: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        nullable=False,
        comment="Trading pair (e.g., XBT/USDC)",
    )
    interval: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        nullable=False,
        comment="Candle interval in minutes (240 = 4h)",
    )

    # --- Price context (for normalization reference, NOT features) ---
    close_price: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=True,
        comment="Close price at this candle",
    )
    volume: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=True,
        comment="Volume at this candle",
    )

    # --- Trend & Regime features ---
    ema_spread_1h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="(EMA20-EMA50)/EMA50, 1h",
    )
    ema_spread_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="(EMA20-EMA50)/EMA50, 4h",
    )
    ema_spread_1d: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="(EMA20-EMA50)/EMA50, 1d",
    )
    supertrend_dist_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="(close - supertrend)/close, 4h",
    )
    supertrend_dir_4h: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="SuperTrend direction 4h: 1 or -1",
    )
    adx_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="ADX(14) 4h, 0-100",
    )
    adx_1d: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="ADX(14) 1d, 0-100",
    )
    macd_hist_1h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="MACD histogram / close, 1h",
    )
    macd_hist_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="MACD histogram / close, 4h",
    )
    rsi_14_1h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="RSI(14) 1h, 0-100",
    )
    rsi_14_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="RSI(14) 4h, 0-100",
    )
    rsi_14_1d: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="RSI(14) 1d, 0-100",
    )
    regime_1h: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Market regime 1h",
    )
    regime_4h: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Market regime 4h",
    )
    regime_1d: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Market regime 1d",
    )

    # --- Volatility features ---
    atr_ratio_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="ATR(14)/close, 4h",
    )
    atr_ratio_1d: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="ATR(14)/close, 1d",
    )
    bb_width_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Bollinger bandwidth, 4h",
    )
    bb_pctb_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Bollinger %B, 4h (0-1 inside bands)",
    )
    realized_vol_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Std of log returns, last 6x4h candles",
    )
    realized_vol_24h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Std of log returns, last 24x1h candles",
    )
    realized_vol_7d: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Std of log returns, last 42x4h candles",
    )
    parkinson_vol_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Parkinson vol estimator (high-low based)",
    )

    # --- Volume & Micro features ---
    volume_ratio_1h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Current volume / MA(20) volume, 1h",
    )
    volume_ratio_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Current volume / MA(20) volume, 4h",
    )
    vwap_deviation_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="(close - VWAP20) / close, 4h",
    )
    hl_ratio: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="(high - low) / close",
    )

    # --- Cyclic features ---
    hour_sin: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="sin(2*pi*hour/24)",
    )
    hour_cos: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="cos(2*pi*hour/24)",
    )
    dow_sin: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="sin(2*pi*day_of_week/7)",
    )
    dow_cos: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="cos(2*pi*day_of_week/7)",
    )
    month_sin: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="sin(2*pi*month/12)",
    )
    month_cos: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="cos(2*pi*month/12)",
    )

    # --- External data (forward-filled from ml_external_data) ---
    fear_greed_index: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Fear & Greed Index (0-100)",
    )

    # --- Targets (NULL in live, computed retrospectively for training) ---
    target_return_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="close[t+4h]/close[t] - 1",
    )
    target_return_24h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="close[t+24h]/close[t] - 1",
    )
    target_realized_vol_4h: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Realized vol over next 4h",
    )
    target_regime_24h: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Regime classification 24h ahead",
    )

    # --- Extensibility ---
    extra_features: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional features as JSON",
    )

    __table_args__ = (
        Index("ix_ml_features_pair_ts", "pair", "timestamp"),
        Index("ix_ml_features_pair_interval_ts", "pair", "interval", "timestamp"),
        {
            "comment": "ML feature vectors per candle (TimescaleDB hypertable)",
        },
    )


class MLExternalData(Base):
    """External data for ML features (Fear & Greed, etc.).

    Composite primary key: (timestamp, source).
    One row per day per source (most external APIs are daily).
    """

    __tablename__ = "ml_external_data"

    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        primary_key=True,
        nullable=False,
        comment="Data timestamp (UTC)",
    )
    source: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        nullable=False,
        comment="Data source (e.g., 'fear_greed')",
    )
    value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Primary numeric value",
    )
    value_classification: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Label (e.g., 'Extreme Fear', 'Greed')",
    )
    raw_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full raw response data",
    )

    __table_args__ = (
        Index("ix_ml_external_source_ts", "source", "timestamp"),
        {
            "comment": "External data sources for ML features",
        },
    )
