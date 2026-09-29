#!/bin/bash
# C3 outillage v2.2, lot 3 — le pilote de conformité exercé en local dans un monde simulé, sans base, sans serveur,
# avant S1 (plans/lot3.md § 5) : une panne du pilote se voit ici, pas sur le serveur.
#
# Monde simulé, dans un répertoire temporaire hors du dépôt, supprimé ensuite :
#  - un clone local du dépôt (HEAD courant), où le pilote et le manifeste de l'arbre de travail sont committés dans
#    le clone seulement ; dans la copie du pilote, TROIS lignes changent (SERVICE, PY, RUN : chemins du monde simulé),
#    comptées ;
#  - un « service » : dépôt git jetable portant poetry.lock et pyproject.toml de HEAD ;
#  - un faux interpréteur (Python, stdlib) : `-V`, `-c import krakenbot`, `-m alembic current`, `-` (heredoc, exécuté
#    pour de vrai), et les sept scripts, qui écrivent des sorties déterministes EMBARQUANT LES CHEMINS DE LEURS ENTRÉES
#    comme le vrai code (c3_anchor.py:309, c3_entry.py:778,797 — la parade K3 est donc éprouvée) et des provenances à
#    durée aléatoire (les exclusions K4 sont donc éprouvées) ;
#  - un faux `systemctl` (active, NRestarts=0).
# Simulations : conforme (pilote 0) ; `eval_run2` (evaluation.json diffère au seul run 2 : pilote 1, eq3 r12=1 r13=0) ;
# `chain_violation` (chaîne en 1 avec une violation de rejeu : pilote 1) ; garde de SHA (pilote 2) ; puis le pilote
# de la porte (gate_L5/run_gate.sh, faux `pytest` qui écrit un JUnit par combo) : conforme (pilote 0), et `gate_skip`
# (combo7 skippé avec rc=0, le faux vert « module skippé » : pilote 1).
# Limite dite : bash local 3.2, serveur bash 5 ; seules des constructions portables sont employées.
# Env : DRYRUN_OUT (sortie, défaut tests/pilot_dryrun.out) ; DRYRUN_KEEP (répertoire où déposer status.txt,
# alembic_*.txt, pilot_exit.txt et sim.env des deux simulations conformes, la porte sous gate/ avec
# pytest_summary.txt — témoins de verify_adverse.sh).
# rc=0 ssi les six simulations rendent leur code attendu et les conformes portent leurs marqueurs.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=${DRYRUN_OUT:-results/c3_outillage_v2_2/tests/pilot_dryrun.out}
SELF=results/c3_outillage_v2_2/conformite/server/run_conformite.sh
MANIFEST=results/c3_outillage_v2_2/conformite/manifest.json
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# pilot_dryrun — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"
log "bash_local=$(bash --version | head -n 1)"

# --- faux systemctl, faux interpréteur -----------------------------------------------------------------------------
mkdir -p "$T/bin"
cat > "$T/bin/systemctl" <<'SH'
#!/bin/bash
case "$1" in
  is-active) echo active ;;
  show) echo "NRestarts=0" ;;
  *) exit 1 ;;
esac
SH
cat > "$T/bin/fakepy" <<'PY'
#!/usr/bin/env python3
import json
import os
import random
import sys

args = sys.argv[1:]
dev = os.environ.get("SIM_DEVIATION", "")
state = os.environ["SIM_STATE"]
src = os.environ.get("PYTHONPATH", "")


def opt(name):
    return args[args.index(name) + 1] if name in args else None


def dump(path, payload):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def count(name):
    path = os.path.join(state, name)
    n = int(open(path).read()) + 1 if os.path.exists(path) else 1
    open(path, "w").write(str(n))
    return n


kb = f"{src}/krakenbot/__init__.py"
if args[:1] == ["-V"]:
    print("Python 3.12.3")
