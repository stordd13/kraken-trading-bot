#!/bin/bash
# C3 outillage v2.2 — diff des tests contre 8c114fe, par l'AST (commentaires et mise en forme ignorés).
# Usage : bash diff_tests.sh <étiquette>. Sortie : diff_tests_<étiquette>.out.
# Pour chaque fonction de niveau module des fichiers de tests C3 : corps (décorateurs exclus) et décorateurs comparés
# à la base. Règles (brief, critère de fin ; plan du lot 1) :
#  1. aucune fonction de la base supprimée ;
#  2. les 46 tests xfail de la base : corps identique (seuls les décorateurs changent : marqueur retiré, ou re-marqué
#     pour le test caduc) ;
#  3. toute autre fonction au corps modifié appartient à la liste déclarée (fixtures, D4, D10, D11) ;
#  4. toute fonction neuve appartient à la liste déclarée ;
#  5. les affectations de niveau module retirées ou ajoutées appartiennent à la liste déclarée.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_2/tests/diff_tests_${LABEL}.out
{
  echo "# diff des tests — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base 8c114fe"
} > "$OUT"
poetry run python - "$OUT" <<'PY'
import ast
import subprocess
import sys

OUT = sys.argv[1]
BASE = "8c114fe"
FILES = [
    "tests/test_scripts/test_c3_anchor.py",
    "tests/test_scripts/test_c3_benchmark.py",
    "tests/test_scripts/test_c3_chronology.py",
    "tests/test_scripts/test_c3_common.py",
    "tests/test_scripts/test_c3_continuity.py",
    "tests/test_scripts/test_c3_entry.py",
    "tests/test_scripts/test_c3_select.py",
    "tests/test_scripts/test_c3_verdict.py",
    "tests/test_scripts/test_c3b_common.py",
    "tests/test_scripts/test_c3b_evaluate.py",
    "tests/test_scripts/test_c3b_prefix.py",
]
# Fonctions au corps modifié, déclarées (plan du lot 1 § 2 et décisions de gate).
DECLARED_BODY = {
    "tests/test_scripts/test_c3_common.py": {
        "manifest": "fixture : famille (R-17)",
        "evaluation": "fixture : equity composée, returns_config recalculé, lambdas (R-15, D1)",
        "benchmark_eval": "fixture : nav (R-15, D1)",
        "test_les_listes_de_champs_optionnels_et_nullables_sont_closes_et_nommees": "D10 : listes épinglées",
    },
    "tests/test_scripts/test_c3_verdict.py": {
        "_reseries": "fixture : séries composées ; monde R-15 : séries seules (D2)",
        "_artifacts": "fixture : séries composées, equity_daily, lambdas",
        "_write_cli_inputs": "fixture : quatre entrées v2.2, empreintes réelles, argv (D4)",
        "_chain_world": "fixture : λ de la chaîne sonde, export d'évaluation, blend",
        "_chain_argv": "fixture : --candles-eval",
        "_v22_world": "fixture : entrée manifest, estimable, entrées posées avant _reseries",
        "test_le_parseur_n_expose_que_des_chemins_et_un_horodatage": "D4 : parseur de l'étape 6",
    },
    "tests/test_scripts/test_c3b_evaluate.py": {
        "continuity": "fixture : NAV du comparateur synthétique = celle du producteur",
        "test_the_full_chain_verifies_a_produced_evaluation": "D11 : --candles-eval",
    },
}
DECLARED_NEW = {
    "tests/test_scripts/test_c3_common.py": {"equity_of", "returns_of", "bh_nav"},
    "tests/test_scripts/test_c3_verdict.py": {
        "_on_grid",
        "_producer_inputs",
        "test_A1_la_cli_du_verdict_recoupe_ce_que_le_producteur_garantit",
        "test_R17_la_table_du_10_1_est_celle_du_texte",
        "test_A2_une_reinscription_discordante_au_registre_est_une_violation",
    },
    "tests/test_scripts/test_c3_anchor.py": {
        "test_R17_temoin_sur_une_famille_close_l_empreinte_differee_attendue_est_acceptee"
    },
}
DECLARED_ASSIGN_REMOVED = {
    ("tests/test_scripts/test_c3_verdict.py", "R15"),
    ("tests/test_scripts/test_c3b_evaluate.py", "R15"),
    ("tests/test_scripts/test_c3_anchor.py", "R17"),
    ("tests/test_scripts/test_c3_benchmark.py", "R21"),
    ("tests/test_scripts/test_c3_select.py", "R21"),
}
DECLARED_ASSIGN_ADDED = {("tests/test_scripts/test_c3_verdict.py", "TABLE_10_1")}
# Décorateurs modifiés sans retrait : le test caduc re-marqué (décision de gate du 29/09).
DECLARED_REMARK = {("tests/test_scripts/test_c3b_evaluate.py", "test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3")}


