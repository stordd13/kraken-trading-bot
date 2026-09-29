#!/bin/bash
# C3 outillage v2.2 — liste des interdits du brief : aucun changement contre 8c114fe sur les chemins gelés.
# Usage : bash interdits.sh <étiquette>. Sortie : interdits_<étiquette>.out ; rc=0 ssi tous les diffs sont vides
# (arbre de travail et index compris).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=8c114fe
OUT=results/c3_outillage_v2_2/tests/interdits_${LABEL}.out
PATHS=(src scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py
  scripts/audit/rejeu_common.py docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md
  results/c3_v2_2 results/c3b_producteur)
{
  echo "# interdits — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
rc=0
for p in "${PATHS[@]}"; do
  git diff --quiet "$BASE" -- "$p"; a=$?
  git diff --quiet --cached -- "$p"; b=$?
  echo "diff_vide $p commit=$a index=$b" >> "$OUT"
  { [ $a -ne 0 ] || [ $b -ne 0 ]; } && rc=1
done
echo "rc=$rc" >> "$OUT"
exit $rc
