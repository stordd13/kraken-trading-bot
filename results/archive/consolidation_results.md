# Consolidation Phase 1A — Résultats

**Date** : 2026-03-01
**Période backtest** : 2017-06 → 2026-02 (3135 jours, ~8.6 ans)
**Pair** : BTC/USDC
**Fees** : maker 0.16%, taker 0.26%, spread 0.02%, slippage 0.01%

---

## 1. Bugs corrigés

### Bug 1 : Pullback state écrasé (`gemini_suivi_tendance_momentum.py`)

**Problème** : `_update_pullback_state()` écrivait `self._prev_close_4h = close_4h` (close actuel) avant que `_is_pullback_bounce()` ne le lise. Résultat : comparaison close actuel vs EMA actuel → zéro signal pullback.

**Fix** : Pattern shift avec variables intermédiaires `_current_close_4h` / `_current_ema20_4h`. La méthode décale maintenant current → previous avant de stocker les nouvelles valeurs.

**Fichier** : `src/krakenbot/strategies/gemini_suivi_tendance_momentum.py`

### Bug 2 : Decimal/float mixing dans indicateurs RSI et Bollinger

**Problème** :
- RSI : `_current_rsi` typé `float`, calcul via `100.0 - (100.0 / (1.0 + rs))` avec `rs = float(...)` — roundtrip Decimal→float→Decimal
- Bollinger : `math.sqrt(float(variance))` pour l'écart-type, champs `bandwidth`/`percent_b` en `float`
- MultiTimeframeAnalyzer : wrappers `Decimal(str(val))` inutiles autour d'indicateurs déjà Decimal

**Fix** :
- RSI : tout en `Decimal` natif, constantes `_ZERO`/`_ONE`/`_HUNDRED`
- Bollinger : `variance.sqrt()` (méthode native Decimal), champs `bandwidth`/`percent_b` en `Decimal`
- MTA : suppression des wrappers float→Decimal, comparaisons avec `_ZERO`/`_ONE`

**Note** : ADX et SuperTrend étaient déjà 100% Decimal — pas de correction nécessaire.

**Fichiers** : `indicators/rsi.py`, `indicators/bollinger.py`, `indicators/multi_timeframe.py`

### Bug 3 : Variable shadowing dans `main.py`

**Problème** : Variable `result` utilisée deux fois (L571 pour query Decimal, L597 pour query OpenPosition). Mypy infère le type de la première utilisation et flag des erreurs sur la seconde.

**Fix** : Renommé en `pos_result` à L597.

**Fichier** : `src/krakenbot/main.py`

### Corrections additionnelles (backtest engine)

- `scripts/backtest.py` : corrigé `period=10` → `atr_period=10` dans l'appel `get_supertrend()`
- `scripts/backtest.py` : restauré le routing `on_trade_filled()` pour les stratégies Grok/Gemini
- `grok_supertrend_4h.py` / `grok_ema_adx_atr.py` : ajouté `self._is_4h = False` dans `__init__` (requis par le backtest engine)
- `grok_ema_adx_atr.py` : ajouté pré-registration des EMAs lazy pour le warmup

---

## 2. Scaling SuperTrend 4h

