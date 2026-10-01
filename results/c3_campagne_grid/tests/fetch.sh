#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 (repris de results/c3_racine_registre/tests/fetch.sh) — rapatriement
# des extraits du run, lancé par `bash` depuis le dépôt.
# usage : bash fetch.sh
# Ne rapatrie que la liste close (plan § 2, attendu § 9) : status.txt, pilot_exit.txt, alembic_before.txt,
# alembic_after.txt. Les sorties des producteurs et de la chaîne, les journaux et le registre restent au serveur,
# jamais ouverts. Avant S2, la règle 64 hex d'interdits.sh est balayée sur ces quatre fichiers (plan, A4).
# Sortie : fetch.out (code par fichier, sha256 local == distant : ce sont des fichiers du chantier, jamais des artefacts
# du chemin) ; rc=0 si tout est rapatrié à l'identique.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DEST=results/c3_campagne_grid/server
FILES=(status.txt pilot_exit.txt alembic_before.txt alembic_after.txt)
OUT=results/c3_campagne_grid/tests/fetch.out
HOST=bruno@77.42.90.102
G=/home/bruno/runs/c3_campagne_grid/campagne/out

: > "$OUT"
fail=0
for f in "${FILES[@]}"; do
  scp -q -P 41922 -o BatchMode=yes "$HOST:$G/$f" "$DEST/$f" >> "$OUT" 2>&1
  r=$?
  l=$(shasum -a 256 "$DEST/$f" 2>/dev/null | cut -d' ' -f1)
  d=$(ssh -p 41922 -o BatchMode=yes "$HOST" "sha256sum $G/$f" 2>/dev/null | cut -d' ' -f1)
  if [ "$r" -eq 0 ] && [ -n "$l" ] && [ "$l" = "$d" ]; then s=0; else s=1; fail=1; fi
  echo "$f=$s sha256=$l" >> "$OUT"
done
echo "rc=$fail" >> "$OUT"
exit "$fail"
