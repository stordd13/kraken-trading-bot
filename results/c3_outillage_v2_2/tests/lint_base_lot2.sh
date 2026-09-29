#!/bin/bash
# C3 outillage v2.2, lot 2 — base mypy strict, à 8c114fe, des trois scripts/audit/ que le lot 2 touche en plus du lot 1
# (c3_entry, c3_continuity, c3b_common). Mesurée dans un worktree détaché à la base : les modules importés
# (c3_common…) y sont ceux de la base, pas ceux du lot 1. Même commande que lint.sh. Sortie : lint_base_lot2.out,
# une ligne « mypy_strict <fichier> <n> » par fichier, lue par lint.sh.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=8c114fe
OUT=results/c3_outillage_v2_2/tests/lint_base_lot2.out
MYPY="$(poetry env info -p)/bin/mypy"
WT="$(mktemp -d)/wt_base"
FILES=(scripts/audit/c3_entry.py scripts/audit/c3_continuity.py scripts/audit/c3b_common.py)
{
  echo "# lint base lot 2 — $(date -u +%FT%TZ)"
  echo "# base $BASE (worktree détaché) ; mypy $("$MYPY" --version)"
} > "$OUT"
git worktree add --detach "$WT" "$BASE" > /dev/null 2>&1 || { echo "worktree impossible" >> "$OUT"; exit 2; }
rc=0
for f in "${FILES[@]}"; do
  line=$(cd "$WT" && MYPYPATH=src:scripts:scripts/audit "$MYPY" --follow-imports=silent --strict "$f" 2>&1 | tail -n 1)
  case "$line" in
    "Success: no issues found"*) n=0 ;;
    "Found "*) n=$(echo "$line" | sed -E 's/^Found ([0-9]+) error.*/\1/') ;;
    *) n="?"; rc=1 ;;
  esac
  echo "mypy_strict $f $n" >> "$OUT"
done
git worktree remove --force "$WT" > /dev/null 2>&1
git worktree prune
echo "rc=$rc" >> "$OUT"
exit $rc
