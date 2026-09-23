# Rapport de session C3a — outillage complet, arrêt Fin, revues Fin (deux passes) appliquées (2026-09-22)

> Fichier **versionné à la clôture documentaire du 22/09** (`docs(c3a)`, décision D1 de la session de
> clôture), comme la passation ; hors liste fermée § L.4 de l'outillage — écart documenté, à ratifier au
> gate d'amendement C3b. Il décrit ce que les artefacts et le code **contiennent**, relu sur disque au
> moment d'écrire, pas ce que la session a voulu y mettre. Les comptes, empreintes et codes cités sont
> ceux mesurés au tip.

Branche `feat/c3a-protocole`, tip **`acaeaf6`** (commit de documentation de la validation Fin ; le
code est celui de `2b62530`, validé — § 12 ; les tips soumis aux revues étaient `b53f869` puis
`b2c3485`), base de session `5e056e0` (code `e358df9`).
Protocole `docs/protocole_c3.md` **gelé au `d931293`**, sha256 `9b62915069e59e9b…`, jamais modifié.
Working tree préservé tel quel de bout en bout : `D agent/passation_c3a_20260920.md` (supprimé du
working tree, suivi à HEAD), `agent/addendum_passation_c3a_20260921.md` et
`agent/brief_reprise_c3a_20260921.md` non suivis ; aucun commit ne les embarque (`git add` par chemin
explicite seulement).

## 1. Ce qui a été livré — commits de la session

| # | SHA | Message | Arrêt |
|---|---|---|---|
| 1 | `6618e82` | fix(c3): chantier 0 — contrôle B=BOOTSTRAP_B et fixtures à 10 000 (+ tests) | |
| 2 | `9cf4688` | fix(c3): chantier 0 — constantes mortes et textes périmés | |
| 2′ | `000168d` | fix(c3): chantier 0 — contrôle B avant tout parsing (+ matrice) | R2 |
| 3 | `c360df2` | feat(c3): c3_anchor + tests | |
| 4 | `bd81b87` | feat(c3): c3_entry + tests + refus de l'artefact rejeu (results/c3a_entry_validation/) | |
| 5 | `24c2525` | feat(c3): c3_benchmark + tests | |
| 6 | `0c30ce9` | feat(c3): c3_select + tests (I.1 lignes 3-6 au paramétré) | |
| 7 | `a17acee` | test(c3): chronologie forte, trois témoins + contrôle négatif | R3 |
| 7a | `d364cd5` | fix(c3): revue R3 — D6 quantité/notionnel, couverture recoupée, pré-contrôles D3/D6, non-finis (+ tests adverses) | |
| 7b | `345f09a` | fix(c3): revue R3 — trou maximal recalculé et recoupé (+ tests) | R3 clos |
| 8 | `8997a6e` | feat(c3): c3_continuity + tests | |
| 9 | `b53f869` | feat(c3): chaîne de verdict § L.2 complète, mode chain + tests | Fin (soumis à revue) |
| F1 | `1b59ea5` | fix(c3): revue Fin (1) — confinement synthétique avant tout chemin de publication (+ matrice) | |
| F2 | `3d3f559` | fix(c3): revue Fin (2) — continuité : résumés et agrégat dérivés des clauses, jamais recopiés | |
| F3 | `e2a3be4` | fix(c3): revue Fin (3) — fenêtre du comparateur d'évaluation recoupée à [T, fin] | |
| F4 | `dfabc07` | fix(c3): revue Fin (4) — cohérence interne de chaque amont dans verify_chain | |
| F5 | `760e3a6` | fix(c3): revue Fin (5) — conjonctions : lecture stricte complète avant la logique | |
| F6 | `b2c3485` | fix(c3): revue Fin (6) — balayage : statuts dérivés des listes de sélection, continuité dérivée de l'évaluation et de l'ancre | soumis à la 2e passe |
| F2-1 | `313843e` | fix(c3): revue Fin 2 — états admissibles par clause en liste close (§ 6.4), paramétré dérivé de la table | |
| F2-2 | `2b62530` | fix(c3): revue Fin 2 — violation avant UndefinedIssue ; chain.verified défini et asserté dans les deux sens | **Fin validée** (revue Claude sur `48-g2b62530`) |
| D | `acaeaf6` | docs(c3): validation Fin — ordre de constat, convention datée du 22/09, contrat de couche de decide() | dernier commit de session, documentation seule |

Fichiers touchés, tous dans la liste fermée § L.4 : `scripts/audit/c3_{common,anchor,entry,benchmark,
select,continuity,verdict}.py` (7), `tests/test_scripts/test_c3_{common,anchor,entry,benchmark,select,
chronology,continuity,verdict}.py` (8), `results/c3a_entry_validation/` (5 fichiers).

### Vérification au tip

| Contrôle | Résultat |
|---|---|
| `pytest -q tests/test_scripts/test_c3_*.py` | **806 passés** au tip `2b62530` (anchor 127, entry 127, verdict 360, select 54, common 50, continuity 51, benchmark 28, chronology 9) ; 754 au `b2c3485`, 605 au `b53f869` |
| `pytest -q --ignore=tests/test_scripts/test_run_p6_determinism.py` | **2615 passés, 6 skipped (218.73 s)** au tip `2b62530` (2563 / 6 au `b2c3485`, 2414 / 6 au `b53f869`) |
| `ruff check .` | vert |
| `ruff format --check` sur les 15 fichiers C3 | vert (12 fichiers hors chantier — `rejeu_*`, `p6_5_*` — étaient déjà non formatés avant la session, non touchés) |
| `mypy src/` | **65 erreurs** = baseline (la 65e : stubs pandas, `feature_store.py:32`) |
| diff de contrôle § L.3 depuis `5e056e0` (`src`, `scripts/backtest.py`, runners P6/P7, `p7_grids.py`, `compute_benchmarks.py`, `config`, `pyproject.toml`, `poetry.lock`) | **vide** |
| `results/rejeu_grid_20260919/P7_phase1_grid.json` | intact, sha256 `08d981e493402f37a8649a47090293a8f64358b61d8558d4978f13e1ff6436c6` |
| `results/c3a_entry_validation/` (5 fichiers) | intacts, empreintes du § 3 inchangées par la revue Fin |
| `len(THRESHOLDS)` | 23 — aucun seuil nouveau |

Leçon de vérification consignée : le commit 4 est parti une première fois sur un test rouge masqué par
`pytest \| tail` (le code de sortie du pipeline était celui de `tail`) ; amendé en `bd81b87` avant tout
push. Depuis, **`set -o pipefail`** précède toute invocation de test en pipeline.

## 2. Done du brief v2 — état, clôture distinguée

| Critère (brief v2, « Critère de fin ») | État | Où |
|---|---|---|
| Gate 1 passé ; gate 2 passé avec arrêt effectif avant tout outillage | fait (sessions antérieures) | `docs/protocole_c3.md` @ `d931293` |
| Décisions A, A bis, B, C, D tranchées et écrites dans le protocole | fait (antérieur) | idem |
| Test de chronologie vert au sens fort | **fait** | `test_c3_chronology.py` : trois témoins (préfixe seul, + futurs A, + futurs B), trois issues, permutation, provenance contaminée, contrôle négatif détectant un scoreur fuyant |
| Parcours complet sur fixtures synthétiques, puis validation **ou rejet motivé** des artefacts réels | **fait** | fixtures : chaîne `anchor → entry → benchmark → select → continuity → verdict` par la sous-commande `chain` (test `test_chain_complete_sur_fixtures…`) ; réel : refus `D_WARMUP_PREFIX` de l'artefact du rejeu (§ 3) et arrêt de `chain` à `entry`, code 2, aucun `verdict.json` |
| Scénarios : aucune configuration admissible, égalités au classement, frontière interne, données manquantes à l'ancrage | **fait** | `test_c3_select.py` (ensemble vide, sous le plancher, égalités à chaque niveau, permutation), `test_c3_entry.py` (D2 totalité / partie, `sufficient` recalculé), `test_c3_continuity.py` (c4 amorçage à T) |
| Plan d'évaluation de la précision écrit dans le protocole | fait (antérieur) | protocole § F |
| Contrat de continuité tranché ; vérification au gate 1 | fait (antérieur) ; l'outillage `c3_continuity` en rapporte les cinq clauses | § 4 ci-dessous |
| Diff de contrôle vide hors liste fermée ; `pytest` et `ruff` verts ; `mypy src/` ≤ baseline | **fait** — baseline **65** (cf. § 5 : re-baseline) | § 1 |
| Brief C3b proposé | **hors session** (clôture, session séparée) | — |
| Diagnostic grid gelé et ses artefacts intacts | **fait** | sha256 ci-dessus |

