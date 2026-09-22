# KrakenBot — Roadmap (Septembre 2026)

> Roadmap consolidée post-pivot Bybit EU. Mise à jour : 22 septembre 2026 (post-audit B4, C1 et C2 mergés, **C3a close**, C3b ouvert).
> Décisions de pivot : `docs/archive/PIVOT_BYBIT_PLAN.md` · audit Bybit : `results/bybit_integration_audit.md` ·
> audit red-team B4 (portée des conclusions) : `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` + addendum en tête de
> `results/B4_bybit_backtest_report.md`.

---

## Phases terminées (archive)

| Phase | Quoi | Tag | Verdict |
|---|---|---|---|
| P0 | Audit Binance | v1.5.0 | Faisabilité confirmée (`results/archive/binance_integration_audit.md`) — obsolète depuis le 1er juillet 2026, documente l'origine des 8.7M rows |
| P1 | Exchange abstraction layer (`ExchangeRestClient`, `BaseWebSocketClient`, `ExchangeFees`) | v1.5.0-exchange-abstraction | Réutilisé tel quel pour Bybit |
| P2 | `BinanceRestClient` + factory | v1.6.0-binance-rest | Modèle du futur `BybitRestClient` |
| P3 | `BinanceWebSocketClient` (reconnect 23 h, watchdog) | v1.7.0-binance-ws | Modèle du futur `BybitWebSocketClient` |
| P4 | Collector + migration `exchange` + import Binance Vision (8.7M rows) | v1.8.0-binance-vision | Données = base de backtest |
| P5 | Multi-pair refactor (registry, router par pair, confidence) | v1.9.0-multi-pair | Aucune référence à l'exchange dans router / risk / stratégies |
| P6 | Backtests 24 combos (8 stratégies × 3 paires), fees Binance 0.075 % flat | v2.0.0-p6-validated | **0/24 aux 5 critères stricts** (`results/P6_backtest_report_v2.md`) → survivors/walk-forward vides (normal) — métriques invalidées par l'audit du 16/09 (addendum B4) ; verdicts de sélection (vides) inchangés |
| P6.7 | Runner multiprocessing (resume, atomic save, déterminisme) | v2.1.0-p6-7-multiprocessing | Réutilisé pour B4 (`results/P6_7_multiprocessing_benchmark.md`) |
| P7 (phase 1) | Grid search cross-validé, 212 configs, 4 stratégies, fees Binance | — (branche mergée 7 sept) | `results/P7_phase1_cross_validate.json` — machinerie OK, **classements non transposables** aux fees Bybit — métriques invalidées par l'audit du 16/09 (addendum B4) ; verdicts de sélection (vides) inchangés |
| B0 | Audit Bybit EU (endpoints, lots, spread, historique, WS, ordres, rate limits, écart de prix) | — | **GO avec réserves** (`results/bybit_integration_audit.md`) |
| B0.5 | Refonte docs + suppression du code legacy Kraken-era | — | Version du 8 sept |
| B4 | Re-run P6 (24 combos) + P7 (212 configs, 280 fenêtres WF) sur données Binance end-stampées, fees Bybit maker/taker, coûts par paire (GATE B), grid honnête (GATE A) | v2.8.0-b4-3-campaign | **0/24, 0/35, sélection paper vide** (`results/B4_bybit_backtest_report.md`) — métriques invalidées par l'audit du 16/09 (addendum B4) ; verdicts de sélection (vides) inchangés |
| C2 | Fidélité du replay : grid rejoué sur les vraies séries 4 h / 1 d / 1 w, préenregistrement lazy aux params effectifs + warmup en bougies, compteurs de rejets, ventes grid appariées par `position_id` (dette 14), `replay_version` 2 | v2.10.0-c2-replay | Signal bit-identique en mode strict, gold hashes grid re-baselinés sur tableau approuvé, 30/30 tests de déterminisme au SHA livré (`results/C2_replay_report.md`) |
| C1 | Métriques fiables : module partagé `krakenbot.backtest_metrics` (`metrics_version` 2), dual MaxDD, PF net, equity export, A/B vs tag | v2.9.0-c1-metrics | Simulation inchangée au centime, gold hashes re-baselinés sur tableau A/B approuvé (`results/C1_metrics_report.md`) |

Le pivot Kraken → Binance (avril 2026) est documenté dans `docs/archive/ROADMAP_pre_binance_pivot.md`.

---

## Vue d'ensemble des phases à venir

