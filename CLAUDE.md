# CLAUDE.md — Guide pour Agents

> Ce fichier définit COMMENT travailler sur ce projet. Pour l'état complet du projet, lire `PROJECT_CONTEXT.md`.

## Le projet en une phrase

Bot de trading automatisé multi-pair (BTC/ETH/SOL sur USDC) sur **Binance**, avec 8 stratégies, risk management centralisé, déployé sur Hetzner.

---

## Skills de référence 

Avant de commencer une tâche, consulte le skill pertinent dans `skills/` :
- Tâche DB (migration, import, query) → `skills/database.md`
- Backtest → `skills/backtest.md`
- Nouvelle stratégie → `skills/new_strategy.md`
- Déploiement serveur → `skills/deployment.md`
- Import données historiques → `skills/binance_import.md`
- Risk management → `skills/risk_management.md`
- Bug ou problème → `skills/troubleshooting.md`
- Pour localiser un module ou une fonction → `docs/CODE_MAP.md` (à régénérer à chaque merge sur dev)

---

## Commandes essentielles

```bash
# Tests (toujours lancer avant de commit)
poetry run pytest -q

# Lint + format (toujours lancer avant de commit)
poetry run ruff check . --fix && poetry run ruff format .

# Lancer le bot en local (paper mode)
poetry run python -m krakenbot

# Lancer le collector en local
poetry run python -m krakenbot.collector

# Backtest une stratégie
poetry run python scripts/backtest.py --strategy grok_supertrend_4h --pair BTC/USDC --exchange binance --days 1095 --capital 1000

# Lancer les 24 backtests P6 en parallèle (multiprocessing)
poetry run python scripts/run_p6_backtests.py              # auto workers
poetry run python scripts/run_p6_backtests.py --workers 8  # override
poetry run python scripts/run_p6_backtests.py --serial     # debug / gate déterminisme
# Reprise automatique : relancer sans --force ignore les combos déjà complétés
# Monitoring temps réel : watch -n 2 cat logs/p6_status.json

# Lancer le grid search P7 (4 stratégies P6 survivantes, grilles ciblées)
# Phase 1 : cross-validate 70/30 sur 212 configurations (≈ 1.5h en parallèle)
poetry run python scripts/run_p7_grid_search.py --phase 1 --workers 8 --timeout 3600
# Phase 2 : walk-forward 8 fenêtres × top-5 par combo (≈ 1.5h)
poetry run python scripts/run_p7_grid_search.py --phase 2 --workers 8 --timeout 3600
# Phase rapport : agrégation + critères + Markdown
poetry run python scripts/run_p7_grid_search.py --phase report
# Monitoring : watch -n 2 cat logs/p7_status.json
# Filtres phase 1 : --strategy grok_supertrend_4h --pair BTC/USDC

# Dashboard
poetry run python scripts/dashboard.py
```

---

## Accès à la base de données

**La DB de production est sur le serveur Hetzner**, pas en local. L'accès se fait via un tunnel SSH.

**Depuis le local (Mac)** :
- Le tunnel bind `localhost:5433` → serveur `localhost:5432`
- Le `.env` contient `DATABASE_URL=postgresql+asyncpg://krakenbot:<pwd>@localhost:5433/krakenbot`
- Vérifier que le tunnel est actif : `nc -zv 127.0.0.1 5433`
- Si le tunnel est mort : lancer `tunnel_ssh_hetzner` (alias zsh) ou relancer autossh manuellement

**Depuis le serveur** :
- `.env` serveur utilise `localhost:5432` (connexion directe au container Docker)
- Pour les queries one-shot : `sudo docker exec krakenbot-db psql -U krakenbot krakenbot`

**IMPORTANT** : ne JAMAIS réimporter les données si elles sont déjà en DB. Vérifier d'abord :
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

Tu dois voir `binance: ~8,700,000` et `kraken: ~1,130,000`.

---

## Architecture clé

### Flux d'un trade
```
Candle WebSocket → EventBus (MARKET_OHLC)
  → MultiStrategyRouter (filtre par pair)
    → Stratégie interne (on_ohlc + generate_signal)
    → GeminiGlobalRiskManager (1% rule, ATR SL, crash protector)
    → EventBus (TRADE_SIGNAL)
  → ExecutionEngine → Binance REST
  → EventBus (TRADE_ORDER_FILLED)
    → route vers stratégie source via bot_id
```

### Multi-pair
- `MultiPairAnalyzerRegistry` : un analyzer par pair, création lazy
- Le router filtre les candles : une candle ETH ne va qu'aux stratégies ETH
- Chaque stratégie a son `self.pair`, son `bot_id` unique, ses positions séparées

### Types d'ordres
- BUY → toujours LIMIT (maker 0.075%)
- SELL profit target → LIMIT
- SELL stop-loss / trailing / timeout → MARKET (exécution garantie)

---

## Conventions de code obligatoires

### Absolues
- **Python 3.12+**, async/await partout
- **Decimal** pour tous les montants et prix (`Decimal("65000.50")`, jamais float)
- **UTC** pour tous les timestamps
- **structlog** pour le logging (jamais print, jamais logging stdlib)
- **Imports absolus** : `from krakenbot.core import ...`

### Patterns
```python
# Logger
logger = structlog.get_logger(__name__)
logger.info("event_name", pair=self.pair, strategy=self.bot_id, key=value)

# Decimal
price = Decimal("65000.50")  # Via string, jamais Decimal(65000.50)

# Normalize pair (XBT → BTC)
from krakenbot.utils.pair import normalize_pair
pair = normalize_pair(raw_pair)

# Accès analyzer multi-pair
analyzer = self._analyzer_registry.get(self.pair)
rsi = analyzer.get_rsi(14, "4h")
```

