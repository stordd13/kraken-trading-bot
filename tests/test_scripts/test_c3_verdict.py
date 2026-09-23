"""C3 — l'issue, la chaîne de verdict, et la préséance de l'estimabilité (§ H.0, § H.1, § F.8).

Tout est **synthétique** : l'issue est une fonction pure d'objets JSON, donc ni base ni campagne ne
sont nécessaires. Les fixtures sont construites pour piéger ce que le protocole nomme, pas le chemin
heureux, et **chacune asserte l'issue interdite autant que l'issue attendue** — c'est la doctrine des
tests négatifs du validateur, appliquée aux verdicts.

Les trois premières fixtures couvrent les trois cas que le gate a nommés, parce qu'elles vérifient
les **conséquences** des règles, ce qu'un index de symboles ne peut pas faire :

* une configuration **inactive** donne ``inconclusif (F_NOT_ESTIMABLE)`` et **jamais** ``réfuté`` —
  elle échoue `Q1` et `Q2`, mais elle échoue **aussi** `E1`, et le § H.0 rend l'estimabilité
  préalable au verdict économique ;
* un **comparateur cash** (`λ = 0`) face à une stratégie active donne un verdict économique
  calculable, et **jamais** ``F_NOT_ESTIMABLE`` — `E1` ne porte pas sur le comparateur ;
* **deux trajectoires variables identiques** sous rééchantillonnage apparié déclenchent `E2`, parce
  que leur `Δ*` est constamment nul alors qu'aucune des deux n'est déterministe.
"""

# ruff: noqa: E402
from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from functools import cache
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))
sys.path.insert(0, str(_project_root / "tests"))

import c3_anchor as ca
import c3_benchmark as cb
import c3_common as cc
import c3_entry as ce
import c3_select as cs
import c3_verdict as cv

from test_scripts import test_c3_common as fx

REAL_OBSERVATIONS = _project_root / "results" / "rejeu_grid_20260919" / "P7_phase1_grid.json"
REAL_DIR = _project_root / "results" / "c3a_entry_validation"
REAL_MANIFEST = REAL_DIR / "manifest_rejeu_grid_20260919.json"
REAL_REGISTRY = REAL_DIR / "variants.json"

N_DAYS = 329  # longueur de la fenêtre d'évaluation de l'ancrage déclaré, en jours
SEED = 20260921
#: Petit échantillon réservé aux tests de **primitives numériques** (`cc.estimability`, `_bootstrap`
#: seul). Un artefact qui le porterait **n'est pas un artefact C3 conforme** : le contrat § F.2 (b)
#: fixe `B = BOOTSTRAP_B`, et tout chemin `decide()` / `main()` de ce fichier tourne à cette valeur.
B_SMALL_PRIMITIVE = 400


@cache
def _bootstrap_cached(
    cfg: tuple[float, ...], bch: tuple[float, ...], block_length: int, b: int
) -> tuple[np.ndarray, int]:
    n = len(cfg)
    rng = np.random.default_rng([SEED, 0, block_length])
    starts = cc.block_start_indices(rng, n, block_length, b)
    idx = cc.block_indices(starts, block_length, n)
    return cc.paired_delta_stars(cfg, bch, idx, fx.EVAL_DAYS)


def _bootstrap(
    returns_config, returns_bench, *, block_length: int = 21, b: int = cc.BOOTSTRAP_B
) -> tuple[np.ndarray, int]:
    """Le vrai chemin numérique du § F.2 : indices appariés, `Δ*`, réplications écartées.

    `B` vaut ``BOOTSTRAP_B`` par défaut — les fixtures verdict-complet sont **conformes au contrat**.
    Mémoïsé par séries : les mêmes 10 000 réplications servent à tous les tests d'un même témoin.
    """
    deltas, discarded = _bootstrap_cached(
        tuple(float(x) for x in returns_config),
        tuple(float(x) for x in returns_bench),
        block_length,
        b,
    )
    return deltas.copy(), discarded


def _evaluation_series(
    returns_config: Any, returns_bench: Any, *, net_pnl: float = 42.0
) -> dict[str, Any]:
    """Les champs de l'évaluation qu'un producteur conforme tire de ses séries (§ F.2 v2.1) : suites,
    écartées et bornes par combinaison, `cagr_pct` (Q2) et `delta_dd` (Q3) recalculables ; seul `net_pnl`
    (Q1) est déclaré. La procédure est celle de `fx.f2_procedure`, écrite depuis le texte ; graine du
    manifeste, paire d'index 0 (`anchor.pairs` = `["BTC/USDC"]`), `n_jours` exact de la fenêtre."""
    bench = fx.bench_by_matching(returns_bench)
    procedure = fx.f2_procedure(returns_config, bench, seed=SEED, pair_index=0)
    return {
        "returns_config": [float(x) for x in returns_config],
        "returns_bench": bench,
        "environment": fx.environment(),
        "B": cc.BOOTSTRAP_B,
        "replications": procedure["replications"],
        "metrics": {
            "net_pnl": net_pnl,
            "cagr_pct": procedure["cagr_config"],
            "delta_dd": procedure["delta_hat"]["dd"],
        },
    }


def _reseries(
    artifacts: dict[str, Any], returns_config: Any, returns_bench: Any, *, net_pnl: float = 42.0
) -> None:
    """Remplace les séries de l'évaluation et tout ce qui en dérive — l'artefact reste cohérent."""
    artifacts["evaluation"].update(
        _evaluation_series(returns_config, returns_bench, net_pnl=net_pnl)
    )


def _artifacts(
    *,
    returns_config,
    returns_bench,
    net_pnl: float = 42.0,
    metrics: dict[str, Any] | None = None,
    bounds: dict[str, float] | None = None,
    provenance: str = cc.PROVENANCE_CLEAN,
) -> dict[str, dict[str, Any]]:
    series = _evaluation_series(returns_config, returns_bench, net_pnl=net_pnl)
    if metrics is not None:
        series["metrics"].update(metrics)
    for combination, bound in (bounds or {}).items():
        series["replications"][combination]["bound"] = bound
    identity = cc.candidate_identity("s", "BTC/USDC", {"a": 1})
    window = {"start": fx.ANCHOR.isoformat(), "end": fx.WINDOW_END.isoformat()}
    return {
        "entry": {**_envelope(), "ok": True, "refusal": None},
        "anchor": {
            **_envelope(),
            "anchor": fx.ANCHOR.isoformat(),
            "window": {"start": fx.WINDOW_START.isoformat(), "end": fx.WINDOW_END.isoformat()},
            "universe_provenance": provenance,
            "variant_key": VARIANT_KEY,
            "pairs": ["BTC/USDC"],
            "uncertainty": {
                "seed": SEED,
                "B": cc.BOOTSTRAP_B,
                "block_lengths": list(cc.BLOCK_LENGTHS),
                "bound_level": cc.BOUND_LEVEL,
            },
        },
        "selection": {
            **_envelope(),
            "status": "SÉLECTION_VALIDE"
            if provenance == cc.PROVENANCE_CLEAN
            else "SÉLECTION_DESCRIPTIVE",
            "reason": None,
            "provenance": provenance,
            "admissible": [identity],
            "survivors": [identity],
            "ranking": [identity],
            "retained": {"identity": identity},
        },
        "continuity": {
            **_envelope(),
            "identity": identity,
            "pair": "BTC/USDC",
            "synthetic": True,
            "evaluation_window": dict(window),
            "state": "NOT_VERIFIABLE",
            "clauses": {
                "c1": {"state": "NOT_VERIFIABLE", "detail": "aucune preuve"},
                "c2": {"state": "DECLARED", "detail": "un seul appel"},
                "c3": {"state": "VERIFIED", "detail": "prouvée par lot"},
                "c4": {"state": "VERIFIED", "detail": "amorçage"},
                "c5": {"state": "NOT_VERIFIABLE", "detail": "non exporté"},
            },
            "stamp_cell": {"state": "VERIFIED", "detail": "dans la cellule finale"},
            "comparator": {
                "state": "VERIFIED",
                "detail": "comparable",
                "tests": {
                    "entry_stamp_present": True,
                    "exit_stamp_present": True,
                    "ff_ok": True,
                    "n_returns_ok": True,
                    "all_finite": True,
                    "window_ok": True,
                },
                "window": {"declared": dict(window), "expected": dict(window)},
            },
            "warmup_anchor_ok": True,
            "benchmark_comparable": True,
            "stamp_same_daily_cell": True,
            "liquidation_normalised": True,
        },
        "evaluation": {
            "synthetic": True,
            "strategy": "s",
            "pair": "BTC/USDC",
            "params": {"a": 1},
            **series,
        },
    }


VARIANT_KEY = "ab" * 32
MANIFEST_SHA = "cd" * 32
OBSERVATIONS_SHA = "ef" * 32


def _envelope() -> dict[str, Any]:
    """L'enveloppe d'un artefact amont réussi ; les empreintes sont posées à l'écriture."""
    return {
        "ok": True,
        "invalide": False,
        "exit_code": 0,
        "protocole": cc.protocol_descriptor(),
        "inputs_sha256": {},
    }


def _witness() -> list[float]:
    """Le témoin d'évaluation des fixtures (`fx.witness_returns`) : contre du cash, six bornes > 0."""
    return fx.witness_returns(N_DAYS)


def _varying(seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(rng.normal(0.0005, 0.02, N_DAYS))


# ---------------------------------------------------------------------------
# Fixture 1 — configuration inactive
# ---------------------------------------------------------------------------


def test_configuration_inactive_donne_inconclusif_et_jamais_refute() -> None:
    """§ H.0 : elle échoue `Q1` et `Q2`, mais elle échoue **aussi** `E1`, qui est préalable."""
    flat = [0.0] * N_DAYS
    artifacts = _artifacts(
        returns_config=flat,
        returns_bench=_varying(11),
        net_pnl=0.0,
    )
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)

    assert violations == []
    assert decision.issue == cc.ISSUE_INCONCLUSIF
    assert decision.reason == "F_NOT_ESTIMABLE"
    # L'issue interdite, assertée explicitement.
    assert decision.issue != cc.ISSUE_REFUTE
    assert decision.issue != cc.ISSUE_VALIDE
    # Et la cause est bien E1, pas E2 : le comparateur varie, donc `Δ*` varie.
    est = decision.estimability
    assert est is not None
    assert est["E1"] is False
    assert est["E2"] is True
    assert est["nonzero_ratio"] == 0.0
    # Les portes Q n'ont même pas été lues : la préséance du § H.0 coupe avant.
    assert decision.gates == {}


def test_configuration_inactive_echouerait_les_portes_Q_si_on_les_lisait() -> None:
    """Le fait que `Q1`/`Q2` échouent est vrai — et c'est précisément pourquoi la préséance compte.

    Sans le § H.0, cette configuration serait ``réfuté`` sur une absence d'observation.
    """
    gates = cv._gate_results({"metrics": {"net_pnl": 0.0, "cagr_pct": 0.0, "delta_dd": -1.5}})
    assert gates == {"Q1": False, "Q2": False, "Q3": False}


# ---------------------------------------------------------------------------
# Fixture 2 — comparateur cash (λ = 0) face à une stratégie active
# ---------------------------------------------------------------------------


def test_comparateur_cash_donne_un_verdict_economique_et_jamais_F_NOT_ESTIMABLE() -> None:
    """§ A.13 E1 : le comparateur est exempté, sans quoi toute comparaison à `λ = 0` serait vaine."""
    cash = [0.0] * N_DAYS  # comparateur déterministe : λ = 0, cash pur
    artifacts = _artifacts(
        returns_config=_witness(),
        returns_bench=cash,
        net_pnl=42.0,
    )
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)

    assert violations == []
    # L'issue interdite, assertée explicitement.
    assert decision.reason != "F_NOT_ESTIMABLE"
    assert decision.issue in (cc.ISSUE_VALIDE, cc.ISSUE_REFUTE)
    est = decision.estimability
    assert est is not None
    assert est["E1"] is True, "E1 ne doit porter que sur la trajectoire évaluée"
    assert est["E2"] is True, "Δ* varie avec le seul rééchantillonnage de la stratégie"
    assert decision.gates == {"Q1": True, "Q2": True, "Q3": True}
    assert decision.issue == cc.ISSUE_VALIDE


def test_comparateur_cash_et_strategie_perdante_donne_refute_pas_inconclusif() -> None:
    """Même exemption d'E1, issue opposée : l'estimabilité acquise, les portes tranchent."""
    artifacts = _artifacts(
        returns_config=_varying(9),
        returns_bench=[0.0] * N_DAYS,
        net_pnl=-30.0,
    )
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)

    assert violations == []
    assert decision.issue == cc.ISSUE_REFUTE
    assert decision.reason is None
    assert decision.issue != cc.ISSUE_INCONCLUSIF


# ---------------------------------------------------------------------------
# Fixture 3 — deux trajectoires variables identiques sous rééchantillonnage apparié
# ---------------------------------------------------------------------------


def test_deux_trajectoires_variables_identiques_declenchent_E2() -> None:
    """§ A.13 E2 : `Δ*` constant **sans** qu'aucun des deux côtés soit déterministe.

    Test de **primitive** (`cc.estimability` seule) : le petit échantillon suffit à exhiber la
    distribution constante ; il **ne représente pas un artefact C3 conforme** (§ F.2 b).
    """
    same = _varying(3)
    deltas, discarded = _bootstrap(same, same, b=B_SMALL_PRIMITIVE)

    assert discarded == 0
    assert len(deltas) == B_SMALL_PRIMITIVE
    # Les CAGR bougent d'une réplication à l'autre — aucune des deux séries n'est déterministe.
    assert float(np.std(same)) > 0.0
    # Et pourtant leur différence est **exactement** nulle, sans tolérance : l'appariement des
    # indices rend les deux suites d'opérations flottantes bit-identiques.
    assert float(deltas.min()) == 0.0
    assert float(deltas.max()) == 0.0
    assert int(np.unique(deltas).size) == 1, "E2 doit se déclencher sur les flottants bruts"

    est = cc.estimability(same, deltas, discarded)
    assert est.e1 is True, "la trajectoire évaluée varie : E1 est satisfaite"
    assert est.e2 is False, "E2 doit se déclencher sur une distribution de Δ* constante"
    assert est.ok is False


def test_trajectoires_identiques_donnent_inconclusif_et_jamais_refute() -> None:
    """La conséquence sur l'issue, pas seulement sur le contrôle — à `B = BOOTSTRAP_B`."""
    same = _varying(3)
    artifacts = _artifacts(
        returns_config=same,
        returns_bench=same,
        net_pnl=0.0,
    )
    assert all(
        len(r["delta_stars"]) == cc.BOOTSTRAP_B
        for r in artifacts["evaluation"]["replications"].values()
    )
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)

    assert violations == []
    assert decision.issue == cc.ISSUE_INCONCLUSIF
    assert decision.reason == "F_NOT_ESTIMABLE"
    assert decision.issue != cc.ISSUE_REFUTE
    assert decision.estimability is not None
    assert decision.estimability["E2"] is False


# ---------------------------------------------------------------------------
# Non-règles et invariants de la chaîne
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provenance", [cc.PROVENANCE_CONTAMINATED, cc.PROVENANCE_UNKNOWN])
def test_provenance_non_clean_interdit_valide_et_refute(provenance: str) -> None:
    """§ A.5 : `unknown` n'est jamais assimilé à `clean`, et aucun des deux ne peut tuer une famille."""
    artifacts = _artifacts(
        returns_config=_varying(5),
        returns_bench=_varying(6),
        net_pnl=42.0,
        provenance=provenance,
    )
    decision = cv.decide(artifacts, violations=[])
    assert decision.issue == cc.ISSUE_INCONCLUSIF
    assert decision.reason == "P_PROVENANCE"
    assert decision.issue not in (cc.ISSUE_VALIDE, cc.ISSUE_REFUTE)


def test_la_chaine_est_identique_octet_pour_octet_sur_deux_executions() -> None:
    """§ 0.6 : deux personnes, mêmes artefacts, même chaîne. Aucun horodatage dedans."""
    artifacts = _artifacts(
        returns_config=_witness(),
        returns_bench=[0.0] * N_DAYS,
        net_pnl=42.0,
    )
    sha = cc.protocol_descriptor()["sha256"]
    kw = {
        "continuity_state": "NOT_VERIFIABLE",
        "variant_key": VARIANT_KEY,
        "observations_sha256": OBSERVATIONS_SHA,
        "synthetic": True,
    }
    first = cv.build_verdict_string("C3A", cv.decide(artifacts, violations=[]), sha, **kw)
    second = cv.build_verdict_string("C3A", cv.decide(artifacts, violations=[]), sha, **kw)
    assert first == second
    assert sha[:16] in first
    assert "generated_at" not in first


def test_le_parseur_n_expose_que_des_chemins_et_un_horodatage() -> None:
    """§ 0.6 : aucun paramètre libre, aucune entrée humaine qui déplacerait une issue."""
    actions = {a.dest for a in cv.build_parser()._actions} - {"help"}
    assert actions == {
        "entry",
        "anchor",
        "selection",
        "continuity",
        "evaluation",
        "campaign",
        "output",
        "now",
    }


def test_toutes_les_raisons_de_la_liste_close_sont_connues_du_module() -> None:
    """La liste close du § H est celle de `c3_common`, et le verdict n'en invente aucune."""
    assert set(cc.CANDIDATE_REASONS) <= set(cc.REASON_PRIORITY)
    assert set(cc.CLAUSE_REASON.values()) <= set(cc.REASON_PRIORITY)
    # Aucune table raison -> portée unique ne doit réapparaître : la portée se lit dans I.1.
    assert not hasattr(cc, "REASON_SCOPE")
    assert not hasattr(cv, "BLOCKING_RUN_REASONS")


# ---------------------------------------------------------------------------
# Entrées adverses — un module qui refuse de mauvais artefacts se teste avec de
# mauvais artefacts. Quatre verdicts faux reproduits, puis la garde généralisée.
# ---------------------------------------------------------------------------


