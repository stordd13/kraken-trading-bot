#!/bin/bash
# C3 outillage v2.3, lot 1 — diff des tests contre la base b50f2d1 (tip du gel mergé), par l'AST (commentaires et mise
# en forme ignorés). Repris de results/c3_outillage_v2_2/tests/diff_tests.sh. Usage : bash diff_tests.sh <étiquette>.
# Sortie : diff_tests_<étiquette>.out. Second argument `partiel` (commits intermédiaires) : un X encore marqué, corps
# et décorateurs identiques à la base, est admis ; sans lui (fin de lot), les huit doivent être levés. Pour chaque
# fonction de niveau module des fichiers de tests C3 : corps et signature (décorateurs exclus) et décorateurs comparés
# à la base. Règles (brief § 3.2 ; plan du lot 1 § 1, D8-D10) :
#  1. aucune fonction de la base supprimée, sauf le test renommé (D9), dont le nœud entier (signature, corps,
#     décorateurs) est identique sous son nom neuf ;
#  2. les huit tests X (sept X + le témoin R-17) : corps identique ; décorateurs = ceux de la base moins le seul
#     marqueur `xfail` ;
#  3. aucun autre test xfail de la base touché (le caduc garde corps et décorateurs) ;
#  4. toute autre fonction au corps ou aux décorateurs modifiés appartient à la liste déclarée ;
#  5. toute fonction neuve appartient à la liste déclarée ;
#  6. les affectations de niveau module retirées, ajoutées ou modifiées appartiennent à la liste déclarée.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
MODE="${2:-final}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_3/tests/diff_tests_${LABEL}.out
{
  echo "# diff des tests — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base b50f2d1"
} > "$OUT"
poetry run python - "$OUT" "$MODE" <<'PY'
import ast
import subprocess
import sys

OUT = sys.argv[1]
PARTIAL = sys.argv[2] == "partiel"
BASE = "b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9"
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
#: Les huit marqueurs levés (brief § 3.1 ; paquet v2.3, réserves X1-X8).
LIFTED = {
    (T + "test_c3_anchor.py", "test_X1_un_manifeste_sans_date_d_evaluation_differee_est_refuse_a_l_etape_1"),
    (T + "test_c3_anchor.py", "test_X2_une_date_trop_proche_ou_illisible_est_refusee_365_jours_exactement_passent"),
    (T + "test_c3_anchor.py", "test_R17_temoin_sur_une_famille_close_l_empreinte_differee_attendue_est_acceptee"),
    (T + "test_c3_common.py", "test_X8_load_manifest_lit_la_date_differee_et_refuse_toute_forme_invalide"),
    (T + "test_c3_verdict.py", "test_X3_l_issue_qui_ouvre_la_voie_inscrit_la_date_du_manifeste_et_l_empreinte_du_descripteur"),
    (T + "test_c3_verdict.py", "test_X4_une_issue_qui_n_ouvre_pas_la_voie_n_inscrit_aucune_evaluation_differee"),
    (T + "test_c3_verdict.py", "test_X5_le_descripteur_est_derive_champ_par_champ_selon_le_tableau_du_texte"),
    (T + "test_c3_verdict.py", "test_X7_le_verdict_d_une_variante_differee_n_inscrit_jamais_d_evaluation_differee"),
}
#: D9 — le renommage, nom seul (Application v2.3, point 2).
RENAMED = {
    (T + "test_c3_entry.py", "test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_v21"):
    "test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_le_protocole_courant",
}
#: D8 — fonctions au corps modifié, déclarées.
DECLARED_BODY = {
    T + "test_c3_common.py": {
        "manifest": "D8 : `deferred_evaluation.date` par défaut, 365 j après la fin de fenêtre (§ A.6 v2.3)",
    },
    T + "test_c3_anchor.py": {
        "_campaign_v21_manifest": "D8 : fenêtre v2.1 (fin 2026-06-29) — la date re-déclarée par `fx.with_deferred_date`",
    },
}
#: D10 — tests neufs (et leurs aides), déclarés.
DECLARED_NEW = {
    T + "test_c3_anchor.py": {
        "test_A6_v23_sur_une_famille_close_le_descripteur_entrant_suit_la_regle_du_run_differe",
    },
    T + "test_c3_verdict.py": {
        "test_A6_v23_le_predicat_d_ouverture_suit_le_10_1_conjonctif_par_conjonctif",
        "test_A6_v23_une_evaluation_differee_inscrite_differente_est_une_violation_sans_empreinte_imprimee",
        "test_A6_v23_tout_champ_hors_de_la_table_est_hors_engagement",
    },
}
DECLARED_ASSIGN_ADDED = {
    (T + "test_c3_verdict.py", "TABLE_10_1_VOIE"),
}
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
