# Skill: Database

> Comment se connecter, querier, migrer, sauvegarder/restaurer, et éviter les pièges TimescaleDB.

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

Le `.env` local contient `DATABASE_URL=postgresql+asyncpg://krakenbot:<pwd>@localhost:5433/krakenbot`.
Pour les backtests P6/P7, utiliser ce `.env` tel quel (ne pas surcharger `DATABASE_URL`).

**ATTENTION** : il y a un Postgres Docker local qui tourne sur `localhost:5432`. Ce n'est PAS la DB de
production (il ne contient que des données Kraken). Si `Settings()` retourne une URL avec port 5432,
c'est le default Pydantic — pour les scripts standalone, toujours `load_dotenv()` +
`os.getenv("DATABASE_URL")`.

Le tunnel peut lâcher silencieusement pendant une opération longue : une query qui ne revient jamais
est presque toujours un tunnel mort, pas un lock Postgres (voir `skills/troubleshooting.md`).

### Depuis le serveur

`.env` serveur utilise `localhost:5432` (connexion directe au container Docker `krakenbot-db`).

```bash
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SELECT COUNT(*) FROM market_data_ohlc;"
```

### Vérification rapide des données (à faire AVANT tout import)

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

Attendu (septembre 2026) :

| `exchange` | Rows | Rôle |
|---|---|---|
| `binance` | ~8,700,000 | Base de backtest (2021-01 → 2026-06, 3 paires × 7 TF). Figée : plus d'import possible depuis l'UE. |
| `kraken` | ~1,130,000 | Legacy, à supprimer une fois Bybit validé en live. |
| `bybit` | 0 (à venir en B3) | Données live Bybit EU (historique depuis 2025-06-11). Cible de production. |

**Ne JAMAIS réimporter** des données déjà présentes. Voir `skills/binance_import.md`.

## Requêtes

### Filtre obligatoire

Tout code de production filtre sur **`settings.exchange_name`** (cible : `bybit`), jamais un littéral.
Les backtests lisent explicitement `exchange = 'binance'` (source de données, décision B0).

```sql
-- Backtest / analyse (source de données Binance)
SELECT * FROM market_data_ohlc WHERE exchange = 'binance' AND pair = 'BTC/USDC' AND interval = 60;

-- MAUVAIS (mélange les sources)
SELECT * FROM market_data_ohlc WHERE pair = 'BTC/USDC' AND interval = 60;
```

Dette connue : `settings.exchange_name` a pour default `"kraken"` (`config/settings.py`). Si `EXCHANGE_NAME`
n'est pas défini dans le `.env`, le bot tourne sur Kraken (incident serveur du 7 sept 2026). Fix prévu en B1.

### Couverture des données

```sql
SELECT exchange, pair, interval, COUNT(*) AS count, MIN(timestamp)::date AS start, MAX(timestamp)::date AS end
FROM market_data_ohlc
GROUP BY exchange, pair, interval
ORDER BY exchange, pair, interval;
```

Notes : SOL/USDC commence le 2021-09-24 sur Binance. **Convention de `timestamp` : fin de période pour tous les exchanges** (`open + interval` ;
Bybit `end + 1 ms`). Historique : les rows `binance` (import Vision) étaient stampées à l'**open time**
(constat B3, 2026-09-11, dette 11) ; elles ont été **re-stampées en fin de période le 2026-09-13 (B4.1)** —
`results/B4_1_timestamp_restamp_report.md`, scripts `scripts/audit/b4_*.py`, manifeste
`results/b4_binance_stamp_boundaries.json`. `scripts/binance_vision_import.py` écrit la fin de période depuis
B4.1. Les 8.7 M rows `binance` finissent le `2026-04-01 00:00` (1w : `2026-04-06`).

## Inserts — TOUJOURS BATCHER

PostgreSQL a une limite de ~65,000 paramètres par requête. Un mois de candles 1m = 43,200 rows × 11
colonnes = 475,000 paramètres → CRASH.

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

Règle : **jamais plus de 5000 rows par execute**. Utiliser `ON CONFLICT DO NOTHING` (idempotence).

## Backup & restore TimescaleDB

### Backups existants

| Date | Fichier | Taille | Contenu |
|---|---|---|---|
| 2026-09-07 | `~/Backups/krakenbot/krakenbot_20260907.dump` (Mac de Bruno) | 203 Mo | DB complète (format custom `pg_dump -Fc`), avant arrêt des services |

