# Note de passation — KrakenBot, C3a en cours (rédigée le 2026-09-20, actualisée le 2026-09-21)

> **Note historique — état au 21/09/2026, conservée telle quelle.** C3a a été **livrée et validée le 22/09**
> (branche `feat/c3a-protocole`, tip `acaeaf6`, 806 tests C3, revues Fin Astra / Claude) : les « cinq modules
> restants », le test de chronologie forte et son contrôle négatif, la chaîne § L.2 et le refus de l'artefact du
> rejeu par `c3_entry` (`D_WARMUP_PREFIX`, 96/96, `results/c3a_entry_validation/`) **existent**. Les passages qui les
> décrivent au futur (§ 1.1, § 1.3, § 2 « C3a (en cours) », § 3 « Reste en C3a », tip `e358df9` / 1931 tests /
> 122 C3, § 4 « sera refusé », § 8, § 9 brouillon d'addendum) sont **périmés** ; l'état courant est dans
> `agent/rapport_session_c3a_20260922.md`, `PROJECT_CONTEXT.md` et `skills/backtest.md` § « Validation C3 ». Les
> blocs `C3A-INTERIM` cités ont été remplacés à la clôture (`docs(c3a)`, 22/09). **Seule correction apportée au
> texte** : la baseline `mypy src/` (§ 3), 64 → **65** (`results/C2_replay_report.md` § 0). Consensus Astra
> acquis (revue Fin du 22/09).

> Usage : (1) coller en ouverture de la nouvelle conversation Claude du Project ; (2) la dernière
> section sert de base au brief de reprise du nouvel agent, **après** cadrage 4 questions.
> Tout ce qui suit est tiré de la conversation précédente et des rapports d'agents ; les SHA et
> chiffres sont ceux rapportés — à revérifier contre un zip frais du repo.

## 1. Avant d'ouvrir la nouvelle conversation (à faire par Bruno)

1. **Recharger les fichiers du Project depuis la tête de `feat/c3a-protocole`** (au minimum
   `371f59b`, qui épingle `e358df9` dans les blocs `C3A-INTERIM` ; `e358df9` seul ne les porte pas)
   — pas depuis `dev`, ni depuis `~/wt-human`, détachée sur `57051cc` = `dev`. **Exporter vers un dossier
   dédié hors de tout checkout**, pour ne jamais écraser un fichier suivi : `mkdir -p ~/c3a_upload &&
   git show feat/c3a-protocole:CLAUDE.md > ~/c3a_upload/CLAUDE.md`, etc. Les versions actuelles du Project datent du 16/09 et
   croient que C2 est le prochain chantier. Recharger `CLAUDE.md`, `PROJECT_CONTEXT.md`,
   `ROADMAP.md` (ils portent l'état courant dans un bloc `C3A-INTERIM`), et **ajouter
   `docs/protocole_c3.md`** et `agent/c3a_protocole_chronologique_v2.md`.
   `skills/backtest.md`, `results/INDEX.md` et `docs/CODE_MAP.md` sont **volontairement en retard**
   (mis à jour au commit de clôture de C3a, parce qu'ils décrivent un outillage et des artefacts qui
   n'existent pas encore) : l'état courant est porté par les blocs `C3A-INTERIM` et le protocole.
2. **Uploader un zip frais du repo** à la tête de `feat/c3a-protocole` (nom `krakenbot-src-<git describe>.zip`, commentaire = SHA), pour pouvoir revérifier le code.
3. **État vérifié au `e358df9`. Corrections du noyau revues par Astra ; GO pour reprendre les cinq
   modules restants. C3a reste incomplet, aucune sélection autorisée.** Ce GO valide le point de
   reprise, pas la chaîne C3a : sa chronologie et sa conformité au manifeste restent à vérifier avec
   les modules suivants. Le contrôle AST est une protection supplémentaire, pas une preuve de ces
   propriétés.

## 2. État du projet en une page

- Bot spot multi-paires (BTC/ETH/SOL vs USDC) sur **Bybit EU** ; collector en production, trader
  masqué. **Rien à trader** : aucune stratégie sélectionnée, B5 (paper) → P10 suspendus.
- **Instrument réparé en deux chantiers, tous deux mergés :**
  - **C1 métriques** — tag `v2.9.0-c1-metrics` (module partagé `backtest_metrics`, `metrics_version` 2).
  - **C2 fidélité du replay** — tag `v2.10.0-c2-replay` (@ `9897803`) : grid sur vraies séries
    4h/1d/1w, séparation décision/exécution, appariement des ventes par `position_id`, warmup en
    bougies, compteurs de rejets, `replay_version` 2. Invariant SuperTrend A bit-identique prouvé.
- **Rejeu diagnostic grid** — mergé dans `dev` @ `dda7b8d`, sans tag. Verdict mécanique :
  `REJEU_GRID_20260919 | famille=inconclusif | raison=F_CANNOT_SEPARATE | BTC/USDC=inconclusif |
  SOL/USDC=descriptif | prespec=20079aff60a55152 | campagne=08d981e493402f37`.
  BTC seule paire votante : 48 éligibles, 16 passent G1∧G2∧G4, aucune ne tient les six bornes
  simultanées ; meilleur Δ̂ +1.92 pp/an sous son SE mono-config (2.56–2.79). SOL inadmissible
  (~27 mois de données dans la fenêtre). ETH jamais balayé pour le grid (statut inconnu).
  Contrefactuel établi : G3 (`net_pnl ≥ 10 × frais`) en gate aurait produit `dépriorisation`
  (8 configs passant G3, toutes à `atr_multiplier` 3.0, toutes en échec G2, intersection vide).
  Famille grid : **ni validée ni dépriorisée**.
- **Migration Alembic `c1ae7a1c0001`** : appliquée sur le serveur (docs corrigées).
- **Phase courante : C3**, découpé en deux lots nommés. **C3a terminé ≠ C3 terminé ; C3 terminé ≠
  stratégie validée.**
  - **C3a** (en cours) — protocole de validation chronologique + outillage de sélection + tests.
  - **C3b** (ensuite) — intégration/validation de l'exécution continue, benchmarks synchronisés,
    liquidation terminale du moteur signal, preuve de départ à plat. Aucune modification moteur
    sans écart démontré ; si modification, gate humain + invariant `compare-ab --strict`.

## 3. C3a — où on en est

Branche `feat/c3a-protocole`, créée depuis `dev` @ `57051cc`. Historique :

| Commit | Contenu |
|---|---|
| `88b88e1` | Protocole v1 soumis au gate 2 |
| `8e01ee2`, `0b50494` | Révisions (contradictions, benchmark, procédure numérique, index des symboles) |
| `d931293` | Deux dernières corrections — **protocole GELÉ** (`docs/protocole_c3.md`) |
| `f63c45e` | Premier outillage (3 fichiers de la liste fermée) + 3 fixtures de conséquences |
| `075f740` | Correctifs du noyau `c3_verdict` + accesseur strict dans `c3_common` — **la revue Astra du 21/09 a identifié des défauts restants** (§ 8) |
| `a9be714` | Mise à jour documentaire intermédiaire : blocs `C3A-INTERIM` dans `CLAUDE.md` (routage vers le protocole), `PROJECT_CONTEXT.md` (état C3a, dette 19, note WF non résolue), `ROADMAP.md` (C3a en cours, C3b ouvert) |
| `e358df9` | **Noyau corrigé, revu par Astra, GO** : aucune publication sur violation (artefact diagnostic invalide, verdict/raison/chaîne à `null`) ; accesseur strict imposé (`discarded` et `B` obligatoires, `B_effectif` recalculé, `require_bool`, domaine r > −1) ; codes de sortie alignés sur I.1 avec test paramétré (lignes 1-2 et 7-15 ; 3-6 = portée `c3_select`, à couvrir) ; scan de source sur l'AST contre `bool(` et `.get(` hors `OPTIONAL_FIELDS` ; blocs `C3A-INTERIM` actualisés |
| `371f59b` | Blocs `C3A-INTERIM` de `PROJECT_CONTEXT.md` et `ROADMAP.md` : le « commit de reprise » épinglé à `e358df9` |
| `5ee4b1f` + suivant | Cette note de passation (première version, puis actualisation au 21/09) |

État au `e358df9` : 1931 tests verts hors module de déterminisme (dont 122 C3), `mypy src/` = **65**
(baseline — corrigé le 22/09 : le « 64 » venait de `--ignore-missing-imports`, `results/C2_replay_report.md` § 0 ;
la 65e erreur est `ml/features/feature_store.py:32`, stubs pandas), ruff vert, diff de contrôle vide, protocole
intact depuis le gel (`d931293`).
Note technique acquise : `math.log1p(-1.0)` lève une exception en Python (pas `-inf`) — la garde de
domaine est nécessaire, pas seulement prudente.

**Reste en C3a** : `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select`, `c3_continuity` et leurs
tests — dont le **test de chronologie forte avec son contrôle négatif** — puis docs de clôture
(section protocole dans `skills/backtest.md`, INDEX, ROADMAP, PROJECT_CONTEXT) et **brief C3b
proposé, non exécuté**. Porte pré-merge **§ L.5** : les 24 tests de déterminisme sur le serveur,
ou diff de contrôle documenté vide sur tous les chemins qu'ils exercent.

## 4. Décisions figées de C3 (ne pas rouvrir)

- **Objet sélectionné** : une configuration figée, choisie une fois, à une date d'ancrage.
  Re-sélection périodique hors périmètre de C3a comme de C3b (extension nommée si voulue un jour).
- **Ancrage** : `début + 0.7 × (fin − début)`, fenêtre déclarée 2023-04-01 → 2026-04-01 ⇒
  **2025-05-07T04:48:00Z**, sans arrondi. Bornes issues du **manifeste gelé**, jamais de la
  dernière donnée. 0.7 hérité de P6/P7, divulgué comme antérieur à C3. Explorer plusieurs ancrages
  = multiplicité à déclarer ; répétition identique d'un manifeste = idempotente.
- **Benchmark** : on synchronise **la contrainte, pas l'événement** (mêmes données disponibles à T,
  même résolution, aucun fill à T ni avant). Le benchmark a sa propre convention d'achat après T ;
  la stratégie garde ses signaux et règles de remplissage. **Piège end-stamp** : à T = 04:48, la
  bougie 5 m estampillée 04:50 ouvre à 04:45 — instant du prix et estampille déclarés séparément,
  instant du prix strictement postérieur à T.
- **Deux comparateurs distincts** : B&H plein notionnel = référence descriptive et base de
  construction ; blend B&H/cash à λ apparié = comparateur décisionnel.
- **Préséance** : l'estimabilité (E1, E2) précède tout verdict économique ; tant qu'elle n'est pas
  satisfaite, ni `validé` ni `réfuté`.
- **Promotion en refus d'artefact** : bornée à D2 par convention déclarée (pas déduite d'une
  opposition données/candidats) ; D3/D4/D6 qui vident l'ensemble → abstention.
- **Filtrer avant classer** : D1–D6, puis P1–P3, puis le premier du classement parmi les survivants.
- **« Réfuté »** porte sur le triplet configuration / manifeste / fenêtre ; une clôture de famille
  est une décision de gestion de la recherche, annoncée comme telle.
- **Données** : l'historique Binance déjà exploré reste rétrospectif — réparer l'instrument ne rend
  pas les données vierges. B5 peut porter une évaluation prospective, sans être ni l'unique
  dispositif possible ni une preuve indépendante automatique ; quatre semaines de paper ne sont
  pas une preuve économique à basse rotation.
- **Artefact du rejeu** : **sera** refusé par `c3_entry` (pas encore écrit), motif
  `D_WARMUP_PREFIX`, sortie prévue sous `results/c3a_entry_validation/` avec hash source — « cet
  artefact ne satisfait pas les conditions d'entrée C3 », jamais un verdict sur la famille grid.

## 5. Dettes ouvertes à connaître

- **Dette 19 — moteur signal sans liquidation terminale** : `unrealized_pnl` n'est écrit que par le
  `GridBacktester` ; le signal valorise l'inventaire résiduel au dernier close sans coût et exporte
  0.0. Mesuré : 166/636 segments (phase 1 B4) et 116/560 (phase 2) rompent l'identité de fin à
  plat ; DCA BTC `all` : 101 achats, 0 vente, `net_pnl −0.9975` pour `+71.68 %` rapporté. Prérequis C3b.
- **Départ à plat non vérifiable** avec les artefacts actuels : le dump d'equity ne contient que des
  états postérieurs au traitement d'une bougie, aucun point à T. C3b doit produire une preuve
  explicite — ce n'est pas « un simple transport de champs ».
- **Dette 15(c)** : `compute_benchmarks.py` en `< P6_END` vs moteurs en `<= end` ; ses sorties sont
  interdites d'usage décisionnel. Traitée en C3b.
- **Dette 13** : params grok résolus par nom de classe dans les moteurs ; élargie à la réconciliation
  FIFO à P&L nul sans filtre de bot au redémarrage. Prérequis B5 (grid inéligible au paper).
- **Dette 17** : cost basis au dernier prix d'entrée pour les positions multi-achats.
- **Dette 10** : `ruff format` sur `scripts/p6_5_diagnose_*.py`, toujours ouverte.
- Mineurs : incohérence de principe `CLAUDE.md` tracké / `agent/AGENTS.md` ignoré ; formulation du
  § 4 des contraintes sur le Sharpe DCA (imprécise, traçable à D6 corrigé en C1).

## 6. Motifs de défauts récurrents — à surveiller à chaque revue

| Motif | Occurrences | Contre-mesure acquise |
|---|---|---|
| Contrôle de présence ou de type qui passe sur une donnée invalide | 5 (`collect_flags` sur `"error"`, `flag_segment` sur bloc absent, sous-blocs `null` du validateur rejeu, `c3_verdict` avant l'accesseur, puis **accesseur contourné** : `.get(clé, défaut)` sur `discarded`, `bool("false")` sur des statuts) | Accesseur strict unique dans `c3_common` **effectivement utilisé** — gardé par le test de scan de source (pas de `bool(…)` sur donnée externe, pas de `.get(clé, défaut)` sur champ obligatoire) ; contrôle du domaine en plus de la finitude (r > −1) ; tests clé absente **et** `null` |
| Règle énoncée à deux endroits, énoncés divergents | 4 paires au gate 2 de C3a | § 0.7 source unique ; index des symboles par `rg` ; un symbole sans site de référence est un **signal d'alerte à vérifier** (une règle peut s'appliquer par renvoi de section sans nommer le symbole) |
| La prose décrit une correction que l'artefact ne porte pas | ≥ 4 (journaux gitignorés, teardown vs setup, « one rule now governs », « énoncés remplacés supprimés ») | Revoir l'artefact, jamais le résumé |
| Généralisation qui dépasse le contre-exemple | G3 (5 formulations fausses), E2 « seulement si », indicateur de longueur, principe de promotion données/candidats, et **trois règles de la première version de cette note** (quota de tests adverses, « tout statut est recalculé », « symbole sans référence = porte inappliquée ») | Décrire ce qu'un contrôle **détecte** ; poser une convention comme convention |
| Faire confiance à un drapeau déclaré au lieu de recalculer | `c3_verdict` estimabilité | Recalculer ce qui est dérivable des preuves, recouper, désaccord = violation |
| Publier un résultat malgré une violation détectée | `c3_verdict` : verdict `validé` écrit et affiché avant le traitement des violations, violations sur stderr seulement | Une violation empêche la publication du verdict ; artefact diagnostic explicitement invalide, sans chaîne citable |
| Régression d'une correction acquise | filtrer/classer et portée du verdict négatif revenus du rejeu | Vérifier explicitement l'héritage des corrections antérieures |

Note de calibration : les corrections qui tiennent sont les concrètes (contradiction pointée,
contre-exemple, ligne de code). Les « principes » ajoutés par-dessus — y compris par Claude — ont
régulièrement introduit une généralisation non fondée.

## 7. Méthode de travail

- Chaque tâche agent : cadrage 4 questions (nouvel agent ou continuation, mode, scope, critère de fin).
- Plan mode avec gates ; arrêt dur aux gates ; un seul acteur git ; assert de branche avant commit.
- Revue croisée systématique par Astra (GPT) à chaque livraison ; Claude vérifie contre un zip du repo.
- Toute découverte annexe se signale, ne se traite pas. Une fixture qui révèle une incohérence du
  protocole gelé ⇒ arrêt et signalement, jamais de correction silencieuse du document.

## 8. Défauts du noyau identifiés par la revue Astra du 21/09 — **corrigés au `e358df9`, GO obtenu**

(Conservé comme historique : ce sont les classes de défauts que les cinq modules restants doivent
éviter dès l'écriture.)

1. **Publication malgré violation** : estimabilité déclarée fausse sur une fixture estimable →
   exit 1 mais `verdict=validé` écrit dans le JSON, violations sur stderr seulement
   (`c3_verdict.py` ~:366 : construction, écriture et affichage précèdent le traitement des
   violations). Correction : une violation empêche la publication du verdict normal ; artefact
   diagnostic explicitement invalide, violations incluses, sans chaîne citable. Contradiction testée
   dans les deux sens.
2. **Accesseur contourné** (~:124) : `discarded` absent devient zéro (9 989 retenues : `inconclusif`
   avec `discarded=11`, `validé` sans la clé) ; statuts déclarés passés par `bool(…)` (`"false"` →
   `validé`, exit 0) ; rendement à exactement −1 accepté (finitude vérifiée, pas le domaine r > −1).
   Correction : compteur obligatoire et cohérent avec les réplications ; typage strict des
   déclarations présentes ; contrôle du domaine ; test de scan de source contre `bool(…)` sur donnée
   externe et `.get(clé, défaut)` sur champ obligatoire.
3. **Codes de sortie divergents de la table I.1** (~:1512 du protocole) : `entry.ok=False` → exit 0
   et verdict (au lieu de `R0_INVALID_RUN`, exit 2, arrêt) ; métrique NaN → exit 2 (le § F.7 renvoie
   à la ligne 15 du § I.1, code 1) ; toutes réplications écartées avec compte explicite → exit 2 (le
   § F.2(e) prévoit `F_NOT_ESTIMABLE`). Correction : test paramétré ligne à ligne sur I.1,
   distinguant donnée absente et échec numérique documenté.
4. **Docs** : blocs `C3A-INTERIM` → « correctifs livrés, revue ayant identifié des défauts
   restants », puis actualiser après correction ; `ROADMAP.md` ~:107 appelle encore le rejeu
   « phase courante ».

GO d'Astra obtenu le 21/09 sur `e358df9`. Reste à couvrir par les modules suivants : les lignes 3
à 6 de la table I.1 (portée `c3_select`), explicitement énumérées comme non couvertes par le test
paramétré actuel.

## 9. Brouillon d'addendum de reprise pour le nouvel agent (à confirmer par cadrage 4 questions)

Lecture proposée des 4 points : **nouvel agent** (décidé) ; **plan mode**, gate sur le plan, avec un
point d'arrêt recommandé après `c3_select` + `test_c3_chronology` (le cœur de la garantie) ; **scope**
= les cinq modules restants, leurs tests, les docs de clôture C3a et le brief C3b proposé — hors
toute modification du protocole, des moteurs, des seuils, toute campagne, toute exécution de C3b ;
**fin** = liste « done » du brief C3a v2 + règles acquises ci-dessous + porte pré-merge § L.5.

> **Reprise de C3a.** Lire, dans l'ordre : `agent/c3a_protocole_chronologique_v2.md` (brief), puis
> `docs/protocole_c3.md` (**gelé** au `d931293` — c'est la spécification, on ne la modifie pas),
> puis le code au `e358df9` (`scripts/audit/c3_common.py`, `c3_verdict.py`, le test de scan AST
> et `OPTIONAL_FIELDS`, le test paramétré I.1 et leurs fixtures).
> Branche `feat/c3a-protocole`, assert de branche avant chaque commit, un seul acteur git.
>
> **À construire** : `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select`, `c3_continuity` et leurs
> tests, dont `test_c3_chronology` (chronologie forte : préfixe seul vs préfixe + futurs différents
> → admissibilité, scores, classement complet et choix/abstention identiques, **plus un contrôle
> négatif** prouvant que le test détecte un scoreur fuyant). Puis docs de clôture et brief C3b
> proposé, non exécuté.
>
> **Règles acquises, non négociables :**
> - Tout accès à un champ obligatoire passe par **l'accesseur strict de `c3_common`** — aucune
>   logique de présence réécrite à la main.
> - Tout statut **dérivable des preuves disponibles** est recalculé, jamais recopié ; un désaccord
>   est une violation. Les déclarations non dérivables (la provenance notamment) sont exigées
>   explicites et strictement typées.
> - Finitude **et domaine** vérifiés avant toute comparaison (NaN, ±inf, rendement ≤ −1).
> - Aucun `bool(…)` sur une donnée externe, aucun `.get(clé, défaut)` sur un champ obligatoire dans
>   `c3_*.py` — gardé par le test de scan de source.
> - Les tests couvrent **chaque classe d'erreur** (déclarations contradictoires dans les deux sens,
>   clés absentes, `null`, types faux dont chaînes `"false"`, non-finis, hors domaine) et contiennent
>   un **témoin sain** — sans quota. Chaque test asserte **l'issue interdite** autant que l'issue attendue.
> - Codes de sortie conformes à la table I.1, **vérifiés par un test paramétré ligne à ligne** — le
>   test actuel couvre 1-2 et 7-15 ; **les lignes 3 à 6 sont dans le done de `c3_select`**. Une
>   violation **empêche la publication du verdict** : un artefact diagnostic reste possible,
>   explicitement invalide, sans chaîne de résultat citable.
> - Si une fixture révèle une incohérence du protocole gelé : **arrêt et signalement**, jamais de
>   modification du document pour faire passer un test.
> - Aucune modification de moteur, de runner, de seuil ; diff de contrôle vide hors la liste fermée.
> - Ton rapport décrit ce que les artefacts contiennent, pas ce que tu as voulu y mettre.
> - Les blocs `<!-- C3A-INTERIM:début -->` … `<!-- C3A-INTERIM:fin -->` de `CLAUDE.md`,
>   `PROJECT_CONTEXT.md` et `ROADMAP.md` (posés en `a9be714`, actualisés en `371f59b`) sont à **remplacer en bloc** à la
>   clôture, marqueurs compris — jamais complétés par un second énoncé d'état. À la clôture aussi :
>   `skills/backtest.md` (section protocole), `results/INDEX.md` (dont `results/c3a_entry_validation/`)
>   et `docs/CODE_MAP.md` (lignes `c3_*.py`, plus le rattrapage des `rejeu_*.py` et de
>   `c1_equity_probe.py`, signalé comme retard antérieur au chantier).
