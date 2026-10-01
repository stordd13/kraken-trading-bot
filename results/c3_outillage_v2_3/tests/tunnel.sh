#!/bin/bash
# C3 outillage v2.3 (repris de v2.2) — tunnel SSH vers la base (127.0.0.1:5433), lecture seule, pour les tests base de la suite.
# Usage : bash tunnel.sh open | close | state. Chaque appel ajoute une ligne horodatée à tunnel.out.
# open  : lance autossh (skills/database.md), puis exige que le port réponde ; rc=0 ssi ouvert.
# close : tue le seul autossh/ssh qui porte ce transfert, puis exige que le port NE réponde plus ; rc=0 ssi fermé.
# state : consigne l'état ; rc=0 toujours.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
OUT="$ROOT/results/c3_outillage_v2_3/tests/tunnel.out"
FWD="127.0.0.1:5433:localhost:5432"
now() { date -u +%FT%TZ; }
is_open() { nc -z -w 3 127.0.0.1 5433 > /dev/null 2>&1; }
action="${1:-state}"
case "$action" in
  open)
    if is_open; then
      echo "$(now) open : déjà ouvert" >> "$OUT"
    else
      autossh -M 0 -f -N -L "$FWD" bruno@77.42.90.102 -p 41922 \
        -o ExitOnForwardFailure=yes -o ServerAliveInterval=60
      for _ in 1 2 3 4 5 6 7 8 9 10; do is_open && break; sleep 1; done
    fi
    if is_open; then echo "$(now) open : port 5433 ouvert" >> "$OUT"; exit 0; fi
    echo "$(now) open : ÉCHEC, port 5433 fermé" >> "$OUT"; exit 1
    ;;
  close)
    pids=$(pgrep -f "$FWD" | tr '\n' ' ')
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill $pids
    fi
    for _ in 1 2 3 4 5; do is_open || break; sleep 1; done
    if is_open; then echo "$(now) close : ÉCHEC, port 5433 encore ouvert (pids ${pids:-aucun})" >> "$OUT"; exit 1; fi
    echo "$(now) close : port 5433 fermé (pids tués : ${pids:-aucun}) ; nc -z échoue" >> "$OUT"; exit 0
    ;;
  state)
    if is_open; then echo "$(now) state : ouvert" >> "$OUT"; else echo "$(now) state : fermé" >> "$OUT"; fi
    exit 0
    ;;
  *) echo "usage : tunnel.sh open|close|state" >&2; exit 2 ;;
esac
