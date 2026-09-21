"""C3 — la sélection (§ A.7 à § A.11, § G.1) et les lignes 3, 4, 6, 8, 9 de la table du § I.1.

La séquence filtrer → filtrer → classer est testée **pure** sur des enregistrements construits
(le contre-exemple du § A.10, les égalités à chaque niveau du départage), puis la chaîne complète
anchor → entry → benchmark → select sur le monde synthétique : témoin sain, permutation, chaque
clause D1-D6 à sa place avec le premier gate imprimé, l'abstention par chacune de ses deux
branches, les paires descriptives, la provenance, la preuve D6 par lot et ses deux contre-exemples,
et les recoupements qui font violation.
"""

# ruff: noqa: E402
from __future__ import annotations

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
import c3_benchmark as cb
import c3_common as cc
import c3_entry as ce
import c3_select as cs

from test_scripts import test_c3_common as fx

# ---------------------------------------------------------------------------
# La chaîne synthétique
# ---------------------------------------------------------------------------


def chain(
    tmp_path: Path,
    manifest_payload: dict[str, Any] | None = None,
    *,
    mutate_observations: Any = None,
    mutate_coverage: Any = None,
    mutate_candles: Any = None,
    **obs_kw: Any,
) -> dict[str, Any]:
    """Écrit le monde, applique les mutations, puis anchor → entry → benchmark ; renvoie les chemins."""
    w = fx.world(tmp_path, manifest_payload, **obs_kw)
    for name, mutate in (
        ("observations", mutate_observations),
        ("coverage", mutate_coverage),
        ("candles", mutate_candles),
    ):
        if mutate is not None:
            data = cc.read_json(w[name])
            mutate(data)
            cc.write_json(w[name], data)
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
    w["entry"] = tmp_path / "entry.json"
    w["benchmark"] = tmp_path / "benchmark.json"
    w["selection"] = tmp_path / "selection.json"
    w["entry_code"] = ce.main(
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
            str(w["entry"]),
            "--now",
            fx.NOW,
        ]
    )
    if w["entry_code"] == 0:
        w["benchmark_code"] = cb.main(
            [
                "--manifest",
                str(w["manifest"]),
                "--anchor",
                str(w["anchor"]),
                "--entry",
                str(w["entry"]),
                "--observations",
                str(w["observations"]),
                "--candles",
                str(w["candles"]),
                "--output",
                str(w["benchmark"]),
                "--now",
                fx.NOW,
            ]
        )
    return w


def select_argv(w: dict[str, Any], *, markdown: bool = False) -> list[str]:
    argv = [
        "--manifest",
        str(w["manifest"]),
        "--anchor",
        str(w["anchor"]),
        "--entry",
        str(w["entry"]),
        "--observations",
        str(w["observations"]),
        "--coverage",
        str(w["coverage"]),
        "--benchmark",
        str(w["benchmark"]),
        "--output",
        str(w["selection"]),
        "--now",
        fx.NOW,
    ]
    if markdown:
        argv += ["--markdown", str(w["selection"].with_suffix(".md"))]
    return argv


def run(w: dict[str, Any], **kw: Any) -> tuple[int, dict[str, Any] | None]:
    code = cs.main(select_argv(w, **kw))
    return code, (cc.read_json(w["selection"]) if w["selection"].exists() else None)


def _first_key(obs: dict[str, Any]) -> str:
    return next(iter(obs))


def _by_identity(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["identity"]: r for r in payload["candidates"]}


def _identity_of(obs: dict[str, Any], key: str) -> str:
    e = obs[key]
    return cc.candidate_identity(e["strategy"], e["pair"], e["params"])


# ---------------------------------------------------------------------------
# Témoin sain
# ---------------------------------------------------------------------------


