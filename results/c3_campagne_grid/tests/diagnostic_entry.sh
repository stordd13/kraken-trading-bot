#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — lecture de diagnostic du STOP au run (constat.md § 6), décidée
# par Bruno avant toute lecture, sur liste close. LECTURE SEULE, au serveur, d'UN fichier : out/pre/entry.json du run,
# et dans ce fichier de la SEULE clé `violations`. entry.md et entry.log ne sont pas ouverts ; aucun autre fichier du
# run, aucun registre. Soumis à relecture puis au GO de Bruno avant de tourner — jamais lancé sans ce GO.
# usage : bash diagnostic_entry.sh
#
# Cadrage (Bruno) : sur un code 1, la cause n'est pas dans la table I-A (`exit_code = 1 if violations else (2 if
# refusal else 0)`, c3_entry.py:978 ; un échec I-A produit un refus, code 2) : elle est dans `violations`.
# N'imprime que, tirés de `violations` :
#   violations_total=<n>
#   violations_par_classe=anchor_inputs_sha256:<n>,anchor_T:<n>,provenance:<n>,non_fini_ou_invalide:<n>,hors_classe:<n>
#   champs=<champ:n,…> pour la classe non_fini_ou_invalide (`-` si aucune), chaque nom de champ validé contre le schéma
#     des observations tiré du code à S1 (SCHEMA ; tests/schema_observations.sh l'épingle au code), sinon hors_liste.
# Jamais la chaîne brute d'une violation, jamais une identité de candidat, jamais une valeur, jamais un chemin. Un
# hors_classe ou un hors_liste dans la sortie est un point de décision, pas une invitation à élargir.
# La sortie d'erreur de l'interpréteur est jetée au serveur (une trace pourrait porter un fragment de violation) :
# seul son code remonte (`lecture_exit`).
# Prouvé avant de servir par tests/diagnostic_preuve.sh (témoins produits par le code à S1, cas adverses, mutants) :
# le corps Python ci-dessous y est extrait tel quel, sans substitution.
# Sortie : diagnostic_entry.out ; rc=0 ssi ssh et lecture en 0.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/diagnostic_entry.out

