# B4.3 — Chantier 0 : moteur grid honnête — note GATE A

> Brief : `agent/AGENT_B4_3_CAMPAIGN.md` § 4 (chantier 0) et § 7.1/7.4. Plan approuvé et **GO Bruno le 2026-09-14**
> (D1-D12 confirmées, dérogations § 8). Branche `feat/b4-3-campaign` depuis `dev` @ `539c339`
> (= tag `v2.7.0-b4-2-fees-engine` + docs de clôture `8bc025a` + commit `ci: run on push to dev (not develop),
> test on Python 3.12` — le « commit fix(ci) » du brief).
> Runs de référence exécutés en local via le tunnel SSH (lecture seule, collector intouché), comme en B4.2.
> Références de lignes `scripts/backtest.py` = **base `539c339`** (état diagnostiqué), sauf mention « HEAD ».
> Revue adversariale du diff (43 agents read-only, § 7) : 4 défauts confirmés, corrigés (C6/C7) avant soumission.
> État : **soumis au GATE A** — aucun run de campagne n'a été lancé.

## 1. Résumé

- Deux défauts du `GridBacktester` corrigés **une fois** : (a) la liquidation de l'inventaire terminal est
  désormais **atteignable sur le chemin grok** (le seul chemin de production) — vente MARKET au dernier close
  tradeable (`close × (1 − spread − slippage)`, fee **taker**, soldes réglés, trades `forced_liquidation`, point
  d'equity final) ; (b) `net_pnl` compte chaque fee **une fois** — dans les **deux** moteurs (décision Bruno D3 :
  sémantique unifiée, delta documenté ; le critère de drift B5 lit ce chiffre) : signal `total_pnl − Σ fees d'achat` ;
  grid = **cash réalisé après liquidation** (`usdc − capital`, identité `net_pnl == ending − capital` par
  construction), égal à `total_pnl − fees d'achat` dès que la comptabilité par lot concorde avec le wallet (les deux
  valeurs et l'écart éventuel sont exposés dans le bloc `liquidation` du dump).
- Ce que le fix révèle sur le run grid P6 de référence (BTC/USDC 2023-04-01 → 2026-04-01, `--fees binance`) : les
  **33 lots terminaux sont tous sous l'eau** (entrées 71 780 → 123 290 vs close 68 240.16) → liquidation
  **−227.07 USDC**, PF **inf → 1.6555**, `win_rate` 1.0 → 0.969, return +12.95 % → **+12.89 %**, `net_pnl` +336.31 →
  **+128.87 = `ending − 1000`** (identité cash à 3e-14). Sous `--fees bybit` : PF 1.617, `net_pnl` **114.21**,
  return +11.42 %.
- **Contrat GATE A (table § 3 du plan) réconcilié ligne à ligne sur le run réel : 37/37 checks** (P6) et 36/36
  (fenêtre gold hash), zéro écart hors conditionnels sur les 18 clés de `to_dict()` ; conditionnels lus au run :
  MaxDD **inchangé** (19.699 %), Sharpe 0.023707 → 0.023614, Sortino 0.033857 → 0.033725, Calmar 0.218928 →
  0.217867 (tous ↓) ; `average_holding_time_minutes` inchangé (1 439.25, paires maker) — les 33 lots liquidés
  étaient détenus **105.6 jours** en moyenne (bloc `liquidation`).
- **Garde d) amendée : PASS** — le rejeu du run signal A est bit-exact **sauf `metrics.net_pnl`** : 2 lignes de log
  sur 5 576 (les deux portent `net_pnl`), `compare --ignore metrics.net_pnl` IDENTICAL sous les deux modèles,
  delta `net_pnl` == +Σ fees de vente à 1e-15 (binance +1.7445, bybit +5.8128), identité cash à 1e-13, diff byte
  du dump bybit = 1 ligne.
- Gold hashes re-baselinés une fois, après les deux fixes (H1 binance `71d68b95…`, H2 bybit `97cae113…`),
  trois segments chiffrés (§ 5). Preuve D4 (kwarg `pair_costs` absent ≡ `pair_costs=None`) : IDENTICAL sur P6 et
  fenêtre rapide. Déterminisme grid sur 3 ans conservé (deux captures identiques).

## 2. Commits (`feat/b4-3-campaign`)

