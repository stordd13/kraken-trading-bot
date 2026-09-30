# C3 — Outillage v2.2 : lever les huit réserves et l'item hors réserve

Nouvel agent. **Plan mode** : tu proposes un plan par lot, il est validé avant la première ligne de code du
lot. **Trois lots, une session agent par lot**, chacun avec son critère de fin mécanique.

Brief rédigé le 2026-09-29 au `dev = 8c114fe` (`8c114fea49c6290f80010a1ae3fe99c347f3254b`). Protocole C3
**v2.2 gelé**, sha256 `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`.

Hiérarchie des textes, en cas d'écart :
1. `docs/protocole_c3.md` v2.2 fait foi sur le fond (§ 0.7) : tu t'arrêtes et tu signales, tu n'arbitres pas.
2. `results/c3_v2_2/outillage_v2_2.md` est **la liste close du chantier** : elle fait foi sur le détail des
   items (fichiers, lignes, tests). La section Adoption de `docs/amendements_c3_v2.2.md` fait foi sur le
   **statut** des réserves.
3. Ce brief ordonne et cadre ; là où il contredit 1 ou 2, ce sont eux qui priment, et tu le signales.

**Tout besoin de texte découvert en chantier est un candidat v2.3** : consigné au rapport, jamais implémenté
« en convention ». La discipline du 21/09 s'applique. Tout item qui semble exiger `src/` ou
`scripts/backtest.py` : **STOP**, pas une exception.

## À lire d'abord

- `results/c3_v2_2/outillage_v2_2.md` **en premier et en entier** : c'est la liste close, un item par
  réserve, avec fichiers, lignes, xfail à lever, artefacts C3b non conformes.
