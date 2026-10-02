#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique — le contrôle du registre réel livré à attendu.md § 4
# (A2', décision de Bruno au GO du plan : le § 1 du runbook étendu, livré et relu, jamais improvisé), prouvé avant de
# servir. Neuf, sans source au chantier v1.
#  - Le bloc est EXTRAIT d'attendu.md lui-même, entre les marqueurs `stop1-registre` : une seule ligne `python3 -c '…'`.
#  - Le chemin du registre de campagne y est remplacé par celui d'un registre fabriqué hors du dépôt (variable
#    d'environnement SIM_REG). Le motif remplacé est CONSTRUIT ici, jamais écrit (interdits.sh, règle 8) ; exactement
#    une substitution, sinon rien n'est exécuté. La clé du parent écrite dans la commande est recoupée, en booléen, avec
#    `parent.variant_key` du manifeste v2 commité.
#  - Les registres fabriqués portent un sel factice (`secrets.token_hex(32)`, jamais imprimé) et l'enregistrement v1
#    écrit par c3_anchor lui-même sur le manifeste v1 commité, au même --now que le run v1.
# Cas : témoin (mode 600) → True ; déviations, jamais True — mode 644, parent absent, parent avec verdict, parent avec
# deferred_evaluation, variante en trop, clé de racine en trop, sel court, sel non hexadécimal → False (code 0) ; fichier
# absent, JSON illisible → code ≠ 0, aucune sortie.
# Sortie : stop1_registre.out (`cas=<nom> sortie=<True|False|-> rc=<n> attendu=<…>`) ; rc=0 ssi tout tient.
set -o pipefail
set -u
unset VIRTUAL_ENV
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
OUT=results/c3_campagne_grid_v2/tests/stop1_registre.out
ATTENDU=results/c3_campagne_grid_v2/attendu.md
NEW=results/c3_campagne_grid_v2/manifest.json
V1=results/c3_campagne_grid/manifest.json
NOW=2026-10-01T00:00:00+00:00
C3=$(printf 'c%s' 3)
REG_EXPR="pathlib.Path.home() / \"$C3/regis$(printf 'try')/variants.json\""
T=$(mktemp -d) || exit 2
T=$(cd "$T" && pwd -P) || exit 2
fail=0
: > "$OUT"
log() { printf '%s\n' "$1" >> "$OUT"; }
log "# stop1_registre — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)"

# 1. le bloc, extrait d'attendu.md ; une substitution, comptée
sed -n '/^<!-- stop1-registre:debut -->$/,/^<!-- stop1-registre:fin -->$/p' "$ATTENDU" | grep -E "^python3 -c '" \
  > "$T/commande.txt"
n=$(wc -l < "$T/commande.txt" | tr -d ' ')
log "bloc_lignes_commande=$n attendu=1"
python3 - "$T/commande.txt" "$T/commande_sim.txt" "$REG_EXPR" "$NEW" >> "$OUT" 2>&1 <<'PY'
import json
import sys

text = open(sys.argv[1], encoding="utf-8").read()
expr = sys.argv[3]
count = text.count(expr)
print(f"substitutions_du_chemin={count} attendu=1")
parent = json.load(open(sys.argv[4], encoding="utf-8"))["parent"]["variant_key"]
print(f"cle_du_parent_dans_la_commande={'0' if f'K = \"{parent}\"' in text else '1'}")
if count != 1:
    sys.exit(1)
open(sys.argv[2], "w", encoding="utf-8").write(
    text.replace(expr, 'pathlib.Path(__import__("os").environ["SIM_REG"])')
)
PY
r=$?
if [ "$n" != "1" ] || [ "$r" != "0" ] || ! grep -qx "cle_du_parent_dans_la_commande=0" "$OUT"; then
  log "commande_non_exercee=1 (extraction ou substitution en écart : rien n'est exécuté)"
  rm -rf "$T"
  log "rc=1"
  exit 1
fi

