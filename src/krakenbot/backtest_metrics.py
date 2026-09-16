"""Shared backtest metrics (chantier C1, post-audit B4) — one measurement system for both
backtest engines and the benchmarks.

Contract (``METRICS_VERSION = 2``), see ``skills/backtest.md`` § Métriques:

* **Daily resampling** (UTC). Grid instants ``t_k``: ``start``, every midnight strictly between
  ``start`` and ``end``, then ``end`` (both edges kept even when they are not midnights; a
  partial edge counts as one daily step). ``NAV(t_k)`` = last equity point stamped ``<= t_k``
  (forward-fill). The **anchor** ``(start, starting_balance)`` is authoritative: a data point
  stamped at ``start`` never overrides it. Between data points sharing a timestamp the last one
  wins (the grid engine's post-liquidation point). Consistent with period-end stamped candles
  (B4.1): the point stamped ``D 00:00`` is the close of day ``D-1``.
* **External flows** (deposits > 0, withdrawals < 0) are bucketed by the same rule (sum over
  ``(t_{k-1}, t_k]``; a flow stamped exactly ``start`` is initial capital: it is added to the
  anchor NAV and earns no return) with the end-of-period convention
  ``r_k = (E_k - F_k - E_{k-1}) / E_{k-1}`` — exact for
  the fixed-DCA benchmark (deposit at the close, converted at that close). ``E_{k-1} == 0`` makes
  the return **undefined** (skipped, never 0).
* **Performance index** ``I_0 = 1`` at the anchor, ``I_k = I_{k-1} * (1 + r_k)`` (an undefined
  return leaves it unchanged): drawdown and Calmar read the index, so a deposit can never mask a
  drawdown. Without flows ``I`` is proportional to the NAV.
* **Sharpe** ``mean(r) / std(r, ddof=1) * sqrt(365)``; ``None`` with fewer than 2 returns or a
  zero standard deviation (never a fake 0). **Sortino** ``mean(r) / sqrt(sum(min(r, 0)^2) / N)
  * sqrt(365)`` (MAR 0, N = all returns); ``None`` without any negative return.
* **Max drawdown**: relative to the running peak (anchor included), on the daily index
  (``max_drawdown_pct_daily`` — the selection / benchmark figure) and on the raw engine
  resolution — the anchor followed by every point stamped in ``[start, end]``
  (``max_drawdown_pct_engine`` — diagnostic only, never a cross-family criterion).
  Neither captures intrabar excursions (wicks): a true intrabar MaxDD cannot be rebuilt.
* **Calmar** = geometric CAGR (%) of the index / ``max_drawdown_pct_daily``; ``None`` when the
  drawdown is 0 or the span is shorter than one day (a total loss gives CAGR -100 %, Calmar -1).
* The identity ``sum(pnl_net_trade) == net_pnl`` holds on a **reconciled** run: terminal
  inventory 0, ``pf_excluded_trades == 0`` and no inventory divergence (the B4.3 flag rule); an
  open lot at the end or a fill booked without a trade breaks it by construction.
* **Profit factor net of both legs**: ``pnl_net_trade = pnl - buy_fee_alloc`` per SELL leg
  (``pnl`` is already net of the sell fee, ``buy_fee_alloc`` is the buy fee of the closed lot).
  A leg with an unknown cost basis (``pnl is None``) is **excluded** and counted in
  ``pf_excluded_trades`` (the PF is then flagged incomplete); a known ``pnl`` without an
  allocated fee (hand-built fixtures only, never the engines) is taken at fee 0.
  ``profit_factor`` = ``gross_profit_net / gross_loss_net`` when the losses are > 0, else
  ``None`` — disambiguated by the exported sums (gains > 0 and losses = 0 -> infinite; both 0 ->
  undefined 0/0).

Pure Python (Decimal in, float / None out); no import from ``scripts/`` (B3 rule).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import math
from typing import Any

METRICS_VERSION = 2
ANNUALISATION_DAYS = 365
_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class EquityPoint:
    """One mark-to-market observation of the engine (at the close of a processed candle)."""

    timestamp: datetime
    equity: Decimal
    cash: Decimal | None = None
    inventory_qty: Decimal | None = None
    mark_price: Decimal | None = None


@dataclass(frozen=True)
class ExternalFlow:
    """Cash entering (> 0) or leaving (< 0) the portfolio at ``timestamp`` (end of period)."""

    timestamp: datetime
    amount: Decimal


@dataclass(frozen=True)
class TradeLeg:
    """A fill as seen by the profit-factor calculation (``pnl`` is set on SELL legs only)."""

    side: str
    timestamp: datetime
    amount_crypto: Decimal
    fee: Decimal
    pnl: Decimal | None = None
    buy_fee_alloc: Decimal | None = None


@dataclass(frozen=True)
class DailySeries:
    """Daily grid ``timestamps`` with the NAV, the flows booked per bucket and the index."""

    timestamps: tuple[datetime, ...]
    nav: tuple[Decimal, ...]
    flows: tuple[Decimal, ...]
    returns: tuple[Decimal | None, ...]  # returns[0] is always None (anchor)
    index: tuple[Decimal, ...]

    @property
    def defined_returns(self) -> list[float]:
        return [float(r) for r in self.returns if r is not None]

    def to_dict(self) -> dict[str, Any]:
        """Compact export (``equity_daily`` of the campaign results): values at the grid instants
        — ``values[0]`` at ``start``, ``values[-1]`` at ``end``, the others at each UTC midnight
        strictly between."""
        return {
            "start": self.timestamps[0].isoformat(),
            "end": self.timestamps[-1].isoformat(),
            "values": [float(v) for v in self.nav],
        }


class MetricsVersionError(ValueError):
    """A results entry was produced under another metrics contract (or none, pre-C1)."""


# ---------------------------------------------------------------------------
# Daily resampling
# ---------------------------------------------------------------------------


def daily_grid(start: datetime, end: datetime) -> list[datetime]:
    """``start``, every UTC midnight strictly inside ``(start, end)``, then ``end``."""
    if end < start:
        raise ValueError(f"end {end.isoformat()} before start {start.isoformat()}")
    grid = [start]
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if midnight <= start:
        midnight += timedelta(days=1)
    while midnight < end:
        grid.append(midnight)
        midnight += timedelta(days=1)
    if end > start:
        grid.append(end)
    return grid


def resample_daily(
    points: Iterable[EquityPoint],
    *,
    start: datetime,
    end: datetime,
    starting_balance: Decimal,
    flows: Iterable[ExternalFlow] = (),
) -> DailySeries:
    """Daily NAV / flows / flow-adjusted returns / performance index (see module docstring)."""
    grid = daily_grid(start, end)
    ordered = sorted(points, key=lambda p: p.timestamp)  # stable: same stamp -> last wins
    flow_list = sorted(flows, key=lambda f: f.timestamp)
    for f in flow_list:
        if f.timestamp < start:
            raise ValueError(f"flow at {f.timestamp.isoformat()} before start")
        if f.timestamp > end:
            raise ValueError(f"flow at {f.timestamp.isoformat()} after end")

    nav: list[Decimal] = []
    bucket_flows: list[Decimal] = []
    pi = 0  # points consumed
    fi = 0  # flows consumed
    last: Decimal | None = None
    for k, t in enumerate(grid):
        while pi < len(ordered) and ordered[pi].timestamp <= t:
            if k > 0:  # the anchor is authoritative: points stamped <= start are ignored
                last = ordered[pi].equity
            pi += 1
        flow_sum = _ZERO
        while fi < len(flow_list) and flow_list[fi].timestamp <= t:
            flow_sum += flow_list[fi].amount
            fi += 1
        if k == 0:
            # a flow stamped exactly at start is initial capital: part of the (authoritative)
            # anchor, and the forward-fill starts from that anchor NAV
            last = starting_balance + flow_sum
        assert last is not None
        nav.append(last)
        bucket_flows.append(flow_sum)

    returns: list[Decimal | None] = [None]
    index: list[Decimal] = [_ONE]
    for k in range(1, len(grid)):
        prev = nav[k - 1]
        if prev > 0:
            r = (nav[k] - bucket_flows[k] - prev) / prev
            returns.append(r)
            index.append(index[-1] * (_ONE + r))
        else:
            returns.append(None)
            index.append(index[-1])
    return DailySeries(tuple(grid), tuple(nav), tuple(bucket_flows), tuple(returns), tuple(index))


# ---------------------------------------------------------------------------
# Ratios (pure, on float returns)
# ---------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def sharpe_ratio(returns: Sequence[float]) -> float | None:
    """Annualised Sharpe on daily returns (sample std); ``None`` when undefined."""
    n = len(returns)
    if n < 2:
        return None
    m = _mean(returns)
    var = sum((r - m) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return None
    return m / std * math.sqrt(ANNUALISATION_DAYS)


def sortino_ratio(returns: Sequence[float]) -> float | None:
    """Annualised Sortino (MAR 0, downside deviation over all N); ``None`` when undefined."""
    n = len(returns)
    if n < 2:
        return None
    downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in returns) / n)
    if downside == 0:
        return None
    return _mean(returns) / downside * math.sqrt(ANNUALISATION_DAYS)


def max_drawdown_pct(values: Sequence[Decimal]) -> float:
    """Largest peak-to-trough decline in % of the running peak (0.0 for an empty series)."""
    peak: Decimal | None = None
    worst = _ZERO
    for v in values:
        if peak is None or v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * _HUNDRED
            if dd > worst:
                worst = dd
    return float(worst)


def cagr_pct(index_start: Decimal, index_end: Decimal, days: float) -> float | None:
    """Geometric annualised return in %, ``None`` when the span is < 1 day or the index <= 0."""
    if days < 1 or index_start <= 0 or index_end < 0:
        return None
    return (math.pow(float(index_end / index_start), ANNUALISATION_DAYS / days) - 1.0) * 100.0


def calmar_ratio(cagr: float | None, max_dd_pct: float) -> float | None:
    if cagr is None or max_dd_pct <= 0:
        return None
    return cagr / max_dd_pct


# ---------------------------------------------------------------------------
# Profit factor net of both legs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfitFactorSummary:
    gross_profit_net: Decimal
    gross_loss_net: Decimal  # absolute value
    pf_excluded_trades: int
    net_trade_pnls: tuple[Decimal, ...]

    @property
    def profit_factor(self) -> float | None:
        if self.gross_loss_net > 0:
            return float(self.gross_profit_net / self.gross_loss_net)
        return None


def net_trade_pnls(legs: Iterable[TradeLeg]) -> ProfitFactorSummary:
    """Derived ``pnl_net_trade`` series of the SELL legs (buy fee imputed to the closing leg)."""
    pnls: list[Decimal] = []
    excluded = 0
    for leg in legs:
        if leg.side != "sell":
            continue
        if leg.pnl is None:
            excluded += 1
            continue
        pnls.append(leg.pnl - (leg.buy_fee_alloc if leg.buy_fee_alloc is not None else _ZERO))
    gains = sum((p for p in pnls if p > 0), _ZERO)
    losses = -sum((p for p in pnls if p < 0), _ZERO)
    return ProfitFactorSummary(gains, losses, excluded, tuple(pnls))


def profit_factor_from_sums(
    gross_profit: float | Decimal | None, gross_loss: float | Decimal | None
) -> float | None:
    """Ratio of summed gains / losses: finite, ``inf`` (gains without losses) or ``None`` (0/0
    or sums unavailable). Used by the campaign aggregation (P7 criterion 2)."""
    if gross_profit is None or gross_loss is None:
        return None
    gp, gl = float(gross_profit), float(gross_loss)
    if gl > 0:
        return gp / gl
    if gp > 0:
        return math.inf
    return None


# ---------------------------------------------------------------------------
# Whole-run computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricsResult:
    daily: DailySeries
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_pct_daily: float
    max_drawdown_pct_engine: float
    cagr_pct: float | None
    calmar_ratio: float | None
    profit_factor: float | None
    gross_profit_net: Decimal
    gross_loss_net: Decimal
    pf_excluded_trades: int
    n_daily_returns: int
    net_trade_pnls: tuple[Decimal, ...]


def compute_metrics(
    points: Sequence[EquityPoint],
    legs: Iterable[TradeLeg],
    *,
    start: datetime,
    end: datetime,
    starting_balance: Decimal,
    flows: Iterable[ExternalFlow] = (),
) -> MetricsResult:
    """All C1 metrics of one run from its raw equity points, its fills and its external flows."""
    daily = resample_daily(
        points, start=start, end=end, starting_balance=starting_balance, flows=flows
    )
    returns = daily.defined_returns
    # engine resolution: the anchor, then every observation of the run window (a point stamped
    # at start counts here — the old money max_drawdown counted it too — but not for the daily
    # NAV, where the anchor is authoritative)
    engine_values = [starting_balance] + [
        p.equity for p in sorted(points, key=lambda p: p.timestamp) if start <= p.timestamp <= end
    ]
    days = (daily.timestamps[-1] - daily.timestamps[0]).total_seconds() / 86400
    mdd_daily = max_drawdown_pct(daily.index)
    cagr = cagr_pct(daily.index[0], daily.index[-1], days)
    pf = net_trade_pnls(legs)
    return MetricsResult(
        daily=daily,
        sharpe_ratio=sharpe_ratio(returns),
        sortino_ratio=sortino_ratio(returns),
        max_drawdown_pct_daily=mdd_daily,
        max_drawdown_pct_engine=max_drawdown_pct(engine_values),
        cagr_pct=cagr,
        calmar_ratio=calmar_ratio(cagr, mdd_daily),
        profit_factor=pf.profit_factor,
        gross_profit_net=pf.gross_profit_net,
        gross_loss_net=pf.gross_loss_net,
        pf_excluded_trades=pf.pf_excluded_trades,
        n_daily_returns=len(returns),
        net_trade_pnls=pf.net_trade_pnls,
    )


# ---------------------------------------------------------------------------
# Consumers: aggregation helpers, version guard, formatting
# ---------------------------------------------------------------------------


def mean_available(values: Iterable[float | None]) -> tuple[float | None, int]:
    """Mean over the defined values and their count; ``(None, 0)`` when none is defined."""
    defined = [v for v in values if v is not None and not math.isnan(v)]
    if not defined:
        return None, 0
    return _mean(defined), len(defined)


def entry_metrics_version(entry: Mapping[str, Any]) -> int | None:
    """``metrics_version`` of a results entry (top level, else inside its metric dicts)."""
    version = entry.get("metrics_version")
    if version is None:
        for segment in ("train", "test", "all", "metrics"):
            block = entry.get(segment)
            if isinstance(block, Mapping) and block.get("metrics_version") is not None:
                version = block["metrics_version"]
                break
    return None if version is None else int(version)


def require_metrics_version(
    entries: Mapping[str, Mapping[str, Any]],
    expected: int = METRICS_VERSION,
    *,
    path: str | None = None,
) -> None:
    """Every non-error entry must carry ``metrics_version == expected`` (mixed / pre-C1 files
    are refused: metrics of two contracts must never be aggregated)."""
    for key, entry in entries.items():
        if "error" in entry:
            continue
        found = entry_metrics_version(entry)
        if found != expected:
            where = f" in {path}" if path else ""
            shown = "<absent: pre-C1 file>" if found is None else str(found)
            raise MetricsVersionError(
                f"entry {key}{where} carries metrics_version={shown} but {expected} is required: "
                "metrics of two contracts cannot be mixed (write to a fresh --output)"
            )


def fmt(value: float | int | None, digits: int = 2, *, suffix: str = "") -> str:
    """Display helper: ``n/a`` for None, ``∞`` for +inf, fixed decimals otherwise."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if math.isnan(value):
            return "n/a"
        if math.isinf(value):
            return "∞" if value > 0 else "-∞"
    return f"{value:.{digits}f}{suffix}"
