"""Inventaire de données — trous USDC 2022-2023, couverture par exchange, arithmétique d'amorçage.

Lecture seule de ``market_data_ohlc``, sans backtest, sans import, sans téléchargement. Le script
produit des **faits** (JSON + Markdown) et aucune recommandation : la décision fenêtre / univers /
comblement se prend ailleurs, sur cet inventaire.

Ce qu'il mesure (les cinq faits du brief)
------------------------------------------
1. **Couverture Binance** — ``exchange='binance'``, toute série présente (paire × intervalle) :
   premier / dernier stamp, count, attendu sur la grille, trous (> 1 intervalle) avec leur nombre
   de bougies manquantes et leur durée ; vue complète, puis zoom ``2022-01 → 2023-06``.
2. **Le trou USDC** — par paire et par timeframe : dernier stamp avant, premier stamp après,
   durée ; et si les timeframes décrivent le même événement (mêmes bornes à un intervalle près).
3. **Kraken et Bybit** — paires, timeframes, premier / dernier stamp, count, et rows estampillées
   dans ``(2022-01-01, 2024-01-01]``.
4. **Backfillable** — codes HTTP d'un ``HEAD`` sur les archives mensuelles 1 d de Binance Vision,
   six symboles × mois ``2022-08 → 2023-05``. Disponibilité seule : rien n'est téléchargé.
5. **Arithmétique d'amorçage** — par (paire, TF ∈ {5 m, 4 h, 1 j, 1 w}), chaque trou ≥ 2 bougies
   et, pour chacun, le début de fenêtre le plus précoce qui le suit tel que ``required`` bougies
   contiguës le précèdent, pour ``required ∈ {14, 50, 200}``.

Conventions fixées ici (et rapportées comme telles)
----------------------------------------------------
* **Estampilles en fin de période** (``timestamp = open + interval``, B4.1) ; PK
  ``(timestamp, pair, interval, exchange)`` : une row par stamp, les counts sont bruts.
* **Un trou** est un couple ``(dernier stamp présent, premier stamp suivant)`` détecté **côté SQL**
  par ``LAG(timestamp) OVER (PARTITION BY exchange, pair, interval ORDER BY timestamp)`` dès que
  l'écart dépasse un intervalle. Seuls les trous et les agrégats traversent le tunnel, jamais les
  rows. Bougies manquantes = ``(fin − début) / pas − 1`` ; ``None`` si l'écart n'est pas un
  multiple du pas (``on_grid = false``). **Durée** (``days``) = intervalle sans aucune bougie =
  ``fin − début − pas`` = ``manquantes × pas`` (la bougie stampée ``fin`` couvre
  ``(fin − pas, fin]``) ; l'écart brut ``fin − début`` est ``span_days``.
* **Le pas hebdomadaire est de 7 jours**, grille ancrée au lundi 00:00 UTC — ``WEEK_MINUTES``,
  ``expected_candles`` et ``longest_missing_run`` viennent de ``c3_common`` par import.
* **Attendu** d'une série = stamps de la grille dans ``[premier, dernier]`` (bornes comprises) ;
  le brief l'écrit ``(premier, dernier]``, ce qui compte un stamp de moins des deux côtés — la
  différence ``attendu − count`` est la même.
* **Borne d'observation** : toute requête est bornée par ``timestamp <= --now``. La table
  ``bybit`` croît en continu ; sans cette borne deux passages ne seraient jamais identiques.
* **Règle C2 d'amorçage** (``scripts/backtest.py``, ``_WARMUP_GAP_TOLERANCE = 1``) : ``loaded >=
  required``, ``stale_by_candles == 0``, ``largest_gap_candles <= 1``. Un trou d'**une** bougie ne
  casse donc pas un amorçage ; un trou de **deux** le casse. Le début admissible le plus précoce
  après un trou bloquant est ``S = premier stamp après le trou + (required − 1) × pas`` quand les
  ``required`` bougies qui suivent sont contiguës ; le calcul parcourt la grille réelle : un trou
  d'une bougie décale ``S`` d'un pas (il faut ``required`` bougies **chargées**), un trou de deux
  bougies ou plus renvoie au trou suivant, et ``None`` quand la série s'arrête avant.
* **Le trou USDC** d'une série est le trou de plus longue durée qui intersecte le zoom
  ``[2022-01-01, 2023-07-01)``. « Même événement » : les deux bornes du trou d'un timeframe sont à
  au plus **un pas de ce timeframe** des bornes du trou de la série la plus fine (1 min).
* Les seuils 14 / 50 / 200 sont des paramètres d'exploration, pas des exigences.

Usage::

    poetry run python scripts/audit/data_inventory.py \\
        --now 2026-09-22T21:00:00Z \\
        --output results/data_inventory_20260923/inventory.json \\
        --markdown results/data_inventory_20260923/inventory.md [--skip-vision]

Codes de sortie : 0 ok ; 2 usage ou base injoignable.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
import sys
from typing import Any
import urllib.error
import urllib.request

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import c3_common as c3  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
import rejeu_common as rc  # noqa: E402
from sqlalchemy import text  # noqa: E402

from krakenbot.config.settings import Settings  # noqa: E402
from krakenbot.core.database import DatabaseManager  # noqa: E402

# Réutilisés par import, jamais recopiés (brief) — épinglés par identité dans les tests.
WEEK_MINUTES = c3.WEEK_MINUTES
longest_missing_run = c3.longest_missing_run
expected_candles = c3.expected_candles

PROJECT_ROOT = _ROOT

EXCHANGE_BINANCE = "binance"
OTHER_EXCHANGES: tuple[str, ...] = ("kraken", "bybit")

#: Vue complète (fait 1) : « 2021-01 → 2026-04 ».
FULL_VIEW_START = datetime(2021, 1, 1, tzinfo=UTC)
FULL_VIEW_END = datetime(2026, 5, 1, tzinfo=UTC)
#: Zoom (faits 1 et 2) : « 2022-01 → 2023-06 », soit ``[2022-01-01, 2023-07-01)``.
ZOOM_START = datetime(2022, 1, 1, tzinfo=UTC)
ZOOM_END = datetime(2023, 7, 1, tzinfo=UTC)
#: Fait 3 : rows estampillées dans ``(2022-01-01, 2024-01-01]`` (bougies closes en 2022 ou 2023).
WINDOW_2022_2023_START = datetime(2022, 1, 1, tzinfo=UTC)
WINDOW_2022_2023_END = datetime(2024, 1, 1, tzinfo=UTC)

#: Fait 5 : les quatre timeframes explorés et les trois niveaux de ``required``.
WARMUP_INTERVALS: tuple[int, ...] = (5, 240, 1440, WEEK_MINUTES)
REQUIRED_LEVELS: tuple[int, ...] = (14, 50, 200)
#: Règle C2 (``scripts/backtest.py`` ``_WARMUP_GAP_TOLERANCE``) : un trou d'une bougie ne casse pas.
WARMUP_GAP_TOLERANCE = 1

#: Fait 3 : ``XBT`` est le code Kraken du bitcoin (``src/krakenbot/connectors/kraken/rest.py``,
#: table ``"XBT/USDC": "BTC/USDC"``). Les paires sont rapportées telles quelles.
BASE_ALIASES: Mapping[str, tuple[str, ...]] = {
    "BTC": ("BTC", "XBT"),
    "ETH": ("ETH",),
    "SOL": ("SOL",),
}
QUOTE = "USDC"

#: Fait 4 : Binance Vision, archives mensuelles 1 d.
VISION_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/{symbol}/1d/{symbol}-1d-{month}.zip"
)
VISION_SYMBOLS: tuple[str, ...] = ("BTCUSDC", "ETHUSDC", "SOLUSDC", "BTCUSDT", "ETHUSDT", "SOLUSDT")
VISION_MONTHS: tuple[str, ...] = (
    "2022-08",
    "2022-09",
    "2022-10",
    "2022-11",
    "2022-12",
    "2023-01",
    "2023-02",
    "2023-03",
    "2023-04",
    "2023-05",
)
VISION_TIMEOUT_S = 20.0

_DAYS_DIGITS = 6
_TF_LABELS: Mapping[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
    WEEK_MINUTES: "1w",
}


# ---------------------------------------------------------------------------
# Couche pure — grille, trous, comptes
# ---------------------------------------------------------------------------


def _as_utc(stamp: datetime) -> datetime:
    """Image UTC d'un stamp ; un datetime naïf est un défaut, jamais supposé UTC."""
    if stamp.tzinfo is None:
        raise ValueError(f"naive timestamp {stamp!r}: every stamp must be tz-aware UTC")
    return stamp.astimezone(UTC)


