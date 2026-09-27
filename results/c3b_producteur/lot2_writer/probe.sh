#!/usr/bin/env bash
# Sonde du lot 2 : relève l'état git, lance probe_writer.py, consigne le code de sortie.
# Usage : bash probe.sh <étiquette> <basetemp>
set -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
LABEL="$1"
BASETEMP="$2"
cd "$ROOT" || exit 2
{
  echo "label=$LABEL"
  echo "branch=$(git branch --show-current)"
  echo "head=$(git rev-parse HEAD)"
  echo "tracked_dirty_lines=$(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
  git status --porcelain --untracked-files=no | sed 's/^/dirty: /'
} > "$HERE/sha_${LABEL}.state.txt"
PYTHONDONTWRITEBYTECODE=1 poetry run python "$HERE/probe_writer.py" "$HERE/sha_${LABEL}.json" "$BASETEMP" \
  2>&1 | tail -n 40 | tee "$HERE/sha_${LABEL}.out"
CODE="${PIPESTATUS[0]}"
echo "probe_exit=$CODE" >> "$HERE/sha_${LABEL}.state.txt"
exit "$CODE"
