#!/bin/bash
# C3a pre-merge gate (docs/protocole_c3.md § L.5): checks at the delivered SHA, on the server,
# isolated checkout, local database. Each command is printed before its block (format of
# results/c2_replay/determinism_server/run2_f585e8b/checks_f585e8b.log). Run after run24.sh.
set -o pipefail
EXPECTED=6f7ed8e99191a795a42ca3a8ce253407d963e546
HERE=/home/bruno/c3a-determinism
OUT=$HERE/junit
cd $HERE/repo || exit 3
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
export POETRY_VIRTUALENVS_IN_PROJECT=true
SHA=$(git rev-parse HEAD)
if [ "$SHA" != "$EXPECTED" ]; then echo "HEAD $SHA != expected $EXPECTED — refusing to run"; exit 3; fi
echo "# C3a pre-merge gate § L.5 — checks at the delivered SHA"
echo "# SHA: $SHA ($(git describe --tags))"
echo "# date: $(date -u +%FT%TZ)"
echo "# host: server, local database, isolated checkout $HERE/repo (HEAD detached), venv .venv"
echo "# python: $(poetry run python --version 2>&1) · $(poetry run ruff --version 2>&1) · $(poetry run mypy --version 2>&1)"
echo
echo '$ git status --short   # (expect: empty — .env is ignored)'
git status --short
echo
echo '$ sha256sum docs/protocole_c3.md   # frozen at d931293'
sha256sum docs/protocole_c3.md
echo
echo '$ git diff --stat 2b62530 HEAD -- src tests config pyproject.toml poetry.lock   # (expect: empty)'
git diff --stat 2b62530 HEAD -- src tests config pyproject.toml poetry.lock
echo "[end]"
echo
echo '$ git diff --stat 2b62530 HEAD -- scripts   # (expect: scripts/audit/c3_verdict.py only, commit acaeaf6)'
git diff --stat 2b62530 HEAD -- scripts
echo "[end]"
echo
echo '$ git log --oneline 2b62530..HEAD -- scripts'
git log --oneline 2b62530..HEAD -- scripts
echo
echo '$ git show 2b62530:scripts/audit/c3_verdict.py > '"$HERE"'/c3_verdict_2b62530.py ; poetry run python '"$HERE"'/ast_bytecode_check.py '"$HERE"'/c3_verdict_2b62530.py scripts/audit/c3_verdict.py'
git show 2b62530:scripts/audit/c3_verdict.py > $HERE/c3_verdict_2b62530.py
poetry run python $HERE/ast_bytecode_check.py $HERE/c3_verdict_2b62530.py scripts/audit/c3_verdict.py
echo "[rc=$?]"
echo
echo '$ git diff --stat f585e8b HEAD -- src scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py scripts/p7_grids.py scripts/compute_benchmarks.py config pyproject.toml poetry.lock   # § L.3 (expect: pyproject.toml only)'
git diff --stat f585e8b HEAD -- src scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py scripts/p7_grids.py scripts/compute_benchmarks.py config pyproject.toml poetry.lock
echo "[end]"
echo
echo '$ nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml='"$OUT"'/suite.xml --ignore=tests/test_scripts/test_run_p6_determinism.py'
nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml=$OUT/suite.xml --ignore=tests/test_scripts/test_run_p6_determinism.py
echo "[rc=$?] $(date -u +%FT%TZ)"
echo
echo '$ nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml='"$OUT"'/short.xml -k "not full" tests/test_scripts/test_run_p6_determinism.py'
nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml=$OUT/short.xml -k "not full" tests/test_scripts/test_run_p6_determinism.py
echo "[rc=$?] $(date -u +%FT%TZ)"
echo
echo '$ poetry run pytest -q -p no:cacheprovider tests/test_strategies/test_grid_atr_v4_backward_compat.py   # gold hashes'
poetry run pytest -q -p no:cacheprovider tests/test_strategies/test_grid_atr_v4_backward_compat.py
echo "[rc=$?]"
echo
echo '$ poetry run pytest -q -p no:cacheprovider tests/test_scripts/test_c3_*.py   # the C3 tests (806 expected), included in suite.xml above'
poetry run pytest -q -p no:cacheprovider tests/test_scripts/test_c3_*.py
echo "[rc=$?]"
echo
echo '$ poetry run ruff check .'
poetry run ruff check .
echo "[rc=$?]"
echo
echo '$ poetry run ruff format --check .'
poetry run ruff format --check .
echo "[rc=$?]"
echo
echo '$ git ls-files "*.py" | xargs poetry run ruff format --check --force-exclude   # tracked files only'
git ls-files "*.py" | xargs poetry run ruff format --check --force-exclude
echo "[rc=$?]"
echo
echo '$ poetry run mypy src/ | tail -1 ; poetry run mypy src/ | grep feature_store.py:32 ; poetry run mypy src/ --ignore-missing-imports | tail -1'
poetry run mypy src/ 2>&1 | tail -1
poetry run mypy src/ 2>&1 | grep 'feature_store.py:32'
poetry run mypy src/ --ignore-missing-imports 2>&1 | tail -1
echo
echo "# --- innocuity (after the runs) $(date -u +%FT%TZ)"
START=$(grep -oE '^=== start [0-9T:Z-]+' $OUT/run24.log | awk '{print $3}')
END=$(date -u +%FT%TZ)
echo "# window: $START -> $END"
echo '$ systemctl is-active krakenbot-collector ; systemctl show krakenbot-collector -p NRestarts -p ActiveEnterTimestamp ; systemctl is-active krakenbot'
systemctl is-active krakenbot-collector
systemctl show krakenbot-collector -p NRestarts -p ActiveEnterTimestamp
systemctl is-active krakenbot
echo '$ ps -eo pid,stat,etime,cmd | awk '"'"'$2 ~ /Z/'"'"'   # zombies (expect: none)'
ps -eo pid,stat,etime,cmd | awk '$2 ~ /Z/'
echo '$ ps -eo pid,etime,cmd | grep -E "pytest|backtest" | grep -v grep   # residual (expect: none)'
ps -eo pid,etime,cmd | grep -E "pytest|backtest" | grep -v grep
echo '$ sudo -n docker exec krakenbot-db psql -U krakenbot -d krakenbot -c "<1m continuity per pair over the window>"'
sudo -n docker exec krakenbot-db psql -U krakenbot -d krakenbot -c "WITH t AS (SELECT pair, timestamp, LAG(timestamp) OVER (PARTITION BY pair ORDER BY timestamp) AS prev FROM market_data_ohlc WHERE exchange='bybit' AND interval=1 AND timestamp BETWEEN '$START' AND '$END') SELECT pair, COUNT(*) AS rows, COUNT(*) FILTER (WHERE timestamp - prev > interval '1 minute') AS gaps, MAX(timestamp - prev) AS max_gap FROM t GROUP BY pair ORDER BY pair;"
echo
echo "# end: $(date -u +%FT%TZ)"
