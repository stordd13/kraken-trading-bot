"""Tests for the logger module.

This module tests the structlog-based logging system including:
- Logger configuration
- Secret masking
- Context binding
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from krakenbot.core.logger import (
    _looks_like_secret,
    _mask_dict_secrets,
    _mask_value,
    add_app_context,
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    mask_secrets,
    unbind_context,
)


class TestSecretMasking:
    """Tests for secret masking functionality."""

    def test_mask_value_short_string(self) -> None:
        """Test that short strings are fully masked."""
        assert _mask_value("short") == "***"
        assert _mask_value("12345678") == "***"

    def test_mask_value_long_string(self) -> None:
        """Test that long strings show first/last characters."""
        result = _mask_value("this_is_a_very_long_secret_key_12345")
        assert result == "thi...345"

    def test_mask_value_none(self) -> None:
        """Test that None is masked as ***."""
        assert _mask_value(None) == "***"

    def test_looks_like_secret_short_string(self) -> None:
        """Test that short strings don't look like secrets."""
        assert _looks_like_secret("short") is False
        assert _looks_like_secret("12345") is False

    def test_looks_like_secret_api_key_pattern(self) -> None:
        """Test detection of API key patterns."""
        assert _looks_like_secret("api_key_abcdefghijklmnopqrstuvwxyz123") is True
        assert _looks_like_secret("my_api_secret_value_is_very_long") is True

    def test_looks_like_secret_base64_pattern(self) -> None:
        """Test detection of base64-like patterns."""
        # A long enough base64-like string should be detected
        assert _looks_like_secret("abcdefghijklmnopqrstuvwxyzABCDEF12") is True

    def test_looks_like_secret_normal_string(self) -> None:
        """Test that normal strings are not flagged as secrets."""
        assert _looks_like_secret("this is a normal sentence") is False
        assert _looks_like_secret("XBT/EUR trading pair name") is False

    def test_mask_dict_secrets_basic(self) -> None:
        """Test masking of secrets in a dictionary."""
        data = {
            "api_key": "secret_api_key_12345678901234567890",
            "name": "test",
            "password": "mypassword123",
        }
        result = _mask_dict_secrets(data)

        # Long strings (>8 chars) are masked as "xxx...xxx"
        assert result["api_key"] == "sec...890"  # Long value shows partial
        assert result["name"] == "test"  # Not a secret field
        assert result["password"] == "myp...123"  # Long password shows partial

    def test_mask_dict_secrets_nested(self) -> None:
        """Test masking of nested dictionaries."""
        data = {
            "config": {
                "api_key": "nested_secret_key",
                "host": "localhost",
            },
            "name": "test",
        }
        result = _mask_dict_secrets(data)

        # Long strings (>8 chars) are masked as "xxx...xxx"
        assert result["config"]["api_key"] == "nes...key"
        assert result["config"]["host"] == "localhost"
        assert result["name"] == "test"


class TestMaskSecretsProcessor:
    """Tests for the mask_secrets processor."""

    def test_mask_secrets_api_key_field(self) -> None:
        """Test that api_key fields are masked."""
        event_dict = {
            "api_key": "test_key",
            "message": "test",
        }
        result = mask_secrets(None, None, event_dict)  # type: ignore[arg-type]

        assert result["api_key"] == "***"
        assert result["message"] == "test"

    def test_mask_secrets_password_field(self) -> None:
        """Test that password fields are masked."""
        event_dict = {
            "password": "secret123",
            "user": "admin",
        }
        result = mask_secrets(None, None, event_dict)  # type: ignore[arg-type]

        # Password is > 8 chars so it shows partial masking
        assert result["password"] == "sec...123"
        assert result["user"] == "admin"

    def test_mask_secrets_preserves_normal_fields(self) -> None:
        """Test that normal fields are not modified."""
        event_dict = {
            "pair": "XBT/EUR",
            "price": 42000.0,
            "side": "buy",
        }
        result = mask_secrets(None, None, event_dict)  # type: ignore[arg-type]

        assert result == event_dict


class TestAddAppContext:
    """Tests for the add_app_context processor."""

    def test_add_app_context_with_pathname(self) -> None:
        """Test extraction of module from pathname."""
        event_dict = {
            "pathname": "/path/to/module.py",
            "message": "test",
        }
        result = add_app_context(None, None, event_dict)  # type: ignore[arg-type]

        assert result["module"] == "module.py"

    def test_add_app_context_with_func_name(self) -> None:
        """Test renaming of func_name to function."""
        event_dict = {
            "func_name": "test_function",
            "message": "test",
        }
        result = add_app_context(None, None, event_dict)  # type: ignore[arg-type]

        assert result["function"] == "test_function"
        assert "func_name" not in result


class TestConfigureLogging:
    """Tests for logging configuration."""

    def test_configure_logging_with_settings(self, mock_settings) -> None:
        """Test that logging can be configured with settings."""
        # This should not raise
        configure_logging(mock_settings)

        # Verify root logger has handler
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0

    def test_configure_logging_json_format(self, mock_settings) -> None:
        """Test JSON format configuration."""
        mock_settings.log_json = True
        configure_logging(mock_settings)

        # Logger should be configured without errors
        logger = get_logger("test")
        assert logger is not None

    def test_configure_logging_console_format(self, mock_settings) -> None:
        """Test console format configuration."""
        mock_settings.log_json = False
        configure_logging(mock_settings)

        # Logger should be configured without errors
        logger = get_logger("test")
        assert logger is not None


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_with_name(self) -> None:
        """Test getting a logger with a specific name."""
        logger = get_logger("test_module")
        assert logger is not None

    def test_get_logger_without_name(self) -> None:
        """Test getting a logger without a name."""
        logger = get_logger()
        assert logger is not None


class TestContextBinding:
    """Tests for context binding functions."""

    def test_bind_and_unbind_context(self) -> None:
        """Test binding and unbinding context variables."""
        # Clear any existing context
        clear_context()

        # Bind context
        bind_context(bot_id="test-bot", strategy="threshold")

        # Unbind specific key
        unbind_context("strategy")

        # Clear all context
        clear_context()

    def test_clear_context(self) -> None:
        """Test clearing all context variables."""
        bind_context(key1="value1", key2="value2")
        clear_context()
        # Should not raise even if context is empty
        clear_context()
