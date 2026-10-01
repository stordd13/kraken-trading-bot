#!/bin/bash
# C3 racine du registre, lot 2 (repris de l'outillage v2.3, lot 2) — pilote serveur de la conformité sous v2.3, au code
# du chantier (plans/lot2.md L1-L6 ; attendu déclaré avant le lancement : ../attendu.md). Versionné au commit S1 et
# exécuté DEPUIS LE CLONE à ce SHA (D1) :
#   bash ~/runs/c3_racine_registre/conf/repo/results/c3_racine_registre/conformite/server/run_conformite.sh <S1, 40 hex>
#
# Ordre : gardes -> pilot_sha256 -> service et alembic avant -> trois exécutions K = 1, 2, 3 (workers 4 / 1 / 4, D4),
# chacune au MÊME chemin absolu $RUN/work (K3 : anchor.json et entry.json embarquent les chemins de leurs entrées),
# renommée out/run<K> ensuite :
#   c3b_prefix -> c3_anchor, c3_entry, c3_benchmark, c3_select (autonomes, registre neuf work/pre/variants.json)
#   -> c3b_evaluate --selection -> copie du registre dans work/chain/ -> c3_verdict.py chain (neuf entrées)
#   -> extraction de booléens par heredoc -> interpréteur des deux provenances -> mv
# -> comparaison au bit des 23 artefacts sur les trois exécutions -> alembic après (toujours) -> service, arbre du
# clone, CAMPAIGN_UNLOCK.
#  - Règles serveur (skills/deployment.md, précédents C3b) : pas de `set -e` (chaque code capturé dans status.txt, on
#    continue) ; second `alembic current` toujours ; un seul environnement (venv du service, `env PYTHONPATH="$REPO/src"`
#    sur chaque invocation Python, jamais sur alembic, lancé depuis l'arbre du service) ; `pilot_sha256` consigné
#    après `guard=0` ; pas de kill ; base en lecture seule assertée par le producteur lui-même (`probe_database`).
#  - Non-lecture (issue non lue ; D3) : les sorties des producteurs et de la chaîne, et leurs journaux, vont EN
#    FICHIERS SEULEMENT — ni tee, ni écran, ni listing, ni taille, ni sha. Remontent : des codes, un nom d'événement
#    tiré de la liste close EVENTS (prouvée égale au code par tests/events.sh), et des booléens extraits par heredoc,
#    qui n'impriment ni identité, ni paire, ni métrique, ni λ, ni issue, ni raison, ni motif.
#  - Les trois exécutions tournent même après un échec ; dans une exécution, une étape dont une entrée manque est
#    SKIPPED, les suivantes sont tentées. Le STOP vient après, sur l'attendu.
#  - Codes du pilote : 2 = garde refusée ; 1 = au moins un fait hors attendu ; 0 = tout l'attendu tenu.
set -o pipefail
set -u
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export NO_COLOR=1

