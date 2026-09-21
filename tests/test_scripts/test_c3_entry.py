"""C3 — la validité d'entrée (§ I-A), l'ordre gelé, `not_assertable`, la promotion D2 (§ I.1 l.4-5, § D.3).

Le témoin sain est un monde synthétique conforme (manifeste, observations avec préfixe et futurs,
couverture) ; chaque contre-exemple en isole un défaut et vérifie **l'assertion qui échoue, celles
qui sont sautées, le code, et ce que l'artefact porte**. La seule sortie réelle de ce protocole — le
refus de l'artefact du rejeu, `D_WARMUP_PREFIX` — est reproduite ici sur le fichier réel quand il est
présent, contre le manifeste et l'artefact committés.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import timedelta
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
import c3_entry as ce

from test_scripts import test_c3_common as fx

REAL_OBSERVATIONS = _project_root / "results" / "rejeu_grid_20260919" / "P7_phase1_grid.json"
REAL_DIR = _project_root / "results" / "c3a_entry_validation"
REAL_MANIFEST = REAL_DIR / "manifest_rejeu_grid_20260919.json"
REAL_ENTRY = REAL_DIR / "entry_rejeu_grid_20260919.json"


def _anchor(w: dict[str, Any]) -> None:
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


def _entry_argv(
    w: dict[str, Any], *, coverage: bool = True, output: str = "entry.json", markdown: bool = False
) -> list[str]:
    argv = [
        "--manifest",
        str(w["manifest"]),
        "--anchor",
        str(w["anchor"]),
        "--observations",
        str(w["observations"]),
        "--output",
        str(w["manifest"].parent / output),
        "--now",
        fx.NOW,
    ]
    if coverage:
        argv += ["--coverage", str(w["coverage"])]
    if markdown:
        argv += ["--markdown", str(w["manifest"].parent / "entry.md")]
    return argv


def _run(w: dict[str, Any], **kw: Any) -> tuple[int, dict[str, Any]]:
    code = ce.main(_entry_argv(w, **kw))
    out = w["manifest"].parent / kw.get("output", "entry.json")
    assert out.exists(), "c3_entry écrit toujours son artefact (§ I.1 l.1558)"
    return code, cc.read_json(out)


def _sound(tmp_path: Path, **obs_kw: Any) -> dict[str, Any]:
    w = fx.world(tmp_path, **obs_kw)
    _anchor(w)
    return w


def _mutate_observations(w: dict[str, Any], mutate: Any) -> None:
    obs = cc.read_json(w["observations"])
    mutate(obs)
    cc.write_json(w["observations"], obs)


def _first(obs: dict[str, Any]) -> dict[str, Any]:
    return obs[next(iter(obs))]


def _statuses(payload: dict[str, Any]) -> dict[str, str]:
    return {row["id"]: row["status"] for row in payload["assertions"]}


# ---------------------------------------------------------------------------
# Témoin sain
# ---------------------------------------------------------------------------


def test_le_temoin_sain_rend_0_et_toutes_les_assertions_vertes(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    code, payload = _run(w, markdown=True)
    assert code == 0
    assert payload["ok"] is True and payload["invalide"] is False and payload["refusal"] is None
    assert payload["not_assertable"] == [] and payload["candidate_diagnostics"] == []
    assert payload["sentence"] is None
    assert all(status == "ok" for status in _statuses(payload).values())
    assert [row["id"] for row in payload["assertions"]] == [f"I-A.{i}" for i in range(1, 9)] + [
        "I-A.fin"
    ]
    assert payload["coverage"]["status"] == "evaluated" and payload["coverage"][
        "sha256"
    ] == cc.file_sha256(w["coverage"])
    assert payload["observations"]["sha256"] == cc.file_sha256(w["observations"])
    assert payload["inputs_sha256"]["anchor"] == cc.file_sha256(w["anchor"])
    assert payload["anchor"] == fx.ANCHOR.isoformat() and payload["n_candidates"] == 6
    assert (tmp_path / "entry.md").exists() and "| I-A.8" in (tmp_path / "entry.md").read_text(
        encoding="utf-8"
    )


def test_le_temoin_prefixe_seul_est_conforme(tmp_path: Path) -> None:
    """§ A.12 : les segments futurs sont optionnels ; une entrée qui ne porte que le préfixe passe."""
    w = _sound(tmp_path, with_futures=False)
    code, payload = _run(w)
    assert code == 0 and payload["refusal"] is None


def test_liquidation_et_dca_counters_nuls_ne_sont_pas_des_erreurs_d_entree(tmp_path: Path) -> None:
    """Blocs optionnels : `null` est la valeur que le runner exporte hors grid / hors DCA ; D6 tranchera."""
    w = _sound(tmp_path)
    _mutate_observations(w, lambda obs: _first(obs).__setitem__("liquidation", None))
    code, payload = _run(w)
    assert code == 0 and payload["refusal"] is None


# ---------------------------------------------------------------------------
# Ordre gelé : chaque assertion peut échouer, et tout ce qui suit est sauté, jamais vert
# ---------------------------------------------------------------------------


def _fail_1(w: dict[str, Any]) -> None:
    _mutate_observations(w, lambda obs: _first(obs).__setitem__("strategy", 5))


def _fail_2(w: dict[str, Any]) -> None:
    _mutate_observations(w, lambda obs: _first(obs).__setitem__("fees", "binance"))


def _fail_3(w: dict[str, Any]) -> None:
    later = (fx.ANCHOR + timedelta(days=1)).isoformat()
    _mutate_observations(
        w, lambda obs: _first(obs)["period"].__setitem__(f"{fx.PREFIX}_end", later)
    )


def _fail_4(w: dict[str, Any]) -> None:
    def dup(obs: dict[str, Any]) -> None:
        obs["dup"] = json.loads(json.dumps(_first(obs)))

    _mutate_observations(w, dup)


def _fail_6(w: dict[str, Any]) -> None:
    _mutate_observations(w, lambda obs: _first(obs)["warmup"][fx.PREFIX].pop("1w"))


def _fail_7(w: dict[str, Any]) -> None:
    cov = cc.read_json(w["coverage"])
    cov["window"]["end"] = fx.WINDOW_END.isoformat()
    cc.write_json(w["coverage"], cov)


def _fail_8(w: dict[str, Any]) -> None:
    def all_insufficient(obs: dict[str, Any]) -> None:
        for entry in obs.values():
            entry["warmup"][fx.PREFIX] = fx.warmup_segment(sufficient=False)

    _mutate_observations(w, all_insufficient)


@pytest.mark.parametrize(
    ("mutate", "failing", "reason", "scope"),
    [
        pytest.param(_fail_1, "I-A.1", "R0_INVALID_RUN", "run", id="I-A.1 forme"),
        pytest.param(_fail_2, "I-A.2", "R0_INVALID_RUN", "run", id="I-A.2 D5"),
        pytest.param(_fail_3, "I-A.3", "R0_INVALID_RUN", "run", id="I-A.3 bornes"),
        pytest.param(_fail_4, "I-A.4", "R0_INVALID_RUN", "run", id="I-A.4 identités"),
        pytest.param(_fail_6, "I-A.6", "R0_INVALID_RUN", "run", id="I-A.6 amorçage"),
        pytest.param(_fail_7, "I-A.7", "R0_INVALID_RUN", "run", id="I-A.7 couverture"),
        pytest.param(_fail_8, "I-A.8", "D_WARMUP_PREFIX", "artefact", id="I-A.8 D2 totalité"),
    ],
)
def test_chaque_assertion_echoue_a_sa_place_et_saute_les_suivantes(
    tmp_path: Path, mutate: Any, failing: str, reason: str, scope: str
) -> None:
    w = _sound(tmp_path)
    mutate(w)
    code, payload = _run(w)
    assert code == 2
    assert payload["ok"] is False and payload["invalide"] is False
    assert payload["refusal"]["assertion"] == failing
    assert payload["refusal"]["reason"] == reason and payload["refusal"]["scope"] == scope
    assert payload["sentence"] == cc.NON_RECEVABLE_SENTENCE
    statuses = _statuses(payload)
    ids = [f"I-A.{i}" for i in range(1, 9)]
    for identifier in ids[: ids.index(failing)]:
        assert statuses[identifier] in ("ok", "not_assertable"), identifier
    assert statuses[failing] == "failed"
    for identifier in ids[ids.index(failing) + 1 :]:
        assert statuses[identifier] == "skipped", identifier
    assert "I-A.fin" not in statuses, "après un refus, la règle de fin n'a rien à ajouter"


# ---------------------------------------------------------------------------
# Forme : chaque bloc de la liste blanche, absent et null
# ---------------------------------------------------------------------------

MANDATORY: tuple[tuple[str, ...], ...] = (
    ("strategy",),
    ("pair",),
    ("params",),
    ("effective_params",),
    ("metrics_version",),
    ("replay_version",),
    ("exchange",),
    ("fees",),
    ("pair_costs",),
    ("pair_costs", "spread"),
    ("pair_costs_file",),
    ("min_order_usdc",),
    ("period",),
    ("period", "train_start"),
    ("period", "train_end"),
    ("train",),
    ("train", "n_daily_returns"),
    ("train", "starting_balance"),
    ("train", "max_drawdown_pct_daily"),
    ("equity_daily",),
    ("equity_daily", "train"),
    ("equity_daily", "train", "values"),
    ("equity_daily", "train", "start"),
    ("warmup",),
    ("warmup", "train"),
    ("warmup", "train", "4h", "sufficient"),
    ("warmup", "train", "4h", "largest_gap_candles"),
    ("rejections",),
    ("rejections", "train"),
    ("liquidation", "train"),
    ("liquidation", "train", "positions"),
    ("liquidation", "train", "fees"),
    ("liquidation", "train", "price"),
)


def _set_path(node: Any, path: tuple[str, ...], mode: str, value: Any = None) -> None:
    for key in path[:-1]:
        node = node[key]
    if mode == "absente":
        node.pop(path[-1])
    elif mode == "nulle":
        node[path[-1]] = None
    else:
        node[path[-1]] = value


@pytest.mark.parametrize("path", MANDATORY, ids=[".".join(p) for p in MANDATORY])
@pytest.mark.parametrize("mode", ["absente", "nulle"])
def test_chaque_bloc_obligatoire_absent_ou_nul_refuse_l_entree_a_la_forme(
    tmp_path: Path, path: tuple[str, ...], mode: str
) -> None:
    nullable_ok = path[-1] in cc.NULLABLE_FIELDS and mode == "nulle"
    w = _sound(tmp_path)
    _mutate_observations(w, lambda obs: _set_path(_first(obs), path, mode))
    code, payload = _run(w)
    if nullable_ok:
        assert code == 0, "un champ nullable à null est une valeur documentée"
        return
    assert code == 2
    assert (
        payload["refusal"]["assertion"] == "I-A.1"
        and payload["refusal"]["reason"] == "R0_INVALID_RUN"
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("strategy",), 5),
        (("metrics_version",), "2"),
        (("pair_costs", "spread"), "abc"),
        (("equity_daily", "train", "values"), "x"),
        (("warmup", "train", "4h", "sufficient"), 1),
        (("warmup", "train", "4h", "stale_by_candles"), "0"),
        (("liquidation", "train", "positions"), "2"),
        (("liquidation", "train", "lots"), {"a": 1}),
        (("liquidation", "train", "lots"), [{"gross_usdc": "1", "fee": "0.0025"}]),
        (("exec_interval",), "5"),
        (("liquidation",), "none"),
        (("dca_counters",), []),
    ],
    ids=[
        "strategy int",
        "metrics_version str",
        "spread non Decimal",
        "values str",
        "sufficient int",
        "stale str",
        "positions str",
        "lots mapping",
        "lot sans amount",
        "exec_interval str",
        "liquidation str",
        "dca_counters list",
    ],
)
def test_chaque_bloc_mal_type_refuse_l_entree_a_la_forme(
    tmp_path: Path, path: tuple[str, ...], value: Any
) -> None:
    w = _sound(tmp_path)
    _mutate_observations(w, lambda obs: _set_path(_first(obs), path, "valeur", value))
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.1"


def test_un_segment_futur_malforme_refuse_l_entree(tmp_path: Path) -> None:
    """§ A.12 : les futurs restent présents et bien formés — un futur cassé est une erreur de forme."""
    w = _sound(tmp_path)
    _mutate_observations(
        w, lambda obs: _first(obs)["equity_daily"]["test"].__setitem__("values", "x")
    )
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.1"


def test_un_non_fini_fourni_est_une_violation_code_1(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    obs = cc.read_json(w["observations"])
    _first(obs)["equity_daily"][fx.PREFIX]["values"][10] = float("nan")
    w["observations"].write_text(json.dumps(obs, allow_nan=True), encoding="utf-8")
    code, payload = _run(w)
    assert code == 1
    assert payload["invalide"] is True and payload["ok"] is False
    assert any("non finie" in v for v in payload["violations"])


# ---------------------------------------------------------------------------
# D5, bornes, identités, amorçage
# ---------------------------------------------------------------------------


def test_une_borne_posterieure_a_T_est_refusee_jamais_tronquee(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    later = (fx.ANCHOR + timedelta(days=3)).isoformat()

    def shift(obs: dict[str, Any]) -> None:
        e = _first(obs)
        e["period"][f"{fx.PREFIX}_end"] = later
        e["equity_daily"][fx.PREFIX]["end"] = later

    _mutate_observations(w, shift)
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.3"
    assert "jamais tronquée" in payload["refusal"]["detail"]


def test_grille_ou_compte_de_rendements_incoherents_refusent_l_entree(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    _mutate_observations(w, lambda obs: _first(obs)[fx.PREFIX].__setitem__("n_daily_returns", 700))
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.3"
    w2 = _sound(tmp_path / "b")
    _mutate_observations(w2, lambda obs: _first(obs)["equity_daily"][fx.PREFIX]["values"].pop())
    code, payload = _run(w2)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.3"


def test_candidat_hors_univers_et_univers_sans_observation(tmp_path: Path) -> None:
    w = _sound(tmp_path)

    def extra(obs: dict[str, Any]) -> None:
        e = json.loads(json.dumps(_first(obs)))
        e["params"] = {"inconnu": 1}
        obs["extra"] = e

    _mutate_observations(w, extra)
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.4"
    assert "hors de l'univers" in payload["refusal"]["detail"]
    w2 = _sound(tmp_path / "b")
    _mutate_observations(w2, lambda obs: obs.pop(next(iter(obs))))
    code, payload = _run(w2)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.4"
    assert "sans observation" in payload["refusal"]["detail"]


def test_intervalle_de_decision_different_du_manifeste_refuse_l_entree(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    _mutate_observations(
        w, lambda obs: _first(obs)["warmup"][fx.PREFIX]["4h"].__setitem__("interval", 60)
    )
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.2"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("metrics_version",), 1),
        (("train", "metrics_version"), 1),
        (("replay_version",), 1),
        (("exchange",), "kraken"),
        (("pair_costs_file",), "autre.json"),
        (("pair_costs", "slippage"), "0.0009"),
        (("min_order_usdc",), 10.0),
        (("train", "starting_balance"), 999.0),
        (("exec_interval",), 15),
    ],
    ids=[
        "metrics_version 1",
        "metrics_version segment",
        "replay_version 1",
        "exchange",
        "pair_costs_file",
        "slippage",
        "min_order",
        "capital",
        "exec_interval 15",
    ],
)
def test_chaque_contrat_D5_different_du_manifeste_refuse_l_entree(
    tmp_path: Path, path: tuple[str, ...], value: Any
) -> None:
    w = _sound(tmp_path)
    _mutate_observations(w, lambda obs: _set_path(_first(obs), path, "valeur", value))
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.2"


def test_sufficient_declare_contredit_par_le_recalcul_est_une_violation(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    _mutate_observations(
        w, lambda obs: _first(obs)["warmup"][fx.PREFIX]["1d"].__setitem__("sufficient", False)
    )
    code, payload = _run(w)
    assert code == 1 and payload["invalide"] is True
    assert any("sufficient" in v and "recalculé" in v for v in payload["violations"])


# ---------------------------------------------------------------------------
# not_assertable : jamais verte, ne bloque pas, interdit ok=True
# ---------------------------------------------------------------------------


def test_exec_interval_sans_porteur_est_consigne_puis_refuse_en_fin(tmp_path: Path) -> None:
    w = _sound(tmp_path, exec_interval=None)
    code, payload = _run(w)
    assert code == 2
    statuses = _statuses(payload)
    assert statuses["I-A.2"] == "not_assertable"
    assert statuses["I-A.8"] == "ok", (
        "une clause non assertable ne bloque pas les assertions suivantes"
    )
    assert statuses["I-A.fin"] == "failed"
    assert (
        payload["refusal"]["assertion"] == "I-A.fin"
        and payload["refusal"]["reason"] == "R0_INVALID_RUN"
    )
    assert "contrat non vérifiable" in payload["refusal"]["detail"]
    assert [n["clause"] for n in payload["not_assertable"]] == ["D5 — intervalle d'exécution"]


def test_couverture_absente_est_consignee_puis_refusee_en_fin(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    code, payload = _run(w, coverage=False)
    assert code == 2
    assert _statuses(payload)["I-A.7"] == "not_assertable"
    assert payload["coverage"] == {"path": None, "sha256": None, "status": "not_provided"}
    assert payload["refusal"]["assertion"] == "I-A.fin"


def test_couverture_malformee_echoue_a_sa_place_pas_en_fin(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    cov = cc.read_json(w["coverage"])
    cov["pairs"]["BTC/USDC"]["10080"]["expected_units"] = 109
    cc.write_json(w["coverage"], cov)
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.7"
    assert "recalculé depuis les bornes" in payload["refusal"]["detail"]
    w2 = _sound(tmp_path / "b")
    cov = cc.read_json(w2["coverage"])
    cov["pairs"].pop("SOL/USDC")
    cc.write_json(w2["coverage"], cov)
    code, payload = _run(w2)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.7"


def test_D2_sur_une_partie_laisse_la_chaine_continuer(tmp_path: Path) -> None:
    """§ I.1 l.4 : `ok=True` avec des diagnostics de candidats non vides est légitime."""
    w = _sound(tmp_path)
    _mutate_observations(
        w,
        lambda obs: _first(obs)["warmup"].__setitem__(
            fx.PREFIX, fx.warmup_segment(sufficient=False)
        ),
    )
    code, payload = _run(w)
    assert code == 0 and payload["ok"] is True and payload["refusal"] is None
    assert payload["n_candidates_d2_failed"] == 1
    diag = payload["candidate_diagnostics"][0]
    assert diag["clause"] == "D2" and diag["reason"] == "D_WARMUP_PREFIX"
    assert diag["timeframes_insufficient"] == ["1d", "1w"] and diag["identity"] is not None


def test_D2_sur_la_totalite_prime_sur_les_clauses_non_assertables(tmp_path: Path) -> None:
    """La forme de l'artefact réel : sans porteur ni couverture, D2 sur tous → D_WARMUP_PREFIX, pas R0."""
    w = _sound(tmp_path, exec_interval=None, sufficient=False)
    code, payload = _run(w, coverage=False)
    assert code == 2
    assert (
        payload["refusal"]["reason"] == "D_WARMUP_PREFIX"
        and payload["refusal"]["assertion"] == "I-A.8"
    )
    assert payload["n_candidates_d2_failed"] == payload["n_candidates"] == 6
    assert len(payload["not_assertable"]) == 2
    assert payload["sentence"] == cc.NON_RECEVABLE_SENTENCE


