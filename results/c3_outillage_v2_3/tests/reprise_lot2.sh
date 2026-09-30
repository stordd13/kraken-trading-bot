#!/bin/bash
# C3 outillage v2.3, lot 2 — preuve de reprise (plans/lot2.md § 4) : chaque pilote, vérificateur et script du lot est
# repris du lot 3 v2.2 ; ce script consigne, fichier par fichier, TOUTES les lignes qui diffèrent de la source v2.2
# (`diff`, lignes `<` source, `>` reprise) et leur nombre. Relecture humaine : les lignes changées sont les chemins
# (`results/c3_outillage_v2_3/`, `runs/c3_outillage_v2_3`, archives `c3_outillage_v2_3_…`, tmux `c3-outillage-v23-`),
# la branche, les constantes (sha du protocole v2.3 et du manifeste v2.3, `--campaign`, `--now`), les en-têtes et
# renvois de plan ; `manifest_check.sh`, `postflight.sh` et `lint_lot2.sh` sont réécrits (écarts déclarés au plan et
# dans leur en-tête). Aucune ligne ne porte un sha d'artefact du chemin sélection.
# Sortie : reprise_lot2.out ; rc=0 ssi chaque source et chaque reprise existent (le jugement est la relecture).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
S=results/c3_outillage_v2_2
D=results/c3_outillage_v2_3
OUT=$D/tests/reprise_lot2.out
PAIRS=(
  conformite/server/run_conformite.sh conformite/server/verify_attendu.py gate_L5/run_gate.sh
  tests/preflight.sh tests/launch.sh tests/wait.sh tests/fetch.sh tests/archive.sh tests/postflight.sh
  tests/verify_conformite.sh tests/verify_gate.sh tests/verify_adverse.sh tests/pilot_dryrun.sh tests/events.sh
  tests/manifest_check.sh
)
fail=0
: > "$OUT"
echo "# reprise_lot2 — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
for p in "${PAIRS[@]}" "tests/lint_lot3.sh=tests/lint_lot2.sh"; do
  src=${p%%=*}
  dst=${p#*=}
  if [ ! -f "$S/$src" ] || [ ! -f "$D/$dst" ]; then echo "fichier_absent $src -> $dst" >> "$OUT"; fail=1; continue; fi
  n_src=$(diff "$S/$src" "$D/$dst" | grep -c '^<')
  n_dst=$(diff "$S/$src" "$D/$dst" | grep -c '^>')
  echo "## $S/$src -> $D/$dst : lignes source changées=$n_src, lignes reprise=$n_dst" >> "$OUT"
  diff "$S/$src" "$D/$dst" | grep -E '^[<>]' | cut -c1-220 >> "$OUT"
done
echo "rc=$fail" >> "$OUT"
exit $fail
