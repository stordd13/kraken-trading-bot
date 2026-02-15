"""Order model for limit order tracking.

This module defines the database model for tracking limit orders
through their lifecycle: PENDING -> FILLED/CANCELLED/EXPIRED.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from sqlalchemy import DECIMAL, JSON, TIMESTAMP, Enum, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from krakenbot.core.database import Base
from krakenbot.models.base import OrderStatus, OrderType, TradeSide


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


class Order(Base):
    """Limit order tracking model.

    Tracks orders from placement through fill/cancel/expiry.
    Used by OrderManager for lifecycle management.

    Attributes:
        id: Unique order identifier (internal UUID).
        order_id: Exchange order ID (Kraken ID or paper-xxx).
        bot_id: Bot instance identifier.
        pair: Trading pair.
        side: Order side (buy/sell).
        order_type: Order type (market/limit).
        amount: Requested order amount in base currency.
        price: Limit price (None for market orders).
        filled_amount: Amount filled so far.
        filled_price: Average fill price.
        fee: Total fees paid.
        status: Current order status.
        strategy: Strategy name that placed this order.
        signal_metadata: JSON metadata from the trading signal.
        expires_at: When the order should be auto-cancelled.
        created_at: Order creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "orders"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique order identifier (internal)",
    )

    # Exchange order ID
    order_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Exchange order ID (Kraken ID or paper-xxx)",
    )

    # Bot identification
    bot_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Bot instance identifier",
    )

    # Order details
    pair: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Trading pair (e.g., XBT/USDC)",
    )
    side: Mapped[TradeSide] = mapped_column(
        Enum(TradeSide, native_enum=False, length=10),
        nullable=False,
        comment="Order side (buy/sell)",
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, native_enum=False, length=10),
        nullable=False,
        default=OrderType.LIMIT,
        comment="Order type (market/limit)",
    )
    trading_mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="spot",
        default="spot",
        comment="Trading mode: spot or margin",
    )

    # Amounts and prices
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        comment="Requested order amount in base currency",
    )
    price: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=True,
        comment="Limit price (None for market orders)",
    )
    filled_amount: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        default=Decimal("0"),
        comment="Amount filled so far",
    )
    filled_price: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=True,
        comment="Average fill price",
    )
    fee: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=8),
        nullable=False,
        default=Decimal("0"),
        comment="Total fees paid",
    )

    # Status
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False, length=20),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True,
        comment="Current order status",
    )

    # Strategy and metadata
    strategy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Strategy name that placed this order",
    )
    signal_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="JSON metadata from the trading signal",
    )

    # Expiry
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="When the order should be auto-cancelled",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        comment="Order creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        comment="Last update timestamp",
    )

    # Indexes
    __table_args__ = (
        Index("ix_orders_bot_status", "bot_id", "status"),
        Index("ix_orders_status_expires", "status", "expires_at"),
        {
            "comment": "Limit order tracking for lifecycle management",
        },
    )

    def __repr__(self) -> str:
        """Return string representation of order."""
        return (
            f"Order(id={self.id!r}, order_id={self.order_id!r}, "
            f"pair={self.pair!r}, side={self.side.value}, "
            f"type={self.order_type.value}, status={self.status.value}, "
            f"amount={self.amount}, price={self.price})"
        )

    @property
    def is_pending(self) -> bool:
        """Check if order is still pending."""
        return self.status == OrderStatus.PENDING

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_expired(self) -> bool:
        """Check if order has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) >= self.expires_at

    @property
    def is_active(self) -> bool:
        """Check if order is still active (pending or partially filled)."""
        return self.status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED)
