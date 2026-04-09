"""Tests for BaseExchangePerps abstract base class."""

from __future__ import annotations

import pytest

from krakenbot.connectors.base_perps import BaseExchangePerps


class TestBaseExchangePerps:
    """Tests for the perps ABC."""

    def test_cannot_instantiate_abc(self) -> None:
        """BaseExchangePerps is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseExchangePerps()  # type: ignore[abstract]

    def test_defines_required_abstract_methods(self) -> None:
        """Verify all expected abstract methods are declared."""
        expected = {
            "name",
            "maker_fee",
            "taker_fee",
            "max_leverage",
            "get_balance",
            "place_perp_order",
            "close_perp_position",
            "get_perp_position",
            "get_all_positions",
            "get_funding_rate",
            "get_funding_history",
            "set_leverage",
            "normalize_pair_to_exchange",
            "denormalize_pair_from_exchange",
            "close",
        }
        assert expected.issubset(BaseExchangePerps.__abstractmethods__)
