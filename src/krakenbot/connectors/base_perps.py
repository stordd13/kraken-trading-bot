"""Abstract base class for perpetual futures exchanges.

Kraken Spot does NOT implement this interface (spot only).
Only perpetual futures connectors (Kraken Futures, future Bybit, etc.)
implement it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any


class BaseExchangePerps(ABC):
    """Interface for perpetual futures exchange connectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Exchange name. E.g. 'kraken_futures'."""

    @property
    @abstractmethod
    def maker_fee(self) -> Decimal:
        """Maker fee rate (e.g. Decimal('0.0002') for 0.02%)."""

    @property
    @abstractmethod
    def taker_fee(self) -> Decimal:
        """Taker fee rate (e.g. Decimal('0.0005') for 0.05%)."""

    @property
    @abstractmethod
    def max_leverage(self) -> int:
        """Maximum leverage allowed by config (safety cap)."""

    @abstractmethod
    async def get_balance(self) -> dict[str, Decimal]:
        """Futures account balance (separate from Spot)."""

    @abstractmethod
    async def place_perp_order(
        self,
        pair: str,
        side: str,
        amount: Decimal,
        price: Decimal | None = None,
        leverage: int = 1,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Place a perpetual futures order.

        Args:
            pair: Internal format, e.g. "XBT/USD".
            side: "buy" or "sell".
            amount: Size in contracts or crypto.
            price: Limit price, or None for market order.
            leverage: Leverage multiplier.
            reduce_only: True to close an existing position.
        """

    @abstractmethod
    async def close_perp_position(self, pair: str) -> dict[str, Any]:
        """Close the entire open position on this pair."""

    @abstractmethod
    async def get_perp_position(self, pair: str) -> dict[str, Any] | None:
        """Return the open position or None.

        When a position exists, the returned dict contains:
            pair, side ('long'|'short'), size, size_usd, entry_price,
            mark_price, unrealized_pnl, leverage, liquidation_price.
        All monetary values are Decimal.
        """

    @abstractmethod
    async def get_all_positions(self) -> list[dict[str, Any]]:
        """Return all open perpetual positions."""

    @abstractmethod
    async def get_funding_rate(self, pair: str) -> Decimal:
        """Current funding rate for this pair (per period)."""

    @abstractmethod
    async def get_funding_history(
        self, pair: str, since_ms: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Funding rate history.

        Returns a list of {'timestamp': int, 'rate': Decimal}.
        """

    @abstractmethod
    async def set_leverage(self, pair: str, leverage: int) -> None:
        """Set leverage for a pair. Must respect max_leverage."""

    @abstractmethod
    def normalize_pair_to_exchange(self, internal_pair: str) -> str:
        """Convert internal pair to exchange format.

        E.g. 'XBT/USD' -> 'PF_XBTUSD' for Kraken Futures.
        """

    @abstractmethod
    def denormalize_pair_from_exchange(self, exchange_pair: str) -> str:
        """Convert exchange pair to internal format.

        E.g. 'PF_XBTUSD' -> 'XBT/USD'.
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the exchange connection and release resources."""
