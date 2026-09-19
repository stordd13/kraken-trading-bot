"""C1 — equity probe for the A/B validation of the metrics chantier (post-audit B4).

The chantier replaces the metric formulas of both engines (``scripts/backtest.py``) but must
leave the **simulation** untouched: trades, balances and the raw equity curve have to be
bit-identical before and after. This read-only harness produces the evidence.

Sub-commands
------------
``capture``     run one backtest (DB read-only), built exactly like the single-run path of
                ``scripts/backtest.py`` ``main()`` (same construction as the B4.2 harness), and
                write the schema-1 payload (``scripts/audit/b4_2_reference_capture.py``) plus
                the engine's raw ``equity_curve`` (verbatim Decimals), the final balances, the
                per-trade audit fields and the Decimal metrics that ``to_dict()`` does not export.
                ``--engine-root PATH`` runs the engines of another checkout (a ``git worktree``
                of the reference tag) with this very script.
``compare-ab``  strict identity of two captures (trade list on the pre-C1 field set, balances,
                equity curve point by point) and the partitioned metrics table: keys that must be
                identical, keys expected to move (with the defect / convention that explains
                the move), keys added or removed by the new contract. ``--markdown`` writes the
                table. Exit 1 on any identity violation.
``compare-ab --strict`` (C2) the master confinement invariant: **everything** in the old
                capture must be byte-identical in the new one — every trade field (including
                the C1 ``buy_fee_alloc``), balances, equity curve, every metric key (identical
                *and* moving ones), Decimal extras, the grid / liquidation / regime blocks, the
                fee model, pair costs and min order. Only ``STRICT_ALLOWED_META`` may differ
                (``git_head``, ``engine_file``, ``source_fingerprints``: where the engines ran
                from) and only ``STRICT_ALLOWED_ADDITIONS`` may appear in the new capture
                (``replay_version``, ``rejections``, ``warmup``, ``dca_counters``: blocks a
                pre-C2 engine does not export). A key that disappears is a violation.

Usage (repo root, tunnel up)::

    poetry run python scripts/audit/c1_equity_probe.py capture \\
        --strategy grok_supertrend_4h --pair BTC/USDC --exchange binance \\
        --start-date 2023-04-01 --end-date 2026-04-01 --interval 5 --fees bybit \\
        --out results/c1_ab/signal_A_bybit_old.json [--engine-root /path/to/worktree]
    poetry run python scripts/audit/c1_equity_probe.py compare-ab OLD.json NEW.json --markdown t.md

Exit codes: 0 ok, 1 difference found, 2 usage or input error.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import fields as dc_fields
from datetime import UTC, datetime
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

from b4_2_reference_capture import (  # noqa: E402
    capture_payload,
    compare_payloads,
    dumps_canonical,
    first_difference,
)

PROBE_VERSION = 1  # payload superset since C2: new blocks are optional (absent = pre-C2 engine)

#: Strict mode (C2): top-level metadata keys allowed to differ between two captures.
STRICT_ALLOWED_META = ("git_head", "engine_file", "source_fingerprints")
#: Strict mode (C2): top-level keys a post-C2 capture may add over a pre-C2 one.
STRICT_ALLOWED_ADDITIONS = ("replay_version", "rejections", "warmup", "dca_counters")

#: Pre-C1 ``BacktestTrade`` fields: the identity is asserted on exactly this set (fields added
#: by C1, e.g. ``buy_fee_alloc``, are reported as "new", never compared).
TRADE_FIELDS_V1 = (
    "timestamp",
    "side",
    "price",
    "amount_usdc",
    "amount_crypto",
    "fee",
    "pnl",
    "regime",
    "liquidity",
    "fee_rate",
    "fee_base_usdc",
    "reference_price",
    "spread_pct",
    "slippage_pct",
    "forced_liquidation",
)

#: ``to_dict()`` keys (and captured Decimal extras) that the chantier must leave identical.
IDENTICAL_KEYS = (
    "total_trades",
    "winning_trades",
    "losing_trades",
    "win_rate",
    "total_return_pct",
    "net_pnl",
    "total_fees",
    "total_pnl",
    "unrealized_pnl",
    "starting_balance",
    "ending_balance",
    "duration_days",
    "average_holding_time_minutes",
    # Decimal extras (not exported by to_dict(), captured from engine.metrics)
    "max_drawdown",
    "average_win",
    "average_loss",
)

#: Keys expected to move, old key -> (new key, cause). Same-name keys map to themselves.
MOVING_KEYS: dict[str, tuple[str, str]] = {
    "sharpe_ratio": ("sharpe_ratio", "D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1"),
    "sortino_ratio": ("sortino_ratio", "D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1"),
    "max_drawdown_pct": ("max_drawdown_pct_daily", "D2 relative to running peak; D1/C2 daily NAV"),
    "profit_factor": ("profit_factor", "D3 net of the buy fee (pnl_net_trade); 0 losses -> None"),
    "calmar_ratio": ("calmar_ratio", "D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily"),
}


# ---------------------------------------------------------------------------
# Serialisation helpers (pure)
# ---------------------------------------------------------------------------


def _dec(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return str(value.value)
    return value


def trade_to_full(trade: Any, n: int) -> dict[str, Any]:
    """Every dataclass field of a ``BacktestTrade`` (old or new), Decimals as strings."""
    out: dict[str, Any] = {"n": n}
    for f in dc_fields(trade):
        out[f.name] = _dec(getattr(trade, f.name))
    return out


def build_probe_payload(engine: Any, base: dict[str, Any], engine_file: str) -> dict[str, Any]:
    """Schema-1 payload + raw equity curve + balances + Decimal metric extras (no mutation)."""
    payload = dict(base)
    payload["probe_version"] = PROBE_VERSION
    payload["engine_file"] = engine_file
    payload["trades_full"] = [trade_to_full(t, n) for n, t in enumerate(engine.metrics.trades, 1)]
    payload["equity_curve"] = [[ts.isoformat(), str(eq)] for ts, eq in engine.equity_curve]
    is_grid = hasattr(engine, "btc_held")
    payload["balances"] = {
        "usdc": str(engine.usdc_balance),
        "crypto": str(engine.btc_held if is_grid else engine.crypto_balance),
    }
    m = engine.metrics
    payload["metrics_extra"] = {
        "max_drawdown": str(m.max_drawdown),
        "average_win": str(m.average_win),
        "average_loss": str(m.average_loss),
        "start_time": m.start_time.isoformat() if m.start_time else None,
        "end_time": m.end_time.isoformat() if m.end_time else None,
    }
    if is_grid and hasattr(engine, "liquidation_summary"):
        payload["liquidation"] = engine.liquidation_summary()
    # C2 blocks — present only when the engine exports them (a pre-C2 engine does not).
    if callable(getattr(engine, "rejections_summary", None)):
        payload["rejections"] = engine.rejections_summary()
    if callable(getattr(engine, "warmup_summary", None)):
        payload["warmup"] = engine.warmup_summary()
    if callable(getattr(engine, "dca_counters_summary", None)):
        dca = engine.dca_counters_summary()
        if dca is not None:
            payload["dca_counters"] = dca
    return payload


def source_fingerprints(engine: Any, engine_file: str) -> dict[str, dict[str, str]]:
    """sha256 of the engine module and of the strategy module actually loaded (C2): the
    ``--engine-root`` capture swaps ``scripts/backtest.py`` only, ``krakenbot`` stays the
    current tree's — the fingerprints make that visible in the capture."""
    import inspect

    out: dict[str, dict[str, str]] = {}
    strategy = getattr(engine, "_strategy_obj", None) or getattr(engine, "strategy", None)
    for label, file in (
        ("backtest", engine_file),
        ("strategy", inspect.getfile(type(strategy)) if strategy is not None else None),
    ):
        if file is None:
            continue
        digest = hashlib.sha256(Path(file).read_bytes()).hexdigest()
        out[label] = {"path": str(Path(file).resolve()), "sha256": digest}
    return out


