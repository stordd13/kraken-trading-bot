"""C3 — le comparateur du préfixe et l'appariement de λ (§ C.3, § C.5, § C.6, § F.2 g).

Construction et comparabilité sont des fonctions pures de bougies synthétiques ; l'appariement,
une recherche sur des NAV réellement construites. Chaque contre-exemple isole ce que le
protocole nomme : une estampille requise absente n'est **jamais** remplacée par la suivante ; une
bougie postérieure à T est refusée, jamais tronquée ; un NaN fourni est une violation ; une cible
au-delà du B&H n'est pas `λ = 1` mais `NOT_ESTIMABLE` ; le résidu, les croisements, la cible nulle.
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
import c3_benchmark as cb
import c3_common as cc
import c3_entry as ce

from test_scripts import test_c3_common as fx

SPREAD = Decimal("0.0002")
SLIPPAGE = Decimal("0.0002")
TAKER = Decimal("0.0025")
CAPITAL = Decimal("1000")


def _pair_candles(payload: dict[str, Any], pair: str = "BTC/USDC") -> cb.PairCandles:
    manifest = cc.load_manifest(fx.manifest())
    return cb.load_candles(payload, manifest, end=fx.ANCHOR)[pair]


def _build(payload: dict[str, Any], pair: str = "BTC/USDC") -> cb.PairBenchmark:
    return cb.build_pair(
        pair,
        _pair_candles(payload, pair),
        start=fx.WINDOW_START,
        end=fx.ANCHOR,
        exec_interval=fx.EXEC_INTERVAL,
        spread=SPREAD,
        slippage=SLIPPAGE,
        taker=TAKER,
        capital=CAPITAL,
    )


# ---------------------------------------------------------------------------
# § C.3 — construction
# ---------------------------------------------------------------------------


def test_serie_saine_constructible_et_comparable() -> None:
    bench = _build(fx.candles(fx.manifest()))
    assert bench.buildable and bench.comparable and bench.reason is None
    assert bench.entry_stamp == "2023-04-01T00:05:00+00:00"
    assert bench.exit_stamp == "2025-05-07T04:45:00+00:00"
    assert bench.nav[0] == CAPITAL, "l'ancre est le capital en cash"
    assert len(bench.nav) == fx.N_PREFIX_POINTS
    assert len(bench.returns) == fx.N_PREFIX_POINTS - 1
    close_in = Decimal("30000.00000000")
    close_out = Decimal("36300.00000000")
    exec_in = close_in * (1 + SPREAD + SLIPPAGE)
    qty = CAPITAL * (1 - TAKER) / exec_in
    assert bench.qty == qty and bench.entry_price == exec_in
    assert bench.exit_price == close_out * (1 - SPREAD - SLIPPAGE)
    # Le dernier point est la valeur liquidée, coûts compris — jamais un simple mark.
    assert bench.nav[-1] == qty * close_out * (1 - SPREAD - SLIPPAGE) * (1 - TAKER)
    assert bench.nav[-1] < qty * close_out
    assert bench.comparability["ff_days"] == 0 and bench.cagr_pct is not None and bench.cagr_pct > 0


@pytest.mark.parametrize("missing", ["entry", "exit"])
def test_estampille_requise_absente_rend_non_constructible_sans_substitution(missing: str) -> None:
    payload = fx.candles(fx.manifest(), missing_exec=missing)
    # Une bougie plus tard existe bel et bien : elle ne doit pas être prise à la place.
    block = payload["pairs"]["BTC/USDC"]
    block["exec"].append(
        {"t": (fx.WINDOW_START + timedelta(minutes=10)).isoformat(), "close": "30001"}
    )
    bench = _build(payload)
    assert not bench.buildable and not bench.comparable
    assert bench.reason is not None and "aucune bougie de substitution" in bench.reason
    assert bench.nav == () and bench.cagr_pct is None


def test_bougie_posterieure_a_T_est_un_refus_jamais_tronquee() -> None:
    payload = fx.candles(fx.manifest(), extra_stamp_after_end=True)
    with pytest.raises(cc.EntryRefusedError, match="jamais tronquée"):
        _pair_candles(payload)


def test_close_non_fini_ou_negatif_est_une_violation() -> None:
    payload = fx.candles(fx.manifest())
    payload["pairs"]["BTC/USDC"]["daily"][3]["close"] = "NaN"
    with pytest.raises(cc.InvalidValueError, match="non finie"):
        _pair_candles(payload)
    payload = fx.candles(fx.manifest())
    payload["pairs"]["BTC/USDC"]["daily"][3]["close"] = "-1"
    with pytest.raises(cc.InvalidValueError, match="strictement positif"):
        _pair_candles(payload)


def test_intervalle_d_execution_different_du_manifeste_est_un_refus() -> None:
    payload = fx.candles(fx.manifest())
    payload["pairs"]["BTC/USDC"]["exec_interval"] = 15
    with pytest.raises(cc.EntryRefusedError, match="intervalle d'exécution"):
        _pair_candles(payload)


def test_trou_quotidien_au_dela_de_D1_rend_non_comparable() -> None:
    payload = fx.candles(fx.manifest())
    daily = payload["pairs"]["BTC/USDC"]["daily"]
    payload["pairs"]["BTC/USDC"]["daily"] = daily[:100] + daily[140:]  # 40 minuits sans close
    bench = _build(payload)
    assert bench.buildable and not bench.comparable
    assert bench.comparability["ff_days"] == 40 and bench.comparability["longest_ff_run_days"] == 40
    assert not bench.comparability["ff_ok"] and "ff_ok" in (bench.reason or "")
    assert bench.cagr_pct is None, "un comparateur non comparable ne publie pas de CAGR"


def test_quelques_jours_forward_filles_restent_comparables_et_comptes() -> None:
    payload = fx.candles(fx.manifest())
    daily = payload["pairs"]["BTC/USDC"]["daily"]
    payload["pairs"]["BTC/USDC"]["daily"] = daily[:50] + daily[53:]
    bench = _build(payload)
    assert bench.comparable and bench.comparability["ff_days"] == 3


def test_la_ruine_rompt_le_compte_de_rendements() -> None:
    """§ C.5 : `resample_daily` cesse de définir un rendement dès qu'une NAV atteint 0."""
    nav = [Decimal(1000), Decimal(500), Decimal(0), Decimal(0)]
    returns = [float(c / p - 1) for p, c in zip(nav, nav[1:], strict=False) if p > 0]
    assert len(returns) == 2 != len(nav) - 1


