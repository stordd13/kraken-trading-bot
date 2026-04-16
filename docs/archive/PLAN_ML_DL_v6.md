# KrakenBot — Plan ML/DL v6.0 (Mars–Août 2026)

> **Document de référence unique.** Mis à jour avec les résultats réels de backtest (Phase -1A, 1B, multi-pair).
> Remplace le v5.0.

---

## 0. Portfolio validé (résultats réels, Mars 2026)

### Stratégies actives

| Stratégie | BTC (9 ans) | ETH (8.5 ans) | SOL (5.5 ans) | Statut |
|-----------|-------------|---------------|---------------|--------|
| **SuperTrend 4h** (200 USDC) | Sharpe 0.49, PF 2.81, MaxDD 6.3% | Sharpe 0.35, PF 1.97, MaxDD 11.6% | Sharpe 0.41, PF 2.57, MaxDD 11.9% | **KEEP × 3 pairs** |
| **Grid ATR V4** (25 USDC) | +1643%, surperforme B&H | — | — | **KEEP BTC only** |
| **EMA Cross 4h** (40 USDC, EMAs 20/50) | Sharpe 0.43, PF 3.54, 50 trades | Sharpe 0.28 | Sharpe 0.15 | **KEEP BTC only** |
| **DCA Weekly** (15 USDC/sem) | Sharpe 0.74, +802% | BUG (0 trades) | BUG (0 trades) | **KEEP BTC + fix multi-pair** |
| Donchian 4h (50 USDC) | Sharpe 0.32 | KILL (0.12) | WATCH (0.28) | **WATCH SOL, park others** |

### Stratégies éliminées (10 strats)

| Stratégie | Raison | Définitif ? |
|-----------|--------|-------------|
| GeminiScalpingVolatilite (5m) | PF 0.14, fees > gains | **Re-tester sur Bybit** |
| GeminiRetourMoyenne (15m) | PF 0.08, quasi-inerte | **Re-tester sur Bybit** |
| GeminiSuiviTendanceMomentum (4h) | PF 0.52, bug pullback | Définitif (même corrigée, perdante) |
| Ichimoku Cloud 4h | Sharpe 0.16, trop de faux breakouts | Définitif |
| VWAP Trend 4h | PF 1.22, fees détruisent l'edge | **Re-tester sur Bybit** |
| Toutes les legacy (5 strats) | Abandonnées avant Phase -1A | Définitif |

### Benchmark
- Buy-and-hold BTC 9 ans : +1304%
- Buy-and-hold ETH 8.5 ans : +560%
- Buy-and-hold SOL 5.5 ans : +2500%

### Trade count total (pour ML training)
SuperTrend : 107 (BTC) + 110 (ETH) + 71 (SOL) = **288 trades**
EMA Cross : 50 (BTC) + 57 (ETH) + 35 (SOL) = **142 trades**
Grid : 410 pairs (BTC) = **410 trades**
**Total : ~840 trades** pour entraîner le signal filter.

---

## 1. Philosophie ML (inchangée)

1. ML = optimiseur d'alpha existant (SuperTrend + Grid + EMA Cross)
2. Fees = ennemi #1 (0.32% Kraken, 0.20% Bybit futur)
3. 9 ans de données 1h+ = avantage pour walk-forward
4. Un seul modèle actif en prod : LightGBM enhancer
5. Toggle `ml.enabled: false` → zéro risque
6. Fallback systématique : ML down → règles pures

---

## 2. Phases ML

### PHASE 0 — Infrastructure (1 semaine)

```
src/krakenbot/ml/
├── __init__.py
├── features/
│   └── feature_store.py
├── models/
│   └── lightgbm/
│       ├── vol_forecaster.py
│       ├── regime_predictor.py
│       └── signal_filter.py
├── inference/
│   └── enhancer.py
├── monitoring/
│   └── drift.py
└── mlflow/
```

Section strategies.yaml :
```yaml
ml:
  enabled: false
  mode: "enhancer"
  confidence_threshold: 0.62
  retrain_every: "30d"
  fallback_on_error: true
```

Extension MultiTimeframeAnalyzer : `get_features_dict(tf)` retournant tous les indicateurs normalisés.

### PHASE 1 — Feature Store (3 semaines)

