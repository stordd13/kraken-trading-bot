# P6.5 — Diagnostic DCA Adaptive vs Fixed (apples-to-apples)

## Pourquoi ce diagnostic

Dans P6, le benchmark DCA fixe (`results/P6_benchmarks.json`) calcule :

    total_return = (final_value - total_invested) / total_invested * 100

alors que le DCA adaptatif (`grok_adaptive_dca_weekly` dans SignalBacktester) calcule :

    total_return = (ending_balance - starting_balance) / starting_balance * 100

De plus :
- Benchmark fixe : capital **illimité** (on ajoute $15/semaine indéfiniment)
- Adaptatif : capital **plafonné à $1000** → épuise l'USDC après ~66 semaines
- Benchmark fixe : mesuré sur **3 ans** ; adaptatif test : **~11 mois** (30% tail)

La comparaison directe 'fixed +23.3% vs adaptive -11%' compare des pommes et des oranges.

## Simulation fixed DCA avec les mêmes contraintes que l'adaptatif

Pour chaque paire, on simule le DCA fixe avec :
- starting capital = $1000 (plafond)
- buys skippés quand `usdc_balance < $15`
- sur la fenêtre **test** seulement (30% queue de P6, ~11 mois)

| Pair | Fixed DCA uncapped (3 ans) | Fixed DCA capped test | Adaptive DCA test | Verdict |
|---|---|---|---|---|
| BTC/USDC | +23.3% (157 buys) | -20.0% (47 buys, 0 skipped) | -11.0% (46 trades) | Adaptive better by +9.0pp |
| ETH/USDC | -15.2% (157 buys) | -20.0% (47 buys, 0 skipped) | -12.7% (47 trades) | Adaptive better by +7.3pp |
| SOL/USDC | -42.6% (118 buys) | -28.5% (47 buys, 0 skipped) | -22.2% (47 trades) | Adaptive better by +6.3pp |

## Interprétation

La bonne comparaison est **fixed capped test vs adaptive test** — même capital,
même contrainte, même fenêtre. Le benchmark uncapped sert uniquement de sanity
check (doit matcher `results/P6_benchmarks.json`).

### Verdict par paire

- BTC/USDC: Adaptive better by +9.0pp
- ETH/USDC: Adaptive better by +7.3pp
- SOL/USDC: Adaptive better by +6.3pp

### Quel est le bug (s'il y en a un) ?

Si adaptive ~= fixed capped : **pas de bug**. Le mismatch apparent avec le
benchmark uncapped est un artefact de méthodologie, pas de logique.

Si adaptive << fixed capped : la logique adaptive (boost RSI<30, reduction
strong_bull) dégrade la performance. À investiguer stratégie par stratégie.

## Recommandation

Si le verdict est 'similar', accepter le DCA adaptatif et **utiliser la méthodologie
fixed capped comme benchmark officiel pour P7** au lieu de l'uncapped.

Ajouter une clé `dca_fixed_capped` à `results/P6_benchmarks.json` pour
comparaisons futures (travail optionnel en P7).

**Aucun fix code en P6.5** pour le DCA — c'est un problème de méthodologie
de benchmark, pas d'un bug dans la stratégie ou le backtester.