elif args[:1] == ["-c"]:
    if "socket" in args[1]:
        sys.exit(0)
    print(kb)
elif args[:2] == ["-m", "pytest"] and "--version" in args:
    print("pytest 9.0.2")
elif args[:2] == ["-m", "pytest"]:
    junit = next(a.split("=", 1)[1] for a in args if a.startswith("--junitxml="))
    test = args[-1]
    skipped = 1 if (dev == "gate_skip" and test.endswith("[combo7]")) else 0
    with open(junit, "w", encoding="utf-8") as handle:
        handle.write(f'<testsuites><testsuite tests="1" failures="0" errors="0" skipped="{skipped}"/></testsuites>\n')
    if skipped:
        print("1 skipped in 0.10s")
    else:
        print(f"1.23s call     {test}")
        print("1 passed in 1.30s")
elif args[:2] == ["-m", "alembic"]:
    print("INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.")
    print("INFO  [alembic.runtime.migration] Will assume transactional DDL.")
    print("c3bd1e7a0001 (head)")
elif args[:1] == ["-"]:
    code = sys.stdin.read()
    sys.argv = ["-", *args[1:]]
    exec(compile(code, "<stdin>", "exec"), {"__name__": "__main__"})
else:
    script = os.path.basename(args[0])
    if script == "c3b_prefix.py":
        out = opt("--output-dir")
        for name in ("observations", "coverage", "candles"):
            dump(f"{out}/{name}.json", {"sim": name, "manifest": opt("--manifest")})
        dump(f"{out}/partial/x.json", {"duration_s": random.random()})
        dump(f"{out}/prefix_run.json", {"interpreter": {"krakenbot": kb}, "duration_s": random.random()})
        print("2026-09-29T00:00:00Z [info     ] job_done                       identity=x")
    elif script == "c3_anchor.py":
        dump(opt("--registry"), {"variants": {"k": {"family": "sim"}}})
        dump(opt("--output"), {"sim": "anchor", "registry": {"path": opt("--registry")}})
    elif script == "c3_entry.py":
        dump(opt("--output"), {"sim": "entry", "observations": {"path": opt("--observations")}})
        open(opt("--markdown"), "w").write(f"entry {opt('--observations')}\n")
    elif script == "c3_benchmark.py":
        dump(opt("--output"), {"sim": "benchmark", "anchor": opt("--anchor")})
    elif script == "c3_select.py":
        dump(opt("--output"), {"sim": "selection", "benchmark": opt("--benchmark")})
        open(opt("--markdown"), "w").write(f"selection {opt('--coverage')}\n")
    elif script == "c3b_evaluate.py":
        out = opt("--output-dir")
        n = count("evaluate")
        drift = n if (dev == "eval_run2" and n == 2) else 0
        dump(f"{out}/evaluation.json", {"sim": "evaluation", "selection": opt("--selection"), "drift": drift})
        for name in ("benchmark_eval", "candles_eval", "evaluation_sensitivity"):
            dump(f"{out}/{name}.json", {"sim": name})
        dump(f"{out}/evaluation_run_provenance.json", {"interpreter": {"krakenbot": kb}, "duration_s": random.random()})
        print("2026-09-29T00:00:00Z [info     ] evaluated                      source=selection")
    elif script == "c3_verdict.py" and args[1:2] == ["chain"]:
        out = opt("--out-dir")
        steps = [{"name": s, "exit_code": 0} for s in ("anchor", "entry", "benchmark", "select", "continuity")]
        for name in ("anchor", "entry", "benchmark", "selection", "continuity"):
            dump(f"{out}/{name}.json", {"sim": f"chain-{name}", "evaluation": opt("--evaluation")})
        for name in ("entry", "selection"):
            open(f"{out}/{name}.md", "w").write(f"chain {name}\n")
        bad = dev == "chain_violation"
        violations = ["rejeu {21:dd} : simulé"] if bad else []
        dump(f"{out}/verdict.json", {"violations": violations, "chain": {"verified": not bad, "steps": steps}})
        registry = json.load(open(opt("--registry")))
        registry["variants"]["k"]["verdict"] = {"issue": "sim"}
        dump(opt("--registry"), registry)
        sys.exit(1 if bad else 0)
    else:
        print(f"fakepy: script inconnu {args}", file=sys.stderr)
        sys.exit(9)
