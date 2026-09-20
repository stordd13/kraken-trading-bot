# Rejeu diagnostic grid — sous instrument réparé (post-C1/C2) — v2

> Brief agent, **version 2** (2026-09-19), après challenge croisé. Changements v1 → v2 :
> (i) l'égalité de sorties mesure une **indiscernabilité**, pas une identité de comportement — la
> dégénérescence du spacing devient une **mesure directe** sur les séries, plus une inférence ;
> (ii) la couverture se mesure en **cycles grid** (hors liquidation terminale) et l'equity
> forward-fillée ne prouve pas l'exposition ; (iii) les Sharpe B&H 0.84/0.30 ne sont **pas** des
> seuils applicables tels quels (dette 15(c) : borne `< P6_END` vs `<= end`, pas de liquidation
> côté benchmark) ; (iv) « dispersion train/test » retirée des bornes d'incertitude, la
> multiplicité des 96 essais doit être traitée ; (v) la règle d'agrégation **config → paire →
> famille** est figée au gate 1 ; (vi) le segment `all` porte le diagnostic, et les scripts de
> post-traitement sont explicitement autorisés. Ajouts : mesure du clamp de spacing, règle
> « échantillon trop petit », admissibilité SOL tranchée avant le run.
>
> Mode : **plan mode, deux gates**. Branche : `feat/rejeu-grid-diag` depuis `dev`
> (@ tag `v2.10.0-c2-replay`). Assert `git branch --show-current == feat/rejeu-grid-diag` avant
> chaque commit ; un seul acteur git ; une découverte annexe se **signale**, ne se traite pas.

## Les deux gates

- **Gate 1 — plan + pré-spécification gelée.** L'agent propose (a) le plan d'exécution et (b) un
  document de pré-spécification fixant **avant tout run** : métriques, seuils, règle de décision,
  règle d'agrégation, définition des trois verdicts, méthode d'incertitude, admissibilité par
  paire, mesure de dégénérescence. Arrêt strict jusqu'à validation humaine. La pré-spécification
  est **committée avant le lancement** et ne bouge plus.
- **Gate 2 — résultats et verdict** rendus contre les critères gelés, sans latitude. Aucun seuil
  n'est réinterprété après coup ; un seuil qui se révèle mal choisi se consigne comme tel et le
  verdict reste celui que la règle gelée produit.

## À lire avant toute ligne

1. `CLAUDE.md`, `PROJECT_CONTEXT.md` (état post-C2, dettes 13/14/15/16/17), `docs/CODE_MAP.md`
2. `docs/CONTRAINTES_POST_B4.md` — **§ 2 coûts, § 3 tension, § 4 benchmark, § 5 morts, § 7
   protocole, § 8 basse rotation** : c'est le cadre de décision de ce chantier
3. `results/C2_replay_report.md` — ce qui a changé dans ce qui est simulé, et le constat rétroactif
4. `results/B4_bybit_backtest_report.md` (addendum en tête) et
   `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md`
5. `skills/backtest.md` (§ Métriques C1, § Replay C2), `skills/deployment.md`, `skills/database.md`
6. `docs/RESEARCH_LOG.md` — l'entrée de ce run y est écrite **avant** le lancement (décision 17)

## Contexte

B4 a rendu 0/48 sur le grid × SOL et un meilleur grid BTC sous le seuil — **avec un instrument
depuis invalidé**. C1 a réparé la mesure, C2 ce qui est simulé. Conséquence à garder présente : sur
la fenêtre gold le grid passe de 45 à 2 trades, l'espacement tape le plafond, et le régime
hebdomadaire n'était pas amorcé sur les 19-21 premières clôtures des segments train/all. **Le grid
que ce rejeu exécute n'est pas celui qui a produit le 0/48.** Les classements B4 ne sont ni un point
de comparaison ni une attente.

Ce rejeu est un **diagnostic pré-spécifié** (décision 15 du `ROADMAP.md`) : hors quota des deux
familles par cycle, mais inscrit au journal des essais. Il ne peut **rien sélectionner** : toute
sélection relève du protocole C3, qui n'existe pas encore.

## Objectif

Répondre à une seule question : **la famille grid, dans ce périmètre gelé, mérite-t-elle un travail
supplémentaire, ou est-elle dépriorisée ?** Avec une troisième issue pleinement admissible :
**inconclusif**.