EXPECTED=${1:-}
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
RUN=/home/bruno/runs/c3_racine_registre/conf
REPO=$RUN/repo
OUT=$RUN/out
WORK=$RUN/work
STATUS=$OUT/status.txt
LOG=$OUT/run.log
SELF=results/c3_racine_registre/conformite/server/run_conformite.sh
MANIFEST=results/c3_racine_registre/conformite/manifest.json
MANIFEST_SHA=9966efade2729f5da6652b0ffa8feda9b127840a77d9a47660823a1e9c50a24b
PROTOCOL_SHA=d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6
UNLOCK=results/c3b_producteur/CAMPAIGN_UNLOCK
CAMPAIGN=RACINE_REGISTRE_CONF
NOW=2026-10-01T00:00:00+00:00
HEAD_LINE="c3bd1e7a0001 (head)"
WORKERS=(- 4 1 4)
STEPS_OK="anchor:0,entry:0,benchmark:0,select:0,continuity:0"
# Événements d'erreur des producteurs, liste close (tests/events.sh la prouve égale au code à S1).
EVENTS="anchor_inputs_mismatch anchor_mismatch anchor_refused anchor_unreadable benchmark_inconsistent benchmark_inputs_mismatch benchmark_refused benchmark_unreadable campaign_window_locked candidate_not_in_universe candles comparator comparator_failed coverage_grid coverage_input coverage_prefix_too_short coverage_recompute coverage_units database_read_failed database_url_missing decision_timeframes_refused designation_on_campaign_window engine_failed entry_controls evaluation_assembly evaluation_controls evaluation_failed f2_invalid_input fee_model_refused first_fill_at flat_start_proof invalid_now invalid_params job_failed jobs_failed lambda_domain lambda_not_estimable liquidation_lots liquidation_rename manifest_refused manifest_unreadable nothing_to_evaluate output_dir_not_empty pair_costs_refused partial_mismatch replay_inputs selection_benchmark_mismatch selection_inconsistent selection_inputs_mismatch selection_refused selection_unreadable series_length uncommitted_tree writer_refused"
# Les 23 artefacts comparés au bit entre les trois exécutions (attendu § 4 item 5). Exclus, déclarés (K4) :
# prefix/prefix_run.json, prefix/partial/*, eval/evaluation_run_provenance.json, logs/* (durées, horodatages).
ARTEFACTS=(
  prefix/observations.json prefix/coverage.json prefix/candles.json
  pre/anchor.json pre/variants.json pre/entry.json pre/entry.md pre/benchmark.json pre/selection.json pre/selection.md
  eval/evaluation.json eval/benchmark_eval.json eval/candles_eval.json eval/evaluation_sensitivity.json
  chain/anchor.json chain/entry.json chain/entry.md chain/benchmark.json chain/selection.json chain/selection.md
  chain/continuity.json chain/verdict.json chain/variants.json
)

mkdir -p "$OUT" || exit 2
cd "$REPO" || exit 2

fail=0
stamp() { date -u +%FT%TZ; }
record() {
  echo "$1" >> "$STATUS"
  echo "=== $1" >> "$LOG"
}
expect() {  # expect <valeur> <attendue> : un écart marque le pilote (code 1), rien d'autre
  if [ "$1" != "$2" ]; then fail=1; fi
}
sha_of() { sha256sum "$1" | cut -d' ' -f1; }
pyrun() { env PYTHONPATH="$REPO/src" "$PY" "$@"; }
service() {
  echo "head=$(git -C "$SERVICE" rev-parse HEAD 2>&1) dirty=$(git -C "$SERVICE" status --porcelain \
--untracked-files=no 2>&1 | wc -l | tr -d ' ') collector=$(systemctl is-active krakenbot-collector 2>&1) \
$(systemctl show -p NRestarts krakenbot-collector 2>&1)"
}
# Le dernier événement d'erreur du journal présent dans EVENTS, sinon `hors_liste` ; rien d'autre n'est lu.
event_of() {
  local found="hors_liste" name e
  while read -r name; do
    for e in $EVENTS; do
      if [ "$name" = "$e" ]; then found=$e; fi
    done
  done < <(grep -oE '\[error +\] [a-z0-9_]+' "$1" 2> /dev/null | awk '{print $NF}')
  echo "$found"
}

# --- Gardes ---------------------------------------------------------------------------------------------------------
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
KB=$(pyrun -c 'import krakenbot; print(krakenbot.__file__)' 2>&1)
if [ "$KB" != "$REPO/src/krakenbot/__init__.py" ]; then
  record "guard=REFUSED krakenbot_resolved=$KB"
  exit 2
fi
if [ ! -f "$REPO/.env" ]; then
  record "guard=REFUSED env_file_absent"
  exit 2
fi
if [ "$(sha_of docs/protocole_c3.md)" != "$PROTOCOL_SHA" ]; then
  record "guard=REFUSED protocol_sha"
  exit 2
fi
if [ "$(sha_of "$MANIFEST")" != "$MANIFEST_SHA" ]; then
  record "guard=REFUSED manifest_sha"
  exit 2
fi
if [ -e "$UNLOCK" ]; then
  record "guard=REFUSED campaign_unlock_present"
  exit 2
fi
if [ -e "$WORK" ] || [ -e "$OUT/run1" ] || [ -e "$OUT/run2" ] || [ -e "$OUT/run3" ]; then
  record "guard=REFUSED work_or_runs_present"
  exit 2
