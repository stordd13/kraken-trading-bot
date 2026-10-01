#!/bin/bash
# C3 racine du registre — interdits du brief (§ 3.3, § 6) et du runbook (§ 4), lancé par `bash` AVANT chaque commit
# (fichiers indexés) et au tip. Repris de results/c3_outillage_v2_3/tests/interdits.sh (base, listes, règle 64 hex du
# plan D10, contrôles du runbook) ; reprise comptée dans reprise_lot1.out.
# Usage : bash interdits.sh <étiquette>. Sortie : interdits_<étiquette>.out. rc=0 ssi :
#  1. chemins gelés : aucun écart contre 313eb00 au commit (HEAD), à l'index ni dans l'arbre, aucun fichier non suivi ;
#  2. le protocole est gelé : sha256 recalculé de docs/protocole_c3.md = la dernière ligne `**sha256 vX.Y :**` de la
#     section « Adoption » du paquet v2.3 (lue, jamais écrite ici) ;
#  3. liste blanche du lot 1 (plan § 5) : tout fichier changé depuis 313eb00 (HEAD, index, arbre, non suivis) est
#     c3_anchor.py, l'un des trois fichiers de test, le runbook (skills/registry.md), le brief, ou sous
#     results/c3_racine_registre/ ;
#  4. aucun artefact du chemin sélection sous results/c3_racine_registre/, CAMPAIGN_UNLOCK absent (arbre et HEAD) ;
#  5. règle 64 hex (plan D10) : toute empreinte de 64 hex ajoutée est l'une des empreintes du protocole consignées à la
#     table « Adoption » du paquet v2.3, ou le sha256 d'un fichier du chantier (results/c3_racine_registre/**,
#     skills/registry.md, le brief) ;
#  6. aucun script ni vérificateur du chantier ne nomme le répertoire de la dette 23 (ce fichier-ci excepté) ;
#  7. runbook § 4 et brief § 6 : aucun script ni vérificateur du chantier, ni le module ou les tests touchés, ne nomme
#     le chemin du registre de campagne (motifs construits ici, ce fichier-ci excepté) ; ce répertoire n'existe pas sous
#     le $HOME local (jamais créé).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
BASE=313eb00c2019b98cf20fb81ac8327f7b9d1e920a
CH=results/c3_racine_registre
DIR=$CH/tests
OUT="$DIR/interdits_${LABEL}.out"
PACKAGE=docs/amendements_c3_v2.3.md
BRIEF=agent/AGENT_C3_RACINE_REGISTRE.md
RUNBOOK=skills/registry.md
{
  echo "# interdits — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current) ; base $BASE"
} > "$OUT"
rc=0

# 1. chemins gelés
FROZEN=(src config pyproject.toml poetry.lock .github scripts/backtest.py scripts/run_p6_backtests.py
  scripts/run_p7_grid_search.py scripts/audit/_common.py scripts/audit/rejeu_common.py scripts/audit/c3b_common.py
  scripts/audit/c3b_prefix.py scripts/audit/c3b_evaluate.py scripts/audit/c3_common.py scripts/audit/c3_verdict.py
  scripts/audit/c3_entry.py scripts/audit/c3_benchmark.py scripts/audit/c3_select.py scripts/audit/c3_continuity.py
  docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md docs/amendements_c3_v2.3.md
  docs/CONTRAINTES_POST_B4.md CLAUDE.md results/c3_v2_2 results/c3b_producteur results/c3_outillage_v2_2
  results/c3_v2_3_gel results/c3_outillage_v2_3)
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
ALLOW='^(scripts/audit/c3_anchor\.py|tests/test_scripts/test_c3_(common|anchor|verdict)\.py|skills/registry\.md|agent/AGENT_C3_RACINE_REGISTRE\.md|results/c3_racine_registre/.+)$'
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
[ -f "$BRIEF" ] && echo "brief $BRIEF sha256_16=$(shasum -a 256 "$BRIEF" | cut -c1-16)" >> "$OUT"
[ -f "$RUNBOOK" ] && echo "runbook $RUNBOOK sha256_16=$(shasum -a 256 "$RUNBOOK" | cut -c1-16)" >> "$OUT"

