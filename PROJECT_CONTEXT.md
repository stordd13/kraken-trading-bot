# KrakenBot — Contexte Projet (Septembre 2026)

> **Source de vérité unique du projet.** Lire en entier avant de toucher au code ou de lancer un agent.
> Dernière mise à jour : 8 septembre 2026, post-B0.5 (refonte docs + cleanup legacy), avant B1 (connecteur Bybit).

---

## 1. Vue d'ensemble

KrakenBot est un bot de trading spot automatisé multi-paires (BTC/USDC, ETH/USDC, SOL/USDC) en cours de
pivot vers **Bybit EU**. Le nom est historique : le bot a démarré sur Kraken (2025), a pivoté vers Binance
en avril 2026 (fees 0.075 %, refonte multi-pair), puis Binance a retiré sa demande MiCA et suspendu ses
services aux résidents UE le 1er juillet 2026. Bybit EU (Bybit EU GmbH, agréé MiCA via la FMA Autriche)
a été retenu en septembre 2026 après audit (B0). Le détail du choix et des décisions vit dans
`docs/archive/PIVOT_BYBIT_PLAN.md` et `results/bybit_integration_audit.md`.

### Objectif final

Bot de trading systématique multi-paires sur Bybit EU, avec :
- 3-5 stratégies actives validées par backtest sur 3-5 ans de données (fees Bybit)
- Multi-timeframe (5m, 15m, 1h, 4h, 1d, 1w)
- Risk management centralisé
- Monitoring Telegram en temps réel
- Capital initial 1k USDC, scaling progressif vers 20k USDC

### État actuel (8 septembre 2026)

- ✅ P0 à P6 terminées (audit, abstraction layer, REST/WS Binance, multi-pair, backtests 24 combos)
- ✅ P7 phase 1 terminée (30 mai 2026 : 212 jobs de grid search cross-validés, fees Binance)
- ✅ B0 audit Bybit EU (7 sept, verdict GO avec réserves) · ✅ B0.5 docs + cleanup (cette version)
- ⏸️ **Serveur Hetzner : services `krakenbot` et `krakenbot-collector` stoppés et désactivés** depuis le
  7 sept. DB intacte, backupée (203 Mo, rapatriée). Redémarrage prévu en B2/B3 avec le connecteur Bybit.
- 🚧 Prochaine phase : B1 (REST Bybit). Aucune clé API Bybit dans le `.env` à ce jour.
- ⚠️ Les résultats P6/P7 (fees Binance 0.075 % flat) ne sont **pas transposables** aux fees Bybit
  (maker/taker asymétriques) : tout est rejoué en B4 avant tout paper trading.

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
- DB en production dans un **container Docker** sur le serveur Hetzner, exposée uniquement sur
  `127.0.0.1:5432` (sécurité)

### Connectivité exchange
- **ccxt** pour les appels REST (Binance existant, Bybit à venir avec `hostname="bybit.eu"`, Kraken legacy)
- **websockets** pour les flux temps réel (Binance combined streams existant ; Bybit v5 public à venir)
- Sélection par `settings.exchange_name` + factory `connectors/exchange.py`

### Code quality
- **Ruff** pour lint et format (`notebooks/` exclus)
- **mypy** strict (quelques erreurs `union-attr` historiques, voir dettes)
- **pytest** : 967 tests collectés post-B0.5 (936 passent, 31 skippés sans tunnel DB)
- **CI/CD** via GitHub Actions sur push vers `dev` et `main` (lint/tests sur `src/`, deploy sur `main`)

---

## 3. Infrastructure

### Serveur de production
- **Hetzner Cloud CX33** : 4 vCPU AMD, 8 GB RAM, 80 GB disque, 7.55 €/mois
- Ubuntu LTS, accès SSH via port custom 41922 (port 22 bloqué par UFW)
- Swap 2 GB permanent
- Container Docker `krakenbot-db` (timescale/timescaledb:latest-pg16) bind sur `127.0.0.1:5432`
- 2 services systemd : `krakenbot-collector.service` et `krakenbot.service` — **stoppés et désactivés**
  (état B0.5). Le workflow `deploy.yml` régénère le `.env` serveur depuis les GitHub Secrets avec un
  template encore Kraken-era (sans `EXCHANGE_NAME`) : à corriger en B1/B2 avant réactivation.

