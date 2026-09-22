"""C3 — constantes gelées, vocabulaire, et noyau numérique pur.

Ce module est la **source unique** des nombres que `docs/protocole_c3.md` fige : chaque autre
`scripts/audit/c3_*.py` les importe d'ici plutôt que de les redire, pour qu'un seuil ne puisse pas
diverger entre deux scripts. Il porte aussi les listes closes de raisons et de statuts, et le
noyau numérique pur de la procédure d'incertitude (§ F.2).

Deux règles du protocole sont **encodées, pas seulement documentées** :

* **§ 0.5 — tout nombre décisionnel porte sa classe.** Chaque constante de seuil est enregistrée
  dans ``THRESHOLDS`` avec sa valeur, sa classe et sa section d'origine. ``tests/`` asserte qu'aucun
  seuil n'existe hors de ce registre.
* **§ 0.5 / antériorité — aucun seuil du rejeu n'est hérité par transitivité.** Les helpers
  *génériques* de ``rejeu_common`` sont réutilisés (canonicalisation, entrées-sorties, arithmétique) ;
  **aucune** de ses constantes de périmètre ou de seuil ne l'est. ``FORBIDDEN_REJEU_NAMES`` liste les
  noms que les tests interdisent dans les sources ``c3_*``.

Pure, read-only. Aucun accès base de données, aucun effet de bord à l'import.

Exit codes des scripts qui l'importent : 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
import statistics
import sys
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import rejeu_common as rc  # noqa: E402

from krakenbot.backtest_metrics import daily_grid, max_drawdown_pct  # noqa: E402

__all_reexports__ = (daily_grid, max_drawdown_pct)

# Réexports génériques — canonicalisation et entrées-sorties. Le contrat de `canon` / `sig` est
# adopté explicitement par le § A.1 bis du protocole, pas hérité en silence.
canon = rc.canon
canon_tolerant = rc.canon_tolerant
dumps_canonical = rc.dumps_canonical
sig = rc.sig
first_difference = rc.first_difference
dec = rc.dec
daily_returns = rc.daily_returns
nnz = rc.nnz
write_json = rc.write_json
read_json = rc.read_json
NonFiniteValueError = rc.NonFiniteValueError

PROJECT_ROOT = _ROOT
PROTOCOL_RELPATH = "docs/protocole_c3.md"

# ---------------------------------------------------------------------------
# § 0.5 — registre des seuils : valeur, classe, section d'origine
# ---------------------------------------------------------------------------

CLASS_MATH = "contrainte mathématique"
CLASS_DATA = "qualité des données"
CLASS_ECON = "préférence économique"
CLASS_CONTRACT = "contrat"
CLASS_METHOD = "préférence méthodologique déclarée"
CLASS_GUARD = "garde-fou méthodologique"

THRESHOLDS: dict[str, tuple[Any, str, str]] = {}


def _t(name: str, value: Any, klass: str, section: str) -> Any:
    """Enregistre un seuil avec sa classe (§ 0.5) et le renvoie."""
    if name in THRESHOLDS:
        raise ValueError(f"seuil déclaré deux fois : {name}")
    THRESHOLDS[name] = (value, klass, section)
    return value


# § A.3 — ancrage
ANCHOR_FRACTION = _t("ANCHOR_FRACTION", 0.70, CLASS_ECON, "§ A.3")

# § 0.5 — nombres décisionnels transverses
CAPITAL = _t("CAPITAL", Decimal("1000"), CLASS_CONTRACT, "§ 0.5")
RISK_FREE = _t("RISK_FREE", Decimal("0"), CLASS_ECON, "§ 0.5")
LAMBDA_RESIDUAL_MAX = _t("LAMBDA_RESIDUAL_MAX", 0.10, CLASS_DATA, "§ 0.5")

# § A.8 D1 — couverture du préfixe
COVERAGE_MIN_RATIO = _t("COVERAGE_MIN_RATIO", 0.97, CLASS_DATA, "§ A.8 D1")
MAX_GAP_DAYS_ABS = _t("MAX_GAP_DAYS_ABS", 31, CLASS_DATA, "§ A.8 D1")
MAX_GAP_RATIO = _t("MAX_GAP_RATIO", 0.03, CLASS_DATA, "§ A.8 D1")
DAY_5M_EXPECTED = _t("DAY_5M_EXPECTED", 288, CLASS_CONTRACT, "§ A.8 D1")
DAY_5M_MIN_CANDLES = _t("DAY_5M_MIN_CANDLES", 144, CLASS_DATA, "§ A.8 D1")

# § A.8 D3 — couverture en cycles achevés
CYCLES_MIN = _t("CYCLES_MIN", 25, CLASS_ECON, "§ A.8 D3")

# § A.10 — plancher de sélection (P1, P2, P3) ; § F.8 les réévalue (Q1, Q2, Q3)
FLOOR_NET_PNL = _t("FLOOR_NET_PNL", 0.0, CLASS_ECON, "§ A.10 P1")
FLOOR_CAGR_PCT = _t("FLOOR_CAGR_PCT", 2.0, CLASS_ECON, "§ A.10 P2")
FLOOR_DELTA_DD = _t("FLOOR_DELTA_DD", 0.0, CLASS_ECON, "§ A.10 P3")

# § A.13 — estimabilité post-ancrage
E1_NONZERO_RATIO = _t("E1_NONZERO_RATIO", 0.10, CLASS_DATA, "§ A.13 E1")
E2_MIN_DISTINCT = _t("E2_MIN_DISTINCT", 2, CLASS_GUARD, "§ A.13 E2")

# § F.2 — procédure d'incertitude
BLOCK_LENGTHS = _t("BLOCK_LENGTHS", (10, 21, 42), CLASS_DATA, "§ F.2 (b)")
BLOCK_LENGTH_HEADLINE = _t("BLOCK_LENGTH_HEADLINE", 21, CLASS_DATA, "§ F.2 (b)")
BOOTSTRAP_B = _t("BOOTSTRAP_B", 10_000, CLASS_DATA, "§ F.2 (b)")
BOUND_LEVEL = _t("BOUND_LEVEL", 0.95, CLASS_METHOD, "§ F.2 (d)")
LAMBDA_COARSE_STEP = _t("LAMBDA_COARSE_STEP", Decimal("0.005"), CLASS_DATA, "§ F.2 (g)")
LAMBDA_FINE_STEP = _t("LAMBDA_FINE_STEP", Decimal("0.001"), CLASS_DATA, "§ F.2 (g)")
LAMBDA_REFINE_HALFWIDTH = _t("LAMBDA_REFINE_HALFWIDTH", Decimal("0.005"), CLASS_DATA, "§ F.2 (g)")
DISCARDED_MAX = _t("DISCARDED_MAX", 10, CLASS_DATA, "§ F.2 (e)")

# Conventions non décisionnelles (pas des seuils) — ni classées, ni au registre.
ANNUALISATION_DAYS = 365
MATCHINGS: tuple[str, ...] = ("dd", "sigma")
RETURN_DOMAIN_FLOOR = -1.0  # log1p n'existe pas en deçà ; § A.8 D4, contrainte mathématique pure

# Noms du rejeu qu'aucune source `c3_*` ne doit importer (§ 0.5, antériorité).
FORBIDDEN_REJEU_NAMES: tuple[str, ...] = (
    "WINDOW_START",
    "WINDOW_END",
    "WINDOW_DAYS",
    "TRAIN_RATIO",
    "SEGMENT_POINTS",
    "SEGMENT_RETURNS",
    "SEGMENTS",
    "CYCLES_MIN",
    "NNZ_MIN",
    "COVERAGE_MIN_DAYS",
    "MAX_GAP_DAYS",
    "DAY_5M_COMPLETE_MIN",
    "FIRST_COVERED_DAY_MAX",
    "LAST_COVERED_DAY_MIN",
    "G2_MIN_RETURN_PCT",
    "G3_FEE_MULTIPLE",
    "MIN_RETURN_DOMAIN",
    "FF_DAYS_MAX",
    "N_CONFIGS_PER_PAIR",
    "N_CONFIGS_TOTAL",
    "BASE_SHA",
    "REASON_PRIORITY",
    "SEED_BASE",
    "DEGENERATE_MAX",
    "ALPHA",
    "CLASS_DEFAULTS",
    "STRATEGY",
    "PAIRS",
)

# ---------------------------------------------------------------------------
# Accesseur strict — un contrôle de présence qui ne passe pas sur une absence
# ---------------------------------------------------------------------------
#
# Quatre fois dans ce projet, un contrôle de présence a laissé passer une absence au lieu de la
# signaler. `skills/backtest.md` § « Contrôles de présence » en fait une doctrine ; ce bloc en est
# la forme exécutable, **écrite une fois et utilisée par tous les modules `c3_*`**, précisément pour
# qu'aucun d'eux ne réécrive à la main une logique de présence qui oublierait `None`, un type faux
# ou un non-fini.
#
# Règle : une preuve obligatoire **absente**, **nulle**, **mal typée** ou **hors liste close** est une
# **erreur d'entrée** (§ I.1 ligne 2, code 2, rien n'est écrit) ; une preuve **non finie** ou **hors
# domaine** est une **violation** (§ I.1 ligne 15, code 1, artefact diagnostic invalide — § F.7,
# § F.2 e). Ce n'est jamais un `False` implicite, et jamais une valeur par défaut.


class MissingEvidenceError(ValueError):
    """Preuve obligatoire **absente, nulle, mal typée ou hors liste close** — erreur d'entrée.

    Code 2 (§ I.1, ligne 2) : la chaîne s'arrête, rien n'est publié. Une valeur **non finie** ou
    **hors domaine** n'est pas de cette classe : c'est un échec de validité, voir ``InvalidValueError``.
    """


class InvalidValueError(ValueError):
    """Valeur **non finie** (`NaN`, `±inf`) ou **hors domaine** (rendement `<= -1`) dans une preuve.

    § F.7 la renvoie à la **ligne 15 du § I.1 : code 1, violation**, pas un résultat. Elle n'est
    volontairement **pas** une sous-classe de ``MissingEvidenceError`` : la CLI doit distinguer une
    donnée absente (2, rien d'écrit) d'un échec de validité documenté (1, artefact diagnostic).
    """


class UndefinedIssueError(ValueError):
    """Convention d'outillage datée du 21/09 (plan § 6.1) : l'issue n'est **pas définie par le texte
    gelé** — clause 3 de continuité en échec sur l'artefact d'évaluation. § B.3 et § G.2 interdisent
    tout verdict directionnel ; § I.1 ne porte aucune ligne de portée run pour ce cas ; l'amendement
    daté (a) est dû à l'ouverture de C3b. Conduite (b) : refus de produire une issue, code 2, rien
    publié — une assignation de code hors table, assumée comme telle et consignée — **pour le cas
    cohérent seulement** : une contradiction déclaré / dérivé constatée avant prime (§ I.1 l.15) et
    l'issue non définie est consignée au diagnostic, code 1 (revue Fin 2, item 2 ; `c3_verdict`).
    """


class EntryRefusedError(MissingEvidenceError):
    """Refus d'entrée porteur d'une **raison** de la liste close (§ I.1, lignes 2 et 5) — code 2."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason


#: Champs externes **réellement optionnels** (absents **ou** nuls → ``None``) — la seule liste blanche
#: que le scan de source accepte pour un ``.get(...)`` ou un ``optional_*(...)`` dans ``c3_*.py``.
#: Tout autre champ est obligatoire et passe par ``require_*``. Chaque entrée dit pourquoi :
#: ``estimability`` (déclaration recoupée, § A.13) ; ``liquidation`` et ``dca_counters`` (le runner
#: exporte ``null`` pour le moteur signal et hors DCA, `run_p7_grid_search.py:768-772` — D6 tranche,
#: § A.8) ; ``lots`` (sous-clé de ``liquidation``, exigence C3b, preuve par lot de D6) ;
#: ``flat_start_proof`` et ``first_fill_at`` (§ B.2 et § B.6, non vérifiables sous les artefacts
#: actuels) ; ``decision_timeframes`` (surcharge par candidat de la déclaration par stratégie) ;
#: ``exec_interval`` (porteur de l'intervalle d'exécution dans une observation — absent de l'export
#: réel, D5 le consigne ``not_assertable``) ; ``run_scope`` (note de portée d'un manifeste réel).
OPTIONAL_FIELDS: frozenset[str] = frozenset(
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
    }
)

