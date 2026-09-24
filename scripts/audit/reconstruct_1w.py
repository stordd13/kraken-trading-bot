"""Reconstruction des 8 estampilles 1 w manquantes des séries USDT Binance, depuis le 1 d.

Brief : ``agent/agent_reconstruction_1w.md``. Protocole : ``docs/protocole_c3.md`` v2.1 § A.8, bloc « Ce que la
lecture des données laisse attendre » : la reconstruction depuis le 1 d est une décision séparée, chiffrée, en rows
marquées dérivées, jamais silencieuse, et un prérequis du manifeste de la première campagne.

Sur ``exchange='binance'``, ``BTC/USDT``, ``ETH/USDT`` et ``SOL/USDT`` en 1 w, huit estampilles hebdomadaires manquent,
les mêmes sur les trois paires (``EXPECTED_MISSING``, brief § 1). Six tombent dans le préfixe de la première campagne
``(2021-03-01, T]`` et font tomber D1 1 w à 188/194 ; deux tombent dans la période évaluée.

Sous-commande ``check`` (défaut) — lecture seule
-------------------------------------------------
Transaction ``READ ONLY`` (assertée), rien n'est écrit en base. Mesures, par paire :

(a) **diagnostic** — ensemble manquant sur ``(WINDOW_START, WINDOW_END]`` comparé à ``EXPECTED_MISSING``, estampilles
    hors grille, ``cc.weekly_stamps_in`` sur le préfixe et sur la période évaluée, D1 1 w recalculé par
    ``cc.coverage_recompute`` sous la règle de ``c3_select.d1_for_pair`` (``d1_week``, épinglée par les tests) ;
(b) **disponibilité 1 d** — pour chaque cible, 7/7 rows sources, prix et volume non NULL, ``source_sha256`` ;
(c) **contrôle d'exactitude** — la méthode appliquée à **toutes** les semaines 1 w présentes de la fenêtre et comparée
    à la row Vision : OHLCV en égalité ``Decimal`` (attendu 0 mismatch), ``trades_count`` à part, ``vwap`` mesuré
    (population, écart si peuplé) ;
(d) **probe Vision** — pour chaque cible et chaque symbole, les deux fichiers mensuels 1 w (mois d'ouverture et de
    clôture de la semaine) : statut, ``Last-Modified``, bougies servies. Une cible trouvée dans un fichier est une
    **entrée de décision** du gate (importer la row réelle ou reconstruire), imprimée en tête du rapport — le
    script ne tranche pas ;
(e) **idempotence** — la clause ``ON CONFLICT DO NOTHING`` de l'import Vision, relevée dans sa source, et sa
    conséquence pour des rows dérivées.

Sous-commande ``write`` — écriture (après le gate humain)
---------------------------------------------------------
Exige ``--vwap-policy`` (décision humaine) et ``--note`` (entrée RESEARCH_LOG), un script committé sur un tree
suivi propre, et la table ``ohlc_derived`` (migration ``c3bd1e7a0001``). Dans **une** transaction : lecture des
séries et des clés déjà dérivées, ``plan_write`` (pur) rejoue le contrôle (c) — un seul mismatch OHLCV, une cible
déjà présente dans ``market_data_ohlc`` ou ``ohlc_derived``, une cible non reconstructible ou une valeur hors
``DECIMAL(18, 8)`` sans arrondi → refus, **aucun INSERT** —, puis deux INSERT **simples** : les 24 rows OHLC
(``exchange='binance'``), puis leurs 24 rows de provenance ; un conflit de clé lève et annule tout. Relecture sur
une connexion neuve, en lecture seule : D1 1 w préfixe (attendu 194/194), couverture évaluée, contrôle sur toutes
les semaines, ``count(*)`` de ``ohlc_derived``, et chaque provenance **rejouée** (``source_sha256`` recalculé
depuis les rows 1 d, row OHLC égale à l'agrégat).

Méthode ``agg_1d_v1`` (``aggregate_week``, pure)
------------------------------------------------
Pour la semaine d'estampille ``S`` (lundi 00:00 UTC, fin de période) : les 7 rows 1 d d'estampilles ``S − 6 j … S``
(end-stamped : la row stampée mardi 00:00 est le lundi). ``open`` du premier jour, ``close`` du dernier, ``high`` max,
``low`` min, ``volume`` Σ, ``trades_count`` Σ si les 7 sont non NULL (sinon NULL), ``vwap`` NULL ou
``Σ(vwap·vol)/Σvol`` selon la politique. Toute autre entrée (≠ 7 rows, doublon, estampille hors de la grille
``S − k j``, prix ou volume NULL) : semaine **non reconstructible**. Les sommes sont exactes (contexte qui lève sur
toute inexactitude).

Conventions : ``DATABASE_URL`` lue après ``load_dotenv`` dans ``main``, jamais ``Settings()`` (piège 5432) ni à
l'import ; ``Decimal`` partout ; littéral ``exchange='binance'`` (script de données) ; le tree suivi doit être propre
et le script committé, pour que le git sha de l'en-tête soit réel (``--allow-uncommitted`` : développement seulement,
en-tête marqué PROVISOIRE). Le JSON est écrit sans ``default=str`` (dette 22) : une valeur non native lève.

Usage::

    poetry run python scripts/audit/reconstruct_1w.py check \\
        --output results/reconstruction_1w_2022_2025/check_report.json \\
        --markdown results/reconstruction_1w_2022_2025/check_report.md [--skip-vision]

    poetry run python scripts/audit/reconstruct_1w.py write --vwap-policy null \\
        --note "docs/RESEARCH_LOG.md — entrée 13" \\
        --output results/reconstruction_1w_2022_2025/write_report.json \\
        --markdown results/reconstruction_1w_2022_2025/write_report.md

Codes de sortie de ``check`` : 0 contrôle vert ; 1 violation (ensemble manquant inattendu, estampille hors grille,
cible non reconstructible ou déjà présente, mismatch OHLCV, semaine présente non contrôlable) — le rapport est
écrit ; 2 usage, tree non propre, ancrage recalculé différent, ``DATABASE_URL`` absente, base injoignable — rien
n'est publié. Codes de ``write`` : 0 écrit et vérifié ; 1 refusé avant tout INSERT (rapport écrit, rien en base) ou
écrit mais relecture en échec (rapport écrit, ``status: written``) ; 2 usage, table absente, erreur avant commit
(transaction annulée, rien publié).
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
import urllib.error
import urllib.request

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import binance_vision_import as bvi  # noqa: E402
import c3_common as cc  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import bindparam, insert, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine  # noqa: E402
import structlog  # noqa: E402

from krakenbot.models.market_data import OHLCData, OHLCDerived  # noqa: E402

logger = structlog.get_logger()

PROJECT_ROOT = _ROOT
SCRIPT_RELPATH = "scripts/audit/reconstruct_1w.py"
IMPORTER_RELPATH = "scripts/binance_vision_import.py"

EXCHANGE = "binance"
PAIRS: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
#: Réutilisé par import, jamais recopié — épinglé par identité dans les tests.
WEEK_MINUTES = cc.WEEK_MINUTES
SOURCE_INTERVAL = 1440
DAYS_PER_WEEK = 7
#: Fenêtre de la première campagne (protocole v2.1 § A.3) et ancrage déclaré (§ A.8 v2.1, RESEARCH_LOG « Adoption ») ;
#: l'ancrage est **recalculé** par ``cc.anchor_of`` et comparé, jamais lu.
WINDOW_START = datetime(2021, 3, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 6, 29, tzinfo=UTC)
ANCHOR_DECLARED = datetime(2024, 11, 22, 4, 48, tzinfo=UTC)
#: Brief § 1 — identiques sur les trois paires.
EXPECTED_MISSING: tuple[datetime, ...] = tuple(
    datetime(y, m, d, tzinfo=UTC)
    for y, m, d in (
        (2022, 6, 6),
        (2022, 7, 4),
        (2022, 9, 5),
        (2022, 10, 3),
        (2022, 11, 7),
        (2022, 12, 5),
        (2025, 2, 3),
        (2025, 3, 3),
    )
)
METHOD = "agg_1d_v1"
OHLCV_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
VWAP_POLICIES: tuple[str, ...] = ("null", "weighted")
VISION_TIMEOUT_S = 30.0
#: Précision des sommes exactes : un produit vwap·volume (2 × 18 chiffres) tient sans arrondi.
_EXACT_PREC = 60
#: Chemins du backtest et de la chaîne C3 balayés pour les lecteurs de la colonne ``vwap`` (brief § 2 (c)).
VWAP_SCAN_PATHS: tuple[str, ...] = (
    "scripts/backtest.py",
    "scripts/run_p6_backtests.py",
    "scripts/run_p6_walkforward.py",
    "scripts/run_p7_grid_search.py",
    "scripts/p7_grids.py",
    "scripts/compute_benchmarks.py",
    "scripts/audit/c3_*.py",
    "src/krakenbot/backtesting",
    "src/krakenbot/backtest_metrics.py",
    "src/krakenbot/replay_contract.py",
    "src/krakenbot/strategies",
    "src/krakenbot/indicators",
)
_VWAP_TOKEN = re.compile(r"\bvwap\b")


class NotReconstructibleError(ValueError):
    """La semaine ne satisfait pas la méthode : 7 rows 1 d exactes sur la grille ``S − k j``, prix et volume non NULL."""


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _require_utc(stamp: datetime, *, what: str) -> None:
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError(f"{what} {stamp!r} : UTC explicite exigé")


def _dec_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


@dataclass(frozen=True)
class Candle:
    """Une row de ``market_data_ohlc`` (colonnes utiles), typée : ``Decimal`` ou ``None``, jamais ``float``."""

    timestamp: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal | None
    trades_count: int | None = None
    vwap: Decimal | None = None

    def __post_init__(self) -> None:
        _require_utc(self.timestamp, what="timestamp")
        for name in (*OHLCV_COLUMNS, "vwap"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                raise TypeError(f"{name} : Decimal exigé, reçu {type(value).__name__}")
        trades = self.trades_count
        if trades is not None and (isinstance(trades, bool) or not isinstance(trades, int)):
            raise TypeError(f"trades_count : int exigé, reçu {type(trades).__name__}")

    def price(self, column: str) -> Decimal:
        value = getattr(self, column)
        if value is None:
            raise NotReconstructibleError(f"{column} NULL à {self.timestamp.isoformat()}")
        return value

    def as_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"timestamp": self.timestamp.isoformat()}
        for column in OHLCV_COLUMNS:
            record[column] = _dec_str(getattr(self, column))
        record["trades_count"] = self.trades_count
        record["vwap"] = _dec_str(self.vwap)
        return record


@dataclass(frozen=True)
class Mismatch:
    stamp: datetime
    column: str
    kind: str  # "ohlcv" | "trades_count"
    vision: str | int | None
    rebuilt: str | int | None

    def as_record(self) -> dict[str, Any]:
        return {
            "week": self.stamp.isoformat(),
            "column": self.column,
            "kind": self.kind,
            "vision": self.vision,
            "rebuilt": self.rebuilt,
        }


# ---------------------------------------------------------------------------
# Méthode agg_1d_v1 — pure, codée une fois, réutilisée par `write` (étape 2)
# ---------------------------------------------------------------------------


def is_week_stamp(stamp: datetime) -> bool:
    _require_utc(stamp, what="estampille")
    return cc.last_stamp_at_or_before(stamp, WEEK_MINUTES) == stamp


def source_stamps(week_stamp: datetime) -> tuple[datetime, ...]:
    """Les 7 estampilles 1 d de la semaine ``S`` : ``S − 6 j … S`` (la row stampée mardi 00:00 est le lundi)."""
    if not is_week_stamp(week_stamp):
        raise NotReconstructibleError(
            f"{week_stamp.isoformat()} n'est pas une estampille 1 w (lundi 00:00 UTC)"
        )
    return tuple(week_stamp - timedelta(days=DAYS_PER_WEEK - 1 - k) for k in range(DAYS_PER_WEEK))


def _exact_sum(values: Iterable[Decimal]) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _EXACT_PREC
        ctx.traps[Inexact] = True
        ctx.traps[Rounded] = True
        return sum(values, Decimal(0))


def weighted_vwap(rows: Sequence[Candle]) -> Decimal | None:
    """``Σ(vwap_d·vol_d)/Σvol_d`` ; ``None`` si un ``vwap`` est NULL ou si ``Σvol == 0``."""
    if any(row.vwap is None for row in rows):
        return None
    with localcontext() as ctx:
        ctx.prec = _EXACT_PREC
        ctx.traps[Inexact] = True
        ctx.traps[Rounded] = True
        numerator = sum((row.price("vwap") * row.price("volume") for row in rows), Decimal(0))
        denominator = sum((row.price("volume") for row in rows), Decimal(0))
    if denominator == 0:
        return None
    return numerator / denominator


def aggregate_week(
    week_stamp: datetime, rows: Sequence[Candle], *, vwap_policy: str = "null"
) -> Candle:
    """La row 1 w de la semaine ``S`` reconstruite depuis ses 7 rows 1 d (méthode ``agg_1d_v1``)."""
    if vwap_policy not in VWAP_POLICIES:
        raise ValueError(f"vwap_policy {vwap_policy!r} hors de {VWAP_POLICIES}")
    expected = source_stamps(week_stamp)
    where = week_stamp.isoformat()
    if len(rows) != DAYS_PER_WEEK:
        raise NotReconstructibleError(f"{where} : {len(rows)} rows 1 d, {DAYS_PER_WEEK} exigées")
    by_stamp: dict[datetime, Candle] = {}
    for row in rows:
        if row.timestamp in by_stamp:
            raise NotReconstructibleError(
                f"{where} : estampille 1 d en double {row.timestamp.isoformat()}"
            )
        by_stamp[row.timestamp] = row
    off_grid = sorted(set(by_stamp) - set(expected))
    if off_grid:
        raise NotReconstructibleError(
            f"{where} : hors de la grille S − k j : {', '.join(s.isoformat() for s in off_grid)}"
        )
    ordered = [by_stamp[stamp] for stamp in expected]
    for row in ordered:
        for column in OHLCV_COLUMNS:
            row.price(column)
    trades = [row.trades_count for row in ordered]
    return Candle(
        timestamp=week_stamp,
        open=ordered[0].price("open"),
        high=max(row.price("high") for row in ordered),
        low=min(row.price("low") for row in ordered),
        close=ordered[-1].price("close"),
        volume=_exact_sum(row.price("volume") for row in ordered),
        trades_count=None
        if any(t is None for t in trades)
        else sum(t for t in trades if t is not None),
        vwap=None if vwap_policy == "null" else weighted_vwap(ordered),
    )


def source_sha256(pair: str, rows: Sequence[Candle]) -> str:
    """sha256 des rows 1 d sources sérialisées — ordre fixé (par estampille), ``str(Decimal)`` non normalisé."""
    payload = {
        "exchange": EXCHANGE,
        "pair": pair,
        "interval": SOURCE_INTERVAL,
        "rows": [row.as_record() for row in sorted(rows, key=lambda r: r.timestamp)],
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compare_week(stored: Candle, rebuilt: Candle) -> list[Mismatch]:
    """Mismatches OHLCV (égalité ``Decimal``) puis ``trades_count`` — le ``vwap`` se mesure à part (``vwap_gap``)."""
    if stored.timestamp != rebuilt.timestamp:
        raise ValueError("comparaison de deux semaines différentes")
    out: list[Mismatch] = []
    for column in OHLCV_COLUMNS:
        vision, ours = getattr(stored, column), getattr(rebuilt, column)
        if vision != ours:
            out.append(
                Mismatch(stored.timestamp, column, "ohlcv", _dec_str(vision), _dec_str(ours))
            )
    if stored.trades_count != rebuilt.trades_count:
        out.append(
            Mismatch(
                stored.timestamp,
                "trades_count",
                "trades_count",
                stored.trades_count,
                rebuilt.trades_count,
            )
        )
    return out


def vwap_gap(stored: Candle, rebuilt: Candle) -> Decimal | None:
    if stored.vwap is None or rebuilt.vwap is None:
        return None
    return abs(stored.vwap - rebuilt.vwap)


# ---------------------------------------------------------------------------
# Grille hebdomadaire et D1 (règle de c3_select.d1_for_pair, sur cc.coverage_recompute)
# ---------------------------------------------------------------------------


def expected_week_stamps(start: datetime, end: datetime) -> list[datetime]:
    """Estampilles 1 w de la grille (lundi 00:00, fin de période) dans ``(start, end]``."""
    stamps: list[datetime] = []
    stamp = cc.first_stamp_strictly_after(start, WEEK_MINUTES)
    while stamp <= end:
        stamps.append(stamp)
        stamp += timedelta(days=DAYS_PER_WEEK)
    return stamps


def missing_week_stamps(
    present: Iterable[datetime], start: datetime, end: datetime
) -> tuple[list[datetime], list[datetime]]:
    """``(manquantes, hors grille)`` dans ``(start, end]`` ; les estampilles hors fenêtre sont ignorées."""
    in_window = {stamp for stamp in present if start < stamp <= end}
    grid = expected_week_stamps(start, end)
    grid_set = set(grid)
    missing = [stamp for stamp in grid if stamp not in in_window]
    off_grid = sorted(stamp for stamp in in_window if stamp not in grid_set)
    return missing, off_grid


def week_coverage_block(
    present: Iterable[datetime], *, start: datetime, end: datetime
) -> dict[str, Any]:
    """Le bloc de couverture 1 w (forme du § A.7) que ``cc.coverage_recompute`` recoupe."""
    present_list = list(present)
    missing, off_grid = missing_week_stamps(present_list, start, end)
    if off_grid:
        raise ValueError(
            f"estampilles 1 w hors grille : {', '.join(s.isoformat() for s in off_grid)}"
        )
    kept = sorted(stamp for stamp in present_list if start < stamp <= end)
    if not kept:
        raise ValueError("aucune estampille 1 w présente dans la fenêtre")
    expected = cc.expected_candles(start, end, WEEK_MINUTES)
    units = cc.expected_units(start, end, WEEK_MINUTES)
    return {
        "expected": expected,
        "observed": expected - len(missing),
        "covered_units": units - len(missing),
        "expected_units": units,
        "unit": cc.coverage_unit(WEEK_MINUTES),
        "missing_stamps": [stamp.isoformat() for stamp in missing],
        "longest_gap_days": cc.gap_days(
            cc.longest_missing_run(missing, WEEK_MINUTES), WEEK_MINUTES
        ),
        "first_day": kept[0].date().isoformat(),
        "last_day": kept[-1].date().isoformat(),
    }


def d1_week(present: Iterable[datetime], *, start: datetime, end: datetime) -> dict[str, Any]:
    """D1 sur la série 1 w : valeurs recoupées par ``cc.coverage_recompute``, règle de ``c3_select.d1_for_pair``."""
    block = week_coverage_block(present, start=start, end=end)
    recomputed = cc.coverage_recompute(
        block, start=start, end=end, interval=WEEK_MINUTES, where="coverage.10080"
    )
    if recomputed["problems"]:
        raise ValueError("couverture incohérente : " + " ; ".join(recomputed["problems"]))
    covered = recomputed["covered_recomputed"]
    units = recomputed["expected_units_recomputed"]
    gap = recomputed["longest_gap_days_recomputed"]
    gap_max = cc.max_gap_days((end - start).total_seconds() / 86400.0)
    ratio = covered / units
    return {
        "unit": cc.coverage_unit(WEEK_MINUTES),
        "covered_units": covered,
        "expected_units": units,
        "ratio": ratio,
        "longest_gap_days": gap,
        "gap_max_days": gap_max,
        "ok": ratio >= cc.COVERAGE_MIN_RATIO and gap <= gap_max,
        "missing": block["missing_stamps"],
    }


# ---------------------------------------------------------------------------
# (d) Probe Vision — partie pure, puis réseau
# ---------------------------------------------------------------------------


def vision_months_for_week(week_stamp: datetime) -> list[tuple[int, int]]:
    """Mois d'ouverture (lundi ``S − 7 j``) et mois de clôture (dimanche ``S − 1 j``) de la semaine ``S``."""
    opening = week_stamp - timedelta(days=DAYS_PER_WEEK)
    closing = week_stamp - timedelta(days=1)
    return sorted({(opening.year, opening.month), (closing.year, closing.month)})


