#!/bin/bash
# C3b clôture — preflight du serveur avant la porte § L.5, LECTURE SEULE, lancé par `bash` depuis le dépôt.
# Relève, sans rien écrire sur le serveur : HEAD et arbre du service, interpréteur du venv du service et pytest,
# ~/runs (c3b_gate absent), archive c3b_gate absente, sessions tmux, disque, collector (actif, NRestarts), `.env` du
# service, port Postgres local joignable. Sortie : preflight_server.out, une ligne `clé=valeur`, puis `rc=`.
# rc=0 ssi pytest est importable dans le venv du service, ~/runs/c3b_gate est absent, `.env` est présent au service,
# le port Postgres répond et le collector est actif. pytest absent = STOP (règle du venv unique : pas de poetry install).
set -o pipefail
set -u

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/preflight_server.out

{
  echo "# preflight_server — $(date -u +%FT%TZ)"
  ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' <<'REMOTE'
set -u
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
ok=0
echo "host=$(hostname) date=$(date -u +%FT%TZ)"
echo "service_head=$(git -C "$SERVICE" rev-parse HEAD)"
echo "service_tracked_dirty_lines=$(git -C "$SERVICE" status --porcelain --untracked-files=no | wc -l)"
if [ -x "$PY" ]; then echo "py=$("$PY" -V 2>&1)"; else echo "py=ABSENT"; ok=1; fi
v=$("$PY" -m pytest --version 2>&1); r=$?
echo "pytest_rc=$r pytest=$v"
if [ "$r" -ne 0 ]; then ok=1; fi
echo "runs_entries=$(ls -1A /home/bruno/runs 2>/dev/null | tr '\n' ' ')"
if [ -e /home/bruno/runs/c3b_gate ]; then echo "c3b_gate=PRESENT"; ok=1; else echo "c3b_gate=absent"; fi
echo "archive_c3b_gate=$(ls -1d /home/bruno/archive/c3b_gate_* 2>/dev/null | tr '\n' ' ')"
echo "tmux=$(tmux ls 2>&1 | tr '\n' ';')"
echo "disk_home=$(df -h /home/bruno | awk 'NR==2 {print $4 " libres / " $2}')"
echo "cpus=$(nproc) mem_free_mb=$(free -m | awk '/^Mem:/ {print $7}')"
c=$(systemctl is-active krakenbot-collector 2>&1)
echo "collector=$c $(systemctl show -p NRestarts krakenbot-collector 2>&1)"
if [ "$c" != "active" ]; then ok=1; fi
echo "trader=$(systemctl is-active krakenbot 2>&1)"
if [ -f "$SERVICE/.env" ]; then echo "service_env=present"; else echo "service_env=ABSENT"; ok=1; fi
"$PY" - <<'PYEOF'
import socket
for port in (5432, 5433):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            print(f"pg_port_{port}=open")
    except OSError:
        print(f"pg_port_{port}=closed")
PYEOF
if ! "$PY" -c 'import socket; socket.create_connection(("127.0.0.1", 5432), timeout=1.0)' 2>/dev/null; then ok=1; fi
echo "remote_ok=$ok"
REMOTE
  echo "ssh_exit=$?"
} > "$OUT" 2>&1

if grep -qx "ssh_exit=0" "$OUT" && grep -qx "remote_ok=0" "$OUT"; then
  echo "rc=0" >> "$OUT"
  exit 0
fi
echo "rc=1" >> "$OUT"
exit 1
