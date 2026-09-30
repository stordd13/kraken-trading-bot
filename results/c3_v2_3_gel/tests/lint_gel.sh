#!/bin/bash
# C3 gel v2.3 — lint (brief § 4.5) : ruff check et ruff format --check sur la liste de la CI (src/ et liste audit C3,
# .github/workflows/ci.yml) et sur les fichiers de test touchés ; formatter jamais lancé en écriture sur un répertoire
# (seulement --check ; une écriture éventuelle se fait à la main, par fichier nommé) ; mypy src/ = 65 (src/ intouché).
# Lancé par `bash` depuis le dépôt. Usage : bash lint_gel.sh <étiquette>. Sortie : lint_gel_<étiquette>.out.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=662c104ef8cb5a9b5c7fb04452f7af817cb5a87a
OUT="results/c3_v2_3_gel/tests/lint_gel_${LABEL}.out"
LOG=$(mktemp)
{
  echo "# lint_gel — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
rc=0
mark() { echo "$1=$2" >> "$OUT"; [ "$2" -eq 0 ] || rc=1; }
RUFF_C3=(scripts/audit/_common.py scripts/audit/_db.py scripts/audit/c3*.py scripts/audit/warmup_at.py
  scripts/audit/reconstruct_1w.py tests/test_scripts/test_c3*.py tests/test_scripts/test_warmup_at.py
  tests/test_scripts/test_reconstruct_1w.py tests/test_scripts/test_audit_common.py)
TOUCHED=$( { git diff --name-only "$BASE"; git diff --name-only --cached "$BASE"; } | grep -E '\.py$' | LC_ALL=C sort -u)
echo "py_touches=$(printf '%s ' $TOUCHED)" >> "$OUT"
poetry run ruff check src/ > "$LOG" 2>&1; mark ruff_check_src $?
poetry run ruff format --check src/ >> "$LOG" 2>&1; mark ruff_format_src $?
poetry run ruff check "${RUFF_C3[@]}" >> "$LOG" 2>&1; mark ruff_check_audit_c3 $?
poetry run ruff format --check "${RUFF_C3[@]}" >> "$LOG" 2>&1; mark ruff_format_audit_c3 $?
if [ -n "$TOUCHED" ]; then
  # shellcheck disable=SC2086
  poetry run ruff check $TOUCHED >> "$LOG" 2>&1; mark ruff_check_touches $?
  # shellcheck disable=SC2086
  poetry run ruff format --check $TOUCHED >> "$LOG" 2>&1; mark ruff_format_touches $?
fi
poetry run ruff check results/c3_v2_3_gel >> "$LOG" 2>&1; mark ruff_check_results_du_chantier $?
[ "$rc" -eq 0 ] || tail -n 30 "$LOG" >> "$OUT"
poetry run mypy src/ > "$LOG" 2>&1
echo "mypy=$(tail -n 1 "$LOG")" >> "$OUT"
grep -qE '^Found 65 errors in ' "$LOG"; mark mypy_src_65 $?
rm -f "$LOG"
echo "rc=$rc" >> "$OUT"
exit $rc
