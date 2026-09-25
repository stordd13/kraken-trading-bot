#!/bin/bash
# C2 pre-merge gate: the 24 full-range determinism tests, on the server, no tunnel.
# One invocation per combo, one JUnit report each. STOPS on any failure (a hash mismatch
# is a determinism bug to investigate, never something to re-roll).
cd /home/bruno/c2-determinism/repo
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
OUT=/home/bruno/c2-determinism/junit
mkdir -p $OUT
SHA=$(git rev-parse HEAD)
echo "=== SHA $SHA"
echo "=== start $(date -u +%FT%TZ)"
for c in $(seq 0 23); do
  echo "--- combo$c start $(date -u +%FT%TZ)"
  nice -n 5 poetry run pytest -p no:cacheprovider -q --durations=0 \
    --junitxml=$OUT/combo$c.xml \
    "tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[combo$c]" \
    > $OUT/combo$c.log 2>&1
  rc=$?
  dur=$(grep -oE "^[0-9.]+s call" $OUT/combo$c.log | head -1)
  if [ $rc -eq 0 ]; then
    echo "--- combo$c PASSED $dur $(date -u +%FT%TZ)"
  else
    echo "--- combo$c FAILED rc=$rc $(date -u +%FT%TZ) — STOPPING, no retry"
    tail -25 $OUT/combo$c.log
    exit 2
  fi
done
echo "=== ALL 24 DONE $(date -u +%FT%TZ)"