## Périmètre figé (aucune extension, avant comme après les résultats)

- Stratégie : `grok_grid_atr_adaptive_v4` uniquement.
- Paires : **BTC/USDC et SOL/USDC** (ETH hors périmètre, comme en P7).
- Grille : `GRID_ATR_GRID` de `scripts/p7_grids.py` **inchangée** — `min_spacing_pct`
  [0.015, 0.020, 0.025, 0.030] × `atr_multiplier` [1.5, 2.0, 2.5, 3.0] × `bear_protection_mode`
  ["none", "1w_only", "1d_only"] = 48 par paire, **96 configs**.
- Période : **2023-04-01 → 2026-04-01**, `--exchange binance`, `--fees bybit`,
  `--pair-costs-file config/pair_costs_b4.json`, `--min-order-usdc 5`.
- Paramètres : **défauts de classe** (dette 13 non fixée — `max_spacing_pct` reste à 0.05, lots au
  défaut de classe). À documenter en tête du rapport, pas à corriger.
- **Phase 1 uniquement.** Pas de phase 2 walk-forward, pas de `--report` / `--selection` : le
  walk-forward actuel n'est pas chronologique (note WF → C3) et le rapport P7 émet du langage de
  sélection (`selected_for_paper`).
- **Segment principal = `all`** (continu sur la période). `train` et `test` sont des analyses
  secondaires : jamais concaténés, jamais comptés comme preuves indépendantes de `all`. Les 96
  configs produisent 288 simulations de segments : ce n'est pas 288 observations.
- Sorties dans de **nouveaux chemins** (`results/rejeu_grid_20260919/…`) : les fichiers B4 et C1
  sont inécrasables, la garde `replay_version` 2 refuse tout mélange.

**Interdit d'office** : élargir la grille, ajouter une paire, changer la période, toucher
`max_spacing_pct`, fixer la dette 13, modifier moteurs / stratégies / runners / configs /
dépendances, relancer avec un périmètre modifié après avoir vu les résultats. Un périmètre qui se
révèle mal choisi est un **résultat**, pas une invitation à le réajuster.

**Autorisé** : scripts de **post-traitement** (signatures, comparaisons, incertitude, mesure du
clamp), archivés sous `scripts/audit/`, conformes à la pré-spécification, ne modifiant aucune
simulation. Contrôle de fin : `git diff --stat dev..HEAD -- src scripts/backtest.py
scripts/run_p6_backtests.py scripts/run_p7_grid_search.py scripts/p7_grids.py tests config
pyproject.toml poetry.lock` **vide**.

## Ce que la pré-spécification doit fixer (gate 1)

### 1. Indiscernabilité des configs — et mesure séparée du clamp

Le runner P7 exporte les métriques, l'equity quotidienne et les diagnostics, **pas** le journal
complet des transactions ni l'exposition au cours du temps. Donc :

- **Classes d'indiscernabilité**, sur une signature définie **avant** lancement, incluant l'equity
  quotidienne complète et les agrégats comptables. Résultat attendu : « 96 configs → N classes
  indiscernables sur les sorties disponibles », par paire. Pour B4, comparaison limitée aux champs
  historiquement conservés.
- **Ne jamais présenter cette égalité comme une preuve** d'identité des ordres ou de saturation du
  spacing.
- **Mesure directe du clamp, hors simulation** (post-traitement autorisé) :
  `spacing = clamp(ATR(14,4h) × atr_multiplier / price, min_spacing_pct, 0.05)` recalculé depuis
  les séries 4 h de la DB pour chaque couple (multiplicateur, plancher), et fraction des clôtures
  4 h **au plancher / à l'intérieur / au plafond**, par paire et par sous-période. C'est ce qui
  transforme l'hypothèse « axe ATR mort sous l'instrument v1, plafond saturé sous l'instrument
  réparé » en constat. Tant que cette mesure n'est pas produite, l'hypothèse est étiquetée comme
  telle dans le rapport.

### 2. Couverture réellement mesurable

Deux pièges présents dans le code :

- `total_trades` du grid **inclut les liquidations terminales**. Rapporter séparément les **cycles
  grid achevés** (`total_trades − liquidation.positions`) et les liquidations ; conserver toutes
  les liquidations dans les résultats économiques. Le seuil de couverture porte sur les **cycles**.
