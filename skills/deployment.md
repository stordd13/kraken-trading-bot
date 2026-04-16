# Skill: Déploiement

> Comment déployer du code, gérer les services, et exécuter des tâches longues sur le serveur.

## Accès serveur

```
Host: 77.42.90.102
Port SSH: 41922 (port 22 bloqué par UFW)
User: bruno
Auth: clé ed25519 uniquement
Sudo: NOPASSWD configuré pour docker, systemctl, ufw, journalctl
Repo: ~/apps/kraken-trading-bot
Container DB: krakenbot-db
```

```bash
ssh bruno@77.42.90.102 -p 41922
```

## Déployer du nouveau code

```bash
ssh bruno@77.42.90.102 -p 41922
cd ~/apps/kraken-trading-bot
git fetch origin
git checkout dev
git pull origin dev
poetry install  # Seulement si pyproject.toml a changé
```

Le CI/CD GitHub Actions déploie automatiquement sur push vers `main`. Pour le déploiement manuel vers `dev`, faire les commandes ci-dessus.

## Services systemd

### Commandes

```bash
# Status
sudo systemctl status krakenbot
sudo systemctl status krakenbot-collector

# Start/Stop
sudo systemctl start krakenbot
sudo systemctl stop krakenbot

# Enable/Disable (survit aux reboots)
sudo systemctl enable krakenbot
sudo systemctl disable krakenbot

# Logs en temps réel
sudo journalctl -u krakenbot -f
sudo journalctl -u krakenbot-collector -f

# Logs des dernières 30 minutes
sudo journalctl -u krakenbot --since "30 min ago"
```

### IMPORTANT — Stopper avant les migrations

Avant toute migration Alembic ou opération DB lourde :
```bash
sudo systemctl stop krakenbot
sudo systemctl stop krakenbot-collector
```

Ne pas oublier de les redémarrer après.

## Tâches longues avec tmux

Pour les opérations qui prennent des heures (imports, backtests), toujours utiliser tmux. Sinon une déconnexion SSH tue le process.

```bash
# Créer une session
tmux new -s import

# Lancer la commande dans la session
cd ~/apps/kraken-trading-bot
poetry run python scripts/binance_vision_import.py --pairs BTC/USDC --intervals 1h --start-date 2021-01-01 --end-date 2026-04-01

# Détacher (le process continue en arrière-plan)
# Ctrl+B puis D

# Lister les sessions
tmux ls

# Réattacher
tmux attach -t import

# Tuer une session
tmux kill-session -t import
```

## Firewall (UFW)

Le serveur a UFW actif. Seul le port SSH 41922 est ouvert.

```bash
sudo ufw status verbose

# Si tu dois ouvrir un port temporairement (debug, dashboard, etc.)
sudo ufw allow 8050/tcp comment "Dash dashboard temp"

# Puis le refermer quand c'est fini
sudo ufw delete allow 8050/tcp
```

**Ne JAMAIS exposer le port 5432** (PostgreSQL) publiquement. C'est ce qui a causé le hack du serveur.

## Container Docker DB

```bash
# Status
sudo docker ps | grep krakenbot-db

# Logs
sudo docker logs krakenbot-db --tail 50

# Shell psql interactif
sudo docker exec -it krakenbot-db psql -U krakenbot krakenbot

# Query one-shot
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SELECT COUNT(*) FROM market_data_ohlc;"

# Restart container (si Postgres ne répond plus)
cd ~/docker/postgres
sudo docker compose restart
```

## Backup DB

```bash
# Créer un backup
sudo docker exec krakenbot-db pg_dump -U krakenbot --no-owner --no-acl krakenbot 2>/dev/null | gzip > ~/backup_$(date +%Y%m%d_%H%M).sql.gz

# Vérifier la taille (doit être > 100 MB avec 10M rows)
ls -lh ~/backup_*.sql.gz

# Restaurer
gunzip < ~/backup_XXXXXXXX_XXXX.sql.gz | sudo docker exec -i krakenbot-db psql -U krakenbot krakenbot
```

**Toujours faire un backup AVANT une migration Alembic lourde.**

## Mémoire serveur

Le serveur CX33 a 8 GB de RAM + 2 GB de swap. Pour les opérations gourmandes (reindex, gros imports) :

```bash
# Vérifier la RAM
free -h

# Si RAM libre < 500 MB, investiguer
ps aux --sort=-%mem | head -10
```

Si le serveur OOM-kill des process (symptôme : migration hang indéfiniment, process disparaît silencieusement), c'est qu'il manque de RAM. Solutions :
1. Stopper les services non essentiels
2. Augmenter le swap temporairement
3. Rescaler le serveur Hetzner vers un tier supérieur
