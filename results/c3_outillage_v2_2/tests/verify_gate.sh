#!/bin/bash
# C3 outillage v2.2, lot 3 — vérification de la porte § L.5 option 1 (plans/lot3.md § 6), item par item, sur les
# seuls extraits rapatriés : status.txt, pilot_exit.txt, alembic_before.txt, alembic_after.txt, pytest_summary.txt.
# Aucun journal ni JUnit de combo n'est lu (ils restent archivés : `--showlocals`). Prouvé avant son premier usage par
# tests/verify_adverse.sh (témoin sain à 0, chaque cas dévié ≠ 0 ; condition du GO).
# usage : bash verify_gate.sh <S2, 40 hex> [répertoire des preuves] [fichier de sortie] [sha256 du pilote]
#   défauts : results/c3_outillage_v2_2/gate_L5, <répertoire>/verify_gate.out, sha256 de gate_L5/run_gate.sh.
# Une clé absente vaut écart. rc=0 ssi tous les items sont tenus.
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
SHA=${1:?sha}
DIR=${2:-results/c3_outillage_v2_2/gate_L5}
OUT=${3:-$DIR/verify_gate.out}
PILOT_SHA=${4:-$(shasum -a 256 results/c3_outillage_v2_2/gate_L5/run_gate.sh | cut -d' ' -f1)}
KRAKENBOT_SUFFIX=/runs/c3_outillage/gate/repo/src/krakenbot/__init__.py
HEAD_LINE="c3bd1e7a0001 (head)"
ST=$DIR/status.txt

: > "$OUT"
# value <clé> : la valeur de la première ligne `clé=…` de status.txt, ou le marqueur __ABSENT__
value() {
  local line
  line=$(grep -m 1 -E "^$1=" "$ST" 2> /dev/null) || { echo "__ABSENT__"; return; }
  echo "${line#*=}"
}
field() {  # field <valeur de ligne> <sous-clé> : la valeur de `sous-clé=…` dans la ligne, ou __ABSENT__
  local w
  for w in $1; do
    case "$w" in "$2="*) echo "${w#*=}"; return ;; esac
  done
  echo "__ABSENT__"
}
held=0
total=0
item() {  # item <libellé> <0 | 1>
  total=$((total + 1))
  if [ "$2" = "0" ]; then held=$((held + 1)); echo "tenu  — $1" >> "$OUT"; else echo "ÉCART — $1" >> "$OUT"; fi
}

# 1. gardes
g=$(value guard)
ok=1
if [ "${g%% *}" = "0" ] && [ "$(field "$g" sha)" = "$SHA" ] && [ "$(field "$g" pytest)" != "__ABSENT__" ] \
  && [[ "$(field "$g" krakenbot)" == *"$KRAKENBOT_SUFFIX" ]] && [ "$(value pilot_sha256)" = "$PILOT_SHA" ] \
  && [ "$(value pilot_copy)" = "0" ]; then ok=0; fi
item "1 gardes : guard=0 au SHA S2, pytest présent, krakenbot du clone, pilote = blob du SHA" "$ok"

# 2. base
ok=1
if [ "$(value alembic_before)" = "0" ] && [ "$(value alembic_after)" = "0" ] \
  && cmp -s "$DIR/alembic_before.txt" "$DIR/alembic_after.txt" \
  && grep -qF "$HEAD_LINE" "$DIR/alembic_before.txt"; then ok=0; fi
item "2 base : alembic 0 avant et après, identiques, c3bd1e7a0001 (head)" "$ok"

# 3. les 24 combos : rc=0 ET JUnit 1/0/0/0, chacun ; full=0 ; agrégat
ok=0
for c in $(seq 0 23); do
  v=$(value "combo$c")
  case "$v" in "0 junit=1/0/0/0 at="*) ;; *) ok=1 ;; esac
done
if [ "$(value full)" != "0" ] \
  || [ "$(value junit_total)" != "tests:24,failures:0,errors:0,skipped:0,missing:0" ]; then ok=1; fi
item "3 les 24 combos en rc=0 et JUnit 1/0/0/0, full=0, agrégat tests:24 sans échec, erreur, skip ni manquant" "$ok"

# 4. extrait : 24 en-têtes, 24 lignes `call`, 24 `1 passed`
ok=1
S=$DIR/pytest_summary.txt
if [ "$(value extract)" = "0" ] && [ "$(grep -cE '^combo[0-9]+$' "$S" 2> /dev/null)" = "24" ] \
  && [ "$(grep -cE '^  [0-9.]+s call ' "$S" 2> /dev/null)" = "24" ] \
  && [ "$(grep -cE '^  1 passed in ' "$S" 2> /dev/null)" = "24" ]; then ok=0; fi
item "4 extrait : pytest_summary.txt porte 24 lignes call et 24 lignes 1 passed" "$ok"

# 5. innocuité : arbre du clone, interpréteur, collector et service inchangés
ok=1
cb=$(value collector_before)
sb=$(value service_before)
if [ "$(value tree_after)" = "0" ] && [ "$(value interpreter_check)" = "0" ] \
  && [ "${cb%% *}" = "active" ] && [ "$cb" = "$(value collector_after)" ] \
  && [ "$sb" != "__ABSENT__" ] && [ "$sb" = "$(value service_after)" ] && [ "$(field "$sb" dirty)" = "0" ]; then
  ok=0
fi
item "5 innocuité : arbre du clone propre, interpréteur du clone, collector et service inchangés" "$ok"

# 6. code du pilote
ok=1
if [ "$(tr -d '[:space:]' < "$DIR/pilot_exit.txt" 2> /dev/null)" = "0" ]; then ok=0; fi
item "6 pilote : code de sortie 0" "$ok"

echo "$held/$total items tenus" >> "$OUT"
if [ "$held" -eq "$total" ]; then rc=0; else rc=1; fi
echo "rc=$rc" >> "$OUT"
exit $rc
