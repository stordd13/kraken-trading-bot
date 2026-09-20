"""Rejeu diagnostic grid — campaign validity (pre-spec section I-A).

The fifteen assertions of section I-A, **in the frozen order**, over the campaign artifact
``results/rejeu_grid_20260919/P7_phase1_grid.json``. The order is part of the specification:
``b4_flags.collect_flags`` silently skips any entry carrying ``"error"`` and ``flag_segment``
returns ``[]`` on a falsy ``liquidation`` block, so "b4_flags is mute" is a FALSE GREEN until
I-A.1 to I-A.12 have passed. Assertion 13 therefore comes last, and it is both the canonical
flag rule and an independent re-application of ``flag_segment`` over the 96 x 3 (entry, segment)
pairs.

A single failed assertion makes the WHOLE run unexploitable (section G.2, ``R0_INVALID_RUN``):
the assertions that follow it are recorded as not evaluated — never as green — and the script
exits 2. Nothing here reads an analysis artifact (the dependency loop of section I is cut).

Pure, read-only.

Usage::

    poetry run python scripts/audit/rejeu_validate_campaign.py \\
        results/rejeu_grid_20260919/P7_phase1_grid.json \\
        --output results/rejeu_grid_20260919/validation_campaign.json \\
        --markdown results/rejeu_grid_20260919/validation_campaign.md

Exit codes: 0 ok, 1 violation, 2 usage or input error.
Section I-A grades the run as a whole: a failed assertion is always exit 2, never 1.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import fnmatch
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import b4_flags  # noqa: E402
from backtest import load_pair_costs  # noqa: E402
import p7_grids  # noqa: E402
import rejeu_common as rc  # noqa: E402
import run_p7_grid_search as p7  # noqa: E402

from krakenbot.backtest_metrics import (  # noqa: E402
    METRICS_VERSION,
    MetricsVersionError,
    cagr_pct,
    max_drawdown_pct,
    require_metrics_version,
    sharpe_ratio,
    sortino_ratio,
)
from krakenbot.replay_contract import (  # noqa: E402
    REPLAY_VERSION,
    ReplayVersionError,
    require_replay_version,
)

# ---------------------------------------------------------------------------
# Frozen shapes (pre-spec section I-A, "Forme réelle d'une entrée de campagne")
# ---------------------------------------------------------------------------

DEFAULT_DIR = rc.PROJECT_ROOT / "results" / "rejeu_grid_20260919"
DEFAULT_ARTIFACT = DEFAULT_DIR / "P7_phase1_grid.json"
DEFAULT_OUTPUT = DEFAULT_DIR / "validation_campaign.json"
PRESPEC_RELPATH = "docs/rejeu_grid_prespec.md"

#: I-A.4 — the 22 top-level keys of a phase-1 grid entry.
TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "strategy", "pair", "exchange", "fees", "metrics_version", "replay_version",
        "pair_costs_file", "pair_costs", "min_order_usdc", "effective_params", "liquidation",
        "equity_daily", "rejections", "warmup", "dca_counters", "params", "phase", "window_idx",
        "period", "train", "test", "all",
    }
)

#: I-A.10 — the 24 keys of the ``METRICS_VERSION`` 2 contract (no ``cagr_pct``).
METRIC_KEYS: frozenset[str] = frozenset(
    {
        "metrics_version", "total_trades", "winning_trades", "losing_trades", "win_rate",
        "total_return_pct", "sharpe_ratio", "sortino_ratio", "max_drawdown_pct_daily",
        "max_drawdown_pct_engine", "profit_factor", "calmar_ratio", "net_pnl", "total_fees",
        "total_pnl", "unrealized_pnl", "starting_balance", "ending_balance", "duration_days",
        "average_holding_time_minutes", "gross_profit_net", "gross_loss_net",
        "pf_excluded_trades", "n_daily_returns",
    }
)

#: I-A.8 — the 18 keys of one ``liquidation[segment]`` block.
LIQUIDATION_KEYS: frozenset[str] = frozenset(
    {
        "buy_fees", "sell_fees", "net_pnl_lot_basis", "residual_net_proceeds",
        "avg_holding_minutes", "positions", "trades", "residual_trade_btc",
        "dust_written_off_btc", "inventory_divergence_btc", "pnl", "fees", "gross_usdc",
        "timestamp", "reference_price", "price", "spread_pct", "slippage_pct",
    }
)

WARMUP_TIMEFRAMES: tuple[str, ...] = ("4h", "1d", "1w")
WARMUP_FIELDS: frozenset[str] = frozenset(
    {
        "interval", "required", "loaded", "extended_by", "stale_by_candles",
        "largest_gap_candles", "sufficient", "first", "last",
    }
)
REJECTION_KEYS: frozenset[str] = frozenset({"unit", "by_cause", "events"})
REJECTION_CAUSES: frozenset[str] = frozenset(
    {
        "ambiguous_sell_fill", "below_min_order", "incoherent_sell_fill", "insufficient_cash",
        "insufficient_inventory", "unmatched_position_id", "unmatched_sell_fills",
    }
)

#: I-A.5 — null on a flat segment (``positions == 0``), asserted otherwise.
LIQUIDATION_NULL_WHEN_FLAT: tuple[str, ...] = (
    "timestamp", "price", "reference_price", "spread_pct", "slippage_pct",
)
#: I-A.5 — ``liquidation`` cost field -> ``pair_costs`` field.
COST_FIELDS: tuple[tuple[str, str], ...] = (("spread_pct", "spread"), ("slippage_pct", "slippage"))

#: I-A.7 — class defaults in force (debt 13 not fixed), compared via ``Decimal(str(value))``.
EFFECTIVE_DECIMAL_EXPECTED: dict[str, Decimal] = {
    name: rc.dec(value) for name, value in rc.CLASS_DEFAULTS.items()
}
#: I-A.7 — ``pause_1w_strong_bear`` implied by ``bear_protection_mode`` (verified in the class).
PAUSE_1W_BY_MODE: dict[str, bool] = {"none": False, "1w_only": True, "1d_only": False}

#: I-A.15 — frozen field sets of the two artifacts produced before the campaign.
DATA_COVERAGE_KEYS: frozenset[str] = frozenset(
    {"generated_at", "base_sha", "prespec", "exchange", "window", "pairs"}
)
BENCHMARK_KEYS: frozenset[str] = frozenset(
    {
        "generated_at", "base_sha", "prespec", "exchange", "fees_model", "pair_costs_file",
        "pair_costs", "capital", "rf", "window", "pairs",
    }
)

SELF_TEST_TOL = 1e-6  # I-A.10 — |recomputed - exported|
FLAT_NET_PNL_TOL = Decimal("1e-6")  # I-A.11 — |net_pnl - (ending - starting)| on a flat segment
UNREALIZED_TOL = Decimal("1e-9")  # I-A.11 — |unrealized_pnl - liquidation.pnl|
DETAIL_LIMIT = 6  # violations quoted in a row's detail before "+N more"

_MISSING = object()


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Any) -> datetime | None:
    """ISO-8601 string -> aware datetime, or None when unreadable."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "<absent>"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _detail(problems: list[str], notes: list[str], limit: int = DETAIL_LIMIT) -> str:
    """One deterministic line per assertion row: the notes, then the violations."""
    parts: list[str] = []
    if notes:
        parts.append("; ".join(notes))
    if problems:
        shown = " | ".join(problems[:limit])
        extra = f" (+{len(problems) - limit} more)" if len(problems) > limit else ""
        parts.append(f"{len(problems)} violation(s): {shown}{extra}")
    return " — ".join(parts) if parts else "ok"