def test_le_temoin_sain_retient_une_configuration_clean(tmp_path: Path) -> None:
    w = chain(tmp_path)
    assert w["entry_code"] == 0 and w["benchmark_code"] == 0
    code, payload = run(w, markdown=True)
    assert code == 0 and payload is not None and payload["ok"] is True
    assert payload["status"] == "SÉLECTION_VALIDE" and payload["reason"] is None
    assert payload["retained"] is not None and payload["abstention_clause"] is None
    records = payload["candidates"]
    assert len(records) == 6 and all(r["status"] == "ADMISSIBLE" for r in records), [
        (r["status"], r["first_failed_gate"], r["clause_details"]) for r in records
    ]
    assert all(all(r["clauses"].values()) for r in records)
    assert all(r["floor"] == {"P1": True, "P2": True, "P3": True} for r in records)
    assert sorted(payload["ranking"]) == sorted(payload["survivors"])
    assert len(payload["ranking"]) == 6
    assert payload["retained"]["identity"] == payload["ranking"][0]
    ranks = [r["rank"] for r in records]
    assert sorted(ranks) == [1, 2, 3, 4, 5, 6]
    deltas = {r["identity"]: r["scores"]["delta_dd"] for r in records}
    assert [deltas[i] for i in payload["ranking"]] == sorted(deltas.values(), reverse=True)
    assert all(block["status"] == "VOTANTE" for block in payload["pairs"].values())
    assert all(r["d6_report"]["passed"] and r["d6_report"]["lots_present"] for r in records)
    # Contre-exemple 2 : poussière ≠ divergence dans la fixture, et D6 ne rate pas pour cela.
    assert all(
        r["d6_report"]["reported"]["dust_written_off_btc"]
        != r["d6_report"]["reported"]["inventory_divergence_btc"]
        for r in records
    )
    assert all(r["mdd_report"]["abs_diff"] == 0.0 for r in records), (
        "fixture cohérente : l'écart MDD est nul ici"
    )
    assert (
        payload["multiplicity"]["n_admissible"] == 6
        and payload["multiplicity"]["window_already_swept"] is True
    )
    assert payload["lambda_label"] == cc.LAMBDA_LABEL
    assert w["selection"].with_suffix(".md").exists()


def test_permuter_les_candidats_ne_change_rien(tmp_path: Path) -> None:
    """§ A.9 : l'ordre d'entrée n'influence ni un score, ni un rang, ni le choix."""
    w1 = chain(tmp_path / "a")

    def reverse(obs: dict[str, Any]) -> None:
        items = list(obs.items())[::-1]
        obs.clear()
        obs.update(items)

    w2 = chain(tmp_path / "b", mutate_observations=reverse)
    _, p1 = run(w1)
    _, p2 = run(w2)
    assert p1 is not None and p2 is not None
    strip = ("inputs_sha256",)
    assert cc.sig({k: v for k, v in p1.items() if k not in strip}) == cc.sig(
        {k: v for k, v in p2.items() if k not in strip}
    )


# ---------------------------------------------------------------------------
# La séquence pure : contre-exemple § A.10 et égalités à chaque niveau
# ---------------------------------------------------------------------------


def _record(
    identity: str,
    *,
    delta_dd: float,
    delta_sigma: float = 0.0,
    mdd: float = 5.0,
    cagr: float = 3.0,
    net_pnl: float = 10.0,
    status: str = "ADMISSIBLE",
) -> cs.CandidateRecord:
    r = cs.CandidateRecord(
        identity=identity,
        key=identity,
        strategy="s",
        pair="BTC/USDC",
        params={},
        projection_sha256="x",
    )
    r.status = status
    r.scores = {
        "cagr_pct": cagr,
        "delta_dd": delta_dd,
        "delta_sigma": delta_sigma,
        "lambda_dd": 0.1,
        "lambda_sigma": 0.1,
        "mdd_daily": mdd,
    }
    r.floor = {
        "P1": net_pnl > cc.FLOOR_NET_PNL,
        "P2": cagr >= cc.FLOOR_CAGR_PCT,
        "P3": delta_dd > cc.FLOOR_DELTA_DD,
    }
    return r


