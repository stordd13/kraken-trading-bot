#!/bin/bash
# C3 outillage v2.2 — suite complète locale, sans les 24 `_full` (porte § L.5 au serveur), tunnel ouvert (les 13
# tests base s'exécutent). Usage : bash suite.sh <étiquette>. Sortie brute au scratchpad si SUITE_RAW est posé,
# sinon dans /tmp du système ; extrait versionné : suite_<étiquette>.out (en-tête, résumé, lignes -rsxX).
# rc=0 ssi : tunnel ouvert, pytest code 0, aucune ligne FAILED / ERROR / XPASS.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DIR=results/c3_outillage_v2_2/tests
OUT="$DIR/suite_${LABEL}.out"
RAW="${SUITE_RAW:-$(mktemp -t suite_raw)}"
{
  echo "# suite — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
  echo "# fichiers suivis modifiés : $(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
  echo "# commande : poetry run pytest -q -p no:cacheprovider -rsxX -k \"not test_determinism_parallel_vs_serial_full\""
} > "$OUT"
if ! nc -z -w 3 127.0.0.1 5433 > /dev/null 2>&1; then
  echo "tunnel_5433=fermé — refus, rien lancé" >> "$OUT"; echo "rc=2" >> "$OUT"; exit 2
fi
echo "tunnel_5433=ouvert" >> "$OUT"
poetry run pytest -q -p no:cacheprovider -rsxX -k "not test_determinism_parallel_vs_serial_full" > "$RAW" 2>&1
rc=$?
echo "pytest_exit=$rc" >> "$OUT"
echo "fin=$(date -u +%FT%TZ)" >> "$OUT"
grep -E '^(FAILED|ERROR|XPASS|XFAIL|SKIPPED) ' "$RAW" | sort >> "$OUT"
grep -E '^[0-9]+ (passed|failed)' "$RAW" | tail -n 1 | sed 's/^/resume=/' >> "$OUT"
bad=$(grep -cE '^(FAILED|ERROR|XPASS) ' "$RAW")
echo "failed_error_xpass=$bad" >> "$OUT"
echo "brut=$RAW" >> "$OUT"
if [ "$rc" -eq 0 ] && [ "$bad" -eq 0 ]; then echo "rc=0" >> "$OUT"; exit 0; fi
echo "rc=1" >> "$OUT"; exit 1
