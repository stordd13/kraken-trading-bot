# Reconstruction 1 w USDT — contrôle (étape 1, lecture seule)

> **Probe Vision (d) : aucune des 24 bougies cibles n'est servie** par les 33 fichiers mensuels lus (33 demandés).

**Contrôle : VERT** — cibles reconstructibles 24/24, **0 mismatch OHLCV** sur 810 semaines Vision comparées.

- Généré : `2026-09-24T15:12:01.289375+00:00` · commande : `scripts/audit/reconstruct_1w.py check --output results/reconstruction_1w_2022_2025/check_report.json --markdown results/reconstruction_1w_2022_2025/check_report.md`
- git `35b06ce03ce180d9769ae4731b13d82085af6876` (branche `feat/c3b-reconstruction-1w`), tree suivi propre : True · `scripts/audit/reconstruct_1w.py` sha256 `1a96b958e3ce9bd4be7ef44a593ed6474a4f10cbd9f316afe2b5af985e81a24b`
- Base : `localhost:5433/krakenbot` · transaction_read_only = `on` · table `ohlc_derived` présente : False
- Périmètre : `exchange='binance'`, BTC/USDT, ETH/USDT, SOL/USDT, fenêtre `(2021-03-01T00:00:00+00:00, 2026-06-29T00:00:00+00:00]`, ancrage `T = 2024-11-22T04:48:00+00:00` (recalculé par `cc.anchor_of`), méthode `agg_1d_v1`
- Artefact : `check_report.json` sha256 `f41b45f16ad880c5e641fc586ec4b479d37cc595a1e94b21f1029d5ddd310108`

## (a) Diagnostic 1 w

| Paire | présentes / attendues | manquantes = brief | hors grille | périodes préfixe | périodes évaluées | D1 1 w préfixe | trou max | couverture évaluée |
|---|---|---|---|---|---|---|---|---|
| BTC/USDT | 270/278 | oui (8) | 0 | 194 | 84 | 188/194 = 96.9 % → échoue | 7 j (≤ 31) | 82/84 |
| ETH/USDT | 270/278 | oui (8) | 0 | 194 | 84 | 188/194 = 96.9 % → échoue | 7 j (≤ 31) | 82/84 |
| SOL/USDT | 270/278 | oui (8) | 0 | 194 | 84 | 188/194 = 96.9 % → échoue | 7 j (≤ 31) | 82/84 |

Estampilles manquantes mesurées (BTC/USDT) : `2022-06-06`, `2022-07-04`, `2022-09-05`, `2022-10-03`, `2022-11-07`, `2022-12-05`, `2025-02-03`, `2025-03-03`

## (b) Disponibilité 1 d des 24 cibles