def _sound() -> dict[str, dict[str, Any]]:
    """Le témoin sain : il doit rendre `validé`, sans quoi les contre-tests ne prouvent rien."""
    return _artifacts(
        returns_config=_witness(),
        returns_bench=[0.0] * N_DAYS,
        net_pnl=42.0,
    )


def test_le_temoin_sain_rend_bien_valide() -> None:
    assert cv.decide(_sound(), violations=[]).issue == cc.ISSUE_VALIDE


def test_provenance_supprimee_refuse_l_entree_au_lieu_de_valider() -> None:
    """Défaut reproduit : une provenance absente ne bloquait rien et rendait `validé`."""
    artifacts = _sound()
    artifacts["anchor"] = {}
    with pytest.raises(cc.MissingEvidenceError, match="universe_provenance"):
        cv.decide(artifacts, violations=[])


def test_bloc_de_continuite_vide_refuse_l_entree_au_lieu_de_valider() -> None:
    """Défaut reproduit : les contrôles ne bloquaient que sur `False` exactement."""
    artifacts = _sound()
    artifacts["continuity"] = {}
    with pytest.raises(cc.MissingEvidenceError, match="continuity"):
        cv.decide(artifacts, violations=[])


def test_bornes_infinies_refusent_l_entree_au_lieu_de_valider() -> None:
    """Défaut reproduit : `float('inf') > 0` est vrai, donc `+inf` franchissait le plancher."""
    artifacts = _sound()
    for replication in artifacts["evaluation"]["replications"].values():
        replication["bound"] = float("inf")
    with pytest.raises(cc.InvalidValueError, match="non finie"):
        cv.decide(artifacts, violations=[])


def test_estimabilite_declaree_contredite_par_les_series_est_une_violation() -> None:
    """Défaut reproduit : le statut déclaré était cru, et une inactive repartait en `réfuté`."""
    flat = [0.0] * N_DAYS
    artifacts = _artifacts(
        returns_config=flat,
        returns_bench=_varying(11),
        net_pnl=0.0,
    )
    artifacts["evaluation"]["estimability"] = {"ok": True, "E1": True, "E2": True}
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)

    assert decision.issue == cc.ISSUE_INCONCLUSIF
    assert decision.reason == "F_NOT_ESTIMABLE"
    assert decision.issue != cc.ISSUE_REFUTE
    assert violations, "un statut déclaré contredit par les séries doit être une violation"
    assert any("E1" in v for v in violations)
    assert decision.estimability is not None
    assert decision.estimability["E1"] is False, "le statut recalculé fait foi"


def test_metrique_non_finie_refuse_l_entree_au_lieu_de_refuter() -> None:
    """Toute comparaison avec un `NaN` est fausse : sans garde, il produisait un `réfuté` muet."""
    artifacts = _sound()
    artifacts["evaluation"]["metrics"]["net_pnl"] = float("nan")
    with pytest.raises(cc.InvalidValueError, match="non finie"):
        cv.decide(artifacts, violations=[])


_REFUSAL_R0 = {"scope": "run", "reason": "R0_INVALID_RUN", "assertion": "I-A.3", "detail": "borne"}
_REFUSAL_D2 = {
    "scope": "artefact",
    "reason": "D_WARMUP_PREFIX",
    "assertion": "I-A.8",
    "detail": "D2 sur tous",
}


# ---------------------------------------------------------------------------
# Le contrat de `entry.json` : `ok` <=> `refusal` null — combinaisons incohérentes selon ce contrat
# ---------------------------------------------------------------------------


def test_entry_refusee_D_WARMUP_PREFIX_porte_sa_raison_et_sort_2(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["entry"].update({"ok": False, "exit_code": 2, "refusal": _REFUSAL_D2})
    with pytest.raises(cc.EntryRefusedError) as info:
        cv.decide(artifacts, violations=[])
    assert info.value.reason == "D_WARMUP_PREFIX"
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_entry_ok_avec_un_refus_porte_est_une_violation(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["entry"].update({"ok": True, "refusal": _REFUSAL_D2})
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert decision.issue == cc.ISSUE_VALIDE, (
        "le calcul continue, mais il sera invalidé à la sortie"
    )
    assert any("incohérent" in v for v in violations)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["verdict"] is None


def test_entry_non_ok_sans_refus_est_une_violation_pas_un_refus_propre(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["entry"].update({"ok": False, "refusal": None})
    violations: list[str] = []
    with pytest.raises(cc.EntryRefusedError):
        cv.decide(artifacts, violations=violations)
    assert violations, "l'incohérence est consignée avant le refus"
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1, "la violation prime sur le refus"
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["verdict"] is None
    assert any("refus d'entrée constaté après violation" in v for v in payload["violations"])


@pytest.mark.parametrize(
    "refusal",
    [
        {"scope": "run", "reason": "A_BELOW_FLOOR", "assertion": "x", "detail": "y"},
        {"scope": "candidat", "reason": "R0_INVALID_RUN", "assertion": "x", "detail": "y"},
        {"reason": "R0_INVALID_RUN"},
        "refusé",
    ],
    ids=["raison hors lignes 2/5", "portée hors liste", "bloc incomplet", "mal typé"],
)
def test_un_refus_mal_forme_est_une_erreur_d_entree(tmp_path: Path, refusal: Any) -> None:
    artifacts = _sound()
    artifacts["entry"].update({"ok": False, "refusal": refusal})
    with pytest.raises(cc.MissingEvidenceError):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2


def test_refusal_absent_est_une_erreur_d_entree_null_est_la_valeur_conforme() -> None:
    artifacts = _sound()
    artifacts["entry"].pop("refusal")
    with pytest.raises(cc.MissingEvidenceError, match="jamais absente"):
        cv.decide(artifacts, violations=[])
    artifacts["entry"]["refusal"] = None
    assert cv.decide(artifacts, violations=[]).issue == cc.ISSUE_VALIDE


# ---------------------------------------------------------------------------
# Le statut de sélection : dérivé de (provenance, retenu) et recoupé — jamais recopié
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provenance", "declared"),
    [
        (cc.PROVENANCE_CLEAN, "SÉLECTION_DESCRIPTIVE"),
        (cc.PROVENANCE_CONTAMINATED, "SÉLECTION_VALIDE"),
        (cc.PROVENANCE_UNKNOWN, "SÉLECTION_VALIDE"),
        (cc.PROVENANCE_CLEAN, "ABSTENTION"),
    ],
    ids=[
        "clean déclaré descriptif",
        "contaminated déclaré valide",
        "unknown déclaré valide",
        "retenu déclaré abstention",
    ],
)
def test_statut_de_selection_declare_contredit_par_la_derivation_est_une_violation(
    tmp_path: Path, provenance: str, declared: str
) -> None:
    artifacts = _artifacts(
        returns_config=_witness(),
        returns_bench=[0.0] * N_DAYS,
        net_pnl=42.0,
        provenance=provenance,
    )
    artifacts["selection"]["status"] = declared
    if declared == "ABSTENTION":
        artifacts["selection"]["reason"] = "A_BELOW_FLOOR"
    violations: list[str] = []
    cv.decide(artifacts, violations=violations)
    assert any("selection.status déclaré" in v for v in violations)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["verdict"] is None


def test_abstention_sans_retenu_declaree_valide_est_une_violation() -> None:
    artifacts = _sound()
    _abstention("A_NO_ADMISSIBLE_CANDIDATE")(artifacts)
    artifacts["selection"]["status"] = "SÉLECTION_VALIDE"
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert decision.issue == cc.ISSUE_INCONCLUSIF and decision.reason == "A_NO_ADMISSIBLE_CANDIDATE"
    assert any("dérivé 'ABSTENTION'" in v for v in violations)


def test_provenance_de_la_selection_differente_de_l_ancrage_est_une_violation() -> None:
    artifacts = _sound()
    artifacts["selection"]["provenance"] = cc.PROVENANCE_UNKNOWN
    violations: list[str] = []
    cv.decide(artifacts, violations=violations)
    assert any("selection.provenance" in v for v in violations)


def test_retained_absent_est_une_erreur_d_entree_null_est_l_abstention() -> None:
    artifacts = _sound()
    artifacts["selection"].pop("retained")
    with pytest.raises(cc.MissingEvidenceError, match="jamais absente"):
        cv.decide(artifacts, violations=[])


#: Chemin d'une preuve obligatoire, décrit comme une suite de clés.
MANDATORY: tuple[tuple[str, ...], ...] = (
    ("entry", "ok"),
    ("anchor", "universe_provenance"),
    ("selection", "status"),
    ("selection", "provenance"),
    ("selection", "retained", "identity"),
    ("continuity", "warmup_anchor_ok"),
    ("continuity", "benchmark_comparable"),
    ("continuity", "stamp_same_daily_cell"),
    ("continuity", "state"),
    ("continuity", "clauses"),
    ("continuity", "clauses", "c3", "state"),
    ("continuity", "identity"),
    ("evaluation", "synthetic"),
    ("evaluation", "returns_config"),
    ("evaluation", "B"),
    ("evaluation", "replications"),
    ("evaluation", "replications", "21:dd"),
    ("evaluation", "replications", "21:dd", "delta_stars"),
    ("evaluation", "replications", "21:dd", "discarded"),
    ("evaluation", "metrics"),
    ("evaluation", "metrics", "net_pnl"),
    ("evaluation", "metrics", "cagr_pct"),
    ("evaluation", "metrics", "delta_dd"),
)


def _mutate(artifacts: dict[str, Any], path: tuple[str, ...], mode: str) -> dict[str, Any]:
    node: Any = artifacts
    for key in path[:-1]:
        node = node[key]
    if mode == "absente":
        node.pop(path[-1])
    else:
        node[path[-1]] = None
    return artifacts


@pytest.mark.parametrize("path", MANDATORY, ids=[".".join(p) for p in MANDATORY])
@pytest.mark.parametrize("mode", ["absente", "nulle"])
def test_chaque_preuve_obligatoire_absente_ou_nulle_refuse_l_entree(
    path: tuple[str, ...], mode: str
) -> None:
    """Doctrine des contrôles de présence : la clé absente **et** la valeur `null`, pour chacune."""
    artifacts = _mutate(_sound(), path, mode)
    with pytest.raises(cc.MissingEvidenceError):
        cv.decide(artifacts, violations=[])


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("entry", "ok"), 1),
        (("continuity", "warmup_anchor_ok"), 1),
        (("anchor", "universe_provenance"), "propre"),
        (("selection", "status"), "OK"),
        (("evaluation", "metrics", "net_pnl"), "42"),
        (("evaluation", "returns_config"), 0.01),
        (("evaluation", "replications", "21:dd", "delta_stars"), {"a": 1}),
    ],
    ids=[
        "entry.ok=int",
        "continuity=int",
        "provenance hors liste",
        "statut hors liste",
        "metrique=str",
        "serie=scalaire",
        "serie=mapping",
    ],
)
def test_chaque_preuve_obligatoire_mal_typee_refuse_l_entree(
    path: tuple[str, ...], value: Any
) -> None:
    """Un entier n'est pas un booléen, et une valeur hors liste close n'est pas une valeur."""
    artifacts = _sound()
    node: Any = artifacts
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(cc.MissingEvidenceError):
        cv.decide(artifacts, violations=[])


def test_serie_contenant_un_non_fini_refuse_l_entree() -> None:
    artifacts = _sound()
    artifacts["evaluation"]["replications"]["21:dd"]["delta_stars"][3] = float("nan")
    with pytest.raises(cc.InvalidValueError, match=r"delta_stars\[3\]"):
        cv.decide(artifacts, violations=[])


def test_une_combinaison_manquante_est_un_contrat_rompu() -> None:
    """§ F.2 (b) v2.1 (AM-14) : « une combinaison manquante ou surnuméraire est un contrat rompu —
    `R0_INVALID_RUN`, code 2 » ; le contrôle se fait avant toute lecture des séries."""
    artifacts = _sound()
    artifacts["evaluation"]["replications"].pop("10:dd")
    with pytest.raises(cc.EntryRefusedError, match="combinaisons") as info:
        cv.decide(artifacts, violations=[])
    assert info.value.reason == "R0_INVALID_RUN"


# ---------------------------------------------------------------------------
# Les mêmes cas par la CLI : code de sortie conforme au § I.1, aucun artefact écrit
# ---------------------------------------------------------------------------


def _write_cli_inputs(tmp_path: Path, artifacts: Mapping[str, Any]) -> list[str]:
    """Écrit les cinq artefacts dans l'ordre de la chaîne, en posant des empreintes cohérentes
    (manifeste et observations fictifs mais identiques partout ; anchor, entry et evaluation réels)."""
    paths = {
        name: tmp_path / f"{name}.json"
        for name in ("entry", "anchor", "selection", "continuity", "evaluation")
    }

    def stamp(name: str, inputs: dict[str, str]) -> None:
        art = artifacts[name]
        if (
            isinstance(art, dict)
            and isinstance(art.get("inputs_sha256"), dict)
            and not art["inputs_sha256"]
        ):
            art["inputs_sha256"] = inputs

    stamp("anchor", {"manifest": MANIFEST_SHA})
    cc.write_json(paths["anchor"], artifacts["anchor"])
    anchor_sha = cc.file_sha256(paths["anchor"])
    stamp(
        "entry", {"manifest": MANIFEST_SHA, "anchor": anchor_sha, "observations": OBSERVATIONS_SHA}
    )
    cc.write_json(paths["entry"], artifacts["entry"])
    entry_sha = cc.file_sha256(paths["entry"])
    stamp(
        "selection",
        {
            "manifest": MANIFEST_SHA,
            "anchor": anchor_sha,
            "entry": entry_sha,
            "observations": OBSERVATIONS_SHA,
        },
    )
    cc.write_json(paths["selection"], artifacts["selection"])
    cc.write_json(paths["evaluation"], artifacts["evaluation"])
    stamp(
        "continuity",
        {
            "manifest": MANIFEST_SHA,
            "anchor": anchor_sha,
            "evaluation": cc.file_sha256(paths["evaluation"]),
        },
    )
    cc.write_json(paths["continuity"], artifacts["continuity"])
    argv: list[str] = []
    for name in ("entry", "anchor", "selection", "continuity", "evaluation"):
        argv += [f"--{name}", str(paths[name])]
    argv += ["--output", str(tmp_path / "verdict.json"), "--now", "2026-09-21T00:00:00+00:00"]
    return argv


def test_cli_temoin_sain_sort_0_et_ecrit_la_chaine(tmp_path: Path) -> None:
    argv = _write_cli_inputs(tmp_path, _sound())
    assert cv.main(argv) == 0
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["verdict"] == cc.ISSUE_VALIDE
    assert payload["verdict_string"].startswith("C3_SYNTH_C3A | verdict=validé")


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda a: a.__setitem__("anchor", {}), id="provenance supprimée"),
        pytest.param(lambda a: a.__setitem__("continuity", {}), id="continuité vide"),
        pytest.param(
            lambda a: a["evaluation"]["replications"]["21:dd"].pop("discarded"),
            id="discarded absent",
        ),
        pytest.param(
            lambda a: a["evaluation"].__setitem__("estimability", {"E1": "false"}),
            id="déclaration en chaîne 'false'",
        ),
    ],
)
def test_cli_refuse_l_entree_avec_exit_2_et_n_ecrit_rien(tmp_path: Path, mutate: Any) -> None:
    """§ I.1 : preuve absente, nulle ou mal typée → code 2, la chaîne s'arrête, rien n'est écrit."""
    artifacts = _sound()
    mutate(artifacts)
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 2
    assert not (tmp_path / "verdict.json").exists(), "aucun artefact ne doit être écrit"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda a: [
                r.__setitem__("bound", float("inf"))
                for r in a["evaluation"]["replications"].values()
            ],
            id="bornes infinies",
        ),
        pytest.param(
            lambda a: a["evaluation"]["metrics"].__setitem__("net_pnl", float("nan")),
            id="métrique NaN",
        ),
        pytest.param(
            lambda a: a["evaluation"]["returns_config"].__setitem__(5, -1.0),
            id="rendement exactement -1",
        ),
        pytest.param(
            lambda a: a["evaluation"]["replications"]["21:dd"].__setitem__("discarded", 11),
            id="B incohérent",
        ),
    ],
)
def test_cli_violation_sort_1_avec_un_diagnostic_sans_verdict(tmp_path: Path, mutate: Any) -> None:
    """§ F.7 → § I.1 ligne 15 : non-finitude, domaine ou compte incohérent = violation, code 1.

    Un artefact **diagnostic** est écrit — explicitement invalide, porteur des violations — mais il ne
    contient **ni verdict, ni raison, ni chaîne citable**.
    """
    artifacts = _sound()
    mutate(artifacts)
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True
    assert payload["violations"], (
        "les violations doivent être dans l'artefact, pas seulement sur stderr"
    )
    assert payload["verdict"] is None
    assert payload["raison"] is None
    assert payload["verdict_string"] is None


def test_cli_estimabilite_contredite_sort_1_sans_publier_de_verdict(tmp_path: Path) -> None:
    """Défaut reproduit : exit 1 mais `verdict=validé` et une chaîne citable étaient écrits.

    Une violation doit **empêcher la publication** du verdict normal. L'artefact diagnostic garde ce
    que le calcul avait produit, mais sous une clé qui dit qu'il a été invalidé.
    """
    artifacts = _sound()  # réellement estimable
    artifacts["evaluation"]["estimability"] = {"E1": False, "E2": False, "ok": False}
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True
    assert payload["verdict"] is None
    assert payload["verdict_string"] is None
    assert any("E1" in v for v in payload["violations"])
    assert payload["diagnostic"]["issue_calculee_puis_invalidee"] == cc.ISSUE_VALIDE


# ---------------------------------------------------------------------------
# Item 1 — la contradiction déclaré / recalculé, dans les deux sens
# ---------------------------------------------------------------------------


def test_contradiction_declare_estimable_recalcule_non_estimable_est_une_violation() -> None:
    flat = [0.0] * N_DAYS
    artifacts = _artifacts(
        returns_config=flat,
        returns_bench=_varying(11),
        net_pnl=0.0,
    )
    artifacts["evaluation"]["estimability"] = {"ok": True, "E1": True}
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert decision.reason == "F_NOT_ESTIMABLE", "le recalcul fait foi"
    assert len(violations) == 2 and all("recalculée" in v for v in violations)


