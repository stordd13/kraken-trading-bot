"""Core modules for KrakenBot.

This package contains foundational modules:
- logger: Structured logging with structlog
- database: Async SQLAlchemy with TimescaleDB support
- event_bus: Async pub/sub event system
- exceptions: Custom exception hierarchy
"""

from krakenbot.core.database import (
    Base,
    DatabaseManager,
    close_db,
    get_db_manager,
    get_read_session,
    get_session,
    init_db,
)
from krakenbot.core.event_bus import (
    Event,
    EventBus,
    EventType,
    get_event_bus,
    reset_event_bus,
)
from krakenbot.core.exceptions import (
    ConfigurationError,
    DataError,
    DataPersistenceError,
    DataValidationError,
    InsufficientBalanceError,
    InvalidConfigurationError,
    KrakenAPIError,
    KrakenBotError,
    OrderCancelError,
    OrderExecutionError,
    RateLimitError,
    RiskLimitExceededError,
    TradingError,
    WebSocketConnectionError,
    WebSocketDisconnectedError,
    WebSocketError,
    WebSocketTimeoutError,
)
from krakenbot.core.logger import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    unbind_context,
)

__all__ = [
    # Logger
    "configure_logging",
    "get_logger",
    "bind_context",
    "unbind_context",
    "clear_context",
    # Database
    "Base",
    "DatabaseManager",
    "get_db_manager",
    "init_db",
    "close_db",
    "get_session",
    "get_read_session",
    # Event Bus
    "EventBus",
    "Event",
    "EventType",
    "get_event_bus",
    "reset_event_bus",
    # Exceptions
    "KrakenBotError",
    "KrakenAPIError",
    "RateLimitError",
    "WebSocketError",
    "WebSocketConnectionError",
    "WebSocketDisconnectedError",
    "WebSocketTimeoutError",
    "TradingError",
    "InsufficientBalanceError",
    "RiskLimitExceededError",
    "OrderExecutionError",
    "OrderCancelError",
    "DataError",
    "DataValidationError",
    "DataPersistenceError",
    "ConfigurationError",
    "InvalidConfigurationError",
]
