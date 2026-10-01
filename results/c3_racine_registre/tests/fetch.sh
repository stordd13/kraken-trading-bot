#!/bin/bash
# C3 racine du registre, lot 2 (repris de l'outillage v2.3, lot 2) — rapatriement des extraits de la phase conf, lancé par `bash` depuis le dépôt
# (modèle : results/c3b_producteur/closure/tests/fetch_gate.sh).
# usage : bash fetch.sh conf
# Ne rapatrie que les extraits de la liste close (attendu § 4 item 5, plan § 8) : status.txt, pilot_exit.txt,
# alembic_before.txt, alembic_after.txt, et pour la porte pytest_summary.txt. Les sorties des producteurs, de la chaîne,
# les journaux et les JUnit restent au serveur (archive), jamais ouverts.
# Sortie : fetch_<phase>.out (code par fichier, sha256 local == distant) ; rc=0 si tout est rapatrié à l'identique.
set -o pipefail
set -u
PHASE=${1:?conf}
case "$PHASE" in
  conf) DEST=results/c3_racine_registre/conformite/server
    FILES=(status.txt pilot_exit.txt alembic_before.txt alembic_after.txt) ;;
  *) echo "phase inconnue : $PHASE" >&2; exit 2 ;;
esac
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_racine_registre/tests/fetch_${PHASE}.out
HOST=bruno@77.42.90.102
G=/home/bruno/runs/c3_racine_registre/$PHASE/out

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
