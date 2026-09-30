Aucune donnée de la fenêtre de campagne 2021-03-01 → 2026-06-29 n'a été lue par le producteur ni par la chaîne, sur aucun run de ce chantier ; aucune issue de chaîne n'a été lue.

# C3 — outillage v2.2 : rapport final du chantier (lots 1 à 3)

**Fenêtre d'instrument, aucune portée économique.** Ce chantier livre le code qui applique le protocole C3 v2.2
(sha256 `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`), puis rétablit sous v2.2 la conformité du
producteur C3b. Celle du 28/09, établie sous v2.1, n'avait plus de valeur probante. Il ne dit rien de la famille grid :
aucune métrique de candidat n'a été lue, commentée ni reportée.

La phrase de la première ligne a une portée, et deux exceptions sont dites au § 8 :
- les 24 tests `_full` de la porte § L.5 ;
- les 13 tests base de la suite, lancés par le tunnel aux lots 1 et 2.

Les deux lisent des données de la période de campagne. Ce ne sont pas des runs du producteur, et aucune métrique n'en
a été lue.

- **Brief** : `agent/AGENT_C3_OUTILLAGE_V2_2.md`. **Liste close** : `results/c3_v2_2/outillage_v2_2.md`.
- **Plans**, un par lot, chacun approuvé avant sa première écriture : `plans/lot1.md` (D1-D14), `plans/lot2.md`
  (D1-D12) et `plans/lot3.md` (D1-D7, plus la condition « vérificateurs prouvés avant de servir »).
- **Branche** `feat/c3-outillage-v2.2`, partie de `dev = 8c114fe`. Trois lots, une session et un GO par lot, poussée à
  chaque lot. **Aucun merge : il est fait par Bruno après relecture de ce rapport (STOP 2).**
- **Journal** : `docs/RESEARCH_LOG.md`, entrée 19, avec son issue.

## 1. Ce qui est livré

### Lot 1 — chaîne pure : R-15, R-21, R-22, R-17 (`lot1_chaine/README.md`)

| Commit | Objet | Marqueurs levés |
|---|---|---|
| `6e9f4c0` | brief tel que reçu, plan du lot 1 | — |
| `40b1276` | **R-15 producteur** (D1) : `evaluation.json` déclare `lambdas {dd, sigma}` ; `benchmark_eval.json` porte `nav`, la NAV du B&H plein notionnel | 1 |
| `1f96cde` | **R-15 chaîne** : quatre entrées de plus au verdict ; recalcul au bit de `returns_config`, de la NAV du B&H, des λ et de `returns_bench` ; règle d'entrée de l'export (code 2) ; recalcul impossible → violation (C-3) ; `--candles-eval` ; test neuf A1 | 8 + 1 (XPASS D12a) |
| `a538d22` | **R-21** : `cc.cagr_pct` rend `None`, jamais une exception ; D4 = rendements définis et tous finis, CAGR fini ; item hors réserve **caduc** (AM-10) | 2 + 1 (R-22 cas 3) |
| `ae12546` | **R-22 cas 1, 2, 4** : registre canonicalisé à la lecture (diagnostic, 1) ; NAV du B&H du préfixe en décimal, rendements non finis non écrits (paire non comparable, 0) ; estimabilité non finie → violation | 3 |
| `8275827` | **R-17** : famille obligatoire ; sha du protocole asserté avant le typage (D9) ; `stop_criterion` à l'ancrage ; table `COUNTED` du § 10.1 ; inscription à l'étape 6 en mode `chain` ; tests neufs : témoin, épinglage, A2 | 5 |
| `c8db3c0`, `8d2ef60` | rapport, preuves et mutants ; statut CI (verte au `c8db3c0`) | — |

### Lot 2 — producteur et réserves mixtes : R-16, R-18, R-19, R-20, hors réserve (`lot2_producteur/README.md`)

