# C3 outillage v2.2, lot 3 — attendu de conformité sous v2.2, déclaré avant le lancement

**Fenêtre d'instrument, aucune lecture économique, issue non lue.** Ce run vérifie, sur le serveur (§ J item 12 :
la conformité ne se prouve pas en local), que le producteur C3b et la chaîne C3 **au code du chantier outillage v2.2**
traversent les six étapes sous le protocole v2.2. Il vérifie aussi que trois exécutions du même run sont identiques
au bit. Il ne dit rien de la famille grid. Aucune métrique, aucun λ, aucune identité ni paire du retenu, aucune issue,
raison ni motif n'est lu, commenté ou reporté.

Cet attendu est écrit et committé avant le lancement, avec l'entrée 19 de `docs/RESEARCH_LOG.md`. Le run se fait au
SHA de ce commit (S1, plan D1). **Bruno le relit au SHA S1 complet avant tout lancement (STOP 1).**

- **Brief** : `agent/AGENT_C3_OUTILLAGE_V2_2.md` § « Lot 3 ».
- **Plan** : `results/c3_outillage_v2_2/plans/lot3.md`, approuvé le 2026-09-29.
  - D1 à D7 accordés tels que recommandés.
  - Condition : les vérificateurs sont prouvés avant de servir (§ 10 ci-dessous).
- **Protocole** v2.2, sha256 `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`.
- **Code** identique à `5f61ac9` (tip du lot 2) : `tests/interdits_S1.out`, diff vide sur `scripts/ tests/ src/
  config/ pyproject.toml poetry.lock .github/`.

## 1. Fenêtre

- **Période** : `2020-01-06T00:00Z → 2020-12-28T00:00Z`, `F = 0,70`.
- **Ancrage** : `T = 2020-09-11T21:36:00Z` (0,70 × 357 j = 249,9 j). Recalculé par `c3_anchor`, jamais passé en
  paramètre. Vérifié en local sur le manifeste (§ 2).
- **Provenance** : `unknown`.
- **Garde-fou 6** : il passe par construction, puisque la fin est avant le 2021-03-01.
  `results/c3b_producteur/CAMPAIGN_UNLOCK` est absent : il n'est ni créé ni transporté. Le pilote l'asserte absent
  dans le clone, avant et après. Le preflight l'asserte absent dans l'arbre du service, et `interdits.sh` dans le
  dépôt.

## 2. Manifeste

**Fichier** : `results/c3_outillage_v2_2/conformite/manifest.json`, sha256
`c3769a6a23147f10da4289981b26737270e98b660d216b415acf94b027cc1ff7`, asserté par la garde du pilote.

**Origine** : c'est celui de la conformité du 28/09 (`results/c3b_producteur/prefix_conformite/manifest.json`,
`d96ed10d…c7f4`), plus les **seules** clés que v2.2 change. Chemins changés, vérifiés par
`tests/manifest_check.sh` (`manifest_check.out`, `rc=0`) :

