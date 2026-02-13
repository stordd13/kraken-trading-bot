"""Adaptive threshold strategy with multi-timeframe analysis.

ThresholdRolling mechanics + dynamic thresholds from MultiTimeframeAnalyzer:
- Rolling reference prices with delayed add (same as ThresholdRolling)
- Adaptive buy/sell thresholds based on market regime + volatility
- Trailing stop per position (tracks highest price since entry)
- Zone filter: blocks buys when 15m is OVERBOUGHT
- Volume filter: blocks buys when 5m volume ratio < min_volume_ratio
- Limit orders for BUY and profit target, market for stop-loss/trailing

Params (from strategies.yaml):
    trailing_stop_pct: Trailing stop percentage (default 3.0)
    min_volume_ratio: Minimum 5m volume ratio for entry (default 0.8)
    block_overbought_15m: Block buys in overbought 15m zone (default true)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from krakenbot.indicators.multi_timeframe import TimeframeZone
from krakenbot.models.base import PositionStatus, SignalType
from krakenbot.models.trades import OpenPosition
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus
    from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer


@dataclass
class AdaptivePosition:
    """Position with trailing stop tracking."""

    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    position_id: int
    reference_price: Decimal
    highest_price: Decimal  # For trailing stop


class AdaptiveStrategy(BaseStrategy):
    """Adaptive threshold strategy with dynamic thresholds and trailing stop.

    Extends the rolling reference approach with:
    - Adaptive thresholds from MultiTimeframeAnalyzer
    - Trailing stop (sell when price drops trailing_stop_pct from highest)
    - Zone and volume filters before entry
    - Limit orders for BUY and profit targets, market for stops
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        bot_id: str | None = None,
        strategy_params: dict[str, Any] | None = None,
        analyzer: MultiTimeframeAnalyzer | None = None,
    ) -> None:
        """Initialize AdaptiveStrategy.

        Args:
            settings: Application settings.
            event_bus: Event bus.
            db_manager: Database manager.
            bot_id: Unique bot identifier.
            strategy_params: Custom params from strategies.yaml.
            analyzer: Shared MultiTimeframeAnalyzer instance.
        """
        super().__init__(
            settings,
            event_bus,
            db_manager,
            bot_id=bot_id,
            strategy_params=strategy_params,
            analyzer=analyzer,
        )

        params = strategy_params or {}
        self.pair = settings.trading.pair
        self.lookback_periods = settings.strategy.lookback_periods
        self.max_holding_minutes = settings.strategy.max_holding_minutes

        # Adaptive params from strategies.yaml
        self.trailing_stop_pct = Decimal(str(params.get("trailing_stop_pct", 3.0)))
        self.min_volume_ratio = float(params.get("min_volume_ratio", 0.8))
        self.block_overbought_15m = bool(params.get("block_overbought_15m", True))

        # Budget params
        budget = None
        if settings.multi_strategy.enabled:
            for s in settings.multi_strategy.strategies:
                if s.bot_id == bot_id:
                    budget = s.budget
                    break
        self.max_open_positions = (
            budget.max_open_positions if budget else settings.risk.max_open_positions
        )
        self.position_size_multiplier = budget.position_size_multiplier if budget else 1.0

        # Fallback thresholds (used when analyzer not ready)
        self._fallback_buy_threshold = settings.strategy.buy_threshold_pct
        self._fallback_sell_threshold = settings.strategy.sell_threshold_pct
        self.stop_loss_pct = settings.risk.emergency_stop_loss_pct

        # Position tracking (same as ThresholdRolling)
        self._reference_prices: list[Decimal] = []
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._open_positions: list[AdaptivePosition] = []
        self._next_position_id: int = 1
        self._skip_db_sync: bool = False
        self._used_references: set[Decimal] = set()
        self._pending_reference: Decimal | None = None
        self._bought_this_candle: bool = False
        self._warming_up: bool = True
        self._warmup_open_price: Decimal | None = None

        self.logger.debug(
            "adaptive_strategy_initialized",
            bot_id=self.bot_id,
            trailing_stop_pct=float(self.trailing_stop_pct),
            min_volume_ratio=self.min_volume_ratio,
            block_overbought_15m=self.block_overbought_15m,
            max_open_positions=self.max_open_positions,
        )

    async def start(self) -> None:
        """Start strategy with position recovery from DB."""
        await super().start()
        if not self._skip_db_sync:
            await self._load_open_positions_from_db()

    async def _load_open_positions_from_db(self) -> None:
        """Recover open positions from database after restart."""
        try:
            async with self.db_manager.read_session() as session:
                result = await session.execute(
                    select(OpenPosition)
                    .where(OpenPosition.bot_id == self.bot_id)
                    .where(OpenPosition.status == PositionStatus.OPEN)
                    .order_by(OpenPosition.position_id)
                )
                positions = result.scalars().all()

                for pos in positions:
                    self._open_positions.append(
                        AdaptivePosition(
                            entry_price=pos.entry_price,
                            entry_time=pos.entry_time,
                            amount_usdc=pos.amount_btc * pos.entry_price,
                            position_id=pos.position_id,
                            reference_price=pos.reference_price,
                            highest_price=pos.entry_price,  # Will be updated on tick
                        )
                    )
                    self._used_references.add(pos.reference_price)
                    self._next_position_id = max(self._next_position_id, pos.position_id + 1)

                if positions:
                    self.logger.info(
                        "adaptive_positions_recovered",
                        count=len(positions),
                        bot_id=self.bot_id,
                    )
        except Exception as e:
            self.logger.warning(
                "adaptive_positions_recovery_failed",
                error=str(e),
                bot_id=self.bot_id,
            )

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Update current price and trailing stop tracking."""
        if tick_data.get("pair") != self.pair:
            return

        price = Decimal(str(tick_data["price"]))
        self._current_price = price

        # Update highest price for trailing stops
        for pos in self._open_positions:
            if price > pos.highest_price:
                pos.highest_price = price

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC candle: update analyzer + reference prices.

        Updates the shared MultiTimeframeAnalyzer for ALL intervals,
        but only executes trading logic on the trigger timeframe (5min).
        """
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))
        interval = ohlc_data.get("interval", 5)

        # Always update current price
        self._current_price = close_price

        # Update shared analyzer for ALL timeframes
        if self.analyzer is not None:
            self.analyzer.update(ohlc_data, interval)

        # Update highest price for trailing stops from candle highs
        candle_high = Decimal(str(ohlc_data.get("high", close_price)))
        for pos in self._open_positions:
            if candle_high > pos.highest_price:
                pos.highest_price = candle_high

        # Only process trading logic on trigger timeframe (5min)
        trigger_tf = self.settings.multi_timeframe.trigger_timeframe
        if interval != trigger_tf:
            return

        # Only on complete candles
        if not ohlc_data.get("is_complete", False):
            # Warmup open price capture
            if self._warming_up and self._warmup_open_price is None:
                self._warmup_open_price = Decimal(str(ohlc_data.get("open", close_price)))
            return

        # End warmup
        if self._warming_up:
            self._warming_up = False
            self._warmup_open_price = None
            self._reference_prices.append(close_price)

        # Reset buy flag on new complete candle
        self._bought_this_candle = False

        # Parse timestamp
        self._current_timestamp = self._parse_timestamp(ohlc_data)

        # Delayed reference add (same as ThresholdRolling)
        if self._pending_reference is not None:
            self._reference_prices.append(self._pending_reference)
            if len(self._reference_prices) > self.lookback_periods:
                removed = self._reference_prices.pop(0)
                self._used_references.discard(removed)

        if close_price not in self._reference_prices:
            self._pending_reference = close_price

    async def generate_signal(self) -> TradingSignal | None:
        """Generate adaptive trading signal."""
        if not self._current_price:
            return None
        if self._warming_up and self._warmup_open_price is None:
            return None
        if not self._warming_up and not self._reference_prices:
            return None

        current_time = self._current_timestamp or datetime.now(UTC)

        # Get analysis from shared analyzer
        analysis = self.analyzer.analyze() if self.analyzer else None

        # Get adaptive thresholds (or fallback)
        if analysis:
            buy_threshold = analysis.recommended_buy_threshold
            sell_threshold = analysis.recommended_sell_threshold
        else:
            buy_threshold = self._fallback_buy_threshold
            sell_threshold = self._fallback_sell_threshold

        # SELL LOGIC: Check each position
        for pos in self._open_positions:
            profit_pct = ((self._current_price - pos.entry_price) / pos.entry_price) * Decimal(
                "100"
            )

            holding_minutes = (current_time - pos.entry_time).total_seconds() / 60
            amount_btc = pos.amount_usdc / pos.entry_price

            # 1. Trailing stop: price dropped from highest
            if pos.highest_price > pos.entry_price:
                drop_from_high = (
                    (pos.highest_price - self._current_price) / pos.highest_price
                ) * Decimal("100")
                if drop_from_high >= self.trailing_stop_pct:
                    return self._sell_signal(
                        pos,
                        amount_btc,
                        profit_pct,
                        holding_minutes,
                        current_time,
                        reason="trailing_stop",
                        order_type="market",
                        confidence=0.95,
                        extra_reason=f"trailing stop: -{float(drop_from_high):.2f}% from high {float(pos.highest_price):.2f}",
                    )

            # 2. Adaptive profit target
            if profit_pct >= Decimal(str(sell_threshold)):
                limit_price = self._current_price  # Sell at current price as limit
                return self._sell_signal(
                    pos,
                    amount_btc,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="profit_target",
                    order_type="limit",
                    confidence=0.9,
                    extra_reason=f"adaptive profit: {float(profit_pct):.2f}% >= {sell_threshold:.2f}%",
                    limit_price=limit_price,
                )

            # 3. Stop-loss
            if profit_pct <= -Decimal(str(self.stop_loss_pct)):
                return self._sell_signal(
                    pos,
                    amount_btc,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="stop_loss",
                    order_type="market",
                    confidence=1.0,
                    extra_reason=f"STOP-LOSS: {float(profit_pct):.2f}% <= -{self.stop_loss_pct}%",
                )

            # 4. Timeout
            if holding_minutes >= self.max_holding_minutes:
                return self._sell_signal(
                    pos,
                    amount_btc,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="timeout",
                    order_type="market",
                    confidence=0.7,
                    extra_reason=f"TIMEOUT: {holding_minutes:.0f}min >= {self.max_holding_minutes}min",
                )

        # BUY LOGIC
        if len(self._open_positions) >= self.max_open_positions:
            return None
        if self._bought_this_candle:
            return None

        # Zone filter: block buys in overbought 15m
        if self.block_overbought_15m and analysis:
            if analysis.zone_15m == TimeframeZone.OVERBOUGHT:
                return None

        # Volume filter: block buys with insufficient volume
        if analysis and analysis.volume_ratio_5m < self.min_volume_ratio:
            return None

        # Check references for buy signal
        refs_to_check = self._reference_prices
        if self._warming_up and self._warmup_open_price:
            refs_to_check = [self._warmup_open_price]

        for ref_price in refs_to_check:
            if ref_price in self._used_references:
                continue

            drop_pct = ((self._current_price - ref_price) / ref_price) * Decimal("100")

            if drop_pct <= Decimal(str(buy_threshold)):
                self._used_references.add(ref_price)
                self._bought_this_candle = True

                # Calculate limit price (slightly below current for maker)
                offset_pct = Decimal(str(self.settings.order.limit_buy_offset_pct))
                limit_price = self._current_price * (Decimal("1") - offset_pct / Decimal("100"))

                regime_str = analysis.regime.value if analysis else "unknown"

                return TradingSignal(
                    signal_type=SignalType.BUY,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.85,
                    reason=f"Adaptive BUY: {float(drop_pct):.2f}% <= {buy_threshold:.2f}% (regime={regime_str})",
                    strategy=self.bot_id,
                    timestamp=current_time,
                    metadata={
                        "reference_price": float(ref_price),
                        "drop_pct": float(drop_pct),
                        "adaptive_threshold": buy_threshold,
                        "regime": regime_str,
                        "order_type": "limit",
                        "limit_price": float(limit_price),
                        "position_size_multiplier": self.position_size_multiplier,
                    },
                )

        return None

    def _sell_signal(
        self,
        pos: AdaptivePosition,
        amount_btc: Decimal,
        profit_pct: Decimal,
        holding_minutes: float,
        current_time: datetime,
        *,
        reason: str,
        order_type: str,
        confidence: float,
        extra_reason: str,
        limit_price: Decimal | None = None,
    ) -> TradingSignal:
        """Build a SELL signal for a position."""
        metadata: dict[str, Any] = {
            "position_id": pos.position_id,
            "amount_btc": float(amount_btc),
            "entry_price": float(pos.entry_price),
            "reference_price": float(pos.reference_price),
            "profit_pct": float(profit_pct),
            "holding_time_minutes": holding_minutes,
            "reason": reason,
            "order_type": order_type,
        }
        if limit_price is not None:
            metadata["limit_price"] = float(limit_price)

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=self._current_price or Decimal("0"),
            confidence=confidence,
            reason=f"Position #{pos.position_id}: {extra_reason} (held {holding_minutes:.1f}min)",
            strategy=self.bot_id,
            timestamp=current_time,
            metadata=metadata,
        )

    async def on_trade_filled(
        self,
        trade_id: str,
        pair: str,
        side: str,
        amount: Decimal,
        price: Decimal,
        fee: Decimal,
        reference_price: Decimal | None,
        position_id: int | None,
    ) -> None:
        """Track positions after trade execution."""
        if side == "buy":
            if reference_price is None:
                return

            amount_usdc = amount * price
            pid = self._next_position_id
            self._next_position_id += 1

            self._open_positions.append(
                AdaptivePosition(
                    entry_price=price,
                    entry_time=datetime.now(UTC),
                    amount_usdc=amount_usdc,
                    position_id=pid,
                    reference_price=reference_price,
                    highest_price=price,
                )
            )
            self._used_references.add(reference_price)

            self.logger.info(
                "adaptive_position_opened",
                position_id=pid,
                entry_price=float(price),
                reference_price=float(reference_price),
                bot_id=self.bot_id,
            )

        elif side == "sell":
            if position_id is None:
                return

            for i, pos in enumerate(self._open_positions):
                if pos.position_id == position_id:
                    closed = self._open_positions.pop(i)
                    pnl = (price - closed.entry_price) * (
                        closed.amount_usdc / closed.entry_price
                    ) - fee
                    self.logger.info(
                        "adaptive_position_closed",
                        position_id=position_id,
                        pnl=float(pnl),
                        bot_id=self.bot_id,
                    )
                    break

    def _parse_timestamp(self, ohlc_data: dict[str, Any]) -> datetime:
        """Parse timestamp from OHLC data."""
        if "timestamp" not in ohlc_data:
            return datetime.now(UTC)

        ts = ohlc_data["timestamp"]
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return datetime.fromtimestamp(float(ts), tz=UTC)
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=UTC)
        return datetime.now(UTC)

    def get_name(self) -> str:
        """Return strategy name."""
        return "adaptive"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "trailing_stop_pct": float(self.trailing_stop_pct),
            "min_volume_ratio": self.min_volume_ratio,
            "block_overbought_15m": self.block_overbought_15m,
            "max_open_positions": self.max_open_positions,
            "position_size_multiplier": self.position_size_multiplier,
        }

    def reset_state(self) -> None:
        """Reset internal state."""
        super().reset_state()
        self._reference_prices.clear()
        self._current_price = None
        self._open_positions.clear()
        self._used_references.clear()
        self._pending_reference = None
        self._next_position_id = 1
        self._bought_this_candle = False
        self._warming_up = True
        self._warmup_open_price = None

    def add_position(
        self,
        entry_price: Decimal,
        amount_usdc: Decimal,
        reference_price: Decimal,
        entry_time: datetime | None = None,
    ) -> int:
        """Add a position (for backtest compatibility).

        Args:
            entry_price: Entry price.
            amount_usdc: Position size in USDC.
            reference_price: Reference price that triggered entry.
            entry_time: Entry timestamp.

        Returns:
            Position ID.
        """
        pid = self._next_position_id
        self._next_position_id += 1

        self._open_positions.append(
            AdaptivePosition(
                entry_price=entry_price,
                entry_time=entry_time or datetime.now(UTC),
                amount_usdc=amount_usdc,
                position_id=pid,
                reference_price=reference_price,
                highest_price=entry_price,
            )
        )
        self._used_references.add(reference_price)
        return pid

    def close_position(self, position_id: int) -> AdaptivePosition | None:
        """Close a position by ID (for backtest compatibility).

        Args:
            position_id: ID of position to close.

        Returns:
            The closed position, or None.
        """
        for i, pos in enumerate(self._open_positions):
            if pos.position_id == position_id:
                return self._open_positions.pop(i)
        return None

    @property
    def open_positions(self) -> list[AdaptivePosition]:
        """Get list of open positions."""
        return self._open_positions.copy()

    @property
    def open_positions_count(self) -> int:
        """Get number of open positions."""
        return len(self._open_positions)

    @property
    def current_price(self) -> Decimal | None:
        """Get current market price."""
        return self._current_price
