# C3 — Racine du registre (R-4) — plan (GO reçu)

## 0. GO reçu (01/10)

Plan approuvé par Bruno le 2026-10-01, tel qu'écrit ci-dessous, à la sortie du mode plan : son approbation vaut GO du
**lot 1** avant toute écriture git. Le runbook manquant au brief a été déposé par Bruno dans `~/Downloads/` à la
question du plan, puis lu avant la soumission. Branche `feat/c3-racine-registre` créée depuis
`313eb00c2019b98cf20fb81ac8327f7b9d1e920a`. Le lot 2 a son propre GO, avant sa première écriture.

## Contexte

Le registre de campagne unique sera créé par Bruno, à la main, après le merge de ce chantier (runbook § 1), avec un
sel à la racine (`{"salt": secrets.token_hex(32), "variants": {}}`) qui rend tout digest du registre non inversible
sans le lire — fermeture structurelle du canal D13 (`anchor.json.registry.sha256`, limite v2.4 du rapport v2.3 § 5).
Or `load_registry` (`scripts/audit/c3_anchor.py:230-245`) rend `{"variants": …}` seul et `register` (`:275`, `:292`)
reconstruit `{"variants": …}` : **la première réécriture par l'ancrage jetterait le sel, silencieusement.** Ce
chantier corrige l'ancrage, prouve par test que le verdict préserve déjà la racine, ajoute le test manquant de la
normalisation UTC de `D` (limite du rapport v2.3 § 5), commite le runbook, puis rejoue la conformité serveur au SHA du
chantier (lot 2). Branche `feat/c3-racine-registre` depuis `dev` @ `313eb00c2019b98cf20fb81ac8327f7b9d1e920a`.
Merge par Bruno, jamais par l'agent.

Ouverture : arbre propre, un seul non-suivi (le brief) ; protocole recalculé `d030ab23…79e6` (v2.3, conforme) ; runbook
reçu dans `~/Downloads/RUNBOOK_REGISTRE_CAMPAGNE.md` (108 lignes, 6 133 o, sha256 `34686dc7…1c18`), lu.

## 1. Constats de lecture

| # | Constat | Effet |
|---|---|---|
| K1 | § A.6 v2.3 (`protocole_c3.md:384-473`) spécifie clé, enregistrements, inscription, non-divulgation — **pas le schéma de racine** du fichier | aucune ligne de texte à amender (constat attendu du brief, tenu) |
| K2 | `registry_inscription` écrit déjà `{**dict(raw), "variants": …}` (`c3_verdict.py:1462`) | prouvé par test (T2-verdict), aucune modification de `c3_verdict.py` attendue |
| K3 | Avec le passthrough, un flottant non fini à la racine atteindrait `write_json_strict` → trace nue, code 1 sans diagnostic (la classe que R-22 cas 1 a fermée dans les enregistrements) ; le runbook § 3 compte sur « la canonicalisation à la lecture produit un code 1 » | D2 |
| K4 | `canon` lit toute chaîne qui a la forme d'un décimal : un sel hex `chiffres e chiffres` (p ≈ 5·10⁻¹³) lève `decimal.Overflow` (constaté : `canon("1234e5678901234567890")`) | D2 : la racine n'est **jamais** passée à `canon` |
| K5 | Normalisation UTC de `D` (D2 du lot 1 v2.3) : `parse_datetime(...).astimezone(UTC)` puis `.isoformat()` (`c3_common.py:399-409`, `:1700`) ; toutes les fixtures écrivent `+00:00` ; `fx._descriptor` (côté test) copie `window` verbatim | T3 ; son attendu ne vient pas de `fx.deferred_descriptor` |
| K6 | `c3_anchor` n'est importé que par `c3_verdict` (paresseux, `:2032`, `chain`) et les tests C3 ; le chemin des 24 `_full` ne l'atteint pas ; `c62acb4..313eb00` ne change que `results/c3_outillage_v2_3/` et `docs/RESEARCH_LOG.md` | porte § L.5 par invariance (L5) |
| K7 | Le runbook nomme `~/c3/` et `~/docker/` (l. 25-46) : document de Bruno, gestes de Bruno ; il contient 0 empreinte de 64 hex ; aucun renvoi relatif à adapter. Son fichier § 1 a la mise en page du writer (`indent=2`, clés déjà triées, ASCII) | commité tel quel (D7) ; la règle dette 23 porte sur les scripts du chantier, inchangée |
| K8 | Runbook « Renvois » : `anchor.json` n'est pas identique au bit entre exécutions sur registre persistant (ouvert de la conversation manifeste) | hors chantier ; listé au rapport (« ce qui attend ») |

