# Kraken Futures Integration

## Overview

Module opt-in pour les perpetual futures Kraken, completement separe du Spot.
Utilise `ccxt.krakenfutures` (module distinct de `ccxt.kraken`).

## Setup

1. Activer Kraken Futures sur votre compte Kraken principal
2. Creer des API keys demo : https://demo-futures.kraken.com/settings/api
3. Creer des API keys production : https://futures.kraken.com/settings/api (quand pret)
4. Configurer les variables d'environnement :

```
KRAKEN_FUTURES_ENABLED=true
KRAKEN_FUTURES_API_KEY=xxx
KRAKEN_FUTURES_API_SECRET=yyy
KRAKEN_FUTURES_DEMO=true          # false pour la production
KRAKEN_FUTURES_MAX_LEVERAGE=3     # cap de securite (1-10)
```

## Architecture

```
KrakenRestClient (Spot)          KrakenFuturesClient (Perps)
       |                                  |
  ccxt.kraken                     ccxt.krakenfutures
       |                                  |
  api.kraken.com              futures.kraken.com
```

- Les deux clients sont **completement independants** (API keys, rate limits, balances)
- Le Spot continue de fonctionner exactement comme avant
- Le Futures n'est charge que si `KRAKEN_FUTURES_ENABLED=true`

## Paires supportees

| Interne | Kraken Futures | Description |
|---------|----------------|-------------|
| XBT/USD | PF_XBTUSD | Bitcoin perpetual (multi-collateral) |
| ETH/USD | PF_ETHUSD | Ethereum perpetual |
| SOL/USD | PF_SOLUSD | Solana perpetual |
| BTC/USD | PF_XBTUSD | Alias pour XBT/USD |

## Fees

| Type | Rate |
|------|------|
| Maker | 0.02% |
| Taker | 0.05% |

A comparer avec le Spot : maker 0.16%, taker 0.26%.

## Testing en Demo

```bash
poetry run python scripts/test_kraken_futures_demo.py
```

Ce script teste (en lecture seule) :
- Balance du compte Futures
- Funding rate actuel XBT/USD
- Historique funding 24h
- Position actuelle
- Toutes les positions

## Leverage

- Cap de securite configurable via `KRAKEN_FUTURES_MAX_LEVERAGE` (defaut: 3)
- Maximum autorise : 10 (validation Pydantic)
- Verifie a chaque `place_perp_order()` et `set_leverage()`
- Kraken Futures supporte jusqu'a 50x, mais on cap volontairement

## Production Checklist

- [ ] Teste 48h+ en demo sans erreurs
- [ ] Max leverage configure (recommande : 3)
- [ ] API keys restreintes par IP (serveur Hetzner)
- [ ] Strategie funding rate arb testee et validee
- [ ] Monitoring/alertes configurees
- [ ] `KRAKEN_FUTURES_DEMO=false` uniquement quand pret

## Prochaines etapes

- **Phase 4** : Strategie funding rate arbitrage (long spot + short perp)
- **Optionnel** : WebSocket Futures pour mark price en temps reel
