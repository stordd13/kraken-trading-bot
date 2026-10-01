#!/bin/bash
# C3 racine du registre, lot 2 — invariance_porte.sh prouvé avant de servir (règle agent 1) : le témoin (l'arbre tel
# quel) sort en rc=0 ; chaque cas dévié, fabriqué puis restauré, le fait sortir en rc≠0 par le contrôle qu'il vise :
#  b  — un fichier du chemin de la porte modifié (scripts/backtest.py, ligne de commentaire ajoutée) ;
#  c  — un module de src/ qui importerait c3_anchor (fichier non suivi, retiré ensuite) ;
#  d  — le module `_full` qui chargerait c3_common à la collecte (ligne ajoutée puis restaurée ; (b) mord aussi) ;
#  a  — un fichier hors liste à la racine (non suivi, retiré ensuite).
# Sortie : invariance_adverse.out, `cas=<nom> rc=<n> attendu=<0|non0> restaure=<0|1> items=[…]`, puis rc=0 ssi tout
# tient.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_racine_registre/tests
OUT=$T/invariance_adverse.out
ADV_OUT=$T/invariance_porte_adv.out
: > "$OUT"
echo "# invariance_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0
ITEMS=$(mktemp)
run() {
  bash "$T/invariance_porte.sh" adv > /dev/null 2>&1
  local r=$?
  grep -E '^(hors_liste |a_fichiers_changes_dans_la_liste=1|b_diff_vide .*=1|  HORS_AUTORISES|c_graphe_import=1|d_modules_du_depot_charges=[0-9]+ dont_c3=[1-9])' \
    "$ADV_OUT" | cut -c1-80 | tr '\n' ';' > "$ITEMS"
  rm -f "$ADV_OUT"
  echo "$r"
}
record() {  # record <cas> <rc> <attendu>
  local now s=0
  now=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
  [ "$now" = "$BEFORE" ] || s=1
  echo "cas=$1 rc=$2 attendu=$3 restaure=$s items=[$(cat "$ITEMS")]" >> "$OUT"
  [ "$s" = "0" ] || fail=1
  if [ "$3" = "0" ] && [ "$2" != "0" ]; then fail=1; fi
  if [ "$3" = "non0" ] && [ "$2" = "0" ]; then fail=1; fi
}

record temoin "$(run)" 0

echo "# adverse" >> scripts/backtest.py; r=$(run); git checkout -q -- scripts/backtest.py; record b_backtest_modifie "$r" non0

f=src/krakenbot/zz_invariance_adverse.py
printf 'import c3_anchor  # adverse\n' > "$f"; r=$(run); rm -f "$f"; record c_src_importe_c3_anchor "$r" non0

F=tests/test_scripts/test_run_p6_determinism.py
printf '\nsys.path.insert(0, str(Path(_project_root) / "scripts" / "audit"))\nimport c3_common  # noqa: E402,F401 adverse\n' >> "$F"
r=$(run); git checkout -q -- "$F"; record d_full_charge_c3_common "$r" non0

f=zz_invariance_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record a_hors_liste "$r" non0

rm -f "$ITEMS"
echo "rc=$fail" >> "$OUT"
exit $fail
