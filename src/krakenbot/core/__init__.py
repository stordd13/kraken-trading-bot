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
    # Database
    "Base",
    "ConfigurationError",
    "DataError",
    "DataPersistenceError",
    "DataValidationError",
    "DatabaseManager",
    "Event",
    # Event Bus
    "EventBus",
    "EventType",
    "InsufficientBalanceError",
    "InvalidConfigurationError",
    "KrakenAPIError",
    # Exceptions
    "KrakenBotError",
    "OrderCancelError",
    "OrderExecutionError",
    "RateLimitError",
    "RiskLimitExceededError",
    "TradingError",
    "WebSocketConnectionError",
    "WebSocketDisconnectedError",
    "WebSocketError",
    "WebSocketTimeoutError",
    "bind_context",
    "clear_context",
    "close_db",
    # Logger
    "configure_logging",
    "get_db_manager",
    "get_event_bus",
    "get_logger",
    "get_read_session",
    "get_session",
    "init_db",
    "reset_event_bus",
    "unbind_context",
]
