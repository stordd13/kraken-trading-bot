"""``scripts/audit/c3b_evaluate.py`` — le producteur, temps 3 (partie 1) : run unique et preuves § B (C3b lot 4a).

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 4a » ; plan du lot validé le 2026-09-28 (GO de Bruno, trois
amendements). Les attendus viennent du brief, du protocole (§ B.2, § B.4, § C.3, § L.1) et de la chaîne elle-même,
appelée en processus sur la sortie du producteur (``c3_anchor``, ``cc.evaluation_admission``, ``c3_continuity``) —
jamais de l'implémentation.

**Herméticité construite, comme au lot 3** : une fixture autouse remplace ``_db.ReadOnlyDatabaseManager`` (dans
``c3b_evaluate`` et ``c3b_prefix``) par un bouchon qui n'ouvre jamais de session, coupe ``.env``, fait lever les
lectures en base de ``c3b_common`` et les trois chargeurs du moteur tant qu'un test ne les remplace pas, et pointe
``CAMPAIGN_UNLOCK`` vers un chemin absent. **Aucun test base.**

Deux moteurs : un **bouchon** (``StubEngine``) qui compte ses ``run`` et mute tout son état dans ``run`` — une lecture
après ``run`` voit un autre état —, et dont la sortie saine est conforme au contrat (elle passe l'admission et
``c3_continuity``) ; et le **vrai** ``GridBacktester``, chargeurs bouchonnés, pour le chemin nominal.
"""

# ruff: noqa: E402
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))
sys.path.insert(0, str(_PROJECT_ROOT / "tests"))

import c3_anchor as ca
import c3_common as cc
import c3_continuity as ccont
import c3_select as cs
import c3b_common as c3bc
import c3b_evaluate as evaluate
import c3b_prefix as prefix

from krakenbot.models.base import TradeSide
from test_scripts import test_c3_common as fx
from test_scripts import test_c3b_common as pc
from test_scripts import test_c3b_prefix as tp

NOW = tp.NOW
T = pc.ANCHOR
FIN = pc.WINDOW_END
#: Brief § Lot 4b : les clés que la partie 2 ajoute à l'artefact d'évaluation (§ F.2) — absentes de la partie 1.
F2_KEYS = frozenset({"returns_config", "returns_bench", "environment", "B", "replications"})
F2_METRICS = frozenset({"cagr_pct", "delta_dd"})


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    tp._StubReadOnlyDb.built = []
    for module in (evaluate, prefix):
        monkeypatch.setattr(module, "ReadOnlyDatabaseManager", tp._StubReadOnlyDb)
        monkeypatch.setattr(module, "load_dotenv", lambda *args, **kwargs: False)
        monkeypatch.setattr(module, "get_settings", pc.engine_settings)
        monkeypatch.setattr(module, "git_provenance", tp._clean_provenance)
    monkeypatch.setenv("DATABASE_URL", tp.STUB_URL)
    monkeypatch.setattr(prefix, "_spawn_pool", tp._unexpected_pool)
    for name in ("probe_database", "fetch_stamps", "fetch_closes", "fetch_derived_stamps"):
        monkeypatch.setattr(c3bc, name, tp._unexpected(name))
    for name in ("_load_candles", "_load_candles_for_interval", "_load_candles_before"):
        monkeypatch.setattr(pc.bt.GridBacktester, name, tp._unexpected(name))
    monkeypatch.setattr(
        c3bc, "CAMPAIGN_UNLOCK", tmp_path_factory.mktemp("verrou") / "CAMPAIGN_UNLOCK"
    )


# ---------------------------------------------------------------------------
# Monde : manifeste de producteur, ancrage réel, sélection simulée conforme
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class World:
    manifest_path: Path
    anchor_path: Path
    manifest: cc.Manifest

    @property
    def btc(self) -> cc.Candidate:
        """Le candidat désigné du monde de test : la première identité BTC dans l'ordre lexicographique."""
        return sorted(
            (c for c in self.manifest.candidates if c.pair == "BTC/USDT"), key=lambda c: c.identity
        )[0]


