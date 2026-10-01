"""Première campagne C3 comptée, famille grid-atr-v4 (repris de results/c3_racine_registre/conformite/server/
verify_attendu.py) — vérification de l'attendu déclaré (``../attendu.md``), item par item.

Ne lit que ``status.txt``, les deux ``alembic current`` et ``pilot_exit.txt`` du répertoire donné : aucune sortie du
producteur ni de la chaîne, aucun registre. L'issue et la raison y figurent, tirées par le pilote de la chaîne § L.2
(liste close, plan § 2). **Compté** n'y figure pas : aucun canal ne le publie hors du registre (plan, K2). Il est
**dérivé** ici de ``(issue, raison)`` par la table du § 10.1 de ``docs/CONTRAINTES_POST_B4.md``, recopiée du texte
(``COUNTED_10_1``, ``CONDITIONAL_10_1``) et épinglée aux constantes du code par ``tests/table_10_1.sh`` : dérivé, non
lu (décision Q1 de Bruno). Prouvé avant son premier usage par ``tests/verify_adverse.sh`` (témoin sain à 0, chaque cas
dévié ≠ 0 avec exactement un item en écart).

Usage (depuis la racine du dépôt) ::

    python3 results/c3_campagne_grid/server/verify_attendu.py --sha <S1, 40 hex>
        [--dir <répertoire des preuves>] [--pilot-sha <sha256 du pilote>]

``--dir`` vaut par défaut le répertoire de ce fichier ; ``--pilot-sha`` le sha256 de ``run_campagne.sh`` à côté.
Code : 0 ssi tous les items sont tenus.
"""

import argparse
from collections.abc import Callable
import hashlib
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PROTOCOL_SHA = "d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6"
MANIFEST_SHA = "d422076b09292d8aeb2a6ae3f39b9c37325f23e954c05c6c83a8979255325041"
KRAKENBOT_SUFFIX = "/runs/c3_campagne_grid/campagne/repo/src/krakenbot/__init__.py"
HEAD_LINE = "c3bd1e7a0001 (head)"
WORKERS = "3"
#: A1 : cinq codes d'étape, ceux de ``c3_verdict.CHAIN_FILES`` (scripts/audit/c3_verdict.py:2016) ; le code de la
#: chaîne elle-même (clé ``chain``) est celui que rend le verdict, pas un sixième pas.
STEPS_OK = "anchor:0,entry:0,benchmark:0,select:0,continuity:0"
#: L'attendu déclaré : issue, raison, compté.
EXPECTED_TRIPLET = ("inconclusif", "P_PROVENANCE", False)
#: ``docs/CONTRAINTES_POST_B4.md`` § 10.1 (section d'origine), recopiée du texte : le statut compté de chaque issue que
#: la chaîne publie, par ``(issue, raison)`` telles que la chaîne § L.2 les écrit (``raison=-`` hors ``inconclusif``).
COUNTED_10_1: dict[tuple[str, str], bool] = {
    ("validé", "-"): True,
    ("réfuté", "-"): True,
    ("inconclusif", "A_BELOW_FLOOR"): True,
    ("inconclusif", "F_NOT_ESTIMABLE"): True,
    ("inconclusif", "F_CANNOT_SEPARATE"): True,
    ("inconclusif", "R0_INVALID_RUN"): False,
    ("inconclusif", "P_PROVENANCE"): False,
    ("inconclusif", "D_WARMUP_PREFIX"): False,
    ("inconclusif", "D_WARMUP_ANCHOR"): False,
    ("inconclusif", "R1_NOT_NORMALISED"): False,
    ("inconclusif", "E_NO_BENCHMARK"): False,
    ("inconclusif", "E_STAMP_MISMATCH"): False,
}
#: § 10.1, ligne conditionnelle : compté si et seulement si aucun candidat n'a été retiré par l'une de ces clauses —
#: non dérivable sans lire la sélection, donc ``indéterminé`` ici (un écart à l'attendu).
CONDITIONAL_10_1: dict[tuple[str, str], tuple[str, ...]] = {
    ("inconclusif", "A_NO_ADMISSIBLE_CANDIDATE"): ("D1", "D2", "D6"),
}


