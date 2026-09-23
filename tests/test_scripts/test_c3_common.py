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
            "exec_interval",
            "run_scope",
            "deployment_pairs",
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
            "refusal",
            "retained",
            "reason",
            "liquidation_normalised",
            "bound",
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
    # Revue R3 (d) : la non-finitude levée par `canon` (héritée de rejeu_common) n'est **pas** une
    # `InvalidValueError` — chaque `main()` doit la router explicitement vers la voie violation.
    assert not issubclass(cc.NonFiniteValueError, cc.InvalidValueError)
    assert issubclass(cc.NonFiniteValueError, ValueError)
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
# § A.6 v2.1 — transposition déclarée (AM-04) : validation sur une paire, déploiement sur une autre
# ---------------------------------------------------------------------------


def _with_deployment(mapping: object) -> dict[str, Any]:
    payload = manifest()
    payload["universe"]["deployment_pairs"] = mapping
    return payload


def test_une_transposition_de_cotation_entre_dans_l_empreinte_pas_dans_l_identite() -> None:
    """§ A.6 v2.1 : « la paire de déploiement entre dans le manifeste, donc dans l'empreinte de la variante, et
    **n'entre pas** dans l'identité du candidat » (§ A.2 : `pair = paire de validation`)."""
    bare = manifest()
    declared = _with_deployment({"BTC/USDC": "BTC/USDT"})
    loaded = cc.load_manifest(declared)
    assert dict(loaded.deployment_pairs) == {"BTC/USDC": "BTC/USDT"}
    assert dict(cc.load_manifest(bare).deployment_pairs) == {}, (
        "aucune transposition n'est présumée"
    )
    assert cc.sig(declared) != cc.sig(bare)
    assert [c.identity for c in loaded.candidates] == [
        c.identity for c in cc.load_manifest(bare).candidates
    ]


@pytest.mark.parametrize(
    ("mapping", "fragment"),
    [
        pytest.param({"BTC/USDC": "ETH/USDT"}, "actif de base", id="actif de base différent"),
        pytest.param({"BTC/USDC": "BTC/USDC"}, "même monnaie de cotation", id="même paire"),
        pytest.param({"ETH/USDC": "ETH/USDT"}, "univers", id="paire hors univers"),
        pytest.param({"BTC/USDC": "BTCUSDT"}, "forme", id="paire mal formée"),
        pytest.param({"BTC/USDC": 1}, "chaîne attendue", id="valeur non chaîne"),
        pytest.param(["BTC/USDT"], "bloc attendu", id="pas un bloc"),
    ],
)
def test_une_transposition_hors_contrat_est_une_erreur_d_entree(
    mapping: object, fragment: str
) -> None:
    """§ A.6 v2.1 : une paire de déploiement distincte « quand, et seulement quand, l'actif de base est le même
    et seule la monnaie de cotation diffère » — tout autre couple est une erreur d'entrée (§ I.1, ligne 2)."""
    with pytest.raises(cc.MissingEvidenceError, match=fragment):
        cc.load_manifest(_with_deployment(mapping))


# ---------------------------------------------------------------------------
# § A.8 v2.1 — les nombres de l'encart « Conséquences de D2 et de D1 sur la fenêtre de v2.1 » (AM-05)
# ---------------------------------------------------------------------------

#: Encart § A.8 v2.1 : les six estampilles 1 w manquantes dans le préfixe, les mêmes sur les trois paires.
V21_MISSING_1W_IN_PREFIX = (
    (2022, 6, 6),
    (2022, 7, 4),
    (2022, 9, 5),
    (2022, 10, 3),
    (2022, 11, 7),
    (2022, 12, 5),
)


def test_l_encart_v21_dit_ce_que_D1_mesure_sur_le_1w_du_prefixe() -> None:
    """Encart § A.8 v2.1 : « Sur les 194 périodes hebdomadaires de (2021-03-01, T], 188 sont présentes, soit
    96,9 %, sous les 97 % de D1 […] ; le trou maximal, 7 jours, reste sous la borne de 31 jours »."""
    start = datetime(2021, 3, 1, tzinfo=UTC)
    anchor = cc.anchor_of(start, datetime(2026, 6, 29, tzinfo=UTC))
    missing = [datetime(y, m, d, tzinfo=UTC) for (y, m, d) in V21_MISSING_1W_IN_PREFIX]
    assert all(start < stamp <= anchor for stamp in missing), "les six tombent dans le préfixe"
    assert all(cc.last_stamp_at_or_before(s, cc.WEEK_MINUTES) == s for s in missing)
    units = cc.expected_units(start, anchor, cc.WEEK_MINUTES)
    assert units == 194
    assert (units - len(missing)) / units < cc.COVERAGE_MIN_RATIO, "D1 échoue sur le 1 w"
    prefix_days = (anchor - start).total_seconds() / 86400.0
    assert cc.gap_days(1, cc.WEEK_MINUTES) == 7.0 <= cc.max_gap_days(prefix_days)


# ---------------------------------------------------------------------------
# § A.13 E2 v2.1 (AM-09) et § F.2 (e) v2.1 (AM-16) — au niveau fonction
# ---------------------------------------------------------------------------

#: § F.2 (h) : les six combinaisons `L × appariement`, `L ∈ {10, 21, 42}`, appariement en drawdown ou en
#: écart-type — sous la forme `L:appariement` des clés de l'artefact d'évaluation.
COMBINATIONS_F2H = ("10:dd", "10:sigma", "21:dd", "21:sigma", "42:dd", "42:sigma")