### Naming
- Classes : `PascalCase`
- Fonctions/variables : `snake_case`
- Constantes : `UPPER_SNAKE_CASE`

---

## Patterns pour les stratégies

Toute nouvelle stratégie DOIT :
1. Hériter de `BaseStrategy`
2. Accepter `pair: str` dans le constructeur
3. Implémenter `on_ohlc()`, `generate_signal()`, `get_name()`, `get_config()`
4. Utiliser `self.pair` partout (jamais hardcoder une paire)
5. Persister ses positions dans `open_positions` (pas en mémoire seule)
6. Logger chaque signal avec metadata (régime, seuils, raison, pair)
7. Mettre `order_type` ("limit"/"market") et `position_size_multiplier` dans `signal.metadata`
8. Être ajoutée dans `strategies.yaml` avec son `class`, `pair`, `bot_id`

---

## Ce qu'il ne faut JAMAIS faire

1. **Ne pas utiliser float** pour les prix/montants
2. **Ne pas hardcoder** `XBT/USDC` ou `BTC/USDC` dans les stratégies
3. **Ne pas créer** de MultiTimeframeAnalyzer manuellement — utiliser le registry
4. **Ne pas insérer** > 5000 rows en un seul SQL execute (limite PostgreSQL ~65k paramètres)
5. **Ne pas commit** `.env`, credentials, ou API keys
6. **Ne pas modifier** MultiStrategyRouter, GeminiGlobalRiskManager, ExecutionEngine sans raison explicite et review humain
7. **Ne pas bypasser** le GlobalRiskManager
8. **Ne pas merger** sur `main` sans passer par `dev`
9. **Ne pas réimporter** des données déjà en DB — vérifier d'abord
10. **Ne pas lancer** de migrations Alembic lourdes (ALTER PK) via un tunnel SSH — exécuter directement sur le serveur avec `maintenance_work_mem` augmenté

---

## Leçons opérationnelles (apprises dans la douleur)

### DB et migrations
- Les ALTER TABLE sur les hypertables TimescaleDB peuvent prendre 10-30 min et nécessitent beaucoup de RAM. Toujours vérifier `free -h` sur le serveur et s'assurer que le swap est actif.
- Si une migration hang, vérifier `pg_stat_activity` pour voir ce que Postgres fait réellement.
- Si le serveur a < 500 MB de RAM libre, augmenter le swap ou le server tier AVANT de lancer la migration.
- Pour les DDL manuelles sur le serveur : `sudo docker exec krakenbot-db psql -U krakenbot krakenbot -c "SET maintenance_work_mem='256MB'; ..."`.

### Tunnel SSH
- Le tunnel SSH peut lâcher silencieusement pendant des opérations longues. Alembic attend alors une réponse qui ne viendra jamais.
- Pour les opérations DB longues, préférer l'exécution directe sur le serveur (SSH + `poetry run alembic upgrade head`) plutôt que via tunnel.

### Binance Vision import
- Les fichiers CSV récents (2025+) utilisent des timestamps en microsecondes (16 chiffres) au lieu de millisecondes (13 chiffres). Le script gère les deux automatiquement.
- Toujours batcher les inserts (1000 rows par batch). Un mois de 1m = 43200 candles × 11 colonnes = 475k paramètres SQL, bien au-dessus de la limite PostgreSQL de 65k.

### Services serveur
- `krakenbot.service` et `krakenbot-collector.service` gérés par systemd
- Pour les tâches de longue durée (imports, backtests), utiliser `tmux` sur le serveur pour survivre aux déconnexions SSH
- Toujours stopper les services avant une migration DB : `sudo systemctl stop krakenbot && sudo systemctl stop krakenbot-collector`

---

## Structure des fichiers clés

```
src/krakenbot/
├── strategies/
│   ├── base.py                              # BaseStrategy ABC + TradingSignal
│   ├── multi_strategy_router.py             # Router (dispatch par pair)
│   ├── gemini_global_risk_manager.py        # Risk overlay
│   ├── grok_grid_atr_adaptive_v4.py         # Grid ATR
│   ├── grok_supertrend_4h.py                # SuperTrend
│   ├── grok_donchian_breakout_4h.py         # Donchian breakout
│   ├── grok_ema_adx_atr.py                  # EMA cross
│   ├── grok_adaptive_dca_weekly.py          # DCA weekly
│   ├── gemini_scalping_volatilite.py        # Scalping 5m
│   ├── gemini_suivi_tendance_momentum.py    # Trend momentum
│   └── gemini_retour_moyenne.py             # Mean reversion
├── indicators/
│   ├── multi_timeframe.py                   # MultiTimeframeAnalyzer
│   └── multi_pair_registry.py               # Per-pair analyzer registry
├── execution/
│   ├── engine.py                            # ExecutionEngine
│   ├── risk.py                              # GlobalRiskManager
│   └── order_manager.py                     # Limit order lifecycle
├── connectors/
│   ├── binance/rest.py, ws.py               # Binance REST + WebSocket
│   └── kraken/rest.py, ws.py, futures.py    # Legacy Kraken
├── config/settings.py                       # Pydantic settings + ExchangeFees
└── main.py                                  # Orchestrateur

scripts/
├── backtest.py                              # BacktestEngine (signal + grid)
├── binance_vision_import.py                 # Import données historiques
├── dashboard.py                             # Dashboard Dash
└── backtest_grid.py                         # Grid search paramètres

strategies.yaml                              # Config multi-stratégie
```

---

## Serveur SSH

```
Host: 77.42.90.102
Port: 41922
User: bruno
Sudo: NOPASSWD configuré pour docker, systemctl, ufw, journalctl
Container DB: krakenbot-db
Repo serveur: ~/apps/kraken-trading-bot
```