def straddling_weeks(stamps: Iterable[datetime]) -> list[datetime]:
    """Les semaines à cheval sur deux mois (lundi d'ouverture et dimanche de clôture dans deux mois différents)."""
    return [stamp for stamp in stamps if len(vision_months_for_week(stamp)) == 2]


def vision_url(pair: str, year: int, month: int) -> str:
    """Schéma d'URL de l'import (``binance_vision_import.py``, ``import_month``)."""
    symbol = bvi.pair_to_binance_symbol(pair)
    label = bvi.INTERVAL_TO_BINANCE[WEEK_MINUTES]
    return f"{bvi.BASE_URL}/{symbol}/{label}/{symbol}-{label}-{year:04d}-{month:02d}.zip"


def vision_week_rows(csv_bytes: bytes, pair: str) -> list[dict[str, Any]]:
    """Chaque ligne kline du CSV, parsée par ``bvi.parse_klines_csv`` (estampille de fin), avec ses colonnes brutes."""
    rows: list[dict[str, Any]] = []
    for raw in csv.reader(io.StringIO(csv_bytes.decode("utf-8"))):
        if not raw:
            continue
        parsed = bvi.parse_klines_csv(",".join(raw).encode("utf-8"), pair, WEEK_MINUTES)
        if parsed:
            rows.append({"stamp": parsed[0]["timestamp"], "raw": raw, "parsed": parsed[0]})
    return rows


