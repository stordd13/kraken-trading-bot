#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 (repris de results/c3_racine_registre/tests/launch.sh) — mise en
# place et lancement du run compté sur le serveur, lancé par `bash` depuis le dépôt, APRÈS le preflight à rc=0 et le
# GO de lancement de Bruno nommant S1.
# usage : bash launch.sh <SHA S1 complet, 40 hex>
# S'arrête au premier code non nul. Étapes (codes dans launch.out) :
#   0. SHA = HEAD local = tip de origin/feat/c3-campagne-grid (git ls-remote) : transport par push, jamais de bundle ;
#   1. ~/runs/c3_campagne_grid/campagne créé (échoue s'il existe) ;
#   2. clone GitHub, fetch de la branche, checkout --detach du SHA, HEAD vérifié ;
#   3. .env copié du service ; out/ créé (pour que pilot_exit.txt s'écrive même si le pilote ne démarre pas) ;
#   4. CAMPAIGN_UNLOCK, créé par Bruno dans l'arbre du service, COPIÉ dans le clone (décision Q2 : transport par script,
#      comme le .env, jamais une création) ; égalité par `cmp`, contenu jamais lu ni affiché, aucun sha ;
#   5. sha du pilote dans le clone == sha du blob local au SHA ;
#   6. session tmux `c3-campagne-grid-<AAAAMMJJ>` : `bash -lc` sur le pilote DU CLONE, sous `nice -n 10`, avec le SHA
#      en argument ; code du pilote dans out/pilot_exit.txt. Aucun kill, aucune relance ; la session se ferme à la
#      sortie du pilote.
set -o pipefail
set -u
SHA=${1:?sha}
PILOT=results/c3_campagne_grid/server/run_campagne.sh
UNLOCK=results/c3b_producteur/CAMPAIGN_UNLOCK
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/launch.out
HOST=bruno@77.42.90.102
SSH=(ssh -p 41922 -o BatchMode=yes "$HOST")
RUN=/home/bruno/runs/c3_campagne_grid/campagne
SESSION=c3-campagne-grid-$(date -u +%Y%m%d)

: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
step() {  # step <clé> <code> : consigne, s'arrête au premier échec
  log "$1=$2"
  if [ "$2" != "0" ]; then
    log "rc=1"
    exit 1
  fi
}
log "# launch — $(date -u +%FT%TZ) — sha $SHA"
if [[ "$SHA" =~ ^[0-9a-f]{40}$ ]] && [ "$(git rev-parse HEAD)" = "$SHA" ]; then r=0; else r=1; fi
step sha_egal_head_local "$r"
remote_tip=$(git ls-remote origin refs/heads/feat/c3-campagne-grid | cut -f1)
log "origin_tip=$remote_tip"
if [ "$remote_tip" = "$SHA" ]; then r=0; else r=1; fi
step sha_egal_tip_origin "$r"
if [ -n "$(git ls-tree "$SHA" -- "$PILOT")" ]; then r=0; else r=1; fi
step pilote_versionne_au_sha "$r"

"${SSH[@]}" "mkdir -p /home/bruno/runs/c3_campagne_grid && mkdir $RUN" >> "$OUT" 2>&1
step mkdir_run $?

"${SSH[@]}" 'bash -s' -- "$SHA" "$RUN" >> "$OUT" 2>&1 <<'REMOTE'
set -u
cd "$2" || exit 10
git clone -q https://github.com/stordd13/kraken-trading-bot.git repo || exit 11
git -C repo fetch -q origin feat/c3-campagne-grid || exit 12
git -C repo checkout -q --detach "$1" || exit 13
[ "$(git -C repo rev-parse HEAD)" = "$1" ] || exit 14
echo "clone_head=$(git -C repo rev-parse HEAD)"
exit 0
REMOTE
step clone $?

"${SSH[@]}" "cp /home/bruno/apps/kraken-trading-bot/.env $RUN/repo/.env && test -f $RUN/repo/.env && mkdir $RUN/out" \
  >> "$OUT" 2>&1
step env_copy_out_dir $?

"${SSH[@]}" "test -f /home/bruno/apps/kraken-trading-bot/$UNLOCK && test ! -e $RUN/repo/$UNLOCK \
&& cp -p /home/bruno/apps/kraken-trading-bot/$UNLOCK $RUN/repo/$UNLOCK \
&& cmp -s /home/bruno/apps/kraken-trading-bot/$UNLOCK $RUN/repo/$UNLOCK" >> "$OUT" 2>&1
step campaign_unlock_transporte_cmp $?

local_sha=$(git show "$SHA:$PILOT" | shasum -a 256 | cut -d' ' -f1)
remote_sha=$("${SSH[@]}" "sha256sum $RUN/repo/$PILOT" | cut -d' ' -f1)
log "pilot_sha256_blob=$local_sha"
log "pilot_sha256_clone=$remote_sha"
if [ -n "$local_sha" ] && [ "$local_sha" = "$remote_sha" ]; then step pilot_cmp 0; else step pilot_cmp 1; fi

"${SSH[@]}" "tmux new -d -s $SESSION \"bash -lc 'nice -n 10 bash $RUN/repo/$PILOT $SHA; echo \\\$? > $RUN/out/pilot_exit.txt'\"" \
  >> "$OUT" 2>&1
step tmux_launch $?
log "session=$SESSION launched_at=$(date -u +%FT%TZ)"
log "rc=0"
exit 0