**Relèvent de la clôture, session séparée, non commencés** : `skills/backtest.md`, `results/INDEX.md`,
`ROADMAP.md`, `PROJECT_CONTEXT.md`, `docs/CODE_MAP.md`, les blocs `C3A-INTERIM` (dont la note de
`CLAUDE.md` qui dit encore que cinq modules « n'existent pas encore »), le brief C3b, tout amendement
du protocole. Le fichier `agent/passation_c3a_20260920.md` reste supprimé du working tree et suivi à
HEAD : sa correction (baseline mypy 64 → 65) est un item de clôture.

## 3. Ce que les artefacts réels contiennent — `results/c3a_entry_validation/`

| Fichier | sha256 (16) | Taille |
|---|---|---|
| `manifest_rejeu_grid_20260919.json` | `ec50063c9e6128e3` | 28 257 o |
| `variants.json` | `18f263aea7ac9bfd` | 845 o |
| `anchor_rejeu_grid_20260919.json` | `0ad3fa7edbbb5472` | 2 210 o |
| `entry_rejeu_grid_20260919.json` | `900e4dacd4d94124` | 32 413 o |
| `entry_rejeu_grid_20260919.md` | `b1e7f3d36940d171` | 10 181 o |

**Manifeste** : provenance `contaminated`, 96 candidats, préfixe `train`, `data = {exchange: binance,
exec_interval: 5, timeframes: {5m: 5, 4h: 240, 1d: 1440, 1w: 10080}}`, `variant_id
c3a-entry-rejeu-grid-20260919`, parent racine, seuils = registre `THRESHOLDS`, `run_scope` : « ce run
établit le refus D2 seul ; le manifeste est dérivé des clés de l'artefact qu'il encadre, donc ses
assertions D5 ne prouvent rien d'indépendant ; provenance `contaminated` = qualification du rapport
gelé results/rejeu_grid_report.md § 10.3 ; aucun classement, aucun verdict économique sur la famille
grid (§ D.3) ». Le manifeste a été **généré par un script de scratchpad non committé** depuis les clés
de l'artefact qu'il encadre — c'est ce que `run_scope` dit.

**Anchor** : `anchor = 2025-05-07T04:48:00+00:00`, `prefix_days = 767.2`, `evaluation_days =
328.79999999999995` (float, tel qu'écrit), estampilles admissibles `{5: 04:45, 240: 04:00, 1440:
2025-05-07T00:00, 10080: 2025-05-05T00:00}`, première bougie d'exécution après T `04:50`,
`variant_key dd2a4751b9db4c10…` (= `sig(canon(manifeste))`), registre `{new_entry: true, sha256
18f263ae…}`, `frozen_values_asserted = [anchor_fraction, uncertainty, thresholds, protocol_sha256]`,
provenance `contaminated`.

**Entry** : `ok false`, `exit_code 2`, `invalide false` ; assertions I-A.1 ok, **I-A.2
`not_assertable`** (D5 intervalle d'exécution : aucun porteur `exec_interval` dans les 96 entrées),
I-A.3 ok, I-A.4 ok (96 identités = univers), I-A.5 ok, I-A.6 ok (`sufficient` recalculé = déclaré),
**I-A.7 `not_assertable`** (couverture non fournie, `coverage = {path: null, sha256: null, status:
not_provided}`), **I-A.8 `failed`** ; `refusal = {reason: D_WARMUP_PREFIX, scope: artefact, assertion:
I-A.8}` ; `n_candidates 96`, `n_candidates_d2_failed 96` ; diagnostics : 48 candidats (BTC) séries
insuffisantes `1d, 1w`, 48 (SOL) `4h, 1d, 1w` ; `observations.sha256 = 08d981e4…` ; `sentence =
NON_RECEVABLE_SENTENCE`. Le refus D2 est de **portée artefact** : aucun classement, aucun score.

Ce que l'artefact réel **ne prouve pas** : D5 (manifeste dérivé), D1 (pas de couverture), et il
n'atteint ni le benchmark ni la sélection. Le mode `chain` sur ce même artefact (test d'intégration)
s'arrête à `entry`, code 2 : `anchor.json` et `entry.json` écrits, rien d'autre, `verdict.json` absent.

## 4. § 4 du plan révisé — état final de chaque ligne

| # | Objet | Cat. | État final |
|---|---|---|---|
| 1 | `B ≠ BOOTSTRAP_B` → R0 code 2, contrat avant cohérence | A | **livré** (`_estimability_of`, en tête, avant tout parsing ; matrice 5 lignes en appel direct et CLI) |
| 2 | artefact diagnostic écrit en code 1 | S | **livré** dans les six modules (`cc.envelope(..., exit_code=1)`, `invalide: true`) |
| 3 | ordre I-A ; D5 « intervalle » et couverture sans porteur | A | **résolue** par `not_assertable` (jamais verte : R0 en `I-A.fin`) |
| 4 / 4′ | champs du manifeste ; D2 stratégie + surcharge par candidat | S / A | **livré** (`cc.Manifest`, `decision_timeframes` par stratégie, surcharge par candidat) |
| 5 / 5′ | registre de variantes ; `variante=` = clé `sig(canon(manifeste))` | S / A | **livré** (`c3_anchor.register` : idempotence, parent absent → R0, seconde racine → R0, altéré → violation ; clé en 7e champ de la chaîne) |
| 6 | `NOT_ESTIMABLE` ∉ admissible ; ensemble vide → `A_NO_ADMISSIBLE_CANDIDATE` | A | **livré** (`c3_select`) |
| 6′ | benchmark de paire non constructible au préfixe → paire `DESCRIPTIF`, candidats `E_NO_BENCHMARK` | A | **livré** |
| 7 / 7′ | table provenance × résultat → statut ; abstention sous contamination = `ABSTENTION` | S / A | **livré** (`selection_status`, recoupée côté verdict : statut dérivé ≠ déclaré = violation) |
| 8 | `liquidation`/`dca_counters` optionnels ; null ⇒ D6 échoue | A | **livré** ; preuve D6 = preuve par lot (§ 6.5) |
| 9 | D3 « aucune vente » par `winning + losing == 0 ∧ total_trades > 0` | S | **livré** (`cc.clause_d3`, raison `C_COVERAGE` documentée, ordre d'affichage D3 puis D6) |
| 10 | métriques recalculées ; MDD : décisions sur recalculé, écart rapporté non classé | S | **livré** (`mdd_recorded`, `mdd_recomputed`, `mdd_abs_diff` rapportés ; aucune violation sur un ulp) |
| 11 | λ dans `c3_benchmark` ; cible > B&H → `NOT_ESTIMABLE` ; tolérance par candidat | — | **livré** (§ 6.2 : pré-contrôles D3/D4/D6 sans score, non-fini fourni → 1) |
| 12 / 12′ | benchmark § C.3 strict ; `candles.json` quatrième entrée hors chaîne | A | **livré** (`--candles`, empreinte dans `benchmark.json`) |
| 13 | chaîne § L.2 neuf champs ; empreintes ; site `chain` | S | **livré** (commit 9, § 6 ci-dessous) |
| 14 | continuité : états, table clause → verdict ; confinement | — | **livré** (§ 6.4, § 6.6) |
| 14′ | clause 3 `FAILED` à l'évaluation | **D** | **convention datée du 21/09** : `UndefinedIssueError`, code 2, rien publié ; amendement (a) dû à C3b |
| 14″ | clauses déclaratives c1/c2/c5 `FAILED` ⇒ R0 code 2 | A | **livré** |
| 15 | D2 et `sufficient` recalculés et recoupés | S | **livré** (I-A.6, I-A.8, `d1_for_pair`, `c3_select` recoupe `entry.candidate_diagnostics`) |
| 16 | schéma d'évaluation (six distributions) | hors périmètre | **intact** |

## 5. Décisions du second R1 et des revues R3 — telles qu'appliquées

**Second R1 (21/09)** : R2 compléments (`B` avant tout parsing + ligne de matrice ; mypy 65
documenté) ; § 6.1 conduite (b) ; § 6.5 preuve par lot avec `lots` sous `liquidation[seg]`, témoins
porteurs de lots ; § 6.2, 6.3, 6.4, 6.6 validés + test des neuf champs sous les deux labels ; § 4 et
§ 13 validés ; ligne 12′ tranchée `candles.json` ; § 5.2 liste close des quatre assertions gelées.

**Revue R3, première passe (a-d)** : (a) D6 quantité/notionnel — `amount_i > 0`, `gross_i == amount_i ×
price`, `fee_i == gross_i × taker` par lot, agrégats recoupés, dans `cc.liquidation_identities`
partagée par `c3_select` et `c3_continuity` ; (b) couverture recoupée avant D1 (`cc.coverage_recompute`
à I-A.7 et dans `d1_for_pair`) ; (c) pré-contrôles D3/D6 au benchmark, aucun score pour un candidat
inadmissible ; (d) `NonFiniteValueError` (levée par `canon`, n'est pas une `InvalidValueError`) routée en
violation dans les cinq `main()`, puis dans `c3_continuity` et `c3_verdict`. Tests adverses
rouges-avant à chaque correction.

**Revue R3, seconde passe** : `longest_gap_days` **recalculé** sur la grille attendue, bords compris
(`cc.longest_missing_run`, `cc.gap_days`), recoupé à I-A.7, consommé par `d1_for_pair` — contre-exemple
Astra : 6 636 bougies 5 min, couverture 744/767 = 97,0013 %, trou 23,0417 j > 23,016 j → D1 échoue
alors qu'un `longest_gap_days` déclaré le masquait. D3/D6 : rien à coder ; `C_COVERAGE` documentée
comme raison de D3, ordre d'affichage D3 puis D6.

**Fait relevé en route** : les clés `residual_trade_btc`, `dust_written_off_btc`,
`inventory_divergence_btc`, `amount_btc` sont **littérales pour toutes les paires** (convention
`btc_held`, `backtest.py:3288-3293`) ; l'outillage les lit telles quelles. La question du renommage va
au brief C3b, pas à l'outillage.

## 6. Fin de chaîne § L.2 — ce que `c3_verdict.py` contient au tip

- **Neuf champs** : `C3_<c> | verdict= | raison= | selection= | statut_selection= | continuite= |
  variante=<16 hex> | provenance= | protocole=<16> | observations=<16>`. `variante` =
  `anchor.variant_key` ; `observations` = `entry.inputs_sha256.observations`, recoupée à celle de
  `selection`. Test : présence **et** correspondance à l'entrée sur disque de chaque champ, sous les
  deux labels — `C3_<c>` au niveau fonction (la CLI ne le produit jamais en C3a) et `C3_SYNTH_<c>` par
  la CLI et par `chain`.
- **`inputs_sha256` des cinq entrées** dans les deux payloads (`cc.envelope("verdict", …)`), normal
  et diagnostic ; `chain {mode: verdict|chain, steps: [{name, exit_code}], verified, checks[17]}`.
- **`verify_chain`** : d'abord la **cohérence interne** de chaque amont (`artifact_coherence`, revue
  Fin 4 : `ok ⟺ exit_code == 0`, `invalide ⟺ exit_code == 1`, entry : `exit_code == 2 ⟹ refus porté`,
  `refus porté ⟹ exit_code ≠ 0` ; contradiction = violation 1, check `<amont>.coherence`) ; puis
  `require_upstream_ok` sur anchor/selection/continuity cohérents, `entry.invalide` → R0 ; neuf
  recoupements d'empreintes (manifeste entre anchor/entry/selection/continuity ; observations entre
  entry/selection ; `anchor.json` tel que consommé par entry/selection/continuity ; `entry.json` par
  selection ; `evaluation.json` par continuity) + quatre `protocole.sha256` — 17 checks ; discordance =
  violation, code 1. Les contradictions sont consignées dans les listes du demandeur (rien n'est
  perdu si un refus lève ensuite). **`chain.verified`, définition fixée (revue Fin 2)** : intégrité
  mécanique de la chaîne — codes de succès des amonts, cohérence interne de chaque amont,
  empreintes concordantes ; pas la qualité de l'issue ; vrai dans tout artefact normal (un
  `inconclusif E_NO_BENCHMARK` compris), faux sur toute violation ou refus consigné après
  violation ; un refus sans violation ne publie rien.
- **Sous-commande `chain`** (`c3_verdict.py chain --manifest --observations [--coverage] [--candles]
  --evaluation --benchmark-eval --registry --out-dir [--campaign] [--now]`) : invoque en processus
  `c3_anchor.main → c3_entry.main → c3_benchmark.main → c3_select.main → c3_continuity.main`, arrêt
  au premier code ≠ 0 (rend ce code, rien d'autre écrit), puis `verify_chain`, puis le verdict ;
  fichiers `out-dir/{anchor,entry,benchmark,selection,continuity,verdict}.json`. **Contre-exemple
  testé** : run 1 cohérent sur disque ; `variants.json` corrompu (`{"variants": [1]}`) → run 2 :
  `c3_anchor` rend 2 avant toute écriture, `chain` rend 2, les six fichiers sont octet pour octet
  ceux du run 1, et `verify_chain` sur ces fichiers **passe** — les empreintes ne prouvent pas que
  l'invocation courante a réussi, seul le code de retour effectif le fait. Un `verdict.json`
  antérieur n'est jamais supprimé (§ L.4) ; discordant, il est signalé sur stderr.
- **Confinement `evaluation.synthetic`** (§ L.1, plan § 6.6 ; revue Fin 1) : `require_synthetic()` est
  le **premier** contrôle de `decide()` et de `run_verdict()`, avant tout chemin de publication —
  verdict calculé, abstention, diagnostic : absent / null / `"true"` → 2, rien écrit ; `false` →
  `EntryRefusedError("R0_INVALID_RUN", "évaluation réelle non exerçable par l'outillage C3a — § L.1
  …")`, code 2, rien écrit (même si une violation a été constatée) ; `true` → label `C3_SYNTH_<c>` et
  `portee = "exercice synthétique de l'outillage — aucune portée économique (§ L.1)"` dans **les deux**
  payloads, imprimée en première ligne dans les deux formes. Matrice testée {abstention, verdict
  calculé, diagnostic} × {true, false, absent, null, "true"} aux trois niveaux (fonction, CLI, chain).
- **Continuité → verdict** (table § 6.4 ; revue Fin 2, 3, 6) : `continuity.json` porte, outre les
  clauses c1..c5, deux blocs dérivables — `stamp_cell` (§ B.4 : `VERIFIED` / `FAILED` /
  `NOT_VERIFIABLE`) et `comparator` (§ C.5 : `tests` = cinq booléens déclarés + `window_ok` recalculé,
  `window {declared, expected}`, état dérivé de la conjonction) — et ses quatre résumés **dérivés** des
  blocs (`warmup_anchor_ok = c4 VERIFIED`, `liquidation_normalised = LIQUIDATION_NORMALISED_OF_C3[c3]`,
  `stamp_same_daily_cell = stamp_cell VERIFIED`, `benchmark_comparable = comparator VERIFIED`) et
  l'agrégat `continuity_aggregate(c1..c5)` (précédence `FAILED > NOT_VERIFIABLE > DECLARED >
  VERIFIED`, une seule définition dans `c3_common`). Le verdict **refait toutes ces dérivations** et
  recoupe chaque valeur déclarée (contradiction = violation 1) ; il dérive aussi `identity` de
  `evaluation.{strategy, pair, params}`, recoupe `pair`, `synthetic`, `evaluation_window` à
  `[anchor.anchor, anchor.window.end]`, `comparator.window.expected` à `evaluation_window`, et refait
  `window_ok`. **Les actions se branchent sur les clauses** : identité dérivée ≠ retenue → R0 ; c1/c2/c5
  `FAILED` → R0 code 2 ; **c3 `FAILED` → `UndefinedIssueError`**, code 2, rien publié, stderr `ISSUE
  NON DEFINIE … amendement pendant (§ 6.1) … convention d'outillage datée du 21/09` (testé en clair,
  fixture « moteur signal à l'évaluation », `liquidation` null, aux trois niveaux) ; c4 `FAILED` →
  `D_WARMUP_ANCHOR` ; comparateur `FAILED` (test faux **ou fenêtre ≠ [T, fin]**) → `E_NO_BENCHMARK` ;
  `stamp_cell` non `VERIFIED` → `E_STAMP_MISMATCH`. **Chaque état est lu contre la liste close de sa
  clause** (colonne « États atteignables (C3a) » de § 6.4, `cc.CLAUSE_ADMISSIBLE_STATES` ; revue
  Fin 2) — c4 « non vérifiable » ou « déclarée », c1/c2/c5 « vérifiées », c3 « déclarée » → code 2,
  rien publié, chez le producteur comme au verdict ; l'agrégat `VERIFIED` est inconstructible en C3a
  (108 combinaisons admissibles testées). La chaîne porte l'agrégat **dérivé** ; les attendus des
  tests sont dérivés de la table (`TABLE_6_4`, vingt lignes avec appui), jamais du code. `decide()`
  lit strictement les cinq entrées **avant** tout chemin de publication, abstention comprise.
- Test d'intégration sur `results/rejeu_grid_20260919/P7_phase1_grid.json` avec le manifeste et une
  copie du registre committés : arrêt à `entry`, code 2, `entry.json` avec `refusal.reason
  D_WARMUP_PREFIX` et 96/96, aucun `benchmark.json`/`selection.json`/`continuity.json`/`verdict.json`,
  source et registre committé intacts, fichiers `--evaluation`/`--benchmark-eval` (`{}`) jamais lus.
- **Sélection consommée par le verdict** (revue Fin 6) : `retained` = tête de `ranking`, `reason`
  dérivée des listes (`survivors` vides ∧ `admissible` vide → `A_NO_ADMISSIBLE_CANDIDATE` ; `survivors`
  vides → `A_BELOW_FLOOR` ; sinon aucune), `ranking` permutation de `survivors`, `survivors ⊆
  admissible`, statut dérivé de (provenance, retenue dérivée) ; déclaré ≠ dérivé = violation ; les
  listes sont obligatoires et typées.
- Parseurs : le parseur verdict n'expose que cinq chemins, `--campaign`, `--output`, `--now` ; le
  parseur `chain` huit chemins, `--campaign`, `--now`. Aucun paramètre libre.

## 7. Conventions d'outillage validées — liste

1. **Artefact diagnostic écrit en code 1** (I.1 muette sur la forme) : `invalide: true`, violations
   listées, aucun verdict, aucune raison, aucune chaîne citable.
2. **`B ≠ BOOTSTRAP_B` → code 2, R0 avant tout parsing** (un `B` hors contrat accompagné d'un compteur
   contradictoire ou d'un non-fini sort en refus 2, jamais en violation 1 par accident d'ordre).
3. **`UndefinedIssueError` → code 2, rien publié** (clause 3 de continuité en échec à l'évaluation) —
   convention datée du 21/09 ; l'amendement (a) ajoutant la ligne run `R1_NOT_NORMALISED` à I.1 est
   dû à l'ouverture de C3b et remplacera cette convention.
4. **Table provenance × statut** : retenu ∧ `clean` → `SÉLECTION_VALIDE` ; retenu ∧ `contaminated` /
   `unknown` → `SÉLECTION_DESCRIPTIVE` ; non retenu → `ABSTENTION` (raison `A_NO_ADMISSIBLE_CANDIDATE`
   ou `A_BELOW_FLOOR`, chaîne `P_PROVENANCE` par priorité sous contamination). Calculée par
   `c3_select`, recoupée par `c3_verdict`.
5. **`not_assertable` jamais verte** : consignée, ne bloque pas le parcours, interdit `ok=True` (R0 en
   `I-A.fin`).
6. **Convention moteur `_btc` littérale** pour toutes les paires ; renommage → brief C3b.
7. **`C_COVERAGE` raison de D3** (aucune vente détectable) ; **ordre d'affichage D3 puis D6**.
8. **Incident `pytest | tail`** → `set -o pipefail` obligatoire.
9. **Re-baseline mypy à 65** (rapport C2 ; la passation disait 64 — correction = item de clôture).
10. Non-finis ou hors domaine **fournis** → violation 1 partout ; absent / null / mal typé / hors liste
    close → 2, rien écrit (sauf `c3_entry`, qui écrit toujours).
11. `evaluation.synthetic` obligatoire ; évaluation réelle refusée ; préfixe `C3_SYNTH_`.
12. Clauses déclaratives de continuité `FAILED` → R0 code 2 ; aucune déclaration ne produit
    `VERIFIED` (agrégat `NOT_VERIFIABLE` ou `DECLARED` en C3a).
13. (revue Fin) **Résumés et agrégat dérivés des clauses par le consommateur**, contradiction =
    violation ; actions branchées sur les clauses. **Cohérence interne** de chaque enveloppe amont
    (`ok ⟺ exit 0`, `invalide ⟺ exit 1`, refus ⟺ exit 2 pour entry) assertée avant d'en lire le
    succès. **Conjonctions** : tout lu et typé, puis conjoint. **Confinement en tête** de tout chemin de
    publication. **Fenêtre du comparateur d'évaluation** recoupée à [T, fin] par C3a (le producteur ne
    connaît pas T) : discordante → non comparable, sans violation.
14. (revue Fin 2) **Listes closes par clause** (§ 6.4), des deux côtés ; **lecture stricte complète
    des cinq entrées avant tout chemin** (abstention, raison run, réfuté, validé) ; **précédence** :
    contradiction déclaré / dérivé → diagnostic 1 même avec c3 en échec, le refus 2 `UndefinedIssueError`
    réservé au cas cohérent ; `chain.verified` = intégrité mécanique (§ 13.7). **Convention
    d'outillage datée du 22/09** (ratifiée à la validation Fin, § 13.7) : preuve obligatoire absente
    constatée **après** une violation → code 2, rien publié, violations dites sur stderr.

## 8. Exigences C3b accumulées (consignées, non traitées)

- Export par le runner de **`lots`** dans `liquidation[seg]` (`amount_<base>`, `gross_usdc`, `fee`,
  `entry_price|null`, `pnl|null`) — sans lui D6 n'est pas `VERIFIED` et aucun candidat réel n'est
  admissible.
- Export par le runner de **l'intervalle d'exécution** (`exec_interval`) et un **producteur de
  couverture** (`coverage.json`) — les deux `not_assertable` de l'artefact réel.
- **Amendement daté** ajoutant la ligne run `R1_NOT_NORMALISED` à I.1 (remplace la convention 3).
- **Paquet de clarifications normatives** : E2 sur les six distributions et la frontière de confiance ;
  tolérance MDD enregistré ↔ recalculé (aujourd'hui rapportée, non classée) ; écart d'énumération
  § L.1 (trois entrées énumérées, `candles.json` quatrième entrée hors chaîne).
- Question du **renommage des clés `_btc`** du bloc `liquidation`.
- **Exécution continue et preuve de départ à plat** (§ B.2), préalables à toute évaluation réelle.

## 9. Écarts consignés avec les fonctions du rejeu (aucune réutilisation telle quelle)

| Fonction du rejeu | Écart avec le protocole gelé | C3a |
|---|---|---|
| `rejeu_effect.match_lambda` (`:267`) | retient λ = 1 `above_bh` quand la cible dépasse le B&H | § F.2 g / § C.6 : `NOT_ESTIMABLE` ; résidu > `LAMBDA_RESIDUAL_MAX` (10 %) non estimable ; raffinement sur la grille 0,001 |
| `rejeu_benchmark.select_entry_candle` (`:166`) | choix de la bougie d'entrée contraire à § C.3 | décider à la borne, exécuter à la première bougie d'exécution **strictement après** ; aucune substitution d'estampille |
| `rejeu_benchmark.comparability_block` (`:301`) | code le compte du rejeu | `comparability` recalculée § C.5 (`entry_stamp_present`, `exit_stamp_present`, `ff_ok`, `n_returns_ok`, `all_finite`), recoupée au déclaré |

Précédents **repris** comme modèles, pas comme code : `rejeu_validate_campaign.run_assertions`
(« sauté, jamais vert »), `rejeu_validate_analysis.b02_frozen_parameters` (contrôle `B`).

## 10. Point § L.5

`git diff --stat f585e8b -- <chemins § L.3>` = **`pyproject.toml` seul** (+7/−1, exclusions Ruff).
L'option 2 de § L.5 (« aucun changement depuis le dernier SHA de déterminisme documenté ») n'est **pas
littéralement disponible**. **Deux conditions écrites, porte pré-merge, hors session** — la validation
Fin (22/09) clôt la session agent, pas la porte pré-merge :

1. **Option 1 due** : 24 tests de déterminisme sur le serveur au SHA livré (recette C2) — sauf
   décision humaine **écrite** traitant l'écart.
2. **Re-passe Astra due** : la revue Astra a été suspendue faute de quota après `b2c3485` ; ses scripts
   de reproduction doivent être relancés sur le SHA final avant tout merge.

## 11. Ce que ce rapport ne dit pas

Aucun verdict économique. Aucune sélection. La seule sortie réelle de l'outillage est le **refus** de
l'artefact du rejeu (§ 3). Les trois issues (`validé`, `réfuté`, `inconclusif`) ne sont exerçables que
sur fixtures déclarées synthétiques, sous le label `C3_SYNTH_`.

## 12. Après ce rapport — clôture de session (validation Fin du 22/09)

Fin validée par la revue de Claude sur l'archive `48-g2b62530` (806 tests C3 reproduits, les sept
reproductions adverses des revues Fin constatées mortes, structures vérifiées). Dernier commit de
session : documentation seule (docstrings de `c3_verdict.py`, § 2 de la validation), archive finale
régénérée, arrêt définitif. Restent, hors session et dans cet ordre : revue du rapport par Bruno et
Claude ; docs de clôture (blocs `C3A-INTERIM`, `skills/backtest.md`, correction du chiffre mypy de la
passation, `results/INDEX.md`, `ROADMAP.md`, `PROJECT_CONTEXT.md`, `docs/CODE_MAP.md`) ; brief C3b avec le
paquet d'amendements accumulé (ligne run `R1_NOT_NORMALISED`, E2 sur les six distributions, tolérance
MDD, énumération § L.1 / `candles.json`, export des lots par le runner, conventions datées du 21/09 et
du 22/09 à ratifier) ; puis la porte pré-merge § L.5 (§ 10). Le working tree reste préservé jusqu'au
bout.

### Texte antérieur

Arrêt Fin. Archive régénérée pour la revue Astra / Claude : `~/Desktop/krakenbot-src-<git describe>.zip`
(`git archive --format=zip --prefix=kraken-trading-bot/ HEAD`, fichiers suivis seulement, commentaire
= SHA complet). Rien d'autre : docs de clôture, blocs `C3A-INTERIM`, brief C3b, amendements — session
séparée, après revue. **La première revue (§ 13) a rendu cinq défauts ; corrigés, archive régénérée
au `b2c3485` pour la seconde passe.**


## 13. Revue Fin (Astra / Claude, 22/09, sur `b53f869`) — six correctifs, rouges-avant

Cinq défauts reproduits par le script d'Astra, un balayage des deux motifs récidivants. Chaque
correctif est arrivé **avec ses tests adverses écrits d'abord, exécutés rouges contre le code du tip
précédent, puis verts** ; les sorties rouges sont conservées dans le scratchpad de session
(`rouge_avant_<n>.txt`) et résumées ici. Un commit par défaut, chacun vert (`pytest` C3 + `ruff`,
`set -o pipefail`).

| # | Défaut (P) | Commit | Rouges-avant | Ce qui a changé |
|---|---|---|---|---|
| 1 | Confinement synthétique : l'abstention retournait avant le contrôle `evaluation.synthetic` (une abstention synthétique publiait `C3_C3A` ; une évaluation réelle + violation publiait un diagnostic) (P1) | `1b59ea5` | **15 / 45** (abstention publiée sans contrôle 0≠2, `decision.synthetic` None, diagnostic sans `portee`, diagnostic publié sur évaluation réelle 1≠2) | `require_synthetic()` en tête de `decide()` et de `run_verdict()` ; `synthetic`/`portee` dans les deux payloads ; `PORTEE` en première ligne des deux rendus ; matrice {abstention, verdict, diagnostic} × {true, false, absent, null, "true"} × {fonction, CLI, chain} |
| 2 | Continuité : le verdict lisait les résumés, pas les clauses (c4 `FAILED` + `warmup_anchor_ok` vrai → « validé » ; agrégat `VERIFIED` déclaré avec c1/c5 `NOT_VERIFIABLE` accepté) (P1) | `3d3f559` | **26 / 47** (validé avec `continuity_state='FAILED'`, résumés contredits sans violation, blocs non exigés, sortie de continuité sans `stamp_cell`/`comparator`) | `c3_common` : `CONTINUITY_SEVERITY`, `continuity_aggregate`, `LIQUIDATION_NORMALISED_OF_C3`, `COMPARABILITY_TESTS` (une définition) ; `c3_continuity` : blocs `stamp_cell` et `comparator`, résumés dérivés ; `c3_verdict._continuity_gates` : lecture complète, dérivations, recoupements, actions sur les clauses ; tests : les deux reproductions, un cas par résumé contredit dans les deux sens, clause × état, blocs manquants → 2 |
| 3 | Fenêtre du comparateur d'évaluation non recoupée (2000–2001 comparable) (P2) | `e2a3be4` | **9 / 9** (validé sur 2000–2001 ; fenêtre non exigée ; continuité code 0 sans fenêtre) | `comparator_block(anchor, end)` : `window_ok` recalculé, `window {declared, expected}` ; discordante → `FAILED`, voie `E_NO_BENCHMARK`, sans violation ; verdict : `window_ok` re-dérivé, `expected` recoupée à `evaluation_window` ; `chain.verified` faux dans tout diagnostic ; `fx.benchmark_eval(window=…)` |
| 4 | Aucun contrat de cohérence interne des amonts (`ok=true, refusal=null, exit_code=2` passait) (P2) | `dfabc07` | **20 / 31** (contradictions sorties en refus 2 ou passées ; entry ok/exit 2 → validé) | `artifact_coherence()` : `ok ⟺ exit 0`, `invalide ⟺ exit 1`, entry `exit 2 ⟹ refus`, `refus ⟹ exit ≠ 0`, `exit_code ∉ {0,1,2}` → 2 ; asserté pour les quatre amonts avant `require_upstream_ok` ; check `<amont>.coherence` (17 checks) ; échec amont **cohérent** → refus 2 inchangé |
| 5 | `all()` paresseux sur les cinq booléens de comparabilité (clé absente derrière un faux → 0 au lieu de 2) (P2) | `760e3a6` | **7 / 10** (continuité 0≠2 ×3 ; benchmark « DID NOT RAISE » ×2 ; sélection 1≠2 ×2) | `comparator_block` : dict des cinq lus, puis `all()` ; `c3_select` : chaque `candidate_diagnostics[i]` bloc typé lu avant classement ; `c3_benchmark.candidate_block` : métriques, liquidation et preuve D6 lues avant le premier pré-contrôle |
| 6 | Balayage : statuts consommés sans dérivation | `b2c3485` | **17 / 17** (retenue ≠ tête du classement validée ; raison non dérivée ; listes non exigées ; identité/paire/portée/fenêtre de continuité non recoupées ; ancre sans date acceptée) | `selection.retained/reason/status` dérivés des listes ; `continuity.identity` dérivée de l'évaluation (comparée à la retenue), `pair`/`synthetic` recoupés, `evaluation_window` recoupée à `[anchor.anchor, anchor.window.end]` |

### 13.1 Balayage — motif « résumé, statut ou booléen consommé sans dérivation » (`c3_verdict`, `c3_continuity`)

**Dérivés et recoupés (commits F2, F3, F6)** : agrégat de continuité ; `warmup_anchor_ok`,
`benchmark_comparable`, `stamp_same_daily_cell`, `liquidation_normalised` ; état du comparateur (de ses
tests et de sa fenêtre) ; `comparator.tests.window_ok` ; `comparator.window.expected` ;
`selection.retained`, `selection.reason`, `selection.status` ; `continuity.identity`, `continuity.pair`,
`continuity.synthetic`, `continuity.evaluation_window`.

**Justifiés — déclaration non dérivable, ou résultat recalculé d'un amont lié par empreinte, hors des
entrées de l'étape (§ L.1)** :

| Site | Justification |
|---|---|
| `anchor.universe_provenance` | déclaration non dérivable (§ A.5) ; recoupée à `selection.provenance` |
| `anchor.variant_key` | dérivable du manifeste seul, que le verdict ne lit pas (cinq entrées § L.1) ; recalculée par `c3_anchor`, liée par `inputs_sha256.manifest` commun aux quatre amonts |
| `anchor.anchor`, `anchor.window` | recalculés du manifeste par `c3_anchor`, recoupés par `c3_entry`, `c3_select`, `c3_continuity` (chacun lit le manifeste) ; le verdict les consomme pour dériver la fenêtre d'évaluation |
| `entry.refusal.{reason, scope, detail}` | résultat des assertions I-A de `c3_entry`, non recalculable sans observations ; cohérence `ok/exit_code/refusal` assertée (F4) |
| `continuity.clauses.c*.state` | résultat recalculé de `c3_continuity` sur `evaluation.json` (empreinte recoupée) ; les refaire exigerait le manifeste (taker, coûts par paire), hors des entrées du verdict ; résumés et agrégat en sont dérivés |
| `evaluation.metrics.{net_pnl, cagr_pct, delta_dd}`, `evaluation.bounds` | schéma d'évaluation hors périmètre (brief § 5) ; `delta_dd` et les six bornes ne sont pas dérivables sans les séries du comparateur ; `net_pnl`/`cagr_pct` le seraient depuis `equity_daily` mais leur recoupement change le contrat d'évaluation → paquet de clarifications C3b (§ 8), consigné, non traité |
| `evaluation.B`, `discarded`, `delta_stars`, `estimability` | déjà recalculés/recoupés (chantier 0) |
| `c3_continuity` : `invocation.single_call`, `flat_start_proof`, `first_fill_at`, `synthetic` | déclarations non dérivables — états `DECLARED`/`NOT_VERIFIABLE`, jamais `VERIFIED` ; `flat_start_proof` contrôlé cohérent (cash = C, quantité 0, 0 ordre) |
| `c3_continuity` : `sufficient`, `comparable`, `anchor.anchor`, `period`, `equity_daily.{start, end}`, `benchmark_eval.pair` | recalculés ou recoupés (déjà) |

### 13.2 Balayage — motif « conjonction, court-circuit, retour anticipé sur champs obligatoires » (cinq modules)

**Corrigés (F5)** : `c3_continuity.comparator_block` (`all()` générateur) ; `c3_select` (`isinstance(d,
Mapping) and require_str(...)` sautait en silence un élément non typé de `entry.candidate_diagnostics`) ;
`c3_benchmark.candidate_block` (retours « pas de comparateur », D3, D4 avant la lecture des métriques,
du bloc de liquidation et de la preuve D6).

**Justifiés** :

| Site | Justification |
|---|---|
| `c3_verdict._gate_results`, `_bounds_all_positive`, `artifact_coherence`, `_entry_contract`, `_continuity_gates` | lecture complète (dict/liste), conjonction ou logique ensuite |
| `c3_verdict.decide` — retour d'abstention | au-delà de `synthetic` (lu en tête), l'évaluation n'est pas lue pour une abstention : aucune configuration n'est évaluée, la chaîne porte `continuite=-` ; en mode `chain`, `c3_continuity` a lu l'évaluation en entier avant |
| `c3_verdict._estimability_of` — `B` avant les séries | décision R2 (matrice `B`) : `B ≠ BOOTSTRAP_B` → R0 **avant tout parsing**, deux sorties code 2 |
| `c3_continuity.run_continuity` — candidat hors univers, paire sans coûts | refus / erreur d'entrée avant la période : deux sorties code 2, rien publié |
| `c3_continuity` clauses 1 à 5 ; `cc.liquidation_identities` ; `cc.warmup_sufficient` ; `cc.clause_d3` | lectures complètes, `checks` accumulés, `passed = all(dict)` |
| `c3_entry.run_assertions` | assertion échouée → suivantes `skipped` (ordre gelé I-A, validé R2) : sortie 2, jamais 0 ; `a01`–`a08` sans `break`, diagnostics D2 collectés sur tous les candidats |
| `c3_select.evaluate_candidate`, `filter_and_rank` | D1–D6 tous évalués avant `first_failed` ; conjonctions sur dicts calculés ; candidat non estimable : `delta_*` du benchmark nuls par construction, non lus |
| `c3_anchor.assert_frozen_values` | lève à la première divergence : sortie 2 dans tous les cas (une lecture complète listerait toutes les divergences — amélioration, pas un défaut de code) |
| `c3_benchmark.load_candles` (`> T` avant NaN), `match_lambda` (`break` sur la grille fine) | § H : R0 avant tout ; valeurs calculées, pas des champs |

### 13.3 Leçon

La discipline « tests adverses rouges avant, verts après » s'applique **aux tranches nouvelles**, pas
seulement aux correctifs : les 92 tests neufs du commit 9 avaient été écrits avec le code, jamais
constatés rouges contre un état antérieur, et cinq défauts y ont tenu. Ajoutée aux règles acquises
(§ 7) à côté du `pipefail`.

### 13.4 État après la revue

754 tests C3 (321 verdict, 127 anchor, 127 entry, 54 select, 50 common, 38 continuity, 28 benchmark,
9 chronology) ; suite complète hors déterminisme **2563 passés, 6 skipped (220 s)** ; `ruff` vert ; diff de contrôle § L.3
vide ; rejeu et livrables réels intacts ; `len(THRESHOLDS)` 23 ; mypy 65. Archive régénérée pour les
deux revues : `~/Desktop/krakenbot-src-v2.10.0-c2-replay-46-gb2c3485.zip`. **Pas de clôture avant
validation des deux revues** ; docs de clôture, `C3A-INTERIM`, brief C3b, amendements restent hors
session.

### 13.5 Revue Fin, seconde passe (Astra / Claude, 22/09, sur `b2c3485`) — deux correctifs, une définition

| # | Item | Commit | Rouges-avant | Ce qui a changé |
|---|---|---|---|---|
| F2-1 | [P1] États admissibles par clause — la table § 6.4 en liste close, des deux côtés ; le paramétré clause × état encodait l'implémentation | `313843e` | **16 / 32** (états hors liste acceptés côté verdict et producteur, constante absente) puis **23 / 58** après la passe interne (abstention publiée avec un état hors liste, portes/bornes non lues derrière une raison run, garde producteur incomplète, surcharge vide acceptée, agrégat par défaut) | `cc.CLAUSE_ADMISSIBLE_STATES` (colonne « États atteignables (C3a) » recopiée), `STAMP_CELL_ADMISSIBLE_STATES`, `COMPARATOR_ADMISSIBLE_STATES` ; `allowed=` par clause au verdict, garde côté producteur (clauses + deux blocs) ; `continuity_aggregate` strict ; `load_manifest` refuse `decision_timeframes: []`, clause 4 sans série → erreur ; `decide()` restructuré « tout lire, puis décider » (`_selection_view`, `_continuity_view`, `_continuity_actions`) ; tests : `TABLE_6_4` (20 lignes, attendu et appui par ligne), c4 NOT_VERIFIABLE/DECLARED → 2, agrégat VERIFIED inconstructible sur 108 combinaisons (texte puis code), producteur : 10 (bloc, état) avec appui, abstention lit la continuité, portes/bornes lues avant tout retour |
| F2-2 | [P2] Violation avant `UndefinedIssue` | `2b62530` | **2 / 10** (les deux reproductions : c3 FAILED + résumé vrai → 2 au lieu de 1 ; c3 FAILED + agrégat menteur VERIFIED → 2 au lieu de 1) | `run_verdict` : `UndefinedIssueError` après violation → consignée au diagnostic, code 1 ; sans violation → 2, rien publié (convention datée, cas cohérent seul) ; test du cas cohérent recadré |
| F2-3 | Définition de `chain.verified` | `2b62530` | verts avant (ils **fixent** la définition, et le disent) | docstrings (module, `run_verdict`) ; tests dans les deux sens : `verified: true` avec `inconclusif E_NO_BENCHMARK` (mode verdict et mode chain), `verified: false` sur toute violation (chaîne : empreinte, cohérence ; hors chaîne : estimabilité, résumé), refus → rien publié |

### 13.6 Passes adversariales internes (workflow, avant chaque commit)

Chaque correctif a été soumis, **avant commit**, à une passe interne : lentilles indépendantes en
lecture seule (dérivation depuis la table, réfutation en boîte noire par la CLI, côté producteur,
cohérence texte ↔ code ↔ tests), puis deux réfutateurs par constat (reproduction ; texte).

**Correctif 1** — 21 constats bruts, 5 confirmés, 1 réfuté, 15 non vérifiés (plafond), tous relus :

| Constat | Traitement |
|---|---|
| Abstention : `decide()` retournait avant de lire `continuity.json` — un état hors liste, un agrégat `VERIFIED` ou `clauses={}` étaient publiés en code 0 (P2, reproduit, réfuté « par le texte » au motif que la table § 6.4 porte sur le chemin évalué — la norme item 1 ne restreint pas le chemin) | **corrigé** : lecture stricte complète des cinq entrées avant tout chemin ; test des 11 mutations en abstention → 2 ; abstention contredite → 1 ; abstention cohérente → 0, `continuite=-` |
| Même motif sur les portes et les bornes : une raison run (abstention, `F_NOT_ESTIMABLE`, `D_WARMUP_ANCHOR`) dispensait de lire `metrics`/`bounds`/`B` | **corrigé** (défaut 5 appliqué à `decide()` lui-même) ; 6 cas testés → 2 |
| Garde producteur incomplète : `stamp_cell` et `comparator` non gardés côté `c3_continuity` alors que la docstring revendiquait « ici comme au verdict » (P2, deux lentilles) | **corrigé** ; test producteur étendu (monkeypatch des deux blocs) |
| `decision_timeframes: []` en surcharge par candidat accepté par `load_manifest` → clause 4 `VERIFIED` sur zéro série (P2) | **corrigé** dans `load_manifest` (surcharge vide refusée) et `clause_4` (aucune série → erreur) |
| `continuity_aggregate({})` / états inconnus → repli `VERIFIED` (P3) | **corrigé** : strict |
| Clés de clause inconnues (`c6`…) ignorées en silence (P3) | **corrigé** : `set(clauses) == {c1..c5}` |
| Paramétré producteur sans c5 ni c2 `VERIFIED` (P2/P3, trois lentilles) ; attendu pris dans `cc.CLAUSE_ADMISSIBLE_STATES` (P2) | **corrigé** : 10 lignes (bloc, état, appui) ; attendus recopiés de la table |
| Test des 108 combinaisons : une seule branche d'exception pour R0 et `UndefinedIssue` (P3) | **corrigé** : une branche par type, précédence R0 > issue non définie écrite |
| Couplage `LIQUIDATION_NORMALISED_OF_C3` ↔ liste close de c3 non asserté (P3) | **corrigé** : asserté dans le test de la liste close |
| Appui inexact « § B.4 … aucune estampille » (P3) ; appui (c3, NOT_VERIFIABLE) sans § 6.5 (réfuté, pris quand même) | **corrigé** : l'état `NOT_VERIFIABLE` de `stamp_cell` est une décision d'outillage (paquet C3b), § B.4 ne connaît que « même cellule » ou `E_STAMP_MISMATCH` |
| Docstring de `decide()` (« refus → 2 sans rien publier ») contredite par le refus après violation (P3) | **corrigé** dans la docstring restructurée |
| Rapport § 7.13 en avance sur le code (précédence `UndefinedIssue`) ; § 6/§ 13 citant un test supprimé (P2/P3) | **traité** par le correctif 2 et cette section |
| `test_agregat_prend_la_pire_clause` exerce `VERIFIED` sur des pseudo-clauses (P3) | **documenté** : test de précédence hors périmètre, complété par le cas strict |

**Correctif 2** — 18 constats bruts (3 lentilles : précédence, `verified`, attendus), 3 confirmés, 2 réfutés, 12 non vérifiés, tous relus :

| Constat | Traitement |
|---|---|
| `verify_chain` consignait les contradictions dans une liste locale : un `require_upstream_ok` levant ensuite sur un autre amont cohérent en échec faisait sortir 2, rien d'écrit — la violation perdue (P2, deux lentilles, reproduit) | **corrigé** : accumulateurs du demandeur ; testé (contradiction + refus ultérieur → 1, diagnostic avec les deux, `verified: false`) |
| Règle « c3 FAILED → code 2, rien publié » écrite deux fois sans la réserve « cas cohérent » (module, `cc.UndefinedIssueError`) (P3/P2) | **corrigé** : une règle, la précédence ; les deux textes y renvoient |
| Le diagnostic publié embarquait « code 2, rien publié » (P3, réfuté comme conforme, pris quand même) | **corrigé** : motif et conduite scindés, le diagnostic consigne le motif |
| Preuve absente **après** une violation → 2 sans diagnostic, violation perdue (P2, réfuté deux fois : conforme au chantier 0, norme muette) | **ratifié** convention d'outillage datée du 22/09 (§ 7.14, § 13.7) : rien publié, la violation dite sur stderr, testé |
| Le rapport ne portait pas la définition de `chain.verified` ; `checks[13]` au lieu de 17 (P2/P3) | **corrigé** (§ 6, § 13.7) |
| Docstring « un refus ne publie rien » : le refus consigné après violation publie un diagnostic (P3) | **corrigé** : docstrings ; testé `verified: false` sur ce diagnostic |
| Tests de la définition sans docstring ni appui ; familles « protocole » et « non-fini » non assertées sur `verified` (P3) | **corrigé** : docstrings avec appui (item 3, chantier 0), deux familles ajoutées ; les tests verts-avant disent qu'ils fixent la définition |
| Appuis « § I.1 l.15 … elle prime » (la précédence est l'item 2, pas le protocole) et « plan § 6.1 » non localisable dans le dépôt (P3) | **corrigé** : appuis réattribués (revue Fin 2, item 2 ; plan révisé § 6.1, hors dépôt) |
| Triplicata du cas cohérent c3 FAILED (P3) | **gardé** : `test_clause_3…` (CLI + message), ligne `TABLE_6_4`, test de la borne de l'item 2 — chacun dit ce qu'il fixe |

### 13.7 `chain.verified` — définition fixée

`chain.verified` = **intégrité mécanique de la chaîne** : codes de succès enregistrés des amonts,
cohérence interne de chaque enveloppe amont (`ok ⟺ exit 0`, `invalide ⟺ exit 1`, refus ⟺ exit 2 pour
entry), empreintes concordantes. Il ne porte pas la qualité économique de l'issue (elle se lit dans
`verdict` / `raison`). Donc `verified: true` avec un `inconclusif E_NO_BENCHMARK` est cohérent ;
`verified: false` sur toute violation, de chaîne ou non ; un refus ne publie rien, donc aucun
`verified`. Écrite dans la docstring du module `c3_verdict.py` et de `run_verdict`, assertée dans les
deux sens.

**Précédence fixée (item 2)** : contradiction déclaré / dérivé constatée → diagnostic code 1
(`invalide: true`, violations listées, l'issue non définie consignée), même avec c3 en échec ; le refus
2 `UndefinedIssueError` reste réservé au cas cohérent — celui que la convention datée du 21/09 couvre.

**Règle générale : l'ordre de constat.** Après une violation, la violation prime (diagnostic, code
1), qu'un refus ou une issue non définie survienne ensuite — **sauf lecture inachevable**.
**Convention d'outillage datée du 22/09 (ratifiée à la validation Fin)** : preuve obligatoire absente,
nulle, mal typée ou hors liste close constatée **après** une violation → code 2, rien publié, violations
dites sur stderr. Fondement : un diagnostic se bâtit sur une lecture complète. La justification
antérieure (« précédent du chantier 0 ») est corrigée dans la docstring de `decide()` : ce précédent
couvre le refus de contrat évalué **avant toute lecture** (`B` hors contrat → 2), non l'ordre de
constat. La clarification normative de ce cas rejoint le paquet C3b (§ 8).

**Contrat de couche** (docstring de `decide()`) : la cohérence d'enveloppe des amonts
(`ok`/`exit_code`/`invalide`, `refusal` pour entry) est le contrat de l'appelant, appliquée à la
frontière fichier par `artifact_coherence` avant tout appel — `decide()` ne la revérifie pas ; aucun
code futur ne l'appelle sur du contenu de fichier non gardé.

### 13.8 Leçons (les deux figurent aux règles acquises)

1. La discipline « rouges-avant » s'applique aux tranches nouvelles, pas seulement aux correctifs
   (première passe).
2. **Rouges-avant prouve qu'un test mord ; il ne prouve pas que son attendu est juste.** L'issue
   attendue d'un test adverse se dérive de la table ou du texte, appui cité ligne à ligne — un
   paramétré qui encode le comportement de l'implémentation est un verrou posé sur le défaut (le
   paramétré clause × état de la première passe acceptait c4 `NOT_VERIFIABLE` → « validé »). Depuis :
   `TABLE_6_4`, `OUT_OF_LIST_PRODUCER`, `ADMISSIBLE_STATES_6_4`, `NORMALISED_6_4` sont recopiés du
   texte et **épinglés** aux constantes du code par des tests d'égalité, jamais l'inverse.