| Paire | Semaine | 1 d présentes | reconstructible | open | high | low | close | volume | trades | source_sha256 |
|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USDT | 2022-06-06 | 7/7 | oui | 29468.10000000 | 32399.00000000 | 29282.36000000 | 29919.21000000 | 422401.40352000 | 7249030 | `f37e1f8c53214f27…` |
| BTC/USDT | 2022-07-04 | 7/7 | oui | 21038.08000000 | 21539.85000000 | 18626.00000000 | 19315.83000000 | 508544.13970000 | 8098167 | `b4c927dcf3a6d5e0…` |
| BTC/USDT | 2022-09-05 | 7/7 | oui | 19555.61000000 | 20576.25000000 | 19540.00000000 | 20000.30000000 | 1527594.84529000 | 38080138 | `651fdae82f0e5ea6…` |
| BTC/USDT | 2022-10-03 | 7/7 | oui | 18809.13000000 | 20385.86000000 | 18471.28000000 | 19056.80000000 | 2777070.91238000 | 39023576 | `6e85d88381dd8c04…` |
| BTC/USDT | 2022-11-07 | 7/7 | oui | 20627.48000000 | 21480.65000000 | 20031.24000000 | 20905.58000000 | 2205754.83045000 | 47012044 | `1220a890dc0f55a9…` |
| BTC/USDT | 2022-12-05 | 7/7 | oui | 16428.77000000 | 17324.00000000 | 15995.27000000 | 17105.70000000 | 1572173.55626000 | 33957294 | `115aaab6a831d965…` |
| BTC/USDT | 2025-02-03 | 7/7 | oui | 102620.01000000 | 106457.44000000 | 96150.00000000 | 97700.59000000 | 184203.26328000 | 38100357 | `28247f55e6815045…` |
| BTC/USDT | 2025-03-03 | 7/7 | oui | 96258.00000000 | 96500.00000000 | 78258.52000000 | 94270.00000000 | 373604.39736000 | 52557578 | `babab334ec52e771…` |
| ETH/USDT | 2022-06-06 | 7/7 | oui | 1813.64000000 | 2016.45000000 | 1737.00000000 | 1806.23000000 | 4894188.42940000 | 5019674 | `30e77723c9788d30…` |
| ETH/USDT | 2022-07-04 | 7/7 | oui | 1197.79000000 | 1238.93000000 | 998.00000000 | 1074.26000000 | 7610801.14680000 | 6463507 | `38b6d193ac72bf03…` |
| ETH/USDT | 2022-09-05 | 7/7 | oui | 1426.76000000 | 1650.00000000 | 1422.08000000 | 1579.28000000 | 5044263.25510000 | 7303513 | `cae400030b1e122b…` |
| ETH/USDT | 2022-10-03 | 7/7 | oui | 1294.62000000 | 1400.00000000 | 1253.20000000 | 1276.72000000 | 4714233.48760000 | 5752095 | `eed4d2a11775ce1d…` |
| ETH/USDT | 2022-11-07 | 7/7 | oui | 1590.45000000 | 1680.00000000 | 1502.32000000 | 1568.29000000 | 4581252.75080000 | 5675381 | `503b08dbc90def61…` |
| ETH/USDT | 2022-12-05 | 7/7 | oui | 1193.88000000 | 1309.77000000 | 1151.02000000 | 1279.41000000 | 3279474.59660000 | 4710731 | `3142d762f15bbf2b…` |
| ETH/USDT | 2025-02-03 | 7/7 | oui | 3232.61000000 | 3437.31000000 | 2750.71000000 | 2869.68000000 | 3917894.04870000 | 26191788 | `20339266cbc1657b…` |
| ETH/USDT | 2025-03-03 | 7/7 | oui | 2819.70000000 | 2839.95000000 | 2076.26000000 | 2518.11000000 | 6704218.92400000 | 34415210 | `5eeb540db97a0e99…` |
| SOL/USDT | 2022-06-06 | 7/7 | oui | 44.98000000 | 48.39000000 | 35.71000000 | 38.52000000 | 31680429.89000000 | 2209771 | `d82b5b8b76c27c8b…` |
| SOL/USDT | 2022-07-04 | 7/7 | oui | 39.39000000 | 41.25000000 | 30.92000000 | 33.39000000 | 32137486.49000000 | 2064570 | `df7003e9b0ed8d2f…` |
| SOL/USDT | 2022-09-05 | 7/7 | oui | 30.43000000 | 33.16000000 | 30.00000000 | 32.16000000 | 16639278.09000000 | 1074135 | `ba491e5483a7f21c…` |
| SOL/USDT | 2022-10-03 | 7/7 | oui | 32.33000000 | 35.41000000 | 31.65000000 | 32.06000000 | 20717720.17000000 | 1237324 | `a00f24cd4b22bbf1…` |
| SOL/USDT | 2022-11-07 | 7/7 | oui | 32.93000000 | 38.79000000 | 30.24000000 | 32.62000000 | 27119839.35000000 | 1806932 | `89598089bf868ca9…` |
| SOL/USDT | 2022-12-05 | 7/7 | oui | 14.11000000 | 14.32000000 | 12.78000000 | 13.71000000 | 20094104.49000000 | 775159 | `0034857c08909b75…` |
| SOL/USDT | 2025-02-03 | 7/7 | oui | 240.49000000 | 244.70000000 | 192.31000000 | 203.51000000 | 32632945.29000000 | 25323947 | `7972ada504d09bfd…` |
| SOL/USDT | 2025-03-03 | 7/7 | oui | 167.94000000 | 179.85000000 | 125.55000000 | 178.71000000 | 57102095.79500000 | 28665318 | `4ae87eafaf771fdf…` |

