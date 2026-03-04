"""External data fetcher for ML features.

Fetches data from free APIs and stores in ``ml_external_data`` table.

Currently supported sources:
    - Fear & Greed Index (alternative.me) — daily, 0-100, free, no key required.
      Full history since 2018-02-01 available via ``?limit=0``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp
from sqlalchemy.dialects.postgresql import insert as pg_insert
import structlog

from krakenbot.ml.db_models import MLExternalData

if TYPE_CHECKING:
    from krakenbot.core.database import DatabaseManager

logger = structlog.get_logger(__name__)


class ExternalDataFetcher:
    """Fetches external data from public APIs."""

    FEAR_GREED_URL = "https://api.alternative.me/fng/"

    _TIMEOUT_SECONDS: int = 30
    _MAX_RETRIES: int = 3
    _RETRY_DELAYS: list[float] = [5.0, 10.0, 20.0]

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    # ------------------------------------------------------------------
    # Fear & Greed Index
    # ------------------------------------------------------------------

    async def fetch_fear_greed(self, limit: int = 1) -> list[dict[str, Any]]:
        """Fetch Fear & Greed Index data from alternative.me API.

        Args:
            limit: Number of historical entries to fetch.
                   Use 0 for full history (since 2018-02-01).

        Returns:
            List of dicts with keys: timestamp (datetime), value (float),
            classification (str).
        """
        url = f"{self.FEAR_GREED_URL}?limit={limit}&format=json"

        for attempt in range(self._MAX_RETRIES):
            try:
                timeout = aiohttp.ClientTimeout(total=self._TIMEOUT_SECONDS)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.warning(
                                "fear_greed_http_error",
                                status=response.status,
                                attempt=attempt + 1,
                            )
                            if response.status >= 400 and response.status < 500:
                                return []  # Client error, don't retry
                            if attempt < self._MAX_RETRIES - 1:
                                await asyncio.sleep(self._RETRY_DELAYS[attempt])
                                continue
                            return []

                        data = await response.json()

                entries = data.get("data", [])
                results = []
                for entry in entries:
                    ts = datetime.fromtimestamp(int(entry["timestamp"]), tz=UTC)
                    results.append(
                        {
                            "timestamp": ts,
                            "value": float(entry["value"]),
                            "classification": entry.get("value_classification", ""),
                        }
                    )

                logger.info("fear_greed_fetched", entries=len(results))
                return results

            except (TimeoutError, aiohttp.ClientError, KeyError, ValueError) as e:
                logger.warning(
                    "fear_greed_fetch_error",
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt < self._MAX_RETRIES - 1:
                    await asyncio.sleep(self._RETRY_DELAYS[attempt])

        return []

    async def fetch_and_store_fear_greed(self, limit: int = 1) -> int:
        """Fetch Fear & Greed data and upsert into ml_external_data.

        Args:
            limit: Number of entries to fetch (0 = full history).

        Returns:
            Number of rows upserted.
        """
        entries = await self.fetch_fear_greed(limit=limit)
        if not entries:
            return 0

        count = 0
        async with self._db.session() as session:
            for entry in entries:
                stmt = (
                    pg_insert(MLExternalData)
                    .values(
                        timestamp=entry["timestamp"],
                        source="fear_greed",
                        value=entry["value"],
                        value_classification=entry["classification"],
                        raw_data={
                            "value": entry["value"],
                            "classification": entry["classification"],
                        },
                    )
                    .on_conflict_do_update(
                        index_elements=["timestamp", "source"],
                        set_={
                            "value": entry["value"],
                            "value_classification": entry["classification"],
                        },
                    )
                )
                await session.execute(stmt)
                count += 1

        logger.info("fear_greed_stored", rows=count)
        return count

    async def backfill_fear_greed(self) -> int:
        """Backfill full Fear & Greed history (since 2018-02-01).

        Uses ``?limit=0`` to get all available data in a single request.

        Returns:
            Number of rows upserted.
        """
        logger.info("fear_greed_backfill_start")
        return await self.fetch_and_store_fear_greed(limit=0)

    # ------------------------------------------------------------------
    # Generic lookup (used by FeatureStore for forward-fill)
    # ------------------------------------------------------------------

    async def get_latest_value(self, source: str, before: datetime) -> float | None:
        """Get the most recent value for a source before a given timestamp.

        Used for forward-fill in feature computation.

        Args:
            source: Data source name (e.g., "fear_greed").
            before: Timestamp upper bound.

        Returns:
            Most recent value, or None if no data available.
        """
        from sqlalchemy import select

        async with self._db.read_session() as session:
            stmt = (
                select(MLExternalData.value)
                .where(
                    MLExternalData.source == source,
                    MLExternalData.timestamp <= before,
                )
                .order_by(MLExternalData.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