def test_contre_exemple_A10_filtrer_avant_classer_designe_B() -> None:
    a = _record("a", delta_dd=3.0, cagr=1.5)  # échoue P2
    b = _record("b", delta_dd=1.0, cagr=3.0)
    out = cs.filter_and_rank([a, b])
    assert out["admissible"] == ["a", "b"]
    assert out["survivors"] == ["b"] and out["ranking"] == ["b"]
    assert out["retained"] is b and out["reason"] is None
    # L'issue interdite : classer puis filtrer aurait désigné A.
    assert out["retained"] is not a


def test_departage_a_chaque_niveau() -> None:
    same_dd = [
        _record("zz", delta_dd=2.0, delta_sigma=0.5),
        _record("aa", delta_dd=2.0, delta_sigma=1.5),
    ]
    assert cs.filter_and_rank(same_dd)["ranking"] == ["aa", "zz"], "Δ^σ plus grand d'abord"
    same_sigma = [
        _record("zz", delta_dd=2.0, delta_sigma=1.0, mdd=3.0),
        _record("aa", delta_dd=2.0, delta_sigma=1.0, mdd=6.0),
    ]
    assert cs.filter_and_rank(same_sigma)["ranking"] == ["zz", "aa"], "MDD plus petit ensuite"
    same_all = [
        _record("zz", delta_dd=2.0, delta_sigma=1.0, mdd=3.0),
        _record("aa", delta_dd=2.0, delta_sigma=1.0, mdd=3.0),
    ]
    assert cs.filter_and_rank(same_all)["ranking"] == ["aa", "zz"], (
        "identité lexicographique en dernier"
    )


def test_abstention_par_chacune_de_ses_deux_branches_pure() -> None:
    none = cs.filter_and_rank([_record("a", delta_dd=1.0, status="NOT_ESTIMABLE")])
    assert none["retained"] is None and none["reason"] == "A_NO_ADMISSIBLE_CANDIDATE"
    floor = cs.filter_and_rank([_record("a", delta_dd=-1.0)])
    assert floor["retained"] is None and floor["reason"] == "A_BELOW_FLOOR"


@pytest.mark.parametrize(
    ("provenance", "retained", "expected"),
    [
        ("clean", True, "SÉLECTION_VALIDE"),
        ("clean", False, "ABSTENTION"),
        ("contaminated", True, "SÉLECTION_DESCRIPTIVE"),
        ("contaminated", False, "ABSTENTION"),
        ("unknown", True, "SÉLECTION_DESCRIPTIVE"),
        ("unknown", False, "ABSTENTION"),
    ],
)
def test_table_provenance_x_resultat(provenance: str, retained: bool, expected: str) -> None:
    assert cs.selection_status(provenance, retained) == expected


# ---------------------------------------------------------------------------
# Table I.1, lignes 3, 4, 6, 8, 9 — par la chaîne complète (code 0, artefact écrit)
# ---------------------------------------------------------------------------


def _degrade_btc_coverage(cov: dict[str, Any]) -> None:
    cov["pairs"]["BTC/USDC"]["1440"]["covered_units"] = 700  # 91 % < 97 %


def _d2_first(obs: dict[str, Any]) -> None:
    obs[_first_key(obs)]["warmup"][fx.PREFIX] = fx.warmup_segment(sufficient=False)


def _d3_first(obs: dict[str, Any]) -> None:
    obs[_first_key(obs)][fx.PREFIX]["total_trades"] = 20  # cycles 18 < 25


