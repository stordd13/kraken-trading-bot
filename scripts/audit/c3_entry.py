"""C3 — la validité d'entrée (§ I-A), les lignes 2, 4 et 5 de la table du § I.1, le refus du § D.3.

Étape 2 de la chaîne du § L.1. Elle lit le manifeste, l'ancrage (étape 1), les observations et,
s'il est fourni, l'artefact de couverture, et écrit **toujours** un artefact de validation — sur
succès, sur violation et sur refus : « la non-recevabilité est un refus d'entrée : code 2, rien n'est
publié **au-delà de la validation** » (§ I.1). Ce que le rapport cite, c'est cet artefact.

**Ordre gelé des assertions** ; tout ce qui suit le premier échec est **sauté, jamais vert**
(précédent : `rejeu_validate_campaign.run_assertions`) :

1. forme des observations — le préfixe est obligatoire, ses blocs typés ; les segments non-préfixe,
   quand présents, sont bien formés (§ A.12 l.652) et jamais lus par π_T ;
2. D5 — contrats d'instrument égaux au manifeste, intervalles des séries de décision ; l'intervalle
   d'exécution n'a **aucun porteur** dans l'export réel : il est consigné ``not_assertable`` ;
3. bornes du préfixe exactement `[début, T]`, `T` recalculé, grille quotidienne de la bonne longueur ;
4. unicité des identités canoniques (§ A.2) **et** égalité stricte observations ↔ univers fermé ;
5. provenance de l'univers, typée, recoupée avec l'ancrage ;
6. bloc d'amorçage du préfixe : chaque série de décision présente, ``sufficient`` **recalculé** selon
   la règle C2 et recoupé au déclaré (désaccord = violation, § I.1 l.15) ;
7. artefact de couverture : absent → ``not_assertable`` ; présent → forme, `[début, T]`, paires de
   l'univers, unités attendues **recalculées** depuis les bornes ;
8. D2 — sur la totalité des candidats → refus d'artefact `D_WARMUP_PREFIX` (§ I.1 l.5, aucun
   classement) ; sur une partie → `ok` avec diagnostics de candidats (l.4), la chaîne continue.

**``not_assertable`` n'est jamais verte** : elle ne bloque pas les assertions suivantes, mais un
parcours achevé sans refus antérieur et avec au moins une clause non assertable sort en refus
``R0_INVALID_RUN`` (« contrat non vérifiable »). C'est ce qui laisse l'artefact réel atteindre D2 et
sortir en ``D_WARMUP_PREFIX`` (§ D.3), tout en interdisant qu'une entrée soit validée pour sélection
sans que chaque clause D5 soit assertable et verte.

Pure, lecture seule hors de ses sorties. Aucun accès base.

Usage::

    poetry run python scripts/audit/c3_entry.py \\
        --manifest results/c3a_entry_validation/manifest_rejeu_grid_20260919.json \\
        --anchor results/c3a_entry_validation/anchor_rejeu_grid_20260919.json \\
        --observations results/rejeu_grid_20260919/P7_phase1_grid.json \\
        --output results/c3a_entry_validation/entry_rejeu_grid_20260919.json \\
        --markdown results/c3a_entry_validation/entry_rejeu_grid_20260919.md \\
        --now 2026-09-22T00:00:00+00:00

Exit codes: 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import c3_common as cc  # noqa: E402

from krakenbot.backtest_metrics import METRICS_VERSION  # noqa: E402
from krakenbot.replay_contract import REPLAY_VERSION  # noqa: E402

STEP = "entry"
STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_NOT_ASSERTABLE = "not_assertable"
FINAL_ASSERTION = "I-A.fin"


@dataclass
class Outcome:
    problems: list[str] = field(default_factory=list)
    not_assertable: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Context:
    manifest: cc.Manifest
    anchor: datetime
    prefix_days: float
    observations: Mapping[str, Any]
    coverage_path: Path | None
    coverage: Mapping[str, Any] | None = None
    coverage_status: str = "not_provided"
    identities: dict[str, str] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def prefix(self) -> str:
        return self.manifest.prefix_segment

    def entry(self, key: str) -> Mapping[str, Any]:
        return cc.require_mapping(self.observations, key, where="observations")

    def matched_candidate(self, entry: Mapping[str, Any], *, where: str) -> cc.Candidate | None:
        """Le candidat du manifeste de même identité canonique (§ A.2), ou ``None``."""
        strategy = cc.require_str(entry, "strategy", where=where)
        pair = cc.require_str(entry, "pair", where=where)
        params = cc.require_mapping(entry, "params", where=where)
        identity = cc.candidate_identity(strategy, pair, params)
        for candidate in self.manifest.candidates:
            if candidate.identity == identity:
                return candidate
        return None

    def decision_timeframes(self, entry: Mapping[str, Any], *, where: str) -> tuple[str, ...]:
        """Les séries de décision du candidat : sa surcharge, sinon celles de sa stratégie."""
        matched = self.matched_candidate(entry, where=where)
        if matched is not None:
            return matched.decision_timeframes
        strategy = cc.require_str(entry, "strategy", where=where)
        if strategy not in self.manifest.engines:
            raise cc.MissingEvidenceError(
                f"{where}.strategy: {strategy!r} absent de manifest.strategies"
            )
        for candidate in self.manifest.candidates:
            if candidate.strategy == strategy:
                return candidate.decision_timeframes
        raise cc.MissingEvidenceError(
            f"{where}: aucune série de décision déclarée pour {strategy!r}"
        )


# ---------------------------------------------------------------------------
# Les assertions, dans l'ordre gelé
# ---------------------------------------------------------------------------


def _liquidation_form(block: Mapping[str, Any], pair: str, *, where: str) -> None:
    """Forme du bloc `liquidation` (grid, B4.3). § A.7 v2.1 : les quantités en actif de base portent le
    suffixe ``_base`` **quelle que soit la paire** (``residual_trade_base``, ``dust_written_off_base``,
    ``inventory_divergence_base``, et ``amount_base`` par lot) ; une clé suffixée par le nom d'un actif
    (``_btc``, ``_eth``, …) est une erreur de forme (§ I.1, ligne 2). Le moteur écrit ``_btc`` pour toutes
    les paires (convention ``btc_held``, `backtest.py:3288-3293`) : le renommage vit dans la couche
    d'export du runner (C3b), jamais ici."""
    del pair  # la paire n'entre pas dans les noms de clés, voir la docstring
    base = "base"
    cc.check_base_quantity_keys(block, where=where)
    cc.require_int(block, "positions", where=where, minimum=0)
    cc.require_int(block, "trades", where=where, minimum=0)
    for key in (
        "buy_fees",
        "sell_fees",
        "net_pnl_lot_basis",
        "residual_net_proceeds",
        "pnl",
        "fees",
        "gross_usdc",
        f"residual_trade_{base}",
        f"dust_written_off_{base}",
        f"inventory_divergence_{base}",
    ):
        cc.require_decimal(block, key, where=where)
    cc.nullable_float(block, "avg_holding_minutes", where=where)
    cc.nullable_datetime(block, "timestamp", where=where)
    cc.nullable_decimal(block, "reference_price", where=where)
    cc.nullable_decimal(block, "price", where=where)
    cc.nullable_decimal(block, "spread_pct", where=where)
    cc.nullable_decimal(block, "slippage_pct", where=where)
    lots = cc.optional_sequence(block, "lots", where=where)
    if lots is not None:
        for i, lot in enumerate(lots):
            lwhere = f"{where}.lots[{i}]"
            if not isinstance(lot, Mapping):
                raise cc.MissingEvidenceError(f"{lwhere}: bloc attendu, reçu {type(lot).__name__}")
            cc.check_base_quantity_keys(lot, where=lwhere)
            cc.require_decimal(lot, f"amount_{base}", where=lwhere)
            cc.require_decimal(lot, "gross_usdc", where=lwhere)
            cc.require_decimal(lot, "fee", where=lwhere)
            cc.nullable_decimal(lot, "entry_price", where=lwhere)
            cc.nullable_decimal(lot, "pnl", where=lwhere)


