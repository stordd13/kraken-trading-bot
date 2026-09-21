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


def test_la_liste_blanche_des_champs_optionnels_est_close_et_nommee() -> None:
    assert cc.OPTIONAL_FIELDS == frozenset({"estimability"})


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
    for name in ("ANNUALISATION_DAYS", "MATCHINGS", "RETURN_DOMAIN_FLOOR"):
        assert name not in cc.THRESHOLDS
        assert hasattr(cc, name)


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