def _d4_first(obs: dict[str, Any]) -> None:
    values = obs[_first_key(obs)]["equity_daily"][fx.PREFIX]["values"]
    for k in range(len(values) // 2, len(values)):
        values[k] = 0.0


def _d6_first_no_lots(obs: dict[str, Any]) -> None:
    obs[_first_key(obs)]["liquidation"][fx.PREFIX].pop("lots")


def _all_d3(obs: dict[str, Any]) -> None:
    for e in obs.values():
        e[fx.PREFIX]["total_trades"] = 20


TABLE_I1 = [
    pytest.param(
        3,
        "coverage",
        _degrade_btc_coverage,
        "BTC/USDC",
        "NON_ADMISSIBLE",
        "D_NOT_ADMISSIBLE",
        "D1",
        id="L3 D1 : la paire devient DESCRIPTIF",
    ),
    pytest.param(
        4,
        "observations",
        _d2_first,
        None,
        "NON_ADMISSIBLE",
        "D_WARMUP_PREFIX",
        "D2",
        id="L4 D2 sur une partie",
    ),
    pytest.param(
        6, "observations", _d3_first, None, "NOT_ESTIMABLE", "C_COVERAGE", "D3", id="L6 D3"
    ),
    pytest.param(
        6, "observations", _d4_first, None, "NOT_ESTIMABLE", "F_NOT_ESTIMABLE", "D4", id="L6 D4"
    ),
    pytest.param(
        6,
        "observations",
        _d6_first_no_lots,
        None,
        "HORS_USAGE_DÉCISIONNEL",
        "R1_NOT_NORMALISED",
        "D6",
        id="L6 D6 lots absent",
    ),
]


@pytest.mark.parametrize(("line", "target", "mutate", "pair", "status", "reason", "gate"), TABLE_I1)
def test_table_I1_lignes_3_4_6_retirent_le_candidat_et_la_chaine_continue(
    tmp_path: Path,
    line: int,
    target: str,
    mutate: Any,
    pair: str | None,
    status: str,
    reason: str,
    gate: str,
) -> None:
    kw = (
        {"mutate_observations": mutate} if target == "observations" else {"mutate_coverage": mutate}
    )
    w = chain(tmp_path, **kw)
    assert w["entry_code"] == 0, "lignes 3, 4, 6 : l'entrée reste conforme (code 0)"
    code, payload = run(w)
    assert code == 0 and payload is not None and payload["ok"] is True
    obs = cc.read_json(w["observations"])
    records = _by_identity(payload)
    if pair is not None:
        hit = [r for r in payload["candidates"] if r["pair"] == pair]
        assert hit and all(
            r["status"] == status
            and r["candidate_reason"] == reason
            and r["first_failed_gate"] == gate
            for r in hit
        )
        assert payload["pairs"][pair]["status"] == "DESCRIPTIF"
        assert all(r["status"] == "ADMISSIBLE" for r in payload["candidates"] if r["pair"] != pair)
    else:
        hit_record = records[_identity_of(obs, _first_key(obs))]
        assert (
            hit_record["status"] == status
            and hit_record["candidate_reason"] == reason
            and hit_record["first_failed_gate"] == gate
        )
        assert hit_record["scores"] is None, "un candidat retiré ne publie pas de score décisionnel"
        assert sum(1 for r in payload["candidates"] if r["status"] == "ADMISSIBLE") == 5
    assert payload["retained"] is not None, "les autres candidats restent : la chaîne continue"
    assert payload["retained"]["identity"] in payload["admissible"]


def test_ligne_8_ensemble_vide_est_une_abstention_publiee(tmp_path: Path) -> None:
    w = chain(tmp_path, mutate_observations=_all_d3)
    assert w["entry_code"] == 0
    code, payload = run(w)
    assert code == 0 and payload is not None and payload["ok"] is True
    assert payload["status"] == "ABSTENTION" and payload["reason"] == "A_NO_ADMISSIBLE_CANDIDATE"
    assert payload["retained"] is None and payload["abstention_clause"] == cc.ABSTENTION_CLAUSE
    assert payload["admissible"] == [] and payload["ranking"] == []
    assert all(r["first_failed_gate"] == "D3" for r in payload["candidates"]), (
        "le premier gate en échec est imprimé pour chaque candidat"
    )
    assert payload["status"] != "SÉLECTION_VALIDE"


def test_ligne_9_aucun_survivant_est_une_abstention_publiee(tmp_path: Path) -> None:
    """Des candidats admissibles qui perdent de l'argent : P1 échoue pour tous."""

    def losing(obs: dict[str, Any]) -> None:
        for e in obs.values():
            e[fx.PREFIX]["net_pnl"] = -5.0

    w = chain(tmp_path, mutate_observations=losing)
    code, payload = run(w)
    assert code == 0 and payload is not None
    assert payload["status"] == "ABSTENTION" and payload["reason"] == "A_BELOW_FLOOR"
    assert len(payload["admissible"]) == 6 and payload["survivors"] == []
    assert all(r["floor"]["P1"] is False for r in payload["candidates"])
    assert payload["abstention_clause"] == cc.ABSTENTION_CLAUSE


# ---------------------------------------------------------------------------
# Paires descriptives, provenance, D3 inapplicable, λ, alertes
# ---------------------------------------------------------------------------


def test_paire_sans_comparateur_est_descriptive_et_ses_candidats_E_NO_BENCHMARK(
    tmp_path: Path,
) -> None:
    def drop_btc_entry(candles: dict[str, Any]) -> None:
        candles["pairs"]["BTC/USDC"]["exec"] = candles["pairs"]["BTC/USDC"]["exec"][1:]

    w = chain(tmp_path, mutate_candles=drop_btc_entry)
    code, payload = run(w)
    assert code == 0 and payload is not None
    assert (
        payload["pairs"]["BTC/USDC"]["status"] == "DESCRIPTIF"
        and payload["pairs"]["SOL/USDC"]["status"] == "VOTANTE"
    )
    btc = [r for r in payload["candidates"] if r["pair"] == "BTC/USDC"]
    assert all(
        r["status"] == "NOT_ESTIMABLE"
        and r["candidate_reason"] == "E_NO_BENCHMARK"
        and r["first_failed_gate"] == "benchmark"
        for r in btc
    )
    assert payload["retained"]["pair"] == "SOL/USDC", (
        "elle retire BTC, elle n'exclut pas SOL (§ D.3)"
    )


@pytest.mark.parametrize("provenance", ["contaminated", "unknown"])
def test_provenance_non_clean_rend_une_selection_descriptive(
    tmp_path: Path, provenance: str
) -> None:
    w = chain(tmp_path, fx.manifest(provenance=provenance))
    code, payload = run(w)
    assert code == 0 and payload is not None
    assert payload["retained"] is not None
    assert payload["status"] == "SÉLECTION_DESCRIPTIVE"
    assert payload["status"] != "SÉLECTION_VALIDE", "unknown n'est jamais assimilé à clean"


def test_D3_inapplicable_pour_une_accumulation_sans_vente(tmp_path: Path) -> None:
    payload_m = fx.manifest()
    payload_m["strategies"]["synth_signal"] = {
        "engine": "signal",
        "decision_timeframes": ["4h", "1d"],
    }
    payload_m["universe"]["candidates"][0]["strategy"] = "synth_signal"

    def accumulation(obs: dict[str, Any]) -> None:
        # `write_json` trie les clés : on cible l'entrée par sa stratégie, pas par sa position.
        e = next(v for v in obs.values() if v["strategy"] == "synth_signal")
        e[fx.PREFIX]["total_trades"] = 101
        e[fx.PREFIX]["winning_trades"] = 0
        e[fx.PREFIX]["losing_trades"] = 0
        e["liquidation"] = None

    w = chain(tmp_path, payload_m, mutate_observations=accumulation)
    assert w["entry_code"] == 0
    code, payload = run(w)
    assert code == 0 and payload is not None
    obs = cc.read_json(w["observations"])
    key = next(k for k, v in obs.items() if v["strategy"] == "synth_signal")
    r = _by_identity(payload)[_identity_of(obs, key)]
    assert (
        r["status"] == "NOT_ESTIMABLE"
        and r["candidate_reason"] == "C_COVERAGE"
        and r["first_failed_gate"] == "D3"
    )
    assert "inapplicable" in r["clause_details"]["D3"] and r["recomputed"]["cycles"] is None
    assert r["clauses"]["D6"] is False, (
        "sans bloc liquidation, D6 échoue aussi — mais D3 est imprimé en premier"
    )


def test_moteur_grid_sans_bloc_liquidation_echoue_D3_puis_D6(tmp_path: Path) -> None:
    w = chain(
        tmp_path,
        mutate_observations=lambda obs: obs[_first_key(obs)].__setitem__("liquidation", None),
    )
    code, payload = run(w)
    assert code == 0 and payload is not None
    obs = cc.read_json(w["observations"])
    r = _by_identity(payload)[_identity_of(obs, _first_key(obs))]
    assert (
        r["clauses"]["D3"] is False
        and r["clauses"]["D6"] is False
        and r["first_failed_gate"] == "D3"
    )


def test_lambda_sans_croisement_rend_NOT_ESTIMABLE_F_NOT_ESTIMABLE(tmp_path: Path) -> None:
    def crash(obs: dict[str, Any]) -> None:
        values = obs[_first_key(obs)]["equity_daily"][fx.PREFIX]["values"]
        for k in range(300, 330):
            values[k] = values[299] * (1 - 0.03 * (k - 299))  # -90 % : MDD au-delà du B&H

    w = chain(tmp_path, mutate_observations=crash)
    code, payload = run(w)
    assert code == 0 and payload is not None
    obs = cc.read_json(w["observations"])
    r = _by_identity(payload)[_identity_of(obs, _first_key(obs))]
    assert (
        r["status"] == "NOT_ESTIMABLE"
        and r["candidate_reason"] == "F_NOT_ESTIMABLE"
        and r["first_failed_gate"] == "λ_dd"
    )
    assert r["clauses"]["D4"] is True, "la NAV reste positive : D4 passe, c'est λ qui retire"
    assert r["scores"] is None and r["identity"] not in payload["admissible"]


def test_un_jour_sous_moins_50_pct_est_une_alerte_pas_un_retrait_par_D4(tmp_path: Path) -> None:
    def one_bad_day(obs: dict[str, Any]) -> None:
        values = obs[_first_key(obs)]["equity_daily"][fx.PREFIX]["values"]
        values[400] = values[399] * 0.45

    w = chain(tmp_path, mutate_observations=one_bad_day)
    code, payload = run(w)
    assert code == 0 and payload is not None
    obs = cc.read_json(w["observations"])
    r = _by_identity(payload)[_identity_of(obs, _first_key(obs))]
    assert r["clauses"]["D4"] is True and r["alerts"] and "alerte" in r["alerts"][0]


# ---------------------------------------------------------------------------
# D6 : preuve par lot, identités exactes, les deux contre-exemples
# ---------------------------------------------------------------------------


def _liq(obs: dict[str, Any]) -> dict[str, Any]:
    return obs[_first_key(obs)]["liquidation"][fx.PREFIX]


def _first_record(w: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    obs = cc.read_json(w["observations"])
    return _by_identity(payload)[_identity_of(obs, _first_key(obs))]


def test_contre_exemple_1_des_frais_arbitrairement_faibles_ne_passent_pas_D6(
    tmp_path: Path,
) -> None:
    def tiny_fee(obs: dict[str, Any]) -> None:
        liq = _liq(obs)
        liq["fees"] = "0.000000000001"
        liq["lots"][0]["fee"] = "0.000000000001"

    w = chain(tmp_path, mutate_observations=tiny_fee)
    code, payload = run(w)
    assert code == 0 and payload is not None
    r = _first_record(w, payload)
    assert (
        r["clauses"]["D6"] is False
        and r["status"] == "HORS_USAGE_DÉCISIONNEL"
        and r["candidate_reason"] == "R1_NOT_NORMALISED"
    )
    assert any("fee" in d and "gross × taker" in d for d in r["d6_report"]["details"])


def test_contre_exemple_2_poussiere_differente_de_la_divergence_ne_fait_pas_echouer_D6(
    tmp_path: Path,
) -> None:
    def real_dust(obs: dict[str, Any]) -> None:
        liq = _liq(obs)
        liq["dust_written_off_btc"] = "7E-28"
        liq["inventory_divergence_btc"] = "1E-27"

    w = chain(tmp_path, mutate_observations=real_dust)
    code, payload = run(w)
    assert code == 0 and payload is not None
    r = _first_record(w, payload)
    assert r["clauses"]["D6"] is True and r["status"] == "ADMISSIBLE"
    assert r["d6_report"]["reported"]["dust_written_off_btc"] == "7E-28"


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        pytest.param(
            lambda liq: liq.__setitem__(
                "price", str(Decimal(liq["reference_price"]) * Decimal("0.99"))
            ),
            "price_identity",
            id="prix ≠ référence × (1−s−sl)",
        ),
        pytest.param(
            lambda liq: liq.__setitem__("spread_pct", "0.0009"),
            "spread_pct",
            id="spread ≠ manifeste",
        ),
        pytest.param(
            lambda liq: liq.__setitem__("trades", liq["positions"] + 2),
            "trades_positions",
            id="deux lots inconnus",
        ),
        pytest.param(
            lambda liq: liq.__setitem__("residual_net_proceeds", "3"),
            "residual_net_iff_unknown",
            id="résidu sans lot inconnu",
        ),
        pytest.param(lambda liq: liq["lots"].pop(), "lots_count", id="un lot de moins que trades"),
        pytest.param(
            lambda liq: liq["lots"][0].__setitem__(
                "gross_usdc", str(Decimal(liq["lots"][0]["gross_usdc"]) + 1)
            ),
            "lots_gross_sum",
            id="Σ gross ≠ gross_usdc",
        ),
        pytest.param(
            lambda liq: liq["lots"][0].__setitem__("entry_price", None),
            "lots_known",
            id="lot à coût inconnu non déclaré",
        ),
    ],
)
def test_chaque_identite_exacte_de_D6_fausse_retire_le_candidat(
    tmp_path: Path, mutate: Any, fragment: str
) -> None:
    w = chain(tmp_path, mutate_observations=lambda obs: mutate(_liq(obs)))
    assert w["entry_code"] == 0, "la forme reste valide : c'est D6 qui tranche, pas l'entrée"
    code, payload = run(w)
    assert code == 0 and payload is not None
    r = _first_record(w, payload)
    assert r["clauses"]["D6"] is False and r["candidate_reason"] == "R1_NOT_NORMALISED"
    assert (
        any(fragment in d for d in r["d6_report"]["details"])
        or r["d6_report"]["checks"].get(fragment) is False
    )


