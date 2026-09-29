#!/bin/bash
# C3 outillage v2.2 — lint et typage. Usage : bash lint.sh <étiquette>. Sortie : lint_<étiquette>.out.
# 1. ruff check + format --check sur src/ et la liste CI « audit C3 » (.github/workflows/ci.yml), puis ruff check .
# 2. mypy src/ : exactement « Found 65 errors » (convention du projet, sans --ignore-missing-imports).
# 3. mypy strict de chaque scripts/audit/ du chantier (MYPYPATH=src:scripts:scripts/audit --follow-imports=silent
#    --strict), une invocation par fichier ; le nombre d'erreurs par fichier est comparé à la base 8c114fe
#    (lint_base.out ; lot 2 : c3_entry, c3_continuity, c3b_common mesurés à la base par lint_base_lot2.sh,
#    lint_base_lot2.out) : aucun écart neuf.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DIR=results/c3_outillage_v2_2/tests
OUT="$DIR/lint_${LABEL}.out"
CI_LIST=(scripts/audit/_common.py scripts/audit/_db.py scripts/audit/c3*.py scripts/audit/warmup_at.py
  scripts/audit/reconstruct_1w.py tests/test_scripts/test_c3*.py tests/test_scripts/test_warmup_at.py
  tests/test_scripts/test_reconstruct_1w.py tests/test_scripts/test_audit_common.py)
AUDIT=(scripts/audit/c3_common.py scripts/audit/c3_anchor.py scripts/audit/c3_benchmark.py
  scripts/audit/c3_select.py scripts/audit/c3_verdict.py scripts/audit/c3b_evaluate.py
  scripts/audit/c3_entry.py scripts/audit/c3_continuity.py scripts/audit/c3b_common.py)
{
  echo "# lint — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
fail=0
poetry run ruff check src/ "${CI_LIST[@]}" > /dev/null 2>&1; r=$?; echo "ruff_check_ci=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
poetry run ruff format --check src/ "${CI_LIST[@]}" > /dev/null 2>&1; r=$?; echo "ruff_format_ci=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
poetry run ruff check . > /dev/null 2>&1; r=$?; echo "ruff_check_depot=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
src_line=$(poetry run mypy src/ 2>&1 | tail -n 1)
echo "mypy_src=$src_line" >> "$OUT"
case "$src_line" in "Found 65 errors in "*) ;; *) fail=1 ;; esac
for f in "${AUDIT[@]}"; do
  line=$(MYPYPATH=src:scripts:scripts/audit poetry run mypy --follow-imports=silent --strict "$f" 2>&1 | tail -n 1)
  case "$line" in
    "Success: no issues found"*) n=0 ;;
    "Found "*) n=$(echo "$line" | sed -E 's/^Found ([0-9]+) error.*/\1/') ;;
    *) n="?" ;;
  esac
  echo "mypy_strict $f $n" >> "$OUT"
  if [ "$LABEL" != "base" ]; then
    b=$(grep -hE "^mypy_strict $f " "$DIR/lint_base.out" "$DIR/lint_base_lot2.out" | head -n 1 | awk '{print $3}')
    if [ "$n" = "?" ] || [ -z "$b" ] || [ "$n" -gt "$b" ]; then echo "  écart neuf (base $b)" >> "$OUT"; fail=1; fi
  fi
done
echo "rc=$fail" >> "$OUT"
exit $fail
