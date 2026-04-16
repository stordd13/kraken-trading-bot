# Skill: Database

> Comment se connecter, querier, migrer, et éviter les pièges TimescaleDB.

## Connexion

### Depuis le local (Mac)

La DB de production est sur le serveur Hetzner, pas en local. Accès via tunnel SSH sur port 5433.

```bash
# Vérifier que le tunnel est actif
nc -zv 127.0.0.1 5433

# Si mort, relancer
tunnel_ssh_hetzner  # alias zsh
# Ou manuellement :
autossh -M 0 -f -N -L 127.0.0.1:5433:localhost:5432 bruno@77.42.90.102 -p 41922 \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=60
```

Le `.env` local contient `DATABASE_URL=...@localhost:5433/krakenbot`.

**ATTENTION** : il y a un Postgres Docker local qui tourne sur `localhost:5432`. Ce n'est PAS la DB de production. Si `Settings()` retourne une URL avec port 5432, c'est un bug Pydantic — toujours utiliser `load_dotenv()` + `os.getenv("DATABASE_URL")` pour récupérer la bonne URL.

### Depuis le serveur

`.env` serveur utilise `localhost:5432` (connexion directe au container Docker).

Pour queries one-shot :
```bash
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SELECT COUNT(*) FROM market_data_ohlc;"
```

### Vérification rapide des données

```python
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
        r = await conn.execute(text('SELECT exchange, COUNT(*) FROM market_data_ohlc GROUP BY exchange'))
        for row in r:
            print(f'{row[0]}: {row[1]:,}')
    await engine.dispose()

asyncio.run(check())
"
```

Attendu : `binance: ~8,700,000` et `kraken: ~1,130,000`.

## Requêtes

### Filtre obligatoire

Tout code de production DOIT filtrer sur `exchange='binance'`. Les données kraken sont du legacy.

```sql
-- BON
SELECT * FROM market_data_ohlc WHERE exchange = 'binance' AND pair = 'BTC/USDC' AND interval = 60;

-- MAUVAIS (mélange les sources)
SELECT * FROM market_data_ohlc WHERE pair = 'BTC/USDC' AND interval = 60;
```

### Couverture des données

```sql
SELECT pair, interval, COUNT(*) as count, MIN(timestamp)::date as start, MAX(timestamp)::date as end
FROM market_data_ohlc
WHERE exchange = 'binance'
GROUP BY pair, interval
ORDER BY pair, interval;
```

## Inserts — TOUJOURS BATCHER

PostgreSQL a une limite de ~65,000 paramètres par requête. Un mois de candles 1m = 43,200 rows × 11 colonnes = 475,000 paramètres → CRASH.

```python
# MAUVAIS — crash sur les gros volumes
await session.execute(insert_stmt, all_43000_rows)

# BON — batch de 1000
BATCH_SIZE = 1000
for i in range(0, len(rows), BATCH_SIZE):
    batch = rows[i:i + BATCH_SIZE]
    await session.execute(insert_stmt, batch)
await session.commit()
```

Règle : **jamais plus de 5000 rows par execute**.

## Migrations Alembic

### Lancer une migration

```bash
# En local (via tunnel SSH)
poetry run alembic upgrade head

# Sur le serveur (connexion directe, plus fiable pour les migrations lourdes)
ssh bruno@77.42.90.102 -p 41922
cd ~/apps/kraken-trading-bot
poetry run alembic upgrade head
```

### Créer une migration

```bash
poetry run alembic revision --autogenerate -m "description"
```

### ATTENTION — Migrations sur hypertables TimescaleDB

Les ALTER TABLE (surtout DROP/CREATE PRIMARY KEY) sur des hypertables avec des millions de rows sont **extrêmement lentes et gourmandes en RAM**.

Checklist AVANT de lancer une migration lourde :
1. `free -h` sur le serveur — au moins 500 MB de RAM libre
2. Swap actif : `swapon -s` doit montrer du swap
3. Stopper les services : `sudo systemctl stop krakenbot && sudo systemctl stop krakenbot-collector`
4. Augmenter la mémoire de maintenance : `SET maintenance_work_mem = '256MB';`
5. **Ne JAMAIS lancer via tunnel SSH** — le tunnel peut couper pendant l'opération de 10-30 minutes
6. Lancer directement sur le serveur : `poetry run alembic upgrade head`

Si la migration hang > 30 minutes, vérifier `pg_stat_activity` :
```bash
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "
SELECT pid, state, wait_event, LEFT(query, 100)
FROM pg_stat_activity
WHERE datname='krakenbot' AND pid != pg_backend_pid();
"
```

### Migration manuelle (dernier recours)

Si Alembic ne passe pas, exécuter le DDL directement dans le container :
```bash
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "
SET maintenance_work_mem = '256MB';
SET statement_timeout = '0';
-- ton ALTER TABLE ici
"
```

Puis stamper la version Alembic :
```bash
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "
UPDATE alembic_version SET version_num = '<new_revision_id>';
"
```