Il n'y a **pas encore de backup récurrent** (item roadmap, requis avant B5).

### Créer un backup (sur le serveur)

```bash
sudo docker exec krakenbot-db pg_dump -U krakenbot -Fc --no-owner --no-acl krakenbot \
    > ~/krakenbot_$(date +%Y%m%d).dump
ls -lh ~/krakenbot_*.dump      # > 100 Mo attendu
# Rapatrier en local
scp -P 41922 bruno@77.42.90.102:~/krakenbot_YYYYMMDD.dump ~/Backups/krakenbot/
```

**Toujours faire un backup AVANT une migration Alembic lourde.**

### Restaurer (procédure TimescaleDB, non triviale)

Un `pg_restore` naïf sur une DB TimescaleDB échoue ou laisse les hypertables incohérentes. Il faut
encadrer la restauration avec `timescaledb_pre_restore()` / `timescaledb_post_restore()` et la même
**version majeure** de l'extension que celle du dump.

```bash
# 0. Services stoppés (sinon des INSERT arrivent pendant le restore)
sudo systemctl stop krakenbot krakenbot-collector

# 1. Version de l'extension côté cible (doit matcher celle du dump, cf. `pg_restore -l dump | grep timescaledb`)
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c \
    "SELECT extversion FROM pg_extension WHERE extname='timescaledb';"

# 2. Copier le dump dans le container
sudo docker cp ~/krakenbot_20260907.dump krakenbot-db:/tmp/krakenbot.dump

# 3. Base vide avec l'extension
sudo docker exec krakenbot-db psql -U krakenbot -d postgres -c "CREATE DATABASE krakenbot_restore;"
sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot_restore -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# 4. pre_restore → pg_restore → post_restore (dans la même base)
sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot_restore -c "SELECT timescaledb_pre_restore();"
sudo docker exec krakenbot-db pg_restore -U krakenbot -d krakenbot_restore -Fc --no-owner --no-acl /tmp/krakenbot.dump
sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot_restore -c "SELECT timescaledb_post_restore();"

# 5. Vérifier puis basculer (renommer les bases) — jamais restaurer par-dessus la base vivante
sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot_restore -c \
    "SELECT exchange, COUNT(*) FROM market_data_ohlc GROUP BY exchange;"
```

Pièges : (a) mismatch de version majeure TimescaleDB → `pg_restore` échoue sur `_timescaledb_catalog` ;
(b) oublier `post_restore()` laisse la DB en mode restore (jobs de compression/retention désactivés) ;
(c) la mémoire : vérifier `free -h` et le swap avant, comme pour une migration.

## Migrations Alembic

### Lancer une migration

```bash
# En local (via tunnel SSH) — uniquement pour les migrations légères
poetry run alembic upgrade head

# Sur le serveur (connexion directe, obligatoire pour les migrations lourdes)
ssh bruno@77.42.90.102 -p 41922
cd ~/apps/kraken-trading-bot
poetry run alembic upgrade head
```

### Créer une migration

```bash
poetry run alembic revision --autogenerate -m "description"
```

### ATTENTION — Migrations sur hypertables TimescaleDB

Les ALTER TABLE (surtout DROP/CREATE PRIMARY KEY) sur des hypertables avec des millions de rows sont
**extrêmement lentes (10-30 min) et gourmandes en RAM**.

Checklist AVANT de lancer une migration lourde :
1. Backup (section ci-dessus)
2. `free -h` sur le serveur — au moins 500 MB de RAM libre, sinon augmenter le swap ou le tier Hetzner
3. Swap actif : `swapon -s` doit montrer du swap
4. Stopper les services : `sudo systemctl stop krakenbot krakenbot-collector`
5. Augmenter la mémoire de maintenance : `SET maintenance_work_mem = '256MB';`
6. **Ne JAMAIS lancer via tunnel SSH** — le tunnel peut couper pendant l'opération
7. Lancer directement sur le serveur (dans `tmux`) : `poetry run alembic upgrade head`

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

Dernière migration connue : `f7a8b9c0d1e2` (colonne `exchange` + PK 4 colonnes). TimescaleDB a
besoin de `max_locks_per_transaction >= 512` pour les grosses requêtes multi-chunks (9 ans).
