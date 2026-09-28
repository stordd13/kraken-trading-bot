#!/bin/bash
# C3b lot 3 — pilote serveur du run de conformité du producteur préfixe (agent/AGENT_C3B_PRODUCTEUR.md § Lot 3,
# plan validé le 2026-09-27), versionné avec ses preuves. Attendu déclaré avant lancement : ../ATTENDU.md.
#
# Ordre : gardes (SHA, arbre, environnement unique) -> alembic current -> producteur run1 (4 workers) -> producteur run2
# (1 worker) -> alembic current -> sha des sorties run1 == run2 -> chaîne sur run1 (c3_anchor, c3_entry, c3_benchmark,
# c3_select) -> contrôle post-run de l'interpréteur.
#  - Pas de `set -e` : chaque code est capturé, écrit dans status.txt, puis on continue.
#  - Le second `alembic current` tourne toujours, même après un échec du producteur.
#  - Les quatre étapes de la chaîne sont tentées même après un échec en amont (une étape dont l'amont a échoué
#    refuse en code 2 : c'est l'information) ; elles sont sautées seulement si run1 n'a rien produit.
#  - Un seul environnement (GO du 27/09) : l'interpréteur du venv du service, jamais un second venv ; gardes :
#    poetry.lock et pyproject.toml du clone == ceux du service, et `krakenbot` résolu vers le src du clone.
#  - Codes : 2 = refus (garde) ; 1 = au moins une étape hors attendu de code ; 0 = tous les codes attendus.
#  - Toute sortie passée par `tee` est lue par ${PIPESTATUS[0]} sur la ligne suivante, jamais par $?.
#  - Amendements du GO de lancement (Bruno, 28/09) : les six invocations Python du producteur et de la chaîne et le
#    contrôle de l'étape 6 tournent sous `env PYTHONPATH="$REPO/src"` (précède les .pth de l'install éditable du
#    service, transmis aux workers spawn) ; les deux `alembic current` restent sans, depuis l'arbre du service.
#    `pilot_sha256` est consigné après `guard=0`, pour vérifier le pilote versionné contre celui qui a tourné.
set -o pipefail
set -u
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export NO_COLOR=1

EXPECTED=6509737718ba7e645f973e877641d7b2b54ef2ad
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
RUN=/home/bruno/runs/c3b_prefix
REPO=$RUN/repo
OUT=$RUN/out
STATUS=$OUT/status.txt
LOG=$OUT/run.log
MANIFEST=results/c3b_producteur/prefix_conformite/manifest.json
NOW=2026-09-28T00:00:00+00:00

mkdir -p "$OUT/chain" || exit 2
cd "$REPO" || exit 2

stamp() { date -u +%FT%TZ; }
record() {
  echo "$1" >> "$STATUS"
  echo "=== $1" | tee -a "$LOG"
}

# --- Gardes : HEAD attendu, arbre suivi propre, environnement unique ---------------------------------------------
SHA=$(git rev-parse HEAD)
if [ "$SHA" != "$EXPECTED" ]; then
  record "guard=REFUSED head=$SHA expected=$EXPECTED"
  exit 2
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  record "guard=REFUSED tracked_tree_dirty"
  exit 2
fi
for f in poetry.lock pyproject.toml; do
  a=$(sha256sum "$f" | cut -d' ' -f1)
  b=$(sha256sum "$SERVICE/$f" | cut -d' ' -f1)
  if [ "$a" != "$b" ]; then
    record "guard=REFUSED env_mismatch file=$f clone=$a service=$b"
    exit 2
  fi
done
KB=$("$PY" -c "import sys; sys.path.insert(0, '$REPO/src'); import krakenbot; print(krakenbot.__file__)")
if [ "$KB" != "$REPO/src/krakenbot/__init__.py" ]; then
  record "guard=REFUSED krakenbot_resolved=$KB"
  exit 2
fi
if [ ! -f "$REPO/.env" ]; then
  record "guard=REFUSED env_file_absent"
  exit 2
fi
record "guard=0 sha=$SHA python=$("$PY" -V 2>&1) krakenbot=$KB"
record "pilot_sha256=$(sha256sum "$0" | cut -d' ' -f1)"
record "start=$(stamp)"

# --- 1. alembic current, avant (depuis l'arbre du service, lecture de la table de version seule) -----------------
(cd "$SERVICE" && "$PY" -m alembic current) 2>&1 | tee -a "$OUT/alembic_before.txt" "$LOG"
rc_ab=${PIPESTATUS[0]}
record "alembic_before=$rc_ab"

# --- 2. producteur, run1 (4 workers) puis run2 (1 worker) --------------------------------------------------------
env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3b_prefix.py --manifest "$MANIFEST" --output-dir "$OUT/run1" --workers 4 --now "$NOW" 2>&1 \
  | tee -a "$OUT/run1.log" "$LOG"
