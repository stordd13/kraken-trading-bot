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
from functools import cache
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
import c3_continuity as cn
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
    return cc.paired_delta_stars(cfg, bch, idx, float(N_DAYS))


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


def _artifacts(
    *,
    returns_config,
    returns_bench,
    metrics: dict[str, Any],
    bounds: dict[str, float] | None = None,
    provenance: str = cc.PROVENANCE_CLEAN,
) -> dict[str, dict[str, Any]]:
    deltas, discarded = _bootstrap(returns_config, returns_bench)
    if bounds is None:
        bounds = {
            f"{length}:{matching}": 1.0 for length in cc.BLOCK_LENGTHS for matching in cc.MATCHINGS
        }
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
                },
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
            "returns_config": list(returns_config),
            "delta_stars": [float(x) for x in deltas],
            "discarded": discarded,
            "B": cc.BOOTSTRAP_B,
            "metrics": metrics,
            "bounds": bounds,
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
        metrics={"net_pnl": 0.0, "cagr_pct": 0.0, "delta_dd": -1.5},
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
        returns_config=_varying(7),
        returns_bench=cash,
        metrics={"net_pnl": 42.0, "cagr_pct": 5.0, "delta_dd": 1.2},
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
        metrics={"net_pnl": -30.0, "cagr_pct": -1.0, "delta_dd": -2.0},
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
        metrics={"net_pnl": 0.0, "cagr_pct": 0.0, "delta_dd": 0.0},
    )
    assert len(artifacts["evaluation"]["delta_stars"]) == cc.BOOTSTRAP_B
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
        metrics={"net_pnl": 42.0, "cagr_pct": 5.0, "delta_dd": 1.2},
        provenance=provenance,
    )
    decision = cv.decide(artifacts, violations=[])
    assert decision.issue == cc.ISSUE_INCONCLUSIF
    assert decision.reason == "P_PROVENANCE"
    assert decision.issue not in (cc.ISSUE_VALIDE, cc.ISSUE_REFUTE)


