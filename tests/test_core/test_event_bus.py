"""Tests for the EventBus module.

This module tests the pub/sub event bus functionality including:
- Subscribe/unsubscribe operations
- Event publishing and delivery
- Wildcard subscriptions
- Async callback support
- Error handling
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.core.event_bus import (
    Event,
    EventBus,
    EventType,
    get_event_bus,
    reset_event_bus,
)


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus instance for testing.

    Returns:
        A new EventBus instance.
    """
    return EventBus()


@pytest.fixture
def event_bus_with_history() -> EventBus:
    """Create an EventBus with history enabled.

    Returns:
        An EventBus with history tracking.
    """
    return EventBus(keep_history=True, max_history=100)


@pytest.fixture(autouse=True)
def reset_global_event_bus() -> None:
    """Reset global event bus before each test."""
    reset_event_bus()


class TestEventBusSubscription:
    """Tests for subscribe/unsubscribe functionality."""

    async def test_subscribe_adds_callback(self, event_bus: EventBus) -> None:
        """Test that subscribing adds callback to subscribers."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("test.event", callback)

        assert event_bus.get_subscriber_count("test.event") == 1

    async def test_subscribe_multiple_callbacks(self, event_bus: EventBus) -> None:
        """Test subscribing multiple callbacks to same event."""
        callback1 = MagicMock(__name__="callback1")
        callback2 = MagicMock(__name__="callback2")

        await event_bus.subscribe("test.event", callback1)
        await event_bus.subscribe("test.event", callback2)

        assert event_bus.get_subscriber_count("test.event") == 2

    async def test_subscribe_with_event_type_enum(self, event_bus: EventBus) -> None:
        """Test subscribing using EventType enum."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe(EventType.MARKET_TICK, callback)

        assert event_bus.get_subscriber_count(EventType.MARKET_TICK) == 1

    async def test_unsubscribe_removes_callback(self, event_bus: EventBus) -> None:
        """Test that unsubscribing removes callback."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("test.event", callback)
        result = await event_bus.unsubscribe("test.event", callback)

        assert result is True
        assert event_bus.get_subscriber_count("test.event") == 0

    async def test_unsubscribe_nonexistent_returns_false(
        self, event_bus: EventBus
    ) -> None:
        """Test unsubscribing a non-existent callback returns False."""
        callback = MagicMock(__name__="callback")
        result = await event_bus.unsubscribe("test.event", callback)

        assert result is False

    async def test_wildcard_subscription(self, event_bus: EventBus) -> None:
        """Test wildcard subscription pattern."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("market.*", callback)

        assert event_bus.get_subscriber_count("market.*") == 1

    async def test_total_subscriber_count(self, event_bus: EventBus) -> None:
        """Test getting total subscriber count."""
        callback1 = MagicMock(__name__="callback1")
        callback2 = MagicMock(__name__="callback2")
        callback3 = MagicMock(__name__="callback3")

        await event_bus.subscribe("event.one", callback1)
        await event_bus.subscribe("event.two", callback2)
        await event_bus.subscribe("event.*", callback3)

        assert event_bus.get_subscriber_count() == 3


