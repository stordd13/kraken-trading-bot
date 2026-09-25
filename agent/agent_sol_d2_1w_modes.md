# Mesure SOL/D2 — timeframes de décision de grok_grid_atr_adaptive_v4 et amorçage au 2021-03-01

Nouvel agent. Mode review : tu proposes chaque fichier, il est relu avant écriture. Lecture seule sur la
base. Aucune modification du moteur, des stratégies, des modèles, des migrations.

## À lire d'abord

- `CLAUDE.md` (routeur), `PROJECT_CONTEXT.md` § 1 et § 6, `ROADMAP.md` (exigences producteur C3b)
- `docs/protocole_c3.md` : § A.8 (D1, D2, « liste dérivée, jamais déclarée »), § I.1 lignes 4-5 et 15
  (clause de promotion, désaccord `decision_timeframes`), § 10.1
- `skills/backtest.md` § « Validation C3 », `skills/database.md` (table `ohlc_derived`),
  `skills/deployment.md` (convention `~/runs/<chantier>/`)
- `results/reconstruction_1w_2022_2025/report.md` (les 8 estampilles 1 w reconstruites)
- `src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py` en entier
- `scripts/backtest.py:295-530` (C2 R2 : `IndicatorRequirement`, `_indicator_requirements`,
  `warmup_needs`, `load_context_series`) et les deux sites d'appel (`:1015`, `:3073`) pour retrouver les
  `load_window` / `load_before` réels et la valeur de `window_start` passée
- `src/krakenbot/indicators/multi_timeframe.py:750-780` (`get_regime`, retour `None`)

## Contexte

Dernier prérequis avant le manifeste de la première campagne C3. Le § A.8 D2 retire un candidat si un
timeframe qui **alimente une porte de décision** n'est pas `sufficient` au début du préfixe (2021-03-01).
Fait connu, non mesuré sur le code : le régime 1 w exige 50 bougies (`_ANALYZER_REGIME_EMA_SLOW`,
`backtest.py:305`) ; SOL n'en porte que 29 au 2021-03-01. L'univers de candidats n'est pas fixé et ne
l'est pas ici (décision de manifeste, § A.5 / § A.6). La mesure se fait donc **par classes
d'équivalence de `decision_timeframes`**, pas par candidats : quand l'univers sera fixé, chaque candidat
tombera dans une classe et la table se lira sans se rejouer.

Lecture préalable (à vérifier, pas à recopier) :

- `:383` lit `get_regime("1w")` inconditionnellement ; la porte ne vit que si `pause_1w_strong_bear`
  (`:384`). En `none` / `1d_only` la valeur ne sert qu'aux logs (`:397`, `:425`, `:462`).
- `bear_protection_mode` (`:137-152`) est un setter sur deux flags. `None` → flags YAML
  (`pause_1w_strong_bear` défaut `True` `:131`, `bear_protection_1d_enabled` `False` `:132`).
  `(pause_1w=True, bear_1d=True)` n'est pas atteignable par le setter.
- `bias_1d = 0` : `_get_directional_bias` (`:224-249`) rend `half/half` quel que soit le régime ;
  `regime_1d` est lu (`:443`) mais ne décide rien.
- `_indicator_requirements` (`backtest.py:420-425`) déclare toujours `regime 1w` pour la stratégie,
  quel que soit le mode. **Liste statique par stratégie ≠ liste de décision par candidat.**

## Objectif

Un rapport chiffré `results/sol_d2_1w_modes/report.md` qui répond, lignes de code citées :

1. Quels timeframes la stratégie **lit** et lesquels **décident**, par classe d'équivalence.
2. Quels axes de paramètres changent cette liste (attendu : seulement `pause_1w_strong_bear`,
   `bear_protection_1d_enabled`, `bias_1d ≠ 0` — à confirmer en lisant tout le fichier, y compris
   `_calculate_spacing`, `_build_grid`, `_recalculate_grid`, les sorties, le sizing).
3. Pour chaque classe × paire (BTC, ETH, SOL USDT binance), D2 au 2021-03-01 : `loaded`, `required`,
   `stale_by_candles`, `largest_gap_candles`, `sufficient`, **calculés par la règle C2 réelle**
   (`load_context_series`), pas lus dans l'inventaire du 23/09.
4. Si SOL est partiel : ce que disent § I.1 lignes 4-5 (promotion) et ce que le manifeste devra
   déclarer. Cité, pas décidé.

## Spec

### Étape 1 — inventaire statique (pas de base)

Table A, une ligne par appel `self.analyzer.get_*` de la stratégie : ligne, méthode, timeframe,
condition d'exécution, ce que la valeur alimente (porte de pause / biais / espacement / log seulement).

Table B, classes d'équivalence. Axes = flags effectifs, pas le mode :

| classe | pause_1w | bear_1d | bias_1d ≠ 0 | modes qui y mènent | TF lus | TF de décision |
|---|---|---|---|---|---|---|

Six classes attendues. Si un autre paramètre entre en jeu à l'étape 2, il devient un axe et la table
s'élargit. Le 4 h ATR (`:429`) est attendu dans toutes les classes.

Noter séparément : ce que `_indicator_requirements` déclare (`:420-425`) et l'écart avec la colonne
« TF de décision » — c'est le fait que C3b doit absorber (classmethod par candidat, ROADMAP).

Noter aussi : ce que le moteur fait quand `sufficient == False` — refus de run ou rapport
(`:3699` suggère un simple drapeau `INSUFFICIENT`). Citer la ligne. Si c'est un rapport, écrire que
D2 est bien la seule barrière et que le moteur ne refuse rien de lui-même.

