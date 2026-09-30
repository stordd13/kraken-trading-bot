#!/bin/bash
# C3 outillage v2.2, lot 1 — les mutants du plan (§ 3), par mutant.sh (substitution littérale unique, témoin rouge
# sous le mutant, fichier restauré par git checkout, diff vide, témoin vert après). Les substitutions sont versionnées
# sous tests/mutants/<id>.old / .new. M3b n'est pas un mutant à tuer : il montre que, sans A1, le mutant M3 survit
# aux fichiers de tests du verdict et du producteur (sous_mutant_exit=0 attendu) — la raison d'être d'A1 (D8).
# Sortie : ../mutants.log (append) ; rc=0 ssi M1-M6 tués et M3b survivant.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
D=results/c3_outillage_v2_2/tests
MU="$D/mutants"
V=tests/test_scripts/test_c3_verdict.py
rc=0
run() { bash "$D/mutant.sh" "$1" "$2" "$MU/$1.old" "$MU/$1.new" "${@:3}"; }
run M1_temoin_R17 scripts/audit/c3_anchor.py \
  tests/test_scripts/test_c3_anchor.py::test_R17_temoin_sur_une_famille_close_l_empreinte_differee_attendue_est_acceptee || rc=1
run M2_table_10_1 scripts/audit/c3_verdict.py "$V::test_R17_la_table_du_10_1_est_celle_du_texte" || rc=1
run M3_A1_run_verdict scripts/audit/c3_verdict.py \
  "$V::test_A1_la_cli_du_verdict_recoupe_ce_que_le_producteur_garantit" || rc=1
run M4_A2_reinscription scripts/audit/c3_verdict.py \
  "$V::test_A2_une_reinscription_discordante_au_registre_est_une_violation" || rc=1
run M5_D3_lambdas scripts/audit/c3_verdict.py \
  "$V::test_R15_des_lambdas_declares_differents_de_ceux_de_l_etape_3_sont_une_violation" \
  "$V::test_R15_returns_bench_different_du_recalcul_sur_l_export_est_une_violation" || rc=1
run M6_D9_sha_avant scripts/audit/c3_anchor.py \
  tests/test_scripts/test_c3_entry.py::test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_v21 \
  "$V::test_chain_sur_le_livrable_reel_v20_s_arrete_a_l_ancrage_code_2_rien_d_ecrit" || rc=1
# M3b : sans A1, qui tue M3 ? Constat (plan, D8, prédisait « personne ») : le seul test R-18 levé par XPASS au commit
# R-15 chaîne (D12a), qui passe par la violation C-3 — il changera de route au lot 2 (admission du refus), A1 reste le
# garde durable. Mutant appliqué, liste des FAILED, restauration vérifiée ; attendu : exactement ce test.
MUT_OLD="$MU/M3_A1_run_verdict.old" MUT_NEW="$MU/M3_A1_run_verdict.new"
git diff --quiet -- scripts/audit/c3_verdict.py || { echo "cible modifiée" >&2; exit 2; }
poetry run python - "$MUT_OLD" "$MUT_NEW" <<'PY'
import pathlib, sys
t = pathlib.Path("scripts/audit/c3_verdict.py"); s = t.read_text(encoding="utf-8")
a, b = (pathlib.Path(x).read_text(encoding="utf-8") for x in sys.argv[1:3])
assert s.count(a) == 1
t.write_text(s.replace(a, b), encoding="utf-8")
PY
LOGM=$(mktemp)
poetry run pytest -q -p no:cacheprovider -rf --tb=no "$V" tests/test_scripts/test_c3b_evaluate.py -k "not test_A1_la_cli" > "$LOGM" 2>&1
git checkout -- scripts/audit/c3_verdict.py
git diff --quiet -- scripts/audit/c3_verdict.py; restored=$?
killers=$(grep -E '^FAILED ' "$LOGM" | sed 's/^FAILED //' | tr '\n' ' ')
{
  echo "## M3b_sans_A1 — $(date -u +%FT%TZ) — HEAD $(git rev-parse --short HEAD)"
  echo "mutant M3 contre $V et test_c3b_evaluate.py, A1 exclu : $(tail -n 1 "$LOGM")"
  echo "tué_par=${killers:-personne} restauré_diff_vide=$restored"
  echo "attendu (constat) : tests/test_scripts/test_c3_verdict.py::test_R18_un_refus_qui_porte_des_series_se_contredit seul"
} >> results/c3_outillage_v2_2/mutants.log
[ "$killers" = "tests/test_scripts/test_c3_verdict.py::test_R18_un_refus_qui_porte_des_series_se_contredit " ] && [ $restored -eq 0 ] || rc=1
rm -f "$LOGM"
echo "## mutants_lot1 rc=$rc" >> results/c3_outillage_v2_2/mutants.log
exit $rc
