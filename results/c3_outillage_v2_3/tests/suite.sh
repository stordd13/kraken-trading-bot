#!/bin/bash
# C3 outillage v2.3 — suite complète locale SANS TUNNEL (brief § 3.3) : le greffon `gate_sans_tunnel` de la porte v2.2
# (results/c3_v2_2/tests/gate_sans_tunnel.py) refuse 127.0.0.1:5432 et :5433 au seul processus pytest ; les tests base
# s'ignorent comme en CI. Les 24 `_full` (porte § L.5, serveur) sont désélectionnés.
# Usage : bash suite_gel.sh <étiquette>. Sortie brute au scratchpad si SUITE_RAW est posé, sinon mktemp ; extrait
# versionné : suite_<étiquette>.out (en-tête, résumé, lignes FAILED/ERROR/XPASS/XFAIL, ignorés par raison).
# rc=0 ssi pytest code 0 et aucune ligne FAILED / ERROR / XPASS. Ne jamais modifier un fichier suivi pendant le run.
set -o pipefail
set -u
unset VIRTUAL_ENV
LABEL="${1:?étiquette}"
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
DIR=results/c3_outillage_v2_3/tests
OUT="$DIR/suite_${LABEL}.out"
RAW="${SUITE_RAW:-$(mktemp -t suite_raw)}"
{
  echo "# suite — $LABEL — $(date -u +%FT%TZ)"
  echo "# HEAD $(git rev-parse HEAD) branche $(git branch --show-current)"
  echo "# fichiers suivis modifiés (non commités) : $(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
  echo "# commande : PYTHONPATH=results/c3_v2_2/tests poetry run pytest -q -p no:cacheprovider -p gate_sans_tunnel -rsxX -k \"not test_determinism_parallel_vs_serial_full\""
} > "$OUT"
if nc -z -w 2 127.0.0.1 5433 > /dev/null 2>&1; then
  echo "tunnel_5433=ouvert (non ouvert par ce script ; neutralisé pour pytest par gate_sans_tunnel)" >> "$OUT"
else
  echo "tunnel_5433=fermé" >> "$OUT"
fi
PYTHONPATH="results/c3_v2_2/tests${PYTHONPATH:+:$PYTHONPATH}" poetry run pytest -q -p no:cacheprovider \
  -p gate_sans_tunnel -rsxX -k "not test_determinism_parallel_vs_serial_full" > "$RAW" 2>&1
rc=$?
echo "pytest_exit=$rc" >> "$OUT"
echo "fin=$(date -u +%FT%TZ)" >> "$OUT"
grep -E '^(FAILED|ERROR|XPASS|XFAIL) ' "$RAW" | sed 's| - .*||' | LC_ALL=C sort >> "$OUT"
echo "## ignorés, par raison" >> "$OUT"
grep -E '^SKIPPED ' "$RAW" | sed -E 's/^SKIPPED \[([0-9]+)\] [^:]+(:[0-9]+)?: /\1 /' \
  | awk '{n=$1; $1=""; c[$0]+=n} END {for (r in c) print c[r] " :" r}' | LC_ALL=C sort -rn >> "$OUT"
grep -E '^[0-9]+ (passed|failed)' "$RAW" | tail -n 1 | sed 's/^/resume=/' >> "$OUT"
bad=$(grep -cE '^(FAILED|ERROR|XPASS) ' "$RAW")
echo "failed_error_xpass=$bad" >> "$OUT"
echo "brut=$RAW" >> "$OUT"
if [ "$rc" -eq 0 ] && [ "$bad" -eq 0 ]; then echo "rc=0" >> "$OUT"; exit 0; fi
echo "rc=1" >> "$OUT"
exit 1
