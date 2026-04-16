# KrakenBot — Roadmap (Avril 2026)

> Roadmap consolidée post-pivot Binance. Remplace ROADMAP_FINAL.md et TODO.md.
> Mise à jour : 16 avril 2026.

---

## Vue d'ensemble

| Phase | Quoi | Durée estimée | Statut |
|---|---|---|---|
| P0 | Audit Binance | 2 jours | ✅ Terminé |
| P1 | Exchange abstraction layer | 3 jours | ✅ Terminé |
| P2 | BinanceRestClient | 3 jours | ✅ Terminé |
| P3 | BinanceWebSocketClient | 4 jours | ✅ Terminé |
| P4 | Collector + DB migration + Binance Vision import | 5 jours | ✅ Terminé |
| P5 | Multi-pair refactor | 5 jours | ✅ Terminé |
| P6 | Backtests Binance (24 combinaisons) | 5-7 jours | 🚧 En cours |
| P7 | Optimisation params + risk management | 3-5 jours | 📋 Planifié |
| P8 | Alertes Telegram + monitoring | 2-3 jours | 📋 Planifié |
| P9 | Paper trading validation (4+ semaines) | 4-6 semaines | 📋 Planifié |
| P10 | Live progressif (1k → 5k → 20k) | Continu | 📋 Planifié |
| P11+ | ML, scalping eval, RL | Mois | 🔮 Futur |

---

## Phases terminées (P0–P5)

### P0 — Audit Binance (tag v1.5.0)
Rapport `results/binance_integration_audit.md` confirmant la faisabilité du pivot. Fees 50% moins chères, API stable, MiCA compliant.

### P1 — Exchange Abstraction (tag v1.5.0-exchange-abstraction)
`ExchangeRestClient` Protocol enrichi, `BaseWebSocketClient` ABC, `ExchangeFees` config centralisée (kraken_defaults, binance_defaults).

### P2 — BinanceRestClient (tag v1.6.0-binance-rest)
Client REST complet, `BinanceSettings`, factory `build_exchange_rest_client`, validé avec vraies API keys.

### P3 — BinanceWebSocketClient (tag v1.7.0-binance-ws)
WebSocket complet, reconnexion préventive 23h, watchdog anti-zombie, alertes Telegram, `_save_ohlc` optionnel via `db_manager`.

### P4 — Collector + DB + Import (tag v1.8.0-binance-vision)
Collector migré vers factory. Migration Alembic : colonne `exchange` + PK 4 colonnes. Script `binance_vision_import.py` avec batch inserts et gestion ms/us timestamps. 8.7M rows Binance importées.

### P5 — Multi-pair Refactor (tag v1.9.0-multi-pair)
`MultiPairAnalyzerRegistry`, router dispatch par pair, strategies pair-aware, collector multi-pair (21 streams), confidence modulation, Donchian activé sur BTC.

---

## Phase en cours

### P6 — Backtests Binance (branche feat/p6-binance-backtests)

**Objectif** : identifier quelles combinaisons (8 stratégies × 3 paires = 24) sont profitables sur Binance.

**Méthodologie** :
1. Première passe : 24 backtests cross-validés (70/30 temporel) sur 3 ans (2023-04 → 2026-04)
2. Filtrage par 5 critères : Sharpe > 1.0, Sortino > 1.5, Max DD < 25%, Profit factor > 1.5, Calmar > 0.5
3. Deuxième passe : walk-forward sur les survivantes (12 mois train / 3 mois test, 8 fenêtres)
4. Benchmarks : Buy & Hold + DCA fixe par paire

**Livrables** :
- `results/P6_backtest_report.md` — rapport avec recommandations
- `notebooks/P6_backtest_analysis.ipynb` — graphes et visualisations

---

## Phases planifiées

### P7 — Optimisation paramètres + Risk management (3-5 jours)

**Objectif** : optimiser les paramètres des stratégies survivantes de P6 ET réviser le risk management.

**Optimisation stratégies** :
- Grid search ciblé sur 1-2 paramètres clés par stratégie survivante
- Cross-validation stricte pour détecter l'overfitting
- Pas de ML, juste de l'optimisation paramétrique classique

