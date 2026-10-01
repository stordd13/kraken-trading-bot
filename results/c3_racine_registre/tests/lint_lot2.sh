#!/bin/bash
# C3 racine du registre, lot 2 (repris de results/c3_racine_registre/tests/lint_lot2.sh) — lint des seuls fichiers Python
# du lot, EN VÉRIFICATION SEULEMENT : `ruff check` et `ruff format --check`, jamais `--fix` ni formatage (le lot n'écrit
# aucun code). Les scripts bash du lot sont vérifiés en syntaxe par `bash -n`. Lancé par `bash` depuis le dépôt.
# Sortie : lint_lot2.out ; rc=0 ssi tout est vert.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_racine_registre/tests/lint_lot2.out
PY_FILES=(results/c3_racine_registre/conformite/server/verify_attendu.py)
SH_FILES=(results/c3_racine_registre/conformite/server/run_conformite.sh
  results/c3_racine_registre/tests/{preflight,launch,wait,fetch,archive,postflight,verify_conformite,verify_adverse,pilot_dryrun,events,manifest_check,interdits_lot2,interdits_lot2_adverse,reprise_lot2,invariance_porte,lint_lot2}.sh)
fail=0
: > "$OUT"
echo "# lint_lot2 — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
poetry run ruff check "${PY_FILES[@]}" >> "$OUT" 2>&1; r=$?; echo "ruff_check=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
poetry run ruff format --check "${PY_FILES[@]}" >> "$OUT" 2>&1; r=$?; echo "ruff_format_check=$r" >> "$OUT"
[ $r -ne 0 ] && fail=1
n=0
for f in "${SH_FILES[@]}"; do
  if ! bash -n "$f" 2>> "$OUT"; then echo "bash_n_echec $f" >> "$OUT"; fail=1; fi
  n=$((n + 1))
done
echo "bash_n_fichiers=$n" >> "$OUT"
echo "rc=$fail" >> "$OUT"
exit $fail
