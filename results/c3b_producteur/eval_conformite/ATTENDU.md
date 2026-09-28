# C3b lot 4a — attendu de conformité de l'évaluation, déclaré avant le lancement

**Fenêtre d'instrument, aucune lecture économique.** Ce run vérifie que le producteur d'évaluation fabrique un
artefact que la chaîne C3 admet, avec ses trois preuves du § B. Il ne dit rien de la famille grid. Aucune métrique
n'est lue, commentée ou reportée comme résultat.

Cet attendu est écrit et committé avant le lancement, avec l'entrée 16 de `docs/RESEARCH_LOG.md`. Le run serveur se
fait au SHA de ce commit.

- **Brief** : `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 4a ».
- **Plan** : validé le 2026-09-28. Bruno a donné son GO avec trois amendements :
  - la preuve à plat repose sur deux lectures probantes, `cash` et `qty`. `pending` est vide par construction ;
  - la garde de désignation vaut aussi au lot 4b ;
  - la contrainte « capital représentable en `float` » est notée pour le manifeste.

## Ce qui est lancé

### Entrées versionnées, lues et jamais réécrites

| Entrée | Rôle |
|---|---|
| `results/c3b_producteur/prefix_conformite/manifest.json` | manifeste du lot 3, sha256 `d96ed10d…` |
| `results/c3b_producteur/prefix_conformite/server/chain/anchor.json` | sortie de `c3_anchor` au lot 3 |
| `results/c3b_producteur/prefix_conformite/server/chain/selection.json` | sortie de `c3_select` au lot 3 ; son contenu n'a été lu par personne, et personne ne le lit |

### Fenêtre d'évaluation

- Période : `[T = 2020-09-11T21:36:00Z, fin = 2020-12-28T00:00:00Z]`, soit 107,1 jours.
- `T` est recalculé depuis le manifeste : `0,70 × 357 j` après le 2020-01-06. L'ancrage le recoupe.
- L'amorçage est lu avant `T`, à `T − 400 j` au plus tôt.
- Toute la fenêtre est **antérieure au 2021-03-01** (garde-fou 6).

### Deux chemins, toujours exécutés tous les deux

Le pilote ne branche jamais sur le code du premier chemin.

**1. Chemin sélection.**

```
c3b_evaluate.py --manifest … --anchor … --selection …/chain/selection.json
```

Le script consomme le retenu mécaniquement et rend :
- 0 s'il a évalué un candidat ;
- 2 avec l'événement `nothing_to_evaluate` s'il n'y a rien à évaluer.

Seuls ce code, l'événement et l'égalité des sha entre les deux exécutions sont rapportés. Les sorties de ce chemin
(artefact, provenance, journal brut, où le moteur écrit sa paire) sont **archivées sans être versionnées ni lues**.

**2. Chemin désigné.**

```
c3b_evaluate.py … --candidate 145867637b7f9bac6b556efc9dc48e929f18624f1c56d54eebe83b6c5eb47962
```

- **Règle de désignation**, mécanique, sans choix humain ni lecture de métrique : la première identité `BTC/USDT` ou
  `ETH/USDT` de l'univers, dans l'ordre lexicographique.
- Sur ce manifeste, elle vaut `145867637b7f9bac…` : `ETH/USDT`, classe C2, paramètres
  `{"bear_protection_mode": "1w_only", "bias_1d": 0}`, séries de décision `[1w, 4h]`. C'est aussi la première
  identité de tout l'univers.
- Le pilote recalcule la règle sur le serveur depuis le seul manifeste. Un écart avec cette valeur est une garde
  refusée : rien n'est lancé.
- La désignation est refusée par le script sur toute fenêtre qui dépasse le 2021-03-01, que `CAMPAIGN_UNLOCK` existe
  ou non.

### Environnement serveur, et ce qu'on y fait

- **Environnement.** Répertoire `~/runs/c3b_eval4a/`. Le clone est isolé, au SHA de ce commit, avec le `.env` du
  service. On utilise le venv unique du service, et `env PYTHONPATH="$REPO/src"` sur chaque invocation Python.
- **Exécutions.** Chaque chemin est exécuté deux fois.
- **Chaîne.** Sur la première sortie désignée, on vérifie l'admission (`cc.evaluation_admission`), puis on lance
  `c3_continuity` avec un comparateur d'évaluation **synthétique** : `{pair, window [T, fin], comparable: true, les
  cinq tests de cc.COMPARABILITY_TESTS à true}`. Ce comparateur n'a aucune valeur de mesure. Il n'existe que parce que
  `c3_continuity` en exige un, et le vrai est l'objet du lot 4b.
- **Base.** `alembic current` est relevé avant et après.

## Attendu, item par item, avec sa dérivation

### 1. Désignation

Le pilote recalcule `145867637b7f9bac6b556efc9dc48e929f18624f1c56d54eebe83b6c5eb47962` et consigne `designation=0`.

### 2. Chemin sélection

- Deux exécutions, avec **le même code, dans `{0, 2}`**.
- Si le code est 2 :
  - l'événement est `nothing_to_evaluate` ;
  - aucun fichier n'est écrit.
- Si le code est 0 : `evaluation_run.json` est identique au bit entre les deux exécutions.
- Rien d'autre n'est déclaré, lu ou rapporté. L'issue BTC/ETH de la sélection du lot 3 reste non lue.

### 3. Chemin désigné : exécution

- **Code 0 aux deux exécutions**, et `evaluation_run.json` **identique au bit**. `--now` n'entre que dans la
  provenance.
- **Clés de l'artefact.** Exactement :

  ```
  synthetic, strategy, pair, params, period, equity_daily, liquidation, warmup, invocation, first_fill_at,
  flat_start_proof, metrics
  ```

  C'est la fixture `evaluation` moins les clés du § F.2. `metrics` ne contient que `net_pnl`.
  `synthetic` vaut `false`.
- **État lu avant `run`** (`flat_start_observed` de la provenance) :

  ```
  {"usdc_balance": "1000.0", "btc_held": "0", "active_buy_orders": 0, "active_sell_orders": 0,
   "strategy_built": false, "trades": 0}
  ```

  Dérivation :
  - `C = 1000` au manifeste. La fabrique passe `float(C)` (`c3b_common.py:302`).
  - Le moteur stocke `Decimal(str(1000.0))`, soit `"1000.0"` (`backtest.py:2250`).
  - L'égalité avec `C` se fait en `Decimal` numérique.
- **Preuve de départ à plat** :

  ```
  {"at": "2020-09-11T21:36:00+00:00", "cash": "1000", "qty": "0", "pending": 0}
  ```

  - `cash` et `qty` sont **les deux lectures probantes**.
  - `pending` est vide **par construction** : sur le chemin grok, les ordres vivent dans la stratégie interne, créée
    dans `run` (`backtest.py:2893-2895`).
  - Cette preuve vaut **DÉCLARÉ**, jamais plus (§ B.2 l.889-891).
- **`invocation`** : `{"single_call": true}`.
- **`period`** : `{"start": T, "end": fin}`.

### 4. Chemin désigné : séries et contrôles

- **`first_fill_at` non nul et strictement après `T`.**
  - Au moins un remplissage est attendu en 107 jours de grille.
  - `T` (21:36) ne tombe sur aucune bougie 5 min, donc le premier remplissage possible est au plus tôt à
    `2020-09-11T21:40Z`.
  - S'il est nul, c'est un **constat** : l'admission refuse alors l'artefact en R0 (§ L.1). Le chemin est exercé,
    mais la preuve c5 manque.
- **`equity_daily`** : `start = T`, `end = fin`, **109 points**.
  - Dérivation : `T`, puis les 107 minuits du 2020-09-12 au 2020-12-27, puis `fin`. C'est la grille
    `daily_grid(T, fin)`.
- **Contrôles internes verts.**
  - Identité `net_pnl` vérifiée à 1e-6 près.
  - Estampille de liquidation dans la cellule quotidienne finale, sauf si `trades == 0`.
  - E10 : `passed_params` égal aux paramètres du manifeste plus la paire.

### 5. Admission

`cc.evaluation_admission` rend **`false`** sans lever : l'évaluation est réelle et admise, avec ses trois porteurs.

### 6. Continuité

`c3_continuity` rend le **code 0**.

| Clause | Attendu | Pourquoi |
|---|---|---|
| **c1** | `DECLARED` | § B.2 |
| **c2** | `DECLARED` | § B.4 : un seul appel, grille de 109 points |
| **c5** | `DECLARED` | § C.3 |
| c3 | `VERIFIED` | Identités exactes avec lots exportés. Elles tiennent aussi quand rien n'est liquidé : un bloc à `trades == 0` avec `lots == []` passe les identités |
| c4 | `VERIFIED` | Voir la dérivation ci-dessous |
| comparateur | `VERIFIED` | **Synthétique, sans valeur** |
| agrégat | `DECLARED` | |

Dérivation de c4, sur les séries de décision `[1w, 4h]` :
- Le 1 w ETH/USDT commence au 2019-01-14 (import du 23/09) et n'a aucun trou avant 2022. Il y a 87 estampilles
  `≤ T`, du 2019-01-14 au 2020-09-07, pour 50 exigées : le régime 1 w lit l'EMA 50 (`backtest.py:305`, besoins de la
  grille `:420-425`).
- ETH/USDT a quatre trous 4 h connus : le 2019-03-12, le 2019-05-15, le 2019-08-15 et le 2020-02-19. Aucun ne dépasse
  deux bougies, et tous précèdent `T` de plus de six mois. Ils sont donc hors de l'amorçage 4 h, qui ne remonte que
  de quelques semaines avant `T` (`results/data_inventory_usdt_2019_20260923/inventory.md`).

### 7. Base

`alembic current` identique avant et après : `c3bd1e7a0001 (head)`. Le producteur lit en lecture seule, assertée par
Postgres.

### 8. Bornes des lectures

- Toutes les lectures du producteur sont bornées à `≤ fin = 2020-12-28T00:00Z`.
- L'amorçage le plus ancien remonte à `T − 400 j`.
- **Aucune donnée de la fenêtre de campagne (`2021-03-01 → 2026-06-29`) n'est lue.**

## Règles en cas d'écart

- Tout écart à un item est un **constat** écrit au rapport. Aucune relance n'a lieu avant son diagnostic.
- Un correctif du producteur est un commit de plus. Il repasse par Bruno avant tout nouveau lancement.
- Seule une panne du pilote lui-même (par exemple un code 127) se relance après correction du pilote.
- Chaque lancement est consigné, avec son `status.txt`.