Table `ml_features` (TimescaleDB hypertable). Calcul batch nightly + incrémental 4h.

**Features (~55 candidates → 15-30 après sélection) :**

Trend & Regime : EMA spreads z-scored multi-TF, SuperTrend distance, ADX, MACD histogram, RSI multi-période.

Volatility : realized vol 4h/24h/7d, vol-of-vol, Parkinson, ATR/price ratio, Bollinger width.

Volume & Micro : volume vs MA(20) z-score, VWAP deviation, high-low/close ratio.

Cyclic : sin/cos heure + jour semaine + mois.

**Données externes (NOUVEAU — faciles à intégrer) :**
- Fear & Greed Index (daily, API gratuite alternative.me/crypto/fear-and-greed-index)
- Intégrer comme feature dans le regime predictor
- Cron daily pour télécharger, stocker dans une table `ml_external_data`
- Potentiellement prédictif en extrêmes (Fear < 20, Greed > 80)

Feature selection : permutation importance + VIF < 5 + forward stepwise.
Validation anti look-ahead : script automatique.

### PHASE 2 — LightGBM Enhancer (4 semaines séquentielles)

**2.1 Vol Forecaster (10 jours)** → realized vol 4h/24h → ajuste ATR stops + grid spacing.
**2.2 Regime Predictor (10 jours)** → régime +24h (5 classes) → remplace get_regime(). Inclut Fear & Greed Index comme feature.
**2.3 Signal Filter (8 jours)** → "ce signal sera-t-il profitable net fees ?" → gate dans le risk manager. Entraîné sur les ~840 trades historiques cross-pair.

Intégration :
```
generate_signal() → TradingSignal
    ↓
MLSignalEnhancer.evaluate(signal, features)
    → vol_forecast → ajuste ATR + spacing
    → regime → override si confidence > seuil
    → signal_quality → accept/reject
    ↓
GeminiGlobalRiskManager (1% rule + crash protector)
    ↓
ExecutionEngine
```

### PHASE 3 — Validation (6-8 semaines)

Walk-forward 9 ans : train 6 ans → test 1 an, 3 fenêtres. Sharpe > 0.5, PF > 1.5 sur ≥ 2/3 fenêtres.
Paper trading 60-70 jours A/B. Bootstrap p < 0.05.

### PHASE 4 — Scaling (Mois 5+)

Réentraînement mensuel. Drift alerts. Multi-pair automatique.

---

## 3. ROADMAP STRATÉGIQUE (au-delà du ML)

> **Section critique — ne pas oublier. Ces décisions ont potentiellement plus d'impact que le ML.**

### 3.1 Migration Bybit (priorité haute, mois 3-4)

**Pourquoi :** Fees maker 0.10% vs 0.16% Kraken = round-trip 0.20% vs 0.32% = **37% de fees en moins.**