def _compare_optional(exported: Any, recomputed: Any, tol: float = SELF_TEST_TOL) -> str | None:
    """None when the two agree (both None, or both defined within ``tol``), else the reason."""
    if exported is None and recomputed is None:
        return None
    if exported is None or recomputed is None:
        return f"exported {exported!r} vs recomputed {recomputed!r} (None mismatch)"
    try:
        delta = abs(float(exported) - float(recomputed))
    except (TypeError, ValueError):
        return f"exported {exported!r} vs recomputed {recomputed!r} (not numeric)"
    if math.isnan(delta) or delta > tol:
        return f"exported {exported!r} vs recomputed {recomputed!r} (delta {delta:.3e} > {tol:.0e})"
    return None


def _parse_name_status(text: str) -> list[tuple[str, str]]:
    """``git diff --name-status`` output -> ``[(status, path)]`` (renames keep the new path)."""
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p for p in line.split("\t") if p.strip()]
        if len(parts) < 2:
            rows.append(("?", line.strip()))
        else:
            rows.append((parts[0].strip(), parts[-1].strip()))
    return rows


def expected_params_by_key() -> dict[str, dict[str, Any]]:
    """The 96 expected keys, REBUILT: ``expand_grid(GRID_ATR_GRID)`` x ``make_key`` (I-A.2)."""
    out: dict[str, dict[str, Any]] = {}
    for pair in rc.PAIRS:
        for params in p7_grids.expand_grid(p7_grids.GRID_ATR_GRID):
            out[p7.make_key(rc.STRATEGY, pair, params, "1")] = params
    return out


def recomputed_split() -> datetime:
    """``P7_START + (P7_END - P7_START) * TRAIN_RATIO`` — never hard-coded (I-A.6)."""
    return p7.P7_START + (p7.P7_END - p7.P7_START) * p7.TRAIN_RATIO


# ---------------------------------------------------------------------------
# Instrument self-test (I-A.10): the exported curve against the exported metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelfTest:
    """Metrics recomputed from ``equity_daily[seg].values`` converted to ``Decimal``."""

    n_defined: int
    sharpe: float | None
    sortino: float | None
    mdd_daily: float
    cagr: float | None


def self_test_segment(values: list[Any], start_iso: Any, end_iso: Any) -> SelfTest | None:
    """Recompute the C1 instrument from the exported NAV; None when the curve is unusable.

    The daily returns and the performance index are rebuilt in ``Decimal`` exactly as
    ``backtest_metrics.resample_daily`` does (no external flow on these runs), then the ratios
    are taken from ``backtest_metrics`` itself — the engine's own routines, not a restatement.
    ``cagr_pct`` is recomputed here and compared to NO exported field (it is not exported).
    """
    navs = [rc.dec(v) for v in values]
    if len(navs) < 2 or any(v is None or not v.is_finite() for v in navs):
        return None
    returns: list[Decimal] = []
    index: list[Decimal] = [Decimal(1)]
    for prev, cur in zip(navs[:-1], navs[1:], strict=True):
        if prev is not None and prev > 0:
            step = (cur - prev) / prev
            returns.append(step)
            index.append(index[-1] * (Decimal(1) + step))
        else:
            index.append(index[-1])
    defined = [float(r) for r in returns]
    start, end = _parse_dt(start_iso), _parse_dt(end_iso)
    days = (end - start).total_seconds() / 86400 if start and end else None
    cagr = cagr_pct(index[0], index[-1], days) if days is not None else None
    return SelfTest(
        n_defined=len(defined),
        sharpe=sharpe_ratio(defined),
        sortino=sortino_ratio(defined),
        mdd_daily=max_drawdown_pct(index),
        cagr=cagr,
    )


# ---------------------------------------------------------------------------
# Injected environment and context — the only git / filesystem calls live here
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Environment:
    """Everything I-A.14 needs about the machine and the tree. Injectable (tests substitute it)."""

    git_head: str
    base_sha: str
    python: str
    numpy: str
    host: str
    poetry_lock_sha256: str
    engine_file_sha256: dict[str, str]
    code_diff: str  # git diff --stat BASE..HEAD -- <CONTROL_DIFF_PATHS>
    tests_diff: str  # git diff --name-status BASE..HEAD -- tests
    porcelain: str  # git status --porcelain -- <CONTROL_DIFF_PATHS> tests

    def to_dict(self) -> dict[str, Any]:
        return {
            "git_head": self.git_head,
            "base_sha": self.base_sha,
            "python": self.python,
            "numpy": self.numpy,
            "host": self.host,
            "poetry_lock_sha256": self.poetry_lock_sha256,
            "engine_file_sha256": dict(sorted(self.engine_file_sha256.items())),
        }


@dataclass(frozen=True)
class SideArtifact:
    """``data_coverage.json`` / ``benchmark.json`` as read from disk (I-A.15)."""

    path: Path
    exists: bool
    data: dict[str, Any] | None
    mtime: float | None


@dataclass(frozen=True)
class Context:
    """Everything the fifteen assertions read. Built once, then the assertions are pure."""

    artifact_path: Path
    artifact_label: str
    artifact_exists: bool
    artifact_sha256: str
    artifact_mtime: float | None
    raw_text: str
    parsed_ok: bool
    results: dict[str, Any]
    entries: dict[str, Any]
    sibling_names: tuple[str, ...]
    expected: dict[str, dict[str, Any]]
    split: datetime
    prespec: dict[str, str]
    env: Environment
    data_coverage: SideArtifact
    benchmark: SideArtifact
    pair_costs_ref: dict[str, dict[str, Decimal]] | None
    pair_costs_path: Path | None
    pair_costs_error: str | None


def _git(root: Path, *args: str) -> str:
    """One git call; a failure returns a non-empty sentinel, so integrity is never *assumed*."""
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv, no shell
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"<git unavailable: {type(exc).__name__}: {exc}>"
    if done.returncode != 0:
        return f"<git failed ({done.returncode}): {done.stderr.strip()}>"
    return done.stdout


def collect_environment(root: Path = rc.PROJECT_ROOT, *, base_sha: str = rc.BASE_SHA) -> Environment:
    """Thin wrapper over git / hashlib / platform — the substitution point of the tests."""
    engine_files = tuple(p for p in rc.CONTROL_DIFF_PATHS if (root / p).is_file())
    try:
        import numpy

        numpy_version = str(numpy.__version__)
    except Exception as exc:  # numpy is a hard dependency; its absence is reportable, not fatal
        numpy_version = f"<absent: {type(exc).__name__}>"
    return Environment(
        git_head=_git(root, "rev-parse", "HEAD").strip(),
        base_sha=base_sha,
        python=platform.python_version(),
        numpy=numpy_version,
        host=platform.node(),
        poetry_lock_sha256=_sha256_file(root / "poetry.lock"),
        engine_file_sha256={p: _sha256_file(root / p) for p in engine_files},
        code_diff=_git(root, "diff", "--stat", f"{base_sha}..HEAD", "--", *rc.CONTROL_DIFF_PATHS),
        tests_diff=_git(root, "diff", "--name-status", f"{base_sha}..HEAD", "--", "tests"),
        porcelain=_git(root, "status", "--porcelain", "--", *rc.CONTROL_DIFF_PATHS, "tests"),
    )


def _read_side(path: Path) -> SideArtifact:
    path = Path(path)
    if not path.is_file():
        return SideArtifact(path, False, None, None)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = None
    return SideArtifact(
        path, True, data if isinstance(data, dict) else None, path.stat().st_mtime
    )