| # | Commit | Contenu |
|---|---|---|
| C1 | `eedfcf1` `fix(backtest): make grid terminal liquidation reachable (taker market close)` | `_record_equity()` sur les deux chemins de replay (dernier close tradeable = candle 5 m en P6/P7), `_liquidate_lot()` + `_force_close_open_positions()` réécrite (prix ajusté forme exacte de :748, taker, soldes, tag, point d'equity, clamp/dust/résidu 1e-12), `pairs_completed` hors liquidations, `GridBacktester(pair_costs=)` + `_costs_for_pair`, refus CLI levé, `BacktestTrade.forced_liquidation`, dump grid (`forced_liquidation` par trade, bloc `liquidation` hors projection), rapport grid, harnais `compare --ignore`, tests existants mis à jour |
| C2 | `76e0197` `fix(backtest): count sell fee once in net_pnl (grid and signal engines)` | `net_pnl = total_pnl − Σ fee(BUY)` (grid :`_calculate_final_metrics`, signal :`calculate_final_metrics` — **seule ligne du moteur signal touchée**), commentaires `BacktestMetrics`, lignes Buy/Sell Fees, `test_backtest.py` −2.4 → −1.6 |
| C3 | `19d1ded` `test(strategies): re-baseline grid_atr_v4 gold hashes after chantier 0 (binance H1, bybit H2)` | test paramétré `(fees, hash)`, historique des 3 baselines précédentes conservé, 3 segments chiffrés |
| C4 | `ac4d81a` `test(backtest): grid terminal inventory and fee accounting` | `tests/test_scripts/test_grid_terminal_liquidation.py` : 15 tests (T1-T11), vraie stratégie à travers `run()` |
| C6 | `818f9f7` `fix(backtest): grid liquidation — holding time, realised-cash net_pnl, idempotence (review)` | `average_holding_time_minutes` exclut les liquidations (retour à la valeur pré-chantier ; durée réelle des lots liquidés dans le bloc `liquidation`), `net_pnl` grid = cash réalisé (identité par construction, `net_pnl_lot_basis` / `residual_net_proceeds` exposés), `_force_close_open_positions` idempotente ; tests T1/T4b/T6/T11 ; **second re-baseline** des hashes (H1 `43dcdf8d…`, H2 `818d7fa8…`, seule `average_holding_time_minutes` bouge vs C3) |
| C7 | `442068a` `feat(audit): verify-fees honours the dump's per-pair cost overrides` | `verify_fees` lit `payload["pair_costs"]` pour la paire du dump (plus de faux positif avec `--pair-costs-file`) + test |
| C8 | ce commit `docs(results): …` | cette note, runs de référence (rejoués sur le code final), `scripts/audit/b4_3_gate_a_reconcile.py`, `skills/backtest.md`, `PROJECT_CONTEXT.md`, `results/INDEX.md` |

Périmètre tenu : `scripts/backtest.py` (GridBacktester + une ligne du moteur signal + CLI/dump), harnais d'audit,
tests, docs d'état. Stratégies et fichiers protégés intouchés ; `market_data_ohlc` lue seulement ; collector
actif sans interruption (`krakenbot-collector` non touché, runs locaux).

## 3. Garde d) amendée — rejeu du run signal A (`grok_supertrend_4h` BTC/USDC, P6, `--interval 5`)

Sorties brutes : `results/b4_3_guard_signal_outputs.txt`. Références B4.2 : `b4_2_ref_signal_A_head.{txt,json}`
(HEAD intact), `b4_2_bybit_signal_A.json`.

| Étape | Résultat |
|---|---|
| (a) logs normalisés (`normalise-log` des deux côtés) | 5 576 / 5 576 lignes ; **2 lignes changées**, toutes deux `net_pnl` : `backtest_completed … net_pnl=22.45285652698451 → 24.19731285387008` (:1320) et `Net P&L: +22.45 → +24.20 USDC` (:1344) |
| (b) `compare` schéma 1, `--fees binance` | sans `--ignore` : `DIFFERENT: $.metrics.net_pnl` (seule différence) ; avec `--ignore metrics.net_pnl` : **IDENTICAL** |
| (c) `verify-fees --fees binance` | 46 buy/maker + 46 sell/taker-market, 0 violation |
| (d) `--fees bybit` vs `b4_2_bybit_signal_A.json` | `compare` : `$.metrics.net_pnl` seul ; `--ignore` : **IDENTICAL** ; `verify-fees` OK ; **diff byte = 1 ligne** (`net_pnl` 13.5016 → 19.3144) |
| (e) delta `net_pnl` == Σ fees de vente | binance +1.744456327 (|Δ − Σ| = 3.3e-15, fees d'achat 1.725) ; bybit +5.812818104 (9.1e-16, fees d'achat 2.30) ; **aucune autre clé** de `metrics` ne diffère |
| (e) identité cash `net_pnl == ending − 1000` (run plat 46/46) | binance +8.0e-14 ; bybit −3.6e-14 |

Fichiers : `b4_3_ref_signal_A_post.txt` (log normalisé), `b4_3_ref_signal_A_post_trades.json`, `b4_3_bybit_signal_A_post.json`.

## 4. Run e) — grid P6 de référence (`grok_grid_atr_adaptive_v4` BTC/USDC 2023-04-01 → 2026-04-01, `--fees binance`)

Même commande que B4.2 étape 0. Réconciliation par `scripts/audit/b4_3_gate_a_reconcile.py` (pur, read-only) du
run réel contre le baseline `b4_2_ref_grid_A_head.json` : chaque delta est **re-dérivé du baseline seul** (lots
ouverts reconstruits par appariement exact des SELL aux BUY sur `amount_crypto`, 0 orphelin) puis comparé au run.

| Check | B4.2 baseline | Run post-chantier 0 | Expected / bound | Note | OK |
|---|---|---|---|---|---|
| determinism (capture run 1 == run 2) | - | IDENTICAL | IDENTICAL |  | ✅ |
| D4: capture (kwarg absent) == dump (pair_costs=None) | - | IDENTICAL | IDENTICAL |  | ✅ |
| baseline trades are a bit-identical prefix | 2097 | 2097 | 2097 |  | ✅ |
| extra trades == L open lots, all tagged forced_liquidation | 0 | 33 extra / 33 tagged | 33 |  | ✅ |
| liquidation price == reference × (1 − spread − slippage) | - | 68219.687952000000 (ref 68240.16000000) | 68219.687952000000 |  | ✅ |
| liquidation fee == gross × taker, liquidity taker | - | all | rate 0.00075 |  | ✅ |
| implied liquidation entries ∈ open entries (per-lot cost basis) | 33 lots | 33 matched / 0 unmatched | all matched |  | ✅ |
| no SELL amount more frequent than in the BUY multiset | - | ok | ok |  | ✅ |
| Σ open lots ≈ baseline btc_held (Decimal drift < 1e-12) | 0.008762229963832720701544122501 | 0.008762229963832720701544122512 | |Δ| < 1e-12 |  | ✅ |
| liquidation pnl == Σ_lots(q·C(1−s)(1−t) − q·entry) | 0 | -227.072974 | -227.072974 |  | ✅ |
| liquidation fees == Σ q·C(1−s)·t | 0 | 0.448317 | 0.448317 |  | ✅ |
| total_fees == old + liquidation fees | 39.600897 | 40.049215 | 40.049215 |  | ✅ |
| total_pnl == old + liquidation pnl | 375.914265 | 148.841292 | 148.841292 |  | ✅ |
| net_pnl == total_pnl − buy fees | 336.313368 | 128.872542 | 128.872542 |  | ✅ |
| net_pnl delta == old sell fees + liquidation pnl (sign pre-declared) | - | -207.440826 | -207.440826 |  | ✅ |
| cash identity net_pnl == ending_balance − capital (≤ 1e-9) | - | 128.872541788 | 128.872541788 |  | ✅ |
| ending_balance == old − V·(1 − (1−s)(1−t)) | 1129.500240 | 1128.872542 | 1128.872542 |  | ✅ |
| total_return_pct strictly lower | 12.950024 | 12.887254 | 12.887254 |  | ✅ |
| total_trades == old + L | 1032 | 1065 | 1065 |  | ✅ |
| winning / losing == old + winners / losers | 1032/0 | 1032/33 | 1032/33 |  | ✅ |
| win_rate | 1.000000 | 0.969014 | 0.969014 |  | ✅ |
| profit_factor == Σwins / Σ|losses| (↓ or inventory in profit) | inf | 1.655478 | 1.655478 |  | ✅ |
| max_drawdown_pct non-decreasing, +≤ liquidation cost (conditional, read at run) | 19.699293 | 19.699293 | [19.699293, +0.0556 pt] |  | ✅ |
| sharpe_ratio (conditional: down on this config) | 0.023707 | 0.023614 | ≤ old | one extra bar return | ✅ |
| sortino_ratio (conditional: down on this config) | 0.033857 | 0.033725 | ≤ old |  | ✅ |
| calmar_ratio (derived) | 0.218928 | 0.217867 | ≤ old |  | ✅ |
| unrealized_pnl == liquidation pnl | 0.0 | -227.072974 | -227.072974 |  | ✅ |
| average_holding_time_minutes unchanged (maker pairs only; liquidations excluded) | 1439.249031 | 1439.249031 | 1439.249031 |  | ✅ |
| net_pnl (realised cash) == net_pnl_lot_basis (lot accounting agrees with the wallet) | - | 128.872541788 | 128.872541788 |  | ✅ |
| liquidation avg holding (from lot entry times) reported | - | 152131.81818181818 | > 0 when L > 0 |  | ✅ |
| pairs_completed unchanged (maker pairs) | 1032 | 1032 | 1032 |  | ✅ |
| grid_profit unchanged | 375.9142653371057294399810758 | 375.9142653371057294399810758 | 375.9142653371057294399810758 |  | ✅ |
| total_orders_placed / rebalance_count unchanged | 26058/3787 | 26058/3787 | = |  | ✅ |
| fills: buy =, sell + L, force_closed == L | {'buy': 1065, 'force_closed': 0, 'sell': 1032} | {'buy': 1065, 'force_closed': 33, 'sell': 1065} | buy 1065, sell 1065, force_closed 33 |  | ✅ |
| btc_held after liquidation == 0 | 0.008762229963832720701544122501 | 0 | 0 |  | ✅ |
| liquidation block: positions == L, residual 0, |dust| & |divergence| < 1e-12 | - | pos 33 res 0 dust -9.8E-30 div -1.1E-29 | pos 33 |  | ✅ |
| liquidation block: buy_fees == old buy fees (no new buy) | 19.968750 | 19.968750 | 19.968750 |  | ✅ |

- **37/37 checks.** Les 2 097 premiers trades sont bit-identiques au B4.2 ; 33 trades taker ajoutés
  (`sell/taker-market 33` au `verify-fees`, 1 065 buy/maker, 1 032 sell/maker, 0 violation) ; chaque entrée
  implicite de liquidation `(gross − fee − pnl)/q` est l'une des 33 entrées ouvertes ; `pairs_completed`,
  `grid_profit`, `total_orders_placed`, `rebalance_count` inchangés.
- Signes pré-déclarés tenus : PF, return, ending ↓ ; le seul delta positif (+19.6321 de fees de vente plus
  comptées deux fois) est absorbé par −227.0730 de liquidation (delta `net_pnl` −207.4408 exact).
- Conditionnels lus au run : `max_drawdown_pct` **inchangé** (le run ne finissait pas dans son creux) ; Sharpe,
  Sortino, Calmar en baisse (un retour 5 m de −5.6e-4 de plus).
- Déterminisme : deux captures (`capture` du harnais, kwarg absent) **identiques** (schéma 1) ; logs normalisés
  identiques sur 326 362 lignes (seule la ligne finale du harnais diffère : chemin de sortie) ; les sha256 des logs
  de capture sont **identiques à ceux du premier rejeu** (avant C6) : le correctif de revue n'a touché aucune ligne
  du log moteur.
- Bloc rapport versionné : `b4_3_ref_grid_A_post.report.txt` ; log brut 130 Mo non versionné (sha256 des logs
  normalisés dans `b4_3_step0_baselines.txt`).

**`--fees bybit`** (info B4.3, `b4_3_bybit_grid_A_post.json` vs `b4_2_bybit_grid_A.json`) : 1 064 BUY / 1 031 paires
maker / **33 liquidations** à 68 212.86 (taker 0.25 %, spread 0.02 %, slippage 0.02 %) : liquidation
**−228.12 USDC**, fees +1.49, PF inf → **1.617**, `win_rate` 0.969, ending 1 115.94 → **1 114.21** (return
+11.59 % → **+11.42 %**), `net_pnl` 316.18 → **114.21 = `ending − 1000`** (identité exacte, = lot-basis, résidu 0),
MaxDD 19.989 % inchangé, `average_holding_time_minutes` 1 434.86 inchangé, `verify-fees --fees bybit` OK
(1 064 / 1 031 / 33). Chiffres bruts : la lecture stratégique est la campagne, pas ce chantier.

## 5. Fenêtre gold hash (BTC/USDC 2025-03-01 → 03-15, runner P6 : train / test / all)

Réconciliation du segment `all` (`b4_3_ref_grid_quick_post.json` vs `b4_2_ref_grid_quick_head.json`) :

| Check | B4.2 baseline | Run post-chantier 0 | Expected / bound | Note | OK |
|---|---|---|---|---|---|
| D4: capture (kwarg absent) == dump (pair_costs=None) | - | IDENTICAL | IDENTICAL |  | ✅ |
| baseline trades are a bit-identical prefix | 82 | 82 | 82 |  | ✅ |
| extra trades == L open lots, all tagged forced_liquidation | 0 | 8 extra / 8 tagged | 8 |  | ✅ |
| liquidation price == reference × (1 − spread − slippage) | - | 83970.671239000000 (ref 83995.87000000) | 83970.671239000000 |  | ✅ |
| liquidation fee == gross × taker, liquidity taker | - | all | rate 0.00075 |  | ✅ |
| implied liquidation entries ∈ open entries (per-lot cost basis) | 8 lots | 8 matched / 0 unmatched | all matched |  | ✅ |
| no SELL amount more frequent than in the BUY multiset | - | ok | ok |  | ✅ |
| Σ open lots ≈ baseline btc_held (Decimal drift < 1e-12) | 0.002249232395154730539555237640 | 0.002249232395154730539555237640 | |Δ| < 1e-12 |  | ✅ |
| liquidation pnl == Σ_lots(q·C(1−s)(1−t) − q·entry) | 0 | -11.122098 | -11.122098 |  | ✅ |
| liquidation fees == Σ q·C(1−s)·t | 0 | 0.141652 | 0.141652 |  | ✅ |
| total_fees == old + liquidation fees | 1.547622 | 1.689274 | 1.689274 |  | ✅ |
| total_pnl == old + liquidation pnl | 13.486072 | 2.363974 | 2.363974 |  | ✅ |
| net_pnl == total_pnl − buy fees | 11.938450 | 1.520224 | 1.520224 |  | ✅ |
| net_pnl delta == old sell fees + liquidation pnl (sign pre-declared) | - | -10.418226 | -10.418226 |  | ✅ |
| cash identity net_pnl == ending_balance − capital (≤ 1e-9) | - | 1.520224294 | 1.520224294 |  | ✅ |
| ending_balance == old − V·(1 − (1−s)(1−t)) | 1001.718554 | 1001.520224 | 1001.520224 |  | ✅ |
| total_return_pct strictly lower | 0.171855 | 0.152022 | 0.152022 |  | ✅ |
| total_trades == old + L | 37 | 45 | 45 |  | ✅ |
| winning / losing == old + winners / losers | 37/0 | 37/8 | 37/8 |  | ✅ |
| win_rate | 1.000000 | 0.822222 | 0.822222 |  | ✅ |
| profit_factor == Σwins / Σ|losses| (↓ or inventory in profit) | inf | 1.212548 | 1.212548 |  | ✅ |
| max_drawdown_pct non-decreasing, +≤ liquidation cost (conditional, read at run) | 3.050866 | 3.050866 | [3.050866, +0.0198 pt] |  | ✅ |
| sharpe_ratio (conditional: down on this config) | 0.023140 | 0.020939 | ≤ old | one extra bar return | ✅ |
| sortino_ratio (conditional: down on this config) | 0.033770 | 0.030557 | ≤ old |  | ✅ |
| calmar_ratio (derived) | 1.468605 | 1.299120 | ≤ old |  | ✅ |
| unrealized_pnl == liquidation pnl | 0.0 | -11.122098 | -11.122098 |  | ✅ |
| average_holding_time_minutes unchanged (maker pairs only; liquidations excluded) | 323.783784 | 323.783784 | 323.783784 |  | ✅ |
| net_pnl (realised cash) == net_pnl_lot_basis (lot accounting agrees with the wallet) | - | 1.520224294 | 1.520224294 |  | ✅ |
| liquidation avg holding (from lot entry times) reported | - | 12108.75 | > 0 when L > 0 |  | ✅ |
| pairs_completed unchanged (maker pairs) | 37 | 37 | 37 |  | ✅ |
| grid_profit unchanged | 13.48607246560646306534356430 | 13.48607246560646306534356430 | 13.48607246560646306534356430 |  | ✅ |
| total_orders_placed / rebalance_count unchanged | 367/56 | 367/56 | = |  | ✅ |
| fills: buy =, sell + L, force_closed == L | {'buy': 45, 'force_closed': 0, 'sell': 37} | {'buy': 45, 'force_closed': 8, 'sell': 45} | buy 45, sell 45, force_closed 8 |  | ✅ |
| btc_held after liquidation == 0 | 0.002249232395154730539555237640 | 0 | 0 |  | ✅ |
| liquidation block: positions == L, residual 0, |dust| & |divergence| < 1e-12 | - | pos 8 res 0 dust -2E-31 div 0E-30 | pos 8 |  | ✅ |
| liquidation block: buy_fees == old buy fees (no new buy) | 0.843750 | 0.843750 | 0.843750 |  | ✅ |

- 36/36 checks ; `verify-fees` binance et bybit OK (45 / 37 / 8) ; identité cash binance −3.6e-14, bybit −2.8e-14 ;
  `average_holding_time_minutes` 323.78 inchangé (paires maker), les 8 lots liquidés détenus 8.4 jours en moyenne.
- Segments (`--fees binance`, split 2025-03-10T19:12Z, dernier close 5 m du train 77 695.99) : **train** 38 trades
  (25 W / 13 L = 13 lots liquidés, liquidation −30.42, `net_pnl` −21.99 == ending 978.01 − 1000, MaxDD 2.84 %) ;
  **test** 6 trades (6 W, inventaire vide en fin, 0 liquidation, `net_pnl` 2.02) ; **all** 45 trades (37 W / 8 L,
  liquidation −11.12, PF 1.2125, ending 1 001.52, MaxDD 3.05 %, `net_pnl` 1.52 == ending − 1000). Le fix b) seul a
  déplacé `net_pnl` de +Σ fees de vente exactement (+0.6965 / +0.1141 / +0.8455), toutes les autres clés
  bit-identiques entre C1 et C2.