def fetch_vision(url: str, *, timeout: float = VISION_TIMEOUT_S) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return {
                "status": int(response.status),
                "last_modified": response.headers.get("Last-Modified"),
                "body": response.read(),
            }
    except urllib.error.HTTPError as exc:
        return {"status": int(exc.code), "last_modified": None, "body": None}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": f"ERR:{type(exc).__name__}", "last_modified": None, "body": None}


def probe_vision(pairs: Sequence[str], stamps: Sequence[datetime]) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    targets: list[dict[str, Any]] = []
    for pair in pairs:
        for stamp in stamps:
            seen: list[dict[str, Any]] = []
            for year, month in vision_months_for_week(stamp):
                url = vision_url(pair, year, month)
                if url not in files:
                    fetched = fetch_vision(url)
                    parsed: list[dict[str, Any]] | None = None
                    digest = None
                    if fetched["status"] == 200 and fetched["body"]:
                        digest = hashlib.sha256(fetched["body"]).hexdigest()
                        csv_bytes = bvi.extract_csv_from_zip(fetched["body"])
                        parsed = None if csv_bytes is None else vision_week_rows(csv_bytes, pair)
                    files[url] = {
                        "url": url,
                        "month": f"{year:04d}-{month:02d}",
                        "status": fetched["status"],
                        "last_modified": fetched["last_modified"],
                        "zip_sha256": digest,
                        "rows": parsed,
                    }
                    logger.info("vision_file", url=url, status=fetched["status"])
                entry = files[url]
                rows = entry["rows"]
                hit = None if rows is None else next((r for r in rows if r["stamp"] == stamp), None)
                seen.append(
                    {
                        "url": url,
                        "month": entry["month"],
                        "status": entry["status"],
                        "last_modified": entry["last_modified"],
                        "zip_sha256": entry["zip_sha256"],
                        "stamps_served": None
                        if rows is None
                        else [r["stamp"].isoformat() for r in rows],
                        "straddling_served": None
                        if rows is None
                        else _iso_list(straddling_weeks(r["stamp"] for r in rows)),
                        "contains_target": None if rows is None else hit is not None,
                        "served_row": None if hit is None else hit["raw"],
                    }
                )
            targets.append(
                {
                    "pair": pair,
                    "week": stamp.isoformat(),
                    "files": seen,
                    "found": any(f["contains_target"] is True for f in seen),
                    "inconclusive": any(f["contains_target"] is None for f in seen),
                }
            )
    found = [t for t in targets if t["found"]]
    inconclusive = [t for t in targets if t["inconclusive"]]
    return {
        "skipped": False,
        "files_read": sum(1 for f in files.values() if f["rows"] is not None),
        "files_requested": len(files),
        "targets": targets,
        "positive": [{"pair": t["pair"], "week": t["week"]} for t in found],
        "inconclusive": [{"pair": t["pair"], "week": t["week"]} for t in inconclusive],
    }


# ---------------------------------------------------------------------------
# Lecture de code, mécanique : lecteurs de `vwap`, clause de conflit de l'import
# ---------------------------------------------------------------------------


def _scan_files(pattern: str) -> list[Path]:
    if any(ch in pattern for ch in "*?["):
        return sorted(PROJECT_ROOT.glob(pattern))
    path = PROJECT_ROOT / pattern
    if path.is_dir():
        return sorted(path.rglob("*.py"))
    return [path] if path.exists() else []


def scan_vwap_tokens() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    absent: list[str] = []
    for pattern in VWAP_SCAN_PATHS:
        paths = _scan_files(pattern)
        if not paths:
            absent.append(pattern)
        for path in paths:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if _VWAP_TOKEN.search(line):
                    hits.append(
                        {
                            "file": str(path.relative_to(PROJECT_ROOT)),
                            "line": number,
                            "text": line.strip(),
                        }
                    )
    return {"paths": list(VWAP_SCAN_PATHS), "absent_paths": absent, "hits": hits}


def importer_conflict_clause() -> dict[str, Any]:
    path = PROJECT_ROOT / IMPORTER_RELPATH
    source = path.read_text(encoding="utf-8")
    lines = [
        {"line": number, "text": line.strip()}
        for number, line in enumerate(source.splitlines(), start=1)
        if "on_conflict_do_nothing" in line or "index_elements" in line
    ]
    return {
        "importer": IMPORTER_RELPATH,
        "importer_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "clause_lines": lines,
    }


# ---------------------------------------------------------------------------
# Provenance git
# ---------------------------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )


def git_provenance() -> dict[str, Any]:
    script = PROJECT_ROOT / SCRIPT_RELPATH
    return {
        "git_sha": _git("rev-parse", "HEAD").stdout.strip(),
        "branch": _git("branch", "--show-current").stdout.strip(),
        "script": SCRIPT_RELPATH,
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "script_tracked": _git("ls-files", "--error-unmatch", SCRIPT_RELPATH).returncode == 0,
        "tracked_tree_clean": _git("status", "--porcelain", "--untracked-files=no").stdout.strip()
        == "",
    }


# ---------------------------------------------------------------------------
# Couche base — lecture seule
# ---------------------------------------------------------------------------

SERIES_SQL = text(
    """
    SELECT pair, timestamp, open, high, low, close, volume, trades_count, vwap
    FROM market_data_ohlc
    WHERE exchange = :exchange AND interval = :interval AND pair IN :pairs
      AND timestamp > :lo AND timestamp <= :hi
    ORDER BY pair, timestamp
    """
).bindparams(bindparam("pairs", expanding=True))

POPULATION_SQL = text(
    """
    SELECT pair, interval, COUNT(*) AS n, COUNT(vwap) AS n_vwap, COUNT(trades_count) AS n_trades,
           MIN(timestamp) AS first_stamp, MAX(timestamp) AS last_stamp
    FROM market_data_ohlc
    WHERE exchange = :exchange AND interval IN (1440, 10080)
    GROUP BY pair, interval
    ORDER BY pair, interval
    """
)

COMPRESSION_SQL = text(
    """
    SELECT compression_enabled FROM timescaledb_information.hypertables
    WHERE hypertable_name = 'market_data_ohlc'
    """
)

CHUNKS_SQL = text(
    """
    SELECT chunk_name, range_start, range_end, is_compressed
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'market_data_ohlc' AND range_end > :lo AND range_start <= :hi
    ORDER BY range_start
    """
)

DERIVED_TABLE_SQL = text("SELECT to_regclass('public.ohlc_derived') IS NOT NULL")


def _candle_from_row(row: Any) -> Candle:
    return Candle(
        timestamp=row.timestamp,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        trades_count=row.trades_count,
        vwap=row.vwap,
    )


async def _read_series(
    conn: AsyncConnection, interval: int, lo: datetime, hi: datetime
) -> dict[str, dict[datetime, Candle]]:
    result = await conn.execute(
        SERIES_SQL,
        {"exchange": EXCHANGE, "interval": interval, "pairs": list(PAIRS), "lo": lo, "hi": hi},
    )
    series: dict[str, dict[datetime, Candle]] = {pair: {} for pair in PAIRS}
    for row in result:
        series[row.pair][row.timestamp] = _candle_from_row(row)
    return series


