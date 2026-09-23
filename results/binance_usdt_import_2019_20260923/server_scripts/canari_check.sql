-- vérification du canari (lecture seule) : attendu 31 rows BTC/USDT 1440 stampées <= 2019-02-01, 2019-01-02T00:00Z -> 2019-02-01T00:00Z
SELECT pair, interval, count(*), min(timestamp), max(timestamp) FROM market_data_ohlc WHERE exchange='binance' AND pair='BTC/USDT' AND interval=1440 AND timestamp <= '2019-02-01 00:00:00+00' GROUP BY 1,2;
-- série BTC/USDT 1d entière : attendu 2 100 rows (2 069 du 23/09 + 31), min 2019-01-02, max 2026-09-01
SELECT pair, interval, count(*), min(timestamp), max(timestamp) FROM market_data_ohlc WHERE exchange='binance' AND pair='BTC/USDT' AND interval=1440 GROUP BY 1,2;
-- premières / dernières rows du canari
(SELECT timestamp, open, high, low, close, volume, trades_count, vwap FROM market_data_ohlc WHERE exchange='binance' AND pair='BTC/USDT' AND interval=1440 AND timestamp <= '2019-02-01 00:00:00+00' ORDER BY timestamp LIMIT 3)
UNION ALL
(SELECT * FROM (SELECT timestamp, open, high, low, close, volume, trades_count, vwap FROM market_data_ohlc WHERE exchange='binance' AND pair='BTC/USDT' AND interval=1440 AND timestamp <= '2019-02-01 00:00:00+00' ORDER BY timestamp DESC LIMIT 3) t ORDER BY timestamp);
-- rows USDC (attendu 8712718) et rows USDT hors du canari (attendu 2575851 = inchangé)
SELECT count(*) FILTER (WHERE pair LIKE '%/USDC') AS usdc_rows, count(*) FILTER (WHERE pair LIKE '%/USDT' AND timestamp > '2021-01-01 00:00:00+00') AS usdt_rows_2021_plus FROM market_data_ohlc WHERE exchange='binance';