PY
chmod +x "$T/bin/systemctl" "$T/bin/fakepy"

# --- service jetable ------------------------------------------------------------------------------------------------
mkdir -p "$T/service"
git -C "$T/service" init -q
git show HEAD:poetry.lock > "$T/service/poetry.lock"
git show HEAD:pyproject.toml > "$T/service/pyproject.toml"
git -C "$T/service" add poetry.lock pyproject.toml
git -C "$T/service" -c user.name=sim -c user.email=sim@localhost commit -q -m service

# simulate <nom> <déviation> <sha à passer : HEAD | faux> [pilote] [phase] -> code du pilote ; monde neuf à chaque fois
simulate() {
  local name=$1 deviation=$2 which=$3 pilot=${4:-$SELF} phase=${5:-conf}
  local run=$T/$name/runs/c3_outillage/$phase
  mkdir -p "$run/out" "$T/$name/state"
  git clone -q "$ROOT" "$run/repo" || return 90
  mkdir -p "$(dirname "$run/repo/$MANIFEST")" "$(dirname "$run/repo/$pilot")"
  cp "$MANIFEST" "$run/repo/$MANIFEST"
  sed -e "s|^SERVICE=/home/bruno/apps/kraken-trading-bot\$|SERVICE=$T/service|" \
    -e "s|^PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python\$|PY=$T/bin/fakepy|" \
    -e "s|^RUN=/home/bruno/runs/c3_outillage/$phase\$|RUN=$run|" "$pilot" > "$run/repo/$pilot"
  CHANGED=$(diff "$pilot" "$run/repo/$pilot" | grep -c '^>')
  git -C "$run/repo" add "$MANIFEST" "$pilot"
  git -C "$run/repo" -c user.name=sim -c user.email=sim@localhost commit -q -m "sim"
  touch "$run/repo/.env"
  local sha
  sha=$(git -C "$run/repo" rev-parse HEAD)
  if [ "$which" = faux ]; then sha=0000000000000000000000000000000000000000; fi
  (cd "$run/repo" && PATH="$T/bin:$PATH" SIM_DEVIATION="$deviation" SIM_STATE="$T/$name/state" \
    bash "$run/repo/$pilot" "$sha" > "$T/$name/stdout.txt" 2>&1)
  local r=$?
  echo "$r" > "$run/out/pilot_exit.txt"
  SIM_RUN=$run
  SIM_SHA=$(git -C "$run/repo" rev-parse HEAD)
  return $r
}
status_line() { grep -E "^$2" "$1/out/status.txt" 2> /dev/null | head -n 1; }

# 1. conforme
simulate conforme "" HEAD; r=$?
log "pilote_lignes_changees=$CHANGED"
[ "$CHANGED" = "3" ] || fail=1
lines=$(wc -l < "$SIM_RUN/out/status.txt" | tr -d ' ')
log "sim_conforme_exit=$r lignes_status=$lines"
log "sim_conforme_$(status_line "$SIM_RUN" 'bit_equal_3of3=')"
log "sim_conforme_$(status_line "$SIM_RUN" 'listing_expected_3of3=')"
[ "$r" = "0" ] || fail=1
grep -qx "bit_equal_3of3=0 compared=23 differing=0 absent=0" "$SIM_RUN/out/status.txt" || fail=1
if [ -n "${DRYRUN_KEEP:-}" ]; then
  mkdir -p "$DRYRUN_KEEP"
  cp "$SIM_RUN/out/status.txt" "$SIM_RUN/out/alembic_before.txt" "$SIM_RUN/out/alembic_after.txt" \
    "$SIM_RUN/out/pilot_exit.txt" "$DRYRUN_KEEP/"
  {
    echo "SIM_SHA=$SIM_SHA"
    echo "SIM_PILOT_SHA=$(sha256sum "$SIM_RUN/repo/$SELF" | cut -d' ' -f1)"
  } > "$DRYRUN_KEEP/sim.env"
