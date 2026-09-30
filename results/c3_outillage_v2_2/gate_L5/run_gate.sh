#!/bin/bash
# C3 outillage v2.2, lot 3 — porte pré-merge § L.5, option 1 (docs/protocole_c3.md) : les 24 tests
# test_determinism_parallel_vs_serial_full sur le serveur, au SHA S2 (D5 ; code identique au SHA livré, prouvé par
# tests/interdits.sh). Repris de results/c3b_producteur/closure/gate_L5/run_c3b_gate.sh (sha256 be071fff…0c9c,
# 28/09) avec quatre écarts déclarés (plans/lot3.md § 6) :
#   1. le SHA attendu est l'argument (40 hex), pas une constante ;
#   2. le pilote est versionné et exécuté DEPUIS LE CLONE (garde : realpath($0) = le fichier du clone), copié dans
#      out/pilot.sh pour l'archive ;
#   3. `service_before` / `service_after` (HEAD et lignes sales de l'arbre du service, collector) ;
#   4. RUN=~/runs/c3_outillage/gate.
#   bash ~/runs/c3_outillage/gate/repo/results/c3_outillage_v2_2/gate_L5/run_gate.sh <S2, 40 hex>
#
# Ordre : gardes (SHA, pilote du clone, arbre, environnement unique, krakenbot résolu vers le clone, .env, pytest,
# port Postgres) -> alembic current -> 24 combos -> agrégat JUnit -> extrait -> arbre après -> alembic current ->
# interpréteur -> service.
#  - Règles C3b : pas de `set -e` (chaque code capturé dans status.txt, on continue) ; second `alembic current`
#    toujours ; un seul environnement (venv du service, `env PYTHONPATH="$REPO/src"` sur chaque invocation Python,
#    jamais sur alembic) ; `pilot_sha256` consigné après `guard=0` ; pas de kill ; pas de relance.
#  - Garde « port Postgres joignable » : sans base, le module est SKIPPÉ (`pytestmark` du fichier de test) et pytest
#    sort en 0 — un faux vert de porte. Un combo ne passe donc que si rc=0 ET JUnit tests=1 failures=0 errors=0
#    skipped=0.
#  - Non-lecture : `addopts` porte `--showlocals` ; un journal de combo en échec contiendrait les métriques P6 des deux
#    exécutions. Les journaux et JUnit restent en fichiers (archivés), jamais affichés ni recopiés dans le journal du
#    pilote. Remontent : les codes, les comptes JUnit (attributs seuls), et pytest_summary.txt (par combo, la ligne
#    de durée `call` et la ligne de résumé, rien d'autre).
#  - Les 24 tournent même après un échec (un combo ou vingt : la distinction compte), une invocation par combo.
#  - Codes du pilote : 2 = garde refusée ; 1 = au moins un contrôle hors attendu ; 0 = tout vert.
set -o pipefail
set -u
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export NO_COLOR=1

EXPECTED=${1:-}
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
RUN=/home/bruno/runs/c3_outillage/gate
REPO=$RUN/repo
OUT=$RUN/out
STATUS=$OUT/status.txt
LOG=$OUT/run.log
SELF=results/c3_outillage_v2_2/gate_L5/run_gate.sh
TEST=tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full

mkdir -p "$OUT/full" || exit 2
cd "$REPO" || exit 2

stamp() { date -u +%FT%TZ; }
record() {
  echo "$1" >> "$STATUS"
  echo "=== $1" >> "$LOG"
}
sha_of() { sha256sum "$1" | cut -d' ' -f1; }
collector() { echo "$(systemctl is-active krakenbot-collector 2>&1) $(systemctl show -p NRestarts krakenbot-collector 2>&1)"; }
resolved() { env PYTHONPATH="$REPO/src" "$PY" -c 'import krakenbot; print(krakenbot.__file__)' 2>&1; }
service() {
  echo "head=$(git -C "$SERVICE" rev-parse HEAD 2>&1) dirty=$(git -C "$SERVICE" status --porcelain \
--untracked-files=no 2>&1 | wc -l | tr -d ' ')"
}

# --- Gardes -----------------------------------------------------------------------------------------------------------
if ! [[ "$EXPECTED" =~ ^[0-9a-f]{40}$ ]]; then
  record "guard=REFUSED expected_sha_absent_ou_mal_forme"
  exit 2
fi
SHA=$(git rev-parse HEAD)
if [ "$SHA" != "$EXPECTED" ]; then
  record "guard=REFUSED head=$SHA expected=$EXPECTED"
  exit 2
fi
if [ "$(realpath "$0")" != "$(realpath "$REPO/$SELF")" ]; then
  record "guard=REFUSED pilote_hors_clone=$(realpath "$0")"
  exit 2
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  record "guard=REFUSED tracked_tree_dirty"
  exit 2
fi
for f in poetry.lock pyproject.toml; do
  a=$(sha_of "$f")
  b=$(sha_of "$SERVICE/$f")
  if [ "$a" != "$b" ]; then
    record "guard=REFUSED env_mismatch file=$f clone=$a service=$b"
    exit 2
  fi
done
KB=$(resolved)
if [ "$KB" != "$REPO/src/krakenbot/__init__.py" ]; then
  record "guard=REFUSED krakenbot_resolved=$KB"
  exit 2
fi
if [ ! -f "$REPO/.env" ]; then
  record "guard=REFUSED env_file_absent"
  exit 2
