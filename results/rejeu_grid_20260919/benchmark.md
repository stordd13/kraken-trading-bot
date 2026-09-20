# Rejeu diagnostic grid — benchmark reconstruit (§ E)

généré 2026-09-20T10:26:04+00:00 · base_sha 9897803f48a6537a248f5a41c53a1ea5522d46a0 · prespec 20079aff60a55152

Fenêtre 2023-04-01T00:00:00+00:00 → 2026-04-01T00:00:00+00:00, données binance (interval 1440), modèle de fees bybit, capital 1000 USDC, rf 0.

Bornes `>= start` et `<= end` (convention des moteurs, répare la dette 15(c)) ; entrée au close stampé à l'ancre, une liquidation terminale stampée à `end` comme le grid. `entry_price` / `exit_price` sont les prix **exécutés** (close ± spread + slippage) ; le taker est facturé sur le notionnel, séparément.

| paire | constructible | comparable | entrée | sortie | rendement % | MDD_daily % | CAGR %/an | Sharpe | Sortino | Calmar | sigma_daily | n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USDC | True | True | 28483.878996 | 68212.863936 | 138.28 | 49.65 | 33.5313 | 0.8493 | 1.2910 | 0.6753 | 0.024595 | 1096 |
| SOL/USDC | False | False | — | — | — | — | — | — | — | — | — | — |

## Comparabilité (§ E.4)

| paire | ff_days | ff_ok | bougie à start | bougie à end | n_daily_returns | tous finis | min > -0.5 | crosscheck écarts / vérifiés | comparable |
|---|---|---|---|---|---|---|---|---|---|
| BTC/USDC | 0 | True | True | True | True | True | True | 0 / 1095 | True |
| SOL/USDC | 271 | False | False | True | False | False | False | 0 / 824 | False |

Le recoupement de minuit (close 5 m vs close 1 d, end-stamping B4.1) est **rapporté, non bloquant** : la série 1 d fait foi pour le benchmark.

## Descripteurs historiques (§ E.1) — descriptifs, jamais un seuil

| paire | source | Sharpe hist. | Δ Sharpe | MDD_daily hist. % | Δ MDD | rendement hist. % | Δ rendement | n hist. |
|---|---|---|---|---|---|---|---|---|
| BTC/USDC | results/C1_benchmarks_v2.json | 0.8470 | +0.0023 | 49.65 | +0.00 | 137.51 | +0.77 | 1096 |
| SOL/USDC | results/C1_benchmarks_v2.json | 0.2954 | — | 70.23 | — | -20.43 | — | 824 |

**SOL/USDC** — first candle stamped 2023-12-29T00:00:00+00:00 is 272.0 days after start (> 24 h); re-anchoring to a later date is forbidden (§ E.2)
