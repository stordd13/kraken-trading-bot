"""``scripts/audit/c3b_prefix.py`` — le producteur, temps 1 : ordre des refus, run unique, sorties (C3b lot 3).

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 3 » ; plan du lot validé le 2026-09-27. Les attendus viennent
du brief (codes 0 / 2 / 3, garde-fou 6, appel unique, déterminisme) et de la chaîne elle-même, appelée en
processus sur la sortie du producteur (``c3_anchor``, ``c3_entry``, ``c3_benchmark``, ``c3_select``).

**Herméticité construite, pas espérée** (amendement 3 du lot) : une fixture autouse remplace
``_db.ReadOnlyDatabaseManager`` dans ``c3b_prefix`` par un bouchon qui n'ouvre jamais de session, coupe ``.env``,
fait lever les quatre lectures en base de ``c3b_common`` et les trois chargeurs du moteur tant qu'un test ne les
remplace pas par des données synthétiques, et interdit tout vrai pool ``spawn`` (un processus neuf perdrait les
bouchons). Sous un mutant qui laisserait passer un refus, ``main`` s'arrête sur une ``AssertionError``, jamais
sur la base.
"""

# ruff: noqa: E402
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))
sys.path.insert(0, str(_PROJECT_ROOT / "tests"))

import c3_anchor as ca
import c3_benchmark as cb
import c3_common as cc
import c3_entry as ce
import c3_select as cs
import c3b_common as c3bc
import c3b_prefix as prefix

from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4
from test_scripts import test_c3b_common as pc

NOW = "2026-09-27T00:00:00+00:00"
STUB_URL = "postgresql+asyncpg://stub:stub@127.0.0.1:9/stub"  # jamais ouverte : le gestionnaire est bouchonné
CLEAN_SHA = "a" * 40


class _StubReadOnlyDb:
    """Remplace ``ReadOnlyDatabaseManager`` : enregistre sa construction, n'ouvre jamais de session."""

    built: list[str] = []

    def __init__(self, url: str) -> None:
        _StubReadOnlyDb.built.append(url)

    def read_session(self) -> Any:
        raise AssertionError("le test ne doit jamais ouvrir de session en base")

    async def close_db(self) -> None:
        return None


def _clean_provenance(script_relpath: str) -> dict[str, Any]:
    return {
        "git_sha": CLEAN_SHA,
        "branch": "feat/c3b-producteur",
        "script": script_relpath,
        "script_sha256": "0" * 64,
        "script_tracked": True,
        "tracked_tree_clean": True,
    }


def _unexpected(name: str) -> Callable[..., Any]:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"{name} non bouchonné : le test atteindrait la base")

    return refuse