def _segment_form(
    entry: Mapping[str, Any], segment: str, pair: str, *, where: str, is_prefix: bool
) -> None:
    metrics = cc.require_mapping(entry, segment, where=where)
    mwhere = f"{where}.{segment}"
    cc.require_int(metrics, "metrics_version", where=mwhere)
    cc.require_int(metrics, "total_trades", where=mwhere, minimum=0)
    cc.require_int(metrics, "winning_trades", where=mwhere, minimum=0)
    cc.require_int(metrics, "losing_trades", where=mwhere, minimum=0)
    for key in (
        "net_pnl",
        "max_drawdown_pct_daily",
        "starting_balance",
        "ending_balance",
        "duration_days",
    ):
        cc.require_float(metrics, key, where=mwhere)
    cc.require_int(metrics, "n_daily_returns", where=mwhere, minimum=0)
    equity = cc.require_mapping(
        cc.require_mapping(entry, "equity_daily", where=where),
        segment,
        where=f"{where}.equity_daily",
    )
    ewhere = f"{where}.equity_daily.{segment}"
    cc.require_datetime(equity, "start", where=ewhere)
    cc.require_datetime(equity, "end", where=ewhere)
    cc.require_finite_series(equity, "values", where=ewhere, min_len=2)
    warmup = cc.require_mapping(
        cc.require_mapping(entry, "warmup", where=where), segment, where=f"{where}.warmup"
    )
    for tf in warmup:
        block = cc.require_mapping(warmup, tf, where=f"{where}.warmup.{segment}")
        bwhere = f"{where}.warmup.{segment}.{tf}"
        cc.require_int(block, "interval", where=bwhere, minimum=1)
        cc.require_int(block, "extended_by", where=bwhere, minimum=0)
        cc.warmup_sufficient(block, where=bwhere)
        cc.nullable_str(block, "first", where=bwhere)
        cc.nullable_str(block, "last", where=bwhere)
    cc.require_mapping(
        cc.require_mapping(entry, "rejections", where=where), segment, where=f"{where}.rejections"
    )
    liquidation = cc.optional_mapping(entry, "liquidation", where=where)
    if liquidation is not None:
        _liquidation_form(
            cc.require_mapping(liquidation, segment, where=f"{where}.liquidation"),
            pair,
            where=f"{where}.liquidation.{segment}",
        )
    dca = cc.optional_mapping(entry, "dca_counters", where=where)
    if dca is not None:
        cc.require_mapping(dca, segment, where=f"{where}.dca_counters")
    if is_prefix:
        period = cc.require_mapping(entry, "period", where=where)
        cc.require_datetime(period, f"{segment}_start", where=f"{where}.period")
        cc.require_datetime(period, f"{segment}_end", where=f"{where}.period")


