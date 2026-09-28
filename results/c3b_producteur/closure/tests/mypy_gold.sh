#!/bin/bash
# C3b clôture — `mypy src/` (baseline 65) et gold hashes (fichier inchangé depuis ec7ffb8, 2 tests verts), lancé par
# `bash` depuis le dépôt, au SHA livré. mypy sort en 1 avec des erreurs : c'est le compte qui fait foi, pas son code.
# Sortie : mypy_gold.out (sorties brutes jointes), rc=0 ssi `Found 65 errors`, fichier gold inchangé et `2 passed`.
set -o pipefail
set -u
unset VIRTUAL_ENV

BASE=ec7ffb8
GOLD=tests/test_strategies/test_grid_atr_v4_backward_compat.py
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/mypy_gold.out

{
  echo "# mypy src/ et gold hashes — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD)"
  echo "## poetry run mypy src/"
} > "$OUT"
poetry run mypy src/ >> "$OUT" 2>&1
echo "mypy_exit=$?" >> "$OUT"
if grep -qE '^Found 65 errors in ' "$OUT"; then mypy=0; else mypy=1; fi
echo "mypy_65=$mypy" >> "$OUT"

git diff --quiet "$BASE" HEAD -- "$GOLD"
gold_file=$?
echo "gold_file_unchanged_since_$BASE=$gold_file" >> "$OUT"

echo "## poetry run pytest -q -p no:cacheprovider $GOLD" >> "$OUT"
poetry run pytest -q -p no:cacheprovider "$GOLD" >> "$OUT" 2>&1
gold_rc=$?
echo "gold_pytest_exit=$gold_rc" >> "$OUT"
if [ "$gold_rc" -eq 0 ] && grep -qE '^2 passed' "$OUT"; then gold=0; else gold=1; fi
echo "gold_2_passed=$gold" >> "$OUT"

if [ "$mypy" -eq 0 ] && [ "$gold_file" -eq 0 ] && [ "$gold" -eq 0 ]; then
  echo "rc=0" >> "$OUT"
  exit 0
fi
echo "rc=1" >> "$OUT"
exit 1
