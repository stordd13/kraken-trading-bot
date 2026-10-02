#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique (repris de results/c3_campagne_grid/tests/verify.sh) —
# vérification de l'attendu sur les extraits rapatriés (server/ : status.txt, alembic_*.txt, pilot_exit.txt), par
# verify_attendu.py — prouvé avant son premier usage par tests/verify_adverse.sh. Lancé par `bash` depuis le dépôt.
# usage : bash verify.sh <S1, 40 hex>
# Sortie : server/verify_attendu.out (items tenus / écarts, triplet constaté, compté dérivé), puis rc= ; rc=0 ssi tous
# les items sont tenus.
set -o pipefail
set -u
SHA=${1:?sha S1}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/server/verify_attendu.out
python3 results/c3_campagne_grid_v2/server/verify_attendu.py --sha "$SHA" > "$OUT" 2>&1
r=$?
echo "rc=$r" >> "$OUT"
exit $r
