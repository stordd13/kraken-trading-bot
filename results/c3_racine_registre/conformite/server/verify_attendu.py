"""C3 racine du registre, lot 2 (repris de l'outillage v2.3, lot 2) — vérification de l'attendu de conformité
(``../attendu.md``), item par item.

Ne lit que ``status.txt``, les deux ``alembic current`` et ``pilot_exit.txt`` du répertoire donné : aucune sortie du
producteur ni de la chaîne (issue non lue ; plan D3). Prouvé avant son premier usage par ``tests/verify_adverse.sh``
(témoin sain à 0, chaque cas dévié ≠ 0 ; condition du GO).

Usage (depuis la racine du dépôt) ::

    python3 results/c3_racine_registre/conformite/server/verify_attendu.py --sha <S1, 40 hex>
        [--dir <répertoire des preuves>] [--pilot-sha <sha256 du pilote>]

``--dir`` vaut par défaut le répertoire de ce fichier ; ``--pilot-sha`` le sha256 de ``run_conformite.sh`` à côté.
Code : 0 ssi tous les items sont tenus.
"""

import argparse
from collections.abc import Callable
import hashlib
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PROTOCOL_SHA = "d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6"
MANIFEST_SHA = "9966efade2729f5da6652b0ffa8feda9b127840a77d9a47660823a1e9c50a24b"
KRAKENBOT_SUFFIX = "/runs/c3_racine_registre/conf/repo/src/krakenbot/__init__.py"
HEAD_LINE = "c3bd1e7a0001 (head)"
WORKERS = {1: "4", 2: "1", 3: "4"}
STEPS_OK = "anchor:0,entry:0,benchmark:0,select:0,continuity:0"
ARTEFACTS = (
    "prefix/observations.json",
    "prefix/coverage.json",
    "prefix/candles.json",
    "pre/anchor.json",
    "pre/variants.json",
    "pre/entry.json",
    "pre/entry.md",
    "pre/benchmark.json",
    "pre/selection.json",
    "pre/selection.md",
    "eval/evaluation.json",
    "eval/benchmark_eval.json",
    "eval/candles_eval.json",
    "eval/evaluation_sensitivity.json",
    "chain/anchor.json",
    "chain/entry.json",
    "chain/entry.md",
    "chain/benchmark.json",
    "chain/selection.json",
    "chain/selection.md",
    "chain/continuity.json",
    "chain/verdict.json",
    "chain/variants.json",
)


def parse_status(path: Path) -> dict[str, str]:
    status: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            status[key] = value
    return status


