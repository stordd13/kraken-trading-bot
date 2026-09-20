"""Rejeu diagnostic grid — reconstructed full-notional buy-and-hold benchmark (prespec § E).

Section E.1 bans the existing benchmark numbers from every threshold: ``compute_benchmarks.py``
loads ``timestamp >= start AND timestamp < end`` where the engines load ``<= end`` (debt 15(c)),
anchors its metric window at ``candles[0].timestamp - interval`` (one day before the grid's
anchor), enters at the first daily **open**, and charges a market entry with **no exit** while the
grid pays a terminal liquidation. This script rebuilds the comparator under the engine's own
convention — bounds ``>= 2023-04-01T00:00Z`` and ``<= 2026-04-01T00:00Z`` on the end-stamped daily
series, anchor at ``start`` with 1000 USDC in cash, entry at the close stamped at the anchor, one
terminal liquidation stamped at ``end`` — and exports the whole daily NAV path, not scalars. The
figures of ``results/C1_benchmarks_v2.json`` are copied into ``historical_descriptors``: they are
descriptive, never a threshold, and ``compute_benchmarks.py`` is not modified.

The blend of § E.3 is NOT exported: ``NAV_λ(t) = (1-λ)*1000 + λ*NAV_bh(t)`` is closed-form, so the
downstream analysis rebuilds it from the full-notional path published here.

Both § E tests around the anchor are applied literally, and they do not look the same way:
constructibility (§ E.2) looks **forward** (a candle stamped at ``start``, else the first candle
stamped ``> start`` within 24 h), while the comparability test (§ E.4) looks **backward** (a candle
at ``start`` or in the 24 h before). Under the frozen load bounds no candle before ``start`` is
ever read, so a pair buildable only through the E.2 fallback is recorded ``buildable`` **and** not
comparable. Neither branch is arbitrated here.

A pair that is not buildable, or not comparable, is a **recorded result** (§ E.5 sends it to
``descriptif``), never a failure of this script: exit 1 is reserved for a self-check of the
instrument — a built NAV that does not live on the frozen 1097-point daily grid, or an anchor that
is not the frozen capital.

Read-only, DB en lecture seule.

Usage::

    poetry run python scripts/audit/rejeu_benchmark.py \\
        --output results/rejeu_grid_20260919/benchmark.json \\
        --markdown results/rejeu_grid_20260919/benchmark.md

Exit codes: 0 ok, 1 violation, 2 usage or input error.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import statistics
import sys
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

from backtest import PairCosts, load_pair_costs  # noqa: E402
import rejeu_common as rc  # noqa: E402

from krakenbot.backtest_metrics import EquityPoint, compute_metrics, daily_grid  # noqa: E402
from krakenbot.config.settings import ExchangeFees, Settings  # noqa: E402
from krakenbot.core.database import DatabaseManager  # noqa: E402
from krakenbot.models.market_data import OHLCData  # noqa: E402

DAILY_INTERVAL = 1440
FIVE_MIN_INTERVAL = 5
#: § E.2 — a candle stamped later than this after ``start`` makes the benchmark unbuildable,
#: and re-anchoring to a later date is forbidden (common dates, no exception).
ENTRY_WINDOW = timedelta(hours=24)

PRESPEC_RELPATH = "docs/rejeu_grid_prespec.md"
HISTORICAL_RELPATH = "results/C1_benchmarks_v2.json"
DEFAULT_OUTPUT = rc.PROJECT_ROOT / "results" / "rejeu_grid_20260919" / "benchmark.json"
DEFAULT_PAIR_COSTS = rc.PROJECT_ROOT / "config" / rc.PAIR_COSTS_BASENAME

#: Frozen key set of one pair block (schema of ``benchmark.json``).
PAIR_KEYS = (
    "buildable",
    "reason",
    "entry_price",
    "exit_price",
    "costs_charged",
    "nav",
    "returns",
    "metrics",
    "comparability",
    "historical_descriptors",
)
METRIC_KEYS = (
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown_pct_daily",
    "cagr_pct",
    "calmar_ratio",
    "n_daily_returns",
    "total_return_pct",
    "sigma_daily",
)
COMPARABILITY_KEYS = (
    "ff_days",
    "ff_ok",
    "candle_at_start",
    "candle_at_end",
    "n_daily_returns_ok",
    "all_finite",
    "min_return_ok",
    "midnight_crosscheck_mismatches",
    "midnight_crosscheck_checked",
    "comparable",
)


# ---------------------------------------------------------------------------
# Candles (pure) — the NAV construction never sees a DB row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candle:
    """One end-stamped close: the candle stamped ``t`` covers ``(t - interval, t]``."""

    timestamp: datetime
    close: Decimal


def _utc(stamp: datetime) -> datetime:
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def to_candles(rows: Iterable[Any]) -> list[Candle]:
    """``OHLCData`` rows (or any object with ``timestamp`` / ``close``) as sorted candles."""
    out = [Candle(_utc(r.timestamp), Decimal(str(r.close))) for r in rows]
    out.sort(key=lambda c: c.timestamp)
    return out


def interior_midnights(start: datetime, end: datetime) -> list[datetime]:
    """The UTC midnights strictly inside ``(start, end)`` — the daily grid minus both edges."""
    return daily_grid(start, end)[1:-1]


# ---------------------------------------------------------------------------
# § E.2 — construction of the full-notional NAV
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Build:
    """Outcome of the § E.2 construction. ``entry_price`` / ``exit_price`` are **executed**
    prices (the close moved by spread + slippage); the fee rates stay in ``costs_charged``."""

    buildable: bool
    reason: str | None
    entry_price: Decimal | None
    exit_price: Decimal | None
    qty: Decimal | None
    points: tuple[EquityPoint, ...]


def select_entry_candle(
    candles: Sequence[Candle], start: datetime
) -> tuple[Candle | None, str | None]:
    """§ E.2 constructibility: the candle stamped exactly at ``start`` (its close IS the price at
    the anchor, end-stamping), else the first candle stamped ``> start`` if it is within 24 h."""
    for candle in candles:
        if candle.timestamp == start:
            return candle, None
    after = [c for c in candles if c.timestamp > start]
    if not after:
        return None, "no daily candle stamped at or after start"
    first = after[0]
    late = first.timestamp - start
    if late <= ENTRY_WINDOW:
        return first, None
    days = late.total_seconds() / 86400.0
    return None, (
        f"first candle stamped {first.timestamp.isoformat()} is {days:.1f} days after start "
        f"(> 24 h); re-anchoring to a later date is forbidden (§ E.2)"
    )


def build_full_notional(
    candles: Sequence[Candle],
    *,
    start: datetime,
    end: datetime,
    spread: Decimal,
    slippage: Decimal,
    taker: Decimal,
    capital: Decimal = rc.CAPITAL,
) -> Build:
    """Anchor at ``start`` with ``capital`` in cash, enter at the anchor close, mark to market at
    every candle stamped ``> start``, and pay ONE terminal liquidation stamped at ``end``.

    The liquidation point is appended **after** the mark carrying the same stamp: ``resample_daily``
    sorts the points stably and lets the last point of an instant win, exactly as the grid engine's
    post-liquidation point does.
    """
    entry, reason = select_entry_candle(candles, start)
    if entry is None:
        return Build(False, reason, None, None, None, ())
    exec_in = entry.close * (Decimal("1") + spread + slippage)
    if exec_in <= 0:
        return Build(False, f"entry close {entry.close} is not strictly positive", None,
                     None, None, ())
    qty = capital * (Decimal("1") - taker) / exec_in
    marks = [c for c in candles if start < c.timestamp <= end]
    points = [EquityPoint(timestamp=c.timestamp, equity=qty * c.close) for c in marks]
    last = marks[-1] if marks else entry
    exec_out = last.close * (Decimal("1") - spread - slippage)
    points.append(EquityPoint(timestamp=end, equity=qty * exec_out * (Decimal("1") - taker)))
    return Build(True, None, exec_in, exec_out, qty, tuple(points))


def benchmark_metrics(
    points: Sequence[EquityPoint],
    *,
    start: datetime,
    end: datetime,
    capital: Decimal = rc.CAPITAL,
) -> tuple[list[float], list[float], dict[str, Any]]:
    """``(nav, returns, metrics)`` through the C1 module (``metrics_version`` 2).

    ``MetricsResult`` carries no ``total_return_pct``: it is derived here from ``daily.nav[-1]``.
    ``sigma_daily`` is the **sample** standard deviation of the daily returns.
    """
    result = compute_metrics(
        list(points), [], start=start, end=end, starting_balance=capital, flows=[]
    )
    nav = [float(v) for v in result.daily.nav]
    returns = result.daily.defined_returns
    metrics: dict[str, Any] = {
        "sharpe_ratio": result.sharpe_ratio,
        "sortino_ratio": result.sortino_ratio,
        "max_drawdown_pct_daily": result.max_drawdown_pct_daily,
        "cagr_pct": result.cagr_pct,
        "calmar_ratio": result.calmar_ratio,
        "n_daily_returns": result.n_daily_returns,
        "total_return_pct": float((result.daily.nav[-1] - capital) / capital * Decimal("100")),
        "sigma_daily": statistics.stdev(returns) if len(returns) > 1 else None,
    }
    return nav, returns, metrics


# ---------------------------------------------------------------------------
# § E.4 — comparability tests (blocking, all recorded)
# ---------------------------------------------------------------------------


def forward_filled_days(candles: Sequence[Candle], grid: Sequence[datetime]) -> int:
    """Grid instants ``t_k`` (k >= 1) with NO candle stamped in ``(t_{k-1}, t_k]``.

    ``daily_grid(start, end)`` is a pure function of the two instants, so asserting that the
    benchmark's grid equals the config's is vacuous (§ E.4): this counts the forward-filled marks
    instead — the only way the two NAV paths can stop describing the same days.
    """
    stamps = sorted(c.timestamp for c in candles)
    index = 0
    forward_filled = 0
    for k in range(1, len(grid)):
        while index < len(stamps) and stamps[index] <= grid[k - 1]:
            index += 1
        found = False
        while index < len(stamps) and stamps[index] <= grid[k]:
            found = True
            index += 1
        if not found:
            forward_filled += 1
    return forward_filled


def midnight_crosscheck(
    daily_closes: Mapping[datetime, Decimal],
    five_min_closes: Mapping[datetime, Decimal],
    midnights: Sequence[datetime],
) -> tuple[int, int, list[datetime]]:
    """Provenance cross-check (§ E.4, reported and NOT blocking): under end-stamping (B4.1) the
    5 m close stamped ``J 00:00`` and the 1 d close stamped ``J 00:00`` close at the same instant.

    Returns ``(mismatches, checked, stamps)``; a midnight missing on either side is not checked.
    """
    mismatches: list[datetime] = []
    checked = 0
    for stamp in midnights:
        one_day = daily_closes.get(stamp)
        five_min = five_min_closes.get(stamp)
        if one_day is None or five_min is None:
            continue
        checked += 1
        if Decimal(str(one_day)) != Decimal(str(five_min)):
            mismatches.append(stamp)
    return len(mismatches), checked, mismatches


def comparability_block(
    candles: Sequence[Candle],
    *,
    start: datetime,
    end: datetime,
    returns: Sequence[float] | None,
    mismatches: int = 0,
    checked: int = 0,
) -> dict[str, Any]:
    """The § E.4 tests, all recorded; ``comparable`` is the conjunction of the blocking ones.

    ``returns is None`` (nothing was built) makes the three return-side tests False: a test cannot
    be satisfied by a series that does not exist, and § E.5 sends that pair to ``descriptif``.
    """
    grid = daily_grid(start, end)
    ff_days = forward_filled_days(candles, grid)
    candle_at_start = any(start - ENTRY_WINDOW <= c.timestamp <= start for c in candles)
    candle_at_end = any(c.timestamp == end for c in candles)
    if returns is None:
        n_ok = finite_ok = min_ok = False
    else:
        n_ok = len(returns) == rc.SEGMENT_RETURNS["all"]
        finite_ok = all(math.isfinite(r) for r in returns)
        min_ok = bool(returns) and min(returns) > rc.MIN_RETURN_DOMAIN
    ff_ok = ff_days <= rc.FF_DAYS_MAX
    return {
        "ff_days": ff_days,
        "ff_ok": ff_ok,
        "candle_at_start": candle_at_start,
        "candle_at_end": candle_at_end,
        "n_daily_returns_ok": n_ok,
        "all_finite": finite_ok,
        "min_return_ok": min_ok,
        "midnight_crosscheck_mismatches": mismatches,
        "midnight_crosscheck_checked": checked,
        "comparable": bool(ff_ok and candle_at_start and candle_at_end and n_ok
                           and finite_ok and min_ok),
    }


def failing_tests(comparability: Mapping[str, Any]) -> list[str]:
    """Human-readable list of the blocking § E.4 tests that failed (the crosscheck is excluded)."""
    failures: list[str] = []
    if not comparability["ff_ok"]:
        failures.append(f"ff_days {comparability['ff_days']} > {rc.FF_DAYS_MAX}")
    if not comparability["candle_at_start"]:
        failures.append("no candle stamped at start (nor within the 24 h before)")
    if not comparability["candle_at_end"]:
        failures.append("no candle stamped at end")
    if not comparability["n_daily_returns_ok"]:
        failures.append(f"n_daily_returns != {rc.SEGMENT_RETURNS['all']}")
    if not comparability["all_finite"]:
        failures.append("a daily return is not finite")
    if not comparability["min_return_ok"]:
        failures.append(f"a daily return is <= {rc.MIN_RETURN_DOMAIN} (log1p domain)")
    return failures


# ---------------------------------------------------------------------------
# Pair block
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairReport:
    """The frozen pair block plus the mismatching midnights (listed, never a threshold)."""

    payload: dict[str, Any]
    mismatches: tuple[datetime, ...]


def historical_descriptors(path: Path, pair: str) -> dict[str, Any] | None:
    """BTC / SOL figures of ``results/C1_benchmarks_v2.json`` — descriptive, never a threshold."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = rc.read_json(path)
    except (OSError, ValueError):
        return None
    entry = ((data or {}).get("buy_and_hold") or {}).get(pair)
    if not isinstance(entry, dict):
        return None
    return {
        "source": _relpath(path),
        "sharpe_ratio": entry.get("sharpe_ratio"),
        "max_drawdown_pct_daily": entry.get("max_drawdown_pct_daily"),
        "total_return_pct": entry.get("total_return_pct"),
        "n_daily_returns": entry.get("n_daily_returns"),
    }