def make_world(tmp_path: Path, payload: Mapping[str, Any] | None = None) -> World:
    """Le manifeste de producteur du lot 3 et **son** ancrage, produit par ``c3_anchor`` en processus."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest_path = tp.write_manifest(tmp_path, payload or pc.producer_manifest())
    chain = tmp_path / "chain"
    chain.mkdir(exist_ok=True)
    anchor_path = chain / "anchor.json"
    code = ca.main(
        [
            "--manifest",
            str(manifest_path),
            "--registry",
            str(chain / "variants.json"),
            "--output",
            str(anchor_path),
            "--now",
            NOW,
        ]
    )
    assert code == 0
    return World(manifest_path, anchor_path, pc.loaded(cc.read_json(manifest_path)))


def retained_block(candidate: cc.Candidate) -> dict[str, Any]:
    """Le bloc ``retained`` de ``c3_select.py:593-601``."""
    return {
        "identity": candidate.identity,
        "key": candidate.identity,
        "strategy": candidate.strategy,
        "pair": candidate.pair,
        "params": dict(candidate.params),
    }


def write_selection(
    tmp_path: Path,
    world: World,
    retained: cc.Candidate | None,
    *,
    ranking: Sequence[str] | None = None,
    retained_override: Mapping[str, Any] | None = None,
    exit_code: int = 0,
    inputs: Mapping[str, Path] | None = None,
) -> Path:
    """Un ``selection.json`` **simulé conforme** à ce que le producteur lit : l'enveloppe de la chaîne
    (``cc.envelope``, empreintes réelles du manifeste et de l'ancrage), ``retained`` et ``ranking`` de
    ``c3_select.run_selection`` (``:588-602``), le statut par ``cs.selection_status``. Chaque test adverse ne
    déforme qu'un champ."""
    chain = tmp_path / "chain"
    chain.mkdir(exist_ok=True)
    others: dict[str, Path] = {}
    for name in ("entry", "observations", "coverage", "benchmark"):
        others[name] = chain / f"{name}.json"
        cc.write_json(others[name], {"bouchon": name})
    recorded = {"manifest": world.manifest_path, "anchor": world.anchor_path, **others}
    recorded.update(inputs or {})
    head = [] if retained is None else [retained.identity]
    payload = cc.envelope(cs.STEP, datetime.fromisoformat(NOW), recorded, exit_code=exit_code)
    payload.update(
        {
            "provenance": world.manifest.provenance,
            "status": cs.selection_status(world.manifest.provenance, retained is not None),
            "reason": None if retained is not None else "A_BELOW_FLOOR",
            "admissible": list(head),
            "survivors": list(head),
            "ranking": list(head if ranking is None else ranking),
            "retained": dict(retained_override)
            if retained_override is not None
            else (None if retained is None else retained_block(retained)),
            "abstention_clause": cc.ABSTENTION_CLAUSE if retained is None else None,
        }
    )
    path = chain / "selection.json"
    cc.write_json(path, payload)
    return path


def run_eval(
    world: World | tuple[Path, Path],
    out: Path,
    *,
    selection: Path | None = None,
    candidate: str | None = None,
    now: str = NOW,
) -> tuple[int, list[dict[str, Any]]]:
    manifest_path, anchor_path = (
        (world.manifest_path, world.anchor_path) if isinstance(world, World) else world
    )
    argv = [
        "--manifest",
        str(manifest_path),
        "--anchor",
        str(anchor_path),
        "--output-dir",
        str(out),
        "--now",
        now,
    ]
    if selection is not None:
        argv += ["--selection", str(selection)]
    if candidate is not None:
        argv += ["--candidate", candidate]
    with structlog.testing.capture_logs() as logs:
        code = evaluate.main(argv)
    return code, logs


def install_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    async def probe(db: Any) -> dict[str, Any]:
        return {"transaction_read_only": "on", "alembic_version": ["c3bd1e7a0001"]}

    monkeypatch.setattr(c3bc, "probe_database", probe)


def spy_build(monkeypatch: pytest.MonkeyPatch, engine: Any = None) -> list[Any]:
    """Remplace ``c3bc.build_engine`` : rend ``engine`` (bouchon) ou délègue au vrai ; enregistre les appels."""
    calls: list[Any] = []
    original = c3bc.build_engine

    def build(settings: Any, db: Any, manifest: Any, candidate: Any, costs: Any) -> Any:
        calls.append(candidate.identity)
        return engine if engine is not None else original(settings, db, manifest, candidate, costs)

    monkeypatch.setattr(c3bc, "build_engine", build)
    return calls


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trade(stamp: datetime, side: TradeSide = TradeSide.BUY) -> Any:
    return pc.bt.BacktestTrade(
        timestamp=stamp,
        side=side,
        price=Decimal("90000"),
        amount_usdc=Decimal("25"),
        amount_crypto=Decimal("0.00025"),
        fee=Decimal("0.025"),
    )


# ---------------------------------------------------------------------------
# Moteur bouchon : état avant run aux noms de GridBacktester, sortie conforme
# ---------------------------------------------------------------------------


class StubEngine:
    """L'état de ``GridBacktester`` avant ``run`` sous ses noms réels (``backtest.py:2250-2291``), le solde tel que le
    moteur le stocke depuis la fabrique (``Decimal(str(float(C)))``, ``:2250`` et ``c3b_common.py:302``). ``run``
    compte ses appels et **mute** solde, inventaire, carnets, stratégie et trades. La sortie saine — trades et
    liquidation aux formules du moteur (``pc.engine_like_liquidation``, estampille ``fin − 5 min``), grille
    quotidienne ``[T, fin]``, amorçage suffisant — passe l'admission et ``c3_continuity`` (témoin conforme)."""

    def __init__(
        self,
        world: World,
        *,
        lots: Sequence[tuple[Decimal, Decimal | None]] = ((Decimal("0.001"), Decimal("95000")),),
        stamp: datetime = FIN - timedelta(minutes=5),
        trades: Sequence[Any] | None = None,
        net_gap: float = 0.0,
        equity: Any = "sain",
        fail: bool = False,
    ) -> None:
        manifest, candidate = world.manifest, world.btc
        self.pair = candidate.pair
        self.usdc_balance: Any = Decimal(str(float(manifest.capital)))
        self.btc_held: Any = Decimal("0")
        self.active_buy_orders: list[Any] = []
        self.active_sell_orders: list[Any] = []
        self._strategy_obj: Any = None
        self.effective_params = {"passed_params": {**candidate.params, "pair": candidate.pair}}
        self.calls: list[tuple[str, datetime, datetime]] = []
        self.fail = fail
        spread, slippage = manifest.pair_costs[candidate.pair]
        summary, engine_trades = pc.engine_like_liquidation(
            list(lots), stamp=stamp, spread=spread, slippage=slippage, taker=manifest.taker
        )
        self._summary = summary
        self._trades = list(engine_trades if trades is None else trades)
        grid = cc.daily_grid(T, FIN)
        values = [1000.0 + 0.5 * k for k in range(len(grid))]
        self._equity: Mapping[str, Any] | None = (
            {"start": T.isoformat(), "end": FIN.isoformat(), "values": values}
            if equity == "sain"
            else equity
        )
        ending = values[-1]
        self._metrics = {
            "net_pnl": ending - 1000.0 + net_gap,
            "ending_balance": ending,
            "starting_balance": 1000.0,
        }
        self.metrics = SimpleNamespace(
            trades=[],
            to_dict=lambda: dict(self._metrics),
            equity_daily_dict=lambda: None if self._equity is None else dict(self._equity),
        )

    async def run(self, pair: str, start: datetime, end: datetime) -> Any:
        self.calls.append((pair, start, end))
        if self.fail:
            raise RuntimeError("panne simulée du moteur")
        self.usdc_balance = Decimal("0")
        self.btc_held = Decimal("1")
        self.active_buy_orders.append({"price": Decimal("1")})
        self.active_sell_orders.append({"price": Decimal("2")})
        self._strategy_obj = object()
        self.metrics.trades.extend(self._trades)
        return self.metrics

    def liquidation_summary(self) -> dict[str, Any]:
        return dict(self._summary)

    def warmup_summary(self) -> dict[str, Any]:
        return fx.warmup_segment()


def stubbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kw: Any
) -> tuple[World, StubEngine, list[Any]]:
    world = make_world(tmp_path)
    install_probe(monkeypatch)
    engine = StubEngine(world, **kw)
    return world, engine, spy_build(monkeypatch, engine)


