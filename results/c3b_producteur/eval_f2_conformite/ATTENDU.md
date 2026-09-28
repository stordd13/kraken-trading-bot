# C3b lot 4b — attendu de conformité du comparateur d'évaluation et du § F.2, déclaré avant le lancement

**Fenêtre d'instrument, aucune lecture économique.** Ce run vérifie deux choses sur la sortie du producteur
d'évaluation :
- elle traverse la chaîne C3 **complète**, soit six étapes ;
- la chaîne rejoue le tirage du § F.2 **au bit près**.

Il ne dit rien de la famille grid. Aucune métrique n'est lue, commentée ou reportée, et **l'issue publiée n'est pas
lue**.

Cet attendu est écrit et committé avant le lancement, avec l'entrée 17 de `docs/RESEARCH_LOG.md`. Le run serveur se
fait au SHA de ce commit.

- **Brief** : `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 4b ».
- **Décisions de Bruno à la clôture du 4a** (28/09) :
  1. la conformité porte sur **le chemin sélection seul** ; la garde de désignation est testée en unitaire ;
  2. **l'issue n'est pas lue** : la phrase du brief « l'issue publiée est citée dans le rapport » est rayée ;
  3. l'attendu se déclare sans connaître l'issue.
- **Plan** : validé le 28/09. `evaluation.json` remplace `evaluation_run.json`. La liste close de ce qui remonte au
  dépôt reçoit deux booléens de plus.
- **GO** : amendements A1 à A4.
  - A2 : `--campaign C3B_LOT4B` est une **étiquette d'instrument**. La dette 21 (`--campaign`) reste intacte.

## Ce qui est lancé

### Entrées versionnées du lot 3, lues et jamais réécrites

| Entrée | Rôle | sha256 |
|---|---|---|
| `results/c3b_producteur/prefix_conformite/manifest.json` | manifeste de conformité | `d96ed10d…c7f4` |
| `…/prefix_conformite/server/chain/anchor.json` | sortie de `c3_anchor` | `e52dc52c…76d9` |
| `…/prefix_conformite/server/chain/selection.json` | sortie de `c3_select`, que personne n'a lue | `a4851cfd…e7d7` |
| `…/prefix_conformite/server/chain/benchmark.json` | sortie de `c3_benchmark` ; le producteur y lit les λ du retenu | `8b7bfd7c…7290` |
| `…/prefix_conformite/server/run1/observations.json` | entrée de la chaîne complète | `57e48213…fd3f` |
| `…/prefix_conformite/server/run1/coverage.json` | entrée de la chaîne complète | `5871f74e…7d51` |
| `…/prefix_conformite/server/chain/variants.json` | registre des variantes, **copié** dans le répertoire du run | `7c5b8065…5b4c` |

**Contrôle préalable fait en local, sur les champs d'empreinte seulement.** Les quatre recoupements sont vrais, et
aucun autre contenu n'est lu :
- `selection.inputs_sha256.benchmark` est l'empreinte du `benchmark.json` versionné ;
- `benchmark.inputs_sha256.{manifest, anchor}` sont celles des deux fichiers versionnés ;
- `benchmark.inputs_sha256.candles` est `20c0d1fb…`.

### Entrée archivée

`run1/candles.json` du lot 3 (15 Mo, jamais versionné) est extrait de l'archive
`~/archive/c3b_lot3_20260928/c3b_lot3_server_20260928.tgz`. Deux garde-fous :
- l'archive doit avoir pour sha256 `80b5f2b9…2cee8` ;
- le fichier extrait doit avoir pour sha256 `20c0d1fb…9376`.

Sinon, la garde est refusée et rien n'est lancé.

### Fenêtre d'évaluation

- **Période** : `[T = 2020-09-11T21:36:00Z, fin = 2020-12-28T00:00:00Z]`, entièrement antérieure au 2021-03-01
  (garde-fou 6).
- **`n_jours`** : `(fin − T) / 86 400 = 107,1`.
- **Grille** : 109 points quotidiens, donc **108 rendements** par série.
- **Comparateur** (§ C.3) :
  - entrée au close de la bougie 5 min de **21:40** le 2020-09-11, la première strictement après `T` ;
  - sortie au close de celle du **2020-12-28T00:00Z**, la dernière `≤ fin` ;
  - marques aux 107 minuits intérieurs.

### Un seul chemin : sélection, deux exécutions, puis la chaîne complète

```
c3b_evaluate.py --manifest … --anchor … --selection …/selection.json --benchmark …/benchmark.json \
    --output-dir out/run{1,2} --now …
c3_verdict.py chain --manifest … --observations …/run1/observations.json --coverage …/run1/coverage.json \
    --candles out/lot3/run1/candles.json --evaluation out/run1/evaluation.json \
    --benchmark-eval out/run1/benchmark_eval.json --registry out/chain/variants.json \
    --out-dir out/chain --campaign C3B_LOT4B --now …
