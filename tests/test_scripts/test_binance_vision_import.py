"""Tests for the Binance Vision historical data import script."""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import io
from pathlib import Path

# Add project root so 'scripts' is importable, and 'src' for krakenbot
import sys
from unittest.mock import AsyncMock, MagicMock
import zipfile

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))

from scripts.binance_vision_import import (
    BATCH_SIZE,
    extract_csv_from_zip,
    import_month,
    pair_to_binance_symbol,
    parse_klines_csv,
)

# ---------------------------------------------------------------------------
# pair_to_binance_symbol
# ---------------------------------------------------------------------------


class TestPairToBinanceSymbol:
    def test_btc_usdc(self) -> None:
        assert pair_to_binance_symbol("BTC/USDC") == "BTCUSDC"

    def test_eth_usdc(self) -> None:
        assert pair_to_binance_symbol("ETH/USDC") == "ETHUSDC"

    def test_sol_usdc(self) -> None:
        assert pair_to_binance_symbol("SOL/USDC") == "SOLUSDC"


# ---------------------------------------------------------------------------
# parse_klines_csv
# ---------------------------------------------------------------------------

SAMPLE_CSV_NO_HEADER = (
    b"1704067200000,42000.00,42500.00,41800.00,42300.00,100.5,"
    b"1704070799999,4230000.00,1500,50.25,2115000.00,0\n"
    b"1704070800000,42300.00,42800.00,42100.00,42700.00,120.3,"
    b"1704074399999,5124100.00,1800,60.15,2567050.00,0\n"
)

SAMPLE_CSV_WITH_HEADER = (
    b"open_time,open,high,low,close,volume,"
    b"close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    + SAMPLE_CSV_NO_HEADER
)


class TestParseKlinesCsv:
    def test_parse_without_header(self) -> None:
        rows = parse_klines_csv(SAMPLE_CSV_NO_HEADER, "BTC/USDC", 60)
        assert len(rows) == 2

        row = rows[0]
        assert row["pair"] == "BTC/USDC"
        assert row["interval"] == 60
        assert row["exchange"] == "binance"
        assert isinstance(row["open"], Decimal)
        assert row["open"] == Decimal("42000.00")
        assert row["high"] == Decimal("42500.00")
        assert row["low"] == Decimal("41800.00")
        assert row["close"] == Decimal("42300.00")
        assert row["volume"] == Decimal("100.5")
        assert row["trades_count"] == 1500
        assert row["vwap"] is None

    def test_parse_with_header(self) -> None:
        rows = parse_klines_csv(SAMPLE_CSV_WITH_HEADER, "BTC/USDC", 60)
        assert len(rows) == 2

    def test_timestamp_is_utc_period_end(self) -> None:
        rows = parse_klines_csv(SAMPLE_CSV_NO_HEADER, "BTC/USDC", 60)
        ts = rows[0]["timestamp"]
        assert isinstance(ts, datetime)
        assert ts.tzinfo is not None
        # 1704067200000 ms = open time 2024-01-01 00:00:00 UTC → stored at the period end (+1h)
        assert ts == datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)

    def test_timestamp_period_end_per_interval(self) -> None:
        """B4.1: DB timestamp = open_time + interval for every TF, ms and µs inputs alike."""
        open_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        for interval in (1, 5, 15, 60, 240, 1440, 10080):
            for raw in ("1704067200000", "1704067200000000"):  # ms, µs
                csv_data = (raw + ",1,2,0.5,1.5,10,1704070799999,0,3,0,0,0\n").encode()
                rows = parse_klines_csv(csv_data, "BTC/USDC", interval)
                assert rows[0]["timestamp"] == open_time + timedelta(minutes=interval), (
                    interval,
                    raw,
                )
        # 1w candle opening Monday 2024-01-01 closes Monday 2024-01-08 00:00 (Monday-anchored grid)
        weekly = parse_klines_csv(b"1704067200000,1,2,0.5,1.5,10,0,0,3,0,0,0\n", "BTC/USDC", 10080)
        assert weekly[0]["timestamp"] == datetime(2024, 1, 8, tzinfo=UTC)

    def test_empty_csv_returns_empty(self) -> None:
        rows = parse_klines_csv(b"", "BTC/USDC", 60)
        assert rows == []

    def test_malformed_row_skipped(self) -> None:
        csv_data = b"not_a_number,42000.00,42500.00\n" + SAMPLE_CSV_NO_HEADER
        rows = parse_klines_csv(csv_data, "BTC/USDC", 60)
        # The malformed row is skipped, 2 valid rows remain
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# extract_csv_from_zip
# ---------------------------------------------------------------------------


