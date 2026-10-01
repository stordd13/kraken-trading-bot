#!/bin/bash
# C3 racine du registre, lot 2 — interdits_lot2.sh prouvé avant de servir (règle agent 1 ; repris de
# results/c3_outillage_v2_3/tests/interdits_lot2_adverse.sh et de tests/interdits_adverse.sh du lot 1) : chaque cas
# dévié fabriqué doit le faire sortir en rc≠0 par son propre item ; le témoin (l'arbre tel quel) et le témoin positif de
# la règle 64 hex (le sha256 du manifeste v2.3 comparé est admis) en rc=0. Chaque cas crée un fichier (ou ajoute une
# ligne à un fichier suivi), lance interdits_lot2.sh sous l'étiquette `adv`, puis restaure ; l'état `git status` est
# comparé avant et après chaque cas. Jamais CAMPAIGN_UNLOCK, jamais le répertoire du registre de campagne sous $HOME
# (brief § 6) : leurs contrôles n'ont pas de cas dévié, déclaré.
# Sortie : interdits_lot2_adverse.out, `cas=<nom> rc=<n> attendu=<0|non0> restaure=<0|1> items_en_ecart=[…]`, puis
# rc=0 ssi tout tient.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_racine_registre/tests
OUT=$T/interdits_lot2_adverse.out
ADV_OUT=$T/interdits_lot2_adv.out
: > "$OUT"
echo "# interdits_lot2_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0

ITEMS=$(mktemp)
run() {
  bash "$T/interdits_lot2.sh" adv > /dev/null 2>&1
  local r=$?
  grep -E '^(hors_liste_blanche|artefact_versionne|empreinte_hors_regle|nomme_dette23|nomme_registre_campagne) |=1( |$)|non_suivis=[1-9]' \
    "$ADV_OUT" | grep -vE '^(arbre_hors_index|empreintes_64_ajoutees)=' | cut -c1-70 | tr '\n' ';' > "$ITEMS"
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
  echo "cas=$1 rc=$2 attendu=$3 restaure=$s items_en_ecart=[$(cat "$ITEMS")]" >> "$OUT"
  if [ "$s" != "0" ]; then fail=1; fi
  if [ "$3" = "0" ] && [ "$2" != "0" ]; then fail=1; fi
  if [ "$3" = "non0" ] && [ "$2" = "0" ]; then fail=1; fi
}

record temoin "$(run)" 0
d=results/c3_racine_registre/zz_adverse

# témoin positif : le sha256 du manifeste v2.3 comparé, écrit dans un fichier du chantier, est admis
H=$(shasum -a 256 results/c3_outillage_v2_3/conformite/manifest.json | cut -d' ' -f1)
mkdir -p "$d"; echo "manifeste v2.3 $H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record sha_manifeste_v23 "$r" 0

# 1. code touché : le module du lot 1 (gelé au lot 2), puis un module gelé dès la base
echo "# adverse" >> scripts/audit/c3_anchor.py; r=$(run); git checkout -q -- scripts/audit/c3_anchor.py
record code_du_lot1_touche "$r" non0
echo "# adverse" >> scripts/audit/c3_verdict.py; r=$(run); git checkout -q -- scripts/audit/c3_verdict.py
record verdict_gele "$r" non0

# 2. un test touché
echo "# adverse" >> tests/test_scripts/test_c3_anchor.py; r=$(run); git checkout -q -- tests/test_scripts/test_c3_anchor.py
record test_touche "$r" non0

# 3. le runbook commité au lot 1
echo "# adverse" >> skills/registry.md; r=$(run); git checkout -q -- skills/registry.md; record runbook_touche "$r" non0

# 4. une doc hors liste (CLAUDE.md, PROJECT_CONTEXT.md)
echo "# adverse" >> CLAUDE.md; r=$(run); git checkout -q -- CLAUDE.md; record claude_md "$r" non0
echo "# adverse" >> PROJECT_CONTEXT.md; r=$(run); git checkout -q -- PROJECT_CONTEXT.md; record project_context "$r" non0

# 5. le livrable clos du lot 1
echo "# adverse" >> results/c3_racine_registre/lot1/README.md; r=$(run)
git checkout -q -- results/c3_racine_registre/lot1/README.md; record readme_lot1 "$r" non0

# 6. le protocole
echo "" >> docs/protocole_c3.md; r=$(run); git checkout -q -- docs/protocole_c3.md; record protocole "$r" non0

# 7. artefact du chemin sous le chantier (verdict, registre) ; un autre manifeste que celui de la conformité
mkdir -p "$d"; echo '{}' > "$d/verdict.json"; r=$(run); rm -rf "$d"; record artefact_verdict "$r" non0
mkdir -p "$d"; echo '{}' > "$d/variants.json"; r=$(run); rm -rf "$d"; record artefact_registre "$r" non0
mkdir -p "$d"; echo '{}' > "$d/manifest.json"; r=$(run); rm -rf "$d"; record autre_manifeste "$r" non0

# 8. une empreinte de 64 hex hors règle (construite ici, jamais écrite), dans un fichier du chantier
H=$(printf 'artefact simule' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$d"; echo "eq3 sha=$H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record empreinte_hors_regle "$r" non0

# 9. fichier hors liste blanche à la racine
f=zz_interdits_lot2_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record hors_liste_blanche "$r" non0

# 10. script du chantier qui nomme le répertoire de la dette 23 (mot construit ici)
W=$(printf 'dock%s' er)
mkdir -p "$d"; printf '#!/bin/bash\nls ~/%s\n' "$W" > "$d/x.sh"; r=$(run); rm -rf "$d"; record nomme_dette23 "$r" non0

# 11. script du chantier qui nomme le registre de campagne (chemin construit ici)
C3=$(printf 'c%s' 3)
mkdir -p "$d"; printf '#!/bin/bash\nstat ~/%s/registry/variants.json\n' "$C3" > "$d/x.sh"; r=$(run); rm -rf "$d"
record nomme_registre_campagne "$r" non0

rm -f "$ITEMS"
echo "rc=$fail" >> "$OUT"
exit $fail
