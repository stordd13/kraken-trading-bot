# C3 outillage v2.3, lot 2 — attendu de conformité sous v2.3, déclaré avant le lancement

**Fenêtre d'instrument, aucune lecture économique, issue non lue.** Ce run vérifie, sur le serveur (§ J item 12 : la
conformité ne se prouve pas en local), que le producteur C3b et la chaîne C3 **au code du chantier outillage v2.3**
traversent les six étapes sous le protocole v2.3, et que trois exécutions du même run sont identiques au bit. Il ne dit
rien de la famille grid. Aucune métrique, aucun λ, aucune identité ni paire du retenu, aucune issue, raison ni motif
n'est lu, commenté ou reporté.

Cet attendu est écrit et committé avant le lancement, avec l'entrée 21 de `docs/RESEARCH_LOG.md`. Le run se fait au SHA
de ce commit (S1, plan D1). **Bruno le relit au SHA S1 complet, avec le manifeste et le pilote, avant tout GO de
lancement (STOP 1). Rien ne tourne sur le serveur avant ce GO.**

- **Brief** : `agent/AGENT_C3_OUTILLAGE_V2_3.md` § 4 « Lot 2 ».
- **Plan** : `results/c3_outillage_v2_3/plans/lot2.md`, approuvé le 2026-09-30 (K1 à K9, D1 à D10).
- **Modèle** : l'attendu de la conformité v2.2 du 30/09 (`results/c3_outillage_v2_2/conformite/attendu.md`), dont les
  items 1 à 10 sont repris dans leurs codes ; le § 3 dit ce que v2.3 change.
- **Protocole** v2.3, sha256 `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`.
- **Code** identique au tip du lot 1, `a30d62a2fec51a4c277d51a5d20047892b2fbcca` : `tests/interdits_lot2_S1.out`,
  diff vide sur `scripts/ tests/ src/ config/ pyproject.toml poetry.lock .github/`.

## 1. Fenêtre

- **Période** : `2020-01-06T00:00Z → 2020-12-28T00:00Z`, `F = 0,70`.
- **Ancrage** : `T = 2020-09-11T21:36:00Z` (0,70 × 357 j = 249,9 j), recalculé par `c3_anchor`, jamais passé en
  paramètre ; vérifié en local sur le manifeste (`tests/manifest_check.out`).
- **Provenance** : `unknown`.
- **Garde-fou 6** : il passe par construction, la fin étant avant le 2021-03-01. `results/c3b_producteur/CAMPAIGN_UNLOCK`
  est absent, ni créé ni transporté ; le pilote l'asserte absent dans le clone avant et après, le preflight dans l'arbre
  du service, `interdits_lot2.sh` dans le dépôt.
- **Date de l'évaluation différée** : `2021-12-28T00:00:00+00:00`, **une déclaration du manifeste, jamais une fenêtre
  lue** (D8). Le garde-fou 6 ne lit que `window` (`c3b_common.py:105-110`) ; aucun module ne lit de donnée à cette date.

## 2. Manifeste

**Fichier** : `results/c3_outillage_v2_3/conformite/manifest.json`, sha256
`24bde67dd88005e22f05b4917c7fa973ab37b384ac19df3acb6a3e56e704565a`, asserté par la garde du pilote.

**Origine** : le manifeste de la conformité v2.2 du 30/09 (`results/c3_outillage_v2_2/conformite/manifest.json`,
`c3769a6a…1ff7`), plus les **seules** clés que v2.3 change (plan K1). Chemins changés, vérifiés par
`tests/manifest_check.sh` (`manifest_check.out`, `rc=0`) :

| Chemin | Changement | Pourquoi |
|---|---|---|
| `deferred_evaluation.date` | ajouté : `2021-12-28T00:00:00+00:00` | § A.6 v2.3 (AM-01) : clé obligatoire sur tout manifeste ; **365 jours exactement** après `window.end`, le bord admis de la borne (X2), rejoué sur le chemin réel (D8) |
| `protocol_sha256` | `1bed7696…` (v2.2) → `d030ab23…` (v2.3) | `c3_anchor` l'asserte |
| `variant_id` | `c3-outillage-v23-conformite-2020` | nouvelle variante |
| `research_log_entry`, `run_scope` | réécrits | entrée 21 ; portée de ce run |

