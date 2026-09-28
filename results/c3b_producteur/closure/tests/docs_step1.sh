#!/bin/bash
# C3b clôture — contrôle mécanique de l'étape 1 (docs a-f), lancé par `bash` depuis le dépôt, AVANT le commit f,
# avec CLAUDE.md et ce script indexés (plan validé le 2026-09-28). Compare l'INDEX à d351b36 (tip du lot 4b) :
#   - branche, ascendance ;
#   - fichiers changés = exactement ceux des commits a-f (plus ce script) ;
#   - brief et RESEARCH_LOG : zéro ligne retirée (insertion / ajout seul) ; pièce jointe F.2 inchangée ;
#   - aucun code : diff vide sur src, scripts, tests, config, alembic, pyproject, poetry.lock, .github, protocole ;
#   - CAMPAIGN_UNLOCK absent (ni fichier, ni suivi) ;
#   - arbre de travail = index pour les fichiers suivis ;
#   - première ligne du rapport = la phrase exigée, au caractère près.
# Écrit sa sortie dans docs_step1.out (une ligne `clé=code` par contrôle, puis `rc=` global). Pas de `set -e`.
set -o pipefail
set -u

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=d351b36
OUT=results/c3b_producteur/closure/tests/docs_step1.out
EXPECTED=(
  CLAUDE.md
  PROJECT_CONTEXT.md
  ROADMAP.md
  agent/AGENT_C3B_PRODUCTEUR.md
  docs/RESEARCH_LOG.md
  results/INDEX.md
  results/c3b_producteur/closure/tests/docs_step1.sh
  results/c3b_producteur/report.md
  skills/backtest.md
)
SENTENCE="Aucune donnée de la fenêtre de campagne 2021-03-01 → 2026-06-29 n'a été lue par le producteur, sur aucun des trois runs serveur ; aucune issue de chaîne n'a été lue."

: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
fail=0
check() {  # check <clé> <code>
  log "$1=$2"
  if [ "$2" != "0" ]; then fail=1; fi
}

log "# docs_step1 — $(date -u +%FT%TZ)"
log "# HEAD $(git rev-parse HEAD) base $(git rev-parse "$BASE")"
log "# commits base..HEAD :"
while IFS= read -r line; do log "#   $line"; done < <(git log --format='%h %s' "$BASE..HEAD")

b=$(git branch --show-current)
if [ "$b" = "feat/c3b-producteur" ]; then check branch 0; else check branch "1 ($b)"; fi

git merge-base --is-ancestor "$BASE" HEAD
check base_is_ancestor $?

actual=$(git diff --cached --name-only "$BASE" | LC_ALL=C sort)
rc_names=$?
expected=$(printf '%s\n' "${EXPECTED[@]}" | LC_ALL=C sort)
log "# fichiers changés (index vs base) :"
while IFS= read -r line; do log "#   $line"; done <<< "$actual"
if [ "$rc_names" -eq 0 ] && [ "$actual" = "$expected" ]; then check files_exact 0; else check files_exact 1; fi

log "# numstat (ajouts, retraits) :"
while IFS= read -r line; do log "#   $line"; done < <(git diff --cached --numstat "$BASE")

del_of() {  # nombre de lignes retirées d'un fichier, index vs base
  git diff --cached --numstat "$BASE" -- "$1" | awk '{print $2}'
}
d=$(del_of agent/AGENT_C3B_PRODUCTEUR.md)
if [ "$d" = "0" ]; then check brief_insertion_only 0; else check brief_insertion_only "1 (retraits=$d)"; fi
d=$(del_of docs/RESEARCH_LOG.md)
if [ "$d" = "0" ]; then check research_log_append_only 0; else check research_log_append_only "1 (retraits=$d)"; fi

git diff --cached --quiet "$BASE" -- agent/c3b_spec_F2_v2.1.md
check spec_f2_unchanged $?

git diff --cached --quiet "$BASE" -- src scripts tests config alembic pyproject.toml poetry.lock .github \
  docs/protocole_c3.md
check no_code_diff $?

if [ ! -e results/c3b_producteur/CAMPAIGN_UNLOCK ] \
  && ! git ls-files --error-unmatch results/c3b_producteur/CAMPAIGN_UNLOCK > /dev/null 2>&1; then
  check campaign_unlock_absent 0
else
  check campaign_unlock_absent 1
fi

git diff --quiet
check worktree_equals_index $?

first=$(head -n 1 results/c3b_producteur/report.md)
if [ "$first" = "$SENTENCE" ]; then check report_first_line 0; else check report_first_line 1; fi

log "rc=$fail"
exit "$fail"
