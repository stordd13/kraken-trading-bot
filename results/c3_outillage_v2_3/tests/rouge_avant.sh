#!/bin/bash
# C3 outillage v2.3, lot 1 — règle agent 1 : « tout test de contrat naît adverse », constaté ROUGE contre un état qui
# n'implémente pas la règle. Les tests neufs du lot (plan D10 : N1-N4) sont lancés dans un worktree détaché à la base
# b50f2d1 (code v2.2 + squelette du gel), avec les fichiers de test COURANTS copiés par-dessus : chacun doit échouer, et
# la ligne où il échoue est consignée (l'attendu de la règle, jamais un préalable de fixture).
# Usage : bash rouge_avant.sh <étiquette> <nodeid…> (nodeids relatifs à tests/test_scripts/). Sortie :
# rouge_avant_<étiquette>.out ; rc=0 ssi chaque test échoue à la base.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
shift
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9
DIR=results/c3_outillage_v2_3/tests
OUT="$DIR/rouge_avant_${LABEL}.out"
PY="$(poetry env info -p)/bin/python"
WT="$(mktemp -d)/wt_base"
RAW=$(mktemp)
{
  echo "# rouge_avant — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; code de la base $BASE"
} > "$OUT"
git worktree add --detach "$WT" "$BASE" > /dev/null 2>&1 || { echo "worktree impossible" >> "$OUT"; exit 2; }
for f in test_c3_common.py test_c3_anchor.py test_c3_verdict.py; do
  cp "tests/test_scripts/$f" "$WT/tests/test_scripts/$f"
done
WT_REAL=$(cd "$WT" && pwd -P)
echo "tests copiés : test_c3_common.py test_c3_anchor.py test_c3_verdict.py (arbre courant)" >> "$OUT"
rc=0
for node in "$@"; do
  (cd "$WT" && "$PY" -m pytest -q -p no:cacheprovider --tb=line "tests/test_scripts/$node" > "$RAW" 2>&1)
  e=$?
  where=$(grep -E '^(/|tests/|E )' "$RAW" | grep -vE '^tests/[^ ]+::' | head -n 2 | sed -e "s|$WT_REAL/||g" -e "s|$WT/||g" | tr '\n' ' ' \
    | sed -E 's/[0-9a-f]{64}/<64hex>/g' | cut -c1-300)
  echo "test=${node} pytest_exit=${e} (attendu 1) échec : ${where}" >> "$OUT"
  [ "$e" -eq 1 ] || rc=1
done
git worktree remove --force "$WT" > /dev/null 2>&1
git worktree prune
rm -f "$RAW"
echo "rc=$rc" >> "$OUT"
exit $rc
