"""Q3 — Liquidity & spread on the 3 USDC pairs (Bybit spot).

One measurement per run, or ``--repeat 3 --spacing 7200`` to take 3
measurements spaced by 2 h (run in the background). Each measurement is
appended to ``$BYBIT_AUDIT_OUT/q3_orderbook.jsonl``.

Usage:
    poetry run python scripts/audit/bybit_q3_orderbook.py
    poetry run python scripts/audit/bybit_q3_orderbook.py --repeat 3 --spacing 7200
    poetry run python scripts/audit/bybit_q3_orderbook.py --summary
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import statistics
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bybit_common import OUT_DIR, PAIRS, get_retry, section, symbol, truncate  # noqa: E402

BAND = Decimal("0.001")  # ±0.1 % around mid
BINANCE_SPREAD_ASSUMPTION = Decimal("0.0002")
BINANCE_SLIPPAGE_ASSUMPTION = Decimal("0.0001")


def depth_within_band(
    levels: list[list[str]], mid: Decimal, side: str
) -> tuple[Decimal, int, bool]:
    """Return (cumulative USDC notional within ±band of mid, levels used, band fully covered)."""
    lo, hi = mid * (1 - BAND), mid * (1 + BAND)
    total = Decimal("0")
    used = 0
    for price_s, qty_s in levels:
        price, qty = Decimal(price_s), Decimal(qty_s)
        inside = price >= lo if side == "bid" else price <= hi
        if not inside:
            return total, used, True  # book extends beyond the band → band fully covered
        total += price * qty
        used += 1
    return total, used, False  # ran out of levels inside the band → truncated


async def measure(session: aiohttp.ClientSession, host: str, limit: int) -> list[dict]:
    rows = []
    for pair in PAIRS:
        sym = symbol(pair)
        data = await get_retry(
            session,
            "/v5/market/orderbook",
            {"category": "spot", "symbol": sym, "limit": limit},
            host=host,
        )
        r = data["result"]
        bids, asks = r["b"], r["a"]
        best_bid, best_ask = Decimal(bids[0][0]), Decimal(asks[0][0])
        mid = (best_bid + best_ask) / 2
        spread_pct = (best_ask - best_bid) / mid * 100
        bid_depth, bid_lv, bid_full = depth_within_band(bids, mid, "bid")
        ask_depth, ask_lv, ask_full = depth_within_band(asks, mid, "ask")
        # Market-impact estimate: average fill price for a 1 000 USDC market buy
        remaining, cost, qty_tot = Decimal("1000"), Decimal("0"), Decimal("0")
        for price_s, qty_s in asks:
            price, qty = Decimal(price_s), Decimal(qty_s)
            take_notional = min(remaining, price * qty)
            cost += take_notional
            qty_tot += take_notional / price
            remaining -= take_notional
            if remaining <= 0:
                break
        slip_1k_bps = ((cost / qty_tot) / best_ask - 1) * 10000 if qty_tot else None
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "host": host,
            "limit": limit,
            "pair": pair,
            "best_bid": str(best_bid),
            "best_ask": str(best_ask),
            "mid": str(mid),
            "spread_pct": f"{spread_pct:.5f}",
            "spread_bps": f"{spread_pct * 100:.3f}",
            "bid_depth_usdc_0.1pct": f"{bid_depth:.2f}",
            "ask_depth_usdc_0.1pct": f"{ask_depth:.2f}",
            "bid_levels_used": bid_lv,
            "ask_levels_used": ask_lv,
            "bid_band_fully_covered": bid_full,
            "ask_band_fully_covered": ask_full,
            "slippage_1k_usdc_buy_bps": f"{slip_1k_bps:.3f}" if slip_1k_bps is not None else None,
            "book_ts": r.get("ts"),
            "update_id": r.get("u"),
            "raw_top3": {"b": bids[:3], "a": asks[:3]},
        }
        rows.append(row)
        print(
            f"{pair:9s} bid={best_bid} ask={best_ask} spread={spread_pct:.4f}% "
            f"depth±0.1%: bid={bid_depth:,.0f} ask={ask_depth:,.0f} USDC "
            f"(levels {bid_lv}/{ask_lv}, covered {bid_full}/{ask_full}) "
            f"slip(1k buy)={row['slippage_1k_usdc_buy_bps']} bps"
        )
        print(f"          raw: {truncate(r, 260)}")
    return rows


def summary() -> None:
    path = OUT_DIR / "q3_orderbook.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    section(f"Q3 summary — {len(rows)} rows from {path}")
    by_key: dict[tuple[str, str, int], list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["host"], r["pair"], r["limit"]), []).append(r)
    print(
        f"{'host':7s} {'pair':9s} {'limit':>5s} {'n':>2s} {'spread% med':>12s} {'spread% max':>12s} "
        f"{'bid depth med':>14s} {'ask depth med':>14s} {'slip1k bps med':>15s}"
    )
    for (host, pair, limit), rs in sorted(by_key.items()):
        sp = [float(r["spread_pct"]) for r in rs]
        bd = [float(r["bid_depth_usdc_0.1pct"]) for r in rs]
        ad = [float(r["ask_depth_usdc_0.1pct"]) for r in rs]
        sl = [float(r["slippage_1k_usdc_buy_bps"]) for r in rs if r["slippage_1k_usdc_buy_bps"]]
        print(
            f"{host:7s} {pair:9s} {limit:>5d} {len(rs):>2d} {statistics.median(sp):>12.4f} {max(sp):>12.4f} "
            f"{statistics.median(bd):>14,.0f} {statistics.median(ad):>14,.0f} "
            f"{statistics.median(sl) if sl else float('nan'):>15.3f}"
        )
    print("\nPer-measurement detail (limit=50):")
    for r in rows:
        if r["limit"] == 50:
            print(
                f"  {r['ts'][:19]} {r['host']:6s} {r['pair']:9s} bid={r['best_bid']:>10s} ask={r['best_ask']:>10s} "
                f"spread={r['spread_pct']}% depth bid/ask={r['bid_depth_usdc_0.1pct']}/"
                f"{r['ask_depth_usdc_0.1pct']} USDC covered={r['bid_band_fully_covered']}/"
                f"{r['ask_band_fully_covered']}"
            )
    print(
        f"\nBacktest assumptions today: spread={BINANCE_SPREAD_ASSUMPTION} "
        f"slippage={BINANCE_SLIPPAGE_ASSUMPTION} (ExchangeFees defaults)"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--spacing", type=int, default=7200, help="seconds between measurements")
    ap.add_argument("--host", default="eu", choices=["eu", "global"])
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.summary:
        summary()
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "q3_orderbook.jsonl"
    async with aiohttp.ClientSession() as session:
        for i in range(args.repeat):
            section(
                f"Q3 measurement {i + 1}/{args.repeat} at {datetime.now(UTC).isoformat()} host={args.host}"
            )
            for limit in (50, 200):
                print(f"-- limit={limit}")
                rows = await measure(session, args.host, limit)
                with out.open("a") as fh:
                    for r in rows:
                        fh.write(json.dumps(r) + "\n")
            print(f"[appended] {out}")
            if i < args.repeat - 1:
                print(f"sleeping {args.spacing}s ...", flush=True)
                await asyncio.sleep(args.spacing)


if __name__ == "__main__":
    asyncio.run(main())
