# KrakenBot — Plan ML/DL v5.0 (Février–Juillet 2026)

> **Document de référence pour Claude Code agents.**
> Ce plan a été validé après 5 itérations de review croisée entre 2 IA.
> Il est la SEULE source de vérité pour toute implémentation ML sur KrakenBot.

---

## 0. Contexte Projet (résumé)

**KrakenBot** = bot de trading automatisé BTC/USDC sur Kraken.

### Architecture existante (NE PAS MODIFIER)
- **Collector** (24/7) : WebSocket Kraken + backfill REST → PostgreSQL/TimescaleDB
- **Trading Bot** : `MultiStrategyRouter` = seule stratégie dans l'EventBus, dispatch vers 7 stratégies internes
- **Risk** : `GeminiGlobalRiskManager` filtre chaque signal BUY (1% rule + ATR stop-loss + crash protector)
- **Execution** : `ExecutionEngine` → Kraken REST via ccxt
- **Backtest** : `scripts/backtest.py` avec `SignalBacktester` + `GridBacktester`

### Stack
Python 3.11+, 100% async/await, Decimal pour prix, structlog, ccxt, SQLAlchemy 2.0 async + asyncpg + TimescaleDB, Dash dashboard.

### Données disponibles
| Intervalle | Profondeur | Volume approx |
|-----------|-----------|---------------|
| 1m | ~6-12 mois | variable |
| 5m | ~1-2 ans | ~315k candles/an |
| 15m | ~3 ans | ~105k candles |
| 1h | **~9 ans (depuis 2017)** | ~26k candles |
| 4h | **~9 ans** | ~6.5k candles |
| 1d | **~9 ans** | ~3.3k candles |
| 1w | **~9 ans** | ~470 candles |

### Les 7 stratégies actives (toutes en attente de backtest)
| # | Nom | bot_id | TF | Type | Budget |
|---|-----|--------|----|----|--------|
| 1 | GeminiScalpingVolatilite | scalping_vol | 5m+1h | Scalping RSI+MACD | 25 USDC |
| 2 | GeminiRetourMoyenne | retour_moy | 15m+1h | Mean reversion BB+DCA | 20 USDC |
| 3 | GeminiSuiviTendanceMomentum | tendance_mom | 4h+1d | Trend EMA pullback | 50 USDC |
| 4 | GrokGridATRAdaptiveV4 | grid_atr_v4 | multi-TF | Grid ATR + biais | 25 USDC |
| 5 | GrokSuperTrend4hRegime | supertrend_4h | 4h+1d | SuperTrend trend | 50 USDC |
| 6 | GrokEMA27_125_ADX_ATR | ema_cross_4h | 4h+1d | EMA cross + 3 stops | 40 USDC |
| 7 | GrokAdaptiveDCAWeekly | dca_weekly | 1d | DCA hebdo adaptatif | 15 USDC/sem |

### Fees Kraken (L'ENNEMI #1)
- BUY limit (maker) : 0.16%
- SELL limit (maker) : 0.16%
- SELL market (taker) : 0.26%
- Round-trip minimum : 0.32% (limit/limit) à 0.42% (limit/market)
- **Tout signal doit espérer > 0.5% de move net pour être rentable**

### Leçons apprises (3 ans de backtests antérieurs)
- **Mean reversion 5m = MORT** (3 strats testées, 3 échecs, avg win trop petit vs fees)
- **Grid trading = SEULE approche profitable** (+45% à +180% sur 3 ans)
- **min_spacing ≥ 1.5% CRITIQUE** pour la grid
- **Limit orders maker** = économise 38% de fees vs market
- **Timeframes longs (4h, 1d)** = moins d'impact fees et de bruit
- **ATR stops > stops % fixes**
- **6/6 stratégies signal-based historiques = zéro profitable**

### Benchmark
Buy-and-hold BTC fév 2023 → fév 2026 = +180%, max drawdown -51%.

---

## 1. Philosophie ML (NON NÉGOCIABLE)

