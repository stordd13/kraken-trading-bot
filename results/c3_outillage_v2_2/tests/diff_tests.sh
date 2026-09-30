#!/bin/bash
# C3 outillage v2.2 — diff des tests contre 8c114fe, par l'AST (commentaires et mise en forme ignorés).
# Usage : bash diff_tests.sh <étiquette>. Sortie : diff_tests_<étiquette>.out.
# Pour chaque fonction de niveau module des fichiers de tests C3 : corps (décorateurs exclus) et décorateurs comparés
# à la base. Règles (brief, critère de fin ; plan du lot 1) :
#  1. aucune fonction de la base supprimée ;
#  2. les 46 tests xfail de la base : corps identique (seuls les décorateurs changent : marqueur retiré, ou re-marqué
#     pour le test caduc) ;
#  3. toute autre fonction au corps modifié appartient à la liste déclarée (fixtures, D4, D10, D11 ; lot 2 : § 5 du
#     plan, D1, D8, D11) ;
#  4. toute fonction neuve appartient à la liste déclarée ;
#  5. les affectations de niveau module retirées, ajoutées ou modifiées appartiennent à la liste déclarée ;
#  6. (lot 2) un décorateur modifié sans retrait de marqueur appartient à la liste déclarée (D11 : paramètre renommé,
#     identifiant gardé).
# Les déclarations sont cumulées : lot 1 puis lot 2, toutes contre 8c114fe.
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
# Fonctions au corps modifié, déclarées (plan du lot 1 § 2 et décisions de gate ; plan du lot 2 § 5).
DECLARED_BODY = {
    "tests/test_scripts/test_c3_common.py": {
        "manifest": "fixture : famille (R-17) ; lot 2 : min_order_quote (R-16)",
        "evaluation": "fixture : equity composée, returns_config recalculé, lambdas (R-15, D1) ; lot 2 : metrics.executions (R-19, D8)",
        "benchmark_eval": "fixture : nav (R-15, D1)",
        "test_les_listes_de_champs_optionnels_et_nullables_sont_closes_et_nommees": "D10 : listes épinglées ; lot 2 : refused, executions, first_day, last_day (obligation d)",
        "observation": "lot 2 : fixture, min_order_quote (R-16)",
        "liquidation_segment": "lot 2 : fixture, gross_quote au bloc et aux lots (R-16)",
    },
    "tests/test_scripts/test_c3_select.py": {
        "test_revue_R3_gross_different_de_amount_x_price_ne_passe_pas_D6": "lot 2 : clés gross_quote de la fixture (R-16, D11)",
    },
    "tests/test_scripts/test_c3_verdict.py": {
        "_reseries": "fixture : séries composées ; monde R-15 : séries seules (D2)",
        "_artifacts": "fixture : séries composées, equity_daily, lambdas",
        "_write_cli_inputs": "fixture : quatre entrées v2.2, empreintes réelles, argv (D4)",
        "_chain_world": "fixture : λ de la chaîne sonde, export d'évaluation, blend",
        "_chain_argv": "fixture : --candles-eval",
        "_v22_world": "fixture : entrée manifest, estimable, entrées posées avant _reseries",
        "test_le_parseur_n_expose_que_des_chemins_et_un_horodatage": "D4 : parseur de l'étape 6",
        "_carry": "lot 2 : les témoins reçoivent metrics.executions (R-19, D8, liste close)",
    },
    "tests/test_scripts/test_c3b_evaluate.py": {
        "continuity": "fixture : NAV du comparateur synthétique = celle du producteur",
        "test_the_full_chain_verifies_a_produced_evaluation": "D11 : --candles-eval",
        "test_a_non_buildable_comparator_stops_before_the_engine": "lot 2, D1 (GO du 29/09) : la ligne « rien d'écrit » (attendu v2.1) retirée",
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
# Lot 2 : les quinze tests neufs du plan (§ 4) et une aide.
DECLARED_NEW_LOT2 = {
    "tests/test_scripts/test_c3_entry.py": {"test_R16_un_lot_qui_porte_gross_usdc_refuse_l_entree_a_la_forme"},
    "tests/test_scripts/test_c3_continuity.py": {
        "test_R16_un_bloc_de_liquidation_d_evaluation_qui_porte_gross_usdc_est_une_erreur_de_forme",
        "test_R18_une_evaluation_executee_sans_comparateur_d_evaluation_est_refusee",
    },
    "tests/test_scripts/test_c3b_common.py": {
        "test_R16_un_montant_gross_hors_table_de_renommage_est_un_controle_en_echec"
    },
    "tests/test_scripts/test_c3_verdict.py": {
        "test_R18_les_motifs_et_la_raison_du_refus_sont_ceux_du_texte",
        "test_R18_un_comparateur_non_comparable_porte_le_motif_comparator_not_comparable",
        "test_R18_l_identite_du_refus_est_recoupee_avant_toute_lecture_du_bloc_refused",
        "test_R18_la_chaine_sur_une_forme_de_refus_n_exige_pas_le_comparateur_d_evaluation",
        "test_R19_un_premier_remplissage_avec_zero_execution_est_une_violation",
        "test_R19_zero_execution_et_equity_constante_differente_de_C_est_une_violation",
        "test_R19_zero_execution_equity_non_constante_rendements_coherents_est_une_violation",
        "_violations_of",
    },
    "tests/test_scripts/test_c3b_evaluate.py": {
        "test_R18_the_refusal_form_exits_0_and_writes_only_its_artefacts",
        "test_R19_executions_is_the_number_of_fills",
        "test_hors_R_an_exception_in_build_pair_is_a_control_error_3",
    },
    "tests/test_scripts/test_c3_select.py": {"test_R20_une_serie_sans_unite_couverte_retire_la_paire_par_D1"},
}
for _f, _names in DECLARED_NEW_LOT2.items():
    DECLARED_NEW.setdefault(_f, set()).update(_names)
DECLARED_ASSIGN_REMOVED = {
    ("tests/test_scripts/test_c3_verdict.py", "R15"),
    ("tests/test_scripts/test_c3b_evaluate.py", "R15"),
    ("tests/test_scripts/test_c3_anchor.py", "R17"),
    ("tests/test_scripts/test_c3_benchmark.py", "R21"),
    ("tests/test_scripts/test_c3_select.py", "R21"),
}
DECLARED_ASSIGN_REMOVED |= {
    ("tests/test_scripts/test_c3_chronology.py", "R16"),
    ("tests/test_scripts/test_c3_anchor.py", "R16"),
    ("tests/test_scripts/test_c3_entry.py", "R16"),
    ("tests/test_scripts/test_c3b_common.py", "R16"),
    ("tests/test_scripts/test_c3_verdict.py", "R18"),
    ("tests/test_scripts/test_c3b_evaluate.py", "R18"),
    ("tests/test_scripts/test_c3_continuity.py", "R19"),
    ("tests/test_scripts/test_c3_verdict.py", "R19"),
    ("tests/test_scripts/test_c3b_evaluate.py", "R19"),
    ("tests/test_scripts/test_c3_entry.py", "R20"),
    ("tests/test_scripts/test_c3b_common.py", "R20"),
}
DECLARED_ASSIGN_ADDED = {
    ("tests/test_scripts/test_c3_verdict.py", "TABLE_10_1"),
    ("tests/test_scripts/test_c3_verdict.py", "REFUSAL_REASON_C5"),
    ("tests/test_scripts/test_c3_verdict.py", "MOTIFS_C5"),
}
# Lot 2 : affectation modifiée, déclarée (liste close : les témoins (i) reçoivent le porteur, R-19).
DECLARED_ASSIGN_MODIFIED = {("tests/test_scripts/test_c3_verdict.py", "REAL_CARRIERS_L1")}
# Lot 2 : décorateur modifié sans retrait de marqueur, déclaré (D11 : lambda du paramètre renommée, id gardé).
DECLARED_DECO = {("tests/test_scripts/test_c3_select.py", "test_chaque_identite_exacte_de_D6_fausse_retire_le_candidat")}
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
        deco = (f, n) in DECLARED_DECO
        tag = (
            "marqueur retiré"
            if lifted
            else "re-marqué, déclaré (caduc)"
            if remark
            else "paramètre renommé, déclaré (D11)"
            if deco
            else "DÉCORATEUR MODIFIÉ NON DÉCLARÉ"
        )
        say(f"  décorateur : {n} — {tag}")
        bad |= not (lifted or remark or deco)
    for n in sorted(set(ba) - set(ha)):
        ok = (f, n) in DECLARED_ASSIGN_REMOVED
        say(f"  affectation retirée {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}"); bad |= not ok
    for n in sorted(set(ha) - set(ba)):
        ok = (f, n) in DECLARED_ASSIGN_ADDED
        say(f"  affectation ajoutée {'déclarée' if ok else 'NON DÉCLARÉE'} : {n}"); bad |= not ok
    for n in sorted(set(ba) & set(ha)):
        if ba[n] != ha[n]:
            if (f, n) in DECLARED_ASSIGN_MODIFIED:
                say(f"  affectation modifiée, déclarée : {n}")
            else:
                say(f"  AFFECTATION MODIFIÉE NON DÉCLARÉE : {n}"); bad = 1
say(f"rc={1 if bad else 0}")
sys.exit(1 if bad else 0)
PY
rc=$?
exit $rc
