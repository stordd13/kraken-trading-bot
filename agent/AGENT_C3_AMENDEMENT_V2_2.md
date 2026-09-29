# C3 — Amendement v2.2 du protocole (chantier documentaire)

Nouvel agent. **Plan mode en deux phases**, un STOP entre les deux. Aucun serveur, aucune base, aucun run.
Aucun changement de comportement dans `scripts/audit/` : ce chantier amende un texte et les tests qui le
recopient ; l'outillage que le texte impose est un chantier séparé, dont ce brief produit la liste close.

Branche `feat/c3-amendements-v2.2` depuis `dev` @ `8689636`. Push en fin de chantier, jamais de merge : le
merge est une décision humaine, après la porte.

## À lire d'abord

- `CLAUDE.md`, `PROJECT_CONTEXT.md` § 1 (état au 28/09) et § 9 (« Candidats amendement v2.2 », les neuf), `ROADMAP.md`
  § « C3 — Validation chronologique »
- `docs/amendements_c3_v2.1.md` **en entier** : c'est le modèle de forme (en-tête, section « Adoption », table
  brief → amendements, un AM = Clause / Avant / Après / Motif / Impact outillage / Test attendu / Statut, réserves
  R-xx, ordre d'application). v2.2 reprend cette forme sans la réinventer.
