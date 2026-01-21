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
from datetime import UTC, datetime
import os
import sys

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


def fetch_ohlc_data(pair: str = "XBT/USDC", hours: int = 24, interval: int = 15) -> pd.DataFrame:
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
    """Execute custom SQL query."""
    try:
        # Basic safety check - only allow SELECT
        if not query.strip().upper().startswith("SELECT"):
            return None, "Only SELECT queries are allowed"

        df = pd.read_sql(query, engine)
        return df, None
    except Exception as e:
        return None, str(e)


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
                # Tab 3: SQL Explorer
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
                # Tab 4: Statistics
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
                # Tab 5: Backtest Results
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
                                                                        "Backtest Runs",
                                                                        className="mb-0",
                                                                    ),
                                                                    width=8,
                                                                ),
                                                                dbc.Col(
                                                                    [
                                                                        dbc.Button(
                                                                            "Refresh",
                                                                            id="refresh-backtest-btn",
                                                                            color="primary",
                                                                            size="sm",
                                                                        ),
                                                                    ],
                                                                    width=4,
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
    """Update statistics tab."""
    stats = fetch_stats()

    return dbc.Row(
        [
            dbc.Col(
                [
                    dbc.Card(
                        [
                            dbc.CardHeader("OHLC Data"),
                            dbc.CardBody(
                                [
                                    html.P(f"Total candles: {stats.get('total_candles', 0):,}"),
                                    html.P(f"First candle: {stats.get('first_candle', '—')}"),
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
                                    html.P(f"Total P&L: {stats.get('total_pnl', 0):+.2f} USDC"),
                                ]
                            ),
                        ]
                    ),
                ],
                width=6,
            ),
        ]
    )


# Store selected backtest ID
selected_backtest_id = dcc.Store(id="selected-backtest-id", data=None)


@callback(
    Output("backtest-runs-table", "children"),
    [Input("refresh-backtest-btn", "n_clicks"), Input("tabs", "active_tab")],
)
def update_backtest_runs(n_clicks, active_tab):
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
        row_selectable="single",
        selected_rows=[0] if not df.empty else [],
        page_size=10,
    )


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
