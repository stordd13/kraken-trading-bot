"""B4.2 — Reference capture / compare / verify harness for the backtest engines.

Step 0 of B4.2 needs the pre-refactor engines' outputs at **full Decimal precision** so that
the iso-fees regression (a replay with ``--fees binance``) can be proven bit-exact on the trade
list and not only on the printed report (the debug logs carry floats and no fee at all).

This script never modifies the engines: ``capture`` builds them exactly like the single-run
path of ``scripts/backtest.py`` ``main()`` and serialises ``engine.metrics``.  ``fee_model`` is
passed to the constructors **only when ``--fees`` is given**, so the same command runs on the
HEAD-intact engines (step 0) and on the refactored ones (replays).

Sub-commands
------------
``capture``        run one backtest (DB read-only) and write the canonical JSON (schema 1)
``compare``        byte-exact comparison of two JSON files projected on the schema-1 core keys
                   (extra keys written by the post-refactor ``--trades-out`` are ignored)
``verify-fees``    check every trade of a post-refactor ``--trades-out`` dump against a fee model
``normalise-log``  strip timestamps / ANSI / main()-only lines from a backtest log for a byte diff

Usage (repo root, tunnel up)::

    poetry run python scripts/audit/b4_2_reference_capture.py capture \\
        --strategy grok_supertrend_4h --pair BTC/USDC --exchange binance \\
        --start-date 2023-04-01 --end-date 2026-04-01 --interval 5 --capital 1000 \\
        --out results/b4_2_ref_signal_A_head.json
    poetry run python scripts/audit/b4_2_reference_capture.py compare A.json B.json
    poetry run python scripts/audit/b4_2_reference_capture.py verify-fees dump.json --fees bybit
    poetry run python scripts/audit/b4_2_reference_capture.py normalise-log run.log --out run.norm

Exit codes: 0 ok, 1 difference / violation found, 2 usage or input error.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from krakenbot.config.settings import ExchangeFees  # noqa: E402

SCHEMA_VERSION = 1

#: Fee models the harness can verify against (same factories as the engines).
FEE_FACTORIES = {
    "bybit": lambda: ExchangeFees.bybit_defaults(),
    "binance": lambda: ExchangeFees.binance_defaults(use_bnb=True),
    "kraken": lambda: ExchangeFees.kraken_defaults(),
}

#: Top-level keys of schema 1 (everything else is dropped by ``project_core``).
CORE_TOP_KEYS = (
    "schema_version",
    "engine",
    "strategy",
    "pair",
    "exchange",
    "period",
    "interval",
    "capital",
    "metrics",
    "regime_breakdown",
    "grid",
    "trades",
)

#: Per-trade keys of schema 1.
CORE_TRADE_KEYS = (
    "n",
    "timestamp",
    "side",
    "price",
    "amount_usdc",
    "amount_crypto",
    "fee",
    "pnl",
    "regime",
)

_ZERO = Decimal("0")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_TS_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")
#: Lines printed by ``main()`` after B4.2 (never by the engines) — dropped before a byte diff.
_MAIN_ONLY_RE = re.compile(r"^(Fee model:|Trades written to |EXIT_[A-Z0-9_]*=)")


# ---------------------------------------------------------------------------
# Serialisation helpers (pure)
# ---------------------------------------------------------------------------


def _dec(value: Any) -> str | None:
    """Serialise a Decimal (or None) without any rounding."""
    if value is None:
        return None
    return str(value)


def _side(value: Any) -> str:
    """``TradeSide`` enum or plain string -> 'buy' / 'sell'."""
    raw = getattr(value, "value", value)
    return str(raw).lower()


def trade_to_core(trade: Any, n: int) -> dict[str, Any]:
    """Project one ``BacktestTrade`` onto the schema-1 per-trade keys."""
    timestamp = trade.timestamp
    return {
        "n": n,
        "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
        "side": _side(trade.side),
        "price": _dec(trade.price),
        "amount_usdc": _dec(trade.amount_usdc),
        "amount_crypto": _dec(trade.amount_crypto),
        "fee": _dec(trade.fee),
        "pnl": _dec(trade.pnl),
        "regime": trade.regime,
    }


def capture_payload(
    engine: Any,
    *,
    strategy: str,
    pair: str,
    exchange: str,
    start: datetime,
    end: datetime,
    interval: int,
    capital: float,
) -> dict[str, Any]:
    """Build the schema-1 payload from a finished engine (no engine mutation)."""
    trades = list(engine.metrics.trades)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine": type(engine).__name__,
        "strategy": strategy,
        "pair": pair,
        "exchange": exchange,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "interval": interval,
        "capital": str(Decimal(str(capital))),
        "metrics": engine.metrics.to_dict(),
        "trades": [trade_to_core(t, n) for n, t in enumerate(trades, start=1)],
    }
    regime_stats = getattr(engine, "_regime_stats", None)
    if regime_stats:
        payload["regime_breakdown"] = {
            regime: {
                "trades": stats["trades"],
                "wins": stats["wins"],
                "losses": stats["losses"],
                "pnl": _dec(stats["pnl"]),
            }
            for regime, stats in sorted(regime_stats.items())
        }
    if hasattr(engine, "pairs_completed"):
        payload["grid"] = {
            "pairs_completed": engine.pairs_completed,
            "grid_profit": _dec(engine.grid_profit),
            "total_fees": _dec(engine.total_fees),
            "total_orders_placed": engine.total_orders_placed,
            "rebalance_count": engine.rebalance_count,
            "btc_held": _dec(engine.btc_held),
            "fills": {
                "buy": sum(1 for t in trades if _side(t.side) == "buy"),
                "sell": sum(1 for t in trades if _side(t.side) == "sell"),
                # A grid trade is a forced end-of-run liquidation iff it is billed taker
                # (every other grid fill is a resting limit order, maker). HEAD-intact B4.2
                # engines had no such attribute and never reached the force-close -> 0;
                # since B4.3 the terminal inventory is liquidated on the grok path too.
                "force_closed": sum(1 for t in trades if getattr(t, "liquidity", None) == "taker"),
            },
        }
    return payload


def dumps_canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# compare (pure)
# ---------------------------------------------------------------------------


def project_core(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only the schema-1 keys (top level and per trade)."""
    core = {k: payload[k] for k in CORE_TOP_KEYS if k in payload}
    core["trades"] = [{k: t.get(k) for k in CORE_TRADE_KEYS} for t in payload.get("trades", [])]
    return core


