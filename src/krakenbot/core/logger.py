"""Structured logging module using structlog.

This module provides a configured logger with:
- JSON and console output formats
- Automatic context (timestamp, module, function)
- Secret masking for API keys
- Integration with application settings
"""

from __future__ import annotations

import logging
import re
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.typing import EventDict, WrappedLogger

    from krakenbot.config.settings import Settings

# Pattern to detect potential secrets
SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?key|api[_-]?secret|password|token|secret)", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9+/]{32,}"),  # Base64-like strings
]

# Keywords that indicate a field might contain a secret
SECRET_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "api_key",
        "api_secret",
        "apikey",
        "apisecret",
        "password",
        "token",
        "secret",
        "credential",
        "credentials",
        "auth",
        "authorization",
        "private_key",
        "privatekey",
    }
)


def mask_secrets(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Mask sensitive values in log entries.

    This processor scans log event dictionaries for fields that might
    contain secrets and replaces their values with masked versions.

    Args:
        _logger: The wrapped logger instance (unused).
        _method_name: The logging method name (unused).
        event_dict: The event dictionary to process.

    Returns:
        The processed event dictionary with secrets masked.
    """
    for key, value in list(event_dict.items()):
        if key.lower() in SECRET_FIELD_NAMES or (
            isinstance(value, str) and _looks_like_secret(value)
        ):
            event_dict[key] = _mask_value(value)
        elif isinstance(value, dict):
            event_dict[key] = _mask_dict_secrets(value)
    return event_dict


def _mask_value(value: Any) -> str:
    """Mask a secret value, showing only first/last few characters.

    Args:
        value: The value to mask.

    Returns:
        Masked string representation.
    """
    if value is None:
        return "***"
    str_value = str(value)
    if len(str_value) <= 8:
        return "***"
    return f"{str_value[:3]}...{str_value[-3:]}"


def _looks_like_secret(value: str) -> bool:
    """Check if a string value looks like a secret.

    Args:
        value: The string to check.

    Returns:
        True if the value appears to be a secret.
    """
    if len(value) < 20:
        return False
    return any(pattern.search(value) for pattern in SECRET_PATTERNS)


def _mask_dict_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask secrets in a dictionary.

    Args:
        data: The dictionary to process.

    Returns:
        A new dictionary with secrets masked.
    """
    result = {}
    for key, value in data.items():
        if key.lower() in SECRET_FIELD_NAMES:
            result[key] = _mask_value(value)
        elif isinstance(value, dict):
            result[key] = _mask_dict_secrets(value)
        elif isinstance(value, str) and _looks_like_secret(value):
            result[key] = _mask_value(value)
        else:
            result[key] = value
    return result


def add_app_context(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Add application context to log entries.

    Adds module, function name, and line number information.

    Args:
        _logger: The wrapped logger instance (unused).
        _method_name: The logging method name (unused).
        event_dict: The event dictionary to process.

    Returns:
        The processed event dictionary with added context.
    """
    # Get call information from structlog if available
    if "pathname" in event_dict:
        event_dict["module"] = event_dict.get("pathname", "").split("/")[-1]
    if "func_name" in event_dict:
        event_dict["function"] = event_dict.pop("func_name")
    return event_dict


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structlog with appropriate processors and output format.

    This function sets up both structlog and the standard library logging
    to work together with consistent formatting.

    Args:
        settings: Application settings. If None, uses default configuration.
    """
    # Lazy import to avoid circular imports
    if settings is None:
        from krakenbot.config.settings import get_settings

        settings = get_settings()

    # Convert log level string to logging constant
    log_level = getattr(logging, settings.log_level.value, logging.INFO)

    # Common processors for both bound and stdlib loggers
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        mask_secrets,
        add_app_context,
    ]

    if settings.log_json:
        # JSON output for production/structured logging
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Console output for development
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Set up root handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Set specific logger levels
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.database.echo else logging.WARNING
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A configured BoundLogger instance.

    Example:
        >>> from krakenbot.core.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("trade_executed", pair="XBT/EUR", side="buy", amount=5.0)
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind context variables that will be included in all subsequent logs.

    This is useful for adding request IDs, user IDs, or other context
    that should appear in all logs within a scope.

    Args:
        **kwargs: Key-value pairs to bind to the logging context.

    Example:
        >>> bind_context(bot_id="bot-1", strategy="threshold")
        >>> logger.info("signal_generated")  # Will include bot_id and strategy
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Remove context variables from the logging context.

    Args:
        *keys: Names of keys to remove from the context.
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


# Module-level logger for internal use
_logger: structlog.stdlib.BoundLogger | None = None


def _get_module_logger() -> structlog.stdlib.BoundLogger:
    """Get the module-level logger, initializing if needed.

    Returns:
        The module logger instance.
    """
    global _logger
    if _logger is None:
        _logger = get_logger(__name__)
    return _logger