# 2. registres fabriqués : base = sel factice + variante v1 inscrite par c3_anchor sur le manifeste v1 commité
mkdir -p "$T/base"
python3 -c 'import json, secrets, sys; open(sys.argv[1], "w").write(json.dumps({"salt": secrets.token_hex(32), "variants": {}}, indent=2) + "\n")' \
  "$T/base/variants.json"
poetry run python scripts/audit/c3_anchor.py --manifest "$V1" --registry "$T/base/variants.json" \
  --output "$T/base/anchor.json" --now "$NOW" > "$T/base/anchor.log" 2>&1
r=$?
log "inscription_v1_par_c3_anchor=$r"
[ "$r" = "0" ] || fail=1
python3 - "$T" "$NEW" >> "$OUT" 2>&1 <<'PY'
import copy
import json
import pathlib
import sys

base = pathlib.Path(sys.argv[1])
reg = json.load(open(base / "base" / "variants.json", encoding="utf-8"))
key = json.load(open(base / "base" / "anchor.json", encoding="utf-8"))["variant_key"]
parent = json.load(open(sys.argv[2], encoding="utf-8"))["parent"]["variant_key"]
print(f"cle_v1_egale_parent_v2={'0' if key == parent else '1'}")


def variant(fn):
    r = copy.deepcopy(reg)
    fn(r)
    return json.dumps(r, indent=2) + "\n"


cases = {
    "temoin": variant(lambda r: None),
    "mode_644": variant(lambda r: None),
    "parent_absent": variant(lambda r: r.__setitem__("variants", {})),
    "parent_avec_verdict": variant(
        lambda r: r["variants"][key].__setitem__(
            "verdict", {"issue": "inconclusif", "raison": "P_PROVENANCE", "compte": False}
        )
    ),
    "parent_avec_differee": variant(
        lambda r: r["variants"][key].__setitem__(
            "deferred_evaluation", {"date": "2027-06-29T00:00:00+00:00", "variant_key": "0" * 64}
        )
    ),
    "variante_en_trop": variant(lambda r: r["variants"].__setitem__("1" * 64, {"family": "grid-atr-v4"})),
    "racine_en_trop": variant(lambda r: r.__setitem__("autre", "x")),
    "sel_court": variant(lambda r: r.__setitem__("salt", r["salt"][:63])),
    "sel_non_hexadecimal": variant(lambda r: r.__setitem__("salt", "g" + r["salt"][1:])),
    "json_illisible": "{\n",
}
for name, text in cases.items():
    (base / name).mkdir()
    (base / name / "variants.json").write_text(text, encoding="utf-8")
(base / "fichier_absent").mkdir()
PY
grep -qx "cle_v1_egale_parent_v2=0" "$OUT" || fail=1

# 3. la commande, exercée sur chaque registre fabriqué
cas() {  # cas <nom> <mode du fichier ou -> <attendu : True | False | erreur>
  local f=$T/$1/variants.json
  if [ "$2" != "-" ] && [ -f "$f" ]; then chmod "$2" "$f"; fi
  SIM_REG="$f" bash -c "$(cat "$T/commande_sim.txt")" > "$T/$1/sortie.txt" 2> "$T/$1/erreur.txt"
  local r=$? got
  got=$(tr -d '\n' < "$T/$1/sortie.txt")
  log "cas=$1 sortie=${got:--} rc=$r attendu=$3"
  case "$3" in
    True) { [ "$got" = "True" ] && [ "$r" = "0" ]; } || fail=1 ;;
    False) { [ "$got" = "False" ] && [ "$r" = "0" ]; } || fail=1 ;;
    erreur) { [ -z "$got" ] && [ "$r" != "0" ]; } || fail=1 ;;
  esac
}
cas temoin 600 True
cas mode_644 644 False
cas parent_absent 600 False
cas parent_avec_verdict 600 False
cas parent_avec_differee 600 False
cas variante_en_trop 600 False
cas racine_en_trop 600 False
cas sel_court 600 False
cas sel_non_hexadecimal 600 False
cas fichier_absent - erreur
cas json_illisible 600 erreur

rm -rf "$T"
[ ! -e "$T" ]; log "temporaire_supprime=$?"
log "rc=$fail"
exit $fail
