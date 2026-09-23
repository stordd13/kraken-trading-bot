#!/bin/bash
# C3a pre-merge gate (§ L.5): single rerun of the suite (all but the determinism file) after the
# async-cleanup incident of the first pass — kept as suite_run1_async_cleanup_incident.xml, full
# output in checks_6f7ed8e.log. Same command as checks.sh. Then the two victim files alone, as C2
# did (results/c2_replay/determinism_server/README.md). The 24 determinism tests are never rerun.
EXPECTED=6f7ed8e99191a795a42ca3a8ce253407d963e546
HERE=/home/bruno/c3a-determinism
OUT=$HERE/junit
cd $HERE/repo || exit 3
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
export POETRY_VIRTUALENVS_IN_PROJECT=true
SHA=$(git rev-parse HEAD)
if [ "$SHA" != "$EXPECTED" ]; then echo "HEAD $SHA != expected $EXPECTED — refusing to run"; exit 3; fi
echo "# C3a pre-merge gate § L.5 — suite rerun after the async-cleanup incident of the first pass"
echo "# SHA: $SHA"
echo "# date: $(date -u +%FT%TZ)"
echo "# first pass (checks_6f7ed8e.log, 22:04:23Z -> 22:11:26Z): 2 failed, 2612 passed, 6 skipped, 1 error —"
echo "#   ERROR  tests/test_main.py::TestKrakenBotStop::test_stop_handles_component_errors (setup, aiohttp ResourceWarning)"
echo "#   FAILED tests/test_main.py::TestKrakenBotStart::test_start_subscribes_1m_when_router_crash_protector_is_configured (pycares callback, loop closed)"
echo "#   FAILED tests/test_scripts/test_b4_campaign_configs.py::TestEngineMinOrder::test_order_below_floor_is_skipped_and_default_keeps_it (ExceptionGroup of 5 unclosed aiohttp sessions, body passed)"
echo
echo '$ nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml='"$OUT"'/suite.xml --ignore=tests/test_scripts/test_run_p6_determinism.py'
nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml=$OUT/suite.xml --ignore=tests/test_scripts/test_run_p6_determinism.py
echo "[rc=$?] $(date -u +%FT%TZ)"
echo
echo '$ poetry run pytest -q -p no:cacheprovider tests/test_main.py   # first victim file, alone'
poetry run pytest -q -p no:cacheprovider tests/test_main.py
echo "[rc=$?]"
echo
echo '$ poetry run pytest -q -p no:cacheprovider tests/test_scripts/test_b4_campaign_configs.py   # second victim file, alone'
poetry run pytest -q -p no:cacheprovider tests/test_scripts/test_b4_campaign_configs.py
echo "[rc=$?]"
echo
echo "# end: $(date -u +%FT%TZ)"
echo "=== SUITE RERUN END"
