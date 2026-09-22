"""C3 — le contrat de continuité (§ B) : cinq clauses, chacune avec l'état de sa vérifiabilité.

Tout est synthétique (§ L.1 : aucune entrée réelle en C3a). Le témoin sain est une évaluation
conforme au contrat (un seul appel, grille continue, liquidation prouvée par lot, amorçage
suffisant à T) ; chaque contre-exemple en isole une clause. Acquis testé en clair : **aucune
déclaration ne produit VERIFIED** — la preuve de départ à plat la plus cohérente vaut DECLARED.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import json
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
import c3_common as cc
import c3_continuity as cn

from test_scripts import test_c3_common as fx


def _world(tmp_path: Path, **eval_kw: Any) -> dict[str, Any]:
    payload = fx.manifest()
    w: dict[str, Any] = {
        "payload": payload,
        "manifest": tmp_path / "manifest.json",
        "registry": tmp_path / "variants.json",
        "anchor": tmp_path / "anchor.json",
        "evaluation": tmp_path / "evaluation.json",
        "benchmark_eval": tmp_path / "benchmark_eval.json",
        "continuity": tmp_path / "continuity.json",
    }
    cc.write_json(w["manifest"], payload)
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
    cc.write_json(w["evaluation"], fx.evaluation(payload, **eval_kw))
    cc.write_json(w["benchmark_eval"], fx.benchmark_eval())
    return w


def _argv(w: dict[str, Any]) -> list[str]:
    return [
        "--manifest",
        str(w["manifest"]),
        "--anchor",
        str(w["anchor"]),
        "--evaluation",
        str(w["evaluation"]),
        "--benchmark-eval",
        str(w["benchmark_eval"]),
        "--output",
        str(w["continuity"]),
        "--now",
        fx.NOW,
    ]


def _run(w: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    code = cn.main(_argv(w))
    return code, (cc.read_json(w["continuity"]) if w["continuity"].exists() else None)


def _mutate_eval(w: dict[str, Any], mutate: Any) -> None:
    data = cc.read_json(w["evaluation"])
    mutate(data)
    cc.write_json(w["evaluation"], data)


def _states(payload: dict[str, Any]) -> dict[str, str]:
    return {k: v["state"] for k, v in payload["clauses"].items()}


# ---------------------------------------------------------------------------
# Témoin sain : ce que C3a peut établir, et rien de plus
# ---------------------------------------------------------------------------


def test_le_temoin_sain_est_non_verifiable_en_c1_et_c5_verifie_en_c3_et_c4(tmp_path: Path) -> None:
    w = _world(tmp_path, first_fill_at=None)
    code, payload = _run(w)
    assert code == 0 and payload is not None and payload["ok"] is True
    assert _states(payload) == {
        "c1": "NOT_VERIFIABLE",
        "c2": "DECLARED",
        "c3": "VERIFIED",
        "c4": "VERIFIED",
        "c5": "NOT_VERIFIABLE",
    }
    assert payload["state"] == "NOT_VERIFIABLE", "l'agrégat porte la pire clause"
    assert payload["warmup_anchor_ok"] is True and payload["benchmark_comparable"] is True
    assert payload["stamp_same_daily_cell"] is True and payload["liquidation_normalised"] is True
    assert payload["synthetic"] is True and payload["d6_report"]["lots_present"] is True
    assert payload["inputs_sha256"]["evaluation"] == cc.file_sha256(w["evaluation"])


def test_aucune_declaration_ne_produit_VERIFIED(tmp_path: Path) -> None:
    """La preuve de départ à plat la plus cohérente et une première exécution déclarée valent DECLARED."""
    w = _world(
        tmp_path,
        flat_start_proof={"cash_at_T": "1000", "inventory_qty_at_T": "0", "pending_orders_at_T": 0},
        first_fill_at=fx.ANCHOR + timedelta(minutes=10),
    )
    code, payload = _run(w)
    assert code == 0 and payload is not None
    states = _states(payload)
    assert states["c1"] == "DECLARED" and states["c5"] == "DECLARED" and states["c2"] == "DECLARED"
    assert "VERIFIED" not in (states["c1"], states["c2"], states["c5"])
    assert payload["state"] == "DECLARED", (
        "sans NOT_VERIFIABLE ni FAILED, l'agrégat est DECLARED — jamais VERIFIED en C3a"
    )
    assert "jamais VERIFIED" in payload["clauses"]["c1"]["detail"]


# ---------------------------------------------------------------------------
# Chaque clause en échec, à sa place
# ---------------------------------------------------------------------------


def test_c1_preuve_de_depart_a_plat_incoherente_est_FAILED(tmp_path: Path) -> None:
    w = _world(
        tmp_path,
        flat_start_proof={
            "cash_at_T": "990",
            "inventory_qty_at_T": "0.001",
            "pending_orders_at_T": 1,
        },
    )
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert _states(payload)["c1"] == "FAILED" and payload["state"] == "FAILED"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("flat_start_proof", "cash_at_T"), None),
        (("flat_start_proof", "pending_orders_at_T"), "0"),
        (("invocation", "single_call"), "true"),
        (("invocation", "single_call"), None),
        (("invocation",), None),
        (("synthetic",), 1),
        (("synthetic",), None),
    ],
    ids=[
        "cash null",
        "pending str",
        "single_call str",
        "single_call null",
        "invocation null",
        "synthetic int",
        "synthetic null",
    ],
)
def test_chaque_champ_mal_type_ou_nul_refuse_l_entree(
    tmp_path: Path, path: tuple[str, ...], value: Any
) -> None:
    w = _world(
        tmp_path,
        flat_start_proof={"cash_at_T": "1000", "inventory_qty_at_T": "0", "pending_orders_at_T": 0},
    )

    def mutate(data: dict[str, Any]) -> None:
        node: Any = data
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    _mutate_eval(w, mutate)
    code, payload = _run(w)
    assert code == 2 and payload is None


def test_single_call_absent_refuse_l_entree(tmp_path: Path) -> None:
    w = _world(tmp_path)
    _mutate_eval(w, lambda d: d["invocation"].pop("single_call"))
    assert _run(w)[0] == 2


def test_c2_appel_multiple_ou_grille_discontinue_est_FAILED(tmp_path: Path) -> None:
    w = _world(tmp_path, single_call=False)
    code, payload = _run(w)
    assert code == 0 and payload is not None and _states(payload)["c2"] == "FAILED"
    w2 = _world(tmp_path / "b")
    _mutate_eval(w2, lambda d: d["equity_daily"]["values"].pop())
    code, payload = _run(w2)
    assert code == 0 and payload is not None and _states(payload)["c2"] == "FAILED"
    assert "grille" in payload["clauses"]["c2"]["detail"]


def test_c3_liquidation_absente_est_FAILED_et_non_normalisee(tmp_path: Path) -> None:
    """La fixture « moteur signal à l'évaluation » : le bloc est null (run_p7_grid_search.py:768)."""
    w = _world(tmp_path, liquidation=False)
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert _states(payload)["c3"] == "FAILED" and payload["liquidation_normalised"] is False
    assert payload["stamp_same_daily_cell"] is False and payload["state"] == "FAILED"