## 2. Inventaire-filet (§ 3.1) — fait à la lecture, versionné au C0 (`tests/inventaire_filet.sh` + `.out`)

**Aucun épinglage normatif de la racine.** Occurrences, toutes non normatives :
- `test_c3_anchor.py:543` `{"variants": [1, 2]}`, `test_c3_verdict.py:2903` `{"variants": [1]}` : type de `variants`
  (refus 2) — inchangés ;
- `test_c3_anchor.py:472, :538, :750-761`, `test_c3_verdict.py:2753-2766, :2833-2837, :3009-3046` : octets ou sha du
  registre **inchangés** (idempotence, pas de réécriture sur violation ou refus) — comportement conservé ;
- `test_c3_anchor.py:480, :497, :509, :520` : `registry["variants"]` seul lu ;
- `REAL_REGISTRY` (`results/c3a_entry_validation/variants.json`) : refusé au sha du protocole avant `load_registry` ;
- `pilot_dryrun.sh:117` : registre **simulé**, son propre écrivain ; `verify_attendu.py:35, :53` : registres comparés
  **entre exécutions** (neufs, aucune clé en plus) ; `mutants_lot1.sh:163` : chantier clos.

## 2 bis. Décisions (recommandations, soumises au GO)

| # | Question | Recommandation et motif |
|---|---|---|
| D1 | Où le passthrough ? | **Lecture et écriture, ancrage seul.** `load_registry` rend `{**racine_lue, "variants": dict(variants)}` ; `register`, branche d'écriture : `{**dict(registry), "variants": updated}` ; branche idempotente : le registre tel que lu (jamais écrit : `main` n'écrit que sur `new_entry` ; l'idempotence reste « octets inchangés »). Valeurs de racine passées **telles que `json.loads` les rend**. `"variants"` reste obligatoire et validé comme aujourd'hui. **Aucune clé de racine n'est lue, réservée ni validée** (le sel reste opaque ; en exiger la présence ou la forme serait une règle que le texte n'écrit pas — la vérification de forme est celle du runbook § 1, par Bruno). Limite déclarée : la mise en page est celle du writer (indent 2, clés triées) ; elle coïncide avec celle du fichier du runbook (K7). |
| D2 | Non-fini à la racine | Les valeurs de racine hors `variants` passent par le **critère du writer strict** — `cc.dumps_canonical` (`allow_nan=False`), jamais `canon` (K4) — à la lecture ; un flottant non fini → `cc.NonFiniteValueError`, message constant sans valeur → violation, code 1, diagnostic, registre non réécrit (§ I.1 l.15 ; même classe que R-22 cas 1 ; le « code 1 » du runbook § 3). `canon(variants)` inchangé. Côté verdict : inatteignable en `chain` (l'étape 1 refuse avant) ; le verdict seul n'écrit pas de registre — déclaré, aucun code. |
| D3 | Verdict | **Aucune modification** (K2). `c3_verdict.py` et `c3_common.py` entrent dans les chemins gelés d'`interdits.sh` : un besoin d'y toucher → STOP, plan amendé. |
| D4 | Valeurs synthétiques | Une constante dans `test_c3_common.py` (`fx`) : `REGISTRY_ROOT_SYNTHETIC = {"salt": "racine-de-test", "racine_de_test_typee": {"entier": 7, "flottant": 0.5, "nul": None, "decimal_en_texte": "0E-30", "liste": [1, "a"], "unicode": "é"}}` — `salt` porte le nom du runbook, la valeur n'a pas la forme d'un sel ; la clé typée fait mordre une réécriture (`canon` : 7 → "7", "0E-30" → "0"). « À l'octet près » : ensemble des clés de racine = avant, et `cc.dumps_canonical(avant[k]) == cc.dumps_canonical(après[k])` (JSON compact trié, **sans** `canon`) pour chaque clé en plus. |
| D5 | Tests neufs | Cinq (§ 3). Nés rouges à `313eb00` : T1, T2-chaîne, T4. **Verts à `313eb00` par construction** : T2-verdict (K2) et T3 (D2 v2.3 implémenté) — consignés `vert_avant`, mordant prouvé par mutants (règle agent 1, variante déclarée). |
| D6 | Graphies de T3 | `+00:00`, `…Z`, et **`+02:00` au même instant** (extension déclarée : seule graphie qui exerce `astimezone(UTC)`, mutant M3b). Appui : § A.6 v2.3, tableau (`window`) ; D2 du plan du lot 1 v2.3 (« un instant, pas une graphie, est engagé ») ; CLAUDE.md, règle d'or 2. |
| D7 | Runbook | `skills/registry.md`, **contenu identique à l'octet** (sha256 reçu = commité, consigné en `.out`) ; aucune adaptation (K7). Ligne de routage `CLAUDE.md` non ajoutée : listée pour le `docs(merge)`. |
| D8 | Non-divulgation | Comportemental : T1 et T2-chaîne assertent les valeurs synthétiques de racine absentes de stdout, stderr et des sorties publiées. Statique : `non_divulgation.sh` repris (règles 1-3 du lot 1 v2.3, trois modules) + **règle 4** : les lignes ajoutées depuis `313eb00` aux modules de chaîne ne contiennent ni `print`, ni journalisation, ni interpolation (f-string, `%`, `.format`). Mordant prouvé sur M5. |
| D9 | Comptes | **3 321 + 5 = 3 326** passés, 19 ignorés, 24 désélectionnés, 1 xfail (le caduc), 0 échec, 0 XPASS, 0 retiré, 0 renommé. |
| D10 | Règle 64 hex | Celle du lot 2 v2.3 (D3) dès le lot 1 : une empreinte de 64 hex ajoutée est de la table d'Adoption, ou le sha256 d'un fichier **versionné** du chantier (`results/c3_racine_registre/**`, `skills/registry.md`, le brief), ou — au lot 2 — le manifeste v2.3 comparé, une archive consignée. |

## 3. Tests neufs (attendus dérivés du texte, du brief ou du runbook, appui cité en docstring)

- **T1** `test_c3_anchor.py::test_A6_la_racine_du_registre_survit_a_l_ancrage_enregistrement_idempotence_enfant` —
  registre `REGISTRY_ROOT_SYNTHETIC` + `variants: {}` → racine enregistrée (0), racine intacte à l'octet ; même manifeste
  relancé → octets du registre inchangés (§ A.6, idempotence) ; enfant enregistré → racine intacte ; valeurs
  synthétiques absentes de stdout, stderr, `anchor*.json`. **Rouge à `313eb00`.**
- **T2-chaîne** `test_c3_verdict.py::test_A6_la_racine_du_registre_traverse_l_ancrage_et_l_inscription_du_verdict` —
  `_opening_world` (verdict **et** évaluation différée inscrits), registre pré-écrit avec la racine synthétique →
  `chain` 0 ; racine intacte à l'octet ; enregistrement porteur de `verdict` et `deferred_evaluation` ; valeurs
  synthétiques absentes des sorties. **Rouge à `313eb00`** (chemin ancrage) — l'adverse du brief.
- **T2-verdict** `test_c3_verdict.py::test_A6_registry_inscription_preserve_les_cles_de_racine` — registre fait à la
  main (racine synthétique + un enregistrement), `cv.registry_inscription` avec et sans bloc différé, écrit par
  `cc.write_json`, relu → racine intacte à l'octet. Vert à `313eb00` (K2).
- **T3** `test_c3_verdict.py::test_A6_v23_les_instants_de_D_sont_normalises_un_instant_pas_une_graphie` — pour chaque
  graphie A de la campagne et B du manifeste différé (D6) : `cv.deferred_descriptor(campagne_A, retenue)` a
  `window = {"start": "2026-04-01T00:00:00+00:00", "end": "2027-04-01T00:00:00+00:00"}` et ne diffère de celui de
  `+00:00` que par `deferred_evaluation_of` (= `sig(campagne_A)` : la clé de variante engage le manifeste brut, § A.6) ;
  `cc.deferred_descriptor_at_run(différé_B)` (la fonction de l'ancrage) a la même empreinte pour tout B ; et
  `sig(D_verdict(A)) == sig(D_run(différé_B dérivé de A))` pour tout couple. Vert à `313eb00`.
- **T4** `test_c3_anchor.py::test_R22_un_non_fini_a_la_racine_du_registre_est_un_diagnostic` — racine `{"salt": NaN,
  "variants": {}}` → code 1, `invalide: true`, registre non réécrit (octets) ; une chaîne `"NaN"` à la racine, elle,
  traverse (opaque, D2). Rouge à `313eb00` (la racine est jetée, code 0).

## 4. Mutants (`mutants.sh`, repris de `mutants_lot1.sh` v2.3 ; un à la fois, restauré au sha près, tueurs relancés verts)

| # | Mutant | Tué par |
|---|---|---|
| M1a | `load_registry` rend `{"variants"}` seul (état `313eb00`) | T1, T2-chaîne |
| M1b | `register` (écriture) rend `{"variants": updated}` | T1, T2-chaîne |
| M2a | `registry_inscription` : racine perdue | T2-verdict, T2-chaîne |
| M2b | `registry_inscription` : racine réécrite par `canon` | T2-verdict, T2-chaîne |
| M2c | `run_verdict` : registre canonicalisé au site d'écriture | T2-chaîne |
| M3a | `D` : la graphie du manifeste entre dans `window` au lieu de l'instant normalisé (`isoformat` contourné) | T3 |
| M3b | `parse_datetime` sans `astimezone(UTC)` | T3 (`+02:00`) |
| M4 | contrôle de la racine retiré (D2) | T4 |
| M5 | `load_registry` imprime la racine sur stderr | T1 ; `non_divulgation.sh` |

M2a-c et M3a-b portent sur des modules gelés pour ce chantier : temporaires seulement, `git diff --quiet` après
restauration. Un mutant à plusieurs sites (M3a probable) est déclaré tel au README.

## 5. Commits du lot 1 (branche assertée, messages par `-F`, `interdits.sh <étiquette>` avant chacun)

- **C0 `docs(agent)`** — brief tel que reçu (sha256 relevé) ; `results/c3_racine_registre/plans/plan.md` (ce plan, GO
  inclus) ; `inventaire_filet.sh` + `.out` ; mesures de base (`suite_base.out`, `lint_base.out`) ; `reprise_lot1.out`
  (scripts repris de v2.3, lignes changées = base, répertoire, listes).
- **C1 `docs(skills)`** — `skills/registry.md`, le runbook tel que reçu (D7).
- **C2 `fix(c3)`** — passthrough (D1) et contrôle de racine (D2) dans `c3_anchor.py` ; `REGISTRY_ROOT_SYNTHETIC` (D4) ;
  T1, T2-chaîne, T2-verdict, T4.
- **C3 `test(c3)`** — T3. Suite 3 326 / 1 xfail. → `git push -u origin feat/c3-racine-registre`, CI (tentative 1).
- **C4 `docs(results)`** — `lot1/README.md`, `tests/*.sh` + `.out`, `mutants.log`. Push ; CI de C4 au message.

Liste blanche du lot 1 : `scripts/audit/c3_anchor.py`, `tests/test_scripts/test_c3_{common,anchor,verdict}.py`,
`skills/registry.md`, `agent/AGENT_C3_RACINE_REGISTRE.md`, `results/c3_racine_registre/**`.

## 6. Vérifications (`results/c3_racine_registre/tests/*.sh`, repris de `results/c3_outillage_v2_3/tests/` ; `bash`, `set -o pipefail`, `.out` committés)

- `interdits.sh` : diff vide contre `313eb00` (HEAD, index, arbre, non suivis) sur `src/`, `config/`, `pyproject.toml`,
  `poetry.lock`, `.github/`, `scripts/backtest.py`, runners, `rejeu_common.py`, `c3b_*.py`, **`c3_{common, verdict,
  entry, benchmark, select, continuity}.py`**, `docs/protocole_c3.md`, `docs/amendements_c3_v2.{1,2,3}.md`,
  `docs/CONTRAINTES_POST_B4.md`, `CLAUDE.md`, `results/{c3_v2_2, c3b_producteur, c3_outillage_v2_2, c3_v2_3_gel,
  c3_outillage_v2_3}` ; sha du protocole recalculé = dernière ligne `**sha256 v2.3 :**` du paquet ; liste blanche ;
  aucun artefact du chemin ; règle 64 hex (D10) ; `CAMPAIGN_UNLOCK` absent ; dette 23 ; **runbook § 4** : aucun script
  du chantier ne nomme le chemin du registre de campagne (motif construit, comme dette 23), `~/c3` absent localement.
  `interdits_adverse.sh` : sa preuve.
- `suite.sh` sans tunnel (greffon `gate_sans_tunnel`) : base, C2, C3. `tunnel.sh` + `base_db.sh` : 13 tests base au tip
  de C3, tunnel refermé et vérifié fermé.
- `comptes.sh` + `declares.txt` (`[neufs]`) : identifiants à `313eb00` (worktree détaché) et au tip ; 0 retiré ;
  3 321 + 5 = 3 326. `diff_tests.sh` (AST contre `313eb00`) : corps existants identiques ; nouveautés = 5 fonctions et
  1 constante déclarées. `xfail_fin.sh`.
- `rouge_avant.sh` (T1, T2-chaîne, T4 rouges à `313eb00`, ligne d'échec consignée) ; `vert_avant` (T2-verdict, T3).
- `non_divulgation.sh` (D8) ; `lint.sh` (ruff sur les fichiers touchés, `ruff check .`, `mypy src/` = 65, mypy strict
  de `c3_anchor.py` ≤ base ; formatter sur les fichiers nommés seulement) ; `ci_status.sh <sha>` (relance pour
  `test_rejeu_effect` seul).

Sortie du lot 1 : 3 326 passés, 1 xfail, 0 échec, 0 XPASS ; 13 tests base verts ; M1a-M5 rouges puis verts ; interdits
verts à chaque commit ; CI verte tentative 1 ; `lot1/README.md` (commits, SHA complets, tests, mutants et tueurs,
écarts, limites — D1 mise en page, D2 côté verdict, K4 —, défauts dits comme tels). **STOP : GO du lot 2.**

## 7. Lot 2 — conformité rejouée, porte par invariance (aperçu ; GO propre avant sa première écriture, aucun code)

- **L1** SHA du run = S1 (manifeste, attendu, pilotes, scripts, entrée 22) ; code identique au tip du lot 1, prouvé.
- **L2** Manifeste = `results/c3_outillage_v2_3/conformite/manifest.json` (`24bde67d…565a`), **seuls**
  `research_log_entry` (entrée 22), `run_scope`, `variant_id` réécrits ; `manifest_check.sh` : ajouté ∅, retiré ∅,
  réécrit = exactement ces trois ; protocole et date différée inchangés ; `c3_anchor` local 0, `T` attendu.
- **L3** Attendu : items et codes du 30/09 ; § « Ce que ce chantier change » (passthrough sans effet ici — registres
  neufs, aucune clé en plus, dit et assumé —, test UTC, rien d'autre).
- **L4** Noms : `variant_id` `c3-racine-registre-conformite-2020`, `--campaign RACINE_REGISTRE_CONF`, runs
  `~/runs/c3_racine_registre/conf/{repo,out}`, archive `~/archive/c3_racine_registre_conf_<AAAAMMJJ>/`, tmux
  `c3-racine-registre-conf-<AAAAMMJJ>`, `--now` = `<date de S1>T00:00:00+00:00` ; famille de test inchangée.
- **L5** Porte § L.5 **non rejouée** — `invariance_porte.sh` : (a) `git diff --name-only c62acb4 <tip>` ⊆ {résultats
  v2.3 et du chantier, `docs/RESEARCH_LOG.md`, `skills/registry.md`, brief, `c3_anchor.py`, trois tests C3} ; (b) diff
  vide contre `313eb00` et `c62acb4` sur `src/ config/ pyproject.toml poetry.lock`, `scripts/` hors `c3_anchor.py`,
  `tests/` hors les trois fichiers C3 ; (c) `c3_anchor` importé seulement par `c3_verdict` et les tests C3 ; (d)
  fermeture d'import du module `_full` à la collecte, sans aucun `c3_*`. Un écart → la porte se rejoue : STOP.
- **L6** Entrée 22 avant lancement ; pilotes et scripts repris par substitutions comptées (`reprise_lot2.out`) ; dry-run
  et vérificateurs re-prouvés (cas déviés) ; **STOP 1, GO nommant le SHA** ; trois exécutions 4/1/4, même `--now`, même
  chemin absolu + `mv`, registre neuf et jeté par exécution ; 23 artefacts identiques au bit ; issue non lue ; archive
  vérifiée par codes puis supprimée ; postflight. Tunnel jamais ouvert ; `CAMPAIGN_UNLOCK` jamais créé ; `~/c3/` ni
  touché ni créé.
- **L7** Rapport final `results/c3_racine_registre/report.md` : lignes périmées pour le `docs(merge)` (`CLAUDE.md`
  l.19, l.43, l.59-60 et routage de `skills/registry.md` ; `skills/backtest.md` § « Validation C3 » ; PROJECT_CONTEXT) ;
  ce qui attend (K8, création du registre par Bruno, manifeste). STOP 2, merge par Bruno.

## 8. Règle d'arrêt

Un épinglage normatif de la racine, un test vert à `313eb00` qui rougit hors de ce plan, un XPASS, un besoin de toucher
au texte gelé ou à un module gelé (D3), un doute sur la portée de la porte § L.5 → STOP et question à Bruno.