fi
PYTEST=$("$PY" -m pytest --version 2>&1)
if [ $? -ne 0 ]; then
  record "guard=REFUSED pytest_absent"
  exit 2
fi
if ! "$PY" -c 'import socket; socket.create_connection(("127.0.0.1", 5432), timeout=2.0)' 2>/dev/null; then
  record "guard=REFUSED postgres_port_5432_closed"
  exit 2
fi
record "guard=0 sha=$SHA python=$("$PY" -V 2>&1) pytest=$PYTEST krakenbot=$KB"
record "pilot_sha256=$(sha_of "$0")"
cp "$0" "$OUT/pilot.sh"
record "pilot_copy=$?"
SERVICE_BEFORE=$(service)
record "service_before=$SERVICE_BEFORE"
record "collector_before=$(collector)"
record "start=$(stamp)"

# --- 1. alembic current, avant (depuis l'arbre du service, sans PYTHONPATH) ---------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_before.txt" 2>&1
rc_ab=$?
record "alembic_before=$rc_ab"

# --- 2. les 24 combos : une invocation par combo, fichiers seulement --------------------------------------------------
junit_of() {  # tests/failures/errors/skipped d'un rapport JUnit, attributs seuls ; `absent` si illisible
  env PYTHONPATH="$REPO/src" "$PY" - "$1" 2>> "$OUT/junit.err" <<'PYEOF'
import sys
import xml.etree.ElementTree as ET

try:
    root = ET.parse(sys.argv[1]).getroot()
except (OSError, ET.ParseError):
    print("absent")
    sys.exit(0)
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
tot = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
print(f"{tot['tests']}/{tot['failures']}/{tot['errors']}/{tot['skipped']}")
PYEOF
}
failed=()
for c in $(seq 0 23); do
  echo "--- combo$c start $(stamp)" >> "$LOG"
  nice -n 5 env PYTHONPATH="$REPO/src" "$PY" -m pytest -p no:cacheprovider -q --durations=0 \
    --junitxml="$OUT/full/combo$c.xml" "$TEST[combo$c]" > "$OUT/full/combo$c.log" 2>&1
  rc=$?
  junit=$(junit_of "$OUT/full/combo$c.xml")
  record "combo$c=$rc junit=$junit at=$(stamp)"
  if [ "$rc" -ne 0 ] || [ "$junit" != "1/0/0/0" ]; then
    failed+=("combo$c")
  fi
done
if [ "${#failed[@]}" -eq 0 ]; then
  full=0
else
  full="FAILED n=${#failed[@]} combos=$(IFS=,; echo "${failed[*]}")"
fi
record "full=$full"

# --- 3. agrégat JUnit des 24 rapports -----------------------------------------------------------------------------------
TOTAL=$(env PYTHONPATH="$REPO/src" "$PY" - "$OUT/full" 2>> "$OUT/junit.err" <<'PYEOF'
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

tot = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
missing = 0
for n in range(24):
    try:
        root = ET.parse(Path(sys.argv[1]) / f"combo{n}.xml").getroot()
    except (OSError, ET.ParseError):
        missing += 1
        continue
    for s in [root] if root.tag == "testsuite" else list(root.iter("testsuite")):
        for k in tot:
            tot[k] += int(s.get(k, 0))
print(",".join(f"{k}:{v}" for k, v in tot.items()) + f",missing:{missing}")
PYEOF
)
record "junit_total=$TOTAL"

# --- 4. extrait : par combo, la ligne de durée `call` et la ligne de résumé, rien d'autre --------------------------------
SUMMARY=$OUT/pytest_summary.txt
: > "$SUMMARY"
lines=0
for c in $(seq 0 23); do
  echo "combo$c" >> "$SUMMARY"
  n=0
  while IFS= read -r line; do
    echo "  $line" >> "$SUMMARY"
    n=$((n + 1))
  done < <(grep -E '^[0-9.]+s call |^[0-9]+ (passed|failed|error|errors|skipped)' "$OUT/full/combo$c.log")
  lines=$((lines + n))
done
if [ "$lines" -eq 48 ]; then extract=0; else extract="1 lines=$lines"; fi
record "extract=$extract"

# --- 5. arbre suivi après, alembic après (toujours), interpréteur, collector, service -----------------------------------
if [ -z "$(git status --porcelain --untracked-files=no)" ]; then tree_after=0; else tree_after=1; fi
record "tree_after=$tree_after"
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_after.txt" 2>&1
rc_aa=$?
record "alembic_after=$rc_aa"
if [ "$(resolved)" = "$REPO/src/krakenbot/__init__.py" ]; then kb=0; else kb=1; fi
record "interpreter_check=$kb"
record "collector_after=$(collector)"
SERVICE_AFTER=$(service)
record "service_after=$SERVICE_AFTER"
record "end=$(stamp)"

if [ "$rc_ab" -eq 0 ] && [ "$full" = "0" ] && [ "$TOTAL" = "tests:24,failures:0,errors:0,skipped:0,missing:0" ] \
  && [ "$extract" = "0" ] && [ "$tree_after" -eq 0 ] && [ "$rc_aa" -eq 0 ] && [ "$kb" -eq 0 ] \
  && [ "$SERVICE_AFTER" = "$SERVICE_BEFORE" ]; then
  exit 0
fi
exit 1
