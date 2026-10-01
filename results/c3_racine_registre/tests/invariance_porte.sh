#!/bin/bash
# C3 racine du registre, lot 2 — la porte § L.5 n'est pas rejouée (plan L5) : son invariance est prouvée. Dernière porte
# jouée : option 1, les 24 `test_determinism_parallel_vs_serial_full` en rc=0, au c62acb4 (outillage v2.3, lot 2, le
# 30/09 ; results/c3_outillage_v2_3/gate_L5/). rc=0 ssi les quatre contrôles tiennent :
#  (a) les fichiers changés de c62acb4 au HEAD (et à l'index, dans l'arbre, non suivis) ⊆ la liste déclarée ci-dessous ;
#  (b) diff vide contre 313eb00 ET contre c62acb4 (HEAD, index, arbre, non suivis) sur src/ config/ pyproject.toml
#      poetry.lock .github/, scripts/ hors scripts/audit/c3_anchor.py, tests/ hors les trois fichiers de test touchés ;
#  (c) graphe d'import statique (`import X`, `from X import`, imports paresseux et `import_module("X")` compris) :
#      c3_anchor n'est importé que par scripts/audit/c3_verdict.py et des tests C3 (tests/test_scripts/test_c3*.py) ;
#      c3_verdict ne l'est que par des tests C3 ; les trois fichiers de test touchés ne le sont que par des fichiers de
#      tests/ (constat du premier essai : test_c3_common, le module de fixtures, est aussi importé par
#      tests/test_scripts/test_audit_common.py — un test, hors du chemin de la porte, (d) le montre) ; aucun n'a
#      d'importeur sous src/ ni scripts/ hors c3_verdict ;
#  (d) à la collecte du module `_full` (`pytest --collect-only`, greffon jetable hors du dépôt), aucun module du dépôt
#      nommé `c3_*` ou `test_c3*` n'est chargé ; les modules du dépôt chargés sont listés. La collecte ne lit aucune
#      donnée (le module ne fait qu'un test de port local, sans tunnel) ; ce n'est pas un run de la porte.
# Usage : bash invariance_porte.sh <étiquette>. Sortie : invariance_porte_<étiquette>.out.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
GATE=c62acb4c351de177d30b9b7f4c75b8d5c3306ba9
BASE=313eb00c2019b98cf20fb81ac8327f7b9d1e920a
OUT=results/c3_racine_registre/tests/invariance_porte_${LABEL}.out
TOUCHED_CODE=scripts/audit/c3_anchor.py
TOUCHED_TESTS=(tests/test_scripts/test_c3_common.py tests/test_scripts/test_c3_anchor.py tests/test_scripts/test_c3_verdict.py)
FULL=tests/test_scripts/test_run_p6_determinism.py
{
  echo "# invariance_porte — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; porte jouée au $GATE ; base $BASE"
} > "$OUT"
rc=0

# (a) fichiers changés depuis la dernière porte jouée
ALLOW='^(results/c3_outillage_v2_3/.+|results/c3_racine_registre/.+|docs/RESEARCH_LOG\.md|skills/registry\.md|agent/AGENT_C3_RACINE_REGISTRE\.md|scripts/audit/c3_anchor\.py|tests/test_scripts/test_c3_(common|anchor|verdict)\.py)$'
CHANGED=$( { git diff --name-only "$GATE" HEAD; git diff --cached --name-only "$GATE"; git diff --name-only "$GATE";
  git ls-files --others --exclude-standard; } | LC_ALL=C sort -u)
echo "## (a) fichiers changés depuis $GATE (HEAD ∪ index ∪ arbre ∪ non suivis), hors résultats" >> "$OUT"
printf '%s\n' "$CHANGED" | grep . | grep -vE '^results/' | sed 's/^/  /' >> "$OUT"
echo "  + $(printf '%s\n' "$CHANGED" | grep -cE '^results/') fichier(s) sous results/" >> "$OUT"
outside=$(printf '%s\n' "$CHANGED" | grep . | grep -vE "$ALLOW")
if [ -n "$outside" ]; then
  while IFS= read -r f; do echo "hors_liste $f" >> "$OUT"; done <<< "$outside"
  echo "a_fichiers_changes_dans_la_liste=1" >> "$OUT"; rc=1
else
  echo "a_fichiers_changes_dans_la_liste=0" >> "$OUT"
fi

