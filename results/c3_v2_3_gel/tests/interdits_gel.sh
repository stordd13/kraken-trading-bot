#!/bin/bash
# C3 gel v2.3 — interdits du brief (§ 3.4, § 5), lancé par `bash` depuis le dépôt AVANT chaque commit (fichiers
# indexés) et au tip. Usage : bash interdits_gel.sh <étiquette>. Sortie : interdits_gel_<étiquette>.out.
# rc=0 ssi :
#  1. chemins gelés : aucun écart contre 662c104 au commit (HEAD), à l'index ni dans l'arbre, aucun fichier non suivi ;
#  2. liste blanche : tout fichier changé depuis 662c104 (HEAD, index, arbre, non suivis) est un fichier des § 3.2-3.4
#     du brief, étendue par le GO du 30/09 aux deux fichiers agent/ commités tels que reçus ;
#  3. aucun artefact du chemin sélection sous results/c3_v2_3_gel/, CAMPAIGN_UNLOCK absent (arbre et HEAD) ;
#  4. aucun sha d'artefact versionné : toute empreinte de 64 hex ajoutée (lignes + du diff, fichiers non suivis) est
#     l'une des quatre empreintes du protocole consignées à la table « Adoption » du paquet v2.3.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=662c104ef8cb5a9b5c7fb04452f7af817cb5a87a
DIR=results/c3_v2_3_gel/tests
OUT="$DIR/interdits_gel_${LABEL}.out"
{
  echo "# interdits_gel — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
rc=0

# 1. chemins gelés
FROZEN=(src scripts config pyproject.toml poetry.lock .github results/c3b_producteur results/c3_outillage_v2_2
  results/c3_v2_2)
for p in "${FROZEN[@]}"; do
  git diff --quiet "$BASE" HEAD -- "$p"; h=$?
  git diff --quiet --cached "$BASE" -- "$p"; i=$?
  git diff --quiet "$BASE" -- "$p"; w=$?
  u=$(git ls-files --others --exclude-standard -- "$p" | wc -l | tr -d ' ')
  echo "gele $p head=$h index=$i arbre=$w non_suivis=$u" >> "$OUT"
  { [ $h -ne 0 ] || [ $i -ne 0 ] || [ $w -ne 0 ] || [ "$u" != "0" ]; } && rc=1
done

# 2. liste blanche
ALLOW='^(docs/protocole_c3\.md|docs/amendements_c3_v2\.3\.md|docs/CONTRAINTES_POST_B4\.md|docs/RESEARCH_LOG\.md|skills/backtest\.md|CLAUDE\.md|tests/test_scripts/test_c3_(common|anchor|verdict)\.py|agent/AGENT_C3_GEL_V2_3\.md|agent/amendements_c3_v2_3_draft\.md|results/c3_v2_3_gel/.+)$'
CHANGED=$( { git diff --name-only "$BASE" HEAD; git diff --cached --name-only "$BASE"; git diff --name-only "$BASE";
  git ls-files --others --exclude-standard; } | LC_ALL=C sort -u)
echo "## fichiers changés depuis la base (HEAD ∪ index ∪ arbre ∪ non suivis)" >> "$OUT"
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
for f in agent/AGENT_C3_GEL_V2_3.md agent/amendements_c3_v2_3_draft.md; do
  [ -f "$f" ] && echo "agent $f sha256_16=$(shasum -a 256 "$f" | cut -c1-16)" >> "$OUT"
done

# 3. chemin sélection
ARTEFACT='(^|/)((variants|evaluation[a-z_]*|benchmark[a-z_]*|candles[a-z_]*|selection|verdict|continuity|anchor|entry|observations|coverage|prefix_run|manifest[a-z_]*)\.(json|md)|[^/]*\.tgz)$'
artefacts=$(printf '%s\n' "$CHANGED" | grep '^results/c3_v2_3_gel/' | grep -E "$ARTEFACT")
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

# 4. empreintes de 64 hex ajoutées ⊆ empreintes du protocole
TMP=$(mktemp)
{ git diff "$BASE" | grep -E '^\+' ; git ls-files --others --exclude-standard -z | xargs -0 cat 2> /dev/null; } \
  | grep -oE '[0-9a-f]{64}' | LC_ALL=C sort -u > "$TMP"
python3 - "$TMP" docs/amendements_c3_v2.3.md >> "$OUT" <<'PY'
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

echo "rc=$rc" >> "$OUT"
exit $rc
