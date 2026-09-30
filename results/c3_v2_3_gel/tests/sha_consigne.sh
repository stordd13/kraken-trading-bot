#!/bin/bash
# C3 gel v2.3 — l'empreinte du protocole et ses consignations (brief § 3.4, § 4.2 ; R-01 de v2.1 : un fichier ne porte
# pas sa propre empreinte). Lancé par `bash` depuis le dépôt. Usage : bash sha_consigne.sh <étiquette>.
# Sortie : sha_consigne_<étiquette>.out. rc=0 ssi :
#  - sha256 recalculé du fichier == dernière ligne `**sha256 vX.Y :**` de la section « Adoption » du paquet v2.3, qui
#    en est la dernière ligne non vide, version v2.3 == dernière ligne de la table d'empreinte == protocol_descriptor ;
#  - la valeur figure dans docs/RESEARCH_LOG.md, skills/backtest.md et CLAUDE.md (les quatre consignations) ;
#  - ADOPTED_PACKAGE du test d'épinglage pointe sur le paquet v2.3 ; les deux tests d'épinglage passent.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
LABEL="${1:?étiquette}"
DIR=results/c3_v2_3_gel/tests
OUT="$DIR/sha_consigne_${LABEL}.out"
PKG=docs/amendements_c3_v2.3.md
LOG=$(mktemp)
{
  echo "# sha_consigne — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
rc=0
mark() { echo "$1=$2" >> "$OUT"; [ "$2" -eq 0 ] || rc=1; }

sha=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
echo "sha_fichier=$sha" >> "$OUT"
python3 - "$PKG" "$sha" >> "$OUT" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
section = text.split("## Adoption", 1)[1].split("\n## ", 1)[0]
lines = re.findall(r"\*\*sha256 v(\d+\.\d+) :\*\* `([0-9a-f]{64})`", section)
last_line = [l for l in section.splitlines() if l.strip()][-1]
table = re.findall(r"^\| (v\d+\.\d+)[^|]*\| `([0-9a-f]{64})` \|", section, re.MULTILINE)
version, value = lines[-1]
print(f"ligne_adoption=v{version} {value}")
print(f"table_adoption={[v for v, _ in table]}")
ok = (
    version == "2.3"
    and value == sys.argv[2]
    and last_line == f"**sha256 v2.3 :** `{value}`"
    and table[-1] == ("v2.3", value)
)
print(f"adoption_ligne_derniere_et_table={0 if ok else 1}")
PY
grep -q '^adoption_ligne_derniere_et_table=0$' "$OUT" || rc=1
desc=$(poetry run python -c "import sys; sys.path.insert(0, 'scripts/audit'); import c3_common as cc; print(cc.protocol_descriptor()['sha256'])" 2> /dev/null)
echo "sha_descripteur=$desc" >> "$OUT"
[ "$desc" = "$sha" ]; mark descripteur_egal $?
for f in "$PKG" docs/RESEARCH_LOG.md skills/backtest.md CLAUDE.md; do
  n=$(grep -c "$sha" "$f")
  echo "consignation $f occurrences=$n" >> "$OUT"
  [ "$n" -ge 1 ]; mark "consigne_$(basename "$f")" $?
done
pin=$(grep -E '^ADOPTED_PACKAGE = ' tests/test_scripts/test_c3_common.py)
echo "epinglage: $pin" >> "$OUT"
[ "$pin" = 'ADOPTED_PACKAGE = _project_root / "docs" / "amendements_c3_v2.3.md"' ]; mark adopted_package_v23 $?
poetry run pytest -q -p no:cacheprovider \
  "tests/test_scripts/test_c3_common.py::test_le_dernier_sha_consigne_hors_du_fichier_est_celui_du_protocole_livre" \
  "tests/test_scripts/test_c3_common.py::test_aucun_sha_de_protocole_n_est_ecrit_en_dur_dans_l_outillage_ni_les_tests" \
  > "$LOG" 2>&1; p=$?
echo "tests_epinglage=$(tail -n 1 "$LOG")" >> "$OUT"
mark tests_epinglage_verts "$p"
rm -f "$LOG"
echo "rc=$rc" >> "$OUT"
exit $rc
