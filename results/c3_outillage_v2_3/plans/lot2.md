# C3 — Outillage v2.3, lot 2 (conformité serveur sous v2.3, porte § L.5, rapport final) — plan (GO reçu)

## Contexte

Lot 1 clos et poussé : `feat/c3-outillage-v2.3` @ `a30d62a2fec51a4c277d51a5d20047892b2fbcca` (X1-X8 levés, 3 321 passés /
1 xfail, 39 mutants, CI verte en tentative 1 sur C4 et C5). La conformité serveur du 30/09 a été prouvée sous v2.2 :
sous v2.3, `c3_anchor` refuse son manifeste (sha v2.2, pas de `deferred_evaluation.date`), elle n'a plus de valeur
probante. Ce lot la **rejoue** sous v2.3, puis tient la porte § L.5 option 1, puis écrit le rapport final du chantier.
Brief § 4 : **aucun code** (ni `scripts/`, ni `tests/`, ni `src/`) ; seulement un manifeste de conformité, un attendu, deux
pilotes, des scripts de preuve `results/c3_outillage_v2_3/tests/*.sh` et leurs sorties, l'entrée du journal, le
rapport. Modèle : lot 3 du chantier v2.2 (`results/c3_outillage_v2_2/plans/lot3.md`, `conformite/`, `gate_L5/`), repris
par substitution. **Rien ne tourne sur le serveur avant STOP 1.** Tunnel jamais ouvert dans ce lot.

## 0. GO reçu (30/09, Bruno)

Branche `feat/c3-outillage-v2.3` au tip du lot 1 `a30d62a2fec51a4c277d51a5d20047892b2fbcca`. G0 (30/09, 20:26:53Z) : tunnel
fermé ; constat : `gel_v2_3.patch` absent de la racine (retiré hors de cette session) — `interdits_lot2.sh` exige
seulement qu'il ne soit pas suivi, et inchangé s'il réapparaît.

Plan approuvé tel quel : K1 à K9 pris, D1 à D10 dans les recommandations.
- **K5** : constat exact — l'obligation venait du D9 du lot 1 et le message de lancement de Bruno l'a propagée sans
  vérifier quelle porte le brief visait ; défaut à consigner au rapport final comme tel, **imputé au lot 1 et au message
  de lancement**, aucune correction du README clos.
- **D8** accepté avec sa motivation (le bord admis de X2 rejoué sur le chemin réel).
- **D3** : la règle 64 hex vaut pour ce lot ; elle ne préjuge en rien du chantier de campagne, où elle sera re-décidée.
- Enchaîner **G0 → C0 → S1, puis STOP 1** : Bruno relit l'attendu, le manifeste et le pilote au SHA S1 complet avant tout
  GO de lancement. **Rien ne tourne sur le serveur avant ce GO.**

## 1. Constats de lecture (déclarés, pas arbitrés)

| # | Constat | Effet |
|---|---|---|
| K1 | v2.3 ne change au manifeste que `protocol_sha256` et la clé obligatoire `deferred_evaluation.date` ; `variant_id`, `research_log_entry`, `run_scope` se réécrivent comme au 30/09 | manifeste = celui du 30/09 (`c3769a6a…1ff7`) + ces seuls chemins, prouvé par `manifest_check.sh` |
| K2 | Provenance `unknown` → `P_PROVENANCE` (rang 2) : la voie du § 10.1 ne s'ouvre pas, **aucune évaluation différée n'est inscrite** ; le verdict n'inscrit que `{issue, raison, compte}` (non compté) dans un registre jeté | aucun code attendu ne change ; l'absence d'inscription n'est pas observable sans lire le registre (non-lecture) — déclaré, jamais vérifié par lecture |
| K3 | Le code de la chaîne v2.3 ne change ni la forme de `verdict.json`, ni la liste des artefacts : les **23 artefacts** du 30/09 restent la liste attendue ; la ligne `written <registre> …` n'a plus de digest (D13 du lot 1) et le pilote ne la lisait pas | pilote et `verify_attendu.py` repris, constantes seules changées |
| K4 | `c3b_*.py` inchangés depuis la conformité v2.2 (lot 1 : diff vide prouvé) ; `EVENTS` du pilote identique, re-prouvé par `events.sh` au code de S1 | liste close reprise |
| K5 | La porte § L.5 option 1 = les 24 `test_determinism_parallel_vs_serial_full` ; **le test renommé au lot 1 n'y figure pas** : l'obligation « la porte cite le nom neuf » de `lot1/README.md` § 5 est **fausse** | défaut du lot 1, dit comme tel au rapport final (§ 6), aucune correction du README clos |
| K6 | Le 30/09 v2.2 a archivé sous `~/archive/c3_outillage_{conf,gate}_20260930/` : même date possible aujourd'hui | noms v2.3 distincts (D9, brief § 4) |
| K7 | Le contrôle « 64 hex ajoutés ∈ table d'Adoption » d'`interdits.sh` (lot 1) refuserait les sha sûrs de ce lot (manifeste, pilotes, extraits, archives), que le précédent v2.2 versionne | règle étendue au lot 2 (D3), jamais relâchée pour un artefact du chemin |
| K8 | L'expression régulière d'artefacts d'`interdits.sh` inclut `manifest*.json` | `conformite/manifest.json` exclu par son nom exact (précédent v2.2) |
| K9 | Les 24 `_full` lisent des bougies USDC 2023-04 → 2026-04 (comparaison par hash, aucune métrique lue) | la phrase « aucune donnée de la fenêtre de campagne lue » est écrite avec sa portée (producteur et chaîne), l'exception en limite (précédent v2.2 K11) |

