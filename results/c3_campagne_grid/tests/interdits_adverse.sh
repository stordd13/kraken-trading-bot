#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — interdits.sh prouvé avant de servir (règle agent 1 ; repris de
# results/c3_racine_registre/tests/interdits_lot2_adverse.sh) : chaque cas dévié fabriqué doit le faire sortir en rc≠0
# par son propre item ; le témoin (l'arbre tel quel) et le témoin positif de la règle 64 hex (le sha256 du manifeste
# gelé est admis) en rc=0. Chaque cas crée un fichier, ajoute une ligne à un fichier suivi ou indexe le brief, lance
# interdits.sh sous l'étiquette `adv`, puis restaure ; l'état `git status` est comparé avant et après chaque cas, et le
# contenu de chaque fichier sauvegardé (journal, pilote) est comparé par `cmp` à sa sauvegarde.
# Les deux cas du pilote (faute de frappe dans un littéral `--registry`, troisième ligne `--registry`) ne s'exercent
# que si le pilote existe ; sinon `sans_objet`, déclaré. Jamais CAMPAIGN_UNLOCK, jamais le répertoire du registre de
# campagne sous $HOME (brief § 3) : leurs contrôles n'ont pas de cas dévié, déclaré.
# Sortie : interdits_adverse.out, `cas=<nom> rc=<n> attendu=<0|non0> restaure=<0|1> items_en_ecart=[…]`, puis rc=0 ssi
# tout tient.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
T=results/c3_campagne_grid/tests
OUT=$T/interdits_adverse.out
ADV_OUT=$T/interdits_adv.out
BRIEF=agent/AGENT_C3_CAMPAGNE_GRID.md
PILOT=results/c3_campagne_grid/server/run_campagne.sh
: > "$OUT"
echo "# interdits_adverse — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
BEFORE=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
fail=0

ITEMS=$(mktemp)
SAVE=$(mktemp)
run() {
  bash "$T/interdits.sh" adv > /dev/null 2>&1
  local r=$?
  grep -E '^(hors_liste_blanche|artefact_versionne|empreinte_hors_regle|nomme_dette23|nomme_registre_campagne|suivi_interdit) |=1( |$)|non_suivis=[1-9]' \
    "$ADV_OUT" | grep -vE '^(arbre_hors_index|empreintes_64_ajoutees)=' | cut -c1-70 | tr '\n' ';' > "$ITEMS"
  rm -f "$ADV_OUT"
  echo "$r"
}
state_ok() {
  local now
  now=$(git status --porcelain --untracked-files=all | grep -v " $ADV_OUT\$" | grep -v " $OUT\$")
  if [ "$now" = "$BEFORE" ]; then echo 0; else echo 1; fi
}
record() {  # record <cas> <rc> <attendu> [contenu restauré : 0 | 1]
  local s
  s=$(state_ok)
  if [ "${4:-0}" != "0" ]; then s=1; fi
  echo "cas=$1 rc=$2 attendu=$3 restaure=$s items_en_ecart=[$(cat "$ITEMS")]" >> "$OUT"
  if [ "$s" != "0" ]; then fail=1; fi
  if [ "$3" = "0" ] && [ "$2" != "0" ]; then fail=1; fi
  if [ "$3" = "non0" ] && [ "$2" = "0" ]; then fail=1; fi
}

record temoin "$(run)" 0
d=results/c3_campagne_grid/zz_adverse

# témoin positif : le sha256 du manifeste gelé, écrit dans un fichier du chantier, est admis
H=$(shasum -a 256 agent/manifest_campagne_draft.json | cut -d' ' -f1)
mkdir -p "$d"; echo "manifeste gelé $H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record sha_manifeste_gele "$r" 0

# 1. code, test, runbook, docs hors liste, un fichier suivi de agent/
echo "# adverse" >> scripts/audit/c3_verdict.py; r=$(run); git checkout -q -- scripts/audit/c3_verdict.py
record code_touche "$r" non0
echo "# adverse" >> tests/test_scripts/test_c3_anchor.py; r=$(run); git checkout -q -- tests/test_scripts/test_c3_anchor.py
record test_touche "$r" non0
echo "# adverse" >> skills/registry.md; r=$(run); git checkout -q -- skills/registry.md; record runbook_touche "$r" non0
echo "# adverse" >> CLAUDE.md; r=$(run); git checkout -q -- CLAUDE.md; record claude_md "$r" non0
echo "# adverse" >> agent/AGENT_C3_RACINE_REGISTRE.md; r=$(run); git checkout -q -- agent/AGENT_C3_RACINE_REGISTRE.md
record agent_suivi_touche "$r" non0

