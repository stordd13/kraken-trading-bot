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

    # With SSH tunnel (from Mac to Hetzner)
    ssh -L 5432:localhost:5432 bruno@<IP> -N &
    python scripts/dashboard.py
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
import sys
import threading

import dash
from dash import Input, Output, State, callback, dash_table, dcc, html
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Database URL
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://krakenbot:bruno@localhost:5432/krakenbot"
).replace("+asyncpg", "")  # Use sync driver for Dash

# Create sync engine
engine = create_engine(DATABASE_URL)

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
)

# ============================================================================
# DATA FETCHING FUNCTIONS
# ============================================================================


def fetch_bot_state() -> dict | None:
    """Fetch current bot state."""
    query = """
    SELECT bot_id, strategy, status, position_size, entry_price,
           daily_pnl, total_pnl, daily_trades_count,
           last_signal_at, last_trade_at, error_message, updated_at
    FROM bot_state
    ORDER BY updated_at DESC
    LIMIT 1
    """
    try:
        df = pd.read_sql(query, engine)
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception as e:
        print(f"Error fetching bot state: {e}")
        return None


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
        df = pd.read_sql(
            text(query.replace(":hours", str(hours))),
            engine,
            params={"pair": pair, "interval": interval},
        )
        return df
    except Exception as e:
        print(f"Error fetching OHLC: {e}")
        return pd.DataFrame()


def fetch_recent_trades(limit: int = 20) -> pd.DataFrame:
    """Fetch recent trades."""
    query = f"""
    SELECT timestamp, pair, side, amount, price, fee, pnl, strategy, status
    FROM trades_history
    ORDER BY timestamp DESC
    LIMIT {limit}
    """
    try:
        return pd.read_sql(query, engine)
    except Exception as e:
        print(f"Error fetching trades: {e}")
        return pd.DataFrame()


def fetch_stats() -> dict:
    """Fetch overall statistics."""
    stats = {}

    try:
        # OHLC stats
        result = pd.read_sql(
            """
            SELECT
                COUNT(*) as total_candles,
                MIN(timestamp) as first_candle,
                MAX(timestamp) as last_candle
            FROM market_data_ohlc
        """,
            engine,
        )
        if not result.empty:
            stats["total_candles"] = int(result.iloc[0]["total_candles"])
            stats["first_candle"] = result.iloc[0]["first_candle"]
            stats["last_candle"] = result.iloc[0]["last_candle"]

        # Trade stats
        result = pd.read_sql(
            """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN side = 'buy' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN side = 'sell' THEN 1 ELSE 0 END) as sells,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM trades_history
        """,
            engine,
        )
        if not result.empty:
            stats["total_trades"] = int(result.iloc[0]["total_trades"])
            stats["total_buys"] = int(result.iloc[0]["buys"] or 0)
            stats["total_sells"] = int(result.iloc[0]["sells"] or 0)
            stats["total_pnl"] = float(result.iloc[0]["total_pnl"] or 0)

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
            df = pd.read_sql(query, engine)
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


