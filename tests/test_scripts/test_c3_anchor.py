"""C3 — l'ancrage recalculé, les estampilles admissibles et le registre de variantes (§ A.3, § A.4, § A.6).

Tout est synthétique. Le témoin sain est un manifeste **conforme au contrat** (valeurs gelées
comprises) ; chaque contre-exemple en isole un défaut, et asserte l'issue interdite autant que
l'issue attendue : un ancrage n'est jamais accepté comme paramètre, une valeur gelée n'est jamais
« à peu près », un parent absent n'est jamais toléré, un enregistrement altéré n'est jamais recopié.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
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

from test_scripts import test_c3_common as fx


def _run(tmp_path: Path, payload: dict[str, Any], **kw: Any) -> tuple[int, dict[str, Any] | None]:
    path = fx.write_manifest(tmp_path, payload, kw.pop("name", "manifest.json"))
    code = ca.main(fx.anchor_argv(tmp_path, path, **kw))
    out = tmp_path / kw.get("output", "anchor.json")
    return code, (cc.read_json(out) if out.exists() else None)


# ---------------------------------------------------------------------------
# Témoin sain
# ---------------------------------------------------------------------------


def test_le_temoin_sain_rend_0_et_l_ancrage_declare(tmp_path: Path) -> None:
    code, payload = _run(tmp_path, fx.manifest())
    assert code == 0
    assert payload is not None and payload["ok"] is True and payload["invalide"] is False
    assert payload["anchor"] == "2025-05-07T04:48:00+00:00"
    assert payload["prefix_days"] == pytest.approx(767.2)
    assert payload["evaluation_days"] == pytest.approx(328.8)
    assert payload["frozen_values_asserted"] == [
        "anchor_fraction",
        "uncertainty",
        "thresholds",
        "protocol_sha256",
    ]
    assert payload["universe_provenance"] == "clean"
    assert payload["registry"]["new_entry"] is True
    assert (tmp_path / "variants.json").exists()
    assert payload["inputs_sha256"]["manifest"] == cc.file_sha256(tmp_path / "manifest.json")


def test_la_table_A4_est_donnee_par_la_regle_et_pas_ecrite_en_dur(tmp_path: Path) -> None:
    """§ A.4 : les quatre valeurs sont ce que la règle « dernière estampille <= T » donne à l'ancrage —
    ici l'ancrage de la fenêtre de construction v2.0 que portent les fixtures (§ A.3 v2.1, « Historique »)."""
    _, payload = _run(tmp_path, fx.manifest())
    assert payload is not None
    assert payload["admissible_stamps_by_label"] == {
        "5m": "2025-05-07T04:45:00+00:00",
        "4h": "2025-05-07T04:00:00+00:00",
        "1d": "2025-05-07T00:00:00+00:00",
        "1w": "2025-05-05T00:00:00+00:00",
    }
    assert payload["first_exec_stamp_after_anchor"] == "2025-05-07T04:50:00+00:00"


def test_un_ancrage_sur_une_estampille_retient_cette_estampille(tmp_path: Path) -> None:
    """Le cas limite est couvert par la règle : si T coïncide avec une estampille, c'est celle-là."""
    payload = fx.manifest()
    # 2024-04-01T00:00Z est un lundi minuit : début 2023-11-20, fin 2023-11-20 + 190 j, et
    # 0,7 × 190 j = 133 j tombent exactement dessus.
    payload["window"] = {
        "start": datetime(2023, 11, 20, tzinfo=UTC).isoformat(),
        "end": datetime(2024, 5, 28, tzinfo=UTC).isoformat(),
    }
    code, out = _run(tmp_path, payload)
    assert code == 0 and out is not None
    assert out["anchor"] == "2024-04-01T00:00:00+00:00"
    assert set(out["admissible_stamps_by_label"].values()) == {"2024-04-01T00:00:00+00:00"}
    assert out["first_exec_stamp_after_anchor"] == "2024-04-01T00:05:00+00:00"


# ---------------------------------------------------------------------------
# § A.3 et § A.4 v2.1 — la fenêtre déclarée de la première campagne (valeurs recopiées du texte)
# ---------------------------------------------------------------------------

