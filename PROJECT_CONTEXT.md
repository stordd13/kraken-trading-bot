# KrakenBot — Contexte Projet (Septembre 2026)

> **Source de vérité unique du projet.** Lire en entier avant de toucher au code ou de lancer un agent.
> Dernière mise à jour : 16 septembre 2026, **post-audit B4**. B4 close le 15 sept (merge `4c98b6b` dans `dev`, tag
> `v2.8.0-b4-3-campaign`) : campagne P6/P7 sous fees Bybit → **zéro sélection sous les critères codés avec un instrument depuis
> invalidé** (audit red-team du 16/09 — addendum en tête de `results/B4_bybit_backtest_report.md`) ; sélection paper vide.
> **C1 (métriques) mergé** (tag `v2.9.0-c1-metrics`) ; **C2 (fidélité replay) = prochain chantier**, puis rejeu diagnostic grid et
> C3 (validation chronologique). **Runs R&D gelés** jusqu'à C1-C2 mergés ; tickets papier (`docs/CONTRAINTES_POST_B4.md`) autorisés,
> journal `docs/RESEARCH_LOG.md` obligatoire avant tout run. **Roadmap B5 → P10 suspendue**. Pour le moment il n'y a rien à trader.

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

### État actuel (16 septembre 2026)

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
- ✅ **B4.3 (15 sept, close)** — chantier 0 (GATE A, 14 sept) : liquidation terminale du `GridBacktester`
  atteignable (MARKET au dernier close, taker + spread + slippage), `net_pnl` compté une fois dans les deux moteurs,
  gold hashes re-baselinés (`results/B4_3_chantier0_gate_a.md`) ; GATE B (15 sept) : coûts par paire mesurés sur
  `api.bybit.eu` (BTC 2/2 bps, ETH 3/2, SOL 11/2), plancher d'ordre 5 USDC, spacing grid ≥ 2 %, cartographie risk
  (`results/B4_3_gate_b_configs.md`) ; **campagne serveur `--fees bybit`** : P6 24 combos → **0 survivant** ; P7 212 configs
  + 280 fenêtres walk-forward → **0 / 35 configs** passent les 7 critères (règles GO P7 : run flaggé = config inéligible,
  Sharpe DCA non comparable, critères figés) ; grid × SOL : 48 / 48 configs flaggées (dette 14). **Sélection paper vide,
  argumentée** : `results/B4_bybit_backtest_report.md` — zéro sélection sous les critères codés avec un instrument depuis
  invalidé (audit du 16/09, addendum du rapport). **Clos le 15 sept** (GO Bruno) : mergé dans `dev`
  (`4c98b6b`, `--no-ff`), CODE_MAP régénéré (`64ca827`), tag `v2.8.0-b4-3-campaign` @ `64ca827`, zip
  `~/Desktop/krakenbot-src-v2.8.0-b4-3-campaign.zip`, serveur sur `dev` en parité **sans restart** (`src/` inchangé).
  **B4 est close** ; sans stratégie sélectionnée, B5 (paper) et P8 (Telegram) **ne démarrent pas** (voir ⏸️ ci-dessous) ;
  leurs prérequis restent consignés (dette 13 : test one-off + alignement YAML ; dette 14 : tolérance grid ; backup DB
  récurrent ; `deploy.yml` à découpler).
- ⏸️ **Roadmap B5 → P10 suspendue (sélection B4 vide)** — décision Bruno du 15 sept : pour le moment, rien à trader.
  **Phase courante : R&D stratégies sur le papier** (runs gelés jusqu'à C1-C2, voir ci-dessous). Toute idée (humaine, IA,
  article) passe le filtre `docs/CONTRAINTES_POST_B4.md`
  sur le papier (ticket d'entrée § 6 : mécanisme, fréquence, mouvement capturé vs round-trip 0.39-0.48 %, résolution
  de la tension significativité/coûts, bear market, données, critère de falsification) **avant une ligne de code** ;
  deux familles maximum par cycle de R&D ; protocole de validation à réécrire en C3 (le walk-forward actuel n'est pas
  chronologique, note WF § 9). Le serveur reste en **collecte seule** (`krakenbot-collector` actif, `krakenbot` masqué
  depuis le 16 sept).
- ⚠️ Les résultats P6/P7 (fees Binance 0.075 % flat) ne sont **pas transposables** aux fees Bybit
  (maker/taker asymétriques) : tout a été rejoué en B4 — verdict ci-dessus.