def _label(path: Path, root: Path) -> str:
    """Repo-relative label when possible: the artifact must not depend on the caller's cwd."""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def build_context(
    artifact: Path,
    *,
    env: Environment,
    data_coverage: Path | None = None,
    benchmark: Path | None = None,
    root: Path = rc.PROJECT_ROOT,
) -> Context:
    """Read the campaign artifact and its two pre-campaign siblings; resolve the costs file."""
    artifact = Path(artifact)
    exists = artifact.is_file()
    raw = artifact.read_text(encoding="utf-8") if exists else ""
    sha = _sha256_file(artifact) if exists else ""
    mtime = artifact.stat().st_mtime if exists else None

    parsed_ok = False
    results: dict[str, Any] = {}
    if exists:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            parsed_ok, results = True, loaded
    entries = {k: v for k, v in results.items() if isinstance(v, dict)}

    siblings: tuple[str, ...] = ()
    if artifact.parent.is_dir():
        siblings = tuple(sorted(p.name for p in artifact.parent.iterdir() if p.is_file()))

    named = sorted({str(e["pair_costs_file"]) for e in entries.values() if e.get("pair_costs_file")})
    pair_costs_ref: dict[str, dict[str, Decimal]] | None = None
    pair_costs_path: Path | None = None
    pair_costs_error: str | None = None
    if len(named) == 1:
        candidate = Path(named[0])
        pair_costs_path = candidate if candidate.is_absolute() else root / candidate
        try:
            pair_costs_ref = {
                pair: {"spread": costs.spread, "slippage": costs.slippage}
                for pair, costs in load_pair_costs(pair_costs_path).items()
            }
        except (OSError, ValueError) as exc:
            pair_costs_error = f"pair costs file {pair_costs_path}: {type(exc).__name__}: {exc}"
    elif len(named) > 1:
        pair_costs_error = "the campaign names several pair_costs_file values: " + ", ".join(named)
    elif entries:
        pair_costs_error = "no entry names a pair_costs_file"

    return Context(
        artifact_path=artifact,
        artifact_label=_label(artifact, root),
        artifact_exists=exists,
        artifact_sha256=sha,
        artifact_mtime=mtime,
        raw_text=raw,
        parsed_ok=parsed_ok,
        results=results,
        entries=entries,
        sibling_names=siblings,
        expected=expected_params_by_key(),
        split=recomputed_split(),
        prespec={"path": PRESPEC_RELPATH, "sha256": _sha256_file(root / PRESPEC_RELPATH)},
        env=env,
        data_coverage=_read_side(data_coverage or artifact.parent / "data_coverage.json"),
        benchmark=_read_side(benchmark or artifact.parent / "benchmark.json"),
        pair_costs_ref=pair_costs_ref,
        pair_costs_path=pair_costs_path,
        pair_costs_error=pair_costs_error,
    )


# ---------------------------------------------------------------------------
# The fifteen assertions — pure functions of the context, in the frozen order
# ---------------------------------------------------------------------------

Outcome = tuple[list[str], list[str]]  # (violations, notes)


def a01_artifact_and_forbidden_outputs(ctx: Context) -> Outcome:
    problems: list[str] = []
    notes: list[str] = []
    if not ctx.artifact_exists:
        problems.append(f"{ctx.artifact_label}: file absent")
    elif not ctx.parsed_ok:
        problems.append(f"{ctx.artifact_label}: does not parse as a JSON object")
    forbidden = sorted(
        name
        for name in ctx.sibling_names
        if fnmatch.fnmatch(name.lower(), "*selection*.json")
        or fnmatch.fnmatch(name.lower(), "*report*.md")
    )
    if forbidden:
        problems.append(
            "forbidden report-phase outputs in the output directory: " + ", ".join(forbidden)
        )
    if "selected_for_paper" in ctx.raw_text:
        problems.append("the raw artifact text contains selected_for_paper")
    notes.append(
        f"{len(ctx.sibling_names)} file(s) in the output directory, none matching "
        "*selection*.json / *report*.md"
        if not forbidden
        else f"{len(ctx.sibling_names)} file(s) in the output directory"
    )
    return problems, notes


def a02_key_set(ctx: Context) -> Outcome:
    problems: list[str] = []
    notes: list[str] = []
    expected = ctx.expected
    entries = ctx.entries
    non_dict = sorted(k for k, v in ctx.results.items() if not isinstance(v, dict))
    if non_dict:
        problems.append(f"{len(non_dict)} non-object top-level key(s): {', '.join(non_dict[:4])}")
    if len(entries) != rc.N_CONFIGS_TOTAL:
        problems.append(f"{len(entries)} entries, expected {rc.N_CONFIGS_TOTAL}")
    missing = sorted(set(expected) - set(entries))
    unexpected = sorted(set(entries) - set(expected))
    if missing:
        problems.append(f"{len(missing)} expected key(s) absent, first {missing[0]}")
    if unexpected:
        problems.append(f"{len(unexpected)} unexpected key(s), first {unexpected[0]}")
    per_pair = Counter(str(e.get("pair")) for e in entries.values())
    for pair in rc.PAIRS:
        if per_pair.get(pair, 0) != rc.N_CONFIGS_PER_PAIR:
            problems.append(
                f"{pair}: {per_pair.get(pair, 0)} entries, expected {rc.N_CONFIGS_PER_PAIR}"
            )
    foreign = sorted(p for p in per_pair if p not in rc.PAIRS)
    if foreign:
        problems.append("pair(s) outside the frozen perimeter: " + ", ".join(foreign))
    without_params: list[str] = []
    for key in sorted(entries):
        params = entries[key].get("params")
        if not isinstance(params, dict):
            without_params.append(key)
            continue
        suffix = key.rsplit("_", 1)[-1]
        digest = p7.params_hash(params)
        if suffix != digest:
            problems.append(f"{key}: 8-hex suffix {suffix} != params_hash(params) {digest}")
    if without_params:
        notes.append(
            f"{len(without_params)} entry(ies) without a params dict: suffix not checked here "
            "(I-A.3 owns the failed jobs)"
        )
    notes.append(
        f"key set rebuilt in-script from expand_grid(GRID_ATR_GRID) x make_key: {len(expected)} keys"
    )
    return problems, notes


def a03_no_error_entry(ctx: Context) -> Outcome:
    failed = sorted(key for key, entry in ctx.entries.items() if "error" in entry)
    problems: list[str] = []
    if failed:
        shown = " | ".join(f"{key}: {ctx.entries[key].get('error')!r}" for key in failed[:4])
        problems.append(
            f"{len(failed)} entry(ies) carry an error key — {shown}"
            + (f" (+{len(failed) - 4} more)" if len(failed) > 4 else "")
        )
    notes = [
        f"{len(ctx.entries)} entries named and counted first; {len(failed)} carrying an error key "
        "(collect_flags would have skipped them silently)"
    ]
    return problems, notes


def a04_top_level_keys(ctx: Context) -> Outcome:
    problems: list[str] = []
    for key in sorted(ctx.entries):
        present = set(ctx.entries[key])
        missing = sorted(TOP_LEVEL_KEYS - present)
        extra = sorted(present - TOP_LEVEL_KEYS)
        if missing or extra:
            problems.append(f"{key}: missing {missing}, extra {extra}")
    return problems, [f"{len(TOP_LEVEL_KEYS)} top-level keys expected per entry"]