class TestEventBusPublishing:
    """Tests for event publishing functionality."""

    async def test_publish_calls_subscriber(self, event_bus: EventBus) -> None:
        """Test that publishing calls subscribed callback."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("test.event", callback)

        await event_bus.publish("test.event", {"key": "value"})

        callback.assert_called_once_with({"key": "value"})

    async def test_publish_async_callback(self, event_bus: EventBus) -> None:
        """Test publishing to async callback."""
        callback = AsyncMock(__name__="callback")
        await event_bus.subscribe("test.event", callback)

        await event_bus.publish("test.event", {"key": "value"})

        callback.assert_called_once_with({"key": "value"})

    async def test_publish_returns_delivery_count(self, event_bus: EventBus) -> None:
        """Test that publish returns number of delivered events."""
        callback1 = MagicMock(__name__="callback1")
        callback2 = MagicMock(__name__="callback2")

        await event_bus.subscribe("test.event", callback1)
        await event_bus.subscribe("test.event", callback2)

        count = await event_bus.publish("test.event", {})

        assert count == 2

    async def test_publish_no_subscribers_returns_zero(
        self, event_bus: EventBus
    ) -> None:
        """Test publishing to event with no subscribers."""
        count = await event_bus.publish("no.subscribers", {})

        assert count == 0

    async def test_publish_wildcard_receives_events(self, event_bus: EventBus) -> None:
        """Test that wildcard subscribers receive matching events."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("market.*", callback)

        await event_bus.publish("market.tick", {"price": "42000"})
        await event_bus.publish("market.ohlc", {"close": "42500"})

        assert callback.call_count == 2

    async def test_publish_wildcard_ignores_non_matching(
        self, event_bus: EventBus
    ) -> None:
        """Test that wildcard doesn't match unrelated events."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("market.*", callback)

        await event_bus.publish("trade.signal", {})

        callback.assert_not_called()

    async def test_publish_with_event_type_enum(self, event_bus: EventBus) -> None:
        """Test publishing using EventType enum."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe(EventType.MARKET_TICK, callback)

        await event_bus.publish(EventType.MARKET_TICK, {"price": "42000"})

        callback.assert_called_once_with({"price": "42000"})

    async def test_callback_error_doesnt_stop_others(
        self, event_bus: EventBus
    ) -> None:
        """Test that error in one callback doesn't prevent others."""
        callback1 = MagicMock(__name__="callback1", side_effect=ValueError("test error"))
        callback2 = MagicMock(__name__="callback2")

        await event_bus.subscribe("test.event", callback1)
        await event_bus.subscribe("test.event", callback2)

        count = await event_bus.publish("test.event", {})

        # callback2 should still be called
        callback2.assert_called_once()
        # Only callback2 succeeded
        assert count == 1


class TestEventBusPublishAndWait:
    """Tests for publish_and_wait functionality."""

    async def test_publish_and_wait_completes_all(self, event_bus: EventBus) -> None:
        """Test that publish_and_wait waits for all handlers."""
        results: list[int] = []

        async def slow_handler(data: dict[str, Any]) -> None:
            await asyncio.sleep(0.1)
            results.append(1)

        async def fast_handler(data: dict[str, Any]) -> None:
            results.append(2)

        await event_bus.subscribe("test.event", slow_handler)
        await event_bus.subscribe("test.event", fast_handler)

        await event_bus.publish_and_wait("test.event", {})

        # Both should have completed
        assert len(results) == 2

    async def test_publish_and_wait_timeout(self, event_bus: EventBus) -> None:
        """Test publish_and_wait respects timeout."""

        async def very_slow_handler(data: dict[str, Any]) -> None:
            await asyncio.sleep(10)

        await event_bus.subscribe("test.event", very_slow_handler)

        with pytest.raises(asyncio.TimeoutError):
            await event_bus.publish_and_wait("test.event", {}, timeout=0.1)


class TestEventBusHistory:
    """Tests for event history functionality."""

    async def test_history_disabled_by_default(self, event_bus: EventBus) -> None:
        """Test that history is disabled by default."""
        await event_bus.publish("test.event", {})

        history = event_bus.get_history()
        assert len(history) == 0

    async def test_history_enabled_stores_events(
        self, event_bus_with_history: EventBus
    ) -> None:
        """Test that enabled history stores events."""
        await event_bus_with_history.publish("test.event", {"key": "value"})

        history = event_bus_with_history.get_history()
        assert len(history) == 1
        assert history[0].event_type == "test.event"
        assert history[0].data == {"key": "value"}

    async def test_history_respects_max_limit(
        self, event_bus_with_history: EventBus
    ) -> None:
        """Test that history respects max_history limit."""
        # EventBus has max_history=100
        for i in range(150):
            await event_bus_with_history.publish("test.event", {"i": i})

        history = event_bus_with_history.get_history()
        assert len(history) == 100
        # Should have most recent events
        assert history[-1].data["i"] == 149

    async def test_history_filter_by_event_type(
        self, event_bus_with_history: EventBus
    ) -> None:
        """Test filtering history by event type."""
        await event_bus_with_history.publish("event.one", {"n": 1})
        await event_bus_with_history.publish("event.two", {"n": 2})
        await event_bus_with_history.publish("event.one", {"n": 3})

        history = event_bus_with_history.get_history(event_type="event.one")
        assert len(history) == 2
        assert all(e.event_type == "event.one" for e in history)

    async def test_history_limit_parameter(
        self, event_bus_with_history: EventBus
    ) -> None:
        """Test limiting history results."""
        for i in range(10):
            await event_bus_with_history.publish("test.event", {"i": i})

        history = event_bus_with_history.get_history(limit=5)
        assert len(history) == 5


