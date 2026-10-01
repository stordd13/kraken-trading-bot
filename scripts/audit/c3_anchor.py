"""C3 — l'ancrage recalculé, les estampilles admissibles et le registre de variantes (§ A.3, § A.4, § A.6).

Étape 1 de la chaîne du § L.1. Elle lit **le manifeste seul** et produit ``anchor.json`` :

* **§ A.3** — `T = début + F × (fin − début)`, **recalculé depuis la règle, jamais accepté comme
  paramètre**, sans aucun arrondi ; les bornes viennent du manifeste gelé, jamais de la dernière donnée.
* **§ A.4** — par timeframe déclaré, la dernière estampille admissible `≤ T`, calculée par l'outil,
  jamais écrite en dur ; et la première estampille d'exécution strictement après `T` (§ C.3).
* **§ A.6** — la clé de variante est l'empreinte du **manifeste complet**, `sig(canon(manifeste))` ;
  ré-exécuter le même manifeste est idempotent (même enregistrement, registre inchangé) ; une clé
  nouvelle déclare son parent, et c'est là que le contrôle mord : parent absent du registre → refus ;
  seconde racine dans un registre non vide → refus (elle contournerait la parenté).
* **§ A.6 v2.2 (AM-05)** — le registre tient l'état du critère d'arrêt, et l'ancrage l'applique : pour une clé
  nouvelle, les enregistrements de la famille que le manifeste déclare sont lus ; une famille qui porte un verdict
  compté n'accepte que la variante dont le descripteur ``D``, re-dérivé du manifeste entrant par la règle du
  § A.6 v2.3 (``cc.deferred_descriptor_at_run``), a l'empreinte de l'évaluation différée inscrite au verdict ; une
  famille qui a consommé sa relance unique (deux verdicts non comptés) n'accepte plus rien — refus
  ``R0_INVALID_RUN``, code 2
  (``CONTRAINTES_POST_B4.md`` § 10.1, section d'origine, non redite ici). Les champs d'issue (``verdict``,
  ``deferred_evaluation``), écrits par ``c3_verdict`` à l'étape 6, sont hors ``RECORD_KEYS`` : l'idempotence tient.
  Le sha256 déclaré du protocole est asserté **avant** le typage du manifeste : un manifeste d'un autre protocole
  n'est pas relu sous le schéma de celui-ci.
* **§ A.6 v2.3 (AM-01)** — ``deferred_evaluation.date``, obligatoire sur tout manifeste (forme : ``cc.load_manifest``),
  est validée ici : au moins 365 jours après ``window.end`` (``assert_deferred_date``), sinon ``R0_INVALID_RUN``,
  code 2.

**Les valeurs gelées sont assertées, pas seulement leur forme** — liste close de quatre assertions,
tout écart étant un contrat rompu (``R0_INVALID_RUN``, code 2, rien d'écrit) : la fraction d'ancrage,
les paramètres de la procédure d'incertitude, chaque seuil avec sa classe et sa section contre le
registre ``THRESHOLDS`` de ``c3_common``, et le sha256 du protocole gelé.

Pure, lecture seule hors de ses deux sorties (``--output``, ``--registry``). Aucun accès base.

Usage::

    poetry run python scripts/audit/c3_anchor.py \\
        --manifest results/c3a_entry_validation/manifest_rejeu_grid_20260919.json \\
        --registry results/c3a_entry_validation/variants.json \\
        --output results/c3a_entry_validation/anchor_rejeu_grid_20260919.json \\
        --now 2026-09-22T00:00:00+00:00

Exit codes: 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import c3_common as cc  # noqa: E402

STEP = "anchor"

#: Liste **close** des assertions de valeurs gelées (plan § 5.2) — rien d'autre n'est asserté ici.
FROZEN_ASSERTIONS: tuple[str, ...] = (
    "anchor_fraction",
    "uncertainty",
    "thresholds",
    "protocol_sha256",
)

#: Clés d'un enregistrement du registre, recalculées à chaque exécution et recoupées.
RECORD_KEYS: tuple[str, ...] = (
    "variant_id",
    "parent",
    "anchor",
    "window",
    "prefix_segment",
    "universe_provenance",
    "manifest_sha256",
    "research_log_entry",
    "family",
)


def assert_frozen_values(manifest: cc.Manifest) -> list[str]:
    """Les quatre assertions, toutes évaluées, chaque écart nommé."""
    problems: list[str] = []
    if manifest.anchor_fraction != cc.ANCHOR_FRACTION:
        problems.append(
            f"anchor_fraction {manifest.anchor_fraction!r} != valeur gelée {cc.ANCHOR_FRACTION!r} (§ A.3)"
        )
    if manifest.bootstrap_b != cc.BOOTSTRAP_B:
        problems.append(f"uncertainty.B {manifest.bootstrap_b} != {cc.BOOTSTRAP_B} (§ F.2 b)")
    if manifest.block_lengths != tuple(cc.BLOCK_LENGTHS):
        problems.append(
            f"uncertainty.block_lengths {list(manifest.block_lengths)} != {list(cc.BLOCK_LENGTHS)} (§ F.2 b)"
        )
    if manifest.bound_level != cc.BOUND_LEVEL:
        problems.append(
            f"uncertainty.bound_level {manifest.bound_level!r} != {cc.BOUND_LEVEL!r} (§ F.2 d)"
        )
    declared = set(manifest.thresholds)
    frozen = set(cc.THRESHOLDS)
    for name in sorted(frozen - declared):
        problems.append(f"thresholds.{name}: seuil gelé absent du manifeste (§ 0.5)")
    for name in sorted(declared - frozen):
        problems.append(f"thresholds.{name}: seuil déclaré inconnu du registre (§ 0.5)")
    for name in sorted(declared & frozen):
        value, klass, section = cc.THRESHOLDS[name]
        block = manifest.thresholds[name]
        if cc.canon(block["value"]) != cc.canon(value):
            problems.append(f"thresholds.{name}.value {block['value']!r} != valeur gelée {value!r}")
        if block["class"] != klass:
            problems.append(f"thresholds.{name}.class {block['class']!r} != {klass!r}")
        if block["section"] != section:
            problems.append(f"thresholds.{name}.section {block['section']!r} != {section!r}")
    current = cc.protocol_descriptor()["sha256"]
    if manifest.protocol_sha256 != current:
        problems.append(
            f"protocol_sha256 {manifest.protocol_sha256[:16]} != sha256 courant {current[:16]} de "
            f"{cc.PROTOCOL_RELPATH} — le manifeste ne déclare pas ce protocole"
        )
    return problems


def assert_deferred_date(manifest: cc.Manifest) -> None:
    """§ A.6 v2.3 (AM-01), à l'étape 1 : `deferred_evaluation.date` est « au moins 12 mois après `window.end` »
    (§ 10.1, « au moins 12 mois de données neuves ») — décision de gate du 30/09 : **≥ 365 jours**, 365 exactement
    admis ; trop proche → ``R0_INVALID_RUN``, code 2 (§ I.1, ligne 2), rien d'écrit. Absente ou illisible, la clé a
    déjà été refusée par ``cc.load_manifest`` (erreur de forme). La date est une déclaration du manifeste, jamais une
    fenêtre lue."""
    gap = manifest.deferred_evaluation_date - manifest.window_end
    if gap < timedelta(days=cc.DEFERRED_MIN_DAYS):
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"deferred_evaluation.date {manifest.deferred_evaluation_date.isoformat()} : "
            f"{gap.total_seconds() / 86400.0:.6f} j après window.end {manifest.window_end.isoformat()}, minimum "
            f"{cc.DEFERRED_MIN_DAYS} j (§ A.6 v2.3)",
        )


def variant_record(manifest: cc.Manifest, *, manifest_sha256: str) -> dict[str, Any]:
    """L'enregistrement recalculé d'une variante — sans horodatage, pour être recoupé."""
    parent: dict[str, Any] = {"is_root": manifest.parent_is_root}
    if not manifest.parent_is_root:
        parent["variant_key"] = manifest.parent_variant_key
    return {
        "variant_id": manifest.variant_id,
        "parent": parent,
        "anchor": manifest.anchor().isoformat(),
        "window": {
            "start": manifest.window_start.isoformat(),
            "end": manifest.window_end.isoformat(),
        },
        "prefix_segment": manifest.prefix_segment,
        "universe_provenance": manifest.provenance,
        "manifest_sha256": manifest_sha256,
        "research_log_entry": manifest.research_log_entry,
        "family": manifest.family,
    }


def assert_declared_protocol(raw: Any) -> None:
    """Le sha256 déclaré du protocole, asserté **avant** ``cc.load_manifest`` (plan du lot 1, D9) : un manifeste d'un
    autre protocole n'est pas relu sous le schéma de celui-ci — v2.2 exige la famille, que les manifestes v2.0 et
    v2.1 ne portent pas. Même refus, même valeur gelée que ``assert_frozen_values``, qui la refait."""
    if not isinstance(raw, Mapping):
        raise cc.MissingEvidenceError(f"manifest: bloc attendu, reçu {type(raw).__name__}")
    declared = cc.require_str(raw, "protocol_sha256", where="manifest")
    current = cc.protocol_descriptor()["sha256"]
    if declared != current:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"valeurs gelées : protocol_sha256 {declared[:16]} != sha256 courant {current[:16]} de "
            f"{cc.PROTOCOL_RELPATH} — le manifeste ne déclare pas ce protocole ; il n'est pas relu sous son schéma",
        )


def stop_criterion(
    variants: Mapping[str, Any], *, family: str, key: str, incoming: Mapping[str, Any]
) -> None:
    """§ A.6 v2.2 (AM-05), à l'étape 1 : l'ancrage lit les enregistrements de la famille et refuse
    (``R0_INVALID_RUN``, code 2) toute variante nouvelle que ``CONTRAINTES_POST_B4.md`` § 10.1 exclut — une seconde
    campagne sur une famille qui porte déjà un verdict compté, ou une relance au-delà de l'unique (deux verdicts non
    comptés). § A.6 v2.3 (AM-01) : sur une famille au verdict compté, l'ancrage **dérive le même descripteur du
    manifeste entrant, par la même règle** (``cc.deferred_descriptor_at_run``), et **seule est acceptée** la variante
    dont ``sig(canon(D))`` égale l'empreinte inscrite au verdict : un état du registre, pas une exception de lecture.
    Non-divulgation : le refus ne nomme aucune empreinte de descripteur, ni l'inscrite ni la dérivée."""
    counted: list[str] = []
    not_counted = 0
    deferred_keys: set[str] = set()
    for other in variants:
        where = f"registry.variants.{other[:16]}"
        stored = cc.require_mapping(variants, other, where="registry.variants")
        if cc.require_str(stored, "family", where=where) != family:
            continue
        verdict = cc.optional_mapping(stored, "verdict", where=where)
        if verdict is not None:
            cc.require_str(verdict, "issue", where=f"{where}.verdict", allowed=cc.ISSUES)
            cc.nullable_str(verdict, "raison", where=f"{where}.verdict")
            if cc.require_bool(verdict, "compte", where=f"{where}.verdict"):
                counted.append(other)
            else:
                not_counted += 1
        deferred = cc.optional_mapping(stored, "deferred_evaluation", where=where)
        if deferred is not None:
            cc.require_datetime(deferred, "date", where=f"{where}.deferred_evaluation")
            deferred_keys.add(
                cc.require_str(deferred, "variant_key", where=f"{where}.deferred_evaluation")
            )
    if counted:
        if deferred_keys:
            descriptor = cc.deferred_descriptor_at_run(incoming)
            if descriptor is not None and cc.sig(descriptor) in deferred_keys:
                return
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"la famille {family!r} porte déjà un verdict compté ({counted[0][:16]}) : seule l'évaluation différée "
            f"inscrite au verdict est acceptée, et le descripteur dérivé du manifeste entrant (variante {key[:16]}) "
            "n'a pas l'empreinte inscrite — empreintes non imprimées (§ A.6 v2.3 ; CONTRAINTES § 10.1)",
        )
    if not_counted >= 2:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"la famille {family!r} a consommé sa relance unique ({not_counted} verdicts non comptés) — une "
            "relance au-delà de l'unique est refusée (§ A.6 v2.2 ; CONTRAINTES § 10.1)",
        )


