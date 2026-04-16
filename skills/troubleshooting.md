# Skill: Troubleshooting

> Problèmes réels rencontrés sur ce projet et comment les résoudre.
> Chaque entrée est un cas vécu, pas théorique.

## "La migration Alembic hang indéfiniment"

### Symptômes
- `alembic upgrade head` affiche "Running upgrade..." et ne revient jamais
- `pg_stat_activity` ne montre aucune query active d'Alembic
- OU montre une query `ALTER TABLE` en état `active` depuis 30+ minutes

### Causes possibles (par ordre de probabilité)

1. **Le serveur manque de RAM** → PostgreSQL OOM-killed silencieusement
   - Diagnostic : `free -h` sur le serveur, si RAM libre < 200 MB c'est ça
   - Fix : ajouter du swap (`fallocate -l 2G /swapfile && mkswap /swapfile && swapon /swapfile`)
   - Ou rescaler le serveur Hetzner

2. **Un service écrit en DB en parallèle** → locks qui bloquent l'ALTER TABLE
   - Diagnostic : `pg_stat_activity` montre des INSERT sur `market_data_ohlc`
   - Fix : stopper les services (`systemctl stop krakenbot && systemctl stop krakenbot-collector`) AVANT la migration

3. **Le tunnel SSH a coupé** → Alembic attend une réponse sur un socket mort
   - Diagnostic : `pg_stat_activity` ne montre pas la connexion Alembic du tout
   - Fix : Ctrl+C, relancer le tunnel, relancer `alembic upgrade head`
   - Mieux : **lancer la migration directement sur le serveur** (pas via tunnel)

4. **L'hypertable TimescaleDB est trop grosse** → ALTER TABLE PK prend 10-30 minutes légitimement
   - Diagnostic : `pg_stat_activity` montre une query `CREATE INDEX` ou `ALTER TABLE` en état `active`
   - Fix : patience, c'est normal. Mais lancer depuis le serveur, pas via tunnel.

### Procédure de recovery si la migration a corrompu quelque chose

```bash
# Restaurer depuis le backup
gunzip < ~/backup_XXXXXXXX_XXXX.sql.gz | sudo docker exec -i krakenbot-db psql -U krakenbot krakenbot

# Vérifier
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SELECT COUNT(*) FROM market_data_ohlc;"
```

## "Le tunnel SSH ne se connecte plus"

### Symptômes
- `ssh bruno@77.42.90.102 -p 41922` hang sans afficher de prompt
- Ou affiche "Connection timed out during banner exchange"

### Causes possibles

1. **Le serveur est saturé** → `sshd` ne peut pas forker un nouveau process
   - Fix : reboot via la console web Hetzner (Power off → Power on)

2. **UFW bloque le port** → peu probable si ça marchait avant
   - Fix : console web Hetzner → login → `sudo ufw allow 41922/tcp`

3. **Le serveur est down** → Hetzner maintenance ou crash
   - Fix : vérifier dans la console web Hetzner le statut du serveur

### Après un reboot forcé

```bash
# Attendre 90 secondes que tout démarre
sleep 90

# Tester SSH
ssh bruno@77.42.90.102 -p 41922

# Vérifier que Docker + Postgres sont up
sudo docker ps | grep krakenbot-db

# Vérifier que les données sont intactes
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SELECT COUNT(*) FROM market_data_ohlc;"
```

## "Le tunnel SSH local existe mais ne route plus"

### Symptômes
- `ps aux | grep autossh` montre le process
- `nc -zv 127.0.0.1 5433` dit "Connection refused"

### Fix
```bash
pkill -9 -f "autossh.*77.42.90.102"
pkill -9 -f "ssh.*5433"
sleep 2
tunnel_ssh_hetzner  # Ou relancer autossh manuellement
sleep 3
nc -zv 127.0.0.1 5433  # Doit dire "succeeded"
```

## "Settings() retourne le mauvais DATABASE_URL (port 5432 au lieu de 5433)"

### Symptôme
- Les queries via `Settings().database.url` se connectent à un Postgres Docker local (port 5432) au lieu du serveur Hetzner (port 5433 via tunnel)

### Cause
Pydantic Settings a un default hardcodé `localhost:5432`. Le `.env` dit `localhost:5433` mais Settings ne le lit pas correctement.

### Fix
Toujours utiliser `load_dotenv()` + `os.getenv("DATABASE_URL")` au lieu de `Settings().database.url` pour les scripts standalone :

```python
from dotenv import load_dotenv
import os
load_dotenv()
url = os.getenv("DATABASE_URL")  # Correct, lit le .env
```

Pour le code applicatif (main.py, collector.py), vérifier que la chaîne de chargement des Settings passe bien par le `.env`.

## "Import Binance Vision crash avec 475000 parameters truncated"

### Symptôme
- Le script `binance_vision_import.py` crash sur les timeframes 1m avec une erreur SQL sur trop de paramètres

### Cause
Un mois de candles 1m = 43,200 rows × 11 colonnes = 475,200 paramètres. PostgreSQL limite à ~65,000 par query.

### Fix
Le script doit batcher les inserts en lots de 1000 rows. Si le fix n'est pas appliqué, voir le commit `fix(scripts): batch binance vision inserts to avoid postgresql parameter limit`.

## "L'agent réimporte les données qui sont déjà en DB"

### Symptôme
- L'agent lance `binance_vision_import.py` alors que les 8.7M rows sont déjà en DB
- Ou l'agent dit "No Binance data locally — only Kraken data"

### Cause
L'agent ne vérifie pas la DB avant de décider d'importer. Ou le tunnel SSH est mort et la query de vérification échoue.

### Fix
1. Vérifier le tunnel : `nc -zv 127.0.0.1 5433`
2. Montrer à l'agent que les données existent :
```bash
poetry run python -c "
from dotenv import load_dotenv; load_dotenv()
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
async def check():
    e = create_async_engine(os.getenv('DATABASE_URL'))
    async with e.connect() as c:
        r = await c.execute(text('SELECT exchange, COUNT(*) FROM market_data_ohlc GROUP BY exchange'))
        for row in r: print(row)
    await e.dispose()
asyncio.run(check())
"
```

## "Le bot démarre mais dit pair=XBT/USDC strategy=threshold"

### Symptôme
- Premier log au boot : `environment=development mode=paper pair=XBT/USDC strategy=threshold`
- Mais ensuite les stratégies multi-pair s'initialisent correctement

### Cause
C'est un log legacy dans `main.py` qui utilise la config `.env` avant que le `MultiStrategyRouter` prenne le relais. Pas bloquant, juste cosmétique.

### Fix
Non critique. À nettoyer quand on touchera à `main.py`.

## "sudo demande un mot de passe dans Claude Code"

### Symptôme
- L'agent Claude Code ne peut pas exécuter de commandes `sudo` sur le serveur parce que le prompt de password bloque

### Fix
Configurer NOPASSWD pour les commandes nécessaires :
```bash
echo "bruno ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/systemctl, /usr/sbin/ufw, /usr/bin/journalctl, /usr/bin/tail, /usr/bin/cat" | sudo tee /etc/sudoers.d/bruno-claude-nopasswd
sudo chmod 440 /etc/sudoers.d/bruno-claude-nopasswd
```

Après le fix, les commandes sudo ne demandent plus de password.
