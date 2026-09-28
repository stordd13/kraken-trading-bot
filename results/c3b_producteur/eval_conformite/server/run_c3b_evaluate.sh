#!/bin/bash
# C3b lot 4a — pilote serveur du run de conformité du producteur d'évaluation (agent/AGENT_C3B_PRODUCTEUR.md § Lot 4a,
# plan validé le 2026-09-28), versionné avec ses preuves. Attendu déclaré avant lancement : ../ATTENDU.md.
#
# Ordre : gardes (SHA, arbre, environnement unique) -> alembic current -> désignation recalculée (== valeur déclarée,
# sinon garde refusée) -> chemin sélection x2 -> chemin désigné x2 -> alembic current -> admission -> comparateur
# d'évaluation synthétique -> c3_continuity -> clauses c1/c2/c5 -> contrôle de l'interpréteur.
#  - Règles du lot 3 reprises : pas de `set -e` (chaque code capturé dans status.txt, on continue) ; second
#    `alembic current` toujours ; un seul environnement (venv du service, `env PYTHONPATH="$REPO/src"` sur chaque
#    invocation Python, jamais sur alembic) ; toute sortie passée par `tee` est lue par ${PIPESTATUS[0]} ;
#    `pilot_sha256` consigné après `guard=0`.
#  - Les deux chemins tournent toujours, le pilote ne branche jamais sur le code de la sélection (plan, point 1).
#  - Chemin sélection : sortie et journal **en fichier seulement** (ni tee, ni écran : le moteur y journalise sa
#    paire) ; seuls le code, l'événement (`nothing_to_evaluate` si 2) et l'égalité des sha sont consignés.
#  - Codes du pilote : 2 = refus (garde) ; 1 = au moins une étape hors attendu ; 0 = tous les codes attendus.
set -o pipefail
set -u
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export NO_COLOR=1

EXPECTED=85c8db71cc4666db0e1a982dc1c70e840cf9c20f
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
RUN=/home/bruno/runs/c3b_eval4a
REPO=$RUN/repo
OUT=$RUN/out
STATUS=$OUT/status.txt
LOG=$OUT/run.log
MANIFEST=results/c3b_producteur/prefix_conformite/manifest.json
ANCHOR=results/c3b_producteur/prefix_conformite/server/chain/anchor.json
SELECTION=results/c3b_producteur/prefix_conformite/server/chain/selection.json
DESIGNATED=145867637b7f9bac6b556efc9dc48e929f18624f1c56d54eebe83b6c5eb47962
NOW=2026-09-28T00:00:00+00:00

mkdir -p "$OUT/select" "$OUT/designated" "$OUT/chain" || exit 2
cd "$REPO" || exit 2

stamp() { date -u +%FT%TZ; }
record() {
  echo "$1" >> "$STATUS"
  echo "=== $1" | tee -a "$LOG"
}
sha_of() { sha256sum "$1" | cut -d' ' -f1; }

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
  a=$(sha_of "$f")
  b=$(sha_of "$SERVICE/$f")
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
record "pilot_sha256=$(sha_of "$0")"
record "start=$(stamp)"

# --- 1. alembic current, avant (depuis l'arbre du service) ------------------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) 2>&1 | tee -a "$OUT/alembic_before.txt" "$LOG"
rc_ab=${PIPESTATUS[0]}
record "alembic_before=$rc_ab"

# --- 2. désignation : la règle recalculée depuis le seul manifeste, comparée à la valeur déclarée -----------------
DES=$(env PYTHONPATH="$REPO/src" "$PY" - "$MANIFEST" 2>>"$LOG" <<'PYEOF'
import sys
sys.path[:0] = ["scripts/audit", "scripts"]
import c3_common as cc
manifest = cc.load_manifest(cc.read_json(sys.argv[1]))
ids = sorted(c.identity for c in manifest.candidates if c.pair in ("BTC/USDT", "ETH/USDT"))
print(ids[0])
PYEOF
)
if [ "$DES" != "$DESIGNATED" ]; then
  record "designation=REFUSED computed=$DES declared=$DESIGNATED"
  record "end=$(stamp)"
  exit 2
fi
record "designation=0 identity=$DES"

# --- 3. chemin sélection, deux exécutions — fichiers seulement ---------------------------------------------------
declare -a rc_sel
for i in 1 2; do
  env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3b_evaluate.py --manifest "$MANIFEST" --anchor "$ANCHOR" \
    --selection "$SELECTION" --output-dir "$OUT/select/run$i" --now "$NOW" > "$OUT/select/run$i.log" 2>&1
  rc=$?
  rc_sel[$i]=$rc
  if [ "$rc" -eq 2 ]; then
    if grep -q "nothing_to_evaluate" "$OUT/select/run$i.log"; then event=nothing_to_evaluate; else event=other_refusal; fi
  elif [ "$rc" -eq 0 ]; then
    event=evaluated
  else
    event=control_failed
  fi
  record "eval_select_run$i=$rc event=$event at=$(stamp)"
done
sel_ok=1
if [ "${rc_sel[1]}" -eq "${rc_sel[2]}" ]; then
  if [ "${rc_sel[1]}" -eq 0 ]; then
    if [ "$(sha_of "$OUT/select/run1/evaluation_run.json")" = "$(sha_of "$OUT/select/run2/evaluation_run.json")" ]; then
      record "select_sha_equal=0"
      sel_ok=0
    else
      record "select_sha_equal=1"
    fi
  elif [ "${rc_sel[1]}" -eq 2 ] && grep -q "nothing_to_evaluate" "$OUT/select/run1.log" \
    && grep -q "nothing_to_evaluate" "$OUT/select/run2.log" \
    && [ ! -e "$OUT/select/run1/evaluation_run.json" ] && [ ! -e "$OUT/select/run2/evaluation_run.json" ]; then
    record "select_sha_equal=NA nothing_written"
    sel_ok=0
  else
    record "select_sha_equal=NA unexpected"
  fi
