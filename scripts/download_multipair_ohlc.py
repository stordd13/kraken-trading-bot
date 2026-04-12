"""Download historical OHLC data for ETH/USDC and SOL/USDC.

Uses Binance via ccxt (public API, no key needed) for deep historical data.
Kraken's REST API is limited to ~720 most recent candles per interval.
Binance provides full history from pair inception.

Data is stored as ETH/USDC and SOL/USDC in the DB (same format as XBT/USDC).
Source is Binance USDT pairs (ETH/USDT, SOL/USDT) — price difference vs USDC
is negligible (<0.1%) for backtesting purposes.

Usage:
    DATABASE_URL="postgresql+asyncpg://krakenbot:krakenbot@localhost:5432/krakenbot" \
        python3 scripts/download_multipair_ohlc.py
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sys
import time

import ccxt

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import structlog

from krakenbot.models.market_data import OHLCData

logger = structlog.get_logger()

# ─── Configuration ───────────────────────────────────────────────────────

# (pair stored in DB, Binance symbol to fetch, earliest start, note)
DOWNLOAD_CONFIG = [
    (
        "ETH/USDC",
        "ETH/USDT",
        datetime(2017, 8, 17, tzinfo=UTC),
        "Binance ETH/USDT → DB as ETH/USDC",
    ),
    (
        "SOL/USDC",
        "SOL/USDT",
        datetime(2020, 8, 11, tzinfo=UTC),
        "Binance SOL/USDT → DB as SOL/USDC",
    ),
]

# Intervals: 1h, 4h, 1d, 1w
INTERVALS = {
    60: "1h",
    240: "4h",
    1440: "1d",
    10080: "1w",
}

BATCH_SIZE = 50
RATE_LIMIT_SECONDS = 0.35  # Binance allows ~1200 req/min, be conservative
MAX_RETRIES = 3
CANDLES_PER_REQUEST = 1000  # Binance max


# ─── DB helpers ──────────────────────────────────────────────────────────


async def get_db_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create async DB engine and session factory."""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://krakenbot:krakenbot@localhost:5432/krakenbot",
    )
    engine = create_async_engine(db_url, pool_size=3, pool_pre_ping=True)

    # Test connection
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("db_connected", url=db_url.split("@")[-1])

    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_last_timestamp(
    session_factory: async_sessionmaker[AsyncSession],
    pair_db: str,
    interval: int,
    exchange: str = "binance",
) -> datetime | None:
    """Get the most recent timestamp in DB for a pair/interval."""
    async with session_factory() as session:
        stmt = (
            select(func.max(OHLCData.timestamp))
            .where(OHLCData.pair == pair_db)
            .where(OHLCData.interval == interval)
            .where(OHLCData.exchange == exchange)
        )
        result = await session.execute(stmt)
        return result.scalar()


async def get_first_timestamp(
    session_factory: async_sessionmaker[AsyncSession],
    pair_db: str,
    interval: int,
    exchange: str = "binance",
) -> datetime | None:
    """Get the oldest timestamp in DB for a pair/interval."""
    async with session_factory() as session:
        stmt = (
            select(func.min(OHLCData.timestamp))
            .where(OHLCData.pair == pair_db)
            .where(OHLCData.interval == interval)
            .where(OHLCData.exchange == exchange)
        )
        result = await session.execute(stmt)
        return result.scalar()


async def save_batch(
    session_factory: async_sessionmaker[AsyncSession],
    candles: list[dict],
) -> int:
    """Insert candles with ON CONFLICT DO NOTHING."""
    if not candles:
        return 0

    async with session_factory() as session:
        stmt = (
            pg_insert(OHLCData)
            .values(candles)
            .on_conflict_do_nothing(
                index_elements=["timestamp", "pair", "interval", "exchange"],
            )
            .returning(OHLCData.timestamp)
        )
        result = await session.execute(stmt)
        await session.commit()
    return len(result.scalars().all())


# ─── Download logic ──────────────────────────────────────────────────────


def create_exchange() -> ccxt.binance:
    """Create ccxt Binance exchange (no API key needed for public data)."""
    return ccxt.binance(
        {
            "enableRateLimit": False,  # We handle rate limiting manually
        }
    )