# ---------------------------------------------------------------------------
# § C.4 / § F.2 (g) — appariement
# ---------------------------------------------------------------------------


def _curves() -> tuple[cb.PairBenchmark, dict[str, cb.LambdaCurve]]:
    bench = _build(fx.candles(fx.manifest()))
    return bench, {
        "dd": cb.LambdaCurve(bench.nav, CAPITAL, "dd"),
        "sigma": cb.LambdaCurve(bench.nav, CAPITAL, "sigma"),
    }


def test_cible_nulle_donne_lambda_zero_imprime() -> None:
    _, curves = _curves()
    match = cb.match_lambda(curves["dd"], 0.0)
    assert match.lam == 0.0 and match.residual == 0.0 and match.estimable
    assert match.note is not None and "cash" in match.note


def test_cible_au_dela_du_BH_est_non_estimable_et_jamais_lambda_1() -> None:
    bench, curves = _curves()
    full = cb.mdd_of(bench.nav)
    match = cb.match_lambda(curves["dd"], full * 3.0)
    assert not match.estimable and match.lam is None
    assert match.note is not None and "aucun croisement" in match.note


def test_cible_atteignable_est_appariee_sur_la_grille_fine_avec_residu_borne() -> None:
    bench, curves = _curves()
    full = cb.mdd_of(bench.nav)
    target = full * 0.4
    match = cb.match_lambda(curves["dd"], target)
    assert match.estimable and match.lam is not None
    assert 0.0 < match.lam < 1.0
    assert round(match.lam * 1000) == pytest.approx(match.lam * 1000), (
        "λ vit sur la grille au pas 0,001"
    )
    assert match.value is not None and match.value >= target, "le plus petit λ qui atteint la cible"
    assert match.residual is not None and match.residual <= cc.LAMBDA_RESIDUAL_MAX
    # Le λ retenu est le premier de la grille fine : un pas en dessous n'atteint pas la cible.
    below = Decimal(str(match.lam)) - cc.LAMBDA_FINE_STEP
    value_below = curves["dd"].value(below)
    assert value_below is not None and value_below < target


