# Chantier 2 — Fidélité du replay (post-audit B4) — v2.1

> Brief agent, **version 2.1** (2026-09-16), après deux passes de challenge croisé : revue externe
> (Astra) + contre-vérification intégrale sur le code au commit `a07eb73` (8 commits après le tag
> `v2.9.0-c1-metrics`). Retouches v2 → v2.1, toutes vérifiées sur le code : (i) la justification
> « le moteur signal exécute au close » était **fausse** (`_resolve_fill:760` : exécution sur N+1,
> open pour market, touch pour limit) — remplacée par le constat neutre ; (ii) décision 5 :
> distinction **rejet replay** vs **fill live acquis** (réconciliation, pas de rejet), et
> équivalence des identifiants à démontrer (le signal grid n'émet pas de `position_id` :542,
> le payload de fill le propagerait :670) ; (iii) l'invariant protège **la configuration de
> référence** SuperTrend A, dont l'historique d'initialisation est conservé exactement face au
> redimensionnement R2 du warmup ; (iv) la preuve 1 couvre **toutes les entrées consommées** par la
> décision grid (ATR 4 h, EMA/régime 1 d, régime 1 w), bougies clôturées seulement.
> Changements majeurs v1 → v2 : (1) R1 sépare explicitement alimentation /
> décision / exécution et l'ordre à timestamp égal est **tranché** (l'ordre proposé en v1
> introduisait un look-ahead d'exécution) ; (2) R4 passe de « tolérance relative » à **appariement
> par `position_id` obligatoire** + validation avant mutation des soldes ; (3) le côté « avant »
> est **re-capturé au tag C1** (les captures `c1_ab/*_new` datent d'un commit intermédiaire
> `76bde08` et sont incomplètes) ; (4) l'invariant maître exige un **mode strict** du comparateur
> (le mode C1 ignore Sharpe/PF/MaxDD par construction) ; (5) R2 est piloté par les **params
> effectifs**, pas les défauts ; (6) la preuve DCA ne dépend plus d'un résultat de marché.
>
> Mode : **plan mode** — proposer un plan détaillé, attendre validation humaine, puis exécuter.
> Branche : `feat/c2-replay` depuis `dev` (après le merge du chore docs).
> Règles permanentes : assert `git branch --show-current == feat/c2-replay` avant chaque commit ;
> toute intervention humaine parallèle passe par un worktree séparé ; une découverte annexe se
> signale, ne se traite pas.

## À lire avant toute ligne de code

