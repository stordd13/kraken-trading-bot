"""Replay contract (C2): the version stamp of *what the backtest engines simulate*.

C1 (``krakenbot.backtest_metrics``, ``metrics_version``) versions *how results are measured*;
this module versions *how the strategies are replayed* (``scripts/backtest.py``): which series
feed the indicators, when decisions and fills happen, which lazy indicators are pre-registered
and how the warmup is sized, how grid sells are matched to lots, and which rejections are
counted. Chantier C2 (post-audit B4, ``agent/chantier2_replay_v2.md``) changed all of that by
design, so results produced before and after are not comparable and must never be mixed in one
campaign file, walk-forward, report or resume.

Versions
--------
* absent — pre-C2 replay (every P6 / P7 / B4 / C1 file): grid decisions on 5-minute candles
  tagged 4h, incomplete lazy pre-registration, price-proximity sell matching, no rejection
  accounting.
* 2 — C2 replay: grid decisions on true 4h closes with 5-minute execution, effective-params
  pre-registration and candle-based warmup, lot matching by ``position_id`` validated before any
  balance mutation, ``rejections`` block per run / segment. (1 is deliberately unused so that
  "absent" and "1" can never be confused in a file.)

The key lives at the **top level** of a results entry, a ``--trades-out`` dump, a probe capture
and an equity sidecar — never inside ``BacktestMetrics.to_dict()`` (the gold-hashed metrics
contract of C1 is untouched). Pure module: no import of ``scripts/`` (rule B3), no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Contract version written by the C2 engines (``scripts/backtest.py``).
REPLAY_VERSION = 2


class ReplayVersionError(ValueError):
    """A results file mixes replay contracts, or was produced by a pre-C2 replay."""


def entry_replay_version(entry: Mapping[str, Any]) -> int | None:
    """``replay_version`` of a results entry / dump / capture (top level only; None = pre-C2)."""
    version = entry.get("replay_version")
    return None if version is None else int(version)


def require_replay_version(
    entries: Mapping[str, Mapping[str, Any]],
    expected: int = REPLAY_VERSION,
    *,
    path: str | None = None,
) -> None:
    """Every non-error entry must carry ``replay_version == expected``.

    Mixed or pre-C2 files are refused: two replay contracts simulate two different strategies
    and can never be aggregated, resumed or ranked together (same rule as ``metrics_version``,
    C1). Error entries (``"error" in entry``) are skipped like every other guard does.
    """
    for key, entry in entries.items():
        if "error" in entry:
            continue
        found = entry_replay_version(entry)
        if found != expected:
            where = f" in {path}" if path else ""
            shown = "<absent: pre-C2 file>" if found is None else str(found)
            raise ReplayVersionError(
                f"entry {key}{where} carries replay_version={shown} but {expected} is required: "
                "results of two replay contracts cannot be mixed (write to a fresh --output)"
            )
