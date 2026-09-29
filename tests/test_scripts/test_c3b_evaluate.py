"""``scripts/audit/c3b_evaluate.py`` — le producteur, temps 3 : run unique et preuves § B (C3b lot 4a), comparateur
d'évaluation et procédure § F.2 rejouable (C3b lot 4b).

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 4a » et § « Lot 4b » ; plans validés le 2026-09-28 (GO de Bruno,
avec amendements). Les attendus viennent du brief, du protocole (§ B.2, § B.4, § C.3-C.5, § F.2, § L.1), de la
procédure § F.2 écrite depuis le texte dans ``test_c3_common.py`` (``f2_procedure``) et de la chaîne elle-même,
appelée en processus sur la sortie du producteur (``c3_anchor``, ``cc.evaluation_admission``, ``c3_continuity``,
``c3_verdict``) — jamais de l'implémentation.

**Herméticité construite, comme au lot 3** : une fixture autouse remplace ``_db.ReadOnlyDatabaseManager`` (dans
``c3b_evaluate`` et ``c3b_prefix``) par un bouchon qui n'ouvre jamais de session, coupe ``.env``, fait lever les
lectures en base de ``c3b_common`` et les trois chargeurs du moteur tant qu'un test ne les remplace pas, et pointe
``CAMPAIGN_UNLOCK`` vers un chemin absent. **Aucun test base.** Les bougies ``[T, fin]`` du comparateur sont servies
par ``tp.install_database`` sur le marché synthétique ; ``benchmark.json`` (λ du préfixe) est **simulé conforme** à ce
que ``c3_benchmark`` écrit (``write_benchmark``).

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
import c3_benchmark as cb
import c3_common as cc
import c3_continuity as ccont
import c3_select as cs
import c3_verdict as cv
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
    benchmark_path: Path

    @property
    def btc(self) -> cc.Candidate:
        """Le candidat désigné du monde de test : la première identité BTC dans l'ordre lexicographique."""
        return sorted(
            (c for c in self.manifest.candidates if c.pair == "BTC/USDT"), key=lambda c: c.identity
        )[0]


#: Les λ du préfixe du candidat désigné dans ``benchmark.json`` simulé : non dyadiques, distincts entre eux et de ceux
#: des autres identités (``OTHER_LAMBDAS``), et **choisis pour que la conversion se voie** : sur la NAV du monde court,
#: ``Decimal(λ)`` au lieu de ``Decimal(str(λ))`` (``c3_benchmark.py:500``) change les rendements au bit pour 11 valeurs
#: de λ sur 999 au pas 0,001 (mesuré au passage des mutants, M10), dont 0,168 et 0,336 ; pas pour 0,123 ni 0,456.
LAMBDAS = {"dd": 0.168, "sigma": 0.336}
OTHER_LAMBDAS = {"dd": 0.9, "sigma": 0.8}


def benchmark_block(
    candidate: cc.Candidate,
    *,
    lambdas: Mapping[str, float] = OTHER_LAMBDAS,
    estimable: bool = True,
) -> dict[str, Any]:
    """Un bloc candidat **aux quinze clés** de ``c3_benchmark.candidate_block`` (``c3_benchmark.py:434-507``) :
    ``estimable`` avec ses deux ``λ`` et ses deux appariements, ou ``NOT_ESTIMABLE`` au premier gate ``λ_dd`` (λ nuls,
    ``F_NOT_ESTIMABLE``). Le producteur n'en lit que ``pair``, ``estimable`` et les deux ``λ`` ; les autres valeurs
    sont neutres."""

    def match(name: str) -> dict[str, Any]:
        return {
            "lambda": lambdas[name] if estimable else None,
            "residual": 0.0 if estimable else None,
            "crossings": 1,
            "value_at_lambda": 1.0,
            "note": None if estimable else "aucun croisement dans [0, 1]",
            "estimable": estimable,
        }

    return {
        "pair": candidate.pair,
        "target_dd": 1.0,
        "target_sigma": 0.01,
        "cagr_pct": 5.0,
        "estimable": estimable,
        "first_failed": None if estimable else "λ_dd",
        "reason": None if estimable else "F_NOT_ESTIMABLE",
        "lambda_dd": lambdas["dd"] if estimable else None,
        "lambda_sigma": lambdas["sigma"] if estimable else None,
        "cagr_blend_dd": 1.0 if estimable else None,
        "cagr_blend_sigma": 1.0 if estimable else None,
        "delta_dd": 4.0 if estimable else None,
        "delta_sigma": 4.0 if estimable else None,
        "match_dd": match("dd"),
        "match_sigma": match("sigma") if estimable else None,
    }


def write_benchmark(
    chain: Path,
    manifest_path: Path,
    anchor_path: Path,
    manifest: cc.Manifest,
    *,
    blocks: Mapping[str, Mapping[str, Any]] | None = None,
    designated: cc.Candidate | None = None,
    exit_code: int = 0,
    inputs: Mapping[str, Path] | None = None,
    lambda_mode: str = cc.LAMBDA_MODE_DECISIONAL,
) -> Path:
    """Un ``benchmark.json`` **simulé conforme** à ce que ``c3_benchmark.main`` écrit (``c3_benchmark.py:646-673``) :
    l'enveloppe de la chaîne aux empreintes réelles du manifeste et de l'ancrage (les trois autres entrées sont des
    bouchons), les clés de premier niveau, un bloc de paire à la forme de ``PairBenchmark.to_dict`` et un bloc
    ``candidate_block`` par identité. Le candidat ``designated`` porte ``LAMBDAS`` ; ``blocks`` remplace des blocs.
    Chaque test adverse ne déforme qu'un champ."""
    others: dict[str, Path] = {}
    for name in ("entry", "observations", "candles"):
        others[name] = chain / f"{name}.json"
        cc.write_json(others[name], {"bouchon": name})
    recorded = {"manifest": manifest_path, "anchor": anchor_path, **others}
    recorded.update(inputs or {})
    anchor = manifest.anchor()
    candidates = {
        c.identity: benchmark_block(
            c, lambdas=LAMBDAS if designated is not None and c == designated else OTHER_LAMBDAS
        )
        for c in manifest.candidates
    }
    candidates.update({k: dict(v) for k, v in (blocks or {}).items()})
    payload = cc.envelope(cb.STEP, datetime.fromisoformat(NOW), recorded, exit_code=exit_code)
    payload.update(
        {
            "window": {"start": manifest.window_start.isoformat(), "end": anchor.isoformat()},
            "prefix_days": (anchor - manifest.window_start).total_seconds() / 86400.0,
            "lambda_mode": lambda_mode,
            "lambda_mode_declared": manifest.lambda_mode,
            "lambda_label": cc.LAMBDA_LABEL,
            "lambda_grid": {
                "coarse_step": str(cc.LAMBDA_COARSE_STEP),
                "fine_step": str(cc.LAMBDA_FINE_STEP),
                "refine_halfwidth": str(cc.LAMBDA_REFINE_HALFWIDTH),
                "residual_max": cc.LAMBDA_RESIDUAL_MAX,
            },
            "costs": {
                "taker": str(manifest.taker),
                "pair_costs": {
                    p: {"spread": str(s), "slippage": str(sl)}
                    for p, (s, sl) in manifest.pair_costs.items()
                },
            },
            "capital": str(manifest.capital),
            "pairs": {
                pair: {
                    "buildable": True,
                    "comparable": True,
                    "reason": None,
                    "entry_stamp": cc.first_stamp_strictly_after(
                        manifest.window_start, manifest.exec_interval
                    ).isoformat(),
                    "exit_stamp": cc.last_stamp_at_or_before(
                        anchor, manifest.exec_interval
                    ).isoformat(),
                    "entry_price": "100000",
                    "exit_price": "90000",
                    "qty": "0.01",
                    "nav": [1000.0, 1000.0],
                    "returns": [0.0],
                    "cagr_pct": 0.0,
                    "comparability": {
                        "entry_stamp_present": True,
                        "exit_stamp_present": True,
                        "ff_days": 0,
                        "longest_ff_run_days": 0,
                        "ff_ok": True,
                        "n_returns_ok": True,
                        "all_finite": True,
                    },
                }
                for pair in manifest.pairs
            },
            "candidates": candidates,
        }
    )
    path = chain / "benchmark.json"
    cc.write_json(path, payload)
    return path


