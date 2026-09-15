"""B4.3 campaign flag rule (GO GATE A, point 2) — shared by the P6/P7 report generators.

Any grid run whose terminal-liquidation block shows an inventory divergence
(``inventory_divergence_btc`` or ``residual_net_proceeds`` beyond Decimal dust) or whose
realised-cash ``net_pnl`` differs from the lot-basis figure (``net_pnl_lot_basis``) is flagged
BY NAME (strategy × pair × config × segment) in the B4 report. The runners persist the
``liquidation`` block per segment (P6: train/test/all; P7: train/test[/all]; walk-forward: per
window); this module only reads it.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

DUST_BTC = Decimal("1e-12")
NET_PNL_TOL = Decimal("1e-9")  # metrics are floats; the Decimal identity holds to ~1e-13

ZERO = Decimal("0")


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def flag_segment(liquidation: dict[str, Any] | None, metrics: dict[str, Any] | None) -> list[str]:
    """Human-readable reasons for which one segment must be flagged (empty = clean)."""
    if not liquidation:
        return []
    reasons: list[str] = []
    residual = _dec(liquidation.get("residual_net_proceeds"))
    if residual is not None and residual != ZERO:
        reasons.append(f"residual proceeds {residual} USDC without a lot")
    residual_btc = _dec(liquidation.get("residual_trade_btc"))
    if residual_btc is not None and residual_btc != ZERO:
        reasons.append(f"residual liquidation {residual_btc} BTC")
    divergence = _dec(liquidation.get("inventory_divergence_btc"))
    if divergence is not None and abs(divergence) > DUST_BTC:
        reasons.append(f"inventory divergence {divergence} BTC")
    dust = _dec(liquidation.get("dust_written_off_btc"))
    if dust is not None and abs(dust) > DUST_BTC:
        reasons.append(f"dust write-off {dust} BTC above tolerance")
    lot_basis = _dec(liquidation.get("net_pnl_lot_basis"))
    net_pnl = _dec((metrics or {}).get("net_pnl"))
    if lot_basis is not None and net_pnl is not None and abs(net_pnl - lot_basis) > NET_PNL_TOL:
        reasons.append(f"net_pnl {net_pnl} != lot basis {lot_basis} (formula vs cash)")
    return reasons


def flag_entry(name: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Flags of one runner entry (P6 / P7 shape: ``liquidation`` and metrics per segment)."""
    liquidation = entry.get("liquidation") or {}
    flags: list[dict[str, Any]] = []
    for segment, block in liquidation.items():
        reasons = flag_segment(block, entry.get(segment))
        if reasons:
            flags.append(
                {
                    "run": name,
                    "strategy": entry.get("strategy"),
                    "pair": entry.get("pair"),
                    "params": entry.get("params"),
                    "segment": segment,
                    "reasons": reasons,
                }
            )
    return flags


def flag_walkforward_entry(name: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Flags of one walk-forward entry (``windows[i].liquidation`` / ``windows[i].metrics``)."""
    flags: list[dict[str, Any]] = []
    for window in entry.get("windows") or []:
        reasons = flag_segment(window.get("liquidation"), window.get("metrics"))
        if reasons:
            flags.append(
                {
                    "run": name,
                    "strategy": entry.get("strategy"),
                    "pair": entry.get("pair"),
                    "params": entry.get("params"),
                    "segment": f"window {window.get('window')}",
                    "reasons": reasons,
                }
            )
    return flags


def collect_flags(results: dict[str, Any], *, walkforward: bool = False) -> list[dict[str, Any]]:
    """Flags over a whole results file (P6 phase D, P7 phase 1/2, or walk-forward)."""
    flags: list[dict[str, Any]] = []
    for name, entry in results.items():
        if not isinstance(entry, dict) or "error" in entry:
            continue
        flags.extend(
            flag_walkforward_entry(name, entry) if walkforward else flag_entry(name, entry)
        )
    return flags


def render_flags_markdown(flags: list[dict[str, Any]], title: str = "Flagged runs") -> list[str]:
    """Markdown block listing the flagged runs by name (or the explicit 'none' line)."""
    lines = [f"## {title} (inventory divergence / formula vs cash)", ""]
    if not flags:
        lines.append(
            "_No run flagged: every grid liquidation reconciled (residual 0, divergence within "
            "Decimal dust, net_pnl == lot basis)._"
        )
        lines.append("")
        return lines
    lines.append("| Run | Strategy | Pair | Segment | Params | Reasons |")
    lines.append("|---|---|---|---|---|---|")
    for f in flags:
        params = f.get("params")
        params_str = ", ".join(f"{k}={v}" for k, v in sorted((params or {}).items())) or "-"
        lines.append(
            f"| `{f['run']}` | {f['strategy']} | {f['pair']} | {f['segment']} | "
            f"{params_str} | {'; '.join(f['reasons'])} |"
        )
    lines.append("")
    return lines