def first_difference(a: Any, b: Any, path: str = "$") -> str | None:
    """Return the JSON path of the first difference between two values, or None."""
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}.{key}: missing on one side"
            diff = first_difference(a[key], b[key], f"{path}.{key}")
            if diff:
                return diff
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            diff = first_difference(x, y, f"{path}[{i}]")
            if diff:
                return diff
        return None
    if a != b:
        return f"{path}: {a!r} != {b!r}"
    return None


def drop_key(payload: dict[str, Any], dotted: str) -> None:
    """Remove ``dotted`` (e.g. ``metrics.net_pnl``) from ``payload`` in place, if present."""
    parts = dotted.split(".")
    node: Any = payload
    for part in parts[:-1]:
        node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            return
    if isinstance(node, dict):
        node.pop(parts[-1], None)


def compare_payloads(
    a: dict[str, Any], b: dict[str, Any], ignore: tuple[str, ...] | list[str] = ()
) -> str | None:
    """Byte-exact comparison of the schema-1 projections; None when identical.

    ``ignore`` lists dotted keys dropped from BOTH projections before the comparison
    (B4.3 guard: ``metrics.net_pnl`` moves by exactly the sell fees, everything else must
    stay bit-exact). The inputs are never mutated.
    """
    pa, pb = copy.deepcopy(project_core(a)), copy.deepcopy(project_core(b))
    for key in ignore:
        drop_key(pa, key)
        drop_key(pb, key)
    if dumps_canonical(pa) == dumps_canonical(pb):
        return None
    return first_difference(pa, pb) or "$: canonical dumps differ"


# ---------------------------------------------------------------------------
# verify-fees (pure)
# ---------------------------------------------------------------------------