def make_world(tmp_path: Path, payload: Mapping[str, Any] | None = None) -> World:
    """Le manifeste de producteur du lot 3, **son** ancrage, produit par ``c3_anchor`` en processus, et son
    ``benchmark.json`` simulé conforme (λ du préfixe, ``LAMBDAS`` pour le candidat désigné)."""
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
    manifest = pc.loaded(cc.read_json(manifest_path))
    world = World(manifest_path, anchor_path, manifest, chain / "benchmark.json")
    write_benchmark(chain, manifest_path, anchor_path, manifest, designated=world.btc)
    return world


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
    for name in ("entry", "observations", "coverage"):
        others[name] = chain / f"{name}.json"
        cc.write_json(others[name], {"bouchon": name})
    recorded = {
        "manifest": world.manifest_path,
        "anchor": world.anchor_path,
        "benchmark": world.benchmark_path,
        **others,
    }
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
    benchmark: Path | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    manifest_path, anchor_path = (
        (world.manifest_path, world.anchor_path) if isinstance(world, World) else world
    )
    argv = [
        "--manifest",
        str(manifest_path),
        "--anchor",
        str(anchor_path),
        "--benchmark",
        str(benchmark if benchmark is not None else anchor_path.parent / "benchmark.json"),
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
    tp.install_database(monkeypatch, pc.market(anchor=FIN))
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
    (tmp_path / "out" / evaluate.EVALUATION).write_text("{}\n", encoding="utf-8")
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
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
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
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
    assert run["flat_start_proof"] == fx.flat_start_proof(at=T)


def test_cash_different_from_C_is_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Brief : « exiger ``usdc_balance == C`` du manifeste … sinon code 3 » ; rien n'est écrit, ``run`` jamais
    appelé."""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    engine.usdc_balance = Decimal("1000.01")
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["flat_start_proof"])
    assert engine.calls == []
    assert not (tmp_path / "out" / evaluate.EVALUATION).exists()


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
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
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
    assert cc.read_json(tmp_path / "out" / evaluate.EVALUATION)["first_fill_at"] == (
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
    assert not (tmp_path / "out" / evaluate.EVALUATION).exists()


def test_no_trade_writes_a_null_first_fill_at_that_the_chain_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief : « ``null`` si aucun trade (la chaîne le traite) ». La chaîne le traite par un refus : § L.1 v2.1, une
    évaluation réelle sans ``first_fill_at`` n'est pas admise (``R0_INVALID_RUN``, le porteur nommé) — écart
    candidat v2.2 (plan § 8). Le bloc de liquidation ne liquide rien : l'exemption ``trades == 0`` s'applique."""
    world, _, _ = stubbed(tmp_path, monkeypatch, lots=(), trades=())
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (0, [])
    run = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
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
    data = pc.market(anchor=FIN)
    pc.install_market(monkeypatch, data)
    tp.install_database(monkeypatch, data)
    return make_world(tmp_path, pc.producer_manifest(**kw))


def test_the_nominal_evaluation_is_admitted_and_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critère de fin du lot 4a : ``cc.evaluation_admission`` vrai (évaluation réelle admise) sur un artefact
    produit, et ``c3_continuity`` sur un comparateur d'évaluation synthétique rend ``c1``, ``c2``, ``c5`` =
    ``DECLARED``. Forme : exactement les clés de la fixture ``evaluation`` (lot 4b : les clés § F.2 comprises)."""
    world = real_world(tmp_path, monkeypatch)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (0, [])
    evaluation = tmp_path / "out" / evaluate.EVALUATION
    run = cc.read_json(evaluation)
    reference = fx.evaluation(fx.manifest())
    assert set(run) == set(reference)
    assert set(run["metrics"]) == set(reference["metrics"])
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
    assert sha(tmp_path / "a" / evaluate.EVALUATION) == sha(tmp_path / "b" / evaluate.EVALUATION)
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
    assert sha(tmp_path / "sel" / evaluate.EVALUATION) == sha(
        tmp_path / "des" / evaluate.EVALUATION
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
    assert not (tmp_path / "out" / evaluate.EVALUATION).exists()


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
        run = cc.read_json(tmp_path / "eval" / evaluate.EVALUATION)
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
    assert [entry["event"] for entry in logs] == ["evaluated", *["written"] * 5]
    text = json.dumps(logs, default=str)
    for secret in (
        world.btc.identity[:16],
        world.btc.pair,
        "net_pnl",
        "first_fill",
        "lambda",
        "cagr",
    ):
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


# ---------------------------------------------------------------------------
# Lot 4b — outillage des tests : bougies d'évaluation, comparateur écrit depuis le texte
# ---------------------------------------------------------------------------

#: § 0.5 : ``C = 1000`` ; brief § Lot 3 : coûts de ``config/pair_costs_b4.json`` pour la paire de déploiement.
C = Decimal("1000")
#: § F.2 (c) : « ``(fin − T)`` en secondes, divisé par 86 400, en double précision ».
N_DAYS = (FIN - T).total_seconds() / 86400.0
#: § F.2 (b), (h) : « ``L ∈ {10, 21, 42}`` » × les deux appariements ``dd`` et ``σ`` — recopiés du texte.
TEXT_COMBINATIONS = frozenset(f"{L}:{m}" for L in (10, 21, 42) for m in ("dd", "sigma"))
TEXT_B = 10_000
#: § C.3 : la première bougie d'exécution **strictement après** ``T = 19:12`` est celle de 19:15 ; la dernière
#: ``≤ fin`` est ``fin`` elle-même (minuit, sur la grille 5 min).
ENTRY_STAMP = T + timedelta(minutes=3)
EXIT_STAMP = FIN


def install_closes(
    monkeypatch: pytest.MonkeyPatch, data: pc.Market
) -> list[tuple[str, int, datetime, datetime]]:
    """``tp.install_database`` (sonde, lectures du marché synthétique), plus un journal des lectures de closes avec
    leur paire et leur intervalle."""
    tp.install_database(monkeypatch, data)
    served = c3bc.fetch_closes
    reads: list[tuple[str, int, datetime, datetime]] = []

    async def closes(
        db: Any, *, exchange: str, pair: str, interval: int, start: datetime, end: datetime
    ) -> Any:
        reads.append((pair, interval, start, end))
        return await served(
            db, exchange=exchange, pair=pair, interval=interval, start=start, end=end
        )

    monkeypatch.setattr(c3bc, "fetch_closes", closes)
    return reads


def with_exec_closes(data: pc.Market, closes: Mapping[datetime, Decimal]) -> pc.Market:
    """Le marché avec d'autres closes 5 min de BTC aux estampilles données (le reste inchangé)."""
    out = dict(data)
    out[("BTC/USDT", 5)] = [
        pc._ohlc("BTC/USDT", 5, c.timestamp, closes[c.timestamp]) if c.timestamp in closes else c
        for c in data[("BTC/USDT", 5)]
    ]
    return out


def hand_nav(*, close_in: Decimal, close_out: Decimal, marks: Sequence[Decimal]) -> list[Decimal]:
    """La NAV du B&H plein notionnel de BTC sur ``[T, fin]``, **écrite depuis la convention** (brief § Lot 4b, § C.3 ;
    ``c3_benchmark.py:11-17``) : ``C`` à ``T`` ; entrée au close de la première bougie d'exécution après ``T``, taker
    + spread + slippage ; marques ``quantité × close 1 j`` à chaque minuit intérieur ; sortie au close de la dernière
    ``≤ fin``, spread + slippage puis taker. Opérations ``Decimal`` dans l'ordre du texte de la chaîne."""
    spread, slippage = (Decimal(x) for x in pc.COSTS["BTC/USDT"])
    taker = Decimal(fx.TAKER)
    exec_in = close_in * (1 + spread + slippage)
    qty = C * (1 - taker) / exec_in
    exec_out = close_out * (1 - spread - slippage)
    return [C, *(qty * mark for mark in marks), qty * exec_out * (1 - taker)]


def expected_bench(nav: Sequence[Decimal], lambdas: Mapping[str, float]) -> dict[str, list[float]]:
    """Brief § Lot 4b : ``nav_bench[m] = blend_nav(nav_bh, λ_m, C)`` ; ``returns_bench[m] =
    cc.recompute_daily(nav_bench[m], days=n_jours).returns`` ; ``λ`` en ``Decimal(str(λ))``
    (``c3_benchmark.py:500``)."""
    return {
        m: list(
            cc.recompute_daily(
                [float(v) for v in cb.blend_nav(nav, Decimal(str(lambdas[m])), C)], days=N_DAYS
            ).returns
        )
        for m in ("dd", "sigma")
    }


def outputs(out: Path) -> dict[str, Any]:
    return {
        name: cc.read_json(out / name)
        for name in (
            evaluate.EVALUATION,
            evaluate.BENCHMARK_EVAL,
            evaluate.CANDLES_EVAL,
            evaluate.SENSITIVITY,
        )
    }


def keys_of(value: Any) -> set[str]:
    """Toutes les clés de mapping d'un payload, à toute profondeur."""
    if isinstance(value, Mapping):
        found = set(value)
        for item in value.values():
            found |= keys_of(item)
        return found
    if isinstance(value, list):
        found = set()
        for item in value:
            found |= keys_of(item)
        return found
    return set()


def chain_replay(world: World, evaluation: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Ce que ``c3_verdict.decide`` fait de l'artefact, en processus (``c3_verdict.py:686-717``) : contrat
    d'instrument, lecture stricte des réplications et des séries, **rejeu** du tirage depuis ``anchor.json``,
    recoupement au bit, bornes et estimabilité. Rend les violations et les paramètres rejoués."""
    anchor_raw = cc.read_json(world.anchor_path)
    cv._evaluation_contract(evaluation)
    replications = cv._read_replications(evaluation)
    returns, bench = cv._read_series(evaluation)
    replay, meta = cv._replay(evaluation, anchor_raw, returns, bench)
    violations: list[str] = []
    cv._cross_check_replay(replications, replay, evaluation, violations=violations)
    cv._bounds_all_positive(replications, replay, violations=violations)
    cv._estimability_of(evaluation, replications, replay, violations=violations)
    return violations, meta


# ---------------------------------------------------------------------------
# E. Comparateur d'évaluation (§ C.3-C.5)
# ---------------------------------------------------------------------------


def test_evaluation_candles_are_read_on_T_fin_for_the_evaluated_pair_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « ``candles_eval.json`` sur ``[T, fin]``, même forme que ``candles.json``, aucune estampille
    ``> fin`` » ; plan, E3 : la paire évaluée seule. Deux lectures exactement — exécution et quotidienne — bornées à
    ``[T, fin]`` ; l'artefact est relu par ``cb.load_candles`` sans refus."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    reads = install_closes(monkeypatch, pc.market(anchor=FIN))
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    assert reads == [("BTC/USDT", 5, T, FIN), ("BTC/USDT", 1440, T, FIN)]
    candles = cc.read_json(tmp_path / "out" / evaluate.CANDLES_EVAL)
    assert list(candles) == ["pairs"] and list(candles["pairs"]) == ["BTC/USDT"]
    block = candles["pairs"]["BTC/USDT"]
    assert set(block) == {"exec_interval", "exec", "daily"} and block["exec_interval"] == 5
    for series in ("exec", "daily"):
        stamps = [datetime.fromisoformat(row["t"]) for row in block[series]]
        assert stamps == sorted(set(stamps)) and T <= stamps[0] and stamps[-1] <= FIN
    assert block["exec"][0]["t"] == ENTRY_STAMP.isoformat()
    assert block["exec"][-1]["t"] == EXIT_STAMP.isoformat()
    assert [row["t"] for row in block["daily"]] == [
        (datetime(2020, 1, 16, tzinfo=UTC) + timedelta(days=k)).isoformat() for k in range(5)
    ]
    view = cb.load_candles(candles, pc.loaded(pc.producer_manifest(pairs=("BTC/USDT",))), end=FIN)
    assert list(view) == ["BTC/USDT"]


def test_the_comparator_enters_at_the_first_exec_close_after_T(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b, § C.3 : entrée « à la **clôture de la première bougie d'exécution strictement après ``T``** »,
    sortie « à la dernière ``≤ fin`` », taker + spread + slippage sur les deux jambes. Le marché porte un autre close
    à 19:10 (``≤ T``, 95 000), à 19:15 (90 000) et à ``fin`` (88 000, contre 90 000 à 23:55) : une autre borne
    d'entrée ou de sortie donne une autre NAV. ``returns_bench`` est égal au bit à la NAV dérivée à la main."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    data = with_exec_closes(
        pc.market(anchor=FIN),
        {
            T - timedelta(minutes=2): Decimal("95000"),
            ENTRY_STAMP: Decimal("90000"),
            FIN: Decimal("88000"),
        },
    )
    install_closes(monkeypatch, data)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    produced = outputs(tmp_path / "out")
    nav = hand_nav(close_in=Decimal("90000"), close_out=Decimal("88000"), marks=[pc.LEVEL] * 4)
    assert produced[evaluate.EVALUATION]["returns_bench"] == expected_bench(nav, LAMBDAS)
    assert produced[evaluate.BENCHMARK_EVAL]["comparable"] is True


def test_benchmark_eval_is_what_comparator_block_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « ``{pair, window {start: T, end: fin}, comparable, comparability {cinq tests}}`` — les clés
    que ``c3_continuity.comparator_block`` lit » ; les cinq tests sont ceux de la fixture ``benchmark_eval`` de la
    chaîne. Sur la sortie, ``comparator_block`` rend ``VERIFIED`` sans violation."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    bench = cc.read_json(tmp_path / "out" / evaluate.BENCHMARK_EVAL)
    reference = fx.benchmark_eval()
    assert set(bench) == set(reference)
    assert set(bench["comparability"]) == set(reference["comparability"])
    assert bench["pair"] == "BTC/USDT"
    assert bench["window"] == {"start": T.isoformat(), "end": FIN.isoformat()}
    assert bench["comparable"] is True and all(v is True for v in bench["comparability"].values())
    violations: list[str] = []
    block = ccont.comparator_block(bench, anchor=T, end=FIN, violations=violations)
    assert (block["state"], violations) == ("VERIFIED", [])


def test_comparable_is_the_recomputed_conjunction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ C.5 : « jours forward-fillés du benchmark » sous la règle de D1. Sans aucun close quotidien aux minuits
    intérieurs de ``[T, fin]``, ``ff_ok`` est faux : ``comparable`` est la conjonction recalculée, faux ; tout est
    écrit (E6) ; ``comparator_block`` rend ``FAILED`` **sans violation** ; la sensibilité n'apparie rien."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    data = dict(pc.market(anchor=FIN))
    data[("BTC/USDT", 1440)] = [c for c in data[("BTC/USDT", 1440)] if not T < c.timestamp < FIN]
    install_closes(monkeypatch, data)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (0, [])
    produced = outputs(tmp_path / "out")
    bench = produced[evaluate.BENCHMARK_EVAL]
    assert bench["comparable"] is False and bench["comparability"]["ff_ok"] is False
    violations: list[str] = []
    block = ccont.comparator_block(bench, anchor=T, end=FIN, violations=violations)
    assert (block["state"], violations) == ("FAILED", [])
    assert produced[evaluate.SENSITIVITY]["matches"] == {"dd": None, "sigma": None}


def test_a_non_buildable_comparator_stops_before_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan, E5 : sans la bougie d'exécution de 19:15, le comparateur n'a pas de prix d'entrée (§ C.5, « observation
    admissible aux deux bornes ») : le moteur n'est pas construit (§ C.5 v2.2 : « le producteur n'exécute pas
    l'évaluation »). Ce qu'il écrit alors — la forme de refus — vit dans le jumeau R-18."""
    world, _, built = stubbed(tmp_path, monkeypatch)
    data = dict(pc.market(anchor=FIN))
    data[("BTC/USDT", 5)] = [c for c in data[("BTC/USDT", 5)] if c.timestamp != ENTRY_STAMP]
    install_closes(monkeypatch, data)
    run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert built == []
    assert not (tmp_path / "out").exists()


def test_a_candle_after_fin_is_refused_by_the_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « aucune estampille ``> fin`` » — une lecture qui en rendrait une (base fautive) est refusée
    **par le producteur** (``c3bc.candles_artefact``), contrôle en échec (3), rien d'écrit."""
    world, _, built = stubbed(tmp_path, monkeypatch)
    data = pc.market(anchor=FIN)

    async def leaky(
        db: Any, *, exchange: str, pair: str, interval: int, start: datetime, end: datetime
    ) -> Any:
        rows = [(c.timestamp, c.close) for c in data[(pair, interval)] if start <= c.timestamp]
        return rows + [(FIN + timedelta(minutes=5), Decimal("90000"))] if interval == 5 else rows

    monkeypatch.setattr(c3bc, "fetch_closes", leaky)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["candles"])
    assert built == []
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# F. λ du préfixe, tenu fixe (§ F.2 f)
# ---------------------------------------------------------------------------


def test_lambdas_are_those_of_the_prefix_benchmark_for_the_evaluated_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « ``λ_dd``, ``λ_σ`` lus dans ``benchmark.json`` (étape 3) pour l'identité retenue, tenus fixes
    (§ F.2 f) ». Le retenu est la **seconde** identité BTC — son bloc n'est pas le premier du fichier (le writer trie
    les clés) — et porte 0,168 / 0,336 ; tous les autres blocs portent 0,9 / 0,8. ``returns_bench`` est égal au bit au
    blend de chacun des deux ``λ`` du bloc retenu, au bon appariement, en ``Decimal(str(λ))``."""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    target = sorted(
        (c for c in world.manifest.candidates if c.pair == "BTC/USDT"), key=lambda c: c.identity
    )[1]
    engine.effective_params = {"passed_params": {**target.params, "pair": target.pair}}
    write_benchmark(
        world.anchor_path.parent,
        world.manifest_path,
        world.anchor_path,
        world.manifest,
        designated=target,
    )
    assert sorted(cc.read_json(world.benchmark_path)["candidates"])[0] != target.identity
    selection = write_selection(tmp_path, world, target)
    assert run_eval(world, tmp_path / "out", selection=selection)[0] == 0
    evaluation = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
    nav = hand_nav(close_in=Decimal("90000"), close_out=Decimal("90000"), marks=[pc.LEVEL] * 4)
    assert evaluation["returns_bench"] == expected_bench(nav, LAMBDAS)
    assert evaluation["returns_bench"]["dd"] != evaluation["returns_bench"]["sigma"]
    sensitivity = cc.read_json(tmp_path / "out" / evaluate.SENSITIVITY)
    assert sensitivity["prefix"] == LAMBDAS


def test_a_not_estimable_prefix_lambda_is_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « ``NOT_ESTIMABLE`` → code 2 » — avant l'arbre, la base et le moteur."""
    world, _, built = stubbed(tmp_path, monkeypatch)
    write_benchmark(
        world.anchor_path.parent,
        world.manifest_path,
        world.anchor_path,
        world.manifest,
        designated=world.btc,
        blocks={world.btc.identity: benchmark_block(world.btc, estimable=False)},
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["lambda_not_estimable"])
    assert (built, tp._StubReadOnlyDb.built) == ([], [])