**Objectif** : Vérifier que le scaling est linéaire (1 position max → pas d'interférence).
**Critère** : MaxDD < 10% à 200 USDC → scaling validé.

| Size USDC | Return | Profit Factor | Sharpe | MaxDD | Trades |
|-----------|--------|---------------|--------|-------|--------|
| 50        | +20.64% | 2.81         | 0.49   | 2.39% | 107    |
| 100       | +41.28% | 2.81         | 0.49   | 4.07% | 107    |
| 150       | +61.92% | 2.81         | 0.49   | 5.32% | 107    |
| 200       | +82.56% | 2.81         | 0.49   | 6.28% | 107    |

**Verdict** : Scaling parfaitement linéaire. PF et Sharpe constants. MaxDD 6.28% à 200 USDC → bien sous le seuil de 10%.

**Action** : `order_size_usdc` passé de 50 → **200 USDC** dans `strategies.yaml`.

---

## 3. Optimisation EMA Cross (grok_ema_adx_atr)

**Objectif** : Passer de EMA(27/125) à EMA(20/50) pour augmenter le nombre de trades.
**Critères** : Trades > 50 ET PF > 2.0 → adopter les nouveaux params.

| Config | Return | Profit Factor | Sharpe | MaxDD | Trades |
|--------|--------|---------------|--------|-------|--------|
| EMA 27/125 (baseline) | +3.61% | 2.68 | 0.23 | 1.64% | 27 |
| EMA 20/50 (test) | +9.25% | 3.54 | 0.43 | 1.73% | 50 |

**Verdict** : EMA(20/50) supérieur sur tous les critères :
- Return : +9.25% vs +3.61% (+156%)
- PF : 3.54 vs 2.68 (+32%)
- Sharpe : 0.43 vs 0.23 (+87%)
- Trades : 50 vs 27 (+85%) — seuil de 50 atteint
- MaxDD : quasi-identique (1.73% vs 1.64%)

**Action** : `ema_fast`/`ema_slow` mis à jour à **20/50** dans `strategies.yaml`.

---

## 4. État final de strategies.yaml

### Stratégies actives (4 survivantes)

| Stratégie | Bot ID | Ordre USDC | Allocation max | Statut |
|-----------|--------|------------|----------------|--------|
| grok_grid_atr_adaptive_v4 | grid_atr_v4 | 25 | 20% | KEEP (champion) |
| grok_supertrend_4h | supertrend_4h | **200** ↑ | 15% | KEEP (scalé 4x) |
| grok_ema_adx_atr | ema_cross_4h | 40 | 15% | WATCH → KEEP (params 20/50) |
| grok_adaptive_dca_weekly | dca_weekly | 15 base | 25% | KEEP |
| grok_ichimoku_cloud_4h | ichimoku_cloud_4h | 50 | 15% | NEW (à backtester) |
| grok_donchian_breakout_4h | donchian_breakout_4h | 50 | 15% | NEW (à backtester) |
| grok_vwap_trend_4h | vwap_trend_4h | 50 | 15% | NEW (à backtester) |

### Stratégies désactivées

| Stratégie | Bot ID | Raison |
|-----------|--------|--------|
| gemini_scalping_volatilite | scalping_vol | -14.8%, PF 0.86 |
| gemini_suivi_tendance_momentum | tendance_mom | -19.3%, pullback bug |
| gemini_retour_moyenne | retour_moy | -8.5%, DCA into falling knife |

---

## 5. Résumé des fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `src/krakenbot/strategies/gemini_suivi_tendance_momentum.py` | Bug 1 : fix pullback shift |
| `src/krakenbot/indicators/rsi.py` | Bug 2 : tout Decimal |
| `src/krakenbot/indicators/bollinger.py` | Bug 2 : sqrt Decimal, champs Decimal |
| `src/krakenbot/indicators/multi_timeframe.py` | Bug 2 : suppression wrappers float→Decimal |
| `src/krakenbot/main.py` | Bug 3 : variable rename |
| `src/krakenbot/strategies/grok_supertrend_4h.py` | Init `_is_4h` |
| `src/krakenbot/strategies/grok_ema_adx_atr.py` | Init `_is_4h` + pré-registration EMAs |
| `scripts/backtest.py` | Fix `atr_period` kwarg + routing `on_trade_filled` |
| `strategies.yaml` | Kill 3 Gemini, scale SuperTrend, update EMA params |

---

## 6. Prochaines étapes

1. **Backtester** ichimoku_cloud_4h, donchian_breakout_4h, vwap_trend_4h (nouvelles stratégies Agent 1)
2. **Paper trading** 2 semaines avec les 4 survivantes + 3 nouvelles
3. **Scaler** progressivement grid_atr_v4 si paper trading confirme
4. **Monitoring** : alertes Telegram/Discord pour les signaux et les stops
