#!/bin/bash
# SOL/D2 — pilote serveur du chantier agent/agent_sol_d2_1w_modes.md (GO Bruno 25/09), versionné avec ses preuves.
# Ordre : garde (SHA, arbre) -> alembic current -> warmup_at -> alembic current -> 24 tests _full de déterminisme.
#  - Pas de `set -e` : chaque code est capturé, écrit dans status.txt, puis on continue.
#  - Le second `alembic current` tourne toujours, même si warmup_at sort en 3 (ou 2) : un contrôle en échec ne
#    dispense pas de prouver que la base n'a pas bougé.
#  - Les 24 _full ne sont sautés que si warmup_at sort en 2 (refus, rien mesuré). Ils conditionnent le merge, pas le
#    commit, et tournent ici pour donner une signature à la dette tunnel : une invocation pytest par combo, un JUnit
#    par combo, **les 24 tournent même après un échec** (un combo ou vingt, c'est la distinction qui manquait le
#    24/09), jamais de relance. full= résume : 0, ou FAILED n=<nombre> combos=<liste>.
#  - Codes : 2 = refus (garde : HEAD inattendu, arbre sale, répertoire absent ; ou warmup_at en refus), comme
#    warmup_at ; 1 = au moins une étape en échec (dont warmup_at en 3, contrôle en échec) ; 0 = tout vert.
#  - Toute sortie passée par `tee` est lue par ${PIPESTATUS[0]} capturé sur la ligne suivante, jamais par $?
#    (incident du `tail`, 25/09) ; les combos écrivent dans un fichier sans pipe, leur $? est celui de pytest.
set -o pipefail
set -u
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export POETRY_VIRTUALENVS_IN_PROJECT=true
export NO_COLOR=1

EXPECTED=c38d7183315ed9b28ce7cb859ed8262a03095143
RUN=/home/bruno/runs/sol_d2
REPO=$RUN/repo
OUT=$RUN/out
STATUS=$OUT/status.txt
LOG=$OUT/run.log

mkdir -p "$OUT/full" || exit 2
cd "$REPO" || exit 2

stamp() { date -u +%FT%TZ; }
record() {
  echo "$1" >> "$STATUS"
  echo "=== $1" | tee -a "$LOG"
}

# --- Garde : HEAD attendu, arbre suivi propre --------------------------------------------------------------------
SHA=$(git rev-parse HEAD)
if [ "$SHA" != "$EXPECTED" ]; then
  record "guard=REFUSED head=$SHA expected=$EXPECTED"
  exit 2
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  record "guard=REFUSED tracked_tree_dirty"
  exit 2
fi
record "guard=0 sha=$SHA"
record "start=$(stamp)"

# --- 1. alembic current, avant -----------------------------------------------------------------------------------
poetry run alembic current 2>&1 | tee -a "$OUT/alembic_before.txt" "$LOG"
rc_ab=${PIPESTATUS[0]}
record "alembic_before=$rc_ab"

# --- 2. warmup_at ------------------------------------------------------------------------------------------------
poetry run python scripts/audit/warmup_at.py --output "$OUT/warmup_2021-03-01.json" 2>&1 \
  | tee -a "$OUT/warmup_at.log" "$LOG"
rc_w=${PIPESTATUS[0]}
record "warmup_at=$rc_w at=$(stamp)"

# --- 3. alembic current, après — toujours ------------------------------------------------------------------------
poetry run alembic current 2>&1 | tee -a "$OUT/alembic_after.txt" "$LOG"
rc_aa=${PIPESTATUS[0]}
record "alembic_after=$rc_aa"

# --- 4. les 24 _full, sautés seulement si warmup_at = 2 ----------------------------------------------------------
if [ "$rc_w" -eq 2 ]; then
  record "full=SKIPPED warmup_at=2"
  record "end=$(stamp)"
  exit 2
fi
failed=()
for c in $(seq 0 23); do
  echo "--- combo$c start $(stamp)" | tee -a "$LOG"
  nice -n 5 poetry run pytest -p no:cacheprovider -q --durations=0 \
    --junitxml="$OUT/full/combo$c.xml" \
    "tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[combo$c]" \
    > "$OUT/full/combo$c.log" 2>&1
  rc=$?
  record "combo$c=$rc at=$(stamp)"
  if [ "$rc" -ne 0 ]; then
    failed+=("combo$c")
    tail -25 "$OUT/full/combo$c.log" >> "$LOG"
  fi
done
if [ "${#failed[@]}" -eq 0 ]; then
  full=0
else
  full="FAILED n=${#failed[@]} combos=$(IFS=,; echo "${failed[*]}")"
fi
record "full=$full"
record "end=$(stamp)"

if [ "$rc_ab" -eq 0 ] && [ "$rc_w" -eq 0 ] && [ "$rc_aa" -eq 0 ] && [ "$full" = "0" ]; then
  exit 0
fi
exit 1
