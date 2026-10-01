#!/bin/bash
# C3 racine du registre, lot 1 — preuve de reprise (plan § 6) : chaque script de preuve du lot est repris de l'outillage
# v2.3 (results/c3_outillage_v2_3/tests/) ; ce script consigne, fichier par fichier, TOUTES les lignes qui diffèrent de
# la source (`diff`, lignes `<` source, `>` reprise) et leur nombre. Relecture humaine : pour les reprises par
# substitution, les lignes changées sont les en-têtes, la base (b50f2d1 → 313eb00), le répertoire
# (results/c3_outillage_v2_3/ → results/c3_racine_registre/) et les listes du plan (§ 3, D4, D8, D10) ; `interdits.sh`,
# `interdits_adverse.sh` et `non_divulgation.sh` portent en plus les contrôles neufs du plan (D3, D8, D10, runbook § 4),
# dits dans leur en-tête ; `mutants.sh` porte les mutants du plan § 4 (liste neuve). Scripts neufs, sans source :
# `inventaire_filet.sh`, `inventaire_adverse.sh`, `reprise_lot1.sh`, `runbook.sh`.
# Usage : bash reprise_lot1.sh <étiquette>. Sortie : reprise_lot1_<étiquette>.out ; rc=0 ssi chaque source et chaque
# reprise existent (le jugement est la relecture).
set -o pipefail
set -u
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
S=results/c3_outillage_v2_3/tests
D=results/c3_racine_registre/tests
OUT=$D/reprise_lot1_${LABEL}.out
PAIRS=(suite.sh lint.sh tunnel.sh base_db.sh xfail_fin.sh ci_status.sh mutant.sh comptes.sh rouge_avant.sh diff_tests.sh
  non_divulgation.sh interdits.sh interdits_adverse.sh "declares_lot1.txt=declares.txt")
[ -f "$D/mutants.sh" ] && PAIRS+=("mutants_lot1.sh=mutants.sh")
fail=0
: > "$OUT"
echo "# reprise_lot1 — $LABEL — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
for p in "${PAIRS[@]}"; do
  src=${p%%=*}
  dst=${p#*=}
  if [ ! -f "$S/$src" ] || [ ! -f "$D/$dst" ]; then echo "fichier_absent $src -> $dst" >> "$OUT"; fail=1; continue; fi
  n_src=$(diff "$S/$src" "$D/$dst" | grep -c '^<')
  n_dst=$(diff "$S/$src" "$D/$dst" | grep -c '^>')
  echo "## $S/$src -> $D/$dst : lignes source changées=$n_src, lignes reprise=$n_dst" >> "$OUT"
  diff "$S/$src" "$D/$dst" | grep -E '^[<>]' | cut -c1-220 >> "$OUT"
done
echo "rc=$fail" >> "$OUT"
exit $fail
