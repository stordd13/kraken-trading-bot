#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — le manifeste gelé vérifié avant S1 (plans/plan.md § 5 ; repris
# de results/c3_racine_registre/tests/manifest_check.sh, réécrit : il n'y a pas de delta ici, le gel entre à l'octet).
#  1. results/c3_campagne_grid/manifest.json est le brouillon gelé À L'OCTET (`cmp`), et son sha256 est celui du gel.
#  2. `protocol_sha256` du manifeste = sha256 de docs/protocole_c3.md = v2.3.
#  3. Faits du gel, lus sur le manifeste : fenêtre 2021-03-01 → 2026-06-29, F = 0,7 ; `deferred_evaluation.date` −
#     `window.end` = 365 jours exactement ; famille `grid-atr-v4` ; provenance `contaminated` ; `parent.is_root` ;
#     graine 20261001 ; 96 candidats distincts = {BTC/USDT, SOL/USDT} × min_spacing_pct 4 × atr_multiplier 4 ×
#     bear_protection_mode 3, tous `grok_grid_atr_adaptive_v4` ; les 8 estampilles 1 w dérivées citées par `run_scope`.
#  4. `c3_anchor` en local — pur, sans base ; registre et sortie dans un répertoire temporaire hors du dépôt, supprimé
#     ensuite : contrôle du manifeste, PAS le run (ce registre temporaire n'est pas le « registre jeté » qu'exclut
#     D-pilote, acté à la relecture, A4) — code 0, T = 2024-11-22T04:48:00+00:00, préfixe 1 362,2 j, 96 candidats,
#     variante nouvelle au registre temporaire. Sortie de l'ancrage filtrée par LISTE BLANCHE (A4) : seules les lignes
#     `ancrage T = …`, `variante … — nouvelle au registre` et `provenance de l'univers …` sont recopiées ; jamais la ligne
#     `written … sha256 …` (64 hex d'un temporaire, hors de la règle d'interdits.sh).
# Sortie : manifest_check.out, une ligne `clé=valeur` par fait, puis rc=0 ssi 1 à 4 tiennent.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/manifest_check.out
NEW=results/c3_campagne_grid/manifest.json
DRAFT=agent/manifest_campagne_draft.json
MANIFEST_SHA=d422076b09292d8aeb2a6ae3f39b9c37325f23e954c05c6c83a8979255325041
PROTOCOL_V23=d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6
EXPECTED_T=2024-11-22T04:48:00+00:00
NOW=2026-10-01T00:00:00+00:00
fail=0

: > "$OUT"
echo "# manifest_check — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"

# 1. copie à l'octet, sha256 du gel
cmp -s "$DRAFT" "$NEW"; r=$?; echo "copie_a_l_octet_du_brouillon=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
echo "sha256sum: $(shasum -a 256 "$NEW")" >> "$OUT"
if [ "$(shasum -a 256 "$NEW" | cut -d' ' -f1)" = "$MANIFEST_SHA" ]; then r=0; else r=1; fail=1; fi
echo "sha256_egal_gel=$r" >> "$OUT"

# 2. sha du protocole
declared=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["protocol_sha256"])' "$NEW")
actual=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
if [ "$declared" = "$PROTOCOL_V23" ] && [ "$actual" = "$PROTOCOL_V23" ]; then r=0; else r=1; fail=1; fi
echo "protocole_v23=$r declare=${declared:0:16}… fichier=${actual:0:16}…" >> "$OUT"

# 3. faits du gel (clés et valeurs du manifeste, jamais une donnée)
python3 - "$NEW" >> "$OUT" 2>&1 <<'PY'
from datetime import datetime
import itertools
import json
import sys

