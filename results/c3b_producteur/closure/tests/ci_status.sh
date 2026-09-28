#!/bin/bash
# C3b clôture — état de la CI (workflow « CI ») sur un SHA poussé, lancé par `bash` depuis le dépôt.
# usage : bash ci_status.sh <sha> <fichier de sortie>
# Attend que le run existe (au plus 5 min), le suit jusqu'à la fin (`gh run watch --exit-status`, journal de suivi
# écarté), puis écrit l'état final lu par `gh run view --json` : statut, conclusion, tentative, étapes en échec.
# Une ligne `clé=valeur` par fait, puis `rc=` : 0 si la conclusion est `success`, 1 sinon, 2 si aucun run trouvé.
# Pas de `set -e` ; aucun PIPESTATUS (aucun pipe dont le code compte).
set -o pipefail
set -u

SHA=${1:?sha}
OUT=${2:?sortie}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2

: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# ci_status — $(date -u +%FT%TZ) — sha $SHA"

id=""
for _ in $(seq 1 30); do
  id=$(gh run list --workflow CI --commit "$SHA" --limit 1 --json databaseId --jq '.[0].databaseId // empty')
  if [ -n "$id" ]; then break; fi
  sleep 10
done
if [ -z "$id" ]; then
  log "run=absent"
  log "rc=2"
  exit 2
fi
log "run=$id url=https://github.com/stordd13/kraken-trading-bot/actions/runs/$id"

gh run watch "$id" --exit-status --interval 30 > /dev/null 2>&1
log "watch_exit=$?"

view=$(gh run view "$id" --json status,conclusion,attempt,headSha,headBranch,event \
  --jq '"status=\(.status)\nconclusion=\(.conclusion)\nattempt=\(.attempt)\nhead_sha=\(.headSha)\nbranch=\(.headBranch)\nevent=\(.event)"')
rc_view=$?
while IFS= read -r line; do log "$line"; done <<< "$view"
log "view_exit=$rc_view"

failed=$(gh run view "$id" --json jobs \
  --jq '[.jobs[].steps[] | select(.conclusion == "failure") | .name] | join(" | ")')
log "failed_steps=${failed:-none}"

if [ "$rc_view" -eq 0 ] && grep -qx "conclusion=success" "$OUT" && grep -qx "head_sha=$SHA" "$OUT"; then
  log "rc=0"
  exit 0
fi
log "rc=1"
exit 1
