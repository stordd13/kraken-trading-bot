# Skill: Déploiement

> Comment accéder au serveur, gérer les services, exécuter des tâches longues, et réactiver le bot
> quand le connecteur Bybit sera prêt.

## État actuel (9 septembre 2026, 18:12 UTC — B2 déployé)

- **`krakenbot-collector` est `enabled` + `active`** depuis le 9 sept 18:12 UTC (B2, `dev@ad296c8`) :
  WS Bybit EU, 3 paires × 7 TF, écrit `exchange='bybit'` dans la DB locale du serveur. Observation 24 h en
  cours (voir ci-dessous).
- **`krakenbot` (trader) reste stoppé ET désactivé** jusqu'à B4/B5. Historique : le bot tournait dans le
  vide depuis la suspension de Binance UE (1er juillet 2026), et au reboot du serveur les services étaient
  repartis sur **Kraken** (le `.env` serveur ne fixait pas `EXCHANGE_NAME`) — réglé : `.env` serveur =
  `EXCHANGE_NAME=bybit`, 4 clés `BYBIT_*`, `SCHEDULER_PAIRS`/`SCHEDULER_INTERVALS` (backup `.env.bak-pre-b2`).
- La DB tourne (container `krakenbot-db`), backupée le 7 sept (voir `skills/database.md`).
- Le serveur suit **`dev`** (`git pull --ff-only origin dev`), pas `main`. ⚠️ Un push sur `main` déclenche
  `deploy.yml`, qui redémarre **les deux** services et exige `krakenbot` actif : pas avant B5.

### Observation 24 h du collector (B2, à faire le 10 sept ~18:15 UTC)

```bash
# Événements watchdog / reconnexions depuis le démarrage (attendu : 0, ou très peu et justifiés)
sudo journalctl -u krakenbot-collector --since "2026-09-09 18:12" --no-pager -o cat \
  | grep -c -E '"event": "bybit_ws_(data_flow_stale|data_flow_zombie|pong_timeout|reconnecting|resubscribed)"'
sudo journalctl -u krakenbot-collector --since "2026-09-09 18:12" --no-pager -o cat \
  | grep -E '"event": "bybit_ws_(data_flow_stale|data_flow_zombie|pong_timeout|reconnecting|preventive_reconnect)"' | cut -c1-200
# Débit du flux agrégé (toutes les 5 min) et stats du collector
sudo journalctl -u krakenbot-collector --since "24 hours ago" --no-pager -o cat | grep -c bybit_ws_data_flow_ok
sudo journalctl -u krakenbot-collector --no-pager -o cat | grep collector_periodic_stats | tail -1
# DB : cohérence par TF, alignement grille, trous 1m (= reconnexions), candles plates
sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot -c \
  "SELECT interval, COUNT(*), MIN(timestamp), MAX(timestamp) FROM market_data_ohlc WHERE exchange='bybit' GROUP BY interval ORDER BY interval;"
sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot -c \
  "SELECT interval, COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM timestamp)::bigint % (interval*60) <> 0) AS misaligned FROM market_data_ohlc WHERE exchange='bybit' GROUP BY interval;"
sudo docker exec krakenbot-db psql -U krakenbot -d krakenbot -c \
  "WITH t AS (SELECT pair, timestamp, LAG(timestamp) OVER (PARTITION BY pair ORDER BY timestamp) prev FROM market_data_ohlc WHERE exchange='bybit' AND interval=1 AND timestamp > '2026-09-09 18:12') SELECT pair, prev, timestamp FROM t WHERE timestamp - prev > interval '1 minute';"
```
Sur le serveur la DB est locale (pas de tunnel) : les 3 décrochages vus en collecte locale ne devraient pas se
reproduire ; s'il y a des reconnexions, c'est un signal réseau réel. Si 24 h propres → tag `v2.4.0-b2-bybit-ws`.
Note : le champ `timestamp` des logs `bybit_ws_ohlc_complete` est l'heure du log (collision avec structlog),
pas la clôture de la candle — lire la DB pour les timestamps de candles (à renommer en B3).

## Accès serveur