def a05_campaign_perimeter(ctx: Context) -> Outcome:
    problems: list[str] = []
    notes: list[str] = []
    try:
        require_metrics_version(ctx.entries, METRICS_VERSION, path=ctx.artifact_label)
    except MetricsVersionError as exc:
        problems.append(f"require_metrics_version: {exc}")
    try:
        require_replay_version(ctx.entries, REPLAY_VERSION, path=ctx.artifact_label)
    except ReplayVersionError as exc:
        problems.append(f"require_replay_version: {exc}")
    if ctx.pair_costs_error:
        problems.append(ctx.pair_costs_error)

    scalars: tuple[tuple[str, Any], ...] = (
        ("strategy", rc.STRATEGY),
        ("exchange", rc.EXCHANGE),
        ("fees", rc.FEES_MODEL),
        ("metrics_version", METRICS_VERSION),
        ("replay_version", REPLAY_VERSION),
        ("phase", "1"),
    )
    missing_liquidation = 0
    for key in sorted(ctx.entries):
        entry = ctx.entries[key]
        for field_name, expected in scalars:
            if entry.get(field_name) != expected:
                problems.append(f"{key}: {field_name} {entry.get(field_name)!r} != {expected!r}")
        pair = entry.get("pair")
        if pair not in rc.PAIRS:
            problems.append(f"{key}: pair {pair!r} outside {rc.PAIRS}")
        costs_file = entry.get("pair_costs_file")
        if costs_file is None or Path(str(costs_file)).name != rc.PAIR_COSTS_BASENAME:
            problems.append(f"{key}: pair_costs_file {costs_file!r} basename != "
                            f"{rc.PAIR_COSTS_BASENAME}")
        reference = (ctx.pair_costs_ref or {}).get(str(pair))
        exported = entry.get("pair_costs")
        if reference is None:
            pass  # already reported by pair_costs_error / the pair assertion above
        elif not isinstance(exported, dict) or set(exported) != {"spread", "slippage"}:
            problems.append(f"{key}: pair_costs {exported!r} is not a spread/slippage object")
        else:
            for field_name, value in sorted(reference.items()):
                if rc.dec(exported.get(field_name)) != value:
                    problems.append(
                        f"{key}: pair_costs.{field_name} {exported.get(field_name)!r} != "
                        f"{value} (from {ctx.pair_costs_path})"
                    )
        if rc.dec(entry.get("min_order_usdc")) != rc.dec(rc.MIN_ORDER_USDC):
            problems.append(f"{key}: min_order_usdc {entry.get('min_order_usdc')!r} != "
                            f"{rc.MIN_ORDER_USDC}")
        if entry.get("window_idx") is not None:
            problems.append(f"{key}: window_idx {entry.get('window_idx')!r} is not None")
        if entry.get("dca_counters") is not None:
            problems.append(f"{key}: dca_counters {entry.get('dca_counters')!r} is not None")

        block = entry.get("liquidation")
        for segment in rc.SEGMENTS:
            liquidation = block.get(segment) if isinstance(block, dict) else None
            if not isinstance(liquidation, dict):
                missing_liquidation += 1
                continue
            positions = rc.dec(liquidation.get("positions"))
            if positions is None or not positions.is_finite():
                problems.append(f"{key}/{segment}: positions {liquidation.get('positions')!r}")
                continue
            if positions < 0:
                problems.append(f"{key}/{segment}: positions {positions} < 0")
            elif positions > 0:
                for cost_field, ref_field in COST_FIELDS:
                    if reference is None:
                        continue
                    if rc.dec(liquidation.get(cost_field)) != reference[ref_field]:
                        problems.append(
                            f"{key}/{segment}: {cost_field} {liquidation.get(cost_field)!r} != "
                            f"{reference[ref_field]}"
                        )
                for field_name in ("timestamp", "price", "reference_price"):
                    if liquidation.get(field_name) is None:
                        problems.append(
                            f"{key}/{segment}: {field_name} is null with {positions} position(s)"
                        )
            else:
                for field_name in LIQUIDATION_NULL_WHEN_FLAT:
                    if liquidation.get(field_name) is not None:
                        problems.append(
                            f"{key}/{segment}: {field_name} {liquidation.get(field_name)!r} must "
                            "be null on a flat segment (positions == 0)"
                        )
                if rc.dec(liquidation.get("trades")) != 0:
                    problems.append(
                        f"{key}/{segment}: trades {liquidation.get('trades')!r} != 0 with "
                        "positions == 0"
                    )
    if missing_liquidation:
        notes.append(
            f"{missing_liquidation} (entry, segment) pair(s) without a liquidation block: the "
            "cost clause is not asserted on them, their presence is I-A.8's assertion"
        )
    notes.append(
        "spread_pct / slippage_pct asserted only when positions > 0; required null (with "
        "timestamp, price, reference_price and trades == 0) when positions == 0"
    )
    return problems, notes


def a06_period(ctx: Context) -> Outcome:
    problems: list[str] = []
    runner = (p7.P7_START, p7.P7_END, p7.TRAIN_RATIO)
    common = (rc.WINDOW_START, rc.WINDOW_END, rc.TRAIN_RATIO)
    if runner != common:
        problems.append(
            f"run_p7_grid_search constants {runner} differ from rejeu_common {common}: the "
            "recomputed split is ambiguous"
        )
    expected = {
        "train_start": p7.P7_START,
        "train_end": ctx.split,
        "test_start": ctx.split,
        "test_end": p7.P7_END,
    }
    for key in sorted(ctx.entries):
        period = ctx.entries[key].get("period")
        if not isinstance(period, dict) or set(period) != set(expected):
            shown = sorted(period) if isinstance(period, dict) else period
            problems.append(f"{key}: period keys {shown!r} != {sorted(expected)}")
            continue
        for name, want in expected.items():
            if _parse_dt(period[name]) != want:
                problems.append(f"{key}/{name}: {period[name]!r} != {want.isoformat()}")
    notes = [
        f"split recomputed from P7_START + (P7_END - P7_START) * {p7.TRAIN_RATIO} = "
        f"{ctx.split.isoformat()}"
    ]
    return problems, notes


def _effective_value(block: dict[str, Any], name: str) -> Any:
    cell = block.get(name)
    if not isinstance(cell, dict) or "value" not in cell:
        return _MISSING
    return cell["value"]


def a07_params_and_effective_params(ctx: Context) -> Outcome:
    problems: list[str] = []
    for key in sorted(ctx.entries):
        entry = ctx.entries[key]
        want_params = ctx.expected.get(key)
        if want_params is None:
            continue  # unknown key: already an I-A.2 violation
        params = entry.get("params")
        if not isinstance(params, dict) or set(params) != set(want_params):
            problems.append(f"{key}: params {params!r} != {want_params!r}")
            continue
        for name, want in want_params.items():
            got = params[name]
            same = got == want if isinstance(want, str) else rc.dec(got) == rc.dec(want)
            if not same:
                problems.append(f"{key}: params.{name} {got!r} != {want!r}")
        effective = entry.get("effective_params")
        block = effective.get("params") if isinstance(effective, dict) else None
        if not isinstance(block, dict):
            problems.append(f"{key}: effective_params.params absent or not an object")
            continue
        for name in ("min_spacing_pct", "atr_multiplier"):
            value = _effective_value(block, name)
            if value is _MISSING:
                problems.append(f"{key}: effective_params.params.{name} absent")
            elif rc.dec(value) != rc.dec(params[name]):
                problems.append(
                    f"{key}: effective_params.{name} {value!r} != params {params[name]!r}"
                )
        for name, want_dec in sorted(EFFECTIVE_DECIMAL_EXPECTED.items()):
            value = _effective_value(block, name)
            if value is _MISSING:
                problems.append(f"{key}: effective_params.params.{name} absent")
            elif rc.dec(value) != want_dec:
                problems.append(f"{key}: effective_params.{name} {value!r} != {want_dec}")
        mode = _effective_value(block, "bear_protection_mode")
        if mode is _MISSING:
            problems.append(f"{key}: effective_params.params.bear_protection_mode absent")
        elif mode != params["bear_protection_mode"]:
            problems.append(
                f"{key}: effective_params.bear_protection_mode {mode!r} != "
                f"params {params['bear_protection_mode']!r}"
            )
        pause = _effective_value(block, "pause_1w_strong_bear")
        want_pause = PAUSE_1W_BY_MODE.get(str(params["bear_protection_mode"]))
        if pause is _MISSING:
            problems.append(f"{key}: effective_params.params.pause_1w_strong_bear absent")
        elif want_pause is None:
            problems.append(f"{key}: bear_protection_mode {params['bear_protection_mode']!r} "
                            "has no frozen pause_1w_strong_bear")
        elif not isinstance(pause, bool) or pause is not want_pause:
            problems.append(
                f"{key}: pause_1w_strong_bear {pause!r} != {want_pause} for mode "
                f"{params['bear_protection_mode']!r}"
            )
    notes = [
        "Decimals compared through Decimal(str(value)) (effective_params exports them as strings)",
        "source never asserted (it reads class_default even under an override); "
        "bear_protection_1d_enabled not exported, hence not asserted (section J.4)",
        "limitation: effective_params is captured on the LAST segment executed (all)",
    ]
    return problems, notes