## (c) Contrôle d'exactitude — toutes les semaines Vision présentes de la fenêtre

| Paire | semaines comparées | non contrôlables | mismatches OHLCV | trades_count comparées | mismatches trades_count | vwap stocké non NULL | vwap reconstruit non NULL | écart vwap max |
|---|---|---|---|---|---|---|---|---|
| BTC/USDT | 270 | 0 | **0** | 270 | 0 | 0 | 0 | — |
| ETH/USDT | 270 | 0 | **0** | 270 | 0 | 0 | 0 | — |
| SOL/USDT | 270 | 0 | **0** | 270 | 0 | 0 | 0 | — |

### vwap

Population de la colonne sur `exchange='binance'`, 1 d et 1 w, tout l'historique :

| Paire | TF | rows | vwap non NULL | trades_count non NULL |
|---|---|---|---|---|
| BTC/USDC | 1 d | 1753 | 0 | 1753 |
| BTC/USDC | 1 w | 246 | 0 | 246 |
| BTC/USDT | 1 d | 2800 | 0 | 2800 |
| BTC/USDT | 1 w | 383 | 0 | 383 |
| ETH/USDC | 1 d | 1753 | 0 | 1753 |
| ETH/USDC | 1 w | 246 | 0 | 246 |
| ETH/USDT | 1 d | 2800 | 0 | 2800 |
| ETH/USDT | 1 w | 383 | 0 | 383 |
| SOL/USDC | 1 d | 1196 | 0 | 1196 |
| SOL/USDC | 1 w | 168 | 0 | 168 |
| SOL/USDT | 1 d | 2212 | 0 | 2212 |
| SOL/USDT | 1 w | 300 | 0 | 300 |

Occurrences du jeton `vwap` sur le chemin backtest / C3 (8) — chemins balayés : `scripts/backtest.py`, `scripts/run_p6_backtests.py`, `scripts/run_p6_walkforward.py`, `scripts/run_p7_grid_search.py`, `scripts/p7_grids.py`, `scripts/compute_benchmarks.py`, `scripts/audit/c3_*.py`, `src/krakenbot/backtesting`, `src/krakenbot/backtest_metrics.py`, `src/krakenbot/replay_contract.py`, `src/krakenbot/strategies`, `src/krakenbot/indicators` ; absents : `src/krakenbot/backtesting`

- `src/krakenbot/indicators/__init__.py:22` — `from krakenbot.indicators.vwap import VWAPIndicator`
- `src/krakenbot/indicators/multi_timeframe.py:36` — `from krakenbot.indicators.vwap import VWAPIndicator`
- `src/krakenbot/indicators/multi_timeframe.py:230` — `"vwap": {},  # Lazy - created on first get_vwap() call`
- `src/krakenbot/indicators/multi_timeframe.py:378` — `for indicator in tf_ind.get("vwap", {}).values():`
- `src/krakenbot/indicators/multi_timeframe.py:740` — `vwap_dict = tf_ind.setdefault("vwap", {})`
- `src/krakenbot/indicators/multi_timeframe.py:868` — `vwap = self.get_vwap(20, tf)`
- `src/krakenbot/indicators/multi_timeframe.py:869` — `if vwap is not None and close is not None and close > _ZERO:`
- `src/krakenbot/indicators/multi_timeframe.py:870` — `features["vwap_deviation"] = float((close - vwap) / close)`

**Proposition (non décidée) : `vwap_policy = "null"`** — la colonne vwap n'est peuplée sur aucune row 1 d des séries USDT : la formule pondérée n'a pas d'entrée, seule la politique null est calculable (vwap non NULL : 0 rows 1 d, 0 rows 1 w sur les séries USDT).

