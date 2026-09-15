# B4.3 — GATE B : configs de campagne (à valider avant tout run)

> Brief : `agent/AGENT_B4_3_CAMPAIGN.md` § 5 (5 points) et § 6 (campagne). Prérequis : GATE A validé (GO Bruno
> 2026-09-14, `results/B4_3_chantier0_gate_a.md`). Moteur = branche `feat/b4-3-campaign` @ `69fcf2c`
> (gold hashes `43dcdf8d…` / `818d7fa8…`). **GO GATE B — Bruno, 2026-09-15 : les 5 points validés, valeurs incluses**
> (§ 0). Le commit `feat(scripts): b4 campaign configs` (§ 5.3) est écrit après ce GO ; il ne change **aucune**
> métrique par défaut (gold hashes et garde signal inchangés, vérifiés) — les nouveautés n'agissent que par les flags
> de la campagne. Séquence validée : commit campagne → calibration `--limit 3` → P6 24 combos → **CHECKPOINT post-P6**
> (résumé 10 lignes : 24/24, survivants, flags divergence / écart formule-cash, anomalies) **avant** P7 phase 1
> (~27 h). Tout résultat aberrant = STOP avant la phase suivante.

## 0. Décisions GO B (Bruno, 2026-09-15)

| # | Décision | Validé | Section |
|---|---|---|---|
| B.1 | Coûts | `--fees bybit` partout ; `config/pair_costs_b4.json` = **BTC 0.0002/0.0002, ETH 0.0003/0.0002, SOL 0.0011/0.0002**. Règle « p75 nocturne » **amendée** en `max(p75 global, p75 nocturne 00–05 UTC)`, bp supérieur, après constat que le spread est piloté par la volatilité (soirée du 14 : ETH 0.124 %) — amendement strictement conservateur. Source `results/q3_orderbook.jsonl` (versionné au commit campagne). Dérivation § 1 | § 1 |
| B.2 | Risk mapping validé ; **`--min-order-usdc 5`** ; **B.2a : défauts de classe conservés** pour la campagne. Conditions : (1) le rapport B4 embarque le **dump machine-readable des params effectifs** de chaque config sélectionnée, capturé au runtime (`effective_params` par entrée de résultat, `effective_params` des configs sélectionnées dans `B4_P7_final_selection.json`) — c'est lui qui alignera `strategies.yaml` en B5 ; (2) **dette numérotée** dans `PROJECT_CONTEXT.md` (résolution par nom de classe, dette 13), fix post-B4 après alignement YAML ; (3) test one-off « le chemin live/router résout par instance » = **prérequis B5**, consigné (dette 13) | § 2 |
| B.3 | Grille spacing `[0.015, 0.020, 0.025, 0.030]`, plancher 2.0 %, reste identique | § 3 |
| B.4 | Serveur : 3 workers `nice`, tmux `b4`, `LOG_LEVEL=WARNING`, `--timeout 5400`, calibration `--limit 3`, `git pull --ff-only` du commit chantier 0 (la branche est poussée sur `origin` et suivie sur le serveur), `df` consigné. **Ne pas toucher au tmux `spread`** | § 4 |
| B.5 | Sorties `B4_P6_*` / `B4_P7_*`, benchmarks `--fees bybit`, jamais de `--force` sur legacy | § 5 |

## 1. Coûts (brief § 5.1)

- **`--fees bybit` partout** : `run_p6_backtests.py`, `run_p6_walkforward.py`, `run_p7_grid_search.py --phase 1|2|report`,
  `compute_benchmarks.py` (§ 5.2). Chaque entrée de résultat porte `fees`, la reprise refuse un autre modèle.
