#!/bin/bash
# C3 racine du registre — interdits.sh prouvé avant de servir (règle agent 1 ; repris de
# results/c3_outillage_v2_3/tests/interdits_adverse.sh) : chaque cas dévié fabriqué doit le faire sortir en rc≠0 ; le
# témoin (l'arbre tel quel) et le témoin positif de la règle 64 hex (D10 : le sha256 d'un fichier du chantier est admis)
# en rc=0. Chaque cas crée un fichier (ou ajoute une ligne à un fichier suivi), lance interdits.sh sous l'étiquette
# `adv`, puis restaure ; l'état `git status` est comparé avant et après chaque cas.
# Jamais CAMPAIGN_UNLOCK, jamais le répertoire du registre de campagne sous $HOME (interdits, même temporairement : brief
# § 6) — leurs contrôles n'ont pas de cas dévié ici, déclaré au README.
# Sortie : interdits_adverse.out, `cas=<nom> rc=<n> attendu=<0|non0> restaure=<0|1> items_en_ecart=[…]` (les lignes
# d'interdits en écart : chaque cas dévié doit mordre par son propre item), puis rc=0 ssi tout tient.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_racine_registre/tests
OUT=$T/interdits_adverse.out
ADV_OUT=$T/interdits_adv.out
: > "$OUT"
echo "# interdits_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0

ITEMS=$(mktemp)
run() {
  bash "$T/interdits.sh" adv > /dev/null 2>&1
  local r=$?
  grep -E '^(hors_liste_blanche|artefact_versionne|empreinte_hors_regle|nomme_dette23|nomme_registre_campagne) |=1( |$)|non_suivis=[1-9]' \
    "$ADV_OUT" | cut -c1-70 | tr '\n' ';' > "$ITEMS"
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

# témoin : l'arbre tel quel
record temoin "$(run)" 0

d=results/c3_racine_registre/zz_adverse

# témoin positif D10 : le sha256 d'un fichier du chantier, écrit dans un autre fichier du chantier, est admis
H=$(shasum -a 256 "$T/interdits.sh" | cut -d' ' -f1)
mkdir -p "$d"; echo "sha $H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record sha_fichier_du_chantier "$r" 0

# 1. fichier non suivi sous tests/ hors des trois fichiers du lot
f=tests/zz_interdits_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record non_suivi_tests "$r" non0

# 2. module de chaîne hors liste (c3_entry), ligne ajoutée puis restaurée
echo "# adverse" >> scripts/audit/c3_entry.py; r=$(run); git checkout -q -- scripts/audit/c3_entry.py
record code_hors_liste "$r" non0

# 3. module gelé pour ce chantier (c3_verdict, plan D3)
echo "# adverse" >> scripts/audit/c3_verdict.py; r=$(run); git checkout -q -- scripts/audit/c3_verdict.py
record verdict_gele "$r" non0

# 4. le protocole gelé touché (chemin gelé et sha recalculé ≠ consigné)
echo "" >> docs/protocole_c3.md; r=$(run); git checkout -q -- docs/protocole_c3.md
record protocole_modifie "$r" non0

# 5. fichier suivi hors liste blanche (CLAUDE.md)
echo "# adverse" >> CLAUDE.md; r=$(run); git checkout -q -- CLAUDE.md; record suivi_claude_md "$r" non0

# 6. fichier hors liste blanche à la racine
f=zz_interdits_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record hors_liste_blanche "$r" non0

# 7. artefact du chemin sous le répertoire du chantier
mkdir -p "$d"; echo '{}' > "$d/verdict.json"; r=$(run); rm -rf "$d"; record artefact_verdict_json "$r" non0

# 8. registre sous le répertoire du chantier
mkdir -p "$d"; echo '{}' > "$d/variants.json"; r=$(run); rm -rf "$d"; record artefact_registre "$r" non0

# 9. empreinte de 64 hex hors règle, dans un fichier du chantier (construite, jamais écrite ici)
H=$(printf 'adverse' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$d"; echo "sha $H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record empreinte_hors_regle "$r" non0

# 10. script du chantier qui nomme le répertoire de la dette 23 (le mot est construit ici)
W=$(printf 'dock%s' er)
mkdir -p "$d"; printf '#!/bin/bash\nls ~/%s\n' "$W" > "$d/x.sh"; r=$(run); rm -rf "$d"; record nomme_dette23 "$r" non0

# 11. script du chantier qui nomme le registre de campagne (le chemin est construit ici)
C3=$(printf 'c%s' 3)
mkdir -p "$d"; printf '#!/bin/bash\nstat ~/%s/registry/variants.json\n' "$C3" > "$d/x.sh"; r=$(run); rm -rf "$d"
record nomme_registre_campagne "$r" non0

# 12. répertoire clos d'un chantier précédent modifié
echo "# adverse" >> results/c3_outillage_v2_3/report.md; r=$(run); git checkout -q -- results/c3_outillage_v2_3/report.md
record v23_modifie "$r" non0

rm -f "$ITEMS"
echo "rc=$fail" >> "$OUT"
exit $fail