- Hashes figés dans un seul commit post-fixes (C3 : H1 `71d68b95…`, H2 `97cae113…`), puis **re-baselinés une
  seconde fois à C6** après le correctif de revue (`average_holding_time_minutes` : all 594.22 → 323.78 = valeur
  pré-chantier, train 227.76 → 286.40, test inchangé ; aucune autre clé ne bouge) : **H1 binance `43dcdf8d…`**,
  **H2 bybit `818d7fa8…`** (all bybit : 45 trades, 8 L, PF 1.1552, liquidation −11.47, `net_pnl` 0.65 == ending − 1000).

## 6. Tests et validation 7.4

- Nouveau `tests/test_scripts/test_grid_terminal_liquidation.py` (15 tests, sans DB) : reachability à travers le
  vrai `run()` avec la vraie stratégie (T1 bybit / T2 binance ; durée de détention exclue de la statistique maker et
  reportée dans le bloc `liquidation`), `pair_costs` au site de liquidation seulement et bare ≡ `pair_costs=None`
  (T3), inventaire vide sans fill et paire complétée (T4a/T4b, `net_pnl != total_pnl − total_fees` figé dehors),
  `net_pnl` grid et signal avec identité cash (T5/T5b), lot fantôme clampé et BTC sans lot avec identité cash
  conservée et écart lot-basis exposé (T6), dust ±1e-20 (T7), parité legacy (T8), pas de candle tradeable (T9),
  schéma `to_dict()` 18 clés + dump signal inchangé (T10), idempotence sur snapshot complet (T11). Mis à jour : `test_grid_fee_sites.py`, `test_grid_metrics.py`,
  `test_backtest_cli.py`, `test_backtest_fee_model.py`, `test_backtest.py`, `test_b4_2_reference_capture.py`
  (`--ignore`), gold hash paramétré.
