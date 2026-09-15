# `pair_costs_b4.json` — coûts par paire de la campagne B4.3 (GO GATE B, 2026-09-15)

| Paire | spread | slippage | Dérivation (`results/q3_orderbook.jsonl`, 42 mesures/paire du 14/09 10:46 au 15/09 06:47 UTC, 10 nocturnes) |
|---|---|---|---|
| BTC/USDC | 0.0002 | 0.0002 | p75 global 1.8 bps / p75 nocturne 0.15 bps → max = 1.8 → **2 bps** (bp supérieur) ; slippage mesuré 1k USDC = 0 → plancher global 2 bps |
| ETH/USDC | 0.0003 | 0.0002 | p75 global 2.8 bps / nocturne 0.16 → **3 bps** ; slippage 0 → 2 bps |
| SOL/USDC | 0.0011 | 0.0002 | p75 global 8.7 bps / nocturne 10.8 → max = 10.8 → **11 bps** ; slippage 0 → 2 bps |

Règle (amendée au GO B par rapport à la proposition « p75 nocturne » du GATE B) :
`spread = ceil_bp(max(p75 global, p75 nocturne 00–05 UTC))`, `slippage = max(2 bps, p75 slippage mesuré)`.
Motif de l'amendement : le spread est piloté par la volatilité et non par l'heure (soirée du 14/09 : ETH 0.124 %) —
l'amendement est strictement conservateur (ne peut que relever les valeurs).

Format (`scripts/backtest.py::load_pair_costs`) : un objet par paire, exactement les clés `spread` et `slippage`,
fractions décimales en chaînes. Appliqué aux fills market du moteur signal, à la liquidation terminale du grid
(`--pair-costs-file`) et à l'entrée market du benchmark Buy & Hold ; jamais aux fills maker. Le harnais `verify-fees`
lit ces valeurs depuis le dump (`pair_costs`) pour la paire du run ; les runners enregistrent le fichier et les valeurs
appliquées dans chaque entrée de résultat et refusent une reprise sous d'autres coûts.
