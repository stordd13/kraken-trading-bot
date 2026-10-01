#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — le script de lecture de diagnostic (tests/diagnostic_entry.sh)
# prouvé AVANT de servir (règles agent 1 et 2), en local, sans serveur, sans base. Son corps Python est extrait tel quel
# (aucune substitution) et exécuté sur des entry.json simulés.
#  1. Témoins PRODUITS PAR LE CODE DE S1 (règle 2 : le témoin est conforme au contrat) :
#     - c3_entry.main sur des entrées fabriquées : ancre au sha faux, à T + 1 min et à provenance `clean` (les trois
#       formes de main, l.938-953) ; puis une observation dont `net_pnl` est NaN (InvalidValueError levée dans
#       l'assertion I-A.1, inscrite par main : revue R3 d, l.974-976) — les deux entry.json sont ceux qu'écrit c3_entry ;
#     - les accesseurs de c3_common (minimum, suite non finie, décimal non fini, champ de couverture, champ hors
#       schéma), cc.candidate_identity (NonFiniteValueError de canon) ;
#     - c3_entry.a06_warmup (séries de décision en désaccord ; `sufficient` déclaré ≠ recalculé) et
#       cc.coverage_recompute (dates contre unités couvertes, AM-09) : les trois formes atteignables hors du cadrage.
#     Les attendus sont dérivés de la classification décidée par Bruno (texte), jamais de la sortie du script.
#  2. Cas adverses : chaque violation plantée porte l'identité réelle d'un candidat (64 hex, clé d'observation) et des
#     valeurs (-987654, NaN, inf, la paire, la stratégie) ; des champs sentinelles sont ajoutés à entry.json hors de
#     `violations` ; entry.md et entry.log sont présents, porteurs de sentinelles, et ILLISIBLES (chmod 000). La sortie
#     doit égaler l'attendu, respecter la grammaire fermée, et ne contenir aucune chaîne plantée.
#  3. Mutants du corps (copies temporaires, une seule modification chacun) : violation brute imprimée ; chemin imprimé
#     au lieu du champ ; champ non validé ; entry.md ouvert ; un autre champ d'entry.json lu. Chacun doit être vu.
# Rien de planté ni de produit n'est imprimé ici : seuls des codes, des booléens et les sorties des témoins (de la
# grammaire fermée) remontent. Sortie : diagnostic_preuve.out ; rc=0 ssi tout tient.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid/tests/diagnostic_preuve.out
SRC=results/c3_campagne_grid/tests/diagnostic_entry.sh
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# diagnostic_preuve — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"
sed -n "/<<'PYEOF'\$/,/^PYEOF\$/p" "$SRC" | sed '1d;$d' > "$T/body.py"
log "corps_extrait_lignes=$(wc -l < "$T/body.py" | tr -d ' ') (sans substitution)"

# --- 1. témoins, produits par le code de S1 -------------------------------------------------------------------------
poetry run python - "$T" > "$T/fabrique.log" 2>&1 <<'PY'
import contextlib
from datetime import timedelta
import io
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, "scripts/audit")
import c3_common as cc  # noqa: E402
import c3_entry  # noqa: E402

base = Path(sys.argv[1])
M = Path("results/c3_campagne_grid/manifest.json")
manifest = cc.load_manifest(cc.read_json(M))
T = manifest.anchor()
P = manifest.prefix_segment
cand = manifest.candidates[0]
ident = cand.identity
sink = io.StringIO()