- L'equity quotidienne **prolonge la dernière valeur connue**, y compris à travers des périodes
  sans données : trois ans de points exportés ne prouvent pas trois ans d'exposition observée. La
  voie « ~3 ans d'equity à exposition non triviale » du § 8 n'est utilisable que si une mesure
  d'exposition **et** de couverture des données est définie et disponible ; sinon elle est écartée
  et seul le repère en cycles s'applique.

Seuil de couverture (§ 8 : ~25-30 round-trips sur la période) : **défini par config, écrit avant
les résultats**. En dessous : inconclusif, et **inconclusif = pas de déploiement**.

### 3. Admissibilité par paire, tranchée avant le run

Le trou SOL (2022-09-29 → 2023-12-28) tombe **à l'intérieur** de la période simulée : sur
2023-04-01 → 2026-04-01, il reste environ **27 mois** de données réelles, contre les **« 3+ ans de
backtest »** posés comme non négociables au § 7 des contraintes. Conséquence à trancher au gate 1 :
si la mesure confirme ce déficit, **aucun résultat SOL ne peut produire un verdict « candidat »**,
quel que soit son contenu — il reste descriptif et alimente le diagnostic. Décider cela avant les
résultats, jamais après.

Documenter `warmup.sufficient=False` ne suffit pas : l'effet du trou **dans la période simulée**
(et non seulement dans le warmup) est gelé au gate 1 comme règle d'admissibilité.

### 4. Benchmark d'exposition — à construire, pas à citer

