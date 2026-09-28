# C3b lot 1 — `decision_timeframes` : preuves (compare-ab, mutants, suite)

Brief : `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 1 ». Branche `feat/c3b-producteur`, base `dev = ec7ffb8`. Exécuté le
2026-09-25, en local (tunnel 5433, `.env`). Aucune lecture économique : ces runs sont des **invariants de
confinement** (`compare-ab --strict`, `skills/backtest.md` § « Invariant de tout chantier moteur »).

## Changement vérifié

- `BaseStrategy.decision_timeframes(params)` : une classmethod qui lève `NotImplementedError` en nommant la classe.
- `GrokGridATRAdaptiveV4.decision_timeframes(params)` : une classmethod pure. Elle lit les paramètres comme `__init__`,
  rejoue le setter des flags et décide `bias_live` en exécutant l'oracle `_get_directional_bias` sur `_REGIME_DOMAIN`
  (`MarketRegime ∪ {None}`, `multi_timeframe.py:750-777`). Elle refuse un `pause_1w_strong_bear` non booléen
  (`TypeError`), même quand `bear_protection_mode` est posé.
- `__init__` et `_handle_ohlc` sont inchangés.
- Diff `src/` : `base.py` +14 lignes, `grok_grid_atr_adaptive_v4.py` +77 lignes, 2 lignes d'import remplacées.

## Invariant `compare-ab --strict` (trois runs de référence)

Les captures « ref » ont été prises **avant toute modification de `src/`** (`src-dirty-lines 0`). Les captures « c3b »
ont été prises avec la classmethod dans l'arbre de travail, avant le commit ; `git_head` vaut donc `ec7ffb8` des deux
côtés. Le fichier grid capturé (`sha256 60e7c3c5…`, relevé dans `source_fingerprints`) est celui du commit `feat` du
lot. La commande est dans `capture.sh` : `c1_equity_probe.py capture --pair BTC/USDC --exchange binance --interval 5
--capital 1000 --fees bybit`.

| Run | Fenêtre | Trades / points / `net_pnl` | sha256 fichier ref → c3b | Verdict | Clés top-level différentes |
|---|---|---|---|---|---|
| signal A `grok_supertrend_4h` | 2023-04-01 → 2026-04-01 | 92 / 6 577 / 19.314423 | `44ad8fb8…` → `44ad8fb8…` (identiques) | `STRICT IDENTITY OK` | aucune |
| grid quick `grok_grid_atr_adaptive_v4` | 2025-03-01 → 2025-03-15 | 4 / 4 033 / 2.395048 | `663659fe…` → `a4e32c67…` | `STRICT IDENTITY OK` | `source_fingerprints` |
| grid A `grok_grid_atr_adaptive_v4` | 2023-04-01 → 2026-04-01 | 114 / 315 650 / 45.722405 | texte canonique `45961a2b…` → `5b5402c8…` | `STRICT IDENTITY OK` | `source_fingerprints` |

- **`source_fingerprints`** ne hache que `scripts/backtest.py` et le module de la stratégie chargée
  (`c1_equity_probe.py:186-202`). `base.py` n'y figure pas. Signal A (stratégie supertrend, inchangée) est donc
  identique **à l'octet près**. Pour grid, seule l'empreinte `strategy` change : `8a3f06ae…` → `60e7c3c5…`.
  `backtest` vaut `7dba443d…` des deux côtés.
- Les 7 lignes « removed » des tableaux `compare_*_strict.md` sont un artefact de rendu de `metrics_table` : les clés
  du contrat C1 absentes des listes `IDENTICAL_KEYS` / `MOVING_KEYS` s'y affichent « removed » avec la valeur « - »,
  qu'elles soient présentes ou non. Le même tableau C2 en montre 7 aussi
  (`results/c2_ab/compare_signal_A_bybit_strict.md`). Vérifié à part : `metrics` est égal entre ref et c3b sur les
  trois runs.
- Les valeurs reproduisent celles publiées en C2 (`results/C2_replay_report.md` § 3.3 : quick bybit 2.395, grid A
  45.72 ; signal A 19.314423).
- Fichiers : `*_ref.json` / `*_c3b.json` (signal A, grid quick), `compare_*_strict.md` (tableau) et
  `compare_*_strict.out` (sortie complète, verdict inclus). Grid A (gz d'environ 5 Mo) est gardé **hors dépôt**,
  dans `~/archive/c3b_lot1_20260925/` : fichiers gz ref `ac2e85e8…` et c3b `12507a47…`. Ignorer ce gz dans le dépôt
  demanderait de modifier `.gitignore`, hors liste close.

## Tests : rouge-avant et mutants

Tests : `tests/test_strategies/test_grid_v4_decision_timeframes.py` (60).

- **Rouge-avant**, sur `src/` à `ec7ffb8` : **58 échecs, 2 passés**. Les deux passés n'appellent pas la classmethod.
  Ils épinglent les entrées : le compte 13 = 12 + 1 de `PROBE_CASES`, et l'inventaire des stratégies du paquet.
- **Mutants** : chacun est appliqué au fichier `src`, testé, puis le fichier est restauré. `mutants.py` et
  `mutants.log` sont versionnés ; `mutants.py` a été formaté par ruff après le run, avec les mêmes chaînes. Le sha du
  fichier restauré est `60e7c3c5…`, identique à l'original.

| Mutant | Résultat | Tué par |
|---|---|---|
| M1 forme fermée `bias_1d != 0` | 13 échecs | probe cases, balayage, coercition |
| M2 `"1d"` ssi `bear_1d` seul | 14 échecs | probe cases, balayage, coercition |
| M3 `"1w"` inconditionnel | 14 échecs | probe cases, balayage, coercition |
| M4 `grid_levels` non coercé | 4 échecs | coercition (`"13"`, `"12"`) |
| M5 `bool(...)` au lieu du refus | 21 échecs | refus du non-booléen (20), cas `"false"` (1) |
| M6 sortie non triée | 8 échecs | balayage (ordre) |
| M7 mode invalide non refusé | 1 échec | `ValueError` identique à celle de `__init__` |

## Suite, gold hashes, typage

- Suite complète locale, lancée avec `-k "not test_determinism_parallel_vs_serial_full"` (condition 2 du GO, les 24
  `_full` sont exclus) :
  - base `ec7ffb8` : **2 938 passés**, 6 ignorés, 24 désélectionnés ;
  - après : **2 998 passés** (= 2 938 + 60), 6 ignorés, 24 désélectionnés.
  - Les 24 `_full` passent sur le serveur au SHA livré, à la porte § L.5 de fin de chantier (option 1, `src/` touché).
- Gold hashes (`tests/test_strategies/test_grid_atr_v4_backward_compat.py`) : 2 passés (binance, bybit), fichier
  inchangé.
- `mypy src/` : 65 erreurs, **liste identique** à la base. `ruff check` et `ruff format --check` sont verts sur `src/`
  et le nouveau test.

## Observation reportée au lot 3 (non traitée ici)

Un `bias_1d` non fini (`"NaN"`) fait lever l'oracle (`int(nan)` dans `_get_directional_bias`), et la classmethod
propage l'erreur. Exigence du lot 3 (GO de Bruno, 25/09) : avant d'appeler la classmethod, le producteur valide que
`grid_levels` est entier et `bias_1d` fini, et refuse nommément (code 2).
