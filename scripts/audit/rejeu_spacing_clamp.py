"""Rejeu diagnostic grid — mesure directe du clamp d'espacement (pré-spec § B).

Hors simulation : on recharge la série 4 h de chaque paire (``exchange='binance'``,
``interval=240``) depuis une amorce exclue des comptes, on alimente
``krakenbot.indicators.atr.ATRIndicator(14)`` bougie par bougie et, pour chacun des 16 couples
(``min_spacing_pct``, ``atr_multiplier``) de ``p7_grids.GRID_ATR_GRID``, on classe chaque clôture
de la fenêtre en ``at_floor`` / ``interior`` / ``at_ceiling`` selon
``spacing = max(plancher, min(0.05, ATR × multiplicateur / close))`` — la formule de
``GrokGridATRAdaptiveV4._calculate_spacing``, comparaisons en Decimal strictes. S'y ajoute la
mesure annexe pertinente pour SOL : la fraction des cellules où le pas de quantification des
niveaux (0,1 USD) pèse au moins 10 % de ``spacing × close``.

**Étiquette obligatoire (§ B.3)** : c'est une mesure **distributionnelle, pas un rejeu**.
L'amorçage diffère de celui du moteur et **aucune des deux paires ne reproduit l'état ATR réalisé
du moteur**. Le clamp ne déplace aucun verdict, dans aucune direction : si la série ne peut pas
être chargée, l'artefact porte ``producible: false`` avec sa raison et le script sort en 0.

Read-only, DB en lecture seule.

Usage::

    poetry run python scripts/audit/rejeu_spacing_clamp.py \\
        --output results/rejeu_grid_20260919/clamp.json \\
        --markdown results/rejeu_grid_20260919/clamp.md

Exit codes: 0 ok, 1 violation, 2 usage or input error.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import p7_grids  # noqa: E402
import rejeu_common as rc  # noqa: E402

from krakenbot.config.settings import Settings  # noqa: E402
from krakenbot.core.database import DatabaseManager  # noqa: E402
from krakenbot.indicators.atr import ATRIndicator  # noqa: E402
from krakenbot.models.market_data import OHLCData  # noqa: E402

# ---------------------------------------------------------------------------
# Frozen by the pre-specification (§ B.1 / § B.3) — not carried by rejeu_common
# ---------------------------------------------------------------------------

#: 4 h series, the timeframe the ATR that fixes the spacing lives on (§ B.1).
INTERVAL_MINUTES = 240

#: Lead-in start of § B.1: candles stamped in ``(LEAD_IN_START, WINDOW_START]`` feed the ATR
#: and are **excluded from every count**.
LEAD_IN_START = datetime(2023, 2, 1, tzinfo=UTC)

#: Verbatim label of § B.3, written in the artefact and printed with every table.
LABEL = (
    "mesure distributionnelle, pas un rejeu ; aucune paire ne reproduit l'état ATR "
    "réalisé du moteur"
)

#: The two 0.1 of the side measure are **different things** and get different symbols:
#: the level quantisation step is an absolute price step in USD
#: (``level_price.quantize(Decimal("0.1"))`` in the strategy)...
LEVEL_QUANTIZATION_STEP = Decimal("0.1")
#: ...and this one is the 10 % share of ``spacing × close`` the step is compared to.
QUANTIZATION_MIN_SHARE = Decimal("0.1")

PRESPEC_RELPATH = "docs/rejeu_grid_prespec.md"
DEFAULT_OUTPUT = Path("results/rejeu_grid_20260919/clamp.json")

AT_FLOOR = "at_floor"
INTERIOR = "interior"
AT_CEILING = "at_ceiling"
CLASSES: tuple[str, ...] = (AT_FLOOR, INTERIOR, AT_CEILING)

#: The 16 couples of § B.1, in the order of ``GRID_ATR_GRID`` (never restated as literals).
COUPLES: tuple[tuple[Decimal, Decimal], ...] = tuple(
    (Decimal(str(floor)), Decimal(str(multiplier)))
    for floor in p7_grids.GRID_ATR_GRID["min_spacing_pct"]
    for multiplier in p7_grids.GRID_ATR_GRID["atr_multiplier"]
)

#: One 4 h candle: ``(timestamp, high, low, close)``, all Decimal, timestamp tz-aware UTC.
Row = tuple[datetime, Decimal, Decimal, Decimal]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def prespec_block(root: Path = rc.PROJECT_ROOT) -> dict[str, str]:
    """``{path, sha256}`` of the frozen pre-specification, carried by every artefact."""
    path = Path(root) / PRESPEC_RELPATH
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    return {"path": PRESPEC_RELPATH, "sha256": digest}


def quarter_label(timestamp: datetime, interval_minutes: int = INTERVAL_MINUTES) -> str:
    """Calendar quarter of the period a candle **covers**, not of its stamp.

    Rows are end-stamped (``t`` covers ``(t − interval, t]``), so the quarter is read on
    ``t − interval``: the candle stamped ``2026-04-01T00:00Z`` is the last one of ``2026Q1``,
    which is what makes the window span exactly the twelve quarters ``2023Q2 … 2026Q1``.
    """
    start = timestamp - timedelta(minutes=interval_minutes)
    return f"{start.year}Q{(start.month - 1) // 3 + 1}"


def classify(raw: Decimal, floor: Decimal, ceiling: Decimal) -> str:
    """Where ``max(floor, min(ceiling, raw))`` lands, with the § B.2 binding rules.

    The ceiling binds iff ``ATR/close >= ceiling / m`` and the floor iff
    ``ATR/close <= floor / m`` — both inclusive, both evaluated on ``raw = ATR × m / close``.
    With the frozen grid (floors 1,5 … 3,0 % against a 5 % ceiling) the two are exclusive;
    should a floor ever exceed the ceiling, the ceiling is reported, as the formula does.
    """
    if raw >= ceiling:
        return AT_CEILING
    if raw <= floor:
        return AT_FLOOR
    return INTERIOR


def _shares(counts: Mapping[str, int], total: int) -> dict[str, float]:
    if total <= 0:
        return dict.fromkeys(CLASSES, 0.0)
    return {name: counts.get(name, 0) / total for name in CLASSES}


def measure_pair(
    rows: Sequence[Row],
    *,
    window_start: datetime = rc.WINDOW_START,
    window_end: datetime = rc.WINDOW_END,
    couples: Sequence[tuple[Decimal, Decimal]] = COUPLES,
    atr_period: int = rc.ATR_PERIOD,
    max_spacing_pct: Decimal = rc.MAX_SPACING_PCT,
    interval_minutes: int = INTERVAL_MINUTES,
) -> dict[str, Any]:
    """Classify every in-window close of one pair, for each couple. **Pure.**

    ``rows`` must be strictly ascending and cover the lead-in: candles stamped ``<= start`` or
    ``> end`` feed the ATR but are counted nowhere (the engine bound convention, § contract).
    A close whose ATR is not ready yet is skipped as well — with the frozen 2023-02-01 lead-in
    the indicator is ready ~360 candles before the window opens, so this never fires in
    production; it is the guard, not a rule. A non-positive close takes the strategy's own
    branch (``_calculate_spacing`` returns ``min_spacing_pct`` when ``price <= 0``), i.e.
    ``at_floor``.

    Returns the frozen per-pair block: ``{n_closes, couples, quantization_share}``. A quarter
    with no in-window close is **absent** from ``by_quarter`` rather than carrying a 0/0 share.
    """
    atr = ATRIndicator(period=atr_period)
    totals: list[Counter[str]] = [Counter() for _ in couples]
    by_quarter: list[dict[str, Counter[str]]] = [{} for _ in couples]
    quarters: set[str] = set()
    n_closes = 0
    quantization_hits = 0
    previous: datetime | None = None

    for timestamp, high, low, close in rows:
        if previous is not None and timestamp <= previous:
            raise ValueError(f"rows must be strictly ascending: {timestamp} after {previous}")
        previous = timestamp
        value = atr.update(high, low, close)
        if timestamp <= window_start or timestamp > window_end or value is None:
            continue
        n_closes += 1
        quarter = quarter_label(timestamp, interval_minutes)
        quarters.add(quarter)
        for index, (floor, multiplier) in enumerate(couples):
            if close <= 0:
                name, spacing = AT_FLOOR, floor
            else:
                raw = value * multiplier / close
                name = classify(raw, floor, max_spacing_pct)
                spacing = max(floor, min(max_spacing_pct, raw))
            totals[index][name] += 1
            by_quarter[index].setdefault(quarter, Counter())[name] += 1
            if LEVEL_QUANTIZATION_STEP >= QUANTIZATION_MIN_SHARE * spacing * close:
                quantization_hits += 1

    cells = n_closes * len(couples)
    return {
        "n_closes": n_closes,
        "couples": [
            {
                "min_spacing_pct": float(floor),
                "atr_multiplier": float(multiplier),
                **_shares(totals[index], n_closes),
                "by_quarter": {
                    quarter: {
                        "n": sum(by_quarter[index][quarter].values()),
                        **_shares(
                            by_quarter[index][quarter],
                            sum(by_quarter[index][quarter].values()),
                        ),
                    }
                    for quarter in sorted(quarters)
                },
            }
            for index, (floor, multiplier) in enumerate(couples)
        ],
        "quantization_share": (quantization_hits / cells) if cells else 0.0,
    }


def build_payload(
    series: Mapping[str, Sequence[Row]],
    *,
    now: datetime,
    reason: str | None = None,
    pairs: Sequence[str] = rc.PAIRS,
    prespec: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The frozen ``clamp.json`` payload. ``reason`` carries a loader failure, if any."""
    problems: list[str] = [] if reason is None else [reason]
    measured: dict[str, Any] = {}
    for pair in pairs:
        rows = series.get(pair)
        if rows is None:
            problems.append(f"{pair}: série 4h non chargée")
            continue
        block = measure_pair(rows)
        measured[pair] = block
        if block["n_closes"] == 0:
            problems.append(f"{pair}: aucune clôture 4h dans la fenêtre")
    producible = not problems
    return {
        "generated_at": now.astimezone(UTC).isoformat(),
        "base_sha": rc.BASE_SHA,
        "prespec": dict(prespec) if prespec is not None else prespec_block(),
        "producible": producible,
        "reason": None if producible else " ; ".join(problems),
        "label": LABEL,
        "atr_period": rc.ATR_PERIOD,
        "max_spacing_pct": float(rc.MAX_SPACING_PCT),
        "lead_in_start": LEAD_IN_START.isoformat(),
        "pairs": measured,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _pct(value: Decimal) -> str:
    return f"{float(value) * 100:.4f} %"


def _thresholds_table() -> list[str]:
    """The binding bounds of § B.2, written in advance and independent of any data."""
    lines = [
        "## Bornes de liaison (§ B.2, écrites d'avance)",
        "",
        "| plancher | m | plafond mord ssi ATR/close >= | plancher mord ssi ATR/close <= |",
        "|---|---|---|---|",
    ]
    for floor, multiplier in COUPLES:
        lines.append(
            f"| {_pct(floor)} | {float(multiplier)} | "
            f"{_pct(rc.MAX_SPACING_PCT / multiplier)} | {_pct(floor / multiplier)} |"
        )
    lines.append("")
    return lines


def _quarter_table(block: Mapping[str, Any], quarters: Sequence[str], name: str) -> list[str]:
    lines = [
        f"### {name} par trimestre",
        "",
        "| plancher | m | " + " | ".join(quarters) + " |",
        "|---|---|" + "---|" * len(quarters),
    ]
    for couple in block["couples"]:
        cells = []
        for quarter in quarters:
            entry = couple["by_quarter"].get(quarter)
            cells.append("—" if entry is None else f"{entry[name]:.4f}")
        lines.append(
            f"| {couple['min_spacing_pct'] * 100:.1f} % | {couple['atr_multiplier']} | "
            + " | ".join(cells)
            + " |"
        )
    lines.append("")
    return lines


def render_markdown(payload: Mapping[str, Any]) -> str:
    """Markdown rendering of the artefact — the label first, always."""
    lines: list[str] = [
        "# Rejeu diagnostic grid — § B, mesure directe du clamp d'espacement",
        "",
        f"**{payload['label']}**",
        "",
        f"generated_at `{payload['generated_at']}` · base_sha `{payload['base_sha'][:16]}` · "
        f"prespec `{payload['prespec']['sha256'][:16]}`",
        "",
        f"ATR({payload['atr_period']}) sur les clôtures 4 h, amorce depuis "
        f"`{payload['lead_in_start']}` (exclue des comptes), fenêtre "
        f"`{rc.WINDOW_START.isoformat()}` → `{rc.WINDOW_END.isoformat()}`, plafond "
        f"{payload['max_spacing_pct']}, {len(COUPLES)} couples.",
        "",
        "`interior = 1 − at_floor − at_ceiling` ; un trimestre sans clôture 4 h est absent de la "
        "table (pas de part sur un dénominateur vide).",
        "",
    ]
    if not payload["producible"]:
        lines += [f"**Non productible** : {payload['reason']}", ""]
    lines += _thresholds_table()
    for pair, block in sorted(payload["pairs"].items()):
        quarters = sorted({q for couple in block["couples"] for q in couple["by_quarter"]})
        lines += [
            f"## {pair}",
            "",
            f"{block['n_closes']} clôtures 4 h comptées · quantization_share "
            f"{block['quantization_share']:.4f} (pas {LEVEL_QUANTIZATION_STEP} USD >= "
            f"{QUANTIZATION_MIN_SHARE} × spacing × close, sur les "
            f"{block['n_closes'] * len(COUPLES)} cellules)",
            "",
            "| plancher | m | at_floor | interior | at_ceiling |",
            "|---|---|---|---|---|",
        ]
        for couple in block["couples"]:
            lines.append(
                f"| {couple['min_spacing_pct'] * 100:.1f} % | {couple['atr_multiplier']} | "
                f"{couple[AT_FLOOR]:.4f} | {couple[INTERIOR]:.4f} | {couple[AT_CEILING]:.4f} |"
            )
        lines.append("")
        if quarters:
            lines += _quarter_table(block, quarters, AT_CEILING)
            lines += _quarter_table(block, quarters, AT_FLOOR)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# DB (read-only)
# ---------------------------------------------------------------------------


def _utc(timestamp: datetime) -> datetime:
    """Every stamp is UTC; a naive one out of the driver is read as UTC, never shifted."""
    return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)


