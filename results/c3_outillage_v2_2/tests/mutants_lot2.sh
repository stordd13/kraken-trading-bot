#!/bin/bash
# C3 outillage v2.2, lot 2 — les mutants du plan (§ 4) et le rejeu des mutants du lot 1 au tip du lot 2 (obligation e),
# par mutant.sh (substitution littérale unique, témoin rouge sous le mutant, fichier restauré par git checkout, diff
# vide, témoin vert après). Substitutions versionnées sous tests/mutants/<id>.old / .new.
# Deux constats en plus, qui ne sont pas des mutants à tuer :
#  - M3 rejoué (run_verdict ne transmet pas les entrées v2.2) : la liste de ses tueurs dans les fichiers du verdict et
#    du producteur ; exigé : A1 en est (obligation e) — le test « refus avec séries » n'en est plus (route R-18) ;
#  - L2M8 (implication retirée) : le test xfail levé homologue reste vert, tué d'abord par le recalcul R-15 — c'est
#    pourquoi T11 et T12 existent.
# Sortie : ../mutants.log (append) ; rc=0 ssi tous tués et les deux constats conformes.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
D=results/c3_outillage_v2_2/tests
MU="$D/mutants"
LOGF=results/c3_outillage_v2_2/mutants.log
T=tests/test_scripts
V=$T/test_c3_verdict.py
E=$T/test_c3b_evaluate.py
rc=0
run() { bash "$D/mutant.sh" "$1" "$2" "$MU/$1.old" "$MU/$1.new" "${@:3}" || rc=1; }
echo "## mutants_lot2 — début $(date -u +%FT%TZ) — HEAD $(git rev-parse --short HEAD)" >> "$LOGF"

# --- Lot 1, rejoués au tip du lot 2 (ancres inchangées)
run M1_temoin_R17 scripts/audit/c3_anchor.py \
  $T/test_c3_anchor.py::test_R17_temoin_sur_une_famille_close_l_empreinte_differee_attendue_est_acceptee
run M2_table_10_1 scripts/audit/c3_verdict.py "$V::test_R17_la_table_du_10_1_est_celle_du_texte"
run M3_A1_run_verdict scripts/audit/c3_verdict.py "$V::test_A1_la_cli_du_verdict_recoupe_ce_que_le_producteur_garantit"
run M4_A2_reinscription scripts/audit/c3_verdict.py \
  "$V::test_A2_une_reinscription_discordante_au_registre_est_une_violation"
run M5_D3_lambdas scripts/audit/c3_verdict.py \
  "$V::test_R15_des_lambdas_declares_differents_de_ceux_de_l_etape_3_sont_une_violation" \
  "$V::test_R15_returns_bench_different_du_recalcul_sur_l_export_est_une_violation"
run M6_D9_sha_avant scripts/audit/c3_anchor.py \
  $T/test_c3_entry.py::test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_v21 \
  "$V::test_chain_sur_le_livrable_reel_v20_s_arrete_a_l_ancrage_code_2_rien_d_ecrit"

# --- Lot 2
run L2M1_garde_non_bornee scripts/audit/c3_common.py \
  $T/test_c3_entry.py::test_un_suffixe_de_monnaie_hors_des_positions_nommees_n_est_ni_lu_ni_refuse
run L2M2_garde_des_lots scripts/audit/c3_entry.py \
  $T/test_c3_entry.py::test_R16_un_lot_qui_porte_gross_usdc_refuse_l_entree_a_la_forme
run L2M3_garde_identites scripts/audit/c3_common.py \
  $T/test_c3_continuity.py::test_R16_un_bloc_de_liquidation_d_evaluation_qui_porte_gross_usdc_est_une_erreur_de_forme
run L2M3b_garde_export scripts/audit/c3b_common.py \
  $T/test_c3b_common.py::test_R16_un_montant_gross_hors_table_de_renommage_est_un_controle_en_echec
run L2M4_C1_ordre scripts/audit/c3_verdict.py \
  "$V::test_R18_l_identite_du_refus_est_recoupee_avant_toute_lecture_du_bloc_refused"
run L2M5_rejeu_du_refus scripts/audit/c3_verdict.py "$V::test_R18_un_refus_que_l_export_dement_est_une_violation"
run L2M6_motif_non_comparable scripts/audit/c3_verdict.py \
  "$V::test_R18_un_comparateur_non_comparable_porte_le_motif_comparator_not_comparable"
run L2M7_ssi_un_sens scripts/audit/c3_common.py \
  "$V::test_R19_un_premier_remplissage_avec_zero_execution_est_une_violation"
run L2M8_implication_retiree scripts/audit/c3_common.py \
  "$V::test_R19_zero_execution_et_equity_constante_differente_de_C_est_une_violation" \
  "$V::test_R19_zero_execution_equity_non_constante_rendements_coherents_est_une_violation"
run L2M8b_constance_seule scripts/audit/c3_common.py \
  "$V::test_R19_zero_execution_et_equity_constante_differente_de_C_est_une_violation"
