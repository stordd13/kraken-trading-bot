"""C3 — la propriété de chronologie forte (§ A.12, § I-B) et son contrôle négatif.

**Énoncé testé.** Pour tout `O'` tel que `π_T(O') = π_T(O)` : admissibilité (clause par clause,
pour chaque candidat), scores, classement **complet** et choix ou abstention (raison comprise)
sont **identiques, octet à octet après canonicalisation**. Trois témoins, exigence littérale du
brief : le **préfixe seul** (aucun bloc hors liste blanche), le **même préfixe + futurs A**, le
**même préfixe + futurs B** — les futurs restent présents et bien formés (§ A.12 l.652), ils sont
écartés sans être lus. La comparaison porte sur l'artefact de sélection **entier** produit par
`main()` sur fichiers, moins les seules empreintes de fichiers (différentes par construction) —
`generated_at` compris, grâce à `--now`.

**Contrôle négatif.** Un sélecteur qui lit le futur mais s'y trouve insensible passerait
l'énoncé ; il est donc apparié à un scoreur **volontairement fuyant**, injecté sur le chemin
`main()`, dont les futurs sont choisis pour **renverser le classement** : la **même** fonction
de comparaison doit alors échouer. Sans ce contrôle, la propriété serait trivialement vraie.

Les contrôles structurels (liste blanche, refus de troncature, signature du scoreur) sont
rapportés comme des indices ; ils n'excluent ni une variable globale ni une lecture de fichier
(§ A.12). La preuve est portée par l'invariance et le contrôle négatif.
"""

# ruff: noqa: E402
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any

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

from test_scripts import test_c3_common as fx

#: Ce qui est exclu de la comparaison : les seules empreintes de fichiers, qui diffèrent par
#: construction puisque `O`, `O'` et le préfixe seul ne sont pas les mêmes octets.
EXCLUDED: tuple[str, ...] = ("inputs_sha256",)


def _chain(
    tmp_path: Path,
    *,
    mutate_observations: Any = None,
    manifest_payload: dict[str, Any] | None = None,
    **obs_kw: Any,
) -> dict[str, Any]:
    """anchor → entry → benchmark → select, **par `main()` sur fichiers**, `--now` fixé."""
    w = fx.world(tmp_path, manifest_payload, **obs_kw)
    if mutate_observations is not None:
        obs = cc.read_json(w["observations"])
        mutate_observations(obs)
        cc.write_json(w["observations"], obs)
    assert (
        ca.main(
            [
                "--manifest",
                str(w["manifest"]),
                "--registry",
                str(w["registry"]),
                "--output",
                str(w["anchor"]),
                "--now",
                fx.NOW,
            ]
        )
        == 0
    )
    entry, bench, sel = (
        tmp_path / "entry.json",
        tmp_path / "benchmark.json",
        tmp_path / "selection.json",
    )
    assert (
        ce.main(
            [
                "--manifest",
                str(w["manifest"]),
                "--anchor",
                str(w["anchor"]),
                "--observations",
                str(w["observations"]),
                "--coverage",
                str(w["coverage"]),
                "--output",
                str(entry),
                "--now",
                fx.NOW,
            ]
        )
        == 0
    )
    assert (
        cb.main(
            [
                "--manifest",
                str(w["manifest"]),
                "--anchor",
                str(w["anchor"]),
                "--entry",
                str(entry),
                "--observations",
                str(w["observations"]),
                "--candles",
                str(w["candles"]),
                "--output",
                str(bench),
                "--now",
                fx.NOW,
            ]
        )
        == 0
    )
    assert (
        cs.main(
            [
                "--manifest",
                str(w["manifest"]),
                "--anchor",
                str(w["anchor"]),
                "--entry",
                str(entry),
                "--observations",
                str(w["observations"]),
                "--coverage",
                str(w["coverage"]),
                "--benchmark",
                str(bench),
                "--output",
                str(sel),
                "--now",
                fx.NOW,
            ]
        )
        == 0
    )
    payload = cc.read_json(sel)
    payload["_observations_sha256"] = cc.file_sha256(w["observations"])
    return payload