| Chemin | Changement | Pourquoi |
|---|---|---|
| `family` | ajouté : `"test-conformite-instrument-2020"` | § A.6 v2.2, R-17 (`load_manifest` l'exige). **Valeur de test**, jamais une famille de campagne |
| `min_order_usdc` → `min_order_quote` | renommé, valeur `5.0` inchangée | § A.7 v2.2, R-16. `5.0` est la valeur du rejeu, inerte sur le grid |
| `protocol_sha256` | `9300f4e5…` (v2.1) → `1bed7696…` (v2.2) | `c3_anchor` l'asserte |
| `variant_id` | `c3-outillage-v22-conformite-2020` | nouvelle variante |
| `research_log_entry`, `run_scope` | réécrits | entrée 19 ; portée de ce run |

**Tout le reste est inchangé.**
- Univers : 12 candidats `grok_grid_atr_adaptive_v4`, classes C1, C2, C5, C6 × BTC, ETH, SOL `/USDT`.
- Fees `bybit` et coûts de `config/pair_costs_b4.json`.
- Seuils, avec leur classe.
- Graine `20260927`.
- `lambda_mode: prefix`.
- `parent.is_root: true`.
- Capital `"1000"`, représentable en float, comme le 28/09.

**Contrats d'artefact et de chaîne.** Les autres « entrées v2.2 » ne sont pas des clés du manifeste (plan K2) :
λ déclarés dans `evaluation.json`, `metrics.executions`, clés `_quote` des observations et des lots, septième entrée
`candles_eval.json`. Le code du tip les porte, et elles se vérifient par les codes de la chaîne (§ 5, item 7).

**Vérifié en local avant S1**, par `c3_anchor` seul : pur, sans base, registre et sortie dans un répertoire
temporaire hors du dépôt. Code 0, `T = 2020-09-11T21:36:00+00:00` (`manifest_check.out`).

## 3. Registre

Il est **neuf par exécution**, sous sa sortie, et ce n'est **jamais** un registre persistant ni le registre de campagne
(brief, décision 5 ; écart 12 C3b).
- `c3_anchor` autonome écrit `work/pre/variants.json` : un registre vide, qui reçoit la variante comme racine.
- `c3_verdict.py chain` reçoit une copie, `work/chain/variants.json`.
  - Son étape 1 y est **idempotente** : `RECORD_KEYS` égaux, même manifeste au bit (`c3_anchor.py:236-247`).
  - Son étape 6 y inscrit une fois `{issue, raison, compte}` (`c3_verdict.py:1802-1811`, `:1318-1354`).
- C'est le chemin du 4b C3b, où la chaîne tournait sur une copie du registre qui connaissait déjà la variante.
- **Les deux fichiers sont archivés, jamais lus** : après l'étape 6, ils portent l'issue.
- Un registre partagé consommerait la relance unique de la famille (§ 6 c) ; celui-ci est jeté avec l'archive.

## 4. Ce qui tourne

**Pilote** : `results/c3_outillage_v2_2/conformite/server/run_conformite.sh`, versionné à S1 et **exécuté depuis le
clone** à ce SHA (D1). Son sha256 est `5a2cc18db5e6044c487f4ccabe04984a6a3ae8ffc63aad301e39a6dd2860cbaf` ; le pilote le
consigne lui-même, et la garde asserte que le fichier exécuté est celui du clone.

**Trois exécutions**, `K = 1, 2, 3`, avec `--workers` 4, 1 et 4 au préfixe (D4). Tout le reste est identique.
- **Le même `--now`** (`2026-09-29T00:00:00+00:00`) est passé à **toutes** les invocations qui l'acceptent, dans les
  trois exécutions : `c3b_prefix`, `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select`, `c3b_evaluate` et
  `c3_verdict.py chain`, qui le transmet à chaque étape (`c3_verdict.py:1921`). C'est ce qui rend `verdict.json` et
  les deux `variants.json` (`first_registered_at`, `c3_anchor.py:263`) comparables au bit.
- **Le même chemin absolu** `~/runs/c3_outillage/conf/work/` sert aux trois exécutions. Chacune est renommée
  `out/run<K>/` après coup (`mv` sur le même système de fichiers, contenu intact). La raison : `anchor.json` et
  `entry.json` embarquent le chemin de leurs entrées (`c3_anchor.py:309`, `c3_entry.py:778,797`), donc trois
  répertoires différents feraient échouer l'égalité au bit pour une raison bénigne (plan K3).

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
    --registry work/chain/variants.json --out-dir work/chain --campaign OUTILLAGE_V22_CONF --now N
```

`--campaign OUTILLAGE_V22_CONF` est une **étiquette d'instrument**, comme `C3B_LOT4B`. Elle ne sert qu'au libellé
(`c3_verdict.py:1379`) ; la dette 21 (`--campaign`) reste intacte.

**Environnement unique** : l'interpréteur du venv du service, `env PYTHONPATH="$REPO/src"` sur chaque invocation
Python. `alembic current` tourne sans `PYTHONPATH`, depuis l'arbre du service, avant et après.

## 5. Attendu, item par item — la liste close de ce qui remonte

Tout ce qui n'est pas dans cette table est archivé au serveur, **jamais versionné ni ouvert**. Les items sont
vérifiés par `verify_attendu.py` sur les seuls `status.txt`, `alembic_before.txt`, `alembic_after.txt` et
`pilot_exit.txt`. Par rapport à la liste du prompt du lot, les **ajouts** sont les codes des producteurs et des étapes
1-4 autonomes, l'interpréteur, le service, l'arbre et `CAMPAIGN_UNLOCK` : ce sont tous des codes ou des booléens.

| # | Clés de `status.txt` | Attendu | Dérivation |
|---|---|---|---|
| 1 | `guard`, `pilot_sha256`, `pilot_copy` | `guard=0` au SHA S1 (complet) ; `krakenbot` du clone ; `protocol=1bed7696…` ; `manifest=c3769a6a…` ; `campaign_unlock=absent` ; `pilot_sha256` = sha du blob à S1 ; copie du pilote 0 | règles serveur, D1. Les gardes demandent aussi un arbre suivi propre, `poetry.lock` et `pyproject.toml` égaux à ceux du service, un `.env` présent, et `work/` et `out/run*` absents |
| 2 | `alembic_before`, `alembic_after`, `alembic_same_head` | `0`, `0`, `0` ; deux fichiers identiques portant `c3bd1e7a0001 (head)` | aucune migration ; base en lecture seule |
| 3 | `service_before`, `service_after`, `tree_after`, `campaign_unlock_after` | service inchangé : HEAD, `dirty=0`, `collector=active`, même `NRestarts` ; arbre du clone propre ; `absent` | service intouché, collector actif, au SHA de production |
| 4 | `workers_<K>`, `prefix_<K>` | `4, 1, 4` ; `0 event=-` ×3 | 28/09 : 0 ×2 sur les mêmes données. Les changements v2.2 du préfixe (R-16, renommage à l'export ; R-20, dates nullables) ne changent aucun code sur des séries toutes couvertes (le refus `coverage_no_covered_unit` de v2.1 n'y a pas joué). **Code 0 ⟹ base en lecture seule assertée par Postgres** : `probe_database`, `SHOW transaction_read_only = on` (`c3b_common.py:792-804`), sinon `database_read_failed` et 2. De même pour l'item 6 |
| 5 | `pre_anchor_<K>`, `pre_entry_<K>`, `pre_benchmark_<K>`, `pre_select_<K>` | `0` ×4, trois fois | lot 3 C3b : D2 en échec sur les 4 candidats SOL (portée candidat, code 0), SOL non comparable au préfixe, sélection descriptive. Sous v2.1, aucun chemin non fini n'a été atteint (tous les codes à 0), donc R-21 et R-22 ne changent rien ici |
| 6 | `eval_<K>` | `0 event=evaluated` ×3, **jamais** `refusal_form_written` | 4b C3b : le chemin sélection a rendu 0 `evaluated`, ce qui supposait sous v2.1 un comparateur constructible (non constructible → 2 avant le moteur). Le retenu est le même : les seuls changements v2.2 qui touchent la sélection passent par des chemins non finis, inatteints. L'événement vient d'une liste close tirée du code (`tests/events.out`) |
| 7 | `registry_copy_<K>`, `chain_<K>`, `chain_steps_<K>`, `chain_verified_<K>`, `violations_empty_<K>`, `replay_violations_empty_<K>`, `extract_<K>` | `0` ; `0` ; `anchor:0,entry:0,benchmark:0,select:0,continuity:0` — **les six codes d'étape** avec `chain_<K>` (le verdict) ; `true` ; `true` ; `true` (préfixes `rejeu`, `réplications`) ; `0` ; trois fois | 4b C3b, plus ce que v2.2 ajoute (détail sous la table) |
| 8 | `interpreter_<K>`, `moved_<K>` | `0`, `0` ×3 : `prefix_run.json` et `evaluation_run_provenance.json` nomment le `krakenbot` du clone | un seul environnement |
| 9 | `listing_expected_3of3`, 23 × `eq3 <artefact>`, `bit_equal_3of3` | `0` ; `0` ×23 ; `0 compared=23 differing=0 absent=0` | voir la liste ci-dessous |
| 10 | `pilot_exit.txt` | `0` | |

**Dérivation de l'item 7, ce que v2.2 ajoute au 4b C3b.**
- Recoupements R-15 : mêmes fonctions des deux côtés (`cc.recompute_daily`, `cb.build_pair`, `cb.blend_nav`), déjà
  vérifiées en processus par `test_the_full_chain_verifies_a_produced_evaluation`.
- R-19 : le retenu a exécuté (`first_fill_at` non nul, puisque la continuité rendait 0 au 4b), donc
  `executions > 0`.
- R-16 : les formes sont écrites par le code du tip.
- R-17 : la variante est présente dans la copie du registre.
- Même interpréteur pour le producteur et le verdict, donc même environnement § F.2 (b) (`c3_verdict.py:239-252`).

**Les 23 artefacts comparés entre les trois exécutions** (`cmp`, booléens seulement ; **aucun sha d'artefact ne
remonte**, D3) :
- `prefix/` : `observations.json`, `coverage.json`, `candles.json` ;
- `pre/` : `anchor.json`, `variants.json`, `entry.json`, `entry.md`, `benchmark.json`, `selection.json`,
  `selection.md` ;
- `eval/` : `evaluation.json`, `benchmark_eval.json`, `candles_eval.json`, `evaluation_sensitivity.json` ;
- `chain/` : `anchor.json`, `entry.json`, `entry.md`, `benchmark.json`, `selection.json`, `selection.md`,
  `continuity.json`, `verdict.json`, `variants.json`.

**Exclus, et c'est déclaré (plan K4)** : `prefix/prefix_run.json`, `prefix/partial/*` et
`eval/evaluation_run_provenance.json`, qui portent `duration_s` (`c3b_prefix.py:136,440` ; `c3b_evaluate.py:917,1229`),
et `logs/*`, qui sont horodatés. « Liste attendue » veut dire que chaque exécution porte exactement ces 23 fichiers,
hors exclusions.

## 6. Constats hérités, écrits en le sachant

- **(a) `P_PROVENANCE` précède `E_NO_BENCHMARK` au § H.1** (lot 2, D7). La provenance est `unknown`, et `P_PROVENANCE`
  est au rang 2 de la liste (`c3_common.py:567-581`).
  - `validé` et `réfuté` sont inatteignables.
  - Aucune raison de rang inférieur, `E_NO_BENCHMARK` compris, ne peut être publiée.
  - Un comparateur constructible mais non comparable donnerait donc `P_PROVENANCE` et un `motif` nul.
  - **Sans effet sur les codes attendus.** L'issue n'est ni déclarée au-delà ni lue.
- **(b) Le coin D6 est hors chemin** (lot 2 : désignation, abstention et comparateur non constructible → 2). Ce run
  passe par la **sélection** (`--selection`), jamais par la désignation. Et le comparateur 2020 se construit : C3b l'a
  prouvé le 28/09 (4b, `evaluated`), et l'item 6 l'exige de nouveau. Une abstention donnerait
  `eval_<K>=2 event=nothing_to_evaluate` : c'est un écart, donc STOP.
- **(c) L'inscription est non comptée**, puisque `P_PROVENANCE` est non compté (`docs/CONTRAINTES_POST_B4.md` § 10.1).
  Elle va dans des registres jetés.

## 7. Bornes des lectures

Toutes les lectures du producteur sont bornées :
- au préfixe, `≤ T`, avec un amorçage `≥ début − 400 j` ;
- à l'évaluation, `≤ fin = 2020-12-28T00:00Z`, avec un amorçage `≥ T − 400 j`.

**Aucune donnée de la fenêtre de campagne (`2021-03-01 → 2026-06-29`) n'est lue par le producteur ni par la chaîne.**

Appuis, sans lecture d'artefact :
- **le code** : `read_evaluation_closes`, `run_once`, et `candles_artefact`, qui refuse toute estampille `> fin` ;
  lectures du préfixe bornées à `T` ;
- **les tests** : lectures relevées exactement `(pair, 5, T, fin)` et `(pair, 1440, T, fin)` ; `run(pair, T, fin)`
  appelé une fois ;
- **les codes de chaîne** : `continuity = 0` impose `period = [T, fin]` (`c3_continuity.py`) ; la règle d'entrée de
  `candles_eval.json` refuse, en code 2, toute estampille postérieure à la fin (§ L.2 v2.2).

Ce n'est pas un journal de requêtes Postgres.

## 8. Non-lecture

**Ce qui ne passe jamais par l'écran**
- Les sorties des producteurs et de la chaîne, en `.json` comme en `.md`, les deux registres, les journaux (le moteur
  y écrit sa paire, le producteur les identités et les sha de ses écrits) et `extract.err`.
- Aucun listing, aucune taille, aucun sha d'artefact. Le seul sha imprimé est celui de l'archive (D3 : un sha
  d'artefact du chemin sélection est un engagement brute-forçable sur un petit espace d'hypothèses).

**Ce qui remonte au dépôt**
- `status.txt` (codes, noms d'événements de la liste close, booléens).
- `pilot_exit.txt`.
- Les deux `alembic current`.
- `verify_attendu.out`.
- Le sha de l'archive, et les sorties des scripts `tests/*_conf.out`.

## 9. Règle d'échec

- **Déclencheurs** : tout code différent de l'attendu, `chain.verified` faux, une violation, trois exécutions non
  identiques, ou un item de `verify_attendu.out` en écart.
- **Alors STOP**, sans relance « pour voir » ni correction. Le constat est versionné (`status.txt` et les extraits).
  Le répertoire serveur reste en place, sans archive ni `rm` (D7). Aucune lecture de diagnostic n'a lieu sans
  l'accord de Bruno.
- **Seule exception** : une panne du pilote lui-même (127, chemin) se relance, après correction du pilote, par un
  nouveau commit repassé par Bruno.
- Si l'écart porte sur l'égalité au bit, entre le run 2 (1 worker) et les runs 1 et 3 (D4), il signale une dépendance
  d'ordonnancement réelle dans le code du lot 2. Le STOP est mérité.

## 10. Les vérificateurs, prouvés avant de servir (condition du GO)

- **`tests/pilot_dryrun.out`** (`rc=0`) : le pilote a tourné en local dans un monde simulé, sans base ni serveur.
  Le monde : un clone, un faux interpréteur qui embarque les chemins de ses entrées et met des durées aléatoires dans
  les provenances, et un faux `systemctl`. Quatre simulations, chacune au code attendu :
  - conforme → 0 (`bit_equal_3of3=0 compared=23`, exclusions et parade K3 éprouvées) ;
  - `evaluation.json` différent au seul run 2 → 1 (`eq3 … r12=1 r13=0`) ;
  - violation de rejeu → 1 ;
  - SHA faux → 2.

  Le pilote de la porte y passe aussi (conforme → 0 ; combo skippé en rc 0 → 1). Limite dite : `bash` local 3.2,
  serveur 5, avec des constructions portables seulement.
- **`tests/verify_adverse.out`** (`rc=0`). Le témoin sain est le `status.txt` de la simulation conforme du pilote
  lui-même, donc au format exact qu'il écrit. `verify_attendu.py` rend 0 sur ce témoin, avec 0 item en écart. Il rend
  1 sur chacun des **22 cas déviés**, avec **exactement un** item en écart par cas. Même preuve pour `verify_gate.sh`
  (témoin 0, 15 cas déviés).
