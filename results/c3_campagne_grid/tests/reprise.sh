#!/bin/bash
# Première campagne C3 comptée, famille grid-atr-v4 — preuve de reprise (brief § 2.2 : « adaptés par substitutions
# comptées ») : chaque pilote, vérificateur et script du chantier repris de results/c3_racine_registre/ y est comparé
# à sa source ; ce script consigne, fichier par fichier, le nombre de lignes qui diffèrent et TOUTES ces lignes
# (`diff`, `<` source, `>` reprise), sauf pour les fichiers réécrits (attendu, archive, contrôle du manifeste), relus
# en entier. Les empreintes de 64 hex des lignes recopiées sont tronquées à 16 hex (règle d'interdits.sh, A4 : une
# sortie se filtre, la règle ne s'élargit jamais). Scripts neufs, sans source : reprise.sh, table_10_1.sh,
# mutants_pilote.sh, archive_dryrun.sh. Le manifeste est comparé à part (manifest_check.out).
# Usage : bash reprise.sh. Sortie : reprise.out ; rc=0 ssi chaque source et chaque reprise existent (le jugement est la
# relecture).
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
S=results/c3_racine_registre
D=results/c3_campagne_grid
OUT=$D/tests/reprise.out
# paires « source reprise » (chemins relatifs à S et à D)
PAIRS=(
  "conformite/server/run_conformite.sh server/run_campagne.sh"
  "conformite/server/verify_attendu.py server/verify_attendu.py"
  "conformite/attendu.md attendu.md"
  "tests/preflight.sh tests/preflight.sh"
  "tests/launch.sh tests/launch.sh"
  "tests/wait.sh tests/wait.sh"
  "tests/fetch.sh tests/fetch.sh"
  "tests/verify_conformite.sh tests/verify.sh"
  "tests/archive.sh tests/archive.sh"
  "tests/postflight.sh tests/postflight.sh"
  "tests/verify_adverse.sh tests/verify_adverse.sh"
  "tests/pilot_dryrun.sh tests/pilot_dryrun.sh"
  "tests/events.sh tests/events.sh"
  "tests/manifest_check.sh tests/manifest_check.sh"
  "tests/interdits_lot2.sh tests/interdits.sh"
  "tests/interdits_lot2_adverse.sh tests/interdits_adverse.sh"
  "tests/lint_lot2.sh tests/lint.sh"
  "tests/tunnel.sh tests/tunnel.sh"
  "tests/ci_status.sh tests/ci_status.sh"
)
REWRITTEN=" attendu.md tests/archive.sh tests/manifest_check.sh "
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