def raised(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except (cc.InvalidValueError, cc.NonFiniteValueError) as exc:
        return str(exc)
    raise AssertionError("aucune violation levée")


def entry_run(name, anchor, observations):
    d = base / "run" / name
    d.mkdir(parents=True)
    (d / "anchor.json").write_text(json.dumps(anchor), encoding="utf-8")
    (d / "observations.json").write_text(json.dumps(observations), encoding="utf-8")
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        code = c3_entry.main([
            "--manifest", str(M), "--anchor", str(d / "anchor.json"), "--observations",
            str(d / "observations.json"), "--output", str(d / "entry.json"), "--markdown", str(d / "entry.md"),
            "--now", "2026-10-01T00:00:00+00:00",
        ])
    assert code == 1, (name, code)
    return d / "entry.json"


good = {
    "ok": True, "invalide": False, "exit_code": 0, "inputs_sha256": {"manifest": cc.file_sha256(M)},
    "anchor": T.isoformat(), "universe_provenance": manifest.provenance,
}
bad = dict(good, inputs_sha256={"manifest": "f" * 64}, anchor=(T + timedelta(minutes=1)).isoformat(),
           universe_provenance="clean")
anchor_file = entry_run("anchor", bad, {})
observation = {
    "strategy": cand.strategy, "pair": cand.pair, "exchange": manifest.exchange, "fees": manifest.fee_model,
    "pair_costs_file": manifest.pair_costs_file, "params": dict(cand.params), "effective_params": {},
    "decision_timeframes": ["1d"], "metrics_version": 2, "replay_version": 2,
    "pair_costs": {"spread": "0.0002", "slippage": "0.0002"}, "min_order_quote": 5.0,
    "equity_daily": {P: {}},
    P: {"metrics_version": 2, "total_trades": 0, "winning_trades": 0, "losing_trades": 0, "net_pnl": math.nan},
}
nan_file = entry_run("nan", good, {ident: observation})
v_anchor = cc.read_json(anchor_file)["violations"]
v_nan = cc.read_json(nan_file)["violations"]
assert len(v_anchor) == 3 and len(v_nan) == 1, (len(v_anchor), len(v_nan))

w_obs = f"observations.{ident}.{P}"
v_non_fini = [
    raised(cc.require_int, {"total_trades": -987654}, "total_trades", where=w_obs, minimum=0),
    raised(cc.require_finite_series, {"values": [1000.0, math.inf]}, "values",
           where=f"observations.{ident}.equity_daily.{P}", min_len=2),
    raised(cc.require_decimal, {"spread": "NaN"}, "spread", where=f"observations.{ident}.pair_costs"),
    raised(cc.require_float, {"longest_gap_days": math.nan}, "longest_gap_days",
           where=f"coverage.pairs.{cand.pair}.1440"),
    raised(cc.candidate_identity, cand.strategy, cand.pair, {"atr_multiplier": math.nan}),
    raised(cc.require_float, {"zz_hors_schema": math.nan}, "zz_hors_schema", where=w_obs),
]

ctx = c3_entry.Context(manifest=manifest, anchor=T, prefix_days=0.0, coverage_path=None,
                       observations={ident: {"strategy": cand.strategy, "pair": cand.pair,
                                             "params": dict(cand.params), "decision_timeframes": ["1d"]}})
try:
    c3_entry.a06_warmup(ctx)
except cc.MissingEvidenceError:
    pass
blocks = {tf: {"required": 10, "loaded": 5, "stale_by_candles": 0, "largest_gap_candles": 0, "sufficient": False}
          for tf in cand.decision_timeframes}
blocks[cand.decision_timeframes[0]]["sufficient"] = True
ctx2 = c3_entry.Context(manifest=manifest, anchor=T, prefix_days=0.0, coverage_path=None,
                        observations={ident: {"strategy": cand.strategy, "pair": cand.pair,
                                              "params": dict(cand.params),
                                              "decision_timeframes": list(cand.decision_timeframes),
                                              "warmup": {P: blocks}}})
c3_entry.a06_warmup(ctx2)
series = {"expected": 0, "observed": 0, "covered_units": 0, "expected_units": 1, "missing_stamps": [],
          "longest_gap_days": 0.0, "first_day": None, "last_day": None}
v_am09 = cc.coverage_recompute(series, start=manifest.window_start, end=T, interval=10080,
                               where=f"coverage.pairs.{cand.pair}.10080")["violations"]
v_hors_classe = ctx.violations + ctx2.violations + v_am09 + [f"forme inconnue simulée {ident} -987654"]
assert [len(ctx.violations), len(ctx2.violations), len(v_am09)] == [1, 1, 1]

sentinels = {
    "refusal": {"detail": f"SENTINELLE refus {ident} -987654"},
    "rows": [{"detail": f"SENTINELLE ligne {ident}"}],
    "diagnostics": [{"identity": ident, "valeur": "SENTINELLE -987654"}],
}
cases = {
    "anchor": None,
    "nan": None,
    "non_fini": {"violations": v_non_fini},
    "hors_classe": {"violations": v_hors_classe},
    "mixte": {"violations": v_anchor + v_nan + v_non_fini + v_hors_classe, **sentinels},
    "vide": {"violations": []},
    "illisible": {"refusal": {"detail": f"SENTINELLE {ident}"}},
    "non_liste": {"violations": f"SENTINELLE {ident}"},
}
for name, payload in cases.items():
    d = base / "temoins" / name
    d.mkdir(parents=True)
    if payload is None:
        source = anchor_file if name == "anchor" else nan_file
        (d / "entry.json").write_bytes(source.read_bytes())
    else:
        (d / "entry.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (d / "entry.md").write_text(f"SENTINELLE md {ident}\n", encoding="utf-8")
    (d / "entry.log").write_text(f"SENTINELLE log {ident} -987654\n", encoding="utf-8")
    (d / "entry.md").chmod(0)
    (d / "entry.log").chmod(0)
(base / "plantes.txt").write_text(
    "\n".join([ident, ident[:16], "987654", cand.pair, cand.strategy, "SENTINELLE", "NaN", "Infinity"]) + "\n",
    encoding="utf-8",
)
print("fabrique=ok")
PY
r=$?
log "fabrique_par_le_code_de_S1=$r"
[ "$r" = "0" ] || fail=1

# --- attendus, dérivés de la classification décidée (texte) ---------------------------------------------------------
# anchor : les trois formes de main → une par classe d'ancre. nan : InvalidValueError sur `net_pnl`, clé du schéma,
# racine observations. non_fini : total_trades, values, spread (clés du schéma, racine observations) ; longest_gap_days
# (racine coverage), NonFiniteValueError (sans champ), zz_hors_schema (hors schéma) → hors_liste ×3. hors_classe : les
# deux formes de a06, la forme AM-09 de coverage_recompute, une forme inconnue. mixte : la réunion (3 + 1 + 6 + 4).
mkdir -p "$T/attendus"
expect() { printf '%s\n' "violations_total=$2" "violations_par_classe=$3" "champs=$4" > "$T/attendus/$1"; }
expect anchor 3 "anchor_inputs_sha256:1,anchor_T:1,provenance:1,non_fini_ou_invalide:0,hors_classe:0" "-"
expect nan 1 "anchor_inputs_sha256:0,anchor_T:0,provenance:0,non_fini_ou_invalide:1,hors_classe:0" "net_pnl:1"
expect non_fini 6 "anchor_inputs_sha256:0,anchor_T:0,provenance:0,non_fini_ou_invalide:6,hors_classe:0" \
  "spread:1,total_trades:1,values:1,hors_liste:3"
expect hors_classe 4 "anchor_inputs_sha256:0,anchor_T:0,provenance:0,non_fini_ou_invalide:0,hors_classe:4" "-"
expect mixte 14 "anchor_inputs_sha256:1,anchor_T:1,provenance:1,non_fini_ou_invalide:7,hors_classe:4" \
  "net_pnl:1,spread:1,total_trades:1,values:1,hors_liste:3"
expect vide 0 "anchor_inputs_sha256:0,anchor_T:0,provenance:0,non_fini_ou_invalide:0,hors_classe:0" "-"
printf '%s\n' "violations_total=illisible" > "$T/attendus/illisible"
printf '%s\n' "violations_total=illisible" > "$T/attendus/non_liste"

# juge <corps> <cas> -> « rc=… attendu_egal=… grammaire=… plantes_absentes=… » (rien de la sortie n'est imprimé)
judge() {
  local body=$1 name=$2 d=$T/temoins/$2 out r
  out=$T/sortie_$(basename "$body")_$name.txt
  python3 "$body" "$d/entry.json" > "$out" 2> /dev/null
  r=$?
  python3 - "$out" "$T/attendus/$name" "$T/plantes.txt" "$T/body.py" "$r" <<'PY'
import ast
import re
import sys

out, expected, planted, body, rc = sys.argv[1:6]
text = open(out, encoding="utf-8").read()
schema = None
for node in ast.parse(open(body, encoding="utf-8").read()).body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCHEMA" for t in node.targets):
        schema = ast.literal_eval(node.value)
field = "(?:" + "|".join(re.escape(k) for k in sorted(schema)) + "|hors_liste)"
grammar = [
    re.compile(r"violations_total=(?:\d+|illisible)"),
    re.compile(r"violations_par_classe=anchor_inputs_sha256:\d+,anchor_T:\d+,provenance:\d+,"
               r"non_fini_ou_invalide:\d+,hors_classe:\d+"),
    re.compile(r"champs=(?:-|" + field + r":\d+(?:," + field + r":\d+)*)"),
]
lines = text.splitlines()
grammar_ok = all(any(g.fullmatch(line) for g in grammar) for line in lines)
planted_ok = not any(p and p in text for p in open(planted, encoding="utf-8").read().splitlines())
equal = text == open(expected, encoding="utf-8").read()
print(f"rc={rc} attendu_egal={'0' if equal else '1'} grammaire={'0' if grammar_ok else '1'} "
      f"plantes_absentes={'0' if planted_ok else '1'}")
PY
}

for name in anchor nan non_fini hors_classe mixte vide illisible non_liste; do
  verdict=$(judge "$T/body.py" "$name")
  case "$name" in illisible|non_liste) want_rc=1 ;; *) want_rc=0 ;; esac
  log "temoin cas=$name $verdict (rc attendu $want_rc)"
  [ "$verdict" = "rc=$want_rc attendu_egal=0 grammaire=0 plantes_absentes=0" ] || fail=1
  case "$name" in illisible|non_liste) ;; *) sed 's/^/  sortie: /' "$T/sortie_body.py_$name.txt" >> "$OUT" ;; esac