**Tout le reste est inchangé**, au caractère près (même mise en forme) : univers de 12 candidats
`grok_grid_atr_adaptive_v4`, classes C1, C2, C5, C6 × BTC, ETH, SOL `/USDT` ; famille de test
`test-conformite-instrument-2020` (jamais une famille de campagne) ; fees `bybit` et coûts de
`config/pair_costs_b4.json` ; `min_order_quote 5.0` ; seuils avec leur classe ; graine `20260927` ; `lambda_mode: prefix` ;
`parent.is_root: true` ; capital `"1000"`.

**Vérifié en local avant S1**, par `c3_anchor` seul (pur, sans base, registre et sortie dans un répertoire temporaire
hors du dépôt) : code 0 — la date passe l'étape 1 — et `T = 2020-09-11T21:36:00+00:00` ; écart de la date : 365,000000 j.

## 3. Ce que v2.3 change à ce run (déclaré, sans effet sur les codes attendus)

- **La clé et sa borne** : `load_manifest` exige `deferred_evaluation.date` dans tous les modules (producteur compris),
  `c3_anchor` la valide à l'étape 1 (≥ 365 jours). Ici, 365 jours exactement : admis.
- **L'évaluation différée n'est pas inscrite** (plan K2) : la provenance `unknown` donne `P_PROVENANCE` (rang 2 du § H.1),
  qui précède `F_CANNOT_SEPARATE` ; la voie du § 10.1 ne s'ouvre pas. L'étape 6 n'inscrit que `{issue, raison, compte}`
  (non compté) dans la copie du registre, jetée avec l'archive. Ce constat **n'est pas vérifié par lecture** (non-lecture
  du registre) : il est dérivé du code et des tests du lot 1 (X4, N1).
- **La ligne du registre écrit n'imprime plus de digest** (D13 du lot 1) ; le pilote ne la lisait pas (plan K3).
- **Rien d'autre** : forme de `verdict.json`, liste des 23 artefacts, codes d'étape et contrôles de la chaîne inchangés
  (plan K3) ; producteur inchangé depuis la conformité v2.2 (`c3b_*.py`, diff vide ; liste close `EVENTS` re-prouvée égale
  au code, `tests/events.out`).

## 4. Registre

Il est **neuf par exécution**, sous sa sortie, et ce n'est **jamais** un registre persistant ni le registre de campagne.
- `c3_anchor` autonome écrit `work/pre/variants.json`, un registre vide qui reçoit la variante comme racine.
- `c3_verdict.py chain` reçoit une copie, `work/chain/variants.json` : son étape 1 y est idempotente (`RECORD_KEYS`
  égaux, même manifeste au bit), son étape 6 y inscrit une fois l'issue et son statut.
- **Les deux fichiers sont archivés, jamais lus.** Un registre partagé consommerait la relance unique de la famille.

## 5. Ce qui tourne

**Pilote** : `results/c3_outillage_v2_3/conformite/server/run_conformite.sh`, versionné à S1 et **exécuté depuis le
clone** à ce SHA (D1), sha256 `1f4b9fd4666d978b9117f2f20618844b4cacce2c5040d48928fad11e7f88be16` ; le pilote le consigne
lui-même, et la garde asserte que le fichier exécuté est celui du clone. Il est repris du pilote v2.2 : seules changent
les constantes (chemins `~/runs/c3_outillage_v2_3/conf`, manifeste, sha du manifeste et du protocole, `--campaign`,
`--now`) et l'en-tête (`tests/reprise_lot2.out`).

**Trois exécutions**, `K = 1, 2, 3`, `--workers` 4, 1 et 4 au préfixe (D4), tout le reste identique :
- le **même `--now`** (`2026-09-30T00:00:00+00:00`) passé à toutes les invocations qui l'acceptent ;
- le **même chemin absolu** `~/runs/c3_outillage_v2_3/conf/work/`, renommé `out/run<K>/` après chaque exécution (`mv`
  sur le même système de fichiers) — `anchor.json` et `entry.json` embarquent le chemin de leurs entrées.

