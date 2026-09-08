"""Bybit EU exchange connectors (spot REST in B1; WebSocket arrives in B2)."""

from krakenbot.connectors.bybit.rest import BybitRestClient

__all__ = ["BybitRestClient"]
