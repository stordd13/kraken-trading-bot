"""Q8 — Close-price divergence Binance vs Bybit, BTC/USDC 1h, last N days.

Bybit side: REST kline (global and EU hosts). Binance side: DB
(``exchange='binance'`` via DATABASE_URL, timestamps are period-END = start+1h)
with automatic fallback to the Binance public REST API when the DB is
unreachable.

Usage: poetry run python scripts/audit/bybit_q8_price_diff.py --days 90 [--binance-source db|api]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
import sys

import aiohttp
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bybit_common import get_retry, ms_to_iso, now_ms, save_json, section  # noqa: E402

H_MS = 3_600_000


async def bybit_closes(
    session, host: str, start_ms: int, end_ms: int, symbol="BTCUSDC"
) -> pd.Series:
    rows = {}
    cur_end = end_ms
    calls = 0
    while cur_end > start_ms:
        data = await get_retry(
            session,
            "/v5/market/kline",
            {
                "category": "spot",
                "symbol": symbol,
                "interval": "60",
                "start": start_ms,
                "end": cur_end,
                "limit": 1000,
            },
            host=host,
        )
        calls += 1
        lst = data["result"]["list"]
        if not lst:
            break
        for c in lst:
            rows[int(c[0])] = (float(c[4]), float(c[5]))
        oldest = min(int(c[0]) for c in lst)
        if oldest <= start_ms or len(lst) < 1000:
            break
        cur_end = oldest - 1
    print(
        f"  bybit[{host}] {len(rows)} candles in {calls} calls, "
        f"{ms_to_iso(min(rows))} → {ms_to_iso(max(rows))}"
    )
    s = pd.Series({k: v[0] for k, v in rows.items()}).sort_index()
    v = pd.Series({k: v[1] for k, v in rows.items()}).sort_index()
    s.name, v.name = f"bybit_{host}", f"vol_{host}"
    return s, v


async def binance_from_db(start_ms: int) -> pd.Series | None:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("  DATABASE_URL not set")
        return None
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(url, connect_args={"timeout": 10})
        start = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
        async with engine.connect() as conn:
            r = await conn.execute(
                text(
                    "SELECT timestamp, close FROM market_data_ohlc WHERE exchange='binance' AND pair='BTC/USDC' "
                    "AND interval=60 AND timestamp >= :start ORDER BY timestamp"
                ),
                {"start": start},
            )
            rows = r.fetchall()
        await engine.dispose()
        if not rows:
            print("  DB returned 0 rows")
            return None
        # DB timestamp = period end (open_time + 1h) → convert back to open time to align with Bybit
        s = pd.Series({int(ts.timestamp() * 1000) - H_MS: float(c) for ts, c in rows}).sort_index()
        s.name = "binance"
        print(
            f"  binance[DB] {len(s)} candles, {ms_to_iso(s.index.min())} → {ms_to_iso(s.index.max())}"
        )
        return s
    except Exception as exc:  # noqa: BLE001
        print(f"  DB unavailable: {type(exc).__name__}: {str(exc)[:120]}")
        return None


async def binance_from_api(session, start_ms: int, end_ms: int) -> pd.Series | None:
    rows = {}
    cur = start_ms
    try:
        while cur < end_ms:
            async with session.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": "BTCUSDC", "interval": "1h", "startTime": cur, "limit": 1000},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    print(f"  binance API HTTP {resp.status}: {(await resp.text())[:200]}")
                    return None
                lst = await resp.json()
            if not lst:
                break
            for c in lst:
                rows[int(c[0])] = float(c[4])
            cur = int(lst[-1][0]) + H_MS
            if len(lst) < 1000:
                break
        s = pd.Series(rows).sort_index()
        s.name = "binance"
        print(
            f"  binance[API] {len(s)} candles, {ms_to_iso(s.index.min())} → {ms_to_iso(s.index.max())}"
        )
        return s
    except Exception as exc:  # noqa: BLE001
        print(f"  binance API error: {exc!r}")
        return None


def compare(bn: pd.Series, by: pd.Series, label: str) -> dict:
    df = pd.concat([bn, by], axis=1, join="inner").dropna()
    diff_bps = (df.iloc[:, 1] / df.iloc[:, 0] - 1) * 1e4
    ret_bn, ret_by = np.log(df.iloc[:, 0]).diff().dropna(), np.log(df.iloc[:, 1]).diff().dropna()
    imax = diff_bps.abs().idxmax()
    out = {
        "label": label,
        "n_matched": int(len(df)),
        "close_corr": float(df.iloc[:, 0].corr(df.iloc[:, 1])),
        "return_corr_1h": float(ret_bn.corr(ret_by)),
        "mean_diff_bps": float(diff_bps.mean()),
        "mean_abs_diff_bps": float(diff_bps.abs().mean()),
        "median_abs_diff_bps": float(diff_bps.abs().median()),
        "p95_abs_diff_bps": float(diff_bps.abs().quantile(0.95)),
        "p99_abs_diff_bps": float(diff_bps.abs().quantile(0.99)),
        "max_abs_diff_bps": float(diff_bps.abs().max()),
        "max_abs_at": ms_to_iso(int(imax)),
        "max_abs_binance": float(df.loc[imax].iloc[0]),
        "max_abs_bybit": float(df.loc[imax].iloc[1]),
        "share_gt_10bps": float((diff_bps.abs() > 10).mean()),
        "share_gt_25bps": float((diff_bps.abs() > 25).mean()),
    }
    print(
        f"  [{label}] n={out['n_matched']} close_corr={out['close_corr']:.6f} ret_corr(1h)={out['return_corr_1h']:.4f} "
        f"mean={out['mean_diff_bps']:+.2f} bps |mean|={out['mean_abs_diff_bps']:.2f} median={out['median_abs_diff_bps']:.2f} "
        f"p95={out['p95_abs_diff_bps']:.2f} p99={out['p99_abs_diff_bps']:.2f} max={out['max_abs_diff_bps']:.2f} bps "
        f"at {out['max_abs_at']} (binance {out['max_abs_binance']} vs bybit {out['max_abs_bybit']}) "
        f">10bps: {out['share_gt_10bps']:.1%} >25bps: {out['share_gt_25bps']:.1%}"
    )
    # top-5 largest divergences for the report
    top = diff_bps.abs().sort_values(ascending=False).head(5)
    out["top5"] = [
        {
            "ts": ms_to_iso(int(i)),
            "diff_bps": float(diff_bps[i]),
            "binance": float(df.loc[i].iloc[0]),
            "bybit": float(df.loc[i].iloc[1]),
        }
        for i in top.index
    ]
    for t in out["top5"]:
        print(f"     {t['ts']} {t['diff_bps']:+.2f} bps  binance={t['binance']} bybit={t['bybit']}")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--binance-source", default="auto", choices=["auto", "db", "api"])
    args = ap.parse_args()
    from dotenv import load_dotenv

    load_dotenv()
    end_ms = (now_ms() // H_MS) * H_MS - H_MS  # last fully closed hour
    start_ms = end_ms - args.days * 24 * H_MS
    results: dict = {"days": args.days, "start": ms_to_iso(start_ms), "end": ms_to_iso(end_ms)}
    section(f"Q8 — BTC/USDC 1h closes, {args.days} days: {results['start']} → {results['end']}")
    async with aiohttp.ClientSession() as session:
        by_g, vol_g = await bybit_closes(session, "global", start_ms, end_ms)
        by_e, vol_e = await bybit_closes(session, "eu", start_ms, end_ms)
        bn = None
        src = None
        if args.binance_source in ("auto", "db"):
            bn = await binance_from_db(start_ms)
            src = "db" if bn is not None else None
        if bn is None and args.binance_source in ("auto", "api"):
            bn = await binance_from_api(session, start_ms, end_ms)
            src = "api" if bn is not None else None
    if bn is None:
        print("  NO BINANCE DATA — cannot compare.")
        results["error"] = "no binance data"
        save_json("q8_price_diff.json", results)
        return
    bn = bn[(bn.index >= start_ms) & (bn.index <= end_ms)]
    results["binance_source"] = src
    print(f"  Binance source: {src}")
    section("Q8 — comparison")
    results["global_vs_binance"] = compare(bn, by_g, "bybit GLOBAL vs binance")
    results["eu_vs_binance"] = compare(bn, by_e, "bybit EU vs binance")
    results["eu_vs_global"] = compare(
        by_g.rename("bybit_global_as_ref"), by_e, "bybit EU vs bybit GLOBAL"
    )
    # zero-volume candles on EU (stale closes)
    zero_e = int((vol_e[(vol_e.index >= start_ms)] == 0).sum())
    zero_g = int((vol_g[(vol_g.index >= start_ms)] == 0).sum())
    print(f"  zero-volume 1h candles: EU={zero_e}/{len(vol_e)}  global={zero_g}/{len(vol_g)}")
    print(f"  median 1h base volume: EU={vol_e.median():.3f} BTC  global={vol_g.median():.3f} BTC")
    results["zero_volume_1h"] = {
        "eu": zero_e,
        "global": zero_g,
        "n_eu": int(len(vol_e)),
        "n_global": int(len(vol_g)),
    }
    results["median_vol_1h_btc"] = {"eu": float(vol_e.median()), "global": float(vol_g.median())}
    save_json("q8_price_diff.json", results)


if __name__ == "__main__":
    asyncio.run(main())
