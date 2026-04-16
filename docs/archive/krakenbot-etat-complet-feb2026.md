# KrakenBot — État complet du projet (Février 2026)

## 1. Vue d'ensemble

Bot de trading automatisé BTC/USDC sur Kraken. Deux services :

- **krakenbot-collector** : collecte de données 24/7 (WebSocket + REST backfill) → PostgreSQL/TimescaleDB sur Hetzner VPS
- **krakenbot** : bot de trading (paper/live, multi-stratégie via MultiStrategyRouter)

Stack : Python 3.11+, async/await, ccxt, Decimal pour les prix, structlog, Pydantic Settings, SQLAlchemy + Alembic, Dash pour le dashboard.

Déployé sur Hetzner VPS, CI/CD GitHub Actions.

---

## 2. Données disponibles en DB

### Candles OHLC (table `market_data_ohlc`, hypertable TimescaleDB)

| Intervalle | Historique disponible | Volume approximatif |
|-----------|----------------------|---------------------|
| 1 min | ~3 ans | ~1.5M candles |
| 5 min | **3 ans (1095 jours)** — utilisé pour tous les backtests | ~315k candles |
| 15 min | ~3 ans | ~105k candles |
| 60 min (1h) | ~3 ans | ~26k candles |

Période couverte : **2023-02-17 → 2026-02-16**

Contexte marché sur cette période :
- 2023 : BTC ~$23k → ~$42k (recovery post-FTX, +80%)
- 2024 : BTC ~$42k → ~$95k (ETF spot approval, halving, bull run)
- 2025 H1 : BTC ~$95k → ~$112k (ATH)
- 2025 H2-2026 : BTC ~$112k → ~$70k (bear market -40%)

Chaque candle : timestamp, pair, interval, open, high, low, close, volume, vwap, trades_count.

### Autres tables
- `market_data_ticks` : ticks bruts (moins utilisé)
- `trades_history` : tous les trades exécutés (paper + live)
- `open_positions` : positions ouvertes (avec colonne `trading_mode` spot/margin)
- `orders` : lifecycle des limit orders (PENDING → FILLED/CANCELLED/EXPIRED)
- `bot_state` : état persistant par bot_id
- `backtest_runs` : résultats des backtests sauvegardés

### Accès aux données pour backtest
Le backtest engine (`scripts/backtest.py`) charge les candles directement depuis la DB via SSH tunnel :
```bash
ssh -L 5432:localhost:5432 bruno@<IP> -N &
poetry run python scripts/backtest.py --strategy <name> --days <N> --interval 5 --capital 1000 --save
```

---

## 3. Architecture de trading

### Flux d'un trade (mode multi-strategy router)
```
Candle WebSocket → EventBus (MARKET_OHLC)
  → MultiStrategyRouter._handle_ohlc()
    → dispatch vers 7 stratégies internes (on_ohlc + generate_signal)
    → GeminiGlobalRiskManager.process_signal() sur chaque signal BUY
      → Règle 1 : Position sizing 1% du capital
      → Règle 2 : Stop-loss ATR systématique
      → Règle 3 : Crash protector (chute ≥7% en 30min → ferme 50% + suspend 2h)
    → emit signal final vers EventBus (TRADE_SIGNAL)
  → ExecutionEngine._execute_signal()
    → GlobalRiskManager.check_order() (checks globaux + par stratégie)
    → KrakenRestClient.place_limit_order() ou place_market_order()
    → Trade enregistré en DB
  → EventBus (TRADE_ORDER_FILLED)
    → MultiStrategyRouter._handle_trade_filled()
      → route vers la stratégie source via bot_id
```

### Types d'ordres
| Signal | Type | Fee | Raison |
|--------|------|-----|--------|
| BUY normal | LIMIT | 0.16% maker | Économie fees |
| SELL profit target | LIMIT | 0.16% maker | Pas pressé |
| SELL stop-loss | MARKET | 0.26% taker | Exécution garantie |
| SELL trailing stop | MARKET | 0.26% taker | Exécution garantie |

