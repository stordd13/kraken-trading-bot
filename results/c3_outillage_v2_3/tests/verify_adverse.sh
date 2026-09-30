#!/bin/bash
# C3 outillage v2.3, lot 2 (repris du lot 3 v2.2) — brief § 4 et condition du GO v2.2 (29/09) : les vérificateurs sont prouvés avant de servir (règle agent 1).
# verify_attendu.py (conformité) et verify_gate.sh (porte § L.5) décident « attendu tenu » ; un défaut chez eux
# laisserait passer une déviation.
#  - Témoins sains : les extraits des simulations CONFORMES du pilote lui-même (tests/pilot_dryrun.sh, DRYRUN_KEEP) —
#    conformes à tout l'attendu par construction (règle agent 2), et au format exact que le pilote écrit.
#  - Cas déviés : chacun écarte UNE ligne (ou un fichier) du témoin, dans une copie ; le vérificateur doit rendre ≠ 0.
# Aucun cas n'est versionné : tout est fabriqué dans un répertoire temporaire hors du dépôt, supprimé ensuite.
# Sortie : verify_adverse.out, `<vérificateur> cas=<nom> rc=<n> attendu=<0|non0> items_en_ecart=<n>` ; rc=0 ssi chaque
# témoin rend 0 avec 0 item en écart, et chaque cas dévié rend autre chose que 0 avec EXACTEMENT un item en écart (la
# déviation mord pour sa raison, pas pour une copie ratée).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_3/tests/verify_adverse.out
VERIFY_CONF=results/c3_outillage_v2_3/conformite/server/verify_attendu.py
VERIFY_GATE=results/c3_outillage_v2_3/tests/verify_gate.sh
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# verify_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"

DRYRUN_OUT="$T/dryrun.out" DRYRUN_KEEP="$T/keep" bash results/c3_outillage_v2_3/tests/pilot_dryrun.sh
r=$?
log "temoins_pilot_dryrun=$r"
[ "$r" = "0" ] || fail=1
# shellcheck disable=SC1091
. "$T/keep/sim.env"
CONF_SHA=$SIM_SHA
CONF_PILOT=$SIM_PILOT_SHA
. "$T/keep/gate/sim.env"
GATE_SHA=$SIM_SHA
GATE_PILOT=$SIM_PILOT_SHA

judge() {  # judge <vérificateur> <cas> <rc> <attendu : 0 | non0> <sortie du vérificateur>
  local n
  n=$(grep -c '^ÉCART' "$5")
  log "$1 cas=$2 rc=$3 attendu=$4 items_en_ecart=$n"
  if [ "$4" = "0" ] && { [ "$3" != "0" ] || [ "$n" != "0" ]; }; then fail=1; fi
  if [ "$4" = "non0" ] && { [ "$3" = "0" ] || [ "$n" != "1" ]; }; then fail=1; fi
}

# --- conformité ------------------------------------------------------------------------------------------------------
# conf <cas> <attendu> <sha passé> <commande de déviation sur le répertoire $D, ou « - »>
conf() {
  local D=$T/conf/$1
  mkdir -p "$D"
  cp "$T/keep/status.txt" "$T/keep/alembic_before.txt" "$T/keep/alembic_after.txt" "$T/keep/pilot_exit.txt" "$D/"
  if [ "$4" != "-" ]; then (cd "$D" && eval "$4"); fi
  python3 "$VERIFY_CONF" --sha "$3" --dir "$D" --pilot-sha "$CONF_PILOT" > "$D/verify.txt" 2>&1
  judge conf "$1" "$?" "$2" "$D/verify.txt"
}
sedi() {  # sedi <expression> <fichier> : sed en place, portable
  sed -e "$1" "$2" > "$2.tmp" && mv "$2.tmp" "$2"
}
conf temoin 0 "$CONF_SHA" -
conf sha_passe_autre non0 0000000000000000000000000000000000000000 -
conf guard_refused non0 "$CONF_SHA" "sedi 's/^guard=0 /guard=REFUSED /' status.txt"
conf pilot_sha_autre non0 "$CONF_SHA" "sedi 's/^pilot_sha256=.*/pilot_sha256=deadbeef/' status.txt"
conf alembic_after_autre non0 "$CONF_SHA" "echo 'c3bd1e7a0002 (head)' >> alembic_after.txt"
conf service_nrestarts non0 "$CONF_SHA" "sedi 's/^\(service_after=.*\)NRestarts=0/\1NRestarts=1/' status.txt"
conf workers_2_a_4 non0 "$CONF_SHA" "sedi 's/^workers_2=1$/workers_2=4/' status.txt"
conf prefix_2_code_3 non0 "$CONF_SHA" "sedi 's/^prefix_2=0 /prefix_2=3 /' status.txt"
conf pre_select_3_code_2 non0 "$CONF_SHA" "sedi 's/^pre_select_3=0$/pre_select_3=2/' status.txt"
conf eval_1_forme_de_refus non0 "$CONF_SHA" \
  "sedi 's/^eval_1=0 event=evaluated /eval_1=0 event=refusal_form_written /' status.txt"