#: Champs **présents mais nullables** (la clé doit exister ; ``null`` est une valeur documentée) — la
#: seule liste que le scan accepte pour un ``nullable_*(...)``. Origine de chaque ``null`` :
#: ``stale_by_candles``, ``first``, ``last`` — rien chargé (`backtest.py:508-528`) ; ``timestamp``,
#: ``reference_price``, ``price``, ``spread_pct``, ``slippage_pct``, ``avg_holding_minutes`` — aucune
#: liquidation forcée (`backtest.py:3296-3300`) ; ``entry_price``, ``pnl`` — lot à coût inconnu ;
#: ``refusal`` — `entry.json` : ``null`` quand l'entrée est conforme, un bloc quand elle est refusée ;
#: ``retained`` — `selection.json` : ``null`` en abstention, un bloc quand une configuration est retenue ;
#: ``reason`` — `benchmark.pairs[].reason` et `selection.reason` : ``null`` quand rien n'est à signaler ;
#: ``liquidation_normalised`` — `continuity.json` : ``true`` prouvé par lot, ``false`` en échec, ``null`` non vérifiable.
NULLABLE_FIELDS: frozenset[str] = frozenset(
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
    }
)


def _require(obj: Any, key: str, *, where: str) -> Any:
    if not isinstance(obj, Mapping):
        raise MissingEvidenceError(f"{where}: bloc attendu, reçu {type(obj).__name__}")
    if key not in obj:
        raise MissingEvidenceError(f"{where}.{key}: clé absente")
    value = obj[key]
    if value is None:
        raise MissingEvidenceError(f"{where}.{key}: valeur nulle")
    return value


def require_mapping(obj: Any, key: str, *, where: str) -> Mapping[str, Any]:
    value = _require(obj, key, where=where)
    if not isinstance(value, Mapping):
        raise MissingEvidenceError(f"{where}.{key}: bloc attendu, reçu {type(value).__name__}")
    return value


def require_bool(obj: Any, key: str, *, where: str) -> bool:
    """Un booléen, et **pas** un entier : `1` n'est pas une preuve satisfaite."""
    value = _require(obj, key, where=where)
    if not isinstance(value, bool):
        raise MissingEvidenceError(f"{where}.{key}: booléen attendu, reçu {type(value).__name__}")
    return value


