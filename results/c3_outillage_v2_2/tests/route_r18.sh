#!/bin/bash
# C3 outillage v2.2, lot 2 — obligation b du lot 1 : test_R18_un_refus_qui_porte_des_series_se_contredit, levé au lot 1
# par la violation C-3 au verdict (D12a), passe désormais par l'admission de la forme de refus : la continuité constate
# « refus + séries » (violation, code 1) et la chaîne s'arrête à l'étape 5, avant tout verdict. Le test est relancé
# sans capture ; rc=0 ssi : pytest code 0, la violation « refus + séries » dite, la chaîne arrêtée à `continuity` en
# code 1, aucune violation du recalcul de l'export (C-3) dite.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_2/tests/route_r18.out
LOG=$(mktemp)
T="tests/test_scripts/test_c3_verdict.py::test_R18_un_refus_qui_porte_des_series_se_contredit"
{
  echo "# route du test R-18 « refus avec séries » — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
  echo "# commande : pytest -q -s -p no:cacheprovider $T"
  echo "# route au lot 1 (lot1_chaine/README.md § 4) : violation C-3 au verdict (export sans estampille d'entrée)"
} > "$OUT"
poetry run pytest -q -s -p no:cacheprovider "$T" > "$LOG" 2>&1
code=$?
grep -E 'VIOLATION|CHAINE ARRETEE|non reconstructible' "$LOG" | cut -c1-220 >> "$OUT"
tail -n 1 "$LOG" >> "$OUT"
n_series=$(grep -c "un bloc \`refused\` et des séries" "$LOG")
n_stop=$(grep -c "CHAINE ARRETEE à l'étape continuity (code de retour 1)" "$LOG")
n_c3=$(grep -c "non reconstructible sur candles_eval.json" "$LOG")
echo "pytest_exit=$code (attendu 0) refus_plus_series=$n_series (attendu ≥ 1) arret_continuite_code_1=$n_stop (attendu 1) violation_C3=$n_c3 (attendu 0)" >> "$OUT"
rm -f "$LOG"
if [ "$code" -eq 0 ] && [ "$n_series" -ge 1 ] && [ "$n_stop" -eq 1 ] && [ "$n_c3" -eq 0 ]; then
  echo "rc=0" >> "$OUT"; exit 0
fi
echo "rc=1" >> "$OUT"; exit 1
