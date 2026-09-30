#!/bin/bash
# C3 outillage v2.2, lot 3 — attente de la fin du pilote d'une phase (conf | gate), lancé par `bash` en arrière-plan
# depuis le dépôt (modèle : results/c3b_producteur/closure/tests/wait_gate.sh).
# usage : bash wait.sh <conf|gate> <intervalle en s> <nombre maximal de sondes>
# Sonde : existence de out/pilot_exit.txt, nombre de lignes de status.txt et sa dernière ligne (des codes et des
# booléens seulement — status.txt ne porte rien d'autre). Ne lit rien d'autre, ne tue rien, ne relance rien.
# Sortie : wait_<phase>.out ; rc=0 si pilot_exit.txt est apparu, 1 sinon (délai dépassé : STOP, rien n'est tué).
set -o pipefail
set -u
PHASE=${1:?conf ou gate}
INTERVAL=${2:?intervalle}
MAX=${3:?sondes}
case "$PHASE" in conf | gate) ;; *) echo "phase inconnue : $PHASE" >&2; exit 2 ;; esac
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_2/tests/wait_${PHASE}.out
SSH=(ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102)
G=/home/bruno/runs/c3_outillage/$PHASE/out

: > "$OUT"
for i in $(seq 1 "$MAX"); do
  probe=$("${SSH[@]}" "if [ -f $G/pilot_exit.txt ]; then echo exit=\$(cat $G/pilot_exit.txt); else echo exit=pending; fi; echo lines=\$(wc -l < $G/status.txt); echo last=\$(tail -n 1 $G/status.txt)" 2>&1)
  printf '%s poll=%s %s\n' "$(date -u +%FT%TZ)" "$i" "$(echo "$probe" | tr '\n' ' ')" >> "$OUT"
  if echo "$probe" | grep -qE '^exit=[0-9]+$'; then
    echo "rc=0" >> "$OUT"
    exit 0
  fi
  sleep "$INTERVAL"
done
echo "rc=1 (délai dépassé, rien n'est tué)" >> "$OUT"
exit 1