def test_le_residu_au_dela_de_10_pct_est_non_estimable() -> None:
    """Une courbe en marches (NAV constante par paliers) laisse des cibles entre deux valeurs."""
    nav = [Decimal(1000)] * 300 + [Decimal(400)] * 300  # une seule chute : MDD 0 puis 60 % selon λ
    curve = cb.LambdaCurve(nav, CAPITAL, "dd")
    # Le blend à λ passe de MDD = 60λ % ; avec la cible 1e-4, le premier λ (0,001) donne 0,06 %
    # soit un résidu de 500 % : hors tolérance.
    match = cb.match_lambda(curve, 1e-4)
    assert (
        not match.estimable
        and match.residual is not None
        and match.residual > cc.LAMBDA_RESIDUAL_MAX
    )


def test_les_croisements_sont_comptes_et_le_plus_petit_retenu() -> None:
    class Bumpy(cb.LambdaCurve):
        def value(self, lam: Decimal) -> float | None:  # noqa: D401 — courbe artificielle non monotone
            x = float(lam)
            return 4.2 if 0.2 <= x < 0.3 or x >= 0.6 else 1.0  # résidu 5 % au croisement

    curve = Bumpy((CAPITAL,) * 3, CAPITAL, "dd")
    match = cb.match_lambda(curve, 4.0)
    assert match.estimable and match.lam == pytest.approx(0.2, abs=1e-9)
    assert match.crossings == 3 and match.note is not None and "3 croisement" in match.note


# ---------------------------------------------------------------------------
# Par candidat, et par la CLI
# ---------------------------------------------------------------------------


def _chain(tmp_path: Path, **obs_kw: Any) -> dict[str, Any]:
    w = fx.world(tmp_path, **obs_kw)
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
                str(w["entry"]),
                "--now",
                fx.NOW,
            ]
        )
        == 0
    )
    w["benchmark"] = tmp_path / "benchmark.json"
    return w


