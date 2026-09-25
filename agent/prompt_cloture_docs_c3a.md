# Session clôture documentaire C3a — brief agent (2026-09-XX)

> Nouvel agent, nouvelle session. **Documentation seule — aucune ligne de code, aucun test
> modifié.** Le protocole `docs/protocole_c3.md` reste gelé au `d931293` : rien n'y change dans
> cette session (les amendements ont leur gate, plus tard). Plan mode : proposer le plan complet,
> **arrêt strict R1** jusqu'à validation humaine, puis exécution.

## 0. État et bornes

- Tip `acaeaf6` sur `feat/c3a-protocole`. C3a : code livré, arrêt Fin validé par les deux revues
  le 22/09. Restent, hors de cette session : gate d'amendement du protocole, porte pré-merge
  § L.5 (24 tests de déterminisme serveur + re-passe Astra sur le SHA final), brief C3b.
- Working tree à l'ouverture : `agent/passation_c3a_20260920.md` supprimé (suivi à HEAD),
  `agent/rapport_session_c3a_20260922.md` non suivi. **Cette session résout cet état,
  délibérément** (§ 2.7-2.8) — c'est la seule exception à la préservation.
- `git add` par chemin explicite seulement ; assert de branche avant chaque commit ; commits
  atomiques `docs(c3a): …`.

## 1. À lire avant le plan

1. `agent/rapport_session_c3a_20260922.md` (working tree) — la source de tout ce qui suit :
   conventions datées (§ 7 et § 13), décisions des revues, § 10 (conditions pré-merge), § 12.
2. `git show HEAD:agent/passation_c3a_20260920.md` — la note à corriger.
3. `CLAUDE.md`, `PROJECT_CONTEXT.md`, `ROADMAP.md`, `docs/CODE_MAP.md`, `results/INDEX.md`,
   `skills/backtest.md`, `docs/RESEARCH_LOG.md`, `docs/CONTRAINTES_POST_B4.md` — l'existant à
   mettre à jour, pas à réécrire.

## 2. Livrables (l'ordre est indicatif, le plan le fixe)

1. **Blocs `C3A-INTERIM`** : recensés (`rg C3A-INTERIM`), chacun résolu — remplacé par l'état
   post-C3a ou supprimé s'il n'a plus d'objet. Aucun bloc restant à la fin.
2. **`skills/backtest.md`** — section « Validation C3 » : la chaîne (7 modules, ordre § L.1,
   codes I.1), et les **conventions d'outillage datées** du rapport, documentées comme
   **comportement de l'outillage, jamais comme norme** (la norme reste le protocole) : artefact
   diagnostic en code 1 ; `B ≠ BOOTSTRAP_B` → 2, R0 avant tout parsing ; `UndefinedIssueError`
   → 2 (clause 3 cohérente) ; preuve absente après violation → 2, violations sur stderr ;
   précédence par ordre de constat ; `not_assertable` jamais verte ; table provenance × statut ;
   listes d'états closes par clause ; définition de `chain.verified` ; confinement
   `evaluation.synthetic` ; convention moteur `_btc` ; D3 `C_COVERAGE` et ordre d'affichage.
3. **Correction de la passation** : restaurer `agent/passation_c3a_20260920.md` depuis HEAD,
   corriger le chiffre mypy (64 → 65, renvoi au rapport C2 § 0 : le 64 venait de
   `--ignore-missing-imports`), committer. Consensus Astra acquis (revue Fin du 22/09).
4. **`PROJECT_CONTEXT.md`** : encart d'état daté — C3a livrée et validée (revues croisées, 806
   tests), artefact réel refusé à l'entrée (§ D.3, 96/96), **fait stratégique : aucune campagne
   existante ne peut traverser la chaîne sans producteur conforme (chantier C3b)** ; phase
   courante : pré-merge + préparation C3b ; roadmap B5→P10 toujours suspendue ; rien à trader.
5. **`ROADMAP.md`** : C3a close ; C3b en deux paquets (1 : gate d'amendement + chantier
   producteur — exports lots / `exec_interval` / preuve de départ à plat / `single_call` /
   `first_fill_at` / amorçage suffisant au préfixe ; 2 : campagne réelle sous la chaîne).
6. **`docs/CODE_MAP.md`** : `scripts/audit/c3_*.py` (7 modules + rôle d'une ligne chacun), les
   8 fichiers de tests, `results/c3a_entry_validation/`.
7. **`results/INDEX.md`** : entrée `c3a_entry_validation/` (refus `D_WARMUP_PREFIX`, portée
   artefact, empreintes).
8. **`docs/RESEARCH_LOG.md`** : entrée de clôture C3a — dates, verdict de session, renvoi au
   rapport.
9. **`CLAUDE.md`** — règles gagnées de la session, ajoutées aux règles agent : tout test de
   contrat naît adverse (constaté rouge avant le correctif ou avec son adverse s'il est neuf) ;
   le témoin sain est lui-même conforme au contrat ; l'attendu d'un test se dérive de la table ou
   du texte, appui cité — jamais de l'implémentation ; `pipefail` sur toute vérification pipée ;
   précédence par ordre de constat.
10. **Le rapport lui-même** : proposition au plan — commit en `agent/` (trace durable, comme la
    passation) ou maintien hors repo ; décision humaine à R1.

**Hors périmètre** : protocole, code, tests, brief C3b, amendements, merge, fichiers `results/`
du rejeu.

## 3. Fin de session

Liste des fichiers modifiés avec une ligne par fichier ; `rg C3A-INTERIM` vide ;
`pytest -q tests/test_scripts/test_c3_*.py` inchangé (806) ; diff de contrôle § L.3 vide ;
`git status` propre. Rappel à l'humain en fin de rapport : **rafraîchir les 7 fichiers du
Project claude.ai** depuis ce tip (ils datent de `5e056e0`).
