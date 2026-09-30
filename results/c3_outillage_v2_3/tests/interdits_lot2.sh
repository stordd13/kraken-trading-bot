#!/bin/bash
# C3 outillage v2.3, lot 2 — interdits du brief (§ 4, § 6) et du plan du lot 2 (plans/lot2.md § 4, D3), lancé par
# `bash` AVANT chaque commit (fichiers indexés) et au tip. Dérivé de tests/interdits.sh (lot 1), qui reste tel quel.
# Usage : bash interdits_lot2.sh <étiquette>. Sortie : interdits_lot2_<étiquette>.out. rc=0 ssi :
#  1. chemins gelés contre b50f2d1 (lot 1) : intacts au commit, à l'index, dans l'arbre, aucun fichier non suivi ;
#  2. le lot 2 n'écrit aucun code : diff vide contre a30d62a (tip du lot 1) sur le code, les tests, la configuration,
#     les docs gelées, les répertoires clos et le livrable du lot 1 ;
#  3. le protocole est gelé : sha256 recalculé = dernière ligne `**sha256 vX.Y :**` de l'Adoption du paquet v2.3 ;
#  4. liste blanche du lot 2 : tout fichier changé depuis a30d62a est sous results/c3_outillage_v2_3/ ou est
#     docs/RESEARCH_LOG.md ; `gel_v2_3.patch` (pas à ce chantier) n'est jamais suivi, et inchangé s'il est présent
#     (constat du 30/09, G0 du lot 2 : absent, retiré hors de cette session) ;
#  5. aucun artefact du chemin sélection sous results/c3_outillage_v2_3/ (`conformite/manifest.json` excepté par son
#     nom exact), CAMPAIGN_UNLOCK absent (arbre et HEAD) ;
#  6. règle 64 hex du lot 2 (plan D3, valable pour ce lot seulement) : toute empreinte de 64 hex ajoutée depuis
#     b50f2d1 est soit une empreinte du protocole (table d'Adoption), soit le sha256 d'un fichier du chantier
#     (results/c3_outillage_v2_3/**, suivi ou non) ou du manifeste v2.2 comparé, soit le sha d'une archive consigné dans
#     un `*.tgz.sha256` du chantier — jamais le sha d'un artefact du chemin ;
#  7. aucun script ni vérificateur du chantier ne nomme le répertoire de la dette 23.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9
LOT1=a30d62a2fec51a4c277d51a5d20047892b2fbcca
DIR=results/c3_outillage_v2_3/tests
OUT="$DIR/interdits_lot2_${LABEL}.out"
PACKAGE=docs/amendements_c3_v2.3.md
FOREIGN=gel_v2_3.patch
FOREIGN_SHA16=1ffa3eec6e2d7051
{
  echo "# interdits_lot2 — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE ; lot 1 $LOT1"
} > "$OUT"
rc=0
frozen() {  # frozen <étiquette> <référence> <chemins…>
  local tag=$1 ref=$2
  shift 2
  local p h i w u
  for p in "$@"; do
    git diff --quiet "$ref" HEAD -- "$p"; h=$?
    git diff --quiet --cached "$ref" -- "$p"; i=$?
    git diff --quiet "$ref" -- "$p"; w=$?
    u=$(git ls-files --others --exclude-standard -- "$p" | wc -l | tr -d ' ')
    echo "$tag $p head=$h index=$i arbre=$w non_suivis=$u" >> "$OUT"
    { [ $h -ne 0 ] || [ $i -ne 0 ] || [ $w -ne 0 ] || [ "$u" != "0" ]; } && rc=1
  done
}

# 1. chemins gelés contre la base du chantier
frozen gele_base "$BASE" src config pyproject.toml poetry.lock .github scripts/backtest.py scripts/run_p6_backtests.py \
  scripts/run_p7_grid_search.py scripts/audit/rejeu_common.py scripts/audit/c3b_common.py scripts/audit/c3b_prefix.py \
  scripts/audit/c3b_evaluate.py docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md \
  docs/amendements_c3_v2.3.md results/c3_v2_2 results/c3b_producteur results/c3_outillage_v2_2 results/c3_v2_3_gel

# 2. le lot 2 n'écrit aucun code, ne touche aucune doc gelée ni le livrable clos du lot 1
frozen gele_lot2 "$LOT1" scripts tests src config pyproject.toml poetry.lock .github agent skills CLAUDE.md \
  PROJECT_CONTEXT.md results/INDEX.md docs/CODE_MAP.md docs/protocole_c3.md docs/amendements_c3_v2.1.md \
  docs/amendements_c3_v2.2.md docs/amendements_c3_v2.3.md docs/CONTRAINTES_POST_B4.md results/c3_v2_2 \
  results/c3b_producteur results/c3_outillage_v2_2 results/c3_v2_3_gel results/c3_outillage_v2_3/lot1 \
  results/c3_outillage_v2_3/plans/lot1.md results/c3_outillage_v2_3/mutants.log

# 3. protocole gelé
current=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
consigned=$(sed -n '/^## Adoption/,/^## AM-00/p' "$PACKAGE" | grep -E '^\*\*sha256 v[0-9]+\.[0-9]+ :\*\*' | tail -n 1 \
  | grep -oE '[0-9a-f]{64}')
if [ -n "$consigned" ] && [ "$current" = "$consigned" ]; then
  echo "protocole_sha_egal_consigne=0 (${current:0:16}…)" >> "$OUT"
else
  echo "protocole_sha_egal_consigne=1 (recalculé ${current:0:16}…, consigné ${consigned:0:16}…)" >> "$OUT"; rc=1
