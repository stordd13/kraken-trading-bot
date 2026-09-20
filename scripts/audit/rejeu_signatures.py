"""Rejeu diagnostic grid — classes d'indiscernabilité sur les 96 configs (§ A).

Groups the campaign entries by equality of their **exported outputs**: the three metric dicts,
the complete daily equity curves, the ``liquidation`` block minus the two fields that say
nothing about the run's behaviour, and the rejection counters (§ A.2). Two tiers are reported,
``sig_exact`` — the number of record — and ``sig_tol``; between two neighbouring classes the
JSON path of the first difference is printed, so a reader sees WHAT separates them. The
retroactive B4 reading is limited to the fields ``results/B4_P7_phase1_cross_validate.json``
kept and its class count is compared to the pre-registered reference (BTC 45, SOL 48): the
agreement is **reported**, never asserted — a disagreement is a constat, not a failure.

Descriptive only: § G.5 freezes that the class count enters no verdict branch, and the caveat
of § A.4 is printed verbatim and carried in the artifact.

Pure, read-only.

Usage::

    poetry run python scripts/audit/rejeu_signatures.py \\
        results/rejeu_grid_20260919/P7_phase1_grid.json \\
        --b4 results/B4_P7_phase1_cross_validate.json \\
        --output results/rejeu_grid_20260919/signatures.json \\
        --markdown results/rejeu_grid_20260919/signatures.md

Exit codes: 0 ok, 1 violation, 2 usage or input error.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import rejeu_common as rc  # noqa: E402

#: Section A.2: the two ``liquidation`` fields excluded from the signature.
EXCLUDED_LIQUIDATION_KEYS: tuple[str, ...] = ("timestamp", "reference_price")

#: Section A.2, verbatim in the artifact so a reader never has to guess the perimeter.
FIELDS_INCLUDED: tuple[str, ...] = (
    "train (the 24 metric keys)",
    "test (the 24 metric keys)",
    "all (the 24 metric keys)",
    "equity_daily[seg].values (complete, all three segments)",
    "liquidation[seg] minus timestamp and reference_price",
    "rejections[seg].by_cause",
)
FIELDS_EXCLUDED: tuple[str, ...] = (
    "params (label of the config, not its output)",
    "effective_params (label of the config, not its output)",
    "period (identical by construction)",
    "warmup (identical per pair, cf. I-A.8)",
)

#: Section A.3, pre-registered reference of the retroactive B4 reading, segment ``all``.
B4_REFERENCE: dict[str, int] = {"BTC/USDC": 45, "SOL/USDC": 48}

PRESPEC_PATH = "docs/rejeu_grid_prespec.md"
DEFAULT_OUTPUT = _ROOT / "results" / "rejeu_grid_20260919" / "signatures.json"


class PayloadError(ValueError):
    """An entry cannot yield a signature payload (missing block, failed job, NaN/Inf)."""


# ---------------------------------------------------------------------------
# Non-finite guard
# ---------------------------------------------------------------------------


def _nonfinite_path(value: Any, path: str = "$") -> str | None:
    """JSON path of the first NaN/Inf leaf, or None.

    ``rc.canon`` maps a float to ``repr(float(x))`` **before** ``json.dumps`` runs, so a NaN
    reaches the dump as the string ``"nan"`` and ``allow_nan=False`` never fires: NaN and Inf
    would land in two different classes, silently. Section A.1 requires the opposite ("tout
    NaN/Inf lève"), so the guard is explicit here. Decimal-valued strings are checked too
    (``"NaN"`` parses as a Decimal).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else path
    if isinstance(value, Decimal):
        return None if value.is_finite() else path
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError):
            return None
        return None if parsed.is_finite() else path
    if isinstance(value, dict):
        for key in sorted(value):
            found = _nonfinite_path(value[key], f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _nonfinite_path(item, f"{path}[{index}]")
            if found is not None:
                return found
        return None
    return None


def check_finite(payload: Any, label: str = "payload") -> None:
    """Raise ``PayloadError`` on any NaN/Inf in the payload (§ A.1), never split silently."""
    found = _nonfinite_path(payload)
    if found is not None:
        raise PayloadError(f"{label}: non-finite value at {found} (prespec A.1)")


# ---------------------------------------------------------------------------
# Signature payloads (section A.2 / A.3)
# ---------------------------------------------------------------------------


def _require_dict(entry: dict[str, Any], key: str, block: str, segment: str) -> dict[str, Any]:
    value = (entry.get(block) or {}).get(segment)
    if not isinstance(value, dict):
        raise PayloadError(f"{key}: {block}[{segment}] missing or not an object")
    return value


def _reject_failed_job(entry: dict[str, Any], key: str) -> None:
    if "error" in entry:
        raise PayloadError(f"{key}: failed job (error={entry.get('error')!r})")


def signature_payload(entry: dict[str, Any], key: str) -> dict[str, Any]:
    """Section A.2 payload of one campaign entry, exactly as frozen."""
    _reject_failed_job(entry, key)
    payload: dict[str, Any] = {
        "metrics": {},
        "equity_daily": {},
        "liquidation": {},
        "rejections": {},
    }
    for segment in rc.SEGMENTS:
        metrics = entry.get(segment)
        if not isinstance(metrics, dict):
            raise PayloadError(f"{key}: metrics segment {segment!r} missing or not an object")
        payload["metrics"][segment] = metrics
        curve = _require_dict(entry, key, "equity_daily", segment)
        values = curve.get("values")
        if not isinstance(values, list):
            raise PayloadError(f"{key}: equity_daily[{segment}].values missing or not a list")
        payload["equity_daily"][segment] = list(values)
        liquidation = _require_dict(entry, key, "liquidation", segment)
        payload["liquidation"][segment] = {
            name: value
            for name, value in liquidation.items()
            if name not in EXCLUDED_LIQUIDATION_KEYS
        }
        rejections = _require_dict(entry, key, "rejections", segment)
        by_cause = rejections.get("by_cause")
        if not isinstance(by_cause, dict):
            raise PayloadError(f"{key}: rejections[{segment}].by_cause missing or not an object")
        payload["rejections"][segment] = by_cause
    check_finite(payload, key)
    return payload


def b4_payload(entry: dict[str, Any], key: str) -> dict[str, Any]:
    """Section A.3 payload: the A.2 fields the pre-C1/C2 B4 file actually kept.

    ``equity_daily`` and ``rejections`` do not exist in that file; ``params`` is kept by the
    file but stays out of the signature (A.2 excludes it as a label of the config).
    """
    _reject_failed_job(entry, key)
    payload: dict[str, Any] = {"metrics": {}, "liquidation": {}}
    for segment in rc.SEGMENTS:
        metrics = entry.get(segment)
        if not isinstance(metrics, dict):
            raise PayloadError(f"{key}: metrics segment {segment!r} missing or not an object")
        payload["metrics"][segment] = metrics
        liquidation = _require_dict(entry, key, "liquidation", segment)
        payload["liquidation"][segment] = {
            name: value
            for name, value in liquidation.items()
            if name not in EXCLUDED_LIQUIDATION_KEYS
        }
    check_finite(payload, key)
    return payload


def signatures_of(payload: Any, label: str = "payload") -> tuple[str, str]:
    """``(sig_exact, sig_tolerant)`` of a payload, NaN/Inf guarded first."""
    check_finite(payload, label)
    return rc.sig(payload), rc.sig_tolerant(payload)


# ---------------------------------------------------------------------------
# Grouping and classes
# ---------------------------------------------------------------------------


def group_by_pair(results: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Entries of the frozen strategy on the two frozen pairs, plus the keys left out."""
    grouped: dict[str, dict[str, Any]] = {pair: {} for pair in rc.PAIRS}
    outside: list[str] = []
    for key in sorted(results):
        entry = results[key]
        if not isinstance(entry, dict):
            outside.append(key)
            continue
        pair = entry.get("pair")
        if entry.get("strategy") != rc.STRATEGY or pair not in grouped:
            outside.append(key)
            continue
        grouped[pair][key] = entry
    return grouped, outside


def classes_of(signatures: dict[str, str]) -> list[dict[str, Any]]:
    """Equality classes, members sorted, classes ordered by their smallest member key."""
    buckets: dict[str, list[str]] = {}
    for key, value in signatures.items():
        buckets.setdefault(value, []).append(key)
    classes = [{"sig": value, "members": sorted(keys)} for value, keys in buckets.items()]
    classes.sort(key=lambda item: item["members"][0])
    return classes


def adjacent_first_differences(
    classes: list[dict[str, Any]], payloads: dict[str, Any]
) -> list[dict[str, str]]:
    """First-difference JSON path between the representatives of two neighbouring classes.

    The comparison runs on the **canonical** images, which is what the signature hashes: a
    ``"0"`` against ``"0E-30"`` is not a difference here, by construction (§ A.1).
    """
    out: list[dict[str, str]] = []
    for left, right in zip(classes, classes[1:], strict=False):
        a, b = left["members"][0], right["members"][0]
        path = rc.first_difference(rc.canon(payloads[a]), rc.canon(payloads[b]))
        if path is None:
            raise PayloadError(
                f"{a} vs {b}: signatures differ but the canonical forms compare equal"
            )
        out.append({"a": a, "b": b, "path": path})
    return out


def pair_block(entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The per-pair block of ``signatures.json`` for one pair of the campaign."""
    payloads = {key: signature_payload(entry, key) for key, entry in entries.items()}
    exact: dict[str, str] = {}
    tolerant: dict[str, str] = {}
    for key, payload in payloads.items():
        exact[key], tolerant[key] = signatures_of(payload, key)
    classes_exact = classes_of(exact)
    classes_tolerant = classes_of(tolerant)
    return {
        "n_configs": len(entries),
        "n_classes_exact": len(classes_exact),
        "n_classes_tolerant": len(classes_tolerant),
        "classes_exact": classes_exact,
        "classes_tolerant": classes_tolerant,
        "first_differences": adjacent_first_differences(classes_exact, payloads),
    }


def b4_block(results: dict[str, Any] | None, file_label: str | None) -> dict[str, Any]:
    """Section A.3 retroactive reading. ``results is None`` records that it was not read."""
    block: dict[str, Any] = {
        "file": file_label,
        "reference": dict(B4_REFERENCE),
        "pairs": {},
    }
    if results is None:
        return block
    grouped, _ = group_by_pair(results)
    for pair, entries in grouped.items():
        signatures = {
            key: signatures_of(b4_payload(entry, key), key)[0] for key, entry in entries.items()
        }
        block["pairs"][pair] = {
            "n_configs": len(entries),
            "n_classes_exact": len(set(signatures.values())),
        }
    return block


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


def _sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(_ROOT).as_posix()
    except ValueError:
        return str(path)


def build_report(
    results: dict[str, Any],
    *,
    now: datetime,
    b4_results: dict[str, Any] | None = None,
    b4_file: str | None = None,
) -> dict[str, Any]:
    """The frozen ``signatures.json`` payload."""
    grouped, _ = group_by_pair(results)
    return {
        "generated_at": now.astimezone(UTC).isoformat(),
        "base_sha": rc.BASE_SHA,
        "prespec": {
            "path": PRESPEC_PATH,
            "sha256": _sha256_of(_ROOT / PRESPEC_PATH),
        },
        "caveat": rc.INDISCERNIBILITY_CAVEAT,
        "fields_included": list(FIELDS_INCLUDED),
        "fields_excluded": list(FIELDS_EXCLUDED),
        "pairs": {pair: pair_block(entries) for pair, entries in grouped.items()},
        "b4_retro": b4_block(b4_results, b4_file),
    }


def b4_agreements(report: dict[str, Any]) -> list[tuple[str, int, int, bool]]:
    """``(pair, measured, reference, agrees)`` for the retroactive reading. Never a failure."""
    retro = report.get("b4_retro") or {}
    reference = retro.get("reference") or {}
    out: list[tuple[str, int, int, bool]] = []
    for pair in sorted(retro.get("pairs") or {}):
        measured = int(retro["pairs"][pair]["n_classes_exact"])
        expected = int(reference.get(pair, -1))
        out.append((pair, measured, expected, measured == expected))
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _same_partition(block: dict[str, Any]) -> bool:
    """True when the tolerant classes group the same members as the exact ones.

    The signatures themselves always differ (two different canonicalisations), so only the
    member partition is comparable.
    """
    exact = [klass["members"] for klass in block["classes_exact"]]
    tolerant = [klass["members"] for klass in block["classes_tolerant"]]
    return exact == tolerant


def render(report: dict[str, Any]) -> list[str]:
    """Stdout rendering — a pure function of the artifact."""
    lines: list[str] = []
    prespec = report["prespec"]["sha256"]
    lines.append("Rejeu diagnostic grid — classes d'indiscernabilité (§ A)")
    lines.append(
        f"généré {report['generated_at']} · base_sha {report['base_sha'][:8]} · "
        f"prespec {report['prespec']['path']} sha256 {(prespec or 'ABSENT')[:16]}"
    )
    lines.append(
        "DESCRIPTIF — § G.5 : le compte de classes n'entre dans aucune branche de verdict."
    )
    lines.append(report["caveat"])
    lines.append("")
    lines.append("Champs inclus : " + " ; ".join(report["fields_included"]))
    lines.append("Champs exclus : " + " ; ".join(report["fields_excluded"]))
    for pair in sorted(report["pairs"]):
        block = report["pairs"][pair]
        lines.append("")
        lines.append(
            f"{pair} : {block['n_configs']} configs → {block['n_classes_exact']} classes "
            f"(sig_exact, nombre de record) / {block['n_classes_tolerant']} classes (sig_tol)"
        )
        for index, klass in enumerate(block["classes_exact"], start=1):
            lines.append(
                f"  [{index:02d}] {klass['sig'][:12]} n={len(klass['members'])} : "
                + ", ".join(klass["members"])
            )
        if _same_partition(block):
            lines.append("  classes tolérantes : partition identique aux classes exactes")
        else:
            for index, klass in enumerate(block["classes_tolerant"], start=1):
                lines.append(
                    f"  tol [{index:02d}] {klass['sig'][:12]} n={len(klass['members'])} : "
                    + ", ".join(klass["members"])
                )
        if block["first_differences"]:
            lines.append("  premières différences entre classes voisines :")
            for diff in block["first_differences"]:
                lines.append(f"    {diff['a']} vs {diff['b']} → {diff['path']}")
        else:
            lines.append("  premières différences : aucune (une seule classe)")
    retro = report["b4_retro"]
    lines.append("")
    if retro.get("file") is None:
        lines.append("Lecture rétroactive B4 : fichier non lu (--b4 absent)")
    else:
        lines.append(f"Lecture rétroactive B4 : {retro['file']}")
        for pair, measured, expected, agrees in b4_agreements(report):
            lines.append(
                f"  {pair} : {retro['pairs'][pair]['n_configs']} configs → {measured} classes "
                f"(référence pré-enregistrée {expected} : "
                f"{'accord' if agrees else 'DÉSACCORD — constat, pas un échec'})"
            )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    """Per-pair table plus the full class listing and the first differences."""
    out: list[str] = ["# Rejeu diagnostic grid — classes d'indiscernabilité (§ A)", ""]
    out.append(
        f"généré {report['generated_at']} · base_sha `{report['base_sha'][:8]}` · "
        f"prespec `{report['prespec']['path']}` sha256 "
        f"`{(report['prespec']['sha256'] or 'ABSENT')[:16]}`"
    )
    out += [
        "",
        "DESCRIPTIF — § G.5 : le compte de classes n'entre dans aucune branche de verdict.",
        "",
        f"> {report['caveat']}",
        "",
        "**Champs inclus** : " + " ; ".join(report["fields_included"]) + ".",
        "",
        "**Champs exclus** : " + " ; ".join(report["fields_excluded"]) + ".",
        "",
        "| paire | configs | classes (sig_exact) | classes (sig_tol) |",
        "|---|---:|---:|---:|",
    ]
    for pair in sorted(report["pairs"]):
        block = report["pairs"][pair]
        out.append(
            f"| {pair} | {block['n_configs']} | {block['n_classes_exact']} | "
            f"{block['n_classes_tolerant']} |"
        )
    for pair in sorted(report["pairs"]):
        block = report["pairs"][pair]
        out += [
            "",
            f"## {pair} — classes exactes",
            "",
            "| # | signature | n | membres |",
            "|---:|---|---:|---|",
        ]
        for index, klass in enumerate(block["classes_exact"], start=1):
            out.append(
                f"| {index} | `{klass['sig'][:16]}` | {len(klass['members'])} | "
                + ", ".join(f"`{m}`" for m in klass["members"])
                + " |"
            )
        if _same_partition(block):
            out += ["", "Classes tolérantes : partition identique aux classes exactes."]
        else:
            out += [
                "",
                f"## {pair} — classes tolérantes",
                "",
                "| # | signature | n | membres |",
                "|---:|---|---:|---|",
            ]
            for index, klass in enumerate(block["classes_tolerant"], start=1):
                out.append(
                    f"| {index} | `{klass['sig'][:16]}` | {len(klass['members'])} | "
                    + ", ".join(f"`{m}`" for m in klass["members"])
                    + " |"
                )
        out += ["", f"## {pair} — premières différences entre classes voisines", ""]
        if block["first_differences"]:
            out += ["| a | b | chemin |", "|---|---|---|"]
            for diff in block["first_differences"]:
                out.append(f"| `{diff['a']}` | `{diff['b']}` | `{diff['path']}` |")
        else:
            out.append("Une seule classe : aucune paire voisine.")
    retro = report["b4_retro"]
    out += ["", "## Lecture rétroactive B4", ""]
    if retro.get("file") is None:
        out.append("Fichier non lu (`--b4` absent).")
    else:
        out += [
            f"Source : `{retro['file']}` — champs conservés par ce fichier uniquement "
            "(`strategy`, `pair`, `params`, `liquidation`, `train`, `test`, `all`).",
            "",
            "| paire | configs | classes (sig_exact) | référence | accord |",
            "|---|---:|---:|---:|---|",
        ]
        for pair, measured, expected, agrees in b4_agreements(report):
            out.append(
                f"| {pair} | {retro['pairs'][pair]['n_configs']} | {measured} | {expected} | "
                f"{'oui' if agrees else 'NON (constat, pas un échec)'} |"
            )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "campaign", type=Path, help="results/rejeu_grid_20260919/P7_phase1_grid.json"
    )
    parser.add_argument(
        "--b4",
        type=Path,
        default=None,
        help="results/B4_P7_phase1_cross_validate.json (optional retro reading)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--now", default=None, help="ISO UTC stamp written as generated_at")
    args = parser.parse_args(argv)

    try:
        now = _parse_now(args.now)
    except ValueError as exc:
        print(f"rejeu_signatures: --now is not an ISO timestamp: {exc}", file=sys.stderr)
        return 2

    try:
        results = rc.read_json(args.campaign)
        b4_results = rc.read_json(args.b4) if args.b4 else None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"rejeu_signatures: cannot read input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(results, dict):
        print("rejeu_signatures: the campaign file is not a JSON object", file=sys.stderr)
        return 2
    if b4_results is not None and not isinstance(b4_results, dict):
        print("rejeu_signatures: the B4 file is not a JSON object", file=sys.stderr)
        return 2

    try:
        report = build_report(
            results,
            now=now,
            b4_results=b4_results,
            b4_file=_relative(args.b4) if args.b4 else None,
        )
    except PayloadError as exc:
        print(f"rejeu_signatures: {exc}", file=sys.stderr)
        return 2

    sha = rc.write_json(args.output, report)
    lines = render(report)
    print("\n".join(lines))
    print(f"\nartefact {_relative(args.output)} sha256 {sha[:16]}")
    _, outside = group_by_pair(results)
    if outside:
        print(
            f"note : {len(outside)} entrée(s) hors périmètre gelé ignorée(s) : "
            + ", ".join(outside[:10])
            + (" …" if len(outside) > 10 else "")
        )
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