def test_la_chaine_est_identique_octet_pour_octet_sur_deux_executions() -> None:
    """§ 0.6 : deux personnes, mêmes artefacts, même chaîne. Aucun horodatage dedans."""
    artifacts = _artifacts(
        returns_config=_varying(7),
        returns_bench=[0.0] * N_DAYS,
        metrics={"net_pnl": 42.0, "cagr_pct": 5.0, "delta_dd": 1.2},
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
        returns_config=_varying(7),
        returns_bench=[0.0] * N_DAYS,
        metrics={"net_pnl": 42.0, "cagr_pct": 5.0, "delta_dd": 1.2},
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
    artifacts["evaluation"]["bounds"] = {k: float("inf") for k in artifacts["evaluation"]["bounds"]}
    with pytest.raises(cc.InvalidValueError, match="non finie"):
        cv.decide(artifacts, violations=[])


def test_estimabilite_declaree_contredite_par_les_series_est_une_violation() -> None:
    """Défaut reproduit : le statut déclaré était cru, et une inactive repartait en `réfuté`."""
    flat = [0.0] * N_DAYS
    artifacts = _artifacts(
        returns_config=flat,
        returns_bench=_varying(11),
        metrics={"net_pnl": 0.0, "cagr_pct": 0.0, "delta_dd": -1.5},
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
    artifacts["entry"].update({"ok": False, "refusal": _REFUSAL_D2})
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
        returns_config=_varying(7),
        returns_bench=[0.0] * N_DAYS,
        metrics={"net_pnl": 42.0, "cagr_pct": 5.0, "delta_dd": 1.2},
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
    artifacts["selection"]["retained"] = None
    artifacts["selection"]["reason"] = "A_NO_ADMISSIBLE_CANDIDATE"
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
    ("evaluation", "delta_stars"),
    ("evaluation", "discarded"),
    ("evaluation", "B"),
    ("evaluation", "metrics"),
    ("evaluation", "metrics", "net_pnl"),
    ("evaluation", "metrics", "cagr_pct"),
    ("evaluation", "metrics", "delta_dd"),
    ("evaluation", "bounds"),
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
        (("evaluation", "delta_stars"), {"a": 1}),
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
    artifacts["evaluation"]["delta_stars"][3] = float("nan")
    with pytest.raises(cc.InvalidValueError, match=r"delta_stars\[3\]"):
        cv.decide(artifacts, violations=[])


def test_bornes_incompletes_refusent_l_entree() -> None:
    artifacts = _sound()
    keys = sorted(artifacts["evaluation"]["bounds"])
    artifacts["evaluation"]["bounds"].pop(keys[0])
    with pytest.raises(cc.MissingEvidenceError, match="exactement"):
        cv.decide(artifacts, violations=[])


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
        pytest.param(lambda a: a["evaluation"].pop("discarded"), id="discarded absent"),
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
            lambda a: a["evaluation"].__setitem__(
                "bounds", {k: float("inf") for k in a["evaluation"]["bounds"]}
            ),
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
        pytest.param(lambda a: a["evaluation"].__setitem__("discarded", 11), id="B incohérent"),
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
        metrics={"net_pnl": 0.0, "cagr_pct": 0.0, "delta_dd": -1.5},
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
    artifacts["evaluation"].pop("discarded")
    with pytest.raises(cc.MissingEvidenceError, match="discarded"):
        cv.decide(artifacts, violations=[])


def test_discarded_incoherent_avec_B_est_une_violation() -> None:
    """`B` déclaré, `B_effectif` recalculé : un désaccord est une violation (§ I.1, ligne 15)."""
    artifacts = _sound()
    artifacts["evaluation"]["discarded"] = 11  # B_effectif 10 000 + 11 != B 10 000
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
    a["evaluation"]["delta_stars"] = a["evaluation"]["delta_stars"][:n_deltas]
    a["evaluation"]["discarded"] = discarded
    if nan_in_deltas:
        a["evaluation"]["delta_stars"][3] = float("nan")


#: (B, len(delta_stars), discarded, non-fini dans delta_stars, code CLI, issue, raison)
MATRIX_B = [
    pytest.param(
        10_000, 9_990, 10, False, 0, cc.ISSUE_VALIDE, None, id="10000/9990/10 -> 0 témoin sain"
    ),
    pytest.param(
        10_000,
        9_989,
        11,
        False,
        0,
        cc.ISSUE_INCONCLUSIF,
        "F_NOT_ESTIMABLE",
        id="10000/9989/11 -> 0 F_NOT_ESTIMABLE, compte cohérent",
    ),
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
    assert len(artifacts["evaluation"]["delta_stars"]) == n_deltas
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
    decision = cv.decide(artifacts, violations=violations)
    if code == 1:
        assert violations and any("B déclaré" in v for v in violations)
        return
    assert violations == []
    assert decision.issue == issue
    assert decision.reason == reason
    est = decision.estimability
    assert est is not None
    assert (est["B"], est["B_effectif"], est["discarded"]) == (b, n_deltas, discarded)


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
    payload = cc.read_json(out)
    if code == 1:
        assert payload["invalide"] is True
        assert payload["verdict"] is None
        assert payload["verdict_string"] is None
        assert any("B déclaré" in v for v in payload["violations"])
        return
    assert payload["invalide"] is False
    assert payload["verdict"] == issue
    assert payload["raison"] == reason
    assert payload["estimabilite"]["B"] == b
    assert payload["estimabilite"]["B_effectif"] == n_deltas
    assert payload["estimabilite"]["discarded"] == discarded


# ---------------------------------------------------------------------------
# Item 3 — la table I.1, ligne à ligne. C'est ce test qui empêchera la prochaine divergence.
# ---------------------------------------------------------------------------


def _abstention(reason: str) -> Any:
    def mutate(a: dict[str, Any]) -> None:
        a["selection"].update(
            {
                "status": "ABSTENTION",
                "reason": reason,
                "provenance": a["anchor"]["universe_provenance"],
                "retained": None,
            }
        )

    return mutate


def _all_discarded(a: dict[str, Any]) -> None:
    a["evaluation"]["delta_stars"] = []
    a["evaluation"]["discarded"] = cc.BOOTSTRAP_B


#: (ligne, fixture, issue attendue, raison attendue, code CLI attendu, artefact écrit ?, chaîne citable ?)
TABLE_I1 = [
    pytest.param(1, lambda a: None, cc.ISSUE_VALIDE, None, 0, True, True, id="L1 entrée conforme"),
    pytest.param(
        2,
        lambda a: a["entry"].update({"ok": False, "refusal": _REFUSAL_R0}),
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
        _all_discarded,
        cc.ISSUE_INCONCLUSIF,
        "F_NOT_ESTIMABLE",
        0,
        True,
        True,
        id="L13 estimabilité (toutes réplications écartées, compte cohérent)",
    ),
    pytest.param(
        14,
        lambda a: a["evaluation"].__setitem__(
            "bounds", dict.fromkeys(a["evaluation"]["bounds"], -0.5)
        ),
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
        all(c["ok"] for c in payload["chain"]["checks"]) and len(payload["chain"]["checks"]) == 13
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
    assert payload["chain"]["mode"] == "verdict" and payload["chain"]["verified"] is True


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


@pytest.mark.parametrize("how", ["clause_c3_FAILED_resume_vrai", "clause_et_resume_coherents"])
def test_clause_3_en_echec_moteur_signal_a_l_evaluation_issue_non_definie(
    tmp_path: Path, how: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixture « moteur signal à l'évaluation » : liquidation terminale non normalisée. Le texte
    gelé ne définit pas l'issue → `UndefinedIssueError`, code 2, rien d'écrit, message cité.
    L'action se branche sur la **clause** (revue Fin 2) : le résumé, cohérent ou contredit, ne
    change pas la conduite (contredit, il ajoute une violation — testé au § revue Fin 2)."""
    artifacts = _sound()
    artifacts["continuity"]["clauses"]["c3"] = {
        "state": "FAILED",
        "detail": "liquidation absente (moteur signal)",
    }
    artifacts["continuity"]["state"] = "FAILED"
    if how == "clause_et_resume_coherents":
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


def test_la_continuite_d_une_autre_configuration_est_refusee(tmp_path: Path) -> None:
    artifacts = _sound()
    artifacts["continuity"]["identity"] = cc.candidate_identity("s", "SOL/USDC", {"a": 2})
    with pytest.raises(cc.EntryRefusedError, match="configuration retenue"):
        cv.decide(artifacts, violations=[])
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


@pytest.mark.parametrize("state", ["VERIFIED", "DECLARED", "NOT_VERIFIABLE"])
def test_l_etat_agrege_est_porte_par_la_chaine_sans_changer_l_issue(state: str) -> None:
    """Clauses cohérentes avec l'agrégat (c1/c5 portées à l'état voulu, c2 idem) ; l'issue ne
    dépend pas de l'agrégat tant qu'aucune clause n'est FAILED."""
    artifacts = _sound()
    clauses = artifacts["continuity"]["clauses"]
    for key in ("c1", "c2", "c5"):
        clauses[key]["state"] = state
    artifacts["continuity"]["state"] = cn.aggregate_state(
        {k: v["state"] for k, v in clauses.items()}
    )
    assert artifacts["continuity"]["state"] == state
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
    assert violations == [] and len(checks) == 13 and all(c["ok"] for c in checks)


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
    [{"ok": False}, {"invalide": True}, {"exit_code": 1}],
    ids=["ok_faux", "invalide", "exit_code_1"],
)
def test_un_amont_en_echec_enregistre_est_un_refus_rien_ecrit(
    tmp_path: Path, artifact: str, failure: dict[str, Any]
) -> None:
    artifacts = _sound()
    artifacts[artifact].update(failure)
    assert cv.main(_write_cli_inputs(tmp_path, artifacts)) == 2
    assert not (tmp_path / "verdict.json").exists()


def test_une_entree_diagnostic_invalide_est_un_refus(tmp_path: Path) -> None:
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
def test_chain_sur_l_artefact_reel_s_arrete_a_entry_code_2_aucun_verdict(tmp_path: Path) -> None:
    """§ 6.6 (4) : sur données réelles la chaîne s'arrête à `entry` (refus D2) ; aucun chemin réel
    n'atteint le verdict en C3a. L'artefact du rejeu et le registre committé restent intacts."""
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
    assert (out / "anchor.json").exists() and (out / "entry.json").exists()
    entry = cc.read_json(out / "entry.json")
    assert entry["ok"] is False and entry["exit_code"] == 2
    assert entry["refusal"]["reason"] == "D_WARMUP_PREFIX" and entry["n_candidates_d2_failed"] == 96
    for f in ("benchmark.json", "selection.json", "continuity.json", "verdict.json"):
        assert not (out / f).exists(), f
    assert cc.file_sha256(REAL_OBSERVATIONS) == before
    assert cc.file_sha256(REAL_REGISTRY) == registry_before
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


@pytest.mark.parametrize("clause", ["c1", "c2", "c3", "c4", "c5"])
@pytest.mark.parametrize("state", list(cc.CONTINUITY_STATES))
def test_revue_Fin_2_valide_avec_continuite_FAILED_est_inconstructible(
    clause: str, state: str
) -> None:
    """Chaque clause dans chaque état, résumés et agrégat **cohérents** : l'issue suit la table
    § 6.4 et `validé` n'existe qu'avec un agrégat sans FAILED."""
    artifacts = _sound()
    c = artifacts["continuity"]
    c["clauses"][clause]["state"] = state
    states = {k: v["state"] for k, v in c["clauses"].items()}
    c["state"] = cn.aggregate_state(states)
    c["warmup_anchor_ok"] = states["c4"] == "VERIFIED"
    c["liquidation_normalised"] = {
        "VERIFIED": True,
        "NOT_VERIFIABLE": None,
        "FAILED": False,
        "DECLARED": False,
    }[states["c3"]]
    violations: list[str] = []
    try:
        decision = cv.decide(artifacts, violations=violations)
    except cc.EntryRefusedError:
        assert clause in ("c1", "c2", "c5") and state == "FAILED"
        return
    except cc.UndefinedIssueError:
        assert clause == "c3" and state == "FAILED"
        return
    if clause == "c3" and state == "DECLARED":
        # DECLARED n'est pas un état atteignable de c3 (jamais par déclaration) : contradiction
        assert violations, "c3 DECLARED est incohérent avec liquidation_normalised"
        return
    assert violations == [], violations
    assert decision.continuity_state == c["state"]
    if state == "FAILED":
        assert clause == "c4" and decision.reason == "D_WARMUP_ANCHOR"
        assert decision.issue != cc.ISSUE_VALIDE
    elif clause == "c3" and state == "NOT_VERIFIABLE":
        assert decision.issue == cc.ISSUE_VALIDE  # non vérifiable est admissible (§ B)
    else:
        assert decision.issue == cc.ISSUE_VALIDE
    assert (decision.issue == cc.ISSUE_VALIDE) == ("FAILED" not in states.values())


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
