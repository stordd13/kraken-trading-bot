# CLAUDE.md — Routeur pour agents

> Ce fichier dit **où lire**. Le détail vit dans `skills/` et `docs/`, chargés à la demande.
> État du projet → `PROJECT_CONTEXT.md` · Où est quoi dans le code → `docs/CODE_MAP.md` · Phases → `ROADMAP.md`.

## Le projet en deux phrases

Bot de trading spot automatisé multi-pair (BTC/ETH/SOL contre USDC) sur **Bybit EU**, 8 stratégies
orchestrées par un router avec risk management centralisé, déployé sur Hetzner (services stoppés
jusqu'à B2/B3). Le connecteur Bybit est en cours (B1–B3) ; les backtests tournent sur les 8.7M rows
Binance déjà en DB avec le modèle de fees Bybit (maker 0.10 % / taker 0.25 %).

## Routage : type de tâche → fichier à lire

| Tâche | Lire |
|---|---|
| DB : connexion, query, migration, backup/restore TimescaleDB | `skills/database.md` |
| Backtest (unitaire, P6, P7 grid search, métriques, fees) | `skills/backtest.md` |
| Nouvelle stratégie ou modification d'une stratégie | `skills/new_strategy.md` |
| Risk management (sizing, SL ATR, types d'ordres) | `skills/risk_management.md` |
| Serveur Hetzner : SSH, systemd, tmux, réactivation | `skills/deployment.md` |
| Connecteur / API Bybit EU (B1–B3) | `skills/bybit.md` |
| Données historiques Binance (base de backtest) | `skills/binance_import.md` |
| Bug, tunnel SSH, migration qui hang | `skills/troubleshooting.md` |
| Flux d'un trade, multi-pair, conventions de code | `docs/architecture.md` |
| Localiser un module / une fonction | `docs/CODE_MAP.md` |
| Résultats de backtests (quoi est où, verdicts) | `results/INDEX.md` |

## Règles d'or (absolues)

1. **Lire le code existant** (et le skill concerné) avant d'écrire.
2. **Decimal** pour tous les prix et montants, jamais float. **UTC** pour tous les timestamps.
3. **structlog** pour les logs (jamais print / logging stdlib). Imports absolus `from krakenbot...`.
4. **Filtre exchange via `settings.exchange_name`**, jamais de littéral `'binance'` / `'bybit'` dans
   le code de production. Seuls les backtests lisent explicitement `exchange='binance'`.
5. **Batcher les inserts SQL** (1000 rows par batch, jamais > 5000 par execute).
6. **Ne jamais réimporter** des données déjà en DB : vérifier d'abord (`skills/database.md`).
7. **Paper avant live**, 3+ ans de backtest avant paper. **B4** (re-backtests avec fees Bybit) est un
   prérequis absolu avant tout paper trading Bybit.
8. **Fichiers protégés** : `MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine` —
   pas de modification sans raison explicite et review humain. Ne jamais bypasser le `GlobalRiskManager`.
9. **Jamais de commit** de `.env`, credentials ou API keys.
10. **Jamais de merge sur `main`** sans passer par `dev`. `pytest` + `ruff` verts avant tout commit.
11. **Pas de migration Alembic lourde via le tunnel SSH** : sur le serveur, services stoppés.

## Commandes essentielles

```bash
poetry run pytest -q                                        # tests (avant tout commit)
poetry run ruff check . --fix && poetry run ruff format .   # lint + format
poetry run python -m krakenbot                              # bot (paper) — connecteur Bybit : B1
poetry run python -m krakenbot.collector                    # collector — Bybit WS : B2
poetry run python scripts/backtest.py --strategy grok_supertrend_4h --pair BTC/USDC \
    --exchange binance --days 1095 --capital 1000           # backtest unitaire
poetry run python scripts/run_p6_backtests.py --workers 8   # 24 combos P6 (resume auto, --serial, --force)
poetry run python scripts/run_p7_grid_search.py --phase 1 --workers 8   # P7 : --phase 1 | 2 | report
poetry run python scripts/dashboard.py                      # dashboard Dash
```

`--exchange binance` désigne la **source de données** (8.7M rows Binance), pas l'exchange cible.

## Conventions git

- Branche de travail `feat/<phase>-<sujet>` depuis `dev`, PR vers `dev`.
- Commits atomiques, préfixes `feat|fix|refactor|docs|chore|test(scope)`.
- Régénérer `docs/CODE_MAP.md` à chaque merge sur `dev` (méthode dans son en-tête).