def a01_form(ctx: Context) -> Outcome:
    """Forme des observations : préfixe obligatoire et typé, segments futurs bien formés si présents."""
    out = Outcome()
    if not isinstance(ctx.observations, Mapping) or not ctx.observations:
        out.problems.append("observations : un dict non vide d'entrées est attendu")
        return out
    for key in ctx.observations:
        where = f"observations.{key}"
        try:
            entry = ctx.entry(key)
            for name in ("strategy", "pair", "exchange", "fees", "pair_costs_file"):
                cc.require_str(entry, name, where=where)
            cc.require_mapping(entry, "params", where=where)
            cc.require_mapping(entry, "effective_params", where=where)
            # § A.8 D2 v2.1 : toute observation exporte la liste de ses séries de décision — suite non
            # vide d'étiquettes distinctes de `data.timeframes`. Absente ou mal formée : § I.1, ligne 2.
            cc.timeframe_labels(
                cc.require_sequence(entry, "decision_timeframes", where=where, min_len=1),
                ctx.manifest.timeframes,
                where=f"{where}.decision_timeframes",
            )
            cc.require_int(entry, "metrics_version", where=where)
            cc.require_int(entry, "replay_version", where=where)
            costs = cc.require_mapping(entry, "pair_costs", where=where)
            cc.require_decimal(costs, "spread", where=f"{where}.pair_costs")
            cc.require_decimal(costs, "slippage", where=f"{where}.pair_costs")
            cc.require_float(entry, "min_order_usdc", where=where)
            cc.optional_int(entry, "exec_interval", where=where)
            pair = cc.require_str(entry, "pair", where=where)
            segments = list(cc.require_mapping(entry, "equity_daily", where=where))
            if ctx.prefix not in segments:
                raise cc.MissingEvidenceError(
                    f"{where}.equity_daily: segment de préfixe {ctx.prefix!r} absent"
                )
            for segment in segments:
                _segment_form(entry, segment, pair, where=where, is_prefix=segment == ctx.prefix)
        except cc.MissingEvidenceError as exc:
            out.problems.append(str(exc))
    if not out.problems:
        out.notes.append(f"{len(ctx.observations)} entrées, préfixe {ctx.prefix!r}")
    return out


def a02_d5(ctx: Context) -> Outcome:
    """D5 : contrats d'instrument égaux au manifeste ; l'intervalle d'exécution sans porteur est consigné."""
    out = Outcome()
    manifest = ctx.manifest
    without_carrier = 0
    for key in ctx.observations:
        where = f"observations.{key}"
        entry = ctx.entry(key)
        pair = cc.require_str(entry, "pair", where=where)
        checks: list[tuple[str, Any, Any]] = [
            (
                "metrics_version",
                cc.require_int(entry, "metrics_version", where=where),
                METRICS_VERSION,
            ),
            (
                f"{ctx.prefix}.metrics_version",
                cc.require_int(
                    cc.require_mapping(entry, ctx.prefix, where=where),
                    "metrics_version",
                    where=f"{where}.{ctx.prefix}",
                ),
                METRICS_VERSION,
            ),
            (
                "replay_version",
                cc.require_int(entry, "replay_version", where=where),
                REPLAY_VERSION,
            ),
            ("exchange", cc.require_str(entry, "exchange", where=where), manifest.exchange),
            ("fees", cc.require_str(entry, "fees", where=where), manifest.fee_model),
            (
                "pair_costs_file",
                cc.require_str(entry, "pair_costs_file", where=where),
                manifest.pair_costs_file,
            ),
            (
                "min_order_usdc",
                cc.require_float(entry, "min_order_usdc", where=where),
                manifest.min_order_usdc,
            ),
        ]
        costs = cc.require_mapping(entry, "pair_costs", where=where)
        if pair in manifest.pair_costs:
            spread, slippage = manifest.pair_costs[pair]
            checks.append(
                (
                    "pair_costs.spread",
                    cc.require_decimal(costs, "spread", where=f"{where}.pair_costs"),
                    spread,
                )
            )
            checks.append(
                (
                    "pair_costs.slippage",
                    cc.require_decimal(costs, "slippage", where=f"{where}.pair_costs"),
                    slippage,
                )
            )
        else:
            out.problems.append(f"{where}.pair: {pair!r} sans coûts déclarés au manifeste")
        metrics = cc.require_mapping(entry, ctx.prefix, where=where)
        starting = cc.require_float(metrics, "starting_balance", where=f"{where}.{ctx.prefix}")
        checks.append(("starting_balance", Decimal(str(starting)), manifest.capital))
        for name, observed, expected in checks:
            if observed != expected:
                out.problems.append(f"{where}.{name}: {observed!r} != manifeste {expected!r}")
        warmup = cc.require_mapping(
            cc.require_mapping(entry, "warmup", where=where), ctx.prefix, where=f"{where}.warmup"
        )
        for tf in ctx.decision_timeframes(entry, where=where):
            if tf in warmup:
                block = cc.require_mapping(warmup, tf, where=f"{where}.warmup.{ctx.prefix}")
                interval = cc.require_int(
                    block, "interval", where=f"{where}.warmup.{ctx.prefix}.{tf}", minimum=1
                )
                if interval != manifest.timeframes[tf]:
                    out.problems.append(
                        f"{where}.warmup.{ctx.prefix}.{tf}.interval: {interval} != manifeste {manifest.timeframes[tf]}"
                    )
        carrier = cc.optional_int(entry, "exec_interval", where=where)
        if carrier is None:
            without_carrier += 1
        elif carrier != manifest.exec_interval:
            out.problems.append(
                f"{where}.exec_interval: {carrier} != manifeste {manifest.exec_interval}"
            )
    if without_carrier:
        out.not_assertable.append(
            {
                "clause": "D5 — intervalle d'exécution",
                "why": f"aucun porteur `exec_interval` dans {without_carrier} entrée(s) : le runner "
                "n'exporte pas l'intervalle d'exécution (§ A.7, aucun champ de la liste blanche ne le porte)",
            }
        )
    return out