def functions(src):
    tree = ast.parse(src)
    out, assigns = {}, {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            sig = ast.dump(node.args) + ast.dump(node.returns) if node.returns else ast.dump(node.args)
            decos = [ast.dump(d) for d in node.decorator_list]
            out[node.name] = (sig + body, decos)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    assigns[t.id] = ast.dump(node.value) if node.value is not None else ""
    return out, assigns


def is_xfail(decos):
    return any("xfail" in d or "id='R1" in d or "id='R2" in d or "id='R18'" in d for d in decos)


log = open(OUT, "a", encoding="utf-8")
say = lambda s: log.write(s + "\n")
bad = 0
for f in FILES:
    base_src = subprocess.run(["git", "show", f"{BASE}:{f}"], capture_output=True, text=True, check=True).stdout
    head_src = open(f, encoding="utf-8").read()
    bf, ba = functions(base_src)
    hf, ha = functions(head_src)
    base_xfail = {n for n, (_, d) in bf.items() if is_xfail(d)}
    removed = sorted(set(bf) - set(hf))
    added = sorted(set(hf) - set(bf))
    body_changed = sorted(n for n in set(bf) & set(hf) if bf[n][0] != hf[n][0])
    deco_changed = sorted(n for n in set(bf) & set(hf) if bf[n][1] != hf[n][1])
    say(f"## {f}")
    say(f"  fonctions base={len(bf)} head={len(hf)} ; xfail de la base={len(base_xfail)}")
    for n in removed:
        say(f"  SUPPRIMÉE (interdit) : {n}"); bad = 1
    for n in added:
        ok = n in DECLARED_NEW.get(f, set())
        say(f"  neuve {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}"); bad |= not ok
    for n in body_changed:
        if n in base_xfail:
            say(f"  CORPS D'UN TEST XFAIL MODIFIÉ (interdit) : {n}"); bad = 1
        elif n in DECLARED_BODY.get(f, {}):
            say(f"  corps modifié, déclaré : {n} — {DECLARED_BODY[f][n]}")
        else:
            say(f"  CORPS MODIFIÉ NON DÉCLARÉ : {n}"); bad = 1
    for n in deco_changed:
        lifted = n in base_xfail and not is_xfail(hf[n][1])
        remark = (f, n) in DECLARED_REMARK
        tag = "marqueur retiré" if lifted else ("re-marqué, déclaré (caduc)" if remark else "DÉCORATEUR MODIFIÉ NON DÉCLARÉ")
        say(f"  décorateur : {n} — {tag}")
        bad |= not (lifted or remark)
    for n in sorted(set(ba) - set(ha)):
        ok = (f, n) in DECLARED_ASSIGN_REMOVED
        say(f"  affectation retirée {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}"); bad |= not ok
    for n in sorted(set(ha) - set(ba)):
        ok = (f, n) in DECLARED_ASSIGN_ADDED
        say(f"  affectation ajoutée {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}"); bad |= not ok
    for n in sorted(set(ba) & set(ha)):
        if ba[n] != ha[n]:
            say(f"  AFFECTATION MODIFIÉE NON DÉCLARÉE : {n}"); bad = 1
say(f"rc={1 if bad else 0}")
sys.exit(1 if bad else 0)
PY
rc=$?
exit $rc
