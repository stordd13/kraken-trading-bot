# KrakenBot — Contexte Projet (Avril 2026)

> **Source de vérité unique du projet.** Lire en entier avant de toucher au code ou de lancer un agent.
> Dernière mise à jour : 16 avril 2026, post-P5 (multi-pair refactor), en cours de P6 (backtests Binance).

---

## 1. Vue d'ensemble

KrakenBot est un bot de trading automatisé crypto en cours de pivot complet de **Kraken vers Binance**, avec une refonte multi-paires (BTC/USDC, ETH/USDC, SOL/USDC).

Malgré son nom historique, le bot ne trade plus sur Kraken. Le nom est conservé pour la continuité du repo.

### Objectif final

Bot de trading systématique multi-paires sur Binance, avec :
- 3-5 stratégies actives validées par backtest sur 3-5 ans de données
- Multi-timeframe (5m, 15m, 1h, 4h, 1d, 1w)
- Risk management centralisé
- Monitoring Telegram en temps réel
- Capital initial 1k USDC, scaling progressif vers 20k USDC

### État actuel (avril 2026)

- ✅ P0 à P5 terminées (audit, abstraction layer, REST/WS Binance, multi-pair refactor)
- 🚧 P6 en cours (backtests Binance sur 24 combinaisons)
- 📋 P7-P10 planifiées
- 🤖 Bot tourne en paper mode sur Binance, 3 stratégies actives BTC seulement (grid_atr_v4, supertrend_4h, donchian_btc)

---

## 2. Stack technique

### Langage et runtime
- **Python 3.12+**, full async/await
- **Poetry** pour la gestion des dépendances
- **Decimal** obligatoire pour tous les prix et montants (jamais float)
- **structlog** pour le logging (jamais print, jamais logging stdlib)
- **UTC** pour tous les timestamps

### Persistence
- **PostgreSQL 16** avec **TimescaleDB** extension (hypertables pour les séries temporelles)
- **SQLAlchemy 2.0 async** + **asyncpg** comme driver
- **Alembic** pour les migrations
- DB en production tourne dans un **container Docker** sur le serveur Hetzner, exposée uniquement sur `127.0.0.1:5432` (sécurité)

### Connectivité exchange
- **ccxt** pour les appels REST (Binance, Kraken legacy)
- **websockets** pour les flux WebSocket temps réel (Binance combined streams)

### Code quality
- **Ruff** pour lint et format
- **mypy** pour le type checking (quelques erreurs union-attr historiques à nettoyer)
- **pytest** pour les tests (1091 tests passent post-P5)
- **CI/CD** via GitHub Actions sur push vers `dev` et `main`

---

## 3. Infrastructure

### Serveur de production
- **Hetzner Cloud CX33** : 4 vCPU AMD, 8 GB RAM, 80 GB disque, 7.55 €/mois
- Ubuntu LTS, accès SSH via port custom 41922 (port 22 bloqué par UFW)
- Swap 2 GB permanent
- Container Docker `krakenbot-db` (timescale/timescaledb:latest-pg16) bind sur `127.0.0.1:5432`
- 2 services systemd : `krakenbot-collector.service` et `krakenbot.service`

### Accès distant à la DB depuis le local
Tunnel SSH obligatoire :
```bash
autossh -M 0 -f -N -L 127.0.0.1:5433:localhost:5432 bruno@77.42.90.102 -p 41922 \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=60
```
Le `.env` local contient `DATABASE_URL=postgresql+asyncpg://krakenbot:<password>@localhost:5433/krakenbot`.

### Sécurité
- Postgres bind sur localhost uniquement (pas exposé publiquement)
- UFW actif : seul le port SSH 41922 est ouvert
- Accès SSH par clé ed25519 uniquement
- API keys Binance read-only pour le dev, write-keys uniquement en live validé

---

## 4. Architecture du bot

### Deux services indépendants

**Collector** (`python -m krakenbot.collector`) :
- Tourne 24/7, collecte candles OHLC via WebSocket Binance combined streams
- 3 paires × 7 timeframes = 21 streams
- Écrit dans `market_data_ohlc` avec `exchange='binance'`

**Trader** (`python -m krakenbot`) :
- Start/stop, lit les candles via son propre WebSocket
- Orchestre les stratégies via le `MultiStrategyRouter`
- Émet les ordres via `ExecutionEngine` → Binance REST
- En mode paper, simule les ordres en mémoire

Les deux communiquent uniquement via la DB.

### Multi-pair architecture (P5)

**MultiPairAnalyzerRegistry** : maintient un `dict[pair, MultiTimeframeAnalyzer]`, création lazy, accès via `registry.get(pair)`.

**MultiTimeframeAnalyzer** : indicateurs sur 6 TF (5m→1w). API : `get_ema()`, `get_rsi()`, `get_atr()`, `get_macd()`, `get_bollinger()`, `get_adx()`, `get_supertrend()`, `get_regime()`.

**MultiStrategyRouter** : seule BaseStrategy dans l'EventBus, dispatch par pair, applique le risk overlay sur chaque BUY.

### Stratégies pair-aware

Toutes héritent de `BaseStrategy(pair=...)`. Une même classe peut être instanciée N fois avec des paires différentes. Chaque instance a son `bot_id`, positions, et logs propres.

### Risk management

#### Paramètres actuels (définis pour 1k USDC mono-pair, à revoir en P7)

**Niveau global** :
- Max positions ouvertes : 25 (à remonter à ~100 en P7 — avec 3 paires × grid 12 niveaux, 25 est trop bas)
- Perte journalière max : 50 EUR fixe (à convertir en 5% du capital dynamique en P7)
- Exposition max : 90% du capital