def errors(logs: list[dict[str, Any]]) -> list[str]:
    return [entry["event"] for entry in logs if entry["log_level"] == "error"]


def continuity(tmp_path: Path, world: World, evaluation: Path) -> tuple[int, dict[str, Any] | None]:
    """``c3_continuity`` en processus sur l'artefact produit, avec un comparateur d'évaluation **synthétique**
    (``fx.benchmark_eval``, fenêtre ``[T, fin]``) — le critère de fin du lot 4a."""
    run = cc.read_json(evaluation)
    bench = tmp_path / "benchmark_eval_synth.json"
    cc.write_json(
        bench,
        fx.benchmark_eval(run["pair"], window={"start": T.isoformat(), "end": FIN.isoformat()}),
    )
    output = tmp_path / "continuity.json"
    code = ccont.main(
        [
            "--manifest",
            str(world.manifest_path),
            "--anchor",
            str(world.anchor_path),
            "--evaluation",
            str(evaluation),
            "--benchmark-eval",
            str(bench),
            "--output",
            str(output),
            "--now",
            NOW,
        ]
    )
    return code, cc.read_json(output) if output.exists() else None


# ---------------------------------------------------------------------------
# A. Garde-fous et refus d'entrée — tous avant le moteur
# ---------------------------------------------------------------------------


def _campaign_payload(end: datetime = datetime(2026, 6, 29, tzinfo=UTC)) -> dict[str, Any]:
    return pc.producer_manifest(start=datetime(2021, 3, 1, tzinfo=UTC), end=end)


def test_a_campaign_window_is_refused_before_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Décision 6 : aucun run du producteur ne touche la fenêtre de campagne ; refus code 2 tant que
    ``CAMPAIGN_UNLOCK`` n'existe pas — avant les paramètres, le moteur et la base, rien n'est écrit."""
    params = tp.spy(monkeypatch, c3bc, "validate_params")
    engines = spy_build(monkeypatch)
    manifest = tp.write_manifest(tmp_path, _campaign_payload())
    code, logs = run_eval(
        (manifest, tmp_path / "absent.json"), tmp_path / "out", selection=tmp_path / "s.json"
    )
    assert (code, errors(logs)) == (2, ["campaign_window_locked"])
    assert (params, engines, tp._StubReadOnlyDb.built) == ([], [], [])
    assert not (tmp_path / "out").exists()


def test_a_designation_on_the_campaign_window_is_refused_even_unlocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan du lot, point 1 : ``--candidate`` « refusée en code 2 dès que la fenêtre touche la campagne » ; « une
    porte de désignation qui existerait sur la fenêtre de campagne n'est pas une option ». Le déverrouillage
    **existe** : il ouvre le chemin sélection (refus suivant : l'ancrage), jamais la désignation."""
    unlock = tmp_path / "CAMPAIGN_UNLOCK"
    unlock.touch()
    monkeypatch.setattr(c3bc, "CAMPAIGN_UNLOCK", unlock)
    params = tp.spy(monkeypatch, c3bc, "validate_params")
    engines = spy_build(monkeypatch)
    payload = _campaign_payload()
    manifest = tp.write_manifest(tmp_path, payload)
    identity = sorted(c.identity for c in pc.loaded(payload).candidates)[0]
    absent = tmp_path / "absent.json"
    code, logs = run_eval((manifest, absent), tmp_path / "out", candidate=identity)
    assert (code, errors(logs)) == (2, ["designation_on_campaign_window"])
    assert (params, engines, tp._StubReadOnlyDb.built) == ([], [], [])
    code, logs = run_eval((manifest, absent), tmp_path / "out", selection=tmp_path / "s.json")
    assert (code, errors(logs)) == (2, ["anchor_unreadable"])
    assert not (tmp_path / "out").exists()


