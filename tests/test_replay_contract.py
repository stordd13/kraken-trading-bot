"""C2 replay contract helpers (``krakenbot.replay_contract``): pure, mirror of the C1 guard."""

from __future__ import annotations

import pytest

from krakenbot.replay_contract import (
    REPLAY_VERSION,
    ReplayVersionError,
    entry_replay_version,
    require_replay_version,
)


def test_replay_version_is_2_and_absent_means_pre_c2() -> None:
    assert REPLAY_VERSION == 2
    assert entry_replay_version({"replay_version": 2}) == 2
    assert entry_replay_version({"replay_version": "2"}) == 2
    # top level only: a nested value never counts (the key is never inside to_dict())
    assert entry_replay_version({"all": {"replay_version": 2}}) is None
    assert entry_replay_version({"fees": "bybit", "metrics_version": 2}) is None


def test_require_replay_version_accepts_homogeneous_and_skips_errors() -> None:
    require_replay_version({"a": {"replay_version": 2}, "b": {"replay_version": 2}})
    require_replay_version({"a": {"replay_version": 2}, "bad": {"error": "boom"}})
    require_replay_version({})


def test_require_replay_version_refuses_pre_c2_and_mixed_files() -> None:
    with pytest.raises(ReplayVersionError, match="absent: pre-C2 file"):
        require_replay_version({"a": {"fees": "bybit", "metrics_version": 2}}, path="x.json")
    with pytest.raises(ReplayVersionError, match="x.json"):
        require_replay_version({"a": {"fees": "bybit", "metrics_version": 2}}, path="x.json")
    with pytest.raises(ReplayVersionError, match="replay_version=1"):
        require_replay_version({"a": {"replay_version": 1}})
    with pytest.raises(ReplayVersionError):
        require_replay_version({"a": {"replay_version": 2}, "b": {"replay_version": 3}})
