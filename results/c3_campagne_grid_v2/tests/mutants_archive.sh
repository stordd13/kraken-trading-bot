#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique — archive_dryrun.sh est vert dès son écriture ; un vert
# dès l'écriture ne prouve rien (règle agent 1) : quatre mutants TEMPORAIRES — trois des enveloppes d'archive (le corps
# distant n'est jamais muté) et un de la ligne A1' du preflight —, chacun appliqué à l'arbre de travail, exercé par
# tests/archive_dryrun.sh (sortie dans un temporaire ; faux ssh, aucun appel réel), puis RESTAURÉ et comparé par `cmp` à
# sa sauvegarde. Neuf, sans source au chantier v1 (modèle : tests/mutants_pilote.sh). Détail d'exécution, déclaré au
# STOP 1.
#  M1 : la précondition 11/11 d'archive.sh retirée → l'archive partirait sans verify ;
#  M2 : le contrôle de la sonde d'archive_prealable.sh neutralisé → le corps partirait sur une sonde en écart ;
#  M3 : la date figée d'archive_prealable.sh changée → l'archive v1 ne porterait plus 20261001 ;
#  M4 : le seuil de la ligne A1' du preflight abaissé à 20261001 → un lancement le 01/10 passerait.
# Sortie : mutants_archive.out, `mutant=<nom> lignes_changees=<n> dryrun_rc=<n> restaure=<0|1> en_ecart=[…]` ; rc=0 ssi
# chaque mutant change exactement une ligne, fait échouer archive_dryrun (rc≠0) et est restauré.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/tests/mutants_archive.out
ARCH=results/c3_campagne_grid_v2/tests/archive.sh
PREA=results/c3_campagne_grid_v2/tests/archive_prealable.sh
PREF=results/c3_campagne_grid_v2/tests/preflight.sh
SA=$(mktemp) || exit 2
SP=$(mktemp) || exit 2
SF=$(mktemp) || exit 2
TMPO=$(mktemp) || exit 2
cp "$ARCH" "$SA" || exit 2
cp "$PREA" "$SP" || exit 2
cp "$PREF" "$SF" || exit 2
fail=0
: > "$OUT"
echo "# mutants_archive — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"

mutate() {  # mutate <nom> <script> <sauvegarde> <expression perl, appliquée ligne à ligne>
  perl -pe "$4" "$3" > "$2"
  local n r c ecarts
  n=$(diff "$3" "$2" | grep -c '^>')
  DRYRUN_OUT="$TMPO" bash results/c3_campagne_grid_v2/tests/archive_dryrun.sh > /dev/null 2>&1
  r=$?
  cp "$3" "$2"
  cmp -s "$3" "$2"
  c=$?
  ecarts=$(grep -E '^  ECART ' "$TMPO" | cut -c1-90 | tr '\n' ';')
  echo "mutant=$1 lignes_changees=$n dryrun_rc=$r restaure=$c en_ecart=[$ecarts]" >> "$OUT"
  if [ "$n" != "1" ] || [ "$r" = "0" ] || [ "$c" != "0" ]; then fail=1; fi
}

mutate M1_precondition_11_sur_11_retiree "$ARCH" "$SA" \
  's/^if ! \{ \[ -f "\$V" \] && grep -qx "11\/11 items vérifiables tenus" "\$V" && grep -qx "rc=0" "\$V"; \}; then$/if false; then/'
mutate M2_controle_de_sonde_neutralise "$PREA" "$SP" \
  's/^if ! \{ grep -qx "sonde_meme_peripherique=0"/if false && { grep -qx "sonde_meme_peripherique=0"/'
mutate M3_date_figee_changee "$PREA" "$SP" 's/^DATE=20261001$/DATE=20261002/'
mutate M4_seuil_a1_abaisse "$PREF" "$SF" 's/^if \[ "\$DAY" -ge 20261002 \]; then/if [ "\$DAY" -ge 20261001 ]; then/'

cmp -s "$SA" "$ARCH"; a=$?
cmp -s "$SP" "$PREA"; p=$?
cmp -s "$SF" "$PREF"; f=$?
echo "scripts_finals_identiques=archive:$a,archive_prealable:$p,preflight:$f" >> "$OUT"
{ [ "$a" = "0" ] && [ "$p" = "0" ] && [ "$f" = "0" ]; } || fail=1
rm -f "$SA" "$SP" "$SF" "$TMPO"
echo "rc=$fail" >> "$OUT"
exit $fail