def counted(issue: str, reason: str) -> bool | None:
    """Le statut compté dérivé de ``(issue, raison)`` par la table du § 10.1 ; ``None`` quand la table ne le donne pas
    sans lecture (ligne conditionnelle, ou couple hors table)."""
    return COUNTED_10_1.get((issue, reason))


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
        args.pilot_sha or hashlib.sha256((HERE / "run_campagne.sh").read_bytes()).hexdigest()
    )
    status = parse_status(args.dir / "status.txt")

    def s(key: str) -> str:
        return status[key]

    def gardes() -> bool:
        guard = s("guard")
        f = fields(guard)
        return (
            guard.split()[0] == "0"
            and f.get("sha") == args.sha
            and f.get("krakenbot", "").endswith(KRAKENBOT_SUFFIX)
            and f.get("protocol") == PROTOCOL_SHA
            and f.get("manifest") == MANIFEST_SHA
            and f.get("campaign_unlock") == "present"
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
            and s("campaign_unlock_after") == "present"
        )

    def prefix() -> bool:
        return s("workers") == WORKERS and s("prefix").split()[:2] == ["0", "event=-"]

    def chain_1_4() -> bool:
        return (
            all(s(f"pre_{step}") == "0" for step in ("anchor", "entry", "benchmark", "select"))
            and s("registry_new_entry_pre") == "true"
        )

    def evaluation() -> bool:
        return s("eval").split()[:2] == ["0", "event=evaluated"]

    def chain_full() -> bool:
        return (
            s("chain").split()[0] == "0"
            and s("chain_steps") == STEPS_OK
            and s("chain_verified") == "true"
            and s("violations_empty") == "true"
            and s("replay_violations_empty") == "true"
            and s("registry_new_entry_chain") == "false"
            and s("issue_inscrite") == "true"
            and s("extract") == "0"
            and "verdict_json" not in status
            and "chain_stopped" not in status
        )

    def issue() -> bool:
        pair = (s("issue"), s("raison"))
        return (
            pair == EXPECTED_TRIPLET[:2]
            and counted(*pair) is EXPECTED_TRIPLET[2]
            and s("selection_descriptive") == "true"
        )

    def interpreter() -> bool:
        return s("interpreter") == "0"

    def no_halt() -> bool:
        return s("halted_at") == "-" and not any(
            value == "NOT_RUN" or value.startswith("NOT_RUN ") for value in status.values()
        )

    def pilot_exit() -> bool:
        return (args.dir / "pilot_exit.txt").read_text(encoding="utf-8").strip() == "0"

    items: list[tuple[str, Callable[[], bool]]] = [
        (
            "1 gardes : guard=0 au SHA S1, krakenbot du clone, protocole v2.3, manifeste gelé, "
            "CAMPAIGN_UNLOCK présent, pilote = blob S1",
            gardes,
        ),
        ("2 base : alembic 0 avant et après, identiques, c3bd1e7a0001 (head)", base),
        (
            "3 service inchangé (HEAD, 0 ligne sale, collector actif, NRestarts), arbre du clone propre, "
            "CAMPAIGN_UNLOCK présent après",
            service,
        ),
        ("4 producteur préfixe : 0, event=-, workers 3", prefix),
        (
            "5 chaîne 1-4 autonome : anchor, entry, benchmark, select en 0 ; première inscription au registre "
            "(registry.new_entry vrai)",
            chain_1_4,
        ),
        ("6 producteur d'évaluation : 0 event=evaluated", evaluation),
        (
            "7 chaîne complète : code 0, cinq codes d'étape en 0 (c3_verdict.CHAIN_FILES), chain.verified vrai, "
            "violations vides, zéro violation au rejeu, ancrage idempotent, issue inscrite",
            chain_full,
        ),
        (
            "8 issue : inconclusif, P_PROVENANCE, non compté (dérivé du § 10.1) ; sélection SÉLECTION_DESCRIPTIVE",
            issue,
        ),
        ("9 interpréteur du clone dans les deux provenances", interpreter),
        ("10 aucun arrêt : halted_at=-, aucune étape NOT_RUN", no_halt),
        ("11 pilote : code de sortie 0", pilot_exit),
    ]
    held = 0
    for label, check in items:
        try:
            ok = bool(check())
        except (KeyError, IndexError, OSError):
            ok = False
        held += ok
        print(f"{'tenu ' if ok else 'ÉCART'} — {label}")
    found = (status.get("issue", "absent"), status.get("raison", "absent"))
    derived = counted(*found)
    compte = "oui" if derived is True else "non" if derived is False else "indéterminé"
    print(
        f"triplet constaté : issue={found[0]} raison={found[1]} compté={compte} "
        "(compté dérivé de (issue, raison) par la table du § 10.1, non lu)"
    )
    print(
        "déclarés, jamais vérifiés : aucune évaluation différée inscrite ; contenu du registre (racine préservée, "
        "compte inscrit) ; bornes des lectures — appuis du code, des tests et des codes de la chaîne (attendu § 8)"
    )
    print(f"{held}/{len(items)} items vérifiables tenus")
    return 0 if held == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