def _d(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def verify_fees(payload: dict[str, Any], fees: ExchangeFees) -> tuple[list[str], dict[str, int]]:
    """Check every trade of a post-refactor dump against ``fees``.

    Returns ``(violations, counts)`` where counts is keyed by ``side/kind`` with kind in
    ``maker`` (resting limit fill), ``taker-market`` (market order with spread+slippage on
    the price — since B4.3 this includes the grid's end-of-run liquidation, priced
    ``reference × (1 − spread − slippage)``) and ``taker-liquidation`` (taker without any
    price adjustment: the pre-B4.3 mark-to-market convention, kept for old dumps).
    """
    violations: list[str] = []
    counts: dict[str, int] = {}
    fee_sum = _ZERO
    for t in payload.get("trades", []):
        n = t.get("n")
        side = t.get("side")
        liquidity = t.get("liquidity")
        fee = _d(t.get("fee"))
        fee_rate = _d(t.get("fee_rate"))
        fee_base = _d(t.get("fee_base_usdc"))
        price = _d(t.get("price"))
        reference = _d(t.get("reference_price"))
        spread = _d(t.get("spread_pct"))
        slippage = _d(t.get("slippage_pct"))
        if fee is None or fee_rate is None or fee_base is None or price is None:
            violations.append(f"trade {n}: missing fee audit fields")
            continue
        if fee != fee_base * fee_rate:
            violations.append(f"trade {n}: fee {fee} != fee_base {fee_base} * rate {fee_rate}")
        fee_sum += fee
        if liquidity == "maker":
            kind = "maker"
            if fee_rate != fees.maker:
                violations.append(f"trade {n}: maker rate {fee_rate} != {fees.maker}")
            if spread not in (None, _ZERO) or slippage not in (None, _ZERO):
                violations.append(f"trade {n}: maker fill carries spread/slippage")
            if reference is not None and price != reference:
                violations.append(f"trade {n}: maker price {price} != reference {reference}")
        elif liquidity == "taker":
            if fee_rate != fees.taker:
                violations.append(f"trade {n}: taker rate {fee_rate} != {fees.taker}")
            if spread in (None, _ZERO) and slippage in (None, _ZERO):
                kind = "taker-liquidation"
                if reference is not None and price != reference:
                    violations.append(
                        f"trade {n}: liquidation price {price} != reference {reference}"
                    )
            else:
                kind = "taker-market"
                if spread != fees.spread or slippage != fees.slippage:
                    violations.append(
                        f"trade {n}: taker costs {spread}/{slippage} != "
                        f"{fees.spread}/{fees.slippage}"
                    )
                if reference is not None:
                    factor = (
                        Decimal("1") + spread + slippage
                        if side == "buy"
                        else Decimal("1") - spread - slippage
                    )
                    if price != reference * factor:
                        violations.append(
                            f"trade {n}: taker price {price} != reference {reference} * {factor}"
                        )
        else:
            violations.append(f"trade {n}: unknown liquidity {liquidity!r}")
            continue
        counts[f"{side}/{kind}"] = counts.get(f"{side}/{kind}", 0) + 1
    metrics_fees = payload.get("metrics", {}).get("total_fees")
    if metrics_fees is not None and float(fee_sum) != float(metrics_fees):
        violations.append(f"sum of trade fees {fee_sum} != metrics.total_fees {metrics_fees}")
    return violations, counts


# ---------------------------------------------------------------------------
# normalise-log (pure)
# ---------------------------------------------------------------------------


def normalise_log_lines(lines: list[str]) -> list[str]:
    """Strip ANSI codes, the wall-clock prefix and main()-only lines; keep everything else."""
    out: list[str] = []
    for raw in lines:
        line = _TS_PREFIX_RE.sub("", _ANSI_RE.sub("", raw.rstrip("\n")))
        if _MAIN_ONLY_RE.match(line):
            continue
        out.append(line)
    return out


# ---------------------------------------------------------------------------
# capture (DB read-only)
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


async def run_capture(args: argparse.Namespace) -> dict[str, Any]:
    """Build the engine like ``scripts/backtest.py`` main()'s single-run path and run it."""
    from backtest import BacktestEngine, GridBacktester  # deferred: import-time side effects

    from krakenbot.config.settings import get_settings
    from krakenbot.core.database import DatabaseManager

    start = _parse_date(args.start_date)
    end = _parse_date(args.end_date)
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    try:
        cls = GridBacktester if args.strategy in GridBacktester.GRID_STRATEGIES else BacktestEngine
        kwargs: dict[str, Any] = {
            "strategy_name": args.strategy,
            "candle_interval": args.interval,
            "exchange": args.exchange,
            "starting_capital": args.capital,
        }
        if args.fees is not None:
            kwargs["fee_model"] = args.fees
        engine = cls(settings, db_manager, **kwargs)
        await engine.run(args.pair, start, end)
    finally:
        await db_manager.close_db()
    return capture_payload(
        engine,
        strategy=args.strategy,
        pair=args.pair,
        exchange=args.exchange,
        start=start,
        end=end,
        interval=args.interval,
        capital=args.capital,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="B4.2 reference capture / compare / verify.")
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Run one backtest and write the schema-1 JSON.")
    cap.add_argument("--strategy", required=True)
    cap.add_argument("--pair", required=True)
    cap.add_argument("--exchange", required=True, help="OHLC data source (kraken|binance).")
    cap.add_argument("--start-date", required=True)
    cap.add_argument("--end-date", required=True)
    cap.add_argument("--interval", type=int, required=True)
    cap.add_argument("--capital", type=float, default=1000.0)
    cap.add_argument(
        "--fees",
        default=None,
        help="Fee model forwarded as fee_model= (only on engines that accept it).",
    )
    cap.add_argument("--out", type=Path, required=True)

    cmp_ = sub.add_parser("compare", help="Compare two JSON captures on the schema-1 keys.")
    cmp_.add_argument("left", type=Path)
    cmp_.add_argument("right", type=Path)
    cmp_.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="DOTTED.KEY",
        help="Drop this key from both projections before comparing (repeatable), "
        "e.g. --ignore metrics.net_pnl (B4.3 signal guard).",
    )

    ver = sub.add_parser("verify-fees", help="Verify a --trades-out dump against a fee model.")
    ver.add_argument("dump", type=Path)
    ver.add_argument("--fees", choices=sorted(FEE_FACTORIES), required=True)

    norm = sub.add_parser("normalise-log", help="Normalise a backtest log for a byte diff.")
    norm.add_argument("log", type=Path)
    norm.add_argument("--out", type=Path, default=None)
    return parser


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "capture":
        payload = asyncio.run(run_capture(args))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(dumps_canonical(payload), encoding="utf-8")
        m = payload["metrics"]
        print(
            f"captured {payload['engine']} {args.strategy} {args.pair}: "
            f"{len(payload['trades'])} trades, return {m['total_return_pct']:+.2f} %, "
            f"fees {m['total_fees']:.2f} -> {args.out}",
            file=sys.stderr,
        )
        return 0
    if args.command == "compare":
        diff = compare_payloads(_load(args.left), _load(args.right), ignore=args.ignore)
        ignored = f" ignoring {', '.join(args.ignore)}" if args.ignore else ""
        if diff is None:
            print(f"IDENTICAL (schema-1 projection{ignored}): {args.left} == {args.right}")
            return 0
        print(f"DIFFERENT: {diff}")
        return 1
    if args.command == "verify-fees":
        violations, counts = verify_fees(_load(args.dump), FEE_FACTORIES[args.fees]())
        for key in sorted(counts):
            print(f"{key:<24} {counts[key]:>6}")
        if violations:
            for v in violations:
                print(f"VIOLATION: {v}")
            print(f"{len(violations)} violation(s) against fee model {args.fees}")
            return 1
        print(f"OK: every trade matches fee model {args.fees}")
        return 0
    if args.command == "normalise-log":
        lines = normalise_log_lines(args.log.read_text(encoding="utf-8").splitlines())
        text = "\n".join(lines) + "\n"
        if args.out is None:
            sys.stdout.write(text)
        else:
            args.out.write_text(text, encoding="utf-8")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
