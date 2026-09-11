# B3 — Données Bybit EU : backfill de gaps, import historique, TaskScheduler générique

> Généré le 2026-09-11, branche `feat/b3-bybit-data` (base `dev` @ `0f73115`, tag de départ `v2.4.0-b2-bybit-ws`).
> Spec : `agent/AGENT_B3_BYBIT_DATA_v2.md`. Serveur Hetzner, collector Bybit **actif pendant toute la phase**.

## Résumé exécutif

- **Backfill de gaps** (`krakenbot.data.backfill` + `scripts/backfill_gap.py`) démontré **avant l'import** sur
  les 22 gaps réels de la DB : 952 candles insérées, 0 trou résiduel, dont les 2 candles 1m `01:05` du 11/09
  (BTC, SOL) exigées **plus** les 2 candles 5m `01:05` de la même fermeture 1006 (la spec supposait « jamais ≥ 5m »).
- **`BybitRestClient.fetch_ohlcv`** rebranché sur l'endpoint brut v5 (`publicGetV5MarketKline` via ccxt) :
  `timestamp = start + interval`, `vwap = turnover/volume`, candle en cours exclue. Contrat **Bybit seulement**.
- **`TaskScheduler`** : client REST read-only injecté par le collector, job unique `gap_backfill` à 03:30 UTC,
  fenêtre de scan 3 jours, events `SCHEDULER_TASK_*` (qui n'existaient pas dans `EventType` : AttributeError latent).
- **Constat convention timestamp** (§ 6) : rows Binance **open-stamped**, rows Bybit **end-stamped** → dette B4.
- Tests : 1140 passés (+ 35 nouveaux), 4 échecs préexistants dépendants de l'ordre (documentés dans la mémoire
  projet), ruff propre, mypy 35 erreurs (48 avant B3, aucune dans le nouveau code).

## 1. Décisions

