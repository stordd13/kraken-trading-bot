"""Rejeu diagnostic grid — shared, frozen constants and pure helpers.

Pure, read-only. This module is the single source of the numbers frozen by
``docs/rejeu_grid_prespec.md``: every other ``scripts/audit/rejeu_*.py`` imports them from
here rather than restating them, so a threshold cannot drift between two scripts.

It also carries the canonicalisation of section A (the ``liquidation`` block is exported as
Decimal-valued **strings**, so rounding "every float" would apply no tolerance where the dust
actually lives) and the small numeric helpers the analyses share.

Usage::

    from rejeu_common import CYCLES_MIN, canon, sig, write_json

Exit codes of the scripts that import it: 0 ok, 1 violation, 2 usage or input error.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Frozen perimeter (prespec section 0)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

STRATEGY = "grok_grid_atr_adaptive_v4"
PAIRS: tuple[str, ...] = ("BTC/USDC", "SOL/USDC")
EXCHANGE = "binance"
FEES_MODEL = "bybit"
PAIR_COSTS_BASENAME = "pair_costs_b4.json"
MIN_ORDER_USDC = 5.0
CAPITAL = Decimal("1000")

WINDOW_START = datetime(2023, 4, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 4, 1, tzinfo=UTC)
TRAIN_RATIO = 0.7
WINDOW_DAYS = 1096

# equity_daily lengths: points -> returns
SEGMENT_POINTS = {"all": 1097, "train": 769, "test": 330}
SEGMENT_RETURNS = {"all": 1096, "train": 768, "test": 329}
SEGMENTS: tuple[str, ...] = ("train", "test", "all")

N_CONFIGS_PER_PAIR = 48
N_CONFIGS_TOTAL = 96

# Class defaults in force (debt 13 not fixed) — asserted, never "fixed"
CLASS_DEFAULTS = {
    "grid_levels": 12,
    "max_spacing_pct": Decimal("0.05"),
    "atr_period": 14,
    "recalc_hours": 6,
    "bias_1d": Decimal("0.2"),
    "order_size_usdc": Decimal("25"),
    "max_allocation_pct": Decimal("20.0"),
}
MAX_SPACING_PCT = Decimal("0.05")
ATR_PERIOD = 14

# ---------------------------------------------------------------------------
# Frozen thresholds (prespec sections C, D, E, F)
# ---------------------------------------------------------------------------

CYCLES_MIN = 25  # section C.2 — coverage filter, not a sample size
COVERAGE_MIN_DAYS = 1065  # section D.2 — 1096 - 31
MAX_GAP_DAYS = 31
DAY_5M_COMPLETE_MIN = 144  # >= half of the 288 expected 5m candles
FIRST_COVERED_DAY_MAX = "2023-04-02"
LAST_COVERED_DAY_MIN = "2026-03-31"

FF_DAYS_MAX = 31  # section E.4 — forward-filled benchmark marks
LAMBDA_STEP = Decimal("0.001")
MATCH_RESIDUAL_WARN = 0.10  # 10 % -> matching labelled approximate (descriptive)
MATCHINGS: tuple[str, ...] = ("dd", "sigma")

G2_MIN_RETURN_PCT = 6.0  # section F.3 — conventional research-continuation floor
G3_FEE_MULTIPLE = 10.0  # DESCRIPTIVE only, never a gate
NNZ_MIN = 110  # conventional activity filter, not an information measure
MIN_RETURN_DOMAIN = -0.5  # log1p domain guard

BLOCK_LENGTHS: tuple[int, ...] = (10, 21, 42)
BLOCK_LENGTH_HEADLINE = 21
BOOTSTRAP_B = 10000
SEED_BASE = 20260919
ALPHA = 0.05
DEGENERATE_MAX = 10  # per config, out of BOOTSTRAP_B
LAMBDA_REESTIMATION_BUDGET_SEC = 7200.0  # 2 h per (L, matching) combination

ANNUALISATION_DAYS = 365

# b4_flags tolerances, restated here for the explicit (non-delegated) reconciliation
DUST_BTC = Decimal("1e-12")
NET_PNL_TOL = Decimal("1e-9")

BASE_SHA = "9897803f48a6537a248f5a41c53a1ea5522d46a0"

CONTROL_DIFF_PATHS: tuple[str, ...] = (
    "src",
    "scripts/backtest.py",
    "scripts/run_p6_backtests.py",
    "scripts/run_p7_grid_search.py",
    "scripts/p7_grids.py",
    "config",
    "pyproject.toml",
    "poetry.lock",
)

NEW_TEST_FILES: tuple[str, ...] = (
    "tests/test_scripts/test_rejeu_data_coverage.py",
    "tests/test_scripts/test_rejeu_validate_campaign.py",
    "tests/test_scripts/test_rejeu_signatures.py",
    "tests/test_scripts/test_rejeu_spacing_clamp.py",
    "tests/test_scripts/test_rejeu_benchmark.py",
    "tests/test_scripts/test_rejeu_effect.py",
    "tests/test_scripts/test_rejeu_verdict.py",
)

# ---------------------------------------------------------------------------
# Verdicts and reason codes (prespec section H) — closed lists, priority order
# ---------------------------------------------------------------------------

VERDICT_CANDIDAT = "candidat"
VERDICT_DEPRIORISATION = "depriorisation"
VERDICT_INCONCLUSIF = "inconclusif"
VERDICT_DESCRIPTIF = "descriptif"

REASON_PRIORITY: tuple[str, ...] = (
    "R0_INVALID_RUN",
    "R1_ACCOUNTING_FLAG",
    "D_UNMEASURABLE",
    "D_NO_ADMISSIBLE_PAIR",
    "D_WARMUP_W2",
    "E_NO_BENCHMARK",
    "C_COVERAGE",
    "F_NOT_ESTIMABLE",
    "F_CANNOT_SEPARATE",
)

STATUS_DESCRIPTIF = "DESCRIPTIF"
STATUS_NO_BENCHMARK = "NO_BENCHMARK"
STATUS_BELOW_COVERAGE = "BELOW_COVERAGE"
STATUS_NOT_ESTIMABLE = "NOT_ESTIMABLE"
STATUS_ELIGIBLE = "ELIGIBLE"

INDISCERNIBILITY_CAVEAT = (
    "L'égalité de signature est une indiscernabilité sur les sorties exportées. Le journal "
    "des transactions n'est pas exporté : ce n'est jamais une preuve d'identité des ordres, "
    "ni une preuve que le clamp a saturé."
)

# ---------------------------------------------------------------------------
# Canonicalisation (prespec section A.1)
# ---------------------------------------------------------------------------


class NonFiniteValueError(ValueError):
    """A NaN or an infinity reached the signature: a validity failure, never a class split."""


def _is_decimal_string(value: str) -> bool:
    try:
        Decimal(value)
    except (InvalidOperation, ValueError):
        return False
    return True


def _finite_decimal(value: Decimal, origin: Any) -> Decimal:
    """Reject a non-finite Decimal (``Decimal("NaN")`` parses, so the string road needs it too)."""
    if not value.is_finite():
        raise NonFiniteValueError(f"non-finite value in the signature payload: {origin!r}")
    return value


def _finite_float(value: float) -> float:
    if not math.isfinite(value):
        raise NonFiniteValueError(f"non-finite value in the signature payload: {value!r}")
    return value


def canon(x: Any) -> Any:
    """Canonical image of a JSON leaf for the indiscernibility signature.

    ``float`` -> shortest round-trip repr ("0.0"); ``int`` / ``bool`` -> repr ("0"); ``None`` ->
    "null"; a string that parses as a Decimal -> its normalised fixed-point form ("0E-30" -> "0",
    so dust and zero do not split two identical runs); any other string verbatim. Containers are
    mapped recursively. A float keeps an image distinct from an int or a Decimal string; ``0`` and
    ``"0"`` do share the image "0", which is harmless here because a given JSON path never changes
    type between two runs of the same runner. **A NaN or an infinity raises** (``allow_nan=False``
    alone cannot fire: the leaf is already a string when ``json.dumps`` runs).
    """
    if isinstance(x, bool) or isinstance(x, int):
        return repr(x)
    if isinstance(x, float):
        return repr(_finite_float(float(x)))
    if x is None:
        return "null"
    if isinstance(x, Decimal):
        return format(_finite_decimal(x, x).normalize(), "f")
    if isinstance(x, str):
        if _is_decimal_string(x):
            return format(_finite_decimal(Decimal(x), x).normalize(), "f")
        return x
    if isinstance(x, dict):
        return {k: canon(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [canon(v) for v in x]
    raise TypeError(f"canon: unsupported leaf type {type(x).__name__}")


def canon_tolerant(x: Any, *, digits: int = 9, quantum: str = "1e-12") -> Any:
    """``canon`` with a tolerance: floats through ``%.{digits}e``, Decimal strings quantised."""
    if isinstance(x, bool) or isinstance(x, int):
        return repr(x)
    if isinstance(x, float):
        return repr(float(f"%.{digits}e" % _finite_float(float(x))))
    if x is None:
        return "null"
    if isinstance(x, Decimal):
        return format(_finite_decimal(x, x).quantize(Decimal(quantum)).normalize(), "f")
    if isinstance(x, str):
        if _is_decimal_string(x):
            return format(_finite_decimal(Decimal(x), x).quantize(Decimal(quantum)).normalize(), "f")
        return x
    if isinstance(x, dict):
        return {k: canon_tolerant(v, digits=digits, quantum=quantum) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [canon_tolerant(v, digits=digits, quantum=quantum) for v in x]
    raise TypeError(f"canon_tolerant: unsupported leaf type {type(x).__name__}")


def dumps_canonical(obj: Any) -> str:
    """Deterministic JSON text; ``allow_nan=False`` so a NaN/Inf raises instead of splitting."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def sig(obj: Any) -> str:
    """sha256 of the canonical JSON text of ``canon(obj)``."""
    return hashlib.sha256(dumps_canonical(canon(obj)).encode("utf-8")).hexdigest()


