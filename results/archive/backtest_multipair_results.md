# Backtest Multi-Pair — ETH/USDC + SOL/USDC Results

**Date**: 2026-03-01
**Pairs**: ETH/USDC (8.5 ans, 2017-08-17 → 2026-03-01), SOL/USDC (5.5 ans, 2020-08-11 → 2026-03-01)
**Capital initial**: 1 000 USDC par test
**Fees**: maker 0.16%, taker 0.26%, spread 0.02%, slippage 0.01%
**Execution**: Next-bar model (signal on candle N, fill at open N+1)
**Data source**: Binance USDT pairs (ETH/USDT, SOL/USDT) stockees comme ETH/USDC, SOL/USDC

---

## Tableau Comparatif (BTC vs ETH vs SOL)

| Strategie | Pair | Periode | Return | Sharpe | PF | WR | Trades | MaxDD% | Verdict |
|-----------|------|---------|--------|--------|------|-------|--------|--------|---------|
| **SuperTrend 4h** | BTC | 9 ans | +20.6% | **0.49** | **2.81** | 49.5% | 107 | 2.4% | KEEP |
| | ETH | 8.5 ans | **+72.0%** | 0.35 | 1.97 | 39.1% | 110 | 11.6% | KEEP |
| | SOL | 5.5 ans | **+94.4%** | **0.41** | **2.57** | 43.7% | 71 | 11.9% | KEEP |
| **EMA Cross 4h** | BTC | 9 ans | +3.6% | 0.23 | 2.68 | 37.0% | 27 | 1.6% | WATCH |
| | ETH | 8.5 ans | +8.2% | **0.28** | 2.17 | 35.1% | 57 | 3.9% | WATCH |
| | SOL | 5.5 ans | +3.3% | 0.15 | 1.79 | 25.7% | 35 | 3.0% | WATCH |
| **Donchian 4h** | BTC | 9 ans | +11.3% | **0.32** | **1.92** | — | — | 2.9% | WATCH |
| | ETH | 8.5 ans | +5.4% | 0.12 | 1.30 | 29.6% | 132 | 7.1% | KILL |
| | SOL | 5.5 ans | +12.9% | 0.28 | 1.87 | 32.1% | 78 | 5.2% | WATCH |
| **DCA Weekly** | BTC | 9 ans | **+802.6%** | **0.74** | — | — | 67 buys | 49.5% | KEEP |
| | ETH | 8.5 ans | -0.0% | 0.16 | — | — | 0 | 14.6% | BUG |
| | SOL | 5.5 ans | -0.0% | 0.35 | — | — | 0 | 53.4% | BUG |

**Criteres** : Sharpe > 0.3, PF > 1.5, MaxDD < 25%

**Notes methodologiques** :
- BTC SuperTrend backteste avec `order_size_usdc=50` (Phase 1A), ETH/SOL avec `order_size_usdc=200` (strategies.yaml actuel). Sharpe et PF sont comparables (scale-invariant), mais Return% et MaxDD% ne sont pas directement comparables entre BTC et ETH/SOL.
- BTC EMA Cross backteste avec EMA 27/125 (Phase 1A), ETH/SOL avec EMA 20/50 (strategies.yaml actuel). Comparaison approximative.
- BTC Donchian : donnees Phase 1B (trade count et WR non disponibles dans le rapport sauvegarde).

---

## Buy & Hold Reference

| Pair | Prix debut | Prix fin | Return | Periode |
|------|-----------|---------|--------|---------|
| **BTC** | 4 505 USDC | 63 259 USDC | **+1 304.2%** | 9 ans (2017-09 → 2026-02) |
| **ETH** | 302 USDC | 1 994 USDC | **+560.3%** | 8.5 ans (2017-08 → 2026-03) |
| **SOL** | 3.30 USDC | 85.77 USDC | **+2 499.7%** | 5.5 ans (2020-08 → 2026-03) |

> Aucune strategie signal-based ne bat le buy-and-hold. C'est attendu : elles deploient 5-20% du capital par trade, pas 100%. Leur valeur est dans le risk-adjusted return (Sharpe, MaxDD).

---

## Resultats Detailles

### 1. SuperTrend 4h — MULTI-PAIR VIABLE

La star du portfolio. Profitable sur les 3 pairs avec un excellent ratio gain/perte.

#### ETH/USDC (8.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-08-17 → 2026-03-01 |
| Balance finale | 1 720.00 USDC |
| Return | **+72.00%** |
| Net P&L | +693.32 USDC |
| Trades | 110 |
| Win rate | 39.09% |
| Avg win / Avg loss | +35.63 / -11.60 USDC |
| Profit factor | 1.97 |
| Avg holding | ~8 jours |
| Max drawdown | 11.56% |
| Sharpe / Sortino | 0.35 / 0.51 |