# (b) diff vide sur le code et les tests du chemin de la porte, contre la base du chantier et contre la porte jouée
SPEC=(src config pyproject.toml poetry.lock .github scripts ":(exclude)$TOUCHED_CODE" tests)
for t in "${TOUCHED_TESTS[@]}"; do SPEC+=(":(exclude)$t"); done
for ref in "$BASE" "$GATE"; do
  git diff --quiet "$ref" HEAD -- "${SPEC[@]}"; h=$?
  git diff --quiet --cached "$ref" -- "${SPEC[@]}"; i=$?
  git diff --quiet "$ref" -- "${SPEC[@]}"; w=$?
  u=$(git ls-files --others --exclude-standard -- "${SPEC[@]}" | wc -l | tr -d ' ')
  echo "b_diff_vide ref=${ref:0:7} head=$h index=$i arbre=$w non_suivis=$u" >> "$OUT"
  { [ $h -ne 0 ] || [ $i -ne 0 ] || [ $w -ne 0 ] || [ "$u" != "0" ]; } && rc=1
done

# (c) graphe d'import statique des modules touchés
python3 - >> "$OUT" <<'PY' || rc=1
import re
import subprocess
import sys

files = []
for extra in ([], ["--others", "--exclude-standard"]):
    files += subprocess.run(
        ["git", "ls-files", *extra, "--", "src", "scripts", "tests"], capture_output=True, text=True, check=True
    ).stdout.split()
files = sorted(f for f in set(files) if f.endswith(".py"))
C3_TESTS = re.compile(r"^tests/test_scripts/test_c3[a-z0-9_]*\.py$")
targets = {
    "c3_anchor": lambda f: f == "scripts/audit/c3_verdict.py" or C3_TESTS.match(f),
    "c3_verdict": lambda f: C3_TESTS.match(f),
    "test_c3_common": lambda f: f.startswith("tests/"),
    "test_c3_anchor": lambda f: f.startswith("tests/"),
    "test_c3_verdict": lambda f: f.startswith("tests/"),
}
bad = 0
for name, allowed in targets.items():
    pattern = re.compile(
        rf"^\s*(import\s+{name}\b|from\s+{name}\s+import\b|from\s+[\w.]+\s+import\s+([\w, ]*\b)?{name}\b)"
        rf"|import_module\(\s*[\"'][\w.]*{name}[\"']"
    )
    importers = []
    for f in files:
        own = f.rsplit("/", 1)[-1][:-3]
        if own == name:
            continue
        with open(f, encoding="utf-8") as handle:
            if any(pattern.search(line) for line in handle):
                importers.append(f)
    outside = [f for f in importers if not allowed(f)]
    print(f"c_importe_{name} importeurs={len(importers)} hors_autorises={len(outside)}")
    for f in importers:
        if not C3_TESTS.match(f):
            print(f"  importeur_hors_tests_c3 {f}")
    for f in outside:
        print(f"  HORS_AUTORISES {f}")
    bad |= bool(outside)
print(f"c_graphe_import={1 if bad else 0}")
sys.exit(1 if bad else 0)
PY

# (d) modules du dépôt chargés à la collecte du module `_full`
TMP=$(mktemp -d) || exit 2
cat > "$TMP/invariance_collecte.py" <<'PY'
import os
import sys


def pytest_collection_finish(session):
    root = os.environ["INV_ROOT"]
    rows = []
    for name, module in sorted(sys.modules.items()):
        path = str(getattr(module, "__file__", None) or "")
        if path.startswith(root + "/") and "/venv/" not in path and "/.venv/" not in path:
            rows.append(f"{name} {path[len(root) + 1:]}")
    with open(os.environ["INV_OUT"], "w", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")
PY
INV_ROOT=$(pwd -P) INV_OUT="$TMP/modules.txt" PYTHONPATH="$TMP${PYTHONPATH:+:$PYTHONPATH}" \
  poetry run pytest --collect-only -q -p no:cacheprovider -p invariance_collecte "$FULL" > "$TMP/collect.log" 2>&1
e=$?
echo "d_collecte_exit=$e ; $(grep -E 'tests? collected|error' "$TMP/collect.log" | tail -n 1)" >> "$OUT"
[ "$e" -eq 0 ] || rc=1
if [ -f "$TMP/modules.txt" ]; then
  n=$(grep -c . "$TMP/modules.txt")
  c3=$(awk '{print $1}' "$TMP/modules.txt" | grep -cE '(^|\.)(c3_|test_c3)')
  echo "d_modules_du_depot_charges=$n dont_c3=$c3" >> "$OUT"
  sed 's/^/  /' "$TMP/modules.txt" >> "$OUT"
  [ "$c3" = "0" ] || rc=1
else
  echo "d_modules_du_depot_charges=absent" >> "$OUT"; rc=1
fi
rm -rf "$TMP"

echo "rc=$rc" >> "$OUT"
exit $rc
