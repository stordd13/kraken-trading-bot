# Skill: Données historiques Binance (base de backtest)

> Les 8.7M rows `exchange='binance'` (BTC/ETH/SOL-USDC × 7 TF, 2021-01 → 2026-06) sont la **base de
> backtest** du projet (décision B0 : prix quasi identiques à Bybit, zéro biais). Elles sont figées :
> Binance a suspendu ses services UE le 1er juillet 2026, aucune mise à jour n'est prévue. Ce skill
> documente comment elles ont été importées, pour référence et pour le futur import Bybit (B3,
> `scripts/bybit_kline_import.py`, même modèle mais REST paginé — voir `skills/bybit.md`).

## Avant tout : vérifier ce qui est en DB

Les données sont déjà là. **Ne pas relancer l'import.** Script de vérification dans
`skills/database.md` (attendu `binance: ~8,700,000`).

## Le script

```bash
poetry run python scripts/binance_vision_import.py \
    --pairs BTC/USDC,ETH/USDC,SOL/USDC \
    --intervals 1m,5m,15m,1h,4h,1d,1w \
    --start-date 2021-01-01 \
    --end-date 2026-04-01
```

### Paramètres

- `--pairs` : liste de paires séparées par des virgules
- `--intervals` : timeframes à importer
- `--start-date` / `--end-date` : période (le script télécharge mois par mois)

### Ce que fait le script

1. Pour chaque combinaison (pair, interval, mois), télécharge le ZIP depuis `data.binance.vision`
2. Parse le CSV contenu dans le ZIP
3. Insère les candles en DB par batches de 1000 rows
4. `ON CONFLICT DO NOTHING` assure l'idempotence (relancer 2 fois ne duplique pas)

## Volumes et timing attendus

| TF | Rows/mois/paire | Total 5 ans × 3 paires (estimation) |
|---|---|---|
| 1m | ~43,200 | ~7.8M |
| 5m | ~8,640 | ~1.5M |
| 15m | ~2,880 | ~520k |
| 1h | ~720 | ~130k |
| 4h | ~180 | ~32k |
| 1d | ~30 | ~5.4k |
| 1w | ~4 | ~720 |

**Réalisé : ~8.7M rows (SOL démarre en sept. 2021), 1-3 heures selon la bande passante.**

## Précautions

### Toujours lancer sur le serveur via tmux

L'import prend des heures. Si la connexion SSH coupe, le process meurt. (Historique — l'accès à
`data.binance.vision` depuis l'UE n'est plus garanti.)

```bash
ssh bruno@77.42.90.102 -p 41922
tmux new -s import
cd ~/apps/kraken-trading-bot
poetry run python scripts/binance_vision_import.py \
    --pairs BTC/USDC,ETH/USDC,SOL/USDC \
    --intervals 1m,5m,15m,1h,4h,1d,1w \
    --start-date 2021-01-01 \
    --end-date 2026-04-01
# Ctrl+B puis D pour détacher
```

### Ne JAMAIS réimporter si les données sont déjà en DB

Avant de lancer un import, vérifier ce qui existe :
```sql
SELECT pair, interval, COUNT(*), MIN(timestamp)::date, MAX(timestamp)::date
FROM market_data_ohlc WHERE exchange = 'binance'
GROUP BY pair, interval ORDER BY pair, interval;
```

Si tu vois ~8.7M rows avec couverture 2021-01 → 2026-06, l'import est déjà fait. Le script est idempotent
mais re-télécharger 1260 fichiers ZIP prend inutilement 1-3h — et n'est plus possible depuis l'UE.

### Timestamps : millisecondes vs microsecondes (leçon apprise dans la douleur)

Les fichiers Binance Vision utilisent :
- **Millisecondes** (13 chiffres, ex: `1704067200000`) pour les anciens fichiers
- **Microsecondes** (16 chiffres, ex: `1704067200000000`) pour les fichiers 2025+

Le script gère les deux automatiquement via auto-détection (`if raw_ts > 10**14: raw_ts / 1_000_000`).
Le `timestamp` stocké en DB est la **fin de période** (`open_time + interval`) ; Bybit (`end + 1 ms`)
s'aligne sans conversion.

### Inserts par batch de 1000

Un mois de 1m = 43,200 candles × 11 colonnes = 475k paramètres SQL, bien au-dessus de la limite
PostgreSQL de ~65k. Le script batch à 1000 rows. Tout nouveau script d'import doit faire pareil.

### SOL/USDC commence en septembre 2021

SOL/USDC n'existait pas en début 2021 sur Binance. Le script log un `file_not_found` pour les mois avant septembre 2021 — c'est normal, pas une erreur.

### Fichiers manquants pour le mois en cours

Binance Vision publie les données mensuelles avec un délai. Le mois en cours n'est généralement pas disponible. Le script log un `file_not_found` pour ces fichiers — c'est normal.

## Vérification post-import

```bash
poetry run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv
load_dotenv()
import os

async def check():
    engine = create_async_engine(os.getenv('DATABASE_URL'))
    async with engine.connect() as conn:
        r = await conn.execute(text('''
            SELECT pair, interval, COUNT(*), MIN(timestamp)::date, MAX(timestamp)::date
            FROM market_data_ohlc WHERE exchange = \\'binance\\'
            GROUP BY pair, interval ORDER BY pair, interval
        '''))
        total = 0
        for row in r:
            print(row)
            total += row[2]
        print(f'Total: {total:,}')
    await engine.dispose()

asyncio.run(check())
"
```

Vérifier :
- 21 lignes (3 paires × 7 intervals)
- BTC et ETH commencent le 2021-01-01
- SOL commence le 2021-09-24
- Toutes finissent en juin 2026 (dernier mois avant la suspension UE)
- Total ~8.7M rows

## Trous récents (backfill)

`scripts/backfill_binance_gap.py` (P7) comble un gap Binance via l'API REST publique
(`api.binance.com`), tant qu'elle reste accessible depuis l'UE — sans garantie. Pas d'usage prévu
après B3 : la source live devient Bybit.
