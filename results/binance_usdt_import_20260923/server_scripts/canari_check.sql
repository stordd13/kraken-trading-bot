-- vérification du canari (lecture seule) : attendu 31 rows, pair exact, 2021-01-02T00:00Z -> 2021-02-01T00:00Z
SELECT pair, interval, count(*), min(timestamp), max(timestamp) FROM market_data_ohlc WHERE exchange='binance' AND pair='BTC/USDT' GROUP BY 1,2;
