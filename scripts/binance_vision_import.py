"""Import historical OHLC data from Binance Vision (free CSV downloads).

Downloads monthly ZIP files from data.binance.vision and imports them
into market_data_ohlc with exchange='binance'.

Usage:
    poetry run python scripts/binance_vision_import.py \\
        --pairs BTC/USDC,ETH/USDC,SOL/USDC \\
        --intervals 1m,5m,15m,1h,4h,1d,1w \\
        --years 3

    # Or with custom date range
    poetry run python scripts/binance_vision_import.py \\
        --pairs BTC/USDC \\
        --intervals 1h,4h,1d \\
        --start-date 2023-01-01 \\
        --end-date 2026-03-01
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import io
from pathlib import Path
import sys
import zipfile

import aiohttp
from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert as pg_insert
import structlog

load_dotenv()

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.config.settings import Settings
from krakenbot.core.database import DatabaseManager
from krakenbot.models.market_data import OHLCData

logger = structlog.get_logger()

# Binance interval mapping (minutes → Binance string)
INTERVAL_TO_BINANCE: dict[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
    10080: "1w",
}

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

# Max rows per INSERT statement. PostgreSQL has a ~65,000 parameter limit.
# Each row has 11 columns → 1000 rows = 11,000 params, well under the limit.
BATCH_SIZE = 1000


def pair_to_binance_symbol(pair: str) -> str:
    """Convert pair notation to Binance symbol.

    >>> pair_to_binance_symbol("BTC/USDC")
    'BTCUSDC'
    """
    return pair.replace("/", "")


async def download_zip(
    session: aiohttp.ClientSession,
    url: str,
    timeout: int = 120,
) -> bytes | None:
    """Download a ZIP file. Returns None if 404 (file doesn't exist)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 404:
                logger.debug("file_not_found", url=url)
                return None
            resp.raise_for_status()
            return await resp.read()
    except Exception as e:
        logger.error("download_failed", url=url, error=str(e))
        return None


def extract_csv_from_zip(zip_data: bytes) -> bytes | None:
    """Extract the single CSV from a Binance Vision ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            csv_name = zf.namelist()[0]
            return zf.read(csv_name)
    except Exception as e:
        logger.error("zip_extract_error", error=str(e))
        return None


def parse_klines_csv(csv_data: bytes, pair: str, interval: int) -> list[dict]:
    """Parse Binance Vision kline CSV format.

    CSV columns (no header in most files):
    open_time, open, high, low, close, volume,
    close_time, quote_volume, trades_count,
    taker_buy_volume, taker_buy_quote_volume, ignore
    """
    rows: list[dict] = []
    text = csv_data.decode("utf-8")

    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row:
            continue
        # Skip header if present
        if row[0].startswith("open_time") or not row[0].isdigit():
            continue

        try:
            raw_ts = int(row[0])
            # Binance Vision uses milliseconds for older files and microseconds
            # for newer files (2025+). Auto-detect based on magnitude.
            # Milliseconds: ~13 digits (e.g. 1704067200000)
            # Microseconds: ~16 digits (e.g. 1704067200000000)
            if raw_ts > 10**14:
                timestamp = datetime.fromtimestamp(raw_ts / 1_000_000, tz=UTC)
            else:
                timestamp = datetime.fromtimestamp(raw_ts / 1000, tz=UTC)

            rows.append(
                {
                    "timestamp": timestamp,
                    "pair": pair,
                    "interval": interval,
                    "exchange": "binance",
                    "open": Decimal(row[1]),
                    "high": Decimal(row[2]),
                    "low": Decimal(row[3]),
                    "close": Decimal(row[4]),
                    "volume": Decimal(row[5]),
                    "trades_count": int(row[8]) if len(row) > 8 else None,
                    "vwap": None,  # Binance doesn't provide VWAP
                }
            )
        except (ValueError, IndexError) as e:
            logger.warning("parse_error", row=row[:3], error=str(e))

    return rows


async def import_month(
    http_session: aiohttp.ClientSession,
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    year: int,
    month: int,
) -> int:
    """Import one month of data for one pair/interval. Returns rows inserted."""
    symbol = pair_to_binance_symbol(pair)
    interval_str = INTERVAL_TO_BINANCE[interval]

    filename = f"{symbol}-{interval_str}-{year:04d}-{month:02d}.zip"
    url = f"{BASE_URL}/{symbol}/{interval_str}/{filename}"

    logger.info("downloading", url=url)
    zip_data = await download_zip(http_session, url)
    if zip_data is None:
        return 0

    csv_data = extract_csv_from_zip(zip_data)
    if csv_data is None:
        return 0

    rows = parse_klines_csv(csv_data, pair, interval)
    if not rows:
        return 0

    # Batch upsert — idempotent via ON CONFLICT DO NOTHING.
    # PostgreSQL has a ~65k parameter limit per query; 1m data can have ~43k rows
    # (43k × 11 cols = 473k params), so we batch to stay well under the limit.
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    async with db_manager.session() as session:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            stmt = pg_insert(OHLCData).values(batch)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["timestamp", "pair", "interval", "exchange"]
            )
            await session.execute(stmt)

            batch_num = i // BATCH_SIZE + 1
            if batch_num % 10 == 0 or batch_num == total_batches:
                logger.info(
                    "imported_batch",
                    pair=pair,
                    interval=interval_str,
                    year=year,
                    month=month,
                    batch=f"{batch_num}/{total_batches}",
                    rows=min(i + BATCH_SIZE, len(rows)),
                )

        await session.commit()

    logger.info(
        "imported",
        pair=pair,
        interval=interval_str,
        year=year,
        month=month,
        rows=len(rows),
        batches=total_batches,
    )
    return len(rows)


async def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Import historical OHLC data from Binance Vision")
    parser.add_argument(
        "--pairs",
        default="BTC/USDC,ETH/USDC,SOL/USDC",
        help="Comma-separated pairs (default: BTC/USDC,ETH/USDC,SOL/USDC)",
    )
    parser.add_argument(
        "--intervals",
        default="1m,5m,15m,1h,4h,1d,1w",
        help="Comma-separated intervals (default: 1m,5m,15m,1h,4h,1d,1w)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Number of years of history (default: 3)",
    )
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD (overrides --years)")
    parser.add_argument("--end-date", help="End date YYYY-MM-DD (default: now)")
    args = parser.parse_args()

    pairs = [p.strip() for p in args.pairs.split(",")]

    interval_str_to_min = {v: k for k, v in INTERVAL_TO_BINANCE.items()}
    intervals = [interval_str_to_min[i.strip()] for i in args.intervals.split(",")]

    # Determine date range
    if args.end_date:
        end_date = datetime.fromisoformat(args.end_date).replace(tzinfo=UTC)
    else:
        end_date = datetime.now(UTC)

    if args.start_date:
        start_date = datetime.fromisoformat(args.start_date).replace(tzinfo=UTC)
    else:
        start_date = end_date - timedelta(days=365 * args.years)

    # Generate (year, month) tuples
    months: list[tuple[int, int]] = []
    current = start_date.replace(day=1)
    while current <= end_date:
        months.append((current.year, current.month))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    total_files = len(pairs) * len(intervals) * len(months)
    logger.info(
        "import_plan",
        pairs=pairs,
        intervals=args.intervals.split(","),
        months_count=len(months),
        total_files=total_files,
    )

    # Setup DB
    settings = Settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    total_rows = 0
    failed_files = 0
    processed = 0

    async with aiohttp.ClientSession() as http_session:
        for pair in pairs:
            for interval in intervals:
                for year, month in months:
                    processed += 1
                    try:
                        rows = await import_month(
                            http_session,
                            db_manager,
                            pair,
                            interval,
                            year,
                            month,
                        )
                        total_rows += rows
                    except Exception as e:
                        logger.error(
                            "month_failed",
                            pair=pair,
                            interval=interval,
                            year=year,
                            month=month,
                            error=str(e),
                        )
                        failed_files += 1

                    if processed % 50 == 0:
                        logger.info(
                            "progress",
                            processed=processed,
                            total=total_files,
                            pct=f"{processed / total_files * 100:.1f}%",
                            total_rows=total_rows,
                        )

    await db_manager.close_db()

    logger.info(
        "import_complete",
        total_rows=total_rows,
        failed_files=failed_files,
        processed_files=processed,
    )


if __name__ == "__main__":
    asyncio.run(main())
