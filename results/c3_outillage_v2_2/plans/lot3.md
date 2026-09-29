# C3 — Outillage v2.2, lot 3 (conformité serveur sous v2.2, porte § L.5, clôture) — plan soumis au GO

> Plan rédigé en plan mode, approuvé le 2026-09-29 (GO en § 0), recopié tel quel par le commit C0. Rien n'a été écrit
> en git ni lancé sur le serveur avant le GO ; **rien ne tourne sur le serveur avant STOP 1**.

## Contexte

Dernier lot du chantier `agent/AGENT_C3_OUTILLAGE_V2_2.md`, sur `feat/c3-outillage-v2.2` au tip `5f61ac9`
(`5f61ac928ef4edf914b863d300a5d0859d028f99`, arbre propre, lots 1-2 livrés et poussés, aucun merge). La porte du
chantier n'est pas « 0 xfail » : c'est **la conformité du producteur rejouée sous v2.2 sur le serveur** (§ J item 12 :
elle ne se prouve pas en local), puis la porte § L.5 option 1, puis la clôture documentaire. **Ce lot n'écrit aucun
code** (ni `scripts/`, ni `tests/`, ni `src/`). Il écrit un manifeste, un attendu, deux pilotes, des scripts de
contrôle `results/c3_outillage_v2_2/tests/*.sh` avec leurs sorties, et un rapport. Tout besoin de code découvert est un
STOP.

## 0. GO reçu (29/09, Bruno) — conditions intégrées ci-dessous

**D1 à D7 accordés tels que recommandés.**
- **D3, précision** : un sha d'artefact du chemin sélection est un engagement brute-forçable sur un petit espace
  d'hypothèses (12 candidats, issues finies). C'est la leçon des 336 octets, généralisée. Les sha du manifeste, des
  pilotes et des archives sont sûrs (une archive porte journaux et durées, irreconstructible). Booléens partout
  ailleurs. L'alternative « sha du préfixe » est rejetée, par uniformité.
- **D4** : si `eq3` casse entre le run 2 et les runs 1/3, c'est une dépendance d'ordonnancement réelle dans le code
  du lot 2, et le STOP est mérité.
- **D6** : les lignes périmées de CLAUDE.md et `skills/backtest.md` sont listées au rapport. Bruno les corrige au
  merge, avec `CODE_MAP`.

**Condition ajoutée (règle agent 1) : les vérificateurs sont prouvés avant de servir.** `verify_attendu.py` et
`verify_gate.sh` décident « attendu tenu » ; un défaut dans l'un d'eux laisserait passer une déviation. Avant leur
premier usage, chacun est exercé sur des cas fabriqués, et la sortie est committée (`tests/verify_adverse.sh` → `.out`,
§ 7) :
- un **témoin sain**, lui-même conforme à tout l'attendu (règle agent 2), doit rendre `rc=0` ;
- chaque **cas dévié** (une seule ligne écartée par cas) doit rendre `rc≠0`.

Pour la conformité, c'est fait avant S1. Pour la porte, avant le lancement de la porte ; en pratique aussi à S1,
puisque `verify_gate.sh` y est écrit.

**Confirmations à l'attendu** (le plan les impliquait) :
- le **même `--now`** sur toutes les invocations qui l'acceptent, les trois exécutions comprises : c'est ce qui rend
  `verdict.json` et les deux `variants.json` comparables au bit ;
- **K11 tel quel** : la phrase de non-lecture avec sa portée.

**STOP 1 inchangé** : Bruno relit l'attendu au SHA S1 complet avant tout lancement.

## 1. Constats de lecture qui fixent le plan (déclarés, pas arbitrés)

