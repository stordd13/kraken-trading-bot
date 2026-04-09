# Kraken Futures Integration — Phase 2 Results

**Date** : 2026-04-08

## Audit

- **ccxt version** : 4.5.34
- **Module** : `ccxt.krakenfutures` (distinct de `ccxt.kraken`)
- Toutes les fonctionnalites requises supportees (swap, funding rates, leverage, positions, sandbox)
- **Decision** : utiliser ccxt.krakenfutures (coherence avec le Spot)
- Voir [kraken_futures_audit.md](kraken_futures_audit.md) pour les details

## Interfaces creees

### BaseExchangePerps (`src/krakenbot/connectors/base_perps.py`)
- ABC pour les exchanges perpetual futures
- 15 methodes abstraites : balance, orders, positions, funding, leverage, pairs, lifecycle
- Tous les montants en `Decimal`

### KrakenFuturesClient (`src/krakenbot/connectors/kraken_futures_rest.py`)
- Implemente `BaseExchangePerps` via `ccxt.async_support.krakenfutures`
- Sandbox mode pour l'environnement demo
- Pair mapping : XBT/USD, ETH/USD, SOL/USD (+ alias BTC/USD)
- Leverage cap configurable (defaut 3, max 10)
- Conversion float→Decimal systematique sur toutes les valeurs ccxt

### KrakenFuturesSettings (`src/krakenbot/config/settings.py`)
- `KRAKEN_FUTURES_ENABLED=false` par defaut
- `KRAKEN_FUTURES_DEMO=true` par defaut
- `SecretStr` pour api_key/secret
- Validation credentials en mode live

## Tests

| Suite | Tests | Status |
|-------|-------|--------|
| `test_base_perps.py` | 2 | PASS |
| `test_kraken_futures_rest.py` | 34 | PASS |
| **Suite complete** | **955** | **PASS (1 skipped)** |

### Tests couverts
- Init, properties (name, fees, max_leverage)
- Demo/production sandbox mode
- Pair normalization (forward + reverse, alias, erreur)
- Leverage cap (place_order, set_leverage, < 1)
- Balance (filtrage zero, Decimal)
- Positions (vide, format, liquidation_price null, close when none, all positions filter)
- Funding rate (Decimal, historique)
- Order placement (market, limit, reduce_only)
- Status normalization

## Wiring

- `main.py` : init conditionnel dans `setup()`, cleanup dans `stop()`
- Import lazy (dans le `if`) : zero impact quand `enabled=False`
- `exchange.py` / `build_exchange_rest_client()` : **non modifie** — isolation totale du Spot

## Impact sur le Spot

**ZERO.** Tous les 921 tests pre-existants passent sans modification.
Le module Futures n'est jamais importe ni execute quand `KRAKEN_FUTURES_ENABLED=false`.

## Known Issues

- WebSocket Futures non implemente (differe — REST polling suffit pour le funding rate arb)
- `fetchFundingRate` est "emulated" dans ccxt (pas natif), mais fonctionne

## Prochaines etapes

1. **Phase 4** : Strategie funding rate arbitrage (long spot + short perp quand funding > seuil)
2. **Optionnel** : WebSocket Futures pour mark price temps reel
3. **Test demo** : executer `scripts/test_kraken_futures_demo.py` avec des API keys demo reelles
