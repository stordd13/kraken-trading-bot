# KrakenBot — Roadmap (Septembre 2026)

> Roadmap consolidée post-pivot Bybit EU. Mise à jour : 8 septembre 2026 (B0.5).
> Décisions de pivot : `docs/archive/PIVOT_BYBIT_PLAN.md` · audit : `results/bybit_integration_audit.md`.

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
| P6 | Backtests 24 combos (8 stratégies × 3 paires), fees Binance 0.075 % flat | v2.0.0-p6-validated | **0/24 aux 5 critères stricts** (`results/P6_backtest_report_v2.md`) → survivors/walk-forward vides (normal) |
| P6.7 | Runner multiprocessing (resume, atomic save, déterminisme) | v2.1.0-p6-7-multiprocessing | Réutilisé pour B4 (`results/P6_7_multiprocessing_benchmark.md`) |
| P7 (phase 1) | Grid search cross-validé, 212 configs, 4 stratégies, fees Binance | — (branche mergée 7 sept) | `results/P7_phase1_cross_validate.json` — machinerie OK, **classements non transposables** aux fees Bybit |
| B0 | Audit Bybit EU (endpoints, lots, spread, historique, WS, ordres, rate limits, écart de prix) | — | **GO avec réserves** (`results/bybit_integration_audit.md`) |
| B0.5 | Refonte docs + suppression du code legacy Kraken-era | — | Cette version |

Le pivot Kraken → Binance (avril 2026) est documenté dans `docs/archive/ROADMAP_pre_binance_pivot.md`.

---

## Vue d'ensemble des phases à venir

| Phase | Quoi | Durée | Livrable / critère de done | Statut |
|---|---|---|---|---|
| **B1** | `BybitRestClient` (ccxt `hostname=bybit.eu`) + `BybitSettings` + `ExchangeFees.bybit_defaults()` + branche factory + tests ; fix `exchange_name` default ; fees maker/taker distincts dans `backtest.py` | 2-3 j | Round-trip d'ordre paper validé avec les vraies clés ; `scripts/audit/bybit_q1/q6/q7` relancés avec clés | ✅ 9 sept (round-trip live validé, `priceLimitRatioX` levé ; fees backtest → B4) |
| **B2** | `BybitWebSocketClient` (v5 public kline, 10 args/subscribe, ping 20 s) + tests ; réactivation du collector | 3-4 j | Candles `exchange='bybit'` en DB en continu 24 h sans zombie | 🚧 code livré 9 sept (`feat/b2-bybit-ws`), observation serveur 24 h à faire |
| **B3** | Import historique Bybit EU (REST paginé, batch 1000) ; collector/scheduler génériques (`TaskScheduler` via factory, backfill gap) | 2 j | Data Bybit en DB (≈ 2.5M candles depuis 2025-06-11), backfill fonctionnel | 📋 |
| **B4** | Re-run P6 (24 combos) et P7 (grid search phases 1-2 + rapport) sur données Binance avec fees Bybit maker/taker + spread/slippage mesurés | 1 j run + 1 j analyse | `results/B4_bybit_backtest_report.md`, sélection paper | 📋 — **prérequis absolu avant B5** |
| **B5** | Paper trading Bybit 4+ semaines (ex-P9) ; P8 Telegram en parallèle ; backup DB récurrent en place | 4-6 sem | 4 sem sans crash, P&L net > 0 sur 3/4 sem, drift backtest/paper < 20 %, pas de trade aberrant | 📋 |
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

### B4 — Re-run P6 + P7 avec fees Bybit (1 jour run + 1 jour analyse)

- Données Binance (8.7M rows), `--fees bybit` (maker/taker distincts, spread 0.02 %, slippage 0.02 %).
- P6 : 24 combos, 5 critères, walk-forward sur les survivants. P7 : grid search phases 1-2 + rapport
  sur les stratégies survivantes.
- Livrable : `results/B4_bybit_backtest_report.md` + sélection pour le paper. Une stratégie sans config
  qui passe est abandonnée.
- Révision risk management (ex-P7) intégrée : max positions ~100, daily loss 5 % dynamique, risk 2 %
  sous 5k, plancher 5-10 USDC, doctrine des sorties MARKET à 0.25 %.

### B5 — Paper trading Bybit (4-6 semaines, ex-P9)

**Conditions de démarrage** : B4 concluant, connecteur B1-B3 déployé, alertes Telegram (P8) en place,
backup DB récurrent en place.

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

Stratégies actives à chaque palier : uniquement celles validées par B4 + B5. Risque de contrepartie
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
6. **B4 est un prérequis absolu avant tout paper** : aucun classement P6/P7 (fees Binance flat) n'est repris tel quel.
7. **Filtre exchange via `settings.exchange_name`**, plus de littéral en production.
8. **`TaskScheduler` via la factory** (B3) — le backfill auto n'a jamais marché pour Binance.
9. **Legacy Kraken** : stratégies et connecteur futures supprimés en B0.5 (supersède la décision « conserver
   tant que ça ne coûte rien » du plan de pivot) ; `connectors/kraken/rest.py` + `ws.py` restent (référence
   paper mode, `normalize_asset_*`) jusqu'à la généralisation B1 ; données `exchange='kraken'` supprimées
   quand Bybit est validé en live.
10. **Pas de ML avant profit live** — P11 après P10 concluant.
11. **Chaque stratégie validée** sur 3+ ans de backtest + cross-validate + walk-forward + 4 semaines paper.
12. **Scale seulement sur preuve** — 30 jours profitable avant d'augmenter le capital.
13. **Sélection darwinienne** — activer large, garder les gagnantes, tuer les perdantes.

---

## Items non bloquants

- [ ] **Backup DB récurrent** : cron `pg_dump -Fc` + rotation + copie sur storage box Hetzner (requis avant B5)
- [ ] **OKX Europe** = option au palier 20k (0.08 / 0.10 avec compte X-Perps, non vérifié sur compte)
- [ ] Documenter les fees Bybit VIP tier quand le volume augmentera
- [ ] Nettoyer les données kraken legacy quand Bybit est validé en live (`DELETE FROM market_data_ohlc WHERE exchange='kraken'`)
- [ ] Rework du dashboard Dash pour afficher multi-pair + P&L par stratégie, filtre `settings.exchange_name`
- [ ] Type check mypy : 10 erreurs `union-attr` dans `main.py` (15 sur `src/`), post-B0.5
- [ ] Généraliser `execution/` (`normalize_asset_*`, type hint `KrakenRestClient`) hors de `connectors/kraken`
- [ ] Nettoyer le chemin `is_multi` mort de `BacktestEngine` avec la refonte des fees (B4)
- [ ] P6.8 — Optimisation backtest speedup (priorité basse) : DB locale ou cache OHLC Parquet pour éliminer
      la contention tunnel SSH ; cible 5-6× (vs 3× actuel) ; à faire avant P11 (ML)
- [x] `.env.example` : template Bybit (B1) · [x] `deploy.yml` : `EXCHANGE_NAME` + `BYBIT_*` (B2 ; secrets GitHub à créer) · [ ] `deploy.yml` ne doit pas redémarrer `krakenbot` avant B5
