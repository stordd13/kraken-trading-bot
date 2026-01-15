"""Async database module with SQLAlchemy and TimescaleDB support.

This module provides:
- Async SQLAlchemy engine and session factory
- Connection pool management
- TimescaleDB hypertable support
- Context managers for database sessions
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings

from krakenbot.core.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models.

    All database models should inherit from this class to be properly
    registered with SQLAlchemy and Alembic migrations.
    """

    pass


class DatabaseManager:
    """Manages database connections, sessions, and lifecycle.

    This class provides a centralized interface for all database operations
    including connection pooling, session management, and TimescaleDB setup.

    Attributes:
        engine: The async SQLAlchemy engine.
        session_factory: Factory for creating async sessions.
    """

    def __init__(self) -> None:
        """Initialize the database manager with no active connections."""
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._initialized: bool = False

    @property
    def engine(self) -> AsyncEngine:
        """Get the async engine, raising if not initialized.

        Returns:
            The async SQLAlchemy engine.

        Raises:
            RuntimeError: If the database has not been initialized.
        """
        if self._engine is None:
            raise RuntimeError(
                "Database not initialized. Call init_db() first."
            )
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory, raising if not initialized.

        Returns:
            The async session factory.

        Raises:
            RuntimeError: If the database has not been initialized.
        """
        if self._session_factory is None:
            raise RuntimeError(
                "Database not initialized. Call init_db() first."
            )
        return self._session_factory

    @property
    def is_initialized(self) -> bool:
        """Check if the database has been initialized.

        Returns:
            True if init_db() has been called successfully.
        """
        return self._initialized

    async def init_db(self, settings: Settings | None = None) -> None:
        """Initialize the database engine and session factory.

        Creates the async engine with configured connection pool settings
        and sets up the session factory for creating database sessions.

        Args:
            settings: Application settings. If None, loads from config.

        Raises:
            Exception: If database connection fails.
        """
        if self._initialized:
            logger.warning("database_already_initialized")
            return

        # Lazy import to avoid circular imports
        if settings is None:
            from krakenbot.config.settings import get_settings

            settings = get_settings()

        database_url = str(settings.database.url)

        logger.info(
            "initializing_database",
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            echo=settings.database.echo,
        )

        self._engine = create_async_engine(
            database_url,
            echo=settings.database.echo,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # Test the connection
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("database_connection_successful")
        except Exception as e:
            logger.error("database_connection_failed", error=str(e))
            await self._cleanup()
            raise

        self._initialized = True

    async def close_db(self) -> None:
        """Close the database engine and cleanup resources.

        This should be called during application shutdown to properly
        close all database connections.
        """
        if not self._initialized:
            logger.warning("database_not_initialized_on_close")
            return

        await self._cleanup()
        logger.info("database_closed")

    async def _cleanup(self) -> None:
        """Internal cleanup of database resources."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._session_factory = None
        self._initialized = False

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Create a database session as an async context manager.

        Yields:
            An async session that will be automatically closed.

        Raises:
            RuntimeError: If database not initialized.
            Exception: Any database errors are propagated after rollback.

        Example:
            >>> async with db_manager.session() as session:
            ...     result = await session.execute(query)
        """
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def read_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Create a read-only database session.

        This is optimized for read operations and doesn't commit changes.

        Yields:
            An async session configured for read operations.
        """
        session = self.session_factory()
        try:
            yield session
        finally:
            await session.close()

    async def setup_timescaledb(self) -> None:
        """Enable the TimescaleDB extension.

        This should be called once during initial database setup.
        Requires PostgreSQL superuser privileges.

        Raises:
            Exception: If TimescaleDB extension cannot be created.
        """
        async with self.engine.begin() as conn:
            await conn.execute(
                text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
            )
        logger.info("timescaledb_extension_enabled")

    async def create_hypertable(
        self,
        table_name: str,
        time_column: str = "timestamp",
        chunk_interval: str = "1 day",
        if_not_exists: bool = True,
    ) -> None:
        """Convert a table to a TimescaleDB hypertable.

        Hypertables provide automatic time-based partitioning for
        efficient time-series data storage and queries.

        Args:
            table_name: Name of the table to convert.
            time_column: Name of the timestamp column for partitioning.
            chunk_interval: Time interval for each chunk (e.g., '1 day').
            if_not_exists: If True, don't error if already a hypertable.

        Raises:
            Exception: If hypertable creation fails.
        """
        migrate_data = "true" if if_not_exists else "false"
        if_not_exists_sql = "true" if if_not_exists else "false"

        sql = text(f"""
            SELECT create_hypertable(
                '{table_name}',
                '{time_column}',
                chunk_time_interval => INTERVAL '{chunk_interval}',
                if_not_exists => {if_not_exists_sql},
                migrate_data => {migrate_data}
            )
        """)

        async with self.engine.begin() as conn:
            await conn.execute(sql)

        logger.info(
            "hypertable_created",
            table=table_name,
            time_column=time_column,
            chunk_interval=chunk_interval,
        )

    async def create_all_tables(self) -> None:
        """Create all tables defined in the ORM models.

        This is mainly for testing. In production, use Alembic migrations.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("tables_created")

    async def drop_all_tables(self) -> None:
        """Drop all tables defined in the ORM models.

        WARNING: This is destructive and should only be used in testing.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("tables_dropped")


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Get or create the global database manager instance.

    Returns:
        The global DatabaseManager instance.
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def init_db(settings: Settings | None = None) -> None:
    """Initialize the global database connection.

    This is a convenience function that calls init_db() on the global
    database manager.

    Args:
        settings: Application settings. If None, loads from config.
    """
    manager = get_db_manager()
    await manager.init_db(settings)


async def close_db() -> None:
    """Close the global database connection.

    This is a convenience function that calls close_db() on the global
    database manager.
    """
    manager = get_db_manager()
    await manager.close_db()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session as an async context manager.

    This is a convenience function that provides sessions from the global
    database manager.

    Yields:
        An async session that will be automatically closed.

    Example:
        >>> async with get_session() as session:
        ...     result = await session.execute(query)
    """
    manager = get_db_manager()
    async with manager.session() as session:
        yield session


@asynccontextmanager
async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a read-only database session.

    This is a convenience function that provides read-only sessions from
    the global database manager.

    Yields:
        An async session configured for read operations.
    """
    manager = get_db_manager()
    async with manager.read_session() as session:
        yield session


def reset_db_manager() -> None:
    """Reset the global database manager (for testing).

    This should only be used in tests to ensure a clean state.
    """
    global _db_manager
    _db_manager = None