async def _load_all(
    pairs: Sequence[str],
    lead_in_start: datetime,
    window_end: datetime,
    interval_minutes: int,
) -> dict[str, list[Row]]:
    settings = Settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    try:
        out: dict[str, list[Row]] = {}
        async with db_manager.read_session() as session:
            for pair in pairs:
                stmt = (
                    select(OHLCData)
                    .where(OHLCData.pair == pair)
                    .where(OHLCData.interval == interval_minutes)
                    .where(OHLCData.exchange == rc.EXCHANGE)
                    .where(OHLCData.timestamp > lead_in_start)
                    .where(OHLCData.timestamp <= window_end)
                    .order_by(OHLCData.timestamp.asc())
                )
                rows = list((await session.execute(stmt)).scalars().all())
                out[pair] = [
                    (
                        _utc(row.timestamp),
                        Decimal(str(row.high)),
                        Decimal(str(row.low)),
                        Decimal(str(row.close)),
                    )
                    for row in rows
                ]
        return out
    finally:
        await db_manager.close_db()


def collect_series(
    pairs: Sequence[str] = rc.PAIRS,
    *,
    lead_in_start: datetime = LEAD_IN_START,
    window_end: datetime = rc.WINDOW_END,
    interval_minutes: int = INTERVAL_MINUTES,
) -> tuple[dict[str, list[Row]], str | None]:
    """Load the 4 h series of every pair. A failure is a reason, never an exception: the clamp
    moves no verdict, so an unavailable DB yields ``producible: false`` and exit 0."""
    try:
        series = asyncio.run(_load_all(pairs, lead_in_start, window_end, interval_minutes))
    except Exception as exc:  # noqa: BLE001 - reported as the artefact's reason
        return {}, f"série 4h non chargeable ({type(exc).__name__}: {exc})"
    return series, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_now(text: str | None) -> datetime:
    if text is None:
        return datetime.now(UTC)
    stamp = datetime.fromisoformat(text)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--now", default=None, help="ISO UTC stamp of generated_at (testable)")
    args = parser.parse_args(argv)

    try:
        now = _parse_now(args.now)
    except ValueError as exc:
        print(f"--now: {exc}", file=sys.stderr)
        return 2

    load_dotenv(_ROOT / ".env")
    series, reason = collect_series()
    payload = build_payload(series, now=now, reason=reason)
    digest = rc.write_json(args.output, payload)
    text = render_markdown(payload)
    print(text)
    print(f"{args.output} sha256 {digest}")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(text, encoding="utf-8")
    if not payload["producible"]:
        print(f"clamp non productible : {payload['reason']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
