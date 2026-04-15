"""Tests for MultiPairAnalyzerRegistry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.indicators.multi_pair_registry import (
    MultiPairAnalyzerRegistry,
    normalize_pair,
)

# =====================================================================
# normalize_pair
# =====================================================================


class TestNormalizePair:
    """Test pair normalization (XBT -> BTC)."""

    def test_xbt_to_btc(self) -> None:
        assert normalize_pair("XBT/USDC") == "BTC/USDC"

    def test_xbt_eur_to_btc_eur(self) -> None:
        assert normalize_pair("XBT/EUR") == "BTC/EUR"

    def test_btc_unchanged(self) -> None:
        assert normalize_pair("BTC/USDC") == "BTC/USDC"

    def test_eth_unchanged(self) -> None:
        assert normalize_pair("ETH/USDC") == "ETH/USDC"

    def test_sol_unchanged(self) -> None:
        assert normalize_pair("SOL/USDC") == "SOL/USDC"

    def test_empty_string(self) -> None:
        assert normalize_pair("") == ""


# =====================================================================
# MultiPairAnalyzerRegistry
# =====================================================================


class TestMultiPairAnalyzerRegistry:
    """Tests for the per-pair analyzer registry."""

    def test_get_or_create_returns_analyzer(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        analyzer = registry.get_or_create("BTC/USDC")
        assert analyzer is not None

    def test_get_or_create_is_idempotent(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        a1 = registry.get_or_create("BTC/USDC")
        a2 = registry.get_or_create("BTC/USDC")
        assert a1 is a2

    def test_different_pairs_get_different_analyzers(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        btc = registry.get_or_create("BTC/USDC")
        eth = registry.get_or_create("ETH/USDC")
        assert btc is not eth

    def test_xbt_normalizes_to_btc(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        a1 = registry.get_or_create("XBT/USDC")
        a2 = registry.get_or_create("BTC/USDC")
        assert a1 is a2

    def test_get_returns_none_for_unregistered(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        assert registry.get("BTC/USDC") is None

    def test_get_returns_analyzer_after_create(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        created = registry.get_or_create("ETH/USDC")
        fetched = registry.get("ETH/USDC")
        assert fetched is created

    def test_pairs_property(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        registry.get_or_create("BTC/USDC")
        registry.get_or_create("ETH/USDC")
        registry.get_or_create("SOL/USDC")
        assert set(registry.pairs) == {"BTC/USDC", "ETH/USDC", "SOL/USDC"}

    def test_len(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        assert len(registry) == 0
        registry.get_or_create("BTC/USDC")
        assert len(registry) == 1
        registry.get_or_create("ETH/USDC")
        assert len(registry) == 2

    def test_contains(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        registry.get_or_create("BTC/USDC")
        assert "BTC/USDC" in registry
        assert "XBT/USDC" in registry  # normalized
        assert "ETH/USDC" not in registry

    def test_update_routes_to_correct_analyzer(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        btc = registry.get_or_create("BTC/USDC")
        eth = registry.get_or_create("ETH/USDC")

        # Mock update on both analyzers
        btc.update = MagicMock()
        eth.update = MagicMock()

        candle = {"open": 100, "high": 110, "low": 90, "close": 105, "volume": 10}
        registry.update("BTC/USDC", candle, 240)

        btc.update.assert_called_once_with(candle, 240)
        eth.update.assert_not_called()

    def test_update_ignores_unregistered_pair(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        registry.get_or_create("BTC/USDC")
        # Should not raise
        registry.update("ETH/USDC", {"close": 100}, 60)

    @pytest.mark.asyncio
    async def test_initialize_all_calls_each_analyzer(self) -> None:
        registry = MultiPairAnalyzerRegistry()
        btc = registry.get_or_create("BTC/USDC")
        eth = registry.get_or_create("ETH/USDC")

        btc.initialize = AsyncMock()
        eth.initialize = AsyncMock()

        mock_db = MagicMock()
        await registry.initialize_all(mock_db, exchange="binance")

        btc.initialize.assert_awaited_once_with(mock_db, pair="BTC/USDC", exchange="binance")
        eth.initialize.assert_awaited_once_with(mock_db, pair="ETH/USDC", exchange="binance")

    def test_independent_indicator_state(self) -> None:
        """Each pair's analyzer has independent internal state."""
        registry = MultiPairAnalyzerRegistry()
        btc = registry.get_or_create("BTC/USDC")
        eth = registry.get_or_create("ETH/USDC")

        # Internal indicator objects should be separate instances
        assert btc._ema_fast_1h is not eth._ema_fast_1h
        assert btc._rsi_1h is not eth._rsi_1h
        assert btc._atr_1h is not eth._atr_1h
