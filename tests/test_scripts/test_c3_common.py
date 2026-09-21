"""C3 — le module commun : scan de source, registre des seuils, accesseur strict.

Le **scan de source** est la garde structurelle contre trois défauts qui sont chacun déjà arrivés :

* importer un seuil du rejeu par transitivité (§ 0.5 du protocole, antériorité) ;
* passer une donnée externe par ``bool(...)``, qui rend ``"false"`` vrai ;
* lire un champ obligatoire par ``.get(clé, défaut)``, qui rend un compteur absent égal à zéro.

Il travaille sur l'**AST** de chaque ``scripts/audit/c3_*.py`` — pas sur le texte — pour ne pas être
trompé par une docstring ou un commentaire, et pour ne pas confondre ``require_bool(`` avec ``bool(``.
La liste blanche des champs réellement optionnels est ``c3_common.OPTIONAL_FIELDS`` : un ``.get`` n'est
accepté que sur une clé constante qui y figure.
"""

# ruff: noqa: E402
from __future__ import annotations

import ast
import math
from pathlib import Path
import sys

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "scripts" / "audit"))

import c3_common as cc

C3_SOURCES = sorted((_project_root / "scripts" / "audit").glob("c3_*.py"))


def _trees() -> list[tuple[Path, ast.Module]]:
    assert C3_SOURCES, "aucune source c3_*.py trouvée"
    return [(p, ast.parse(p.read_text(encoding="utf-8"), filename=str(p))) for p in C3_SOURCES]


# ---------------------------------------------------------------------------
# Scan de source
# ---------------------------------------------------------------------------


def test_aucun_seuil_du_rejeu_n_est_importe_dans_c3() -> None:
    """§ 0.5 : réutiliser un seuil du rejeu serait du blanchiment de seuil."""
    forbidden = set(cc.FORBIDDEN_REJEU_NAMES)
    hits: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "rejeu_common":
                hits += [
                    f"{path.name}:{node.lineno} from rejeu_common import {a.name}"
                    for a in node.names
                    if a.name in forbidden
                ]
            if (
                isinstance(node, ast.Attribute)
                and node.attr in forbidden
                and isinstance(node.value, ast.Name)
                and node.value.id in ("rc", "rejeu_common")
            ):
                hits.append(f"{path.name}:{node.lineno} {node.value.id}.{node.attr}")
    assert hits == [], "seuils du rejeu importés : " + "; ".join(hits)


def test_aucun_bool_applique_dans_les_sources_c3() -> None:
    """`bool("false")` vaut `True` : un statut déclaré passe par `require_bool`, jamais par `bool(`."""
    hits = [
        f"{path.name}:{node.lineno}"
        for path, tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool"
    ]
    assert hits == [], "bool(...) appliqué à une donnée : " + ", ".join(hits)


def test_aucun_get_hors_liste_blanche_dans_les_sources_c3() -> None:
    """`.get(clé, défaut)` sur un champ obligatoire fait d'une absence une valeur. Liste blanche seule."""
    hits: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
            ):
                continue
            key = node.args[0] if node.args else None
            allowed = (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value in cc.OPTIONAL_FIELDS
            )
            if not allowed:
                shown = ast.unparse(key) if key is not None else "<sans clé>"
                hits.append(f"{path.name}:{node.lineno} .get({shown})")
    assert hits == [], "accès .get hors liste blanche : " + "; ".join(hits)


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


@pytest.mark.parametrize(
    ("prefix", "allowed"),
    [("optional_", cc.OPTIONAL_FIELDS), ("nullable_", cc.NULLABLE_FIELDS)],
    ids=["optional_* -> OPTIONAL_FIELDS", "nullable_* -> NULLABLE_FIELDS"],
)
def test_les_accesseurs_optionnels_et_nullables_ne_lisent_que_leur_liste_close(
    prefix: str, allowed: frozenset[str]
) -> None:
    """`optional_*(obj, clé)` et `nullable_*(obj, clé)` n'acceptent qu'une clé constante de leur liste.

    C'est ce qui empêche un champ obligatoire de devenir optionnel par un simple changement
    d'accesseur : la clé doit être **nommée** dans la liste close, avec la raison de sa nullité.
    """
    hits: list[str] = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called_name(node)
            if name is None or not name.startswith(prefix):
                continue
            key = node.args[1] if len(node.args) > 1 else None
            ok = (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value in allowed
            )
            if not ok:
                shown = ast.unparse(key) if key is not None else "<sans clé>"
                hits.append(f"{path.name}:{node.lineno} {name}(..., {shown})")
    assert hits == [], f"accès {prefix}* hors liste close : " + "; ".join(hits)


