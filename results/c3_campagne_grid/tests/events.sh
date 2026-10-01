#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 (repris de results/c3_racine_registre/tests/events.sh) — la liste close des événements d'erreur des producteurs, recopiée dans le pilote de
# campagne (variable EVENTS), est prouvée égale à celle que le code nomme (results/c3_outillage_v2_2/plans/lot3.md § 5).
# Extraction par l'AST de scripts/audit/{c3b_prefix,c3b_evaluate,c3b_common,_common,_db}.py : premier argument
# littéral de `_refuse`, `_control`, `ProducerRefusal`, `ProducerControlError`, `logger.error`. Tout premier argument
# non littéral doit être un relais de nom (`exc.reason`, `exc.control`, ou le paramètre `reason` / `control` d'une
# aide), sinon rc=1. Les événements `info` (`evaluated`, `refusal_form_written`, `written`, `job_done`) sont listés à
# part : le pilote ne consigne que les deux premiers, sur le producteur d'évaluation.
# Sortie : events.out ; rc=0 ssi liste du pilote == liste du code et aucun non-littéral hors relais.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/events.out
PILOT=results/c3_campagne_grid/server/run_campagne.sh

: > "$OUT"
echo "# events — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
python3 - "$PILOT" >> "$OUT" 2>&1 <<'PY'
import ast
import re
import sys

FILES = [
    "scripts/audit/c3b_prefix.py",
    "scripts/audit/c3b_evaluate.py",
    "scripts/audit/c3b_common.py",
    "scripts/audit/_common.py",
    "scripts/audit/_db.py",
]
ERROR_CALLS = {"_refuse", "_control", "ProducerRefusal", "ProducerControlError"}
RELAYS = {"exc.reason", "exc.control", "reason", "control"}
errors: set[str] = set()
infos: set[str] = set()
bad: list[str] = []
for path in FILES:
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
        is_logger = isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "logger"
        if name in ERROR_CALLS or (is_logger and name == "error"):
            target = errors
        elif is_logger and name == "info":
            target = infos
        else:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            target.add(arg.value)
        elif ast.unparse(arg) not in RELAYS:
            bad.append(f"{path}:{node.lineno} {ast.unparse(arg)}")
print(f"code_erreurs_n={len(errors)}")
print(f"code_erreurs={' '.join(sorted(errors))}")
print(f"code_info={' '.join(sorted(infos))}")
print(f"non_litteraux_hors_relais={len(bad)}")
for line in bad:
    print(f"non_litteral {line}")
with open(sys.argv[1], encoding="utf-8") as handle:
    text = handle.read()
match = re.search(r'^EVENTS="([^"]*)"', text, re.M)
pilot = set(match.group(1).split()) if match else set()
print(f"pilote_n={len(pilot)}")
print(f"pilote_moins_code={' '.join(sorted(pilot - errors)) or '-'}")
print(f"code_moins_pilote={' '.join(sorted(errors - pilot)) or '-'}")
ok = match is not None and pilot == errors and not bad
print(f"egal={'0' if ok else '1'}")
sys.exit(0 if ok else 1)
PY
r=$?
echo "rc=$r" >> "$OUT"
exit $r
