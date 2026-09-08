# KrakenBot — Pivot Binance → Bybit EU (Septembre 2026)

> Contexte : Binance a retiré sa demande MiCA le 24 juin 2026 et suspendu ses services
> aux résidents UE le 1er juillet 2026. Pas de retour annoncé. Le bot doit changer d'exchange.
> Décision : Bybit EU (Bybit EU GmbH, agréé MiCA via FMA Autriche).

---

## 1. Pourquoi Bybit EU

| Candidat | Agrément | Maker / Taker spot (entrée) | Verdict |
|---|---|---|---|
| Kraken Pro | Irlande | 0.40 / 0.80 (refonte 9 juil. 2026) | Éliminé : 5× Binance, tue grid et stops |
| Coinbase Advanced | Irlande | 0.40–0.60 | Éliminé : fees |
| Bitvavo | Pays-Bas | 0.15 / 0.25 | Possible mais API plus limitée |
| OKX Europe | Malte | 0.08 / 0.10 avec compte X-Perps, 0.20 / 0.35 sinon | Alternative crédible, non vérifiée sur compte |
| **Bybit EU** | **Autriche** | **0.10 / 0.25 (vérifié sur le compte de Bruno)** | **Retenu** |

Fees Bybit EU spot mesurées sur le compte : maker 0.10 %, taker 0.25 %.
Round-trip limit/limit 0.20 % (vs 0.15 % Binance BNB), limit/market 0.35 %.
Le taker à 0.25 % pèse sur les sorties market (stop-loss, trailing, timeout) : les backtests doivent
utiliser maker et taker distincts, pas un taux flat.

Réserve connue : incident cold wallet Bybit février 2025. Risque de contrepartie à garder en tête
pour le scaling (P10), pas un bloqueur pour 1k–20k en spot.

Quote currency : on reste sur USDC (MiCA-compliant). USDT est délisté chez les acteurs EU.

---

## 2. Ce que le pivot Kraken → Binance nous a laissé (réutilisable tel quel)

- `ExchangeRestClient` Protocol + `build_exchange_rest_client` / `build_exchange_ws_client` (factory)
- `BaseWebSocketClient` ABC (reconnexion, heartbeat, stats)
- `ExchangeFees` (maker/taker/spread/slippage) avec `kraken_defaults` / `binance_defaults`
- Colonne `exchange` en DB, PK `(timestamp, pair, interval, exchange)`, `normalize_pair`
- Router / risk manager / execution engine / 8 stratégies : aucune référence à l'exchange
- P6.7 parallel runner, P7 grid search (`strategy_params_override`)
- 8.7M rows Binance (2021-01 → 2026-06) : restent la base de backtest

Hardcodes `binance` à généraliser (liste exhaustive, audit du 7 sept 2026) :
- `connectors/exchange.py` : dispatch factory (ajouter branche `bybit`)
- `indicators/multi_timeframe.py:240` et `multi_pair_registry.py:94` : default `exchange="binance"`
- `connectors/binance/ws.py:_handle_kline` : `exchange="binance"` (normal, c'est le connecteur)
- `scripts/backtest.py:227,1837` : sélection des fees par exchange
- `scheduler/task_scheduler.py:14,65,84` : hardcode `KrakenRestClient` (dette : le backfill auto
  n'a jamais marché pour Binance, cf. découverte P7)

---

## 3. Phases

| Phase | Quoi | Durée | Livrable / done |
|---|---|---|---|
| **B0** | Audit Bybit EU (API, paires, lot sizes, WS v5, historique, spread) | 1 j | `results/bybit_integration_audit.md` |
| **B1** | `BybitRestClient` (ccxt) + `BybitSettings` + `ExchangeFees.bybit_defaults` + factory + tests | 2-3 j | Paper order round-trip validé avec vraies clés |
| **B2** | `BybitWebSocketClient` (v5 public kline) + tests | 3-4 j | Candles `exchange='bybit'` en DB en continu 24h sans zombie |
| **B3** | Import historique Bybit (API paginée, batch 1000) + collector/scheduler génériques | 2 j | Data Bybit en DB, `TaskScheduler` passe par la factory, backfill gap fonctionnel |
| **B4** | Re-run P6 (24 combos) et P7 (grid search) avec fees Bybit maker/taker + spread mesuré | 1 j run + 1 j analyse | `results/B4_bybit_backtest_report.md`, sélection paper |
| **B5** | Paper trading Bybit 4+ semaines (ex-P9) ; P8 Telegram en parallèle | 4-6 sem | Critères P9 : 4 sem sans crash, P&L net > 0 sur 3/4 sem |
| **P10** | Live progressif 1k → 5k → 20k | Continu | Inchangé |

Règle : B0 avant tout. Ses conclusions (endpoints EU, profondeur data, spread réel) conditionnent
les prompts B1-B4, qui ne sont pas écrits avant.

---

## 4. Décisions tranchées

1. **Backtests sur données Binance, fees Bybit.** Les prix BTC/ETH/SOL sont quasi identiques
   d'un exchange à l'autre. On garde 5 ans d'historique plutôt que les 2-3 ans probables de Bybit
   USDC. Les données Bybit servent à valider la période commune et au warmup live.
2. **Spread mesuré, pas supposé.** Le 0.02 % de spread des backtests est remplacé par la mesure
   B0 sur BTC/USDC, ETH/USDC, SOL/USDC (Bybit EU).
3. **Pas de ré-import Binance.** Les 8.7M rows restent, `exchange='binance'`. Les données Bybit
   arrivent en `exchange='bybit'`. Filtre de production : `settings.exchange_name`, plus de littéral.
4. **Fix du backfill au passage.** `TaskScheduler` doit passer par la factory. C'est le bon moment,
   on touche déjà le collector.
5. **Kraken legacy conservé** dans le repo tant que ça ne coûte rien, supprimé quand Bybit est validé live.

---

## 5. Immédiat (avant B0)

- [ ] Hetzner : `sudo systemctl stop krakenbot krakenbot-collector` (tournent dans le vide depuis le 1er juillet)
- [ ] Hetzner : état de P7 (`tmux attach -t p7`, `ls results/P7_*`). Rapatrier les résultats s'ils existent.
- [ ] Binance : retirer les fonds (retraits toujours ouverts, pas de date limite annoncée)
- [ ] Bybit EU : créer clés API **read-only** pour B0
- [ ] Bybit EU : noter le spread bid/ask des 3 paires USDC à 3 moments de la journée
