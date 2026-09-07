"""Q1 — Bybit EU endpoints, clock offset, recv_window, authenticated calls.

Usage: poetry run python scripts/audit/bybit_q1_endpoints.py
Read-only. Uses BYBIT_API_KEY / BYBIT_API_SECRET from .env if present.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import statistics
import sys

import aiohttp
import ccxt.async_support as ccxt_async

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bybit_common import (  # noqa: E402
    HOSTS,
    get,
    load_env_keys,
    now_ms,
    save_json,
    section,
    truncate,
)


async def clock_offset(session: aiohttp.ClientSession, host: str, n: int = 5) -> dict:
    offsets, rtts = [], []
    for _ in range(n):
        t0 = now_ms()
        data = await get(session, "/v5/market/time", host=host)
        t1 = now_ms()
        server = int(data["time"])
        rtts.append(t1 - t0)
        offsets.append(server - (t0 + t1) // 2)
        await asyncio.sleep(0.2)
    return {
        "host": HOSTS[host],
        "sample": data,
        "rtt_ms": rtts,
        "offset_ms": offsets,
        "offset_median_ms": statistics.median(offsets),
        "rtt_median_ms": statistics.median(rtts),
    }


async def all_spot_instruments(session: aiohttp.ClientSession, host: str) -> list[dict]:
    out: list[dict] = []
    cursor = None
    while True:
        params = {"category": "spot", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        data = await get(session, "/v5/market/instruments-info", params, host=host)
        out.extend(data["result"]["list"])
        cursor = data["result"].get("nextPageCursor")
        if not cursor:
            break
    return out


async def main() -> None:
    results: dict = {}
    async with aiohttp.ClientSession() as session:
        section("Q1.a — Server time / clock offset / RTT per host")
        for host in HOSTS:
            r = await clock_offset(session, host)
            results[f"time_{host}"] = r
            print(
                f"{host:7s} {r['host']:26s} offset(median)={r['offset_median_ms']:+d} ms  "
                f"rtt(median)={r['rtt_median_ms']} ms  raw={truncate(r['sample'], 200)}"
            )
        print(
            "Bybit default recv_window = 5000 ms (doc). Request rejected if "
            "|server_time - timestamp| > recv_window (retCode 10002)."
        )

        section("Q1.b — Spot instrument universe: global vs EU host")
        inst = {}
        for host in HOSTS:
            lst = await all_spot_instruments(session, host)
            inst[host] = {i["symbol"]: i for i in lst}
            usdc = sorted(s for s in inst[host] if s.endswith("USDC"))
            trading = sum(1 for i in lst if i["status"] == "Trading")
            print(f"{host:7s}: {len(lst)} spot symbols ({trading} Trading), {len(usdc)} *USDC")
            results[f"instruments_{host}_count"] = len(lst)
            results[f"instruments_{host}_usdc"] = usdc
        only_global = sorted(set(inst["global"]) - set(inst["eu"]))
        only_eu = sorted(set(inst["eu"]) - set(inst["global"]))
        print(f"only on global ({len(only_global)}): {truncate(only_global, 400)}")
        print(f"only on EU     ({len(only_eu)}): {truncate(only_eu, 400)}")
        for sym in ("BTCUSDC", "ETHUSDC", "SOLUSDC"):
            g, e = inst["global"].get(sym), inst["eu"].get(sym)
            same = g == e
            print(
                f"{sym}: global={'yes' if g else 'NO'} eu={'yes' if e else 'NO'} identical_filters={same}"
            )
            if g and e and not same:
                print("   global:", truncate(g, 400))
                print("   eu    :", truncate(e, 400))
        results["only_global"] = only_global
        results["only_eu"] = only_eu

        section("Q1.c — Private endpoints exist on both hosts? (unauthenticated probe)")
        for host in HOSTS:
            for path in ("/v5/user/query-api", "/v5/account/wallet-balance"):
                data, status, headers = await get(
                    session, path, {"accountType": "UNIFIED"}, host=host, return_headers=True
                )
                print(f"{host:7s} GET {path:30s} HTTP {status} -> {truncate(data, 160)}")
                results[f"probe_{host}_{path}"] = {"status": status, "body": data}

    section("Q1.d — ccxt.bybit hostname handling")
    for hostname in ("bybit.com", "bybit.eu"):
        ex = ccxt_async.bybit({"hostname": hostname, "enableRateLimit": True})
        try:
            url = ex.implode_hostname(ex.urls["api"]["public"])
            t = await ex.fetch_time()
            print(
                f"ccxt.bybit(hostname={hostname!r}) -> {url}  fetch_time={t}  "
                f"recvWindow={ex.options.get('recvWindow')}  "
                f"adjustForTimeDifference={ex.options.get('adjustForTimeDifference')}"
            )
        finally:
            await ex.close()

    section("Q1.e — Authenticated calls (read-only) with .env keys")
    key, secret = load_env_keys()
    if not key or not secret:
        print("BYBIT_API_KEY / BYBIT_API_SECRET NOT FOUND in .env -> authenticated part SKIPPED.")
        results["auth"] = "keys_missing"
    else:
        for hostname in ("bybit.com", "bybit.eu"):
            ex = ccxt_async.bybit(
                {
                    "apiKey": key,
                    "secret": secret,
                    "hostname": hostname,
                    "enableRateLimit": True,
                    "options": {"adjustForTimeDifference": True},
                }
            )
            try:
                api = await ex.privateGetV5UserQueryApi()
                print(f"[{hostname}] query-api -> {truncate(api, 700)}")
                bal = await ex.privateGetV5AccountWalletBalance({"accountType": "UNIFIED"})
                print(f"[{hostname}] wallet-balance -> {truncate(bal, 500)}")
                results[f"auth_{hostname}"] = {"query_api": api, "wallet": bal}
            except Exception as exc:  # noqa: BLE001
                print(f"[{hostname}] AUTH ERROR: {exc!r}")
                results[f"auth_{hostname}"] = {"error": repr(exc)}
            finally:
                await ex.close()

    save_json("q1_endpoints.json", results)


if __name__ == "__main__":
    asyncio.run(main())