#### SOL/USDC (5.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2020-08-11 → 2026-03-01 |
| Balance finale | 1 943.71 USDC |
| Return | **+94.37%** |
| Net P&L | +907.51 USDC |
| Trades | 71 |
| Win rate | 43.66% |
| Avg win / Avg loss | +51.00 / -15.36 USDC |
| Profit factor | 2.57 |
| Avg holding | ~8 jours |
| Max drawdown | 11.94% |
| Sharpe / Sortino | 0.41 / 0.61 |

#### Analyse cross-pair SuperTrend

- **Universelle** : fonctionne sur BTC, ETH, et SOL avec des Sharpe > 0.3 partout
- Les returns absolus sont plus eleves sur ETH/SOL car `order_size_usdc=200` (vs 50 sur BTC Phase 1A)
- Le PF est meilleur sur SOL (2.57) que ETH (1.97) — SOL a des trends plus nets
- Le MaxDD est plus eleve sur ETH/SOL (~12% vs 2.4% BTC) — position 4× plus grosse + altcoins plus volatils
- Le nombre de trades est similaire (~70-110 sur toutes les pairs) — frequence de signaux stable

---

### 2. EMA Cross 4h (20/50) — MULTI-PAIR MARGINAL

Faiblement profitable sur toutes les pairs, mais trop conservatrice.

#### ETH/USDC (8.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-08-17 → 2026-03-01 |
| Balance finale | 1 082.44 USDC |
| Return | +8.24% |
| Net P&L | +76.28 USDC |
| Trades | 57 |
| Win rate | 35.09% |
| Avg win / Avg loss | +7.98 / -1.99 USDC |
| Profit factor | 2.17 |
| Avg holding | 125h 41min |
| Max drawdown | 3.85% |
| Sharpe / Sortino | 0.28 / 0.39 |

#### SOL/USDC (5.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2020-08-11 → 2026-03-01 |
| Balance finale | 1 032.65 USDC |
| Return | +3.27% |
| Net P&L | +28.92 USDC |
| Trades | 35 |
| Win rate | 25.71% |
| Avg win / Avg loss | +8.80 / -1.70 USDC |
| Profit factor | 1.79 |
| Avg holding | 106h 10min |
| Max drawdown | 2.97% |
| Sharpe / Sortino | 0.15 / 0.23 |

#### Analyse cross-pair EMA Cross

- **Profitable partout** mais Sharpe < 0.3 sur toutes les pairs (max 0.28 sur ETH)
- Le WR chute sur SOL (25.7%) vs ETH (35.1%) — SOL a plus de faux signaux
- PF correct partout (1.79-2.68) — les gains compensent les pertes malgre le faible WR
- MaxDD tres faible (< 4%) — la strategie est ultra-conservatrice (`order_size_usdc=40`)
- Plus de trades sur ETH (57) et SOL (35) qu'en BTC (27) — les EMAs 20/50 croisent plus souvent sur altcoins
- **Verdict** : utilisable comme "filet de securite" a faible risque, mais ne justifie pas seule le multi-pair

---

### 3. Donchian Breakout 4h — SOL OK, ETH FAIBLE

#### ETH/USDC (8.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-08-17 → 2026-03-01 |
| Balance finale | 1 054.37 USDC |
| Return | +5.44% |
| Net P&L | +37.03 USDC |
| Trades | 132 |
| Win rate | 29.55% |
| Avg win / Avg loss | +7.28 / -2.35 USDC |
| Profit factor | 1.30 |
| Avg holding | 104h 36min |
| Max drawdown | 7.06% |
| Sharpe / Sortino | 0.12 / 0.17 |

#### SOL/USDC (5.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2020-08-11 → 2026-03-01 |
| Balance finale | 1 128.71 USDC |
| Return | +12.87% |
| Net P&L | +118.21 USDC |
| Trades | 78 |
| Win rate | 32.05% |
| Avg win / Avg loss | +11.59 / -2.92 USDC |
| Profit factor | 1.87 |
| Avg holding | 95h 4min |
| Max drawdown | 5.20% |
| Sharpe / Sortino | 0.28 / 0.44 |

#### Analyse cross-pair Donchian

- **SOL** : quasi identique a BTC (Sharpe 0.28 vs 0.32, PF 1.87 vs 1.92). SOL trend-followe bien.
- **ETH** : nettement plus faible (Sharpe 0.12, PF 1.30). ETH genere trop de faux breakouts (132 trades vs 78 SOL).
- La strategie fonctionne mieux sur les actifs a "trends nets" (BTC, SOL) que sur ETH qui est plus range-bound.
- **Verdict** : activable sur SOL, pas sur ETH.

---

### 4. DCA Weekly — BUG : 0 TRADES SUR ETH/SOL