### Étape 2 — bornes de forme sur `decision_timeframes`

Pour chaque classe, la liste que la classmethod C3b devra rendre, sous forme d'ensemble trié.
Vérifier qu'aucune classe ne rend une liste vide (§ A.8 : erreur d'entrée). Le 4 h est-il toujours
présent ? Si une classe rendait `{}`, le dire — c'est un fait pour C3b, pas à corriger ici.

### Étape 3 — amorçage mesuré (base serveur, lecture seule)

Sur le serveur, sous `~/runs/sol_d2/`. Écrire `scripts/audit/warmup_at.py` : lecture seule, importe
`load_context_series` et `warmup_needs` de `scripts/backtest.py` **sans les modifier**, réutilise les
mêmes `load_window` / `load_before` que le moteur (retrouvés aux sites d'appel), et appelle
`load_context_series` avec **exactement** les arguments que le moteur passerait pour
`start = 2021-03-01T00:00:00Z`, `end = T` (prendre la borne du protocole), `window_start` calculé
comme le moteur le calcule — si `window_start` dépend d'une extension calendaire, le reproduire, ne
pas l'approximer.

Séries à mesurer, par paire BTC/USDT, ETH/USDT, SOL/USDT, `exchange = 'binance'` :
`5m`, `4h`, `1d`, `1w`, avec `required` = ce que `warmup_needs(_indicator_requirements(...))` donne
pour la stratégie aux paramètres par défaut (`atr_period = 14`). Si le 5 m n'apparaît pas dans les
requirements de cette stratégie, le mesurer quand même avec `required = 0` et le dire : D1 le couvre,
D2 non.

Sortie : `results/sol_d2_1w_modes/warmup_2021-03-01.json` (writer strict, pas de `default=str` —
dette 22) avec, par paire × TF : `interval, required, loaded, extended_by, stale_by_candles,
largest_gap_candles, sufficient, first, last`, plus `git_sha`, `db_row_count_binance` (contrôle :
attendu 11 952 996), `generated_at`.

Contrôle croisé obligatoire : SOL 1 w `loaded` attendu 29 et `first = 2020-08-17`. Si l'un des deux
diffère, s'arrêter et rapporter avant d'aller plus loin.

Contrôle des rows dérivées : les 8 estampilles 1 w reconstruites sont hors de `(−∞, 2021-03-01]`,
donc aucune ne doit entrer dans `loaded`. Le vérifier par une requête sur `ohlc_derived` jointe aux
stamps chargés ; écrire le résultat (attendu : 0 row dérivée dans l'historique d'amorçage).

### Étape 4 — table D2

Table C = Table B × {BTC, ETH, SOL} → `D2 = AND(sufficient[tf] for tf in TF_de_décision)`. Une
cellule = `pass` / `fail(tf: loaded/required)`. Puis, en clair : sur SOL, quelles classes survivent,
lesquelles sortent, et si l'ensemble des classes survivantes est vide. Sur BTC et ETH : attendu
`pass` partout ; si un `fail` apparaît, c'est un fait nouveau — le mettre en tête du rapport.

### Étape 5 — protocole

Citer § I.1 lignes 4-5 et § A.8 (portée candidat de D2) : un candidat SOL retiré par D2 ne retire pas
la paire ; la campagne est partielle sur SOL. Écrire ce que le manifeste devra déclarer
(`decision_timeframes` par stratégie ou par candidat, § A.8 ; les 8 estampilles dérivées, ROADMAP)
et ce qu'il ne devra pas faire (déplacer le début du préfixe pour sauver SOL est un choix d'univers,
§ A.5, pas une conséquence de cette mesure). Ne rien trancher.

## Validation

- `scripts/audit/warmup_at.py` : couche pure (construction des arguments, agrégation, D2 par classe)
  testée dans `tests/test_scripts/test_warmup_at.py`, marqueur `db` sur tout test qui touche la base ;
  ruff + mypy propres.
- Le JSON se relit et le rapport en dérive ; chaque chiffre du rapport est dans le JSON.
- Le rapport cite chaque ligne de code par `fichier:ligne` au SHA courant.
- Aucune requête d'écriture, aucune migration, `alembic current` inchangé avant/après
  (`c3bd1e7a0001`). Le noter dans le rapport.
- `~/runs/sol_d2/` supprimé à la clôture ; le rapport le dit.

## Livrables

- `scripts/audit/warmup_at.py` + tests
- `results/sol_d2_1w_modes/report.md` (tables A, B, C ; § I.1 ; contrôles), `warmup_2021-03-01.json`
- `docs/RESEARCH_LOG.md` : une entrée **seulement si** un fait nouveau apparaît (BTC/ETH `fail`,
  axe de paramètre inattendu, `loaded` SOL ≠ 29, rows dérivées dans l'amorçage). Sinon rien.
- `ROADMAP.md` : une ligne sous les exigences C3b si l'écart « requirements statiques ≠ décision »
  n'y est pas déjà nommé.

## Commits attendus (atomiques, sur `dev`)

1. `feat(audit): warmup_at — amorçage C2 mesuré à une date, lecture seule` (script + tests)
2. `docs(results): mesure SOL/D2 et classes decision_timeframes au 2021-03-01` (rapport + JSON)
3. `docs: RESEARCH_LOG / ROADMAP` — uniquement si les conditions ci-dessus sont remplies

## Hors scope

La classmethod `decision_timeframes` (C3b). Toute écriture en base. Tout changement dans
`scripts/backtest.py`, les stratégies, les modèles. L'univers de candidats. La dette 21, 24, tunnel.
Si une anomalie hors périmètre apparaît, la noter dans le rapport et s'arrêter là.