1. **ML = optimiseur d'alpha existant.** ML n'invente pas de signaux. Il améliore les stratégies rule-based déjà profitables (grid principalement, possiblement 1-2 strats 4h).
2. **Fees = ennemi #1.** Toute target ML ≥ +0.64% net (0.32% round-trip maker).
3. **9 ans de données 1h+ = avantage majeur** pour walk-forward validation (2 cycles bull/bear complets).
4. **Aucune stratégie rule-based ne reçoit de ML si elle n'a pas prouvé son edge en backtest.**
5. **Un seul modèle actif en prod** : LightGBM enhancer. Tout le reste = recherche offline.
6. **Toggle `ml.enabled: false` dans strategies.yaml** → zéro risque de régression.
7. **Fallback systématique** : si ML down → règles pures, transparent.

---

## 2. Phases du Plan

### PHASE -1 — BACKTEST DES 7 STRATÉGIES (3-4 semaines)

> **BLOQUANT : rien ne se passe en ML avant que cette phase soit terminée.**

#### Phase -1A : Backtests individuels (semaine 1-2)
Lancer chaque stratégie individuellement avec le backtest engine ACTUEL (pas de refactoring).
- SignalBacktester pour les 6 strats signal-based
- GridBacktester pour GrokGridATRAdaptiveV4
- Période : max disponible (9 ans pour 4h/1d, 3 ans pour 5m/15m)
- Fees : maker 0.16%, taker 0.26%, spread 0.02%, slippage 0.01%

**Métriques obligatoires par stratégie :**
- Return total (%)
- Sharpe ratio
- Profit Factor
- Max Drawdown (%)
- Win rate + avg win / avg loss
- Nombre de trades
- Performance par régime (bull/bear/neutral/strong_bull/strong_bear)
- Comparaison vs buy-and-hold même période

**Critères de survie :**
- Sharpe > 0.4 sur la période complète
- Max DD < 30%
- PF > 1.5 après fees réalistes

**Résultat attendu :** 2-4 stratégies survivantes (grid quasi-certaine, DCA par construction, possiblement 1-2 strats 4h). Les autres → `active: false` dans strategies.yaml.

#### Phase -1B : Backtest multi-strat (semaine 3-4, après -1A)
Refactoring de backtest.py pour :
- Coexistence SignalBacktester + GridBacktester dans un même run
- Capital partagé + allocations yaml
- GeminiGlobalRiskManager simulé sur toutes positions simultanées
- **Ne refactorer que pour les stratégies survivantes de -1A**

---

### PHASE 0 — Infrastructure ML (1 semaine)

#### Structure de dossiers
```
src/krakenbot/ml/
├── __init__.py
├── features/
│   └── feature_store.py          # réutilise MultiTimeframeAnalyzer.get_features_dict()
├── models/
│   └── lightgbm/
│       ├── vol_forecaster.py     # 2.1
│       ├── regime_predictor.py   # 2.2
│       └── signal_filter.py      # 2.3
├── inference/
│   └── enhancer.py               # MLSignalEnhancer (classe unique)
├── monitoring/
│   └── drift.py                  # PSI + feature importance tracking
└── mlflow/                       # tracking expériences
```

#### Section strategies.yaml
```yaml
ml:
  enabled: false
  mode: "enhancer"          # enhancer uniquement pour l'instant
  confidence_threshold: 0.62
  retrain_every: "30d"
  fallback_on_error: true   # si ML crash → règles pures automatiquement
```

#### Extension MultiTimeframeAnalyzer
Ajouter `get_features_dict(tf, lookback=240)` qui retourne un dict de tous les indicateurs existants, normalisés et prêts pour le ML.

---

### PHASE 1 — Feature Store (3 semaines)

#### Table TimescaleDB
```sql
-- ml_features : hypertable indexée par timestamp
CREATE TABLE ml_features (
    timestamp TIMESTAMPTZ NOT NULL,
    pair VARCHAR(20) NOT NULL,
    -- ~55 features candidates, réduites à 15-30 après sélection
    -- Trend/Regime, Volatility, Volume/Micro, Cyclic
);
SELECT create_hypertable('ml_features', 'timestamp');
```

#### Buckets de features (~55 candidates → 15-30 après sélection)

**Trend & Regime (~12 candidates) :**
- EMA spreads z-scored (20/50, 50/200) sur 1h, 4h, 1d
- SuperTrend distance normalisée (4h)
- ADX multi-TF (1h, 4h, 1d)
- MACD histogram z-score (4h, 1d)
- RSI multi-période (7, 14) sur 4h, 1d

**Volatility (~10 candidates) :**
- Realized volatility (returns std) sur 4h, 24h, 7d
- Vol-of-vol (std de la realized vol)
- Parkinson estimator (basé sur high-low)
- ATR/price ratio (4h, 1d)
- Bollinger width normalisé (4h)

