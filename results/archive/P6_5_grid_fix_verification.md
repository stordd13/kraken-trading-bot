# P6.5 — GridBacktester Metrics Fix Verification

## Symptôme

Dans `results/P6_phase_d_results.json` (v1), toutes les lignes `grok_grid_atr_adaptive_v4` ont :
- `win_rate = 1.0` (100% — impossible quand la stratégie perd de l'argent)
- `losing_trades = 0`
- `profit_factor = 0.0` (division-par-zéro masquée)
- `average_holding_time_minutes = 0.0` (jamais calculé)

Exemple : grid_atr sur BTC fait -13.6% de return sur test mais exhibe `win_rate=1.0`, incohérent.

## Causes racines

Dans `scripts/backtest.py` `GridBacktester._calculate_final_metrics` :

### Bug 1 — Survivorship bias (win_rate=1.0)
`total_trades = self.pairs_completed` (ligne 2483). Ne compte **que** les buy→sell complétés. Par design du grid, chaque sell est toujours placé au-dessus de son buy apparié (avec fees couverts), donc tout pair fermé est profitable → `win_rate = 1.0`. Les positions ouvertes en fin de backtest (buy rempli mais sell jamais atteint) sont **ignorées**, même si elles sont en perte non réalisée.

### Bug 2 — Profit factor division-par-zéro
Lignes 2502-2503 :
```python
if total_losses > 0:
    self.metrics.profit_factor = float(total_wins / total_losses)
```
Quand `losing_pnls` est vide (conséquence du bug 1), `profit_factor` reste à `0.0` (valeur par défaut). Devrait être `inf` ou signalé autrement.

### Bug 3 — avg_holding_time non calculé
Le bloc du SignalBacktester (lignes 1020-1034) qui apparie buys/sells par timestamp n'est pas répliqué dans le GridBacktester. Le champ reste à `0.0` par défaut.

## Fix appliqué

### Changements dans `scripts/backtest.py`

1. **Track du prix final** dans la boucle de `run()` : `self._last_close = current_price`, `self._last_timestamp = candle.timestamp` à chaque tick équité.

2. **Expose inner strategy** pour le Grok grid path : `self._strategy_obj = strategy` après `_create_grok_grid_strategy()` (ligne 2345), pour force-closer aussi les positions Grok-side.

3. **Nouvelle méthode `_force_close_open_positions`** : parcourt `self.active_sell_orders` (et `inner_strategy.open_positions` si présent), marque chaque position au prix final, calcule PnL non-réalisée, ajoute un trade SELL virtuel, et incrémente `winning_trades`/`losing_trades` selon le signe du PnL. Somme dans `self.metrics.unrealized_pnl`.

4. **profit_factor avec infinity** :
   ```python
   if total_losses > 0:
       self.metrics.profit_factor = float(total_wins / total_losses)
   elif total_wins > 0:
       self.metrics.profit_factor = float("inf")
   # else: 0.0
   ```

5. **Avg holding time** : bloc copié du SignalBacktester (lignes 1020-1034), matche chaque SELL avec le BUY le plus récent qui le précède.

6. **Nouveau champ `BacktestMetrics.unrealized_pnl`** (+ `to_dict()`) pour tracer l'ampleur des positions force-closed.

## Tests — `tests/test_grid_metrics.py`

| Test | Couvre |
|---|---|
| `test_profit_factor_all_winners_returns_inf` | Bug 2, cas infini |
| `test_profit_factor_no_trades_stays_zero` | Bug 2, cas vide |
| `test_profit_factor_normal_mix` | Bug 2, cas normal (2 wins, 1 loss → 6.0) |
| `test_grid_force_close_adds_losing_trades_at_unfavorable_price` | Bug 1 + unrealized_pnl |
| `test_grid_avg_holding_time_calculated` | Bug 3 |
| `test_force_close_without_open_positions_is_noop` | Cas normal sans positions ouvertes |

Tous passent (`poetry run pytest tests/test_grid_metrics.py -v` → 6 passed).

## Vérification end-to-end

Le re-run des 24 backtests P6 (après Phase 1 + Phase 4) devrait produire :
- `win_rate` < 1.0 pour les grids qui perdent de l'argent
- `profit_factor` cohérent (ni 0.0 systématique, ni inf sauf tous winners)
- `average_holding_time_minutes` > 0
- `unrealized_pnl` reflète les positions force-closed

Commande :
```bash
poetry run python scripts/backtest.py --strategy grok_grid_atr_adaptive_v4 --pair BTC/USDC --exchange binance --days 365
```

## Commit

`fix(backtest): correctly account for open positions and losing trades in grid metrics`