def test_a_designation_window_ending_on_the_campaign_start_passes_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Borne, même prédicat que le garde-fou 6 (écart E6 du lot 3) : ``end == 2021-03-01`` passe (``end >`` est
    refusé) — le refus suivant vient d'un autre contrôle (ici l'ancrage)."""
    payload = pc.producer_manifest(
        start=datetime(2020, 6, 1, tzinfo=UTC), end=datetime(2021, 3, 1, tzinfo=UTC)
    )
    manifest = tp.write_manifest(tmp_path, payload)
    identity = sorted(c.identity for c in pc.loaded(payload).candidates)[0]
    code, logs = run_eval(
        (manifest, tmp_path / "absent.json"), tmp_path / "out", candidate=identity
    )
    assert (code, errors(logs)) == (2, ["anchor_unreadable"])


@pytest.mark.parametrize(
    "target",
    [["--selection", "s.json", "--candidate", "x"], []],
    ids=["les deux", "aucun"],
)
def test_selection_and_candidate_are_exclusive_and_one_is_required(target: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        evaluate.build_parser().parse_args(
            ["--manifest", "m", "--anchor", "a", "--output-dir", "d", *target]
        )
    assert caught.value.code == 2


def test_a_designation_outside_the_universe_is_refused(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    code, logs = run_eval(world, tmp_path / "out", candidate="0" * 64)
    assert (code, errors(logs)) == (2, ["candidate_not_in_universe"])


def test_an_empty_selection_is_nothing_to_evaluate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4a : « absence de retenu → code 2 “rien à évaluer” », aucun fichier ; ni moteur, ni base."""
    engines = spy_build(monkeypatch)
    world = make_world(tmp_path)
    selection = write_selection(tmp_path, world, None)
    code, logs = run_eval(world, tmp_path / "out", selection=selection)
    assert (code, errors(logs)) == (2, ["nothing_to_evaluate"])
    assert (engines, tp._StubReadOnlyDb.built) == ([], [])
    assert not (tmp_path / "out").exists()


def test_a_failed_upstream_selection_is_refused(tmp_path: Path) -> None:
    """``cc.require_upstream_ok`` : un artefact amont n'est consommable que s'il enregistre son succès."""
    world = make_world(tmp_path)
    selection = write_selection(tmp_path, world, world.btc, exit_code=1)
    code, logs = run_eval(world, tmp_path / "out", selection=selection)
    assert (code, errors(logs)) == (2, ["selection_refused"])


@pytest.mark.parametrize("name", ["manifest", "anchor"])
def test_a_selection_of_another_manifest_or_anchor_is_refused(tmp_path: Path, name: str) -> None:
    """Les empreintes enregistrées par ``c3_select`` doivent être celles des fichiers fournis
    (``cc.check_inputs_match``) : sinon ce ne sont pas les sorties d'une même chaîne."""
    world = make_world(tmp_path)
    other = tmp_path / f"autre_{name}.json"
    cc.write_json(other, {"autre": name})
    selection = write_selection(tmp_path, world, world.btc, inputs={name: other})
    code, logs = run_eval(world, tmp_path / "out", selection=selection)
    assert (code, errors(logs)) == (2, ["selection_inputs_mismatch"])


def test_a_retained_block_disagreeing_with_the_ranking_head_is_3(tmp_path: Path) -> None:
    """Le classement fait foi (``c3_verdict.py:830``) : un retenu qui n'est pas la tête du classement, ou un
    retenu nul devant un classement non vide, est une incohérence amont — contrôle en échec, rien d'évalué."""
    world = make_world(tmp_path)
    other = next(c for c in world.manifest.candidates if c.identity != world.btc.identity)
    for retained, ranking in ((world.btc, [other.identity]), (None, [other.identity])):
        selection = write_selection(tmp_path, world, retained, ranking=ranking)
        code, logs = run_eval(world, tmp_path / "out", selection=selection)
        assert (code, errors(logs)) == (3, ["selection_inconsistent"])


def test_a_retained_identity_not_derived_from_its_fields_is_3(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    other = next(c for c in world.manifest.candidates if c.identity != world.btc.identity)
    forged = {**retained_block(world.btc), "identity": other.identity, "key": other.identity}
    selection = write_selection(
        tmp_path, world, world.btc, ranking=[other.identity], retained_override=forged
    )
    code, logs = run_eval(world, tmp_path / "out", selection=selection)
    assert (code, errors(logs)) == (3, ["selection_inconsistent"])


def test_a_retained_candidate_outside_the_universe_is_3(tmp_path: Path) -> None:
    """Un retenu bien formé (identité dérivée, tête du classement) mais absent de l'univers du manifeste : la
    sélection ne vient pas de ce manifeste malgré ses empreintes — contrôle en échec, jamais un run."""
    world = make_world(tmp_path)
    params = {"grid_levels": 7}
    identity = cc.candidate_identity(pc.STRATEGY, "BTC/USDT", params)
    foreign = {
        "identity": identity,
        "key": identity,
        "strategy": pc.STRATEGY,
        "pair": "BTC/USDT",
        "params": params,
    }
    selection = write_selection(
        tmp_path, world, world.btc, ranking=[identity], retained_override=foreign
    )
    code, logs = run_eval(world, tmp_path / "out", selection=selection)
    assert (code, errors(logs)) == (3, ["selection_inconsistent"])


def test_an_anchor_of_another_manifest_is_refused(tmp_path: Path) -> None:
    world = make_world(tmp_path / "a")
    other = make_world(tmp_path / "b", pc.producer_manifest(classes=("C2",)))
    code, logs = run_eval(
        (world.manifest_path, other.anchor_path), tmp_path / "out", candidate=world.btc.identity
    )
    assert (code, errors(logs)) == (2, ["anchor_inputs_mismatch"])


@pytest.mark.parametrize("field", ["anchor", "pairs", "window"])
def test_an_anchor_whose_T_pairs_or_window_differ_is_3(tmp_path: Path, field: str) -> None:
    """Brief § Lot 4a : « ``T`` et ``pairs`` triées depuis ``anchor.json`` (recoupés avec ``manifest.anchor()`` —
    écart = code 3) » ; § A.3 : ``T`` est recalculé, jamais un paramètre. L'empreinte du manifeste reste juste."""
    world = make_world(tmp_path)
    raw = dict(cc.read_json(world.anchor_path))
    if field == "anchor":
        raw["anchor"] = (T + timedelta(minutes=1)).isoformat()
    elif field == "pairs":
        raw["pairs"] = list(reversed(raw["pairs"]))
    else:
        raw["window"] = {
            **raw["window"],
            "start": (pc.WINDOW_START + timedelta(days=1)).isoformat(),
        }
    cc.write_json(world.anchor_path, raw)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["anchor_mismatch"])