fi
record "guard=0 sha=$SHA python=$("$PY" -V 2>&1) krakenbot=$KB protocol=$PROTOCOL_SHA manifest=$MANIFEST_SHA campaign_unlock=absent"
record "pilot_sha256=$(sha_of "$0")"
cp "$0" "$OUT/pilot.sh"
record "pilot_copy=$?"
SERVICE_BEFORE=$(service)
record "service_before=$SERVICE_BEFORE"
record "start=$(stamp)"

# --- alembic current, avant (depuis l'arbre du service, sans PYTHONPATH) ------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_before.txt" 2>&1
rc_ab=$?
record "alembic_before=$rc_ab"
expect "$rc_ab" 0

# --- une exécution ------------------------------------------------------------------------------------------------
# step <clé> <journal> <entrées requises…> -- <arguments python…> : SKIPPED si une entrée manque, sinon le code.
step() {
  local key=$1 journal=$2
  shift 2
  local missing=""
  while [ "$1" != "--" ]; do
    if [ ! -f "$1" ]; then missing=1; fi
    shift
  done
  shift
  if [ -n "$missing" ]; then
    record "$key=SKIPPED entree_absente"
    fail=1
    return
  fi
  pyrun "$@" > "$WORK/logs/$journal" 2>&1
  local r=$?
  record "$key=$r"
  expect "$r" 0
}

