"""Backtesting framework for KrakenBot strategies.

This module provides tools to test trading strategies on historical data
and calculate performance metrics.

Usage:
    poetry run python scripts/backtest.py --strategy grok_supertrend_4h --pair BTC/USDC \\
        --exchange binance --fees bybit --days 1095 --capital 1000
"""

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import inspect
import json
from pathlib import Path
import re
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import desc, select, text

from krakenbot.backtest_metrics import (
    METRICS_VERSION,
    DailySeries,
    EquityPoint,
    TradeLeg,
    compute_metrics,
    fmt,
)
from krakenbot.config.settings import FEE_MODEL_NAMES, ExchangeFees, Settings, get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import EventBus
from krakenbot.core.logger import get_logger
from krakenbot.indicators.multi_timeframe import INTERVAL_TO_TF, MACD_PARAMS
from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from krakenbot.models.trades import BacktestRun, Trade, TradeStatus
from krakenbot.strategies.base import SignalType, TradingSignal


def _backtest_chunk_days(interval: int) -> int:
    """Choose a conservative chunk size for hypertable reads."""
    if interval >= 10080:
        return 90
    if interval >= 1440:
        return 30
    if interval >= 240:
        return 14
    if interval >= 60:
        return 7
    return 3


async def _load_candles_chunked(
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    start_time: datetime,
    end_time: datetime,
    exchange: str = "kraken",
) -> list[OHLCData]:
    """Load OHLC candles in bounded windows to avoid Timescale lock exhaustion."""
    candles: list[OHLCData] = []
    chunk_days = _backtest_chunk_days(interval)
    window_start = start_time

    while window_start <= end_time:
        window_end = min(window_start + timedelta(days=chunk_days), end_time)

        async with db_manager.read_session() as session:
            # Timescale can choose a generic prepared plan that touches too many
            # chunks; forcing a custom plan keeps backtest reads bounded.
            await session.execute(text("SET LOCAL plan_cache_mode = force_custom_plan"))
            stmt = (
                select(OHLCData)
                .where(OHLCData.pair == pair)
                .where(OHLCData.interval == interval)
                .where(OHLCData.exchange == exchange)
                .where(OHLCData.timestamp >= window_start)
                .where(
                    OHLCData.timestamp <= window_end
                    if window_end == end_time
                    else OHLCData.timestamp < window_end
                )
                .order_by(OHLCData.timestamp.asc())
            )
            result = await session.execute(stmt)
            candles.extend(result.scalars().all())

        if window_end >= end_time:
            break
        window_start = window_end

    return candles


def _override_pair_in_params(
    params: dict[str, Any] | None,
    pair: str,
) -> dict[str, Any]:
    """Return a shallow-copied params dict with 'pair' forced to `pair`.

    Why: strategies.yaml may hardcode `pair: BTC/USDC` in router inner params.
    `BaseStrategy.effective_pair` reads strategy_params["pair"] before
    settings.trading.pair, so the YAML value shadows the backtest pair unless
    we override here. Always inject the pair (even when params is None or empty)
    so the strategy sees a single, consistent source of truth.
    """
    merged = dict(params or {})
    merged["pair"] = pair
    return merged


@dataclass(frozen=True)
class PairCosts:
    """Per-pair spread/slippage override for market fills (fractions, e.g. 0.0002)."""

    spread: Decimal
    slippage: Decimal

    def __post_init__(self) -> None:
        if self.spread < 0 or self.slippage < 0:
            raise ValueError(f"PairCosts must not be negative: {self}")


