#!/bin/bash
# C3b clôture — attente de la fin du pilote de la porte § L.5, lancé par `bash` en arrière-plan depuis le dépôt.
# Sonde toutes les 5 min (au plus 3 h 30) : existence de out/pilot_exit.txt, nombre de lignes de status.txt et sa
# dernière ligne (des codes seulement). Ne lit rien d'autre, ne tue rien, ne relance rien.
# Sortie : wait_gate.out ; rc=0 si pilot_exit.txt est apparu, 1 sinon (délai dépassé : STOP, rien n'est tué).
set -o pipefail
set -u

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/wait_gate.out
SSH=(ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102)
G=/home/bruno/runs/c3b_gate/out

: > "$OUT"
for i in $(seq 1 42); do
  probe=$("${SSH[@]}" "if [ -f $G/pilot_exit.txt ]; then echo exit=\$(cat $G/pilot_exit.txt); else echo exit=pending; fi; echo lines=\$(wc -l < $G/status.txt); echo last=\$(tail -n 1 $G/status.txt)" 2>&1)
  printf '%s poll=%s %s\n' "$(date -u +%FT%TZ)" "$i" "$(echo "$probe" | tr '\n' ' ')" >> "$OUT"
  if echo "$probe" | grep -qE '^exit=[0-9]+$'; then
    echo "rc=0" >> "$OUT"
    exit 0
  fi
  sleep 300
done
echo "rc=1 (délai dépassé, rien n'est tué)" >> "$OUT"
exit 1
