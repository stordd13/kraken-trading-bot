#!/bin/bash
# C3b lot 4b — pilote serveur du run de conformité : producteur d'évaluation complet (chemin sélection), puis chaîne C3
# complète (agent/AGENT_C3B_PRODUCTEUR.md § Lot 4b, plan validé le 2026-09-28, GO avec A1-A4), versionné avec ses
# preuves. Attendu déclaré avant lancement : ../ATTENDU.md.
#
# Ordre : gardes (SHA, arbre, environnement unique, archive du lot 3 et candles.json extrait, registre copié) ->
# alembic current -> producteur x2 (chemin sélection) -> égalités au bit -> alembic current -> c3_verdict.py chain ->
# extraction des booléens -> interpréteur.
#  - Règles des lots 3 et 4a : pas de `set -e` (chaque code capturé dans status.txt, on continue) ; second
#    `alembic current` toujours ; un seul environnement (venv du service, `env PYTHONPATH="$REPO/src"` sur chaque
#    invocation Python, jamais sur alembic) ; `pilot_sha256` consigné après `guard=0` ; pas de kill.
#  - Non-lecture (décision 2 du 28/09 ; leçon du 4a) : les sorties du producteur et de la chaîne, et leurs journaux,
#    vont **en fichiers seulement** — ni tee, ni écran, ni listing, ni taille, ni sha. Remontent : les codes, le nom
#    d'événement du producteur (liste close `EVENTS`), et des booléens et comptes extraits par heredoc, qui n'impriment
#    ni identité, ni paire, ni métrique, ni issue.
#  - `--campaign C3B_LOT4B` : étiquette d'instrument (A2) ; la dette 21 (`--campaign`) reste intacte.
#  - Codes du pilote : 2 = garde refusée ; 1 = au moins une étape hors attendu ; 0 = tout l'attendu tenu.
set -o pipefail
set -u
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export NO_COLOR=1

EXPECTED=459190a222bb24aface23c46d80b2d879795a49c
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
RUN=/home/bruno/runs/c3b_eval4b
REPO=$RUN/repo
OUT=$RUN/out
STATUS=$OUT/status.txt
LOG=$OUT/run.log
LOT3_ARCHIVE=/home/bruno/archive/c3b_lot3_20260928/c3b_lot3_server_20260928.tgz
LOT3_ARCHIVE_SHA=80b5f2b9099061cbfc4eeea83ead5c60ea8cec4d7e1403cacccab1fc0632cee8
CANDLES_SHA=20c0d1fb46184f18b186499fea906d1f70b6fcd3c300d4b82ce4f8d2f3139376
REGISTRY_SHA=7c5b80656a17fbc958193a37ec54db3a63ec575d48393c1767a95595d5185b4c
P=results/c3b_producteur/prefix_conformite
MANIFEST=$P/manifest.json
ANCHOR=$P/server/chain/anchor.json
SELECTION=$P/server/chain/selection.json
BENCHMARK=$P/server/chain/benchmark.json
OBSERVATIONS=$P/server/run1/observations.json
COVERAGE=$P/server/run1/coverage.json
REGISTRY_SRC=$P/server/chain/variants.json
CAMPAIGN=C3B_LOT4B
NOW=2026-09-28T00:00:00+00:00
# Les événements d'erreur de c3b_evaluate.py (refus et contrôles), liste close : seul un nom de cette liste est
# consigné ; tout autre texte du journal reste en fichier.
EVENTS="invalid_now manifest_unreadable manifest_refused campaign_window_locked designation_on_campaign_window
invalid_params decision_timeframes_refused fee_model_refused pair_costs_refused anchor_unreadable
anchor_inputs_mismatch anchor_mismatch anchor_refused selection_unreadable selection_inputs_mismatch
selection_inconsistent selection_refused nothing_to_evaluate candidate_not_in_universe replay_inputs
benchmark_unreadable benchmark_inputs_mismatch benchmark_refused benchmark_inconsistent lambda_not_estimable
lambda_domain f2_invalid_input selection_benchmark_mismatch uncommitted_tree output_dir_not_empty database_url_missing
database_read_failed candles comparator_not_buildable comparator flat_start_proof first_fill_at evaluation_controls
engine_failed liquidation_rename liquidation_lots series_length evaluation_assembly evaluation_failed writer_refused"