| Phase | Quoi | Durée | Livrable / critère de done | Statut |
|---|---|---|---|---|
| **B1** | `BybitRestClient` (ccxt `hostname=bybit.eu`) + `BybitSettings` + `ExchangeFees.bybit_defaults()` + branche factory + tests ; fix `exchange_name` default ; fees maker/taker distincts dans `backtest.py` | 2-3 j | Round-trip d'ordre paper validé avec les vraies clés ; `scripts/audit/bybit_q1/q6/q7` relancés avec clés | ✅ 9 sept (round-trip live validé, `priceLimitRatioX` levé ; fees backtest → B4) |
| **B2** | `BybitWebSocketClient` (v5 public kline, 10 args/subscribe, ping 20 s) + tests ; réactivation du collector | 3-4 j | Candles `exchange='bybit'` en DB en continu 24 h sans zombie | ✅ 10 sept — `v2.4.0-b2-bybit-ws`, collector Bybit en production, 24 h propres |
| **B3** | Import historique Bybit EU (REST paginé, batch 1000) ; collector/scheduler génériques (`TaskScheduler` via factory, backfill gap) | 2 j | Data Bybit en DB (≈ 2.5M candles depuis 2025-06-11), backfill fonctionnel | ✅ 13 sept — `v2.5.0-b3-bybit-data` (merge `3ea32d9`) : historique EU importé, backfill démontré sur gaps réels, scheduler actif ; constat convention timestamp → dette B4 |
| **B4** | Re-run P6 (24 combos) et P7 (grid search phases 1-2 + rapport) sur données Binance avec fees Bybit maker/taker + spread/slippage mesurés | 1 j run + 1 j analyse | `results/B4_bybit_backtest_report.md`, sélection paper | ✅ 15 sept — `v2.8.0-b4-3-campaign` : 0/24, 0/35, sélection paper vide ; **métriques invalidées par l'audit du 16/09 (addendum B4) ; verdicts de sélection (vides) inchangés** |
| **C1** | Métriques fiables (module partagé, dual MaxDD, PF net, equity export, A/B vs tag) | 3-5 j | `results/C1_metrics_report.md`, gold hashes re-baselinés sur tableau A/B approuvé | ✅ 16 sept — mergé dans `dev`, tag `v2.9.0-c1-metrics` |
| **C2** | Fidélité replay (grid 4h réels, préenregistrement EMA200 DCA, compteurs de rejets, dette 14 avec review) | 2-4 j | `results/C2_replay_report.md`, gold hashes grid re-baselinés sur tableau approuvé, preuves de déterminisme `results/c2_replay/determinism_server/` | ✅ 19 sept — mergé dans `dev`, tag `v2.10.0-c2-replay` |
| **Rejeu grid** | Diagnostic pré-spécifié : 96 configs (48 × BTC/SOL) sous instrument réparé, analyse écrite avant lancement, « inconclusif » possible | 1-2 j | `results/rejeu_grid_report.md`, pré-spécification gelée `docs/rejeu_grid_prespec.md`, artefacts `results/rejeu_grid_20260919/` | ✅ 20 sept — **`inconclusif (F_CANNOT_SEPARATE)`** : 16 configs BTC passent les gates ponctuels, aucune ne tient les six bornes simultanées ; SOL descriptif (données insuffisantes). Ni candidat, ni dépriorisation : **pas de déploiement, pas de tuning supplémentaire**, périmètre non élargi. Suite → C3 |
| **C3** | Validation chronologique (sélection sur le passé seul, equity continue, benchmark d'exposition, issue « inconclusif ») | 3-5 j | Protocole gelé + outillé ; puis campagne réelle sous la chaîne | ✅ **C3a close le 22 sept** — protocole **gelé** (`docs/protocole_c3.md`, `d931293`), outillage **complet** (7 modules, 806 tests, `c3_verdict.py chain`), artefact du rejeu **refusé à l'entrée** (`D_WARMUP_PREFIX`, 96/96) ; branche `feat/c3a-protocole` @ `acaeaf6` **non mergée** (porte § L.5 due). 📋 **C3b ouvert** : (1) gate d'amendement du protocole + chantier producteur ; (2) campagne réelle sous la chaîne. Détail : § « C3 — Validation chronologique » |
| **B5** | Paper trading Bybit 4+ semaines (ex-P9) ; P8 Telegram en parallèle ; backup DB récurrent en place (fait le 16/09) | 4-6 sem | 4 sem sans crash, P&L net > 0 sur 3/4 sem, drift backtest/paper < 20 %, pas de trade aberrant | 📋 — démarre sur **un candidat validé sous le protocole C3** |
| **P10** | Live progressif 1k → 5k → 20k | Continu | Voir paliers | 📋 |
| P11+ | ML, scalping eval, RL | Mois | — | 🔮 |

Règle : chaque phase B est écrite après la précédente, à partir de ses conclusions.

---

## Détail des phases

### B1 — Connecteur REST Bybit EU (2-3 jours)

- `BybitSettings` (hostname, api/ws urls, `recv_window_ms=5000`, `account_type=UNIFIED`), clés
  `BYBIT_API_KEY` / `BYBIT_API_SECRET` (read-only d'abord), `.env.example` mis à jour.
- `connectors/bybit/rest.py` cloné de `binance/rest.py` : `load_markets()` sur `bybit.eu`, filtres de lot
  (`skills/bybit.md`), market BUY **sans price**, LIMIT `timeInForce=PostOnly`, `clientOrderId` →
  `orderLinkId`, mapping `retCode` → exceptions, `fetch_balance` UTA, pas de BNB.
- `ExchangeFees.bybit_defaults(maker=0.0010, taker=0.0025, spread=0.0002, slippage=0.0002)`.
- Dettes à régler ici : `exchange_name` default (erreur explicite ou `bybit`), `deploy.yml` / `.env`
  serveur avec `EXCHANGE_NAME`, fees maker/taker distincts dans `scripts/backtest.py` (ou en ouverture de B4).
- Point non tranché de B0 à lever en premier : type de compte (UTA), permissions, IP whitelist, headers
  de rate limit, `priceLimitRatioX` 0.5 % sur les LIMIT éloignés.
- **Fait les 8-9 sept 2026** (`feat/b1-bybit-rest`) : tout, round-trip live inclus (protocole a/b/c,
  `priceLimitRatioX` sans effet sur les ordres passifs) — voir `skills/bybit.md` § « Levé en B1 ».
  `exchange_name` est obligatoire (erreur explicite). Fees maker/taker distincts dans `backtest.py` →
  ouverture de B4.

### B2 — WebSocket Bybit EU (3-4 jours)

- `connectors/bybit/ws.py` cloné de `binance/ws.py` : subscribe par lots de 10, parse `kline.*`
  (`data[0]`, `confirm`, `timestamp = end + 1 ms`, `volume` base / `turnover` quote, pas de
  `trades_count`), `tickers.*` (`lastPrice`), ping applicatif 20 s, ignorer les acks, reconnect
  préventif 23 h conservé, watchdog calibré sur l'ensemble des topics.
- Réactivation du collector sur Hetzner (`skills/deployment.md`), 24 h d'observation.

### B3 — Données et collector génériques (2 jours)

- `scripts/bybit_kline_import.py` : REST paginé `start` + `limit=1000`, liste descendante, candles
  `volume=0` acceptées, `exchange='bybit'`, batch 1000, idempotent.
- `TaskScheduler` passe par `build_exchange_rest_client` (fin du hardcode `KrakenRestClient`), backfill
  de gaps fonctionnel pour l'exchange courant ; defaults `exchange="binance"` des indicateurs →
  `settings.exchange_name`.
- Dashboard / collector filtrent sur `settings.exchange_name`.
- **Fait le 11 sept 2026** (`feat/b3-bybit-data`) : module `krakenbot.data.backfill` (LAG + tail, `ON CONFLICT
  DO NOTHING`) + `scripts/backfill_gap.py` ; `BybitRestClient.fetch_ohlcv` sur l'endpoint brut v5 (end-stamped,
  `vwap`) ; `scripts/bybit_kline_import.py` (reprise, trou de tête détecté) ; `TaskScheduler` avec client
  read-only injecté, job unique 03:30 UTC, `SCHEDULER_BACKFILL_DAYS=3` ; `exchange` obligatoire au warmup ;
  `fetch_ohlc.py` / `backfill_binance_gap.py` supprimés ; `candle_timestamp` dans les logs WS. **Constat** :
  rows Binance open-stamped vs moteur end-stamped → dette 11 (`PROJECT_CONTEXT.md`), à trancher en ouverture
  de B4. Rapport : `results/B3_bybit_data_report.md`. Dashboard : hors B3 (filtre déjà via settings côté collector).

### B4 — Re-run P6 + P7 avec fees Bybit (1 jour run + 1 jour analyse)

- Données Binance (8.7M rows), `--fees bybit` (maker/taker distincts, spread 0.02 %, slippage 0.02 %).
- P6 : 24 combos, 5 critères, walk-forward sur les survivants. P7 : grid search phases 1-2 + rapport
  sur les stratégies survivantes.
- Livrable : `results/B4_bybit_backtest_report.md` + sélection pour le paper. Une stratégie sans config
  qui passe est abandonnée.
- Révision risk management (ex-P7) intégrée : max positions ~100, daily loss 5 % dynamique, risk 2 %
  sous 5k, plancher 5-10 USDC, doctrine des sorties MARKET à 0.25 %.
- **Fait le 15 sept 2026** (`feat/b4-3-campaign`, tag `v2.8.0-b4-3-campaign`) : P6 0/24, P7 0/35, sélection paper vide
  (`results/B4_bybit_backtest_report.md`). **Métriques invalidées par l'audit du 16/09 (addendum B4) ; verdicts de
  sélection (vides) inchangés** — réparation de l'instrument : C1 et C2 **mergés** → rejeu grid (**clos le 20 sept**, `inconclusif`) → C3 (**C3a close le 22 sept**, C3b ouvert — section suivante).

### C3 — Validation chronologique (C3a close, C3b ouvert)

**C3a — protocole et outillage de sélection, close le 22 sept 2026** (branche `feat/c3a-protocole`, tip `acaeaf6`,
**non mergée, pas de tag**) :

- `docs/protocole_c3.md` **gelé** au `d931293` (21/09, sha256 `9b62915069e59e9b…`) : spécification de toute sélection
  future ; ne change que par amendement daté (§ 0.7).
- Outillage complet, liste fermée § L.4 : `scripts/audit/c3_{common,anchor,entry,benchmark,select,continuity,verdict}.py`
  (7 modules, ordre § L.1), tests `tests/test_scripts/test_c3_*.py` (8 fichiers, **806**), sous-commande
  `c3_verdict.py chain` (chaîne § L.2, neuf champs) ; suite complète 2 615 / 6 ; diff de contrôle § L.3 vide ;
  `mypy src/` 65 = baseline. Comportement et conventions d'outillage datées : `skills/backtest.md` § « Validation C3 ».
- Arrêt Fin validé le 22/09 par les deux revues (Astra / Claude) : deux passes, huit correctifs rouges-avant,
  `chain.verified` défini. Rapport : `agent/rapport_session_c3a_20260922.md`.
- **Seule sortie réelle** : refus de `results/rejeu_grid_20260919/P7_phase1_grid.json` à l'entrée (`D_WARMUP_PREFIX`,
  portée artefact, 96/96 — `results/c3a_entry_validation/`). Aucune sélection, aucun verdict économique ;
  `validé` / `réfuté` inatteignables avant C3b (§ L.1).