def load_pair_costs(path: Path) -> dict[str, PairCosts]:
    """Load ``{"BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"}, ...}`` (Decimal(str))."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a JSON object keyed by pair, got {type(raw).__name__}")
    costs: dict[str, PairCosts] = {}
    for pair, entry in raw.items():
        if "/" not in pair:
            raise ValueError(f"{path}: {pair!r} is not a pair (expected BASE/QUOTE)")
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: {pair}: expected an object with spread and slippage")
        if set(entry) != {"spread", "slippage"}:
            raise ValueError(
                f"{path}: {pair}: expected exactly the keys spread and slippage, got "
                f"{sorted(entry)}"
            )
        costs[pair] = PairCosts(
            spread=Decimal(str(entry["spread"])), slippage=Decimal(str(entry["slippage"]))
        )
    return costs


def resolve_fee_model(fee_model: str | ExchangeFees | None) -> tuple[ExchangeFees, str]:
    """Resolve the engine fee model: a ``--fees`` name or an ``ExchangeFees`` instance.

    There is deliberately no default (B4.2): the fee model is independent of the OHLC data
    source (``exchange``) and must be stated explicitly, like ``settings.exchange_name``.
    """
    if fee_model is None:
        raise ValueError(
            "fee_model is required (no silent default): pass one of "
            f"{', '.join(FEE_MODEL_NAMES)} or an ExchangeFees instance — see PROJECT_CONTEXT.md §5"
        )
    if isinstance(fee_model, ExchangeFees):
        return fee_model, "custom"
    if isinstance(fee_model, str):
        return ExchangeFees.from_name(fee_model), fee_model.strip().lower()
    raise TypeError(f"fee_model must be a str or ExchangeFees, got {type(fee_model).__name__}")


_PARAMS_GET_RE = re.compile(r"""params\.get\(\s*["']([A-Za-z0-9_]+)["']""")
_SIMPLE_TYPES = (bool, int, float, str, Decimal)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, _SIMPLE_TYPES) or value is None:
        return value
    return repr(value)


def capture_effective_params(
    strategy: Any,
    passed_params: Mapping[str, Any] | None,
    override: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Machine-readable snapshot of the parameters a strategy instance actually runs with.

    B4.3 GATE B (decision B.2a): the engines resolve router inner-strategy params by class
    name while ``strategies.yaml`` keys them by instance, so most strategies backtest on
    their class defaults. This captures, at runtime, every ``params.get("<name>", …)`` read
    by the strategy's ``__init__`` with its resolved value (the instance attribute of the same
    name when it exists, else the passed value) and its source: ``override`` (P7 sweep),
    ``passed`` (YAML / engine-injected such as ``pair``) or ``class_default``. Never raises.
    """
    passed = dict(passed_params or {})
    override = dict(override or {})
    names: list[str] = []
    try:
        source = inspect.getsource(type(strategy).__init__)
        for name in _PARAMS_GET_RE.findall(source):
            if name not in names:
                names.append(name)
    except (OSError, TypeError):
        pass
    for name in passed:
        if name not in names:
            names.append(name)
    params: dict[str, dict[str, Any]] = {}
    for name in names:
        if hasattr(strategy, name):
            value: Any = _jsonable(getattr(strategy, name))
        elif name in passed:
            value = _jsonable(passed[name])
        else:
            value = None  # read by __init__ under another attribute name: value not exposed
        if name in override:
            origin = "override"
        elif name in passed:
            origin = "passed"
        else:
            origin = "class_default"
        params[name] = {"value": value, "source": origin}
    return {
        "strategy_class": type(strategy).__name__,
        "passed_params": {k: _jsonable(v) for k, v in passed.items()},
        "params": params,
    }


# ---------------------------------------------------------------------------
# C2 (R2): indicator requirements at effective params, pre-registration, candle-based warmup
# ---------------------------------------------------------------------------

#: Analyzer buckets created at MultiTimeframeAnalyzer.__init__ (never lazy): their periods.
_ANALYZER_FIXED_ATR = 14
_ANALYZER_FIXED_RSI = 14
_ANALYZER_FIXED_ADX = 14
_ANALYZER_FIXED_BB = 20
_ANALYZER_REGIME_EMA_SLOW = 50  # get_regime reads the fixed ema_fast(20)/ema_slow(50) pair
#: Backward extension of a calendar warmup window, in multiples of the required history.
_WARMUP_EXTENSION_FACTOR = 3
#: Largest internal gap (missing candles) a warmup history may carry and still be sufficient.
_WARMUP_GAP_TOLERANCE = 1


@dataclass(frozen=True)
class IndicatorRequirement:
    """An indicator a strategy reads on its analyzer, with the parameters it passes (C2, R2).

    ``kind`` ∈ ema | atr | rsi | supertrend | donchian | adx | macd | bb | regime; ``params``
    are the exact values of the strategy's call site (so the lazy key is identical: e.g.
    ``(st_atr_period, float(st_multiplier))`` for SuperTrend). ``candles`` is the readiness
    count of the indicator class (ready ≠ converged: EMA / ATR / RSI / ADX / SuperTrend seed
    on their first ``period`` candles and stay history-dependent afterwards).
    """

    kind: str
    tf: str
    params: tuple[Any, ...] = ()

    @property
    def candles(self) -> int:
        if self.kind in ("ema", "atr", "supertrend"):
            return int(self.params[0])
        if self.kind == "rsi":
            return int(self.params[0]) + 1
        if self.kind == "donchian":
            return max(int(self.params[0]), int(self.params[1]))
        if self.kind == "adx":
            return 2 * _ANALYZER_FIXED_ADX
        if self.kind == "macd":
            # MACD values from candle `slow` on, signal EMA after `signal` of them
            _fast, slow, signal = MACD_PARAMS[self.tf]
            return slow + signal - 1
        if self.kind == "bb":
            return _ANALYZER_FIXED_BB
        if self.kind == "regime":
            return _ANALYZER_REGIME_EMA_SLOW
        raise ValueError(f"unknown indicator kind {self.kind!r}")

    @property
    def lazy(self) -> bool:
        """Created by the analyzer on the first ``get_*`` call (the call returns None)."""
        if self.kind in ("ema", "supertrend", "donchian"):
            return True
        if self.kind == "atr":
            return int(self.params[0]) != _ANALYZER_FIXED_ATR
        if self.kind == "rsi":
            return int(self.params[0]) != _ANALYZER_FIXED_RSI
        return False

    def preregister(self, analyzer: Any) -> None:
        """Create the indicator in the analyzer before any warmup candle flows (no-op if fixed)."""
        if not self.lazy:
            return
        if self.kind == "ema":
            analyzer.get_ema(int(self.params[0]), self.tf)
        elif self.kind == "atr":
            analyzer.get_atr(int(self.params[0]), self.tf)
        elif self.kind == "rsi":
            analyzer.get_rsi(int(self.params[0]), self.tf)
        elif self.kind == "supertrend":
            analyzer.get_supertrend(
                self.tf, atr_period=int(self.params[0]), multiplier=self.params[1]
            )
        elif self.kind == "donchian":
            analyzer.get_donchian(
                self.tf, period_upper=int(self.params[0]), period_lower=int(self.params[1])
            )


def indicator_requirements(strategy_name: str, strategy: Any) -> list[IndicatorRequirement]:
    """Every analyzer read of a strategy, at the parameters the instance actually runs with.

    Built from the instance attributes (not from ``effective_params``, which stringifies
    Decimals and cannot see a parameter stored under another attribute name); the table is
    checked against the strategy sources by ``tests/test_scripts/test_c2_warmup_requirements.py``
    (every ``analyzer.get_*`` call site is covered). ``regime`` stands for ``get_regime(tf)``,
    which reads the analyzer's fixed EMA 20 / 50 of that timeframe.
    """
    R = IndicatorRequirement
    if strategy_name == "grok_supertrend_4h":
        return [
            R("supertrend", "4h", (int(strategy.st_atr_period), float(strategy.st_multiplier))),
            R("atr", "4h", (14,)),
            R("regime", "1d"),
        ]
    if strategy_name == "grok_ema_adx_atr":
        return [
            R("ema", "4h", (int(strategy.ema_fast_period),)),
            R("ema", "4h", (int(strategy.ema_slow_period),)),
            R("adx", "4h"),
            R("atr", "4h", (14,)),
            R("regime", "1d"),
        ]
    if strategy_name == "grok_donchian_breakout_4h":
        return [
            R(
                "donchian",
                "4h",
                (int(strategy.donchian_upper_period), int(strategy.donchian_lower_period)),
            ),
            R("atr", "4h", (14,)),
            R("regime", "1d"),
            R("adx", "1d"),
        ]
    if strategy_name == "grok_adaptive_dca_weekly":
        return [
            R("rsi", "1d", (14,)),
            R("ema", "1d", (200,)),
            R("regime", "1w"),
            R("regime", "1d"),
        ]
    if strategy_name == "grok_grid_atr_adaptive_v4":
        return [
            R("atr", "4h", (int(strategy.atr_period),)),
            R("regime", "1d"),
            R("regime", "1w"),
        ]
    if strategy_name == "gemini_scalping_volatilite":
        return [
            R("atr", "5m", (14,)),
            R("rsi", "5m", (int(strategy.rsi_period),)),
            R("macd", "5m"),
            R("regime", "1h"),
        ]
    if strategy_name == "gemini_retour_moyenne":
        return [
            R("bb", "15m"),
            R("atr", "15m", (14,)),
            R("rsi", "15m", (14,)),
            R("adx", "1h"),
        ]
    if strategy_name == "gemini_suivi_tendance_momentum":
        return [
            R("atr", "4h", (14,)),
            R("ema", "4h", (20,)),
            R("regime", "1d"),
            R("ema", "1d", (50,)),
            R("ema", "1d", (200,)),
            R("adx", "1d"),
        ]
    return []


def preregister_indicators(analyzer: Any, requirements: list[IndicatorRequirement]) -> None:
    """Create every lazy indicator of ``requirements`` before the warmup data flows (C2, R2).

    Pre-C2 the engines registered a hardcoded list (EMA 20/50 4h, SuperTrend (10, 3.0),
    Donchian (20, 10)); a variant swept by P7 — SuperTrend (8, 2.0), Donchian (15, 10) — or
    the DCA's EMA 200 1d was created on its first read after the warmup and stayed silent
    for its whole period (B4 constat, results/C2_replay_report.md).
    """
    for req in requirements:
        req.preregister(analyzer)


def warmup_needs(requirements: list[IndicatorRequirement]) -> dict[str, int]:
    """Candles required per timeframe for every requirement to be ready at ``start``."""
    needs: dict[str, int] = {}
    for req in requirements:
        needs[req.tf] = max(needs.get(req.tf, 0), req.candles)
    return needs


async def load_context_series(
    load_window: Callable[[int, datetime, datetime], Awaitable[list[OHLCData]]],
    load_before: Callable[[int, datetime, int, datetime], Awaitable[list[OHLCData]]],
    *,
    interval: int,
    window_start: datetime,
    start: datetime,
    end: datetime,
    required: int,
) -> tuple[list[OHLCData], dict[str, Any]]:
    """Load one context series with a candle-sized warmup and report what was really loaded.

    Monotone rule (C2, R2): the calendar window ``[window_start, end]`` is loaded as before;
    when fewer than ``required`` candles are stamped ``<= start`` the history is extended
    backwards by count (never reduced) down to a floor of ``required × interval × 3`` before
    ``window_start``. The report states what the indicators will really see: candles loaded
    at or before ``start``, extension, candles missing between the last one and ``start``
    (``stale_by_candles``), the largest gap inside the history — and ``sufficient`` only when
    the count is met, the history reaches ``start`` and no gap exceeds one candle. Nothing is
    ever bridged silently: a hole is reported, never certified.
    """
    candles = await load_window(interval, window_start, end)
    history = [c for c in candles if c.timestamp <= start]
    loaded = len(history)
    extended_by = 0
    if required > loaded:
        floor = window_start - timedelta(minutes=interval * required * _WARMUP_EXTENSION_FACTOR)
        extra = await load_before(interval, window_start, required - loaded, floor)
        candles = extra + candles
        history = extra + history
        extended_by = len(extra)
        loaded += extended_by
    step = timedelta(minutes=interval)
    stamps = [c.timestamp for c in history]
    largest_gap = 0
    for earlier, later in zip(stamps, stamps[1:], strict=False):
        largest_gap = max(largest_gap, int((later - earlier) / step) - 1)
    stale = None if not stamps else max(0, int((start - stamps[-1]) / step) - 1)
    sufficient = loaded >= required and stale == 0 and largest_gap <= _WARMUP_GAP_TOLERANCE
    report = {
        "interval": interval,
        "required": required,
        "loaded": loaded,
        "extended_by": extended_by,
        "stale_by_candles": stale,
        "largest_gap_candles": largest_gap,
        "sufficient": sufficient,
        "first": stamps[0].isoformat() if stamps else None,
        "last": stamps[-1].isoformat() if stamps else None,
    }
    return candles, report


async def _load_candles_before(
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    before: datetime,
    limit: int,
    floor: datetime,
    exchange: str,
) -> list[OHLCData]:
    """The ``limit`` most recent candles stamped in ``[floor, before)``, oldest first (C2, R2)."""
    if limit <= 0:
        return []
    async with db_manager.read_session() as session:
        await session.execute(text("SET LOCAL plan_cache_mode = force_custom_plan"))
        stmt = (
            select(OHLCData)
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == interval)
            .where(OHLCData.exchange == exchange)
            .where(OHLCData.timestamp < before)
            .where(OHLCData.timestamp >= floor)
            .order_by(desc(OHLCData.timestamp))
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
    rows.reverse()
    return rows


@dataclass(frozen=True)
class ReplayEvent:
    """One step of the grok grid replay (C2, R1): a candle with its true interval and role.

    ``exec`` — trading candle (``candle_interval``): the resting grid orders are filled on its
    high/low and the equity is marked at its close (the only role that moves balances);
    ``ctx`` — 1w / 1d context close: the analyzer is updated; ``decision`` — 4h close: the
    analyzer is updated then, when ``decides`` (timestamp >= start), the strategy's
    ``_handle_ohlc`` runs. ``phase`` orders the events of one timestamp: execution first (an
    order created with the information of this close cannot fill on a candle already over),
    then the contexts from the slowest to the 4h decision. Orders created by the decision are
    eligible from the next ``exec`` event only.
    """

    candle: "OHLCData"
    interval: int
    role: str
    phase: int
    decides: bool = False


#: Same-timestamp order of the grok grid replay events (C2, R1).
_GRID_REPLAY_PHASE: dict[str, int] = {"exec": 0, "1w": 1, "1d": 2, "4h": 3}


@dataclass
class BacktestTrade:
    """Record of a simulated trade during backtesting."""

    timestamp: datetime
    side: TradeSide
    price: Decimal
    amount_usdc: Decimal
    amount_crypto: Decimal
    fee: Decimal
    pnl: Decimal | None = None  # Profit/loss (set when closing position)
    regime: str | None = None  # Market regime at trade time
    # Fee audit fields (B4.2): how the fee was billed, for trade-by-trade verification.
    liquidity: str | None = None  # "maker" (resting limit fill) | "taker" (market / liquidation)
    fee_rate: Decimal | None = None  # rate applied (fees.maker or fees.taker)
    fee_base_usdc: Decimal | None = None  # notional the fee was computed on
    reference_price: Decimal | None = None  # price before spread + slippage
    spread_pct: Decimal | None = None
    slippage_pct: Decimal | None = None
    # B4.3: True for the end-of-run market liquidation of terminal inventory (grid engine).
    forced_liquidation: bool = False
    # C1: SELL legs only — buy fee of the lot(s) this sell closes, imputed to the closing leg
    # by the net-of-both-legs profit factor (``pnl`` itself stays net of the sell fee only).
    # None when the cost basis is unknown (grid inventory divergence: ``pnl`` is None too).
    buy_fee_alloc: Decimal | None = None


@dataclass
class BacktestMetrics:
    """Performance metrics from a backtest run."""

    # Basic stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # P&L metrics
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    # B4.3: net P&L with every fee counted once. Signal engine: total_pnl minus the BUY-side
    # fees (every SELL fee is already netted inside its trade's pnl) — equals the cash P&L
    # ending_balance - starting_balance when the run ends flat. Grid engine: the realised cash
    # P&L after the terminal liquidation (== total_pnl - buy fees whenever the lot accounting
    # agrees with the wallet; the difference is the inventory divergence, exposed in the dump).
    net_pnl: Decimal = Decimal("0")
    # Grid engine: P&L realised by the end-of-run market liquidation of the terminal inventory
    # (B4.3). The key name is kept for schema stability (P6/P7 JSON, gold hash, harness).
    unrealized_pnl: Decimal = Decimal("0")

    # Performance ratios (C1: ``None`` = undefined, never a fake 0; see
    # krakenbot.backtest_metrics for the definitions, contract METRICS_VERSION)
    win_rate: float = 0.0  # winning_trades / total_trades
    average_win: Decimal = Decimal("0")
    average_loss: Decimal = Decimal("0")
    # gross_profit_net / gross_loss_net (both legs' fees imputed); None when losses == 0
    profit_factor: float | None = None
    gross_profit_net: Decimal = Decimal("0")
    gross_loss_net: Decimal = Decimal("0")  # absolute value
    pf_excluded_trades: int = 0  # closed lots with an unknown cost basis (PF incomplete)

    # Risk metrics
    max_drawdown: Decimal = Decimal("0")  # Largest peak-to-trough decline (engine resolution)
    max_drawdown_pct_daily: float = 0.0  # relative to the running peak, daily NAV (selection)
    max_drawdown_pct_engine: float = 0.0  # same, at the engine's resolution (diagnostic)
    sharpe_ratio: float | None = None  # daily returns, sample std, sqrt(365)
    sortino_ratio: float | None = None  # daily returns, downside deviation (MAR 0)
    calmar_ratio: float | None = None  # geometric CAGR / max_drawdown_pct_daily
    n_daily_returns: int = 0
    equity_daily: DailySeries | None = None  # daily NAV grid (exported next to the metrics)

    # Position tracking
    starting_balance: Decimal = Decimal("1000")
    ending_balance: Decimal = Decimal("1000")
    total_return_pct: float = 0.0

    # Time metrics
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_days: float = 0.0
    average_holding_time_minutes: float = 0.0  # Average time positions are held

    # Trade history
    trades: list[BacktestTrade] = field(default_factory=list)

    def to_dict(self) -> dict[str, float | int | None]:
        """Scalar metrics, JSON-serialisable — the ``METRICS_VERSION`` 2 contract (C1).

        Ratios are ``None`` when undefined. ``profit_factor`` is disambiguated by the two
        sums (gains > 0 and losses == 0 -> infinite; both 0 -> undefined) and flagged
        incomplete by ``pf_excluded_trades``. The daily equity is deliberately NOT here
        (see ``equity_daily_dict``): this dict feeds the gold hashes and the campaign files.
        """
        return {
            "metrics_version": METRICS_VERSION,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_return_pct": self.total_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct_daily": self.max_drawdown_pct_daily,
            "max_drawdown_pct_engine": self.max_drawdown_pct_engine,
            "profit_factor": self.profit_factor,
            "calmar_ratio": self.calmar_ratio,
            "net_pnl": float(self.net_pnl),
            "total_fees": float(self.total_fees),
            "total_pnl": float(self.total_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "starting_balance": float(self.starting_balance),
            "ending_balance": float(self.ending_balance),
            "duration_days": self.duration_days,
            "average_holding_time_minutes": self.average_holding_time_minutes,
            "gross_profit_net": float(self.gross_profit_net),
            "gross_loss_net": float(self.gross_loss_net),
            "pf_excluded_trades": self.pf_excluded_trades,
            "n_daily_returns": self.n_daily_returns,
        }

    def equity_daily_dict(self) -> dict[str, Any] | None:
        """Daily NAV grid (``{start, end, values}``), stored by the runners next to the
        metrics and at the top level of the ``--trades-out`` dump; None before a run."""
        return self.equity_daily.to_dict() if self.equity_daily is not None else None

    def profit_factor_display(self) -> str:
        """``profit_factor`` for humans: ratio, ∞ (gains without losses), n/a (0/0), with
        the number of excluded lots when the figure is incomplete."""
        if self.profit_factor is not None:
            text = fmt(self.profit_factor)
        elif self.gross_profit_net > 0 and self.gross_loss_net == 0:
            text = "∞"
        else:
            text = "n/a"
        if self.pf_excluded_trades:
            text += f" (incomplete: {self.pf_excluded_trades} lot(s) with unknown cost)"
        return text


def _side_str(side: Any) -> str:
    return str(getattr(side, "value", side)).lower()


def _buy_fee_from_cost_basis(cost_basis: Decimal, maker_rate: Decimal) -> Decimal:
    """Buy fee of a grid lot from its cost basis: a maker buy books ``crypto = (notional -
    fee) / price`` with ``fee = notional * r``, hence ``cost_basis = notional * (1 - r)`` and
    ``fee = cost_basis * r / (1 - r)`` (exact; prorata of a clamped lot by construction)."""
    return cost_basis * maker_rate / (Decimal("1") - maker_rate)


def apply_shared_metrics(
    metrics: BacktestMetrics, equity_curve: list[tuple[datetime, Decimal]]
) -> None:
    """Fill the C1 ratios of ``metrics`` from the raw equity curve and the trade list through
    ``krakenbot.backtest_metrics`` (both engines call this last; the simulation state is never
    touched). Without run dates (unit tests) the equity curve's own span is used; with no
    equity at all only the profit factor is computed and every ratio stays None."""
    legs = [
        TradeLeg(
            side=_side_str(t.side),
            timestamp=t.timestamp,
            amount_crypto=t.amount_crypto,
            fee=t.fee,
            pnl=t.pnl,
            buy_fee_alloc=t.buy_fee_alloc,
        )
        for t in metrics.trades
    ]
    start = metrics.start_time or (equity_curve[0][0] if equity_curve else None)
    end = metrics.end_time or (equity_curve[-1][0] if equity_curve else None)
    if start is None or end is None:
        from krakenbot.backtest_metrics import net_trade_pnls

        pf = net_trade_pnls(legs)
        metrics.profit_factor = pf.profit_factor
        metrics.gross_profit_net = pf.gross_profit_net
        metrics.gross_loss_net = pf.gross_loss_net
        metrics.pf_excluded_trades = pf.pf_excluded_trades
        return
    result = compute_metrics(
        [EquityPoint(timestamp=ts, equity=eq) for ts, eq in equity_curve],
        legs,
        start=start,
        end=end,
        starting_balance=metrics.starting_balance,
    )
    metrics.sharpe_ratio = result.sharpe_ratio
    metrics.sortino_ratio = result.sortino_ratio
    metrics.max_drawdown_pct_daily = result.max_drawdown_pct_daily
    metrics.max_drawdown_pct_engine = result.max_drawdown_pct_engine
    metrics.calmar_ratio = result.calmar_ratio
    metrics.profit_factor = result.profit_factor
    metrics.gross_profit_net = result.gross_profit_net
    metrics.gross_loss_net = result.gross_loss_net
    metrics.pf_excluded_trades = result.pf_excluded_trades
    metrics.n_daily_returns = result.n_daily_returns
    metrics.equity_daily = result.daily


class BacktestEngine:
    """Engine for running strategy backtests on historical data.

    The engine replays historical OHLC data from the database and simulates
    strategy execution without modifying the live bot state.
    """

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        *,
        fee_model: str | ExchangeFees,
        strategy_name: str = "threshold",
        candle_interval: int = 1,
        exchange: str = "kraken",
        starting_capital: float = 1000.0,
        strategy_params_override: dict[str, Any] | None = None,
        pair_costs: Mapping[str, PairCosts] | None = None,
        min_order_usdc: float | Decimal = 1.0,
    ):
        """Initialize backtest engine.

        Args:
            settings: Application settings
            db_manager: Database manager for historical data
            fee_model: Fee model name (``--fees``: bybit | binance | kraken) or an
                ``ExchangeFees`` instance. Required — independent of ``exchange``.
            strategy_name: Name of strategy to backtest
            candle_interval: Candle interval in minutes (default: 1)
            exchange: OHLC data source to filter on (``exchange`` column); it does NOT
                select the fees any more (B4.2)
            starting_capital: Starting balance in USDC
            pair_costs: Optional per-pair spread/slippage overrides applied to market
                fills only; ``None`` keeps the fee model's global values (unchanged).
            min_order_usdc: Smallest BUY notional the simulation places (B4.3 GATE B):
                a sized order below it is skipped, like an exchange ``minOrderAmt``
                rejection. Default 1 = historical behaviour (bit-identical).
            strategy_params_override: Optional dict of params merged on top of
                the strategies.yaml entry for this strategy. Used by the P7
                grid search to inject sweep params without editing the YAML.
                None (default) preserves the existing YAML-only behavior.
        """
        self.settings = settings
        self.db_manager = db_manager
        self.strategy_name = strategy_name
        self.candle_interval = candle_interval
        self.exchange = exchange
        self._params_override = strategy_params_override
        self.logger = get_logger().bind(component="backtest")

        # Fee model (B4.2): explicit, decoupled from the OHLC data source.
        self.fees, self.fee_model_name = resolve_fee_model(fee_model)
        self._pair_costs: dict[str, PairCosts] = dict(pair_costs or {})
        self.min_order_usdc = Decimal(str(min_order_usdc))
        # Runtime snapshot of the strategy's effective parameters (set by run(), B4.3 GATE B).
        self.effective_params: dict[str, Any] | None = None
        # C2 (R2): indicator requirements at effective params, warmup needs (candles per TF)
        # and the per-TF report of what was really loaded (see load_context_series).
        self._requirements: list[IndicatorRequirement] = []
        self._warmup_needs: dict[str, int] = {}
        self.warmup: dict[str, dict[str, Any]] = {}

        # Simulation state
        self.usdc_balance = Decimal(str(starting_capital))
        self.crypto_balance = Decimal("0")
        self.entry_price: Decimal | None = None
        self.in_position = False

        # Metrics tracking
        self.metrics = BacktestMetrics(starting_balance=self.usdc_balance)
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        # C1: same points with cash / inventory / mark price (``--equity-out`` sidecar);
        # equity_curve itself is unchanged (A/B identity).
        self.equity_detail: list[EquityPoint] = []
        self._open_buy_fees = Decimal("0")  # C1: buy fees of the open lot(s), imputed at the sell
        self._current_regime: str | None = None
        self._regime_stats: dict[str, dict] = {}
        self._entry_regime: str | None = None  # single-position mode

        # Strategy instance (will be created during run)
        self.event_bus = EventBus()
        self.strategy = None  # Will be created during run

    def _apply_params_override(self, params: dict[str, Any] | None) -> dict[str, Any] | None:
        """Merge the engine-level ``strategy_params_override`` onto YAML params.

        When ``self._params_override`` is None (default), the YAML params are
        returned unchanged — strictly backward compatible.

        When an override is provided AND the YAML params are None, the override
        becomes the params dict on its own (so a sweep can run even if the
        YAML entry is missing — useful for new strategies under P7).
        """
        if self._params_override is None:
            return params
        if params is None:
            return dict(self._params_override)
        return {**params, **self._params_override}

    def _load_strategy_params(self, strategy_name: str) -> dict[str, Any] | None:
        """Load strategy params from strategies.yaml via settings."""
        if not self.settings.multi_strategy.enabled:
            return self._apply_params_override(None)
        for s in self.settings.multi_strategy.strategies:
            if s.name == strategy_name:
                return self._apply_params_override(s.params)
        return self._apply_params_override(None)

    def _load_inner_strategy_params(self, inner_name: str) -> dict[str, Any] | None:
        """Load params for an inner strategy nested under multi_strategy_router."""
        # We bypass the engine-level override on the router lookup itself,
        # since the router has its own param shape (strategies dict). The
        # override is then applied to the resolved inner params.
        if not self.settings.multi_strategy.enabled:
            return self._apply_params_override(None)
        router_params: dict[str, Any] | None = None
        for s in self.settings.multi_strategy.strategies:
            if s.name == "multi_strategy_router":
                router_params = s.params
                break
        if router_params is None:
            return self._apply_params_override(None)
        strategies = router_params.get("strategies", {})
        inner = strategies.get(inner_name, {})
        return self._apply_params_override(inner.get("params"))

    # Strategies that need specific higher timeframes loaded
    _NEEDS_4H = {
        "gemini_suivi_tendance_momentum",
        "grok_supertrend_4h",
        "grok_ema_adx_atr",
        "grok_donchian_breakout_4h",
    }
    _NEEDS_1D = {
        "gemini_suivi_tendance_momentum",
        "grok_supertrend_4h",
        "grok_ema_adx_atr",
        "grok_adaptive_dca_weekly",
        "grok_donchian_breakout_4h",
    }
    _NEEDS_1W = {
        "gemini_suivi_tendance_momentum",
        "grok_ema_adx_atr",
        "grok_adaptive_dca_weekly",
    }
    _NEEDS_1H = {
        "gemini_scalping_volatilite",
        "gemini_retour_moyenne",
    }
    _NEEDS_15M = {
        "gemini_retour_moyenne",
    }
    # Strategies that check _is_4h / _is_daily in generate_signal()
    _HAS_IS_4H = {
        "grok_supertrend_4h",
        "grok_ema_adx_atr",
        "grok_donchian_breakout_4h",
    }
    _HAS_IS_DAILY = {"grok_adaptive_dca_weekly"}

    async def _load_candles_for_interval(
        self,
        pair: str,
        interval: int,
        start_time: datetime,
        end_time: datetime,
    ) -> list[OHLCData]:
        """Load OHLC candles for a specific interval.

        Args:
            pair: Trading pair.
            interval: Candle interval in minutes (5, 15, 60).
            start_time: Start of period.
            end_time: End of period.

        Returns:
            List of OHLC candles sorted by timestamp.
        """
        return await _load_candles_chunked(
            self.db_manager,
            pair,
            interval,
            start_time,
            end_time,
            exchange=self.exchange,
        )

    async def _load_candles_before(
        self, pair: str, interval: int, before: datetime, limit: int, floor: datetime
    ) -> list[OHLCData]:
        """The ``limit`` candles right before ``before`` (not older than ``floor``), C2 R2."""
        return await _load_candles_before(
            self.db_manager, pair, interval, before, limit, floor, self.exchange
        )

    async def _load_context_series(
        self,
        pair: str,
        tf: str,
        interval: int,
        window_start: datetime,
        start: datetime,
        end: datetime,
    ) -> list[OHLCData]:
        """One context series sized in candles (C2, R2); its report lands in ``self.warmup``."""
        candles, report = await load_context_series(
            lambda i, s, e: self._load_candles_for_interval(pair, i, s, e),
            lambda i, b, n, f: self._load_candles_before(pair, i, b, n, f),
            interval=interval,
            window_start=window_start,
            start=start,
            end=end,
            required=self._warmup_needs.get(tf, 0),
        )
        self.warmup[tf] = report
        return candles

    def warmup_summary(self) -> dict[str, dict[str, Any]]:
        """Per-timeframe warmup report (C2, R2): required / loaded / extended / stale / gaps."""
        return {
            tf: dict(report)
            for tf, report in sorted(self.warmup.items(), key=lambda kv: kv[1]["interval"])
        }

    async def _build_replay_sequence(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
        candles_trading: list[OHLCData],
    ) -> list[tuple[OHLCData, int, bool]]:
        """Build interleaved replay sequence with multi-timeframe warmup.

        Loads 15m and 1h candles (with warmup period before start_time),
        merges them with the trading candles, and sorts chronologically.
        Higher timeframes are processed first on timestamp ties so the
        analyzer is updated before the trigger timeframe generates signals.
        C2 (R2): every context series is sized in candles from the strategy's indicator
        requirements (``load_context_series``: calendar window kept as a floor, backward
        extension by count, per-TF report in ``self.warmup``), and a candle present both as
        warmup and as trading candle (the one stamped exactly ``start``) is fed once.

        Args:
            pair: Trading pair.
            start_time: Start of backtest trading period.
            end_time: End of backtest period.
            candles_trading: Already-loaded trading candles for the period.

        Returns:
            List of (candle, interval, is_tradeable) tuples.
        """
        ci = self.candle_interval  # Trading interval (e.g., 5, 1, 15)
        tf_ci = INTERVAL_TO_TF.get(ci, f"{ci}m")

        # Warmup periods before start_time (calendar floors; extended by candle count, R2)
        warmup_1h = start_time - timedelta(days=3)  # ~72 candles (> 50 warmup)
        warmup_15m = start_time - timedelta(hours=10)  # ~40 candles (> 20 warmup)
        warmup_trading = start_time - timedelta(hours=3)  # ~36 candles (> 20 warmup)
        warmup_4h = start_time - timedelta(days=15)  # ~90 candles
        warmup_1d = start_time - timedelta(days=250)  # ~250 calendar days (holes reported)
        warmup_1w = start_time - timedelta(days=400)  # ~57 candles

        # Load higher timeframe data (full range: warmup + backtest period)
        candles_1h: list[OHLCData] = []
        candles_15m: list[OHLCData] = []
        if self.strategy_name in self._NEEDS_1H:
            candles_1h = await self._load_context_series(
                pair, "1h", 60, warmup_1h, start_time, end_time
            )
        if self.strategy_name in self._NEEDS_15M:
            candles_15m = await self._load_context_series(
                pair, "15m", 15, warmup_15m, start_time, end_time
            )
        candles_warmup = await self._load_context_series(
            pair, tf_ci, ci, warmup_trading, start_time, start_time
        )

        # Load 4h, 1d, 1w if the strategy needs them
        candles_4h: list[OHLCData] = []
        candles_1d: list[OHLCData] = []
        candles_1w: list[OHLCData] = []
        if self.strategy_name in self._NEEDS_4H:
            candles_4h = await self._load_context_series(
                pair, "4h", 240, warmup_4h, start_time, end_time
            )
        if self.strategy_name in self._NEEDS_1D:
            candles_1d = await self._load_context_series(
                pair, "1d", 1440, warmup_1d, start_time, end_time
            )
        if self.strategy_name in self._NEEDS_1W:
            candles_1w = await self._load_context_series(
                pair, "1w", 10080, warmup_1w, start_time, end_time
            )

        self.logger.info(
            "mtf_data_loaded",
            trading_interval=ci,
            candles_1h=len(candles_1h),
            candles_15m=len(candles_15m),
            candles_4h=len(candles_4h),
            candles_1d=len(candles_1d),
            candles_1w=len(candles_1w),
            candles_warmup=len(candles_warmup),
            candles_trading=len(candles_trading),
        )

        # Build sequence
        sequence: list[tuple[OHLCData, int, bool]] = []

        # Trading interval warmup (before start_time) - not tradeable
        for c in candles_warmup:
            sequence.append((c, ci, False))

        # 1h candles - never tradeable (feed analyzer)
        for c in candles_1h:
            sequence.append((c, 60, False))

        # 15m candles - never tradeable (feed analyzer)
        for c in candles_15m:
            sequence.append((c, 15, False))

        # 4h candles — tradeable only for 4h strategies
        is_4h_trigger = self.strategy_name in self._HAS_IS_4H
        for c in candles_4h:
            is_tradeable = is_4h_trigger and c.timestamp >= start_time
            sequence.append((c, 240, is_tradeable))

        # 1d candles — tradeable only for daily strategies
        is_daily_trigger = self.strategy_name in self._HAS_IS_DAILY
        for c in candles_1d:
            is_tradeable = is_daily_trigger and c.timestamp >= start_time
            sequence.append((c, 1440, is_tradeable))

        # 1w candles — never tradeable (feed analyzer only)
        for c in candles_1w:
            sequence.append((c, 10080, False))

        # Trading candles (skip if 4h is the trigger — already added above)
        if not is_4h_trigger and not is_daily_trigger:
            for c in candles_trading:
                sequence.append((c, ci, True))

        # C2 (R2): a candle present twice at the same (timestamp, interval) — the trading
        # candle stamped exactly ``start`` is in the warmup AND in the trading range — is fed
        # once; the tradeable version wins. No-op for the 4h / 1d triggers (their trading
        # candles are never appended).
        merged: dict[tuple[datetime, int], tuple[OHLCData, int, bool]] = {}
        for item in sequence:
            key = (item[0].timestamp, item[1])
            previous = merged.get(key)
            if previous is None or (item[2] and not previous[2]):
                merged[key] = item
        sequence = list(merged.values())

        # Sort: timestamp ASC, then higher timeframes first
        interval_order = {10080: 0, 1440: 1, 240: 2, 60: 3, 15: 4, ci: 5}
        sequence.sort(key=lambda x: (x[0].timestamp, interval_order.get(x[1], 6)))

        return sequence

    async def load_historical_data(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[OHLCData]:
        """Load OHLC data from database for backtesting period.

        Args:
            pair: Trading pair (e.g., "XBT/USDC")
            start_time: Start of backtest period
            end_time: End of backtest period

        Returns:
            List of OHLC candles sorted by timestamp
        """
        self.logger.info(
            "loading_historical_data",
            pair=pair,
            interval=self.candle_interval,
            start=start_time.isoformat(),
            end=end_time.isoformat(),
        )

        async with self.db_manager.session() as session:
            stmt = (
                select(OHLCData)
                .where(OHLCData.pair == pair)
                .where(OHLCData.interval == self.candle_interval)
                .where(OHLCData.exchange == self.exchange)
                .where(OHLCData.timestamp >= start_time)
                .where(OHLCData.timestamp <= end_time)
                .order_by(OHLCData.timestamp.asc())
            )
            result = await session.execute(stmt)
            candles = list(result.scalars().all())

        self.logger.info(
            "historical_data_loaded", candle_count=len(candles), interval=self.candle_interval
        )
        return candles

    def _resolve_fill(self, signal: TradingSignal, candle: OHLCData) -> tuple[Decimal | None, bool]:
        """Resolve fill price using the NEXT candle's OHLC (no look-ahead bias).

        Args:
            signal: Pending signal from previous candle.
            candle: The NEXT candle (N+1) used for fill simulation.

        Returns:
            Tuple of (fill_price, is_limit_fill).
            fill_price is None if a limit order wasn't reached.
        """
        order_type = (signal.metadata or {}).get("order_type", "market")

        if order_type == "limit":
            limit_price = Decimal(
                str(signal.metadata.get("limit_price") or signal.price or candle.open)
            )
            if signal.signal_type == SignalType.BUY:
                if candle.low <= limit_price:
                    return limit_price, True
                return None, True
            else:  # SELL limit
                if candle.high >= limit_price:
                    return limit_price, True
                return None, True
        else:
            # Market order: fill at open of N+1 (spread+slippage added by execute_signal)
            return candle.open, False

    def _costs_for_pair(self, pair: str) -> tuple[Decimal, Decimal]:
        """Spread and slippage for a market fill on ``pair`` (override or model globals)."""
        override = self._pair_costs.get(pair)
        if override is None:
            return self.fees.spread, self.fees.slippage
        return override.spread, override.slippage

    async def execute_signal(
        self, signal: TradingSignal, current_price: Decimal, *, is_limit_fill: bool = False
    ) -> None:
        """Execute a trading signal in the simulation.

        Args:
            signal: Trading signal from strategy
            current_price: Current market price (open of next candle for market, limit price for limit)
            is_limit_fill: If True, skip spread/slippage and use maker fee
        """
        if signal.signal_type == SignalType.HOLD:
            return

        # Realistic trading costs: resting limit fill -> maker, no spread/slippage;
        # market fill -> taker + spread + slippage (per-pair override or model globals).
        if is_limit_fill:
            liquidity = "maker"
            fee_pct = self.fees.maker
            spread_pct = Decimal("0")  # Limit order: no spread
            slippage_pct = Decimal("0")  # Limit order: no slippage
        else:
            liquidity = "taker"
            fee_pct = self.fees.taker
            spread_pct, slippage_pct = self._costs_for_pair(signal.pair)

        # Accumulation strategies buy repeatedly without selling (e.g. DCA)
        is_accumulation = self.strategy_name in [
            "grok_adaptive_dca_weekly",
        ]

        # Grok strategies use on_trade_filled() instead of set_position_state()
        uses_otf = hasattr(self.strategy, "on_trade_filled") and self.strategy_name in [
            "gemini_scalping_volatilite",
            "gemini_retour_moyenne",
            "gemini_suivi_tendance_momentum",
            "grok_supertrend_4h",
            "grok_ema_adx_atr",
            "grok_adaptive_dca_weekly",
            "grok_donchian_breakout_4h",
        ]

        # Override order size from strategy metadata
        if uses_otf and signal.metadata:
            strategy_order_size = signal.metadata.get("order_size_usdc")
            if strategy_order_size is not None:
                order_amount_override = min(self.usdc_balance, Decimal(str(strategy_order_size)))
            else:
                order_amount_override = None
        else:
            order_amount_override = None

        if signal.signal_type == SignalType.BUY and (is_accumulation or not self.in_position):
            # Buy with available USDC
            if order_amount_override is not None:
                order_amount = order_amount_override
            else:
                base_amount = Decimal(str(self.settings.trading.default_order_amount_eur))
                # Apply position_size_multiplier to match runtime sizing
                # (ExecutionEngine._resolve_open_order_notional)
                if signal.metadata:
                    mult = signal.metadata.get("position_size_multiplier")
                    if mult is not None:
                        base_amount *= Decimal(str(mult))
                order_amount = min(self.usdc_balance, base_amount)

            self.logger.debug(
                "backtest_buy_attempt",
                usdc_balance=float(self.usdc_balance),
                order_amount=float(order_amount),
                min_order=float(self.min_order_usdc),
            )

            if order_amount < self.min_order_usdc:  # Minimum order (exchange minOrderAmt)
                self.logger.warning(
                    "backtest_buy_skipped_min_order", order_amount=float(order_amount)
                )
                return

            # Apply spread + slippage to get realistic execution price
            # When buying, we pay the ASK price (higher than mid)
            execution_price = current_price * (Decimal("1") + spread_pct + slippage_pct)

            fee = order_amount * fee_pct
            amount_after_fee = order_amount - fee
            crypto_bought = amount_after_fee / execution_price

            # Update balances
            self.usdc_balance -= order_amount
            self.crypto_balance += crypto_bought
            self.entry_price = execution_price  # Store actual execution price
            self.in_position = True
            self._open_buy_fees += fee  # C1: imputed to the closing sell (accumulation-safe)

            # Update strategy position state for next signal generation
            if uses_otf:
                # Grok strategies: notify via on_trade_filled
                await self.strategy.on_trade_filled(
                    trade_id=f"bt-{len(self.metrics.trades) + 1}",
                    pair=signal.pair,
                    side="buy",
                    amount=crypto_bought,
                    price=execution_price,
                    fee=fee,
                    reference_price=current_price,
                    position_id=None,
                )
            else:
                # Single position mode (legacy)
                # Use current_price (not execution_price) so strategy sees mid-market price
                self.strategy.set_position_state(has_position=True, entry_price=current_price)

            # Record trade with entry regime
            entry_regime = (
                signal.metadata.get("regime") if signal.metadata else None
            ) or self._current_regime
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.BUY,
                price=execution_price,  # Actual execution price with spread+slippage
                amount_usdc=order_amount,
                amount_crypto=crypto_bought,
                fee=fee,
                regime=entry_regime,
                liquidity=liquidity,
                fee_rate=fee_pct,
                fee_base_usdc=order_amount,
                reference_price=current_price,
                spread_pct=spread_pct,
                slippage_pct=slippage_pct,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee

            # Store entry regime for future SELL trade
            self._entry_regime = entry_regime

            self.logger.debug(
                "backtest_buy",
                price=float(current_price),
                amount_usdc=float(order_amount),
                crypto=float(crypto_bought),
            )

        elif signal.signal_type == SignalType.SELL and self.in_position:
            # Apply spread + slippage to get realistic execution price
            # When selling, we receive the BID price (lower than mid)
            execution_price = current_price * (Decimal("1") - spread_pct - slippage_pct)

            if uses_otf:
                # Grok strategies: sell via on_trade_filled
                proceeds = self.crypto_balance * execution_price
                fee = proceeds * fee_pct
                amount_after_fee = proceeds - fee

                cost_basis = (
                    self.entry_price * self.crypto_balance if self.entry_price else Decimal("0")
                )
                pnl = amount_after_fee - cost_basis

                crypto_sold = self.crypto_balance

                await self.strategy.on_trade_filled(
                    trade_id=f"bt-sell-{len(self.metrics.trades) + 1}",
                    pair=signal.pair,
                    side="sell",
                    amount=crypto_sold,
                    price=execution_price,
                    fee=fee,
                    reference_price=current_price,
                    position_id=signal.metadata.get("position_id") if signal.metadata else None,
                )

                self.usdc_balance += amount_after_fee
                self.crypto_balance = Decimal("0")
                self.in_position = False
            else:
                # Single position mode - use global tracking
                proceeds = self.crypto_balance * execution_price
                fee = proceeds * fee_pct
                amount_after_fee = proceeds - fee

                # Calculate P&L
                cost_basis = (
                    self.entry_price * self.crypto_balance if self.entry_price else Decimal("0")
                )
                pnl = amount_after_fee - cost_basis

                # Update balances
                self.usdc_balance += amount_after_fee
                crypto_sold = self.crypto_balance
                self.crypto_balance = Decimal("0")
                self.in_position = False

                # Single position mode
                self.strategy.set_position_state(has_position=False, entry_price=None)

            # Record trade with ENTRY regime (not exit regime)
            sell_regime = self._entry_regime or self._current_regime
            self._entry_regime = None
            buy_fee_alloc = self._open_buy_fees  # C1: the whole position is closed
            self._open_buy_fees = Decimal("0")
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.SELL,
                price=execution_price,  # Actual execution price with spread+slippage
                amount_usdc=amount_after_fee,
                amount_crypto=crypto_sold,
                fee=fee,
                pnl=pnl,
                regime=sell_regime,
                liquidity=liquidity,
                fee_rate=fee_pct,
                fee_base_usdc=proceeds,
                reference_price=current_price,
                spread_pct=spread_pct,
                slippage_pct=slippage_pct,
                buy_fee_alloc=buy_fee_alloc,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee
            self.metrics.total_pnl += pnl

            # Track win/loss
            if pnl > 0:
                self.metrics.winning_trades += 1
            else:
                self.metrics.losing_trades += 1

            # Extract holding time from signal metadata if available
            holding_time_minutes = (
                signal.metadata.get("holding_time_minutes") if signal.metadata else None
            )

            log_data = {
                "price": float(current_price),
                "crypto": float(crypto_sold),
                "pnl": float(pnl),
            }

            if holding_time_minutes is not None:
                log_data["holding_time_minutes"] = holding_time_minutes

            self.logger.debug("backtest_sell", **log_data)

            self.entry_price = None

    def calculate_final_metrics(self) -> None:
        """Calculate final performance metrics after backtest completes."""
        sell_trades = [t for t in self.metrics.trades if t.side == TradeSide.SELL]
        self.metrics.total_trades = len(sell_trades)

        # Accumulation strategies (e.g. DCA) have no sells — count buys instead
        if self.metrics.total_trades == 0 and self.strategy_name in [
            "grok_adaptive_dca_weekly",
        ]:
            self.metrics.total_trades = len(
                [t for t in self.metrics.trades if t.side == TradeSide.BUY]
            )

        if self.metrics.total_trades > 0:
            self.metrics.win_rate = self.metrics.winning_trades / self.metrics.total_trades

        # Calculate average win/loss
        winning_pnls = [t.pnl for t in self.metrics.trades if t.pnl and t.pnl > 0]
        losing_pnls = [t.pnl for t in self.metrics.trades if t.pnl and t.pnl < 0]

        if winning_pnls:
            self.metrics.average_win = sum(winning_pnls, Decimal("0")) / len(winning_pnls)
        if losing_pnls:
            self.metrics.average_loss = sum(losing_pnls, Decimal("0")) / len(losing_pnls)

        # Profit factor: C1, net of both legs, computed with the shared metrics (see below)

        # Net P&L (B4.3): sell fees are already netted inside each trade's pnl (proceeds - fee
        # - cost basis, cost basis = order amount - buy fee): subtract the buy fees once.
        buy_fees = sum(
            (t.fee for t in self.metrics.trades if t.side == TradeSide.BUY), Decimal("0")
        )
        self.metrics.net_pnl = self.metrics.total_pnl - buy_fees

        # Final balance — prefer equity curve (values crypto at last candle close)
        if self.equity_curve:
            self.metrics.ending_balance = self.equity_curve[-1][1]
        else:
            self.metrics.ending_balance = self.usdc_balance
            if self.crypto_balance > 0 and self.metrics.trades:
                self.metrics.ending_balance += self.crypto_balance * self.metrics.trades[-1].price

        # Total return
        if self.metrics.starting_balance > 0:
            self.metrics.total_return_pct = float(
                (
                    (self.metrics.ending_balance - self.metrics.starting_balance)
                    / self.metrics.starting_balance
                )
                * 100
            )

        # Max drawdown calculation
        peak = self.metrics.starting_balance
        max_dd = Decimal("0")

        for _timestamp, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown

        self.metrics.max_drawdown = max_dd  # money, engine resolution (unchanged by C1)

        # Calculate average holding time (for completed trades with timestamps)
        buy_trades = {t.timestamp: t for t in self.metrics.trades if t.side == TradeSide.BUY}
        sell_trades = [t for t in self.metrics.trades if t.side == TradeSide.SELL]

        holding_times = []
        for sell_trade in sell_trades:
            # Find the corresponding buy trade (match by closest timestamp before sell)
            matching_buys = [t for t in buy_trades.values() if t.timestamp < sell_trade.timestamp]
            if matching_buys:
                buy_trade = max(matching_buys, key=lambda x: x.timestamp)
                holding_time = (sell_trade.timestamp - buy_trade.timestamp).total_seconds() / 60
                holding_times.append(holding_time)

        if holding_times:
            self.metrics.average_holding_time_minutes = sum(holding_times) / len(holding_times)

        # C1: Sharpe / Sortino / MaxDD % (daily + engine) / Calmar / net profit factor through
        # the shared module (daily resampling, flow-aware contract METRICS_VERSION).
        apply_shared_metrics(self.metrics, self.equity_curve)

        # Regime breakdown: aggregate P&L per market regime
        regime_stats: dict[str, dict] = {}
        for trade in self.metrics.trades:
            r = trade.regime or "unknown"
            if r not in regime_stats:
                regime_stats[r] = {
                    "trades": 0,
                    "pnl": Decimal("0"),
                    "wins": 0,
                    "losses": 0,
                }
            if trade.pnl is not None:
                regime_stats[r]["trades"] += 1
                regime_stats[r]["pnl"] += trade.pnl
                if trade.pnl > 0:
                    regime_stats[r]["wins"] += 1
                else:
                    regime_stats[r]["losses"] += 1
        self._regime_stats = regime_stats

    async def run(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
    ) -> BacktestMetrics:
        """Run backtest for specified period.

        Args:
            pair: Trading pair to backtest
            start_time: Start of backtest period
            end_time: End of backtest period

        Returns:
            Performance metrics from the backtest
        """
        self.logger.info(
            "backtest_starting",
            pair=pair,
            strategy=self.strategy_name,
            start=start_time.isoformat(),
            end=end_time.isoformat(),
        )

        self.metrics.start_time = start_time
        self.metrics.end_time = end_time
        self.metrics.duration_days = (end_time - start_time).total_seconds() / 86400

        # Load historical data
        candles = await self.load_historical_data(pair, start_time, end_time)

        if len(candles) < 10:
            self.logger.error(
                "insufficient_data",
                candle_count=len(candles),
                minimum_required=10,
            )
            raise ValueError(f"Insufficient data: only {len(candles)} candles available")

        # Initialize strategy
        # Override settings pair with backtest pair
        self.settings.trading.pair = pair

        # ---------------------------------------------------------------
        # Gemini strategies (Phase-1A)
        # ---------------------------------------------------------------
        if self.strategy_name == "gemini_scalping_volatilite":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.gemini_scalping_volatilite import (
                GeminiScalpingVolatilite,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("gemini_scalping_volatilite"), pair
            )
            self.strategy = GeminiScalpingVolatilite(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="scalping_vol",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "gemini_retour_moyenne":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.gemini_retour_moyenne import GeminiRetourMoyenne

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("gemini_retour_moyenne"), pair
            )
            self.strategy = GeminiRetourMoyenne(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="retour_moy",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "gemini_suivi_tendance_momentum":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.gemini_suivi_tendance_momentum import (
                GeminiSuiviTendanceMomentum,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("gemini_suivi_tendance_momentum"), pair
            )
            self.strategy = GeminiSuiviTendanceMomentum(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="tendance_mom",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        # ---------------------------------------------------------------
        # Grok strategies (Phase-1A)
        # ---------------------------------------------------------------
        elif self.strategy_name == "grok_supertrend_4h":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_supertrend_4h import (
                GrokSuperTrend4hRegime,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_supertrend_4h"), pair
            )
            self.strategy = GrokSuperTrend4hRegime(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="supertrend_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "grok_ema_adx_atr":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_ema_adx_atr import GrokEMA27_125_ADX_ATR

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_ema_adx_atr"), pair
            )
            self.strategy = GrokEMA27_125_ADX_ATR(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="ema_cross_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        # ---------------------------------------------------------------
        # New trend-following strategies (Phase-1B)
        # ---------------------------------------------------------------
        elif self.strategy_name == "grok_adaptive_dca_weekly":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_adaptive_dca_weekly import (
                GrokAdaptiveDCAWeekly,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_adaptive_dca_weekly"), pair
            )
            self.strategy = GrokAdaptiveDCAWeekly(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="dca_weekly",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )

        elif self.strategy_name == "grok_donchian_breakout_4h":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_donchian_breakout_4h import (
                GrokDonchianChannelBreakoutV1,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_donchian_breakout_4h"), pair
            )
            self.strategy = GrokDonchianChannelBreakoutV1(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="donchian_breakout_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        else:
            raise ValueError(
                f"Unknown strategy: {self.strategy_name}. "
                f"Available: gemini_scalping_volatilite, gemini_retour_moyenne, "
                f"gemini_suivi_tendance_momentum, "
                f"grok_supertrend_4h, grok_ema_adx_atr, "
                f"grok_adaptive_dca_weekly, grok_donchian_breakout_4h"
            )

        # CRITICAL: Skip DB sync in backtest mode for all strategies
        self.strategy._skip_db_sync = True
        self.effective_params = capture_effective_params(
            self.strategy, strategy_params, self._params_override
        )

        # C2 (R2): pre-register every lazy indicator the strategy reads, at the parameters
        # the instance really runs with, before any warmup candle flows (a lazy indicator
        # created on its first read after the warmup stays silent for its whole period), and
        # size the warmup of each context series in candles from the same requirements.
        bt_analyzer = getattr(self.strategy, "analyzer", None)
        self._requirements = indicator_requirements(self.strategy_name, self.strategy)
        if bt_analyzer is not None:
            preregister_indicators(bt_analyzer, self._requirements)
        self._warmup_needs = warmup_needs(self._requirements)

        # Build replay sequence (with MTF warmup for strategies using MultiTimeframeAnalyzer)
        needs_mtf = self.strategy_name in [
            "gemini_scalping_volatilite",
            "gemini_retour_moyenne",
            "gemini_suivi_tendance_momentum",
            "grok_supertrend_4h",
            "grok_ema_adx_atr",
            "grok_adaptive_dca_weekly",
            "grok_donchian_breakout_4h",
        ]
        if needs_mtf:
            replay_sequence = await self._build_replay_sequence(pair, start_time, end_time, candles)
        else:
            replay_sequence = [(c, self.candle_interval, True) for c in candles]

        tradeable_total = sum(1 for _, _, t in replay_sequence if t)

        # Replay historical data — NEXT-BAR EXECUTION MODEL
        # Signal on candle N → fill at open of candle N+1 (market) or limit price (limit)
        # This eliminates look-ahead bias: we never fill at a price we just analyzed.
        tradeable_idx = 0
        pending: tuple[TradingSignal, str | None] | None = None  # (signal, entry_regime)

        for candle, interval, is_tradeable in replay_sequence:
            # PHASE 1: Execute pending signal from PREVIOUS candle using THIS candle's OHLC
            if is_tradeable and pending:
                pending_signal, entry_regime = pending
                fill_price, is_limit = self._resolve_fill(pending_signal, candle)
                if fill_price is not None:
                    saved_regime = self._current_regime
                    self._current_regime = entry_regime
                    await self.execute_signal(pending_signal, fill_price, is_limit_fill=is_limit)
                    self._current_regime = saved_regime
                else:
                    self.logger.debug(
                        "limit_order_not_filled",
                        timestamp=candle.timestamp,
                        signal=pending_signal.signal_type.value,
                    )
                pending = None

            # PHASE 2: Feed OHLC to strategy (all timeframes)
            ohlc_data = {
                "pair": candle.pair,
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "interval": interval,
                "is_complete": True,
            }

            # Feed the analyzer BEFORE on_ohlc so indicators are up-to-date.
            # Strategies like grok_* don't call analyzer.update() internally.
            bt_analyzer = getattr(self.strategy, "analyzer", None)
            if bt_analyzer is not None:
                bt_analyzer.update(ohlc_data, interval)

            await self.strategy.on_ohlc(ohlc_data)

            # Only trade on tradeable candles (skip warmup + higher TFs)
            if not is_tradeable:
                continue

            tradeable_idx += 1

            # Set timeframe flags for strategies that check them in generate_signal()
            if hasattr(self.strategy, "_is_4h"):
                self.strategy._is_4h = interval == 240
            if hasattr(self.strategy, "_is_daily"):
                self.strategy._is_daily = interval == 1440

            # Simulate tick with closing price for strategy analysis
            tick_data = {
                "pair": candle.pair,
                "timestamp": candle.timestamp,
                "price": candle.close,
                "volume": candle.volume,
                "side": "buy",  # Dummy side for backtest
            }
            await self.strategy.on_tick(tick_data)

            # PHASE 3: Generate signal → defer to NEXT candle
            signal = await self.strategy.generate_signal()

            # Track current regime from analyzer
            bt_analyzer = getattr(self.strategy, "analyzer", None)
            if bt_analyzer:
                last_analysis = getattr(bt_analyzer, "_last_analysis", None)
                if last_analysis:
                    self._current_regime = last_analysis.regime.value

            # Log signals for debugging
            if signal and signal.signal_type.value in ["buy", "sell"]:
                self.logger.info(
                    "backtest_signal",
                    timestamp=candle.timestamp,
                    signal=signal.signal_type.value,
                    reason=signal.reason,
                    price=float(candle.close),
                )

            # Queue signal for next-bar execution (no look-ahead bias)
            if signal:
                pending = (signal, self._current_regime)

            # Track equity curve (mark-to-market at close is fine)
            current_equity = self.usdc_balance
            if self.crypto_balance > 0:
                current_equity += self.crypto_balance * candle.close
            self.equity_curve.append((candle.timestamp, current_equity))
            self.equity_detail.append(
                EquityPoint(
                    timestamp=candle.timestamp,
                    equity=current_equity,
                    cash=self.usdc_balance,
                    inventory_qty=self.crypto_balance,
                    mark_price=candle.close,
                )
            )

            # Log progress every 100 tradeable candles
            if tradeable_idx % 100 == 0:
                self.logger.info(
                    "backtest_progress",
                    processed=tradeable_idx,
                    total=tradeable_total,
                    pct=round(tradeable_idx / tradeable_total * 100, 1),
                )

        # Calculate final metrics
        self.calculate_final_metrics()

        self.logger.info(
            "backtest_completed",
            total_trades=self.metrics.total_trades,
            net_pnl=float(self.metrics.net_pnl),
            win_rate=round(self.metrics.win_rate * 100, 2),
            total_return_pct=round(self.metrics.total_return_pct, 2),
        )

        return self.metrics

    def print_report(self) -> None:
        """Print a formatted backtest report to console."""
        print("\n" + "=" * 80)
        print("BACKTEST REPORT".center(80))
        print("=" * 80)

        print(f"\n{'Strategy:':<30} {self.strategy_name}")
        print(f"{'Period:':<30} {self.metrics.start_time.date()} to {self.metrics.end_time.date()}")
        print(f"{'Duration:':<30} {self.metrics.duration_days:.1f} days")

        print("\n" + "-" * 80)
        print("PERFORMANCE SUMMARY")
        print("-" * 80)

        print(f"{'Starting Balance:':<30} {float(self.metrics.starting_balance):.2f} USDC")
        print(f"{'Ending Balance:':<30} {float(self.metrics.ending_balance):.2f} USDC")
        print(f"{'Total Return:':<30} {self.metrics.total_return_pct:+.2f}%")
        print(f"{'Net P&L:':<30} {float(self.metrics.net_pnl):+.2f} USDC")
        print(f"{'Total Fees Paid:':<30} {float(self.metrics.total_fees):.2f} USDC")

        print("\n" + "-" * 80)
        print("TRADE STATISTICS")
        print("-" * 80)

        print(f"{'Total Trades:':<30} {self.metrics.total_trades}")
        print(f"{'Winning Trades:':<30} {self.metrics.winning_trades}")
        print(f"{'Losing Trades:':<30} {self.metrics.losing_trades}")
        print(f"{'Win Rate:':<30} {self.metrics.win_rate * 100:.2f}%")
        print(f"{'Average Win:':<30} {float(self.metrics.average_win):+.2f} USDC")
        print(f"{'Average Loss:':<30} {float(self.metrics.average_loss):+.2f} USDC")
        print(f"{'Profit Factor (net):':<30} {self.metrics.profit_factor_display()}")

        # Display average holding time if available
        if self.metrics.average_holding_time_minutes > 0:
            hours = int(self.metrics.average_holding_time_minutes // 60)
            minutes = int(self.metrics.average_holding_time_minutes % 60)
            if hours > 0:
                time_str = f"{hours}h {minutes}min"
            else:
                time_str = f"{minutes}min"
            print(
                f"{'Avg Holding Time:':<30} {time_str} ({self.metrics.average_holding_time_minutes:.1f} min)"
            )

        print("\n" + "-" * 80)
        print("RISK METRICS")
        print("-" * 80)

        print(f"{'Max Drawdown:':<30} {float(self.metrics.max_drawdown):.2f} USDC")
        print(f"{'Max Drawdown % (daily):':<30} {self.metrics.max_drawdown_pct_daily:.2f}%")
        print(f"{'Max Drawdown % (engine):':<30} {self.metrics.max_drawdown_pct_engine:.2f}%")
        print(f"{'Sharpe Ratio (daily):':<30} {fmt(self.metrics.sharpe_ratio)}")
        print(f"{'Sortino Ratio (daily):':<30} {fmt(self.metrics.sortino_ratio)}")
        print(f"{'Calmar Ratio:':<30} {fmt(self.metrics.calmar_ratio)}")

        # Regime breakdown
        if self._regime_stats:
            print("\n" + "-" * 80)
            print("REGIME BREAKDOWN")
            print("-" * 80)
            print(f"  {'Regime':<16} {'Trades':>7} {'Win Rate':>10} {'Net P&L':>14}")
            print(f"  {'-' * 16} {'-' * 7} {'-' * 10} {'-' * 14}")

            # Display in canonical order
            regime_order = ["strong_bull", "bull", "neutral", "bear", "strong_bear", "unknown"]
            for regime in regime_order:
                if regime not in self._regime_stats:
                    continue
                stats = self._regime_stats[regime]
                trades = stats["trades"]
                if trades > 0:
                    win_rate = stats["wins"] / trades * 100
                    pnl = float(stats["pnl"])
                    print(
                        f"  {regime.upper():<16} {trades:>7} {win_rate:>9.1f}% {pnl:>+13.2f} USDC"
                    )
                else:
                    print(f"  {regime.upper():<16} {trades:>7} {'N/A':>10} {'0.00':>13} USDC")

        print("\n" + "=" * 80 + "\n")

    async def save_to_database(
        self,
        pair: str,
        run_name: str | None = None,
    ) -> BacktestRun:
        """Save backtest results to database for dashboard visualization.

        Args:
            pair: Trading pair that was backtested.
            run_name: Optional human-readable name. If not provided, generates one.

        Returns:
            The saved BacktestRun instance.
        """
        # Generate run name if not provided
        if run_name is None:
            date_str = self.metrics.start_time.strftime("%Y-%m-%d")
            run_name = f"{self.strategy_name}_{pair}_{date_str}_{self.metrics.duration_days:.0f}d"

        # Create BacktestRun instance
        backtest_run = BacktestRun(
            run_name=run_name,
            strategy=self.strategy_name,
            pair=pair,
            start_time=self.metrics.start_time,
            end_time=self.metrics.end_time,
            starting_balance=self.metrics.starting_balance,
            ending_balance=self.metrics.ending_balance,
            total_trades=self.metrics.total_trades,
            winning_trades=self.metrics.winning_trades,
            losing_trades=self.metrics.losing_trades,
            win_rate=Decimal(str(self.metrics.win_rate)),
            total_pnl=self.metrics.total_pnl,
            total_fees=self.metrics.total_fees,
            net_pnl=self.metrics.net_pnl,
            total_return_pct=Decimal(str(self.metrics.total_return_pct)),
            max_drawdown=self.metrics.max_drawdown,
            max_drawdown_pct=Decimal(str(self.metrics.max_drawdown_pct_daily)),
            sharpe_ratio=_db_ratio(self.metrics.sharpe_ratio),
            sortino_ratio=_db_ratio(self.metrics.sortino_ratio),
            profit_factor=_db_ratio(self.metrics.profit_factor),
            gross_profit_net=self.metrics.gross_profit_net,
            gross_loss_net=self.metrics.gross_loss_net,
            pf_excluded_trades=self.metrics.pf_excluded_trades,
            metrics_version=METRICS_VERSION,
            average_win=self.metrics.average_win,
            average_loss=self.metrics.average_loss,
        )

        # Save to database
        async with self.db_manager.session() as session:
            session.add(backtest_run)
            await session.commit()
            await session.refresh(backtest_run)

            self.logger.info(
                "backtest_saved_to_db",
                backtest_id=str(backtest_run.id),
                run_name=run_name,
            )

        return backtest_run

    async def save_trades_to_database(
        self,
        backtest_run_id: str,
        pair: str,
    ) -> None:
        """Save backtest trades to database (optional, for detailed analysis).

        Args:
            backtest_run_id: ID of the backtest run (for filtering).
            pair: Trading pair.
        """
        async with self.db_manager.session() as session:
            for trade in self.metrics.trades:
                db_trade = Trade(
                    timestamp=trade.timestamp,
                    pair=pair,
                    side=trade.side,
                    amount=trade.amount_crypto,
                    price=trade.price,
                    fee=trade.fee,
                    fee_currency="USDC",
                    strategy=f"backtest_{backtest_run_id}",  # Tag as backtest trade
                    pnl=trade.pnl,
                    status=TradeStatus.FILLED,
                    notes=f"Backtest trade from run {backtest_run_id}",
                )
                session.add(db_trade)

            await session.commit()

            self.logger.info(
                "backtest_trades_saved",
                backtest_id=backtest_run_id,
                trade_count=len(self.metrics.trades),
            )


class GridBacktester:
    """Backtest engine specialized for grid strategies.

    Grid strategies manage multiple simultaneous limit orders.
    Fills are detected by checking candle low/high against all active levels.
    """

    GRID_STRATEGIES = {"grok_grid_atr_adaptive_v4"}

    # Decimal prec-28 running sums drift by ~1e-29 BTC while a real grid lot is ~1e-4 BTC:
    # below this threshold a residual is Decimal dust, not inventory (B4.3 liquidation).
    _INVENTORY_DUST_BTC = Decimal("1e-12")

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        *,
        fee_model: str | ExchangeFees,
        strategy_name: str = "grok_grid_atr_adaptive_v4",
        candle_interval: int = 5,
        exchange: str = "kraken",
        starting_capital: float = 1000.0,
        strategy_params_override: dict[str, Any] | None = None,
        pair_costs: Mapping[str, PairCosts] | None = None,
        min_order_usdc: float | Decimal = 1.0,
    ):
        """Initialize grid backtester.

        ``fee_model`` (required, B4.2) names the fee model (``--fees``) or is an
        ``ExchangeFees`` instance; ``exchange`` only selects the OHLC data source.
        Grid fills are resting limit orders (maker, no spread/slippage). The only
        taker site is the end-of-run MARKET liquidation of the terminal inventory
        (``_force_close_open_positions``, B4.3): taker fee plus spread and slippage on
        the last tradeable close, per-pair override through ``pair_costs`` (same
        ``PairCosts`` mapping as the signal engine), else the fee-model globals.
        ``strategy_params_override`` merges on top of the strategies.yaml entry for
        this grid strategy. None preserves YAML-only behavior. Used by the P7 grid search.
        ``min_order_usdc`` is accepted for runner symmetry only: grid lots are fixed
        (``order_size_usdc``) and a buy is skipped when the balance cannot cover the lot.
        """
        self.settings = settings
        self.db_manager = db_manager
        self.strategy_name = strategy_name
        self.candle_interval = candle_interval
        self.exchange = exchange
        self._params_override = strategy_params_override
        self.logger = get_logger().bind(component="grid_backtest")

        # Fee model (B4.2): explicit, decoupled from the OHLC data source.
        self.fees, self.fee_model_name = resolve_fee_model(fee_model)
        # Per-pair spread/slippage overrides (B4.3): consumed only by the end-of-run market
        # liquidation; grid fills are resting limit orders and never pay them.
        self._pair_costs: dict[str, PairCosts] = dict(pair_costs or {})
        self._pair: str | None = None
        self.min_order_usdc = Decimal(str(min_order_usdc))
        self.effective_params: dict[str, Any] | None = None
        # C2 (R2): see BacktestEngine — requirements, warmup needs (candles) and reports.
        self._requirements: list[IndicatorRequirement] = []
        self._warmup_needs: dict[str, int] = {}
        self.warmup: dict[str, dict[str, Any]] = {}

        # Simulation state
        self.usdc_balance = Decimal(str(starting_capital))
        self.btc_held = Decimal("0")

        # Terminal liquidation state (B4.3): last tradeable close/timestamp seen by run(),
        # inner strategy exposed on the grok path, and liquidation accounting.
        self._last_close: Decimal | None = None
        self._last_timestamp: datetime | None = None
        self._strategy_obj: Any = None
        self.liquidated_positions: int = 0
        self.buy_fees: Decimal = Decimal("0")
        self.net_pnl_lot_basis: Decimal = Decimal("0")
        self.inventory_divergence_btc: Decimal = Decimal("0")
        self.liquidation_dust_btc: Decimal = Decimal("0")
        self.liquidation_residual_proceeds: Decimal = Decimal("0")
        self.liquidation_holding_minutes: list[float] = []
        self._terminal_liquidation_done = False

        # Grid state
        self.active_buy_orders: list[dict[str, Decimal]] = []  # {price, amount_usdc}
        self.active_sell_orders: list[dict[str, Any]] = []  # {price, amount_btc, entry_price}
        # C2 (R1): the inputs the grok grid decision consumes, read on the analyzer right
        # before each 4h decision (proof harness; not exported by to_dict()).
        self.decision_trace: list[dict[str, Any]] = []

        # Grid metrics
        self.pairs_completed: int = 0
        self.grid_profit: Decimal = Decimal("0")
        self.total_fees: Decimal = Decimal("0")
        self.total_orders_placed: int = 0
        self.rebalance_count: int = 0

        # Standard metrics
        self.metrics = BacktestMetrics(starting_balance=self.usdc_balance)
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        # C1: same points with cash / inventory / mark price (``--equity-out`` sidecar);
        # equity_curve itself is unchanged (A/B identity).
        self.equity_detail: list[EquityPoint] = []
        self._open_buy_fees = Decimal("0")  # C1: buy fees of the open lot(s), imputed at the sell

        # EventBus for strategy init
        self.event_bus = EventBus()

        # Strategy params
        self._strategy_bot_id = strategy_name
        self._strategy_params = self._load_grid_strategy_params(strategy_name)

        # Grid config from strategy params
        self.grid_levels = int(self._strategy_params.get("grid_levels", 10))
        self.grid_spacing_pct = Decimal(str(self._strategy_params.get("grid_spacing_pct", 2.0)))
        self.range_size_pct = Decimal(str(self._strategy_params.get("range_size_pct", 20.0)))
        self.rebalance_threshold_pct = Decimal(
            str(self._strategy_params.get("rebalance_threshold_pct", 5.0))
        )
        self.order_amount_usdc = Decimal(str(self._strategy_params.get("order_amount_usdc", 30)))

        # Grid center tracking
        self._grid_center: Decimal | None = None
        self._grid_initialized = False

    def _costs_for_pair(self, pair: str | None) -> tuple[Decimal, Decimal]:
        """Spread and slippage for the market liquidation on ``pair`` (override or globals)."""
        override = self._pair_costs.get(pair) if pair is not None else None
        if override is None:
            return self.fees.spread, self.fees.slippage
        return override.spread, override.slippage

    def _record_equity(self, candle: OHLCData) -> None:
        """Append the mark-to-market equity point and remember the last tradeable close.

        ``_last_close`` / ``_last_timestamp`` feed the end-of-run liquidation (B4.3): on
        both replay paths they are the close of the last tradeable candle at
        ``candle_interval`` — the same price as the last equity point.
        """
        equity = self.usdc_balance + self.btc_held * candle.close
        self.equity_curve.append((candle.timestamp, equity))
        self.equity_detail.append(
            EquityPoint(
                timestamp=candle.timestamp,
                equity=equity,
                cash=self.usdc_balance,
                inventory_qty=self.btc_held,
                mark_price=candle.close,
            )
        )
        self._last_close = candle.close
        self._last_timestamp = candle.timestamp

    def _apply_params_override(self, params: dict[str, Any] | None) -> dict[str, Any] | None:
        """Merge engine-level override (if any) onto YAML params."""
        if self._params_override is None:
            return params
        if params is None:
            return dict(self._params_override)
        return {**params, **self._params_override}

    def _load_strategy_params(self, strategy_name: str) -> dict[str, Any] | None:
        """Load top-level strategy params from settings."""
        if not self.settings.multi_strategy.enabled:
            return self._apply_params_override(None)
        for strategy in self.settings.multi_strategy.strategies:
            if strategy.name == strategy_name:
                self._strategy_bot_id = getattr(strategy, "bot_id", strategy_name)
                return self._apply_params_override(strategy.params or {})
        return self._apply_params_override(None)

    def _load_inner_strategy_entry(self, inner_name: str) -> dict[str, Any] | None:
        """Load an inner router strategy entry from settings (no override applied here)."""
        if not self.settings.multi_strategy.enabled:
            return None
        for strategy in self.settings.multi_strategy.strategies:
            if strategy.name != "multi_strategy_router":
                continue
            strategies = (strategy.params or {}).get("strategies", {})
            entry = strategies.get(inner_name)
            if entry is not None:
                return entry
        return None

    def _load_grid_strategy_params(self, strategy_name: str) -> dict[str, Any]:
        """Resolve params for grid strategies, including router inner strategies."""
        if strategy_name == "grok_grid_atr_adaptive_v4":
            entry = self._load_inner_strategy_entry(strategy_name) or {}
            self._strategy_bot_id = entry.get("bot_id", "grid_atr_v4")
            return self._apply_params_override(entry.get("params") or {}) or {}
        return self._load_strategy_params(strategy_name) or {}

    def _make_ohlc_payload(self, candle: OHLCData, interval: int) -> dict[str, Any]:
        """Build strategy-compatible OHLC payload."""
        return {
            "pair": candle.pair,
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "interval": interval,
            "timeframe": interval,
            "is_complete": True,
        }

    async def _build_grok_grid_replay_sequence(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
        candles_trading: list[OHLCData],
    ) -> list[ReplayEvent]:
        """Build the grok ATR-grid replay: true 4h / 1d / 1w series, 5m execution (C2, R1).

        Pre-C2 the trading candles were tagged 240 and the 4h series stopped at ``start``:
        after the warmup the "4h" indicators were fed with 5-minute bars and the grid decided
        on every one of them. Now the 4h series is loaded over the whole run and carries the
        decisions (at its closes >= ``start``), 1d / 1w feed the analyzer with their true
        interval (unchanged), and the trading candles keep their own interval: fills and
        equity only. Same-timestamp order: ``exec`` (5m) → 1w → 1d → 4h decision.
        ``candle_interval`` must stay below 4h, otherwise the execution series would be the 4h
        series fed twice.
        """
        if self.candle_interval >= 240:
            raise ValueError(
                "grok grid replay: candle_interval must be shorter than 4h (240 minutes) — "
                f"got {self.candle_interval}; decisions run on the 4h series, fills on the "
                "trading candles"
            )
        warmup_4h = start_time - timedelta(days=15)
        warmup_1d = start_time - timedelta(days=250)
        warmup_1w = start_time - timedelta(days=400)

        candles_4h = await self._load_context_series(
            pair, "4h", 240, warmup_4h, start_time, end_time
        )
        candles_1d = await self._load_context_series(
            pair, "1d", 1440, warmup_1d, start_time, end_time
        )
        candles_1w = await self._load_context_series(
            pair, "1w", 10080, warmup_1w, start_time, end_time
        )

        ci = self.candle_interval
        events: list[ReplayEvent] = [
            ReplayEvent(c, ci, "exec", _GRID_REPLAY_PHASE["exec"]) for c in candles_trading
        ]
        events += [ReplayEvent(c, 10080, "ctx", _GRID_REPLAY_PHASE["1w"]) for c in candles_1w]
        events += [ReplayEvent(c, 1440, "ctx", _GRID_REPLAY_PHASE["1d"]) for c in candles_1d]
        events += [
            ReplayEvent(
                c, 240, "decision", _GRID_REPLAY_PHASE["4h"], decides=c.timestamp >= start_time
            )
            for c in candles_4h
        ]
        events.sort(key=lambda e: (e.candle.timestamp, e.phase))
        self.logger.info(
            "grid_replay_sequence_built",
            trading_interval=ci,
            candles_trading=len(candles_trading),
            candles_4h=len(candles_4h),
            decisions=sum(1 for e in events if e.decides),
            candles_1d=len(candles_1d),
            candles_1w=len(candles_1w),
        )
        return events

    async def _create_grok_grid_strategy(self):
        """Instantiate the real ATR-adaptive grid strategy for faithful replay."""
        from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
        from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4

        analyzer = MultiTimeframeAnalyzer()
        strategy = GrokGridATRAdaptiveV4(
            settings=self.settings,
            event_bus=self.event_bus,
            db_manager=self.db_manager,
            bot_id=self._strategy_bot_id,
            strategy_params=self._strategy_params,
            analyzer=analyzer,
        )
        strategy._skip_db_sync = True
        strategy._running = True
        self.effective_params = capture_effective_params(
            strategy, self._strategy_params, self._params_override
        )
        # C2 (R2): the grid had no pre-registration at all — it worked only because its ATR
        # period defaults to the analyzer's fixed 14 bucket and its regimes use fixed EMAs.
        self._requirements = indicator_requirements(self.strategy_name, strategy)
        preregister_indicators(analyzer, self._requirements)
        self._warmup_needs = warmup_needs(self._requirements)
        return strategy, analyzer

    def _get_grok_grid_pending_orders(self, strategy: Any) -> list[dict[str, Any]]:
        """Return pending buy levels plus paired sell targets for open positions."""
        pending_orders: list[dict[str, Any]] = []

        for key, level in strategy._grid_levels.items():
            if level.status != "pending" or level.side != "buy":
                continue
            pending_orders.append(
                {
                    "order_id": key,
                    "side": "buy",
                    "price": level.price,
                    "amount_usdc": level.amount_usdc,
                    "level": level,
                }
            )

        for position in strategy.open_positions:
            pending_orders.append(
                {
                    "order_id": f"sell_pos_{position.position_id}",
                    "side": "sell",
                    "price": position.sell_level,
                    "amount_btc": position.amount_btc,
                    "position_id": position.position_id,
                }
            )

        return pending_orders

    def _get_grok_grid_pending_order_ids(self, strategy: Any) -> set[str]:
        """Return current pending order ids for order-placement accounting."""
        return {order["order_id"] for order in self._get_grok_grid_pending_orders(strategy)}

    def _mark_grok_grid_level_filled(self, strategy: Any, side: str, price: Decimal) -> None:
        """Mark the grid level of a simulated fill as filled — exact key on both sides.

        C2 (R4): the former SELL branch matched ``|level.price - price| < 1`` USD, a second
        price-proximity matcher next to the strategy's; levels are keyed ``f"{side}_{price}"``
        by the strategy itself, so the exact key is the only correct lookup. Status only —
        pending SELL orders are derived from the open lots, never from these levels.
        """
        level = strategy._grid_levels.get(f"{side}_{price}")
        if level is not None:
            level.status = "filled"

    async def _process_grok_grid_buy_fill(
        self, strategy: Any, order: dict[str, Any], candle: OHLCData
    ) -> None:
        """Process a grok ATR-grid BUY fill through the real strategy lifecycle."""
        fill_price = order["price"]
        amount_usdc = order["amount_usdc"]
        if self.usdc_balance < amount_usdc:
            return

        fee = amount_usdc * self.fees.maker
        net_usdc = amount_usdc - fee
        btc_bought = net_usdc / fill_price

        self.usdc_balance -= amount_usdc
        self.btc_held += btc_bought
        self.total_fees += fee
        self._mark_grok_grid_level_filled(strategy, "buy", fill_price)

        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.BUY,
                price=fill_price,
                amount_usdc=amount_usdc,
                amount_crypto=btc_bought,
                fee=fee,
                liquidity="maker",
                fee_rate=self.fees.maker,
                fee_base_usdc=amount_usdc,
                reference_price=fill_price,
                spread_pct=Decimal("0"),
                slippage_pct=Decimal("0"),
            )
        )

        strategy._current_timestamp = candle.timestamp
        await strategy.on_trade_filled(
            trade_id=f"grid-buy-{candle.timestamp.isoformat()}-{fill_price}",
            pair=candle.pair,
            side="buy",
            amount=btc_bought,
            price=fill_price,
            fee=fee,
            reference_price=None,
            position_id=None,
        )
        self.total_orders_placed += 1

    async def _process_grok_grid_sell_fill(
        self, strategy: Any, order: dict[str, Any], candle: OHLCData
    ) -> None:
        """Process a grok ATR-grid SELL fill: validate the designated lot, then settle (C2, R4).

        The lot is looked up by ``position_id`` in the strategy's open positions **before** any
        balance mutation: an unknown id or an inventory shortfall is a skip — nothing moves,
        no trade is booked (pre-C2 the wallet was debited first and the fill then dropped
        silently: an orphan accounting write, dette 15(d)). The quantity sold is the lot's.
        After the settlement the strategy must have closed that very lot (it matches by id
        since C2): anything else is a replay-invariant violation and raises.
        """
        fill_price = order["price"]
        amount_btc = order["amount_btc"]
        position_id = order["position_id"]

        matched_position = next(
            (p for p in strategy.open_positions if p.position_id == position_id), None
        )
        if matched_position is None:
            self.logger.warning(
                "grid_sell_fill_unknown_position_id",
                position_id=position_id,
                price=float(fill_price),
                timestamp=candle.timestamp,
            )
            return
        if matched_position.amount_btc != amount_btc:
            raise RuntimeError(
                f"replay invariant violated: sell order for lot {position_id} carries "
                f"{amount_btc} BTC but the lot holds {matched_position.amount_btc} BTC"
            )
        if self.btc_held < amount_btc:
            self.logger.warning(
                "grid_sell_fill_insufficient_inventory",
                position_id=position_id,
                amount_btc=float(amount_btc),
                btc_held=float(self.btc_held),
                timestamp=candle.timestamp,
            )
            return

        gross_usdc = amount_btc * fill_price
        fee = gross_usdc * self.fees.maker
        net_usdc = gross_usdc - fee
        self.btc_held -= amount_btc
        self.usdc_balance += net_usdc
        self.total_fees += fee
        self._mark_grok_grid_level_filled(strategy, "sell", fill_price)

        cost_basis = matched_position.amount_btc * matched_position.entry_price
        pnl = net_usdc - cost_basis
        self.grid_profit += pnl
        self.metrics.total_pnl += pnl
        self.pairs_completed += 1
        if pnl > 0:
            self.metrics.winning_trades += 1
        else:
            self.metrics.losing_trades += 1

        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.SELL,
                price=fill_price,
                amount_usdc=gross_usdc,
                amount_crypto=amount_btc,
                fee=fee,
                pnl=pnl,
                liquidity="maker",
                fee_rate=self.fees.maker,
                fee_base_usdc=gross_usdc,
                reference_price=fill_price,
                spread_pct=Decimal("0"),
                slippage_pct=Decimal("0"),
                buy_fee_alloc=_buy_fee_from_cost_basis(cost_basis, self.fees.maker),
            )
        )

        strategy._current_timestamp = candle.timestamp
        await strategy.on_trade_filled(
            trade_id=f"grid-sell-{candle.timestamp.isoformat()}-{fill_price}",
            pair=candle.pair,
            side="sell",
            amount=amount_btc,
            price=fill_price,
            fee=fee,
            reference_price=None,
            position_id=position_id,
        )
        if any(p.position_id == position_id for p in strategy.open_positions):
            raise RuntimeError(
                f"replay invariant violated: lot {position_id} is still open after its sell "
                f"fill at {fill_price} ({candle.timestamp.isoformat()})"
            )
        self.total_orders_placed += 1

    def _initialize_grid(self, current_price: Decimal) -> None:
        """Initialize the grid around the current price."""
        half_range = current_price * self.range_size_pct / Decimal("200")
        grid_low = current_price - half_range
        grid_high = current_price + half_range
        self._grid_center = current_price

        self.active_buy_orders.clear()
        self.active_sell_orders.clear()

        for i in range(self.grid_levels):
            ratio = Decimal(str(i)) / Decimal(str(self.grid_levels - 1))
            level_price = grid_low * (grid_high / grid_low) ** ratio
            level_price = level_price.quantize(Decimal("0.1"))

            if level_price < current_price:
                self.active_buy_orders.append(
                    {"price": level_price, "amount_usdc": self.order_amount_usdc}
                )
                self.total_orders_placed += 1
            elif level_price > current_price:
                # Sell orders need BTC — initially empty, they get created from fills
                pass

        self._grid_initialized = True
        self.logger.info(
            "grid_backtest_initialized",
            center=float(current_price),
            buy_levels=len(self.active_buy_orders),
            low=float(grid_low),
            high=float(grid_high),
        )

    def _process_buy_fill(self, order: dict[str, Decimal], candle: OHLCData) -> None:
        """Process a buy order fill."""
        fill_price = order["price"]
        amount_usdc = order["amount_usdc"]

        if self.usdc_balance < amount_usdc:
            return  # Insufficient balance

        fee = amount_usdc * self.fees.maker
        net_usdc = amount_usdc - fee
        btc_bought = net_usdc / fill_price

        self.usdc_balance -= amount_usdc
        self.btc_held += btc_bought
        self.total_fees += fee

        # Record trade
        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.BUY,
                price=fill_price,
                amount_usdc=amount_usdc,
                amount_crypto=btc_bought,
                fee=fee,
                liquidity="maker",
                fee_rate=self.fees.maker,
                fee_base_usdc=amount_usdc,
                reference_price=fill_price,
                spread_pct=Decimal("0"),
                slippage_pct=Decimal("0"),
            )
        )

        # Place paired sell at upper level
        sell_price = fill_price * (Decimal("1") + self.grid_spacing_pct / Decimal("100"))
        sell_price = sell_price.quantize(Decimal("0.1"))

        # Ensure sell price is profitable (covers 2x round-trip fees = 0.64%)
        min_profitable_sell = fill_price * Decimal("1.0064")
        if sell_price < min_profitable_sell:
            sell_price = min_profitable_sell.quantize(Decimal("0.1"))

        self.active_sell_orders.append(
            {
                "price": sell_price,
                "amount_btc": btc_bought,
                "entry_price": fill_price,
            }
        )
        self.total_orders_placed += 2  # buy filled + sell placed

    def _process_sell_fill(self, order: dict[str, Any], candle: OHLCData) -> None:
        """Process a sell order fill."""
        fill_price = order["price"]
        amount_btc = order["amount_btc"]
        entry_price = order["entry_price"]

        if self.btc_held < amount_btc:
            return  # Insufficient BTC

        gross_usdc = amount_btc * fill_price
        fee = gross_usdc * self.fees.maker
        net_usdc = gross_usdc - fee

        self.btc_held -= amount_btc
        self.usdc_balance += net_usdc
        self.total_fees += fee

        # Calculate profit
        cost_basis = amount_btc * entry_price
        pnl = net_usdc - cost_basis
        self.grid_profit += pnl
        self.metrics.total_pnl += pnl
        self.pairs_completed += 1

        if pnl > 0:
            self.metrics.winning_trades += 1
        else:
            self.metrics.losing_trades += 1

        # Record trade
        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.SELL,
                price=fill_price,
                amount_usdc=gross_usdc,
                amount_crypto=amount_btc,
                fee=fee,
                pnl=pnl,
                liquidity="maker",
                fee_rate=self.fees.maker,
                fee_base_usdc=gross_usdc,
                reference_price=fill_price,
                spread_pct=Decimal("0"),
                slippage_pct=Decimal("0"),
                buy_fee_alloc=_buy_fee_from_cost_basis(cost_basis, self.fees.maker),
            )
        )

        # Place paired buy at lower level
        buy_price = fill_price * (Decimal("1") - self.grid_spacing_pct / Decimal("100"))
        buy_price = buy_price.quantize(Decimal("0.1"))
        self.active_buy_orders.append({"price": buy_price, "amount_usdc": self.order_amount_usdc})
        self.total_orders_placed += 1

    def _check_rebalance(self, current_price: Decimal) -> bool:
        """Check and execute rebalance if needed."""
        if self._grid_center is None:
            return False
        deviation_pct = abs(current_price - self._grid_center) / self._grid_center * Decimal("100")
        if deviation_pct > self.rebalance_threshold_pct:
            self._initialize_grid(current_price)
            self.rebalance_count += 1
            return True
        return False

    async def run(self, pair: str, start_time: datetime, end_time: datetime) -> BacktestMetrics:
        """Run grid backtest."""
        self.metrics.start_time = start_time
        self.metrics.end_time = end_time
        self.metrics.duration_days = (end_time - start_time).total_seconds() / 86400

        self.settings.trading.pair = pair
        self._pair = pair

        # Override hardcoded pair in YAML strategy_params so the inner strategy
        # (e.g. grok_grid_atr_adaptive_v4) binds to the backtest pair, not the
        # default BTC/USDC shipped in strategies.yaml.
        self._strategy_params = _override_pair_in_params(self._strategy_params, pair)

        # Load candles
        candles = await self._load_candles(pair, start_time, end_time)
        if len(candles) < 10:
            raise ValueError(f"Insufficient data: only {len(candles)} candles")

        self.logger.info(
            "grid_backtest_started",
            strategy=self.strategy_name,
            pair=pair,
            candles=len(candles),
            period=f"{start_time.date()} to {end_time.date()}",
        )

        if self.strategy_name == "grok_grid_atr_adaptive_v4":
            strategy, analyzer = await self._create_grok_grid_strategy()
            # Expose inner strategy for force-close of unrealized positions at end.
            self._strategy_obj = strategy
            events = await self._build_grok_grid_replay_sequence(
                pair, start_time, end_time, candles
            )
            await self._replay_grok_grid(strategy, analyzer, events)
            self._calculate_final_metrics()
            return self.metrics

        replay_sequence = [(c, self.candle_interval, True) for c in candles]

        # Replay (legacy non-grok grid)
        for candle, _interval, is_tradeable in replay_sequence:
            current_price = candle.close

            if not is_tradeable:
                continue

            # Initialize grid on first tradeable candle
            if not self._grid_initialized:
                self._initialize_grid(current_price)
                continue

            # Check buy fills: candle.low <= buy_price
            filled_buys = []
            remaining_buys = []
            for order in self.active_buy_orders:
                if candle.low <= order["price"]:
                    filled_buys.append(order)
                else:
                    remaining_buys.append(order)
            self.active_buy_orders = remaining_buys

            for order in filled_buys:
                self._process_buy_fill(order, candle)

            # Check sell fills: candle.high >= sell_price
            filled_sells = []
            remaining_sells = []
            for order in self.active_sell_orders:
                if candle.high >= order["price"]:
                    filled_sells.append(order)
                else:
                    remaining_sells.append(order)
            self.active_sell_orders = remaining_sells

            for order in filled_sells:
                self._process_sell_fill(order, candle)

            # Check rebalance
            self._check_rebalance(current_price)

            # Track equity and remember the last tradeable close for the liquidation
            self._record_equity(candle)

        # Calculate final metrics
        self._calculate_final_metrics()

        return self.metrics

    async def _replay_grok_grid(
        self, strategy: Any, analyzer: Any, events: list[ReplayEvent]
    ) -> None:
        """Drive the grok grid over its replay events (C2, R1).

        ``exec``: snapshot the pending orders (buy levels + one sell per open lot), fill the
        touched ones (buys then sells), feed the candle to the analyzer at its own interval,
        update the strategy's price state (``on_ohlc``) and mark the equity — the last exec
        close is the terminal-liquidation reference. ``ctx``: analyzer update only.
        ``decision``: analyzer update, then — from ``start`` on — the strategy decides on the
        4h close (``_handle_ohlc``); warmup 4h candles only feed the analyzer.
        """
        for event in events:
            candle, interval = event.candle, event.interval
            payload = self._make_ohlc_payload(candle, interval)

            if event.role == "exec":
                pending_orders = self._get_grok_grid_pending_orders(strategy)
                filled_buys = [
                    order
                    for order in pending_orders
                    if order["side"] == "buy" and candle.low <= order["price"]
                ]
                filled_sells = [
                    order
                    for order in pending_orders
                    if order["side"] == "sell" and candle.high >= order["price"]
                ]
                for order in filled_buys:
                    await self._process_grok_grid_buy_fill(strategy, order, candle)
                for order in filled_sells:
                    await self._process_grok_grid_sell_fill(strategy, order, candle)
                analyzer.update(payload, interval)
                await strategy.on_ohlc(payload)
                self._record_equity(candle)
                continue

            analyzer.update(payload, interval)
            if event.role != "decision" or not event.decides:
                continue

            self.decision_trace.append(
                {
                    "timestamp": candle.timestamp,
                    "close": candle.close,
                    "atr_4h": analyzer.get_atr(strategy.atr_period, "4h"),
                    "regime_1d": analyzer.get_regime("1d"),
                    "regime_1w": analyzer.get_regime("1w"),
                }
            )
            old_center = strategy._grid_center
            old_spacing = strategy._grid_spacing
            before_ids = self._get_grok_grid_pending_order_ids(strategy)

            await strategy._handle_ohlc(payload)

            after_ids = self._get_grok_grid_pending_order_ids(strategy)
            self.total_orders_placed += len(after_ids - before_ids)
            if old_center is not None and (
                strategy._grid_center != old_center or strategy._grid_spacing != old_spacing
            ):
                self.rebalance_count += 1

    async def _load_candles(
        self, pair: str, start_time: datetime, end_time: datetime
    ) -> list[OHLCData]:
        """Load OHLC candles from database."""
        return await _load_candles_chunked(
            self.db_manager,
            pair,
            self.candle_interval,
            start_time,
            end_time,
            exchange=self.exchange,
        )

    async def _load_candles_for_interval(
        self, pair: str, interval: int, start_time: datetime, end_time: datetime
    ) -> list[OHLCData]:
        """Load OHLC candles for a specific interval."""
        return await _load_candles_chunked(
            self.db_manager,
            pair,
            interval,
            start_time,
            end_time,
            exchange=self.exchange,
        )

    async def _load_candles_before(
        self, pair: str, interval: int, before: datetime, limit: int, floor: datetime
    ) -> list[OHLCData]:
        """The ``limit`` candles right before ``before`` (not older than ``floor``), C2 R2."""
        return await _load_candles_before(
            self.db_manager, pair, interval, before, limit, floor, self.exchange
        )

    async def _load_context_series(
        self,
        pair: str,
        tf: str,
        interval: int,
        window_start: datetime,
        start: datetime,
        end: datetime,
    ) -> list[OHLCData]:
        """One context series sized in candles (C2, R2); its report lands in ``self.warmup``."""
        candles, report = await load_context_series(
            lambda i, s, e: self._load_candles_for_interval(pair, i, s, e),
            lambda i, b, n, f: self._load_candles_before(pair, i, b, n, f),
            interval=interval,
            window_start=window_start,
            start=start,
            end=end,
            required=self._warmup_needs.get(tf, 0),
        )
        self.warmup[tf] = report
        return candles

    def warmup_summary(self) -> dict[str, dict[str, Any]]:
        """Per-timeframe warmup report (C2, R2): required / loaded / extended / stale / gaps."""
        return {
            tf: dict(report)
            for tf, report in sorted(self.warmup.items(), key=lambda kv: kv[1]["interval"])
        }

    def _liquidate_lot(
        self,
        amount_btc: Decimal,
        entry_price: Decimal | None,
        exec_price: Decimal,
        reference_price: Decimal,
        spread_pct: Decimal,
        slippage_pct: Decimal,
        final_ts: datetime,
        entry_time: datetime | None = None,
    ) -> Decimal:
        """Sell ``amount_btc`` at market at the end of the run and book it (B4.3).

        Taker fee on the spread/slippage-adjusted price, balances settled, trade tagged
        ``forced_liquidation``. ``entry_price`` None means BTC held without a known lot
        (inventory divergence): the proceeds are real cash (credited, counted in the
        realised ``net_pnl``) but no lot pnl / win-loss is booked. ``entry_time`` feeds the
        liquidation holding-time statistic. Returns the booked lot pnl (0 when unknown).
        """
        gross_usdc = amount_btc * exec_price
        fee = gross_usdc * self.fees.taker
        net_usdc = gross_usdc - fee
        pnl = None if entry_price is None else net_usdc - amount_btc * entry_price

        self.btc_held -= amount_btc
        self.usdc_balance += net_usdc
        self.total_fees += fee
        if pnl is not None:
            self.metrics.total_pnl += pnl
            self.liquidated_positions += 1
            if pnl > 0:
                self.metrics.winning_trades += 1
            else:
                self.metrics.losing_trades += 1
        else:
            self.liquidation_residual_proceeds += net_usdc
        if entry_time is not None:
            self.liquidation_holding_minutes.append((final_ts - entry_time).total_seconds() / 60)

        self.metrics.trades.append(
            BacktestTrade(
                timestamp=final_ts,
                side=TradeSide.SELL,
                price=exec_price,
                amount_usdc=gross_usdc,
                amount_crypto=amount_btc,
                fee=fee,
                pnl=pnl,
                liquidity="taker",
                fee_rate=self.fees.taker,
                fee_base_usdc=gross_usdc,
                reference_price=reference_price,
                spread_pct=spread_pct,
                slippage_pct=slippage_pct,
                forced_liquidation=True,
                buy_fee_alloc=(
                    None
                    if entry_price is None
                    else _buy_fee_from_cost_basis(amount_btc * entry_price, self.fees.maker)
                ),
            )
        )
        return pnl if pnl is not None else Decimal("0")

    def _force_close_open_positions(self) -> None:
        """Liquidate the terminal inventory at MARKET on the last tradeable close (B4.3).

        Without this, grid metrics suffer survivorship bias: only completed buy→sell
        pairs are recorded (always profitable by design), win_rate is 1.0 and open lots
        that went underwater are never counted. Semantics (brief B4.3 §4a): every open
        lot — legacy ``active_sell_orders`` and the inner grok strategy's
        ``open_positions`` — is sold at ``last_close × (1 − spread − slippage)`` with the
        TAKER fee (per-pair ``pair_costs`` override, else the fee-model globals); balances
        are settled (``btc_held`` → 0, ``usdc_balance`` += net proceeds); each trade is
        tagged ``forced_liquidation``; one final equity point is appended so ending
        balance, return, drawdown and Sharpe all carry the liquidation cost.

        Inventory reconciliation: the strategy closes positions by price proximity while
        the engine debits by position id, so ``sum(lots)`` can diverge from ``btc_held``
        (phantom lot). A lot exceeding the BTC actually held by more than
        ``_INVENTORY_DUST_BTC`` is clamped; BTC held without any lot is liquidated as one
        trade with unknown cost basis (``pnl`` None); |residual| <= dust is written off.
        The signed divergence and the written-off dust are surfaced on the engine.
        Idempotent: the liquidation is booked once per run (the inner strategy still lists
        its positions afterwards, the engine does not notify it).
        """
        if self._terminal_liquidation_done:
            return
        reference_price = self._last_close
        final_ts = self._last_timestamp or self.metrics.end_time
        if reference_price is None or reference_price <= 0 or final_ts is None:
            return  # no tradeable candle replayed: nothing to mark
        self._terminal_liquidation_done = True

        spread_pct, slippage_pct = self._costs_for_pair(self._pair)
        # Exact form mirrored from the signal engine's market sell (verify-fees checks it).
        exec_price = reference_price * (Decimal("1") - spread_pct - slippage_pct)

        lots: list[tuple[Decimal, Decimal, datetime | None]] = [
            (order["amount_btc"], order["entry_price"], order.get("entry_time"))
            for order in self.active_sell_orders
        ]
        inner_strategy = self._strategy_obj
        if inner_strategy is not None and hasattr(inner_strategy, "open_positions"):
            for position in list(inner_strategy.open_positions):
                amount_btc = getattr(position, "amount_btc", None)
                entry_price = getattr(position, "entry_price", None)
                if amount_btc is None or entry_price is None:
                    continue
                lots.append((amount_btc, entry_price, getattr(position, "entry_time", None)))

        self.inventory_divergence_btc = self.btc_held - sum(
            (amount for amount, _, _ in lots), Decimal("0")
        )

        unrealized_total = Decimal("0")
        booked = 0
        for amount_btc, entry_price, entry_time in lots:
            if amount_btc - self.btc_held > self._INVENTORY_DUST_BTC:
                # Phantom lot (strategy closed another lot by proximity): clamp to what is held.
                amount_btc = max(self.btc_held, Decimal("0"))
            if amount_btc <= 0:
                continue
            unrealized_total += self._liquidate_lot(
                amount_btc,
                entry_price,
                exec_price,
                reference_price,
                spread_pct,
                slippage_pct,
                final_ts,
                entry_time,
            )
            booked += 1
        if self.btc_held > self._INVENTORY_DUST_BTC:
            # BTC held without a matching lot: cost basis unknown, proceeds still real.
            self._liquidate_lot(
                self.btc_held,
                None,
                exec_price,
                reference_price,
                spread_pct,
                slippage_pct,
                final_ts,
            )
            booked += 1
        self.liquidation_dust_btc = self.btc_held  # |x| <= dust after the above
        self.btc_held = Decimal("0")
        self.active_sell_orders.clear()

        if booked:
            final_equity = self.usdc_balance + self.btc_held * reference_price
            self.equity_curve.append((final_ts, final_equity))
            self.equity_detail.append(
                EquityPoint(
                    timestamp=final_ts,
                    equity=final_equity,
                    cash=self.usdc_balance,
                    inventory_qty=self.btc_held,
                    mark_price=reference_price,
                )
            )
            self.logger.info(
                "grid_terminal_liquidation",
                positions=self.liquidated_positions,
                trades=booked,
                reference_price=float(reference_price),
                price=float(exec_price),
                pnl=float(unrealized_total),
                dust_btc=float(self.liquidation_dust_btc),
                divergence_btc=float(self.inventory_divergence_btc),
            )
        if abs(self.inventory_divergence_btc) > self._INVENTORY_DUST_BTC:
            self.logger.warning(
                "grid_liquidation_inventory_divergence",
                divergence_btc=float(self.inventory_divergence_btc),
                lots=len(lots),
            )

        self.metrics.unrealized_pnl = unrealized_total

    def liquidation_summary(self) -> dict[str, Any]:
        """Terminal-liquidation indicators of the finished run (B4.3), JSON-serialisable.

        Persisted by the campaign runners next to the metrics so the reports can flag any
        run whose inventory diverged (``residual_net_proceeds`` / ``inventory_divergence_btc``
        beyond Decimal dust) or whose realised-cash ``net_pnl`` differs from the lot-basis
        figure. Same content as the ``liquidation`` block of ``dump_trades_json``.
        """
        trades = list(self.metrics.trades)
        tagged = [t for t in trades if t.forced_liquidation]
        first = tagged[0] if tagged else None
        holding = self.liquidation_holding_minutes
        return {
            "buy_fees": _dec(self.buy_fees),
            "sell_fees": _dec(self.total_fees - self.buy_fees),
            "net_pnl_lot_basis": _dec(self.net_pnl_lot_basis),
            "residual_net_proceeds": _dec(self.liquidation_residual_proceeds),
            "avg_holding_minutes": (sum(holding) / len(holding)) if holding else None,
            "positions": self.liquidated_positions,
            "trades": len(tagged),
            "residual_trade_btc": _dec(
                sum((t.amount_crypto for t in tagged if t.pnl is None), Decimal("0"))
            ),
            "dust_written_off_btc": _dec(self.liquidation_dust_btc),
            "inventory_divergence_btc": _dec(self.inventory_divergence_btc),
            "pnl": _dec(self.metrics.unrealized_pnl),
            "fees": _dec(sum((t.fee for t in tagged), Decimal("0"))),
            "gross_usdc": _dec(sum((t.amount_usdc for t in tagged), Decimal("0"))),
            "timestamp": first.timestamp.isoformat() if first else None,
            "reference_price": _dec(first.reference_price) if first else None,
            "price": _dec(first.price) if first else None,
            "spread_pct": _dec(first.spread_pct) if first else None,
            "slippage_pct": _dec(first.slippage_pct) if first else None,
        }

    def _calculate_final_metrics(self) -> None:
        """Calculate final performance metrics."""
        # Liquidate the terminal inventory first so its losses are counted (B4.3).
        self._force_close_open_positions()

        self.metrics.total_trades = self.pairs_completed + self.liquidated_positions
        self.metrics.total_fees = self.total_fees
        # B4.3: every SELL fee (maker fill or taker liquidation) is already inside its trade's
        # pnl (pnl = net proceeds - cost basis, cost basis = amount_usdc - buy fee), so the buy
        # fee is the only fee not yet netted: net_pnl_lot_basis = total_pnl - buy fees. Once the
        # inventory is liquidated the wallet is flat and net_pnl is the REALISED CASH P&L
        # (usdc_balance - starting_balance == ending_balance - starting_balance, by
        # construction); it equals net_pnl_lot_basis whenever the lot accounting agrees with the
        # wallet — the difference, if any, is the inventory divergence (residual proceeds with
        # unknown cost basis, or a clamped phantom lot) and is exposed in the dump.
        self.buy_fees = sum(
            (t.fee for t in self.metrics.trades if t.side == TradeSide.BUY), Decimal("0")
        )
        self.net_pnl_lot_basis = self.metrics.total_pnl - self.buy_fees
        if self._terminal_liquidation_done and self.btc_held == 0:
            self.metrics.net_pnl = self.usdc_balance - self.metrics.starting_balance
        else:
            self.metrics.net_pnl = self.net_pnl_lot_basis

        if self.metrics.total_trades > 0:
            self.metrics.win_rate = self.metrics.winning_trades / self.metrics.total_trades

        # Average win/loss
        winning_pnls = [t.pnl for t in self.metrics.trades if t.pnl and t.pnl > 0]
        losing_pnls = [t.pnl for t in self.metrics.trades if t.pnl and t.pnl < 0]

        if winning_pnls:
            self.metrics.average_win = sum(winning_pnls, Decimal("0")) / len(winning_pnls)
        if losing_pnls:
            self.metrics.average_loss = sum(losing_pnls, Decimal("0")) / len(losing_pnls)

        # Profit factor: C1, net of both legs, computed with the shared metrics (see below)

        # Average holding time — match each maker sell to the most recent prior buy. Forced
        # liquidations are excluded (they all share the final timestamp and would each be
        # matched to the run's last buy); their real holding time, from the lot's entry time,
        # is reported in the liquidation block (liquidation_holding_minutes).
        buy_trades_by_ts = {t.timestamp: t for t in self.metrics.trades if t.side == TradeSide.BUY}
        sell_trades = [
            t for t in self.metrics.trades if t.side == TradeSide.SELL and not t.forced_liquidation
        ]
        holding_times: list[float] = []
        for sell_trade in sell_trades:
            matching_buys = [
                t for t in buy_trades_by_ts.values() if t.timestamp < sell_trade.timestamp
            ]
            if matching_buys:
                buy_trade = max(matching_buys, key=lambda x: x.timestamp)
                delta_min = (sell_trade.timestamp - buy_trade.timestamp).total_seconds() / 60
                holding_times.append(delta_min)
        if holding_times:
            self.metrics.average_holding_time_minutes = sum(holding_times) / len(holding_times)

        # Ending balance (include unrealized BTC value)
        if self.equity_curve:
            self.metrics.ending_balance = self.equity_curve[-1][1]
        else:
            self.metrics.ending_balance = self.usdc_balance

        # Total return
        if self.metrics.starting_balance > 0:
            self.metrics.total_return_pct = float(
                (self.metrics.ending_balance - self.metrics.starting_balance)
                / self.metrics.starting_balance
                * 100
            )

        # Max drawdown
        peak = self.metrics.starting_balance
        max_dd = Decimal("0")
        for _ts, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown
        self.metrics.max_drawdown = max_dd  # money, engine resolution (unchanged by C1)

        # C1: Sharpe / Sortino / MaxDD % (daily + engine) / Calmar / net profit factor through
        # the shared module (after the terminal liquidation: its point is in the curve).
        apply_shared_metrics(self.metrics, self.equity_curve)

    def print_report(self) -> None:
        """Print grid-specific backtest report."""
        print("\n" + "=" * 80)
        print("GRID BACKTEST REPORT".center(80))
        print("=" * 80)

        print(f"\n{'Strategy:':<30} {self.strategy_name}")
        if self.metrics.start_time and self.metrics.end_time:
            print(
                f"{'Period:':<30} {self.metrics.start_time.date()} to {self.metrics.end_time.date()}"
            )
        print(f"{'Duration:':<30} {self.metrics.duration_days:.1f} days")

        print("\n" + "-" * 80)
        print("GRID METRICS")
        print("-" * 80)

        print(f"{'Grid Pairs Completed (maker):':<30} {self.pairs_completed}")
        print(f"{'Grid Profit (maker pairs):':<30} {float(self.grid_profit):+.2f} USDC")
        print(f"{'Total Fees:':<30} {float(self.total_fees):.2f} USDC")
        print(f"{'Buy Fees:':<30} {float(self.buy_fees):.2f} USDC")
        print(
            f"{'Sell Fees (incl. liquidation):':<30} "
            f"{float(self.total_fees - self.buy_fees):.2f} USDC"
        )

        print(
            f"{'BTC residual after liquidation:':<30} {float(self.btc_held):.6f} BTC "
            f"(dust {self.liquidation_dust_btc}, divergence {self.inventory_divergence_btc})"
        )

        efficiency = (
            (self.pairs_completed * 2) / self.total_orders_placed * 100
            if self.total_orders_placed > 0
            else 0
        )
        print(f"{'Grid Efficiency:':<30} {efficiency:.1f}%")
        print(f"{'Total Orders Placed:':<30} {self.total_orders_placed}")
        print(f"{'Rebalances:':<30} {self.rebalance_count}")

        liquidations = [t for t in self.metrics.trades if t.forced_liquidation]
        if liquidations:
            first = liquidations[0]
            print(
                f"{'Forced Liquidations:':<30} {self.liquidated_positions} positions "
                f"({len(liquidations)} trades) @ {float(first.price):.2f} "
                f"(close {float(first.reference_price or 0):.2f}, spread {first.spread_pct}, "
                f"slippage {first.slippage_pct}, taker {self.fees.taker})"
            )
            print(f"{'Liquidation P&L:':<30} {float(self.metrics.unrealized_pnl):+.2f} USDC")
            if self.liquidation_holding_minutes:
                avg_h = sum(self.liquidation_holding_minutes) / len(
                    self.liquidation_holding_minutes
                )
                print(f"{'Liquidated lots avg holding:':<30} {avg_h / 1440:.1f} days")
            print(
                f"{'Liquidation Fees:':<30} "
                f"{float(sum((t.fee for t in liquidations), Decimal('0'))):.2f} USDC"
            )
        else:
            print(f"{'Forced Liquidations:':<30} 0 (inventory empty)")

        print("\n" + "-" * 80)
        print("PERFORMANCE SUMMARY")
        print("-" * 80)

        print(f"{'Starting Balance:':<30} {float(self.metrics.starting_balance):.2f} USDC")
        print(f"{'Ending Balance:':<30} {float(self.metrics.ending_balance):.2f} USDC")
        print(f"{'Total Return:':<30} {self.metrics.total_return_pct:+.2f}%")
        print(f"{'Net P&L:':<30} {float(self.metrics.net_pnl):+.2f} USDC")

        print("\n" + "-" * 80)
        print("RISK METRICS")
        print("-" * 80)

        print(f"{'Max Drawdown:':<30} {float(self.metrics.max_drawdown):.2f} USDC")
        print(f"{'Max Drawdown % (daily):':<30} {self.metrics.max_drawdown_pct_daily:.2f}%")
        print(f"{'Max Drawdown % (engine):':<30} {self.metrics.max_drawdown_pct_engine:.2f}%")
        print(f"{'Sharpe Ratio (daily):':<30} {fmt(self.metrics.sharpe_ratio)}")
        print(f"{'Sortino Ratio (daily):':<30} {fmt(self.metrics.sortino_ratio)}")
        print(f"{'Calmar Ratio:':<30} {fmt(self.metrics.calmar_ratio)}")

        print("\n" + "=" * 80 + "\n")

    async def save_to_database(self, pair: str, run_name: str | None = None) -> BacktestRun:
        """Save grid backtest results to database."""
        if run_name is None:
            run_name = f"{self.strategy_name}_{self.metrics.start_time.date()}_to_{self.metrics.end_time.date()}"

        backtest_run = BacktestRun(
            run_name=run_name,
            strategy=self.strategy_name,
            pair=pair,
            start_time=self.metrics.start_time,
            end_time=self.metrics.end_time,
            starting_balance=self.metrics.starting_balance,
            ending_balance=self.metrics.ending_balance,
            total_trades=self.metrics.total_trades,
            winning_trades=self.metrics.winning_trades,
            losing_trades=self.metrics.losing_trades,
            win_rate=Decimal(str(round(self.metrics.win_rate, 4))),
            total_return_pct=Decimal(str(round(self.metrics.total_return_pct, 4))),
            max_drawdown=self.metrics.max_drawdown or Decimal("0"),
            max_drawdown_pct=Decimal(str(round(self.metrics.max_drawdown_pct_daily, 4))),
            total_pnl=self.metrics.total_pnl,
            net_pnl=self.metrics.net_pnl,
            sharpe_ratio=_db_ratio(self.metrics.sharpe_ratio, 4),
            sortino_ratio=_db_ratio(self.metrics.sortino_ratio, 4),
            profit_factor=_db_ratio(self.metrics.profit_factor, 4),
            gross_profit_net=self.metrics.gross_profit_net,
            gross_loss_net=self.metrics.gross_loss_net,
            pf_excluded_trades=self.metrics.pf_excluded_trades,
            metrics_version=METRICS_VERSION,
            average_win=self.metrics.average_win,
            average_loss=self.metrics.average_loss,
            total_fees=self.total_fees,
        )

        async with self.db_manager.session() as session:
            session.add(backtest_run)
            await session.commit()
            await session.refresh(backtest_run)

        return backtest_run


def build_parser() -> argparse.ArgumentParser:
    """CLI parser of scripts/backtest.py (module level so tests can exercise it)."""
    parser = argparse.ArgumentParser(description="Backtest KrakenBot trading strategies")
    parser.add_argument(
        "--strategy",
        type=str,
        default="threshold",
        help="Strategy name to backtest (default: threshold)",
    )
    parser.add_argument(
        "--pair",
        type=str,
        default="XBT/USDC",
        help="Trading pair (default: XBT/USDC)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to backtest (default: 7)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD, default: now)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save backtest results to database (for dashboard visualization)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Custom name for this backtest run",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Candle interval in minutes (default: 1). Use 5 for more realistic trading.",
    )
    parser.add_argument(
        "--cross-validate",
        action="store_true",
        help="Run temporal cross-validation (train 70%% / test 30%%)",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Train set ratio for cross-validation (default: 0.7 = 70%%)",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default="kraken",
        help=(
            "OHLC data source: kraken or binance (default: kraken). Fees are NOT derived "
            "from it — see --fees."
        ),
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD). Overrides --days when set.",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1000.0,
        help="Starting capital in USDC (default: 1000)",
    )

    parser.add_argument(
        "--fees",
        choices=FEE_MODEL_NAMES,
        required=True,
        help=(
            "Fee model applied by the engine (maker/taker/spread/slippage): bybit, binance "
            "(BNB flat 0.075%%, the P6/P7 model) or kraken. Independent of --exchange "
            "(data source). No default on purpose."
        ),
    )
    parser.add_argument(
        "--pair-costs-file",
        type=Path,
        default=None,
        help=(
            "JSON per-pair spread/slippage overrides for market fills, e.g. "
            '{"BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"}}. Applies to the '
            "signal engine's market fills and to the grid end-of-run liquidation."
        ),
    )
    parser.add_argument(
        "--trades-out",
        type=Path,
        default=None,
        help="Write the per-trade fee audit JSON after the run (single run only).",
    )
    parser.add_argument(
        "--equity-out",
        type=Path,
        default=None,
        help="C1: write the engine-resolution equity sidecar (JSONL: timestamp, cash, "
        "inventory, mark price, equity, external flow) of a single run.",
    )
    parser.add_argument(
        "--min-order-usdc",
        type=float,
        default=1.0,
        help=(
            "Smallest BUY notional the signal engine places (exchange minOrderAmt); smaller "
            "sized orders are skipped. Default 1.0 = historical behaviour (B4.3 campaign: 5)."
        ),
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate the CLI arguments (exit 2 on cross-flag violations)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.pair_costs = None
    if args.pair_costs_file is not None:
        try:
            args.pair_costs = load_pair_costs(args.pair_costs_file)
        except (OSError, ValueError) as exc:
            parser.error(f"--pair-costs-file: {exc}")
    if args.equity_out is not None and args.cross_validate:
        parser.error("--equity-out applies to a single run, not to --cross-validate")
    if args.trades_out is not None and args.cross_validate:
        parser.error("--trades-out is a single-run artifact; drop it or drop --cross-validate")
    if args.strategy in GridBacktester.GRID_STRATEGIES:
        if args.cross_validate:
            # C2 (N1): the cross-validate branch builds a BacktestEngine unconditionally and
            # GridBacktester has no such mode — fail fast rather than replay a grid strategy
            # through the signal engine.
            parser.error(
                f"--cross-validate has no grid mode: {args.strategy} would run through the "
                "signal engine (use the P6 / P7 runners for train/test splits)"
            )
        if args.interval >= 240:
            parser.error(
                "--interval must be shorter than 4h for a grid strategy (decisions run on the "
                f"4h series, fills on the trading candles); got {args.interval}"
            )
    return args


def _dec(value: Any) -> str | None:
    return None if value is None else str(value)


def _db_ratio(value: float | None, ndigits: int | None = None) -> Decimal | None:
    """Ratio column of ``BacktestRun``: NULL when the metric is undefined (C1)."""
    if value is None:
        return None
    return Decimal(str(round(value, ndigits) if ndigits is not None else value))


def dump_equity_jsonl(engine: Any, path: Path, *, pair: str) -> int:
    """C1 equity sidecar: one header line, then one line per engine-resolution point
    (timestamp, cash, inventory_qty, mark_price, equity, external_flow — 0 for the engines;
    the field exists for the benchmarks). Mark-to-market at the close of every processed
    tradeable candle (plus the grid's post-liquidation point): intrabar excursions are not
    captured. Returns the number of points written."""
    header = {
        "metrics_version": METRICS_VERSION,
        "engine": type(engine).__name__,
        "strategy": engine.strategy_name,
        "pair": pair,
        "fees": engine.fee_model_name,
        "resolution": "engine",
        "valuation": "mark-to-market at the close of each processed tradeable candle",
    }
    lines = [json.dumps(header, sort_keys=True)]
    for point in engine.equity_detail:
        lines.append(
            json.dumps(
                {
                    "timestamp": point.timestamp.isoformat(),
                    "cash": _dec(point.cash),
                    "inventory_qty": _dec(point.inventory_qty),
                    "mark_price": _dec(point.mark_price),
                    "equity": _dec(point.equity),
                    "external_flow": "0",
                },
                sort_keys=True,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(engine.equity_detail)


def dump_trades_json(
    engine: Any,
    path: Path,
    *,
    pair: str,
    start: datetime,
    end: datetime,
    exchange: str,
    interval: int,
    capital: float,
) -> None:
    """Write the per-trade fee audit JSON (superset of scripts/audit/b4_2_reference_capture
    schema 1: same core keys, plus fee model, rates, overrides and per-trade audit fields).
    All Decimals are serialised with ``str()`` — no rounding. Grid engines additionally
    carry the per-trade ``forced_liquidation`` flag and a top-level ``liquidation`` block
    (B4.3); signal dumps are unchanged."""
    trades = list(engine.metrics.trades)
    is_grid = hasattr(engine, "pairs_completed")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "engine": type(engine).__name__,
        "strategy": engine.strategy_name,
        "pair": pair,
        "exchange": exchange,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "interval": interval,
        "capital": str(Decimal(str(capital))),
        "fees": engine.fee_model_name,
        "fee_rates": {
            "maker": str(engine.fees.maker),
            "taker": str(engine.fees.taker),
            "spread": str(engine.fees.spread),
            "slippage": str(engine.fees.slippage),
        },
        "pair_costs": (
            {
                p: {"spread": str(c.spread), "slippage": str(c.slippage)}
                for p, c in sorted(getattr(engine, "_pair_costs", {}).items())
            }
            or None
        ),
        "metrics": engine.metrics.to_dict(),
        "trades": [
            {
                "n": n,
                "timestamp": trade.timestamp.isoformat(),
                "side": trade.side.value if hasattr(trade.side, "value") else str(trade.side),
                "liquidity": trade.liquidity,
                "price": _dec(trade.price),
                "reference_price": _dec(trade.reference_price),
                "amount_usdc": _dec(trade.amount_usdc),
                "amount_crypto": _dec(trade.amount_crypto),
                "fee": _dec(trade.fee),
                "fee_rate": _dec(trade.fee_rate),
                "fee_base_usdc": _dec(trade.fee_base_usdc),
                "spread_pct": _dec(trade.spread_pct),
                "slippage_pct": _dec(trade.slippage_pct),
                "pnl": _dec(trade.pnl),
                "regime": trade.regime,
                "buy_fee_alloc": _dec(trade.buy_fee_alloc),
                **({"forced_liquidation": trade.forced_liquidation} if is_grid else {}),
            }
            for n, trade in enumerate(trades, start=1)
        ],
    }
    # C1: contract version and the daily NAV grid, outside the harness' schema-1 projection
    payload["metrics_version"] = METRICS_VERSION
    payload["equity_daily"] = engine.metrics.equity_daily_dict()
    # C2 (R2): what each context series really fed the indicators with (candles, gaps).
    payload["warmup"] = engine.warmup_summary()
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
                "buy": sum(1 for t in trades if t.side == TradeSide.BUY),
                "sell": sum(1 for t in trades if t.side == TradeSide.SELL),
                "force_closed": sum(1 for t in trades if t.liquidity == "taker"),
            },
        }
        # B4.3 terminal liquidation block — outside the harness' schema-1 projection.
        payload["liquidation"] = engine.liquidation_summary()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


async def main(argv: list[str] | None = None) -> None:
    """CLI entry point for backtesting."""
    # Load .env here, not at import time: importing this module must not mutate
    # os.environ (tests import it at collection). Explicit project-root path.
    load_dotenv(Path(__file__).parent.parent / ".env")
    args = parse_args(argv)
    fees, _ = resolve_fee_model(args.fees)
    print(
        f"Fee model: {args.fees} (maker {fees.maker} / taker {fees.taker} / "
        f"spread {fees.spread} / slippage {fees.slippage}); data source: {args.exchange}; "
        f"pair costs: {sorted(args.pair_costs) if args.pair_costs else 'none'}"
    )

    # Parse dates
    if args.end_date:
        end_time = datetime.fromisoformat(args.end_date).replace(tzinfo=UTC)
    else:
        end_time = datetime.now(UTC)

    if args.start_date:
        start_time = datetime.fromisoformat(args.start_date).replace(tzinfo=UTC)
    else:
        start_time = end_time - timedelta(days=args.days)

    # Initialize components
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    try:
        if args.cross_validate:
            # Temporal cross-validation: train on first X%, test on remaining
            total_duration = end_time - start_time
            train_duration = total_duration * args.train_ratio
            split_time = start_time + train_duration

            print("\n" + "=" * 80)
            print("TEMPORAL CROSS-VALIDATION".center(80))
            print("=" * 80)
            total_days = int(total_duration.total_seconds() / 86400)
            print(f"\nTotal period: {start_time.date()} to {end_time.date()} ({total_days} days)")
            print(f"Train ratio: {args.train_ratio:.0%}")
            print(f"Split point: {split_time.date()}")
            print(
                f"Train: {start_time.date()} to {split_time.date()} ({int(train_duration.days)} days)"
            )
            print(
                f"Test:  {split_time.date()} to {end_time.date()} ({total_days - int(train_duration.days)} days)"
            )

            # Run TRAIN backtest
            print("\n" + "-" * 80)
            print("TRAIN SET".center(80))
            print("-" * 80)

            train_engine = BacktestEngine(
                settings,
                db_manager,
                strategy_name=args.strategy,
                candle_interval=args.interval,
                exchange=args.exchange,
                starting_capital=args.capital,
                fee_model=args.fees,
                pair_costs=args.pair_costs,
                min_order_usdc=args.min_order_usdc,
            )
            train_metrics = await train_engine.run(args.pair, start_time, split_time)
            train_engine.print_report()

            # Run TEST backtest
            print("\n" + "-" * 80)
            print("TEST SET".center(80))
            print("-" * 80)

            test_engine = BacktestEngine(
                settings,
                db_manager,
                strategy_name=args.strategy,
                candle_interval=args.interval,
                exchange=args.exchange,
                starting_capital=args.capital,
                fee_model=args.fees,
                pair_costs=args.pair_costs,
                min_order_usdc=args.min_order_usdc,
            )
            test_metrics = await test_engine.run(args.pair, split_time, end_time)
            test_engine.print_report()

            # Print comparison
            print("\n" + "=" * 80)
            print("TRAIN vs TEST COMPARISON".center(80))
            print("=" * 80)
            print(f"\n{'Metric':<25} {'Train':<15} {'Test':<15} {'Delta':<15}")
            print("-" * 70)

            # Total return
            train_ret = train_metrics.total_return_pct
            test_ret = test_metrics.total_return_pct
            print(
                f"{'Total Return %':<25} {train_ret:>+.2f}%{'':<8} {test_ret:>+.2f}%{'':<8} {test_ret - train_ret:>+.2f}%"
            )

            # Win rate
            train_wr = train_metrics.win_rate * 100
            test_wr = test_metrics.win_rate * 100
            print(
                f"{'Win Rate %':<25} {train_wr:>.2f}%{'':<9} {test_wr:>.2f}%{'':<9} {test_wr - train_wr:>+.2f}%"
            )

            # Ratios (C1: None = undefined -> n/a, delta only when both are defined)
            for label, attr in (
                ("Profit Factor (net)", "profit_factor"),
                ("Sharpe Ratio (daily)", "sharpe_ratio"),
                ("Sortino Ratio (daily)", "sortino_ratio"),
            ):
                a, b = getattr(train_metrics, attr), getattr(test_metrics, attr)
                delta = f"{b - a:>+.2f}" if a is not None and b is not None else "n/a"
                print(f"{label:<25} {fmt(a):>6}{'':<9} {fmt(b):>6}{'':<9} {delta}")

            # Max drawdown (daily NAV, relative to the running peak)
            train_dd = train_metrics.max_drawdown_pct_daily
            test_dd = test_metrics.max_drawdown_pct_daily
            print(
                f"{'Max Drawdown %':<25} {train_dd:>.2f}%{'':<9} {test_dd:>.2f}%{'':<9} {test_dd - train_dd:>+.2f}%"
            )

            # Trade count
            print(
                f"{'Total Trades':<25} {train_metrics.total_trades:<15} {test_metrics.total_trades:<15} {test_metrics.total_trades - train_metrics.total_trades:>+d}"
            )

            print("\n" + "=" * 80)

            # Overfitting warning
            if train_ret > 0 and test_ret < 0:
                print("\n⚠️  WARNING: Possible OVERFITTING detected!")
                print("    Strategy is profitable on train but loses on test data.")
                print("    Consider adjusting parameters or using a different strategy.\n")
            elif train_ret > test_ret * 2 and train_ret > 5:
                print("\n⚠️  CAUTION: Train performance is significantly better than test.")
                print("    This may indicate overfitting to historical patterns.\n")
            elif test_ret > train_ret:
                print("\n✅ Good sign: Test performance matches or exceeds train performance.\n")

        else:
            # Standard single backtest — route grid strategies to GridBacktester
            if args.strategy in GridBacktester.GRID_STRATEGIES:
                engine = GridBacktester(
                    settings,
                    db_manager,
                    strategy_name=args.strategy,
                    candle_interval=args.interval,
                    exchange=args.exchange,
                    starting_capital=args.capital,
                    fee_model=args.fees,
                    pair_costs=args.pair_costs,
                    min_order_usdc=args.min_order_usdc,
                )
            else:
                engine = BacktestEngine(
                    settings,
                    db_manager,
                    strategy_name=args.strategy,
                    candle_interval=args.interval,
                    exchange=args.exchange,
                    starting_capital=args.capital,
                    fee_model=args.fees,
                    pair_costs=args.pair_costs,
                    min_order_usdc=args.min_order_usdc,
                )

            await engine.run(args.pair, start_time, end_time)

            if args.trades_out is not None:
                dump_trades_json(
                    engine,
                    args.trades_out,
                    pair=args.pair,
                    start=start_time,
                    end=end_time,
                    exchange=args.exchange,
                    interval=args.interval,
                    capital=args.capital,
                )
                print(f"Trades written to {args.trades_out}")
            if args.equity_out is not None:
                n_points = dump_equity_jsonl(engine, args.equity_out, pair=args.pair)
                print(f"Equity written to {args.equity_out} ({n_points} points)")

            # Print report
            engine.print_report()

            # Save to database if requested
            if args.save:
                backtest_run = await engine.save_to_database(args.pair, run_name=args.name)
                print(f"\n✅ Backtest results saved to database with ID: {backtest_run.id}")
                print(f"   Run name: {backtest_run.run_name}")

                # Save individual trades for dashboard visualization (signal-based only)
                if hasattr(engine, "save_trades_to_database"):
                    await engine.save_trades_to_database(str(backtest_run.id), args.pair)
                    print(f"   Trades saved: {len(engine.metrics.trades)}")
                print("   View in dashboard: python scripts/dashboard.py\n")

    finally:
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