Les Sharpe B&H 0.84 (BTC) / 0.30 (SOL) restent des **repères historiques descriptifs**. Ils ne sont
pas des seuils applicables tels quels : `compute_benchmarks.py` charge en `< P6_END` là où les
moteurs chargent `<= end` (**dette 15(c)**, un jour d'écart), ne subit aucune liquidation terminale
contrairement au grid, et ses dates effectives dépendent des données disponibles.

Le gate 1 fixe donc : dates communes, conventions de coûts et de liquidation, traitement du cash,
comparaison du risque, et **drawdown quotidien contre quotidien**. Si un benchmark comparable ne
peut pas être produit dans le périmètre autorisé (post-traitement inclus), les chiffres historiques
restent descriptifs et **ne fondent aucun verdict économique** — ce qui, en soi, pousse vers
« inconclusif ».

### 5. Borne d'incertitude — nommée, pas quelconque

« Dispersion train/test » est un diagnostic de stabilité, **pas** une borne d'incertitude : retirée.
La pré-spécification nomme :

- l'**effet évalué**, de préférence relatif au benchmark ;
- la **méthode et ses paramètres** ;
- le traitement des **valeurs indéfinies** (`None`, PF infini — contrat C1) ;
- la **prise en compte des 96 essais** si le verdict dépend du meilleur : un intervalle calculé
  config par config ne corrige pas la sélection du maximum (multiplicité ; cf. Bailey &
  López de Prado sur le Sharpe dégonflé). Aucun outil n'est imposé, mais « une méthode écrite
  avant » sans traitement de la multiplicité ne suffit pas.
- **Règle « échantillon trop petit »** : si le nombre de cycles tombe sous ce que la méthode
  retenue exige, le verdict est **inconclusif par règle** — on ne calcule pas quand même pour
  commenter le chiffre.

### 6. Règle d'agrégation config → paire → famille

Figée au gate 1, avec au minimum :

- passage **config → paire** (que fait-on des configs invalides, non admissibles ou sous le seuil
  de couverture ?) ;
- passage **paire → famille**, dont le cas réel attendu **BTC exploitable / SOL inadmissible ou
  inconclusif** ;
- **run portant une anomalie comptable non résolue = non exploitable.** « Flag investigué » ne le
  rend pas admissible. La dette 14 étant corrigée, `b4_flags` doit être muet : un flag est un
  **échec du run**. Les assertions de présence et de validité passent avant les tolérances
  (`collect_flags` saute silencieusement les entrées portant `error`).

### 7. Définition opératoire des trois verdicts

- **candidat** — la famille, dans ce périmètre, justifie un travail supplémentaire (et devra de
  toute façon passer C3 avant tout paper) ;
- **dépriorisation** — porte sur **ce grid et ce périmètre gelé**, pas sur l'impossibilité
  économique de toute stratégie grid ; rejoint le § 5, ne revient qu'avec un mécanisme nouveau ;
- **inconclusif** — couverture insuffisante, benchmark non comparable, échantillon trop petit ou
  admissibilité non satisfaite : pas de déploiement, pas de tuning supplémentaire, on note pourquoi.

**Dégénérescence ≠ inconclusif automatique** : plusieurs paramètres donnant la même sortie réduit
l'information sur les paramètres, cela n'empêche pas d'évaluer le résultat observé.

### 8. Blocs de warmup

Consigner par paire et par segment ce qui a été réellement chargé (`required`, `loaded`,
`stale_by_candles`, `largest_gap_candles`, `sufficient`). Un segment `sufficient=False` **qualifie
la portée** du résultat correspondant selon la règle gelée en § 3 ; il ne s'ignore pas.

## Exécution

- **Sur le serveur, en checkout isolé** (jamais l'arbre ni le venv du service), DB en accès local.
  Précédent C2 : 41 min par combo via le tunnel contre 238 s en local.
- Interdits : merge, déploiement, `systemctl`, modification du `.env` serveur, dispatch de workflow.
  Parallélisme plafonné pour laisser de la marge au collector ; après le lot, vérifier le service
  actif et l'absence de trou 1 m sur la fenêtre du run.
- Entrée `docs/RESEARCH_LOG.md` écrite **avant** le lancement : périmètre, version du code, modèle
  de fees, critères gelés, verdicts possibles.
- Vérifier avant le run que la migration Alembic `c1ae7a1c0001` est appliquée sur le serveur (ne
  bloque pas la campagne — les runners n'écrivent pas en DB — mais le signaler si absent).

## Livrables

- `docs/rejeu_grid_prespec.md` — pré-spécification gelée, committée avant le run (gate 1).
- `results/rejeu_grid_20260919/` — artefacts (96 résultats, JSON `replay_version` 2).
- `scripts/audit/` — scripts de post-traitement archivés (signatures, clamp, benchmark, incertitude).
- `results/rejeu_grid_report.md` — périmètre, pré-spécification référencée, classes
  d'indiscernabilité, mesure du clamp, cycles grid et couverture, benchmark d'exposition (ou
  constat qu'il n'est pas comparable), bornes d'incertitude avec traitement de la multiplicité,
  blocs de warmup, admissibilité par paire, **verdict par la règle d'agrégation gelée**,
  découvertes annexes signalées.
- Mise à jour `results/INDEX.md`, `docs/RESEARCH_LOG.md` (issue du run), ligne « rejeu grid » du
  `ROADMAP.md`.

## Critère de fin (done)

- [ ] Gate 1 passé : plan + pré-spécification validés puis committés **avant** tout run
- [ ] Entrée RESEARCH_LOG écrite avant le lancement
- [ ] 96 runs au périmètre gelé, artefacts `replay_version` 2, `b4_flags` muet (sinon run non
      exploitable), assertions de présence/validité avant tolérances
- [ ] Classes d'indiscernabilité rendues (96 → N, par paire, + lecture rétroactive B4 sur les
      champs conservés), **sans** les présenter comme identité de comportement
- [ ] Mesure du clamp produite (plancher / intérieur / plafond) ou hypothèse explicitement
      étiquetée comme non mesurée
- [ ] Couverture en **cycles grid** mesurée contre le seuil gelé ; liquidations rapportées à part
      et conservées dans l'économique
- [ ] Admissibilité SOL tranchée selon la règle gelée en § 3
- [ ] Benchmark d'exposition comparable produit, ou constat écrit qu'il ne l'est pas
- [ ] Borne d'incertitude avec traitement de la multiplicité, ou règle « échantillon trop petit »
      appliquée
- [ ] Verdict rendu **par la règle d'agrégation gelée**, sans réinterprétation post-hoc
- [ ] Zéro modification de code hors `scripts/audit/` (diff de contrôle vide)
- [ ] Serveur intact : collector actif, aucun redémarrage, aucune trace de trou 1 m

## Commits attendus (indicatif)

- `docs(rejeu): pre-specification for the grid diagnostic replay (frozen)` *(gate 1)*
- `chore(rejeu): research log entry before campaign launch`
- `chore(rejeu): campaign artifacts (96 configs, BTC/SOL, replay_version 2)`
- `feat(audit): post-processing scripts (signatures, spacing clamp, benchmark, uncertainty)`
- `docs(rejeu): grid diagnostic report + verdict + index/roadmap update`
