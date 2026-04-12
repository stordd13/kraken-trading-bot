"""Tests for the minimal exchange abstraction layer."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from krakenbot.connectors.exchange import build_exchange_rest_client


class TestBuildExchangeRestClient:
    """Tests for runtime REST client construction."""

    def test_factory_returns_kraken_client_today(self, mock_settings) -> None:
        """The current runtime factory should preserve Kraken behavior."""
        event_bus = MagicMock()
        db_manager = MagicMock()
        fake_client = MagicMock(exchange_name="kraken")

        with patch("krakenbot.connectors.kraken.rest.KrakenRestClient", return_value=fake_client):
            client = build_exchange_rest_client(mock_settings, event_bus, db_manager)

        assert client is fake_client

    def test_factory_result_exposes_exchange_protocol_surface(self, mock_settings) -> None:
        """The runtime factory should return an object with the required surface."""
        event_bus = MagicMock()
        db_manager = MagicMock()
        fake_client = MagicMock()
        fake_client.exchange_name = "kraken"
        fake_client.is_paper_mode = True
        fake_client.stats = {"api_calls": 0}
        fake_client.paper_balance = {"USDC": Decimal("0")}

        with patch("krakenbot.connectors.kraken.rest.KrakenRestClient", return_value=fake_client):
            client = build_exchange_rest_client(mock_settings, event_bus, db_manager)

        assert client.exchange_name == "kraken"
        assert client.is_paper_mode is True