## (d) Probe Vision — fichiers mensuels 1 w des cibles

| Paire | Semaine | Fichier | HTTP | Last-Modified | bougies servies | contient S |
|---|---|---|---|---|---|---|
| BTC/USDT | 2022-06-06 | `BTCUSDT-1w-2022-05.zip` | 200 | Thu, 02 Jun 2022 05:14:06 GMT | 4 | non |
| BTC/USDT | 2022-06-06 | `BTCUSDT-1w-2022-06.zip` | 200 | Fri, 01 Jul 2022 04:34:47 GMT | 3 | non |
| BTC/USDT | 2022-07-04 | `BTCUSDT-1w-2022-06.zip` | 200 | Fri, 01 Jul 2022 04:34:47 GMT | 3 | non |
| BTC/USDT | 2022-07-04 | `BTCUSDT-1w-2022-07.zip` | 200 | Mon, 01 Aug 2022 08:59:16 GMT | 4 | non |
| BTC/USDT | 2022-09-05 | `BTCUSDT-1w-2022-08.zip` | 200 | Thu, 01 Sep 2022 05:35:08 GMT | 4 | non |
| BTC/USDT | 2022-09-05 | `BTCUSDT-1w-2022-09.zip` | 200 | Mon, 03 Oct 2022 05:42:35 GMT | 3 | non |
| BTC/USDT | 2022-10-03 | `BTCUSDT-1w-2022-09.zip` | 200 | Mon, 03 Oct 2022 05:42:35 GMT | 3 | non |
| BTC/USDT | 2022-10-03 | `BTCUSDT-1w-2022-10.zip` | 200 | Thu, 03 Nov 2022 13:56:04 GMT | 4 | non |
| BTC/USDT | 2022-11-07 | `BTCUSDT-1w-2022-10.zip` | 200 | Thu, 03 Nov 2022 13:56:04 GMT | 4 | non |
| BTC/USDT | 2022-11-07 | `BTCUSDT-1w-2022-11.zip` | 200 | Fri, 02 Dec 2022 09:21:31 GMT | 3 | non |
| BTC/USDT | 2022-12-05 | `BTCUSDT-1w-2022-11.zip` | 200 | Fri, 02 Dec 2022 09:21:31 GMT | 3 | non |
| BTC/USDT | 2022-12-05 | `BTCUSDT-1w-2022-12.zip` | 200 | Wed, 04 Jan 2023 04:45:49 GMT | 4 | non |
| BTC/USDT | 2025-02-03 | `BTCUSDT-1w-2025-01.zip` | 200 | Tue, 04 Mar 2025 10:35:11 GMT | 3 | non |
| BTC/USDT | 2025-02-03 | `BTCUSDT-1w-2025-02.zip` | 200 | Tue, 04 Mar 2025 10:35:12 GMT | 3 | non |
| BTC/USDT | 2025-03-03 | `BTCUSDT-1w-2025-02.zip` | 200 | Tue, 04 Mar 2025 10:35:12 GMT | 3 | non |
| BTC/USDT | 2025-03-03 | `BTCUSDT-1w-2025-03.zip` | 200 | Wed, 08 Oct 2025 11:53:22 GMT | 5 | non |
| ETH/USDT | 2022-06-06 | `ETHUSDT-1w-2022-05.zip` | 200 | Thu, 02 Jun 2022 05:14:09 GMT | 4 | non |
| ETH/USDT | 2022-06-06 | `ETHUSDT-1w-2022-06.zip` | 200 | Fri, 01 Jul 2022 04:34:49 GMT | 3 | non |
| ETH/USDT | 2022-07-04 | `ETHUSDT-1w-2022-06.zip` | 200 | Fri, 01 Jul 2022 04:34:49 GMT | 3 | non |
| ETH/USDT | 2022-07-04 | `ETHUSDT-1w-2022-07.zip` | 200 | Mon, 01 Aug 2022 08:59:20 GMT | 4 | non |
| ETH/USDT | 2022-09-05 | `ETHUSDT-1w-2022-08.zip` | 200 | Thu, 01 Sep 2022 05:35:11 GMT | 4 | non |
| ETH/USDT | 2022-09-05 | `ETHUSDT-1w-2022-09.zip` | 200 | Mon, 03 Oct 2022 06:02:11 GMT | 3 | non |
| ETH/USDT | 2022-10-03 | `ETHUSDT-1w-2022-09.zip` | 200 | Mon, 03 Oct 2022 06:02:11 GMT | 3 | non |
| ETH/USDT | 2022-10-03 | `ETHUSDT-1w-2022-10.zip` | 200 | Thu, 03 Nov 2022 20:50:02 GMT | 4 | non |
| ETH/USDT | 2022-11-07 | `ETHUSDT-1w-2022-10.zip` | 200 | Thu, 03 Nov 2022 20:50:02 GMT | 4 | non |
| ETH/USDT | 2022-11-07 | `ETHUSDT-1w-2022-11.zip` | 200 | Fri, 02 Dec 2022 09:42:50 GMT | 3 | non |
| ETH/USDT | 2022-12-05 | `ETHUSDT-1w-2022-11.zip` | 200 | Fri, 02 Dec 2022 09:42:50 GMT | 3 | non |
| ETH/USDT | 2022-12-05 | `ETHUSDT-1w-2022-12.zip` | 200 | Wed, 04 Jan 2023 05:08:00 GMT | 4 | non |
| ETH/USDT | 2025-02-03 | `ETHUSDT-1w-2025-01.zip` | 200 | Tue, 04 Mar 2025 10:58:50 GMT | 3 | non |
| ETH/USDT | 2025-02-03 | `ETHUSDT-1w-2025-02.zip` | 200 | Tue, 04 Mar 2025 10:58:50 GMT | 3 | non |
| ETH/USDT | 2025-03-03 | `ETHUSDT-1w-2025-02.zip` | 200 | Tue, 04 Mar 2025 10:58:50 GMT | 3 | non |
| ETH/USDT | 2025-03-03 | `ETHUSDT-1w-2025-03.zip` | 200 | Wed, 08 Oct 2025 12:02:32 GMT | 5 | non |
| SOL/USDT | 2022-06-06 | `SOLUSDT-1w-2022-05.zip` | 200 | Thu, 02 Jun 2022 05:30:15 GMT | 4 | non |
| SOL/USDT | 2022-06-06 | `SOLUSDT-1w-2022-06.zip` | 200 | Fri, 01 Jul 2022 04:48:49 GMT | 3 | non |
| SOL/USDT | 2022-07-04 | `SOLUSDT-1w-2022-06.zip` | 200 | Fri, 01 Jul 2022 04:48:49 GMT | 3 | non |
| SOL/USDT | 2022-07-04 | `SOLUSDT-1w-2022-07.zip` | 200 | Mon, 01 Aug 2022 09:17:23 GMT | 4 | non |
| SOL/USDT | 2022-09-05 | `SOLUSDT-1w-2022-08.zip` | 200 | Thu, 01 Sep 2022 05:52:56 GMT | 4 | non |
| SOL/USDT | 2022-09-05 | `SOLUSDT-1w-2022-09.zip` | 200 | Mon, 03 Oct 2022 05:22:57 GMT | 3 | non |
| SOL/USDT | 2022-10-03 | `SOLUSDT-1w-2022-09.zip` | 200 | Mon, 03 Oct 2022 05:22:57 GMT | 3 | non |
| SOL/USDT | 2022-10-03 | `SOLUSDT-1w-2022-10.zip` | 200 | Thu, 03 Nov 2022 06:45:26 GMT | 4 | non |
| SOL/USDT | 2022-11-07 | `SOLUSDT-1w-2022-10.zip` | 200 | Thu, 03 Nov 2022 06:45:26 GMT | 4 | non |
| SOL/USDT | 2022-11-07 | `SOLUSDT-1w-2022-11.zip` | 200 | Fri, 02 Dec 2022 08:52:59 GMT | 3 | non |
| SOL/USDT | 2022-12-05 | `SOLUSDT-1w-2022-11.zip` | 200 | Fri, 02 Dec 2022 08:52:59 GMT | 3 | non |
| SOL/USDT | 2022-12-05 | `SOLUSDT-1w-2022-12.zip` | 200 | Wed, 04 Jan 2023 04:20:13 GMT | 4 | non |
| SOL/USDT | 2025-02-03 | `SOLUSDT-1w-2025-01.zip` | 200 | Tue, 04 Mar 2025 10:10:52 GMT | 3 | non |
| SOL/USDT | 2025-02-03 | `SOLUSDT-1w-2025-02.zip` | 200 | Tue, 04 Mar 2025 10:10:52 GMT | 3 | non |
| SOL/USDT | 2025-03-03 | `SOLUSDT-1w-2025-02.zip` | 200 | Tue, 04 Mar 2025 10:10:52 GMT | 3 | non |
| SOL/USDT | 2025-03-03 | `SOLUSDT-1w-2025-03.zip` | 200 | Wed, 08 Oct 2025 11:44:14 GMT | 5 | non |

