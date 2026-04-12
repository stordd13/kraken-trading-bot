"""Exchange connectors for KrakenBot.

This package contains the connectors for communicating with supported exchanges:
- binance/: Binance spot REST connector
- kraken/: Kraken spot, futures, and websocket connectors
- exchange: minimal runtime REST abstraction and factory
- base_perps: abstract base class for perpetual futures exchanges
- base_ws: abstract base class for exchange WebSocket clients

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
from krakenbot.connectors.base_ws import BaseWebSocketClient
from krakenbot.connectors.binance.rest import BinanceRestClient
from krakenbot.connectors.binance.ws import BinanceWebSocketClient
from krakenbot.connectors.exchange import (
    ExchangeRestClient,
    build_exchange_rest_client,
    build_exchange_ws_client,
)
from krakenbot.connectors.kraken.rest import KrakenRestClient
from krakenbot.connectors.kraken.ws import KrakenWebSocketClient

__all__ = [
    "BaseExchangePerps",
    "BaseWebSocketClient",
    "BinanceRestClient",
    "BinanceWebSocketClient",
    "ExchangeRestClient",
    "KrakenRestClient",
    "KrakenWebSocketClient",
    "build_exchange_rest_client",
    "build_exchange_ws_client",
]
