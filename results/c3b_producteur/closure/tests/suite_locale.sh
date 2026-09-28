#!/bin/bash
# C3b clôture — suite complète locale au SHA livré, sans les 24 `_full` (ils tournent au serveur, porte § L.5),
# lancée par `bash` depuis le dépôt. Pas de pipe sur pytest : sa sortie va dans le fichier, son code est `$?`.
# Attendu (lot 4b, aucun code changé depuis) : 3 264 passés, 6 ignorés, 24 désélectionnés, 0 échec, code 0.
# Tunnel (127.0.0.1:5433) vérifié avant : sans lui, les tests base seraient skippés — refus (2), rien lancé.
# Sortie : suite_locale.out ; rc=0 ssi code pytest 0 et résumé exact.
set -o pipefail
set -u
unset VIRTUAL_ENV

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/suite_locale.out
EXPECT_PASSED=3264
EXPECT_SKIPPED=6
EXPECT_DESELECTED=24

{
  echo "# suite locale — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
  echo "# lignes suivies modifiées : $(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
  echo "# commande : poetry run pytest -q -p no:cacheprovider -k \"not test_determinism_parallel_vs_serial_full\""
} > "$OUT"

if ! nc -z -w 2 127.0.0.1 5433 > /dev/null 2>&1; then
  echo "tunnel_5433=closed" >> "$OUT"
  echo "rc=2" >> "$OUT"
  exit 2
fi
echo "tunnel_5433=open" >> "$OUT"

poetry run pytest -q -p no:cacheprovider -k "not test_determinism_parallel_vs_serial_full" >> "$OUT" 2>&1
rc=$?
echo "pytest_exit=$rc" >> "$OUT"
echo "end=$(date -u +%FT%TZ)" >> "$OUT"

summary=$(grep -E '^[0-9]+ passed' "$OUT" | tail -n 1)
want="$EXPECT_PASSED passed, $EXPECT_SKIPPED skipped, $EXPECT_DESELECTED deselected in "
if [ "$rc" -eq 0 ] && [ "${summary#"$want"}" != "$summary" ]; then
  echo "summary_exact=0" >> "$OUT"
  echo "rc=0" >> "$OUT"
  exit 0
fi
echo "summary_exact=1 (attendu : $want…)" >> "$OUT"
echo "rc=1" >> "$OUT"
exit 1