def test_les_listes_de_champs_optionnels_et_nullables_sont_closes_et_nommees() -> None:
    assert cc.OPTIONAL_FIELDS == frozenset(
        {
            "estimability",
            "liquidation",
            "dca_counters",
            "lots",
            "flat_start_proof",
            "first_fill_at",
            "decision_timeframes",
        }
    )
    assert cc.NULLABLE_FIELDS == frozenset(
        {
            "stale_by_candles",
            "first",
            "last",
            "timestamp",
            "reference_price",
            "price",
            "spread_pct",
            "slippage_pct",
            "avg_holding_minutes",
            "entry_price",
            "pnl",
        }
    )
    assert not (cc.OPTIONAL_FIELDS & cc.NULLABLE_FIELDS), (
        "un champ est optionnel ou nullable, pas les deux"
    )


# ---------------------------------------------------------------------------
# Registre des seuils (§ 0.5)
# ---------------------------------------------------------------------------


def test_chaque_seuil_porte_une_classe_connue_et_une_section() -> None:
    classes = {
        cc.CLASS_MATH,
        cc.CLASS_DATA,
        cc.CLASS_ECON,
        cc.CLASS_CONTRACT,
        cc.CLASS_METHOD,
        cc.CLASS_GUARD,
    }
    assert len(cc.THRESHOLDS) == 23
    for name, (_value, klass, section) in cc.THRESHOLDS.items():
        assert klass in classes, name
        assert section.startswith("§ "), name


def test_un_seuil_declare_deux_fois_leve() -> None:
    with pytest.raises(ValueError, match="deux fois"):
        cc._t("ANCHOR_FRACTION", 0.5, cc.CLASS_ECON, "§ A.3")


def test_les_conventions_non_decisionnelles_ne_sont_pas_au_registre() -> None:
    for name in (
        "ANNUALISATION_DAYS",
        "MATCHINGS",
        "RETURN_DOMAIN_FLOOR",
        "WARMUP_GAP_TOLERANCE",
        "WEEK_MINUTES",
        "D1_INTERVALS",
    ):
        assert name not in cc.THRESHOLDS
        assert hasattr(cc, name)


# ---------------------------------------------------------------------------
# Accesseurs optionnels et nullables — absent, null, mal typé, chacun à sa place
# ---------------------------------------------------------------------------


def test_optional_mapping_distingue_absent_null_et_mal_type() -> None:
    assert cc.optional_mapping({}, "liquidation", where="t") is None
    assert cc.optional_mapping({"liquidation": None}, "liquidation", where="t") is None
    assert cc.optional_mapping({"liquidation": {"a": 1}}, "liquidation", where="t") == {"a": 1}
    with pytest.raises(cc.MissingEvidenceError, match="bloc attendu"):
        cc.optional_mapping({"liquidation": "x"}, "liquidation", where="t")
    with pytest.raises(cc.MissingEvidenceError, match="bloc attendu"):
        cc.optional_mapping("pas un bloc", "liquidation", where="t")


def test_nullable_int_exige_la_cle_et_accepte_null() -> None:
    assert cc.nullable_int({"stale_by_candles": None}, "stale_by_candles", where="t") is None
    assert cc.nullable_int({"stale_by_candles": 0}, "stale_by_candles", where="t") == 0
    with pytest.raises(cc.MissingEvidenceError, match="jamais absente"):
        cc.nullable_int({}, "stale_by_candles", where="t")
    with pytest.raises(cc.MissingEvidenceError, match="entier attendu"):
        cc.nullable_int({"stale_by_candles": True}, "stale_by_candles", where="t")
    with pytest.raises(cc.InvalidValueError, match="minimum"):
        cc.nullable_int({"stale_by_candles": -1}, "stale_by_candles", where="t", minimum=0)


@pytest.mark.parametrize("value", ["0.0002", 5, 1000.0, "1E-27"])
def test_require_decimal_accepte_les_formes_exportees(value: object) -> None:
    from decimal import Decimal

    assert cc.require_decimal({"price": value}, "price", where="t") == Decimal(str(value))


@pytest.mark.parametrize("value", [True, "abc", [], {}, None])
def test_require_decimal_refuse_les_types_faux(value: object) -> None:
    with pytest.raises(cc.MissingEvidenceError):
        cc.require_decimal({"price": value}, "price", where="t")


