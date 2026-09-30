#!/usr/bin/env bash
# C3 outillage v2.3 (repris de results/c3_outillage_v2_2/tests/ci_status.sh) — état de la CI (workflow « CI ») sur un SHA poussé, lancé par `bash` depuis le dépôt.
# usage : bash ci_status.sh <sha> <fichier de sortie>
# Forme reprise de results/c3b_producteur/closure/tests/ci_status.sh, plus la règle de relance de Bruno (STOP 2) :
#   relance des jobs en échec pour le flaky connu `test_rejeu_effect` SEUL — l'unique étape en échec est « Run tests »
#   et tous les tests FAILED sont dans tests/test_scripts/test_rejeu_effect.py ; une seule relance. Tout autre rouge
#   est un STOP : aucune relance, rc=1. Le fichier de sortie dit quel job a été relancé et pourquoi.
# Une ligne `clé=valeur` par fait, puis `rc=` : 0 si la conclusion finale est `success` sur le SHA, 1 sinon, 2 si aucun
# run trouvé. Pas de `set -e`.
set -o pipefail
set -u

SHA=${1:?sha}
OUT=${2:?sortie}
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2

: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# ci_status — $(date -u +%FT%TZ) — sha $SHA — branche $(git branch --show-current)"

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

state() {  # $1 = étiquette de la tentative
  gh run watch "$id" --exit-status --interval 30 > /dev/null 2>&1
  log "$1_watch_exit=$?"
  view=$(gh run view "$id" --json status,conclusion,attempt,headSha,headBranch,event \
    --jq '"status=\(.status)\nconclusion=\(.conclusion)\nattempt=\(.attempt)\nhead_sha=\(.headSha)\nbranch=\(.headBranch)\nevent=\(.event)"')
  rc_view=$?
  while IFS= read -r line; do log "$1_$line"; done <<< "$view"
  log "$1_view_exit=$rc_view"
  failed_steps=$(gh run view "$id" --json jobs \
    --jq '[.jobs[].steps[] | select(.conclusion == "failure") | .name] | join(" | ")')
  log "$1_failed_steps=${failed_steps:-none}"
  conclusion=$(printf '%s\n' "$view" | sed -n 's/^conclusion=//p')
  head=$(printf '%s\n' "$view" | sed -n 's/^head_sha=//p')
}

state t1
if [ "$rc_view" -eq 0 ] && [ "$conclusion" = "success" ] && [ "$head" = "$SHA" ]; then
  log "relance=aucune"
  log "rc=0"
  exit 0
fi

# rouge : quels tests ?
tests_failed=$(gh run view "$id" --log-failed 2>/dev/null | grep -oE 'FAILED tests/[^ ]+' | sed 's/^FAILED //' | sort -u)
n_failed=$(printf '%s' "$tests_failed" | grep -c . )
n_other=$(printf '%s' "$tests_failed" | grep -vc '^tests/test_scripts/test_rejeu_effect\.py::')
log "t1_tests_failed=${n_failed}"
while IFS= read -r t; do [ -n "$t" ] && log "t1_failed_test=$t"; done <<< "$tests_failed"

if [ "$failed_steps" = "Run tests" ] && [ "$n_failed" -gt 0 ] && [ "$n_other" -eq 0 ]; then
  jobs_failed=$(gh run view "$id" --json jobs --jq '[.jobs[] | select(.conclusion == "failure") | .name] | join(" | ")')
  log "relance=jobs en échec (${jobs_failed}) — raison : seul test en échec = flaky connu test_rejeu_effect (sous-chaîne '1.645'), règle de Bruno au STOP 2"
  gh run rerun "$id" --failed > /dev/null 2>&1
  log "rerun_exit=$?"
  sleep 20
  state t2
  if [ "$rc_view" -eq 0 ] && [ "$conclusion" = "success" ] && [ "$head" = "$SHA" ]; then
    log "rc=0"
    exit 0
  fi
  log "stop=rouge après la relance unique"
  log "rc=1"
  exit 1
fi

log "relance=aucune — STOP : rouge hors test_rejeu_effect (étapes : ${failed_steps:-?} ; tests hors flaky : ${n_other})"
log "rc=1"
exit 1
