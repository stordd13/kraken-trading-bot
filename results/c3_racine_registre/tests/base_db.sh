#!/bin/bash
# C3 racine du registre, lot 1 (repris de l'outillage v2.3) — les tests base (lecture seule), tunnel ouvert (brief § 3.2 : « ouvert pour les 13 tests
# base »). Sans tunnel, `suite.sh` les voit ignorés (greffon gate_sans_tunnel, comme en CI) : 13 ignorés « base
# injoignable », répartis dans six fichiers (results/c3_v2_3_gel/tests/suite_C2.out). Ici, les six fichiers entiers sont
# lancés tunnel ouvert, sans le greffon, sans les 24 `_full` : rc=0 ssi pytest code 0, aucune ligne FAILED / ERROR, et
# plus aucun test ignoré pour base injoignable ; le décompte des ignorés « base » de la suite sans tunnel (extrait
# suite_<étiquette>.out, 2e argument) est recopié pour la réconciliation (13 attendus).
# Usage : bash base_db.sh <étiquette> <étiquette de suite>. Sortie : base_db_<étiquette>.out.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
SUITE="${2:?étiquette de suite}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DIR=results/c3_racine_registre/tests
OUT="$DIR/base_db_${LABEL}.out"
RAW=$(mktemp)
FILES=(tests/test_strategies/test_grid_atr_v4_backward_compat.py tests/test_scripts/test_run_p6_determinism.py
  tests/test_scripts/test_c2_replay_fidelity_db.py tests/test_scripts/test_rejeu_data_coverage.py
  tests/test_scripts/test_rejeu_benchmark.py tests/test_scripts/test_rejeu_spacing_clamp.py)
{
  echo "# base_db — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
if ! nc -z -w 3 127.0.0.1 5433 > /dev/null 2>&1; then
  echo "tunnel_5433=fermé — rien lancé" >> "$OUT"; echo "rc=2" >> "$OUT"; exit 2
fi
echo "tunnel_5433=ouvert" >> "$OUT"
sans=$(sed -n '/^## ignorés, par raison/,/^resume=/p' "$DIR/suite_${SUITE}.out" | grep -iE 'reachable|injoignable|database' \
  | awk '{s+=$1} END {print s+0}')
echo "ignores_base_sans_tunnel(suite_${SUITE})=$sans" >> "$OUT"
poetry run pytest -q -p no:cacheprovider -rsxX -k "not test_determinism_parallel_vs_serial_full" "${FILES[@]}" \
  > "$RAW" 2>&1
rc_py=$?
echo "pytest_exit=$rc_py" >> "$OUT"
grep -E '^[0-9]+ (passed|failed)' "$RAW" | tail -n 1 | sed 's/^/resume=/' >> "$OUT"
bad=$(grep -cE '^(FAILED|ERROR) ' "$RAW")
still=$(grep -E '^SKIPPED ' "$RAW" | grep -ciE 'reachable|injoignable|database')
echo "failed_error=$bad ignores_base_restants=$still" >> "$OUT"
grep -E '^SKIPPED ' "$RAW" | sed 's/^/  /' >> "$OUT"
rm -f "$RAW"
if [ "$rc_py" -eq 0 ] && [ "$bad" -eq 0 ] && [ "$still" -eq 0 ] && [ "$sans" -eq 13 ]; then
  echo "rc=0" >> "$OUT"; exit 0
fi
echo "rc=1" >> "$OUT"
exit 1
