# Note de passation — KrakenBot, C3a en cours (2026-09-20)

> Usage : (1) coller en ouverture de la nouvelle conversation Claude du Project ; (2) la dernière
> section sert de base au brief de reprise du nouvel agent, **après** cadrage 4 questions.
> Tout ce qui suit est tiré de la conversation précédente et des rapports d'agents ; les SHA et
> chiffres sont ceux rapportés — à revérifier contre un zip frais du repo.

## 1. Avant d'ouvrir la nouvelle conversation (à faire par Bruno)

1. **Recharger les fichiers du Project depuis la branche `feat/c3a-protocole` au commit `a9be714`**
   — pas depuis `dev`, ni depuis `~/wt-human` qui est sur `dev` (ex. `git show
   feat/c3a-protocole:CLAUDE.md > CLAUDE.md`). Les versions actuelles du Project datent du 16/09 et
   croient que C2 est le prochain chantier. Recharger `CLAUDE.md`, `PROJECT_CONTEXT.md`,
   `ROADMAP.md` (ils portent l'état courant dans un bloc `C3A-INTERIM`), et **ajouter
   `docs/protocole_c3.md`** et `agent/c3a_protocole_chronologique_v2.md`.
   `skills/backtest.md`, `results/INDEX.md` et `docs/CODE_MAP.md` sont **volontairement en retard**
   (mis à jour au commit de clôture de C3a, parce qu'ils décrivent un outillage et des artefacts qui
   n'existent pas encore) : l'état courant est porté par les blocs `C3A-INTERIM` et le protocole.
2. **Uploader un zip frais du repo** au commit `a9be714` pour pouvoir revérifier le code.
3. **Faire revoir `075f740` et `a9be714` ensemble par Astra** avant de lancer le nouvel agent (pas
   encore fait ; `a9be714` est documentaire, la revue porte sur les trois blocs `C3A-INTERIM`).

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
| `075f740` | **Noyau `c3_verdict` corrigé** + accesseur strict unique dans `c3_common` |
| `a9be714` | Mise à jour documentaire intermédiaire : blocs `C3A-INTERIM` dans `CLAUDE.md` (routage vers le protocole), `PROJECT_CONTEXT.md` (état C3a, dette 19, note WF non résolue), `ROADMAP.md` (C3a en cours, C3b ouvert) |

État au `075f740` : 1871 tests verts hors module de déterminisme, `mypy src/` = 64 (baseline),
ruff vert, diff de contrôle vide, protocole intact depuis le gel.

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
- **Artefact du rejeu** : refusé par l'outil, motif `D_WARMUP_PREFIX`, sortie sous
  `results/c3a_entry_validation/` avec hash source — « cet artefact ne satisfait pas les conditions
  d'entrée C3 », jamais un verdict sur la famille grid.

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
| Contrôle de présence qui passe sur une absence | 4 (`collect_flags` sur `"error"`, `flag_segment` sur bloc absent, sous-blocs `null` du validateur rejeu, `c3_verdict`) | Accesseur strict unique dans `c3_common` (absent, `null`, mauvais type, non-fini) ; tests négatifs clé absente **et** `null` |
| Règle énoncée à deux endroits, énoncés divergents | 4 paires au gate 2 de C3a | § 0.7 source unique ; index des symboles par `rg` ; **un symbole sans site de référence = une porte que rien n'applique** |
| La prose décrit une correction que l'artefact ne porte pas | ≥ 4 (journaux gitignorés, teardown vs setup, « one rule now governs », « énoncés remplacés supprimés ») | Revoir l'artefact, jamais le résumé |
| Généralisation qui dépasse le contre-exemple | G3 (5 formulations fausses), E2 « seulement si », indicateur de longueur, principe de promotion données/candidats | Décrire ce qu'un contrôle **détecte** ; poser une convention comme convention |
| Faire confiance à un drapeau déclaré au lieu de recalculer | `c3_verdict` estimabilité | Recalculer, recouper, désaccord = violation |
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

## 8. Points à vérifier en ouvrant

1. Revue Astra de `075f740` (accesseur strict, estimabilité recalculée, finitude, 62 tests).
2. Sémantique de sortie : une preuve manquante → exit 2 sans artefact ; une violation → exit 1
   **avec** artefact écrit. Vérifier que cet artefact est **sans ambiguïté marqué comme violation**
   et ne contient aucune chaîne de verdict citable comme résultat.
3. Que la table I.1 du protocole gelé dise exactement cette sémantique (sinon : arrêt et signalement).

## 9. Brouillon d'addendum de reprise pour le nouvel agent (à confirmer par cadrage 4 questions)

Lecture proposée des 4 points : **nouvel agent** (décidé) ; **plan mode**, gate sur le plan, avec un
point d'arrêt recommandé après `c3_select` + `test_c3_chronology` (le cœur de la garantie) ; **scope**
= les cinq modules restants, leurs tests, les docs de clôture C3a et le brief C3b proposé — hors
toute modification du protocole, des moteurs, des seuils, toute campagne, toute exécution de C3b ;
**fin** = liste « done » du brief C3a v2 + règles acquises ci-dessous + porte pré-merge § L.5.

> **Reprise de C3a.** Lire, dans l'ordre : `agent/c3a_protocole_chronologique_v2.md` (brief), puis
> `docs/protocole_c3.md` (**gelé** au `d931293` — c'est la spécification, on ne la modifie pas),
> puis le code au `075f740` (`scripts/audit/c3_common.py`, `c3_verdict.py` et leurs tests).
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
> - Tout statut est **recalculé**, jamais recopié d'une valeur déclarée ; un désaccord est une violation.
> - Finitude vérifiée **avant** toute comparaison (NaN, ±inf).
> - Les tests d'un module qui refuse des artefacts sont **majoritairement adverses** (drapeaux
>   contradictoires, clés absentes, `null`, types faux, non-finis) ; chaque fichier contient un
>   **témoin sain** ; chaque test asserte **l'issue interdite** autant que l'issue attendue.
> - Codes de sortie conformes à la table I.1 du protocole ; un artefact écrit sur violation est
>   marqué sans ambiguïté comme violation.
> - Si une fixture révèle une incohérence du protocole gelé : **arrêt et signalement**, jamais de
>   modification du document pour faire passer un test.
> - Aucune modification de moteur, de runner, de seuil ; diff de contrôle vide hors la liste fermée.
> - Ton rapport décrit ce que les artefacts contiennent, pas ce que tu as voulu y mettre.
> - Les blocs `<!-- C3A-INTERIM:début -->` … `<!-- C3A-INTERIM:fin -->` de `CLAUDE.md`,
>   `PROJECT_CONTEXT.md` et `ROADMAP.md` (commit `a9be714`) sont à **remplacer en bloc** à la
>   clôture, marqueurs compris — jamais complétés par un second énoncé d'état. À la clôture aussi :
>   `skills/backtest.md` (section protocole), `results/INDEX.md` (dont `results/c3a_entry_validation/`)
>   et `docs/CODE_MAP.md` (lignes `c3_*.py`, plus le rattrapage des `rejeu_*.py` et de
>   `c1_equity_probe.py`, signalé comme retard antérieur au chantier).