@pytest.mark.parametrize("name", ["manifest", "anchor"])
def test_a_benchmark_of_another_manifest_or_anchor_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """``cc.check_inputs_match`` : le ``benchmark.json`` doit avoir été calculé sur les fichiers fournis."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    other = tmp_path / f"autre_{name}.json"
    cc.write_json(other, {"autre": name})
    write_benchmark(
        world.anchor_path.parent,
        world.manifest_path,
        world.anchor_path,
        world.manifest,
        designated=world.btc,
        inputs={name: other},
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["benchmark_inputs_mismatch"])


@pytest.mark.parametrize(
    "fault", ["amont_en_echec", "mode_reestime"], ids=["amont-en-echec", "mode-non-decisionnel"]
)
def test_a_failed_or_non_decisional_benchmark_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """``cc.require_upstream_ok`` ; § C.4 : seul le mode ``prefix`` est décisionnel."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    write_benchmark(
        world.anchor_path.parent,
        world.manifest_path,
        world.anchor_path,
        world.manifest,
        designated=world.btc,
        exit_code=1 if fault == "amont_en_echec" else 0,
        lambda_mode="reestimated" if fault == "mode_reestime" else cc.LAMBDA_MODE_DECISIONAL,
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["benchmark_refused"])


def test_a_selection_computed_on_another_benchmark_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan, E2 : sur le chemin sélection, ``c3_select`` a enregistré l'empreinte du ``benchmark.json`` qu'il a lu
    (``inputs_sha256.benchmark``) ; ``--benchmark`` doit être ce fichier-là."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    other = tmp_path / "autre_benchmark.json"
    cc.write_json(other, {"autre": "benchmark"})
    selection = write_selection(tmp_path, world, world.btc, inputs={"benchmark": other})
    code, logs = run_eval(world, tmp_path / "out", selection=selection)
    assert (code, errors(logs)) == (2, ["selection_benchmark_mismatch"])


