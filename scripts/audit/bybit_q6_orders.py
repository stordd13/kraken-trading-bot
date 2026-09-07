"""Q6 — Order types / payloads on Bybit spot via ccxt (NO order is sent).

Uses ``ccxt.bybit.create_order_request`` to build the exact JSON body that
ccxt would POST to ``/v5/order/create`` for the order shapes KrakenBot uses,
and documents the status/cancel endpoints. Read-only.

Usage: poetry run python scripts/audit/bybit_q6_orders.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

import aiohttp
import ccxt.async_support as ccxt_async

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bybit_common import HOSTS, get, load_env_keys, save_json, section, truncate  # noqa: E402


async def main() -> None:
    results: dict = {}
    ex = ccxt_async.bybit(
        {"hostname": "bybit.eu", "enableRateLimit": True, "options": {"defaultType": "spot"}}
    )
    try:
        section("Q6.a — ccxt.bybit capabilities (describe()['has'] subset) + options")
        has = ex.has
        keys = [
            "createOrder",
            "createMarketBuyOrderWithCost",
            "createMarketSellOrderWithCost",
            "createPostOnlyOrder",
            "createLimitOrder",
            "createMarketOrder",
            "createStopOrder",
            "createStopLimitOrder",
            "createStopMarketOrder",
            "createOrderWithTakeProfitAndStopLoss",
            "editOrder",
            "cancelOrder",
            "cancelAllOrders",
            "fetchOrder",
            "fetchOpenOrder",
            "fetchOpenOrders",
            "fetchClosedOrders",
            "fetchCanceledAndClosedOrders",
            "fetchMyTrades",
            "fetchBalance",
            "fetchOHLCV",
            "fetchOrderBook",
            "fetchTicker",
            "fetchTime",
        ]
        for k in keys:
            print(f"  has.{k:40s} = {has.get(k)}")
        opts = {
            k: ex.options.get(k)
            for k in (
                "createMarketBuyOrderRequiresPrice",
                "defaultType",
                "recvWindow",
                "adjustForTimeDifference",
                "enableUnifiedAccount",
                "enableUnifiedMargin",
                "brokerId",
                "timeDifference",
            )
        }
        print("  options:", opts)
        results["has"] = {k: has.get(k) for k in keys}
        results["options"] = opts

        section("Q6.b — relevant private endpoints & ccxt rate-limit cost (describe()['api'])")
        api = ex.describe()["api"]
        for method in ("get", "post"):
            for path, cost in api["private"][method].items():
                if (
                    "order" in path
                    and "v5" in path
                    and any(s in path for s in ("create", "cancel", "realtime", "history", "amend"))
                ):
                    print(f"  private.{method.upper():4s} {path:40s} cost={cost}")
        results["order_endpoints"] = {
            m: {p: c for p, c in api["private"][m].items() if "v5/order" in p}
            for m in ("get", "post")
        }

        section("Q6.c — exact POST /v5/order/create bodies ccxt would send (nothing is sent)")
        await ex.load_markets()
        cases = [
            (
                "market BUY, amount in BASE (0.001 BTC)",
                ("BTC/USDC", "market", "buy", 0.001, None, {}),
            ),
            (
                "market BUY, amount + price → ccxt computes cost",
                ("BTC/USDC", "market", "buy", 0.001, 79000, {}),
            ),
            (
                "market BUY with explicit cost=100 USDC",
                ("BTC/USDC", "market", "buy", None, None, {"cost": 100}),
            ),
            (
                "market BUY, createMarketBuyOrderRequiresPrice=False (amount = QUOTE)",
                (
                    "BTC/USDC",
                    "market",
                    "buy",
                    100,
                    None,
                    {"createMarketBuyOrderRequiresPrice": False},
                ),
            ),
            ("market SELL 0.001 BTC", ("BTC/USDC", "market", "sell", 0.001, None, {})),
            (
                "limit BUY 0.001 @ 79000 (GTC default)",
                ("BTC/USDC", "limit", "buy", 0.001, 79000, {}),
            ),
            ("limit BUY postOnly", ("BTC/USDC", "limit", "buy", 0.001, 79000, {"postOnly": True})),
            ("limit SELL IOC", ("BTC/USDC", "limit", "sell", 0.001, 80000, {"timeInForce": "IOC"})),
            ("limit SELL FOK", ("BTC/USDC", "limit", "sell", 0.001, 80000, {"timeInForce": "FOK"})),
            (
                "limit BUY with clientOrderId (→ orderLinkId)",
                (
                    "BTC/USDC",
                    "limit",
                    "buy",
                    0.001,
                    79000,
                    {"clientOrderId": "krakenbot-grid-btc-000123"},
                ),
            ),
            (
                "market SELL with stop trigger (stop-loss style)",
                ("BTC/USDC", "market", "sell", 0.001, None, {"triggerPrice": 75000}),
            ),
            ("limit BUY SOL 0.5 @ 100", ("SOL/USDC", "limit", "buy", 0.5, 100, {})),
        ]
        for label, (sym, typ, side, amt, price, params) in cases:
            try:
                req = ex.create_order_request(sym, typ, side, amt, price, params)
                body = req if isinstance(req, dict) else req
                print(f"  {label}\n     → {json.dumps(body, default=str)}")
                results[f"body::{label}"] = body
            except Exception as exc:  # noqa: BLE001
                print(f"  {label}\n     → ERROR {type(exc).__name__}: {truncate(str(exc), 300)}")
                results[f"body::{label}"] = {"error": repr(exc)}

        section("Q6.d — how ccxt maps status / cancel / lookup")
        print(
            "  fetch_order(id, symbol)      → GET /v5/order/realtime?category=spot&symbol=..&orderId=.. "
            "(falls back to /v5/order/history if not open) — has.fetchOrder =",
            has.get("fetchOrder"),
        )
        print(
            "  fetch_open_orders(symbol)    → GET /v5/order/realtime?category=spot&symbol=..&openOnly=0"
        )
        print(
            "  cancel_order(id, symbol)     → POST /v5/order/cancel {category, symbol, orderId | orderLinkId}"
        )
        print("  fetch_my_trades(symbol)      → GET /v5/execution/list?category=spot")
        print("  fetch_balance()              → GET /v5/account/wallet-balance?accountType=UNIFIED")
    finally:
        await ex.close()

    section("Q6.e — unauthenticated probes proving the endpoints exist on api.bybit.eu")
    async with aiohttp.ClientSession() as session:
        for path, params in (
            ("/v5/order/realtime", {"category": "spot", "symbol": "BTCUSDC"}),
            ("/v5/order/history", {"category": "spot"}),
            ("/v5/execution/list", {"category": "spot"}),
        ):
            data, status, _ = await get(session, path, params, host="eu", return_headers=True)
            print(f"  GET {path:22s} HTTP {status} → {truncate(data, 200)}")
        async with session.post(
            HOSTS["eu"] + "/v5/order/cancel",
            json={"category": "spot", "symbol": "BTCUSDC", "orderId": "x"},
        ) as resp:
            txt = await resp.text()
            print(f"  POST /v5/order/cancel   HTTP {resp.status} → {truncate(txt, 200)}")

    key, secret = load_env_keys()
    if key and secret:
        section("Q6.f — authenticated read-only: open orders + last executions (EU)")
        ex = ccxt_async.bybit(
            {
                "apiKey": key,
                "secret": secret,
                "hostname": "bybit.eu",
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        try:
            oo = await ex.fetch_open_orders("BTC/USDC")
            print("  open orders BTC/USDC:", truncate(oo, 400))
            tr = await ex.fetch_my_trades("BTC/USDC", limit=3)
            print("  last trades BTC/USDC:", truncate(tr, 600))
        except Exception as exc:  # noqa: BLE001
            print("  AUTH ERROR:", repr(exc))
        finally:
            await ex.close()
    else:
        print("\n(no BYBIT_API_KEY in .env → Q6.f authenticated read-only part skipped)")

    save_json("q6_orders.json", results)


if __name__ == "__main__":
    asyncio.run(main())
