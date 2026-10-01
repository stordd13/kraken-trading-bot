#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 (repris de results/c3_racine_registre/conformite/server/
# run_conformite.sh) — pilote serveur du run compté, au code de S1 (plans/plan.md § 1 ; attendu déclaré avant le
# lancement : ../attendu.md). Versionné au commit S1 et exécuté DEPUIS LE CLONE à ce SHA :
#   bash ~/runs/c3_campagne_grid/campagne/repo/results/c3_campagne_grid/server/run_campagne.sh <S1, 40 hex>
#
# Ordre : gardes -> pilot_sha256 -> service et alembic avant -> UNE exécution, arrêtée au premier écart :
#   c3b_prefix -> c3_anchor (première inscription au registre de campagne), c3_entry, c3_benchmark, c3_select
#   (autonomes) -> c3b_evaluate --selection -> c3_verdict.py chain (même registre) -> extraction par heredoc
#   -> interpréteur des deux provenances -> alembic après (toujours) -> service, arbre du clone, CAMPAIGN_UNLOCK.
#  - Règles serveur (skills/deployment.md, précédents C3b) : pas de `set -e` (chaque code consigné dans status.txt) ;
#    second `alembic current` toujours ; un seul environnement (venv du service, `env PYTHONPATH="$REPO/src"` sur
#    chaque invocation Python, jamais sur alembic, lancé depuis l'arbre du service) ; `pilot_sha256` consigné après
#    `guard=0` ; pas de kill ; base en lecture seule assertée par le producteur lui-même (`probe_database`).
#  - Registre de campagne (runbook skills/registry.md) : nommé sur les deux seules lignes `--registry` (ancrage
#    autonome, chaîne) ; ce pilote ne le lit, ne le copie, ne le liste ni ne le teste jamais.
#  - Arrêt au premier écart (plan § 1) : une étape ne tourne que si toutes les précédentes ont rendu leur attendu ;
#    sinon `<clé>=NOT_RUN`, et `halted_at` nomme le premier écart. Aucune écriture au registre ne suit un écart. Les
#    contrôles « après » (alembic, service, arbre du clone, CAMPAIGN_UNLOCK) sont inconditionnels.
#  - Non-lecture : sorties et journaux EN FICHIERS SEULEMENT — ni tee, ni écran, ni listing, ni taille, ni sha.
#    Remontent (plan § 2) : des codes, un nom d'événement de la liste close EVENTS (prouvée égale au code par
#    tests/events.sh), des booléens, et l'issue et la raison tirées de la chaîne § L.2 que `c3_verdict chain` publie
#    sur stdout, validées contre leurs listes closes. Aucun autre champ de la chaîne, aucune identité, aucune métrique.
#  - Codes du pilote : 2 = garde refusée ; 1 = au moins un fait hors attendu ; 0 = tout l'attendu tenu.
set -o pipefail
set -u
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export NO_COLOR=1

EXPECTED=${1:-}
SERVICE=/home/bruno/apps/kraken-trading-bot
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
RUN=/home/bruno/runs/c3_campagne_grid/campagne
REPO=$RUN/repo
OUT=$RUN/out
STATUS=$OUT/status.txt
LOG=$OUT/run.log
SELF=results/c3_campagne_grid/server/run_campagne.sh
MANIFEST=results/c3_campagne_grid/manifest.json
MANIFEST_SHA=d422076b09292d8aeb2a6ae3f39b9c37325f23e954c05c6c83a8979255325041
PROTOCOL_SHA=d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6
UNLOCK=results/c3b_producteur/CAMPAIGN_UNLOCK
CAMPAIGN=GRID_ATR_V4_2026
NOW=2026-10-01T00:00:00+00:00
WORKERS=3
HEAD_LINE="c3bd1e7a0001 (head)"
# A1 : cinq codes d'étape (c3_verdict.CHAIN_FILES) ; le code de la chaîne elle-même est celui que rend le verdict.
STEPS_OK="anchor:0,entry:0,benchmark:0,select:0,continuity:0"
# Événements d'erreur des producteurs, liste close (tests/events.sh la prouve égale au code à S1).
EVENTS="anchor_inputs_mismatch anchor_mismatch anchor_refused anchor_unreadable benchmark_inconsistent benchmark_inputs_mismatch benchmark_refused benchmark_unreadable campaign_window_locked candidate_not_in_universe candles comparator comparator_failed coverage_grid coverage_input coverage_prefix_too_short coverage_recompute coverage_units database_read_failed database_url_missing decision_timeframes_refused designation_on_campaign_window engine_failed entry_controls evaluation_assembly evaluation_controls evaluation_failed f2_invalid_input fee_model_refused first_fill_at flat_start_proof invalid_now invalid_params job_failed jobs_failed lambda_domain lambda_not_estimable liquidation_lots liquidation_rename manifest_refused manifest_unreadable nothing_to_evaluate output_dir_not_empty pair_costs_refused partial_mismatch replay_inputs selection_benchmark_mismatch selection_inconsistent selection_inputs_mismatch selection_refused selection_unreadable series_length uncommitted_tree writer_refused"