def test_an_identity_absent_from_the_benchmark_is_refused_without_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world, _, _ = stubbed(tmp_path, monkeypatch)
    raw = dict(cc.read_json(world.benchmark_path))
    raw["candidates"] = {k: v for k, v in raw["candidates"].items() if k != world.btc.identity}
    cc.write_json(world.benchmark_path, raw)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (2, ["benchmark_refused"])
    assert world.btc.identity[:16] not in json.dumps(logs, default=str)


def test_a_benchmark_block_of_another_pair_is_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le bloc de l'identité évaluée porte sa paire (``c3_benchmark.candidate_block``) : une autre paire sous la même
    identité est une incohérence amont — contrôle en échec (3), jamais un λ appliqué au mauvais comparateur."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    block = {**benchmark_block(world.btc, lambdas=LAMBDAS), "pair": "SOL/USDT"}
    write_benchmark(
        world.anchor_path.parent,
        world.manifest_path,
        world.anchor_path,
        world.manifest,
        designated=world.btc,
        blocks={world.btc.identity: block},
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["benchmark_inconsistent"])


@pytest.mark.parametrize("value", [-0.001, 1.001])
def test_a_lambda_outside_the_unit_interval_is_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: float
) -> None:
    """§ F.2 (g) : « ``λ ∈ [0, 1]`` »."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    write_benchmark(
        world.anchor_path.parent,
        world.manifest_path,
        world.anchor_path,
        world.manifest,
        designated=world.btc,
        blocks={
            world.btc.identity: benchmark_block(world.btc, lambdas={"dd": value, "sigma": 0.5})
        },
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["lambda_domain"])


# ---------------------------------------------------------------------------
# G. Procédure § F.2 — rejouable au bit par la chaîne
# ---------------------------------------------------------------------------

_N = fx.N_EVAL_POINTS - 1
_BENCHES = {
    "cash": ([0.0] * _N, [0.0] * _N),
    "mixte": ([0.0] * _N, fx.varying_returns(5)),
    "varie": (fx.varying_returns(5), fx.varying_returns(7)),
}


#: Séries de configuration : le témoin des fixtures, et ``varying_returns(9)`` — sur le témoin, la somme exacte
#: (``math.fsum``) et la somme de numpy du § F.2 (c) coïncident ; sur ``varying_returns(9)``, non (mesuré, M12).
_CONFIGS = {"temoin": fx.witness_returns(), "varie9": fx.varying_returns(9)}


@pytest.mark.parametrize("pair_index", [0, 1])
@pytest.mark.parametrize("bench", sorted(_BENCHES))
@pytest.mark.parametrize("config_name", sorted(_CONFIGS))
def test_f2_is_bit_equal_to_the_procedure_written_from_the_text(
    tmp_path: Path, config_name: str, bench: str, pair_index: int
) -> None:
    """Brief § Lot 4b : « sur les séries témoin des fixtures (``witness_returns``, cash), sortie égale au bit à
    ``f2_procedure`` (suites, écartées, bornes, ``cagr_pct``, ``delta_dd``) ». ``f2_procedure`` est la procédure
    § F.2 (b)-(d) **écrite depuis le texte** dans ``test_c3_common.py`` ; l'égalité vaut aussi sur le texte JSON
    écrit par le writer strict (``repr`` le plus court, § F.2 d)."""
    config = _CONFIGS[config_name]
    dd, sigma = _BENCHES[bench]
    returns_bench = {"dd": dd, "sigma": sigma}
    block = evaluate.f2_block(
        config,
        returns_bench,
        inputs=evaluate.ReplayInputs(seed=fx.SEED, pair_index=pair_index, days=fx.EVAL_DAYS),
        net_pnl=42.0,
    )
    expected = fx.f2_procedure(
        config, returns_bench, seed=fx.SEED, pair_index=pair_index, days=fx.EVAL_DAYS
    )
    assert set(block["replications"]) == set(expected["replications"]) == TEXT_COMBINATIONS
    for combination, reference in expected["replications"].items():
        assert block["replications"][combination] == reference, combination
    assert block["metrics"] == {
        "net_pnl": 42.0,
        "cagr_pct": expected["cagr_config"],
        "delta_dd": expected["delta_hat"]["dd"],
    }
    assert block["returns_config"] == config and block["returns_bench"] == returns_bench
    import _common

    ours = _common.write_json_strict(tmp_path / "ours.json", block["replications"])
    text = _common.write_json_strict(tmp_path / "text.json", expected["replications"])
    assert ours == text


def test_the_instrument_contract_is_that_of_the_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ F.2 (b) : ``B = 10 000``, ``L ∈ {10, 21, 42}``, les deux appariements, l'environnement « en quatre champs,
    et quatre seulement » ; ``c3_verdict._evaluation_contract`` passe sur l'artefact produit dans le même
    environnement."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    evaluation = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
    assert evaluation["B"] == TEXT_B
    assert set(evaluation["replications"]) == TEXT_COMBINATIONS
    assert set(evaluation["returns_bench"]) == {"dd", "sigma"}
    assert evaluation["environment"] == fx.environment()
    cv._evaluation_contract(evaluation)


def test_returns_config_is_recompute_daily_of_the_exported_equity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « ``returns_config = cc.recompute_daily(equity_daily.values, days=n_jours).returns``,
    dérivée de la série exportée par la fonction de la chaîne » — vrai moteur, artefact relu depuis le disque."""
    world = real_world(tmp_path, monkeypatch)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    evaluation = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
    recomputed = cc.recompute_daily(evaluation["equity_daily"]["values"], days=N_DAYS)
    assert evaluation["returns_config"] == list(recomputed.returns)
    assert len(evaluation["returns_config"]) == len(cc.daily_grid(T, FIN)) - 1