| # | Constat | Appui | Effet sur le plan |
|---|---|---|---|
| K1 | Le 4b C3b n'a **pas** rejoué le préfixe. Il a consommé les sorties versionnées du lot 3 : manifeste v2.1, `anchor`, `selection`, `benchmark`, `observations`, `coverage`, registre, et `candles.json` archivé. Sous v2.2, `c3_anchor` refuse ce manifeste (sha v2.1, pas de `family`). Le registre v2.1 fait refuser toute clé neuve (code 2, enregistrement sans `family`, `c3_anchor.py:170`). Et `observations.json` porte `min_order_usdc` / `gross_usdc`, refusés par `c3_entry` (R-16). | `eval_f2_conformite/ATTENDU.md` § « Entrées » ; `outillage_v2_2.md` R-16 / R-17 « artefacts non conformes » | La conformité v2.2 rejoue **les quatre temps** : `c3b_prefix` → `c3_anchor/entry/benchmark/select` → `c3b_evaluate` (chemin sélection) → `c3_verdict chain` (six étapes). Le lot 3 C3b et le 4b C3b sont fondus en un seul pilote. **Aucun fichier de `results/c3b_producteur/` n'est lu** par le pilote. |
| K2 | Seules trois clés du manifeste changent pour v2.2 : `family` (chaîne non vide, `c3_common.py:1438`), `min_order_quote` (nombre, `:1434` ; l'ancienne `min_order_usdc` retirée, sinon elle resterait silencieusement dans l'empreinte) et `protocol_sha256` (v2.2, asserté par `c3_anchor`). Les λ déclarés (`evaluation.lambdas`), `metrics.executions`, les clés `_quote` des artefacts et la septième entrée `candles_eval.json` sont des **contrats d'artefact et de chaîne**, portés par le code du tip. | cartographie de `load_manifest` à `5f61ac9` | L'attendu ne les écrit pas au manifeste. Il les vérifie par les codes : admission R-19, formes R-16, recoupements R-15 à l'étape 6. |
| K3 | `anchor.json` et `entry.json` embarquent le **chemin** de leurs entrées (registre, observations, couverture). | `c3_anchor.py:309`, `c3_entry.py:778,797` | Trois exécutions dans trois répertoires différents ne seraient pas identiques au bit, pour une raison bénigne. Chaque exécution tourne donc au **même chemin absolu** `$RUN/work/`, renommé en `out/run<K>/` après coup (`mv` sur le même système de fichiers, contenu intact). |
| K4 | Les provenances portent `duration_s`, et les journaux sont horodatés : `prefix_run.json`, `prefix/partial/*.json`, `evaluation_run_provenance.json`. | `c3b_prefix.py:136,440` ; `c3b_evaluate.py:917,1229` | Ces fichiers sont **exclus de l'égalité au bit**, comme le 28/09, et l'exclusion est déclarée. Leur seul contrôle est le booléen « interpréteur du clone ». |
| K5 | Les journaux portent des identités (`job_done identity=…`), la paire (le moteur) et les sha des écrits (`written … sha256=…`, `c3b_evaluate.py:1244`, `c3_verdict.py:1882`). | code | Journaux **en fichiers seulement** : ni `tee`, ni écran, ni listing, ni taille. |
| K6 | Avec la provenance `unknown`, `P_PROVENANCE` est au rang 2 du § H.1 (`c3_common.py:567-581`). `validé` et `réfuté` sont inatteignables, et aucune raison de rang inférieur (dont `E_NO_BENCHMARK`) ne peut être celle qui est publiée. L'inscription au registre du run est donc non comptée. | cartographie ; lot 2 D7 | C'est le constat hérité n° 1, écrit à l'attendu sans effet sur les codes. Registre **neuf par exécution** : partagé, il consommerait la relance unique de la famille. |
| K7 | « v2.2 en exige trois » (brief l.195) n'a **aucune ancre** dans `docs/protocole_c3.md` ni dans `docs/amendements_c3_v2.2.md` : `grep` sur « trois ex », « déterminis », « exécutions de référence » ne rend rien. | grep | Trois exécutions restent exigées par le brief, et elles sont tenues. Le rapport le consigne en écart au brief. |
| K8 | Le brief (l.196-197) dit l'option 2 du § L.5 indisponible « parce que `scripts/audit/` change ». Or la liste de l'option 2 (§ L.5, l.2264-2266) ne nomme pas `scripts/audit/`, et `git diff fe82fe5 5f61ac9` est **vide** sur tous ses chemins (mesuré). | § L.5 ; `git diff --stat` | L'option 1 est demandée, et elle est tenue. Le rapport écrit les deux constats : la justification du brief est inexacte, et l'option 2 serait aussi remplie. C'est déclaré, sans substitution. |
| K9 | `docs/RESEARCH_LOG.md` : « Toute campagne ou run … inscrit ici **avant son lancement** ». Le prompt place l'entrée 19 en clôture. | journal, l.3 | Voir D2. |
| K10 | `5f61ac9` ne contient pas le manifeste v2.2 dans son arbre, et le producteur exige un arbre suivi propre (`uncommitted_tree`). | `_common.py:111-129` | Voir D1. |
| K11 | La phrase « aucune donnée de la fenêtre de campagne n'a été lue » est fausse **sans sa portée**. Les 24 `_full` de la porte lisent des bougies USDC 2023-04 → 2026-04, et les 13 tests base des lots 1-2 ont lu par le tunnel. | C3b `report.md` § 5 (précédent) | La phrase est écrite en tête du rapport avec sa portée (producteur et chaîne). Les deux exceptions vont en § Limites : comparaison par hash, aucune métrique lue. |
| K12 | CLAUDE.md, règle d'or 10 (« `pytest` + `ruff` verts avant tout commit ») : le lot ne lance aucune suite locale (pas de tunnel). | prompt | La suite verte de `5f61ac9` vaut pour ce lot, parce que le code est identique : `interdits.sh` le prouve (diff vide sur `scripts/ tests/ src/ config/ pyproject.toml poetry.lock .github/`). La CI est lue verte à chaque SHA poussé. `ruff check` et `ruff format --check`, **sans correction**, tournent sur les seuls `.py` du lot. |

## 2. Décisions demandées au GO

