# Skill: Backtest

> Comment lancer des backtests, interpréter les métriques, et éviter les pièges.

## Contexte post-pivot (septembre 2026)

- **Données** : les 8.7M rows `exchange='binance'` (2021-01 → 2026-06) restent la base de backtest
  (décision B0 : corrélation close 0.999999 Binance vs Bybit, zéro biais). `--exchange binance` désigne
  la **source de données**, pas l'exchange cible. Aucune donnée Bybit en DB avant B3.
- **Fees** : tout ce qui a été produit jusqu'ici (P6, P7 phase 1) l'a été avec les fees Binance
  **0.075 % flat**. Ces résultats ne sont **pas transposables** à Bybit (maker 0.10 / taker 0.25,
  asymétriques) : la machinerie est réutilisable, les classements sont à rejouer en **B4**.
- **Modèle de fees (B4.2)** : `--fees {bybit,binance,kraken}` est **obligatoire** sur `backtest.py`, les
  runners P6/P7 et le walk-forward (absence → exit 2) ; il est indépendant de `--exchange`. Voir
  « Modèle de fees » ci-dessous.
- Résultats existants et verdicts : `results/INDEX.md`.

## Campagne B4.3 (fees Bybit, coûts par paire, plancher d'ordre) — commandes validées au GATE B