#: Monde long (lot 4b) : une fenêtre de 154 jours (2020-01-06 → 2020-06-08), dont l'évaluation porte **47 rendements**,
#: plus que la plus longue des longueurs de bloc (§ F.2 b, ``L = 42``). Sur le monde court (5 rendements), chaque
#: réplication est une rotation de la série entière — la même somme pour tous les tirages : ni la graine ni l'index de
#: paire ne s'y voient (M01 y survivait, défaut du test relevé au passage des mutants).
LONG_START = datetime(2020, 1, 6, tzinfo=UTC)
LONG_END = datetime(2020, 6, 8, tzinfo=UTC)


def long_world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, pairs: Sequence[str] = pc.PAIRS
) -> World:
    """Le monde de producteur sur la fenêtre longue, ses bougies d'évaluation servies par la base bouchonnée, et un
    moteur bouchon **conforme sur cette fenêtre** : grille quotidienne ``[T, fin]``, NAV variable (rendements
    ``fx.varying_returns(9)``), métriques cohérentes avec la NAV, liquidation dans la cellule finale."""
    world = make_world(tmp_path, pc.producer_manifest(pairs=pairs, start=LONG_START, end=LONG_END))
    anchor, end = world.manifest.anchor(), world.manifest.window_end
    tp.install_database(monkeypatch, pc.market(anchor=end))
    n_points = len(cc.daily_grid(anchor, end))
    values = [1000.0]
    for r in fx.varying_returns(9, n=n_points - 1):
        values.append(values[-1] * (1.0 + r))
    engine = StubEngine(
        world,
        stamp=end - timedelta(minutes=5),
        equity={"start": anchor.isoformat(), "end": end.isoformat(), "values": values},
    )
    engine._metrics = {
        "net_pnl": values[-1] - 1000.0,
        "ending_balance": values[-1],
        "starting_balance": 1000.0,
    }
    spy_build(monkeypatch, engine)
    return world


