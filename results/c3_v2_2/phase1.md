# C3 — Amendement v2.2 du protocole : phase 1 (lecture seule)

> **Chantier** : brief `agent/AGENT_C3_AMENDEMENT_V2_2.md` (Bruno, 29/09). Branche `feat/c3-amendements-v2.2`
> depuis `dev` @ `8689636`. Le commit `3bd3365` suit le brief.
>
> **Portée de ce document** : c'est le livrable de la phase 1 et le seul fichier écrit en phase 1. Aucune ligne de
> `scripts/audit/`, `src/`, tests ou protocole n'est touchée ; aucun run n'est lancé ; aucune base n'est ouverte ;
> aucun tunnel n'est ouvert.
>
> **État** : les décisions de Bruno sur ce rapport ont été données au plan, le 29/09 ; elles sont consignées au § 10.
> STOP court : Bruno relit ce rapport pour vérifier qu'il consigne fidèlement ses décisions. Son GO ouvre la
> phase 2.
>
> Les faits lus dans le code sont tagués **[v]**, avec leur `fichier:ligne`, au SHA `8689636`.

## § 0 — Préalables et contrôle

- **Protocole lu** : `docs/protocole_c3.md` v2.1. Son sha256 a été vérifié **avant toute lecture** :
  `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129`.
- **Le producteur n'a pas changé depuis le run 4b.** `git diff 459190a 8689636 -- scripts/audit src` est
  vide. Le code de `dev` est donc celui qui a produit les sorties archivées du 4b. Ce qui est dit d'elles au § 4
  se déduit de ce code, **sans les lire**.
- **Règle de non-lecture.**
  - Aucune archive C3b n'a été lue, listée ni hachée : ni `~/archive`, ni le serveur.
  - Trois fichiers **versionnés** ont été ouverts, pour y compter des noms de clés, et pour rien d'autre :
    - `results/c3b_producteur/prefix_conformite/server/run1/observations.json` ;
    - `results/c3b_producteur/prefix_conformite/server/chain/selection.json` ;
    - `results/c3b_producteur/eval_conformite/server/designated/run1/evaluation_run.json`.
  - Un premier comptage a été fait par un sous-agent, restreint à `git ls-files results`, avec la consigne de
    ne rendre que des comptes. Le script ci-dessous le refait, et **c'est lui qui fait foi**.
  - Il y a un écart : le sous-agent avait rendu 15 `projection_sha256` pour `selection.json`. Le script compte
    la clé exacte et rend 13. Ce sont 12 entrées par candidat **[v]** `c3_select.py:180` et une table de premier
    niveau **[v]** `:584`. Ce compte ne dit que le nombre de candidats, déjà public : il ne révèle rien de
    l'issue.
- **Pas de pytest en phase 1** (décision de Bruno, 29/09). Le dépôt ne change que par deux `.md`. Le décompte
  3 264 / 6 / 24 est celui de la clôture C3b au même code. La suite tournera au `gate.sh` de la phase 2.

Le script de contrôle est lancé par `bash`, depuis le scratchpad de la session. Son texte :

```bash
#!/bin/bash
set -o pipefail
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
BASE=8689636
SHA_V21=9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129
COUNTED=(
  results/c3b_producteur/prefix_conformite/server/run1/observations.json
  results/c3b_producteur/prefix_conformite/server/chain/selection.json
  results/c3b_producteur/eval_conformite/server/designated/run1/evaluation_run.json
)
KEYS=(min_order_usdc gross_usdc projection_sha256)
rc=0
echo "# HEAD $(git rev-parse --short HEAD) branche $(git branch --show-current)"
sha=$(shasum -a 256 docs/protocole_c3.md | cut -d' ' -f1)
echo "protocole_sha256=${sha}"
if [ "$sha" = "$SHA_V21" ]; then echo "protocole_v21_inchange=0"; else echo "protocole_v21_inchange=1"; rc=1; fi
echo "## git diff --stat ${BASE} HEAD"
git diff --stat "$BASE" HEAD
echo "## fichiers suivis modifiés / non suivis (git status --porcelain)"
git status --porcelain
echo "## fichiers comptés : versionnés ?"
for f in "${COUNTED[@]}"; do
  if git ls-files --error-unmatch "$f" > /dev/null 2>&1; then v=0; else v=1; rc=1; fi
  echo "versionne=${v} ${f}"
done
echo "## occurrences de clés (grep -o | wc -l), rien d'autre n'est imprimé"
for f in "${COUNTED[@]}"; do
  for k in "${KEYS[@]}"; do
    n=$(grep -o "\"${k}\"" "$f" | wc -l | tr -d ' ')
    echo "${k}=${n} ${f}"
  done
done
echo "rc=${rc}"
exit "$rc"
```

