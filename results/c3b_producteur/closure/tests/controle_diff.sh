#!/bin/bash
# C3b clôture — diff de contrôle du chantier, lancé par `bash` depuis le dépôt, les fichiers de la porte INDEXÉS
# (avant le commit de porte).
# usage : bash controle_diff.sh <sha livré S>
#   1. git diff --stat ec7ffb8..S, en clair ;
#   2. chaque fichier changé ∈ liste close amendée (lots 1-4b, _db.py, docs a-f) ou sous results/c3b_producteur/ ;
#   3. diff vide sur les chemins nommés : moteur, runners, p7_grids, compute_benchmarks, rejeu_*, les six c3_* de la
#      chaîne, config/, alembic/, pyproject.toml, poetry.lock, docs/protocole_c3.md ;
#   4. tests/test_scripts/test_c3_*.py : vide, SAUF test_c3_common.py et test_c3_verdict.py, touchés par le seul
#      6953fbc (lot 2, décision 1 de Bruno du 27/09) — vérifié : un seul commit, et diff ec7ffb8..S == diff du commit ;
#   5. src/ : le seul commit 10ed8d8 (lot 1), deux fichiers ;
#   6. invariance : l'index par rapport à S ne touche que results/c3b_producteur/closure/ (aucun code) — la porte
#      jouée à S vaut pour le tip, sans rejeu (précédent C2).
# Sortie : controle_diff.out, une ligne `clé=code` par contrôle, puis `rc=`.
set -o pipefail
set -u

S=${1:?sha livré}
BASE=ec7ffb8
LOT2=6953fbc
LOT1=10ed8d8
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3b_producteur/closure/tests/controle_diff.out
ALLOWED=(
  .github/workflows/ci.yml
  CLAUDE.md
  PROJECT_CONTEXT.md
  ROADMAP.md
  agent/AGENT_C3B_PRODUCTEUR.md
  docs/RESEARCH_LOG.md
  results/INDEX.md
  scripts/audit/_common.py
  scripts/audit/_db.py
  scripts/audit/c3_common.py
  scripts/audit/c3b_common.py
  scripts/audit/c3b_evaluate.py
  scripts/audit/c3b_prefix.py
  scripts/audit/reconstruct_1w.py
  scripts/audit/warmup_at.py
  skills/backtest.md
  src/krakenbot/strategies/base.py
  src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py
  tests/test_scripts/test_audit_common.py
  tests/test_scripts/test_c3_common.py
  tests/test_scripts/test_c3_verdict.py
  tests/test_scripts/test_c3b_common.py
  tests/test_scripts/test_c3b_evaluate.py
  tests/test_scripts/test_c3b_prefix.py
  tests/test_strategies/test_grid_v4_decision_timeframes.py
)
NAMED_EMPTY=(
  scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py scripts/p7_grids.py
  scripts/compute_benchmarks.py ':(glob)scripts/audit/rejeu_*.py'
  scripts/audit/c3_anchor.py scripts/audit/c3_entry.py scripts/audit/c3_benchmark.py scripts/audit/c3_select.py
  scripts/audit/c3_continuity.py scripts/audit/c3_verdict.py
  config alembic pyproject.toml poetry.lock docs/protocole_c3.md
)
C3_TESTS_EMPTY=(
  tests/test_scripts/test_c3_anchor.py tests/test_scripts/test_c3_entry.py tests/test_scripts/test_c3_benchmark.py
  tests/test_scripts/test_c3_select.py tests/test_scripts/test_c3_chronology.py tests/test_scripts/test_c3_continuity.py
)

: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
fail=0
check() { log "$1=$2"; if [ "$2" != "0" ]; then fail=1; fi; }

log "# controle_diff — $(date -u +%FT%TZ)"
log "# base $(git rev-parse "$BASE") S $(git rev-parse "$S") HEAD $(git rev-parse HEAD)"
log "## 1. git diff --stat $BASE..S"
git diff --stat "$BASE" "$S" >> "$OUT"
log "## commits $BASE..S"
git log --format='%h %s' "$BASE..$S" >> "$OUT"

# 2. appartenance à la liste close amendée
out_of_list=0
while IFS= read -r f; do
  ok=1
  case "$f" in results/c3b_producteur/*) ok=0 ;; esac
  for a in "${ALLOWED[@]}"; do
    if [ "$f" = "$a" ]; then ok=0; fi
  done
  if [ "$ok" -ne 0 ]; then
    log "hors_liste: $f"
    out_of_list=1
  fi
done < <(git diff --name-only "$BASE" "$S")
check files_in_closed_list "$out_of_list"

# 3. chemins nommés : diff vide
git diff --quiet "$BASE" "$S" -- "${NAMED_EMPTY[@]}"
check named_paths_empty $?
git diff --quiet "$BASE" "$S" -- "${C3_TESTS_EMPTY[@]}"
check c3_tests_empty_except_two $?

# 4. test_c3_common.py, test_c3_verdict.py : 6953fbc seul
for f in tests/test_scripts/test_c3_common.py tests/test_scripts/test_c3_verdict.py; do
  commits=$(git log --format=%h "$BASE..$S" -- "$f" | tr '\n' ' ')
  log "# $f touché par : $commits($(git diff --numstat "$BASE" "$S" -- "$f" | awk '{print "+" $1 " -" $2}'))"
  if [ "$(git log --format=%H "$BASE..$S" -- "$f")" = "$(git rev-parse "$LOT2")" ]; then c=0; else c=1; fi
  if [ "$(git diff "$BASE" "$S" -- "$f")" = "$(git diff "$LOT2~1" "$LOT2" -- "$f")" ]; then d=0; else d=1; fi
  check "$(basename "$f" .py)_only_$LOT2" "$((c + d))"
done

# 5. src/ : le seul commit du lot 1
if [ "$(git log --format=%H "$BASE..$S" -- src)" = "$(git rev-parse "$LOT1")" ]; then check src_only_lot1 0; else check src_only_lot1 1; fi

# 6. invariance du commit de porte par rapport à S
log "## index vs S"
git diff --cached --name-only "$S" >> "$OUT"
beyond=$(git diff --cached --name-only "$S" | grep -vc '^results/c3b_producteur/closure/')
if [ "$beyond" = "0" ]; then check gate_commit_closure_only 0; else check gate_commit_closure_only 1; fi
git diff --cached --quiet "$S" -- src scripts tests config alembic pyproject.toml poetry.lock .github docs/protocole_c3.md
check gate_commit_no_code $?

log "rc=$fail"
exit "$fail"
