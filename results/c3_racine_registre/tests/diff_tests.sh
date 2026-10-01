#!/bin/bash
# C3 racine du registre, lot 1 — diff des tests contre la base 313eb00 (dev au merge de l'outillage v2.3), par l'AST
# (commentaires et mise en forme ignorés). Repris de results/c3_outillage_v2_3/tests/diff_tests.sh (listes du plan,
# § 3 et D4). Usage : bash diff_tests.sh <étiquette>. Sortie : diff_tests_<étiquette>.out. Pour chaque fonction de
# niveau module des fichiers de tests C3 : corps et signature (décorateurs exclus) et décorateurs comparés à la base.
# Règles (brief § 3.3 : « corps des tests existants intacts hors liste déclarée ») :
#  1. aucune fonction de la base supprimée ni renommée ;
#  2. aucun test xfail de la base touché (le caduc garde corps et décorateurs) ;
#  3. toute fonction existante au corps ou aux décorateurs modifiés appartient à la liste déclarée (vide ici) ;
#  4. toute fonction neuve appartient à la liste déclarée (les cinq tests du plan § 3) ;
#  5. les affectations de niveau module retirées, ajoutées ou modifiées appartiennent à la liste déclarée (la constante
#     `REGISTRY_ROOT_SYNTHETIC` de `fx`, plan D4).
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
MODE="${2:-final}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_racine_registre/tests/diff_tests_${LABEL}.out
{
  echo "# diff des tests — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base 313eb00"
} > "$OUT"
poetry run python - "$OUT" "$MODE" <<'PY'
import ast
import subprocess
import sys

OUT = sys.argv[1]
PARTIAL = sys.argv[2] == "partiel"
BASE = "313eb00c2019b98cf20fb81ac8327f7b9d1e920a"
T = "tests/test_scripts/"
FILES = [
    T + "test_c3_anchor.py",
    T + "test_c3_benchmark.py",
    T + "test_c3_chronology.py",
    T + "test_c3_common.py",
    T + "test_c3_continuity.py",
    T + "test_c3_entry.py",
    T + "test_c3_select.py",
    T + "test_c3_verdict.py",
    T + "test_c3b_common.py",
    T + "test_c3b_evaluate.py",
    T + "test_c3b_prefix.py",
]
#: Aucun marqueur à lever, aucun renommage, aucun corps existant modifié (plan § 3, D9).
LIFTED: set[tuple[str, str]] = set()
RENAMED: dict[tuple[str, str], str] = {}
DECLARED_BODY: dict[str, dict[str, str]] = {}
#: Plan § 3 — les cinq tests neufs, déclarés.
DECLARED_NEW = {
    T + "test_c3_anchor.py": {
        "test_A6_la_racine_du_registre_survit_a_l_ancrage_enregistrement_idempotence_enfant",
        "test_R22_un_non_fini_a_la_racine_du_registre_est_un_diagnostic",
    },
    T + "test_c3_verdict.py": {
        "test_A6_la_racine_du_registre_traverse_l_ancrage_et_l_inscription_du_verdict",
        "test_A6_registry_inscription_preserve_les_cles_de_racine",
        "test_A6_v23_les_instants_de_D_sont_normalises_un_instant_pas_une_graphie",
    },
}
#: Plan D4 — la racine synthétique, une constante de `fx`.
DECLARED_ASSIGN_ADDED: set[tuple[str, str]] = {(T + "test_c3_common.py", "REGISTRY_ROOT_SYNTHETIC")}
DECLARED_ASSIGN_REMOVED: set[tuple[str, str]] = set()
DECLARED_ASSIGN_MODIFIED: set[tuple[str, str]] = set()


