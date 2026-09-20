"""Rejeu diagnostic grid — validité des analyses (prespec § I-B).

Deuxième étage de la validité, exécuté **après** ``rejeu_effect.py`` et **avant**
``rejeu_verdict.py`` (§ L, étape 10). La boucle de dépendance est cassée : la validité de campagne
(§ I-A) ne lit aucun artefact d'analyse, et celle-ci ne rejuge pas la campagne. **Un échec ici
donne ``inconclusif (F_NOT_ESTIMABLE)`` sans toucher au verdict de campagne** — c'est le verdict
qui en tire la conséquence, pas ce script.

Ce qu'il vérifie, littéralement :

* ``effect.json`` consigne ``B``, chaque ``L``, chaque graine, ``numpy.__version__``, ``|J_calc|``,
  **le mode de λ** (ré-estimé / gelé-sensibilité), le compte de réplications dégénérées, et le
  **premier gate en échec de chaque config inéligible** ;
* ces paramètres sont ceux que le § F.4 a gelés : ``B = 10000``, ``L ∈ {10, 21, 42}``, graines
  ``default_rng([SEED_BASE, index de paire, L])`` — un artefact produit avec une surcharge de test
  est un artefact qui ne vaut pas pour la campagne, et il doit le dire ;
* la règle du § F.7 : une config au-delà de ``DEGENERATE_MAX`` réplications dégénérées rend
  l'inférence inutilisable **pour la paire**, ce qui doit être consigné (``not_estimable``) ;
* **un rerun sur les mêmes entrées reproduit ``LB_j`` bit à bit.** Sans ``--rerun``, le rerun est
  fait ici même, en appelant ``rejeu_effect`` sur les mêmes entrées avec le ``B``, les longueurs de
  bloc et le mode de λ que l'artefact déclare ; avec ``--rerun``, un second ``effect.json`` produit
  indépendamment est comparé. Un rerun impossible est un **échec**, jamais un saut ;
* ``signatures.json`` et ``clamp.json`` sont présents, ou explicitement marqués non productibles.

Pure, read-only.

Usage::

    poetry run python scripts/audit/rejeu_validate_analysis.py \\
        --effect results/rejeu_grid_20260919/effect.json \\
        --signatures results/rejeu_grid_20260919/signatures.json \\
        --clamp results/rejeu_grid_20260919/clamp.json \\
        --campaign results/rejeu_grid_20260919/P7_phase1_grid.json \\
        --benchmark results/rejeu_grid_20260919/benchmark.json \\
        --coverage results/rejeu_grid_20260919/data_coverage.json \\
        --validation results/rejeu_grid_20260919/validation_campaign.json \\
        --output results/rejeu_grid_20260919/validation_analysis.json

Exit codes: 0 ok, 1 violation, 2 usage or input error.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sys
import tempfile
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import rejeu_common as rc  # noqa: E402
import rejeu_effect as eff  # noqa: E402

PRESPEC_RELPATH = "docs/rejeu_grid_prespec.md"
OUTPUT_DIR = rc.PROJECT_ROOT / "results" / "rejeu_grid_20260919"
DEFAULT_EFFECT = OUTPUT_DIR / "effect.json"
DEFAULT_SIGNATURES = OUTPUT_DIR / "signatures.json"
DEFAULT_CLAMP = OUTPUT_DIR / "clamp.json"
DEFAULT_CAMPAIGN = OUTPUT_DIR / "P7_phase1_grid.json"
DEFAULT_BENCHMARK = OUTPUT_DIR / "benchmark.json"
DEFAULT_COVERAGE = OUTPUT_DIR / "data_coverage.json"
DEFAULT_VALIDATION = OUTPUT_DIR / "validation_campaign.json"
DEFAULT_CALIBRATION = OUTPUT_DIR / "calibration.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "validation_analysis.json"

#: Fixed stamp handed to the rerun: ``generated_at`` is not compared, only ``LB``.
RERUN_NOW = "2000-01-01T00:00:00+00:00"

LAMBDA_MODES = (eff.LAMBDA_MODE_REESTIMATED, eff.LAMBDA_MODE_FROZEN)

#: Names the frozen ``inputs_sha256`` block carries, present or not.
INPUT_NAMES: tuple[str, ...] = (
    "effect",
    "signatures",
    "clamp",
    "campaign",
    "benchmark",
    "coverage",
    "validation_campaign",
    "calibration",
    "rerun",
)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class Context:
    """Everything the assertions read. Paths may be absent: that is a result, not a crash."""

    effect: Mapping[str, Any] | None
    effect_error: str | None
    signatures: Mapping[str, Any] | None
    signatures_error: str | None
    clamp: Mapping[str, Any] | None
    clamp_error: str | None
    rerun: Mapping[str, Any] | None
    rerun_error: str | None
    paths: Mapping[str, Path]
    sha256: Mapping[str, str | None]
    prespec: Mapping[str, str]

    @property
    def pairs(self) -> Mapping[str, Any]:
        block = (self.effect or {}).get("pairs")
        return block if isinstance(block, Mapping) else {}


Outcome = tuple[list[str], list[str]]


def _detail(problems: Sequence[str], notes: Sequence[str]) -> str:
    parts = [*problems, *notes]
    return " — ".join(parts) if parts else "ok"


def read_optional(path: Path | None) -> tuple[Mapping[str, Any] | None, str | None, str | None]:
    """(payload, error, sha256) for one optional JSON input."""
    if path is None:
        return None, "not given", None
    path = Path(path)
    if not path.exists():
        return None, "missing", None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = rc.read_json(path)
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"unparseable: {exc}", digest
    if not isinstance(payload, Mapping):
        return None, "not a JSON object", digest
    return payload, None, digest


def prespec_descriptor() -> dict[str, str]:
    path = rc.PROJECT_ROOT / PRESPEC_RELPATH
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    return {"path": PRESPEC_RELPATH, "sha256": digest}


def _configs(pair_block: Mapping[str, Any]) -> Mapping[str, Any]:
    block = pair_block.get("configs")
    return block if isinstance(block, Mapping) else {}


# ---------------------------------------------------------------------------
# I-B.1 — what effect.json must record
# ---------------------------------------------------------------------------


def b01_recorded_fields(ctx: Context) -> Outcome:
    """``B``, each ``L``, each seed, ``numpy.__version__``, ``|J_calc|`` and the λ mode."""
    if ctx.effect is None:
        return [f"effect.json {ctx.effect_error or 'unreadable'}"], []
    problems: list[str] = []
    notes: list[str] = []
    replications = ctx.effect.get("B")
    if not isinstance(replications, int) or isinstance(replications, bool) or replications < 2:
        problems.append(f"B is {replications!r}, not a replication count")
    lengths = ctx.effect.get("block_lengths")
    if not isinstance(lengths, list) or not lengths or not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in lengths
    ):
        problems.append(f"block_lengths is {lengths!r}, not a list of positive integers")
        lengths = []
    version = ctx.effect.get("numpy_version")
    if not isinstance(version, str) or not version:
        problems.append(f"numpy_version is {version!r}")
    elif version != np.__version__:
        notes.append(f"numpy {version} recorded, {np.__version__} running here")
    mode = ctx.effect.get("lambda_mode")
    if mode not in LAMBDA_MODES:
        problems.append(f"lambda_mode is {mode!r}, not one of {LAMBDA_MODES}")
    elif mode == eff.LAMBDA_MODE_FROZEN:
        label = ctx.effect.get("lambda_mode_label")
        if label != eff.FROZEN_LABEL:
            problems.append(
                f"lambda_mode is frozen_sensitivity but lambda_mode_label is {label!r}, "
                f"not the frozen {eff.FROZEN_LABEL!r}"
            )
        else:
            notes.append("λ gelé: " + eff.FROZEN_LABEL + " — aucun candidat ne peut s'y appuyer")
    seeds = ctx.effect.get("seeds")
    if not isinstance(seeds, Mapping):
        problems.append(f"seeds is {seeds!r}, not a mapping")
        seeds = {}
    if not ctx.pairs:
        problems.append("no pair block in effect.json")
    for pair, block in sorted(ctx.pairs.items()):
        if not isinstance(block, Mapping):
            problems.append(f"{pair}: pair block is not an object")
            continue
        j_calc = block.get("J_calc")
        if not isinstance(j_calc, list):
            problems.append(f"{pair}: J_calc is {j_calc!r}")
            continue
        if block.get("n_J_calc") != len(j_calc):
            problems.append(
                f"{pair}: n_J_calc {block.get('n_J_calc')!r} != |J_calc| {len(j_calc)}"
            )
        configs = _configs(block)
        unknown = [key for key in j_calc if key not in configs]
        if unknown:
            problems.append(f"{pair}: J_calc names {len(unknown)} key(s) absent from configs")
        eligible = block.get("J_eligible")
        if not isinstance(eligible, list):
            problems.append(f"{pair}: J_eligible is {eligible!r}")
        else:
            outside = [key for key in eligible if key not in set(j_calc)]
            if outside:
                problems.append(f"{pair}: J_eligible has {len(outside)} key(s) outside J_calc")
            if not eligible and block.get("not_estimable") is not True:
                problems.append(f"{pair}: J_eligible is empty but not_estimable is not True")
        pair_seeds = seeds.get(pair) if isinstance(seeds, Mapping) else None
        if not isinstance(pair_seeds, Mapping):
            problems.append(f"{pair}: no seed block")
            continue
        for length in lengths:
            if str(length) not in pair_seeds:
                problems.append(f"{pair}: no seed recorded for L={length}")
    return problems, notes


# ---------------------------------------------------------------------------
# I-B.2 — the frozen bootstrap parameters of section F.4
# ---------------------------------------------------------------------------


def b02_frozen_parameters(ctx: Context) -> Outcome:
    """``B = 10000``, ``L = (10, 21, 42)``, seeds = ``default_rng([SEED_BASE, pair, L])``."""
    if ctx.effect is None:
        return [f"effect.json {ctx.effect_error or 'unreadable'}"], []
    problems: list[str] = []
    if ctx.effect.get("B") != rc.BOOTSTRAP_B:
        problems.append(f"B is {ctx.effect.get('B')!r}, the frozen value is {rc.BOOTSTRAP_B}")
    lengths = ctx.effect.get("block_lengths")
    if lengths != list(rc.BLOCK_LENGTHS):
        problems.append(f"block_lengths {lengths!r} != frozen {list(rc.BLOCK_LENGTHS)}")
    seeds = ctx.effect.get("seeds")
    seeds = seeds if isinstance(seeds, Mapping) else {}
    for pair, block in sorted(seeds.items()):
        if pair not in rc.PAIRS:
            problems.append(f"{pair}: outside the frozen perimeter {rc.PAIRS}")
            continue
        if not isinstance(block, Mapping):
            continue
        index = rc.PAIRS.index(pair)
        for label, value in sorted(block.items()):
            try:
                expected = eff.stream_seed(index, int(label))
            except (TypeError, ValueError):
                problems.append(f"{pair}: seed label {label!r} is not a block length")
                continue
            if value != expected:
                problems.append(
                    f"{pair}/L={label}: seed {value!r} != default_rng([{rc.SEED_BASE}, {index}, "
                    f"{label}]) -> {expected}"
                )
    return problems, [f"seeds rebuilt in-script from SEED_BASE {rc.SEED_BASE}"]


# ---------------------------------------------------------------------------
# I-B.3 — degenerate replications and the section F.7 rule
# ---------------------------------------------------------------------------


def b03_degenerate_replications(ctx: Context) -> Outcome:
    """Counted, never silently dropped; beyond ``DEGENERATE_MAX`` the pair is not estimable."""
    if ctx.effect is None:
        return [f"effect.json {ctx.effect_error or 'unreadable'}"], []
    problems: list[str] = []
    total = 0
    over = 0
    for pair, block in sorted(ctx.pairs.items()):
        if not isinstance(block, Mapping):
            continue
        exceeded: list[str] = []
        for key, config in sorted(_configs(block).items()):
            if not isinstance(config, Mapping):
                problems.append(f"{pair}/{key}: config block is not an object")
                continue
            count = config.get("degenerate_replications")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                problems.append(f"{pair}/{key}: degenerate_replications is {count!r}")
                continue
            total += count
            if count > rc.DEGENERATE_MAX:
                exceeded.append(key)
        over += len(exceeded)
        if exceeded:
            if block.get("not_estimable") is not True:
                problems.append(
                    f"{pair}: {len(exceeded)} config(s) beyond {rc.DEGENERATE_MAX} degenerate "
                    "replications but the pair is not marked not_estimable (§ F.7)"
                )
            if block.get("reason") != "F_NOT_ESTIMABLE":
                problems.append(
                    f"{pair}: degenerate configs but reason is {block.get('reason')!r}, "
                    "not F_NOT_ESTIMABLE (§ F.7)"
                )
            carried = [
                key
                for key, config in sorted(_configs(block).items())
                if isinstance(config, Mapping) and config.get("LB_all_six_positive") is True
            ]
            if carried:
                problems.append(
                    f"{pair}: inference declared unusable but {len(carried)} config(s) still "
                    "carry LB_all_six_positive"
                )
        if block.get("not_estimable") is True and not block.get("reason"):
            problems.append(f"{pair}: not_estimable with no reason recorded")
    return problems, [f"{total} degenerate replication(s) recorded, {over} config(s) over the cap"]


# ---------------------------------------------------------------------------
# I-B.4 — the first failing gate of every ineligible config
# ---------------------------------------------------------------------------


def b04_first_failing_gate(ctx: Context) -> Outcome:
    """Every ineligible config is printable as ``NON ÉVALUÉE (gate: …)`` — never a blank."""
    if ctx.effect is None:
        return [f"effect.json {ctx.effect_error or 'unreadable'}"], []
    problems: list[str] = []
    counts: dict[str, int] = {}
    for pair, block in sorted(ctx.pairs.items()):
        if not isinstance(block, Mapping):
            continue
        for key, config in sorted(_configs(block).items()):
            if not isinstance(config, Mapping):
                continue
            status = config.get("status")
            gate = config.get("first_failing_gate")
            if status != rc.STATUS_ELIGIBLE:
                if not isinstance(gate, str) or not gate:
                    problems.append(
                        f"{pair}/{key}: status {status!r} without a first failing gate"
                    )
                else:
                    counts[gate] = counts.get(gate, 0) + 1
                continue
            gates = config.get("gates")
            gates = gates if isinstance(gates, Mapping) else {}
            expected = next((name for name in ("G1", "G2", "G4") if gates.get(name) is not True),
                            None)
            if gate != expected:
                problems.append(
                    f"{pair}/{key}: first_failing_gate {gate!r} != {expected!r} for gates "
                    f"{dict(gates)!r}"
                )
            if config.get("passes_gates") is not (expected is None):
                problems.append(
                    f"{pair}/{key}: passes_gates {config.get('passes_gates')!r} does not match "
                    f"G1 ∧ G2 ∧ G4"
                )
    summary = ", ".join(f"{gate} x{count}" for gate, count in sorted(counts.items())) or "none"
    return problems, [f"ineligible configs by first failing gate: {summary}"]


# ---------------------------------------------------------------------------
# I-B.5 — a rerun on the same inputs reproduces LB_j bit for bit
# ---------------------------------------------------------------------------


def lb_fingerprint(effect: Mapping[str, Any]) -> dict[str, str]:
    """``pair/key -> sha256`` of the canonical image of that config's ``LB`` block.

    ``rc.canon`` sends every float through its shortest round-trip repr, so equality of these
    digests is equality of the float64 values themselves — bit for bit, not "to a tolerance".
    """
    out: dict[str, str] = {}
    pairs = effect.get("pairs")
    pairs = pairs if isinstance(pairs, Mapping) else {}
    for pair, block in pairs.items():
        if not isinstance(block, Mapping):
            continue
        for key, config in _configs(block).items():
            if not isinstance(config, Mapping):
                continue
            out[f"{pair}/{key}"] = rc.sig(config.get("LB"))
    return out


def rerun_arguments(effect: Mapping[str, Any], paths: Mapping[str, Path], output: Path
                    ) -> list[str]:
    """The exact ``rejeu_effect`` invocation that reproduces the published artifact."""
    lengths = effect.get("block_lengths")
    lengths = lengths if isinstance(lengths, list) and lengths else list(rc.BLOCK_LENGTHS)
    replications = effect.get("B")
    replications = replications if isinstance(replications, int) else rc.BOOTSTRAP_B
    argv = [
        "--campaign", str(paths["campaign"]),
        "--benchmark", str(paths["benchmark"]),
        "--coverage", str(paths["coverage"]),
        "--validation", str(paths["validation_campaign"]),
        "--calibration", str(paths["calibration"]),
        "--output", str(output),
        "--now", RERUN_NOW,
        "--bootstrap-b", str(replications),
        "--block-lengths", ",".join(str(int(value)) for value in lengths),
    ]
    if effect.get("lambda_mode") != eff.LAMBDA_MODE_REESTIMATED:
        # The published bound is the declared fallback; the rerun must take the same road.
        argv.append("--no-reestimate")
    return argv


def perform_rerun(ctx: Context) -> tuple[Mapping[str, Any] | None, str | None]:
    """``--rerun`` artifact when given, otherwise a real rerun of ``rejeu_effect`` right here."""
    if ctx.rerun is not None:
        return ctx.rerun, None
    if ctx.rerun_error and ctx.rerun_error != "not given":
        return None, f"--rerun {ctx.rerun_error}"
    if ctx.effect is None:
        return None, "effect.json unreadable"
    missing = [
        name
        for name in ("campaign", "benchmark", "coverage", "validation_campaign")
        if not Path(ctx.paths[name]).exists()
    ]
    if missing:
        return None, "the rerun needs " + ", ".join(missing)
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "effect_rerun.json"
        code = eff.main(rerun_arguments(ctx.effect, ctx.paths, output))
        if code != 0 or not output.exists():
            return None, f"rejeu_effect rerun exited {code}"
        payload = rc.read_json(output)
    return (payload if isinstance(payload, Mapping) else None), None


def b05_rerun_reproduces_lb(ctx: Context) -> Outcome:
    """A rerun on the same inputs reproduces ``LB_j`` bit for bit. Impossible rerun = failure."""
    rerun, error = perform_rerun(ctx)
    if rerun is None:
        return [f"no rerun to compare: {error or 'unavailable'}"], []
    if ctx.effect is None:
        return [f"effect.json {ctx.effect_error or 'unreadable'}"], []
    published = lb_fingerprint(ctx.effect)
    reproduced = lb_fingerprint(rerun)
    problems: list[str] = []
    missing = sorted(set(published) - set(reproduced))
    added = sorted(set(reproduced) - set(published))
    if missing:
        problems.append(f"{len(missing)} config(s) absent from the rerun: {missing[:3]}")
    if added:
        problems.append(f"{len(added)} config(s) only in the rerun: {added[:3]}")
    differing = sorted(
        name for name in set(published) & set(reproduced) if published[name] != reproduced[name]
    )
    if differing:
        problems.append(
            f"{len(differing)} config(s) whose LB does not reproduce bit for bit: {differing[:3]}"
        )
    source = "--rerun artifact" if ctx.rerun is not None else "in-process rejeu_effect rerun"
    return problems, [f"{len(published)} LB block(s) compared against the {source}"]


# ---------------------------------------------------------------------------
# I-B.6 / I-B.7 — signatures.json and clamp.json
# ---------------------------------------------------------------------------


def b06_signatures_present(ctx: Context) -> Outcome:
    """§ A is descriptive and enters no verdict, but it must exist or say that it cannot."""
    if ctx.signatures is None:
        return [f"signatures.json {ctx.signatures_error or 'unreadable'}"], []
    if ctx.signatures.get("producible") is False:
        reason = ctx.signatures.get("reason")
        if not reason:
            return ["signatures.json marked not producible without a reason"], []
        return [], [f"explicitly not producible: {reason}"]
    problems = [
        f"signatures.json has no {field!r}"
        for field in ("caveat", "fields_included", "pairs")
        if field not in ctx.signatures
    ]
    pairs = ctx.signatures.get("pairs")
    count = len(pairs) if isinstance(pairs, Mapping) else 0
    return problems, [f"{count} pair block(s); § G.5: degeneracy never changes a verdict"]


def b07_clamp_present(ctx: Context) -> Outcome:
    """§ B is a distributional measurement; it moves no verdict, in any direction."""
    if ctx.clamp is None:
        return [f"clamp.json {ctx.clamp_error or 'unreadable'}"], []
    if ctx.clamp.get("producible") is False:
        reason = ctx.clamp.get("reason")
        if not reason:
            return ["clamp.json marked not producible without a reason"], []
        return [], [
            f"explicitly not producible: {reason} — the hypothesis is labelled NOT MEASURED and "
            "nothing else changes (§ B.3)"
        ]
    problems = [
        f"clamp.json has no {field!r}"
        for field in ("label", "atr_period", "pairs")
        if field not in ctx.clamp
    ]
    return problems, ["§ G.5: the clamp never changes a verdict, in any direction"]


ASSERTIONS: tuple[tuple[str, str, Callable[[Context], Outcome]], ...] = (
    ("I-B.1", "effect.json records B, L, seeds, numpy, |J_calc| and the λ mode",
     b01_recorded_fields),
    ("I-B.2", "frozen bootstrap parameters: B, block lengths, seeds", b02_frozen_parameters),
    ("I-B.3", "degenerate replications counted and the § F.7 rule applied",
     b03_degenerate_replications),
    ("I-B.4", "first failing gate of every ineligible config", b04_first_failing_gate),
    ("I-B.5", "a rerun on the same inputs reproduces LB_j bit for bit", b05_rerun_reproduces_lb),
    ("I-B.6", "signatures.json present or explicitly not producible", b06_signatures_present),
    ("I-B.7", "clamp.json present or explicitly not producible", b07_clamp_present),
)


# ---------------------------------------------------------------------------
# Runner, payload, rendering
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Assertion:
    id: str
    name: str
    ok: bool
    skipped: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "ok": self.ok,
            "skipped": self.skipped,
            "detail": self.detail,
        }


def run_assertions(ctx: Context) -> list[Assertion]:
    """The seven assertions. Unlike § I-A there is no false-green ordering here: they all run.

    The one dependency is real and explicit: with an unreadable ``effect.json`` nothing can be
    checked, so the assertions that need it are marked **skipped** and the skip is consigned —
    never silently green.
    """
    rows: list[Assertion] = []
    for identifier, name, check in ASSERTIONS:
        needs_effect = identifier not in {"I-B.6", "I-B.7"}
        if ctx.effect is None and needs_effect and identifier != "I-B.1":
            rows.append(
                Assertion(
                    identifier,
                    name,
                    False,
                    True,
                    f"not evaluated: effect.json {ctx.effect_error or 'unreadable'} "
                    "(I-B.1 owns that failure)",
                )
            )
            continue
        try:
            problems, notes = check(ctx)
        except Exception as exc:  # a crashing check is a failing check, never a skip
            problems, notes = [f"{type(exc).__name__}: {exc}"], []
        rows.append(Assertion(identifier, name, not problems, False, _detail(problems, notes)))
    return rows


def build_payload(ctx: Context, rows: Sequence[Assertion], *, now: str) -> dict[str, Any]:
    failed = [row.id for row in rows if not row.ok]
    ok = not failed
    return {
        "generated_at": now,
        "base_sha": rc.BASE_SHA,
        "prespec": dict(ctx.prespec),
        "ok": ok,
        "exit_code": 0 if ok else 2,
        "assertions": [row.to_dict() for row in rows],
        "failed": failed,
        "inputs_sha256": {name: ctx.sha256.get(name) for name in INPUT_NAMES},
    }


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    lines = [
        "Rejeu diagnostic grid — analysis validity (section I-B)",
        f"prespec {payload['prespec']['sha256'][:16]}",
        "",
    ]
    for row in payload["assertions"]:
        status = "ok " if row["ok"] else ("--- " if row["skipped"] else "FAIL")
        lines.append(f"{status} {row['id']:<7} {row['name']}")
        lines.append(f"         {row['detail']}")
    lines.append("")
    verdict = "ANALYSES EXPLOITABLES (exit 0)" if payload["ok"] else (
        "ANALYSES NON EXPLOITABLES (exit 2) — inconclusif (F_NOT_ESTIMABLE), "
        "sans toucher au verdict de campagne"
    )
    lines.append(f"Verdict: {verdict} — failed: {', '.join(payload['failed']) or 'none'}")
    return lines


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Rejeu diagnostic grid — validité des analyses (§ I-B)",
        "",
        f"`ok` : **{payload['ok']}** · sortie `{payload['exit_code']}` · prespec "
        f"`{payload['prespec']['sha256'][:16]}`",
        "",
        "| # | Assertion | État | Détail |",
        "|---|---|---|---|",
    ]
    for row in payload["assertions"]:
        status = "ok" if row["ok"] else ("non évaluée" if row["skipped"] else "**ÉCHEC**")
        lines.append(f"| {row['id']} | {row['name']} | {status} | {row['detail']} |")
    lines.append("")
    lines.append(
        "Un échec ici donne `inconclusif (F_NOT_ESTIMABLE)` **sans toucher au verdict de "
        "campagne** (§ I-B)."
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--effect", type=Path, default=DEFAULT_EFFECT)
    parser.add_argument("--signatures", type=Path, default=DEFAULT_SIGNATURES)
    parser.add_argument("--clamp", type=Path, default=DEFAULT_CLAMP)
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument(
        "--rerun",
        type=Path,
        default=None,
        help="a second effect.json produced independently; without it the rerun is run here",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--now", default=None, help="ISO UTC stamp of generated_at (default: now), for determinism"
    )
    return parser


def build_context(args: argparse.Namespace) -> Context:
    effect, effect_error, effect_sha = read_optional(args.effect)
    signatures, signatures_error, signatures_sha = read_optional(args.signatures)
    clamp, clamp_error, clamp_sha = read_optional(args.clamp)
    rerun, rerun_error, rerun_sha = read_optional(args.rerun)
    paths = {
        "effect": Path(args.effect),
        "signatures": Path(args.signatures),
        "clamp": Path(args.clamp),
        "campaign": Path(args.campaign),
        "benchmark": Path(args.benchmark),
        "coverage": Path(args.coverage),
        "validation_campaign": Path(args.validation),
        "calibration": Path(args.calibration),
    }
    sha256: dict[str, str | None] = {
        "effect": effect_sha,
        "signatures": signatures_sha,
        "clamp": clamp_sha,
        "rerun": rerun_sha,
    }
    for name in ("campaign", "benchmark", "coverage", "validation_campaign", "calibration"):
        path = paths[name]
        sha256[name] = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        )
    return Context(
        effect=effect,
        effect_error=effect_error,
        signatures=signatures,
        signatures_error=signatures_error,
        clamp=clamp,
        clamp_error=clamp_error,
        rerun=rerun,
        rerun_error=rerun_error,
        paths=paths,
        sha256=sha256,
        prespec=prespec_descriptor(),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.now is None:
        now = datetime.now(UTC).isoformat()
    else:
        try:
            parsed = datetime.fromisoformat(args.now)
        except ValueError as exc:
            print(f"--now: {exc}", file=sys.stderr)
            return 2
        now = (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).isoformat()

    ctx = build_context(args)
    rows = run_assertions(ctx)
    payload = build_payload(ctx, rows, now=now)
    digest = rc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(payload), encoding="utf-8")
        print(f"written {args.markdown}")
    for row in rows:
        if not row.ok:
            print(f"{row.id}: {row.detail}", file=sys.stderr)
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
