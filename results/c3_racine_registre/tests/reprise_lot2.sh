#!/bin/bash
# C3 racine du registre, lot 2 — preuve de reprise (plans/lot2.md L6) : chaque pilote, vérificateur et script du lot est
# repris du lot 2 de l'outillage v2.3 ; ce script consigne, fichier par fichier, TOUTES les lignes qui diffèrent de la
# source (`diff`, lignes `<` source, `>` reprise) et leur nombre. Relecture humaine : les lignes changées sont les
# chemins (`results/c3_racine_registre/`, `runs/c3_racine_registre`, archives `c3_racine_registre_…`, tmux
# `c3-racine-registre-`), la branche, les constantes (sha du manifeste, `--campaign`, `--now`), les en-têtes ; la phase
# `gate` retirée (porte non rejouée, L5) de preflight, launch, wait, fetch, archive, postflight, pilot_dryrun et
# verify_adverse ; `manifest_check.sh` réécrit pour le delta du lot (L2). Le manifeste est comparé à part
# (manifest_check.out). Scripts neufs, sans source : `invariance_porte.sh`, `reprise_lot2.sh`. Aucune ligne ne porte un
# sha d'artefact du chemin sélection.
# Usage : bash reprise_lot2.sh. Sortie : reprise_lot2.out ; rc=0 ssi chaque source et chaque reprise existent (le
# jugement est la relecture).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
S=results/c3_outillage_v2_3
D=results/c3_racine_registre
OUT=$D/tests/reprise_lot2.out
PAIRS=(
  conformite/server/run_conformite.sh conformite/server/verify_attendu.py conformite/attendu.md
  tests/preflight.sh tests/launch.sh tests/wait.sh tests/fetch.sh tests/archive.sh tests/postflight.sh
  tests/verify_conformite.sh tests/verify_adverse.sh tests/pilot_dryrun.sh tests/events.sh tests/manifest_check.sh
  tests/interdits_lot2.sh tests/interdits_lot2_adverse.sh tests/lint_lot2.sh
)
fail=0
: > "$OUT"
echo "# reprise_lot2 — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
for p in "${PAIRS[@]}"; do
  if [ ! -f "$S/$p" ] || [ ! -f "$D/$p" ]; then echo "fichier_absent $p" >> "$OUT"; fail=1; continue; fi
  n_src=$(diff "$S/$p" "$D/$p" | grep -c '^<')
  n_dst=$(diff "$S/$p" "$D/$p" | grep -c '^>')
  echo "## $S/$p -> $D/$p : lignes source changées=$n_src, lignes reprise=$n_dst" >> "$OUT"
  if [ "$p" = conformite/attendu.md ]; then
    echo "(attendu : réécrit pour ce lot ; diff non recopié, relu en entier)" >> "$OUT"
    continue
  fi
  diff "$S/$p" "$D/$p" | grep -E '^[<>]' | cut -c1-220 >> "$OUT"
done
echo "rc=$fail" >> "$OUT"
exit $fail