## 14. Porte pré-merge § L.5 — passée le 2026-09-22 au `6f7ed8e`

**Option retenue : 1** (24 tests de déterminisme full-range sur le serveur, au SHA livré, recette C2). L'option 2
n'est pas disponible : `git diff --stat f585e8b 6f7ed8e -- <chemins § L.3>` = `pyproject.toml` seul (+7/−1, bloc
`extend-exclude` de Ruff), constaté en local à l'étape 1 et rejoué sur le serveur (`checks_6f7ed8e.log`).

**Vérifications préalables (étape 1, local, lecture seule).** Branche `feat/c3a-protocole`, HEAD
`6f7ed8e99191a795a42ca3a8ce253407d963e546`, `sha256sum docs/protocole_c3.md` =
`9b62915069e59e9b0f35120c60a77f48a72b278aa9102b3096dfcb8dc25e23c2` (gel `d931293`, intouché). Le critère « diff
vide `2b62530..6f7ed8e` sur `src scripts tests config pyproject.toml poetry.lock` » a **échoué** au premier passage :
`acaeaf6` touche `scripts/audit/c3_verdict.py` (+20/−6). STOP (22/09, 20:42Z), rapport, décision humaine ci-dessous ;
critère d'étape 1 devenu « diff vide hors ce fichier + preuve AST/bytecode archivée », satisfait.

