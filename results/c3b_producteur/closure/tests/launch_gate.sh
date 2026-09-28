#!/bin/bash
# C3b clôture — mise en place et lancement de la porte § L.5 sur le serveur, lancé par `bash` depuis le dépôt.
# usage : bash launch_gate.sh <sha livré>
# S'arrête au premier code non nul. Étapes (codes dans launch_gate.out) :
#   1. ~/runs/c3b_gate créé (échoue s'il existe) ; 2. clone GitHub, fetch de feat/c3b-producteur, checkout --detach
#   du SHA livré ; 3. .env copié du service ; 4. pilote copié par scp, sha local == sha distant ; 5. session tmux
#   `c3b-gate-<date>` : `bash -lc` sur le pilote, code du pilote dans out/pilot_exit.txt. Aucun kill, aucune relance.
set -o pipefail
set -u

SHA=${1:?sha}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/launch_gate.out
PILOT=results/c3b_producteur/closure/gate_L5/run_c3b_gate.sh
HOST=bruno@77.42.90.102
SSH=(ssh -p 41922 -o BatchMode=yes "$HOST")
SESSION=c3b-gate-$(date -u +%Y%m%d)

: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
step() {  # step <clé> <code> : consigne, s'arrête au premier échec
  log "$1=$2"
  if [ "$2" != "0" ]; then
    log "rc=1"
    exit 1
  fi
}
log "# launch_gate — $(date -u +%FT%TZ) — sha $SHA"
if ! grep -q "^EXPECTED=$SHA\$" "$PILOT"; then step pilot_expected_sha 1; fi
step pilot_expected_sha 0

"${SSH[@]}" 'mkdir /home/bruno/runs/c3b_gate' >> "$OUT" 2>&1
step mkdir_run $?

"${SSH[@]}" 'bash -s' -- "$SHA" >> "$OUT" 2>&1 <<'REMOTE'
set -u
cd /home/bruno/runs/c3b_gate || exit 10
git clone -q https://github.com/stordd13/kraken-trading-bot.git repo || exit 11
git -C repo fetch -q origin feat/c3b-producteur || exit 12
git -C repo checkout -q --detach "$1" || exit 13
[ "$(git -C repo rev-parse HEAD)" = "$1" ] || exit 14
echo "clone_head=$(git -C repo rev-parse HEAD)"
exit 0
REMOTE
step clone $?

"${SSH[@]}" 'cp /home/bruno/apps/kraken-trading-bot/.env /home/bruno/runs/c3b_gate/repo/.env && test -f /home/bruno/runs/c3b_gate/repo/.env' >> "$OUT" 2>&1
step env_copy $?

scp -q -P 41922 -o BatchMode=yes "$PILOT" "$HOST:/home/bruno/runs/c3b_gate/run_c3b_gate.sh" >> "$OUT" 2>&1
step scp_pilot $?

local_sha=$(shasum -a 256 "$PILOT" | cut -d' ' -f1)
remote_sha=$("${SSH[@]}" 'sha256sum /home/bruno/runs/c3b_gate/run_c3b_gate.sh' | cut -d' ' -f1)
log "pilot_sha256_local=$local_sha"
log "pilot_sha256_remote=$remote_sha"
if [ -n "$local_sha" ] && [ "$local_sha" = "$remote_sha" ]; then step pilot_cmp 0; else step pilot_cmp 1; fi

"${SSH[@]}" "tmux new -d -s $SESSION \"bash -lc 'bash /home/bruno/runs/c3b_gate/run_c3b_gate.sh; echo \\\$? > /home/bruno/runs/c3b_gate/out/pilot_exit.txt'\"" >> "$OUT" 2>&1
step tmux_launch $?
log "session=$SESSION launched_at=$(date -u +%FT%TZ)"
log "rc=0"
exit 0
