"""B4.3 chantier 0 — GATE A reconciliation of a grid reference run against its B4.2 baseline.

Pure, read-only. Given the B4.2 HEAD-intact capture (schema 1, engine without terminal
liquidation) and the post-chantier-0 artefacts of the same run (harness capture, optional
second capture for determinism, ``--trades-out`` dump), it re-derives every pre-signed delta
of the GATE A contract (plan § 3) from the baseline alone and checks the real run against it:

- trades: the baseline trades are a bit-identical prefix, then exactly L liquidation trades
  (L = open lots reconstructed from the baseline by matching sells to buys on amount_crypto);
- each liquidation trade's implied entry ((amount_usdc - fee - pnl) / amount_crypto) is one of
  the open entries, and no SELL amount occurs more often than in the BUY multiset;
- identities: total_fees, total_pnl, net_pnl (== ending - capital, and delta == baseline sell
  fees + liquidation pnl), ending_balance (== old - V * (1 - (1-s)(1-t))), return, win/loss,
  win_rate, profit_factor, pairs_completed / grid_profit / orders / rebalances unchanged;
- conditionals read from the run: max_drawdown_pct (non-decreasing, bounded), Sharpe/Sortino,
  Calmar; liquidation block: btc_held 0, residual 0, |dust| and |divergence| below 1e-12;
- determinism (two captures identical) and the D4 proof (capture without the kwarg ==
  ``backtest.py`` dump with ``pair_costs=None`` on the schema-1 projection).

Usage::

    poetry run python scripts/audit/b4_3_gate_a_reconcile.py \\
        --baseline results/b4_2_ref_grid_A_head.json \\
        --capture results/b4_3_ref_grid_A_post.json \\
        --dump results/b4_3_ref_grid_A_post_trades.json \\
        [--capture2 /tmp/run2.json] --fees binance [--markdown out.md]

Exit 0 when every check passes, 1 otherwise (each failed check is printed).
"""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

import b4_2_reference_capture as harness  # noqa: E402

from krakenbot.config.settings import ExchangeFees  # noqa: E402

ZERO = Decimal("0")
DUST = Decimal("1e-12")
FLOAT_TOL = 1e-9  # metrics are floats in to_dict(); Decimal identities hold to ~1e-13


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def open_lots(baseline: dict[str, Any]) -> list[tuple[Decimal, Decimal]]:
    """Reconstruct the open lots of a baseline capture: buys never matched by a sell.

    Grid sells carry the exact ``amount_crypto`` of their lot, so the multiset of sell
    amounts is a sub-multiset of the buy amounts; the remainder is the terminal inventory.
    """
    trades = baseline["trades"]
    buys = [(i, t) for i, t in enumerate(trades) if t["side"] == "buy"]
    sells = [t for t in trades if t["side"] == "sell"]
    pending: dict[str, list[int]] = {}
    for i, t in buys:
        pending.setdefault(t["amount_crypto"], []).append(i)
    matched: set[int] = set()
    orphans = 0
    for s in sells:
        queue = pending.get(s["amount_crypto"])
        if queue:
            matched.add(queue.pop(0))
        else:
            orphans += 1
    if orphans:
        raise ValueError(f"{orphans} sell(s) without a matching buy amount in the baseline")
    return [(_d(t["amount_crypto"]), _d(t["price"])) for i, t in buys if i not in matched]


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str, str, bool]] = []
        self.failures: list[str] = []

    def check(self, name: str, old: Any, new: Any, expected: Any, ok: bool, note: str = "") -> None:
        self.rows.append((name, str(old), str(new), str(expected), note, ok))
        if not ok:
            self.failures.append(f"{name}: old={old} new={new} expected={expected} {note}")

    def markdown(self) -> str:
        lines = [
            "| Check | B4.2 baseline | Run post-chantier 0 | Expected / bound | Note | OK |",
            "|---|---|---|---|---|---|",
        ]
        for name, old, new, exp, note, ok in self.rows:
            lines.append(f"| {name} | {old} | {new} | {exp} | {note} | {'✅' if ok else '❌'} |")
        return "\n".join(lines) + "\n"


