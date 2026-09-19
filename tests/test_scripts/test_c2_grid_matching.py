"""C2 (R4, dette 14) — grid sell fills close the lot they designate, and nothing else.

Strategy side (``grok_grid_atr_adaptive_v4.on_trade_filled``): matching by ``position_id``
without any price fallback; without an id, the unique open lot at the fill price; unknown /
absent / ambiguous attribution is logged and counted and the callback ends without removing a
lot or placing a replacement BUY. Engine side (``GridBacktester._process_grok_grid_sell_fill``):
the lot is validated before any balance mutation; the quantity sold is the lot's; a strategy
that fails to close the designated lot is a replay-invariant violation.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "src"))

from krakenbot.core.event_bus import EventBus
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import (
    GridATRLevel,
    GridATRPosition,
    GrokGridATRAdaptiveV4,
)

T0 = datetime(2025, 3, 1, tzinfo=UTC)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        multi_strategy=SimpleNamespace(enabled=False, strategies=[]),
        trading=SimpleNamespace(pair="SOL/USDC", default_order_amount_eur=50),
    )


def _strategy(skip_db_sync: bool = True) -> GrokGridATRAdaptiveV4:
    strategy = GrokGridATRAdaptiveV4(
        settings=_settings(),
        event_bus=EventBus(),
        db_manager=MagicMock(),
        bot_id="grid_atr_sol",
        strategy_params={"pair": "SOL/USDC", "order_size_usdc": 25, "min_spacing_pct": 0.015},
        analyzer=MagicMock(),
    )
    strategy._skip_db_sync = skip_db_sync
    strategy._running = True
    strategy._grid_spacing = Decimal("0.015")
    strategy._current_price = Decimal("180")
    strategy._current_timestamp = T0
    return strategy


def _lot(strategy: GrokGridATRAdaptiveV4, entry: str, sell_level: str) -> GridATRPosition:
    pid = strategy._next_position_id
    strategy._next_position_id += 1
    amount = (Decimal("25") * Decimal("0.999")) / Decimal(entry)
    pos = GridATRPosition(
        position_id=pid,
        entry_price=Decimal(entry),
        entry_time=T0,
        amount_btc=amount,
        amount_usdc=amount * Decimal(entry),
        sell_level=Decimal(sell_level),
    )
    strategy._grid_positions.append(pos)
    return pos


async def _sell(strategy: GrokGridATRAdaptiveV4, price: str, position_id: int | None) -> None:
    await strategy.on_trade_filled(
        trade_id="t",
        pair="SOL/USDC",
        side="sell",
        amount=Decimal("0.13"),
        price=Decimal(price),
        fee=Decimal("0.02"),
        reference_price=None,
        position_id=position_id,
    )


def _pending_buys(strategy: GrokGridATRAdaptiveV4) -> list[Decimal]:
    return sorted(
        level.price
        for level in strategy._grid_levels.values()
        if level.side == "buy" and level.status == "pending"
    )


# ---------------------------------------------------------------------------
# Strategy: id present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_by_position_id_closes_the_designated_lot_only() -> None:
    s = _strategy()
    older = _lot(s, "178.2", "180.9")  # the SOL double-pop shape: |180.9 - 180.3| < 1 USD
    newer = _lot(s, "177.6", "180.3")
    await _sell(s, "180.3", newer.position_id)
    assert [p.position_id for p in s.open_positions] == [older.position_id]
    assert s._completed_pairs == 1
    assert _pending_buys(s) == [Decimal("177.6")]  # 180.3 * (1 - 0.015) quantized
    assert all(v == 0 for v in s.fill_anomalies.values())


@pytest.mark.asyncio
async def test_two_lots_with_strictly_identical_sell_level_the_id_decides() -> None:
    s = _strategy()
    a = _lot(s, "177.6", "180.3")
    b = _lot(s, "177.7", "180.3")
    await _sell(s, "180.3", b.position_id)
    assert [p.position_id for p in s.open_positions] == [a.position_id]
    await _sell(s, "180.3", a.position_id)
    assert s.open_positions == []
    assert s._completed_pairs == 2
    assert all(v == 0 for v in s.fill_anomalies.values())


@pytest.mark.asyncio
async def test_unknown_position_id_is_counted_and_changes_nothing() -> None:
    s = _strategy()
    kept = _lot(s, "177.6", "180.3")
    before_levels = dict(s._grid_levels)
    await _sell(s, "180.3", 999)
    assert s.open_positions == [kept]
    assert s._grid_levels == before_levels  # no replacement BUY
    assert s._completed_pairs == 0 and s._total_grid_profit == 0
    assert s.fill_anomalies["unmatched_position_id"] == 1


@pytest.mark.asyncio
async def test_fill_below_the_designated_level_is_counted_but_the_id_decides() -> None:
    s = _strategy()
    lot = _lot(s, "177.6", "180.3")
    await _sell(s, "180.2", lot.position_id)
    assert s.open_positions == []
    assert s.fill_anomalies["incoherent_sell_fill"] == 1


# ---------------------------------------------------------------------------
# Strategy: id absent (nominal live path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_id_unique_lot_at_the_fill_price_is_closed() -> None:
    s = _strategy()
    _lot(s, "178.2", "180.9")
    target = _lot(s, "177.6", "180.3")
    await _sell(s, "180.30", None)  # Decimal('180.30') == Decimal('180.3')
    assert target not in s.open_positions and len(s.open_positions) == 1
    assert _pending_buys(s) == [Decimal("177.6")]
    assert all(v == 0 for v in s.fill_anomalies.values())


@pytest.mark.asyncio
async def test_no_id_zero_or_several_candidates_need_reconciliation() -> None:
    s = _strategy()
    _lot(s, "178.2", "180.9")
    before = list(s.open_positions)
    await _sell(s, "180.3", None)  # no lot at that level: the old code would have popped 180.9
    assert s.open_positions == before
    assert _pending_buys(s) == []
    assert s.fill_anomalies["unmatched_sell_fills"] == 1

    _lot(s, "177.6", "180.3")
    _lot(s, "177.7", "180.3")
    before = list(s.open_positions)
    await _sell(s, "180.3", None)
    assert s.open_positions == before
    assert _pending_buys(s) == []
    assert s.fill_anomalies["ambiguous_sell_fill"] == 1


# ---------------------------------------------------------------------------
# The B4 SOL double pop, reproduced: old matching vs new
# ---------------------------------------------------------------------------


def _old_pop(positions: list[GridATRPosition], price: Decimal) -> GridATRPosition | None:
    """The pre-C2 strategy matching, verbatim: first lot within 1 USD of the fill price."""
    for i, pos in enumerate(positions):
        if abs(pos.sell_level - price) < Decimal("1"):
            return positions.pop(i)
    return None


@pytest.mark.asyncio
async def test_old_proximity_matching_sold_the_same_lot_twice_the_new_one_does_not() -> None:
    # Lot B (older, target 180.9) sits before lot A (newer, target 180.3); a candle high of
    # 180.5 fills A's order only. The engine debits by id (A) on both sides of the change.
    s = _strategy()
    b = _lot(s, "178.2", "180.9")
    a = _lot(s, "177.6", "180.3")

    # OLD: the strategy pops B (|180.9 - 180.3| < 1); A's order stays pending and fills again
    # on the next candle -> A sold twice, B never sold (inventory divergence of B4).
    old_positions = [b, a]
    assert _old_pop(old_positions, Decimal("180.3")) is b
    assert _old_pop(old_positions, Decimal("180.3")) is a
    assert old_positions == []  # two sales booked for A's price, both lots gone on paper

    # NEW: the first fill closes A by id; a second fill for A is unknown -> rejected, counted;
    # B is intact with its own order.
    await _sell(s, "180.3", a.position_id)
    await _sell(s, "180.3", a.position_id)
    assert [p.position_id for p in s.open_positions] == [b.position_id]
    assert s._completed_pairs == 1
    assert s.fill_anomalies["unmatched_position_id"] == 1


# ---------------------------------------------------------------------------
# Paired SELL signal metadata (live path): amount_btc, no position_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paired_sell_signal_carries_amount_btc_and_no_position_id() -> None:
    s = _strategy(skip_db_sync=False)
    published: list[dict] = []

    async def publish(_event_type, payload):  # noqa: ANN001
        published.append(payload)

    s.event_bus = SimpleNamespace(publish=publish)
    await s.on_trade_filled(
        trade_id="t",
        pair="SOL/USDC",
        side="buy",
        amount=Decimal("0.1400"),
        price=Decimal("177.6"),
        fee=Decimal("0.025"),
        reference_price=None,
        position_id=None,
    )
    assert len(published) == 1
    signal = published[0]["signal"]
    assert signal.signal_type.value == "sell"
    assert signal.metadata["amount_btc"] == 0.14
    assert "position_id" not in signal.metadata  # decision 3: non-correspondance documentée
    assert signal.metadata["limit_price"] == float(s.open_positions[0].sell_level)

    # naked grid levels (built from the center) carry neither key
    published.clear()
    await s._emit_grid_signal(
        GridATRLevel(
            price=Decimal("176.0"), side="buy", status="pending", amount_usdc=Decimal("25")
        )
    )
    assert "amount_btc" not in published[0]["signal"].metadata
    assert "position_id" not in published[0]["signal"].metadata


def test_get_config_exposes_the_fill_anomaly_counters() -> None:
    s = _strategy()
    assert s.get_config()["fill_anomalies"] == {
        "unmatched_position_id": 0,
        "unmatched_sell_fills": 0,
        "ambiguous_sell_fill": 0,
        "incoherent_sell_fill": 0,
    }


# ---------------------------------------------------------------------------
# Engine: validate before mutate, the lot's quantity, post-condition, temporal eligibility
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_grid_terminal_liquidation import (  # noqa: E402
    LEVEL,
    ORDER,
    _engine,
    _flat,
    _run,
)

from test_scripts.test_grid_terminal_liquidation import (
    _candle as _engine_candle,
)


def _snapshot(engine) -> tuple:  # noqa: ANN001
    return (
        engine.usdc_balance,
        engine.btc_held,
        engine.total_fees,
        len(engine.metrics.trades),
        engine.pairs_completed,
        engine.metrics.total_pnl,
    )


async def _engine_with_two_lots():  # noqa: ANN202
    """Real engine + real strategy: two lots bought at 100000 and 100500 (sell targets
    102000 / 102500 with spacing 2 %), no candle replay — fills are driven by hand."""
    engine = _engine("bybit")
    strategy, _analyzer = await engine._create_grok_grid_strategy()
    strategy._grid_spacing = Decimal("0.02")
    strategy._current_timestamp = T0
    for price in (Decimal("100000"), Decimal("100500")):
        level = GridATRLevel(price=price, side="buy", status="pending", amount_usdc=ORDER)
        strategy._grid_levels[f"buy_{price}"] = level
        order = {
            "order_id": f"buy_{price}",
            "side": "buy",
            "price": price,
            "amount_usdc": ORDER,
            "level": level,
        }
        await engine._process_grok_grid_buy_fill(
            strategy, order, _engine_candle(0, "100600", "100600", "99900", "100000")
        )
    assert len(strategy.open_positions) == 2
    return engine, strategy


def _sell_order(position) -> dict:  # noqa: ANN001
    return {
        "order_id": f"sell_pos_{position.position_id}",
        "side": "sell",
        "price": position.sell_level,
        "amount_btc": position.amount_btc,
        "position_id": position.position_id,
    }


@pytest.mark.asyncio
async def test_engine_sell_fill_closes_the_designated_lot_with_its_quantity_and_cost_basis() -> (
    None
):
    engine, strategy = await _engine_with_two_lots()
    bought = sum(t.amount_crypto for t in engine.metrics.trades)
    first, second = strategy.open_positions
    candle = _engine_candle(1, "103000", "103000", "101900", "102600")

    await engine._process_grok_grid_sell_fill(strategy, _sell_order(second), candle)
    # 1. the designated lot is removed, the other preserved
    assert [p.position_id for p in strategy.open_positions] == [first.position_id]
    sell = engine.metrics.trades[-1]
    # 2. quantity sold == the lot's quantity
    assert sell.amount_crypto == second.amount_btc
    # 3. the P&L cost basis is the designated lot's
    assert sell.pnl == sell.amount_usdc - sell.fee - second.amount_btc * second.entry_price
    # 4. no oversell: cumulative sold <= cumulative bought, inventory reconciles
    sold = sum(t.amount_crypto for t in engine.metrics.trades if t.side.value == "sell")
    assert sold <= bought and engine.btc_held == bought - sold == first.amount_btc

    await engine._process_grok_grid_sell_fill(strategy, _sell_order(first), candle)
    assert strategy.open_positions == []
    sold = sum(t.amount_crypto for t in engine.metrics.trades if t.side.value == "sell")
    assert sold == bought and engine.btc_held == 0
    assert engine.pairs_completed == 2 and engine.metrics.winning_trades == 2


@pytest.mark.asyncio
async def test_engine_rejects_an_unknown_position_id_before_any_mutation() -> None:
    engine, strategy = await _engine_with_two_lots()
    first, second = strategy.open_positions
    before = _snapshot(engine)
    ghost = dict(_sell_order(first), order_id="sell_pos_999", position_id=999)
    await engine._process_grok_grid_sell_fill(
        strategy, ghost, _engine_candle(1, "103000", "103000", "101900", "102600")
    )
    # 5. no accounting mutation at all: balances, inventory, fees, trades, pairs, pnl
    assert _snapshot(engine) == before
    assert [p.position_id for p in strategy.open_positions] == [
        first.position_id,
        second.position_id,
    ]


@pytest.mark.asyncio
async def test_engine_rejects_an_inventory_shortfall_before_any_mutation() -> None:
    engine, strategy = await _engine_with_two_lots()
    first, _second = strategy.open_positions
    engine.btc_held = first.amount_btc / 2  # corrupted wallet: cannot cover the lot
    before = _snapshot(engine)
    await engine._process_grok_grid_sell_fill(
        strategy, _sell_order(first), _engine_candle(1, "103000", "103000", "101900", "102600")
    )
    assert _snapshot(engine) == before
    assert len(strategy.open_positions) == 2


@pytest.mark.asyncio
async def test_engine_raises_when_the_order_quantity_is_not_the_lots() -> None:
    engine, strategy = await _engine_with_two_lots()
    first, _second = strategy.open_positions
    wrong = dict(_sell_order(first), amount_btc=first.amount_btc * 2)
    with pytest.raises(RuntimeError, match="replay invariant"):
        await engine._process_grok_grid_sell_fill(
            strategy, wrong, _engine_candle(1, "103000", "103000", "101900", "102600")
        )
    assert len(strategy.open_positions) == 2  # nothing moved


@pytest.mark.asyncio
async def test_engine_raises_when_the_strategy_does_not_close_the_designated_lot() -> None:
    engine, strategy = await _engine_with_two_lots()
    first, _second = strategy.open_positions

    async def keep_everything(**kwargs):  # noqa: ANN003, ANN202
        return None  # a strategy that ignores the fill

    strategy.on_trade_filled = keep_everything  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="still open"):
        await engine._process_grok_grid_sell_fill(
            strategy, _sell_order(first), _engine_candle(1, "103000", "103000", "101900", "102600")
        )


@pytest.mark.asyncio
async def test_sell_created_by_the_buy_callback_at_T_is_not_eligible_on_the_candle_of_T() -> None:
    # candle 0 fills the seeded BUY at 100000 (low 99500) and its high (103000) is above the
    # paired sell target (102000, spacing 2 %): the sell created by the callback at T must
    # wait for the next candle; candle 1 (high 103000) fills it.
    candles = [
        _engine_candle(0, "100500", "103000", "99500", "100000"),
        _engine_candle(1, "100000", "103000", "99900", "102500"),
    ] + [_flat(i, "101000") for i in range(2, 12)]  # run() needs >= 10 candles
    engine = await _run(_engine("bybit"), candles)
    sides = [(t.side.value, t.timestamp) for t in engine.metrics.trades if not t.forced_liquidation]
    assert sides == [("buy", candles[0].timestamp), ("sell", candles[1].timestamp)]
    assert engine.pairs_completed == 1 and engine.metrics.trades[1].price == LEVEL * Decimal("1.02")


@pytest.mark.asyncio
async def test_engine_sells_a_lot_short_by_decimal_dust_but_rejects_a_real_shortfall() -> None:
    """The running sum btc_held is prec-28 arithmetic: after other lots were sold it can sit
    ~1e-29 BTC below the last lot's exact amount. That is dust, not inventory: the sale
    proceeds (pre-C2 the guard silently blocked such a lot until the terminal liquidation).
    A shortfall beyond the dust threshold is still a counted skip with no mutation."""
    engine, strategy = await _engine_with_two_lots()
    first, second = strategy.open_positions
    candle = _engine_candle(1, "103000", "103000", "101900", "102600")
    engine.btc_held = first.amount_btc + second.amount_btc - Decimal("1E-29")  # dust short
    await engine._process_grok_grid_sell_fill(strategy, _sell_order(second), candle)
    await engine._process_grok_grid_sell_fill(strategy, _sell_order(first), candle)
    assert strategy.open_positions == [] and engine.pairs_completed == 2
    assert abs(engine.btc_held) <= engine._INVENTORY_DUST_BTC
    assert engine.rejections.by_cause["insufficient_inventory"] == 0

    engine2, strategy2 = await _engine_with_two_lots()
    lot = strategy2.open_positions[0]
    engine2.btc_held = lot.amount_btc - Decimal("1E-9")  # a real shortfall (> dust)
    before = _snapshot(engine2)
    await engine2._process_grok_grid_sell_fill(strategy2, _sell_order(lot), candle)
    assert _snapshot(engine2) == before and len(strategy2.open_positions) == 2
    assert engine2.rejections.by_cause["insufficient_inventory"] == 1
