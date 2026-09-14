"""Shared test fixtures for KrakenBot tests.

This module provides common fixtures used across all test modules including:
- Mock settings configurations
- Mock database sessions
- Sample market data
- Sample trade data
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    LogLevel,
    RiskManagementSettings,
    Settings,
    StrategySettings,
    TradingMode,
    TradingSettings,
)
from krakenbot.models.base import BotStatus, TradeSide, TradeStatus

#: Exchange credentials purged from os.environ for every test. ``_env_file=None`` only
#: disables pydantic-settings' dotenv source, never its environment source, so a key leaked
#: into os.environ (a script's ``load_dotenv`` executed at run time, or a developer shell
#: exporting it) would silently satisfy "credentials present" assertions.
_EXCHANGE_CREDENTIAL_VARS = (
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BYBIT_TRADE_API_KEY",
    "BYBIT_TRADE_API_SECRET",
    "KRAKEN_API_KEY",
    "KRAKEN_API_SECRET",
    "KRAKEN_FUTURES_API_KEY",
    "KRAKEN_FUTURES_API_SECRET",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
)


@pytest.fixture(autouse=True)
def _default_exchange_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin EXCHANGE_NAME and purge exchange credentials for every test.

    ``Settings.exchange_name`` is required (no default) since B1. Tests that build
    ``Settings(...)`` without it inherit Kraken here; tests targeting another
    exchange pass ``exchange_name=`` explicitly (kwargs beat env vars).

    The credential purge makes the suite order-independent and hermetic: no
    script may load ``.env`` at import time any more (B4.2), but ``runner.main()``
    is invoked at run time by the DB-gated tests and a developer shell may export
    keys. ``DATABASE_URL*`` is deliberately left alone (DB-gated tests need it).
    """
    monkeypatch.setenv("EXCHANGE_NAME", "kraken")
    for var in _EXCHANGE_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing.

    Returns:
        A Settings instance configured for testing.
    """
    settings = Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        log_level=LogLevel.DEBUG,
        log_json=False,
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
            echo=False,
            pool_size=2,
            max_overflow=2,
        ),
        risk=RiskManagementSettings(
            max_position_pct=5.0,
            daily_loss_limit_eur=50.0,
            max_open_positions=3,
            min_trade_interval_sec=60,
            emergency_stop_loss_pct=10.0,
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="XBT/EUR",
            default_order_amount_eur=15.0,
            candle_interval_min=15,
        ),
        strategy=StrategySettings(
            name="threshold",
            buy_threshold_pct=-1.0,
            sell_threshold_pct=2.0,
            lookback_periods=10,
        ),
    )
    return settings


@pytest.fixture
def mock_async_session() -> AsyncMock:
    """Create a mock async database session.

    Returns:
        A mock AsyncSession object.
    """
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    return session


@pytest.fixture
def sample_ohlc_data() -> list[dict]:
    """Create sample OHLC data for testing.

    Returns:
        List of OHLC data dictionaries.
    """
    base_timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    return [
        {
            "timestamp": base_timestamp,
            "pair": "XBT/EUR",
            "interval": 15,
            "open": Decimal("42000.00000000"),
            "high": Decimal("42500.00000000"),
            "low": Decimal("41800.00000000"),
            "close": Decimal("42300.00000000"),
            "volume": Decimal("10.50000000"),
            "vwap": Decimal("42150.00000000"),
            "trades_count": 150,
        },
        {
            "timestamp": datetime(2024, 1, 15, 12, 15, 0, tzinfo=UTC),
            "pair": "XBT/EUR",
            "interval": 15,
            "open": Decimal("42300.00000000"),
            "high": Decimal("42800.00000000"),
            "low": Decimal("42200.00000000"),
            "close": Decimal("42700.00000000"),
            "volume": Decimal("12.30000000"),
            "vwap": Decimal("42500.00000000"),
            "trades_count": 180,
        },
    ]


@pytest.fixture
def sample_tick_data() -> list[dict]:
    """Create sample tick data for testing.

    Returns:
        List of tick data dictionaries.
    """
    base_timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    return [
        {
            "timestamp": base_timestamp,
            "pair": "XBT/EUR",
            "sequence": 0,
            "price": Decimal("42000.00000000"),
            "volume": Decimal("0.10000000"),
            "side": TradeSide.BUY,
        },
        {
            "timestamp": base_timestamp,
            "pair": "XBT/EUR",
            "sequence": 1,
            "price": Decimal("42005.00000000"),
            "volume": Decimal("0.05000000"),
            "side": TradeSide.SELL,
        },
    ]


@pytest.fixture
def sample_trade_data() -> dict:
    """Create sample trade data for testing.

    Returns:
        Trade data dictionary.
    """
    return {
        "id": uuid.uuid4(),
        "timestamp": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        "pair": "XBT/EUR",
        "side": TradeSide.BUY,
        "amount": Decimal("0.00012000"),
        "price": Decimal("42000.00000000"),
        "fee": Decimal("0.01260000"),
        "fee_currency": "EUR",
        "strategy": "threshold",
        "pnl": None,
        "status": TradeStatus.FILLED,
        "order_id": "OXXXXX-XXXXX-XXXXXX",
    }


@pytest.fixture
def sample_bot_state_data() -> dict:
    """Create sample bot state data for testing.

    Returns:
        Bot state data dictionary.
    """
    return {
        "bot_id": "bot-threshold-001",
        "strategy": "threshold",
        "status": BotStatus.RUNNING,
        "position_size": Decimal("0.00012000"),
        "entry_price": Decimal("42000.00000000"),
        "daily_pnl": Decimal("1.50000000"),
        "total_pnl": Decimal("15.30000000"),
        "daily_trades_count": 3,
        "last_signal_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        "last_trade_at": datetime(2024, 1, 15, 11, 45, 0, tzinfo=UTC),
    }


@pytest.fixture
def mock_db_manager() -> Generator[MagicMock, None, None]:
    """Create a mock database manager.

    Yields:
        A patched database manager mock.
    """
    with patch("krakenbot.core.database._db_manager") as mock:
        manager = MagicMock()
        manager.is_initialized = True
        manager.session = AsyncMock()
        manager.read_session = AsyncMock()
        mock.return_value = manager
        yield manager


@pytest.fixture
def utc_now() -> datetime:
    """Get current UTC timestamp for testing.

    Returns:
        Current datetime with UTC timezone.
    """
    return datetime.now(UTC)