def functions(src):
    tree = ast.parse(src)
    out, assigns = {}, {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            sig = ast.dump(node.args) + (ast.dump(node.returns) if node.returns else "")
            decos = [ast.dump(d) for d in node.decorator_list]
            out[node.name] = (sig + body, decos)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    assigns[t.id] = ast.dump(node.value) if node.value is not None else ""
    return out, assigns


def is_xfail(deco: str) -> bool:
    return "attr='xfail'" in deco


log = open(OUT, "a", encoding="utf-8")
say = lambda s: log.write(s + "\n")
bad = 0
lifted_seen = set()
for f in FILES:
    base_src = subprocess.run(["git", "show", f"{BASE}:{f}"], capture_output=True, text=True, check=True).stdout
    head_src = open(f, encoding="utf-8").read()
    bf, ba = functions(base_src)
    hf, ha = functions(head_src)
    base_xfail = {n for n, (_, d) in bf.items() if any(is_xfail(x) for x in d)}
    renamed_new = {new for (ff, _old), new in RENAMED.items() if ff == f}
    say(f"## {f}")
    say(f"  fonctions base={len(bf)} head={len(hf)} ; xfail de la base={len(base_xfail)}")
    for n in sorted(set(bf) - set(hf)):
        new = RENAMED.get((f, n))
        if new is not None and new in hf and hf[new] == bf[n]:
            say(f"  renommé (D9), nœud identique : {n} → {new}")
        else:
            say(f"  SUPPRIMÉE (interdit) : {n}")
            bad = 1
    for n in sorted(set(hf) - set(bf)):
        if n in renamed_new:
            continue
        ok = n in DECLARED_NEW.get(f, set())
        say(f"  neuve {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}")
        bad |= not ok
    for n in sorted(set(bf) & set(hf)):
        body_changed = bf[n][0] != hf[n][0]
        deco_changed = bf[n][1] != hf[n][1]
        if (f, n) in LIFTED:
            if PARTIAL and not body_changed and not deco_changed:
                say(f"  X encore marqué (partiel) : {n}")
                continue
            lifted_seen.add((f, n))
            expected = [d for d in bf[n][1] if not is_xfail(d)]
            ok = not body_changed and hf[n][1] == expected and len(expected) == len(bf[n][1]) - 1
            say(f"  X levé : {n} — corps {'identique' if not body_changed else 'MODIFIÉ'}, "
                f"décorateurs {'= base moins xfail' if hf[n][1] == expected else 'NON CONFORMES'}")
            bad |= not ok
            continue
        if n in base_xfail and (body_changed or deco_changed):
            say(f"  XFAIL DE LA BASE TOUCHÉ (interdit) : {n}")
            bad = 1
            continue
        if body_changed or deco_changed:
            why = DECLARED_BODY.get(f, {}).get(n)
            if why is not None and not deco_changed:
                say(f"  corps modifié, déclaré : {n} — {why}")
            else:
                say(f"  MODIFIÉ NON DÉCLARÉ (corps={body_changed}, décorateurs={deco_changed}) : {n}")
                bad = 1
    for n in sorted(set(ba) - set(ha)):
        ok = (f, n) in DECLARED_ASSIGN_REMOVED
        say(f"  affectation retirée {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}")
        bad |= not ok
    for n in sorted(set(ha) - set(ba)):
        ok = (f, n) in DECLARED_ASSIGN_ADDED
        say(f"  affectation ajoutée {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}")
        bad |= not ok
    for n in sorted(set(ba) & set(ha)):
        if ba[n] != ha[n]:
            ok = (f, n) in DECLARED_ASSIGN_MODIFIED
            say(f"  affectation modifiée {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}")
            bad |= not ok
missing = set() if PARTIAL else LIFTED - lifted_seen
for f, n in sorted(missing):
    say(f"  X ATTENDU ABSENT : {f}::{n}")
say(f"x_leves_vus={len(lifted_seen)} sur {len(LIFTED)}")
bad |= bool(missing)
say(f"rc={1 if bad else 0}")
sys.exit(1 if bad else 0)
PY
exit $?
