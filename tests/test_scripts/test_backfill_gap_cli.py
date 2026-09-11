"""backfill_gap.py CLI: settings-driven defaults, read-only client, summary table."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from krakenbot.data.backfill import BackfillSummary, Gap, GapResult  # noqa: E402

_ENV_BEFORE = dict(os.environ)
from scripts import backfill_gap  # noqa: E402

# the script's load_dotenv() must not leak .env into other tests (BYBIT_TRADE_* etc.)
os.environ.clear()
os.environ.update(_ENV_BEFORE)


def test_format_summary_lists_gaps() -> None:
    gap = Gap(
        "BTC/USDC",
        1,
        datetime(2026, 9, 11, 1, 5, tzinfo=UTC),
        datetime(2026, 9, 11, 1, 5, tzinfo=UTC),
    )
    summary = BackfillSummary(
        exchange="bybit",
        now=datetime(2026, 9, 11, 7, tzinfo=UTC),
        dry_run=False,
        results=[GapResult(gap=gap, fetched=2, inserted=1, pages=1, stop_reason="completed")],
    )
    text = backfill_gap.format_summary(summary)
    assert "BTC/USDC  1m" in text and "completed" in text
    assert "gaps_found=1 gaps_filled=1 candles_inserted=1 failures=0" in text


async def test_main_uses_settings_and_read_only_client() -> None:
    settings = MagicMock()
    settings.exchange_name = "bybit"
    settings.scheduler.pairs = ["BTC/USDC"]
    settings.scheduler.intervals = [1, 5]
    settings.scheduler.batch_size = 1000
    db = MagicMock()
    db.init_db = AsyncMock()
    db.close_db = AsyncMock()
    client = MagicMock()
    client.close = AsyncMock()
    summary = BackfillSummary(exchange="bybit", now=datetime.now(UTC), dry_run=True)

    with (
        patch.object(backfill_gap, "get_settings", return_value=settings),
        patch.object(backfill_gap, "DatabaseManager", return_value=db),
        patch.object(backfill_gap, "build_exchange_rest_client", return_value=client) as factory,
        patch.object(backfill_gap, "backfill_gaps", AsyncMock(return_value=summary)) as bf,
    ):
        rc = await backfill_gap._async_main(
            backfill_gap.parse_args(["--dry-run", "--lookback-days", "3"])
        )

    assert rc == 0
    assert factory.call_args.kwargs == {"read_only": True}
    args, kwargs = bf.call_args
    assert args[2] == "bybit" and args[3] == ["BTC/USDC"] and args[4] == [1, 5]
    assert kwargs["dry_run"] is True and kwargs["lookback"].days == 3
    client.close.assert_awaited_once()
    db.close_db.assert_awaited_once()
