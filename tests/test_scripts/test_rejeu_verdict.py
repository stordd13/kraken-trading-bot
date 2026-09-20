"""Rejeu diagnostic grid — le verdict (§ G, § H) et la validité des analyses (§ I-B).

Un seul fichier de tests pour ``scripts/audit/rejeu_verdict.py`` et
``scripts/audit/rejeu_validate_analysis.py`` : la liste close des nouveaux fichiers de tests
(§ I-A.14) n'en porte qu'une entrée, et les deux scripts partagent leurs artefacts d'entrée.

Tout est synthétique : le verdict est une fonction pure de sept objets JSON gelés, donc ni DB ni
campagne ne sont nécessaires. Les fixtures sont construites pour piéger ce que la pré-spécification
nomme, pas le chemin heureux :

* les trois verdicts sont **atteignables**, chacun par sa propre voie ;
* un ``candidat`` qui perd **une** des six bornes retombe en ``inconclusif (F_CANNOT_SEPARATE)`` ;
* une config qui passe les gates et une **autre** qui tient les bornes ne font **pas** un
  ``candidat`` — § G.3 exige la **même** configuration ;
* un échec § I-A court-circuite tout en ``R0_INVALID_RUN``, même avec tous les autres artefacts
  parfaits, et un flag ``b4_flags`` (I-A.13) donne ``R1_ACCOUNTING_FLAG`` ;
* SOL seule ne peut produire ni ``candidat`` ni ``dépriorisation`` (§ D.3) ;
* ``lambda_mode == "frozen_sensitivity"`` rend ``candidat`` inatteignable (§ F.4) ;
* les non-règles du § G.5 sont prouvées : la dégénérescence, le clamp, ``train``/``test``, le
  Sharpe et le multiple de frais G3 ne changent **jamais** un verdict ;
* la chaîne de verdict est **identique octet pour octet** sur deux exécutions des mêmes entrées.

Côté § I-B : le rerun qui reproduit ``LB_j`` bit à bit (par artefact de rerun **et** par rerun
réel de ``rejeu_effect``), les graines gelées, la règle des réplications dégénérées, le premier
gate en échec de chaque config inéligible, et ``signatures.json`` / ``clamp.json`` présents ou
explicitement non productibles.
"""

# ruff: noqa: E402
from __future__ import annotations

import json
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

from p7_grids import GRID_ATR_GRID, expand_grid
import rejeu_common as rc
import rejeu_effect as eff
import rejeu_validate_analysis as rva
import rejeu_verdict as rv
import run_p7_grid_search as p7

NOW = "2026-09-19T12:00:00+00:00"
OTHER_NOW = "2027-01-02T03:04:05+00:00"
CAMPAIGN_SHA = "a" * 64
GRID = expand_grid(GRID_ATR_GRID)
BTC, SOL = rc.PAIRS
N_POINTS = rc.SEGMENT_POINTS["all"]


# ---------------------------------------------------------------------------
# Synthetic artifacts
# ---------------------------------------------------------------------------


def _key(pair: str, params: dict[str, Any]) -> str:
    return p7.make_key(rc.STRATEGY, pair, params, "1")


def _lb(
    value: float = 1.5,
    *,
    overrides: dict[tuple[str, str], float] | None = None,
    lengths: tuple[int, ...] = rc.BLOCK_LENGTHS,
) -> dict[str, dict[str, float]]:
    block = {str(length): dict.fromkeys(rc.MATCHINGS, value) for length in lengths}
    for (label, matching), override in (overrides or {}).items():
        block[label][matching] = override
    return block


def _config(
    params: dict[str, Any],
    *,
    cycles: int | None = 53,
    nnz: int = 400,
    gates: tuple[bool, bool, bool] = (True, True, True),
    lb: dict[str, dict[str, float]] | None = None,
    delta_dd: float = 3.0,
    delta_sigma: float = 2.0,
    mdd: float = 12.0,
    status: str = rc.STATUS_ELIGIBLE,
    first_failing_gate: str | None = None,
    degenerate: int = 0,
    sharpe: float | None = 0.93,
    fee_multiple: float | None = 15.0,
) -> dict[str, Any]:
    """One ``effect.json`` config block, consistent with the § G.1 ladder by construction."""
    eligible = status == rc.STATUS_ELIGIBLE
    gate_map: dict[str, bool | None] = (
        dict(zip(("G1", "G2", "G4"), gates, strict=True))
        if eligible
        else {"G1": None, "G2": None, "G4": None}
    )
    lb_block = (lb if lb is not None else _lb()) if eligible else None
    if eligible and first_failing_gate is None:
        first_failing_gate = next(
            (name for name, value in zip(("G1", "G2", "G4"), gates, strict=True) if not value),
            None,
        )
    six = bool(
        lb_block
        and all(
            math.isfinite(lb_block.get(str(length), {}).get(matching, float("nan")))
            and lb_block[str(length)][matching] > 0.0
            for length in rc.BLOCK_LENGTHS
            for matching in rc.MATCHINGS
        )
    )
    return {
        "params": dict(params),
        "cycles": cycles,
        "nnz": nnz,
        "status": status,
        "first_failing_gate": first_failing_gate,
        "net_pnl": 45.72,
        "total_return_pct": 7.5,
        "total_fees": 3.02,
        "fee_multiple": fee_multiple,
        "mdd_daily": mdd,
        "sharpe_ratio": sharpe,
        "lambda_dd": 0.08 if eligible else None,
        "lambda_sigma": 0.11 if eligible else None,
        "match_residual_dd": 0.01 if eligible else None,
        "match_residual_sigma": 0.02 if eligible else None,
        "lambda_sigma_crossings": 1 if eligible else None,
        "beta_hat": 0.21,
        "delta_dd": delta_dd if eligible else None,
        "delta_sigma": delta_sigma if eligible else None,
        "gates": gate_map,
        "passes_gates": eligible and all(gates),
        "se": {str(length): 1.1 for length in rc.BLOCK_LENGTHS} if eligible else None,
        "LB": lb_block,
        "LB_all_six_positive": six,
        "jackknife_delta_dd": 2.8 if eligible else None,
        "degenerate_replications": degenerate,
    }