m = json.load(open(sys.argv[1], encoding="utf-8"))
checks = {}
checks["fenetre"] = (m["window"]["start"], m["window"]["end"]) == (
    "2021-03-01T00:00:00+00:00",
    "2026-06-29T00:00:00+00:00",
)
checks["fraction_ancrage"] = m["anchor_fraction"] == 0.7
end = datetime.fromisoformat(m["window"]["end"])
date = datetime.fromisoformat(m["deferred_evaluation"]["date"])
days = (date - end).total_seconds() / 86400.0
print(f"ecart_date_differee_jours={days:.6f} attendu=365.000000")
checks["ecart_365"] = days == 365.0
checks["famille"] = m["family"] == "grid-atr-v4"
checks["provenance"] = m["universe"]["provenance"] == "contaminated"
checks["racine"] = m["parent"] == {"is_root": True}
checks["graine"] = m["uncertainty"]["seed"] == 20261001
cands = m["universe"]["candidates"]
keys = [
    (c["strategy"], c["pair"], c["params"]["min_spacing_pct"], c["params"]["atr_multiplier"],
     c["params"]["bear_protection_mode"])
    for c in cands
]
grid = set(
    itertools.product(
        ["grok_grid_atr_adaptive_v4"],
        ["BTC/USDT", "SOL/USDT"],
        [0.015, 0.02, 0.025, 0.03],
        [1.5, 2.0, 2.5, 3.0],
        ["none", "1w_only", "1d_only"],
    )
)
print(f"candidats={len(cands)} distincts={len(set(keys))} produit_attendu={len(grid)}")
checks["univers_96"] = len(cands) == 96 and set(keys) == grid and all(len(c["params"]) == 3 for c in cands)
stamps = ["2022-06-06", "2022-07-04", "2022-09-05", "2022-10-03", "2022-11-07", "2022-12-05", "2025-02-03", "2025-03-03"]
checks["estampilles_1w_derivees_citees"] = all(s in m["run_scope"] for s in stamps)
checks["entree_23_citee"] = "entrée 23" in m["research_log_entry"]
for name, ok in checks.items():
    print(f"{name}={'0' if ok else '1'}")
sys.exit(0 if all(checks.values()) else 1)
PY
r=$?; echo "faits_du_gel=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1

# 4. c3_anchor local, hors dépôt : contrôle du manifeste, pas le run
TMP=$(mktemp -d) || exit 2
poetry run python scripts/audit/c3_anchor.py --manifest "$NEW" --registry "$TMP/variants.json" \
  --output "$TMP/anchor.json" --now "$NOW" > "$TMP/anchor.log" 2>&1
r=$?; echo "c3_anchor_local=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
python3 - "$TMP/anchor.json" "$EXPECTED_T" >> "$OUT" 2>&1 <<'PY'
import json
import sys

try:
    a = json.load(open(sys.argv[1], encoding="utf-8"))
    facts = {
        "T": a["anchor"],
        "prefixe_jours": f"{a['prefix_days']:.1f}",
        "evaluation_jours": f"{a['evaluation_days']:.1f}",
        "n_candidats": a["n_candidates"],
        "nouvelle_au_registre_temporaire": a["registry"]["new_entry"],
    }
except (OSError, KeyError, TypeError, ValueError):
    facts = {}
for key, value in facts.items():
    print(f"ancrage_{key}={value}")
ok = (
    facts.get("T") == sys.argv[2]
    and facts.get("prefixe_jours") == "1362.2"
    and facts.get("n_candidats") == 96
    and facts.get("nouvelle_au_registre_temporaire") is True
)
print(f"ancrage_attendu={'0' if ok else '1'} T_attendu={sys.argv[2]}")
sys.exit(0 if ok else 1)
PY
r=$?; [ $r -ne 0 ] && fail=1
grep -E "^(ancrage T = |variante .* — nouvelle au registre$|provenance de l'univers )" "$TMP/anchor.log" \
  | sed 's/^/anchor_log: /' >> "$OUT"
rm -rf "$TMP"
[ ! -e "$TMP" ]; echo "temporaire_supprime=$?" >> "$OUT"

echo "rc=$fail" >> "$OUT"
exit $fail
