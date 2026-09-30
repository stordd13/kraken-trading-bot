#!/bin/bash
# C3 gel v2.3 — décompte de la suite (brief § 4.3, amendé par le GO du 30/09, décision G-10) et réconciliation par
# identifiants contre la base 662c104 (règle du STOP 2 v2.2). Usage : bash comptes_gel.sh <suite de tête>
# (lit suite_base.out, suite_<suite>.out, declares_gel.txt). Sortie : comptes_gel.out. rc=0 ssi :
#  1. collectes (--co, même -k) : retirés = ∅ ; ajoutés = exactement [neufs] ;
#  2. XFAIL(tête) = XFAIL(base) ∪ [neufs] ∪ [vers_xfail] ; aucun XPASS, FAILED, ERROR ;
#  3. équation : passés(tête) = passés(base) − |[vers_xfail]| ; ignorés et désélectionnés inchangés ;
#  4. attendu du GO : 3 309 passés, 9 xfail, 0 échec, 0 XPASS ;
#  5. objets de premier niveau des trois fichiers de test (AST, contre la base) : modifiés = [objets_modifies],
#     ajoutés = [objets_ajoutes], retirés = ∅ — aucun test existant modifié hors déclaration.
set -o pipefail
set -u
unset VIRTUAL_ENV
SUITE="${1:?suite de tête}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=662c104ef8cb5a9b5c7fb04452f7af817cb5a87a
DIR=results/c3_v2_3_gel/tests
OUT="$DIR/comptes_gel.out"
PY="$(poetry env info -p)/bin/python"
WT="$(mktemp -d)/wt_base"
A=$(mktemp); B=$(mktemp); LOG=$(mktemp)
K="not test_determinism_parallel_vs_serial_full"
{
  echo "# comptes_gel — suite $SUITE — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
collect() {  # $1 répertoire, $2 sortie
  (cd "$1" && "$PY" -m pytest --co -q -p no:cacheprovider -k "$K" > "$LOG" 2>&1)
  local e=$?
  grep -E '^tests/[^ ]+\.py::' "$LOG" | LC_ALL=C sort > "$2"
  echo "collecte $(basename "$1") : exit=$e ; $(tail -n 1 "$LOG")" >> "$OUT"
  return "$e"
}
git worktree add --detach "$WT" "$BASE" > /dev/null 2>&1 || { echo "worktree impossible" >> "$OUT"; exit 2; }
collect "$WT" "$A"; ea=$?
git worktree remove --force "$WT" > /dev/null 2>&1; git worktree prune
collect "$ROOT" "$B"; eb=$?
rc=0
{ [ $ea -ne 0 ] || [ $eb -ne 0 ]; } && rc=1
"$PY" - "$A" "$B" "$DIR/suite_base.out" "$DIR/suite_${SUITE}.out" "$DIR/declares_gel.txt" "$BASE" >> "$OUT" <<'PY' || rc=1
import ast
import re
import subprocess
import sys
from pathlib import Path

a, b, sbase, shead, decl, base = sys.argv[1:7]
ids = lambda p: {x for x in Path(p).read_text(encoding="utf-8").split("\n") if x}
A, B = ids(a), ids(b)
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
bad = 0


def check(name: str, ok: bool) -> None:
    global bad
    print(f"{name}={0 if ok else 1}")
    bad |= not ok


XRE = re.compile(r"^XFAIL (tests/\S+?\.py::[A-Za-z0-9_]+(?:\[[^\]]*\])?)")


def lines_of(path: str, prefix: str) -> set[str]:
    return {m.group(1) for l in Path(path).read_text(encoding="utf-8").splitlines() if (m := XRE.match(l))} if prefix == "XFAIL" else {
        l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.startswith(prefix)
    }


def resume(path: str) -> dict[str, int]:
    line = next(l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.startswith("resume="))
    return {k: int(v) for v, k in re.findall(r"(\d+) (passed|skipped|deselected|xfailed|xpassed|failed|errors?)", line)}


removed, added = sorted(A - B), sorted(B - A)
print(f"collectes : base={len(A)} tete={len(B)}")
check("retires_vide", not removed)
for t in removed:
    print(f"  retiré : {t}")
check("ajoutes_egal_neufs_declares", set(added) == sections["neufs"])
for t in added:
    print(f"  neuf : {t}")
xb, xh = lines_of(sbase, "XFAIL"), lines_of(shead, "XFAIL")
print(f"xfail : base={len(xb)} tete={len(xh)}")
check("xfail_tete_egal_base_neufs_vers_xfail", xh == xb | sections["neufs"] | sections["vers_xfail"])
bad_lines = [l for l in Path(shead).read_text(encoding="utf-8").splitlines() if l.startswith(("XPASS ", "FAILED ", "ERROR "))]
check("aucun_xpass_failed_error", not bad_lines)
rb, rh = resume(sbase), resume(shead)
print(f"resume base={rb} tete={rh}")
calc = rb["passed"] - len(sections["vers_xfail"])
print(f"equation : {rb['passed']} (base) − {len(sections['vers_xfail'])} (témoin R-17 → xfail) + 0 (neufs verts) = {calc} ; tête = {rh['passed']}")
check("equation_juste", calc == rh["passed"])
check("ignores_inchanges", rb.get("skipped") == rh.get("skipped"))
check("deselectionnes_inchanges_24", rb.get("deselected") == rh.get("deselected") == 24)
check(
    "attendu_du_GO_3309_passes_9_xfail",
    rh.get("passed") == 3309 and rh.get("xfailed") == 9 and not rh.get("failed") and not rh.get("xpassed"),
)


def objects(text: str) -> dict[str, str]:
    tree = ast.parse(text)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            continue
        src = ast.get_source_segment(text, node) or ""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            src = "\n".join(ast.get_source_segment(text, d) or "" for d in node.decorator_list) + "\n" + src
        for n in names:
            out[n] = src
    return out


changed, new, gone = set(), set(), set()
for name in ("test_c3_anchor.py", "test_c3_common.py", "test_c3_verdict.py"):
    path = f"tests/test_scripts/{name}"
    old = objects(subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True, check=True).stdout)
    cur = objects(Path(path).read_text(encoding="utf-8"))
    changed |= {f"{name}::{k}" for k in old.keys() & cur.keys() if old[k] != cur[k]}
    new |= {f"{name}::{k}" for k in cur.keys() - old.keys()}
    gone |= {f"{name}::{k}" for k in old.keys() - cur.keys()}
print(f"objets : modifies={len(changed)} ajoutes={len(new)} retires={len(gone)}")
for k in sorted(changed):
    print(f"  modifié : {k}")
check("objets_modifies_egal_declares", changed == sections["objets_modifies"])
check("objets_ajoutes_egal_declares", new == sections["objets_ajoutes"])
check("objets_retires_vide", not gone)
for k in sorted((changed ^ sections["objets_modifies"]) | (new ^ sections["objets_ajoutes"]) | gone):
    print(f"  écart : {k}")
sys.exit(1 if bad else 0)
PY
rm -f "$A" "$B" "$LOG"
echo "rc=$rc" >> "$OUT"
exit $rc
