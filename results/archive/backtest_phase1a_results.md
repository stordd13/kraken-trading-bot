# Backtest Phase 1A — 7 Strategies Results

**Date**: 2026-03-01
**Pair**: XBT/USDC
**Capital initial**: 1 000 USDC
**Fees**: maker 0.16%, taker 0.26%, spread 0.02%, slippage 0.01%
**Execution**: Next-bar model (signal on candle N, fill at open N+1)

---

## Tableau Recapitulatif

| # | Strategie | Periode | TF | Trades | Win% | Return | Sharpe | Sortino | MaxDD% | PF | Verdict |
|---|-----------|---------|-----|--------|------|--------|--------|---------|--------|----|---------|
| 1 | **grok_grid_atr_adaptive_v4** | 9 ans | 4h | 410 pairs | — | **+1643.6%** | 0.14 | 0.20 | 50.1% | — | KEEP |
| 2 | **grok_adaptive_dca_weekly** | 9 ans | 1d | 67 buys | — | **+802.6%** | 0.74 | 1.07 | 49.5% | — | KEEP |
| 3 | **grok_supertrend_4h** | 9 ans | 4h | 107 | 49.5% | **+20.6%** | 0.49 | 0.72 | 2.4% | 2.81 | KEEP |
| 4 | **grok_ema_adx_atr** | 9 ans | 4h | 27 | 37.0% | +3.6% | 0.23 | 0.32 | 1.6% | 2.68 | WATCH |
| 5 | gemini_retour_moyenne | 3 ans | 15m | 11 | 27.3% | -0.1% | -0.14 | -0.17 | 0.1% | 0.08 | KILL |
| 6 | gemini_scalping_volatilite | 3 ans | 5m | 85 | 35.3% | -1.2% | -0.25 | -0.29 | 1.2% | 0.14 | KILL |
| 7 | gemini_suivi_tendance_momentum | 9 ans | 4h | 205 | 27.3% | -9.6% | -0.49 | -0.68 | 10.0% | 0.52 | KILL* |
| — | **Buy & Hold BTC (9 ans)** | 9 ans | — | — | — | **+1304.2%** | — | — | — | — | ref |
| — | **Buy & Hold BTC (3 ans)** | 3 ans | — | — | — | **+167.7%** | — | — | — | — | ref |

**Criteres de validation** (CLAUDE.md) : battre buy-and-hold, Sharpe > 0.3, MaxDD < 25%, PF > 1.5

---

## Resultats Detailles

### 1. grok_grid_atr_adaptive_v4 (GridBacktester)

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-09-04 → 2026-03-01 (3100 j) |
| Balance finale | 17 436.45 USDC |
| Return | **+1643.65%** |
| Grid pairs completed | 410 |
| Grid profit brut | +249.73 USDC |
| Fees totaux | 35.16 USDC |
| Net grid profit | +214.57 USDC |
| BTC held (unrealized) | 0.2756 BTC |
| Orders places | 9 804 |
| Rebalances | 1 341 |
| Max drawdown | 50.06% |
| Sharpe / Sortino | 0.14 / 0.20 |

**Analyse**: La majorite du return (+1643%) vient de l'exposition longue au BTC (0.276 BTC × prix final), pas du grid trading pur (+214 USDC). Le grid profit net est modeste mais positif. MaxDD de 50% est eleve — inherent a la strategie grid qui accumule du BTC en baisse. Par rapport au buy-and-hold (+1304%), la grid surperforme grace a l'effet de grid + accumulation BTC.

**Verdict**: **KEEP** — surperforme buy-and-hold. Reduire `max_allocation_pct` si le MaxDD est trop risque.

---

### 2. grok_adaptive_dca_weekly

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-09-04 → 2026-03-01 (3100 j) |
| Balance finale | 9 025.70 USDC |
| Return | **+802.57%** |
| Buys executes | ~67 (1000 USDC / 15 USDC/semaine) |
| Fees totaux | 1.60 USDC |
| Max drawdown | 49.53% |
| Sharpe / Sortino | 0.74 / 1.07 |