def a03_bounds(ctx: Context) -> Outcome:
    """Bornes du préfixe exactement `[début, T]`, jamais tronquées ; grille quotidienne cohérente."""
    out = Outcome()
    start, anchor = ctx.manifest.window_start, ctx.anchor
    grid_len = len(cc.daily_grid(start, anchor))
    capital = float(ctx.manifest.capital)
    for key in ctx.observations:
        where = f"observations.{key}"
        entry = ctx.entry(key)
        period = cc.require_mapping(entry, "period", where=where)
        p_start = cc.require_datetime(period, f"{ctx.prefix}_start", where=f"{where}.period")
        p_end = cc.require_datetime(period, f"{ctx.prefix}_end", where=f"{where}.period")
        equity = cc.require_mapping(
            cc.require_mapping(entry, "equity_daily", where=where),
            ctx.prefix,
            where=f"{where}.equity_daily",
        )
        e_start = cc.require_datetime(equity, "start", where=f"{where}.equity_daily.{ctx.prefix}")
        e_end = cc.require_datetime(equity, "end", where=f"{where}.equity_daily.{ctx.prefix}")
        values = cc.require_finite_series(
            equity, "values", where=f"{where}.equity_daily.{ctx.prefix}", min_len=2
        )
        metrics = cc.require_mapping(entry, ctx.prefix, where=where)
        for label, observed, expected in (
            (f"period.{ctx.prefix}_start", p_start, start),
            (f"period.{ctx.prefix}_end", p_end, anchor),
            (f"equity_daily.{ctx.prefix}.start", e_start, start),
            (f"equity_daily.{ctx.prefix}.end", e_end, anchor),
        ):
            if observed != expected:
                out.problems.append(
                    f"{where}.{label}: {observed.isoformat()} != {expected.isoformat()} attendu — "
                    "une borne hors `[début, T]` est une erreur d'entrée, jamais tronquée (§ A.7)"
                )
        if len(values) != grid_len:
            out.problems.append(
                f"{where}.equity_daily.{ctx.prefix}.values: {len(values)} points, grille quotidienne de {grid_len}"
            )
        n_returns = cc.require_int(
            metrics, "n_daily_returns", where=f"{where}.{ctx.prefix}", minimum=0
        )
        if n_returns != len(values) - 1:
            out.problems.append(
                f"{where}.{ctx.prefix}.n_daily_returns: {n_returns} != {len(values) - 1}"
            )
        if values[0] != capital:
            out.problems.append(
                f"{where}.equity_daily.{ctx.prefix}.values[0]: {values[0]!r} != capital {capital!r}"
            )
        duration = cc.require_float(metrics, "duration_days", where=f"{where}.{ctx.prefix}")
        if duration != ctx.prefix_days:
            out.problems.append(
                f"{where}.{ctx.prefix}.duration_days: {duration!r} != {ctx.prefix_days!r} recalculé"
            )
    return out


def a04_identities(ctx: Context) -> Outcome:
    """Unicité des identités (§ A.2) et égalité stricte observations ↔ univers fermé (§ A.5)."""
    out = Outcome()
    seen: dict[str, str] = {}
    for key in ctx.observations:
        where = f"observations.{key}"
        entry = ctx.entry(key)
        identity = cc.candidate_identity(
            cc.require_str(entry, "strategy", where=where),
            cc.require_str(entry, "pair", where=where),
            cc.require_mapping(entry, "params", where=where),
        )
        if identity in seen:
            out.problems.append(
                f"{where}: identité {identity[:16]} déjà portée par {seen[identity]} (§ A.2)"
            )
        seen[identity] = key
        ctx.identities[key] = identity
    universe = {c.identity for c in ctx.manifest.candidates}
    observed = set(seen)
    for identity in sorted(observed - universe):
        out.problems.append(
            f"observations.{seen[identity]}: identité {identity[:16]} hors de l'univers fermé (§ A.5)"
        )
    for identity in sorted(universe - observed):
        out.problems.append(f"univers : identité {identity[:16]} déclarée sans observation")
    if not out.problems:
        out.notes.append(f"{len(seen)} identités, égales à l'univers")
    return out


