"""Alembic environment configuration.

This module sets up the Alembic migration environment with:
- Async SQLAlchemy support
- Environment variable configuration
- Import of all models for autogenerate
"""

import asyncio
from logging.config import fileConfig
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add the src directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Load environment variables from .env file
load_dotenv()

# Import the Base and all models to register them
from krakenbot.core.database import Base  # noqa: E402
from krakenbot.ml.db_models import MLExternalData, MLFeatureRow  # noqa: E402, F401

# Import all models so they are registered with Base.metadata
from krakenbot.models import (  # noqa: E402, F401
    BotState,
    OHLCData,
    OHLCDerived,
    Order,
    TickData,
    Trade,
)

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get database URL from environment or config.

    Returns:
        Database connection URL.
    """
    # Try environment variable first
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # Fall back to config file
    return config.get_main_option("sqlalchemy.url", "")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() will emit the given string to the
    script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations within a transaction.

    Args:
        connection: Database connection.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine.

    Creates an async Engine and associates a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Wrapper for async migration runner.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