```
c3b_prefix.py --manifest M --output-dir work/prefix --workers {4|1|4} --now N
c3_anchor.py    --manifest M --registry work/pre/variants.json --output work/pre/anchor.json --now N
c3_entry.py     … --output work/pre/entry.json --markdown work/pre/entry.md --now N
c3_benchmark.py … --output work/pre/benchmark.json --now N
c3_select.py    … --output work/pre/selection.json --markdown work/pre/selection.md --now N
c3b_evaluate.py --manifest M --anchor work/pre/anchor.json --selection work/pre/selection.json \
    --benchmark work/pre/benchmark.json --output-dir work/eval --now N
cp work/pre/variants.json work/chain/variants.json
c3_verdict.py chain --manifest M --observations work/prefix/observations.json --coverage work/prefix/coverage.json \
    --candles work/prefix/candles.json --evaluation work/eval/evaluation.json \
    --benchmark-eval work/eval/benchmark_eval.json --candles-eval work/eval/candles_eval.json \
    --registry work/chain/variants.json --out-dir work/chain --campaign OUTILLAGE_V23_CONF --now N
```

`--campaign OUTILLAGE_V23_CONF` est une **étiquette d'instrument** (libellé seulement ; dette 21 intacte).
**Environnement unique** : l'interpréteur du venv du service, `env PYTHONPATH="$REPO/src"` sur chaque invocation Python ;
`alembic current` sans `PYTHONPATH`, depuis l'arbre du service, avant et après.

## 6. Attendu, item par item — la liste close de ce qui remonte

Tout ce qui n'est pas dans cette table est archivé au serveur, **jamais versionné ni ouvert**. Les items sont vérifiés
par `verify_attendu.py` sur les seuls `status.txt`, `alembic_before.txt`, `alembic_after.txt` et `pilot_exit.txt`.

| # | Clés de `status.txt` | Attendu |
|---|---|---|
| 1 | `guard`, `pilot_sha256`, `pilot_copy` | `guard=0` au SHA S1 (complet) ; `krakenbot` du clone ; `protocol=d030ab23…79e6` ; `manifest=24bde67d…565a` ; `campaign_unlock=absent` ; `pilot_sha256` = sha du blob à S1 ; copie du pilote 0. Les gardes exigent aussi un arbre suivi propre, `poetry.lock` et `pyproject.toml` égaux à ceux du service, un `.env`, et `work/` et `out/run*` absents |
| 2 | `alembic_before`, `alembic_after`, `alembic_same_head` | `0`, `0`, `0` ; deux fichiers identiques portant `c3bd1e7a0001 (head)` |
| 3 | `service_before`, `service_after`, `tree_after`, `campaign_unlock_after` | service inchangé (HEAD, `dirty=0`, `collector=active`, même `NRestarts`) ; arbre du clone propre ; `absent` |
| 4 | `workers_<K>`, `prefix_<K>` | `4, 1, 4` ; `0 event=-` ×3. **Code 0 ⟹ base en lecture seule assertée par Postgres** (`probe_database`, `SHOW transaction_read_only = on`), sinon `database_read_failed` et 2 ; de même pour l'item 6 |
| 5 | `pre_anchor_<K>`, `pre_entry_<K>`, `pre_benchmark_<K>`, `pre_select_<K>` | `0` ×4, trois fois — l'ancrage autonome admet la date (§ 3) |
| 6 | `eval_<K>` | `0 event=evaluated` ×3, **jamais** `refusal_form_written` |
| 7 | `registry_copy_<K>`, `chain_<K>`, `chain_steps_<K>`, `chain_verified_<K>`, `violations_empty_<K>`, `replay_violations_empty_<K>`, `extract_<K>` | `0` ; `0` ; `anchor:0,entry:0,benchmark:0,select:0,continuity:0` ; `true` ; `true` ; `true` ; `0` ; trois fois |
| 8 | `interpreter_<K>`, `moved_<K>` | `0`, `0` ×3 : les deux provenances nomment le `krakenbot` du clone |
| 9 | `listing_expected_3of3`, 23 × `eq3 <artefact>`, `bit_equal_3of3` | `0` ; `0` ×23 ; `0 compared=23 differing=0 absent=0` |
| 10 | `pilot_exit.txt` | `0` |

**Les 23 artefacts comparés** entre les trois exécutions (`cmp`, booléens seulement ; **aucun sha d'artefact ne
remonte**) : `prefix/` observations, coverage, candles ; `pre/` anchor, variants, entry (`.json`, `.md`), benchmark,
selection (`.json`, `.md`) ; `eval/` evaluation, benchmark_eval, candles_eval, evaluation_sensitivity ; `chain/` anchor,
entry (`.json`, `.md`), benchmark, selection (`.json`, `.md`), continuity, verdict, variants. **Exclus, déclaré** :
`prefix/prefix_run.json`, `prefix/partial/*`, `eval/evaluation_run_provenance.json` (durées) et `logs/*` (horodatés).