def fetch_open_positions() -> pd.DataFrame:
    """Fetch open positions (buys without matching sells).

    Uses FIFO matching: calculates net position by pair and computes
    weighted average entry price from unmatched buy trades.
    """
    query = """
    WITH trade_flows AS (
        SELECT
            pair,
            side,
            timestamp,
            amount,
            price,
            strategy,
            -- Running sum of position changes
            SUM(CASE WHEN side = 'buy' THEN amount ELSE -amount END)
                OVER (PARTITION BY pair ORDER BY timestamp) as running_position
        FROM trades_history
        WHERE status = 'filled'
          AND strategy NOT LIKE 'backtest_%'
        ORDER BY pair, timestamp
    ),
    current_positions AS (
        SELECT
            pair,
            SUM(CASE WHEN side = 'buy' THEN amount ELSE -amount END) as net_position
        FROM trades_history
        WHERE status = 'filled'
          AND strategy NOT LIKE 'backtest_%'
        GROUP BY pair
        HAVING SUM(CASE WHEN side = 'buy' THEN amount ELSE -amount END) > 0.00000001
    ),
    -- Get the most recent buys that make up the current position
    recent_buys AS (
        SELECT
            t.pair,
            t.timestamp as entry_time,
            t.amount,
            t.price,
            t.strategy,
            SUM(t.amount) OVER (PARTITION BY t.pair ORDER BY t.timestamp DESC) as cumulative_amount
        FROM trades_history t
        INNER JOIN current_positions cp ON t.pair = cp.pair
        WHERE t.side = 'buy'
          AND t.status = 'filled'
          AND t.strategy NOT LIKE 'backtest_%'
        ORDER BY t.pair, t.timestamp DESC
    ),
    -- Calculate weighted average entry price for open position
    position_details AS (
        SELECT
            rb.pair,
            cp.net_position as amount,
            MIN(rb.entry_time) as entry_time,
            SUM(rb.amount * rb.price) / SUM(rb.amount) as avg_entry_price,
            MAX(rb.strategy) as strategy
        FROM recent_buys rb
        INNER JOIN current_positions cp ON rb.pair = cp.pair
        WHERE rb.cumulative_amount <= cp.net_position * 1.5  -- Include relevant buys
        GROUP BY rb.pair, cp.net_position
    )
    SELECT
        pair,
        amount,
        avg_entry_price as entry_price,
        entry_time,
        strategy
    FROM position_details
    ORDER BY entry_time DESC
    """
    try:
        return pd.read_sql(query, engine)
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
        return pd.read_sql(query, engine)
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
        df = pd.read_sql(query, engine)
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

            await bt_engine.save_to_database(pair)
            await bt_engine.save_trades_to_database(str(bt_engine.backtest_run.id), pair)

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