def test_les_six_combinaisons_sont_celles_du_texte() -> None:
    assert cc.COMBINATIONS == COMBINATIONS_F2H


def _suites(**overrides: tuple[list[float], int]) -> dict[str, tuple[list[float], int]]:
    varying = [0.1 * i for i in range(50)]
    suites = {c: (list(varying), 0) for c in COMBINATIONS_F2H}
    suites.update(overrides)
    return suites


_ACTIVE = [0.01, -0.01] * 20


def test_E2_se_calcule_sur_chacune_des_six_distributions() -> None:
    """§ A.13 v2.1, E2 : « Une seule distribution constante suffit à faire échouer E2 »."""
    est = cc.combined_estimability(_ACTIVE, _suites(**{"42:sigma": ([0.25] * 50, 0)}))
    assert est.e1 is True
    assert est.e2 is False and est.ok is False
    assert [c for c, e in est.per_combination.items() if not e.e2] == ["42:sigma"]
    assert cc.combined_estimability(_ACTIVE, _suites()).e2 is True


def test_le_plafond_de_replications_ecartees_s_applique_par_combinaison() -> None:
    """§ F.2 (e) v2.1 : au-delà de 10 écartées « sur l'une quelconque des six combinaisons », l'inférence est
    inutilisable ; 10 reste tolérable (≤ 10 sur 10 000)."""
    over = cc.combined_estimability(
        _ACTIVE, _suites(**{"10:dd": ([0.1 * i for i in range(50)], 11)})
    )
    assert over.within_ceiling is False and over.ok is False
    at = cc.combined_estimability(_ACTIVE, _suites(**{"10:dd": ([0.1 * i for i in range(50)], 10)}))
    assert at.within_ceiling is True and at.ok is True


def _resuffix_block(block: dict[str, Any], suffix: str) -> dict[str, Any]:
    """Le bloc de liquidation, ses quatre quantités en actif de base portant le suffixe demandé (§ A.7)."""
    out = {}
    for key, value in block.items():
        stem = next((s for s in BASE_QUANTITY_STEMS if key.startswith(f"{s}_")), None)
        out[f"{stem}_{suffix}" if stem is not None else key] = value
    if "lots" in out:
        out["lots"] = [_resuffix_block(dict(lot), suffix) for lot in out["lots"]]
    return out


def _identities(block: dict[str, Any]) -> dict[str, Any]:
    spread, slippage = (Decimal(x) for x in PAIR_COSTS["BTC/USDC"])
    return cc.liquidation_identities(
        block,
        spread=spread,
        slippage=slippage,
        taker=Decimal(TAKER),
        end=ANCHOR,
        where="t.liquidation",
    )


def test_les_quantites_en_actif_de_base_sont_celles_du_texte() -> None:
    """§ A.7 v2.1, ligne « Comptabilité » : `amount_base`, `residual_trade_base`, `dust_written_off_base`,
    `inventory_divergence_base` — la liste recopiée du texte, épinglée à la constante du code."""
    assert cc.BASE_QUANTITY_STEMS == BASE_QUANTITY_STEMS


def test_un_bloc_de_liquidation_en_base_passe_les_identites_et_la_preuve_par_lot() -> None:
    """§ A.7 v2.1 : les clés `amount_base`, `residual_trade_base`, `dust_written_off_base`,
    `inventory_divergence_base`, « quelle que soit la paire »."""
    block = _resuffix_block(liquidation_segment("BTC/USDC", reference_price="30000"), "base")
    proof = _identities(block)
    assert proof["passed"] is True and proof["lots_present"] is True
    assert set(proof["reported"]) >= {"dust_written_off_base", "inventory_divergence_base"}


@pytest.mark.parametrize("suffix", ["btc", "eth", "sol"])
def test_un_bloc_suffixe_par_un_actif_est_une_erreur_de_forme(suffix: str) -> None:
    """§ A.7 v2.1 : « un bloc qui porte une clé suffixée par le nom d'un actif (`_btc`, `_eth`, …) est une erreur
    de forme (§ I.1, ligne 2) » — le message nomme la clé `_base` attendue."""
    block = _resuffix_block(liquidation_segment("BTC/USDC", reference_price="30000"), suffix)
    with pytest.raises(cc.MissingEvidenceError, match="_base"):
        _identities(block)


def test_un_bloc_portant_les_deux_suffixes_est_une_erreur_de_forme() -> None:
    """§ A.7 v2.1 : une clé suffixée par un actif est une erreur de forme même à côté de sa jumelle `_base`."""
    block = _resuffix_block(liquidation_segment("BTC/USDC", reference_price="30000"), "base")
    block["dust_written_off_btc"] = block["dust_written_off_base"]
    with pytest.raises(cc.MissingEvidenceError, match="dust_written_off_base"):
        _identities(block)


def test_l_encart_v21_dit_ce_que_D2_mesure_sur_le_1w_de_SOL() -> None:
    """Encart § A.8 v2.1 : « Au 2021-03-01, SOL en porte 29 (première estampille 1 w le 2020-08-17) ; la 50ᵉ
    tombe le 2021-07-26 » — le régime 1 w exige 50 bougies."""
    first = datetime(2020, 8, 17, tzinfo=UTC)
    start = datetime(2021, 3, 1, tzinfo=UTC)
    assert cc.weekly_stamps_in(first - timedelta(days=7), start) == 29
    assert first + timedelta(weeks=49) == datetime(2021, 7, 26, tzinfo=UTC), "la 50ᵉ estampille"


