"""Exchange connectors for KrakenBot.

This package contains the connectors for communicating with supported exchanges:
- kraken_ws: WebSocket client for real-time market data
- kraken_rest: REST client for trading operations
- kraken_futures_rest: REST client for Kraken Futures (perpetual swaps)
- exchange: minimal runtime REST abstraction and factory
- base_perps: abstract base class for perpetual futures exchanges

Example:
    >>> from krakenbot.connectors import (
    ...     KrakenWebSocketClient,
    ...     ExchangeRestClient,
    ...     build_exchange_rest_client,
    ... )
    >>> ws_client = KrakenWebSocketClient(settings, event_bus, db_manager)
    >>> rest_client = build_exchange_rest_client(settings, event_bus, db_manager)
"""

from krakenbot.connectors.base_perps import BaseExchangePerps
from krakenbot.connectors.exchange import ExchangeRestClient, build_exchange_rest_client
from krakenbot.connectors.kraken_rest import KrakenRestClient
from krakenbot.connectors.kraken_ws import KrakenWebSocketClient

__all__ = [
    "BaseExchangePerps",
    "ExchangeRestClient",
    "KrakenRestClient",
    "KrakenWebSocketClient",
    "build_exchange_rest_client",
]
