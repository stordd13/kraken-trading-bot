"""Scheduled tasks models for audit trail and execution tracking.

This module defines ORM models for tracking scheduled task executions.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, String, Integer, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from krakenbot.core.database import Base

# Import utc_now from trades module where it's defined
from krakenbot.models.trades import utc_now

if TYPE_CHECKING:
    pass  # For future type hints if needed


class TaskExecutionLog(Base):
    """Audit trail for scheduled task executions.

    This model tracks every execution of scheduled tasks (OHLC data collection,
    backfills, etc.) for monitoring and debugging purposes.

    Attributes:
        id: Auto-incrementing primary key.
        task_id: Unique task identifier (e.g., 'daily_ohlc_1min').
        pair: Trading pair for this task.
        interval: OHLC interval in minutes.
        started_at: When task started execution.
        completed_at: When task completed (NULL if failed or still running).
        status: Task status (running, success, failed).
        candles_fetched: Number of candles fetched in this execution.
        error_message: Error message if task failed.
    """

    __tablename__ = "task_execution_logs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    task_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Unique task identifier (e.g., 'daily_ohlc_1min')",
    )

    pair: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Trading pair (e.g., 'XBT/USDC')",
    )

    interval: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="OHLC interval in minutes",
    )

    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
        comment="When task started execution",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="When task completed (NULL if failed or still running)",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        comment="Task status: running, success, failed",
    )

    candles_fetched: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of candles fetched in this execution",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if task failed",
    )

    __table_args__ = (
        # Composite index for querying task history
        Index("ix_task_logs_task_started", "task_id", "started_at"),
        # Index for querying by pair and interval
        Index("ix_task_logs_pair_interval", "pair", "interval"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<TaskExecutionLog(id={self.id}, task_id='{self.task_id}', "
            f"pair='{self.pair}', interval={self.interval}, status='{self.status}')>"
        )
