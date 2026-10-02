#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique — le manifeste gelé v2 vérifié avant S1
# (plans/plan.md § 6 ; repris de results/c3_campagne_grid/tests/manifest_check.sh, étendu : surcharges, parent, trois
# cas d'ancrage sur registre temporaire).
#  1. results/c3_campagne_grid_v2/manifest.json est le brouillon gelé À L'OCTET (`cmp`), et son sha256 est celui du gel.
#  2. `protocol_sha256` du manifeste = sha256 de docs/protocole_c3.md = v2.3.
#  3. Faits du gel, lus sur le manifeste : fenêtre 2021-03-01 → 2026-06-29, F = 0,7 ; `deferred_evaluation.date` −
#     `window.end` = 365 jours exactement ; famille `grid-atr-v4` ; provenance `contaminated` ; parent NON racine
#     (`is_root` faux, `variant_key` de 64 hex) ; graine 20261001 ; 96 candidats distincts = {BTC/USDT, SOL/USDT} ×
#     min_spacing_pct 4 × atr_multiplier 4 × bear_protection_mode 3, tous `grok_grid_atr_adaptive_v4` ; les 8
#     estampilles 1 w dérivées citées par `run_scope` ; « entrée 24 » citée ; le titre cité entre « » présent UNE fois au
#     journal, en en-tête `### <titre> (entrée 24,`, entre l'issue de l'entrée 23 et « Essais à venir ».
#  4. Surcharges `decision_timeframes` : chacune égale la sortie triée de la classmethod pure
#     GrokGridATRAdaptiveV4.decision_timeframes(params) (96/96) ; critère a06 de c3_entry (c3_entry.py:496 : en
#     ensemble, liste effective du manifeste contre l'export du producteur, c3b_common.decision_timeframes_by_candidate) :
#     0 désaccord sur v2 ; CAS ADVERSE, le même contrôle sur le manifeste v1 commité : 64 désaccords (la cause de l'arrêt
#     du run v1, constatée par la lecture de diagnostic du 01/10) — le contrôle naît rouge contre l'état précédent.
#  5. Parent : parent.variant_key = sig(canon(manifeste v1 commité)), recalculé (seul le préfixe de 16 hex est imprimé).
#  6. c3_anchor en local — pur, sans base ; registres et sorties dans un répertoire temporaire hors du dépôt, supprimé
#     ensuite ; sel factice écrit au fichier par `secrets.token_hex(32)`, jamais imprimé ; la variante v1 est inscrite
#     par c3_anchor LUI-MÊME, sur le manifeste v1 commité, même --now. Trois cas, un journal par cas :
#       vide    : registre au sel seul → code 2, refus de parenté, registre inchangé, aucune sortie écrite ;
#       avec_v1 : registre portant v1 → code 0, nouvelle au registre, T, préfixe 1 362,2 j, 96 candidats ; racine (sel)
#                 et enregistrement v1 inchangés, deux variantes (booléens) ;
#       rejeu   : même registre → code 0, déjà au registre, idempotent, registre inchangé.
#     Contrôle du manifeste, PAS le run (A4 du chantier v1) : ces registres temporaires ne sont pas des « registres
#     jetés » au sens du pilote. De anchor.json, n'imprime que T, préfixe, évaluation, n, new_entry (jamais variant_key,
#     registry.sha256, manifest_sha256, inputs_sha256) ; journaux filtrés par LISTE BLANCHE (A4) — jamais une ligne
#     `written … sha256 …`.
# Sortie : manifest_check.out, une ligne `clé=valeur` par fait, puis rc=0 ssi 1 à 6 tiennent.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/tests/manifest_check.out
NEW=results/c3_campagne_grid_v2/manifest.json
DRAFT=agent/manifest_campagne_v2_draft.json
V1=results/c3_campagne_grid/manifest.json
MANIFEST_SHA=b757c45bbed2b0913ac4ec781c9c6928fa935b7c71639e66f26fb5d2468f4f11
PROTOCOL_V23=d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6
EXPECTED_T=2024-11-22T04:48:00+00:00
NOW=2026-10-01T00:00:00+00:00
# Liste blanche des lignes de journal de c3_anchor recopiées (A4 du chantier v1) ; tout le reste est jeté.
KEEP="^(ancrage T = |variante [0-9a-f]{16} \(.*\) — (nouvelle au registre|déjà au registre, idempotent)$|provenance de l'univers |ENTREE REFUSEE R0_INVALID_RUN: variante [0-9a-f]{16} déclare le parent [0-9a-f]{16}, absent du registre \(§ A\.6\)$)"
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

