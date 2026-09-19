"""C2 (preuve 1, réel) — on the real grid quick window (BTC/USDC 2025-03-01 → 2025-03-15,
Binance data, --fees bybit, class defaults) every input the grid decision consumed is
recomputed independently from the candles the engine really loaded (its ``warmup`` report
gives the window), using only the candles closed at each decision instant.

DB-gated: skipped when the SSH tunnel / local Postgres is unreachable (same pattern as
``test_grid_atr_v4_backward_compat.py``).
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import socket
import sys

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))

from test_scripts.test_c2_replay_fidelity import _atr_wilder, _regime, _rel_close


def _db_reachable() -> bool:
    for port in (5433, 5432):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            continue
    return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="Database not reachable")

PAIR = "BTC/USDC"
START = datetime(2025, 3, 1, tzinfo=UTC)
END = datetime(2025, 3, 15, tzinfo=UTC)


@pytest.mark.asyncio
async def test_grid_quick_window_decision_inputs_db() -> None:
    from dotenv import load_dotenv

    load_dotenv(_project_root / ".env")
    from krakenbot.config.settings import get_settings
    from krakenbot.core.database import DatabaseManager
    from scripts.backtest import GridBacktester, _load_candles_chunked

    settings = get_settings()
    db = DatabaseManager()
    await db.init_db(settings)
    try:
        engine = GridBacktester(
            settings,
            db,
            fee_model="bybit",
            strategy_name="grok_grid_atr_adaptive_v4",
            candle_interval=5,
            exchange="binance",
            starting_capital=1000.0,
        )
        await engine.run(PAIR, START, END)
        trace = engine.decision_trace
        assert len(trace) == 14 * 6 + 1  # every 4h close from START to END inclusive
        windows = {
            tf: datetime.fromisoformat(engine.warmup[tf]["first"]) for tf in ("4h", "1d", "1w")
        }
        series = {}
        for tf, interval in (("4h", 240), ("1d", 1440), ("1w", 10080)):
            series[tf] = await _load_candles_chunked(
                db, PAIR, interval, windows[tf], END, exchange="binance"
            )
    finally:
        await db.close_db()

    for entry in trace[::7] + [trace[-1]]:
        T = entry["timestamp"]
        closed = {tf: [c for c in series[tf] if c.timestamp <= T] for tf in series}
        assert _rel_close(entry["atr_4h"], _atr_wilder(closed["4h"], 14)), T
        assert entry["regime_1d"] == _regime(closed["1d"]), T
        assert entry["regime_1w"] == _regime(closed["1w"]), T
        nxt = [c for c in series["4h"] if c.timestamp > T][:1]
        if nxt:
            assert not _rel_close(entry["atr_4h"], _atr_wilder(closed["4h"] + nxt, 14))
    assert engine.warmup["4h"]["sufficient"] and engine.warmup["1d"]["loaded"] >= 50
    assert isinstance(trace[0]["atr_4h"], Decimal)
