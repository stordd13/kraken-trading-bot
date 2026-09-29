#!/bin/bash
# C3 outillage v2.2 — liste des interdits du brief : aucun changement contre 8c114fe sur les chemins gelés.
# Lot 3 (plans/lot3.md § 7) : bloc de plus contre 5f61ac9, tip du lot 2 — aucun code (le lot n'en écrit pas), fichiers
# changés dans la liste blanche, aucun artefact du chemin versionné, CAMPAIGN_UNLOCK absent, aucun script du lot qui
# nomme docker (dette 23).
# Usage : bash interdits.sh <étiquette>. Sortie : interdits_<étiquette>.out ; rc=0 ssi tout tient (arbre de travail,
# index et fichiers non suivis compris).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=8c114fe
LOT3=5f61ac928ef4edf914b863d300a5d0859d028f99
OUT=results/c3_outillage_v2_2/tests/interdits_${LABEL}.out
PATHS=(src scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py
  scripts/audit/rejeu_common.py docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md
  results/c3_v2_2 results/c3b_producteur)
{
  echo "# interdits — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE ; lot 3 depuis $LOT3"
} > "$OUT"
rc=0
for p in "${PATHS[@]}"; do
  git diff --quiet "$BASE" -- "$p"; a=$?
  git diff --quiet --cached -- "$p"; b=$?
  echo "diff_vide $p commit=$a index=$b" >> "$OUT"
  { [ $a -ne 0 ] || [ $b -ne 0 ]; } && rc=1
done

# --- lot 3 : aucun code, rien hors de la liste close ------------------------------------------------------------
LOT3_PATHS=(scripts tests src config pyproject.toml poetry.lock .github agent skills CLAUDE.md
  docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md docs/CONTRAINTES_POST_B4.md
  results/c3_v2_2 results/c3b_producteur)
for p in "${LOT3_PATHS[@]}"; do
  git diff --quiet "$LOT3" -- "$p"; a=$?
  git diff --quiet --cached -- "$p"; b=$?
  u=$(git ls-files --others --exclude-standard -- "$p" | wc -l | tr -d ' ')
  echo "lot3_diff_vide $p depuis=$a index=$b non_suivis=$u" >> "$OUT"
  { [ $a -ne 0 ] || [ $b -ne 0 ] || [ "$u" != "0" ]; } && rc=1
done

# fichiers changés depuis 5f61ac9 (suivis) et fichiers non suivis : liste blanche du lot 3
ALLOW='^(results/c3_outillage_v2_2/|docs/RESEARCH_LOG\.md$|PROJECT_CONTEXT\.md$|results/INDEX\.md$)'
CHANGED=$( { git diff --name-only "$LOT3"; git ls-files --others --exclude-standard; } | LC_ALL=C sort -u)
n_changed=$(printf '%s\n' "$CHANGED" | grep -c . )
outside=$(printf '%s\n' "$CHANGED" | grep . | grep -vE "$ALLOW")
echo "lot3_fichiers_changes=$n_changed" >> "$OUT"
if [ -n "$outside" ]; then
  while IFS= read -r f; do echo "lot3_hors_liste_blanche $f" >> "$OUT"; done <<< "$outside"
  echo "lot3_liste_blanche=1" >> "$OUT"
  rc=1
else
  echo "lot3_liste_blanche=0" >> "$OUT"
fi

# aucun artefact du chemin (producteurs, chaîne, registre, archive) versionné sous le répertoire du chantier
ARTEFACT='(^|/)((variants|evaluation[a-z_]*|benchmark[a-z_]*|candles[a-z_]*|selection|verdict|continuity|anchor|entry|observations|coverage|prefix_run)\.(json|md)|[^/]*\.tgz)$'
artefacts=$(printf '%s\n' "$CHANGED" | grep '^results/c3_outillage_v2_2/' | grep -E "$ARTEFACT")
if [ -n "$artefacts" ]; then
  while IFS= read -r f; do echo "lot3_artefact_versionne $f" >> "$OUT"; done <<< "$artefacts"
  echo "lot3_aucun_artefact=1" >> "$OUT"
  rc=1
else
  echo "lot3_aucun_artefact=0" >> "$OUT"
fi

# CAMPAIGN_UNLOCK : ni dans l'arbre de travail, ni dans HEAD
UNLOCK=results/c3b_producteur/CAMPAIGN_UNLOCK
if [ -e "$UNLOCK" ] || git cat-file -e "HEAD:$UNLOCK" 2> /dev/null; then
  echo "lot3_campaign_unlock=present" >> "$OUT"
  rc=1
else
  echo "lot3_campaign_unlock=absent" >> "$OUT"
fi

# aucun script ni vérificateur du lot ne nomme docker (~/docker/ : dette 23) — ce fichier-ci excepté
docker=$(find results/c3_outillage_v2_2 -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits.sh -print0 \
  | xargs -0 grep -il docker 2> /dev/null)
if [ -n "$docker" ]; then
  while IFS= read -r f; do echo "lot3_nomme_docker $f" >> "$OUT"; done <<< "$docker"
  echo "lot3_docker=1" >> "$OUT"
  rc=1
else
  echo "lot3_docker=0" >> "$OUT"
fi

echo "rc=$rc" >> "$OUT"
exit $rc
