# Skill: Troubleshooting

> Problèmes réels rencontrés sur ce projet et comment les résoudre.
> Chaque entrée est un cas vécu, pas théorique.

## "Le bot a redémarré sur Kraken / log `pair=XBT/USDC strategy=threshold`" (incident du 7 sept 2026)

### Symptôme
- Premier log au boot : `krakenbot_initializing ... pair=XBT/USDC strategy=threshold` puis le REST/WS
  client Kraken s'initialise (ou `exchange=kraken` dans `analyzer_warmup_starting`).
- Au reboot du serveur Hetzner, les services sont repartis en tapant l'API Kraken alors que le projet
  était sur Binance depuis avril 2026.

### Cause
`settings.exchange_name` a pour default `"kraken"` (`src/krakenbot/config/settings.py`), et
`trading.pair` pour default `"XBT/USDC"`. Le `.env` serveur (régénéré par `deploy.yml`) ne fixait pas
`EXCHANGE_NAME`. Le `.env` local n'a pas non plus `EXCHANGE_NAME` au 7 sept 2026.

### Fix
- Immédiat : `EXCHANGE_NAME=bybit` (ou `binance` pour les scripts qui lisent les données) dans le
  `.env` concerné ; services stoppés et désactivés tant que le connecteur Bybit n'existe pas.
- Structurel (B1) : default → erreur explicite si non défini, ou default `bybit`. Mettre à jour
  `deploy.yml` et `.env.example`.

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
   - Fix : stopper les services (`sudo systemctl stop krakenbot krakenbot-collector`) AVANT la migration

3. **Le tunnel SSH a coupé** → Alembic attend une réponse sur un socket mort
   - Diagnostic : `pg_stat_activity` ne montre pas la connexion Alembic du tout
   - Fix : Ctrl+C, relancer le tunnel, relancer `alembic upgrade head`
   - Mieux : **lancer la migration directement sur le serveur** (pas via tunnel)

4. **L'hypertable TimescaleDB est trop grosse** → ALTER TABLE PK prend 10-30 minutes légitimement
   - Diagnostic : `pg_stat_activity` montre une query `CREATE INDEX` ou `ALTER TABLE` en état `active`
   - Fix : patience, c'est normal. Mais lancer depuis le serveur, pas via tunnel.

### Recovery si la migration a corrompu quelque chose

Restaurer depuis le dernier dump avec la procédure TimescaleDB (`timescaledb_pre_restore()` →
`pg_restore` → `timescaledb_post_restore()`) décrite dans `skills/database.md`. Un `psql < dump.sql`
naïf ne suffit pas sur des hypertables.

## "Le tunnel SSH ne se connecte plus"

### Symptômes
- `ssh bruno@77.42.90.102 -p 41922` hang sans afficher de prompt
- Ou affiche "Connection timed out during banner exchange" / "Operation timed out" (cas du 7 sept
  pendant l'audit B0 : l'audit a été fait sur l'API Binance publique au lieu de la DB)

### Causes possibles

1. **Le serveur est saturé** → `sshd` ne peut pas forker un nouveau process
   - Fix : reboot via la console web Hetzner (Power off → Power on)

2. **UFW bloque le port** → peu probable si ça marchait avant
   - Fix : console web Hetzner → login → `sudo ufw allow 41922/tcp`

3. **Le serveur est down** → Hetzner maintenance ou crash
   - Fix : vérifier dans la console web Hetzner le statut du serveur

### Après un reboot forcé

```bash
sleep 90                                   # Attendre que tout démarre
ssh bruno@77.42.90.102 -p 41922
sudo docker ps | grep krakenbot-db         # Docker + Postgres up ?
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SELECT COUNT(*) FROM market_data_ohlc;"
sudo systemctl status krakenbot krakenbot-collector   # Doivent être inactive/disabled (état B0.5)
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
- Les queries via `Settings().database.url` se connectent au Postgres Docker local (port 5432, données
  Kraken uniquement) au lieu du serveur Hetzner (port 5433 via tunnel)

### Cause
Pydantic Settings a un default hardcodé `localhost:5432`. Le `.env` dit `localhost:5433` mais Settings
ne le lit pas dans certains contextes (scripts standalone).

### Fix
Toujours utiliser `load_dotenv()` + `os.getenv("DATABASE_URL")` au lieu de `Settings().database.url`
pour les scripts standalone :

```python
from dotenv import load_dotenv
import os
load_dotenv()
url = os.getenv("DATABASE_URL")  # Correct, lit le .env
```

## "Import crash avec 475000 parameters truncated"

### Symptôme
- Un script d'import crash sur les timeframes 1m avec une erreur SQL sur trop de paramètres

### Cause
Un mois de candles 1m = 43,200 rows × 11 colonnes = 475,200 paramètres. PostgreSQL limite à ~65,000
par query.

### Fix
Batcher les inserts en lots de 1000 rows (`skills/database.md`). `binance_vision_import.py` le fait ;
tout nouveau script d'import (Bybit B3) doit le faire aussi.

## "L'agent réimporte les données qui sont déjà en DB"

### Symptôme
- L'agent lance `binance_vision_import.py` alors que les 8.7M rows sont déjà en DB
- Ou l'agent dit "No Binance data locally — only Kraken data" (il a tapé le Docker local, port 5432)

### Cause
L'agent ne vérifie pas la DB avant de décider d'importer. Ou le tunnel SSH est mort et la query de
vérification échoue.

### Fix
1. Vérifier le tunnel : `nc -zv 127.0.0.1 5433`
2. Lancer le script de vérification de `skills/database.md` (attendu `binance: ~8,700,000`).
3. Rappel : les données Binance ne peuvent **plus** être réimportées depuis l'UE de toute façon.

## "Un test est skippé : Database not reachable"

Les tests de déterminisme P6 et le gold-hash `grid_atr_v4` (`tests/test_strategies/test_grid_atr_v4_backward_compat.py`)
ont besoin du tunnel (port 5433). Sans tunnel ils se skippent (31 skips attendus). Ce n'est pas un échec,
mais ces gates doivent être verts avant de merger un changement du backtester.

## "sudo demande un mot de passe dans Claude Code"

### Symptôme
- L'agent ne peut pas exécuter de commandes `sudo` sur le serveur parce que le prompt de password bloque

### Fix
Configurer NOPASSWD pour les commandes nécessaires :
```bash
echo "bruno ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/systemctl, /usr/sbin/ufw, /usr/bin/journalctl, /usr/bin/tail, /usr/bin/cat" | sudo tee /etc/sudoers.d/bruno-claude-nopasswd
sudo chmod 440 /etc/sudoers.d/bruno-claude-nopasswd
```