def _unexpected_pool(workers: int) -> Any:
    raise AssertionError("aucun vrai pool spawn en test : il perdrait les bouchons")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    _StubReadOnlyDb.built = []
    monkeypatch.setattr(prefix, "ReadOnlyDatabaseManager", _StubReadOnlyDb)
    monkeypatch.setattr(prefix, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("DATABASE_URL", STUB_URL)
    monkeypatch.setattr(prefix, "get_settings", pc.engine_settings)
    monkeypatch.setattr(prefix, "git_provenance", _clean_provenance)
    monkeypatch.setattr(prefix, "_spawn_pool", _unexpected_pool)
    for name in ("probe_database", "fetch_stamps", "fetch_closes", "fetch_derived_stamps"):
        monkeypatch.setattr(c3bc, name, _unexpected(name))
    for name in ("_load_candles", "_load_candles_for_interval", "_load_candles_before"):
        monkeypatch.setattr(pc.bt.GridBacktester, name, _unexpected(name))


def install_database(
    monkeypatch: pytest.MonkeyPatch, data: pc.Market
) -> list[tuple[str, Any, Any]]:
    """Les quatre lectures en base, servies par le marché synthétique ; rend le journal des bornes lues."""
    reads: list[tuple[str, Any, Any]] = []

    async def probe(db: Any) -> dict[str, Any]:
        return {"transaction_read_only": "on", "alembic_version": ["c3bd1e7a0001"]}

    async def stamps(
        db: Any, *, exchange: str, pair: str, interval: int, start: datetime, end: datetime
    ) -> list[datetime]:
        assert exchange == "binance"
        reads.append(("stamps", start, end))
        return [c.timestamp for c in data.get((pair, interval), []) if start < c.timestamp <= end]

    async def closes(
        db: Any, *, exchange: str, pair: str, interval: int, start: datetime, end: datetime
    ) -> list[Any]:
        reads.append(("closes", start, end))
        return [
            (c.timestamp, c.close)
            for c in data.get((pair, interval), [])
            if start <= c.timestamp <= end
        ]

    async def derived(
        db: Any, *, exchange: str, pairs: Any, intervals: Any, start: datetime, end: datetime
    ) -> Any:
        reads.append(("derived", start, end))
        return {pair: {iv: [] for iv in intervals} for pair in pairs}

    monkeypatch.setattr(c3bc, "probe_database", probe)
    monkeypatch.setattr(c3bc, "fetch_stamps", stamps)
    monkeypatch.setattr(c3bc, "fetch_closes", closes)
    monkeypatch.setattr(c3bc, "fetch_derived_stamps", derived)
    return reads


def count_runs(
    monkeypatch: pytest.MonkeyPatch, *, fail_pair: str | None = None
) -> list[tuple[str, datetime, datetime]]:
    """Compte les appels à ``GridBacktester.run`` (le vrai run, délégué) ; ``fail_pair`` fait lever ce run-là."""
    calls: list[tuple[str, datetime, datetime]] = []
    original = pc.bt.GridBacktester.run

    async def counted(self: Any, pair: str, start: datetime, end: datetime) -> Any:
        calls.append((pair, start, end))
        if pair == fail_pair:
            raise RuntimeError("panne simulée du moteur")
        return await original(self, pair, start, end)

    monkeypatch.setattr(pc.bt.GridBacktester, "run", counted)
    return calls


def spy(monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> list[Any]:
    calls: list[Any] = []
    original = getattr(module, name)

    def recorded(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, recorded)
    return calls


def spy_classmethod(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []
    original = GrokGridATRAdaptiveV4.decision_timeframes

    def recorded(cls: Any, params: Any) -> Any:
        calls.append(params)
        return original(params)

    monkeypatch.setattr(GrokGridATRAdaptiveV4, "decision_timeframes", classmethod(recorded))
    return calls


def write_manifest(tmp_path: Path, payload: Mapping[str, Any], *, allow_nan: bool = False) -> Path:
    path = tmp_path / "manifest.json"
    if allow_nan:
        # Site adverse : un manifeste porteur d'un NaN n'est pas du JSON strict ; il s'écrit hors du writer.
        path.write_text(
            json.dumps(payload, allow_nan=True, sort_keys=True, indent=2), encoding="utf-8"
        )
    else:
        cc.write_json(path, payload)
    return path


def run_main(
    manifest: Path, out: Path, *, workers: int = 1, now: str = NOW
) -> tuple[int, list[dict[str, Any]]]:
    argv = [
        "--manifest",
        str(manifest),
        "--output-dir",
        str(out),
        "--workers",
        str(workers),
        "--now",
        now,
    ]
    with structlog.testing.capture_logs() as logs:
        code = prefix.main(argv)
    return code, logs


def events(logs: list[dict[str, Any]]) -> list[str]:
    return [entry["event"] for entry in logs if entry["log_level"] == "error"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nominal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kw: Any
) -> tuple[Path, list[Any], list[Any]]:
    data = pc.market()
    pc.install_market(monkeypatch, data)
    reads = install_database(monkeypatch, data)
    runs = count_runs(monkeypatch)
    manifest = write_manifest(tmp_path, pc.producer_manifest(**kw))
    return manifest, reads, runs


# ---------------------------------------------------------------------------
# Garde-fou 6 : avant tout (décision 6, amendement 4)
# ---------------------------------------------------------------------------


def test_a_campaign_window_is_refused_before_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Décision 6 : « aucun run du producteur ne touche la fenêtre ``2021-03-01 → 2026-06-29`` » ; brief § Lot 3 :
    refus code 2 tant que ``CAMPAIGN_UNLOCK`` n'existe pas — avant les paramètres, la classmethod, le moteur et la
    base, et rien n'est écrit."""
    monkeypatch.setattr(c3bc, "CAMPAIGN_UNLOCK", tmp_path / "absent")
    params = spy(monkeypatch, c3bc, "validate_params")
    classmethod_calls = spy_classmethod(monkeypatch)
    engines = spy(monkeypatch, c3bc, "build_engine")
    payload = pc.producer_manifest(
        start=datetime(2021, 3, 1, tzinfo=UTC), end=datetime(2026, 6, 29, tzinfo=UTC)
    )
    code, logs = run_main(write_manifest(tmp_path, payload), tmp_path / "out")
    assert code == 2
    assert events(logs) == ["campaign_window_locked"]
    assert (params, classmethod_calls, engines, _StubReadOnlyDb.built) == ([], [], [], [])
    assert not (tmp_path / "out").exists()


def test_a_window_ending_on_the_campaign_start_passes_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Borne : ``end == 2021-03-01`` n'est pas refusé (``end > 2021-03-01`` l'est) — le refus suivant vient d'un
    autre contrôle (ici l'arbre)."""
    monkeypatch.setattr(c3bc, "CAMPAIGN_UNLOCK", tmp_path / "absent")
    monkeypatch.setattr(
        prefix,
        "git_provenance",
        lambda relpath: {**_clean_provenance(relpath), "tracked_tree_clean": False},
    )
    payload = pc.producer_manifest(
        start=datetime(2020, 6, 1, tzinfo=UTC), end=datetime(2021, 3, 1, tzinfo=UTC)
    )
    code, logs = run_main(write_manifest(tmp_path, payload), tmp_path / "out")
    assert (code, events(logs)) == (2, ["uncommitted_tree"])


# ---------------------------------------------------------------------------
# Refus d'entrée — tous avant la base, aucun run partiel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("grid_levels", 12.5),
        ("grid_levels", "12"),
        ("grid_levels", True),
        ("grid_levels", None),
        ("bias_1d", "abc"),
        ("bias_1d", None),
        ("bias_1d", True),
    ],
)
def test_bad_params_are_refused_before_the_classmethod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, value: Any
) -> None:
    """Amendement 2 : « validation des paramètres AVANT la classmethod : ``grid_levels`` entier, ``bias_1d`` fini,
    refus nommé code 2 »."""
    classmethod_calls = spy_classmethod(monkeypatch)
    payload = pc.producer_manifest(classes=("C1",), pairs=("BTC/USDT",))
    payload["universe"]["candidates"][0]["params"] = {key: value}
    code, logs = run_main(write_manifest(tmp_path, payload), tmp_path / "out")
    assert (code, events(logs)) == (2, ["invalid_params"])
    (error,) = [entry for entry in logs if entry["log_level"] == "error"]
    assert error["problems"][0].startswith(f"universe.candidates[0].params.{key}")
    assert classmethod_calls == [] and _StubReadOnlyDb.built == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("bias_1d", "NaN"),
        ("bias_1d", "inf"),
        ("bias_1d", float("nan")),
        ("grid_levels", float("nan")),
    ],
)
def test_non_finite_params_are_refused_at_load_with_their_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, value: Any
) -> None:
    """Écart E9 : ``cc.load_manifest`` lève ``NonFiniteValueError`` (canonicalisation de l'identité) ; le producteur
    en fait un refus 2 qui nomme la clé — jamais une trace en code 1."""
    classmethod_calls = spy_classmethod(monkeypatch)
    payload = pc.producer_manifest(classes=("C1",), pairs=("BTC/USDT",))
    payload["universe"]["candidates"][0]["params"] = {key: value}
    code, logs = run_main(write_manifest(tmp_path, payload, allow_nan=True), tmp_path / "out")
    assert (code, events(logs)) == (2, ["manifest_refused"])
    (error,) = [entry for entry in logs if entry["log_level"] == "error"]
    assert f"universe.candidates[0].params.{key}" in error["problems"]
    assert classmethod_calls == []