```

**Chemin désigné** : il ne tourne pas au serveur (décision 1). Sa garde est testée en unitaire.

**Ce qui ne passe jamais par l'écran**
- `evaluation.json`, `benchmark_eval.json`, `candles_eval.json`, `evaluation_sensitivity.json`, la provenance ;
- `anchor`, `entry`, `benchmark`, `selection`, `continuity` et `verdict` de la chaîne, en `.json` comme en `.md` ;
- les journaux (le moteur y écrit sa paire).

Tous ces fichiers sont archivés, jamais versionnés ni ouverts : ni listing, ni taille, ni sha comparable, ni `tee`.

**Ce qui remonte au dépôt**
- Les codes et booléens de `status.txt`, extraits par heredoc du pilote.
- Les deux `alembic current`, `pilot_exit.txt`, le pilote, et le sha de l'archive.

## Attendu, item par item, avec sa dérivation

### 1. Gardes

**Attendu** : `guard=0`, puis `pilot_sha256` consigné.

**Conditions**
- HEAD = SHA de ce commit, et arbre suivi propre.
- `poetry.lock` et `pyproject.toml` identiques au service.
- `krakenbot` résolu vers le clone, et `.env` présent.
- sha de l'archive du lot 3 et du `candles.json` extrait conformes.
- Registre copié.

### 2. Producteur, chemin sélection, deux exécutions

**Attendu** : `eval_run1=0 event=evaluated`, `eval_run2=0 event=evaluated`, `eval_bit_equal=0`,
`outputs_bit_equal=0`, `interpreter_check=0`.

Dérivation :
- **Même retenu qu'au 4a.** Les entrées sont les mêmes qu'au 4a, où le chemin sélection a rendu 0 deux fois : un
  candidat est donc retenu, et c'est le même.
- **λ estimables par construction.** `c3_select` n'admet que des candidats dont le bloc de `benchmark.json` est
  estimable (`c3_select.py:390-395`).
- **Comparateur constructible et comparable, pour BTC comme pour ETH** (inventaire du 23/09,
  `results/data_inventory_usdt_2019_20260923/inventory.md`) :
  - aucun trou 5 min à 21:40 le 11/09 ni à minuit le 28/12 ;
  - les trois trous 5 min de la fenêtre (30/11, 21/12, 25/12) ne touchent ni l'entrée ni la sortie ;
  - la série 1 j n'a aucun trou, donc `ff_days = 0` ;
  - ces faits valent pour les deux paires et ne désignent pas le retenu.
- **Séries** : 109 points de part et d'autre, soit trois séries de 108 rendements. Le CAGR observé est fini sur
  107 jours, sauf NAV nulle, qu'aucun contrôle du 4a n'a vue.
- **Déterminisme**
  - même code, mêmes entrées, même lecture en base ;
  - `replay_bootstrap` est pur ;
  - le writer trie les clés, et `--now` n'entre que dans la provenance.
- **`interpreter_check`** : la provenance nomme le `krakenbot` du clone.

### 3. Chaîne complète

**Attendu**
- `chain_steps=anchor:0,entry:0,benchmark:0,select:0,continuity:0` et `chain_exit=0` (le verdict).
- `chain_verified=true`, `verdict_violations=0`, `replay_violations=0`.

Dérivation :
- **Étapes 1 à 4** : la chaîne du lot 3, recalculée sur les mêmes entrées, rendait 0 partout. Le registre copié
  connaît déjà la variante `e324967c…` : l'enregistrement est idempotent, sans violation.
- **Étape 5, `c3_continuity`** :
  - l'évaluation est réelle et porte ses trois porteurs ;
  - `period = [T, fin]` ;
  - le comparateur vaut `[T, fin]`, d'où `window_ok`.
- **Étape 6, `c3_verdict`**
  - **Contrat d'instrument** : `B = 10 000`, les six combinaisons, et un environnement égal puisque c'est le même
    interpréteur que le producteur.
  - **Rejeu au bit** : même fonction (`cc.replay_bootstrap`), mêmes séries après aller-retour JSON (le `repr` le plus
    court se relit à l'identique), même graine, même index de paire trié, même `n_jours`.
  - **Déjà vérifié en processus**, en local, par deux tests : `test_the_chain_replay_finds_the_declared_artefact`
    (paires dans les deux ordres) et `test_the_full_chain_verifies_a_produced_evaluation`.
- **`validé` et `réfuté` sont inatteignables par construction.** La provenance de l'univers est `unknown`, donc
  `P_PROVENANCE` fait partie des raisons (`c3_verdict.py:721-722`, § A.5). **L'issue n'est ni déclarée ni lue.**

### 4. Base

`alembic current` est identique avant et après : `c3bd1e7a0001 (head)`. Le producteur lit en lecture seule, assertée
par Postgres.

### 5. Bornes des lectures

- Toutes les lectures du producteur sont bornées à `≤ fin = 2020-12-28T00:00Z` :
  - bougies `[T, fin]` de la seule paire évaluée ;
  - `run(pair, T, fin)` ;
  - amorçage `≥ T − 400 j`.
- **Aucune donnée de la fenêtre de campagne (`2021-03-01 → 2026-06-29`) n'est lue.**

**Appuis, sans lecture d'artefact**
- **le code** : `read_evaluation_closes`, `run_once`, et `candles_artefact`, qui refuse toute estampille `> fin` ;
- **les tests** : les lectures relevées valent exactement `(pair, 5, T, fin)` et `(pair, 1440, T, fin)` ;
- **la chaîne** : `continuity = 0` impose `period = [T, fin]` (`c3_continuity.py:384-388`), et `verdict = 0` impose
  que c2 n'est pas en échec, donc une grille quotidienne `[T, fin]`.

## Règles en cas d'écart

- **Tout écart à un item est un constat** écrit au rapport. Aucune relance n'a lieu avant son diagnostic avec Bruno,
  et **aucune lecture pour diagnostiquer sans son accord**.
  - Exemple : un `first_fill_at` nul donnerait R0 à `continuity`. C'est le candidat v2.2 déjà connu.
- Un correctif du producteur est un commit de plus. Il repasse par Bruno avant tout nouveau lancement.
- Seule une panne du pilote lui-même (par exemple un code 127) se relance après correction du pilote.
- Chaque lancement est consigné, avec son `status.txt`.
