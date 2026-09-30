# C3 — Outillage v2.3, lot 1 (lever X1-X8) — plan (GO reçu)

## 0. GO reçu (30/09)

Plan approuvé par Bruno le 2026-09-30, tel qu'écrit ci-dessous, à la sortie du mode plan : son approbation vaut GO avant
toute écriture git. D13 est la décision de Bruno à la question posée avant la sortie (canal de second ordre de la
non-divulgation). Branche `feat/c3-outillage-v2.3` créée depuis `b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9`.

## Contexte

Le protocole v2.3 est gelé et mergé (`dev` @ `b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9`, sha256 du protocole
`d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`, recalculé à l'ouverture : conforme). AM-01
(évaluation différée : clé `deferred_evaluation.date`, descripteur `D`, non-divulgation) est porté par huit tests
`xfail(strict=True)` X1-X8, posés au gel depuis le texte seul. Brief `agent/AGENT_C3_OUTILLAGE_V2_3.md` : deux lots, une
session et un GO par lot ; **cette session = lot 1** (code et tests, lever X1-X8). Le lot 2 (conformité serveur v2.3 et
porte § L.5) aura son propre plan, dans sa propre session. Branche `feat/c3-outillage-v2.3` depuis `b50f2d1`. Rien n'est
écrit avant le GO. Le merge est fait par Bruno.

Arbre à l'ouverture : propre ; deux fichiers non suivis — le brief (commité tel que reçu au C0) et `gel_v2_3.patch`
(racine, 190 296 o, pas à moi : jamais touché ni commité, son sha256 relevé au C0 et revérifié inchangé à chaque commit ;
`interdits.sh` l'exclut par son nom exact).

Ce que la lecture établit (et que le brief ne dit pas) :
- les corps des X sont figés (diff AST) : **leurs appels le sont donc aussi** — `cc.load_manifest(...).deferred_evaluation_date`,
  `cc.MissingEvidenceError`, `cv.deferred_descriptor(campagne_brute, bloc_candidat_brut)`. « Indicatif » ne laisse
  libre que ce qui est derrière ces appels.
- **X7 passerait dès qu'on accepte la variante différée à l'ancrage**, avant toute inscription : un verdict qui n'inscrit
  rien « n'inscrit jamais ». D'où l'ordre des commits (§ 2) : verdict d'abord, ancrage ensuite, pour que X7 ne se lève
  que quand sa règle entière existe.
- `F_CANNOT_SEPARATE` n'est atteint dans `decide()` qu'après `Q1 ∧ Q2 ∧ Q3` (`c3_verdict.py:1185-1196`) : le conjonctif
  Q est redondant dans les états atteignables, son mutant ne mourra par aucun test de chaîne. Et aucun X ne contient un
  `F_CANNOT_SEPARATE` à `Δ̂_σ ≤ 0` : le mutant « Δ̂ ignoré » survivrait. Il faut des tests neufs (D10).
- `THRESHOLDS` est épinglé à 23 entrées et tout seuil du registre doit être déclaré par le manifeste
  (`c3_anchor.py:97-102`) : la borne de 365 jours n'y entre pas (D3).
- `load_manifest` est appelé par les cinq modules de chaîne **et** le producteur (`c3b_common`, `c3b_prefix`,
  `c3b_evaluate`) : la clé devient obligatoire partout ; le garde-fou 6 lit `window` seul, la date n'est jamais une
  fenêtre lue (`c3b_common.py:58-61`, `:106`).
- Le nom périmé est à `test_c3_entry.py:706` (le brief dit `:709`, ligne de la docstring).

## 1. Décisions (recommandations, soumises au GO)

| # | Nature | Question | Recommandation et motif |
|---|---|---|---|
| D1 | emplacement (X5) | Où vit la dérivation de `D` ? | **`c3_common`**, une règle, deux entrées : `cc.deferred_descriptor_at_verdict(campagne, retenue)` et `cc.deferred_descriptor_at_run(entrant)`, sur un noyau privé commun (`of`, `window`, candidat, provenance seuls diffèrent, colonnes du tableau). `cv.deferred_descriptor` = enveloppe mince de la première (appel de X5). L'ancrage n'importe pas le verdict. |
| D2 | valeur | Sous quelle forme les valeurs entrent dans `D` ? | **Telles que le manifeste les déclare** (comme la clé de variante, `sig(canon(brut))` ; `canon` normalise déjà les chaînes Decimal), lues par les accesseurs stricts, **sauf les deux instants de `window`**, normalisés `parse_datetime(...).isoformat()` (UTC) : `canon` garde une chaîne ISO verbatim, donc `…Z` et `…+00:00` feraient deux engagements pour le même instant, et un manifeste différé dérivé qui reformate la date perdrait la sortie en silence — la perte que le motif d'AM-01 écarte. `data` = exactement `{exchange, exec_interval, timeframes}`, `window` = exactement `{start, end}`, `candidate` = exactement `{strategy, pair, params}`. Sans effet sur les X (fixtures déjà en `+00:00`). |
| D3 | forme / valeur | Où se valide la date ? | **Forme dans `load_manifest`** : `require_mapping(raw, "deferred_evaluation")` puis `require_datetime(..., "date")` → `Manifest.deferred_evaluation_date` ; absente, nulle, mal typée, sans fuseau → `MissingEvidenceError`, code 2 dans tout module (X1, X8). **Valeur à l'étape 1** (`c3_anchor`, après les valeurs gelées, avant le registre) : `date − window.end ≥ timedelta(days=cc.DEFERRED_MIN_DAYS)`, sinon `EntryRefusedError("R0_INVALID_RUN")`, code 2, rien écrit (X2). `cc.DEFERRED_MIN_DAYS = 365` : constante simple, **hors `THRESHOLDS`** (sinon tout manifeste devrait la déclarer sous `selection_rule.thresholds`, forme que le texte ne crée pas) ; sa valeur est épinglée par le comportement (X2 : 365 j passent, 364 j et 365 j − 1 s refusés). `FROZEN_ASSERTIONS` (liste close de quatre) inchangé ; `anchor.json` inchangé. Commentaire de `OPTIONAL_FIELDS` : `deferred_evaluation` y reste pour l'**enregistrement du registre** ; au manifeste, la clé est obligatoire. |
| D4 | prédicat | Comment le verdict sait que l'issue « ouvre la voie » ? | Fonction pure **`cv.opens_deferred_way(decision)`** = `(issue, raison) == (inconclusif, F_CANNOT_SEPARATE)` ∧ `Q1 ∧ Q2 ∧ Q3` (ensemble exact, chaque porte `True`) ∧ `Δ̂_m > 0` pour chaque appariement `m` — `Δ̂` ne dépend pas de `L`, les six combinaisons se réduisent aux deux appariements (rapport du gel § 8). `Decision` reçoit un champ `delta_hat: Mapping[str, float] \| None = None` (valeurs **rejouées**, posées par `decide()` là où le rejeu existe) ; **non publié** dans `verdict.json` (charge utile inchangée). Conjonctif Q gardé explicite : le texte le nomme ; son mutant est tué par N1 seul (déclaré). |
| D5 | inscription | Comment et quand le verdict inscrit ? | Mode `chain` seul (le seul qui porte `--registry`), code 0 seul (calcul après « aucune violation », écriture sur la branche de publication normale, comme le verdict v2.2). À côté de `verdict`, `deferred_evaluation = {date, variant_key}` : `date` = **la chaîne** `deferred_evaluation.date` du manifeste, copiée ; `variant_key = cc.sig(cv.deferred_descriptor(manifeste_brut, bloc_retenu))`, le bloc retenu étant le candidat brut dont l'identité § A.2 est `decision.retained`. **Une fois par famille** : pas d'inscription si un **autre** enregistrement de la même famille porte déjà un `deferred_evaluation` (lettre du texte ; sur les états atteignables, équivalent à « la famille porte un autre verdict compté », puisque l'ancrage n'y laisse entrer que la différée). **Écrit une fois** : relance au même manifeste, blocs identiques → rien ; un bloc existant différent → violation (diagnostic, code 1, registre intact), **sans jamais imprimer les valeurs** (le message v2.2 imprime les deux triplets de verdict ; le bloc différé, lui, n'est jamais interpolé). |
| D6 | ancrage (X6) | Comment l'ancrage compare ? | `stop_criterion(variants, *, family, key, incoming)` : sur une famille au verdict compté, `D` re-dérivé du manifeste entrant **par la même règle** (D1) ; défini seulement si le parent n'est pas racine et s'il y a **exactement un** candidat (« l'unique candidat ») ; accepté ssi `sig(canon(D))` ∈ empreintes inscrites ; sinon refus `R0_INVALID_RUN`, code 2, dont le message nomme la famille, la variante comptée et la clé entrante (clés de manifeste brut, imprimées aujourd'hui) mais **aucune empreinte de descripteur**, ni l'inscrite ni la dérivée. Branche « relance au-delà de l'unique » inchangée. `register()` transmet le manifeste brut. |
| D7 | non-divulgation | Contrôle mécanique ? | (a) **Comportemental** : X3 (chaîne : stdout, stderr, fichiers du répertoire de sortie), N2 (ancrage, acceptation et refus), N3 (discordance au verdict) — chacun vérifié par un mutant qui imprime l'empreinte (M15a-c). (b) **Statique** : `non_divulgation.sh` sur les lignes ajoutées de `c3_common`, `c3_anchor`, `c3_verdict` (`git diff b50f2d1 -U0`) — aucune interpolation (`{…}` d'f-string, `%`, `.format`) ni argument de `print`/`raise`/log qui nomme `deferred`, `descriptor`, `derived` ou l'empreinte inscrite ; **et aucune impression d'un digest du registre** dans `scripts/audit/c3_*.py` (D13) ; sortie committée, rc=0, mordant prouvé sur le mutant M15d. (c) Canal de second ordre : D13. |
| D13 | non-divulgation, second ordre (**décision de Bruno, 30/09, question du plan**) | Le verdict imprime le digest du registre après écriture (`c3_verdict.py:1882`). | **Le digest disparaît de cette ligne, sans condition** : `written <registre> (issue inscrite, § A.6)`, qu'un bloc différé soit inscrit ou non — une omission conditionnelle ferait de la forme du log un canal d'un bit (digest absent ⟺ voie ouverte ⟺ `F_CANNOT_SEPARATE ∧ Q`), donc une fuite de l'issue, non lue. Coût nul : ce digest ne sert aucun recoupement (aucun test ni vérificateur ne le lit, constaté) ; l'intégrité du registre est portée par `anchor.json.registry.sha256`. Les digests des autres artefacts (`:1862`, `:1879`) restent : ils ne couvrent pas l'empreinte. **`anchor.json.registry.sha256` reste tel quel** (contrat de chaîne ; y toucher est du texte) — **limite déclarée au README, candidate v2.4** (et, par transitivité, le digest imprimé d'`anchor.json` qui la contient), avec la note : la fermeture structurelle est un **sel aléatoire à la racine du registre**, écrit à la création du registre de campagne, qui rend tout digest non inversible sans lire le registre ; elle relève de la conversation manifeste, et exigera son propre item d'outillage, `load_registry` jetant aujourd'hui toute clé de racine inconnue à la réécriture (`c3_anchor.py:218`). Même classe, déclarée aussi : la **taille** du registre diffère quand un bloc différé est inscrit — couverte par la règle de non-lecture (aucun listing de tailles ; à tenir par les vérificateurs du lot 2). Contrôles : `non_divulgation.sh` (grep) et N3 (le sha du registre absent de stdout/stderr). |
| D8 | fixtures | Quels manifestes reçoivent la date ? | `fx.manifest()` : `deferred_evaluation.date = WINDOW_END + 365 j` (`2027-04-01T00:00:00+00:00`) par défaut — compatible avec les X (`with_deferred_date` est idempotent sur ce défaut ; X1/X8 retirent la clé eux-mêmes). Aucun autre constructeur ; une seule aide re-déclare la date, `_campaign_v21_manifest` (§ 1 bis). Déclarés au diff AST. |
| D9 | renommage | Nom neuf du test périmé ? | `test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_le_protocole_courant` — nom seul, décorateur et corps intacts (diff AST : même corps, identifiant renommé, déclaré). Les répertoires clos qui citent l'ancien nom (`results/c3_v2_2/tests/gate.sh`, `results/c3_outillage_v2_2/tests/mutants_lot*.sh`) restent tels quels ; le lot 2 citera le nom neuf. |
| D10 | tests neufs hors brief | Les X ne tuent pas tous les mutants exigés. | **Quatre tests neufs**, nés adverses (rouges à `b50f2d1`), attendus dérivés du texte : **N1** `test_A6_v23_le_predicat_d_ouverture_suit_le_10_1_conjonctif_par_conjonctif` (verdict, pur : table recopiée de CONTRAINTES § 10.1 — témoin vrai ; Q1, Q2, Q3 faux un à un ; `Δ̂_σ = 0` ; `Δ̂_dd < 0` ; `validé`, `réfuté`, `F_NOT_ESTIMABLE` → faux) ; **N2** `test_A6_v23_sur_une_famille_close_le_descripteur_entrant_suit_la_regle_du_run_differe` (ancrage : témoin intégré accepté ; même configuration mais provenance `unknown`, puis deux candidats dont la retenue en tête → refusés ; aucune des deux empreintes — inscrite, dérivée — dans stdout, stderr ni sorties) ; **N3** `test_A6_v23_une_evaluation_differee_inscrite_differente_est_une_violation_sans_empreinte_imprimee` (monde de X3 : première chaîne → inscription, et ni l'empreinte ni le sha256 du registre écrit dans stdout/stderr (D13) ; bloc différé altéré dans le registre, chaîne relancée → code 1, registre intact au sha près, empreintes absentes des sorties) ; **N4** `test_A6_v23_tout_champ_hors_de_la_table_est_hors_engagement` (verdict, pur : `research_log_entry`, `run_scope`, `variant_id`, `protocol_sha256`, provenance `unknown`, clés en trop dans `data`, `fees`, `window`, le bloc candidat → `D` inchangé hors `deferred_evaluation_of`, qui suit `sig(campagne)` ; ferme la limite « constante `clean` non discriminée » du rapport du gel § 8). **Porte du brief : 3 321 passés au lieu de 3 317** (3 309 + 8 levés + 4 neufs), écart déclaré. |
| D11 | ordre | Découpage des commits ? | § 2 : date (X1, X2, X8) → verdict (X3, X4, X5 ; N1, N3, N4) → ancrage (X6, X7 ; N2). Chaque marqueur est levé au commit qui le fait passer, et à aucun autre ; tout XPASS imprévu → STOP. |
| D12 | limite | « une fois » pour le run différé lui-même | Après la différée, la famille porte deux verdicts comptés et l'empreinte inscrite reste acceptée : un second manifeste de même `D` (autre entrée journal, autre `variant_id`) passerait. Le texte renvoie la mécanique du run différé à un amendement ultérieur (AM-01, « Limites dites ») : **non implémenté, déclaré**, candidat v2.4. |

## 1 bis. Inventaire des manifestes à doter de la date (D8)

Recensement (`grep` des constructeurs de manifeste, des surcharges de `window`, des empreintes épinglées) :
- **Un seul constructeur** : `fx.manifest()` (`test_c3_common.py:882`). `producer_manifest` (`test_c3b_common.py:88`)
  passe par lui (fenêtre ≤ 2020-01-20 : la date par défaut de 2027-04-01 reste ≥ 365 j) ; aucun manifeste écrit à la
  main ailleurs, aucun manifeste sur disque lu par un test hors le livrable v2.0 (`manifest_rejeu_grid_20260919.json`,
  refusé par le sha du protocole **avant** `load_manifest` — inchangé).
- **Une seule surcharge de fenêtre qui rend la date trop proche** : `_campaign_v21_manifest` (`test_c3_anchor.py:114`,
  fin 2026-06-29 → 276 j), qui sert trois tests verts (`:123`, `:134`, `:156`) : l'aide re-déclare la date par
  `fx.with_deferred_date` (corps d'aide modifié, déclaré). Les autres surcharges (`:83`, fin 2024-05-28 ; `:398-400`,
  fenêtre inversée ou nulle, refusée avant) sont sans effet. Les aides producteur `_campaign_payload`
  (`test_c3b_prefix.py:252`, `test_c3b_evaluate.py:522`, fenêtre 2021-03-01 → 2026-06-29) n'atteignent que
  `load_manifest` et attendent un refus du garde-fou 6 : la date est présente (forme conforme), la borne de 365 j n'est
  contrôlée qu'à l'étape 1 — **sans effet** (c'est une raison de plus de ne pas mettre la borne dans `load_manifest`).
  Les autres fenêtres du producteur (2020-01-06 → 2020-01-20, → 2020-06-08, → 2020-12-28, 2020-06-01 → 2021-03-01)
  restent ≥ 365 j de 2027-04-01.
- `MANDATORY` (`test_c3_anchor.py:257`) est une liste explicite : **inchangée** (la présence de la clé est portée par
  X1 et X8 ; l'y ajouter créerait deux identifiants de plus).
- Aucune empreinte de manifeste épinglée (aucun 64 hex dans les tests C3), aucun `Decision` construit ni comparé dans
  les tests : le champ `delta_hat` est sans effet sur eux.
- Vérification empirique à C2 : tout test vert à `b50f2d1` qui rougit hors de cette liste → STOP (§ 6).

## 2. Commits (branche `feat/c3-outillage-v2.3` depuis `b50f2d1`, assert de branche avant chacun, messages par `-F`)

- **C0 `docs(agent)`** — le brief tel que reçu (sha256 relevé) + `results/c3_outillage_v2_3/plans/lot1.md` (ce plan, GO
  inclus). Mesures de base : `suite.sh base`, `lint_base.sh` (mypy strict des trois modules à `b50f2d1`).
- **C1 `test(c3)`** — renommage D9, rien d'autre. Suite : 3 309 / 9 xfail inchangés, un identifiant renommé.
- **C2 `feat(c3)`** — la clé : `load_manifest` (D3, forme), `Manifest.deferred_evaluation_date`,
  `cc.DEFERRED_MIN_DAYS`, contrôle de l'étape 1 dans `c3_anchor` (D3, valeur) ; fixtures D8. Lève **X1, X2, X8**
  (3 312 / 6 xfail).
- **C3 `feat(c3)`** — le verdict : noyau de `D` et `deferred_descriptor_at_verdict` dans `c3_common` (D1, D2),
  `cv.deferred_descriptor`, `Decision.delta_hat`, `cv.opens_deferred_way` (D4), inscription et garde « une fois par
  famille » dans `registry_inscription` / `run_verdict` (D5), ligne du registre sans digest (D13). Lève **X3, X4,
  X5** ; tests neufs **N1, N3, N4**
  (3 318 / 3 xfail). X6 et X7 restent xfail : l'ancrage refuse encore la différée.
- **C4 `feat(c3)`** — l'ancrage : `deferred_descriptor_at_run`, `stop_criterion` par descripteur (D6). Lève **X6
  (témoin R-17), X7** ; test neuf **N2** (**3 321 / 1 xfail**, le caduc `test_c3b_evaluate.py:2151`).
  → `git push -u origin feat/c3-outillage-v2.3`, CI lue par `gh` (tentative 1).
- **C5 `docs(results)`** — `results/c3_outillage_v2_3/lot1/README.md`, `tests/*.sh` + `.out`, `mutants.log`. Push ;
  la CI de C5 est donnée au message de fin de lot (un commit ne porte pas la CI de son propre SHA).

Fichiers de code touchés : `scripts/audit/c3_common.py`, `scripts/audit/c3_anchor.py`, `scripts/audit/c3_verdict.py`,
et rien d'autre sous `scripts/` (interdits : `src/`, moteur, runners, `rejeu_common.py`, `c3b_*.py` — diff vide).
Tests : `tests/test_scripts/test_c3_{common,anchor,verdict,entry}.py` seuls (aucun fichier producteur : § 1 bis).
Liste blanche du lot = ces sept fichiers + `agent/AGENT_C3_OUTILLAGE_V2_3.md` + `results/c3_outillage_v2_3/`.

Réutilisé tel quel : accesseurs stricts (`require_mapping`, `require_datetime`, `require_str`, `optional_sequence`,
`_require`), `cc.sig` / `canon`, `cc.candidate_identity`, `cc.parse_datetime`, `EntryRefusedError`, la structure
`registry_inscription` / `run_verdict` de v2.2 ; côté tests, `fx.with_deferred_date`, `fx.deferred_manifest`,
`fx.deferred_descriptor(_at_run)`, `_opening_world`, `_chain_world`, `_chain_argv`, `_closed_family_with_deferred`.
Scans de source respectés : pas de `bool(`, `.get(` et `optional_*` seulement sur des clés de `OPTIONAL_FIELDS`
(`decision_timeframes`, `deferred_evaluation`), listes closes inchangées (commentaire seul).

## 3. Mutants (`mutants_lot1.sh` → `results/c3_outillage_v2_3/mutants.log`, après C4, un à la fois, substitution
littérale unique, restauration `git checkout` + `git diff --quiet`, tueurs relancés verts)

| # | Mutant (règle) | Tué par |
|---|---|---|
| M1 | `load_manifest` lit le bloc en optionnel (absent → `None`) | X1, X8 |
| M2 | borne `>=` → `>` | X2 (témoin 365 j) |
| M3 | 365 → 364 | X2 (`364_jours`) |
| M4 | contrôle de la date retiré de l'étape 1 | X2 |
| M5 | prédicat : conjonctif issue/raison retiré | X4 (`valide`), N1 |
| M6a-c | prédicat : Q1, puis Q2, puis Q3 ignoré | N1 |
| M7 | prédicat : `Δ̂` ignoré | N1 |
| M8 | prédicat : `Δ̂ > 0` → `Δ̂ >= 0` | N1 (`Δ̂_σ = 0`) |
| M9.1-10 | `D` : chacun des dix champs omis, un par un | X5 (et X3 / X6 selon le champ) |
| M10a-g | `D` : `engines` non restreint ; `pair_costs` non restreint ; `decision_timeframes` non trié ; surcharge par candidat ignorée ; provenance de la campagne au lieu de `clean` ; `data` entier ; `research_log_entry` ajouté | X5 ; X5, X6 ; X5, X6 ; X5 ; N4 ; N4 ; N4 |
| M11a-d | run différé : `of = sig(entrant)` ; `window` depuis la date de l'entrant ; provenance constante `clean` ; premier candidat au lieu de l'unique | X6 ; X6 ; N2 ; N2 |
| M12a-b | ancrage : empreinte brute (état v2.2) ; tout accepté sur famille close | X6 ; adverse R-17 |
| M13 | garde « une fois par famille » retirée | X7 |
| M14 | bloc différé ignoré à la réinscription | N3 |
| M15a-c | empreinte imprimée : refus de l'ancrage (préfixe 16) ; violation de discordance ; ligne d'inscription du verdict | N2 ; N3 ; X3 |
| M15d | digest du registre rétabli sur la ligne du verdict (D13) | N3 ; `non_divulgation.sh` |

Chacun : rouge sous mutant, arbre restauré au sha près, vert ensuite ; tueur nommé au README.

## 4. Vérifications (`results/c3_outillage_v2_3/tests/*.sh`, lancés par `bash`, `set -o pipefail`, `.out` committés)

Adaptés des chantiers v2.2 et gel (base `b50f2d1`, répertoire, listes) :
- `interdits.sh <étiquette>` à chaque commit : diff vide contre `b50f2d1` (HEAD, index, arbre, non suivis) sur `src/`,
  `scripts/backtest.py`, runners P6/P7, `rejeu_common.py`, `scripts/audit/c3b_*.py`, `docs/protocole_c3.md`,
  `docs/amendements_c3_v2.{1,2,3}.md`, `results/c3_v2_2/`, `results/c3b_producteur/`, `results/c3_outillage_v2_2/`,
  `results/c3_v2_3_gel/` ; **sha256 recalculé du protocole = dernière ligne `**sha256 v2.3 :**` du paquet** (lu, pas
  écrit en dur) ; liste blanche du lot ; `gel_v2_3.patch` exclu par son nom, sha inchangé ; toute empreinte 64 hex
  ajoutée ∈ table d'Adoption ; aucun artefact du chemin ; `CAMPAIGN_UNLOCK` absent ; aucun script qui nomme docker.
  `interdits_adverse.sh` : la preuve qu'il mord (cas fabriqués, restaurés).
- `suite.sh <étiquette>` sans tunnel (greffon `gate_sans_tunnel`, lu dans `results/c3_v2_2/tests/`) : base, C1…C4.
- `tunnel.sh open|close|state` + `base_db.sh` : tunnel ouvert au tip de C4, **les 13 tests base** passent (lecture
  seule), tunnel fermé et **vérifié fermé** (`nc -z` échoue).
- `comptes.sh` + `declares_lot1.txt` (`[leves]`, `[neufs]`, `[renomme]`) : collectes à `b50f2d1` (worktree détaché) et
  au tip ; retiré = l'ancien nom seul, ajoutés = le nom neuf + N1-N4 ; équation 3 309 + 8 + 4 = 3 321 ; ignorés 19 et
  désélectionnés 24 inchangés.
- `diff_tests.sh` (AST contre `b50f2d1`) : corps des huit X identiques, décorateurs = retrait du seul `xfail` ; corps du
  test renommé identique ; toute autre fonction modifiée ou neuve ∈ liste déclarée.
- `xfail_fin.sh` : seul le caduc reste `xfail`.
- `non_divulgation.sh` (D7 b).
- `lint.sh` : ruff check + `format --check` (liste CI, fichiers touchés), `ruff check .`, `mypy src/` = 65, mypy strict
  des trois modules ≤ base. Formatter sur les fichiers nommés, jamais un répertoire ; hunks vérifiés par `git diff -U0`.
- `ci_status.sh <sha>` : tentative 1 ; relance réservée à `test_rejeu_effect`.

## 5. Question du plan — tranchée

Canal de second ordre de la non-divulgation (digest du registre) : tranché par Bruno le 30/09 → D13. Au README :
décision déclarée, limite `anchor.json.registry.sha256` (candidate v2.4, note du sel), limite de taille du registre.

## 5 bis. Sortie du lot 1 (critères, écarts déclarés d'avance)

- Suite sans tunnel : **3 321 passés** (3 309 + 8 levés + 4 neufs — écart au « 3 317 » du brief, D10), 19 ignorés,
  24 désélectionnés, **1 xfail** (le caduc), 0 échec, 0 XPASS ; aucun test retiré (un renommé, D9).
- Les 13 tests base verts, tunnel ouvert puis fermé et vérifié fermé.
- Mutants § 3 tous rouges, restaurés, verts ; `mypy src/` = 65 ; ruff vert ; interdits verts à chaque commit.
- CI verte en tentative 1 au SHA poussé ; `lot1/README.md` (modèle `lot1_chaine/README.md` v2.2) : commits (SHA
  complets), marqueurs levés, tests neufs, mutants et tueurs, écarts au brief (D10 comptes, D9 ligne `:706`, D13),
  limites déclarées (D12, D13), défauts dits comme tels. Pas de mise à jour de `skills/`, `CLAUDE.md`,
  `PROJECT_CONTEXT.md`, `CODE_MAP` dans ce lot (candidats du `docs(merge)`).

## 6. Règle d'arrêt

Tout test vert à `b50f2d1` qui rougit sans être nommé ici, tout XPASS imprévu, tout attendu X qu'il faudrait toucher,
tout besoin hors des trois modules → STOP, rien d'arbitré.