async def collect(url: str) -> dict[str, Any]:
    """Le seul endroit qui touche la base : une transaction ``READ ONLY`` assertée, puis rollback."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text("SET LOCAL statement_timeout = '120s'"))
            read_only = (await conn.execute(text("SHOW transaction_read_only"))).scalar_one()
            if read_only != "on":
                raise RuntimeError(f"transaction_read_only = {read_only!r}, 'on' exigé")
            weekly = await _read_series(conn, WEEK_MINUTES, WINDOW_START, WINDOW_END)
            daily = await _read_series(
                conn, SOURCE_INTERVAL, WINDOW_START - timedelta(days=DAYS_PER_WEEK), WINDOW_END
            )
            population = [
                {
                    "pair": row.pair,
                    "interval": int(row.interval),
                    "rows": int(row.n),
                    "vwap_non_null": int(row.n_vwap),
                    "trades_count_non_null": int(row.n_trades),
                    "first": row.first_stamp.isoformat(),
                    "last": row.last_stamp.isoformat(),
                }
                for row in await conn.execute(POPULATION_SQL, {"exchange": EXCHANGE})
            ]
            compression = (await conn.execute(COMPRESSION_SQL)).scalar_one_or_none()
            chunks = [
                {
                    "chunk": row.chunk_name,
                    "range_start": row.range_start,
                    "range_end": row.range_end,
                    "is_compressed": bool(row.is_compressed),
                }
                for row in await conn.execute(
                    CHUNKS_SQL, {"lo": min(EXPECTED_MISSING), "hi": max(EXPECTED_MISSING)}
                )
            ]
            derived_exists = bool((await conn.execute(DERIVED_TABLE_SQL)).scalar_one())
            await conn.rollback()
    finally:
        await engine.dispose()
    return {
        "read_only": read_only,
        "weekly": weekly,
        "daily": daily,
        "population": population,
        "compression_enabled": compression,
        "chunks": chunks,
        "derived_table_exists": derived_exists,
    }


# ---------------------------------------------------------------------------
# Construction du rapport
# ---------------------------------------------------------------------------


def _iso_list(stamps: Iterable[datetime]) -> list[str]:
    return [stamp.isoformat() for stamp in stamps]


def diagnose_pair(weekly: Mapping[datetime, Candle], anchor: datetime) -> dict[str, Any]:
    missing, off_grid = missing_week_stamps(weekly, WINDOW_START, WINDOW_END)
    in_window = [s for s in weekly if WINDOW_START < s <= WINDOW_END]
    return {
        "present_in_window": len(in_window),
        "expected_in_window": len(expected_week_stamps(WINDOW_START, WINDOW_END)),
        "missing": _iso_list(missing),
        "missing_equals_brief": tuple(missing) == EXPECTED_MISSING,
        "off_grid": _iso_list(off_grid),
        "weekly_stamps_prefix": cc.weekly_stamps_in(WINDOW_START, anchor),
        "weekly_stamps_evaluated": cc.weekly_stamps_in(anchor, WINDOW_END),
        "d1_prefix": d1_week(weekly, start=WINDOW_START, end=anchor) if not off_grid else None,
        "coverage_evaluated": d1_week(weekly, start=anchor, end=WINDOW_END)
        if not off_grid
        else None,
    }


def availability(
    pair: str, weekly: Mapping[datetime, Candle], daily: Mapping[datetime, Candle]
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for stamp in EXPECTED_MISSING:
        sources = source_stamps(stamp)
        rows = [daily[s] for s in sources if s in daily]
        entry: dict[str, Any] = {
            "week": stamp.isoformat(),
            "source_stamps": _iso_list(sources),
            "present": len(rows),
            "absent": _iso_list(s for s in sources if s not in daily),
            "already_present_in_1w": stamp in weekly,
        }
        try:
            rebuilt = aggregate_week(stamp, rows, vwap_policy="null")
        except NotReconstructibleError as exc:
            entry.update({"reconstructible": False, "reason": str(exc)})
        else:
            entry.update(
                {
                    "reconstructible": True,
                    "source_sha256": source_sha256(pair, rows),
                    "rebuilt": rebuilt.as_record(),
                    "sources": [row.as_record() for row in sorted(rows, key=lambda r: r.timestamp)],
                }
            )
        targets.append(entry)
    return targets


def control(weekly: Mapping[datetime, Candle], daily: Mapping[datetime, Candle]) -> dict[str, Any]:
    compared = 0
    not_controllable: list[dict[str, str]] = []
    ohlcv: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    trades_compared = 0
    trades_with_null = 0
    vwap_stored = 0
    vwap_rebuilt = 0
    vwap_gaps: list[Decimal] = []
    for stamp in sorted(s for s in weekly if WINDOW_START < s <= WINDOW_END):
        stored = weekly[stamp]
        try:
            rows = [daily[s] for s in source_stamps(stamp) if s in daily]
            rebuilt = aggregate_week(stamp, rows, vwap_policy="weighted")
        except NotReconstructibleError as exc:
            not_controllable.append({"week": stamp.isoformat(), "reason": str(exc)})
            continue
        compared += 1
        for mismatch in compare_week(stored, rebuilt):
            (ohlcv if mismatch.kind == "ohlcv" else trades).append(mismatch.as_record())
        if stored.trades_count is None or rebuilt.trades_count is None:
            trades_with_null += 1
        else:
            trades_compared += 1
        vwap_stored += stored.vwap is not None
        vwap_rebuilt += rebuilt.vwap is not None
        gap = vwap_gap(stored, rebuilt)
        if gap is not None:
            vwap_gaps.append(gap)
    return {
        "weeks_compared": compared,
        "not_controllable": not_controllable,
        "ohlcv_mismatches": ohlcv,
        "trades_count": {
            "compared": trades_compared,
            "with_null": trades_with_null,
            "mismatches": trades,
        },
        "vwap": {
            "stored_non_null": vwap_stored,
            "rebuilt_non_null": vwap_rebuilt,
            "compared": len(vwap_gaps),
            "max_abs_gap": None if not vwap_gaps else str(max(vwap_gaps)),
        },
    }


def vwap_proposal(population: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ours = [p for p in population if p["pair"] in PAIRS]
    daily_non_null = sum(p["vwap_non_null"] for p in ours if p["interval"] == SOURCE_INTERVAL)
    weekly_non_null = sum(p["vwap_non_null"] for p in ours if p["interval"] == WEEK_MINUTES)
    if daily_non_null == 0:
        policy = "null"
        reason = (
            "la colonne vwap n'est peuplée sur aucune row 1 d des séries USDT : la formule pondérée n'a pas "
            "d'entrée, seule la politique null est calculable"
        )
    else:
        policy = "weighted"
        reason = "vwap peuplé sur des rows 1 d : formule pondérée calculable, écart à documenter"
    return {
        "proposal": policy,
        "reason": reason,
        "usdt_daily_vwap_non_null": daily_non_null,
        "usdt_weekly_vwap_non_null": weekly_non_null,
        "decided": False,
    }


def chunk_status(chunks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for stamp in EXPECTED_MISSING:
        holders = [c for c in chunks if c["range_start"] <= stamp < c["range_end"]]
        out.append(
            {
                "week": stamp.isoformat(),
                "chunks": [
                    {
                        "chunk": c["chunk"],
                        "range_start": c["range_start"].isoformat(),
                        "range_end": c["range_end"].isoformat(),
                        "is_compressed": c["is_compressed"],
                    }
                    for c in holders
                ],
            }
        )
    return out


def build_report(
    collected: Mapping[str, Any],
    *,
    vision: Mapping[str, Any],
    provenance: Mapping[str, Any],
    database: Mapping[str, Any],
    generated_at: datetime,
    argv: Sequence[str],
) -> dict[str, Any]:
    anchor = cc.anchor_of(WINDOW_START, WINDOW_END)
    violations: list[str] = []
    pairs: dict[str, Any] = {}
    for pair in PAIRS:
        weekly = collected["weekly"][pair]
        daily = collected["daily"][pair]
        diag = diagnose_pair(weekly, anchor)
        if not diag["missing_equals_brief"]:
            violations.append(
                f"{pair} (a) : manquantes {diag['missing']} != brief {_iso_list(EXPECTED_MISSING)}"
            )
        if diag["off_grid"]:
            violations.append(f"{pair} (a) : estampilles 1 w hors grille {diag['off_grid']}")
        targets = availability(pair, weekly, daily)
        for target in targets:
            if not target["reconstructible"]:
                violations.append(
                    f"{pair} (b) : {target['week']} non reconstructible — {target['reason']}"
                )
            if target["already_present_in_1w"]:
                violations.append(f"{pair} (b) : {target['week']} déjà présente en 1 w")
        ctrl = control(weekly, daily)
        if ctrl["ohlcv_mismatches"]:
            violations.append(f"{pair} (c) : {len(ctrl['ohlcv_mismatches'])} mismatch(es) OHLCV")
        if ctrl["not_controllable"]:
            violations.append(
                f"{pair} (c) : {len(ctrl['not_controllable'])} semaine(s) non contrôlable(s)"
            )
        pairs[pair] = {"a_diagnostic": diag, "b_availability": targets, "c_control": ctrl}
    reconstructible = sum(t["reconstructible"] for p in pairs.values() for t in p["b_availability"])
    ohlcv_total = sum(len(p["c_control"]["ohlcv_mismatches"]) for p in pairs.values())
    compared_total = sum(p["c_control"]["weeks_compared"] for p in pairs.values())
    return {
        "artifact": "reconstruct_1w.check",
        "generated_at": generated_at.isoformat(),
        "argv": list(argv),
        "provenance": dict(provenance),
        "database": dict(database),
        "scope": {
            "exchange": EXCHANGE,
            "pairs": list(PAIRS),
            "target_interval": WEEK_MINUTES,
            "source_interval": SOURCE_INTERVAL,
            "window": {"start": WINDOW_START.isoformat(), "end": WINDOW_END.isoformat()},
            "anchor": anchor.isoformat(),
            "expected_missing": _iso_list(EXPECTED_MISSING),
            "method": METHOD,
        },
        "pairs": pairs,
        "vwap": {
            "population_binance": list(collected["population"]),
            "readers_scan": scan_vwap_tokens(),
            **vwap_proposal(collected["population"]),
        },
        "d_vision_probe": dict(vision),
        "e_idempotence": importer_conflict_clause(),
        "timescale": {
            "compression_enabled": collected["compression_enabled"],
            "target_chunks": chunk_status(collected["chunks"]),
        },
        "ohlc_derived_table_exists": collected["derived_table_exists"],
        "summary": {
            "ok": not violations,
            "violations": violations,
            "targets_reconstructible": f"{reconstructible}/{len(EXPECTED_MISSING) * len(PAIRS)}",
            "weeks_compared": compared_total,
            "ohlcv_mismatches": ohlcv_total,
            "vision_positive": list(vision.get("positive", [])),
        },
    }


# ---------------------------------------------------------------------------
# Étape 2 — `write` : garde-fous purs (`plan_write`), puis deux INSERT simples dans une transaction
# ---------------------------------------------------------------------------

_Q8 = Decimal("1E-8")
_NUMERIC_18_8_MAX = Decimal("9999999999.99999999")


def fits_numeric_18_8(value: Decimal) -> bool:
    """Tient dans ``DECIMAL(18, 8)`` sans arrondi ni dépassement (au-delà, Postgres arrondit ou lève)."""
    if not value.is_finite():
        return False
    try:
        exact = value.quantize(_Q8) == value
    except InvalidOperation:
        return False
    return exact and abs(value) <= _NUMERIC_18_8_MAX


class WriteRefusedError(Exception):
    """Écriture refusée **avant tout INSERT** : ``code`` 1 = violation (contrôle, cible présente, non
    reconstructible, hors DECIMAL(18, 8)), 2 = usage (politique, note, table de provenance absente)."""

    def __init__(self, code: int, reasons: Sequence[str]) -> None:
        super().__init__(" ; ".join(reasons))
        self.code = code
        self.reasons = list(reasons)


@dataclass(frozen=True)
class WriteState:
    """Ce que ``write`` lit avant d'écrire, dans la même transaction."""

    weekly: Mapping[str, Mapping[datetime, Candle]]
    daily: Mapping[str, Mapping[datetime, Candle]]
    derived_keys: frozenset[tuple[str, datetime]]
    derived_table_exists: bool