Toutes les sorties vont dans de **nouveaux** fichiers `results/B4_*` ; les fichiers P6/P7 historiques (sans clé
`fees`) ne sont jamais réécrits (`--force` interdit dessus). Chaque entrée de résultat enregistre `fees`,
`pair_costs_file`, `pair_costs` (valeurs appliquées à la paire), `min_order_usdc`, `effective_params` (params
réellement utilisés par la stratégie, capturés au runtime — la source de l'alignement `strategies.yaml` en B5) et,
pour le grid, le bloc `liquidation` par segment ; la reprise refuse un fichier produit sous d'autres coûts.

```bash
# Serveur (tmux b4, jamais la session spread). Deux pièges mesurés au lancement P6 (2026-09-15) :
#  - ~/.bashrc fait `set -a; source .env` → tout shell interactif exporte SCHEDULER_PAIRS sans guillemets
#    (JSON invalide) et load_dotenv ne surcharge pas → SettingsError dans les workers : unset AVANT poetry run.
#  - LOG_LEVEL n'est PAS honoré par les scripts (aucun n'appelle configure_logging) : ~190 Mo/min d'INFO
#    (strategy_tick…) → filtrer le flux avec grep --line-buffered AVANT tee (motif ancré sur l'événement
#    structlog `] +event` — un motif non ancré supprime aussi les `job_done key=grok_supertrend_4h_…`).
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
export LOG_LEVEL=WARNING          # sans effet sur les scripts, gardé par cohérence
COSTS=config/pair_costs_b4.json   # BTC 2/2 bps, ETH 3/2, SOL 11/2 (dérivation : config/pair_costs_b4.README.md)
FILTER='\] +(strategy_tick|grid_atr_(buy|sell|built|recalc|pair)|grid_paused|grid_resumed|backtest_(buy|sell|signal|progress)|supertrend_|donchian_|ema_|dca_|regime_)'
# Forme du wrapper (~/b4_p7_phase1.sh) : … 2>&1 | grep --line-buffered -v -E "$FILTER" | tee -a logs/b4_p7.log ;
# rc=${PIPESTATUS[0]} ; bornes horodatées dans logs/b4_campaign.log ; suivi via logs/p6_status.json / p7_status.json.

# P6 — calibration sur les 3 jobs les plus lourds (les grids), puis reprise automatique des 24
nice -n 10 poetry run python scripts/run_p6_backtests.py --fees bybit --pair-costs-file $COSTS \
    --min-order-usdc 5 --workers 3 --timeout 5400 --limit 3 --output results/B4_P6_phase_d_results.json
nice -n 10 poetry run python scripts/run_p6_backtests.py --fees bybit --pair-costs-file $COSTS \
    --min-order-usdc 5 --workers 3 --timeout 5400 --output results/B4_P6_phase_d_results.json
poetry run python scripts/compute_benchmarks.py --fees bybit --pair-costs-file $COSTS --output results/B4_benchmarks.json
poetry run python scripts/filter_p6_survivors.py --input results/B4_P6_phase_d_results.json \
    --benchmarks results/B4_benchmarks.json --survivors results/B4_P6_phase_e_survivors.json \
    --report results/B4_P6_phase_e_filtering.md
poetry run python scripts/run_p6_walkforward.py --fees bybit --pair-costs-file $COSTS --min-order-usdc 5 \
    --survivors results/B4_P6_phase_e_survivors.json --output results/B4_P6_phase_f_walkforward.json
poetry run python scripts/generate_p6_report.py --phase-d B4_P6_phase_d_results.json --benchmarks B4_benchmarks.json \
    --survivors B4_P6_phase_e_survivors.json --walkforward B4_P6_phase_f_walkforward.json --output B4_P6_backtest_report.md
# ⛔ CHECKPOINT post-P6 (24/24, survivants, runs flaggés, anomalies) avant P7

# P7 — 212 jobs phase 1 (mesuré serveur : ≈ 3 h à 3 workers, DB locale), 280 fenêtres phase 2 (≈ 1 h), rapport.
# Calibration d'abord : même commande phase 1 avec --limit 3 (3 jobs grid, ≈ 4 min), puis reprise sans --force.
# Même littéral --pair-costs-file sur les 3 phases (comparé comme chaîne à la reprise) ; --min-order-usdc 5 aussi
# sur --phase report ; --phase1-input/--phase2-input obligatoires (les défauts sont les fichiers legacy → exit 2).
nice -n 10 poetry run python scripts/run_p7_grid_search.py --phase 1 --fees bybit --pair-costs-file $COSTS \
    --min-order-usdc 5 --workers 3 --timeout 5400 --output results/B4_P7_phase1_cross_validate.json
nice -n 10 poetry run python scripts/run_p7_grid_search.py --phase 2 --fees bybit --pair-costs-file $COSTS \
    --min-order-usdc 5 --workers 3 --timeout 5400 --phase1-input results/B4_P7_phase1_cross_validate.json \
    --output results/B4_P7_phase2_walk_forward.json
poetry run python scripts/run_p7_grid_search.py --phase report --fees bybit --pair-costs-file $COSTS --min-order-usdc 5 \
    --phase1-input results/B4_P7_phase1_cross_validate.json --phase2-input results/B4_P7_phase2_walk_forward.json \
    --benchmarks results/B4_benchmarks.json --report results/B4_P7_optimization_report.md \
    --selection results/B4_P7_final_selection.json
```

Règle de flag (GO GATE A) : `scripts/b4_flags.py` — tout run grid dont le bloc `liquidation` montre un résidu, une
divergence d'inventaire > 1e-12 BTC ou `net_pnl ≠ net_pnl_lot_basis` est nommé dans les rapports P6/P7
(section « Flagged runs ») ; mesuré en P6 : 3 flags, tous grid × SOL (« mauvais pop », tolérance de fermeture
absolue de la stratégie).

Règles GO P7 (Bruno, 2026-09-15 — `results/B4_3_gate_b_configs.md` § 7) : (1) une config flaggée est **inéligible**
à la sélection paper quel que soit son score (`p7_report.py` la sort de `selected_for_paper` → `ineligible_flagged`) ;
(2) le rapport note que le Sharpe DCA n'est pas comparable (courbe majoritairement cash), compare au DCA en
return/MaxDD et au B&H en Sharpe, et affiche le nombre de trades à côté de chaque métrique ; (3) critères P7 tels
quels — zéro config passante = zéro sélection paper.

## Lancer les 24 backtests P6 en parallèle

Pour (re)lancer toute la campagne P6 (8 stratégies × 3 paires), utiliser le runner
parallélisé. Il partage les 24 jobs sur un `multiprocessing.Pool` (spawn context), chaque
worker ouvre sa propre connexion DB et exécute train + test + all séquentiellement.