- Validation 7.4 (`results/b4_3_validation_outputs.txt`) : suite complète `pytest -q -p no:cacheprovider -W error::ResourceWarning`
  (tunnel ouvert, gold hashes H1/H2 inclus, `test_run_p6_determinism.py` à part) en **trois ordres** (A défaut, B
  fichiers inversés, C « victimes d'abord ») sur le commit final `442068a` : **1 318 passés, 6 skipped (intégration
  Bybit), 0 échec, 0 error** dans les trois (1 300 B4.2 + 15 nouveaux + 2 tests du harnais + 2ᵉ hash) ; lane
  déterminisme rapide
  (`-m "not slow"`, tunnel) : 6 passés ; `ruff check` propre ; `ruff format --check` : seuls `scripts/p6_5_diagnose_*`
  (dette 10 préexistante) ; `mypy src/ --ignore-missing-imports` : 64 erreurs / 18 fichiers = baseline B4.2 (aucune
  nouvelle). Dérogation 1 : à C1 et C2 le gold hash DB-gated était rouge (attendu, annoncé), suite sans DB verte.

## 7. Revue adversariale du diff (43 agents read-only : 6 lenses, 2 vérificateurs par constat, recalcul indépendant)

18 constats bruts → **13 confirmés** (≥ 2 vérificateurs), regroupés en 4 défauts réels, tous corrigés (C6/C7) :