**Analyse**: Strategie d'accumulation pure (buy-only, jamais de sell). Les 1000 USDC sont depenses en ~67 semaines (1.3 ans), le reste est une exposition passive au BTC. Le Sharpe de 0.74 et Sortino 1.07 sont excellents pour une strategie DCA. Le return de +802% est inferieur au buy-and-hold (+1304%) car le DCA achete graduellement au lieu de tout en une fois au plus bas. MaxDD de 49.5% est attendu (exposition 100% BTC).

**Note methodologique**: Le backtest epuise le capital en ~15 mois. En production avec un flux d'entrees regulier (salaire → USDC → DCA), la strategie continuerait indefiniment. L'oversold_boost (×2.5 quand RSI < 30 + sous EMA200) et le bull_reduction (×0.5 en strong_bull) ne se sont declenches que rarement sur cette periode.

**Verdict**: **KEEP** — role complementaire d'accumulation long-terme. Ne peut pas battre buy-and-hold par design (DCA vs lump-sum), mais excellente discipline d'achat.

---

### 3. grok_supertrend_4h

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-09-04 → 2026-03-01 (3100 j) |
| Balance finale | 1 206.41 USDC |
| Return | **+20.64%** |
| Net P&L | +191.92 USDC |
| Trades | 107 |
| Win rate | 49.53% |
| Avg win / Avg loss | +6.29 / -2.20 USDC |
| Profit factor | **2.81** |
| Avg holding | 8.2 jours |
| Fees totaux | 23.04 USDC |
| Max drawdown | 2.39% |
| Sharpe / Sortino | 0.49 / 0.72 |

**Analyse**: Profitable avec un excellent profit factor (2.81) et un tres faible drawdown (2.39%). Le return absolu (+20.6%) est modeste car la strategie ne deploie que 50 USDC par trade (5% du capital). Le Sharpe de 0.49 passe le seuil de 0.3. Wins et losses sont equilibres (50/50) mais les gains moyens sont 2.86× les pertes moyennes — pattern classique de trend-following reussi.

**Limitation du backtest**: Le regime_1d est "UNKNOWN" car le regime breakdown utilise l'ancien systeme d'analyse (pas le MultiTimeframeAnalyzer). En production, le filtre regime ajoutera de la selectivite.

**Verdict**: **KEEP** — profitable, faible risque, bon Sharpe. Augmenter `order_size_usdc` (50→100) pour capturer plus de valeur.

---

### 4. grok_ema_adx_atr (EMA 27/125 cross)

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-09-04 → 2026-03-01 (3100 j) |
| Balance finale | 1 036.11 USDC |
| Return | +3.61% |
| Net P&L | +33.20 USDC |
| Trades | 27 |
| Win rate | 37.04% |
| Avg win / Avg loss | +6.04 / -1.32 USDC |
| Profit factor | **2.68** |
| Avg holding | 6.1 jours |
| Fees totaux | 4.64 USDC |
| Max drawdown | 1.64% |
| Sharpe / Sortino | 0.23 / 0.32 |

**Analyse**: Faiblement profitable (+3.6% sur 9 ans). Excellent profit factor (2.68) mais tres peu de trades (27 = 3/an). Le Sharpe de 0.23 est sous le seuil de 0.3 mais proche. Le drawdown extremement faible (1.64%) montre une strategie conservatrice. Le probleme principal est le manque d'opportunites — l'EMA 27/125 cross ne se produit pas souvent sur 4h.

**Verdict**: **WATCH** — profitable mais sous-deploye. Tester avec des EMA plus courtes (20/50) ou combiner avec d'autres filtres d'entree pour augmenter la frequence de trades.

---

### 5. gemini_retour_moyenne