- `CLAUDE.md` (routeur), `PROJECT_CONTEXT.md` § 1 (état au 29/09), dettes 19, 21, 23, 24.
- `docs/protocole_c3.md` v2.2, dans cet ordre : § L.1 (les **sept** entrées, ligne 0 et ligne 6), § L.2
  (recoupements, NAV du comparateur, frontière des motifs), § A.6 (famille, statut compté, évaluation
  différée, refus § 10.1), § A.7 (positions nommées `_quote`, dates de couverture), § A.8 D4 (« définis et
  tous finis », « Le CAGR qui déborde »), § B.8 (« Ce qu'exige `validé` » — **ne change pas**), § C.5-C.6
  (comparabilité), § F.2 (d), § I.1 (forme d'un diagnostic, frontière ligne 2 / ligne 15), § J items 12-13,
  § K.1, § L.5.
- `docs/amendements_c3_v2.2.md` : section **Adoption** (décisions C-1 à C-6, statuts), puis AM-03, AM-04,
  AM-05, AM-06, AM-08, AM-09, AM-10 avec leurs blocs « Impact outillage » et « Test attendu ».
- `results/c3_v2_2/report.md` (défauts du chantier v2.2), `results/c3_v2_2/phase1.md` § 1 (classification
  des cinq sorties code 1 — les cas 1 à 4 sont R-22).
- `results/c3b_producteur/report.md` § « Défauts » et lot 4b (la conformité 2020 du 28/09 : **c'est ce que
  le lot 3 rejoue sous v2.2**) ; `agent/AGENT_C3B_PRODUCTEUR.md` § « Écarts constatés » (notamment écarts
  12 — registre neuf sous la sortie du run — et 14-15, devenus R-18 et R-15).
- `skills/backtest.md` § « Validation C3 » et « Producteur C3b », `skills/database.md`,
  `skills/deployment.md` (`~/runs/<chantier>/`, lanceur, archive).
- Le code, **en lecture avant toute écriture** : les neuf `scripts/audit/c3*.py` de la liste close, et les
  46 tests `xfail` (`grep -rn "def test_R1[5-9]_\|def test_R2[0-2]_\|def test_hors_R_" tests/test_scripts/`),
  avec leurs mondes et fixtures (`test_c3_common.py` : `fx.evaluation`, `fx.manifest`, `_chain_world`).

## Contexte

v2.2 est adoptée le 29/09 **texte et tests seulement** : aucune ligne de `scripts/audit/*.py` ni de `src/`
n'a changé depuis `8689636`. Les 46 tests `xfail(strict=True, raises=…)` portent l'attendu du texte ; ce
chantier livre le code qui les fait passer, retire les marqueurs, puis **rétablit la conformité du
producteur sous v2.2** — celle du 28/09 (v2.1) n'a plus de valeur probante. Sous v2.2, `c3_anchor` refuse
tout manifeste v2.1/v2.0 : les artefacts C3a et C3b sont historiques, on ne les répare pas, on reproduit.

État de départ : suite 3 246 passés + 46 xfail, 0 échec, 0 XPASS ; `mypy src/` = 65 ; gold intact ;
alembic `c3bd1e7a0001` ; `results/c3b_producteur/CAMPAIGN_UNLOCK` **n'existe pas et ne se crée pas ici**
(le producteur refuse, code 2, toute fenêtre finissant après le 2021-03-01 — la fenêtre de conformité 2020
passe ce garde-fou par construction).

## Décisions déjà tranchées — ne pas rouvrir

1. **L'attendu des 46 xfail est normatif, leur interface d'appel indicative.** Attendu = code, issue,
   raison, motif, clé exigée : il ne se change **jamais**. Interface = noms de clés (`lambdas`, `family`,
   `verdict`, `deferred_evaluation`, `refused`), option `--candles-eval`, entrées du dictionnaire
   d'artefacts : tu peux la compléter ou la renommer **en le déclarant** au plan et au rapport. Un xfail
   levé en modifiant son assertion n'est pas levé. Un XPASS force la suppression du marqueur, rien d'autre.
2. **Décisions de rédaction C-1 à C-6** (STOP 1 du 29/09) : C-1 identité recoupée avant lecture du bloc
   `refused` ; C-2 clause 3 vérifiée à vide sur `lots: []` (déjà le cas — aucun outillage), NON VÉRIFIABLE
   si la clé est absente ; C-3 deux motifs seulement (`comparator_not_buildable`,
   `comparator_not_comparable`), recalcul impossible sur une évaluation non refusée = violation ; C-4
   recoupement sur la NAV du B&H plein notionnel, le blend en découle ; C-5 `continuite=-` chaque fois
   qu'aucun état de clause n'entre dans l'issue ; C-6 clé `metrics.executions`, jamais `total_trades`
   (homonyme moteur : `pairs_completed + liquidated_positions`, `scripts/backtest.py:3326` — tu ne le lis
   pas, tu exportes les remplissages de `engine.metrics.trades`).
3. **AM-08 en implication seule** : `first_fill_at` nul ⟺ `executions == 0` ; `executions == 0` ⟹
   `equity_daily` constante `= C`. Rien dans l'autre sens.
4. **AM-04 borné aux deux positions nommées** (ligne Contrats `min_order_quote` ; bloc de liquidation et
   lots `gross_quote`). Hors de ces positions, un suffixe de monnaie n'est **ni lu ni refusé**. L'argument
   moteur `min_order_usdc=` de `backtest.py` ne bouge pas : AM-04 vit dans la couche d'export
   (`c3b_common.py`) et dans les gardes de forme de la chaîne. Clé du manifeste : `min_order_quote`.
5. **AM-05** : famille au manifeste ; statut compté écrit par `c3_verdict` à l'étape 6 (issue, raison,
   compté ; pour une évaluation différée : date déclarée et empreinte attendue), écrit une fois — une
   réécriture différente est une violation ; `c3_anchor` refuse une seconde campagne comptée sur la
   famille, une relance au-delà de l'unique, et sur une famille close toute variante dont l'empreinte n'est
   pas la différée attendue. Registre **unique et persistant** pour les campagnes ; les runs de conformité
   utilisent un registre **neuf sous la sortie du run** (écart 12 C3b), jamais le registre de campagne.
6. **Le § B.8 et `test_c3_verdict.py:3167` ne changent pas** (R-18).
7. **Chemin sélection intouché** : `rejeu_common` intouché, gold intact, aucune sortie du chemin sélection
   versionnée ou ouverte.

## Liste close des fichiers

- **Modifiés** : `scripts/audit/c3_common.py`, `c3_entry.py`, `c3_anchor.py`, `c3_benchmark.py`,
  `c3_select.py`, `c3_continuity.py`, `c3_verdict.py`, `c3b_common.py`, `c3b_evaluate.py` — aux positions
  que `outillage_v2_2.md` nomme, item par item.
- **Tests** : `tests/test_scripts/test_c3_*.py`, `test_c3b_*.py` — retrait des 46 marqueurs, complétion des
  mondes et fixtures (entrées nouvelles, `fx.evaluation`, `fx.manifest`, `_chain_world`), renommage des
  fixtures simulées R-16 avec le code, le témoin R-17 neuf. **Aucun attendu modifié, aucun test supprimé.**
- **Nouveaux** : `results/c3_outillage_v2_2/` (plans, `tests/*.sh` + `.out`, rapports de lot, rapport
  final, `mutants.log`).
- **Docs à la clôture** : `PROJECT_CONTEXT.md`, `docs/RESEARCH_LOG.md` (entrée 19), `results/INDEX.md` ;
  `docs/CODE_MAP.md` régénéré au merge (Bruno).
- **Interdits** : `src/` en entier, `scripts/backtest.py`, les runners P6/P7, `rejeu_common.py`,
  `docs/protocole_c3.md`, `docs/amendements_c3_v2.*.md`, `~/docker/` (dette 23), tout fichier de
  `results/c3_v2_2/` (chantier clos) et de `results/c3b_producteur/` hors lecture.

Branche : `feat/c3-outillage-v2.2` depuis `dev = 8c114fe`. Push de sauvegarde en fin de lot ; **jamais de
merge avant la porte** ; le merge est fait par Bruno.

## Lot 1 — chaîne pure : R-15 (côté chaîne), R-21, R-22, R-17

Dans cet ordre (bloquant manifeste d'abord, R-17 en dernier).

- **R-15 côté chaîne** (`outillage_v2_2.md` § R-15) : septième entrée `candles_eval.json` au parseur
  `chain` (`--candles-eval`) et à `verify_chain` ; règle d'entrée (une paire, aucune estampille > fin,
  jamais tronquée) ; recalcul de `returns_config` sur `equity_daily` par `cc.recompute_daily` ; lecture de
  `benchmark.json` et recoupement des λ déclarés ; reconstruction du B&H (`cb.build_pair`) et du blend
  (`cb.blend_nav`) sur l'export, recoupement de `returns_bench` et de la NAV du comparateur **au bit** ;
  recalcul impossible sur une évaluation non refusée = violation. 8 des 9 xfail R-15 (le neuvième,
  `test_c3b_evaluate.py`, est au lot 2) ; complète `fx.evaluation` et `_chain_world` sans toucher les
  attendus.
- **R-21** : CAGR non défini sans exception (`recompute_daily`, `cagr_pct`), D4 le retire
  (`estimable: false`, `first_failed: D4`), code 0. Les 2 xfail portent `raises=OverflowError` : leur levée
  supprime l'exception, le marqueur, et rien d'autre.
- **R-22** : les quatre formes dues (cas 1 registre non fini → diagnostic code 1 ; cas 2 NAV décimale,
  rendements non finis non écrits → paire non comparable code 0 ; cas 3 D4 « tous finis » → retrait code
  0 ; cas 4 non-fini fourni non recopié → diagnostic code 1). 4 xfail.
- **R-17** : famille obligatoire au manifeste (`load_manifest`), refus R0 à l'ancrage (seconde campagne
  comptée, relance au-delà de l'unique, empreinte non différée sur famille close), champs d'issue hors
  `RECORD_KEYS` pour que l'idempotence tienne, écriture du statut à l'étape 6 par `c3_verdict` (table du
  § 10.1 recopiée dans un test et épinglée à la constante du code). 5 xfail, **plus le témoin à écrire** :
  sur une famille close, la variante de l'empreinte différée attendue est acceptée — vérifié par mutation.

**Critère de fin du lot 1** :
- Les 20 xfail du lot levés (marqueurs retirés dans le commit qui livre le code de la réserve — suite verte
  à chaque commit), 0 XPASS, 0 échec, décompte réconcilié par diff d'identifiants contre `8c114fe`.
- Les 4 xfail de chaîne R-18 **restent xfail**, mais échouent désormais sur leur **attendu** (plus sur
  l'option `--candles-eval` inconnue) : prouvé par un script `results/c3_outillage_v2_2/tests/*.sh` qui
  rejoue ces 4 tests en `--runxfail` et compare la nature de l'échec, sortie committée.
- Témoin R-17 vert, mutant qui refuse l'empreinte différée attendue : rouge, consigné à `mutants.log`.
- `ruff` (liste CI) et `mypy src/` = 65 ; mypy strict des `scripts/audit/` modifiés comme au C3b.
- Diff des tests contre `8c114fe` : marqueurs retirés + interface d'appel complétée + fixtures, rien
  d'autre — chaque renommage d'interface déclaré au rapport de lot.
- Tunnel ouvert en début de lot pour les 13 tests base, **fermé et vérifié fermé en fin de lot**. Le
  greffon `gate_sans_tunnel.py` ne s'applique pas à ce chantier.
- Rapport `results/c3_outillage_v2_2/lot1_chaine/README.md`, push de sauvegarde, CI verte (règle : relance
  pour `test_rejeu_effect` seul, tout autre rouge = STOP).

## Lot 2 — producteur et réserves mixtes : R-15 (côté producteur), R-16, R-18, R-19, puis R-20 et hors R

Bloquants manifeste d'abord (R-15p, R-16, R-18, R-19), puis R-20 et l'item hors réserve.

- **R-15 côté producteur** : `evaluation.json` déclare les λ du préfixe (aujourd'hui seulement dans
  `evaluation_sensitivity.json`) ; `benchmark_eval.json` porte la NAV du B&H. 1 xfail.
- **R-16** : `gross_quote` et `min_order_quote` à l'export (`lots_from_trades`, `liquidation_block`,
  `observation_entry`), à la lecture (`PREFIX_WHITELIST_CONTRACTS`, `liquidation_identities`, clé du
  manifeste, garde symétrique de `check_base_quantity_keys` **bornée aux deux positions nommées**),
  `c3_entry` et `c3_select` aux lignes nommées. Fixtures simulées renommées **avec** le code. 10 xfail.
  **Garde-fou** : le témoin vert « suffixe hors positions nommées ni lu ni refusé » reste vert, mutation
  « garde non bornée » à l'appui.
- **R-18** : forme de refus de `evaluation.json` (identité, fenêtre `[T, fin]`, `refused {reason, window,
  motif}`, **aucune série**) + `candles_eval.json` écrit, au lieu du refus 2 sans artefact ; admission :
  identité d'abord, puis route sans contrat § B ; verdict : `E_NO_BENCHMARK` avec son motif, rejeu de la
  non-constructibilité sur l'export (s'appuie sur R-15 du lot 1), `continuite=-`. 5 xfail (les 4 de chaîne
  laissés en attente au lot 1, plus celui du producteur).
