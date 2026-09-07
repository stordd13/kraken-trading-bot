"""Q2 — USDC spot pairs on Bybit (EU host + global): lot size, min notional, tick.

Usage: poetry run python scripts/audit/bybit_q2_instruments.py
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
import sys

import aiohttp
import ccxt.async_support as ccxt_async

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from bybit_common import HOSTS, PAIRS, get, save_json, section, symbol, truncate  # noqa: E402

FIELDS = [
    "minOrderQty",
    "basePrecision",
    "quotePrecision",
    "minOrderAmt",
    "maxOrderQty",
    "maxMarketOrderQty",
    "maxLimitOrderQty",
    "maxOrderAmt",
    "postOnlyMaxLimitOrderSize",
]


async def main() -> None:
    results: dict = {}
    async with aiohttp.ClientSession() as session:
        for host in HOSTS:
            section(f"Q2 — instruments-info?category=spot on {HOSTS[host]}")
            for pair in PAIRS:
                sym = symbol(pair)
                data = await get(
                    session,
                    "/v5/market/instruments-info",
                    {"category": "spot", "symbol": sym},
                    host=host,
                )
                lst = data["result"]["list"]
                if not lst:
                    print(f"{sym}: NOT FOUND -> {truncate(data, 200)}")
                    results[f"{host}_{sym}"] = None
                    continue
                i = lst[0]
                lot, pf = i["lotSizeFilter"], i["priceFilter"]
                print(
                    f"{sym}: status={i['status']} marginTrading={i.get('marginTrading')} "
                    f"innovation={i.get('innovation')} stTag={i.get('stTag')}"
                )
                print(
                    f"   tickSize={pf['tickSize']}  "
                    + "  ".join(f"{f}={lot.get(f)}" for f in FIELDS)
                )
                print(f"   raw: {truncate(i, 500)}")
                results[f"{host}_{sym}"] = i

    section("Q2 — Comparison with Binance constants (connectors/binance/rest.py)")
    from krakenbot.connectors.binance.rest import MIN_NOTIONAL, MIN_ORDER_SIZE

    print(
        f"{'pair':10s} {'binance minQty':>15s} {'bybit minOrderQty':>18s} {'bybit qtyStep':>14s} "
        f"{'binance minNotional':>20s} {'bybit minOrderAmt':>18s} {'tickSize':>9s}"
    )
    for pair in PAIRS:
        i = results.get(f"eu_{symbol(pair)}") or results.get(f"global_{symbol(pair)}")
        if not i:
            print(f"{pair:10s} bybit: missing")
            continue
        lot = i["lotSizeFilter"]
        print(
            f"{pair:10s} {str(MIN_ORDER_SIZE[pair]):>15s} {lot['minOrderQty']:>18s} "
            f"{lot['basePrecision']:>14s} {str(MIN_NOTIONAL):>20s} {lot['minOrderAmt']:>18s} "
            f"{i['priceFilter']['tickSize']:>9s}"
        )

    section("Q2 — ccxt.bybit load_markets() view (precision / limits) on hostname=bybit.eu")
    ex = ccxt_async.bybit(
        {"hostname": "bybit.eu", "enableRateLimit": True, "options": {"defaultType": "spot"}}
    )
    try:
        markets = await ex.load_markets()
        for pair in PAIRS:
            m = markets.get(pair)
            if not m:
                print(f"{pair}: not in ccxt markets")
                continue
            print(
                f"{pair}: id={m['id']} type={m['type']} spot={m['spot']} active={m['active']} "
                f"precision={m['precision']} limits={m['limits']} "
                f"taker={m.get('taker')} maker={m.get('maker')}"
            )
            results[f"ccxt_{pair}"] = {
                "id": m["id"],
                "precision": m["precision"],
                "limits": m["limits"],
                "taker": m.get("taker"),
                "maker": m.get("maker"),
            }
        # Also: which quote currencies exist for BTC on spot? (USDC vs USDT vs EUR)
        btc_quotes = sorted(
            m["quote"] for m in markets.values() if m["spot"] and m["base"] == "BTC"
        )
        print(f"BTC spot quotes in ccxt markets: {btc_quotes}")
    finally:
        await ex.close()

    # Sanity: does Decimal(minOrderQty) * price >= minOrderAmt for realistic prices?
    section("Q2 — Effective minimum order per pair (USDC), tickers on EU host")
    async with aiohttp.ClientSession() as session:
        for pair in PAIRS:
            sym = symbol(pair)
            t = await get(
                session, "/v5/market/tickers", {"category": "spot", "symbol": sym}, host="eu"
            )
            last = Decimal(t["result"]["list"][0]["lastPrice"])
            i = results.get(f"eu_{sym}")
            if i:
                lot = i["lotSizeFilter"]
                min_by_qty = Decimal(lot["minOrderQty"]) * last
                print(
                    f"{pair}: last={last} minOrderQty*last={min_by_qty:.4f} USDC  "
                    f"minOrderAmt={lot['minOrderAmt']} USDC -> effective min = "
                    f"{max(min_by_qty, Decimal(lot['minOrderAmt'])):.4f} USDC; "
                    f"turnover24h={t['result']['list'][0].get('turnover24h')} USDC"
                )
                results[f"ticker_{sym}"] = t["result"]["list"][0]

    save_json("q2_instruments.json", results)


if __name__ == "__main__":
    asyncio.run(main())