## 2. Décisions demandées au GO

| # | Question | Recommandation et motif |
|---|---|---|
| D1 | SHA du run de conformité | **S1**, le commit qui porte attendu, manifeste, pilotes, scripts et entrée 21 ; code identique à `a30d62a` (prouvé par `interdits_lot2.sh`) ; pilote exécuté depuis le clone (précédent v2.2 D1) |
| D2 | Journal | **Entrée 21 à S1, avant lancement** ; « Issue de l'entrée 21 » et un ajout aux « Essais à venir » en clôture (S3), sans réécrire |
| D3 | Ce qui remonte | **Codes et booléens seulement** ; aucun sha d'artefact du chemin sélection. `interdits_lot2.sh` admet une empreinte de 64 hex seulement si elle est : de la table d'Adoption ; le sha256 d'un fichier **versionné** du chantier (`results/c3_outillage_v2_3/**`) ou du manifeste v2.2 comparé ; ou le sha d'une archive consigné dans un `*.tgz.sha256` du chantier |
| D4 | Trois exécutions | **`--workers` 4 / 1 / 4 au préfixe**, tout le reste identique, même `--now`, même chemin absolu + `mv` ; critère : 23 artefacts identiques au bit |
| D5 | SHA de la porte | **S2** (preuves de conformité) ; S3 porte le rapport ; invariance du code de S2 au tip prouvée par `interdits_lot2.sh` |
| D6 | Docs hors liste | `CLAUDE.md`, `skills/backtest.md`, `PROJECT_CONTEXT.md`, `results/INDEX.md`, `docs/CODE_MAP.md` : **non touchés** (le brief ne les nomme pas) ; lignes périmées listées au rapport pour le `docs(merge)` de Bruno. Seul doc touché : `docs/RESEARCH_LOG.md` |
| D7 | Écart à l'attendu | **Rien** : STOP, répertoire serveur laissé en place, seuls `status.txt`, `pilot_exit.txt`, les deux `alembic` remontent ; aucune lecture de diagnostic sans l'accord de Bruno |
| D8 | Date déclarée | `deferred_evaluation.date = 2021-12-28T00:00:00+00:00` : **365 jours exactement** après `window.end` (2020-12-28 ; 2021 non bissextile) — le bord admis de X2 rejoué sur le chemin réel. Une déclaration, jamais une fenêtre lue ; garde-fou 6 ne lit que `window` |
| D9 | Noms serveur | runs `~/runs/c3_outillage_v2_3/{conf,gate}/{repo,out}` ; archives `~/archive/c3_outillage_v2_3_{conf,gate}_<AAAAMMJJ>/` (brief) ; tmux `c3-outillage-v23-{conf,gate}-<AAAAMMJJ>` ; `~/docker/` jamais nommé |
| D10 | Valeurs | famille `test-conformite-instrument-2020` inchangée (valeur de test, registre neuf par exécution) ; `variant_id` `c3-outillage-v23-conformite-2020` ; `--campaign OUTILLAGE_V23_CONF` (étiquette d'instrument, dette 21 intacte) ; `--now` = `<date de S1>T00:00:00+00:00`, le même partout |

## 3. Commits (branche assertée, message par `-F`, `interdits_lot2.sh <label>` avant chacun)

| Commit | Contenu | Poussé |
|---|---|---|
| G0 (geste) | `bash tests/tunnel.sh state` → fermé attendu | — |
| **C0** `docs(results)` | `plans/lot2.md` (ce plan, GO inclus) ; `tests/interdits_lot2.sh` ; `interdits_lot2_C0.out` ; `tunnel.out` | non |
| **S1** `docs(research)` — **SHA du run** | `conformite/{manifest.json, attendu.md, server/run_conformite.sh, server/verify_attendu.py}`, `gate_L5/run_gate.sh`, scripts `preflight`, `launch`, `wait`, `fetch`, `archive`, `postflight`, `verify_conformite`, `verify_gate`, `verify_adverse`, `pilot_dryrun`, `manifest_check`, `events`, `lint_lot2`, et leurs `.out` d'avant lancement (`manifest_check`, `events`, `lint_lot2`, `pilot_dryrun`, `verify_adverse`) ; `docs/RESEARCH_LOG.md` entrée 21 ; `interdits_lot2_S1.out` | oui, CI lue |
| **STOP 1** | Bruno relit l'attendu au SHA S1 complet, avec pilote et manifeste → **GO de lancement nommant S1** | |
| **S2** `docs(results)` | preuves de conformité (`conformite/server/{status.txt, pilot_exit.txt, alembic_before.txt, alembic_after.txt, verify_attendu.out, <archive>.tgz.sha256}`, `tests/{preflight,launch,wait,fetch,archive}_conf.out`, `ci_status_S1.out`) | oui, CI lue |
| porte § L.5 au S2 | | |
| **S3** `docs(results)` | preuves de la porte (`gate_L5/…`, `tests/*_gate.out`, `verify_gate.out`, `postflight.out`) ; **`report.md`** ; `RESEARCH_LOG` (issue 21, essais à venir) ; `tunnel.out` (fermé) | oui, CI lue |
| **S4** `docs(results)` | `ci_status_S3.out` | oui ; CI de S4 au message |
| **STOP 2** | rapport final, relecture de Bruno, **merge par Bruno** | |

## 4. Livrables, par reprise du lot 3 v2.2 (constantes seules changées, chaque écart déclaré)

- **`conformite/manifest.json`** : celui du 30/09 + `deferred_evaluation.date` (D8), `protocol_sha256` v2.3, `variant_id`,
  `research_log_entry` (entrée 21), `run_scope` réécrits. `manifest_check.sh` : chemins changés contre
  `results/c3_outillage_v2_2/conformite/manifest.json` = exactement `ajouté {deferred_evaluation.date}`, `retiré ∅`,
  `réécrit {protocol_sha256, research_log_entry, run_scope, variant_id}` ; sha du protocole = v2.3 ; `c3_anchor` local
  (hors dépôt) code 0 et `T = 2020-09-11T21:36:00+00:00` (preuve locale que la date passe la borne).
- **`conformite/attendu.md`** : l'attendu du 30/09, items 1-10 inchangés dans leurs codes (préfixe 0 ×3, chaîne 1-4
  autonome 0 ×4 ×3, `eval 0 event=evaluated` ×3, `chain` 0 avec les six codes d'étape, `chain.verified` vrai, violations
  vides, 23 artefacts identiques au bit, alembic `c3bd1e7a0001 (head)` inchangé, service inchangé, `pilot_exit=0`),
  protocole et manifeste v2.3, et un § « Ce que v2.3 change » : la clé et sa borne (D8), K2, K3.
