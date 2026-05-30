# Skill: Backtest

> Comment lancer des backtests, interpréter les métriques, et éviter les pièges.

## Lancer les 24 backtests P6 en parallèle

Pour (re)lancer toute la campagne P6 (8 stratégies × 3 paires), utiliser le runner
parallélisé. Il partage les 24 jobs sur un `multiprocessing.Pool` (spawn context), chaque
worker ouvre sa propre connexion DB et exécute train + test + all séquentiellement.

```bash
# Parallèle (par défaut), worker count auto-détecté
poetry run python scripts/run_p6_backtests.py

# Explicite
poetry run python scripts/run_p6_backtests.py --workers 8

# Resume automatique : relancer sans --force → combos déjà faits sont skippés
poetry run python scripts/run_p6_backtests.py

# Force re-run
poetry run python scripts/run_p6_backtests.py --force

# Série (debug / gate déterminisme)
poetry run python scripts/run_p6_backtests.py --serial

# Sous-set pour tests rapides (après tri par durée estimée)
poetry run python scripts/run_p6_backtests.py --limit 3

# Timeout par job (défaut 1800s)
poetry run python scripts/run_p6_backtests.py --timeout 600
```

### Monitoring temps réel

```bash
watch -n 2 cat logs/p6_status.json
```

Affiche : `total_jobs`, `completed_jobs`, `running_jobs`, `failed_jobs`, `estimated_remaining_seconds`.

### Détection auto du worker count

Si `--workers` n'est pas fourni : `min(cpu_count - 2, 8, ram_gb // 2 si RAM < 16 GB)`.
La cap à 8 respecte la contrainte RAM (~1 GB par worker pandas) ; la cap RAM protège le
serveur Hetzner 8 GB si jamais on lance en prod.

### Resume et atomic save

Les résultats sont écrits dans `results/P6_phase_d_results.json` après CHAQUE job terminé
via `tempfile + os.replace` atomique POSIX — crash/Ctrl+C ne corrompt pas le fichier. La
sauvegarde est partagée par le main thread et le handler SIGINT via un `threading.Lock`.

### Déterminisme

Deux niveaux de tests dans [tests/test_scripts/test_run_p6_determinism.py](../tests/test_scripts/test_run_p6_determinism.py) :

- **Quick** (3 combos, fenêtre 3 mois) : `pytest tests/test_scripts/test_run_p6_determinism.py -q -m "not slow"`.
  Inclut un gate `test_determinism_serial_vs_serial` qui valide que le backtester LUI-MÊME
  est déterministe (si ce gate échoue, ce n'est pas un bug de P6.7 mais du backtester).
- **Full** (24 combos, fenêtre 3 ans, `@pytest.mark.slow`) : `pytest -m slow` avant de merger
  P6.7 → dev.

Les deux nécessitent le tunnel SSH actif (`nc -zv 127.0.0.1 5433`) — ils se skippent
automatiquement si la DB n'est pas joignable.

---

## Lancer le grid search P7 (optimisation paramétrique)

P7 cible 4 stratégies × paires retenues de P6 et fait un grid search ciblé en
deux phases, puis applique des critères stricts pour décider quelles
configurations méritent un paper trading.

```bash
# Phase 1 — cross-validate 70/30 sur 212 configurations
poetry run python scripts/run_p7_grid_search.py --phase 1 --workers 8 --timeout 3600

# Phase 2 — walk-forward 8 fenêtres × top-5 par combo (≈ 280 backtests)
poetry run python scripts/run_p7_grid_search.py --phase 2 --workers 8 --timeout 3600

# Phase rapport — agrège phase 2, applique 7 critères, écrit le markdown
poetry run python scripts/run_p7_grid_search.py --phase report

# Filtres utiles (smoke tests)
poetry run python scripts/run_p7_grid_search.py --phase 1 \
    --strategy grok_supertrend_4h --pair BTC/USDC --limit 1 --serial
```

### Architecture P7

- [scripts/p7_grids.py](../scripts/p7_grids.py) — définit les 4 grilles
  (SuperTrend, Grid ATR V4, DCA Weekly, Donchian) avec les **noms réels** des
  kwargs du `__init__` des stratégies (pas les aliases de spec).
- [scripts/run_p7_grid_search.py](../scripts/run_p7_grid_search.py) —
  orchestrateur : job builder, multiprocessing pool, atomic save, resume,
  walk-forward windows, top-K, CLI `--phase`.
- [scripts/p7_report.py](../scripts/p7_report.py) — agrégation walk-forward,
  application des 7 critères de sélection, génération du rapport markdown.

### Injection des paramètres custom

Les `BacktestEngine` et `GridBacktester` acceptent un kwarg
`strategy_params_override: dict[str, Any] | None`. Quand fourni, il est mergé
**par-dessus** la config `strategies.yaml` résolue pour la stratégie testée
(le YAML reste la source pour les params non sweepés). Quand `None`, le
comportement est strictement inchangé — gardé par le test
[tests/test_strategies/test_grid_atr_v4_backward_compat.py](../tests/test_strategies/test_grid_atr_v4_backward_compat.py)
qui figé un SHA256 bit-à-bit de la baseline pré-P7.

### Critères de sélection (les 7, tous doivent passer)

1. `mean_sharpe_oos > 0.4`
2. `mean_profit_factor_oos > 1.3`
3. `max_drawdown_global < 30%`
4. `mean_trades_test >= 20` (relaxé à `>= 5` pour DCA)
5. `consistency >= 5/8` fenêtres avec Sharpe positif
6. `mean_sharpe_oos / mean_sharpe_train > 0.5` (anti-overfit)
7. Bat soit Buy & Hold soit DCA fixe en Sharpe (OU permissif)

Benchmarks Sharpe extraits du rapport P6 v2 (1k USDC, fees Binance) :

| Pair | Buy & Hold | DCA fixed |
|---|---|---|
| BTC/USDC | 0.85 | 2.37 |
| ETH/USDC | 0.40 | 2.10 |
| SOL/USDC | 0.31 | 1.93 |

Si une stratégie n'a aucune config qui passe → on l'abandonne, documenté
dans `results/P7_optimization_report.md`.

---

## Lancer un backtest unitaire

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