### Paper mode
- Simule les trades en mémoire (`_paper_balance` dans `kraken_rest.py`)
- Les limit orders sont simulés : fill quand `candle.low <= limit_buy_price` ou `candle.high >= limit_sell_price`
- Les trades sont enregistrés en DB exactement comme en live

### Multi-stratégie (architecture actuelle)
- Config dans `strategies.yaml` : le `multi_strategy_router` est la seule stratégie active
- Le router contient 7 stratégies internes + GeminiGlobalRiskManager
- Chaque stratégie interne a son `bot_id`, son `order_size_usdc`, son `max_allocation_pct`
- Le router est la seule BaseStrategy enregistrée dans l'EventBus
- `GlobalRiskManager` existant : checks à 2 niveaux (global tous bots + par stratégie)

---

## 4. Multi-timeframe étendu

Le bot s'abonne aux candles sur **6 timeframes** via WebSocket. Le `MultiTimeframeAnalyzer` maintient :

### Timeframes
`5m`, `15m`, `1h`, `4h`, `1d`, `1w`

### Régime de marché (calculé par timeframe)
```
strong_bear  : EMA20 << EMA50, RSI < 35
bear         : EMA20 < EMA50
neutral      : EMA20 ≈ EMA50 (écart < 0.5%)
bull         : EMA20 > EMA50
strong_bull  : EMA20 >> EMA50, RSI > 65
```

### Indicateurs disponibles (par timeframe)

| Indicateur | Méthode | Périodes/Params |
|-----------|---------|----------------|
| EMA | `get_ema(period, tf)` | Arbitraire (20, 27, 50, 125, 200...) — création lazy |
| RSI | `get_rsi(period, tf)` | Arbitraire (7, 14...) — création lazy |
| ATR | `get_atr(period, tf)` | Arbitraire (10, 14...) — création lazy |
| MACD | `get_macd(tf)` | 12/26/9 (adapté par TF) |
| Bollinger | `get_bollinger(tf)` | Period 20, StdDev 2.0 |
| ADX | `get_adx(tf)` | Period 14 |
| SuperTrend | `get_supertrend(tf, period, mult)` | Configurable |
| Régime | `get_regime(tf)` | EMA20/50 + RSI |

---

## 5. Stratégies legacy — historique complet

### 5.1 ThresholdRollingStrategy (abandonnée)
**Concept :** Mean reversion à seuils fixes. Achète quand le prix baisse de -3% par rapport à une référence roulante, vend quand il monte de +2%.

**Résultat backtest 1 an :** -41.33%, 967 trades, 56.3% win rate.

**Pourquoi ça ne marche pas :** Le ratio win/loss est structurellement mauvais. Avg win +0.68% vs avg loss -1.51% (ratio 1:2.2). Il faudrait 67.6% de win rate pour breakeven, mais on n'atteint que 56%. Les fees (0.16-0.26%) mangent 37-62% du gain moyen sur des trades de 50 USDC.

### 5.2 AdaptiveStrategy (abandonnée)
**Concept :** Évolution de ThresholdRolling avec seuils dynamiques selon le régime de marché.

**Résultat backtest 1 an :** -19.07%, 718 trades, 58.1% win rate. Perd dans TOUS les régimes y compris STRONG_BULL.

**Pourquoi ça ne marche pas :** Même problème structurel que ThresholdRolling. Mean reversion sur candles 5min ne fonctionne pas.

### 5.3 CapitulationStrategy (abandonnée)
**Concept :** Détecte les crashes extrêmes (RSI 1h < 20, volume spike > 3×, RSI 5min < 15).

**Résultat backtest 1 an :** -1.60%, 9 trades, 11.1% win rate.

**Pourquoi ça ne marche pas :** Trop peu de trades. Les conditions sont trop strictes — 9 signaux en un an.

### 5.4 BearShortStrategy (abandonnée)
**Concept :** Short via Kraken margin en BEAR/STRONG_BEAR.

**Résultat backtest 1 an :** -4.79%, 168 trades, 28.0% win rate.

