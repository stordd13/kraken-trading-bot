#!/bin/bash
# C3 v2.2 — contrôle d'un commit de documentation hors protocole (étapes A, G, H du plan) : aucun pytest.
# Lancé par `bash` depuis le dépôt, fichiers du commit INDEXÉS. Vérifie : le protocole n'a pas bougé depuis la
# base (tant que l'application n'a pas commencé) ou a le sha attendu passé en argument ; aucun fichier de code
# touché depuis 8689636 ; chaque fichier changé (commité ou indexé) appartient à la liste close du chantier ;
# le paquet porte ses rubriques. Sortie : pkg_check.out, une ligne `clé=code`, puis `rc=`.
# usage : bash pkg_check.sh [sha256 attendu du protocole]   (défaut : sha v2.1)
set -o pipefail
set -u

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=8689636
EXPECT=${1:-9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129}
OUT=results/c3_v2_2/tests/pkg_check.out
PKG=docs/amendements_c3_v2.2.md
ALLOWED_RE='^(agent/AGENT_C3_AMENDEMENT_V2_2\.md|docs/amendements_c3_v2\.2\.md|docs/protocole_c3\.md|results/c3_v2_2/.*|tests/test_scripts/test_c3(b)?_[a-z_]+\.py|CLAUDE\.md|skills/backtest\.md|docs/RESEARCH_LOG\.md|PROJECT_CONTEXT\.md|ROADMAP\.md|docs/CODE_MAP\.md|results/INDEX\.md)$'
FROZEN=(src scripts/audit scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py
  scripts/p7_grids.py scripts/compute_benchmarks.py config pyproject.toml poetry.lock
  results/c3a_entry_validation results/c3b_producteur docs/CONTRAINTES_POST_B4.md)
rc=0

{
  echo "# pkg_check — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse --short HEAD) branche $(git branch --show-current)"
} > "$OUT"

sha=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
if [ "$sha" = "$EXPECT" ]; then v=0; else v=1; rc=1; fi
echo "protocole_sha_attendu=${v} (${sha})" >> "$OUT"

if git diff --quiet "$BASE" -- "${FROZEN[@]}" && git diff --cached --quiet "$BASE" -- "${FROZEN[@]}"; then v=0; else v=1; rc=1; fi
echo "diff_vide_chemins_geles=${v}" >> "$OUT"

bad=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  if ! printf '%s\n' "$f" | grep -Eq "$ALLOWED_RE"; then
    echo "hors_liste ${f}" >> "$OUT"
    bad=1
  fi
done < <( { git diff --name-only "$BASE" HEAD; git diff --name-only --cached; } | sort -u )
[ "$bad" -eq 0 ] || rc=1
echo "fichiers_dans_liste_close=${bad}" >> "$OUT"

missing=0
if [ -f "$PKG" ]; then
  for h in "## AM-00" "## AM-01" "## AM-02" "## AM-03" "## AM-04" "## AM-05" "## AM-06" "## AM-07" "## AM-08" \
      "## AM-09" "## AM-10" "## AM-11" "## AM-12" "## Table de correspondance" "## Constats de rédaction" \
      "## Vérifié, sans amendement" "## Ordre d'application"; do
    if ! grep -q "^${h}" "$PKG"; then echo "rubrique_absente ${h}" >> "$OUT"; missing=1; fi
  done
else
  missing=1
fi
[ "$missing" -eq 0 ] || rc=1
echo "paquet_rubriques=${missing}" >> "$OUT"

echo "rc=${rc}" >> "$OUT"
exit "$rc"