@pytest.mark.parametrize(
    ("strategy", "params", "engine"),
    [
        (pc.STRATEGY, {"pause_1w_strong_bear": "false"}, "grid"),
        ("gemini_retour_moyenne", {}, "grid"),
        (
            pc.STRATEGY,
            {"grid_levels": 13},
            "signal",
        ),  # identité distincte du candidat C1 déjà présent
    ],
    ids=["pause-false", "non-grid", "moteur-signal"],
)
def test_a_decision_timeframes_refusal_runs_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    strategy: str,
    params: dict[str, Any],
    engine: str,
) -> None:
    """Brief § Lot 3 : « ``pause_1w_strong_bear: "false"`` dans un candidat → code 2 avant tout run, clé nommée ;
    stratégie non grid → code 2 » ; un seul candidat fautif refuse tout l'univers."""
    engines = spy(monkeypatch, c3bc, "build_engine")
    payload = pc.producer_manifest(classes=("C1",), pairs=("BTC/USDT",))
    payload["strategies"][strategy] = {"engine": engine, "decision_timeframes": ["4h"]}
    payload["universe"]["candidates"].append(
        {"strategy": strategy, "pair": "BTC/USDT", "params": params, "decision_timeframes": ["4h"]}
    )
    code, logs = run_main(write_manifest(tmp_path, payload), tmp_path / "out")
    assert (code, events(logs)) == (2, ["decision_timeframes_refused"])
    assert engines == [] and _StubReadOnlyDb.built == []


