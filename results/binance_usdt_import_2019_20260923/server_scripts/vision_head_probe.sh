#!/bin/bash
# vision_head_probe.sh — sondes HEAD Binance Vision (lecture seule, aucune écriture en base) : 3 symboles × 6 TF × 24 mois (2019-01 → 2020-12) = 432 URLs.
# Serveur Hetzner. Sortie : "<code> <url>" par ligne, triée. Établit le compte exact des file_not_found attendus avant l'import.
set -o pipefail
for sym in BTCUSDT ETHUSDT SOLUSDT; do for tf in 5m 15m 1h 4h 1d 1w; do for y in 2019 2020; do for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  echo "https://data.binance.vision/data/spot/monthly/klines/$sym/$tf/$sym-$tf-$y-$m.zip"
done; done; done; done | xargs -P 6 -I{} sh -c 'printf "%s %s\n" "$(curl -sI -o /dev/null --max-time 60 -w %{http_code} "{}")" "{}"' | sort -k2