def _core(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in EXCLUDED and not k.startswith("_")}


def assert_chronology_invariant(payloads: list[Mapping[str, Any]]) -> None:
    """La comparaison, **unique**, utilisée par les témoins et par le contrôle négatif."""
    assert len(payloads) >= 2
    reference = _core(payloads[0])
    for other in payloads[1:]:
        core = _core(other)
        assert cc.sig(core) == cc.sig(reference), (
            f"première différence : {cc.first_difference(cc.canon(reference), cc.canon(core))}"
        )


def _three_witnesses(tmp_path: Path, **kw: Any) -> list[dict[str, Any]]:
    prefix_only = _chain(tmp_path / "prefix", with_futures=False, **kw)
    futures_a = _chain(tmp_path / "a", futures_variant=0, **kw)
    futures_b = _chain(tmp_path / "b", futures_variant=3, **kw)
    # Les trois fichiers d'observations sont bien différents : le test n'est pas vide de contenu.
    assert len({p["_observations_sha256"] for p in (prefix_only, futures_a, futures_b)}) == 3
    return [prefix_only, futures_a, futures_b]


# ---------------------------------------------------------------------------
# Invariance — trois témoins, trois issues, permutation
# ---------------------------------------------------------------------------


def test_invariance_quand_une_configuration_est_retenue(tmp_path: Path) -> None:
    payloads = _three_witnesses(tmp_path)
    assert payloads[1]["status"] == "SÉLECTION_VALIDE" and payloads[1]["retained"] is not None
    assert_chronology_invariant(payloads)
    # Les quatre objets nommés au § A.12, explicitement.
    for other in payloads[1:]:
        a, b = payloads[0], other
        assert [r["clauses"] for r in a["candidates"]] == [r["clauses"] for r in b["candidates"]]
        assert [r["scores"] for r in a["candidates"]] == [r["scores"] for r in b["candidates"]]
        assert a["ranking"] == b["ranking"] and a["retained"] == b["retained"]
        assert a["projection_sha256_all"] == b["projection_sha256_all"]


def _all_d3(obs: dict[str, Any]) -> None:
    for e in obs.values():
        e[fx.PREFIX]["total_trades"] = 20


def _losing(obs: dict[str, Any]) -> None:
    for e in obs.values():
        e[fx.PREFIX]["net_pnl"] = -5.0


def test_invariance_de_l_abstention_ensemble_vide(tmp_path: Path) -> None:
    payloads = _three_witnesses(tmp_path, mutate_observations=_all_d3)
    assert (
        payloads[1]["status"] == "ABSTENTION"
        and payloads[1]["reason"] == "A_NO_ADMISSIBLE_CANDIDATE"
    )
    assert_chronology_invariant(payloads)


def test_invariance_de_l_abstention_sous_le_plancher(tmp_path: Path) -> None:
    payloads = _three_witnesses(tmp_path, mutate_observations=_losing)
    assert payloads[1]["status"] == "ABSTENTION" and payloads[1]["reason"] == "A_BELOW_FLOOR"
    assert_chronology_invariant(payloads)


def test_invariance_sous_permutation_et_futurs_differents(tmp_path: Path) -> None:
    """§ A.9 et § A.12 ensemble : permuter les candidats **et** changer les futurs ne change rien."""

    def reverse(obs: dict[str, Any]) -> None:
        items = list(obs.items())[::-1]
        obs.clear()
        obs.update(items)

    reference = _chain(tmp_path / "ref", futures_variant=0)
    permuted = _chain(tmp_path / "perm", futures_variant=5, mutate_observations=reverse)
    assert_chronology_invariant([reference, permuted])