def a05_provenance(ctx: Context) -> Outcome:
    out = Outcome()
    out.notes.append(f"provenance {ctx.manifest.provenance!r} (liste close § A.5)")
    return out


def a06_warmup(ctx: Context) -> Outcome:
    """Chaque série de décision présente au bloc d'amorçage ; `sufficient` recalculé et recoupé.

    § A.8 D2 v2.1 : la liste exportée par l'observation est recoupée, **en ensemble**, à la liste effective
    du candidat apparié (sa surcharge au manifeste, sinon la déclaration de sa stratégie) — jamais à celle
    d'un autre candidat ; un désaccord est une violation (§ I.1, ligne 15), jamais un arbitrage."""
    out = Outcome()
    for key in ctx.observations:
        where = f"observations.{key}"
        entry = ctx.entry(key)
        exported = cc.timeframe_labels(
            cc.require_sequence(entry, "decision_timeframes", where=where, min_len=1),
            ctx.manifest.timeframes,
            where=f"{where}.decision_timeframes",
        )
        matched = ctx.matched_candidate(entry, where=where)
        if matched is not None and set(exported) != set(matched.decision_timeframes):
            ctx.violations.append(
                f"{where}.decision_timeframes exportée {sorted(exported)} ≠ liste effective du "
                f"manifeste {sorted(matched.decision_timeframes)} pour ce candidat — un désaccord est "
                "une violation, jamais un arbitrage (§ A.8 D2)"
            )
        warmup = cc.require_mapping(
            cc.require_mapping(entry, "warmup", where=where), ctx.prefix, where=f"{where}.warmup"
        )
        for tf in ctx.decision_timeframes(entry, where=where):
            if tf not in warmup:
                out.problems.append(
                    f"{where}.warmup.{ctx.prefix}: série de décision {tf!r} absente"
                )
                continue
            block = cc.require_mapping(warmup, tf, where=f"{where}.warmup.{ctx.prefix}")
            recomputed, declared = cc.warmup_sufficient(
                block, where=f"{where}.warmup.{ctx.prefix}.{tf}"
            )
            if recomputed != declared:
                ctx.violations.append(
                    f"{where}.warmup.{ctx.prefix}.{tf}.sufficient déclaré {declared!r}, recalculé {recomputed!r} "
                    "— le statut recalculé fait foi"
                )
    return out


def a07_coverage(ctx: Context) -> Outcome:
    """Artefact de couverture : absent → non assertable ; présent → forme, bornes, paires, unités."""
    out = Outcome()
    if ctx.coverage_path is None:
        ctx.coverage_status = "not_provided"
        out.not_assertable.append(
            {
                "clause": "couverture (D1, § A.7)",
                "why": "artefact de couverture non fourni — aucun producteur committé ne peut le fabriquer en C3a",
            }
        )
        return out
    try:
        raw = cc.read_json(ctx.coverage_path)
    except (OSError, ValueError) as exc:
        out.problems.append(f"coverage: {exc}")
        ctx.coverage_status = "unreadable"
        return out
    ctx.coverage_status = "evaluated"
    where = "coverage"
    try:
        if not isinstance(raw, Mapping):
            raise cc.MissingEvidenceError(f"{where}: bloc attendu, reçu {type(raw).__name__}")
        window = cc.require_mapping(raw, "window", where=where)
        w_start = cc.require_datetime(window, "start", where=f"{where}.window")
        w_end = cc.require_datetime(window, "end", where=f"{where}.window")
        if (w_start, w_end) != (ctx.manifest.window_start, ctx.anchor):
            out.problems.append(
                f"{where}.window: [{w_start.isoformat()}, {w_end.isoformat()}] != "
                f"[{ctx.manifest.window_start.isoformat()}, {ctx.anchor.isoformat()}] (§ A.7)"
            )
        pairs = cc.require_mapping(raw, "pairs", where=where)
        for pair in ctx.manifest.pairs:
            if pair not in pairs:
                out.problems.append(f"{where}.pairs: paire {pair!r} de l'univers absente")
                continue
            block = cc.require_mapping(pairs, pair, where=f"{where}.pairs")
            for iv in cc.D1_INTERVALS:
                if str(iv) not in block:
                    out.problems.append(
                        f"{where}.pairs.{pair}: série {iv} absente (D1 couvre 5 min, 4 h, 1 j et 1 w)"
                    )
                    continue
                series = cc.require_mapping(block, str(iv), where=f"{where}.pairs.{pair}")
                swhere = f"{where}.pairs.{pair}.{iv}"
                cc.require_int(series, "observed", where=swhere, minimum=0)
                cc.require_int(series, "expected", where=swhere, minimum=0)
                cc.require_int(series, "covered_units", where=swhere, minimum=0)
                expected_units = cc.require_int(series, "expected_units", where=swhere, minimum=1)
                unit = cc.require_str(series, "unit", where=swhere, allowed=("day", "week"))
                cc.require_sequence(series, "missing_stamps", where=swhere)
                cc.require_float(series, "longest_gap_days", where=swhere)
                cc.require_str(series, "first_day", where=swhere)
                cc.require_str(series, "last_day", where=swhere)
                recomputed = cc.expected_units(ctx.manifest.window_start, ctx.anchor, iv)
                if expected_units != recomputed:
                    out.problems.append(
                        f"{swhere}.expected_units: {expected_units} != {recomputed} recalculé depuis les bornes"
                    )
                if unit != cc.coverage_unit(iv):
                    out.problems.append(f"{swhere}.unit: {unit!r} != {cc.coverage_unit(iv)!r}")
                # Revue R3 (b) : tout ce qui est dérivable des estampilles manquantes et des bornes
                # est recalculé et recoupé — une contradiction est un problème de couverture,
                # jamais un D1 vert par déclaration.
                out.problems.extend(
                    cc.coverage_recompute(
                        series,
                        start=ctx.manifest.window_start,
                        end=ctx.anchor,
                        interval=iv,
                        where=swhere,
                    )["problems"]
                )
    except cc.MissingEvidenceError as exc:
        out.problems.append(str(exc))
    if not out.problems:
        ctx.coverage = raw
    return out