def write_capture(path: Path, payload: dict[str, Any]) -> str:
    text = dumps_canonical(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_capture(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# compare-ab (pure)
# ---------------------------------------------------------------------------


def compare_identity(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Violations of the simulation identity (empty list = identical)."""
    v: list[str] = []
    ot, nt = old.get("trades_full", []), new.get("trades_full", [])
    if len(ot) != len(nt):
        v.append(f"trades: {len(ot)} != {len(nt)}")
    for a, b in zip(ot, nt, strict=False):
        for key in TRADE_FIELDS_V1:
            if a.get(key) != b.get(key):
                v.append(f"trade {a.get('n')}.{key}: {a.get(key)!r} != {b.get(key)!r}")
                break
        if len(v) > 20:
            v.append("... (truncated)")
            break
    if old.get("balances") != new.get("balances"):
        v.append(f"balances: {old.get('balances')} != {new.get('balances')}")
    oe, ne = old.get("equity_curve", []), new.get("equity_curve", [])
    if len(oe) != len(ne):
        v.append(f"equity_curve: {len(oe)} != {len(ne)} points")
    for i, (a, b) in enumerate(zip(oe, ne, strict=False)):
        if a != b:
            v.append(f"equity_curve[{i}]: {a} != {b}")
            break
    for key in ("grid", "regime_breakdown"):
        if old.get(key) != new.get(key):
            v.append(f"{key}: differs")
    om, nm = old.get("metrics", {}), new.get("metrics", {})
    ox, nx = old.get("metrics_extra", {}), new.get("metrics_extra", {})
    for key in IDENTICAL_KEYS:
        a = om.get(key, ox.get(key))
        b = nm.get(key, nx.get(key))
        if a != b:
            v.append(f"metrics.{key}: {a!r} != {b!r} (must be identical)")
    # schema-1 projection: everything but the moving / added / removed metric keys (the
    # IDENTICAL_KEYS were compared above; the trades core is compared here again)
    contract_delta = (set(om) ^ set(nm)) | set(MOVING_KEYS) | {nk for nk, _ in MOVING_KEYS.values()}
    diff = compare_payloads(old, new, ignore=[f"metrics.{k}" for k in sorted(contract_delta)])
    if diff is not None:
        v.append(f"schema-1 projection (ignoring moving / new / removed metric keys): {diff}")
    return v


def compare_strict(
    old: dict[str, Any],
    new: dict[str, Any],
    *,
    allowed_meta: tuple[str, ...] = STRICT_ALLOWED_META,
    allowed_additions: tuple[str, ...] = STRICT_ALLOWED_ADDITIONS,
) -> list[str]:
    """Violations of the strict (C2) identity: every key of ``old`` byte-identical in ``new``
    (canonical JSON of each top-level block, deep), additions limited to ``allowed_additions``,
    ``allowed_meta`` ignored on both sides, a disappeared key is a violation."""
    v: list[str] = []
    o = {k: val for k, val in old.items() if k not in allowed_meta}
    n = {k: val for k, val in new.items() if k not in allowed_meta}
    for key in sorted(set(n) - set(o)):
        if key not in allowed_additions:
            v.append(f"new top-level key {key!r} is not an allowed addition")
    for key in sorted(set(o) - set(n)):
        v.append(f"key {key!r} disappeared from the new capture")
    for key in sorted(set(o) & set(n)):
        diff = first_difference(o[key], n[key], path=f"$.{key}")
        if diff is not None:
            v.append(diff)
    return v


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6f}" if abs(value) < 1e6 else repr(value)
    return str(value)


def metrics_table(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, str]]:
    """Partitioned rows: identical / moving (with cause) / new / removed."""
    om, nm = old.get("metrics", {}), new.get("metrics", {})
    ox, nx = old.get("metrics_extra", {}), new.get("metrics_extra", {})
    rows: list[dict[str, str]] = []
    for key in IDENTICAL_KEYS:
        a = om.get(key, ox.get(key))
        b = nm.get(key, nx.get(key))
        rows.append(
            {
                "key": key,
                "old": _fmt(a),
                "new": _fmt(b),
                "status": "identical" if a == b else "DIFFERENT (violation)",
                "cause": "-",
            }
        )
    for old_key, (new_key, cause) in MOVING_KEYS.items():
        a, b = om.get(old_key), nm.get(new_key)
        label = old_key if old_key == new_key else f"{old_key} -> {new_key}"
        rows.append(
            {"key": label, "old": _fmt(a), "new": _fmt(b), "status": "moving", "cause": cause}
        )
    known_new = set(IDENTICAL_KEYS) | {nk for nk, _ in MOVING_KEYS.values()}
    for key in sorted(set(nm) - known_new):
        rows.append({"key": key, "old": "-", "new": _fmt(nm[key]), "status": "new", "cause": "-"})
    for key in sorted(set(om) - set(IDENTICAL_KEYS) - set(MOVING_KEYS)):
        rows.append(
            {"key": key, "old": _fmt(om[key]), "new": "-", "status": "removed", "cause": "-"}
        )
    return rows


def render_markdown(old: dict[str, Any], new: dict[str, Any], violations: list[str]) -> str:
    lines = [
        f"### {old.get('engine')} — {old.get('strategy')} {old.get('pair')} "
        f"{old.get('period', {}).get('start', '')[:10]} → {old.get('period', {}).get('end', '')[:10]} "
        f"(`--fees {old.get('fees', '?')}`)",
        "",
        f"- trades: {len(old.get('trades_full', []))} / equity points: "
        f"{len(old.get('equity_curve', []))} / balances: {old.get('balances')}",
        f"- old engine: `{old.get('engine_file')}` · new engine: `{new.get('engine_file')}`",
        "- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, "
        + ("schema-1 projection): **IDENTICAL**" if not violations else "…): **VIOLATIONS**"),
    ]
    for item in violations:
        lines.append(f"  - {item}")
    lines += ["", "| Key | Old | New | Status | Cause |", "|---|---|---|---|---|"]
    for r in metrics_table(old, new):
        lines.append(f"| `{r['key']}` | {r['old']} | {r['new']} | {r['status']} | {r['cause']} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# capture (DB read-only)
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _git_head(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "?"


async def run_capture(args: argparse.Namespace) -> dict[str, Any]:
    """Build and run the engine like ``scripts/backtest.py`` main()'s single-run path."""
    if args.engine_root is not None:
        root = Path(args.engine_root).resolve()
        for sub in ("scripts", "src"):
            sys.path.insert(0, str(root / sub))
    import backtest  # deferred: resolves to --engine-root when given

    from krakenbot.config.settings import get_settings
    from krakenbot.core.database import DatabaseManager

    start, end = _parse_date(args.start_date), _parse_date(args.end_date)
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    try:
        cls = (
            backtest.GridBacktester
            if args.strategy in backtest.GridBacktester.GRID_STRATEGIES
            else backtest.BacktestEngine
        )
        kwargs: dict[str, Any] = {
            "strategy_name": args.strategy,
            "candle_interval": args.interval,
            "exchange": args.exchange,
            "starting_capital": args.capital,
            "fee_model": args.fees,
            "min_order_usdc": args.min_order_usdc,
        }
        if args.pair_costs_file is not None:
            kwargs["pair_costs"] = backtest.load_pair_costs(Path(args.pair_costs_file))
        engine = cls(settings, db_manager, **kwargs)
        await engine.run(args.pair, start, end)
    finally:
        await db_manager.close_db()
    base = capture_payload(
        engine,
        strategy=args.strategy,
        pair=args.pair,
        exchange=args.exchange,
        start=start,
        end=end,
        interval=args.interval,
        capital=args.capital,
    )
    base["fees"] = args.fees
    base["pair_costs_file"] = args.pair_costs_file
    base["min_order_usdc"] = args.min_order_usdc
    engine_root = Path(args.engine_root).resolve() if args.engine_root else _PROJECT_ROOT
    base["git_head"] = _git_head(engine_root)
    engine_file = str(Path(backtest.__file__).resolve())
    payload = build_probe_payload(engine, base, engine_file)
    payload["source_fingerprints"] = source_fingerprints(engine, engine_file)
    replay_version = getattr(backtest, "REPLAY_VERSION", None)
    if replay_version is not None:
        payload["replay_version"] = replay_version
    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C1 equity probe: capture / compare-ab.")
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Run one backtest, write the probe JSON.")
    cap.add_argument("--strategy", required=True)
    cap.add_argument("--pair", required=True)
    cap.add_argument("--exchange", required=True)
    cap.add_argument("--start-date", required=True)
    cap.add_argument("--end-date", required=True)
    cap.add_argument("--interval", type=int, required=True)
    cap.add_argument("--capital", type=float, default=1000.0)
    cap.add_argument("--fees", required=True)
    cap.add_argument("--pair-costs-file", default=None)
    cap.add_argument("--min-order-usdc", type=float, default=1.0)
    cap.add_argument("--engine-root", default=None, help="Checkout whose engines to run.")
    cap.add_argument("--out", type=Path, required=True, help=".json or .json.gz")

    cmp_ = sub.add_parser("compare-ab", help="Identity + partitioned metrics table.")
    cmp_.add_argument("old", type=Path)
    cmp_.add_argument("new", type=Path)
    cmp_.add_argument("--markdown", type=Path, default=None)
    cmp_.add_argument(
        "--strict",
        action="store_true",
        help="C2 master invariant: every key of OLD byte-identical in NEW (metrics identical "
        "and moving, all trade fields, balances, equity, liquidation, fees); only "
        f"{', '.join(STRICT_ALLOWED_META)} may differ and only "
        f"{', '.join(STRICT_ALLOWED_ADDITIONS)} may be added.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "capture":
        from dotenv import load_dotenv

        load_dotenv(_PROJECT_ROOT / ".env")
        payload = asyncio.run(run_capture(args))
        digest = write_capture(args.out, payload)
        m = payload["metrics"]
        print(
            f"captured {payload['engine']} {args.strategy} {args.pair} [{payload['git_head']}]: "
            f"{len(payload['trades_full'])} trades, {len(payload['equity_curve'])} equity points, "
            f"return {m['total_return_pct']:+.4f} %, net_pnl {m['net_pnl']:.6f} -> {args.out} "
            f"(sha256 {digest[:16]}…)",
            file=sys.stderr,
        )
        return 0
    if args.command == "compare-ab":
        old, new = load_capture(args.old), load_capture(args.new)
        violations = compare_identity(old, new)
        if args.strict:
            violations = violations + [f"strict: {item}" for item in compare_strict(old, new)]
        md = render_markdown(old, new, violations)
        if args.markdown is not None:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(md, encoding="utf-8")
        print(md)
        label = "STRICT IDENTITY" if args.strict else "IDENTITY"
        if violations:
            print(f"{len(violations)} {label.lower()} violation(s)", file=sys.stderr)
            return 1
        print(f"{label} OK", file=sys.stderr)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
