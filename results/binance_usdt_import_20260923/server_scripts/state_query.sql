-- state_before / state_after (lecture seule)
SELECT pair, interval, count(*), min(timestamp), max(timestamp) FROM market_data_ohlc WHERE exchange='binance' GROUP BY 1,2 ORDER BY 1,2;
SELECT exchange, count(*) FROM market_data_ohlc GROUP BY 1 ORDER BY 1;