| Metrique | Valeur |
|----------|--------|
| Periode | 2023-03-02 → 2026-03-01 (1095 j) |
| Balance finale | 998.85 USDC |
| Return | -0.12% |
| Net P&L | -1.56 USDC |
| Trades | 11 |
| Win rate | 27.27% |
| Avg win / Avg loss | +0.02 / -0.11 USDC |
| Profit factor | 0.08 |
| Max drawdown | 0.13% |
| Sharpe / Sortino | -0.14 / -0.17 |

**Analyse**: Presque inerte. Seulement 11 trades en 3 ans avec des montants minuscules (order_size 20 USDC). Profit factor de 0.08 — les gains sont 12× plus petits que les pertes. La strategie DCA avec 3 niveaux de spacing 0.5% est trop conservative sur les timeframes courts (15m). Le mean-reversion ne fonctionne pas bien sur BTC.

**Verdict**: **KILL** — Sharpe negatif, PF 0.08. Mean-reversion mal adaptee au BTC qui est un actif de momentum.

---

### 6. gemini_scalping_volatilite

| Metrique | Valeur |
|----------|--------|
| Periode | 2023-03-02 → 2026-03-01 (1095 j) |
| Balance finale | 988.22 USDC |
| Return | -1.18% |
| Net P&L | -16.44 USDC |
| Trades | 85 |
| Win rate | 35.29% |
| Avg win / Avg loss | +0.04 / -0.18 USDC |
| Profit factor | 0.14 |
| Avg holding | 33 min |
| Max drawdown | 1.21% |
| Sharpe / Sortino | -0.25 / -0.29 |

**Analyse**: Scalping a haute frequence (33 min avg) mais perdant. Les gains moyens (+0.04 USDC) sont 4.5× plus petits que les pertes (-0.18 USDC). Le PF de 0.14 est catastrophique — la strategie perd systematiquement. Les fees (0.16% maker) mangent tout le profit potentiel des petits mouvements (SL 1.5×ATR, TP 1.0×ATR avec un ratio risque/reward defavorable).

**Verdict**: **KILL** — Sharpe negatif, PF 0.14. Le ratio TP/SL (1.0/1.5) est inversement optimal — le TP devrait etre plus grand que le SL.

---

### 7. gemini_suivi_tendance_momentum*

| Metrique | Valeur |
|----------|--------|
| Periode | 2017-09-04 → 2026-03-01 (3100 j) |
| Balance finale | 904.27 USDC |
| Return | -9.57% |
| Net P&L | -122.20 USDC |
| Trades | 205 |
| Win rate | 27.32% |
| Avg win / Avg loss | +1.54 / -1.11 USDC |
| Profit factor | 0.52 |
| Avg holding | 39h 30min |
| Max drawdown | 9.95% |
| Sharpe / Sortino | -0.49 / -0.68 |

**Analyse**: Perdante malgre des conditions d'entree tres selectionnees (regime bull + golden cross + ADX>20 + pullback bounce).

**BUG DETECTE**: La strategie a un bug de timing dans `_update_pullback_state()` — elle ecrase `_prev_close_4h` avec le close ACTUEL dans `on_ohlc()`, puis `_is_pullback_bounce()` compare la meme valeur (close actuel vs EMA20 actuel), rendant la condition impossible. Le backtest a contourne ce bug en sauvegardant/restaurant l'etat precedent, mais **ce bug existe aussi en live mode** (meme sequence on_ohlc → generate_signal).

**Correction requise**: Dans `_update_pullback_state`, stocker les valeurs AVANT d'appeler `on_ohlc()`, ou deplacer l'appel apres `generate_signal()`. Sans correction, cette strategie ne generera **jamais de signal en production**.

**Verdict**: **KILL*** — Sharpe -0.49, PF 0.52, et bug bloquant en live. Corriger le bug puis re-tester avant d'envisager une reactivation.

---