def download_pair_interval_sync(
    exchange: ccxt.binance,
    pair_db: str,
    ccxt_symbol: str,
    interval_min: int,
    timeframe: str,
    start_from: datetime,
    description: str,
) -> list[dict]:
    """Fetch all OHLC candles from Binance for one pair/interval.

    Returns list of candle dicts ready for DB insertion.
    Binance properly paginates from the `since` parameter forward.
    """
    now = datetime.now(UTC)
    since_ms = int(start_from.timestamp() * 1000)
    now_ms = int(now.timestamp() * 1000)
    all_candles: list[dict] = []

    logger.info(
        "download_start",
        pair_db=pair_db,
        ccxt_symbol=ccxt_symbol,
        interval=timeframe,
        since=start_from.strftime("%Y-%m-%d"),
        description=description,
    )

    while since_ms < now_ms:
        retry = 0
        candles_raw = None

        while retry < MAX_RETRIES:
            try:
                candles_raw = exchange.fetch_ohlcv(
                    ccxt_symbol,
                    timeframe,
                    since=since_ms,
                    limit=CANDLES_PER_REQUEST,
                )
                break
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                retry += 1
                logger.warning("fetch_retry", retry=retry, error=str(e))
                time.sleep(2**retry)
            except ccxt.ExchangeError as e:
                logger.warning("pair_not_available", ccxt_symbol=ccxt_symbol, error=str(e))
                return all_candles

        if candles_raw is None or retry >= MAX_RETRIES:
            logger.error("fetch_failed", ccxt_symbol=ccxt_symbol, interval=timeframe)
            break

        if not candles_raw:
            break

        # Parse candles
        for ts_ms, o, h, low, c, v in candles_raw:
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
            if ts >= now:
                continue
            all_candles.append(
                {
                    "timestamp": ts,
                    "pair": pair_db,
                    "interval": interval_min,
                    "exchange": "binance",
                    "open": Decimal(str(o)),
                    "high": Decimal(str(h)),
                    "low": Decimal(str(low)),
                    "close": Decimal(str(c)),
                    "volume": Decimal(str(v)),
                }
            )

        # Progress
        last_ts = datetime.fromtimestamp(candles_raw[-1][0] / 1000, tz=UTC)
        print(
            f"\r  {pair_db} {timeframe} ({ccxt_symbol}): "
            f"{len(all_candles):>7,} candles → {last_ts.strftime('%Y-%m-%d')}",
            end="",
            flush=True,
        )

        # End of data
        if len(candles_raw) < CANDLES_PER_REQUEST:
            break

        # Advance to next page
        since_ms = candles_raw[-1][0] + 1

        # Rate limit
        time.sleep(RATE_LIMIT_SECONDS)

    print()  # newline after progress
    return all_candles


async def get_data_summary(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[dict]:
    """Get summary of downloaded data per pair/interval."""
    summary = []
    for pair_db in ["ETH/USDC", "SOL/USDC"]:
        for interval_min, tf_label in sorted(INTERVALS.items()):
            first_ts = await get_first_timestamp(session_factory, pair_db, interval_min)
            last_ts = await get_last_timestamp(session_factory, pair_db, interval_min)
            async with session_factory() as session:
                stmt = (
                    select(func.count())
                    .select_from(OHLCData)
                    .where(OHLCData.pair == pair_db)
                    .where(OHLCData.interval == interval_min)
                    .where(OHLCData.exchange == "binance")
                )
                result = await session.execute(stmt)
                count = result.scalar() or 0

            summary.append(
                {
                    "pair": pair_db,
                    "interval": tf_label,
                    "count": count,
                    "first": first_ts,
                    "last": last_ts,
                }
            )
    return summary


# ─── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    """Download all configured pairs and intervals."""
    print("=" * 60)
    print("  Multi-Pair OHLC Download via Binance")
    print("  (ETH/USDT → ETH/USDC, SOL/USDT → SOL/USDC)")
    print("=" * 60)

    session_factory = await get_db_session_factory()
    exchange = create_exchange()

    total_all = 0
    start_time = time.time()

    for pair_db, ccxt_symbol, start_from, description in DOWNLOAD_CONFIG:
        print(f"\n--- {ccxt_symbol} → DB as {pair_db} ---")

        for interval_min, timeframe in sorted(INTERVALS.items()):
            # Check if we already have recent data
            last_ts = await get_last_timestamp(session_factory, pair_db, interval_min)
            now = datetime.now(UTC)

            if last_ts and (now - last_ts) < timedelta(minutes=interval_min * 2):
                logger.info(
                    "already_up_to_date",
                    pair_db=pair_db,
                    interval=timeframe,
                    last_ts=last_ts.strftime("%Y-%m-%d"),
                )
                print(f"  {pair_db} {timeframe}: up to date (last: {last_ts.strftime('%Y-%m-%d')})")
                continue

            # Determine start point (resume from last timestamp if exists)
            effective_start = start_from
            if last_ts and last_ts > start_from:
                effective_start = last_ts + timedelta(minutes=interval_min)

            # Download from Binance (sync ccxt call)
            candles = download_pair_interval_sync(
                exchange=exchange,
                pair_db=pair_db,
                ccxt_symbol=ccxt_symbol,
                interval_min=interval_min,
                timeframe=timeframe,
                start_from=effective_start,
                description=description,
            )

            # Save to DB in batches
            if candles:
                saved_total = 0
                for i in range(0, len(candles), BATCH_SIZE):
                    batch = candles[i : i + BATCH_SIZE]
                    saved = await save_batch(session_factory, batch)
                    saved_total += saved
                total_all += saved_total
                logger.info(
                    "saved_to_db",
                    pair_db=pair_db,
                    interval=timeframe,
                    candles=saved_total,
                )

    elapsed = time.time() - start_time

    # Print summary
    print("\n" + "=" * 60)
    print("  Download Summary")
    print("=" * 60)

    summary = await get_data_summary(session_factory)
    for row in summary:
        if row["count"] > 0:
            print(
                f"  {row['pair']} {row['interval']:<4}: "
                f"{row['count']:>7,} candles "
                f"({row['first'].strftime('%Y-%m-%d')} → {row['last'].strftime('%Y-%m-%d')})"
            )
        else:
            print(f"  {row['pair']} {row['interval']:<4}: no data")

    print(f"\n  Total new: {total_all:,} candles in {elapsed:.0f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