execute() {
  local k=$1
  local w=${WORKERS[$1]}
  local P=$WORK/prefix C=$WORK/pre E=$WORK/eval H=$WORK/chain
  record "workers_$k=$w"
  record "start_$k=$(stamp)"
  if ! mkdir "$WORK" 2> /dev/null; then
    record "work_$k=REFUSED present"
    fail=1
    return
  fi
  mkdir -p "$WORK/logs" "$C" "$H"

  # 1. producteur préfixe
  pyrun scripts/audit/c3b_prefix.py --manifest "$MANIFEST" --output-dir "$P" --workers "$w" --now "$NOW" \
    > "$WORK/logs/prefix.log" 2>&1
  local r=$?
  local ev="-"
  if [ "$r" -ne 0 ]; then ev=$(event_of "$WORK/logs/prefix.log"); fi
  record "prefix_$k=$r event=$ev at=$(stamp)"
  expect "$r" 0

  # 2. chaîne 1-4 autonome, registre neuf sous la sortie de l'exécution
  step "pre_anchor_$k" anchor.log "$MANIFEST" -- scripts/audit/c3_anchor.py --manifest "$MANIFEST" \
    --registry "$C/variants.json" --output "$C/anchor.json" --now "$NOW"
  step "pre_entry_$k" entry.log "$C/anchor.json" "$P/observations.json" "$P/coverage.json" -- \
    scripts/audit/c3_entry.py --manifest "$MANIFEST" --anchor "$C/anchor.json" --observations "$P/observations.json" \
    --coverage "$P/coverage.json" --output "$C/entry.json" --markdown "$C/entry.md" --now "$NOW"
  step "pre_benchmark_$k" benchmark.log "$C/anchor.json" "$C/entry.json" "$P/observations.json" "$P/candles.json" -- \
    scripts/audit/c3_benchmark.py --manifest "$MANIFEST" --anchor "$C/anchor.json" --entry "$C/entry.json" \
    --observations "$P/observations.json" --candles "$P/candles.json" --output "$C/benchmark.json" --now "$NOW"
  step "pre_select_$k" select.log "$C/anchor.json" "$C/entry.json" "$P/observations.json" "$P/coverage.json" \
    "$C/benchmark.json" -- scripts/audit/c3_select.py --manifest "$MANIFEST" --anchor "$C/anchor.json" \
    --entry "$C/entry.json" --observations "$P/observations.json" --coverage "$P/coverage.json" \
    --benchmark "$C/benchmark.json" --output "$C/selection.json" --markdown "$C/selection.md" --now "$NOW"

  # 3. producteur d'évaluation, chemin sélection
  if [ -f "$C/anchor.json" ] && [ -f "$C/selection.json" ] && [ -f "$C/benchmark.json" ]; then
    pyrun scripts/audit/c3b_evaluate.py --manifest "$MANIFEST" --anchor "$C/anchor.json" \
      --selection "$C/selection.json" --benchmark "$C/benchmark.json" --output-dir "$E" --now "$NOW" \
      > "$WORK/logs/evaluate.log" 2>&1
    r=$?
    if [ "$r" -eq 0 ] && grep -qE '\[info +\] evaluated ' "$WORK/logs/evaluate.log"; then
      ev=evaluated
    elif [ "$r" -eq 0 ] && grep -qE '\[info +\] refusal_form_written ' "$WORK/logs/evaluate.log"; then
      ev=refusal_form_written
    elif [ "$r" -eq 0 ]; then
      ev=hors_liste
    else
      ev=$(event_of "$WORK/logs/evaluate.log")
    fi
    record "eval_$k=$r event=$ev at=$(stamp)"
    expect "$r" 0
    expect "$ev" evaluated
  else
    record "eval_$k=SKIPPED entree_absente"
    fail=1
  fi

  # 4. chaîne complète : registre de l'exécution copié (idempotent à l'étape 1, inscription à l'étape 6)
  if [ -f "$C/variants.json" ]; then
    cp "$C/variants.json" "$H/variants.json"
    r=$?
  else
    r=1
  fi
  record "registry_copy_$k=$r"
  expect "$r" 0
  local beval=()
  if [ -f "$E/benchmark_eval.json" ]; then beval=(--benchmark-eval "$E/benchmark_eval.json"); fi
  if [ -f "$E/evaluation.json" ] && [ -f "$E/candles_eval.json" ] && [ -f "$H/variants.json" ] \
    && [ -f "$P/observations.json" ] && [ -f "$P/coverage.json" ] && [ -f "$P/candles.json" ]; then
    pyrun scripts/audit/c3_verdict.py chain --manifest "$MANIFEST" --observations "$P/observations.json" \
      --coverage "$P/coverage.json" --candles "$P/candles.json" --evaluation "$E/evaluation.json" \
      ${beval[@]+"${beval[@]}"} --candles-eval "$E/candles_eval.json" --registry "$H/variants.json" --out-dir "$H" \
      --campaign "$CAMPAIGN" --now "$NOW" > "$WORK/logs/chain.log" 2>&1
    r=$?
    record "chain_$k=$r"
    expect "$r" 0
  else
    record "chain_$k=SKIPPED entree_absente"
    fail=1
  fi

  # 5. extraction : chain.verified, violations vides, violations de rejeu vides, étapes — rien d'autre
  local extract
  extract=$(pyrun - "$H/verdict.json" "$WORK/logs/chain.log" 2>> "$OUT/extract.err" <<'PYEOF'
import json
import re
import sys

path, log = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as handle:
        verdict = json.load(handle)
except FileNotFoundError:
    try:
        with open(log, encoding="utf-8") as handle:
            stop = re.search(r"CHAINE ARRETEE à l'étape (\w+)(?: \(code de retour (\d+)\))?", handle.read())
    except FileNotFoundError:
        stop = None
    print("verdict_json=absent")
    print(f"chain_stopped={stop.group(1)}:{stop.group(2) or 'NA'}" if stop else "chain_stopped=inconnu")
    sys.exit(0)
violations = verdict["violations"]
chain = verdict["chain"]
replay = [v for v in violations if str(v).startswith(("rejeu", "réplications"))]
print(f"chain_verified={'true' if chain['verified'] is True else 'false'}")
print(f"violations_empty={'true' if violations == [] else 'false'}")
print(f"replay_violations_empty={'true' if replay == [] else 'false'}")
print("chain_steps=" + ",".join(f"{step['name']}:{step['exit_code']}" for step in chain["steps"]))
PYEOF
  )
  r=$?
  local line
  while IFS= read -r line; do
    if [ -n "$line" ]; then record "${line%%=*}_$k=${line#*=}"; fi
  done <<< "$extract"
  record "extract_$k=$r"
  expect "$r" 0
  echo "$extract" | grep -qx "chain_verified=true" || fail=1
  echo "$extract" | grep -qx "violations_empty=true" || fail=1
  echo "$extract" | grep -qx "replay_violations_empty=true" || fail=1
  echo "$extract" | grep -qx "chain_steps=$STEPS_OK" || fail=1

  # 6. interpréteur des deux provenances : booléen seulement
  pyrun - "$P/prefix_run.json" "$E/evaluation_run_provenance.json" "$REPO" >> "$OUT/extract.err" 2>&1 <<'PYEOF'
import json
import sys

want = f"{sys.argv[3]}/src/krakenbot/__init__.py"
ok = True
for path in sys.argv[1:3]:
    try:
        with open(path, encoding="utf-8") as handle:
            ok = ok and json.load(handle)["interpreter"]["krakenbot"] == want
    except (OSError, KeyError, TypeError, ValueError):
        ok = False
sys.exit(0 if ok else 1)
PYEOF
  r=$?
  record "interpreter_$k=$r"
  expect "$r" 0

  # 7. renommage : l'exécution quitte le chemin commun
  mv "$WORK" "$OUT/run$k"
  r=$?
  record "moved_$k=$r"
  expect "$r" 0
  record "end_$k=$(stamp)"
}

