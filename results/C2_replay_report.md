# C2 — Fidélité du replay : rapport (avant/après, preuves, constats)

> Brief : `agent/chantier2_replay_v2.md` (v2.1). Plan approuvé le 2026-09-17 (Bruno) après revue adversariale.
> Branche `feat/c2-replay` depuis `dev` @ `a07eb73` (src/scripts/tests identiques au tag `v2.9.0-c1-metrics` @ `51be3e8`).
> **Ce rapport ne porte aucun verdict économique** : les écarts avant/après sont attribués aux correctifs R1-R4 ;
> le verdict appartient au rejeu diagnostic grid (phase suivante) sous protocole C3.
>
> État : **en cours** (étape 0).

## 0. Étape 0 — baselines et références « avant » (tag `v2.9.0-c1-metrics`)

- `mypy src/` à `a07eb73` : **65 erreurs / 18 fichiers** (C1 en consignait 64 ; baseline constatée, à ne pas dépasser).
- `pytest -q` à `a07eb73` (tunnel actif) : _(à consigner)_.
- Références C1 en place (sha256 16) : `c1_ab/signal_A_bybit_new.json` `c8e5832e17446caa`, `grid_quick_binance_new.json`
  `bf6d492129fc5aa3`, `grid_quick_bybit_new.json` `04d109094a388d2f` (= `results/C1_metrics_report.md` § 3).
- Worktree `~/wt-c1-ref` = `51be3e8` (tag). Captures « avant » faites **avant tout commit touchant `src/`**
  (`c1_equity_probe.py capture --engine-root ~/wt-c1-ref` ne substitue que `scripts/backtest.py` : `krakenbot` est importé
  depuis `src/` du tree courant, identique au tag à ce stade — `git diff --stat v2.9.0-c1-metrics..a07eb73 -- src scripts tests` vide).

| Capture (`results/c2_ab/`) | Commande | sha256 (16) |
|---|---|---|
| `signal_A_bybit_ref.json` | `grok_supertrend_4h BTC/USDC --exchange binance --start-date 2023-04-01 --end-date 2026-04-01 --interval 5 --capital 1000 --fees bybit` | `3e1317167d9861fe` (92 trades, 6 577 points, `net_pnl` 19.314423 = C1) |
| `grid_quick_binance_ref.json` | `grok_grid_atr_adaptive_v4 BTC/USDC … 2025-03-01 → 2025-03-15 --fees binance` | `c1b3e1e7b6032501` (90 trades, 4 034 points, `net_pnl` 1.520224 = C1) |
| `grid_quick_bybit_ref.json` | idem `--fees bybit` | `d8a59dad6bf2a8e2` (90 trades, `net_pnl` 0.654538 = C1) |
| `grid_A_bybit_ref.json.gz` (non versionné) | `grok_grid_atr_adaptive_v4 BTC/USDC … 2023-04-01 → 2026-04-01 --fees bybit` | fichier gz `68a5eb1cd21ac335`, texte canonique `b18d523d4b876a59` (2 128 trades, 315 650 points, `net_pnl` 114.206947 = C1) |
| `dca_2022_bybit_ref.json` | `grok_adaptive_dca_weekly BTC/USDC … 2022-01-01 → 2022-09-28 --fees bybit --min-order-usdc 5` | `50cdf06a20a72d58` (36 achats, 271 points, return −16.46 %, `net_pnl` −0.495 = −Σ fees d'achat) |

Empreintes des sources exécutées côté « avant » (sha256 16, identiques dans le worktree du tag et dans l'arbre à ce stade) :
`scripts/backtest.py` `a82a485a4fe1e3fb`, `grok_grid_atr_adaptive_v4.py` `f220f15738ed2f95`, `grok_supertrend_4h.py` `815ba42b06c0ab2f`,
`grok_adaptive_dca_weekly.py` `6da1b07d7f2942fd`. Captures faites du 2026-09-17 06:38 au 06:46 UTC, avant tout commit de code.

## 1. Défauts → correctifs

_(R1 séries/décision/exécution · R2 préenregistrement + warmup en bougies · R3 compteurs · R4 appariement par id · N1 `--cross-validate` × grid refusé · provenance `replay_version`)_

## 2. Preuves

_(1 harnais indicateurs + ordre temporel · 2 lazy 8/8 · 3 compteurs · 4 appariement + rejeu P6 grids · 5 invariant strict SuperTrend A · 6 avant/après · 7 suite)_

## 3. Avant / après (sans verdict)

## 4. Constat rétroactif (préenregistrement × grilles P7)

## 5. Identifiants lots ↔ callback : non-correspondance documentée (hors périmètre → test dette 13 élargi)

## 6. Découvertes annexes (signalées, non traitées)

## 7. Gold hashes (re-baseline soumis à review)