def tf_label(interval: int) -> str:
    return _TF_LABELS.get(int(interval), f"{int(interval)}min")


def step_of(interval: int) -> timedelta:
    """Le pas de la série : 7 jours pour l'hebdomadaire, ``interval`` minutes sinon."""
    return timedelta(days=7) if interval == WEEK_MINUTES else timedelta(minutes=interval)


def is_on_grid(stamp: datetime, interval: int) -> bool:
    """Le stamp est une estampille de la série (lundi 00:00 UTC pour 1 w)."""
    stamp = _as_utc(stamp)
    return c3.last_stamp_at_or_before(stamp, interval) == stamp


def holes_from_stamps(stamps: Sequence[datetime], interval: int) -> list[tuple[datetime, datetime]]:
    """Image Python du ``LAG`` SQL : couples consécutifs dont l'écart dépasse un pas."""
    ordered = sorted(_as_utc(s) for s in stamps)
    step = step_of(interval)
    return [(a, b) for a, b in zip(ordered, ordered[1:], strict=False) if b - a > step]


def describe_hole(prev: datetime, following: datetime, interval: int) -> dict[str, Any]:
    """Un trou : bornes, bougies manquantes, durée en jours, appartenance à la grille."""
    prev, following = _as_utc(prev), _as_utc(following)
    if following <= prev:
        raise ValueError(f"hole bounds inverted: {prev.isoformat()} .. {following.isoformat()}")
    step = step_of(interval)
    delta = following - prev
    exact = delta % step == timedelta(0)
    missing = (delta // step) - 1 if exact else None
    on_grid = exact and is_on_grid(prev, interval) and is_on_grid(following, interval)
    # Fin de période : la bougie stampée ``following`` couvre ``(following − pas, following]``,
    # donc l'intervalle sans aucune bougie est ``(prev, following − pas]`` — ``missing × pas``.
    absent = delta - step
    return {
        "start": prev,
        "end": following,
        "interval": int(interval),
        "missing": missing,
        "days": round(absent.total_seconds() / 86400.0, _DAYS_DIGITS),
        "span_days": round(delta.total_seconds() / 86400.0, _DAYS_DIGITS),
        "on_grid": on_grid,
    }


def is_blocking(hole: Mapping[str, Any]) -> bool:
    """Casse un amorçage au sens C2 : plus d'une bougie manquante, ou un écart non mesurable."""
    missing = hole["missing"]
    return missing is None or int(missing) > WARMUP_GAP_TOLERANCE


def missing_stamps_of(holes: Sequence[Mapping[str, Any]], interval: int) -> list[datetime]:
    """Toutes les estampilles manquantes des trous mesurables, énumérées sur la grille."""
    step = step_of(interval)
    out: list[datetime] = []
    for hole in holes:
        if hole["missing"] is None:
            continue
        out.extend(hole["start"] + j * step for j in range(1, int(hole["missing"]) + 1))
    return out


def grid_count_closed(first: datetime, last: datetime, interval: int) -> int:
    """Stamps de la grille dans ``[first, last]`` : ``expected_candles`` compte ``(first, last]``,
    plus ``first`` lui-même s'il est sur la grille."""
    first, last = _as_utc(first), _as_utc(last)
    if last < first:
        return 0
    return expected_candles(first, last, interval) + (1 if is_on_grid(first, interval) else 0)


def missing_in(holes: Sequence[Mapping[str, Any]], a: datetime, b: datetime, interval: int) -> int:
    """Estampilles manquantes des trous mesurables qui tombent dans ``[a, b]``."""
    step = step_of(interval)
    a, b = _as_utc(a), _as_utc(b)
    total = 0
    for hole in holes:
        if hole["missing"] is None:
            continue
        k = int(hole["missing"])
        j_min = max(1, math.ceil((a - hole["start"]) / step))
        j_max = min(k, math.floor((b - hole["start"]) / step))
        total += max(0, j_max - j_min + 1)
    return total


def series_summary(
    *,
    first: datetime | None,
    last: datetime | None,
    count: int,
    holes: Sequence[Mapping[str, Any]],
    interval: int,
) -> dict[str, Any]:
    """Attendu, manquantes et comptes de trous d'une série à partir de ses trous."""
    if first is None or last is None:
        return {
            "expected": 0,
            "missing": 0,
            "holes_1": 0,
            "holes_ge2": 0,
            "holes_unmeasurable": 0,
            "holes_missing_sum": 0,
            "largest_missing_run": 0,
            "first_on_grid": None,
            "last_on_grid": None,
        }
    expected = grid_count_closed(first, last, interval)
    measurable = [h for h in holes if h["missing"] is not None]
    absent = missing_stamps_of(holes, interval)
    return {
        "expected": expected,
        "missing": expected - int(count),
        "holes_1": sum(1 for h in measurable if int(h["missing"]) == 1),
        "holes_ge2": sum(1 for h in measurable if int(h["missing"]) >= 2),
        "holes_unmeasurable": len(holes) - len(measurable),
        "holes_missing_sum": sum(int(h["missing"]) for h in measurable),
        "largest_missing_run": longest_missing_run(absent, interval) if absent else 0,
        "first_on_grid": is_on_grid(first, interval),
        "last_on_grid": is_on_grid(last, interval),
    }


def admissible_starts(
    holes: Sequence[Mapping[str, Any]],
    *,
    first: datetime | None,
    last: datetime | None,
    interval: int,
) -> list[dict[str, datetime | None]]:
    """Pour chaque trou, le début de fenêtre le plus précoce qui le suit avec ``required`` bougies
    chargées, contiguës au sens C2 (trou d'une bougie toléré), par niveau de ``required``.

    Parcourt les segments de stamps présents ``[first, h0.start], [h0.end, h1.start], …,
    [hn.end, last]`` : un trou d'une bougie ne remet pas le compte à zéro (il coûte un pas), un
    trou bloquant renvoie à sa propre réponse, la fin de série donne ``None``.
    """
    if not holes:
        return []
    if first is None or last is None:
        raise ValueError("first/last are required when holes exist")
    step = step_of(interval)
    bounds: list[datetime] = [_as_utc(first)]
    for hole in holes:
        bounds.extend((hole["start"], hole["end"]))
    bounds.append(_as_utc(last))
    segments = [(bounds[i], bounds[i + 1]) for i in range(0, len(bounds), 2)]
    memo: list[dict[str, datetime | None]] = [{} for _ in holes]

    def start_after(index: int, required: int) -> datetime | None:
        if holes[index]["missing"] is None:
            return None
        loaded = 0
        j = index + 1
        while True:
            a, b = segments[j]
            n = grid_count_closed(a, b, interval)
            if loaded + n >= required:
                return a + (required - loaded - 1) * step
            loaded += n
            if j >= len(holes):
                return None
            if is_blocking(holes[j]):
                return memo[j][str(required)]
            j += 1

    for index in range(len(holes) - 1, -1, -1):
        memo[index] = {str(r): start_after(index, r) for r in REQUIRED_LEVELS}
    return memo


def usdc_hole(
    holes: Sequence[Mapping[str, Any]], zoom_start: datetime, zoom_end: datetime
) -> Mapping[str, Any] | None:
    """Le trou de plus longue durée qui intersecte ``[zoom_start, zoom_end)`` ; le plus précoce à
    durée égale ; ``None`` s'il n'y en a pas."""
    candidates = [h for h in holes if h["start"] < zoom_end and h["end"] > zoom_start]
    if not candidates:
        return None
    return sorted(candidates, key=lambda h: (-float(h["days"]), h["start"]))[0]


def same_event(
    hole: Mapping[str, Any], reference: Mapping[str, Any], interval: int
) -> dict[str, Any]:
    """Les deux bornes du trou sont-elles à au plus un pas de ``interval`` de celles du trou de
    référence (la série la plus fine) ?"""
    minute = timedelta(minutes=1)
    tolerance = int(step_of(interval) / minute)
    before = int((hole["start"] - reference["start"]) / minute)
    after = int((hole["end"] - reference["end"]) / minute)
    return {
        "delta_before_minutes": before,
        "delta_after_minutes": after,
        "tolerance_minutes": tolerance,
        "same_event": abs(before) <= tolerance and abs(after) <= tolerance,
    }


# ---------------------------------------------------------------------------
# Artefact — pur, l'horloge est injectée
# ---------------------------------------------------------------------------


def _iso(stamp: datetime | None) -> str | None:
    return None if stamp is None else _as_utc(stamp).isoformat()


def _hole_json(hole: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "start": _iso(hole["start"]),
        "end": _iso(hole["end"]),
        "missing": hole["missing"],
        "days": hole["days"],
        "span_days": hole["span_days"],
        "on_grid": hole["on_grid"],
    }


def _in_zoom(hole: Mapping[str, Any]) -> bool:
    return bool(hole["start"] < ZOOM_END and hole["end"] > ZOOM_START)


def _split_pair(pair: str) -> tuple[str, str]:
    base, _, quote = pair.partition("/")
    return base, quote


def _fact1(series: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in series:
        if row["exchange"] != EXCHANGE_BINANCE:
            continue
        interval = int(row["interval"])
        holes = [describe_hole(a, b, interval) for a, b in row["holes"]]
        summary = series_summary(
            first=row["first"],
            last=row["last"],
            count=int(row["count"]),
            holes=holes,
            interval=interval,
        )
        out.setdefault(row["pair"], {})[str(interval)] = {
            "first": _iso(row["first"]),
            "last": _iso(row["last"]),
            "count": int(row["count"]),
            **summary,
            "holes": [_hole_json(h) for h in holes],
            "holes_in_zoom": [_hole_json(h) for h in holes if _in_zoom(h)],
        }
    return out


def _holes_of(series: Sequence[Mapping[str, Any]]) -> dict[str, dict[int, list[dict[str, Any]]]]:
    """Trous décrits, par paire et intervalle, pour ``exchange='binance'``."""
    out: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for row in series:
        if row["exchange"] != EXCHANGE_BINANCE:
            continue
        interval = int(row["interval"])
        out.setdefault(row["pair"], {})[interval] = [
            describe_hole(a, b, interval) for a, b in row["holes"]
        ]
    return out


def _fact2(series: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair, by_interval in _holes_of(series).items():
        finest = min(by_interval)
        reference = usdc_hole(by_interval[finest], ZOOM_START, ZOOM_END)
        per_interval: dict[str, Any] = {}
        for interval in sorted(by_interval):
            hole = usdc_hole(by_interval[interval], ZOOM_START, ZOOM_END)
            if hole is None:
                per_interval[str(interval)] = None
                continue
            entry = {
                "last_before": _iso(hole["start"]),
                "first_after": _iso(hole["end"]),
                "days": hole["days"],
                "missing": hole["missing"],
            }
            if reference is not None:
                entry.update(same_event(hole, reference, interval))
            per_interval[str(interval)] = entry
        verdicts = [
            v["same_event"] for v in per_interval.values() if v is not None and "same_event" in v
        ]
        out[pair] = {
            "reference_interval": finest,
            "per_interval": per_interval,
            "intervals_with_hole": sum(1 for v in per_interval.values() if v is not None),
            "intervals_same_event": sum(1 for v in verdicts if v),
            "all_same_event": bool(verdicts) and all(verdicts),
        }
    return out


def _fact3(series: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    exchanges: dict[str, list[dict[str, Any]]] = {name: [] for name in OTHER_EXCHANGES}
    for row in series:
        if row["exchange"] not in exchanges:
            continue
        exchanges[row["exchange"]].append(
            {
                "pair": row["pair"],
                "interval": int(row["interval"]),
                "first": _iso(row["first"]),
                "last": _iso(row["last"]),
                "count": int(row["count"]),
                "count_in_window": int(row["count_2022_2023"]),
                "first_in_window": _iso(row["first_2022_2023"]),
                "last_in_window": _iso(row["last_2022_2023"]),
            }
        )
    constat: dict[str, Any] = {}
    for name, rows in exchanges.items():
        rows.sort(key=lambda r: (r["pair"], r["interval"]))
        with_rows = [r for r in rows if r["count_in_window"] > 0]
        coverage: dict[str, list[str]] = {}
        for base, aliases in BASE_ALIASES.items():
            matching = sorted(
                {
                    (r["pair"], r["interval"])
                    for r in with_rows
                    if _split_pair(r["pair"])[0] in aliases and _split_pair(r["pair"])[1] == QUOTE
                }
            )
            coverage[f"{base}/{QUOTE}"] = [f"{pair} {tf_label(iv)}" for pair, iv in matching]
        constat[name] = {
            "series_total": len(rows),
            "series_with_rows_in_window": len(with_rows),
            "pairs_with_rows_in_window": sorted({r["pair"] for r in with_rows}),
            "coverage_2022_2023": coverage,
        }
    return {
        "window": {"start": _iso(WINDOW_2022_2023_START), "end": _iso(WINDOW_2022_2023_END)},
        "exchanges": exchanges,
        "constat": constat,
        "note": (
            "XBT est le code Kraken du bitcoin (src/krakenbot/connectors/kraken/rest.py, "
            "table XBT/USDC -> BTC/USDC) ; les paires sont rapportées telles quelles."
        ),
    }


def _fact5(series: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    firsts = {
        (row["pair"], int(row["interval"])): (row["first"], row["last"])
        for row in series
        if row["exchange"] == EXCHANGE_BINANCE
    }
    out: dict[str, Any] = {}
    for pair, by_interval in _holes_of(series).items():
        for interval in WARMUP_INTERVALS:
            if interval not in by_interval:
                continue
            holes = by_interval[interval]
            first, last = firsts[(pair, interval)]
            starts = admissible_starts(holes, first=first, last=last, interval=interval)
            reference = usdc_hole(holes, ZOOM_START, ZOOM_END)
            entries = []
            usdc_entry = None
            for hole, start in zip(holes, starts, strict=True):
                if not is_blocking(hole):
                    continue
                entry = {
                    **_hole_json(hole),
                    "admissible_start": {k: _iso(v) for k, v in start.items()},
                }
                entries.append(entry)
                if hole is reference:
                    usdc_entry = entry
            out.setdefault(pair, {})[str(interval)] = {
                "blocking_holes": entries,
                "usdc_hole": usdc_entry,
            }
    return out


def build_artifact(
    series: Sequence[Mapping[str, Any]],
    *,
    generated_at: datetime,
    vision: Mapping[str, Any] | None,
    session_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """L'artefact ``inventory.json``. Pur : horloge, rows et sondes HTTP sont injectées."""
    now = _as_utc(generated_at)
    return {
        "generated_at": now.isoformat(),
        "observation_bound": now.isoformat(),
        "db_session": dict(session_info) if session_info else None,
        "conventions": {
            "stamp": "fin de période (timestamp = open + interval), PK (timestamp, pair, interval, exchange)",
            "hole": (
                "LAG SQL ; bougies manquantes = (fin - début) / pas - 1 (None si hors grille) ; "
                "days = fin - début - pas (intervalle sans bougie) ; span_days = fin - début"
            ),
            "weekly": "pas de 7 jours, grille ancrée au lundi 00:00 UTC (c3_common.WEEK_MINUTES)",
            "expected": "stamps de la grille dans [premier, dernier] (c3_common.expected_candles + 1)",
            "observation_bound": "toute requête bornée par timestamp <= generated_at",
            "warmup_rule": (
                "C2 : loaded >= required, stale_by_candles == 0, largest_gap_candles <= "
                f"{WARMUP_GAP_TOLERANCE} ; S = premier stamp après le trou + (required - 1) x pas "
                "sur grille réelle (trou d'une bougie toléré, trou >= 2 renvoie au suivant)"
            ),
            "usdc_hole": "trou de plus longue durée intersectant le zoom [2022-01-01, 2023-07-01)",
            "same_event": "les deux bornes à au plus un pas du timeframe des bornes de la série 1 min",
            "required_levels": list(REQUIRED_LEVELS),
        },
        "views": {
            "full": {"start": _iso(FULL_VIEW_START), "end": _iso(FULL_VIEW_END)},
            "zoom": {"start": _iso(ZOOM_START), "end": _iso(ZOOM_END)},
        },
        "fact1_binance": _fact1(series),
        "fact2_usdc_hole": _fact2(series),
        "fact3_other_exchanges": _fact3(series),
        "fact4_vision": {
            "url_template": VISION_URL,
            "symbols": list(VISION_SYMBOLS),
            "months": list(VISION_MONTHS),
            "skipped": vision is None,
            "status": dict(vision["status"]) if vision is not None else None,
        },
        "fact5_warmup": _fact5(series),
    }


# ---------------------------------------------------------------------------
# Recoupement contre le bloc ``warmup.train`` du rejeu (validation, stdout seulement)
# ---------------------------------------------------------------------------


def reconcile_rejeu(
    series: Sequence[Mapping[str, Any]], train: Mapping[str, Any], pair: str
) -> list[dict[str, Any]]:
    """Recalcule ``loaded`` et ``largest_gap_candles`` de chaque timeframe du bloc depuis les trous
    mesurés : présents dans ``[first, last]`` = grille − manquantes ; plus grand trou inclus."""
    holes_by_interval = _holes_of(series).get(pair, {})
    out: list[dict[str, Any]] = []
    for tf, block in sorted(train.items(), key=lambda kv: int(kv[1]["interval"])):
        interval = int(block["interval"])
        first_s, last_s = block.get("first"), block.get("last")
        entry: dict[str, Any] = {
            "tf": tf,
            "interval": interval,
            "declared_loaded": block.get("loaded"),
            "declared_largest_gap": block.get("largest_gap_candles"),
            "first": first_s,
            "last": last_s,
        }
        if first_s is None or last_s is None or interval not in holes_by_interval:
            entry.update({"recomputed_loaded": None, "recomputed_largest_gap": None})
            out.append(entry)
            continue
        first = c3.parse_datetime(first_s, where=f"{tf}.first")
        last = c3.parse_datetime(last_s, where=f"{tf}.last")
        holes = holes_by_interval[interval]
        inside = [h for h in holes if h["start"] >= first and h["end"] <= last]
        entry["recomputed_loaded"] = grid_count_closed(first, last, interval) - missing_in(
            holes, first, last, interval
        )
        entry["recomputed_largest_gap"] = max(
            (int(h["missing"]) for h in inside if h["missing"] is not None), default=0
        )
        entry["holes_inside"] = [_hole_json(h) for h in inside]
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Rendu Markdown
# ---------------------------------------------------------------------------


def _fmt_days(value: float | None) -> str:
    return "—" if value is None else f"{float(value):.2f}"


def _fmt(value: Any) -> str:
    return "—" if value is None else str(value)


def _iso_short(value: str | None) -> str:
    if value is None:
        return "—"
    return value.replace("+00:00", "Z")


def _fact1_md(artifact: Mapping[str, Any]) -> list[str]:
    fact1 = artifact["fact1_binance"]
    views = artifact["views"]
    lines = [
        "## 1. Couverture Binance",
        "",
        f"`exchange='binance'`, vue complète `{_iso_short(views['full']['start'])} → "
        f"{_iso_short(views['full']['end'])}`, puis zoom `{_iso_short(views['zoom']['start'])} → "
        f"{_iso_short(views['zoom']['end'])}`. Attendu = stamps de la grille dans "
        "`[premier, dernier]` ; manquantes = attendu − count ; un trou = écart > 1 intervalle "
        "entre deux stamps présents ; durée = intervalle sans aucune bougie = fin − début − pas "
        "= manquantes × pas.",
        "",
        "### 1.1 Séries présentes",
        "",
        "| Paire | TF | Premier | Dernier | Count | Attendu | Manquantes | Trous 1 bougie | "
        "Trous ≥ 2 | Plus long run manquant |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for pair in sorted(fact1):
        for interval_key in sorted(fact1[pair], key=int):
            s = fact1[pair][interval_key]
            lines.append(
                f"| {pair} | {tf_label(int(interval_key))} | {_iso_short(s['first'])} | "
                f"{_iso_short(s['last'])} | {s['count']} | {s['expected']} | {s['missing']} | "
                f"{s['holes_1']} | {s['holes_ge2']} | {s['largest_missing_run']} |"
            )
    for title, key in (
        ("### 1.2 Trous > 1 intervalle — vue complète", "holes"),
        ("### 1.3 Trous > 1 intervalle — zoom 2022-01 → 2023-06", "holes_in_zoom"),
    ):
        lines += [
            "",
            title,
            "",
            "| Paire | TF | Début (dernier présent) | Fin (premier suivant) | Manquantes | "
            "Durée (j) | Sur grille |",
            "|---|---|---|---|---|---|---|",
        ]
        count = 0
        for pair in sorted(fact1):
            for interval_key in sorted(fact1[pair], key=int):
                for hole in fact1[pair][interval_key][key]:
                    count += 1
                    lines.append(
                        f"| {pair} | {tf_label(int(interval_key))} | {_iso_short(hole['start'])} | "
                        f"{_iso_short(hole['end'])} | {_fmt(hole['missing'])} | "
                        f"{_fmt_days(hole['days'])} | {'oui' if hole['on_grid'] else 'non'} |"
                    )
        if count == 0:
            lines.append("| — | — | — | — | — | — | — |")
    return lines


def _fact2_md(artifact: Mapping[str, Any]) -> list[str]:
    fact2 = artifact["fact2_usdc_hole"]
    lines = [
        "## 2. Le trou USDC",
        "",
        "Par série, le trou de plus longue durée qui intersecte le zoom. Référence : la série la "
        "plus fine (1 min). « Même événement » : les deux bornes à au plus un pas du timeframe "
        "des bornes de la référence.",
        "",
        "| Paire | TF | Dernier stamp avant | Premier stamp après | Durée (j) | Manquantes | "
        "Δ début vs réf. (min) | Δ fin vs réf. (min) | Tolérance (min) | Même événement |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for pair in sorted(fact2):
        block = fact2[pair]
        for interval_key in sorted(block["per_interval"], key=int):
            entry = block["per_interval"][interval_key]
            label = tf_label(int(interval_key))
            if entry is None:
                lines.append(f"| {pair} | {label} | — | — | — | — | — | — | — | aucun trou |")
                continue
            verdict = (
                "—" if "same_event" not in entry else ("oui" if entry["same_event"] else "non")
            )
            lines.append(
                f"| {pair} | {label} | {_iso_short(entry['last_before'])} | "
                f"{_iso_short(entry['first_after'])} | {_fmt_days(entry['days'])} | "
                f"{_fmt(entry['missing'])} | {_fmt(entry.get('delta_before_minutes'))} | "
                f"{_fmt(entry.get('delta_after_minutes'))} | "
                f"{_fmt(entry.get('tolerance_minutes'))} | {verdict} |"
            )
    lines += ["", "Constat par paire :", ""]
    for pair in sorted(fact2):
        block = fact2[pair]
        n_hole, n_same = block["intervals_with_hole"], block["intervals_same_event"]
        ref = tf_label(int(block["reference_interval"]))
        if n_hole == 0:
            lines.append(f"- **{pair}** : aucun trou dans le zoom, sur aucun timeframe.")
            continue
        off = [
            tf_label(int(k))
            for k, v in block["per_interval"].items()
            if v is not None and "same_event" in v and not v["same_event"]
        ]
        if block["all_same_event"]:
            lines.append(
                f"- **{pair}** : les {n_hole} timeframes décrivent le même événement "
                f"(bornes à un intervalle près de la série {ref})."
            )
        else:
            lines.append(
                f"- **{pair}** : {n_same}/{n_hole} timeframes décrivent le même événement que "
                f"la série {ref} ; hors tolérance : {', '.join(off) if off else '—'}."
            )
    return lines


def _fact3_md(artifact: Mapping[str, Any]) -> list[str]:
    fact3 = artifact["fact3_other_exchanges"]
    window = fact3["window"]
    win = f"({_iso_short(window['start'])}, {_iso_short(window['end'])}]"
    lines = [
        "## 3. Kraken et Bybit",
        "",
        f"Par `exchange ∈ {{kraken, bybit}}`, toute série présente ; « fenêtre » = rows "
        f"estampillées dans `{win}`.",
        "",
        "| Exchange | Paire | TF | Premier | Dernier | Count | Rows dans la fenêtre | "
        "Premier dans la fenêtre | Dernier dans la fenêtre |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name in OTHER_EXCHANGES:
        for row in fact3["exchanges"].get(name, []):
            lines.append(
                f"| {name} | {row['pair']} | {tf_label(row['interval'])} | "
                f"{_iso_short(row['first'])} | {_iso_short(row['last'])} | {row['count']} | "
                f"{row['count_in_window']} | {_iso_short(row['first_in_window'])} | "
                f"{_iso_short(row['last_in_window'])} |"
            )
    lines += [
        "",
        "Constat (mesuré) — rows dans la fenêtre 2022-2023 sur BTC/ETH/SOL contre USDC :",
        "",
    ]
    for name in OTHER_EXCHANGES:
        c = fact3["constat"][name]
        parts = []
        for target, matches in c["coverage_2022_2023"].items():
            parts.append(f"{target} : {', '.join(matches) if matches else 'aucune row'}")
        lines.append(
            f"- **{name}** : {c['series_with_rows_in_window']}/{c['series_total']} séries ont des "
            f"rows dans la fenêtre (paires : "
            f"{', '.join(c['pairs_with_rows_in_window']) if c['pairs_with_rows_in_window'] else 'aucune'}) "
            f"— {' ; '.join(parts)}."
        )
    lines += ["", f"Note : {fact3['note']}"]
    return lines


def _fact4_md(artifact: Mapping[str, Any]) -> list[str]:
    fact4 = artifact["fact4_vision"]
    lines = [
        "## 4. Backfillable (Binance Vision, `HEAD` seulement)",
        "",
        f"`HEAD` sur `{fact4['url_template']}` — codes HTTP tels quels. Disponibilité seule : rien "
        "n'est téléchargé, rien n'est lu sur les prix.",
        "",
    ]
    if fact4["skipped"]:
        lines.append("Sondes HTTP **non exécutées** (`--skip-vision`).")
        return lines
    months = fact4["months"]
    lines += [
        "| Symbole | " + " | ".join(months) + " |",
        "|---|" + "---|" * len(months),
    ]
    for symbol in fact4["symbols"]:
        row = fact4["status"][symbol]
        lines.append(f"| {symbol} | " + " | ".join(str(row[m]) for m in months) + " |")
    return lines


def _fact5_md(artifact: Mapping[str, Any]) -> list[str]:
    fact5 = artifact["fact5_warmup"]
    levels = [str(r) for r in REQUIRED_LEVELS]
    lines = [
        "## 5. Arithmétique d'amorçage",
        "",
        "Par (paire, TF ∈ {5 m, 4 h, 1 j, 1 w}) : chaque trou ≥ 2 bougies manquantes sur toute la "
        "série et, pour chacun, le début de fenêtre le plus précoce qui le suit tel que `required` "
        "bougies chargées le précèdent (règle C2 : `loaded ≥ required`, `stale_by_candles = 0`, "
        "`largest_gap_candles ≤ 1` — un trou d'une seule bougie ne casse pas). "
        "`S = premier stamp après le trou + (required − 1) × pas` sur la grille réelle : un trou "
        "d'une bougie dans les `required` suivantes décale `S` d'un pas, un trou ≥ 2 renvoie au "
        "trou suivant, `None` si la série s'arrête avant. Dérivé du calcul, aucune date choisie à la "
        "main.",
        "",
        "| Paire | TF | Trou (dernier présent → premier suivant) | Manquantes | "
        + " | ".join(f"S ({r})" for r in levels)
        + " |",
        "|---|---|---|---|" + "---|" * len(levels),
    ]
    for pair in sorted(fact5):
        for interval_key in sorted(fact5[pair], key=int):
            block = fact5[pair][interval_key]
            label = tf_label(int(interval_key))
            if not block["blocking_holes"]:
                lines.append(
                    f"| {pair} | {label} | aucun trou ≥ 2 bougies | — |" + " — |" * len(levels)
                )
            for hole in block["blocking_holes"]:
                cells = " | ".join(_iso_short(hole["admissible_start"][r]) for r in levels)
                lines.append(
                    f"| {pair} | {label} | {_iso_short(hole['start'])} → {_iso_short(hole['end'])} | "
                    f"{_fmt(hole['missing'])} | {cells} |"
                )
    lines += [
        "",
        "Début admissible après le trou USDC (fait 2), par (paire, TF), pour 14 / 50 / 200 :",
        "",
    ]
    for pair in sorted(fact5):
        for interval_key in sorted(fact5[pair], key=int):
            block = fact5[pair][interval_key]
            label = tf_label(int(interval_key))
            hole = block["usdc_hole"]
            if hole is None:
                lines.append(f"- **{pair} {label}** : aucun trou ≥ 2 bougies dans le zoom.")
                continue
            values = " / ".join(_iso_short(hole["admissible_start"][r]) for r in levels)
            lines.append(
                f"- **{pair} {label}** — trou {_iso_short(hole['start'])} → "
                f"{_iso_short(hole['end'])} ({_fmt(hole['missing'])} bougies) : {values}."
            )
    return lines


def render_markdown(artifact: Mapping[str, Any], *, json_sha256: str, json_name: str) -> str:
    session = artifact.get("db_session") or {}
    lines = [
        "# Inventaire de données — trous USDC 2022-2023, couverture par exchange, "
        "arithmétique d'amorçage",
        "",
        f"Généré le {artifact['generated_at']} · borne d'observation "
        f"`timestamp <= {artifact['observation_bound']}` · lecture seule "
        f"(`transaction_read_only = {session.get('transaction_read_only', '?')}`, "
        f"`statement_timeout = {session.get('statement_timeout', '?')}`) · "
        f"`{json_name}` sha256 `{json_sha256}`",
        "",
        "Conventions : estampilles en fin de période (`timestamp = open + interval`) ; trous "
        "détectés côté SQL par `LAG` ; bougies manquantes = (fin − début) / pas − 1 ; pas "
        "hebdomadaire de 7 jours ancré au lundi 00:00 UTC ; attendu = stamps de la grille dans "
        "`[premier, dernier]` ; toute requête bornée par `timestamp <= borne d'observation`. "
        "Ce document produit des faits, aucune recommandation.",
        "",
    ]
    lines += _fact1_md(artifact)
    lines.append("")
    lines += _fact2_md(artifact)
    lines.append("")
    lines += _fact3_md(artifact)
    lines.append("")
    lines += _fact4_md(artifact)
    lines.append("")
    lines += _fact5_md(artifact)
    lines += [
        "",
        "## Ce que ce document ne dit pas",
        "",
        "- Aucune recommandation de fenêtre, d'univers ou de source de données : les tableaux "
        "décrivent ce qui est en base et ce qui répond à un `HEAD`, rien de plus.",
        "- Aucune interprétation du protocole C3 (`docs/protocole_c3.md`) : la règle C2 citée au "
        "fait 5 est celle du moteur (`scripts/backtest.py`), reproduite pour le calcul, pas lue "
        "comme une clause d'admissibilité.",
        "- Les seuils 14 / 50 / 200 sont des paramètres d'exploration, pas des exigences.",
        "- Le fait 4 ne dit rien de la pertinence d'un proxy USDT : c'est une décision, pas une "
        "donnée.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Couche réseau — HEAD Binance Vision (fait 4)
# ---------------------------------------------------------------------------


def vision_head(symbol: str, month: str, *, timeout: float = VISION_TIMEOUT_S) -> int | str:
    """Code HTTP du ``HEAD`` (entier), ou ``"ERR:<Exception>"`` si la requête n'aboutit pas."""
    url = VISION_URL.format(symbol=symbol, month=month)
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"ERR:{type(exc).__name__}"


def probe_vision() -> dict[str, Any]:
    status = {
        symbol: {month: vision_head(symbol, month) for month in VISION_MONTHS}
        for symbol in VISION_SYMBOLS
    }
    return {"status": status}


# ---------------------------------------------------------------------------
# Couche DB — agrégats et trous, jamais les rows
# ---------------------------------------------------------------------------

SUMMARY_SQL = text(
    """
    SELECT exchange, pair, interval AS iv, COUNT(*) AS n,
           MIN(timestamp) AS first_stamp, MAX(timestamp) AS last_stamp,
           COUNT(*) FILTER (WHERE timestamp > :w_start AND timestamp <= :w_end) AS n_w,
           MIN(timestamp) FILTER (WHERE timestamp > :w_start AND timestamp <= :w_end) AS first_w,
           MAX(timestamp) FILTER (WHERE timestamp > :w_start AND timestamp <= :w_end) AS last_w
    FROM market_data_ohlc
    WHERE timestamp <= :now
    GROUP BY exchange, pair, interval
    ORDER BY exchange, pair, interval
    """
)

HOLES_SQL = text(
    """
    WITH s AS (
        SELECT pair, interval AS iv, timestamp,
               LAG(timestamp) OVER (PARTITION BY exchange, pair, interval ORDER BY timestamp) AS prev
        FROM market_data_ohlc
        WHERE exchange = :exchange AND timestamp <= :now
    )
    SELECT pair, iv, prev, timestamp AS following
    FROM s
    WHERE prev IS NOT NULL AND timestamp - prev > make_interval(mins => iv)
    ORDER BY pair, iv, prev
    """
)


async def collect(now: datetime) -> dict[str, Any]:
    """Le seul endroit qui touche la base : session en lecture seule, agrégats + trous."""
    settings = Settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    try:
        async with db_manager.read_session() as session:
            await session.execute(text("SET transaction_read_only = on"))
            await session.execute(text("SET default_transaction_read_only = on"))
            await session.execute(text("SET statement_timeout = '300s'"))
            read_only = (await session.execute(text("SHOW transaction_read_only"))).scalar_one()
            timeout = (await session.execute(text("SHOW statement_timeout"))).scalar_one()
            summary = (
                await session.execute(
                    SUMMARY_SQL,
                    {"now": now, "w_start": WINDOW_2022_2023_START, "w_end": WINDOW_2022_2023_END},
                )
            ).all()
            holes = (
                await session.execute(HOLES_SQL, {"exchange": EXCHANGE_BINANCE, "now": now})
            ).all()
    finally:
        await db_manager.close_db()

    holes_by_series: dict[tuple[str, int], list[tuple[datetime, datetime]]] = {}
    for pair, iv, prev, following in holes:
        holes_by_series.setdefault((pair, int(iv)), []).append((prev, following))
    series: list[dict[str, Any]] = []
    for exchange, pair, iv, n, first, last, n_w, first_w, last_w in summary:
        series.append(
            {
                "exchange": exchange,
                "pair": pair,
                "interval": int(iv),
                "first": first,
                "last": last,
                "count": int(n),
                "holes": holes_by_series.get((pair, int(iv)), [])
                if exchange == EXCHANGE_BINANCE
                else [],
                "count_2022_2023": int(n_w),
                "first_2022_2023": first_w,
                "last_2022_2023": last_w,
            }
        )
    return {
        "series": series,
        "session": {"transaction_read_only": str(read_only), "statement_timeout": str(timeout)},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_now(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventaire de données (lecture seule) : trous USDC, couverture, amorçage."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results" / "data_inventory_20260923" / "inventory.json",
        help="Artefact JSON (défaut : results/data_inventory_20260923/inventory.json).",
    )
    parser.add_argument("--markdown", type=Path, default=None, help="Rendu Markdown optionnel.")
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="Instant ISO : generated_at ET borne d'observation timestamp <= now (défaut : now UTC).",
    )
    parser.add_argument(
        "--skip-vision", action="store_true", help="N'exécute pas les HEAD Binance Vision (fait 4)."
    )
    parser.add_argument(
        "--reconcile-rejeu",
        type=Path,
        default=None,
        help="Optionnel : P7_phase1_grid.json du rejeu ; recoupe warmup.train BTC sur stdout.",
    )
    args = parser.parse_args(argv)
    if args.now is None:
        args.generated_at = datetime.now(UTC).replace(microsecond=0)
    else:
        try:
            args.generated_at = _parse_now(args.now)
        except ValueError as exc:
            parser.error(f"--now: {exc}")
    return args


def _print_reconciliation(series: Sequence[Mapping[str, Any]], path: Path) -> None:
    grid = rc.read_json(path)
    key = next(k for k in sorted(grid) if grid[k].get("pair") == "BTC/USDC")
    train = grid[key]["warmup"]["train"]
    print(f"recoupement warmup.train de {key} ({path}) :")
    for entry in reconcile_rejeu(series, train, "BTC/USDC"):
        same = (
            entry["declared_loaded"] == entry["recomputed_loaded"]
            and entry["declared_largest_gap"] == entry["recomputed_largest_gap"]
        )
        print(
            f"  {entry['tf']:>3}: loaded déclaré {entry['declared_loaded']} / recalculé "
            f"{entry['recomputed_loaded']} ; largest_gap déclaré {entry['declared_largest_gap']} / "
            f"recalculé {entry['recomputed_largest_gap']} ; [{entry['first']} .. {entry['last']}]"
            f" -> {'identique' if same else 'ÉCART'}"
        )
        for hole in entry.get("holes_inside", []):
            print(f"       trou {hole['start']} -> {hole['end']} ({hole['missing']} manquantes)")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # .env chargé ici, pas à l'import (règle B4.2).
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        collected = asyncio.run(collect(args.generated_at))
    except Exception as exc:  # noqa: BLE001 - base injoignable = erreur d'entrée, code 2
        print(f"database read failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    series = collected["series"]
    print(f"  {len(series)} séries agrégées, borne timestamp <= {args.generated_at.isoformat()}")

    vision = None if args.skip_vision else probe_vision()
    artifact = build_artifact(
        series, generated_at=args.generated_at, vision=vision, session_info=collected["session"]
    )
    digest = rc.write_json(args.output, artifact)
    print(f"inventory.json written: {args.output} (sha256 {digest})")
    if args.markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(
            render_markdown(artifact, json_sha256=digest, json_name=args.output.name),
            encoding="utf-8",
        )
        print(f"markdown written: {args.markdown}")
    if args.reconcile_rejeu is not None:
        _print_reconciliation(series, args.reconcile_rejeu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
