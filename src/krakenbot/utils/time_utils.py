"""Time conversion utilities for OHLC data fetching.

This module provides helpers for converting between different time representations
used by Kraken API, CCXT library, and the internal database format.
"""

from datetime import UTC, datetime, timedelta


def minutes_to_ccxt_timeframe(interval_minutes: int) -> str:
    """Convert interval in minutes to CCXT timeframe string.

    Args:
        interval_minutes: Candle interval in minutes.

    Returns:
        CCXT timeframe string (e.g., "1m", "5m", "15m", "1h", "1d").

    Raises:
        ValueError: If interval is not supported.

    Examples:
        >>> minutes_to_ccxt_timeframe(1)
        '1m'
        >>> minutes_to_ccxt_timeframe(60)
        '1h'
        >>> minutes_to_ccxt_timeframe(1440)
        '1d'
    """
    # Map common intervals
    interval_map = {
        1: "1m",
        5: "5m",
        15: "15m",
        30: "30m",
        60: "1h",
        240: "4h",
        1440: "1d",
        10080: "1w",
        21600: "15d",  # Note: Not all exchanges support this
    }

    if interval_minutes in interval_map:
        return interval_map[interval_minutes]

    # Try to calculate for other intervals
    if interval_minutes < 60:
        return f"{interval_minutes}m"
    elif interval_minutes < 1440:
        hours = interval_minutes // 60
        if interval_minutes % 60 == 0:
            return f"{hours}h"
    elif interval_minutes >= 1440:
        days = interval_minutes // 1440
        if interval_minutes % 1440 == 0:
            return f"{days}d"

    raise ValueError(
        f"Unsupported interval: {interval_minutes} minutes. "
        f"Supported intervals: {sorted(interval_map.keys())}"
    )


def calculate_pagination_steps(
    start_time: datetime,
    end_time: datetime,
    interval_minutes: int,
    limit: int = 720,
) -> list[tuple[datetime, datetime]]:
    """Calculate pagination chunks for fetching historical OHLC data.

    Given a time range and API limit, this function calculates the optimal
    pagination steps to fetch all data without exceeding the API limit.

    Args:
        start_time: Start of the time range (UTC).
        end_time: End of the time range (UTC).
        interval_minutes: Candle interval in minutes.
        limit: Maximum candles per API request (default 720 for Kraken).

    Returns:
        List of (chunk_start, chunk_end) tuples covering the full range.

    Examples:
        >>> start = datetime(2026, 1, 1, tzinfo=UTC)
        >>> end = datetime(2026, 1, 3, tzinfo=UTC)
        >>> steps = calculate_pagination_steps(start, end, 15, limit=720)
        >>> len(steps)
        1
        >>> steps[0][0] == start
        True
    """
    if start_time >= end_time:
        raise ValueError("start_time must be before end_time")

    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")

    if limit <= 0:
        raise ValueError("limit must be positive")

    # Calculate total candles needed
    total_duration = end_time - start_time
    total_minutes = total_duration.total_seconds() / 60
    total_candles = int(total_minutes / interval_minutes)

    if total_candles <= limit:
        # All data fits in one request
        return [(start_time, end_time)]

    # Calculate chunk size in time
    chunk_duration_minutes = limit * interval_minutes
    chunk_duration = timedelta(minutes=chunk_duration_minutes)

    chunks = []
    current_start = start_time

    while current_start < end_time:
        # Calculate chunk end
        current_end = current_start + chunk_duration

        # Don't exceed the final end_time
        if current_end > end_time:
            current_end = end_time

        chunks.append((current_start, current_end))

        # Move to next chunk (start where the last one ended)
        current_start = current_end

    return chunks


def get_max_days_for_interval(interval_minutes: int) -> int:
    """Get recommended maximum days to backfill for a given interval.

    This function returns the safe maximum based on Kraken API retention limits.

    Args:
        interval_minutes: Candle interval in minutes.

    Returns:
        Maximum number of days to safely backfill.

    Examples:
        >>> get_max_days_for_interval(1)
        7
        >>> get_max_days_for_interval(15)
        90
        >>> get_max_days_for_interval(60)
        365
    """
    # Conservative limits based on Kraken API data retention
    if interval_minutes == 1:
        return 7  # 1min: ~7 days
    elif interval_minutes == 5:
        return 30  # 5min: ~30 days
    elif interval_minutes == 15:
        return 90  # 15min: ~90 days
    elif interval_minutes == 30:
        return 180  # 30min: ~180 days
    elif interval_minutes == 60:
        return 365  # 1h: ~1 year
    elif interval_minutes == 240:
        return 730  # 4h: ~2 years
    elif interval_minutes >= 1440:
        return 3285  # 1d/1w: ~9 years (available via Binance since 2017)
    else:
        # Unknown interval, use conservative default
        return 30


def calculate_total_candles(
    start_time: datetime,
    end_time: datetime,
    interval_minutes: int,
) -> int:
    """Calculate total number of candles in a time range.

    Args:
        start_time: Start of the time range (UTC).
        end_time: End of the time range (UTC).
        interval_minutes: Candle interval in minutes.

    Returns:
        Estimated number of candles.

    Examples:
        >>> start = datetime(2026, 1, 1, tzinfo=UTC)
        >>> end = datetime(2026, 1, 2, tzinfo=UTC)
        >>> calculate_total_candles(start, end, 15)
        96
    """
    total_duration = end_time - start_time
    total_minutes = total_duration.total_seconds() / 60
    return int(total_minutes / interval_minutes)


def ms_to_datetime(ms: int) -> datetime:
    """Exact epoch-milliseconds → aware UTC datetime (no float rounding)."""
    return datetime.fromtimestamp(ms // 1000, tz=UTC) + timedelta(milliseconds=ms % 1000)
