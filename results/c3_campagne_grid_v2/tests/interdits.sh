#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4 (relance unique) — interdits du brief (§ 3), du runbook
# (skills/registry.md § 4) et du plan (plans/plan.md § 6), lancé par `bash` AVANT chaque commit (fichiers indexés) et au
# tip. Repris de results/c3_campagne_grid/tests/interdits.sh ; reprise comptée dans reprise.out.
# Usage : bash interdits.sh <étiquette>. Sortie : interdits_<étiquette>.out. rc=0 ssi :
#  1. chemins gelés contre cce566d (base du chantier), dont le chantier v1 results/c3_campagne_grid/ (historique clos) :
#     intacts au commit, à l'index, dans l'arbre, aucun non suivi — sauf, sous agent/, le brief et le brouillon du
#     manifeste v2, non suivis par décision (brief § 3) ;
#  2. le protocole est gelé : sha256 recalculé = dernière ligne `**sha256 vX.Y :**` de l'Adoption du paquet v2.3 ;
#  3. liste blanche : tout fichier changé depuis cce566d est sous results/c3_campagne_grid_v2/ ou est docs/RESEARCH_LOG.md ;
#     le brief et le brouillon ne sont ni suivis ni indexés ;
#  4. docs/RESEARCH_LOG.md en ajout seul : aucune ligne retirée ni modifiée depuis cce566d (commits, index, arbre) ;
#  5. aucun artefact du chemin sélection sous results/c3_campagne_grid_v2/ (`manifest.json` à la racine du chantier
#     excepté par son nom exact), aucune archive ni empreinte d'archive (`.tgz`, `.tgz.sha256`) ; CAMPAIGN_UNLOCK absent
#     en local (arbre et HEAD) ;
#  6. règle 64 hex : toute empreinte de 64 hex ajoutée depuis cce566d (chaque commit, l'arbre, les non suivis) est une
#     empreinte du protocole (table d'Adoption), le sha256 d'un fichier du chantier (results/c3_campagne_grid_v2/**,
#     suivi ou non) ou l'une des deux empreintes du gel v2 — le sha256 du manifeste gelé et la clé de variante du parent
#     qu'il porte — jamais celui d'un artefact du chemin ni d'une archive ; une sortie qui porterait autre chose est
#     filtrée à la source, la règle n'est jamais élargie (A4 du chantier v1) ;
#  7. aucun script ni vérificateur du chantier ne nomme le répertoire de la dette 23 (ce fichier et son adverse
#     exceptés : le mot y est construit) ;
#  8. registre de campagne : dans les scripts et vérificateurs du chantier, son chemin n'apparaît que sur les deux
#     lignes `--registry` du pilote, chacune égale au chemin construit ici, une seule fois par ligne (contrôle
#     mécanique ; la relecture du STOP 1 au caractère près reste la parade, A2) ; tant que le pilote n'existe pas, zéro
#     occurrence ; le répertoire n'existe pas sous le $HOME local.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=cce566d82f40166d9ff95c972e346b26831ed304
CH=results/c3_campagne_grid_v2
DIR=$CH/tests
OUT="$DIR/interdits_${LABEL}.out"
PACKAGE=docs/amendements_c3_v2.3.md
BRIEF=agent/AGENT_C3_CAMPAGNE_GRID_V2.md
DRAFT=agent/manifest_campagne_v2_draft.json
PILOT=$CH/server/run_campagne.sh
MANIFEST_SHA=b757c45bbed2b0913ac4ec781c9c6928fa935b7c71639e66f26fb5d2468f4f11
PARENT_KEY=3159a90780ebbf8a4ae4a271a7f3685be4a63309485554466790297fb057fcb5
{
  echo "# interdits — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
rc=0
untracked_except() {  # fichiers non suivis sous <chemin>, hors le brief et le brouillon (non suivis par décision)
  git ls-files --others --exclude-standard -- "$1" | grep -vxF -e "$BRIEF" -e "$DRAFT"
}
frozen() {  # frozen <étiquette> <référence> <chemins…>
  local tag=$1 ref=$2
  shift 2
  local p h i w u
  for p in "$@"; do
    git diff --quiet "$ref" HEAD -- "$p"; h=$?
    git diff --quiet --cached "$ref" -- "$p"; i=$?
    git diff --quiet "$ref" -- "$p"; w=$?
    u=$(untracked_except "$p" | wc -l | tr -d ' ')
    echo "$tag $p head=$h index=$i arbre=$w non_suivis=$u" >> "$OUT"
    { [ $h -ne 0 ] || [ $i -ne 0 ] || [ $w -ne 0 ] || [ "$u" != "0" ]; } && rc=1
  done
}

# 1. chemins gelés contre la base du chantier (brief § 3 : diff vide contre cce566d, chantier v1 compris)
frozen gele "$BASE" src scripts tests config pyproject.toml poetry.lock .github skills agent CLAUDE.md PROJECT_CONTEXT.md \
  ROADMAP.md results/INDEX.md docs/CODE_MAP.md docs/protocole_c3.md docs/amendements_c3_v2.1.md \
  docs/amendements_c3_v2.2.md docs/amendements_c3_v2.3.md docs/CONTRAINTES_POST_B4.md docs/rejeu_grid_prespec.md \
  results/rejeu_grid_report.md results/c3_racine_registre results/c3_outillage_v2_3 results/c3_v2_3_gel \
  results/c3_outillage_v2_2 results/c3_v2_2 results/c3b_producteur results/c3_campagne_grid

# 2. protocole gelé
current=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
consigned=$(sed -n '/^## Adoption/,/^## AM-00/p' "$PACKAGE" | grep -E '^\*\*sha256 v[0-9]+\.[0-9]+ :\*\*' | tail -n 1 \
  | grep -oE '[0-9a-f]{64}')
if [ -n "$consigned" ] && [ "$current" = "$consigned" ]; then
  echo "protocole_sha_egal_consigne=0 (${current:0:16}…)" >> "$OUT"
else
  echo "protocole_sha_egal_consigne=1 (recalculé ${current:0:16}…, consigné ${consigned:0:16}…)" >> "$OUT"; rc=1
fi

# 3. liste blanche ; le brief et le brouillon jamais suivis ni indexés
ALLOW='^(results/c3_campagne_grid_v2/.+|docs/RESEARCH_LOG\.md)$'
CHANGED=$( { git diff --name-only "$BASE" HEAD; git diff --cached --name-only "$BASE"; git diff --name-only "$BASE";
  untracked_except .; } | LC_ALL=C sort -u)
echo "## fichiers changés depuis la base (HEAD ∪ index ∪ arbre ∪ non suivis, brief et brouillon exceptés)" >> "$OUT"
printf '%s\n' "$CHANGED" | grep . | sed 's/^/  /' >> "$OUT"
outside=$(printf '%s\n' "$CHANGED" | grep . | grep -vE "$ALLOW")
if [ -n "$outside" ]; then
  while IFS= read -r f; do echo "hors_liste_blanche $f" >> "$OUT"; done <<< "$outside"
  echo "liste_blanche=1" >> "$OUT"; rc=1
else
  echo "liste_blanche=0" >> "$OUT"
fi
tracked=0
for f in "$BRIEF" "$DRAFT"; do
  if git ls-files --error-unmatch -- "$f" > /dev/null 2>&1; then echo "suivi_interdit $f" >> "$OUT"; tracked=1; fi
done
echo "brief_et_brouillon_non_suivis=$tracked" >> "$OUT"
[ "$tracked" = "0" ] || rc=1
echo "## fichiers du commit courant (index contre HEAD)" >> "$OUT"
git diff --cached --name-status HEAD | sed 's/^/  /' >> "$OUT"
echo "arbre_hors_index=$(git diff --name-only | wc -l | tr -d ' ') fichier(s) suivi(s) modifiés non indexés" >> "$OUT"

# 4. le journal en ajout seul (git diff --numstat : colonne des lignes retirées, commits, index et arbre)
removed=$( { git diff --numstat "$BASE" HEAD -- docs/RESEARCH_LOG.md; git diff --cached --numstat "$BASE" -- docs/RESEARCH_LOG.md;
  git diff --numstat "$BASE" -- docs/RESEARCH_LOG.md; } | awk '{s += $2} END {print s + 0}')
if [ "$removed" = "0" ]; then
  echo "journal_ajout_seul=0" >> "$OUT"
else
  echo "journal_ajout_seul=1 (lignes retirées ou modifiées : $removed)" >> "$OUT"; rc=1
fi

# 5. chemin sélection, archives ; CAMPAIGN_UNLOCK absent en local
ARTEFACT='(^|/)((variants|evaluation[a-z_]*|benchmark[a-z_]*|candles[a-z_]*|selection|verdict|continuity|anchor|entry|observations|coverage|prefix_run|manifest[a-z_]*)\.(json|md)|[^/]*\.tgz|[^/]*\.tgz\.sha256)$'
ALL_CHANTIER=$( { git ls-files -- "$CH"; git ls-files --others --exclude-standard -- "$CH"; } | LC_ALL=C sort -u)
artefacts=$(printf '%s\n' "$ALL_CHANTIER" | grep -E "$ARTEFACT" | grep -vxF "$CH/manifest.json")
if [ -n "$artefacts" ]; then
  while IFS= read -r f; do echo "artefact_versionne $f" >> "$OUT"; done <<< "$artefacts"
  echo "aucun_artefact=1" >> "$OUT"; rc=1
else
  echo "aucun_artefact=0" >> "$OUT"
fi
UNLOCK=results/c3b_producteur/CAMPAIGN_UNLOCK
if [ -e "$UNLOCK" ] || git cat-file -e "HEAD:$UNLOCK" 2> /dev/null; then
  echo "campaign_unlock_local=1 (présent)" >> "$OUT"; rc=1
else
  echo "campaign_unlock_local=0 (absent)" >> "$OUT"
fi

# 6. règle 64 hex
FOUND=$(mktemp); SAFE=$(mktemp)
{ git log -p --format= "$BASE"..HEAD | grep -E '^\+'; git diff "$BASE" | grep -E '^\+';
  git diff --cached "$BASE" | grep -E '^\+'; git ls-files --others --exclude-standard -z | xargs -0 cat 2> /dev/null; } \
  | grep -oE '[0-9a-f]{64}' | LC_ALL=C sort -u > "$FOUND"
{
  printf '%s\n' "$ALL_CHANTIER" | grep . | while IFS= read -r f; do [ -f "$f" ] && shasum -a 256 "$f" | cut -d' ' -f1; done
  echo "$MANIFEST_SHA"
  echo "$PARENT_KEY"
} | LC_ALL=C sort -u > "$SAFE"
python3 - "$FOUND" "$SAFE" "$PACKAGE" >> "$OUT" <<'PY'
import re, sys
found = set(open(sys.argv[1]).read().split())
safe = set(open(sys.argv[2]).read().split())
try:
    text = open(sys.argv[3], encoding="utf-8").read()
    section = text.split("## Adoption", 1)[1].split("\n## ", 1)[0]
    table = set(re.findall(r"^\| v\d+\.\d+[^|]*\| `([0-9a-f]{64})` \|", section, re.MULTILINE))
except (OSError, IndexError):
    table = set()
extra = sorted(found - table - safe)
print(
    f"empreintes_64_ajoutees={len(found)} dont_protocole={len(found & table)} "
    f"dont_fichiers_du_chantier_ou_gel={len((found - table) & safe)} table_adoption={len(table)}"
)
for h in extra:
    print(f"empreinte_hors_regle {h[:16]}…")
print(f"aucun_sha_hors_regle={0 if not extra else 1}")
PY
grep -q '^aucun_sha_hors_regle=0$' "$OUT" || rc=1
rm -f "$FOUND" "$SAFE"

# 7. dette 23 : le mot est construit ici
W=$(printf 'dock%s' er)
named=$(find "$CH" -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits.sh ! -name interdits_adverse.sh -print0 \
  | xargs -0 grep -il "$W" 2> /dev/null)
if [ -n "$named" ]; then
  while IFS= read -r f; do echo "nomme_dette23 $f" >> "$OUT"; done <<< "$named"
  echo "dette23=1" >> "$OUT"; rc=1
else
  echo "dette23=0" >> "$OUT"
fi

# 8. registre de campagne (chemin construit ici) : les deux seules lignes `--registry` du pilote
C3=$(printf 'c%s' 3)
REG_FULL="/home/bruno/${C3}/regis$(printf 'try')/variants.json"
REG_PAT="(~|\\\$HOME|\\\$\\{HOME\\}|home/[a-z]+)/${C3}(/|\$|[^_a-z0-9])|${C3}/regis$(printf 'try')"
hits=$(find "$CH" -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits.sh ! -name interdits_adverse.sh -print0 \
  | xargs -0 grep -nE "$REG_PAT" 2> /dev/null)
allowed=0
bad=0
while IFS= read -r hit; do
  [ -z "$hit" ] && continue
  file=${hit%%:*}
  rest=${hit#*:}
  content=${rest#*:}
  n_pat=$(printf '%s\n' "$content" | grep -oE "$REG_PAT" | wc -l | tr -d ' ')
  if [ "$file" = "$PILOT" ] && [ "$n_pat" = "1" ] \
    && { [[ "$content" == *"--registry ${REG_FULL} "* ]] || [[ "$content" == *"--registry ${REG_FULL}" ]]; }; then
    allowed=$((allowed + 1))
  else
    bad=$((bad + 1))
    echo "nomme_registre_campagne ${file}:${rest%%:*}" >> "$OUT"
  fi
done <<< "$hits"
if [ -f "$PILOT" ]; then want=2; else want=0; fi
echo "registre_lignes_admises=$allowed attendu=$want hors_admis=$bad" >> "$OUT"
if [ "$allowed" != "$want" ] || [ "$bad" != "0" ]; then
  echo "registre_campagne_non_nomme=1" >> "$OUT"; rc=1
else
  echo "registre_campagne_non_nomme=0" >> "$OUT"
fi
if [ -e "$HOME/$C3" ]; then
  echo "registre_campagne_absent_local=1 (le répertoire existe sous \$HOME)" >> "$OUT"; rc=1
else
  echo "registre_campagne_absent_local=0" >> "$OUT"
fi

echo "rc=$rc" >> "$OUT"
exit $rc
