"""Custom exceptions for KrakenBot.

This module defines a hierarchy of custom exceptions used throughout
the application for proper error handling and propagation.

Exception Hierarchy:
    KrakenBotError (base)
    ├── KrakenAPIError (API communication errors)
    ├── WebSocketError (WebSocket connection errors)
    │   ├── WebSocketConnectionError
    │   ├── WebSocketDisconnectedError
    │   └── WebSocketTimeoutError
    ├── TradingError (trading-related errors)
    │   ├── InsufficientBalanceError
    │   ├── RiskLimitExceededError
    │   ├── OrderExecutionError
    │   └── OrderCancelError
    ├── DataError (data-related errors)
    │   ├── DataValidationError
    │   └── DataPersistenceError
    └── ConfigurationError (configuration errors)
        └── InvalidConfigurationError
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from decimal import Decimal


class KrakenBotError(Exception):
    """Base exception for all KrakenBot errors.

    All custom exceptions in the application should inherit from this class.

    Attributes:
        message: Human-readable error description.
        details: Optional dictionary with additional error context.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            details: Optional dictionary with additional error context.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for logging.

        Returns:
            Dictionary representation of the error.
        """
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# =============================================================================
# API Errors
# =============================================================================


class KrakenAPIError(KrakenBotError):
    """Kraken API communication error.

    Raised when API calls fail or return unexpected responses.

    Attributes:
        status_code: HTTP status code if available.
        response: Raw API response if available.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the API error.

        Args:
            message: Error description.
            status_code: HTTP status code if available.
            response: Raw API response if available.
            details: Additional error context.
        """
        details = details or {}
        if status_code is not None:
            details["status_code"] = status_code
        if response is not None:
            details["response"] = response
        super().__init__(message, details)
        self.status_code = status_code
        self.response = response


class RateLimitError(KrakenAPIError):
    """Kraken API rate limit exceeded.

    Raised when API requests are rejected due to rate limiting.

    Attributes:
        retry_after: Seconds to wait before retrying.
    """

    def __init__(
        self,
        message: str = "API rate limit exceeded",
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the rate limit error.

        Args:
            message: Error description.
            retry_after: Seconds to wait before retrying.
            details: Additional error context.
        """
        details = details or {}
        if retry_after is not None:
            details["retry_after_seconds"] = retry_after
        super().__init__(message, status_code=429, details=details)
        self.retry_after = retry_after


# =============================================================================
# WebSocket Errors
# =============================================================================


class WebSocketError(KrakenBotError):
    """Base class for WebSocket-related errors.

    Raised when WebSocket operations fail.
    """

    pass


