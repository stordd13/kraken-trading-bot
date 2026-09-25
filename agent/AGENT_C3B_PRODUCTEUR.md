# C3b — Producteur conforme au protocole C3 v2.1

Nouvel agent. **Plan mode** : tu proposes un plan par lot, il est validé avant la première ligne de code
du lot. Cinq lots, **une session agent par lot**, chacun avec son critère de fin mécanique. Base en lecture
seule partout (aucune écriture, aucune migration). Aucune modification de `scripts/backtest.py` ni des
runners P6/P7 (§ L.3, C4 du 23/09) — voir « Liste close ».

Brief rédigé le 2026-09-25 au `dev = e9c8faf`. Pièce jointe : `agent/c3b_spec_F2_v2.1.md` (le § F.2 v2.1
recopié, sha256 du protocole `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129`). En cas
d'écart entre ce brief et `docs/protocole_c3.md`, **le protocole fait foi** (§ 0.7) : tu t'arrêtes et tu le
signales, tu n'arbitres pas.

## À lire d'abord

- `CLAUDE.md` (routeur), `PROJECT_CONTEXT.md` § 1 (état au 25/09), § 9 dettes 19, 21, 22, `ROADMAP.md`
  § « C3 — Validation chronologique » (les exigences C3b, lignes 137-175)
- `docs/protocole_c3.md` v2.1, dans cet ordre : § L.1 (les six entrées hors chaîne), § A.7 (liste blanche,
  artefact de couverture, clés `_base`), § A.8 (D1-D6, « liste dérivée, jamais déclarée »), § B.2 (preuve de
  départ à plat), § B.4 (appel unique), § B.5 (deux warmups), § C.3 (décider / exécuter, convention d'achat
  du benchmark), § C.4-C.5 (λ, comparabilité), § F.2 en entier (pièce jointe), § I.1 (table des codes),
  § I.2 (non assertable), § J (items 1, 10, 12), § L.3 (diff de contrôle)
- `results/sol_d2_1w_modes/report.md` § 3, § 4, § 8 (classes, oracle, dettes producteur) ;
  `scripts/audit/warmup_at.py` (`CLASSES`, `bias_split`, `bias_live`, `class_of`, `ReadOnlyDatabaseManager`,
  `git_provenance`) ; `tests/test_scripts/test_warmup_at.py` (la sonde comportementale, référence du lot 1)
- `skills/backtest.md` § « Validation C3 » et § « Replay », `skills/database.md` (`ohlc_derived`),
  `skills/deployment.md` (`~/runs/<chantier>/`, lanceur, archive)
- Le contrat que la chaîne lit — **c'est la spécification de forme de tes artefacts, il n'y en a pas
  d'autre** : `scripts/audit/c3_common.py` (`load_manifest`, `project_prefix`, `recompute_daily`,
  `coverage_recompute`, `replay_bootstrap`, `replay_environment`, `evaluation_admission`),
  `scripts/audit/c3_entry.py` (`_liquidation_form`, `_segment_form`, `a01_form` … `a08_d2`),
  `scripts/audit/c3_benchmark.py` (`load_candles`, `build_pair`, `blend_nav`), `scripts/audit/c3_continuity.py`
  (`comparator_block`, blocs lus), `scripts/audit/c3_verdict.py` (`_evaluation_contract`, `_read_replications`,
  `_read_series`, `_replay`) ; et les fixtures `tests/test_scripts/test_c3_common.py` (`evaluation`,
  `benchmark_eval`, `flat_start_proof`, `f2_procedure`, manifeste synthétique)
- `scripts/run_p7_grid_search.py:690-790` (`_run_segment` et le dict `result` : la couche d'export que tu
  reproduis, sans la modifier), `scripts/backtest.py` : `GridBacktester.__init__` (`:2200-2300`, état avant
  `run`), `run` (`:2865`), `liquidation_summary` (`:3269`), `equity_daily_dict` (`:708`),
  `_force_close_open_positions` (`:3149`) — **en lecture**
- `src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py` en entier (`__init__ :122-152`, `_get_directional_bias
  :224-249`, `_handle_ohlc :350-460`), `src/krakenbot/strategies/base.py`

## Contexte

Aucune campagne existante ne traverse la chaîne C3 : `c3_entry` refuse tout artefact réel (`D_WARMUP_PREFIX`,
clauses **non assertables** — `exec_interval`, couverture, `decision_timeframes`, `_base`, preuves § B). Le
protocole v2.1 fixe le contrat ; ce chantier livre le producteur qui le remplit. Le manifeste de la première
campagne, l'amendement v2.2 et la dette 21 sont **des conversations séparées** : ce brief ne les ouvre pas.