def test_a_non_boolean_pause_flag_is_refused_before_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 3 (mêmes refus que le préfixe) : ``"false"`` est vrai à ``:384`` — refus de tout l'univers."""
    engines = spy_build(monkeypatch)
    payload = pc.producer_manifest()
    payload["universe"]["candidates"][0]["params"]["pause_1w_strong_bear"] = "false"
    manifest = tp.write_manifest(tmp_path, payload)
    code, logs = run_eval((manifest, tmp_path / "absent.json"), tmp_path / "out", candidate="x")
    assert (code, errors(logs)) == (2, ["decision_timeframes_refused"])
    assert engines == []


def test_an_uncommitted_tree_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = make_world(tmp_path)
    monkeypatch.setattr(
        evaluate,
        "git_provenance",
        lambda relpath: {**tp._clean_provenance(relpath), "tracked_tree_clean": False},
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["uncommitted_tree"])


def test_an_output_dir_with_final_artefacts_is_refused(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / evaluate.EVALUATION_RUN).write_text("{}\n", encoding="utf-8")
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["output_dir_not_empty"])


def test_a_missing_or_unreadable_database_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``DATABASE_URL`` absente : refus ; base injoignable ou lecture seule non assertée (``probe_database`` qui
    lève) : refus — jamais un moteur construit."""
    engines = spy_build(monkeypatch)
    world = make_world(tmp_path)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["database_read_failed"])
    monkeypatch.delenv("DATABASE_URL")
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["database_url_missing"])
    assert engines == []


# ---------------------------------------------------------------------------
# B. Preuve de départ à plat (§ B.2, § J item 10)
# ---------------------------------------------------------------------------


def test_the_flat_start_proof_is_read_before_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ B.2 l.885-886 : la preuve est capturée « avant le traitement de la première bougie du run
    d'évaluation ». Le bouchon mute solde, inventaire, carnets, stratégie et trades **dans** ``run`` : une lecture
    après ``run`` ne verrait plus un départ à plat. Ce qui a été lu est consigné tel que le moteur le stocke."""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (0, [])
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION_RUN)
    assert run["flat_start_proof"] == {
        "at": T.isoformat(),
        "cash": "1000",
        "qty": "0",
        "pending": 0,
    }
    observed = cc.read_json(tmp_path / "out" / evaluate.PROVENANCE)["flat_start_observed"]
    assert observed == {
        "usdc_balance": "1000.0",
        "btc_held": "0",
        "active_buy_orders": 0,
        "active_sell_orders": 0,
        "strategy_built": False,
        "trades": 0,
    }
    assert engine.usdc_balance == Decimal("0")  # le run a bien muté l'état après la capture


def test_the_flat_start_proof_has_the_fixture_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4a : « la forme exacte de la fixture ``flat_start_proof`` » — l'égalité est au dict près, avec
    la fixture de la chaîne à ``T`` (``C = 1000``, § 0.5)."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION_RUN)
    assert run["flat_start_proof"] == fx.flat_start_proof(at=T)


def test_cash_different_from_C_is_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brief : « exiger ``usdc_balance == C`` du manifeste … sinon code 3 » ; rien n'est écrit, ``run`` jamais
    appelé."""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    engine.usdc_balance = Decimal("1000.01")
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["flat_start_proof"])
    assert engine.calls == []
    assert not (tmp_path / "out" / evaluate.EVALUATION_RUN).exists()


@pytest.mark.parametrize(
    "attribute",
    ["btc_held", "active_buy_orders", "active_sell_orders", "_strategy_obj", "trades"],
)
def test_inventory_orders_strategy_or_trades_before_run_are_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attribute: str
) -> None:
    """Brief : ``btc_held == 0`` et ``pending == 0`` avant ``run`` ; plan (amendement 1) : sur le chemin grok,
    ``pending`` est vide par construction — la stratégie (``:2257``, créée dans ``run`` ``:2893-2895``) et les
    trades (``:2291``) sont des préconditions du même contrôle."""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    if attribute == "btc_held":
        engine.btc_held = Decimal("0.001")
    elif attribute == "_strategy_obj":
        engine._strategy_obj = object()
    elif attribute == "trades":
        engine.metrics.trades.append(trade(T + timedelta(hours=1)))
    else:
        getattr(engine, attribute).append({"price": Decimal("1")})
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["flat_start_proof"])
    assert engine.calls == []


def test_a_float_balance_is_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``1000.0 == Decimal("1000")`` est vrai en Python : sans contrôle de type, une dérive du moteur vers ``float``
    passerait sous l'égalité."""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    engine.usdc_balance = 1000.0
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["flat_start_proof"])