class WebSocketConnectionError(WebSocketError):
    """WebSocket connection failed.

    Raised when unable to establish a WebSocket connection.
    """

    def __init__(
        self,
        message: str = "Failed to connect to WebSocket",
        url: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the connection error.

        Args:
            message: Error description.
            url: WebSocket URL that failed.
            details: Additional error context.
        """
        details = details or {}
        if url is not None:
            details["url"] = url
        super().__init__(message, details)
        self.url = url


class WebSocketDisconnectedError(WebSocketError):
    """WebSocket unexpectedly disconnected.

    Raised when an established WebSocket connection is lost.
    """

    def __init__(
        self,
        message: str = "WebSocket connection lost",
        code: int | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the disconnection error.

        Args:
            message: Error description.
            code: WebSocket close code.
            reason: WebSocket close reason.
            details: Additional error context.
        """
        details = details or {}
        if code is not None:
            details["close_code"] = code
        if reason is not None:
            details["close_reason"] = reason
        super().__init__(message, details)
        self.code = code
        self.reason = reason


class WebSocketTimeoutError(WebSocketError):
    """WebSocket operation timed out.

    Raised when a WebSocket operation exceeds its timeout.
    """

    def __init__(
        self,
        message: str = "WebSocket operation timed out",
        timeout_seconds: float | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the timeout error.

        Args:
            message: Error description.
            timeout_seconds: Timeout duration that was exceeded.
            operation: The operation that timed out.
            details: Additional error context.
        """
        details = details or {}
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds
        if operation is not None:
            details["operation"] = operation
        super().__init__(message, details)
        self.timeout_seconds = timeout_seconds
        self.operation = operation


# =============================================================================
# Trading Errors
# =============================================================================


class TradingError(KrakenBotError):
    """Base class for trading-related errors."""

    pass


class InsufficientBalanceError(TradingError):
    """Insufficient balance for trade.

    Raised when an account doesn't have enough funds to execute a trade.
    """

    def __init__(
        self,
        message: str = "Insufficient balance",
        required: Decimal | None = None,
        available: Decimal | None = None,
        currency: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the insufficient balance error.

        Args:
            message: Error description.
            required: Amount required for the trade.
            available: Amount currently available.
            currency: Currency of the amounts.
            details: Additional error context.
        """
        details = details or {}
        if required is not None:
            details["required_amount"] = str(required)
        if available is not None:
            details["available_amount"] = str(available)
        if currency is not None:
            details["currency"] = currency
        super().__init__(message, details)
        self.required = required
        self.available = available
        self.currency = currency


class RiskLimitExceededError(TradingError):
    """Risk management limit exceeded.

    Raised when a trade would violate risk management rules.
    """

    def __init__(
        self,
        message: str = "Risk limit exceeded",
        limit_type: str | None = None,
        limit_value: Decimal | float | None = None,
        current_value: Decimal | float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the risk limit error.

        Args:
            message: Error description.
            limit_type: Type of limit that was exceeded.
            limit_value: The configured limit value.
            current_value: The current value that exceeded the limit.
            details: Additional error context.
        """
        details = details or {}
        if limit_type is not None:
            details["limit_type"] = limit_type
        if limit_value is not None:
            details["limit_value"] = str(limit_value)
        if current_value is not None:
            details["current_value"] = str(current_value)
        super().__init__(message, details)
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.current_value = current_value


class OrderExecutionError(TradingError):
    """Order execution failed.

    Raised when an order cannot be placed or executed.
    """

    def __init__(
        self,
        message: str = "Order execution failed",
        order_id: str | None = None,
        pair: str | None = None,
        side: str | None = None,
        amount: Decimal | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the order execution error.

        Args:
            message: Error description.
            order_id: Exchange order ID if available.
            pair: Trading pair.
            side: Order side (buy/sell).
            amount: Order amount.
            details: Additional error context.
        """
        details = details or {}
        if order_id is not None:
            details["order_id"] = order_id
        if pair is not None:
            details["pair"] = pair
        if side is not None:
            details["side"] = side
        if amount is not None:
            details["amount"] = str(amount)
        super().__init__(message, details)
        self.order_id = order_id
        self.pair = pair
        self.side = side
        self.amount = amount


class OrderCancelError(TradingError):
    """Order cancellation failed.

    Raised when an order cannot be cancelled.
    """

    def __init__(
        self,
        message: str = "Order cancellation failed",
        order_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the order cancel error.

        Args:
            message: Error description.
            order_id: Exchange order ID.
            details: Additional error context.
        """
        details = details or {}
        if order_id is not None:
            details["order_id"] = order_id
        super().__init__(message, details)
        self.order_id = order_id


# =============================================================================
# Data Errors
# =============================================================================


class DataError(KrakenBotError):
    """Base class for data-related errors."""

    pass


class DataValidationError(DataError):
    """Data validation failed.

    Raised when received data fails validation.
    """

    def __init__(
        self,
        message: str = "Data validation failed",
        field: str | None = None,
        expected: str | None = None,
        received: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the validation error.

        Args:
            message: Error description.
            field: Name of the field that failed validation.
            expected: Expected value or type.
            received: Actual received value.
            details: Additional error context.
        """
        details = details or {}
        if field is not None:
            details["field"] = field
        if expected is not None:
            details["expected"] = expected
        if received is not None:
            details["received"] = received
        super().__init__(message, details)
        self.field = field
        self.expected = expected
        self.received = received


class DataPersistenceError(DataError):
    """Data persistence failed.

    Raised when data cannot be saved to the database.
    """

    def __init__(
        self,
        message: str = "Failed to persist data",
        table: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the persistence error.

        Args:
            message: Error description.
            table: Database table involved.
            operation: Database operation that failed.
            details: Additional error context.
        """
        details = details or {}
        if table is not None:
            details["table"] = table
        if operation is not None:
            details["operation"] = operation
        super().__init__(message, details)
        self.table = table
        self.operation = operation


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(KrakenBotError):
    """Base class for configuration-related errors."""

    pass


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration.

    Raised when configuration values are invalid or incompatible.
    """

    def __init__(
        self,
        message: str = "Invalid configuration",
        setting: str | None = None,
        value: Any = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the configuration error.

        Args:
            message: Error description.
            setting: Name of the invalid setting.
            value: The invalid value.
            reason: Explanation of why it's invalid.
            details: Additional error context.
        """
        details = details or {}
        if setting is not None:
            details["setting"] = setting
        if value is not None:
            details["value"] = str(value)
        if reason is not None:
            details["reason"] = reason
        super().__init__(message, details)
        self.setting = setting
        self.value = value
        self.reason = reason