def a08_d2(ctx: Context) -> Outcome:
    """D2 : sur la totalité → refus d'artefact (l.5) ; sur une partie → diagnostics, la chaîne continue (l.4)."""
    out = Outcome()
    failed: list[str] = []
    for key in ctx.observations:
        where = f"observations.{key}"
        entry = ctx.entry(key)
        warmup = cc.require_mapping(
            cc.require_mapping(entry, "warmup", where=where), ctx.prefix, where=f"{where}.warmup"
        )
        insufficient = [
            tf
            for tf in ctx.decision_timeframes(entry, where=where)
            if not cc.warmup_sufficient(
                cc.require_mapping(warmup, tf, where=f"{where}.warmup.{ctx.prefix}"),
                where=f"{where}.warmup.{ctx.prefix}.{tf}",
            )[0]
        ]
        if insufficient:
            failed.append(key)
            ctx.diagnostics.append(
                {
                    "key": key,
                    "identity": ctx.identities[key],
                    "clause": "D2",
                    "reason": "D_WARMUP_PREFIX",
                    "timeframes_insufficient": insufficient,
                }
            )
    total = len(ctx.observations)
    if failed and len(failed) == total:
        out.problems.append(
            f"D2 échoue sur la totalité des {total} candidats de l'artefact : refus d'artefact "
            "D_WARMUP_PREFIX, aucun classement n'est produit (§ I.1 l.5, § D.3)"
        )
    elif failed:
        out.notes.append(
            f"D2 échoue sur {len(failed)}/{total} candidats — retirés, la chaîne continue (§ I.1 l.4)"
        )
    else:
        out.notes.append(f"D2 satisfait sur les {total} candidats")
    return out


ASSERTIONS: tuple[tuple[str, str, Callable[[Context], Outcome]], ...] = (
    ("I-A.1", "forme des observations", a01_form),
    ("I-A.2", "D5 — contrats d'instrument égaux au manifeste", a02_d5),
    ("I-A.3", "bornes du préfixe exactement [début, T]", a03_bounds),
    ("I-A.4", "unicité des identités et univers fermé", a04_identities),
    ("I-A.5", "provenance de l'univers", a05_provenance),
    ("I-A.6", "amorçage du préfixe : séries de décision, sufficient recalculé", a06_warmup),
    ("I-A.7", "artefact de couverture", a07_coverage),
    ("I-A.8", "D2 — promotion en refus d'artefact sur la totalité", a08_d2),
)


def _detail(
    problems: Sequence[str], notes: Sequence[str], not_assertable: Sequence[Mapping[str, str]]
) -> str:
    parts = (
        list(problems)
        + [f"non assertable : {n['clause']} — {n['why']}" for n in not_assertable]
        + list(notes)
    )
    return " ; ".join(parts) if parts else "ok"


def run_assertions(
    ctx: Context,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, str]]]:
    """Les huit assertions dans l'ordre gelé, puis la règle de fin sur les clauses non assertables."""
    rows: list[dict[str, Any]] = []
    refusal: dict[str, Any] | None = None
    not_assertable: list[dict[str, str]] = []
    for identifier, name, check in ASSERTIONS:
        if refusal is not None:
            rows.append(
                {
                    "id": identifier,
                    "name": name,
                    "status": STATUS_SKIPPED,
                    "detail": f"non évaluée : {refusal['assertion']} a déjà échoué — sous l'ordre gelé, "
                    "toute assertion postérieure serait un faux vert",
                }
            )
            continue
        try:
            outcome = check(ctx)
        except cc.MissingEvidenceError as exc:
            outcome = Outcome(problems=[str(exc)])
        for item in outcome.not_assertable:
            not_assertable.append({"assertion": identifier, **item})
        if outcome.problems:
            status = STATUS_FAILED
            reason = "D_WARMUP_PREFIX" if identifier == "I-A.8" else "R0_INVALID_RUN"
            refusal = {
                "scope": "artefact" if identifier == "I-A.8" else "run",
                "reason": reason,
                "assertion": identifier,
                "detail": " ; ".join(outcome.problems),
            }
        elif outcome.not_assertable:
            status = STATUS_NOT_ASSERTABLE
        else:
            status = STATUS_OK
        rows.append(
            {
                "id": identifier,
                "name": name,
                "status": status,
                "detail": _detail(outcome.problems, outcome.notes, outcome.not_assertable),
            }
        )
    if refusal is None and not_assertable:
        clauses = ", ".join(n["clause"] for n in not_assertable)
        refusal = {
            "scope": "run",
            "reason": "R0_INVALID_RUN",
            "assertion": FINAL_ASSERTION,
            "detail": f"contrat non vérifiable : {len(not_assertable)} clause(s) non assertable(s) ({clauses}) — "
            "une entrée n'est validée pour sélection que si chaque clause est assertable et verte",
        }
        rows.append(
            {
                "id": FINAL_ASSERTION,
                "name": "aucune clause non assertable",
                "status": STATUS_FAILED,
                "detail": refusal["detail"],
            }
        )
    elif refusal is None:
        rows.append(
            {
                "id": FINAL_ASSERTION,
                "name": "aucune clause non assertable",
                "status": STATUS_OK,
                "detail": "ok",
            }
        )
    return rows, refusal, not_assertable