@dataclass(frozen=True)
class WritePlan:
    ohlc_rows: list[dict[str, Any]]
    provenance_rows: list[dict[str, Any]]
    control: dict[str, Any]
    d1_before: dict[str, Any]
    coverage_evaluated_before: dict[str, Any]


def plan_write(
    state: WriteState,
    *,
    vwap_policy: str,
    note: str,
    provenance: Mapping[str, Any],
    created_at: datetime,
) -> WritePlan:
    """Rejoue le contrôle (c), vérifie chaque cible, construit les 24 + 24 rows — ou refuse sans rien écrire."""
    if vwap_policy not in VWAP_POLICIES:
        raise WriteRefusedError(2, [f"vwap_policy {vwap_policy!r} hors de {VWAP_POLICIES}"])
    if not note.strip():
        raise WriteRefusedError(2, ["note vide : la référence RESEARCH_LOG est exigée"])
    if not state.derived_table_exists:
        raise WriteRefusedError(
            2,
            [
                "table ohlc_derived absente : `alembic upgrade head` d'abord (migration c3bd1e7a0001)"
            ],
        )
    anchor = cc.anchor_of(WINDOW_START, WINDOW_END)
    reasons: list[str] = []
    control_summary: dict[str, Any] = {}
    d1_before: dict[str, Any] = {}
    evaluated_before: dict[str, Any] = {}
    ohlc_rows: list[dict[str, Any]] = []
    provenance_rows: list[dict[str, Any]] = []
    for pair in PAIRS:
        weekly = state.weekly.get(pair, {})
        daily = state.daily.get(pair, {})
        _, off_grid = missing_week_stamps(weekly, WINDOW_START, WINDOW_END)
        if off_grid:
            reasons.append(f"{pair} (a) : estampilles 1 w hors grille {_iso_list(off_grid)}")
        else:
            d1_before[pair] = d1_week(weekly, start=WINDOW_START, end=anchor)
            evaluated_before[pair] = d1_week(weekly, start=anchor, end=WINDOW_END)
        ctrl = control(weekly, daily)
        control_summary[pair] = {
            "weeks_compared": ctrl["weeks_compared"],
            "ohlcv_mismatches": len(ctrl["ohlcv_mismatches"]),
            "trades_count_mismatches": len(ctrl["trades_count"]["mismatches"]),
            "not_controllable": len(ctrl["not_controllable"]),
        }
        if ctrl["ohlcv_mismatches"]:
            first = ctrl["ohlcv_mismatches"][0]
            reasons.append(
                f"{pair} (c) : {len(ctrl['ohlcv_mismatches'])} mismatch(es) OHLCV, premier "
                f"{first['week'][:10]} {first['column']} Vision {first['vision']} ≠ {first['rebuilt']}"
            )
        if ctrl["not_controllable"]:
            reasons.append(
                f"{pair} (c) : {len(ctrl['not_controllable'])} semaine(s) non contrôlable(s)"
            )
        for stamp in EXPECTED_MISSING:
            where = f"{pair} {stamp.isoformat()}"
            if stamp in weekly:
                reasons.append(f"{where} : déjà présente dans market_data_ohlc")
                continue
            if (pair, stamp) in state.derived_keys:
                reasons.append(f"{where} : déjà présente dans ohlc_derived")
                continue
            sources = source_stamps(stamp)
            rows = [daily[s] for s in sources if s in daily]
            try:
                rebuilt = aggregate_week(stamp, rows, vwap_policy=vwap_policy)
            except NotReconstructibleError as exc:
                reasons.append(f"{where} (b) : {exc}")
                continue
            values = {column: rebuilt.price(column) for column in OHLCV_COLUMNS}
            if rebuilt.vwap is not None:
                values["vwap"] = rebuilt.vwap
            unfit = sorted(
                column for column, value in values.items() if not fits_numeric_18_8(value)
            )
            if unfit:
                reasons.append(f"{where} : hors DECIMAL(18, 8) sans arrondi : {', '.join(unfit)}")
                continue
            key = {"timestamp": stamp, "pair": pair, "interval": WEEK_MINUTES, "exchange": EXCHANGE}
            ohlc_rows.append(
                {**key, **values, "vwap": rebuilt.vwap, "trades_count": rebuilt.trades_count}
            )
            provenance_rows.append(
                {
                    **key,
                    "method": METHOD,
                    "source_interval": SOURCE_INTERVAL,
                    "source_stamps": _iso_list(sources),
                    "source_sha256": source_sha256(pair, rows),
                    "vwap_policy": vwap_policy,
                    "script_sha256": provenance["script_sha256"],
                    "git_sha": provenance["git_sha"],
                    "created_at": created_at,
                    "note": note,
                }
            )
    if reasons:
        raise WriteRefusedError(1, reasons)
    expected = len(PAIRS) * len(EXPECTED_MISSING)
    if len(ohlc_rows) != expected or len(provenance_rows) != expected:
        raise WriteRefusedError(1, [f"{len(ohlc_rows)} rows planifiées, {expected} attendues"])
    return WritePlan(
        ohlc_rows=ohlc_rows,
        provenance_rows=provenance_rows,
        control=control_summary,
        d1_before=d1_before,
        coverage_evaluated_before=evaluated_before,
    )


DERIVED_KEYS_SQL = text(
    """
    SELECT pair, timestamp FROM ohlc_derived
    WHERE exchange = :exchange AND interval = :interval AND pair IN :pairs
    """
).bindparams(bindparam("pairs", expanding=True))

DERIVED_ROWS_SQL = text(
    """
    SELECT d.timestamp, d.pair, d.interval, d.exchange, d.method, d.source_interval, d.source_stamps,
           d.source_sha256, d.vwap_policy, d.script_sha256, d.git_sha, d.created_at, d.note,
           o.open, o.high, o.low, o.close, o.volume, o.trades_count, o.vwap
    FROM ohlc_derived d
    LEFT JOIN market_data_ohlc o
      ON o.timestamp = d.timestamp AND o.pair = d.pair AND o.interval = d.interval
     AND o.exchange = d.exchange
    ORDER BY d.pair, d.timestamp
    """
)

DERIVED_COUNT_SQL = text("SELECT COUNT(*) FROM ohlc_derived")


async def load_write_state(conn: AsyncConnection) -> WriteState:
    exists = bool((await conn.execute(DERIVED_TABLE_SQL)).scalar_one())
    weekly = await _read_series(conn, WEEK_MINUTES, WINDOW_START, WINDOW_END)
    daily = await _read_series(
        conn, SOURCE_INTERVAL, WINDOW_START - timedelta(days=DAYS_PER_WEEK), WINDOW_END
    )
    keys: frozenset[tuple[str, datetime]] = frozenset()
    if exists:
        result = await conn.execute(
            DERIVED_KEYS_SQL,
            {"exchange": EXCHANGE, "interval": WEEK_MINUTES, "pairs": list(PAIRS)},
        )
        keys = frozenset((row.pair, row.timestamp) for row in result)
    return WriteState(weekly=weekly, daily=daily, derived_keys=keys, derived_table_exists=exists)


async def perform_write(
    conn: Any,
    *,
    load: Any,
    vwap_policy: str,
    note: str,
    provenance: Mapping[str, Any],
    created_at: datetime,
) -> WritePlan:
    """Lit, planifie (refus sans rien exécuter), puis deux INSERT **simples** : OHLC puis provenance.

    Un conflit de clé lève et annule la transaction : la présence des cibles vient d'être vérifiée, un
    ``ON CONFLICT DO NOTHING`` masquerait une course au lieu de la signaler (gate du 24/09).
    """
    state = await load(conn)
    plan = plan_write(
        state, vwap_policy=vwap_policy, note=note, provenance=provenance, created_at=created_at
    )
    await conn.execute(insert(OHLCData), plan.ohlc_rows)
    await conn.execute(insert(OHLCDerived), plan.provenance_rows)
    return plan