Deux faits mesurés le 25/09 entrent dans le contrat du producteur : `decision_timeframes` a **trois axes**
(`pause_1w` effectif, `bear_1d` effectif, `bias_live(grid_levels, bias_1d)` par l'oracle — six classes,
quatre ensembles) ; et une chaîne `"false"` dans `pause_1w_strong_bear` est **vraie** à `:384`.

## Décisions déjà tranchées (Bruno, 25/09) — ne pas rouvrir

1. **Grid seule.** `GrokGridATRAdaptiveV4` porte la classmethod ; `BaseStrategy.decision_timeframes` lève
   `NotImplementedError` ; le producteur **refuse** (code 2) toute stratégie qui ne l'implémente pas et tout
   engine autre que `GridBacktester`. Le moteur signal entre quand la dette 19 sera ouverte (C4), pas ici.
2. **`scripts/backtest.py` hors liste.** Preuve à plat et `first_fill_at` se dérivent **dans le producteur**
   depuis l'état du moteur avant `run` et depuis `metrics.trades`. Si en cours de lot tu conclus que c'est
   impossible sans toucher le moteur : **STOP**, tu écris pourquoi, tu ne contournes pas.
3. **Le producteur importe les primitives de la chaîne** (`c3_common`, `c3_benchmark`) : `recompute_daily`
   pour les rendements, `replay_bootstrap` pour le § F.2, `build_pair` / `blend_nav` pour le comparateur,
   `expected_units` / `coverage_unit` / `longest_missing_run` pour la couverture. « Une seule fonction, une
   seule convention » (§ F.2 c). Aucune réimplémentation, aucune copie.
4. **Dette 22 — site du fix.** `rejeu_common.write_json` **n'est pas touché** (diagnostic gelé du 20/09,
   artefacts d'histoire). `c3_common.write_json` cesse de le réexporter et devient strict, depuis
   `scripts/audit/_common.py`. Écart déclaré par rapport au libellé de la dette (`rejeu_common.py:344`) :
   à consigner dans `PROJECT_CONTEXT.md` dette 22 en la fermant.
5. **S-1 (`min_order_usdc`, `gross_usdc`) hors C3b** : `min_order_usdc` est dans la liste blanche § A.7,
   le renommer est un amendement. Candidat v2.2. **S-4 dans le lot 2.**
6. **Garde-fou de fenêtre — le plus important de ce brief.** Le producteur produit des **métriques de
   candidats**. Tant que le manifeste de la première campagne n'est pas gelé et inscrit au `RESEARCH_LOG`,
   **aucun run du producteur ne touche la fenêtre `2021-03-01 → 2026-06-29`**, sur aucune paire, avec aucun
   paramétrage. Les essais d'intégration sur base réelle se font sur une **fenêtre de conformité disjointe,
   entièrement antérieure au 2021-03-01** (proposition : `2020-01-06 → 2020-12-28`, BTC/USDT et ETH/USDT ;
   SOL y échoue D1 par construction — c'est un cas à exercer, pas à éviter). Un run sur la fenêtre de
   campagne avant le manifeste = shopping (§ 10.1, zéro retry-tuning) ; c'est un STOP, pas une nuance.

## Architecture cible

Le producteur est un **outillage hors chaîne** (§ L.1, ligne 0) : deux commandes, deux temps.

```
temps 1 — préfixe                     temps 2 — chaîne 1..4          temps 3 — évaluation          temps 4 — chaîne 5..6
c3b_prefix.py --manifest m.json  →   c3_anchor / c3_entry /     →   c3b_evaluate.py            →   c3_continuity / c3_verdict
  observations.json                    c3_benchmark / c3_select        --manifest --anchor            (chain)
  coverage.json                        (T, λ_dd, λ_σ, retenu)          --benchmark --select
  candles.json                                                         evaluation.json
  prefix_run.json (provenance)                                         benchmark_eval.json
                                                                       candles_eval.json
                                                                       evaluation_run.json (provenance)
```

L'évaluation **dépend** des sorties 1-4 (T recalculé par `c3_anchor`, `λ` du préfixe par `c3_benchmark`,
candidat retenu par `c3_select`) : elle ne peut pas être produite avant. Elle ne s'exécute que pour **le**
candidat retenu ; sélection vide ou abstention → code 2 « rien à évaluer », aucun fichier.

Fichiers :

| Fichier | Rôle |
|---|---|
| `scripts/audit/_common.py` | partagé par tous les scripts d'audit : `write_json_strict`, `read_json`, `git_provenance`, `ReadOnlyDatabaseManager`, `parse_now` — déplacés depuis `warmup_at.py` / `reconstruct_1w.py`, jamais dupliqués |
| `scripts/audit/c3b_common.py` | fabrique du moteur depuis le manifeste, couche d'export (`_base`, `decision_timeframes`, `exec_interval`, `period`), export de bougies, artefact de couverture, provenance |
| `scripts/audit/c3b_prefix.py` | temps 1 |
| `scripts/audit/c3b_evaluate.py` | temps 3 |
| `src/krakenbot/strategies/base.py`, `grok_grid_atr_adaptive_v4.py` | classmethod (lot 1) |

