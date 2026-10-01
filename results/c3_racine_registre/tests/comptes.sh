#!/bin/bash
# C3 racine du registre, lot 1 — décompte de la suite et réconciliation par identifiants contre la base 313eb00 (repris
# de results/c3_racine_registre/tests/comptes.sh). Usage : bash comptes.sh <suite de tête> (lit suite_base.out,
# suite_<suite>.out, declares.txt). Sortie : comptes_<suite>.out. rc=0 ssi :
#  1. collectes (--co, même -k, base en worktree détaché) : retirés = exactement [renomme_ancien] ; ajoutés = exactement
#     [renomme_nouveau] ∪ [neufs] ;
#  2. XFAIL(tête) = XFAIL(base) − [leves] ; [leves] ⊆ XFAIL(base) ; aucun XPASS, FAILED, ERROR ;
#  3. équation : passés(tête) = passés(base) + |[leves]| + |[neufs]| ; ignorés et désélectionnés (24) inchangés ;
#  4. le -k écarte exactement les 24 `test_determinism_parallel_vs_serial_full` (collecte avec et sans -k, à la tête).
set -o pipefail
set -u
unset VIRTUAL_ENV
SUITE="${1:?suite de tête}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=313eb00c2019b98cf20fb81ac8327f7b9d1e920a
DIR=results/c3_racine_registre/tests
OUT="$DIR/comptes_${SUITE}.out"
PY="$(poetry env info -p)/bin/python"
WT="$(mktemp -d)/wt_base"
A=$(mktemp); B=$(mktemp); C=$(mktemp); LOG=$(mktemp)
K="not test_determinism_parallel_vs_serial_full"
{
  echo "# comptes — suite $SUITE — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
collect() {  # $1 répertoire, $2 sortie, $3 filtre -k (vide : aucun)
  if [ -n "$3" ]; then
    (cd "$1" && "$PY" -m pytest --co -q -p no:cacheprovider -k "$3" > "$LOG" 2>&1)
  else
    (cd "$1" && "$PY" -m pytest --co -q -p no:cacheprovider > "$LOG" 2>&1)
  fi
  local e=$?
  grep -E '^tests/[^ ]+\.py::' "$LOG" | LC_ALL=C sort > "$2"
  echo "collecte $(basename "$1") -k='${3}' : exit=$e ; $(tail -n 1 "$LOG")" >> "$OUT"
  return "$e"
}
git worktree add --detach "$WT" "$BASE" > /dev/null 2>&1 || { echo "worktree impossible" >> "$OUT"; exit 2; }
collect "$WT" "$A" "$K"; ea=$?
git worktree remove --force "$WT" > /dev/null 2>&1; git worktree prune
collect "$ROOT" "$B" "$K"; eb=$?
collect "$ROOT" "$C" ""; ec=$?
rc=0
{ [ $ea -ne 0 ] || [ $eb -ne 0 ] || [ $ec -ne 0 ]; } && rc=1
"$PY" - "$A" "$B" "$C" "$DIR/suite_base.out" "$DIR/suite_${SUITE}.out" "$DIR/declares.txt" >> "$OUT" <<'PY' || rc=1
import re
import sys
from pathlib import Path

a, b, c, sbase, shead, decl = sys.argv[1:7]
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
    elif current is not None:
        sections[current].add(line)
for key in ("leves", "neufs", "renomme_ancien", "renomme_nouveau"):
    sections.setdefault(key, set())
bad = 0


def check(name: str, ok: bool) -> None:
    global bad
    print(f"{name}={0 if ok else 1}")
    bad |= not ok


XRE = re.compile(r"^XFAIL (tests/\S+?\.py::[A-Za-z0-9_]+(?:\[[^\]]*\])?)")


def xfails(path: str) -> set[str]:
    return {m.group(1) for l in Path(path).read_text(encoding="utf-8").splitlines() if (m := XRE.match(l))}


def resume(path: str) -> dict[str, int]:
    line = next(l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.startswith("resume="))
    return {k: int(v) for v, k in re.findall(r"(\d+) (passed|skipped|deselected|xfailed|xpassed|failed|errors?)", line)}


removed, added = sorted(A - B), sorted(B - A)
print(f"collectes : base={len(A)} tete={len(B)}")
check("retires_egal_renomme_ancien", set(removed) == sections["renomme_ancien"])
for t in removed:
    print(f"  retiré : {t}")
check("ajoutes_egal_renomme_nouveau_et_neufs", set(added) == sections["renomme_nouveau"] | sections["neufs"])
for t in added:
    print(f"  ajouté : {t}")
deselected = sorted(C - B)
check(
    "k_deselectionne_exactement_24_full",
    len(deselected) == 24
    and all(t.startswith("tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[") for t in deselected),
)
xb, xh = xfails(sbase), xfails(shead)
print(f"xfail : base={len(xb)} tete={len(xh)} leves_declares={len(sections['leves'])}")
check("leves_inclus_xfail_base", sections["leves"] <= xb)
check("xfail_tete_egal_base_moins_leves", xh == xb - sections["leves"])
for t in sorted(xh):
    print(f"  reste xfail : {t}")
bad_lines = [l for l in Path(shead).read_text(encoding="utf-8").splitlines() if l.startswith(("XPASS ", "FAILED ", "ERROR "))]
check("aucun_xpass_failed_error", not bad_lines)
rb, rh = resume(sbase), resume(shead)
print(f"resume base={rb} tete={rh}")
calc = rb["passed"] + len(sections["leves"]) + len(sections["neufs"])
print(
    f"equation : {rb['passed']} (base) + {len(sections['leves'])} (levés) + {len(sections['neufs'])} (neufs) = {calc} ;"
    f" tête = {rh['passed']}"
)
check("equation_juste", calc == rh["passed"])
check("ignores_inchanges", rb.get("skipped") == rh.get("skipped"))
check("deselectionnes_inchanges_24", rb.get("deselected") == rh.get("deselected") == 24)
check("xfailed_resume_egal_lignes", rh.get("xfailed", 0) == len(xh))
sys.exit(1 if bad else 0)
PY
rm -f "$A" "$B" "$C" "$LOG"
echo "rc=$rc" >> "$OUT"
exit $rc