async def verify_after_write(conn: AsyncConnection) -> dict[str, Any]:
    """Relecture sur une connexion neuve, en lecture seule : couverture, contrôle, provenance rejouée."""
    await conn.execute(text("SET TRANSACTION READ ONLY"))
    anchor = cc.anchor_of(WINDOW_START, WINDOW_END)
    weekly = await _read_series(conn, WEEK_MINUTES, WINDOW_START, WINDOW_END)
    daily = await _read_series(
        conn, SOURCE_INTERVAL, WINDOW_START - timedelta(days=DAYS_PER_WEEK), WINDOW_END
    )
    count = int((await conn.execute(DERIVED_COUNT_SQL)).scalar_one())
    derived = list(await conn.execute(DERIVED_ROWS_SQL))
    await conn.rollback()
    problems: list[str] = []
    pairs: dict[str, Any] = {}
    for pair in PAIRS:
        missing, off_grid = missing_week_stamps(weekly[pair], WINDOW_START, WINDOW_END)
        ctrl = control(weekly[pair], daily[pair])
        d1_after = d1_week(weekly[pair], start=WINDOW_START, end=anchor)
        evaluated_after = d1_week(weekly[pair], start=anchor, end=WINDOW_END)
        pairs[pair] = {
            "missing_in_window": _iso_list(missing),
            "off_grid": _iso_list(off_grid),
            "d1_prefix_after": d1_after,
            "coverage_evaluated_after": evaluated_after,
            "weeks_compared": ctrl["weeks_compared"],
            "ohlcv_mismatches": len(ctrl["ohlcv_mismatches"]),
            "trades_count_mismatches": len(ctrl["trades_count"]["mismatches"]),
        }
        if missing or off_grid:
            problems.append(
                f"{pair} : manquantes {_iso_list(missing)}, hors grille {_iso_list(off_grid)}"
            )
        if not d1_after["ok"] or d1_after["covered_units"] != d1_after["expected_units"]:
            problems.append(
                f"{pair} : D1 1 w préfixe {d1_after['covered_units']}/{d1_after['expected_units']}"
            )
        if ctrl["ohlcv_mismatches"] or ctrl["not_controllable"]:
            problems.append(f"{pair} : contrôle après écriture non vert")
    rows: list[dict[str, Any]] = []
    for row in derived:
        sources = source_stamps(row.timestamp)
        source_rows = [daily[row.pair][s] for s in sources if s in daily[row.pair]]
        replayed_sha = source_sha256(row.pair, source_rows)
        stored = None if row.open is None else _candle_from_row(row)
        try:
            rebuilt = aggregate_week(row.timestamp, source_rows, vwap_policy=row.vwap_policy)
        except NotReconstructibleError as exc:
            rebuilt = None
            problems.append(
                f"{row.pair} {row.timestamp.isoformat()} : sources non rejouables — {exc}"
            )
        same = (
            stored is not None
            and rebuilt is not None
            and not compare_week(stored, rebuilt)
            and stored.vwap == rebuilt.vwap
        )
        if stored is None:
            problems.append(f"{row.pair} {row.timestamp.isoformat()} : provenance sans row OHLC")
        if replayed_sha != row.source_sha256:
            problems.append(
                f"{row.pair} {row.timestamp.isoformat()} : source_sha256 rejoué différent"
            )
        if not same:
            problems.append(f"{row.pair} {row.timestamp.isoformat()} : row OHLC ≠ agrégat rejoué")
        rows.append(
            {
                "pair": row.pair,
                "week": row.timestamp.isoformat(),
                "interval": row.interval,
                "exchange": row.exchange,
                "method": row.method,
                "source_interval": row.source_interval,
                "source_stamps": list(row.source_stamps),
                "source_sha256": row.source_sha256,
                "source_sha256_replayed_equal": replayed_sha == row.source_sha256,
                "vwap_policy": row.vwap_policy,
                "script_sha256": row.script_sha256,
                "git_sha": row.git_sha,
                "created_at": row.created_at.isoformat(),
                "note": row.note,
                "ohlc": None if stored is None else stored.as_record(),
                "ohlc_equals_replayed_aggregate": same,
            }
        )
    expected = len(PAIRS) * len(EXPECTED_MISSING)
    if count != expected or len(rows) != expected:
        problems.append(f"ohlc_derived : {count} rows ({len(rows)} jointes), {expected} attendues")
    return {
        "ok": not problems,
        "problems": problems,
        "ohlc_derived_count": count,
        "pairs": pairs,
        "rows": rows,
    }


