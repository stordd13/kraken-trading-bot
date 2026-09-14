# `pair_costs_b4.json` — PLACEHOLDER (valeurs au summary q3)

Statut : **placeholder** créé au GATE B (2026-09-14). Les trois paires portent les globaux du modèle Bybit
(spread 0.02 % / slippage 0.02 %) **uniquement pour que le fichier soit chargeable** ; les valeurs réelles
viennent du summary q3 de Bruno (mesures diurnes + nocturnes 01:00-03:00 UTC), arrondies au conservateur
(règle proposée : `results/B4_3_gate_b_configs.md` § 1). **Aucun run de campagne avec ce fichier tant que le
GATE B n'est pas validé valeurs incluses.**

Format (`scripts/backtest.py::load_pair_costs`) : un objet par paire, exactement les clés `spread` et
`slippage`, fractions décimales en chaînes. Appliqué aux fills market du moteur signal et à la liquidation
terminale du grid (`--pair-costs-file`), jamais aux fills maker. Le harnais `verify-fees` lit ces valeurs
depuis le dump (`pair_costs`) pour la paire du run.