def a08_blocks_present(ctx: Context) -> Outcome:
    problems: list[str] = []
    notes: list[str] = []
    warmup_by_pair: dict[str, dict[str, list[str]]] = {}
    for key in sorted(ctx.entries):
        entry = ctx.entries[key]
        blocks: dict[str, Any] = {}
        for name in ("liquidation", "equity_daily", "rejections", "warmup"):
            block = entry.get(name)
            if not isinstance(block, dict) or not block:
                problems.append(f"{key}: {name} is {block!r}")
                continue
            if set(block) != set(rc.SEGMENTS):
                problems.append(f"{key}: {name} segments {sorted(block)} != {sorted(rc.SEGMENTS)}")
            blocks[name] = block
        for segment in rc.SEGMENTS:
            # each block is checked independently: an absent liquidation segment (already
            # reported above) must never mask a malformed warmup or rejections block
            liquidation = blocks.get("liquidation", {}).get(segment)
            if liquidation is None:
                pass
            elif not isinstance(liquidation, dict) or set(liquidation) != LIQUIDATION_KEYS:
                shown = sorted(liquidation) if isinstance(liquidation, dict) else liquidation
                problems.append(
                    f"{key}/{segment}: liquidation keys {shown!r} != the {len(LIQUIDATION_KEYS)} "
                    "frozen keys"
                )
            warmup = blocks.get("warmup", {}).get(segment)
            if warmup is None:
                pass
            elif not isinstance(warmup, dict) or set(warmup) != set(WARMUP_TIMEFRAMES):
                shown = sorted(warmup) if isinstance(warmup, dict) else warmup
                problems.append(f"{key}/{segment}: warmup timeframes {shown!r}")
            else:
                for timeframe in WARMUP_TIMEFRAMES:
                    fields = warmup[timeframe]
                    if not isinstance(fields, dict) or set(fields) != WARMUP_FIELDS:
                        shown = sorted(fields) if isinstance(fields, dict) else fields
                        problems.append(f"{key}/{segment}/{timeframe}: warmup fields {shown!r}")
            rejections = blocks.get("rejections", {}).get(segment)
            if rejections is None:
                pass
            elif not isinstance(rejections, dict) or set(rejections) != REJECTION_KEYS:
                shown = sorted(rejections) if isinstance(rejections, dict) else rejections
                problems.append(f"{key}/{segment}: rejections keys {shown!r}")
            else:
                for name in ("by_cause", "events"):
                    causes = rejections[name]
                    if not isinstance(causes, dict) or set(causes) != REJECTION_CAUSES:
                        shown = sorted(causes) if isinstance(causes, dict) else causes
                        problems.append(f"{key}/{segment}: rejections.{name} causes {shown!r}")
        warmup_block = blocks.get("warmup")
        if isinstance(warmup_block, dict) and warmup_block:
            pair = str(entry.get("pair"))
            warmup_by_pair.setdefault(pair, {}).setdefault(rc.sig(warmup_block), []).append(key)
    for pair in sorted(warmup_by_pair):
        groups = warmup_by_pair[pair]
        if len(groups) == 1:
            count = len(next(iter(groups.values())))
            notes.append(f"{pair}: one warmup block shared by its {count} configs")
        else:
            shown = "; ".join(f"{sig[:12]} x{len(keys)}" for sig, keys in sorted(groups.items()))
            notes.append(
                f"{pair}: warmup differs across configs — {len(groups)} distinct blocks ({shown}); "
                "REPORTED, resolved by retaining the strictest W class (section D.4), not fatal"
            )
    return problems, notes


def a09_equity_grids(ctx: Context) -> Outcome:
    problems: list[str] = []
    notes: list[str] = []
    anchor = float(rc.CAPITAL)
    observed_bounds: dict[str, set[tuple[Any, Any]]] = {}
    for key in sorted(ctx.entries):
        block = ctx.entries[key].get("equity_daily")
        if not isinstance(block, dict):
            continue  # I-A.8 owns the absence
        for segment in rc.SEGMENTS:
            grid = block.get(segment)
            if not isinstance(grid, dict) or not isinstance(grid.get("values"), list):
                problems.append(f"{key}/{segment}: equity_daily block absent or without values")
                continue
            values = grid["values"]
            if len(values) != rc.SEGMENT_POINTS[segment]:
                problems.append(
                    f"{key}/{segment}: {len(values)} points, expected "
                    f"{rc.SEGMENT_POINTS[segment]} (-> {rc.SEGMENT_RETURNS[segment]} returns)"
                )
                continue
            bad = [
                i
                for i, value in enumerate(values)
                if not _is_number(value) or not math.isfinite(value) or value <= 0
            ]
            if bad:
                problems.append(
                    f"{key}/{segment}: {len(bad)} non-finite or non-positive value(s), first at "
                    f"index {bad[0]} ({values[bad[0]]!r})"
                )
            elif float(values[0]) != anchor:
                problems.append(f"{key}/{segment}: values[0] {values[0]!r} != {anchor}")
            if segment == "all":
                if _parse_dt(grid.get("start")) != rc.WINDOW_START:
                    problems.append(f"{key}/all: start {grid.get('start')!r} != frozen anchor")
                if _parse_dt(grid.get("end")) != rc.WINDOW_END:
                    problems.append(f"{key}/all: end {grid.get('end')!r} != frozen end")
            else:
                observed_bounds.setdefault(segment, set()).add(
                    (grid.get("start"), grid.get("end"))
                )
    for segment in sorted(observed_bounds):
        bounds = sorted(observed_bounds[segment])
        notes.append(
            f"{segment} bounds observed (reported, the pre-spec freezes only the all bounds): "
            + "; ".join(f"{start} -> {end}" for start, end in bounds[:2])
            + (f" (+{len(bounds) - 2} more)" if len(bounds) > 2 else "")
        )
    notes.append(
        f"points expected: all {rc.SEGMENT_POINTS['all']}, train {rc.SEGMENT_POINTS['train']}, "
        f"test {rc.SEGMENT_POINTS['test']}"
    )
    return problems, notes


