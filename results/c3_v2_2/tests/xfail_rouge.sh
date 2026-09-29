#!/bin/bash
# C3 v2.2 — preuve « rouge pour la bonne raison » des xfail d'un commit : relance en --runxfail des tests désignés
# par -k, et ajoute à xfail_rouge.out, sous un en-tête daté, la ligne d'échec de chacun (exception et assertion).
# usage : bash xfail_rouge.sh "<étiquette>" "<expression -k>" <fichiers de test…>
set -o pipefail
set -u
unset VIRTUAL_ENV

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL=${1:?étiquette}
K=${2:?expression -k}
shift 2
OUT=results/c3_v2_2/tests/xfail_rouge.out
LOG=$(mktemp)
{
  echo "## ${LABEL} — $(date -u +%FT%TZ) — HEAD $(git rev-parse --short HEAD)"
  echo "# -k \"${K}\" $*"
} >> "$OUT"
poetry run pytest -q -p no:cacheprovider --runxfail --tb=line -k "$K" "$@" > "$LOG" 2>&1
code=$?
grep -E '^/.*(Error|assert)' "$LOG" | sed "s|${ROOT}/||" >> "$OUT"
tail -n 1 "$LOG" >> "$OUT"
echo "runxfail_exit=${code} (attendu : 1, chaque test désigné en échec)" >> "$OUT"
rm -f "$LOG"
[ "$code" -eq 1 ] && exit 0
exit 1