@pytest.mark.parametrize(
    "override",
    [{"tracked_tree_clean": False}, {"script_tracked": False}],
    ids=["arbre-sale", "script-non-suivi"],
)
def test_an_uncommitted_tree_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: dict[str, Any]
) -> None:
    """Conventions du brief : « refus sur arbre git non committé (``uncommitted_tree``, comme ``warmup_at``) »."""
    monkeypatch.setattr(
        prefix, "git_provenance", lambda relpath: {**_clean_provenance(relpath), **override}
    )
    code, logs = run_main(write_manifest(tmp_path, pc.producer_manifest()), tmp_path / "out")
    assert (code, events(logs)) == (2, ["uncommitted_tree"])
    assert _StubReadOnlyDb.built == [] and not (tmp_path / "out").exists()


def test_a_missing_database_url_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    code, logs = run_main(write_manifest(tmp_path, pc.producer_manifest()), tmp_path / "out")
    assert (code, events(logs)) == (2, ["database_url_missing"])
    assert _StubReadOnlyDb.built == []


def test_an_unreadable_database_is_refused(tmp_path: Path) -> None:
    """Convention ``warmup_at`` : base injoignable ou lecture seule non assertée = refus 2. Ici la sonde lève
    (bouchon par défaut) : le gestionnaire est construit, jamais lu."""
    code, logs = run_main(write_manifest(tmp_path, pc.producer_manifest()), tmp_path / "out")
    assert (code, events(logs)) == (2, ["database_read_failed"])
    assert _StubReadOnlyDb.built == [STUB_URL] and not (tmp_path / "out").exists()


def test_an_output_dir_with_final_artefacts_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "observations.json").write_text("{}\n", encoding="utf-8")
    code, logs = run_main(write_manifest(tmp_path, pc.producer_manifest()), tmp_path / "out")
    assert (code, events(logs)) == (2, ["output_dir_not_empty"])


def test_the_anchor_is_never_a_parameter() -> None:
    """§ A.3 : « ``T`` est recalculé par l'outil depuis la règle, jamais accepté comme paramètre libre »."""
    with pytest.raises(SystemExit) as caught:
        prefix.build_parser().parse_args(
            ["--manifest", "m", "--output-dir", "d", "--anchor", "2020-09-11"]
        )
    assert caught.value.code == 2


def test_the_conformity_anchor_is_off_every_grid() -> None:
    """Fenêtre de conformité (brief § Lot 3) : ``0,70 × 357 j = 249,9 j`` ⇒ ``T = 2020-09-11T21:36Z``, qu'aucune
    bougie ne clôture (1 296 min, ni multiple de 5 ni de 240, § A.4) ; deux manifestes de même fenêtre, même ``T``."""
    start, end = datetime(2020, 1, 6, tzinfo=UTC), datetime(2020, 12, 28, tzinfo=UTC)
    first = pc.loaded(pc.producer_manifest(classes=("C1",), start=start, end=end))
    second = pc.loaded(pc.producer_manifest(classes=("C2", "C5", "C6"), start=start, end=end))
    assert first.anchor() == second.anchor() == datetime(2020, 9, 11, 21, 36, tzinfo=UTC)
    assert all(
        cc.last_stamp_at_or_before(first.anchor(), iv) != first.anchor() for iv in cc.D1_INTERVALS
    )


