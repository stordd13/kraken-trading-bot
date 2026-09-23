-- state_before / state_after (lecture seule) — chantier USDT 2019-2020 (chore/data-binance-usdt-2019)
-- 1. les 39 séries binance : count / min / max
SELECT pair, interval, count(*), min(timestamp), max(timestamp) FROM market_data_ohlc WHERE exchange='binance' GROUP BY 1,2 ORDER BY 1,2;
-- 2. les 18 séries */USDT restreintes aux rows du 23/09 (doivent être intactes : count, min, max, sum(close), sum(volume) identiques avant/après)
--    restriction : timestamp > 2021-01-01T00:00Z (5m,15m,1h,4h,1d) ; > 2021-01-04T00:00Z (1w : le fichier 2020-12 apporte légitimement le stamp 2021-01-04)
SELECT pair, interval, count(*), min(timestamp), max(timestamp), sum(close) AS sum_close, sum(volume) AS sum_volume
FROM market_data_ohlc WHERE exchange='binance' AND pair LIKE '%/USDT'
  AND timestamp > CASE WHEN interval=10080 THEN '2021-01-04 00:00:00+00'::timestamptz ELSE '2021-01-01 00:00:00+00'::timestamptz END
GROUP BY 1,2 ORDER BY 1,2;
-- 3. rows */USDT à la jointure ou avant (<= 2021-01-04T00:00Z) : attendu 0 avant l'import ; après : les rows 2019-2020 + stamps de jointure
SELECT pair, interval, count(*), min(timestamp), max(timestamp) FROM market_data_ohlc WHERE exchange='binance' AND pair LIKE '%/USDT' AND timestamp <= '2021-01-04 00:00:00+00' GROUP BY 1,2 ORDER BY 1,2;
-- 4. rows par exchange
SELECT exchange, count(*) FROM market_data_ohlc GROUP BY 1 ORDER BY 1;
-- 5. rows */USDT hors binance (attendu : aucune)
SELECT exchange, pair, interval, count(*) FROM market_data_ohlc WHERE pair LIKE '%/USDT' AND exchange <> 'binance' GROUP BY 1,2,3 ORDER BY 1,2,3;
-- 6. taille hypertable
SELECT pg_size_pretty(hypertable_size('market_data_ohlc')) AS hypertable_size,
       (SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name='market_data_ohlc') AS chunks,
       (SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name='market_data_ohlc' AND is_compressed) AS compressed_chunks;
