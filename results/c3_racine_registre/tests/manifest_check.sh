#!/bin/bash
# C3 racine du registre, lot 2 — le manifeste de conformité vérifié avant S1 (plans/lot2.md L2 ; repris de
# results/c3_outillage_v2_3/tests/manifest_check.sh, réécrit pour le delta de ce lot).
#  1. Chemins JSON changés contre le manifeste de la conformité v2.3 (results/c3_outillage_v2_3/conformite/manifest.json)
#     = exactement la liste déclarée : rien d'ajouté ; rien de retiré ; `research_log_entry`, `run_scope`, `variant_id`
#     réécrits (plan L2) ; et le texte ne diffère que sur ces trois lignes (même mise en forme).
#  2. `protocol_sha256` du manifeste = sha256 de docs/protocole_c3.md (v2.3).
#  3. `deferred_evaluation.date` − `window.end` : exactement 365 jours, inchangé (le bord admis de la borne, § A.6 v2.3).
#  4. `c3_anchor` en local — pur, sans base ; registre et sortie dans un répertoire temporaire hors du dépôt, supprimé
#     ensuite — code 0 (la date passe l'étape 1), et T = 2020-09-11T21:36:00+00:00, seul champ lu de sa sortie.
#  5. sha256 du manifeste, déclaré à l'attendu.
# Sortie : manifest_check.out, une ligne `clé=valeur` par fait, puis rc=0 ssi 1 à 4 tiennent.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_racine_registre/tests/manifest_check.out
NEW=results/c3_racine_registre/conformite/manifest.json
OLD=results/c3_outillage_v2_3/conformite/manifest.json
PROTOCOL_V23=d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6
EXPECTED_T=2020-09-11T21:36:00+00:00
NOW=2026-10-01T00:00:00+00:00
fail=0

: > "$OUT"
echo "# manifest_check — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
echo "manifest_sha256=$(shasum -a 256 "$NEW" | cut -d' ' -f1)" >> "$OUT"
echo "manifest_v23_sha256=$(shasum -a 256 "$OLD" | cut -d' ' -f1)" >> "$OUT"
echo "lignes_texte_changees=$(diff "$OLD" "$NEW" | grep -c '^>') (attendu 3)" >> "$OUT"
[ "$(diff "$OLD" "$NEW" | grep -c '^>')" = "3" ] && [ "$(diff "$OLD" "$NEW" | grep -c '^<')" = "3" ] || fail=1

# 1. chemins changés (clés seulement, jamais les valeurs), et 3. l'écart de la date
python3 - "$OLD" "$NEW" >> "$OUT" 2>&1 <<'PY'
from datetime import datetime
import json
import sys


def flatten(node, prefix=""):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            out.update(flatten(value, f"{prefix}.{key}" if prefix else key))
        return out
    return {prefix: node}


raw_new = json.load(open(sys.argv[2], encoding="utf-8"))
old = flatten(json.load(open(sys.argv[1], encoding="utf-8")))
new = flatten(raw_new)
seen = {
    "ajoute": sorted(set(new) - set(old)),
    "retire": sorted(set(old) - set(new)),
    "reecrit": sorted(k for k in set(old) & set(new) if old[k] != new[k]),
}
expected = {
    "ajoute": [],
    "retire": [],
    "reecrit": ["research_log_entry", "run_scope", "variant_id"],
}
for kind in ("ajoute", "retire", "reecrit"):
    print(f"chemins_{kind}={','.join(seen[kind]) or '-'}")
paths_ok = seen == expected
print(f"chemins_attendus={'0' if paths_ok else '1'}")
end = datetime.fromisoformat(raw_new["window"]["end"])
date = datetime.fromisoformat(raw_new["deferred_evaluation"]["date"])
days = (date - end).total_seconds() / 86400.0
gap_ok = days == 365.0
print(f"ecart_date_differee_jours={days:.6f} attendu=365.000000 ecart_ok={'0' if gap_ok else '1'}")
sys.exit(0 if paths_ok and gap_ok else 1)
PY
r=$?; echo "diff_manifeste_et_ecart=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1

# 2. sha du protocole
declared=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["protocol_sha256"])' "$NEW")
actual=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
if [ "$declared" = "$PROTOCOL_V23" ] && [ "$actual" = "$PROTOCOL_V23" ]; then r=0; else r=1; fail=1; fi
echo "protocole_v23=$r declare=${declared:0:16}… fichier=${actual:0:16}…" >> "$OUT"

# 4. c3_anchor local, hors dépôt
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