- `docs/protocole_c3.md` v2.1, sha256 `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129`
  (vérifier avant toute lecture : `shasum -a 256 docs/protocole_c3.md`), dans cet ordre : § 0.7 (une règle, une
  section d'origine), § A.6 (registre), § A.7 (liste blanche, artefact de couverture), § A.8 l.510-520 et
  l.600-610, § B.8 (états, table des actions, « ce qu'exige `validé` »), § C.5-C.6, § H.1, § I.1 (table unique,
  ligne 15, frontière ligne 2 / ligne 15), § L.1 (les six entrées hors chaîne, admission de l'évaluation réelle),
  § L.2, § M
- `docs/CONTRAINTES_POST_B4.md` § 10.1-10.2 (critère d'arrêt : ce qui compte, la relance unique, le jalon 2027-01-31)
- `results/sol_d2_1w_modes/report.md` § 8.1 (candidats 1 et 2) ; `results/c3b_producteur/report.md` § « Défauts du
  chantier » et les écarts 11, 14, 15 de `agent/AGENT_C3B_PRODUCTEUR.md` (candidats 6, 7, 8, 9 : leur origine)
- Code, **en lecture** : `scripts/audit/c3_common.py` (`evaluation_admission` ~`:1167`, `protocol_descriptor`,
  `PROTOCOL_RELPATH`), `c3_anchor.py:95-110` (recoupement du sha), `c3_continuity.py` (`comparator_block`,
  admission en tête), `c3_verdict.py` (`_evaluation_contract`, `_read_series`, `_replay`), `c3b_evaluate.py`
  (ce que porte `evaluation.json`, `benchmark_eval.json`, `candles_eval.json` ; refus `comparator_not_buildable`)
- Tests : `tests/test_scripts/test_c3_common.py:540-600` (`ADOPTED_PACKAGE`, `_adoption_section`, les deux tests
  du sha, le test « liste recopiée du bloc du texte ») et tout test qui recopie un bloc du protocole (phase 1 les
  inventorie)

## Contexte

C3b a livré le producteur conforme (28/09). En le construisant, neuf écarts entre le texte v2.1 et ce que la
chaîne fait ou devrait faire ont été consignés, jamais implémentés (« convention d'outillage non amendée »,
interdite depuis le 21/09). Le manifeste de la première campagne s'écrira contre v2.2 : `c3_anchor` recalcule le
sha du fichier et refuse tout manifeste qui en déclare un autre, donc v2.2 doit être gelée avant. Le compteur
§ 10.2 tourne depuis le 23/09 ; jalon : premier verdict grid avant le 2027-01-31. Ce chantier est borné pour
cette raison.

## Décisions déjà tranchées (Bruno, 29/09) — ne pas rouvrir

| # | Candidat | Décision | Outillage induit | Statut outillage |
|---|---|---|---|---|
| 1 | § A.8 l.515 : `grid_levels` est un axe de `decision_timeframes` | adopter | aucun | — |
| 2 | § A.8 l.605-606 : « lit le 1 w » → « alimente une porte de décision » | adopter | aucun | — |
| 3+7 | La chaîne recoupe ce que le producteur garantit : `returns_config ← equity_daily`, λ, `returns_bench` | **un seul AM** au § L.2, principe + trois lignes de recoupement, **chacune avec son lieu de lecture** (voir ci-dessous) | `c3_verdict` recoupe les trois ; **septième entrée § L.1** `candles_eval.json` | **bloquant manifeste** |
| 4 | S-1 : `min_order_usdc`, `gross_usdc` | adopter, suffixe **`_quote`** par symétrie avec AM-06 `_base` ; périmètre : **artefacts seulement** (liste blanche § A.7, clés d'observation, export producteur) ; l'argument `min_order_usdc` du moteur `backtest.py` **ne bouge pas** (hors liste, le renommage vit dans la couche d'export) | export producteur, projection `c3_select`, fixtures | **bloquant manifeste** (signature de projection = identités des candidats) |
| 5 | Enforcement du § 10.1 au registre de variantes | adopter au § A.6 : le registre porte l'état du compteur de famille, `c3_anchor` refuse une variante hors critère (seconde campagne comptée sur la même famille, relance au-delà de l'unique) | `c3_anchor`, registre | non bloquant manifeste, **bloquant campagne** (l'outillage existe avant la première campagne comptée) |
| 6 | E5 : `E_NO_BENCHMARK` inatteignable sur comparateur non constructible | amender § C.5 : le refus amont est **ratifié et lu par la chaîne**. Le producteur écrit un **artefact de refus** (identité de la configuration, fenêtre, motif) ; la chaîne le lit à l'étape 5 et publie `E_NO_BENCHMARK`. Échec du recalcul d'un comparateur admis → `E_NO_BENCHMARK` aussi, **motif distinct** (le motif est un champ de l'issue, pas une raison nouvelle : la liste § H.1 ne change pas) | producteur (artefact de refus), `c3_continuity` / `c3_verdict` (lecture) | **bloquant manifeste** (une campagne sans issue § I.1 n'est pas une campagne : le § 10.1 ne sait pas la compter) |
| 8 | `first_fill_at` nul refusé en R0 | adopter : l'admission (§ L.1) accepte `first_fill_at: null` **si et seulement si** l'évaluation porte zéro trade ; c5 = `NON VÉRIFIABLE` (§ B.8) ; conséquence à écrire : `validé` inatteignable sur cette évaluation (c5 `DÉCLARÉ` exigé), l'issue vient du § H | `evaluation_admission`, `c3_continuity` | **bloquant manifeste** (faux R0 sur une cellule sans fill) |
| 9 | Dates de couverture quand `covered_units == 0` | adopter : `first_day` / `last_day` nullables au § A.7, nuls **ssi** `covered_units == 0`, sinon violation | `c3_entry` I-A.7, producteur `coverage.json` | mineur, non bloquant |
| C | Cinq sorties code 1 hors table § I.1 | **classification en phase 1** (voir), décision de Bruno au STOP | selon classification | à décider |
| Astra | Re-passe non faite | ligne dans « Adoption » (voir « Section Adoption ») | — | — |

**AM 3+7, les trois lieux de lecture — à écrire tels quels.** Sans eux l'outillage n'est pas implémentable :
- `returns_config ← equity_daily` : dans l'artefact d'évaluation lui-même (`equity_daily` y est) ;
  `c3_verdict` recalcule par `cc.recompute_daily` et compare à `returns_config` déclaré ;
- λ : dans `benchmark.json` de l'étape 3, que la chaîne a déjà ; `c3_verdict` compare les λ que l'artefact
  d'évaluation déclare avoir utilisés à ceux de l'étape 3 ;
- `returns_bench` : recalculé depuis `candles_eval.json`, **nouvelle entrée hors chaîne** (§ L.1 pas 0 : six
  entrées → sept), par `cb.build_pair` / `cb.blend_nav` avec les λ de l'étape 3 ; règle d'entrée : **aucune
  estampille postérieure à la fin de la fenêtre d'évaluation**, une seule paire, celle évaluée (4b E3).

Une discordance sur l'un des trois est une **violation** (§ I.1 ligne 15 : le rejeu ne retrouve pas la valeur),
pas un `E_NO_BENCHMARK` : le producteur affirme une valeur que la chaîne ne retrouve pas.

**AM-6, forme de l'artefact de refus — à trancher au STOP.** Position Claude : une **forme de refus de
l'artefact d'évaluation** (même fichier, bloc `refused: {reason: "comparator_not_buildable", window, motif}`,
sans séries) plutôt qu'une huitième entrée § L.1 ; l'admission en tête de `c3_continuity` la reconnaît et la
route vers l'étape 6 sans contrat § B. Argument : une entrée de moins à hacher, à recouper, à archiver. L'agent
propose au STOP, avec l'alternative (fichier séparé) et ce que chacune coûte à § L.1 / § L.2 / `chain.verified`.

## Phase 1 — lecture seule, rapport, STOP

Livrable : `results/c3_v2_2/phase1.md`, committé. Rien d'autre n'est écrit en phase 1.

1. **Classification des cinq sorties code 1 hors table § I.1** : `c3_anchor.py:335`, `c3_benchmark.py:166-168`,
   `c3_select.py:294-297`, `c3_verdict.py:413`, `OverflowError` levée par `cc.recompute_daily` sur le chemin
   chaîne (le producteur la route en `f2_invalid_input`, code 3 ; la chaîne ne la rattrape pas). Pour chacune :
   la situation exacte (une phrase, `fichier:ligne`), puis **l'une des trois** : (a) couverte par le libellé de
   la ligne 15 → code 1 correct, aucun texte, aucun outillage ; (b) non couverte → **ligne à ajouter ou libellé
   de la ligne 15 à étendre** (texte v2.2), outillage inchangé ; (c) couverte mais le code ne produit pas la
   forme d'un diagnostic (traceback, pas d'`invalide: true`) → texte inchangé, **fix outillage** au chantier
   suivant. Aucune quatrième catégorie ; un cas qui n'entre dans aucune est un STOP.
2. **Inventaire des tests-miroirs** : tout test de `tests/test_scripts/test_c3_*.py` (et `test_c3b_*.py`) qui
   recopie ou relit un bloc du protocole (listes closes § B.8, § H.1, liste blanche § A.7, table § I.1, § L.1,
   regex sur `amendements_c3_v2.1.md`). Pour chaque AM de la table : quels tests-miroirs il touche, et pour
   chacun : **(i)** mis à jour dans le commit de l'AM, ou **(ii)** `xfail(strict=True, reason="R-xx")` parce
   qu'il attend l'outillage. Aucun test ne reste rouge.
3. **Où la liste blanche § A.7 est reflétée** dans le code (`c3_select` projection, `c3b_prefix` export,
   fixtures) : c'est la portée réelle de AM-4, et la base de sa réserve.
4. **Conformité C3b sous v2.2** : pour chaque AM, quels artefacts de `results/c3b_producteur/` (préfixe 2020,
   évaluation, chaîne archivée) deviennent non conformes à v2.2, et comment. Attendu de Bruno, à confirmer ou
   infirmer par la lecture : AM-4 les rend **tous incomparables** (signature de projection) ; AM-3+7 et AM-6
   ajoutent une entrée qu'ils ne portent pas ; AM-8 et AM-9 ne cassent rien. C'est ce qui écrit les réserves
   sans les découvrir au chantier outillage.
5. **Ordre d'application proposé** et liste des fichiers touchés en phase 2, exhaustive.

STOP. Bruno tranche : classification (C), forme de l'artefact de refus (AM-6), inventaire (i)/(ii), et
confirme la table. Aucune ligne de phase 2 avant ce GO.

## Phase 2 — rédaction, application, gel

1. `docs/amendements_c3_v2.2.md`, sur le modèle v2.1 : en-tête (base amendée = v2.1, sha, sources : ce brief,
   `PROJECT_CONTEXT.md` § 9, rapport SOL/D2 § 8.1, rapport C3b, écarts C3b 11/14/15), table candidat → AM,
   un AM par ligne de la table plus ceux issus de la classification (b), AM d'index § M, AM d'en-tête et sha
   (le bloc « Amendements — v2.2 » en tête du protocole, comme v2.1), section « Vérifié, sans amendement »,
   ordre d'application. Faits lus dans le code tagués **[v]** avec `fichier:ligne`, comme en v2.1.
2. Application au protocole, **un commit par AM**, texte + tests-miroirs (i) du même AM dans le même commit,
   `xfail(strict=True, reason="R-xx …")` pour les (ii). Puis index § M régénéré. Puis en-tête et sha.
3. **Section Adoption** (rédigée par l'agent, adoptée par Bruno au commit qui la porte) :
   - table des empreintes v2.0 / v2.1 / v2.2 et la ligne `**sha256 v2.2 :**` ;
   - décisions de gate (la table ci-dessus, telle que tranchée au STOP) ;
   - réserves d'application **R-xx datées**, une par item d'outillage induit, chacune avec : le § qui l'impose,
     le statut (bloquant manifeste / bloquant campagne / non bloquant), les tests `xfail` qui la portent, les
     artefacts C3b qu'elle rend non conformes ;
   - **la ligne Astra**, à écrire ainsi : « Re-passe Astra non faite (Astra non à jour depuis v2.0 ; réservée aux
     familles de stratégies). AM-3+7, AM-6 et AM-8 changent ce que la chaîne vérifie — ce sont les amendements
     où une lecture adverse aurait servi. À défaut, lecture adverse écrite par Claude avant adoption, consignée
     à la table de gate ; adoption par Bruno. » Les deux rôles restent distincts.
4. Tests du sha : `test_c3_common.py:544-571` généralisés — `ADOPTED_PACKAGE` → v2.2, regex sur la **dernière**
   ligne `**sha256 vX.Y :**`, le test « aucun sha en dur » compte les empreintes de la table (trois), pas
   « exactement deux ». Le test épingle la ligne au fichier, comme avant.
5. Propagation du sha, sans en faire un sujet : `CLAUDE.md`, `skills/backtest.md` § « Validation C3 »,
   `docs/RESEARCH_LOG.md` (entrée 18 : adoption, aucun run), `PROJECT_CONTEXT.md` § 1 et § 9 (candidats → AM-xx,
   liste close outillage), `ROADMAP.md`, `docs/CODE_MAP.md` en-tête. Un commit `docs`.
6. **Liste close du chantier outillage** : `results/c3_v2_2/outillage_v2_2.md` — un item par réserve, avec le §
   qui l'impose, le fichier, le statut, le test `xfail` à lever. C'est l'entrée du chantier suivant ; rien n'en
   est implémenté ici.

## Règles de forme

- § 0.7 : une règle, une section d'origine. Un AM qui redit une règle ailleurs que dans sa section d'origine est
  refusé ; il renvoie.
- La liste des raisons § H.1 et la table § I.1 sont des listes closes : aucune raison nouvelle. Un « motif » est un
  champ, pas une raison.
- Le texte ne nomme aucune ligne de code comme règle ; il nomme des sections. Les `[v]` sont des faits, pas des
  normes.
- Aucune retouche de fond hors des AM décidés : un défaut de texte trouvé en route est **consigné** au rapport
  (candidat v2.3), pas corrigé.
- Shell : l'agent tourne en zsh. Toute vérification qui produit un code (sha, pytest, ruff, mypy) passe par
  `results/c3_v2_2/tests/*.sh`, lancé par `bash`, committé avec sa sortie. Aucune variable non quotée.

## Validation — critère de fin

Tous vrais, prouvés par `results/c3_v2_2/tests/gate.sh` (sortie committée) :

- `shasum -a 256 docs/protocole_c3.md` = la ligne `**sha256 v2.2 :**` de la section Adoption = ce que
  `cc.protocol_descriptor()["sha256"]` rend ;
- suite complète **verte au sens CI** (`pytest`, 0 failed ; les `xfail strict` comptés et listés, chacun avec sa
  R-xx) ; ruff et mypy `src/` = 65 inchangés ; gold hashes intacts ; diff de contrôle § L.3 vide (aucune ligne de
  `scripts/backtest.py`, runners P6/P7, `scripts/audit/c3*.py` hors tests-miroirs) ;
- `git diff --stat 8689636 HEAD -- src scripts/audit/*.py` **vide** : aucun comportement changé ;
- `docs/amendements_c3_v2.2.md` complet : table candidat → AM, décisions de gate, réserves R-xx, ligne Astra,
  ordre d'application, section « Vérifié, sans amendement » ;
- `results/c3_v2_2/phase1.md` et `results/c3_v2_2/outillage_v2_2.md` committés ;
- le manifeste historique `results/c3a_entry_validation/` reste intact ; sous v2.2, `c3_anchor` le refuse comme
  il refusait sous v2.1 (test existant, inchangé) ;
- branche poussée, CI lue par l'agent (`gh`), verte.

## Gates

| Quand | Quoi |
|---|---|
| Fin de phase 1 | STOP : `phase1.md` relu par Bruno, classification et AM-6 tranchés, inventaire (i)/(ii) validé → GO |
| Avant le commit Adoption | STOP : lecture adverse Claude sur AM-3+7, AM-6, AM-8 consignée ; Bruno adopte |
| Fin de phase 2 | STOP avant push : `gate.sh` vert, rapport `results/c3_v2_2/report.md` (par AM : commit, tests touchés, réserve) |
| Tout défaut de texte hors table, tout besoin de toucher `scripts/audit/*.py` au-delà des tests, tout doute sur § 0.7 | STOP |

## Ce que ce chantier ne fait pas

- L'outillage induit (recoupements `c3_verdict`, septième entrée, artefact de refus, admission `first_fill_at`,
  registre § 10.1, renommage `_quote` dans l'export, nullables couverture, fix des sorties (c)) : chantier
  suivant, depuis `outillage_v2_2.md`.
- Le manifeste de la première campagne, `CAMPAIGN_UNLOCK`, dette 21, dette 24, univers et provenance.
- Toute lecture, listing ou sha des sorties archivées de C3b sur fenêtre d'instrument (règle de non-lecture).
- La re-passe Astra. Une relecture de v2.1 par Astra n'est pas ouverte ici.
- Tout run, sur toute fenêtre.