**Pourquoi ça ne marche pas :** Le détecteur de régime oscille trop entre BEAR et NEUTRAL.

### 5.5 TrendFollowingStrategy (désactivée)
**Concept :** EMA20 croise EMA50 par le haut (golden cross 1h) → BUY. Trailing stop 6%.

**Résultats backtests 3 ans :** V1 : -1.15% (217 trades, bug). V2 : -0.21% (8 trades). Ne capture aucun mouvement sur BTC +180%.

### 5.6 GridSpotStrategy (LEGACY — remplacée par GrokGridATRAdaptiveV4)
**Concept :** Grille de limit orders autour du prix, range fixe ±15%.

**Résultats backtests 3 ans :**

| Version | Range | Levels | Spacing | Return | Paires | Rebalances | Ratio P/F |
|---------|-------|--------|---------|--------|--------|------------|-----------|
| V1 | ±10% | 10 | 2.0% | +171% | 55 | 263 | 4.35× |
| V2 | ±20% | 15 | 1.5% | +45% | 274 | 50 | 3.78× |
| V3 | ±15% | 15 | 1.5% | en test | — | — | — |

### 5.7 GridAdaptiveStrategy (LEGACY — remplacée par GrokGridATRAdaptiveV4)
**Concept :** Comme GridSpot mais range calculé dynamiquement via ATR.

**Résultats backtests 3 ans :**

| Version | min_spacing | Return | Paires | Ratio P/F |
|---------|------------|--------|--------|-----------|
| V1 | 0.5% | +180% | 440 | 1.48× |
| V2 | 1.5% | +178% | 105 | 3.47× |

---

## 6. Nouvelles stratégies (via MultiStrategyRouter)

> **Statut : implémentées, en attente de backtest et paper trading.**
> Toutes ces stratégies tournent sous le `MultiStrategyRouter` avec un budget de ~1000 USDC.

### 6.1 GeminiScalpingVolatilite — Scalping intraday 5m
**Concept :** Scalping rapide sur oversold RSI + MACD crossover. Positions de quelques minutes à heures, jamais overnight.

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 5m (trigger) + 1h (filtre régime) |
| **Entrée BUY** | RSI(7, 5m) < 30 + MACD hist passe positif sur 5m + régime 1h ≠ strong_bear |
| **Take-Profit** | +1.0 × ATR(14, 5m) en LIMIT |
| **Stop-Loss** | -1.5 × ATR(14, 5m) en MARKET |
| **Trailing** | Activation à +0.5×ATR, trail à 1.0×ATR |
| **No Overnight** | Ferme tout à 23:00 UTC |
| **Taille ordre** | 25 USDC, max 2 positions, max 10% capital |

### 6.2 GeminiSuiviTendanceMomentum — Trend following 4h/1d
**Concept :** Swing trading sur pullback vers EMA(20) en tendance haussière confirmée par golden cross EMA50/200 + ADX > 20.

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 4h (trigger) + 1d (macro filter) |
| **Macro filter** | EMA(50,1d) > EMA(200,1d) + ADX(1d) > 20 + régime 1d = bull/strong_bull |
| **Entrée BUY** | Pullback bounce : prev close ≤ EMA(20,4h), current close > EMA(20,4h) |
| **Stop-Loss initial** | -2.5 × ATR(14, 4h) en MARKET |
| **Trailing** | 2.0 × ATR(14, 4h) depuis le plus haut |
| **Exit régime** | Sortie immédiate si régime 1d → bear/strong_bear |
| **Taille ordre** | 50 USDC, max 1 position, max 15% capital |

### 6.3 GeminiRetourMoyenne — Mean reversion Bollinger + DCA 15m
**Concept :** Mean reversion en range (ADX < 20 sur 1h). Entrée sur touch BB lower + divergence RSI. DCA 3 niveaux espacés de 0.5%.

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 15m (trigger) + 1h (filtre range) |
| **Range detect** | ADX(14, 1h) < 20 = pas de tendance |
| **Entrée BUY** | Prix touche BB lower (15m) + divergence RSI haussière |
| **DCA** | 3 niveaux espacés de 0.5% sous BB lower |
| **Take-Profit** | BB middle (15m) en LIMIT |
| **Stop-Loss** | -2.0 × ATR(14, 15m) sous le DCA le plus bas |
| **Taille ordre** | 20 USDC par niveau, max 2 positions, max 10% capital |

