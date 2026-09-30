#!/bin/bash
# C3 outillage v2.2, lot 3 — postflight du serveur après les deux phases, LECTURE SEULE, lancé par `bash` depuis le
# dépôt (plans/lot3.md § 6).
# usage : bash postflight.sh <AAAAMMJJ conf> <AAAAMMJJ gate> <HEAD du service relevé au preflight>
# Relève : ~/runs/c3_outillage absent ; aucune session tmux `c3-outillage-*` ; les deux archives présentes et
# `sha256sum -c --status` sur leur .sha256 ; collector actif ; HEAD du service égal à celui du preflight, 0 ligne sale ;
# CAMPAIGN_UNLOCK absent de l'arbre du service. Sortie : postflight.out ; rc=0 ssi tout tient.
set -o pipefail
set -u
DCONF=${1:?date conf}
DGATE=${2:?date gate}
SERVICE_HEAD=${3:?head du service}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_2/tests/postflight.out

{
  echo "# postflight — $(date -u +%FT%TZ)"
  ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' -- "$DCONF" "$DGATE" "$SERVICE_HEAD" <<'REMOTE'
set -u
SERVICE=/home/bruno/apps/kraken-trading-bot
if [ -e /home/bruno/runs/c3_outillage ]; then echo "runs_c3_outillage=PRESENT"; else echo "runs_c3_outillage=absent"; fi
if [ -e "$SERVICE/results/c3b_producteur/CAMPAIGN_UNLOCK" ]; then echo "campaign_unlock_service=PRESENT"; else echo "campaign_unlock_service=absent"; fi
n=$(tmux ls 2>/dev/null | grep -c '^c3-outillage-')
echo "tmux_sessions_chantier=$n"
for pair in "conf $1" "gate $2"; do
  set -- $pair
  ARC=/home/bruno/archive/c3_outillage_$1_$2
  if (cd "$ARC" 2>/dev/null && sha256sum -c --status "c3_outillage_$1_server_$2.tgz.sha256"); then
    echo "archive_$1=0"
  else
    echo "archive_$1=1"
  fi
done
c=$(systemctl is-active krakenbot-collector 2>&1)
echo "collector=$c $(systemctl show -p NRestarts krakenbot-collector 2>&1)"
REMOTE_HEAD=$(git -C "$SERVICE" rev-parse HEAD)
DIRTY=$(git -C "$SERVICE" status --porcelain --untracked-files=no | wc -l)
echo "service_head=$REMOTE_HEAD dirty=$DIRTY"
REMOTE
  echo "ssh_exit=$?"
} > "$OUT" 2>&1
fail=0
grep -qx "ssh_exit=0" "$OUT" || fail=1
grep -qx "runs_c3_outillage=absent" "$OUT" || fail=1
grep -qx "tmux_sessions_chantier=0" "$OUT" || fail=1
grep -qx "campaign_unlock_service=absent" "$OUT" || fail=1
grep -qx "archive_conf=0" "$OUT" || fail=1
grep -qx "archive_gate=0" "$OUT" || fail=1
grep -qE "^collector=active " "$OUT" || fail=1
grep -qx "service_head=$SERVICE_HEAD dirty=0" "$OUT" || fail=1
echo "rc=$fail" >> "$OUT"
exit $fail