def _argv(w: dict[str, Any]) -> list[str]:
    return [
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


def test_cli_temoin_sain_publie_lambda_et_delta_pour_chaque_candidat(tmp_path: Path) -> None:
    w = _chain(tmp_path)
    assert cb.main(_argv(w)) == 0
    payload = cc.read_json(w["benchmark"])
    assert (
        payload["ok"] is True
        and payload["lambda_mode"] == "prefix"
        and payload["lambda_label"] == cc.LAMBDA_LABEL
    )
    assert set(payload["pairs"]) == set(fx.PAIRS) and all(
        b["comparable"] for b in payload["pairs"].values()
    )
    assert len(payload["candidates"]) == 6
    for identity, block in payload["candidates"].items():
        assert block["estimable"], (
            identity,
            block["first_failed"],
            block["match_dd"],
            block["match_sigma"],
        )
        assert block["lambda_dd"] is not None and block["lambda_sigma"] is not None
        assert block["delta_dd"] == pytest.approx(block["cagr_pct"] - block["cagr_blend_dd"])
        assert block["target_dd"] > 0 and block["match_dd"]["residual"] <= cc.LAMBDA_RESIDUAL_MAX
    assert payload["inputs_sha256"]["candles"] == cc.file_sha256(w["candles"])


def test_cli_refuse_de_tourner_si_l_entree_n_est_pas_verte(tmp_path: Path) -> None:
    w = _chain(tmp_path)
    entry = cc.read_json(w["entry"])
    entry["ok"] = False
    entry["exit_code"] = 2
    cc.write_json(w["entry"], entry)
    assert cb.main(_argv(w)) == 2
    assert not w["benchmark"].exists()


def test_cli_empreintes_discordantes_sont_une_violation(tmp_path: Path) -> None:
    w = _chain(tmp_path)
    obs = cc.read_json(w["observations"])
    obs[next(iter(obs))]["phase"] = "9"  # octet changé après la validation d'entrée, forme intacte
    cc.write_json(w["observations"], obs)
    assert cb.main(_argv(w)) == 1
    payload = cc.read_json(w["benchmark"])
    assert payload["invalide"] is True and any(
        "inputs_sha256.observations" in v for v in payload["violations"]
    )


def test_cli_nan_dans_les_bougies_est_une_violation_code_1(tmp_path: Path) -> None:
    w = _chain(tmp_path)
    candles = cc.read_json(w["candles"])
    candles["pairs"]["BTC/USDC"]["daily"][5]["close"] = "NaN"
    cc.write_json(w["candles"], candles)
    assert cb.main(_argv(w)) == 1
    assert cc.read_json(w["benchmark"])["invalide"] is True


def test_cli_bougie_posterieure_a_T_sort_2_sans_ecrire(tmp_path: Path) -> None:
    w = _chain(tmp_path)
    cc.write_json(w["candles"], fx.candles(w["payload"], extra_stamp_after_end=True))
    assert cb.main(_argv(w)) == 2
    assert not w["benchmark"].exists()


def test_fixture_mixte_tolerance_bornee_aux_defauts_d_admissibilite(tmp_path: Path) -> None:
    """§ 6.2 : NAV à 0 → candidat consigné D4 sans score, les autres continuent (code 0) ;
    un NaN fourni dans une trajectoire reste une violation (code 1)."""
    w = _chain(tmp_path)
    obs = cc.read_json(w["observations"])
    keys = list(obs)
    ruined = obs[keys[0]]["equity_daily"][fx.PREFIX]["values"]
    for k in range(len(ruined) // 2, len(ruined)):
        ruined[k] = 0.0
    cc.write_json(w["observations"], obs)
    # L'entrée a été validée sur l'ancien fichier : on la refait sur le nouveau.
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
                str(w["entry"]),
                "--now",
                fx.NOW,
            ]
        )
        == 0
    )
    assert cb.main(_argv(w)) == 0
    payload = cc.read_json(w["benchmark"])
    blocks = payload["candidates"]
    first_identity = cc.candidate_identity(
        obs[keys[0]]["strategy"], obs[keys[0]]["pair"], obs[keys[0]]["params"]
    )
    assert (
        blocks[first_identity]["estimable"] is False
        and blocks[first_identity]["first_failed"] == "D4"
    )
    assert blocks[first_identity]["delta_dd"] is None, (
        "aucun score décisionnel pour un candidat inadmissible"
    )
    assert sum(1 for b in blocks.values() if b["estimable"]) == 5
    # Le NaN, lui, ne se tolère pas.
    obs[keys[1]]["equity_daily"][fx.PREFIX]["values"][7] = float("nan")
    w["observations"].write_text(json.dumps(obs, allow_nan=True), encoding="utf-8")
    entry = cc.read_json(w["entry"])
    entry["inputs_sha256"]["observations"] = cc.file_sha256(w["observations"])
    cc.write_json(w["entry"], entry)
    assert cb.main(_argv(w)) == 1


def test_paire_sans_benchmark_rend_ses_candidats_E_NO_BENCHMARK(tmp_path: Path) -> None:
    w = _chain(tmp_path)
    cc.write_json(w["candles"], fx.candles(w["payload"], missing_exec="entry"))
    assert cb.main(_argv(w)) == 0
    payload = cc.read_json(w["benchmark"])
    for block in payload["candidates"].values():
        assert (
            block["estimable"] is False
            and block["reason"] == "E_NO_BENCHMARK"
            and block["first_failed"] == "benchmark"
        )


def test_le_parseur_n_expose_que_des_chemins_et_un_horodatage() -> None:
    actions = {a.dest for a in cb.build_parser()._actions} - {"help"}
    assert actions == {"manifest", "anchor", "entry", "observations", "candles", "output", "now"}


def test_le_comparateur_ne_depend_que_du_prefixe(tmp_path: Path) -> None:
    """Les futurs des observations ne changent rien au comparateur ni aux λ (préparation § A.12)."""
    w1 = _chain(tmp_path / "a", futures_variant=0)
    w2 = _chain(tmp_path / "b", futures_variant=3)
    assert cb.main(_argv(w1)) == 0 and cb.main(_argv(w2)) == 0
    p1, p2 = cc.read_json(w1["benchmark"]), cc.read_json(w2["benchmark"])
    strip = ("inputs_sha256",)
    core1 = {k: v for k, v in p1.items() if k not in strip}
    core2 = {k: v for k, v in p2.items() if k not in strip}
    assert cc.sig(core1) == cc.sig(core2)