@pytest.mark.parametrize(
    "pairs", [("BTC/USDT", "SOL/USDT"), ("SOL/USDT", "BTC/USDT")], ids=["tri", "inverse"]
)
def test_the_chain_replay_finds_the_declared_artefact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pairs: tuple[str, str]
) -> None:
    """§ F.2 (d) : la chaîne « rejoue le tirage — graine du manifeste, index de paire, ``n_jours`` » et « toute
    différence avec ce que l'artefact déclare est une violation ». Rejouée en processus sur l'artefact produit :
    **zéro violation**, et les paramètres rejoués sont ceux du texte — graine du manifeste, index de BTC dans les
    paires **triées** (0, que le manifeste liste BTC en premier ou en second), ``(fin − T)`` / 86 400. Monde long :
    47 rendements, plus que ``L = 42`` — sur 5 rendements le tirage ne se voit pas (``long_world``)."""
    world = long_world(tmp_path, monkeypatch, pairs=pairs)
    anchor, end = world.manifest.anchor(), world.manifest.window_end
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    evaluation = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
    assert len(evaluation["returns_config"]) == len(cc.daily_grid(anchor, end)) - 1 > 42
    violations, meta = chain_replay(world, evaluation)
    assert violations == []
    assert meta == {
        "seed": world.manifest.seed,
        "pair_index": 0,
        "days": (end - anchor).total_seconds() / 86400.0,
    }


