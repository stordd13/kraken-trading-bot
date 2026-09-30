#!/bin/bash
# C3 gel v2.3 — les huit xfail d'AM-01 sont rouges aujourd'hui, et à l'endroit voulu (règle agent 1 : un test naît
# adverse). Lancé par `bash` depuis le dépôt, jamais pendant la suite. Deux passes :
#  1. normale : les huit sortent XFAIL strict avec leur raison, aucun XPASS ;
#  2. --runxfail --tb=line : la ligne et l'exception où chacun échoue (l'assertion de la règle, jamais un préalable).
# Sortie : xfail_rouge.out ; rc=0 ssi la passe 1 donne exactement 8 xfailed et 0 XPASS / FAILED.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_v2_3_gel/tests/xfail_rouge.out
LOG=$(mktemp)
K="X1_ or X2_ or X3_ or X4_ or X5_ or X7_ or X8_ or test_R17_temoin"
FILES=(tests/test_scripts/test_c3_common.py tests/test_scripts/test_c3_anchor.py tests/test_scripts/test_c3_verdict.py)
{
  echo "# xfail_rouge — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; -k \"$K\""
  echo "## passe 1 — normale"
} > "$OUT"
poetry run pytest -q -p no:cacheprovider -rxXf "${FILES[@]}" -k "$K" > "$LOG" 2>&1
grep -E '^(XFAIL|XPASS|FAILED|ERROR) ' "$LOG" | sed 's|tests/test_scripts/||' >> "$OUT"
tail -n 1 "$LOG" | sed 's/^/resume=/' >> "$OUT"
rc=0
grep -qE '(^|, )8 xfailed in ' "$LOG" && ! grep -qE '[0-9]+ (passed|failed)' "$LOG" || rc=1
grep -qE '^(XPASS|FAILED|ERROR) ' "$LOG" && rc=1
echo "## passe 2 — --runxfail --tb=line : où chacun échoue" >> "$OUT"
poetry run pytest -q -p no:cacheprovider --runxfail --tb=line "${FILES[@]}" -k "$K" > "$LOG" 2>&1
grep -E '^/.*\.py:[0-9]+: ' "$LOG" | sed "s|$ROOT/tests/test_scripts/||" | sed -E 's/([0-9a-f]{16})[0-9a-f]{48}/\1…/g' | cut -c1-200 >> "$OUT"
tail -n 1 "$LOG" | sed 's/^/resume_runxfail=/' >> "$OUT"
rm -f "$LOG"
echo "rc=$rc" >> "$OUT"
exit $rc
