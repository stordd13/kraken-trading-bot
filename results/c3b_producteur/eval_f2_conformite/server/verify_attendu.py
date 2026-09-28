"""C3b lot 4b — vérification de l'attendu (``../ATTENDU.md``), item par item, sur ``status.txt``, les deux ``alembic
current`` et ``pilot_exit.txt`` **seulement** : aucune sortie du producteur ni de la chaîne n'est lue (décision 2 du
28/09 : l'issue n'est pas lue).

Usage (depuis la racine du dépôt) : ``python results/c3b_producteur/eval_f2_conformite/server/verify_attendu.py``
"""

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EXPECTED_SHA = "459190a222bb24aface23c46d80b2d879795a49c"
PILOT_SHA = "9b401797639bc9b1928aa952257a67c9742f471244f9de7547d1d25f637f9cc8"
HEAD = "c3bd1e7a0001 (head)"

status: dict[str, str] = {}
for line in (HERE / "status.txt").read_text(encoding="utf-8").splitlines():
    key, _, value = line.partition("=")
    status[key] = value


def first(key: str) -> str:
    return status[key].split()[0]


items: list[tuple[str, bool]] = [
    (
        "1 gardes : guard=0 au SHA du commit 2, entrées du lot 3, pilote consigné",
        first("guard") == "0"
        and f"sha={EXPECTED_SHA}" in status["guard"]
        and "lot3_candles=0" in status["guard"]
        and "registry=0" in status["guard"]
        and "/runs/c3b_eval4b/repo/src/krakenbot/__init__.py" in status["guard"]
        and status["pilot_sha256"] == PILOT_SHA,
    ),
    (
        "2 producteur : 0/0 evaluated, evaluation.json au bit, trois autres artefacts au bit, interpréteur du clone",
        status["eval_run1"].startswith("0 event=evaluated")
        and status["eval_run2"].startswith("0 event=evaluated")
        and status["eval_bit_equal"] == "0"
        and status["outputs_bit_equal"] == "0"
        and status["interpreter_check"] == "0",
    ),
    (
        "3 chaîne complète : six étapes en 0, chain.verified vrai, zéro violation, zéro violation au rejeu",
        status["chain_steps"] == "anchor:0,entry:0,benchmark:0,select:0,continuity:0"
        and status["chain_exit"] == "0"
        and status["chain_verified"] == "true"
        and status["verdict_violations"] == "0"
        and status["replay_violations"] == "0"
        and status["extract"] == "0",
    ),
    (
        "4 base : alembic identique avant et après, c3bd1e7a0001 (head)",
        status["alembic_before"] == "0"
        and status["alembic_after"] == "0"
        and (HERE / "alembic_before.txt").read_text(encoding="utf-8")
        == (HERE / "alembic_after.txt").read_text(encoding="utf-8")
        and HEAD in (HERE / "alembic_before.txt").read_text(encoding="utf-8"),
    ),
    (
        "pilote : code de sortie 0",
        (HERE / "pilot_exit.txt").read_text(encoding="utf-8").strip() == "0",
    ),
]
for label, ok in items:
    print(f"{'tenu ' if ok else 'ÉCART'} — {label}")
print(
    "5 bornes des lectures : appuis du code, des tests et des codes de la chaîne (ATTENDU § 5) — "
    "aucune lecture d'artefact"
)
held = sum(ok for _, ok in items)
print(f"{held}/{len(items)} items vérifiables tenus")
sys.exit(0 if held == len(items) else 1)