- **R-19** : `metrics.executions` exporté (remplissages de `engine.metrics.trades`) et exigé à l'admission ;
  `first_fill_at` nul ssi zéro exécution ; recoupements continuité/verdict ; c5 NOT_VERIFIABLE admis quand
  `first_fill_at` est nul. À vérifier au plan : le cas du lot soldé en poussière. 6 xfail.
- **R-20** : dates de couverture nulles ssi `covered_units == 0`, refus `coverage_no_covered_unit` remplacé
  par l'écriture à dates nulles, `NULLABLE_FIELDS` en conséquence. 4 xfail.
- **Hors réserve** : `cb.build_pair` (`c3b_evaluate.py:544`) déplacé dans le `try` de l'étape 10b →
  `OverflowError` sort en code 3, plus en trace code 1. 1 xfail.

**Critère de fin du lot 2** :
- Les 26 xfail restants levés : **0 xfail dans toute la suite**, 0 XPASS, 0 échec ; décompte final
  réconcilié par diff d'identifiants contre `8c114fe` (46 levés + témoin(s) neufs, aucun supprimé).
- Diff des assertions des 46 tests contre `8c114fe` : identiques hors marqueurs, interface déclarée,
  fixtures — script committé avec sa sortie.
- Témoins R-16 et R-17 verts, mutants consignés ; `ruff`, `mypy src/` = 65, mypy strict audit.
- Aucun changement à `scripts/backtest.py` : `git diff 8c114fe -- scripts/backtest.py src/` vide, prouvé
  dans un `.sh`.