def _capital_manifest(value: str) -> cc.Manifest:
    payload = pc.producer_manifest()
    payload["selection_rule"]["thresholds"]["CAPITAL"]["value"] = value
    return pc.loaded(payload)


@pytest.mark.parametrize(
    ("capital", "stored", "cash"),
    [("1000", "1000.0", "1000"), ("1000.50", "1000.5", "1000.50")],
)
def test_what_the_engine_stores_for_C(capital: str, stored: str, cash: str) -> None:
    """Plan, point 2 : la fabrique passe ``starting_capital=float(manifest.capital)`` (``c3b_common.py:302``) et le
    moteur stocke ``Decimal(str(starting_capital))`` (``backtest.py:2250``) — donc ``str(float(C))`` : ``"1000.0"``
    pour ``1000``, ``"1000.5"`` pour ``1000.50``. L'égalité est numérique ; ``cash`` exporté est le ``C`` du
    manifeste. Une égalité de chaînes casserait dès ``1000`` ; une qui passe sur ``1000`` et casse sur ``1000.50``
    est un défaut (plan, point 2). Vrai moteur."""
    manifest = _capital_manifest(capital)
    candidate = manifest.candidates[0]
    engine = c3bc.build_engine(
        pc.engine_settings(), MagicMock(), manifest, candidate, c3bc.engine_pair_costs(manifest)
    )
    assert str(engine.usdc_balance) == stored
    proof, observed = evaluate.capture_flat_start(engine, capital=manifest.capital, anchor=T)
    assert proof == {"at": T.isoformat(), "cash": cash, "qty": "0", "pending": 0}
    assert observed["usdc_balance"] == stored


def test_a_capital_the_float_cannot_carry_is_3() -> None:
    """Un ``C`` à 20 chiffres significatifs : ``float(C)`` le tronque, le moteur ne démarre pas avec ``C`` — la
    preuve est refusée (amendement 3 : contrainte notée au rapport pour le manifeste). Une comparaison en
    ``float`` la laisserait passer. Vrai moteur."""
    manifest = _capital_manifest("1000.1234567890123456789")
    candidate = manifest.candidates[0]
    engine = c3bc.build_engine(
        pc.engine_settings(), MagicMock(), manifest, candidate, c3bc.engine_pair_costs(manifest)
    )
    assert engine.usdc_balance != manifest.capital
    with pytest.raises(c3bc.ProducerControlError) as caught:
        evaluate.capture_flat_start(engine, capital=manifest.capital, anchor=T)
    assert caught.value.control == "flat_start_proof"


# ---------------------------------------------------------------------------
# C. Appel unique, first_fill_at, contrôles internes
# ---------------------------------------------------------------------------


def test_run_is_called_once_on_T_fin_and_single_call_pins_the_counter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ B.4 : « L'évaluation est **un seul appel** ``engine.run(pair, T, fin)`` » ; brief : « ``single_call`` faux
    si le compteur ≠ 1 » — l'artefact déclare ``single_call`` si et seulement si le compteur vaut 1."""
    world, engine, built = stubbed(tmp_path, monkeypatch)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION_RUN)
    assert engine.calls == [(world.btc.pair, T, FIN)]
    assert run["invocation"] == {"single_call": len(engine.calls) == 1}
    assert built == [world.btc.identity]


def test_first_fill_at_is_the_smallest_trade_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ C.3, brief : « ``first_fill_at`` = plus petite estampille de ``metrics.trades`` » — l'ordre de la liste
    n'y est pour rien."""
    early = T + timedelta(minutes=8)
    world, _, _ = stubbed(tmp_path, monkeypatch)
    engine = StubEngine(world)
    engine._trades = [*reversed(engine._trades), trade(early)]
    spy_build(monkeypatch, engine)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    assert cc.read_json(tmp_path / "out" / evaluate.EVALUATION_RUN)["first_fill_at"] == (
        early.isoformat()
    )


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(minutes=-5)], ids=["T", "T-5min"])
def test_a_fill_at_or_before_T_is_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offset: timedelta
) -> None:
    """Brief : « **strictement** ``> T`` exigé (code 3 sinon) » ; § C.3."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    engine = StubEngine(world)
    engine._trades = [trade(T + offset), *engine._trades]
    spy_build(monkeypatch, engine)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["first_fill_at"])
    assert not (tmp_path / "out" / evaluate.EVALUATION_RUN).exists()


def test_no_trade_writes_a_null_first_fill_at_that_the_chain_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief : « ``null`` si aucun trade (la chaîne le traite) ». La chaîne le traite par un refus : § L.1 v2.1, une
    évaluation réelle sans ``first_fill_at`` n'est pas admise (``R0_INVALID_RUN``, le porteur nommé) — écart
    candidat v2.2 (plan § 8). Le bloc de liquidation ne liquide rien : l'exemption ``trades == 0`` s'applique."""
    world, _, _ = stubbed(tmp_path, monkeypatch, lots=(), trades=())
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (0, [])
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION_RUN)
    assert run["first_fill_at"] is None and run["liquidation"]["trades"] == 0
    with pytest.raises(cc.EntryRefusedError, match="first_fill_at"):
        cc.evaluation_admission(run)