# ---------------------------------------------------------------------------
# Artefact
# ---------------------------------------------------------------------------


def build_payload(
    *,
    now: datetime,
    inputs: Mapping[str, Path],
    exit_code: int,
    violations: Sequence[str],
    manifest: cc.Manifest | None,
    anchor: datetime | None,
    observations_path: Path,
    coverage_path: Path | None,
    coverage_status: str,
    rows: Sequence[Mapping[str, Any]],
    refusal: Mapping[str, Any] | None,
    not_assertable: Sequence[Mapping[str, str]],
    diagnostics: Sequence[Mapping[str, Any]],
    n_candidates: int,
) -> dict[str, Any]:
    payload = cc.envelope(STEP, now, inputs, exit_code=exit_code, violations=violations)
    coverage_sha = (
        cc.file_sha256(coverage_path)
        if coverage_path is not None and coverage_path.exists()
        else None
    )
    payload.update(
        {
            "observations": {
                "path": str(observations_path),
                "sha256": cc.file_sha256(observations_path),
            },
            "prefix_segment": manifest.prefix_segment if manifest else None,
            "anchor": anchor.isoformat() if anchor else None,
            "window": (
                {"start": manifest.window_start.isoformat(), "end": manifest.window_end.isoformat()}
                if manifest
                else None
            ),
            "universe_provenance": manifest.provenance if manifest else None,
            "n_candidates": n_candidates,
            "assertions": list(rows),
            "not_assertable": list(not_assertable),
            "refusal": dict(refusal) if refusal else None,
            "candidate_diagnostics": list(diagnostics),
            "n_candidates_d2_failed": len(diagnostics),
            "sentence": cc.NON_RECEVABLE_SENTENCE if refusal else None,
            "coverage": {
                "path": str(coverage_path) if coverage_path is not None else None,
                "sha256": coverage_sha,
                "status": coverage_status,
            },
            "run_scope": manifest.run_scope if manifest else None,
        }
    )
    return payload


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    marks = {
        STATUS_OK: "ok  ",
        STATUS_FAILED: "FAIL",
        STATUS_SKIPPED: "--- ",
        STATUS_NOT_ASSERTABLE: "N/A ",
    }
    out = [
        f"validité d'entrée — {payload['n_candidates']} candidats, préfixe {payload['prefix_segment']!r}, T = {payload['anchor']}"
    ]
    out += [
        f"  {marks[row['status']]} {row['id']} {row['name']} : {row['detail']}"
        for row in payload["assertions"]
    ]
    if payload["invalide"]:
        out.append("ARTEFACT INVALIDE — validation non publiée")
        out += [f"  violation : {v}" for v in payload["violations"]]
    elif payload["refusal"]:
        r = payload["refusal"]
        out.append(
            f"ENTREE REFUSEE {r['reason']} (portée {r['scope']}, {r['assertion']}) — {payload['sentence']}"
        )
    else:
        out.append(
            f"entrée conforme — {payload['n_candidates_d2_failed']} candidat(s) retiré(s) par D2, la chaîne continue"
        )
    if payload["run_scope"]:
        out.append(f"portée du run : {payload['run_scope']}")
    return out


