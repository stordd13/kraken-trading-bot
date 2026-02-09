"""Application configuration using Pydantic Settings.

This module defines all configuration settings for the KrakenBot application.
Settings are loaded from environment variables with validation.
"""

from enum import Enum
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    """Trading mode enumeration."""

    PAPER = "paper"
    LIVE = "live"


class LogLevel(str, Enum):
    """Logging level enumeration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class KrakenSettings(BaseSettings):
    """Kraken API configuration."""

    model_config = SettingsConfigDict(env_prefix="KRAKEN_")

    api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Kraken API key",
    )
    api_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Kraken API secret",
    )
    api_url: str = Field(
        default="https://api.kraken.com",
        description="Kraken REST API base URL",
    )
    ws_url: str = Field(
        default="wss://ws.kraken.com",
        description="Kraken WebSocket URL",
    )
    ws_reconnect_delay_sec: int = Field(
        default=5,
        description="WebSocket reconnection delay in seconds",
        ge=1,
        le=60,
    )
    api_rate_limit_calls: int = Field(
        default=15,
        description="Maximum API calls per minute",
        ge=1,
        le=60,
    )


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: PostgresDsn = Field(
        default="postgresql+asyncpg://krakenbot:krakenbot@localhost:5432/krakenbot",
        description="Database connection URL",
    )
    echo: bool = Field(
        default=False,
        description="Echo SQL queries (dev only)",
    )
    pool_size: int = Field(
        default=5,
        description="Connection pool size",
        ge=1,
        le=20,
    )
    max_overflow: int = Field(
        default=10,
        description="Maximum overflow connections",
        ge=0,
        le=50,
    )


class RiskManagementSettings(BaseSettings):
    """Risk management configuration."""

    model_config = SettingsConfigDict(env_prefix="RISK_")

    max_position_pct: float = Field(
        default=5.0,
        description="Maximum position size as percentage of portfolio",
        ge=0.1,
        le=100.0,
    )
    daily_loss_limit_eur: float = Field(
        default=50.0,
        description="Daily loss limit in EUR",
        ge=0.0,
    )
    max_open_positions: int = Field(
        default=10,  # Increased from 3 to allow more positions
        description="Maximum number of simultaneous open positions",
        ge=1,
        le=20,  # Increased limit from 10 to 20
    )
    min_trade_interval_sec: int = Field(
        default=60,
        description="Minimum interval between trades in seconds",
        ge=10,
        le=3600,
    )
    emergency_stop_loss_pct: float = Field(
        default=10.0,
        description="Emergency stop-loss percentage",
        ge=1.0,
        le=50.0,
    )


class TradingSettings(BaseSettings):
    """Trading configuration."""

    model_config = SettingsConfigDict(env_prefix="TRADING_")

    mode: TradingMode = Field(
        default=TradingMode.PAPER,
        description="Trading mode (paper or live)",
    )
    pair: str = Field(
        default="XBT/USDC",  # Changed from XBT/EUR to match backtests
        description="Trading pair",
    )
    bot_instance_id: str = Field(
        default="",
        description="Unique identifier for this bot instance. If empty, uses strategy name only.",
    )
    default_order_amount_eur: float = Field(
        default=100.0,  # Increased from 15.0 for better profit potential
        description="Default order amount in EUR",
        ge=1.0,
        le=10000.0,
    )
    candle_interval_min: int = Field(
        default=15,
        description="Candle interval in minutes",
        ge=1,
        le=1440,
    )
    confirm_live: str = Field(
        default="no",
        description="Explicit confirmation for live trading (must be 'yes')",
    )

    @model_validator(mode="after")
    def validate_live_mode(self) -> "TradingSettings":
        """Ensure live mode requires explicit confirmation."""
        if self.mode == TradingMode.LIVE:
            if self.confirm_live.lower() != "yes":
                raise ValueError(
                    "Live trading requires TRADING_CONFIRM_LIVE=yes environment variable"
                )
        return self


class StrategySettings(BaseSettings):
    """Strategy configuration."""

    model_config = SettingsConfigDict(env_prefix="STRATEGY_")

    name: str = Field(
        default="threshold",
        description="Strategy name to use",
    )
    buy_threshold_pct: float = Field(
        default=-1.0,
        description="Buy threshold percentage (negative for price drop)",
        ge=-10.0,
        le=0.0,
    )
    sell_threshold_pct: float = Field(
        default=2.0,
        description="Sell threshold percentage (positive for price rise)",
        ge=0.0,
        le=20.0,
    )
    lookback_periods: int = Field(
        default=50,
        description="Number of candles to look back for analysis (50 x 15min = 12h30)",
        ge=1,
        le=10000,  # Allow up to 10000 for 7 days of 1-min candles
    )
    max_holding_minutes: int = Field(
        default=10080,  # 7 days = 7 * 24 * 60
        description="Maximum time to hold a position before forced exit (minutes)",
        ge=60,  # minimum 1 hour
        le=20160,  # maximum 14 days
    )


class TechnicalIndicatorSettings(BaseSettings):
    """Technical indicator strategy configuration."""

    model_config = SettingsConfigDict(env_prefix="TI_")

    # RSI settings
    rsi_period: int = Field(
        default=14,
        description="RSI calculation period",
        ge=5,
        le=50,
    )
    rsi_oversold: float = Field(
        default=30.0,
        description="RSI oversold threshold (BUY signal)",
        ge=10.0,
        le=40.0,
    )
    rsi_overbought: float = Field(
        default=70.0,
        description="RSI overbought threshold (SELL signal)",
        ge=60.0,
        le=90.0,
    )

    # MACD settings
    macd_fast: int = Field(
        default=12,
        description="MACD fast EMA period",
        ge=5,
        le=30,
    )
    macd_slow: int = Field(
        default=26,
        description="MACD slow EMA period",
        ge=15,
        le=60,
    )
    macd_signal: int = Field(
        default=9,
        description="MACD signal line period",
        ge=3,
        le=20,
    )

    # Bollinger Bands settings
    bb_period: int = Field(
        default=20,
        description="Bollinger Bands SMA period",
        ge=10,
        le=50,
    )
    bb_multiplier: float = Field(
        default=2.0,
        description="Bollinger Bands standard deviation multiplier",
        ge=1.0,
        le=3.0,
    )


class ScheduledTasksSettings(BaseSettings):
    """Scheduled data collection tasks configuration."""

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")

    enabled: bool = Field(
        default=True,
        description="Enable scheduled tasks",
    )

    timezone: str = Field(
        default="UTC",
        description="Timezone for cron schedules",
    )

    # Cron expression for daily OHLC backfill (all intervals)
    daily_backfill_cron: str = Field(
        default="0 2 * * *",  # 02:00 UTC daily
        description="Cron expression for daily OHLC backfill (all intervals)",
    )
    backfill_days: int = Field(
        default=1,
        description="Number of days to backfill each run",
        ge=1,
        le=30,
    )

    # Data collection settings
    pairs: list[str] = Field(
        default=["XBT/USDC", "XBT/EUR"],
        description="Trading pairs to collect data for",
    )
    intervals: list[int] = Field(
        default=[1, 5, 15, 60],
        description="OHLC intervals to collect (in minutes)",
    )
    batch_size: int = Field(
        default=1000,
        description="Bulk insert batch size",
        ge=100,
        le=10000,
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(
        default="KrakenBot",
        description="Application name",
    )
    environment: Literal["development", "production", "testing"] = Field(
        default="development",
        description="Application environment",
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Logging level",
    )
    log_json: bool = Field(
        default=True,
        description="Use JSON structured logging",
    )

    # Sub-settings
    kraken: KrakenSettings = Field(default_factory=KrakenSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    risk: RiskManagementSettings = Field(default_factory=RiskManagementSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    scheduler: ScheduledTasksSettings = Field(default_factory=ScheduledTasksSettings)
    technical_indicator: TechnicalIndicatorSettings = Field(
        default_factory=TechnicalIndicatorSettings
    )

    def validate_all(self) -> None:
        """Validate all settings and secrets at startup."""
        errors = []

        # Validate Kraken credentials in live mode
        if self.trading.mode == TradingMode.LIVE:
            if not self.kraken.api_key.get_secret_value():
                errors.append("KRAKEN_API_KEY is required for live trading")
            if not self.kraken.api_secret.get_secret_value():
                errors.append("KRAKEN_API_SECRET is required for live trading")

        # Validate database connection
        if not self.database.url:
            errors.append("DATABASE_URL is required")

        # Validate risk settings make sense
        if self.risk.emergency_stop_loss_pct <= self.strategy.sell_threshold_pct:
            errors.append("Emergency stop-loss must be greater than sell threshold")

        if errors:
            raise ValueError(
                "Configuration validation failed:\n" + "\n".join(f"- {e}" for e in errors)
            )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_live_trading(self) -> bool:
        """Check if live trading is enabled."""
        return self.trading.mode == TradingMode.LIVE


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance.

    Returns:
        The global Settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.validate_all()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings (useful for testing).

    Returns:
        A fresh Settings instance.
    """
    global _settings
    _settings = Settings()
    _settings.validate_all()
    return _settings