```bash
# Parallèle (par défaut), worker count auto-détecté
poetry run python scripts/run_p6_backtests.py --fees bybit

# Explicite
poetry run python scripts/run_p6_backtests.py --fees bybit --workers 8

# Resume automatique : relancer sans --force → combos déjà faits sont skippés (même --fees exigé :
# un fichier produit sous un autre modèle, ou sans clé `fees` (pré-B4.2), est refusé → exit 2)
poetry run python scripts/run_p6_backtests.py --fees bybit

# Force re-run
poetry run python scripts/run_p6_backtests.py --fees bybit --force

# Série (debug / gate déterminisme)
poetry run python scripts/run_p6_backtests.py --fees bybit --serial

# Sous-set pour tests rapides (après tri par durée estimée)
poetry run python scripts/run_p6_backtests.py --fees bybit --limit 3

# Timeout par job (défaut 1800s)
poetry run python scripts/run_p6_backtests.py --fees bybit --timeout 600
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
(⚠️ ce fichier date de P6 sous fees Binance et n'a pas de clé `fees` : B4.3 écrit dans un **nouveau**
`--output`, ex. `results/P6_phase_d_results_bybit.json`, sinon la reprise refuse — c'est voulu)
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
poetry run python scripts/run_p7_grid_search.py --phase 1 --fees bybit --workers 8 --timeout 3600

# Phase 2 — walk-forward 8 fenêtres × top-5 par combo (≈ 280 backtests) ; le fichier phase 1
# doit avoir été produit avec le même --fees (validé, sinon exit 2)
poetry run python scripts/run_p7_grid_search.py --phase 2 --fees bybit --workers 8 --timeout 3600

# Phase rapport — agrège phase 2, applique 7 critères, écrit le markdown (--fees validé contre les 2 fichiers)
poetry run python scripts/run_p7_grid_search.py --phase report --fees bybit

# Filtres utiles (smoke tests)
poetry run python scripts/run_p7_grid_search.py --phase 1 --fees bybit \
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

Benchmarks Sharpe extraits du rapport P6 v2 (1k USDC, fees Binance 0.075 % flat — à recalculer en B4.3
avec `--fees bybit`) :

| Pair | Buy & Hold | DCA fixed |
|---|---|---|
| BTC/USDC | 0.85 | 2.37 |
| ETH/USDC | 0.40 | 2.10 |
| SOL/USDC | 0.31 | 1.93 |

Si une stratégie n'a aucune config qui passe → on l'abandonne, documenté
dans `results/P7_optimization_report.md` (produit par `--phase report`, pas encore généré).

### État P7 (30 mai 2026)

Phase 1 terminée : `results/P7_phase1_cross_validate.json` (212 jobs, fees Binance, sans clé `fees`). Phase 2
et rapport non lancés. Le tout est rejoué en B4.3 avec `--fees bybit` dans de nouveaux fichiers de sortie.

---

## Lancer un backtest unitaire

```bash
poetry run python scripts/backtest.py \
    --strategy grok_supertrend_4h \
    --pair BTC/USDC \
    --exchange binance \
    --fees bybit \
    --start-date 2023-04-01 \
    --end-date 2026-04-01 \
    --capital 1000 \
    --cross-validate \
    --save

# Run unitaire avec dump des trades (audit fee par fee) et overrides de spread/slippage par paire
poetry run python scripts/backtest.py --strategy grok_supertrend_4h --pair BTC/USDC \
    --exchange binance --fees bybit --interval 5 --start-date 2023-04-01 --end-date 2026-04-01 \
    --trades-out results/my_run_trades.json --pair-costs-file config/pair_costs.json
