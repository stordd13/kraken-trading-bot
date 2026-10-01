#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 (repris de results/c3_racine_registre/tests/preflight.sh) — preflight
# du serveur avant le lancement, LECTURE SEULE, lancé par `bash` depuis le dépôt (plans/plan.md § 1).
# usage : bash preflight.sh
# Relève, sans rien écrire sur le serveur : HEAD et lignes sales de l'arbre du service ; interpréteur du venv du
# service et pytest ; sha de poetry.lock et pyproject.toml du service comparés à ceux de HEAD local ; ~/runs (le
# répertoire du chantier absent) ; archive du jour absente ; sessions tmux ; disque ; mémoire disponible ; collector
# (actif, NRestarts) ; trader ; `.env` du service ; ports Postgres 5432 / 5433 ; CAMPAIGN_UNLOCK PRÉSENT dans l'arbre du
# service (existence seule, contenu jamais lu : créé par Bruno entre STOP 1 et le GO, décision Q2). Ne touche jamais le
# répertoire du registre de campagne. Sortie : preflight.out, une ligne `clé=valeur`, puis `rc=`.
# rc=0 ssi : répertoire du chantier absent, archive du jour absente, collector actif, `.env` présent, port 5432 ouvert,
# poetry.lock et pyproject.toml égaux à HEAD, CAMPAIGN_UNLOCK présent, mémoire disponible ≥ 5000 Mo.
# Un refus de preflight = rien lancé, rien écrit : re-tenter le preflight après l'accord de Bruno n'est pas une relance
# du run compté (plan, A5).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/preflight.out
LOCK_SHA=$(git show HEAD:poetry.lock | shasum -a 256 | cut -d' ' -f1)
PYPROJECT_SHA=$(git show HEAD:pyproject.toml | shasum -a 256 | cut -d' ' -f1)
DAY=$(date -u +%Y%m%d)
MEM_MIN_MB=5000

{
  echo "# preflight — $(date -u +%FT%TZ) — HEAD local $(git rev-parse HEAD)"
  ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$LOCK_SHA" "$PYPROJECT_SHA" "$DAY" "$MEM_MIN_MB" <<'REMOTE'
set -u
LOCK_SHA=$1
PYPROJECT_SHA=$2
DAY=$3
MEM_MIN_MB=$4
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
ok=0
echo "host=$(hostname) date=$(date -u +%FT%TZ) bash=${BASH_VERSION}"
echo "service_head=$(git -C "$SERVICE" rev-parse HEAD)"
echo "service_tracked_dirty_lines=$(git -C "$SERVICE" status --porcelain --untracked-files=no | wc -l)"
if [ -x "$PY" ]; then echo "py=$("$PY" -V 2>&1)"; else echo "py=ABSENT"; ok=1; fi
v=$("$PY" -m pytest --version 2>&1); r=$?
echo "pytest_rc=$r pytest=$v"
a=$(sha256sum "$SERVICE/poetry.lock" | cut -d' ' -f1)
b=$(sha256sum "$SERVICE/pyproject.toml" | cut -d' ' -f1)
if [ "$a" = "$LOCK_SHA" ]; then echo "poetry_lock_egal_head=0"; else echo "poetry_lock_egal_head=1"; ok=1; fi
if [ "$b" = "$PYPROJECT_SHA" ]; then echo "pyproject_egal_head=0"; else echo "pyproject_egal_head=1"; ok=1; fi
echo "runs_entries=$(ls -1A /home/bruno/runs 2>/dev/null | tr '\n' ' ')"
if [ -e /home/bruno/runs/c3_campagne_grid ]; then echo "run_dir=PRESENT"; ok=1; else echo "run_dir=absent"; fi
if [ -e "/home/bruno/archive/c3_campagne_grid_$DAY" ]; then echo "archive_du_jour=PRESENT"; ok=1; else echo "archive_du_jour=absent"; fi
echo "tmux=$(tmux ls 2>&1 | tr '\n' ';')"
echo "disk_home=$(df -h /home/bruno | awk 'NR==2 {print $4 " libres / " $2}')"
m=$(free -m | awk '/^Mem:/ {print $7}')
echo "cpus=$(nproc) mem_free_mb=$m mem_min_mb=$MEM_MIN_MB"
if [ -z "$m" ] || [ "$m" -lt "$MEM_MIN_MB" ]; then echo "memoire_suffisante=1"; ok=1; else echo "memoire_suffisante=0"; fi
c=$(systemctl is-active krakenbot-collector 2>&1)
echo "collector=$c $(systemctl show -p NRestarts krakenbot-collector 2>&1)"
if [ "$c" != "active" ]; then ok=1; fi
echo "trader=$(systemctl is-active krakenbot 2>&1)"
if [ -f "$SERVICE/.env" ]; then echo "service_env=present"; else echo "service_env=ABSENT"; ok=1; fi
if [ -f "$SERVICE/results/c3b_producteur/CAMPAIGN_UNLOCK" ]; then echo "campaign_unlock_service=present"; else echo "campaign_unlock_service=ABSENT"; ok=1; fi
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
