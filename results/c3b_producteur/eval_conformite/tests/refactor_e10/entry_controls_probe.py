"""C3b lot 4a, commit A — sonde d'identité de l'extraction E10 (``passed_params_problems`` hors d'``entry_controls``).

Imprime, en JSON trié, la sortie de ``c3b_common.entry_controls`` sur des entrées fixes qui exercent les deux branches
du contrôle E10 (bloc absent ou sans ``passed_params``, divergence) et le cas conforme, puis le sha256 de ce texte.
Lancée avant l'extraction (``4d5eb46``) puis après : les deux sorties doivent être identiques au bit.

Usage (depuis la racine du dépôt) ::

    poetry run python results/c3b_producteur/eval_conformite/tests/refactor_e10/entry_controls_probe.py
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
for sub in ("", "src", "scripts", "scripts/audit", "tests"):
    sys.path.insert(0, str(ROOT / sub))

import c3b_common as c3bc  # noqa: E402
from test_scripts import test_c3b_common as pc  # noqa: E402


def main() -> None:
    manifest = pc.loaded(pc.producer_manifest(classes=("C1", "C2")))
    anchor = manifest.anchor()
    candidate = next(c for c in manifest.candidates if c.pair == "BTC/USDT")
    summary, trades = pc.engine_like_liquidation(
        [(Decimal("0.001"), Decimal("95000"))], stamp=anchor
    )
    block = c3bc.liquidation_block(summary, trades)
    params = dict(candidate.params)
    passed = {**params, "pair": candidate.pair}
    cases: dict[str, Any] = {
        "conforme": {"passed_params": passed},
        "bloc_absent": None,
        "bloc_non_mapping": ["passed_params"],
        "sans_passed_params": {"other": 1},
        "divergence_cle_en_plus": {"passed_params": {**passed, "atr_period": 21}},
        "divergence_paire": {"passed_params": {**params, "pair": "ETH/USDT"}},
    }
    out: dict[str, list[str]] = {}
    for name, effective in cases.items():
        entry = {
            "strategy": candidate.strategy,
            "pair": candidate.pair,
            "params": params,
            "effective_params": effective,
            "liquidation": {manifest.prefix_segment: block},
        }
        out[name] = c3bc.entry_controls(entry, manifest=manifest, anchor=anchor)
    text = json.dumps(out, sort_keys=True, indent=2, ensure_ascii=False)
    print(text)
    print("sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main()