Sa sortie, avant l'écriture de ce fichier, au commit `3bd3365`, avec un code de sortie de 0 :

```
# HEAD 3bd3365 branche feat/c3-amendements-v2.2
protocole_sha256=9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129
protocole_v21_inchange=0
## git diff --stat 8689636 HEAD
 agent/AGENT_C3_AMENDEMENT_V2_2.md | 181 ++++++++++++++++++++++++++++++++++++++
 1 file changed, 181 insertions(+)
## fichiers suivis modifiés / non suivis (git status --porcelain)
## fichiers comptés : versionnés ?
versionne=0 results/c3b_producteur/prefix_conformite/server/run1/observations.json
versionne=0 results/c3b_producteur/prefix_conformite/server/chain/selection.json
versionne=0 results/c3b_producteur/eval_conformite/server/designated/run1/evaluation_run.json
## occurrences de clés (grep -o | wc -l), rien d'autre n'est imprimé
min_order_usdc=12 results/c3b_producteur/prefix_conformite/server/run1/observations.json
gross_usdc=66 results/c3b_producteur/prefix_conformite/server/run1/observations.json
projection_sha256=0 results/c3b_producteur/prefix_conformite/server/run1/observations.json
min_order_usdc=0 results/c3b_producteur/prefix_conformite/server/chain/selection.json
gross_usdc=0 results/c3b_producteur/prefix_conformite/server/chain/selection.json
projection_sha256=13 results/c3b_producteur/prefix_conformite/server/chain/selection.json
min_order_usdc=0 results/c3b_producteur/eval_conformite/server/designated/run1/evaluation_run.json
gross_usdc=1 results/c3b_producteur/eval_conformite/server/designated/run1/evaluation_run.json
projection_sha256=0 results/c3b_producteur/eval_conformite/server/designated/run1/evaluation_run.json
rc=0
```

`versionne=0` veut dire « suivi par git ». Les trois fichiers le sont, donc la règle de non-lecture n'a pas été
franchie.

## § 1 — Les cinq sorties code 1 hors table § I.1