**Révision risk management** :
- Max positions global : 25 → ~100 (safeguard, pas limite opérationnelle)
- Daily loss limit : 50 EUR fixe → 5% du capital dynamique
- Risk per trade : 1% → 2% pour capital < 5k USDC
- Min position size : ajouter plancher 10 USDC (Binance MIN_NOTIONAL)
- Daily loss calcul : somme pertes brutes → P&L net réalisé

### P8 — Alertes Telegram + Monitoring (2-3 jours)

- Notification sur chaque trade exécuté (BUY/SELL, montant, P&L)
- Alerte erreur critique / bot stoppé
- Alerte daily loss limit atteinte
- Rapport quotidien P&L par stratégie (optionnel)
- Config : `TELEGRAM_BOT_TOKEN` dans `.env`

### P9 — Paper Trading Validation (4-6 semaines)

**Conditions de démarrage** : stratégies P7-optimisées + alertes P8 en place

**Ce qu'on surveille** :
- P&L réel vs P&L backtesté (drift acceptable < 20%)
- Nombre de trades vs attendu
- Drawdown max observé vs backtesté
- Comportement en conditions de marché extrêmes (si ça arrive)
- Bugs, crashes, reconnexions

**Critères de succès pour passer en live** :
- 4 semaines minimum sans crash
- P&L net positif sur au moins 3 des 4 semaines
- Pas de trade aberrant (position trop grosse, mauvaise paire, etc.)
- Alertes Telegram fonctionnelles

### P10 — Live Progressif

| Palier | Capital | Trigger | Durée min |
|---|---|---|---|
| 1 | 1,000 USDC | Paper concluant (P9) | 30 jours |
| 2 | 5,000 USDC | Palier 1 profitable 30j | 30 jours |
| 3 | 20,000 USDC | Palier 2 profitable 30j | Continu |

Stratégies actives à chaque palier : uniquement celles validées par P6 + P7 + P9.

---

## Phases futures (post-go-live)

### P11 — ML Signal Filter (1-2 mois, Q3 2026)

**Prérequis** : bot profitable en live depuis 2+ mois, données live accumulées.

LightGBM "enhancer" qui filtre les faux signaux :
- Feature store sur les indicateurs techniques normalisés
- Meta-labeling : "ce signal sera-t-il profitable net fees ?"
- Toggle `ml.enabled: false` → zéro risque, fallback sur règles pures
- Walk-forward validation obligatoire

### P12 — Évaluation Scalping (Q3-Q4 2026)

Avec les données live Binance et les fees réelles observées :
- Re-backtester les stratégies scalping (Gemini Scalping Volatilité)
- Tester le mean reversion avec fees BNB
- Si PF > 1.5 → activer avec ML signal filter
- Si toujours perdant → abandonner définitivement

### P13 — ML Vol Forecaster (Q4 2026)

Prédicteur de volatilité réalisée (4h/24h) pour ajuster dynamiquement :
- ATR stops (stops plus larges en haute vol, plus serrés en basse vol)
- Grid spacing (grilles plus larges quand le marché bouge plus)

### P14 — RL Trader + Allocation Dynamique (2027)

- RL directionnel : classifieur "prix plus haut/plus bas dans 4h", comme 8ème stratégie
- Allocation dynamique performance-based : redistribue le capital entre stratégies selon Sharpe rolling

---

## Décisions stratégiques permanentes

1. **Binance définitif** — pas de re-pivot prévu
2. **Pas de ML avant profit live** — P11 après P10 concluant
3. **Chaque stratégie validée** sur 3+ ans de backtest + cross-validate + walk-forward + 4 semaines paper
4. **Scale seulement sur preuve** — 30 jours profitable avant d'augmenter le capital
5. **Sélection darwinienne** — activer large, garder les gagnantes, tuer les perdantes

---

## Petits items restants (non bloquants)

- [ ] Documenter les fees Binance VIP tier (quand le volume augmentera)
- [ ] Nettoyer les données kraken legacy quand le pivot est complètement validé (`DELETE FROM market_data_ohlc WHERE exchange='kraken'`)
- [ ] Rework du dashboard Streamlit/Dash pour afficher multi-pair + P&L par stratégie
- [ ] Ajouter les paires ETH/SOL dans le backfill collector (déjà fonctionnel, juste activer dans la config)
- [ ] Type check mypy : nettoyer les ~97 erreurs `union-attr` héritées dans `main.py`
- [ ] Supprimer les stratégies legacy (threshold_rolling, adaptive, capitulation, bear_short, trend_following) si jamais plus utilisées
