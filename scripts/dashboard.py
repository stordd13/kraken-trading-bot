#!/usr/bin/env python3
"""Real-time dashboard for KrakenBot monitoring.

Built with Dash (Plotly) for better async support and real-time updates.

Features:
- Real-time price chart with candlesticks
- Bot status and P&L metrics
- Recent trades history
- SQL Explorer for custom queries
- Auto-refresh every 10 seconds

Usage:
    python scripts/dashboard.py

    # Or with custom port
    python scripts/dashboard.py --port 8051

    # With SSH tunnel (local forwarded port must match DATABASE_URL)
    # Example: autossh -L 5433:localhost:5432 ...
    python scripts/dashboard.py
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
import sys
import threading

from dotenv import load_dotenv

# Load .env file BEFORE accessing os.environ
load_dotenv()

import dash
from dash import Input, Output, State, callback, dash_table, dcc, html
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from krakenbot.config.settings import get_settings

# Load settings and build per-strategy exit configuration
_settings = get_settings()

# Per-strategy exit configuration for target price calculation.
# Built dynamically from strategies.yaml — zero code changes when adding a new strategy.
_default_sell_pct = _settings.strategy.sell_threshold_pct  # e.g., 2.0 for +2%

_DEFAULT_EXIT_TYPE = "fixed_pct"

_EXIT_TYPE_COLORS = {
    "fixed_pct": "rgba(255, 215, 0, 0.5)",
    "trailing_stop": "rgba(100, 200, 255, 0.5)",
    "profit_target": "rgba(255, 100, 100, 0.5)",
    "grid": "rgba(100, 255, 100, 0.5)",
}


def _build_strategy_exit_config() -> dict[str, dict]:
    """Build exit config from strategies.yaml. Falls back to __default__ for unknown strategies."""
    config: dict[str, dict] = {
        "__default__": {"type": "fixed_pct", "sell_threshold_pct": _default_sell_pct},
    }

    if _settings.multi_strategy.enabled:
        for strat_cfg in _settings.multi_strategy.strategies:
            dashboard_meta = strat_cfg.dashboard or {}
            exit_type = dashboard_meta.get("exit_type", _DEFAULT_EXIT_TYPE)

            if exit_type == "trailing_stop":
                entry = {
                    "type": "trailing_stop",
                    "trailing_stop_pct": strat_cfg.params.get("trailing_stop_pct", 3.0),
                }
            elif exit_type == "profit_target":
                entry = {
                    "type": "profit_target",
                    "profit_target_pct": strat_cfg.params.get("max_profit_target_pct", 15.0),
                }
            else:
                entry = {
                    "type": "fixed_pct",
                    "sell_threshold_pct": strat_cfg.params.get(
                        "sell_threshold_pct", _default_sell_pct
                    ),
                }

            config[strat_cfg.name] = entry
            if strat_cfg.bot_id and strat_cfg.bot_id != strat_cfg.name:
                config[strat_cfg.bot_id] = entry

    return config


STRATEGY_EXIT_CONFIG = _build_strategy_exit_config()


def _build_backtest_strategy_options() -> list[dict[str, str]]:
    """Build backtest strategy dropdown options dynamically from strategies.yaml."""
    options = {
        "threshold_rolling": "Threshold Rolling",
        "adaptive": "Adaptive",
        "capitulation": "Capitulation",
        "bear_short": "Bear Short",
    }
    # Add strategies from strategies.yaml not already listed
    if _settings.multi_strategy.enabled:
        for strat_cfg in _settings.multi_strategy.strategies:
            if strat_cfg.name not in options:
                dashboard_meta = strat_cfg.dashboard or {}
                label = dashboard_meta.get("label", strat_cfg.name.replace("_", " ").title())
                options[strat_cfg.name] = label

    return [{"label": label, "value": name} for name, label in options.items()]


_BACKTEST_STRATEGY_OPTIONS = _build_backtest_strategy_options()

# Database URL
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://krakenbot:bruno@localhost:5432/krakenbot"
).replace("+asyncpg", "")  # Use sync driver for Dash


def _trade_scope_filter(*, alias: str = "", exclude_backtests: bool = True) -> str:
    """Build a trade scope filter for SQL queries."""
    prefix = f"{alias}." if alias else ""
    conditions: list[str] = []

    if exclude_backtests:
        conditions.append(f"COALESCE({prefix}strategy, '') NOT LIKE 'backtest_%'")

    return " AND ".join(conditions) if conditions else "1=1"


def _describe_database_endpoint(database_url: str) -> str:
    """Return a concise host:port/database description for logs."""
    url = make_url(database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    database = url.database or "postgres"
    return f"{host}:{port}/{database}"


def _dashboard_tunnel_hint(database_url: str) -> str:
    """Return SSH tunnel guidance aligned with DATABASE_URL."""
    url = make_url(database_url)
    port = url.port or 5432
    return (
        f"    -> Start the SSH tunnel that forwards local port {port} "
        "to the remote Postgres port, then retry"
    )


# Create sync engine
engine = create_engine(DATABASE_URL)


def _read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a SQL query through SQLAlchemy text() for pandas compatibility."""
    return pd.read_sql(text(query), engine, params=params)