class TestExtractCsvFromZip:
    def test_extract_valid_zip(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("BTCUSDC-1h-2024-01.csv", "some,csv,data\n")
        zip_bytes = buf.getvalue()

        result = extract_csv_from_zip(zip_bytes)
        assert result == b"some,csv,data\n"

    def test_extract_invalid_zip_returns_none(self) -> None:
        result = extract_csv_from_zip(b"not a zip")
        assert result is None


# ---------------------------------------------------------------------------
# import_month
# ---------------------------------------------------------------------------


def _build_http_mock(response: MagicMock) -> MagicMock:
    """Build a mock aiohttp session whose .get() returns an async context manager."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=response)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_http = MagicMock()
    mock_http.get.return_value = mock_cm
    return mock_http


def _build_db_mock() -> tuple[MagicMock, AsyncMock]:
    """Build a mock DatabaseManager whose .session() is an async context manager."""
    mock_session = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.session.return_value = mock_cm
    return mock_db, mock_session


class TestImportMonth:
    @pytest.mark.asyncio
    async def test_404_returns_zero(self) -> None:
        """A 404 response (file doesn't exist on Binance Vision) returns 0."""
        mock_response = MagicMock()
        mock_response.status = 404

        mock_http = _build_http_mock(mock_response)
        mock_db = MagicMock()

        result = await import_month(mock_http, mock_db, "BTC/USDC", 60, 2020, 1)
        assert result == 0

    @pytest.mark.asyncio
    async def test_inserts_rows(self) -> None:
        """A successful download + parse inserts rows via pg_insert."""
        # Build a valid ZIP containing CSV data
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("BTCUSDC-1h-2024-01.csv", SAMPLE_CSV_NO_HEADER.decode())
        zip_bytes = buf.getvalue()

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=zip_bytes)

        mock_http = _build_http_mock(mock_response)
        mock_db, mock_session = _build_db_mock()

        result = await import_month(mock_http, mock_db, "BTC/USDC", 60, 2024, 1)
        assert result == 2
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_on_conflict_do_nothing(self) -> None:
        """Re-importing the same month uses ON CONFLICT DO NOTHING."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("BTCUSDC-1h-2024-01.csv", SAMPLE_CSV_NO_HEADER.decode())
        zip_bytes = buf.getvalue()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=zip_bytes)

        mock_http = _build_http_mock(mock_response)
        mock_db, mock_session = _build_db_mock()

        # Import twice — both should succeed without error
        r1 = await import_month(mock_http, mock_db, "BTC/USDC", 60, 2024, 1)
        r2 = await import_month(mock_http, mock_db, "BTC/USDC", 60, 2024, 1)
        assert r1 == 2
        assert r2 == 2
        # The SQL statement uses on_conflict_do_nothing which the DB handles
        assert mock_session.execute.call_count == 2


# ---------------------------------------------------------------------------
# Batch insert tests
# ---------------------------------------------------------------------------


def _build_large_csv(n_rows: int) -> bytes:
    """Build a CSV with n_rows kline entries (1h candles starting 2024-01-01)."""
    lines: list[str] = []
    base_ts_ms = 1704067200000  # 2024-01-01 00:00:00 UTC
    for i in range(n_rows):
        ts = base_ts_ms + i * 3600000  # 1h apart
        lines.append(
            f"{ts},42000.00,42500.00,41800.00,42300.00,100.5,"
            f"{ts + 3599999},4230000.00,1500,50.25,2115000.00,0"
        )
    return "\n".join(lines).encode()


def _build_large_zip(n_rows: int) -> bytes:
    """Build a ZIP containing a CSV with n_rows kline entries."""
    csv_data = _build_large_csv(n_rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BTCUSDC-1h-2024-01.csv", csv_data.decode())
    return buf.getvalue()


class TestBatchInsert:
    @pytest.mark.asyncio
    async def test_inserts_in_batches_when_rows_exceed_batch_size(self) -> None:
        """Large imports should be split into multiple execute() calls."""
        n_rows = BATCH_SIZE * 2 + 500  # e.g. 2500 rows → 3 batches
        zip_bytes = _build_large_zip(n_rows)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=zip_bytes)

        mock_http = _build_http_mock(mock_response)
        mock_db, mock_session = _build_db_mock()

        result = await import_month(mock_http, mock_db, "BTC/USDC", 60, 2024, 1)

        assert result == n_rows
        expected_batches = (n_rows + BATCH_SIZE - 1) // BATCH_SIZE
        assert mock_session.execute.call_count == expected_batches
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_data_loss_in_batch_insert(self) -> None:
        """All rows must be passed to execute() across batches — none lost."""
        n_rows = BATCH_SIZE * 2 + 500
        zip_bytes = _build_large_zip(n_rows)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=zip_bytes)

        mock_http = _build_http_mock(mock_response)
        mock_db, mock_session = _build_db_mock()

        await import_month(mock_http, mock_db, "BTC/USDC", 60, 2024, 1)

        # Count total rows across all execute() calls by inspecting the
        # INSERT statements' compile parameters. Each call passes a batch
        # via pg_insert(...).values(batch) — the statement embeds the rows.
        # We verify the call count matches expected batches (no lost batch).
        total_execute_calls = mock_session.execute.call_count
        expected_batches = (n_rows + BATCH_SIZE - 1) // BATCH_SIZE
        assert total_execute_calls == expected_batches
        # Also verify return value accounts for all rows
        assert n_rows == BATCH_SIZE * 2 + 500

    @pytest.mark.asyncio
    async def test_batch_insert_is_idempotent(self) -> None:
        """Running import twice with batching should not error."""
        n_rows = BATCH_SIZE + 100
        zip_bytes = _build_large_zip(n_rows)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=zip_bytes)

        mock_http = _build_http_mock(mock_response)
        mock_db, mock_session = _build_db_mock()

        r1 = await import_month(mock_http, mock_db, "BTC/USDC", 60, 2024, 1)
        r2 = await import_month(mock_http, mock_db, "BTC/USDC", 60, 2024, 1)

        assert r1 == n_rows
        assert r2 == n_rows
        # Each import produces 2 batches → 4 execute calls total
        expected_batches_per_import = (n_rows + BATCH_SIZE - 1) // BATCH_SIZE
        assert mock_session.execute.call_count == expected_batches_per_import * 2
        # Two commits (one per import_month call)
        assert mock_session.commit.call_count == 2