### 6.4 GrokGridATRAdaptiveV4 — Grid ATR + biais directionnel
**Concept :** Grid trading avec spacing ATR-based et biais directionnel selon le régime quotidien. Pause en weekly strong_bear.

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 4h (calcul/recalc grille) |
| **Spacing** | max(1.5%, ATR × 4.0 / prix) |
| **Biais** | BULL → plus de BUY, BEAR → plus de SELL, NEUTRAL → réparti |
| **Pause** | régime 1w = strong_bear → HOLD complet |
| **Recalc** | Toutes les 6 heures |
| **Min profitabilité** | sell_level ≥ entry × 1.0064 (couvre ~0.64% fees A/R) |
| **Taille ordre** | 25 USDC, 12 niveaux, max 20% capital |

### 6.5 GrokSuperTrend4hRegime — SuperTrend 4h + régime 1d
**Concept :** Trend following mécanique basé sur SuperTrend(10, 3.0) sur 4h. La ligne SuperTrend sert de trailing stop naturel.

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 4h (trigger) + 1d (filtre régime) |
| **Entrée BUY** | close > SuperTrend + régime 1d = bull/strong_bull |
| **Exit SuperTrend** | close < SuperTrend (direction flip) → MARKET |
| **Exit régime** | régime 1d → bear/strong_bear → MARKET |
| **Stop-Loss initial** | -3.5 × ATR(14, 4h) |
| **Trailing** | SuperTrend line (mise à jour automatique) |
| **Taille ordre** | 50 USDC, 1 position, max 15% capital |

### 6.6 GrokEMA27_125_ADX_ATR — EMA cross + gestion stops 3 étages
**Concept :** Golden cross EMA(27)/EMA(125) sur 4h avec confirmation ADX. Stop management progressif : initial → break-even → trailing.

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 4h (trigger) + 1d (filtre régime) |
| **Entrée BUY** | EMA(27) croise au-dessus EMA(125) + ADX ≥ 14 + régime 1d = bull/strong_bull |
| **Exit death cross** | EMA(27) croise sous EMA(125) → MARKET |
| **Exit régime** | régime 1d → bear/strong_bear → MARKET |
| **Stop initial** | -3.5 × ATR(14, 4h) |
| **Break-even** | Quand profit ≥ 1.5×ATR → SL monte à entry |
| **Trailing** | Après break-even → SL = highest - 3.0×ATR |
| **Taille ordre** | 40 USDC, 1 position, max 15% capital |

### 6.7 GrokAdaptiveDCAWeekly — DCA hebdomadaire adaptatif
**Concept :** Accumulation BTC mécanique chaque lundi. Montant adapté au marché : boost en oversold, réduction en strong bull.

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 1d (lundi uniquement) |
| **Entrée BUY** | Chaque lundi (weekday == 0), 1 achat par semaine ISO |
| **Montant base** | 15 USDC |
| **Oversold boost** | RSI(14,1d) < 30 ET close < EMA(200,1d) → ×2.5 |
| **Bull reduction** | régime 1w = strong_bull → ×0.5 |
| **Type ordre** | LIMIT à prix × 0.999 (maker fee optimization) |
| **Pas de SELL** | Accumulation pure, pas de vente automatique |
| **Max allocation** | 25% capital |

---

## 7. GeminiGlobalRiskManager — Module de risk overlay

> **Ce n'est PAS une stratégie (pas de BaseStrategy).** C'est un module qui s'interpose entre les stratégies et l'exécution via le router.

### Règle 1 : Position Sizing (1% Rule)
```
Taille de position = (capital × 1%) / |entry - stop_loss|
```
La perte maximale par trade est limitée à 1% du capital total.