- **`config/pair_costs_b4.json`** (valeurs GO B) et dérivation depuis `results/q3_orderbook.jsonl` (126 mesures de
  carnet `api.bybit.eu`, 42 par paire, du 2026-09-14 10:46 au 2026-09-15 06:47 UTC, dont 10 nocturnes 00–05 UTC ;
  `spread_pct` en % du mid ; slippage mesuré pour 1 k USDC) :

  | Paire | p75 spread global | p75 nocturne 00–05 | max → bp supérieur | slippage mesuré p75 | **Retenu** |
  |---|---|---|---|---|---|
  | BTC/USDC | 0.018 % (1.8 bps) | 0.0015 % (0.15 bps) | 1.8 → **2 bps** | 0 → plancher 2 bps | **0.0002 / 0.0002** |
  | ETH/USDC | 0.028 % (2.8 bps) | 0.0016 % (0.16 bps) | 2.8 → **3 bps** | 0 → 2 bps | **0.0003 / 0.0002** |
  | SOL/USDC | 0.087 % (8.7 bps) | 0.108 % (10.8 bps) | 10.8 → **11 bps** | 0 → 2 bps | **0.0011 / 0.0002** |

  Règle amendée au GO B : `spread = ceil_bp(max(p75 global, p75 nocturne))`, `slippage = max(2 bps, p75 mesuré)` —
  la proposition initiale « p75 nocturne seul » aurait donné 1 bp sur BTC/ETH ; l'amendement est strictement
  conservateur. Détail : `config/pair_costs_b4.README.md`.
- **Où ça s'applique** : fills **market** du moteur signal (SL, trailing, timeout, `regime_shift_bear`,
  `supertrend_flip`, `death_cross`, `donchian_lower_break`) et **liquidation terminale du grid** (chantier 0, D4) ;
  jamais aux fills limit/maker (entrées signal, grille). Sous `--pair-costs-file`, un run BTC aux globaux est
  **bit-identique** au run sans fichier (preuve D4).
- **Plomberie (commit campagne)** : `--pair-costs-file` sur les trois runners, chemin + contenu enregistrés dans
  chaque entrée (`pair_costs`) et vérifiés à la reprise comme `fees` ; `verify-fees` lit déjà les overrides du dump
  (C7). Les benchmarks (B&H, DCA fixe) prennent les mêmes coûts (§ 5.2).

## 2. Risk backtest-visible vs runtime pur (brief § 5.2)

### 2.1 Ce que les moteurs simulent réellement — et avec quels paramètres

**Constat (vérifié par instanciation, 2026-09-14)** : les moteurs résolvent les params des stratégies internes du
router **par nom de classe** (`strategies.get("grok_supertrend_4h")`, `backtest.py:_load_inner_strategy_params`)
alors que `strategies.yaml` les indexe **par instance** (`supertrend_btc`, `grid_atr_btc`, `grid_atr_eth`… avec un
champ `class:`). Résultat : les **5 stratégies grok** (supertrend, grid, donchian, dca, ema) tournent sur les
**défauts de classe**, pas sur le YAML ; les **3 gemini** (clés YAML = nom de classe) reçoivent leurs params YAML.
Preuve : le run grid P6 de référence a des lots de **25 USDC** (défaut de classe) alors que `grid_atr_btc` dit 10.
C'était déjà le cas en P6/P7 historiques (même code de résolution) : les classements P6/P7 sont ceux des défauts.
P7 n'est pas concerné pour les params balayés (override explicite) ; les autres restent aux défauts.

