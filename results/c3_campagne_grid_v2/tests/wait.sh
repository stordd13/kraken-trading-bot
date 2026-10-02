#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique (repris de results/c3_campagne_grid/tests/wait.sh) —
# attente de la fin du pilote, lancé par `bash` en arrière-plan depuis le dépôt.
# usage : bash wait.sh <intervalle en s> <nombre maximal de sondes>   (plan v1 § 1, inchangé : 120 120, plafond 4 h)
# Sonde : existence de out/pilot_exit.txt, nombre de lignes de status.txt et la CLÉ de sa dernière ligne — jamais sa
# valeur (plan v1 § 1). Ne lit rien d'autre, ne tue rien, ne relance rien.
# Sortie : wait.out ; rc=0 si pilot_exit.txt est apparu, 1 sinon (délai dépassé : STOP, rien n'est tué).
set -o pipefail
set -u
INTERVAL=${1:?intervalle}
MAX=${2:?sondes}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/tests/wait.out
SSH=(ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102)
G=/home/bruno/runs/c3_campagne_grid/campagne/out

: > "$OUT"
for i in $(seq 1 "$MAX"); do
  probe=$("${SSH[@]}" "if [ -f $G/pilot_exit.txt ]; then echo exit=\$(cat $G/pilot_exit.txt); else echo exit=pending; fi; echo lines=\$(wc -l < $G/status.txt); echo last_key=\$(tail -n 1 $G/status.txt | cut -d= -f1)" 2>&1)
  printf '%s poll=%s %s\n' "$(date -u +%FT%TZ)" "$i" "$(echo "$probe" | tr '\n' ' ')" >> "$OUT"
  if echo "$probe" | grep -qE '^exit=[0-9]+$'; then
    echo "rc=0" >> "$OUT"
    exit 0
  fi
  sleep "$INTERVAL"
done
echo "rc=1 (délai dépassé, rien n'est tué)" >> "$OUT"
exit 1
