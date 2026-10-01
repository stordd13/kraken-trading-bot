#!/bin/bash
# C3 racine du registre, lot 2 — interdits du brief (§ 4, § 6), du runbook (§ 4) et du plan du lot 2 (plans/lot2.md),
# lancé par `bash` AVANT chaque commit (fichiers indexés) et au tip. Repris de
# results/c3_outillage_v2_3/tests/interdits_lot2.sh, avec les contrôles du lot 1 de ce chantier (tests/interdits.sh,
# qui reste tel quel) ; reprise comptée dans reprise_lot2.out.
# Usage : bash interdits_lot2.sh <étiquette>. Sortie : interdits_lot2_<étiquette>.out. rc=0 ssi :
#  1. chemins gelés contre 313eb00 (base du chantier) : intacts au commit, à l'index, dans l'arbre, aucun non suivi ;
#  2. le lot 2 n'écrit aucun code : diff vide contre 56c65aa (tip du lot 1) sur le code, les tests, la configuration,
#     les docs gelées, les répertoires clos et le livrable du lot 1 ;
#  3. le protocole est gelé : sha256 recalculé = dernière ligne `**sha256 vX.Y :**` de l'Adoption du paquet v2.3 ;
#  4. liste blanche du lot 2 : tout fichier changé depuis 56c65aa est sous results/c3_racine_registre/ ou est
#     docs/RESEARCH_LOG.md ;
#  5. aucun artefact du chemin sélection sous results/c3_racine_registre/ (`conformite/manifest.json` excepté par son
#     nom exact), CAMPAIGN_UNLOCK absent (arbre et HEAD) ;
#  6. règle 64 hex du lot 2 (plans/lot2.md § 2) : toute empreinte de 64 hex ajoutée depuis 313eb00 est une empreinte du
#     protocole (table d'Adoption), le sha256 d'un fichier du chantier (results/c3_racine_registre/**, suivi ou non,
#     skills/registry.md, le brief), celui du manifeste v2.3 comparé, ou le sha d'une archive consigné dans un
#     `*.tgz.sha256` du chantier — jamais le sha d'un artefact du chemin ;
#  7. aucun script ni vérificateur du chantier ne nomme le répertoire de la dette 23 (ce fichier-ci excepté) ;
#  8. runbook § 4, brief § 6 : aucun script ni vérificateur du chantier ne nomme le chemin du registre de campagne
#     (motifs construits ici, ce fichier-ci et tests/interdits.sh exceptés) ; ce répertoire n'existe pas sous le $HOME
#     local.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=313eb00c2019b98cf20fb81ac8327f7b9d1e920a
LOT1=56c65aaf8d14e6c70a4dcc66f321a83bb785d817
CH=results/c3_racine_registre
DIR=$CH/tests
OUT="$DIR/interdits_lot2_${LABEL}.out"
PACKAGE=docs/amendements_c3_v2.3.md
BRIEF=agent/AGENT_C3_RACINE_REGISTRE.md
RUNBOOK=skills/registry.md
V23_MANIFEST=results/c3_outillage_v2_3/conformite/manifest.json
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
  scripts/run_p7_grid_search.py scripts/audit/_common.py scripts/audit/rejeu_common.py scripts/audit/c3b_common.py \
  scripts/audit/c3b_prefix.py scripts/audit/c3b_evaluate.py scripts/audit/c3_common.py scripts/audit/c3_verdict.py \
  scripts/audit/c3_entry.py scripts/audit/c3_benchmark.py scripts/audit/c3_select.py scripts/audit/c3_continuity.py \
  docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md docs/amendements_c3_v2.3.md \
  docs/CONTRAINTES_POST_B4.md CLAUDE.md results/c3_v2_2 results/c3b_producteur results/c3_outillage_v2_2 \
  results/c3_v2_3_gel results/c3_outillage_v2_3

# 2. le lot 2 n'écrit aucun code, ne touche aucune doc gelée ni le livrable clos du lot 1
frozen gele_lot2 "$LOT1" scripts tests src config pyproject.toml poetry.lock .github agent skills CLAUDE.md \
  PROJECT_CONTEXT.md results/INDEX.md docs/CODE_MAP.md docs/protocole_c3.md docs/amendements_c3_v2.1.md \
  docs/amendements_c3_v2.2.md docs/amendements_c3_v2.3.md docs/CONTRAINTES_POST_B4.md results/c3_v2_2 \
  results/c3b_producteur results/c3_outillage_v2_2 results/c3_v2_3_gel results/c3_outillage_v2_3 "$CH/lot1" \
  "$CH/plans/plan.md" "$CH/mutants.log"