**Niveau stratégie** (StrategyBudget) :
- `max_allocation_pct` : % max du capital par stratégie
- `max_open_positions` : positions max simultanées par stratégie

**GeminiGlobalRiskManager** (overlay sur chaque BUY) :
- Sizing : `position_size = (capital × risk_pct × confidence) / |entry - stop_loss|`
- `risk_pct` : 1% actuellement (conservateur pour 1k USDC — envisager 2% pour petits comptes en P7)
- Stop-loss ATR : `SL = entry - 3.0 × ATR(14, 4h)` du pair concerné
- Crash Protector : chute ≥ 7% en 30 min → ferme 50% longs + suspend 2h

**Confidence modulation** (P5) :
- `confidence` (0.3 à 1.0) module la taille de position
- Plancher à 0.3 pour éviter des positions ridiculement petites

#### Révisions prévues en P7

| Paramètre | Actuel | Cible P7 | Raison |
|---|---|---|---|
| Max positions global | 25 | ~100 | Safeguard anti-bug, pas limite opérationnelle |
| Daily loss limit | 50 EUR fixe | 5% du capital (dynamique) | Scale automatiquement avec le capital |
| Risk per trade | 1% | 2% si capital < 5k, 1% sinon | Positions viables avec petit capital |
| Min position size | Aucun | 10 USDC | MIN_NOTIONAL Binance, évite rejets |
| Daily loss calcul | Somme pertes brutes | P&L net réalisé | Scalper profitable non stoppé à tort |
| Limites par pair | Aucun | À envisager | Éviter surconcentration sur 1 pair |

---

## 5. Fees Binance (CRITIQUE pour tout backtest)

| Type | Fee standard | Fee avec BNB discount |
|---|---|---|
| BUY/SELL limit (maker) | 0.10% | 0.075% |
| BUY/SELL market (taker) | 0.10% | 0.075% |

Le compte Binance a le BNB discount activé → on backtest avec **0.075%**.

Avec spread (0.02%) + slippage (0.01%) → round-trip réaliste : **~0.18%** (vs ~0.35% sur Kraken).

---

## 6. Base de données

### Schema principal

**market_data_ohlc** (hypertable TimescaleDB) :
- PK : `(timestamp, pair, interval, exchange)`
- Colonnes : open, high, low, close, volume, vwap, trades_count
- Chunks mensuels

**Volumes actuels (avril 2026)** :
- `exchange='binance'` : ~8.7M rows (BTC/ETH/SOL × 7 TF × 5 ans)
- `exchange='kraken'` : ~1.13M rows (legacy, à supprimer quand pivot validé)

**Filtre obligatoire** : tout code de production filtre sur `exchange='binance'`.

**Note SOL** : données SOL démarrent le 24 sept 2021.

### Import de données historiques

Script `scripts/binance_vision_import.py` — télécharge depuis data.binance.vision, gère ms/us timestamps, batch inserts de 1000 rows, idempotent (ON CONFLICT DO NOTHING).

### Migrations

Dernière : `f7a8b9c0d1e2`. Attention aux ALTER TABLE sur hypertables : augmenter `maintenance_work_mem` et vérifier le swap avant.

---

## 7. Stratégies disponibles

8 stratégies implémentées, toutes pair-aware. Statut à valider par P6.

| Classe | Type | TF | Statut |
|---|---|---|---|
| `grok_grid_atr_adaptive_v4` | Grid | multi-TF | Active BTC |
| `grok_supertrend_4h` | Trend following | 4h+1d | Active BTC |
| `grok_donchian_breakout_4h` | Breakout | 4h+1d | Active BTC |
| `grok_ema_adx_atr` | EMA cross | 4h+1d | Inactive |
| `grok_adaptive_dca_weekly` | DCA hebdo | 1d | Inactive |
| `gemini_scalping_volatilite` | Scalping | 5m+1h | Inactive (re-tester Binance) |
| `gemini_suivi_tendance_momentum` | Pullback EMA | 4h+1d | Inactive |
| `gemini_retour_moyenne` | Mean reversion BB | 15m+1h | Inactive (re-tester Binance) |

---

## 8. Roadmap

### Terminées : P0–P5

### En cours : P6 (backtests Binance, 24 combinaisons)

### Planifiées : P7 (optim params + risk mgmt), P8 (Telegram), P9 (paper 4+ sem), P10 (live)

### Futures : P11 (ML signal filter), P12 (éval scalping), P13 (ML vol), P14 (RL + alloc dynamique)

---

## 9. Leçons historiques

- **Grid trading** : seule approche profitable sur Kraken. À reconfirmer sur Binance.
- **min_spacing ≥ 1.5%** : critique pour couvrir les fees.
- **Mean reversion 5m/15m** : mortes sur Kraken, à re-tester sur Binance (fees -50%).
- **Stops ATR-based** : supérieurs aux % fixes.
- **HFT / trailing < 5% / grid sans biais en bear** : ne marchera jamais.

---

## 10. Règles d'or

1. **Decimal** pour montants, **structlog** pour logs, **normalize_pair** pour paires.
2. **Filtrer** `exchange='binance'` dans toutes requêtes DB de production.
3. **Batcher** les inserts SQL (~1000 rows max).
4. **Tester en paper** avant live, **3+ ans de backtest** avant paper.
5. **Ne JAMAIS commit** `.env` ni credentials.
6. **Ne JAMAIS modifier** MultiStrategyRouter/GeminiGlobalRiskManager/ExecutionEngine sans review humain.
7. **Lire le code existant** avant d'écrire.