def test_n_days_never_comes_from_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ F.2 (c) : ``n_jours`` vient des bornes. Le bouchon déclare ``duration_days = 5,0`` ; la provenance porte
    ``(fin − T)`` / 86 400 et le rejeu de la chaîne ne voit aucune violation. (Sur le vrai ``GridBacktester``,
    ``duration_days`` est la même expression, ``backtest.py:2869`` : ce test épingle la source, plan E8.)"""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    engine._metrics["duration_days"] = 5.0
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    provenance = cc.read_json(tmp_path / "out" / evaluate.PROVENANCE)
    assert provenance["replay"]["days"] == N_DAYS
    violations, _ = chain_replay(world, cc.read_json(tmp_path / "out" / evaluate.EVALUATION))
    assert violations == []


def test_an_anchor_seed_different_from_the_manifest_is_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan, E9 : la graine est lue dans ``anchor.uncertainty.seed`` et recoupée à celle du manifeste (§ F.2 b)."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    raw = dict(cc.read_json(world.anchor_path))
    raw["uncertainty"] = {**raw["uncertainty"], "seed": world.manifest.seed + 1}
    cc.write_json(world.anchor_path, raw)
    write_benchmark(
        world.anchor_path.parent,
        world.manifest_path,
        world.anchor_path,
        world.manifest,
        designated=world.btc,
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["replay_inputs"])


def test_three_series_of_different_lengths_are_3_before_any_draw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « trois séries de même longueur, sinon code 3 avant tout tirage ». Une NAV à 0 au milieu de la
    grille rend un rendement indéfini (``recompute_daily`` le saute) : la configuration a un rendement de moins que
    le comparateur. Aucun tirage, rien d'écrit. Même contrôle en unitaire, NAV du comparateur plus courte."""
    values = [1000.0 + 0.5 * k for k in range(len(cc.daily_grid(T, FIN)))]
    values[2] = 0.0
    draws = tp.spy(monkeypatch, cc, "replay_bootstrap")
    world, _, _ = stubbed(
        tmp_path,
        monkeypatch,
        equity={"start": T.isoformat(), "end": FIN.isoformat(), "values": values},
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["series_length"])
    assert draws == []
    assert not (tmp_path / "out").exists()
    with pytest.raises(c3bc.ProducerControlError) as caught:
        evaluate.evaluation_series(
            [1000.0, 1001.0, 1002.0],
            nav_bh=[C, C],
            lambdas={"dd": Decimal("0.5"), "sigma": Decimal("0.5")},
            capital=C,
            days=2.0,
        )
    assert caught.value.control == "series_length"


@pytest.mark.parametrize("case", ["ruine", "explosion"])
def test_an_invalid_input_is_3_before_any_draw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """§ F.2 (e), table : « un rendement ``≤ −1`` dans les données fournies » (NAV finale à 0 : rendement −1) ou « une
    série dont le ``CAGR`` observé n'est pas fini » (NAV qui explose : l'exponentielle déborde) est une entrée
    invalide — contrôle en échec (3), aucun artefact ; dans le premier cas, aucun tirage."""
    values = [1000.0 + 0.5 * k for k in range(len(cc.daily_grid(T, FIN)))]
    if case == "ruine":
        values[-1] = 0.0
    else:
        values[1:] = [1e300] * (len(values) - 1)
    draws = tp.spy(monkeypatch, cc, "replay_bootstrap")
    world, _, _ = stubbed(
        tmp_path,
        monkeypatch,
        equity={"start": T.isoformat(), "end": FIN.isoformat(), "values": values},
    )
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (3, ["f2_invalid_input"])
    assert not (tmp_path / "out").exists()
    if case == "ruine":
        assert draws == []


def test_evaluation_json_has_exactly_the_keys_of_the_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brief § Lot 4b : « ``evaluation.json`` : exactement les clés de la fixture ``evaluation`` de
    ``test_c3_common.py``, pas une de plus ». Ni ``λ`` ni sensibilité (§ F.2 f : « jamais dans evaluation.json »)."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    evaluation = cc.read_json(tmp_path / "out" / evaluate.EVALUATION)
    reference = fx.evaluation(fx.manifest())
    assert set(evaluation) == set(reference)
    assert (
        set(evaluation["metrics"])
        == set(reference["metrics"])
        == {
            "net_pnl",
            "cagr_pct",
            "delta_dd",
        }
    )
    for combination, item in evaluation["replications"].items():
        assert set(item) == set(reference["replications"][combination])
    assert not [k for k in keys_of(evaluation) if "lambda" in k or "sensitiv" in k]


def test_the_full_chain_verifies_a_produced_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'image locale du run serveur : temps 1 (``c3b_prefix``), chaîne 1..4, temps 3, puis ``c3_verdict.py chain``
    **complète** sur les sorties du producteur : code 0, ``chain.verified`` vrai, aucune violation, cinq étapes en
    code 0.

    Le monde synthétique n'a **aucun candidat estimable** au préfixe (D3 : trop peu de cycles en 9,8 jours) :
    ``c3_select`` s'abstient, le chemin sélection rendrait 2 « rien à évaluer ». Le temps 3 tourne donc sur la
    première identité BTC désignée, ses ``λ`` pris dans un ``benchmark.json`` simulé conforme aux empreintes réelles
    du manifeste et de l'ancrage. La chaîne ne voit pas ``λ`` (plan, E11) ; elle **lit, rejoue et recoupe** tout
    l'artefact avant de décider l'abstention (``c3_verdict.py:686-717`` avant ``:724``). Le chemin sélection
    lui-même traverse la chaîne au run serveur."""
    import shutil

    data = pc.market(anchor=FIN)
    pc.install_market(monkeypatch, data)
    tp.install_database(monkeypatch, data)
    payload = pc.producer_manifest()
    manifest_path = tp.write_manifest(tmp_path, payload)
    assert tp.run_main(manifest_path, tmp_path / "prefix")[0] == 0
    first = tp._chain(tmp_path, manifest_path, tmp_path / "prefix")
    assert first["codes"] == {"anchor": 0, "entry": 0, "benchmark": 0, "select": 0}
    chain = tmp_path / "chain"
    assert cc.read_json(chain / "selection.json")["retained"] is None
    manifest = pc.loaded(payload)
    btc = sorted((c for c in manifest.candidates if c.pair == "BTC/USDT"), key=lambda c: c.identity)
    lambdas = tmp_path / "lambdas"
    lambdas.mkdir()
    benchmark = write_benchmark(
        lambdas, manifest_path, chain / "anchor.json", manifest, designated=btc[0]
    )
    code, logs = run_eval(
        (manifest_path, chain / "anchor.json"),
        tmp_path / "eval",
        candidate=btc[0].identity,
        benchmark=benchmark,
    )
    assert (code, errors(logs)) == (0, [])
    registry = tmp_path / "registry.json"
    shutil.copy(chain / "variants.json", registry)
    prefix_out, eval_out, out = tmp_path / "prefix", tmp_path / "eval", tmp_path / "verdict"
    code = cv.main(
        [
            "chain",
            "--manifest",
            str(manifest_path),
            "--observations",
            str(prefix_out / "observations.json"),
            "--coverage",
            str(prefix_out / "coverage.json"),
            "--candles",
            str(prefix_out / "candles.json"),
            "--evaluation",
            str(eval_out / evaluate.EVALUATION),
            "--benchmark-eval",
            str(eval_out / evaluate.BENCHMARK_EVAL),
            "--registry",
            str(registry),
            "--out-dir",
            str(out),
            "--campaign",
            "C3B_TEST",
            "--now",
            NOW,
        ]
    )
    assert code == 0
    verdict = cc.read_json(out / "verdict.json")
    assert verdict["chain"]["verified"] is True and verdict["violations"] == []
    assert [(s["name"], s["exit_code"]) for s in verdict["chain"]["steps"]] == [
        ("anchor", 0),
        ("entry", 0),
        ("benchmark", 0),
        ("select", 0),
        ("continuity", 0),
    ]


def test_two_evaluations_are_bit_identical_on_every_artefact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Déterminisme, lot 4b : les quatre artefacts identiques au bit entre deux exécutions ; ``--now`` n'entre que
    dans la provenance. Vrai moteur."""
    world = real_world(tmp_path, monkeypatch)
    identity = world.btc.identity
    assert run_eval(world, tmp_path / "a", candidate=identity, now=NOW)[0] == 0
    assert (
        run_eval(world, tmp_path / "b", candidate=identity, now="2026-10-01T12:00:00+00:00")[0] == 0
    )
    for name in (
        evaluate.EVALUATION,
        evaluate.BENCHMARK_EVAL,
        evaluate.CANDLES_EVAL,
        evaluate.SENSITIVITY,
    ):
        assert sha(tmp_path / "a" / name) == sha(tmp_path / "b" / name), name


