#!/bin/bash
# C3 outillage v2.3, lot 1 — interdits.sh prouvé avant de servir (règle agent 1 ; repris de
# results/c3_outillage_v2_2/tests/interdits_adverse.sh) : chaque cas dévié fabriqué doit le faire sortir en rc≠0 ; le
# témoin (l'arbre tel quel) en rc=0. Chaque cas crée un fichier (ou ajoute une ligne à un fichier suivi), lance
# interdits.sh sous l'étiquette `adv`, puis restaure ; l'état `git status` est comparé avant et après chaque cas.
# Jamais CAMPAIGN_UNLOCK (interdit, même temporairement) ; `gel_v2_3.patch` n'est jamais touché (pas à ce chantier) :
# son contrôle (sha inchangé) n'a pas de cas dévié ici, déclaré au README.
# Sortie : interdits_adverse.out, `cas=<nom> rc=<n> attendu=<0|non0> restaure=<0|1>`, puis rc=0 ssi témoin 0, chaque
# cas ≠ 0, tout restauré.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_outillage_v2_3/tests
OUT=$T/interdits_adverse.out
ADV_OUT=$T/interdits_adv.out
: > "$OUT"
echo "# interdits_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0

run() {
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

# 1. fichier non suivi sous tests/ hors des quatre fichiers du lot
f=tests/zz_interdits_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record non_suivi_tests "$r" non0

# 2. module de code hors des trois du lot (c3_entry), ligne ajoutée puis restaurée
echo "# adverse" >> scripts/audit/c3_entry.py; r=$(run); git checkout -q -- scripts/audit/c3_entry.py
record code_hors_liste "$r" non0

# 3. le protocole gelé touché (chemin gelé et sha recalculé ≠ consigné)
echo "" >> docs/protocole_c3.md; r=$(run); git checkout -q -- docs/protocole_c3.md
record protocole_modifie "$r" non0

# 4. fichier suivi hors liste blanche (CLAUDE.md)
echo "# adverse" >> CLAUDE.md; r=$(run); git checkout -q -- CLAUDE.md; record suivi_claude_md "$r" non0

# 5. fichier hors liste blanche à la racine
f=zz_interdits_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record hors_liste_blanche "$r" non0

# 6. artefact du chemin sous le répertoire du chantier
d=results/c3_outillage_v2_3/zz_adverse
mkdir -p "$d"; echo '{}' > "$d/verdict.json"; r=$(run); rm -rf "$d"; record artefact_verdict_json "$r" non0

# 7. registre sous le répertoire du chantier
mkdir -p "$d"; echo '{}' > "$d/variants.json"; r=$(run); rm -rf "$d"; record artefact_registre "$r" non0

# 8. empreinte de 64 hex hors table d'Adoption, dans un fichier du chantier (construite, jamais écrite ici)
H=$(printf 'adverse' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$d"; echo "sha $H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record empreinte_hors_table "$r" non0

# 9. script du chantier qui nomme le répertoire de la dette 23 (le mot est construit ici)
W=$(printf 'dock%s' er)
mkdir -p "$d"; printf '#!/bin/bash\nls ~/%s\n' "$W" > "$d/x.sh"; r=$(run); rm -rf "$d"; record "nomme_dette23" "$r" non0

# 10. répertoire clos d'un chantier précédent modifié
echo "# adverse" >> results/c3_v2_3_gel/report.md; r=$(run); git checkout -q -- results/c3_v2_3_gel/report.md
record gel_modifie "$r" non0

echo "rc=$fail" >> "$OUT"
exit $fail
