#!/bin/bash
# C3b clôture — rapatriement des preuves de la porte § L.5 vers closure/gate_L5/, lancé par `bash` depuis le dépôt.
# Ne rapatrie que les fichiers lisibles sans lecture de métrique : status.txt, pilot_exit.txt, alembic_before.txt,
# alembic_after.txt, pytest_summary.txt. Les journaux et JUnit des combos restent au serveur (archive).
# Sortie : fetch_gate.out (code par fichier, sha256 local == distant), rc=0 si tout est rapatrié à l'identique.
set -o pipefail
set -u

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/fetch_gate.out
DEST=results/c3b_producteur/closure/gate_L5
HOST=bruno@77.42.90.102
G=/home/bruno/runs/c3b_gate/out
FILES=(status.txt pilot_exit.txt alembic_before.txt alembic_after.txt pytest_summary.txt)

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