Toutes sortent de la même façon : par une exception que personne ne rattrape. On obtient un code 1 avec une
trace, mais **ni artefact de diagnostic `invalide: true`, ni ligne `VIOLATION`**. Pourtant le § I.1 v2.1
(« Forme d'un diagnostic ») et le § L.4 (« codes de sortie ceux de la table ») prescrivent une forme.

Pour chaque sortie, la situation, la catégorie que j'ai proposée et la décision (détail au § 10) :

| # | Site | Situation | Proposé | Décision (29/09) |
|---|---|---|---|---|
| 1 | `c3_anchor.py:335` | Le registre fourni (`--registry`) porte un non-fini (un jeton `NaN` que `read_json` accepte) dans un enregistrement **autre** que celui de la variante. `load_registry` ne contrôle que la forme **[v]** `:132-143`. Quand une variante nouvelle s'enregistre, la réécriture du registre fait lever le writer strict. Le texte prescrit la ligne 15, puisque c'est une valeur fournie non finie (frontière du § I.1), et donc un diagnostic. | (c) | **(c)** |
| 2 | `c3_benchmark.py:166-168` (aussi `:436-438`, `:504-506`) | Le B&H est construit sur des bougies **finies**. Soit la NAV `Decimal`, passée en `float` dans `to_dict`, déborde. Soit `returns` est écrit non fini alors que `all_finite` est faux, la paire étant déjà non comparable **[v]** `:249`, `:278`. Dans les deux cas le writer lève. Le texte prescrit § C.5 (finitude) puis § C.6 : paire non comparable, candidats `NOT_ESTIMABLE`, code 0. Il ne dit rien de la représentabilité d'une NAV `Decimal`. | (c) au sens large | **(c)** |
| 3 | `c3_select.py:294-297` (aussi `:368-371` ; `:402` injoignable par ce chemin) | Une NAV de préfixe finie mais extrême : un rapport de deux points déborde le double, d'où un rendement ±inf et un σ ou un MDD non finis. Le D4 du code est `domain_ok` **[v]** `:342` : il ne teste pas « tous finis », ce qui est un écart au texte de D4. `mdd_report` et `recomputed` sont écrits quel que soit le premier gate en échec, et le writer lève. Le texte prescrit D4 (§ A.8 : « définis et tous finis »), c'est-à-dire la ligne 6 : candidat retiré, code 0. | (c) au sens large | **(c)** |
| 4 | `c3_verdict.py:413` | `evaluation.estimability` est optionnel et C3b ne l'écrit jamais. Il est recopié entier dans `estimabilite.declared`, alors que seuls `E1`, `E2` et `ok` y sont typés. Un autre champ non fini fait lever le writer. Le texte prescrit la ligne 15 (valeur fournie non finie). | (c) | **(c)** |
| 5 | `cc.recompute_daily` → `cc.cagr_pct` (`math.exp`) **[v]** `c3_common.py:732`, `:1625` | Le chemin chaîne l'emprunte dans `c3_benchmark` **[v]** `:266`, `:310`, `:433` et dans `c3_select` **[v]** `:280`. `OverflowError` n'est pas une `cc.*Error`, et aucun `main` ne l'attrape, pas même `chain`, qui exécute les étapes en processus. Le cas : un CAGR de préfixe qui déborde sur des rendements finis. C'est impossible sur un préfixe de 1362 j avec des doubles, possible sur une fenêtre courte. D4 passe, et rien ne couvre ce cas. | (c), alternative (b) | **(b) → AM-10**, qui étend D4 |

- **Réserve que j'avais écrite sur les cas 2 et 3.** Si « (c) » ne visait que le diagnostic de la ligne 15, ces
  deux cas n'entraient dans aucune des trois catégories. Bruno a tranché : (c) s'entend « le texte prescrit une
  forme, le code en produit une autre », que cette forme soit un diagnostic ou non.
- **Constat annexe, hors (C), versé à l'outillage.** Côté producteur, `cb.build_pair` est appelé à
  `c3b_evaluate.py:544`, **hors** du `try` de l'étape 10b **[v]** `:1089-1118`. Une `OverflowError` y sort en code
  1 avec une trace, alors que le contrat du producteur est 0/2/3.

## § 2 — Inventaire des tests-miroirs

**Les cinq tests qui relisent un document à l'exécution :**
1. `test_c3_common.py:552` — la ligne `**sha256 v2.1 :**` de la section « Adoption » de
   `amendements_c3_v2.1.md` égale le sha du protocole.
2. `test_c3_common.py:562` — « exactement deux » empreintes dans cette section, et aucune dans un `.py`.
3. `test_c3_common.py:574` — le bloc § H.1.
4. `test_c3_verdict.py:3167` — la table § B.8 et la phrase de précédence.
5. `test_c3b_evaluate.py:1001` — la tolérance du § B.2.

Tous les autres miroirs sont des **copies en dur** :
- `REASONS_H1`, `TABLE_I1`, `ADMISSIBLE_STATES_6_4`, `TABLE_6_4`, `REAL_CARRIERS_L1`, `NINE_FIELDS` ;
- les ensembles de la liste blanche dans `test_c3_chronology.py:287` ;
- `BASE_QUANTITY_STEMS`, les valeurs V21 de `test_c3_anchor.py:98-111`, `COMBINATIONS_F2H`,
  `REPLAY_ENVIRONMENT_FIELDS`, `TEXT_COMBINATIONS`.

Aucun test ne relit le § 0.7, le § M, le § L.1, le § L.2 ni `CONTRAINTES_POST_B4.md`.

**Motif (ii), validé le 29/09.** L'attendu est réécrit sur le texte v2.2 (règle 3 : appui cité), puis marqué
`xfail(strict=True, reason="R-xx …")`. Le test est rouge-avant par construction, et le XPASS du chantier outillage
forcera la levée du marqueur. **(i)** : mis à jour dans le commit de l'AM, vert tout de suite.

| AM | Tests touchés | Traitement |
|---|---|---|
| AM-00 (en-tête, sha) | `test_c3_common.py:552` passe au rouge dès le premier commit qui touche le texte | **pont** `xfail(strict=True, reason="en attente AM-00 …")`, posé au premier commit de texte et levé au commit AM-00 ; ensuite (i), généralisé (`ADOPTED_PACKAGE` → v2.2, **dernière** ligne `**sha256 vX.Y :**`) |
| AM-00 | `test_c3_common.py:562` | (i) : le compte devient celui de la table, trois empreintes |
| AM-00 | `test_c3_entry.py:709`, `test_c3_verdict.py:2501` (refus du livrable C3a par `c3_anchor`) | inchangés : ce sont des témoins, et le refus tient sous v2.2 |
| AM-01, AM-02 | aucun miroir | témoins : `tests/test_strategies/test_grid_v4_decision_timeframes.py`, `tests/test_scripts/test_warmup_at.py` |
| AM-03 (+7) | `test_c3_verdict.py:2551` (parseur `chain` : `candles`, `evaluation`, `benchmark_eval`… mais pas `candles_eval`) | (ii) |
| AM-03 | nouveaux adverses | (ii) : `returns_config` ≠ recalcul sur `equity_daily` → violation ; λ déclarés ≠ `benchmark.json` → violation ; `returns_bench` ≠ recalcul sur `candles_eval.json` → violation ; `candles_eval.json` portant une estampille postérieure à `fin` ou une autre paire → refus |
| AM-04 | `test_c3_chronology.py:287` (contrats : `min_order_usdc`), `test_c3_entry.py:244` (chemin obligatoire `min_order_usdc`), `:310` (lot `gross_usdc`), `:446` (D5 sur `min_order_usdc`), `test_c3b_common.py:751` (lot `gross_usdc`) | (ii) |
| AM-04 | `test_c3_anchor.py:273` (chemin obligatoire du manifeste `min_order_usdc`) | (ii) : la clé du manifeste devient `min_order_quote` (décision 29/09) |
| AM-04 | fixtures `test_c3_common.py:893`, `:1067`, `:1086`, `:1169` | **non touchées ici** : ce sont des artefacts simulés, renommés avec le code au chantier outillage |
| AM-04 | nouvel adverse | (ii) : un bloc qui porte `gross_usdc` → erreur de forme nommant `gross_quote` |
| AM-05 | tests du registre, `test_c3_anchor.py:45` à `:583` | inchangés : parenté et idempotence tiennent |
| AM-05 | nouveaux adverses | (ii) : seconde campagne comptée sur la même famille → refus ; relance au-delà de l'unique → refus ; statut compté écrit par `c3_verdict` à l'étape 6 |
| AM-06 | `test_c3b_evaluate.py:1401` (`comparator_not_buildable` : code 2, rien écrit) | (ii) : un artefact de refus est écrit |
| AM-06 | nouvel adverse | (ii) : la chaîne sur une évaluation refusée donne `E_NO_BENCHMARK` avec son motif, code 0, verdict publié |
| AM-08 | `test_c3b_evaluate.py:924` (sans trade, `first_fill_at` nul refusé par l'admission) | (ii) : admis, c5 `NON VÉRIFIABLE` |
| AM-08 | `test_c3_continuity.py:201`, `test_c3_verdict.py:1864` et `:1898`, `test_c3_verdict.py:1949` (c1 ou c5 `NON VÉRIFIABLE` sur une évaluation réelle → violation) | (i) : les docstrings citent le texte v2.2. L'attendu reste le même, parce que ces fixtures portent un remplissage ; il faudra les compléter du porteur `metrics.total_trades` à l'outillage |
| AM-08 | nouveaux adverses | (ii) : réelle sans trade → admise, c5 `NON VÉRIFIABLE`, sans violation, `validé` inatteignable ; toute contradiction entre `first_fill_at` nul, `total_trades == 0` et `equity_daily` constante égale à `C` → violation |
| AM-09 | `test_c3b_common.py:1119` (`coverage_no_covered_unit` : refus) | (ii) : dates nulles écrites |
| AM-09 | `test_c3_entry.py:801` (dates hors fenêtre → I-A.7) | inchangé |
| AM-09 | nouveaux adverses | (ii) : `covered_units == 0` avec des dates nulles → admis (D1 échoue sur la paire) ; dates nulles avec `covered_units > 0` → violation ; dates non nulles avec `covered_units == 0` → violation |
| AM-10 (D4, cas 5) | aucun miroir | (ii) : un CAGR de préfixe qui déborde sur des rendements finis → candidat retiré par D4, code 0 |
| AM-11 (§ F.8) | aucun miroir | texte seul |
| § H.1, § B.8 relus à l'exécution | `test_c3_common.py:574`, `test_c3_verdict.py:3167` | inchangés. Aucun AM ne touche la liste du § H.1. AM-08 touche le paragraphe « Ce qu'exige `validé` » du § B.8, pas sa table ni sa phrase de précédence : ce sera vérifié à l'application |

## § 3 — Où la liste blanche § A.7 est reflétée (portée réelle d'AM-04)

**`min_order_usdc`**
- **Liste blanche** : `PREFIX_WHITELIST_CONTRACTS` **[v]** `c3_common.py:1525`, lu par `project_prefix`
  **[v]** `:1537`.
- **D5** **[v]** : `c3_entry.py:264`, `:318-320` ; `c3_select.py:231-233`.
- **Manifeste** **[v]** `c3_common.py:1316`. Le protocole ne nomme pas cette clé.
- **Export du producteur** **[v]** `c3b_common.py:415`. L'argument du moteur `min_order_usdc=` **[v]**
  `c3b_common.py:314` et `scripts/backtest.py` ne bougent pas (décision 29/09).

**`gross_usdc`**
- **Bloc et lots** **[v]** : `c3_common.py:1943`, `:2038`, `:2078`.
- **Forme** **[v]** : `c3_entry.py:155`, `:175`.
- **Export** **[v]** `c3b_common.py:345` : la clé est écrite par `lots_from_trades` et, dans le bloc,
  transmise par `liquidation_block` **sans renommage**. La table de renommage `LIQUIDATION_RENAME` **[v]**
  `:69-73` ne porte que les trois `_btc`, et la garde de reste **[v]** `:368` ne cherche que `_btc`.

**Constats**
- **La chaîne n'a aucune garde `_usdc` / `_usdt`** : `BASE_QUANTITY_STEMS` **[v]** `c3_common.py:1873-1878`
  n'a pas `gross`. Il faudra une garde symétrique de `check_base_quantity_keys`.
- **Lecteurs hors C3** des sorties des runners (`rejeu_validate_campaign.py`, `b4_p6_checkpoint.py`,
  `b4_p7_checkpoint.py`, `generate_p6_report.py`, `run_p6_walkforward.py`, `c1_equity_probe.py`) : ils lisent
  les sorties inchangées des runners et gardent `_usdc`.
- **`src/`** : aucune occurrence.
- **L'empreinte de projection change.** `projection_sha256 = sig(π_T(O))` **[v]** `c3_select.py:275` : π_T
  porte les contrats et la liquidation entière, donc renommer l'une des deux clés change l'empreinte de
  projection de **chaque** candidat. **Pas son identité** : `sig{strategy, pair, params}` **[v]**
  `c3_common.py:688-694`.

## § 4 — Conformité des artefacts C3b sous v2.2

Pour chaque attendu de Bruno, je confirme ou j'infirme. Le détail des comptes est au § 0.

- **Préalable, qui infirme en partie l'attendu.** Ce n'est pas AM-04 qui rend d'abord tout non rejouable, c'est
  l'en-tête (AM-00). Tous les artefacts de chaîne versionnés de C3b portent le sha v2.1 : en-têtes `protocole`,
  et `protocol_sha256` du manifeste du lot 3. Sous v2.2, `c3_anchor` **[v]** `:103-108` refuse ce manifeste,
  comme il refuse sous v2.1 le livrable C3a. Les artefacts C3b deviennent donc un **historique v2.1**, quel que
  soit le contenu des AM ; il n'y a rien à régénérer.
- **AM-04 : confirmé, avec une précision.**
  - `observations.json` porte 12 `min_order_usdc` et 66 `gross_usdc` ; l'`evaluation_run.json` désigné du 4a
    porte 1 `gross_usdc`. Sous v2.2 ce sont des erreurs de forme (ligne 2).
  - Les 12 empreintes de projection de `selection.json` ne sont plus recalculables à l'identique.
  - **Les identités de candidat ne changent pas** : c'est l'empreinte de projection qui change. Le brief
    confondait les deux.
- **AM-03 : confirmé, avec un complément.** L'`evaluation.json` du 4b est archivé et non lu, mais il a été
  produit par le code de `dev` (§ 0).
  - Il **ne porte aucun λ**. Seul `evaluation_sensitivity.json` les porte **[v]** `c3b_evaluate.py:748`, et
    aucune étape de la chaîne ne le lit.
  - `candles_eval.json` est produit, mais il n'est pas une entrée de la chaîne : aucun module `c3_*` ne le lit.
- **AM-06 : à nuancer selon la forme.**
  - Forme retenue (A, même fichier) : aucune entrée n'est ajoutée, et une évaluation non refusée reste conforme.
  - Sous la forme B, une huitième entrée, présente au seul refus, aurait manqué.
- **AM-08, AM-09 : confirmé, ils ne cassent rien.** Ce sont des élargissements, et ils ne peuvent pas rendre
  non conforme un artefact déjà admis. Cela se déduit sans rien lire.
  - Pour AM-08, le recoupement `first_fill_at` ⟺ `total_trades` ⟺ `equity_daily` constante (décision 29/09)
    demande un porteur que les artefacts C3b n'ont pas. Il est déjà hors de portée, sous l'historique v2.1.
- **AM-05** : le registre `prefix_conformite/server/chain/variants.json` ne porte ni la famille ni le statut
  compté. Il est non conforme au registre v2.2.
- **AM-01, AM-02, AM-11** : texte seul, sans effet sur un artefact.
- **AM-10** : les artefacts du préfixe 2020 portent des rendements finis sur une fenêtre de 250 j environ. D4
  étendu ne les touche que si leur CAGR déborde, ce qui aurait fait sortir `c3_benchmark` en trace (code 1,
  cas 5 du § 1) ; or tous les codes du run sont à 0 **[v]** `results/c3b_producteur/report.md` § 2, lot 3.

## § 5 — AM-06 : les deux formes et ce que chacune coûte

**A — même fichier : proposée, puis retenue (§ 10).**
- **Forme** : un bloc `refused: {reason: "comparator_not_buildable", window, motif}`, sans séries, dans
  `evaluation.json`.
- **§ L.1** : les entrées ne changent pas. L'admission gagne une route « refus → étape 6, sans contrat § B », et
  `benchmark_eval.json` n'est pas exigé sur cette route.
- **§ L.2** : il faut écrire « état de la continuité : sans objet ». `chain.verified` ne change pas.
- **Risque** : le schéma devient conditionnel. `refused` accompagné de séries → violation ; ni l'un ni les autres
  → ligne 2.
- **Atout, décisif** : avec la septième entrée d'AM-03 (`candles_eval.json`), la chaîne **rejoue** la
  non-constructibilité par `cb.build_pair`. Le refus est alors recoupé, et plus seulement déclaré.

**B — fichier séparé.**
- **Forme** : une huitième entrée au § L.1, en disjonction exclusive avec l'évaluation.
- **Coût** : une entrée de plus à hacher (`inputs_sha256`, `verify_chain` **[v]** `c3_verdict.py:940`) et à
  exposer au parseur `chain`. Même valeur « sans objet » au § L.2.
- **Atout** : le schéma de l'évaluation reste univoque.

**Fait lu.** Aujourd'hui, le refus sort en code 2 **avant le moteur**, et rien n'est écrit **[v]**
`c3b_evaluate.py:555-558`, `:912-914`. La chaîne n'a donc rien à lire, et `E_NO_BENCHMARK` est inatteignable.

## § 6 — Précisions nécessaires à la rédaction (posées au plan ; réponses au § 10)

1. **AM-03, λ.** `evaluation.json` doit **déclarer** les λ utilisés, ce qui demande un export du producteur.
   - `c3_verdict` ne lit pas `benchmark.json` aujourd'hui **[v]** `INPUT_NAMES`, `c3_verdict.py:111`, et
     `verify_chain` ne le hache pas.
   - Pour `candles_eval.json`, la chaîne peut lire comme le producteur :
     `cb.load_candles(…, replace(manifest, candidates=(candidate,)), end=fin)` **[v]** `c3b_evaluate.py:540`. Ce
     lecteur refuse déjà une estampille postérieure à `fin` **[v]** `c3_benchmark.py:91-95`.
2. **AM-03 × AM-06, motif « recalcul » : la frontière est à écrire.**
   - Recalcul **impossible** (l'entrée ne le permet pas) → `E_NO_BENCHMARK`, motif distinct.
   - Recalcul **possible et différent** → violation (ligne 15).
3. **AM-03 × § 0.7.**
   - Le § F.2 (d) et le § J item 12 disent « les séries quotidiennes restent déclaratives ». Ce sera faux pour
     `returns_config` et `returns_bench` : ils doivent renvoyer au § L.2 dans le même AM.
   - Ligne proposée au § 0.7 : « Recoupements → § L.2 ».
4. **AM-04** : la clé du manifeste, que le texte ne nomme pas.
5. **AM-05.**
   - Où la famille est-elle déclarée ?
   - Qui écrit le statut compté après l'étape 6 ? Aujourd'hui, le registre n'est écrit qu'à l'étape 1 **[v]**
     `c3_anchor.py:334-335`.
   - Comment s'articuler avec le § K.1 (« ce protocole […] ne le contient pas ») ?
6. **AM-08.** `evaluation.json` ne porte **aucun compte de trades**.
   - `liquidation.trades` ne compte que les liquidations forcées **[v]** `scripts/backtest.py:3288`.
   - `metrics` ne porte que `{net_pnl, cagr_pct, delta_dd}` **[v]** `c3b_evaluate.py:650-691`.
   - `first_fill_at` est nul si et seulement si le moteur n'a aucun trade **[v]** `c3b_evaluate.py:394-398`.
7. **Numérotation** des AM et des réserves.
8. **Tests adverses neufs**, un par réserve.
9. **`results/INDEX.md`.**

## § 7 — Défauts et constats hors table (consignés, non corrigés ici)

- **D4 du code ≠ D4 du texte.** Le code n'a que `domain_ok` **[v]** `c3_select.py:342`, là où le texte dit
  « définis et tous finis ». C'est un défaut d'outillage (cas 3 du § 1), qui s'étend par AM-10 au CAGR.
- **Producteur** : l'`OverflowError` de `cb.build_pair` sort hors du `try` **[v]** `c3b_evaluate.py:544` (§ 1).
  C'est un défaut d'outillage.
- **Nom de test périmé** : `test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_v21`
  (`test_c3_entry.py:709`). Le brief le veut inchangé ; il est seulement noté.
- **Note « postérieure au gel » de v2.1** (§ F.8 : `cc.cagr_pct`, `math.fsum`, à la sélection ; chemin `numpy` du
  § F.2 (c) à l'évaluation). v2.1 la nommait candidat v2.2, et elle manquait à la table du brief. **Décision
  29/09 : traitée dans v2.2 (AM-11)**, et non reportée en v2.3.

## § 8 — Ordre d'application et fichiers touchés en phase 2

**Rédaction du paquet** `docs/amendements_c3_v2.2.md` : AM-03 et AM-06 sont écrits **avant** AM-05. Un statut
compté doit lire l'état « sans objet » de la continuité et le refus recoupé. Ensuite viennent les autres, puis
l'en-tête, la table candidat → AM, « Vérifié, sans amendement » et l'ordre d'application.

**Application**, un commit par AM, dans l'ordre des sections. Chaque commit porte le texte et ses miroirs (i)
et (ii).

| # | AM | Section(s) | Note |
|---|---|---|---|
| 1 | AM-05 | § A.6 (famille au manifeste, statut compté écrit à l'étape 6, renvoi à CONTRAINTES § 10.1 sans reformulation) ; § K.1 : renvoi éventuel au § A.6, fixé à la rédaction | pose le **pont** `xfail` du test sha |
| 2 | AM-04 | § A.7, ligne Contrats (`min_order_quote`) et ligne Comptabilité (`gross_quote`, garde des suffixes de monnaie) | |
| 3 | AM-09 | § A.7 (couverture : dates nullables ssi `covered_units == 0`) | |
| 4 | AM-10 | § A.8 D4, l.454 (« … et le CAGR annualisé qui en découle, fini ») | |
| 5 | AM-01 | § A.8, l.515 (`grid_levels`) | |
| 6 | AM-02 | § A.8, l.604-606 (« alimente une porte de décision ») | |
| 7 | AM-06 | § C.5 (refus ratifié, lu et recoupé ; motif) ; § L.1 (route d'admission) ; § L.2 (« sans objet ») | |
| 8 | AM-11 | § F.8 (les deux chemins, l'écart borné, sans effet décisionnel) | |
| 9 | AM-08 | § L.1 (admission : `first_fill_at` nul ssi zéro trade, triple recoupement) ; § B.8 (« Ce qu'exige `validé` ») | |
| 10 | AM-03 (+7) | § L.1 pas 0 (sept entrées) ; § L.2 (principe et trois recoupements, lieux de lecture) ; § F.2 (d), § J 12 (renvois) ; § 0.7 (ligne) | |
| 11 | AM-12 | § M, index régénéré | |
| 12 | AM-00 | en-tête, bloc « Amendements — v2.2 », sha | levée du pont |

Ensuite :
- **STOP** : lecture adverse de Claude sur AM-03, AM-06 et AM-08, consignée ; Bruno adopte.
- Commit Adoption.
- Tests du sha généralisés.
- Propagation `docs`.
- `outillage_v2_2.md`.
- `gate.sh` et `report.md`.
- **STOP** avant push.

**Fichiers touchés, liste exhaustive**
- `docs/amendements_c3_v2.2.md` (neuf) et `docs/protocole_c3.md`.
- `tests/test_scripts/test_c3_common.py`, `test_c3_chronology.py`, `test_c3_entry.py`, `test_c3_continuity.py`,
  `test_c3_verdict.py`, `test_c3_anchor.py`, `test_c3_select.py` (AM-10), `test_c3_benchmark.py` (AM-10),
  `test_c3b_common.py`, `test_c3b_evaluate.py`.
- Propagation : `CLAUDE.md`, `skills/backtest.md`, `docs/RESEARCH_LOG.md` (entrée 18), `PROJECT_CONTEXT.md`
  (§ 1, § 9), `ROADMAP.md`, `docs/CODE_MAP.md` (en-tête), `results/INDEX.md` (une ligne).
- `results/c3_v2_2/` : `phase1.md`, `outillage_v2_2.md`, `report.md`, et `tests/*.sh` avec leurs `.out`
  (dont `gate.sh`).

**Jamais touchés**
- `scripts/audit/*.py`, `src/`, `scripts/backtest.py`, les runners P6/P7, `scripts/compute_benchmarks.py`.
- `results/c3a_entry_validation/`, `results/c3b_producteur/`, `docs/CONTRAINTES_POST_B4.md`.

## § 9 — Décisions demandées (telles que soumises au plan)

1. La classification (C), avec la réserve sur les cas 2, 3 et 5.
2. La forme de l'artefact de refus d'AM-06.
3. L'inventaire (i) / (ii) et le motif « réécrire, puis `xfail` strict ».
4. Le pont `xfail` du test sha.
5. La numérotation des AM et des réserves.
6. La clé du manifeste (AM-04).
7. Les trois précisions d'AM-05, et le doute § 0.7.
8. Le porteur « zéro trade » (AM-08).
9. La ligne § 0.7 d'AM-03.
10. Un adverse neuf par réserve.
11. `results/INDEX.md`.
12. Le sort de la note du § F.8.
13. La confirmation de la table du brief.

## § 10 — Décisions de Bruno (29/09), consignées

- **Lectures acceptées telles quelles.**
  - Les identités de candidat ne changent pas avec AM-04 ; seule l'empreinte de projection change.
  - C'est AM-00 qui rend d'abord les artefacts C3b historiques.
- **Exécution de la phase 1.**
  - Pas de pytest : un tunnel ouvert pour rien est l'incident de C3b.
  - Le § 0 nomme les fichiers comptés, chemin par chemin, vérifiables sans avoir à croire.
- **1. Classification.** (c) s'entend « le texte prescrit une forme, le code en produit une autre »,
  diagnostic ou pas.
  - Cas 1 à 4 : **(c)**, aucun texte.
  - Cas 5 : **(b)**. D4 dit « rendements définis et tous finis » ; sur des rendements finis dont le CAGR
    déborde, D4 passe et rien ne couvre.
    - Correctif, **AM-10** : étendre D4 (§ A.8 l.454), « … et le CAGR annualisé qui en découle, fini ». On
      tombe en ligne 6, candidat retiré, code 0.
    - Pas la ligne 15 : une valeur calculée n'est pas une valeur fournie. La symétrie avec le § F.2 (e) tient :
      au préfixe il y a un candidat à retirer, à l'évaluation il n'y en a pas.
  - Le constat `c3b_evaluate.py:544` va à l'outillage.
- **2. AM-06 : forme A, même fichier.**
  - Avec `candles_eval.json`, la chaîne rejoue la non-constructibilité : le refus est recoupé.
  - `refused` avec séries → violation ; ni l'un ni les autres → ligne 2.
  - Au § L.2 : « état de la continuité : sans objet ».
- **3. Inventaire (i) / (ii)** et motif « réécrire sur v2.2, puis `xfail` strict » : validés.
- **4. Pont `xfail` du test sha** : accepté. Son `reason` dit « en attente AM-00 » : ce n'est pas une réserve.
- **5. Numérotation** : AM-01 à AM-09 sur les candidats, AM-07 est un renvoi, AM-10 et suivants pour les (b),
  les réserves à partir de **R-15**.
  - Application que je propose, sans objection au plan : **AM-11** pour la note du § F.8, **AM-12** pour
    l'index § M, AM-00 pour l'en-tête et le sha.
- **6. Clé du manifeste** : `min_order_quote`, renommée à l'outillage ; AM-04 le nomme dans son « Impact
  outillage ».
- **7. AM-05.**
  - La **famille** est un champ du manifeste, ajouté à la liste minimale du § A.6.
  - Le **statut compté** est écrit par **`c3_verdict` à l'étape 6**, dans l'enregistrement de la variante, avec
    l'issue et la raison ; `c3_anchor` le lit à la campagne suivante. Le registre reste le pendant machine du
    `RESEARCH_LOG`, sans deux vérités.
  - **§ K.1** : renvoi à CONTRAINTES § 10.1 sans reformulation, comme AM-23. La section d'origine du critère est
    le § 10, pas le protocole. Ce n'est pas un écart au § 0.7, c'en est l'application.
- **8. Porteur « zéro trade »** : `metrics.total_trades`, déclaratif, **recoupé**.
  - `first_fill_at` nul ⟺ `total_trades == 0` ⟺ `equity_daily` constante, égale à `C`. Sans trade, il n'y a
    ni fee ni variation, et la troisième égalité est recalculable.
  - Toute contradiction entre les trois est une violation.
- **9. § 0.7** : la ligne « Recoupements → § L.2 » est ajoutée, et le § F.2 (d) et le § J item 12 sont corrigés
  dans AM-03.
- **10.** Un adverse `xfail` strict par réserve : oui.
- **11.** `results/INDEX.md` : oui, une ligne.
- **12. Note du § F.8 : dans v2.2**, pas en v2.3 — la reporter deux fois en ferait une dette.
  - AM texte seul : le § F.8 dit les deux chemins (`fsum` à la sélection, `numpy` à l'évaluation), l'écart
    borné, sans effet décisionnel déclaré.
  - Aucun outillage.
- **13. Table confirmée.**
- **Remarque sur l'ordre.** AM-05 reste à sa place dans l'ordre des sections pour l'application. Il est
  rédigé après AM-03 et AM-06 : rédaction dans un ordre, application dans l'autre, comme v2.1 (§ 8).

**Statuts d'outillage (table du brief, et décisions ci-dessus)**

| AM | Statut |
|---|---|
| AM-03 | bloquant manifeste |
| AM-04 | bloquant manifeste |
| AM-05 | bloquant campagne |
| AM-06 | bloquant manifeste |
| AM-08 | bloquant manifeste |
| AM-09 | non bloquant |
| AM-10, et le fix outillage des cas 1 à 4 | statut à fixer à la section « Adoption » ; ma proposition : **non bloquant manifeste, bloquant campagne** — ces chemins ne s'ouvrent que sur des entrées extrêmes, mais une campagne ne doit pas pouvoir sortir hors table |
| AM-01, AM-02, AM-11 | aucun outillage |