| # | Question | Recommandation et motif |
|---|---|---|
| D1 | À quel SHA tourne la conformité ? Le prompt dit `checkout --detach 5f61ac9`. | **Au SHA S1**, le commit qui porte l'attendu, le manifeste, les pilotes et l'entrée 19. C'est le précédent C3b (lots 3, 4a, 4b : « exécuté au commit de cette entrée »). Le code de S1 est identique à celui de `5f61ac9`, prouvé par `interdits_S1.out` (diff vide sur les chemins de code). Le manifeste est alors versionné et haché dans l'arbre que lit le producteur. **Amélioration sur le précédent** : le pilote est versionné à S1 et **exécuté depuis le clone**. Le pilote qui tourne est celui du commit, sans `scp`, et son `pilot_sha256` égale celui du blob git. L'alternative (`5f61ac9`, avec un manifeste transporté hors arbre) laisse le manifeste hors de l'arbre versionné du run. |
| D2 | Où va l'entrée 19 du journal ? | **À S1, avant le lancement** (règle du journal, et précédent des entrées 15 à 17). L'« Issue de l'entrée 19 » est ajoutée en clôture, sans réécrire l'entrée. |
| D3 | « sha256 des artefacts des trois exécutions » : que remonte au dépôt ? | **Des booléens seulement**, par artefact (`eq3 <nom>=0`) et en agrégat (`bit_equal_3of3=0 compared=23`). Les sha restent dans l'archive serveur (`files_all.sha256`, jamais affiché). Un sha versionné d'un artefact du chemin sélection est **comparable** : à une évaluation désignée de chaque candidat BTC/ETH sur la même fenêtre, ou à un registre reconstruit pour chaque issue possible. Il dirait le retenu ou l'issue (règle de non-lecture, leçon des 336 octets). Les sha versionnés sont ceux du manifeste (une entrée), des pilotes, des archives et des HEAD. Alternative : sha des trois sorties du préfixe versionnés comme le 28/09, booléens en aval. |
| D4 | « Trois exécutions du même run » : mêmes options partout ? | **`--workers` 4, 1, 4 au préfixe**, et tout le reste identique. Le critère unique reste l'égalité au bit sur les trois. Le lot 2 a changé `c3b_common` (export) ; une exécution à un worker re-prouve l'indépendance à l'ordre des jobs (lot 3 C3b, sous v2.1) pour environ 1 min 30 de plus. L'alternative, 4 / 4 / 4, est la lettre de « même run ». |
| D5 | À quel SHA tourne la porte § L.5 ? | **Au SHA S2** (preuves de conformité), puis S3 porte le rapport complet, porte comprise. De S2 à la fin, seuls `results/`, `docs/RESEARCH_LOG.md`, `PROJECT_CONTEXT.md` et `results/INDEX.md` changent : c'est prouvé par `interdits.sh` et par la liste blanche des fichiers changés, sur le précédent C2 / C3b de l'invariance d'un commit de preuves. L'alternative est l'ordre C3b : le rapport d'abord, la porte à ce SHA, puis ses preuves « au commit suivant », avec un rapport qui n'en parle pas. |
| D6 | Docs hors de la liste close devenues fausses : CLAUDE.md (« v2.2 … ces règles ne sont pas encore outillées », « v2.2 pas encore outillée, 46 `xfail` strict »), `skills/backtest.md` § « Validation C3 ». | **Non touchées**, parce que la liste close du brief se limite à `PROJECT_CONTEXT`, `RESEARCH_LOG` et `INDEX`. Le rapport les liste ligne par ligne pour le merge, et `interdits.sh` les tient intactes. |
| D7 | Que faire du serveur si un code s'écarte de l'attendu ? | **Rien.** Le répertoire `~/runs/c3_outillage/<phase>/` reste en place, sans archive ni `rm`. Seuls `status.txt`, `pilot_exit.txt` et les deux `alembic` remontent. Un constat est versionné, puis STOP. Bruno décide de toute lecture de diagnostic, de l'archive et du nettoyage (précédent 4b : « `status.txt` seul, puis STOP »). |

Valeurs déclarées, sans décision : famille `"test-conformite-instrument-2020"` (valeur de test, jamais une famille de
campagne) ; `variant_id` `"c3-outillage-v22-conformite-2020"` ; `--campaign OUTILLAGE_V22_CONF`, étiquette
d'instrument (dette 21 intacte, comme `C3B_LOT4B`) ; `--now` fixe, le même partout (`<date de S1>T00:00:00+00:00`).

## 3. Commits (branche assertée avant chacun, message par `-F`, `interdits.sh <label>` avant chacun)

