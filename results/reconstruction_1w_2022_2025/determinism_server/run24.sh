#!/bin/bash
# Reconstruction 1 w — pre-merge server gate: the 24 full-range determinism tests on the server, no tunnel
# (diff § L.3 not empty on src/: OHLCDerived model, option A). Recipe of C2 / C3a
# (results/c3a_determinism_server/run_6f7ed8e/run24.sh), paths changed, expected SHA asserted, script versioned.
# One invocation per combo, one JUnit report each. STOPS on any failure (a hash mismatch is a determinism bug
# to investigate, never something to re-roll).
EXPECTED=5cb8a24e7e594d9dbd93d4f39af8654a9891e3a4
cd /home/bruno/r1w-determinism/repo || exit 3
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV
export POETRY_VIRTUALENVS_IN_PROJECT=true
OUT=/home/bruno/r1w-determinism/junit
mkdir -p $OUT
SHA=$(git rev-parse HEAD)
if [ "$SHA" != "$EXPECTED" ]; then echo "=== HEAD $SHA != expected $EXPECTED — refusing to run"; exit 3; fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "=== tracked tree not clean — refusing to run"; exit 3; fi
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