def test_contradiction_declare_non_estimable_recalcule_estimable_est_une_violation() -> None:
    artifacts = _sound()
    artifacts["evaluation"]["estimability"] = {"ok": False, "E1": False, "E2": False}
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert decision.issue == cc.ISSUE_VALIDE, (
        "le calcul continue, mais il sera invalidé à la sortie"
    )
    assert len(violations) == 3


def test_declaration_coherente_ne_produit_aucune_violation() -> None:
    artifacts = _sound()
    artifacts["evaluation"]["estimability"] = {"ok": True, "E1": True, "E2": True}
    violations: list[str] = []
    cv.decide(artifacts, violations=violations)
    assert violations == []


# ---------------------------------------------------------------------------
# Item 2 — contournements de l'accesseur strict, reproduits
# ---------------------------------------------------------------------------


def test_discarded_absent_est_une_erreur_d_entree_et_non_zero() -> None:
    """Défaut reproduit : `discarded` absent valait 0, donc `validé` là où 11 donnait `inconclusif`."""
    artifacts = _sound()
    artifacts["evaluation"]["replications"]["21:dd"].pop("discarded")
    with pytest.raises(cc.MissingEvidenceError, match="discarded"):
        cv.decide(artifacts, violations=[])


def test_discarded_incoherent_avec_B_est_une_violation() -> None:
    """`B` déclaré, `B_effectif` recalculé : un désaccord est une violation (§ I.1, ligne 15)."""
    artifacts = _sound()
    # B_effectif 10 000 + 11 != B 10 000, sur une combinaison
    artifacts["evaluation"]["replications"]["21:dd"]["discarded"] = 11
    violations: list[str] = []
    cv.decide(artifacts, violations=violations)
    assert any("B déclaré" in v for v in violations)


def test_B_absent_est_une_erreur_d_entree() -> None:
    artifacts = _sound()
    artifacts["evaluation"].pop("B")
    with pytest.raises(cc.MissingEvidenceError, match=r"evaluation\.B"):
        cv.decide(artifacts, violations=[])


@pytest.mark.parametrize("value", ["false", "true", 0, 1, "", None])
def test_declaration_presente_mal_typee_est_une_erreur_de_type(value: Any) -> None:
    """Défaut reproduit : `bool("false")` valait `True`. Un booléen est un booléen."""
    artifacts = _sound()
    artifacts["evaluation"]["estimability"] = {"E1": value}
    with pytest.raises(cc.MissingEvidenceError):
        cv.decide(artifacts, violations=[])


def test_rendement_exactement_moins_un_est_hors_domaine() -> None:
    """Défaut reproduit : `-1.0` est fini, donc passait ; `log1p(-1)` est pourtant indéfini."""
    artifacts = _sound()
    artifacts["evaluation"]["returns_config"][5] = -1.0
    with pytest.raises(cc.InvalidValueError, match="hors domaine"):
        cv.decide(artifacts, violations=[])


def test_rendement_juste_au_dessus_de_moins_un_est_accepte() -> None:
    artifacts = _sound()
    artifacts["evaluation"]["returns_config"][5] = -0.999999
    cv.decide(artifacts, violations=[])  # ne lève pas


# ---------------------------------------------------------------------------
# Chantier 0 (a) — les deux contrôles sur `B` : le contrat (§ F.2 b, R0) **avant** la cohérence
# des compteurs (§ I.1 l.15). Matrice complète, en appel direct et par la CLI.
# ---------------------------------------------------------------------------


def _with_replications(
    a: dict[str, Any], *, b: int, n_deltas: int, discarded: int, nan_in_deltas: bool = False
) -> None:
    """Déclare `B`, garde `n_deltas` réplications de la suite générée, déclare `discarded`.

    Tronquer la suite est la forme documentée d'un échec numérique (§ F.2 e) : les réplications
    écartées ne sont pas remplacées, elles sont comptées. `nan_in_deltas` glisse un non-fini dans la
    suite : seul, il vaut une violation (code 1) ; **avec un `B` hors contrat, c'est R0 qui prime**.
    """
    a["evaluation"]["B"] = b
    for replication in a["evaluation"]["replications"].values():
        replication["delta_stars"] = replication["delta_stars"][:n_deltas]
        replication["discarded"] = discarded
    if nan_in_deltas:
        a["evaluation"]["replications"]["21:dd"]["delta_stars"][3] = float("nan")


#: (B, len(delta_stars), discarded, non-fini dans delta_stars, code CLI, issue, raison). Les comptes
#: cohérents (9 990 / 10 → estimable, 9 989 / 11 → `F_NOT_ESTIMABLE`) se testent au niveau fonction
#: (`test_c3_common`, plafond par combinaison) : une suite tronquée à la main n'est pas celle qu'un
#: producteur conforme tire de ses séries (§ F.2 v2.1), et le rejeu de la chaîne la contredirait.
MATRIX_B = [
    pytest.param(
        10_000, 10_000, 11, False, 1, None, None, id="10000/10000/11 -> 1 compte contradictoire"
    ),
    pytest.param(
        400,
        395,
        5,
        False,
        2,
        None,
        "R0_INVALID_RUN",
        id="400/395/5 -> 2 cohérent mais hors contrat",
    ),
    pytest.param(
        400,
        400,
        5,
        False,
        2,
        None,
        "R0_INVALID_RUN",
        id="400/400/5 -> 2 R0 évalué avant la cohérence",
    ),
    pytest.param(
        400,
        400,
        5,
        True,
        2,
        None,
        "R0_INVALID_RUN",
        id="400 + NaN dans delta_stars -> 2 R0 évalué avant tout parsing",
    ),
]


@pytest.mark.parametrize(
    ("b", "n_deltas", "discarded", "nan_in_deltas", "code", "issue", "reason"), MATRIX_B
)
def test_matrice_B_en_appel_direct(
    b: int, n_deltas: int, discarded: int, nan_in_deltas: bool, code: int, issue: Any, reason: Any
) -> None:
    artifacts = _sound()
    _with_replications(
        artifacts, b=b, n_deltas=n_deltas, discarded=discarded, nan_in_deltas=nan_in_deltas
    )
    assert all(
        len(r["delta_stars"]) == n_deltas for r in artifacts["evaluation"]["replications"].values()
    )
    violations: list[str] = []
    if code == 2:
        # `EntryRefusedError`, et pas `InvalidValueError` : le contrat est lu avant les séries.
        with pytest.raises(cc.EntryRefusedError) as info:
            cv.decide(artifacts, violations=violations)
        assert info.value.reason == reason
        assert "F.2" in str(info.value)
        # L'issue interdite : un `B` hors contrat n'est ni un verdict, ni une violation.
        assert violations == [], (
            "R0 est évalué avant la cohérence : aucune violation n'est produite"
        )
        return
    assert code == 1 and issue is None
    cv.decide(artifacts, violations=violations)
    assert violations and any("B déclaré" in v for v in violations)


@pytest.mark.parametrize(
    ("b", "n_deltas", "discarded", "nan_in_deltas", "code", "issue", "reason"), MATRIX_B
)
def test_matrice_B_par_la_cli(
    tmp_path: Path,
    b: int,
    n_deltas: int,
    discarded: int,
    nan_in_deltas: bool,
    code: int,
    issue: Any,
    reason: Any,
) -> None:
    artifacts = _sound()
    _with_replications(
        artifacts, b=b, n_deltas=n_deltas, discarded=discarded, nan_in_deltas=nan_in_deltas
    )
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == code
    out = tmp_path / "verdict.json"
    if code == 2:
        assert not out.exists(), "code 2 : rien n'est écrit"
        return
    assert code == 1 and issue is None
    payload = cc.read_json(out)
    assert payload["invalide"] is True
    assert payload["verdict"] is None
    assert payload["verdict_string"] is None
    assert any("B déclaré" in v for v in payload["violations"])


# ---------------------------------------------------------------------------
# § A.13 E2 v2.1 (AM-09), § F.2 (b) v2.1 (AM-14), § F.2 (e) v2.1 (AM-16) — les six distributions
# ---------------------------------------------------------------------------


def test_six_distributions_variables_satisfont_E2() -> None:
    """§ A.13 v2.1, E2 : « Chacune des six distributions rééchantillonnées de Δ* […] porte au moins deux
    valeurs distinctes » — le témoin sain le satisfait sur les six."""
    decision = cv.decide(_sound(), violations=[])
    est = decision.estimability
    assert est is not None and est["E2"] is True
    assert sorted(est["combinations"]) == sorted(cc.COMBINATIONS)
    assert all(
        c["E2"] is True and c["within_ceiling"] is True for c in est["combinations"].values()
    )


def test_des_distributions_constantes_sur_un_appariement_font_echouer_E2() -> None:
    """§ A.13 v2.1, E2 : « Une seule distribution constante suffit à faire échouer E2 » (au niveau fonction :
    `test_c3_common`). Ici, par les séries : le comparateur de l'appariement σ est la configuration elle-même,
    ses trois distributions sont constantes — sous rééchantillonnage apparié, la différence vaut toujours zéro
    (§ A.13) — et l'issue est `inconclusif (F_NOT_ESTIMABLE)` (§ H.0), jamais `validé`, alors que les trois
    distributions dd varient et que les portes Q passent."""
    artifacts = _sound()
    _reseries(artifacts, _witness(), {"dd": [0.0] * N_DAYS, "sigma": _witness()})
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert violations == []
    assert decision.issue == cc.ISSUE_INCONCLUSIF and decision.reason == "F_NOT_ESTIMABLE"
    assert decision.issue != cc.ISSUE_VALIDE
    est = decision.estimability
    assert est is not None and est["E2"] is False
    assert {k for k, v in est["combinations"].items() if not v["E2"]} == {
        "10:sigma",
        "21:sigma",
        "42:sigma",
    }


def test_au_dela_du_plafond_de_replications_ecartees_l_inference_est_inutilisable() -> None:
    """§ F.2 (e) v2.1 : au-delà de 10 réplications écartées sur l'une quelconque des six combinaisons,
    `inconclusif (F_NOT_ESTIMABLE)` ; `B_effectif` est publié par combinaison. Par les séries : un jour de
    rendement extrême (`log1p(r) = 300`) laisse la trajectoire observée finie, mais toute réplication qui le
    tire trois fois déborde — échec numérique, réplication écartée et comptée (§ F.2 e), sur les six
    combinaisons (le plafond au niveau fonction, une combinaison seule : `test_c3_common`)."""
    artifacts = _sound()
    extreme = _witness()
    extreme[100] = math.expm1(300.0)
    _reseries(artifacts, extreme, [0.0] * N_DAYS)
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert violations == []
    assert decision.issue == cc.ISSUE_INCONCLUSIF and decision.reason == "F_NOT_ESTIMABLE"
    est = decision.estimability
    assert est is not None and est["within_ceiling"] is False
    for v in est["combinations"].values():
        assert v["discarded"] > cc.DISCARDED_MAX and v["within_ceiling"] is False
        assert v["B_effectif"] == cc.BOOTSTRAP_B - v["discarded"]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: r.pop("42:dd"), id="cinq combinaisons"),
        pytest.param(lambda r: r.__setitem__("15:dd", dict(r["21:dd"])), id="clé étrangère"),
        pytest.param(
            lambda r: r.__setitem__("21:max", r.pop("21:sigma")), id="appariement inconnu"
        ),
    ],
)
def test_un_ensemble_de_combinaisons_hors_contrat_est_un_refus_R0(
    tmp_path: Path, mutate: Any
) -> None:
    """§ F.2 (b) v2.1 : « une combinaison manquante ou surnuméraire est un contrat rompu — R0_INVALID_RUN,
    code 2, rien n'est publié (§ I.1, ligne 2) »."""
    artifacts = _sound()
    mutate(artifacts["evaluation"]["replications"])
    with pytest.raises(cc.EntryRefusedError) as info:
        cv.decide(artifacts, violations=[])
    assert info.value.reason == "R0_INVALID_RUN"
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_le_contrat_d_instrument_vient_avant_toute_lecture(tmp_path: Path) -> None:
    """§ F.2 (b) v2.1 et § I.1 v2.1 : le refus de contrat est « fait avant toute lecture des séries » et
    « vient en premier par construction » — un `B` hors contrat accompagné d'une contradiction de continuité
    sort en refus R0, code 2, rien publié ; jamais en diagnostic par accident d'ordre de lecture."""
    artifacts = _sound()
    artifacts["continuity"]["warmup_anchor_ok"] = (
        False  # contredit c4 VERIFIED : une violation, seule
    )
    artifacts["evaluation"]["B"] = 400
    violations: list[str] = []
    with pytest.raises(cc.EntryRefusedError) as info:
        cv.decide(artifacts, violations=violations)
    assert info.value.reason == "R0_INVALID_RUN" and "F.2" in str(info.value)
    assert violations == [], "le contrat est évalué avant la lecture de la continuité"
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda r: r["21:dd"].__setitem__("bound", None), id="borne nulle, suite non vide"
        ),
        pytest.param(
            lambda r: r["21:dd"].update(
                {"delta_stars": [], "discarded": cc.BOOTSTRAP_B, "bound": 1.0}
            ),
            id="borne déclarée, suite vide",
        ),
    ],
)
def test_une_borne_est_nulle_si_et_seulement_si_sa_suite_est_vide(mutate: Any) -> None:
    """§ F.2 (e) v2.1 : une combinaison sans réplication retenue ne porte pas de borne — la borne est nulle si
    et seulement si la suite retenue est vide ; l'écart, dans un sens ou dans l'autre, contredit l'artefact
    (§ I.1, ligne 15)."""
    artifacts = _sound()
    mutate(artifacts["evaluation"]["replications"])
    violations: list[str] = []
    cv.decide(artifacts, violations=violations)
    assert any("21:dd" in v and "borne" in v for v in violations)


def test_une_borne_absente_est_une_erreur_d_entree() -> None:
    """§ I.1 v2.1, ligne 2 : une clé absente est une erreur de forme — la borne est nullable, jamais absente."""
    artifacts = _sound()
    artifacts["evaluation"]["replications"]["21:dd"].pop("bound")
    with pytest.raises(cc.MissingEvidenceError, match="bound"):
        cv.decide(artifacts, violations=[])


# ---------------------------------------------------------------------------
# Item 3 — la table I.1, ligne à ligne. C'est ce test qui empêchera la prochaine divergence.
# ---------------------------------------------------------------------------


def _abstention(reason: str) -> Any:
    def mutate(a: dict[str, Any]) -> None:
        identity = a["selection"]["retained"]["identity"]
        a["selection"].update(
            {
                "status": "ABSTENTION",
                "reason": reason,
                "provenance": a["anchor"]["universe_provenance"],
                "retained": None,
                # listes cohérentes avec la raison (revue Fin 6 : la raison en dérive)
                "admissible": [] if reason == "A_NO_ADMISSIBLE_CANDIDATE" else [identity],
                "survivors": [],
                "ranking": [],
            }
        )

    return mutate


def _flat(a: dict[str, Any]) -> None:
    """Une configuration restée plate après l'ancrage, contre du cash : E1 échoue (aucun jour à rendement
    non nul, § A.13), et `Δ*` est constamment nul (E2) — l'artefact reste cohérent avec ses séries."""
    _reseries(a, [0.0] * N_DAYS, [0.0] * N_DAYS, net_pnl=0.0)


def _cannot_separate(a: dict[str, Any]) -> None:
    """Un effet positif que la borne ne sépare pas de zéro : N(0,0005 ; 0,02), graine 51, contre du cash —
    mesuré par la procédure § F.2 : CAGR ≈ 3,8 %/an (Q2), Δ̂_dd > 0 (Q3), six bornes ≈ −110 points."""
    _reseries(a, _varying(51), [0.0] * N_DAYS)


#: (ligne, fixture, issue attendue, raison attendue, code CLI attendu, artefact écrit ?, chaîne citable ?)
TABLE_I1 = [
    pytest.param(1, lambda a: None, cc.ISSUE_VALIDE, None, 0, True, True, id="L1 entrée conforme"),
    pytest.param(
        2,
        lambda a: a["entry"].update({"ok": False, "exit_code": 2, "refusal": _REFUSAL_R0}),
        None,
        "R0_INVALID_RUN",
        2,
        False,
        False,
        id="L2 contrat rompu R0",
    ),
    pytest.param(
        7,
        lambda a: (
            a["anchor"].__setitem__("universe_provenance", "contaminated"),
            a["selection"].__setitem__("provenance", "contaminated"),
            a["selection"].__setitem__("status", "SÉLECTION_DESCRIPTIVE"),
        ),
        cc.ISSUE_INCONCLUSIF,
        "P_PROVENANCE",
        0,
        True,
        True,
        id="L7 provenance",
    ),
    pytest.param(
        8,
        _abstention("A_NO_ADMISSIBLE_CANDIDATE"),
        cc.ISSUE_INCONCLUSIF,
        "A_NO_ADMISSIBLE_CANDIDATE",
        0,
        True,
        True,
        id="L8 ensemble vide",
    ),
    pytest.param(
        9,
        _abstention("A_BELOW_FLOOR"),
        cc.ISSUE_INCONCLUSIF,
        "A_BELOW_FLOOR",
        0,
        True,
        True,
        id="L9 aucun survivant",
    ),
    pytest.param(
        10,
        lambda a: (
            a["continuity"]["comparator"].__setitem__("state", "FAILED"),
            a["continuity"]["comparator"]["tests"].__setitem__("ff_ok", False),
            a["continuity"].__setitem__("benchmark_comparable", False),
        ),
        cc.ISSUE_INCONCLUSIF,
        "E_NO_BENCHMARK",
        0,
        True,
        True,
        id="L10 benchmark",
    ),
    pytest.param(
        11,
        lambda a: (
            a["continuity"]["stamp_cell"].__setitem__("state", "FAILED"),
            a["continuity"].__setitem__("stamp_same_daily_cell", False),
        ),
        cc.ISSUE_INCONCLUSIF,
        "E_STAMP_MISMATCH",
        0,
        True,
        True,
        id="L11 estampille",
    ),
    pytest.param(
        12,
        lambda a: (
            a["continuity"]["clauses"]["c4"].__setitem__("state", "FAILED"),
            a["continuity"].__setitem__("state", "FAILED"),
            a["continuity"].__setitem__("warmup_anchor_ok", False),
        ),
        cc.ISSUE_INCONCLUSIF,
        "D_WARMUP_ANCHOR",
        0,
        True,
        True,
        id="L12 warmup ancrage",
    ),
    pytest.param(
        13,
        _flat,
        cc.ISSUE_INCONCLUSIF,
        "F_NOT_ESTIMABLE",
        0,
        True,
        True,
        id="L13 estimabilité (configuration plate : E1, et E2)",
    ),
    pytest.param(
        14,
        _cannot_separate,
        cc.ISSUE_INCONCLUSIF,
        "F_CANNOT_SEPARATE",
        0,
        True,
        True,
        id="L14 borne",
    ),
    pytest.param(
        15,
        lambda a: a["evaluation"].__setitem__("estimability", {"ok": False}),
        None,
        None,
        1,
        True,
        False,
        id="L15 violation : déclaré ≠ recalculé",
    ),
    pytest.param(
        15,
        lambda a: a["evaluation"]["metrics"].__setitem__("cagr_pct", float("inf")),
        None,
        None,
        1,
        True,
        False,
        id="L15 violation : non-finitude",
    ),
]


