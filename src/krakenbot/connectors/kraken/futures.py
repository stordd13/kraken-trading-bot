"""Kraken Futures REST client using ccxt.krakenfutures.

Completely separate from KrakenRestClient (Spot).
Uses dedicated Kraken Futures API keys.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar

import ccxt.async_support as ccxt

from krakenbot.connectors.base_perps import BaseExchangePerps
from krakenbot.core.logger import get_logger

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings

logger = get_logger(__name__)


class KrakenFuturesClient(BaseExchangePerps):
    """REST client for Kraken Futures (perpetual swaps).

    Completely separate from KrakenRestClient (Spot).
    Uses dedicated Kraken Futures API keys.
    """

    # Internal pair -> Kraken Futures symbol (PF_ = perpetual multi-collateral)
    _PAIR_MAP: ClassVar[dict[str, str]] = {
        "XBT/USD": "PF_XBTUSD",
        "ETH/USD": "PF_ETHUSD",
        "SOL/USD": "PF_SOLUSD",
        "BTC/USD": "PF_XBTUSD",  # alias
    }

    # Explicit reverse map (avoid dict comprehension bug with BTC/USD alias)
    _PAIR_REVERSE: ClassVar[dict[str, str]] = {
        "PF_XBTUSD": "XBT/USD",
        "PF_ETHUSD": "ETH/USD",
        "PF_SOLUSD": "SOL/USD",
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._max_leverage = settings.kraken_futures.max_leverage

        self._exchange: ccxt.krakenfutures = ccxt.krakenfutures(
            {
                "apiKey": settings.kraken_futures.api_key.get_secret_value(),
                "secret": settings.kraken_futures.api_secret.get_secret_value(),
                "enableRateLimit": True,
            }
        )

        if settings.kraken_futures.demo:
            self._exchange.set_sandbox_mode(True)
            logger.info("kraken_futures_demo_mode_enabled")

    @property
    def name(self) -> str:
        return "kraken_futures"

    @property
    def maker_fee(self) -> Decimal:
        return Decimal("0.0002")  # 0.02%

    @property
    def taker_fee(self) -> Decimal:
        return Decimal("0.0005")  # 0.05%

    @property
    def max_leverage(self) -> int:
        return self._max_leverage

    def normalize_pair_to_exchange(self, internal_pair: str) -> str:
        if internal_pair not in self._PAIR_MAP:
            raise ValueError(f"Unsupported pair: {internal_pair}")
        return self._PAIR_MAP[internal_pair]

    def denormalize_pair_from_exchange(self, exchange_pair: str) -> str:
        return self._PAIR_REVERSE.get(exchange_pair, exchange_pair)

    async def get_balance(self) -> dict[str, Decimal]:
        """Futures account balance (separate from Spot)."""
        raw = await self._exchange.fetch_balance()
        result: dict[str, Decimal] = {}
        for currency, amount in raw.get("total", {}).items():
            if amount and Decimal(str(amount)) > 0:
                result[currency] = Decimal(str(amount))
        return result

    async def place_perp_order(
        self,
        pair: str,
        side: str,
        amount: Decimal,
        price: Decimal | None = None,
        leverage: int = 1,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        if leverage > self._max_leverage:
            raise ValueError(f"Leverage {leverage} exceeds max {self._max_leverage}")

        exchange_pair = self.normalize_pair_to_exchange(pair)

        # Set leverage before placing the order
        try:
            await self.set_leverage(pair, leverage)
        except Exception as e:
            # Kraken may return an error if leverage is already at this value
            if "leverage not modified" not in str(e).lower():
                logger.warning("set_leverage_warning", error=str(e))

        params: dict[str, Any] = {}
        if reduce_only:
            params["reduceOnly"] = True

        if price is None:
            result = await self._exchange.create_market_order(
                symbol=exchange_pair,
                side=side.lower(),
                amount=float(amount),
                params=params,
            )
        else:
            result = await self._exchange.create_limit_order(
                symbol=exchange_pair,
                side=side.lower(),
                amount=float(amount),
                price=float(price),
                params=params,
            )

        return {
            "order_id": result["id"],
            "status": self._normalize_status(result["status"]),
            "pair": pair,
            "side": side,
            "amount": Decimal(str(result["amount"])),
            "price": Decimal(str(result.get("price") or 0)),
            "leverage": leverage,
            "reduce_only": reduce_only,
        }

    async def close_perp_position(self, pair: str) -> dict[str, Any]:
        position = await self.get_perp_position(pair)
        if position is None:
            return {"status": "NO_POSITION"}

        opposite_side = "sell" if position["side"] == "long" else "buy"

        return await self.place_perp_order(
            pair=pair,
            side=opposite_side,
            amount=position["size"],
            price=None,  # market order for guaranteed execution
            leverage=position["leverage"],
            reduce_only=True,
        )

    async def get_perp_position(self, pair: str) -> dict[str, Any] | None:
        exchange_pair = self.normalize_pair_to_exchange(pair)
        positions = await self._exchange.fetch_positions([exchange_pair])

        for pos in positions:
            contracts = pos.get("contracts")
            if contracts and Decimal(str(contracts)) > 0:
                return {
                    "pair": pair,
                    "side": "long" if pos["side"] == "long" else "short",
                    "size": Decimal(str(pos["contracts"])),
                    "size_usd": Decimal(str(pos.get("notional") or 0)),
                    "entry_price": Decimal(str(pos.get("entryPrice") or 0)),
                    "mark_price": Decimal(str(pos.get("markPrice") or 0)),
                    "unrealized_pnl": Decimal(str(pos.get("unrealizedPnl") or 0)),
                    "leverage": int(pos.get("leverage") or 1),
                    "liquidation_price": (
                        Decimal(str(pos["liquidationPrice"]))
                        if pos.get("liquidationPrice")
                        else None
                    ),
                }
        return None

    async def get_all_positions(self) -> list[dict[str, Any]]:
        positions = await self._exchange.fetch_positions()
        result: list[dict[str, Any]] = []
        for pos in positions:
            contracts = pos.get("contracts")
            if not contracts or Decimal(str(contracts)) == 0:
                continue
            internal_pair = self.denormalize_pair_from_exchange(pos["symbol"])
            result.append(
                {
                    "pair": internal_pair,
                    "side": "long" if pos["side"] == "long" else "short",
                    "size": Decimal(str(pos["contracts"])),
                    "size_usd": Decimal(str(pos.get("notional") or 0)),
                    "entry_price": Decimal(str(pos.get("entryPrice") or 0)),
                    "mark_price": Decimal(str(pos.get("markPrice") or 0)),
                    "unrealized_pnl": Decimal(str(pos.get("unrealizedPnl") or 0)),
                    "leverage": int(pos.get("leverage") or 1),
                }
            )
        return result

    async def get_funding_rate(self, pair: str) -> Decimal:
        exchange_pair = self.normalize_pair_to_exchange(pair)
        rate_data = await self._exchange.fetch_funding_rate(exchange_pair)
        return Decimal(str(rate_data["fundingRate"]))

    async def get_funding_history(
        self, pair: str, since_ms: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        exchange_pair = self.normalize_pair_to_exchange(pair)
        history = await self._exchange.fetch_funding_rate_history(
            symbol=exchange_pair, since=since_ms, limit=limit
        )
        return [
            {
                "timestamp": h["timestamp"],
                "rate": Decimal(str(h["fundingRate"])),
            }
            for h in history
        ]

    async def set_leverage(self, pair: str, leverage: int) -> None:
        if leverage > self._max_leverage:
            raise ValueError(f"Leverage {leverage} exceeds max {self._max_leverage}")
        if leverage < 1:
            raise ValueError("Leverage must be >= 1")

        exchange_pair = self.normalize_pair_to_exchange(pair)
        await self._exchange.set_leverage(leverage, exchange_pair)

    @staticmethod
    def _normalize_status(ccxt_status: str) -> str:
        """Map ccxt order status to internal status."""
        mapping = {
            "open": "PENDING",
            "closed": "FILLED",
            "canceled": "CANCELLED",
            "expired": "EXPIRED",
        }
        return mapping.get(ccxt_status, ccxt_status.upper())

    async def close(self) -> None:
        """Close the ccxt connection."""
        await self._exchange.close()