def test_require_decimal_non_fini_est_une_erreur_de_valeur() -> None:
    with pytest.raises(cc.InvalidValueError, match="non finie"):
        cc.require_decimal({"price": "NaN"}, "price", where="t")
    with pytest.raises(cc.InvalidValueError, match="non finie"):
        cc.require_decimal({"price": float("inf")}, "price", where="t")


def test_parse_datetime_exige_un_fuseau() -> None:
    with pytest.raises(cc.MissingEvidenceError, match="sans fuseau"):
        cc.parse_datetime("2025-05-07T04:48:00", where="t")
    with pytest.raises(cc.MissingEvidenceError, match="instant ISO"):
        cc.parse_datetime("hier", where="t")
    with pytest.raises(cc.MissingEvidenceError, match="instant ISO attendu"):
        cc.parse_datetime(20250507, where="t")
    parsed = cc.parse_datetime("2025-05-07T06:48:00+02:00", where="t")
    assert parsed.isoformat() == "2025-05-07T04:48:00+00:00"


# ---------------------------------------------------------------------------
# § A.8 D1 — dénominateurs recalculés depuis les bornes ; § A.9 / § F.2 — recalculs quotidiens
# ---------------------------------------------------------------------------


def test_unites_attendues_du_prefixe_declare() -> None:
    """767 jours entiers et 110 périodes hebdomadaires sur [2023-04-01, 2025-05-07T04:48] (§ A.8)."""
    from datetime import UTC, datetime

    start = datetime(2023, 4, 1, tzinfo=UTC)
    anchor = cc.anchor_of(start, datetime(2026, 4, 1, tzinfo=UTC))
    assert anchor.isoformat() == "2025-05-07T04:48:00+00:00"
    assert cc.full_days_in(start, anchor) == 767
    assert cc.weekly_stamps_in(start, anchor) == 110
    assert cc.expected_units(start, anchor, 5) == 767
    assert cc.expected_units(start, anchor, 10080) == 110
    assert cc.coverage_unit(10080) == "week" and cc.coverage_unit(1440) == "day"
    # Un préfixe trop court pour un jour entier ne compte aucune unité — et ne divise jamais par zéro.
    assert cc.full_days_in(start, start.replace(hour=4)) == 0
    assert cc.max_gap_days(767.2) == pytest.approx(23.016)
    assert cc.max_gap_days(3000.0) == 31.0


def test_recompute_daily_sur_une_trajectoire_saine() -> None:
    values = [1000.0, 1010.0, 1005.0, 1020.0]
    rec = cc.recompute_daily(values, days=3.0)
    assert rec.n_points == 4 and rec.undefined_returns == 0 and rec.domain_ok
    assert rec.returns == pytest.approx((0.01, 1005.0 / 1010.0 - 1.0, 1020.0 / 1005.0 - 1.0))
    assert rec.cagr_pct is not None and rec.cagr_pct > 0
    assert rec.mdd_daily == pytest.approx((1010.0 - 1005.0) / 1010.0 * 100.0)
    assert rec.sigma_daily is not None and rec.sigma_daily > 0
    assert rec.alert_days == ()


def test_recompute_daily_ruine_et_alerte() -> None:
    """Une NAV à 0 rend le rendement suivant indéfini (D4) ; un jour à −50 % est une alerte, pas un retrait."""
    rec = cc.recompute_daily([1000.0, 400.0, 0.0, 0.0], days=3.0)
    assert rec.undefined_returns == 1
    assert not rec.domain_ok
    assert rec.cagr_pct is None
    assert rec.alert_days == (1, 2)
    assert rec.mdd_daily == pytest.approx(100.0)


def test_warmup_sufficient_recalcule_selon_la_regle_c2() -> None:
    block = {
        "required": 50,
        "loaded": 91,
        "stale_by_candles": 0,
        "largest_gap_candles": 0,
        "sufficient": True,
    }
    assert cc.warmup_sufficient(block, where="t") == (True, True)
    gap = {**block, "largest_gap_candles": 163, "sufficient": False}
    assert cc.warmup_sufficient(gap, where="t") == (False, False)
    nothing = {
        "required": 14,
        "loaded": 0,
        "stale_by_candles": None,
        "largest_gap_candles": 0,
        "sufficient": False,
    }
    assert cc.warmup_sufficient(nothing, where="t") == (False, False)
    contradicted = {**block, "sufficient": False}
    assert cc.warmup_sufficient(contradicted, where="t") == (True, False)
    with pytest.raises(cc.MissingEvidenceError, match="jamais absente"):
        cc.warmup_sufficient({k: v for k, v in block.items() if k != "stale_by_candles"}, where="t")