@pytest.mark.parametrize(
    ("line", "mutate", "issue", "reason", "code", "written", "citable"), TABLE_I1
)
def test_table_I1_ligne_a_ligne(
    tmp_path: Path,
    line: int,
    mutate: Any,
    issue: Any,
    reason: Any,
    code: int,
    written: bool,
    citable: bool,
) -> None:
    """Chaque ligne de la table du § I.1 exerçable par `c3_verdict`, en appel direct ET par la CLI."""
    artifacts = _sound()
    mutate(artifacts)

    # Appel direct.
    violations: list[str] = []
    if line == 2:
        with pytest.raises(cc.EntryRefusedError) as info:
            cv.decide(artifacts, violations=violations)
        assert info.value.reason == "R0_INVALID_RUN"
    elif line == 15 and issue is None and reason is None:
        try:
            cv.decide(artifacts, violations=violations)
        except cc.InvalidValueError as exc:
            violations.append(str(exc))
        assert violations, "la ligne 15 est une violation"
    else:
        decision = cv.decide(artifacts, violations=violations)
        assert violations == []
        assert decision.issue == issue
        assert decision.reason == reason

    # CLI : code de sortie, artefact, chaîne.
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == code
    out = tmp_path / "verdict.json"
    assert out.exists() is written
    if written:
        payload = cc.read_json(out)
        assert (payload["verdict_string"] is not None) is citable
        assert payload["invalide"] is (not citable)


def test_les_raisons_de_portee_candidat_sont_enumerees_sans_portee_exclusive() -> None:
    """Lignes 3 à 6 d'I.1 : leurs raisons sont énumérées — **pas** une table raison → portée.

    `F_NOT_ESTIMABLE` y figure (ligne 6, D4) **et** est de portée run (ligne 13) : c'est la seule
    de l'énumération que `decide()` émet, et il l'émet en portée run. Les lignes 3 à 6 elles-mêmes
    s'exercent dans `c3_select` / `c3_entry`, pas ici ; elles sont énumérées pour que nul ne les
    croie couvertes.
    """
    assert set(cc.CANDIDATE_REASONS) == {
        "D_WARMUP_PREFIX",
        "R1_NOT_NORMALISED",
        "D_NOT_ADMISSIBLE",
        "C_COVERAGE",
        "F_NOT_ESTIMABLE",
    }
    # L'union des raisons des lignes 3 à 6 (clauses D1, D2, D3, D4, D6) est exactement cette liste.
    lines_3_to_6 = {cc.CLAUSE_REASON[c] for c in ("D1", "D2", "D3", "D4", "D6")}
    assert lines_3_to_6 == set(cc.CANDIDATE_REASONS)
    # Ce que `decide()` émet (table I.1 paramétrée) n'en recoupe que `F_NOT_ESTIMABLE`, en portée run.
    emitted = {row.values[3] for row in TABLE_I1 if row.values[3] is not None}
    assert emitted & set(cc.CANDIDATE_REASONS) == {"F_NOT_ESTIMABLE"}


# ---------------------------------------------------------------------------
# Revue R3 (d) — un non-fini qui atteint la canonicalisation est une violation, jamais un traceback
# ---------------------------------------------------------------------------


def test_revue_R3_non_fini_a_la_canonicalisation_est_une_violation_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`NonFiniteValueError` n'est pas une `InvalidValueError` : le verdict doit la router en violation."""

    def raise_non_finite(*args: Any, **kwargs: Any) -> Any:
        raise cc.NonFiniteValueError("non-finite value in the signature payload: nan")

    monkeypatch.setattr(cv, "decide", raise_non_finite)
    argv = _write_cli_inputs(tmp_path, _sound())
    assert cv.main(argv) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["verdict"] is None
    assert any("non-finite" in v for v in payload["violations"])


# ---------------------------------------------------------------------------
# § L.2 — la chaîne à neuf champs : présence et correspondance aux entrées, sous les deux labels
# ---------------------------------------------------------------------------

NINE_FIELDS = (
    "verdict",
    "raison",
    "selection",
    "statut_selection",
    "continuite",
    "variante",
    "provenance",
    "protocole",
    "observations",
)


def _fields(chain: str) -> tuple[str, dict[str, str]]:
    parts = chain.split(" | ")
    fields = dict(part.split("=", 1) for part in parts[1:])
    return parts[0], fields


@pytest.mark.parametrize(
    ("synthetic", "label"), [(False, "C3_C3A"), (True, "C3_SYNTH_C3A")], ids=["reel", "synth"]
)
def test_les_neuf_champs_correspondent_aux_entrees_sous_les_deux_labels(
    synthetic: bool, label: str
) -> None:
    """Le label `C3_<c>` n'existe qu'au niveau fonction en C3a — la CLI refuse toute évaluation
    réelle (§ L.1) ; `C3_SYNTH_<c>` est ce qu'elle produit. Les neuf champs valent dans les deux cas."""
    artifacts = _sound()
    decision = cv.decide(artifacts, violations=[])
    sha = cc.protocol_descriptor()["sha256"]
    chain = cv.build_verdict_string(
        "C3A",
        decision,
        sha,
        continuity_state=artifacts["continuity"]["state"],
        variant_key=artifacts["anchor"]["variant_key"],
        observations_sha256=OBSERVATIONS_SHA,
        synthetic=synthetic,
    )
    got_label, fields = _fields(chain)
    assert got_label == label
    assert tuple(fields) == NINE_FIELDS, "neuf champs, dans l'ordre, ni plus ni moins"
    assert fields == {
        "verdict": decision.issue,
        "raison": decision.reason or "-",
        "selection": artifacts["selection"]["retained"]["identity"],
        "statut_selection": artifacts["selection"]["status"],
        "continuite": artifacts["continuity"]["state"],
        "variante": VARIANT_KEY[:16],
        "provenance": artifacts["anchor"]["universe_provenance"],
        "protocole": sha[:16],
        "observations": OBSERVATIONS_SHA[:16],
    }
    assert decision.issue == cc.ISSUE_VALIDE and fields["raison"] == "-"