| Commit | Contenu | Poussé | CI |
|---|---|---|---|
| **G0** (pas un commit) | premier geste après le GO : `bash tests/tunnel.sh state` (fermé attendu) | — | — |
| **C0** `docs(results)` | `plans/lot3.md` (ce plan, GO inclus) ; `tests/interdits.sh` étendu (§ 7) ; `interdits_C0.out` ; `tunnel.out` (ligne de G0) | non | — |
| **S1** `docs(research)` — **SHA du run** | `conformite/manifest.json`, `conformite/attendu.md`, `conformite/server/run_conformite.sh`, `conformite/server/verify_attendu.py`, `gate_L5/run_gate.sh`, les scripts de § 7, `tests/manifest_check.out`, `tests/events.out`, `tests/lint_lot3.out`, **`tests/verify_adverse.out`** (condition du GO), `interdits_S1.out` ; `docs/RESEARCH_LOG.md` entrée 19 (avant lancement) | oui | `ci_status_S1.out` |
| **STOP 1** | Bruno relit l'attendu au SHA S1 (complet), avec le pilote et le manifeste → **GO de lancement** nommant S1 | | |
| **S2** `docs(results)` | preuves de conformité : `conformite/server/{status.txt, pilot_exit.txt, alembic_before.txt, alembic_after.txt, verify_attendu.out, <archive>.tgz.sha256}`, `tests/{preflight,launch,wait,fetch,archive}_conf.out`, `ci_status_S1.out`, `interdits_S2.out` | oui | `ci_status_S2.out` |
| porte § L.5 au S2 (D5) | | | |
| **S3** `docs(results)` | preuves de la porte (`gate_L5/{status.txt, pilot_exit.txt, alembic_*.txt, pytest_summary.txt, <archive>.sha256}`, `tests/*_gate.out`, `verify_gate.out`, `postflight.out`) ; `report.md` ; `PROJECT_CONTEXT.md` ; `docs/RESEARCH_LOG.md` (issue de l'entrée 19, et ajout aux « Essais à venir ») ; `results/INDEX.md` ; `interdits_S3.out` ; `tunnel.out` (état fermé) | oui | `ci_status_S3.out` |
| **S4** `docs(results)` | `ci_status_S3.out` (précédent `5f61ac9`) | oui | lue, citée au message de STOP 2 |
| **STOP 2** | fin du chantier ; **merge par Bruno** après relecture | | |

## 4. Livrable 1 — `results/c3_outillage_v2_2/conformite/attendu.md` (contenu)

En tête : « Fenêtre d'instrument, aucune lecture économique, issue non lue ». Écrit et committé à S1 avec l'entrée 19 ;
le run se fait au SHA de ce commit.

1. **Fenêtre** : `2020-01-06T00:00Z → 2020-12-28T00:00Z`, `F = 0,70`, `T = 2020-09-11T21:36:00Z`. Provenance
   `unknown`. Le garde-fou 6 passe par construction : fin < 2021-03-01, et `CAMPAIGN_UNLOCK` est absent, jamais créé,
   asserté par le pilote avant et après.
2. **Manifeste** : celui du 28/09 (`prefix_conformite/manifest.json`, `d96ed10d…`) plus les seules clés v2.2 (K2).
   Les chemins changés sont listés et vérifiés par `tests/manifest_check.sh` (sortie `.out`) :
   - `family` ajoutée ;
   - `min_order_usdc` → `min_order_quote: 5.0` ;
   - `protocol_sha256` → `1bed7696…292a` ;
   - `variant_id`, `research_log_entry` (entrée 19) et `run_scope` réécrits.

   Capital `"1000"` inchangé, représentable en float. Univers inchangé (12 candidats), graine inchangée. Le sha256 du
   manifeste est déclaré. Il est validé en local, avant S1, par `c3_anchor` seul (pur, sans base, registre et sortie
   dans le scratchpad) : code 0 et `T` attendu, consignés.
3. **Registre** : neuf **par exécution**, sous sa sortie, jamais un registre persistant.
   - `c3_anchor` autonome écrit `work/pre/variants.json`, un registre vide qui reçoit la racine.
   - `chain` reçoit une copie `work/chain/variants.json`. L'étape 1 y est idempotente (`RECORD_KEYS`, même manifeste
     au bit), puis l'étape 6 y inscrit l'issue, une fois. C'est le chemin du 4b.
   - Les deux fichiers sont archivés et jamais lus : après l'étape 6, ils portent l'issue.
4. **Ce qui tourne**, trois exécutions `K = 1, 2, 3` (workers 4 / 1 / 4, D4), chacune dans `work/`, puis renommée
   `out/run<K>/` :
   `c3b_prefix` → `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select` (autonomes, `work/pre/`) → `c3b_evaluate
   --selection` (`work/eval/`) → `c3_verdict.py chain`, avec les neuf entrées (`--candles-eval`, `--benchmark-eval`
   compris) et `--registry work/chain/variants.json` (`work/chain/`).