def build_pair_report(
    candles: Sequence[Candle],
    *,
    start: datetime,
    end: datetime,
    spread: Decimal,
    slippage: Decimal,
    taker: Decimal,
    five_min_closes: Mapping[datetime, Decimal] | None = None,
    historical: dict[str, Any] | None = None,
    capital: Decimal = rc.CAPITAL,
) -> PairReport:
    """Everything § E produces for one pair, from candles only (no DB, no clock)."""
    build = build_full_notional(
        candles, start=start, end=end, spread=spread, slippage=slippage, taker=taker,
        capital=capital,
    )
    nav: list[float] | None = None
    returns: list[float] | None = None
    metrics: dict[str, Any] | None = None
    if build.buildable:
        nav, returns, metrics = benchmark_metrics(
            build.points, start=start, end=end, capital=capital
        )
    mismatches, checked, stamps = midnight_crosscheck(
        {c.timestamp: c.close for c in candles},
        five_min_closes or {},
        interior_midnights(start, end),
    )
    comparability = comparability_block(
        candles, start=start, end=end, returns=returns, mismatches=mismatches, checked=checked
    )
    if not build.buildable:
        reason = build.reason
    elif not comparability["comparable"]:
        reason = "not comparable: " + "; ".join(failing_tests(comparability))
    else:
        reason = None
    payload = {
        "buildable": build.buildable,
        "reason": reason,
        "entry_price": None if build.entry_price is None else float(build.entry_price),
        "exit_price": None if build.exit_price is None else float(build.exit_price),
        "costs_charged": {
            "taker": str(taker),
            "spread": str(spread),
            "slippage": str(slippage),
        },
        "nav": nav,
        "returns": returns,
        "metrics": metrics,
        "comparability": comparability,
        "historical_descriptors": historical,
    }
    return PairReport(payload, tuple(stamps))


