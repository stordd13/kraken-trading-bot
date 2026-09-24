# Reconstruction 1 w USDT — écriture (étape 2)

**ÉCRIT ET VÉRIFIÉ** — 24 rows `market_data_ohlc` + 24 rows `ohlc_derived`, `vwap_policy = "null"`.

- Généré : `2026-09-24T15:47:20.274794+00:00` · commande : `scripts/audit/reconstruct_1w.py write --vwap-policy null --note docs/RESEARCH_LOG.md — entrée 13 (reconstruction des 8 estampilles 1 w USDT, inscrite le 24/09/2026 avant l'écriture, commit 4866c7d) --output results/reconstruction_1w_2022_2025/write_report.json --markdown results/reconstruction_1w_2022_2025/write_report.md`
- git `4866c7d39ed4c6d7f279aa2a6ef4cf8e5bd8e8f7` (branche `feat/c3b-reconstruction-1w`), tree suivi propre : True · `scripts/audit/reconstruct_1w.py` sha256 `d25e230cf5fe321396ba2daa245461fcce687551526096ed8ad21f732aac966c`
- Base : `localhost:5433/krakenbot` · note : « docs/RESEARCH_LOG.md — entrée 13 (reconstruction des 8 estampilles 1 w USDT, inscrite le 24/09/2026 avant l'écriture, commit 4866c7d) » · created_at `2026-09-24T15:47:20.274794+00:00`
- Artefact : `write_report.json` sha256 `b0f1acecda841091790af0a81b90b2a054812dd01cab27c00a893903fb04e743`

## Contrôle (c) rejoué dans la transaction, avant les INSERT

| Paire | semaines comparées | mismatches OHLCV | mismatches trades_count | non contrôlables |
|---|---|---|---|---|
| BTC/USDT | 270 | **0** | 0 | 0 |
| ETH/USDT | 270 | **0** | 0 | 0 |
| SOL/USDT | 270 | **0** | 0 | 0 |

## Couverture 1 w, avant / après (relue sur une connexion neuve)

| Paire | D1 préfixe avant | D1 préfixe après | évaluée avant | évaluée après | manquantes après | semaines contrôlées après | mismatches OHLCV après |
|---|---|---|---|---|---|---|---|
| BTC/USDT | 188/194 (échoue) | 194/194 (passe) | 82/84 | 84/84 | 0 | 278 | 0 |
| ETH/USDT | 188/194 (échoue) | 194/194 (passe) | 82/84 | 84/84 | 0 | 278 | 0 |
| SOL/USDT | 188/194 (échoue) | 194/194 (passe) | 82/84 | 84/84 | 0 | 278 | 0 |

## Les 24 rows dérivées, relues (`SELECT count(*) FROM ohlc_derived` = 24)

| Paire | Semaine | open | high | low | close | volume | trades | vwap | source_sha256 | sha rejoué | = agrégat rejoué |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC/USDT | 2022-06-06 | 29468.10000000 | 32399.00000000 | 29282.36000000 | 29919.21000000 | 422401.40352000 | 7249030 | NULL | `f37e1f8c53214f27…` | oui | oui |
| BTC/USDT | 2022-07-04 | 21038.08000000 | 21539.85000000 | 18626.00000000 | 19315.83000000 | 508544.13970000 | 8098167 | NULL | `b4c927dcf3a6d5e0…` | oui | oui |
| BTC/USDT | 2022-09-05 | 19555.61000000 | 20576.25000000 | 19540.00000000 | 20000.30000000 | 1527594.84529000 | 38080138 | NULL | `651fdae82f0e5ea6…` | oui | oui |
| BTC/USDT | 2022-10-03 | 18809.13000000 | 20385.86000000 | 18471.28000000 | 19056.80000000 | 2777070.91238000 | 39023576 | NULL | `6e85d88381dd8c04…` | oui | oui |
| BTC/USDT | 2022-11-07 | 20627.48000000 | 21480.65000000 | 20031.24000000 | 20905.58000000 | 2205754.83045000 | 47012044 | NULL | `1220a890dc0f55a9…` | oui | oui |
| BTC/USDT | 2022-12-05 | 16428.77000000 | 17324.00000000 | 15995.27000000 | 17105.70000000 | 1572173.55626000 | 33957294 | NULL | `115aaab6a831d965…` | oui | oui |
| BTC/USDT | 2025-02-03 | 102620.01000000 | 106457.44000000 | 96150.00000000 | 97700.59000000 | 184203.26328000 | 38100357 | NULL | `28247f55e6815045…` | oui | oui |
| BTC/USDT | 2025-03-03 | 96258.00000000 | 96500.00000000 | 78258.52000000 | 94270.00000000 | 373604.39736000 | 52557578 | NULL | `babab334ec52e771…` | oui | oui |
| ETH/USDT | 2022-06-06 | 1813.64000000 | 2016.45000000 | 1737.00000000 | 1806.23000000 | 4894188.42940000 | 5019674 | NULL | `30e77723c9788d30…` | oui | oui |
| ETH/USDT | 2022-07-04 | 1197.79000000 | 1238.93000000 | 998.00000000 | 1074.26000000 | 7610801.14680000 | 6463507 | NULL | `38b6d193ac72bf03…` | oui | oui |
| ETH/USDT | 2022-09-05 | 1426.76000000 | 1650.00000000 | 1422.08000000 | 1579.28000000 | 5044263.25510000 | 7303513 | NULL | `cae400030b1e122b…` | oui | oui |
| ETH/USDT | 2022-10-03 | 1294.62000000 | 1400.00000000 | 1253.20000000 | 1276.72000000 | 4714233.48760000 | 5752095 | NULL | `eed4d2a11775ce1d…` | oui | oui |
| ETH/USDT | 2022-11-07 | 1590.45000000 | 1680.00000000 | 1502.32000000 | 1568.29000000 | 4581252.75080000 | 5675381 | NULL | `503b08dbc90def61…` | oui | oui |
| ETH/USDT | 2022-12-05 | 1193.88000000 | 1309.77000000 | 1151.02000000 | 1279.41000000 | 3279474.59660000 | 4710731 | NULL | `3142d762f15bbf2b…` | oui | oui |
| ETH/USDT | 2025-02-03 | 3232.61000000 | 3437.31000000 | 2750.71000000 | 2869.68000000 | 3917894.04870000 | 26191788 | NULL | `20339266cbc1657b…` | oui | oui |
| ETH/USDT | 2025-03-03 | 2819.70000000 | 2839.95000000 | 2076.26000000 | 2518.11000000 | 6704218.92400000 | 34415210 | NULL | `5eeb540db97a0e99…` | oui | oui |
| SOL/USDT | 2022-06-06 | 44.98000000 | 48.39000000 | 35.71000000 | 38.52000000 | 31680429.89000000 | 2209771 | NULL | `d82b5b8b76c27c8b…` | oui | oui |
| SOL/USDT | 2022-07-04 | 39.39000000 | 41.25000000 | 30.92000000 | 33.39000000 | 32137486.49000000 | 2064570 | NULL | `df7003e9b0ed8d2f…` | oui | oui |
| SOL/USDT | 2022-09-05 | 30.43000000 | 33.16000000 | 30.00000000 | 32.16000000 | 16639278.09000000 | 1074135 | NULL | `ba491e5483a7f21c…` | oui | oui |
| SOL/USDT | 2022-10-03 | 32.33000000 | 35.41000000 | 31.65000000 | 32.06000000 | 20717720.17000000 | 1237324 | NULL | `a00f24cd4b22bbf1…` | oui | oui |
| SOL/USDT | 2022-11-07 | 32.93000000 | 38.79000000 | 30.24000000 | 32.62000000 | 27119839.35000000 | 1806932 | NULL | `89598089bf868ca9…` | oui | oui |
| SOL/USDT | 2022-12-05 | 14.11000000 | 14.32000000 | 12.78000000 | 13.71000000 | 20094104.49000000 | 775159 | NULL | `0034857c08909b75…` | oui | oui |
| SOL/USDT | 2025-02-03 | 240.49000000 | 244.70000000 | 192.31000000 | 203.51000000 | 32632945.29000000 | 25323947 | NULL | `7972ada504d09bfd…` | oui | oui |
| SOL/USDT | 2025-03-03 | 167.94000000 | 179.85000000 | 125.55000000 | 178.71000000 | 57102095.79500000 | 28665318 | NULL | `4ae87eafaf771fdf…` | oui | oui |

Provenance commune : `method = agg_1d_v1`, `source_interval = 1440`, `vwap_policy = null`, `git_sha = 4866c7d39ed4c6d7f279aa2a6ef4cf8e5bd8e8f7`, `script_sha256 = d25e230cf5fe321396ba2daa245461fcce687551526096ed8ad21f732aac966c`.

## Retour arrière (non exécuté)

```sql
BEGIN;
DELETE FROM market_data_ohlc o USING ohlc_derived d
 WHERE o.timestamp = d.timestamp AND o.pair = d.pair AND o.interval = d.interval
   AND o.exchange = d.exchange AND d.method = 'agg_1d_v1';
DELETE FROM ohlc_derived WHERE method = 'agg_1d_v1';
COMMIT;
-- puis, si la table doit disparaître : alembic downgrade c1ae7a1c0001
```