- 🔎 **Audit red-team du 16 sept** (`results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md`) : constats vérifiés indépendamment
  (code du tag `v2.8.0-b4-3-campaign` + reproduction des JSON de campagne), consensus à trois (Bruno, audit externe, revue
  interne) → **instrument de mesure invalidé** : métriques (D1-D6 : unités de Sharpe, MaxDD, PF, agrégation P7, equity non
  persistée, benchmark DCA), replay (grid 4 h nourri de bougies 5 m, EMA200 DCA jamais préenregistrée, plancher 5 USDC ×
  `bull_reduction`) et walk-forward **non chronologique** (candidats choisis sur une période chevauchant les fenêtres OOS).
  Portée des conclusions B4 : addendum en tête de `results/B4_bybit_backtest_report.md`. Les verdicts de sélection (vides)
  sont inchangés.
- ▶️ **Chantiers post-audit** : ✅ **C1 métriques mergé** dans `dev` le 16 sept (12 commits, tag `v2.9.0-c1-metrics`,
  `results/C1_metrics_report.md`, dette 15) ; ✅ **C2 fidélité replay livré les 17-18 sept** (branche `feat/c2-replay`, **non mergée** — PR vers `dev` et tag tranchés avec Bruno,
  `results/C2_replay_report.md` : grid rejoué sur les vraies séries 4 h / 1 d / 1 w, préenregistrement aux params effectifs,
  warmup en bougies, rejets comptés, ventes grid appariées par id, `replay_version` 2 ; dettes 14 et 16 résolues, 17 et 18
  créées, dette 13 élargie) ; puis **rejeu diagnostic
  grid** (96 configs BTC/SOL, périmètre pré-spécifié, verdict « inconclusif » possible) ; puis **C3 validation chronologique**
  (note WF § 9) avant toute sélection. **Gel des runs R&D** jusqu'à C1-C2 mergés ; tickets papier (`docs/CONTRAINTES_POST_B4.md`
  § 6) autorisés ; tout run futur s'inscrit d'abord dans `docs/RESEARCH_LOG.md`.
- 🛠️ **Prérequis B5 avancés le 16 sept** : backup DB récurrent **fait et testé** (cron 04:15 daily / 04:45 weekly, restore
  prouvé sur container jetable — `skills/database.md`) ; `deploy.yml` **découplé** du trader (marqueurs
  `# B5: re-enable trader`) ; **trader masqué** sur le serveur (`systemctl mask krakenbot`). Reste ouvert : test dette 13.

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
- 2 services systemd : `krakenbot-collector.service` **actif** (B2, 9 sept) et `krakenbot.service` (trader)
  **masqué** (`systemctl mask`, 16 sept) jusqu'à B5. Le workflow `deploy.yml` régénère le `.env` serveur depuis
  les GitHub Secrets : template Bybit depuis B2 (`EXCHANGE_NAME=bybit`, `BYBIT_*`, `SCHEDULER_PAIRS/INTERVALS`) —
  les secrets `BYBIT_API_KEY/SECRET` et `BYBIT_TRADE_API_KEY/SECRET` doivent exister côté GitHub. Depuis le
  16 sept, le workflow est **découplé du trader** (marqueurs `# B5: re-enable trader`) : il n'installe, n'active
  et ne redémarre que `krakenbot-collector`.

### Backup
- Dump complet du 7 sept 2026 : `~/Backups/krakenbot/krakenbot_20260907.dump` (203 Mo, `pg_dump -Fc`).
- Backup récurrent **en place depuis le 16 sept** : cron `scripts/backup_db.sh` (04:15 UTC daily / 04:45 dimanche
  weekly, rotation 7 j / 28 j, `~/backups/krakenbot/` sur le serveur).