run L2M9_executions_liquidation scripts/audit/c3b_evaluate.py "$E::test_R19_executions_is_the_number_of_fills"
run L2M10_exemption_c5 scripts/audit/c3_verdict.py \
  "$V::test_c1_ou_c5_non_verifiable_sur_une_evaluation_reelle_est_une_violation[c5]"
run L2M11_dates_un_sens scripts/audit/c3_common.py \
  $T/test_c3_entry.py::test_R20_des_dates_presentes_sur_une_serie_sans_unite_couverte_sont_une_violation
run L2M12_garde_comparateur scripts/audit/c3b_evaluate.py \
  "$E::test_hors_R_an_exception_in_build_pair_is_a_control_error_3"
run L2M13_comparateur_exige scripts/audit/c3_continuity.py \
  $T/test_c3_continuity.py::test_R18_une_evaluation_executee_sans_comparateur_d_evaluation_est_refusee
run L2M14_motifs_du_texte scripts/audit/c3_common.py "$V::test_R18_les_motifs_et_la_raison_du_refus_sont_ceux_du_texte"
run L2M15_comparateur_requis_a_la_chaine scripts/audit/c3_verdict.py \
  "$V::test_R18_la_chaine_sur_une_forme_de_refus_n_exige_pas_le_comparateur_d_evaluation"
run L2M16_refus_en_code_2 scripts/audit/c3b_evaluate.py \
  "$E::test_R18_the_refusal_form_exits_0_and_writes_only_its_artefacts"
# Ajouté après le premier passage (défaut du plan : T14 n'avait pas de mutant) — l'entrée exige de nouveau les dates.
run L2M17_dates_exigees_a_l_entree scripts/audit/c3_entry.py \
  $T/test_c3_select.py::test_R20_une_serie_sans_unite_couverte_retire_la_paire_par_D1

# --- Constat 1 : M3 rejoué, qui le tue ?
constat() {  # $1 étiquette, $2 fichier cible, $3 .old, $4 .new, $5 sortie des FAILED ; tests en suite
  local label=$1 target=$2 old=$3 new=$4 out=$5
  shift 5
  git diff --quiet -- "$target" || { echo "cible modifiée : $target" >&2; exit 2; }
  poetry run python - "$target" "$old" "$new" <<'PY'
import pathlib, sys
t = pathlib.Path(sys.argv[1]); s = t.read_text(encoding="utf-8")
a, b = (pathlib.Path(x).read_text(encoding="utf-8") for x in sys.argv[2:4])
assert s.count(a) == 1
t.write_text(s.replace(a, b), encoding="utf-8")
PY
  poetry run pytest -q -p no:cacheprovider -rf --tb=no "$@" > "$out" 2>&1
  git checkout -- "$target"
  git diff --quiet -- "$target"
}
LOGM=$(mktemp)
constat M3_rejeu scripts/audit/c3_verdict.py "$MU/M3_A1_run_verdict.old" "$MU/M3_A1_run_verdict.new" "$LOGM" "$V" "$E"
restored=$?
killers=$(grep -E '^FAILED ' "$LOGM" | sed -E 's/^FAILED ([^ ]+).*/\1/' | sort)
a1=$(printf '%s\n' "$killers" | grep -c "test_A1_la_cli_du_verdict_recoupe_ce_que_le_producteur_garantit")
series=$(printf '%s\n' "$killers" | grep -c "test_R18_un_refus_qui_porte_des_series_se_contredit")
{
  echo "## M3_rejeu_tueurs — $(date -u +%FT%TZ) — HEAD $(git rev-parse --short HEAD)"
  echo "mutant M3 contre $V et $E : $(tail -n 1 "$LOGM")"
  printf '%s\n' "$killers" | sed 's/^/tué_par=/'
  echo "A1_parmi_les_tueurs=$a1 (attendu 1) refus_avec_series_parmi_les_tueurs=$series (attendu 0 : route R-18) restauré_diff_vide=$restored"
} >> "$LOGF"
{ [ "$a1" -eq 1 ] && [ "$series" -eq 0 ] && [ "$restored" -eq 0 ]; } || rc=1

# --- Constat 2 : L2M8, le test xfail levé homologue reste vert (R-15 le tue d'abord)
constat L2M8_constat scripts/audit/c3_common.py "$MU/L2M8_implication_retiree.old" "$MU/L2M8_implication_retiree.new" \
  "$LOGM" "$V::test_R19_zero_execution_avec_une_equity_non_constante_est_une_violation"
restored=$?
survived=$(grep -cE '^1 passed' "$LOGM")
{
  echo "## L2M8_constat_homologue — $(date -u +%FT%TZ) — HEAD $(git rev-parse --short HEAD)"
  echo "mutant L2M8 contre test_R19_zero_execution_avec_une_equity_non_constante_est_une_violation : $(tail -n 1 "$LOGM")"
  echo "homologue_vert_sous_mutant=$survived (attendu 1 : R-15 le voit d'abord) restauré_diff_vide=$restored"
} >> "$LOGF"
{ [ "$survived" -eq 1 ] && [ "$restored" -eq 0 ]; } || rc=1
rm -f "$LOGM"
echo "## mutants_lot2 rc=$rc" >> "$LOGF"
exit $rc
