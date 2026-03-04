"""add ml_features and ml_external_data tables

Revision ID: da05b87b4016
Revises: e1f2a3b4c5d6
Create Date: 2026-03-04 15:37:51.439495
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "da05b87b4016"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ML feature store tables."""
    # --- ml_external_data ---
    op.create_table(
        "ml_external_data",
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Data timestamp (UTC)",
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            comment="Data source (e.g., 'fear_greed')",
        ),
        sa.Column(
            "value",
            sa.Float(),
            nullable=True,
            comment="Primary numeric value",
        ),
        sa.Column(
            "value_classification",
            sa.String(length=50),
            nullable=True,
            comment="Label (e.g., 'Extreme Fear', 'Greed')",
        ),
        sa.Column(
            "raw_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Full raw response data",
        ),
        sa.PrimaryKeyConstraint("timestamp", "source"),
        comment="External data sources for ML features",
    )
    op.create_index(
        "ix_ml_external_source_ts",
        "ml_external_data",
        ["source", "timestamp"],
        unique=False,
    )

    # --- ml_features ---
    op.create_table(
        "ml_features",
        # Primary key
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            comment="Candle open timestamp (UTC)",
        ),
        sa.Column(
            "pair",
            sa.String(length=20),
            nullable=False,
            comment="Trading pair (e.g., XBT/USDC)",
        ),
        sa.Column(
            "interval",
            sa.Integer(),
            nullable=False,
            comment="Candle interval in minutes (240 = 4h)",
        ),
        # Price context
        sa.Column(
            "close_price",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Close price at this candle",
        ),
        sa.Column(
            "volume",
            sa.DECIMAL(precision=18, scale=8),
            nullable=True,
            comment="Volume at this candle",
        ),
        # Trend & Regime
        sa.Column("ema_spread_1h", sa.Float(), nullable=True, comment="(EMA20-EMA50)/EMA50, 1h"),
        sa.Column("ema_spread_4h", sa.Float(), nullable=True, comment="(EMA20-EMA50)/EMA50, 4h"),
        sa.Column("ema_spread_1d", sa.Float(), nullable=True, comment="(EMA20-EMA50)/EMA50, 1d"),
        sa.Column(
            "supertrend_dist_4h",
            sa.Float(),
            nullable=True,
            comment="(close - supertrend)/close, 4h",
        ),
        sa.Column(
            "supertrend_dir_4h",
            sa.Integer(),
            nullable=True,
            comment="SuperTrend direction 4h: 1 or -1",
        ),
        sa.Column("adx_4h", sa.Float(), nullable=True, comment="ADX(14) 4h, 0-100"),
        sa.Column("adx_1d", sa.Float(), nullable=True, comment="ADX(14) 1d, 0-100"),
        sa.Column(
            "macd_hist_1h", sa.Float(), nullable=True, comment="MACD histogram / close, 1h"
        ),
        sa.Column(
            "macd_hist_4h", sa.Float(), nullable=True, comment="MACD histogram / close, 4h"
        ),
        sa.Column("rsi_14_1h", sa.Float(), nullable=True, comment="RSI(14) 1h, 0-100"),
        sa.Column("rsi_14_4h", sa.Float(), nullable=True, comment="RSI(14) 4h, 0-100"),
        sa.Column("rsi_14_1d", sa.Float(), nullable=True, comment="RSI(14) 1d, 0-100"),
        sa.Column("regime_1h", sa.String(length=20), nullable=True, comment="Market regime 1h"),
        sa.Column("regime_4h", sa.String(length=20), nullable=True, comment="Market regime 4h"),
        sa.Column("regime_1d", sa.String(length=20), nullable=True, comment="Market regime 1d"),
        # Volatility
        sa.Column("atr_ratio_4h", sa.Float(), nullable=True, comment="ATR(14)/close, 4h"),
        sa.Column("atr_ratio_1d", sa.Float(), nullable=True, comment="ATR(14)/close, 1d"),
        sa.Column(
            "bb_width_4h", sa.Float(), nullable=True, comment="Bollinger bandwidth, 4h"
        ),
        sa.Column(
            "bb_pctb_4h",
            sa.Float(),
            nullable=True,
            comment="Bollinger %B, 4h (0-1 inside bands)",
        ),
        sa.Column(
            "realized_vol_4h",
            sa.Float(),
            nullable=True,
            comment="Std of log returns, last 6x4h candles",
        ),
        sa.Column(
            "realized_vol_24h",
            sa.Float(),
            nullable=True,
            comment="Std of log returns, last 24x1h candles",
        ),
        sa.Column(
            "realized_vol_7d",
            sa.Float(),
            nullable=True,
            comment="Std of log returns, last 42x4h candles",
        ),
        sa.Column(
            "parkinson_vol_4h",
            sa.Float(),
            nullable=True,
            comment="Parkinson vol estimator (high-low based)",
        ),
        # Volume & Micro
        sa.Column(
            "volume_ratio_1h",
            sa.Float(),
            nullable=True,
            comment="Current volume / MA(20) volume, 1h",
        ),
        sa.Column(
            "volume_ratio_4h",
            sa.Float(),
            nullable=True,
            comment="Current volume / MA(20) volume, 4h",
        ),
        sa.Column(
            "vwap_deviation_4h",
            sa.Float(),
            nullable=True,
            comment="(close - VWAP20) / close, 4h",
        ),
        sa.Column("hl_ratio", sa.Float(), nullable=True, comment="(high - low) / close"),
        # Cyclic
        sa.Column("hour_sin", sa.Float(), nullable=True, comment="sin(2*pi*hour/24)"),
        sa.Column("hour_cos", sa.Float(), nullable=True, comment="cos(2*pi*hour/24)"),
        sa.Column("dow_sin", sa.Float(), nullable=True, comment="sin(2*pi*day_of_week/7)"),
        sa.Column("dow_cos", sa.Float(), nullable=True, comment="cos(2*pi*day_of_week/7)"),
        sa.Column("month_sin", sa.Float(), nullable=True, comment="sin(2*pi*month/12)"),
        sa.Column("month_cos", sa.Float(), nullable=True, comment="cos(2*pi*month/12)"),
        # External data
        sa.Column(
            "fear_greed_index",
            sa.Float(),
            nullable=True,
            comment="Fear & Greed Index (0-100)",
        ),
        # Targets (NULL in live)
        sa.Column(
            "target_return_4h",
            sa.Float(),
            nullable=True,
            comment="close[t+4h]/close[t] - 1",
        ),
        sa.Column(
            "target_return_24h",
            sa.Float(),
            nullable=True,
            comment="close[t+24h]/close[t] - 1",
        ),
        sa.Column(
            "target_realized_vol_4h",
            sa.Float(),
            nullable=True,
            comment="Realized vol over next 4h",
        ),
        sa.Column(
            "target_regime_24h",
            sa.String(length=20),
            nullable=True,
            comment="Regime classification 24h ahead",
        ),
        # Extensibility
        sa.Column(
            "extra_features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Additional features as JSON",
        ),
        sa.PrimaryKeyConstraint("timestamp", "pair", "interval"),
        comment="ML feature vectors per candle (TimescaleDB hypertable)",
    )
    op.create_index(
        "ix_ml_features_pair_interval_ts",
        "ml_features",
        ["pair", "interval", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_ml_features_pair_ts",
        "ml_features",
        ["pair", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Drop ML feature store tables."""
    op.drop_index("ix_ml_features_pair_ts", table_name="ml_features")
    op.drop_index("ix_ml_features_pair_interval_ts", table_name="ml_features")
    op.drop_table("ml_features")
    op.drop_index("ix_ml_external_source_ts", table_name="ml_external_data")
    op.drop_table("ml_external_data")