# 2. le brief de ce chantier indexé (jamais commité par ce chantier)
git add -- "$BRIEF"; r=$(run); git rm -q --cached -- "$BRIEF"; record brief_indexe "$r" non0

# 3. le protocole
echo "" >> docs/protocole_c3.md; r=$(run); git checkout -q -- docs/protocole_c3.md; record protocole "$r" non0

# 4. le journal : une ligne existante modifiée (ajout seul violé), restauré depuis sa sauvegarde
cp docs/RESEARCH_LOG.md "$SAVE"
sed -e 's/^# Journal des essais de recherche (append-only)$/# Journal des essais de recherche (modifié)/' "$SAVE" \
  > docs/RESEARCH_LOG.md
r=$(run); cp "$SAVE" docs/RESEARCH_LOG.md; cmp -s "$SAVE" docs/RESEARCH_LOG.md; c=$?
record journal_ligne_modifiee "$r" non0 "$c"

# 5. artefacts du chemin sous le chantier : verdict, registre, un autre manifeste, une empreinte d'archive
mkdir -p "$d"; echo '{}' > "$d/verdict.json"; r=$(run); rm -rf "$d"; record artefact_verdict "$r" non0
mkdir -p "$d"; echo '{}' > "$d/variants.json"; r=$(run); rm -rf "$d"; record artefact_registre "$r" non0
mkdir -p "$d"; echo '{}' > "$d/manifest.json"; r=$(run); rm -rf "$d"; record autre_manifeste "$r" non0
mkdir -p "$d"; echo x > "$d/c3_campagne_grid_server.tgz.sha256"; r=$(run); rm -rf "$d"; record empreinte_archive "$r" non0

# 6. une empreinte de 64 hex hors règle (construite ici, jamais écrite), dans un fichier du chantier
H=$(printf 'artefact simule' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$d"; echo "sha=$H" > "$d/note.txt"; r=$(run); rm -rf "$d"; record empreinte_hors_regle "$r" non0

# 7. fichier hors liste blanche à la racine
f=zz_interdits_adverse.txt
echo x > "$f"; r=$(run); rm -f "$f"; record hors_liste_blanche "$r" non0

# 8. script du chantier qui nomme le répertoire de la dette 23 (mot construit ici)
W=$(printf 'dock%s' er)
mkdir -p "$d"; printf '#!/bin/bash\nls ~/%s\n' "$W" > "$d/x.sh"; r=$(run); rm -rf "$d"; record nomme_dette23 "$r" non0

# 9. script du chantier, autre que le pilote, qui nomme le registre de campagne (chemin construit ici)
C3=$(printf 'c%s' 3)
mkdir -p "$d"; printf '#!/bin/bash\nstat ~/%s/registry/variants.json\n' "$C3" > "$d/x.sh"; r=$(run); rm -rf "$d"
record nomme_registre_campagne "$r" non0

# 10. le pilote : faute de frappe dans le premier littéral `--registry` ; troisième ligne `--registry`
if [ -f "$PILOT" ]; then
  REG_FULL="/home/bruno/${C3}/regis$(printf 'try')/variants.json"
  cp "$PILOT" "$SAVE"
  perl -pe 'if (!$done && s{(--registry \S*?)variants\.json}{${1}variant.json}) { $done = 1 }' "$SAVE" > "$PILOT"
  r=$(run); cp "$SAVE" "$PILOT"; cmp -s "$SAVE" "$PILOT"; c=$?
  record registre_faute_de_frappe "$r" non0 "$c"
  { cat "$SAVE"; printf '# --registry %s\n' "$REG_FULL"; } > "$PILOT"
  r=$(run); cp "$SAVE" "$PILOT"; cmp -s "$SAVE" "$PILOT"; c=$?
  record registre_troisieme_ligne "$r" non0 "$c"
else
  echo "cas=registre_faute_de_frappe sans_objet (pilote absent)" >> "$OUT"
  echo "cas=registre_troisieme_ligne sans_objet (pilote absent)" >> "$OUT"
fi

rm -f "$ITEMS" "$SAVE"
echo "rc=$fail" >> "$OUT"
exit $fail
