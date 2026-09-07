"""Q5 — Bybit v5 public spot WebSocket: capture + behaviour tests.

Modes:
  --mode capture  (default) subscribe kline.1.BTCUSDC + tickers.BTCUSDC for
                  --duration seconds, ping every 20 s, dump raw messages.
  --mode noping   open a connection, subscribe, never ping; report when/if the
                  server closes it (up to --duration seconds).
  --mode limits   probe: >10 args in one subscribe, invalid topic, many topics
                  across several requests, subscribe echo format.

Usage:
    poetry run python scripts/audit/bybit_q5_ws_capture.py --host eu --duration 300
    poetry run python scripts/audit/bybit_q5_ws_capture.py --mode noping --duration 600
    poetry run python scripts/audit/bybit_q5_ws_capture.py --mode limits
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bybit_common import OUT_DIR, WS_HOSTS, ms_to_iso, save_json, section, truncate  # noqa: E402

PING_INTERVAL = 20  # Bybit doc recommendation


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


async def capture(host: str, duration: int, topics: list[str]) -> None:
    url = WS_HOSTS[host]
    section(f"Q5 capture on {url} for {duration}s, topics={topics}")
    raw: list[dict] = []
    t_end = time.time() + duration
    async with websockets.connect(url, ping_interval=None, max_size=2**22) as ws:
        sub = {"req_id": "audit-1", "op": "subscribe", "args": topics}
        await ws.send(json.dumps(sub))
        print(f"{now_iso()} SENT {sub}")
        last_ping = time.time()
        while time.time() < t_end:
            if time.time() - last_ping >= PING_INTERVAL:
                ping = {"req_id": f"ping-{int(time.time())}", "op": "ping"}
                await ws.send(json.dumps(ping))
                raw.append({"t": now_iso(), "dir": "out", "msg": ping})
                last_ping = time.time()
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except TimeoutError:
                continue
            data = json.loads(msg)
            raw.append({"t": now_iso(), "dir": "in", "msg": data})
            if len(raw) <= 6 or data.get("op") in ("subscribe", "pong", "ping"):
                print(f"{now_iso()} RECV {truncate(data, 400)}")
        close_code = ws.close_code
    print(f"connection closed by us; close_code={close_code}")

    # ---- analysis
    section("Q5 analysis")
    by_topic: dict[str, int] = {}
    klines = []
    for r in raw:
        if r["dir"] != "in":
            continue
        m = r["msg"]
        key = m.get("topic") or f"op:{m.get('op')}"
        by_topic[key] = by_topic.get(key, 0) + 1
        if str(m.get("topic", "")).startswith("kline."):
            klines.append(r)
    print("messages by topic/op:", by_topic)
    confirmed = [r for r in klines if r["msg"]["data"][0].get("confirm") is True]
    unconfirmed = [r for r in klines if r["msg"]["data"][0].get("confirm") is False]
    print(
        f"kline msgs: {len(klines)} (confirm=true: {len(confirmed)}, confirm=false: {len(unconfirmed)})"
    )
    if klines:
        k = klines[0]["msg"]["data"][0]
        print("kline fields:", sorted(k.keys()))
        for r in klines[:1] + confirmed[:2]:
            d = r["msg"]["data"][0]
            print(
                f"  start={d['start']} ({ms_to_iso(d['start'])}) end={d['end']} ({ms_to_iso(d['end'])}) "
                f"end-start={int(d['end']) - int(d['start'])} ms confirm={d['confirm']} "
                f"timestamp={d.get('timestamp')} ts(msg)={r['msg'].get('ts')}"
            )
        print(
            "→ end - start = interval - 1 ms ⇒ `end` is INCLUSIVE (last ms), same convention as Binance `T`."
        )
        # timing: when does the confirm=true message arrive relative to `end`?
        for r in confirmed[:3]:
            d = r["msg"]["data"][0]
            recv_ms = int(datetime.fromisoformat(r["t"]).timestamp() * 1000)
            print(
                f"  confirm=true received at {r['t']} = {recv_ms - int(d['end'])} ms after candle end"
            )
        # do we get a message for the *new* candle right after confirm?
        if confirmed:
            idx = raw.index(confirmed[0])
            nxt = [
                x for x in raw[idx + 1 :] if str(x["msg"].get("topic", "")).startswith("kline.")
            ][:1]
            if nxt:
                d = nxt[0]["msg"]["data"][0]
                print(
                    f"  next kline msg after confirm: start={ms_to_iso(d['start'])} confirm={d['confirm']}"
                )
    pongs = [r for r in raw if r["dir"] == "in" and r["msg"].get("op") == "pong"]
    if pongs:
        print("pong format:", truncate(pongs[0]["msg"], 300))
    tick = [
        r for r in raw if r["dir"] == "in" and str(r["msg"].get("topic", "")).startswith("tickers.")
    ]
    if tick:
        print("ticker sample:", truncate(tick[0]["msg"], 500))
        print("ticker fields:", sorted(tick[0]["msg"]["data"].keys()))
        print(f"ticker msgs: {len(tick)}; types: {sorted({r['msg'].get('type') for r in tick})}")
    # save 3 raw kline messages + subscribe ack for the report
    sample = {
        "subscribe_ack": next((r for r in raw if r["msg"].get("op") == "subscribe"), None),
        "kline_first": klines[0] if klines else None,
        "kline_confirmed": confirmed[:2],
        "pong": pongs[:1],
        "ticker": tick[:1],
    }
    save_json(f"q5_capture_{host}_samples.json", sample)
    save_json(f"q5_capture_{host}_raw.json", raw)


async def noping(host: str, duration: int) -> None:
    url = WS_HOSTS[host]
    section(f"Q5 no-ping test on {url}: subscribe, never send ping, wait up to {duration}s")
    t0 = time.time()
    last_msg = t0
    n = 0
    try:
        async with websockets.connect(url, ping_interval=None, max_size=2**22) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": ["kline.1.BTCUSDC"]}))
            while time.time() - t0 < duration:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5.0)
                    n += 1
                    last_msg = time.time()
                except TimeoutError:
                    continue
        print(
            f"connection still alive after {duration}s without client ping ({n} msgs) — closed by us. "
            f"close_code={ws.close_code} close_reason={ws.close_reason!r}"
        )
    except websockets.ConnectionClosed as exc:
        print(
            f"SERVER CLOSED connection after {time.time() - t0:.1f}s without client ping: "
            f"code={exc.rcvd.code if exc.rcvd else None} reason={exc.rcvd.reason if exc.rcvd else None!r} "
            f"msgs={n} last_msg={time.time() - last_msg:.1f}s ago"
        )


async def limits(host: str) -> None:
    url = WS_HOSTS[host]
    section(f"Q5 limits probe on {url}")

    async def send_and_collect(ws, payload, wait=2.0):
        await ws.send(json.dumps(payload))
        out = []
        t_end = time.time() + wait
        while time.time() < t_end:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.5))
            except TimeoutError:
                continue
            if "op" in m:
                out.append(m)
        return out

    syms = [
        "BTCUSDC",
        "ETHUSDC",
        "SOLUSDC",
        "XRPUSDC",
        "DOGEUSDC",
        "ADAUSDC",
        "LINKUSDC",
        "AVAXUSDC",
        "DOTUSDC",
        "TONUSDC",
        "SUIUSDC",
        "LTCUSDC",
    ]
    async with websockets.connect(url, ping_interval=None, max_size=2**22) as ws:
        # 1) 12 args in one request (doc: spot max 10 args per request)
        args = [f"tickers.{s}" for s in syms]
        res = await send_and_collect(ws, {"req_id": "many", "op": "subscribe", "args": args})
        print(f"subscribe with {len(args)} args → {truncate(res, 400)}")
        # 2) invalid topic
        res = await send_and_collect(
            ws, {"req_id": "bad", "op": "subscribe", "args": ["kline.1.NOPEUSDC"]}
        )
        print(f"subscribe invalid symbol → {truncate(res, 400)}")
        res = await send_and_collect(
            ws, {"req_id": "bad2", "op": "subscribe", "args": ["kline.7.BTCUSDC"]}
        )
        print(f"subscribe invalid interval → {truncate(res, 400)}")
        # 3) the project's full set: 3 pairs × 7 intervals = 21 kline topics + 3 tickers, in chunks of 10
        topics = [
            f"kline.{i}.{s}"
            for s in ("BTCUSDC", "ETHUSDC", "SOLUSDC")
            for i in ("1", "5", "15", "60", "240", "D", "W")
        ] + [f"tickers.{s}" for s in ("BTCUSDC", "ETHUSDC", "SOLUSDC")]
        acks = []
        for i in range(0, len(topics), 10):
            acks += await send_and_collect(
                ws, {"req_id": f"chunk{i}", "op": "subscribe", "args": topics[i : i + 10]}, wait=1.5
            )
        print(f"{len(topics)} project topics in chunks of 10 → acks: {truncate(acks, 500)}")
        # 4) unsubscribe format
        res = await send_and_collect(
            ws, {"req_id": "unsub", "op": "unsubscribe", "args": ["tickers.BTCUSDC"]}
        )
        print(f"unsubscribe → {truncate(res, 300)}")
        # 5) ping/pong format
        res = await send_and_collect(ws, {"req_id": "p1", "op": "ping"})
        print(f"ping → {truncate(res, 300)}")
        # 6) duplicate subscription
        res = await send_and_collect(
            ws, {"req_id": "dup", "op": "subscribe", "args": ["kline.1.BTCUSDC"]}
        )
        print(f"duplicate subscribe → {truncate(res, 300)}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="eu", choices=list(WS_HOSTS))
    ap.add_argument("--mode", default="capture", choices=["capture", "noping", "limits"])
    ap.add_argument("--duration", type=int, default=300)
    ap.add_argument("--topics", default="kline.1.BTCUSDC,tickers.BTCUSDC")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.mode == "capture":
        await capture(args.host, args.duration, args.topics.split(","))
    elif args.mode == "noping":
        await noping(args.host, args.duration)
    else:
        await limits(args.host)


if __name__ == "__main__":
    asyncio.run(main())
