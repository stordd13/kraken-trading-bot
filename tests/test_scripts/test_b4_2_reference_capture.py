"""Pure tests for scripts/audit/b4_2_reference_capture.py (no DB, no engine run)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

import b4_2_reference_capture as h  # noqa: E402

from krakenbot.config.settings import ExchangeFees  # noqa: E402
from krakenbot.models.base import TradeSide  # noqa: E402

T0 = datetime(2025, 3, 1, tzinfo=UTC)
T1 = datetime(2025, 3, 2, tzinfo=UTC)


def _trade(**kw):
    base = {
        "timestamp": T0,
        "side": TradeSide.BUY,
        "price": Decimal("100.5"),
        "amount_usdc": Decimal("50"),
        "amount_crypto": Decimal("0.497512437810945273631840796"),
        "fee": Decimal("0.0375"),
        "pnl": None,
        "regime": "bull",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _metrics(trades, total_fees="0.0375"):
    return SimpleNamespace(
        trades=trades,
        to_dict=lambda: {"total_trades": 1, "total_fees": float(Decimal(total_fees))},
    )


def _signal_engine(trades):
    engine = SimpleNamespace(metrics=_metrics(trades))
    engine._regime_stats = {
        "bull": {"trades": 1, "pnl": Decimal("1.5"), "wins": 1, "losses": 0},
    }
    return engine


class _GridEngine:
    def __init__(self, trades):
        self.metrics = _metrics(trades)
        self.pairs_completed = 1
        self.grid_profit = Decimal("1.5")
        self.total_fees = Decimal("0.0375")
        self.total_orders_placed = 3
        self.rebalance_count = 0
        self.btc_held = Decimal("0.01")


def _payload(engine, **kw):
    args = {
        "strategy": "s",
        "pair": "BTC/USDC",
        "exchange": "binance",
        "start": T0,
        "end": T1,
        "interval": 5,
        "capital": 1000.0,
    }
    args.update(kw)
    return h.capture_payload(engine, **args)


class TestCapturePayload:
    def test_signal_engine_schema(self) -> None:
        payload = _payload(_signal_engine([_trade()]))
        assert payload["schema_version"] == 1
        assert payload["engine"] == "SimpleNamespace"
        assert payload["capital"] == "1000.0"
        assert payload["period"] == {"start": T0.isoformat(), "end": T1.isoformat()}
        assert payload["regime_breakdown"] == {
            "bull": {"trades": 1, "wins": 1, "losses": 0, "pnl": "1.5"}
        }
        assert "grid" not in payload
        (trade,) = payload["trades"]
        assert trade == {
            "n": 1,
            "timestamp": T0.isoformat(),
            "side": "buy",
            "price": "100.5",
            "amount_usdc": "50",
            "amount_crypto": "0.497512437810945273631840796",
            "fee": "0.0375",
            "pnl": None,
            "regime": "bull",
        }

    def test_decimals_are_never_rounded(self) -> None:
        payload = _payload(_signal_engine([_trade(price=Decimal("28444.01751"))]))
        assert payload["trades"][0]["price"] == "28444.01751"

    def test_grid_engine_fills_and_force_closed(self) -> None:
        trades = [
            _trade(),
            _trade(side=TradeSide.SELL, pnl=Decimal("1.5")),
            _trade(side=TradeSide.SELL, pnl=Decimal("-2"), liquidity="taker"),
        ]
        payload = _payload(_GridEngine(trades))
        assert payload["engine"] == "_GridEngine"
        assert payload["grid"] == {
            "pairs_completed": 1,
            "grid_profit": "1.5",
            "total_fees": "0.0375",
            "total_orders_placed": 3,
            "rebalance_count": 0,
            "btc_held": "0.01",
            "fills": {"buy": 1, "sell": 2, "force_closed": 1},
        }
        assert "regime_breakdown" not in payload

    def test_plain_string_side_is_accepted(self) -> None:
        payload = _payload(_signal_engine([_trade(side="sell")]))
        assert payload["trades"][0]["side"] == "sell"


class TestCompare:
    def test_identical_after_projection_ignores_extra_keys(self) -> None:
        a = _payload(_signal_engine([_trade()]))
        b = _payload(_signal_engine([_trade()]))
        b["fees"] = "bybit"
        b["trades"][0]["liquidity"] = "maker"
        b["trades"][0]["fee_rate"] = "0.0010"
        assert h.compare_payloads(a, b) is None

    def test_detects_first_differing_trade_field(self) -> None:
        a = _payload(_signal_engine([_trade()]))
        b = _payload(_signal_engine([_trade(fee=Decimal("0.0376"))]))
        diff = h.compare_payloads(a, b)
        assert diff is not None
        assert diff.startswith("$.trades[0].fee")

    def test_detects_length_and_metrics_differences(self) -> None:
        a = _payload(_signal_engine([_trade()]))
        b = _payload(_signal_engine([_trade(), _trade()]))
        assert "length" in (h.compare_payloads(a, b) or "")
        c = _payload(_signal_engine([_trade()]))
        c["metrics"]["total_fees"] = 9.9
        assert (h.compare_payloads(a, c) or "").startswith("$.metrics.total_fees")


def _dump_trade(n, side, liquidity, fees: ExchangeFees, *, liquidation=False):
    reference = Decimal("100")
    fee_base = Decimal("50")
    if liquidity == "maker":
        rate, spread, slippage, price = fees.maker, Decimal("0"), Decimal("0"), reference
    elif liquidation:
        rate, spread, slippage, price = fees.taker, Decimal("0"), Decimal("0"), reference
    else:
        rate, spread, slippage = fees.taker, fees.spread, fees.slippage
        factor = 1 + spread + slippage if side == "buy" else 1 - spread - slippage
        price = reference * factor
    return {
        "n": n,
        "timestamp": T0.isoformat(),
        "side": side,
        "liquidity": liquidity,
        "price": str(price),
        "reference_price": str(reference),
        "amount_usdc": "50",
        "amount_crypto": "0.5",
        "fee": str(fee_base * rate),
        "fee_rate": str(rate),
        "fee_base_usdc": str(fee_base),
        "spread_pct": str(spread),
        "slippage_pct": str(slippage),
        "pnl": None,
        "regime": None,
    }


class TestVerifyFees:
    def test_synthetic_bybit_dump_passes(self) -> None:
        fees = ExchangeFees.bybit_defaults()
        trades = [
            _dump_trade(1, "buy", "maker", fees),
            _dump_trade(2, "sell", "taker", fees),
            _dump_trade(3, "sell", "taker", fees, liquidation=True),
        ]
        total = sum(Decimal(t["fee"]) for t in trades)
        payload = {"metrics": {"total_fees": float(total)}, "trades": trades}
        violations, counts = h.verify_fees(payload, fees)
        assert violations == []
        assert counts == {"buy/maker": 1, "sell/taker-market": 1, "sell/taker-liquidation": 1}

    def test_wrong_rate_and_spread_on_maker_are_violations(self) -> None:
        fees = ExchangeFees.bybit_defaults()
        bad_rate = _dump_trade(1, "buy", "maker", fees)
        bad_rate["fee_rate"] = "0.0025"
        bad_rate["fee"] = str(Decimal("50") * Decimal("0.0025"))
        maker_with_spread = _dump_trade(2, "sell", "maker", fees)
        maker_with_spread["spread_pct"] = "0.0002"
        payload = {"metrics": {}, "trades": [bad_rate, maker_with_spread]}
        violations, _ = h.verify_fees(payload, fees)
        assert any("maker rate" in v for v in violations)
        assert any("spread/slippage" in v for v in violations)

    def test_fee_must_equal_base_times_rate_and_sum_metrics(self) -> None:
        fees = ExchangeFees.binance_defaults(use_bnb=True)
        t = _dump_trade(1, "buy", "maker", fees)
        t["fee"] = "0.04"
        payload = {"metrics": {"total_fees": 0.0375}, "trades": [t]}
        violations, _ = h.verify_fees(payload, fees)
        assert any("!= fee_base" in v for v in violations)
        assert any("metrics.total_fees" in v for v in violations)

    def test_unknown_liquidity_is_a_violation(self) -> None:
        fees = ExchangeFees.kraken_defaults()
        t = _dump_trade(1, "buy", "maker", fees)
        t["liquidity"] = None
        violations, counts = h.verify_fees({"metrics": {}, "trades": [t]}, fees)
        assert any("unknown liquidity" in v for v in violations)
        assert counts == {}


class TestNormaliseLog:
    def test_strips_prefix_ansi_and_main_only_lines(self) -> None:
        lines = [
            "2026-09-14 08:53:01 [info     ] backtest_starting component=backtest",
            "\x1b[32m2026-09-14 08:53:02\x1b[0m [debug    ] backtest_buy price=1.0",
            "Fee model: bybit (maker 0.0010 / taker 0.0025)",
            "Trades written to results/x.json",
            "EXIT_A1=0",
            "Total Return:                  +2.42%",
        ]
        assert h.normalise_log_lines(lines) == [
            "[info     ] backtest_starting component=backtest",
            "[debug    ] backtest_buy price=1.0",
            "Total Return:                  +2.42%",
        ]


class TestCli:
    def test_compare_cli_exit_codes(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        a = _payload(_signal_engine([_trade()]))
        b = _payload(_signal_engine([_trade(fee=Decimal("1"))]))
        pa, pb = tmp_path / "a.json", tmp_path / "b.json"
        pa.write_text(h.dumps_canonical(a))
        pb.write_text(h.dumps_canonical(b))
        assert h.main(["compare", str(pa), str(pa)]) == 0
        assert h.main(["compare", str(pa), str(pb)]) == 1
        assert "DIFFERENT: $.trades[0].fee" in capsys.readouterr().out

    def test_verify_fees_cli(self, tmp_path: Path) -> None:
        fees = ExchangeFees.bybit_defaults()
        t = _dump_trade(1, "buy", "maker", fees)
        dump = tmp_path / "d.json"
        dump.write_text(
            h.dumps_canonical({"metrics": {"total_fees": float(Decimal(t["fee"]))}, "trades": [t]})
        )
        assert h.main(["verify-fees", str(dump), "--fees", "bybit"]) == 0
        assert h.main(["verify-fees", str(dump), "--fees", "kraken"]) == 1

    def test_normalise_log_cli_writes_file(self, tmp_path: Path) -> None:
        log = tmp_path / "run.log"
        log.write_text("2026-09-14 08:53:01 [info     ] x\nFee model: bybit\n")
        out = tmp_path / "run.norm"
        assert h.main(["normalise-log", str(log), "--out", str(out)]) == 0
        assert out.read_text() == "[info     ] x\n"

    def test_capture_requires_arguments(self) -> None:
        with pytest.raises(SystemExit) as exc:
            h.main(["capture", "--strategy", "s"])
        assert exc.value.code == 2
