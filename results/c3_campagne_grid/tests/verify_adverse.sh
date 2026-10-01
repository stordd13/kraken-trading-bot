#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 (repris de results/c3_racine_registre/tests/verify_adverse.sh) —
# le vérificateur est prouvé avant de servir (règle agent 1) : verify_attendu.py décide « attendu tenu » ; un défaut
# chez lui laisserait passer une déviation, y compris un triplet « meilleur ».
#  - Témoin sain : les extraits de la simulation CONFORME du pilote lui-même (tests/pilot_dryrun.sh, DRYRUN_KEEP) —
#    conformes à tout l'attendu par construction (règle agent 2), et au format exact que le pilote écrit.
#  - Cas déviés : chacun écarte UNE ligne (ou un fichier) du témoin, dans une copie ; le vérificateur doit rendre ≠ 0.
# Aucun cas n'est versionné : tout est fabriqué dans un répertoire temporaire hors du dépôt, supprimé ensuite.
# Sortie : verify_adverse.out, `conf cas=<nom> rc=<n> attendu=<0|non0> items_en_ecart=<n>` ; rc=0 ssi le témoin rend 0
# avec 0 item en écart, et chaque cas dévié rend autre chose que 0 avec EXACTEMENT un item en écart (la déviation mord
# pour sa raison, pas pour une copie ratée).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/verify_adverse.out
VERIFY=results/c3_campagne_grid/server/verify_attendu.py
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# verify_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"

DRYRUN_OUT="$T/dryrun.out" DRYRUN_KEEP="$T/keep" bash results/c3_campagne_grid/tests/pilot_dryrun.sh
r=$?
log "temoin_pilot_dryrun=$r"
[ "$r" = "0" ] || fail=1
# shellcheck disable=SC1091
. "$T/keep/sim.env"

judge() {  # judge <cas> <rc> <attendu : 0 | non0> <sortie du vérificateur>
  local n
  n=$(grep -c '^ÉCART' "$4")
  log "conf cas=$1 rc=$2 attendu=$3 items_en_ecart=$n"
  if [ "$3" = "0" ] && { [ "$2" != "0" ] || [ "$n" != "0" ]; }; then fail=1; fi
  if [ "$3" = "non0" ] && { [ "$2" = "0" ] || [ "$n" != "1" ]; }; then fail=1; fi
}
# conf <cas> <attendu> <sha passé> <commande de déviation sur le répertoire $D, ou « - »>
conf() {
  local D=$T/conf/$1
  mkdir -p "$D"
  cp "$T/keep/status.txt" "$T/keep/alembic_before.txt" "$T/keep/alembic_after.txt" "$T/keep/pilot_exit.txt" "$D/"
  if [ "$4" != "-" ]; then (cd "$D" && eval "$4"); fi
  python3 "$VERIFY" --sha "$3" --dir "$D" --pilot-sha "$SIM_PILOT_SHA" > "$D/verify.txt" 2>&1
  judge "$1" "$?" "$2" "$D/verify.txt"
}
sedi() {  # sedi <expression> <fichier> : sed en place, portable
  sed -e "$1" "$2" > "$2.tmp" && mv "$2.tmp" "$2"
}
S=$SIM_SHA
conf temoin 0 "$S" -
# item 1 — gardes
conf sha_passe_autre non0 0000000000000000000000000000000000000000 -
conf guard_refused non0 "$S" "sedi 's/^guard=0 /guard=REFUSED /' status.txt"
conf unlock_absent_a_la_garde non0 "$S" "sedi 's/campaign_unlock=present\$/campaign_unlock=absent/' status.txt"
conf pilot_sha_autre non0 "$S" "sedi 's/^pilot_sha256=.*/pilot_sha256=deadbeef/' status.txt"
# item 2 — base
conf alembic_after_autre non0 "$S" "echo 'c3bd1e7a0002 (head)' >> alembic_after.txt"
# item 3 — service
conf service_nrestarts non0 "$S" "sedi 's/^\(service_after=.*\)NRestarts=0/\1NRestarts=1/' status.txt"
conf unlock_absent_apres non0 "$S" "sedi 's/^campaign_unlock_after=present\$/campaign_unlock_after=absent/' status.txt"
# item 4 — préfixe
conf workers_4 non0 "$S" "sedi 's/^workers=3\$/workers=4/' status.txt"
conf prefix_code_3 non0 "$S" "sedi 's/^prefix=0 /prefix=3 /' status.txt"
# item 5 — chaîne 1-4 autonome, première inscription
conf pre_select_code_2 non0 "$S" "sedi 's/^pre_select=0\$/pre_select=2/' status.txt"
conf new_entry_pre_faux non0 "$S" "sedi 's/^registry_new_entry_pre=true\$/registry_new_entry_pre=false/' status.txt"
# item 6 — évaluation
conf eval_forme_de_refus non0 "$S" "sedi 's/^eval=0 event=evaluated /eval=0 event=refusal_form_written /' status.txt"
# item 7 — chaîne complète
conf chain_code_1 non0 "$S" "sedi 's/^chain=0 /chain=1 /' status.txt"
conf chain_steps_continuity_1 non0 "$S" "sedi 's/^chain_steps=\(.*\)continuity:0\$/chain_steps=\1continuity:1/' status.txt"
conf chain_verified_faux non0 "$S" "sedi 's/^chain_verified=true\$/chain_verified=false/' status.txt"
conf violations_non_vides non0 "$S" "sedi 's/^violations_empty=true\$/violations_empty=false/' status.txt"
conf rejeu_non_vide non0 "$S" "sedi 's/^replay_violations_empty=true\$/replay_violations_empty=false/' status.txt"
conf new_entry_chaine_vrai non0 "$S" \
  "sedi 's/^registry_new_entry_chain=false\$/registry_new_entry_chain=true/' status.txt"
conf issue_non_inscrite non0 "$S" "sedi 's/^issue_inscrite=true\$/issue_inscrite=false/' status.txt"
conf extract_1 non0 "$S" "sedi 's/^extract=0\$/extract=1/' status.txt"
conf chain_stopped_present non0 "$S" "echo 'chain_stopped=continuity:1' >> status.txt"
# item 8 — issue : tout autre triplet est un écart, « meilleur » compris
conf triplet_meilleur non0 "$S" "sedi 's/^issue=inconclusif\$/issue=validé/; s/^raison=P_PROVENANCE\$/raison=-/' status.txt"
conf raison_comptee non0 "$S" "sedi 's/^raison=P_PROVENANCE\$/raison=F_CANNOT_SEPARATE/' status.txt"
conf raison_conditionnelle non0 "$S" "sedi 's/^raison=P_PROVENANCE\$/raison=A_NO_ADMISSIBLE_CANDIDATE/' status.txt"
conf issue_hors_liste non0 "$S" "sedi 's/^issue=inconclusif\$/issue=hors_liste/' status.txt"
conf selection_non_descriptive non0 "$S" \
  "sedi 's/^selection_descriptive=true\$/selection_descriptive=false/' status.txt"
conf cle_raison_absente non0 "$S" "sedi '/^raison=/d' status.txt"
# item 9 — interpréteur
conf interpreter_1 non0 "$S" "sedi 's/^interpreter=0\$/interpreter=1/' status.txt"
# item 10 — aucun arrêt
conf halted_at_eval non0 "$S" "sedi 's/^halted_at=-\$/halted_at=eval/' status.txt"
conf etape_not_run non0 "$S" "echo 'etape_simulee=NOT_RUN' >> status.txt"
# item 11 — code du pilote
conf pilot_exit_1 non0 "$S" "echo 1 > pilot_exit.txt"

rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
