"""Kraken exchange connectors for KrakenBot.

This package contains the connectors for communicating with the Kraken exchange:
- kraken_ws: WebSocket client for real-time market data
- kraken_rest: REST client for trading operations

Example:
    >>> from krakenbot.connectors import KrakenWebSocketClient, KrakenRestClient
    >>> ws_client = KrakenWebSocketClient(settings, event_bus, db_manager)
    >>> rest_client = KrakenRestClient(settings, event_bus, db_manager)
"""

from krakenbot.connectors.kraken_rest import KrakenRestClient
from krakenbot.connectors.kraken_ws import KrakenWebSocketClient

__all__ = [
    "KrakenRestClient",
    "KrakenWebSocketClient",
]
