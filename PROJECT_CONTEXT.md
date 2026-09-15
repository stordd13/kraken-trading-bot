# KrakenBot — Contexte Projet (Septembre 2026)

> **Source de vérité unique du projet.** Lire en entier avant de toucher au code ou de lancer un agent.
> Dernière mise à jour : 13 septembre 2026, B3 clôturée (merge `3ea32d9` dans `dev`, tag `v2.5.0-b3-bybit-data`) : historique Bybit EU en DB, backfill de gaps, scheduler actif. Prochaine phase : B4.

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
- ▶️ **Serveur Hetzner : `krakenbot-collector` réactivé le 9 sept 18:12 UTC (B2, WS Bybit)** ; `krakenbot`
  (trader) reste stoppé et désactivé jusqu'à B4/B5. DB intacte, backupée le 7 sept (203 Mo, rapatriée).
- ✅ B1 `BybitRestClient` (8-9 sept, branche `feat/b1-bybit-rest`) : settings (clés read-only + trade),
  factory, 72 tests unitaires, round-trip read-only + paper + **live** validé sur `api.bybit.eu`
  (PostOnly → cancel, rejet PostOnly normalisé, `priceLimitRatioX` sans impact sur les ordres passifs).
- ✅ B2 code `BybitWebSocketClient` (9 sept, branche `feat/b2-bybit-ws`) : WS public spot v5 (24 topics en
  3 requêtes, ping 20 s, watchdog flux agrégé 2 paliers configurables `BYBIT_WS_WATCHDOG_*`, escalade
  Telegram), factory, collector `EXCHANGE_NAME=bybit` (7 TF, `TaskScheduler` Kraken neutralisé), 46 tests +
  intégration réelle, collecte locale 1 h validée (225 candles, grille alignée, 3 décrochages réseau détectés par le pong et récupérés ; les candles clôturant pendant une coupure manquent → backfill B3). `deploy.yml` régénère un `.env` Bybit (secrets
  `BYBIT_*` à créer). **Fait le 9 sept** : merge dans `dev` (`ad296c8`), `.env` serveur, collector
  `enable --now`. Observation 24 h **propre** (10 sept : 0 zombie, 0 trou 1m, 2 fermetures 1006 récupérées) → tag `v2.4.0-b2-bybit-ws`.