# ---------------------------------------------------------------------------
# Accesseur strict — présence / type (code 2) contre valeur (code 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("obj", [{}, {"k": None}])
def test_absent_ou_nul_est_une_erreur_de_presence(obj: dict) -> None:
    with pytest.raises(cc.MissingEvidenceError):
        cc.require_bool(obj, "k", where="t")
    with pytest.raises(cc.MissingEvidenceError):
        cc.require_float(obj, "k", where="t")
    with pytest.raises(cc.MissingEvidenceError):
        cc.require_int(obj, "k", where="t")


@pytest.mark.parametrize("value", [1, 0, "true", "false", "", 1.0, [], {}])
def test_un_booleen_n_est_ni_un_entier_ni_une_chaine(value: object) -> None:
    with pytest.raises(cc.MissingEvidenceError, match="booléen attendu"):
        cc.require_bool({"k": value}, "k", where="t")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_fini_est_une_erreur_de_valeur_pas_de_presence(value: float) -> None:
    with pytest.raises(cc.InvalidValueError, match="non finie"):
        cc.require_float({"k": value}, "k", where="t")
    with pytest.raises(cc.InvalidValueError):
        cc.require_finite_series({"k": [0.1, value]}, "k", where="t")


def test_les_deux_classes_d_erreur_sont_disjointes() -> None:
    assert not issubclass(cc.InvalidValueError, cc.MissingEvidenceError)
    assert issubclass(cc.EntryRefusedError, cc.MissingEvidenceError)
    assert cc.EntryRefusedError("R0_INVALID_RUN", "x").reason == "R0_INVALID_RUN"


def test_require_int_n_a_aucun_defaut_et_respecte_le_minimum() -> None:
    with pytest.raises(cc.MissingEvidenceError):
        cc.require_int({}, "n", where="t")
    with pytest.raises(cc.MissingEvidenceError, match="entier attendu"):
        cc.require_int({"n": True}, "n", where="t")
    with pytest.raises(cc.InvalidValueError, match="minimum"):
        cc.require_int({"n": -1}, "n", where="t", minimum=0)
    assert cc.require_int({"n": 0}, "n", where="t", minimum=0) == 0


def test_serie_vide_documentee_contre_serie_absente() -> None:
    assert cc.require_finite_series({"s": []}, "s", where="t", min_len=0) == []
    with pytest.raises(cc.MissingEvidenceError, match="minimum 1"):
        cc.require_finite_series({"s": []}, "s", where="t")
    with pytest.raises(cc.MissingEvidenceError, match="clé absente"):
        cc.require_finite_series({}, "s", where="t", min_len=0)


def test_domaine_des_rendements_en_plus_de_la_finitude() -> None:
    with pytest.raises(cc.InvalidValueError, match="hors domaine"):
        cc.require_finite_series(
            {"r": [0.01, -1.0]}, "r", where="t", domain_floor=cc.RETURN_DOMAIN_FLOOR
        )
    ok = cc.require_finite_series(
        {"r": [0.01, -0.99]}, "r", where="t", domain_floor=cc.RETURN_DOMAIN_FLOOR
    )
    assert ok == [0.01, -0.99]
    # La raison de la garde : `log1p(-1)` n'est pas -inf en Python, c'est une exception.
    with pytest.raises(ValueError):
        math.log1p(-1.0)
    assert math.log1p(-0.99) < 0


def test_require_str_refuse_hors_liste_close() -> None:
    with pytest.raises(cc.MissingEvidenceError, match="hors liste close"):
        cc.require_str({"p": "propre"}, "p", where="t", allowed=cc.PROVENANCES)
    assert cc.require_str({"p": "clean"}, "p", where="t", allowed=cc.PROVENANCES) == "clean"


# ---------------------------------------------------------------------------
# Fixtures synthétiques partagées (§ D.4 : « générées en code ») — importées par les autres
# `test_c3_*.py` sous `test_scripts.test_c3_common`. Un monde synthétique conforme au contrat : une
# fenêtre gelée, deux paires, une stratégie grid, N candidats par paire, un préfixe `train` et deux
# segments futurs bien formés que π_T doit écarter sans les lire.
# ---------------------------------------------------------------------------

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