class TestEventBusClearSubscribers:
    """Tests for clearing subscribers."""

    async def test_clear_all_subscribers(self, event_bus: EventBus) -> None:
        """Test clearing all subscribers."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("event.one", callback)
        await event_bus.subscribe("event.two", callback)
        await event_bus.subscribe("market.*", callback)

        await event_bus.clear_subscribers()

        assert event_bus.get_subscriber_count() == 0

    async def test_clear_specific_event_subscribers(self, event_bus: EventBus) -> None:
        """Test clearing subscribers for specific event."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("event.one", callback)
        await event_bus.subscribe("event.two", callback)

        await event_bus.clear_subscribers("event.one")

        assert event_bus.get_subscriber_count("event.one") == 0
        assert event_bus.get_subscriber_count("event.two") == 1


class TestEventBusStatistics:
    """Tests for statistics tracking."""

    async def test_stats_track_published_events(self, event_bus: EventBus) -> None:
        """Test that stats track published events."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("test.event", callback)

        await event_bus.publish("test.event", {})
        await event_bus.publish("test.event", {})

        stats = event_bus.get_stats()
        assert stats["events_published"] == 2
        assert stats["events_delivered"] == 2

    async def test_stats_track_delivery_errors(self, event_bus: EventBus) -> None:
        """Test that stats track delivery errors."""
        callback = MagicMock(__name__="callback", side_effect=ValueError("error"))
        await event_bus.subscribe("test.event", callback)

        await event_bus.publish("test.event", {})

        stats = event_bus.get_stats()
        assert stats["delivery_errors"] == 1

    async def test_reset_stats(self, event_bus: EventBus) -> None:
        """Test resetting statistics."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe("test.event", callback)
        await event_bus.publish("test.event", {})

        event_bus.reset_stats()

        stats = event_bus.get_stats()
        assert stats["events_published"] == 0


class TestEvent:
    """Tests for the Event dataclass."""

    def test_event_creation(self) -> None:
        """Test creating an Event."""
        event = Event(event_type="test.event", data={"key": "value"})

        assert event.event_type == "test.event"
        assert event.data == {"key": "value"}
        assert event.timestamp is not None

    def test_event_to_dict(self) -> None:
        """Test converting Event to dictionary."""
        event = Event(event_type="test.event", data={"key": "value"})
        result = event.to_dict()

        assert result["event_type"] == "test.event"
        assert result["data"] == {"key": "value"}
        assert "timestamp" in result


class TestGlobalEventBus:
    """Tests for global event bus functions."""

    def test_get_event_bus_returns_singleton(self) -> None:
        """Test that get_event_bus returns the same instance."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    def test_reset_event_bus_creates_new_instance(self) -> None:
        """Test that reset creates a new instance."""
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()

        assert bus1 is not bus2


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self) -> None:
        """Test EventType enum values."""
        assert EventType.MARKET_TICK.value == "market.tick"
        assert EventType.MARKET_OHLC.value == "market.ohlc"
        assert EventType.TRADE_ORDER_FILLED.value == "trade.order_filled"
        assert EventType.BOT_STARTED.value == "bot.started"

    async def test_event_type_usable_with_subscribe(
        self, event_bus: EventBus
    ) -> None:
        """Test that EventType can be used for subscriptions."""
        callback = MagicMock(__name__="callback")
        await event_bus.subscribe(EventType.MARKET_TICK, callback)
        await event_bus.publish(EventType.MARKET_TICK, {})

        callback.assert_called_once()