| Défaut confirmé | Correctif |
|---|---|
| `average_holding_time_minutes` pollué : les L liquidations partagent `final_ts` → l'heuristique « dernier BUY précédent » leur attribuait toutes la même durée (P6 : 1 439 → 1 992 min, +38 %, non déclaré, hashé dans H1/H2) | liquidations **exclues** de la statistique (paires maker seulement → retour à la valeur pré-chantier, delta 0) ; durée réelle des lots (`entry_time` → `final_ts`) dans `liquidation.avg_holding_minutes` ; check ajouté au script de réconciliation |
| Identité cash rompue dans le cas résiduel (BTC sans lot : proceeds crédités, `total_pnl` non) — atteignable si le « mauvais pop » diverge | `net_pnl` grid = **cash réalisé** après liquidation (identité par construction) ; `net_pnl_lot_basis` (= `total_pnl − fees d'achat`) et `residual_net_proceeds` exposés ; T6 fige l'écart, le script de réconciliation vérifie `net_pnl == net_pnl_lot_basis` et résidu 0 sur les références |
| `_force_close_open_positions` non idempotente (un 2ᵉ appel reconstruisait les lots depuis la stratégie, écrasait `unrealized_pnl` à 0 et corrompait la divergence) | garde `_terminal_liquidation_done` ; T11 compare un snapshot complet |
| `verify-fees` : faux positif sur tout dump grid produit avec `--pair-costs-file` (globaux attendus) | le harnais lit `pair_costs` du dump pour sa paire (C7) + test |