# 3. faits du gel (clés et valeurs du manifeste, jamais une donnée) ; le titre de l'entrée 24 au journal
python3 - "$NEW" docs/RESEARCH_LOG.md >> "$OUT" 2>&1 <<'PY'
from datetime import datetime
import itertools
import json
import re
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
parent = m["parent"]
checks["parent_non_racine"] = (
    sorted(parent) == ["is_root", "variant_key"]
    and parent["is_root"] is False
    and re.fullmatch(r"[0-9a-f]{64}", parent["variant_key"]) is not None
)
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
checks["entree_24_citee"] = "entrée 24" in m["research_log_entry"]
# le titre cité entre « » : présent une fois en en-tête de l'entrée 24, entre l'issue de l'entrée 23 et « Essais à venir »
found = re.search(r"« (.+) »", m["research_log_entry"])
lines = open(sys.argv[2], encoding="utf-8").read().splitlines()
heading = f"### {found.group(1)} (entrée 24," if found else None
hits = [i for i, line in enumerate(lines) if heading and line.startswith(heading)]
issue23 = [i for i, line in enumerate(lines) if line.startswith("### Issue de l'entrée 23")]
avenir = [i for i, line in enumerate(lines) if line.startswith("### Essais à venir")]
placed = len(hits) == 1 and len(issue23) == 1 and len(avenir) == 1 and issue23[0] < hits[0] < avenir[0]
print(f"titre_entree_24_au_journal={'0' if placed else '1'} occurrences={len(hits)}")
checks["titre_entree_24"] = placed
for name, ok in checks.items():
    print(f"{name}={'0' if ok else '1'}")
sys.exit(0 if all(checks.values()) else 1)
PY
r=$?; echo "faits_du_gel=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1

# 4-5. surcharges = classmethod ; critère a06 contre l'export du producteur (v2 et, adverse, v1) ; parent = sig(canon(v1))
poetry run python - "$NEW" "$V1" >> "$OUT" 2>&1 <<'PY'
from collections import Counter
import sys

sys.path.insert(0, "scripts/audit")
sys.path.insert(0, "scripts")
sys.path.insert(0, "src")
import c3_common as cc  # noqa: E402
import c3b_common as c3bc  # noqa: E402

from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4  # noqa: E402

new_raw, v1_raw = cc.read_json(sys.argv[1]), cc.read_json(sys.argv[2])
cands = new_raw["universe"]["candidates"]
equal = sum(c.get("decision_timeframes") == sorted(GrokGridATRAdaptiveV4.decision_timeframes(c["params"])) for c in cands)
classes = Counter(",".join(c["decision_timeframes"]) for c in cands)
print(f"surcharges_egales_classmethod={equal}/{len(cands)} attendu=96/96")
print("classes_surcharges=" + " ".join(f"{k}:{v}" for k, v in sorted(classes.items())))


def a06(raw):
    """Le critère de c3_entry.a06_warmup (l.496) : ensemble exporté par le producteur ≠ liste effective du manifeste."""
    manifest = cc.load_manifest(raw)
    exported = c3bc.decision_timeframes_by_candidate(manifest)
    bad = sum(set(exported[c.identity]) != set(c.decision_timeframes) for c in manifest.candidates)
    return bad, len(manifest.candidates)


bad2, n2 = a06(new_raw)
bad1, n1 = a06(v1_raw)
print(f"a06_desaccords_v2={bad2}/{n2} attendu=0")
print(f"a06_desaccords_v1_adverse={bad1}/{n1} attendu=64")
key_v1 = cc.sig(v1_raw)
parent_ok = new_raw["parent"]["variant_key"] == key_v1
print(f"parent_egal_sig_canon_v1={'0' if parent_ok else '1'} prefixe={key_v1[:16]}")
ok = equal == len(cands) == 96 and bad2 == 0 and bad1 == 64 and parent_ok
sys.exit(0 if ok else 1)
PY
r=$?; echo "surcharges_a06_parent=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1

# 6. c3_anchor local, hors dépôt : contrôle du manifeste, pas le run
TMP=$(mktemp -d) || exit 2
python3 - "$TMP" <<'PY'
import json
import pathlib
import secrets
import sys

base = pathlib.Path(sys.argv[1])
salt = secrets.token_hex(32)  # sel factice : écrit au fichier, jamais imprimé
for case in ("vide", "avec_v1"):
    (base / case).mkdir()
    (base / case / "variants.json").write_text(json.dumps({"salt": salt, "variants": {}}, indent=2) + "\n")