execute 1
execute 2
execute 3

# --- déterminisme : liste attendue et égalité au bit des 23 artefacts, booléens seulement -------------------------
listing() {
  (cd "$1" && find . -type f ! -path './logs/*' ! -path './prefix/partial/*' ! -name prefix_run.json \
    ! -name evaluation_run_provenance.json | sed 's|^\./||' | LC_ALL=C sort)
}
EXPECTED_LIST=$(printf '%s\n' "${ARTEFACTS[@]}" | LC_ALL=C sort)
listing_ok=0
for k in 1 2 3; do
  if [ ! -d "$OUT/run$k" ] || [ "$(listing "$OUT/run$k")" != "$EXPECTED_LIST" ]; then listing_ok=1; fi
done
record "listing_expected_3of3=$listing_ok"
expect "$listing_ok" 0
compared=0
differing=0
absent=0
for a in "${ARTEFACTS[@]}"; do
  if [ -f "$OUT/run1/$a" ] && [ -f "$OUT/run2/$a" ] && [ -f "$OUT/run3/$a" ]; then
    compared=$((compared + 1))
    cmp -s "$OUT/run1/$a" "$OUT/run2/$a"; e12=$?
    cmp -s "$OUT/run1/$a" "$OUT/run3/$a"; e13=$?
    if [ "$e12" -eq 0 ] && [ "$e13" -eq 0 ]; then
      record "eq3 $a=0"
    else
      differing=$((differing + 1))
      record "eq3 $a=1 r12=$e12 r13=$e13"
    fi
  else
    absent=$((absent + 1))
    record "eq3 $a=absent"
  fi
done
if [ "$compared" -eq "${#ARTEFACTS[@]}" ] && [ "$differing" -eq 0 ] && [ "$absent" -eq 0 ]; then bit=0; else bit=1; fi
record "bit_equal_3of3=$bit compared=$compared differing=$differing absent=$absent"
expect "$bit" 0

# --- alembic après (toujours), service, arbre du clone, CAMPAIGN_UNLOCK --------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_after.txt" 2>&1
rc_aa=$?
record "alembic_after=$rc_aa"
expect "$rc_aa" 0
if cmp -s "$OUT/alembic_before.txt" "$OUT/alembic_after.txt" && grep -qF "$HEAD_LINE" "$OUT/alembic_after.txt"; then
  alembic_same=0
else
  alembic_same=1
fi
record "alembic_same_head=$alembic_same"
expect "$alembic_same" 0
SERVICE_AFTER=$(service)
record "service_after=$SERVICE_AFTER"
expect "$SERVICE_AFTER" "$SERVICE_BEFORE"
if [ -z "$(git status --porcelain --untracked-files=no)" ]; then tree_after=0; else tree_after=1; fi
record "tree_after=$tree_after"
expect "$tree_after" 0
if [ -e "$UNLOCK" ]; then unlock_after=present; else unlock_after=absent; fi
record "campaign_unlock_after=$unlock_after"
expect "$unlock_after" absent
record "end=$(stamp)"

exit "$fail"