| Commit | Objet | Marqueurs levés |
|---|---|---|
| `e722901` | plan du lot 2 (GO inclus) ; `lint.sh` étendu | — |
| `93b983e` | **R-16** : clés `_quote` aux positions nommées, à l'export et à la lecture ; garde `cc.check_quote_amount_keys` bornée aux deux positions (D11) ; argument moteur `min_order_usdc=` inchangé | 10 |
| `5ea08ac` | **R-18** : forme de refus du comparateur non constructible, écrite par le producteur (code 0, moteur jamais construit) ; admission, identité avant le bloc (C-1), rejeu de la non-constructibilité, `inconclusif`, `continuite=-`, `motif` / `motif_detail` | 4 |
| `5d41fb2` | **R-19** : `metrics.executions` exporté et exigé ; `first_fill_at` nul ⟺ zéro exécution ; zéro exécution ⟹ equity = `C` (D9) ; c5 `NON VÉRIFIABLE` ssi `first_fill_at` nul | 6 |
| `1517424` | **R-20** : dates de couverture nulles ssi aucune unité couverte ; contradiction → violation (D10) | 4 |
| `8ff96a5` | **hors réserve** : construction du comparateur en échec → `comparator_failed`, code 3, à son site avant le moteur (D2) ; adverse neuf T15 | — |
| `c566b33` | branche morte `except OverflowError` retirée (D12) | — |
| `4f25205`, `5f61ac9` | rapport, preuves et mutants ; statut CI (verte au `4f25205`) | — |

### Lot 3 — conformité serveur sous v2.2 et porte § L.5 (ce rapport)

| Commit | Objet |
|---|---|
| `892111f` (C0) | plan du lot 3 (GO inclus) ; `interdits.sh` étendu (bloc lot 3 contre `5f61ac9`) et prouvé par `interdits_adverse.sh` ; tunnel constaté fermé |
| `08cba3d` (S1) | **SHA du run de conformité**. Il porte l'entrée 19, l'attendu, le manifeste v2.2, les deux pilotes, `verify_attendu.py`, les scripts serveur génériques, `events`, `manifest_check`, `lint_lot3`, `pilot_dryrun` et `verify_adverse`. **Aucun code** |
| `4089fd5` (S2) | preuves de la conformité (codes et booléens) ; **SHA de la porte § L.5** |
| S3 | preuves de la porte, ce rapport, `PROJECT_CONTEXT.md`, issue de l'entrée 19, `results/INDEX.md` |
| S4 | statut CI de S3 |