```


### Paramètres clés

- `--strategy` : nom de la classe (snake_case)
- `--pair` : `BTC/USDC`, `ETH/USDC`, ou `SOL/USDC`
- `--exchange` : `binance` (source de données OHLC uniquement ; les fees n'en dérivent plus)
- `--fees` : **obligatoire** — `bybit` (cible de production), `binance` (0.075 % flat, modèle des résultats
  P6/P7 historiques, sert au rejeu iso-fees) ou `kraken` ; voir « Modèle de fees »
- `--trades-out PATH.json` : dump trade par trade (prix, prix de référence, fee, taux, base, liquidité
  maker/taker, spread/slippage) — run unitaire seulement (pas avec `--cross-validate`)
- `--pair-costs-file PATH.json` : overrides de spread/slippage par paire pour les fills market
  (`{"BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"}}`) : sorties market du moteur signal **et**
  liquidation terminale du grid (B4.3) ; sans fichier, les valeurs globales du modèle s'appliquent
- `--min-order-usdc N` : plancher de notionnel d'un BUY du moteur signal (rejet `minOrderAmt` simulé : un ordre
  dimensionné en dessous est sauté) ; défaut 1 = comportement historique, campagne B4 = 5 (Bybit)
- `--cross-validate` : split 70% train / 30% test temporel
- `--save` : sauvegarde les résultats dans `backtest_runs` en DB

### Deux modes

- **SignalBacktester** : pour les stratégies signal-based (SuperTrend, EMA Cross, Donchian, Scalping, etc.)
- **GridBacktester** : pour la grid (GrokGridATRAdaptiveV4)

Le script détecte automatiquement le mode selon la stratégie.

## Modèle de fees (`--fees`) — doctrine maker/taker (B4.2)

Le modèle de fees est **découplé de la source de données** : `--fees {bybit,binance,kraken}` est requis
partout (`backtest.py`, `run_p6_backtests.py`, `run_p7_grid_search.py` toutes phases, `run_p6_walkforward.py`),
résolu par `ExchangeFees.from_name()` ; les constructeurs `BacktestEngine` / `GridBacktester` prennent un
`fee_model` keyword-only requis (nom ou instance `ExchangeFees`). `settings.exchange_fees` reste le modèle
**live/paper** des connecteurs : le backtest ne le lit jamais.

| Site de fill | Ordre simulé | Fee |
|---|---|---|
| Moteur signal, entrée `order_type: limit` remplie par toucher (`candle.low <= limit_price`) | limit reposant | **maker**, spread = slippage = 0 |
| Moteur signal, sortie `order_type: market` (SL, trailing, timeout, régime, flip) à l'open de N+1 | market | **taker** + spread + slippage sur le prix |
| Grid ATR : niveaux BUY et cibles SELL remplis par toucher | limit reposant | **maker** |
| Grid ATR : liquidation de l'inventaire terminal en fin de run (`_force_close_open_positions`, B4.3) | MARKET au dernier close tradeable (candle 5 m en P6/P7) | **taker** + spread + slippage (`--pair-costs-file` ou globaux du modèle) ; soldes réglés, trades `forced_liquidation`, point d'equity final |

Hypothèses documentées (B4.3) : les sorties limit émises après franchissement du niveau
(`gemini_scalping_volatilite` TP, `gemini_retour_moyenne` TP) sont marketables en réel mais facturées
maker ; les ordres appariés de la grille sont pricés sur le fill, pas sur le marché.

Chaque `BacktestTrade` porte `liquidity`, `fee_rate`, `fee_base_usdc`, `reference_price`, `spread_pct`,
`slippage_pct` (et `forced_liquidation` pour le grid) ; `--trades-out` les écrit, et
`scripts/audit/b4_2_reference_capture.py verify-fees dump.json --fees bybit` vérifie trade par trade (entrées
0.0010, sorties market et liquidations 0.0025 + 0.0002 + 0.0002 ; avec `--pair-costs-file`, le harnais
attend encore les globaux → ne pas l'appliquer à ces dumps avant le commit campagne).

**`net_pnl` (B4.3, les deux moteurs)** : chaque fee comptée une fois. Signal : `net_pnl = total_pnl − Σ fees
d'achat` — la fee de vente est déjà dans le `pnl` de chaque trade ; l'ancienne formule `total_pnl − total_fees` la
comptait deux fois ; run plat ⇒ `net_pnl == ending_balance − capital`. Grid : `net_pnl` = **cash réalisé après la
liquidation terminale** (`usdc − capital`, identité par construction), égal à `total_pnl − fees d'achat`
(`liquidation.net_pnl_lot_basis` du dump) dès que la comptabilité par lot concorde avec le wallet — un écart signale
une divergence d'inventaire (`residual_net_proceeds`, `inventory_divergence_btc`). Vérifié à 1e-9 sur les rejeux de
référence (`results/B4_3_chantier0_gate_a.md`). Le critère de drift B5 lit ce chiffre.
Régression iso-fees : `capture` / `compare` / `normalise-log` du même harnais (voir
`results/B4_2_fees_engine_report.md`). Chaque entrée de résultat P6/P7 porte sa clé `fees` ; la reprise
refuse un fichier d'un autre modèle ou sans clé (`--force` = seule échappatoire).