def _pair_block(
    configs: dict[str, dict[str, Any]],
    *,
    admissible: bool = True,
    warmup: str = "W1",
    comparable: bool = True,
    not_estimable: bool | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    eligible = sorted(
        key for key, config in configs.items() if config["status"] == rc.STATUS_ELIGIBLE
    )
    return {
        "admissible": admissible,
        "warmup_class": warmup,
        "benchmark_comparable": comparable,
        "n_J_calc": len(configs),
        "J_calc": sorted(configs),
        "J_eligible": eligible,
        "q_FWE": {
            str(length): dict.fromkeys(rc.MATCHINGS, 0.4) for length in rc.BLOCK_LENGTHS
        },
        "se_ratio_max_min": 1.4,
        "configs": configs,
        "not_estimable": (not eligible) if not_estimable is None else not_estimable,
        "reason": reason if reason is not None else (None if eligible else "C_COVERAGE"),
        "coverage_note": None,
    }


def _effect(
    pairs: dict[str, dict[str, Any]],
    *,
    lambda_mode: str = eff.LAMBDA_MODE_REESTIMATED,
    replications: int = rc.BOOTSTRAP_B,
    lengths: tuple[int, ...] = rc.BLOCK_LENGTHS,
) -> dict[str, Any]:
    return {
        "generated_at": NOW,
        "base_sha": rc.BASE_SHA,
        "prespec": {"path": eff.PRESPEC_RELPATH, "sha256": "b" * 64},
        "B": replications,
        "block_lengths": [int(length) for length in lengths],
        "seeds": {
            pair: {
                str(length): eff.stream_seed(rc.PAIRS.index(pair), length) for length in lengths
            }
            for pair in pairs
        },
        "numpy_version": np.__version__,
        "lambda_mode": lambda_mode,
        "lambda_mode_label": (
            eff.FROZEN_LABEL if lambda_mode == eff.LAMBDA_MODE_FROZEN else None
        ),
        "pairs": pairs,
        "coverage_table": {pair: [] for pair in pairs},
    }


def _coverage(**admissible: bool) -> dict[str, Any]:
    return {
        "generated_at": NOW,
        "exchange": rc.EXCHANGE,
        "pairs": {
            pair: {"admissible": admissible.get(pair.split("/")[0], pair == BTC)}
            for pair in rc.PAIRS
        },
    }


def _benchmark(**comparable: bool) -> dict[str, Any]:
    pairs: dict[str, Any] = {}
    for pair in rc.PAIRS:
        ok = comparable.get(pair.split("/")[0], pair == BTC)
        pairs[pair] = {
            "buildable": ok,
            "reason": None if ok else "first candle 271 days late",
            "nav": [1000.0, 1001.0] if ok else None,
            "returns": [0.001] if ok else None,
            "comparability": {"comparable": ok},
        }
    return {"generated_at": NOW, "exchange": rc.EXCHANGE, "pairs": pairs}


def _validation_campaign(failed: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "generated_at": NOW,
        "base_sha": rc.BASE_SHA,
        "artifact": "results/rejeu_grid_20260919/P7_phase1_grid.json",
        "artifact_sha256": CAMPAIGN_SHA,
        "ok": not failed,
        "exit_code": 0 if not failed else 2,
        "assertions": [],
        "failed": list(failed),
    }


def _validation_analysis(ok: bool = True, failed: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "generated_at": NOW,
        "ok": ok,
        "exit_code": 0 if ok else 2,
        "assertions": [],
        "failed": list(failed),
    }


def _signatures(classes: int = 45) -> dict[str, Any]:
    return {
        "generated_at": NOW,
        "caveat": rc.INDISCERNIBILITY_CAVEAT,
        "fields_included": ["all", "equity_daily"],
        "fields_excluded": ["params"],
        "pairs": {
            BTC: {"n_configs": 48, "n_classes_exact": classes, "n_classes_tolerant": classes},
        },
        "b4_retro": {"file": "results/B4_P7_phase1_cross_validate.json"},
    }


def _clamp(producible: bool = True, reason: str | None = None) -> dict[str, Any]:
    return {
        "generated_at": NOW,
        "producible": producible,
        "reason": reason if not producible else None,
        "label": "mesure distributionnelle, pas un rejeu",
        "atr_period": rc.ATR_PERIOD,
        "max_spacing_pct": float(rc.MAX_SPACING_PCT),
        "pairs": {} if not producible else {BTC: {"n_closes": 6570, "couples": []}},
    }


def _write(tmp_path: Path, name: str, payload: Any) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _paths(tmp_path: Path, **payloads: Any) -> dict[str, Path]:
    """The seven frozen inputs, written to ``tmp_path``. A payload of ``None`` is NOT written."""
    defaults = {
        "validation_campaign": _validation_campaign(),
        "validation_analysis": _validation_analysis(),
        "data_coverage": _coverage(),
        "benchmark": _benchmark(),
        "signatures": _signatures(),
        "clamp": _clamp(),
        "effect": _effect({BTC: _pair_block(_candidat_configs())}),
    }
    defaults.update(payloads)
    tmp_path.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, payload in defaults.items():
        path = tmp_path / f"{name}.json"
        if payload is not None:
            path.write_text(json.dumps(payload), encoding="utf-8")
        out[name] = path
    out["output"] = tmp_path / "verdict.json"
    return out


def _argv(paths: dict[str, Path], *extra: str) -> list[str]:
    return [
        "--validation-campaign", str(paths["validation_campaign"]),
        "--validation-analysis", str(paths["validation_analysis"]),
        "--data-coverage", str(paths["data_coverage"]),
        "--benchmark", str(paths["benchmark"]),
        "--signatures", str(paths["signatures"]),
        "--clamp", str(paths["clamp"]),
        "--effect", str(paths["effect"]),
        "--output", str(paths["output"]),
        "--now", NOW,
        *extra,
    ]


def _verdict(paths: dict[str, Path], *extra: str) -> tuple[int, dict[str, Any]]:
    code = rv.main(_argv(paths, *extra))
    return code, json.loads(paths["output"].read_text(encoding="utf-8"))


def _candidat_configs() -> dict[str, dict[str, Any]]:
    """Two eligible BTC configs that pass the gates and hold the six bounds."""
    return {
        _key(BTC, GRID[0]): _config(GRID[0], delta_dd=3.0, delta_sigma=2.0),
        _key(BTC, GRID[1]): _config(GRID[1], delta_dd=1.0, delta_sigma=0.5),
    }


# ---------------------------------------------------------------------------
# 1. The three verdicts are each reachable
# ---------------------------------------------------------------------------


def test_candidat_is_reachable(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_CANDIDAT
    assert payload["reason"] is None
    btc = payload["pairs"][BTC]
    assert btc["verdict"] == rc.VERDICT_CANDIDAT
    assert btc["n_eligible"] == 2 and btc["n_passing_gates"] == 2 and btc["n_candidat"] == 2
    # § G.3: the representative is the argmax of Δ̂^dd, named AFTER, as carrier of the evidence.
    assert btc["representative"] == _key(BTC, GRID[0])
    assert payload["pairs"][SOL]["verdict"] == rc.VERDICT_DESCRIPTIF
    assert payload["verdict_string"] == (
        f"REJEU_GRID_20260919 | famille=candidat | raison=- | {BTC}=candidat | "
        f"{SOL}=descriptif | representant={_key(BTC, GRID[0])} | "
        f"prespec={rv.prespec_descriptor()['sha256'][:16]} | campagne={CAMPAIGN_SHA[:16]}"
    )


def test_depriorisation_is_reachable(tmp_path: Path) -> None:
    """Merited, not by default: every eligible config fails a point gate (§ H)."""
    configs = {
        _key(BTC, params): _config(params, gates=(True, False, True), lb=_lb(2.0))
        for params in GRID[:3]
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_DEPRIORISATION
    assert payload["reason"] == rv.REASON_POINT_NEGATIVE
    btc = payload["pairs"][BTC]
    assert btc["verdict"] == rc.VERDICT_DEPRIORISATION
    assert btc["n_eligible"] == 3 and btc["n_passing_gates"] == 0 and btc["n_candidat"] == 0
    assert btc["representative"] is None


def test_inconclusif_is_reachable_when_no_config_holds_the_bounds(tmp_path: Path) -> None:
    """A positive point estimate that fails the family bound is inconclusif, NEVER dépriorisation."""
    configs = {
        _key(BTC, params): _config(params, lb=_lb(-0.2)) for params in GRID[:2]
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "F_CANNOT_SEPARATE"
    assert payload["pairs"][BTC]["n_passing_gates"] == 2
    assert payload["pairs"][BTC]["n_candidat"] == 0


# ---------------------------------------------------------------------------
# 2. The six bounds, on the SAME configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", [str(length) for length in rc.BLOCK_LENGTHS])
@pytest.mark.parametrize("matching", list(rc.MATCHINGS))
def test_one_failing_bound_of_six_drops_the_candidat(
    tmp_path: Path, label: str, matching: str
) -> None:
    """Any single one of the six combinations at or below zero, and there is no candidat."""
    params = GRID[0]
    configs = {
        _key(BTC, params): _config(params, lb=_lb(1.5, overrides={(label, matching): -1e-12}))
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "F_CANNOT_SEPARATE"
    assert payload["pairs"][BTC]["n_candidat"] == 0
    assert payload["pairs"][BTC]["representative"] is None


def test_a_bound_of_exactly_zero_is_not_strictly_positive(tmp_path: Path) -> None:
    params = GRID[0]
    configs = {_key(BTC, params): _config(params, lb=_lb(1.5, overrides={("21", "dd"): 0.0}))}
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    _, payload = _verdict(paths)
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF


def test_gates_on_one_config_and_bounds_on_another_is_not_a_candidat(tmp_path: Path) -> None:
    """§ G.3 / § H: ``candidat`` needs the SAME configuration to do both."""
    passing, holding = GRID[0], GRID[1]
    configs = {
        # passes G1 ∧ G2 ∧ G4, but its six bounds are negative
        _key(BTC, passing): _config(passing, lb=_lb(-0.5)),
        # holds the six bounds, but fails G2
        _key(BTC, holding): _config(holding, gates=(True, False, True), lb=_lb(2.0)),
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "F_CANNOT_SEPARATE"
    btc = payload["pairs"][BTC]
    assert btc["n_eligible"] == 2 and btc["n_passing_gates"] == 1 and btc["n_candidat"] == 0


def test_a_missing_block_length_is_not_six_combinations(tmp_path: Path) -> None:
    """A bound published on two block lengths cannot carry a candidat: six means six."""
    params = GRID[0]
    configs = {_key(BTC, params): _config(params, lb=_lb(3.0, lengths=(10, 21)))}
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    _, payload = _verdict(paths)
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["pairs"][BTC]["n_candidat"] == 0


# ---------------------------------------------------------------------------
# 3. The run-level gate (§ G.2) short-circuits everything
# ---------------------------------------------------------------------------


def test_an_ia_failure_short_circuits_to_r0_even_with_perfect_artifacts(tmp_path: Path) -> None:
    """No partial salvage: the same engine produced the 96 entries (§ G.2)."""
    paths = _paths(tmp_path, validation_campaign=_validation_campaign(("I-A.9",)))
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "R0_INVALID_RUN"
    assert "representant=-" in payload["verdict_string"]
    # no partial salvage: the pair that measured a candidat keeps no economic verdict either
    assert payload["pairs"][BTC]["verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["pairs"][BTC]["reason"] == "R0_INVALID_RUN"
    assert payload["pairs"][BTC]["representative"] is None
    assert f"{BTC}=inconclusif" in payload["verdict_string"]
    # the counts stay visible — they are facts about effect.json, never votes
    assert payload["pairs"][BTC]["n_candidat"] == 2


def test_b4_flags_flag_gives_r1_not_r0(tmp_path: Path) -> None:
    """I-A.13 is evaluated only after I-A.1..I-A.12 pass: its failure IS "b4_flags spoke"."""
    paths = _paths(tmp_path, validation_campaign=_validation_campaign(("I-A.13",)))
    _, payload = _verdict(paths)
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "R1_ACCOUNTING_FLAG"


def test_a_flag_plus_another_failure_is_r0(tmp_path: Path) -> None:
    paths = _paths(tmp_path, validation_campaign=_validation_campaign(("I-A.13", "I-A.14")))
    _, payload = _verdict(paths)
    assert payload["reason"] == "R0_INVALID_RUN"


def test_a_missing_validation_campaign_is_r0(tmp_path: Path) -> None:
    paths = _paths(tmp_path, validation_campaign=None)
    _, payload = _verdict(paths)
    assert payload["reason"] == "R0_INVALID_RUN"
    assert payload["inputs_sha256"]["validation_campaign"] is None
    assert payload["verdict_string"].endswith("campagne=-")


def test_ok_false_without_a_failed_list_is_still_r0(tmp_path: Path) -> None:
    block = _validation_campaign()
    block["ok"] = False
    block["exit_code"] = 2
    paths = _paths(tmp_path, validation_campaign=block)
    _, payload = _verdict(paths)
    assert payload["reason"] == "R0_INVALID_RUN"


# ---------------------------------------------------------------------------
# 4. § D — admissibility, D_UNMEASURABLE, D_NO_ADMISSIBLE_PAIR, W2
# ---------------------------------------------------------------------------


def test_unmeasurable_coverage_gives_d_unmeasurable(tmp_path: Path) -> None:
    """§ D.3: a rule that silently assumed full coverage would be a defect."""
    paths = _paths(tmp_path, data_coverage={"generated_at": NOW})
    _, payload = _verdict(paths)
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "D_UNMEASURABLE"


def test_inadmissible_btc_becomes_descriptif_and_the_family_has_no_voter(tmp_path: Path) -> None:
    configs = {_key(BTC, GRID[0]): _config(GRID[0], status=rc.STATUS_DESCRIPTIF)}
    paths = _paths(
        tmp_path,
        data_coverage=_coverage(BTC=False),
        effect=_effect({BTC: _pair_block(configs, admissible=False)}),
    )
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["verdict"] == rc.VERDICT_DESCRIPTIF
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "D_NO_ADMISSIBLE_PAIR"


def test_warmup_w2_makes_every_config_descriptif(tmp_path: Path) -> None:
    configs = {
        _key(BTC, params): _config(params, status=rc.STATUS_DESCRIPTIF) for params in GRID[:2]
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs, warmup="W2")}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["verdict"] == rc.VERDICT_DESCRIPTIF
    assert payload["pairs"][BTC]["reason"] == "D_WARMUP_W2"
    assert payload["reason"] == "D_NO_ADMISSIBLE_PAIR"


def test_an_unknown_warmup_class_keeps_the_strictest(tmp_path: Path) -> None:
    configs = {_key(BTC, GRID[0]): _config(GRID[0], status=rc.STATUS_DESCRIPTIF)}
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs, warmup="")}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["verdict"] == rc.VERDICT_DESCRIPTIF
    assert payload["pairs"][BTC]["reason"] == "D_WARMUP_W2"


# ---------------------------------------------------------------------------
# 5. § D.3 — SOL votes for nothing
# ---------------------------------------------------------------------------


def test_sol_alone_can_never_produce_a_candidat(tmp_path: Path) -> None:
    """Even measured admissible, W0 and comparable, with configs that hold everything."""
    configs = {_key(SOL, GRID[0]): _config(GRID[0])}
    paths = _paths(
        tmp_path,
        data_coverage=_coverage(BTC=False, SOL=True),
        benchmark=_benchmark(BTC=False, SOL=True),
        effect=_effect({SOL: _pair_block(configs, warmup="W0")}),
    )
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["pairs"][SOL]["verdict"] == rc.VERDICT_DESCRIPTIF
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "D_NO_ADMISSIBLE_PAIR"
    assert payload["pairs"][SOL]["representative"] is None


def test_sol_alone_can_never_produce_a_depriorisation(tmp_path: Path) -> None:
    """The one-way ratchet § D.3 forbids: data declared untestable may not kill a family."""
    configs = {
        _key(SOL, params): _config(params, gates=(False, False, False), lb=_lb(-1.0))
        for params in GRID[:2]
    }
    paths = _paths(
        tmp_path,
        data_coverage=_coverage(BTC=False, SOL=True),
        benchmark=_benchmark(BTC=False, SOL=True),
        effect=_effect({SOL: _pair_block(configs, warmup="W0")}),
    )
    _, payload = _verdict(paths)
    assert payload["pairs"][SOL]["verdict"] == rc.VERDICT_DESCRIPTIF
    assert payload["family_verdict"] != rc.VERDICT_DEPRIORISATION
    assert payload["reason"] == "D_NO_ADMISSIBLE_PAIR"


def test_the_expected_case_btc_votes_and_sol_is_descriptif(tmp_path: Path) -> None:
    """§ G.4: "BTC vote, SOL est descriptif ⇒ le verdict de famille est celui de BTC"."""
    btc_configs = {
        _key(BTC, params): _config(params, gates=(True, False, True)) for params in GRID[:2]
    }
    sol_configs = {_key(SOL, GRID[0]): _config(GRID[0], status=rc.STATUS_DESCRIPTIF)}
    paths = _paths(
        tmp_path,
        effect=_effect({
            BTC: _pair_block(btc_configs),
            SOL: _pair_block(sol_configs, admissible=False, warmup="W2", comparable=False),
        }),
    )
    _, payload = _verdict(paths)
    assert payload["pairs"][SOL]["verdict"] == rc.VERDICT_DESCRIPTIF
    assert payload["family_verdict"] == rc.VERDICT_DEPRIORISATION


# ---------------------------------------------------------------------------
# 6. § E / § C / § F — the other pair-level reasons
# ---------------------------------------------------------------------------


def test_a_non_comparable_benchmark_gives_e_no_benchmark(tmp_path: Path) -> None:
    configs = {
        _key(BTC, GRID[0]): _config(GRID[0], status=rc.STATUS_NO_BENCHMARK,
                                    first_failing_gate="E_NO_BENCHMARK")
    }
    paths = _paths(
        tmp_path,
        benchmark=_benchmark(BTC=False),
        effect=_effect({BTC: _pair_block(configs, comparable=False)}),
    )
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "E_NO_BENCHMARK"


def test_every_config_below_coverage_gives_the_modal_c_coverage(tmp_path: Path) -> None:
    configs = {
        _key(BTC, params): _config(
            params, cycles=12, status=rc.STATUS_BELOW_COVERAGE, first_failing_gate="C_COVERAGE"
        )
        for params in GRID[:4]
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["n_eligible"] == 0
    assert payload["reason"] == "C_COVERAGE"


def test_the_modal_gate_is_the_most_frequent_one(tmp_path: Path) -> None:
    configs = {
        _key(BTC, GRID[0]): _config(GRID[0], cycles=12, status=rc.STATUS_BELOW_COVERAGE,
                                    first_failing_gate="C_COVERAGE"),
        _key(BTC, GRID[1]): _config(GRID[1], nnz=10, status=rc.STATUS_NOT_ESTIMABLE,
                                    first_failing_gate="F_NOT_ESTIMABLE"),
        _key(BTC, GRID[2]): _config(GRID[2], nnz=10, status=rc.STATUS_NOT_ESTIMABLE,
                                    first_failing_gate="F_NOT_ESTIMABLE"),
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    _, payload = _verdict(paths)
    assert payload["reason"] == "F_NOT_ESTIMABLE"


def test_an_analysis_failure_gives_f_not_estimable_without_touching_the_campaign(
    tmp_path: Path,
) -> None:
    """§ I-B: the campaign stays valid; only the inference becomes unusable."""
    paths = _paths(tmp_path, validation_analysis=_validation_analysis(False, ("I-B.5",)))
    _, payload = _verdict(paths)
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "F_NOT_ESTIMABLE"
    assert payload["pairs"][BTC]["representative"] is None


def test_an_analysis_failure_never_reads_as_r0(tmp_path: Path) -> None:
    paths = _paths(tmp_path, validation_analysis=None)
    _, payload = _verdict(paths)
    assert payload["reason"] == "F_NOT_ESTIMABLE"
    assert payload["reason"] != "R0_INVALID_RUN"


def test_a_below_coverage_pair_keeps_c_coverage_over_an_analysis_failure(tmp_path: Path) -> None:
    """§ H: the reason is taken from rc.REASON_PRIORITY, in that priority order."""
    configs = {
        _key(BTC, params): _config(
            params, cycles=3, status=rc.STATUS_BELOW_COVERAGE, first_failing_gate="C_COVERAGE"
        )
        for params in GRID[:2]
    }
    paths = _paths(
        tmp_path,
        effect=_effect({BTC: _pair_block(configs)}),
        validation_analysis=_validation_analysis(False, ("I-B.5",)),
    )
    _, payload = _verdict(paths)
    assert payload["reason"] == "C_COVERAGE"


# ---------------------------------------------------------------------------
# 7. § F.4 — a frozen λ forbids candidat
# ---------------------------------------------------------------------------


def test_frozen_sensitivity_forbids_candidat(tmp_path: Path) -> None:
    paths = _paths(
        tmp_path,
        effect=_effect(
            {BTC: _pair_block(_candidat_configs())}, lambda_mode=eff.LAMBDA_MODE_FROZEN
        ),
    )
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "F_NOT_ESTIMABLE"
    assert payload["pairs"][BTC]["n_candidat"] == 2  # the numbers stay visible
    assert payload["pairs"][BTC]["representative"] is None


def test_frozen_sensitivity_still_allows_depriorisation(tmp_path: Path) -> None:
    """§ F.4: the run can then only return `dépriorisation` or `inconclusif`."""
    configs = {
        _key(BTC, params): _config(params, gates=(False, True, True)) for params in GRID[:2]
    }
    paths = _paths(
        tmp_path,
        effect=_effect({BTC: _pair_block(configs)}, lambda_mode=eff.LAMBDA_MODE_FROZEN),
    )
    _, payload = _verdict(paths)
    assert payload["family_verdict"] == rc.VERDICT_DEPRIORISATION


def test_an_absent_lambda_mode_is_treated_as_frozen(tmp_path: Path) -> None:
    """Unknown coverage guarantee is never assumed to be the 95 % one."""
    payload_effect = _effect({BTC: _pair_block(_candidat_configs())})
    del payload_effect["lambda_mode"]
    paths = _paths(tmp_path, effect=payload_effect)
    _, payload = _verdict(paths)
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF


# ---------------------------------------------------------------------------
# 8. § G.3 — the representative, chosen AFTER, deterministic to the last step
# ---------------------------------------------------------------------------


def test_representative_is_argmax_delta_dd(tmp_path: Path) -> None:
    configs = {
        _key(BTC, GRID[0]): _config(GRID[0], delta_dd=1.0),
        _key(BTC, GRID[1]): _config(GRID[1], delta_dd=9.0),
        _key(BTC, GRID[2]): _config(GRID[2], delta_dd=4.0),
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["representative"] == _key(BTC, GRID[1])


def test_representative_ties_break_on_delta_sigma_then_mdd_then_params_hash(
    tmp_path: Path,
) -> None:
    tied = {
        _key(BTC, GRID[0]): _config(GRID[0], delta_dd=5.0, delta_sigma=1.0),
        _key(BTC, GRID[1]): _config(GRID[1], delta_dd=5.0, delta_sigma=2.0),
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(tied)}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["representative"] == _key(BTC, GRID[1])

    tied = {
        _key(BTC, GRID[0]): _config(GRID[0], delta_dd=5.0, delta_sigma=2.0, mdd=30.0),
        _key(BTC, GRID[1]): _config(GRID[1], delta_dd=5.0, delta_sigma=2.0, mdd=4.0),
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(tied)}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["representative"] == _key(BTC, GRID[1])

    fully_tied = {
        _key(BTC, params): _config(params, delta_dd=5.0, delta_sigma=2.0, mdd=4.0)
        for params in GRID[:5]
    }
    expected = min(fully_tied, key=lambda key: p7.params_hash(fully_tied[key]["params"]))
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(fully_tied)}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["representative"] == expected


# ---------------------------------------------------------------------------
# 9. § G.5 — the non-rules, each proved
# ---------------------------------------------------------------------------


def _string_of(tmp_path: Path, **payloads: Any) -> str:
    paths = _paths(tmp_path, **payloads)
    _, payload = _verdict(paths)
    return str(payload["verdict_string"])


def test_degeneracy_never_changes_a_verdict(tmp_path: Path) -> None:
    """"48 -> 1 classe" and "48 -> 48 classes" read identically (§ A, § G.5)."""
    one = _string_of(tmp_path / "a", signatures=_signatures(classes=1))
    many = _string_of(tmp_path / "b", signatures=_signatures(classes=48))
    none = _string_of(tmp_path / "c", signatures=None)
    assert one == many == none


def test_the_clamp_never_changes_a_verdict(tmp_path: Path) -> None:
    """§ B.3: not producible ⇒ labelled NOT MEASURED, and nothing else changes."""
    measured = _string_of(tmp_path / "a", clamp=_clamp(True))
    unmeasured = _string_of(
        tmp_path / "b", clamp=_clamp(False, reason="DB unavailable from this host")
    )
    absent = _string_of(tmp_path / "c", clamp=None)
    assert measured == unmeasured == absent


def test_sharpe_never_changes_a_verdict(tmp_path: Path) -> None:
    high = _effect({BTC: _pair_block({
        _key(BTC, GRID[0]): _config(GRID[0], sharpe=9.9),
    })})
    none = _effect({BTC: _pair_block({
        _key(BTC, GRID[0]): _config(GRID[0], sharpe=None),
    })})
    assert _string_of(tmp_path / "a", effect=high) == _string_of(tmp_path / "b", effect=none)


def test_the_fee_multiple_g3_never_changes_a_verdict(tmp_path: Path) -> None:
    """§ F.3: G3 is descriptive; a candidat below 10x is a qualification, never a failure."""
    rich = _effect({BTC: _pair_block({
        _key(BTC, GRID[0]): _config(GRID[0], fee_multiple=40.0),
    })})
    poor = _effect({BTC: _pair_block({
        _key(BTC, GRID[0]): _config(GRID[0], fee_multiple=0.4),
    })})
    assert rc.G3_FEE_MULTIPLE == 10.0
    assert _string_of(tmp_path / "a", effect=rich) == _string_of(tmp_path / "b", effect=poor)


def test_train_and_test_are_not_even_an_input_of_the_verdict(tmp_path: Path) -> None:
    """The only way ``train``/``test`` could vote is through the campaign artifact, which this
    script never opens: the parser has no option for it, and neither has the sha block."""
    options = {
        option
        for action in rv.build_parser()._actions
        for option in action.option_strings
    }
    assert "--campaign" not in options
    paths = _paths(tmp_path)
    _, payload = _verdict(paths)
    assert set(payload["inputs_sha256"]) == {
        "validation_campaign", "validation_analysis", "data_coverage", "benchmark",
        "signatures", "clamp", "effect",
    }


# ---------------------------------------------------------------------------
# 10. Determinism and the frozen schema
# ---------------------------------------------------------------------------


def test_the_verdict_string_is_byte_identical_across_two_runs(tmp_path: Path) -> None:
    """The falsifiability contract: two people, the same artifacts, the same string."""
    paths = _paths(tmp_path)
    first = json.dumps(_verdict(paths)[1], sort_keys=True)
    first_bytes = paths["output"].read_bytes()
    second_code = rv.main(_argv(paths, "--markdown", str(tmp_path / "verdict.md")))
    assert second_code == 0
    assert paths["output"].read_bytes() == first_bytes
    payload = json.loads(paths["output"].read_text(encoding="utf-8"))
    assert json.dumps(payload, sort_keys=True) == first
    # the stamp moves, the verdict string does not
    other = tmp_path / "other.json"
    assert rv.main(_argv(paths, "--now", OTHER_NOW, "--output", str(other))) == 0
    moved = json.loads(other.read_text(encoding="utf-8"))
    assert moved["generated_at"] != payload["generated_at"]
    assert moved["verdict_string"] == payload["verdict_string"]


def test_main_writes_the_frozen_schema(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    markdown = tmp_path / "verdict.md"
    code = rv.main(_argv(paths, "--markdown", str(markdown)))
    assert code == 0
    payload = json.loads(paths["output"].read_text(encoding="utf-8"))
    assert set(payload) == {
        "generated_at", "base_sha", "prespec", "family_verdict", "reason", "verdict_string",
        "pairs", "inputs_sha256",
    }
    assert payload["generated_at"] == NOW
    assert payload["base_sha"] == rc.BASE_SHA
    assert payload["prespec"]["path"] == rv.PRESPEC_RELPATH
    for block in payload["pairs"].values():
        assert set(block) == {
            "verdict", "reason", "representative", "n_eligible", "n_passing_gates", "n_candidat",
        }
    assert markdown.exists() and payload["verdict_string"] in markdown.read_text(encoding="utf-8")


def test_bad_now_is_a_usage_error(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    assert rv.main(_argv(paths)[:-1] + ["not-a-date"]) == 2


def test_a_recorded_status_that_contradicts_the_ladder_is_a_violation(tmp_path: Path) -> None:
    """effect.json's own ``status`` is cross-checked, never copied: § G.1 is the rule."""
    configs = {_key(BTC, GRID[0]): _config(GRID[0])}
    configs[_key(BTC, GRID[0])]["status"] = rc.STATUS_BELOW_COVERAGE
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    code, payload = _verdict(paths)
    assert code == 1
    # the recomputed ladder governs: 53 cycles is ELIGIBLE whatever the artifact recorded
    assert payload["pairs"][BTC]["n_eligible"] == 1


def test_a_recorded_lb_flag_that_contradicts_the_numbers_is_a_violation(tmp_path: Path) -> None:
    configs = {_key(BTC, GRID[0]): _config(GRID[0], lb=_lb(-1.0))}
    configs[_key(BTC, GRID[0])]["LB_all_six_positive"] = True
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    code, payload = _verdict(paths)
    assert code == 1
    assert payload["pairs"][BTC]["n_candidat"] == 0


def test_a_non_finite_delta_is_not_estimable_never_a_number_to_comment(tmp_path: Path) -> None:
    """§ F.7: any NaN / Inf in Δ is a validity failure, not a value compared to a threshold."""
    config = _config(GRID[0])
    config["delta_dd"] = float("nan")
    config["status"] = rc.STATUS_NOT_ESTIMABLE
    config["first_failing_gate"] = "F_NOT_ESTIMABLE"
    config["gates"] = {"G1": None, "G2": None, "G4": None}
    config["passes_gates"] = False
    config["LB"] = None
    config["LB_all_six_positive"] = False
    paths = _paths(
        tmp_path, effect=_effect({BTC: _pair_block({_key(BTC, GRID[0]): config})})
    )
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["pairs"][BTC]["n_eligible"] == 0
    assert payload["reason"] == "F_NOT_ESTIMABLE"


def test_an_unmeasurable_cycle_count_is_not_estimable_not_below_coverage(
    tmp_path: Path,
) -> None:
    """The false green of § I: an absent ``liquidation`` block makes ``cycles`` unmeasurable,
    not small — pretending the quantity was measured would be a defect."""
    configs = {
        _key(BTC, GRID[0]): _config(
            GRID[0], cycles=None, status=rc.STATUS_NOT_ESTIMABLE,
            first_failing_gate="F_NOT_ESTIMABLE",
        )
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["reason"] == "F_NOT_ESTIMABLE"
    assert payload["reason"] != "C_COVERAGE"


def test_an_eligible_config_without_a_published_bound_cannot_be_a_candidat(
    tmp_path: Path,
) -> None:
    config = _config(GRID[0])
    config["LB"] = None
    config["LB_all_six_positive"] = False
    paths = _paths(
        tmp_path, effect=_effect({BTC: _pair_block({_key(BTC, GRID[0]): config})})
    )
    code, payload = _verdict(paths)
    assert code == 0, payload
    assert payload["family_verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["reason"] == "F_CANNOT_SEPARATE"


def test_the_run_gate_outranks_every_other_reason(tmp_path: Path) -> None:
    """§ G.2 is evaluated "avant tout le reste", and ``rc.REASON_PRIORITY`` starts with R0/R1."""
    paths = _paths(
        tmp_path,
        validation_campaign=_validation_campaign(("I-A.2",)),
        data_coverage={"generated_at": NOW},
        validation_analysis=_validation_analysis(False, ("I-B.5",)),
    )
    _, payload = _verdict(paths)
    assert payload["reason"] == "R0_INVALID_RUN"
    assert rc.REASON_PRIORITY[0] == "R0_INVALID_RUN"
    assert rc.REASON_PRIORITY[1] == "R1_ACCOUNTING_FLAG"


def test_a_cycle_count_just_under_the_frozen_filter_is_below_coverage(tmp_path: Path) -> None:
    """25 is the frozen number; 24 is excluded and the report consigns that it bit (§ C.2)."""
    assert rc.CYCLES_MIN == 25
    configs = {
        _key(BTC, GRID[0]): _config(
            GRID[0], cycles=24, status=rc.STATUS_BELOW_COVERAGE, first_failing_gate="C_COVERAGE"
        ),
        _key(BTC, GRID[1]): _config(GRID[1], cycles=25),
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["n_eligible"] == 1
    assert payload["family_verdict"] == rc.VERDICT_CANDIDAT
    assert payload["pairs"][BTC]["representative"] == _key(BTC, GRID[1])


def test_an_nnz_just_under_the_activity_filter_is_not_estimable(tmp_path: Path) -> None:
    assert rc.NNZ_MIN == 110
    configs = {
        _key(BTC, GRID[0]): _config(
            GRID[0], nnz=109, status=rc.STATUS_NOT_ESTIMABLE,
            first_failing_gate="F_NOT_ESTIMABLE",
        )
    }
    paths = _paths(tmp_path, effect=_effect({BTC: _pair_block(configs)}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["n_eligible"] == 0
    assert payload["reason"] == "F_NOT_ESTIMABLE"


def test_a_pair_absent_from_effect_is_not_silently_green(tmp_path: Path) -> None:
    paths = _paths(tmp_path, effect=_effect({}))
    _, payload = _verdict(paths)
    assert payload["pairs"][BTC]["verdict"] == rc.VERDICT_INCONCLUSIF
    assert payload["pairs"][BTC]["reason"] == "F_NOT_ESTIMABLE"
    assert payload["pairs"][SOL]["verdict"] == rc.VERDICT_DESCRIPTIF


# ---------------------------------------------------------------------------
# 11. § I-B — rejeu_validate_analysis
# ---------------------------------------------------------------------------


def _analysis_paths(tmp_path: Path, **payloads: Any) -> dict[str, Path]:
    defaults = {
        "effect": _effect({BTC: _pair_block(_candidat_configs())}),
        "signatures": _signatures(),
        "clamp": _clamp(),
    }
    defaults.update(payloads)
    tmp_path.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, payload in defaults.items():
        path = tmp_path / f"{name}.json"
        if payload is not None:
            path.write_text(json.dumps(payload), encoding="utf-8")
        out[name] = path
    out["output"] = tmp_path / "validation_analysis.json"
    return out


def _analysis_argv(paths: dict[str, Path], *extra: str) -> list[str]:
    return [
        "--effect", str(paths["effect"]),
        "--signatures", str(paths["signatures"]),
        "--clamp", str(paths["clamp"]),
        "--output", str(paths["output"]),
        "--now", NOW,
        *extra,
    ]


def _validate(paths: dict[str, Path], *extra: str) -> tuple[int, dict[str, Any]]:
    code = rva.main(_analysis_argv(paths, *extra))
    return code, json.loads(paths["output"].read_text(encoding="utf-8"))


def _row(payload: dict[str, Any], identifier: str) -> dict[str, Any]:
    return next(row for row in payload["assertions"] if row["id"] == identifier)


def test_analysis_validation_passes_on_a_clean_set(tmp_path: Path) -> None:
    effect = _effect({BTC: _pair_block(_candidat_configs())})
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 0, payload["failed"]
    assert payload["ok"] is True and payload["exit_code"] == 0
    assert payload["failed"] == []
    assert [row["id"] for row in payload["assertions"]] == [a[0] for a in rva.ASSERTIONS]
    assert set(payload) == {
        "generated_at", "base_sha", "prespec", "ok", "exit_code", "assertions", "failed",
        "inputs_sha256",
    }
    assert payload["generated_at"] == NOW
    assert set(payload["inputs_sha256"]) == set(rva.INPUT_NAMES)


def test_a_single_changed_lb_bit_fails_the_rerun(tmp_path: Path) -> None:
    """Bit for bit: one ULP on one of the six bounds is a failure, not a tolerance."""
    effect = _effect({BTC: _pair_block(_candidat_configs())})
    rerun_payload = json.loads(json.dumps(effect))
    key = sorted(rerun_payload["pairs"][BTC]["configs"])[0]
    block = rerun_payload["pairs"][BTC]["configs"][key]["LB"]["21"]
    block["dd"] = math.nextafter(block["dd"], math.inf)
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", rerun_payload)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2
    assert payload["failed"] == ["I-B.5"]
    assert "does not reproduce bit for bit" in _row(payload, "I-B.5")["detail"]


def test_a_rerun_that_cannot_be_performed_is_a_failure_not_a_skip(tmp_path: Path) -> None:
    paths = _analysis_paths(tmp_path)
    code, payload = _validate(paths, "--campaign", str(tmp_path / "absent.json"))
    assert code == 2
    assert "I-B.5" in payload["failed"]
    assert _row(payload, "I-B.5")["skipped"] is False


def test_signatures_absent_fails_but_not_producible_passes(tmp_path: Path) -> None:
    effect = _effect({BTC: _pair_block(_candidat_configs())})
    rerun = _write(tmp_path, "rerun.json", effect)
    missing = _analysis_paths(tmp_path / "a", effect=effect, signatures=None)
    code, payload = _validate(missing, "--rerun", str(rerun))
    assert code == 2 and "I-B.6" in payload["failed"]

    marked = _analysis_paths(
        tmp_path / "b",
        effect=effect,
        signatures={"producible": False, "reason": "campaign artifact unreadable"},
    )
    code, payload = _validate(marked, "--rerun", str(rerun))
    assert code == 0, payload["failed"]
    assert "explicitly not producible" in _row(payload, "I-B.6")["detail"]


def test_clamp_not_producible_needs_a_reason(tmp_path: Path) -> None:
    effect = _effect({BTC: _pair_block(_candidat_configs())})
    rerun = _write(tmp_path, "rerun.json", effect)
    silent = _analysis_paths(tmp_path / "a", effect=effect, clamp={"producible": False})
    code, payload = _validate(silent, "--rerun", str(rerun))
    assert code == 2 and "I-B.7" in payload["failed"]

    spoken = _analysis_paths(
        tmp_path / "b", effect=effect, clamp=_clamp(False, reason="no DB from this host")
    )
    code, payload = _validate(spoken, "--rerun", str(rerun))
    assert code == 0, payload["failed"]
    assert "NOT MEASURED" in _row(payload, "I-B.7")["detail"]


def test_degenerate_replications_over_the_cap_must_make_the_pair_not_estimable(
    tmp_path: Path,
) -> None:
    """§ F.7: beyond 10 out of 10 000 the inference is unusable FOR THE PAIR, and says so."""
    configs = _candidat_configs()
    first = sorted(configs)[0]
    configs[first]["degenerate_replications"] = rc.DEGENERATE_MAX + 1
    effect = _effect({BTC: _pair_block(configs, not_estimable=False, reason=None)})
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and "I-B.3" in payload["failed"]
    detail = _row(payload, "I-B.3")["detail"]
    assert "not_estimable" in detail and "LB_all_six_positive" in detail


def test_degenerate_replications_recorded_and_handled_pass(tmp_path: Path) -> None:
    configs = _candidat_configs()
    for key in configs:
        configs[key]["degenerate_replications"] = rc.DEGENERATE_MAX + 5
        configs[key]["LB_all_six_positive"] = False
    effect = _effect({
        BTC: _pair_block(configs, not_estimable=True, reason="F_NOT_ESTIMABLE")
    })
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 0, payload["failed"]


def test_an_ineligible_config_without_a_first_failing_gate_fails(tmp_path: Path) -> None:
    configs = {
        _key(BTC, GRID[0]): _config(
            GRID[0], cycles=3, status=rc.STATUS_BELOW_COVERAGE, first_failing_gate=None
        )
    }
    effect = _effect({BTC: _pair_block(configs)})
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and "I-B.4" in payload["failed"]
    assert "without a first failing gate" in _row(payload, "I-B.4")["detail"]


def test_an_eligible_config_whose_gate_label_lies_fails(tmp_path: Path) -> None:
    configs = _candidat_configs()
    first = sorted(configs)[0]
    configs[first]["gates"]["G2"] = False
    effect = _effect({BTC: _pair_block(configs)})
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and "I-B.4" in payload["failed"]


def test_a_wrong_seed_fails_the_frozen_parameters(tmp_path: Path) -> None:
    effect = _effect({BTC: _pair_block(_candidat_configs())})
    effect["seeds"][BTC]["21"] = 12345
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and "I-B.2" in payload["failed"]
    assert str(rc.SEED_BASE) in _row(payload, "I-B.2")["detail"]


def test_an_overridden_b_or_block_length_fails_the_frozen_parameters(tmp_path: Path) -> None:
    effect = _effect(
        {BTC: _pair_block(_candidat_configs())}, replications=40, lengths=(10, 21)
    )
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and payload["failed"] == ["I-B.2"]
    assert "10000" in _row(payload, "I-B.2")["detail"]


def test_frozen_lambda_without_the_frozen_label_fails(tmp_path: Path) -> None:
    effect = _effect(
        {BTC: _pair_block(_candidat_configs())}, lambda_mode=eff.LAMBDA_MODE_FROZEN
    )
    effect["lambda_mode_label"] = None
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and "I-B.1" in payload["failed"]

    effect["lambda_mode_label"] = eff.FROZEN_LABEL
    paths = _analysis_paths(tmp_path / "b", effect=effect)
    rerun = _write(tmp_path, "rerun_ok.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 0, payload["failed"]
    assert "sans garantie de couverture" in _row(payload, "I-B.1")["detail"]


def test_an_unknown_lambda_mode_fails(tmp_path: Path) -> None:
    effect = _effect({BTC: _pair_block(_candidat_configs())})
    effect["lambda_mode"] = "whatever"
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and "I-B.1" in payload["failed"]


def test_an_empty_eligible_set_must_be_marked_not_estimable(tmp_path: Path) -> None:
    configs = {
        _key(BTC, GRID[0]): _config(
            GRID[0], cycles=3, status=rc.STATUS_BELOW_COVERAGE, first_failing_gate="C_COVERAGE"
        )
    }
    effect = _effect({BTC: _pair_block(configs, not_estimable=False, reason=None)})
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    code, payload = _validate(paths, "--rerun", str(rerun))
    assert code == 2 and "I-B.1" in payload["failed"]


def test_an_unreadable_effect_skips_the_rest_and_records_the_skip(tmp_path: Path) -> None:
    paths = _analysis_paths(tmp_path, effect=None)
    code, payload = _validate(paths)
    assert code == 2
    assert _row(payload, "I-B.1")["ok"] is False
    for identifier in ("I-B.2", "I-B.3", "I-B.4", "I-B.5"):
        row = _row(payload, identifier)
        assert row["ok"] is False and row["skipped"] is True
        assert "I-B.1 owns that failure" in row["detail"]
    # signatures / clamp do not need effect.json and are still evaluated
    assert _row(payload, "I-B.6")["ok"] is True


def test_analysis_validation_is_deterministic(tmp_path: Path) -> None:
    effect = _effect({BTC: _pair_block(_candidat_configs())})
    paths = _analysis_paths(tmp_path, effect=effect)
    rerun = _write(tmp_path, "rerun.json", effect)
    first = paths["output"]
    _validate(paths, "--rerun", str(rerun))
    blob = first.read_bytes()
    _validate(paths, "--rerun", str(rerun))
    assert first.read_bytes() == blob


# ---------------------------------------------------------------------------
# 12. § I-B.5 — the real rerun, through rejeu_effect itself
# ---------------------------------------------------------------------------


def _nav(seed: int, *, drift: float, amplitude: float) -> list[float]:
    rng = np.random.default_rng(seed)
    steps = drift + amplitude * rng.standard_normal(N_POINTS - 1)
    values = float(rc.CAPITAL) * np.cumprod(1.0 + steps)
    return [float(rc.CAPITAL)] + [round(float(v), 8) for v in values]


def _metrics(values: list[float], *, total_trades: int) -> dict[str, Any]:
    return {
        "metrics_version": 2,
        "total_trades": total_trades,
        "winning_trades": total_trades,
        "losing_trades": 0,
        "win_rate": 1.0,
        "total_return_pct": (values[-1] - values[0]) / values[0] * 100.0,
        "sharpe_ratio": 0.93,
        "sortino_ratio": 1.49,
        "max_drawdown_pct_daily": 2.04,
        "max_drawdown_pct_engine": 2.57,
        "profit_factor": None,
        "calmar_ratio": 0.73,
        "net_pnl": 45.72,
        "total_fees": 3.02,
        "total_pnl": 48.74,
        "unrealized_pnl": -15.310009211802027,
        "starting_balance": 1000.0,
        "ending_balance": 1045.72,
        "duration_days": 1096.0,
        "average_holding_time_minutes": 5776.98,
        "gross_profit_net": 61.13,
        "gross_loss_net": 15.41,
        "pf_excluded_trades": 0,
        "n_daily_returns": rc.SEGMENT_RETURNS["all"],
    }


def _entry(params: dict[str, Any], values: list[float], *, total_trades: int) -> dict[str, Any]:
    metrics = _metrics(values, total_trades=total_trades)
    return {
        "strategy": rc.STRATEGY,
        "pair": BTC,
        "exchange": rc.EXCHANGE,
        "fees": rc.FEES_MODEL,
        "metrics_version": 2,
        "replay_version": 2,
        "params": dict(params),
        "phase": "1",
        "window_idx": None,
        "equity_daily": {
            "all": {
                "start": rc.WINDOW_START.isoformat(),
                "end": rc.WINDOW_END.isoformat(),
                "values": values,
            }
        },
        # the real BTC W1 block: 4h clean, 1d/1w insufficient by an internal hole
        "warmup": {
            "all": {
                "4h": {"interval": 240, "required": 14, "loaded": 91, "extended_by": 0,
                       "stale_by_candles": 0, "largest_gap_candles": 0, "sufficient": True,
                       "first": None, "last": None},
                "1d": {"interval": 1440, "required": 50, "loaded": 88, "extended_by": 0,
                       "stale_by_candles": 0, "largest_gap_candles": 163, "sufficient": False,
                       "first": None, "last": None},
                "1w": {"interval": 10080, "required": 50, "loaded": 50, "extended_by": 19,
                       "stale_by_candles": 0, "largest_gap_candles": 23, "sufficient": False,
                       "first": None, "last": None},
            }
        },
        "liquidation": {
            "all": {
                "buy_fees": "1.4250", "sell_fees": "1.5995", "net_pnl_lot_basis": "45.72",
                "residual_net_proceeds": "0", "avg_holding_minutes": 108008.75, "positions": 4,
                "trades": 4, "residual_trade_btc": "0", "dust_written_off_btc": "-6E-31",
                "inventory_divergence_btc": "0E-30", "pnl": "-15.31", "fees": "0.212",
                "gross_usdc": "84.80", "timestamp": "2026-04-01T00:00:00+00:00",
                "reference_price": "68240.16", "price": "68212.86",
                "spread_pct": "0.0002", "slippage_pct": "0.0002",
            }
        },
        "train": metrics,
        "test": metrics,
        "all": metrics,
    }


@pytest.fixture(scope="module")
def real_effect(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """A genuine (small) ``rejeu_effect`` run, so I-B.5 can rerun it for real."""
    tmp_path = tmp_path_factory.mktemp("rejeu_verdict_rerun")
    campaign = {
        _key(BTC, params): _entry(
            params, _nav(11 + index, drift=0.0002, amplitude=0.004), total_trades=40 + index
        )
        for index, params in enumerate(GRID[:2])
    }
    bench = _nav(7, drift=0.0008, amplitude=0.02)
    paths = {
        "campaign": tmp_path / "P7_phase1_grid.json",
        "benchmark": tmp_path / "benchmark.json",
        "coverage": tmp_path / "data_coverage.json",
        "validation_campaign": tmp_path / "validation_campaign.json",
        "calibration": tmp_path / "calibration_absent.json",
        "effect": tmp_path / "effect.json",
        "signatures": tmp_path / "signatures.json",
        "clamp": tmp_path / "clamp.json",
        "output": tmp_path / "validation_analysis.json",
    }
    paths["campaign"].write_text(json.dumps(campaign), encoding="utf-8")
    paths["benchmark"].write_text(
        json.dumps({
            "pairs": {
                BTC: {
                    "buildable": True,
                    "nav": bench,
                    "returns": rc.daily_returns(bench),
                    "comparability": {"comparable": True},
                }
            }
        }),
        encoding="utf-8",
    )
    paths["coverage"].write_text(
        json.dumps({"pairs": {BTC: {"admissible": True}}}), encoding="utf-8"
    )
    paths["validation_campaign"].write_text(
        json.dumps({"ok": True, "exit_code": 0, "failed": []}), encoding="utf-8"
    )
    paths["signatures"].write_text(json.dumps(_signatures()), encoding="utf-8")
    paths["clamp"].write_text(json.dumps(_clamp()), encoding="utf-8")
    code = eff.main([
        "--campaign", str(paths["campaign"]),
        "--benchmark", str(paths["benchmark"]),
        "--coverage", str(paths["coverage"]),
        "--validation", str(paths["validation_campaign"]),
        "--calibration", str(paths["calibration"]),
        "--output", str(paths["effect"]),
        "--bootstrap-b", "40",
        "--block-lengths", "10",
        "--now", NOW,
    ])
    return {"code": code, "paths": paths}


def test_the_in_process_rerun_reproduces_lb_bit_for_bit(real_effect: dict[str, Any]) -> None:
    """No ``--rerun`` artifact: the script re-runs ``rejeu_effect`` on the same inputs itself."""
    assert real_effect["code"] == 0
    paths = real_effect["paths"]
    code = rva.main([
        "--effect", str(paths["effect"]),
        "--signatures", str(paths["signatures"]),
        "--clamp", str(paths["clamp"]),
        "--campaign", str(paths["campaign"]),
        "--benchmark", str(paths["benchmark"]),
        "--coverage", str(paths["coverage"]),
        "--validation", str(paths["validation_campaign"]),
        "--calibration", str(paths["calibration"]),
        "--output", str(paths["output"]),
        "--now", NOW,
    ])
    payload = json.loads(paths["output"].read_text(encoding="utf-8"))
    row = _row(payload, "I-B.5")
    assert row["ok"] is True, row["detail"]
    assert "in-process rejeu_effect rerun" in row["detail"]
    # B and the block lengths were overridden for this test, and the artifact says so: I-B.2 is
    # the assertion that refuses to call such a run a campaign run.
    assert code == 2 and payload["failed"] == ["I-B.2"]


def test_the_real_artifact_carries_the_fields_ib1_demands(real_effect: dict[str, Any]) -> None:
    payload = json.loads(real_effect["paths"]["effect"].read_text(encoding="utf-8"))
    ctx_paths = {name: Path(path) for name, path in real_effect["paths"].items()}
    ctx = rva.Context(
        effect=payload, effect_error=None, signatures=None, signatures_error="missing",
        clamp=None, clamp_error="missing", rerun=None, rerun_error="not given",
        paths=ctx_paths, sha256={}, prespec=rva.prespec_descriptor(),
    )
    problems, _notes = rva.b01_recorded_fields(ctx)
    assert problems == []
    problems, _notes = rva.b04_first_failing_gate(ctx)
    assert problems == []
