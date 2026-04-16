"""Tests for _override_pair_in_params helper and pair override wiring."""

# ruff: noqa: E402

from pathlib import Path
import sys

# Add scripts directory to path (same pattern as tests/test_backtest.py)
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from backtest import _override_pair_in_params


def test_override_pair_in_params_with_dict() -> None:
    original = {"rsi_period": 7, "pair": "BTC/USDC"}
    result = _override_pair_in_params(original, "ETH/USDC")
    assert result == {"rsi_period": 7, "pair": "ETH/USDC"}
    # Original must not be mutated
    assert original == {"rsi_period": 7, "pair": "BTC/USDC"}


def test_override_pair_in_params_with_none() -> None:
    result = _override_pair_in_params(None, "SOL/USDC")
    assert result == {"pair": "SOL/USDC"}


def test_override_pair_in_params_empty_dict() -> None:
    result = _override_pair_in_params({}, "ETH/USDC")
    assert result == {"pair": "ETH/USDC"}


def test_override_pair_in_params_preserves_extra_keys() -> None:
    original = {"adx_min": 14, "ema_fast": 27, "ema_slow": 125}
    result = _override_pair_in_params(original, "SOL/USDC")
    assert result["adx_min"] == 14
    assert result["ema_fast"] == 27
    assert result["ema_slow"] == 125
    assert result["pair"] == "SOL/USDC"


def _mock_settings(pair: str = "BTC/USDC"):
    """Return a SimpleNamespace masquerading as Settings for strategy ctors."""
    from types import SimpleNamespace

    return SimpleNamespace(
        trading=SimpleNamespace(
            pair=pair,
            default_order_amount_eur=50,
        ),
        fees=SimpleNamespace(maker=0.001, taker=0.001),
    )


def test_gemini_strategy_reads_overridden_pair() -> None:
    """Instantiating a gemini strategy with pair-overridden params yields correct self.pair.

    Regression for P6.5 bug 1: strategies.yaml hardcodes pair: BTC/USDC in router
    inner params, which shadowed the backtest pair via BaseStrategy.effective_pair.
    """
    from unittest.mock import MagicMock

    from krakenbot.strategies.gemini_scalping_volatilite import GeminiScalpingVolatilite

    yaml_params = {
        "pair": "BTC/USDC",
        "rsi_period": 7,
        "rsi_oversold": 30,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 1.0,
    }
    overridden = _override_pair_in_params(yaml_params, "ETH/USDC")

    strategy = GeminiScalpingVolatilite(
        settings=_mock_settings(),
        event_bus=MagicMock(),
        db_manager=MagicMock(),
        bot_id="scalping_vol",
        strategy_params=overridden,
    )

    assert strategy.pair == "ETH/USDC"


def test_grok_supertrend_reads_overridden_pair() -> None:
    """Grok strategies must also bind to the backtest pair despite YAML hardcode."""
    from unittest.mock import MagicMock

    from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime

    yaml_params = {
        "pair": "BTC/USDC",
        "supertrend_period": 10,
        "supertrend_multiplier": 3.0,
        "order_size_usdc": 50,
    }
    overridden = _override_pair_in_params(yaml_params, "SOL/USDC")

    strategy = GrokSuperTrend4hRegime(
        settings=_mock_settings(),
        event_bus=MagicMock(),
        db_manager=MagicMock(),
        bot_id="supertrend_4h",
        strategy_params=overridden,
    )

    assert strategy.pair == "SOL/USDC"