def fields(value: str) -> dict[str, str]:
    """Les paires ``clé=valeur`` d'une valeur de ligne (le premier mot, sans ``=``, est ignoré)."""
    out: dict[str, str] = {}
    for word in value.split():
        key, sep, val = word.partition("=")
        if sep:
            out[key] = val
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--dir", type=Path, default=HERE)
    parser.add_argument("--pilot-sha", default=None)
    args = parser.parse_args()
    pilot_sha = (
        args.pilot_sha or hashlib.sha256((HERE / "run_conformite.sh").read_bytes()).hexdigest()
    )
    status = parse_status(args.dir / "status.txt")

    def s(key: str) -> str:
        return status[key]

    def per_run(check: Callable[[int], bool]) -> bool:
        return all(check(k) for k in (1, 2, 3))

    def gardes() -> bool:
        guard = s("guard")
        f = fields(guard)
        return (
            guard.split()[0] == "0"
            and f.get("sha") == args.sha
            and f.get("krakenbot", "").endswith(KRAKENBOT_SUFFIX)
            and f.get("protocol") == PROTOCOL_SHA
            and f.get("manifest") == MANIFEST_SHA
            and f.get("campaign_unlock") == "absent"
            and s("pilot_sha256") == pilot_sha
            and s("pilot_copy") == "0"
        )

    def base() -> bool:
        before = (args.dir / "alembic_before.txt").read_text(encoding="utf-8")
        after = (args.dir / "alembic_after.txt").read_text(encoding="utf-8")
        return (
            s("alembic_before") == "0"
            and s("alembic_after") == "0"
            and s("alembic_same_head") == "0"
            and before == after
            and HEAD_LINE in before
        )

    def service() -> bool:
        before, after = s("service_before"), s("service_after")
        f = fields(before)
        return (
            before == after
            and f.get("dirty") == "0"
            and f.get("collector") == "active"
            and "NRestarts" in f
            and s("tree_after") == "0"
            and s("campaign_unlock_after") == "absent"
        )

    def prefix() -> bool:
        return per_run(
            lambda k: s(f"workers_{k}") == WORKERS[k]
            and s(f"prefix_{k}").split()[:2] == ["0", "event=-"]
        )

    def chain_1_4() -> bool:
        return per_run(
            lambda k: all(
                s(f"pre_{step}_{k}") == "0" for step in ("anchor", "entry", "benchmark", "select")
            )
        )

    def evaluation() -> bool:
        return per_run(lambda k: s(f"eval_{k}").split()[:2] == ["0", "event=evaluated"])

    def chain_full() -> bool:
        return per_run(
            lambda k: s(f"registry_copy_{k}") == "0"
            and s(f"chain_{k}") == "0"
            and s(f"chain_steps_{k}") == STEPS_OK
            and s(f"chain_verified_{k}") == "true"
            and s(f"violations_empty_{k}") == "true"
            and s(f"replay_violations_empty_{k}") == "true"
            and s(f"extract_{k}") == "0"
            and f"verdict_json_{k}" not in status
            and f"chain_stopped_{k}" not in status
        )

    def interpreter() -> bool:
        return per_run(lambda k: s(f"interpreter_{k}") == "0" and s(f"moved_{k}") == "0")

    def determinism() -> bool:
        eq3 = {key[len("eq3 ") :]: value for key, value in status.items() if key.startswith("eq3 ")}
        return (
            s("listing_expected_3of3") == "0"
            and set(eq3) == set(ARTEFACTS)
            and all(value == "0" for value in eq3.values())
            and s("bit_equal_3of3") == f"0 compared={len(ARTEFACTS)} differing=0 absent=0"
        )

    def pilot_exit() -> bool:
        return (args.dir / "pilot_exit.txt").read_text(encoding="utf-8").strip() == "0"

    items = [
        (
            "1 gardes : guard=0 au SHA S1, krakenbot du clone, protocole v2.3, manifeste déclaré, "
            "CAMPAIGN_UNLOCK absent, pilote = blob S1",
            gardes,
        ),
        ("2 base : alembic 0 avant et après, identiques, c3bd1e7a0001 (head)", base),
        (
            "3 service inchangé (HEAD, 0 ligne sale, collector actif, NRestarts), arbre du clone propre, "
            "CAMPAIGN_UNLOCK absent après",
            service,
        ),
        ("4 producteur préfixe : 0 aux trois exécutions, workers 4 / 1 / 4", prefix),
        ("5 chaîne 1-4 autonome : anchor, entry, benchmark, select en 0, trois fois", chain_1_4),
        ("6 producteur d'évaluation : 0 event=evaluated, trois fois", evaluation),
        (
            "7 chaîne complète : six codes d'étape en 0, chain.verified vrai, violations vides, zéro violation au "
            "rejeu, trois fois",
            chain_full,
        ),
        ("8 interpréteur du clone dans les deux provenances, renommage, trois fois", interpreter),
        (
            "9 déterminisme : liste attendue, 23 artefacts identiques au bit sur les trois exécutions",
            determinism,
        ),
        ("10 pilote : code de sortie 0", pilot_exit),
    ]
    held = 0
    for label, check in items:
        try:
            ok = bool(check())
        except (KeyError, IndexError, OSError):
            ok = False
        held += ok
        print(f"{'tenu ' if ok else 'ÉCART'} — {label}")
    print(
        "11 bornes des lectures : appuis du code, des tests et des codes de la chaîne (attendu § 7) — "
        "aucune lecture d'artefact"
    )
    print(f"{held}/{len(items)} items vérifiables tenus")
    return 0 if held == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
