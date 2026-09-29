#!/bin/bash
# C3 outillage v2.2, lot 3 — le manifeste de conformité v2.2 vérifié avant S1 (plans/lot3.md § 4 item 2, § 7).
#  1. Chemins JSON changés contre le manifeste du 28/09 = exactement la liste déclarée : `family` et `min_order_quote`
#     ajoutés, `min_order_usdc` retiré, `protocol_sha256`, `research_log_entry`, `run_scope`, `variant_id` réécrits.
#  2. `protocol_sha256` du manifeste = sha256 de docs/protocole_c3.md (v2.2).
#  3. `c3_anchor` en local — pur, sans base ; registre et sortie dans un répertoire temporaire hors du dépôt, supprimé
#     ensuite — code 0, et T = 2020-09-11T21:36:00+00:00, seul champ lu de sa sortie.
#  4. sha256 du manifeste, déclaré à l'attendu.
# Sortie : manifest_check.out, une ligne `clé=valeur` par fait, puis rc=0 ssi 1 à 3 tiennent.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_outillage_v2_2/tests/manifest_check.out
NEW=results/c3_outillage_v2_2/conformite/manifest.json
OLD=results/c3b_producteur/prefix_conformite/manifest.json
PROTOCOL_V22=1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a
EXPECTED_T=2020-09-11T21:36:00+00:00
NOW=2026-09-29T00:00:00+00:00
fail=0

: > "$OUT"
echo "# manifest_check — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
echo "manifest_sha256=$(shasum -a 256 "$NEW" | cut -d' ' -f1)" >> "$OUT"
echo "manifest_28_09_sha256=$(shasum -a 256 "$OLD" | cut -d' ' -f1)" >> "$OUT"

# 1. chemins changés (clés seulement, jamais les valeurs)
python3 - "$OLD" "$NEW" >> "$OUT" 2>&1 <<'PY'
import json
import sys


def flatten(node, prefix=""):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            out.update(flatten(value, f"{prefix}.{key}" if prefix else key))
        return out
    return {prefix: node}


old = flatten(json.load(open(sys.argv[1], encoding="utf-8")))
new = flatten(json.load(open(sys.argv[2], encoding="utf-8")))
seen = {
    "ajoute": sorted(set(new) - set(old)),
    "retire": sorted(set(old) - set(new)),
    "reecrit": sorted(k for k in set(old) & set(new) if old[k] != new[k]),
}
expected = {
    "ajoute": ["family", "min_order_quote"],
    "retire": ["min_order_usdc"],
    "reecrit": ["protocol_sha256", "research_log_entry", "run_scope", "variant_id"],
}
for kind in ("ajoute", "retire", "reecrit"):
    print(f"chemins_{kind}={','.join(seen[kind])}")
ok = seen == expected
print(f"chemins_attendus={'0' if ok else '1'}")
sys.exit(0 if ok else 1)
PY
r=$?; echo "diff_manifeste=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1

# 2. sha du protocole
declared=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["protocol_sha256"])' "$NEW")
actual=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
if [ "$declared" = "$PROTOCOL_V22" ] && [ "$actual" = "$PROTOCOL_V22" ]; then r=0; else r=1; fail=1; fi
echo "protocole_v22=$r declare=$declared fichier=$actual" >> "$OUT"

# 3. c3_anchor local, hors dépôt
TMP=$(mktemp -d) || exit 2
poetry run python scripts/audit/c3_anchor.py --manifest "$NEW" --registry "$TMP/variants.json" \
  --output "$TMP/anchor.json" --now "$NOW" > "$TMP/anchor.log" 2>&1
r=$?; echo "c3_anchor_local=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
T=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["anchor"])' "$TMP/anchor.json" 2>/dev/null)
if [ "$T" = "$EXPECTED_T" ]; then r=0; else r=1; fail=1; fi
echo "ancrage_T=$r T=${T:-absent} attendu=$EXPECTED_T" >> "$OUT"
rm -rf "$TMP"
[ ! -e "$TMP" ]; echo "temporaire_supprime=$?" >> "$OUT"

echo "rc=$fail" >> "$OUT"
exit $fail
