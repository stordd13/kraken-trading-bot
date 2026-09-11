"""Market-data maintenance: exchange-agnostic OHLC gap detection and REST backfill."""

from krakenbot.data.backfill import (
    BackfillSummary,
    Gap,
    GapResult,
    backfill_gaps,
    candle_to_row,
    detect_gaps,
    fetch_max_timestamps,
    fetch_timestamp_bounds,
    fill_gap,
    floor_to_grid,
    insert_candles,
    internal_gaps_from_rows,
    is_grid_aligned,
    last_closed_timestamp,
    tail_gap,
)

__all__ = [
    "BackfillSummary",
    "Gap",
    "GapResult",
    "backfill_gaps",
    "candle_to_row",
    "detect_gaps",
    "fetch_max_timestamps",
    "fetch_timestamp_bounds",
    "fill_gap",
    "floor_to_grid",
    "insert_candles",
    "internal_gaps_from_rows",
    "is_grid_aligned",
    "last_closed_timestamp",
    "tail_gap",
]