# ---------------------------------------------------------------------------
# Chemin nominal : vrai moteur, lectures bouchonnées, chaîne appelée sur la sortie
# ---------------------------------------------------------------------------


def _chain(tmp_path: Path, manifest: Path, out: Path) -> dict[str, Any]:
    chain = tmp_path / "chain"
    chain.mkdir()
    registry, anchor, entry = chain / "variants.json", chain / "anchor.json", chain / "entry.json"
    codes = {
        "anchor": ca.main(
            [
                "--manifest",
                str(manifest),
                "--registry",
                str(registry),
                "--output",
                str(anchor),
                "--now",
                NOW,
            ]
        ),
        "entry": ce.main(
            [
                "--manifest",
                str(manifest),
                "--anchor",
                str(anchor),
                "--observations",
                str(out / "observations.json"),
                "--coverage",
                str(out / "coverage.json"),
                "--output",
                str(entry),
                "--now",
                NOW,
            ]
        ),
    }
    codes["benchmark"] = cb.main(
        [
            "--manifest",
            str(manifest),
            "--anchor",
            str(anchor),
            "--entry",
            str(entry),
            "--observations",
            str(out / "observations.json"),
            "--candles",
            str(out / "candles.json"),
            "--output",
            str(chain / "benchmark.json"),
            "--now",
            NOW,
        ]
    )
    codes["select"] = cs.main(
        [
            "--manifest",
            str(manifest),
            "--anchor",
            str(anchor),
            "--entry",
            str(entry),
            "--observations",
            str(out / "observations.json"),
            "--coverage",
            str(out / "coverage.json"),
            "--benchmark",
            str(chain / "benchmark.json"),
            "--output",
            str(chain / "selection.json"),
            "--now",
            NOW,
        ]
    )
    return {
        "codes": codes,
        "entry": cc.read_json(entry),
        "benchmark": cc.read_json(chain / "benchmark.json"),
    }


def test_the_nominal_run_feeds_the_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brief § Lot 3, conformité par construction : ``observations.json`` indexé par identité, ``prefix_run.json`` à
    part ; ``c3_entry`` code 0 **sans clause non assertable** ; D2 retire les candidats sans amorçage (SOL, § I.1
    l.4) ; ``c3_benchmark`` et ``c3_select`` s'exécutent (code 0) ; toutes les lectures bornées à ``≤ T``."""
    manifest_path, reads, runs = _nominal(tmp_path, monkeypatch)
    out = tmp_path / "out"
    code, logs = run_main(manifest_path, out)
    assert (code, events(logs)) == (0, [])
    manifest = pc.loaded(cc.read_json(manifest_path))
    observations = cc.read_json(out / "observations.json")
    assert list(observations) == sorted(c.identity for c in manifest.candidates)
    run = cc.read_json(out / "prefix_run.json")
    assert run["outputs"] == {
        name: sha(out / name) for name in ("observations.json", "coverage.json", "candles.json")
    }
    assert run["anchor"] == pc.ANCHOR.isoformat() and run["provenance"]["git_sha"] == CLEAN_SHA
    assert run["manifest"]["sha256"] == sha(manifest_path)
    assert set(cc.read_json(out / "coverage.json")) == {"window", "pairs"}
    assert set(cc.read_json(out / "candles.json")) == {"pairs"}
    assert all(end == pc.ANCHOR and start == pc.WINDOW_START for _, start, end in reads)
    result = _chain(tmp_path, manifest_path, out)
    assert result["codes"] == {"anchor": 0, "entry": 0, "benchmark": 0, "select": 0}
    assert result["entry"]["not_assertable"] == [] and result["entry"]["refusal"] is None
    diagnostics = result["entry"]["candidate_diagnostics"]
    sol = {c.identity for c in manifest.candidates if c.pair == "SOL/USDT"}
    assert {d["identity"] for d in diagnostics} == sol
    assert all(d["reason"] == "D_WARMUP_PREFIX" for d in diagnostics)