#: § A.3 v2.1, bloc de calcul : « fenêtre déclarée (v2.1, première campagne) : 2021-03-01T00:00:00Z →
#: 2026-06-29T00:00:00Z ⇒ T = 2024-11-22T04:48:00Z (préfixe 1362,2 j · période évaluée 583,8 j · fenêtre 1946 j) ».
V21_WINDOW = {"start": "2021-03-01T00:00:00+00:00", "end": "2026-06-29T00:00:00+00:00"}
V21_ANCHOR = "2024-11-22T04:48:00+00:00"
V21_PREFIX_DAYS = 1362.2
V21_EVALUATION_DAYS = 583.8
V21_WINDOW_DAYS = 1946.0
#: § A.4 v2.1, table « Dernière observation admissible à T = 2024-11-22T04:48Z ».
V21_STAMPS = {
    "5m": "2024-11-22T04:45:00+00:00",
    "4h": "2024-11-22T04:00:00+00:00",
    "1d": "2024-11-22T00:00:00+00:00",
    "1w": "2024-11-18T00:00:00+00:00",
}


def _campaign_v21_manifest() -> dict[str, Any]:
    """La fixture de campagne v2.1 : le manifeste conforme des fixtures, sur la fenêtre déclarée du § A.3 v2.1."""
    payload = fx.manifest()
    payload["window"] = dict(V21_WINDOW)
    return payload


def test_la_fenetre_de_la_premiere_campagne_donne_l_ancrage_du_texte(tmp_path: Path) -> None:
    """§ A.3 v2.1 : T recalculé depuis la règle sur la fenêtre déclarée, sans aucun arrondi de 04:48."""
    code, payload = _run(tmp_path, _campaign_v21_manifest())
    assert code == 0 and payload is not None
    assert payload["window"] == V21_WINDOW
    assert payload["anchor"] == V21_ANCHOR, "aucun arrondi implicite de 04:48 (§ A.3)"
    assert payload["prefix_days"] == pytest.approx(V21_PREFIX_DAYS, abs=1e-9)
    assert payload["evaluation_days"] == pytest.approx(V21_EVALUATION_DAYS, abs=1e-9)
    assert payload["window_days"] == V21_WINDOW_DAYS


def test_la_table_A4_v21_est_ce_que_la_regle_donne_a_l_ancrage_v21(tmp_path: Path) -> None:
    """§ A.4 v2.1 : les quatre estampilles admissibles à T = 2024-11-22T04:48Z (le 1 w : le lundi 18 novembre)."""
    code, payload = _run(tmp_path, _campaign_v21_manifest())
    assert code == 0 and payload is not None
    assert payload["admissible_stamps_by_label"] == V21_STAMPS
    assert payload["first_exec_stamp_after_anchor"] == "2024-11-22T04:50:00+00:00"


def test_une_transposition_d_actif_de_base_est_refusee_a_l_ancrage(tmp_path: Path) -> None:
    """§ A.6 v2.1 (transposition déclarée) : seule la monnaie de cotation peut différer entre paire de validation
    et paire de déploiement ; un autre actif de base est une erreur d'entrée — code 2, rien d'écrit (§ I.1 l.2)."""
    payload = fx.manifest()
    payload["universe"]["deployment_pairs"] = {"BTC/USDC": "ETH/USDT"}
    code, out = _run(tmp_path, payload)
    assert code == 2 and out is None
    assert not (tmp_path / "variants.json").exists()
    payload["universe"]["deployment_pairs"] = {"BTC/USDC": "BTC/USDT"}
    code, out = _run(tmp_path, payload)
    assert code == 0 and out is not None, "la transposition de cotation seule est admise"


def test_un_ancrage_ecrit_dans_le_manifeste_n_est_jamais_lu(tmp_path: Path) -> None:
    """§ A.3 : « T est recalculé par l'outil depuis la règle, jamais accepté comme paramètre libre » — une clé
    d'ancrage déclarée en dur dans le manifeste est ignorée (elle change l'empreinte, pas T)."""
    payload = _campaign_v21_manifest()
    payload["anchor"] = "2025-01-01T00:00:00+00:00"
    code, out = _run(tmp_path, payload)
    assert code == 0 and out is not None
    assert out["anchor"] == V21_ANCHOR and out["anchor"] != payload["anchor"]