- Procédure de restore TimescaleDB (`timescaledb_pre_restore()` / `pg_restore --no-owner` /
  `timescaledb_post_restore()`, version d'extension **exacte**) : `skills/database.md` — restore **testé le 16 sept**
  sur un container jetable (dump daily 13:42, counts vérifiés).

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

**Métriques (C1, 2026-09-16, branche `feat/c1-metrics`)** : un seul système de mesure, `krakenbot.backtest_metrics`
(`metrics_version` 2), partagé par les deux moteurs et `compute_benchmarks.py` — rééchantillonnage quotidien UTC avec
ancre autoritaire, Sharpe/Sortino sur rendements quotidiens (`None` si indéfini, jamais un faux 0), MaxDD relatif au
pic courant (`max_drawdown_pct_daily` = critères, `_engine` = diagnostic), Calmar CAGR géométrique, profit factor net
des deux jambes (`buy_fee_alloc`, sommes exportées, lots à coût inconnu exclus), flux externes pour le DCA fixe (D6).
Simulation inchangée au centime (rejeux signal A / grid quick / grid A, `results/C1_metrics_report.md`). Chaque
résultat porte `metrics_version` ; mélange pré-C1 / v2 refusé, `--force` limité à un fichier homogène, JSON B4
inécrasables ; `--equity-out` + `equity_daily`. Migration Alembic `c1ae7a1c0001` (ratios NULL + 4 colonnes)
**appliquée en local** (Docker, 16/09) ; **serveur en attente** d'une fenêtre services stoppés (règle 11). Détails :
`skills/backtest.md` § Métriques, `results/C1_metrics_report.md`.

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

- **Terminées** : P0–P6 (pivot Binance, multi-pair, backtests), P7 phase 1, B0 (audit Bybit), B0.5 (docs), B1 REST
  Bybit, B2 WS, B3 data/collector, **B4 re-run P6 + P7 fees Bybit** (15 sept, tag `v2.8.0-b4-3-campaign`) → **0 survivant**
  (zéro sélection sous les critères codés avec un instrument depuis invalidé — addendum B4), **C1 métriques** (16 sept,
  tag `v2.9.0-c1-metrics`).
- ▶️ **Chantiers post-audit** : C2 fidélité replay (prochain) → rejeu diagnostic grid (96 configs BTC/SOL) → C3 validation
  chronologique ; runs R&D gelés jusqu'à C1-C2 mergés.
- ⏸️ **Suspendues (sélection B4 vide)** : B5 paper 4+ semaines, P8 Telegram, P10 live progressif — reprise seulement
  quand un candidat aura été validé sous le protocole C3 (sélection chronologique, equity continue) sous fees Bybit.
- **R&D stratégies** sous `docs/CONTRAINTES_POST_B4.md` (ticket d'entrée obligatoire, deux familles max par cycle,
  critères écrits avant les runs, inscription à `docs/RESEARCH_LOG.md` avant tout lancement ; le pipeline P6/P7
  `--fees bybit` redevient l'outil de test après C2).
- **Futures** : P11 (ML signal filter), P12 (éval scalping avec fees réelles), P13 (ML vol), P14 (RL + alloc dynamique) —
  après un edge prouvé, pas avant.

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
   (`results/B4_3_chantier0_gate_a.md`). Reste : sorties limit marketables facturées maker. Le « mauvais pop »
   de la stratégie grid (fermeture par proximité de prix vs id), instrumenté en B4.3 (`inventory_divergence_btc`),
   est **résolu en C2** (dette 14).
3. ✅ **B3** — `TaskScheduler` généralisé : client REST injecté par le collector (factory, `read_only=True`),
   backfill de gaps `krakenbot.data.backfill`, plus d'import de `scripts/` depuis `src/` ;
   `scripts/fetch_ohlc.py` et `backfill_binance_gap.py` supprimés.
4. **Restore TimescaleDB non trivial** — procédure documentée dans `skills/database.md` ; **testée le 16/09/2026**
   (version d'extension **exacte** requise, rôles absents du dump, `scripts/restore_db.sh` non aligné → chore cleanup
   post-C1).
5. ✅ **16/09/2026 — Backup DB récurrent** : cron `scripts/backup_db.sh` 04:15 daily / 04:45 weekly sur le serveur,
   rotation 7 j / 28 j, restore prouvé sur container jetable. Reste : copie hors serveur (storage box) non incluse.
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
    **Élargie en C2 (2026-09-17, décision 3 de la revue du plan)** — non-correspondance des identifiants lots grid ↔
    `OpenPosition` : le compteur de lots de la stratégie repart à 1 à chaque démarrage sans réhydratation depuis
    `open_positions` ; les rows grid reçoivent un id de repli `max+1` sur toutes les rows du bot (le router protégé saute
    `_assign_runtime_position_id`) et **restent OPEN** (aucun closer par id pour le grid) ; une émission naïve de
    `position_id` fermerait une row périmée après restart (mauvais `entry_price`, P&L fabriqué) ou, hors router, produirait
    des rows OPEN dupliquées ; `order_manager._position_profit_targets` est indexé par int sans `bot_id` ; au démarrage suivant,
    `_reconcile_positions_with_exchange` (`main.py:804`) ferme les rows OPEN les plus **anciennes en FIFO** avec `pnl = 0`
    et **sans filtre `bot_id`** — le P&L réel du lot est perdu et les rows d'une autre stratégie peuvent être fermées. En conséquence le
    SELL apparié du grid émet `amount_btc` seul, **jamais `position_id`** ; le chemin sans id (lot unique au prix exact,
    sinon réconciliation signalée) reste le chemin nominal en live. Le test one-off devient : **restart avec rows OPEN
    périmées, puis réhydratation des lots depuis `open_positions` ou closer par id** — l'équivalence lot ↔ row n'est
    démontrée qu'à ce moment. **Prérequis B5 explicite : le grid est inéligible au paper tant que cette démonstration
    n'est pas faite** (`results/C2_replay_report.md` § 5).
14. ✅ **C2 (2026-09-17) — Tolérance de fermeture absolue du grid** (`grok_grid_atr_adaptive_v4.py`, `_match_sell_fill` avant C2 : `|sell_level − prix| < 1` USD)
    contre appariement moteur par `position_id` → « mauvais pop » : sur SOL (~180 USD) des cibles SELL à moins de 1 USD
    sont fréquentes et **40 lots ont été vendus deux fois** sur le run P6 B4 (3 runs flaggés, divergence d'inventaire
    jusqu'à −0.033 SOL, lot-basis +1.2 % trop optimiste ; `net_pnl` cash exact) ; jamais sur BTC, quasi jamais sur ETH.
    **Règle GO P7 n° 1** : toute config flaggée est inéligible à la sélection paper ; une candidature grid × SOL exige
    d'abord ce fix (tolérance **relative**, en % du prix ou fraction du spacing) dans la stratégie protégée, review
    humaine, puis re-run. Source : `results/B4_P6_checkpoint.md`, `results/B4_bybit_backtest_report.md` § 6.
    **Résolution C2** (supersède la « tolérance relative ») : appariement **par `position_id`** dans la stratégie
    (`_match_sell_fill`, aucun repli de prix ; sans id : lot unique dont `sell_level == prix`, égalité Decimal ; inconnu /
    absent / ambigu → journalisé + compté dans `fill_anomalies`, callback terminé sans retirer de lot ni créer de BUY de
    remplacement) ; moteur : lot validé **avant** toute mutation — id inconnu ou inventaire insuffisant
    au-delà de la poussière → rejet compté sans mutation ; quantité de l'ordre ≠ quantité du lot, ou lot encore ouvert
    après le callback → `RuntimeError` (invariant de replay, job en `error`) ; diff R4 validé au gate humain (`a7a5e10`).
    Rejeu P6 des 3 grids (`results/c2_replay/P6_grid_rerun.json`) : SOL réconcilié sur les 3 segments (divergence
    d'inventaire = poussière Decimal, `net_pnl` = lot-basis, 0 `unmatched`). Reste, en live : un SELL limit peut être
    rempli à un prix **meilleur** que sa limite → égalité exacte en défaut → `unmatched_sell_fills` légitime → réconciliation
    signalée, jamais attribuée (dette 13 élargie).
12. **`fetch_ohlcv` end-stamped pour Bybit seulement** : le backfill générique (`krakenbot.data.backfill`)
    n'est garanti correct que pour `EXCHANGE_NAME=bybit` ; les clients REST Binance/Kraken renvoient l'open
    time ccxt alors que la DB est end-stamped (B4.1) : un backfill y insérerait des candles décalées d'un
    intervalle sans erreur (docstring du Protocol `connectors/exchange.py`). Inchangé en B4.1.
15. ✅ **C1 (2026-09-16) — mesure des backtests** : les six défauts de mesure de l'audit red-team (D1 unités du
    Sharpe, D2 MaxDD au pic final, D3 PF sans fee d'achat, D4 agrégation P7 `None`/`inf` → 0, D5 equity non
    persistée, D6 dépôts DCA comptés comme rendements) sont **résolus** par `krakenbot.backtest_metrics`
    (`metrics_version` 2) — simulation identique au centime, `results/C1_metrics_report.md`. **Reste** :
    (a) migration `c1ae7a1c0001` **à appliquer sur le serveur** (fenêtre services stoppés, règle 11) — appliquée en
    local le 16/09 ; (b) le **chemin legacy v1** de `p7_report` (coercition `_safe_float`, moyenne des PF,
    constantes `BENCHMARK_SHARPE`) n'est conservé que pour relire les fichiers B4 (checkpoints
    `scripts/audit/b4_p6/p7_checkpoint.py`, verdicts reproduits à l'identique) — à retirer quand B4 sera archivé ;
    la détection « PF inf » de ces checkpoints est aveugle sur v2 et `scripts/audit/b4_3_gate_a_reconcile.py` ne
    lit que des captures v1 ; (c) `compute_benchmarks.py` charge `< P6_END` alors que les moteurs chargent `<= end`
    (un jour) et son « lundi » est le stamp de fin de période (close du dimanche) → chantier 3 ; (d) scindée en C2 :
    la vente grok sans position appariée (wallet débité sans trade) est **résolue** (R4 : rejet compté avant toute
    mutation) ; le cost basis au **dernier** prix d'entrée en accumulation (moteur signal) passe en **dette 17**.
16. ✅ **C2 (2026-09-17) — Fidélité du replay** (audit red-team 16/09) : grid backtesté avec indicateurs 4 h nourris de
    bougies 5 m ; EMA200 1d du DCA jamais préenregistrée (boost oversold inopérant en fenêtre trimestrielle) ; interaction
    `bull_reduction × 15 USDC = 4.50 < plancher 5` (achats rejetés en strong_bull) ; comptage des rejets absent des
    résultats. **Résolu** (`results/C2_replay_report.md`, `skills/backtest.md` § Replay) : R1 grid rejoué sur les vraies
    séries 4 h / 1 d / 1 w (décision aux clôtures 4 h, exécution 5 m, ordre tranché à timestamp égal, `--interval` < 240,
    `--cross-validate` × grid refusé) ; R2 préenregistrement lazy aux paramètres **effectifs** des 8 stratégies + warmup en
    bougies (bloc `warmup` : chargé / requis / extension bornée / staleness / trous, `sufficient` — un trou est signalé,
    jamais comblé) ; R3 bloc `rejections` par (ordre, cause) sur les deux moteurs + `dca_counters` ; R4 = dette 14 ;
    provenance `replay_version` 2 (fichiers pré-C2 refusés par les runners, B4 / C1 inécrasables). Invariant : signal A
    (SuperTrend) bit-identique tag ↔ branche en mode strict ; gold hashes grid re-baselinés sur tableau approuvé. Constat
    rétroactif : 19/20 configs SuperTrend et 3/4 Donchian de P7 créaient leur indicateur après le warmup (muettes 1-3 jours
    par segment), EMA 200 DCA muette 200 jours. **Reste** : la table `backtest_runs` (`--save`, dashboard) porte
    `metrics_version` depuis C1 mais **aucune colonne `replay_version`** (pas de migration en C2) — une row post-C2 y est
    indiscernable d'une row pré-C2.
17. **Exécution du moteur signal et benchmarks — hors C2** (constats C1/C2, 2026-09-17) : (a) accumulation :
    `cost_basis = entry_price × crypto_balance` au **dernier** prix d'entrée (multi-achats sans moyenne pondérée) ;
    (b) benchmarks décalés (`compute_benchmarks.py` charge `< P6_END` alors que les moteurs chargent `<= end`, « lundi » =
    stamp de fin de période) → **C3** ; (c) exécution intrabar du grid : les fills limit sont déclenchés au touch du
    low / high de la bougie d'exécution, sans file d'attente ni fill partiel (le moteur signal, lui, reste next-bar à
    l'open de N+1) ; l'equity est valorisée au close, les mèches ne sont pas capturées (`skills/backtest.md`).
18. **Double alimentation de l'analyzer par les 3 stratégies gemini** (constat C2) : `backtest.py` appelle
    `analyzer.update` sur chaque bougie **et** leur `on_ohlc` le rappelle → période effective des indicateurs ~divisée par
    deux en replay. La preuve 2 de C2 prend pour référence « le flux réellement reçu » (mécanique du replay prouvée, pas la
    justesse de leurs indicateurs). **Blocage explicite de P12** (réévaluation scalping / mean reversion avec fees réelles) :
    invalide par construction tant que ce n'est pas corrigé.

**Note WF** (audit red-team 16/09) : la sélection top-5 de P7 phase 2 utilise le Sharpe du test global (période chevauchant
les fenêtres) — le walk-forward actuel n'est pas une validation chronologique. **Résolution : C3**.

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