def test_run_is_called_once_per_candidate_on_the_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 3 : « appel unique : moteur bouchon avec compteur → ``run`` appelé **une fois**, bornes
    ``(start, T)`` exactes »."""
    manifest_path, _, runs = _nominal(tmp_path, monkeypatch)
    assert run_main(manifest_path, tmp_path / "out")[0] == 0
    manifest = pc.loaded(cc.read_json(manifest_path))
    assert sorted(runs) == sorted((c.pair, pc.WINDOW_START, pc.ANCHOR) for c in manifest.candidates)


def test_two_runs_are_bit_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Amendement 6 : « deux exécutions → ``observations.json`` et ``candles.json`` identiques au bit » — le
    ``--now`` n'entre que dans ``prefix_run.json``."""
    manifest_path, _, _ = _nominal(tmp_path, monkeypatch)
    assert run_main(manifest_path, tmp_path / "a", now="2026-09-27T00:00:00+00:00")[0] == 0
    assert run_main(manifest_path, tmp_path / "b", now="2026-10-01T12:00:00+00:00")[0] == 0
    for name in ("observations.json", "coverage.json", "candles.json"):
        assert sha(tmp_path / "a" / name) == sha(tmp_path / "b" / name)
    assert (
        cc.read_json(tmp_path / "a" / "prefix_run.json")["generated_at"]
        != cc.read_json(tmp_path / "b" / "prefix_run.json")["generated_at"]
    )


class _Handle:
    def __init__(self, pool: _ReversePool) -> None:
        self.pool = pool
        self.value: Any = None

    def get(self, timeout: float) -> Any:
        assert timeout == prefix.JOB_TIMEOUT_S
        self.pool.run_all()
        return self.value


class _ReversePool:
    """Un pool en processus qui **exécute les jobs en ordre inverse** de leur soumission."""

    def __init__(self) -> None:
        self.jobs: list[tuple[_Handle, Callable[..., Any], tuple[Any, ...]]] = []
        self.done = False

    def __enter__(self) -> _ReversePool:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def apply_async(self, fn: Callable[..., Any], args: tuple[Any, ...]) -> _Handle:
        handle = _Handle(self)
        self.jobs.append((handle, fn, args))
        return handle

    def run_all(self) -> None:
        if not self.done:
            for handle, fn, args in reversed(self.jobs):
                handle.value = fn(*args)
            self.done = True


def test_the_execution_order_does_not_change_the_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 3 : « l'ordre d'exécution ne change pas la sortie » — moteurs exécutés en ordre inverse par le
    chemin ``--workers N`` : sortie identique au bit à celle de ``--workers 1``."""
    manifest_path, _, _ = _nominal(tmp_path, monkeypatch)
    assert run_main(manifest_path, tmp_path / "serial")[0] == 0
    monkeypatch.setattr(prefix, "_spawn_pool", lambda workers: _ReversePool())
    assert run_main(manifest_path, tmp_path / "pool", workers=3)[0] == 0
    for name in ("observations.json", "coverage.json", "candles.json"):
        assert sha(tmp_path / "serial" / name) == sha(tmp_path / "pool" / name)


class _TimeoutPool(_ReversePool):
    def apply_async(self, fn: Callable[..., Any], args: tuple[Any, ...]) -> Any:
        class Late:
            def get(self, timeout: float) -> Any:
                raise multiprocessing.TimeoutError

        return Late()


def test_a_job_timeout_is_a_failed_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path, _, _ = _nominal(tmp_path, monkeypatch)
    monkeypatch.setattr(prefix, "_spawn_pool", lambda workers: _TimeoutPool())
    code, logs = run_main(manifest_path, tmp_path / "out", workers=2)
    assert code == 3 and "jobs_failed" in events(logs)
    assert not (tmp_path / "out" / "observations.json").exists()


# ---------------------------------------------------------------------------
# Reprise, échecs et contrôles internes
# ---------------------------------------------------------------------------


def test_a_matching_partial_is_resumed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brief § Lot 3 : « reprise autorisée **seulement** si le sha256 du manifeste est identique à celui du fichier
    partiel » (et, plan E du 27/09, du même commit) — le candidat repris n'est pas relancé, la sortie est la même."""
    manifest_path, _, runs = _nominal(tmp_path, monkeypatch)
    assert run_main(manifest_path, tmp_path / "a")[0] == 0
    first = sorted((tmp_path / "a" / "partial").iterdir())[0]
    (tmp_path / "b" / "partial").mkdir(parents=True)
    shutil.copy(first, tmp_path / "b" / "partial" / first.name)
    runs.clear()
    assert run_main(manifest_path, tmp_path / "b")[0] == 0
    assert len(runs) == len(pc.loaded(cc.read_json(manifest_path)).candidates) - 1
    assert sha(tmp_path / "a" / "observations.json") == sha(tmp_path / "b" / "observations.json")
    resumed = [
        c for c in cc.read_json(tmp_path / "b" / "prefix_run.json")["candidates"] if c["resumed"]
    ]
    assert [c["identity"] for c in resumed] == [first.stem]


