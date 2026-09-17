# C2 — Fidélité du replay : rapport (avant/après, preuves, constats)

> Brief : `agent/chantier2_replay_v2.md` (v2.1). Plan approuvé le 2026-09-17 (Bruno) après revue adversariale.
> Branche `feat/c2-replay` depuis `dev` @ `a07eb73` (src/scripts/tests identiques au tag `v2.9.0-c1-metrics` @ `51be3e8`).
> **Ce rapport ne porte aucun verdict économique** : les écarts avant/après sont attribués aux correctifs R1-R4 ;
> le verdict appartient au rejeu diagnostic grid (phase suivante) sous protocole C3.
>
> État : **gate 2** — commits 1-11 posés, tableau de re-baseline des gold hashes (§ 7) soumis à review ; docs après GO.

## 0. Étape 0 — baselines et références « avant » (tag `v2.9.0-c1-metrics`)

- `mypy src/` à `a07eb73` : **65 erreurs / 18 fichiers** (C1 en consignait 64 ; baseline constatée, à ne pas dépasser).
- `pytest -q -k "not determinism"` à `a07eb73` (tunnel actif) : **1 418 passés, 6 skippés, 30 désélectionnés** (les 30 tests de
  déterminisme P6 ont bloqué 25 min sur le tunnel SSH à 0 % CPU pendant le premier baseline ; ils sont rejoués à la porte
  pré-merge, tunnel vérifié d'abord, sans nouvelle désélection). Les 9 échecs du baseline étaient les tests R4 écrits avant
  l'application du diff.
- mypy : la 65e erreur est nommée — `src/krakenbot/ml/features/feature_store.py:32: Library stubs not installed for "pandas"
  [import-untyped]`, supprimée par `--ignore-missing-imports` que les baselines B4.2/B4.3/C1 utilisaient (« 64 ») ; listes
  d'erreurs identiques au tag et sur la branche (65 sans le flag, 64 avec).
- Références C1 en place (sha256 16) : `c1_ab/signal_A_bybit_new.json` `c8e5832e17446caa`, `grid_quick_binance_new.json`
  `bf6d492129fc5aa3`, `grid_quick_bybit_new.json` `04d109094a388d2f` (= `results/C1_metrics_report.md` § 3).
- Worktree `~/wt-c1-ref` = `51be3e8` (tag). Captures « avant » faites **avant tout commit touchant `src/`**
  (`c1_equity_probe.py capture --engine-root ~/wt-c1-ref` ne substitue que `scripts/backtest.py` : `krakenbot` est importé
  depuis `src/` du tree courant, identique au tag à ce stade — `git diff --stat v2.9.0-c1-metrics..a07eb73 -- src scripts tests` vide).

| Capture (`results/c2_ab/`) | Commande | sha256 (16) |
|---|---|---|
| `signal_A_bybit_ref.json` | `grok_supertrend_4h BTC/USDC --exchange binance --start-date 2023-04-01 --end-date 2026-04-01 --interval 5 --capital 1000 --fees bybit` | `3e1317167d9861fe` (92 trades, 6 577 points, `net_pnl` 19.314423 = C1) |
| `grid_quick_binance_ref.json` | `grok_grid_atr_adaptive_v4 BTC/USDC … 2025-03-01 → 2025-03-15 --fees binance` | `c1b3e1e7b6032501` (90 trades, 4 034 points, `net_pnl` 1.520224 = C1) |
| `grid_quick_bybit_ref.json` | idem `--fees bybit` | `d8a59dad6bf2a8e2` (90 trades, `net_pnl` 0.654538 = C1) |
| `grid_A_bybit_ref.json.gz` (non versionné) | `grok_grid_atr_adaptive_v4 BTC/USDC … 2023-04-01 → 2026-04-01 --fees bybit` | fichier gz `68a5eb1cd21ac335`, texte canonique `b18d523d4b876a59` (2 128 trades, 315 650 points, `net_pnl` 114.206947 = C1) |
| `dca_2022_bybit_ref.json` | `grok_adaptive_dca_weekly BTC/USDC … 2022-01-01 → 2022-09-28 --fees bybit --min-order-usdc 5` | `50cdf06a20a72d58` (36 achats, 271 points, return −16.46 %, `net_pnl` −0.495 = −Σ fees d'achat) |

Empreintes des sources exécutées côté « avant » (sha256 16, identiques dans le worktree du tag et dans l'arbre à ce stade) :
`scripts/backtest.py` `a82a485a4fe1e3fb`, `grok_grid_atr_adaptive_v4.py` `f220f15738ed2f95`, `grok_supertrend_4h.py` `815ba42b06c0ab2f`,
`grok_adaptive_dca_weekly.py` `6da1b07d7f2942fd`. Captures faites du 2026-09-17 06:38 au 06:46 UTC, avant tout commit de code.

## 0 bis. Discipline — relecture des patchs préparés

Les scripts de patch des commits 4-8 et le module `replay_contract.py` ont été préparés avant la validation du gate R4 :
écart de discipline consigné par Bruno (le plan imposait l'arrêt). Conséquence appliquée : **chaque patch a été relu contre
le plan corrigé au moment de son application**, avec deux corrections issues de cette relecture — (a) commit 7 : le brouillon
R3 ré-ajoutait aux listes pendantes un ordre legacy rejeté (changement de comportement) → retiré, l'ordre reste abandonné
comme avant, seuls les compteurs s'ajoutent ; (b) commit 9 : la validation R4 « inventaire suffisant » rejetait une vente
de lot dont le montant dépassait `btc_held` de ~1e-29 BTC (arrondi Decimal des sommes, pas un manque d'inventaire) — garde
identique pré-C2 qui bloquait ces lots en silence jusqu'à la liquidation terminale ; tolérance = seuil de poussière B4.3
(`_INVENTORY_DUST_BTC`). Au gate 2 (gold hashes) : arrêt strict, rien n'est préparé au-delà.

## 1. Défauts → correctifs

| # | Défaut (audit red-team 16/09) | Correctif C2 | Commit |
|---|---|---|---|
| R1 | Grid : bougies 5 m taguées 240 nourrissant les indicateurs « 4 h », décision à chaque 5 m, série 4 h absente après `start` | `ReplayEvent` à trois rôles — `exec` (5 m : fills, prix, equity), `ctx` (1 w/1 d), `decision` (4 h, clôtures ≥ `start`) ; 4 h chargé sur tout le run ; ordre `(timestamp, phase)` = exécution → 1 w → 1 d → décision 4 h ; garde `--interval < 240` ; N1 `--cross-validate` × grid refusé | `10fe39b` |
| R2 | Préenregistrement hardcodé (EMA 20/50 4 h, ST (10,3.0), Donchian (20,10)), aucun pour le grid, EMA200 1 d du DCA jamais créée, warmup en jours | `indicator_requirements` aux attributs effectifs des 8 stratégies, `preregister_indicators` sur les deux moteurs, warmup en bougies (règle monotone bornée, suffisance = comptage ∧ staleness ∧ trous), bloc `warmup` exporté, bougie à `start` nourrie une fois | `808219d` |
| R3 | Rejets invisibles (min order = warning, limite non touchée = debug, SELL à plat / BUY en position silencieux, cash / inventaire = `return`) | `RejectionLedger` par (ordre distinct, cause), 5 clés minimales + extensions, identités d'ordre stables, `dca_counters`, blocs exportés (dumps, runners, probe) | `7c56d72` |
| R4 | Stratégie : `|sell_level − prix| < 1` USD (double pop SOL) ; moteur : soldes mutés avant validation du lot | Stratégie : appariement par id sans fallback, sans id = lot unique au prix exact, sinon réconciliation (log + compteur, pas de BUY de remplacement) ; SELL apparié avec `amount_btc`, sans `position_id` ; moteur : validation (id, quantité, inventaire à la poussière près) avant toute mutation, post-condition `RuntimeError` | `a7a5e10`, `2f13a39`, `508adae` |
| — | Provenance | `replay_version` 2 au top-level (entrées P6/P7/WF, dumps, captures) ; refus de reprise / amorçage / rapport sur fichier sans clé, `--force` inclus ; chemin legacy v1 de `p7_report` intact ; rows DB hors périmètre (dette) | `c4b57e5` |
| — | Mode strict du comparateur | `compare-ab --strict` : toutes les clés, `buy_fee_alloc`, `liquidation`, fees / coûts ; seuls `git_head` / `engine_file` / `source_fingerprints` peuvent différer, additions limitées aux blocs C2 ; test négatif | `402f446` |

## 2. Preuves

| Preuve | Résultat |
|---|---|
| 1 harnais indicateurs + ordre temporel | `test_c2_replay_fidelity.py` (synthétique) : ATR 4 h / régime 1 d / régime 1 w de chaque décision == recalcul indépendant sur les bougies clôturées ≤ T, la bougie 4 h suivante casse l'égalité ; ordre créé à T non rempli sur la bougie de T ; ordre préexistant touché à T rempli avant le recalc de T ; SELL créé par le callback d'un BUY rempli à T inéligible à T ; `test_c2_replay_fidelity_db.py` : idem sur la fenêtre réelle BTC 2025-03-01 → 03-15 (85 décisions = une par clôture 4 h) — **vert** |
| 2 lazy 8/8 | `test_c2_warmup_requirements.py` : table ⊇ tous les `analyzer.get_*` des 8 sources (grep), préenregistrement sous la clé exacte et readiness après exactement `besoin` bougies (défauts + une variante par indicateur paramétré : ST (8, 2.0), EMA 20/125, Donchian (15, 10), ATR 21, RSI 9, DCA EMA 200), aucune création lazy à la lecture, TF consommés ⊆ chargés, valeur == recalcul (EMA 125/200, ATR 21, RSI 9, Donchian) — gemini : référence = flux réellement reçu (double alimentation, § 6), preuve de la mécanique du replay, pas de la justesse de leurs indicateurs ; chargeur : no-op si suffisant, extension bornée, staleness / trou / vide signalés `sufficient=False` ; bougie à `start` nourrie une fois — **vert** |
| 3 compteurs | `test_c2_rejections.py` : cas B4 exact `bull_reduction` 0.3 × 15 = 4.50 < 5 → `below_min_order` une fois par ordre hebdomadaire (events à part ; défaut 0.5 → 7.5 exécuté) ; clamp cash → `insufficient_cash` ; no-ops silencieux comptés ; niveau grid sans cash retesté 10 bougies = 1 ordre / 10 events ; niveau recréé = nouvel ordre ; 5 clés imposées présentes sur les deux moteurs ; bloc dans les dumps — **vert** |
| 4 appariement | `test_c2_grid_matching.py` : chemins id présent / absent / ambigu / incohérent ; deux lots à `sell_level` strictement identique (l'id tranche) ; double pop SOL reproduit (ancien matching recopié → 2 ventes du même lot ; nouveau → 1 vente, seconde rejetée et comptée) ; 5 assertions après chaque vente ; aucune mutation sur id inconnu / inventaire insuffisant ; `RuntimeError` sur quantité ≠ lot ou lot non fermé ; poussière tolérée, manque réel rejeté — **vert** ; rejeu P6 réel : § 3.4 |
| 5 invariant | `compare-ab --strict` signal A tag vs branche : **`STRICT IDENTITY OK`** (exit 0) — 92 trades, 6 577 points d'equity, `net_pnl` 19.314423, toutes clés de métriques, `buy_fee_alloc`, soldes, fees identiques ; capture `results/c2_ab/signal_A_bybit_c2.json` (sha256 16 `a62c0c87aba2caa5`, commit `c4b57e5`) ; test négatif du mode strict dans `test_c1_equity_probe.py` |
| 6 avant/après | § 3 |
| 7 suite | commits 1-10 : `pytest -q -k "not determinism"` = 1 502 passés + tests C2 (seuls les 2 gold hashes grid échouent, attendu jusqu'au recalage) ; ruff / format verts ; mypy `src/` = 65 (= baseline nommée) ; porte pré-merge (déterminisme ×30, tunnel vérifié) après le gate 2 |

## 3. Avant / après (sans verdict)

### 3.1 Signal A SuperTrend BTC 2023-04-01 → 2026-04-01 (`--fees bybit`) — invariant strict

Identité byte-à-byte (mode strict) : aucune clé ne bouge. Seules différences : `git_head` (`51be3e8` → `c4b57e5`), `engine_file`,
`source_fingerprints` ; additions C2 : `replay_version` 2, `rejections` (`limit_expired` = entrées limit non touchées en N+1,
information nouvelle), `warmup` (4 h 91 ≥ 14, 1 d ~86 ≥ 50 malgré le trou BTC 2022-09-29 → 2023-03-12 signalé par
`largest_gap_candles`). Le flux d'initialisation des indicateurs de la référence est inchangé par construction (aucune
extension) — les EMA 20/50 4 h que le tag préenregistrait sans les lire ne le sont plus, sans effet mesurable.

### 3.2 DCA de référence BTC 2022-01-01 → 2022-09-28 (`--fees bybit --min-order-usdc 5`, défauts de classe)

| Clé | Avant (tag) | Après (C2) | Attribution |
|---|---|---|---|
| achats exécutés | 36 | 36 | — |
| montants d'achat (USDC) | {7.5, 15} Σ 495.00 | {7.5, 15, 18.75, 37.5} Σ 551.25 | **R2** : EMA 200 1 d préenregistrée et prête à `start` (warmup 1 d 251 bougies ≥ 200) → branche oversold active dès janvier : 3 achats ×2.5 (37.5) et 1 achat ×2.5 × 0.5 (18.75) ; au tag, l'EMA 200 était créée au premier lundi ≥ `start` et prête ~200 jours plus tard (branche muette sur la fenêtre) |
| `total_fees` / `net_pnl` | 0.495 / −0.495 | 0.55125 / −0.55125 | R2 (Σ fees d'achat = 0.1 % du notionnel, aucune vente) |
| `total_return_pct` / `ending_balance` | −16.46 % / 835.37 | −17.18 % / 828.18 | R2 (exposition BTC plus grande sur une fenêtre où le BTC baisse) |
| `max_drawdown` / `max_drawdown_pct_daily` | 201.05 / 19.59 % | 213.30 / 20.72 % | R2 |
| `sharpe_ratio` / `sortino_ratio` / `calmar_ratio` | −1.535 / −1.957 / −1.102 | −1.397 / −1.807 / −1.086 | R2 |
| `total_trades`, `win_rate`, `total_pnl`, `duration_days` | identiques | identiques | — |

**Compteurs descriptifs mesurés (après, `dca_counters` + `rejections`)** : 39 lundis évalués, 39 signaux (30 `base`, 5
`bull_reduce`, 3 `oversold_boost`, 1 `oversold_boost+bull_reduce`), 36 achats exécutés, **3 `limit_expired`** — les trois
lundis sans achat sont des ordres limit à 0.999 × close non touchés par le low de la bougie quotidienne suivante (2 signaux
`base` et 1 `oversold_boost` : 28 × 15 + 5 × 7.5 + 2 × 37.5 + 18.75 = 551.25 ✓ ; au tag les mêmes 36 fills, sans boost :
30 × 15 + 6 × 7.5 = 495 ✓). Aucun `below_min_order` (7.5 ≥ 5 au défaut 0.5). Warmup : 1 d 251/200, 1 w 51/50, `sufficient`
sur les deux. Aucun langage de validation : ces chiffres décrivent ce que le replay simule désormais.

### 3.3 Grid quick BTC 2025-03-01 → 03-15 (binance + bybit) et grid A BTC 2023-04-01 → 2026-04-01 (bybit)

Captures « après » sur la branche (commit `16078d1`, moteur = `508adae`) ; sha256 16 : `grid_quick_binance_c2.json`
`ab156d03402b2ab8`, `grid_quick_bybit_c2.json` `8b69fb00c497ada3`, `grid_A_bybit_c2.json.gz` (non versionné)
`c30fd6fbf094f2e2`. Tableaux complets : `results/c2_ab/compare_grid_quick_*.md`, `compare_grid_A_bybit.md` (le statut
« DIFFERENT (violation) » du comparateur C1 signifie ici « différent par conception »).

| Clé | quick binance avant → après | quick bybit avant → après | grid A bybit avant → après | Attribution |
|---|---|---|---|---|
| trades (fills) / paires maker / lots liquidés | 90 / 37 / 8 → 4 / 2 / 0 | 90 / 37 / 8 → 4 / 2 / 0 | 2 128 / 1 031 / 33 → 114 / 53 / 4 | **R1** : décisions sur les 85 clôtures 4 h de la fenêtre quick (4 033 ticks 5 m avant), `atr_4h` ≈ 2 194 (vrai 4 h) contre ≈ 279 (bougies 5 m) → espacement au plafond 5 % au lieu du plancher 1,5 %, recalc effectif 8 h ; bien moins de niveaux touchés |
| `net_pnl` | 1.520 → 2.421 | 0.655 → 2.395 | 114.21 → 45.72 | R1 |
| `total_fees` | 1.689 → 0.077 | 2.535 → 0.102 | 54.24 → 3.02 | R1 (volume de fills) |
| `unrealized_pnl` (liquidation terminale) | −11.12 → 0 | −11.47 → 0 | −228.12 → −15.31 | R1 (inventaire terminal 8 → 0 lots ; 33 → 4) |
| `average_holding_time_minutes` | 324 → 1 418 | 324 → 1 418 | 1 435 → 5 777 | R1 (espacement) |
| `sharpe_ratio` / `max_drawdown_pct_daily` / `profit_factor` / `calmar_ratio` | 0.352 / 2.18 / 1.135 / 1.85 → 9.17 / 0.00 / n/a (0 perte) / n/a | 0.188 / 2.20 / 1.056 / 0.78 → 9.16 / 0.00 / n/a / n/a | 0.367 / 17.97 / 1.499 / 0.204 → 0.931 / 2.04 / 3.967 / 0.734 | conséquences des lignes précédentes (2 gains sans perte sur 14 jours : Sharpe non significatif, `n_daily_returns` 14) |
| `liquidation.inventory_divergence_btc` / `residual_net_proceeds` | 0 / 0 → 0 / 0 | −1e-30 / 0 → 0 / 0 | −4e-30 / 0 → 0 / 0 | **R4** : aucun double pop sur BTC avant comme après (les cibles à 0.1 USD ne se chevauchent pas à ~90 000 USD) |
| `rejections` (C2) | — → aucun | — → aucun | — → aucun | R3 : aucun rejet sur ces runs BTC |
| `warmup` (C2, par TF : chargé/requis, staleness, plus grand trou, suffisant) | 4 h 91/14 0 0 ✓ · 1 d 251/50 0 0 ✓ · 1 w 56/50 0 1 ✓ | idem | 4 h 91/14 0 0 ✓ · **1 d 88/50 0 163 ✗** · **1 w 50/50 0 23 ✗** | R2 : sur grid A le trou BTC 2022-09-29 → 2023-03-12 tombe dans les fenêtres de 250 / 400 j : comptage atteint, aucune extension, `sufficient=False` **signalé** (les EMA 20/50 des régimes 1 d / 1 w sont amorcées en partie sur des bougies d'avant le trou) — observation, pas de correction |

Aucun verdict : ces chiffres décrivent la stratégie **spécifiée** (décisions aux clôtures 4 h, ATR 4 h réel) telle que le
replay la simule désormais ; le verdict appartient au rejeu diagnostic grid (phase suivante, protocole C3).

### 3.4 Rejeu P6 des trois grids (BTC / ETH / SOL, train / test / all) — preuve 4 (réel)

`scripts/run_p6_backtests.py --fees bybit --pair-costs-file config/pair_costs_b4.json --min-order-usdc 5 --limit 3 --workers 3`
(recette B4 : les 3 premiers jobs sont les grids), défauts de classe (dette 13), 2023-04-01 → 2026-04-01, split
2025-05-07T04:48Z ; artefact `results/c2_replay/P6_grid_rerun.json` (sha256 16 `d306903bc6233952`, `replay_version` 2,
commit `508adae`). Preuve automatisée `tests/test_scripts/test_c2_grid_rerun_artifact.py` (5 tests verts) dans l'ordre imposé :
(1) présence / validité — entrée sans clé `error` (`collect_flags` saute les entrées en erreur), trois segments, champs
comptables, bloc `liquidation`, valeurs numériques ; (2) tolérances de la règle canonique `scripts/b4_flags.py` (divergence
≤ 1e-12 BTC, `net_pnl` vs lot-basis ≤ 1e-9) ; (3) compteurs `unmatched_sell_fills` / `unmatched_position_id` /
`ambiguous_sell_fill` = 0 ; (4) SOL : `warmup.sufficient=False` attendu par segment ; tests négatifs (bloc `liquidation`
supprimé, entrée en erreur) → la preuve échoue.

| Paire / segment | trades (W/L) | `net_pnl` = lot-basis | lots liquidés | `inventory_divergence_btc` | rejets | warmup observé (chargé/requis, staleness, plus grand trou) |
|---|---|---|---|---|---|---|
| **SOL** train | 127 (120/7) | 102.4491 = 102.4491 | 7 | 1.1e-27 (poussière) | aucun | 4 h **0/14** (fenêtre calendaire vide, extension bornée à 7 j n'atteint pas le bloc d'avant le trou de 455 j → ATR amorcé sur les seules bougies post-2023-12-28) ✗ · 1 d 68/50, staleness **182** ✗ · 1 w 50/50, staleness **24** ✗ |
| SOL test | 46 (35/11) | −68.9564 = −68.9564 | 11 | 0 | aucun | 4 h 90/14 ✓ · 1 d 250/50 ✓ · 1 w 55/50 (trou 1) ✓ |
| SOL all | 179 (167/12) | 72.5957 = 72.5957 | 12 | 0 | aucun | comme train (✗ ✗ ✗) |
| BTC train | 40 (40/0) | 46.7999 = 46.7999 | 0 | −1e-31 | aucun | 4 h 91/14 ✓ · 1 d 88/50, trou **163** ✗ · 1 w 50/50, trou **23** ✗ |
| BTC test | 15 (12/3) | −2.8373 = −2.8373 | 4 | −1e-30 | aucun | ✓ ✓ ✓ |
| BTC all | 57 (53/4) | 45.7224 = 45.7224 | 4 | 0 | aucun | comme train (✓ ✗ ✗) |
| ETH train | 88 (79/9) | 20.5188 = 20.5188 | 10 | 6e-29 | aucun | comme BTC train |
| ETH test | 49 (42/7) | 8.9144 = 8.9144 | 8 | 1e-29 | aucun | ✓ ✓ ✓ |
| ETH all | 145 (138/7) | 124.4440 = 124.4440 | 7 | 4e-29 | aucun | comme BTC train |

Lecture (descriptive) : en B4 les trois segments SOL étaient flaggés (divergence −0.0256 / −0.0058 / −0.0335 SOL, `net_pnl`
≠ lot-basis de −3.76 / −0.74 / −3.86 USDC : 40 lots vendus deux fois) ; post-C2 la divergence est de la poussière Decimal sur
les 9 segments, `net_pnl` = lot-basis partout, aucun rejet — y compris aucun `insufficient_inventory`, alors qu'un premier
rejeu (tué) avant le commit 9 avait bloqué 3 lots (positions 3, 12, 18) des milliers de fois sur la poussière. Les blocs
`warmup` consignent, sans interprétation, que les segments qui commencent au 2023-04-01 démarrent dans le trou SOL
(4 h vide, 1 d / 1 w périmés de 182 j / 24 semaines) et que BTC / ETH portent le trou de 164 j dans leurs fenêtres 1 d / 1 w.

## 4. Constat rétroactif (préenregistrement × grilles P7)

En B4, P7 balayait `st_atr_period` [7, 10, 14, 20] × `st_multiplier` [2.0 … 4.0] (20 combos) et `donchian_upper_period`
[10, 15, 20, 30] alors que le préenregistrement hardcodait SuperTrend (10, 3.0) et Donchian (20, 10) : **19/20 configs
SuperTrend et 3/4 périodes Donchian** ont créé leur indicateur à la première lecture après le warmup (clé lazy = paramètres
exacts) et sont restées muettes pendant `st_atr_period` (7-20 bougies 4 h ≈ 1-3 jours) ou `donchian_upper_period` (10-30
bougies) au début de **chaque** segment (train, test, all, chaque fenêtre walk-forward). L'EMA 200 1 d du DCA, jamais
préenregistrée, était muette 200 jours à partir du premier lundi ≥ `start` : sur des fenêtres trimestrielles, la branche
oversold était inatteignable par construction (48 configs × 8 fenêtres). `grok_ema_adx_atr` (hors P7) n'a jamais eu ses EMA
27/125 prêtes en 90 bougies de warmup. Vérifié par `test_p7_variants_created_their_indicators_lazily_before_c2`. Constat de
portée pour l'invalidation B4 ; aucune correction rétroactive.

## 5. Identifiants lots ↔ callback : non-correspondance documentée (hors périmètre → test dette 13 élargi)

La chaîne SELL est transparente pour `metadata` (risk manager pass-through, `OrderManager` copie, payload
`order_manager.py:796`, router `:650`), mais : (i) le compteur de lots de la stratégie repart à 1 à chaque démarrage, sans
réhydratation depuis `open_positions` ; (ii) les rows `OpenPosition` grid reçoivent un id de repli `max+1` sur toutes les rows
du bot (le router protégé saute `_assign_runtime_position_id`, l'engine protégé alloue) et **restent OPEN** (aucun closer par
id pour le grid) ; (iii) une émission naïve de `position_id` fermerait une row périmée après restart (mauvais `entry_price`,
P&L fabriqué) ou, hors router, produirait des rows OPEN dupliquées (`MultipleResultsFound` avalé) ; (iv)
`order_manager._position_profit_targets` est indexé par int sans `bot_id`. Décision (Bruno, revue du plan) : le SELL apparié
émet `amount_btc` seul, **pas** `position_id` ; le chemin sans id reste le chemin nominal en live (lot unique au prix exact,
sinon réconciliation signalée). Démonstration reportée au **test dette 13 élargi** (restart avec rows OPEN périmées,
réhydratation ou closer par id) ; **prérequis B5 : le grid est inéligible au paper tant que ce n'est pas démontré**.

## 6. Découvertes annexes (signalées, non traitées)

- Les 3 stratégies gemini nourrissent l'analyzer deux fois par bougie (moteur `backtest.py` + leur `on_ohlc`) : période
  effective des indicateurs ~divisée par deux. Dette avec **blocage explicite de P12** (réévaluation scalping / mean reversion
  invalide par construction tant que ce n'est pas corrigé).
- `--cross-validate` × grid : neutralisé (N1, `parser.error`), pas routé — il n'existe pas de mode cross-validate du grid.
- `interval_order` du moteur signal (clé dupliquée hors `--interval 5`), `MultiTimeframeAnalyzer.initialize` (charge les bougies
  les plus anciennes, live), `get_features_dict` crée des indicateurs malgré sa docstring READ-ONLY, ADX `warmup_periods` =
  2p+1 vs prêt à 2p ; SELL nus de `_build_grid` jamais remplis en replay (ordres sans inventaire en live).
- Rows `backtest_runs` (CLI `--save`, dashboard) sans `replay_version` : pré/post-C2 visuellement mélangeables, comme pré/post-C1.
- Tests de déterminisme P6 : blocage sur le tunnel SSH observé pendant le baseline (workers spawn à 0 % CPU) — à surveiller
  à la porte pré-merge.

## 7. Gold hashes (re-baseline soumis à review — gate 2)

Fenêtre `tests/test_strategies/test_grid_atr_v4_backward_compat.py` : `grok_grid_atr_adaptive_v4` BTC/USDC 2025-03-01 →
2025-03-15, runner P6 (split 70/30 à 2025-03-10T19:12Z, segments train / test / all, `--interval 5`, capital 1 000).
Protocole : (a) runner + moteur du **tag** `v2.9.0-c1-metrics` depuis le worktree (`PYTHONPATH` worktree, `.env` copié) →
hashes **`619cac94…` (binance) / `ca846347…` (bybit) = `EXPECTED_HASHES` en vigueur, baseline reproduite** ;
(b) runner + moteur de la branche (`508adae`) → nouveaux hashes ci-dessous (identiques avant et après le commit 9 : aucune
vente bloquée par la poussière sur cette fenêtre). Fichiers : `results/c2_replay/gold_window_{binance,bybit}_{ref,c2}.json`.
Cause attendue du mouvement : **la stratégie spécifiée est désormais simulée** (R1 : décisions aux clôtures 4 h, ATR 4 h
réel → espacement 5 %, recalc 8 h ; R2 : préenregistrement/warmup sans effet ici — ATR 14 fixe, régimes fixes ; R3 :
aucun rejet ; R4 : aucun double pop sur BTC). Aucune clé n'est recalée sans ce tableau ; `EXPECTED_HASHES` n'est modifié
qu'après GO.

| Modèle | Ancien (C1, en vigueur) | Nouveau (C2, proposé) |
|---|---|---|
| `binance` | `619cac94d128a877615a042a8f00e007048beee11d49aa0b04fda391d6a7f9f1` | `5fb528dfb4c22e6fb5b0dfc2d1b8f7a80a5bedbbb332e18d85dee4581084345a` |
| `bybit` | `ca846347817276ed3040fd341b5a2ee9e46c5aaa62b5efd7e8907c84ae8f13ec` | `e9f0d3508c353d30f42fbeee3910ee4be643caca61d6b73edbdae73e6530cc54` |


### 7.`--fees binance` — ancien (tag C1) `619cac94…` → nouveau (C2) `5fb528dfb4c22e6fb5b0dfc2d1b8f7a80a5bedbbb332e18d85dee4581084345a`

| Segment | Clé | Ancien | Nouveau | Statut |
|---|---|---|---|---|
| train | `average_holding_time_minutes` | 286.400000 | 1417.500000 | mouvement |
| train | `calmar_ratio` | -21.907711 | n/a | mouvement |
| train | `duration_days` | 9.800000 | 9.800000 | identique |
| train | `ending_balance` | 978.013855 | 1002.421275 | mouvement |
| train | `gross_loss_net` | 30.663028 | 0.000000 | mouvement |
| train | `gross_profit_net` | 8.676884 | 2.421275 | mouvement |
| train | `losing_trades` | 13 | 0 | mouvement |
| train | `max_drawdown_pct_daily` | 2.570242 | 0.000000 | mouvement |
| train | `max_drawdown_pct_engine` | 2.839125 | 0.147946 | mouvement |
| train | `n_daily_returns` | 10 | 10 | identique |
| train | `net_pnl` | -21.986145 | 2.421275 | mouvement |
| train | `pf_excluded_trades` | 0 | 0 | identique |
| train | `profit_factor` | 0.282975 | n/a | mouvement |
| train | `sharpe_ratio` | -7.110160 | 11.254837 | mouvement |
| train | `sortino_ratio` | -7.478601 | n/a | mouvement |
| train | `starting_balance` | 1000.000000 | 1000.000000 | identique |
| train | `total_fees` | 1.409033 | 0.076845 | mouvement |
| train | `total_pnl` | -21.273645 | 2.458775 | mouvement |
| train | `total_return_pct` | -2.198614 | 0.242128 | mouvement |
| train | `total_trades` | 38 | 2 | mouvement |
| train | `unrealized_pnl` | -30.419278 | 0.000000 | mouvement |
| train | `win_rate` | 0.657895 | 1.000000 | mouvement |
| train | `winning_trades` | 25 | 2 | mouvement |
| train | liquidation.`positions` | 13 | 0 | mouvement |
| train | liquidation.`inventory_divergence_btc` | 0E-30 | 0E-31 | mouvement |
| train | liquidation.`net_pnl_lot_basis` | -21.98614450096208764304625212 | 2.42127515708583446750017199 | mouvement |
| train | liquidation.`residual_net_proceeds` | 0 | 0 | identique |
| train | rejections (C2) | — | aucun | nouveau |
| train | warmup (C2) | — | 4h: 91/14, 1d: 251/50, 1w: 56/50 | nouveau |
| test | `average_holding_time_minutes` | 393.333333 | 0.000000 | mouvement |
| test | `calmar_ratio` | n/a | n/a | identique |
| test | `duration_days` | 4.200000 | 4.200000 | identique |
| test | `ending_balance` | 1002.021666 | 1000.000000 | mouvement |
| test | `gross_loss_net` | 0.000000 | 0.000000 | identique |
| test | `gross_profit_net` | 2.021666 | 0.000000 | mouvement |
| test | `losing_trades` | 0 | 0 | identique |
| test | `max_drawdown_pct_daily` | 0.000000 | 0.000000 | identique |
| test | `max_drawdown_pct_engine` | 0.070553 | 0.000000 | mouvement |
| test | `n_daily_returns` | 5 | 5 | identique |
| test | `net_pnl` | 2.021666 | 0.000000 | mouvement |
| test | `pf_excluded_trades` | 0 | 0 | identique |
| test | `profit_factor` | n/a | n/a | identique |
| test | `sharpe_ratio` | 20.596031 | n/a | mouvement |
| test | `sortino_ratio` | n/a | n/a | identique |
| test | `starting_balance` | 1000.000000 | 1000.000000 | identique |
| test | `total_fees` | 0.226602 | 0.000000 | mouvement |
| test | `total_pnl` | 2.134166 | 0.000000 | mouvement |
| test | `total_return_pct` | 0.202167 | 0.000000 | mouvement |
| test | `total_trades` | 6 | 0 | mouvement |
| test | `unrealized_pnl` | 0.000000 | 0.000000 | identique |
| test | `win_rate` | 1.000000 | 0.000000 | mouvement |
| test | `winning_trades` | 6 | 0 | mouvement |
| test | liquidation.`positions` | 0 | 0 | identique |
| test | liquidation.`inventory_divergence_btc` | 0E-31 | 0 | mouvement |
| test | liquidation.`net_pnl_lot_basis` | 2.02166574555675722038788410 | 0 | mouvement |
| test | liquidation.`residual_net_proceeds` | 0 | 0 | identique |
| test | rejections (C2) | — | aucun | nouveau |
| test | warmup (C2) | — | 4h: 90/14, 1d: 250/50, 1w: 56/50 | nouveau |
| all | `average_holding_time_minutes` | 323.783784 | 1417.500000 | mouvement |
| all | `calmar_ratio` | 1.851280 | n/a | mouvement |
| all | `duration_days` | 14.000000 | 14.000000 | identique |
| all | `ending_balance` | 1001.520224 | 1002.421275 | mouvement |
| all | `gross_loss_net` | 11.272098 | 0.000000 | mouvement |
| all | `gross_profit_net` | 12.792322 | 2.421275 | mouvement |
| all | `losing_trades` | 8 | 0 | mouvement |
| all | `max_drawdown_pct_daily` | 2.182222 | 0.000000 | mouvement |
| all | `max_drawdown_pct_engine` | 3.050866 | 0.147946 | mouvement |
| all | `n_daily_returns` | 14 | 14 | identique |
| all | `net_pnl` | 1.520224 | 2.421275 | mouvement |
| all | `pf_excluded_trades` | 0 | 0 | identique |
| all | `profit_factor` | 1.134866 | n/a | mouvement |
| all | `sharpe_ratio` | 0.351973 | 9.169936 | mouvement |
| all | `sortino_ratio` | 0.544204 | n/a | mouvement |
| all | `starting_balance` | 1000.000000 | 1000.000000 | identique |
| all | `total_fees` | 1.689274 | 0.076845 | mouvement |
| all | `total_pnl` | 2.363974 | 2.458775 | mouvement |
| all | `total_return_pct` | 0.152022 | 0.242128 | mouvement |
| all | `total_trades` | 45 | 2 | mouvement |
| all | `unrealized_pnl` | -11.122098 | 0.000000 | mouvement |
| all | `win_rate` | 0.822222 | 1.000000 | mouvement |
| all | `winning_trades` | 37 | 2 | mouvement |
| all | liquidation.`positions` | 8 | 0 | mouvement |
| all | liquidation.`inventory_divergence_btc` | 0E-30 | 0E-31 | mouvement |
| all | liquidation.`net_pnl_lot_basis` | 1.52022429375764292696504000 | 2.42127515708583446750017199 | mouvement |
| all | liquidation.`residual_net_proceeds` | 0 | 0 | identique |
| all | rejections (C2) | — | aucun | nouveau |
| all | warmup (C2) | — | 4h: 91/14, 1d: 251/50, 1w: 56/50 | nouveau |

### 7.`--fees bybit` — ancien (tag C1) `ca846347…` → nouveau (C2) `e9f0d3508c353d30f42fbeee3910ee4be643caca61d6b73edbdae73e6530cc54`

| Segment | Clé | Ancien | Nouveau | Statut |
|---|---|---|---|---|
| train | `average_holding_time_minutes` | 286.400000 | 1417.500000 | mouvement |
| train | `calmar_ratio` | -21.896978 | n/a | mouvement |
| train | `duration_days` | 9.800000 | 9.800000 | identique |
| train | `ending_balance` | 977.078448 | 1002.395048 | mouvement |
| train | `gross_loss_net` | 31.281399 | 0.000000 | mouvement |
| train | `gross_profit_net` | 8.359847 | 2.395048 | mouvement |
| train | `losing_trades` | 13 | 0 | mouvement |
| train | `max_drawdown_pct_daily` | 2.641362 | 0.000000 | mouvement |
| train | `max_drawdown_pct_engine` | 2.868107 | 0.147910 | mouvement |
| train | `n_daily_returns` | 10 | 10 | identique |
| train | `net_pnl` | -22.921552 | 2.395048 | mouvement |
| train | `pf_excluded_trades` | 0 | 0 | identique |
| train | `profit_factor` | 0.267247 | n/a | mouvement |
| train | `sharpe_ratio` | -7.322200 | 11.247048 | mouvement |
| train | `sortino_ratio` | -7.638121 | n/a | mouvement |
| train | `starting_balance` | 1000.000000 | 1000.000000 | identique |
| train | `total_fees` | 2.320131 | 0.102447 | mouvement |
| train | `total_pnl` | -21.971552 | 2.445048 | mouvement |
| train | `total_return_pct` | -2.292155 | 0.239505 | mouvement |
| train | `total_trades` | 38 | 2 | mouvement |
| train | `unrealized_pnl` | -30.956399 | 0.000000 | mouvement |
| train | `win_rate` | 0.657895 | 1.000000 | mouvement |
| train | `winning_trades` | 25 | 2 | mouvement |
| train | liquidation.`positions` | 13 | 0 | mouvement |
| train | liquidation.`inventory_divergence_btc` | -2E-30 | 0E-31 | mouvement |
| train | liquidation.`net_pnl_lot_basis` | -22.92155151394069356038297058 | 2.39504812802428429718550022 | mouvement |
| train | liquidation.`residual_net_proceeds` | 0 | 0 | identique |
| train | rejections (C2) | — | aucun | nouveau |
| train | warmup (C2) | — | 4h: 91/14, 1d: 251/50, 1w: 56/50 | nouveau |
| test | `average_holding_time_minutes` | 393.333333 | 0.000000 | mouvement |
| test | `calmar_ratio` | n/a | n/a | identique |
| test | `duration_days` | 4.200000 | 4.200000 | identique |
| test | `ending_balance` | 1001.945607 | 1000.000000 | mouvement |
| test | `gross_loss_net` | 0.000000 | 0.000000 | identique |
| test | `gross_profit_net` | 1.945607 | 0.000000 | mouvement |
| test | `losing_trades` | 0 | 0 | identique |
| test | `max_drawdown_pct_daily` | 0.000000 | 0.000000 | identique |
| test | `max_drawdown_pct_engine` | 0.071163 | 0.000000 | mouvement |
| test | `n_daily_returns` | 5 | 5 | identique |
| test | `net_pnl` | 1.945607 | 0.000000 | mouvement |
| test | `pf_excluded_trades` | 0 | 0 | identique |
| test | `profit_factor` | n/a | n/a | identique |
| test | `sharpe_ratio` | 20.524195 | n/a | mouvement |
| test | `sortino_ratio` | n/a | n/a | identique |
| test | `starting_balance` | 1000.000000 | 1000.000000 | identique |
| test | `total_fees` | 0.302098 | 0.000000 | mouvement |
| test | `total_pnl` | 2.095607 | 0.000000 | mouvement |
| test | `total_return_pct` | 0.194561 | 0.000000 | mouvement |
| test | `total_trades` | 6 | 0 | mouvement |
| test | `unrealized_pnl` | 0.000000 | 0.000000 | identique |
| test | `win_rate` | 1.000000 | 0.000000 | mouvement |
| test | `winning_trades` | 6 | 0 | mouvement |
| test | liquidation.`positions` | 0 | 0 | identique |
| test | liquidation.`inventory_divergence_btc` | 0E-31 | 0 | mouvement |
| test | liquidation.`net_pnl_lot_basis` | 1.94560737739332947316624942 | 0 | mouvement |
| test | liquidation.`residual_net_proceeds` | 0 | 0 | identique |
| test | rejections (C2) | — | aucun | nouveau |
| test | warmup (C2) | — | 4h: 90/14, 1d: 250/50, 1w: 56/50 | nouveau |
| all | `average_holding_time_minutes` | 323.783784 | 1417.500000 | mouvement |
| all | `calmar_ratio` | 0.782173 | n/a | mouvement |
| all | `duration_days` | 14.000000 | 14.000000 | identique |
| all | `ending_balance` | 1000.654538 | 1002.395048 | mouvement |
| all | `gross_loss_net` | 11.668595 | 0.000000 | mouvement |
| all | `gross_profit_net` | 12.323133 | 2.395048 | mouvement |
| all | `losing_trades` | 8 | 0 | mouvement |
| all | `max_drawdown_pct_daily` | 2.199705 | 0.000000 | mouvement |
| all | `max_drawdown_pct_engine` | 3.064055 | 0.147910 | mouvement |
| all | `n_daily_returns` | 14 | 14 | identique |
| all | `net_pnl` | 0.654538 | 2.395048 | mouvement |
| all | `pf_excluded_trades` | 0 | 0 | identique |
| all | `profit_factor` | 1.056094 | n/a | mouvement |
| all | `sharpe_ratio` | 0.188154 | 9.164218 | mouvement |
| all | `sortino_ratio` | 0.288301 | n/a | mouvement |
| all | `starting_balance` | 1000.000000 | 1000.000000 | identique |
| all | `total_fees` | 2.535270 | 0.102447 | mouvement |
| all | `total_pnl` | 1.779538 | 2.445048 | mouvement |
| all | `total_return_pct` | 0.065454 | 0.239505 | mouvement |
| all | `total_trades` | 45 | 2 | mouvement |
| all | `unrealized_pnl` | -11.468595 | 0.000000 | mouvement |
| all | `win_rate` | 0.822222 | 1.000000 | mouvement |
| all | `winning_trades` | 37 | 2 | mouvement |
| all | liquidation.`positions` | 8 | 0 | mouvement |
| all | liquidation.`inventory_divergence_btc` | -1E-30 | 0E-31 | mouvement |
| all | liquidation.`net_pnl_lot_basis` | 0.65453780420668317747629007 | 2.39504812802428429718550022 | mouvement |
| all | liquidation.`residual_net_proceeds` | 0 | 0 | identique |
| all | rejections (C2) | — | aucun | nouveau |
| all | warmup (C2) | — | 4h: 91/14, 1d: 251/50, 1w: 56/50 | nouveau |