5. **Liste close de ce qui remonte**, avec l'attendu (tout le reste est archivé, jamais versionné ni ouvert) :

   | Clé de `status.txt` | Attendu | Dérivation |
   |---|---|---|
   | `guard` | `0`. Gardes : HEAD = S1 (complet), arbre suivi propre, `poetry.lock` et `pyproject.toml` égaux au service, `krakenbot` résolu vers le clone, `.env` présent, sha du protocole du clone = v2.2, sha du manifeste = déclaré, `CAMPAIGN_UNLOCK` absent, `work/` absent | règles serveur |
   | `pilot_sha256` | égal au sha du blob à S1 | D1 |
   | `alembic_before`, `alembic_after` | `0`, deux fichiers identiques, `c3bd1e7a0001 (head)` | aucune migration |
   | `service_before`, `service_after` | HEAD du service inchangé, 0 ligne sale ; collector `active`, `NRestarts` inchangé | service intouché |
   | `prefix_<K>` | `0` | 28/09 : 0 ×2 sur les mêmes données. Les changements v2.2 du préfixe (R-16 renommage, R-20 dates nullables) ne changent aucun code sur des séries toutes couvertes (le refus `coverage_no_covered_unit` de v2.1 n'y a pas joué). Code 0 ⟹ base **en lecture seule assertée par Postgres** (`probe_database`, `SHOW transaction_read_only = on`, `c3b_common.py:792-804` ; sinon `database_read_failed`, 2) ; de même pour `eval_<K>` |
   | `pre_anchor_<K>`, `pre_entry_<K>`, `pre_benchmark_<K>`, `pre_select_<K>` | `0` ×4 | lot 3 C3b : D2 en échec sur SOL (portée candidat), SOL `E_NO_BENCHMARK` au préfixe, sélection descriptive. Aucun chemin non fini n'a été atteint sous v2.1 (codes 0), donc R-21 et R-22 sont sans effet |
   | `eval_<K>` | `0 event=evaluated` (jamais `refusal_form_written`) | 4b : chemin sélection 0 `evaluated`, ce qui supposait sous v2.1 un comparateur constructible. Même retenu : les seuls changements v2.2 qui touchent la sélection sont les chemins non finis, inatteints |
   | `chain_<K>` et `chain_steps_<K>` | `0` et `anchor:0,entry:0,benchmark:0,select:0,continuity:0` : **les six codes d'étape** | 4b ; plus les recoupements R-15 (mêmes fonctions `cc.recompute_daily`, `cb.build_pair`, `cb.blend_nav` des deux côtés, vérifiés en processus par `test_the_full_chain_verifies_a_produced_evaluation`), R-19 (le retenu a exécuté : `first_fill_at` non nul au 4b), R-17 (variante présente dans la copie) ; même interpréteur, donc même environnement § F.2 (b) |
   | `chain_verified_<K>` | `true` | idem |
   | `violations_empty_<K>`, `replay_violations_empty_<K>` | `true`, `true` (booléens ; préfixes `rejeu` et `réplications`) | idem |
   | `interpreter_<K>` | `0` : les deux provenances nomment le `krakenbot` du clone | un seul environnement |
   | `eq3 <artefact>` ×23, `listing_expected_3of3`, `bit_equal_3of3` | `0` partout, `compared=23 differing=0 absent=0` | voir la liste ci-dessous |
   | `tree_after`, `campaign_unlock_after` | `0`, `absent` | |
   | `pilot_exit.txt` | `0` | |

   Les 23 artefacts comparés entre les trois exécutions sont :
   - `prefix/` : `observations.json`, `coverage.json`, `candles.json` ;
   - `pre/` : `anchor.json`, `variants.json`, `entry.json`, `entry.md`, `benchmark.json`, `selection.json`,
     `selection.md` ;
   - `eval/` : `evaluation.json`, `benchmark_eval.json`, `candles_eval.json`, `evaluation_sensitivity.json` ;
   - `chain/` : `anchor.json`, `entry.json`, `entry.md`, `benchmark.json`, `selection.json`, `selection.md`,
     `continuity.json`, `verdict.json`, `variants.json`.

   Sont exclus, et c'est déclaré : `prefix_run.json`, `prefix/partial/*`, `evaluation_run_provenance.json` et
   `logs/*` (K4). « Liste attendue » veut dire que chaque exécution porte exactement ces 23 fichiers hors exclusions,
   ni plus ni moins.
6. **Constats hérités, écrits en le sachant.**
   - (a) Provenance `unknown` : `P_PROVENANCE` précède `E_NO_BENCHMARK` au § H.1. Un comparateur non comparable
     donnerait `P_PROVENANCE` et un `motif` nul (lot 2 D7), sans effet sur les codes attendus.
   - (b) Le coin D6 (désignation, abstention et comparateur non constructible → 2) est hors chemin : on passe par la
     sélection, pas par la désignation, et le comparateur 2020 se construit (C3b l'a prouvé le 28/09 ; attendu
     `event=evaluated`).
   - (c) K6 : l'inscription est non comptée, dans un registre jeté.
7. **Bornes des lectures**, par appuis et non par mesure : le code (`candles_artefact` refuse `> fin`, lectures
   `(pair, 5 | 1440, T, fin)`, un `run(pair, T, fin)`, amorçage `≥ T − 400 j`, préfixe `≤ T`), les tests et les codes
   de chaîne (`continuity = 0` ⟹ `period = [T, fin]`). Ce n'est pas un journal de requêtes.
8. **Règle d'échec.** Tout code différent de l'attendu, `chain.verified` faux, une violation, ou trois exécutions non
   identiques : STOP. Le constat est versionné (`status.txt` seul), rien n'est relancé « pour voir », rien n'est
   corrigé, rien n'est lu pour diagnostiquer sans l'accord de Bruno (D7). Seule une panne du pilote lui-même (127,
   chemin) se relance, après correction du pilote, par un nouveau commit repassé par Bruno.

## 5. Livrable 2 — procédure serveur

**Arborescence** : `~/runs/c3_outillage/{conf,gate}/{repo,out}` (et `conf/work`, transitoire). Archives :
`~/archive/c3_outillage_{conf,gate}_<AAAAMMJJ>/`. Sessions tmux : `c3-outillage-{conf,gate}-<AAAAMMJJ>`, fermées
d'elles-mêmes à la sortie du pilote, sans `kill`. `~/docker/` n'est jamais nommé.

**Ordre, après le GO de lancement**
1. `bash tests/preflight.sh conf`, en lecture seule. Il relève :
   - le HEAD du service et ses lignes sales ;
   - l'interpréteur du venv du service ;
   - les sha de `poetry.lock` et `pyproject.toml` du service, comparés à S1 ;
   - `~/runs/c3_outillage` absent, archive du jour absente ;
   - les sessions tmux, le disque et la mémoire ;
   - le collector (`active`, `NRestarts`), le trader inactif ;
   - le `.env` du service présent ;
   - les ports 5432 ouvert et 5433 fermé ;
   - `CAMPAIGN_UNLOCK` absent de l'arbre du service.

   `rc` différent de 0 → STOP.
2. `bash tests/launch.sh conf <S1 complet>`. Il vérifie que le HEAD local, le tip de `origin/feat/c3-outillage-v2.2`
   et l'argument sont égaux, puis :
   - `mkdir` du répertoire du run (échoue s'il existe) ;
   - clone GitHub, `fetch` de la branche, `checkout --detach <S1>`, HEAD vérifié ;
   - `.env` copié du service, `out/` créé (pour que `pilot_exit.txt` s'écrive même si le pilote ne démarre pas) ;
   - sha du pilote dans le clone égal au blob local ;
   - `tmux new -d -s … "bash -lc 'bash <clone>/…/run_conformite.sh <S1>; echo \$? > <out>/pilot_exit.txt'"`.
3. `bash tests/wait.sh conf 60 40`, en arrière-plan. Il sonde l'existence de `pilot_exit.txt`, le nombre de lignes et
   la dernière ligne de `status.txt` (des codes seulement). Il ne tue rien et ne relance rien.
4. `bash tests/fetch.sh conf`, qui ne rapatrie que `status.txt`, `pilot_exit.txt` et les deux `alembic`, avec leur sha
   local comparé au distant. Puis `bash tests/verify_conformite.sh`, qui lance `verify_attendu.py` sur ces seuls
   fichiers. `rc` différent de 0 → D7.
5. `bash tests/archive.sh conf <date>`, qui archive `out/` : les trois exécutions, les journaux et la copie du pilote,
   **sans `repo/` ni `.env`**. Les contrôles, par codes seulement :
   - liste de l'archive égale à la liste des fichiers ;
   - 0 entrée `repo/` ou `.env` ;
   - `sha256sum -c` de l'archive ;
   - extraction et `diff -rq` ;
   - `cmp` du pilote ;
   - `sha256sum -c` de l'extraction.

   **Ni taille ni listing affichés.** Seul le sha de l'archive est imprimé. Puis `rm -rf ~/runs/c3_outillage/conf`,
   et l'heure est consignée.
6. S2 poussé, CI verte, puis la porte (§ 6).

**Pilote `run_conformite.sh <S1>`**, sur le modèle du 4b :
- En-tête : `set -o pipefail`, `set -u`, pas de `set -e`, `unset SCHEDULER_PAIRS SCHEDULER_INTERVALS VIRTUAL_ENV`,
  `NO_COLOR=1`.
- `PY` : le venv du service. `env PYTHONPATH="$REPO/src"` sur chaque invocation Python, jamais sur `alembic`, lancé
  depuis l'arbre du service.
- Gardes (refus = 2, `guard=REFUSED <raison>`), `pilot_sha256` consigné après `guard=0`, puis copie de `$0` dans
  `out/pilot.sh`. `service_before`, `alembic_before`.
- Pour `K` de 1 à 3 :
  1. `mkdir work/`.
  2. Les sept invocations, **fichiers seulement** (`> work/logs/<étape>.log 2>&1`), un code par étape. Une étape dont
     l'entrée manque est `SKIPPED` ; les suivantes sont tentées.
  3. L'événement du producteur est cherché dans une **liste close** tirée du code à S1 (`_refuse`, `ProducerRefusal`,
     `ProducerControlError`, `logger.error` de `c3b_prefix`, `c3b_evaluate` et `c3b_common`, plus `evaluated` et
     `refusal_form_written`). Complétude prouvée par `tests/events.sh`. Hors liste : `hors_liste`.
  4. Extraction par heredoc sur `chain/verdict.json` : `chain.verified`, violations vides, violations de rejeu vides,
     `chain.steps`. Si `verdict.json` est absent : `chain_stopped=<étape>:<code>`, pris sur le message
     `CHAINE ARRETEE …` (`c3_verdict.py:1929`).
  5. Interpréteur des deux provenances.
  6. `mv work out/run<K>`.
- Les trois exécutions tournent même après un échec : l'information compte, et le STOP vient après.
- Comparaison sur les trois exécutions, par `cmp -s` : liste attendue, 23 × `eq3`, agrégat.
- Puis `alembic_after` (toujours), `service_after`, `tree_after`, `campaign_unlock_after`.
- Code du pilote : 2 si une garde refuse, 1 si quelque chose s'écarte de l'attendu, 0 sinon.
- Durée estimée : environ 6 min (préfixe 43 s à 4 workers, 2 min 10 à 1 ; évaluation 9 s ; chaîne quelques secondes).

## 6. Porte § L.5 option 1, au SHA S2 (D5)

`gate_L5/run_gate.sh <S2>` est le pilote C3b `run_c3b_gate.sh` (`be071fff…`) repris tel quel, avec quatre écarts
déclarés :
- SHA en argument ;
- exécuté depuis le clone ;
- `service_before/after` ajoutés ;
- `RUN=~/runs/c3_outillage/gate`.

Il garde tout le reste : gardes, `pytest` présent, port 5432 joignable, 24 invocations `nice -n 5 … pytest -p
no:cacheprovider --junitxml`, un combo ne passant que si `rc=0` **et** son JUnit vaut `1/0/0/0`, agrégat JUnit,
extrait `pytest_summary.txt` (ligne `call` et ligne de résumé), `tree_after`, alembic, interpréteur, collector.
Journaux et JUnit en fichiers seulement (`--showlocals`).

Séquence : `preflight.sh gate`, puis `launch.sh gate <S2>`, puis `wait.sh gate 300 42` (environ 71 min), puis
`fetch.sh gate`, puis `verify_gate.sh` (`full=0`, `junit_total=tests:24,failures:0,errors:0,skipped:0,missing:0`,
`extract=0`, `tree_after=0`, alembic identique, collector inchangé, `pilot_exit=0`), puis `archive.sh gate <date>`,
puis `postflight.sh`. Le postflight relève `~/runs/c3_outillage` absent (`rmdir` du parent vide), aucune session tmux
du chantier, les deux archives présentes et `sha256sum -c`, le collector actif, le HEAD du service inchangé et
`CAMPAIGN_UNLOCK` absent.

## 7. Scripts de contrôle (`results/c3_outillage_v2_2/tests/`, lancés par `bash`, `pipefail`, sortie `.out` committée, `rc=` en dernière ligne)

Les scripts sont génériques par phase, sur le modèle de `results/c3b_producteur/closure/tests/*.sh` :
`preflight.sh`, `launch.sh`, `wait.sh`, `fetch.sh`, `archive.sh` (`conf` : sans `tgz_size`), `postflight.sh`.

Les autres :
- `manifest_check.sh` : chemins JSON changés contre le manifeste du 28/09 = la liste attendue exacte ; `c3_anchor`
  local sur le scratchpad → 0 et `T` ; sha du manifeste.
- `events.sh` : liste close du pilote = liste tirée du code à S1.
- `lint_lot3.sh` : `ruff check` et `ruff format --check` sur les seuls `.py` du lot, jamais `--fix`.
- `verify_conformite.sh` et `verify_gate.sh`. Chacun prend en argument le répertoire des preuves à juger (par défaut
  celui du dépôt), ce qui permet de le pointer sur des cas fabriqués.
- `verify_adverse.sh` (**condition du GO**) fabrique ses cas dans un `mktemp -d`, par heredoc ; aucun fichier de cas
  n'est versionné. Il consigne `cas=<nom> rc=<n>` par cas, et `rc=0` ssi le témoin rend 0 et chaque cas dévié rend
  autre chose que 0.
  - **Conformité.** Le témoin sain est le `status.txt` complet de § 8, avec les valeurs attendues, deux `alembic`
    identiques à `c3bd1e7a0001 (head)` et `pilot_exit=0`. Un cas dévié par famille d'items :
    - `guard=REFUSED` ;
    - `pilot_sha256` ≠ blob ;
    - `alembic_after` différent de `alembic_before` ;
    - `service_after` avec `NRestarts` changé ;
    - `prefix_2=3` ;
    - `pre_select_3=2` ;
    - `eval_1=0 event=refusal_form_written` ;
    - `chain_steps_2` avec `continuity:1` ;
    - `chain_verified_3=false` ;
    - `violations_empty_1=false` ;
    - `replay_violations_empty_2=false` ;
    - `interpreter_1=1` ;
    - une clé `eq3` à 1 (run 2 seul) ;
    - `bit_equal_3of3` avec `compared=22` ;
    - `listing_expected_3of3=1` ;
    - une clé attendue **absente** ;
    - `campaign_unlock_after=present` ;
    - `pilot_exit=1`.
  - **Porte.** Le témoin sain est 24 combos `0 junit=1/0/0/0`, avec `full=0` et
    `junit_total=tests:24,failures:0,errors:0,skipped:0,missing:0`. Cas déviés :
    - agrégat 23/24 (`missing:1`) ;
    - un combo `junit=1/0/0/1` (le faux vert « module skippé ») ;
    - un combo `rc=1` ;
    - `extract=1 lines=46` ;
    - `tree_after=1` ;
    - alembic différent ;
    - collector changé ;
    - `pilot_exit=1`.
- `ci_status.sh`, repris tel quel, SHA complet.
- `tunnel.sh state`.

**`interdits.sh` étendu**, en gardant le bloc contre `8c114fe`. Bloc lot 3 contre `5f61ac9`, arbre, index et commits
compris :
- diff vide sur `scripts/ tests/ src/ config/ pyproject.toml poetry.lock .github/ agent/ skills/ CLAUDE.md
  docs/protocole_c3.md docs/amendements_c3_v2.1.md docs/amendements_c3_v2.2.md docs/CONTRAINTES_POST_B4.md
  results/c3_v2_2 results/c3b_producteur` ;
- fichiers changés ⊆ {`results/c3_outillage_v2_2/**`, `docs/RESEARCH_LOG.md`, `PROJECT_CONTEXT.md`,
  `results/INDEX.md`} ;
- aucun fichier versionné sous `results/c3_outillage_v2_2/` qui porte un nom d'artefact du chemin (`variants`,
  `evaluation*`, `benchmark*`, `candles*`, `selection*`, `verdict*`, `continuity*`, `anchor`, `entry`,
  `observations`, `coverage`, `prefix_run`, `*.tgz`), hors `conformite/manifest.json` ;
- `CAMPAIGN_UNLOCK` absent de l'arbre et de HEAD ;
- aucun script du lot qui nomme `docker`.

## 8. Format des extraits de preuve

Une ligne `clé=valeur` par fait, et rien d'autre. Exemple de `status.txt` :

```
guard=0 sha=<S1> python=Python 3.12.3 krakenbot=/home/bruno/runs/c3_outillage/conf/repo/src/krakenbot/__init__.py protocol=1bed7696…292a manifest=<sha> campaign_unlock=absent
pilot_sha256=<sha>
service_before=head=<sha> dirty=0 collector=active NRestarts=<n>
alembic_before=0
workers_1=4
prefix_1=0 event=- at=…
pre_anchor_1=0 / pre_entry_1=0 / pre_benchmark_1=0 / pre_select_1=0
eval_1=0 event=evaluated at=…
chain_1=0
chain_steps_1=anchor:0,entry:0,benchmark:0,select:0,continuity:0
chain_verified_1=true  violations_empty_1=true  replay_violations_empty_1=true  extract_1=0  interpreter_1=0  moved_1=0
… (K = 2, 3)
listing_expected_3of3=0
eq3 eval/evaluation.json=0 … (23 lignes)
bit_equal_3of3=0 compared=23 differing=0 absent=0
alembic_after=0  service_after=…  tree_after=0  campaign_unlock_after=absent  end=…
```

Remontent aussi : `pilot_exit.txt`, les deux `alembic current`, le sha de l'archive et `verify_attendu.out` (items
tenus sur items). Ne remontent jamais les sorties des producteurs ou de la chaîne, les journaux, les listings, les
tailles, les sha d'artefacts (D3), l'identité, la paire, les métriques, les λ, l'issue, la raison ni le motif.

