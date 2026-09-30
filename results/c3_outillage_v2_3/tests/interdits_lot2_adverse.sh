#!/bin/bash
# C3 outillage v2.3, lot 2 — interdits_lot2.sh prouvé avant de servir (règle agent 1 ; repris de
# tests/interdits_adverse.sh du lot 1) : chaque cas dévié fabriqué doit le faire sortir en rc≠0 ; le témoin (l'arbre tel
# quel) en rc=0. Chaque cas crée un fichier (ou ajoute une ligne à un fichier suivi), lance interdits_lot2.sh sous
# l'étiquette `adv`, puis restaure ; l'état `git status` est comparé avant et après chaque cas. Jamais CAMPAIGN_UNLOCK.
# Sortie : interdits_lot2_adverse.out, `cas=<nom> rc=<n> attendu=<0|non0> restaure=<0|1>`, puis rc=0 ssi témoin 0,
# chaque cas ≠ 0, tout restauré.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_outillage_v2_3/tests
OUT=$T/interdits_lot2_adverse.out
ADV_OUT=$T/interdits_lot2_adv.out
: > "$OUT"
echo "# interdits_lot2_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0

run() {
  bash "$T/interdits_lot2.sh" adv > /dev/null 2>&1
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

record temoin "$(run)" 0

# 1. code touché : un module de chaîne du lot 1 (gelé au lot 2)
echo "# adverse" >> scripts/audit/c3_verdict.py; r=$(run); git checkout -q -- scripts/audit/c3_verdict.py
record code_du_lot1_touche "$r" non0

# 2. un test touché
echo "# adverse" >> tests/test_scripts/test_c3_anchor.py; r=$(run); git checkout -q -- tests/test_scripts/test_c3_anchor.py
record test_touche "$r" non0

# 3. une doc hors liste (CLAUDE.md, PROJECT_CONTEXT.md)
echo "# adverse" >> CLAUDE.md; r=$(run); git checkout -q -- CLAUDE.md; record claude_md "$r" non0
echo "# adverse" >> PROJECT_CONTEXT.md; r=$(run); git checkout -q -- PROJECT_CONTEXT.md; record project_context "$r" non0

# 4. le livrable clos du lot 1
echo "# adverse" >> results/c3_outillage_v2_3/lot1/README.md; r=$(run)
git checkout -q -- results/c3_outillage_v2_3/lot1/README.md; record readme_lot1 "$r" non0

# 5. le protocole
echo "" >> docs/protocole_c3.md; r=$(run); git checkout -q -- docs/protocole_c3.md; record protocole "$r" non0

# 6. artefact du chemin sous le chantier (verdict, registre) ; un autre manifeste que celui de la conformité
d=results/c3_outillage_v2_3/zz_adverse
mkdir -p "$d"; echo '{}' > "$d/verdict.json"; r=$(run); rm -rf "$d"; record artefact_verdict "$r" non0
mkdir -p "$d"; echo '{}' > "$d/variants.json"; r=$(run); rm -rf "$d"; record artefact_registre "$r" non0
mkdir -p "$d"; echo '{}' > "$d/manifest.json"; r=$(run); rm -rf "$d"; record autre_manifeste "$r" non0

# 7. une empreinte de 64 hex hors règle (construite ici, jamais écrite), dans un fichier du chantier
H=$(printf 'artefact simule' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$d"; echo "eq3 sha=$H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record empreinte_hors_regle "$r" non0

# 8. fichier hors liste blanche à la racine
f=zz_interdits_lot2_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record hors_liste_blanche "$r" non0

# 9. script du chantier qui nomme le répertoire de la dette 23 (mot construit ici)
W=$(printf 'dock%s' er)
mkdir -p "$d"; printf '#!/bin/bash\nls ~/%s\n' "$W" > "$d/x.sh"; r=$(run); rm -rf "$d"; record nomme_dette23 "$r" non0

echo "rc=$fail" >> "$OUT"
exit $fail
