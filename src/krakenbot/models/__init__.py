"""Database models for KrakenBot.

This package contains all SQLAlchemy ORM models used by the application.
All models inherit from the Base class defined in core.database.
"""

from krakenbot.ml.db_models import MLExternalData, MLFeatureRow
from krakenbot.models.base import (
    BotStatus,
    OrderStatus,
    OrderType,
    SignalType,
    TradeSide,
    TradeStatus,
)
from krakenbot.models.market_data import OHLCData, OHLCDerived, TickData
from krakenbot.models.orders import Order
from krakenbot.models.trades import BotState, PaperBalance, Trade

__all__ = [
    "BotState",
    # Enums
    "BotStatus",
    # Market data models
    "MLExternalData",
    "MLFeatureRow",
    "OHLCData",
    "OHLCDerived",
    # Order enums
    "OrderStatus",
    "OrderType",
    # Order model
    "Order",
    # Paper trading
    "PaperBalance",
    "SignalType",
    "TickData",
    # Trade models
    "Trade",
    "TradeSide",
    "TradeStatus",
]