Constats mineurs traités en doc : références de lignes de cette note = base `539c339` (en-tête) ; docstring
`src/krakenbot/models/trades.py:588,691` (`net_pnl = total_pnl − total_fees`) et lignes `backtest_runs` écrites
avant B4.3 avec `--save` (ancienne convention, sommées par le dashboard) → annexe § 9. Recalcul indépendant des
deltas P6 depuis le baseline seul (Decimal prec 60) : **aucun écart > 1e-9** (écarts de sommation ≤ 1.6e-26).
Constats non confirmés (1/2 réfuté) : variantes du cas résiduel et de l'idempotence, couvertes par les correctifs.

## 8. Preuve D4 (décision Bruno)

`GridBacktester` construit **sans** le kwarg (harnais `capture`, runner P6 / gold hash) et **avec** `pair_costs=None`
passé explicitement (`backtest.py --trades-out`) : `compare` IDENTICAL sur le schéma 1 pour P6 (2 130 trades) et la
fenêtre rapide (90 trades) ; unitairement, `bare._pair_costs == explicit._pair_costs == {}` et les runs synthétiques
T3 sont bit-identiques (trades et `to_dict()`). Un override pour une autre paire retombe sur les globaux.

## 9. Dérogations accordées et exigences opposables (GO Bruno, 2026-09-14)

