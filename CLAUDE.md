# CLAUDE.md - Guide de Travail

> Ce fichier définit COMMENT travailler sur ce projet, pas QUOI existe. Pour l'état du projet, lis le code. Pour les tâches, voir TODO.md.

## Projet en une phrase

Bot de trading automatisé BTC/USDC sur Kraken : collecte données 24/7, multi-stratégies en parallèle, analyse multi-timeframe, limit orders, déployé sur Hetzner.

---

## Principes d'Architecture

### 2 services séparés
- **Collector** (`python -m krakenbot.collector`) : tourne 24/7, ne jamais le couper. Collecte WebSocket + backfill REST.
- **Trading Bot** (`python -m krakenbot`) : start/stop flexible. Orchestre les stratégies.

Ils communiquent uniquement via la DB (PostgreSQL + TimescaleDB).

### Single process, multi-stratégie
Toutes les stratégies tournent dans un seul processus. Pas de multi-process. Raisons : pas de race condition sur la balance, un seul WebSocket, risk global centralisé. La config vit dans `strategies.yaml` à la racine.

### Risk à 2 niveaux
Toujours vérifier les limites **globales** (toutes stratégies) ET **par stratégie** (via StrategyBudget). Ne jamais bypasser le GlobalRiskManager.

### Limit orders par défaut
- BUY → limit (maker fee 0.16%)
- SELL profit target → limit
- SELL stop-loss, trailing stop, timeout → market (exécution garantie)

Quand un stop-loss se déclenche, **toujours annuler le limit sell** profit target existant d'abord.

### Multi-timeframe
Le MultiTimeframeAnalyzer est une **instance partagée** entre toutes les stratégies. Ne pas en créer plusieurs. Il analyse **6 timeframes** (5m, 15m, 1h, 4h, 1d, 1w) et fournit : EMA (période arbitraire, lazy), RSI, ATR, MACD, Bollinger, ADX, SuperTrend, et un MarketRegime (strong_bear → strong_bull) par timeframe.

### MultiStrategyRouter
En mode multi-stratégie, le `MultiStrategyRouter` est la **seule** BaseStrategy enregistrée dans l'EventBus. Il dispatch les candles vers 7 stratégies internes et applique le `GeminiGlobalRiskManager` (1% rule, ATR SL, crash protector) sur chaque signal BUY avant émission.

### Mode legacy
Si `strategies.yaml` absent ou `enabled: false`, le bot fonctionne exactement comme avant (single strategy depuis .env). Ne jamais casser ce mode.

---

## Conventions de Code

### Absolues
- **Python 3.11+**, async/await partout, jamais de code bloquant
- **Type hints** obligatoires sur toutes les fonctions
- **Decimal** pour tous les montants et prix (jamais float)
- **UTC** pour tous les timestamps
- **structlog** pour le logging (pas print, pas logging stdlib)
- **Imports absolus** : `from krakenbot.core import ...`

### Style
```python
# ✅
async def place_order(pair: str, amount: Decimal, price: Decimal) -> Order:
    """Place un limit order."""

# ❌
def place_order(pair, amount, price):
```

### Naming
- Classes : `PascalCase`
- Fonctions/variables : `snake_case`
- Constantes : `UPPER_SNAKE_CASE`
- Enums : `PascalCase` pour la classe, `UPPER_SNAKE_CASE` pour les valeurs

### Lint (lancer avant chaque commit)
```bash
ruff check . --fix && ruff format .
```

---

## Patterns à Suivre

### Stratégies
Toute nouvelle stratégie **doit** :
- Hériter de `BaseStrategy`
- Implémenter `on_ohlc()`, `generate_signal()`, `get_name()`, `get_config()`
- Accepter `bot_id` et `strategy_params` dans son constructeur
- Persister ses positions dans la table `open_positions` (pas juste en mémoire)
- Avoir son propre `bot_id` unique dans `bot_state`
- Logger chaque signal avec metadata complètes (régime, seuils, raison)
- Mettre `order_type` ("limit" ou "market") dans `signal.metadata`
- Mettre `position_size_multiplier` dans `signal.metadata`

### Indicateurs
- Réutiliser les indicateurs existants dans `indicators/` (RSI, MACD, BB, EMA, ATR, ADX, SuperTrend)
- Accéder via `MultiTimeframeAnalyzer` : `get_ema(period, tf)`, `get_rsi(period, tf)`, `get_atr(period, tf)`, `get_adx(tf)`, `get_supertrend(tf, period, mult)`, etc.
- Ne pas les réimplémenter
- Nouveaux indicateurs : même interface (méthode `update()` incrémentale)

### EventBus
Le flux est : `WebSocket → MARKET_OHLC → Strategy → TRADE_SIGNAL → ExecutionEngine → TRADE_ORDER_FILLED → Strategy.on_trade_filled()`

Chaque stratégie filtre par `bot_id` dans `on_trade_filled`, pas par nom de stratégie.

### DB
- Déduplication OHLC via clé composite `(timestamp, pair, interval)` + `session.merge()`
- Migrations via Alembic : `alembic revision --autogenerate -m "description"`
- Tables principales : `market_data_ohlc` (hypertable), `trades_history`, `bot_state`, `open_positions`, `orders`

---

## Règles

### Sécurité
- JAMAIS de secrets dans le code ou les commits
- JAMAIS de commit de `.env`
- Config stratégies dans `strategies.yaml` (pas de secrets dedans)
- Mode live requiert `TRADING_CONFIRM_LIVE=yes` explicite

### Fiabilité
- Toujours gérer la réconciliation au démarrage (positions DB vs balance Kraken)
- Le collector ne doit JAMAIS être interrompu — c'est la source de données
- Les limit orders expirent — le OrderManager nettoie les ordres stale
- Stop-loss en market order, jamais en limit (exécution garantie critique)

### Développement
- Committer après chaque composant fonctionnel
- Tester en mode paper avant live
- Ne pas casser les stratégies existantes quand on en ajoute une nouvelle
- Le backtest doit supporter toutes les stratégies (`--strategy adaptive|capitulation|multi_strategy_router|...`)

---

## Commandes

```bash
# Dev
poetry install
poetry run python -m krakenbot.collector    # Collector 24/7
poetry run python -m krakenbot              # Trading bot

# Tests & Lint
poetry run pytest
poetry run ruff check . --fix && ruff format .
poetry run mypy src/

# Dashboard (tunnel SSH depuis Mac)
ssh -L 5432:localhost:5432 bruno@<IP> -N &
poetry run python scripts/dashboard.py      # http://localhost:8050

# Backtest
poetry run python scripts/backtest.py --strategy adaptive --days 30 --interval 5
poetry run python scripts/backtest_grid.py --quick --days 7

# Déploiement
sudo systemctl status krakenbot
sudo journalctl -u krakenbot -f
```

---

## Vision Long Terme

1. ✅ Bot live multi-stratégie avec limit orders
2. 🚧 Alertes Telegram/Discord, monitoring avancé
3. 📋 Multi-pair (ETH/USDC, SOL/USDC)
4. 📋 Strategy registry dynamique (ajouter une strat sans redémarrer)
5. 🔮 ML : features engineering sur les données accumulées
6. 🔮 RL : agent qui apprend à optimiser les seuils en continu