WINDOW_START = datetime(2023, 4, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 4, 1, tzinfo=UTC)
ANCHOR = datetime(2025, 5, 7, 4, 48, tzinfo=UTC)
PAIRS: tuple[str, ...] = ("BTC/USDC", "SOL/USDC")
STRATEGY = "synth_grid"
PREFIX = "train"
TIMEFRAMES: dict[str, int] = {"5m": 5, "4h": 240, "1d": 1440, "1w": 10080}
DECISION_TFS: tuple[str, ...] = ("4h", "1d", "1w")
PAIR_COSTS: dict[str, tuple[str, str]] = {
    "BTC/USDC": ("0.0002", "0.0002"),
    "SOL/USDC": ("0.0011", "0.0002"),
}
TAKER = "0.0025"
EXEC_INTERVAL = 5
NOW = "2026-09-22T00:00:00+00:00"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def thresholds_block() -> dict[str, dict[str, Any]]:
    """Le registre `THRESHOLDS` tel qu'un manifeste conforme le déclare (valeur, classe, section)."""
    return {
        name: {"value": _jsonable(value), "class": klass, "section": section}
        for name, (value, klass, section) in cc.THRESHOLDS.items()
    }


def default_params(pair: str, index: int) -> dict[str, Any]:
    return {
        "min_spacing_pct": 0.01 + 0.005 * index,
        "atr_multiplier": 1.5 + 0.5 * index,
        "tag": pair[:3],
    }


def manifest(
    *,
    provenance: str = cc.PROVENANCE_CLEAN,
    n_per_pair: int = 3,
    pairs: tuple[str, ...] = PAIRS,
    candidates: list[dict[str, Any]] | None = None,
    variant_id: str = "synth-root",
    parent: dict[str, Any] | None = None,
    protocol_sha256: str | None = None,
    prefix_segment: str = PREFIX,
) -> dict[str, Any]:
    """Un manifeste **conforme** (§ A.6, valeurs gelées incluses) ; chaque test le déforme ensuite."""
    if candidates is None:
        candidates = [
            {"strategy": STRATEGY, "pair": pair, "params": default_params(pair, i)}
            for pair in pairs
            for i in range(n_per_pair)
        ]
    return {
        "window": {"start": WINDOW_START.isoformat(), "end": WINDOW_END.isoformat()},
        "anchor_fraction": cc.ANCHOR_FRACTION,
        "prefix_segment": prefix_segment,
        "data": {
            "exchange": "binance",
            "exec_interval": EXEC_INTERVAL,
            "timeframes": dict(TIMEFRAMES),
        },
        "fees": {
            "model": "bybit",
            "taker": TAKER,
            "pair_costs_file": "config/pair_costs_b4.json",
            "pair_costs": {p: {"spread": s, "slippage": sl} for p, (s, sl) in PAIR_COSTS.items()},
        },
        "min_order_usdc": 5.0,
        "universe": {"provenance": provenance, "candidates": candidates},
        "strategies": {STRATEGY: {"engine": "grid", "decision_timeframes": list(DECISION_TFS)}},
        "selection_rule": {
            "text": "§ A.10 : D1-D6, puis P1∧P2∧P3, puis classement par Δ^dd (§ A.9)",
            "thresholds": thresholds_block(),
        },
        "benchmark": {
            "definition": "§ C.3/C.4 : blend statique B&H/cash apparié en drawdown",
            "lambda_mode": "prefix",
        },
        "gates_Q": {"Q1": "net_pnl > 0", "Q2": "CAGR >= 2 %/an", "Q3": "Δ^dd > 0"},
        "uncertainty": {
            "seed": 20260921,
            "B": cc.BOOTSTRAP_B,
            "block_lengths": list(cc.BLOCK_LENGTHS),
            "bound_level": cc.BOUND_LEVEL,
        },
        "variant_id": variant_id,
        "parent": parent if parent is not None else {"is_root": True},
        "research_log_entry": "docs/RESEARCH_LOG.md — entrée synthétique (fixture)",
        "protocol_sha256": protocol_sha256
        if protocol_sha256 is not None
        else cc.protocol_descriptor()["sha256"],
    }


def write_manifest(tmp_path: Any, payload: dict[str, Any], name: str = "manifest.json") -> Any:
    path = tmp_path / name
    cc.write_json(path, payload)
    return path


def anchor_argv(
    tmp_path: Any,
    manifest_path: Any,
    *,
    registry: str = "variants.json",
    output: str = "anchor.json",
) -> list[str]:
    return [
        "--manifest",
        str(manifest_path),
        "--registry",
        str(tmp_path / registry),
        "--output",
        str(tmp_path / output),
        "--now",
        NOW,
    ]