# ---------------------------------------------------------------------------
# Artefact
# ---------------------------------------------------------------------------


def _relpath(path: Path) -> str:
    path = Path(path)
    try:
        return path.resolve().relative_to(rc.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def prespec_descriptor() -> dict[str, str]:
    """Path and sha256 of the frozen pre-specification (absent file -> empty digest)."""
    path = rc.PROJECT_ROOT / PRESPEC_RELPATH
    digest = ""
    if path.exists():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": PRESPEC_RELPATH, "sha256": digest}


def build_payload(
    reports: Mapping[str, PairReport],
    *,
    now: datetime,
    pair_costs_file: Path,
    pair_costs: Mapping[str, PairCosts],
    start: datetime = rc.WINDOW_START,
    end: datetime = rc.WINDOW_END,
) -> dict[str, Any]:
    """The frozen ``benchmark.json`` object (§ L step 2), deterministic for a given ``now``."""
    return {
        "generated_at": now.isoformat(),
        "base_sha": rc.BASE_SHA,
        "prespec": prespec_descriptor(),
        "exchange": rc.EXCHANGE,
        "fees_model": rc.FEES_MODEL,
        "pair_costs_file": _relpath(pair_costs_file),
        "pair_costs": {
            pair: {
                "spread": str(pair_costs[pair].spread),
                "slippage": str(pair_costs[pair].slippage),
            }
            for pair in rc.PAIRS
            if pair in pair_costs
        },
        "capital": str(rc.CAPITAL),
        "rf": 0,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "pairs": {pair: reports[pair].payload for pair in rc.PAIRS if pair in reports},
    }


def structural_violations(payload: Mapping[str, Any]) -> list[str]:
    """Self-checks of the instrument (exit 1): a built NAV must live on the frozen daily grid.

    A non-buildable or non-comparable pair is a **recorded result** (§ E.5), never a violation.
    """
    violations: list[str] = []
    expected = rc.SEGMENT_POINTS["all"]
    for pair, block in payload["pairs"].items():
        if not block["buildable"]:
            continue
        nav = block["nav"] or []
        if len(nav) != expected:
            violations.append(f"{pair}: nav has {len(nav)} points, the frozen grid has {expected}")
        if nav and nav[0] != float(rc.CAPITAL):
            violations.append(f"{pair}: nav[0] == {nav[0]!r}, the anchor is {float(rc.CAPITAL)}")
    return violations


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    """One-screen rendering for stdout."""
    lines = [
        f"benchmark {payload['exchange']} / fees {payload['fees_model']} / "
        f"window {payload['window']['start']} -> {payload['window']['end']}",
        f"pair costs: {payload['pair_costs_file']} — capital {payload['capital']} USDC, rf 0",
    ]
    for pair, block in payload["pairs"].items():
        comparability = block["comparability"]
        head = (
            f"{pair}: buildable={block['buildable']} comparable={comparability['comparable']} "
            f"ff_days={comparability['ff_days']} "
            f"crosscheck={comparability['midnight_crosscheck_mismatches']}"
            f"/{comparability['midnight_crosscheck_checked']}"
        )
        lines.append(head)
        metrics = block["metrics"]
        if metrics is not None:
            lines.append(
                f"    entry {block['entry_price']} exit {block['exit_price']} | "
                f"return {metrics['total_return_pct']:+.2f}% "
                f"MDD_daily {metrics['max_drawdown_pct_daily']:.2f}% "
                f"sigma {metrics['sigma_daily']:.6f} n {metrics['n_daily_returns']}"
            )
        if block["reason"]:
            lines.append(f"    reason: {block['reason']}")
    return lines


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _delta(new: Any, old: Any, digits: int = 4) -> str:
    if new is None or old is None:
        return "—"
    return f"{float(new) - float(old):+.{digits}f}"


def render_markdown(
    payload: Mapping[str, Any], reports: Mapping[str, PairReport] | None = None
) -> str:
    """Tables of § E: construction, metrics, comparability, historical descriptors + delta."""
    out = [
        "# Rejeu diagnostic grid — benchmark reconstruit (§ E)",
        "",
        f"généré {payload['generated_at']} · base_sha {payload['base_sha']} · "
        f"prespec {payload['prespec']['sha256'][:16]}",
        "",
        f"Fenêtre {payload['window']['start']} → {payload['window']['end']}, "
        f"données {payload['exchange']} (interval {DAILY_INTERVAL}), modèle de fees "
        f"{payload['fees_model']}, capital {payload['capital']} USDC, rf 0.",
        "",
        "Bornes `>= start` et `<= end` (convention des moteurs, répare la dette 15(c)) ; entrée au "
        "close stampé à l'ancre, une liquidation terminale stampée à `end` comme le grid. "
        "`entry_price` / `exit_price` sont les prix **exécutés** (close ± spread + slippage) ; "
        "le taker est facturé sur le notionnel, séparément.",
        "",
        "| paire | constructible | comparable | entrée | sortie | rendement % | MDD_daily % | "
        "CAGR %/an | Sharpe | Sortino | Calmar | sigma_daily | n |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for pair, block in payload["pairs"].items():
        metrics = block["metrics"] or {}
        out.append(
            f"| {pair} | {block['buildable']} | {block['comparability']['comparable']} | "
            f"{_fmt(block['entry_price'], 6)} | {_fmt(block['exit_price'], 6)} | "
            f"{_fmt(metrics.get('total_return_pct'), 2)} | "
            f"{_fmt(metrics.get('max_drawdown_pct_daily'), 2)} | "
            f"{_fmt(metrics.get('cagr_pct'))} | {_fmt(metrics.get('sharpe_ratio'))} | "
            f"{_fmt(metrics.get('sortino_ratio'))} | {_fmt(metrics.get('calmar_ratio'))} | "
            f"{_fmt(metrics.get('sigma_daily'), 6)} | {_fmt(metrics.get('n_daily_returns'))} |"
        )
    out += [
        "",
        "## Comparabilité (§ E.4)",
        "",
        "| paire | ff_days | ff_ok | bougie à start | bougie à end | n_daily_returns | "
        "tous finis | min > -0.5 | crosscheck écarts / vérifiés | comparable |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for pair, block in payload["pairs"].items():
        comparability = block["comparability"]
        out.append(
            f"| {pair} | {comparability['ff_days']} | {comparability['ff_ok']} | "
            f"{comparability['candle_at_start']} | {comparability['candle_at_end']} | "
            f"{comparability['n_daily_returns_ok']} | {comparability['all_finite']} | "
            f"{comparability['min_return_ok']} | "
            f"{comparability['midnight_crosscheck_mismatches']}"
            f" / {comparability['midnight_crosscheck_checked']} | "
            f"{comparability['comparable']} |"
        )
    out += [
        "",
        "Le recoupement de minuit (close 5 m vs close 1 d, end-stamping B4.1) est **rapporté, non "
        "bloquant** : la série 1 d fait foi pour le benchmark.",
        "",
        "## Descripteurs historiques (§ E.1) — descriptifs, jamais un seuil",
        "",
        "| paire | source | Sharpe hist. | Δ Sharpe | MDD_daily hist. % | Δ MDD | "
        "rendement hist. % | Δ rendement | n hist. |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for pair, block in payload["pairs"].items():
        historical = block["historical_descriptors"]
        metrics = block["metrics"] or {}
        if historical is None:
            out.append(f"| {pair} | — | — | — | — | — | — | — | — |")
            continue
        mdd_hist = historical["max_drawdown_pct_daily"]
        out.append(
            f"| {pair} | {historical['source']} | {_fmt(historical['sharpe_ratio'])} | "
            f"{_delta(metrics.get('sharpe_ratio'), historical['sharpe_ratio'])} | "
            f"{_fmt(mdd_hist, 2)} | "
            f"{_delta(metrics.get('max_drawdown_pct_daily'), mdd_hist, 2)} | "
            f"{_fmt(historical['total_return_pct'], 2)} | "
            f"{_delta(metrics.get('total_return_pct'), historical['total_return_pct'], 2)} | "
            f"{_fmt(historical['n_daily_returns'])} |"
        )
    for pair, block in payload["pairs"].items():
        if block["reason"]:
            out += ["", f"**{pair}** — {block['reason']}"]
    stamps = [
        (pair, report.mismatches) for pair, report in (reports or {}).items() if report.mismatches
    ]
    if stamps:
        out += ["", "## Écarts du recoupement de minuit", ""]
        for pair, mismatched in stamps:
            out.append(f"- {pair} : " + ", ".join(s.isoformat() for s in mismatched))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# DB (read-only)
# ---------------------------------------------------------------------------


async def load_daily_candles(
    db_manager: DatabaseManager, pair: str, *, start: datetime, end: datetime
) -> list[Candle]:
    """Daily candles under the ENGINE bound convention: ``>= start`` and ``<= end`` (§ E.2).

    ``>= start`` (not ``> start``) keeps the candle stamped at the anchor, whose close IS the price
    at ``start``; ``<= end`` is what repairs debt 15(c) on this side of the rejeu.
    """
    async with db_manager.read_session() as session:
        stmt = (
            select(OHLCData)
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == DAILY_INTERVAL)
            .where(OHLCData.exchange == rc.EXCHANGE)
            .where(OHLCData.timestamp >= start)
            .where(OHLCData.timestamp <= end)
            .order_by(OHLCData.timestamp.asc())
        )
        rows = list((await session.execute(stmt)).scalars().all())
    return to_candles(rows)


async def load_closes_at(
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    stamps: Sequence[datetime],
    *,
    chunk: int = 500,
) -> dict[datetime, Decimal]:
    """Closes of ``interval`` candles stamped exactly on the given instants (chunked ``IN``)."""
    closes: dict[datetime, Decimal] = {}
    async with db_manager.read_session() as session:
        for offset in range(0, len(stamps), chunk):
            window = list(stamps[offset : offset + chunk])
            stmt = (
                select(OHLCData.timestamp, OHLCData.close)
                .where(OHLCData.pair == pair)
                .where(OHLCData.interval == interval)
                .where(OHLCData.exchange == rc.EXCHANGE)
                .where(OHLCData.timestamp.in_(window))
            )
            for stamp, close in (await session.execute(stmt)).all():
                closes[_utc(stamp)] = Decimal(str(close))
    return closes


async def collect_reports(
    pair_costs: Mapping[str, PairCosts],
    fees: ExchangeFees,
    historical_path: Path,
    *,
    start: datetime = rc.WINDOW_START,
    end: datetime = rc.WINDOW_END,
) -> dict[str, PairReport]:
    """One read-only pass over the DB: daily series + the 5 m closes of every interior midnight."""
    settings = Settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    reports: dict[str, PairReport] = {}
    try:
        midnights = interior_midnights(start, end)
        for pair in rc.PAIRS:
            candles = await load_daily_candles(db_manager, pair, start=start, end=end)
            five_min = await load_closes_at(db_manager, pair, FIVE_MIN_INTERVAL, midnights)
            costs = pair_costs[pair]
            reports[pair] = build_pair_report(
                candles,
                start=start,
                end=end,
                spread=costs.spread,
                slippage=costs.slippage,
                taker=fees.taker,
                five_min_closes=five_min,
                historical=historical_descriptors(historical_path, pair),
            )
    finally:
        await db_manager.close_db()
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="benchmark.json")
    parser.add_argument("--markdown", type=Path, default=None, help="optional table rendering")
    parser.add_argument(
        "--pair-costs-file",
        type=Path,
        default=DEFAULT_PAIR_COSTS,
        help=f"per-pair spread/slippage of the campaign (default: config/{rc.PAIR_COSTS_BASENAME})",
    )
    parser.add_argument(
        "--historical",
        type=Path,
        default=rc.PROJECT_ROOT / HISTORICAL_RELPATH,
        help="C1 benchmarks read as descriptors only (never a threshold)",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="ISO UTC stamp written as generated_at (default: now) — injected to stay testable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.now is None:
        now = datetime.now(UTC)
    else:
        try:
            now = _utc(datetime.fromisoformat(args.now))
        except ValueError as exc:
            print(f"--now: {exc}", file=sys.stderr)
            return 2
    load_dotenv(_ROOT / ".env")
    try:
        pair_costs = load_pair_costs(args.pair_costs_file)
    except (OSError, ValueError) as exc:
        print(f"--pair-costs-file: {exc}", file=sys.stderr)
        return 2
    missing = [pair for pair in rc.PAIRS if pair not in pair_costs]
    if missing:
        print(f"--pair-costs-file: no costs for {', '.join(missing)}", file=sys.stderr)
        return 2
    fees = ExchangeFees.from_name(rc.FEES_MODEL)
    try:
        reports = asyncio.run(collect_reports(pair_costs, fees, args.historical))
    except Exception as exc:  # DB unreachable / query failure: an input error, not a violation
        print(f"database: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    payload = build_payload(
        reports, now=now, pair_costs_file=args.pair_costs_file, pair_costs=pair_costs
    )
    digest = rc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    for pair, report in reports.items():
        if report.mismatches:
            shown = ", ".join(s.isoformat() for s in report.mismatches[:20])
            print(f"{pair}: midnight crosscheck mismatches at {shown}"
                  + (" ..." if len(report.mismatches) > 20 else ""))
    print(f"written {args.output} sha256 {digest}")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(payload, reports), encoding="utf-8")
        print(f"written {args.markdown}")
    violations = structural_violations(payload)
    for violation in violations:
        print(f"VIOLATION {violation}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