### Règle 2 : Stop-Loss ATR systématique
```
SL = entry_price - 3.0 × ATR(14, "4h")
```
Chaque signal BUY reçoit un SL calculé par ATR. Le multiplier est configurable.

### Règle 3 : Crash Protector
- **Détection** : chute ≥ 7% en 30 minutes (rolling window sur 1m candles)
- **Action immédiate** : ferme 50% des positions longues (les plus grosses d'abord)
- **Suspension** : bloque toute nouvelle entrée pendant 2 heures

### Pipeline process_signal()
```
Signal BUY entrant
  → Est-on en crash ? → Oui → signal rejeté (None)
  → Calcul ATR SL
  → Position sizing 1% rule
  → Injection metadata (risk_stop_loss, risk_position_size_btc, etc.)
  → Signal modifié sortant

Signal SELL → passe toujours (on ne bloque jamais une sortie)
```

### Config actuelle (strategies.yaml)
```yaml
risk:
  risk_per_trade_pct: 1.0
  atr_sl_multiplier: 3.0
  atr_sl_timeframe: "4h"
  atr_sl_period: 14
  crash_threshold_pct: 7.0
  crash_window_min: 30
  crash_close_pct: 0.5
  crash_suspend_hours: 2
```

---

## 8. MultiStrategyRouter — Orchestrateur

### Architecture
Le router est la **seule** BaseStrategy enregistrée dans l'EventBus. Il contient en interne les 7 stratégies + le GeminiGlobalRiskManager.

```
EventBus MARKET_OHLC → Router._handle_ohlc()
  ├── update_price() pour crash protector (sur 1m candles)
  ├── dispatch vers chaque stratégie interne :
  │   ├── Stratégies avec _handle_ohlc custom → appel direct
  │   └── Stratégies standard → on_ohlc() + generate_signal()
  ├── Chaque signal BUY → _apply_risk_overlay()
  │   └── GeminiGlobalRiskManager.process_signal()
  └── Signal final → EventBus TRADE_SIGNAL → ExecutionEngine

EventBus TRADE_ORDER_FILLED → Router._handle_trade_filled()
  └── Route vers stratégie source via bot_id
```

### Bot IDs des stratégies internes
| Stratégie | bot_id |
|-----------|--------|
| GeminiScalpingVolatilite | scalping_vol |
| GeminiSuiviTendanceMomentum | tendance_mom |
| GeminiRetourMoyenne | retour_moy |
| GrokGridATRAdaptiveV4 | grid_atr_v4 |
| GrokSuperTrend4hRegime | supertrend_4h |
| GrokEMA27_125_ADX_ATR | ema_cross_4h |
| GrokAdaptiveDCAWeekly | dca_weekly |

### Dispatch intelligent
- Détecte si une stratégie a un `_handle_ohlc` custom (grid, supertrend, ema_cross, dca, scalping, tendance, retour_moyenne)
- Les stratégies avec custom handler gèrent leur propre filtrage timeframe et émettent directement
- Le router intercepte les signaux émis et applique le risk overlay

### Gestion du crash
En cas de crash détecté (chute ≥7% en 30 min) :
1. Collecte TOUTES les positions ouvertes de TOUTES les stratégies (duck-typing)
2. Trie par taille décroissante
3. Génère des SELL MARKET pour 50% des positions
4. Suspend les nouvelles entrées pendant 2h

---

## 9. Leçons apprises — ce qui marche et ce qui ne marche pas

### CE QUI NE MARCHE PAS en crypto avec un petit capital (~1000 USDC)

1. **Mean reversion sur candles 5min** — Les mouvements sont trop petits (avg win +0.68%) pour couvrir les fees. 3 stratégies testées, 3 échecs.

2. **Stratégies signal-based en général** — Sur 6 stratégies signal-based testées, ZÉRO est profitable sur 1-3 ans.

3. **Trailing stops serrés (2-3%)** — Se déclenchent systématiquement sur le bruit intraday.

4. **Détection de régime comme switch on/off** — Le MarketRegime (EMA20/EMA50 1h) oscille trop entre BEAR et NEUTRAL. Inutile comme filtre binaire.

5. **Hard stops sur candles 5min** — Tue les positions trend-following avant que le trend ne s'installe.

### CE QUI MARCHE

1. **Grid trading** — Seule approche structurellement profitable. Chaque paire = profit garanti (spacing - fees).

2. **min_spacing ≥ 1.5%** — Ratio profit/fees 1.48× → 3.47× juste en montant le spacing minimum.

3. **Limit orders (maker fees 0.16%)** — Division des fees par 1.6 vs market orders.

4. **Timeframes plus longs (4h, 1d)** — Réduisent l'impact des fees et le bruit. Les 7 nouvelles stratégies utilisent 4h/1d pour les signaux principaux.

5. **Stops ATR-based** — Plus robustes que les stops % fixes. S'adaptent à la volatilité.

6. **Risk overlay centralisé** — Le GeminiGlobalRiskManager garantit qu'aucune stratégie ne peut risquer plus de 1% du capital sur un trade.

### HYPOTHÈSES À VALIDER (nouvelles stratégies)

Les 7 nouvelles stratégies suivent les leçons apprises mais **n'ont pas encore été backtestées**. Les hypothèses clés :
- Le scalping 5m avec RSI(7) + MACD donne-t-il un meilleur edge que le mean reversion classique ?
- Le trend following sur 4h avec SuperTrend/EMA est-il plus stable qu'avec EMA20/50 1h ?
- Le DCA hebdomadaire adaptatif bat-il le DCA fixe simple ?
- La grille ATR avec biais directionnel améliore-t-elle le ratio P/F ?

---

## 10. Fees Kraken

| Type | Fee | Utilisation |
|------|-----|-------------|
| Maker (limit order) | 0.16% | BUY et SELL des grids |
| Taker (market order) | 0.26% | Stop-loss, trailing stop |
| Spread simulé (backtest) | 0.02% | Ajouté au backtest |
| Slippage simulé (backtest) | 0.01% | Ajouté au backtest |
| Margin rollover | 0.01% / 4h | Estimé pour les shorts |

**Fee totale par paire grid :** 0.16% (buy) + 0.16% (sell) = 0.32%
**Spacing minimum profitable :** 0.64% (2× fees) — en pratique on utilise 1.5% min.

---

## 11. Backtest engine

**Fichier :** `scripts/backtest.py`

Deux modes :
- **SignalBacktester** : pour les stratégies signal-based. Signal sur candle N → exécution à l'OPEN de candle N+1.
- **GridBacktester** : pour les grids. Gère N ordres simultanés, fill quand le prix traverse un niveau.

**Corrections appliquées :** look-ahead bias fix, fees réalistes (spread + slippage + maker/taker), tracking régime à l'entrée.

**Commande :**
```bash
poetry run python scripts/backtest.py --strategy <name> --days <N> --interval 5 --capital 1000 --save
```

---

## 12. État actuel du déploiement

```
Stratégie active :
  ✅ multi_strategy_router — orchestrateur unique avec :
     ├── scalping_vol       (GeminiScalpingVolatilite)     — 25 USDC/ordre, max 10%
     ├── tendance_mom       (GeminiSuiviTendanceMomentum)  — 50 USDC/ordre, max 15%
     ├── retour_moy         (GeminiRetourMoyenne)          — 20 USDC/ordre, max 10%
     ├── grid_atr_v4        (GrokGridATRAdaptiveV4)        — 25 USDC/ordre, max 20%
     ├── supertrend_4h      (GrokSuperTrend4hRegime)       — 50 USDC/ordre, max 15%
     ├── ema_cross_4h       (GrokEMA27_125_ADX_ATR)        — 40 USDC/ordre, max 15%
     └── dca_weekly          (GrokAdaptiveDCAWeekly)         — 15 USDC/semaine, max 25%
     + GeminiGlobalRiskManager (1% rule, ATR SL, crash protector)

Stratégies legacy (disabled) :
  ❌ grid_spot — remplacée par grok_grid_atr_adaptive_v4
  ❌ grid_adaptive — remplacée par grok_grid_atr_adaptive_v4
  ❌ trend_following — ne capture pas les trends
  ❌ adaptive / capitulation / bear_short / threshold_rolling — abandonnées

Mode : EN ATTENTE — backtest + paper trading requis avant déploiement
Capital prévu : ~1000 USDC
Pair : XBT/USDC
```

---

## 13. Structure des fichiers clés

```
src/krakenbot/
├── strategies/
│   ├── __init__.py                          # Exports des 11 classes
│   ├── base.py                              # BaseStrategy ABC + TradingSignal
│   ├── multi_strategy_router.py             # ROUTER — orchestrateur 7 strats + risk
│   ├── gemini_global_risk_manager.py        # Risk overlay (1%, ATR SL, crash)
│   ├── gemini_scalping_volatilite.py        # Scalping RSI+MACD 5m
│   ├── gemini_suivi_tendance_momentum.py    # Trend EMA50/200 1d + pullback 4h
│   ├── gemini_retour_moyenne.py             # Mean reversion BB + DCA 15m
│   ├── grok_grid_atr_adaptive_v4.py         # Grid ATR + biais directionnel
│   ├── grok_supertrend_4h.py                # SuperTrend 4h + régime 1d
│   ├── grok_ema_adx_atr.py                  # EMA 27/125 cross + ADX + stops 3 étages
│   ├── grok_adaptive_dca_weekly.py          # DCA hebdo adaptatif
│   ├── grid_spot.py                         # LEGACY
│   ├── grid_adaptive.py                     # LEGACY
│   ├── trend_following.py                   # LEGACY
│   ├── adaptive.py                          # LEGACY
│   ├── capitulation.py                      # LEGACY
│   ├── bear_short.py                        # LEGACY
│   ├── threshold_rolling.py                 # LEGACY
│   └── threshold.py                         # Deprecated
├── indicators/
│   ├── multi_timeframe.py                   # MultiTimeframeAnalyzer (6 TF, 8 indicateurs)
│   ├── ema.py, rsi.py, macd.py, bollinger.py, atr.py, adx.py, supertrend.py
├── execution/
│   ├── engine.py                            # Signal → Risk → Order
│   ├── risk.py                              # GlobalRiskManager (2 niveaux)
│   └── order_manager.py                     # Lifecycle limit orders
├── connectors/
│   ├── kraken_rest.py                       # REST via ccxt (paper + live)
│   └── kraken_ws.py                         # WebSocket multi-interval
├── config/settings.py
└── main.py                                  # Orchestrateur + STRATEGY_REGISTRY

scripts/
├── backtest.py                              # BacktestEngine (signal + grid)
├── dashboard.py                             # Dashboard Dash
└── backtest_grid.py                         # Grid search paramètres

strategies.yaml                              # Config multi-stratégie (7 strats + risk + legacy)
```

---

## 14. Prochaines étapes

### Immédiat (quand le serveur sera up)
1. `ruff check . --fix && ruff format .` — lint complet
2. `poetry run pytest` — tests unitaires
3. Backtest individuel de chaque nouvelle stratégie sur 3 ans
4. Paper trading du multi_strategy_router complet

### Court terme
- Analyser les résultats de backtest → désactiver les stratégies non-rentables
- Optimiser les paramètres des stratégies gagnantes (grid search)
- Alertes Telegram/Discord sur trades exécutés

### Moyen terme
- Multi-pair (ETH/USDC, SOL/USDC)
- Dashboard : afficher les 7 stratégies + P&L par stratégie

### Long terme
- ML/DL sur 3 ans de données accumulées
- RL : agent qui optimise les seuils en continu

### Benchmark à battre
| Métrique | Buy-and-hold 3 ans | Objectif |
|----------|-------------------|----------|
| Return | +180% | > +180% |
| Max drawdown | -51% | < -25% |
| Sharpe | ~0.06 | > 0.3 |