# ---------------------------------------------------------------------------
# Valeurs gelées : assertées, pas seulement typées (liste close de quatre)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        pytest.param(
            lambda m: m.__setitem__("anchor_fraction", 0.69), "anchor_fraction", id="F = 0,69"
        ),
        pytest.param(
            lambda m: m.__setitem__("anchor_fraction", 0.5), "anchor_fraction", id="F = 0,5"
        ),
        pytest.param(
            lambda m: m["uncertainty"].__setitem__("B", 400), "uncertainty.B", id="B = 400"
        ),
        pytest.param(
            lambda m: m["uncertainty"].__setitem__("block_lengths", [10, 21]),
            "block_lengths",
            id="block_lengths tronqués",
        ),
        pytest.param(
            lambda m: m["uncertainty"].__setitem__("bound_level", 0.9),
            "bound_level",
            id="bound_level 0,9",
        ),
        pytest.param(
            lambda m: m["selection_rule"]["thresholds"]["CYCLES_MIN"].__setitem__("value", 20),
            "CYCLES_MIN.value",
            id="seuil déplacé",
        ),
        pytest.param(
            lambda m: m["selection_rule"]["thresholds"]["FLOOR_CAGR_PCT"].__setitem__(
                "class", "contrat"
            ),
            "FLOOR_CAGR_PCT.class",
            id="classe fausse",
        ),
        pytest.param(
            lambda m: m["selection_rule"]["thresholds"]["CAPITAL"].__setitem__("section", "§ A.3"),
            "CAPITAL.section",
            id="section fausse",
        ),
        pytest.param(
            lambda m: m["selection_rule"]["thresholds"].pop("DISCARDED_MAX"),
            "DISCARDED_MAX",
            id="seuil gelé absent",
        ),
        pytest.param(
            lambda m: m["selection_rule"]["thresholds"].__setitem__(
                "G3_FEE_MULTIPLE",
                {"value": 10.0, "class": "préférence économique", "section": "§ X"},
            ),
            "G3_FEE_MULTIPLE",
            id="seuil inconnu déclaré",
        ),
        pytest.param(
            lambda m: m.__setitem__("protocol_sha256", "0" * 64),
            "protocol_sha256",
            id="sha protocole faux",
        ),
    ],
)
def test_une_valeur_gelee_deplacee_est_un_contrat_rompu(
    tmp_path: Path, mutate: Any, fragment: str, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = fx.manifest()
    mutate(payload)
    code, out = _run(tmp_path, payload)
    assert code == 2
    assert out is None, "code 2 : rien n'est écrit"
    assert not (tmp_path / "variants.json").exists(), "aucun enregistrement au registre"
    err = capsys.readouterr().err
    assert "ENTREE REFUSEE R0_INVALID_RUN" in err and fragment in err


def test_les_valeurs_gelees_sont_assertees_en_appel_direct() -> None:
    manifest = cc.load_manifest(fx.manifest())
    assert ca.assert_frozen_values(manifest) == []
    moved = fx.manifest()
    moved["anchor_fraction"] = 0.75
    moved["uncertainty"]["B"] = 1
    problems = ca.assert_frozen_values(cc.load_manifest(moved))
    assert len(problems) == 2
    assert any("anchor_fraction" in p for p in problems) and any(
        "uncertainty.B" in p for p in problems
    )


# ---------------------------------------------------------------------------
# Typage strict du manifeste : absent, null, type faux, hors liste close, doublon
# ---------------------------------------------------------------------------

MANDATORY: tuple[tuple[str, ...], ...] = (
    ("window",),
    ("window", "start"),
    ("window", "end"),
    ("anchor_fraction",),
    ("prefix_segment",),
    ("data",),
    ("data", "exchange"),
    ("data", "exec_interval"),
    ("data", "timeframes"),
    ("fees",),
    ("fees", "model"),
    ("fees", "taker"),
    ("fees", "pair_costs_file"),
    ("fees", "pair_costs"),
    ("fees", "pair_costs", "BTC/USDC", "spread"),
    ("min_order_usdc",),
    ("universe",),
    ("universe", "provenance"),
    ("universe", "candidates"),
    ("strategies",),
    ("strategies", "synth_grid", "engine"),
    ("strategies", "synth_grid", "decision_timeframes"),
    ("selection_rule",),
    ("selection_rule", "text"),
    ("selection_rule", "thresholds"),
    ("benchmark",),
    ("benchmark", "definition"),
    ("benchmark", "lambda_mode"),
    ("gates_Q",),
    ("gates_Q", "Q3"),
    ("uncertainty",),
    ("uncertainty", "seed"),
    ("uncertainty", "B"),
    ("uncertainty", "block_lengths"),
    ("uncertainty", "bound_level"),
    ("variant_id",),
    ("parent",),
    ("parent", "is_root"),
    ("research_log_entry",),
    ("protocol_sha256",),
)


def _mutate(payload: dict[str, Any], path: tuple[str, ...], mode: str) -> None:
    node: Any = payload
    for key in path[:-1]:
        node = node[key]
    if mode == "absente":
        node.pop(path[-1])
    else:
        node[path[-1]] = None


@pytest.mark.parametrize("path", MANDATORY, ids=[".".join(p) for p in MANDATORY])
@pytest.mark.parametrize("mode", ["absente", "nulle"])
def test_chaque_champ_obligatoire_absent_ou_nul_refuse_l_entree(
    tmp_path: Path, path: tuple[str, ...], mode: str
) -> None:
    payload = fx.manifest()
    _mutate(payload, path, mode)
    with pytest.raises(cc.MissingEvidenceError):
        cc.load_manifest(payload)
    code, out = _run(tmp_path, payload)
    assert code == 2 and out is None


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("anchor_fraction",), "0.7"),
        (("anchor_fraction",), True),
        (("window", "start"), "2023-04-01T00:00:00"),
        (("data", "exec_interval"), 5.0),
        (("fees", "taker"), True),
        (("universe", "provenance"), "propre"),
        (("universe", "candidates"), []),
        (("strategies", "synth_grid", "engine"), "hybrid"),
        (("strategies", "synth_grid", "decision_timeframes"), ["4h", "2h"]),
        (("strategies", "synth_grid", "decision_timeframes"), ["4h", "4h"]),
        (("benchmark", "lambda_mode"), "post"),
        (("uncertainty", "seed"), "20260921"),
        (("uncertainty", "block_lengths"), [10, "21", 42]),
        (("parent", "is_root"), "true"),
        (("variant_id",), ""),
    ],
    ids=[
        "F en chaîne",
        "F booléen",
        "borne sans fuseau",
        "exec_interval flottant",
        "taker booléen",
        "provenance hors liste",
        "univers vide",
        "moteur hors liste",
        "timeframe non déclaré",
        "timeframe en doublon",
        "lambda_mode hors liste",
        "seed en chaîne",
        "block_lengths mêlés",
        "is_root en chaîne",
        "variant_id vide",
    ],
)
def test_chaque_champ_mal_type_ou_hors_liste_refuse_l_entree(
    tmp_path: Path, path: tuple[str, ...], value: Any
) -> None:
    payload = fx.manifest()
    node: Any = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(cc.MissingEvidenceError):
        cc.load_manifest(payload)
    code, out = _run(tmp_path, payload)
    assert code == 2 and out is None