@pytest.mark.parametrize("field", ["manifest_sha256", "git_sha"])
def test_a_foreign_partial_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    manifest_path, _, runs = _nominal(tmp_path, monkeypatch)
    partial = {
        "manifest_sha256": sha(manifest_path),
        "git_sha": CLEAN_SHA,
        "identity": "x",
        "entry": {},
        "duration_s": 1.0,
    }
    partial[field] = "0" * len(partial[field])
    (tmp_path / "out" / "partial").mkdir(parents=True)
    cc.write_json(tmp_path / "out" / "partial" / "x.json", partial)
    code, logs = run_main(manifest_path, tmp_path / "out")
    assert (code, events(logs)) == (2, ["partial_mismatch"])
    assert runs == []


def test_a_failed_job_is_3_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = pc.market()
    pc.install_market(monkeypatch, data)
    install_database(monkeypatch, data)
    count_runs(monkeypatch, fail_pair="SOL/USDT")
    code, logs = run_main(write_manifest(tmp_path, pc.producer_manifest()), tmp_path / "out")
    assert code == 3 and events(logs).count("job_failed") == 2
    assert not any((tmp_path / "out" / name).exists() for name in prefix.FINAL_ARTEFACTS)
    assert (
        len(list((tmp_path / "out" / "partial").iterdir())) == 2
    )  # BTC, repris au prochain lancement


def test_a_passed_params_divergence_is_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Écart E10 : une entrée ``strategies.yaml`` au nom de classe changerait les paramètres du run sous
    ``decision_timeframes`` — contrôle interne en échec, rien de publié."""
    manifest_path, _, _ = _nominal(tmp_path, monkeypatch)
    monkeypatch.setattr(
        prefix,
        "get_settings",
        lambda: pc.engine_settings(router_entry={"params": {"atr_period": 21}}),
    )
    code, logs = run_main(manifest_path, tmp_path / "out")
    assert (code, events(logs)) == (3, ["entry_controls"])
    assert not (tmp_path / "out" / "observations.json").exists()


# ---------------------------------------------------------------------------
# Discipline de source et pureté à l'import
# ---------------------------------------------------------------------------


def test_the_producer_never_coerces_nor_opens_a_database_by_itself() -> None:
    """Même discipline que la couche commune (``test_c3b_common.assert_source_discipline``) : aucun ``bool(``,
    aucun ``.get(`` de dictionnaire, aucune connexion hors du gestionnaire en lecture seule importé."""
    pc.assert_source_discipline("scripts/audit/c3b_prefix.py")


def test_importing_the_producer_changes_nothing() -> None:
    """Règle B4.2 : ``.env`` chargé dans ``main``, jamais à l'import ; l'import ne change pas l'environnement."""
    probe = (
        "import importlib, json, os, sys\n"
        "root = sys.argv[1]\n"
        "sys.path[:0] = [root + '/scripts/audit', root + '/scripts', root + '/src', root]\n"
        "before = dict(os.environ)\n"
        "importlib.import_module('c3b_prefix')\n"
        "print(json.dumps(sorted(k for k in set(before) | set(os.environ) if before.get(k) != os.environ.get(k))))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    proc = subprocess.run(
        [sys.executable, "-c", probe, str(_PROJECT_ROOT)],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []
