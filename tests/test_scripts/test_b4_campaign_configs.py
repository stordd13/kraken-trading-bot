"""B4.3 campaign configs (GATE B): runner plumbing, flag rule, fee-aware benchmarks, engine
min-order floor and effective-parameter capture. No DB.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

import b4_flags
import compute_benchmarks as cb
import run_p6_walkforward as wf

from krakenbot.config.settings import ExchangeFees
from krakenbot.models.market_data import OHLCData
from krakenbot.strategies.base import SignalType, TradingSignal
from scripts import p7_grids, p7_report
from scripts import run_p6_backtests as p6
from scripts import run_p7_grid_search as p7
from scripts.backtest import BacktestEngine, GridBacktester, capture_effective_params

COSTS = '{"BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"}, "ETH/USDC": {"spread": "0.0003", "slippage": "0.0002"}}'


@pytest.fixture
def costs_file(tmp_path: Path) -> Path:
    path = tmp_path / "pair_costs.json"
    path.write_text(COSTS)
    return path


# ---------------------------------------------------------------------------
# P6 runner
# ---------------------------------------------------------------------------


class TestP6Plumbing:
    def test_parse_args_defaults_and_flags(self, costs_file: Path) -> None:
        args = p6.parse_args(["--fees", "bybit"])
        assert args.pair_costs_file is None and args.min_order_usdc == 1.0
        args = p6.parse_args(
            ["--fees", "bybit", "--pair-costs-file", str(costs_file), "--min-order-usdc", "5"]
        )
        assert args.pair_costs_file == costs_file and args.min_order_usdc == 5.0

    def test_invalid_pair_costs_file_exits_2(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('{"BTC/USDC": {"spread": "0.0002"}}')
        with pytest.raises(SystemExit) as exc:
            p6.parse_args(["--fees", "bybit", "--pair-costs-file", str(bad)])
        assert exc.value.code == 2

    def test_jobs_carry_campaign_fields_and_legacy_dicts_load(self) -> None:
        jobs = p6.build_job_list(fees="bybit", pair_costs_file="config/x.json", min_order_usdc=5)
        assert {j["pair_costs_file"] for j in jobs} == {"config/x.json"}
        assert {j["min_order_usdc"] for j in jobs} == {5}
        legacy = {
            k: v for k, v in jobs[0].items() if k not in ("pair_costs_file", "min_order_usdc")
        }
        job = p6.Job.from_dict(legacy)
        assert job.pair_costs_file is None and job.min_order_usdc == 1.0

    def test_resume_refuses_other_campaign_costs(self) -> None:
        jobs = p6.build_job_list(fees="bybit", pair_costs_file="config/x.json", min_order_usdc=5)
        key = p6.make_key(jobs[0]["strategy"], jobs[0]["pair"])
        same = {key: {"fees": "bybit", "pair_costs_file": "config/x.json", "min_order_usdc": 5.0}}
        assert jobs[0] not in p6.filter_pending_jobs(jobs, same, force=False, fees="bybit")
        for other in (
            {"fees": "bybit", "pair_costs_file": None, "min_order_usdc": 5.0},
            {"fees": "bybit", "pair_costs_file": "config/x.json", "min_order_usdc": 1.0},
            {"fees": "bybit"},  # pre-B4.3 entry = (None, 1.0)
        ):
            with pytest.raises(p6.CampaignConfigMismatchError):
                p6.filter_pending_jobs(jobs, {key: other}, force=False, fees="bybit")
        assert len(
            p6.filter_pending_jobs(jobs, {key: {"fees": "bybit"}}, force=True, fees="bybit")
        ) == len(jobs)


# ---------------------------------------------------------------------------
# P7 runner
# ---------------------------------------------------------------------------


class TestP7Plumbing:
    def test_parse_args_report_paths(self, tmp_path: Path, costs_file: Path) -> None:
        args = p7.parse_args(
            [
                "--phase",
                "report",
                "--fees",
                "bybit",
                "--pair-costs-file",
                str(costs_file),
                "--min-order-usdc",
                "5",
                "--phase1-input",
                str(tmp_path / "p1.json"),
                "--phase2-input",
                str(tmp_path / "p2.json"),
                "--report",
                str(tmp_path / "r.md"),
                "--selection",
                str(tmp_path / "s.json"),
                "--benchmarks",
                str(tmp_path / "b.json"),
            ]
        )
        assert args.phase2_input == tmp_path / "p2.json" and args.report == tmp_path / "r.md"
        assert args.selection == tmp_path / "s.json" and args.benchmarks == tmp_path / "b.json"
        assert args.min_order_usdc == 5.0

    def test_phase1_jobs_carry_campaign_fields(self) -> None:
        jobs = p7.build_phase1_jobs(
            strategy_filter="grok_supertrend_4h",
            pair_filter="BTC/USDC",
            fees="bybit",
            pair_costs_file="config/x.json",
            min_order_usdc=5,
        )
        assert {j["pair_costs_file"] for j in jobs} == {"config/x.json"}
        assert p7.P7Job.from_dict(jobs[0]).min_order_usdc == 5

    def test_phase2_refuses_phase1_entries_of_other_campaign(self) -> None:
        top_k = {
            ("s", "BTC/USDC"): [
                {"strategy": "s", "pair": "BTC/USDC", "params": {}, "fees": "bybit"}  # (None, 1.0)
            ]
        }
        with pytest.raises(p7.CampaignConfigMismatchError):
            p7.build_phase2_jobs(
                top_k, fees="bybit", pair_costs_file="config/x.json", min_order_usdc=5
            )
        jobs = p7.build_phase2_jobs(top_k, fees="bybit")
        assert jobs and jobs[0]["pair_costs_file"] is None and jobs[0]["min_order_usdc"] == 1.0

    def test_assert_results_campaign_signature(self, tmp_path: Path) -> None:
        entries = {
            "k": {"fees": "bybit", "pair_costs_file": "config/x.json", "min_order_usdc": 5.0}
        }
        p7._assert_results_fee_model(entries, "bybit", tmp_path / "p.json")  # fees only: fine
        p7._assert_results_fee_model(
            entries,
            "bybit",
            tmp_path / "p.json",
            pair_costs_file="config/x.json",
            min_order_usdc=5,
            check_campaign=True,
        )
        with pytest.raises(p7.CampaignConfigMismatchError):
            p7._assert_results_fee_model(
                entries,
                "bybit",
                tmp_path / "p.json",
                pair_costs_file=None,
                min_order_usdc=5,
                check_campaign=True,
            )

    def test_load_benchmark_sharpe(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text(
            json.dumps(
                {
                    "buy_and_hold": {"BTC/USDC": {"sharpe_ratio": 0.5}},
                    "dca_fixed_15usd_weekly": {
                        "BTC/USDC": {"sharpe_ratio": 1.5},
                        "ETH/USDC": {"error": "no data"},
                    },
                }
            )
        )
        assert p7.load_benchmark_sharpe(path) == {
            "BTC/USDC": {"buy_and_hold": 0.5, "dca_fixed": 1.5},
            "ETH/USDC": {"buy_and_hold": 0.0, "dca_fixed": 0.0},
        }

    def test_grid_spacing_sweep_rebased_for_bybit(self) -> None:
        assert p7_grids.GRID_ATR_GRID["min_spacing_pct"] == [0.015, 0.020, 0.025, 0.030]
        assert len(p7_grids.build_phase1_combos()) == 212


# ---------------------------------------------------------------------------
# Walk-forward runner
# ---------------------------------------------------------------------------


class TestWalkForwardPlumbing:
    def test_parse_args_flags(self, costs_file: Path) -> None:
        args = wf.parse_args(
            ["--fees", "bybit", "--pair-costs-file", str(costs_file), "--min-order-usdc", "5"]
        )
        assert sorted(args.pair_costs) == ["BTC/USDC", "ETH/USDC"] and args.min_order_usdc == 5.0

    def test_survivors_of_other_campaign_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        survivors = tmp_path / "s.json"
        survivors.write_text(
            json.dumps({"k": {"strategy": "s", "pair": "BTC/USDC", "fees": "bybit"}})
        )
        import asyncio

        rc = asyncio.run(
            wf.main(
                [
                    "--fees",
                    "bybit",
                    "--survivors",
                    str(survivors),
                    "--min-order-usdc",
                    "5",
                    "--output",
                    str(tmp_path / "o.json"),
                ]
            )
        )
        assert rc == 2
        assert "min_order_usdc" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Flag rule
# ---------------------------------------------------------------------------


class TestFlagRule:
    CLEAN = {
        "residual_net_proceeds": "0",
        "residual_trade_btc": "0",
        "inventory_divergence_btc": "-1.1E-29",
        "dust_written_off_btc": "-9.8E-30",
        "net_pnl_lot_basis": "128.8725417880159",
    }

    def test_clean_segment_has_no_flag(self) -> None:
        assert b4_flags.flag_segment(self.CLEAN, {"net_pnl": 128.872541788016}) == []
        assert b4_flags.flag_segment(None, {"net_pnl": 1.0}) == []

    def test_divergence_residual_and_formula_gap_are_flagged(self) -> None:
        bad = dict(self.CLEAN, residual_net_proceeds="22.4", inventory_divergence_btc="0.005")
        reasons = b4_flags.flag_segment(bad, {"net_pnl": 128.87})
        assert any("residual proceeds" in r for r in reasons)
        assert any("inventory divergence" in r for r in reasons)
        gap = b4_flags.flag_segment(self.CLEAN, {"net_pnl": 100.0})
        assert gap and "formula vs cash" in gap[0]

    def test_collect_and_render(self) -> None:
        results = {
            "ok": {
                "strategy": "g",
                "pair": "BTC/USDC",
                "liquidation": {"all": self.CLEAN},
                "all": {"net_pnl": 128.872541788016},
            },
            "bad": {
                "strategy": "g",
                "pair": "SOL/USDC",
                "params": {"a": 1},
                "liquidation": {"test": dict(self.CLEAN, residual_net_proceeds="1")},
                "test": {"net_pnl": 5.0},
            },
            "err": {"error": "boom"},
            "signal": {"strategy": "s", "pair": "ETH/USDC", "all": {"net_pnl": 1.0}},
        }
        flags = b4_flags.collect_flags(results)
        assert [f["run"] for f in flags] == ["bad"] and flags[0]["segment"] == "test"
        md = "\n".join(b4_flags.render_flags_markdown(flags))
        assert "`bad`" in md and "a=1" in md
        assert "No run flagged" in "\n".join(b4_flags.render_flags_markdown([]))
        wf_results = {
            "k": {
                "strategy": "g",
                "pair": "BTC/USDC",
                "windows": [
                    {
                        "window": 3,
                        "liquidation": dict(self.CLEAN, inventory_divergence_btc="0.01"),
                        "metrics": {"net_pnl": 128.872541788016},
                    }
                ],
            }
        }
        wf_flags = b4_flags.collect_flags(wf_results, walkforward=True)
        assert wf_flags[0]["segment"] == "window 3"


# ---------------------------------------------------------------------------
# P7 report: benchmarks file, flagged runs and effective params in the selection
# ---------------------------------------------------------------------------


def _window(idx: int, sharpe: float, flagged: bool = False) -> dict:
    liq = {
        "residual_net_proceeds": "1" if flagged else "0",
        "inventory_divergence_btc": "0",
        "net_pnl_lot_basis": "1.0",
    }
    return {
        "strategy": "grok_grid_atr_adaptive_v4",
        "pair": "BTC/USDC",
        "params": {"min_spacing_pct": 0.02},
        "fees": "bybit",
        "phase": "2",
        "window_idx": idx,
        "period": {"train_start": "t", "train_end": "t", "test_start": "t", "test_end": "t"},
        "train": {"sharpe_ratio": 1.0},
        "test": {
            "sharpe_ratio": sharpe,
            "profit_factor": 2.0,
            "total_trades": 40,
            "max_drawdown_pct": 5.0,
            "net_pnl": 1.0,
        },
        "effective_params": {
            "strategy_class": "GrokGridATRAdaptiveV4",
            "passed_params": {},
            "params": {"order_size_usdc": {"value": "25", "source": "class_default"}},
        },
        "liquidation": {"test": liq, "train": dict(liq, residual_net_proceeds="0")},
    }


class TestP7ReportCampaign:
    """GO P7 rules (Bruno, 2026-09-15): a flagged config is ineligible whatever its score (1);
    trades next to every metric and benchmark return/MaxDD with the DCA note (2); criteria
    unchanged (3)."""

    LOW = {"BTC/USDC": {"buy_and_hold": 0.1, "dca_fixed": 0.1}}

    def _report(self, tmp_path: Path, p1: dict, p2: dict, **kw) -> tuple[dict, str]:
        p1_path, p2_path = tmp_path / "p1.json", tmp_path / "p2.json"
        p1_path.write_text(json.dumps(p1))
        p2_path.write_text(json.dumps(p2))
        md, sel = tmp_path / "r.md", tmp_path / "s.json"
        selection = p7_report.generate_report(p1_path, p2_path, md, sel, **kw)
        return selection, md.read_text()

    def test_report_uses_benchmarks_file_and_effective_params(self, tmp_path: Path) -> None:
        p2 = {
            f"grok_grid_atr_adaptive_v4_BTC_USDC_p2_abcd1234_w{i}": _window(i, 1.0)
            for i in range(8)
        }
        # A benchmark above the OOS Sharpe must abandon the combo (criterion 7)...
        selection, _ = self._report(
            tmp_path, {}, p2, benchmarks={"BTC/USDC": {"buy_and_hold": 5.0, "dca_fixed": 5.0}}
        )
        assert selection["selected_for_paper"] == [] and len(selection["abandoned"]) == 1
        # ... and a low one selects it, with the runtime-captured params embedded and the
        # trade counts next to the metrics (GO P7 rule 2).
        selection, text = self._report(tmp_path, {}, p2, benchmarks=self.LOW)
        assert len(selection["selected_for_paper"]) == 1
        sel = selection["selected_for_paper"][0]
        assert sel["effective_params"]["params"]["order_size_usdc"]["value"] == "25"
        assert sel["mean_trades_test"] == 40 and sel["min_trades_window"] == 40
        assert selection["flagged_runs"] == [] and selection["ineligible_flagged"] == []
        assert "campaign benchmarks file" in text and "order_size_usdc" in text
        assert "1.00 (n=40)" in text and "40 / 40" in text
        assert "Reading rule (GO P7, rule 2)" in text
        assert (
            json.loads((tmp_path / "s.json").read_text())["benchmarks"]["BTC/USDC"]["buy_and_hold"]
            == 0.1
        )

    def test_flagged_window_makes_the_config_ineligible_whatever_its_score(
        self, tmp_path: Path
    ) -> None:
        p2 = {
            f"grok_grid_atr_adaptive_v4_BTC_USDC_p2_abcd1234_w{i}": _window(
                i, 1.0, flagged=(i == 2)
            )
            for i in range(8)
        }
        selection, text = self._report(tmp_path, {}, p2, benchmarks=self.LOW)
        # The config passes the 7 criteria but is flagged → never selected (GO P7 rule 1).
        assert selection["selected_for_paper"] == []
        assert [f["segment"] for f in selection["flagged_runs"]] == ["test"]
        assert len(selection["ineligible_flagged"]) == 1
        inel = selection["ineligible_flagged"][0]
        assert inel["passed_criteria"] is True and inel["n_flags"] == 1
        assert inel["params_hash"] == "abcd1234" and inel["mean_trades_test"] == 40
        assert inel["flagged_runs"] == ["grok_grid_atr_adaptive_v4_BTC_USDC_p2_abcd1234_w2/test"]
        assert len(selection["abandoned"]) == 1
        assert "flagged" in selection["abandoned"][0]["reason"]
        assert selection["abandoned"][0]["n_ineligible"] == 1
        # The 7 criteria themselves are untouched (rule 3): the verdict still says passed.
        assert [v["passed"] for v in selection["all_verdicts"]] == [True]
        assert "Ineligible configurations (flag rule" in text and "Flagged runs" in text

    def test_phase1_flag_alone_makes_the_config_ineligible(self, tmp_path: Path) -> None:
        p1 = {
            "grok_grid_atr_adaptive_v4_BTC_USDC_p1_abcd1234": {
                "strategy": "grok_grid_atr_adaptive_v4",
                "pair": "BTC/USDC",
                "params": {"min_spacing_pct": 0.02},
                "train": {"sharpe_ratio": 1.0, "total_trades": 30},
                "test": {"sharpe_ratio": 1.0, "profit_factor": 2.0, "total_trades": 40},
                "all": {"sharpe_ratio": 1.0, "net_pnl": 5.0},
                "liquidation": {
                    "all": {
                        "residual_net_proceeds": "0",
                        "inventory_divergence_btc": "-0.03",
                        "net_pnl_lot_basis": "5.0",
                    }
                },
            },
            # Another config of the same combo, clean in phase 1 and selected.
            "grok_grid_atr_adaptive_v4_BTC_USDC_p1_ffff0000": {
                "strategy": "grok_grid_atr_adaptive_v4",
                "pair": "BTC/USDC",
                "params": {"min_spacing_pct": 0.03},
                "train": {"sharpe_ratio": 0.9, "total_trades": 30},
                "test": {"sharpe_ratio": 0.9, "profit_factor": 1.9, "total_trades": 35},
            },
        }
        p2 = {
            f"grok_grid_atr_adaptive_v4_BTC_USDC_p2_abcd1234_w{i}": _window(i, 1.5)
            for i in range(8)
        }
        p2.update(
            {
                f"grok_grid_atr_adaptive_v4_BTC_USDC_p2_ffff0000_w{i}": dict(
                    _window(i, 0.9), params={"min_spacing_pct": 0.03}
                )
                for i in range(8)
            }
        )
        selection, text = self._report(tmp_path, p1, p2, benchmarks=self.LOW)
        assert [f["segment"] for f in selection["flagged_runs"]] == ["all"]
        # abcd1234 has the best OOS Sharpe (1.5) but its phase-1 run is flagged → ineligible;
        # the clean ffff0000 (0.9) is the one selected.
        assert [i["params_hash"] for i in selection["ineligible_flagged"]] == ["abcd1234"]
        assert [s["params_hash"] for s in selection["selected_for_paper"]] == ["ffff0000"]
        assert selection["abandoned"] == []
        assert "Train Sharpe (n trades)" in text and "1.00 (n=30)" in text

    def test_all_configs_flagged_abandons_the_combo(self, tmp_path: Path) -> None:
        p2 = {
            f"grok_grid_atr_adaptive_v4_BTC_USDC_p2_abcd1234_w{i}": _window(i, 1.0, flagged=True)
            for i in range(8)
        }
        selection, _ = self._report(tmp_path, {}, p2, benchmarks=self.LOW)
        assert selection["selected_for_paper"] == []
        assert len(selection["ineligible_flagged"]) == 1
        assert selection["ineligible_flagged"][0]["n_flags"] == 8
        assert "All 1 configuration(s) are flagged" in selection["abandoned"][0]["reason"]

    def test_benchmark_details_table_and_dca_note(self, tmp_path: Path) -> None:
        p2 = {
            f"grok_grid_atr_adaptive_v4_BTC_USDC_p2_abcd1234_w{i}": _window(i, 1.0)
            for i in range(8)
        }
        details = {
            "BTC/USDC": {
                "buy_and_hold": {"sharpe": 0.84, "return_pct": 137.5, "max_drawdown_pct": 49.6},
                "dca_fixed": {"sharpe": 2.35, "return_pct": 45.2, "max_drawdown_pct": 100.0},
            }
        }
        _, text = self._report(tmp_path, {}, p2, benchmarks=self.LOW, benchmark_details=details)
        assert "| Buy & Hold Return | Buy & Hold MaxDD | DCA fixed Return |" in text
        assert "| BTC/USDC | 0.84 | +137.5% | 49.6% | +45.2% | 100.0% | 2.35 |" in text
        assert "not comparable" in text and "Reading rule (GO P7, rule 2)" in text

    def test_load_benchmark_details(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text(
            json.dumps(
                {
                    "buy_and_hold": {
                        "BTC/USDC": {
                            "sharpe_ratio": 0.5,
                            "total_return_pct": 10.0,
                            "max_drawdown_pct": 20.0,
                        }
                    },
                    "dca_fixed_15usd_weekly": {
                        "BTC/USDC": {"sharpe_ratio": 1.5, "total_return_pct": -5.0},
                        "ETH/USDC": {"error": "no data"},
                    },
                }
            )
        )
        details = p7.load_benchmark_details(path)
        assert details["BTC/USDC"]["buy_and_hold"] == {
            "sharpe": 0.5,
            "return_pct": 10.0,
            "max_drawdown_pct": 20.0,
        }
        assert details["BTC/USDC"]["dca_fixed"]["return_pct"] == -5.0
        assert details["ETH/USDC"]["dca_fixed"]["sharpe"] == 0.0
        # criterion 7 keeps its own loader, unchanged
        assert p7.load_benchmark_sharpe(path)["BTC/USDC"] == {"buy_and_hold": 0.5, "dca_fixed": 1.5}


# ---------------------------------------------------------------------------
# Benchmarks under a fee model
# ---------------------------------------------------------------------------


def _daily(n: int, price: str = "100") -> list[OHLCData]:
    return [
        OHLCData(
            timestamp=datetime(2025, 3, 3, tzinfo=UTC) + timedelta(days=i),
            pair="BTC/USDC",
            interval=1440,
            exchange="binance",
            open=Decimal(price),
            high=Decimal(price),
            low=Decimal(price),
            close=Decimal(price),
            volume=Decimal("1"),
            vwap=Decimal(price),
            trades_count=1,
        )
        for i in range(n)
    ]


class TestBenchmarksFees:
    def test_buy_and_hold_pays_taker_and_costs_once(self) -> None:
        candles = _daily(15)
        assert cb.buy_and_hold(candles)["ending_balance"] == 1000.0
        bh = cb.buy_and_hold(candles, fees=ExchangeFees.bybit_defaults())
        assert bh["ending_balance"] == pytest.approx(1000 * (1 - 0.0025) / (1 + 0.0004), abs=0.01)
        assert bh["entry_fee_usdc"] == 2.5
        override = {"BTC/USDC": cb.PairCosts(Decimal("0.0011"), Decimal("0.0002"))}
        bh2 = cb.buy_and_hold(candles, fees=ExchangeFees.bybit_defaults(), pair_costs=override)
        assert bh2["ending_balance"] == pytest.approx(1000 * (1 - 0.0025) / (1 + 0.0013), abs=0.01)

    def test_dca_pays_maker_on_each_buy(self) -> None:
        candles = _daily(15)
        assert cb.dca_fixed_weekly(candles)["ending_balance"] == 45.0  # 3 Mondays x 15
        dca = cb.dca_fixed_weekly(candles, fees=ExchangeFees.bybit_defaults())
        assert dca["ending_balance"] == pytest.approx(45 * (1 - 0.001), abs=0.01)  # rounded 2 dp

    def test_parse_args(self, costs_file: Path, tmp_path: Path) -> None:
        args = cb.parse_args(["--fees", "none"])
        assert args.fees == "none" and args.pair_costs is None
        args = cb.parse_args(
            [
                "--fees",
                "bybit",
                "--pair-costs-file",
                str(costs_file),
                "--output",
                str(tmp_path / "b.json"),
            ]
        )
        assert (
            sorted(args.pair_costs) == ["BTC/USDC", "ETH/USDC"]
            and args.output == tmp_path / "b.json"
        )
        with pytest.raises(SystemExit):
            cb.parse_args([])


# ---------------------------------------------------------------------------
# Engine: min-order floor and effective-parameter capture
# ---------------------------------------------------------------------------


class TestEngineMinOrder:
    @staticmethod
    def _engine(min_order: float) -> BacktestEngine:
        settings = MagicMock()
        settings.trading.default_order_amount_eur = 25.0
        engine = BacktestEngine(
            settings,
            MagicMock(),
            fee_model="bybit",
            strategy_name="grok_supertrend_4h",
            min_order_usdc=min_order,
        )
        engine.strategy = MagicMock()
        engine.strategy.on_trade_filled = AsyncMock()
        engine.usdc_balance = Decimal("3")
        return engine

    @pytest.mark.asyncio
    async def test_order_below_floor_is_skipped_and_default_keeps_it(self) -> None:
        signal = TradingSignal(
            pair="BTC/USDC",
            signal_type=SignalType.BUY,
            price=Decimal("100"),
            timestamp=datetime(2025, 3, 1, tzinfo=UTC),
            confidence=1.0,
            reason="test",
            strategy="grok_supertrend_4h",
            metadata={"order_size_usdc": 3},
        )
        strict = self._engine(5.0)
        await strict.execute_signal(signal, Decimal("100"), is_limit_fill=True)
        assert strict.metrics.trades == [] and strict.usdc_balance == Decimal("3")
        lenient = self._engine(1.0)
        await lenient.execute_signal(signal, Decimal("100"), is_limit_fill=True)
        assert len(lenient.metrics.trades) == 1 and lenient.min_order_usdc == Decimal("1.0")


@pytest.mark.asyncio
async def test_capture_effective_params_reports_defaults_passed_and_overrides() -> None:
    from tests.test_scripts.test_grid_terminal_liquidation import _grid_settings

    engine = GridBacktester(
        _grid_settings(),
        MagicMock(),
        fee_model="bybit",
        strategy_params_override={"min_spacing_pct": 0.02},
    )
    engine._strategy_params = {**engine._strategy_params, "pair": "BTC/USDC"}
    strategy, _ = await engine._create_grok_grid_strategy()
    eff = engine.effective_params
    assert eff["strategy_class"] == "GrokGridATRAdaptiveV4"
    assert eff["params"]["min_spacing_pct"] == {"value": "0.02", "source": "override"}
    assert eff["params"]["order_size_usdc"] == {
        "value": "25",
        "source": "passed",
    }  # fixture YAML value
    assert eff["params"]["pair"]["source"] == "passed"
    bare = GridBacktester(_grid_settings(), MagicMock(), fee_model="bybit")
    bare._strategy_params = {}
    strategy, _ = await bare._create_grok_grid_strategy()
    assert bare.effective_params["params"]["order_size_usdc"] == {
        "value": "25",
        "source": "class_default",
    }
    assert bare.effective_params["params"]["atr_multiplier"] == {
        "value": "4.0",
        "source": "class_default",
    }
    # liquidation_summary is the dump's block
    assert set(engine.liquidation_summary()) >= {
        "positions",
        "net_pnl_lot_basis",
        "residual_net_proceeds",
        "inventory_divergence_btc",
    }
    assert capture_effective_params(object(), None, None)["params"] == {}


# ---------------------------------------------------------------------------
# Post-P6 checkpoint summary
# ---------------------------------------------------------------------------


def test_p6_checkpoint_summary_lines(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path(_project_root) / "scripts" / "audit"))
    import b4_p6_checkpoint as cp

    good = {
        "sharpe_ratio": 1.5,
        "sortino_ratio": 2.0,
        "max_drawdown_pct": 10.0,
        "profit_factor": 2.0,
        "calmar_ratio": 1.0,
        "total_trades": 40,
        "total_return_pct": 5.0,
        "net_pnl": 50.0,
    }
    results = {
        "grok_supertrend_4h_BTC_USDC": {
            "strategy": "grok_supertrend_4h",
            "pair": "BTC/USDC",
            "fees": "bybit",
            "pair_costs_file": "config/pair_costs_b4.json",
            "min_order_usdc": 5.0,
            "train": dict(good),
            "test": dict(good),
            "all": dict(good),
        },
        "grok_grid_atr_adaptive_v4_BTC_USDC": {
            "strategy": "grok_grid_atr_adaptive_v4",
            "pair": "BTC/USDC",
            "fees": "bybit",
            "pair_costs_file": "config/pair_costs_b4.json",
            "min_order_usdc": 5.0,
            "train": dict(good),
            "test": dict(good, total_trades=0),
            "all": dict(good),
            "liquidation": {
                "all": {
                    "positions": 3,
                    "pnl": "-10",
                    "fees": "0.1",
                    "residual_net_proceeds": "0",
                    "inventory_divergence_btc": "0",
                    "net_pnl_lot_basis": "50.0",
                }
            },
        },
        "crashed": {"strategy": "x", "pair": "ETH/USDC", "error": "boom"},
    }
    lines = cp.summarize(results, {"buy_and_hold": {"BTC/USDC": {"sharpe_ratio": 0.1}}})
    assert len(lines) == 10
    assert lines[0].startswith("1. Completion: 2/24") and "crashed" in lines[0]
    assert "grok_supertrend_4h_BTC_USDC" in lines[2]  # survivor
    assert "0 trades" in lines[5]  # anomaly on the grid test segment
    assert "3 lots" in lines[6]
    assert "STOP" in lines[9]


# ---------------------------------------------------------------------------
# P7 checkpoint summary (phase 1 and phase 2 shapes)
# ---------------------------------------------------------------------------


def test_p7_checkpoint_summary_lines() -> None:
    sys.path.insert(0, str(Path(_project_root) / "scripts" / "audit"))
    import b4_p7_checkpoint as cp

    good = {
        "sharpe_ratio": 0.6,
        "profit_factor": 1.6,
        "total_trades": 25,
        "total_return_pct": 3.0,
        "max_drawdown_pct": 12.0,
        "net_pnl": 30.0,
    }
    base = {
        "fees": "bybit",
        "pair_costs_file": "config/pair_costs_b4.json",
        "min_order_usdc": 5.0,
        "params": {"min_spacing_pct": 0.02},
    }
    p1 = {
        "grok_supertrend_4h_BTC_USDC_p1_aaaa1111": dict(
            base,
            strategy="grok_supertrend_4h",
            pair="BTC/USDC",
            phase="1",
            train=dict(good),
            test=dict(good),
            all=dict(good),
        ),
        "grok_grid_atr_adaptive_v4_SOL_USDC_p1_bbbb2222": dict(
            base,
            strategy="grok_grid_atr_adaptive_v4",
            pair="SOL/USDC",
            phase="1",
            train=dict(good),
            test=dict(good, profit_factor=12.0, total_trades=4),
            all=dict(good),
            liquidation={
                "all": {
                    "positions": 3,
                    "pnl": "-10",
                    "fees": "0.1",
                    "residual_net_proceeds": "0",
                    "inventory_divergence_btc": "-0.03",
                    "net_pnl_lot_basis": "30.0",
                }
            },
        ),
        "crashed_p1_cccc3333": {"strategy": "x", "pair": "ETH/USDC", "phase": "1", "error": "boom"},
    }
    lines = cp.summarize(p1)
    assert len(lines) == 10
    assert lines[0].startswith("1. Completion (phase 1): 2/212") and "crashed" in lines[0]
    assert "1 flagged run(s) → 1 ineligible config(s)" in lines[2] and "#bbbb2222" in lines[2]
    assert "too good — PF 12.0 on 4 trades" in lines[3]
    assert "n=25" in lines[4] and "train 0.60" in lines[4]
    assert "grok_supertrend_4h_BTC_USDC_p1_aaaa1111" in lines[5]  # clears criteria 1-2-4
    assert "1 not reconciled" in lines[6]
    assert lines[9].startswith("10. Verdict: phase 1 INCOMPLETE") and "STOP" in lines[9]

    p2 = {
        f"grok_supertrend_4h_BTC_USDC_p2_aaaa1111_w{i}": dict(
            base,
            strategy="grok_supertrend_4h",
            pair="BTC/USDC",
            phase="2",
            window_idx=i,
            period={"train_start": "t", "train_end": "t", "test_start": "t", "test_end": "t"},
            train=dict(good),
            test=dict(good, sharpe_ratio=1.0),
        )
        for i in range(8)
    }
    lines = cp.summarize(p2, {"BTC/USDC": {"buy_and_hold": 0.1, "dca_fixed": 0.1}})
    assert lines[0].startswith("1. Completion (phase 2): 8/280")
    assert "1 passing, 1 passing AND eligible" in lines[5]
    assert "n=25" in lines[4]
    assert "0 segments" in lines[6]