def sig_tolerant(obj: Any) -> str:
    return hashlib.sha256(dumps_canonical(canon_tolerant(obj)).encode("utf-8")).hexdigest()


def first_difference(a: Any, b: Any, path: str = "$") -> str | None:
    """JSON path of the first difference between two nested structures, or None."""
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return path
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}.{key}"
            sub = first_difference(a[key], b[key], f"{path}.{key}")
            if sub is not None:
                return sub
        return None
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return f"{path}[len]"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            sub = first_difference(x, y, f"{path}[{i}]")
            if sub is not None:
                return sub
        return None
    return None if a == b else path


# ---------------------------------------------------------------------------
# Decimal coercion (matches b4_flags._dec) and numeric helpers
# ---------------------------------------------------------------------------


def dec(value: Any) -> Decimal | None:
    """``Decimal(str(value))`` or None when the value is absent / unparseable."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def daily_returns(values: Sequence[float]) -> list[float]:
    """Simple daily returns from the exported NAV points (no external flows on these runs)."""
    out: list[float] = []
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        out.append(cur / prev - 1.0 if prev > 0 else float("nan"))
    return out


def cagr_from_returns(returns: Sequence[float], days: float = float(WINDOW_DAYS)) -> float:
    """Geometric annualised return in %/yr from simple daily returns (log1p sum)."""
    total = math.fsum(math.log1p(r) for r in returns)
    return (math.exp(total * ANNUALISATION_DAYS / days) - 1.0) * 100.0


def nnz(returns: Sequence[float], tol: float = 1e-12) -> int:
    """Days on which the NAV moved. NOT a measure of exposure (prespec section C.4)."""
    return sum(1 for r in returns if abs(r) > tol)


def ols_beta(strategy: Sequence[float], benchmark: Sequence[float]) -> float | None:
    """Slope through the origin of the config's daily returns on the benchmark's. Descriptive."""
    denom = math.fsum(b * b for b in benchmark)
    if denom <= 0:
        return None
    return math.fsum(s * b for s, b in zip(strategy, benchmark, strict=True)) / denom


def cycles_of(entry: dict[str, Any], segment: str = "all") -> int | None:
    """``total_trades - liquidation[segment].positions`` (prespec section C.1)."""
    metrics = entry.get(segment)
    liq = (entry.get("liquidation") or {}).get(segment)
    if not isinstance(metrics, dict) or not isinstance(liq, dict):
        return None
    total = metrics.get("total_trades")
    positions = liq.get("positions")
    if total is None or positions is None:
        return None
    return int(total) - int(positions)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def write_json(path: Path, payload: Any) -> str:
    """Write pretty JSON (directories created) and return the sha256 of its canonical form."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
