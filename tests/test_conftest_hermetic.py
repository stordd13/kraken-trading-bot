"""The shared fixtures are hermetic to ``TELEGRAM_*`` (C3a pre-merge gate incident, 2026-09-22).

``get_settings()`` calls ``load_dotenv()`` at run time (``settings.py:962``), so on a machine whose
``.env`` carries real ``TELEGRAM_ENABLED`` / ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID`` (the
server) those keys sit in ``os.environ`` when ``mock_settings`` builds ``Settings(...)``.
``TelegramSettings`` (``env_prefix="TELEGRAM_"``) reads them, ``KrakenBot._init_telegram_notifier``
(setup step 4) registers a real ``TelegramNotifier`` and ``start()`` (step 7) fires
``send_bot_started`` as a detached task: a genuine HTTPS request to api.telegram.org leaves the unit
tests (messages received on 2026-09-22) and its ``aiohttp.ClientSession`` / ``pycares`` objects
outlive the test loop (``PytestUnraisableExceptionWarning`` raised in a neighbouring test). Locally,
without ``TELEGRAM_*``, everything is green — hence these tests inject the variables themselves.

The settings test and the bot test set the variables *in their body*, i.e. after the autouse purge
of ``tests/conftest.py`` has already run: that is the run-time ``load_dotenv`` scenario, and the
fixture itself must not read them. The purge test sets them one scope above the purge (module).
Written before the fix and observed red against ``dev`` @ ``9c90bcd`` (``rouge_avant_test.txt``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import MultiStrategySettings, Settings, StrategyInstanceConfig
from krakenbot.main import KrakenBot

#: The three keys purged by ``tests/conftest.py`` (mirrored: conftest is not importable).
_TELEGRAM_ENV = {
    "TELEGRAM_ENABLED": "true",
    "TELEGRAM_BOT_TOKEN": "000:fake",
    "TELEGRAM_CHAT_ID": "1",
}


@pytest.fixture(scope="module", autouse=True)
def _telegram_env_above_the_purge() -> Iterator[None]:
    """Put ``TELEGRAM_*`` in ``os.environ`` before the function-scoped autouse purge runs.

    Module scope is set up before every function-scoped fixture of this module, which is what a
    ``.env``-sourcing shell did on the server before pytest even started.
    """
    with pytest.MonkeyPatch.context() as mp:
        for key, value in _TELEGRAM_ENV.items():
            mp.setenv(key, value)
        yield


def _leak_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-inject the keys inside the test body, after the autouse purge has run."""
    for key, value in _TELEGRAM_ENV.items():
        monkeypatch.setenv(key, value)


@contextmanager
def _test_main_collaborators(settings: Settings) -> Iterator[None]:
    """The collaborator patches of the ``tests/test_main.py`` fixtures, nothing more.

    ``TelegramNotifier`` is deliberately *not* patched: that is the gap the incident went through.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.merge = AsyncMock()
    session.add = MagicMock()
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    db = MagicMock()
    db.init_db = AsyncMock()
    db.close_db = AsyncMock()
    db.is_initialized = True
    db.session = MagicMock(return_value=session_cm)
    db.read_session = MagicMock(return_value=session_cm)

    rest = MagicMock()
    rest.close = AsyncMock()
    rest.get_balance = AsyncMock(return_value={"EUR": Decimal("1000.00"), "XBT": Decimal("0.0")})
    rest.initialize_paper_balance = AsyncMock()
    rest.is_paper_mode = True
    rest.exchange_name = "kraken"

    ws = MagicMock()
    ws.connect = AsyncMock()
    ws.close = AsyncMock()
    ws.subscribe_ohlc = AsyncMock()
    ws.subscribe_ticker = AsyncMock()

    engine = MagicMock()
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    strategy = MagicMock()
    strategy.start = AsyncMock()
    strategy.stop = AsyncMock()
    strategy.get_name.return_value = "multi_strategy_router"
    strategy.bot_id = "multi_router"

    analyzer = MagicMock()
    analyzer.initialize = AsyncMock()
    risk_manager = MagicMock()
    risk_manager.register_strategy = MagicMock()

    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()

    with (
        patch("krakenbot.main.get_settings", return_value=settings),
        patch("krakenbot.main.configure_logging"),
        patch("krakenbot.main.get_logger", return_value=MagicMock()),
        patch("krakenbot.main.get_event_bus", return_value=bus),
        patch("krakenbot.main.DatabaseManager", return_value=db),
        patch("krakenbot.main.build_exchange_rest_client", return_value=rest),
        patch("krakenbot.main.build_exchange_ws_client", return_value=ws),
        patch("krakenbot.main.ExecutionEngine", return_value=engine),
        patch("krakenbot.main.MultiTimeframeAnalyzer", return_value=analyzer),
        patch("krakenbot.main.GlobalRiskManager", return_value=risk_manager),
        patch.dict(
            "krakenbot.main.STRATEGY_REGISTRY",
            {"multi_strategy_router": MagicMock(return_value=strategy)},
        ),
    ):
        yield


def test_autouse_purge_strips_telegram_env() -> None:
    """The autouse purge of ``tests/conftest.py`` removes the three keys before the body runs."""
    present = sorted(key for key in _TELEGRAM_ENV if key in os.environ)
    assert present == []


def test_mock_settings_ignores_telegram_env(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """``mock_settings`` yields a disabled, token-less Telegram block whatever ``os.environ`` says."""
    _leak_telegram_env(monkeypatch)
    settings: Settings = request.getfixturevalue("mock_settings")

    assert settings.telegram.enabled is False
    assert settings.telegram.bot_token.get_secret_value() == ""
    assert settings.telegram.chat_id == ""


@pytest.mark.asyncio
async def test_bot_start_never_registers_a_notifier_under_telegram_env(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Along the ``tests/test_main.py`` path (setup → start), ``set_notifier`` is never called.

    The registration happens in ``setup()`` step 4 (``_init_telegram_notifier``) and the detached
    ``send_bot_started`` of ``start()`` step 7 reads the registered notifier; the spy replaces the
    name bound in ``krakenbot.main``, so even red this test sends nothing.
    """
    _leak_telegram_env(monkeypatch)
    settings: Settings = request.getfixturevalue("mock_settings")
    settings.multi_strategy = MultiStrategySettings(
        enabled=True,
        strategies=[
            StrategyInstanceConfig(
                name="multi_strategy_router", bot_id="multi_router", params={"strategies": {}}
            )
        ],
    )
    set_notifier_spy = MagicMock(name="set_notifier")
    monkeypatch.setattr("krakenbot.main.set_notifier", set_notifier_spy)

    with _test_main_collaborators(settings):
        bot = KrakenBot()
        await bot.setup()
        await bot.start()

    set_notifier_spy.assert_not_called()
