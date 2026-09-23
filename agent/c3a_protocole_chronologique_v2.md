# C3a — Protocole de validation chronologique (lot 1 de C3) — v2

> Brief agent, **version 2**. Changements v1 → v2 : (i) la continuité n'exige **plus** a priori un
> nouveau mode moteur — avec une configuration figée il n'y a aucun portefeuille à transmettre, et
> le segment `all` du rejeu prouve qu'un run continu existe déjà ; (ii) « puissance déclarée avant »
> est remplacé par un **plan d'évaluation de la précision**, l'ancienne version réécrivait
> l'historique du rejeu (les ≈ 6 pp/an étaient des seuils critiques **observés après**, pas une
> puissance annoncée) ; (iii) la formulation sur B5 est nuancée (ni unique dispositif prospectif,
> ni preuve indépendante automatique) ; (iv) le « done » distingue nouvelle voie C3 et ancienne
> phase 2 P7 conservée, et n'oblige plus à accepter les artefacts existants ; (v) ajout d'une
> **règle d'ancrage** fixée avant application.
>
> Mode : **plan mode, deux gates**. Branche : `feat/c3a-protocole` depuis le `dev` courant
> (`57051cc` au moment d'écrire — **partir du `dev` courant et consigner son SHA**, il bouge).
> Assert `git branch --show-current == feat/c3a-protocole` avant chaque commit ; un seul acteur
> git ; une découverte annexe se **signale**, ne se traite pas.
>
> **C3 est découpé en deux lots nommés dès maintenant. C3a terminé ≠ C3 terminé ; C3 terminé ≠
> stratégie validée.**
>
> | Lot | Livrable | Limite |
> |---|---|---|
> | **C3a — ce chantier** | Protocole complet, contrat de continuité, outillage de sélection n'utilisant que le passé, tests de chronologie | Aucune validation économique, aucune sélection pour le paper |
> | **C3b — ensuite** | Intégration et validation de l'exécution continue, benchmarks synchronisés, tests d'intégration | Aucune campagne de recherche implicite |
>
> C3a **ne modifie aucun moteur**. Si C3b devait en modifier un, ce serait sous gate humain dédié
> (`backtest.py` est un fichier > 1 000 lignes) et sous invariant de confinement : le chemin
> existant reste **bit-identique**, prouvé par `compare-ab --strict` (harnais C2).

## Les deux gates

- **Gate 1 — plan.** L'agent propose le plan et tranche les points ouverts. Arrêt strict jusqu'à
  validation humaine.
- **Gate 2 — le protocole, revu pour lui-même.** `docs/protocole_c3.md` est soumis **avant** que
  la moindre ligne d'outillage soit écrite, et **l'agent s'arrête jusqu'au GO humain**. C'est le
  livrable qui gouvernera toute sélection future du projet : il se review comme un texte, pas à
  travers son code.

## À lire avant toute ligne

1. `CLAUDE.md`, `PROJECT_CONTEXT.md` (dettes 13 à 17, **note WF** en fin de § 9), `docs/CODE_MAP.md`
2. `docs/CONTRAINTES_POST_B4.md` — **§ 4 benchmark, § 7 protocole, § 8 basse rotation** (source de
   l'exigence « equity continue, sélection chronologique »)
3. `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` — origine du défaut de sélection
4. `results/C1_metrics_report.md`, `results/C2_replay_report.md` — l'instrument réparé
5. `docs/rejeu_grid_prespec.md` + `results/rejeu_grid_report.md` + `scripts/audit/rejeu_*.py` —
   **antériorité obligatoire** : le précédent complet d'un protocole pré-spécifié qui a tenu
6. `skills/backtest.md` (§ Métriques, § Replay, § validation), `docs/RESEARCH_LOG.md`

## Contexte — les deux défauts, qui ne sont pas de même nature

L'audit du 16/09 a rassemblé sous « walk-forward non chronologique » deux choses distinctes :

- **(a) Fuite de sélection.** La sélection top-5 de P7 phase 2 utilise le Sharpe du test global,
  sur une période qui chevauche les fenêtres OOS : le choix est informé par ce qu'il est censé
  prédire. Réparable dans la **logique de sélection**, sans toucher aux moteurs → **C3a**.
- **(b) Réinitialisation par segment.** Le runner crée un moteur neuf par segment
  (`run_p7_grid_search.py:~726`) : `train` et `test` ne transmettent rien et le grid paie une
  liquidation terminale à chaque fin de segment. Des simulations trimestrielles réinitialisées ne
  valident pas un comportement destiné à porter ses positions continûment.

**Ce que (b) n'implique pas, sous configuration figée.** Le même runner exécute déjà le segment
`all` en un seul `engine.run(pair, train_start, test_end)` : un moteur, un run, trois ans continus
— les 96 courbes `all` du rejeu en sont la preuve. Avec une configuration figée il n'y a aucun
changement de configuration à comptabiliser, donc aucun portefeuille à transmettre. **Au gate 1,
vérifier si une exécution unique des moteurs existants satisfait le contrat de continuité.** C3b
en assure l'intégration et la validation ; une modification moteur n'est requise que pour des
**écarts démontrés**. Restent à vérifier : warmup à l'ancrage, première exécution à l'ancrage,
liquidation finale.

C1 a réparé la mesure, C2 ce qui est simulé. C3 répare **comment on décide à partir de ce qui est
mesuré**. Tant qu'il n'existe pas, aucune sélection n'est possible et B5 reste fermé quoi qu'on
trouve.

## Objectif de C3a

Produire le **protocole de validation v2** : un document qui, appliqué mécaniquement, dit comment
une configuration est choisie sans jamais regarder l'avenir, comment son résultat est évalué,
contre quoi, avec quelle incertitude, et dans quels cas le verdict est « inconclusif ». Plus
l'outillage qui exécute la partie sélection et les tests qui prouvent sa chronologie.

## Décisions déjà figées (ne pas rouvrir au plan)

1. **Objet sélectionné : une configuration figée, choisie une fois, à une date d'ancrage.** La
   sélection n'utilise que les données antérieures à cette date ; la configuration retenue est
   ensuite évaluée sur la période postérieure, en equity continue.
   **Une procédure qui re-sélectionne périodiquement ses paramètres est hors périmètre**, et
   nommée comme telle dans le protocole : elle valide un objet différent (une règle, pas une
   configuration) et ne correspond pas à ce qui est déployé — en production une configuration est
   posée dans `strategies.yaml`, surveillée, et tuée à la main (décision 13). Si elle est voulue un
   jour, c'est une extension nommée avec sa propre charge de validation, pas une dérive. Le
   mécanisme de changement de configuration est donc **hors périmètre de C3a comme de C3b**.
2. **Aucune modification de moteur en C3a.** Diff de contrôle vide sur `src/`,
   `scripts/backtest.py`, les runners et `p7_grids.py` — hors une liste fermée et nommée de
   nouveaux fichiers d'audit et de tests.
3. **Le diagnostic grid gelé et ses artefacts sont préservés** : ni réécrits, ni réinterprétés, ni
   rouverts. Le verdict `inconclusif` du rejeu n'est pas un sujet de C3.
4. **Réutilisation des scripts du rejeu** : réutiliser les composants compatibles **après examen de
   leurs hypothèses**, et préserver le diagnostic gelé et ses artefacts. Ces scripts portent des
   règles propres aux 48 configurations, au segment `all` et à un benchmark apparié après coup —
   ce n'est pas déjà un protocole de sélection chronologique générique. Ni généralisation imposée,
   ni réécriture par réflexe.

## Les cinq décisions que le protocole doit trancher

### A. Ce qui est sélectionné, et quand

La date d'ancrage, les données accessibles à cette date, l'univers de configurations candidates,
la règle de classement, le traitement des égalités, et le cas **où aucune configuration n'est
admissible** (qui doit exister et mener à « inconclusif », pas à un repêchage).

**Test essentiel, non négociable** : entre un préfixe de données seul et ce **même préfixe
accompagné de futurs différents**, le protocole doit produire des résultats identiques sur
**l'admissibilité, les scores, le classement et le choix (ou l'abstention)** — pas seulement sur
le nom du gagnant. C'est ce qui distingue un protocole chronologique d'un protocole qui se croit
chronologique.

### A bis. La règle d'ancrage, fixée avant application

La date d'ancrage est elle-même un choix susceptible d'être shoppé : essayer plusieurs ancrages et
garder le plus flatteur est le motif que ce projet répète. Le protocole fixe la règle avant toute
application — fraction déclarée des données disponibles, ou date calendaire posée à l'avance — et
écrit qu'explorer plusieurs ancrages constitue une **multiplicité à déclarer**, pas une analyse de
sensibilité gratuite.

### B. Le contrat de continuité du portefeuille

**Tranché en C3a**, son implémentation ou sa simple vérification relevant de C3b :

- les positions fictives des simulations de sélection **ne passent jamais** dans le portefeuille
  évalué (le portefeuille évalué démarre plat à la date d'ancrage) ;
- les positions déjà détenues **dans** le portefeuille évalué ne disparaissent à aucune frontière
  interne (trimestre, fenêtre de reporting) : les statistiques périodiques se calculent **sur** la
  courbe continue, elles ne la découpent pas en runs ;
- toute liquidation prévue par le contrat (notamment la liquidation terminale) **paie ses coûts**
  — fees, spread, slippage par paire, comme le reste du modèle ;
- warmup et première exécution à l'ancrage explicitement spécifiés.

### C. La synchronisation stratégie ↔ benchmark

Bornes temporelles, instant de disponibilité des bougies, première exécution, warmup, frais et
valorisation finale, explicites des deux côtés. La **dette 15(c)** (`compute_benchmarks.py` charge
en `< P6_END` là où les moteurs chargent `<= end`) peut rester ouverte en C3a, mais son traitement
doit être **défini**, et un benchmark encore désaligné est **interdit d'usage décisionnel** — il
reste descriptif, comme dans le rejeu.

### D. Quelles données prouvent quoi

Les artefacts existants permettent de tester l'**orchestration**. Ils ne permettent pas de
reconstituer une validation chronologique en redécoupant leurs courbes. Prévoir des **scénarios
synthétiques** et, si nécessaire, des **rejeux techniques courts** — jamais une campagne de
recherche.

Le protocole distingue explicitement trois natures de données :

- **historique déjà exploré** (Binance 2021-2026, balayé par P6, P7, B4 et le rejeu) — utilisable
  pour développer et pour une évaluation rétrospective, jamais comme hors-échantillon ;
- **évaluation chronologique rétrospective** — ce que C3 produit : honnête sur la fuite de
  sélection, mais menée sur des données déjà vues ;
- **échantillon réellement jamais consulté** — des données futures, gelées avant observation.

Conséquence à écrire dans le protocole : **les résultats historiques restent rétrospectifs au
niveau du processus de recherche ; réparer l'instrument ne rend pas les données vierges.** Une
confirmation prospective exige une configuration, des critères et des règles de suivi **fixés
avant observation des résultats**. B5 peut porter cette évaluation, tout en testant le
fonctionnement opérationnel — sans être ni l'unique dispositif prospectif possible (une évaluation
différée sur des données futures gelées joue le même rôle), ni une preuve indépendante
automatique : modifier les paramètres ou ne conserver que les gagnants pendant le paper en
détruirait la portée.

Préciser également que **quatre semaines de paper ne constituent pas une preuve économique**, en
particulier à basse rotation. Distinguer les **conditions d'admission** au paper des **preuves
exigées pour conclure** ensuite — sans modifier implicitement les règles B5, qui restent celles du
`ROADMAP.md`.

## Doctrine des critères (à inscrire dans le protocole)

Chaque critère précise **ce qu'il mesure, sa justification, ses dépendances mécaniques aux
paramètres, et les arbitrages qu'il opère**. Une corrélation avec un paramètre balayé ne constitue
pas à elle seule un motif d'exclusion — un paramètre peut légitimement modifier l'économie, et un
critère de risque peut légitimement écarter une configuration au rendement supérieur. Toute
calibration n'utilise que les données autorisées avant l'évaluation.

**Hypothèse à tester ou à rejeter au gate 1** (pas à inscrire d'office) : le défaut de G3 dans le
rejeu était d'être un **proxy** d'une quantité non mesurée (les frictions non modélisées) sans lien
démontré avec sa cible. Règle candidate : un critère présenté comme proxy doit dire ce qu'il proxie
et pourquoi il le suit. À valider sur les cas du projet, ou à jeter — trois formulations
antérieures de cette leçon se sont révélées fausses.

## Plan d'évaluation de la précision

Avant application, le protocole fixe **l'effet économiquement pertinent, la procédure
d'incertitude et les règles de conclusion**. Toute estimation prévisionnelle de puissance précise
ses hypothèses et ses données de calibration, antérieures à l'évaluation. **Si aucune estimation
défendable n'est disponible, le déclarer — sans inventer de seuil de détection.** L'issue
« inconclusif » est prévue explicitement et n'est pas un échec du protocole.

Rappel de discipline, sans réécrire l'historique : dans le rejeu, les ≈ 6 pp/an étaient les
**seuils critiques observés** de la procédure, mesurés après la campagne ; la pré-spécification
interdisait explicitement de les extrapoler depuis la calibration. Ce précédent enseigne que les
règles de conclusion doivent être écrites avant — il ne fournit pas une puissance annoncée.

## Interdits

- Aucune campagne de backtest de recherche, aucune sélection de stratégie, aucune réouverture du
  verdict grid, aucune modification de moteur, de métriques, de fees ou de critères P6/P7.
- Aucun langage de validation économique dans les livrables.
- `docs/RESEARCH_LOG.md` : entrée écrite **avant** tout rejeu technique, si le plan en prévoit.

## Livrables

- `docs/protocole_c3.md` — le protocole v2, soumis au gate 2 **avant** l'outillage : décisions
  A/A bis/B/C/D, contrat de continuité, doctrine des critères, natures de données, plan
  d'évaluation de la précision, liste des cas « inconclusif », et ce qui est explicitement hors
  périmètre (re-sélection périodique, changement de configuration).
- `scripts/audit/c3_*.py` — outillage de sélection chronologique + tests, dans la convention maison
  (pur, read-only, JSON in/out, codes 0/1/2).
- `tests/test_scripts/test_c3_*.py` — liste fermée et nommée, exclue du diff de contrôle.
- Mises à jour : `skills/backtest.md` (section protocole), `results/INDEX.md`, ligne C3 du
  `ROADMAP.md` (C3a fait, C3b ouvert), `PROJECT_CONTEXT.md` — **note WF : ne pas la déclarer
  résolue.** Les runners restent inchangés, donc la fuite de la phase 2 P7 est toujours présente.
  Formulation : « nouvelle voie C3 chronologique ; ancienne phase 2 P7 conservée pour reproduction,
  impropre à une nouvelle validation chronologique ».
- **Brief C3b** proposé en fin de chantier — proposé, pas exécuté.

## Critère de fin (done)

- [ ] Gate 1 passé ; **gate 2 passé, avec arrêt effectif avant tout outillage**
- [ ] Décisions A, A bis, B, C, D tranchées et écrites dans `docs/protocole_c3.md`
- [ ] Test de chronologie vert au sens fort : préfixe seul vs préfixe + futurs différents →
      admissibilité, scores, classement et choix/abstention identiques
- [ ] **Parcours complet sur fixtures synthétiques**, puis validation **ou rejet motivé** des
      artefacts réels selon leurs périodes et leur provenance. Aucun classement forcé à partir de
      scores globaux : si les artefacts du rejeu ne conviennent pas à une sélection chronologique,
      le refus documenté est le bon résultat.
- [ ] Scénarios synthétiques couvrant : aucune configuration admissible, égalités au classement,
      frontière interne, données manquantes à l'ancrage
- [ ] Plan d'évaluation de la précision écrit dans le protocole, avant toute application
- [ ] Contrat de continuité tranché, et vérification faite au gate 1 de ce qu'une exécution unique
      des moteurs existants en satisfait ou non les clauses
- [ ] Diff de contrôle vide hors la liste fermée ; `pytest -q` et `ruff` verts ; `mypy src/` ≤ baseline
- [ ] Brief C3b proposé
- [ ] Diagnostic grid gelé et ses artefacts intacts

## Commits attendus (indicatif)

- `docs(c3): protocole de validation chronologique v2 (gate 2)`
- `feat(audit): outillage de sélection chronologique + tests`
- `test(c3): chronologie forte, scénarios synthétiques, cas inconclusif`
- `docs(c3): skills/backtest section protocole + index/roadmap + note WF`
- `docs(c3): brief C3b (exécution continue) — proposé, non exécuté`