conf chain_steps_2_continuity_1 non0 "$CONF_SHA" \
  "sedi 's/^chain_steps_2=\(.*\)continuity:0$/chain_steps_2=\1continuity:1/' status.txt"
conf chain_verified_3_faux non0 "$CONF_SHA" "sedi 's/^chain_verified_3=true$/chain_verified_3=false/' status.txt"
conf violations_1_non_vides non0 "$CONF_SHA" \
  "sedi 's/^violations_empty_1=true$/violations_empty_1=false/' status.txt"
conf rejeu_2_non_vide non0 "$CONF_SHA" \
  "sedi 's/^replay_violations_empty_2=true$/replay_violations_empty_2=false/' status.txt"
conf interpreter_1 non0 "$CONF_SHA" "sedi 's/^interpreter_1=0$/interpreter_1=1/' status.txt"
conf eq3_run2_seul non0 "$CONF_SHA" \
  "sedi 's|^eq3 eval/evaluation.json=0$|eq3 eval/evaluation.json=1 r12=1 r13=0|' status.txt"
conf eq3_ligne_absente non0 "$CONF_SHA" "sedi '/^eq3 chain\/verdict.json=/d' status.txt"
conf compared_22 non0 "$CONF_SHA" \
  "sedi 's/^bit_equal_3of3=0 compared=23 /bit_equal_3of3=0 compared=22 /' status.txt"
conf listing_1 non0 "$CONF_SHA" "sedi 's/^listing_expected_3of3=0$/listing_expected_3of3=1/' status.txt"
conf cle_absente_chain_verified_2 non0 "$CONF_SHA" "sedi '/^chain_verified_2=/d' status.txt"
conf chain_stopped_present non0 "$CONF_SHA" "echo 'chain_stopped_1=continuity:1' >> status.txt"
conf campaign_unlock_apres non0 "$CONF_SHA" \
  "sedi 's/^campaign_unlock_after=absent$/campaign_unlock_after=present/' status.txt"
conf pilot_exit_1 non0 "$CONF_SHA" "echo 1 > pilot_exit.txt"

# --- porte ------------------------------------------------------------------------------------------------------------
# gate <cas> <attendu> <sha passé> <commande de déviation sur $D, ou « - »>
gate() {
  local D=$T/gate/$1
  mkdir -p "$D"
  cp "$T/keep/gate/"{status.txt,alembic_before.txt,alembic_after.txt,pilot_exit.txt,pytest_summary.txt} "$D/"
  if [ "$4" != "-" ]; then (cd "$D" && eval "$4"); fi
  bash "$VERIFY_GATE" "$3" "$D" "$D/verify.txt" "$GATE_PILOT" > /dev/null 2>&1
  judge gate "$1" "$?" "$2" "$D/verify.txt"
}
gate temoin 0 "$GATE_SHA" -
gate sha_passe_autre non0 0000000000000000000000000000000000000000 -
gate agregat_23_sur_24 non0 "$GATE_SHA" \
  "sedi 's/^junit_total=.*/junit_total=tests:23,failures:0,errors:0,skipped:0,missing:1/' status.txt"
gate combo7_skippe_rc0 non0 "$GATE_SHA" "sedi 's|^combo7=0 junit=1/0/0/0 |combo7=0 junit=1/0/0/1 |' status.txt"
gate combo3_rc1 non0 "$GATE_SHA" "sedi 's|^combo3=0 |combo3=1 |' status.txt"
gate full_failed non0 "$GATE_SHA" "sedi 's/^full=0$/full=FAILED n=1 combos=combo3/' status.txt"
gate extract_46 non0 "$GATE_SHA" "sedi 's/^extract=0$/extract=1 lines=46/' status.txt"
gate resume_passed_manquant non0 "$GATE_SHA" \
  "awk '!(/^  1 passed in / && !seen++)' pytest_summary.txt > s.tmp && mv s.tmp pytest_summary.txt"
gate tree_after_1 non0 "$GATE_SHA" "sedi 's/^tree_after=0$/tree_after=1/' status.txt"
gate alembic_after_autre non0 "$GATE_SHA" "echo 'c3bd1e7a0002 (head)' >> alembic_after.txt"
gate collector_nrestarts non0 "$GATE_SHA" "sedi 's/^\(collector_after=.*\)NRestarts=0/\1NRestarts=1/' status.txt"
gate service_head_autre non0 "$GATE_SHA" "sedi 's/^service_after=head=[0-9a-f]*/service_after=head=deadbeef/' status.txt"
gate interpreter_1 non0 "$GATE_SHA" "sedi 's/^interpreter_check=0$/interpreter_check=1/' status.txt"
gate cle_absente_full non0 "$GATE_SHA" "sedi '/^full=/d' status.txt"
gate pilot_sha_autre non0 "$GATE_SHA" "sedi 's/^pilot_sha256=.*/pilot_sha256=deadbeef/' status.txt"
gate pilot_exit_1 non0 "$GATE_SHA" "echo 1 > pilot_exit.txt"

rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