**Volume & Microstructure (~8 candidates) :**
- Volume vs MA(20) z-score (4h, 1d)
- VWAP deviation normalisée
- Ratio (high-low)/close (proxy pression directionnelle)
- Trade count anomaly z-score

**Cyclic & Calendar (~4 candidates) :**
- Heure du jour (sin/cos encoded)
- Jour de la semaine (sin/cos encoded)
- Mois de l'année (sin/cos encoded — 108 observations sur 9 ans)
- ~~months-since-halving~~ **SUPPRIMÉ** (seulement 2 événements dans 9 ans = overfitting garanti)

#### Feature selection
- Permutation importance (sur LightGBM baseline)
- VIF < 5 (éliminer multicolinéarité)
- Forward stepwise selection
- Chaque feature gardée DOIT avoir une justification économique
- **Pas de chiffre magique** — on mesure et on coupe

#### Validation anti look-ahead bias
Script automatique qui vérifie : aucune feature au temps t n'utilise de donnée > t.

#### Calcul
- Batch nightly (reconstruction complète)
- Incrémental sur chaque candle 4h (pour le live)

---

### PHASE 2 — LightGBM Enhancer (4 semaines séquentielles)

**Ordre imposé (impact maximum d'abord) :**

#### 2.1 — Vol Forecaster (10 jours)
- **Target** : realized volatility sur les prochaines 4h et 24h
- **Pourquoi en premier** : la volatilité est autocorrélée → plus facile à prédire que la direction. Impact immédiat sur le spacing de la grid et les multiplicateurs ATR des stops.
- **Modèle** : LightGBM régression
- **Validation** : walk-forward train 6 ans → test 1 an, 3 fenêtres non-chevauchantes
- **Métrique** : RMSE < baseline (vol passée comme prédicteur naïf), R² > 0.3

#### 2.2 — Regime Predictor (10 jours)
- **Target** : régime réel sur les prochaines 24h (5 classes basées sur le return forward réalisé, PAS sur les EMA)
- **Pourquoi** : le régime EMA actuel (`get_regime()`) oscille trop entre BEAR et NEUTRAL. Un classifieur ML devrait être plus stable.
- **Modèle** : LightGBM classification multiclasse
- **Output** : probabilités par classe → remplace `get_regime()` pour les strats actives
- **Validation** : walk-forward 9 ans, accuracy > 45% (5 classes = 20% random), F1-macro > 0.35
- **Fallback** : si confidence < seuil → utiliser le régime EMA classique

#### 2.3 — Signal Filter (8 jours)
- **Target** : binaire — "ce signal BUY sera profitable net fees dans les 48h ?"
- **Pourquoi en dernier** : dépend des 2 modèles précédents comme features additionnelles, et n'existe que pour les stratégies validées en Phase -1
- **Entraîné sur** : signaux historiques des strats survivantes (pas des strats mortes)
- **Modèle** : LightGBM binaire
- **Intégration** : gate dans le GeminiGlobalRiskManager
- **Métrique** : precision > 0.55, et signaux gardés ont un PF > PF baseline

#### Intégration dans le pipeline (les 3 modèles ensemble)
```
Stratégie.generate_signal() → TradingSignal
    ↓
MLSignalEnhancer.evaluate(signal, features)
    → vol_forecast → ajuste ATR multiplier + grid spacing
    → regime_prediction → override get_regime() si confidence > seuil
    → signal_quality → confidence score
    ↓
if confidence < threshold[strategy_id]:
    REJECT signal (log raison)
else:
    adjust position_size via vol_forecast
    ↓
GeminiGlobalRiskManager.process_signal()   # 1% rule + crash protector TOUJOURS actif
    ↓
ExecutionEngine
```

**Fallback 100%** : si ML down, erreur, ou `ml.enabled: false` → le pipeline revient aux règles pures, transparent.

---

### PHASE 3 — Validation & Paper Trading (6-8 semaines)

#### Walk-forward 9 ans (valide le modèle)
- Train 6 ans → test 1 an, 3 fenêtres non-chevauchantes
- Chaque modèle doit être profitable/améliorant sur ≥ 2/3 fenêtres
- **Critères :**
  - Sharpe > 0.5
  - PF > 1.5
  - Amélioration vs rule-based seul sur ≥ 2/3 fenêtres

#### Paper trading A/B 60-70 jours (valide l'intégration)
- **Bot A** : MultiStrategyRouter rule-based seul
- **Bot B** : MultiStrategyRouter + ML enhancer
- Même capital, même seed, métriques en DB
- **Critères GO-LIVE :**
  - Sharpe B ≥ Sharpe A (pas de dégradation)
  - MaxDD B ≤ MaxDD A × 1.1
  - Divergence backtest/paper < 20%
  - Bootstrap 10k resamples : p-value différence Sharpe < 0.05

---

### PHASE 4 — Scaling (Mois 5+)

- Réentraînement automatique mensuel (dimanche 02:00 UTC via systemd timer)
- Drift alert Telegram : PSI > 0.22 ou feature importance shift > 18%
- Extension multi-pair (ETH/USDC, SOL/USDC) avec même feature store
- **Optionnel Q3 2026** : LSTM vol-only si LightGBM plafonne
- **Optionnel Q4 2026** : RL grid optimizer comme projet séparé
- Scaling capital : +5k tous les 30 jours si Sharpe > 0.6 sur 60 jours rolling

---

## 3. CE QU'ON NE FAIT PAS (JAMAIS)

- ❌ Prédiction directionnelle directe (avant que l'enhancer soit validé)
- ❌ LSTM/TFT/PPO/SAC en production (avant mois 6+)
- ❌ Sentiment analysis / NLP / news / Twitter
- ❌ GANs ou données synthétiques
- ❌ Remplacement des règles par ML (ML = overlay, pas remplacement)
- ❌ Modèle "end-to-end" candles → ordres
- ❌ Feature halving (trop peu de datapoints)
- ❌ ML sur stratégies non prouvées en backtest

---

## 4. Stack ML

| Composant | Techno | Raison |
|-----------|--------|--------|
| Feature engineering | pandas + numpy | Simple, rapide |
| Feature store | TimescaleDB (ml_features) | Déjà dans la stack |
| Modèles Phase 2 | LightGBM | Interprétable, rapide, peu de données = pas besoin de DL |
| Tracking expériences | MLflow | Standard, léger |
| Sérialisation | joblib | LightGBM natif |
| Optionnel futur | PyTorch | Seulement pour LSTM vol-only Phase 4 |
| Pas besoin de GPU | — | Modèles petits, inférence légère |

---

## 5. Calendrier réaliste (solo dev)

| Semaines | Phase | Livrable |
|----------|-------|----------|
| 1-4 | Phase -1 | Backtests terminés, strats triées, strategies.yaml mis à jour |
| 5-7 | Phase 0 + 1 | Infrastructure ml/ + Feature Store opérationnel |
| 8-11 | Phase 2 | 3 LightGBM entraînés et validés en walk-forward |
| 12-19 | Phase 3 | Paper trading 60+ jours, A/B test, validation statistique |
| ~Mi-juillet 2026 | GO LIVE | ML enhancer en production sur 1-2k USDC |

---

## 6. Fichiers clés existants (ne pas modifier sans raison)

```
src/krakenbot/
├── strategies/
│   ├── base.py                              # BaseStrategy ABC + TradingSignal
│   ├── multi_strategy_router.py             # ROUTER unique
│   ├── gemini_global_risk_manager.py        # Risk overlay
│   ├── gemini_scalping_volatilite.py        # Strat 1
│   ├── gemini_suivi_tendance_momentum.py    # Strat 3
│   ├── gemini_retour_moyenne.py             # Strat 2
│   ├── grok_grid_atr_adaptive_v4.py         # Strat 4 (grid)
│   ├── grok_supertrend_4h.py                # Strat 5
│   ├── grok_ema_adx_atr.py                  # Strat 6
│   └── grok_adaptive_dca_weekly.py          # Strat 7
├── indicators/
│   └── multi_timeframe.py                   # MultiTimeframeAnalyzer (6 TF, 8 indicateurs)
├── execution/
│   ├── engine.py                            # ExecutionEngine
│   └── risk.py                              # GlobalRiskManager
├── connectors/
│   ├── kraken_rest.py                       # REST via ccxt
│   └── kraken_ws.py                         # WebSocket
scripts/
├── backtest.py                              # BacktestEngine (signal + grid)
strategies.yaml                              # Config multi-stratégie
```
