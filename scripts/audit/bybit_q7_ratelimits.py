"""Q7 — Bybit REST rate limits: headers, burst behaviour, ccxt costs.

Usage: poetry run python scripts/audit/bybit_q7_ratelimits.py [--burst 120]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import time

import aiohttp
import ccxt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bybit_common import HOSTS, get, load_env_keys, save_json, section  # noqa: E402

PUBLIC = [
    ("/v5/market/time", {}),
    (
        "/v5/market/kline",
        {"category": "spot", "symbol": "BTCUSDC", "interval": "60", "limit": 1000},
    ),
    ("/v5/market/orderbook", {"category": "spot", "symbol": "BTCUSDC", "limit": 50}),
    ("/v5/market/tickers", {"category": "spot", "symbol": "BTCUSDC"}),
    ("/v5/market/instruments-info", {"category": "spot", "symbol": "BTCUSDC"}),
    ("/v5/market/recent-trade", {"category": "spot", "symbol": "BTCUSDC", "limit": 10}),
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--burst", type=int, default=120)
    args = ap.parse_args()
    results: dict = {}

    async with aiohttp.ClientSession() as session:
        section("Q7.a — rate-limit headers on public endpoints (api.bybit.eu)")
        for path, params in PUBLIC:
            data, status, headers = await get(session, path, params, host="eu", return_headers=True)
            rl = {
                k: v
                for k, v in headers.items()
                if "limit" in k.lower() or k.lower().startswith("x-bapi")
            }
            print(
                f"  {path:32s} HTTP {status} retCode={data.get('retCode')} headers={rl or '(no X-Bapi-Limit headers)'}"
            )
            results[f"headers::{path}"] = rl
        print(
            "  → doc: X-Bapi-Limit / X-Bapi-Limit-Status / X-Bapi-Limit-Reset-Timestamp are returned "
            "on PRIVATE (authenticated) endpoints only; public market endpoints share an IP limit."
        )

        section(
            f"Q7.b — burst test: {args.burst} concurrent GET /v5/market/kline (limit=1000) on api.bybit.eu"
        )
        t0 = time.time()

        async def one(i):
            try:
                data, status, headers = await get(
                    session,
                    "/v5/market/kline",
                    {"category": "spot", "symbol": "BTCUSDC", "interval": "60", "limit": 1000},
                    host="eu",
                    return_headers=True,
                )
                return status, data.get("retCode"), data.get("retMsg")
            except Exception as exc:  # noqa: BLE001
                return "EXC", None, repr(exc)[:80]

        res = await asyncio.gather(*(one(i) for i in range(args.burst)))
        dt = time.time() - t0
        from collections import Counter

        c = Counter((s, rc) for s, rc, _ in res)
        print(f"  {args.burst} requests in {dt:.2f}s → outcomes {dict(c)}")
        bad = [r for r in res if r[0] != 200 or r[1] != 0]
        if bad:
            print("  first non-OK:", bad[:3])
        results["burst"] = {
            "n": args.burst,
            "seconds": dt,
            "outcomes": {str(k): v for k, v in c.items()},
            "bad": bad[:5],
        }

        key, secret = load_env_keys()
        if key and secret:
            section("Q7.c — rate-limit headers on a private endpoint (authenticated, read-only)")
            import hashlib
            import hmac

            ts = str(int(time.time() * 1000))
            recv = "5000"
            query = "accountType=UNIFIED"
            sign = hmac.new(
                secret.encode(), (ts + key + recv + query).encode(), hashlib.sha256
            ).hexdigest()
            hdr = {
                "X-BAPI-API-KEY": key,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": recv,
                "X-BAPI-SIGN": sign,
            }
            async with session.get(
                HOSTS["eu"] + "/v5/account/wallet-balance?" + query, headers=hdr
            ) as resp:
                data = await resp.json(content_type=None)
                rl = {k: v for k, v in resp.headers.items() if k.lower().startswith("x-bapi")}
                print(
                    f"  HTTP {resp.status} retCode={data.get('retCode')} {data.get('retMsg')} headers={rl}"
                )
                results["private_headers"] = rl
        else:
            print("\n(no BYBIT_API_KEY in .env → Q7.c private-endpoint headers not captured)")

    section("Q7.d — ccxt.bybit rate limiting model")
    ex = ccxt.bybit()
    api = ex.describe()["api"]
    print(
        f"  ex.rateLimit = {ex.rateLimit} ms between weighted units → {1000 / ex.rateLimit:.0f} units/s"
    )
    for grp, method, path in (
        ("public", "get", "v5/market/kline"),
        ("public", "get", "v5/market/orderbook"),
        ("public", "get", "v5/market/tickers"),
        ("public", "get", "v5/market/instruments-info"),
        ("private", "get", "v5/account/wallet-balance"),
        ("private", "get", "v5/order/realtime"),
        ("private", "post", "v5/order/create"),
        ("private", "post", "v5/order/cancel"),
        ("private", "get", "v5/execution/list"),
    ):
        print(f"  cost {grp}.{method.upper():4s} {path:32s} = {api[grp][method].get(path)}")
    results["ccxt_rateLimit_ms"] = ex.rateLimit
    results["ccxt_costs"] = {
        f"{g}.{m}.{p}": api[g][m].get(p)
        for g, m, p in (
            ("public", "get", "v5/market/kline"),
            ("private", "post", "v5/order/create"),
            ("private", "post", "v5/order/cancel"),
            ("private", "get", "v5/order/realtime"),
        )
    }

    section("Q7.e — KrakenBot load estimate vs Bybit limits (doc values)")
    print(
        "  Doc (2025/26): public market endpoints ≈ 600 req / 5 s per IP; private endpoints 10–20 req/s per UID "
        "(order create/cancel 20/s spot, 50/s VIP), wallet-balance 50 req/s. WS: ≤10 args/subscribe, "
        "500 connections / 5 min per IP."
    )
    print(
        "  Collector: 3 pairs × 7 TF = 21 kline topics + 3 tickers over ONE WebSocket (no REST). "
        "REST only at startup/backfill: ~21–100 kline calls. → negligible."
    )
    print(
        "  Trader: ≤ a few orders/min + order status polls (order_manager) ≈ < 1 req/s. → < 5 % of private limit."
    )
    print(
        "  Backfill 1 y × 21 series ≈ 700 calls; 15 months EU history ≈ 2 532 calls → < 15 min sequential."
    )
    save_json("q7_ratelimits.json", results)


if __name__ == "__main__":
    asyncio.run(main())