1. `CLAUDE.md` (règles d'or — dont fichiers protégés et review humaine) et `docs/CODE_MAP.md`
2. `PROJECT_CONTEXT.md` — §5 (métriques v2 / fees), §9 (dettes 14, 16, et la dette 17 créée par ce
   brief), état post-audit
3. `skills/backtest.md` (spec métriques C1 — **figée**, ce chantier ne la touche pas) et
   `skills/new_strategy.md` (le chantier modifie un fichier de stratégie)
4. `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` — phase 1 §3 (stratégies différentes de
   celles annoncées) et §7 (exécution)
5. `results/C1_metrics_report.md` et `scripts/audit/c1_equity_probe.py` (le harnais à étendre :
   `IDENTICAL_KEYS:82`, `MOVING_KEYS`, `compare_identity:~218`)
6. `agent/chantier1_metriques.md` — le pattern de chantier (gates, preuves, re-baseline)
7. `docs/RESEARCH_LOG.md` — les runs de validation de ce chantier y sont inscrits avant lancement
   (décision 17)

## Contexte

C1 a réparé **la mesure** (métriques partagées, A/B d'identité prouvé, tag `v2.9.0-c1-metrics`).
C2 répare **ce qui est simulé** : l'audit a établi que le grid backtesté n'était pas le grid
spécifié, qu'une branche du DCA était structurellement inactive, et que les rejets d'ordres
n'étaient ni comptés ni visibles. Différence de nature avec C1 : ces corrections **changent la
stratégie simulée par conception** — il n'existe pas d'A/B d'identité globale. La validation
s'inverse : preuves ciblées de correction + un invariant de confinement + un avant/après documenté
sans jugement de valeur.

## Défauts à corriger

Localisations **vérifiées au commit `a07eb73`** (elles drifteront si le chore docs touche ces
fichiers — re-vérifier à l'étape 0) :

| # | Défaut | Localisation (a07eb73) |
|---|---|---|
| R1 | Replay grid : les bougies de trading (5 m) sont taguées `240` dans la séquence (`_build_grok_grid_replay_sequence`), donc ATR/EMA/ADX « 4 h » sont nourris de bougies 5 m. De plus le moteur n'appelle la logique de stratégie que sur les événements tradeables, et la stratégie ne décide que si l'intervalle reçu vaut 4 h : la correction du tag seule supprimerait toute décision grid | `scripts/backtest.py:1883-1910` (séquence), `:2300-2326` (dispatch tradeable-only) ; `src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py:352-354` (gate 4 h) |
| R2 | Préenregistrement lazy incomplet et **aveugle aux params effectifs** : `_LAZY_EMAS` + SuperTrend (10, 3.0) + Donchian (20, 10) hardcodés ; le DCA (EMA200 1d, RSI14 1d) absent ; la clé lazy est paramétrée (« for a given parameter set ») donc une variante P7 (ex. SuperTrend (8, 2.0)) n'est jamais préenregistrée ; warmup 4 h = 15 j ≈ 90 bougies < EMA125 (`count >= period` requis) | `scripts/backtest.py:1343-1358` (préenregistrement), `:640` (warmup) ; `src/krakenbot/indicators/multi_timeframe.py:586-594` (clé paramétrée) ; `src/krakenbot/indicators/ema.py:63` (readiness) ; `scripts/p7_grids.py:50-51,75` (variantes B4) |
| R3 | Rejets invisibles : `order_amount < min_order_usdc` → skip avec un warning log, aucun compteur (dont `bull_reduction=0.3` × 15 = 4.50 < 5) ; `btc_held < amount` → return nu ; aucune structure de rejets dans les résultats | `scripts/backtest.py:868` (min order), `:2038-2039` (inventaire insuffisant) |
| R4 | Double défaut d'appariement des ventes grid : (a) la stratégie ignore le `position_id` que le moteur lui transmet et matche par `abs(sell_level − prix) < 1` USD — avec des cibles quantizées à 0.1 pouvant être **strictement identiques**, d'où le « mauvais pop » (40 lots vendus deux fois sur SOL en B4) ; (b) le moteur mute `btc_held`/`usdc_balance` **avant** de chercher le lot et return silencieusement s'il n'existe pas → écriture comptable orpheline | stratégie : `grok_grid_atr_adaptive_v4.py:632` (matching par prix), `:587` (quantize 0.1) ; moteur : `scripts/backtest.py:2044-2056` (mutation avant matching), `:2095` (`position_id` transmis) |

## Objectif

Le replay simule la stratégie **telle que spécifiée** : indicateurs alimentés sur leurs vraies
unités de temps, décisions du grid sur les clôtures 4 h, exécutions et equity sur les bougies
5 m ; toutes les branches sont actives après warmup ; tous les rejets sont visibles ; une vente
ferme le lot qu'elle désigne et rien d'autre — avec la preuve que rien d'autre n'a bougé.

## Décisions figées

1. **R1 — trois rôles séparés, vraies séries, pas d'agrégation silencieuse.**
   - **Alimentation** : le replay grid charge les séries 4 h, 1 d **et 1 w** depuis la DB
     (`exchange='binance'`, end-stamped) — les trois sont consommées par la stratégie (ATR/EMA
     4 h, régime quotidien pour la géométrie de grille, régime hebdomadaire pour la pause
     strong_bear dès l'entrée de la logique) — et les entrelace avec leur vrai `interval`.
     L'agrégation 5 m → 4 h à la volée est interdite comme chemin par défaut.
   - **Décision** : la logique de stratégie (`_handle_ohlc`) est déclenchée sur les **clôtures
     4 h réelles**, plus sur les bougies tradeables.
   - **Exécution** : les fills au touch et l'enregistrement d'equity restent évalués sur les
     bougies 5 m (tradeables).
   - **Ordre à timestamp égal (tranché)** : à un timestamp T où coïncident une bougie 5 m et une
     ou plusieurs clôtures de contexte : (1) exécuter les ordres préexistants sur la bougie 5 m
     terminée, avec leurs callbacks ; (2) mettre à jour les contextes clôturés (1 w, puis 1 d,
     puis 4 h) ; (3) prendre la décision 4 h ; (4) les ordres issus de cette décision ne sont
     éligibles qu'à partir des bougies suivantes. Justification : un ordre créé avec
     l'information du close 4 h de T ne peut pas être rempli rétroactivement sur le high/low
     d'une période déjà écoulée.
   - **Divergence documentée, pas alignée** : le moteur signal conserve son fonctionnement
     historique — signal généré sur N, exécution sur **N+1** (`_resolve_fill:760` : open pour
     market, toucher du niveau pour limit) — et son ordre de traitement à timestamp égal
     (`interval_order:713`, gros TF avant la bougie tradeable) reste **inchangé** dans C2,
     couvert par l'invariant de référence SuperTrend A. La section replay de
     `skills/backtest.md` documente les deux conventions telles qu'elles sont, sans leur
     inventer de justification commune : grid = décision sur clôture 4 h, exécution au touch
     sur les 5 m suivantes ; signal = décision sur N, exécution sur N+1.
2. **Invariant maître de confinement, en mode strict.** Le rejeu **signal A SuperTrend** (même
   commande que la référence) doit être **bit-identique** pré/post C2. Le mode `compare-ab`
   actuel de `c1_equity_probe` ne suffit pas : il ignore par construction les `MOVING_KEYS`
   (Sharpe, Sortino, MaxDD, PF, Calmar…) autorisées à bouger en C1. C2 ajoute un **mode strict**
   qui vérifie : toutes les métriques C1 (identical + moving), les champs de trades ajoutés par
   C1 (dont `buy_fee_alloc`), soldes, equity, et une liste **explicite** des seules différences
   de métadonnées autorisées (commit, horodatage de capture). Un test démontre qu'une
   altération artificielle d'une métrique (ex. Sharpe) dans une copie de capture fait échouer ce
   mode. **La configuration de référence SuperTrend A** n'est visée par aucune correction — ses
   variantes non-défaut relèvent, elles, de R2. Pour cette référence, l'historique
   d'initialisation et l'ordre d'alimentation des indicateurs sont conservés **exactement** : le
   redimensionnement du warmup (R2) ne doit pas la modifier — un indicateur peut être « prêt »
   tout en portant une valeur différente si son historique d'amorçage change. Forme suggérée,
   à confirmer au plan : `warmup(config) = max(warmup existant, besoin des params effectifs)`,
   monotone, qui étend sans jamais réduire (pour la référence, besoin ≈ 50 bougies 4 h < 90
   existantes → flux inchangé). Le moindre écart sur la référence = fuite de périmètre = STOP.
3. **Côté « avant » = re-capture au tag C1, pas les captures historiques.** Les
   `results/c1_ab/*_new` identifient le commit intermédiaire `76bde08`, les JSON grid A ne sont
   pas dans le repo et aucune capture DCA n'existe : leur équivalence avec le tag n'est pas
   établie. **Étape 0 de l'exécution** (après validation du plan, avant le premier commit de
   code) : `git worktree add ~/wt-c1-ref v2.9.0-c1-metrics`, y capturer les cinq références —
   signal A SuperTrend, grid quick (binance + bybit), grid A bybit, et le run DCA de référence
   (config et période fixées au plan) — sha256 consignés dans le rapport C2. Ces captures sont le
   « avant » canonique ; les artefacts `c1_ab` historiques restent intouchés et ne servent plus
   de référence. Le « après » se capture avec le même harnais sur `feat/c2-replay`.
4. **Figé, intouchable** : module de métriques C1 (`backtest_metrics.py`), mécanique de fill au
   touch, modèle de fees et `pair_costs`, seuils des critères P6/P7, fichiers protégés
   (Router/RiskManager/ExecutionEngine).
5. **R4 — appariement par identifiant, gate humain dédié.**
   - **Dans le replay, une vente ferme le lot désigné par `position_id`.** Un identifiant fourni
     mais inconnu ne déclenche **aucun** fallback par prix : rejet explicite, loggé, compté. La
     tolérance de prix disparaît comme mécanisme d'appariement ; elle peut subsister au plus
     comme contrôle de cohérence (le lot désigné doit porter un `sell_level` cohérent avec le
     fill), à trancher au plan.
   - **Chemin sans identifiant : replay et live ne se traitent pas pareil.** Dans le **replay**,
     un appariement invalide est rejeté avant toute mutation comptable (le simulateur contrôle
     le fill). Dans le **callback live**, un fill déjà exécuté est un événement acquis : on peut
     refuser de l'attribuer arbitrairement à un lot, on ne peut pas le traiter comme un ordre
     jamais exécuté — une attribution ambiguë est explicitement signalée comme **nécessitant
     réconciliation** (log dédié + compteur), sans attribution arbitraire ni ordre de
     remplacement. Comportement par défaut proposé quand l'id est absent : appariement
     **unique** exigé (un seul lot candidat) sinon signalement — jamais de « premier lot
     proche ».
   - **Équivalence des identifiants à démontrer.** État constaté (a07eb73) : le circuit live
     propage `position_id` (router `:650`, engine `:304`, payload `:670`) mais le signal grid
     **n'émet pas** cette métadonnée (`_emit_grid_signal:542-551`) — en l'état, le chemin sans
     id est le chemin **nominal** du grid en live. Le plan démontre l'équivalence entre
     identifiants des lots grid et identifiants reçus au callback (analyse + test) ; toute
     limitation dont la levée exigerait une modification des fichiers protégés est **documentée
     hors périmètre** (elle alimente le test dette 13, prérequis B5). C2 ne s'ouvre pas
     implicitement sur une refonte du live.
   - Le diff du fichier de stratégie soumis au gate humain couvre **les deux chemins** (id
     présent / id absent) et leur comportement est écrit noir sur blanc dans la docstring.
   - **Validation avant mutation (moteur)** : `_process_grok_grid_sell_fill` valide le lot
     **avant** de toucher `btc_held`/`usdc_balance` ; aucune mutation comptable en cas
     d'appariement invalide. L'escalade éventuelle en erreur dure (vs skip compté) est tranchée
     au plan ; la validation-avant-mutation, elle, est obligatoire.
   - Le **diff du fichier de stratégie est soumis seul, en review humaine, avant d'écrire le
     reste du chantier qui en dépend** (règle d'or 6 : stratégie sensible).
6. **R3 — compteurs, pas de changement de comportement (hors validation R4 ci-dessus).**
   - Export par run/segment d'un dict `rejections` par cause. Clés minimales imposées :
     `below_min_order`, `insufficient_cash`, `insufficient_inventory`, `unmatched_sell_fills`,
     `unmatched_position_id` ; extension au plan.
   - **Unité de comptage figée** : par **(ordre distinct, cause)** — un ordre sous le plancher
     retesté à chaque bougie 5 m compte **une** fois. Un compteur d'événements brut séparé peut
     s'y ajouter pour le debug, clairement nommé (`*_events`).
   - `unmatched_sell_fills` et `unmatched_position_id` doivent valoir 0 sur les re-runs
     post-R4.
7. **Provenance** : les résultats post-C2 sont **non mélangeables** avec les post-C1 — même
   pattern de garde que C1 (clé de version/signature, reprise refusée, fichiers B4 et C1
   inécrasables). Mécanisme exact au plan.
8. **Dette 17 créée, pas corrigée** : le cost basis au dernier prix d'entrée pour les positions
   multi-achats (annexe 1 du rapport C1, `backtest.py:836/864` au tag v2.8.0) est un défaut
   **comptable**, pas de replay — hors périmètre, documenté en dette 17 dans PROJECT_CONTEXT
   avec renvoi. Idem pour le décalage d'un jour des benchmarks (C3) et toute question
   d'exécution (touch, stops intrabar).
9. **Re-baseline gold** : discipline identique à l'étape 7 de C1 — tableau avant/après, bloc
   d'historique, hashes proposés à la review humaine, jamais recalés silencieusement. La cause
   attendue est « la stratégie spécifiée est désormais simulée », pas « les chiffres sont
   meilleurs ».
10. **Porte pré-merge inchangée** : suite complète + `-m slow` verts avant tout merge.

## Preuves exigées (le cœur de la validation)

1. **Harnais indicateurs et temporalité (R1)** :
   - Sur un échantillon de points de décision du replay grid, la comparaison indépendante couvre
     **toutes les entrées réellement consommées par la décision** (`grok_grid_atr_adaptive_v4.py`
     `:363` et suivants) : ATR 4 h (espacement), EMA/**régime 1 d** (géométrie de grille,
     pauses), **régime 1 w** (pause strong_bear) — chacune recalculée indépendamment depuis les
     séries clôturées chargées de la DB, avec **uniquement les bougies clôturées disponibles à
     ce point de décision** (aucune bougie de contexte en cours). Un harnais limité aux
     indicateurs 4 h passerait avec un contexte quotidien ou hebdomadaire incorrect. Tolérance
     Decimal/epsilon documentée. Test automatisé, pas une vérification manuelle.
   - Tests d'ordre temporel : un ordre créé par la décision 4 h de T **ne remplit pas** sur la
     bougie 5 m se terminant à T (pas de fill rétroactif) ; un ordre préexistant touché par
     cette bougie **remplit avant** son éventuelle annulation par le recalc de T.
2. **Warmup et complétude lazy pilotés par la config testée (R2)** :
   - Inventaire exhaustif (grep + exécution) des indicateurs lazy de **chacune des 8
     stratégies**, **aux paramètres effectifs** (mécanisme `effective_params` de la dette 13
     branché en amont du warmup — plus de constantes hardcodées).
   - Formulation de l'exigence : **tous les indicateurs requis par la configuration testée sont
     préenregistrés et prêts après un historique suffisant** ; les historiques insuffisants ou
     données manquantes sont **explicitement signalés** dans les résultats, sans utiliser de
     données futures. Le warmup est dimensionné en **bougies requises** (max des périodes des
     params effectifs + marge), pas en jours calendaires — les trous documentés (BTC/ETH 164 j,
     SOL 455 j) rendent l'équivalence jours/bougies fausse par endroits.
   - Test paramétré sur les 8 stratégies, incluant **au moins une variante non-défaut** par
     indicateur paramétré (ex. SuperTrend (8, 2.0), EMA 125) : readiness prouvée après warmup,
     valeur == référence.
   - Frontières : aucun ordre pendant le warmup ; aucune bougie comptée deux fois à `start`.
   - EMA200 1d DCA : prête post-warmup, valeur == référence (warmup 1 d ≥ 200 **bougies**).
3. **Compteurs (R3)** : tests synthétiques par cause — dont le cas exact `bull_reduction`
   4.50 < 5 qui incrémente `below_min_order` une seule fois pour un même ordre retesté sur
   plusieurs bougies — et présence du dict `rejections` dans les résultats.
4. **Appariement (R4)** — après chaque vente du replay, assertions :
   - le lot **désigné** est retiré, tous les autres préservés ;
   - quantité vendue == quantité du lot ;
   - cost basis du P&L == celui du lot désigné ;
   - aucune vente cumulée supérieure à la quantité achetée (pas de survente) ;
   - **aucune mutation comptable** (soldes, inventaire, trades) en cas d'appariement invalide.
   Reproduction synthétique du double-pop (séquence type SOL : ancien matching par prix →
   2 ventes du même lot ; nouveau → 1 vente, la seconde rejetée et comptée) ; puis re-run d'une
   config grid × SOL flaggée de B4 → `inventory_divergence == 0`, `unmatched_sell_fills == 0`,
   `unmatched_position_id == 0`, `net_pnl_lot_basis` cohérent avec le cash.
5. **Invariant maître** : compare-ab **mode strict** signal A SuperTrend pré/post C2 → identité
   stricte intégrale (métriques identical + moving, trades avec `buy_fee_alloc`, soldes,
   equity) ; + le test négatif du mode strict (métrique altérée → violation détectée).
6. **Avant/après documenté, sans verdict** : grid quick (binance + bybit), grid A bybit, et le
   run DCA de référence — tableau des métriques C1 avant/après, chaque écart attribué à R1-R4,
   **aucun langage de validation économique** (le verdict appartient au rejeu diagnostic, phase
   suivante). Pour le DCA : la preuve de branche est le **test synthétique** (toutes conditions
   forcées — RSI < seuil, prix < EMA200, tick hebdomadaire disponible — multiplicateur ×2.5
   vérifié) ; sur le rejeu historique on exporte les **compteurs descriptifs** (conditions
   évaluées, signaux, rejets, achats exécutés) **sans exiger une activation positive** — un
   résultat de marché n'est pas une preuve de code. Le rapport consigne aussi le **constat
   rétroactif** : en B4, P7 variait `st_atr_period` [7-20] × `st_multiplier` [2.0-4.0] et
   `donchian_upper_period` [10-30] alors que le préenregistrement hardcodait (10, 3.0) et
   (20, 10) — 19/20 configs SuperTrend et 3/4 Donchian ont créé leurs indicateurs en cours de
   run (fenêtres partiellement muettes). Constat de portée pour l'invalidation B4, aucune
   correction rétroactive.
7. **Suite** : `pytest -q` complet + `-m slow` verts, `ruff check .` + `ruff format --check .`,
   `mypy src/` ≤ baseline constatée à l'étape 0 du chantier.

## À trancher au plan (liste fermée)

Mécanique exacte du dispatch décision/exécution dans le moteur (implémentation de la décision
1) ; faisabilité détaillée de l'appariement par id côté stratégie, comportement id-absent et
mécanisme de signalement « nécessite réconciliation » du chemin live (propositions par défaut
en décision 5, à confirmer ou amender) ; démonstration d'équivalence des identifiants lots
grid ↔ callback (décision 5) ; sort du contrôle de cohérence prix résiduel (décision 5) ;
escalade erreur dure vs skip compté pour la branche sell-no-match du replay (la
validation-avant-mutation est déjà figée) ; clés additionnelles du dict `rejections` ;
mécanisme de provenance (décision 7) ; implémentation du warmup en bougies requises et forme
exacte de la règle préservant la référence (`max(existant, besoin)` suggéré, décision 2) ;
config et période du run DCA de référence (contrainte : une période contenant 2022 est
souhaitable, sans exigence d'activation) ; plan de tests impactés (T10, grid metrics,
backward-compat) et sha256 des captures.

## Interdits

- Aucun changement : module métriques, fill/exécution, fees, critères, benchmarks, WF, fichiers
  protégés (hors le fichier de stratégie R4, sous gate humain dédié).
- Pas de re-run de campagne, pas d'écriture dans les JSON B4/C1 existants (les re-captures au
  tag sont de **nouveaux** fichiers), pas de langage de validation économique dans les rapports.
- `docs/RESEARCH_LOG.md` : entrée écrite **avant** les runs de validation (captures de l'étape 0
  incluses).

## Critère de fin (done)

- [ ] Étape 0 : références re-capturées au tag `v2.9.0-c1-metrics` (worktree), sha256 consignés ;
      baseline mypy constatée
- [ ] Preuves 1-5 vertes (harnais indicateurs + temporalité, lazy 8/8 aux params effectifs,
      compteurs, appariement R4 avec ses 5 assertions, invariant SuperTrend en mode strict +
      test négatif)
- [ ] Avant/après documenté (preuve 6) dans `results/C2_replay_report.md`, attribution R1-R4,
      constat rétroactif préenregistrement × grilles P7 consigné
- [ ] Gate humain R4 passé (diff stratégie reviewé seul, chemins id présent/absent couverts,
      sémantique replay-rejet vs live-réconciliation explicite) ; équivalence des identifiants
      lots ↔ callback démontrée, ou limitation documentée hors périmètre (→ test dette 13) ;
      gold hashes re-baselinés sur tableau approuvé
- [ ] Provenance active : mélange post-C1/post-C2 refusé, démontré par test
- [ ] Suite complète + slow verts, ruff, mypy ≤ baseline
- [ ] Docs : `skills/backtest.md` (section replay : trois rôles, ordre à timestamp égal et
      divergence signal/grid, warmup en bougies, rejections, provenance), PROJECT_CONTEXT
      (dette 14 résolue, dette 16 résolue, dette 17 créée), INDEX (artefacts C2), RESEARCH_LOG
      (entrée validation)

## Commits attendus (indicatif — l'agent propose au plan)

- `chore(c2): recapture reference runs at v2.9.0-c1-metrics (worktree, sha256)` *(étape 0,
  artefacts seulement)*
- `feat(audit): strict identity mode for c1_equity_probe + negative test`
- `fix(strategy): grid sell matching by position_id, explicit no-id path (dette 14)` *(gate
  humain dédié)*
- `fix(backtest): validate lot before balance mutation in grid sell fill (R4)`
- `feat(backtest): grid replay on true 4h/1d/1w series, decision/execution split,
  deterministic same-timestamp order (R1)`
- `fix(backtest): effective-params-driven lazy preregistration + candle-based warmup (R2)`
- `feat(backtest): rejection counters per (order, cause) incl. unmatched sells (R3)`
- `feat(backtest): post-C2 provenance guard`
- `test(replay): indicator harness, temporal ordering, lazy 8/8, double-pop repro,
  supertrend strict identity`
- `test(strategies): re-baseline grid gold hashes (C2 table approved)`
- `docs(replay): C2 report + skills/backtest replay section + debts 14/16/17`
