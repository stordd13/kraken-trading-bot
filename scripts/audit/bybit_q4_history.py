"""Q4 — Historical kline depth on Bybit spot (global vs EU host) + public dumps.

For each pair × interval: first available candle (start-only query returns
records from ``start`` onward, list is sorted descending), estimated candle
count, and estimated API calls to import everything.
``--gap-check`` pages the full 60-minute history and reports missing candles.

Usage:
    poetry run python scripts/audit/bybit_q4_history.py [--gap-check]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import math
from pathlib import Path
import sys

import aiohttp
import ccxt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bybit_common import (  # noqa: E402
    HOSTS,
    MIN_TO_BYBIT,
    PAIRS,
    get_retry,
    ms_to_iso,
    now_ms,
    save_json,
    section,
    symbol,
    truncate,
)

EPOCH_2017 = int(datetime(2017, 1, 1, tzinfo=UTC).timestamp() * 1000)
KLINE_RATE_LIMIT_PER_5S = 600  # Bybit doc: public market endpoints, per IP


async def first_candle(session, host, sym, interval):
    data = await get_retry(
        session,
        "/v5/market/kline",
        {
            "category": "spot",
            "symbol": sym,
            "interval": interval,
            "start": EPOCH_2017,
            "limit": 1000,
        },
        host=host,
    )
    lst = data["result"]["list"]
    if not lst:
        return None, data
    earliest = lst[-1]  # descending order → last element is the earliest
    # cross-check with limit=1
    d1 = await get_retry(
        session,
        "/v5/market/kline",
        {"category": "spot", "symbol": sym, "interval": interval, "start": EPOCH_2017, "limit": 1},
        host=host,
    )
    l1 = d1["result"]["list"]
    consistent = bool(l1) and l1[0][0] == earliest[0]
    return {
        "start_ms": int(earliest[0]),
        "start_iso": ms_to_iso(earliest[0]),
        "raw": earliest,
        "limit1_consistent": consistent,
        "batch_len": len(lst),
    }, data


async def gap_check(session, host, sym, interval_min=60):
    """Page the whole history for one interval and count missing candles."""
    step = interval_min * 60_000
    start = EPOCH_2017
    times: list[int] = []
    calls = 0
    while True:
        data = await get_retry(
            session,
            "/v5/market/kline",
            {
                "category": "spot",
                "symbol": sym,
                "interval": str(interval_min),
                "start": start,
                "limit": 1000,
            },
            host=host,
        )
        calls += 1
        lst = data["result"]["list"]
        if not lst:
            break
        batch = sorted(int(c[0]) for c in lst)
        times.extend(batch)
        if len(lst) < 1000:
            break
        start = batch[-1] + step
        await asyncio.sleep(0.05)
    times = sorted(set(times))
    if not times:
        return {"count": 0, "calls": calls}
    expected = (times[-1] - times[0]) // step + 1
    gaps = []
    for a, b in zip(times, times[1:], strict=False):
        if b - a != step:
            gaps.append({"from": ms_to_iso(a), "to": ms_to_iso(b), "missing": (b - a) // step - 1})
    return {
        "count": len(times),
        "expected": expected,
        "missing": expected - len(times),
        "first": ms_to_iso(times[0]),
        "last": ms_to_iso(times[-1]),
        "calls": calls,
        "gaps": gaps[:30],
        "n_gaps": len(gaps),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap-check", action="store_true")
    args = ap.parse_args()
    results: dict = {}
    now = now_ms()
    async with aiohttp.ClientSession() as session:
        section("Q4.a — kline query semantics (proof)")
        d = await get_retry(
            session,
            "/v5/market/kline",
            {
                "category": "spot",
                "symbol": "BTCUSDC",
                "interval": "60",
                "start": EPOCH_2017,
                "limit": 3,
            },
            host="eu",
        )
        print("start=2017-01-01, limit=3 →", truncate(d, 500))
        print("→ list is DESCENDING; with start only, Bybit returns candles from `start` onward.")
        d = await get_retry(
            session,
            "/v5/market/kline",
            {"category": "spot", "symbol": "BTCUSDC", "interval": "60", "limit": 2},
            host="eu",
        )
        print("no start/end, limit=2 →", truncate(d, 400))
        print(
            "→ row format: [startTime(ms), open, high, low, close, volume(base), turnover(quote)]"
        )

        for host in HOSTS:
            section(f"Q4.b — first candle per pair × interval on {HOSTS[host]}")
            print(
                f"{'pair':9s} {'itv':>5s} {'first candle (UTC)':26s} {'est. candles':>13s} {'calls@1000':>10s} {'limit1 ok':>9s}"
            )
            total_calls = 0
            total_candles = 0
            for pair in PAIRS:
                sym = symbol(pair)
                for minutes, itv in MIN_TO_BYBIT.items():
                    fc, raw = await first_candle(session, host, sym, itv)
                    key = f"{host}_{sym}_{itv}"
                    if fc is None:
                        print(f"{pair:9s} {itv:>5s} {'NO DATA':26s} raw={truncate(raw, 120)}")
                        results[key] = None
                        continue
                    n = (now - fc["start_ms"]) // (minutes * 60_000) + 1
                    calls = math.ceil(n / 1000)
                    total_calls += calls
                    total_candles += n
                    results[key] = {**fc, "est_candles": n, "calls": calls}
                    print(
                        f"{pair:9s} {itv:>5s} {fc['start_iso']:26s} {n:>13,d} {calls:>10d} {str(fc['limit1_consistent']):>9s}"
                    )
                    await asyncio.sleep(0.05)
            secs_ccxt = total_calls * ccxt.bybit().rateLimit / 1000
            secs_doc = total_calls / (KLINE_RATE_LIMIT_PER_5S / 5)
            print(
                f"TOTAL {host}: ≈{total_candles:,d} candles, {total_calls} API calls of 1000 → "
                f"≥{secs_ccxt:.0f}s at ccxt rateLimit {ccxt.bybit().rateLimit} ms "
                f"(≥{secs_doc:.0f}s at doc limit {KLINE_RATE_LIMIT_PER_5S}/5s); "
                f"realistic sequential ≈ {total_calls * 0.35 / 60:.1f} min at ~350 ms/call"
            )
            results[f"{host}_totals"] = {"candles": total_candles, "calls": total_calls}

        if args.gap_check:
            for host in HOSTS:
                section(f"Q4.c — gap check, interval 60, full history on {HOSTS[host]}")
                for pair in PAIRS:
                    g = await gap_check(session, host, symbol(pair))
                    results[f"gap_{host}_{symbol(pair)}"] = g
                    print(
                        f"{pair:9s} candles={g.get('count'):,} expected={g.get('expected'):,} "
                        f"missing={g.get('missing')} n_gaps={g.get('n_gaps')} calls={g['calls']} "
                        f"first={g.get('first')} last={g.get('last')}"
                    )
                    for gap in g.get("gaps", [])[:8]:
                        print(f"     gap {gap['from']} → {gap['to']} ({gap['missing']} candles)")

        section("Q4.d — public.bybit.com downloadable dumps")
        async with session.get("https://public.bybit.com/") as resp:
            root = await resp.text()
        import re

        dirs = re.findall(r'href="([^"]+)"', root)
        print("root dirs:", dirs)
        async with session.get("https://public.bybit.com/spot/") as resp:
            spot = re.findall(r'href="([^"]+)"', await resp.text())
        usdc_dirs = [d for d in spot if d.rstrip("/") in ("BTCUSDC", "ETHUSDC", "SOLUSDC")]
        print(f"spot/ has {len(spot)} symbol dirs; our pairs present: {usdc_dirs}")
        for d_ in usdc_dirs:
            async with session.get(f"https://public.bybit.com/spot/{d_}") as resp:
                files = re.findall(r'href="([^"]+)"', await resp.text())
            print(f"  {d_}: {len(files)} files, first={files[:2]}, last={files[-2:]}")
            results[f"dump_{d_}"] = {"n_files": len(files), "first": files[:2], "last": files[-2:]}
        # sample content of one file (header + 2 rows)
        import gzip

        async with session.get(
            "https://public.bybit.com/spot/BTCUSDC/BTCUSDC_2026-09-06.csv.gz"
        ) as resp:
            content = gzip.decompress(await resp.read()).decode()
        head = content.splitlines()[:3]
        print("  sample BTCUSDC_2026-09-06.csv.gz:", head)
        print(
            "  → these are TRADE (tick) dumps, not klines. kline_for_metatrader4/ covers USDT perp only."
        )
        async with session.get("https://public.bybit.com/kline_for_metatrader4/") as resp:
            mt4 = re.findall(r'href="([^"]+)"', await resp.text())
        print(
            f"  kline_for_metatrader4/: {len(mt4)} dirs, USDC dirs: {[d for d in mt4 if 'USDC' in d]}"
        )
        results["dump_sample"] = head
        results["mt4_dirs"] = mt4

    save_json("q4_history.json", results)


if __name__ == "__main__":
    asyncio.run(main())
