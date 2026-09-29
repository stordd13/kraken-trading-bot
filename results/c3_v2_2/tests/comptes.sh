#!/usr/bin/env bash
# Réconciliation des comptes (question de Bruno au STOP 2) : clôture C3b → porte v2.2.
#   Base : results/c3b_producteur/closure/tests/suite_locale.out, 3 264 passés, 6 ignorés, 24 désélectionnés, au HEAD
#   fe82fe5 (tunnel ouvert : tests base passés) ; tests, src et scripts identiques entre fe82fe5 et 8689636.
#   Porte : results/c3_v2_2/tests/gate.out, 3 246 passés, 19 ignorés, 24 désélectionnés, 46 xfailed.
# Méthode : collecte seule (--co) des identifiants à 8689636 (worktree temporaire hors du dépôt) et à HEAD, même
# commande que la porte, greffon gate_sans_tunnel chargé des deux côtés (aucun skipif ne touche la base). Chaque
# identifiant retiré ou ajouté est classé ; l'équation passés(HEAD) = base − base_ignorés − retirés + ajoutés_verts
# est vérifiée. Les ignorés et les xfail sont repris de gate.out.
set -u
set -o pipefail
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=8689636
OUT=results/c3_v2_2/tests/comptes.out
PY="$(poetry env info -p)/bin/python"
PLUG="$ROOT/results/c3_v2_2/tests"
WT=$(mktemp -d)/wt_base
A=$(mktemp); B=$(mktemp); LOG=$(mktemp)
rc=0
say() { printf '%s\n' "$1" | tee -a "$OUT"; }
mark() { say "$1=$2"; if [ "$2" != "0" ]; then rc=1; fi; }
: > "$OUT"
say "# comptes — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "# HEAD $(git rev-parse --short HEAD) branche $(git branch --show-current) ; base ${BASE}"

collect() {  # $1 = répertoire, $2 = fichier d'identifiants
  (cd "$1" && PYTHONPATH="$PLUG" "$PY" -m pytest --co -q -p no:cacheprovider -p gate_sans_tunnel \
    -k "not test_determinism_parallel_vs_serial_full" > "$LOG" 2>&1)
  local e=$?
  grep -E '^tests/[^ ]+\.py::' "$LOG" | sed 's|^tests/||' | sort > "$2"
  say "collecte $1 : exit=${e} ; $(tail -n 1 "$LOG")"
  return "$e"
}

git worktree add --detach "$WT" "$BASE" > /dev/null 2>&1 || { say "worktree impossible"; exit 2; }
collect "$WT" "$A"; ea=$?
collect "$ROOT" "$B"; eb=$?
git worktree remove --force "$WT" > /dev/null 2>&1
git worktree prune
if [ -d "$WT" ]; then say "worktree_retire=1"; rc=1; else say "worktree_retire=0"; fi
if [ "$ea" = "0" ] && [ "$eb" = "0" ]; then v=0; else v=1; fi
mark collectes_sans_erreur "$v"

"$PY" - "$A" "$B" gate.out "$OUT" <<'PY'
import re, sys
from pathlib import Path

a = Path(sys.argv[1]).read_text().split("\n")
b = Path(sys.argv[2]).read_text().split("\n")
a = {x for x in a if x}
b = {x for x in b if x}
gate = Path("results/c3_v2_2/tests/gate.out").read_text(encoding="utf-8")
out = open(sys.argv[4], "a", encoding="utf-8")


def say(s):
    print(s)
    out.write(s + "\n")


xfail = {re.sub(r"^XFAIL ", "", m).split(" - ")[0] for m in re.findall(r"^XFAIL .*$", gate, re.MULTILINE)}
removed = sorted(a - b)
added = sorted(b - a)
added_xfail = [t for t in added if t.replace("test_scripts/", "", 1) in xfail or t.split("/", 1)[-1] in xfail]
added_green = [t for t in added if t not in added_xfail]
base_passed, base_skipped = 3264, 6
m = re.search(r"resume=(\d+) passed, (\d+) skipped, (\d+) deselected, (\d+) xfailed", gate)
head_passed, head_skipped, _, head_xfailed = map(int, m.groups())
db_skipped = head_skipped - base_skipped  # les 6 ignorés de la base (intégration Bybit) le sont encore
say(f"collectes : base={len(a)} head={len(b)} (base attendue {base_passed}+{base_skipped}={base_passed + base_skipped})")
say(f"collecte_base_egale_cloture={0 if len(a) == base_passed + base_skipped else 1}")
say(f"collecte_head_egale_porte={0 if len(b) == head_passed + head_skipped + head_xfailed else 1}")
say(f"retires={len(removed)} ajoutes={len(added)} dont xfail={len(added_xfail)} verts={len(added_green)}")
say(f"xfail_tous_neufs={0 if len(added_xfail) == head_xfailed else 1}")
calc = base_passed - db_skipped - len(removed) + len(added_green)
say(
    f"equation : {base_passed} (clôture) − {db_skipped} (base, ignorés sans tunnel) − {len(removed)} (retirés)"
    f" + {len(added_green)} (verts neufs) = {calc} ; porte = {head_passed}"
)
say(f"equation_juste={0 if calc == head_passed else 1}")
say("## retirés (présents à la base, absents à HEAD)")
for t in removed:
    say(f"- {t}")
say("## verts neufs (absents à la base, présents à HEAD, non xfail)")
for t in added_green:
    say(f"- {t}")
PY
grep -qE '^(collecte_base_egale_cloture|collecte_head_egale_porte|xfail_tous_neufs|equation_juste)=1$' "$OUT" && rc=1
rm -f "$A" "$B" "$LOG"
say "rc=${rc}"
exit "$rc"
