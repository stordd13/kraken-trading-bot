"""Abstract base class for exchange WebSocket clients.

Provides the common interface and shared state that all exchange WebSocket
implementations must follow.  Exchange-specific logic (URLs, message formats,
subscription payloads) lives in the concrete subclass.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from krakenbot.core.logger import get_logger

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus

logger = get_logger(__name__)


class BaseWebSocketClient(ABC):
    """Abstract base for all exchange WebSocket clients.

    Initialises common connection / reconnection state, statistics tracking,
    and heartbeat bookkeeping.  Concrete subclasses override the abstract
    methods with exchange-specific behaviour.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self._settings = settings
        self._event_bus = event_bus
        self._db_manager = db_manager

        # Connection state
        self._running = False
        self._connected = False

        # Reconnection settings
        self._reconnect_delay: int | float = 5
        self._max_reconnect_attempts = 10
        self._reconnect_count = 0

        # Heartbeat settings
        self._heartbeat_interval = 30.0  # seconds
        self._heartbeat_timeout = 10.0  # seconds
        self._last_message_time: datetime | None = None

        # Background tasks
        self._message_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._data_flow_task: asyncio.Task[None] | None = None

        # Statistics
        self._stats: dict[str, int] = {
            "messages_received": 0,
            "ohlc_received": 0,
            "ticks_received": 0,
            "errors": 0,
            "reconnections": 0,
        }

    # ------------------------------------------------------------------
    # Concrete properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether the WebSocket connection is alive."""
        return self._connected

    @property
    def stats(self) -> dict[str, int]:
        """Return a snapshot of client statistics."""
        return self._stats.copy()

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """Establish the WebSocket connection and start background tasks."""

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close the WebSocket connection."""

    @abstractmethod
    async def subscribe_ohlc(self, pair: str, interval: int) -> None:
        """Subscribe to OHLC candle updates for *pair* at *interval* minutes."""

    @abstractmethod
    async def subscribe_ticker(self, pair: str) -> None:
        """Subscribe to real-time ticker (bid/ask/last) updates for *pair*."""

    @abstractmethod
    async def unsubscribe_ohlc(self, pair: str, interval: int) -> None:
        """Unsubscribe from OHLC candle updates."""
