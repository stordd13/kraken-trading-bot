#!/bin/bash
# C3 v2.2 — contrôle d'un commit d'application (étapes C, E, F du plan) : suites C3 et C3b (hermétiques, aucune
# base, aucun tunnel), ruff sur la liste C3 de la CI, diff vide sur le code depuis 8689636, et la liste des xfail
# avec leur raison. Lancé par `bash` depuis le dépôt, fichiers du commit INDEXÉS. Pas de pipe sur pytest : sa
# sortie va dans un fichier, son code est `$?`.
# Sortie : suite_c3.out ; rc=0 ssi pytest 0 (aucun échec, aucun XPASS strict), ruff 0, diff de code vide.
set -o pipefail
set -u
unset VIRTUAL_ENV

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=8689636
OUT=results/c3_v2_2/tests/suite_c3.out
LOG=$(mktemp)
RUFF_FILES=(scripts/audit/_common.py scripts/audit/_db.py scripts/audit/c3*.py scripts/audit/warmup_at.py
  scripts/audit/reconstruct_1w.py tests/test_scripts/test_c3*.py tests/test_scripts/test_warmup_at.py
  tests/test_scripts/test_reconstruct_1w.py tests/test_scripts/test_audit_common.py)
rc=0

{
  echo "# suite_c3 — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse --short HEAD) branche $(git branch --show-current)"
  echo "# indexé : $(git diff --cached --name-only | tr '\n' ' ')"
  echo "# commande : poetry run pytest -q -p no:cacheprovider -rxX tests/test_scripts/test_c3*.py tests/test_scripts/test_c3b*.py"
} > "$OUT"

poetry run pytest -q -p no:cacheprovider -rxX tests/test_scripts/test_c3*.py tests/test_scripts/test_c3b*.py > "$LOG" 2>&1
py=$?
echo "pytest_exit=${py}" >> "$OUT"
grep -E '^(XFAIL|XPASS|FAILED|ERROR) ' "$LOG" | sort >> "$OUT"
tail -n 1 "$LOG" >> "$OUT"
[ "$py" -eq 0 ] || { rc=1; tail -n 60 "$LOG" >> "$OUT"; }

poetry run ruff check "${RUFF_FILES[@]}" > "$LOG" 2>&1
r1=$?
poetry run ruff format --check "${RUFF_FILES[@]}" >> "$LOG" 2>&1
r2=$?
echo "ruff_check=${r1} ruff_format=${r2}" >> "$OUT"
[ "$r1" -eq 0 ] && [ "$r2" -eq 0 ] || { rc=1; tail -n 30 "$LOG" >> "$OUT"; }

if git diff --quiet "$BASE" -- src scripts/audit && git diff --cached --quiet "$BASE" -- src scripts/audit; then v=0; else v=1; rc=1; fi
echo "diff_vide_src_scripts_audit=${v}" >> "$OUT"

rm -f "$LOG"
echo "rc=${rc}" >> "$OUT"
exit "$rc"
