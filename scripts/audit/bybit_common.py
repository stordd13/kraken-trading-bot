"""Shared helpers for the Bybit EU integration audit (B0).

Throwaway exploration code — read-only, public endpoints unless API keys are
present in ``.env`` (``BYBIT_API_KEY`` / ``BYBIT_API_SECRET``).
Raw outputs go to ``$BYBIT_AUDIT_OUT`` (default ``/tmp/bybit_audit``).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import time
from typing import Any

import aiohttp

HOSTS: dict[str, str] = {
    "global": "https://api.bybit.com",
    "eu": "https://api.bybit.eu",
}
WS_HOSTS: dict[str, str] = {
    "global": "wss://stream.bybit.com/v5/public/spot",
    "eu": "wss://stream.bybit.eu/v5/public/spot",
}

PAIRS: list[str] = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]

# Project interval (minutes) ↔ Bybit v5 kline interval string
MIN_TO_BYBIT: dict[int, str] = {
    1: "1",
    5: "5",
    15: "15",
    60: "60",
    240: "240",
    1440: "D",
    10080: "W",
}
BYBIT_TO_MIN: dict[str, int] = {v: k for k, v in MIN_TO_BYBIT.items()}

OUT_DIR = Path(os.environ.get("BYBIT_AUDIT_OUT", "/tmp/bybit_audit"))


def symbol(pair: str) -> str:
    """'BTC/USDC' → 'BTCUSDC'."""
    return pair.replace("/", "")


def ms_to_iso(ms: int | str) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC).isoformat()


def now_ms() -> int:
    return int(time.time() * 1000)


async def get(
    session: aiohttp.ClientSession,
    path: str,
    params: dict[str, Any] | None = None,
    host: str = "global",
    return_headers: bool = False,
) -> Any:
    """GET a Bybit v5 endpoint and return the parsed JSON (and headers)."""
    url = HOSTS[host] + path
    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        data = await resp.json(content_type=None)
        if return_headers:
            return data, resp.status, dict(resp.headers)
        return data


async def get_retry(
    session: aiohttp.ClientSession,
    path: str,
    params: dict[str, Any] | None = None,
    host: str = "global",
    retries: int = 5,
) -> Any:
    """GET with simple retry on network errors / rate limiting."""
    for attempt in range(retries):
        try:
            data = await get(session, path, params, host)
            if data.get("retCode") == 10006:  # rate limit
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            return data
        except (TimeoutError, aiohttp.ClientError) as exc:
            print(f"  [retry {attempt + 1}/{retries}] {path} {params}: {exc!r}")
            await asyncio.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"GET {path} failed after {retries} retries")


def save_json(name: str, obj: Any) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / name
    p.write_text(json.dumps(obj, indent=2, default=str))
    print(f"[saved] {p}")
    return p


def truncate(obj: Any, n: int = 700) -> str:
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + f"... (+{len(s) - n} chars)"


def load_env_keys() -> tuple[str | None, str | None]:
    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv("BYBIT_API_KEY"), os.getenv("BYBIT_API_SECRET")


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