@pytest.mark.parametrize(
    ("path", "value"),
    [(("data", "exec_interval"), 0), (("uncertainty", "seed"), -1)],
    ids=["exec_interval 0", "seed négatif"],
)
def test_une_valeur_hors_domaine_est_une_violation_code_1(
    tmp_path: Path, path: tuple[str, ...], value: Any
) -> None:
    """Décision du 21/09 : hors domaine fourni en entrée → violation, code 1, artefact diagnostic."""
    payload = fx.manifest()
    node: Any = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(cc.InvalidValueError):
        cc.load_manifest(payload)
    code, out = _run(tmp_path, payload)
    assert code == 1
    assert out is not None and out["invalide"] is True and out["anchor"] is None
    assert not (tmp_path / "variants.json").exists()


def test_fenetre_inversee_ou_nulle_refuse_l_entree(tmp_path: Path) -> None:
    payload = fx.manifest()
    payload["window"] = {"start": fx.WINDOW_END.isoformat(), "end": fx.WINDOW_START.isoformat()}
    assert _run(tmp_path, payload)[0] == 2
    payload["window"] = {"start": fx.WINDOW_START.isoformat(), "end": fx.WINDOW_START.isoformat()}
    assert _run(tmp_path, payload, name="m2.json")[0] == 2


