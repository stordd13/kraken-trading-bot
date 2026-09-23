-- collector Bybit après import (lecture seule) : dernière bougie 1m < 3 min ; 0 trou 1m par paire sur la fenêtre de l'import
-- :t0 / :t1 = début / fin de l'import (UTC), substitués par sed avant exécution
SELECT pair, max(timestamp) AS last_1m, now() - max(timestamp) AS age FROM market_data_ohlc WHERE exchange='bybit' AND interval=1 GROUP BY 1 ORDER BY 1;
WITH s AS (
  SELECT pair, timestamp, LAG(timestamp) OVER (PARTITION BY pair ORDER BY timestamp) AS prev
  FROM market_data_ohlc WHERE exchange='bybit' AND interval=1 AND timestamp >= ':t0' AND timestamp <= ':t1'
)
SELECT pair, count(*) AS rows_in_window, count(*) FILTER (WHERE timestamp - prev > interval '1 minute') AS holes_gt_1m FROM s GROUP BY 1 ORDER BY 1;