# ---------------------------------------------------------------------------
# L'ancrage amont : exigé vert, empreintes recoupées, T recalculé
# ---------------------------------------------------------------------------


def test_ancrage_amont_en_echec_refuse_l_entree(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    anchor = cc.read_json(w["anchor"])
    anchor["ok"] = False
    anchor["exit_code"] = 2
    cc.write_json(w["anchor"], anchor)
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.0"
    assert payload["assertions"] == []


def test_ancrage_declare_different_du_recalcul_est_une_violation(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    anchor = cc.read_json(w["anchor"])
    anchor["anchor"] = "2025-05-08T00:00:00+00:00"
    cc.write_json(w["anchor"], anchor)
    code, payload = _run(w)
    assert code == 1 and any("recalcul" in v for v in payload["violations"])


def test_ancrage_calcule_sur_un_autre_manifeste_est_une_violation(tmp_path: Path) -> None:
    """Les empreintes détectent la discordance : anchor.json ne vient pas de ce manifeste."""
    w = _sound(tmp_path)
    other = fx.manifest(variant_id="other")
    cc.write_json(w["manifest"], other)
    code, payload = _run(w)
    assert code == 1 and any("inputs_sha256.manifest" in v for v in payload["violations"])


def test_anchor_bloc_incomplet_refuse_l_entree(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    cc.write_json(w["anchor"], {"ok": True})
    code, payload = _run(w)
    assert code == 2 and payload["refusal"]["assertion"] == "I-A.0"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_le_parseur_n_expose_que_des_chemins_et_un_horodatage() -> None:
    actions = {a.dest for a in ce.build_parser()._actions} - {"help"}
    assert actions == {
        "manifest",
        "anchor",
        "observations",
        "coverage",
        "output",
        "markdown",
        "now",
    }


def test_entrees_illisibles_sortent_2_sans_ecrire(tmp_path: Path) -> None:
    w = _sound(tmp_path)
    argv = _entry_argv(w)
    argv[argv.index("--observations") + 1] = str(tmp_path / "absent.json")
    assert ce.main(argv) == 2
    assert not (tmp_path / "entry.json").exists()


# ---------------------------------------------------------------------------
# La sortie réelle : refus de l'artefact du rejeu (§ D.3), reproduit contre les fichiers committés
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (REAL_OBSERVATIONS.exists() and REAL_MANIFEST.exists() and REAL_ENTRY.exists()),
    reason="artefact du rejeu ou livrable réel absent",
)
def test_l_artefact_du_rejeu_est_refuse_D_WARMUP_PREFIX_et_intact(tmp_path: Path) -> None:
    before = cc.file_sha256(REAL_OBSERVATIONS)
    w = {
        "manifest": REAL_MANIFEST,
        "registry": tmp_path / "variants.json",
        "anchor": tmp_path / "anchor.json",
        "observations": REAL_OBSERVATIONS,
        "coverage": tmp_path / "none.json",
    }
    _anchor(w)
    argv = _entry_argv(w, coverage=False, output="entry.json")
    argv[argv.index("--output") + 1] = str(tmp_path / "entry.json")
    code = ce.main(argv)
    payload = cc.read_json(tmp_path / "entry.json")
    assert code == 2
    assert (
        payload["refusal"]["reason"] == "D_WARMUP_PREFIX"
        and payload["refusal"]["scope"] == "artefact"
    )
    assert payload["refusal"]["assertion"] == "I-A.8"
    assert payload["n_candidates"] == 96 and payload["n_candidates_d2_failed"] == 96
    assert {n["assertion"] for n in payload["not_assertable"]} == {"I-A.2", "I-A.7"}
    assert payload["sentence"] == cc.NON_RECEVABLE_SENTENCE
    assert payload["run_scope"], "la portée du run réel est dite dans l'artefact"
    assert cc.file_sha256(REAL_OBSERVATIONS) == before, "l'artefact du rejeu reste intact"
    committed = cc.read_json(REAL_ENTRY)
    for key in (
        "assertions",
        "refusal",
        "candidate_diagnostics",
        "not_assertable",
        "n_candidates",
        "run_scope",
        "universe_provenance",
        "exit_code",
    ):
        assert payload[key] == committed[key], key
    # Le chemin des observations est celui de l'invocation ; seule l'empreinte est comparable.
    assert payload["observations"]["sha256"] == committed["observations"]["sha256"]
    assert payload["observations"]["sha256"] == before