- ✅ **B3 (11 sept)** : historique Bybit EU importé (**2 543 347 rows**, 3 paires × 7 TF depuis 2025-06-11, 34 min,
  0 trou, 0 désalignement), backfill de gaps démontré **avant** l'import (22 gaps / 952 candles, dont les 1m et 5m
  `01:05` du 11/09), `TaskScheduler` générique (client read-only, job `gap_backfill` 03:30 UTC) actif après restart
  du collector, cohérences 1d/1w (décalage d'un intervalle attendu), prix 1h (corr ≥ 0,99998) et WS/REST (identiques)
  passées. Rapport : `results/B3_bybit_data_report.md`. **Constat** : dette 11 (convention timestamp, B4).
- ✅ **B4.1 (13 sept)** : 8 712 718 rows Binance re-stampées en fin de période (dette 11), tag
  `v2.6.0-b4-1-binance-restamp` ; ✅ **B4.2 (14 sept)** : modèle de fees maker/taker découplé de la source de
  données (`--fees` obligatoire), chemins morts supprimés, suite de tests hermétique (dotenv, boucle
  d'événements) — mergé dans `dev` (`3406a6c`), tag `v2.7.0-b4-2-fees-engine` (`fea0e16`), serveur en parité
  sans restart — `results/B4_2_fees_engine_report.md`.
- 🚧 **B4.3 en cours** — chantier 0 fait le 14 sept (branche `feat/b4-3-campaign`) : liquidation terminale du
  `GridBacktester` atteignable (MARKET au dernier close, taker + spread + slippage, soldes réglés), `net_pnl`
  unifié dans les deux moteurs (`total_pnl − fees d'achat`), gold hashes binance/bybit re-baselinés, garde
  signal et deltas grid signés (`results/B4_3_chantier0_gate_a.md`) → **GATE A** ; ensuite GATE B (coûts par
  paire, grilles P7, risk) puis campagne P6/P7 `--fees bybit` dans de nouveaux fichiers de sortie.
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
  (état B0.5). Le workflow `deploy.yml` régénère le `.env` serveur depuis les GitHub Secrets : template
  Bybit depuis B2 (`EXCHANGE_NAME=bybit`, `BYBIT_*`, `SCHEDULER_PAIRS/INTERVALS`) — les secrets
  `BYBIT_API_KEY/SECRET` et `BYBIT_TRADE_API_KEY/SECRET` doivent exister côté GitHub. ⚠️ Le workflow
  redémarre **les deux** services et exige `krakenbot` actif : ne pas pousser sur `main` tant que le trader
  ne doit pas tourner (B4/B5).

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
klines + 3 tickers = 24 topics, `SCHEDULER_PAIRS` / `SCHEDULER_INTERVALS`), écrit dans `market_data_ohlc`
avec `exchange='bybit'` (hardcodé dans le connecteur, comme `binance`/`kraken`). Le backfill REST de gaps
(`TaskScheduler`, module `krakenbot.data.backfill`, B3) tourne pour tout exchange : job unique `gap_backfill`
à 03:30 UTC (après les fermetures 1006 nocturnes), client REST **read-only** injecté par le collector,
trous internes des 3 derniers jours + gap de fin, `ON CONFLICT DO NOTHING` (les rows WS font foi).

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

**Mécanisme (B4.2)** : le modèle de fees est **découplé de la source de données**. `scripts/backtest.py`,
`run_p6_backtests.py`, `run_p7_grid_search.py` et `run_p6_walkforward.py` exigent `--fees {bybit,binance,kraken}`
(pas de défaut ; absence → erreur), résolu par `ExchangeFees.from_name()` ; le dashboard passe `bybit`.
`--exchange` ne choisit que les données. Sites de fill : entrées limit et fills de grille = maker ; sorties
market = taker + spread + slippage ; liquidation de l'inventaire terminal du GridBacktester (B4.3) = MARKET au
dernier close, taker + spread + slippage, soldes réglés. `net_pnl` compte chaque fee une fois dans les deux
moteurs (B4.3) : signal `total_pnl − fees d'achat`, grid = cash réalisé après liquidation ; run plat ⇒
`net_pnl == ending − capital` (identité vérifiée sur les rejeux de référence).
`settings.exchange_fees` reste le modèle **live/paper** des connecteurs ; le backtest ne le lit jamais.
Chaque résultat P6/P7 porte désormais sa clé `fees` et la reprise refuse un fichier d'un autre modèle
(`--force` = seule échappatoire) : B4.3 écrit dans de nouveaux fichiers. Détails : `skills/backtest.md`,
`results/B4_2_fees_engine_report.md`.

Contexte historique : les backtests P6 et P7 phase 1 ont été faits avec les fees Binance BNB
**0.075 % flat** (round-trip ~0.18 %). Les fees Kraken (0.16 / 0.26 %) sont le défaut de `ExchangeFees()` nu.

---

## 6. Base de données

### Schema principal

**market_data_ohlc** (hypertable TimescaleDB) :
- PK : `(timestamp, pair, interval, exchange)`
- Colonnes : open, high, low, close, volume, vwap, trades_count (nullable — Bybit n'en fournit pas)
- Chunks de 30 jours ; `timestamp` = **fin de période** (`open + interval`, Bybit `end + 1 ms`) pour
  **tous** les exchanges — les rows `binance` le sont depuis le re-stamp B4.1 du 2026-09-13
  (`results/B4_1_timestamp_restamp_report.md`)

**Volumes (septembre 2026)** :
- `exchange='binance'` : 8 712 718 rows (BTC/ETH/SOL × 7 TF, 2021-01-01 → 2026-04-01 00:00, 1w → 2026-04-06) —
  **base de backtest, figée**, **end-stamped depuis B4.1** (dette 11 résolue ; counts inchangés par le re-stamp)
- `exchange='kraken'` : 1 181 469 rows (legacy, à supprimer quand Bybit est validé en live)
- `exchange='bybit'` : **2 543 347 rows** (B3, 2026-09-11 : 3 paires × 7 TF depuis 2025-06-11 09:21 UTC, + WS en continu, + backfill nocturne)

**Filtre obligatoire** : le code de production filtre sur `settings.exchange_name` (cible `bybit`) ; les
backtests lisent explicitement `exchange='binance'`.

### Import de données

- Binance Vision (historique, figé) : `scripts/binance_vision_import.py` — `skills/binance_import.md`.
- Bybit (B3) : `scripts/bybit_kline_import.py` (REST brut v5 paginé, reprise `MAX(timestamp)`, batch 1000)
  et `scripts/backfill_gap.py` (gaps, `--dry-run`) — runbooks dans `skills/bybit.md`.

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
   `EXCHANGE_NAME` ; le `.env` local non plus. **Résolu en B1** : `exchange_name` est `Literal[kraken|binance|bybit]`
   **sans default** (erreur explicite au démarrage), `.env.example` à jour, `.env` local = `bybit`.
   Reste : `deploy.yml` / `.env` serveur (B2).
2. ✅ **B4.2 (2026-09-14)** — `scripts/backtest.py` : fees flat choisies sur la source de données. Résolu :
   `--fees {bybit,binance,kraken}` obligatoire partout, registre `ExchangeFees.from_name()`, maker/taker
   par site de fill (liquidations forcées du GridBacktester → taker), `settings.exchange_fees` = live/paper
   documenté, rollover supprimé avec le chemin short mort. Régression iso-fees bit-exacte prouvée
   (`results/B4_2_fees_engine_report.md`). ✅ **B4.3 chantier 0 (2026-09-14)** : liquidation terminale du
   grid atteignable sur le chemin grok (MARKET au dernier close, taker + spread + slippage, soldes réglés,
   trades `forced_liquidation`), `net_pnl` compte chaque fee une fois dans les deux moteurs
   (`results/B4_3_chantier0_gate_a.md`). Reste : sorties limit marketables facturées maker ; « mauvais pop »
   de la stratégie grid (fermeture par proximité de prix vs id) instrumenté (`inventory_divergence_btc`), non
   corrigé (fichier protégé).
3. ✅ **B3** — `TaskScheduler` généralisé : client REST injecté par le collector (factory, `read_only=True`),
   backfill de gaps `krakenbot.data.backfill`, plus d'import de `scripts/` depuis `src/` ;
   `scripts/fetch_ohlc.py` et `backfill_binance_gap.py` supprimés.
4. **Restore TimescaleDB non trivial** — procédure documentée dans `skills/database.md`.
5. **Backup DB récurrent absent** — cron + rotation + storage box, requis avant **B5**.
6. **mypy `union-attr`** : 10 erreurs dans `main.py` (13 avant B0.5), 15 sur `src/` (21 avant). Le
   « ~97 » historique était périmé.
7. **`execution/` dépend de `connectors/kraken/rest.py`** : `order_manager.py` et `risk.py` importent
   `normalize_asset_balances` / `normalize_asset_symbol` (normaliseurs Kraken appliqués à tous les
   exchanges) ; `engine.py` type-hint `KrakenRestClient`. À généraliser en B1.
8. ✅ **B3** — `exchange` est **obligatoire** (plus de default `"binance"`) dans
   `MultiTimeframeAnalyzer.initialize` et `MultiPairAnalyzerRegistry.initialize_all` ; `main.py` passe
   `settings.exchange_name`.
9. ✅ **B4.2** — chemin `is_multi` mort de `BacktestEngine`, chemin short/rollover (`_execute_short_signal`,
   seul émetteur supprimé en B0.5), `_check_directional_pause` et son état (`_grid_paused`,
   `_hourly_prices`, `directional_pause_pct`) et 3 attributs write-only supprimés avec preuves
   d'inatteignabilité (3 réfutateurs par affirmation). Reste : le chemin grid legacy non-grok
   (inatteignable en prod, couvert seulement par `tests/test_grid_metrics.py`) → B4.3.
10. **`scripts/p6_5_diagnose_*.py`** ne passent pas `ruff format` (pré-existant, hors CI qui ne vérifie
    que `src/`).
11. ✅ **B4.1 (2026-09-13) — Convention de timestamp Binance** : les 8 712 718 rows `binance` (import Vision,
    open-stamped) ont été **re-stampées en fin de période** (`timestamp := timestamp + interval`) sur le serveur
    — 2 550 fenêtres transactionnelles (une version intermédiaire du rapport écrivait « 2 511 » : erreur
    d'addition, corrigée), 0 collision, comptabilité exacte par série, collector arrêté de 17:46:59 à 18:13:23
    UTC, backup frais `krakenbot_20260913_b4pre.dump` avant écriture. **Prémisse corrigée** : la « fenêtre
    avril–juin 2026 de rows WS Binance end-stamped à assainir » n'a jamais existé en DB (`MAX(timestamp)`
    des 21 séries = 2026-03-31 avant re-stamp) ; les rows WS de cette époque sont sous `exchange='kraken'`
    (`XBT/USDC` jusqu'au 2026-05-30, collector alors sur Kraken — cf. dette 1). Invariants post-migration
    verts (audit v2 : vote OHLC, première semaine tradée Bybit et fenêtres sous le plancher de couverture
    exclues, contrôle inverse sur la vue virtuelle `timestamp − interval`) ; backtest de référence différent
    du baseline P6 (look-ahead multi-TF supprimé). `scripts/binance_vision_import.py` écrit désormais la fin de
    période. Source : `results/B4_1_timestamp_restamp_report.md`.
13. **Résolution des params de stratégie par nom de classe dans les moteurs de backtest** (constat B4.3 GATE B,
    vérifié par instanciation) : `BacktestEngine._load_inner_strategy_params` / `GridBacktester._load_grid_strategy_params`
    cherchent `router.strategies["<classe>"]` alors que `strategies.yaml` indexe les instances (`grid_atr_btc`,
    `class: grok_grid_atr_adaptive_v4`) → les 5 stratégies grok ont toujours backtesté (P6, P7, B4) sur leurs **défauts
    de classe** (grid : lots 25 USDC, le YAML dit 10), les 3 gemini (clé = classe) sur le YAML. Décision GO B (B.2a) :
    défauts conservés pour la campagne B4 ; les params effectifs sont capturés au runtime (`effective_params` dans chaque
    résultat, `B4_P7_final_selection.json`) et alignent `strategies.yaml` en B5 ; **fix de la résolution post-B4**, après
    cet alignement (il change toutes les métriques grok). **Prérequis B5** : test one-off prouvant que le chemin
    live/router résout bien par instance (`class:`) — consigné, non fait.
12. **`fetch_ohlcv` end-stamped pour Bybit seulement** : le backfill générique (`krakenbot.data.backfill`)
    n'est garanti correct que pour `EXCHANGE_NAME=bybit` ; les clients REST Binance/Kraken renvoient l'open
    time ccxt alors que la DB est end-stamped (B4.1) : un backfill y insérerait des candles décalées d'un
    intervalle sans erreur (docstring du Protocol `connectors/exchange.py`). Inchangé en B4.1.

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