### Backup
- Dump complet du 7 sept 2026 : `~/Backups/krakenbot/krakenbot_20260907.dump` (203 Mo, `pg_dump -Fc`).
- Procédure de restore TimescaleDB (`timescaledb_pre_restore()` / `pg_restore --no-owner` /
  `timescaledb_post_restore()`, même version majeure d'extension) : `skills/database.md`.
- Pas de backup récurrent : item roadmap, requis avant B5.

### Accès distant à la DB depuis le local
Tunnel SSH obligatoire (`localhost:5433` → serveur `5432`), `.env` local avec
`DATABASE_URL=...@localhost:5433/krakenbot`. Détail : `skills/database.md`.

### Sécurité
- Postgres bind sur localhost uniquement (pas exposé publiquement)
- UFW actif : seul le port SSH 41922 est ouvert
- Accès SSH par clé ed25519 uniquement
- Clés API : read-only pour le dev, write-keys uniquement en live validé, IP whitelist = IP Hetzner

---

## 4. Architecture du bot

Flux d'un trade, multi-pair et conventions : `docs/architecture.md`. Où est quoi : `docs/CODE_MAP.md`.

### Deux services indépendants

**Collector** (`python -m krakenbot.collector`) : 24/7, candles OHLC par WebSocket (3 paires × 7 TF = 21
streams), écrit dans `market_data_ohlc` avec `exchange = settings.exchange_name`.

**Trader** (`python -m krakenbot`) : start/stop, lit les candles via son propre WebSocket, orchestre les
stratégies via le `MultiStrategyRouter` (seule stratégie top-level depuis B0.5), émet les ordres via
`ExecutionEngine` → REST exchange. En mode paper, simule les ordres en mémoire.

Les deux communiquent uniquement via la DB.

### Multi-pair architecture (P5)

**MultiPairAnalyzerRegistry** : `dict[pair, MultiTimeframeAnalyzer]`, création lazy, accès `registry.get(pair)`.
**MultiTimeframeAnalyzer** : indicateurs sur 6 TF (5m→1w).
**MultiStrategyRouter** : seule BaseStrategy dans l'EventBus, dispatch par pair, applique le risk overlay
sur chaque BUY. Toutes les stratégies sont pair-aware (`BaseStrategy(pair=...)`, `bot_id` unique par instance).

### Risk management

#### Paramètres actuels (définis pour 1k USDC mono-pair, à revoir en P7/B4)

**Niveau global** : max 25 positions ouvertes (cible ~100), perte journalière max 50 EUR fixe (cible 5 %
du capital), exposition max 90 %.
**Niveau stratégie** (StrategyBudget) : `max_allocation_pct`, `max_open_positions`.
**GeminiGlobalRiskManager** (overlay sur chaque BUY) : sizing
`position_size = (capital × risk_pct × confidence) / |entry - stop_loss|`, `risk_pct` 1 %, SL ATR
`entry - 3.0 × ATR(14, 4h)` du pair concerné, crash protector (chute ≥ 7 % en 30 min → ferme 50 % des
longs + suspend 2 h), confidence 0.3–1.0.

#### Révisions prévues en P7/B4

| Paramètre | Actuel | Cible | Raison |
|---|---|---|---|
| Max positions global | 25 | ~100 | Safeguard anti-bug, pas limite opérationnelle |
| Daily loss limit | 50 EUR fixe | 5 % du capital (dynamique) | Scale automatiquement avec le capital |
| Risk per trade | 1 % | 2 % si capital < 5k, 1 % sinon | Positions viables avec petit capital |
| Min position size | Aucun | 5 USDC (Bybit `minOrderAmt`), viser 10 | Évite rejets et trades mangés par les fees |
| Daily loss calcul | Somme pertes brutes | P&L net réalisé | Scalper profitable non stoppé à tort |
| Sorties MARKET | Coût = maker | Taker 0.25 % = 2.5× maker | Doctrine des stops à re-valider (B4) |
| Limites par pair | Aucun | À envisager | Éviter surconcentration sur 1 pair |

---

## 5. Fees Bybit EU (CRITIQUE pour tout backtest)

Vérifiées sur le compte (spot, VIP0) :

| Type | Fee |
|---|---|
| Maker (limit, PostOnly) | **0.10 %** |
| Taker (market) | **0.25 %** |
| Spread simulé | 0.02 % |
| Slippage simulé | 0.02 % |

Round-trip limit/limit **0.20 %**, limit/market (stop-loss, trailing, timeout) **0.35 %**. Les sorties
MARKET sont le premier poste de coût : les backtests doivent utiliser maker et taker **distincts**.

Contexte historique : les backtests P6 et P7 phase 1 ont été faits avec les fees Binance BNB
**0.075 % flat** (round-trip ~0.18 %). Les fees Kraken (0.16 / 0.26 %) sont le défaut de `ExchangeFees()` nu.

---

## 6. Base de données

### Schema principal

**market_data_ohlc** (hypertable TimescaleDB) :
- PK : `(timestamp, pair, interval, exchange)`
- Colonnes : open, high, low, close, volume, vwap, trades_count (nullable — Bybit n'en fournit pas)
- Chunks mensuels ; `timestamp` = fin de période (`open + interval`, Bybit `end + 1 ms`)

**Volumes (septembre 2026)** :
- `exchange='binance'` : ~8.7M rows (BTC/ETH/SOL × 7 TF, 2021-01 → 2026-06) — **base de backtest, figée**
- `exchange='kraken'` : ~1.13M rows (legacy, à supprimer quand Bybit est validé en live)
- `exchange='bybit'` : **valeur cible**, 0 row avant B3 (historique EU depuis 2025-06-11, ~2.5M candles)

**Filtre obligatoire** : le code de production filtre sur `settings.exchange_name` (cible `bybit`) ; les
backtests lisent explicitement `exchange='binance'`.

### Import de données

- Binance Vision (historique, figé) : `scripts/binance_vision_import.py` — `skills/binance_import.md`.
- Bybit (B3) : `scripts/bybit_kline_import.py` à écrire, REST paginé — `skills/bybit.md`.

### Migrations

Dernière : `f7a8b9c0d1e2`. ALTER TABLE sur hypertables : augmenter `maintenance_work_mem`, vérifier le swap,
jamais via tunnel. Procédures : `skills/database.md`.

---

## 7. Stratégies disponibles

8 stratégies pair-aware, toutes internes au `MultiStrategyRouter`. Les 10 stratégies legacy Kraken-era
(threshold_rolling, adaptive, capitulation, bear_short, trend_following, grid_spot, grid_adaptive,
supertrend_short, ichimoku_cloud, vwap_trend) ont été supprimées en B0.5, ainsi que le connecteur Kraken
Futures. Statut à revalider en B4 avec les fees Bybit.

| Classe | Type | TF | Statut (P6/P7, fees Binance) |
|---|---|---|---|
| `grok_grid_atr_adaptive_v4` | Grid | multi-TF | Configurée BTC/ETH ; P7 grid search fait |
| `grok_supertrend_4h` | Trend following | 4h+1d | Configurée BTC/ETH/SOL ; P7 grid search fait |
| `grok_donchian_breakout_4h` | Breakout | 4h+1d | Configurée BTC/ETH/SOL ; P7 grid search fait |
| `grok_ema_adx_atr` | EMA cross | 4h+1d | Configurée BTC ; marginal |
| `grok_adaptive_dca_weekly` | DCA hebdo | 1d | Configurée BTC ; P7 grid search fait |
| `gemini_scalping_volatilite` | Scalping | 5m+1h | KILL 1A — conservée pour réévaluation P12 |
| `gemini_suivi_tendance_momentum` | Pullback EMA | 4h+1d | KILL 1A (bug pullback connu) |
| `gemini_retour_moyenne` | Mean reversion BB | 15m+1h | KILL 1A — conservée pour réévaluation P12 |

Aucune stratégie n'est active tant que le serveur est stoppé. P6 : 0/24 combos ont passé les 5 critères
stricts (rapport v2) — d'où le grid search P7 puis le re-run B4.

---

## 8. Roadmap

Détail : `ROADMAP.md`.

- **Terminées** : P0–P6 (pivot Binance, multi-pair, backtests), P7 phase 1, B0 (audit Bybit), B0.5 (docs).
- **À venir** : B1 REST Bybit → B2 WS → B3 data/collector → **B4 re-run P6 + P7 fees Bybit** → B5 paper
  4+ semaines (+ P8 Telegram) → P10 live progressif.
- **Futures** : P11 (ML signal filter), P12 (éval scalping avec fees réelles), P13 (ML vol), P14 (RL + alloc dynamique).

---

## 9. Dettes connues (documentées, pas fixées en B0.5)

1. **`settings.exchange_name` default `"kraken"`** (`src/krakenbot/config/settings.py`, champ
   `exchange_name`) et `trading.pair` default `"XBT/USDC"`. Incident du 7 sept 2026 : au reboot, les
   services ont redémarré sur Kraken car le `.env` serveur (généré par `deploy.yml`) ne fixait pas
   `EXCHANGE_NAME` ; le `.env` local non plus. **B1** : default → erreur explicite si non défini, ou
   default `bybit` ; mettre à jour `deploy.yml` et `.env.example` (encore Kraken-era).
2. **`scripts/backtest.py` : fees flat.** `BacktestEngine.__init__` et `GridBacktester.__init__`
   choisissent `ExchangeFees.binance_defaults(use_bnb=True)` (maker = taker = 0.075 %) ou `ExchangeFees()`
   nu (= Kraken) ; `settings.exchange_fees` est ignoré ; rollover `0.0001`/4h en dur. **B4 exige maker
   et taker distincts** (sorties SL/trailing/timeout = MARKET = taker 0.25 %). À faire en B1 ou en
   ouverture de B4.
3. **`TaskScheduler` hardcode `KrakenRestClient`** (`src/krakenbot/scheduler/task_scheduler.py`,
   import + instanciation) au lieu de la factory, et importe `scripts.fetch_ohlc` depuis `src/`. Le
   backfill automatique n'a jamais marché pour Binance. À généraliser via factory en **B3**.
4. **Restore TimescaleDB non trivial** — procédure documentée dans `skills/database.md`.
5. **Backup DB récurrent absent** — cron + rotation + storage box, requis avant **B5**.
6. **mypy `union-attr`** : 10 erreurs dans `main.py` (13 avant B0.5), 15 sur `src/` (21 avant). Le
   « ~97 » historique était périmé.
7. **`execution/` dépend de `connectors/kraken/rest.py`** : `order_manager.py` et `risk.py` importent
   `normalize_asset_balances` / `normalize_asset_symbol` (normaliseurs Kraken appliqués à tous les
   exchanges) ; `engine.py` type-hint `KrakenRestClient`. À généraliser en B1.
8. **Defaults `exchange="binance"`** dans `indicators/multi_timeframe.py` et `multi_pair_registry.py`
   (warmup) : à passer par `settings.exchange_name` en B3.
9. **`BacktestEngine` garde un chemin `is_multi` mort** (multi-position legacy, toujours `False`
   depuis B0.5) et `GridBacktester` un `_check_directional_pause` inutilisé — à nettoyer avec la dette 2.
10. **`scripts/p6_5_diagnose_*.py`** ne passent pas `ruff format` (pré-existant, hors CI qui ne vérifie
    que `src/`).

---

## 10. Leçons historiques

- **Grid trading** : seule approche profitable sur Kraken ; sur Binance, 0/24 combos P6 aux critères stricts.
  À reconfirmer sur fees Bybit (taker 0.25 % pèse sur les grilles serrées).
- **min_spacing ≥ 1.5 %** couvrait les fees Binance ; à recalculer pour Bybit.
- **Mean reversion 5m/15m** : mortes sur Kraken et Binance ; réévaluation P12 avec fees réelles.
- **Stops ATR-based** : supérieurs aux % fixes — d'autant plus sur Bybit EU (mèches nocturnes jusqu'à 40 bps).
- **HFT / trailing < 5 % / grid sans biais en bear** : ne marchera jamais.
- **Prix inter-exchanges** : corrélation 0.999999 Binance vs Bybit sur 90 jours → backtester sur Binance
  avec les fees de l'exchange cible est légitime.

---

## 11. Règles d'or

Voir `CLAUDE.md` (routeur) — résumé :
1. **Decimal** pour montants, **structlog** pour logs, **normalize_pair** pour paires.
2. **Filtrer** via `settings.exchange_name` dans le code de production (jamais de littéral).
3. **Batcher** les inserts SQL (~1000 rows max).
4. **Tester en paper** avant live, **3+ ans de backtest** avant paper, **B4 avant tout paper Bybit**.
5. **Ne JAMAIS commit** `.env` ni credentials.
6. **Ne JAMAIS modifier** MultiStrategyRouter/GeminiGlobalRiskManager/ExecutionEngine sans review humain.
7. **Lire le code existant** avant d'écrire.
