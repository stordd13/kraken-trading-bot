#!/bin/bash
# C3 outillage v2.3, lot 2 (repris du lot 3 v2.2) — preflight du serveur avant une phase (conf | gate), LECTURE SEULE, lancé par `bash` depuis
# le dépôt (results/c3_outillage_v2_2/plans/lot3.md § 5, § 6 ; modèle : results/c3b_producteur/closure/tests/preflight_server.sh).
# usage : bash preflight.sh <conf|gate>
# Relève, sans rien écrire sur le serveur : HEAD et lignes sales de l'arbre du service ; interpréteur du venv du
# service et pytest ; sha de poetry.lock et pyproject.toml du service comparés à ceux de HEAD local ; ~/runs (le
# répertoire de la phase absent) ; archive du jour de la phase absente ; sessions tmux ; disque ; mémoire ; collector
# (actif, NRestarts) ; trader ; `.env` du service ; ports Postgres 5432 / 5433 ; CAMPAIGN_UNLOCK absent de l'arbre du
# service. Sortie : preflight_<phase>.out, une ligne `clé=valeur`, puis `rc=`.
# rc=0 ssi : répertoire de la phase absent, archive du jour absente, collector actif, `.env` présent, port 5432 ouvert,
# poetry.lock et pyproject.toml égaux à HEAD, CAMPAIGN_UNLOCK absent, et (gate) pytest importable.
set -o pipefail
set -u
PHASE=${1:?conf ou gate}
case "$PHASE" in conf | gate) ;; *) echo "phase inconnue : $PHASE" >&2; exit 2 ;; esac
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_3/tests/preflight_${PHASE}.out
LOCK_SHA=$(git show HEAD:poetry.lock | shasum -a 256 | cut -d' ' -f1)
PYPROJECT_SHA=$(git show HEAD:pyproject.toml | shasum -a 256 | cut -d' ' -f1)
DAY=$(date -u +%Y%m%d)

{
  echo "# preflight $PHASE — $(date -u +%FT%TZ) — HEAD local $(git rev-parse HEAD)"
  ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$PHASE" "$LOCK_SHA" "$PYPROJECT_SHA" "$DAY" <<'REMOTE'
set -u
PHASE=$1
LOCK_SHA=$2
PYPROJECT_SHA=$3
DAY=$4
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
ok=0
echo "host=$(hostname) date=$(date -u +%FT%TZ) bash=${BASH_VERSION}"
echo "service_head=$(git -C "$SERVICE" rev-parse HEAD)"
echo "service_tracked_dirty_lines=$(git -C "$SERVICE" status --porcelain --untracked-files=no | wc -l)"
if [ -x "$PY" ]; then echo "py=$("$PY" -V 2>&1)"; else echo "py=ABSENT"; ok=1; fi
v=$("$PY" -m pytest --version 2>&1); r=$?
echo "pytest_rc=$r pytest=$v"
if [ "$PHASE" = gate ] && [ "$r" -ne 0 ]; then ok=1; fi
a=$(sha256sum "$SERVICE/poetry.lock" | cut -d' ' -f1)
b=$(sha256sum "$SERVICE/pyproject.toml" | cut -d' ' -f1)
if [ "$a" = "$LOCK_SHA" ]; then echo "poetry_lock_egal_head=0"; else echo "poetry_lock_egal_head=1 service=$a"; ok=1; fi
if [ "$b" = "$PYPROJECT_SHA" ]; then echo "pyproject_egal_head=0"; else echo "pyproject_egal_head=1 service=$b"; ok=1; fi
echo "runs_entries=$(ls -1A /home/bruno/runs 2>/dev/null | tr '\n' ' ')"
if [ -e "/home/bruno/runs/c3_outillage_v2_3/$PHASE" ]; then echo "run_dir=PRESENT"; ok=1; else echo "run_dir=absent"; fi
if [ -e "/home/bruno/archive/c3_outillage_v2_3_${PHASE}_$DAY" ]; then echo "archive_du_jour=PRESENT"; ok=1; else echo "archive_du_jour=absent"; fi
echo "tmux=$(tmux ls 2>&1 | tr '\n' ';')"
echo "disk_home=$(df -h /home/bruno | awk 'NR==2 {print $4 " libres / " $2}')"
echo "cpus=$(nproc) mem_free_mb=$(free -m | awk '/^Mem:/ {print $7}')"
c=$(systemctl is-active krakenbot-collector 2>&1)
echo "collector=$c $(systemctl show -p NRestarts krakenbot-collector 2>&1)"
if [ "$c" != "active" ]; then ok=1; fi
echo "trader=$(systemctl is-active krakenbot 2>&1)"
if [ -f "$SERVICE/.env" ]; then echo "service_env=present"; else echo "service_env=ABSENT"; ok=1; fi
if [ -e "$SERVICE/results/c3b_producteur/CAMPAIGN_UNLOCK" ]; then echo "campaign_unlock_service=PRESENT"; ok=1; else echo "campaign_unlock_service=absent"; fi
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