- **Porte pré-merge § L.5 due, hors C3a** : `git diff --stat f585e8b -- <chemins § L.3>` = `pyproject.toml` seul
  (exclusions Ruff), donc l'option 2 n'est pas disponible → **24 tests de déterminisme sur le serveur au SHA final**
  (recette C2) **et re-passe Astra** sur ce SHA, sauf décision humaine **écrite** traitant l'écart.

**C3b — deux paquets, dans cet ordre** (brief à écrire, non commencé) :

1. **Gate d'amendement du protocole** (amendements datés) : ligne run `R1_NOT_NORMALISED` à I.1 (remplace la convention
   du 21/09 sur la clause 3) ; E2 sur les six distributions et frontière de confiance sur les bornes ; tolérance MDD
   enregistré ↔ recalculé ; énumération § L.1 / `candles.json` quatrième entrée ; ratification des conventions
   d'outillage datées 21/09 et 22/09 ; renommage des clés `_btc` ; état `NOT_VERIFIABLE` de `stamp_cell`. **Chantier
   producteur** (runner) : export `lots` sous `liquidation[seg]` (D6, clause 3), `exec_interval` (D5), artefact de
   couverture (D1), **preuve de départ à plat à `T`** (§ B.2, clause 1 — pas un transport de champs : `--equity-out`
   n'a aucun point à `T`), `invocation.single_call` (clause 2), `first_fill_at` (clause 5), amorçage suffisant au
   préfixe (D2) ; dette 19 (liquidation terminale du moteur signal, § B.3), dette 15(c) ; exécution continue
   post-ancrage et procédure d'incertitude (§ B.4, § F.2). Aucune modification moteur sans écart démontré ; si
   modification, gate humain + invariant `compare-ab --strict`.
2. **Campagne réelle sous la chaîne** : inscription à `docs/RESEARCH_LOG.md` avant lancement, manifeste gelé,
   `c3_verdict.py chain` — les trois issues ne deviennent atteignables qu'alors.

**Conséquence opérationnelle : aucune sélection possible aujourd'hui** — non plus parce que l'outillage est incomplet,
mais parce qu'**aucune campagne existante ne traverse la chaîne** sans producteur conforme. Les conditions de démarrage
de B5 sont inchangées.

### B5 — Paper trading Bybit (4-6 semaines, ex-P9)

**Conditions de démarrage** : **un candidat validé sous le protocole C3** (remplace « B4 concluant »), connecteur
B1-B3 déployé, alertes Telegram (P8) en place, backup DB récurrent en place (fait le 16/09), test dette 13, trader
démasqué et `deploy.yml` re-couplé (marqueurs `# B5: re-enable trader`).

**Ce qu'on surveille** : P&L réel vs backtesté (drift < 20 %), nombre de trades vs attendu, drawdown max,
fills partiels sur LIMIT PostOnly (murs MM mobiles), stops déclenchés par des mèches EU absentes de
Binance, reconnexions WS.

**Critères de succès pour passer en live** : 4 semaines minimum sans crash, P&L net positif sur au moins
3 des 4 semaines, pas de trade aberrant, alertes fonctionnelles.

### P8 — Alertes Telegram + Monitoring (2-3 jours, en parallèle de B5)

- Notification sur chaque trade exécuté (BUY/SELL, montant, P&L), erreur critique / bot stoppé, daily
  loss limit atteinte, rapport quotidien P&L par stratégie (optionnel). Config : `TELEGRAM_BOT_TOKEN` dans `.env`.

### P10 — Live progressif

| Palier | Capital | Trigger | Durée min |
|---|---|---|---|
| 1 | 1,000 USDC | Paper concluant (B5) | 30 jours |
| 2 | 5,000 USDC | Palier 1 profitable 30j | 30 jours |
| 3 | 20,000 USDC | Palier 2 profitable 30j ; réévaluer OKX Europe (0.08/0.10 avec X-Perps) | Continu |

Stratégies actives à chaque palier : uniquement celles validées par le protocole C3 + B5. Risque de contrepartie
Bybit (incident cold wallet fév. 2025) : à garder en tête pour le scaling, pas un bloqueur à 1k-20k spot.

---

## Phases futures (post-go-live)

### P11 — ML Signal Filter (1-2 mois)
Prérequis : bot profitable en live depuis 2+ mois. LightGBM "enhancer" (meta-labeling « ce signal
sera-t-il profitable net fees ? »), toggle `ml.enabled: false`, walk-forward obligatoire.

### P12 — Évaluation Scalping
Avec les données live Bybit et les fees réelles : re-backtester `gemini_scalping_volatilite` et
`gemini_retour_moyenne` (conservées pour ça). Si PF > 1.5 → activer avec ML filter ; sinon abandon définitif.

### P13 — ML Vol Forecaster
Prédicteur de volatilité réalisée (4h/24h) pour ajuster ATR stops et grid spacing.

### P14 — RL Trader + Allocation Dynamique (2027)
Classifieur directionnel 4h comme stratégie supplémentaire ; allocation performance-based (Sharpe rolling).

---

## Décisions tranchées (permanentes)

1. **Bybit EU** remplace Binance (suspension UE du 1er juillet 2026). Instance séparée `api.bybit.eu` /
   `stream.bybit.eu` ; tout le code B1-B3 cible ce host.
2. **Backtests sur données Binance, fees Bybit.** Corrélation de prix 0.999999, zéro biais. Pas de
   ré-import Binance : les 8.7M rows restent en `exchange='binance'`, Bybit arrive en `exchange='bybit'`.
3. **Spread mesuré, pas supposé** : 0.02 % spread + 0.02 % slippage (conservateur vs B0).
4. **Quote USDC** conservée (MiCA-compliant ; USDT délisté chez les acteurs EU).
5. **PostOnly en entrée** pour garantir le maker ; sorties SL/trailing/timeout en MARKET.
6. **B4 est un prérequis absolu avant tout paper** : aucun classement P6/P7 (fees Binance flat) n'est repris tel quel ; **depuis C3 (22/09), la condition de démarrage de B5 est un candidat validé sous le protocole C3** (§ B5).
7. **Filtre exchange via `settings.exchange_name`**, plus de littéral en production.
8. ✅ **`TaskScheduler` via la factory** (B3) — backfill de gaps actif pour l'exchange courant (Bybit).
9. **Legacy Kraken** : stratégies et connecteur futures supprimés en B0.5 (supersède la décision « conserver
   tant que ça ne coûte rien » du plan de pivot) ; `connectors/kraken/rest.py` + `ws.py` restent (référence
   paper mode, `normalize_asset_*`) jusqu'à la généralisation B1 ; données `exchange='kraken'` supprimées
   quand Bybit est validé en live.
10. **Pas de ML avant profit live** — P11 après P10 concluant.
11. **Chaque stratégie validée** sur 3+ ans de backtest + cross-validate + walk-forward + 4 semaines paper.
12. **Scale seulement sur preuve** — 30 jours profitable avant d'augmenter le capital.
13. **Sélection darwinienne** — activer large, garder les gagnantes, tuer les perdantes.
14. **Instrument réparé (C1-C2) avant tout run de backtest.**
15. **Rejeu grid = diagnostic pré-spécifié**, hors quota des 2 familles/cycle mais inscrit au journal des essais.
16. **Protocole basse rotation** (voir `docs/CONTRAINTES_POST_B4.md`) : repères de couverture nécessaires jamais
    suffisants, « inconclusif = pas de déploiement ».
17. **Tout run de backtest est inscrit à `docs/RESEARCH_LOG.md` avant son lancement.**
18. **Aucune sélection hors `docs/protocole_c3.md`** (gelé `d931293`) : le protocole ne change que par amendement daté (gate) ; l'outillage exécute, il ne norme pas.

---

## Items non bloquants

- [x] **Backup DB récurrent** (16/09) : cron `scripts/backup_db.sh` 04:15 daily / 04:45 weekly (`pg_dump -Fc`, rotation
      7 j / 28 j) **avec test de restauration** prouvé le 16/09 sur container jetable (`skills/database.md`) — copie sur
      storage box Hetzner restant à faire
- [x] **Découplage `deploy.yml`** (16/09) : le workflow activait et redémarrait `krakenbot` puis exigeait qu'il tourne ;
      neutralisé tant que le trader est off (marqueurs `# B5: re-enable trader`, collector seul) ; trader masqué sur le serveur
- [ ] **Test dette 13** : test one-off prouvant que le chemin live/router résout les params de stratégie par instance
      (`class:` dans `strategies.yaml`), prérequis B5
- [x] **Cron de collecte orderbook élargie** (16/09) : horaire, bid + ask, 2 profondeurs, 24/7 (week-ends et heures US
      inclus) — `scripts/audit/bybit_q3_orderbook.py --host eu` → `~/audit_data/` sur le serveur
- [ ] **Chore cleanup repo post-C1** : archiver le kraken-era de `results/` vers `results/archive/`, retirer la dépendance
      `streamlit` de `pyproject.toml`, code Kraken conditionné à la dette 7, trier les 3 stashes git anciens, aligner
      `scripts/restore_db.sh` sur `skills/database.md` (`timescaledb_pre_restore()/post_restore()`, rôles)
- [ ] **OKX Europe** = option au palier 20k (0.08 / 0.10 avec compte X-Perps, non vérifié sur compte)
- [ ] Documenter les fees Bybit VIP tier quand le volume augmentera
- [ ] Nettoyer les données kraken legacy quand Bybit est validé en live (`DELETE FROM market_data_ohlc WHERE exchange='kraken'`)
- [ ] Rework du dashboard Dash pour afficher multi-pair + P&L par stratégie, filtre `settings.exchange_name`
- [ ] Type check mypy : 10 erreurs `union-attr` dans `main.py` (15 sur `src/`), post-B0.5
- [ ] Généraliser `execution/` (`normalize_asset_*`, type hint `KrakenRestClient`) hors de `connectors/kraken`
- [x] Nettoyer le chemin `is_multi` mort de `BacktestEngine` avec la refonte des fees (B4.2, `refactor(backtest): remove dead is_multi and short/rollover paths`)
- [ ] P6.8 — Optimisation backtest speedup (priorité basse) : DB locale ou cache OHLC Parquet pour éliminer
      la contention tunnel SSH ; cible 5-6× (vs 3× actuel) ; à faire avant P11 (ML)
- [x] `.env.example` : template Bybit (B1) · [x] `deploy.yml` : `EXCHANGE_NAME` + `BYBIT_*` (B2 ; secrets GitHub à créer) · [x] `deploy.yml` découplé du trader (16/09, voir ci-dessus)
