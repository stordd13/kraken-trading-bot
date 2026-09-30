#!/bin/bash
# C3 gel v2.3 — les tests verts du commit C2 mordent-ils ? (règle agent 1 ; vérifier par mutation.) Lancé par `bash`
# depuis le dépôt, APRÈS la suite, jamais pendant (les sous-processus importeraient le mutant). Chaque mutant est
# appliqué à une copie en place, le test visé est lancé, le fichier est restauré depuis sa copie, son sha256 revérifié.
#  M1 — c3_anchor.stop_criterion accepte toute empreinte sur une famille au verdict compté : l'adverse R-17 mis à jour
#       (X6, côté refus, vert) doit rougir ;
#  M2-M4 — le descripteur côté test (`fx.deferred_descriptor`, attendu de X3, X6, X7) perd une règle du tableau
#       d'AM-01 : X5, qui l'épingle avant l'appel à l'outillage, doit sortir FAILED (AssertionError, pas l'AttributeError
#       déclarée) au lieu de xfailed.
# Sortie : mutants_gel.out ; rc=0 ssi chaque mutant est vu et l'arbre rendu identique (git diff vide sur scripts/).
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DIR=results/c3_v2_3_gel/tests
OUT="$DIR/mutants_gel.out"
TMP=$(mktemp -d)
LOG=$(mktemp)
{
  echo "# mutants_gel — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
FILES=(scripts/audit/c3_anchor.py tests/test_scripts/test_c3_common.py)
for f in "${FILES[@]}"; do cp "$f" "$TMP/$(basename "$f")"; done
before=$(shasum -a 256 "${FILES[@]}")
rc=0
ADVERSE="tests/test_scripts/test_c3_anchor.py::test_R17_sur_une_famille_close_une_autre_empreinte_que_la_differee_est_refusee"
X5="tests/test_scripts/test_c3_verdict.py::test_X5_le_descripteur_est_derive_champ_par_champ_selon_le_tableau_du_texte"

mutant() {  # $1 nom, $2 fichier, $3 lu, $4 écrit, $5 test visé, $6 motif attendu dans la sortie pytest
  python3 - "$2" "$3" "$4" <<'PY'
import sys
path, old, new = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
assert text.count(old) == 1, f"mutant inapplicable : {old!r} ({text.count(old)} occurrences) dans {path}"
open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
PY
  poetry run pytest -q -p no:cacheprovider -rfxX "$5" > "$LOG" 2>&1; r=$?
  cp "$TMP/$(basename "$2")" "$2"
  if [ "$r" -ne 0 ] && grep -qE "$6" "$LOG"; then
    echo "mutant $1 vu=0 (pytest=$r ; $(tail -n 1 "$LOG"))" >> "$OUT"
  else
    echo "mutant $1 vu=1 (pytest=$r ; $(tail -n 1 "$LOG")) — NON VU" >> "$OUT"; rc=1
  fi
}

mutant M1_ancrage_accepte_tout_sur_famille_close scripts/audit/c3_anchor.py \
  "        if key in expected:
            return" \
  "        if True:
            return" \
  "$ADVERSE" '^FAILED .*test_R17_sur_une_famille_close'
mutant M2_timeframes_non_tries tests/test_scripts/test_c3_common.py \
  '"decision_timeframes": sorted(effective),' '"decision_timeframes": list(effective),' \
  "$X5" '^FAILED .*test_X5_'
mutant M3_engines_non_restreint tests/test_scripts/test_c3_common.py \
  '"engines": {strategy: block["engine"]},' '"engines": {n: b["engine"] for n, b in raw["strategies"].items()},' \
  "$X5" '^FAILED .*test_X5_'
mutant M4_pair_costs_non_restreint tests/test_scripts/test_c3_common.py \
  '"pair_costs": {pair: copy.deepcopy(fees["pair_costs"][pair])},' '"pair_costs": copy.deepcopy(fees["pair_costs"]),' \
  "$X5" '^FAILED .*test_X5_'

after=$(shasum -a 256 "${FILES[@]}")
if [ "$before" = "$after" ] && git diff --quiet -- scripts; then
  echo "arbre_restaure=0 (sha256 identiques, git diff scripts/ vide)" >> "$OUT"
else
  echo "arbre_restaure=1" >> "$OUT"; rc=1
fi
rm -rf "$TMP" "$LOG"
echo "rc=$rc" >> "$OUT"
exit $rc