def test_c3_identite_exacte_fausse_est_FAILED(tmp_path: Path) -> None:
    w = _world(tmp_path)

    def wrong_price(d: dict[str, Any]) -> None:
        liq = d["liquidation"]
        liq["price"] = str(Decimal(liq["reference_price"]) * Decimal("0.99"))

    _mutate_eval(w, wrong_price)
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert _states(payload)["c3"] == "FAILED" and payload["liquidation_normalised"] is False


def test_c3_sans_lots_est_NOT_VERIFIABLE_jamais_VERIFIED(tmp_path: Path) -> None:
    """Identités exactes vraies, preuve par lot absente : indécidable, ni vert ni faux."""
    w = _world(tmp_path, lots=False)
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert _states(payload)["c3"] == "NOT_VERIFIABLE" and payload["liquidation_normalised"] is None
    assert payload["state"] == "NOT_VERIFIABLE"


def test_c3_quantite_de_lot_nulle_est_FAILED_via_la_preuve_partagee(tmp_path: Path) -> None:
    """Le correctif R3 a) s'applique ici aussi : `liquidation_identities` est la même fonction."""
    w = _world(tmp_path)

    def zero_amount(d: dict[str, Any]) -> None:
        for lot in d["liquidation"]["lots"]:
            lot["amount_btc"] = "0"

    _mutate_eval(w, zero_amount)
    code, payload = _run(w)
    assert code == 0 and payload is not None and _states(payload)["c3"] == "FAILED"
    assert any("amount_btc" in d for d in payload["d6_report"]["details"])


