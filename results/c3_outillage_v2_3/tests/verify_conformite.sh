#!/bin/bash
# C3 outillage v2.3, lot 2 (repris du lot 3 v2.2) — vérification de l'attendu de conformité sur les extraits rapatriés (conformite/server/ :
# status.txt, alembic_*.txt, pilot_exit.txt), par verify_attendu.py — prouvé avant son premier usage par
# tests/verify_adverse.sh (condition du GO). Lancé par `bash` depuis le dépôt.
# usage : bash verify_conformite.sh <S1, 40 hex>
# Sortie : conformite/server/verify_attendu.out (items tenus / écarts), puis rc= ; rc=0 ssi tous les items sont tenus.
set -o pipefail
set -u
SHA=${1:?sha S1}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_3/conformite/server/verify_attendu.out
python3 results/c3_outillage_v2_3/conformite/server/verify_attendu.py --sha "$SHA" > "$OUT" 2>&1
r=$?
echo "rc=$r" >> "$OUT"
exit $r
