#!/bin/bash
# C3 racine du registre — inventaire_filet.sh prouvé avant de servir (règle agent 1) : le témoin (l'arbre tel quel) sort
# en rc=0 ; chaque cas dévié fabriqué — un fichier de test temporaire qui épingle la racine exacte du registre, sous une
# des formes que le brief nomme — le fait sortir en rc≠0 (occurrence NON CLASSÉE). Chaque cas est retiré aussitôt ;
# l'état `git status` est comparé avant et après chaque cas.
# Sortie : inventaire_adverse.out, `cas=<nom> rc=<n> attendu=<0|non0> restaure=<0|1>`, puis rc=0 ssi tout tient.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_racine_registre/tests
OUT=$T/inventaire_adverse.out
ADV_OUT=$T/inventaire_filet_adv.out
F=tests/test_scripts/zz_inventaire_adverse.py
: > "$OUT"
echo "# inventaire_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0

run() {
  bash "$T/inventaire_filet.sh" adv > /dev/null 2>&1
  local r=$?
  rm -f "$ADV_OUT"
  echo "$r"
}
record() {  # record <cas> <rc> <attendu>
  local now s=0
  now=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
  [ "$now" = "$BEFORE" ] || s=1
  echo "cas=$1 rc=$2 attendu=$3 restaure=$s" >> "$OUT"
  [ "$s" = "0" ] || fail=1
  if [ "$3" = "0" ] && [ "$2" != "0" ]; then fail=1; fi
  if [ "$3" = "non0" ] && [ "$2" = "0" ]; then fail=1; fi
}
case_() {  # case_ <nom> <ligne python>
  printf 'def test_zz(registry, path):\n    %s\n' "$2" > "$F"
  local r
  r=$(run)
  rm -f "$F"
  record "$1" "$r" non0
}

record temoin "$(run)" 0
case_ racine_egale_au_litteral 'assert cc.read_json(path) == {"variants": {}}'
case_ cles_de_racine_par_set 'assert set(registry) == {"variants"}'
case_ cles_de_racine_par_keys 'assert list(registry.keys()) == ["variants"]'
case_ cles_de_racine_relues 'assert sorted(cc.read_json(path / "variants.json")) == ["variants"]'

echo "rc=$fail" >> "$OUT"
exit $fail