PY
anchor() {  # anchor <manifeste> <registre> <sortie> <journal>
  poetry run python scripts/audit/c3_anchor.py --manifest "$1" --registry "$2" --output "$3" --now "$NOW" > "$4" 2>&1
}
keep() { grep -E "$KEEP" "$1" | sed "s/^/anchor_log_$2: /" >> "$OUT"; }
# la variante v1, inscrite par c3_anchor lui-même sur le manifeste v1 commité
anchor "$V1" "$TMP/avec_v1/variants.json" "$TMP/avec_v1/anchor_v1.json" "$TMP/avec_v1/v1.log"
r=$?; echo "inscription_v1_par_c3_anchor=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
keep "$TMP/avec_v1/v1.log" v1
cp "$TMP/vide/variants.json" "$TMP/vide/avant.json"
cp "$TMP/avec_v1/variants.json" "$TMP/avec_v1/avant.json"
# cas vide : le contrôle de parent mord
anchor "$NEW" "$TMP/vide/variants.json" "$TMP/vide/anchor.json" "$TMP/vide/anchor.log"
r=$?; echo "cas_vide_code=$r attendu=2" >> "$OUT"; [ "$r" = "2" ] || fail=1
cmp -s "$TMP/vide/avant.json" "$TMP/vide/variants.json"; r=$?; echo "cas_vide_registre_inchange=$r" >> "$OUT"
[ $r -ne 0 ] && fail=1
[ ! -e "$TMP/vide/anchor.json" ]; r=$?; echo "cas_vide_aucune_sortie=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
keep "$TMP/vide/anchor.log" vide
grep -qE "^ENTREE REFUSEE R0_INVALID_RUN: .* absent du registre" "$TMP/vide/anchor.log"; r=$?
echo "cas_vide_refus_de_parente=$r" >> "$OUT"; [ $r -ne 0 ] && fail=1
# cas avec_v1 : nouvelle inscription
anchor "$NEW" "$TMP/avec_v1/variants.json" "$TMP/avec_v1/anchor.json" "$TMP/avec_v1/anchor.log"
r=$?; echo "cas_avec_v1_code=$r attendu=0" >> "$OUT"; [ "$r" = "0" ] || fail=1
python3 - "$TMP/avec_v1" "$EXPECTED_T" "$V1" >> "$OUT" 2>&1 <<'PY'
import json
import pathlib
import sys

base, expected_t = pathlib.Path(sys.argv[1]), sys.argv[2]
try:
    a = json.load(open(base / "anchor.json", encoding="utf-8"))
    facts = {
        "T": a["anchor"],
        "prefixe_jours": f"{a['prefix_days']:.1f}",
        "evaluation_jours": f"{a['evaluation_days']:.1f}",
        "n_candidats": a["n_candidates"],
        "nouvelle_au_registre": a["registry"]["new_entry"],
    }
    before = json.load(open(base / "avant.json", encoding="utf-8"))
    after = json.load(open(base / "variants.json", encoding="utf-8"))
    v1_key = json.load(open(base / "anchor_v1.json", encoding="utf-8"))["variant_key"]
    root_kept = sorted(after) == sorted(before) == ["salt", "variants"] and after["salt"] == before["salt"]
    v1_kept = after["variants"].get(v1_key) == before["variants"].get(v1_key) is not None
    two = len(after["variants"]) == 2 and len(before["variants"]) == 1
except (OSError, KeyError, TypeError, ValueError):
    facts, root_kept, v1_kept, two = {}, False, False, False
for key, value in facts.items():
    print(f"cas_avec_v1_ancrage_{key}={value}")
print(f"cas_avec_v1_racine_preservee={'0' if root_kept else '1'}")
print(f"cas_avec_v1_enregistrement_v1_inchange={'0' if v1_kept else '1'}")
print(f"cas_avec_v1_deux_variantes={'0' if two else '1'}")
ok = (
    facts.get("T") == expected_t
    and facts.get("prefixe_jours") == "1362.2"
    and facts.get("n_candidats") == 96
    and facts.get("nouvelle_au_registre") is True
    and root_kept
    and v1_kept
    and two
)
print(f"cas_avec_v1_attendu={'0' if ok else '1'} T_attendu={expected_t}")
sys.exit(0 if ok else 1)
PY
r=$?; [ $r -ne 0 ] && fail=1
keep "$TMP/avec_v1/anchor.log" avec_v1
cp "$TMP/avec_v1/variants.json" "$TMP/avec_v1/apres.json"
# cas rejeu : idempotent
anchor "$NEW" "$TMP/avec_v1/variants.json" "$TMP/avec_v1/anchor_rejeu.json" "$TMP/avec_v1/rejeu.log"
r=$?; echo "cas_rejeu_code=$r attendu=0" >> "$OUT"; [ "$r" = "0" ] || fail=1
cmp -s "$TMP/avec_v1/apres.json" "$TMP/avec_v1/variants.json"; r=$?; echo "cas_rejeu_registre_inchange=$r" >> "$OUT"
[ $r -ne 0 ] && fail=1
ne=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["registry"]["new_entry"])' \
  "$TMP/avec_v1/anchor_rejeu.json" 2>&1)
echo "cas_rejeu_nouvelle_au_registre=$ne attendu=False" >> "$OUT"; [ "$ne" = "False" ] || fail=1
keep "$TMP/avec_v1/rejeu.log" rejeu
rm -rf "$TMP"
[ ! -e "$TMP" ]; echo "temporaire_supprime=$?" >> "$OUT"

echo "rc=$fail" >> "$OUT"
exit $fail
