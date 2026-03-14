"""Application configuration using Pydantic Settings.

This module defines all configuration settings for the KrakenBot application.
Settings are loaded from environment variables with validation.
"""

from __future__ import annotations

from enum import Enum
import logging
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml

from krakenbot.ml.config import MLSettings

_ROUTER_PARAM_KEYS = frozenset({"capital_usdc", "risk", "strategies"})
_ROUTER_INNER_STRATEGY_KEYS = frozenset({"active", "bot_id", "params"})


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
    def validate_live_mode(self) -> TradingSettings:
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
        default=[1, 5, 15, 60, 240, 1440, 10080],
        description="OHLC intervals to collect (in minutes)",
    )
    batch_size: int = Field(
        default=1000,
        description="Bulk insert batch size",
        ge=100,
        le=10000,
    )


class StrategyBudget(BaseModel):
    """Per-strategy budget and risk allocation."""

    max_open_positions: int = Field(default=5, ge=1, le=50)
    daily_loss_limit_eur: float = Field(default=25.0, ge=0.0)
    max_position_pct: float = Field(default=5.0, ge=0.1, le=100.0)
    position_size_multiplier: float = Field(default=1.0, ge=0.1, le=10.0)


class StrategyInstanceConfig(BaseModel):
    """Configuration for a single strategy instance."""

    name: str
    enabled: bool = True
    bot_id: str
    budget: StrategyBudget = Field(default_factory=StrategyBudget)
    params: dict[str, Any] = Field(default_factory=dict)
    dashboard: dict[str, Any] = Field(default_factory=dict)


class MultiStrategySettings(BaseSettings):
    """Multi-strategy orchestration settings."""

    model_config = SettingsConfigDict(env_prefix="MULTI_STRATEGY_")

    enabled: bool = Field(
        default=False,
        description="Enable multi-strategy mode. False = legacy single strategy.",
    )
    strategies: list[StrategyInstanceConfig] = Field(default_factory=list)
    global_max_open_positions: int = Field(default=10, ge=1, le=50)
    global_daily_loss_limit_eur: float = Field(default=50.0, ge=0.0)
    global_max_portfolio_exposure_pct: float = Field(default=30.0, ge=1.0, le=100.0)


class MultiTimeframeSettings(BaseSettings):
    """Multi-timeframe analysis settings."""

    model_config = SettingsConfigDict(env_prefix="MTF_")

    enabled: bool = Field(default=True, description="Enable multi-timeframe analysis")
    trend_timeframe: int = Field(default=60, description="Trend timeframe in minutes (1h)")
    zone_timeframe: int = Field(default=15, description="Zone timeframe in minutes")
    trigger_timeframe: int = Field(default=5, description="Trigger timeframe in minutes")
    ema_fast_period: int = Field(default=20, ge=5, le=100)
    ema_slow_period: int = Field(default=50, ge=10, le=200)
    atr_period: int = Field(default=14, ge=5, le=50)
    regime_neutral_threshold: float = Field(
        default=0.5,
        description="EMA spread threshold (%) to distinguish neutral from trend",
    )
    warmup_candles_1h: int = Field(default=50, ge=10, le=200)


class CapitulationSettings(BaseSettings):
    """Capitulation strategy specific settings."""

    model_config = SettingsConfigDict(env_prefix="CAPITULATION_")

    rsi_1h_threshold: float = Field(default=20.0, ge=5.0, le=40.0)
    rsi_5m_threshold: float = Field(default=15.0, ge=5.0, le=40.0)
    volume_spike_multiplier: float = Field(default=3.0, ge=1.5, le=10.0)
    trailing_stop_pct: float = Field(default=5.0, ge=0.5, le=10.0)
    max_profit_target_pct: float = Field(default=10.0, ge=2.0, le=50.0)
    max_holding_minutes: int = Field(default=2880, ge=60, le=20160)
    cooldown_hours: int = Field(default=4, ge=1, le=48)