#### ETH/USDC (8.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-08-17 → 2026-03-01 |
| Balance finale | 999.98 USDC |
| Return | -0.00% |
| Trades | **0** |
| Max drawdown | 14.62% |
| Sharpe | 0.16 |

#### SOL/USDC (5.5 ans)

| Metrique | Valeur |
|----------|--------|
| Periode | 2020-08-11 → 2026-03-01 |
| Balance finale | 999.98 USDC |
| Return | -0.00% |
| Trades | **0** |
| Max drawdown | 53.35% |
| Sharpe | 0.35 |

#### Analyse

**BUG DETECTE** : La strategie DCA Weekly ne genere aucun signal BUY sur ETH/USDC et SOL/USDC (0 trades). Sur BTC, elle genere 67 achats pour +802.57%.

Cause probable : la strategie utilise un calendrier hebdomadaire ou des conditions d'entree qui referencent des parametres BTC-specifiques. A investiguer dans `grok_adaptive_dca_weekly.py`.

Les metriques Sharpe/MaxDD affichees proviennent probablement du buy-and-hold reference calcule en interne, pas de la strategie elle-meme (qui n'a fait aucun trade).

**Action requise** : debugger `grok_adaptive_dca_weekly` pour identifier pourquoi `generate_signal()` ne retourne jamais BUY sur non-BTC pairs. Probable cause : verification du pair name ou condition d'entree trop restrictive.

---

## Synthese Multi-Pair

### Tableau recapitulatif des verdicts

| Strategie | BTC | ETH | SOL | Multi-pair viable ? |
|-----------|-----|-----|-----|---------------------|
| **SuperTrend 4h** | KEEP | KEEP | KEEP | **OUI** — universelle |
| **EMA Cross 4h** | WATCH | WATCH | WATCH | NON — Sharpe < 0.3 partout |
| **Donchian 4h** | WATCH | KILL | WATCH | PARTIEL — SOL seulement |
| **DCA Weekly** | KEEP | BUG | BUG | **A DEBUGGER** |

### Analyse cross-pair

1. **SuperTrend 4h est universelle** : c'est la seule strategie signal-based qui passe les criteres (Sharpe > 0.3, PF > 1.5) sur les 3 pairs. Elle fonctionne mieux sur les actifs avec des tendances claires. SOL > ETH en termes de PF.

2. **EMA Cross est trop conservative** : malgre un drawdown minime, elle ne genere pas assez de profit pour justifier le multi-pair. Le Sharpe plafonne a 0.28 (ETH). Position size trop petite (40 USDC = 4% du capital).

3. **Donchian est pair-dependante** : excellente sur SOL (trends nets), mediocre sur ETH (trop de faux breakouts). Les breakout strategies fonctionnent mieux sur les actifs a forte directionnalite.

4. **DCA est cassee sur altcoins** : bug a corriger. Si le DCA fonctionne correctement, il devrait etre universel par nature (achat periodique, independant du pair).

### Portfolio multi-pair optimal (recommandation)

**Phase 1 — Activation immediate** :
- SuperTrend 4h sur **BTC + ETH + SOL** = 3 instances en parallele
- Capital par pair : 1 000 USDC → 3 000 USDC total
- Expected combined Sharpe : ~0.42 (moyenne ponderee) avec decorrelation partielle entre pairs

**Phase 2 — Apres debug DCA** :
- Ajouter DCA Weekly sur **BTC + ETH + SOL** (accumulation long-terme)
- Capital DCA : 15 USDC/semaine/pair = 45 USDC/semaine total

**Phase 3 — Optionnel** :
- Ajouter Donchian Breakout 4h sur **SOL uniquement** (Sharpe 0.28, proche du seuil)
- Ne PAS activer Donchian sur ETH (Sharpe 0.12)

---

## Actions Prioritaires

1. **Debugger DCA Weekly** : investiguer pourquoi 0 trades sur ETH/SOL dans `grok_adaptive_dca_weekly.py`
2. **Re-backtester BTC** avec les memes parametres actuels (`order_size_usdc=200` pour SuperTrend) pour avoir une comparaison Return/MaxDD homogene
3. **Paper trading** : activer SuperTrend 4h sur ETH/USDC et SOL/USDC dans `strategies.yaml` (paper mode, 2 semaines minimum)
4. **Monitorer la correlation** : si BTC/ETH/SOL bougent ensemble (ce qui est frequent), le multi-pair n'apporte pas de diversification reelle. Mesurer la correlation des signaux en paper trading.

---

*Rapport genere automatiquement. Donnees OHLC via Binance (USDT pairs). BTC reference : Phase 1A/1B. Tous les backtests utilisent des fees realistes (maker 0.16%, taker 0.26%) et le modele d'execution next-bar.*