async def run_write(
    url: str,
    *,
    vwap_policy: str,
    note: str,
    provenance: Mapping[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    """Une transaction d'écriture (commit à la sortie du bloc), puis la relecture sur une connexion neuve.

    Une ``WriteRefusedError`` ou toute erreur avant le commit annule tout : rien n'est écrit. Une erreur de
    la relecture est rapportée avec ``written: True`` — les rows sont en base, la vérification ne l'est pas.
    """
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET LOCAL statement_timeout = '120s'"))
                plan = await perform_write(
                    conn,
                    load=load_write_state,
                    vwap_policy=vwap_policy,
                    note=note,
                    provenance=provenance,
                    created_at=created_at,
                )
        logger.info(
            "write_committed",
            ohlc_rows=len(plan.ohlc_rows),
            provenance_rows=len(plan.provenance_rows),
        )
        try:
            async with engine.connect() as conn:
                verification = await verify_after_write(conn)
        except Exception as exc:  # noqa: BLE001 - écrit mais non vérifié : rapporté, jamais masqué
            verification = {
                "ok": False,
                "problems": [f"relecture impossible : {type(exc).__name__}: {exc}"],
            }
    finally:
        await engine.dispose()
    return {"written": True, "plan": plan, "verification": verification}


def _plan_record(plan: WritePlan) -> dict[str, Any]:
    def row_record(row: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, datetime):
                out[key] = value.isoformat()
            elif isinstance(value, Decimal):
                out[key] = str(value)
            else:
                out[key] = value
        return out

    return {
        "control_before": plan.control,
        "d1_prefix_before": plan.d1_before,
        "coverage_evaluated_before": plan.coverage_evaluated_before,
        "ohlc_rows": [row_record(r) for r in plan.ohlc_rows],
        "provenance_rows": [row_record(r) for r in plan.provenance_rows],
    }


def render_write_markdown(report: Mapping[str, Any], *, json_name: str, json_sha256: str) -> str:
    prov = report["provenance"]
    db = report["database"]
    lines = ["# Reconstruction 1 w USDT — écriture (étape 2)", ""]
    if report["status"] == "refused":
        lines.append(f"**REFUSÉ — rien n'a été écrit** (code {report['refusal']['code']}) :")
        lines.extend(f"- {r}" for r in report["refusal"]["reasons"])
    else:
        verification = report["verification"]
        head = "ÉCRIT ET VÉRIFIÉ" if verification["ok"] else "ÉCRIT — VÉRIFICATION EN ÉCHEC"
        lines.append(
            f"**{head}** — {len(report['plan']['ohlc_rows'])} rows `market_data_ohlc` + "
            f"{len(report['plan']['provenance_rows'])} rows `ohlc_derived`, `vwap_policy = "
            f'"{report["vwap_policy"]}"`.'
        )
        lines.extend(f"- {p}" for p in verification["problems"])
    lines.extend(
        [
            "",
            f"- Généré : `{report['generated_at']}` · commande : `{' '.join(report['argv'])}`",
            f"- git `{prov['git_sha']}` (branche `{prov['branch']}`), tree suivi propre : "
            f"{prov['tracked_tree_clean']} · `{prov['script']}` sha256 `{prov['script_sha256']}`",
            f"- Base : `{db['host']}:{db['port']}/{db['database']}` · note : « {report['note']} » · "
            f"created_at `{report['created_at']}`",
            f"- Artefact : `{json_name}` sha256 `{json_sha256}`",
        ]
    )
    if report["status"] == "refused":
        lines.append("")
        return "\n".join(lines)
    plan = report["plan"]
    verification = report["verification"]
    lines.extend(
        [
            "",
            "## Contrôle (c) rejoué dans la transaction, avant les INSERT",
            "",
            "| Paire | semaines comparées | mismatches OHLCV | mismatches trades_count | non contrôlables |",
            "|---|---|---|---|---|",
        ]
    )
    for pair, c in plan["control_before"].items():
        lines.append(
            f"| {pair} | {c['weeks_compared']} | **{c['ohlcv_mismatches']}** | "
            f"{c['trades_count_mismatches']} | {c['not_controllable']} |"
        )
    lines.extend(
        [
            "",
            "## Couverture 1 w, avant / après (relue sur une connexion neuve)",
            "",
            "| Paire | D1 préfixe avant | D1 préfixe après | évaluée avant | évaluée après | manquantes après | "
            "semaines contrôlées après | mismatches OHLCV après |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for pair in PAIRS:
        before = plan["d1_prefix_before"].get(pair)
        ev_before = plan["coverage_evaluated_before"].get(pair)
        after = verification.get("pairs", {}).get(pair)
        if before is None or ev_before is None or after is None:
            lines.append(f"| {pair} | — | — | — | — | — | — | — |")
            continue
        d1a = after["d1_prefix_after"]
        eva = after["coverage_evaluated_after"]
        lines.append(
            f"| {pair} | {before['covered_units']}/{before['expected_units']} "
            f"({'passe' if before['ok'] else 'échoue'}) | {d1a['covered_units']}/{d1a['expected_units']} "
            f"({'passe' if d1a['ok'] else 'échoue'}) | {ev_before['covered_units']}/{ev_before['expected_units']} | "
            f"{eva['covered_units']}/{eva['expected_units']} | {len(after['missing_in_window'])} | "
            f"{after['weeks_compared']} | {after['ohlcv_mismatches']} |"
        )
    lines.extend(
        [
            "",
            f"## Les {len(verification.get('rows', []))} rows dérivées, relues "
            f"(`SELECT count(*) FROM ohlc_derived` = {verification.get('ohlc_derived_count')})",
            "",
            "| Paire | Semaine | open | high | low | close | volume | trades | vwap | source_sha256 | sha rejoué | "
            "= agrégat rejoué |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in verification.get("rows", []):
        o = row["ohlc"] or {}
        lines.append(
            f"| {row['pair']} | {row['week'][:10]} | {o.get('open')} | {o.get('high')} | {o.get('low')} | "
            f"{o.get('close')} | {o.get('volume')} | {o.get('trades_count')} | {o.get('vwap') or 'NULL'} | "
            f"`{row['source_sha256'][:16]}…` | {'oui' if row['source_sha256_replayed_equal'] else '**NON**'} | "
            f"{'oui' if row['ohlc_equals_replayed_aggregate'] else '**NON**'} |"
        )
    first = (verification.get("rows") or [{}])[0]
    lines.extend(
        [
            "",
            f"Provenance commune : `method = {first.get('method')}`, `source_interval = {first.get('source_interval')}`, "
            f"`vwap_policy = {first.get('vwap_policy')}`, `git_sha = {first.get('git_sha')}`, "
            f"`script_sha256 = {first.get('script_sha256')}`.",
            "",
            "## Retour arrière (non exécuté)",
            "",
            "```sql",
            "BEGIN;",
            "DELETE FROM market_data_ohlc o USING ohlc_derived d",
            " WHERE o.timestamp = d.timestamp AND o.pair = d.pair AND o.interval = d.interval",
            f"   AND o.exchange = d.exchange AND d.method = '{METHOD}';",
            f"DELETE FROM ohlc_derived WHERE method = '{METHOD}';",
            "COMMIT;",
            "-- puis, si la table doit disparaître : alembic downgrade c1ae7a1c0001",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sorties
# ---------------------------------------------------------------------------


def write_json_strict(path: Path, payload: Any) -> str:
    """JSON indenté, clés triées, **sans** ``default`` : une valeur non native lève (dette 22)."""
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _pct(ratio: float) -> str:
    return f"{ratio * 100:.1f} %"


def render_markdown(report: Mapping[str, Any], *, json_name: str, json_sha256: str) -> str:
    summary = report["summary"]
    prov = report["provenance"]
    db = report["database"]
    scope = report["scope"]
    vision = report["d_vision_probe"]
    lines: list[str] = []
    title = "# Reconstruction 1 w USDT — contrôle (étape 1, lecture seule)"
    lines.append(title)
    lines.append("")
    if vision.get("skipped"):
        lines.append("> **Probe Vision (d) : non exécutée** (`--skip-vision`).")
    elif vision["positive"]:
        found = ", ".join(f"{p['pair']} {p['week'][:10]}" for p in vision["positive"])
        lines.append(
            f"> **PROBE VISION POSITIF — {len(vision['positive'])} des 24 bougies cibles sont servies par un fichier "
            f"mensuel Vision : {found}.** Décision au gate : importer les rows réelles (la reconstruction sert "
            "alors de contrôle bit-exact) ou reconstruire. Rows telles que servies : section (d)."
        )
    else:
        extra = (
            f" ; **{len(vision['inconclusive'])} cible(s) non concluante(s)** (fichier illisible)"
            if vision["inconclusive"]
            else ""
        )
        lines.append(
            f"> **Probe Vision (d) : aucune des 24 bougies cibles n'est servie** par les "
            f"{vision['files_read']} fichiers mensuels lus ({vision['files_requested']} demandés){extra}."
        )
    lines.append("")
    if summary["ok"]:
        lines.append(
            f"**Contrôle : VERT** — cibles reconstructibles {summary['targets_reconstructible']}, "
            f"**{summary['ohlcv_mismatches']} mismatch OHLCV** sur {summary['weeks_compared']} semaines Vision "
            "comparées."
        )
    else:
        lines.append("**Contrôle : STOP** — violations :")
        lines.extend(f"- {v}" for v in summary["violations"])
    lines.append("")
    if prov.get("provisional"):
        lines.append(
            "> **PROVISOIRE** — script non committé ou tree suivi non propre (`--allow-uncommitted`)."
        )
        lines.append("")
    lines.extend(
        [
            f"- Généré : `{report['generated_at']}` · commande : `{' '.join(report['argv'])}`",
            f"- git `{prov['git_sha']}` (branche `{prov['branch']}`), tree suivi propre : "
            f"{prov['tracked_tree_clean']} · `{prov['script']}` sha256 `{prov['script_sha256']}`",
            f"- Base : `{db['host']}:{db['port']}/{db['database']}` · transaction_read_only = "
            f"`{db['transaction_read_only']}` · table `ohlc_derived` présente : "
            f"{report['ohlc_derived_table_exists']}",
            f"- Périmètre : `exchange='{scope['exchange']}'`, {', '.join(scope['pairs'])}, fenêtre "
            f"`({scope['window']['start']}, {scope['window']['end']}]`, ancrage `T = {scope['anchor']}` "
            f"(recalculé par `cc.anchor_of`), méthode `{scope['method']}`",
            f"- Artefact : `{json_name}` sha256 `{json_sha256}`",
            "",
            "## (a) Diagnostic 1 w",
            "",
            "| Paire | présentes / attendues | manquantes = brief | hors grille | périodes préfixe | "
            "périodes évaluées | D1 1 w préfixe | trou max | couverture évaluée |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for pair, data in report["pairs"].items():
        a = data["a_diagnostic"]
        d1 = a["d1_prefix"]
        ev = a["coverage_evaluated"]
        d1_txt = (
            "—"
            if d1 is None
            else f"{d1['covered_units']}/{d1['expected_units']} = {_pct(d1['ratio'])} → "
            f"{'passe' if d1['ok'] else 'échoue'}"
        )
        gap_txt = "—" if d1 is None else f"{d1['longest_gap_days']:g} j (≤ {d1['gap_max_days']:g})"
        ev_txt = "—" if ev is None else f"{ev['covered_units']}/{ev['expected_units']}"
        lines.append(
            f"| {pair} | {a['present_in_window']}/{a['expected_in_window']} | "
            f"{'oui' if a['missing_equals_brief'] else 'NON'} ({len(a['missing'])}) | {len(a['off_grid'])} | "
            f"{a['weekly_stamps_prefix']} | {a['weekly_stamps_evaluated']} | {d1_txt} | {gap_txt} | {ev_txt} |"
        )
    first = next(iter(report["pairs"].values()))["a_diagnostic"]
    lines.extend(
        [
            "",
            f"Estampilles manquantes mesurées ({report['scope']['pairs'][0]}) : "
            + ", ".join(f"`{m[:10]}`" for m in first["missing"]),
            "",
            "## (b) Disponibilité 1 d des 24 cibles",
            "",
            "| Paire | Semaine | 1 d présentes | reconstructible | open | high | low | close | volume | "
            "trades | source_sha256 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for pair, data in report["pairs"].items():
        for t in data["b_availability"]:
            if t["reconstructible"]:
                r = t["rebuilt"]
                lines.append(
                    f"| {pair} | {t['week'][:10]} | {t['present']}/7 | oui | {r['open']} | {r['high']} | "
                    f"{r['low']} | {r['close']} | {r['volume']} | {r['trades_count']} | "
                    f"`{t['source_sha256'][:16]}…` |"
                )
            else:
                lines.append(
                    f"| {pair} | {t['week'][:10]} | {t['present']}/7 | **NON** — {t['reason']} | | | | | | | |"
                )
    lines.extend(
        [
            "",
            "## (c) Contrôle d'exactitude — toutes les semaines Vision présentes de la fenêtre",
            "",
            "| Paire | semaines comparées | non contrôlables | mismatches OHLCV | trades_count comparées | "
            "mismatches trades_count | vwap stocké non NULL | vwap reconstruit non NULL | écart vwap max |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for pair, data in report["pairs"].items():
        c = data["c_control"]
        lines.append(
            f"| {pair} | {c['weeks_compared']} | {len(c['not_controllable'])} | "
            f"**{len(c['ohlcv_mismatches'])}** | {c['trades_count']['compared']} | "
            f"{len(c['trades_count']['mismatches'])} | {c['vwap']['stored_non_null']} | "
            f"{c['vwap']['rebuilt_non_null']} | {c['vwap']['max_abs_gap'] or '—'} |"
        )
    for pair, data in report["pairs"].items():
        c = data["c_control"]
        listed = c["ohlcv_mismatches"] + c["trades_count"]["mismatches"]
        if listed:
            lines.extend(
                ["", f"Mismatches {pair} (50 premiers ; liste complète dans le JSON) :", ""]
            )
            lines.append("| Semaine | colonne | Vision | reconstruit |")
            lines.append("|---|---|---|---|")
            for m in listed[:50]:
                lines.append(
                    f"| {m['week'][:10]} | {m['column']} | {m['vision']} | {m['rebuilt']} |"
                )
        if c["not_controllable"]:
            lines.extend(["", f"Semaines non contrôlables {pair} :", ""])
            lines.extend(f"- `{n['week'][:10]}` — {n['reason']}" for n in c["not_controllable"])
    vw = report["vwap"]
    lines.extend(
        [
            "",
            "### vwap",
            "",
            "Population de la colonne sur `exchange='binance'`, 1 d et 1 w, tout l'historique :",
            "",
            "| Paire | TF | rows | vwap non NULL | trades_count non NULL |",
            "|---|---|---|---|---|",
        ]
    )
    for p in vw["population_binance"]:
        tf = "1 d" if p["interval"] == SOURCE_INTERVAL else "1 w"
        lines.append(
            f"| {p['pair']} | {tf} | {p['rows']} | {p['vwap_non_null']} | {p['trades_count_non_null']} |"
        )
    scan = vw["readers_scan"]
    lines.extend(
        [
            "",
            f"Occurrences du jeton `vwap` sur le chemin backtest / C3 ({len(scan['hits'])}) — chemins balayés : "
            + ", ".join(f"`{p}`" for p in scan["paths"])
            + (
                " ; absents : " + ", ".join(f"`{p}`" for p in scan["absent_paths"])
                if scan["absent_paths"]
                else ""
            ),
            "",
        ]
    )
    lines.extend(f"- `{h['file']}:{h['line']}` — `{h['text']}`" for h in scan["hits"])
    lines.extend(
        [
            "",
            f'**Proposition (non décidée) : `vwap_policy = "{vw["proposal"]}"`** — {vw["reason"]} '
            f"(vwap non NULL : {vw['usdt_daily_vwap_non_null']} rows 1 d, {vw['usdt_weekly_vwap_non_null']} rows "
            "1 w sur les séries USDT).",
            "",
            "## (d) Probe Vision — fichiers mensuels 1 w des cibles",
            "",
        ]
    )
    if vision.get("skipped"):
        lines.append("Non exécutée (`--skip-vision`).")
    else:
        lines.append(
            "| Paire | Semaine | Fichier | HTTP | Last-Modified | bougies servies | contient S |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for t in vision["targets"]:
            for f in t["files"]:
                served = "—" if f["stamps_served"] is None else str(len(f["stamps_served"]))
                contains = {True: "**OUI**", False: "non", None: "illisible"}[f["contains_target"]]
                lines.append(
                    f"| {t['pair']} | {t['week'][:10]} | `{f['url'].rsplit('/', 1)[-1]}` | {f['status']} | "
                    f"{f['last_modified'] or '—'} | {served} | {contains} |"
                )
        absent_both = sum(
            1 for t in vision["targets"] if all(f["contains_target"] is False for f in t["files"])
        )
        lines.append("")
        lines.append(
            f"Cibles absentes des deux fichiers (mois d'ouverture et mois de clôture) : **{absent_both}/"
            f"{len(vision['targets'])}**."
        )
        straddlers: dict[str, list[str]] = {}
        for t in vision["targets"]:
            for f in t["files"]:
                if f["straddling_served"]:
                    straddlers[f["url"].rsplit("/", 1)[-1]] = f["straddling_served"]
        lines.append(
            "Semaines à cheval **servies** par ces fichiers : "
            + (
                " ; ".join(
                    f"`{name}` → " + ", ".join(f"`{s[:10]}`" for s in stamps)
                    for name, stamps in sorted(straddlers.items())
                )
                if straddlers
                else "aucune"
            )
            + "."
        )
        for t in vision["targets"]:
            for f in t["files"]:
                if f["served_row"] is not None:
                    lines.append("")
                    lines.append(
                        f"Row servie — {t['pair']} {t['week'][:10]}, `{f['url'].rsplit('/', 1)[-1]}` : "
                        f"`{','.join(f['served_row'])}`"
                    )
    e = report["e_idempotence"]
    lines.extend(
        [
            "",
            "## (e) Idempotence de l'import Vision",
            "",
            f"`{e['importer']}` (sha256 `{e['importer_sha256']}`), lignes de la clause de conflit :",
            "",
        ]
    )
    lines.extend(f"- `:{c['line']}` — `{c['text']}`" for c in e["clause_lines"])
    lines.extend(
        [
            "",
            "Conséquence : une reprise de l'import (`ON CONFLICT DO NOTHING` sur la PK `(timestamp, pair, interval, "
            "exchange)`) **n'écrase jamais** une row dérivée : une vraie row Vision servie plus tard pour une des "
            "8 estampilles serait ignorée en silence. La remplacer exige une action explicite : `DELETE` de la row "
            "OHLC **et** de sa row de provenance `ohlc_derived`, puis réimport. La reprise prévue (1 w 2026-07/08) "
            "est hors de la fenêtre des cibles.",
            "",
            "## TimescaleDB — chunks des cibles",
            "",
            f"Compression activée sur `market_data_ohlc` : `{report['timescale']['compression_enabled']}`.",
            "",
            "| Semaine | chunk | intervalle | compressé |",
            "|---|---|---|---|",
        ]
    )
    for entry in report["timescale"]["target_chunks"]:
        for c in entry["chunks"] or [
            {"chunk": "—", "range_start": "", "range_end": "", "is_compressed": None}
        ]:
            lines.append(
                f"| {entry['week'][:10]} | `{c['chunk']}` | {c['range_start'][:10]} → {c['range_end'][:10]} | "
                f"{c['is_compressed']} |"
            )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_iso(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require_utc(stamp, what="--generated-at")
    return stamp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconstruction des 8 estampilles 1 w USDT depuis le 1 d — check (lecture seule) ou write."
    )
    parser.add_argument("command", nargs="?", default="check", choices=("check", "write"))
    parser.add_argument(
        "--output", type=Path, required=True, help="Artefact JSON (check_report / write_report)."
    )
    parser.add_argument("--markdown", type=Path, default=None, help="Rendu Markdown.")
    parser.add_argument(
        "--skip-vision", action="store_true", help="check : ne pas interroger Binance Vision (d)."
    )
    parser.add_argument(
        "--allow-uncommitted",
        action="store_true",
        help="check, développement seulement : accepte un script non committé, en-tête PROVISOIRE.",
    )
    parser.add_argument("--generated-at", type=_parse_iso, default=None)
    parser.add_argument(
        "--vwap-policy",
        choices=VWAP_POLICIES,
        default=None,
        help="write : politique vwap, explicite (décision humaine).",
    )
    parser.add_argument("--note", default=None, help="write : référence de l'entrée RESEARCH_LOG.")
    args = parser.parse_args(argv)
    if args.command == "write":
        if args.vwap_policy is None or args.note is None:
            parser.error("write exige --vwap-policy et --note")
        if args.allow_uncommitted:
            parser.error("write refuse --allow-uncommitted : le script écrit doit être committé")
    return args


def _database(url: str) -> dict[str, Any]:
    parsed = make_url(url)
    return {"host": parsed.host, "port": parsed.port, "database": parsed.database}


def main_write(
    args: argparse.Namespace, provenance: dict[str, Any], url: str, argv: Sequence[str]
) -> int:
    created_at = datetime.now(UTC)
    report: dict[str, Any] = {
        "artifact": "reconstruct_1w.write",
        "generated_at": (args.generated_at or created_at).isoformat(),
        "argv": list(argv),
        "provenance": provenance,
        "database": _database(url),
        "vwap_policy": args.vwap_policy,
        "note": args.note,
        "created_at": created_at.isoformat(),
    }
    try:
        outcome = asyncio.run(
            run_write(
                url,
                vwap_policy=args.vwap_policy,
                note=args.note,
                provenance=provenance,
                created_at=created_at,
            )
        )
    except WriteRefusedError as exc:
        logger.error("write_refused", code=exc.code, reasons=exc.reasons)
        if exc.code == 2:
            return 2
        report.update({"status": "refused", "refusal": {"code": exc.code, "reasons": exc.reasons}})
        code = 1
    except Exception as exc:  # noqa: BLE001 - erreur avant commit : transaction annulée, rien d'écrit
        logger.error("write_failed_rolled_back", error=f"{type(exc).__name__}: {exc}")
        return 2
    else:
        verification = outcome["verification"]
        report.update(
            {
                "status": "written",
                "plan": _plan_record(outcome["plan"]),
                "verification": verification,
            }
        )
        code = 0 if verification["ok"] else 1
    digest = write_json_strict(args.output, report)
    logger.info("write_report_json", path=str(args.output), sha256=digest)
    if args.markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(
            render_write_markdown(report, json_name=args.output.name, json_sha256=digest),
            encoding="utf-8",
        )
        logger.info("write_report_markdown", path=str(args.markdown))
    logger.info(
        "write_summary",
        status=report["status"],
        verified=report.get("verification", {}).get("ok"),
        problems=report.get("verification", {}).get("problems"),
    )
    return code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    anchor = cc.anchor_of(WINDOW_START, WINDOW_END)
    if anchor != ANCHOR_DECLARED:
        logger.error(
            "anchor_mismatch", recomputed=anchor.isoformat(), declared=ANCHOR_DECLARED.isoformat()
        )
        return 2
    provenance = git_provenance()
    committed = provenance["script_tracked"] and provenance["tracked_tree_clean"]
    if not committed and not args.allow_uncommitted:
        logger.error(
            "uncommitted_tree",
            script_tracked=provenance["script_tracked"],
            tracked_tree_clean=provenance["tracked_tree_clean"],
            hint="committer d'abord : le git sha de l'en-tête doit être réel",
        )
        return 2
    provenance["provisional"] = not committed
    # .env chargé ici, jamais à l'import (règle B4.2) ; jamais Settings() (piège 5432).
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        logger.error("database_url_missing")
        return 2
    run_argv = sys.argv if argv is None else ["reconstruct_1w.py", *argv]
    if args.command == "write":
        return main_write(args, provenance, url, run_argv)
    database = _database(url)
    try:
        collected = asyncio.run(collect(url))
    except Exception as exc:  # noqa: BLE001 - base injoignable ou contrat de lecture violé = code 2
        logger.error("database_read_failed", error=f"{type(exc).__name__}: {exc}")
        return 2
    database["transaction_read_only"] = collected["read_only"]
    vision = {"skipped": True} if args.skip_vision else probe_vision(PAIRS, EXPECTED_MISSING)
    report = build_report(
        collected,
        vision=vision,
        provenance=provenance,
        database=database,
        generated_at=args.generated_at or datetime.now(UTC),
        argv=sys.argv if argv is None else ["reconstruct_1w.py", *argv],
    )
    digest = write_json_strict(args.output, report)
    logger.info("check_report_json", path=str(args.output), sha256=digest)
    if args.markdown is not None:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(
            render_markdown(report, json_name=args.output.name, json_sha256=digest),
            encoding="utf-8",
        )
        logger.info("check_report_markdown", path=str(args.markdown))
    summary = report["summary"]
    logger.info(
        "check_summary",
        ok=summary["ok"],
        reconstructible=summary["targets_reconstructible"],
        weeks_compared=summary["weeks_compared"],
        ohlcv_mismatches=summary["ohlcv_mismatches"],
        vision_positive=len(summary["vision_positive"]),
        violations=summary["violations"],
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
