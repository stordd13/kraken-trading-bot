"""Gemini Retour Moyenne — mean reversion with Bollinger + RSI divergence + DCA.

Range detection (1h):
- ADX(14) < 20 on 1h = no trend, range-bound market

Entry (15m):
- Price touches BB lower band on 15m
- RSI divergence: price makes lower low, RSI(14) makes higher low (bullish)
- DCA: 3 levels spaced 0.5% below BB lower

Exit:
- Take-profit at BB middle band on 15m (LIMIT)
- Stop-loss: 2.0 × ATR(14, "15m") below lowest DCA entry (MARKET)

This is a short-term range-bound strategy — positions last hours to a day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus
    from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


@dataclass
class MeanRevPosition:
    """Tracked mean reversion position with DCA levels."""

    position_id: int
    entries: list[dict[str, Decimal]] = field(default_factory=list)  # [{price, amount_usdc}]
    avg_entry_price: Decimal = _ZERO
    total_usdc: Decimal = _ZERO
    stop_loss: Decimal = _ZERO
    entry_time: datetime = field(default_factory=lambda: datetime.now(UTC))


class GeminiRetourMoyenne(BaseStrategy):
    """Mean reversion strategy using Bollinger Bands + RSI divergence.

    Detects range-bound markets via ADX < 20 on 1h.
    Enters on BB lower touch on 15m with RSI bullish divergence.
    DCA 3 levels spaced 0.5% below BB lower for better avg entry.
    Exits at BB middle band.
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
        super().__init__(
            settings,
            event_bus,
            db_manager,
            bot_id=bot_id,
            strategy_params=strategy_params,
            analyzer=analyzer,
        )

        params = strategy_params or {}
        self.pair = self.effective_pair

        # Range detection
        self.adx_range_max = Decimal(str(params.get("adx_range_max", 20)))

        # DCA config
        self.dca_levels: int = params.get("dca_levels", 3)
        self.dca_spacing_pct = Decimal(str(params.get("dca_spacing_pct", 0.5)))

        # Stop-loss
        self.sl_atr_mult = Decimal(str(params.get("sl_atr_mult", 2.0)))

        # RSI divergence lookback (number of 15m candles)
        self.divergence_lookback: int = params.get("divergence_lookback", 10)

        # Budget & position sizing
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 25)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 15.0)))
        self.max_open_positions: int = params.get("max_open_positions", 2)
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Internal state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._open_positions: list[MeanRevPosition] = []
        self._next_position_id: int = 1

        # RSI divergence tracking on 15m
        self._price_lows_15m: list[Decimal] = []
        self._rsi_lows_15m: list[Decimal] = []

        self.logger.info(
            "gemini_mean_reversion_initialized",
            bot_id=self.bot_id,
            order_size_usdc=float(self.order_size_usdc),
            max_allocation_pct=float(self.max_allocation_pct),
            adx_range_max=float(self.adx_range_max),
            dca_levels=self.dca_levels,
            dca_spacing_pct=float(self.dca_spacing_pct),
            sl_atr_mult=float(self.sl_atr_mult),
        )

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        if tick_data.get("pair") != self.pair:
            return
        self._current_price = Decimal(str(tick_data["price"]))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        if ohlc_data.get("pair") != self.pair:
            return

        close = Decimal(str(ohlc_data["close"]))
        low = Decimal(str(ohlc_data.get("low", close)))
        interval = ohlc_data.get("interval", 5)
        self._current_price = close

        # Update shared analyzer for ALL timeframes
        if self.analyzer is not None:
            self.analyzer.update(ohlc_data, interval)

        self._current_timestamp = self._parse_timestamp(ohlc_data)

        # Track price lows and RSI lows on 15m for divergence detection
        if interval == 15 and ohlc_data.get("is_complete", False):
            self._track_divergence(low)

    async def generate_signal(self) -> TradingSignal | None:
        if self._current_price is None or self.analyzer is None:
            return None

        now = self._current_timestamp or datetime.now(UTC)

        # --- SELL LOGIC ---
        for pos in self._open_positions:
            sell = self._check_exit(pos, now)
            if sell is not None:
                return sell

        # --- BUY LOGIC ---
        if len(self._open_positions) >= self.max_open_positions:
            return None

        return self._check_entry(now)

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(self, pos: MeanRevPosition, now: datetime) -> TradingSignal | None:
        if self._current_price is None or self.analyzer is None:
            return None

        if pos.avg_entry_price <= _ZERO:
            return None

        profit_pct = (self._current_price - pos.avg_entry_price) / pos.avg_entry_price * _HUNDRED

        # Exit 1: Stop-loss
        if self._current_price <= pos.stop_loss:
            return self._make_sell_signal(
                pos,
                now,
                reason="stop_loss",
                order_type="market",
                confidence=1.0,
                extra=(
                    f"STOP-LOSS: {float(self._current_price):.2f} "
                    f"<= {float(pos.stop_loss):.2f} ({float(profit_pct):.2f}%)"
                ),
            )

        # Exit 2: Take-profit at BB middle
        bb = self.analyzer.get_bollinger("15m")
        if bb is not None:
            bb_middle = bb["middle"]
            if self._current_price >= bb_middle:
                return self._make_sell_signal(
                    pos,
                    now,
                    reason="take_profit_bb_middle",
                    order_type="limit",
                    confidence=0.9,
                    extra=(f"TP BB middle: {float(bb_middle):.2f} ({float(profit_pct):.2f}%)"),
                    limit_price=bb_middle,
                )

        return None

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(self, now: datetime) -> TradingSignal | None:
        if self.analyzer is None or self._current_price is None:
            return None

        # Condition 1: Range market — ADX(14) < threshold on 1h
        adx_1h = self.analyzer.get_adx("1h")
        if adx_1h is None or adx_1h >= self.adx_range_max:
            return None

        # Condition 2: Price near BB lower on 15m
        bb = self.analyzer.get_bollinger("15m")
        if bb is None:
            return None

        bb_lower = bb["lower"]
        bb_middle = bb["middle"]

        # Price must be at or below BB lower
        if self._current_price > bb_lower:
            return None

        # Condition 3: RSI bullish divergence on 15m
        if not self._detect_rsi_divergence():
            return None

        # ATR for stop-loss
        atr = self.analyzer.get_atr(14, "15m")
        if atr is None or atr <= _ZERO:
            return None

        # Calculate DCA levels below BB lower
        # Level 0 = BB lower, Level 1 = BB lower - 0.5%, Level 2 = BB lower - 1.0%
        dca_base = bb_lower
        lowest_dca = (
            dca_base
            * (_HUNDRED - self.dca_spacing_pct * Decimal(str(self.dca_levels - 1)))
            / _HUNDRED
        )
        stop_loss = lowest_dca - self.sl_atr_mult * atr

        # First DCA level: buy at BB lower (limit)
        limit_price = dca_base * Decimal("0.999")  # Maker fee offset

        rsi_15m = self.analyzer.get_rsi(14, "15m")

        self.logger.info(
            "mean_rev_buy_signal",
            adx_1h=float(adx_1h),
            bb_lower=float(bb_lower),
            bb_middle=float(bb_middle),
            rsi_15m=float(rsi_15m) if rsi_15m else None,
            entry=float(self._current_price),
            sl=float(stop_loss),
            dca_levels=self.dca_levels,
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=self._current_price,
            confidence=0.75,
            reason=(
                f"MEAN REV BUY: BB lower touch + RSI divergence "
                f"(ADX={float(adx_1h):.1f}, DCA level 1/{self.dca_levels})"
            ),
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "order_type": "limit",
                "limit_price": float(limit_price),
                "order_size_usdc": float(self.order_size_usdc),
                "max_allocation_pct": float(self.max_allocation_pct),
                "position_size_multiplier": self._position_size_multiplier,
                "risk_stop_loss": float(stop_loss),
                "risk_take_profit": float(bb_middle),
                "bb_lower": float(bb_lower),
                "bb_middle": float(bb_middle),
                "adx_1h": float(adx_1h),
                "rsi_15m": float(rsi_15m) if rsi_15m else None,
                "dca_level": 1,
                "dca_total_levels": self.dca_levels,
                "dca_spacing_pct": float(self.dca_spacing_pct),
            },
        )

    # ------------------------------------------------------------------
    # RSI Divergence Detection
    # ------------------------------------------------------------------

    def _track_divergence(self, low_15m: Decimal) -> None:
        """Track price lows and RSI lows on 15m for divergence detection."""
        if self.analyzer is None:
            return
        rsi = self.analyzer.get_rsi(14, "15m")
        if rsi is None:
            return

        self._price_lows_15m.append(low_15m)
        self._rsi_lows_15m.append(rsi)

        # Keep only lookback window
        if len(self._price_lows_15m) > self.divergence_lookback:
            self._price_lows_15m.pop(0)
            self._rsi_lows_15m.pop(0)

    def _detect_rsi_divergence(self) -> bool:
        """Detect bullish RSI divergence: price lower low + RSI higher low.

        Looks at the last N 15m candles for a divergence pattern.
        Returns True if found.
        """
        if len(self._price_lows_15m) < 3:
            return False

        # Find last two local lows in price
        # Simple: compare current vs minimum in the first half of window
        mid = len(self._price_lows_15m) // 2
        first_half_prices = self._price_lows_15m[:mid]
        second_half_prices = self._price_lows_15m[mid:]
        first_half_rsi = self._rsi_lows_15m[:mid]
        second_half_rsi = self._rsi_lows_15m[mid:]

        if not first_half_prices or not second_half_prices:
            return False

        # Price: second half has a lower low than first half
        price_low_1 = min(first_half_prices)
        price_low_2 = min(second_half_prices)
        price_lower_low = price_low_2 < price_low_1

        # RSI: second half has a higher low than first half (divergence)
        rsi_low_1 = min(first_half_rsi)
        rsi_low_2 = min(second_half_rsi)
        rsi_higher_low = rsi_low_2 > rsi_low_1

        return price_lower_low and rsi_higher_low

    # ------------------------------------------------------------------
    # Sell signal builder
    # ------------------------------------------------------------------

    def _make_sell_signal(
        self,
        pos: MeanRevPosition,
        now: datetime,
        *,
        reason: str,
        order_type: str,
        confidence: float,
        extra: str,
        limit_price: Decimal | None = None,
    ) -> TradingSignal:
        total_btc = pos.total_usdc / pos.avg_entry_price if pos.avg_entry_price > _ZERO else _ZERO
        profit_pct = (
            (self._current_price - pos.avg_entry_price) / pos.avg_entry_price * _HUNDRED
            if self._current_price and pos.avg_entry_price > _ZERO
            else _ZERO
        )

        metadata: dict[str, Any] = {
            "position_id": pos.position_id,
            "amount_btc": float(total_btc),
            "entry_price": float(pos.avg_entry_price),
            "profit_pct": float(profit_pct),
            "dca_entries": len(pos.entries),
            "reason": reason,
            "order_type": order_type,
        }
        if limit_price is not None:
            metadata["limit_price"] = float(limit_price)

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=self._current_price or _ZERO,
            confidence=confidence,
            reason=f"Position #{pos.position_id}: {extra}",
            strategy=self.bot_id,
            timestamp=now,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Trade filled callback
    # ------------------------------------------------------------------

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
        if side == "buy":
            amount_usdc = amount * price

            # Check if we should add to existing position (DCA) or open new
            if self._open_positions and len(self._open_positions[-1].entries) < self.dca_levels:
                pos = self._open_positions[-1]
                pos.entries.append({"price": price, "amount_usdc": amount_usdc})
                pos.total_usdc += amount_usdc
                # Recalculate weighted average
                total_weighted = sum(e["price"] * e["amount_usdc"] for e in pos.entries)
                pos.avg_entry_price = total_weighted / pos.total_usdc

                # Update stop-loss based on lowest entry
                atr = self.analyzer.get_atr(14, "15m") if self.analyzer else None
                if atr and atr > _ZERO:
                    lowest_entry = min(e["price"] for e in pos.entries)
                    pos.stop_loss = lowest_entry - self.sl_atr_mult * atr

                self.logger.info(
                    "mean_rev_dca_added",
                    position_id=pos.position_id,
                    dca_level=len(pos.entries),
                    avg_entry=float(pos.avg_entry_price),
                    bot_id=self.bot_id,
                )
            else:
                # New position
                pid = self._next_position_id
                self._next_position_id += 1

                atr = self.analyzer.get_atr(14, "15m") if self.analyzer else None
                sl_dist = self.sl_atr_mult * atr if atr and atr > _ZERO else price * Decimal("0.02")

                pos = MeanRevPosition(
                    position_id=pid,
                    entries=[{"price": price, "amount_usdc": amount_usdc}],
                    avg_entry_price=price,
                    total_usdc=amount_usdc,
                    stop_loss=price - sl_dist,
                    entry_time=datetime.now(UTC),
                )
                self._open_positions.append(pos)
                self.logger.info(
                    "mean_rev_position_opened",
                    position_id=pid,
                    entry=float(price),
                    sl=float(pos.stop_loss),
                    bot_id=self.bot_id,
                )

        elif side == "sell":
            if position_id is None:
                return
            for i, pos in enumerate(self._open_positions):
                if pos.position_id == position_id:
                    closed = self._open_positions.pop(i)
                    total_btc = closed.total_usdc / closed.avg_entry_price
                    pnl = (price - closed.avg_entry_price) * total_btc - fee
                    self.logger.info(
                        "mean_rev_position_closed",
                        position_id=position_id,
                        pnl=float(pnl),
                        dca_entries=len(closed.entries),
                        bot_id=self.bot_id,
                    )
                    break

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_timestamp(self, ohlc_data: dict[str, Any]) -> datetime:
        ts = ohlc_data.get("timestamp")
        if ts is None:
            return datetime.now(UTC)
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
        return "gemini_retour_moyenne"

    def get_config(self) -> dict[str, Any]:
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "adx_range_max": float(self.adx_range_max),
            "dca_levels": self.dca_levels,
            "dca_spacing_pct": float(self.dca_spacing_pct),
            "sl_atr_mult": float(self.sl_atr_mult),
            "max_open_positions": self.max_open_positions,
            "open_positions": len(self._open_positions),
        }
