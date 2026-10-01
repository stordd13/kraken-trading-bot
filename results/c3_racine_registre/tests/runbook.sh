#!/bin/bash
# C3 racine du registre, lot 1 — le runbook est commité TEL QUE REÇU (brief § 0.2, plan D7) : le fichier reçu et
# skills/registry.md sont identiques à l'octet (cmp), même sha256, même taille, même nombre de lignes. Le sha256 imprimé
# est celui d'un fichier du chantier (règle 64 hex, plan D10).
# Usage : bash runbook.sh <étiquette> <fichier reçu>. Sortie : runbook_<étiquette>.out ; rc=0 ssi identiques.
set -o pipefail
set -u
LABEL="${1:?étiquette}"
SRC="${2:?fichier reçu}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DST=skills/registry.md
OUT=results/c3_racine_registre/tests/runbook_${LABEL}.out
{
  echo "# runbook — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
} > "$OUT"
if [ ! -f "$SRC" ] || [ ! -f "$DST" ]; then echo "fichier_absent" >> "$OUT"; echo "rc=2" >> "$OUT"; exit 2; fi
cmp -s "$SRC" "$DST"; c=$?
{
  echo "recu=$(basename "$SRC") octets=$(wc -c < "$SRC" | tr -d ' ') lignes=$(wc -l < "$SRC" | tr -d ' ') sha256=$(shasum -a 256 "$SRC" | cut -d' ' -f1)"
  echo "commite=$DST octets=$(wc -c < "$DST" | tr -d ' ') lignes=$(wc -l < "$DST" | tr -d ' ') sha256=$(shasum -a 256 "$DST" | cut -d' ' -f1)"
  echo "identiques_cmp=$c"
} >> "$OUT"
echo "rc=$c" >> "$OUT"
exit $c