def test_un_parent_non_racine_sans_cle_refuse_l_entree(tmp_path: Path) -> None:
    payload = fx.manifest(parent={"is_root": False})
    assert _run(tmp_path, payload)[0] == 2


def test_candidat_hors_couts_ou_hors_strategies_refuse_l_entree(tmp_path: Path) -> None:
    payload = fx.manifest()
    payload["universe"]["candidates"].append(
        {"strategy": fx.STRATEGY, "pair": "ETH/USDC", "params": {"a": 1}}
    )
    assert _run(tmp_path, payload)[0] == 2
    payload = fx.manifest()
    payload["universe"]["candidates"].append(
        {"strategy": "inconnue", "pair": "BTC/USDC", "params": {"a": 1}}
    )
    assert _run(tmp_path, payload, name="m2.json")[0] == 2


def test_identite_canonique_dupliquee_dans_l_univers_est_un_contrat_rompu(tmp_path: Path) -> None:
    """§ A.2 : deux candidats de même identité sont une erreur d'entrée, jamais un tirage au sort."""
    payload = fx.manifest()
    payload["universe"]["candidates"].append(dict(payload["universe"]["candidates"][0]))
    with pytest.raises(cc.EntryRefusedError) as info:
        cc.load_manifest(payload)
    assert info.value.reason == "R0_INVALID_RUN"
    assert _run(tmp_path, payload)[0] == 2


def test_surcharge_par_candidat_des_timeframes_de_decision() -> None:
    payload = fx.manifest()
    payload["universe"]["candidates"][0]["decision_timeframes"] = ["4h"]
    manifest = cc.load_manifest(payload)
    assert manifest.candidates[0].decision_timeframes == ("4h",)
    assert manifest.candidates[1].decision_timeframes == fx.DECISION_TFS
    payload["universe"]["candidates"][0]["decision_timeframes"] = ["15m"]
    with pytest.raises(cc.MissingEvidenceError, match="hors des séries"):
        cc.load_manifest(payload)


