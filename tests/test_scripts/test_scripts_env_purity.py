"""Importing a script must not mutate os.environ (B4.2 root fix of the .env leak).

Before B4.2, ``scripts/backtest.py`` and the P6/P7 runners called ``load_dotenv`` at import
time; pytest imports every test module at collection, so the developer's ``.env`` (real
``BYBIT_*`` keys) leaked into ``os.environ`` for the whole session and broke the credential
tests. A collection-time import cannot be observed from inside the same process once it has
happened, hence the subprocess: a fresh interpreter imports the module and prints the keys
that were added or changed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_PROBE = """
import importlib, json, os, sys
root = sys.argv[1]
sys.path[:0] = [root + "/scripts", root + "/src", root]
before = dict(os.environ)
importlib.import_module(sys.argv[2])
changed = sorted(k for k in os.environ if before.get(k) != os.environ[k])
print(json.dumps(changed))
"""

SCRIPTS = (
    "backtest",
    "run_p6_backtests",
    "run_p7_grid_search",
    "run_p6_walkforward",
    "binance_vision_import",
)


@pytest.mark.parametrize("module", SCRIPTS)
def test_import_does_not_mutate_environ(module: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, str(_PROJECT_ROOT), module],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    changed = json.loads(proc.stdout.strip().splitlines()[-1])
    assert changed == [], f"importing {module} mutated os.environ: {changed}"


#: Mirror of ``_EXCHANGE_CREDENTIAL_VARS`` in tests/conftest.py (the conftest module is not
#: importable from a test under pytest's default import mode).
_CREDENTIAL_VARS = (
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BYBIT_TRADE_API_KEY",
    "BYBIT_TRADE_API_SECRET",
    "KRAKEN_API_KEY",
    "KRAKEN_API_SECRET",
    "KRAKEN_FUTURES_API_KEY",
    "KRAKEN_FUTURES_API_SECRET",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
)


def test_conftest_purges_exchange_credentials() -> None:
    """The autouse fixture removes every exchange credential before each test."""
    present = [var for var in _CREDENTIAL_VARS if var in os.environ]
    assert present == []