fi

# 2. evaluation.json différent au seul run 2
simulate eval_run2 eval_run2 HEAD; r=$?
log "sim_eval_run2_exit=$r"
log "sim_eval_run2_$(status_line "$SIM_RUN" 'eq3 eval/evaluation.json=')"
[ "$r" = "1" ] || fail=1
grep -qx "eq3 eval/evaluation.json=1 r12=1 r13=0" "$SIM_RUN/out/status.txt" || fail=1

# 3. chaîne en 1 avec une violation de rejeu
simulate chain_violation chain_violation HEAD; r=$?
log "sim_chain_violation_exit=$r"
log "sim_chain_violation_$(status_line "$SIM_RUN" 'chain_1=')"
log "sim_chain_violation_$(status_line "$SIM_RUN" 'replay_violations_empty_1=')"
[ "$r" = "1" ] || fail=1
grep -qx "replay_violations_empty_1=false" "$SIM_RUN/out/status.txt" || fail=1

# 4. garde : SHA passé ≠ HEAD
simulate guard_head "" faux; r=$?
log "sim_guard_head_exit=$r"
log "sim_guard_head_$(status_line "$SIM_RUN" 'guard=' | cut -d' ' -f1)"
[ "$r" = "2" ] || fail=1

# 5. pilote de la porte, conforme : 24 combos 1/0/0/0
GATE=results/c3_outillage_v2_2/gate_L5/run_gate.sh
simulate gate_conforme "" HEAD "$GATE" gate; r=$?
log "gate_pilote_lignes_changees=$CHANGED"
[ "$CHANGED" = "3" ] || fail=1
log "sim_gate_conforme_exit=$r"
log "sim_gate_conforme_$(status_line "$SIM_RUN" 'full=')"
log "sim_gate_conforme_$(status_line "$SIM_RUN" 'junit_total=')"
log "sim_gate_conforme_$(status_line "$SIM_RUN" 'extract=')"
[ "$r" = "0" ] || fail=1
grep -qx "junit_total=tests:24,failures:0,errors:0,skipped:0,missing:0" "$SIM_RUN/out/status.txt" || fail=1
if [ -n "${DRYRUN_KEEP:-}" ]; then
  mkdir -p "$DRYRUN_KEEP/gate"
  cp "$SIM_RUN/out/status.txt" "$SIM_RUN/out/alembic_before.txt" "$SIM_RUN/out/alembic_after.txt" \
    "$SIM_RUN/out/pilot_exit.txt" "$SIM_RUN/out/pytest_summary.txt" "$DRYRUN_KEEP/gate/"
  {
    echo "SIM_SHA=$SIM_SHA"
    echo "SIM_PILOT_SHA=$(sha256sum "$SIM_RUN/repo/$GATE" | cut -d' ' -f1)"
  } > "$DRYRUN_KEEP/gate/sim.env"
fi

# 6. porte : combo7 skippé avec rc=0 (le faux vert « module skippé ») -> pilote 1
simulate gate_skip gate_skip HEAD "$GATE" gate; r=$?
log "sim_gate_skip_exit=$r"
log "sim_gate_skip_$(status_line "$SIM_RUN" 'combo7=' | cut -d' ' -f1-2)"
log "sim_gate_skip_$(status_line "$SIM_RUN" 'full=')"
[ "$r" = "1" ] || fail=1
grep -q "^combo7=0 junit=1/0/0/1 " "$SIM_RUN/out/status.txt" || fail=1

rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