done

# --- 3. mutants du corps : chacun doit être vu sur le témoin mixte ------------------------------------------------------
mutate() {  # mutate <nom> <ancien> <nouveau>
  python3 - "$T/body.py" "$T/$1.py" "$2" "$3" <<'PY'
import sys

source, target, old, new = sys.argv[1:5]
text = open(source, encoding="utf-8").read()
assert text.count(old) == 1, old
open(target, "w", encoding="utf-8").write(text.replace(old, new))
PY
  local r=$?
  local verdict
  verdict=$(judge "$T/$1.py" mixte)
  log "mutant=$1 applique=$r $verdict"
  if [ "$r" != "0" ] || [ "$verdict" = "rc=0 attendu_egal=0 grammaire=0 plantes_absentes=0" ]; then fail=1; fi
}
mutate M1_violation_brute 'print(f"violations_total={len(violations)}")' \
  'print(f"violations_total={len(violations)} {violations}")'
mutate M2_chemin_au_lieu_du_champ 'return "non_fini_ou_invalide", key if ok else "hors_liste"' \
  'return "non_fini_ou_invalide", head if ok else "hors_liste"'
mutate M3_champ_non_valide 'ok = head.startswith("observations.") and key in SCHEMA' 'ok = True'
mutate M4_entry_md_ouvert $'import sys\n' \
  $'import sys\nopen(sys.argv[1][: -len("entry.json")] + "entry.md", encoding="utf-8").read()\n'
mutate M5_autre_champ_lu 'violations = json.load(handle)["violations"]' \
  'raw = json.load(handle); violations = raw["violations"] + [str(raw.get("refusal"))]'

chmod -R u+rw "$T" 2> /dev/null
rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