def test_selection_and_designation_write_the_same_artefacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lot 4b : la désignation ne change aucun des quatre artefacts, seulement la source de la provenance."""
    world = real_world(tmp_path, monkeypatch)
    selection = write_selection(tmp_path, world, world.btc)
    assert run_eval(world, tmp_path / "sel", selection=selection)[0] == 0
    assert run_eval(world, tmp_path / "des", candidate=world.btc.identity)[0] == 0
    for name in (
        evaluate.EVALUATION,
        evaluate.BENCHMARK_EVAL,
        evaluate.CANDLES_EVAL,
        evaluate.SENSITIVITY,
    ):
        assert sha(tmp_path / "sel" / name) == sha(tmp_path / "des" / name), name


def test_a_designation_before_the_campaign_writes_the_full_artefact_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garde de désignation reprise (plan 4a, amendement 2) : refusée sur la campagne (tests de la section A),
    admise hors campagne — et, au lot 4b, elle écrit les cinq fichiers."""
    world, _, _ = stubbed(tmp_path, monkeypatch)
    code, logs = run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    assert (code, errors(logs)) == (0, [])
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == sorted(evaluate.FINAL_ARTEFACTS)


# ---------------------------------------------------------------------------
# H. Sensibilité descriptive (§ F.2 f, § C.4)
# ---------------------------------------------------------------------------


def test_the_sensitivity_is_the_reestimated_lambda_and_stays_out_of_the_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ F.2 (f) : « la ré-estimation post-ancrage est calculée et rapportée comme sensibilité descriptive » ; § C.4 :
    mode ré-estimé, « DESCRIPTIF uniquement », étiquette obligatoire. Même recherche que le préfixe (§ F.2 g,
    ``cb.match_lambda``) sur la NAV du comparateur d'évaluation, cibles recalculées sur la trajectoire évaluée."""
    world, engine, _ = stubbed(tmp_path, monkeypatch)
    assert run_eval(world, tmp_path / "out", candidate=world.btc.identity)[0] == 0
    sensitivity = cc.read_json(tmp_path / "out" / evaluate.SENSITIVITY)
    assert engine._equity is not None
    daily = cc.recompute_daily(engine._equity["values"], days=N_DAYS)
    nav = hand_nav(close_in=Decimal("90000"), close_out=Decimal("90000"), marks=[pc.LEVEL] * 4)
    targets = {"dd": daily.mdd_daily, "sigma": daily.sigma_daily}
    assert sensitivity["targets"] == targets
    for m in ("dd", "sigma"):
        target = targets[m]
        assert target is not None
        expected = cb.match_lambda(cb.LambdaCurve(nav, C, m), target).to_dict()
        assert sensitivity["matches"][m] == expected, m
    assert sensitivity["lambda_mode"] == "reestimated" and sensitivity["status"] == "DESCRIPTIF"
    assert sensitivity["lambda_label"] == cc.LAMBDA_LABEL
    assert sensitivity["window"] == {"start": T.isoformat(), "end": FIN.isoformat()}


# ---------------------------------------------------------------------------
# § C.5 v2.2 (AM-06) — le producteur écrit la forme de refus et l'export de bougies d'évaluation (R-18)
# ---------------------------------------------------------------------------

R18 = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="R-18 : § C.5 v2.2 (AM-06), refus amont d'un comparateur non constructible — outillage à venir",
)


@R18
def test_R18_a_non_buildable_comparator_writes_the_refusal_form_and_the_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§ C.5 v2.2 : « Il écrit l'artefact d'évaluation sous sa forme de refus : l'identité de la configuration, la
    fenêtre `[T, fin]`, et un bloc `refused` qui porte la raison `comparator_not_buildable` et un motif, sans
    aucune série » ; § L.1 v2.2 : sur cette route, « l'export de bougies d'évaluation [est exigé] ». Jumeau de
    l'ancien refus (2), rien d'écrit. Noms de clés indicatifs."""
    world, _, built = stubbed(tmp_path, monkeypatch)
    data = dict(pc.market(anchor=FIN))
    data[("BTC/USDT", 5)] = [c for c in data[("BTC/USDT", 5)] if c.timestamp != ENTRY_STAMP]
    install_closes(monkeypatch, data)
    run_eval(world, tmp_path / "out", candidate=world.btc.identity)
    out = tmp_path / "out"
    assert (out / evaluate.EVALUATION).exists(), "aucun artefact d'évaluation sous forme de refus"
    evaluation = cc.read_json(out / evaluate.EVALUATION)
    assert evaluation["refused"]["reason"] == "comparator_not_buildable"
    assert evaluation["refused"]["window"] == {"start": T.isoformat(), "end": FIN.isoformat()}
    assert {"strategy", "pair", "params"} <= set(evaluation)
    assert not {"returns_config", "returns_bench", "equity_daily", "replications"} & set(evaluation)
    assert (out / evaluate.CANDLES_EVAL).exists()
    assert built == []