def create_candlestick_chart(df: pd.DataFrame, trades_df: pd.DataFrame = None) -> go.Figure:
    """Create candlestick chart with trades overlay."""
    fig = go.Figure()

    if not df.empty:
        fig.add_trace(
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
            fig.add_trace(
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
            fig.add_trace(
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

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=450,
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
        # Auto-refresh interval
        dcc.Interval(id="interval-component", interval=10 * 1000, n_intervals=0),
        # Store for delete status
        dcc.Store(id="delete-status-store", data=None),
        # Metrics Row
        dbc.Row(
            [
                dbc.Col(html.Div(id="metric-status"), width=3),
                dbc.Col(html.Div(id="metric-position"), width=3),
                dbc.Col(html.Div(id="metric-pnl"), width=3),
                dbc.Col(html.Div(id="metric-trades"), width=3),
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
                                dbc.CardHeader(html.H5("Recent Trades", className="mb-0")),
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
                                                width=8,
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
                # Tab 4: SQL Explorer
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
                                                    html.Code("market_data_ticks"), className="mb-1"
                                                ),
                                                html.Li(
                                                    html.Code("trades_history"), className="mb-1"
                                                ),
                                                html.Li(html.Code("bot_state"), className="mb-1"),
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
                                                            options=[
                                                                {
                                                                    "label": "Threshold",
                                                                    "value": "threshold",
                                                                },
                                                                {
                                                                    "label": "Threshold Multi",
                                                                    "value": "threshold_multi",
                                                                },
                                                                {
                                                                    "label": "Threshold Rolling",
                                                                    "value": "threshold_rolling",
                                                                },
                                                                {
                                                                    "label": "Technical Indicator",
                                                                    "value": "technical_indicator",
                                                                },
                                                            ],
                                                            value="threshold",
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
    ],
    [Input("interval-component", "n_intervals"), Input("refresh-btn", "n_clicks")],
)
def update_metrics(n_intervals, n_clicks):
    """Update metric cards."""
    bot_state = fetch_bot_state()
    now = datetime.now(UTC).strftime("%H:%M:%S UTC")

    if bot_state:
        status = bot_state.get("status", "unknown")
        status_color = (
            "success" if status == "running" else "warning" if status == "stopped" else "danger"
        )

        status_card = create_metric_card(
            "Bot Status", status.upper(), bot_state.get("strategy", ""), status_color
        )

        position = float(bot_state.get("position_size", 0) or 0)
        entry = bot_state.get("entry_price")
        position_card = create_metric_card(
            "Position",
            f"{position:.6f} BTC" if position > 0 else "No position",
            f"Entry: {float(entry):.2f}" if entry else "",
            "info" if position > 0 else "secondary",
        )

        daily_pnl = float(bot_state.get("daily_pnl", 0) or 0)
        total_pnl = float(bot_state.get("total_pnl", 0) or 0)
        pnl_color = "success" if total_pnl >= 0 else "danger"
        pnl_card = create_metric_card(
            "Total P&L", f"{total_pnl:+.2f} USDC", f"Today: {daily_pnl:+.2f}", pnl_color
        )

        trades_count = int(bot_state.get("daily_trades_count", 0) or 0)
        trades_card = create_metric_card("Trades Today", str(trades_count), "", "primary")
    else:
        status_card = create_metric_card("Bot Status", "OFFLINE", "", "danger")
        position_card = create_metric_card("Position", "—", "", "secondary")
        pnl_card = create_metric_card("Total P&L", "—", "", "secondary")
        trades_card = create_metric_card("Trades Today", "—", "", "secondary")

    return status_card, position_card, pnl_card, trades_card, f"Last update: {now}"


@callback(
    Output("price-chart", "figure"),
    [
        Input("interval-component", "n_intervals"),
        Input("refresh-btn", "n_clicks"),
        Input("hours-select", "value"),
    ],
)
def update_chart(n_intervals, n_clicks, hours):
    """Update price chart."""
    hours = int(hours) if hours else 24
    df = fetch_ohlc_data(hours=hours)
    trades_df = fetch_recent_trades(limit=50)
    return create_candlestick_chart(df, trades_df)


@callback(
    Output("trades-table", "children"),
    [Input("interval-component", "n_intervals"), Input("refresh-btn", "n_clicks")],
)
def update_trades_table(n_intervals, n_clicks):
    """Update trades table."""
    df = fetch_recent_trades(limit=50)

    if df.empty:
        return dbc.Alert("No trades found", color="info")

    # Format columns
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
    df["price"] = df["price"].apply(lambda x: f"{float(x):.2f}" if x else "—")
    df["amount"] = df["amount"].apply(lambda x: f"{float(x):.6f}" if x else "—")
    df["pnl"] = df["pnl"].apply(lambda x: f"{float(x):+.2f}" if x else "—")
    df["fee"] = df["fee"].apply(lambda x: f"{float(x):.4f}" if x else "—")

    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": col.upper(), "id": col} for col in df.columns],
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
                "if": {"filter_query": "{side} = buy"},
                "backgroundColor": "rgba(0, 255, 136, 0.1)",
            },
            {
                "if": {"filter_query": "{side} = sell"},
                "backgroundColor": "rgba(255, 68, 68, 0.1)",
            },
        ],
        page_size=20,
    )