@pytest.mark.parametrize(("gap", "code"), [(2e-6, 3), (5e-7, 0)])
def test_a_net_pnl_identity_gap_is_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gap: float, code: int
) -> None:
    """§ B.2 l.870 : ``|net_pnl − (ending − starting)| ≤ 1e-6`` — nécessaire, pas suffisant ; au-delà, code 3."""
    world, _, _ = stubbed(tmp_path, monkeypatch, net_gap=gap)
    result, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (result, errors(logs)) == (code, [] if code == 0 else ["evaluation_controls"])


def test_a_liquidation_outside_the_final_daily_cell_is_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ B.4 : l'estampille de liquidation et la borne finale « dans la même cellule de la grille quotidienne »
    (``c3_continuity.stamp_cell_block``), sinon ``E_STAMP_MISMATCH`` — le producteur ne l'écrit pas."""
    world, _, _ = stubbed(tmp_path, monkeypatch, stamp=FIN - timedelta(days=2))
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["evaluation_controls"])


def _grid_values() -> list[float]:
    return [1000.0] * len(cc.daily_grid(T, FIN))


@pytest.mark.parametrize(
    "equity",
    [
        None,
        {"start": (T + timedelta(minutes=1)).isoformat(), "end": FIN.isoformat()},
        {"start": T.isoformat(), "end": (FIN - timedelta(minutes=5)).isoformat()},
        {"start": T.isoformat(), "end": FIN.isoformat(), "short": True},
    ],
    ids=["absent", "start", "end", "longueur"],
)
def test_equity_daily_bounds_and_length_are_those_of_T_fin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, equity: dict[str, Any] | None
) -> None:
    """Brief : ``equity_daily`` avec ``start == T``, ``end == fin`` ; la clause 2 recompte la grille quotidienne
    ``[T, fin]`` (``c3_continuity.py:156-165``) — le producteur n'écrit pas une grille qu'elle refuserait."""
    series: dict[str, Any] | None = None
    if equity is not None:
        values = _grid_values()
        series = {
            "start": equity["start"],
            "end": equity["end"],
            "values": values[:-1] if "short" in equity else values,
        }
    world, _, _ = stubbed(tmp_path, monkeypatch, equity=series)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["evaluation_controls"])


def test_an_engine_failure_is_3_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, engine, _ = stubbed(tmp_path, monkeypatch, fail=True)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["engine_failed"])
    assert engine.calls == [(world.btc.pair, T, FIN)]
    assert not any((tmp_path / "out" / name).exists() for name in evaluate.FINAL_ARTEFACTS)


def test_the_tolerance_is_that_of_the_text() -> None:
    """§ B.2 l.870 : « ``|net_pnl − (ending_balance − starting_balance)| ≤ 1e-6`` »."""
    text = (_PROJECT_ROOT / "docs" / "protocole_c3.md").read_text(encoding="utf-8")
    assert "|net_pnl − (ending_balance − starting_balance)| ≤ 1e-6" in text
    assert evaluate.NET_PNL_IDENTITY_TOL == 1e-6


# ---------------------------------------------------------------------------
# D. Chemin nominal : vrai GridBacktester, chargeurs bouchonnés, chaîne appelée sur la sortie
# ---------------------------------------------------------------------------


def real_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> World:
    """Le marché du lot 3 prolongé jusqu'à ``fin`` : le niveau d'achat amorcé de BTC se remplit à la première
    bougie 5 min strictement après ``T`` (prix 90 000 sous le niveau 100 000), la vente appariée n'est jamais
    touchée, la position finit ouverte et la liquidation terminale tombe à ``fin`` (dernière bougie ``≤ fin``)."""
    pc.install_market(monkeypatch, pc.market(anchor=FIN))
    install_probe(monkeypatch)
    return make_world(tmp_path, pc.producer_manifest(**kw))


def test_the_nominal_evaluation_is_admitted_and_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critère de fin du lot 4a : ``cc.evaluation_admission`` vrai (évaluation réelle admise) sur un artefact
    produit, et ``c3_continuity`` sur un comparateur d'évaluation synthétique rend ``c1``, ``c2``, ``c5`` =
    ``DECLARED``. Forme : les clés de la fixture ``evaluation`` moins celles du lot 4b."""
    world = real_world(tmp_path, monkeypatch)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (0, [])
    evaluation = tmp_path / "out" / evaluate.EVALUATION_RUN
    run = cc.read_json(evaluation)
    reference = fx.evaluation(fx.manifest())
    assert set(run) == set(reference) - F2_KEYS
    assert set(run["metrics"]) == set(reference["metrics"]) - F2_METRICS
    assert run["synthetic"] is False
    assert run["period"] == {"start": T.isoformat(), "end": FIN.isoformat()}
    assert (
        run["first_fill_at"] == (T + timedelta(minutes=3)).isoformat()
    )  # 19:15, première bougie > 19:12
    assert run["liquidation"]["timestamp"] == FIN.isoformat()
    assert cc.evaluation_admission(run) is False
    code, report = continuity(tmp_path, world, evaluation)
    assert code == 0 and report is not None
    states = {key: clause["state"] for key, clause in report["clauses"].items()}
    assert (states["c1"], states["c2"], states["c5"]) == ("DECLARED", "DECLARED", "DECLARED")
    assert (states["c3"], states["c4"]) == ("VERIFIED", "VERIFIED")
    assert report["synthetic"] is False and report["state"] == "DECLARED"


def test_two_evaluations_are_bit_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Déterminisme : deux exécutions → ``evaluation_run.json`` identique au bit ; ``--now`` n'entre que dans la
    provenance."""
    world = real_world(tmp_path, monkeypatch)
    identity = world.btc.identity
    assert run_eval(world, tmp_path / "a", candidate=identity, now=NOW)[0] == 0
    assert (
        run_eval(world, tmp_path / "b", candidate=identity, now="2026-10-01T12:00:00+00:00")[0] == 0
    )
    assert sha(tmp_path / "a" / evaluate.EVALUATION_RUN) == sha(
        tmp_path / "b" / evaluate.EVALUATION_RUN
    )
    generated = [
        cc.read_json(tmp_path / d / evaluate.PROVENANCE)["generated_at"] for d in ("a", "b")
    ]
    assert generated[0] != generated[1]


