#!/bin/bash
# C3 racine du registre, lot 2 (repris de l'outillage v2.3, lot 2) — postflight du serveur après la phase conf,
# LECTURE SEULE, lancé par `bash` depuis le dépôt (plans/lot2.md L6, brief § 4).
# usage : bash postflight.sh <AAAAMMJJ conf> <HEAD du service relevé au preflight> <NRestarts du preflight>
# Relève : ~/runs/c3_racine_registre absent ; aucune session tmux `c3-racine-registre-*` ; l'archive de la
# conformité présente et `sha256sum -c --status` sur son .sha256 ; collector actif et NRestarts égal à celui du preflight ; HEAD du service
# égal à celui du preflight, 0 ligne sale ; alembic head inchangé (`c3bd1e7a0001 (head)`, depuis l'arbre du service,
# sans PYTHONPATH) ; CAMPAIGN_UNLOCK absent de l'arbre du service. Sortie : postflight.out ; rc=0 ssi tout tient.
# Écarts au postflight v2.2, déclarés : NRestarts comparé au preflight, alembic head relevé (brief § 4).
set -o pipefail
set -u
DCONF=${1:?date conf}
SERVICE_HEAD=${2:?head du service}
NRESTARTS=${3:?NRestarts du preflight}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_racine_registre/tests/postflight.out

{
  echo "# postflight — $(date -u +%FT%TZ)"
  ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$DCONF" <<'REMOTE'
set -u
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
if [ -e /home/bruno/runs/c3_racine_registre ]; then echo "runs_c3_racine_registre=PRESENT"; else echo "runs_c3_racine_registre=absent"; fi
if [ -e "$SERVICE/results/c3b_producteur/CAMPAIGN_UNLOCK" ]; then echo "campaign_unlock_service=PRESENT"; else echo "campaign_unlock_service=absent"; fi
n=$(tmux ls 2>/dev/null | grep -c '^c3-racine-registre-')
echo "tmux_sessions_chantier=$n"
for pair in "conf $1"; do
  set -- $pair
  ARC=/home/bruno/archive/c3_racine_registre_$1_$2
  if (cd "$ARC" 2>/dev/null && sha256sum -c --status "c3_racine_registre_$1_server_$2.tgz.sha256"); then
    echo "archive_$1=0"
  else
    echo "archive_$1=1"
  fi
done
echo "collector=$(systemctl is-active krakenbot-collector 2>&1) $(systemctl show -p NRestarts krakenbot-collector 2>&1)"
REMOTE_HEAD=$(git -C "$SERVICE" rev-parse HEAD)
DIRTY=$(git -C "$SERVICE" status --porcelain --untracked-files=no | wc -l)
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
grep -qx "runs_c3_racine_registre=absent" "$OUT" || fail=1
grep -qx "tmux_sessions_chantier=0" "$OUT" || fail=1
grep -qx "campaign_unlock_service=absent" "$OUT" || fail=1
grep -qx "archive_conf=0" "$OUT" || fail=1
grep -qx "collector=active NRestarts=$NRESTARTS" "$OUT" || fail=1
grep -qx "service_head=$SERVICE_HEAD dirty=0" "$OUT" || fail=1
grep -qx "alembic_head=0" "$OUT" || fail=1
echo "rc=$fail" >> "$OUT"
exit $fail
