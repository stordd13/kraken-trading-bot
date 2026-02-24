"""Tests for the database module.

This module tests the async database functionality including:
- Database manager initialization
- Session management
- Connection handling
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.core.database import (
    Base,
    DatabaseManager,
    get_db_manager,
    reset_db_manager,
)


class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    def test_initial_state(self) -> None:
        """Test that manager starts uninitialized."""
        manager = DatabaseManager()
        assert manager.is_initialized is False

    def test_engine_raises_when_not_initialized(self) -> None:
        """Test that accessing engine raises when not initialized."""
        manager = DatabaseManager()
        with pytest.raises(RuntimeError, match="Database not initialized"):
            _ = manager.engine

    def test_session_factory_raises_when_not_initialized(self) -> None:
        """Test that accessing session_factory raises when not initialized."""
        manager = DatabaseManager()
        with pytest.raises(RuntimeError, match="Database not initialized"):
            _ = manager.session_factory

    @pytest.mark.asyncio
    async def test_init_db_creates_engine(self, mock_settings) -> None:
        """Test that init_db creates engine and session factory."""
        manager = DatabaseManager()

        with patch("krakenbot.core.database.create_async_engine") as mock_create_engine:
            # Create a mock engine
            mock_engine = MagicMock()

            # Create async context manager for begin()
            mock_connection = AsyncMock()
            mock_connection.execute = AsyncMock()

            # Use AsyncMock for the context manager
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_connection)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_engine.begin.return_value = mock_context

            mock_create_engine.return_value = mock_engine

            await manager.init_db(mock_settings)

            # Verify engine was created with correct parameters
            mock_create_engine.assert_called_once()
            call_kwargs = mock_create_engine.call_args[1]
            assert call_kwargs["pool_size"] == mock_settings.database.pool_size
            assert call_kwargs["max_overflow"] == mock_settings.database.max_overflow

    @pytest.mark.asyncio
    async def test_init_db_idempotent(self, mock_settings) -> None:
        """Test that init_db can be called multiple times safely."""
        manager = DatabaseManager()

        with patch("krakenbot.core.database.create_async_engine") as mock_create_engine:
            mock_engine = MagicMock()

            mock_connection = AsyncMock()
            mock_connection.execute = AsyncMock()

            # Use AsyncMock for the context manager
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_connection)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_engine.begin.return_value = mock_context

            mock_create_engine.return_value = mock_engine

            await manager.init_db(mock_settings)

            # Force initialized state
            manager._initialized = True

            # Second call should return early
            await manager.init_db(mock_settings)

            # Engine should only be created once
            assert mock_create_engine.call_count == 1

    @pytest.mark.asyncio
    async def test_close_db_disposes_engine(self) -> None:
        """Test that close_db disposes the engine."""
        manager = DatabaseManager()

        mock_engine = AsyncMock()
        manager._engine = mock_engine
        manager._initialized = True

        await manager.close_db()

        mock_engine.dispose.assert_called_once()
        assert manager._engine is None
        assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_close_db_not_initialized(self) -> None:
        """Test that close_db handles uninitialized state."""
        manager = DatabaseManager()

        # Should not raise
        await manager.close_db()


class TestSessionContextManager:
    """Tests for session context managers."""

    @pytest.mark.asyncio
    async def test_session_commits_on_success(self) -> None:
        """Test that session commits on successful execution."""
        manager = DatabaseManager()

        mock_session = AsyncMock()
        mock_session_factory = MagicMock(return_value=mock_session)
        manager._session_factory = mock_session_factory
        manager._initialized = True

        async with manager.session() as session:
            pass  # Simulate successful operation

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_rollbacks_on_error(self) -> None:
        """Test that session rollbacks on error."""
        manager = DatabaseManager()

        mock_session = AsyncMock()
        mock_session_factory = MagicMock(return_value=mock_session)
        manager._session_factory = mock_session_factory
        manager._initialized = True

        with pytest.raises(ValueError):
            async with manager.session() as session:
                raise ValueError("Test error")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_session_no_commit(self) -> None:
        """Test that read session doesn't commit."""
        manager = DatabaseManager()

        mock_session = AsyncMock()
        mock_session_factory = MagicMock(return_value=mock_session)
        manager._session_factory = mock_session_factory
        manager._initialized = True

        async with manager.read_session() as session:
            pass

        mock_session.commit.assert_not_called()
        mock_session.close.assert_called_once()


class TestTimescaleDBSupport:
    """Tests for TimescaleDB support functions."""

    @pytest.mark.asyncio
    async def test_setup_timescaledb(self) -> None:
        """Test TimescaleDB extension setup."""
        manager = DatabaseManager()

        mock_engine = MagicMock()
        mock_connection = AsyncMock()
        mock_connection.execute = AsyncMock()

        # Use AsyncMock for the context manager
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_engine.begin.return_value = mock_context

        manager._engine = mock_engine
        manager._initialized = True

        await manager.setup_timescaledb()

        mock_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_hypertable(self) -> None:
        """Test hypertable creation."""
        manager = DatabaseManager()

        mock_engine = MagicMock()
        mock_connection = AsyncMock()
        mock_connection.execute = AsyncMock()

        # Use AsyncMock for the context manager
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_engine.begin.return_value = mock_context

        manager._engine = mock_engine
        manager._initialized = True

        await manager.create_hypertable(
            table_name="market_data_ohlc",
            time_column="timestamp",
            chunk_interval="1 day",
        )

        mock_connection.execute.assert_called_once()


class TestGlobalDatabaseManager:
    """Tests for global database manager functions."""

    def test_get_db_manager_creates_singleton(self) -> None:
        """Test that get_db_manager returns the same instance."""
        reset_db_manager()

        manager1 = get_db_manager()
        manager2 = get_db_manager()

        assert manager1 is manager2

    def test_reset_db_manager(self) -> None:
        """Test that reset_db_manager clears the singleton."""
        reset_db_manager()

        manager1 = get_db_manager()
        reset_db_manager()
        manager2 = get_db_manager()

        assert manager1 is not manager2


class TestBase:
    """Tests for SQLAlchemy Base class."""

    def test_base_is_declarative_base(self) -> None:
        """Test that Base is a valid declarative base."""
        # Check that Base has metadata (required for declarative base)
        assert hasattr(Base, "metadata")
        # Check that Base has registry (required for SQLAlchemy 2.0 declarative base)
        assert hasattr(Base, "registry")