# ---------------------------------------------------------------------------
# Fixtures synthétiques partagées (§ D.4 : « générées en code ») — importées par les autres
# `test_c3_*.py` sous `test_scripts.test_c3_common`. Un monde synthétique conforme au contrat : une
# fenêtre gelée, deux paires, une stratégie grid, N candidats par paire, un préfixe `train` et deux
# segments futurs bien formés que π_T doit écarter sans les lire.
# ---------------------------------------------------------------------------

from datetime import UTC, datetime, timedelta
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


# ---------------------------------------------------------------------------
# Observations, couverture et bougies synthétiques — le monde complet d'un run C3a
# ---------------------------------------------------------------------------

N_PREFIX_POINTS = len(cc.daily_grid(WINDOW_START, ANCHOR))  # 769 : début, 767 minuits, T
PREFIX_DAYS = (ANCHOR - WINDOW_START).total_seconds() / 86400.0  # 767.2
LAST_EXEC_STAMP = cc.last_stamp_at_or_before(ANCHOR, EXEC_INTERVAL)  # 04:45
FIRST_EXEC_STAMP = cc.first_stamp_strictly_after(WINDOW_START, EXEC_INTERVAL)  # 00:05
SEGMENT_FUTURE = ("test", "all")


#: § A.7 v2.1 — les quatre quantités en actif de base, suffixées `_base` quelle que soit la paire.
BASE_QUANTITY_STEMS: tuple[str, ...] = (
    "amount",
    "residual_trade",
    "dust_written_off",
    "inventory_divergence",
)


def base_asset(pair: str) -> str:
    """§ A.7 v2.1 : les quantités en actif de base sont suffixées `_base` **quelle que soit la paire** —
    la fixture reproduit l'export conforme (C3b), pas la convention littérale `_btc` du moteur."""
    del pair
    return "base"


def nav_path(
    pair: str, index: int, n_points: int = N_PREFIX_POINTS, *, drift: float | None = None
) -> list[float]:
    """Une trajectoire déterministe, distincte par (paire, candidat), jamais ruinée : dérive
    douce, bruit faible (bien sous la volatilité du B&H) et un repli de ~4 % sur vingt jours —
    un drawdown qui s'apparie sur la grille de λ au pas 0,001."""
    seed = (sum(ord(ch) for ch in pair) * 7 + index * 13) % 97
    step_drift = 0.0004 + 0.0002 * index if drift is None else drift
    dip_start = 200 + 17 * index
    values = [1000.0]
    for k in range(1, n_points):
        wobble = ((k * 31 + seed) % 23 - 11) / 4000.0
        dip = -0.002 if dip_start <= k < dip_start + 20 else 0.0
        values.append(round(values[-1] * (1.0 + step_drift + wobble + dip), 6))
    return values


def warmup_block(
    interval: int, *, required: int, loaded: int, gap: int = 0, stale: int | None = 0
) -> dict[str, Any]:
    sufficient = loaded >= required and stale == 0 and gap <= cc.WARMUP_GAP_TOLERANCE
    return {
        "interval": interval,
        "required": required,
        "loaded": loaded,
        "extended_by": 0,
        "stale_by_candles": stale,
        "largest_gap_candles": gap,
        "sufficient": sufficient,
        "first": None
        if loaded == 0
        else (WINDOW_START - timedelta(minutes=interval * loaded)).isoformat(),
        "last": None if loaded == 0 else WINDOW_START.isoformat(),
    }


def warmup_segment(*, sufficient: bool = True) -> dict[str, dict[str, Any]]:
    if sufficient:
        return {
            "4h": warmup_block(240, required=14, loaded=91),
            "1d": warmup_block(1440, required=50, loaded=91),
            "1w": warmup_block(10080, required=50, loaded=57),
        }
    return {
        "4h": warmup_block(240, required=14, loaded=91),
        "1d": warmup_block(1440, required=50, loaded=88, gap=163),
        "1w": warmup_block(10080, required=50, loaded=50, gap=23),
    }


def rejections_segment() -> dict[str, Any]:
    causes = (
        "ambiguous_sell_fill",
        "below_min_order",
        "incoherent_sell_fill",
        "insufficient_cash",
        "insufficient_inventory",
        "unmatched_position_id",
        "unmatched_sell_fills",
    )
    return {
        "unit": "(order, cause)",
        "by_cause": dict.fromkeys(causes, 0),
        "events": dict.fromkeys(causes, 0),
    }


def liquidation_segment(
    pair: str,
    *,
    reference_price: str,
    positions: int = 2,
    lots: bool = True,
    timestamp: datetime = LAST_EXEC_STAMP,
) -> dict[str, Any]:
    """Un bloc `liquidation` grid conforme, avec sa preuve par lot (§ 6.5) — poussière ≠ divergence
    volontairement (contre-exemple 2 : ce n'est pas une identité du moteur)."""
    spread, slippage = (Decimal(x) for x in PAIR_COSTS[pair])
    taker = Decimal(TAKER)
    reference = Decimal(reference_price)
    price = reference * (Decimal(1) - spread - slippage)
    lot_rows: list[dict[str, Any]] = []
    fees = Decimal(0)
    gross_total = Decimal(0)
    amount_total = Decimal(0)
    for i in range(positions):
        amount = Decimal("0.00025925") + Decimal(i) * Decimal("0.00001")
        gross = amount * price
        fee = gross * taker
        fees += fee
        gross_total += gross
        amount_total += amount
        lot_rows.append(
            {
                f"amount_{base_asset(pair)}": str(amount),
                "gross_usdc": str(gross),
                "fee": str(fee),
                "entry_price": str(reference * Decimal("0.98")),
                "pnl": str(gross - fee - amount * reference * Decimal("0.98")),
            }
        )
    block: dict[str, Any] = {
        "buy_fees": "1.7250",
        "sell_fees": "1.862219181251586203286056939",
        "net_pnl_lot_basis": "61.92250504972200892203442513",
        "residual_net_proceeds": "0",
        "avg_holding_minutes": 122180.0 if positions else None,
        "positions": positions,
        "trades": positions,
        f"residual_trade_{base_asset(pair)}": "0",
        f"dust_written_off_{base_asset(pair)}": "7E-28",
        f"inventory_divergence_{base_asset(pair)}": "1E-27",
        "pnl": "-1.11608608129261557311025728",
        "fees": str(fees),
        "gross_usdc": str(gross_total),
        "timestamp": timestamp.isoformat() if positions else None,
        "reference_price": str(reference) if positions else None,
        "price": str(price) if positions else None,
        "spread_pct": str(spread) if positions else None,
        "slippage_pct": str(slippage) if positions else None,
    }
    if lots:
        block["lots"] = lot_rows
    return block