## 7. Constats hérités, écrits en le sachant

- **(a)** Provenance `unknown` : `P_PROVENANCE` (rang 2 du § H.1) précède toute autre raison ; `validé` et `réfuté` sont
  inatteignables ; un comparateur non comparable donnerait `P_PROVENANCE` et un `motif` nul. Sans effet sur les codes.
- **(b)** Le coin D6 (désignation, abstention, comparateur non constructible → 2) est hors chemin : ce run passe par la
  sélection, et le comparateur 2020 se construit (conformités du 28/09 et du 30/09 : `evaluated`). Une abstention
  donnerait `eval_<K>=2 event=nothing_to_evaluate` : un écart, donc STOP.
- **(c)** L'inscription est non comptée (`P_PROVENANCE`) et sans évaluation différée (§ 3), dans des registres jetés.

## 8. Bornes des lectures

Toutes les lectures du producteur sont bornées : au préfixe, `≤ T`, amorçage `≥ début − 400 j` ; à l'évaluation,
`≤ fin = 2020-12-28T00:00Z`, amorçage `≥ T − 400 j`. **Aucune donnée de la fenêtre de campagne (`2021-03-01 →
2026-06-29`) n'est lue par le producteur ni par la chaîne**, et la date différée (2021-12-28) n'est lue par aucun
module comme une fenêtre. Appuis, sans lecture d'artefact : le code (`candles_artefact` refuse toute estampille `> fin`,
lectures du préfixe bornées à `T`), les tests (lectures `(pair, 5, T, fin)` et `(pair, 1440, T, fin)`, `run(pair, T,
fin)` une fois), les codes de chaîne (`continuity = 0` impose `period = [T, fin]` ; la règle d'entrée de
`candles_eval.json` refuse, en code 2, toute estampille postérieure à la fin). Ce n'est pas un journal de requêtes.

## 9. Non-lecture

- **Jamais à l'écran** : les sorties des producteurs et de la chaîne (`.json`, `.md`), les deux registres, les
  journaux, `extract.err` ; aucun listing, aucune taille (la taille du registre dit s'il porte un bloc différé : D13 du
  lot 1), aucun sha d'artefact. Le seul sha imprimé est celui de l'archive.
- **Remonte au dépôt** : `status.txt` (codes, noms d'événements de la liste close, booléens), `pilot_exit.txt`, les deux
  `alembic current`, `verify_attendu.out`, le sha de l'archive, les sorties des scripts `tests/*_conf.out`.

## 10. Règle d'échec

Tout code différent de l'attendu, `chain.verified` faux, une violation, trois exécutions non identiques ou un item de
`verify_attendu.out` en écart : **STOP**, sans relance « pour voir » ni correction ; le constat est versionné
(`status.txt` et les extraits) ; le répertoire serveur reste en place, sans archive ni `rm` (D7) ; aucune lecture de
diagnostic sans l'accord de Bruno. Seule une panne du pilote lui-même (127, chemin) se relance, après correction par un
commit repassé par Bruno.

## 11. Les vérificateurs, prouvés avant de servir

- **`tests/pilot_dryrun.out`** (`rc=0`) : les deux pilotes ont tourné en local dans un monde simulé (clone, faux
  interpréteur qui embarque les chemins de ses entrées et met des durées aléatoires dans les provenances, faux
  `systemctl`), trois lignes changées par pilote (chemins du monde simulé) : conformité conforme → 0 (`bit_equal_3of3=0
  compared=23`) ; `evaluation.json` différent au seul run 2 → 1 ; violation de rejeu → 1 ; SHA faux → 2 ; porte conforme
  → 0 ; combo skippé en rc 0 → 1. Limite dite : `bash` local 3.2, serveur 5.
- **`tests/verify_adverse.out`** (`rc=0`) : `verify_attendu.py` rend 0 sur le témoin (le `status.txt` de la simulation
  conforme du pilote lui-même), et 1 sur chacun des **22 cas déviés** avec exactement un item en écart ; même preuve pour
  `verify_gate.sh` (témoin 0, **15 cas déviés**).