@callback(
    [Output("positions-table", "children"), Output("positions-summary", "children")],
    [Input("interval-component", "n_intervals"), Input("refresh-btn", "n_clicks")],
)
def update_positions_table(n_intervals, n_clicks):
    """Update open positions table with unrealized P&L."""
    df = fetch_open_positions()

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

        # Calculate duration
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=UTC)
        duration = now - entry_time
        hours = duration.total_seconds() / 3600
        if hours < 1:
            duration_str = f"{int(duration.total_seconds() / 60)}m"
        elif hours < 24:
            duration_str = f"{hours:.1f}h"
        else:
            duration_str = f"{duration.days}d {int(hours % 24)}h"

        # Calculate unrealized P&L
        if current_price:
            unrealized_pnl = (current_price - entry_price) * amount
            unrealized_pnl_pct = ((current_price / entry_price) - 1) * 100
            total_unrealized_pnl += unrealized_pnl
        else:
            unrealized_pnl = None
            unrealized_pnl_pct = None

        rows.append(
            {
                "pair": row["pair"],
                "amount": f"{amount:.6f}",
                "entry_price": f"{entry_price:.2f}",
                "current_price": f"{current_price:.2f}" if current_price else "—",
                "unrealized_pnl": f"{unrealized_pnl:+.2f}" if unrealized_pnl is not None else "—",
                "unrealized_pnl_pct": f"{unrealized_pnl_pct:+.2f}%"
                if unrealized_pnl_pct is not None
                else "—",
                "duration": duration_str,
                "strategy": row["strategy"],
            }
        )

    display_df = pd.DataFrame(rows)

    # Summary badge
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
            {"name": "Pair", "id": "pair"},
            {"name": "Amount", "id": "amount"},
            {"name": "Entry Price", "id": "entry_price"},
            {"name": "Current Price", "id": "current_price"},
            {"name": "P&L (USDC)", "id": "unrealized_pnl"},
            {"name": "P&L (%)", "id": "unrealized_pnl_pct"},
            {"name": "Duration", "id": "duration"},
            {"name": "Strategy", "id": "strategy"},
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

    return dash_table.DataTable(
        data=df.head(100).to_dict("records"),
        columns=[{"name": col, "id": col} for col in df.columns],
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
                                    dbc.CardHeader("Trading"),
                                    dbc.CardBody(
                                        [
                                            html.P(f"Total trades: {stats.get('total_trades', 0)}"),
                                            html.P(
                                                f"Buys: {stats.get('total_buys', 0)} | Sells: {stats.get('total_sells', 0)}"
                                            ),
                                            html.P(
                                                f"Total P&L: {stats.get('total_pnl', 0):+.2f} USDC"
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
        lambda r: f"{r['start_time'].strftime('%m/%d')} - {r['end_time'].strftime('%m/%d')}"
        if pd.notna(r["start_time"])
        else "—",
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
    [Output("backtest-details", "children"), Output("backtest-equity-chart", "figure")],
    [Input("backtest-runs-datatable", "selected_rows"), Input("backtest-runs-datatable", "data")],
)
def update_backtest_details(selected_rows, data):
    """Update backtest details when a row is selected."""
    empty_fig = create_backtest_equity_chart(pd.DataFrame())

    if not selected_rows or not data:
        return dbc.Alert("Select a backtest run to see details", color="secondary"), empty_fig

    selected_row = data[selected_rows[0]]
    run_id = selected_row.get("id_short", "")

    # Fetch full backtest data
    df = fetch_backtest_runs()
    if df.empty:
        return dbc.Alert("Backtest data not found", color="warning"), empty_fig

    # Find matching row by id prefix
    matching = df[df["id"].astype(str).str.startswith(run_id)]
    if matching.empty:
        return dbc.Alert("Backtest not found", color="warning"), empty_fig

    bt = matching.iloc[0]

    # Create details card
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
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            html.P(
                                [
                                    html.Strong("Win Rate: "),
                                    f"{float(bt.get('win_rate', 0)) * 100:.1f}%",
                                ]
                            ),
                            html.P(
                                [
                                    html.Strong("Profit Factor: "),
                                    f"{float(bt.get('profit_factor', 0)):.2f}",
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
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            html.P(
                                [
                                    html.Strong("Sharpe Ratio: "),
                                    f"{float(bt.get('sharpe_ratio', 0)):.2f}",
                                ]
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
        ]
    )

    # Fetch trades for equity curve
    trades_df = fetch_backtest_trades(str(bt.get("id", "")))
    equity_fig = create_backtest_equity_chart(trades_df, float(bt.get("starting_balance", 1000)))

    return details, equity_fig


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
        lambda r: f"{r['start_time'].strftime('%m/%d')} - {r['end_time'].strftime('%m/%d')}"
        if pd.notna(r["start_time"])
        else "—",
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

    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║           KrakenBot Dashboard                            ║
    ╠══════════════════════════════════════════════════════════╣
    ║  URL: http://localhost:{args.port}                           ║
    ║  Auto-refresh: Every 10 seconds                          ║
    ║                                                          ║
    ║  Make sure SSH tunnel is active:                         ║
    ║  ssh -L 5432:localhost:5432 bruno@<IP> -N                ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    app.run(debug=args.debug, port=args.port, host="0.0.0.0")
