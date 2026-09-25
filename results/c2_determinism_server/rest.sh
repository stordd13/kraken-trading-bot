#!/bin/bash
cd /home/bruno/c2-determinism/repo
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
OUT=/home/bruno/c2-determinism/junit
echo "=== SHA $(git rev-parse HEAD)"
echo "=== [1/3] suite (all but the determinism file, run separately combo by combo) $(date -u +%FT%TZ)"
nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml=$OUT/suite.xml \
  --ignore=tests/test_scripts/test_run_p6_determinism.py
echo "=== [1/3] exit $? $(date -u +%FT%TZ)"
echo "=== [2/3] ruff"
poetry run ruff check . ; echo "ruff-check rc=$?"
poetry run ruff format --check . 2>&1 | tail -3
echo "=== [3/3] mypy"
poetry run mypy src/ 2>&1 | tail -2
echo "--- with --ignore-missing-imports"
poetry run mypy src/ --ignore-missing-imports 2>&1 | tail -1
echo "=== REST DONE $(date -u +%FT%TZ)"
