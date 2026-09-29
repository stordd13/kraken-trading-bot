#!/bin/bash
# C3 v2.2, AM-12 — l'index du § M est celui que régénère index_m.py depuis le texte (méthode validée : elle
# reproduit l'index v2.1 au caractère près sur le texte v2.1, 8689636). Lancé par `bash` depuis le dépôt.
# Sortie : index_m.out ; rc=0 ssi aucune colonne de références vide, table du § M == régénération, et
# reproduction exacte de l'index v2.1 sur le texte v2.1.
set -o pipefail
set -u
unset VIRTUAL_ENV

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_v2_2/tests/index_m.out
TMP=$(mktemp -d)
rc=0
{
  echo "# index_m — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse --short HEAD) branche $(git branch --show-current)"
} > "$OUT"

extract() {
  python3 - "$1" <<'PY'
import sys
t = open(sys.argv[1], encoding="utf-8").read().split("## § M.", 1)[1]
print("\n".join(line for line in t.splitlines() if line.startswith("| `")))
PY
}

git show 8689636:docs/protocole_c3.md > "$TMP/v21.md"
python3 results/c3_v2_2/tests/index_m.py "$TMP/v21.md" > "$TMP/v21_regen.txt"
extract "$TMP/v21.md" > "$TMP/v21_table.txt"
if diff -q "$TMP/v21_table.txt" "$TMP/v21_regen.txt" > /dev/null; then v=0; else v=1; rc=1; fi
echo "methode_reproduit_v21=${v}" >> "$OUT"

python3 results/c3_v2_2/tests/index_m.py docs/protocole_c3.md > "$TMP/regen.txt"
py=$?
echo "aucune_colonne_vide=${py}" >> "$OUT"
[ "$py" -eq 0 ] || { rc=1; grep '^VIDE' "$TMP/regen.txt" >> "$OUT"; }
extract docs/protocole_c3.md > "$TMP/table.txt"
if diff "$TMP/table.txt" "$TMP/regen.txt" >> "$OUT"; then v=0; else v=1; rc=1; fi
echo "table_M_egale_regeneration=${v}" >> "$OUT"
echo "## écart à l'index v2.1 (diff v2.1 → v2.2)" >> "$OUT"
diff "$TMP/v21_table.txt" "$TMP/table.txt" >> "$OUT"
rm -rf "$TMP"
echo "rc=${rc}" >> "$OUT"
exit "$rc"
