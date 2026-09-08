# AGENT P7 — Optimisation paramétrique des stratégies P6 retenues

> Durée estimée : 1-2 jours de code + ~3h de run + analyse
> Branche : `feat/p7-parameter-optimization` créée depuis `dev`

---

## Contexte projet

Lire AVANT de commencer :
- `PROJECT_CONTEXT.md` : état global du projet
- `CLAUDE.md` : conventions et patterns
- `skills/backtest.md` : méthodologie backtest
- `skills/troubleshooting.md` : pièges connus

P6.5 a validé 4 stratégies avec un edge potentiel (mais aucune n'atteint les critères stricts à 1k USDC + 1% risk). P6.7 a parallélisé le backtester (speedup 3×). P7 va optimiser les paramètres de ces stratégies pour identifier les configurations viables.

---

## Objectif

Pour chaque stratégie retenue, faire un grid search ciblé sur 2-3 paramètres clés, identifier les top configurations, puis valider via walk-forward avant de proposer une activation paper.

**Stratégies à optimiser** :
1. **SuperTrend 4h** sur BTC/USDC, ETH/USDC, SOL/USDC (3 combos)
2. **Grid ATR V4** sur BTC/USDC, SOL/USDC (2 combos)
3. **DCA Adaptive Weekly** sur BTC/USDC (1 combo)
4. **Donchian Breakout 4h** sur SOL/USDC (1 combo, à watcher)

---

## Méthodologie

### Phase 1 — Grid search cross-validate (rapide, identifie les candidats)

Pour chaque combinaison stratégie × paire :
1. Générer la grille de paramètres (définie ci-dessous)
2. Pour chaque combinaison de paramètres, lancer un backtest avec cross-validation 70/30
3. Sauvegarder toutes les métriques par configuration
4. Trier par Sharpe out-of-sample décroissant
5. Garder les **5 meilleures configurations** par combo

### Phase 2 — Walk-forward sur les top 5

Pour chacune des 5 configurations retenues par combo :
1. Walk-forward 8 fenêtres : train 12 mois / test 3 mois / avance 3 mois
2. Calculer la consistance : combien de fenêtres test ont un Sharpe positif
3. Calculer le Sharpe moyen et la stabilité (std des Sharpe sur les 8 fenêtres)

### Phase 3 — Sélection finale

Appliquer les critères révisés (voir section "Critères de sélection") sur les résultats walk-forward.

---

## Grilles de paramètres

### SuperTrend 4h (60 backtests phase 1 = 20 × 3 paires)

```python
SUPERTREND_GRID = {
    "atr_period": [7, 10, 14, 20],
    "atr_multiplier": [2.0, 2.5, 3.0, 3.5, 4.0],
}
# 4 × 5 = 20 combinaisons par paire
```

### Grid ATR V4 (64 backtests phase 1 = 32 × 2 paires)

```python
GRID_ATR_GRID = {
    "min_spacing_pct": [1.0, 1.5, 2.0, 2.5],
    "atr_multiplier_spacing": [1.5, 2.0, 2.5, 3.0],
    "bear_protection_enabled": [False, True],  # NOUVEAU : à implémenter
}
# 4 × 4 × 2 = 32 combinaisons par paire
```

**Note bear protection** : à implémenter dans la stratégie comme paramètre on/off. Si activé, pause les achats grid quand `regime("1d") == "strong_bear"`. Reprend automatiquement quand le régime change.

### DCA Adaptive Weekly (48 backtests phase 1 = 48 × 1 paire BTC)

```python
DCA_GRID = {
    "boost_multiplier": [1.5, 2.0, 2.5, 3.0],
    "reduction_multiplier": [0.3, 0.5, 0.7, 1.0],  # 1.0 = pas de réduction
    "rsi_oversold_threshold": [25, 30, 35],
}
# 4 × 4 × 3 = 48 combinaisons sur BTC uniquement
```

### Donchian Breakout 4h (8 backtests phase 1 = 8 × 1 paire SOL)

```python
DONCHIAN_GRID = {
    "channel_period": [10, 15, 20, 30],
    "breakout_confirmation": ["close", "high_low"],  # close = breakout sur close, high_low = sur extremes
}
# 4 × 2 = 8 combinaisons sur SOL uniquement
```

**Total phase 1 : 180 backtests**
**Total phase 2 (top 5 × 4 strats × 8 fenêtres) : 160 backtests**
**Total P7 : ~340 backtests**

Avec speedup 3× : environ 2-3h de run.

---

## Critères de sélection finale (appliqués sur résultats walk-forward)

Une configuration est retenue pour le paper trading si elle satisfait TOUS ces critères :

1. **Sharpe out-of-sample moyen > 0.4** (moyenne sur les 8 fenêtres walk-forward)
2. **Profit Factor moyen > 1.3**
3. **Max Drawdown global < 30%**
4. **Minimum 20 trades sur le test set** moyen (sauf DCA qui peut avoir moins)
5. **Consistance walk-forward** : au moins 5/8 fenêtres avec Sharpe positif
6. **Anti-overfitting** : ratio Sharpe moyen test / Sharpe moyen train > 0.5
7. **Battre le benchmark** : Sharpe moyen > Sharpe du Buy & Hold OU du DCA fixe sur la même paire (pas obligation des deux)

Si une stratégie a 0 configuration qui passe ces critères → on l'abandonne définitivement.

Si une stratégie a plusieurs configurations qui passent → on garde la meilleure (Sharpe moyen le plus élevé avec stabilité acceptable).

---

## Architecture technique

### Script principal : `scripts/run_p7_grid_search.py`

Nouveau script qui réutilise `scripts/run_p6_backtests.py` (multiprocessing déjà en place de P6.7).

Structure :

```
scripts/run_p7_grid_search.py
├── parse_args()                          # --strategy, --pair, --phase, --workers, --force
├── build_grid_jobs(strategy, pair)       # génère toutes les combinaisons params
├── run_phase_1_cross_validate(jobs)      # réutilise multiprocessing de P6.7
├── select_top_5(results_per_combo)       # tri par Sharpe OOS
├── run_phase_2_walk_forward(top_5_per_combo)
├── apply_selection_criteria(wf_results)
└── generate_report(final_results)
```

### Réutilisation du code existant

- **Multiprocessing** : utiliser le pool de `run_p6_backtests.py` (factorisé en module si besoin)
- **BacktestEngine / GridBacktester** : aucune modification
- **Stratégies** : seule modification autorisée = ajouter `bear_protection_enabled` à Grid ATR V4 comme paramètre

### Sauvegarde des résultats

Fichiers générés (tous dans `results/`) :

- `P7_phase1_cross_validate.json` : tous les résultats phase 1 (180 backtests)
- `P7_phase2_walk_forward.json` : résultats walk-forward sur les top 5 (160 backtests)
- `P7_final_selection.json` : configurations qui passent les critères + détail
- `P7_optimization_report.md` : rapport synthèse avec tableaux et recommandations

Format JSON cohérent avec ceux de P6 pour faciliter le diff et la comparaison.

---

## Implémentation par phases

### Phase A — Setup et bear protection Grid (30-60 min)

1. Créer la branche `feat/p7-parameter-optimization` depuis `dev`
2. Implémenter `bear_protection_enabled` dans `GrokGridATRAdaptiveV4` :
   - Nouveau param dans `__init__`
   - Dans `generate_signal`, si `bear_protection_enabled and regime("1d") == "strong_bear"` → return None (pas de nouveau buy)
   - Les positions existantes continuent normalement (pas de panic sell)
3. Tests unitaires pour cette modification
4. Commit : `feat(strategy): add optional bear protection to grid_atr_v4`

### Phase B — Script grid search phase 1 (2-3h)

1. Créer `scripts/run_p7_grid_search.py`
2. Implémenter `build_grid_jobs()` qui prend une stratégie + paire et génère tous les jobs
3. Factoriser le pool multiprocessing de `run_p6_backtests.py` dans un module commun si nécessaire
4. Implémenter la sauvegarde progressive (réutiliser l'atomic save de P6.7)
5. Tests unitaires sur le générateur de grille
6. Commit : `feat(scripts): add P7 grid search phase 1 with multiprocessing`

### Phase C — Phase 2 walk-forward (2-3h)

1. Implémenter le walk-forward 8 fenêtres dans le BacktestEngine OU dans le script P7 selon ce qui est plus propre (préférer le script P7 pour ne pas toucher au BacktestEngine)
2. Implémenter `select_top_5()` qui filtre par Sharpe OOS décroissant
3. Implémenter `run_phase_2_walk_forward()` qui prend les top 5 et lance le walk-forward
4. Tests unitaires sur la logique de sélection
5. Commit : `feat(scripts): add P7 walk-forward validation on top configurations`

### Phase D — Critères de sélection et rapport (1-2h)

1. Implémenter `apply_selection_criteria()` qui filtre les survivants des survivants
2. Implémenter `generate_report()` qui produit `results/P7_optimization_report.md` avec :
   - Synthèse exécutive (combien de configs survivent par stratégie)
   - Tableau des 5 meilleures configurations par combo
   - Tableau final des configurations retenues pour paper trading
   - Comparaison avec les résultats P6 (avant optimisation vs après)
   - Recommandations pour P8 (paper trading)
3. Commit : `feat(scripts): add P7 selection criteria and report generation`

### Phase E — Run et validation (~3h de compute, 1h d'analyse)

1. Lancer phase 1 sur la machine locale : `poetry run python scripts/run_p7_grid_search.py --phase 1 --workers 8`
2. Vérifier les résultats intermédiaires
3. Lancer phase 2 : `poetry run python scripts/run_p7_grid_search.py --phase 2 --workers 8`
4. Générer le rapport final
5. Commit : `docs: add P7 optimization report and final selection`

---

## Commits attendus (ordre)

1. `feat(strategy): add optional bear protection to grid_atr_v4`
2. `test(strategy): add tests for grid_atr_v4 bear protection`
3. `feat(scripts): add P7 grid search phase 1 with multiprocessing`
4. `test(scripts): add tests for P7 grid job generation`
5. `feat(scripts): add P7 walk-forward validation on top configurations`
6. `feat(scripts): add P7 selection criteria and report generation`
7. `docs: update CLAUDE.md and skills/backtest.md for P7`
8. `docs: add P7 optimization report and final selection`

---

## Critères de done

- [ ] `pytest -q` vert (nouveaux tests pour bear protection + générateur grille)
- [ ] Phase 1 lancée avec succès (180 backtests, JSON complet)
- [ ] Phase 2 lancée avec succès (walk-forward sur top 5)
- [ ] Rapport `results/P7_optimization_report.md` généré avec tableaux clairs
- [ ] Sélection finale : pour chaque stratégie, soit 1 configuration retenue, soit décision claire d'abandon documentée
- [ ] Aucune modification du BacktestEngine ou GridBacktester
- [ ] Aucune modification des autres stratégies (juste bear protection sur Grid)
- [ ] Pas de nouvelle dépendance

---

## Règles importantes

1. **Ne pas modifier les stratégies sauf bear protection sur Grid ATR V4**. Si tu identifies un autre bug, documente-le dans `results/P7_additional_findings.md` et fix sur une branche séparée.

2. **Réutiliser le multiprocessing de P6.7**. Si besoin de factoriser dans un module commun, fais-le proprement avec tests.

3. **Sauvegarde progressive obligatoire**. Le script doit pouvoir être interrompu et relancé sans tout recommencer.

4. **Pas de grid search élargi**. Reste sur les paramètres et ranges spécifiés. L'élargissement viendra dans une éventuelle P7.5 selon les résultats.

5. **Walk-forward sur top 5 uniquement**, pas sur les 30+ configurations de phase 1. Sinon explosion combinatoire.

6. **Si une stratégie ne donne aucun survivant après P7**, c'est OK. Documente-le clairement et passe à la suivante. Ne pas relâcher les critères pour faire passer artificiellement une stratégie.

---

## Format des résultats

### P7_phase1_cross_validate.json

```json
{
  "grok_supertrend_4h_BTC_USDC": {
    "strategy": "grok_supertrend_4h",
    "pair": "BTC/USDC",
    "exchange": "binance",
    "configurations": [
      {
        "params": {"atr_period": 14, "atr_multiplier": 3.0},
        "train": {...metrics...},
        "test": {...metrics...},
        "all": {...metrics...}
      },
      ...
    ]
  },
  ...
}
```

### P7_phase2_walk_forward.json

```json
{
  "grok_supertrend_4h_BTC_USDC": {
    "top_5_configurations": [
      {
        "params": {...},
        "walk_forward": {
          "windows": [
            {"window": 1, "train_start": "...", "test_start": "...", "metrics": {...}},
            ...
          ],
          "consistency": 6,
          "mean_sharpe": 0.45,
          "std_sharpe": 0.15
        }
      },
      ...
    ]
  }
}
```

### P7_final_selection.json

```json
{
  "selected_for_paper": [
    {
      "strategy": "grok_supertrend_4h",
      "pair": "BTC/USDC",
      "params": {...},
      "mean_sharpe_oos": 0.52,
      "mean_profit_factor": 1.65,
      "consistency": 6,
      "beats_benchmark": "buy_and_hold",
      "rationale": "..."
    }
  ],
  "abandoned": [
    {
      "strategy": "donchian_breakout_4h",
      "pair": "SOL/USDC",
      "reason": "No configuration passed Sharpe > 0.4 criterion (best was 0.31)"
    }
  ]
}
```

---

## Validation manuelle après le run

Quand le run est fini, vérifier :

1. **Nombre de backtests effectifs** : phase 1 doit avoir ~180 entrées, phase 2 doit avoir 20 entrées (top 5 × 4 stratégies)
2. **Cohérence des chiffres** : un Sharpe > 3 ou un return > 500% est suspect, vérifier le backtest individuel
3. **Détection d'overfitting** : pour chaque configuration retenue, ratio test/train doit être > 0.5
4. **Comparaison avec P6** : la meilleure config P7 doit être strictement meilleure que la version P6 (sinon le grid search n'a rien apporté)

---

## Contexte projet à charger en début de session

```bash
# Lecture obligatoire au démarrage
cat PROJECT_CONTEXT.md
cat CLAUDE.md
cat skills/backtest.md
cat skills/troubleshooting.md
cat results/P6_backtest_report_v2.md  # résultats P6.5 finaux
```

Bonne chance.