## 9. Livrable 3 — clôture (S3)

**`results/c3_outillage_v2_2/report.md`**

Première ligne, avec sa portée (K11) :

> « Aucune donnée de la fenêtre de campagne 2021-03-01 → 2026-06-29 n'a été lue par le producteur ni par la chaîne,
> sur aucun run de ce chantier ; aucune issue de chaîne n'a été lue. »

Puis, par lot :
- livré (tables commit par commit des lots 1-2, reprises, et lot 3) ;
- tests (tables des suites, comptes : 3 259 + 45 + 19 = 3 323 ; 45 levés et 1 caduc déclaré) ;
- mutants (M1-M6 et M3b ; L2M1-L2M17) ;
- écarts au brief et à la liste close (tables des lots 1-2 reprises, et le lot 3 : K1, K2, K3, K7, K8, K11, K12, D1,
  D3, D4, D5).

Ensuite, les candidats v2.3 consolidés :
- lot 1 : D3, D6, **D7 — évaluation différée, prérequis probable avant campagne**, D14 ;
- lot 2 : D3, D6, D7 ;
- le nom périmé `…_n_est_pas_rejouable_sous_v21` (`test_c3_entry.py:709`).

Puis :
- les défauts des trois lots (§ 6 des README 1-2, et ceux du lot 3, dits comme tels) ;
- les preuves serveur (conformité : codes, attendu tenu n/n, archive, heure du `rm` ; porte : 24/24, archive) ;
- tunnel, base, interdits ;
- les limites : les 24 `_full` et les 13 tests base, comparaison par hash ou lecture sans métrique ; l'issue est
  inscrite dans des registres jetés ;