def test_invariance_sous_provenance_contaminee(tmp_path: Path) -> None:
    payloads = _three_witnesses(tmp_path, manifest_payload=fx.manifest(provenance="contaminated"))
    assert payloads[1]["status"] == "SÉLECTION_DESCRIPTIVE"
    assert_chronology_invariant(payloads)


# ---------------------------------------------------------------------------
# Contrôle négatif — le test détecte un scoreur fuyant
# ---------------------------------------------------------------------------


def _leaky_scorer(
    projection: Mapping[str, Any], raw: Mapping[str, Any], bench: Mapping[str, Any]
) -> tuple[float, float]:
    """Lit un bloc **hors liste blanche** : le segment futur `test`. C'est la fuite du § 0.2 (a)."""
    del projection
    return float(raw["test"]["net_pnl"]), float(bench["delta_sigma"])


def _rank_futures(sign: int) -> Any:
    def mutate(obs: dict[str, Any]) -> None:
        for i, e in enumerate(obs.values()):
            e["test"]["net_pnl"] = float(sign * (i + 1))

    return mutate


def test_controle_negatif_un_scoreur_fuyant_est_detecte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cs, "default_scorer", _leaky_scorer)
    leaky_a = _chain(tmp_path / "a", futures_variant=0, mutate_observations=_rank_futures(+1))
    leaky_b = _chain(tmp_path / "b", futures_variant=3, mutate_observations=_rank_futures(-1))
    # Le futur a bien été lu : le classement diffère entre les deux futurs.
    assert leaky_a["ranking"] != leaky_b["ranking"] or leaky_a["survivors"] != leaky_b["survivors"]
    # Et c'est **la même** fonction de comparaison qui le détecte.
    with pytest.raises(AssertionError):
        assert_chronology_invariant([leaky_a, leaky_b])


def test_controle_negatif_le_scoreur_par_defaut_ignore_les_memes_futurs(tmp_path: Path) -> None:
    """Le contrepoint exact du contrôle négatif : mêmes futurs renversés, scoreur par défaut, invariance."""
    a = _chain(tmp_path / "a", futures_variant=0, mutate_observations=_rank_futures(+1))
    b = _chain(tmp_path / "b", futures_variant=3, mutate_observations=_rank_futures(-1))
    assert_chronology_invariant([a, b])


def test_le_scoreur_par_defaut_ne_lit_que_le_comparateur() -> None:
    """Indice structurel, pas une preuve : le scoreur par défaut ignore la projection et l'observation."""
    sentinel = object()
    delta = cs.default_scorer(sentinel, sentinel, {"delta_dd": 1.5, "delta_sigma": -0.5})  # type: ignore[arg-type]
    assert delta == (1.5, -0.5)


def test_la_liste_blanche_de_la_projection_est_celle_du_A7() -> None:
    """Indice structurel : les champs retenus par π_T sont exactement ceux que le § A.7 énumère."""
    m = fx.manifest()
    obs = fx.observations(m)
    entry = next(iter(obs.values()))
    projection = cc.project_prefix(entry, fx.PREFIX, where="t")
    assert set(projection) == {
        "identity",
        "contracts",
        "bounds",
        "metrics",
        "equity_daily",
        "liquidation",
        "warmup",
        "rejections",
        "dca_counters",
    }
    assert set(projection["identity"]) == {"strategy", "pair", "params", "effective_params"}
    assert set(projection["contracts"]) == {
        "metrics_version",
        "replay_version",
        "exchange",
        "fees",
        "pair_costs",
        "pair_costs_file",
        "min_order_usdc",
    }
    assert projection["bounds"] == {
        "start": fx.WINDOW_START.isoformat(),
        "end": fx.ANCHOR.isoformat(),
    }
    # Un futur différent ne change pas l'empreinte de la projection.
    other = fx.observation(entry["strategy"], entry["pair"], entry["params"], 0, futures_variant=7)
    assert cc.sig(cc.project_prefix(other, fx.PREFIX, where="t")) == cc.sig(projection)
    assert other["test"] != entry["test"], "les futurs diffèrent bien"
