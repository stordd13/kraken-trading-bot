#!/bin/bash
# Seconde campagne C3 comptée, famille grid-atr-v4, relance unique (repris de results/c3_campagne_grid/tests/
# reprise.sh) — preuve de reprise (brief § 2.2 : « scripts repris de results/c3_campagne_grid/tests/ par substitutions
# comptées ») : chaque pilote, vérificateur et script du chantier repris du chantier v1 y est comparé à sa source ; ce
# script consigne, fichier par fichier, le nombre de lignes qui diffèrent et TOUTES ces lignes (`diff`, `<` source,
# `>` reprise), sauf pour l'attendu, réécrit et relu en entier. Les deux scripts d'archive ont pour source l'archive.sh
# du v1 ; leur corps distant n'apparaît dans aucun diff (identique à l'octet, prouvé aussi par archive_dryrun.sh). Les
# empreintes de 64 hex des lignes recopiées sont tronquées à 16 hex (règle d'interdits.sh, A4 du chantier v1). Scripts
# neufs, sans source : stop1_registre.sh (A2'), mutants_archive.sh. Non repris : les trois scripts du diagnostic v1
# (diagnostic_entry.sh, diagnostic_preuve.sh, schema_observations.sh). Le manifeste est comparé à part
# (manifest_check.out).
# Usage : bash reprise.sh. Sortie : reprise.out ; rc=0 ssi chaque source et chaque reprise existent (le jugement est la
# relecture).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
S=results/c3_campagne_grid
D=results/c3_campagne_grid_v2
OUT=$D/tests/reprise.out
# paires « source reprise » (chemins relatifs à S et à D)
PAIRS=(
  "server/run_campagne.sh server/run_campagne.sh"
  "server/verify_attendu.py server/verify_attendu.py"
  "attendu.md attendu.md"
  "tests/preflight.sh tests/preflight.sh"
  "tests/launch.sh tests/launch.sh"
  "tests/wait.sh tests/wait.sh"
  "tests/fetch.sh tests/fetch.sh"
  "tests/verify.sh tests/verify.sh"
  "tests/archive.sh tests/archive.sh"
  "tests/archive.sh tests/archive_prealable.sh"
  "tests/postflight.sh tests/postflight.sh"
  "tests/verify_adverse.sh tests/verify_adverse.sh"
  "tests/pilot_dryrun.sh tests/pilot_dryrun.sh"
  "tests/mutants_pilote.sh tests/mutants_pilote.sh"
  "tests/events.sh tests/events.sh"
  "tests/table_10_1.sh tests/table_10_1.sh"
  "tests/archive_dryrun.sh tests/archive_dryrun.sh"
  "tests/manifest_check.sh tests/manifest_check.sh"
  "tests/interdits.sh tests/interdits.sh"
  "tests/interdits_adverse.sh tests/interdits_adverse.sh"
  "tests/lint.sh tests/lint.sh"
  "tests/tunnel.sh tests/tunnel.sh"
  "tests/ci_status.sh tests/ci_status.sh"
  "tests/reprise.sh tests/reprise.sh"
)
REWRITTEN=" attendu.md "
fail=0
: > "$OUT"
echo "# reprise — $(date -u +%FT%TZ) — HEAD $(git rev-parse HEAD)" >> "$OUT"
for pair in "${PAIRS[@]}"; do
  src=${pair%% *}
  dst=${pair#* }
  if [ ! -f "$S/$src" ] || [ ! -f "$D/$dst" ]; then echo "fichier_absent $src -> $dst" >> "$OUT"; fail=1; continue; fi
  n_src=$(diff "$S/$src" "$D/$dst" | grep -c '^<')
  n_dst=$(diff "$S/$src" "$D/$dst" | grep -c '^>')
  echo "## $S/$src -> $D/$dst : lignes source changées=$n_src, lignes reprise=$n_dst" >> "$OUT"
  case "$REWRITTEN" in
    *" $dst "*)
      echo "(réécrit pour ce chantier ; diff non recopié, relu en entier)" >> "$OUT"
      continue
      ;;
  esac
  diff "$S/$src" "$D/$dst" | grep -E '^[<>]' | sed -E 's/([0-9a-f]{16})[0-9a-f]{48}/\1…/g' | cut -c1-220 >> "$OUT"
done
echo "rc=$fail" >> "$OUT"
exit $fail