def metrics_block(
    values: list[float], *, days: float, cycles: int = 40, positions: int = 2
) -> dict[str, Any]:
    """Un bloc de métriques cohérent avec la trajectoire qu'il accompagne (metrics_version 2)."""
    rec = cc.recompute_daily(values, days=days)
    return {
        "metrics_version": 2,
        "total_trades": cycles + positions,
        "winning_trades": cycles + positions - 1,
        "losing_trades": 1,
        "win_rate": (cycles + positions - 1) / (cycles + positions),
        "total_return_pct": (values[-1] / values[0] - 1.0) * 100.0,
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.9,
        "max_drawdown_pct_daily": rec.mdd_daily,
        "max_drawdown_pct_engine": rec.mdd_daily * 1.4,
        "profit_factor": 3.1,
        "calmar_ratio": 2.0,
        "net_pnl": values[-1] - values[0],
        "total_fees": 3.5872191812515863,
        "total_pnl": values[-1] - values[0] + 3.5872191812515863,
        "unrealized_pnl": -1.1160860812926157,
        "starting_balance": values[0],
        "ending_balance": values[-1],
        "duration_days": days,
        "average_holding_time_minutes": 2361.42,
        "gross_profit_net": 167.3,
        "gross_loss_net": 1.85,
        "pf_excluded_trades": 0,
        "n_daily_returns": len(values) - 1,
    }


def observation(
    strategy: str,
    pair: str,
    params: dict[str, Any],
    index: int,
    *,
    with_futures: bool = True,
    futures_variant: int = 0,
    lots: bool = True,
    sufficient: bool = True,
    exec_interval: int | None = EXEC_INTERVAL,
    cycles: int = 40,
    positions: int = 2,
    nav: list[float] | None = None,
    decision_timeframes: list[str] | None = None,
) -> dict[str, Any]:
    """Une entrée d'observation conforme au contrat (C1/C2), préfixe `train` + futurs optionnels ;
    elle exporte ses séries de décision (§ A.8 D2 v2.1), par défaut celles de la stratégie des fixtures."""
    values = nav if nav is not None else nav_path(pair, index)
    reference = f"{values[-1] * 33.5:.8f}"
    entry: dict[str, Any] = {
        "strategy": strategy,
        "pair": pair,
        "params": params,
        "decision_timeframes": list(
            decision_timeframes if decision_timeframes is not None else DECISION_TFS
        ),
        "effective_params": {
            "strategy_class": "SynthGrid",
            "passed_params": {**params, "pair": pair},
            "params": {k: {"value": v, "source": "override"} for k, v in params.items()},
        },
        "exchange": "binance",
        "fees": "bybit",
        "metrics_version": 2,
        "replay_version": 2,
        "pair_costs_file": "config/pair_costs_b4.json",
        "pair_costs": {"spread": PAIR_COSTS[pair][0], "slippage": PAIR_COSTS[pair][1]},
        "min_order_usdc": 5.0,
        "phase": "1",
        "window_idx": None,
        "period": {
            f"{PREFIX}_start": WINDOW_START.isoformat(),
            f"{PREFIX}_end": ANCHOR.isoformat(),
        },
        PREFIX: metrics_block(values, days=PREFIX_DAYS, cycles=cycles, positions=positions),
        "equity_daily": {
            PREFIX: {"start": WINDOW_START.isoformat(), "end": ANCHOR.isoformat(), "values": values}
        },
        "liquidation": {
            PREFIX: liquidation_segment(
                pair, reference_price=reference, positions=positions, lots=lots
            )
        },
        "warmup": {PREFIX: warmup_segment(sufficient=sufficient)},
        "rejections": {PREFIX: rejections_segment()},
        "dca_counters": None,
    }
    if exec_interval is not None:
        entry["exec_interval"] = exec_interval
    if with_futures:
        future_points = len(cc.daily_grid(ANCHOR, WINDOW_END))
        future_days = (WINDOW_END - ANCHOR).total_seconds() / 86400.0
        all_points = len(cc.daily_grid(WINDOW_START, WINDOW_END))
        all_days = (WINDOW_END - WINDOW_START).total_seconds() / 86400.0
        future_nav = nav_path(
            pair,
            index + 50 + futures_variant * 7,
            future_points,
            drift=0.0003 * (futures_variant + 1),
        )
        all_nav = nav_path(
            pair,
            index + 90 + futures_variant * 11,
            all_points,
            drift=0.0002 * (futures_variant + 1),
        )
        entry["period"].update(
            {"test_start": ANCHOR.isoformat(), "test_end": WINDOW_END.isoformat()}
        )
        entry["test"] = metrics_block(
            future_nav, days=future_days, cycles=15 + futures_variant, positions=1
        )
        entry["all"] = metrics_block(
            all_nav, days=all_days, cycles=60 + futures_variant, positions=3
        )
        entry["equity_daily"]["test"] = {
            "start": ANCHOR.isoformat(),
            "end": WINDOW_END.isoformat(),
            "values": future_nav,
        }
        entry["equity_daily"]["all"] = {
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "values": all_nav,
        }
        entry["liquidation"]["test"] = liquidation_segment(
            pair,
            reference_price=f"{future_nav[-1] * 31.0:.8f}",
            positions=1,
            lots=lots,
            timestamp=WINDOW_END - timedelta(minutes=EXEC_INTERVAL),
        )
        entry["liquidation"]["all"] = liquidation_segment(
            pair,
            reference_price=f"{all_nav[-1] * 29.0:.8f}",
            positions=3,
            lots=lots,
            timestamp=WINDOW_END - timedelta(minutes=EXEC_INTERVAL),
        )
        entry["warmup"]["test"] = warmup_segment(sufficient=True)
        entry["warmup"]["all"] = warmup_segment(sufficient=sufficient)
        entry["rejections"]["test"] = rejections_segment()
        entry["rejections"]["all"] = rejections_segment()
    return entry


