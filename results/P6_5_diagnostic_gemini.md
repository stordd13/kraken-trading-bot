# P6.5 — Diagnostic Gemini Pair Filter

## Symptôme

Sur 3 ans de données Binance, les 3 stratégies Gemini ont produit des trades sur BTC/USDC mais **zéro** sur ETH/USDC et SOL/USDC :

| Stratégie | BTC | ETH | SOL |
|---|---|---|---|
| `gemini_retour_moyenne` | 3 | **0** | **0** |
| `gemini_scalping_volatilite` | 213 | **0** | **0** |
| `gemini_suivi_tendance_momentum` | 12 | **0** | **0** |

Statistiquement impossible sur des séries identiques → bug.

## Trace du bug (4 étapes)

### Étape 1 — YAML hardcode
`strategies.yaml:223,239,251` contient un `pair: BTC/USDC` pour chacune des 3 stratégies Gemini sous `multi_strategy_router.params.strategies`.

```yaml
gemini_scalping_volatilite:
  active: false
  bot_id: scalping_vol
  params:
    pair: BTC/USDC        # ← hardcode
    rsi_period: 7
    ...
```

### Étape 2 — Priorité YAML > settings
`src/krakenbot/strategies/base.py:187` — la propriété `effective_pair` :

```python
@property
def effective_pair(self) -> str:
    pair = self.strategy_params.get("pair") or self.settings.trading.pair
    return pair.replace("XBT/", "BTC/")
```

Quand `strategy_params["pair"]` existe (depuis YAML), il **écrase** `settings.trading.pair`.

### Étape 3 — Le backtest engine met settings mais pas params
`scripts/backtest.py:1130` :
```python
self.settings.trading.pair = pair   # ← ex. "ETH/USDC"
```
Cette affectation est correcte, mais `_load_inner_strategy_params()` retourne ensuite les params YAML intacts (incluant `pair: BTC/USDC`) au constructeur de la stratégie. Le constructeur fait `self.pair = self.effective_pair` → lit `"BTC/USDC"` depuis params → `self.pair = "BTC/USDC"`.

### Étape 4 — Filtre candle rejette tout
Chaque stratégie Gemini filtre dès `on_ohlc` :

- `gemini_scalping_volatilite.py:139` : `if ohlc_data.get("pair") != self.pair: return`
- `gemini_retour_moyenne.py:133` : idem
- `gemini_suivi_tendance_momentum.py:136` : idem

Quand le backtest tourne sur ETH/USDC, les candles arrivent avec `pair="ETH/USDC"` mais `self.pair="BTC/USDC"` → rejetées silencieusement → aucun `generate_signal` → 0 trades.

Les stratégies **Grok** n'ont pas ce filtre en entrée de `on_ohlc`, donc elles fonctionnaient (avec un `self.pair` cosmétiquement incorrect, visible dans les logs).

## Fix

Un helper module-level dans `scripts/backtest.py` injecte `pair` dans tous les `strategy_params` chargés depuis YAML, avant de les passer au constructeur de la stratégie :

```python
def _override_pair_in_params(
    params: dict[str, Any] | None,
    pair: str,
) -> dict[str, Any]:
    merged = dict(params or {})
    merged["pair"] = pair
    return merged
```

Appliqué aux **14 call sites** dans `BacktestEngine.run()` (lignes 1145, 1158, 1171, 1182, 1199, 1213, 1229, 1248, 1262, 1278, 1294, 1313, 1329, 1343) et dans `GridBacktester.run()` (override direct de `self._strategy_params` après `self.settings.trading.pair = pair`).

Approche choisie : fix au niveau engine plutôt que dans le YAML ou les stratégies. Avantages :
- Aucune modification du YAML (config prod préservée)
- Aucune modification des stratégies (règle "pas de modif strat")
- Robuste si un futur ajout YAML oublie de retirer `pair:`

## Vérification

Tests unitaires (`tests/test_backtest_pair_override.py`, 6 tests) :
- `test_override_pair_in_params_with_dict` — mutation non destructive
- `test_override_pair_in_params_with_none` — injection propre
- `test_override_pair_in_params_empty_dict` — injection propre
- `test_override_pair_in_params_preserves_extra_keys` — autres clés conservées
- `test_gemini_strategy_reads_overridden_pair` — GeminiScalpingVolatilite instancié avec override ETH/USDC → `strategy.pair == "ETH/USDC"` ✓
- `test_grok_supertrend_reads_overridden_pair` — idem pour Grok avec SOL/USDC ✓

```
poetry run pytest tests/test_backtest_pair_override.py -v     # 6 passed
poetry run pytest tests/test_backtest.py -v                   # 11 passed (régression)
```

Re-run Phase D (24 backtests) attendu : Gemini sur ETH/SOL doivent maintenant produire des trades > 0.

## Commit

`fix(backtest): override hardcoded pair in strategy_params for multi-pair backtests`