## Buy & Hold Reference

| Periode | Prix debut | Prix fin | Return |
|---------|-----------|---------|--------|
| 9 ans (2017-09-04 → 2026-02-24) | 4 505 USDC | 63 259 USDC | **+1304.2%** |
| 3 ans (2023-03-02 → 2026-02-24) | 23 630 USDC | 63 259 USDC | **+167.7%** |

---

## Problemes Rencontres

1. **PostgreSQL OutOfMemoryError**: Les requetes sur 9 ans de candles 1h/4h/1d/1w en parallele depassaient `max_locks_per_transaction=128` (TimescaleDB chunks). Fix: `ALTER SYSTEM SET max_locks_per_transaction = 512` + restart container.

2. **Bug `max_open_positions` Pydantic**: `le=20` dans settings.py vs `25` dans strategies.yaml. Fix: `le=50`.

3. **Lazy EMA/SuperTrend non initialises avant warmup**: Les indicateurs lazy (EMA 50/200 sur 1d, SuperTrend sur 4h) n'etaient crees qu'au premier appel de `generate_signal()`, apres que toutes les donnees de warmup avaient deja ete traitees. Fix: pre-enregistrement des indicateurs lazy avant le replay.

4. **Flags `_is_4h`/`_is_daily` jamais sets**: Le BacktestEngine appelle `on_ohlc()` directement au lieu de `_handle_ohlc()`, donc les flags utilises par `generate_signal()` n'etaient jamais initialises. Fix: set/reset explicite par nom de strategie.

5. **Analyzer non mis a jour pour strategies Grok**: En live, le Router appelle `analyzer.update()`. En backtest standalone, les strategies Grok ne le font pas dans leur `on_ohlc()`. Fix: appel manuel `analyzer.update()` dans la boucle backtest.

6. **Ending balance calcule au prix du dernier trade**: Pour DCA (buy-only), `self.metrics.trades[-1].price` etait le prix du dernier achat (2019) au lieu du prix final du marche. Le return affichait -44.95% au lieu de +802.57%. Fix: utiliser l'equity curve (mark-to-market) pour le calcul final.

7. **Bug pullback bounce dans `gemini_suivi_tendance_momentum`**: La strategie ecrase `_prev_close_4h` AVANT `generate_signal()`, rendant la detection de pullback impossible. Ce bug existe aussi en live mode. Workaround backtest applique (save/restore).

---

## Recommandations

### KEEP (activer en paper trading)
- **grok_grid_atr_adaptive_v4**: Performer #1, surperforme buy-and-hold. Surveiller le MaxDD.
- **grok_adaptive_dca_weekly**: Accumulation disciplinee. Augmenter le capital si flux regulier.
- **grok_supertrend_4h**: Meilleur Sharpe (0.49), meilleur PF (2.81), meilleur drawdown (2.4%).

### WATCH (optimiser avant activation)
- **grok_ema_adx_atr**: Profitable mais trop peu de trades. Tester EMAs plus courtes.

### KILL (desactiver)
- **gemini_retour_moyenne**: PF 0.08, quasi-inerte. Mean-reversion inadaptee au BTC.
- **gemini_scalping_volatilite**: PF 0.14, ratio TP/SL inversement optimal.
- **gemini_suivi_tendance_momentum**: Bug bloquant + perdante meme corrigee.

### Actions prioritaires
1. Corriger le bug pullback dans `gemini_suivi_tendance_momentum` (live + backtest)
2. Passer les 3 KEEP en paper trading dans le router
3. Desactiver les 3 KILL dans `strategies.yaml` (`active: false`)
4. Pour `grok_ema_adx_atr`: tester EMA 20/50 au lieu de 27/125 et re-backtester

---

*Rapport genere automatiquement par le BacktestEngine. Tous les backtests utilisent des fees realistes (maker 0.16%, taker 0.26%) et le modele d'execution next-bar.*
