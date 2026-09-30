#!/bin/bash
# C3 outillage v2.3, lot 1 (repris du lot 2 v2.2) — critère de fin : « 0 xfail dans la suite hors le caduc déclaré ». Lit l'extrait versionné
# d'une suite (suite_<étiquette>.out, lignes -rsxX) et exige que l'ensemble de ses lignes XFAIL soit exactement le test
# caduc (décision de gate du 29/09, lot 1), sans XPASS ni échec. Usage : bash xfail_fin.sh <étiquette de suite>.
# Sortie : xfail_fin.out ; rc=0 ssi la suite est verte et le seul XFAIL est le caduc.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
SUITE="${1:?étiquette de suite}"
DIR=results/c3_outillage_v2_3/tests
IN="$DIR/suite_${SUITE}.out"
OUT="$DIR/xfail_fin.out"
CADUC="tests/test_scripts/test_c3b_evaluate.py::test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3"
{
  echo "# xfail en fin de lot 1 — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; extrait lu : $IN"
} > "$OUT"
[ -f "$IN" ] || { echo "extrait absent" >> "$OUT"; echo "rc=2" >> "$OUT"; exit 2; }
xfails=$(grep -E '^XFAIL ' "$IN" | sed -E 's/^XFAIL ([^ ]+).*/\1/' | sort -u)
n_xfail=$(printf '%s\n' "$xfails" | grep -c . )
bad=$(grep -cE '^(FAILED|ERROR|XPASS) ' "$IN")
rc_suite=$(grep -E '^rc=' "$IN" | tail -n 1 | cut -d= -f2)
{
  echo "suite_rc=${rc_suite} failed_error_xpass=${bad}"
  echo "xfail_n=${n_xfail}"
  printf '%s\n' "$xfails" | sed 's/^/xfail=/'
  grep -E '^resume=' "$IN"
} >> "$OUT"
if [ "$rc_suite" = "0" ] && [ "$bad" -eq 0 ] && [ "$xfails" = "$CADUC" ]; then
  echo "seul_xfail_le_caduc=oui" >> "$OUT"; echo "rc=0" >> "$OUT"; exit 0
fi
echo "seul_xfail_le_caduc=non" >> "$OUT"; echo "rc=1" >> "$OUT"; exit 1