**Le lot n'écrit aucun code.** Diff vide contre `5f61ac9` sur `scripts/ tests/ src/ config/ pyproject.toml
poetry.lock .github/`, à chaque commit : `tests/interdits_{C0,S1,S2,S3}.out`.

Noms d'interface ajoutés aux lots 1-2, déclarés dans leurs README :
- `family`, `verdict {issue, raison, compte}`, `deferred_evaluation`, `lambdas`, `--candles-eval` ;
- `motif_detail`, `refused_route`, `--benchmark-eval` facultatif ;
- `Manifest.min_order_quote` ;
- `cc.REFUSAL_REASONS`, `cc.BENCHMARK_MOTIFS`, `cc.EVALUATION_SERIES`, `cc.is_refusal_form`,
  `cc.refusal_series_carried`, `cc.execution_recoupements`, `cc.check_quote_amount_keys`.

## 2. Tests

| Étape | Passés | Ignorés | Désélectionnés (`_full`) | xfail | Échecs / XPASS |
|---|---|---|---|---|---|
| base (`8c114fe`) | 3 259 | 6 | 24 | 46 | 0 |
| fin du lot 1 (`8d2ef60`) | 3 284 | 6 | 24 | 25 | 0 |
| fin du lot 2 (`c566b33`) | **3 323** | 6 | 24 | **1** | 0 |
| lot 3 | inchangé : aucun code, aucun test (K12) | | | | |

- **Décompte** : 3 259 + 45 levés + 19 neufs = 3 323 (`tests/comptes_lot2.out`, par diff d'identifiants contre
  `8c114fe`). Aucun test retiré.
- **Tests neufs** : 4 au lot 1 (A1, A2, le témoin R-17 et l'épinglage § 10.1) et 15 au lot 2 (T1-T15).
- **Le seul xfail restant** est l'item hors réserve **caduc** (`test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3`).
  AM-10 l'a rendu caduc, par décision de gate du 29/09 ; il est re-marqué `raises=AssertionError`, ses assertions
  intactes, et T15 le remplace. La porte « 0 xfail » du brief devient donc **45 levés + 1 caduc déclaré**.
- **Diff des tests** contre `8c114fe` (`tests/diff_tests_lot{1,2}.out`, par l'AST) : les corps des 46 tests xfail de
  la base sont identiques. Tout autre changement est déclaré.
- **CI verte en tentative 1, sans aucune relance**, à chaque SHA :

  | SHA | Run |
  |---|---|
  | `c8db3c0` (lot 1) | 36599366877 |
  | `4f25205` (lot 2) | 36631049528 |
  | `08cba3d` (S1) | 36638062076 |
  | `4089fd5` (S2) | 36682922620 |

  S3 : `tests/ci_status_S3.out`, au commit S4.

## 3. Mutants (`mutants.log`)

- **Lot 1** : M1 à M6, tous rouges, puis restaurés et verts. M3b (M3 sans A1) est tué par le seul test R-18 « refus
  avec séries » (défaut 2 du lot 1).
- **Lot 2** : **19 mutants**, L2M1 à L2M17 plus L2M3b et L2M8b (19 noms distincts à `mutants.log` comme au tableau),
  chacun tué par le test nommé au `lot2_producteur/README.md` § 3. Ce README dit « dix-huit » (§ 6, défaut 4), et le
  compte est faux : 13 prévus + 6 ajoutés = 19 (voir § 6.1). Les six mutants du lot 1 ont été rejoués au tip du lot 2 et sont tous rouges.
  - **Constat L2M8** : le test xfail levé homologue reste vert sous ce mutant, parce que le recalcul R-15 le voit
    d'abord.
- **Lot 3** : pas de mutant de code, puisqu'il n'y a pas de code. Les vérificateurs sont prouvés par cas déviés
  (§ 7.1).

## 4. Écarts au brief et à la liste close (déclarés, jamais arbitrés)

### Lot 1 (`lot1_chaine/README.md` § 4-5)

| Critère ou item | Constat |
|---|---|
| « Les 20 xfail du lot levés » | **21** : R-15 entier au lot 1 (D1), plus 1 XPASS (D12a) |
| « Les 4 xfail de chaîne R-18 restent xfail » | **3** : le test « refus avec séries » passe par la violation C-3 (D12a) |
| Item hors réserve | **caduc par AM-10** (option A du 29/09) |
| R-15 : liens d'empreinte dans `verify_chain` | dans `verify_producer_inputs`, appelée juste après (D5), fichiers re-hachés |
| R-17 : inscription de l'évaluation différée | **non implémentée** (D7, trou de texte) |

### Lot 2 (`lot2_producteur/README.md` § 4-5)

| Critère ou item | Constat |
|---|---|
| « 0 xfail dans toute la suite » | 0 hors le caduc déclaré |
| Hors réserve : « `cb.build_pair` dans le `try` de 10b » | garde **à son site**, avant le moteur (D2) |
| Diff des tests : marqueurs, interface, fixtures | plus un test vert modifié (D1), deux tests de `test_c3_select.py` (D11), `REAL_CARRIERS_L1` et `_carry` (D8) |
| R-19 : le témoin continuité « reçoit le porteur » | non : sans premier remplissage, il ne déclare pas de compte (D8) |
| R-19 : recoupements « continuité ou verdict » | au verdict seul (D9) |
| R-20 : `c3b_prefix.py:395-406` | intouché : rien à y changer |

### Lot 3 (`plans/lot3.md` § 1-2)

| # | Écart | Ce qui le couvre |
|---|---|---|
| K1 | La conformité rejoue les **quatre temps**, pas seulement l'évaluation comme le 4b C3b : sous v2.2, `c3_anchor` refuse le manifeste v2.1 et le registre v2.1 | attendu § 4 |
| K2 | « Manifeste + λ, `metrics.executions`, `_quote`, `candles_eval.json` » : seules `family`, `min_order_quote` et `protocol_sha256` sont des clés du manifeste. Le reste, ce sont des contrats d'artefact, vérifiés par les codes de la chaîne | `manifest_check.out` |
| K7 | « v2.2 en exige trois » (brief) : aucune ancre au protocole ni aux amendements v2.2. Trois exécutions tenues quand même | grep au plan |
| K8 | « `scripts/audit/` change, l'option 2 du § L.5 est indisponible » (brief) : la liste de l'option 2 ne nomme pas `scripts/audit/`, et `git diff fe82fe5 5f61ac9` est **vide** sur tous ses chemins. **L'option 2 est donc aussi remplie**, avec les rejeux de `fe82fe5` (porte C3b du 28/09). L'option 1, demandée, est tenue en plus | constaté au plan par `git diff --stat`, non versionné en `.out` |
| K11 | La phrase de non-lecture est écrite avec sa portée, pas dans l'absolu | première ligne, § 8 |
| K12 | Règle d'or 10 : aucune suite locale dans ce lot. La suite verte de `5f61ac9` vaut, puisque le code est identique (`interdits`), avec la CI verte à chaque SHA | § 2 |
| D1 | Run au **SHA S1** (`08cba3d`), pas à `5f61ac9` : le manifeste est versionné dans l'arbre du run, et le pilote est exécuté depuis le clone | GO |
| D3 | « sha256 des artefacts des trois exécutions » → **booléens seulement**. Un sha d'artefact du chemin sélection est un engagement brute-forçable | GO |
| D4 | `--workers` 4 / 1 / 4 au préfixe, pas la lettre du « même run » | GO |
| D5 | Porte § L.5 au **SHA S2**, et non au SHA final ; invariance jusqu'au tip prouvée par `interdits_S3.out` | GO ; § 7.2 |

**Écarts au plan du lot 3**, ajoutés en chemin et déclarés au STOP 1 :
- `tests/pilot_dryrun.sh` : les deux pilotes exercés en local dans un monde simulé ;
- `tests/interdits_adverse.sh` : `interdits.sh` prouvé comme un vérificateur ;
- `lint_lot3.sh` : il contrôle aussi la syntaxe bash (`bash -n`) ;
- les témoins de `verify_adverse.sh` sortent de la simulation du pilote, et non d'un heredoc écrit à la main.

## 5. Candidats v2.3, consolidés (consignés, rien d'implémenté « en convention »)

| Origine | Candidat |
|---|---|
| lot 1, **D7** | **Évaluation différée — prérequis probable avant campagne.** Le texte ne dit pas d'où `c3_verdict` tire la date déclarée et le manifeste attendu. Une famille close par une issue qui ouvre la voie de sortie prospective du § 10.1 refuserait tout, évaluation différée comprise. Mini-amendement à trancher en conversation manifeste, avant la campagne |
| lot 1, D3 | abstention où l'étape 3 n'a publié aucun λ pour la configuration évaluée : quelle configuration, et quels recoupements |
| lot 1, D6 | inscription au registre à l'étape 6 hors `chain` (le verdict seul ne porte pas de registre) |
| lot 1, D14 | les sorties code 1 et 2 ne laissent aucune trace au registre : trou dans l'application du « zéro retry », couvert par la discipline et non par le registre |
| lot 2, D3 | le code de sortie du producteur qui écrit la forme de refus (0) n'est pas dans la table du § I.1 |
| lot 2, D6 | forme de refus en abstention → R0 (lettre de C-1), asymétrique avec la route exécutée |
| lot 2, D7 | `E_NO_BENCHMARK` constaté sous une raison prioritaire (`P_PROVENANCE`) : `motif` nul |
| brief | nom de test périmé `…_n_est_pas_rejouable_sous_v21` (`test_c3_entry.py:709`) |

## 6. Défauts du chantier, dits comme tels

### 6.1 Lots 1 et 2 (repris des README, § 6)

**Lot 1**
1. Prédiction D12b fausse : l'item hors réserve n'est pas passé en XPASS au commit R-21. La règle d'arrêt a joué, et
   le lot a repris sur l'option A.
2. Prédiction D8 partiellement fausse : M3 était tué aussi par le test R-18 « refus avec séries ».
3. Mes scripts de preuve étaient d'abord faux :
   - `xfail_reste.sh` comptait les occurrences au lieu des tests ;
   - `comptes.sh` portait un contrôle factice ;
   - `mutants_lot1.sh` attendait une survie.

   Tous ont été corrigés avant d'être consignés.
4. Un patch C4 a été appliqué à moitié (ancre non unique).
5. Fixture `nav` par défaut trop étroite.
6. Une sonde temporaire a été posée dans `tests/`, puis retirée.

**Lot 2**
1. Un `ruff format scripts/audit/` a reformaté six fichiers `rejeu_*` dans l'arbre de travail, dont
   `rejeu_common.py`, interdit. Je les ai restaurés avant tout commit.
2. T14 n'avait pas de mutant au plan : L2M17 a été ajouté après coup.
3. Les scripts de vérification annoncés au commit 0 n'y étaient pas.
4. Le plan annonçait 13 mutants ; il y en a eu 19. **Le README du lot 2 écrit « dix-huit »** : erreur de compte
   constatée à la clôture, déclarée ici, sans retoucher ce README (liste close de S3).
5. Une variable non découpée sous zsh.
6. Un premier appel de `ci_status.sh` avec un SHA court.

### 6.2 Lot 3

1. **`interdits_adverse.sh`, premier passage : témoin rouge.** Mon propre harnais contenait le mot que le contrôle
   « dette 23 » d'`interdits.sh` attrape. J'ai corrigé le harnais (le mot est construit à l'exécution), sans élargir
   l'exception d'`interdits.sh`. Le témoin a joué son rôle.
2. **`pilot_dryrun.sh`, premier passage.** Mon script copiait le manifeste avant d'avoir créé son répertoire dans le
   clone simulé. La garde du pilote a refusé, à juste titre (arbre non committé).
3. **Deux fragilités du pilote, trouvées par la simulation avant S1.**
   - `wc -l` remplit de blancs sous macOS (`dirty=       0`) : normalisé par `tr -d ' '`.
   - Un lien symbolique (`/var` → `/private/var`) faisait échouer la garde « pilote du clone » : la garde résout
     maintenant les deux côtés par `realpath`.

   Sans la simulation, la seconde aurait pu refuser le lancement sur un serveur où un chemin passe par un lien.
4. **`verify_attendu.py` : `ruff format --check` rouge au premier passage.** Le formateur est interdit dans ce lot :
   j'ai lu le diff par `--diff` et je l'ai appliqué à la main.
5. **Commandes shell.**
   - Un `cd` dans une commande composée a déplacé le répertoire courant de l'outil, sans effet.
   - Un motif glob sans correspondance sous zsh a interrompu une commande de lecture, relancée ensuite.
6. **La simulation locale tourne sous `bash` 3.2**, et le serveur sous 5.2. Seules des constructions portables ont été
   employées, dont `${arr[@]+"${arr[@]}"}` pour le tableau éventuellement vide.
7. **`PROJECT_CONTEXT.md` § 8** porte encore « suite : outillage v2.2, puis manifeste » (l.458). Le plan limitait
   l'édition de ce fichier au § 1. La ligne est listée au § 9 pour le merge.

## 7. Preuves serveur

Les deux phases ont tourné en lecture seule. `alembic` était à `c3bd1e7a0001 (head)` avant et après, le service à
`8689636` sans ligne sale, et le collector actif avec `NRestarts=0`, tous inchangés.

Environnement : l'interpréteur du venv du service (Python 3.12.3, pytest 9.0.2), avec `env PYTHONPATH="$REPO/src"`
sur chaque invocation, `bash -lc` sous tmux. Pas de `set -e`, pas de `kill`, pas de relance.

### 7.1 Conformité sous v2.2 (`conformite/`)

- **Attendu** : `conformite/attendu.md`, committé à S1 avec l'entrée 19. Bruno l'a relu (STOP 1), et son GO de
  lancement nomme S1 ; la question posée avant ce GO sur les motifs `grep` a reçu sa réponse (identiques au 4b, déjà
  éprouvés sur le rendu serveur).
- **Préalables à S1**, tous à `rc=0` :
  - `manifest_check.out` : 7 chemins changés, exactement ; `c3_anchor` local 0 ; `T` attendu ;
  - `events.out` : liste close = code, 54 noms ;
  - `pilot_dryrun.out` : 6 simulations ;
  - `verify_adverse.out` : 2 témoins à 0 ; 22 + 15 cas déviés à 1, chacun avec un seul item en écart ;
  - `lint_lot3.out`.
- **Run** : un seul, au SHA **`08cba3d966aaf517c251a076fb7b6c60f88470c6`**, le 2026-09-30 de **07:10:19 à
  07:14:28Z**. Pilote `5a2cc18d…` exécuté depuis le clone. Code du pilote : **0**.
- **`verify_attendu.out`** : **10 items vérifiables sur 10 tenus**, `rc=0`.

  | Item | Mesuré |
  |---|---|
  | Gardes | `guard=0` au SHA S1, `krakenbot` du clone, protocole v2.2, manifeste `c3769a6a…`, `CAMPAIGN_UNLOCK` absent |
  | Trois exécutions (workers 4 / 1 / 4) | préfixe 0 ; `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select` en 0 ; `c3b_evaluate` **`0 event=evaluated`** ; `chain` 0 avec **`anchor:0,entry:0,benchmark:0,select:0,continuity:0`** ; **`chain.verified` vrai, violations vides, zéro violation au rejeu** ; interpréteur du clone |
  | Déterminisme | **23 artefacts identiques au bit sur les trois exécutions** (`compared=23 differing=0 absent=0`), liste attendue exacte |
  | Base, service | inchangés ; arbre du clone propre |

- **Durées** (bornes `start_<K>` / `end_<K>`) : 53 s à 4 workers (exécutions 1 et 3), 2 min 20 s à 1 worker (exécution 2).
- **Archive** : `~/archive/c3_outillage_conf_20260930/c3_outillage_conf_server_20260930.tgz`, 139 fichiers, sha256
  `17a1e6e84a0766b3c373f6f11e6176ceca30c317f73f71a03ad9c2010a380211`. Vérifiée par codes seulement : liste, 0 entrée
  `repo/` ou `.env`, `sha256sum -c`, extraction et `diff -rq`, `cmp` du pilote, `sha256sum -c` de l'extraction.
  **`rm -rf` à 07:15:05Z.**
- **Issue non lue.**
  - Par construction, `validé` et `réfuté` sont inatteignables, parce que la provenance est `unknown` et que
    `P_PROVENANCE` est au rang 2 du § H.1.
  - L'inscription au registre est non comptée, dans des registres jetés avec l'archive.
  - Rien du chemin sélection n'a été ouvert, listé ni mesuré. Seul le sha de l'archive a été imprimé.

### 7.2 Porte § L.5, option 1 (`gate_L5/`)

- **SHA testé** : **`4089fd5c657be64a569c012964fd7de4aed0b52e`** (S2, D5), CI verte (run 36682922620).
  - Pilote `gate_L5/run_gate.sh` (`00f26878…`) : c'est celui de C3b (`be071fff…`), avec quatre écarts déclarés en
    tête (SHA en argument, exécuté depuis le clone, `service_before/after`, `RUN`).
- **Fenêtre** : 2026-09-30, **07:25:15 → 08:36:55Z (71 min 40 s)**. Code du pilote : **0**.
- **Résultat** : `full=0`, les **24 combos en `rc=0` avec un JUnit `1/0/0/0`**, et l'agrégat
  `junit_total=tests:24,failures:0,errors:0,skipped:0,missing:0`.
  - `verify_gate.out` : **6 items sur 6 tenus**. Le vérificateur avait été prouvé avant, et le faux vert « module
    skippé » y est un cas dévié.
  - Durées `call` (s) : 243,43 · 245,05 · 198,07 · 54,80 · 54,88 · 43,77 · 57,85 · 57,54 · 46,60 · 50,73 · 49,05 ·
    39,01 · 53,11 · 52,96 · 42,58 · 333,28 · 337,96 · 255,74 · 318,14 · 318,79 · 243,43 · 413,72 · 415,82 · 314,66.
    C'est le profil des portes précédentes (C3b le 28/09 : 71 min 17 s).
- **Non-lecture** : journaux et JUnit (`--showlocals`) en fichiers seulement, archivés. N'ont été rapatriés que
  `status.txt`, `pytest_summary.txt` (ligne `call` et ligne de résumé), `pilot_exit.txt` et les deux `alembic`.
- **Archive** : `~/archive/c3_outillage_gate_20260930/c3_outillage_gate_server_20260930.tgz`, 56 fichiers, sha256
  `1908f2a7d13e0fa39615a0ea81e9657a86948fe266eb9dce2c5125d0a2a73087`. Vérifiée par codes. **`rm -rf` à 08:41:21Z.**
- **`postflight.out`** (`rc=0`) :
  - `~/runs/c3_outillage` absent, aucune session tmux du chantier ;
  - les deux archives passent `sha256sum -c` ;
  - `CAMPAIGN_UNLOCK` absent de l'arbre du service ;
  - collector actif, `NRestarts=0` ; service `8689636`, 0 ligne sale.
- **Invariance jusqu'au tip.** Après S2, seuls changent `results/c3_outillage_v2_2/`, `docs/RESEARCH_LOG.md`,
  `PROJECT_CONTEXT.md` et `results/INDEX.md`. Le code est identique à `5f61ac9`, comme le prouve `interdits_S3.out`
  (diff vide et liste blanche). La porte jouée à S2 vaut donc pour le tip, sans rejeu (précédent C2 / C3b). L'option
  2 est aussi remplie (K8).

## 8. Tunnel, base, lint, interdits, limites

- **Tunnel** (`tests/tunnel.out`).
  - Lots 1 et 2 : ouvert pour les 13 tests base de la suite existante (lecture seule), fermé et vérifié fermé en fin de
    lot.
  - Lot 3 : **jamais ouvert**. Il a été constaté fermé au premier geste après le GO (21:50:28Z le 29/09), puis avant
    STOP 2.
- **Aucune migration.**
- **Lint et typage.**
  - Lots 1-2 : ruff (liste CI et dépôt) vert, `mypy src/` = 65, mypy strict sans écart neuf.
  - Lot 3 : `lint_lot3.out`, en vérification seulement, aucun formatage.
- **Interdits** (`tests/interdits_*.out`, tous `rc=0`) : diff vide contre `8c114fe` sur `src/`,
  `scripts/backtest.py`, les runners, `rejeu_common.py`, le protocole, les amendements, `results/c3_v2_2/` et
  `results/c3b_producteur/`. Au lot 3, s'ajoutent :
  - le bloc contre `5f61ac9` ;
  - la liste blanche des fichiers changés ;
  - aucun artefact du chemin versionné ;
  - `CAMPAIGN_UNLOCK` absent ;
  - aucun script qui nomme le répertoire de la dette 23.

**Limites**
- **Les 24 `_full`** sont des backtests P6 (USDC, défauts de classe, 2023-04 → 2026-04) comparés par hash. Ce ne sont
  pas des runs du producteur. Ils lisent la période de campagne sur d'autres séries ; aucune métrique n'est lue.
- **Les 13 tests base des lots 1-2** ont lu la base par le tunnel, en lecture seule. Aucune métrique de candidat n'en
  a été lue.
- **La phrase de la première ligne repose sur trois appuis** : le code, les tests et les codes de la chaîne (attendu
  § 7). Ce n'est pas un journal de requêtes Postgres.
- **Le chemin sélection ne traverse `c3_verdict` qu'au serveur.** Le monde synthétique n'a aucun candidat estimable
  au préfixe : c'est un candidat de clôture C3b, toujours ouvert.
- **La preuve de départ à plat vaut DÉCLARÉ**, jamais plus (§ B.2).
- **R-17 : le registre de campagne unique et persistant n'existe pas encore.** Les runs de conformité utilisent des
  registres jetés. L'inscription de l'évaluation différée n'est pas outillée (D7, § 5).

## 9. Ce qui attend

- **Merge par Bruno**, après relecture de ce rapport. Puis `docs/CODE_MAP.md` régénéré au merge, et
  `git pull --ff-only` du serveur : le service est à `8689636`.
- **Lignes périmées hors de la liste close du chantier**, pour le merge (D6 : Bruno les corrige) :
  - `CLAUDE.md` l.17 : « suite : outillage v2.2 …, puis manifeste » ;
  - `CLAUDE.md` l.44 : « v2.2 pas encore outillée, 46 `xfail` strict » ;
  - `CLAUDE.md` l.45 : « suite : outillage v2.2, puis manifeste » ;
  - `CLAUDE.md` l.56 : « ces règles ne sont pas encore outillées » ;
  - `skills/backtest.md` l.543-547 : « L'outillage suit encore v2.1 … portées par 46 tests `xfail` strict » ;
  - `PROJECT_CONTEXT.md` l.458 (§ 8) : « suite : outillage v2.2, puis manifeste ».
- **Conversation manifeste**, avant la première campagne comptée :
  - **D7 v2.3 (évaluation différée) à trancher** ;
  - le registre de campagne persistant ;
  - `CAMPAIGN_UNLOCK`, créé par Bruno ;
  - le capital représentable ;
  - `min_order_quote` réel Bybit ;
  - les 8 estampilles 1 w dérivées ;
  - `decision_timeframes` par candidat ;
  - la famille réelle ;
  - les dettes 21 (`--campaign`) et 24 (spread et slippage).
- **Candidats de clôture, hors chantier** : marqueur `db` ; `test_rejeu_effect` instable (sous-chaîne « 1.645 ») ;
  monde synthétique estimable ; fabrique en `Decimal` ; `git_provenance` étendue.