# ---------------------------------------------------------------------------
# Recoupements → violation ; refus → rien d'écrit
# ---------------------------------------------------------------------------


def test_ecart_MDD_enregistre_recalcule_est_rapporte_sans_violation(tmp_path: Path) -> None:
    def nudge(obs: dict[str, Any]) -> None:
        obs[_first_key(obs)][fx.PREFIX]["max_drawdown_pct_daily"] += 1e-13

    w = chain(tmp_path, mutate_observations=nudge)
    code, payload = run(w)
    assert code == 0 and payload is not None and payload["violations"] == []
    r = _first_record(w, payload)
    assert 0 < r["mdd_report"]["abs_diff"] < 1e-12 and "non classé" in r["mdd_report"]["note"]


def test_D2_selon_l_entree_contredit_par_le_recalcul_est_une_violation(tmp_path: Path) -> None:
    w = chain(tmp_path)
    entry = cc.read_json(w["entry"])
    entry["candidate_diagnostics"].append(
        {
            "key": "x",
            "identity": "0" * 64,
            "clause": "D2",
            "reason": "D_WARMUP_PREFIX",
            "timeframes_insufficient": ["1w"],
        }
    )
    cc.write_json(w["entry"], entry)
    bench = cc.read_json(w["benchmark"])
    bench["inputs_sha256"]["entry"] = cc.file_sha256(w["entry"])
    cc.write_json(w["benchmark"], bench)
    code, payload = run(w)
    assert code == 1 and payload is not None and payload["invalide"] is True
    assert any("D2" in v and "désaccord" in v for v in payload["violations"])
    assert payload["status"] is None and payload["retained"] is None