mkdir -p "$OUT/lot3" "$OUT/chain" || exit 2
cd "$REPO" || exit 2

stamp() { date -u +%FT%TZ; }
record() {
  echo "$1" >> "$STATUS"
  echo "=== $1" >> "$LOG"
}
sha_of() { sha256sum "$1" | cut -d' ' -f1; }
# Le dernier événement d'erreur du producteur présent dans la liste close, sinon `hors_liste`.
event_of() {
  local found="hors_liste" name e
  while read -r name; do
    for e in $EVENTS; do
      if [ "$name" = "$e" ]; then found=$e; fi
    done
  done < <(grep -oE '\[error +\] [a-z0-9_]+' "$1" | awk '{print $NF}')
  echo "$found"
}
# 0 si le fichier existe dans run1 et run2 et y est identique octet pour octet, 1 sinon ; rien d'autre n'est lu.
same() {
  if [ -f "$OUT/run1/$1" ] && [ -f "$OUT/run2/$1" ] && cmp -s "$OUT/run1/$1" "$OUT/run2/$1"; then
    echo 0
  else
    echo 1
  fi
}

# --- Gardes : HEAD attendu, arbre suivi propre, environnement unique, entrées du lot 3 -----------------------------
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
if [ "$(sha_of "$LOT3_ARCHIVE")" != "$LOT3_ARCHIVE_SHA" ]; then
  record "guard=REFUSED lot3_archive_sha"
  exit 2
fi
# Dans l'archive du lot 3, le fichier est `out/run1/candles.json` (vérifié le 28/09) : extrait en `out/lot3/run1/`.
if ! tar -xzf "$LOT3_ARCHIVE" -C "$OUT/lot3" --strip-components=1 out/run1/candles.json \
  || [ "$(sha_of "$OUT/lot3/run1/candles.json")" != "$CANDLES_SHA" ]; then
  record "guard=REFUSED lot3_candles"
  exit 2
fi
cp "$REGISTRY_SRC" "$OUT/chain/variants.json" || exit 2
if [ "$(sha_of "$OUT/chain/variants.json")" != "$REGISTRY_SHA" ]; then
  record "guard=REFUSED registry_sha"
  exit 2
fi
record "guard=0 sha=$SHA python=$("$PY" -V 2>&1) krakenbot=$KB lot3_candles=0 registry=0"
record "pilot_sha256=$(sha_of "$0")"
record "start=$(stamp)"

# --- 1. alembic current, avant (depuis l'arbre du service) ----------------------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_before.txt" 2>&1
rc_ab=$?
record "alembic_before=$rc_ab"

# --- 2. producteur, chemin sélection, deux exécutions — fichiers seulement ------------------------------------------
declare -a rc_ev
for i in 1 2; do
  env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3b_evaluate.py --manifest "$MANIFEST" --anchor "$ANCHOR" \
    --selection "$SELECTION" --benchmark "$BENCHMARK" --output-dir "$OUT/run$i" --now "$NOW" \
    > "$OUT/run$i.log" 2>&1
  rc=$?
  rc_ev[$i]=$rc
  if [ "$rc" -eq 0 ] && grep -qE '\[info +\] evaluated ' "$OUT/run$i.log"; then
    event=evaluated
  else
    event=$(event_of "$OUT/run$i.log")
  fi
  record "eval_run$i=$rc event=$event at=$(stamp)"
done

# --- 3. égalités au bit, booléens seulement -------------------------------------------------------------------------
eval_eq=$(same evaluation.json)
record "eval_bit_equal=$eval_eq"
out_eq=0
for f in benchmark_eval.json candles_eval.json evaluation_sensitivity.json; do
  if [ "$(same "$f")" != 0 ]; then out_eq=1; fi
done
record "outputs_bit_equal=$out_eq"

