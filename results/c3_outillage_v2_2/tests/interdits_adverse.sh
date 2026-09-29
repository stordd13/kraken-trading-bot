#!/bin/bash
# C3 outillage v2.2, lot 3 — interdits.sh prouvé avant de servir (règle agent 1) : chaque cas dévié fabriqué doit le
# faire sortir en rc≠0 ; le témoin (l'arbre tel quel) en rc=0. Chaque cas crée un fichier (ou ajoute une ligne à un
# fichier suivi), lance interdits.sh sous l'étiquette `adv`, puis restaure ; l'état `git status` est comparé avant et
# après chaque cas. Jamais CAMPAIGN_UNLOCK (interdit de ce lot, même temporairement).
# Sortie : interdits_adverse.out, `cas=<nom> rc=<n> restaure=<0|1>`, puis rc=0 ssi témoin 0, chaque cas ≠ 0, tout
# restauré.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_outillage_v2_2/tests
OUT=$T/interdits_adverse.out
ADV_OUT=$T/interdits_adv.out
: > "$OUT"
echo "# interdits_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0

run() {  # run <nom> <attendu : 0 | non0>
  bash "$T/interdits.sh" adv > /dev/null 2>&1
  local r=$?
  rm -f "$ADV_OUT"
  echo "$r"
}
state_ok() {
  local now
  now=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
  if [ "$now" = "$BEFORE" ]; then echo 0; else echo 1; fi
}
record() {  # record <cas> <rc> <attendu>
  local s
  s=$(state_ok)
  echo "cas=$1 rc=$2 attendu=$3 restaure=$s" >> "$OUT"
  if [ "$s" != "0" ]; then fail=1; fi
  if [ "$3" = "0" ] && [ "$2" != "0" ]; then fail=1; fi
  if [ "$3" = "non0" ] && [ "$2" = "0" ]; then fail=1; fi
}

# témoin : l'arbre tel quel
record temoin "$(run)" 0

# 1. fichier non suivi sous tests/ (code interdit)
f=tests/zz_interdits_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record non_suivi_tests "$r" non0

# 2. ligne ajoutée à un fichier suivi interdit (CLAUDE.md), restauré par git checkout
echo "# adverse" >> CLAUDE.md; r=$(run); git checkout -q -- CLAUDE.md; record suivi_modifie_claude_md "$r" non0

# 3. fichier hors liste blanche à la racine
f=zz_interdits_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record hors_liste_blanche "$r" non0

# 4. artefact du chemin sous le répertoire du chantier
d=results/c3_outillage_v2_2/zz_adverse
mkdir -p "$d"; echo '{}' > "$d/verdict.json"; r=$(run); rm -rf "$d"; record artefact_verdict_json "$r" non0

# 5. archive sous le répertoire du chantier
mkdir -p "$d"; echo x > "$d/c3_outillage_conf_server_20260930.tgz"; r=$(run); rm -rf "$d"; record archive_tgz "$r" non0

# 6. script du lot qui nomme le répertoire de la dette 23 (le mot est construit ici : ce script-ci ne le porte pas, sinon
#    le témoin rougit — constaté au premier passage)
W=$(printf 'dock%s' er)
mkdir -p "$d"; printf '#!/bin/bash\nls ~/%s\n' "$W" > "$d/x.sh"; r=$(run); rm -rf "$d"; record "nomme_$W" "$r" non0

# 7. modification sous results/c3b_producteur (hors lecture)
echo "# adverse" >> results/c3b_producteur/report.md; r=$(run); git checkout -q -- results/c3b_producteur/report.md
record c3b_producteur_modifie "$r" non0

echo "rc=$fail" >> "$OUT"
exit $fail