else
  record "select_sha_equal=NA codes_differ"
fi

# --- 4. chemin désigné, deux exécutions --------------------------------------------------------------------------
declare -a rc_des
for i in 1 2; do
  env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3b_evaluate.py --manifest "$MANIFEST" --anchor "$ANCHOR" \
    --candidate "$DESIGNATED" --output-dir "$OUT/designated/run$i" --now "$NOW" 2>&1 \
    | tee -a "$OUT/designated/run$i.log" "$LOG"
  rc_des[$i]=${PIPESTATUS[0]}
  record "eval_designated_run$i=${rc_des[$i]} at=$(stamp)"
done
des_same=1
if [ -f "$OUT/designated/run1/evaluation_run.json" ] && [ -f "$OUT/designated/run2/evaluation_run.json" ]; then
  s1=$(sha_of "$OUT/designated/run1/evaluation_run.json")
  s2=$(sha_of "$OUT/designated/run2/evaluation_run.json")
  record "sha_evaluation_run run1=$s1 run2=$s2"
  [ "$s1" = "$s2" ] && des_same=0
fi
record "designated_sha_equal=$des_same"

# --- 5. alembic current, après — toujours ------------------------------------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) 2>&1 | tee -a "$OUT/alembic_after.txt" "$LOG"
rc_aa=${PIPESTATUS[0]}
record "alembic_after=$rc_aa"

# --- 6-9. chaîne sur la sortie désignée ---------------------------------------------------------------------------
EVAL=$OUT/designated/run1/evaluation_run.json
if [ ! -f "$EVAL" ]; then
  record "chain=SKIPPED designated_run1_sans_sortie"
  record "end=$(stamp)"
  exit 1
fi

env PYTHONPATH="$REPO/src" "$PY" - "$EVAL" <<'PYEOF' 2>&1 | tee -a "$OUT/chain/admission.log" "$LOG"
import sys
sys.path[:0] = ["scripts/audit", "scripts"]
import c3_common as cc
synthetic = cc.evaluation_admission(cc.read_json(sys.argv[1]))
print(f"evaluation_admission -> {synthetic!r} (False : évaluation réelle, admise)")
sys.exit(0 if synthetic is False else 1)
PYEOF
rc_ad=${PIPESTATUS[0]}
record "admission=$rc_ad"

env PYTHONPATH="$REPO/src" "$PY" - "$MANIFEST" "$EVAL" "$OUT/chain/benchmark_eval_synth.json" <<'PYEOF' 2>&1 | tee -a "$LOG"
import sys
sys.path[:0] = ["scripts/audit", "scripts"]
import c3_common as cc
manifest = cc.load_manifest(cc.read_json(sys.argv[1]))
run = cc.read_json(sys.argv[2])
payload = {
    "pair": run["pair"],
    "window": {"start": manifest.anchor().isoformat(), "end": manifest.window_end.isoformat()},
    "comparable": True,
    "comparability": {name: True for name in cc.COMPARABILITY_TESTS},
}
print("benchmark_eval synthétique", cc.write_json(sys.argv[3], payload))
PYEOF
rc_be=${PIPESTATUS[0]}
record "benchmark_eval_synth=$rc_be"

env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3_continuity.py --manifest "$MANIFEST" --anchor "$ANCHOR" \
  --evaluation "$EVAL" --benchmark-eval "$OUT/chain/benchmark_eval_synth.json" \
  --output "$OUT/chain/continuity.json" --now "$NOW" 2>&1 | tee -a "$OUT/chain/continuity.log" "$LOG"
rc_co=${PIPESTATUS[0]}
record "c3_continuity=$rc_co"

env PYTHONPATH="$REPO/src" "$PY" - "$OUT/chain/continuity.json" <<'PYEOF' 2>&1 | tee -a "$LOG"
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
states = {key: clause["state"] for key, clause in report["clauses"].items()}
print(f"clauses {states} stamp_cell {report['stamp_cell']['state']} comparator {report['comparator']['state']} state {report['state']}")
sys.exit(0 if all(states[k] == "DECLARED" for k in ("c1", "c2", "c5")) else 1)
PYEOF
rc_cd=${PIPESTATUS[0]}
record "continuity_declared=$rc_cd"

env PYTHONPATH="$REPO/src" "$PY" - "$OUT/designated/run1/evaluation_run_provenance.json" "$REPO" <<'PYEOF' 2>&1 | tee -a "$LOG"
import json, sys
run = json.load(open(sys.argv[1], encoding="utf-8"))
repo = sys.argv[2]
kb = run["interpreter"]["krakenbot"]
print(f"provenance interpreter={run['interpreter']['executable']} krakenbot={kb} env={run['environment']}")
sys.exit(0 if kb == f"{repo}/src/krakenbot/__init__.py" else 1)
PYEOF
rc_kb=${PIPESTATUS[0]}
record "interpreter_check=$rc_kb"
record "end=$(stamp)"

if [ "$rc_ab" -eq 0 ] && [ "$sel_ok" -eq 0 ] && [ "${rc_des[1]}" -eq 0 ] && [ "${rc_des[2]}" -eq 0 ] \
  && [ "$des_same" -eq 0 ] && [ "$rc_aa" -eq 0 ] && [ "$rc_ad" -eq 0 ] && [ "$rc_be" -eq 0 ] \
  && [ "$rc_co" -eq 0 ] && [ "$rc_cd" -eq 0 ] && [ "$rc_kb" -eq 0 ]; then
  exit 0
fi
exit 1
