"""Read-only diagnostic of the Bybit EU API keys and fund location (B1 follow-up).

For each key pair in .env (BYBIT_* read-only, BYBIT_TRADE_* trade) prints:
  - query-api: note, readOnly flag, permissions, IP whitelist, UTA flag, expiry
  - wallet-balance accountType=UNIFIED (what spot orders can use)
  - coins-balance FUND (Funding wallet — NOT usable by spot orders until transferred)

Never places an order. Usage: poetry run python scripts/audit/bybit_key_diag.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import ccxt.async_support as ccxt
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def probe(label, key, secret):
    ex = ccxt.bybit(
        {
            "apiKey": key,
            "secret": secret,
            "hostname": "bybit.eu",
            "options": {
                "defaultType": "spot",
                "adjustForTimeDifference": True,
                "enableUnifiedAccount": True,
            },
        }
    )
    try:
        r = await ex.privateGetV5UserQueryApi()
        res = r.get("result", {})
        keep = {
            k: res.get(k)
            for k in [
                "note",
                "readOnly",
                "permissions",
                "ips",
                "type",
                "uta",
                "unified",
                "expiredAt",
            ]
        }
        print(f"[{label}] query-api ->", json.dumps(keep))
        try:
            r = await ex.privateGetV5AccountWalletBalance({"accountType": "UNIFIED"})
            lst = r["result"]["list"][0]
            coins = [
                (c["coin"], c.get("walletBalance"), c.get("availableToWithdraw"))
                for c in lst.get("coin", [])
            ]
            print(
                f"[{label}] wallet-balance UNIFIED -> totalEquity={lst.get('totalEquity')} coins={coins}"
            )
        except Exception as e:
            print(f"[{label}] UNIFIED -> {type(e).__name__}: {str(e)[:160]}")
        for acct in ["FUND", "UNIFIED"]:
            try:
                r = await ex.privateGetV5AssetTransferQueryAccountCoinsBalance(
                    {"accountType": acct}
                )
                bal = [
                    (b["coin"], b.get("walletBalance"), b.get("transferBalance"))
                    for b in r["result"]["balance"]
                    if float(b.get("walletBalance") or 0) > 0
                ]
                print(f"[{label}] coins-balance {acct} -> {bal}")
            except Exception as e:
                print(f"[{label}] coins-balance {acct} -> {type(e).__name__}: {str(e)[:160]}")
    except Exception as e:
        print(f"[{label}] query-api -> {type(e).__name__}: {str(e)[:200]}")
    finally:
        await ex.close()


async def main():
    for label, prefix in (("readonly", "BYBIT_"), ("trade", "BYBIT_TRADE_")):
        key, secret = os.environ.get(f"{prefix}API_KEY"), os.environ.get(f"{prefix}API_SECRET")
        if key and secret:
            await probe(label, key, secret)
        else:
            print(f"[{label}] {prefix}API_KEY / {prefix}API_SECRET missing from .env")
    print("same key id?", os.environ.get("BYBIT_API_KEY") == os.environ.get("BYBIT_TRADE_API_KEY"))


asyncio.run(main())