1. Gold hash DB-gated **rouge à C1 et C2 tunnel ouvert** (annoncé dans les messages de commit ; suite sans DB verte
   à chaque commit : 1 300 passés à C1, 316 tests backtest/scripts à C2 ; CI non concernée) ; re-baseline **unique à
   C3** (H1 + H2) — **puis un second re-baseline à C6**, imposé par le correctif de revue (`average_holding_time_minutes`
   revient à sa valeur pré-chantier ; seule clé qui bouge, les deux hashes dans le même commit). Consigné ici.
2. `unrealized_pnl` porte le P&L de liquidation (stabilité du schéma : 18 clés `to_dict()`, gold hash, harnais) ;
   commentaire explicite dans `BacktestMetrics` ; rename consigné en annexe.
- Table § 3 du plan = contrat : réconciliée ligne à ligne (§ 4), conditionnels lus au run et consignés, **aucun
  écart** hors conditionnels. Red flags appliqués tels quels (identité cash à 1e-12 sur les deux moteurs — mesuré
  ≤ 8e-14 ; delta `net_pnl` == +19.6321 − |liquidation| — exact).
- Preuve D4 sur les deux chemins de construction (§ 7). « Mauvais pop » non corrigé : instrumenté
  (`inventory_divergence_btc` = −1.1e-29 sur P6, = dérive Decimal), annexe § 9.