def a10_metrics_self_test(ctx: Context) -> Outcome:
    problems: list[str] = []
    calmar_skipped: list[str] = []
    calmar_checked = 0
    for key in sorted(ctx.entries):
        entry = ctx.entries[key]
        curves = entry.get("equity_daily")
        for segment in rc.SEGMENTS:
            metrics = entry.get(segment)
            if not isinstance(metrics, dict):
                problems.append(f"{key}/{segment}: metrics block absent")
                continue
            if set(metrics) != METRIC_KEYS:
                problems.append(
                    f"{key}/{segment}: metric keys missing {sorted(METRIC_KEYS - set(metrics))}, "
                    f"extra {sorted(set(metrics) - METRIC_KEYS)}"
                )
                continue
            grid = curves.get(segment) if isinstance(curves, dict) else None
            if not isinstance(grid, dict) or not isinstance(grid.get("values"), list):
                problems.append(f"{key}/{segment}: no exported curve to self-test against")
                continue
            probe = self_test_segment(grid["values"], grid.get("start"), grid.get("end"))
            if probe is None:
                problems.append(
                    f"{key}/{segment}: the exported curve cannot be recomputed (non-finite or "
                    "non-positive NAV)"
                )
                continue
            for name, recomputed in (
                ("sharpe_ratio", probe.sharpe),
                ("sortino_ratio", probe.sortino),
            ):
                reason = _compare_optional(metrics[name], recomputed)
                if reason:
                    problems.append(f"{key}/{segment}: {name} {reason}")
            reason = _compare_optional(metrics["max_drawdown_pct_daily"], probe.mdd_daily)
            if reason:
                problems.append(f"{key}/{segment}: max_drawdown_pct_daily {reason}")
            if metrics["n_daily_returns"] != probe.n_defined:
                problems.append(
                    f"{key}/{segment}: n_daily_returns {metrics['n_daily_returns']!r} != "
                    f"{probe.n_defined} defined returns recomputed from the curve"
                )
            if segment == "all" and metrics["n_daily_returns"] != rc.SEGMENT_RETURNS["all"]:
                problems.append(
                    f"{key}/all: n_daily_returns {metrics['n_daily_returns']!r} != "
                    f"{rc.SEGMENT_RETURNS['all']}"
                )
            calmar = metrics["calmar_ratio"]
            if calmar is None or probe.cagr is None or not _is_number(
                metrics["max_drawdown_pct_daily"]
            ):
                calmar_skipped.append(f"{key}/{segment}")
                continue
            calmar_checked += 1
            identity = float(calmar) * float(metrics["max_drawdown_pct_daily"])
            reason = _compare_optional(identity, probe.cagr)
            if reason:
                problems.append(
                    f"{key}/{segment}: calmar_ratio x max_drawdown_pct_daily vs recomputed CAGR "
                    f"{reason}"
                )
    notes = [
        f"{len(METRIC_KEYS)} metric keys; sharpe / sortino / max_drawdown_pct(index) / defined "
        "returns recomputed from equity_daily values converted to Decimal, tolerance "
        f"{SELF_TEST_TOL:.0e}, None <-> None exact",
        "cagr_pct is NOT exported: it is recomputed and compared to no field; its only "
        f"admissible cross-check (calmar_ratio x max_drawdown_pct_daily) ran on {calmar_checked} "
        f"segment(s) and was SKIPPED on {len(calmar_skipped)}"
        + (f" (first: {', '.join(sorted(calmar_skipped)[:3])})" if calmar_skipped else ""),
    ]
    return problems, notes


def a11_accounting_identities(ctx: Context) -> Outcome:
    problems: list[str] = []
    for key in sorted(ctx.entries):
        entry = ctx.entries[key]
        block = entry.get("liquidation")
        for segment in rc.SEGMENTS:
            metrics = entry.get(segment)
            liquidation = block.get(segment) if isinstance(block, dict) else None
            if not isinstance(metrics, dict) or not isinstance(liquidation, dict):
                continue  # presence is owned by I-A.8 / I-A.10
            total = rc.dec(metrics.get("total_trades"))
            positions = rc.dec(liquidation.get("positions"))
            if total is None or positions is None:
                problems.append(
                    f"{key}/{segment}: total_trades {metrics.get('total_trades')!r} / positions "
                    f"{liquidation.get('positions')!r} not coercible"
                )
                continue
            if not (total >= positions >= 0):
                problems.append(
                    f"{key}/{segment}: total_trades {total} >= positions {positions} >= 0 violated"
                )
            if total - positions < 0:
                problems.append(f"{key}/{segment}: cycles {total - positions} < 0")
            winning = rc.dec(metrics.get("winning_trades"))
            losing = rc.dec(metrics.get("losing_trades"))
            if winning is None or losing is None or winning + losing != total:
                problems.append(
                    f"{key}/{segment}: winning {metrics.get('winning_trades')!r} + losing "
                    f"{metrics.get('losing_trades')!r} != total_trades {total}"
                )
            starting = rc.dec(metrics.get("starting_balance"))
            if starting != rc.dec(rc.CAPITAL):
                problems.append(
                    f"{key}/{segment}: starting_balance {metrics.get('starting_balance')!r} != "
                    f"{rc.CAPITAL}"
                )
            if segment == "all" and rc.dec(metrics.get("duration_days")) != rc.dec(rc.WINDOW_DAYS):
                problems.append(
                    f"{key}/all: duration_days {metrics.get('duration_days')!r} != "
                    f"{rc.WINDOW_DAYS}"
                )
            if rc.dec(metrics.get("pf_excluded_trades")) != 0:
                problems.append(
                    f"{key}/{segment}: pf_excluded_trades "
                    f"{metrics.get('pf_excluded_trades')!r} != 0"
                )
            unrealized = rc.dec(metrics.get("unrealized_pnl"))
            liquidation_pnl = rc.dec(liquidation.get("pnl"))
            if (
                unrealized is None
                or liquidation_pnl is None
                or abs(unrealized - liquidation_pnl) > UNREALIZED_TOL
            ):
                problems.append(
                    f"{key}/{segment}: unrealized_pnl {metrics.get('unrealized_pnl')!r} != "
                    f"liquidation.pnl {liquidation.get('pnl')!r} — this field carries the "
                    "TERMINAL LIQUIDATION P&L, not an open mark"
                )
            if positions == 0:
                net = rc.dec(metrics.get("net_pnl"))
                ending = rc.dec(metrics.get("ending_balance"))
                if (
                    net is None
                    or ending is None
                    or starting is None
                    or abs(net - (ending - starting)) > FLAT_NET_PNL_TOL
                ):
                    problems.append(
                        f"{key}/{segment}: segment ended flat but net_pnl "
                        f"{metrics.get('net_pnl')!r} != ending {metrics.get('ending_balance')!r} "
                        f"- starting {metrics.get('starting_balance')!r}"
                    )
    notes = [
        "all figures coerced by Decimal(str(x)) as b4_flags._dec does; no '~ 0' assertion exists "
        "anywhere: unrealized_pnl IS liquidation.pnl"
    ]
    return problems, notes