- ce qui attend : merge par Bruno, `CODE_MAP` au merge, les lignes de D6, `pull` du serveur, conversation manifeste
  (D7 v2.3 à trancher avant campagne, `CAMPAIGN_UNLOCK`, dettes 21 et 24).

**Autres fichiers**
- `PROJECT_CONTEXT.md` § 1 : une puce « outillage v2.2 livré, conformité v2.2 prouvée », et la phrase « Rien n'est
  outillé » de la puce v2.2 datée « au 29/09 ». Rien d'autre.
- `docs/RESEARCH_LOG.md` : « Issue de l'entrée 19 », et un ajout aux « Essais à venir », sans rien réécrire.
- `results/INDEX.md` : une ligne `c3_outillage_v2_2/`, et la date de mise à jour.

## 10. Vérification de bout en bout

- **Avant S1** : `manifest_check.out` (`rc=0`, `c3_anchor` local 0, `T` attendu), `events.out`, `lint_lot3.out`,
  **`verify_adverse.out`** (témoins à 0, chaque cas dévié ≠ 0 pour les deux vérificateurs), `interdits_S1.out`
  (`rc=0`). CI verte au SHA S1 complet (`ci_status.sh` : relance pour `test_rejeu_effect` seul,
  tout autre rouge = STOP).
- **Conformité** : `verify_attendu.out` avec tous les items tenus et `rc=0`, archive vérifiée, `rm` consigné.
- **Porte** : `verify_gate.out` `rc=0` (24/24), archive vérifiée, `postflight.out` `rc=0`.
- **Clôture** : `interdits_S3.out` `rc=0`. `tunnel.sh state` fermé (jamais ouvert dans ce lot). CI verte au SHA S3 et
  lue au SHA S4. `git status` propre. Push final **sans merge**. Puis STOP 2.