mkdir -p "$OUT" || exit 2
cd "$REPO" || exit 2

fail=0
halted=""
stamp() { date -u +%FT%TZ; }
record() {
  echo "$1" >> "$STATUS"
  echo "=== $1" >> "$LOG"
}
go() { [ -z "$halted" ]; }
deviate() {  # deviate <étape> : un fait hors attendu ; le premier arrête les étapes suivantes
  fail=1
  if [ -z "$halted" ]; then halted=$1; fi
}
expect() {  # expect <valeur> <attendue> : contrôle inconditionnel ; un écart marque le pilote (code 1), rien d'autre
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
# Le booléen registry.new_entry d'un anchor.json, rien d'autre.
new_entry() {
  pyrun - "$1" 2>> "$OUT/extract.err" <<'PYEOF'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = json.load(handle)["registry"]["new_entry"]
except (OSError, KeyError, TypeError, ValueError):
    value = None
print("true" if value is True else "false" if value is False else "absent")
PYEOF
}
# step <clé> <journal> -- <arguments python…> : NOT_RUN après un écart, sinon le code (attendu 0).
step() {
  local key=$1 journal=$2
  shift 3
  if ! go; then
    record "$key=NOT_RUN"
    return
  fi
  pyrun "$@" > "$OUT/logs/$journal" 2>&1
  local r=$?
  record "$key=$r"
  [ "$r" = "0" ] || deviate "$key"
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
    record "guard=REFUSED env_mismatch file=$f"
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
# Garde-fou 6 levé par Bruno : CAMPAIGN_UNLOCK, créé par lui dans l'arbre du service, transporté ici par launch.sh.
if [ ! -f "$UNLOCK" ]; then
  record "guard=REFUSED campaign_unlock_absent"
  exit 2
fi
for d in prefix pre eval chain logs; do
  if [ -e "$OUT/$d" ]; then
    record "guard=REFUSED sorties_presentes"
    exit 2
  fi
done
record "guard=0 sha=$SHA python=$("$PY" -V 2>&1) krakenbot=$KB protocol=$PROTOCOL_SHA manifest=$MANIFEST_SHA campaign_unlock=present"
record "pilot_sha256=$(sha_of "$0")"
cp "$0" "$OUT/pilot.sh"
r=$?
record "pilot_copy=$r"
expect "$r" 0
SERVICE_BEFORE=$(service)
record "service_before=$SERVICE_BEFORE"
record "start=$(stamp)"

# --- alembic current, avant (depuis l'arbre du service, sans PYTHONPATH) ------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_before.txt" 2>&1
r=$?
record "alembic_before=$r"
[ "$r" = "0" ] || deviate alembic_before
mkdir -p "$OUT/logs" "$OUT/pre" "$OUT/chain"
record "workers=$WORKERS"

# --- 1. producteur préfixe ------------------------------------------------------------------------------------------
if go; then
  pyrun scripts/audit/c3b_prefix.py --manifest "$MANIFEST" --output-dir "$OUT/prefix" --workers "$WORKERS" \
    --now "$NOW" > "$OUT/logs/prefix.log" 2>&1
  r=$?
  ev="-"
  if [ "$r" -ne 0 ]; then ev=$(event_of "$OUT/logs/prefix.log"); fi
  record "prefix=$r event=$ev at=$(stamp)"
  [ "$r" = "0" ] || deviate prefix
else
  record "prefix=NOT_RUN"
fi

# --- 2. chaîne 1-4 autonome ; l'ancrage fait la première inscription au registre de campagne -------------------------
step pre_anchor anchor.log -- scripts/audit/c3_anchor.py --manifest "$MANIFEST" \
  --registry /home/bruno/c3/registry/variants.json --output "$OUT/pre/anchor.json" --now "$NOW"
if go; then
  ne=$(new_entry "$OUT/pre/anchor.json")
  record "registry_new_entry_pre=$ne"
  [ "$ne" = "true" ] || deviate registry_new_entry_pre
else
  record "registry_new_entry_pre=NOT_RUN"
fi
step pre_entry entry.log -- scripts/audit/c3_entry.py --manifest "$MANIFEST" --anchor "$OUT/pre/anchor.json" \
  --observations "$OUT/prefix/observations.json" --coverage "$OUT/prefix/coverage.json" \
  --output "$OUT/pre/entry.json" --markdown "$OUT/pre/entry.md" --now "$NOW"
step pre_benchmark benchmark.log -- scripts/audit/c3_benchmark.py --manifest "$MANIFEST" \
  --anchor "$OUT/pre/anchor.json" --entry "$OUT/pre/entry.json" --observations "$OUT/prefix/observations.json" \
  --candles "$OUT/prefix/candles.json" --output "$OUT/pre/benchmark.json" --now "$NOW"
step pre_select select.log -- scripts/audit/c3_select.py --manifest "$MANIFEST" --anchor "$OUT/pre/anchor.json" \
  --entry "$OUT/pre/entry.json" --observations "$OUT/prefix/observations.json" \
  --coverage "$OUT/prefix/coverage.json" --benchmark "$OUT/pre/benchmark.json" \
  --output "$OUT/pre/selection.json" --markdown "$OUT/pre/selection.md" --now "$NOW"

# --- 3. producteur d'évaluation, chemin sélection -------------------------------------------------------------------
if go; then
  pyrun scripts/audit/c3b_evaluate.py --manifest "$MANIFEST" --anchor "$OUT/pre/anchor.json" \
    --selection "$OUT/pre/selection.json" --benchmark "$OUT/pre/benchmark.json" --output-dir "$OUT/eval" \
    --now "$NOW" > "$OUT/logs/evaluate.log" 2>&1
  r=$?
  if [ "$r" -eq 0 ] && grep -qE '\[info +\] evaluated ' "$OUT/logs/evaluate.log"; then
    ev=evaluated
  elif [ "$r" -eq 0 ] && grep -qE '\[info +\] refusal_form_written ' "$OUT/logs/evaluate.log"; then
    ev=refusal_form_written
  elif [ "$r" -eq 0 ]; then
    ev=hors_liste
  else
    ev=$(event_of "$OUT/logs/evaluate.log")
  fi
  record "eval=$r event=$ev at=$(stamp)"
  { [ "$r" = "0" ] && [ "$ev" = "evaluated" ]; } || deviate eval
else
  record "eval=NOT_RUN"
fi

# --- 4. chaîne complète, sur le même registre (étape 1 idempotente, inscription de l'issue à l'étape 6) -------------
chain_ran=0
if go; then
  pyrun scripts/audit/c3_verdict.py chain --manifest "$MANIFEST" --observations "$OUT/prefix/observations.json" \
    --coverage "$OUT/prefix/coverage.json" --candles "$OUT/prefix/candles.json" \
    --evaluation "$OUT/eval/evaluation.json" --benchmark-eval "$OUT/eval/benchmark_eval.json" \
    --candles-eval "$OUT/eval/candles_eval.json" \
    --registry /home/bruno/c3/registry/variants.json --out-dir "$OUT/chain" --campaign "$CAMPAIGN" --now "$NOW" \
    > "$OUT/logs/chain.log" 2>&1
  r=$?
  chain_ran=1
  record "chain=$r at=$(stamp)"
  [ "$r" = "0" ] || deviate chain
else
  record "chain=NOT_RUN"
fi

# --- 5. extraction : la liste close du plan § 2, rien d'autre ------------------------------------------------------
if [ "$chain_ran" = "1" ]; then
  extract=$(pyrun - "$OUT/chain/verdict.json" "$OUT/chain/anchor.json" "$OUT/logs/chain.log" "$CAMPAIGN" \
    2>> "$OUT/extract.err" <<'PYEOF'
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
verdict_path, anchor_path, log_path, campaign = sys.argv[1:5]
#: § H.1 (section d'origine) : les trois issues, et les raisons de la liste fermée ; `-` hors `inconclusif`.
ISSUES = ("validé", "réfuté", "inconclusif")
REASONS = (
    "R0_INVALID_RUN", "P_PROVENANCE", "D_WARMUP_PREFIX", "A_NO_ADMISSIBLE_CANDIDATE", "A_BELOW_FLOOR",
    "D_WARMUP_ANCHOR", "R1_NOT_NORMALISED", "E_NO_BENCHMARK", "E_STAMP_MISMATCH", "F_NOT_ESTIMABLE",
    "F_CANNOT_SEPARATE", "D_NOT_ADMISSIBLE", "C_COVERAGE",
)
#: § L.2 : les neuf champs qui suivent le label de la chaîne, dans l'ordre où `c3_verdict` les écrit.
KEYS = (
    "verdict", "raison", "selection", "statut_selection", "continuite", "variante", "provenance", "protocole",
    "observations",
)
failed = False
try:
    with open(log_path, encoding="utf-8") as handle:
        log = handle.read().splitlines()
except OSError:
    log = []
    failed = True

# 1. contrôles mécaniques de verdict.json, comme aux conformités : jamais un champ d'issue
try:
    with open(verdict_path, encoding="utf-8") as handle:
        verdict = json.load(handle)
except FileNotFoundError:
    stop = None
    for line in log:
        found = re.search(r"CHAINE ARRETEE à l'étape (\w+)(?: \(code de retour (\d+)\))?", line)
        if found:
            stop = found
    print("verdict_json=absent")
    print(f"chain_stopped={stop.group(1)}:{stop.group(2) or 'NA'}" if stop else "chain_stopped=inconnu")
except (OSError, ValueError):
    print("verdict_json=illisible")
    failed = True
else:
    try:
        violations = verdict["violations"]
        chain = verdict["chain"]
        replay = [v for v in violations if str(v).startswith(("rejeu", "réplications"))]
        print(f"chain_verified={'true' if chain['verified'] is True else 'false'}")
        print(f"violations_empty={'true' if violations == [] else 'false'}")
        print(f"replay_violations_empty={'true' if replay == [] else 'false'}")
        print("chain_steps=" + ",".join(f"{step['name']}:{step['exit_code']}" for step in chain["steps"]))
    except (KeyError, TypeError):
        print("verdict_json=forme_hors_liste")
        failed = True

# 2. new_entry de l'ancrage de la chaîne : idempotent attendu (la première inscription est celle de l'ancrage autonome)
try:
    with open(anchor_path, encoding="utf-8") as handle:
        value = json.load(handle)["registry"]["new_entry"]
except (OSError, KeyError, TypeError, ValueError):
    value = None
print(f"registry_new_entry_chain={'true' if value is True else 'false' if value is False else 'absent'}")

# 3. la chaîne § L.2 publiée sur stdout : l'issue et la raison, chacune validée contre sa liste close ; le statut de
#    sélection comparé à SÉLECTION_DESCRIPTIVE, jamais imprimé ; aucun autre champ n'est lu.
label = f"C3_{campaign} | "
lines = [line for line in log if line.startswith(label)]
descriptive = False
if len(lines) == 1:
    pairs = [part.split("=", 1) for part in lines[0][len(label):].split(" | ")]
    if all(len(pair) == 2 for pair in pairs) and tuple(pair[0] for pair in pairs) == KEYS:
        fields = dict(pairs)
        issue = fields["verdict"] if fields["verdict"] in ISSUES else "hors_liste"
        reason = fields["raison"] if fields["raison"] in REASONS or fields["raison"] == "-" else "hors_liste"
        descriptive = fields["statut_selection"] == "SÉLECTION_DESCRIPTIVE"
    else:
        issue = reason = "forme_hors_liste"
elif not lines:
    issue = reason = "absent"
else:
    issue = reason = "multiple"
print(f"issue={issue}")
print(f"raison={reason}")
print(f"selection_descriptive={'true' if descriptive else 'false'}")

# 4. la ligne de forme fixe de l'inscription de l'issue au registre (§ A.6 ; D13 : ni valeur ni digest)
inscribed = any(re.fullmatch(r"written .+ \(issue inscrite, § A\.6\)", line) for line in log)
print(f"issue_inscrite={'true' if inscribed else 'false'}")
sys.exit(1 if failed else 0)
PYEOF
  )
  r=$?
  while IFS= read -r line; do
    if [ -n "$line" ]; then record "$line"; fi
  done <<< "$extract"
  record "extract=$r"
  ok=0
  [ "$r" = "0" ] || ok=1
  for want in chain_verified=true violations_empty=true replay_violations_empty=true "chain_steps=$STEPS_OK" \
    registry_new_entry_chain=false issue_inscrite=true issue=inconclusif raison=P_PROVENANCE \
    selection_descriptive=true; do
    printf '%s\n' "$extract" | grep -qxF -- "$want" || ok=1
  done
  [ "$ok" = "0" ] || deviate extract
else
  record "extract=NOT_RUN"
fi

# --- 6. interpréteur des deux provenances : booléen seulement -------------------------------------------------------
if go; then
  pyrun - "$OUT/prefix/prefix_run.json" "$OUT/eval/evaluation_run_provenance.json" "$REPO" >> "$OUT/extract.err" 2>&1 <<'PYEOF'
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
  record "interpreter=$r"
  [ "$r" = "0" ] || deviate interpreter
else
  record "interpreter=NOT_RUN"
fi
record "halted_at=${halted:--}"
record "end_run=$(stamp)"

# --- alembic après (toujours), service, arbre du clone, CAMPAIGN_UNLOCK --------------------------------------------
(cd "$SERVICE" && "$PY" -m alembic current) > "$OUT/alembic_after.txt" 2>&1
r=$?
record "alembic_after=$r"
expect "$r" 0
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
if [ -f "$UNLOCK" ]; then unlock_after=present; else unlock_after=absent; fi
record "campaign_unlock_after=$unlock_after"
expect "$unlock_after" present
record "end=$(stamp)"

exit "$fail"
