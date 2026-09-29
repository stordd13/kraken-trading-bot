#!/bin/bash
# C3 outillage v2.2, lot 1 — les xfail de chaîne R-18 restés xfail échouent désormais sur leur ATTENDU, et non plus
# sur l'option --candles-eval inconnue du parseur (critère de fin du lot 1 ; comparaison avec la nature constatée à
# 8c114fe, results/c3_v2_2/tests/xfail_rouge.out, section R18 : « usage: c3_verdict.py chain … »).
# À 8c114fe, la chaîne rendait 2 parce qu'argparse refusait --candles-eval (sortie d'usage). Relance en --runxfail des
# trois tests de chaîne R-18 restants. rc=0 ssi : pytest code 1, trois échecs sur assertion, aucune sortie d'usage
# d'argparse ni « unrecognized arguments », et la chaîne a tourné jusqu'à la continuité dans chacun (« CHAINE ARRETEE
# à l'étape continuity » : la forme de refus n'y est pas encore admise — R-18, lot 2).
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_2/tests/xfail_reste.out
LOG=$(mktemp)
K="R18_une_evaluation_sous_forme or R18_un_refus_que_l_export or R18_un_refus_d_une_autre"
{
  echo "# xfail R-18 de chaîne restés — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
  echo "# commande : pytest -q -p no:cacheprovider --runxfail --tb=short -k \"$K\" tests/test_scripts/test_c3_verdict.py"
  echo "# nature à 8c114fe :"
  sed -n '/^## .*R-18/,/^runxfail_exit/p' results/c3_v2_2/tests/xfail_rouge.out | grep -E "test_c3_verdict" | cut -c1-160 | sed 's/^/#   /'
} > "$OUT"
poetry run pytest -q -p no:cacheprovider --runxfail --tb=short -k "$K" tests/test_scripts/test_c3_verdict.py > "$LOG" 2>&1
code=$?
echo "# nature au HEAD :" >> "$OUT"
grep -E '^(E   |_+ test_)' "$LOG" | cut -c1-220 >> "$OUT"
tail -n 1 "$LOG" >> "$OUT"
n_assert=$(grep -cE '^E   (AssertionError|assert )' "$LOG")
n_usage=$(grep -cE 'usage: c3_verdict|unrecognized arguments' "$LOG")
# une fois par test : les sections « ____ test_… ____ » du rapport, et non les occurrences (répétées par le rendu
# de l'assertion)
n_cont=$(awk '/^_+ test_/{if (s) n++; s=0} /CHAINE ARRETEE à l.étape continuity/{s=1} END{if (s) n++; print n+0}' "$LOG")
echo "runxfail_exit=$code (attendu 1) echecs_sur_assertion=$n_assert (attendu 3) usage_argparse=$n_usage (attendu 0) arret_continuite=$n_cont (attendu 3)" >> "$OUT"
rm -f "$LOG"
if [ "$code" -eq 1 ] && [ "$n_assert" -eq 3 ] && [ "$n_usage" -eq 0 ] && [ "$n_cont" -eq 3 ]; then echo "rc=0" >> "$OUT"; exit 0; fi
echo "rc=1" >> "$OUT"; exit 1