| # | Décision | Pourquoi |
|---|---|---|
| 1 | Logique de backfill dans `src/krakenbot/data/backfill.py`, scripts = wrappers | dette `src/ → scripts/` remboursée (spec §2.1) |
| 2 | `fetch_ohlcv` Bybit via l'endpoint brut (API implicite ccxt, même hostname EU et même token-bucket) | `turnover` indispensable au `vwap` ; un seul chemin pour import et backfill |
| 3 | Convention Bybit = fin de période (`start + interval`), identique au WS B2 | spec §2.2 ; ~9k rows WS déjà en DB |
| 4 | Contrat `fetch_ohlcv` end-stamped **honnêtement limité à Bybit** (docstring Protocol) | amendement A : Binance/Kraken restent open-time ccxt, Binance en DB est mixte |
| 5 | Client du scheduler en **read-only** (`build_exchange_rest_client(..., read_only=True)`) | amendement B : jamais la clé trade pour de la lecture, même en `TRADING_MODE=live` (B5) |
| 6 | `SCHEDULER_BACKFILL_DAYS` défaut **3**, cron **`30 3 * * *`** | amendement C ; après la fenêtre 1006 01:00–02:40 UTC |
| 7 | Un seul job APScheduler (pas 7) | un rate limiter, un run séquentiel, `max_instances=1` réel |
| 8 | Reprise d'import consciente du **trou de tête** (`MIN(timestamp)` trop récent ⇒ scan complet) | le collector écrit depuis le 09/09 : `MAX(timestamp)` = maintenant, une reprise naïve sauterait tout l'historique |
| 9 | Grille 1w ancrée **lundi** (offset 4 jours depuis l'epoch, un jeudi) | la query « désalignement » de `skills/bybit.md` était fausse pour 10080 |
| 10 | Suppression de `scripts/fetch_ohlc.py` et `backfill_binance_gap.py` | validé par Bruno ; plus aucun consommateur |
| 11 | `exchange` obligatoire au warmup des analyzers (dette n°8) | validé par Bruno ; `main.py` passait déjà `settings.exchange_name` |

## 2. Vérifications locales (lecture seule, tunnel)

Endpoint brut sur `api.bybit.eu`, clé read-only, `api_calls=5` :

```
FIRST EU 1h candles (DB ts = start+interval):
   2025-06-11 10:00:00+00:00 o 109720.1 c 109720.1 vol 0 vwap None
   2025-06-11 11:00:00+00:00 o 109720.1 c 109720.1 vol 0 vwap None
   2025-06-11 12:00:00+00:00 o 109720.1 c 109298 vol 0.00002 vwap 109298.00000000
FIRST EU 1w candles:
   2025-06-16 00:00:00+00:00 Monday o 109720.1
   2025-06-23 00:00:00+00:00 Monday o 109298
   2025-06-30 00:00:00+00:00 Monday o 109298
RECENT 1d candles (compare with DB WS rows 2026-09-10/11):
   2026-09-10 00:00:00+00:00 o 78466.1 c 78284.2      ← identique à la row WS en DB
   2026-09-11 00:00:00+00:00 o 78284.2 c 76565.2      ← identique à la row WS en DB
1m candles around the known gap (DB ts 01:05 missing):
   2026-09-11 01:05:00+00:00 o 76982.2 c 76982.2 vol 0 vwap None
```

Première candle EU : **2025-06-11 09:00 UTC** (1h, DB ts `10:00`), plate. Dry-run d'import (curseurs) : 673 appels
estimés pour BTC 1m, total ≈ 2 550 (cohérent avec l'estimation B0 de 2 532).

## 3. Séquence serveur — étape 1 : démo backfill AVANT l'import (2026-09-11 08:20 UTC)

Déploiement : `git checkout feat/b3-bybit-data` @ `4500877`, `poetry install`, `.env` serveur inchangé
(`SCHEDULER_ENABLED=true`, `EXCHANGE_NAME=bybit`, 3 paires × 7 TF), `krakenbot-collector` **active**, `krakenbot` inactive.

### 3.1 Preuve SQL AVANT (`server_now = 2026-09-11 08:20:31 UTC`)

```
   pair   | interval |          prev          |          next          | missing
----------+----------+------------------------+------------------------+---------
 BTC/USDC |        1 | 2026-09-09 13:38:00+00 | 2026-09-09 13:40:00+00 |       1
 BTC/USDC |        1 | 2026-09-09 13:56:00+00 | 2026-09-09 13:58:00+00 |       1
 BTC/USDC |        1 | 2026-09-09 14:07:00+00 | 2026-09-09 18:13:00+00 |     245
 BTC/USDC |        1 | 2026-09-11 01:04:00+00 | 2026-09-11 01:06:00+00 |       1   ← candle 01:05 (fermeture 1006 01:04:54)
 BTC/USDC |        5 | 2026-09-09 14:05:00+00 | 2026-09-09 18:15:00+00 |      49
 BTC/USDC |        5 | 2026-09-11 01:00:00+00 | 2026-09-11 01:10:00+00 |       1   ← 5m 01:05, même fermeture
 BTC/USDC |       15 | 2026-09-09 14:00:00+00 | 2026-09-09 18:15:00+00 |      16
 BTC/USDC |       60 | 2026-09-09 14:00:00+00 | 2026-09-09 19:00:00+00 |       4
 ETH/USDC |        1 | 2026-09-09 13:38:00+00 | 2026-09-09 13:40:00+00 |       1
 ETH/USDC |        1 | 2026-09-09 13:56:00+00 | 2026-09-09 13:58:00+00 |       1
 ETH/USDC |        1 | 2026-09-09 14:07:00+00 | 2026-09-09 18:13:00+00 |     245
 ETH/USDC |        5 | 2026-09-09 14:05:00+00 | 2026-09-09 18:15:00+00 |      49
 ETH/USDC |       15 | 2026-09-09 14:00:00+00 | 2026-09-09 18:15:00+00 |      16
 ETH/USDC |       60 | 2026-09-09 14:00:00+00 | 2026-09-09 19:00:00+00 |       4
 SOL/USDC |        1 | 2026-09-09 13:38:00+00 | 2026-09-09 13:40:00+00 |       1
 SOL/USDC |        1 | 2026-09-09 13:56:00+00 | 2026-09-09 13:58:00+00 |       1
 SOL/USDC |        1 | 2026-09-09 14:07:00+00 | 2026-09-09 18:13:00+00 |     245
 SOL/USDC |        1 | 2026-09-11 01:04:00+00 | 2026-09-11 01:06:00+00 |       1   ← candle 01:05
 SOL/USDC |        5 | 2026-09-09 14:05:00+00 | 2026-09-09 18:15:00+00 |      49
 SOL/USDC |        5 | 2026-09-11 01:00:00+00 | 2026-09-11 01:10:00+00 |       1
 SOL/USDC |       15 | 2026-09-09 14:00:00+00 | 2026-09-09 18:15:00+00 |      16
 SOL/USDC |       60 | 2026-09-09 14:00:00+00 | 2026-09-09 19:00:00+00 |       4
(22 rows)
```
Rows à `2026-09-11 01:05` (interval 1, 5) : **2** (les deux d'ETH, qui avait reçu la candle). Le trou 14:07 → 18:13
du 09/09 est l'intervalle entre la collecte locale de validation B2 et le démarrage du collector serveur.

### 3.2 Dry-run puis run réel

`scripts/backfill_gap.py --dry-run` : 22 gaps listés (identiques à la table ci-dessus, `tail_gap` = aucun car
le collector est à jour ; `backfill_no_baseline` pour 1w : pas encore de candle hebdo clôturée depuis le 09/09).

Run réel (`08:21:14 → 08:21:23 UTC`, 9 s, 22 appels REST) :
```
backfill_gap_filled pair=BTC/USDC interval=1  start=2026-09-09T13:39 end=2026-09-09T13:39 missing=1   fetched=1000 inserted=1   pages=1 stop_reason=completed
backfill_gap_filled pair=BTC/USDC interval=1  start=2026-09-09T14:08 end=2026-09-09T18:12 missing=245 fetched=1000 inserted=245 pages=1 stop_reason=completed
backfill_gap_filled pair=BTC/USDC interval=1  start=2026-09-11T01:05 end=2026-09-11T01:05 missing=1   fetched=437  inserted=1   pages=1 stop_reason=completed
backfill_gap_filled pair=BTC/USDC interval=5  start=2026-09-11T01:05 end=2026-09-11T01:05 missing=1   fetched=88   inserted=1   pages=1 stop_reason=completed
… (22 lignes, toutes inserted == missing)
backfill_completed candles_inserted=952 dry_run=False exchange=bybit failures=0 gaps_filled=22 gaps_found=22
```
Second run immédiat : `gaps_found=0 gaps_filled=0 candles_inserted=0 failures=0` (idempotence).

### 3.3 Preuve SQL APRÈS (`server_now = 2026-09-11 08:21:31 UTC`)

```
 pair | interval | prev | next
------+----------+------+------
(0 rows)                                   ← zéro trou interne, toutes paires, tous TF

   pair   | interval |       timestamp        |      open      |      high      |      low       |     close      |   volume   |      vwap
----------+----------+------------------------+----------------+----------------+----------------+----------------+------------+----------------
 BTC/USDC |        1 | 2026-09-11 01:05:00+00 | 76982.20000000 | 76982.20000000 | 76982.20000000 | 76982.20000000 | 0.00000000 |               ← plate, vwap NULL
 BTC/USDC |        5 | 2026-09-11 01:05:00+00 | 76895.80000000 | 76982.20000000 | 76895.80000000 | 76982.20000000 | 0.02432100 | 76944.32278278
 ETH/USDC |        1 | 2026-09-11 01:05:00+00 |  2456.75000000 |  2456.75000000 |  2456.75000000 |  2456.75000000 | 0.00000000 |
 ETH/USDC |        5 | 2026-09-11 01:05:00+00 |  2456.49000000 |  2456.75000000 |  2456.49000000 |  2456.75000000 | 0.00200000 |  2456.75000000
 SOL/USDC |        1 | 2026-09-11 01:05:00+00 |    99.40000000 |    99.40000000 |    99.40000000 |    99.40000000 | 0.00000000 |
 SOL/USDC |        5 | 2026-09-11 01:05:00+00 |    99.13000000 |    99.40000000 |    99.13000000 |    99.40000000 | 6.57800000 |    99.33644269
(6 rows)

   pair   | interval |  n   |         min_ts         |         max_ts         | vwap_null_with_volume
 BTC/USDC |        1 | 2594 | 2026-09-09 13:08:00+00 | 2026-09-11 08:21:00+00 |                     0
 BTC/USDC |        5 |  519 | 2026-09-09 13:10:00+00 | 2026-09-11 08:20:00+00 |                     0
 BTC/USDC |       15 |  173 | 2026-09-09 13:15:00+00 | 2026-09-11 08:15:00+00 |                     0
 BTC/USDC |       60 |   43 | 2026-09-09 14:00:00+00 | 2026-09-11 08:00:00+00 |                     0
 (idem ETH, SOL ; 4h/1d inchangés)
```
Counts : 1m 2345 → 2594 (+249 = 245 + 1 + 1 + 1 + 1), 5m 469 → 519 (+50), 15m 157 → 173 (+16), 1h 39 → 43 (+4).
`vwap NULL` ⇔ `volume = 0` sur toutes les candles comblées.

**Gate 1 soumise à Bruno avant l'import.**

## 4. Séquence serveur — étape 2 : import historique (tmux `b3-import`, collector actif)

`poetry run python scripts/bybit_kline_import.py` — **09:07:49 → 09:41:42 UTC, 2 034 s (34 min), exit 0**,
2 553 appels, 2 543 294 candles reçues, **2 533 015 insérées** (la différence = rows déjà écrites par le WS et le
backfill de l'étape 1, ON CONFLICT DO NOTHING). Pour chaque série le curseur de reprise a détecté le **trou de tête**
(`bybit_import_leading_hole`, `MIN(timestamp)=2026-09-09 …`) et scanné depuis 2025-06-01.

Durée : ~0,8 s par page (rate limit ccxt 100 ms + RTT + insertion de 1 000 rows), contre « ~15 min » estimés en B0
pour le fetch seul — pas d'anomalie, cadence constante (BTC/ETH/SOL 1m : 528 / 520 / 527 s).

```
  Pair      TF   Since (open)               Res  Est. Pages  Fetched Inserted Last ts                      Dur s  Stop
  BTC/USDC  1m   2025-06-01T00:00:00+00:00  no    674   659   658076   655427 2026-09-11T09:16:00+00:00    528.4  reached_now
  BTC/USDC  5m   2025-06-01T00:00:00+00:00  no    135   132   131615   131085 2026-09-11T09:15:00+00:00    103.9  reached_now
  BTC/USDC  15m  2025-06-01T00:00:00+00:00  no     45    44    43872    43695 2026-09-11T09:15:00+00:00     34.7  reached_now
  BTC/USDC  1h   2025-06-01T00:00:00+00:00  no     12    11    10968    10924 2026-09-11T09:00:00+00:00      8.7  reached_now
  BTC/USDC  4h   2025-06-01T00:00:00+00:00  no      3     3     2742     2732 2026-09-11T08:00:00+00:00      2.5  reached_now
  BTC/USDC  1d   2025-06-01T00:00:00+00:00  no      1     1      457      455 2026-09-11T00:00:00+00:00      0.5  reached_now
  BTC/USDC  1w   2025-05-26T00:00:00+00:00  no      1     1       65       65 2026-09-07T00:00:00+00:00      0.3  reached_now
  ETH/USDC  1m   …                          no    674   659   658052   655392 2026-09-11T09:27:00+00:00    520.2  reached_now
  ETH/USDC  5m   …                          no    135   132   131610   131078 2026-09-11T09:25:00+00:00    104.0  reached_now
  ETH/USDC  15m  …                          no     45    44    43871    43693 2026-09-11T09:30:00+00:00     34.8  reached_now
  ETH/USDC  1h   …                          no     12    11    10968    10924 2026-09-11T09:00:00+00:00      9.6  reached_now
  ETH/USDC  4h   …                          no      3     3     2742     2732 2026-09-11T08:00:00+00:00      2.4  reached_now
  ETH/USDC  1d   …                          no      1     1      457      455 2026-09-11T00:00:00+00:00      0.5  reached_now
  ETH/USDC  1w   …                          no      1     1       65       65 2026-09-07T00:00:00+00:00      0.3  reached_now
  SOL/USDC  1m   …                          no    674   659   658029   655357 2026-09-11T09:39:00+00:00    526.8  reached_now
  SOL/USDC  5m   …                          no    135   132   131606   131071 2026-09-11T09:40:00+00:00    108.5  reached_now
  SOL/USDC  15m  …                          no     45    44    43868    43690 2026-09-11T09:30:00+00:00     34.3  reached_now
  SOL/USDC  1h   …                          no     12    11    10967    10923 2026-09-11T09:00:00+00:00      8.8  reached_now
  SOL/USDC  4h   …                          no      3     3     2742     2732 2026-09-11T08:00:00+00:00      2.4  reached_now
  SOL/USDC  1d   …                          no      1     1      457      455 2026-09-11T00:00:00+00:00      0.5  reached_now
  SOL/USDC  1w   …                          no      1     1       65       65 2026-09-07T00:00:00+00:00      0.3  reached_now
  total: pages=2553 fetched=2543294 inserted=2533015 duration=2034s
```

### 4.1 Condition d'arrêt — prouvée par les deux dernières réponses de chaque série (`last_responses`)

Toutes les séries s'arrêtent sur `reached_now` : la dernière page est **courte** (< 1000) et sa dernière candle est
la **dernière candle clôturée** (`last_closed = floor(now)`), la candle en cours ayant été exclue par `fetch_ohlcv`.
Exemples bruts :
```
BTC 1m : [{since: 2026-09-10T15:20, candles: 1000, last: 2026-09-11T08:00}, {since: 2026-09-11T08:00, candles: 76, last: 2026-09-11T09:16}]  now≈09:16:37
BTC 1h : [{since: 2026-06-21T09:00, candles: 1000, last: 2026-08-02T01:00}, {since: 2026-08-02T01:00, candles: 968, last: 2026-09-11T09:00}]
BTC 1d : [{since: 2025-06-01T00:00, candles: 457, first: 2025-06-12T00:00, last: 2026-09-11T00:00}]   (1 page)
BTC 1w : [{since: 2025-05-26T00:00, candles: 65,  first: 2025-06-16T00:00, last: 2026-09-07T00:00}]   (1 page, lundi)
```
Le cas « page courte puis réponse vide » (fin d'historique **passée**) n'a pas eu à se produire : l'historique EU
va jusqu'à maintenant. Il est couvert par les tests unitaires (`test_short_page_then_empty_is_end_of_history`).

### 4.2 Validations SQL post-import (`server_now = 2026-09-11 09:42:10 UTC`)

```
   pair   | interval |   n    |         min_ts         |         max_ts         |  flat  | vwap_null_with_vol | vwap_with_zero_vol
----------+----------+--------+------------------------+------------------------+--------+--------------------+--------------------
 BTC/USDC |        1 | 658102 | 2025-06-11 09:21:00+00 | 2026-09-11 09:42:00+00 | 155656 |                  0 |                  0
 BTC/USDC |        5 | 131620 | 2025-06-11 09:25:00+00 | 2026-09-11 09:40:00+00 |  13818 |                  0 |                  0
 BTC/USDC |       15 |  43873 | 2025-06-11 09:30:00+00 | 2026-09-11 09:30:00+00 |   2899 |                  0 |                  0
 BTC/USDC |       60 |  10968 | 2025-06-11 10:00:00+00 | 2026-09-11 09:00:00+00 |    518 |                  0 |                  0
 BTC/USDC |      240 |   2742 | 2025-06-11 12:00:00+00 | 2026-09-11 08:00:00+00 |    118 |                  0 |                  0
 BTC/USDC |     1440 |    457 | 2025-06-12 00:00:00+00 | 2026-09-11 00:00:00+00 |     18 |                  0 |                  0
 BTC/USDC |    10080 |     65 | 2025-06-16 00:00:00+00 | 2026-09-07 00:00:00+00 |      2 |                  0 |                  0
 ETH/USDC |        1 | 658067 | 2025-06-11 09:56:00+00 | 2026-09-11 09:42:00+00 | 235483 |                  0 |                  0
 ETH/USDC |        5 | 131613 | 2025-06-11 10:00:00+00 | 2026-09-11 09:40:00+00 |  16444 |                  0 |                  0
 ETH/USDC |       15 |  43871 | 2025-06-11 10:00:00+00 | 2026-09-11 09:30:00+00 |   2765 |                  0 |                  0
 ETH/USDC |       60 |  10968 | 2025-06-11 10:00:00+00 | 2026-09-11 09:00:00+00 |    506 |                  0 |                  0
 ETH/USDC |      240 |   2742 | 2025-06-11 12:00:00+00 | 2026-09-11 08:00:00+00 |    119 |                  0 |                  0
 ETH/USDC |     1440 |    457 | 2025-06-12 00:00:00+00 | 2026-09-11 00:00:00+00 |     19 |                  0 |                  0
 ETH/USDC |    10080 |     65 | 2025-06-16 00:00:00+00 | 2026-09-07 00:00:00+00 |      2 |                  0 |                  0
 SOL/USDC |        1 | 658032 | 2025-06-11 10:31:00+00 | 2026-09-11 09:42:00+00 | 227209 |                  0 |                  0
 SOL/USDC |        5 | 131606 | 2025-06-11 10:35:00+00 | 2026-09-11 09:40:00+00 |  17591 |                  0 |                  0
 SOL/USDC |       15 |  43868 | 2025-06-11 10:45:00+00 | 2026-09-11 09:30:00+00 |   3145 |                  0 |                  0
 SOL/USDC |       60 |  10967 | 2025-06-11 11:00:00+00 | 2026-09-11 09:00:00+00 |    542 |                  0 |                  0
 SOL/USDC |      240 |   2742 | 2025-06-11 12:00:00+00 | 2026-09-11 08:00:00+00 |    121 |                  0 |                  0
 SOL/USDC |     1440 |    457 | 2025-06-12 00:00:00+00 | 2026-09-11 00:00:00+00 |     18 |                  0 |                  0
 SOL/USDC |    10080 |     65 | 2025-06-16 00:00:00+00 | 2026-09-07 00:00:00+00 |      2 |                  0 |                  0

 interval | misaligned          (grille 1w ancrée lundi : offset 4 j)
        1 |          0
        5 |          0
       15 |          0
       60 |          0
      240 |          0
     1440 |          0
    10080 |          0

 pair | interval | prev | next
------+----------+------+------
(0 rows)                                   ← zéro trou interne (query LAG, 21 séries)

 exchange |  count
 binance  | 8712718
 bybit    | 2543347
 kraken   | 1181469
```
- **2 543 347 rows Bybit** (estimation B0 : ~2.5M). MIN 1m = 2025-06-11 09:21 (BTC), 09:56 (ETH), 10:31 (SOL) ;
  1d depuis le 2025-06-12 00:00 (candle du 11 juin) ; 1w depuis le 2025-06-16 (lundi).
- `vwap IS NULL ⇔ volume = 0` sur les 2.5M rows (deux compteurs à 0). **24 % de candles 1m plates** sur BTC,
  36 % sur ETH/SOL — l'EU est peu liquide la nuit et les premières semaines.

## 5. Cohérences croisées (§3.3) — `scripts/audit/bybit_b3_crosscheck.py` (serveur, 09:42 UTC)

### (a) 1d / 1w : décalage d'exactement un intervalle — OK, pas de STOP

Pour la même candle, la row Bybit porte le timestamp de fin, la row Binance (Vision) celui d'ouverture. Preuve :
en joignant Binance à `ts − 1 intervalle`, 276/294 opens 1d coïncident à 1 % près, contre 115/293 au même `ts`
(1w : 40/43 décalé vs 8/42 au même ts). Toutes les candles 1w des deux exchanges tombent un **lundi** (DOW=1).
```
BTC/USDC 1d: bybit_rows=457 [2025-06-12 → 2026-09-11] | binance rows at SAME ts=293 (open within 1 %: 115) | binance rows at ts-1d=294 (open within 1 %: 276)  → OK
BTC/USDC 1w: bybit_rows=65  [2025-06-16 → 2026-09-07] | binance rows at SAME ts=42  (open within 1 %: 8)   | binance rows at ts-1w=43  (open within 1 %: 40)   → OK
    DOW (0=Sun,1=Mon): [('binance', 1, 246), ('bybit', 1, 65)]
ETH/USDC 1d: … SAME ts=293 (98) | ts-1d=294 (275) → OK      ETH/USDC 1w: … SAME ts=42 (5) | ts-1w=43 (39) → OK
SOL/USDC 1d: … SAME ts=293 (63) | ts-1d=294 (274) → OK      SOL/USDC 1w: … SAME ts=42 (3) | ts-1w=43 (39) → OK
```
Décision (validée) : Bybit reste en fin de période ; la divergence est la dette 11 (§ 6), pas un défaut de B3.

### (b) Prix 1h Bybit EU vs Binance (Binance décalé de +1 h), chevauchement 2025-06 → 2026-03-31 — OK

```
BTC/USDC 1h: n=6529 [2025-06-11 12:00 → 2026-04-01 00:00] corr=0.999994 |diff| median=1.73 bps p99=23.2 bps max=196.8 bps at 2026-02-06 01:00 (bybit 64665.60 vs binance 63417.51) signed mean=+0.09 bps
ETH/USDC 1h: n=6541 [2025-06-27 18:00 → 2026-04-01 00:00] corr=0.999983 |diff| median=3.55 bps p99=48.5 bps max=333.0 bps at 2025-07-04 19:00 (bybit 2568.00 vs binance 2485.23) signed mean=-0.17 bps
SOL/USDC 1h: n=6504 [2025-06-27 18:00 → 2026-04-01 00:00] corr=0.999987 |diff| median=3.35 bps p99=46.7 bps max=305.5 bps at 2025-07-24 06:00 (bybit 176.42 vs binance 181.98) signed mean=-0.84 bps
```
Corrélation > 0.999 partout, écart médian 2–4 bps (bruit), biais signé ≈ 0. Les maxima (2–3 %) sont des heures
isolées d'illiquidité EU (juillet 2025 pour ETH/SOL, nuit du 2026-02-06 pour BTC) : ils justifient le slippage
simulé de B4 mais ne remettent pas en cause « backtests sur données Binance ». Le p99 (23–49 bps) est plus large
que celui de Q8 en B0 (18 bps) parce que la période couvre les premiers mois de l'instance EU.

### (c) WS vs REST : 9 candles (1m / 1h / 1d × 3 paires) — IDENTIQUES, vwap compris

```
BTC/USDC 1m   2026-09-09 18:13: DB 78635.2/78635.2/78615.2/78615.2/0.001425 vwap=78617.38007018 | REST idem → OHLCV IDENTICAL, vwap same
BTC/USDC 60m  2026-09-09 19:00: DB 78760/78760/78407.9/78407.9/1.039725 vwap=78581.19581216 | REST idem → IDENTICAL
BTC/USDC 1440m 2026-09-10 00:00: DB 78466.1/79750/77758.4/78284.2/79.927808 vwap=78985.46316858 | REST idem → IDENTICAL
ETH/USDC 1m / 60m / 1440m, SOL/USDC 1m / 60m / 1440m : IDENTICAL, vwap same
```
`ON CONFLICT DO NOTHING` sous chevauchement WS/REST : aucune surprise, les rows WS conservées sont égales à ce que
le REST aurait écrit.

## 5bis. Séquence serveur — étapes 4 et 5 : restart du collector, scheduler

`sudo systemctl restart krakenbot-collector` à **09:43:34 UTC** (branche `feat/b3-bybit-data` @ `4500877`) :
```
bybit_rest_initialized   mode=paper hostname=bybit.eu key_role=readonly has_api_key=true          ← amendement B
task_scheduler_initialized exchange=bybit timezone=UTC enabled=true cron="30 3 * * *" lookback_days=3
collector_initialized    components=[event_bus, database, rest_client, websocket_client, task_scheduler]
task_scheduler_started   num_jobs=1 job_id=gap_backfill cron="30 3 * * *" pairs=[BTC,ETH,SOL] intervals=[1,5,15,60,240,1440,10080]
bybit_ws_ohlc_complete   pair=ETH/USDC interval=1 close=2462.25 volume=0 candle_timestamp=2026-09-11T09:45:00+00:00   ← plus de kwarg timestamp=
collector_periodic_stats (09:48:39) scheduler={"num_jobs": 1, "jobs": [{"id": "gap_backfill", "next_run": "2026-09-12T03:30:00+00:00"}]}
                         rest_client api_calls=0 ; ws ohlc_received=21 reconnections=0 errors=0
```
0 ligne `error`/`traceback` dans le journal, 0 kwarg `timestamp=` sur `ohlc_complete`.

- **Mini-gap du restart** : aucun — reconnexion en 5 s sans clôture de candle dans la fenêtre
  (`backfill_gap.py --dry-run` à 09:45 : `gaps_found=0`, run réel : 0 ; LAG depuis 09:00 : 0 trou).
- **Corps du job exécuté une fois à la main** (même code que le cron, `TaskScheduler.run_backfill()` avec le client
  read-only) à 09:46:16 UTC : `scheduled_backfill_completed gaps_found=0 gaps_filled=0 candles_inserted=0 duration_s=2.9`,
  row `task_execution_logs id=676 task_id=gap_backfill pair='*' interval=0 status=success candles_fetched=0`.
  (Le script one-off n'a pas attendu `bus.subscribe`, donc il n'a pas capté l'event ; la publication de
  `SCHEDULER_TASK_SUCCESS` est couverte par `tests/test_scheduler/test_task_scheduler.py`.)
- **Première exécution cron réelle : 2026-09-12 03:30 UTC — pas encore observée à la clôture de ce rapport.**
  À vérifier par Bruno :
  ```bash
  sudo journalctl -u krakenbot-collector --since "2026-09-12 03:29" --no-pager -o cat | grep -E "scheduled_backfill|backfill_gap"
  sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot -c "SELECT * FROM task_execution_logs WHERE task_id='gap_backfill' ORDER BY id DESC LIMIT 10;"
  ```
  Attendu : 1 row de run (`pair='*'`) + 0–2 rows de gaps 1m/5m si une fermeture 1006 a chevauché une clôture.

## 6. Constat : conventions de timestamp divergentes (dette B4)

Vérifié en DB (tunnel, 2026-09-11 07:35 UTC) :

```
binance BTC/USDC 1d : 2023-12-31 open 42145.98 close 42274.27 | 2024-01-01 open 42274.27 close 44185.08  → open time
binance BTC/USDC 1w : 2024-01-01 (lundi) open 42274.27                                                     → open time
binance BTC/USDC 1m : MAX(timestamp) = 2026-03-31 23:59                                                    → open time
bybit   BTC/USDC 1d : 2026-09-10 00:00 open 78466.1 close 78284.2 (= candle du 9 sept)                      → fin de période
```
Les rows Binance (import Vision, `scripts/binance_vision_import.py:124-136`, `timestamp = row[0]` = open time)
sont **open-stamped** ; les rows WS (Binance `k["T"] + 1`, Bybit `end + 1 ms`) et l'import B3 sont **end-stamped**.
`skills/database.md`, `skills/binance_import.md` et `PROJECT_CONTEXT.md` affirmaient le contraire — corrigés.

**Dette consignée (formulation validée par Bruno)** : moteur de backtest conçu pour end-stamps + données Binance
open-stamped = look-ahead multi-TF dans P6/P7 ; fenêtre avril–juin 2026 à auditer (collisions PK WS/Vision) ;
remédiation (re-stamp Binance ou adaptation moteur + assainissement de la fenêtre) à trancher en ouverture de B4,
avant tout re-run. Rien de plus en B3 — pas de fix, pas de re-stamp, juste le constat sourcé. B4 était déjà le
moment où on rouvre `backtest.py` pour les fees ; c'est maintenant un prérequis de validité, pas juste de coûts.

Conséquence pour B3 : l'import Bybit garde la convention WS (fin de période) ; le contrôle 1d/1w du § 5 attend
un décalage d'**exactement un intervalle** entre Bybit et Binance pour la même candle.

## 7. Anomalies et limites

- `EventType.SCHEDULER_TASK_SUCCESS/FAILED` étaient référencés par l'ancien scheduler mais **absents** de l'enum
  (AttributeError au premier run, jamais exercé par les tests) → ajoutés.
- Gap 5m la nuit du 11/09 (BTC, SOL) : la spec supposait « jamais sur les TF ≥ 5m » ; faux dès la première nuit
  avec une fermeture chevauchant une clôture 5m. Le backfill couvre les 7 TF.
- L'invariant `fetch_ohlcv` end-stamped n'existe que pour Bybit : le backfill générique **n'est pas correct** sur
  binance/kraken (candles décalées d'un intervalle, sans erreur). Écrit dans le Protocol, le module, le CLI (warning).
- `poetry` absent du PATH SSH non interactif sur le serveur (`bash -lc` nécessaire) — sans impact sur systemd.
- Durée d'import 34 min (2 553 pages à ~0,8 s) contre « ~15 min » estimés : l'estimation B0 ne comptait pas
  l'insertion ; cadence constante, pas d'anomalie.
- Illiquidité EU : 24–36 % de candles 1m plates sur 15 mois ; maxima d'écart 1h vs Binance de 2–3 % sur des heures
  isolées (juillet 2025 ETH/SOL, 2026-02-06 BTC) — argument pour le slippage simulé de B4.
- `skills/deployment.md:72-75` décrit encore le template `.env` de `deploy.yml` comme « Kraken-era » : périmé
  (le template est Bybit depuis B2), non corrigé ici (hors scope).

## 8. Critères de fin (spec §4)

- [x] Les 2 candles 1m du 11/09 (BTC, SOL) comblées **par le backfill, avant l'import**, preuve SQL (§ 3).
- [x] Historique Bybit complet en DB : 2 543 347 rows, 3 paires × 7 TF depuis 2025-06-11, 0 désalignement, 0 trou (§ 4).
- [x] Cohérences croisées §3.3 passées, aucun STOP (§ 5) ; divergence 1d/1w = décalage d'un intervalle, documentée.
- [x] `TaskScheduler` sans Kraken en dur, sans import de `scripts/`, actif pour tout exchange ; garde supprimée ;
      `task_scheduler_started num_jobs=1`, `next_run=2026-09-12T03:30:00+00:00`.
- [~] Exécution schedulée : corps du job exécuté et loggé (`task_execution_logs id=676`) ; **le premier tir cron
      (12/09 03:30 UTC) reste à observer** (commandes ci-dessus).
- [x] `pytest` + `ruff` verts (1140 passés ; 4 échecs préexistants dépendants de l'ordre), mypy 35 erreurs (48 avant).
- [x] Logs WS sans kwarg `timestamp=` (bybit + binance), vérifié après restart.
- [x] Docs à jour : `skills/bybit.md`, `skills/database.md`, `skills/binance_import.md`, `skills/deployment.md`,
      `PROJECT_CONTEXT.md`, `ROADMAP.md`, `docs/CODE_MAP.md`, `results/INDEX.md`.

## 9. Clôture — à faire par Bruno (spec §6)

1. Review du diff (scheduler surtout), merge de `feat/b3-bybit-data` dans `dev`, push.
2. Serveur : `cd ~/apps/kraken-trading-bot && git checkout dev && git pull --ff-only origin dev && sudo systemctl
   restart krakenbot-collector` (le serveur est actuellement sur la branche de feature, collector déjà à jour).
3. Observer le premier run cron du 12/09 03:30 UTC (commandes § 5bis).
4. Tag `v2.5.0-b3-bybit-data`, push du tag. B4 s'ouvre par la dette 11.