def test_sufficient_declare_contredit_est_une_violation_a_la_selection_aussi(
    tmp_path: Path,
) -> None:
    w = chain(tmp_path)
    obs = cc.read_json(w["observations"])
    obs[_first_key(obs)]["warmup"][fx.PREFIX]["1d"]["sufficient"] = False
    cc.write_json(w["observations"], obs)
    for name in ("entry", "benchmark"):
        art = cc.read_json(w[name])
        art["inputs_sha256"]["observations"] = cc.file_sha256(w["observations"])
        cc.write_json(w[name], art)
    code, payload = run(w)
    assert (
        code == 1 and payload is not None and any("sufficient" in v for v in payload["violations"])
    )


def test_empreintes_discordantes_sont_une_violation(tmp_path: Path) -> None:
    w = chain(tmp_path)
    obs = cc.read_json(w["observations"])
    obs[_first_key(obs)]["phase"] = "9"
    cc.write_json(w["observations"], obs)
    code, payload = run(w)
    assert (
        code == 1
        and payload is not None
        and any("inputs_sha256.observations" in v for v in payload["violations"])
    )


def test_entree_non_verte_refuse_de_tourner(tmp_path: Path) -> None:
    w = chain(tmp_path)
    entry = cc.read_json(w["entry"])
    entry["ok"] = False
    entry["exit_code"] = 2
    cc.write_json(w["entry"], entry)
    code, payload = run(w)
    assert code == 2 and payload is None


