#!/bin/bash
# C3 outillage v2.3 — interdits du brief (§ 3.2, § 6), lancé par `bash` AVANT chaque commit (fichiers indexés) et au
# tip. Repris de results/c3_v2_3_gel/tests/interdits_gel.sh et results/c3_outillage_v2_2/tests/interdits.sh.
# Usage : bash interdits.sh <étiquette>. Sortie : interdits_<étiquette>.out. rc=0 ssi :
#  1. chemins gelés : aucun écart contre b50f2d1 au commit (HEAD), à l'index ni dans l'arbre, aucun fichier non suivi ;
#  2. le protocole est gelé : sha256 recalculé de docs/protocole_c3.md = la dernière ligne `**sha256 vX.Y :**` de la
#     section « Adoption » du paquet v2.3 (lue, jamais écrite ici) ;
#  3. liste blanche du lot 1 (plan § 2) : tout fichier changé depuis b50f2d1 (HEAD, index, arbre, non suivis) est l'un
#     des trois modules, l'un des quatre fichiers de test, le brief, ou sous results/c3_outillage_v2_3/ ;
#     `gel_v2_3.patch` (racine, non suivi, pas à ce chantier) est exclu par son nom et doit rester inchangé ;
#  4. aucun artefact du chemin sélection sous results/c3_outillage_v2_3/, CAMPAIGN_UNLOCK absent (arbre et HEAD) ;
#  5. aucun sha d'artefact versionné : toute empreinte de 64 hex ajoutée est l'une des empreintes du protocole
#     consignées à la table « Adoption » du paquet v2.3 ;
#  6. aucun script ni vérificateur du chantier ne nomme le répertoire de la dette 23 (ce fichier-ci excepté).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9
DIR=results/c3_outillage_v2_3/tests
OUT="$DIR/interdits_${LABEL}.out"
PACKAGE=docs/amendements_c3_v2.3.md
FOREIGN=gel_v2_3.patch
FOREIGN_SHA16=1ffa3eec6e2d7051
{
  echo "# interdits — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
rc=0

# 1. chemins gelés
FROZEN=(src config pyproject.toml poetry.lock .github scripts/backtest.py scripts/run_p6_backtests.py
  scripts/run_p7_grid_search.py scripts/audit/rejeu_common.py scripts/audit/c3b_common.py scripts/audit/c3b_prefix.py
  scripts/audit/c3b_evaluate.py docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md
  docs/amendements_c3_v2.3.md results/c3_v2_2 results/c3b_producteur results/c3_outillage_v2_2 results/c3_v2_3_gel)
for p in "${FROZEN[@]}"; do
  git diff --quiet "$BASE" HEAD -- "$p"; h=$?
  git diff --quiet --cached "$BASE" -- "$p"; i=$?
  git diff --quiet "$BASE" -- "$p"; w=$?
  u=$(git ls-files --others --exclude-standard -- "$p" | wc -l | tr -d ' ')
  echo "gele $p head=$h index=$i arbre=$w non_suivis=$u" >> "$OUT"
  { [ $h -ne 0 ] || [ $i -ne 0 ] || [ $w -ne 0 ] || [ "$u" != "0" ]; } && rc=1
done

# 2. protocole gelé : sha recalculé = dernière ligne consignée du paquet
current=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
consigned=$(sed -n '/^## Adoption/,/^## AM-00/p' "$PACKAGE" | grep -E '^\*\*sha256 v[0-9]+\.[0-9]+ :\*\*' | tail -n 1 \
  | grep -oE '[0-9a-f]{64}')
if [ -n "$consigned" ] && [ "$current" = "$consigned" ]; then
  echo "protocole_sha_egal_consigne=0 (${current:0:16}…)" >> "$OUT"
else
  echo "protocole_sha_egal_consigne=1 (recalculé ${current:0:16}…, consigné ${consigned:0:16}…)" >> "$OUT"; rc=1
fi

# 3. liste blanche
ALLOW='^(scripts/audit/c3_(common|anchor|verdict)\.py|tests/test_scripts/test_c3_(common|anchor|verdict|entry)\.py|agent/AGENT_C3_OUTILLAGE_V2_3\.md|results/c3_outillage_v2_3/.+)$'
CHANGED=$( { git diff --name-only "$BASE" HEAD; git diff --cached --name-only "$BASE"; git diff --name-only "$BASE";
  git ls-files --others --exclude-standard; } | grep -vxF "$FOREIGN" | LC_ALL=C sort -u)
echo "## fichiers changés depuis la base (HEAD ∪ index ∪ arbre ∪ non suivis ; $FOREIGN exclu)" >> "$OUT"
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
elif [ -f "$FOREIGN" ] && [ "$(shasum -a 256 "$FOREIGN" | cut -c1-16)" = "$FOREIGN_SHA16" ]; then
  echo "etranger_inchange=0 ($FOREIGN non suivi, sha256_16 $FOREIGN_SHA16)" >> "$OUT"
else
  echo "etranger_inchange=1 ($FOREIGN absent ou modifié)" >> "$OUT"; rc=1
fi
echo "## fichiers du commit courant (index contre HEAD)" >> "$OUT"
git diff --cached --name-status HEAD | sed 's/^/  /' >> "$OUT"
echo "arbre_hors_index=$(git diff --name-only | wc -l | tr -d ' ') fichier(s) suivi(s) modifiés non indexés" >> "$OUT"
f=agent/AGENT_C3_OUTILLAGE_V2_3.md
[ -f "$f" ] && echo "brief $f sha256_16=$(shasum -a 256 "$f" | cut -c1-16)" >> "$OUT"

# 4. chemin sélection
ARTEFACT='(^|/)((variants|evaluation[a-z_]*|benchmark[a-z_]*|candles[a-z_]*|selection|verdict|continuity|anchor|entry|observations|coverage|prefix_run|manifest[a-z_]*)\.(json|md)|[^/]*\.tgz)$'
artefacts=$(printf '%s\n' "$CHANGED" | grep '^results/c3_outillage_v2_3/' | grep -E "$ARTEFACT")
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

# 5. empreintes de 64 hex ajoutées ⊆ empreintes du protocole
TMP=$(mktemp)
{ git diff "$BASE" | grep -E '^\+' ; git ls-files --others --exclude-standard -z | grep -zvxF "$FOREIGN" \
  | xargs -0 cat 2> /dev/null; } | grep -oE '[0-9a-f]{64}' | LC_ALL=C sort -u > "$TMP"
python3 - "$TMP" "$PACKAGE" >> "$OUT" <<'PY'
import re, sys
found = set(open(sys.argv[1]).read().split())
try:
    text = open(sys.argv[2], encoding="utf-8").read()
    section = text.split("## Adoption", 1)[1].split("\n## ", 1)[0]
    allowed = set(re.findall(r"^\| v\d+\.\d+[^|]*\| `([0-9a-f]{64})` \|", section, re.MULTILINE))
except (OSError, IndexError):
    allowed = set()
extra = sorted(found - allowed)
print(f"empreintes_64_ajoutees={len(found)} dont_protocole={len(found & allowed)} table_adoption={len(allowed)}")
for h in extra:
    print(f"empreinte_hors_protocole {h[:16]}…")
print(f"aucun_sha_artefact={0 if not extra else 1}")
PY
grep -q '^aucun_sha_artefact=0$' "$OUT" || rc=1
rm -f "$TMP"

# 6. dette 23 : aucun script ni vérificateur du chantier ne nomme le répertoire (ce fichier-ci excepté)
W=$(printf 'dock%s' er)
named=$(find results/c3_outillage_v2_3 -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits.sh -print0 \
  | xargs -0 grep -il "$W" 2> /dev/null)
if [ -n "$named" ]; then
  while IFS= read -r f; do echo "nomme_dette23 $f" >> "$OUT"; done <<< "$named"
  echo "dette23=1" >> "$OUT"; rc=1
else
  echo "dette23=0" >> "$OUT"
fi

echo "rc=$rc" >> "$OUT"
exit $rc