def test_estampille_de_liquidation_hors_de_la_derniere_cellule(tmp_path: Path) -> None:
    """§ B.4 : liquidation estampillée deux jours avant la borne → cellules distinctes."""
    w = _world(tmp_path)
    _mutate_eval(
        w,
        lambda d: d["liquidation"].__setitem__(
            "timestamp", (fx.WINDOW_END - timedelta(days=2)).isoformat()
        ),
    )
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert payload["stamp_same_daily_cell"] is False
    assert _states(payload)["c3"] == "VERIFIED", (
        "l'estampille n'est pas une identité D6 : c'est E_STAMP_MISMATCH côté verdict"
    )


def test_c4_amorcage_insuffisant_a_T_est_FAILED(tmp_path: Path) -> None:
    w = _world(tmp_path, sufficient=False)
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert _states(payload)["c4"] == "FAILED" and payload["warmup_anchor_ok"] is False


def test_c4_sufficient_declare_contredit_est_une_violation(tmp_path: Path) -> None:
    w = _world(tmp_path)
    _mutate_eval(w, lambda d: d["warmup"]["1d"].__setitem__("sufficient", False))
    code, payload = _run(w)
    assert code == 1 and payload is not None and payload["invalide"] is True
    assert any("sufficient" in v for v in payload["violations"])


def test_c5_premiere_execution_a_T_ou_avant_est_FAILED(tmp_path: Path) -> None:
    w = _world(tmp_path, first_fill_at=fx.ANCHOR)
    code, payload = _run(w)
    assert code == 0 and payload is not None and _states(payload)["c5"] == "FAILED"
    w2 = _world(tmp_path / "b", first_fill_at=fx.ANCHOR - timedelta(minutes=5))
    code, payload = _run(w2)
    assert code == 0 and payload is not None and _states(payload)["c5"] == "FAILED"


def test_comparateur_declare_contredit_par_ses_tests_est_une_violation(tmp_path: Path) -> None:
    w = _world(tmp_path)
    cc.write_json(w["benchmark_eval"], fx.benchmark_eval(contradict=True))
    code, payload = _run(w)
    assert (
        code == 1 and payload is not None and any("comparable" in v for v in payload["violations"])
    )
    w2 = _world(tmp_path / "b")
    cc.write_json(w2["benchmark_eval"], fx.benchmark_eval(comparable=False))
    code, payload = _run(w2)
    assert code == 0 and payload is not None and payload["benchmark_comparable"] is False


# ---------------------------------------------------------------------------
# Entrées : univers, période, paire, amont, non-finis, CLI
# ---------------------------------------------------------------------------


def test_configuration_hors_univers_refuse_l_entree(tmp_path: Path) -> None:
    w = _world(tmp_path)
    _mutate_eval(w, lambda d: d["params"].__setitem__("inconnu", 1))
    assert _run(w)[0] == 2


def test_periode_differente_de_T_fin_refuse_l_entree(tmp_path: Path) -> None:
    w = _world(tmp_path)
    _mutate_eval(w, lambda d: d["period"].__setitem__("start", fx.WINDOW_START.isoformat()))
    assert _run(w)[0] == 2


def test_paire_du_comparateur_differente_refuse_l_entree(tmp_path: Path) -> None:
    w = _world(tmp_path)
    cc.write_json(w["benchmark_eval"], fx.benchmark_eval("SOL/USDC"))
    assert _run(w)[0] == 2


def test_ancrage_amont_en_echec_ou_discordant(tmp_path: Path) -> None:
    w = _world(tmp_path)
    anchor = cc.read_json(w["anchor"])
    anchor["ok"] = False
    cc.write_json(w["anchor"], anchor)
    assert _run(w)[0] == 2
    w2 = _world(tmp_path / "b")
    cc.write_json(w2["manifest"], fx.manifest(variant_id="autre"))
    code, payload = _run(w2)
    assert (
        code == 1
        and payload is not None
        and any("inputs_sha256.manifest" in v for v in payload["violations"])
    )


def test_nan_dans_la_trajectoire_est_une_violation_code_1(tmp_path: Path) -> None:
    w = _world(tmp_path)
    data = cc.read_json(w["evaluation"])
    data["equity_daily"]["values"][3] = float("nan")
    w["evaluation"].write_text(json.dumps(data, allow_nan=True), encoding="utf-8")
    code, payload = _run(w)
    assert code == 1 and payload is not None and payload["invalide"] is True