# 4. chemin sélection
ARTEFACT='(^|/)((variants|evaluation[a-z_]*|benchmark[a-z_]*|candles[a-z_]*|selection|verdict|continuity|anchor|entry|observations|coverage|prefix_run|manifest[a-z_]*)\.(json|md)|[^/]*\.tgz)$'
artefacts=$(printf '%s\n' "$CHANGED" | grep "^$CH/" | grep -E "$ARTEFACT")
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

# 5. empreintes de 64 hex ajoutées ⊆ empreintes du protocole ∪ sha256 des fichiers du chantier (D10)
TMP=$(mktemp)
OWN=$(mktemp)
{ git diff "$BASE" | grep -E '^\+' ; git ls-files --others --exclude-standard -z | xargs -0 cat 2> /dev/null; } \
  | grep -oE '[0-9a-f]{64}' | LC_ALL=C sort -u > "$TMP"
{ find "$CH" -type f -print0 | xargs -0 shasum -a 256 2> /dev/null
  for f in "$RUNBOOK" "$BRIEF"; do [ -f "$f" ] && shasum -a 256 "$f"; done; } | cut -d' ' -f1 | LC_ALL=C sort -u > "$OWN"
python3 - "$TMP" "$PACKAGE" "$OWN" >> "$OUT" <<'PY'
import re, sys
found = set(open(sys.argv[1]).read().split())
own = set(open(sys.argv[3]).read().split())
try:
    text = open(sys.argv[2], encoding="utf-8").read()
    section = text.split("## Adoption", 1)[1].split("\n## ", 1)[0]
    allowed = set(re.findall(r"^\| v\d+\.\d+[^|]*\| `([0-9a-f]{64})` \|", section, re.MULTILINE))
except (OSError, IndexError):
    allowed = set()
extra = sorted(found - allowed - own)
print(
    f"empreintes_64_ajoutees={len(found)} dont_protocole={len(found & allowed)} "
    f"dont_fichiers_du_chantier={len((found - allowed) & own)} table_adoption={len(allowed)}"
)
for h in extra:
    print(f"empreinte_hors_regle {h[:16]}…")
print(f"aucun_sha_artefact={0 if not extra else 1}")
PY
grep -q '^aucun_sha_artefact=0$' "$OUT" || rc=1
rm -f "$TMP" "$OWN"

# 6. dette 23 : aucun script ni vérificateur du chantier ne nomme le répertoire (ce fichier-ci excepté)
W=$(printf 'dock%s' er)
named=$(find "$CH" -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits.sh -print0 \
  | xargs -0 grep -il "$W" 2> /dev/null)
if [ -n "$named" ]; then
  while IFS= read -r f; do echo "nomme_dette23 $f" >> "$OUT"; done <<< "$named"
  echo "dette23=1" >> "$OUT"; rc=1
else
  echo "dette23=0" >> "$OUT"
fi

# 7. registre de campagne (runbook § 4, brief § 6) : jamais nommé par un script du chantier, jamais créé localement
C3=$(printf 'c%s' 3)
REG_PAT="(~|\\\$HOME|\\\$\\{HOME\\}|home/[a-z]+)/${C3}(/|\$|[^_a-z0-9])|${C3}/regis$(printf 'try')"
named=$( { find "$CH" -type f \( -name '*.sh' -o -name '*.py' \) ! -name interdits.sh -print0
  printf '%s\0' scripts/audit/c3_anchor.py tests/test_scripts/test_c3_common.py tests/test_scripts/test_c3_anchor.py \
    tests/test_scripts/test_c3_verdict.py; } | xargs -0 grep -lE "$REG_PAT" 2> /dev/null)
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
