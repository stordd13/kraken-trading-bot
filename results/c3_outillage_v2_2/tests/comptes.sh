#!/bin/bash
# C3 outillage v2.2 — réconciliation des comptes par identifiants contre la base 8c114fe (règle du STOP 2 v2.2).
# Usage : bash comptes.sh <étiquette> <suite>   (lit suite_base.out, suite_<suite>.out et declares_<étiquette>.txt)
# 1. Collecte (--co) à 8c114fe (worktree temporaire) et au HEAD, avec le -k de la convention ; retirés = ∅ ;
#    ajoutés = exactement la section [neufs] de declares_<étiquette>.txt.
# 2. Le -k « not test_determinism_parallel_vs_serial_full » désélectionne exactement les 24 `_full` : collecte au
#    HEAD avec et sans -k, différence = 24 ids, tous test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full.
# 3. XFAIL levés (base − HEAD) = exactement la section [leves] ; XFAIL du HEAD ⊆ XFAIL de la base.
# 4. Équation : passés(HEAD) = passés(base) + levés + neufs ; ignorés et désélectionnés inchangés.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
SUITE="${2:?suite de tête}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=8c114fe
DIR=results/c3_outillage_v2_2/tests
OUT="$DIR/comptes_${LABEL}.out"
PY="$(poetry env info -p)/bin/python"
WT="$(mktemp -d)/wt_base"
A=$(mktemp); B=$(mktemp); C=$(mktemp); LOG=$(mktemp)
K="not test_determinism_parallel_vs_serial_full"
{
  echo "# comptes — $LABEL (suite $SUITE) — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
collect() {  # $1 répertoire, $2 sortie, $3 expression -k ("" = aucune)
  if [ -n "$3" ]; then
    (cd "$1" && "$PY" -m pytest --co -q -p no:cacheprovider -k "$3" > "$LOG" 2>&1)
  else
    (cd "$1" && "$PY" -m pytest --co -q -p no:cacheprovider > "$LOG" 2>&1)
  fi
  local e=$?
  grep -E '^tests/[^ ]+\.py::' "$LOG" | sort > "$2"
  echo "collecte $(basename "$1") k=[${3}] : exit=$e ; $(tail -n 1 "$LOG")" >> "$OUT"
  return "$e"
}
git worktree add --detach "$WT" "$BASE" > /dev/null 2>&1 || { echo "worktree impossible" >> "$OUT"; exit 2; }
collect "$WT" "$A" "$K"; ea=$?
git worktree remove --force "$WT" > /dev/null 2>&1; git worktree prune
collect "$ROOT" "$B" "$K"; eb=$?
collect "$ROOT" "$C" ""; ec=$?
rc=0
{ [ $ea -ne 0 ] || [ $eb -ne 0 ] || [ $ec -ne 0 ]; } && rc=1
"$PY" - "$A" "$B" "$C" "$DIR/suite_base.out" "$DIR/suite_${SUITE}.out" "$DIR/declares_${LABEL}.txt" "$OUT" <<'PY' || rc=1
import re
import sys
from pathlib import Path

a, b, c, sbase, shead, decl, out = sys.argv[1:8]
ids = lambda p: {x for x in Path(p).read_text(encoding="utf-8").split("\n") if x}
A, B, C = ids(a), ids(b), ids(c)
sections: dict[str, set[str]] = {}
current = None
for line in Path(decl).read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("[") and line.endswith("]"):
        current = line[1:-1]
        sections[current] = set()
    else:
        sections[current].add(line)
log = open(out, "a", encoding="utf-8")
bad = 0


def say(s: str) -> None:
    log.write(s + "\n")


def check(name: str, ok: bool) -> None:
    global bad
    say(f"{name}={0 if ok else 1}")
    bad |= not ok


XRE = re.compile(r"^XFAIL (tests/\S+?\.py::[A-Za-z0-9_]+(?:\[[^\]]*\])?)(?: - .*)?$")


def xfails(path: str) -> set[str]:
    return {m.group(1) for line in Path(path).read_text(encoding="utf-8").splitlines() if (m := XRE.match(line))}


def resume(path: str) -> dict[str, int]:
    line = next(l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.startswith("resume="))
    return {k: int(v) for v, k in re.findall(r"(\d+) (passed|skipped|deselected|xfailed|xpassed|failed)", line)}


removed, added = sorted(A - B), sorted(B - A)
say(f"collectes : base={len(A)} head={len(B)} head_sans_k={len(C)}")
check("retires_vide", not removed)
for t in removed:
    say(f"  retiré : {t}")
check("ajoutes_egal_declares", set(added) == sections.get("neufs", set()))
for t in added:
    say(f"  neuf : {t}")
full = sorted(C - B)
check(
    "k_desélectionne_exactement_24_full",
    len(full) == 24
    and all(t.startswith("tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[") for t in full)
    and not (B - C),
)
xb, xh = xfails(sbase), xfails(shead)
lifted = xb - xh
say(f"xfail : base={len(xb)} head={len(xh)} leves={len(lifted)}")
check("xfail_head_inclus_base", xh <= xb)
check("leves_egal_declares", lifted == sections.get("leves", set()))
for t in sorted(lifted ^ sections.get("leves", set())):
    say(f"  écart levés : {t}")
rb, rh = resume(sbase), resume(shead)
say(f"resume base={rb} head={rh}")
calc = rb["passed"] + len(lifted) + len(added)
say(f"equation : {rb['passed']} (base) + {len(lifted)} (levés) + {len(added)} (neufs) = {calc} ; head = {rh['passed']}")
check("equation_juste", calc == rh["passed"])
check("ignores_inchanges", rb.get("skipped", 0) == rh.get("skipped", 0))
check("deselectionnes_inchanges", rb.get("deselected", 0) == rh.get("deselected", 0) == 24)
check("xfailed_resume_egal_lignes", rh.get("xfailed", 0) == len(xh) and rb.get("xfailed", 0) == len(xb))
sys.exit(1 if bad else 0)
PY
rm -f "$A" "$B" "$C" "$LOG"
echo "rc=$rc" >> "$OUT"
exit $rc