{
  echo "# diagnostic_entry — $(date -u +%FT%TZ) — HEAD local $(git rev-parse HEAD)"
  ssh -p 41922 -o BatchMode=yes bruno@77.42.90.102 'bash -s' <<'REMOTE'
set -u
PY=/home/bruno/.cache/pypoetry/virtualenvs/krakenbot-3rJ6HBr0-py3.12/bin/python
ENTRY=/home/bruno/runs/c3_campagne_grid/campagne/out/pre/entry.json
"$PY" - "$ENTRY" 2> /dev/null <<'PYEOF'
import json
import re
import sys

#: Le schéma des observations : les clés que c3_entry lit sur les observations au code de S1 (accesseurs
#: cc.require_*/nullable_*/optional_* de Context, _liquidation_form, _segment_form, a01, a02, a03, a04, a06, a08, et
#: cc.warmup_sufficient). Recopié, épinglé à l'extraction par l'AST du code (tests/schema_observations.sh).
SCHEMA = (
    "amount_base", "avg_holding_minutes", "buy_fees", "dca_counters", "decision_timeframes", "duration_days",
    "dust_written_off_base", "effective_params", "end", "ending_balance", "entry_price", "equity_daily",
    "exchange", "exec_interval", "extended_by", "fee", "fees", "first", "gross_quote", "interval",
    "inventory_divergence_base", "largest_gap_candles", "last", "liquidation", "loaded", "losing_trades", "lots",
    "max_drawdown_pct_daily", "metrics_version", "min_order_quote", "n_daily_returns", "net_pnl",
    "net_pnl_lot_basis", "pair", "pair_costs", "pair_costs_file", "params", "period", "pnl", "positions", "price",
    "reference_price", "rejections", "replay_version", "required", "residual_net_proceeds", "residual_trade_base",
    "sell_fees", "slippage", "slippage_pct", "spread", "spread_pct", "stale_by_candles", "start",
    "starting_balance", "strategy", "sufficient", "timestamp", "total_trades", "trades", "values", "warmup",
    "winning_trades",
)
CLASSES = ("anchor_inputs_sha256", "anchor_T", "provenance", "non_fini_ou_invalide", "hors_classe")
# Les formes du code de S1 (235461e), par motif — classification fermée décidée par Bruno.
#   anchor_inputs_sha256 : c3_common.check_inputs_match (l.1101-1106), appelé par c3_entry.main (l.938) ;
#   anchor_T             : c3_entry.main (l.944-946) ;
#   provenance           : c3_entry.main (l.951-953).
ANCHOR_INPUTS = re.compile(r"anchor\.inputs_sha256\.manifest: enregistré .*, fichier [0-9a-f]{16}", re.S)
ANCHOR_T = re.compile(r"anchor\.anchor déclaré \S+, recalculé \S+ — le recalcul fait foi", re.S)
PROVENANCE = re.compile(r"anchor\.universe_provenance '[^']*' != manifeste '[^']*'", re.S)
#   non_fini_ou_invalide : InvalidValueError (c3_common l.348, 358, 385, 472, 484, 554, 556, 915, 2295) et
#   NonFiniteValueError (rejeu_common l.180, 186), y compris levées depuis l'intérieur des assertions (revue R3 d,
#   c3_entry l.974-976). Les formes à chemin portent le champ en dernière composante ; les autres n'en portent aucun.
KEY = r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
FIELD_FORMS = (
    re.compile(r"(?P<head>.+)\." + KEY + r": valeur non finie \(.*\)", re.S),
    re.compile(r"(?P<head>.+)\." + KEY + r": -?\d+ < minimum -?\d+", re.S),
    re.compile(r"(?P<head>.+)\." + KEY + r"\[\d+\]: valeur non finie \(.*\)", re.S),
    re.compile(r"(?P<head>.+)\." + KEY + r"\[\d+\]: \S+ hors domaine \(doit être > \S+\)", re.S),
    re.compile(r"(?P<head>.+)\." + KEY + r": bloc contradictoire — .*", re.S),
)
NO_FIELD_FORMS = (
    re.compile(r"rejeu : CAGR observé .* non fini \(.*\) — entrée invalide \(§ F\.2 e\)", re.S),
    re.compile(r"non-finite value in the signature payload: .*", re.S),
)


def classify(violation):
    """(classe, champ) : le champ n'existe que pour non_fini_ou_invalide ; il n'est rendu que s'il est une clé du
    schéma des observations sous la racine `observations.`, sinon hors_liste. Rien d'autre n'est rendu."""
    if not isinstance(violation, str):
        return "hors_classe", None
    if ANCHOR_INPUTS.fullmatch(violation):
        return "anchor_inputs_sha256", None
    if ANCHOR_T.fullmatch(violation):
        return "anchor_T", None
    if PROVENANCE.fullmatch(violation):
        return "provenance", None
    for form in FIELD_FORMS:
        match = form.fullmatch(violation)
        if match:
            head, key = match.group("head"), match.group("key")
            ok = head.startswith("observations.") and key in SCHEMA
            return "non_fini_ou_invalide", key if ok else "hors_liste"
    for form in NO_FIELD_FORMS:
        if form.fullmatch(violation):
            return "non_fini_ou_invalide", "hors_liste"
    return "hors_classe", None


try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        violations = json.load(handle)["violations"]
    if not isinstance(violations, list):
        raise TypeError("violations")
except (OSError, ValueError, KeyError, TypeError):
    print("violations_total=illisible")
    sys.exit(1)
counts = dict.fromkeys(CLASSES, 0)
fields = {}
for violation in violations:
    cls, field = classify(violation)
    counts[cls] += 1
    if cls == "non_fini_ou_invalide":
        fields[field] = fields.get(field, 0) + 1
order = sorted(name for name in fields if name != "hors_liste") + (["hors_liste"] if "hors_liste" in fields else [])
print(f"violations_total={len(violations)}")
print("violations_par_classe=" + ",".join(f"{name}:{counts[name]}" for name in CLASSES))
print("champs=" + (",".join(f"{name}:{fields[name]}" for name in order) or "-"))
PYEOF
echo "lecture_exit=$?"
REMOTE
  echo "ssh_exit=$?"
} > "$OUT" 2>&1

if grep -qx "ssh_exit=0" "$OUT" && grep -qx "lecture_exit=0" "$OUT"; then
  echo "rc=0" >> "$OUT"
  exit 0
fi
echo "rc=1" >> "$OUT"
exit 1