rc_1=${PIPESTATUS[0]}
record "producer_run1=$rc_1 at=$(stamp)"

env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3b_prefix.py --manifest "$MANIFEST" --output-dir "$OUT/run2" --workers 1 --now "$NOW" 2>&1 \
  | tee -a "$OUT/run2.log" "$LOG"
rc_2=${PIPESTATUS[0]}
record "producer_run2=$rc_2 at=$(stamp)"

# --- 3. alembic current, après — toujours ------------------------------------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) 2>&1 | tee -a "$OUT/alembic_after.txt" "$LOG"
rc_aa=${PIPESTATUS[0]}
record "alembic_after=$rc_aa"

# --- 4. sha des sorties run1 == run2 -----------------------------------------------------------------------------
same=0
for name in observations.json coverage.json candles.json; do
  if [ -f "$OUT/run1/$name" ] && [ -f "$OUT/run2/$name" ]; then
    s1=$(sha256sum "$OUT/run1/$name" | cut -d' ' -f1)
    s2=$(sha256sum "$OUT/run2/$name" | cut -d' ' -f1)
    record "sha_$name run1=$s1 run2=$s2"
    [ "$s1" = "$s2" ] || same=1
  else
    record "sha_$name ABSENT"
    same=1
  fi
done
record "sha_equal=$same"

# --- 5. chaîne sur run1 ------------------------------------------------------------------------------------------
if [ ! -f "$OUT/run1/observations.json" ]; then
  record "chain=SKIPPED run1_sans_sortie"
  record "end=$(stamp)"
  exit 1
fi
C=$OUT/chain
env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3_anchor.py --manifest "$MANIFEST" --registry "$C/variants.json" --output "$C/anchor.json" \
  --now "$NOW" 2>&1 | tee -a "$C/anchor.log" "$LOG"
rc_an=${PIPESTATUS[0]}
record "c3_anchor=$rc_an"
env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3_entry.py --manifest "$MANIFEST" --anchor "$C/anchor.json" \
  --observations "$OUT/run1/observations.json" --coverage "$OUT/run1/coverage.json" \
  --output "$C/entry.json" --markdown "$C/entry.md" --now "$NOW" 2>&1 | tee -a "$C/entry.log" "$LOG"
rc_en=${PIPESTATUS[0]}
record "c3_entry=$rc_en"
env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3_benchmark.py --manifest "$MANIFEST" --anchor "$C/anchor.json" --entry "$C/entry.json" \
  --observations "$OUT/run1/observations.json" --candles "$OUT/run1/candles.json" \
  --output "$C/benchmark.json" --now "$NOW" 2>&1 | tee -a "$C/benchmark.log" "$LOG"
rc_be=${PIPESTATUS[0]}
record "c3_benchmark=$rc_be"
env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3_select.py --manifest "$MANIFEST" --anchor "$C/anchor.json" --entry "$C/entry.json" \
  --observations "$OUT/run1/observations.json" --coverage "$OUT/run1/coverage.json" \
  --benchmark "$C/benchmark.json" --output "$C/selection.json" --markdown "$C/selection.md" --now "$NOW" 2>&1 \
  | tee -a "$C/select.log" "$LOG"
rc_se=${PIPESTATUS[0]}
record "c3_select=$rc_se"

# --- 6. contrôle post-run : l'interpréteur et le paquet consignés par le producteur -----------------------------
env PYTHONPATH="$REPO/src" "$PY" - "$OUT/run1/prefix_run.json" "$REPO" <<'PYEOF' 2>&1 | tee -a "$LOG"
import json, sys
run = json.load(open(sys.argv[1], encoding="utf-8"))
repo = sys.argv[2]
kb = run["interpreter"]["krakenbot"]
print(f"prefix_run interpreter={run['interpreter']['executable']} krakenbot={kb} env={run['environment']}")
sys.exit(0 if kb == f"{repo}/src/krakenbot/__init__.py" else 1)
PYEOF
rc_kb=${PIPESTATUS[0]}
record "interpreter_check=$rc_kb"
record "end=$(stamp)"

if [ "$rc_ab" -eq 0 ] && [ "$rc_1" -eq 0 ] && [ "$rc_2" -eq 0 ] && [ "$rc_aa" -eq 0 ] && [ "$same" -eq 0 ] \
  && [ "$rc_an" -eq 0 ] && [ "$rc_en" -eq 0 ] && [ "$rc_be" -eq 0 ] && [ "$rc_se" -eq 0 ] && [ "$rc_kb" -eq 0 ]; then
  exit 0
fi
exit 1
