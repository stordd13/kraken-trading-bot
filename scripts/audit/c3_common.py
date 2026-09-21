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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import rejeu_common as rc  # noqa: E402

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
    "WINDOW_START", "WINDOW_END", "WINDOW_DAYS", "TRAIN_RATIO",
    "SEGMENT_POINTS", "SEGMENT_RETURNS", "SEGMENTS",
    "CYCLES_MIN", "NNZ_MIN", "COVERAGE_MIN_DAYS", "MAX_GAP_DAYS",
    "DAY_5M_COMPLETE_MIN", "FIRST_COVERED_DAY_MAX", "LAST_COVERED_DAY_MIN",
    "G2_MIN_RETURN_PCT", "G3_FEE_MULTIPLE", "MIN_RETURN_DOMAIN", "FF_DAYS_MAX",
    "N_CONFIGS_PER_PAIR", "N_CONFIGS_TOTAL", "BASE_SHA", "REASON_PRIORITY",
    "SEED_BASE", "DEGENERATE_MAX", "ALPHA", "CLASS_DEFAULTS", "STRATEGY", "PAIRS",
)

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

#: Portées du § I.1. Une raison de portée « candidat » n'est jamais portée par la chaîne.
REASON_SCOPE: dict[str, str] = {
    "R0_INVALID_RUN": "run",
    "P_PROVENANCE": "run",
    "D_WARMUP_PREFIX": "candidat",  # promue en « artefact » par PROMOTABLE_CLAUSES (§ I.1)
    "A_NO_ADMISSIBLE_CANDIDATE": "run",
    "A_BELOW_FLOOR": "run",
    "D_WARMUP_ANCHOR": "run",
    "E_NO_BENCHMARK": "run",
    "E_STAMP_MISMATCH": "run",
    "F_NOT_ESTIMABLE": "run",
    "F_CANNOT_SEPARATE": "run",
    "R1_NOT_NORMALISED": "candidat",
    "D_NOT_ADMISSIBLE": "candidat",
    "C_COVERAGE": "candidat",
}

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
    "ADMISSIBLE", "NOT_ESTIMABLE", "NON_ADMISSIBLE", "HORS_USAGE_DÉCISIONNEL",
)
STATUS_PAIR: tuple[str, ...] = ("VOTANTE", "DESCRIPTIF")
STATUS_SELECTION: tuple[str, ...] = (
    "SÉLECTION_VALIDE", "SÉLECTION_DESCRIPTIVE", "ABSTENTION",
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


def artifact_header(now: datetime, inputs: dict[str, Path] | None = None) -> dict[str, Any]:
    """En-tête commun : `generated_at`, `protocole`, `inputs_sha256`."""
    header: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "protocole": protocol_descriptor(),
    }
    if inputs:
        header["inputs_sha256"] = {k: file_sha256(v) for k, v in sorted(inputs.items())}
    return header