- **`conformite/server/run_conformite.sh`**, **`verify_attendu.py`**, **`gate_L5/run_gate.sh`** : repris ; changent
  `SELF`, `MANIFEST`, `MANIFEST_SHA`, `PROTOCOL_SHA` (v2.3), `RUN` (D9), `CAMPAIGN`, `NOW`, `KRAKENBOT_SUFFIX` ; rien
  d'autre (diff contre les fichiers v2.2 versionné dans `tests/reprise_lot2.out`, lignes changées = liste déclarée).
- **Scripts** (`preflight`, `launch`, `wait`, `fetch`, `archive`, `postflight`, `verify_conformite`, `verify_gate`,
  `verify_adverse`, `pilot_dryrun`, `events`, `lint_lot2`) : repris, chemins et noms (D9), branche
  `feat/c3-outillage-v2.3`, archives `c3_outillage_v2_3_<phase>_…` ; `ci_status.sh` et `tunnel.sh` du lot 1 tels quels.
- **`tests/interdits_lot2.sh`** : les contrôles du lot 1 contre `b50f2d1` (protocole, `CAMPAIGN_UNLOCK`, dette 23,
  `gel_v2_3.patch` inchangé) **plus** diff vide contre `a30d62a` sur `scripts/ tests/ src/ config/ pyproject.toml
  poetry.lock .github/ agent/ skills/ CLAUDE.md docs/protocole_c3.md docs/amendements_c3_v2.* docs/CONTRAINTES_POST_B4.md
  results/c3_v2_2 results/c3b_producteur results/c3_outillage_v2_2 results/c3_v2_3_gel` ; fichiers changés depuis
  `a30d62a` ⊆ `{results/c3_outillage_v2_3/**, docs/RESEARCH_LOG.md}` ; aucun artefact du chemin (hors
  `conformite/manifest.json`) ; règle 64 hex de D3. `interdits_lot2_adverse.sh` : sa preuve (témoin 0, cas déviés dont un
  sha d'artefact hors règle, `conformite/verdict.json`, `scripts/` touché, `CLAUDE.md` touché).

## 5. Procédure serveur (après le GO de lancement)

1. `preflight.sh conf` (lecture seule : HEAD et lignes sales du service, venv, `poetry.lock`/`pyproject.toml` = S1, run et
   archive du jour absents, tmux, disque, mémoire, collector actif et `NRestarts`, trader inactif, `.env`, 5432 ouvert /
   5433 fermé, `CAMPAIGN_UNLOCK` absent) → rc≠0 : STOP.
2. `launch.sh conf <S1>` (HEAD local = tip origin = argument ; clone, `checkout --detach`, `.env`, sha du pilote = blob ;
   tmux `bash -lc`).
3. `wait.sh conf 60 40` en arrière-plan (existence de `pilot_exit.txt`, nombre de lignes et dernière ligne de
   `status.txt` : des codes).
4. `fetch.sh conf` (status, pilot_exit, alembic ×2) → `verify_conformite.sh <S1>` → rc≠0 : D7.
5. `archive.sh conf <date>` (out/ seul, sans `repo/` ni `.env` ; contrôles par codes ; `rm -rf` puis `rmdir` du parent).
6. S2 poussé, CI verte → porte : `preflight.sh gate`, `launch.sh gate <S2>`, `wait.sh gate 300 42` (≈ 71 min),
   `fetch.sh gate`, `verify_gate.sh <S2>` (24/24 `rc=0`, JUnit `tests:24,failures:0,errors:0,skipped:0,missing:0`,
   extrait, arbre, alembic, collector), `archive.sh gate <date>`, `postflight.sh` (runs absents, aucune session tmux
   du chantier, deux archives `sha256sum -c`, collector actif `NRestarts` inchangé, HEAD et lignes sales du service
   inchangés, alembic head inchangé, `CAMPAIGN_UNLOCK` absent).

Journaux en fichiers seulement ; ni listing, ni taille, ni sha d'artefact ; issue jamais lue.

## 6. Rapport final `results/c3_outillage_v2_3/report.md` (S3, modèle : rapport v2.2)

Première ligne avec sa portée (K9). Puis : livré (lot 1, repris ; lot 2) ; tests (suites, comptes 3 309 + 8 + 4 =
3 321, 8 levés, 1 caduc) ; mutants (39) ; écarts au brief (lot 1 : D9 ligne 706, D10 3 321 ; lot 2 : K5, D3 règle 64 hex,
D6) ; décisions et limites (D2, D12, D13 du lot 1 : `anchor.json.registry.sha256` et la note du sel, taille du registre) ;
candidats v2.4 consolidés ; défauts des deux lots dits comme tels (dont K5) ; preuves serveur (conformité : codes,
attendu tenu n/n, archive ; porte : 24/24, archive) ; tunnel, base, interdits ; ce qui attend (merge par Bruno, CODE_MAP,
lignes périmées de D6, pull du serveur, manifeste de la première campagne sous v2.3, sel du registre de campagne).

## 7. Vérification

- **Avant S1** : `manifest_check.out` rc=0 ; `events.out` rc=0 ; `lint_lot2.out` rc=0 (ruff check/format `--check` sur les
  `.py` du lot, `bash -n` sur les `.sh`) ; `reprise_lot2.out` (diffs contre v2.2 = liste déclarée) ;
  **`pilot_dryrun.out`** (monde simulé : conforme → 0, `bit_equal_3of3=0 compared=23` ; un artefact différent au seul run 2
  → 1 ; violation de rejeu → 1 ; SHA faux → 2 ; porte conforme → 0, combo skippé → 1) ; **`verify_adverse.out`**
  (témoins 0, chaque cas dévié ≠ 0, un item en écart par cas) ; `interdits_lot2_adverse.out` ; `interdits_lot2_S1.out`
  rc=0 ; CI verte au SHA S1.
- **Conformité** : `verify_attendu.out` tous items tenus, archive vérifiée, `rm` consigné.
- **Porte** : `verify_gate.out` rc=0 (24/24), archive vérifiée, `postflight.out` rc=0.
- **Clôture** : `interdits_lot2_S3.out` rc=0 ; `tunnel.sh state` fermé ; CI verte à S3, lue à S4 ; `git status` propre
  (hors `gel_v2_3.patch`) ; push sans merge ; STOP 2.

## 8. Règle d'arrêt

Tout code hors attendu, `chain.verified` faux, une violation, trois exécutions non identiques, un item en écart, un
besoin de code (`scripts/`, `tests/`, `src/`), une garde du preflight en échec → STOP, constat versionné, rien de relancé
« pour voir ». Seule une panne du pilote lui-même (127, chemin) se relance, après correction par un commit repassé par
Bruno.