def test_nan_dans_les_parametres_est_une_violation_code_1(tmp_path: Path) -> None:
    w = _world(tmp_path)
    data = cc.read_json(w["evaluation"])
    data["params"]["nan"] = float("nan")
    w["evaluation"].write_text(json.dumps(data, allow_nan=True), encoding="utf-8")
    code, payload = _run(w)
    assert code == 1 and payload is not None and payload["invalide"] is True


def test_le_parseur_n_expose_que_des_chemins_et_un_horodatage() -> None:
    actions = {a.dest for a in cn.build_parser()._actions} - {"help"}
    assert actions == {"manifest", "anchor", "evaluation", "benchmark_eval", "output", "now"}


def test_agregat_prend_la_pire_clause() -> None:
    assert cn.aggregate_state({"a": "VERIFIED", "b": "DECLARED"}) == "DECLARED"
    assert (
        cn.aggregate_state({"a": "VERIFIED", "b": "NOT_VERIFIABLE", "c": "DECLARED"})
        == "NOT_VERIFIABLE"
    )
    assert cn.aggregate_state({"a": "FAILED", "b": "VERIFIED"}) == "FAILED"
    assert cn.aggregate_state({"a": "VERIFIED"}) == "VERIFIED"


# ---------------------------------------------------------------------------
# Revue Fin (2) — les blocs dérivables : cellule d'estampille et comparateur, résumés = dérivés
# ---------------------------------------------------------------------------

SUMMARY_OF_C3 = {"VERIFIED": True, "NOT_VERIFIABLE": None, "FAILED": False}


def _assert_summaries_derived(payload: dict[str, Any]) -> None:
    states = _states(payload)
    assert payload["state"] == cn.aggregate_state(states)
    assert payload["warmup_anchor_ok"] is (states["c4"] == "VERIFIED")
    assert payload["liquidation_normalised"] is SUMMARY_OF_C3[states["c3"]]
    assert payload["stamp_same_daily_cell"] is (payload["stamp_cell"]["state"] == "VERIFIED")
    assert payload["benchmark_comparable"] is (payload["comparator"]["state"] == "VERIFIED")
    tests = payload["comparator"]["tests"]
    assert set(tests) >= {
        "entry_stamp_present",
        "exit_stamp_present",
        "ff_ok",
        "n_returns_ok",
        "all_finite",
    }
    assert (payload["comparator"]["state"] == "VERIFIED") is all(tests.values())


def test_revue_Fin_2_le_temoin_sain_porte_les_blocs_stamp_cell_et_comparator(
    tmp_path: Path,
) -> None:
    w = _world(tmp_path)
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert (
        payload["stamp_cell"]["state"] == "VERIFIED"
        and payload["comparator"]["state"] == "VERIFIED"
    )
    _assert_summaries_derived(payload)


def test_revue_Fin_2_estampille_hors_cellule_est_un_bloc_FAILED_derive(tmp_path: Path) -> None:
    w = _world(tmp_path)
    _mutate_eval(
        w,
        lambda d: d["liquidation"].__setitem__(
            "timestamp", (fx.WINDOW_END - timedelta(days=2)).isoformat()
        ),
    )
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert payload["stamp_cell"]["state"] == "FAILED" and payload["stamp_same_daily_cell"] is False
    _assert_summaries_derived(payload)


def test_revue_Fin_2_liquidation_absente_rend_la_cellule_non_verifiable(tmp_path: Path) -> None:
    w = _world(tmp_path, liquidation=False)
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert payload["stamp_cell"]["state"] == "NOT_VERIFIABLE"
    assert payload["stamp_same_daily_cell"] is False and _states(payload)["c3"] == "FAILED"
    _assert_summaries_derived(payload)


def test_revue_Fin_2_comparateur_non_comparable_est_un_bloc_FAILED_derive(tmp_path: Path) -> None:
    w = _world(tmp_path)
    cc.write_json(w["benchmark_eval"], fx.benchmark_eval(comparable=False))
    code, payload = _run(w)
    assert code == 0 and payload is not None
    assert (
        payload["comparator"]["state"] == "FAILED"
        and payload["comparator"]["tests"]["ff_ok"] is False
    )
    assert payload["benchmark_comparable"] is False
    _assert_summaries_derived(payload)