def test_F_non_fini_est_une_violation_pas_un_refus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non fini fourni en entrée → code 1, artefact diagnostic invalide (décision du 21/09, § I.1 l.15)."""
    payload = fx.manifest()
    payload["anchor_fraction"] = float("nan")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
    code = ca.main(fx.anchor_argv(tmp_path, path))
    assert code == 1
    out = cc.read_json(tmp_path / "anchor.json")
    assert out["invalide"] is True and out["ok"] is False and out["anchor"] is None
    assert any("non finie" in v for v in out["violations"])
    assert not (tmp_path / "variants.json").exists()
    assert "VIOLATION" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Registre de variantes : idempotence, parenté, altération
# ---------------------------------------------------------------------------


def test_reexecuter_le_meme_manifeste_est_idempotent(tmp_path: Path) -> None:
    payload = fx.manifest()
    code1, out1 = _run(tmp_path, payload)
    registry_after_1 = (tmp_path / "variants.json").read_bytes()
    code2, out2 = _run(tmp_path, payload, output="anchor2.json")
    assert code1 == 0 and code2 == 0 and out1 is not None and out2 is not None
    assert (tmp_path / "variants.json").read_bytes() == registry_after_1, (
        "même enregistrement, registre inchangé"
    )
    assert out2["registry"]["new_entry"] is False
    assert out1["variant_key"] == out2["variant_key"]
    same = {k: v for k, v in out1.items() if k != "registry"}
    assert same == {k: v for k, v in out2.items() if k != "registry"}
    registry = cc.read_json(tmp_path / "variants.json")
    assert list(registry["variants"]) == [out1["variant_key"]]


def test_un_manifeste_different_est_une_nouvelle_variante_avec_parent(tmp_path: Path) -> None:
    """§ A.6 : deux essais qui ne diffèrent que par un champ portent deux clés distinctes."""
    _, root = _run(tmp_path, fx.manifest())
    assert root is not None
    child = fx.manifest(
        provenance="unknown",
        variant_id="synth-child",
        parent={"is_root": False, "variant_key": root["variant_key"]},
    )
    code, out = _run(tmp_path, child, name="child.json", output="anchor_child.json")
    assert code == 0 and out is not None
    assert out["variant_key"] != root["variant_key"]
    assert out["registry"]["new_entry"] is True
    registry = cc.read_json(tmp_path / "variants.json")
    assert len(registry["variants"]) == 2
    assert registry["variants"][out["variant_key"]]["parent"]["variant_key"] == root["variant_key"]


def test_un_parent_absent_du_registre_refuse_l_entree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(tmp_path, fx.manifest())
    orphan = fx.manifest(variant_id="orphan", parent={"is_root": False, "variant_key": "f" * 64})
    code, out = _run(tmp_path, orphan, name="orphan.json", output="anchor_orphan.json")
    assert code == 2 and out is None
    assert "absent du registre" in capsys.readouterr().err
    assert len(cc.read_json(tmp_path / "variants.json")["variants"]) == 1, "rien n'est enregistré"


def test_une_seconde_racine_dans_un_registre_non_vide_refuse_l_entree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(tmp_path, fx.manifest())
    second = fx.manifest(variant_id="another-root", provenance="contaminated")
    code, out = _run(tmp_path, second, name="second.json", output="anchor_second.json")
    assert code == 2 and out is None
    assert "seconde racine" in capsys.readouterr().err
    assert len(cc.read_json(tmp_path / "variants.json")["variants"]) == 1


def test_un_enregistrement_altere_est_une_violation_et_n_est_pas_recopie(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = fx.manifest()
    _, out1 = _run(tmp_path, payload)
    assert out1 is not None
    registry_path = tmp_path / "variants.json"
    registry = cc.read_json(registry_path)
    registry["variants"][out1["variant_key"]]["anchor"] = "2025-05-08T00:00:00+00:00"
    cc.write_json(registry_path, registry)
    altered = registry_path.read_bytes()
    code, out2 = _run(tmp_path, payload, output="anchor2.json")
    assert code == 1
    assert out2 is not None and out2["invalide"] is True and out2["anchor"] is None
    assert any("registre" in v and "anchor" in v for v in out2["violations"])
    assert registry_path.read_bytes() == altered, "le registre altéré n'est pas réécrit par l'outil"
    assert "VIOLATION" in capsys.readouterr().err


def test_un_registre_malforme_refuse_l_entree(tmp_path: Path) -> None:
    (tmp_path / "variants.json").write_text('{"variants": [1, 2]}', encoding="utf-8")
    code, out = _run(tmp_path, fx.manifest())
    assert code == 2 and out is None
    (tmp_path / "variants.json").write_text("{pas du json", encoding="utf-8")
    assert _run(tmp_path, fx.manifest(), name="m2.json")[0] == 2


def test_le_parseur_n_expose_que_des_chemins_et_un_horodatage() -> None:
    """§ 0.6 : aucun paramètre libre — l'ancrage n'est jamais un argument."""
    actions = {a.dest for a in ca.build_parser()._actions} - {"help"}
    assert actions == {"manifest", "registry", "output", "now"}


def test_now_illisible_ou_manifeste_illisible_sort_2(tmp_path: Path) -> None:
    path = fx.write_manifest(tmp_path, fx.manifest())
    argv = fx.anchor_argv(tmp_path, path)
    argv[argv.index("--now") + 1] = "demain"
    assert ca.main(argv) == 2
    assert ca.main(fx.anchor_argv(tmp_path, tmp_path / "absent.json")) == 2
    assert not (tmp_path / "anchor.json").exists()


# ---------------------------------------------------------------------------
# Revue R3 (d) — un non-fini qui atteint la canonicalisation est une violation, jamais un traceback
# ---------------------------------------------------------------------------


def test_revue_R3_nan_dans_un_seuil_du_manifeste_est_une_violation_code_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reproduction Astra : `thresholds.CAPITAL.value = NaN` traversait `canon` en traceback nu."""
    payload = fx.manifest()
    payload["selection_rule"]["thresholds"]["CAPITAL"]["value"] = float("nan")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
    code = ca.main(fx.anchor_argv(tmp_path, path))
    assert code == 1
    out = cc.read_json(tmp_path / "anchor.json")
    assert out["invalide"] is True and out["anchor"] is None
    assert any("non-finite" in v or "non fini" in v for v in out["violations"])
    assert not (tmp_path / "variants.json").exists()
    assert "VIOLATION" in capsys.readouterr().err