def a12_liquidation_reconciliation(ctx: Context) -> Outcome:
    problems: list[str] = []
    checked = 0
    for key in sorted(ctx.entries):
        entry = ctx.entries[key]
        block = entry.get("liquidation")
        for segment in rc.SEGMENTS:
            liquidation = block.get(segment) if isinstance(block, dict) else None
            metrics = entry.get(segment)
            if not isinstance(liquidation, dict):
                continue  # presence is owned by I-A.8
            checked += 1
            for name in ("residual_net_proceeds", "residual_trade_btc"):
                value = rc.dec(liquidation.get(name))
                if value is None or value != 0:
                    problems.append(f"{key}/{segment}: {name} {liquidation.get(name)!r} != 0")
            for name in ("inventory_divergence_btc", "dust_written_off_btc"):
                value = rc.dec(liquidation.get(name))
                if value is None or not value.is_finite() or abs(value) > rc.DUST_BTC:
                    problems.append(
                        f"{key}/{segment}: {name} {liquidation.get(name)!r} beyond "
                        f"DUST_BTC {rc.DUST_BTC}"
                    )
            lot_basis = rc.dec(liquidation.get("net_pnl_lot_basis"))
            net = rc.dec((metrics or {}).get("net_pnl")) if isinstance(metrics, dict) else None
            if lot_basis is None or net is None or abs(net - lot_basis) > rc.NET_PNL_TOL:
                problems.append(
                    f"{key}/{segment}: net_pnl {(metrics or {}).get('net_pnl')!r} vs lot basis "
                    f"{liquidation.get('net_pnl_lot_basis')!r} beyond "
                    f"NET_PNL_TOL {rc.NET_PNL_TOL}"
                )
    notes = [
        f"{checked} liquidation block(s) reconciled explicitly (not delegated), with the "
        "b4_flags tolerances applied AFTER presence was proven by I-A.8"
    ]
    return problems, notes


def a13_b4_flags_mute(ctx: Context) -> Outcome:
    problems: list[str] = []
    flags = b4_flags.collect_flags(ctx.results)
    if flags:
        shown = " | ".join(
            f"{flag['run']}/{flag['segment']}: {'; '.join(flag['reasons'])}" for flag in flags[:4]
        )
        problems.append(f"collect_flags returned {len(flags)} flag(s) — {shown}")
    checked = 0
    for key in sorted(ctx.entries):
        entry = ctx.entries[key]
        block = entry.get("liquidation")
        for segment in rc.SEGMENTS:
            checked += 1
            liquidation = block.get(segment) if isinstance(block, dict) else None
            reasons = b4_flags.flag_segment(liquidation, entry.get(segment))
            if reasons:
                problems.append(f"{key}/{segment}: flag_segment {'; '.join(reasons)}")
    expected_pairs = rc.N_CONFIGS_TOTAL * len(rc.SEGMENTS)
    if checked != expected_pairs:
        problems.append(
            f"flag_segment re-applied on {checked} (entry, segment) pairs, expected "
            f"{expected_pairs}"
        )
    notes = [
        f"collect_flags mute and flag_segment independently re-applied over {checked} "
        "(entry, segment) pairs — evaluated only now, after I-A.1..I-A.12"
    ]
    return problems, notes


def a14_instrument_integrity(ctx: Context) -> Outcome:
    problems: list[str] = []
    env = ctx.env
    if env.code_diff.strip():
        head = " / ".join(line.strip() for line in env.code_diff.strip().splitlines()[:3])
        problems.append(f"code diff against {env.base_sha[:7]} is not empty: {head}")
    listed = _parse_name_status(env.tests_diff)
    for status, path in listed:
        if path not in rc.NEW_TEST_FILES:
            problems.append(
                f"tests diff touches {path} (status {status}): outside the closed list of "
                f"{len(rc.NEW_TEST_FILES)} new test files"
            )
        elif not status.startswith("A"):
            problems.append(f"tests diff shows {path} as {status}, not a pure addition")
    if env.porcelain.strip():
        head = " / ".join(line.strip() for line in env.porcelain.strip().splitlines()[:3])
        problems.append(f"git status --porcelain is not empty over the pinned paths: {head}")
    notes = [
        f"git HEAD {env.git_head or '<unknown>'} against base {env.base_sha}",
        f"tests diff lists {len(listed)} path(s), all inside the closed list of "
        f"{len(rc.NEW_TEST_FILES)}"
        if not any(path not in rc.NEW_TEST_FILES for _, path in listed)
        else f"tests diff lists {len(listed)} path(s)",
        f"python {env.python}, numpy {env.numpy}, host {env.host}, poetry.lock "
        f"{env.poetry_lock_sha256[:12]}, {len(env.engine_file_sha256)} engine fingerprint(s)",
    ]
    return problems, notes


def a15_pre_campaign_artifacts(ctx: Context) -> Outcome:
    problems: list[str] = []
    notes: list[str] = []
    campaign_stamp = (
        datetime.fromtimestamp(ctx.artifact_mtime, UTC) if ctx.artifact_mtime else None
    )
    for name, side, required in (
        ("data_coverage.json", ctx.data_coverage, DATA_COVERAGE_KEYS),
        ("benchmark.json", ctx.benchmark, BENCHMARK_KEYS),
    ):
        if not side.exists or not isinstance(side.data, dict):
            problems.append(f"{name}: absent or not a JSON object at {side.path}")
            continue
        missing = sorted(required - set(side.data))
        if missing:
            problems.append(f"{name}: frozen field(s) absent: {missing}")
        if side.data.get("base_sha") != rc.BASE_SHA:
            problems.append(f"{name}: base_sha {side.data.get('base_sha')!r} != {rc.BASE_SHA}")
        generated = _parse_dt(side.data.get("generated_at"))
        if generated is None:
            problems.append(f"{name}: generated_at {side.data.get('generated_at')!r} unreadable")
        elif campaign_stamp is not None and generated > campaign_stamp:
            problems.append(
                f"{name}: generated_at {generated.isoformat()} is AFTER the campaign artifact "
                f"({campaign_stamp.isoformat()}): it was not produced before the campaign"
            )

    coverage = ctx.data_coverage.data or {}
    if coverage:
        if coverage.get("exchange") != rc.EXCHANGE:
            problems.append(f"data_coverage.json: exchange {coverage.get('exchange')!r}")
        window = coverage.get("window") if isinstance(coverage.get("window"), dict) else {}
        if _parse_dt(window.get("start")) != rc.WINDOW_START:
            problems.append(f"data_coverage.json: window.start {window.get('start')!r}")
        if _parse_dt(window.get("end")) != rc.WINDOW_END:
            problems.append(f"data_coverage.json: window.end {window.get('end')!r}")
        if rc.dec(window.get("days")) != rc.dec(rc.WINDOW_DAYS):
            problems.append(f"data_coverage.json: window.days {window.get('days')!r}")
        pairs = coverage.get("pairs") if isinstance(coverage.get("pairs"), dict) else {}
        for pair in rc.PAIRS:
            if pair not in pairs:
                problems.append(f"data_coverage.json: pair {pair} absent")

    benchmark = ctx.benchmark.data or {}
    if benchmark:
        if benchmark.get("exchange") != rc.EXCHANGE:
            problems.append(f"benchmark.json: exchange {benchmark.get('exchange')!r}")
        if benchmark.get("fees_model") != rc.FEES_MODEL:
            problems.append(f"benchmark.json: fees_model {benchmark.get('fees_model')!r}")
        costs_file = benchmark.get("pair_costs_file")
        if costs_file is None or Path(str(costs_file)).name != rc.PAIR_COSTS_BASENAME:
            problems.append(f"benchmark.json: pair_costs_file {costs_file!r}")
        exported = benchmark.get("pair_costs") if isinstance(
            benchmark.get("pair_costs"), dict
        ) else {}
        campaign_costs = {
            str(entry.get("pair")): entry.get("pair_costs")
            for entry in ctx.entries.values()
            if isinstance(entry.get("pair_costs"), dict)
        }
        for pair in rc.PAIRS:
            reference = (ctx.pair_costs_ref or {}).get(pair)
            got = exported.get(pair)
            if reference is None:
                problems.append(f"benchmark.json: no campaign reference costs for {pair}")
                continue
            if not isinstance(got, dict):
                problems.append(f"benchmark.json: pair_costs[{pair}] {got!r}")
                continue
            for field_name, value in sorted(reference.items()):
                if rc.dec(got.get(field_name)) != value:
                    problems.append(
                        f"benchmark.json: pair_costs[{pair}].{field_name} "
                        f"{got.get(field_name)!r} != {value}"
                    )
            campaign = campaign_costs.get(pair)
            if isinstance(campaign, dict):
                for field_name in ("spread", "slippage"):
                    if rc.dec(got.get(field_name)) != rc.dec(campaign.get(field_name)):
                        problems.append(
                            f"benchmark.json: pair_costs[{pair}].{field_name} "
                            f"{got.get(field_name)!r} != campaign {campaign.get(field_name)!r}"
                        )
    notes.append(
        "'produced before the campaign' is read as generated_at <= the campaign artifact's mtime"
    )
    return problems, notes