Cibles absentes des deux fichiers (mois d'ouverture et mois de clôture) : **24/24**.
Semaines à cheval **servies** par ces fichiers : `BTCUSDT-1w-2022-12.zip` → `2023-01-02` ; `BTCUSDT-1w-2025-03.zip` → `2025-04-07` ; `ETHUSDT-1w-2022-12.zip` → `2023-01-02` ; `ETHUSDT-1w-2025-03.zip` → `2025-04-07` ; `SOLUSDT-1w-2022-12.zip` → `2023-01-02` ; `SOLUSDT-1w-2025-03.zip` → `2025-04-07`.

## (e) Idempotence de l'import Vision

`scripts/binance_vision_import.py` (sha256 `63575e0f36d65bfc02fd8b4d1a53a3ebc5fe070d342b36c29cda554550db0514`), lignes de la clause de conflit :

- `:200` — `stmt = stmt.on_conflict_do_nothing(`
- `:201` — `index_elements=["timestamp", "pair", "interval", "exchange"]`

Conséquence : une reprise de l'import (`ON CONFLICT DO NOTHING` sur la PK `(timestamp, pair, interval, exchange)`) **n'écrase jamais** une row dérivée : une vraie row Vision servie plus tard pour une des 8 estampilles serait ignorée en silence. La remplacer exige une action explicite : `DELETE` de la row OHLC **et** de sa row de provenance `ohlc_derived`, puis réimport. La reprise prévue (1 w 2026-07/08) est hors de la fenêtre des cibles.

## TimescaleDB — chunks des cibles

Compression activée sur `market_data_ohlc` : `False`.

| Semaine | chunk | intervalle | compressé |
|---|---|---|---|
| 2022-06-06 | `_hyper_2_3280_chunk` | 2022-05-28 → 2022-06-27 | False |
| 2022-07-04 | `_hyper_2_3281_chunk` | 2022-06-27 → 2022-07-27 | False |
| 2022-09-05 | `_hyper_2_3283_chunk` | 2022-08-26 → 2022-09-25 | False |
| 2022-10-03 | `_hyper_2_3284_chunk` | 2022-09-25 → 2022-10-25 | False |
| 2022-11-07 | `_hyper_2_3285_chunk` | 2022-10-25 → 2022-11-24 | False |
| 2022-12-05 | `_hyper_2_3286_chunk` | 2022-11-24 → 2022-12-24 | False |
| 2025-02-03 | `_hyper_2_3312_chunk` | 2025-01-12 → 2025-02-11 | False |
| 2025-03-03 | `_hyper_2_3254_chunk` | 2025-02-11 → 2025-03-13 | False |