Conventions communes aux scripts : `--now` injectable ; codes de sortie **0 / 2 (refus d'entrée) / 3
(contrôle interne en échec)** comme `warmup_at` — jamais les codes de la table § I.1, qui appartiennent à la
chaîne ; toute sortie JSON par `write_json_strict` ; `Decimal` sérialisé en `str` **au site d'écriture** ;
`float` tel quel (le `json` de Python écrit le `repr` le plus court, § A.1 bis) ; jamais un type numpy dans
un payload. Refus sur arbre git non committé (`uncommitted_tree`, comme `warmup_at`). Provenance dans un
fichier **à part** (`*_run.json`), jamais dans les artefacts lus par la chaîne : leurs clés sont celles que
les accesseurs lisent, et rien d'autre.

## Liste close des fichiers (§ L.3)

**Modifiés** :

```
src/krakenbot/strategies/base.py
src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py
scripts/audit/c3_common.py                 (write_json : strict, depuis _common — rien d'autre)
scripts/audit/warmup_at.py                 (imports depuis _common — rien d'autre)
scripts/audit/reconstruct_1w.py            (imports depuis _common — rien d'autre)
.github/workflows/ci.yml                   (S-4)
```

**Nouveaux** :

```
scripts/audit/_common.py   scripts/audit/c3b_common.py   scripts/audit/c3b_prefix.py   scripts/audit/c3b_evaluate.py
tests/test_scripts/test_audit_common.py   tests/test_scripts/test_c3b_common.py
tests/test_scripts/test_c3b_prefix.py     tests/test_scripts/test_c3b_evaluate.py
tests/test_strategies/test_grid_v4_decision_timeframes.py
results/c3b_producteur/                    (rapport, preuves serveur, conformité)
```

**Documentation** : `ROADMAP.md` (C3b, paquet 1), `PROJECT_CONTEXT.md` (§ 1, dette 22 fermée, § 9),
`skills/backtest.md` (§ « Producteur C3b »), `docs/RESEARCH_LOG.md` (une ligne : essai d'instrument sur
fenêtre de conformité, aucune lecture économique), `results/INDEX.md`, `docs/CODE_MAP.md` (régénéré à la
clôture par Bruno, pas par toi).

**Diff de contrôle vide** sur tout le reste, et nommément sur : `scripts/backtest.py`,
`scripts/run_p6_backtests.py`, `scripts/run_p7_grid_search.py`, `scripts/p7_grids.py`,
`scripts/compute_benchmarks.py`, `scripts/audit/rejeu_*.py`, `scripts/audit/c3_{anchor,entry,benchmark,
select,continuity,verdict}.py`, `tests/test_scripts/test_c3_*.py`, `config/`, `alembic/`, `pyproject.toml`,
`poetry.lock`, `docs/protocole_c3.md`. Un besoin hors liste = STOP et note au plan, pas un ajout.

## Lot 1 — `decision_timeframes` (src)

**Livrable.** `GrokGridATRAdaptiveV4.decision_timeframes(params: Mapping[str, Any]) -> tuple[str, ...]`,
classmethod **pure** : aucune instance, aucun analyzer, aucun accès I/O. Sur `BaseStrategy`, la même
signature lève `NotImplementedError` avec le nom de la classe.

**Spécification.**

- Entrées lues, coercées **exactement comme `__init__` les lit** : `grid_levels` (`int(...)`, défaut 12),
  `bias_1d` (`Decimal(str(...))`, défaut 0.2), `pause_1w_strong_bear` (défaut `True`),
  `bear_protection_mode` (`None` / `"none"` / `"1w_only"` / `"1d_only"` ; autre valeur → la même
  `ValueError` que `__init__`). `bear_protection_1d_enabled` n'est lu d'aucun paramètre (`:132`) : il
  vaut `False` sauf par le setter.
- **Refus du non-booléen** : `pause_1w_strong_bear` qui n'est pas `bool` (au sens `type(x) is bool`) →
  `TypeError` nommant la clé et le type reçu. `"false"`, `0`, `1`, `"True"` sont tous refusés. La
  classmethod refuse ; `__init__` **n'est pas modifié** (compare-ab).
- Flags effectifs : le setter de `:137-152` rejoué sur les deux flags.
- `bias_live` **par l'oracle** : `cls._get_directional_bias` appelée non liée sur une sonde
  `(grid_levels, bias_1d)`, sur le domaine `{"strong_bull", "bull", "neutral", "bear", "strong_bear", None}`
  (vérifie le domaine réel de `get_regime` dans `multi_timeframe.py` et cite la ligne) ; décide si et
  seulement si l'ensemble des résultats a plus d'un élément. Jamais `bias_1d != 0`, jamais la forme fermée.
- Résultat : `("4h",)` toujours ; `+ "1w"` ssi `pause_1w` effectif ; `+ "1d"` ssi `bear_1d` effectif **ou**
  `bias_live`. Ordre de sortie **trié** (`sorted`), la chaîne compare en ensembles.
- Les étiquettes sont celles de `data.timeframes` du manifeste (`"4h"`, `"1d"`, `"1w"`) — pas des minutes.

**Tests rouges-avant** (`tests/test_strategies/test_grid_v4_decision_timeframes.py`) :

- les treize jeux de paramètres de `test_warmup_at.py` → `decision_timeframes(params)` égale, en ensemble,
  `warmup_at.class_of(instance).decision_tfs` ; l'instance construite par `warmup_at.default_strategy` +
  override — **la sonde comportementale reste la référence**, pas la table `CLASSES` recopiée ;
- balayage : `mode ∈ {None, none, 1w_only, 1d_only} × pause ∈ {True, False} × G ∈ 1..24 × b ∈ {0, 0.05,
  0.1, 0.16, 0.2, 0.5}` → égalité avec `class_of` sur chaque point ;
- `"false"`, `0`, `1`, `"True"`, `None` → `TypeError` ; mode invalide → `ValueError` ;
- pureté : deux appels identiques → même tuple ; aucun attribut de classe muté (comparer `vars(cls)`) ;
- `BaseStrategy.decision_timeframes` → `NotImplementedError` ; une stratégie gemini quelconque aussi ;
- mutants temporaires, tous rouges, fichier restauré : forme fermée `b != 0`, `"1d"` ssi `bear_1d` seul,
  `"1w"` inconditionnel, G non coercé, coercition `bool(...)` du flag.

**Critère de fin.** Tests ci-dessus verts ; **suite complète locale verte** ; gold hashes intacts ;
`compare-ab --strict` identique sur les trois runs de référence (`skills/backtest.md`) — `src/` est touché ;
`ruff` / `mypy src/` = baseline 65. Commit : `feat(strategies): decision_timeframes classmethod, refus du
non-booléen (C3b lot 1)`. **Gate humain avant le lot 2** (c'est `src/`).

## Lot 2 — `_common.py`, writer strict, S-4

**Livrable.** `scripts/audit/_common.py` ; `c3_common.write_json` strict ; `warmup_at` et `reconstruct_1w`
sans copie locale de `git_provenance` / `write_json_strict` / `ReadOnlyDatabaseManager` ; CI qui lint les
fichiers de la liste close.

**Spécification.**

- `write_json_strict(path, payload) -> str` : `json.dumps(sort_keys=True, indent=2, ensure_ascii=False,
  allow_nan=False, default=_refuse)` où `_refuse` lève `TypeError` avec **le chemin de clé** (`a.b[3].c`) et
  le type — ce qui impose un parcours préalable du payload pour connaître le chemin, ou une erreur enrichie
  au niveau du walker. `allow_nan=False` : un `NaN`/`inf` est une erreur d'écriture, pas un `NaN` en JSON.
  Retour : sha256 du texte écrit, `+ "\n"` final, comme aujourd'hui.
- `git_provenance(script_path)` paramétrée par le chemin haché (les deux copies divergeaient là).
- `c3_common.write_json = _common.write_json_strict` ; tout site C3 qui passait un `Decimal` / `datetime` /
  numpy passe désormais la conversion explicite. Les **932 tests C3 doivent rester verts sans modification
  des tests** ; s'il faut en modifier un, STOP et note : c'est qu'un artefact C3a écrivait une chaîne à la
  place d'un nombre, et il faut le dire.
- CI : `ruff check` et `ruff format --check` sur `scripts/audit/_common.py scripts/audit/c3*.py
  scripts/audit/warmup_at.py scripts/audit/reconstruct_1w.py` et `tests/test_scripts/test_c3*.py
  tests/test_scripts/test_warmup_at.py tests/test_scripts/test_reconstruct_1w.py tests/test_scripts/
  test_audit_common.py`. **Pas** `scripts/audit/` entier : les `rejeu_*.py` ne sont pas formatés et sont
  gelés ; les reformater est une décision séparée.

**Tests rouges-avant** (`test_audit_common.py`) : `numpy.float64` → `TypeError` nommant la clé ; `Decimal`
→ `TypeError` ; `datetime` → `TypeError` ; `NaN` → `ValueError` ; chemin de clé imbriqué exact dans le
message ; payload JSON pur → **sha identique** à `rejeu_common.write_json` sur le même payload (la
convention de forme ne change pas) ; `git_provenance` sur un arbre sale → `uncommitted_tree`.

**Critère de fin.** Suite locale verte ; CI verte sur la branche (le job ruff élargi passe) ; grep :
aucune définition de `git_provenance` / `write_json_strict` / `ReadOnlyDatabaseManager` hors `_common.py`.
Commits : `refactor(audit): _common.py partagé (git_provenance, ReadOnlyDatabaseManager)`,
`fix(audit): write_json strict — un type non JSON est une erreur nommée (dette 22)`, `ci: ruff sur les
scripts d'audit C3`.

## Lot 3 — producteur préfixe (`c3b_prefix.py`)

**Livrable.** `poetry run python scripts/audit/c3b_prefix.py --manifest m.json --output-dir DIR [--workers N]
[--now ISO]` → `observations.json`, `coverage.json`, `candles.json`, `prefix_run.json`.

**Spécification.**

- Le manifeste est **la seule entrée** : chargé par `cc.load_manifest` (strict, mêmes refus que la chaîne).
  Fenêtre, `T = manifest.anchor()` (recalculé, **jamais un paramètre**), `exchange`, `exec_interval`, fees,
  `pair_costs_file`, `min_order_usdc`, capital, candidats (`strategy`, `pair`, `params`). Un manifeste dont
  `window.start >= 2021-03-01` ou `window.end > 2021-03-01` est refusé (code 2) tant que le fichier
  `results/c3b_producteur/CAMPAIGN_UNLOCK` n'existe pas — c'est le garde-fou 6, mécanique. Ce fichier est
  créé par Bruno à la conversation manifeste, pas par toi.
- Avant tout run : `decision_timeframes(params)` sur chaque candidat — un `TypeError` (non-booléen) ou
  `NotImplementedError` → refus **global** code 2, aucun run, la clé fautive nommée. Un run partiel sur un
  univers mal formé n'existe pas.
- Par candidat : `GridBacktester(settings, db, fee_model=fees, strategy_name, candle_interval=exec_interval,
  exchange, starting_capital=C, strategy_params_override=params, pair_costs, min_order_usdc)` — **les mêmes
  arguments que `run_p7_grid_search._engine`**, cite la ligne — puis **un seul** `run(pair, window_start,
  T)`. Entrée d'observation = le dict `result` de `run_p7_grid_search:748-786` avec un seul segment nommé
  `manifest.prefix_segment`, sans `phase` / `window_idx`, plus :
  - `decision_timeframes` : la liste triée de la classmethod ;
  - `exec_interval` : `manifest.exec_interval` (c'est le `candle_interval` du moteur) ;
  - `liquidation[<préfixe>]` : `engine.liquidation_summary()` **renommé** dans la couche d'export —
    `residual_trade_btc → residual_trade_base`, `dust_written_off_btc → dust_written_off_base`,
    `inventory_divergence_btc → inventory_divergence_base`, et `amount_btc → amount_base` dans chaque lot ;
    aucune clé `_btc` ne survit (`cc.check_base_quantity_keys`). **`liquidation_summary` ne porte pas
    `lots`** (vérifié le 25/09 : la liste `lots` de `_force_close_open_positions:3185` est locale) : les
    lots se reconstruisent **dans le producteur** depuis `metrics.trades` tagués `forced_liquidation`
    (`:3125-3145`) — `amount_base = amount_crypto`, `gross_usdc = amount_usdc`, `fee`, `pnl` ;
    `entry_price = (gross − fee − pnl) / amount` puisque `pnl = net − amount × entry_price` (`:3107`),
    `null` avec `pnl` quand le coût est inconnu. Test de conformité : `cc.liquidation_identities(block, …)
    ["passed"]` vrai sur ta sortie (Σ fee, Σ gross, `trades − positions ∈ {0, 1}`, `gross_i == amount_i ×
    price`, `fee_i == gross_i × taker`) ;
  - `period` : `{<préfixe>_start, <préfixe>_end}` en ISO, `end == T` exactement ;
  - `params` = ceux du manifeste, `effective_params` = ceux du moteur.
  Clé d'entrée : `cc.candidate_identity(strategy, pair, params)`.
- `coverage.json` : `{window: {start, end: T}, pairs: {pair: {"5": …, "240": …, "1440": …, "10080": …}}}`,
  chaque série avec **exactement** les clés que `a07_coverage` lit (`observed`, `expected`, `covered_units`,
  `expected_units`, `unit`, `missing_stamps`, `longest_gap_days`, `first_day`, `last_day`). Estampilles lues
  en base sur `[start, T]`, `exchange` du manifeste ; les rows de `ohlc_derived` **comptent comme observées**
  (décision C3 du 23/09) et leurs estampilles sont recopiées dans `prefix_run.json` (pas dans `coverage.json`).
  `expected_units`, `unit`, `longest_gap_days` par **les fonctions de `c3_common`** : le test de conformité
  est `cc.coverage_recompute(series, …)["problems"] == []` sur ta propre sortie.
- `candles.json` : `{pairs: {pair: {exec_interval, exec: [{t, close}], daily: [{t, close}]}}}` sur
  `[start, T]`, `close` en `str` de `Decimal`, **aucune estampille `> T`** (la chaîne refuse), aucune en
  double, triées.
- Parallélisme : `--workers` par processus, un `DatabaseManager` par worker, résultats **par candidat**
  écrits atomiquement (`save_result_atomic`-like, réimplémenté dans `c3b_common`, pas importé du runner
  P6), reprise autorisée **seulement** si le sha256 du manifeste est identique à celui du fichier partiel.
  Tri des jobs par paire puis identité : l'ordre d'exécution ne change pas la sortie.
- Déterminisme : `observations.json` et `candles.json` **identiques au bit** entre deux exécutions (le
  `--now` n'y entre pas) ; `prefix_run.json` porte git, base (url masquée, `alembic current`), environnement
  (`cc.replay_environment()`), sha256 des trois autres fichiers, durée par candidat.

**Tests rouges-avant** (`test_c3b_common.py`, `test_c3b_prefix.py` — **aucun test base**, comme
`warmup_at`) :

- couche d'export : un `liquidation_summary` synthétique avec clés `_btc` et lots → sortie sans aucune
  clé `_btc`, `_liquidation_form` de `c3_entry` vert ; mutant « lot non renommé » rouge ;
- forme d'une entrée : sortie de l'export → `c3_entry.a01_form` sur un contexte synthétique = zéro problème
  (le test de conformité par construction) ; retirer `decision_timeframes` → problème nommé ;
- appel unique : moteur bouchon avec compteur → `run` appelé **une fois**, bornes `(start, T)` exactes ;
- `T` recalculé : deux manifestes de même fenêtre → même `T` ; `T` ≠ estampille de grille (04:48) ;
- refus : `pause_1w_strong_bear: "false"` dans un candidat → code 2 avant tout run, clé nommée ; stratégie
  non grid → code 2 ; fenêtre de campagne sans `CAMPAIGN_UNLOCK` → code 2 ;
- couverture : sur des listes d'estampilles synthétiques (trous, semaines manquantes, rows dérivées),
  `coverage_recompute` vert ; mutants « 1 w compté en jours », « dérivées non comptées », « trou de bord »
  rouges ;
- bougies : une estampille `> T` injectée → refus **du producteur** (pas seulement de la chaîne).

**Critère de fin (serveur, fenêtre de conformité, `~/runs/c3b_prefix/`, lanceur aux règles du 25/09).**
Manifeste de conformité : fenêtre `2020-01-06 → 2020-12-28`, BTC/USDT + ETH/USDT + SOL/USDT, quatre
candidats grid couvrant les classes C1, C2, C5, C6 (un par ensemble). Attendu **déclaré avant le run** :
SOL sort par D1 (portée paire) ; BTC/ETH passent I-A **sans clause non assertable** ; `c3_entry` code 0 ;
`c3_benchmark` et `c3_select` s'exécutent (leur issue n'a **aucune lecture économique** — c'est une fenêtre
d'instrument, et le rapport le dit en première ligne). Deux runs → mêmes sha256. Ligne au `RESEARCH_LOG`
**avant** le lancement. Preuves sous `results/c3b_producteur/prefix_conformite/` (status.txt, logs, sha,
sorties de la chaîne). Commit : `feat(audit): c3b_prefix — observations, couverture, bougies (C3b lot 3)`.

## Lot 4a — run d'évaluation et preuves § B (`c3b_evaluate.py`, partie 1)

**Livrable.** `c3b_evaluate.py --manifest --anchor anchor.json --select select.json --output-dir DIR` →
`evaluation_run.json` (intermédiaire, **pas encore l'artefact lu par la chaîne**) et provenance.

**Spécification.**

- Entrées : `T` et `pairs` triées depuis `anchor.json` (recoupés avec `manifest.anchor()` — écart = code 3) ;
  identité retenue depuis `select.json` ; absence de retenu → code 2 « rien à évaluer ».
- **Preuve de départ à plat, capturée avant la première bougie** (§ B.2, § J item 10) : après construction du
  moteur et **avant** `run`, lire `engine.usdc_balance`, `engine.btc_held`, `len(engine.active_buy_orders) +
  len(engine.active_sell_orders)` ; exiger `usdc_balance == C` du manifeste, `btc_held == 0`, `pending == 0`,
  sinon code 3. Exporter `flat_start_proof = {"at": T.isoformat(), "cash": str(C), "qty": "0", "pending": 0}`
  — la forme exacte de la fixture `flat_start_proof`. Cette preuve vaut `DÉCLARÉ`, jamais plus : le rapport
  le dit avec ce mot.
- **Un seul appel** `run(pair, T, fin)` ; `invocation = {"single_call": true}` n'est écrit que par le chemin
  de code qui appelle `run` une fois — un test l'épingle par compteur.
- `first_fill_at` = plus petite estampille de `metrics.trades` ; **strictement `> T`** exigé (code 3
  sinon) ; `null` si aucun trade (la chaîne le traite).
- `equity_daily = engine.metrics.equity_daily_dict()` (`start == T`, `end == fin`) ; `liquidation` renommé
  `_base` (même couche que le lot 3) ; `warmup = engine.warmup_summary()` (W-ancrage, § B.5) ; `period`
  `{start: T, end: fin}` ; `strategy`, `pair`, `params` ; `synthetic: false` ; `metrics.net_pnl` depuis
  `metrics.to_dict()["net_pnl"]`.
- Contrôle interne : `|net_pnl − (ending − starting)| ≤ 1e-6` (nécessaire, pas suffisant — § B.2) → code 3
  s'il échoue ; et `liquidation.timestamp` dans la même cellule quotidienne que `fin` ou `trades == 0`
  (§ B.4, `stamp_cell`).

**Tests rouges-avant** (`test_c3b_evaluate.py`, moteur bouchon) : preuve lue **avant** `run` (le bouchon
mute `usdc_balance` dans `run` — un mutant qui lit après est rouge) ; `single_call` faux si le compteur ≠ 1 ;
`first_fill_at ≤ T` → code 3 ; `cash != C` → code 3 ; forme de `flat_start_proof` égale à la fixture ;
sélection vide → code 2.

**Critère de fin.** Tests verts ; `cc.evaluation_admission(evaluation_run)` vrai sur un artefact produit
(les trois porteurs présents) ; `c3_continuity` **sur un `benchmark_eval` synthétique** rend `c1 = DÉCLARÉ`,
`c2 = DÉCLARÉ`, `c5 = DÉCLARÉ` sur le run de conformité. Commit : `feat(audit): c3b_evaluate — run unique,
flat_start_proof, first_fill_at (C3b lot 4a)`.

## Lot 4b — comparateur d'évaluation et § F.2 (`c3b_evaluate.py`, partie 2)

**Livrable.** `evaluation.json` complet, `benchmark_eval.json`, `candles_eval.json`,
`evaluation_sensitivity.json` (hors chaîne).

**Spécification.**

- `candles_eval.json` : même forme que `candles.json`, sur `[T, fin]`, aucune estampille `> fin`.
- Comparateur (§ C.3-C.5) : `c3_benchmark.build_pair(pair, candles, start=T, end=fin, exec_interval, spread,
  slippage, taker, capital)` — entrée à la **clôture de la première bougie d'exécution strictement après
  `T`**, sortie à la dernière `≤ fin`, taker + spread + slippage sur les deux jambes ; c'est déjà la
  convention de la fonction, tu la cites, tu ne la réécris pas. `λ_dd`, `λ_σ` **lus dans `benchmark.json`**
  (étape 3) pour l'identité retenue, **tenus fixes** (§ F.2 f) ; `NOT_ESTIMABLE` au préfixe → code 2.
  `nav_bench[m] = blend_nav(nav_bh, λ_m, C)` ; `returns_bench[m] = cc.recompute_daily(nav_bench[m],
  days=n_jours).returns`.
- `returns_config = cc.recompute_daily(equity_daily.values, days=n_jours).returns` — **dérivée de la série
  exportée par la même fonction que la chaîne** (ex-S-3 : le recoupement côté chaîne attend l'amendement
  v2.2 ; côté producteur, l'égalité au bit est garantie par construction et testée). `n_jours = (fin − T)`
  en secondes / 86 400, double précision, jamais `duration_days` du moteur.
- Longueurs : les trois séries de même `n`, sinon code 3 avant tout tirage.
- § F.2 : `replay = cc.replay_bootstrap(returns_config, {"dd": …, "sigma": …}, seed=anchor.uncertainty.seed,
  pair_index=sorted(anchor.pairs).index(pair), days=n_jours)` ; export
  `replications[f"{L}:{m}"] = {"delta_stars": [...], "discarded": k, "bound": b|null}` pour les six
  combinaisons, `B = cc.BOOTSTRAP_B`, `environment = cc.replay_environment()`, `metrics = {net_pnl,
  cagr_pct: replay.cagr_config, delta_dd: replay.delta_hat["dd"]}`. Une entrée invalide (§ F.2 e, CAGR
  observé non fini) → code 3, aucun artefact.
- `benchmark_eval.json` : `{pair, window: {start: T, end: fin}, comparable, comparability: {les cinq tests}}`
  — les clés que `comparator_block` lit ; `comparable` = conjonction, recalculée, jamais posée à la main.
- `evaluation_sensitivity.json` : λ ré-estimés **sur la fenêtre d'évaluation** (§ F.2 f, « sensibilité
  descriptive ») — hors chaîne, jamais dans `evaluation.json`.
- `evaluation.json` porte **exactement** les clés de la fixture `evaluation` de `test_c3_common.py`, et
  aucune autre.

**Tests rouges-avant** : sur les séries témoin des fixtures (`witness_returns`, cash), la sortie du
producteur est **égale au bit** à `f2_procedure(...)` — suites, écartées, bornes, `cagr_pct`, `delta_dd` ;
`returns_config` égale au bit à `recompute_daily(equity_daily).returns` (mutant « rendements depuis
`equity_curve` du moteur » rouge) ; `n_jours` depuis les bornes (mutant `duration_days` rouge) ;
`pair_index` depuis les paires triées de l'ancrage (mutant « index du manifeste » rouge) ; `λ` du préfixe
(mutant « λ ré-estimé » rouge) ; longueurs différentes → code 3 ; clé en trop dans `evaluation.json` →
test de forme rouge ; `_evaluation_contract` de `c3_verdict` vert sur un artefact produit dans le même
environnement.

**Critère de fin (serveur, `~/runs/c3b_eval/`).** Sur la campagne de conformité du lot 3 : `c3_verdict.py
chain` **complète, six étapes**, `chain.verified: true`, **zéro violation au rejeu** (égalité au bit sur les
six suites, `Δ̂`, CAGR, six bornes) ; deux exécutions du producteur → `evaluation.json` identiques au bit ;
l'issue publiée est citée dans le rapport avec, en première ligne, « fenêtre d'instrument, aucune portée
économique ». Preuves sous `results/c3b_producteur/eval_conformite/`. Commit : `feat(audit): c3b_evaluate —
comparateur § C.5, procédure § F.2 rejouable (C3b lot 4b)`.

## Preuves serveur et porte pré-merge

- Tout run serveur : `~/runs/<chantier>/`, lanceur avec `set -o pipefail` / `${PIPESTATUS[0]}`, pas de
  `set -e`, `status.txt` clé=code par étape, second `alembic current` inconditionnel, `bash -lc` sous tmux,
  archive vérifiée (`tar -tzf` + sha) avant tout `rm -rf`. Extrait dans le dépôt, brut sous
  `~/archive/c3b_<lot>_<date>/`.
- Producteur **et** chaîne tournent sur le serveur (§ J item 12) : l'environnement déclaré est celui du
  serveur, et la conformité ne se prouve pas en local.
- Porte § L.5 **option 1** obligatoire au SHA livré (les 24 `_full` sur le serveur) : `src/` est touché par
  le lot 1. L'option 2 est indisponible par construction.
- Suite complète locale verte à chaque lot ; `mypy src/` = baseline ; `MYPYPATH=src:scripts:scripts/audit
  mypy --follow-imports=silent scripts/audit/c3b_*.py scripts/audit/_common.py` strict vert.

## Gates

| Quand | Quoi |
|---|---|
| Début de chaque lot | plan écrit (fichiers touchés dans la liste close, tests nommés, mutants prévus) → GO Bruno |
| Fin du lot 1 | gate humain : diff `src/` relu, compare-ab, gold hashes, suite |
| Fin du lot 3 | attendu de conformité écrit **avant** le run serveur, relu ; puis preuves |
| Fin du lot 4b | STOP avant merge : rapport `results/c3b_producteur/report.md`, porte § L.5, docs |
| Tout besoin hors liste, tout doute sur le texte gelé, tout besoin de toucher le moteur | STOP |

Rapport final (`results/c3b_producteur/report.md`) : par lot, ce qui est livré, les tests, les mutants, les
preuves serveur, les écarts constatés avec le protocole (candidats v2.2 — à lister, jamais à implémenter), la
dette 22 fermée avec son écart de site, et **la phrase** : aucune donnée de la fenêtre de campagne n'a été
lue par le producteur.

## Ce que ce chantier ne fait pas

- Le manifeste de la première campagne, l'univers, les 8 estampilles dérivées à déclarer, la dette 21
  (`--campaign`), la dette 24 (spread/slippage Bybit) : conversation manifeste.
- L'amendement v2.2 (§ A.8 l.515 `grid_levels`, l.605-606 « alimente une porte », recoupement
  `returns_config ← equity_daily` côté chaîne, S-1, enforcement mécanique du § 10.1 au registre de variantes —
  ce dernier est une règle normative sans texte au protocole, donc amendement d'abord, outillage ensuite).
- Le moteur signal, la dette 19, `scripts/backtest.py`.
- Toute lecture économique d'un run de conformité.
- La factorisation au-delà de `_common.py` (pas de refonte de `rejeu_common`).