def observation_key(strategy: str, pair: str, index: int) -> str:
    return f"{strategy}_{pair.replace('/', '_')}_p1_{index:04d}"


def observations(manifest_payload: dict[str, Any], **kw: Any) -> dict[str, dict[str, Any]]:
    """Le fichier d'observations d'un manifeste : une entrée par candidat de l'univers, dans l'ordre."""
    out: dict[str, dict[str, Any]] = {}
    counters: dict[str, int] = {}
    for cand in manifest_payload["universe"]["candidates"]:
        pair = cand["pair"]
        index = counters.get(pair, 0)
        counters[pair] = index + 1
        # § A.8 D2 v2.1 : l'observation exporte la liste effective **du candidat** — sa surcharge au
        # manifeste, sinon la déclaration de sa stratégie.
        effective = (
            cand.get("decision_timeframes")
            or manifest_payload["strategies"][cand["strategy"]]["decision_timeframes"]
        )
        out[observation_key(cand["strategy"], pair, index)] = observation(
            cand["strategy"], pair, cand["params"], index, decision_timeframes=effective, **kw
        )
    return out


def coverage(
    manifest_payload: dict[str, Any],
    *,
    start: datetime = WINDOW_START,
    end: datetime = ANCHOR,
    degrade: dict[str, dict[int, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """L'artefact de couverture (§ A.7) sur `[début, T]`, **cohérent par construction** : comptes
    de bougies et d'unités recalculés depuis les bornes ; `degrade[pair][interval]` surcharge."""
    pairs = sorted({c["pair"] for c in manifest_payload["universe"]["candidates"]})
    blocks: dict[str, Any] = {}
    for pair in pairs:
        blocks[pair] = {}
        for iv in cc.D1_INTERVALS:
            units = cc.expected_units(start, end, iv)
            candles_expected = cc.expected_candles(start, end, iv)
            block = {
                "observed": candles_expected,
                "expected": candles_expected,
                "covered_units": units,
                "expected_units": units,
                "unit": cc.coverage_unit(iv),
                "missing_stamps": [],
                "longest_gap_days": 0.0,
                "first_day": start.date().isoformat(),
                "last_day": end.date().isoformat(),
            }
            if degrade and pair in degrade and iv in degrade[pair]:
                block.update(degrade[pair][iv])
            blocks[pair][str(iv)] = block
    return {
        "generated_at": NOW,
        "source": "fixture synthétique (§ A.7 : produit hors chaîne)",
        "exchange": "binance",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "pairs": blocks,
    }


def degrade_coverage(
    cov: dict[str, Any],
    pair: str,
    interval: int,
    *,
    n_missing: int,
    offset_units: int = 100,
    start: datetime = WINDOW_START,
    end: datetime = ANCHOR,
) -> None:
    """Retire `n_missing` estampilles **consécutives** de la série, en gardant le bloc cohérent :
    `observed`, `covered_units` (règle de D1 propre à la série) et `longest_gap_days` suivent."""
    block = cov["pairs"][pair][str(interval)]
    step = timedelta(days=7) if interval == cc.WEEK_MINUTES else timedelta(minutes=interval)
    first = cc.first_stamp_strictly_after(start, interval) + step * offset_units
    stamps = [first + step * k for k in range(n_missing)]
    assert stamps[-1] <= end, "dégradation hors de la fenêtre"
    block["missing_stamps"] = [s.isoformat() for s in stamps]
    block["observed"] = block["expected"] - n_missing
    block["covered_units"] = cc.coverage_recompute(
        block, start=start, end=end, interval=interval, where="fixture"
    )["covered_recomputed"]
    block["longest_gap_days"] = cc.gap_days(n_missing, interval)


def candles(
    manifest_payload: dict[str, Any],
    *,
    start: datetime = WINDOW_START,
    end: datetime = ANCHOR,
    daily_scale: dict[str, float] | None = None,
    missing_exec: str | None = None,
    extra_stamp_after_end: bool = False,
) -> dict[str, Any]:
    """Les closes dont § C.3 a besoin : deux bougies d'exécution et un close 1 j par minuit intérieur."""
    pairs = sorted({c["pair"] for c in manifest_payload["universe"]["candidates"]})
    grid = cc.daily_grid(start, end)
    out: dict[str, Any] = {}
    for pair in pairs:
        scale = (daily_scale or {}).get(pair, 1.0)
        base = 30000.0 if pair.startswith("BTC") else 150.0
        daily = []
        for k, stamp in enumerate(grid[1:-1], start=1):
            # Un actif qui monte lentement, oscille largement (drawdowns réels de ~25 %) et bruite
            # chaque jour : le B&H plein notionnel est plus risqué que tout candidat synthétique.
            close = (
                base
                * scale
                * (1.0 + 0.0003 * k + 0.15 * math.sin(k / 60.0) + (((k * 17) % 29) - 14) / 1000.0)
            )
            daily.append({"t": stamp.isoformat(), "close": f"{close:.8f}"})
        exec_rows = [
            {
                "t": cc.first_stamp_strictly_after(start, EXEC_INTERVAL).isoformat(),
                "close": f"{base * scale:.8f}",
            },
            {
                "t": cc.last_stamp_at_or_before(end, EXEC_INTERVAL).isoformat(),
                "close": f"{base * scale * 1.21:.8f}",
            },
        ]
        if missing_exec == "entry":
            exec_rows = exec_rows[1:]
        elif missing_exec == "exit":
            exec_rows = exec_rows[:1]
        if extra_stamp_after_end:
            exec_rows.append(
                {
                    "t": (end + timedelta(minutes=EXEC_INTERVAL)).isoformat(),
                    "close": f"{base * scale:.8f}",
                }
            )
        out[pair] = {"exec_interval": EXEC_INTERVAL, "exec": exec_rows, "daily": daily}
    return {
        "generated_at": NOW,
        "source": "fixture synthétique (§ C.3 : produit hors chaîne)",
        "exchange": "binance",
        "pairs": out,
    }


def world(
    tmp_path: Any, manifest_payload: dict[str, Any] | None = None, **obs_kw: Any
) -> dict[str, Any]:
    """Écrit manifeste, observations, couverture et bougies dans `tmp_path` ; renvoie les chemins."""
    payload = manifest_payload if manifest_payload is not None else manifest()
    paths = {
        "manifest": tmp_path / "manifest.json",
        "observations": tmp_path / "observations.json",
        "coverage": tmp_path / "coverage.json",
        "candles": tmp_path / "candles.json",
    }
    cc.write_json(paths["manifest"], payload)
    cc.write_json(paths["observations"], observations(payload, **obs_kw))
    cc.write_json(paths["coverage"], coverage(payload))
    cc.write_json(paths["candles"], candles(payload))
    return {
        "payload": payload,
        **paths,
        "registry": tmp_path / "variants.json",
        "anchor": tmp_path / "anchor.json",
    }


# ---------------------------------------------------------------------------
# Revue R3 (2e passe, b) — le trou maximal est recalculé sur la grille attendue, bords compris
# ---------------------------------------------------------------------------


def _block_with_missing(
    stamps: list[datetime], *, interval: int, declared_gap: float
) -> dict[str, Any]:
    start, end = WINDOW_START, ANCHOR
    block = coverage(manifest())["pairs"]["BTC/USDC"][str(interval)]
    block["missing_stamps"] = [s.isoformat() for s in stamps]
    block["observed"] = block["expected"] - len(stamps)
    block["covered_units"] = cc.coverage_recompute(
        {**block, "longest_gap_days": declared_gap},
        start=start,
        end=end,
        interval=interval,
        where="t",
    )["covered_recomputed"]
    block["longest_gap_days"] = declared_gap
    return block


@pytest.mark.parametrize(
    ("interval", "k", "edge"),
    [(1440, 5, "start"), (1440, 4, "end"), (5, 300, "start"), (240, 7, "end"), (10080, 3, "start")],
    ids=["1j début", "1j fin", "5min début", "4h fin", "1w début"],
)
def test_revue_R3b_un_trou_en_bord_de_fenetre_est_vu_par_le_recalcul(
    interval: int, k: int, edge: str
) -> None:
    """Une série qui commence en retard ou s'arrête tôt est un trou — pas seulement un vide intérieur."""
    step = timedelta(days=7) if interval == cc.WEEK_MINUTES else timedelta(minutes=interval)
    first = cc.first_stamp_strictly_after(WINDOW_START, interval)
    last = cc.last_stamp_at_or_before(ANCHOR, interval)
    stamps = (
        [first + step * i for i in range(k)]
        if edge == "start"
        else [last - step * i for i in range(k)]
    )
    block = _block_with_missing(stamps, interval=interval, declared_gap=cc.gap_days(k, interval))
    rec = cc.coverage_recompute(block, start=WINDOW_START, end=ANCHOR, interval=interval, where="t")
    assert rec["longest_gap_candles"] == k
    assert rec["longest_gap_days_recomputed"] == cc.gap_days(k, interval)
    assert rec["problems"] == []
    # Le même bloc avec un trou déclaré nul est contredit.
    block["longest_gap_days"] = 0.0
    rec = cc.coverage_recompute(block, start=WINDOW_START, end=ANCHOR, interval=interval, where="t")
    assert any("longest_gap_days" in p for p in rec["problems"])


def test_revue_R3b_le_plus_long_run_est_pris_parmi_plusieurs_trous() -> None:
    day = timedelta(days=1)
    first = cc.first_stamp_strictly_after(WINDOW_START, 1440)
    stamps = (
        [first + day * i for i in (10, 11, 12)]
        + [first + day * i for i in (50, 51, 52, 53, 54)]
        + [first + day * 200]
    )
    block = _block_with_missing(stamps, interval=1440, declared_gap=5.0)
    rec = cc.coverage_recompute(block, start=WINDOW_START, end=ANCHOR, interval=1440, where="t")
    assert rec["longest_gap_candles"] == 5 and rec["problems"] == []


# ---------------------------------------------------------------------------
# Évaluation synthétique (§ L.1 : C3a n'exerce les étapes 5 et 6 que sur des fixtures)
# ---------------------------------------------------------------------------

from collections.abc import Mapping, Sequence  # noqa: E402
import copy  # noqa: E402
from functools import cache  # noqa: E402
import platform  # noqa: E402

import numpy as np  # noqa: E402

N_EVAL_POINTS = len(cc.daily_grid(ANCHOR, WINDOW_END))  # 330
EVAL_DAYS = (WINDOW_END - ANCHOR).total_seconds() / 86400.0  # 328.8
SEED = 20260921


# ---------------------------------------------------------------------------
# § F.2 (b), (c), (d) v2.1 — la procédure d'incertitude, écrite ICI depuis le texte, et non importée du
# noyau de `c3_common` : c'est ce que fait un producteur conforme, et le rejeu de la chaîne doit la
# retrouver bit à bit. Une divergence entre ce texte-ci et le noyau est un défaut de l'un ou de l'autre.
# ---------------------------------------------------------------------------

#: § F.2 (b) : les longueurs de bloc, en tête `L = 21` ; § F.2 (h) : les deux appariements.
F2_BLOCK_LENGTHS: tuple[int, ...] = (10, 21, 42)
F2_MATCHINGS: tuple[str, ...] = ("dd", "sigma")


def environment() -> dict[str, str]:
    """§ F.2 (b) v2.1 et § I.2 I-C : l'environnement du tirage — Python, numpy, architecture et bibliothèque
    C (bibliothèque et version, séparées par une espace) ; jamais la chaîne noyau."""
    lib, version = platform.libc_ver()
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "machine": platform.machine(),
        "libc": f"{lib} {version}".strip(),
    }


def _f2_cagr_rows(log_returns: Any, idx: Any, days: float) -> Any:
    """§ F.2 (c) v2.1 : `(exp(Σ log1p(r) × 365 / n_jours) − 1) × 100` par `numpy` — `log1p` élément par
    élément, somme par ligne, `exp` ; un débordement rend la réplication non finie (§ F.2 e)."""
    with np.errstate(over="ignore", invalid="ignore"):
        return (np.exp(log_returns[idx].sum(axis=1) * (365 / days)) - 1.0) * 100.0


@cache
def _f2_cached(
    cfg: tuple[float, ...],
    bench_dd: tuple[float, ...],
    bench_sigma: tuple[float, ...],
    seed: int,
    pair_index: int,
    days: float,
    b: int,
) -> dict[str, Any]:
    n = len(cfg)
    log_cfg = np.log1p(np.asarray(cfg, dtype=float))
    log_bench = {
        "dd": np.log1p(np.asarray(bench_dd, dtype=float)),
        "sigma": np.log1p(np.asarray(bench_sigma, dtype=float)),
    }
    # § F.2 (c) v2.1 : le même chemin, appliqué aux indices identité, donne les valeurs observées.
    identity = np.arange(n)[None, :]
    cagr_config = float(_f2_cagr_rows(log_cfg, identity, days)[0])
    delta_hat = {
        m: cagr_config - float(_f2_cagr_rows(log_bench[m], identity, days)[0]) for m in F2_MATCHINGS
    }
    replications: dict[str, dict[str, Any]] = {}
    for length in F2_BLOCK_LENGTHS:
        # § F.2 (b) v2.1 : un tirage par `L`, en un seul appel ; les mêmes indices pour la configuration,
        # le comparateur, et les deux appariements.
        rng = np.random.default_rng([seed, pair_index, length])
        starts = rng.integers(0, n, size=(b, math.ceil(n / length)))
        idx = (starts[:, :, None] + np.arange(length)).reshape(b, -1)[:, :n] % n
        rows_config = _f2_cagr_rows(log_cfg, idx, days)
        for matching in F2_MATCHINGS:
            with np.errstate(invalid="ignore"):
                delta = rows_config - _f2_cagr_rows(log_bench[matching], idx, days)
            finite = np.isfinite(delta)
            kept = delta[finite]
            centre = delta_hat[matching]
            # § F.2 (d) : LB = Δ̂ − quantile_0,95(Δ* − Δ̂), `numpy.quantile(..., method="linear")` ;
            # § F.2 (e) v2.1 : une combinaison sans réplication retenue ne porte pas de borne.
            bound = (
                None
                if kept.size == 0
                else centre - float(np.quantile(kept - centre, 0.95, method="linear"))
            )
            replications[f"{length}:{matching}"] = {
                "delta_stars": [float(x) for x in kept],
                "discarded": int((~finite).sum()),
                "bound": bound,
            }
    return {"cagr_config": cagr_config, "delta_hat": delta_hat, "replications": replications}


def f2_procedure(
    returns_config: Sequence[float],
    returns_bench: Mapping[str, Sequence[float]],
    *,
    seed: int = SEED,
    pair_index: int = 0,
    days: float = EVAL_DAYS,
    b: int = cc.BOOTSTRAP_B,
) -> dict[str, Any]:
    """La procédure § F.2 v2.1 d'un producteur conforme, mémoïsée par séries ; renvoie une copie profonde
    (les tests mutent leurs artefacts) : `cagr_config`, `delta_hat` par appariement, `replications`."""
    cached = _f2_cached(
        tuple(float(x) for x in returns_config),
        tuple(float(x) for x in returns_bench["dd"]),
        tuple(float(x) for x in returns_bench["sigma"]),
        seed,
        pair_index,
        days,
        b,
    )
    return copy.deepcopy(cached)


def bench_by_matching(returns_bench: Any) -> dict[str, list[float]]:
    """Une série de comparateur (les deux appariements) ou déjà une table `{dd, sigma}`."""
    if isinstance(returns_bench, Mapping):
        return {m: [float(x) for x in returns_bench[m]] for m in F2_MATCHINGS}
    return {m: [float(x) for x in returns_bench] for m in F2_MATCHINGS}


def witness_returns(n: int = N_EVAL_POINTS - 1) -> list[float]:
    """Le témoin d'évaluation : dérive positive à faible bruit, N(0,0005 ; 0,002), graine 11. Contre du cash,
    mesuré par la procédure ci-dessus : CAGR ≈ 22,3 %/an et six bornes ≈ 14,6 à 17,2 points de %/an."""
    return list(np.random.default_rng(11).normal(0.0005, 0.002, n))


def varying_returns(seed: int, n: int = N_EVAL_POINTS - 1) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(rng.normal(0.0005, 0.02, n))


def evaluation(
    manifest_payload: dict[str, Any],
    *,
    candidate_index: int = 0,
    synthetic: bool = True,
    lots: bool = True,
    liquidation: bool = True,
    single_call: bool = True,
    sufficient: bool = True,
    first_fill_at: datetime | None = ANCHOR + timedelta(minutes=EXEC_INTERVAL * 2),
    flat_start_proof: dict[str, Any] | None = None,
    returns_config: list[float] | None = None,
    returns_bench: Any = None,
    net_pnl: float = 42.0,
    metrics: dict[str, Any] | None = None,
    bounds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Un artefact d'évaluation **synthétique** de la configuration retenue, sur [T, fin] : le contrat lu par
    c3_verdict (§ F.2, § F.8) et les blocs que c3_continuity vérifie (§ B). Suites, bornes, `cagr_pct` et
    `delta_dd` sont ceux de la procédure § F.2 v2.1 (graine du manifeste, index de la paire parmi les paires
    triées de l'univers) ; seul `net_pnl` (Q1) est déclaré. Défaut : le témoin contre du cash."""
    cand = manifest_payload["universe"]["candidates"][candidate_index]
    pair = cand["pair"]
    pairs = sorted({c["pair"] for c in manifest_payload["universe"]["candidates"]})
    values = nav_path(pair, candidate_index + 7, N_EVAL_POINTS, drift=0.0006)
    config = returns_config if returns_config is not None else witness_returns()
    bench = bench_by_matching(
        returns_bench if returns_bench is not None else [0.0] * (N_EVAL_POINTS - 1)
    )
    procedure = f2_procedure(
        config,
        bench,
        seed=manifest_payload["uncertainty"]["seed"],
        pair_index=pairs.index(pair),
        days=EVAL_DAYS,
    )
    replicated = procedure["replications"]
    for combination, bound in (bounds or {}).items():
        replicated[combination]["bound"] = bound
    reference = f"{values[-1] * 33.5:.8f}"
    liq = (
        liquidation_segment(
            pair,
            reference_price=reference,
            positions=2,
            lots=lots,
            timestamp=WINDOW_END - timedelta(minutes=EXEC_INTERVAL),
        )
        if liquidation
        else None
    )
    out: dict[str, Any] = {
        "synthetic": synthetic,
        "strategy": cand["strategy"],
        "pair": pair,
        "params": cand["params"],
        "period": {"start": ANCHOR.isoformat(), "end": WINDOW_END.isoformat()},
        "equity_daily": {
            "start": ANCHOR.isoformat(),
            "end": WINDOW_END.isoformat(),
            "values": values,
        },
        "liquidation": liq,
        "warmup": warmup_segment(sufficient=sufficient),
        "invocation": {"single_call": single_call},
        "first_fill_at": None if first_fill_at is None else first_fill_at.isoformat(),
        "flat_start_proof": flat_start_proof,
        "returns_config": list(config),
        "returns_bench": bench,
        "environment": environment(),
        "B": cc.BOOTSTRAP_B,
        "replications": replicated,
        "metrics": metrics
        if metrics is not None
        else {
            "net_pnl": net_pnl,
            "cagr_pct": procedure["cagr_config"],
            "delta_dd": procedure["delta_hat"]["dd"],
        },
    }
    return out


def benchmark_eval(
    pair: str = "BTC/USDC",
    *,
    comparable: bool = True,
    contradict: bool = False,
    window: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Le bloc de comparabilité du comparateur d'évaluation (§ C.5), synthétique ; ``window``
    remplace la fenêtre [T, fin] déclarée (revue Fin, défaut 3)."""
    tests = {
        "entry_stamp_present": True,
        "exit_stamp_present": True,
        "ff_ok": comparable,
        "n_returns_ok": True,
        "all_finite": True,
    }
    declared = comparable if not contradict else (not comparable)
    return {
        "pair": pair,
        "window": window
        if window is not None
        else {"start": ANCHOR.isoformat(), "end": WINDOW_END.isoformat()},
        "comparable": declared,
        "comparability": tests,
    }