def test_la_cli_ecrit_la_chaine_synthetique_les_empreintes_et_la_portee(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifacts = _sound()
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 0
    payload = cc.read_json(tmp_path / "verdict.json")
    label, fields = _fields(payload["verdict_string"])
    assert label == "C3_SYNTH_C3A" and tuple(fields) == NINE_FIELDS
    # Chaque champ correspond à son entrée sur disque, pas à une valeur recopiée dans la fixture.
    anchor = cc.read_json(tmp_path / "anchor.json")
    entry = cc.read_json(tmp_path / "entry.json")
    continuity = cc.read_json(tmp_path / "continuity.json")
    assert fields["variante"] == anchor["variant_key"][:16] == payload["variante"][:16]
    assert fields["observations"] == entry["inputs_sha256"]["observations"][:16]
    assert payload["observations_sha256"] == entry["inputs_sha256"]["observations"]
    assert fields["continuite"] == continuity["state"] == payload["continuite"]
    assert fields["protocole"] == cc.protocol_descriptor()["sha256"][:16]
    assert (
        fields["selection"]
        == payload["selection"]
        == artifacts["selection"]["retained"]["identity"]
    )
    # `inputs_sha256` des cinq entrées, égales aux fichiers.
    assert set(payload["inputs_sha256"]) == set(cv.INPUT_NAMES)
    for name in cv.INPUT_NAMES:
        assert payload["inputs_sha256"][name] == cc.file_sha256(tmp_path / f"{name}.json")
    assert payload["ok"] is True and payload["exit_code"] == 0 and payload["step"] == "verdict"
    assert payload["synthetic"] is True and payload["portee"] == cv.PORTEE_SYNTH
    assert payload["chain"]["mode"] == "verdict" and payload["chain"]["verified"] is True
    assert (
        all(c["ok"] for c in payload["chain"]["checks"]) and len(payload["chain"]["checks"]) == 17
    )
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"PORTEE : {cv.PORTEE_SYNTH}"
    assert out[1] == payload["verdict_string"]


def test_l_artefact_diagnostic_porte_les_empreintes_et_aucune_chaine(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["selection"]["provenance"] = "unknown"  # ≠ anchor.universe_provenance → violation
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["exit_code"] == 1 and payload["ok"] is False
    assert payload["verdict_string"] is None and payload["verdict"] is None
    assert set(payload["inputs_sha256"]) == set(cv.INPUT_NAMES)
    # Un diagnostic n'est jamais une chaîne « vérifiée » (revue Fin 3) ; les recoupements
    # d'empreintes, eux, ont tous passé — la violation vient d'ailleurs.
    assert payload["chain"]["mode"] == "verdict" and payload["chain"]["verified"] is False
    assert all(c["ok"] for c in payload["chain"]["checks"])


# ---------------------------------------------------------------------------
# Confinement des verdicts synthétiques (plan § 6.6) — une règle de code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["absent", None, "true"], ids=["absent", "null", "chaine"])
def test_synthetic_absent_nul_ou_chaine_est_une_erreur_d_entree(tmp_path: Path, value: Any) -> None:
    artifacts = _sound()
    if value == "absent":
        del artifacts["evaluation"]["synthetic"]
    else:
        artifacts["evaluation"]["synthetic"] = value
    with pytest.raises(cc.MissingEvidenceError, match="synthetic"):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_une_evaluation_reelle_est_refusee_rien_publie(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§ L.1 : `validé`/`réfuté` sont inatteignables sur données réelles en C3a — le code l'exécute."""
    artifacts = _sound()
    artifacts["evaluation"]["synthetic"] = False
    with pytest.raises(cc.EntryRefusedError) as info:
        cv.decide(artifacts, violations=[])
    assert info.value.reason == "R0_INVALID_RUN"
    assert "évaluation réelle non exerçable par l'outillage C3a" in str(info.value)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()
    assert "évaluation réelle non exerçable par l'outillage C3a — § L.1" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Continuité → verdict (plan § 6.4) ; clause 3 en échec = convention datée du 21/09 (§ 6.1)
# ---------------------------------------------------------------------------


def test_clause_3_en_echec_moteur_signal_a_l_evaluation_issue_non_definie(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixture « moteur signal à l'évaluation » : liquidation terminale non normalisée, résumés et
    agrégat **concordants**. Le texte gelé ne définit pas l'issue → `UndefinedIssueError`, code 2,
    rien d'écrit, message cité (§ 6.1, convention datée du 21/09). Le cas contredit (résumé vrai
    sur une clause en échec) n'est plus ce refus mais un diagnostic code 1 — revue Fin 2 (2),
    testé sous `test_revue_Fin2_2_*`."""
    artifacts = _sound()
    artifacts["continuity"]["clauses"]["c3"] = {
        "state": "FAILED",
        "detail": "liquidation absente (moteur signal)",
    }
    artifacts["continuity"]["state"] = "FAILED"
    artifacts["continuity"]["liquidation_normalised"] = False
    with pytest.raises(cc.UndefinedIssueError) as info:
        cv.decide(artifacts, violations=[])
    assert str(info.value) == cv.UNDEFINED_ISSUE_MESSAGE
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()
    err = capsys.readouterr().err
    assert "ISSUE NON DEFINIE" in err
    assert "issue non définie par le texte gelé, amendement pendant (§ 6.1)" in err
    assert "convention d'outillage datée du 21/09" in err


@pytest.mark.parametrize("clause", ["c1", "c2", "c5"])
def test_clause_declarative_en_echec_est_un_refus_R0(tmp_path: Path, clause: str) -> None:
    """L'artefact déclare lui-même une rupture du contrat § B : refus, code 2, rien d'écrit."""
    artifacts = _sound()
    artifacts["continuity"]["clauses"][clause] = {"state": "FAILED", "detail": "rupture déclarée"}
    artifacts["continuity"]["state"] = "FAILED"
    with pytest.raises(cc.EntryRefusedError) as info:
        cv.decide(artifacts, violations=[])
    assert info.value.reason == "R0_INVALID_RUN" and f"clause {clause}" in str(info.value)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_l_evaluation_d_une_autre_configuration_est_refusee(tmp_path: Path) -> None:
    """L'évaluation (et sa continuité, cohérente) portent une autre configuration que la retenue :
    refus R0 (§ H.1). L'identité comparée est celle **dérivée** de l'évaluation (revue Fin 6)."""
    artifacts = _sound()
    artifacts["evaluation"].update({"pair": "SOL/USDC", "params": {"a": 2}})
    artifacts["continuity"]["identity"] = cc.candidate_identity("s", "SOL/USDC", {"a": 2})
    artifacts["continuity"]["pair"] = "SOL/USDC"
    with pytest.raises(cc.EntryRefusedError, match="configuration retenue"):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_une_identite_de_continuite_seule_discordante_est_une_violation(tmp_path: Path) -> None:
    """Le déclaré contredit le dérivé : violation, pas un refus — l'évaluation est bien celle de la
    configuration retenue."""
    artifacts = _sound()
    artifacts["continuity"]["identity"] = cc.candidate_identity("s", "SOL/USDC", {"a": 2})
    _, violations = _never_valide(artifacts)
    assert any("continuity.identity" in v for v in violations)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1


@pytest.mark.parametrize("state", ["DECLARED", "NOT_VERIFIABLE"])
def test_l_etat_agrege_est_porte_par_la_chaine_sans_changer_l_issue(state: str) -> None:
    """Clauses cohérentes avec l'agrégat (c1/c5 portées à l'état voulu, c2 DECLARED — ses seuls
    états admissibles sont {DECLARED, FAILED}, § 6.4) ; l'issue ne dépend pas de l'agrégat tant
    qu'aucune clause n'est FAILED. VERIFIED n'est pas un agrégat constructible (§ 6.4)."""
    artifacts = _sound()
    clauses = artifacts["continuity"]["clauses"]
    for key in ("c1", "c5"):
        clauses[key]["state"] = state
    clauses["c2"]["state"] = "DECLARED"
    artifacts["continuity"]["state"] = state
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert violations == [] and decision.continuity_state == state
    assert decision.issue == cc.ISSUE_VALIDE


def test_un_etat_de_continuite_hors_liste_close_est_une_erreur_d_entree() -> None:
    artifacts = _sound()
    artifacts["continuity"]["state"] = "OK"
    with pytest.raises(cc.MissingEvidenceError, match="continuity.state"):
        cv.decide(artifacts, violations=[])


# ---------------------------------------------------------------------------
# verify_chain — succès enregistré des amonts, empreintes recoupées
# ---------------------------------------------------------------------------


def _raws_and_paths(
    tmp_path: Path, artifacts: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Path]]:
    _write_cli_inputs(tmp_path, artifacts)
    paths = {name: tmp_path / f"{name}.json" for name in cv.INPUT_NAMES}
    return {name: cc.read_json(path) for name, path in paths.items()}, paths


def test_verify_chain_passe_sur_une_chaine_coherente(tmp_path: Path) -> None:
    raws, paths = _raws_and_paths(tmp_path, _sound())
    violations, checks = cv.verify_chain(raws, paths)
    assert violations == [] and len(checks) == 17 and all(c["ok"] for c in checks)
    assert [c["check"] for c in checks[:4]] == [
        f"{n}.coherence" for n in ("entry", "anchor", "selection", "continuity")
    ]


@pytest.mark.parametrize(
    ("artifact", "key"),
    [
        ("selection", "entry"),
        ("selection", "anchor"),
        ("selection", "observations"),
        ("selection", "manifest"),
        ("entry", "anchor"),
        ("entry", "manifest"),
        ("continuity", "evaluation"),
        ("continuity", "anchor"),
        ("continuity", "manifest"),
    ],
)
def test_une_empreinte_discordante_est_une_violation_code_1(
    tmp_path: Path, artifact: str, key: str
) -> None:
    artifacts = _sound()
    argv = _write_cli_inputs(tmp_path, artifacts)
    path = tmp_path / f"{artifact}.json"
    data = cc.read_json(path)
    data["inputs_sha256"][key] = "0" * 64
    cc.write_json(path, data)
    # Réécrire un amont change son empreinte : les consommateurs aval sont réécrits en cascade
    # pour isoler la seule discordance injectée.
    if artifact == "entry":
        sel = cc.read_json(tmp_path / "selection.json")
        sel["inputs_sha256"]["entry"] = cc.file_sha256(path)
        cc.write_json(tmp_path / "selection.json", sel)
    assert cv.main(argv) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False
    assert any(f"chaîne : {artifact}.{key}" in v for v in payload["violations"])
    failed = [c["check"] for c in payload["chain"]["checks"] if not c["ok"]]
    assert failed == [f"{artifact}.{key}"]


def test_un_protocole_different_dans_un_amont_est_une_violation(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["anchor"]["protocole"] = {"path": cc.PROTOCOL_RELPATH, "sha256": "f" * 64}
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert any("anchor.protocole" in v for v in payload["violations"])


@pytest.mark.parametrize("artifact", ["anchor", "selection", "continuity"])
@pytest.mark.parametrize(
    "failure",
    [
        {"ok": False, "invalide": True, "exit_code": 1},
        {"ok": False, "invalide": False, "exit_code": 2},
    ],
    ids=["diagnostic_coherent", "refus_coherent"],
)
def test_un_amont_en_echec_enregistre_coherent_est_un_refus_rien_ecrit(
    tmp_path: Path, artifact: str, failure: dict[str, Any]
) -> None:
    """Un échec amont **cohérent** garde son traitement : refus 2, rien d'écrit (revue Fin 4)."""
    artifacts = _sound()
    artifacts[artifact].update(failure)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_une_entree_diagnostic_invalide_coherente_est_un_refus(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["entry"].update({"invalide": True, "exit_code": 1, "ok": False})
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


@pytest.mark.parametrize("artifact", ["anchor", "entry", "selection", "continuity"])
def test_un_amont_sans_empreintes_est_une_erreur_d_entree(tmp_path: Path, artifact: str) -> None:
    artifacts = _sound()
    argv = _write_cli_inputs(tmp_path, artifacts)
    path = tmp_path / f"{artifact}.json"
    data = cc.read_json(path)
    del data["inputs_sha256"]
    cc.write_json(path, data)
    assert cv.main(argv) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_un_verdict_anterieur_discordant_est_signale_jamais_supprime(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifacts = _sound()
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 0
    first = (tmp_path / "verdict.json").read_bytes()
    # Une nouvelle évaluation sur disque : la continuité ne l'a pas consommée → violation, et
    # l'ancien verdict est signalé avant d'être remplacé par le diagnostic.
    data = cc.read_json(tmp_path / "evaluation.json")
    data["metrics"]["net_pnl"] = 43.0
    cc.write_json(tmp_path / "evaluation.json", data)
    assert cv.main(argv) == 1
    err = capsys.readouterr().err
    assert "AVERTISSEMENT un verdict antérieur discordant" in err
    assert (tmp_path / "verdict.json").read_bytes() != first
    assert cc.read_json(tmp_path / "verdict.json")["invalide"] is True


# ---------------------------------------------------------------------------
# Sous-commande chain — le site réel de l'orchestration (plan § 5.3)
# ---------------------------------------------------------------------------


def _retained_index(tmp_path: Path, w: dict[str, Any]) -> int | None:
    """Une chaîne de sondage anchor → entry → benchmark → select, pour connaître la retenue
    (``None`` si la sélection s'abstient)."""
    probe = tmp_path / "probe"
    probe.mkdir()
    registry = probe / "variants.json"
    anchor, entry, bench, sel = (probe / n for n in ("a.json", "e.json", "b.json", "s.json"))
    m, o, c, k = (str(w[n]) for n in ("manifest", "observations", "coverage", "candles"))
    now = ["--now", fx.NOW]
    assert (
        ca.main(["--manifest", m, "--registry", str(registry), "--output", str(anchor)] + now) == 0
    )
    assert (
        ce.main(
            [
                "--manifest",
                m,
                "--anchor",
                str(anchor),
                "--observations",
                o,
                "--coverage",
                c,
                "--output",
                str(entry),
            ]
            + now
        )
        == 0
    )
    assert (
        cb.main(
            [
                "--manifest",
                m,
                "--anchor",
                str(anchor),
                "--entry",
                str(entry),
                "--observations",
                o,
                "--candles",
                k,
                "--output",
                str(bench),
            ]
            + now
        )
        == 0
    )
    assert (
        cs.main(
            [
                "--manifest",
                m,
                "--anchor",
                str(anchor),
                "--entry",
                str(entry),
                "--observations",
                o,
                "--coverage",
                c,
                "--benchmark",
                str(bench),
                "--output",
                str(sel),
            ]
            + now
        )
        == 0
    )
    retained_block = cc.read_json(sel)["retained"]
    if retained_block is None:
        return None
    retained = retained_block["identity"]
    for i, cand in enumerate(w["payload"]["universe"]["candidates"]):
        if cc.candidate_identity(cand["strategy"], cand["pair"], cand["params"]) == retained:
            return i
    raise AssertionError("la configuration retenue n'est pas dans l'univers")


def _chain_world(
    tmp_path: Path, *, mutate_observations: Any = None, **eval_kw: Any
) -> dict[str, Any]:
    w = fx.world(tmp_path)
    if mutate_observations is not None:
        obs = cc.read_json(w["observations"])
        mutate_observations(obs)
        cc.write_json(w["observations"], obs)
    index = _retained_index(tmp_path, w)
    if index is None:
        index = 0  # abstention : l'évaluation porte sur un candidat de l'univers, sans retenue
    cand = w["payload"]["universe"]["candidates"][index]
    w["evaluation"] = tmp_path / "evaluation.json"
    w["benchmark_eval"] = tmp_path / "benchmark_eval.json"
    cc.write_json(w["evaluation"], fx.evaluation(w["payload"], candidate_index=index, **eval_kw))
    cc.write_json(w["benchmark_eval"], fx.benchmark_eval(cand["pair"]))
    w["out"] = tmp_path / "run"
    return w


def _chain_argv(
    w: dict[str, Any], *, out: Path | None = None, coverage: bool = True, candles: bool = True
) -> list[str]:
    argv = [
        "chain",
        "--manifest",
        str(w["manifest"]),
        "--observations",
        str(w["observations"]),
        "--evaluation",
        str(w["evaluation"]),
        "--benchmark-eval",
        str(w["benchmark_eval"]),
        "--registry",
        str(w["registry"]),
        "--out-dir",
        str(out if out is not None else w["out"]),
        "--now",
        fx.NOW,
    ]
    if coverage:
        argv += ["--coverage", str(w["coverage"])]
    if candles:
        argv += ["--candles", str(w["candles"])]
    return argv


CHAIN_FILES = (
    "anchor.json",
    "entry.json",
    "benchmark.json",
    "selection.json",
    "continuity.json",
    "verdict.json",
)


def test_chain_complete_sur_fixtures_verdict_et_neuf_champs_correspondants(tmp_path: Path) -> None:
    w = _chain_world(tmp_path)
    assert cv.main(_chain_argv(w)) == 0
    out = w["out"]
    assert all((out / f).exists() for f in CHAIN_FILES)
    payload = cc.read_json(out / "verdict.json")
    assert payload["ok"] is True and payload["verdict"] in (
        cc.ISSUE_VALIDE,
        cc.ISSUE_REFUTE,
        cc.ISSUE_INCONCLUSIF,
    )
    assert payload["chain"]["mode"] == "chain" and payload["chain"]["verified"] is True
    assert [s["name"] for s in payload["chain"]["steps"]] == [
        "anchor",
        "entry",
        "benchmark",
        "select",
        "continuity",
    ]
    assert all(s["exit_code"] == 0 for s in payload["chain"]["steps"])
    label, fields = _fields(payload["verdict_string"])
    assert label == "C3_SYNTH_C3A" and tuple(fields) == NINE_FIELDS
    anchor = cc.read_json(out / "anchor.json")
    entry = cc.read_json(out / "entry.json")
    selection = cc.read_json(out / "selection.json")
    continuity = cc.read_json(out / "continuity.json")
    assert fields["variante"] == anchor["variant_key"][:16]
    assert fields["observations"] == cc.file_sha256(w["observations"])[:16]
    assert (
        entry["inputs_sha256"]["observations"]
        == selection["inputs_sha256"]["observations"]
        == payload["observations_sha256"]
    )
    assert fields["selection"] == selection["retained"]["identity"] == continuity["identity"]
    assert (
        fields["statut_selection"] == selection["status"]
        and fields["continuite"] == continuity["state"]
    )
    assert fields["provenance"] == anchor["universe_provenance"]
    assert fields["protocole"] == cc.protocol_descriptor()["sha256"][:16]
    for name, path in (
        ("anchor", out / "anchor.json"),
        ("entry", out / "entry.json"),
        ("selection", out / "selection.json"),
        ("continuity", out / "continuity.json"),
        ("evaluation", w["evaluation"]),
    ):
        assert payload["inputs_sha256"][name] == cc.file_sha256(path)
    assert payload["portee"] == cv.PORTEE_SYNTH


def test_chain_contre_exemple_un_amont_echoue_avant_ecriture_et_le_verdict_ancien_reste(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run 1 cohérent sur disque ; run 2 : `c3_anchor` rend 2 **avant toute écriture** (registre
    malformé). `verify_chain` sur les fichiers **passe** (tous du run 1) ; `chain` doit échouer (2)
    et `verdict.json` rester octet pour octet celui du run 1 — les empreintes ne prouvent pas que
    l'invocation courante a réussi, seul le code de retour effectif le fait."""
    w = _chain_world(tmp_path)
    assert cv.main(_chain_argv(w)) == 0
    out = w["out"]
    before = {f: (out / f).read_bytes() for f in CHAIN_FILES}
    capsys.readouterr()
    w["registry"].write_text('{"variants": [1]}', encoding="utf-8")
    assert cv.main(_chain_argv(w)) == 2
    err = capsys.readouterr().err
    assert "CHAINE ARRETEE à l'étape anchor (code de retour 2)" in err
    after = {f: (out / f).read_bytes() for f in CHAIN_FILES}
    assert after == before, "rien n'a été réécrit : les six fichiers sont ceux du run 1"
    paths = {
        "entry": out / "entry.json",
        "anchor": out / "anchor.json",
        "selection": out / "selection.json",
        "continuity": out / "continuity.json",
        "evaluation": w["evaluation"],
    }
    raws = {name: cc.read_json(path) for name, path in paths.items()}
    violations, checks = cv.verify_chain(raws, paths)
    assert violations == [] and all(c["ok"] for c in checks), (
        "les fichiers du run 1 sont mutuellement cohérents : verify_chain seul ne voit pas l'échec"
    )


def test_chain_s_arrete_a_benchmark_sans_candles(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    w = _chain_world(tmp_path)
    assert cv.main(_chain_argv(w, candles=False)) == 2
    out = w["out"]
    assert (out / "anchor.json").exists() and (out / "entry.json").exists()
    assert not (out / "benchmark.json").exists() and not (out / "verdict.json").exists()
    assert "CHAINE ARRETEE à l'étape benchmark" in capsys.readouterr().err


def test_chain_sur_une_evaluation_reelle_s_arrete_au_verdict_rien_publie(tmp_path: Path) -> None:
    """§ 6.6 (2) de bout en bout : la continuité s'exécute, le verdict refuse, aucun `verdict.json`."""
    w = _chain_world(tmp_path, synthetic=False)
    assert cv.main(_chain_argv(w)) == 2
    assert (w["out"] / "continuity.json").exists()
    assert cc.read_json(w["out"] / "continuity.json")["synthetic"] is False
    assert not (w["out"] / "verdict.json").exists()


def test_chain_moteur_signal_a_l_evaluation_clause_3_FAILED_rien_publie(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """La convention datée du 21/09 de bout en bout : `c3_continuity` rapporte c3 `FAILED`
    (`liquidation` null), le verdict refuse de produire une issue, code 2, aucun `verdict.json`."""
    w = _chain_world(tmp_path, liquidation=False)
    assert cv.main(_chain_argv(w)) == 2
    continuity = cc.read_json(w["out"] / "continuity.json")
    assert continuity["clauses"]["c3"]["state"] == "FAILED"
    assert continuity["liquidation_normalised"] is False
    assert not (w["out"] / "verdict.json").exists()
    err = capsys.readouterr().err
    assert "ISSUE NON DEFINIE" in err and "amendement pendant (§ 6.1)" in err


@pytest.mark.skipif(
    not (REAL_OBSERVATIONS.exists() and REAL_MANIFEST.exists() and REAL_REGISTRY.exists()),
    reason="artefact du rejeu ou livrable réel absent",
)
def test_chain_sur_le_livrable_reel_v20_s_arrete_a_l_ancrage_code_2_rien_d_ecrit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """En-tête v2.1 et § A.6 : le manifeste réel de C3a déclare le sha256 de v2.0, et `c3_anchor` asserte le
    sha256 du protocole courant parmi les valeurs gelées — la chaîne s'arrête donc à l'étape 1 (§ L.1), code 2,
    rien d'écrit en aval (§ I.1, ligne 2). L'artefact du rejeu et le registre committé restent intacts."""
    before = cc.file_sha256(REAL_OBSERVATIONS)
    registry_before = cc.file_sha256(REAL_REGISTRY)
    registry = tmp_path / "variants.json"
    registry.write_bytes(REAL_REGISTRY.read_bytes())
    never_read = tmp_path / "never_read.json"
    never_read.write_text("{}", encoding="utf-8")
    out = tmp_path / "run"
    argv = [
        "chain",
        "--manifest",
        str(REAL_MANIFEST),
        "--observations",
        str(REAL_OBSERVATIONS),
        "--evaluation",
        str(never_read),
        "--benchmark-eval",
        str(never_read),
        "--registry",
        str(registry),
        "--out-dir",
        str(out),
        "--now",
        fx.NOW,
    ]
    assert cv.main(argv) == 2
    for f in (
        "anchor.json",
        "entry.json",
        "benchmark.json",
        "selection.json",
        "continuity.json",
        "verdict.json",
    ):
        assert not (out / f).exists(), f
    err = capsys.readouterr().err
    assert "CHAINE ARRETEE à l'étape anchor" in err and "protocol_sha256" in err
    assert cc.file_sha256(REAL_OBSERVATIONS) == before
    assert cc.file_sha256(REAL_REGISTRY) == registry_before
    assert cc.file_sha256(registry) == registry_before, (
        "un refus d'ancrage ne réécrit pas le registre"
    )
    assert never_read.read_text(encoding="utf-8") == "{}"


def test_le_parseur_chain_n_expose_que_des_chemins_une_campagne_et_un_horodatage() -> None:
    actions = {a.dest for a in cv.build_chain_parser()._actions} - {"help"}
    assert actions == {
        "manifest",
        "observations",
        "coverage",
        "candles",
        "evaluation",
        "benchmark_eval",
        "registry",
        "out_dir",
        "campaign",
        "now",
    }


def test_un_now_illisible_en_mode_chain_est_une_erreur_d_usage_rien_ecrit(tmp_path: Path) -> None:
    w = _chain_world(tmp_path)
    argv = _chain_argv(w)
    argv[argv.index("--now") + 1] = "hier"
    assert cv.main(argv) == 2
    assert not any((w["out"] / f).exists() for f in CHAIN_FILES)


# ---------------------------------------------------------------------------
# Revue Fin (1) — confinement synthétique : aucun chemin de publication avant le contrôle
# ---------------------------------------------------------------------------

SYNTH_VALUES: list[tuple[str, Any]] = [
    ("true", True),
    ("false", False),
    ("absent", "absent"),
    ("null", None),
    ("chaine", "true"),
]


def _set_synthetic(evaluation: dict[str, Any], value: Any) -> None:
    if value == "absent":
        evaluation.pop("synthetic", None)
    else:
        evaluation["synthetic"] = value


def _abstain(artifacts: dict[str, Any]) -> None:
    artifacts["selection"].update(
        {
            "status": "ABSTENTION",
            "reason": "A_NO_ADMISSIBLE_CANDIDATE",
            "retained": None,
            "admissible": [],
            "survivors": [],
            "ranking": [],
        }
    )


def _violate(artifacts: dict[str, Any]) -> None:
    artifacts["selection"]["provenance"] = "unknown"  # ≠ anchor → violation, chemin diagnostic


PUBLICATION_PATHS: list[tuple[str, Any]] = [
    ("abstention", _abstain),
    ("verdict", lambda a: None),
    ("diagnostic", _violate),
]


@pytest.mark.parametrize(
    ("path", "mutate"), PUBLICATION_PATHS, ids=[p for p, _ in PUBLICATION_PATHS]
)
@pytest.mark.parametrize(("label", "value"), SYNTH_VALUES, ids=[v for v, _ in SYNTH_VALUES])
def test_revue_Fin_1_confinement_au_niveau_fonction(
    path: str, mutate: Any, label: str, value: Any
) -> None:
    """Le contrôle `evaluation.synthetic` précède **tout** chemin : abstention, verdict calculé,
    diagnostic. Vrai → la décision porte `synthetic=True` et la chaîne le préfixe ; faux → refus ;
    absent / null / chaîne → erreur d'entrée."""
    artifacts = _sound()
    mutate(artifacts)
    _set_synthetic(artifacts["evaluation"], value)
    violations: list[str] = []
    if value is True:
        decision = cv.decide(artifacts, violations=violations)
        assert decision.synthetic is True, path
        chain = cv.build_verdict_string(
            "C3A",
            decision,
            cc.protocol_descriptor()["sha256"],
            continuity_state=decision.continuity_state,
            variant_key=VARIANT_KEY,
            observations_sha256=OBSERVATIONS_SHA,
            synthetic=decision.synthetic,
        )
        assert chain.startswith("C3_SYNTH_C3A | "), chain
        assert (path == "diagnostic") == bool(violations)
    elif value is False:
        with pytest.raises(cc.EntryRefusedError, match="évaluation réelle non exerçable"):
            cv.decide(artifacts, violations=violations)
    else:
        with pytest.raises(cc.MissingEvidenceError, match="evaluation.synthetic"):
            cv.decide(artifacts, violations=violations)


@pytest.mark.parametrize(
    ("path", "mutate"), PUBLICATION_PATHS, ids=[p for p, _ in PUBLICATION_PATHS]
)
@pytest.mark.parametrize(("label", "value"), SYNTH_VALUES, ids=[v for v, _ in SYNTH_VALUES])
def test_revue_Fin_1_confinement_au_niveau_cli(
    tmp_path: Path,
    path: str,
    mutate: Any,
    label: str,
    value: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifacts = _sound()
    mutate(artifacts)
    _set_synthetic(artifacts["evaluation"], value)
    code = cv.main(_write_cli_inputs(tmp_path, artifacts))
    out = tmp_path / "verdict.json"
    captured = capsys.readouterr()
    if value is True:
        assert code == (1 if path == "diagnostic" else 0), captured.err
        payload = cc.read_json(out)
        assert payload["synthetic"] is True and payload["portee"] == cv.PORTEE_SYNTH
        assert captured.out.splitlines()[0] == f"PORTEE : {cv.PORTEE_SYNTH}"
        if path == "diagnostic":
            assert payload["invalide"] is True and payload["verdict_string"] is None
        else:
            assert payload["verdict_string"].startswith("C3_SYNTH_C3A | ")
            assert "C3_C3A |" not in payload["verdict_string"]
    else:
        assert code == 2 and not out.exists(), (path, label, captured.err)
        if value is False:
            assert "évaluation réelle non exerçable par l'outillage C3a" in captured.err


def _all_d3(obs: dict[str, Any]) -> None:
    for e in obs.values():
        e[fx.PREFIX]["total_trades"] = 20  # aucune vente identifiable : D3 échoue partout


def _contradict_estimability(evaluation: dict[str, Any]) -> None:
    evaluation["estimability"] = {"E1": False, "E2": False, "ok": False}  # ≠ recalculé → violation


CHAIN_PATHS: list[tuple[str, Any, Any]] = [
    ("abstention", _all_d3, None),
    ("verdict", None, None),
    ("diagnostic", None, _contradict_estimability),
]


@pytest.mark.parametrize(
    ("path", "mutate_obs", "mutate_eval"), CHAIN_PATHS, ids=[p for p, _, _ in CHAIN_PATHS]
)
@pytest.mark.parametrize(("label", "value"), SYNTH_VALUES, ids=[v for v, _ in SYNTH_VALUES])
def test_revue_Fin_1_confinement_au_niveau_chain(
    tmp_path: Path,
    path: str,
    mutate_obs: Any,
    mutate_eval: Any,
    label: str,
    value: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    w = _chain_world(tmp_path, mutate_observations=mutate_obs)
    evaluation = cc.read_json(w["evaluation"])
    if mutate_eval is not None:
        mutate_eval(evaluation)
    _set_synthetic(evaluation, value)
    cc.write_json(w["evaluation"], evaluation)
    code = cv.main(_chain_argv(w))
    out = w["out"] / "verdict.json"
    captured = capsys.readouterr()
    if value is True:
        assert code == (1 if path == "diagnostic" else 0), captured.err
        payload = cc.read_json(out)
        assert payload["synthetic"] is True and payload["portee"] == cv.PORTEE_SYNTH
        if path == "abstention":
            assert payload["verdict_string"].startswith(
                "C3_SYNTH_C3A | verdict=inconclusif | raison=A_NO_ADMISSIBLE_CANDIDATE"
            )
        elif path == "verdict":
            assert payload["verdict_string"].startswith("C3_SYNTH_C3A | ")
        else:
            assert payload["invalide"] is True and payload["verdict_string"] is None
    else:
        assert code == 2 and not out.exists(), (path, label, captured.err)


# ---------------------------------------------------------------------------
# Revue Fin (2) — continuité : résumés et agrégat dérivés des clauses, jamais recopiés
# ---------------------------------------------------------------------------


def _never_valide(artifacts: dict[str, Any]) -> tuple[Any, list[str]]:
    """Exécute `decide()` ; renvoie (issue ou exception, violations). Asserte « jamais validé »."""
    violations: list[str] = []
    try:
        decision = cv.decide(artifacts, violations=violations)
    except (cc.EntryRefusedError, cc.UndefinedIssueError) as exc:
        return exc, violations
    # Un artefact contredit ne publie jamais « validé » : soit l'issue calculée n'est pas validé,
    # soit une violation la retient dans un diagnostic (§ I.1 l.15) — la CLI rend 1, jamais 0.
    assert decision.issue != cc.ISSUE_VALIDE or violations, (
        "un artefact de continuité contredit ne valide jamais"
    )
    return decision, violations


def test_revue_Fin_2_c4_FAILED_et_warmup_anchor_ok_vrai_est_une_violation_jamais_valide(
    tmp_path: Path,
) -> None:
    """Reproduction d'Astra : la clause dit FAILED, le résumé dit vrai — le verdict lisait le résumé."""
    artifacts = _sound()
    artifacts["continuity"]["clauses"]["c4"] = {"state": "FAILED", "detail": "amorçage insuffisant"}
    artifacts["continuity"]["state"] = "FAILED"
    # résumé laissé à True : contradiction déclaré / dérivé
    outcome, violations = _never_valide(artifacts)
    assert any("warmup_anchor_ok" in v for v in violations), violations
    assert isinstance(outcome, cv.Decision) and outcome.reason == "D_WARMUP_ANCHOR", (
        "l'action se branche sur la clause : D_WARMUP_ANCHOR (§ I.1 l.12)"
    )
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["verdict"] is None


def test_revue_Fin_2_agregat_VERIFIED_declare_avec_c1_c5_NOT_VERIFIABLE_est_une_violation(
    tmp_path: Path,
) -> None:
    """Reproduction d'Astra : précédence FAILED > NOT_VERIFIABLE > DECLARED > VERIFIED, recalculée."""
    artifacts = _sound()
    artifacts["continuity"]["state"] = "VERIFIED"
    outcome, violations = _never_valide(artifacts)
    assert any("continuity.state" in v and "NOT_VERIFIABLE" in v for v in violations), violations
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    assert cc.read_json(tmp_path / "verdict.json")["invalide"] is True


@pytest.mark.parametrize(
    ("summary", "mutate_block", "expected_reason"),
    [
        (
            "warmup_anchor_ok",
            lambda c: c["clauses"]["c4"].__setitem__("state", "FAILED"),
            "D_WARMUP_ANCHOR",
        ),
        ("warmup_anchor_ok", lambda c: c.__setitem__("warmup_anchor_ok", False), None),
        (
            "benchmark_comparable",
            lambda c: (
                c["comparator"].__setitem__("state", "FAILED"),
                c["comparator"]["tests"].__setitem__("ff_ok", False),
            ),
            "E_NO_BENCHMARK",
        ),
        ("benchmark_comparable", lambda c: c.__setitem__("benchmark_comparable", False), None),
        (
            "stamp_same_daily_cell",
            lambda c: c["stamp_cell"].__setitem__("state", "FAILED"),
            "E_STAMP_MISMATCH",
        ),
        ("stamp_same_daily_cell", lambda c: c.__setitem__("stamp_same_daily_cell", False), None),
        (
            "liquidation_normalised",
            lambda c: c["clauses"]["c3"].__setitem__("state", "NOT_VERIFIABLE"),
            None,
        ),
        ("liquidation_normalised", lambda c: c.__setitem__("liquidation_normalised", False), None),
        ("liquidation_normalised", lambda c: c.__setitem__("liquidation_normalised", None), None),
    ],
    ids=[
        "c4_FAILED_resume_vrai",
        "c4_VERIFIED_resume_faux",
        "comparator_FAILED_resume_vrai",
        "comparator_VERIFIED_resume_faux",
        "stamp_FAILED_resume_vrai",
        "stamp_VERIFIED_resume_faux",
        "c3_NOT_VERIFIABLE_resume_vrai",
        "c3_VERIFIED_resume_faux",
        "c3_VERIFIED_resume_null",
    ],
)
def test_revue_Fin_2_chaque_resume_contredit_est_une_violation(
    tmp_path: Path, summary: str, mutate_block: Any, expected_reason: str | None
) -> None:
    artifacts = _sound()
    mutate_block(artifacts["continuity"])
    if artifacts["continuity"]["clauses"]["c4"]["state"] == "FAILED":
        artifacts["continuity"]["state"] = "FAILED"
    outcome, violations = _never_valide(artifacts)
    assert any(summary in v for v in violations), (summary, violations)
    if expected_reason is not None:
        assert isinstance(outcome, cv.Decision) and outcome.reason == expected_reason
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    assert cc.read_json(tmp_path / "verdict.json")["invalide"] is True


@pytest.mark.parametrize(
    ("mutate_block", "expected"),
    [
        (
            lambda c: (
                c["clauses"]["c4"].__setitem__("state", "FAILED"),
                c.__setitem__("state", "FAILED"),
                c.__setitem__("warmup_anchor_ok", False),
            ),
            "D_WARMUP_ANCHOR",
        ),
        (
            lambda c: (
                c["comparator"].__setitem__("state", "FAILED"),
                c["comparator"]["tests"].__setitem__("n_returns_ok", False),
                c.__setitem__("benchmark_comparable", False),
            ),
            "E_NO_BENCHMARK",
        ),
        (
            lambda c: (
                c["stamp_cell"].__setitem__("state", "FAILED"),
                c.__setitem__("stamp_same_daily_cell", False),
            ),
            "E_STAMP_MISMATCH",
        ),
        (
            lambda c: (
                c["stamp_cell"].__setitem__("state", "NOT_VERIFIABLE"),
                c.__setitem__("stamp_same_daily_cell", False),
            ),
            "E_STAMP_MISMATCH",
        ),
    ],
    ids=["c4", "comparator", "stamp_FAILED", "stamp_NOT_VERIFIABLE"],
)
def test_revue_Fin_2_les_actions_se_branchent_sur_les_clauses_coherentes(
    tmp_path: Path, mutate_block: Any, expected: str
) -> None:
    """Résumés cohérents avec les clauses : aucune violation, la raison run vient de la clause."""
    artifacts = _sound()
    mutate_block(artifacts["continuity"])
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert (
        violations == [] and decision.issue == cc.ISSUE_INCONCLUSIF and decision.reason == expected
    )
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 0
    payload = cc.read_json(tmp_path / "verdict.json")
    assert (
        payload["raison"] == expected and payload["continuite"] == artifacts["continuity"]["state"]
    )


def test_revue_Fin_2_c3_FAILED_coherent_est_l_issue_non_definie_et_normalise_faux_seul_une_violation() -> (
    None
):
    artifacts = _sound()
    c = artifacts["continuity"]
    c["clauses"]["c3"]["state"] = "FAILED"
    c["state"] = "FAILED"
    c["liquidation_normalised"] = False
    with pytest.raises(cc.UndefinedIssueError):
        cv.decide(artifacts, violations=[])
    # Le résumé seul ne déclenche pas la convention : il est contredit par la clause → violation.
    artifacts = _sound()
    artifacts["continuity"]["liquidation_normalised"] = False
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert decision.issue != cc.ISSUE_VALIDE or violations, "jamais validé sans violation"
    assert any("liquidation_normalised" in v for v in violations)


# ---------------------------------------------------------------------------
# Revue Fin 2 (1) — la table § 6.4 s'applique en liste close ; les attendus se dérivent de la table
# ---------------------------------------------------------------------------

#: Colonne « États atteignables (C3a) » de la table § 6.4 (plan révisé, validée au second R1),
#: **recopiée du texte, pas du code** : la liste close de chaque clause.
ADMISSIBLE_STATES_6_4: dict[str, tuple[str, ...]] = {
    "c1": ("NOT_VERIFIABLE", "DECLARED", "FAILED"),
    "c2": ("DECLARED", "FAILED"),
    "c3": ("VERIFIED", "NOT_VERIFIABLE", "FAILED"),
    "c4": ("VERIFIED", "FAILED"),
    "c5": ("NOT_VERIFIABLE", "DECLARED", "FAILED"),
}

#: Résumés dérivés d'une clause, tels que le plan les fixe (§ 6.4 c4 : « VERIFIED / FAILED » ;
#: § 6.4 c3 et § 6.5 : `liquidation_normalised` vrai par preuve par lot, faux en échec, indécidable
#: sans lots) — écrits depuis le texte pour que le test ne recopie pas l'implémentation.
NORMALISED_6_4: dict[str, bool | None] = {"VERIFIED": True, "NOT_VERIFIABLE": None, "FAILED": False}


def _aggregate_6_4(states: dict[str, str]) -> str:
    """« Agrégat continuite= : FAILED > NOT_VERIFIABLE > DECLARED > VERIFIED » (§ 6.4, texte)."""
    for worst in ("FAILED", "NOT_VERIFIABLE", "DECLARED", "VERIFIED"):
        if worst in states.values():
            return worst
    return "VERIFIED"


#: Chaque ligne (clause, état) → issue attendue **et son appui**, la ligne § 6.4 qui la justifie.
#: `calculee` = « issue calculée, continuite= le porte » ; `R0` = refus code 2 (l.1510) ;
#: `undefined` = UndefinedIssueError (§ 6.1, convention datée du 21/09) ; `D_WARMUP_ANCHOR` = raison
#: run (I.1 l.12) ; `hors_liste` = valeur hors liste close → code 2, rien publié (chantier 0).
TABLE_6_4: list[tuple[str, str, str, str]] = [
    (
        "c1",
        "NOT_VERIFIABLE",
        "calculee",
        "§ 6.4 c1 : NOT_VERIFIABLE (bloc absent) → issue calculée ; § B.2 l.743, l.723-724",
    ),
    (
        "c1",
        "DECLARED",
        "calculee",
        "§ 6.4 c1 : DECLARED (flat_start_proof cohérent) → issue calculée ; § B.2 l.764-768",
    ),
    (
        "c1",
        "FAILED",
        "R0",
        "§ 6.4 c1 : FAILED → R0 code 2, l'artefact déclare une rupture § B.2 ; l.1510",
    ),
    (
        "c1",
        "VERIFIED",
        "hors_liste",
        "§ 6.4 c1 : atteignables {NOT_VERIFIABLE, DECLARED, FAILED} — aucune déclaration ne produit VERIFIED",
    ),
    (
        "c2",
        "DECLARED",
        "calculee",
        "§ 6.4 c2 : DECLARED (single_call ∧ grille continue) → idem c1 ; § B.4 l.822-832",
    ),
    (
        "c2",
        "FAILED",
        "R0",
        "§ 6.4 c2 : FAILED (false ou grille discontinue) → idem c1, R0 code 2 ; § B.4 l.822-832",
    ),
    ("c2", "NOT_VERIFIABLE", "hors_liste", "§ 6.4 c2 : atteignables {DECLARED, FAILED}"),
    (
        "c2",
        "VERIFIED",
        "hors_liste",
        "§ 6.4 c2 : atteignables {DECLARED, FAILED} — clause déclarative",
    ),
    (
        "c3",
        "VERIFIED",
        "calculee",
        "§ 6.4 c3 : VERIFIED (preuve par lot présente et vraie) → issue calculée ; § B.3 l.811-815",
    ),
    (
        "c3",
        "NOT_VERIFIABLE",
        "calculee",
        "§ 6.4 c3 : NOT_VERIFIABLE (lots absents, § 6.5) → issue calculée, porté par continuite= ; § B.3 l.811-815",
    ),
    (
        "c3",
        "FAILED",
        "undefined",
        "§ 6.4 c3 : FAILED → UndefinedIssueError, code 2, rien publié (§ 6.1) ; § B.3 l.811-815, § G.2 l.1399",
    ),
    (
        "c3",
        "DECLARED",
        "hors_liste",
        "§ 6.4 c3 : atteignables {VERIFIED, NOT_VERIFIABLE, FAILED} — aucune déclaration ne prouve une liquidation costée",
    ),
    (
        "c4",
        "VERIFIED",
        "calculee",
        "§ 6.4 c4 : VERIFIED (sufficient recalculé vrai sur chaque TF) → issue calculée ; § B.5 l.848-853",
    ),
    (
        "c4",
        "FAILED",
        "D_WARMUP_ANCHOR",
        "§ 6.4 c4 : FAILED → D_WARMUP_ANCHOR (l.12) ; § B.5 l.848-853, I.1 l.1525",
    ),
    (
        "c4",
        "NOT_VERIFIABLE",
        "hors_liste",
        "§ 6.4 c4 : atteignables {VERIFIED, FAILED} — l'amorçage est recalculé, jamais non vérifiable",
    ),
    (
        "c4",
        "DECLARED",
        "hors_liste",
        "§ 6.4 c4 : atteignables {VERIFIED, FAILED} — l'amorçage n'est jamais déclaré",
    ),
    (
        "c5",
        "NOT_VERIFIABLE",
        "calculee",
        "§ 6.4 c5 : NOT_VERIFIABLE (first_fill_at absent) → idem c1 ; § C.3 l.940",
    ),
    (
        "c5",
        "DECLARED",
        "calculee",
        "§ 6.4 c5 : DECLARED (présent, > T) → idem c1 ; § A.4 l.252-256",
    ),
    ("c5", "FAILED", "R0", "§ 6.4 c5 : FAILED (≤ T) → idem c1, R0 code 2 ; § C.3 l.940"),
    (
        "c5",
        "VERIFIED",
        "hors_liste",
        "§ 6.4 c5 : atteignables {NOT_VERIFIABLE, DECLARED, FAILED} — clause déclarative",
    ),
]


def _coherent_continuity(artifacts: dict[str, Any], clause: str, state: str) -> None:
    """Pose l'état, puis des résumés et un agrégat **cohérents selon le texte** (pas selon le code)."""
    c = artifacts["continuity"]
    c["clauses"][clause]["state"] = state
    states = {k: v["state"] for k, v in c["clauses"].items()}
    c["state"] = _aggregate_6_4(states)
    c["warmup_anchor_ok"] = states["c4"] == "VERIFIED"
    if states["c3"] in NORMALISED_6_4:
        c["liquidation_normalised"] = NORMALISED_6_4[states["c3"]]


def test_la_liste_close_des_etats_par_clause_est_celle_de_la_table_6_4() -> None:
    assert cc.CLAUSE_ADMISSIBLE_STATES == ADMISSIBLE_STATES_6_4
    for clause, states in ADMISSIBLE_STATES_6_4.items():
        assert set(states) <= set(cc.CONTINUITY_STATES), clause
    # Le résumé de c3 est défini sur la liste close de c3, et sur elle seule (§ 6.4 c3, § 6.5).
    assert cc.LIQUIDATION_NORMALISED_OF_C3 == NORMALISED_6_4
    assert set(cc.LIQUIDATION_NORMALISED_OF_C3) == set(ADMISSIBLE_STATES_6_4["c3"])


@pytest.mark.parametrize(
    ("block", "state"),
    [("stamp_cell", "DECLARED"), ("comparator", "DECLARED"), ("comparator", "NOT_VERIFIABLE")],
)
def test_revue_Fin2_1_les_blocs_derivables_ont_aussi_leur_liste_close(
    tmp_path: Path, block: str, state: str
) -> None:
    """`stamp_cell` (§ B.4) n'est jamais « déclarée » ; le comparateur (§ C.5) est une conjonction
    recalculée, vraie ou fausse — hors liste → code 2, rien publié."""
    artifacts = _sound()
    artifacts["continuity"][block]["state"] = state
    with pytest.raises(cc.MissingEvidenceError, match=f"continuity.{block}.state"):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


@pytest.mark.parametrize(
    ("clause", "state", "expected", "appui"),
    TABLE_6_4,
    ids=[f"{c}-{s}-{e}" for c, s, e, _ in TABLE_6_4],
)
def test_revue_Fin2_1_chaque_ligne_de_la_table_6_4_donne_l_issue_qu_elle_dit(
    tmp_path: Path, clause: str, state: str, expected: str, appui: str
) -> None:
    """Attendus **dérivés de la table**, appui cité ligne à ligne — un paramétré qui encoderait le
    comportement de l'implémentation serait un verrou posé sur le défaut (revue Fin 2, leçon)."""
    artifacts = _sound()
    _coherent_continuity(artifacts, clause, state)
    violations: list[str] = []
    argv = _write_cli_inputs(tmp_path, artifacts)
    out = tmp_path / "verdict.json"
    if expected == "hors_liste":
        with pytest.raises(cc.MissingEvidenceError, match=f"continuity.clauses.{clause}.state"):
            cv.decide(artifacts, violations=violations)
        assert cv.main(argv) == 2 and not out.exists(), appui
        return
    if expected == "R0":
        with pytest.raises(cc.EntryRefusedError) as info:
            cv.decide(artifacts, violations=violations)
        assert info.value.reason == "R0_INVALID_RUN" and violations == [], appui
        assert cv.main(argv) == 2 and not out.exists(), appui
        return
    if expected == "undefined":
        with pytest.raises(cc.UndefinedIssueError):
            cv.decide(artifacts, violations=violations)
        assert violations == [], appui
        assert cv.main(argv) == 2 and not out.exists(), appui
        return
    decision = cv.decide(artifacts, violations=violations)
    assert violations == [], (appui, violations)
    assert decision.continuity_state == artifacts["continuity"]["state"], appui
    if expected == "D_WARMUP_ANCHOR":
        assert decision.issue == cc.ISSUE_INCONCLUSIF and decision.reason == "D_WARMUP_ANCHOR", (
            appui
        )
        assert cv.main(argv) == 0 and cc.read_json(out)["raison"] == "D_WARMUP_ANCHOR"
        return
    assert expected == "calculee"
    # « issue calculée » : le témoin sain franchit E1/E2 et Q1-Q3 → validé, la clause n'y change rien.
    assert decision.issue == cc.ISSUE_VALIDE, appui
    assert cv.main(argv) == 0 and cc.read_json(out)["continuite"] == decision.continuity_state


@pytest.mark.parametrize("state", ["NOT_VERIFIABLE", "DECLARED"])
def test_revue_Fin2_1_c4_non_verifiable_ou_declare_est_hors_liste_jamais_valide(
    tmp_path: Path, state: str
) -> None:
    """La régression reproduite : c4 ∈ {VERIFIED, FAILED} seulement (§ 6.4 c4) — tout autre état
    est hors liste close, code 2, rien publié ; jamais « validé »."""
    artifacts = _sound()
    _coherent_continuity(artifacts, "c4", state)
    with pytest.raises(cc.MissingEvidenceError, match="continuity.clauses.c4.state"):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_revue_Fin2_1_l_agregat_VERIFIED_est_inconstructible_en_C3a() -> None:
    """c1, c2, c5 sont déclaratives : VERIFIED leur est inatteignable (§ 6.4), donc aucune
    combinaison d'états admissibles n'agrège en VERIFIED — sur les 3×2×3×2×3 = 108 combinaisons,
    par le texte (`_aggregate_6_4`) comme par le code (`cc.continuity_aggregate`), et dans la chaîne."""
    import itertools

    combos = list(
        itertools.product(*(ADMISSIBLE_STATES_6_4[k] for k in ("c1", "c2", "c3", "c4", "c5")))
    )
    assert len(combos) == 108
    for combo in combos:
        states = dict(zip(("c1", "c2", "c3", "c4", "c5"), combo, strict=True))
        assert _aggregate_6_4(states) != "VERIFIED", states
        assert cc.continuity_aggregate(states) == _aggregate_6_4(states), states
        artifacts = _sound()
        c = artifacts["continuity"]
        for key, value in states.items():
            c["clauses"][key]["state"] = value
        c["state"] = _aggregate_6_4(states)
        c["warmup_anchor_ok"] = states["c4"] == "VERIFIED"
        c["liquidation_normalised"] = NORMALISED_6_4[states["c3"]]
        violations: list[str] = []
        declarative_failed = "FAILED" in (states["c1"], states["c2"], states["c5"])
        try:
            decision = cv.decide(artifacts, violations=violations)
        except cc.EntryRefusedError:
            # § 6.4 c1/c2/c5 : FAILED → R0 ; quand c3 est aussi FAILED, le refus R0 précède
            # l'issue non définie (§ H : « R0 est évalué avant toute autre chose »).
            assert declarative_failed, states
            continue
        except cc.UndefinedIssueError:
            # § 6.4 c3 : FAILED → UndefinedIssueError, seulement si aucune clause déclarative n'a
            # déjà rompu le contrat.
            assert states["c3"] == "FAILED" and not declarative_failed, states
            continue
        assert not declarative_failed and states["c3"] != "FAILED", states
        assert violations == [], (states, violations)
        assert decision.continuity_state in ("NOT_VERIFIABLE", "DECLARED", "FAILED"), states
        assert decision.continuity_state != "VERIFIED"
        assert (decision.issue == cc.ISSUE_VALIDE) == ("FAILED" not in states.values()), states


def test_revue_Fin_2_l_etat_du_comparateur_est_derive_de_ses_tests() -> None:
    artifacts = _sound()
    artifacts["continuity"]["comparator"]["tests"]["all_finite"] = False  # état laissé VERIFIED
    outcome, violations = _never_valide(artifacts)
    assert any("comparator" in v for v in violations), violations
    assert isinstance(outcome, cv.Decision) and outcome.reason == "E_NO_BENCHMARK"


@pytest.mark.parametrize(
    "missing",
    [
        "stamp_cell",
        "comparator",
        ("comparator", "tests"),
        ("comparator", "tests", "all_finite"),
        "evaluation_window",
        "pair",
    ],
)
def test_revue_Fin_2_bloc_de_continuite_manquant_est_une_erreur_d_entree(missing: Any) -> None:
    artifacts = _sound()
    target = artifacts["continuity"]
    keys = (missing,) if isinstance(missing, str) else missing
    for k in keys[:-1]:
        target = target[k]
    del target[keys[-1]]
    with pytest.raises(cc.MissingEvidenceError, match="continuity"):
        cv.decide(artifacts, violations=[])


# ---------------------------------------------------------------------------
# Revue Fin (3) — la fenêtre du comparateur d'évaluation est recoupée à [T, fin]
# ---------------------------------------------------------------------------

WINDOW_2000 = {"start": "2000-01-01T00:00:00+00:00", "end": "2001-01-01T00:00:00+00:00"}


def test_revue_Fin_3_fenetre_2000_2001_declaree_comparable_est_une_violation_jamais_valide(
    tmp_path: Path,
) -> None:
    """Reproduction d'Astra : tests § C.5 tous vrais sur une fenêtre 2000–2001 — la fenêtre fait
    partie de la comparabilité recalculée ; déclarée `window_ok` alors qu'elle diffère de
    [T, fin] = contradiction → violation, `chain.verified` ne reste pas vrai."""
    artifacts = _sound()
    artifacts["continuity"]["comparator"]["window"]["declared"] = dict(WINDOW_2000)
    outcome, violations = _never_valide(artifacts)
    assert any("window_ok" in v for v in violations), violations
    assert isinstance(outcome, cv.Decision) and outcome.reason == "E_NO_BENCHMARK"
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False


def test_revue_Fin_3_fenetre_discordante_coherente_est_E_NO_BENCHMARK_sans_violation(
    tmp_path: Path,
) -> None:
    artifacts = _sound()
    comp = artifacts["continuity"]["comparator"]
    comp["window"]["declared"] = dict(WINDOW_2000)
    comp["tests"]["window_ok"] = False
    comp["state"] = "FAILED"
    artifacts["continuity"]["benchmark_comparable"] = False
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert violations == [] and decision.issue == cc.ISSUE_INCONCLUSIF
    assert decision.reason == "E_NO_BENCHMARK"
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 0
    assert cc.read_json(tmp_path / "verdict.json")["raison"] == "E_NO_BENCHMARK"


def test_revue_Fin_3_fenetre_attendue_differente_de_la_fenetre_d_evaluation_est_une_violation() -> (
    None
):
    artifacts = _sound()
    artifacts["continuity"]["comparator"]["window"]["expected"] = dict(WINDOW_2000)
    _, violations = _never_valide(artifacts)
    assert any("comparator.window.expected" in v for v in violations), violations


@pytest.mark.parametrize(
    "missing",
    [
        ("comparator", "window"),
        ("comparator", "window", "declared"),
        ("comparator", "tests", "window_ok"),
    ],
)
def test_revue_Fin_3_fenetre_du_comparateur_manquante_est_une_erreur_d_entree(missing: Any) -> None:
    artifacts = _sound()
    target = artifacts["continuity"]
    for k in missing[:-1]:
        target = target[k]
    del target[missing[-1]]
    with pytest.raises(cc.MissingEvidenceError, match="continuity.comparator"):
        cv.decide(artifacts, violations=[])


def test_revue_Fin_3_chain_fenetre_2000_2001_ne_valide_jamais(tmp_path: Path) -> None:
    """De bout en bout : le comparateur d'évaluation déclaré sur 2000–2001, tests vrais, comparable
    vrai → la continuité le classe FAILED (fenêtre ≠ [T, fin]), le verdict rend E_NO_BENCHMARK."""
    w = _chain_world(tmp_path)
    pair = cc.read_json(w["evaluation"])["pair"]
    cc.write_json(w["benchmark_eval"], fx.benchmark_eval(pair, window=dict(WINDOW_2000)))
    assert cv.main(_chain_argv(w)) == 0
    continuity = cc.read_json(w["out"] / "continuity.json")
    assert continuity["comparator"]["state"] == "FAILED"
    assert continuity["comparator"]["tests"]["window_ok"] is False
    assert continuity["benchmark_comparable"] is False
    payload = cc.read_json(w["out"] / "verdict.json")
    assert payload["verdict"] == cc.ISSUE_INCONCLUSIF and payload["raison"] == "E_NO_BENCHMARK"
    assert payload["verdict"] != cc.ISSUE_VALIDE


# ---------------------------------------------------------------------------
# Revue Fin (4) — contrat de cohérence interne de chaque amont dans verify_chain
# ---------------------------------------------------------------------------


def test_revue_Fin_4_entry_ok_vrai_sans_refus_avec_exit_code_2_est_une_violation_jamais_valide(
    tmp_path: Path,
) -> None:
    """Reproduction d'Astra : `ok=true, refusal=null, exit_code=2` — trois champs qui ne peuvent
    pas venir du même run ; jamais « validé », jamais `chain.verified=true`."""
    artifacts = _sound()
    artifacts["entry"].update({"ok": True, "refusal": None, "exit_code": 2})
    raws, paths = _raws_and_paths(tmp_path, artifacts)
    violations, checks = cv.verify_chain(raws, paths)
    assert any("entry" in v and "exit_code" in v for v in violations), violations
    assert any(c["check"] == "entry.coherence" and c["ok"] is False for c in checks)
    assert cv.main(_write_cli_inputs(tmp_path / "cli", artifacts)) == 1
    payload = cc.read_json(tmp_path / "cli" / "verdict.json")
    assert payload["invalide"] is True and payload["verdict"] is None
    assert payload["chain"]["verified"] is False


@pytest.mark.parametrize("artifact", ["anchor", "selection", "continuity"])
@pytest.mark.parametrize(
    "contradiction",
    [
        {"ok": True, "exit_code": 1},
        {"ok": True, "exit_code": 2},
        {"ok": True, "invalide": True, "exit_code": 0},
        {"ok": False, "exit_code": 0},
        {"ok": False, "invalide": True, "exit_code": 2},
    ],
    ids=["ok_exit1", "ok_exit2", "ok_invalide_exit0", "ko_exit0", "invalide_exit2"],
)
def test_revue_Fin_4_amont_incoherent_est_une_violation_code_1(
    tmp_path: Path, artifact: str, contradiction: dict[str, Any]
) -> None:
    artifacts = _sound()
    artifacts[artifact].update(contradiction)
    raws, paths = _raws_and_paths(tmp_path, artifacts)
    violations, checks = cv.verify_chain(raws, paths)
    assert any(v.startswith(f"chaîne : {artifact}.coherence") for v in violations), violations
    assert cv.main(_write_cli_inputs(tmp_path / "cli", artifacts)) == 1
    payload = cc.read_json(tmp_path / "cli" / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False


@pytest.mark.parametrize(
    "contradiction",
    [
        {
            "ok": False,
            "exit_code": 0,
            "refusal": {
                "scope": "run",
                "reason": "R0_INVALID_RUN",
                "assertion": "I-A.0",
                "detail": "x",
            },
        },
        {"ok": False, "invalide": False, "exit_code": 2, "refusal": None},
        {"ok": True, "exit_code": 0, "invalide": True},
    ],
    ids=["refus_exit0", "exit2_sans_refus", "ok_invalide"],
)
def test_revue_Fin_4_entry_incoherente_est_une_violation_jamais_un_refus(
    tmp_path: Path, contradiction: dict[str, Any]
) -> None:
    artifacts = _sound()
    artifacts["entry"].update(contradiction)
    code = cv.main(_write_cli_inputs(tmp_path, artifacts))
    assert code == 1, "une contradiction interne est une violation, pas un refus silencieux"
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False
    assert any("entry.coherence" in v for v in payload["violations"])


def test_revue_Fin_4_un_refus_d_entree_coherent_garde_son_traitement(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["entry"].update(
        {
            "ok": False,
            "invalide": False,
            "exit_code": 2,
            "refusal": {
                "scope": "artefact",
                "reason": "D_WARMUP_PREFIX",
                "assertion": "I-A.8",
                "detail": "D2",
            },
        }
    )
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


@pytest.mark.parametrize("artifact", ["entry", "anchor", "selection", "continuity"])
def test_revue_Fin_4_exit_code_hors_liste_close_est_une_erreur_d_entree(
    tmp_path: Path, artifact: str
) -> None:
    artifacts = _sound()
    artifacts[artifact]["exit_code"] = 3
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


# ---------------------------------------------------------------------------
# Revue Fin (6) — balayage : statuts dérivés des listes de sélection ; identité, paire, portée et
# fenêtre de continuité dérivées de l'évaluation et de l'ancre
# ---------------------------------------------------------------------------


def _other_identity() -> str:
    return cc.candidate_identity("s", "SOL/USDC", {"a": 2})


def test_revue_Fin_6_retenue_differente_de_la_tete_du_classement_est_une_violation(
    tmp_path: Path,
) -> None:
    artifacts = _sound()
    other = _other_identity()
    sel = artifacts["selection"]
    sel["admissible"] = [other, sel["retained"]["identity"]]
    sel["survivors"] = list(sel["admissible"])
    sel["ranking"] = [other, sel["retained"]["identity"]]  # la tête n'est pas la retenue déclarée
    _, violations = _never_valide(artifacts)
    assert any("selection.retained" in v and "ranking" in v for v in violations), violations
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1


def test_revue_Fin_6_abstention_declaree_avec_un_classement_non_vide_est_une_violation() -> None:
    artifacts = _sound()
    sel = artifacts["selection"]
    sel.update({"status": "ABSTENTION", "reason": "A_BELOW_FLOOR", "retained": None})
    # listes laissées pleines : le classement dit qu'une configuration est retenue
    _, violations = _never_valide(artifacts)
    assert any("selection.retained" in v for v in violations), violations
    assert any("selection.reason" in v for v in violations), violations


@pytest.mark.parametrize(
    ("reason", "admissible", "survivors"),
    [
        ("A_NO_ADMISSIBLE_CANDIDATE", ["x"], []),
        ("A_BELOW_FLOOR", [], []),
        (None, ["x"], []),
    ],
    ids=[
        "aucun_admissible_mais_liste_pleine",
        "sous_plancher_sans_admissible",
        "sans_raison_sans_survivant",
    ],
)
def test_revue_Fin_6_la_raison_d_abstention_derive_des_listes(
    reason: str | None, admissible: list[str], survivors: list[str]
) -> None:
    artifacts = _sound()
    sel = artifacts["selection"]
    sel.update(
        {
            "status": "ABSTENTION",
            "reason": reason,
            "retained": None,
            "admissible": admissible,
            "survivors": survivors,
            "ranking": [],
        }
    )
    _, violations = _never_valide(artifacts)
    assert any("selection.reason" in v for v in violations), violations


def test_revue_Fin_6_classement_qui_n_est_pas_une_permutation_des_survivants() -> None:
    artifacts = _sound()
    sel = artifacts["selection"]
    sel["ranking"] = [sel["retained"]["identity"], _other_identity()]
    _, violations = _never_valide(artifacts)
    assert any("selection.ranking" in v and "survivors" in v for v in violations), violations


@pytest.mark.parametrize("missing", ["admissible", "survivors", "ranking"])
def test_revue_Fin_6_listes_de_selection_manquantes_sont_une_erreur_d_entree(
    tmp_path: Path, missing: str
) -> None:
    artifacts = _sound()
    del artifacts["selection"][missing]
    with pytest.raises(cc.MissingEvidenceError, match=f"selection.{missing}"):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_revue_Fin_6_identite_de_continuite_derivee_de_l_evaluation(tmp_path: Path) -> None:
    """`continuity.identity` se dérive de `evaluation.{strategy, pair, params}` : un désaccord est
    une violation, et c'est l'identité **dérivée** qui est comparée à la retenue."""
    artifacts = _sound()
    artifacts["evaluation"]["params"] = {"a": 2}
    violations: list[str] = []
    with pytest.raises(cc.EntryRefusedError, match="configuration retenue"):
        cv.decide(artifacts, violations=violations)
    assert any("continuity.identity" in v for v in violations), violations
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1, "la violation prime sur le refus"


@pytest.mark.parametrize(
    ("key", "value", "fragment"),
    [("pair", "SOL/USDC", "continuity.pair"), ("synthetic", False, "continuity.synthetic")],
)
def test_revue_Fin_6_paire_et_portee_de_continuite_recoupees_a_l_evaluation(
    key: str, value: Any, fragment: str
) -> None:
    artifacts = _sound()
    artifacts["continuity"][key] = value
    _, violations = _never_valide(artifacts)
    assert any(fragment in v for v in violations), violations


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a["anchor"].__setitem__("anchor", (fx.ANCHOR + timedelta(days=1)).isoformat()),
        lambda a: a["anchor"]["window"].__setitem__(
            "end", (fx.WINDOW_END + timedelta(days=1)).isoformat()
        ),
    ],
    ids=["ancre_deplacee", "fin_deplacee"],
)
def test_revue_Fin_6_fenetre_d_evaluation_derivee_de_l_ancre(mutate: Any) -> None:
    artifacts = _sound()
    mutate(artifacts)
    _, violations = _never_valide(artifacts)
    assert any("evaluation_window" in v and "anchor" in v for v in violations), violations


@pytest.mark.parametrize("missing", [("anchor",), ("window",), ("window", "end")])
def test_revue_Fin_6_ancre_sans_date_ou_fenetre_est_une_erreur_d_entree(
    missing: tuple[str, ...],
) -> None:
    artifacts = _sound()
    target = artifacts["anchor"]
    for k in missing[:-1]:
        target = target[k]
    del target[missing[-1]]
    with pytest.raises(cc.MissingEvidenceError, match="anchor"):
        cv.decide(artifacts, violations=[])


# ---------------------------------------------------------------------------
# Revue Fin 2 (1), passe interne — lecture stricte complète des cinq entrées avant tout chemin
# ---------------------------------------------------------------------------

OUT_OF_LIST_CONTINUITY: list[tuple[str, Any]] = [
    ("c4_DECLARED", lambda c: c["clauses"]["c4"].__setitem__("state", "DECLARED")),
    ("c4_NOT_VERIFIABLE", lambda c: c["clauses"]["c4"].__setitem__("state", "NOT_VERIFIABLE")),
    ("c2_VERIFIED", lambda c: c["clauses"]["c2"].__setitem__("state", "VERIFIED")),
    ("c1_VERIFIED", lambda c: c["clauses"]["c1"].__setitem__("state", "VERIFIED")),
    ("c3_DECLARED", lambda c: c["clauses"]["c3"].__setitem__("state", "DECLARED")),
    ("c5_VERIFIED", lambda c: c["clauses"]["c5"].__setitem__("state", "VERIFIED")),
    ("stamp_cell_DECLARED", lambda c: c["stamp_cell"].__setitem__("state", "DECLARED")),
    ("comparator_NOT_VERIFIABLE", lambda c: c["comparator"].__setitem__("state", "NOT_VERIFIABLE")),
    ("state_OK", lambda c: c.__setitem__("state", "OK")),
    ("clauses_vides", lambda c: c.__setitem__("clauses", {})),
    (
        "clause_c6_inconnue",
        lambda c: c["clauses"].__setitem__("c6", {"state": "VERIFIED", "detail": "forgé"}),
    ),
]


@pytest.mark.parametrize(
    ("label", "mutate"), OUT_OF_LIST_CONTINUITY, ids=[name for name, _ in OUT_OF_LIST_CONTINUITY]
)
def test_revue_Fin2_1_l_abstention_lit_la_continuite_strictement(
    tmp_path: Path, label: str, mutate: Any
) -> None:
    """La norme ne restreint pas la liste close au chemin retenu : « hors liste close → code 2, rien
    publié … dans le verdict (consommation) ». Une abstention lit `continuity.json` en entier, comme
    toute entrée obligatoire (constat de la passe interne)."""
    artifacts = _sound()
    _abstain(artifacts)
    mutate(artifacts["continuity"])
    with pytest.raises(cc.MissingEvidenceError, match="continuity"):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2, label
    assert not (tmp_path / "verdict.json").exists()


def test_revue_Fin2_1_l_abstention_recoupe_la_continuite_et_porte_continuite_tiret(
    tmp_path: Path,
) -> None:
    """Abstention + continuité contredite (c4 VERIFIED, résumé faux) → violation, diagnostic 1 ;
    abstention + continuité cohérente → 0, la chaîne porte `continuite=-` (aucune configuration
    retenue, l'évaluation n'est pas celle d'une retenue)."""
    artifacts = _sound()
    _abstain(artifacts)
    argv = _write_cli_inputs(tmp_path / "ok", artifacts)
    assert cv.main(argv) == 0
    payload = cc.read_json(tmp_path / "ok" / "verdict.json")
    assert payload["continuite"] is None and " | continuite=- | " in payload["verdict_string"]
    artifacts["continuity"]["warmup_anchor_ok"] = False  # contredit c4 VERIFIED
    violations: list[str] = []
    decision = cv.decide(artifacts, violations=violations)
    assert decision.issue == cc.ISSUE_INCONCLUSIF and decision.continuity_state is None
    assert any("warmup_anchor_ok" in v for v in violations)
    assert cv.main(_write_cli_inputs(tmp_path / "ko", artifacts)) == 1
    assert cc.read_json(tmp_path / "ko" / "verdict.json")["invalide"] is True


@pytest.mark.parametrize(
    ("path", "mutate_eval"),
    [
        ("abstention", lambda e: e["metrics"].pop("delta_dd")),
        ("abstention", lambda e: e["replications"]["21:dd"].pop("bound")),
        ("abstention", lambda e: e.__setitem__("B", 400)),
        ("F_NOT_ESTIMABLE", lambda e: e["metrics"].pop("delta_dd")),
        ("F_NOT_ESTIMABLE", lambda e: e["replications"]["21:dd"].pop("bound")),
        ("D_WARMUP_ANCHOR", lambda e: e["metrics"].pop("net_pnl")),
    ],
    ids=[
        "abst_metrique",
        "abst_bornes",
        "abst_B",
        "notest_metrique",
        "notest_bornes",
        "warmup_metrique",
    ],
)
def test_revue_Fin2_1_les_portes_et_les_bornes_sont_lues_avant_tout_retour_anticipe(
    tmp_path: Path, path: str, mutate_eval: Any
) -> None:
    """Défaut 5 appliqué à `decide()` lui-même : une raison run (abstention, F_NOT_ESTIMABLE,
    D_WARMUP_ANCHOR) ne dispense pas de lire strictement `metrics`, `bounds` et `B` — une preuve
    manquante reste un code 2 (ou un refus R0 pour `B`), jamais un inconclusif publié."""
    artifacts = _sound()
    if path == "abstention":
        _abstain(artifacts)
    elif path == "F_NOT_ESTIMABLE":
        _flat(artifacts)
    else:
        _coherent_continuity(artifacts, "c4", "FAILED")
    mutate_eval(artifacts["evaluation"])
    with pytest.raises((cc.MissingEvidenceError, cc.EntryRefusedError)):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


# ---------------------------------------------------------------------------
# Revue Fin 2 (2) — violation avant UndefinedIssue : une contradiction constatée est un
# diagnostic code 1, même quand c3 est en échec ; le refus 2 reste réservé au cas cohérent
# ---------------------------------------------------------------------------


def _c3_failed(artifacts: dict[str, Any]) -> None:
    c = artifacts["continuity"]
    c["clauses"]["c3"] = {"state": "FAILED", "detail": "liquidation absente (moteur signal)"}
    c["state"] = "FAILED"
    c["liquidation_normalised"] = False


def test_revue_Fin2_2_c3_FAILED_et_resume_normalise_vrai_est_un_diagnostic_code_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reproduction d'Astra : c3=FAILED + liquidation_normalised=true — contradiction déclaré/dérivé
    → diagnostic code 1 (invalide: true, violations listées), pas le refus 2 de la convention
    datée. Appui : revue Fin 2, item 2 (précédence fixée ; précédent du chantier 0 pour un refus
    après violation) ; § I.1 l.15 (« c'est une violation, pas un résultat »)."""
    artifacts = _sound()
    _c3_failed(artifacts)
    artifacts["continuity"]["liquidation_normalised"] = True  # ment sur la clause en échec
    violations: list[str] = []
    with pytest.raises(cc.UndefinedIssueError):
        cv.decide(artifacts, violations=violations)
    assert any("liquidation_normalised" in v for v in violations)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["verdict"] is None
    assert any("liquidation_normalised" in v for v in payload["violations"])
    assert any("issue non définie" in v for v in payload["violations"]), (
        "la convention datée est consignée dans le diagnostic, pas exécutée"
    )
    assert "ISSUE NON DEFINIE" not in capsys.readouterr().err


def test_revue_Fin2_2_c3_FAILED_et_agregat_menteur_VERIFIED_est_un_diagnostic_code_1(
    tmp_path: Path,
) -> None:
    """Reproduction d'Astra (item 2) : c3 en échec, résumé cohérent, agrégat déclaré VERIFIED →
    contradiction déclaré/dérivé (dérivé FAILED, précédence § 6.4) → diagnostic code 1, jamais le
    refus 2 — « le refus 2 reste réservé au cas cohérent »."""
    artifacts = _sound()
    _c3_failed(artifacts)
    artifacts["continuity"]["state"] = "VERIFIED"
    violations: list[str] = []
    with pytest.raises(cc.UndefinedIssueError):
        cv.decide(artifacts, violations=violations)
    assert any("continuity.state" in v for v in violations)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False


def test_revue_Fin2_2_c3_FAILED_coherent_reste_le_refus_2_de_la_convention_datee(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le cas que la convention datée du 21/09 couvre : c3 en échec, résumés et agrégat concordants
    → UndefinedIssueError, code 2, rien publié (§ 6.1, conduite (b))."""
    artifacts = _sound()
    _c3_failed(artifacts)
    violations: list[str] = []
    with pytest.raises(cc.UndefinedIssueError):
        cv.decide(artifacts, violations=violations)
    assert violations == []
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()
    assert "ISSUE NON DEFINIE" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Revue Fin 2 (3) — chain.verified : intégrité mécanique de la chaîne, pas la qualité de l'issue
# ---------------------------------------------------------------------------


def test_revue_Fin2_3_chain_verified_vrai_avec_un_inconclusif_E_NO_BENCHMARK(
    tmp_path: Path,
) -> None:
    """Définition fixée : `chain.verified` = codes de succès des amonts, cohérence interne de chaque
    amont, empreintes concordantes. Un inconclusif E_NO_BENCHMARK sur des artefacts intègres est
    `verified: true` — l'issue économique se lit dans verdict/raison, pas dans verified."""
    artifacts = _sound()
    comp = artifacts["continuity"]["comparator"]
    comp["tests"]["ff_ok"] = False
    comp["state"] = "FAILED"
    artifacts["continuity"]["benchmark_comparable"] = False
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 0
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["verdict"] == cc.ISSUE_INCONCLUSIF and payload["raison"] == "E_NO_BENCHMARK"
    assert payload["chain"]["verified"] is True
    assert all(c["ok"] for c in payload["chain"]["checks"])


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        (
            "violation_hors_chaine_estimabilite",
            lambda a: a["evaluation"].__setitem__("estimability", {"ok": False}),
        ),
        (
            "violation_hors_chaine_resume",
            lambda a: a["continuity"].__setitem__("warmup_anchor_ok", False),
        ),
        ("violation_de_chaine_empreinte", "empreinte"),
        ("violation_de_chaine_coherence", lambda a: a["selection"].__setitem__("exit_code", 2)),
        (
            "violation_de_chaine_protocole",
            lambda a: a["anchor"].__setitem__(
                "protocole", {"path": cc.PROTOCOL_RELPATH, "sha256": "f" * 64}
            ),
        ),
        (
            "violation_hors_chaine_non_fini",
            lambda a: a["evaluation"]["replications"]["21:dd"]["delta_stars"].__setitem__(
                3, float("nan")
            ),
        ),
    ],
    ids=["estimabilite", "resume", "empreinte", "coherence", "protocole", "non_fini"],
)
def test_revue_Fin2_3_chain_verified_faux_sur_toute_violation(
    tmp_path: Path, label: str, mutate: Any
) -> None:
    """Sens « faux » de la définition (revue Fin 2, item 3 : « verified: false sur toute violation
    ou refus ») : chaîne (empreinte, cohérence, protocole) comme hors chaîne (estimabilité, résumé,
    non-fini fourni) — un diagnostic (§ I.1 l.15) ne porte jamais `verified: true`. Vert avant le
    correctif 2 : ce test fixe la définition, il ne mord pas sur un défaut."""
    artifacts = _sound()
    if mutate == "empreinte":
        argv = _write_cli_inputs(tmp_path, artifacts)
        sel = cc.read_json(tmp_path / "selection.json")
        sel["inputs_sha256"]["anchor"] = "0" * 64
        cc.write_json(tmp_path / "selection.json", sel)
    else:
        mutate(artifacts)
        argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 1, label
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False, label


def test_revue_Fin2_3_un_refus_ne_publie_rien_donc_aucun_verified(tmp_path: Path) -> None:
    """Item 3, moitié « ou refus » : un refus sans violation ne publie rien (chantier 0 : code 2,
    rien d'écrit), il n'y a donc aucun `verified` à porter. Vert avant : fixe la définition."""
    artifacts = _sound()
    artifacts["selection"].update({"ok": False, "invalide": False, "exit_code": 2})
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_revue_Fin2_3_un_refus_apres_violation_publie_un_diagnostic_verified_faux(
    tmp_path: Path,
) -> None:
    """Item 3, moitié « ou refus », le seul refus qui publie : consigné après une violation
    (chantier 0), le diagnostic porte `verified: false`."""
    artifacts = _sound()
    artifacts["entry"].update({"ok": False, "refusal": None})  # incohérent (exit 0) puis refus R0
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False
    assert any("refus d'entrée constaté après violation" in v for v in payload["violations"])


def test_revue_Fin2_3_chain_verified_en_mode_chain_avec_E_NO_BENCHMARK(tmp_path: Path) -> None:
    """Sens « vrai » en mode chain (item 3) : les cinq étapes ont rendu 0, les enveloppes sont
    cohérentes, les empreintes concordent ; l'issue est un inconclusif E_NO_BENCHMARK (fenêtre du
    comparateur 2000–2001) — `verified: true`. Vert avant : fixe la définition."""
    w = _chain_world(tmp_path)
    pair = cc.read_json(w["evaluation"])["pair"]
    cc.write_json(w["benchmark_eval"], fx.benchmark_eval(pair, window=dict(WINDOW_2000)))
    assert cv.main(_chain_argv(w)) == 0
    payload = cc.read_json(w["out"] / "verdict.json")
    assert payload["raison"] == "E_NO_BENCHMARK" and payload["chain"]["verified"] is True
    assert payload["chain"]["mode"] == "chain"


# ---------------------------------------------------------------------------
# Revue Fin 2 (2), passe interne — une contradiction d'amont consignée n'est jamais perdue
# ---------------------------------------------------------------------------


def test_revue_Fin2_2_une_contradiction_d_amont_n_est_pas_perdue_par_un_refus_ulterieur(
    tmp_path: Path,
) -> None:
    """Constat de la passe interne : `verify_chain` consignait les contradictions dans une liste
    locale ; un `require_upstream_ok` levant ensuite sur un autre amont cohérent en échec faisait
    sortir 2 sans diagnostic. Chantier 0 : refus après violation → consigné au diagnostic, code 1 ;
    docstring de `verify_chain` : « une contradiction … est une violation, code 1 »."""
    artifacts = _sound()
    artifacts["entry"].update({"ok": True, "invalide": False, "exit_code": 1})  # contradiction
    artifacts["selection"].update(
        {"ok": False, "invalide": False, "exit_code": 2}
    )  # échec cohérent
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["invalide"] is True and payload["chain"]["verified"] is False
    assert any("entry.coherence" in v for v in payload["violations"])
    assert any("refus d'entrée constaté après violation" in v for v in payload["violations"])
    assert any(
        c["check"] == "entry.coherence" and c["ok"] is False for c in payload["chain"]["checks"]
    )


def test_revue_Fin2_2_une_preuve_absente_apres_violation_sort_2_et_la_violation_est_dite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Chantier 0 : absent → 2, rien d'écrit — la norme est muette sur une violation constatée avant
    (consigné au rapport, question ouverte). Conduite retenue : rien n'est publié, mais rien n'est
    perdu — les violations déjà constatées sont dites sur stderr avec l'erreur d'entrée."""
    artifacts = _sound()
    argv = _write_cli_inputs(tmp_path, artifacts)
    sel = cc.read_json(tmp_path / "selection.json")
    sel["inputs_sha256"]["anchor"] = "0" * 64  # discordance consignée d'abord
    del sel["inputs_sha256"]["entry"]  # puis preuve absente
    cc.write_json(tmp_path / "selection.json", sel)
    assert cv.main(argv) == 2
    assert not (tmp_path / "verdict.json").exists()
    err = capsys.readouterr().err
    assert "ENTREE INVALIDE" in err and "VIOLATION chaîne : selection.anchor" in err


def test_revue_Fin2_2_le_diagnostic_ne_dit_pas_rien_publie(tmp_path: Path) -> None:
    """Un artefact publié n'affirme pas de lui-même « code 2, rien publié » : le diagnostic consigne
    le motif de l'issue non définie, pas la conduite (b) qui ne s'est pas appliquée."""
    artifacts = _sound()
    _c3_failed(artifacts)
    artifacts["continuity"]["liquidation_normalised"] = True
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    undefined = [v for v in payload["violations"] if "issue non définie" in v]
    assert undefined and all("rien publié" not in v for v in undefined), undefined