fi

# 4. liste blanche du lot 2, et le fichier étranger
ALLOW='^(results/c3_outillage_v2_3/.+|docs/RESEARCH_LOG\.md)$'
CHANGED=$( { git diff --name-only "$LOT1" HEAD; git diff --cached --name-only "$LOT1"; git diff --name-only "$LOT1";
  git ls-files --others --exclude-standard; } | grep -vxF "$FOREIGN" | LC_ALL=C sort -u)
echo "## fichiers changés depuis le lot 1 (HEAD ∪ index ∪ arbre ∪ non suivis ; $FOREIGN exclu)" >> "$OUT"
printf '%s\n' "$CHANGED" | grep . | sed 's/^/  /' >> "$OUT"
outside=$(printf '%s\n' "$CHANGED" | grep . | grep -vE "$ALLOW")
if [ -n "$outside" ]; then
  while IFS= read -r f; do echo "hors_liste_blanche $f" >> "$OUT"; done <<< "$outside"
  echo "liste_blanche=1" >> "$OUT"; rc=1
else
  echo "liste_blanche=0" >> "$OUT"
fi
if git ls-files --error-unmatch "$FOREIGN" > /dev/null 2>&1; then
  echo "etranger_suivi=1 ($FOREIGN est suivi : interdit)" >> "$OUT"; rc=1
elif [ ! -e "$FOREIGN" ]; then
  echo "etranger=absent (non suivi ; constat, pas un écart)" >> "$OUT"
elif [ "$(shasum -a 256 "$FOREIGN" | cut -c1-16)" = "$FOREIGN_SHA16" ]; then
  echo "etranger_inchange=0 ($FOREIGN non suivi, sha256_16 $FOREIGN_SHA16)" >> "$OUT"
else
  echo "etranger_inchange=1 ($FOREIGN modifié)" >> "$OUT"; rc=1
fi
echo "## fichiers du commit courant (index contre HEAD)" >> "$OUT"
git diff --cached --name-status HEAD | sed 's/^/  /' >> "$OUT"
echo "arbre_hors_index=$(git diff --name-only | wc -l | tr -d ' ') fichier(s) suivi(s) modifiés non indexés" >> "$OUT"

# 5. chemin sélection
ARTEFACT='(^|/)((variants|evaluation[a-z_]*|benchmark[a-z_]*|candles[a-z_]*|selection|verdict|continuity|anchor|entry|observations|coverage|prefix_run|manifest[a-z_]*)\.(json|md)|[^/]*\.tgz)$'
ALL_CHANTIER=$( { git ls-files -- results/c3_outillage_v2_3; git ls-files --others --exclude-standard -- results/c3_outillage_v2_3; } \
  | LC_ALL=C sort -u)
artefacts=$(printf '%s\n' "$ALL_CHANTIER" | grep -E "$ARTEFACT" | grep -vxF results/c3_outillage_v2_3/conformite/manifest.json)
if [ -n "$artefacts" ]; then
  while IFS= read -r f; do echo "artefact_versionne $f" >> "$OUT"; done <<< "$artefacts"
  echo "aucun_artefact=1" >> "$OUT"; rc=1
else
  echo "aucun_artefact=0" >> "$OUT"
fi
UNLOCK=results/c3b_producteur/CAMPAIGN_UNLOCK
if [ -e "$UNLOCK" ] || git cat-file -e "HEAD:$UNLOCK" 2> /dev/null; then
  echo "campaign_unlock=present" >> "$OUT"; rc=1
else
  echo "campaign_unlock=absent" >> "$OUT"
fi

# 6. règle 64 hex du lot 2 (D3)
FOUND=$(mktemp); SAFE=$(mktemp)
{ git diff "$BASE" | grep -E '^\+' ; git ls-files --others --exclude-standard -z | grep -zvxF "$FOREIGN" \
  | xargs -0 cat 2> /dev/null; } | grep -oE '[0-9a-f]{64}' | LC_ALL=C sort -u > "$FOUND"
{
  printf '%s\n' "$ALL_CHANTIER" | grep . | while IFS= read -r f; do [ -f "$f" ] && shasum -a 256 "$f" | cut -d' ' -f1; done
  shasum -a 256 results/c3_outillage_v2_2/conformite/manifest.json | cut -d' ' -f1
  printf '%s\n' "$ALL_CHANTIER" | grep -E '\.tgz\.sha256$' | while IFS= read -r f; do [ -f "$f" ] && cut -d' ' -f1 "$f"; done
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
    f"dont_fichiers_du_chantier_ou_archives={len((found - table) & safe)} table_adoption={len(table)}"
)
for h in extra:
    print(f"empreinte_hors_regle {h[:16]}…")
print(f"aucun_sha_artefact={0 if not extra else 1}")
PY
grep -q '^aucun_sha_artefact=0$' "$OUT" || rc=1
rm -f "$FOUND" "$SAFE"

# 7. dette 23 : le mot est construit ici, aucun fichier du chantier ne le porte
W=$(printf 'dock%s' er)
named=$(find results/c3_outillage_v2_3 -type f \( -name '*.sh' -o -name '*.py' \) -print0 | xargs -0 grep -il "$W" 2> /dev/null)
if [ -n "$named" ]; then
  while IFS= read -r f; do echo "nomme_dette23 $f" >> "$OUT"; done <<< "$named"
  echo "dette23=1" >> "$OUT"; rc=1
else
  echo "dette23=0" >> "$OUT"
fi

echo "rc=$rc" >> "$OUT"
exit $rc