def test_couverture_differente_de_celle_validee_est_une_violation(tmp_path: Path) -> None:
    w = chain(tmp_path)
    cov = cc.read_json(w["coverage"])
    cov["source"] = "autre"
    cc.write_json(w["coverage"], cov)
    code, payload = run(w)
    assert code == 1 and payload is not None and any("coverage" in v for v in payload["violations"])


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda w: cc.write_json(
                w["benchmark"], {**cc.read_json(w["benchmark"]), "candidates": {}}
            ),
            id="benchmark sans candidats",
        ),
        pytest.param(
            lambda w: cc.write_json(
                w["anchor"],
                {k: v for k, v in cc.read_json(w["anchor"]).items() if k != "variant_key"},
            ),
            id="ancrage sans clé de variante",
        ),
    ],
)
def test_bloc_obligatoire_absent_refuse_l_entree(tmp_path: Path, mutate: Any) -> None:
    w = chain(tmp_path)
    mutate(w)
    for name in ("entry", "benchmark"):
        art = cc.read_json(w[name])
        for dep in ("anchor",):
            if dep in art.get("inputs_sha256", {}):
                art["inputs_sha256"][dep] = cc.file_sha256(w[dep])
        cc.write_json(w[name], art)
    bench = cc.read_json(w["benchmark"])
    bench["inputs_sha256"]["entry"] = cc.file_sha256(w["entry"])
    cc.write_json(w["benchmark"], bench)
    code, payload = run(w)
    assert code == 2 and payload is None


def test_nan_fourni_dans_une_trajectoire_est_une_violation_code_1(tmp_path: Path) -> None:
    w = chain(tmp_path)
    obs = cc.read_json(w["observations"])
    obs[_first_key(obs)]["equity_daily"][fx.PREFIX]["values"][9] = float("nan")
    w["observations"].write_text(json.dumps(obs, allow_nan=True), encoding="utf-8")
    for name in ("entry", "benchmark"):
        art = cc.read_json(w[name])
        art["inputs_sha256"]["observations"] = cc.file_sha256(w["observations"])
        cc.write_json(w[name], art)
    code, payload = run(w)
    assert code == 1 and payload is not None and payload["invalide"] is True


def test_le_parseur_n_expose_que_des_chemins_et_un_horodatage() -> None:
    actions = {a.dest for a in cs.build_parser()._actions} - {"help"}
    assert actions == {
        "manifest",
        "anchor",
        "entry",
        "observations",
        "coverage",
        "benchmark",
        "output",
        "markdown",
        "now",
    }