```
Host: 77.42.90.102
Port SSH: 41922 (port 22 bloqué par UFW)
User: bruno
Auth: clé ed25519 uniquement
Sudo: NOPASSWD pour docker, systemctl, ufw, journalctl, cp, tail, cat — utiliser `sudo -n <cmd>` ;
      tout autre binaire demande le mot de passe (si le prompt bloque : voir troubleshooting)
Repo: ~/apps/kraken-trading-bot
Container DB: krakenbot-db (timescale/timescaledb, bind 127.0.0.1:5432)
Serveur: Hetzner CX33, 4 vCPU, 8 GB RAM, 2 GB swap, 80 GB disque
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

Le CI/CD GitHub Actions (`.github/workflows/deploy.yml`) déploie automatiquement sur push vers `main`
**et régénère le `.env` serveur depuis les GitHub Secrets**. Ce template est encore Kraken-era
(`KRAKEN_API_KEY`, pas d'`EXCHANGE_NAME`, pas de `BYBIT_*`) : à mettre à jour en B1/B2 avant tout
redémarrage, sinon le prochain deploy réintroduit l'incident du 7 sept.

## Services systemd

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

### Stopper avant les migrations

Avant toute migration Alembic ou opération DB lourde (backup/restore inclus) :
```bash
sudo systemctl stop krakenbot krakenbot-collector
```

### Procédure de réactivation (B2 → B5)

1. `.env` serveur : `EXCHANGE_NAME=bybit`, `BYBIT_API_KEY` / `BYBIT_API_SECRET` (clés créées sur
   bybit.eu, IP whitelist = IP du serveur Hetzner), `TRADING_MODE=paper`. Mettre à jour `deploy.yml`
   et les GitHub Secrets en même temps.
2. Vérifier `poetry run python -c "from krakenbot.config.settings import get_settings; print(get_settings().exchange_name)"` → `bybit`.
3. ✅ B2 (9 sept 18:12 UTC) : `sudo systemctl enable --now krakenbot-collector`, observation 24 h
   (commandes ci-dessus).
4. B5 : `sudo systemctl enable --now krakenbot` en paper, seulement après B4 (re-backtests fees Bybit).
5. Vérifier le premier log `krakenbot_initializing` : `exchange=bybit`, `pair=BTC/USDC`, pas `XBT`.

## Tâches longues avec tmux

Pour les opérations qui prennent des heures (imports, backtests), toujours utiliser tmux. Sinon une
déconnexion SSH tue le process.

```bash
tmux new -s import              # Créer une session
cd ~/apps/kraken-trading-bot
poetry run python scripts/run_p6_backtests.py --workers 4   # ex. de tâche longue
# Ctrl+B puis D pour détacher (le process continue en arrière-plan)
tmux ls                         # Lister
tmux attach -t import           # Réattacher
tmux kill-session -t import     # Tuer
```

## Firewall (UFW)

Le serveur a UFW actif. Seul le port SSH 41922 est ouvert.

```bash
sudo ufw status verbose

# Ouvrir un port temporairement (debug, dashboard, etc.)
sudo ufw allow 8050/tcp comment "Dash dashboard temp"
# Puis le refermer
sudo ufw delete allow 8050/tcp
```

**Ne JAMAIS exposer le port 5432** (PostgreSQL) publiquement. C'est ce qui a causé le hack du serveur.

## Container Docker DB

```bash
sudo docker ps | grep krakenbot-db                 # Status
sudo docker logs krakenbot-db --tail 50            # Logs
sudo docker exec -it krakenbot-db psql -U krakenbot krakenbot   # Shell psql
sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SELECT COUNT(*) FROM market_data_ohlc;"

# Restart container (si Postgres ne répond plus)
cd ~/docker/postgres
sudo docker compose restart
```

## Backup DB

Procédure complète (pg_dump custom, restore TimescaleDB avec pre/post_restore, localisation des
dumps) dans `skills/database.md`. Backup récurrent (cron + rotation + storage box Hetzner) : item
roadmap, à mettre en place avant B5.

## Mémoire serveur

```bash
free -h                          # Si RAM libre < 500 MB, investiguer
ps aux --sort=-%mem | head -10
```

Si le serveur OOM-kill des process (symptôme : migration qui hang, process qui disparaît
silencieusement), il manque de RAM : stopper les services non essentiels, augmenter le swap, ou
rescaler le serveur Hetzner. Les backtests P6/P7 en parallèle sur le serveur : max 4 workers (~1 GB
par worker pandas).