def load_registry(path: Path) -> dict[str, Any]:
    """Le registre, ou un registre vide s'il n'existe pas encore ; mal formé → erreur d'entrée. Chaque
    enregistrement est canonicalisé à la lecture : une valeur **fournie** non finie, dans quelque enregistrement
    que ce soit, est une violation (§ I.1, ligne 15 : diagnostic ``invalide``, code 1), jamais une trace du writer
    à la réécriture (R-22, cas 1)."""
    if not Path(path).exists():
        return {"variants": {}}
    try:
        raw = cc.read_json(path)
    except (OSError, ValueError) as exc:
        raise cc.MissingEvidenceError(f"registry: {exc}") from exc
    variants = cc.require_mapping(raw, "variants", where="registry")
    for key in variants:
        cc.require_mapping(variants, key, where="registry.variants")
    cc.canon(dict(variants))
    return {"variants": dict(variants)}


def register(
    registry: Mapping[str, Any],
    key: str,
    record: Mapping[str, Any],
    *,
    incoming: Mapping[str, Any],
    now: datetime,
    violations: list[str],
) -> tuple[dict[str, Any], bool]:
    """Idempotence, parenté, et recoupement de l'enregistrement existant (§ A.6).

    Renvoie ``(registre, nouvel_enregistrement)``. Un enregistrement existant dont le contenu
    recalculé diffère est une **violation** (statut enregistré ≠ recalculé, § I.1 l.15) ; le
    registre n'est alors pas réécrit.
    """
    variants = cc.require_mapping(registry, "variants", where="registry")
    if key in variants:
        stored = cc.require_mapping(variants, key, where="registry.variants")
        stored_core = {
            k: cc._require(stored, k, where=f"registry.variants.{key[:16]}") for k in RECORD_KEYS
        }
        if cc.canon(stored_core) != cc.canon(dict(record)):
            path = cc.first_difference(cc.canon(stored_core), cc.canon(dict(record)))
            violations.append(
                f"registre : enregistrement {key[:16]} différent du recalcul (première différence {path}) "
                "— le recalcul fait foi, le registre n'est pas réécrit"
            )
        return {"variants": dict(variants)}, False
    stop_criterion(variants, family=str(record["family"]), key=key, incoming=incoming)
    parent = record["parent"]
    if parent["is_root"]:
        if variants:
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN",
                f"variante {key[:16]} déclarée racine dans un registre non vide ({len(variants)} "
                "variante(s)) — une seconde racine contournerait la parenté (§ A.6)",
            )
    elif parent["variant_key"] not in variants:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"variante {key[:16]} déclare le parent {str(parent['variant_key'])[:16]}, absent du registre (§ A.6)",
        )
    updated = dict(variants)
    updated[key] = {**dict(record), "first_registered_at": now.isoformat()}
    return {"variants": updated}, True