ASSERTIONS: tuple[tuple[str, str, Callable[[Context], Outcome]], ...] = (
    ("I-A.1", "artifact parses; no selection or report output beside it",
     a01_artifact_and_forbidden_outputs),
    ("I-A.2", "96 entries, 48 per pair, key set rebuilt from the grid", a02_key_set),
    ("I-A.3", "no entry carries an error key", a03_no_error_entry),
    ("I-A.4", "22 top-level keys per entry (conditional on I-A.3)", a04_top_level_keys),
    ("I-A.5", "frozen campaign perimeter: exchange, fees, costs, versions",
     a05_campaign_perimeter),
    ("I-A.6", "period equals the four frozen bounds, split recomputed", a06_period),
    ("I-A.7", "params and effective_params equal the frozen configuration",
     a07_params_and_effective_params),
    ("I-A.8", "liquidation / equity_daily / rejections / warmup present and shaped",
     a08_blocks_present),
    ("I-A.9", "equity grids 1097 / 769 / 330, anchored at 1000, all finite", a09_equity_grids),
    ("I-A.10", "24 metric keys and instrument self-test against the exported curve",
     a10_metrics_self_test),
    ("I-A.11", "per-segment accounting identities", a11_accounting_identities),
    ("I-A.12", "terminal liquidation reconciliation, explicit", a12_liquidation_reconciliation),
    ("I-A.13", "b4_flags mute and flag_segment re-applied over 96 x 3", a13_b4_flags_mute),
    ("I-A.14", "instrument integrity: control diff, worktree, fingerprints",
     a14_instrument_integrity),
    ("I-A.15", "data_coverage.json and benchmark.json produced before the campaign",
     a15_pre_campaign_artifacts),
)


# ---------------------------------------------------------------------------
# Runner, payload, rendering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Assertion:
    id: str
    name: str
    ok: bool
    skipped: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "ok": self.ok,
            "skipped": self.skipped,
            "detail": self.detail,
        }


def run_assertions(ctx: Context) -> list[Assertion]:
    """The fifteen assertions in the frozen order; everything after a failure is NOT evaluated."""
    rows: list[Assertion] = []
    stopped_at: str | None = None
    for identifier, name, check in ASSERTIONS:
        if stopped_at is not None:
            rows.append(
                Assertion(
                    identifier,
                    name,
                    False,
                    True,
                    f"not evaluated: {stopped_at} already failed — under the frozen order of "
                    "section I-A every later assertion (b4_flags included) would be a false green",
                )
            )
            continue
        try:
            problems, notes = check(ctx)
        except Exception as exc:
            problems, notes = [f"{type(exc).__name__}: {exc}"], []
        ok = not problems
        rows.append(Assertion(identifier, name, ok, False, _detail(problems, notes)))
        if not ok:
            stopped_at = identifier
    return rows


def build_payload(ctx: Context, rows: list[Assertion], *, now: str) -> dict[str, Any]:
    failed = [row.id for row in rows if not row.ok and not row.skipped]
    ok = not failed
    listed = _parse_name_status(ctx.env.tests_diff)
    tests_only_new = all(
        path in rc.NEW_TEST_FILES and status.startswith("A") for status, path in listed
    )
    return {
        "generated_at": now,
        "base_sha": rc.BASE_SHA,
        "prespec": ctx.prespec,
        "artifact": ctx.artifact_label,
        "artifact_sha256": ctx.artifact_sha256,
        "ok": ok,
        "exit_code": 0 if ok else 2,
        "assertions": [row.to_dict() for row in rows],
        "failed": failed,
        "environment": ctx.env.to_dict(),
        "control_diff": {
            "code_diff_empty": not ctx.env.code_diff.strip(),
            "tests_diff_only_new": tests_only_new,
            "worktree_clean": not ctx.env.porcelain.strip(),
            "detail": (
                f"code paths {', '.join(rc.CONTROL_DIFF_PATHS)}; tests diff lists "
                + (", ".join(f"{status} {path}" for status, path in listed) or "nothing")
                + "; porcelain "
                + ("empty" if not ctx.env.porcelain.strip() else ctx.env.porcelain.strip())
            ),
        },
    }


def render_lines(payload: dict[str, Any]) -> list[str]:
    lines = [
        f"Rejeu diagnostic grid — campaign validity (section I-A) on {payload['artifact']}",
        f"sha256 {payload['artifact_sha256']} · prespec {payload['prespec']['sha256'][:16]}",
        "",
    ]
    for row in payload["assertions"]:
        status = "ok " if row["ok"] else ("--- " if row["skipped"] else "FAIL")
        lines.append(f"{status} {row['id']:<7} {row['name']}")
        lines.append(f"         {row['detail']}")
    lines.append("")
    verdict = "EXPLOITABLE (exit 0)" if payload["ok"] else "NOT EXPLOITABLE (exit 2)"
    failed = ", ".join(payload["failed"]) or "none"
    lines.append(f"Verdict: {verdict} — failed: {failed}")
    return lines


def render_markdown(payload: dict[str, Any]) -> str:
    verdict = "EXPLOITABLE (exit 0)" if payload["ok"] else "NOT EXPLOITABLE (exit 2)"
    lines = [
        "# Rejeu diagnostic grid — validité de campagne (§ I-A)",
        "",
        f"- artefact : `{payload['artifact']}` (sha256 `{payload['artifact_sha256']}`)",
        f"- pré-spec : `{payload['prespec']['path']}` (sha256 `{payload['prespec']['sha256']}`)",
        f"- base sha : `{payload['base_sha']}` · HEAD `{payload['environment']['git_head']}`",
        f"- verdict : **{verdict}** — échecs : {', '.join(payload['failed']) or 'aucun'}",
        "",
        "| # | Assertion | Résultat | Détail |",
        "|---|---|---|---|",
    ]
    for row in payload["assertions"]:
        status = "ok" if row["ok"] else ("non évaluée" if row["skipped"] else "**ÉCHEC**")
        detail = str(row["detail"]).replace("|", "\\|")
        lines.append(f"| {row['id']} | {row['name']} | {status} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("artifact", type=Path, nargs="?", default=DEFAULT_ARTIFACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--data-coverage", type=Path, default=None)
    parser.add_argument("--benchmark", type=Path, default=None)
    parser.add_argument(
        "--now", default=None, help="ISO UTC stamp of generated_at (default: now), for determinism"
    )
    args = parser.parse_args(argv)

    now = args.now or datetime.now(UTC).isoformat()
    env = collect_environment()
    ctx = build_context(
        args.artifact, env=env, data_coverage=args.data_coverage, benchmark=args.benchmark
    )
    rows = run_assertions(ctx)
    payload = build_payload(ctx, rows, now=now)
    rc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(payload), encoding="utf-8")
    for row in rows:
        if not row.ok and not row.skipped:
            print(f"{row.id}: {row.detail}", file=sys.stderr)
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