| Stratégie | Source des params en backtest | Sizing effectif (par ordre) | Runtime YAML (instance BTC) |
|---|---|---|---|
| `grok_supertrend_4h` | défauts de classe | `order_size_usdc` 50 (`min(usdc, 50)`) | `supertrend_btc` : st 10/3.0, sl 3.5, alloc 10 % (pas d'`order_size_usdc` → 50) |
| `grok_grid_atr_adaptive_v4` | défauts de classe | lots **25** USDC, 12 niveaux, spacing 1.5 %-5 %, ATR×4 | `grid_atr_btc` : lots **10**, alloc 10 % ; `grid_atr_eth` : lots 25 |
| `grok_donchian_breakout_4h` | défauts de classe | 50 USDC | `donchian_btc` : 30 USDC, alloc 10 % |
| `grok_adaptive_dca_weekly` | défauts de classe | base 15 USDC × multiplicateurs | `dca_btc` : 15, alloc 25 % |
| `grok_ema_adx_atr` | défauts de classe | 40 USDC | `ema_cross_btc` : alloc 15 % (inactif) |
| `gemini_*` (3) | **YAML** | 25 / 25 / 50 USDC | idem |

**Décision B.2a (GO B)** — **défauts de classe conservés** pour la campagne. Conditions appliquées : (1) les moteurs
capturent au runtime les params effectifs de chaque stratégie (`capture_effective_params`, source `class_default` /
`passed` / `override`) ; les runners les persistent dans chaque entrée (`effective_params`) et `p7_report` les embarque
pour chaque config sélectionnée (`B4_P7_final_selection.json`, section du rapport) — c'est le dump qui alignera
`strategies.yaml` en B5 ; (2) dette 13 dans `PROJECT_CONTEXT.md` (résolution par nom de classe), fix post-B4 après
l'alignement YAML ; (3) test one-off « le chemin live/router résout bien par instance » consigné comme prérequis B5.

### 2.2 Simulé par les moteurs (backtest-visible)

| Mécanisme | Signal (`BacktestEngine`) | Grid (`GridBacktester`) |
|---|---|---|
| Taille d'ordre | `min(usdc_balance, order_size_usdc)` (métadonnée stratégie) ; sinon `default_order_amount_eur` (env, 25) × `position_size_multiplier` | `order_size_usdc` par niveau (25) |
| Plancher d'ordre | **1 USDC** (`backtest.py:684`, sinon skip) | aucun (lot fixe) |
| Stop-loss / sorties | `sl_atr_mult` **de la stratégie** (3.5 × ATR 4h), trailing, timeout, régime, flip → **market** (taker + coûts) | aucune sortie hors paires maker et **liquidation terminale** (chantier 0) |
| Capital | 1 000 USDC **par combo** (stratégie seule sur sa paire) | idem |
| Positions simultanées | 1 (`in_position`), sauf DCA (accumulation) | jusqu'à `grid_levels` lots |
| Fees / coûts | maker entrées, taker + spread + slippage sorties (par paire via `--pair-costs-file`) | maker grille, taker + coûts liquidation |

### 2.3 Plancher de position (brief : 5-10 USDC)

Bybit spot `minOrderAmt` = 5 USDC (B0). Proposition : paramètre moteur `min_order_usdc` (défaut **1** = comportement
actuel → gold hashes et garde intacts), exposé par les runners (`--min-order-usdc`), **5** pour la campagne (cible 10
notée pour B5). Effet attendu : quasi nul sur les ordres nominaux (25-50 USDC), il n'agit que quand `usdc_balance`
s'épuise (`min(usdc, order)`) — un ordre résiduel < 5 USDC est **sauté** au lieu d'être passé (fidèle au rejet
exchange). Pour la grille : `order_size_usdc` 25 > 5, sans effet ; un lot partiel n'existe pas.

### 2.4 Runtime pur — documenté pour la config paper B5, non simulé

| Paramètre | Runtime actuel | Cible B5 (PROJECT_CONTEXT § 4) | Backtest |
|---|---|---|---|
| Max positions global | 25 (`global_max_open_positions` 10 en settings, 25 YAML) | ~100 (safeguard) | non simulé (1 position signal / N lots grid) |
| Daily loss limit | 50 EUR fixe | 5 % du capital, sur P&L **net réalisé** | non simulé |
| Exposition max | 90 % | 90 % | non simulé |
| Sizing GRM | `capital × risk_pct 1 % × confidence / \|entry − SL\|`, SL ATR 3.0 × ATR(14, 4h) | risk 2 % si capital < 5k | non simulé : les stratégies posent leurs propres SL (`sl_atr_mult` 3.5) et tailles fixes |
| Crash protector | −7 % / 30 min → ferme 50 % + suspend 2 h | idem | non simulé |
| Budgets `max_allocation_pct` / `StrategyBudget` | 10-25 % de 1 000 par instance | à revoir | non simulé : chaque combo a 1 000 USDC entiers → **returns non transposables** tels quels au paper multi-stratégies (diviser par le budget) |
| Limites par paire | aucune | à envisager | non simulé |
| Sorties MARKET | coût = taker 0.25 % + coûts par paire | doctrine des stops à revalider sur les résultats | simulé (fees + `pair_costs`) |

Le rapport B4 reprend cette table telle quelle (« risk révisé : valeurs retenues pour B5 »).

## 3. Grilles P7 (brief § 5.3)

- **Plancher de spacing** : round-trip maker/maker Bybit **0.20 %** (vs 0.15 % Binance qui justifiait le 1.5 % =
  **10 ×** le coût par cycle) → même couverture ⇒ **2.0 %** ; limit/market 0.35 % n'intervient qu'à la liquidation
  terminale (une fois par run) et ne pèse pas sur le cycle. Grille P7 : `min_spacing_pct: [0.015, 0.020, 0.025,
  0.030]` (1.0 % retiré : 5 × seulement ; 1.5 % gardé comme témoin de la calibration Binance). `atr_multiplier`
  [1.5, 2.0, 2.5, 3.0] et `bear_protection_mode` [none, 1w_only, 1d_only] inchangés → 48 combos/paire, **212 jobs**
  phase 1 comme en P7 historique (SuperTrend 60, Grid 96, DCA 48, Donchian 8).
- `min_profitable = prix × 1.0064` (stratégie :590, calibré Kraken 4 × 0.16 %) : plancher sur la cible SELL, **jamais
  contraignant** avec un spacing ≥ 1.5 % (> 0.64 %) → sans effet sur la campagne ; consigné (stratégie protégée).
- Phase 2 inchangée : 8 fenêtres 12 m / 3 m, top-5 par combo → 280 jobs. Critères P7 (7) inchangés ; critères P6 (5 +
  cohérence + benchmark) inchangés — note : `total_trades` grid inclut désormais les lots liquidés (33 sur P6 : sans
  effet sur `min_trades` 30).
- Benchmarks « bat B&H ou DCA fixe » recalculés sous fees Bybit (§ 5.2) → `results/B4_benchmarks.json`.

## 4. Exécution serveur (brief § 5.4)

**État relevé le 2026-09-14 16:29 UTC (SSH lecture seule)** : `krakenbot` 4 vCPU, RAM 7.6 Gi (5.8 Gi disponibles),
disque **58 G libres / 75 G**, load 0.03 ; `krakenbot-collector` **active**, `krakenbot` inactive ; repo
`~/apps/kraken-trading-bot` @ `8bc025a` (tracke `dev`) ; `logs/` 12 K, `results/` 9.1 M ; **une session tmux
`spread` attachée** (créée 10:46 — mesure q3 ?) → **ne pas la toucher**.

| Point | Proposition |
|---|---|
| Code | pousser `feat/b4-3-campaign` sur `origin` (trace, comme B4.2) ; sur le serveur `git fetch origin && git checkout -b feat/b4-3-campaign origin/feat/b4-3-campaign` puis `git pull --ff-only` à chaque commit (le collector tourne sur les modules déjà chargés ; la branche ne touche ni `collector` ni `src/` hors une docstring — aucun restart) ; retour sur `dev` à la clôture |
| Session | `tmux new -s b4` (jamais `spread`) ; une commande par phase, `Ctrl+B D`. **Piège consigné (15/09)** : `~/.bashrc:119` fait `set -a && source .env && set +a` → tout shell interactif exporte `SCHEDULER_PAIRS=[BTC/USDC,…]` sans guillemets (JSON invalide) et `load_dotenv` ne surcharge pas une variable existante → `SettingsError … field "pairs"` dans les workers ; les scripts de run font `unset SCHEDULER_PAIRS SCHEDULER_INTERVALS` avant `poetry run` (`~/b4_p6_calib.sh`, `~/b4_p6_full.sh`, …). Les services systemd (`EnvironmentFile`) ne sont pas concernés |
| Workers | **3** (`--workers 3` explicite : l'auto-détection donnerait `min(4 − 2, 8, 7.6 // 2)` = 2) ; `nice -n 10` ; ~1 Gi/worker → 3 Gi sur 5.8 disponibles ; le collector garde son vCPU |
| Logs | `LOG_LEVEL=WARNING` dans l'environnement de la commande : sinon chaque run grid imprime ~130 Mo d'INFO (`strategy_tick`) — 3 combos grid × 3 segments en P6, 96 × 3 en P7 = plusieurs dizaines de Go dans le scrollback ; le suivi passe par `logs/p6_status.json` / `p7_status.json` et le résumé final ; `2>&1 \| tee -a logs/b4_p6.log` |
| Timeouts | `--timeout 5400` (P6.7 : jobs grid à 2 953 s en parallèle > 1 800 s par défaut) |
| Calibration | `run_p6_backtests.py --fees bybit --pair-costs-file config/pair_costs_b4.json --min-order-usdc 5 --workers 3 --limit 3 --output results/B4_P6_phase_d_results.json` (3 premiers jobs = les grids) → mesure la durée réelle sur DB locale avant de lancer les 24 (reprise automatique ensuite, sans `--force`) |
| Durées estimées (P6.7 via tunnel, DB locale probablement plus rapide) | P6 : Σ série 291 min → 3 workers, contention ~1.6 × ⇒ **≈ 2.5 h** ; P7 phase 1 : ≈ 51 h série (grid 96 jobs × ~25 min, SuperTrend 60 × 7, DCA 48 × 3.7, Donchian 8 × 6.7) ⇒ **≈ 27 h** ; phase 2 : 280 fenêtres de 15 mois ⇒ **≈ 8-10 h** ; rapport : minutes. Total ≈ 40 h serveur, reprise possible à tout moment |
| Fenêtre | P6 jour J (après GO B) ; P7 phase 1 lancée le soir de J, ~1.5 j ; phase 2 J+2 ; `df -h` avant chaque phase (≥ 20 G libres) |
| Collector | `systemctl is-active krakenbot-collector` + `journalctl -u krakenbot-collector --since <début>` avant/après chaque phase ; aucun redémarrage ; comptage des candles `bybit` sur la fenêtre (brief § 7.5) |
| Fin | `tmux kill-session -t b4`, `ps aux \| grep run_p` vide, `df -h`, résultats rapatriés (`scp`) et commités depuis le poste local |

## 5. Sorties (brief § 5.5)

### 5.1 Fichiers (tous nouveaux ; les legacy sans clé `fees` ne sont **jamais** réécrits, `--force` interdit dessus)

| Étape | Commande (serveur, tmux `b4`, `LOG_LEVEL=WARNING`, `nice -n 10`) | Sortie |
|---|---|---|
| P6 phase D | `run_p6_backtests.py --fees bybit --pair-costs-file config/pair_costs_b4.json --min-order-usdc 5 --workers 3 --timeout 5400 --output results/B4_P6_phase_d_results.json` | `B4_P6_phase_d_results.json` |
| Benchmarks | `compute_benchmarks.py --fees bybit --pair-costs-file … --output results/B4_benchmarks.json` | `B4_benchmarks.json` |
| P6 phase E | `filter_p6_survivors.py --input results/B4_P6_phase_d_results.json --benchmarks results/B4_benchmarks.json --survivors results/B4_P6_phase_e_survivors.json --report results/B4_P6_phase_e_filtering.md` | survivants + filtrage |
| P6 phase F | `run_p6_walkforward.py --fees bybit --pair-costs-file … --survivors results/B4_P6_phase_e_survivors.json --output results/B4_P6_phase_f_walkforward.json` | walk-forward (vide si 0 survivant : normal, documenté) |
| P6 rapport | `generate_p6_report.py --input B4_P6_phase_d_results.json --output B4_P6_backtest_report.md` | `B4_P6_backtest_report.md` |
| P7 phase 1 | `run_p7_grid_search.py --phase 1 --fees bybit --pair-costs-file … --min-order-usdc 5 --workers 3 --timeout 5400 --output results/B4_P7_phase1_cross_validate.json` | 212 jobs |
| P7 phase 2 | `--phase 2 … --phase1-input results/B4_P7_phase1_cross_validate.json --output results/B4_P7_phase2_walk_forward.json` | 280 jobs |
| P7 rapport | `--phase report --fees bybit --phase1-input … --phase2-input … --benchmarks results/B4_benchmarks.json --report results/B4_P7_optimization_report.md --selection results/B4_P7_final_selection.json` | rapport + sélection machine |
| Rapport final | rédigé à la main | `results/B4_bybit_backtest_report.md` (brief § 6.3) |

P7 tourne sur les stratégies survivantes de P6 ; si aucune ne survit, sur les 4 stratégies historiques du grid search
(brief § 6.2), avec la question « une config sauve-t-elle une stratégie que sa config par défaut condamne ? ».

### 5.2 Benchmarks sous fees Bybit

`compute_benchmarks.py` n'a pas de modèle de fees aujourd'hui (B&H et DCA fixe sans fee). Proposition : `--fees` +
`--pair-costs-file` (achat B&H = taker + coûts, achats DCA hebdo = maker, valorisation finale au dernier close sans
sortie — même convention que le moteur signal sans liquidation) → `B4_benchmarks.json` ; l'ancien `P6_benchmarks.json`
reste la référence Binance. Alternative : benchmarks sans fee (favorables aux benchmarks, donc conservateurs pour
les stratégies) — à trancher.

### 5.3 Contenu du commit `feat(scripts): b4 campaign configs` (après GO B, avant tout run)

1. `--pair-costs-file` sur `run_p6_backtests.py`, `run_p6_walkforward.py`, `run_p7_grid_search.py` (phases 1-2) →
   `pair_costs` passé aux deux moteurs, enregistré par entrée, contrôlé à la reprise (comme `fees`).
2. `min_order_usdc` moteurs (défaut 1) + `--min-order-usdc` runners (campagne : 5).
3. `p7_grids.py` : `min_spacing_pct` `[0.015, 0.020, 0.025, 0.030]`.
4. `filter_p6_survivors.py`, `generate_p6_report.py`, `compute_benchmarks.py`, `run_p7_grid_search.py --phase report` :
   chemins d'entrée/sortie en arguments (défauts = chemins legacy inchangés), `--fees` sur les benchmarks.
5. **Règle de flag (GO GATE A, point 2)** : les runners persistent par segment le bloc grid `liquidation`
   (positions, pnl, fees, `residual_net_proceeds`, `dust_written_off_btc`, `inventory_divergence_btc`,
   `net_pnl_lot_basis`) ; `generate_p6_report.py` et `p7_report.py` **flaggent nominativement** (stratégie × paire ×
   config × segment) tout run avec divergence d'inventaire ou `net_pnl ≠ net_pnl_lot_basis` (au-delà de 1e-12).
6. Tests : plomberie CLI (refus de reprise sur `pair_costs` différent), `min_order_usdc` (défaut = bit-identique :
   gold hashes et garde signal inchangés), grille P7, chemins, persistance et flag.
7. `skills/backtest.md` : commandes de campagne ; `results/INDEX.md` : lignes `B4_*` à la production.

### 5.4 Statut séparé

Les fichiers `B4_*` portent `fees: "bybit"` et `pair_costs` ; `logs/p6_status.json` / `p7_status.json` sont
réécrits par les runners (statut de la campagne courante) ; les fichiers P6/P7 historiques ne sont ni lus (sauf
contexte du rapport) ni écrits.

## 6. Ce qui reste hors scope (rappel brief § 3)

Stratégies et fichiers protégés intouchés (résolution YAML `class:` et « mauvais pop » consignés) ; `market_data_ohlc`
en lecture seule ; collector jamais arrêté ; pas de déploiement ni de push `main` ; scalping/ML = P12/P11.