# --- 4. alembic current, après — toujours ---------------------------------------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_after.txt" 2>&1
rc_aa=$?
record "alembic_after=$rc_aa"

# --- 5. chaîne complète sur run1 — fichiers seulement ---------------------------------------------------------------
EVAL=$OUT/run1/evaluation.json
BEVAL=$OUT/run1/benchmark_eval.json
if [ ! -f "$EVAL" ] || [ ! -f "$BEVAL" ]; then
  record "chain=SKIPPED run1_sans_sortie"
  record "end=$(stamp)"
  exit 1
fi
env PYTHONPATH="$REPO/src" "$PY" scripts/audit/c3_verdict.py chain --manifest "$MANIFEST" \
  --observations "$OBSERVATIONS" --coverage "$COVERAGE" --candles "$OUT/lot3/run1/candles.json" \
  --evaluation "$EVAL" --benchmark-eval "$BEVAL" --registry "$OUT/chain/variants.json" \
  --out-dir "$OUT/chain" --campaign "$CAMPAIGN" --now "$NOW" > "$OUT/chain.log" 2>&1
rc_chain=$?
record "chain_exit=$rc_chain"

# --- 6. extraction : chain.verified, violations, violations au rejeu, étapes — rien d'autre -------------------------
EXTRACT=$(env PYTHONPATH="$REPO/src" "$PY" - "$OUT/chain/verdict.json" "$OUT/chain.log" 2>> "$OUT/extract.err" <<'PYEOF'
import json
import re
import sys

path, log = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as handle:
        verdict = json.load(handle)
except FileNotFoundError:
    with open(log, encoding="utf-8") as handle:
        stop = re.search(r"CHAINE ARRETEE à l'étape (\w+)(?: \(code de retour (\d+)\))?", handle.read())
    print("verdict_json=absent")
    print(f"chain_stopped={stop.group(1)}:{stop.group(2) or 'NA'}" if stop else "chain_stopped=inconnu")
    sys.exit(0)
violations = verdict["violations"]
chain = verdict["chain"]
print(f"chain_verified={'true' if chain['verified'] is True else 'false'}")
print(f"verdict_violations={len(violations)}")
print(f"replay_violations={sum(1 for v in violations if v.startswith(('rejeu', 'réplications')))}")
print("chain_steps=" + ",".join(f"{step['name']}:{step['exit_code']}" for step in chain["steps"]))
PYEOF
)
rc_ex=$?
while IFS= read -r line; do
  if [ -n "$line" ]; then record "$line"; fi
done <<< "$EXTRACT"
record "extract=$rc_ex"

# --- 7. interpréteur de la provenance : booléen seulement -----------------------------------------------------------
env PYTHONPATH="$REPO/src" "$PY" - "$OUT/run1/evaluation_run_provenance.json" "$REPO" >> "$OUT/extract.err" 2>&1 <<'PYEOF'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    run = json.load(handle)
sys.exit(0 if run["interpreter"]["krakenbot"] == f"{sys.argv[2]}/src/krakenbot/__init__.py" else 1)
PYEOF
rc_kb=$?
record "interpreter_check=$rc_kb"
record "end=$(stamp)"

steps_ok=1
if echo "$EXTRACT" | grep -qx "chain_steps=anchor:0,entry:0,benchmark:0,select:0,continuity:0"; then steps_ok=0; fi
if [ "$rc_ab" -eq 0 ] && [ "${rc_ev[1]}" -eq 0 ] && [ "${rc_ev[2]}" -eq 0 ] && [ "$eval_eq" -eq 0 ] \
  && [ "$out_eq" -eq 0 ] && [ "$rc_aa" -eq 0 ] && [ "$rc_chain" -eq 0 ] && [ "$rc_ex" -eq 0 ] \
  && [ "$steps_ok" -eq 0 ] && [ "$rc_kb" -eq 0 ] \
  && echo "$EXTRACT" | grep -qx "chain_verified=true" \
  && echo "$EXTRACT" | grep -qx "verdict_violations=0" \
  && echo "$EXTRACT" | grep -qx "replay_violations=0"; then
  exit 0
fi
exit 1