**Impact estimé :**
- Grid ATR : chaque pair génère +37% de profit net (fees = coût #1 de la grid)
- SuperTrend : PF augmente mécaniquement (même gains, moins de fees)
- Strats "mortes" à re-tester : scalping 5m, mean-reversion 15m, VWAP trend — toutes tuées par les fees, potentiellement viables avec 0.20% round-trip

**Plan migration :**
1. ccxt supporte Bybit nativement → changement de connector relativement propre
2. Re-backtester TOUTES les stratégies (actives + mortes) avec fees Bybit
3. Paper trading 2 semaines sur Bybit avant live
4. Garder Kraken comme fallback

**Fees VIP Bybit (avec volume) :**
- Base : 0.10% maker / 0.10% taker
- VIP1 (1M$/mois) : 0.08% / 0.09%
- VIP2 (5M$/mois) : 0.06% / 0.08%
- Market maker program : 0.00% maker possible

### 3.2 Scaling capital (quand stratégie validée)

**Contexte :** Le capital actuel (1000 USDC) est pour tester. Le owner peut déployer 20k+ USDC dès qu'une stratégie fait 10%+/mois de manière consistante.

**Plan de scaling :**
- Validation : stratégie profitable sur 2+ mois de paper trading
- Step 1 : 1k → 5k USDC (×5, risque limité)
- Step 2 : 5k → 20k USDC (après 30 jours profitable à 5k)
- Step 3 : 20k+ USDC (après 60 jours profitable à 5k+)
- Le SuperTrend scale linéairement (vérifié : PF constant à 50/100/150/200 USDC)

**Impact du scaling sur les fees :**
- Plus de volume = tiers de fees plus bas sur Bybit
- À 20k USDC avec 5-10 trades/jour, le volume mensuel peut atteindre les tiers VIP
- Les fees basses rendent le scalping viable → nouveau territoire de stratégies

### 3.3 Scalping revival (après migration Bybit + capital)

**Pourquoi c'est mort aujourd'hui :** fees 0.32% round-trip, moves moyens 5m ~0.3%, pas de données Level 2.

**Pourquoi ça pourrait revivre :**
- Bybit fees 0.20% (ou moins avec VIP) → le seuil de rentabilité baisse de 40%
- Capital 20k+ = position sizes plus grosses = les petits moves deviennent significatifs en absolus
- Le ML vol forecaster peut identifier les périodes de haute vol (moves > 0.5%) = scalping sélectif
- Bybit a des WebSocket plus rapides et un meilleur carnet d'ordres que Kraken

**Plan :**
- NE PAS implémenter maintenant
- Après migration Bybit : re-backtester GeminiScalpingVolatilite et une strat RSI mean-reversion avec fees Bybit
- Si PF > 1.5 → implémenter avec ML signal filter
- Si toujours perdant → abandonner définitivement le scalping

### 3.4 RL Trader directionnel (long terme, mois 6+)

**Concept :** classifieur binaire "prix plus haut ou plus bas dans 4h" → 1 trade par candle.

**Pourquoi pas maintenant :**
- Accuracy nécessaire ~60% pour être profitable avec fees actuelles
- Meilleurs modèles académiques : 53-56% hors-échantillon
- 19k candles 4h = overfitting quasi-garanti avec du deep learning
- Le marché est non-stationnaire (BTC 2017 ≠ BTC 2024)

**Pourquoi ça pourrait marcher plus tard :**
- Fees Bybit basses → accuracy nécessaire baisse à ~55%
- Le feature store ML sera mature (features validées, anti look-ahead)
- Plus de données (multi-pair = 3× les candles)
- Comme 8ème stratégie dans le router (budget limité, kill si perdant)

**Plan :**
- NE PAS implémenter avant que le ML enhancer soit en production et validé (mois 4+)
- Implémenter comme stratégie indépendante dans le router, PAS comme remplacement
- Budget : 50 USDC/trade, max 10% capital
- Évaluation : 3 mois de backtest + 2 mois paper
- Si Sharpe < 0.3 après 3 mois → kill

### 3.5 Données alternatives (moyen terme)

| Source | Effort | Impact attendu | Quand |
|--------|--------|---------------|-------|
| Fear & Greed Index | Faible (1 API, 1 cron) | Modéré (feature regime) | **Phase 1 ML** |
| Funding rates (Bybit perps) | Faible | Modéré (sentiment dérivés) | Après migration Bybit |
| Open Interest | Faible | Modéré (positioning) | Après migration Bybit |
| On-chain (whale movements) | Élevé | Incertain | Pas prioritaire |
| Twitter/Reddit sentiment | Très élevé | Incertain | Pas recommandé (dev solo) |

---

## 4. CE QU'ON NE FAIT PAS (pour l'instant)

- ❌ Scalping sur Kraken (fees trop élevées)
- ❌ RL/DL en production (pas avant mois 6)
- ❌ Sentiment social NLP (trop complexe pour un dev solo)
- ❌ Short/margin (BearShort a échoué, pas de données de levier)
- ❌ Remplacement des règles par ML

## 5. Calendrier révisé

| Période | Action |
|---------|--------|
| Sem 1-2 | Phase 0+1 ML (infra + features) + fix DCA multi-pair |
| Sem 3-6 | Phase 2 ML (3 LightGBM) |
| Sem 7-14 | Phase 3 ML (paper 60j) + paper multi-pair |
| Mois 4 | GO LIVE ML enhancer 1-3k USDC |
| Mois 4-5 | Migration Bybit + re-backtest all strats avec fees Bybit |
| Mois 5 | Scale capital 5-20k si profitable |
| Mois 6+ | Re-évaluer scalping + RL trader sur Bybit |
