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

import c3_common as cc
import c3_verdict as cv

N_DAYS = 329  # longueur de la fenêtre d'évaluation de l'ancrage déclaré, en jours
B_TEST = 400  # réplications : assez pour que la distribution vive, assez peu pour être rapide
SEED = 20260921


def _bootstrap(returns_config, returns_bench, *, block_length: int = 21, b: int = B_TEST):
    """Le vrai chemin numérique du § F.2 : indices appariés, `Δ*`, réplications écartées."""
    n = len(returns_config)
    rng = np.random.default_rng([SEED, 0, block_length])
    starts = cc.block_start_indices(rng, n, block_length, b)
    idx = cc.block_indices(starts, block_length, n)
    return cc.paired_delta_stars(returns_config, returns_bench, idx, float(N_DAYS))


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
            f"{length}:{matching}": 1.0
            for length in cc.BLOCK_LENGTHS
            for matching in cc.MATCHINGS
        }
    return {
        "entry": {"ok": True, "reason": None},
        "anchor": {"universe_provenance": provenance},
        "selection": {
            "status": "SÉLECTION_VALIDE",
            "reason": None,
            "retained": {"identity": cc.candidate_identity("s", "BTC/USDC", {"a": 1})},
        },
        "continuity": {
            "warmup_anchor_ok": True,
            "benchmark_comparable": True,
            "stamp_same_daily_cell": True,
        },
        "evaluation": {
            "returns_config": list(returns_config),
            "delta_stars": [float(x) for x in deltas],
            "discarded": discarded,
            "metrics": metrics,
            "bounds": bounds,
        },
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
    """§ A.13 E2 : `Δ*` constant **sans** qu'aucun des deux côtés soit déterministe."""
    same = _varying(3)
    deltas, discarded = _bootstrap(same, same)

    assert discarded == 0
    assert len(deltas) == B_TEST
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
    """La conséquence sur l'issue, pas seulement sur le contrôle."""
    same = _varying(3)
    deltas, discarded = _bootstrap(same, same)
    artifacts = _artifacts(
        returns_config=same,
        returns_bench=same,
        metrics={"net_pnl": 0.0, "cagr_pct": 0.0, "delta_dd": 0.0},
    )
    artifacts["evaluation"]["delta_stars"] = [float(x) for x in deltas]
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
    first = cv.build_verdict_string("C3A", cv.decide(artifacts, violations=[]), sha)
    second = cv.build_verdict_string("C3A", cv.decide(artifacts, violations=[]), sha)
    assert first == second
    assert sha[:16] in first
    assert "generated_at" not in first


def test_le_parseur_n_expose_que_des_chemins_et_un_horodatage() -> None:
    """§ 0.6 : aucun paramètre libre, aucune entrée humaine qui déplacerait une issue."""
    actions = {a.dest for a in cv.build_parser()._actions} - {"help"}
    assert actions == {
        "entry", "anchor", "selection", "continuity", "evaluation", "campaign", "output", "now",
    }


def test_toutes_les_raisons_de_la_liste_close_sont_connues_du_module() -> None:
    """La liste close du § H est celle de `c3_common`, et le verdict n'en invente aucune."""
    assert set(cc.REASON_SCOPE) == set(cc.REASON_PRIORITY)
    assert set(cv.BLOCKING_RUN_REASONS) <= set(cc.REASON_PRIORITY)
    assert "F_CANNOT_SEPARATE" not in cv.BLOCKING_RUN_REASONS


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
    with pytest.raises(cc.MissingEvidenceError, match="warmup_anchor_ok"):
        cv.decide(artifacts, violations=[])


def test_bornes_infinies_refusent_l_entree_au_lieu_de_valider() -> None:
    """Défaut reproduit : `float('inf') > 0` est vrai, donc `+inf` franchissait le plancher."""
    artifacts = _sound()
    artifacts["evaluation"]["bounds"] = {k: float("inf") for k in artifacts["evaluation"]["bounds"]}
    with pytest.raises(cc.MissingEvidenceError, match="non finie"):
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
    with pytest.raises(cc.MissingEvidenceError, match="non finie"):
        cv.decide(artifacts, violations=[])


#: Chemin d'une preuve obligatoire, décrit comme une suite de clés.
MANDATORY: tuple[tuple[str, ...], ...] = (
    ("entry", "ok"),
    ("anchor", "universe_provenance"),
    ("selection", "status"),
    ("selection", "retained"),
    ("selection", "retained", "identity"),
    ("continuity", "warmup_anchor_ok"),
    ("continuity", "benchmark_comparable"),
    ("continuity", "stamp_same_daily_cell"),
    ("evaluation", "returns_config"),
    ("evaluation", "delta_stars"),
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
    ids=["entry.ok=int", "continuity=int", "provenance hors liste", "statut hors liste",
         "metrique=str", "serie=scalaire", "serie=mapping"],
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
    with pytest.raises(cc.MissingEvidenceError, match=r"delta_stars\[3\]"):
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
    argv: list[str] = []
    for name in ("entry", "anchor", "selection", "continuity", "evaluation"):
        path = tmp_path / f"{name}.json"
        cc.write_json(path, artifacts[name])
        argv += [f"--{name}", str(path)]
    argv += ["--output", str(tmp_path / "verdict.json"), "--now", "2026-09-21T00:00:00+00:00"]
    return argv


def test_cli_temoin_sain_sort_0_et_ecrit_la_chaine(tmp_path: Path) -> None:
    argv = _write_cli_inputs(tmp_path, _sound())
    assert cv.main(argv) == 0
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["verdict"] == cc.ISSUE_VALIDE
    assert payload["verdict_string"].startswith("C3_C3A | verdict=validé")


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda a: a.__setitem__("anchor", {}), id="provenance supprimée"),
        pytest.param(lambda a: a.__setitem__("continuity", {}), id="continuité vide"),
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
    ],
)
def test_cli_refuse_l_entree_avec_exit_2_et_n_ecrit_rien(tmp_path: Path, mutate: Any) -> None:
    """§ I.1 : entrée refusée → code 2, la chaîne s'arrête, aucun verdict n'est produit."""
    artifacts = _sound()
    mutate(artifacts)
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 2
    assert not (tmp_path / "verdict.json").exists(), "aucun artefact ne doit être écrit"


def test_cli_estimabilite_contredite_sort_1_et_ecrit_le_verdict(tmp_path: Path) -> None:
    """Une violation n'est pas une entrée invalide : code 1, et l'artefact est écrit pour la relire."""
    flat = [0.0] * N_DAYS
    artifacts = _artifacts(
        returns_config=flat,
        returns_bench=_varying(11),
        metrics={"net_pnl": 0.0, "cagr_pct": 0.0, "delta_dd": -1.5},
    )
    artifacts["evaluation"]["estimability"] = {"ok": True, "E1": True, "E2": True}
    argv = _write_cli_inputs(tmp_path, artifacts)
    assert cv.main(argv) == 1
    payload = cc.read_json(tmp_path / "verdict.json")
    assert payload["verdict"] == cc.ISSUE_INCONCLUSIF
    assert payload["raison"] == "F_NOT_ESTIMABLE"