def require_float(obj: Any, key: str, *, where: str) -> float:
    """Un nombre **fini**. Un `NaN` ou un infini lève, il ne participe à aucune comparaison.

    Sans cette garde, un `NaN` rendrait **fausse** toute comparaison qui le lit, donc produirait
    silencieusement un verdict négatif ; et `+inf` franchirait n'importe quel plancher.
    """
    value = _require(obj, key, where=where)
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise MissingEvidenceError(f"{where}.{key}: nombre attendu, reçu {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidValueError(f"{where}.{key}: valeur non finie ({value!r})")
    return number


def require_int(obj: Any, key: str, *, where: str, minimum: int | None = None) -> int:
    """Un entier **obligatoire** — aucun défaut possible : un compteur absent n'est pas zéro."""
    value = _require(obj, key, where=where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MissingEvidenceError(f"{where}.{key}: entier attendu, reçu {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise InvalidValueError(f"{where}.{key}: {value} < minimum {minimum}")
    return int(value)


def require_str(obj: Any, key: str, *, where: str, allowed: Sequence[str] | None = None) -> str:
    value = _require(obj, key, where=where)
    if not isinstance(value, str):
        raise MissingEvidenceError(f"{where}.{key}: chaîne attendue, reçu {type(value).__name__}")
    if allowed is not None and value not in allowed:
        raise MissingEvidenceError(f"{where}.{key}: {value!r} hors liste close {sorted(allowed)}")
    return value


def require_decimal(obj: Any, key: str, *, where: str) -> Decimal:
    """Un montant exporté en **chaîne Decimal** (`_dec = str(Decimal)`, `backtest.py:3689`), fini.

    Un ``int`` est accepté (JSON ne distingue pas ``1000`` de ``"1000"`` dans un manifeste) ; un
    ``float`` aussi, converti par ``str`` comme le fait le projet ; un booléen jamais.
    """
    value = _require(obj, key, where=where)
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise MissingEvidenceError(f"{where}.{key}: Decimal attendu, reçu {type(value).__name__}")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise MissingEvidenceError(f"{where}.{key}: {value!r} n'est pas un Decimal") from exc
    if not number.is_finite():
        raise InvalidValueError(f"{where}.{key}: valeur non finie ({value!r})")
    return number


def require_sequence(obj: Any, key: str, *, where: str, min_len: int = 0) -> Sequence[Any]:
    """Une liste JSON (jamais une chaîne, jamais un bloc), d'au moins ``min_len`` éléments."""
    value = _require(obj, key, where=where)
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise MissingEvidenceError(f"{where}.{key}: suite attendue, reçu {type(value).__name__}")
    if len(value) < min_len:
        raise MissingEvidenceError(f"{where}.{key}: {len(value)} éléments, minimum {min_len}")
    return value


def parse_datetime(value: Any, *, where: str) -> datetime:
    """Un instant ISO 8601 **avec fuseau** (UTC pour tous les timestamps du projet), rendu en UTC."""
    if not isinstance(value, str):
        raise MissingEvidenceError(f"{where}: instant ISO attendu, reçu {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MissingEvidenceError(f"{where}: {value!r} n'est pas un instant ISO") from exc
    if parsed.tzinfo is None:
        raise MissingEvidenceError(f"{where}: {value!r} sans fuseau horaire")
    return parsed.astimezone(UTC)


def require_datetime(obj: Any, key: str, *, where: str) -> datetime:
    return parse_datetime(_require(obj, key, where=where), where=f"{where}.{key}")


def _optional(obj: Any, key: str, *, where: str, must_exist: bool) -> Any:
    """Le seul point de lecture d'un champ optionnel ou nullable — jamais un ``.get`` ailleurs."""
    if not isinstance(obj, Mapping):
        raise MissingEvidenceError(f"{where}: bloc attendu, reçu {type(obj).__name__}")
    if key not in obj:
        if must_exist:
            raise MissingEvidenceError(f"{where}.{key}: clé absente (nullable, jamais absente)")
        return None
    return obj[key]


def optional_mapping(obj: Any, key: str, *, where: str) -> Mapping[str, Any] | None:
    """Bloc **optionnel** (``OPTIONAL_FIELDS``) : absent ou ``null`` → ``None`` ; mal typé → erreur."""
    value = _optional(obj, key, where=where, must_exist=False)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise MissingEvidenceError(f"{where}.{key}: bloc attendu, reçu {type(value).__name__}")
    return value


def optional_sequence(obj: Any, key: str, *, where: str) -> Sequence[Any] | None:
    value = _optional(obj, key, where=where, must_exist=False)
    if value is None:
        return None
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise MissingEvidenceError(f"{where}.{key}: suite attendue, reçu {type(value).__name__}")
    return value


def optional_int(obj: Any, key: str, *, where: str) -> int | None:
    value = _optional(obj, key, where=where, must_exist=False)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MissingEvidenceError(f"{where}.{key}: entier attendu, reçu {type(value).__name__}")
    return int(value)


def optional_str(obj: Any, key: str, *, where: str) -> str | None:
    value = _optional(obj, key, where=where, must_exist=False)
    if value is None:
        return None
    if not isinstance(value, str):
        raise MissingEvidenceError(f"{where}.{key}: chaîne attendue, reçu {type(value).__name__}")
    return value


def nullable_int(obj: Any, key: str, *, where: str, minimum: int | None = None) -> int | None:
    """Entier **nullable** (``NULLABLE_FIELDS``) : la clé doit exister, ``null`` est une valeur."""
    value = _optional(obj, key, where=where, must_exist=True)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MissingEvidenceError(f"{where}.{key}: entier attendu, reçu {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise InvalidValueError(f"{where}.{key}: {value} < minimum {minimum}")
    return int(value)


def nullable_float(obj: Any, key: str, *, where: str) -> float | None:
    value = _optional(obj, key, where=where, must_exist=True)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise MissingEvidenceError(f"{where}.{key}: nombre attendu, reçu {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidValueError(f"{where}.{key}: valeur non finie ({value!r})")
    return number


def nullable_decimal(obj: Any, key: str, *, where: str) -> Decimal | None:
    value = _optional(obj, key, where=where, must_exist=True)
    if value is None:
        return None
    return require_decimal(obj, key, where=where)


def nullable_str(obj: Any, key: str, *, where: str) -> str | None:
    value = _optional(obj, key, where=where, must_exist=True)
    if value is None:
        return None
    if not isinstance(value, str):
        raise MissingEvidenceError(f"{where}.{key}: chaîne attendue, reçu {type(value).__name__}")
    return value


def nullable_mapping(obj: Any, key: str, *, where: str) -> Mapping[str, Any] | None:
    value = _optional(obj, key, where=where, must_exist=True)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise MissingEvidenceError(f"{where}.{key}: bloc attendu, reçu {type(value).__name__}")
    return value


def nullable_bool(obj: Any, key: str, *, where: str) -> bool | None:
    value = _optional(obj, key, where=where, must_exist=True)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise MissingEvidenceError(f"{where}.{key}: booléen attendu, reçu {type(value).__name__}")
    return value


def nullable_datetime(obj: Any, key: str, *, where: str) -> datetime | None:
    value = _optional(obj, key, where=where, must_exist=True)
    if value is None:
        return None
    return parse_datetime(value, where=f"{where}.{key}")


def require_finite_series(
    obj: Any,
    key: str,
    *,
    where: str,
    min_len: int = 1,
    domain_floor: float | None = None,
) -> list[float]:
    """Une suite de nombres **tous finis**, chaque élément passant la même garde.

    ``min_len=0`` autorise une suite **vide documentée** (toutes les réplications écartées, § F.2 e) ;
    l'absence de la clé reste une erreur d'entrée. ``domain_floor`` ajoute la garde de domaine du
    § A.8 D4 — un rendement `<= -1` rend `log1p` indéfini — **en plus** de la finitude, jamais à sa place.
    """
    value = _require(obj, key, where=where)
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise MissingEvidenceError(f"{where}.{key}: suite attendue, reçu {type(value).__name__}")
    if len(value) < min_len:
        raise MissingEvidenceError(f"{where}.{key}: {len(value)} éléments, minimum {min_len}")
    out: list[float] = []
    for i, item in enumerate(value):
        if item is None or isinstance(item, bool) or not isinstance(item, (int, float, Decimal)):
            raise MissingEvidenceError(f"{where}.{key}[{i}]: nombre attendu, reçu {item!r}")
        number = float(item)
        if not math.isfinite(number):
            raise InvalidValueError(f"{where}.{key}[{i}]: valeur non finie ({item!r})")
        if domain_floor is not None and number <= domain_floor:
            raise InvalidValueError(
                f"{where}.{key}[{i}]: {number} hors domaine (doit être > {domain_floor})"
            )
        out.append(number)
    return out


# ---------------------------------------------------------------------------
# § H — issues, et § I.1 — raisons en ordre de priorité (liste close)
# ---------------------------------------------------------------------------

ISSUE_VALIDE = "validé"
ISSUE_REFUTE = "réfuté"
ISSUE_INCONCLUSIF = "inconclusif"
ISSUE_DESCRIPTIF = "descriptif"
ISSUES: tuple[str, ...] = (ISSUE_VALIDE, ISSUE_REFUTE, ISSUE_INCONCLUSIF, ISSUE_DESCRIPTIF)

#: Ordre de priorité du § H. La chaîne porte **la première raison qui s'applique**.
REASON_PRIORITY: tuple[str, ...] = (
    "R0_INVALID_RUN",
    "P_PROVENANCE",
    "D_WARMUP_PREFIX",
    "A_NO_ADMISSIBLE_CANDIDATE",
    "A_BELOW_FLOOR",
    "D_WARMUP_ANCHOR",
    "E_NO_BENCHMARK",
    "E_STAMP_MISMATCH",
    "F_NOT_ESTIMABLE",
    "F_CANNOT_SEPARATE",
    "R1_NOT_NORMALISED",
    "D_NOT_ADMISSIBLE",
    "C_COVERAGE",
)

#: Raisons **pouvant concerner un candidat** (§ I.1, lignes 3 à 6). C'est une énumération, **pas une
#: table raison → portée** : la portée se lit dans la ligne du § I.1 qui s'applique, et une même
#: raison en a plusieurs — `D_WARMUP_PREFIX` est de portée candidat (ligne 4) **ou** artefact
#: (ligne 5), `F_NOT_ESTIMABLE` de portée candidat (ligne 6, D4) **ou** run (ligne 13). Un dict
#: raison → portée unique était faux par construction ; il a été retiré.
CANDIDATE_REASONS: tuple[str, ...] = (
    "D_WARMUP_PREFIX",
    "R1_NOT_NORMALISED",
    "D_NOT_ADMISSIBLE",
    "C_COVERAGE",
    "F_NOT_ESTIMABLE",
)

#: § I.1 — liste close des clauses promouvables en refus d'artefact. **D2 seule.**
PROMOTABLE_CLAUSES: tuple[str, ...] = ("D2",)

#: Clause → raison (§ A.8, § I.1).
CLAUSE_REASON: dict[str, str] = {
    "D1": "D_NOT_ADMISSIBLE",
    "D2": "D_WARMUP_PREFIX",
    "D3": "C_COVERAGE",
    "D4": "F_NOT_ESTIMABLE",
    "D5": "R0_INVALID_RUN",
    "D6": "R1_NOT_NORMALISED",
}
CLAUSE_ORDER: tuple[str, ...] = ("D1", "D2", "D3", "D4", "D5", "D6")

# Statuts (§ H) — trois vocabulaires clos, qui ne se confondent pas avec les raisons.
STATUS_CANDIDATE: tuple[str, ...] = (
    "ADMISSIBLE",
    "NOT_ESTIMABLE",
    "NON_ADMISSIBLE",
    "HORS_USAGE_DÉCISIONNEL",
)
STATUS_PAIR: tuple[str, ...] = ("VOTANTE", "DESCRIPTIF")
STATUS_SELECTION: tuple[str, ...] = (
    "SÉLECTION_VALIDE",
    "SÉLECTION_DESCRIPTIVE",
    "ABSTENTION",
)

PROVENANCE_CLEAN = "clean"
PROVENANCE_CONTAMINATED = "contaminated"
PROVENANCE_UNKNOWN = "unknown"
PROVENANCES: tuple[str, ...] = (PROVENANCE_CLEAN, PROVENANCE_CONTAMINATED, PROVENANCE_UNKNOWN)

#: § A.5 — `unknown` n'est jamais assimilé à `clean`.
PROVENANCE_CAN_SUPPORT_VALIDE: dict[str, bool] = {
    PROVENANCE_CLEAN: True,
    PROVENANCE_CONTAMINATED: False,
    PROVENANCE_UNKNOWN: False,
}

#: Phrase littérale de non-recevabilité (§ D.3), assertée par les tests.
NON_RECEVABLE_SENTENCE = "cet artefact ne satisfait pas les conditions d'entrée C3"


def worst_reason(*reasons: str | None) -> str | None:
    """La raison la plus prioritaire au sens du § H, ou None."""
    present = [r for r in reasons if r]
    if not present:
        return None
    unknown = [r for r in present if r not in REASON_PRIORITY]
    if unknown:
        raise ValueError(f"raison hors liste close : {sorted(unknown)}")
    return min(present, key=REASON_PRIORITY.index)


# ---------------------------------------------------------------------------
# § A.3 / § A.4 — ancrage et estampilles admissibles
# ---------------------------------------------------------------------------


def anchor_of(start: datetime, end: datetime, fraction: float = ANCHOR_FRACTION) -> datetime:
    """`début + F × (fin − début)`, **sans aucun arrondi** (§ A.3).

    Les bornes viennent du manifeste gelé, jamais de la dernière donnée disponible : c'est ce qui
    rend le test de chronologie du § A.12 exécutable.
    """
    if end <= start:
        raise ValueError("fin doit être strictement postérieure à début")
    return start + (end - start) * fraction


def last_stamp_at_or_before(instant: datetime, interval_minutes: int) -> datetime:
    """Dernière estampille `<= instant` de la série `interval_minutes` (§ A.4).

    Les bougies sont estampillées en **fin** de période, donc celle estampillée `t` est close à `t`
    et appartient au passé de `t`. Si `instant` coïncide avec une estampille, **c'est celle-là**.
    L'hebdomadaire est ancré au lundi.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes doit être strictement positif")
    if interval_minutes == 10_080:  # 1 w, ancrée au lundi 00:00 UTC
        midnight = instant.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = midnight - timedelta(days=midnight.weekday())
        return monday
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    step = interval_minutes * 60
    elapsed = int((instant - epoch).total_seconds())
    return epoch + timedelta(seconds=(elapsed // step) * step)


def first_stamp_strictly_after(instant: datetime, interval_minutes: int) -> datetime:
    """Première estampille **strictement postérieure** à `instant` (§ C.3).

    C'est l'estampille de la bougie dont la **clôture** sert de prix d'exécution au benchmark : son
    instant est strictement postérieur à `instant`, là où son *open* peut lui être antérieur.
    """
    last = last_stamp_at_or_before(instant, interval_minutes)
    if interval_minutes == 10_080:
        return last + timedelta(days=7)
    return last + timedelta(minutes=interval_minutes)


def admissible_stamps(anchor: datetime, intervals: Sequence[int]) -> dict[int, str]:
    """Table du § A.4 : par timeframe, la dernière observation admissible à l'ancrage."""
    return {iv: last_stamp_at_or_before(anchor, iv).isoformat() for iv in intervals}


# ---------------------------------------------------------------------------
# § A.2 — identité canonique, et § A.9 — départage
# ---------------------------------------------------------------------------


def candidate_identity(strategy: str, pair: str, params: Any) -> str:
    """`sig(canon({strategy, pair, params}))` (§ A.2).

    Et **pas** un hachage des seuls paramètres : celui-ci ne suffit que dans un univers limité à une
    stratégie et une paire, ce qui n'est pas le cas général et ne doit pas être supposé.
    """
    return sig({"strategy": strategy, "pair": pair, "params": params})


def tie_break_key(delta_sigma: float, mdd_daily: float, identity: str) -> tuple[float, float, str]:
    """Chaîne de départage du § A.9, appliquée qu'il y ait égalité ou non.

    Ordre : `Δ^σ` plus grand, puis `max_drawdown_pct_daily` plus petit, puis identité canonique
    lexicographiquement la plus petite. Renvoie une clé de tri **croissante**.
    """
    return (-float(delta_sigma), float(mdd_daily), identity)


# ---------------------------------------------------------------------------
# § F.2 — noyau numérique pur de la procédure d'incertitude
# ---------------------------------------------------------------------------


class InvalidInputError(ValueError):
    """Entrée invalide au sens du § F.2 (e) : erreur d'entrée, aucun bootstrap n'est lancé."""


def check_returns(returns: Sequence[float], *, label: str) -> np.ndarray:
    """Valide une série de rendements **avant** tout tirage (§ F.2 e, entrées invalides)."""
    arr = np.asarray(list(returns), dtype=float)
    if arr.size == 0:
        raise InvalidInputError(f"{label}: série vide")
    if not np.all(np.isfinite(arr)):
        raise InvalidInputError(f"{label}: valeur non finie dans les entrées")
    if np.any(arr <= RETURN_DOMAIN_FLOOR):
        raise InvalidInputError(f"{label}: rendement <= -1, log1p indéfini")
    return arr


def cagr_pct(returns: Sequence[float], days: float) -> float:
    """Rendement géométrique annualisé en %/an, par somme de `log1p` (§ F.2 c)."""
    if days <= 0:
        raise InvalidInputError("days doit être strictement positif")
    total = math.fsum(math.log1p(r) for r in returns)
    return (math.exp(total * ANNUALISATION_DAYS / days) - 1.0) * 100.0


def block_start_indices(rng: np.random.Generator, n: int, block_length: int, b: int) -> np.ndarray:
    """Départs de blocs, tirés **une fois par `L`, avant tout découpage** (§ F.2 b)."""
    m = math.ceil(n / block_length)
    return rng.integers(0, n, size=(b, m))


def block_indices(starts: np.ndarray, block_length: int, n: int) -> np.ndarray:
    """Indices circulaires `(B, n)` — **appariés**, donc appliqués aux deux séries (§ F.2 a)."""
    idx = (starts[:, :, None] + np.arange(block_length)).reshape(starts.shape[0], -1)
    return idx[:, :n] % n


def paired_delta_stars(
    returns_config: Sequence[float],
    returns_bench: Sequence[float],
    idx: np.ndarray,
    days: float,
) -> tuple[np.ndarray, int]:
    """`Δ*` par réplication, indices **appariés**, plus le compte de réplications écartées.

    § F.2 (e) : une réplication qui produit un `Δ*` non fini est **écartée et comptée**, jamais
    remplacée — un retirage biaiserait la distribution vers les chemins qui se terminent bien.
    """
    cfg = np.asarray(list(returns_config), dtype=float)
    bch = np.asarray(list(returns_bench), dtype=float)
    if cfg.shape != bch.shape:
        raise InvalidInputError("les deux séries doivent avoir la même longueur (appariement)")
    log_cfg = np.log1p(cfg)
    log_bch = np.log1p(bch)
    scale = ANNUALISATION_DAYS / days
    cagr_cfg = (np.exp(log_cfg[idx].sum(axis=1) * scale) - 1.0) * 100.0
    cagr_bch = (np.exp(log_bch[idx].sum(axis=1) * scale) - 1.0) * 100.0
    delta = cagr_cfg - cagr_bch
    finite = np.isfinite(delta)
    return delta[finite], int((~finite).sum())


def pivotal_lower_bound(
    delta_hat: float, delta_stars: Sequence[float], level: float = BOUND_LEVEL
) -> float:
    """Borne inférieure **pivotale**, unilatérale (§ F.2 d).

    ``LB = Δ̂ − quantile_level(Δ* − Δ̂)``, convention de quantile ``method="linear"``. La forme
    pivotale corrige le déplacement de la distribution rééchantillonnée ; la forme percentile le
    reporte tel quel. Sous queues lourdes les deux diffèrent, et la différence peut changer le signe.
    """
    arr = np.asarray(list(delta_stars), dtype=float)
    if arr.size == 0:
        raise InvalidInputError("aucune réplication retenue")
    q = float(np.quantile(arr - float(delta_hat), level, method="linear"))
    return float(delta_hat) - q


@dataclass(frozen=True)
class Estimability:
    """Résultat du § A.13, avec le détail qui permet de le relire."""

    e1: bool
    e2: bool
    nonzero_ratio: float
    distinct_delta_stars: int
    discarded: int

    @property
    def ok(self) -> bool:
        return self.e1 and self.e2 and self.discarded <= DISCARDED_MAX

    def to_dict(self) -> dict[str, Any]:
        return {
            "E1": self.e1,
            "E2": self.e2,
            "nonzero_ratio": self.nonzero_ratio,
            "distinct_delta_stars": self.distinct_delta_stars,
            "discarded": self.discarded,
            "B_effectif": None,
            "ok": self.ok,
        }


def estimability(
    returns_config: Sequence[float], delta_stars: Sequence[float], discarded: int = 0
) -> Estimability:
    """§ A.13 — E1 et E2, plus le plafond de réplications écartées du § F.2 (e).

    **E1 ne porte que sur la trajectoire évaluée.** Le comparateur en est exempté : à `λ = 0` il est
    du cash déterministe, et l'exiger actif rendrait toute comparaison à `λ = 0` inconclusive.

    **E2 détecte une distribution de `Δ*` constante, quelle qu'en soit la cause** — deux trajectoires
    déterministes, ou deux trajectoires variables **identiques** sous rééchantillonnage apparié. Il
    n'exige pas que les deux côtés soient déterministes : ce serait confondre une condition
    suffisante avec une condition nécessaire.
    """
    cfg = np.asarray(list(returns_config), dtype=float)
    ratio = float(np.count_nonzero(cfg)) / float(cfg.size) if cfg.size else 0.0
    arr = np.asarray(list(delta_stars), dtype=float)
    distinct = int(np.unique(arr).size) if arr.size else 0
    return Estimability(
        e1=ratio >= E1_NONZERO_RATIO,
        e2=distinct >= E2_MIN_DISTINCT,
        nonzero_ratio=ratio,
        distinct_delta_stars=distinct,
        discarded=int(discarded),
    )


# ---------------------------------------------------------------------------
# Provenance du document et des artefacts
# ---------------------------------------------------------------------------


def protocol_descriptor(root: Path | None = None) -> dict[str, str]:
    """`{path, sha256}` du protocole gelé — épinglé dans chaque artefact et dans la chaîne."""
    base = Path(root) if root is not None else PROJECT_ROOT
    path = base / PROTOCOL_RELPATH
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": PROTOCOL_RELPATH, "sha256": digest}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_header(now: datetime, inputs: Mapping[str, Path] | None = None) -> dict[str, Any]:
    """En-tête commun : `generated_at`, `protocole`, `inputs_sha256`."""
    header: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "protocole": protocol_descriptor(),
    }
    if inputs:
        header["inputs_sha256"] = {k: file_sha256(v) for k, v in sorted(inputs.items())}
    return header


def envelope(
    step: str,
    now: datetime,
    inputs: Mapping[str, Path],
    *,
    exit_code: int,
    violations: Sequence[str] = (),
) -> dict[str, Any]:
    """L'enveloppe commune à tout artefact `c3_*` : en-tête, étape, `ok`, `exit_code`, `invalide`.

    `invalide` vaut **vrai si et seulement si** l'artefact est le diagnostic d'une violation
    (code 1) : il porte les violations et aucun résultat citable. Un refus (code 2) n'est pas
    « invalide », il est un refus — seul `c3_entry` en écrit un (§ I.1 l.1558 : rien n'est publié
    au-delà de la validation).
    """
    payload: dict[str, Any] = dict(artifact_header(now, inputs))
    payload.update(
        {
            "step": step,
            "ok": exit_code == 0,
            "exit_code": exit_code,
            "invalide": exit_code == 1,
            "violations": list(violations),
        }
    )
    return payload


def check_inputs_match(
    artifact: Mapping[str, Any], inputs: Mapping[str, Path], *, where: str
) -> list[str]:
    """Empreintes d'un artefact amont contre les fichiers réellement fournis — discordances.

    Elles **détectent une discordance** ; elles ne prouvent pas que l'invocation courante a réussi.
    """
    recorded = require_mapping(artifact, "inputs_sha256", where=where)
    out: list[str] = []
    for name, path in sorted(inputs.items()):
        stated = require_str(recorded, name, where=f"{where}.inputs_sha256")
        actual = file_sha256(path)
        if stated != actual:
            out.append(
                f"{where}.inputs_sha256.{name}: enregistré {stated[:16]}, fichier {actual[:16]}"
            )
    return out


def require_upstream_ok(artifact: Mapping[str, Any], *, where: str) -> None:
    """Un artefact amont n'est consommable que s'il enregistre lui-même son succès (code 0)."""
    ok = require_bool(artifact, "ok", where=where)
    invalide = require_bool(artifact, "invalide", where=where)
    code = require_int(artifact, "exit_code", where=where)
    if invalide or not ok or code != 0:
        raise EntryRefusedError(
            "R0_INVALID_RUN",
            f"{where}: artefact amont en échec (ok={ok}, invalide={invalide}, exit_code={code})",
        )


def parse_now(value: str | None) -> datetime:
    """`--now` injectable (§ L.4) : ISO UTC, ou l'instant courant. Lève `ValueError` si illisible."""
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Vocabulaires clos du manifeste et de la continuité
# ---------------------------------------------------------------------------

ENGINES: tuple[str, ...] = ("grid", "signal")
#: § C.4 — seul `prefix` est décisionnel ; `reestimated` est descriptif.
LAMBDA_MODES: tuple[str, ...] = ("prefix", "reestimated")
LAMBDA_MODE_DECISIONAL = "prefix"
#: § C.4 — étiquette obligatoire à côté de tout λ.
LAMBDA_LABEL = (
    "un appariement sur un risque réalisé est une comparaison rétrospective, "
    "jamais une allocation validée pour l'avenir"
)
#: § A.11 — clause verbatim, citée dans tout rapport qui s'abstient.
ABSTENTION_CLAUSE = (
    "Aucune clause n'est relâchée, aucun ancrage n'est déplacé, aucune fenêtre n'est élargie, "
    "aucun univers n'est étendu, aucun candidat n'est repêché. Un périmètre qui se révèle mal "
    "choisi est un résultat."
)
CONTINUITY_STATES: tuple[str, ...] = ("VERIFIED", "DECLARED", "NOT_VERIFIABLE", "FAILED")
#: Précédence de l'agrégat de continuité (plan § 6.4) : la pire clause donne l'état. **Une seule
#: définition**, consommée par le producteur (`c3_continuity`) et par le consommateur (`c3_verdict`,
#: qui la recalcule et la recoupe — revue Fin, défaut 2).
CONTINUITY_SEVERITY: tuple[str, ...] = ("FAILED", "NOT_VERIFIABLE", "DECLARED", "VERIFIED")
#: **Table § 6.4, colonne « États atteignables (C3a) », en liste close** (revue Fin 2, défaut 1) :
#: c1, c2, c5 sont déclaratives (jamais `VERIFIED`) ; c2 n'est jamais « non vérifiable » (le bloc
#: `invocation` est obligatoire) ; c3 n'est jamais « déclarée » (seule la preuve par lot la vérifie) ;
#: c4 est recalculée (`sufficient`), donc `VERIFIED` ou `FAILED`, jamais autre chose. Un état hors de
#: la liste de sa clause est une valeur hors liste close → code 2, rien publié — chez le producteur
#: (`c3_continuity`) comme chez le consommateur (`c3_verdict`). Conséquence : l'agrégat `VERIFIED`
#: est inconstructible en C3a.
CLAUSE_ADMISSIBLE_STATES: dict[str, tuple[str, ...]] = {
    "c1": ("NOT_VERIFIABLE", "DECLARED", "FAILED"),
    "c2": ("DECLARED", "FAILED"),
    "c3": ("VERIFIED", "NOT_VERIFIABLE", "FAILED"),
    "c4": ("VERIFIED", "FAILED"),
    "c5": ("NOT_VERIFIABLE", "DECLARED", "FAILED"),
}
#: Les deux blocs dérivables hors des cinq clauses, en liste close eux aussi. La cellule
#: d'estampille : § B.4 ne connaît que « même cellule » ou `E_STAMP_MISMATCH` ; l'état
#: `NOT_VERIFIABLE` (bloc absent, estampille nulle) est une décision d'outillage de
#: `c3_continuity.stamp_cell_block`, consignée au paquet de clarifications C3b, jamais « déclarée ».
#: Le comparateur d'évaluation : § C.5, une conjonction recalculée est vraie ou fausse, rien d'autre.
STAMP_CELL_ADMISSIBLE_STATES: tuple[str, ...] = ("VERIFIED", "FAILED", "NOT_VERIFIABLE")
COMPARATOR_ADMISSIBLE_STATES: tuple[str, ...] = ("VERIFIED", "FAILED")
#: Ce que la clause 3 (liquidation terminale costée) dit de la normalisation : dérivé de son état,
#: jamais recopié — définie sur la liste close de c3, et sur elle seule.
LIQUIDATION_NORMALISED_OF_C3: dict[str, bool | None] = {
    "VERIFIED": True,
    "NOT_VERIFIABLE": None,
    "FAILED": False,
}


#: § C.5 — les tests de comparabilité du comparateur d'évaluation, liste close, **lus et typés tous
#: avant la conjonction** (revue Fin, défaut 5) ; partagée par `c3_continuity` et `c3_verdict`.
COMPARABILITY_TESTS: tuple[str, ...] = (
    "entry_stamp_present",
    "exit_stamp_present",
    "ff_ok",
    "n_returns_ok",
    "all_finite",
)


def continuity_aggregate(states: Mapping[str, str]) -> str:
    """L'état agrégé des clauses § B, par précédence `CONTINUITY_SEVERITY` (la pire clause).

    Strict : un mapping vide ou un état hors `CONTINUITY_STATES` est une erreur d'entrée — jamais un
    repli sur ``VERIFIED``, l'état que la table § 6.4 rend inconstructible en C3a.
    """
    if not states:
        raise MissingEvidenceError("continuité : aucune clause à agréger")
    for key, state in states.items():
        if state not in CONTINUITY_STATES:
            raise MissingEvidenceError(
                f"continuité : clause {key} dans l'état {state!r} hors liste close {list(CONTINUITY_STATES)}"
            )
    for candidate in CONTINUITY_SEVERITY:
        if candidate in states.values():
            return candidate
    return "VERIFIED"


#: Les quatre séries que D1 couvre (§ A.8), en minutes.
D1_INTERVALS: tuple[int, ...] = (5, 240, 1440, 10080)
WEEK_MINUTES = 10_080
#: Contrat C2 de l'export `warmup` (`backtest.py:309`, `:519`) — recopié pour **recouper** la valeur
#: déclarée de `sufficient`, jamais pour décider ; non décisionnel, hors registre.
WARMUP_GAP_TOLERANCE = 1


# ---------------------------------------------------------------------------
# Manifeste (§ A.5, § A.6) — typage strict ; les valeurs gelées sont assertées par c3_anchor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    strategy: str
    pair: str
    params: Mapping[str, Any]
    identity: str
    decision_timeframes: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    raw: Mapping[str, Any]
    window_start: datetime
    window_end: datetime
    anchor_fraction: float
    prefix_segment: str
    exchange: str
    exec_interval: int
    timeframes: Mapping[str, int]
    fee_model: str
    taker: Decimal
    pair_costs_file: str
    pair_costs: Mapping[str, tuple[Decimal, Decimal]]
    min_order_usdc: float
    provenance: str
    candidates: tuple[Candidate, ...]
    engines: Mapping[str, str]
    thresholds: Mapping[str, Mapping[str, Any]]
    lambda_mode: str
    seed: int
    bootstrap_b: int
    block_lengths: tuple[int, ...]
    bound_level: float
    variant_id: str
    parent_is_root: bool
    parent_variant_key: str | None
    research_log_entry: str
    protocol_sha256: str
    run_scope: str | None

    @property
    def capital(self) -> Decimal:
        return Decimal(str(self.thresholds["CAPITAL"]["value"]))

    @property
    def pairs(self) -> tuple[str, ...]:
        return tuple(sorted({c.pair for c in self.candidates}))

    def anchor(self) -> datetime:
        return anchor_of(self.window_start, self.window_end, self.anchor_fraction)


def load_manifest(raw: Any) -> Manifest:
    """Typage strict du manifeste — chaque champ par l'accesseur, chaque liste close vérifiée.

    Ce que cette fonction **ne fait pas** : asserter les valeurs gelées (fraction d'ancrage,
    paramètres d'incertitude, seuils, sha256 du protocole). C'est le rôle de `c3_anchor`, étape 1.
    """
    where = "manifest"
    if not isinstance(raw, Mapping):
        raise MissingEvidenceError(f"{where}: bloc attendu, reçu {type(raw).__name__}")
    window = require_mapping(raw, "window", where=where)
    start = require_datetime(window, "start", where=f"{where}.window")
    end = require_datetime(window, "end", where=f"{where}.window")
    if end <= start:
        raise MissingEvidenceError(
            f"{where}.window: fin {end.isoformat()} <= début {start.isoformat()}"
        )
    fraction = require_float(raw, "anchor_fraction", where=where)
    prefix = require_str(raw, "prefix_segment", where=where)
    data = require_mapping(raw, "data", where=where)
    exchange = require_str(data, "exchange", where=f"{where}.data")
    exec_interval = require_int(data, "exec_interval", where=f"{where}.data", minimum=1)
    tf_block = require_mapping(data, "timeframes", where=f"{where}.data")
    timeframes = {
        label: require_int(tf_block, label, where=f"{where}.data.timeframes", minimum=1)
        for label in tf_block
    }
    if not timeframes:
        raise MissingEvidenceError(f"{where}.data.timeframes: aucune série déclarée")
    fees = require_mapping(raw, "fees", where=where)
    fee_model = require_str(fees, "model", where=f"{where}.fees")
    taker = require_decimal(fees, "taker", where=f"{where}.fees")
    pair_costs_file = require_str(fees, "pair_costs_file", where=f"{where}.fees")
    costs_block = require_mapping(fees, "pair_costs", where=f"{where}.fees")
    pair_costs: dict[str, tuple[Decimal, Decimal]] = {}
    for pair in costs_block:
        block = require_mapping(costs_block, pair, where=f"{where}.fees.pair_costs")
        pair_costs[pair] = (
            require_decimal(block, "spread", where=f"{where}.fees.pair_costs.{pair}"),
            require_decimal(block, "slippage", where=f"{where}.fees.pair_costs.{pair}"),
        )
    min_order = require_float(raw, "min_order_usdc", where=where)
    universe = require_mapping(raw, "universe", where=where)
    provenance = require_str(universe, "provenance", where=f"{where}.universe", allowed=PROVENANCES)
    strategies_block = require_mapping(raw, "strategies", where=where)
    engines: dict[str, str] = {}
    strategy_tfs: dict[str, tuple[str, ...]] = {}
    for name in strategies_block:
        block = require_mapping(strategies_block, name, where=f"{where}.strategies")
        engines[name] = require_str(
            block, "engine", where=f"{where}.strategies.{name}", allowed=ENGINES
        )
        tfs = require_sequence(
            block, "decision_timeframes", where=f"{where}.strategies.{name}", min_len=1
        )
        strategy_tfs[name] = _timeframe_labels(
            tfs, timeframes, where=f"{where}.strategies.{name}.decision_timeframes"
        )
    raw_candidates = require_sequence(universe, "candidates", where=f"{where}.universe", min_len=1)
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for i, item in enumerate(raw_candidates):
        cwhere = f"{where}.universe.candidates[{i}]"
        if not isinstance(item, Mapping):
            raise MissingEvidenceError(f"{cwhere}: bloc attendu, reçu {type(item).__name__}")
        strategy = require_str(item, "strategy", where=cwhere)
        pair = require_str(item, "pair", where=cwhere)
        params = require_mapping(item, "params", where=cwhere)
        if strategy not in engines:
            raise MissingEvidenceError(
                f"{cwhere}.strategy: {strategy!r} absent de manifest.strategies"
            )
        if pair not in pair_costs:
            raise MissingEvidenceError(
                f"{cwhere}.pair: {pair!r} sans coûts déclarés dans manifest.fees.pair_costs"
            )
        override = optional_sequence(item, "decision_timeframes", where=cwhere)
        if override is not None and len(override) == 0:
            # Une surcharge vide n'est pas « aucune surcharge » : elle laisserait D2 et la clause 4
            # « vérifiées » sur zéro série, sans rien recalculer (passe interne, revue Fin 2).
            raise MissingEvidenceError(
                f"{cwhere}.decision_timeframes: surcharge vide — au moins une série de décision"
            )
        tfs = (
            strategy_tfs[strategy]
            if override is None
            else _timeframe_labels(override, timeframes, where=f"{cwhere}.decision_timeframes")
        )
        identity = candidate_identity(strategy, pair, params)
        if identity in seen:
            raise EntryRefusedError(
                "R0_INVALID_RUN", f"{cwhere}: identité canonique dupliquée {identity[:16]} (§ A.2)"
            )
        seen.add(identity)
        candidates.append(Candidate(strategy, pair, params, identity, tfs))
    rule = require_mapping(raw, "selection_rule", where=where)
    require_str(rule, "text", where=f"{where}.selection_rule")
    thresholds_block = require_mapping(rule, "thresholds", where=f"{where}.selection_rule")
    thresholds: dict[str, Mapping[str, Any]] = {}
    for name in thresholds_block:
        block = require_mapping(thresholds_block, name, where=f"{where}.selection_rule.thresholds")
        _require(block, "value", where=f"{where}.selection_rule.thresholds.{name}")
        require_str(block, "class", where=f"{where}.selection_rule.thresholds.{name}")
        require_str(block, "section", where=f"{where}.selection_rule.thresholds.{name}")
        thresholds[name] = block
    if "CAPITAL" not in thresholds:
        raise MissingEvidenceError(f"{where}.selection_rule.thresholds: CAPITAL absent (§ 0.5)")
    benchmark = require_mapping(raw, "benchmark", where=where)
    require_str(benchmark, "definition", where=f"{where}.benchmark")
    lambda_mode = require_str(
        benchmark, "lambda_mode", where=f"{where}.benchmark", allowed=LAMBDA_MODES
    )
    gates = require_mapping(raw, "gates_Q", where=where)
    for gate in ("Q1", "Q2", "Q3"):
        require_str(gates, gate, where=f"{where}.gates_Q")
    uncertainty = require_mapping(raw, "uncertainty", where=where)
    seed = require_int(uncertainty, "seed", where=f"{where}.uncertainty", minimum=0)
    bootstrap_b = require_int(uncertainty, "B", where=f"{where}.uncertainty")
    lengths = require_sequence(
        uncertainty, "block_lengths", where=f"{where}.uncertainty", min_len=1
    )
    block_lengths: list[int] = []
    for i, item in enumerate(lengths):
        if isinstance(item, bool) or not isinstance(item, int):
            raise MissingEvidenceError(
                f"{where}.uncertainty.block_lengths[{i}]: entier attendu, reçu {item!r}"
            )
        block_lengths.append(item)
    bound_level = require_float(uncertainty, "bound_level", where=f"{where}.uncertainty")
    variant_id = require_str(raw, "variant_id", where=where)
    if not variant_id:
        raise MissingEvidenceError(f"{where}.variant_id: chaîne vide")
    parent = require_mapping(raw, "parent", where=where)
    is_root = require_bool(parent, "is_root", where=f"{where}.parent")
    parent_key = None if is_root else require_str(parent, "variant_key", where=f"{where}.parent")
    research_log_entry = require_str(raw, "research_log_entry", where=where)
    protocol_sha = require_str(raw, "protocol_sha256", where=where)
    run_scope = optional_str(raw, "run_scope", where=where)
    return Manifest(
        raw=raw,
        window_start=start,
        window_end=end,
        anchor_fraction=fraction,
        prefix_segment=prefix,
        exchange=exchange,
        exec_interval=exec_interval,
        timeframes=timeframes,
        fee_model=fee_model,
        taker=taker,
        pair_costs_file=pair_costs_file,
        pair_costs=pair_costs,
        min_order_usdc=min_order,
        provenance=provenance,
        candidates=tuple(candidates),
        engines=engines,
        thresholds=thresholds,
        lambda_mode=lambda_mode,
        seed=seed,
        bootstrap_b=bootstrap_b,
        block_lengths=tuple(block_lengths),
        bound_level=bound_level,
        variant_id=variant_id,
        parent_is_root=is_root,
        parent_variant_key=parent_key,
        research_log_entry=research_log_entry,
        protocol_sha256=protocol_sha,
        run_scope=run_scope,
    )


def _timeframe_labels(
    items: Sequence[Any], timeframes: Mapping[str, int], *, where: str
) -> tuple[str, ...]:
    labels: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise MissingEvidenceError(f"{where}[{i}]: chaîne attendue, reçu {type(item).__name__}")
        if item not in timeframes:
            raise MissingEvidenceError(
                f"{where}[{i}]: {item!r} hors des séries déclarées {sorted(timeframes)}"
            )
        labels.append(item)
    if len(set(labels)) != len(labels):
        raise MissingEvidenceError(f"{where}: doublon")
    return tuple(labels)


# ---------------------------------------------------------------------------
# § A.7 — la projection d'ancrage π_T, liste blanche exhaustive
# ---------------------------------------------------------------------------

#: Champs de premier niveau retenus par π_T — identité et contrats (§ A.7). Toute autre clé de
#: premier niveau est écartée sans être lue, ni hachée, ni rapportée.
PREFIX_WHITELIST_IDENTITY: tuple[str, ...] = ("strategy", "pair", "params", "effective_params")
PREFIX_WHITELIST_CONTRACTS: tuple[str, ...] = (
    "metrics_version",
    "replay_version",
    "exchange",
    "fees",
    "pair_costs",
    "pair_costs_file",
    "min_order_usdc",
)


def project_prefix(entry: Mapping[str, Any], prefix: str, *, where: str) -> dict[str, Any]:
    """π_T(O) pour une observation : ne retient que la liste blanche du § A.7, et rien d'autre.

    Les bornes retenues sont **les seules bornes du segment de préfixe** ; les blocs de segment
    retenus sont ceux du préfixe, **entiers** ; `liquidation` et `dca_counters` sont optionnels
    (`OPTIONAL_FIELDS`) et projetés à `null` quand le runner les a exportés `null`.
    """
    identity = {key: _require(entry, key, where=where) for key in PREFIX_WHITELIST_IDENTITY}
    contracts = {key: _require(entry, key, where=where) for key in PREFIX_WHITELIST_CONTRACTS}
    period = require_mapping(entry, "period", where=where)
    bounds = {
        "start": _require(period, f"{prefix}_start", where=f"{where}.period"),
        "end": _require(period, f"{prefix}_end", where=f"{where}.period"),
    }
    metrics = require_mapping(entry, prefix, where=where)
    equity = require_mapping(
        require_mapping(entry, "equity_daily", where=where), prefix, where=f"{where}.equity_daily"
    )
    liquidation_block = optional_mapping(entry, "liquidation", where=where)
    liquidation = (
        None
        if liquidation_block is None
        else require_mapping(liquidation_block, prefix, where=f"{where}.liquidation")
    )
    warmup = require_mapping(
        require_mapping(entry, "warmup", where=where), prefix, where=f"{where}.warmup"
    )
    rejections = require_mapping(
        require_mapping(entry, "rejections", where=where), prefix, where=f"{where}.rejections"
    )
    dca_block = optional_mapping(entry, "dca_counters", where=where)
    dca = (
        None
        if dca_block is None
        else require_mapping(dca_block, prefix, where=f"{where}.dca_counters")
    )
    return {
        "identity": identity,
        "contracts": contracts,
        "bounds": bounds,
        "metrics": metrics,
        "equity_daily": equity,
        "liquidation": liquidation,
        "warmup": warmup,
        "rejections": rejections,
        "dca_counters": dca,
    }


# ---------------------------------------------------------------------------
# Recalculs depuis la trajectoire quotidienne (§ A.8 D4, § A.9, § F.2 c) et amorçage (§ B.5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyRecompute:
    """Ce que la trajectoire quotidienne exportée permet de recalculer — et ce qu'elle interdit."""

    n_points: int
    returns: tuple[float, ...]
    undefined_returns: int
    domain_ok: bool
    cagr_pct: float | None
    mdd_daily: float
    sigma_daily: float | None
    alert_days: tuple[int, ...]


def recompute_daily(values: Sequence[float], *, days: float) -> DailyRecompute:
    """Rendements, CAGR § F.2 (c), MDD quotidien sur l'index Decimal, σ échantillon (ddof 1).

    L'appelant a validé la finitude (`require_finite_series`) : un `NaN` fourni est une violation,
    pas un cas de ce calcul. Ici, un dénominateur `<= 0` rend le rendement **indéfini** et
    `domain_ok` faux — c'est D4 (portée candidat), parce que le rendement est **dérivé** d'une NAV
    fournie ; le § F.7 (violation) porte sur des rendements **fournis**. Le MDD suit l'algorithme du
    moteur (`backtest_metrics.max_drawdown_pct` sur l'index) ; la NAV exportée est un `float`, donc
    ce recalcul ne restitue pas la précision Decimal du moteur : l'écart est rapporté, non classé.
    """
    vals = [float(v) for v in values]
    returns: list[float] = []
    alerts: list[int] = []
    undefined = 0
    index: list[Decimal] = [Decimal(1)]
    for k in range(1, len(vals)):
        prev, cur = vals[k - 1], vals[k]
        if prev > 0:
            r = cur / prev - 1.0
            returns.append(r)
            if r <= -0.5:
                alerts.append(k)
            dprev, dcur = Decimal(str(prev)), Decimal(str(cur))
            index.append(index[-1] * (Decimal(1) + (dcur - dprev) / dprev))
        else:
            undefined += 1
            index.append(index[-1])
    domain_ok = len(vals) >= 2 and all(v > 0 for v in vals)
    cagr = cagr_pct(returns, days) if domain_ok and returns else None
    sigma = statistics.stdev(returns) if len(returns) > 1 else None
    return DailyRecompute(
        n_points=len(vals),
        returns=tuple(returns),
        undefined_returns=undefined,
        domain_ok=domain_ok,
        cagr_pct=cagr,
        mdd_daily=max_drawdown_pct(index),
        sigma_daily=sigma,
        alert_days=tuple(alerts),
    )


def warmup_sufficient(block: Mapping[str, Any], *, where: str) -> tuple[bool, bool]:
    """`(recalculé, déclaré)` de `sufficient` — règle C2 (`backtest.py:519`), recoupée, jamais recopiée."""
    required = require_int(block, "required", where=where, minimum=0)
    loaded = require_int(block, "loaded", where=where, minimum=0)
    stale = nullable_int(block, "stale_by_candles", where=where, minimum=0)
    gap = require_int(block, "largest_gap_candles", where=where, minimum=0)
    declared = require_bool(block, "sufficient", where=where)
    recomputed = loaded >= required and stale == 0 and gap <= WARMUP_GAP_TOLERANCE
    return recomputed, declared


# ---------------------------------------------------------------------------
# § A.8 D1 — dénominateurs par timeframe, recalculés depuis les bornes (jamais lus)
# ---------------------------------------------------------------------------


def full_days_in(start: datetime, end: datetime) -> int:
    """Jours civils **entiers** `[d 00:00, d+1 00:00]` inclus dans `[start, end]` — l'unité de D1
    pour 5 min, 4 h et 1 j ; un jour de bord partiel n'est pas une unité (il ne peut atteindre ni
    144 bougies ni 6 estampilles)."""
    first = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if first < start:
        first += timedelta(days=1)
    count = 0
    day = first
    while day + timedelta(days=1) <= end:
        count += 1
        day += timedelta(days=1)
    return count


def weekly_stamps_in(start: datetime, end: datetime) -> int:
    """Estampilles hebdomadaires (lundi 00:00, fin de période) dans `(start, end]` — l'unité de D1
    pour 1 w : des **périodes**, jamais des jours (§ A.8)."""
    stamp = first_stamp_strictly_after(start, WEEK_MINUTES)
    count = 0
    while stamp <= end:
        count += 1
        stamp += timedelta(days=7)
    return count


def expected_units(start: datetime, end: datetime, interval: int) -> int:
    return weekly_stamps_in(start, end) if interval == WEEK_MINUTES else full_days_in(start, end)


def coverage_unit(interval: int) -> str:
    return "week" if interval == WEEK_MINUTES else "day"


def max_gap_days(prefix_days: float) -> float:
    """`min(31 j, 3 % des jours du préfixe)` (§ A.8 D1)."""
    return min(float(MAX_GAP_DAYS_ABS), MAX_GAP_RATIO * prefix_days)


def gap_days(run_candles: int, interval: int) -> float:
    """Un run de `run_candles` estampilles manquantes consécutives, en jours — la formule est le
    contrat de `longest_gap_days` : `run × 7` pour 1 w, sinon `run × intervalle / 1440`, en double."""
    if interval == WEEK_MINUTES:
        return run_candles * 7.0
    return run_candles * interval / 1440.0


def longest_missing_run(stamps: Sequence[datetime], interval: int) -> int:
    """Plus longue suite d'estampilles manquantes **consécutives sur la grille attendue**. Une série
    qui commence en retard ou s'arrête tôt est un trou au bord, compté comme les autres (revue R3,
    2e passe) : les estampilles manquantes sont déjà contraintes à `(début, T]` et à la grille."""
    step = timedelta(days=7) if interval == WEEK_MINUTES else timedelta(minutes=interval)
    longest = 0
    run = 0
    previous: datetime | None = None
    for stamp in sorted(stamps):
        run = run + 1 if previous is not None and stamp - previous == step else 1
        longest = max(longest, run)
        previous = stamp
    return longest


def expected_candles(start: datetime, end: datetime, interval: int) -> int:
    """Estampilles de la série `interval` dans `(start, end]` — le compte de bougies attendu."""
    if interval == WEEK_MINUTES:
        return weekly_stamps_in(start, end)
    first = first_stamp_strictly_after(start, interval)
    if first > end:
        return 0
    return int((end - first).total_seconds() // (interval * 60)) + 1


def unit_day_of(stamp: datetime, interval: int) -> Any:
    """Le jour civil qu'une bougie **estampillée en fin de période** couvre : celui de `stamp − intervalle`."""
    return (stamp - timedelta(minutes=interval)).date()


def coverage_recompute(
    block: Mapping[str, Any], *, start: datetime, end: datetime, interval: int, where: str
) -> dict[str, Any]:
    """Recoupe un bloc de couverture (§ A.7) **avant** que D1 le consomme (plan R3, correctif b).

    Tout ce qui est dérivable des `missing_stamps` et des bornes est recalculé et comparé au
    déclaré : le compte de bougies attendu, le compte observé, et surtout `covered_units` — par la
    règle de D1 propre à chaque série (1 j : jour présent ; 4 h : les six estampilles ; 5 min :
    au moins 144 bougies ; 1 w : période présente). Une contradiction est un **problème de
    couverture**, jamais un D1 vert. Les compteurs sont aussi recoupés entre eux (`observed <=
    expected`, `observed == 0 ⟹ covered == 0`) et les jours de bord contre la fenêtre.
    """
    problems: list[str] = []
    expected = require_int(block, "expected", where=where, minimum=0)
    observed = require_int(block, "observed", where=where, minimum=0)
    covered = require_int(block, "covered_units", where=where, minimum=0)
    expected_units_declared = require_int(block, "expected_units", where=where, minimum=1)
    missing_raw = require_sequence(block, "missing_stamps", where=where)
    stamps: list[datetime] = []
    for i, item in enumerate(missing_raw):
        stamp = parse_datetime(item, where=f"{where}.missing_stamps[{i}]")
        if not (start < stamp <= end):
            problems.append(f"{where}.missing_stamps[{i}]: {stamp.isoformat()} hors de (début, T]")
        if last_stamp_at_or_before(stamp, interval) != stamp:
            problems.append(
                f"{where}.missing_stamps[{i}]: {stamp.isoformat()} n'est pas une estampille de la série {interval}"
            )
        stamps.append(stamp)
    if len(set(stamps)) != len(stamps):
        problems.append(f"{where}.missing_stamps: doublon")
    expected_recomputed = expected_candles(start, end, interval)
    if expected != expected_recomputed:
        problems.append(
            f"{where}.expected: {expected} != {expected_recomputed} recalculé depuis les bornes"
        )
    observed_recomputed = expected_recomputed - len(stamps)
    if observed != observed_recomputed:
        problems.append(
            f"{where}.observed: {observed} != {observed_recomputed} = attendu − estampilles manquantes"
        )
    if observed > expected:
        problems.append(f"{where}.observed: {observed} > expected {expected}")
    units_recomputed = expected_units(start, end, interval)
    if expected_units_declared != units_recomputed:
        problems.append(
            f"{where}.expected_units: {expected_units_declared} != {units_recomputed} recalculé depuis les bornes"
        )
    if interval == WEEK_MINUTES:
        covered_recomputed = units_recomputed - len(stamps)
    else:
        first_full = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if first_full < start:
            first_full += timedelta(days=1)
        full_days = {(first_full + timedelta(days=k)).date() for k in range(units_recomputed)}
        per_day = Counter(unit_day_of(stamp, interval) for stamp in stamps)
        if interval == 5:
            uncovered = {
                d
                for d, n in per_day.items()
                if d in full_days and DAY_5M_EXPECTED - n < DAY_5M_MIN_CANDLES
            }
        else:
            uncovered = {d for d in per_day if d in full_days}
        covered_recomputed = units_recomputed - len(uncovered)
    if covered != covered_recomputed:
        problems.append(
            f"{where}.covered_units: {covered} != {covered_recomputed} recalculé depuis missing_stamps"
        )
    if observed == 0 and covered != 0:
        problems.append(f"{where}: observed == 0 mais covered_units == {covered}")
    # Le trou maximal, même motif que covered_units : recalculé sur la grille attendue, bords
    # compris, et recoupé au déclaré — d1_for_pair ne consomme jamais le déclaré.
    longest_run = longest_missing_run(stamps, interval)
    gap_recomputed = gap_days(longest_run, interval)
    gap_declared = require_float(block, "longest_gap_days", where=where)
    if gap_declared != gap_recomputed:
        problems.append(
            f"{where}.longest_gap_days: {gap_declared!r} != {gap_recomputed!r} recalculé "
            f"({longest_run} estampilles consécutives manquantes)"
        )
    first_day = require_str(block, "first_day", where=where)
    last_day = require_str(block, "last_day", where=where)
    try:
        first_d = datetime.fromisoformat(first_day).date()
        last_d = datetime.fromisoformat(last_day).date()
    except ValueError:
        problems.append(
            f"{where}.first_day/last_day: dates illisibles ({first_day!r}, {last_day!r})"
        )
    else:
        if not (start.date() <= first_d <= last_d <= end.date()):
            problems.append(
                f"{where}.first_day/last_day: [{first_day}, {last_day}] hors de la fenêtre ou inversés"
            )
    return {
        "expected_recomputed": expected_recomputed,
        "observed_recomputed": observed_recomputed,
        "covered_recomputed": covered_recomputed,
        "expected_units_recomputed": units_recomputed,
        "longest_gap_candles": longest_run,
        "longest_gap_days_recomputed": gap_recomputed,
        "n_missing": len(stamps),
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# § A.8 D3 et D6 — règles partagées par c3_benchmark, c3_select et c3_continuity
# ---------------------------------------------------------------------------


def clause_d3(
    engine: str,
    *,
    total_trades: int,
    winning: int,
    losing: int,
    liquidation: Mapping[str, Any] | None,
    where: str,
) -> tuple[int | None, str]:
    """`(cycles, détail)` selon le moteur déclaré (§ A.8 D3) ; `None` = non calculable ou inapplicable."""
    if engine == "grid":
        if liquidation is None:
            return None, "moteur grid sans bloc liquidation : cycles non calculables"
        cycles = total_trades - require_int(liquidation, "positions", where=where, minimum=0)
    elif winning + losing == 0 and total_trades > 0:
        return (
            None,
            "stratégie d'accumulation sans aucune vente : D3 inapplicable, aucun nombre de substitution (§ A.8 D3)",
        )
    else:
        cycles = total_trades
    return cycles, f"cycles achevés {cycles} {'>=' if cycles >= CYCLES_MIN else '<'} {CYCLES_MIN}"


def d3_passes(cycles: int | None) -> bool:
    return cycles is not None and cycles >= CYCLES_MIN


def liquidation_identities(
    block: Mapping[str, Any] | None,
    *,
    spread: Decimal,
    slippage: Decimal,
    taker: Decimal,
    end: datetime,
    where: str,
) -> dict[str, Any]:
    """D6 — identités **exactes** en Decimal (plan § 5.5) et preuve par lot (§ 6.5, revue R3 a).

    Par lot : `amount_i > 0`, `gross_i == amount_i × price` (le prix du bloc — un seul prix de
    liquidation, `backtest.py:3104`), `fee_i == gross_i × taker` (`:3105`), `entry_price` et `pnl`
    nuls ensemble ; agrégats : Σ fee = fees, Σ gross = gross_usdc, nombre de lots = trades, lots à
    coût connu = positions, Σ amount des lots inconnus = residual_trade_btc. `lots` absent ⇒ la
    magnitude du taker est indécidable ⇒ non vérifié. Aucun seuil. Partagé par la sélection (D6 au
    préfixe) et la continuité (clause 3 à l'évaluation).
    """
    zero = Decimal(0)
    one = Decimal(1)
    checks: dict[str, bool | None] = {}
    details: list[str] = []
    reported: dict[str, Any] = {}

    def check(name: str, ok: bool, detail: str) -> None:
        checks[name] = ok
        if not ok:
            details.append(f"{name}: {detail}")

    if block is None:
        return {
            "passed": False,
            "lots_present": False,
            "checks": {"bloc_present": False},
            "details": [
                "bloc `liquidation` absent ou null : liquidation terminale non normalisée (§ B.3)"
            ],
            "reported": reported,
        }
    positions = require_int(block, "positions", where=where, minimum=0)
    trades = require_int(block, "trades", where=where, minimum=0)
    residual_trade = require_decimal(block, "residual_trade_btc", where=where)
    residual_net = require_decimal(block, "residual_net_proceeds", where=where)
    fees = require_decimal(block, "fees", where=where)
    gross = require_decimal(block, "gross_usdc", where=where)
    unknown = trades - positions
    check("trades_positions", unknown in (0, 1), f"trades − positions = {unknown}, attendu 0 ou 1")
    check(
        "residual_trade_iff_unknown",
        (residual_trade == zero) == (unknown == 0),
        f"residual_trade_btc {residual_trade} vs lot inconnu {unknown}",
    )
    check(
        "residual_net_iff_unknown",
        (residual_net == zero) == (unknown == 0),
        f"residual_net_proceeds {residual_net} vs lot inconnu {unknown}",
    )
    reported["dust_written_off_btc"] = str(
        require_decimal(block, "dust_written_off_btc", where=where)
    )
    reported["inventory_divergence_btc"] = str(
        require_decimal(block, "inventory_divergence_btc", where=where)
    )
    reported["net_pnl_lot_basis"] = str(require_decimal(block, "net_pnl_lot_basis", where=where))
    reported["pnl"] = str(require_decimal(block, "pnl", where=where))
    price: Decimal | None = None
    if trades > 0:
        timestamp = nullable_datetime(block, "timestamp", where=where)
        reference = nullable_decimal(block, "reference_price", where=where)
        price = nullable_decimal(block, "price", where=where)
        spread_pct = nullable_decimal(block, "spread_pct", where=where)
        slippage_pct = nullable_decimal(block, "slippage_pct", where=where)
        present = None not in (timestamp, reference, price, spread_pct, slippage_pct)
        check(
            "prix_presents",
            present,
            "timestamp / reference_price / price / spread_pct / slippage_pct requis quand trades > 0",
        )
        if present:
            assert timestamp is not None and reference is not None and price is not None
            check("spread_pct", spread_pct == spread, f"{spread_pct} != manifeste {spread}")
            check(
                "slippage_pct", slippage_pct == slippage, f"{slippage_pct} != manifeste {slippage}"
            )
            expected_price = reference * (one - spread - slippage)
            check(
                "price_identity",
                price == expected_price,
                f"price {price} != reference × (1 − spread − slippage) = {expected_price}",
            )
            check(
                "timestamp_le_borne",
                timestamp <= end,
                f"{timestamp.isoformat()} > borne {end.isoformat()}",
            )
        check("gross_positive", gross > zero, f"gross_usdc {gross} <= 0 avec trades > 0")
        check(
            "fees_positive",
            fees > zero,
            f"fees {fees} <= 0 avec trades > 0 — le taker n'a pas été prélevé",
        )
    else:
        check(
            "etat_sans_trade",
            positions == 0 and fees == zero and gross == zero,
            f"positions {positions}, fees {fees}, gross {gross} avec trades = 0",
        )
    lots = optional_sequence(block, "lots", where=where)
    if lots is None:
        checks["lots_present"] = False
        details.append(
            "lots absent : la magnitude du taker est indécidable sur l'export agrégé — D6 non vérifié (exigence C3b : export des lots)"
        )
        return {
            "passed": False,
            "lots_present": False,
            "checks": checks,
            "details": details,
            "reported": reported,
        }
    checks["lots_present"] = True
    fee_sum = zero
    gross_sum = zero
    known = 0
    unknown_amount = zero
    lots_ok = True
    for i, lot in enumerate(lots):
        lwhere = f"{where}.lots[{i}]"
        if not isinstance(lot, Mapping):
            raise MissingEvidenceError(f"{lwhere}: bloc attendu, reçu {type(lot).__name__}")
        gross_i = require_decimal(lot, "gross_usdc", where=lwhere)
        fee_i = require_decimal(lot, "fee", where=lwhere)
        amount_i = require_decimal(lot, "amount_btc", where=lwhere)
        entry_price = nullable_decimal(lot, "entry_price", where=lwhere)
        pnl = nullable_decimal(lot, "pnl", where=lwhere)
        if amount_i <= zero:
            lots_ok = False
            details.append(f"lot[{i}]: amount_btc {amount_i} non strictement positif")
        if price is None:
            lots_ok = False
            details.append(
                f"lot[{i}]: aucun prix de liquidation dans le bloc pour vérifier gross = amount × price"
            )
        elif gross_i != amount_i * price:
            lots_ok = False
            details.append(f"lot[{i}]: gross_usdc {gross_i} != amount × price = {amount_i * price}")
        expected_fee = gross_i * taker
        if fee_i != expected_fee:
            lots_ok = False
            details.append(f"lot[{i}]: fee {fee_i} != gross × taker = {expected_fee}")
        if gross_i <= zero or fee_i <= zero:
            lots_ok = False
            details.append(f"lot[{i}]: gross {gross_i} ou fee {fee_i} non strictement positif")
        if (entry_price is None) != (pnl is None):
            lots_ok = False
            details.append(
                f"lot[{i}]: entry_price et pnl doivent être nuls ensemble (lot à coût inconnu)"
            )
        if entry_price is None:
            unknown_amount += amount_i
        else:
            known += 1
        fee_sum += fee_i
        gross_sum += gross_i
    check(
        "lots_identites",
        lots_ok,
        "au moins un lot contredit amount > 0, gross = amount × price ou fee = gross × taker",
    )
    check("lots_fees_sum", fee_sum == fees, f"Σ fee_i {fee_sum} != fees {fees}")
    check("lots_gross_sum", gross_sum == gross, f"Σ gross_i {gross_sum} != gross_usdc {gross}")
    check("lots_count", len(lots) == trades, f"{len(lots)} lots != trades {trades}")
    check("lots_known", known == positions, f"{known} lots à coût connu != positions {positions}")
    check(
        "lots_unknown_amount",
        unknown_amount == residual_trade,
        f"Σ amount des lots inconnus {unknown_amount} != residual_trade_btc {residual_trade}",
    )
    passed = all(v for v in checks.values() if v is not None)
    return {
        "passed": passed,
        "lots_present": True,
        "checks": checks,
        "details": details,
        "reported": reported,
    }
