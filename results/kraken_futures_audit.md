# Kraken Futures Library Audit

**Date**: 2026-04-08
**ccxt version**: 4.5.34

## 1. ccxt.krakenfutures Capabilities

| Feature | Supported | Notes |
|---------|-----------|-------|
| `swap` | True | Perpetual futures |
| `fetchFundingRate` | emulated | Emulated from other endpoints |
| `fetchFundingRateHistory` | True | Native |
| `setLeverage` | True | Native |
| `fetchPositions` | True | Native |
| `fetchBalance` | True | Separate from Spot balance |
| `createMarketOrder` | True | Native |
| `createLimitOrder` | True | Native |
| `fetchOpenOrders` | True | Native |
| `cancelOrder` | True | Native |
| `sandbox` | True | demo-futures.kraken.com |

### Sandbox/Demo URLs

```
public:  https://demo-futures.kraken.com/derivatives/api/
private: https://demo-futures.kraken.com/derivatives/api/
charts:  https://demo-futures.kraken.com/api/charts/
history: https://demo-futures.kraken.com/api/history/
```

Activated via `exchange.set_sandbox_mode(True)`.

## 2. Library Decision

**Decision: utiliser `ccxt.krakenfutures`** (module distinct de `ccxt.kraken`).

Raisons :
- Le projet utilise deja ccxt 4.5.34 pour le Spot
- Toutes les fonctionnalites requises sont supportees
- Sandbox mode natif pour le demo environment
- Pas besoin d'ajouter une dependance supplementaire (python-kraken-sdk)

## 3. Differences cles vs Spot

| Aspect | ccxt.kraken (Spot) | ccxt.krakenfutures |
|--------|--------------------|--------------------|
| Module Python | `ccxt.kraken` | `ccxt.krakenfutures` |
| API Endpoint | api.kraken.com | futures.kraken.com |
| Demo env | N/A | demo-futures.kraken.com |
| API keys | Spot keys | Keys Futures separees |
| Fees | 0.16% / 0.26% | 0.02% / 0.05% |
| Symbols | XBT/USDC | PF_XBTUSD |
| Rate limit | Separe | Separe |

## 4. WebSocket Futures

**Decision: differe a une phase ulterieure.**

Pour le funding rate arbitrage (Phase 4), le REST polling du funding rate toutes les quelques minutes est suffisant. Le WebSocket Futures (`wss://futures.kraken.com/ws/v1`) sera implemente si necessaire pour le tick-level trading.

Subscriptions WS utiles (pour reference future) :
- `ticker` — mark price, funding rate
- `book_snapshot` — order book
- Pour les OHLC, on continue a utiliser le Spot (les candles sont similaires)