- Tunnel fermé et vérifié en fin de lot ; rapport `lot2_producteur/README.md`, push, CI verte.

## Lot 3 — conformité serveur sous v2.2 et porte § L.5

**La porte de fin de chantier n'est pas « 0 xfail »** : c'est la conformité rejouée sous v2.2.

- **Attendu écrit avant le run, relu par Bruno (STOP 1)**, comme au lot 3 C3b : codes, booléens, liste
  close de ce qui remonte. Règle de non-lecture inchangée : sorties du chemin sélection et verdicts
  archivés, jamais versionnés, jamais ouverts ; seuls remontent codes et booléens sur liste close ;
  **issue non lue**.
- **Rejeu** : fenêtre d'instrument `2020-01-06 → 2020-12-28` (provenance `unknown`), manifeste v2.2 avec
  les nouvelles entrées — famille, `min_order_quote`, λ déclarés, `metrics.executions`, `_quote`, septième
  entrée `candles_eval.json` — registre **neuf** sous la sortie du run. Producteur puis chaîne complète sur
  le serveur (§ J item 12 : la conformité ne se prouve pas en local) : **six étapes en 0, `chain.verified`
  vrai, zéro violation, zéro violation au rejeu**.
- **Déterminisme** : trois exécutions de référence du même run, artefacts **identiques au bit** entre les
  trois (le lot 4b C3b l'a prouvé sur deux ; v2.2 en exige trois).
- **Porte § L.5 option 1** au SHA livré : les 24 `_full` au serveur (`scripts/audit/` change, l'option 2
  est indisponible). `~/runs/c3_outillage/`, preuves versionnées en extrait, brut archivé.
- **Serveur, règles complètes** : clone par push + `checkout --detach <sha>`, venv du service, `PYTHONPATH`
  sur chaque invocation, `pilot_sha256` après `guard=0`, `alembic current` avant/après (=`c3bd1e7a0001`),
  `status.txt` clé=code, pas de `set -e`, pas de `kill` sur la durée, `bash -lc` sous tmux, archive
  vérifiée (`tar -tzf` + sha) avant tout `rm -rf`. Le service reste au SHA de production, collector actif,
  base en lecture seule assertée.

**Critère de fin du lot 3 = porte du chantier (STOP 2)** : rapport final
`results/c3_outillage_v2_2/report.md` — par lot : livré, tests, mutants, écarts au brief et à la liste
close (déclarés, jamais arbitrés), candidats v2.3 consignés, preuves serveur, la phrase « aucune donnée de
la fenêtre de campagne n'a été lue », défauts du chantier. `PROJECT_CONTEXT.md` et `RESEARCH_LOG.md`
(entrée 19) à jour. **Merge par Bruno après relecture.**

## Règles d'exécution

- Shell agent : zsh. Toute vérification qui rend un code passe par `results/c3_outillage_v2_2/tests/*.sh`,
  lancé par `bash`, sortie `.out` committée ; variables quotées ; messages de commit par `-F`. Un greffon
  pytest, s'il en faut un, vit sous `tests/` du chantier, n'est chargé que par le script qui le nomme, avec
  sa preuve de portée.
- Commits atomiques `feat/fix/test/docs/refactor`, un par réserve autant que possible, marqueurs xfail
  retirés dans le commit qui lève la réserve.
- `gh` authentifié, tu lis la CI toi-même. Relance autorisée pour `test_rejeu_effect` seul ; tout autre
  rouge = STOP.
- Base en **lecture seule** partout, aucune migration.

## Gates

| Quand | Quoi |
|---|---|
| Début de chaque lot | plan écrit (items de la liste close couverts, fichiers/lignes, tests, mutants, renommages d'interface prévus) → GO Bruno |
| Fin des lots 1 et 2 | rapport de lot, diff des tests relu, push de sauvegarde, CI verte |
| Lot 3, avant tout run serveur | **STOP 1** : attendu de conformité écrit et relu |
| Fin du lot 3 | **STOP 2** : rapport final, porte § L.5, docs — avant merge |
| Tout besoin hors liste close, tout besoin de texte, tout besoin de toucher `src/` ou le moteur, tout doute sur un attendu | **STOP** |

## Ce que ce chantier ne fait pas

- Le manifeste de la première campagne, `CAMPAIGN_UNLOCK`, la dette 21 (`--campaign`), la dette 24
  (spread/slippage Bybit), l'univers P7, les 8 estampilles dérivées, `min_order_quote` réel Bybit, le
  capital représentable, `decision_timeframes` multi-classes, la famille de la variante réelle :
  **conversation manifeste**, après ce chantier.
- Tout texte : v2.2 est gelée, les candidats v2.3 se consignent (dont le nom de test périmé
  `..._n_est_pas_rejouable_sous_v21`, `test_c3_entry.py:709` — il ne se corrige pas ici).
- Les candidats de clôture (marqueur db à fixture, `test_rejeu_effect`, monde synthétique estimable,
  fabrique en Decimal, `git_provenance` étendue) : consignés si croisés, pas ouverts.
- `src/`, `scripts/backtest.py`, `rejeu_common`, le moteur signal (dette 19), `~/docker/` (dette 23).
- Toute lecture économique d'un run de conformité.