def reconcile(
    baseline: dict[str, Any],
    capture: dict[str, Any],
    dump: dict[str, Any],
    fees: ExchangeFees,
    capture2: dict[str, Any] | None = None,
) -> Report:
    rep = Report()
    s = fees.spread + fees.slippage
    t = fees.taker

    # --- determinism and D4 proof --------------------------------------------------------
    if capture2 is not None:
        rep.check(
            "determinism (capture run 1 == run 2)",
            "-",
            harness.compare_payloads(capture, capture2) or "IDENTICAL",
            "IDENTICAL",
            harness.compare_payloads(capture, capture2) is None,
        )
    d4 = harness.compare_payloads(capture, dump)
    rep.check(
        "D4: capture (kwarg absent) == dump (pair_costs=None)",
        "-",
        d4 or "IDENTICAL",
        "IDENTICAL",
        d4 is None,
    )

    # --- trades: baseline prefix + L liquidation trades -----------------------------------
    old_trades = baseline["trades"]
    new_trades = capture["trades"]
    lots = open_lots(baseline)
    n_old, n_lots = len(old_trades), len(lots)
    prefix_ok = (
        harness.project_core({"trades": old_trades})["trades"]
        == harness.project_core({"trades": new_trades[:n_old]})["trades"]
    )
    rep.check("baseline trades are a bit-identical prefix", n_old, n_old, n_old, prefix_ok)
    extra = new_trades[n_old:]
    dump_extra = dump["trades"][n_old:]
    tagged = [x for x in dump_extra if x.get("forced_liquidation")]
    rep.check(
        "extra trades == L open lots, all tagged forced_liquidation",
        0,
        f"{len(extra)} extra / {len(tagged)} tagged",
        n_lots,
        len(extra) == n_lots == len(tagged) and all(x["side"] == "sell" for x in extra),
    )

    # --- liquidation price / fee audit ----------------------------------------------------
    reference = _d(tagged[0]["reference_price"]) if tagged else None
    exec_price = _d(tagged[0]["price"]) if tagged else None
    if reference is not None and exec_price is not None:
        rep.check(
            "liquidation price == reference × (1 − spread − slippage)",
            "-",
            f"{exec_price} (ref {reference})",
            f"{reference * (Decimal('1') - s)}",
            exec_price == reference * (Decimal("1") - s)
            and all(_d(x["price"]) == exec_price for x in tagged),
        )
        rep.check(
            "liquidation fee == gross × taker, liquidity taker",
            "-",
            "all",
            f"rate {t}",
            all(
                _d(x["fee"]) == _d(x["amount_usdc"]) * t
                and _d(x["fee_rate"]) == t
                and x["liquidity"] == "taker"
                and _d(x["spread_pct"]) == fees.spread
                and _d(x["slippage_pct"]) == fees.slippage
                for x in tagged
            ),
        )
    # implied entries ∈ open entries (per-lot cost basis, Decimal round-trip tolerance 1e-9 rel.)
    remaining = [e for _, e in lots]
    unmatched = 0
    for x in tagged:
        if x["pnl"] is None:
            unmatched += 1
            continue
        implied = (_d(x["amount_usdc"]) - _d(x["fee"]) - _d(x["pnl"])) / _d(x["amount_crypto"])
        hit = next(
            (i for i, e in enumerate(remaining) if abs(e - implied) <= e * Decimal("1e-9")), None
        )
        if hit is None:
            unmatched += 1
        else:
            remaining.pop(hit)
    rep.check(
        "implied liquidation entries ∈ open entries (per-lot cost basis)",
        f"{n_lots} lots",
        f"{n_lots - unmatched} matched / {unmatched} unmatched",
        "all matched",
        unmatched == 0 and not remaining,
    )
    buy_amounts = Counter(x["amount_crypto"] for x in new_trades if x["side"] == "buy")
    sell_amounts = Counter(x["amount_crypto"] for x in new_trades if x["side"] == "sell")
    rep.check(
        "no SELL amount more frequent than in the BUY multiset",
        "-",
        "ok" if all(buy_amounts[a] >= n for a, n in sell_amounts.items()) else "violated",
        "ok",
        all(buy_amounts[a] >= n for a, n in sell_amounts.items()),
    )

    # --- expected metrics from the baseline alone ------------------------------------------
    om, nm = baseline["metrics"], capture["metrics"]
    og, ng = baseline["grid"], capture["grid"]
    btc_held_old = _d(og["btc_held"])
    sum_lots = sum((a for a, _ in lots), ZERO)
    rep.check(
        "Σ open lots ≈ baseline btc_held (Decimal drift < 1e-12)",
        str(btc_held_old),
        str(sum_lots),
        "|Δ| < 1e-12",
        abs(sum_lots - btc_held_old) < DUST,
    )
    liq_pnl = sum((_d(x["pnl"]) for x in tagged if x["pnl"] is not None), ZERO)
    liq_fees = sum((_d(x["fee"]) for x in tagged), ZERO)
    old_buy_fees = sum((_d(x["fee"]) for x in old_trades if x["side"] == "buy"), ZERO)
    old_sell_fees = sum((_d(x["fee"]) for x in old_trades if x["side"] == "sell"), ZERO)
    C = reference if reference is not None else ZERO
    exp_liq_pnl = sum(
        (a * C * (Decimal("1") - s) * (Decimal("1") - t) - a * e for a, e in lots), ZERO
    )
    exp_liq_fees = sum((a * C * (Decimal("1") - s) * t for a, _ in lots), ZERO)
    losers = sum(1 for a, e in lots if a * C * (Decimal("1") - s) * (Decimal("1") - t) - a * e <= 0)

    def close(a: Any, b: Any, tol: float = FLOAT_TOL) -> bool:
        return abs(float(a) - float(b)) <= tol

    rep.check(
        "liquidation pnl == Σ_lots(q·C(1−s)(1−t) − q·entry)",
        "0",
        f"{liq_pnl:.6f}",
        f"{exp_liq_pnl:.6f}",
        close(liq_pnl, exp_liq_pnl, 1e-6),
    )
    rep.check(
        "liquidation fees == Σ q·C(1−s)·t",
        "0",
        f"{liq_fees:.6f}",
        f"{exp_liq_fees:.6f}",
        close(liq_fees, exp_liq_fees, 1e-6),
    )
    rep.check(
        "total_fees == old + liquidation fees",
        f"{om['total_fees']:.6f}",
        f"{nm['total_fees']:.6f}",
        f"{_d(om['total_fees']) + liq_fees:.6f}",
        close(nm["total_fees"], _d(om["total_fees"]) + liq_fees),
    )
    rep.check(
        "total_pnl == old + liquidation pnl",
        f"{om['total_pnl']:.6f}",
        f"{nm['total_pnl']:.6f}",
        f"{_d(om['total_pnl']) + liq_pnl:.6f}",
        close(nm["total_pnl"], _d(om["total_pnl"]) + liq_pnl),
    )
    exp_net = _d(om["total_pnl"]) + liq_pnl - old_buy_fees
    rep.check(
        "net_pnl == total_pnl − buy fees",
        f"{om['net_pnl']:.6f}",
        f"{nm['net_pnl']:.6f}",
        f"{exp_net:.6f}",
        close(nm["net_pnl"], exp_net),
    )
    rep.check(
        "net_pnl delta == old sell fees + liquidation pnl (sign pre-declared)",
        "-",
        f"{_d(nm['net_pnl']) - _d(om['net_pnl']):+.6f}",
        f"{old_sell_fees + liq_pnl:+.6f}",
        close(_d(nm["net_pnl"]) - _d(om["net_pnl"]), old_sell_fees + liq_pnl),
    )
    capital = _d(capture["capital"])
    rep.check(
        "cash identity net_pnl == ending_balance − capital (≤ 1e-9)",
        "-",
        f"{nm['net_pnl']:.9f}",
        f"{_d(nm['ending_balance']) - capital:.9f}",
        close(nm["net_pnl"], _d(nm["ending_balance"]) - capital),
    )
    V = btc_held_old * C
    exp_ending = _d(om["ending_balance"]) - V * (
        Decimal("1") - (Decimal("1") - s) * (Decimal("1") - t)
    )
    rep.check(
        "ending_balance == old − V·(1 − (1−s)(1−t))",
        f"{om['ending_balance']:.6f}",
        f"{nm['ending_balance']:.6f}",
        f"{exp_ending:.6f}",
        close(nm["ending_balance"], exp_ending, 1e-6)
        and nm["ending_balance"] < om["ending_balance"],
    )
    rep.check(
        "total_return_pct strictly lower",
        f"{om['total_return_pct']:.6f}",
        f"{nm['total_return_pct']:.6f}",
        f"{float((exp_ending - capital) / capital * 100):.6f}",
        nm["total_return_pct"] < om["total_return_pct"]
        and close(nm["total_return_pct"], (exp_ending - capital) / capital * 100, 1e-6),
    )
    rep.check(
        "total_trades == old + L",
        om["total_trades"],
        nm["total_trades"],
        om["total_trades"] + n_lots,
        nm["total_trades"] == om["total_trades"] + n_lots,
    )
    rep.check(
        "winning / losing == old + winners / losers",
        f"{om['winning_trades']}/{om['losing_trades']}",
        f"{nm['winning_trades']}/{nm['losing_trades']}",
        f"{om['winning_trades'] + n_lots - losers}/{om['losing_trades'] + losers}",
        nm["winning_trades"] == om["winning_trades"] + n_lots - losers
        and nm["losing_trades"] == om["losing_trades"] + losers,
    )
    rep.check(
        "win_rate",
        f"{om['win_rate']:.6f}",
        f"{nm['win_rate']:.6f}",
        f"{(nm['winning_trades'] / nm['total_trades']) if nm['total_trades'] else 0:.6f}",
        close(
            nm["win_rate"], nm["winning_trades"] / nm["total_trades"] if nm["total_trades"] else 0
        ),
    )
    wins = sum(
        (_d(x["pnl"]) for x in new_trades if x["pnl"] is not None and _d(x["pnl"]) > 0), ZERO
    )
    losses = abs(
        sum((_d(x["pnl"]) for x in new_trades if x["pnl"] is not None and _d(x["pnl"]) < 0), ZERO)
    )
    exp_pf = float(wins / losses) if losses > 0 else float("inf")
    pf_ok = (
        (nm["profit_factor"] == exp_pf) if losses == 0 else close(nm["profit_factor"], exp_pf, 1e-6)
    )
    rep.check(
        "profit_factor == Σwins / Σ|losses| (↓ or inventory in profit)",
        om["profit_factor"],
        f"{nm['profit_factor']:.6f}" if losses else nm["profit_factor"],
        f"{exp_pf:.6f}" if losses else "inf",
        pf_ok and nm["profit_factor"] <= om["profit_factor"],
    )
    # conditionals
    max_dd_bound = float(V * (Decimal("1") - (Decimal("1") - s) * (Decimal("1") - t)))
    peak_guess = float(_d(om["ending_balance"]))  # only used for the pct bound below
    rep.check(
        "max_drawdown_pct non-decreasing, +≤ liquidation cost (conditional, read at run)",
        f"{om['max_drawdown_pct']:.6f}",
        f"{nm['max_drawdown_pct']:.6f}",
        f"[{om['max_drawdown_pct']:.6f}, +{max_dd_bound / peak_guess * 100:.4f} pt]",
        om["max_drawdown_pct"] - FLOAT_TOL
        <= nm["max_drawdown_pct"]
        <= om["max_drawdown_pct"]
        + max_dd_bound / min(peak_guess, float(capital)) * 100
        + FLOAT_TOL,
    )
    rep.check(
        "sharpe_ratio (conditional: down on this config)",
        f"{om['sharpe_ratio']:.6f}",
        f"{nm['sharpe_ratio']:.6f}",
        "≤ old",
        nm["sharpe_ratio"] <= om["sharpe_ratio"] + FLOAT_TOL,
        "one extra bar return",
    )
    rep.check(
        "sortino_ratio (conditional: down on this config)",
        f"{om['sortino_ratio']:.6f}",
        f"{nm['sortino_ratio']:.6f}",
        "≤ old",
        nm["sortino_ratio"] <= om["sortino_ratio"] + FLOAT_TOL,
    )
    rep.check(
        "calmar_ratio (derived)",
        f"{om['calmar_ratio']:.6f}",
        f"{nm['calmar_ratio']:.6f}",
        "≤ old",
        nm["calmar_ratio"] <= om["calmar_ratio"] + FLOAT_TOL,
    )
    rep.check(
        "unrealized_pnl == liquidation pnl",
        om["unrealized_pnl"],
        f"{nm['unrealized_pnl']:.6f}",
        f"{liq_pnl:.6f}",
        close(nm["unrealized_pnl"], liq_pnl),
    )
    rep.check(
        "average_holding_time_minutes unchanged (maker pairs only; liquidations excluded)",
        f"{om['average_holding_time_minutes']:.6f}",
        f"{nm['average_holding_time_minutes']:.6f}",
        f"{om['average_holding_time_minutes']:.6f}",
        close(nm["average_holding_time_minutes"], om["average_holding_time_minutes"]),
    )
    liq_block = dump.get("liquidation", {})
    rep.check(
        "net_pnl (realised cash) == net_pnl_lot_basis (lot accounting agrees with the wallet)",
        "-",
        f"{nm['net_pnl']:.9f}",
        f"{_d(liq_block.get('net_pnl_lot_basis', '0')):.9f}",
        close(nm["net_pnl"], _d(liq_block.get("net_pnl_lot_basis", "0")))
        and _d(liq_block.get("residual_net_proceeds", "1")) == ZERO,
    )
    avg_holding = liq_block.get("avg_holding_minutes")
    rep.check(
        "liquidation avg holding (from lot entry times) reported",
        "-",
        str(avg_holding),
        "> 0 when L > 0",
        ((avg_holding or 0) > 0) if n_lots else avg_holding is None,
    )
    # grid block
    rep.check(
        "pairs_completed unchanged (maker pairs)",
        og["pairs_completed"],
        ng["pairs_completed"],
        og["pairs_completed"],
        ng["pairs_completed"] == og["pairs_completed"],
    )
    rep.check(
        "grid_profit unchanged",
        og["grid_profit"],
        ng["grid_profit"],
        og["grid_profit"],
        ng["grid_profit"] == og["grid_profit"],
    )
    rep.check(
        "total_orders_placed / rebalance_count unchanged",
        f"{og['total_orders_placed']}/{og['rebalance_count']}",
        f"{ng['total_orders_placed']}/{ng['rebalance_count']}",
        "=",
        ng["total_orders_placed"] == og["total_orders_placed"]
        and ng["rebalance_count"] == og["rebalance_count"],
    )
    rep.check(
        "fills: buy =, sell + L, force_closed == L",
        str(og["fills"]),
        str(ng["fills"]),
        f"buy {og['fills']['buy']}, sell {og['fills']['sell'] + n_lots}, force_closed {n_lots}",
        ng["fills"]
        == {
            "buy": og["fills"]["buy"],
            "sell": og["fills"]["sell"] + n_lots,
            "force_closed": n_lots,
        },
    )
    rep.check(
        "btc_held after liquidation == 0",
        og["btc_held"],
        ng["btc_held"],
        "0",
        _d(ng["btc_held"]) == ZERO,
    )
    liq = dump.get("liquidation", {})
    rep.check(
        "liquidation block: positions == L, residual 0, |dust| & |divergence| < 1e-12",
        "-",
        f"pos {liq.get('positions')} res {liq.get('residual_trade_btc')} dust {liq.get('dust_written_off_btc')} div {liq.get('inventory_divergence_btc')}",
        f"pos {n_lots}",
        liq.get("positions") == n_lots
        and _d(liq.get("residual_trade_btc", "1")) == ZERO
        and abs(_d(liq.get("dust_written_off_btc", "1"))) < DUST
        and abs(_d(liq.get("inventory_divergence_btc", "1"))) < DUST,
    )
    rep.check(
        "liquidation block: buy_fees == old buy fees (no new buy)",
        f"{old_buy_fees:.6f}",
        f"{_d(liq.get('buy_fees', '0')):.6f}",
        f"{old_buy_fees:.6f}",
        _d(liq.get("buy_fees", "0")) == old_buy_fees,
    )
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--baseline", type=Path, required=True, help="B4.2 HEAD-intact capture")
    parser.add_argument(
        "--capture", type=Path, required=True, help="post-chantier-0 harness capture"
    )
    parser.add_argument("--capture2", type=Path, default=None, help="second capture (determinism)")
    parser.add_argument(
        "--dump", type=Path, required=True, help="post-chantier-0 --trades-out dump"
    )
    parser.add_argument("--fees", choices=sorted(harness.FEE_FACTORIES), required=True)
    parser.add_argument("--markdown", type=Path, default=None, help="write the table here")
    args = parser.parse_args(argv)
    rep = reconcile(
        _load(args.baseline),
        _load(args.capture),
        _load(args.dump),
        harness.FEE_FACTORIES[args.fees](),
        _load(args.capture2) if args.capture2 else None,
    )
    text = rep.markdown()
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")
    print(text)
    if rep.failures:
        for f in rep.failures:
            print(f"FAIL: {f}")
        print(f"{len(rep.failures)} check(s) failed")
        return 1
    print(f"OK: {len(rep.rows)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
