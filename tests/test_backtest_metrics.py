"""Synthetic trajectories with hand-computed expectations — ``krakenbot.backtest_metrics`` (C1).

The eight cases of the chantier brief (§ 4) plus the edge rules fixed in the plan (authoritative
anchor, last-wins, partial edges, flows, unknown cost basis, empty equity).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import math

import pytest

from krakenbot.backtest_metrics import (
    METRICS_VERSION,
    EquityPoint,
    ExternalFlow,
    MetricsVersionError,
    TradeLeg,
    compute_metrics,
    daily_grid,
    entry_metrics_version,
    fmt,
    max_drawdown_pct,
    mean_available,
    net_trade_pnls,
    profit_factor_from_sums,
    require_metrics_version,
    resample_daily,
    sharpe_ratio,
    sortino_ratio,
)

T0 = datetime(2025, 3, 1, tzinfo=UTC)
DAY = timedelta(days=1)
H = timedelta(hours=1)
CAPITAL = Decimal("1000")
SQRT365 = math.sqrt(365)


def _pt(ts: datetime, equity: str | int | float) -> EquityPoint:
    return EquityPoint(timestamp=ts, equity=Decimal(str(equity)))


def _daily_points(values: list[str | int | float], start: datetime = T0) -> list[EquityPoint]:
    """One point per day, the first one stamped ``start + 1 day`` (the anchor is ``start``)."""
    return [_pt(start + DAY * (i + 1), v) for i, v in enumerate(values)]


def _run(values: list[str | int | float], capital: Decimal = CAPITAL):
    pts = _daily_points(values)
    return compute_metrics(pts, [], start=T0, end=pts[-1].timestamp, starting_balance=capital)


def _sell(pnl: str | None, buy_fee: str | None = None, ts: datetime = T0) -> TradeLeg:
    return TradeLeg(
        side="sell",
        timestamp=ts,
        amount_crypto=Decimal("1"),
        fee=Decimal("0"),
        pnl=None if pnl is None else Decimal(pnl),
        buy_fee_alloc=None if buy_fee is None else Decimal(buy_fee),
    )


def _buy(fee: str, ts: datetime = T0) -> TradeLeg:
    return TradeLeg(side="buy", timestamp=ts, amount_crypto=Decimal("1"), fee=Decimal(fee))


# ---------------------------------------------------------------------------
# Brief § 4 — the eight synthetic cases
# ---------------------------------------------------------------------------


def test_1_max_drawdown_relative_to_running_peak() -> None:
    """1000 -> 700 -> 2000 -> 1900: 30 % (peak 1000, trough 700), not 15 % (300 / final peak)."""
    m = _run([700, 2000, 1900])
    assert m.max_drawdown_pct_daily == 30.0
    assert m.max_drawdown_pct_engine == 30.0
    old_formula = 300 / 2000 * 100  # largest money loss / final peak (D2)
    assert old_formula == 15.0 and m.max_drawdown_pct_daily != old_formula


def test_2_intraday_drop_and_recovery_is_engine_only() -> None:
    """100 -> 75 -> 100 inside one UTC day, flat daily closes: daily ~0, engine 25."""
    pts = [_pt(T0 + 6 * H, 75), _pt(T0 + 12 * H, 100), _pt(T0 + 18 * H, 100), _pt(T0 + DAY, 100)]
    m = compute_metrics(pts, [], start=T0, end=T0 + DAY, starting_balance=Decimal("100"))
    assert m.max_drawdown_pct_daily == 0.0
    assert m.max_drawdown_pct_engine == 25.0
    assert m.daily.nav == (Decimal("100"), Decimal("100"))


def test_3_constant_returns_give_no_sharpe() -> None:
    """+1 % every day: std == 0 -> Sharpe None (never a fake 0), Sortino None (no downside)."""
    m = _run(["1010", "1020.1", "1030.301"])
    assert m.daily.defined_returns == pytest.approx([0.01, 0.01, 0.01])
    assert m.sharpe_ratio is None
    assert m.sortino_ratio is None
    assert m.n_daily_returns == 3


def test_4_short_alternating_series_known_sharpe_and_sortino() -> None:
    """Returns +2 %, -1 %, +2 %, -1 % (exact in Decimal): mean 0.005, sample var 0.0003."""
    m = _run(["1020", "1009.8", "1029.996", "1019.69604"])
    assert m.daily.defined_returns == pytest.approx([0.02, -0.01, 0.02, -0.01])
    mean = 0.005
    sample_std = math.sqrt((4 * 0.015**2) / 3)  # ddof = 1 -> sqrt(0.0003)
    downside = math.sqrt((0.01**2 + 0.01**2) / 4)  # MAR 0, N total = 4
    assert m.sharpe_ratio == pytest.approx(mean / sample_std * SQRT365)
    assert m.sharpe_ratio == pytest.approx(5.5151, abs=1e-4)
    assert m.sortino_ratio == pytest.approx(mean / downside * SQRT365)
    assert m.sortino_ratio == pytest.approx(13.5093, abs=1e-4)
    # hand check of the ratios themselves (pure functions)
    assert sharpe_ratio([0.02, -0.01, 0.02, -0.01]) == pytest.approx(
        0.005 / math.sqrt(0.0003) * SQRT365
    )
    assert sortino_ratio([0.02, -0.01, 0.02, -0.01]) == pytest.approx(
        0.005 / math.sqrt(0.00005) * SQRT365
    )


def test_5_five_minute_series_over_three_days_resamples_to_three_daily_closes() -> None:
    """864 five-minute points from D 00:05 to D+3 00:00: anchor + 3 closes, at the exact stamps."""
    step = timedelta(minutes=5)
    pts = [_pt(T0 + step * i, 1000 + i) for i in range(1, 865)]
    s = resample_daily(pts, start=T0, end=T0 + 3 * DAY, starting_balance=CAPITAL)
    assert s.timestamps == (T0, T0 + DAY, T0 + 2 * DAY, T0 + 3 * DAY)
    # the close stamped D+1 00:00 (i = 288) closes the day, not the 00:05 point (i = 289)
    assert s.nav == (Decimal("1000"), Decimal("1288"), Decimal("1576"), Decimal("1864"))
    assert len(s.defined_returns) == 3


def test_6_profit_factor_net_of_both_legs() -> None:
    # +10, +10, -5 without buy fees -> 4.0
    pf = net_trade_pnls([_sell("10", "0"), _sell("10", "0"), _sell("-5", "0")])
    assert pf.profit_factor == 4.0 and pf.gross_profit_net == 20 and pf.gross_loss_net == 5
    # the same trades with a 1 USDC buy fee each: 9, 9, -6 -> 3.0 (the old gross-of-buy-fee
    # calculation would still say 4.0)
    pf_net = net_trade_pnls([_sell("10", "1"), _sell("10", "1"), _sell("-5", "1")])
    assert pf_net.profit_factor == 3.0 and pf_net.profit_factor != pf.profit_factor
    assert pf_net.net_trade_pnls == (Decimal("9"), Decimal("9"), Decimal("-6"))
    # anti double-counting on a fully closed run: sum(pnl_net_trade) == total_pnl - buy fees
    legs = [
        _buy("0.5"),
        _sell("3", "0.5"),
        _buy("0.7"),
        _sell("-2", "0.7"),
        _buy("0.9"),
        _sell("1", "0.9"),
    ]
    total_pnl = sum((leg.pnl for leg in legs if leg.pnl is not None), Decimal("0"))
    buy_fees = sum((leg.fee for leg in legs if leg.side == "buy"), Decimal("0"))
    net_pnl_engine = total_pnl - buy_fees  # the engines' net_pnl formula (B4.3)
    assert (
        sum(net_trade_pnls(legs).net_trade_pnls, Decimal("0")) == net_pnl_engine == Decimal("-0.1")
    )
    # 0 loss -> None, disambiguated by the sums (gains > 0, losses = 0 -> infinite)
    zero_loss = net_trade_pnls([_sell("10", "0"), _sell("5", "0")])
    assert zero_loss.profit_factor is None
    assert (zero_loss.gross_profit_net, zero_loss.gross_loss_net) == (15, 0)
    assert profit_factor_from_sums(zero_loss.gross_profit_net, zero_loss.gross_loss_net) == math.inf
    # no closed trade -> 0/0 undefined
    empty = net_trade_pnls([_buy("1")])
    assert empty.profit_factor is None and (empty.gross_profit_net, empty.gross_loss_net) == (0, 0)
    assert profit_factor_from_sums(0, 0) is None
    # unknown cost basis (pnl None): excluded, never a 0 or positive gain invented
    partial = net_trade_pnls([_sell("10", "1"), _sell(None), _sell("-4", "1")])
    assert partial.pf_excluded_trades == 1
    assert partial.net_trade_pnls == (Decimal("9"), Decimal("-5"))
    assert partial.profit_factor == 1.8


def test_7_aggregation_by_sums_and_none_aware_means() -> None:
    windows = [
        (Decimal("10"), Decimal("5")),
        (Decimal("8"), Decimal("0")),
        (Decimal("6"), Decimal("3")),
    ]
    per_window = [profit_factor_from_sums(gp, gl) for gp, gl in windows]
    assert per_window == [2.0, math.inf, 2.0]  # the infinite window never becomes 0
    total = profit_factor_from_sums(sum(gp for gp, _ in windows), sum(gl for _, gl in windows))
    assert total == 24 / 8 == 3.0
    assert mean_available([0.5, None, 1.0]) == (0.75, 2)
    assert mean_available([None, None]) == (None, 0)
    assert mean_available([]) == (None, 0)


def test_8_flat_prices_with_weekly_deposits_and_no_fees_are_not_returns() -> None:
    """Price 100 flat, 15 USDC deposited every 7 days, no fee: every adjusted return is 0."""
    pts, flows = [], []
    coins = Decimal("0")
    for day in range(1, 29):
        ts = T0 + DAY * day
        if day % 7 == 0:
            coins += Decimal("15") / Decimal("100")
            flows.append(ExternalFlow(timestamp=ts, amount=Decimal("15")))
        pts.append(_pt(ts, coins * 100))
    m = compute_metrics(
        pts, [], start=T0, end=T0 + 28 * DAY, starting_balance=Decimal("0"), flows=flows
    )
    assert m.daily.nav[-1] == Decimal("60")  # 4 deposits, no return
    assert all(r == 0 for r in m.daily.defined_returns)
    assert m.n_daily_returns == 21  # days 8..28 (the anchor and the days at E = 0 are undefined)
    assert m.sharpe_ratio is None and m.sortino_ratio is None
    assert m.max_drawdown_pct_daily == 0.0
    assert set(m.daily.index) == {Decimal("1")}


# ---------------------------------------------------------------------------
# Edge rules fixed in the plan (C2 / C3 / C7)
# ---------------------------------------------------------------------------


def test_anchor_is_authoritative_over_a_data_point_at_start() -> None:
    s = resample_daily(
        [_pt(T0, 999), _pt(T0 + DAY, 999)], start=T0, end=T0 + DAY, starting_balance=CAPITAL
    )
    assert s.nav == (Decimal("1000"), Decimal("999"))


def test_last_data_point_wins_at_an_equal_timestamp() -> None:
    """The grid's post-liquidation point shares the last candle's stamp and must count."""
    pts = [_pt(T0 + DAY, 1000), _pt(T0 + DAY, 990)]
    s = resample_daily(pts, start=T0, end=T0 + DAY, starting_balance=CAPITAL)
    assert s.nav[-1] == Decimal("990")


def test_entry_loss_then_constant_prices() -> None:
    """Anchor 1000, first point 999 (entry cost) then flat: one negative return, then zeros."""
    m = _run([999, 999, 999])
    assert m.daily.index == (Decimal("1"), Decimal("0.999"), Decimal("0.999"), Decimal("0.999"))
    assert m.daily.defined_returns == pytest.approx([-0.001, 0.0, 0.0])
    assert m.sharpe_ratio is not None and m.sharpe_ratio < 0
    assert m.sortino_ratio is not None and m.sortino_ratio < 0
    assert m.max_drawdown_pct_daily == pytest.approx(0.1)
    assert m.cagr_pct is not None and m.cagr_pct < 0
    assert m.calmar_ratio is not None and m.calmar_ratio < 0


def test_partial_edges_are_kept_as_grid_points() -> None:
    start, end = T0 + 12 * H, T0 + 2 * DAY + 6 * H
    assert daily_grid(start, end) == [start, T0 + DAY, T0 + 2 * DAY, end]
    assert daily_grid(T0, T0) == [T0]
    with pytest.raises(ValueError):
        daily_grid(T0 + DAY, T0)


def test_forward_fill_on_days_without_observation() -> None:
    pts = [_pt(T0 + DAY, 1010), _pt(T0 + 3 * DAY, 1030)]
    s = resample_daily(pts, start=T0, end=T0 + 3 * DAY, starting_balance=CAPITAL)
    assert s.nav == (Decimal("1000"), Decimal("1010"), Decimal("1010"), Decimal("1030"))


def test_flows_are_bucketed_and_summed_and_validated() -> None:
    flows = [
        ExternalFlow(T0, Decimal("1")),  # at start -> anchor bucket, earns no return
        ExternalFlow(T0 + DAY + 10 * H, Decimal("5")),
        ExternalFlow(T0 + DAY + 20 * H, Decimal("5")),
    ]
    s = resample_daily(
        [_pt(T0 + 2 * DAY, 1010)], start=T0, end=T0 + 2 * DAY, starting_balance=CAPITAL, flows=flows
    )
    assert s.flows == (Decimal("1"), Decimal("0"), Decimal("10"))
    assert s.returns[2] == Decimal("0")  # (1010 - 10 - 1000) / 1000
    with pytest.raises(ValueError):
        resample_daily(
            [],
            start=T0,
            end=T0 + DAY,
            starting_balance=CAPITAL,
            flows=[ExternalFlow(T0 - H, Decimal("1"))],
        )
    with pytest.raises(ValueError):
        resample_daily(
            [],
            start=T0,
            end=T0 + DAY,
            starting_balance=CAPITAL,
            flows=[ExternalFlow(T0 + 2 * DAY, Decimal("1"))],
        )


def test_first_deposit_on_a_zero_balance_is_undefined_not_zero() -> None:
    flows = [ExternalFlow(T0 + DAY, Decimal("15"))]
    pts = [_pt(T0 + DAY, 15), _pt(T0 + 2 * DAY, 15)]
    s = resample_daily(pts, start=T0, end=T0 + 2 * DAY, starting_balance=Decimal("0"), flows=flows)
    assert s.returns == (None, None, Decimal("0"))
    assert s.index == (Decimal("1"), Decimal("1"), Decimal("1"))


def test_a_deposit_cannot_mask_a_drawdown() -> None:
    """1 coin at 100; day 1 the price falls to 90 and 15 USDC is deposited at the close: the NAV
    rises to 105 but the adjusted return is -10 % and the index carries the drawdown."""
    flows = [ExternalFlow(T0 + DAY, Decimal("15"))]
    m = compute_metrics(
        [_pt(T0 + DAY, 105)],
        [],
        start=T0,
        end=T0 + DAY,
        starting_balance=Decimal("100"),
        flows=flows,
    )
    assert m.daily.returns[1] == Decimal("-0.1")
    assert m.daily.index[-1] == Decimal("0.9")
    assert m.max_drawdown_pct_daily == 10.0
    assert max_drawdown_pct(m.daily.nav) == 0.0  # what a NAV-based drawdown would have said


def test_empty_equity_gives_undefined_ratios_and_zero_drawdown() -> None:
    m = compute_metrics([], [], start=T0, end=T0 + 3 * DAY, starting_balance=CAPITAL)
    assert m.daily.nav == (CAPITAL,) * 4
    assert m.sharpe_ratio is None and m.sortino_ratio is None and m.calmar_ratio is None
    assert m.max_drawdown_pct_daily == 0.0 and m.max_drawdown_pct_engine == 0.0
    assert m.profit_factor is None and m.pf_excluded_trades == 0
    assert m.daily.to_dict() == {
        "start": T0.isoformat(),
        "end": (T0 + 3 * DAY).isoformat(),
        "values": [1000.0, 1000.0, 1000.0, 1000.0],
    }


def test_engine_drawdown_starts_at_the_anchor_like_the_old_peak_init() -> None:
    """A run whose first point is below the starting balance: the engine drawdown counts it."""
    pts = [_pt(T0 + H, 995), _pt(T0 + DAY, 1002)]
    m = compute_metrics(pts, [], start=T0, end=T0 + DAY, starting_balance=CAPITAL)
    assert m.max_drawdown_pct_engine == 0.5
    assert m.max_drawdown_pct_daily == 0.0


def test_calmar_uses_geometric_cagr_of_the_index() -> None:
    """+10 % over 365 days with a 5 % drawdown: CAGR 10 %, Calmar 2.0."""
    pts = [_pt(T0 + 100 * DAY, 950), _pt(T0 + 365 * DAY, 1100)]
    m = compute_metrics(pts, [], start=T0, end=T0 + 365 * DAY, starting_balance=CAPITAL)
    assert m.cagr_pct == pytest.approx(10.0)
    assert m.max_drawdown_pct_daily == 5.0
    assert m.calmar_ratio == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Consumer helpers
# ---------------------------------------------------------------------------


def test_require_metrics_version() -> None:
    ok = {"a": {"metrics_version": METRICS_VERSION}, "b": {"error": "boom"}}
    require_metrics_version(ok)
    nested = {"a": {"test": {"metrics_version": METRICS_VERSION}}}
    require_metrics_version(nested)
    assert entry_metrics_version({"train": {}, "test": {"metrics_version": 2}}) == 2
    assert entry_metrics_version({"fees": "bybit"}) is None
    with pytest.raises(MetricsVersionError, match="pre-C1"):
        require_metrics_version({"a": {"fees": "bybit", "test": {}}}, path="x.json")
    with pytest.raises(MetricsVersionError, match="metrics_version=1"):
        require_metrics_version({"a": {"metrics_version": 1}})


def test_fmt() -> None:
    assert fmt(None) == "n/a"
    assert fmt(math.inf) == "∞"
    assert fmt(1.2345) == "1.23"
    assert fmt(12.5, 1, suffix="%") == "12.5%"
    assert fmt(math.nan) == "n/a"