Note `.env` : les scripts chargent `.env` dans `main()` (jamais à l'import) avec un chemin explicite ;
`get_settings()` retombe sur une résolution par fichier appelant qui devient dépendante du CWD sous
`pytest --cov` / debugger — lancer les rejeux depuis la racine, sans couverture.

## Fees Bybit EU (CRITIQUE)

Cible de production (vérifié sur le compte, VIP0) :

| Type | Fee |
|---|---|
| Maker (limit, PostOnly) | **0.10 %** |
| Taker (market) | **0.25 %** |
| Spread simulé | 0.02 % |
| Slippage simulé | 0.02 % |

Round-trip limit/limit : **0.20 %** ; limit/market (stop-loss, trailing, timeout) : **0.35 %**.
Le taker à 2.5× le maker change la doctrine des sorties MARKET (voir `skills/risk_management.md`).

Marqueurs de fees legacy dans les logs/rapports : `0.075 %` flat = Binance BNB (P6/P7 historiques) ;
`0.16 % / 0.26 %` = Kraken spot (défaut de `ExchangeFees()` nu). Ni l'un ni l'autre n'est valable pour
une décision de mise en paper Bybit.

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
- Chaque paire maker complétée est un win par construction ; les **pertes** viennent de la **liquidation
  terminale** (B4.3) : en fin de run l'inventaire ouvert est vendu MARKET au dernier close (taker + spread +
  slippage), chaque lot compte comme un trade (perdant s'il est sous l'eau), `unrealized_pnl` porte ce P&L
  réalisé, `total_trades = paires maker + lots liquidés`. Sur le run P6 de référence : 33 lots tous sous
  l'eau → `win_rate` 0.969, PF inf → 1.66, `net_pnl` 336 → 129 USDC (= `ending − 1000`).
- `profit_factor` vaut `inf` seulement si aucun lot n'est perdant (inventaire vide ou tout en profit).
- Le rapport sépare « Grid Pairs Completed (maker) », « Forced Liquidations », « Buy Fees » / « Sell Fees
  (incl. liquidation) » ; le dump `--trades-out` a un bloc `liquidation` (positions, prix, fees, résidu,
  divergence d'inventaire — attendus 0 sur tout run sain).
- Regarder : paires maker vs lots liquidés, profit par paire vs fees, comportement en bear vs bull.

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

1. **Oublier les fees, ou utiliser les mauvaises** → résultats trop optimistes (P6/P7 = 0.075 % flat ;
   depuis B4.2 `--fees` est obligatoire, `--fees bybit` pour toute décision de paper)
2. **Look-ahead bias** → le backtest "voit" le futur. Toujours next-bar execution.
3. **Survivorship bias** → ne tester que les paires qui ont survécu
4. **Overfitting** → toujours cross-validate, jamais optimiser sur le test set
5. **Période non représentative** → toujours tester sur au moins 3 ans incluant bull ET bear
6. **SOL commence en sept 2021** → la période commune aux 3 paires est 2021-09 à aujourd'hui
