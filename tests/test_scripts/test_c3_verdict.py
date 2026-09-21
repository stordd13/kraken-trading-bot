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

import c3_common as cc
import c3_verdict as cv

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
            "B": cc.BOOTSTRAP_B,
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
    first = cv.build_verdict_string("C3A", cv.decide(artifacts, violations=[]), sha)
    second = cv.build_verdict_string("C3A", cv.decide(artifacts, violations=[]), sha)
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
    with pytest.raises(cc.MissingEvidenceError, match="warmup_anchor_ok"):
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


def _with_replications(a: dict[str, Any], *, b: int, n_deltas: int, discarded: int) -> None:
    """Déclare `B`, garde `n_deltas` réplications de la suite générée, déclare `discarded`.

    Tronquer la suite est la forme documentée d'un échec numérique (§ F.2 e) : les réplications
    écartées ne sont pas remplacées, elles sont comptées.
    """
    a["evaluation"]["B"] = b
    a["evaluation"]["delta_stars"] = a["evaluation"]["delta_stars"][:n_deltas]
    a["evaluation"]["discarded"] = discarded


#: (B, len(delta_stars), discarded, code CLI, issue attendue, raison attendue)
MATRIX_B = [
    pytest.param(10_000, 9_990, 10, 0, cc.ISSUE_VALIDE, None, id="10000/9990/10 -> 0 témoin sain"),
    pytest.param(
        10_000,
        9_989,
        11,
        0,
        cc.ISSUE_INCONCLUSIF,
        "F_NOT_ESTIMABLE",
        id="10000/9989/11 -> 0 F_NOT_ESTIMABLE, compte cohérent",
    ),
    pytest.param(10_000, 10_000, 11, 1, None, None, id="10000/10000/11 -> 1 compte contradictoire"),
    pytest.param(
        400, 395, 5, 2, None, "R0_INVALID_RUN", id="400/395/5 -> 2 cohérent mais hors contrat"
    ),
    pytest.param(
        400, 400, 5, 2, None, "R0_INVALID_RUN", id="400/400/5 -> 2 R0 évalué avant la cohérence"
    ),
]


@pytest.mark.parametrize(("b", "n_deltas", "discarded", "code", "issue", "reason"), MATRIX_B)
def test_matrice_B_en_appel_direct(
    b: int, n_deltas: int, discarded: int, code: int, issue: Any, reason: Any
) -> None:
    artifacts = _sound()
    _with_replications(artifacts, b=b, n_deltas=n_deltas, discarded=discarded)
    assert len(artifacts["evaluation"]["delta_stars"]) == n_deltas
    violations: list[str] = []
    if code == 2:
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


@pytest.mark.parametrize(("b", "n_deltas", "discarded", "code", "issue", "reason"), MATRIX_B)
def test_matrice_B_par_la_cli(
    tmp_path: Path, b: int, n_deltas: int, discarded: int, code: int, issue: Any, reason: Any
) -> None:
    artifacts = _sound()
    _with_replications(artifacts, b=b, n_deltas=n_deltas, discarded=discarded)
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
        a["selection"] = {"status": "ABSTENTION", "reason": reason}

    return mutate


def _all_discarded(a: dict[str, Any]) -> None:
    a["evaluation"]["delta_stars"] = []
    a["evaluation"]["discarded"] = cc.BOOTSTRAP_B


#: (ligne, fixture, issue attendue, raison attendue, code CLI attendu, artefact écrit ?, chaîne citable ?)
TABLE_I1 = [
    pytest.param(1, lambda a: None, cc.ISSUE_VALIDE, None, 0, True, True, id="L1 entrée conforme"),
    pytest.param(
        2,
        lambda a: a.__setitem__("entry", {"ok": False}),
        None,
        "R0_INVALID_RUN",
        2,
        False,
        False,
        id="L2 contrat rompu R0",
    ),
    pytest.param(
        7,
        lambda a: a.__setitem__("anchor", {"universe_provenance": "contaminated"}),
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
        lambda a: a["continuity"].__setitem__("benchmark_comparable", False),
        cc.ISSUE_INCONCLUSIF,
        "E_NO_BENCHMARK",
        0,
        True,
        True,
        id="L10 benchmark",
    ),
    pytest.param(
        11,
        lambda a: a["continuity"].__setitem__("stamp_same_daily_cell", False),
        cc.ISSUE_INCONCLUSIF,
        "E_STAMP_MISMATCH",
        0,
        True,
        True,
        id="L11 estampille",
    ),
    pytest.param(
        12,
        lambda a: a["continuity"].__setitem__("warmup_anchor_ok", False),
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