def build_payload(
    manifest: cc.Manifest,
    *,
    key: str,
    new_entry: bool,
    registry_path: Path,
    now: datetime,
    inputs: Mapping[str, Path],
) -> dict[str, Any]:
    anchor = manifest.anchor()
    intervals = sorted(set(manifest.timeframes.values()))
    stamps = cc.admissible_stamps(anchor, intervals)
    window_days = (manifest.window_end - manifest.window_start).total_seconds() / 86400.0
    prefix_days = (anchor - manifest.window_start).total_seconds() / 86400.0
    payload = cc.envelope(STEP, now, inputs, exit_code=0)
    payload.update(
        {
            "anchor": anchor.isoformat(),
            "window": {
                "start": manifest.window_start.isoformat(),
                "end": manifest.window_end.isoformat(),
            },
            "anchor_fraction": manifest.anchor_fraction,
            "prefix_segment": manifest.prefix_segment,
            "window_days": window_days,
            "prefix_days": prefix_days,
            "evaluation_days": window_days - prefix_days,
            "admissible_stamps": {str(iv): stamps[iv] for iv in intervals},
            "admissible_stamps_by_label": {
                label: stamps[iv] for label, iv in sorted(manifest.timeframes.items())
            },
            "exec_interval": manifest.exec_interval,
            "first_exec_stamp_after_anchor": cc.first_stamp_strictly_after(
                anchor, manifest.exec_interval
            ).isoformat(),
            "universe_provenance": manifest.provenance,
            "n_candidates": len(manifest.candidates),
            "pairs": list(manifest.pairs),
            "variant_key": key,
            "variant_id": manifest.variant_id,
            "parent": variant_record(manifest, manifest_sha256="")["parent"],
            "registry": {
                "path": str(registry_path),
                "sha256": cc.file_sha256(registry_path),
                "new_entry": new_entry,
            },
            "manifest_sha256": cc.file_sha256(inputs["manifest"]),
            "research_log_entry": manifest.research_log_entry,
            "frozen_values_asserted": list(FROZEN_ASSERTIONS),
            "uncertainty": {
                "seed": manifest.seed,
                "B": manifest.bootstrap_b,
                "block_lengths": list(manifest.block_lengths),
                "bound_level": manifest.bound_level,
            },
        }
    )
    return payload


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    if payload["invalide"]:
        return ["ARTEFACT INVALIDE — ancrage non publié"] + [
            f"  violation : {v}" for v in payload["violations"]
        ]
    out = [
        f"ancrage T = {payload['anchor']} (F = {payload['anchor_fraction']}, fenêtre "
        f"{payload['window']['start']} -> {payload['window']['end']}, préfixe {payload['prefix_days']:.1f} j)",
        "estampilles admissibles : "
        + " ".join(f"{k}={v}" for k, v in sorted(payload["admissible_stamps_by_label"].items())),
        f"première exécution possible : {payload['first_exec_stamp_after_anchor']}",
        f"variante {payload['variant_key'][:16]} ({payload['variant_id']}) — "
        + (
            "nouvelle au registre"
            if payload["registry"]["new_entry"]
            else "déjà au registre, idempotent"
        ),
        f"provenance de l'univers : {payload['universe_provenance']} ({payload['n_candidates']} candidats)",
    ]
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--now", default=None, help="Horodatage ISO UTC de generated_at, pour le déterminisme."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        print(f"--now: {exc}", file=sys.stderr)
        return 2
    try:
        raw = cc.read_json(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"--manifest: {exc}", file=sys.stderr)
        return 2
    inputs = {"manifest": args.manifest}

    violations: list[str] = []
    manifest: cc.Manifest | None = None
    registry: dict[str, Any] = {"variants": {}}
    key = ""
    new_entry = False
    try:
        assert_declared_protocol(raw)
        manifest = cc.load_manifest(raw)
        problems = assert_frozen_values(manifest)
        if problems:
            raise cc.EntryRefusedError("R0_INVALID_RUN", "valeurs gelées : " + " ; ".join(problems))
        assert_deferred_date(manifest)
        registry = load_registry(args.registry)
        key = cc.sig(raw)
        record = variant_record(manifest, manifest_sha256=cc.file_sha256(args.manifest))
        registry, new_entry = register(
            registry, key, record, incoming=raw, now=now, violations=violations
        )
    except cc.EntryRefusedError as exc:
        print(f"ENTREE REFUSEE {exc}", file=sys.stderr)
        return 2
    except cc.MissingEvidenceError as exc:
        print(f"ENTREE INVALIDE {exc}", file=sys.stderr)
        return 2
    except (cc.InvalidValueError, cc.NonFiniteValueError) as exc:
        # Non fini dans le manifeste, y compris un NaN atteignant `canon` (revue R3 d) : violation.
        violations.append(str(exc))

    if violations:
        payload = cc.envelope(STEP, now, inputs, exit_code=1, violations=violations)
        payload["anchor"] = None
        payload["variant_key"] = key or None
        digest = cc.write_json(args.output, payload)
        print("\n".join(render_lines(payload)))
        print(f"written {args.output} sha256 {digest}")
        for violation in violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        return 1

    assert manifest is not None
    if new_entry:
        cc.write_json(args.registry, registry)
    payload = build_payload(
        manifest, key=key, new_entry=new_entry, registry_path=args.registry, now=now, inputs=inputs
    )
    digest = cc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