def test_selection_and_designation_write_the_same_artefact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La désignation ne change pas l'artefact, seulement sa source déclarée dans la provenance."""
    world = real_world(tmp_path, monkeypatch)
    selection = write_selection(tmp_path, world, world.btc)
    assert run_eval(world, tmp_path / "sel", selection=selection)[0] == 0
    assert run_eval(world, tmp_path / "des", candidate=world.btc.identity)[0] == 0
    assert sha(tmp_path / "sel" / evaluate.EVALUATION_RUN) == sha(
        tmp_path / "des" / evaluate.EVALUATION_RUN
    )
    sources = [cc.read_json(tmp_path / d / evaluate.PROVENANCE)["source"] for d in ("sel", "des")]
    assert sources == [
        {"kind": "selection", "path": str(selection), "sha256": sha(selection)},
        {"kind": "designation", "identity": world.btc.identity},
    ]


def test_a_passed_params_divergence_is_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """E10, partagé avec le lot 3 (``c3bc.passed_params_problems``) : une entrée ``strategies.yaml`` au nom de
    classe changerait les paramètres du run sous ``decision_timeframes`` — contrôle en échec, rien de publié."""
    world = real_world(tmp_path, monkeypatch)
    monkeypatch.setattr(
        evaluate,
        "get_settings",
        lambda: pc.engine_settings(router_entry={"params": {"atr_period": 21}}),
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["evaluation_controls"])
    assert not (tmp_path / "out" / evaluate.EVALUATION_RUN).exists()


def test_the_chain_upstream_feeds_the_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Architecture cible (brief) : temps 1 (``c3b_prefix``) → chaîne 1..4 en processus → temps 3 sur la vraie
    ``selection.json``. Quelle que soit l'issue du monde synthétique : code 2 « rien à évaluer » si et seulement si
    rien n'est retenu ; sinon code 0 et l'identité évaluée est celle du retenu."""
    data = pc.market(anchor=FIN)
    pc.install_market(monkeypatch, data)
    tp.install_database(monkeypatch, data)
    manifest_path = tp.write_manifest(tmp_path, pc.producer_manifest())
    assert tp.run_main(manifest_path, tmp_path / "prefix")[0] == 0
    result = tp._chain(tmp_path, manifest_path, tmp_path / "prefix")
    assert result["codes"] == {"anchor": 0, "entry": 0, "benchmark": 0, "select": 0}
    chain = tmp_path / "chain"
    code, logs = run_eval(
        (manifest_path, chain / "anchor.json"),
        tmp_path / "eval",
        selection=chain / "selection.json",
    )
    retained = cc.read_json(chain / "selection.json")["retained"]
    if retained is None:
        assert (code, errors(logs)) == (2, ["nothing_to_evaluate"])
        assert not (tmp_path / "eval").exists()
    else:
        assert (code, errors(logs)) == (0, [])
        run = cc.read_json(tmp_path / "eval" / evaluate.EVALUATION_RUN)
        assert (
            cc.candidate_identity(run["strategy"], run["pair"], run["params"])
            == (retained["identity"])
        )


# ---------------------------------------------------------------------------
# Journal, discipline de source, pureté à l'import
# ---------------------------------------------------------------------------


def test_evaluator_events_never_carry_identity_pair_or_metric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan, point 1 : sur le chemin sélection, seul le code est rapporté ; en succès, les événements du producteur
    ne portent ni identité, ni paire, ni métrique (moteur bouchon : aucun journal de moteur n'est capturé)."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    selection = write_selection(tmp_path, world, world.btc)
    code, logs = run_eval(world, tmp_path / "out", selection=selection)
    assert code == 0
    assert [entry["event"] for entry in logs] == ["evaluated", "written", "written"]
    text = json.dumps(logs, default=str)
    for secret in (world.btc.identity[:16], world.btc.pair, "net_pnl", "first_fill"):
        assert secret not in text


def test_the_evaluator_never_coerces_nor_opens_a_database_by_itself() -> None:
    pc.assert_source_discipline("scripts/audit/c3b_evaluate.py")


def test_importing_the_evaluator_changes_nothing() -> None:
    """Règle B4.2 : ``.env`` chargé dans ``main``, jamais à l'import ; l'import ne change pas l'environnement."""
    probe = (
        "import importlib, json, os, sys\n"
        "root = sys.argv[1]\n"
        "sys.path[:0] = [root + '/scripts/audit', root + '/scripts', root + '/src', root]\n"
        "before = dict(os.environ)\n"
        "importlib.import_module('c3b_evaluate')\n"
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