## 10. Annexes consignées (non faites)

- Stratégie grid : fermeture de position par proximité de prix (`|sell_level − prix| < 1`, :631-634) vs
  appariement moteur par `position_id` → lot fantôme possible ; détecté par `inventory_divergence_btc` et le contrôle
  multiset du script de réconciliation ; corrigible seulement dans le fichier protégé. Branche :1805-1806
  (`matched_position is None`) inatteignable sur le chemin grok, à marquer défensive.
- Moteur signal : pas de liquidation de fin de run (stock DCA valorisé sans fee) — forme générale de l'invariant :
  `net_pnl == ending − capital − valeur de l'inventaire ouvert` ; sorties limit marketables facturées maker (n10) ;
  `min_profitable = prix × 1.0064` (stratégie :590, calibré Kraken) — à traiter au GATE B.
- `src/krakenbot/models/trades.py:588,691` (docstring et commentaire de colonne `net_pnl = total_pnl −
  total_fees`) à aligner au merge ; les lignes `backtest_runs` écrites avant B4.3 avec `--save` portent l'ancienne
  convention et sont sommées avec les nouvelles par `dashboard.py:546` (marqueur de convention absent) ;
- « mauvais pop » : outre le lot fantôme, une position déjà vendue peut être re-liquidée (clampée à `btc_held`) —
  la divergence est exposée, la double comptabilisation de son coût de base est compensée dans `net_pnl` (cash) ;
  `unrealized_pnl` mal nommée (renommer = schéma) ; `fees` absent de `backtest_runs` ; chemin grid legacy non-grok à
  supprimer (réécrire `test_grid_metrics.py`) ; `_initialize_grid` vide `active_sell_orders` sans toucher `btc_held`
  (legacy) ; `dashboard.py` grid routée vers le moteur signal ; gold hash à étendre à la liste de trades ;
  `verify-fees` avec coûts par paire (commit campagne) ; `docs/CODE_MAP.md` :126/:152 (prose « no-op sur le chemin
  grok », « taker sans spread ») régénéré au merge.

## 11. Fichiers produits (`results/`)

`b4_3_step0_baselines.txt` (baselines HEAD + sha256 des logs P6), `b4_3_guard_signal_outputs.txt`,
`b4_3_ref_signal_A_post.txt` / `b4_3_ref_signal_A_post_trades.json` / `b4_3_bybit_signal_A_post.json`,
`b4_3_ref_grid_A_post.json` / `b4_3_ref_grid_A_post_trades.json` / `b4_3_ref_grid_A_post.report.txt` /
`b4_3_bybit_grid_A_post.json`, `b4_3_ref_grid_quick_post.json` / `b4_3_ref_grid_quick_post_trades.json` /
`b4_3_bybit_grid_quick_post.json`, `b4_3_validation_outputs.txt`, cette note. Les captures grid B4.2
(`b4_2_ref_grid_*`) restent comme **baselines supersédées** (biais de survie documenté).

## 12. Suite (après GO A)

GATE B (`results/B4_3_gate_b_configs.md`, brief § 5) : coûts par paire depuis le summary q3 de Bruno →
`config/pair_costs_b4.json` (signal + liquidation grid) ; cartographie risk backtest-visible vs runtime ; grilles
P7 avec plancher de spacing recalculé pour Bybit (proposition 2.0 %) ; exécution serveur (3 workers, tmux, durée,
disque) ; sorties `results/B4_P6_*` / `B4_P7_*`, jamais de `--force` sur legacy. Zéro run avant le GO B.