class CommonIndicatorsSettings(BaseModel):
    """Common indicators configuration for the shared data layer.

    These defaults apply to all timeframes in the MultiTimeframeAnalyzer
    generic registry. Override via the common_indicators section in
    strategies.yaml.
    """

    timeframes: list[str] = Field(
        default=["5m", "15m", "1h", "4h", "1d", "1w"],
        description="Timeframes to track indicators for",
    )
    ema_fast_period: int = Field(default=20, ge=5, le=200)
    ema_slow_period: int = Field(default=50, ge=10, le=400)
    rsi_default_period: int = Field(default=14, ge=5, le=50)
    atr_default_period: int = Field(default=14, ge=5, le=50)
    bb_default_period: int = Field(default=20, ge=5, le=50)
    adx_period: int = Field(default=14, ge=5, le=50)


class PaperSettings(BaseSettings):
    """Paper trading configuration."""

    model_config = SettingsConfigDict(env_prefix="PAPER_")

    balance_reset: bool = Field(
        default=False,
        description="Force re-fetch real Kraken balance on next startup",
    )


class OrderSettings(BaseSettings):
    """Order execution settings (limit vs market)."""

    model_config = SettingsConfigDict(env_prefix="ORDER_")

    default_order_type: str = Field(
        default="limit",
        description="Default order type: 'limit' or 'market'",
    )
    limit_buy_offset_pct: float = Field(
        default=0.05,
        description="Place limit buy this % below current price to ensure maker",
        ge=0.0,
        le=1.0,
    )
    limit_order_expiry_minutes: int = Field(
        default=15,
        description="Cancel limit orders after this many minutes",
        ge=1,
        le=1440,
    )
    check_interval_seconds: int = Field(
        default=30,
        description="How often to check pending order status",
        ge=5,
        le=300,
    )
    profit_target_as_limit: bool = Field(
        default=True,
        description="Place profit target SELL as limit order",
    )
    stop_loss_as_market: bool = Field(
        default=True,
        description="Always use market order for stop-loss (guaranteed execution)",
    )


def _load_strategies_yaml() -> dict[str, Any] | None:
    """Load strategies.yaml from project root if it exists.

    Returns:
        Parsed YAML dict or None if file doesn't exist.
    """
    # Search in current dir and parent dirs up to 3 levels
    for parent in [Path.cwd()] + list(Path.cwd().parents)[:3]:
        yaml_path = parent / "strategies.yaml"
        if yaml_path.exists():
            with open(yaml_path) as f:
                return yaml.safe_load(f)
    return None


def _get_supported_router_inner_strategy_names() -> set[str]:
    """Return the inner strategy names actually supported by the runtime router."""
    from krakenbot.strategies.multi_strategy_router import _INNER_STRATEGY_CLASSES

    return set(_INNER_STRATEGY_CLASSES.keys())


