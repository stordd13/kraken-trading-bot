"""Streamlit dashboard for KrakenBot monitoring.

This dashboard provides real-time monitoring of the trading bot including:
- Current positions and P&L
- Price charts with trading signals
- Recent trade history
- Bot statistics and performance metrics

Usage:
    streamlit run scripts/dashboard.py
"""

import asyncio
from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select, desc

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.models.market_data import OHLCData
from krakenbot.models.trades import Trade, BotState, BacktestRun
from krakenbot.models.base import BotStatus


# Page configuration
st.set_page_config(
    page_title="KrakenBot Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_db_manager():
    """Get database manager instance."""
    return DatabaseManager()


async def fetch_bot_state(db_manager: DatabaseManager) -> BotState | None:
    """Fetch current bot state from database."""
    async with db_manager.session() as session:
        stmt = select(BotState).order_by(desc(BotState.last_updated)).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def fetch_recent_ohlc(
    db_manager: DatabaseManager,
    pair: str,
    hours: int = 24,
) -> list[OHLCData]:
    """Fetch recent OHLC data for chart."""
    since = datetime.now(UTC) - timedelta(hours=hours)

    async with db_manager.session() as session:
        stmt = (
            select(OHLCData)
            .where(OHLCData.pair == pair)
            .where(OHLCData.timestamp >= since)
            .order_by(OHLCData.timestamp.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def fetch_recent_trades(
    db_manager: DatabaseManager,
    limit: int = 20,
) -> list[Trade]:
    """Fetch recent trades from database."""
    async with db_manager.session() as session:
        stmt = (
            select(Trade)
            .order_by(desc(Trade.timestamp))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def fetch_backtest_runs(
    db_manager: DatabaseManager,
    limit: int = 50,
) -> list[BacktestRun]:
    """Fetch recent backtest runs from database."""
    async with db_manager.session() as session:
        stmt = (
            select(BacktestRun)
            .order_by(desc(BacktestRun.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def fetch_backtest_by_id(
    db_manager: DatabaseManager,
    backtest_id: str,
) -> BacktestRun | None:
    """Fetch specific backtest run by ID."""
    async with db_manager.session() as session:
        stmt = select(BacktestRun).where(BacktestRun.id == backtest_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


def create_price_chart(ohlc_data: list[OHLCData], trades: list[Trade]) -> go.Figure:
    """Create interactive price chart with candlesticks and trade markers."""
    fig = go.Figure()

    # Add candlestick chart
    if ohlc_data:
        fig.add_trace(go.Candlestick(
            x=[candle.timestamp for candle in ohlc_data],
            open=[float(candle.open) for candle in ohlc_data],
            high=[float(candle.high) for candle in ohlc_data],
            low=[float(candle.low) for candle in ohlc_data],
            close=[float(candle.close) for candle in ohlc_data],
            name="Price",
        ))

    # Add buy signals
    buy_trades = [t for t in trades if t.side.value == "buy"]
    if buy_trades:
        fig.add_trace(go.Scatter(
            x=[t.timestamp for t in buy_trades],
            y=[float(t.price) for t in buy_trades],
            mode="markers",
            name="Buy",
            marker=dict(
                symbol="triangle-up",
                size=15,
                color="green",
                line=dict(color="darkgreen", width=2),
            ),
        ))

    # Add sell signals
    sell_trades = [t for t in trades if t.side.value == "sell"]
    if sell_trades:
        fig.add_trace(go.Scatter(
            x=[t.timestamp for t in sell_trades],
            y=[float(t.price) for t in sell_trades],
            mode="markers",
            name="Sell",
            marker=dict(
                symbol="triangle-down",
                size=15,
                color="red",
                line=dict(color="darkred", width=2),
            ),
        ))

    # Update layout
    fig.update_layout(
        title="Price Chart with Trading Signals",
        xaxis_title="Time",
        yaxis_title="Price (USDC)",
        template="plotly_dark",
        height=500,
        xaxis_rangeslider_visible=False,
    )

    return fig


def render_header():
    """Render dashboard header."""
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.title("🤖 KrakenBot Dashboard")

    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    with col3:
        settings = get_settings()
        mode = settings.trading.mode.value
        if mode == "paper":
            st.success("📝 Paper Trading")
        else:
            st.error("⚠️ LIVE Trading")


def render_metrics(bot_state: BotState | None):
    """Render key metrics cards."""
    col1, col2, col3, col4 = st.columns(4)

    if bot_state:
        with col1:
            st.metric(
                "Total P&L",
                f"{float(bot_state.total_pnl):+.2f} USDC",
                delta=f"{float(bot_state.daily_pnl):+.2f} today",
            )

        with col2:
            st.metric(
                "Position",
                f"{float(bot_state.current_position_crypto):.8f} BTC",
            )

        with col3:
            entry_label = "Entry Price" if bot_state.entry_price else "No Position"
            entry_value = f"{float(bot_state.entry_price):.2f}" if bot_state.entry_price else "—"
            st.metric(entry_label, entry_value)

        with col4:
            st.metric("Total Trades", bot_state.trade_count)
    else:
        for col in [col1, col2, col3, col4]:
            with col:
                st.metric("No Data", "—")


def render_bot_status(bot_state: BotState | None):
    """Render bot status information."""
    st.subheader("Bot Status")

    if bot_state:
        col1, col2 = st.columns(2)

        with col1:
            status_color = {
                BotStatus.RUNNING: "🟢",
                BotStatus.IDLE: "🟡",
                BotStatus.STOPPED: "🔴",
                BotStatus.ERROR: "🔴",
            }.get(bot_state.status, "⚪")

            st.write(f"**Status:** {status_color} {bot_state.status.value.upper()}")
            st.write(f"**Strategy:** {bot_state.strategy}")
            st.write(f"**Bot ID:** `{bot_state.bot_id}`")

        with col2:
            st.write(f"**Last Updated:** {bot_state.last_updated.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            if bot_state.last_signal_at:
                st.write(f"**Last Signal:** {bot_state.last_signal_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                st.write("**Last Signal:** Never")
    else:
        st.warning("No bot state found in database. Is the bot running?")


def render_trades_table(trades: list[Trade]):
    """Render recent trades table."""
    st.subheader("Recent Trades")

    if trades:
        df = pd.DataFrame([
            {
                "Time": t.timestamp.strftime("%Y-%m-%d %H:%M"),
                "Side": t.side.value.upper(),
                "Price": f"{float(t.price):.2f}",
                "Amount (USDC)": f"{float(t.amount_eur):.2f}",
                "Amount (BTC)": f"{float(t.amount_crypto):.8f}",
                "Fee": f"{float(t.fee):.2f}",
                "P&L": f"{float(t.pnl):+.2f}" if t.pnl else "—",
                "Status": t.status.value,
            }
            for t in trades
        ])

        # Color code by side
        def highlight_side(row):
            if row["Side"] == "BUY":
                return ["background-color: rgba(0, 255, 0, 0.1)"] * len(row)
            elif row["Side"] == "SELL":
                return ["background-color: rgba(255, 0, 0, 0.1)"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df.style.apply(highlight_side, axis=1),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No trades yet. Waiting for trading signals...")


def render_chart(db_manager: DatabaseManager, pair: str, hours: int):
    """Render price chart."""
    st.subheader(f"{pair} Price Chart (Last {hours}h)")

    # Fetch data
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    ohlc_data = loop.run_until_complete(fetch_recent_ohlc(db_manager, pair, hours))
    trades = loop.run_until_complete(fetch_recent_trades(db_manager, limit=50))

    if ohlc_data:
        fig = create_price_chart(ohlc_data, trades)
        st.plotly_chart(fig, use_container_width=True)

        # Show data summary
        latest = ohlc_data[-1]
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Latest Price", f"{float(latest.close):.2f} USDC")
        with col2:
            change_pct = float(latest.price_change_pct) if hasattr(latest, 'price_change_pct') else 0
            st.metric("24h Change", f"{change_pct:+.2f}%")
        with col3:
            st.metric("Volume", f"{float(latest.volume):.4f} BTC")
    else:
        st.warning(f"No OHLC data found for {pair}. Is the bot running and receiving data?")


def main():
    """Main dashboard application."""
    # Initialize database
    db_manager = get_db_manager()

    # Async event loop for database operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Render header
    render_header()

    st.markdown("---")

    # Settings
    settings = get_settings()
    pair = settings.trading.pair

    # Sidebar controls
    with st.sidebar:
        st.header("Settings")

        # Mode selection
        mode = st.radio(
            "View Mode",
            options=["Live Bot", "Backtest Results"],
            index=0,
        )

        # If backtest mode, show selector
        selected_backtest = None
        if mode == "Backtest Results":
            backtests = loop.run_until_complete(fetch_backtest_runs(db_manager, limit=50))
            if backtests:
                backtest_options = {
                    f"{bt.run_name} ({bt.created_at.strftime('%Y-%m-%d %H:%M')})": str(bt.id)
                    for bt in backtests
                }
                selected_name = st.selectbox(
                    "Select Backtest",
                    options=list(backtest_options.keys()),
                )
                selected_id = backtest_options[selected_name]
                selected_backtest = loop.run_until_complete(
                    fetch_backtest_by_id(db_manager, selected_id)
                )
            else:
                st.warning("No backtests found. Run a backtest with --save flag.")

        hours = st.slider("Chart Hours", min_value=1, max_value=168, value=24, step=1)
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)

    # Conditional rendering based on mode
    if mode == "Backtest Results" and selected_backtest:
        # Backtest metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Net P&L",
                f"{float(selected_backtest.net_pnl):+.2f} USDC",
                delta=f"{float(selected_backtest.total_return_pct):+.2f}% return",
            )
        with col2:
            st.metric(
                "Win Rate",
                f"{float(selected_backtest.win_rate) * 100:.1f}%",
                delta=f"{selected_backtest.total_trades} trades",
            )
        with col3:
            st.metric(
                "Sharpe Ratio",
                f"{float(selected_backtest.sharpe_ratio):.2f}",
            )
        with col4:
            st.metric(
                "Max Drawdown",
                f"{float(selected_backtest.max_drawdown):.2f} USDC",
                delta=f"{float(selected_backtest.max_drawdown_pct):.2f}%",
            )

        st.markdown("---")

        # Backtest details
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Backtest Details")
            st.write(f"**Strategy:** {selected_backtest.strategy}")
            st.write(f"**Pair:** {selected_backtest.pair}")
            st.write(f"**Period:** {selected_backtest.start_time.strftime('%Y-%m-%d')} to {selected_backtest.end_time.strftime('%Y-%m-%d')}")
            st.write(f"**Duration:** {(selected_backtest.end_time - selected_backtest.start_time).days} days")

        with col2:
            st.subheader("Performance Metrics")
            st.write(f"**Starting Balance:** {float(selected_backtest.starting_balance):.2f} USDC")
            st.write(f"**Ending Balance:** {float(selected_backtest.ending_balance):.2f} USDC")
            st.write(f"**Total Fees:** {float(selected_backtest.total_fees):.2f} USDC")
            st.write(f"**Profit Factor:** {float(selected_backtest.profit_factor):.2f}")

        st.markdown("---")

        # Render chart for backtest period
        ohlc_data = loop.run_until_complete(fetch_recent_ohlc(
            db_manager,
            selected_backtest.pair,
            hours=(selected_backtest.end_time - selected_backtest.start_time).days * 24,
        ))
        if ohlc_data:
            fig = create_price_chart(ohlc_data, [])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No OHLC data found for this backtest period.")

    else:
        # Live Bot Mode
        # Fetch bot state
        bot_state = loop.run_until_complete(fetch_bot_state(db_manager))

        # Render metrics
        render_metrics(bot_state)

        st.markdown("---")

        # Two-column layout
        col1, col2 = st.columns([2, 1])

        with col1:
            # Render chart
            render_chart(db_manager, pair, hours)

        with col2:
            # Bot status
            render_bot_status(bot_state)

    st.markdown("---")

    # Trades table
    trades = loop.run_until_complete(fetch_recent_trades(db_manager, limit=20))
    render_trades_table(trades)

    # Auto-refresh
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()

    # Footer
    st.markdown("---")
    st.caption("KrakenBot Dashboard • Real-time monitoring for your trading bot")


if __name__ == "__main__":
    # Connect to database
    db_manager = get_db_manager()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    settings = get_settings()
    loop.run_until_complete(db_manager.init_db(settings))

    try:
        main()
    finally:
        loop.run_until_complete(db_manager.close_db())