def _expected_candle_count(hours: int, interval: int) -> int:
    """Return the expected number of candles for a window."""
    return max(1, (hours * 60) // interval)


def _candidate_chart_intervals(hours: int) -> list[int]:
    """Return chart intervals to try, in preferred order."""
    if hours <= 6:
        return [1, 5, 15]
    if hours <= 24:
        return [1, 5, 15]
    if hours <= 72:
        return [15, 5, 1, 60]
    return [60, 15, 5]


def _apply_missing_candle_rangebreaks(
    fig: go.Figure, timestamps: pd.Series, interval_min: int, has_regime: bool
) -> None:
    """Compress missing-candle gaps so sparse data remains readable."""
    if timestamps.empty or len(timestamps) < 2:
        return

    ts = pd.to_datetime(timestamps, utc=True).sort_values()
    expected = pd.date_range(start=ts.iloc[0], end=ts.iloc[-1], freq=f"{interval_min}min")
    missing = expected.difference(pd.DatetimeIndex(ts))

    if missing.empty or len(missing) > 1500:
        return

    rangebreaks = [{"values": missing.to_pydatetime().tolist()}]

    if has_regime:
        fig.update_xaxes(rangebreaks=rangebreaks, row=1, col=1)
        fig.update_xaxes(rangebreaks=rangebreaks, row=2, col=1)
    else:
        fig.update_xaxes(rangebreaks=rangebreaks)


def _compute_display_window(df: pd.DataFrame, hours: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Compute the visible window anchored to the latest chart candle."""
    if not df.empty:
        display_end = pd.to_datetime(df["timestamp"], utc=True).max()
    else:
        display_end = pd.Timestamp.now(tz="UTC").floor("min")

    display_start = display_end - pd.Timedelta(hours=hours)
    return display_start, display_end


def _filter_df_to_window(
    df: pd.DataFrame | None,
    display_start: pd.Timestamp,
    display_end: pd.Timestamp,
    *,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame | None:
    """Filter a dataframe to the visible chart window."""
    if df is None or df.empty or timestamp_col not in df.columns:
        return df

    timestamps = pd.to_datetime(df[timestamp_col], utc=True)
    mask = (timestamps >= display_start) & (timestamps <= display_end)
    return df.loc[mask].copy()


# Test DB connection at startup
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1")).fetchone()
    print(f"  DB connection OK ({_describe_database_endpoint(DATABASE_URL)})")
except Exception as _e:
    print(f"  DB connection FAILED: {_e}")
    print(f"    URL: {_describe_database_endpoint(DATABASE_URL)}")
    print(_dashboard_tunnel_hint(DATABASE_URL))
    sys.exit(1)

# Global state for background backtest execution
_backtest_thread: threading.Thread | None = None
_backtest_progress: dict = {
    "running": False,
    "progress": 0,
    "message": "",
    "error": None,
}

# Initialize Dash app
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    title="KrakenBot Dashboard",
    update_title=None,
    suppress_callback_exceptions=True,
)

# ============================================================================
# STRATEGY TARGET LOGIC
# ============================================================================


def compute_target_for_position(strategy: str, entry_price: float) -> dict:
    """Compute target price and label for a position based on its strategy.

    Looks up exit config by exact name/bot_id, then tries base name fallback
    (e.g., "adaptive_prod" -> "adaptive"), then falls back to __default__.

    Args:
        strategy: Strategy name or bot_id (e.g., "adaptive_prod", "capitulation_prod").
        entry_price: Position entry price.

    Returns:
        dict with keys: target_price (float|None), label (str), color (str).
    """
    strategy_key = (strategy or "").lower()

    # Lookup exact (by name or bot_id)
    config = STRATEGY_EXIT_CONFIG.get(strategy_key)

    # Fallback: extract base name from bot_id (e.g., "adaptive_prod" -> "adaptive")
    if config is None and "_" in strategy_key:
        base_name = strategy_key.rsplit("_", 1)[0]
        config = STRATEGY_EXIT_CONFIG.get(base_name)

    # Ultimate fallback
    if config is None:
        config = STRATEGY_EXIT_CONFIG["__default__"]

    exit_type = config.get("type", "fixed_pct")
    color = _EXIT_TYPE_COLORS.get(exit_type, "rgba(255, 215, 0, 0.5)")

    if exit_type == "profit_target":
        pct = config.get("profit_target_pct", 15.0)
        return {
            "target_price": entry_price * (1 + pct / 100),
            "label": f"+{pct}%",
            "color": color,
        }

    if exit_type == "trailing_stop":
        pct = config.get("trailing_stop_pct", 3.0)
        return {
            "target_price": None,
            "label": f"Trailing {pct}%",
            "color": color,
        }

    if exit_type == "grid":
        spacing = config.get("grid_spacing_pct", 2.0)
        return {
            "target_price": entry_price * (1 + spacing / 100),
            "label": f"Grid +{spacing}%",
            "color": color,
        }

    # fixed_pct (default)
    pct = config.get("sell_threshold_pct", _default_sell_pct)
    return {
        "target_price": entry_price * (1 + pct / 100),
        "label": f"+{pct}%",
        "color": color,
    }


# ============================================================================
# DATA FETCHING FUNCTIONS
# ============================================================================


def fetch_bot_state() -> dict | None:
    """Fetch aggregated bot state across all running instances.

    Returns aggregated metrics:
    - active_instances: count of running bots
    - total_position: sum of all position sizes
    - total_daily_pnl: today's realized runtime/paper P&L from trades_history
    - total_pnl: sum of total P&L across instances
    - total_trades_today: today's runtime/paper trade count from trades_history
    """
    bot_query = """
    SELECT
        COUNT(DISTINCT bot_id) as active_instances,
        COALESCE(SUM(position_size), 0) as total_position,
        MAX(updated_at) as last_updated,
        MAX(last_trade_at) as last_trade_at,
        STRING_AGG(DISTINCT status, ', ') as statuses
    FROM bot_state
    WHERE status IN ('RUNNING', 'PAUSED')
       OR updated_at > NOW() - INTERVAL '1 hour'
    """
    today_query = """
    SELECT
        COALESCE(SUM(CASE WHEN pnl IS NOT NULL THEN pnl ELSE 0 END), 0) as today_pnl,
        COUNT(*) as today_trades
    FROM trades_history
    WHERE DATE(timestamp AT TIME ZONE 'UTC') = CURRENT_DATE
      AND UPPER(CAST(status AS TEXT)) = 'FILLED'
      AND COALESCE(strategy, '') NOT LIKE 'backtest_%'
    """
    total_pnl_query = """
    SELECT
        COALESCE(SUM(CASE WHEN pnl IS NOT NULL THEN pnl ELSE 0 END), 0) as total_pnl
    FROM trades_history
    WHERE UPPER(CAST(status AS TEXT)) = 'FILLED'
      AND COALESCE(strategy, '') NOT LIKE 'backtest_%'
    """
    try:
        df = _read_sql(bot_query)
        if df.empty:
            return None
        result = df.iloc[0].to_dict()

        # Get realized runtime/paper P&L directly from trade history
        today_df = _read_sql(today_query)
        total_df = _read_sql(total_pnl_query)
        today_pnl = float(today_df.iloc[0]["today_pnl"]) if not today_df.empty else 0.0
        today_trades = int(today_df.iloc[0]["today_trades"]) if not today_df.empty else 0
        total_pnl = float(total_df.iloc[0]["total_pnl"]) if not total_df.empty else 0.0

        # Convert numpy types to Python types
        result["active_instances"] = int(result.get("active_instances") or 0)
        result["total_position"] = float(result.get("total_position") or 0)
        result["total_daily_pnl"] = today_pnl
        result["total_pnl"] = total_pnl
        result["total_trades_today"] = today_trades
        return result
    except Exception as e:
        print(f"Error fetching bot state: {e}")
        return None


def get_optimal_interval(hours: int) -> int:
    """Select optimal candle interval based on timeframe to avoid gaps."""
    return _candidate_chart_intervals(hours)[0]


def fetch_ohlc_data(pair: str = "XBT/USDC", hours: int = 24, interval: int = 1) -> pd.DataFrame:
    """Fetch OHLC data for chart."""
    query = """
    SELECT timestamp, open, high, low, close, volume
    FROM market_data_ohlc
    WHERE pair = :pair
      AND interval = :interval
      AND timestamp >= NOW() - INTERVAL ':hours hours'
    ORDER BY timestamp ASC
    """
    try:
        return _read_sql(
            query.replace(":hours", str(hours)), params={"pair": pair, "interval": interval}
        )
    except Exception as e:
        print(f"Error fetching OHLC: {e}")
        return pd.DataFrame()


def fetch_best_ohlc_data(
    pair: str = "XBT/USDC", hours: int = 24
) -> tuple[pd.DataFrame, int, float]:
    """Fetch the best available OHLC interval for the requested chart window."""
    best_df = pd.DataFrame()
    best_interval = get_optimal_interval(hours)
    best_coverage = -1.0

    for interval in _candidate_chart_intervals(hours):
        df = fetch_ohlc_data(pair=pair, hours=hours, interval=interval)
        coverage = len(df) / _expected_candle_count(hours, interval)

        if coverage > best_coverage:
            best_df = df
            best_interval = interval
            best_coverage = coverage

        if coverage >= 0.7:
            break

    return best_df, best_interval, max(best_coverage, 0.0)


def fetch_recent_trades(limit: int = 20, strategy_filter: str | None = None) -> pd.DataFrame:
    """Fetch recent trades with position context.

    Args:
        limit: Maximum rows to return.
        strategy_filter: Filter by strategy/bot_id. None or "all" = no filter.
    """
    conditions = [_trade_scope_filter(alias="t")]
    params: dict = {}

    if strategy_filter and strategy_filter != "all":
        conditions.append("(t.strategy = :strat)")
        params["strat"] = strategy_filter

    where_clause = " AND ".join(conditions)

    query = f"""
    SELECT
        t.timestamp,
        t.pair,
        t.side,
        t.amount,
        t.price,
        t.fee,
        t.pnl,
        t.strategy,
        t.status,
        op.entry_price as position_entry_price,
        op.position_id
    FROM trades_history t
    LEFT JOIN open_positions op ON (
        t.id = op.entry_trade_id OR t.id = op.exit_trade_id
    )
    WHERE {where_clause}
    ORDER BY t.timestamp DESC
    LIMIT {limit}
    """
    try:
        return pd.read_sql(text(query), engine, params=params)
    except Exception as e:
        print(f"Error fetching trades: {e}")
        return pd.DataFrame()


def fetch_stats() -> dict:
    """Fetch dashboard statistics with runtime and backtest scopes separated."""
    stats = {}

    try:
        # OHLC stats
        result = pd.read_sql(
            text(
                """
            SELECT
                COUNT(*) as total_candles,
                MIN(timestamp) as first_candle,
                MAX(timestamp) as last_candle
            FROM market_data_ohlc
        """
            ),
            engine,
        )
        if not result.empty:
            stats["total_candles"] = int(result.iloc[0]["total_candles"])
            stats["first_candle"] = result.iloc[0]["first_candle"]
            stats["last_candle"] = result.iloc[0]["last_candle"]

        # Runtime/paper trading stats (exclude persisted backtests)
        runtime_trade_query = f"""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN side = 'buy' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN side = 'sell' THEN 1 ELSE 0 END) as sells,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM trades_history
            WHERE {_trade_scope_filter()}
        """
        result = _read_sql(
            runtime_trade_query.replace(
                "side = 'buy'", "UPPER(CAST(side AS TEXT)) = 'BUY'"
            ).replace("side = 'sell'", "UPPER(CAST(side AS TEXT)) = 'SELL'")
        )
        if not result.empty:
            stats["total_trades"] = int(result.iloc[0]["total_trades"])
            stats["total_buys"] = int(result.iloc[0]["buys"] or 0)
            stats["total_sells"] = int(result.iloc[0]["sells"] or 0)
            stats["total_pnl"] = float(result.iloc[0]["total_pnl"] or 0)

        # Backtests are shown separately to avoid polluting runtime metrics
        backtest_result = pd.read_sql(
            text(
                """
            SELECT
                COUNT(*) as total_backtest_runs,
                COALESCE(SUM(total_trades), 0) as total_backtest_trades,
                COALESCE(SUM(net_pnl), 0) as total_backtest_pnl,
                MAX(created_at) as last_backtest_at
            FROM backtest_runs
            """
            ),
            engine,
        )
        if not backtest_result.empty:
            stats["total_backtest_runs"] = int(backtest_result.iloc[0]["total_backtest_runs"])
            stats["total_backtest_trades"] = int(
                backtest_result.iloc[0]["total_backtest_trades"] or 0
            )
            stats["total_backtest_pnl"] = float(backtest_result.iloc[0]["total_backtest_pnl"] or 0)
            stats["last_backtest_at"] = backtest_result.iloc[0]["last_backtest_at"]

    except Exception as e:
        print(f"Error fetching stats: {e}")

    return stats


def execute_custom_query(query: str) -> tuple[pd.DataFrame | None, str | None]:
    """Execute custom SQL query.

    Allows SELECT on any table.
    Allows DELETE only on backtest-related data:
    - backtest_runs table
    - trades_history with strategy LIKE 'backtest%'
    """
    try:
        query_upper = query.strip().upper()

        # SELECT queries - always allowed
        if query_upper.startswith("SELECT"):
            df = _read_sql(query)
            return df, None

        # DELETE queries - restricted to backtest data
        if query_upper.startswith("DELETE"):
            # Allow DELETE FROM backtest_runs
            if "BACKTEST_RUNS" in query_upper:
                with engine.connect() as conn:
                    result = conn.execute(text(query))
                    conn.commit()
                    return None, f"Deleted {result.rowcount} row(s) from backtest_runs"

            # Allow DELETE FROM trades_history only with backtest filter
            if "TRADES_HISTORY" in query_upper:
                # Must have a backtest filter to prevent accidental deletion of real trades
                if "BACKTEST" not in query_upper or "STRATEGY" not in query_upper:
                    return None, (
                        "DELETE from trades_history requires a backtest filter. "
                        "Example: DELETE FROM trades_history WHERE strategy LIKE 'backtest_%'"
                    )
                with engine.connect() as conn:
                    result = conn.execute(text(query))
                    conn.commit()
                    return None, f"Deleted {result.rowcount} row(s) from trades_history"

            return (
                None,
                "DELETE only allowed on backtest_runs or trades_history (with backtest filter)",
            )

        return None, "Only SELECT and DELETE (backtest data only) queries are allowed"
    except Exception as e:
        return None, str(e)


def fetch_open_positions(strategy_filter: str | None = None) -> pd.DataFrame:
    """Fetch open positions from open_positions table.

    Args:
        strategy_filter: Filter by strategy/bot_id. None or "all" = no filter.
    """
    conditions = ["status = 'OPEN'"]
    params: dict = {}

    if strategy_filter and strategy_filter != "all":
        conditions.append("(bot_id = :strat OR strategy = :strat)")
        params["strat"] = strategy_filter

    where_clause = " AND ".join(conditions)

    query = f"""
    SELECT
        bot_id,
        position_id,
        pair,
        amount_btc as amount,
        entry_price,
        reference_price,
        entry_time,
        strategy,
        COALESCE(trading_mode, 'spot') as trading_mode
    FROM open_positions
    WHERE {where_clause}
    ORDER BY bot_id, position_id
    """
    try:
        return pd.read_sql(text(query), engine, params=params)
    except Exception as e:
        print(f"Error fetching open positions: {e}")
        return pd.DataFrame()


def fetch_current_price(pair: str = "XBT/USDC") -> float | None:
    """Fetch current price from latest OHLC data."""
    query = """
    SELECT close
    FROM market_data_ohlc
    WHERE pair = :pair
    ORDER BY timestamp DESC
    LIMIT 1
    """
    try:
        df = pd.read_sql(text(query), engine, params={"pair": pair})
        if not df.empty:
            return float(df.iloc[0]["close"])
        return None
    except Exception as e:
        print(f"Error fetching current price: {e}")
        return None


def fetch_backtest_runs() -> pd.DataFrame:
    """Fetch all backtest runs from database."""
    query = """
    SELECT id, run_name, strategy, pair, start_time, end_time,
           starting_balance, ending_balance, total_trades,
           winning_trades, losing_trades, win_rate,
           net_pnl, total_return_pct, max_drawdown_pct,
           sharpe_ratio, profit_factor, created_at
    FROM backtest_runs
    ORDER BY created_at DESC
    LIMIT 20
    """
    try:
        return _read_sql(query)
    except Exception as e:
        print(f"Error fetching backtest runs: {e}")
        return pd.DataFrame()


def fetch_data_range_stats() -> dict:
    """Fetch data range and candle counts per interval."""
    query = """
    SELECT
        interval,
        COUNT(*) as candle_count,
        MIN(timestamp) as earliest,
        MAX(timestamp) as latest
    FROM market_data_ohlc
    WHERE pair = 'XBT/USDC'
    GROUP BY interval
    ORDER BY interval
    """
    try:
        df = _read_sql(query)
        if df.empty:
            return {
                "intervals": [],
                "total_candles": 0,
                "global_earliest": None,
                "global_latest": None,
            }
        return {
            "intervals": df.to_dict("records"),
            "total_candles": int(df["candle_count"].sum()),
            "global_earliest": df["earliest"].min(),
            "global_latest": df["latest"].max(),
        }
    except Exception as e:
        print(f"Error fetching data range: {e}")
        return {
            "intervals": [],
            "total_candles": 0,
            "global_earliest": None,
            "global_latest": None,
        }


def compute_market_regime(hours: int = 168) -> pd.DataFrame:
    """Compute market regime from 1h OHLC data using EMA(20)/EMA(50) crossover.

    Uses the same logic as MultiTimeframeAnalyzer._classify_regime():
    EMA spread % thresholds at 0.5% (neutral) and 1.0% (strong).

    Args:
        hours: Number of hours of history to compute (default 7 days).

    Returns:
        DataFrame with columns: timestamp, regime, ema_spread_pct.
    """
    # Need extra history for EMA warmup (50 candles = 50 hours)
    total_hours = hours + 60
    query = """
    SELECT timestamp, close
    FROM market_data_ohlc
    WHERE pair = 'XBT/USDC'
      AND interval = 60
      AND timestamp >= NOW() - INTERVAL ':hours hours'
    ORDER BY timestamp ASC
    """
    try:
        df = _read_sql(query.replace(":hours", str(total_hours)))
        if df.empty or len(df) < 50:
            return pd.DataFrame()

        df["close"] = df["close"].astype(float)
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_spread_pct"] = ((df["ema20"] - df["ema50"]) / df["ema50"]) * 100

        threshold = 0.5  # Same as MultiTimeframeAnalyzer default
        df["regime"] = df["ema_spread_pct"].apply(
            lambda s: (
                "STRONG_BULL"
                if s > threshold * 2
                else (
                    "BULL"
                    if s > threshold
                    else (
                        "STRONG_BEAR"
                        if s < -threshold * 2
                        else "BEAR"
                        if s < -threshold
                        else "NEUTRAL"
                    )
                )
            )
        )

        # Trim warmup period
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=hours)
        df = df[df["timestamp"] >= cutoff]

        return df[["timestamp", "regime", "ema_spread_pct"]]
    except Exception as e:
        print(f"Error computing market regime: {e}")
        return pd.DataFrame()


def fetch_bot_states_per_strategy() -> pd.DataFrame:
    """Fetch bot state for each strategy instance individually."""
    query = """
    SELECT
        bot_id,
        strategy,
        status,
        position_size,
        daily_pnl,
        total_pnl,
        daily_trades_count,
        updated_at,
        last_trade_at
    FROM bot_state
    WHERE status IN ('RUNNING', 'PAUSED')
       OR updated_at > NOW() - INTERVAL '1 hour'
    ORDER BY strategy, bot_id
    """
    try:
        return _read_sql(query)
    except Exception as e:
        print(f"Error fetching per-strategy bot states: {e}")
        return pd.DataFrame()


def fetch_orders(strategy_filter: str | None = None, limit: int = 50) -> pd.DataFrame:
    """Fetch orders from the orders table.

    Args:
        strategy_filter: Filter by strategy/bot_id. None or "all" = no filter.
        limit: Maximum rows to return.
    """
    base_query = """
    SELECT
        order_id, bot_id, pair, side, order_type,
        amount, price, filled_amount, filled_price, fee,
        status, strategy, expires_at, created_at, updated_at
    FROM orders
    """
    if strategy_filter and strategy_filter != "all":
        base_query += " WHERE (strategy = :strat OR bot_id = :strat)"
        base_query += f" ORDER BY created_at DESC LIMIT {limit}"
        try:
            return pd.read_sql(text(base_query), engine, params={"strat": strategy_filter})
        except Exception as e:
            print(f"Error fetching orders: {e}")
            return pd.DataFrame()
    else:
        base_query += f" ORDER BY created_at DESC LIMIT {limit}"
        try:
            return _read_sql(base_query)
        except Exception as e:
            print(f"Error fetching orders: {e}")
            return pd.DataFrame()


def fetch_distinct_strategies() -> list[dict]:
    """Fetch distinct strategies/bot_ids for filter dropdowns."""
    query = """
    SELECT DISTINCT bot_id, strategy
    FROM bot_state
    WHERE bot_id IS NOT NULL
    UNION
    SELECT DISTINCT bot_id, strategy
    FROM open_positions
    WHERE bot_id IS NOT NULL
    UNION
    SELECT DISTINCT bot_id, strategy
    FROM orders
    WHERE bot_id IS NOT NULL
      AND COALESCE(strategy, '') NOT LIKE 'backtest_%'
    UNION
    SELECT DISTINCT strategy as bot_id, strategy
    FROM trades_history
    WHERE strategy IS NOT NULL
      AND COALESCE(strategy, '') NOT LIKE 'backtest_%'
    ORDER BY strategy, bot_id
    """
    try:
        df = _read_sql(query)
        options = [{"label": "All Strategies", "value": "all"}]
        for _, row in df.iterrows():
            bot_id = row["bot_id"]
            strategy = row.get("strategy", "")
            label = f"{strategy} ({bot_id})" if strategy and strategy != bot_id else bot_id
            options.append({"label": label, "value": bot_id})
        return options
    except Exception:
        return [{"label": "All Strategies", "value": "all"}]


def run_backtest_in_thread(strategy: str, days: int, interval: int, pair: str) -> None:
    """Run backtest in background thread."""
    global _backtest_progress

    async def _run() -> None:
        global _backtest_progress
        try:
            _backtest_progress = {
                "running": True,
                "progress": 5,
                "message": "Initializing...",
                "error": None,
            }

            # Import here to avoid circular imports
            from krakenbot.config.settings import get_settings
            from krakenbot.core.database import DatabaseManager

            # Import backtest engine from scripts
            script_dir = os.path.dirname(__file__)
            sys.path.insert(0, script_dir)
            from backtest import BacktestEngine

            settings = get_settings()
            db_manager = DatabaseManager()
            await db_manager.init_db(settings)

            _backtest_progress["progress"] = 10
            _backtest_progress["message"] = "Creating backtest engine..."

            bt_engine = BacktestEngine(
                settings=settings,
                db_manager=db_manager,
                strategy_name=strategy,
                candle_interval=interval,
            )

            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(days=days)

            _backtest_progress["progress"] = 15
            _backtest_progress["message"] = "Loading historical data..."

            await bt_engine.run(pair, start_time, end_time)

            _backtest_progress["progress"] = 85
            _backtest_progress["message"] = "Saving results..."

            backtest_run = await bt_engine.save_to_database(pair)
            await bt_engine.save_trades_to_database(str(backtest_run.id), pair)

            _backtest_progress = {
                "running": False,
                "progress": 100,
                "message": "Completed!",
                "error": None,
            }

            await db_manager.close_db()

        except Exception as e:
            _backtest_progress = {
                "running": False,
                "progress": 0,
                "message": "",
                "error": str(e),
            }

    asyncio.run(_run())


def delete_backtest_run(backtest_id: str) -> tuple[bool, str]:
    """Delete a backtest run and its associated trades.

    Args:
        backtest_id: UUID of the backtest run to delete.

    Returns:
        Tuple of (success, message).
    """
    try:
        with engine.connect() as conn:
            # Delete associated trades first
            conn.execute(
                text("DELETE FROM trades_history WHERE strategy LIKE :pattern"),
                {"pattern": f"backtest_{backtest_id}%"},
            )
            # Delete the backtest run
            result = conn.execute(
                text("DELETE FROM backtest_runs WHERE id = :id"),
                {"id": backtest_id},
            )
            conn.commit()

            if result.rowcount > 0:
                return True, f"Deleted backtest {backtest_id[:8]}..."
            else:
                return False, "Backtest not found"
    except Exception as e:
        return False, str(e)


def fetch_backtest_trades(strategy_filter: str) -> pd.DataFrame:
    """Fetch trades from a specific backtest run."""
    query = """
    SELECT timestamp, pair, side, amount, price, fee, pnl, strategy
    FROM trades_history
    WHERE strategy LIKE :strategy_filter
    ORDER BY timestamp ASC
    """
    try:
        return pd.read_sql(
            text(query), engine, params={"strategy_filter": f"backtest_{strategy_filter}%"}
        )
    except Exception as e:
        print(f"Error fetching backtest trades: {e}")
        return pd.DataFrame()


# ============================================================================
# CHART CREATION
# ============================================================================


def create_candlestick_chart(
    df: pd.DataFrame,
    trades_df: pd.DataFrame = None,
    positions_df: pd.DataFrame = None,
    regime_df: pd.DataFrame = None,
    interval_min: int = 1,
    coverage: float | None = None,
    display_start: pd.Timestamp | None = None,
    display_end: pd.Timestamp | None = None,
) -> go.Figure:
    """Create candlestick chart with trades overlay, position levels, and regime subplot."""
    from plotly.subplots import make_subplots

    has_regime = regime_df is not None and not regime_df.empty

    if has_regime:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.82, 0.18],
        )
    else:
        fig = go.Figure()

    def _add_trace(trace: go.Scatter | go.Candlestick) -> None:
        if has_regime:
            fig.add_trace(trace, row=1, col=1)
        else:
            fig.add_trace(trace)

    if not df.empty:
        _add_trace(
            go.Candlestick(
                x=df["timestamp"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="BTC/USDC",
                increasing_line_color="#00ff88",
                decreasing_line_color="#ff4444",
            )
        )

    # Add trade markers if available
    if trades_df is not None and not trades_df.empty:
        buys = trades_df[trades_df["side"] == "buy"]
        sells = trades_df[trades_df["side"] == "sell"]

        if not buys.empty:
            _add_trace(
                go.Scatter(
                    x=buys["timestamp"],
                    y=buys["price"],
                    mode="markers",
                    name="Buy",
                    marker={
                        "symbol": "triangle-up",
                        "size": 12,
                        "color": "#00ff88",
                        "line": {"color": "white", "width": 1},
                    },
                )
            )

        if not sells.empty:
            _add_trace(
                go.Scatter(
                    x=sells["timestamp"],
                    y=sells["price"],
                    mode="markers",
                    name="Sell",
                    marker={
                        "symbol": "triangle-down",
                        "size": 12,
                        "color": "#ff4444",
                        "line": {"color": "white", "width": 1},
                    },
                )
            )

    # Add open position entry/target lines (per-strategy)
    if positions_df is not None and not positions_df.empty:
        for _, pos in positions_df.iterrows():
            entry_price = float(pos["entry_price"])
            strategy = pos.get("strategy", "threshold_rolling")
            pos_id = pos.get("position_id", "?")

            target_info = compute_target_for_position(strategy, entry_price)
            target_price = target_info["target_price"]
            target_label = target_info["label"]
            target_color = target_info["color"]

            # Entry price - solid green line
            fig.add_hline(
                y=entry_price,
                line_dash="solid",
                line_color="rgba(0, 255, 136, 0.5)",
                line_width=1,
                annotation_text=f"Entry #{pos_id}",
                annotation_position="left",
                annotation_font_color="rgba(0, 255, 136, 0.7)",
                annotation_font_size=10,
                row=1 if has_regime else None,
                col=1 if has_regime else None,
            )

            if target_price is not None:
                fig.add_hline(
                    y=target_price,
                    line_dash="dash",
                    line_color=target_color,
                    line_width=1,
                    annotation_text=f"Target #{pos_id} ({target_label})",
                    annotation_position="left",
                    annotation_font_color=target_color,
                    annotation_font_size=10,
                    row=1 if has_regime else None,
                    col=1 if has_regime else None,
                )
            else:
                fig.add_annotation(
                    x=0.02,
                    y=entry_price,
                    xref="paper",
                    text=f"#{pos_id} {target_label}",
                    showarrow=False,
                    font={"color": target_color, "size": 10},
                    xanchor="left",
                    yshift=12,
                )

    # Add regime subplot
    if has_regime:
        regime_colors = {
            "STRONG_BEAR": "#ff4444",
            "BEAR": "#ff8c00",
            "NEUTRAL": "#888888",
            "BULL": "#90ee90",
            "STRONG_BULL": "#00ff88",
        }
        fig.add_trace(
            go.Bar(
                x=regime_df["timestamp"],
                y=[1] * len(regime_df),
                marker_color=[regime_colors.get(r, "#888") for r in regime_df["regime"]],
                hovertext=[
                    f"{r} ({s:+.2f}%)"
                    for r, s in zip(regime_df["regime"], regime_df["ema_spread_pct"], strict=True)
                ],
                hoverinfo="text+x",
                showlegend=False,
            ),
            row=2,
            col=1,
        )
        fig.update_yaxes(
            visible=False,
            row=2,
            col=1,
        )
        fig.update_xaxes(
            gridcolor="rgba(255,255,255,0.1)",
            row=2,
            col=1,
        )

    chart_height = 520 if has_regime else 450

    _apply_missing_candle_rangebreaks(
        fig,
        df["timestamp"] if not df.empty else pd.Series(dtype="datetime64[ns, UTC]"),
        interval_min,
        has_regime,
    )

    if display_start is not None and display_end is not None:
        fig.update_xaxes(range=[display_start, display_end])

    title_text = f"XBT/USDC chart ({interval_min}m candles)"
    if coverage is not None:
        title_text += f" | coverage {coverage * 100:.0f}%"

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=chart_height,
        title={"text": title_text, "x": 0.01, "xanchor": "left", "font": {"size": 14}},
        margin={"l": 50, "r": 50, "t": 30, "b": 50},
        xaxis_rangeslider_visible=False,
        xaxis={"gridcolor": "rgba(255,255,255,0.1)"},
        yaxis={"gridcolor": "rgba(255,255,255,0.1)", "title": "Price (USDC)"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )

    return fig


def create_backtest_equity_chart(
    trades_df: pd.DataFrame, starting_balance: float = 1000
) -> go.Figure:
    """Create equity curve chart from backtest trades."""
    fig = go.Figure()

    if trades_df.empty:
        fig.add_annotation(
            text="No backtest data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 16, "color": "gray"},
        )
    else:
        # Calculate cumulative equity
        equity = [starting_balance]
        timestamps = [trades_df["timestamp"].iloc[0]]

        cumulative_pnl = 0
        for _, trade in trades_df.iterrows():
            if trade["pnl"] is not None and pd.notna(trade["pnl"]):
                cumulative_pnl += float(trade["pnl"])
            equity.append(starting_balance + cumulative_pnl)
            timestamps.append(trade["timestamp"])

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=equity,
                mode="lines",
                name="Equity",
                line={"color": "#00ff88", "width": 2},
                fill="tozeroy",
                fillcolor="rgba(0, 255, 136, 0.1)",
            )
        )

        # Add starting balance reference line
        fig.add_hline(
            y=starting_balance,
            line_dash="dash",
            line_color="rgba(255, 255, 255, 0.3)",
            annotation_text=f"Start: {starting_balance}",
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=350,
        margin={"l": 50, "r": 50, "t": 30, "b": 50},
        xaxis={"gridcolor": "rgba(255,255,255,0.1)", "title": "Time"},
        yaxis={"gridcolor": "rgba(255,255,255,0.1)", "title": "Equity (USDC)"},
    )

    return fig


# ============================================================================
# LAYOUT
# ============================================================================


def create_metric_card(title: str, value: str, subtitle: str = "", color: str = "primary"):
    """Create a metric card component."""
    return dbc.Card(
        [
            dbc.CardBody(
                [
                    html.H6(title, className="text-muted mb-1"),
                    html.H3(value, className=f"text-{color} mb-0"),
                    html.Small(subtitle, className="text-muted") if subtitle else None,
                ]
            )
        ],
        className="mb-3",
    )


app.layout = dbc.Container(
    [
        # Header
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H2("KrakenBot Dashboard", className="text-primary mb-0"),
                        html.Small("Real-time monitoring", className="text-muted"),
                    ],
                    width=8,
                ),
                dbc.Col(
                    [
                        html.Div(id="last-update", className="text-end text-muted"),
                        dbc.Button(
                            "Refresh",
                            id="refresh-btn",
                            color="primary",
                            size="sm",
                            className="mt-2",
                        ),
                    ],
                    width=4,
                    className="text-end",
                ),
            ],
            className="mb-4 pt-3",
        ),
        # Trading mode banner
        html.Div(id="trading-mode-banner", className="mb-3"),
        # Auto-refresh interval
        dcc.Interval(id="interval-component", interval=10 * 1000, n_intervals=0),
        # Store for delete status
        dcc.Store(id="delete-status-store", data=None),
        # Metrics Row (aggregated)
        dbc.Row(
            [
                dbc.Col(html.Div(id="metric-status"), width=3),
                dbc.Col(html.Div(id="metric-position"), width=3),
                dbc.Col(html.Div(id="metric-pnl"), width=3),
                dbc.Col(html.Div(id="metric-trades"), width=3),
            ],
            className="mb-2",
        ),
        # Per-strategy breakdown row
        dbc.Row(
            [
                dbc.Col(html.Div(id="metric-strategy-breakdown"), width=12),
            ],
            className="mb-4",
        ),
        # Tabs
        dbc.Tabs(
            [
                # Tab 1: Charts
                dbc.Tab(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        dbc.Card(
                                            [
                                                dbc.CardHeader(
                                                    [
                                                        dbc.Row(
                                                            [
                                                                dbc.Col(
                                                                    html.H5(
                                                                        "Price Chart",
                                                                        className="mb-0",
                                                                    ),
                                                                    width=6,
                                                                ),
                                                                dbc.Col(
                                                                    [
                                                                        dbc.Select(
                                                                            id="hours-select",
                                                                            options=[
                                                                                {
                                                                                    "label": "6 hours",
                                                                                    "value": "6",
                                                                                },
                                                                                {
                                                                                    "label": "12 hours",
                                                                                    "value": "12",
                                                                                },
                                                                                {
                                                                                    "label": "24 hours",
                                                                                    "value": "24",
                                                                                },
                                                                                {
                                                                                    "label": "48 hours",
                                                                                    "value": "48",
                                                                                },
                                                                                {
                                                                                    "label": "7 days",
                                                                                    "value": "168",
                                                                                },
                                                                            ],
                                                                            value="24",
                                                                            size="sm",
                                                                        ),
                                                                    ],
                                                                    width=6,
                                                                    className="text-end",
                                                                ),
                                                            ]
                                                        ),
                                                    ]
                                                ),
                                                dbc.CardBody(
                                                    [
                                                        dcc.Graph(
                                                            id="price-chart",
                                                            config={"displayModeBar": False},
                                                        ),
                                                    ]
                                                ),
                                            ]
                                        ),
                                    ],
                                    width=12,
                                ),
                            ],
                            className="mb-4",
                        ),
                    ],
                    label="Charts",
                    tab_id="tab-charts",
                ),
                # Tab 2: Trades
                dbc.Tab(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                html.H5("Recent Trades", className="mb-0"),
                                                width=8,
                                            ),
                                            dbc.Col(
                                                dbc.Select(
                                                    id="trades-strategy-filter",
                                                    options=[],
                                                    value="all",
                                                    size="sm",
                                                ),
                                                width=4,
                                            ),
                                        ]
                                    )
                                ),
                                dbc.CardBody(
                                    [
                                        html.Div(id="trades-table"),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    label="Trades",
                    tab_id="tab-trades",
                ),
                # Tab 3: Positions
                dbc.Tab(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                html.H5("Open Positions", className="mb-0"),
                                                width=4,
                                            ),
                                            dbc.Col(
                                                dbc.Select(
                                                    id="positions-strategy-filter",
                                                    options=[],
                                                    value="all",
                                                    size="sm",
                                                ),
                                                width=4,
                                            ),
                                            dbc.Col(
                                                html.Div(
                                                    id="positions-summary", className="text-end"
                                                ),
                                                width=4,
                                            ),
                                        ]
                                    )
                                ),
                                dbc.CardBody(
                                    [
                                        html.Div(id="positions-table"),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    label="Positions",
                    tab_id="tab-positions",
                ),
                # Tab 4: Orders
                dbc.Tab(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                html.H5("Orders", className="mb-0"),
                                                width=4,
                                            ),
                                            dbc.Col(
                                                dbc.Select(
                                                    id="orders-strategy-filter",
                                                    options=[],
                                                    value="all",
                                                    size="sm",
                                                ),
                                                width=4,
                                            ),
                                            dbc.Col(
                                                html.Div(
                                                    id="orders-summary",
                                                    className="text-end",
                                                ),
                                                width=4,
                                            ),
                                        ]
                                    )
                                ),
                                dbc.CardBody(
                                    [
                                        html.Div(id="orders-table"),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    label="Orders",
                    tab_id="tab-orders",
                ),
                # Tab 5: SQL Explorer
                dbc.Tab(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H5("SQL Explorer", className="mb-0")),
                                dbc.CardBody(
                                    [
                                        dbc.Textarea(
                                            id="sql-input",
                                            placeholder="SELECT * FROM market_data_ohlc LIMIT 10",
                                            value="SELECT * FROM market_data_ohlc ORDER BY timestamp DESC LIMIT 20",
                                            className="mb-3",
                                            style={"fontFamily": "monospace", "height": "100px"},
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Button(
                                                            "Execute Query",
                                                            id="execute-query-btn",
                                                            color="success",
                                                            className="me-2",
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                                dbc.Col(
                                                    [
                                                        html.Div(
                                                            id="query-status", className="text-end"
                                                        ),
                                                    ],
                                                    width=6,
                                                ),
                                            ],
                                            className="mb-3",
                                        ),
                                        html.Hr(),
                                        html.H6("Available Tables:"),
                                        html.Ul(
                                            [
                                                html.Li(
                                                    html.Code("market_data_ohlc"), className="mb-1"
                                                ),
                                                html.Li(
                                                    html.Code("trades_history"), className="mb-1"
                                                ),
                                                html.Li(
                                                    html.Code("open_positions"), className="mb-1"
                                                ),
                                                html.Li(html.Code("orders"), className="mb-1"),
                                                html.Li(html.Code("bot_state"), className="mb-1"),
                                                html.Li(
                                                    html.Code("backtest_runs"), className="mb-1"
                                                ),
                                                html.Li(
                                                    html.Code("task_execution_logs"),
                                                    className="mb-1",
                                                ),
                                            ],
                                            className="mb-3",
                                        ),
                                        html.Hr(),
                                        html.Div(id="sql-results"),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    label="SQL Explorer",
                    tab_id="tab-sql",
                ),
                # Tab 5: Statistics
                dbc.Tab(
                    [
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H5("Database Statistics", className="mb-0")),
                                dbc.CardBody(
                                    [
                                        html.Div(id="stats-content"),
                                    ]
                                ),
                            ]
                        ),
                    ],
                    label="Statistics",
                    tab_id="tab-stats",
                ),
                # Tab 6: Backtest Results
                dbc.Tab(
                    [
                        # Data range badge
                        html.Div(id="backtest-data-range", className="mb-3"),
                        # Run Backtest Form
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H5("Run New Backtest", className="mb-0")),
                                dbc.CardBody(
                                    [
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Strategy"),
                                                        dbc.Select(
                                                            id="backtest-strategy-select",
                                                            options=_BACKTEST_STRATEGY_OPTIONS,
                                                            value="threshold_rolling",
                                                        ),
                                                    ],
                                                    width=3,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Days"),
                                                        dbc.Input(
                                                            id="backtest-days-input",
                                                            type="number",
                                                            value=7,
                                                            min=1,
                                                            max=365,
                                                        ),
                                                    ],
                                                    width=2,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Interval (min)"),
                                                        dbc.Select(
                                                            id="backtest-interval-select",
                                                            options=[
                                                                {"label": "1 min", "value": "1"},
                                                                {"label": "5 min", "value": "5"},
                                                                {"label": "15 min", "value": "15"},
                                                                {"label": "60 min", "value": "60"},
                                                            ],
                                                            value="15",
                                                        ),
                                                    ],
                                                    width=2,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("Pair"),
                                                        dbc.Select(
                                                            id="backtest-pair-select",
                                                            options=[
                                                                {
                                                                    "label": "XBT/USDC",
                                                                    "value": "XBT/USDC",
                                                                },
                                                            ],
                                                            value="XBT/USDC",
                                                        ),
                                                    ],
                                                    width=2,
                                                ),
                                                dbc.Col(
                                                    [
                                                        dbc.Label("\u00a0"),  # Spacer
                                                        dbc.Button(
                                                            "Run Backtest",
                                                            id="run-backtest-btn",
                                                            color="success",
                                                            className="w-100",
                                                        ),
                                                    ],
                                                    width=3,
                                                ),
                                            ],
                                        ),
                                        html.Div(id="backtest-progress", className="mt-3"),
                                    ]
                                ),
                            ],
                            className="mb-4",
                        ),
                        # Stores for backtest state
                        dcc.Interval(
                            id="backtest-progress-interval",
                            interval=2000,
                            disabled=True,
                        ),
                        # Backtest Runs Table
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        dbc.Card(
                                            [
                                                dbc.CardHeader(
                                                    [
                                                        dbc.Row(
                                                            [
                                                                dbc.Col(
                                                                    html.H5(
                                                                        "Backtest Runs",
                                                                        className="mb-0",
                                                                    ),
                                                                    width=6,
                                                                ),
                                                                dbc.Col(
                                                                    [
                                                                        dbc.Button(
                                                                            "Compare Selected",
                                                                            id="compare-backtest-btn",
                                                                            color="info",
                                                                            size="sm",
                                                                            className="me-2",
                                                                        ),
                                                                        dbc.Button(
                                                                            "Delete Selected",
                                                                            id="delete-backtest-btn",
                                                                            color="danger",
                                                                            size="sm",
                                                                            className="me-2",
                                                                        ),
                                                                        dbc.Button(
                                                                            "Refresh",
                                                                            id="refresh-backtest-btn",
                                                                            color="primary",
                                                                            size="sm",
                                                                        ),
                                                                    ],
                                                                    width=6,
                                                                    className="text-end",
                                                                ),
                                                            ]
                                                        ),
                                                    ]
                                                ),
                                                dbc.CardBody(
                                                    [
                                                        html.Div(id="backtest-runs-table"),
                                                    ]
                                                ),
                                            ]
                                        ),
                                    ],
                                    width=12,
                                ),
                            ],
                            className="mb-4",
                        ),
                        # Comparison Section (collapsible)
                        dbc.Collapse(
                            id="comparison-collapse",
                            is_open=False,
                            children=[
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            dbc.Row(
                                                [
                                                    dbc.Col(
                                                        html.H5(
                                                            "Strategy Comparison", className="mb-0"
                                                        ),
                                                        width=8,
                                                    ),
                                                    dbc.Col(
                                                        dbc.Button(
                                                            "Close",
                                                            id="close-comparison-btn",
                                                            size="sm",
                                                            color="secondary",
                                                        ),
                                                        width=4,
                                                        className="text-end",
                                                    ),
                                                ]
                                            )
                                        ),
                                        dbc.CardBody(
                                            [
                                                html.Div(id="comparison-metrics-table"),
                                                html.Hr(),
                                                dcc.Graph(
                                                    id="comparison-equity-chart",
                                                    config={"displayModeBar": False},
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-4",
                                ),
                            ],
                        ),
                        # Details Row
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        dbc.Card(
                                            [
                                                dbc.CardHeader(
                                                    html.H5(
                                                        "Selected Backtest Details",
                                                        className="mb-0",
                                                    )
                                                ),
                                                dbc.CardBody(
                                                    [
                                                        html.Div(id="backtest-details"),
                                                    ]
                                                ),
                                            ]
                                        ),
                                    ],
                                    width=6,
                                ),
                                dbc.Col(
                                    [
                                        dbc.Card(
                                            [
                                                dbc.CardHeader(
                                                    html.H5("Equity Curve", className="mb-0")
                                                ),
                                                dbc.CardBody(
                                                    [
                                                        dcc.Graph(
                                                            id="backtest-equity-chart",
                                                            config={"displayModeBar": False},
                                                        ),
                                                    ]
                                                ),
                                            ]
                                        ),
                                    ],
                                    width=6,
                                ),
                            ]
                        ),
                        # Trade analysis row (shown when a backtest is selected)
                        dbc.Row(
                            [
                                dbc.Col(
                                    html.Div(id="backtest-trades-detail"),
                                    width=12,
                                ),
                            ],
                            className="mt-3",
                        ),
                    ],
                    label="Backtest",
                    tab_id="tab-backtest",
                ),
            ],
            id="tabs",
            active_tab="tab-charts",
        ),
    ],
    fluid=True,
    className="bg-dark min-vh-100",
)


# ============================================================================
# CALLBACKS
# ============================================================================


@callback(
    [
        Output("metric-status", "children"),
        Output("metric-position", "children"),
        Output("metric-pnl", "children"),
        Output("metric-trades", "children"),
        Output("last-update", "children"),
        Output("metric-strategy-breakdown", "children"),
    ],
    [Input("interval-component", "n_intervals"), Input("refresh-btn", "n_clicks")],
)
def update_metrics(n_intervals, n_clicks):
    """Update metric cards with aggregated data from all bot instances."""
    bot_state = fetch_bot_state()
    now = datetime.now(UTC).strftime("%H:%M:%S UTC")

    if bot_state and bot_state.get("active_instances", 0) > 0:
        # Status card - show number of active instances
        active_count = bot_state.get("active_instances", 0)
        statuses = bot_state.get("statuses", "UNKNOWN")
        status_color = "success" if "RUNNING" in statuses else "warning"
        status_card = create_metric_card(
            "Bot Status",
            f"{active_count} instance(s)",
            statuses,
            status_color,
        )

        # Position card - aggregated across all instances
        position = bot_state.get("total_position", 0)
        position_card = create_metric_card(
            "Total Position",
            f"{position:.6f} BTC" if position > 0 else "No position",
            f"Across {active_count} instance(s)" if active_count > 1 else "",
            "info" if position > 0 else "secondary",
        )

        # P&L card - aggregated
        daily_pnl = bot_state.get("total_daily_pnl", 0)
        total_pnl = bot_state.get("total_pnl", 0)
        pnl_color = "success" if total_pnl >= 0 else "danger"
        pnl_card = create_metric_card(
            "Total P&L", f"{total_pnl:+.2f} USDC", f"Today: {daily_pnl:+.2f}", pnl_color
        )

        # Trades card - aggregated
        trades_count = bot_state.get("total_trades_today", 0)
        trades_card = create_metric_card("Trades Today", str(trades_count), "", "primary")
    else:
        status_card = create_metric_card("Bot Status", "OFFLINE", "", "danger")
        position_card = create_metric_card("Position", "—", "", "secondary")
        pnl_card = create_metric_card("Total P&L", "—", "", "secondary")
        trades_card = create_metric_card("Trades Today", "—", "", "secondary")

    # Per-strategy breakdown
    per_strategy_df = fetch_bot_states_per_strategy()
    if per_strategy_df.empty:
        breakdown = html.Div()
    else:
        cards = []
        for _, row in per_strategy_df.iterrows():
            bot_id = row.get("bot_id", "")
            strategy = row.get("strategy", "")
            status = str(row.get("status", "unknown"))
            total_pnl_s = float(row.get("total_pnl", 0) or 0)
            daily_pnl_s = float(row.get("daily_pnl", 0) or 0)
            trades_today = int(row.get("daily_trades_count", 0) or 0)
            pnl_color_s = "success" if total_pnl_s >= 0 else "danger"
            status_color_s = "success" if status.lower() == "running" else "warning"

            card = dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.H6(strategy, className="mb-1 text-muted"),
                            html.Small(bot_id, className="text-muted d-block mb-1"),
                            dbc.Badge(status.upper(), color=status_color_s, className="me-1"),
                            html.Span(
                                f"P&L: {total_pnl_s:+.2f}",
                                className=f"text-{pnl_color_s} ms-1",
                            ),
                            html.Small(
                                f" | Today: {daily_pnl_s:+.2f} | {trades_today} trades",
                                className="text-muted d-block",
                            ),
                        ],
                        className="p-2",
                    ),
                    className="mb-2",
                ),
                width=4,
            )
            cards.append(card)
        breakdown = dbc.Row(cards)

    return (
        status_card,
        position_card,
        pnl_card,
        trades_card,
        f"Last update: {now}",
        breakdown,
    )


@callback(
    Output("trading-mode-banner", "children"),
    [Input("interval-component", "n_intervals"), Input("refresh-btn", "n_clicks")],
)
def update_trading_mode_banner(n_intervals, n_clicks):
    """Show trading mode, active strategies, and data collection status."""
    # Trading mode from settings
    mode = _settings.trading.mode.value.upper()
    is_live = mode == "LIVE"

    mode_badge = dbc.Badge(
        f"  {mode}  ",
        color="danger" if is_live else "warning",
        className="me-2 fs-6",
    )

    # Per-strategy status from DB
    per_strategy_df = fetch_bot_states_per_strategy()
    strategy_badges = []
    for _, row in per_strategy_df.iterrows():
        strategy = row.get("strategy", "?")
        status = str(row.get("status", "unknown")).upper()
        updated = row.get("updated_at")

        if status == "RUNNING":
            color = "success"
        elif status == "PAUSED":
            color = "warning"
        else:
            color = "secondary"

        # Show how long ago the last heartbeat was
        age_str = ""
        if updated is not None:
            try:
                if hasattr(updated, "tzinfo") and updated.tzinfo is None:
                    from zoneinfo import ZoneInfo

                    updated = updated.replace(tzinfo=ZoneInfo("UTC"))
                age = datetime.now(UTC) - updated
                if age.total_seconds() < 120:
                    age_str = f" ({int(age.total_seconds())}s ago)"
                else:
                    age_str = f" ({int(age.total_seconds() / 60)}m ago)"
            except Exception:
                pass

        strategy_badges.append(
            dbc.Badge(
                f"{strategy}: {status}{age_str}",
                color=color,
                className="me-1",
            )
        )

    if not strategy_badges:
        strategy_badges = [dbc.Badge("No strategies detected", color="secondary", className="me-1")]

    # Data freshness
    data_stats = fetch_data_range_stats()
    data_info = ""
    if data_stats.get("global_latest"):
        latest = data_stats["global_latest"]
        try:
            if hasattr(latest, "tzinfo") and latest.tzinfo is None:
                from zoneinfo import ZoneInfo

                latest = latest.replace(tzinfo=ZoneInfo("UTC"))
            data_age = datetime.now(UTC) - latest
            if data_age.total_seconds() < 300:
                data_info = "Data: live"
            else:
                data_info = f"Data: {int(data_age.total_seconds() / 60)}m stale"
        except Exception:
            pass

    return dbc.Alert(
        [
            html.Div(
                [
                    html.Strong("Mode: "),
                    mode_badge,
                    html.Strong("Strategies: ", className="ms-3"),
                    *strategy_badges,
                    html.Span(
                        f"  |  {data_info}" if data_info else "",
                        className="text-muted ms-2",
                    ),
                ],
                className="d-flex align-items-center flex-wrap",
            ),
        ],
        color="danger" if is_live else "info",
        className="py-2 mb-0",
    )


@callback(
    [
        Output("trades-strategy-filter", "options"),
        Output("positions-strategy-filter", "options"),
        Output("orders-strategy-filter", "options"),
    ],
    [Input("interval-component", "n_intervals"), Input("refresh-btn", "n_clicks")],
)
def update_strategy_filters(n_intervals, n_clicks):
    """Populate strategy filter dropdowns from database."""
    options = fetch_distinct_strategies()
    return options, options, options


@callback(
    Output("price-chart", "figure"),
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-btn", "n_clicks"),
        Input("hours-select", "value"),
    ],
)
def update_chart(n_intervals, n_clicks, hours):
    """Update price chart with market regime subplot."""
    hours = int(hours) if hours else 24
    df, interval, coverage = fetch_best_ohlc_data(hours=hours)
    display_start, display_end = _compute_display_window(df, hours)
    trades_df = _filter_df_to_window(
        fetch_recent_trades(limit=50),
        display_start,
        display_end,
    )
    positions_df = fetch_open_positions()
    regime_df = _filter_df_to_window(
        compute_market_regime(hours=max(hours, 48)),
        display_start,
        display_end,
    )
    return create_candlestick_chart(
        df,
        trades_df,
        positions_df,
        regime_df,
        interval_min=interval,
        coverage=coverage,
        display_start=display_start,
        display_end=display_end,
    )


@callback(
    Output("trades-table", "children"),
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-btn", "n_clicks"),
        Input("trades-strategy-filter", "value"),
    ],
)
def update_trades_table(n_intervals, n_clicks, strategy_filter):
    """Update trades table with strategy filter and entry/exit price distinction."""
    df = fetch_recent_trades(limit=50, strategy_filter=strategy_filter)

    if df.empty:
        return dbc.Alert("No trades found", color="info")

    # Build display rows
    rows = []
    for _, row in df.iterrows():
        timestamp = pd.to_datetime(row["timestamp"]).strftime("%Y-%m-%d %H:%M")
        side = row["side"]
        amount = float(row["amount"]) if row["amount"] else 0
        price = float(row["price"]) if row["price"] else 0
        fee = float(row["fee"]) if row["fee"] else 0
        pnl = float(row["pnl"]) if row["pnl"] else None
        position_entry = (
            float(row["position_entry_price"]) if row.get("position_entry_price") else None
        )
        position_id = row.get("position_id")
        strategy = row.get("strategy", "")

        # Determine entry vs exit price based on side
        # For margin shorts: SELL = open (entry), BUY = close (exit)
        is_short = "bear_short" in (strategy or "")
        if is_short:
            if side == "sell":
                entry_price = price
                exit_price = None
            else:
                entry_price = position_entry
                exit_price = price
        else:
            if side == "buy":
                entry_price = price
                exit_price = None
            else:
                entry_price = position_entry
                exit_price = price

        # Display side with SHORT indicator for margin
        display_side = f"SHORT {side.upper()}" if is_short else side.upper()

        rows.append(
            {
                "timestamp": timestamp,
                "strategy": strategy,
                "side": display_side,
                "amount": f"{amount:.6f}",
                "entry_price": f"${entry_price:.2f}" if entry_price else "—",
                "exit_price": f"${exit_price:.2f}" if exit_price else "—",
                "fee": f"${fee:.4f}" if fee else "—",
                "pnl": f"{pnl:+.2f}" if pnl else "—",
                "position_id": f"#{position_id}" if position_id else "—",
            }
        )

    display_df = pd.DataFrame(rows)

    return dash_table.DataTable(
        data=display_df.to_dict("records"),
        columns=[
            {"name": "Time", "id": "timestamp"},
            {"name": "Strategy", "id": "strategy"},
            {"name": "Side", "id": "side"},
            {"name": "Amount", "id": "amount"},
            {"name": "Entry Price", "id": "entry_price"},
            {"name": "Exit Price", "id": "exit_price"},
            {"name": "Fee", "id": "fee"},
            {"name": "P&L", "id": "pnl"},
            {"name": "Position", "id": "position_id"},
        ],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "border": "1px solid rgb(70, 70, 70)",
            "textAlign": "left",
            "padding": "10px",
            "fontSize": "13px",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": "{side} = BUY"},
                "backgroundColor": "rgba(0, 255, 136, 0.1)",
            },
            {
                "if": {"filter_query": "{side} = SELL"},
                "backgroundColor": "rgba(255, 68, 68, 0.1)",
            },
            {
                "if": {"filter_query": "{pnl} contains '+'"},
                "color": "#00ff88",
            },
            {
                "if": {"filter_query": "{pnl} contains '-'"},
                "color": "#ff4444",
            },
        ],
        page_size=20,
    )


@callback(
    [Output("positions-table", "children"), Output("positions-summary", "children")],
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-btn", "n_clicks"),
        Input("positions-strategy-filter", "value"),
    ],
)
def update_positions_table(n_intervals, n_clicks, strategy_filter):
    """Update open positions table with per-strategy targets and unrealized P&L."""
    df = fetch_open_positions(strategy_filter=strategy_filter)

    if df.empty:
        return (
            dbc.Alert("No open positions", color="secondary"),
            dbc.Badge("0 positions", color="secondary"),
        )

    # Get current price for P&L calculation
    current_price = fetch_current_price("XBT/USDC")

    # Calculate unrealized P&L for each position
    now = datetime.now(UTC)
    rows = []
    total_unrealized_pnl = 0.0

    for _, row in df.iterrows():
        entry_price = float(row["entry_price"])
        amount = float(row["amount"])
        entry_time = pd.to_datetime(row["entry_time"])
        strategy = row.get("strategy", "threshold_rolling")
        trading_mode = row.get("trading_mode", "spot")
        is_short = trading_mode == "margin"

        # Get reference price (may be None for older positions)
        reference_price = float(row["reference_price"]) if row["reference_price"] else None

        # Per-strategy target price calculation
        target_info = compute_target_for_position(strategy, entry_price)
        target_price = target_info["target_price"]
        target_label = target_info["label"]

        # Extract short bot_id + short indicator
        bot_id = row.get("bot_id", "")
        short_bot_id = bot_id.split("_")[-1] if "_" in bot_id else bot_id
        if is_short:
            short_bot_id = f"SHORT {short_bot_id}"

        # Position ID
        position_id = row.get("position_id", "—")

        # Calculate duration
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=UTC)
        duration = now - entry_time
        dur_hours = duration.total_seconds() / 3600
        if dur_hours < 1:
            duration_str = f"{int(duration.total_seconds() / 60)}m"
        elif dur_hours < 24:
            duration_str = f"{dur_hours:.1f}h"
        else:
            duration_str = f"{duration.days}d {int(dur_hours % 24)}h"

        # Calculate unrealized P&L (inverted for margin shorts)
        if current_price:
            if is_short:
                unrealized_pnl = (entry_price - current_price) * amount
                unrealized_pnl_pct = ((entry_price / current_price) - 1) * 100
            else:
                unrealized_pnl = (current_price - entry_price) * amount
                unrealized_pnl_pct = ((current_price / entry_price) - 1) * 100
            total_unrealized_pnl += unrealized_pnl
            # Calculate distance to target (only if fixed target)
            if target_price:
                distance_to_target_pct = ((target_price / current_price) - 1) * 100
            else:
                distance_to_target_pct = None
        else:
            unrealized_pnl = None
            unrealized_pnl_pct = None
            distance_to_target_pct = None

        rows.append(
            {
                "position_id": f"#{position_id}",
                "bot_id": short_bot_id,
                "strategy": strategy,
                "amount": f"{amount:.6f}",
                "entry_price": f"${entry_price:.2f}",
                "reference_price": f"${reference_price:.2f}" if reference_price else "—",
                "target_price": f"${target_price:.2f}" if target_price else target_label,
                "current_price": f"${current_price:.2f}" if current_price else "—",
                "unrealized_pnl": f"{unrealized_pnl:+.2f}" if unrealized_pnl is not None else "—",
                "unrealized_pnl_pct": f"{unrealized_pnl_pct:+.2f}%"
                if unrealized_pnl_pct is not None
                else "—",
                "to_target": f"{distance_to_target_pct:+.2f}%"
                if distance_to_target_pct is not None
                else target_label,
                "duration": duration_str,
            }
        )

    display_df = pd.DataFrame(rows)

    # Summary badge (no global target -- per-strategy now)
    pnl_color = "success" if total_unrealized_pnl >= 0 else "danger"
    summary = html.Span(
        [
            dbc.Badge(f"{len(rows)} position(s)", color="info", className="me-2"),
            dbc.Badge(f"P&L: {total_unrealized_pnl:+.2f} USDC", color=pnl_color),
        ]
    )

    table = dash_table.DataTable(
        data=display_df.to_dict("records"),
        columns=[
            {"name": "#", "id": "position_id"},
            {"name": "Bot", "id": "bot_id"},
            {"name": "Strategy", "id": "strategy"},
            {"name": "Amount", "id": "amount"},
            {"name": "Entry", "id": "entry_price"},
            {"name": "Reference", "id": "reference_price"},
            {"name": "Target", "id": "target_price"},
            {"name": "Current", "id": "current_price"},
            {"name": "P&L", "id": "unrealized_pnl"},
            {"name": "P&L %", "id": "unrealized_pnl_pct"},
            {"name": "To Target", "id": "to_target"},
            {"name": "Duration", "id": "duration"},
        ],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "border": "1px solid rgb(70, 70, 70)",
            "textAlign": "left",
            "padding": "8px",
            "fontSize": "13px",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": "{unrealized_pnl} contains '+'"},
                "color": "#00ff88",
            },
            {
                "if": {"filter_query": "{unrealized_pnl} contains '-'"},
                "color": "#ff4444",
            },
        ],
        page_size=10,
    )

    return table, summary


@callback(
    [Output("orders-table", "children"), Output("orders-summary", "children")],
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-btn", "n_clicks"),
        Input("orders-strategy-filter", "value"),
    ],
)
def update_orders_table(n_intervals, n_clicks, strategy_filter):
    """Update orders table with color coding by status."""
    df = fetch_orders(strategy_filter=strategy_filter)

    if df.empty:
        return (
            dbc.Alert("No orders found", color="secondary"),
            dbc.Badge("0 orders", color="secondary"),
        )

    rows = []
    pending_count = 0
    for _, row in df.iterrows():
        status = str(row.get("status", "")).upper()
        if status in ("PENDING", "PARTIALLY_FILLED"):
            pending_count += 1

        created = pd.to_datetime(row["created_at"]).strftime("%Y-%m-%d %H:%M")
        expires = (
            pd.to_datetime(row["expires_at"]).strftime("%m/%d %H:%M")
            if row.get("expires_at") and pd.notna(row["expires_at"])
            else "—"
        )

        rows.append(
            {
                "order_id": str(row.get("order_id", ""))[:16],
                "bot_id": row.get("bot_id", ""),
                "pair": row.get("pair", ""),
                "side": str(row.get("side", "")).upper(),
                "type": str(row.get("order_type", "")),
                "amount": f"{float(row['amount']):.6f}" if row.get("amount") else "—",
                "price": f"${float(row['price']):.2f}" if row.get("price") else "—",
                "filled": f"{float(row.get('filled_amount', 0) or 0):.6f}",
                "status": status,
                "strategy": row.get("strategy", ""),
                "expires_at": expires,
                "created_at": created,
            }
        )

    display_df = pd.DataFrame(rows)

    summary = html.Span(
        [
            dbc.Badge(f"{len(rows)} order(s)", color="info", className="me-2"),
            dbc.Badge(f"{pending_count} pending", color="warning") if pending_count > 0 else None,
        ]
    )

    table = dash_table.DataTable(
        data=display_df.to_dict("records"),
        columns=[
            {"name": "Order ID", "id": "order_id"},
            {"name": "Bot", "id": "bot_id"},
            {"name": "Pair", "id": "pair"},
            {"name": "Side", "id": "side"},
            {"name": "Type", "id": "type"},
            {"name": "Amount", "id": "amount"},
            {"name": "Price", "id": "price"},
            {"name": "Filled", "id": "filled"},
            {"name": "Status", "id": "status"},
            {"name": "Strategy", "id": "strategy"},
            {"name": "Expires", "id": "expires_at"},
            {"name": "Created", "id": "created_at"},
        ],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "border": "1px solid rgb(70, 70, 70)",
            "textAlign": "left",
            "padding": "8px",
            "fontSize": "13px",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": "{status} = PENDING"},
                "backgroundColor": "rgba(255, 215, 0, 0.15)",
            },
            {
                "if": {"filter_query": "{status} = FILLED"},
                "backgroundColor": "rgba(0, 255, 136, 0.1)",
            },
            {
                "if": {"filter_query": "{status} = CANCELLED"},
                "backgroundColor": "rgba(150, 150, 150, 0.1)",
            },
            {
                "if": {"filter_query": "{status} = EXPIRED"},
                "backgroundColor": "rgba(255, 68, 68, 0.1)",
            },
            {
                "if": {"filter_query": "{side} = BUY"},
                "color": "#00ff88",
            },
            {
                "if": {"filter_query": "{side} = SELL"},
                "color": "#ff4444",
            },
        ],
        page_size=20,
    )

    return table, summary


@callback(
    [Output("sql-results", "children"), Output("query-status", "children")],
    Input("execute-query-btn", "n_clicks"),
    State("sql-input", "value"),
    prevent_initial_call=True,
)
def execute_query(n_clicks, query):
    """Execute custom SQL query."""
    if not query:
        return "", dbc.Badge("No query", color="warning")

    df, error = execute_custom_query(query)

    if error:
        return dbc.Alert(f"Error: {error}", color="danger"), dbc.Badge("Error", color="danger")

    if df is None or df.empty:
        return dbc.Alert("No results", color="info"), dbc.Badge("0 rows", color="info")

    # Convert non-JSON-serializable types (UUID, Timestamp) to strings
    serializable_df = df.head(100).copy()
    for col in serializable_df.columns:
        if serializable_df[col].dtype == "object":
            serializable_df[col] = serializable_df[col].astype(str)
    return dash_table.DataTable(
        data=serializable_df.to_dict("records"),
        columns=[{"name": col, "id": col} for col in serializable_df.columns],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "border": "1px solid rgb(70, 70, 70)",
            "textAlign": "left",
            "padding": "8px",
            "maxWidth": "200px",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
        },
        page_size=20,
        export_format="csv",
    ), dbc.Badge(f"{len(df)} rows", color="success")


@callback(
    Output("stats-content", "children"),
    [Input("interval-component", "n_intervals"), Input("refresh-btn", "n_clicks")],
)
def update_stats(n_intervals, n_clicks):
    """Update statistics tab with data range info."""
    stats = fetch_stats()
    data_range = fetch_data_range_stats()
    last_backtest_at = stats.get("last_backtest_at")
    last_backtest_label = (
        last_backtest_at.strftime("%Y-%m-%d %H:%M") if pd.notna(last_backtest_at) else "—"
    )

    # Create data range table
    intervals_data = data_range.get("intervals", [])
    range_rows = []
    for item in intervals_data:
        interval = item["interval"]
        count = item["candle_count"]
        earliest = item["earliest"]
        latest = item["latest"]
        span_days = (latest - earliest).days if earliest and latest else 0

        range_rows.append(
            {
                "interval": f"{interval} min",
                "count": f"{count:,}",
                "earliest": earliest.strftime("%Y-%m-%d %H:%M") if earliest else "—",
                "latest": latest.strftime("%Y-%m-%d %H:%M") if latest else "—",
                "span": f"{span_days} days",
            }
        )

    data_range_table = (
        dash_table.DataTable(
            data=range_rows,
            columns=[
                {"name": "Interval", "id": "interval"},
                {"name": "Candles", "id": "count"},
                {"name": "Earliest", "id": "earliest"},
                {"name": "Latest", "id": "latest"},
                {"name": "Span", "id": "span"},
            ],
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": "rgb(30, 30, 30)",
                "color": "white",
                "fontWeight": "bold",
            },
            style_cell={
                "backgroundColor": "rgb(50, 50, 50)",
                "color": "white",
                "padding": "8px",
            },
        )
        if range_rows
        else dbc.Alert("No OHLC data available", color="info")
    )

    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader("Available Data Range (XBT/USDC)"),
                                    dbc.CardBody([data_range_table]),
                                ]
                            ),
                        ],
                        width=12,
                        className="mb-4",
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader("OHLC Data"),
                                    dbc.CardBody(
                                        [
                                            html.P(
                                                f"Total candles: {stats.get('total_candles', 0):,}"
                                            ),
                                            html.P(
                                                f"First candle: {stats.get('first_candle', '—')}"
                                            ),
                                            html.P(f"Last candle: {stats.get('last_candle', '—')}"),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader("Runtime / Paper Trading"),
                                    dbc.CardBody(
                                        [
                                            html.P(f"Total trades: {stats.get('total_trades', 0)}"),
                                            html.P(
                                                f"Buys: {stats.get('total_buys', 0)} | Sells: {stats.get('total_sells', 0)}"
                                            ),
                                            html.P(
                                                f"Total P&L: {stats.get('total_pnl', 0):+.2f} USDC"
                                            ),
                                            html.P("Backtests excluded from these numbers"),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader("Backtests"),
                                    dbc.CardBody(
                                        [
                                            html.P(
                                                f"Saved runs: {stats.get('total_backtest_runs', 0)}"
                                            ),
                                            html.P(
                                                "Trades across runs: "
                                                f"{stats.get('total_backtest_trades', 0)}"
                                            ),
                                            html.P(
                                                "Combined net P&L: "
                                                f"{stats.get('total_backtest_pnl', 0):+.2f} USDC"
                                            ),
                                            html.P(f"Last run: {last_backtest_label}"),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
        ]
    )


# Store selected backtest ID
selected_backtest_id = dcc.Store(id="selected-backtest-id", data=None)
delete_status_store = dcc.Store(id="delete-status-store", data=None)


@callback(
    Output("backtest-runs-table", "children"),
    [
        Input("refresh-backtest-btn", "n_clicks"),
        Input("tabs", "active_tab"),
        Input("delete-status-store", "data"),
    ],
)
def update_backtest_runs(n_clicks, active_tab, delete_status):
    """Update backtest runs table."""
    if active_tab != "tab-backtest":
        return dash.no_update

    df = fetch_backtest_runs()

    if df.empty:
        return dbc.Alert(
            [
                html.H5("No backtest runs found"),
                html.P("Run a backtest with --save to see results here:"),
                html.Code(
                    "poetry run python scripts/backtest.py --strategy threshold_rolling --days 7 --save"
                ),
            ],
            color="info",
        )

    # Format for display
    display_df = df.copy()
    display_df["period"] = display_df.apply(
        lambda r: (
            f"{r['start_time'].strftime('%m/%d')} - {r['end_time'].strftime('%m/%d')}"
            if pd.notna(r["start_time"])
            else "—"
        ),
        axis=1,
    )
    display_df["return"] = display_df["total_return_pct"].apply(
        lambda x: f"{float(x):+.2f}%" if pd.notna(x) else "—"
    )
    display_df["win_rate_pct"] = display_df["win_rate"].apply(
        lambda x: f"{float(x) * 100:.1f}%" if pd.notna(x) else "—"
    )
    display_df["pnl"] = display_df["net_pnl"].apply(
        lambda x: f"{float(x):+.2f}" if pd.notna(x) else "—"
    )
    display_df["id_short"] = display_df["id"].apply(lambda x: str(x)[:8] if x else "—")

    # Select columns to display
    columns_to_show = [
        "id_short",
        "run_name",
        "strategy",
        "period",
        "total_trades",
        "win_rate_pct",
        "pnl",
        "return",
    ]
    display_df = display_df[columns_to_show]

    return dash_table.DataTable(
        id="backtest-runs-datatable",
        data=display_df.to_dict("records"),
        columns=[
            {"name": "ID", "id": "id_short"},
            {"name": "Run Name", "id": "run_name"},
            {"name": "Strategy", "id": "strategy"},
            {"name": "Period", "id": "period"},
            {"name": "Trades", "id": "total_trades"},
            {"name": "Win Rate", "id": "win_rate_pct"},
            {"name": "Net P&L", "id": "pnl"},
            {"name": "Return", "id": "return"},
        ],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "border": "1px solid rgb(70, 70, 70)",
            "textAlign": "left",
            "padding": "10px",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": "{return} contains '-'"},
                "color": "#ff4444",
            },
            {
                "if": {"filter_query": "{return} contains '+' && {return} != '+0.00%'"},
                "color": "#00ff88",
            },
        ],
        row_selectable="multi",
        selected_rows=[0] if not df.empty else [],
        page_size=10,
    )


@callback(
    Output("delete-status-store", "data"),
    Input("delete-backtest-btn", "n_clicks"),
    [State("backtest-runs-datatable", "selected_rows"), State("backtest-runs-datatable", "data")],
    prevent_initial_call=True,
)
def handle_delete_backtest(n_clicks, selected_rows, data):
    """Delete selected backtest run."""
    if not n_clicks or not selected_rows or not data:
        return dash.no_update

    selected_row = data[selected_rows[0]]
    short_id = selected_row.get("id_short", "")

    # Get full ID from database
    df = fetch_backtest_runs()
    if df.empty:
        return {"success": False, "message": "No backtests found"}

    matching = df[df["id"].astype(str).str.startswith(short_id)]
    if matching.empty:
        return {"success": False, "message": "Backtest not found"}

    full_id = str(matching.iloc[0]["id"])
    success, message = delete_backtest_run(full_id)

    return {"success": success, "message": message, "timestamp": datetime.now(UTC).isoformat()}


@callback(
    [
        Output("backtest-details", "children"),
        Output("backtest-equity-chart", "figure"),
        Output("backtest-trades-detail", "children"),
    ],
    [Input("backtest-runs-datatable", "selected_rows"), Input("backtest-runs-datatable", "data")],
)
def update_backtest_details(selected_rows, data):
    """Update backtest details when a row is selected."""
    empty_fig = create_backtest_equity_chart(pd.DataFrame())
    empty_trades = html.Div()

    if not selected_rows or not data:
        return (
            dbc.Alert("Select a backtest run to see details", color="secondary"),
            empty_fig,
            empty_trades,
        )

    selected_row = data[selected_rows[0]]
    run_id = selected_row.get("id_short", "")

    # Fetch full backtest data
    df = fetch_backtest_runs()
    if df.empty:
        return dbc.Alert("Backtest data not found", color="warning"), empty_fig, empty_trades

    # Find matching row by id prefix
    matching = df[df["id"].astype(str).str.startswith(run_id)]
    if matching.empty:
        return dbc.Alert("Backtest not found", color="warning"), empty_fig, empty_trades

    bt = matching.iloc[0]

    # Extract win/loss analysis metrics from backtest_runs
    avg_win = float(bt.get("average_win", 0) or 0)
    avg_loss = float(bt.get("average_loss", 0) or 0)
    profit_factor = float(bt.get("profit_factor", 0) or 0)
    net_pnl = float(bt.get("net_pnl", 0) or 0)
    total_fees = float(bt.get("total_fees", 0) or 0)

    # Create details card with additional win/loss analysis
    details = html.Div(
        [
            html.H6(bt.get("run_name", "Unknown"), className="text-primary"),
            html.Hr(),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.P([html.Strong("Strategy: "), bt.get("strategy", "—")]),
                            html.P([html.Strong("Pair: "), bt.get("pair", "—")]),
                            html.P(
                                [
                                    html.Strong("Period: "),
                                    f"{bt.get('start_time', '—')} to {bt.get('end_time', '—')}",
                                ]
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            html.P(
                                [
                                    html.Strong("Starting: "),
                                    f"{float(bt.get('starting_balance', 0)):.2f} USDC",
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Ending: "),
                                    f"{float(bt.get('ending_balance', 0)):.2f} USDC",
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Return: "),
                                    f"{float(bt.get('total_return_pct', 0)):+.2f}%",
                                ]
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
            html.Hr(),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.P([html.Strong("Trades: "), str(bt.get("total_trades", 0))]),
                            html.P(
                                [
                                    html.Strong("Wins/Losses: "),
                                    f"{bt.get('winning_trades', 0)}/{bt.get('losing_trades', 0)}",
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Win Rate: "),
                                    f"{float(bt.get('win_rate', 0)) * 100:.1f}%",
                                ]
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            html.P(
                                [
                                    html.Strong("Avg Win: "),
                                    html.Span(
                                        f"+{avg_win:.2f} USDC",
                                        className="text-success",
                                    ),
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Avg Loss: "),
                                    html.Span(
                                        f"{avg_loss:.2f} USDC",
                                        className="text-danger",
                                    ),
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Profit Factor: "),
                                    f"{profit_factor:.2f}",
                                ]
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
            html.Hr(),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.P(
                                [
                                    html.Strong("Max Drawdown: "),
                                    f"{float(bt.get('max_drawdown_pct', 0)):.2f}%",
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Sharpe Ratio: "),
                                    f"{float(bt.get('sharpe_ratio', 0)):.2f}",
                                ]
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            html.P(
                                [
                                    html.Strong("Net P&L: "),
                                    html.Span(
                                        f"{net_pnl:+.2f} USDC",
                                        className="text-success" if net_pnl >= 0 else "text-danger",
                                    ),
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Total Fees: "),
                                    f"{total_fees:.2f} USDC",
                                ]
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
        ]
    )

    # Fetch trades for equity curve and trade detail table
    trades_df = fetch_backtest_trades(str(bt.get("id", "")))
    equity_fig = create_backtest_equity_chart(trades_df, float(bt.get("starting_balance", 1000)))

    # Build trade detail table
    trades_detail = _build_backtest_trades_table(trades_df)

    return details, equity_fig, trades_detail


def _build_backtest_trades_table(trades_df: pd.DataFrame):
    """Build a detailed trade analysis table from backtest trades.

    Pairs BUY/SELL trades to show entry/exit price, P&L, and holding time.
    Includes summary metrics (biggest win, biggest loss, avg holding time).
    """
    if trades_df.empty:
        return html.Div()

    # Pair BUY/SELL trades
    paired_trades = []
    pending_buys = []

    for _, trade in trades_df.iterrows():
        side = str(trade.get("side", "")).lower()
        if side == "buy":
            pending_buys.append(trade)
        elif side == "sell" and pending_buys:
            buy = pending_buys.pop(0)
            entry_price = float(buy["price"])
            exit_price = float(trade["price"])
            pnl = float(trade["pnl"]) if pd.notna(trade.get("pnl")) else 0
            buy_time = pd.to_datetime(buy["timestamp"])
            sell_time = pd.to_datetime(trade["timestamp"])
            holding = sell_time - buy_time
            holding_min = holding.total_seconds() / 60

            paired_trades.append(
                {
                    "entry_time": buy_time.strftime("%m/%d %H:%M"),
                    "exit_time": sell_time.strftime("%m/%d %H:%M"),
                    "entry_price": f"${entry_price:,.2f}",
                    "exit_price": f"${exit_price:,.2f}",
                    "pnl": f"{pnl:+.2f}",
                    "pnl_raw": pnl,
                    "return_pct": f"{((exit_price - entry_price) / entry_price) * 100:+.2f}%",
                    "holding": (
                        f"{int(holding_min)}m" if holding_min < 60 else f"{holding_min / 60:.1f}h"
                    ),
                }
            )

    if not paired_trades:
        return dbc.Alert("No completed round-trips found", color="secondary", className="mt-3")

    paired_df = pd.DataFrame(paired_trades)
    pnl_values = [t["pnl_raw"] for t in paired_trades]
    wins = [p for p in pnl_values if p > 0]
    losses = [p for p in pnl_values if p <= 0]

    # Summary metrics
    biggest_win = max(pnl_values) if pnl_values else 0
    biggest_loss = min(pnl_values) if pnl_values else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    summary = dbc.Row(
        [
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Biggest Win", className="text-muted"),
                            html.H5(
                                f"+{biggest_win:.2f}",
                                className="text-success mb-0",
                            ),
                        ],
                        className="p-2 text-center",
                    ),
                ),
                width=3,
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Biggest Loss", className="text-muted"),
                            html.H5(
                                f"{biggest_loss:.2f}",
                                className="text-danger mb-0",
                            ),
                        ],
                        className="p-2 text-center",
                    ),
                ),
                width=3,
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Avg Win", className="text-muted"),
                            html.H5(
                                f"+{avg_win:.2f}",
                                className="text-success mb-0",
                            ),
                        ],
                        className="p-2 text-center",
                    ),
                ),
                width=3,
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Avg Loss", className="text-muted"),
                            html.H5(
                                f"{avg_loss:.2f}",
                                className="text-danger mb-0",
                            ),
                        ],
                        className="p-2 text-center",
                    ),
                ),
                width=3,
            ),
        ],
        className="mb-2",
    )

    table = dash_table.DataTable(
        data=paired_df.drop(columns=["pnl_raw"]).to_dict("records"),
        columns=[
            {"name": "Entry", "id": "entry_time"},
            {"name": "Exit", "id": "exit_time"},
            {"name": "Entry $", "id": "entry_price"},
            {"name": "Exit $", "id": "exit_price"},
            {"name": "Return", "id": "return_pct"},
            {"name": "P&L", "id": "pnl"},
            {"name": "Duration", "id": "holding"},
        ],
        style_table={"overflowX": "auto", "maxHeight": "400px", "overflowY": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "border": "1px solid rgb(70, 70, 70)",
            "textAlign": "center",
            "padding": "8px",
            "fontSize": "12px",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": "{pnl} contains '+'"},
                "color": "#00ff88",
            },
            {
                "if": {"filter_query": "{pnl} contains '-'"},
                "color": "#ff4444",
            },
        ],
        page_size=15,
    )

    return dbc.Card(
        [
            dbc.CardHeader(
                html.H5(
                    f"Trade Details ({len(paired_trades)} round-trips)",
                    className="mb-0",
                )
            ),
            dbc.CardBody([summary, table]),
        ]
    )


# ============================================================================
# DATA RANGE CALLBACK
# ============================================================================


@callback(
    Output("backtest-data-range", "children"),
    Input("tabs", "active_tab"),
)
def update_data_range_badge(active_tab):
    """Show data range badge in Backtest tab."""
    if active_tab != "tab-backtest":
        return dash.no_update

    stats = fetch_data_range_stats()

    if not stats.get("global_earliest"):
        return dbc.Alert("No market data available", color="warning", className="mb-2")

    earliest = stats["global_earliest"].strftime("%Y-%m-%d")
    latest = stats["global_latest"].strftime("%Y-%m-%d")
    total = stats["total_candles"]

    # Create interval breakdown
    intervals_text = ", ".join(
        [f"{item['interval']}min: {item['candle_count']:,}" for item in stats.get("intervals", [])]
    )

    return html.Div(
        [
            dbc.Badge(f"Data: {earliest} to {latest}", color="info", className="me-2"),
            dbc.Badge(f"{total:,} candles", color="secondary", className="me-2"),
            html.Small(f"({intervals_text})", className="text-muted"),
        ]
    )


# ============================================================================
# BACKTEST EXECUTION CALLBACKS
# ============================================================================


@callback(
    [
        Output("backtest-progress-interval", "disabled"),
        Output("run-backtest-btn", "disabled"),
    ],
    Input("run-backtest-btn", "n_clicks"),
    [
        State("backtest-strategy-select", "value"),
        State("backtest-days-input", "value"),
        State("backtest-interval-select", "value"),
        State("backtest-pair-select", "value"),
    ],
    prevent_initial_call=True,
)
def start_backtest(n_clicks, strategy, days, interval, pair):
    """Start backtest in background thread."""
    global _backtest_thread, _backtest_progress

    if _backtest_progress.get("running"):
        return dash.no_update, dash.no_update

    _backtest_thread = threading.Thread(
        target=run_backtest_in_thread,
        args=(strategy, int(days), int(interval), pair),
        daemon=True,
    )
    _backtest_thread.start()

    return False, True  # Enable interval, disable button


@callback(
    [
        Output("backtest-progress", "children"),
        Output("backtest-progress-interval", "disabled", allow_duplicate=True),
        Output("run-backtest-btn", "disabled", allow_duplicate=True),
        Output("backtest-runs-table", "children", allow_duplicate=True),
    ],
    Input("backtest-progress-interval", "n_intervals"),
    prevent_initial_call=True,
)
def update_backtest_progress(n_intervals):
    """Poll backtest progress."""
    global _backtest_progress

    if _backtest_progress.get("error"):
        error_msg = _backtest_progress["error"]
        _backtest_progress = {"running": False, "progress": 0, "message": "", "error": None}
        return (
            dbc.Alert(f"Error: {error_msg}", color="danger"),
            True,
            False,
            dash.no_update,
        )

    if not _backtest_progress.get("running"):
        if _backtest_progress.get("progress") == 100:
            # Completed - refresh table
            _backtest_progress = {"running": False, "progress": 0, "message": "", "error": None}
            # Trigger table refresh by returning updated content
            df = fetch_backtest_runs()
            if not df.empty:
                # Re-create table (simplified refresh)
                return (
                    dbc.Alert("Backtest completed!", color="success", dismissable=True),
                    True,
                    False,
                    update_backtest_runs_table(df),
                )
            return (
                dbc.Alert("Backtest completed!", color="success", dismissable=True),
                True,
                False,
                dash.no_update,
            )
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    progress = _backtest_progress.get("progress", 0)
    message = _backtest_progress.get("message", "Running...")

    return (
        html.Div(
            [
                dbc.Progress(value=progress, striped=True, animated=True, className="mb-2"),
                html.Small(message, className="text-muted"),
            ]
        ),
        False,
        True,
        dash.no_update,
    )


def update_backtest_runs_table(df: pd.DataFrame) -> dash_table.DataTable:
    """Helper to create backtest runs DataTable."""
    display_df = df.copy()
    display_df["period"] = display_df.apply(
        lambda r: (
            f"{r['start_time'].strftime('%m/%d')} - {r['end_time'].strftime('%m/%d')}"
            if pd.notna(r["start_time"])
            else "—"
        ),
        axis=1,
    )
    display_df["return"] = display_df["total_return_pct"].apply(
        lambda x: f"{float(x):+.2f}%" if pd.notna(x) else "—"
    )
    display_df["win_rate_pct"] = display_df["win_rate"].apply(
        lambda x: f"{float(x) * 100:.1f}%" if pd.notna(x) else "—"
    )
    display_df["pnl"] = display_df["net_pnl"].apply(
        lambda x: f"{float(x):+.2f}" if pd.notna(x) else "—"
    )
    display_df["id_short"] = display_df["id"].apply(lambda x: str(x)[:8] if x else "—")

    columns_to_show = [
        "id_short",
        "run_name",
        "strategy",
        "period",
        "total_trades",
        "win_rate_pct",
        "pnl",
        "return",
    ]
    display_df = display_df[columns_to_show]

    return dash_table.DataTable(
        id="backtest-runs-datatable",
        data=display_df.to_dict("records"),
        columns=[
            {"name": "ID", "id": "id_short"},
            {"name": "Run Name", "id": "run_name"},
            {"name": "Strategy", "id": "strategy"},
            {"name": "Period", "id": "period"},
            {"name": "Trades", "id": "total_trades"},
            {"name": "Win Rate", "id": "win_rate_pct"},
            {"name": "Net P&L", "id": "pnl"},
            {"name": "Return", "id": "return"},
        ],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "border": "1px solid rgb(70, 70, 70)",
            "textAlign": "left",
            "padding": "10px",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": "{return} contains '-'"},
                "color": "#ff4444",
            },
            {
                "if": {"filter_query": "{return} contains '+' && {return} != '+0.00%'"},
                "color": "#00ff88",
            },
        ],
        row_selectable="multi",
        selected_rows=[0] if not df.empty else [],
        page_size=10,
    )


# ============================================================================
# COMPARISON CALLBACKS
# ============================================================================


def create_comparison_equity_chart(runs_data: list[dict]) -> go.Figure:
    """Create overlaid equity curves for multiple backtests."""
    fig = go.Figure()

    colors = ["#00ff88", "#ff4444", "#4488ff", "#ffaa00", "#aa44ff"]

    for i, run in enumerate(runs_data):
        trades_df = fetch_backtest_trades(str(run["id"]))
        if trades_df.empty:
            continue

        # Calculate equity curve
        starting_balance = float(run["starting_balance"])
        equity = [starting_balance]
        timestamps = [trades_df["timestamp"].iloc[0]]

        cumulative_pnl = 0
        for _, trade in trades_df.iterrows():
            if trade["pnl"] is not None and pd.notna(trade["pnl"]):
                cumulative_pnl += float(trade["pnl"])
            equity.append(starting_balance + cumulative_pnl)
            timestamps.append(trade["timestamp"])

        run_name = run.get("run_name", "Unknown")
        if len(run_name) > 20:
            run_name = run_name[:20] + "..."

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=equity,
                mode="lines",
                name=f"{run['strategy']} ({run_name})",
                line={"color": colors[i % len(colors)], "width": 2},
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin={"l": 50, "r": 50, "t": 30, "b": 50},
        xaxis={"gridcolor": "rgba(255,255,255,0.1)", "title": "Time"},
        yaxis={"gridcolor": "rgba(255,255,255,0.1)", "title": "Equity (USDC)"},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    )

    return fig


def create_comparison_metrics_table(runs: list[dict]) -> dash_table.DataTable:
    """Create side-by-side metrics comparison table."""
    metrics = [
        ("Strategy", "strategy"),
        ("Period", None),
        ("Total Return %", "total_return_pct"),
        ("Net P&L", "net_pnl"),
        ("Win Rate %", "win_rate"),
        ("Total Trades", "total_trades"),
        ("Sharpe Ratio", "sharpe_ratio"),
        ("Max Drawdown %", "max_drawdown_pct"),
        ("Profit Factor", "profit_factor"),
    ]

    rows = []
    for metric_name, key in metrics:
        row = {"Metric": metric_name}
        for i, run in enumerate(runs):
            col_name = f"Run {i + 1}"
            if key is None and metric_name == "Period":
                start = (
                    run["start_time"].strftime("%m/%d") if pd.notna(run.get("start_time")) else "?"
                )
                end = run["end_time"].strftime("%m/%d") if pd.notna(run.get("end_time")) else "?"
                row[col_name] = f"{start} - {end}"
            elif key == "win_rate":
                val = run.get(key)
                row[col_name] = f"{float(val) * 100:.1f}%" if pd.notna(val) else "—"
            elif key in ["total_return_pct", "max_drawdown_pct"]:
                val = run.get(key)
                row[col_name] = f"{float(val):+.2f}%" if pd.notna(val) else "—"
            elif key == "net_pnl":
                val = run.get(key)
                row[col_name] = f"{float(val):+.2f}" if pd.notna(val) else "—"
            elif key in ["sharpe_ratio", "profit_factor"]:
                val = run.get(key)
                row[col_name] = f"{float(val):.2f}" if pd.notna(val) else "—"
            else:
                row[col_name] = str(run.get(key, "—"))
        rows.append(row)

    columns = [{"name": "Metric", "id": "Metric"}]
    columns.extend([{"name": f"Run {i + 1}", "id": f"Run {i + 1}"} for i in range(len(runs))])

    return dash_table.DataTable(
        data=rows,
        columns=columns,
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "rgb(30, 30, 30)",
            "color": "white",
            "fontWeight": "bold",
        },
        style_cell={
            "backgroundColor": "rgb(50, 50, 50)",
            "color": "white",
            "padding": "10px",
        },
    )


@callback(
    [
        Output("comparison-collapse", "is_open"),
        Output("comparison-metrics-table", "children"),
        Output("comparison-equity-chart", "figure"),
    ],
    [
        Input("compare-backtest-btn", "n_clicks"),
        Input("close-comparison-btn", "n_clicks"),
    ],
    [
        State("backtest-runs-datatable", "selected_rows"),
        State("backtest-runs-datatable", "data"),
    ],
    prevent_initial_call=True,
)
def handle_comparison(compare_clicks, close_clicks, selected_rows, data):
    """Show/hide comparison view."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update

    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger == "close-comparison-btn":
        return False, dash.no_update, dash.no_update

    if not selected_rows or len(selected_rows) < 2:
        return (
            True,
            dbc.Alert("Select at least 2 runs to compare", color="warning"),
            go.Figure(),
        )

    # Get selected run IDs
    selected_ids = [data[i]["id_short"] for i in selected_rows]

    # Fetch full run data
    df = fetch_backtest_runs()
    runs = []
    for short_id in selected_ids:
        matching = df[df["id"].astype(str).str.startswith(short_id)]
        if not matching.empty:
            runs.append(matching.iloc[0].to_dict())

    if len(runs) < 2:
        return (
            True,
            dbc.Alert("Could not find selected runs", color="warning"),
            go.Figure(),
        )

    # Create comparison views
    metrics_table = create_comparison_metrics_table(runs)
    equity_chart = create_comparison_equity_chart(runs)

    return True, metrics_table, equity_chart


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KrakenBot Dashboard")
    parser.add_argument("--port", type=int, default=8050, help="Port to run on")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    # Quick data check
    try:
        with engine.connect() as conn:
            trade_count = conn.execute(
                text("SELECT COUNT(*) FROM trades_history WHERE strategy NOT LIKE 'backtest_%'")
            ).scalar()
            pos_count = conn.execute(
                text("SELECT COUNT(*) FROM open_positions WHERE status = 'OPEN'")
            ).scalar()
            backtest_runs = conn.execute(text("SELECT COUNT(*) FROM backtest_runs")).scalar()
        data_info = (
            f"  Data: {trade_count} runtime/paper trades, {pos_count} open positions, "
            f"{backtest_runs} backtest runs"
        )
    except Exception:
        data_info = "  Data: could not query trades/positions"

    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║           KrakenBot Dashboard                            ║
    ╠══════════════════════════════════════════════════════════╣
    ║  URL: http://localhost:{args.port}                           ║
    ║  Auto-refresh: Every 10 seconds                          ║
    ╚══════════════════════════════════════════════════════════╝
    {data_info}
    """)

    # Force Dash to process all registered callbacks before serving requests
    app._setup_server()

    app.run(debug=args.debug, port=args.port, host="127.0.0.1")
