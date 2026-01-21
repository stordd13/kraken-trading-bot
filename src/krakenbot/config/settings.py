"""Application configuration using Pydantic Settings.

This module defines all configuration settings for the KrakenBot application.
Settings are loaded from environment variables with validation.
"""

from enum import Enum
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
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

    @field_validator("mode")
    @classmethod
    def validate_live_mode(cls, v: TradingMode, info) -> TradingMode:
        """Ensure live mode requires explicit confirmation."""
        if v == TradingMode.LIVE:
            confirm = info.data.get("confirm_live", "no")
            if confirm.lower() != "yes":
                raise ValueError(
                    "Live trading requires TRADING_CONFIRM_LIVE=yes environment variable"
                )
        return v


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
        default=10,
        description="Number of candles to look back for analysis",
        ge=1,
        le=100,
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

    # Cron expressions for scheduled jobs
    daily_1min_cron: str = Field(
        default="0 2 * * *",  # 02:00 UTC daily
        description="Cron expression for 1min OHLC collection",
    )
    daily_5min_cron: str = Field(
        default="15 2 * * *",  # 02:15 UTC daily
        description="Cron expression for 5min OHLC collection",
    )
    weekly_15min_cron: str = Field(
        default="0 3 * * 1",  # 03:00 UTC Mondays
        description="Cron expression for 15min OHLC collection",
    )
    monthly_1h_cron: str = Field(
        default="0 4 1 * *",  # 04:00 UTC 1st of month
        description="Cron expression for 1h OHLC collection",
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
            errors.append(
                "Emergency stop-loss must be greater than sell threshold"
            )

        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f"- {e}" for e in errors))

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