def render_markdown(payload: Mapping[str, Any]) -> str:
    words = {
        STATUS_OK: "ok",
        STATUS_FAILED: "**ÉCHEC**",
        STATUS_SKIPPED: "non évaluée",
        STATUS_NOT_ASSERTABLE: "**non assertable**",
    }
    out = [
        "# C3 — validité d'entrée (§ I-A)",
        "",
        f"généré {payload['generated_at']} · protocole {payload['protocole']['sha256'][:16]} · "
        f"observations `{payload['observations']['path']}` sha256 `{payload['observations']['sha256'][:16]}`",
        "",
        f"Préfixe `{payload['prefix_segment']}`, ancrage `{payload['anchor']}`, {payload['n_candidates']} candidats, "
        f"provenance `{payload['universe_provenance']}`.",
        "",
        "| assertion | statut | détail |",
        "|---|---|---|",
    ]
    for row in payload["assertions"]:
        out.append(f"| {row['id']} {row['name']} | {words[row['status']]} | {row['detail']} |")
    out.append("")
    if payload["invalide"]:
        out.append("**Artefact invalide** — violations :")
        out += [f"- {v}" for v in payload["violations"]]
    elif payload["refusal"]:
        r = payload["refusal"]
        out.append(
            f"**Entrée refusée** — `{r['reason']}` (portée {r['scope']}, {r['assertion']}) : {r['detail']}"
        )
        out.append("")
        out.append(f"> {payload['sentence']}")
    else:
        out.append(
            f"Entrée conforme ; {payload['n_candidates_d2_failed']} candidat(s) retiré(s) par D2 (ligne 4)."
        )
    if payload["candidate_diagnostics"]:
        out += ["", f"Diagnostics de candidats (D2) : {len(payload['candidate_diagnostics'])}", ""]
        for d in payload["candidate_diagnostics"][:200]:
            out.append(
                f"- `{d['key']}` : séries insuffisantes {', '.join(d['timeframes_insufficient'])}"
            )
    if payload["run_scope"]:
        out += ["", f"Portée du run : {payload['run_scope']}"]
    return "\n".join(out) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument(
        "--coverage",
        type=Path,
        default=None,
        help="artefact de couverture (§ A.7) ; absent = non assertable",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--now", default=None, help="Horodatage ISO UTC de generated_at, pour le déterminisme."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        print(f"--now: {exc}", file=sys.stderr)
        return 2
    raws: dict[str, Any] = {}
    for name in ("manifest", "anchor", "observations"):
        try:
            raws[name] = cc.read_json(getattr(args, name))
        except (OSError, ValueError) as exc:
            print(f"--{name}: {exc}", file=sys.stderr)
            return 2
    inputs: dict[str, Path] = {
        "manifest": args.manifest,
        "anchor": args.anchor,
        "observations": args.observations,
    }
    if args.coverage is not None and Path(args.coverage).exists():
        inputs["coverage"] = args.coverage

    violations: list[str] = []
    manifest: cc.Manifest | None = None
    anchor: datetime | None = None
    rows: list[dict[str, Any]] = []
    refusal: dict[str, Any] | None = None
    not_assertable: list[dict[str, str]] = []
    diagnostics: list[dict[str, Any]] = []
    coverage_status = "not_provided" if args.coverage is None else "not_evaluated"
    n_candidates = len(raws["observations"]) if isinstance(raws["observations"], Mapping) else 0
    try:
        manifest = cc.load_manifest(raws["manifest"])
        cc.require_upstream_ok(raws["anchor"], where="anchor")
        violations += cc.check_inputs_match(
            raws["anchor"], {"manifest": args.manifest}, where="anchor"
        )
        anchor = manifest.anchor()
        declared = cc.require_datetime(raws["anchor"], "anchor", where="anchor")
        if declared != anchor:
            violations.append(
                f"anchor.anchor déclaré {declared.isoformat()}, recalculé {anchor.isoformat()} — le recalcul fait foi"
            )
        declared_provenance = cc.require_str(
            raws["anchor"], "universe_provenance", where="anchor", allowed=cc.PROVENANCES
        )
        if declared_provenance != manifest.provenance:
            violations.append(
                f"anchor.universe_provenance {declared_provenance!r} != manifeste {manifest.provenance!r}"
            )
        ctx = Context(
            manifest=manifest,
            anchor=anchor,
            prefix_days=(anchor - manifest.window_start).total_seconds() / 86400.0,
            observations=raws["observations"],
            coverage_path=args.coverage,
            violations=violations,
        )
        rows, refusal, not_assertable = run_assertions(ctx)
        diagnostics = ctx.diagnostics
        coverage_status = ctx.coverage_status
    except cc.EntryRefusedError as exc:
        refusal = {"scope": "run", "reason": exc.reason, "assertion": "I-A.0", "detail": str(exc)}
    except cc.MissingEvidenceError as exc:
        refusal = {
            "scope": "run",
            "reason": "R0_INVALID_RUN",
            "assertion": "I-A.0",
            "detail": f"entrées de l'étape : {exc}",
        }
    except (cc.InvalidValueError, cc.NonFiniteValueError) as exc:
        # Non fini fourni (§ F.7) ou atteignant la canonicalisation : violation, code 1 (revue R3 d).
        violations.append(str(exc))

    exit_code = 1 if violations else (2 if refusal else 0)
    payload = build_payload(
        now=now,
        inputs=inputs,
        exit_code=exit_code,
        violations=violations,
        manifest=manifest,
        anchor=anchor,
        observations_path=args.observations,
        coverage_path=args.coverage,
        coverage_status=coverage_status,
        rows=rows,
        refusal=refusal,
        not_assertable=not_assertable,
        diagnostics=diagnostics,
        n_candidates=n_candidates,
    )
    digest = cc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    if args.markdown is not None:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(payload), encoding="utf-8")
        print(f"written {args.markdown}")
    for violation in violations:
        print(f"VIOLATION {violation}", file=sys.stderr)
    if refusal is not None and not violations:
        print(f"ENTREE REFUSEE {refusal['reason']}: {refusal['detail']}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