# 3. protocole gelé
current=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
consigned=$(sed -n '/^## Adoption/,/^## AM-00/p' "$PACKAGE" | grep -E '^\*\*sha256 v[0-9]+\.[0-9]+ :\*\*' | tail -n 1 \
  | grep -oE '[0-9a-f]{64}')
if [ -n "$consigned" ] && [ "$current" = "$consigned" ]; then
  echo "protocole_sha_egal_consigne=0 (${current:0:16}…)" >> "$OUT"
else
  echo "protocole_sha_egal_consigne=1 (recalculé ${current:0:16}…, consigné ${consigned:0:16}…)" >> "$OUT"; rc=1
fi

# 4. liste blanche du lot 2
ALLOW='^(results/c3_racine_registre/.+|docs/RESEARCH_LOG\.md)$'
CHANGED=$( { git diff --name-only "$LOT1" HEAD; git diff --cached --name-only "$LOT1"; git diff --name-only "$LOT1";
  git ls-files --others --exclude-standard; } | LC_ALL=C sort -u)
echo "## fichiers changés depuis le lot 1 (HEAD ∪ index ∪ arbre ∪ non suivis)" >> "$OUT"
printf '%s\n' "$CHANGED" | grep . | sed 's/^/  /' >> "$OUT"
outside=$(printf '%s\n' "$CHANGED" | grep . | grep -vE "$ALLOW")
if [ -n "$outside" ]; then
  while IFS= read -r f; do echo "hors_liste_blanche $f" >> "$OUT"; done <<< "$outside"
  echo "liste_blanche=1" >> "$OUT"; rc=1
else
  echo "liste_blanche=0" >> "$OUT"
fi
echo "## fichiers du commit courant (index contre HEAD)" >> "$OUT"
git diff --cached --name-status HEAD | sed 's/^/  /' >> "$OUT"
echo "arbre_hors_index=$(git diff --name-only | wc -l | tr -d ' ') fichier(s) suivi(s) modifiés non indexés" >> "$OUT"

# 5. chemin sélection
ARTEFACT='(^|/)((variants|evaluation[a-z_]*|benchmark[a-z_]*|candles[a-z_]*|selection|verdict|continuity|anchor|entry|observations|coverage|prefix_run|manifest[a-z_]*)\.(json|md)|[^/]*\.tgz)$'
ALL_CHANTIER=$( { git ls-files -- "$CH"; git ls-files --others --exclude-standard -- "$CH"; } | LC_ALL=C sort -u)
artefacts=$(printf '%s\n' "$ALL_CHANTIER" | grep -E "$ARTEFACT" | grep -vxF "$CH/conformite/manifest.json")
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

# 6. règle 64 hex du lot 2
FOUND=$(mktemp); SAFE=$(mktemp)
{ git diff "$BASE" | grep -E '^\+' ; git ls-files --others --exclude-standard -z | xargs -0 cat 2> /dev/null; } \
  | grep -oE '[0-9a-f]{64}' | LC_ALL=C sort -u > "$FOUND"
{
  printf '%s\n' "$ALL_CHANTIER" | grep . | while IFS= read -r f; do [ -f "$f" ] && shasum -a 256 "$f" | cut -d' ' -f1; done
  for f in "$RUNBOOK" "$BRIEF" "$V23_MANIFEST"; do [ -f "$f" ] && shasum -a 256 "$f" | cut -d' ' -f1; done
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

# 7. dette 23 : le mot est construit ici
W=$(printf 'dock%s' er)
named=$(find "$CH" -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits_lot2.sh ! -name interdits.sh -print0 \
  | xargs -0 grep -il "$W" 2> /dev/null)
if [ -n "$named" ]; then
  while IFS= read -r f; do echo "nomme_dette23 $f" >> "$OUT"; done <<< "$named"
  echo "dette23=1" >> "$OUT"; rc=1
else
  echo "dette23=0" >> "$OUT"
fi

# 8. registre de campagne : jamais nommé par un script du chantier, jamais créé localement (chemin construit ici)
C3=$(printf 'c%s' 3)
REG_PAT="(~|\\\$HOME|\\\$\\{HOME\\}|home/[a-z]+)/${C3}(/|\$|[^_a-z0-9])|${C3}/regis$(printf 'try')"
named=$(find "$CH" -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits_lot2.sh ! -name interdits.sh -print0 \
  | xargs -0 grep -lE "$REG_PAT" 2> /dev/null)
if [ -n "$named" ]; then
  while IFS= read -r f; do echo "nomme_registre_campagne $f" >> "$OUT"; done <<< "$named"
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
