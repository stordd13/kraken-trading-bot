# Skill: Backtest

> Comment lancer des backtests, interpréter les métriques, et éviter les pièges.

## Lancer un backtest

```bash
poetry run python scripts/backtest.py \
    --strategy grok_supertrend_4h \
    --pair BTC/USDC \
    --exchange binance \
    --start-date 2023-04-01 \
    --end-date 2026-04-01 \
    --capital 1000 \
    --cross-validate \
    --save
```

### Paramètres clés

- `--strategy` : nom de la classe (snake_case)
- `--pair` : `BTC/USDC`, `ETH/USDC`, ou `SOL/USDC`
- `--exchange` : `binance` (obligatoire pour utiliser les bonnes données et fees)
- `--cross-validate` : split 70% train / 30% test temporel
- `--save` : sauvegarde les résultats dans `backtest_runs` en DB

### Deux modes

- **SignalBacktester** : pour les stratégies signal-based (SuperTrend, EMA Cross, Donchian, Scalping, etc.)
- **GridBacktester** : pour la grid (GrokGridATRAdaptiveV4)

Le script détecte automatiquement le mode selon la stratégie.

## Fees Binance (CRITIQUE)

Le compte de production a le BNB discount activé.

| Type | Fee |
|---|---|
| Maker (limit) | 0.075% |
| Taker (market) | 0.075% |
| Spread simulé | 0.02% |
| Slippage simulé | 0.01% |

Round-trip réaliste : ~0.18%.

**Vérifier que le backtest utilise les fees Binance**, pas Kraken. Si tu vois 0.16%/0.26% dans les logs, c'est les fees Kraken legacy.

## Modèle d'exécution

**Next-bar** : signal sur candle N → exécution à l'open de candle N+1. Ceci évite le look-ahead bias.

## Métriques et comment les interpréter

### Métriques de qualité de la stratégie (indépendantes du capital)

| Métrique | Bon | Excellent | Red flag |
|---|---|---|---|
| Profit Factor | > 1.5 | > 2.0 | < 1.0 (perdant) |
| Win Rate | > 40% | > 55% | < 25% |
| Avg Win / Avg Loss | > 1.5 | > 2.5 | < 0.5 |

### Métriques de performance (dépendent du capital et du sizing)

| Métrique | Seuil P6 | Note |
|---|---|---|
| Sharpe annualisé | > 1.0 | Avec 1k USDC et 1% risk, le Sharpe est artificiellement bas |
| Sortino | > 1.5 | Comme Sharpe mais ne pénalise que la downside vol |
| Max Drawdown | < 25% | En % du capital |
| Calmar | > 0.5 | Return annualisé / max drawdown |

### ATTENTION — Piège du sizing

Avec 1000 USDC et la règle 1% de risk, les positions sont minuscules (~10-25 USDC par trade). Résultat : les returns absolus et le Sharpe sont très bas **même si la stratégie a un vrai edge**.

Pour évaluer la qualité réelle d'une stratégie, regarde le **Profit Factor** et le **ratio Avg Win / Avg Loss** qui sont indépendants de la taille des positions. Un PF de 1.8 est excellent quel que soit le capital.

### Métriques spécifiques à la grid

La grid a des particularités :
- `win_rate: 1.0` est normal (chaque paire complétée est un win)
- `profit_factor: 0.0` est un bug de calcul (division par 0 si 0 losing trades)
- Les **positions ouvertes en fin de backtest** créent des pertes non réalisées qui tirent le return vers le bas. Ce n'est pas un bug de la stratégie, c'est le design de la grid.
- Regarder plutôt : nombre de paires complétées, profit par paire vs fees, comportement en bear vs bull.

## Cross-validation

Le flag `--cross-validate` split temporellement : 70% premiers jours = train, 30% derniers jours = test.

### Interpréter les résultats train vs test

| Situation | Diagnostic |
|---|---|
| Train bon, test bon | Stratégie robuste, pas d'overfitting |
| Train excellent, test mauvais | **Overfitting** — la stratégie a mémorisé le passé |
| Train moyen, test meilleur | Bon signe — la stratégie généralise |
| Train et test mauvais | Stratégie ne marche pas, à abandonner |

Critère de cohérence : `test_sharpe / train_sharpe > 0.5`. En dessous, overfitting probable.

## Walk-forward

Plus rigoureux que le cross-validate simple. Fenêtre glissante :
- Train : 12 mois
- Test : 3 mois suivants
- Avance : 3 mois
- Sur 3 ans : 8 fenêtres

**Consistency score** : combien de fenêtres test ont un PF > 1.0. Si < 50% (moins de 4/8), la stratégie est instable temporellement.

## Benchmarks de comparaison

Toute stratégie doit battre au moins un des deux :
1. **Buy and Hold** de la même paire sur la même période
2. **DCA fixe** (15 USDC chaque lundi)

Si une stratégie ne bat ni l'un ni l'autre, elle ne sert à rien.

## Pièges courants

1. **Oublier les fees** → résultats trop optimistes
2. **Look-ahead bias** → le backtest "voit" le futur. Toujours next-bar execution.
3. **Survivorship bias** → ne tester que les paires qui ont survécu
4. **Overfitting** → toujours cross-validate, jamais optimiser sur le test set
5. **Période non représentative** → toujours tester sur au moins 3 ans incluant bull ET bear
6. **SOL commence en sept 2021** → la période commune aux 3 paires est 2021-09 à aujourd'hui