**Rejeu serveur (étape 2).** Checkout isolé `~/c3a-determinism/repo` (clone GitHub + `git bundle` local des 59
commits, `origin/feat/c3a-protocole` étant resté à `5e056e0` ; aucune écriture sur `origin`), HEAD détaché sur
`6f7ed8e` (`git describe` = `v2.10.0-c2-replay-59-g6f7ed8e`), venv propre `.venv` (`poetry install`, rc 0, Python
3.12.3 / pytest 9.0.2 / ruff 0.14.13 / mypy 1.19.1), `.env` copié de l'arbre du service, base locale, `nice -n 5`,
une invocation pytest par combo, arrêt prévu au premier échec (il n'a pas servi), pilotes refusant tout autre SHA.
Jamais l'arbre du service, jamais `systemctl`, jamais le `.env` serveur.

| Passage | Fenêtre (UTC, 2026-09-22) | Résultat |
|---|---|---|
| 24 combos full-range (`run24.sh` → `combo0..23.{xml,log}`, `run24.log`) | 20:54:39Z → 22:04:23Z (69 min 44 s) | **tests=24 failures=0 errors=0 skipped=0**, durées 38 s → 406 s, profil identique à C2 |
| Suite hors déterminisme, première passe (`suite_run1_async_cleanup_incident.xml`) | 22:04:29Z → 22:11:26Z | **2 failed / 2 612 passed / 6 skipped / 1 error** — incident de nettoyage asynchrone, classe C2, aucun `AssertionError` (§ 14.2) |
| Suite hors déterminisme, relance unique (`suite_rerun.sh` → `suite.xml`, `suite_rerun.log`) | 22:18:49Z → 22:25:40Z | **4 failed / 2 610 passed / 6 skipped / 1 error — non verte, même classe, reproductible (§ 14.2)** ; `test_main.py` seul 1 failed / 15 passed / 2 errors, `test_b4_campaign_configs.py` seul 30 passed |
| 6 tests de déterminisme courts (`short.xml`) | 22:11:28Z (24,5 s) | **tests=6 failures=0 errors=0 skipped=0** |
| Gold hashes (`test_grid_atr_v4_backward_compat.py`) | — | 2 passés |
| 806 tests C3 (`tests/test_scripts/test_c3_*.py`, inclus dans la suite) | — | **806 passés** (226,8 s) |
| `ruff check .` | — | propre |
| `ruff format --check` (`.` et fichiers suivis `--force-exclude`) | — | 12 fichiers à reformater / 262 formatés, aucun de C3a (§ 14.3) |
| `mypy src/` / `--ignore-missing-imports` | — | **65** / 64 (= baseline, § 5) |
| Preuve AST/bytecode `c3_verdict.py` `2b62530` vs `6f7ed8e` (`ast_bytecode_check.py`) | — | AST hors docstrings **identique**, bytecode de module **identique**, rc 0 |

Innocuité (22:16:34Z) : `krakenbot-collector` actif, `NRestarts=0` (depuis le 13/09 19:54Z), trader inactif ; aucun
zombie, aucun processus résiduel ; bougies 1 m Bybit sur la fenêtre 20:54:39Z → 22:16:34Z : 82 lignes / 0 trou par
paire (BTC, ETH, SOL), plus grand écart 1 min.

**Archive** : `results/c3a_determinism_server/run_6f7ed8e/` — `combo0..23.{xml,log}`, `run24.log`,
`suite_run1_async_cleanup_incident.xml`, `suite.xml`, `suite_rerun.log`, `short.xml`, `checks_6f7ed8e.log`, **les
pilotes versionnés** `run24.sh`, `checks.sh`, `suite_rerun.sh`, `ast_bytecode_check.py` (à côté de leurs journaux — C2
ne l'avait pas fait, trou de reproductibilité relevé par Bruno), `README.md` (SHA, fenêtres, commandes exactes,
agrégats, incident, empreinte du lot). Exception `.gitignore` `!results/c3a_determinism_server/**/*.log`, même
convention que C2. Ligne ajoutée à `results/INDEX.md`.

### 14.1 Décision humaine (Bruno, reçue le 2026-09-22, datée 2026-09-23 dans la consigne) — condition 2 du § 10

> Re-passe Astra (condition 2 du § 10). Les reproductions adverses des revues Fin ont été relancées
> sur l'archive `48-g2b62530` (revue Claude, 22/09) : sept reproductions, toutes mortes. `2b62530`
> est le dernier commit de code de la branche ; `acaeaf6` → `6f7ed8e` : diff vide sur `src/`, `tests/`, `config/`,
> `pyproject.toml`, `poetry.lock` ; sur `scripts/`, limité aux docstrings et commentaires de
> `scripts/audit/c3_verdict.py` (+20/−6, commit `acaeaf6`), AST hors docstrings et bytecode de module identiques à
> `2b62530` — commande et sortie archivées dans `checks_6f7ed8e.log`. Les tests adverses qui encodent les
> reproductions Fin font partie des 806 tests C3 exécutés à l'étape 2 sur `6f7ed8e`. La condition « relancées sur
> le SHA final » est satisfaite pour le code. Ce qui n'a pas eu lieu : la contre-vérification externe par Astra,
> quota épuisé — consignée comme non faite, sans substitut. Décision : merger sans l'attendre ; si le quota revient,
> la re-passe se fait sur `dev` post-merge et s'archive au même endroit.

Historique de la ligne corrigée : la consigne initiale disait « diff vide sur `src/`, `scripts/`, … vérifié à l'étape
1 » ; l'étape 1 l'a réfutée (STOP du 22/09, 20:42Z ; le § 12 de ce rapport disait déjà « docstrings de
`c3_verdict.py` »), Bruno a réécrit la ligne (ci-dessus) et tranché : pas de relance séparée des sept reproductions,
le bytecode identique et la suite complète sur le SHA final couvrent le cas — une preuve d'équivalence exécutable
est plus forte qu'un diff vide.

### 14.2 Incident de la première passe de la suite — conservé, relancé une fois, comme en C2

Trois non-verts, tous de la classe consignée en C2 (`run1_835ffe2/suite_run1_teardown_incident.xml`) : objets
asynchrones (`aiohttp.ClientSession`, résolveur `pycares`/`aiodns`) survivant au test qui les a créés, ramassés
pendant un autre test et remontés par le hook `unraisableexception` de pytest. `TestKrakenBotStop::
test_stop_handles_component_errors` en erreur **au setup** (corps non exécuté) — même test, même phase, même signal
qu'en C2 ; `TestKrakenBotStart::test_start_subscribes_1m_when_router_crash_protector_is_configured` — callback
`_addrinfo_cb` sur boucle fermée, même test qu'en C2 ; `test_b4_campaign_configs.py::TestEngineMinOrder::
test_order_below_floor_is_skipped_and_default_keeps_it` — `ExceptionGroup` de cinq `ClientSession` non fermées venues
de `test_main.py`, corps allé au bout (journal capturé), victime de passage. Aucun `AssertionError` (vérifié dans le
XML). `src/` est identique à `f585e8b` (§ L.3), où la même suite rendait 1 514 passés / 0 erreur. Traitement C2 :
XML conservé sous un nom qui l'annonce, **relance unique de la suite seule** (`suite_rerun.sh`, jamais les 24 combos),
fichiers victimes rejoués seuls. **La relance n'a pas rendu vert, elle a rendu pire** (4 failed / 2 610 passed / 1 error, dont `test_c2_replay_fidelity.py` victime de passage) et `tests/test_main.py` seul échoue (1 failed / 15 passed / 2 errors) — reproductible, là où C2 concluait « non reproductible ». Aucune troisième relance. Tableau des cinq non-verts et sortie complète : `README.md` du lot, `suite_rerun.log`.

**Cause identifiée (lecture du code, aucune modification).** `tests/conftest.py::mock_settings` (l. 93) construit `Settings(environment="testing", kraken=…, database=…, risk=…, trading=…)` sans fixer `telegram` ; `TelegramSettings` (`env_prefix="TELEGRAM_"`) se remplit donc depuis l'environnement. Sur le serveur, le `.env` copié de l'arbre du service (recette C2) et l'export du `~/.bashrc` (l. 119, `set -a && source .env`) fournissent `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` **réels** ; `KrakenBot._init_telegram_notifier()` (`main.py` l. 443) construit un vrai `TelegramNotifier` — jamais patché dans `tests/test_main.py` — et `start()` lance `send_bot_started` en tâche détachée (`asyncio.create_task`, `main.py` l. 577) : une **vraie requête HTTPS vers `api.telegram.org`** (résolution `aiodns`/`pycares`, `aiohttp.ClientSession`) part des tests unitaires et survit à la fermeture de la boucle du test — callback `_addrinfo_cb` sur boucle fermée, session jamais fermée, ramassée pendant un test voisin. En local, le `.env` n'a **aucune** variable `TELEGRAM_` : notifier désactivé, `tests/test_main.py` 18 passés (×3), suite locale **2 615 passés / 6 skippés**, 196 s (22/09 22:27:46Z → 22:31:04Z, rc 0, même commande, `-p no:cacheprovider`). C2 avait le même défaut latent (son incident, « non reproductible » après trois relances vertes) ; ce soir la course est perdue à chaque passage. Ni `src/`, ni `tests/test_main.py`, ni `tests/conftest.py` n'ont changé depuis `f585e8b` ; les deux venvs (C2, C3a) sont identiques (75 paquets). **Ce n'est pas une régression C3a**, c'est un défaut d'hermétisme de la suite révélé par la recette (un `.env` de service avec des identifiants réels). Conséquence possible, à vérifier par Bruno : des messages Telegram « bot started (paper) » reçus pendant chaque suite serveur (19/09 en C2 ; 22/09 vers 22:05Z, 22:19Z et 22:25Z). Correctif hors périmètre de ce chantier (aucune ligne de code) : `telegram=TelegramSettings(enabled=False)` dans la fixture, ou patcher `TelegramNotifier` dans `tests/test_main.py` — item de dette de suite.

### 14.3 Découvertes annexes, signalées, non traitées

- `ruff format --check .` rend **12 fichiers** à reformater au `6f7ed8e` contre 2 au `f585e8b` (dette 10). Les 10
  nouveaux viennent du rejeu grid (`aa17ed0`, `5a443da`, mergés dans `dev` le 20/09), préexistent sur `dev` à
  l'identique (diff vide depuis la base de branche `57051cc`) ; les 15 fichiers C3a (`c3_*.py`, `test_c3_*.py`) sont
  formatés. Dette 10 élargie de 2 à 12, hors C3a.
- `origin/feat/c3a-protocole` était resté à `5e056e0` (11 commits documentaires derrière le tip) ; le merge de
  l'étape 5 les pousse avec `dev`.
- La surveillance par l'outil `Monitor` de la session ne pouvait pas ouvrir de SSH (environnement sans agent) ;
  remplacée par des sondes `run_in_background` de 9,5 min, sans effet sur le rejeu.
