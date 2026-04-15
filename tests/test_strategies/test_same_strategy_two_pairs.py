"""Tests for same strategy class instantiated on two different pairs.

Validates that:
- Two instances of the same strategy class have separate pair assignments
- Each instance maintains independent state (pair, positions)
- effective_pair reads from strategy_params
"""

from __future__ import annotations

from unittest.mock import MagicMock

from krakenbot.indicators.multi_pair_registry import MultiPairAnalyzerRegistry
from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime


def _make_supertrend(
    mock_settings: MagicMock,
    pair: str,
    bot_id: str,
) -> GrokSuperTrend4hRegime:
    """Create a SuperTrend strategy bound to a specific pair."""
    registry = MultiPairAnalyzerRegistry()
    analyzer = registry.get_or_create(pair)

    event_bus = MagicMock()
    db_manager = MagicMock()

    strategy = GrokSuperTrend4hRegime(
        settings=mock_settings,
        event_bus=event_bus,
        db_manager=db_manager,
        bot_id=bot_id,
        strategy_params={"pair": pair},
        analyzer=analyzer,
    )
    return strategy


class TestSameStrategyTwoPairs:
    """Two SuperTrend 4h instances on BTC and ETH."""

    def test_different_pair_assignments(self, mock_settings: MagicMock) -> None:
        """Each instance reports its own pair."""
        btc_st = _make_supertrend(mock_settings, "BTC/USDC", "supertrend_btc")
        eth_st = _make_supertrend(mock_settings, "ETH/USDC", "supertrend_eth")

        assert btc_st.pair == "BTC/USDC"
        assert eth_st.pair == "ETH/USDC"

    def test_different_bot_ids(self, mock_settings: MagicMock) -> None:
        btc_st = _make_supertrend(mock_settings, "BTC/USDC", "supertrend_btc")
        eth_st = _make_supertrend(mock_settings, "ETH/USDC", "supertrend_eth")

        assert btc_st.bot_id == "supertrend_btc"
        assert eth_st.bot_id == "supertrend_eth"

    def test_independent_analyzers(self, mock_settings: MagicMock) -> None:
        """Each pair's strategy gets a unique analyzer (not shared)."""
        registry = MultiPairAnalyzerRegistry()
        btc_analyzer = registry.get_or_create("BTC/USDC")
        eth_analyzer = registry.get_or_create("ETH/USDC")

        event_bus = MagicMock()
        db_manager = MagicMock()

        btc_st = GrokSuperTrend4hRegime(
            settings=mock_settings,
            event_bus=event_bus,
            db_manager=db_manager,
            bot_id="st_btc",
            strategy_params={"pair": "BTC/USDC"},
            analyzer=btc_analyzer,
        )
        eth_st = GrokSuperTrend4hRegime(
            settings=mock_settings,
            event_bus=event_bus,
            db_manager=db_manager,
            bot_id="st_eth",
            strategy_params={"pair": "ETH/USDC"},
            analyzer=eth_analyzer,
        )

        assert btc_st.analyzer is not eth_st.analyzer

    def test_effective_pair_from_params(self, mock_settings: MagicMock) -> None:
        """effective_pair reads from strategy_params.pair."""
        btc_st = _make_supertrend(mock_settings, "BTC/USDC", "st_btc")
        assert btc_st.effective_pair == "BTC/USDC"

    def test_effective_pair_normalizes_xbt(self, mock_settings: MagicMock) -> None:
        """effective_pair normalizes XBT to BTC."""
        st = _make_supertrend(mock_settings, "XBT/USDC", "st_xbt")
        assert st.effective_pair == "BTC/USDC"
        assert st.pair == "BTC/USDC"

    def test_same_strategy_class(self, mock_settings: MagicMock) -> None:
        """Both are the same class."""
        btc_st = _make_supertrend(mock_settings, "BTC/USDC", "st_btc")
        eth_st = _make_supertrend(mock_settings, "ETH/USDC", "st_eth")
        assert type(btc_st) is type(eth_st)