def _validate_router_runtime_alignment(
    multi_strategy: MultiStrategySettings,
) -> tuple[list[str], list[str]]:
    """Validate router config against what the runtime actually consumes."""
    errors: list[str] = []
    warnings: list[str] = []

    supported_inner_strategies = _get_supported_router_inner_strategy_names()

    for strat_config in multi_strategy.strategies:
        if not strat_config.enabled or strat_config.name != "multi_strategy_router":
            continue

        router_params = strat_config.params
        ignored_router_fields = sorted(set(router_params) - _ROUTER_PARAM_KEYS)
        if ignored_router_fields:
            warnings.append(
                f"Router '{strat_config.bot_id}' has ignored runtime params: "
                f"{', '.join(ignored_router_fields)}"
            )

        inner_configs = router_params.get("strategies", {})
        if not isinstance(inner_configs, dict):
            continue

        for inner_name, inner_cfg in inner_configs.items():
            if not isinstance(inner_cfg, dict):
                continue

            is_active = bool(inner_cfg.get("active", True))

            if is_active and inner_name not in supported_inner_strategies:
                errors.append(
                    f"Router inner strategy '{inner_name}' is active in strategies.yaml "
                    "but not supported by the runtime"
                )

            ignored_inner_fields = sorted(set(inner_cfg) - _ROUTER_INNER_STRATEGY_KEYS)
            if is_active and ignored_inner_fields:
                warnings.append(
                    f"Router inner strategy '{inner_name}' has ignored runtime fields: "
                    f"{', '.join(ignored_inner_fields)}"
                )

    return errors, warnings


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
    multi_strategy: MultiStrategySettings = Field(default_factory=MultiStrategySettings)
    multi_timeframe: MultiTimeframeSettings = Field(default_factory=MultiTimeframeSettings)
    capitulation: CapitulationSettings = Field(default_factory=CapitulationSettings)
    order: OrderSettings = Field(default_factory=OrderSettings)
    paper: PaperSettings = Field(default_factory=PaperSettings)
    common_indicators: CommonIndicatorsSettings = Field(default_factory=CommonIndicatorsSettings)

    # ML settings (loaded from strategies.yaml ml: section)
    ml: MLSettings = Field(default_factory=lambda: MLSettings())

    def model_post_init(self, __context: Any) -> None:
        """Load strategies.yaml after settings init."""
        # Skip YAML loading in testing environment
        if self.environment == "testing":
            return
        yaml_data = _load_strategies_yaml()
        if yaml_data and yaml_data.get("enabled", False):
            strategies_list = []
            for s in yaml_data.get("strategies", []):
                strategies_list.append(StrategyInstanceConfig(**s))
            self.multi_strategy = MultiStrategySettings(
                enabled=True,
                strategies=strategies_list,
                global_max_open_positions=yaml_data.get("global_max_open_positions", 10),
                global_daily_loss_limit_eur=yaml_data.get("global_daily_loss_limit_eur", 50.0),
                global_max_portfolio_exposure_pct=yaml_data.get(
                    "global_max_portfolio_exposure_pct", 30.0
                ),
            )
            # Parse common_indicators section if present
            ci_data = yaml_data.get("common_indicators")
            if ci_data and isinstance(ci_data, dict):
                self.common_indicators = CommonIndicatorsSettings(**ci_data)

            # Parse ml section if present
            ml_data = yaml_data.get("ml")
            if ml_data and isinstance(ml_data, dict):
                self.ml = MLSettings(**ml_data)

            logging.getLogger(__name__).info(
                "Loaded strategies.yaml: %d strategies enabled",
                len([s for s in strategies_list if s.enabled]),
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

        # Validate multi-strategy budgets don't exceed global limits
        if self.multi_strategy.enabled:
            total_positions = sum(
                s.budget.max_open_positions for s in self.multi_strategy.strategies if s.enabled
            )
            total_loss = sum(
                s.budget.daily_loss_limit_eur for s in self.multi_strategy.strategies if s.enabled
            )
            if total_positions > self.multi_strategy.global_max_open_positions:
                errors.append(
                    f"Sum of per-strategy max_open_positions ({total_positions}) exceeds "
                    f"global limit ({self.multi_strategy.global_max_open_positions})"
                )
            if total_loss > self.multi_strategy.global_daily_loss_limit_eur:
                errors.append(
                    f"Sum of per-strategy daily_loss_limit ({total_loss}) exceeds "
                    f"global limit ({self.multi_strategy.global_daily_loss_limit_eur})"
                )

            router_errors, router_warnings = _validate_router_runtime_alignment(
                self.multi_strategy
            )
            errors.extend(router_errors)

            settings_logger = logging.getLogger(__name__)
            for warning in router_warnings:
                settings_logger.warning(warning)

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
        # Load .env into OS environment so nested BaseSettings models
        # (DatabaseSettings, KrakenSettings, etc.) can read their env vars.
        # Without this, only the root Settings reads .env via Pydantic's env_file.
        load_dotenv()
        _settings = Settings()
        _settings.validate_all()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings (useful for testing).

    Returns:
        A fresh Settings instance.
    """
    global _settings
    load_dotenv(override=True)
    _settings = Settings()
    _settings.validate_all()
    return _settings
