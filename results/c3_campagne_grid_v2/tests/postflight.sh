#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique (repris de results/c3_campagne_grid/tests/postflight.sh) —
# postflight du serveur après l'archive, LECTURE SEULE, lancé par `bash` depuis le dépôt (plans/plan.md § 5).
# usage : bash postflight.sh <AAAAMMJJ de l'archive> <HEAD du service relevé au preflight> <NRestarts du preflight>
# Relève : ~/runs/c3_campagne_grid absent ; aucune session tmux `c3-campagne-grid-*` ; les DEUX archives — celle du
# run v2 (date en argument) et celle du run v1 faite par l'archive-préalable (c3_campagne_grid_20261001, littéral) —
# présentes, en lecture seule, sans repo/ ni .env, témoins présents (codes seulement : ni taille, ni compte, ni sha) ; collector actif et
# NRestarts égal à celui du preflight ; HEAD du service égal à celui du preflight, 0 ligne sale ; alembic head inchangé
# (`c3bd1e7a0001 (head)`, depuis l'arbre du service, sans PYTHONPATH) ; CAMPAIGN_UNLOCK de l'arbre du service présent,
# jamais touché (Bruno le supprime après le merge). JAMAIS le répertoire du registre de campagne : ni lecture, ni stat,
# ni sha, ni listing — la vérification des clés de racine et la sauvegarde sont la cérémonie de Bruno, après STOP 2.
# Sortie : postflight.out ; rc=0 ssi tout tient.
set -o pipefail
set -u
DARC=${1:?date de l archive}
SERVICE_HEAD=${2:?head du service}
NRESTARTS=${3:?NRestarts du preflight}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/tests/postflight.out

{
  echo "# postflight — $(date -u +%FT%TZ)"
  ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$DARC" <<'REMOTE'
set -u
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
ARC=/home/bruno/archive/c3_campagne_grid_$1
if [ -e /home/bruno/runs/c3_campagne_grid ]; then echo "runs_c3_campagne_grid=PRESENT"; else echo "runs_c3_campagne_grid=absent"; fi
if [ -f "$SERVICE/results/c3b_producteur/CAMPAIGN_UNLOCK" ]; then echo "campaign_unlock_service=present"; else echo "campaign_unlock_service=ABSENT"; fi
n=$(tmux ls 2>/dev/null | grep -c '^c3-campagne-grid-')
echo "tmux_sessions_chantier=$n"
if [ -f "$ARC/out/status.txt" ] && [ -f "$ARC/out/pilot_exit.txt" ]; then echo "archive_presente=0"; else echo "archive_presente=1"; fi
w=$(find "$ARC/out" -perm /222 2>/dev/null | wc -l | tr -d ' ')
if [ -d "$ARC/out" ] && [ "$w" = "0" ]; then echo "archive_lecture_seule=0"; else echo "archive_lecture_seule=1"; fi
f=$(find "$ARC" \( -name repo -o -name .env \) 2>/dev/null | wc -l | tr -d ' ')
if [ "$f" = "0" ]; then echo "archive_sans_repo_ni_env=0"; else echo "archive_sans_repo_ni_env=1"; fi
# l'archive du run v1 (archive-préalable, plan § 2), mêmes contrôles
ARC1=/home/bruno/archive/c3_campagne_grid_20261001
if [ -f "$ARC1/out/status.txt" ] && [ -f "$ARC1/out/pilot_exit.txt" ]; then echo "archive_v1_presente=0"; else echo "archive_v1_presente=1"; fi
w=$(find "$ARC1/out" -perm /222 2>/dev/null | wc -l | tr -d ' ')
if [ -d "$ARC1/out" ] && [ "$w" = "0" ]; then echo "archive_v1_lecture_seule=0"; else echo "archive_v1_lecture_seule=1"; fi
f=$(find "$ARC1" \( -name repo -o -name .env \) 2>/dev/null | wc -l | tr -d ' ')
if [ "$f" = "0" ]; then echo "archive_v1_sans_repo_ni_env=0"; else echo "archive_v1_sans_repo_ni_env=1"; fi
echo "collector=$(systemctl is-active krakenbot-collector 2>&1) $(systemctl show -p NRestarts krakenbot-collector 2>&1)"
REMOTE_HEAD=$(git -C "$SERVICE" rev-parse HEAD)
DIRTY=$(git -C "$SERVICE" status --porcelain --untracked-files=no | wc -l | tr -d ' ')
echo "service_head=$REMOTE_HEAD dirty=$DIRTY"
if (cd "$SERVICE" && "$PY" -m alembic current 2>&1) | grep -qF "c3bd1e7a0001 (head)"; then
  echo "alembic_head=0"
else
  echo "alembic_head=1"
fi
REMOTE
  echo "ssh_exit=$?"
} > "$OUT" 2>&1
fail=0
grep -qx "ssh_exit=0" "$OUT" || fail=1
grep -qx "runs_c3_campagne_grid=absent" "$OUT" || fail=1
grep -qx "tmux_sessions_chantier=0" "$OUT" || fail=1
grep -qx "campaign_unlock_service=present" "$OUT" || fail=1
grep -qx "archive_presente=0" "$OUT" || fail=1
grep -qx "archive_lecture_seule=0" "$OUT" || fail=1
grep -qx "archive_sans_repo_ni_env=0" "$OUT" || fail=1
grep -qx "archive_v1_presente=0" "$OUT" || fail=1
grep -qx "archive_v1_lecture_seule=0" "$OUT" || fail=1
grep -qx "archive_v1_sans_repo_ni_env=0" "$OUT" || fail=1
grep -qx "collector=active NRestarts=$NRESTARTS" "$OUT" || fail=1
grep -qx "service_head=$SERVICE_HEAD dirty=0" "$OUT" || fail=1
grep -qx "alembic_head=0" "$OUT" || fail=1
echo "rc=$fail" >> "$OUT"
exit $fail
