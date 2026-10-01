#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — le dry-run du pilote est vert dès son écriture ; un vert dès
# l'écriture ne prouve rien (règle agent 1) : trois mutants TEMPORAIRES du pilote, chacun appliqué à l'arbre de
# travail, exercé par tests/pilot_dryrun.sh (sortie dans un temporaire), puis RESTAURÉ et comparé par `cmp` à sa
# sauvegarde. Détail d'exécution, déclaré au STOP 1 (plan § 5 : « dry-run et cas déviés re-prouvés avant de servir »).
#  M1 : le contrôle du triplet retiré de la liste des attendus de l'extraction → le triplet « meilleur » passerait ;
#  M2 : l'arrêt au premier écart désactivé (`go` toujours vrai) → après une forme de refus, la chaîne tournerait ;
#  M3 : la garde CAMPAIGN_UNLOCK inversée → le run conforme serait refusé.
# Sortie : mutants_pilote.out, `mutant=<nom> lignes_changees=<n> dryrun_rc=<n> restaure=<0|1> en_ecart=[…]` ; rc=0 ssi
# chaque mutant change exactement une ligne, fait échouer le dry-run (rc≠0) et est restauré.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/mutants_pilote.out
PILOT=results/c3_campagne_grid/server/run_campagne.sh
SAVE=$(mktemp) || exit 2
TMPO=$(mktemp) || exit 2
cp "$PILOT" "$SAVE" || exit 2
fail=0
: > "$OUT"
echo "# mutants_pilote — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"

mutate() {  # mutate <nom> <expression perl, appliquée ligne à ligne>
  perl -pe "$2" "$SAVE" > "$PILOT"
  local n r c ecarts
  n=$(diff "$SAVE" "$PILOT" | grep -c '^>')
  DRYRUN_OUT="$TMPO" bash results/c3_campagne_grid/tests/pilot_dryrun.sh > /dev/null 2>&1
  r=$?
  cp "$SAVE" "$PILOT"
  cmp -s "$SAVE" "$PILOT"
  c=$?
  ecarts=$( { grep -E '^(marqueur_absent|registre_simule_inattendu) ' "$TMPO";
    grep -E '^sim_[a-z_]+_exit=[0-9]+ attendu=[0-9]+$' "$TMPO" | awk -F'[= ]' '$2 != $4'; } | cut -c1-80 | tr '\n' ';')
  echo "mutant=$1 lignes_changees=$n dryrun_rc=$r restaure=$c en_ecart=[$ecarts]" >> "$OUT"
  if [ "$n" != "1" ] || [ "$r" = "0" ] || [ "$c" != "0" ]; then fail=1; fi
}

mutate M1_triplet_non_controle 's/ issue=inconclusif raison=P_PROVENANCE \\$/ \\/'
mutate M2_arret_desactive 's/^go\(\) \{ \[ -z "\$halted" \]; \}$/go() { true; }/'
mutate M3_garde_unlock_inversee 's/^if \[ ! -f "\$UNLOCK" \]; then$/if [ -f "\$UNLOCK" ]; then/'

cmp -s "$SAVE" "$PILOT"
echo "pilote_final_identique=$?" >> "$OUT"
rm -f "$SAVE" "$TMPO"
echo "rc=$fail" >> "$OUT"
exit $fail
