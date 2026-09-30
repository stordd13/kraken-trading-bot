# Journal des essais de recherche (append-only)

> **Règle.** Toute campagne ou run exploratoire de backtest est inscrit ici **avant son lancement**
> (décision 17 du `ROADMAP.md`). Les modifications guidées par des résultats (nouveau paramétrage, nouveau
> filtre, nouvelle fenêtre, nouveau critère) sont de **nouveaux essais**, tracés à leur tour. **Rien n'est
> supprimé ni réécrit** : une entrée erronée est corrigée par une entrée suivante qui la cite. Le journal
> sert au contrôle des essais multiples (audit red-team B4, phase 2 priorité 5) : sans lui, aucun taux de
> faux positifs n'est estimable.
>
> Granularité : la campagne (le détail par config vit dans les JSON référencés). Le rejeu diagnostic grid
> (décision 15) est hors quota des 2 familles/cycle mais s'inscrit ici comme tout run. Tant que les runs
> R&D sont gelés (jusqu'au merge de C1-C2), seules les entrées rétroactives et les chantiers de réparation
> de l'instrument figurent ici.

## Format d'une entrée

`date | phase/campagne | famille + périmètre (configs × paires) | données + période | version code
(tag/commit) + version métriques | modèle de fees | verdict | décision consécutive | source (rapport)`

Versions métriques : **v1** = moteurs pré-C1 (défauts D1-D6 de l'audit red-team du 16/09, invalidés) ;
**v2** = `krakenbot.backtest_metrics`, `metrics_version` 2 (C1, tag `v2.9.0-c1-metrics`).

## Entrées

### Reconstruction rétroactive (16/09/2026 — dates depuis les rapports sources)

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-04-19 | P6 — 24 combos | 8 stratégies × 3 paires (BTC/ETH/SOL) = 24 combos, cross-validate 70/30 | Binance (open-stampées), 2023-04 → 2026-04 | `v2.0.0-p6-validated` ; métriques v1 (invalidées D1-D6) | binance 0.075 % flat | 0/24 aux 5 critères stricts | grid search P7 | `results/P6_backtest_report_v2.md`, `results/P6_phase_d_results.json` |
| 2 | 2026-05-30 | P7 phase 1 — grid search cross-validé | 212 configs (4 stratégies : grid ATR v4, SuperTrend, DCA, Donchian) | Binance (open-stampées), 2023-04 → 2026-04 | commit `f04d1fd` (branche mergée le 7 sept, pas de tag) ; métriques v1 | binance 0.075 % flat | classements non transposables aux fees Bybit | re-run B4 | `results/P7_phase1_cross_validate.json` |
| 3 | 2026-09-15 | B4 — P6 re-run | 24 combos (8 × 3) | Binance **end-stampées** (B4.1), 2023-04 → 2026-04 | `v2.8.0-b4-3-campaign` (P6 @ `874fb62`) ; métriques v1 | bybit maker 0.10 % / taker 0.25 % + coûts GATE B par paire (BTC 2/2, ETH 3/2, SOL 11/2 bps), plancher 5 USDC | 0 survivant (3 runs grid × SOL flaggés, dette 14) | GO P7 (checkpoint validé) | `results/B4_P6_backtest_report.md`, `results/B4_P6_checkpoint.md` |
| 4 | 2026-09-15 | B4 — P7 phases 1-2 | 212 configs (SuperTrend 60, Grid 96, DCA 48, Donchian 8) sur 7 combos + 35 configs × 8 fenêtres walk-forward (280) | idem 3 | `v2.8.0-b4-3-campaign` (P7 @ `eb13800`, rapport @ `a59226f`) ; métriques v1 | idem 3 | 0/35, sélection vide ; 48/48 grid × SOL flaggées (dette 14) | roadmap B5 → P10 suspendue ; audit red-team du 16/09 → instrument invalidé (addendum B4) → C1 → C2 → rejeu grid → C3 | `results/B4_bybit_backtest_report.md`, `results/B4_P7_optimization_report.md`, `results/B4_P7_checkpoint.md` |
| 5 | 2026-09-15 | B4 — benchmarks | B&H + DCA fixe 15 USDC/semaine × 3 paires | idem 3 | `v2.8.0-b4-3-campaign` ; métriques v1 (DCA contaminé D6) | idem 3 | B&H Sharpe (quotidien) 0.84 / 0.38 / 0.30 ; DCA Sharpe 2.1-2.4 non comparable (D6) | critère P7 n° 7 ; recalcul v2 en C1 (`results/C1_benchmarks_v2.json`) | `results/B4_benchmarks.json`, `results/B4_bybit_backtest_report.md` § 5 |
| 6 | ≤ 2026-03 | Campagnes kraken-era antérieures | — | — | — | — | — | — | non reconstruites au détail, voir `docs/archive/` (rapports : `results/archive/`) |

### Chantier C2 — fidélité du replay (inscrit le 2026-09-17, avant lancement)

Runs de **validation de l'instrument** (pas des essais R&D) : aucun verdict de sélection n'en découle, aucun
langage de validation économique dans le rapport (`results/C2_replay_report.md`). Version métriques v2 partout.

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 7 | 2026-09-17 | C2 étape 0 — références « avant » (5 captures `scripts/audit/c1_equity_probe.py capture --engine-root ~/wt-c1-ref`) | signal A `grok_supertrend_4h` BTC ; grid quick `grok_grid_atr_adaptive_v4` BTC (binance + bybit) ; grid A `grok_grid_atr_adaptive_v4` BTC ; DCA réf. `grok_adaptive_dca_weekly` BTC — défauts de classe (dette 13) | Binance end-stampées ; signal A et grid A 2023-04-01 → 2026-04-01 ; grid quick 2025-03-01 → 2025-03-15 ; DCA 2022-01-01 → 2022-09-28 ; `--interval 5 --capital 1000` (DCA : `--min-order-usdc 5`) | tag `v2.9.0-c1-metrics` (worktree) ; métriques v2 | bybit (grid quick aussi binance) | captures « avant » canoniques, sha256 consignés ; descriptif seulement | côté « avant » des preuves 5 et 6 de C2 | `results/C2_replay_report.md`, `results/c2_ab/` |
| 8 | 2026-09-17 | C2 — références « après » (mêmes 5 commandes sur `feat/c2-replay`) + invariant strict | idem 7 | idem 7 | branche `feat/c2-replay` (commit consigné au rapport) ; métriques v2 ; `replay_version` 2 | idem 7 | signal A **bit-identique** en mode strict (sinon STOP) ; grid quick / grid A / DCA : écarts attribués à R1-R4, sans verdict | preuves 5 et 6 ; re-baseline des gold hashes soumis à review | `results/C2_replay_report.md` |
| 9 | 2026-09-17 | C2 — rejeu P6 des 3 grids (`run_p6_backtests.py --limit 3`, train/test/all) | `grok_grid_atr_adaptive_v4` × BTC/ETH/SOL (3 combos, défauts de classe) | Binance end-stampées, 2023-04-01 → 2026-04-01, split 70/30 | branche `feat/c2-replay` ; métriques v2 ; `replay_version` 2 | bybit + coûts GATE B (`config/pair_costs_b4.json`), plancher 5 USDC | SOL : aucun flag `b4_flags` (divergence ≤ 1e-12, cash = lot-basis ≤ 1e-9), compteurs `unmatched_*` = 0, `warmup.sufficient=False` attendu par segment ; descriptif seulement | preuve 4 (réel) de C2 ; artefact `results/c2_replay/P6_grid_rerun.json` | `results/C2_replay_report.md` |
| 10 | 2026-09-17 | C2 — rejeu P6 des 3 grids **relancé** après le commit 12 (correctifs diagnostic de la revue du gate 2 : staleness sans `-1`, preuve 1 sur les bornes chargées) — même recette que l'entrée 9, nouvel artefact au même chemin (sha256 au rapport) | idem 9 | idem 9 | branche `feat/c2-replay` (commit 12) ; métriques v2 ; `replay_version` 2 | idem 9 | idem 9, plus : blocs `warmup` aux valeurs exactes du contrat (SOL train / all : 1 d périmé de 183 bougies, 1 w de 25) ; simulation et gold hashes inchangés (changement purement diagnostic) | commit 12 (artefact), puis recalage des gold hashes (commit 13) | `results/C2_replay_report.md` § 3.4 |

Écart consigné, mesuré : le run 10 a démarré à **10:52:56 UTC** et cette ligne a été écrite **après** son lancement, le
run étant déjà en cours (il s'est terminé à 11:08:54 UTC, 16 min). C'est une relance d'un run déjà inscrit en 9, avec un
moteur dont seule la sortie diagnostique change — la règle « inscrit avant lancement » vaut néanmoins aussi pour les
relances : consigné, pas justifié.

### Issues des entrées 7-10 (C2, inscrites après les runs, sans verdict économique)

| # | Issue mesurée | Source |
|---|---|---|
| 7 | 5 captures « avant » posées (sha256 au rapport § 0), `source_fingerprints` identiques au tag | `results/C2_replay_report.md` § 0 |
| 8 | signal A **bit-identique** en mode strict (`STRICT IDENTITY OK`, exit 0) ; grid quick ×2, grid A, DCA : écarts attribués R1 / R2 (grid : 4 033 ticks 5 m → 85 décisions 4 h, ATR 4 h réel → espacement 5 %, recalc 8 h ; DCA : EMA 200 prête à `start`, branche oversold active, 39 lundis / 39 signaux / 36 achats / 3 `limit_expired` mesurés) ; re-baseline des gold hashes approuvée au gate 2 | § 3, § 7 |
| 9 | SOL réconcilié sur les 3 segments (divergence ≤ 1.1e-27, `net_pnl` = lot-basis, `unmatched_*` = 0), aucun rejet sur les 9 segments ; `warmup.sufficient=False` sur SOL train / all (4 h vide, 1 d / 1 w périmés) et BTC / ETH train / all (trou de 164 j dans les fenêtres 1 d / 1 w) — observé, jamais comblé | § 3.4 |
| 10 | Comptabilité des 9 segments **inchangée au bit près** (trades, `net_pnl`, `ending_balance`, fees, `liquidation`, `rejections` identiques à l'artefact du commit 9) ; **4 valeurs de staleness** bougent — SOL train et all, 1 d 182 → 183 et 1 w 24 → 25 — les 23 autres blocs identiques, `sufficient` inchangé ; gold hashes vérifiés inchangés par le correctif (binance `5fb528df…`, bybit `e9f0d350…`) ; nouvel artefact sha256 16 `5e3c6631730ee6cd` | § 3.4 |

### Porte pré-merge C2 — rejeu de déterminisme sur serveur (2026-09-19)

Hors quota d'essais (vérification d'instrument, aucun verdict de sélection). Les 24 tests
`test_determinism_parallel_vs_serial_full` (24 combos = 8 stratégies × 3 paires, 2023-04-01 → 2026-04-01, chaque combo
rejoué en sériel puis dans un pool de 2 workers, comparaison de hash) ont été rejoués **sur le serveur**, en checkout
isolé au SHA `835ffe21f031834a0a168daf409c4d6d09bc08d8`, base en accès local. Résultat : **24 passés, 0 échec, 0 skip**
(agrégat JUnit `results/c2_replay/determinism_server/`). Motif du déplacement : via le tunnel SSH, les mêmes tests
échouaient sur des erreurs de connexion sans jamais produire d'écart de hash. Collector vérifié après le lot (actif, 0
redémarrage, aucun zombie) et continuité 1 m intacte sur la fenêtre (73 lignes par paire, 0 trou).

**Second rejeu, au SHA livré** (2026-09-19, 12:11:42Z → 13:24:43Z) : l'archivage des preuves du premier lot déplaçant le
SHA, les 24 tests ont été **intégralement rejoués** au SHA `f585e8bb676ad194753305da86db953d425de97c` — de nouveau
**24 passés, 0 échec, 0 skip** — avec, au même passage et au même SHA, la suite hors déterminisme (**1 514 passés,
6 skippés, 0 erreur**), les **6** tests de déterminisme de la fenêtre courte, les 2 gold hashes, `ruff check` propre et
`mypy src/` = 65. Soit **30/30** au SHA livré. Innocuité revérifiée : collector actif, `NRestarts=0`, aucun zombie,
continuité 1 m intacte (72 lignes par paire, 0 trou). Artefacts : `results/c2_replay/determinism_server/run2_f585e8b/`.
Une vérification d'invariance (`git diff --stat f585e8b..HEAD -- src scripts tests config pyproject.toml poetry.lock`,
sortie vide) établit que le commit d'archivage ne touche aucun code, donc qu'aucun rejeu supplémentaire n'est requis.

### Rejeu diagnostic grid — 96 configs BTC/SOL (inscrit le 2026-09-20, avant lancement)

Diagnostic **pré-spécifié** (décision 15 du `ROADMAP.md`) : hors quota des deux familles par cycle, mais inscrit ici
comme tout run. Les métriques, les seuils, la règle d'agrégation, la méthode d'incertitude et la définition
opératoire des trois verdicts sont gelés **avant** le lancement dans `docs/rejeu_grid_prespec.md` (commit `4ecd985`,
amendé en `aa17ed0` sur deux corrections d'implémentation sans effet sur un seuil ni sur une règle de décision) et
ne bougent plus. Le rejeu **ne peut rien sélectionner** : toute sélection relève de C3. Le verdict « inconclusif »
est pleinement admissible, et un négatif propre est un résultat attendu et déclaré d'avance (§ K.1 de la pré-spec).

Trois mesures de **pré-campagne** ont été produites et committées avant le lancement, sur le serveur en checkout
isolé, base en accès local : couverture réelle des données (`data_coverage.json`), benchmark d'exposition
reconstruit aux bornes moteur (`benchmark.json`), résolution pré-enregistrée et vérification d'équivalence du MaxDD
vectorisé (`calibration.json`). Leurs deux conséquences étaient prévues par la pré-spec et sont confirmées par la
mesure : **BTC/USDC admissible** (1 096 jours couverts sur 1 096, trou 0) et **SOL/USDC inadmissible**
(825 jours, trou de 271 jours en fenêtre, première bougie 2023-12-28) — et, par une seconde route indépendante, le
benchmark SOL n'est **pas constructible** (première bougie quotidienne 272 jours après l'ancre). SOL est donc
**descriptif** : il ne peut produire ni « candidat » ni « dépriorisation », et reste dans le diagnostic technique.

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 11 | 2026-09-20 | Rejeu diagnostic grid — P7 **phase 1 uniquement** (ni phase 2, ni `--report`, ni `--selection`) | `grok_grid_atr_adaptive_v4` × **BTC/USDC et SOL/USDC**, `GRID_ATR_GRID` inchangée (`min_spacing_pct` 4 × `atr_multiplier` 4 × `bear_protection_mode` 3) = **96 configs**, défauts de classe (dette 13 non fixée : `max_spacing_pct` 0.05 non balayé, lots 25 USDC, `bias_1d` 0.2, `max_allocation_pct` non appliqué) | Binance **end-stampées**, 2023-04-01 → 2026-04-01 ; segment `all` **seul décisionnel**, `train`/`test` descriptifs et jamais concaténés (288 simulations ≠ 288 observations) | branche `feat/rejeu-grid-diag` @ `aa17ed0`, depuis `dev` @ tag `v2.10.0-c2-replay` (`9897803`) ; métriques **v2** ; `replay_version` **2** | bybit maker 0.10 % / taker 0.25 % + coûts GATE B par paire (`config/pair_costs_b4.json` : BTC 2/2 bps, SOL 11/2 bps), `--min-order-usdc 5` (inerte sur le grid, valeur de provenance) | **candidat / dépriorisation / inconclusif**, par la règle gelée : couverture ≥ **25 cycles achevés** (`total_trades − liquidation.positions`) ; plancher économique **`total_return_pct(all) ≥ 6 %`** (convention de poursuite de recherche, pas un seuil de déploiement) ; **Δ CAGR > 0** contre un blend **statique** cash + λ·B&H apparié par recherche sur le drawdown quotidien **et** sur la volatilité ; **borne simultanée `LB_j > 0` sur les six combinaisons** (L ∈ {10, 21, 42} × appariement), λ ré-estimé dans chaque réplication ; Sharpe et `net_pnl/total_fees` **descriptifs, jamais décisionnels** ; SOL descriptif | selon le verdict : travail de **mécanisme** (§ 5 / § 6 des contraintes) puis C3 — ou clôture de la famille grid, toute reprise exigeant un mécanisme nouveau (clause de clôture § K.2) | `results/rejeu_grid_report.md`, `docs/rejeu_grid_prespec.md`, artefacts `results/rejeu_grid_20260919/` |

### Issue de l'entrée 11 (rejeu diagnostic grid, inscrite après le run)

Campagne lancée le 2026-09-20 à 10:52:58 UTC au SHA `0120ce8`, terminée à 11:50:20 UTC : **96 jobs, 96 réussis,
0 échec, 57,4 min**, 3 workers, checkout isolé serveur, base locale — dans la limite murale externe de 6 h déclarée
avant le run, sans aucune reprise. Collector intact (actif, `NRestarts=0`, 59 bougies 1 m par paire sur la fenêtre,
**0 trou**, écart maximal 1,00 min).

| # | Issue mesurée | Source |
|---|---|---|
| 11 | **Verdict `inconclusif` (`F_CANNOT_SEPARATE`)**, émis par `scripts/audit/rejeu_verdict.py` et cité tel quel dans le rapport. BTC/USDC vote, SOL/USDC est descriptif par trois routes indépendantes (couverture 825 j, benchmark non constructible, warmup W2) | `results/rejeu_grid_report.md`, `results/rejeu_grid_20260919/verdict.json` |
| 11 | Validité de campagne : **15/15 assertions**, `b4_flags` muet après les assertions de présence, zéro rejet sur les sept causes, diff de contrôle vide | `validation_campaign.json` |
| 11 | Couverture : **aucune config tronquée** — 77 cycles au minimum sur BTC (médiane 144,5), 168 sur SOL, contre un seuil de 25. Le choix 25 plutôt que 30 n'a rien tranché | `effect.json` |
| 11 | Gates ponctuels BTC : G1 48/48, G2 18/48, G4 31/48 → **16/48** passent les trois. G3 descriptif : 8/48 le franchissent, **aucune n'est parmi les 16** — l'ajouter comme gate obligatoire, toutes autres règles inchangées, aurait laissé zéro config et conduit à `dépriorisation` | `effect.json` |
| 11 | Borne d'incertitude : **aucune des 48 configs ne tient `LB_j > 0`** sur les six combinaisons ; les `q_FWE` ≈ 5,9-6,25 pp/an sont les **seuils critiques observés de cette procédure**, pas une limite générale de détection. Les erreurs-types sont élevées relativement aux effets observés (meilleur Δ̂ +1,92 contre un `se` mono-config de 2,56-2,79) ; la procédure pré-spécifiée ne sépare aucun effet de zéro ; la contribution propre de la correction de multiplicité **n'a pas été isolée** | `effect.json` |
| 11 | Clamp mesuré : plafond de 5 % saturé **sur SOL seulement** (82 % puis 95 % des clôtures 4 h à m = 2,5 et 3,0) et **pas sur BTC** (espacement intérieur 78-91 % du temps). D'où 23 classes d'indiscernabilité sur SOL contre **48/48 distinctes sur BTC** | `clamp.json`, `signatures.json` |
| 11 | Lecture rétroactive B4 : 48 → 45 classes (BTC) et 48 → 48 (SOL), **en accord** avec la référence pré-enregistrée avant le run | `signatures.json` |
| 11 | Attendu déclaré au § K.1 **partiellement falsifié** : 18 configs BTC franchissent le plancher de 6 % (jusqu'à 10,32 %), la référence post-C2 à multiplicateur 4,0 — hors balayage — n'était pas représentative | `effect.json`, `docs/rejeu_grid_prespec.md` § K.1 |

Chaîne de verdict, citée telle quelle :

```
REJEU_GRID_20260919 | famille=inconclusif | raison=F_CANNOT_SEPARATE | BTC/USDC=inconclusif | SOL/USDC=descriptif | representant=- | prespec=20079aff60a55152 | campagne=08d981e493402f37
```

Conséquence gelée : **pas de déploiement et pas de tuning supplémentaire** ; la raison est écrite et le
périmètre **n'est pas élargi** pour chercher une autre réponse. La clause de clôture du § K.2 ne s'applique
pas — elle ne vaut que pour une `dépriorisation`. Suite : **C3** (equity continue, sélection chronologique),
qui devra aussi reprendre l'amorçage des portes de régime (warmup 1 d/1 w de BTC `sufficient=False`).

Validité des analyses (§ I-B) : **7/7**, dont la reproductibilité **bit à bit** des `LB_j` — un second passage
complet et indépendant de `rejeu_effect` donne un artefact **identique champ par champ** hors horodatage.

Correctif postérieur du validateur : `rejeu_validate_campaign.py` acceptait un sous-bloc présent mais `null`
(faux vert, commit `5a443da`, huit tests négatifs et doctrine dans `skills/backtest.md`). Les artefacts
livrés n'en contiennent aucun ; re-validés avec le validateur corrigé, ils redonnent **EXPLOITABLE,
exit 0** (`validation_campaign_revalidated.json`) — le verdict n'est pas remis en cause.

### Clôture C3a — la chaîne C3 n'a produit qu'un refus d'entrée (inscrite le 2026-09-22, après coup : aucun run de backtest)

C3a livre le protocole gelé (`docs/protocole_c3.md` @ `d931293`) et son outillage (`scripts/audit/c3_*.py`, 806 tests) ;
**aucune simulation n'a été lancée, aucune donnée nouvelle produite**. Le seul « run » de la chaîne sur données réelles
est l'application de `c3_entry` à l'artefact du rejeu (entrée 11), qui le **refuse** — consigné parce que c'est la
seule sortie réelle de l'outillage et qu'elle borne ce que le rejeu peut encore prouver. Produit au commit `bd81b87`
(2026-09-22), revalidé au tip `acaeaf6` (empreintes inchangées, `test_c3_entry.py`).

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 12 | 2026-09-22 | C3a — validité d'entrée § I-A de l'artefact du rejeu (`c3_entry.py`, puis `c3_verdict.py chain` en test d'intégration) — **aucune simulation** | `grok_grid_atr_adaptive_v4` × BTC/USDC et SOL/USDC, les 96 configs de l'entrée 11, préfixe `train` seul (`[2023-04-01, T]`, `T = 2025-05-07T04:48:00Z` recalculé) | `results/rejeu_grid_20260919/P7_phase1_grid.json` (sha256 `08d981e493402f37…`, intact) ; métadonnées seules | `feat/c3a-protocole` @ `bd81b87`, revalidé au tip `acaeaf6` ; protocole `d931293` ; artefact lu : métriques v2, `replay_version` 2 | hérité de l'artefact (bybit + coûts GATE B) — non exercé | **Refus d'artefact `D_WARMUP_PREFIX`** (portée artefact, I-A.8, code 2) : D2 échoue sur **96/96** candidats (48 BTC `1d, 1w` ; 48 SOL `4h, 1d, 1w`) ; I-A.2 (`exec_interval`) et I-A.7 (couverture) `not_assertable` ; `chain` s'arrête à `entry`, aucun `verdict.json`. **Aucune sélection, aucun verdict économique** (§ D.3) | C3b : chantier producteur (exports `lots`, `exec_interval`, couverture, preuve de départ à plat, `single_call`, `first_fill_at`, amorçage suffisant au préfixe) puis campagne réelle sous la chaîne, inscrite ici **avant** lancement ; gate d'amendement du protocole | `results/c3a_entry_validation/entry_rejeu_grid_20260919.{json,md}`, `agent/rapport_session_c3a_20260922.md` § 3 |

Phrase portée par l'artefact (`entry_rejeu_grid_20260919.md`), citée telle quelle :

> **Entrée refusée** — `D_WARMUP_PREFIX` (portée artefact, I-A.8) : D2 échoue sur la totalité des 96 candidats de l'artefact : refus d'artefact D_WARMUP_PREFIX, aucun classement n'est produit (§ I.1 l.5, § D.3)
>
> cet artefact ne satisfait pas les conditions d'entrée C3

Verdict de session : **aucune sélection, aucun verdict économique**. Les trois issues n'ont été exercées que sur
fixtures synthétiques (`C3_SYNTH_`). **C3a ≠ C3** : le protocole et l'outil existent ; aucune campagne existante ne
les traverse.

### Adoption du protocole C3 v2.1 et du critère d'arrêt (inscrite le 2026-09-23 — aucun run)

Critère d'arrêt pré-enregistré, § 10 de `CONTRAINTES_POST_B4.md`, adopté avec v2.1 du protocole C3. Première
campagne : famille grid, fenêtre 2021-03-01 → 2026-06-29, ancrage 70 %, BTC/ETH/SOL sur USDT Binance, manifeste à
geler avant tout run.

- **Protocole** : `docs/protocole_c3.md` v2.1, amendé le 2026-09-23 (vingt-huit amendements, adoptés par Bruno,
  quatorze réserves — `docs/amendements_c3_v2.1.md`, section « Adoption ») ; sha256
  **`9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129`** — celui que portera le manifeste de la
  première campagne (v2.0, `9b62915069e59e9b…`, reste celui du livrable C3a). Branche `feat/c3-amendements-v2.1`.
- **Ancrage de la première campagne** : `T = 2024-11-22T04:48:00Z` (préfixe 1362,2 j, période évaluée 583,8 j).
- **Ce que la lecture des données laisse attendre, écrit avant tout run** (§ A.8 v2.1) :
  - **SOL partiel ou absent** : au 2021-03-01, SOL n'a que 29 bougies 1 w (première le 2020-08-17 ; la 50ᵉ, qu'exige
    le régime 1 w, tombe le 2021-07-26) — D2 retire les candidats SOL dont une porte lit le 1 w ;
  - **D1 1 w échoue** sur les trois paires : six estampilles hebdomadaires manquent en 2022, dans le préfixe
    (06-06, 07-04, 09-05, 10-03, 11-07, 12-05) — 188/194 = 96,9 % < 97 % ; **sans reconstruction, l'ensemble
    admissible est vide** (`A_NO_ADMISSIBLE_CANDIDATE`, non compté au sens du § 10.1, retrait par D1). La décision de
    reconstruire ces estampilles depuis le 1 d — chiffrée, en rows marquées dérivées, jamais silencieuse — est un
    **prérequis du manifeste**.
- **Aucune simulation lancée, aucune donnée produite, aucune sélection.** Le livrable réel de C3a
  (`results/c3a_entry_validation/`, entrée 12) reste l'historique v2.0 ; sous v2.1, `c3_anchor` refuse son manifeste.

### Reconstruction des 8 estampilles 1 w USDT (inscrite le 24/09/2026, avant l'écriture)

Opération de **données**, pas un essai : aucune simulation, aucune sélection, hors quota. Elle lève le
prérequis que le § A.8 v2.1 du protocole pose au manifeste de la première campagne (D1 1 w à 188/194 sur le
préfixe `(2021-03-01, T = 2024-11-22T04:48Z]`). Brief `agent/agent_reconstruction_1w.md` ; décisions de
Bruno du 24/09 (périmètre, marquage, D1, gate de l'étape 1).

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 13 | 2026-09-24 | C3b, données — reconstruction des estampilles 1 w manquantes depuis le 1 d (`scripts/audit/reconstruct_1w.py write --vwap-policy null`), **aucune simulation** | `exchange='binance'`, `BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `interval = 10080` : **8 estampilles × 3 paires = 24 rows** — 2022-06-06, 2022-07-04, 2022-09-05, 2022-10-03, 2022-11-07, 2022-12-05 (préfixe), 2025-02-03, 2025-03-03 (période évaluée) | sources : rows 1 d Binance Vision USDT, 7 par semaine (`S − 6 j … S`) ; contrôle sur `(2021-03-01, 2026-06-29]` | branche `feat/c3b-reconstruction-1w` : check `2bee227`, exécuté au `35b06ce` ; write `9b59c26`, exécuté au commit de cette entrée (SHA consigné par row dans `ohlc_derived.git_sha` et dans `write_report.json`) ; migration `c3bd1e7a0001` ; métriques : sans objet | sans objet | 24 rows `market_data_ohlc` + 24 rows `ohlc_derived`, contrôle rejoué vert avant les INSERT ; D1 1 w préfixe **188/194 → 194/194** sur les trois paires, période évaluée 82/84 → 84/84 | manifeste de la première campagne : les 8 estampilles dérivées y sont **listées**, lues dans `ohlc_derived` | `results/reconstruction_1w_2022_2025/` (`check_report.*`, `write_report.*`, `report.md`) |

- **Méthode `agg_1d_v1`** (fonction pure, `Decimal`, sommes exactes) : `open` du premier jour, `close` du dernier,
  `high` max, `low` min, `volume` Σ, `trades_count` Σ ; exactement 7 rows 1 d sur la grille `S − k j`, sinon
  semaine non reconstructible. Marquage : table de provenance `ohlc_derived` (une row ⟺ la row OHLC de même clé
  n'est pas une donnée d'exchange), `source_sha256` rejouable depuis les 7 rows 1 d ; aucune colonne ajoutée à
  `market_data_ohlc`, aucune valeur `exchange` spéciale.
- **Contrôle d'exactitude (c)**, mesuré avant cette entrée (`check` au `35b06ce`, 2026-09-24T15:12:01Z,
  `check_report.json` sha256 `f41b45f16ad8…`) : la méthode appliquée aux **810** semaines 1 w Vision présentes de la
  fenêtre (270 × 3) redonne la row Vision **au `Decimal` près** — **0 mismatch OHLCV, 0 mismatch `trades_count`** ;
  24/24 cibles reconstructibles (7/7 rows 1 d, sans NULL). `write` rejoue ce contrôle dans sa transaction et refuse
  sur un seul mismatch.
- **vwap** : la colonne est **NULL sur toutes les rows `binance` 1 d et 1 w, USDC comme USDT** (0 non NULL sur les
  12 séries) ; **aucun lecteur** ne l'utilise sur le chemin backtest / C3 — le VWAP des stratégies est recalculé depuis
  `close` et `volume` (`indicators/multi_timeframe.py:378-379`, `get_vwap:868`). Décision Bruno (24/09) :
  `vwap_policy = null`, les 24 rows dérivées portent `vwap` NULL.
- **Décision D1** (Bruno, 24/09) : les rows dérivées sont **comptées comme observées** par D1 ; le manifeste liste les
  8 estampilles dérivées.
- **Cause** (probe des 33 fichiers mensuels Vision 1 w des cibles, tous HTTP 200) : les 24 bougies sont absentes du
  fichier du mois d'ouverture **et** de celui du mois de clôture. La **règle de génération de Vision a changé** : le
  fichier `2025-03`, **régénéré le 08/10/2025**, sert la semaine à cheval `2025-04-07` ; les fichiers de 2022
  (Last-Modified entre le 02/06/2022 et le 04/01/2023) et de 2025-01 / 2025-02 (04/03/2025) **n'ont pas été régénérés**
  et omettent la semaine à cheval qui finit le 2 du mois suivant ou plus tard. L'import n'y est pour rien (il insère
  tout ce que le fichier sert). **Conséquence** : la reprise 1 w 2026-07/08 (skill `binance_import.md`) ne devrait pas
  exiger de reconstruction — **à vérifier par un contrôle au moment de la reprise** (le `check` de ce chantier est borné
  à la fenêtre de la campagne et aux 8 cibles : la vérification portera sur les estampilles 1 w reprises).
- **Idempotence** : l'import Vision fait `ON CONFLICT DO NOTHING` (`binance_vision_import.py:200-201`) — une vraie row
  Vision servie plus tard pour une des 8 estampilles **n'écraserait pas** la row dérivée ; la remplacer exige un
  `DELETE` explicite de la row OHLC et de sa provenance, puis le réimport.

### Issue de l'entrée 13 (inscrite après l'écriture)

Migration `c1ae7a1c0001 → c3bd1e7a0001` appliquée par le tunnel le 2026-09-24 à 15:47:07-15:47:12Z ; `write` exécuté au
`4866c7d` de 15:47:19 à 15:47:26Z, `vwap_policy = null`.

| # | Issue mesurée | Source |
|---|---|---|
| 13 | Contrôle (c) rejoué dans la transaction avant les INSERT : 810 semaines, **0 mismatch OHLCV**, 0 mismatch `trades_count` ; **24 rows `market_data_ohlc` + 24 rows `ohlc_derived`** écrites, valeurs identiques à celles reconstruites par `check` au `35b06ce` | `results/reconstruction_1w_2022_2025/write_report.md` |
| 13 | Relecture sur connexion neuve : **D1 1 w préfixe 194/194** (passe) sur BTC/USDT, ETH/USDT et SOL/USDT, période évaluée 84/84, 0 estampille manquante sur `(2021-03-01, 2026-06-29]`, 278 semaines contrôlées par paire, 0 mismatch ; `count(*) ohlc_derived` = 24, chaque `source_sha256` rejoué égal, chaque row OHLC égale à l'agrégat rejoué | idem |
| 13 | Contrôle SQL indépendant du script : `binance` 11 952 996 rows (= 11 952 972 + 24), 1 w USDT 391 / 391 / 308, un seul `git_sha` dans `ohlc_derived`, 0 provenance sans row OHLC, `alembic_version` = `c3bd1e7a0001` | `results/reconstruction_1w_2022_2025/evidence/independent_counts.txt` |

Reste avant le merge sur `dev` : les 24 tests `_full` sur le serveur (diff § L.3 non vide sur `src/`, option A), sur
signal de Bruno ; aucune commande alembic sur le serveur avant le merge. Rapport : `results/reconstruction_1w_2022_2025/report.md`.

### Mesure SOL/D2 — classes `decision_timeframes` et amorçage au 2021-03-01 (inscrite le 25/09/2026, après la mesure — aucun run de backtest)

Mesure en **lecture seule**, pas un essai : aucune simulation, aucune sélection, hors quota. Brief
`agent/agent_sol_d2_1w_modes.md`. Dernière mesure avant le manifeste de la première campagne (§ A.8 D2 sur SOL).
Inscrite parce qu'elle porte un fait nouveau (brief, § Livrables).

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Issue mesurée | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 14 | 2026-09-25 | C3b, mesure — amorçage C2 du moteur grid au début du préfixe (`scripts/audit/warmup_at.py`), **aucune simulation** | `grok_grid_atr_adaptive_v4`, six classes d'équivalence de `decision_timeframes` (C1-C6) × `BTC/USDT`, `ETH/USDT`, `SOL/USDT` | `exchange='binance'`, 5 m / 4 h / 1 d / 1 w, amorçage au 2021-03-01, `end = T = 2024-11-22T04:48Z` | `c38d718` (branche `feat/c3b-sol-d2`), serveur, lecture seule garantie par Postgres ; métriques : sans objet | sans objet | contrôles verts (SOL 1 w 29 bougies, première 2020-08-17, prête 2021-07-26 ; 0 row dérivée dans l'amorçage ; 11 952 996 rows binance ; alembic `c3bd1e7a0001` inchangé) ; D2 : BTC/ETH pass dans les six classes ; **SOL survit dans C3-C6, sort dans C1-C2** (`fail(1w: 29/50)`), ensemble survivant non vide | aucune ici ; entrées de la conversation manifeste : `decision_timeframes` par candidat dès que l'univers couvre plus d'une classe (rapport § 8), candidats amendement v2.2 (§ 8.1), dettes C3b (§ 8.2) | `results/sol_d2_1w_modes/report.md`, `warmup_2021-03-01.json` (sha256 `566beeb4…d35d`) |

- **Fait nouveau** : l'axe pressenti « `bias_1d ≠ 0` » est faux ; **`grid_levels` est un axe** de
  `decision_timeframes`. `regime_1d` décide si et seulement si `_get_directional_bias` n'est pas constante sur le
  domaine de `get_regime` ; `bias_1d ≠ 0` n'est ni suffisant ni nécessaire. Candidats amendement v2.2 : rapport § 8.1,
  items 1 et 2. Dettes C3b : rapport § 8.2, items 1 et 2. Non redits ici.
- **Tunnel** : la suite complète locale du 25/09 a perdu les 24 `_full` sur une coupure du tunnel à 11:23:48Z ; les
  mêmes 24 passent au serveur au même SHA (`full=0`). C'est une **occurrence d'instabilité du tunnel, distincte du
  hash divergent 2/2844 du 24/09**, qui reste ouvert (rapport § 9.3-9.4).
- L'item « décision de reconstruction 1 w » de « Essais à venir » est clos par l'entrée 13 ; le paragraphe n'est pas
  réécrit (ajout seul).

### C3b lot 3 — producteur préfixe sur la fenêtre de conformité 2020 (inscrite le 27/09/2026, avant lancement — essai d'instrument, fenêtre hors campagne, aucune lecture économique)

Essai d'**instrument**, pas un essai de recherche : aucune sélection n'en sort, hors quota. Le producteur calcule des
métriques de candidats — d'où cette ligne, exigée par le brief (`agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 3 », critère de
fin) — sur une fenêtre **entièrement antérieure au 2021-03-01**, et aucune n'est lue. Attendu complet, item par item :
`results/c3b_producteur/prefix_conformite/ATTENDU.md`, committé avec cette entrée.

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 15 | 2026-09-27 | C3b lot 3 — essai d'instrument du producteur préfixe (`scripts/audit/c3b_prefix.py`), puis chaîne `c3_anchor → c3_entry → c3_benchmark → c3_select` sur sa sortie ; **aucune lecture économique** | `grok_grid_atr_adaptive_v4`, 4 paramétrages — un par ensemble de `decision_timeframes` (classes C1, C2, C5, C6) — × `BTC/USDT`, `ETH/USDT`, `SOL/USDT` = **12 candidats** ; provenance `unknown` : aucun `validé` atteignable sur une fenêtre d'instrument | `exchange='binance'`, exécution 5 m, séries 4 h / 1 j / 1 w ; fenêtre de conformité `2020-01-06 → 2020-12-28`, préfixe `[2020-01-06, T = 2020-09-11T21:36Z]`, **hors campagne** (garde-fou 6) ; toute lecture bornée à `≤ T` | branche `feat/c3b-producteur`, exécuté au commit de cette entrée (SHA consigné dans `prefix_run.json`) ; métriques v2, `replay_version` 2 ; protocole v2.1 `9300f4e5…` | bybit maker 0,10 % / taker 0,25 % ; coûts de `config/pair_costs_b4.json` pour la paire de déploiement USDC (§ A.6, transposition déclarée) ; `min_order_usdc 5.0` (valeur du rejeu, inerte sur le grid) | producteur : deux exécutions en code 0, sorties identiques au bit (4 workers puis 1) ; `c3_anchor` 0 ; `c3_entry` 0, **aucune clause non assertable**, D2 en échec sur les 4 candidats SOL (aucune donnée SOL avant le 2020-08-11) ; `c3_benchmark` 0 (SOL `E_NO_BENCHMARK`) ; `c3_select` 0, sélection descriptive, SOL sort par D1 ; issue BTC/ETH **ni déclarée ni lue** ; `alembic` inchangé | aucune décision économique ; la conformité du préfixe conditionne le lot 4a (run d'évaluation) | `results/c3b_producteur/prefix_conformite/` (`ATTENDU.md`, `manifest.json`, rapport au commit de preuves) |

- **Garde-fou 6, mécanique** : le producteur refuse (code 2) tout manifeste dont la fenêtre finit après le
  2021-03-01 tant que `results/c3b_producteur/CAMPAIGN_UNLOCK` n'existe pas. Ce fichier n'existe pas ; il sera créé
  par Bruno à la conversation manifeste.
- **Tout lancement est consigné** (`status.txt` par lancement) ; un écart à l'attendu est un constat, sans relance
  avant diagnostic. L'issue mesurée sera inscrite dans une section suivante, sans réécrire celle-ci.

### Issue de l'entrée 15 (inscrite après le run — aucune lecture économique)

Un seul lancement, au `6509737` (pilote sha256 `ee1f5a53…`, consigné dans `status.txt`), le 2026-09-28 de 06:46:17 à
06:49:15Z sur le serveur, lecture seule assertée par Postgres. Archive `~/archive/c3b_lot3_20260928/` (sha256
`80b5f2b9…`) vérifiée avant le `rm -rf ~/runs/c3b_prefix` (06:51:56Z).

| # | Issue mesurée | Source |
|---|---|---|
| 15 | Producteur : run1 (4 workers) et run2 (1 worker) en **code 0** ; `observations.json` `57e48213…`, `coverage.json` `5871f74e…`, `candles.json` `20c0d1fb…` **identiques au bit** ; 12 entrées ; `T = 2020-09-11T21:36Z` ; 0 estampille dérivée dans `(début, T]` ; `alembic` `c3bd1e7a0001` inchangé | `results/c3b_producteur/prefix_conformite/server/status.txt`, `run1/prefix_run.json` |
| 15 | Chaîne : `c3_anchor` 0 ; `c3_entry` 0 — I-A.1 à I-A.8 `ok`, **aucune clause non assertable**, couverture évaluée, D2 en échec sur les 4 candidats SOL et eux seuls (séries attendues) ; `c3_benchmark` 0 — SOL non constructible (estampille `2020-01-06T00:05Z` absente) ; `c3_select` 0 — provenance `unknown`, aucune `SÉLECTION_VALIDE`, SOL `DESCRIPTIF` par D1 (5 min 31/249) ; issue BTC/ETH **non lue** | `server/chain/`, `server/verify_attendu.out` |
| 15 | Attendu tenu sur ses 7 items ; défaut de rédaction de l'item 5 (« sélection descriptive » présume un candidat retenu), vérifié par le seul booléen `!= SÉLECTION_VALIDE`, qui ne lit pas l'issue | `results/c3b_producteur/prefix_conformite/README.md` § 4 |

### C3b lot 4a — producteur d'évaluation sur la fenêtre de conformité 2020 (inscrite le 28/09/2026, avant lancement — essai d'instrument, fenêtre hors campagne, aucune lecture économique)

Essai d'**instrument**, pas un essai de recherche : aucune sélection n'en sort, et il est hors quota. C'est un run
distinct de l'entrée 15 (nouveau script, fenêtre `[T, fin]` jamais lue jusqu'ici, nouvelles métriques de candidat) :
il reçoit donc sa propre entrée. L'entrée 15 est close, avec son issue inscrite, et on n'y ajoute rien (ajout seul).
Attendu complet, item par item : `results/c3b_producteur/eval_conformite/ATTENDU.md`, committé avec cette entrée.

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 16 | 2026-09-28 | C3b lot 4a — essai d'instrument du producteur d'évaluation (`scripts/audit/c3b_evaluate.py`) : un seul `run(pair, T, fin)` par chemin, puis admission (`cc.evaluation_admission`) et `c3_continuity` sur un comparateur d'évaluation **synthétique** ; **aucune lecture économique** | `grok_grid_atr_adaptive_v4`, deux chemins exécutés chacun deux fois. **Sélection** : le retenu de `selection.json` du lot 3, consommé mécaniquement ; seul le code (0 évalué / 2 `nothing_to_evaluate`) est rapporté, et les sorties sont archivées sans être lues. **Désignation** : `145867637b7f9bac…` (`ETH/USDT`, classe C2, séries `[1w, 4h]`), première identité BTC/ETH dans l'ordre lexicographique, recalculée par le pilote | `exchange='binance'`, exécution 5 m, séries 4 h / 1 j / 1 w ; évaluation `[T = 2020-09-11T21:36Z, fin = 2020-12-28T00:00Z]`, amorçage avant `T` (`≥ T − 400 j`), **hors campagne** (garde-fou 6 ; la désignation est refusée au-delà du 2021-03-01, `CAMPAIGN_UNLOCK` ou non) | branche `feat/c3b-producteur`, exécuté au commit de cette entrée (SHA consigné dans `evaluation_run_provenance.json`) ; métriques v2, `replay_version` 2 ; protocole v2.1 `9300f4e5…` | bybit maker 0,10 % / taker 0,25 % ; coûts de `config/pair_costs_b4.json` pour la paire de déploiement USDC (§ A.6) ; `min_order_usdc 5.0` (inerte sur le grid) | sélection : deux codes égaux dans {0, 2}, rien d'autre ; désignation : deux exécutions en code 0, `evaluation_run.json` identique au bit, preuve à plat `{at: T, cash: "1000", qty: "0", pending: 0}` (**DÉCLARÉ**), `single_call` vrai, `first_fill_at > T`, 109 points quotidiens ; admission : réelle et admise ; `c3_continuity` 0, **c1, c2, c5 `DECLARED`**, c3 et c4 `VERIFIED`, comparateur synthétique sans valeur ; `alembic` inchangé | aucune décision économique ; la conformité de l'évaluation conditionne le lot 4b (comparateur d'évaluation, § F.2) | `results/c3b_producteur/eval_conformite/` (`ATTENDU.md`, rapport au commit de preuves) |

- **Deux gardes mécaniques.**
  - Le garde-fou 6 refuse toute fenêtre qui finit après le 2021-03-01 tant que `CAMPAIGN_UNLOCK` n'existe pas.
  - La désignation (`--candidate`) est refusée sur une telle fenêtre **même si** `CAMPAIGN_UNLOCK` existe : sur la
    campagne, seul le retenu de `c3_select` s'évalue.
- **Tout lancement est consigné** (`status.txt` par lancement). Un écart à l'attendu est un constat, sans relance
  avant diagnostic. L'issue mesurée sera inscrite dans une section suivante, sans réécrire celle-ci.

### Issue de l'entrée 16 (inscrite après le run — aucune lecture économique)

Un seul lancement, au `85c8db7` (pilote sha256 `7bdc1bd2…`, consigné dans `status.txt`), le 2026-09-28 de 12:34:12 à
12:34:44Z sur le serveur, lecture seule assertée par Postgres. Il a eu lieu après la CI verte sur `85c8db7` : la
tentative 1 était rouge, sur le test instable `test_rejeu_effect.py`, sans rapport avec le lot, et la tentative 2 est
verte. Archive `~/archive/c3b_lot4a_20260928/` (sha256 `1e401ab2…`), vérifiée avant le `rm -rf ~/runs/c3b_eval4a`
(12:36:11Z).

| # | Issue mesurée | Source |
|---|---|---|
| 16 | Chemin sélection : **code 0 aux deux exécutions** (événement `evaluated`), sorties identiques au bit. C'est le seul fait rapporté ; les sorties sont archivées, non lues | `results/c3b_producteur/eval_conformite/server/status.txt` |
| 16 | Chemin désigné (`145867637b…`, recalculé égal) : code 0 ×2, `evaluation_run.json` `a2042a02…` identique au bit. Preuve de départ à plat `{at: T, cash: "1000", qty: "0", pending: 0}` (**DÉCLARÉ**), moteur à `usdc_balance "1000.0"` avant `run` ; `single_call` vrai ; `first_fill_at` après `T` ; 109 points quotidiens | `server/designated/run1/`, `server/verify_attendu.out` |
| 16 | Admission : réelle et admise ; `c3_continuity` 0, **c1, c2, c5 `DECLARED`**, c3 et c4 `VERIFIED`, `stamp_cell` `NOT_VERIFIABLE` (rien liquidé à `fin`), comparateur synthétique sans valeur ; `alembic` `c3bd1e7a0001` inchangé | `server/chain/continuity.json` |
| 16 | Attendu tenu sur ses 8 items. Défaut de ma part : une liste des tailles de fichiers a laissé voir que l'artefact du chemin sélection diffère de celui du chemin désigné (retenu ≠ désigné). Rien d'autre n'est lu, et ce fait n'est utilisé nulle part | `results/c3b_producteur/eval_conformite/README.md` § 4 |

### C3b lot 4b — comparateur d'évaluation et procédure § F.2, chaîne complète sur la fenêtre de conformité 2020 (inscrite le 28/09/2026, avant lancement — essai d'instrument, fenêtre hors campagne, aucune lecture économique, issue non lue)

Essai d'**instrument**, pas un essai de recherche : aucune sélection n'en sort, et il est hors quota. Il reçoit sa
propre entrée, parce que c'est un run neuf :
- le comparateur d'évaluation est construit sur `[T, fin]` ;
- le tirage du § F.2 a lieu ;
- `c3_verdict` calcule un verdict pour la première fois.

**L'issue n'est ni déclarée ni lue** (décision de Bruno du 28/09). L'entrée 16 est close, avec son issue inscrite, et
on n'y ajoute rien. Attendu complet, item par item : `results/c3b_producteur/eval_f2_conformite/ATTENDU.md`, committé
avec cette entrée.

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 17 | 2026-09-28 | C3b lot 4b — essai d'instrument du producteur d'évaluation complet (`scripts/audit/c3b_evaluate.py`, parties 1 et 2 : comparateur § C.3-C.5, λ du préfixe tenus fixes, procédure § F.2), puis `c3_verdict.py chain` **complète** (six étapes) sur sa sortie ; `--campaign C3B_LOT4B`, étiquette d'instrument (dette 21 intacte) ; **aucune lecture économique, issue non lue** | `grok_grid_atr_adaptive_v4` ; **chemin sélection seul** : le retenu de `selection.json` du lot 3, consommé mécaniquement, deux exécutions ; aucune identité, paire, métrique ni issue ne remonte au dépôt | `exchange='binance'`, exécution 5 m, séries 4 h / 1 j / 1 w ; évaluation `[T = 2020-09-11T21:36Z, fin = 2020-12-28T00:00Z]` (`n_jours` 107,1, 108 rendements), bougies du comparateur lues sur `[T, fin]` pour la seule paire évaluée, amorçage `≥ T − 400 j`, **hors campagne** (garde-fou 6) | branche `feat/c3b-producteur`, exécuté au commit de cette entrée (SHA consigné dans la provenance) ; métriques v2, `replay_version` 2 ; protocole v2.1 `9300f4e5…` | bybit maker 0,10 % / taker 0,25 % ; coûts de `config/pair_costs_b4.json` pour la paire de déploiement USDC (§ A.6) ; `min_order_usdc 5.0` (inerte sur le grid) | producteur : deux exécutions en code 0, `evaluation.json` identique au bit, trois autres artefacts identiques, interpréteur du clone ; chaîne : `anchor`, `entry`, `benchmark`, `select`, `continuity` et `verdict` en code 0, `chain.verified` vrai, **zéro violation, zéro violation au rejeu** ; `alembic` inchangé ; `validé` et `réfuté` inatteignables par construction (provenance `unknown`) | aucune décision économique ; la conformité du § F.2 conditionne la porte § L.5 et le STOP avant merge de C3b | `results/c3b_producteur/eval_f2_conformite/` (`ATTENDU.md`, rapport au commit de preuves) |

### Issue de l'entrée 17 (inscrite après le run — aucune lecture économique, issue non lue)

- **Lancement** : un seul, au `459190a` (pilote sha256 `9b401797…`, consigné dans `status.txt`), le 2026-09-28 de
  14:48:51 à 14:49:13Z, sur le serveur, en lecture seule assertée par Postgres.
- **CI** : il a eu lieu après la CI verte sur `459190a`, dès la tentative 1.
- **Archive** : `~/archive/c3b_lot4b_20260928/` (sha256 `6c02f438…`), vérifiée par codes seulement avant le
  `rm -rf ~/runs/c3b_eval4b` (14:50:01Z).
- **Rien n'a été lu du chemin sélection** hors de `status.txt`.

| # | Issue mesurée | Source |
|---|---|---|
| 17 | Producteur, chemin sélection : **code 0 aux deux exécutions** (événement `evaluated`) ; `evaluation.json` identique au bit, trois autres artefacts identiques, interpréteur du clone. Les sorties sont archivées, non lues | `results/c3b_producteur/eval_f2_conformite/server/status.txt` |
| 17 | Chaîne complète : `anchor`, `entry`, `benchmark`, `select` et `continuity` en 0, `verdict` en 0 ; **`chain.verified` vrai, 0 violation, 0 violation au rejeu**. L'issue publiée **n'est pas lue** (`validé` et `réfuté` sont inatteignables par construction : provenance `unknown`) | `server/status.txt`, `server/verify_attendu.out` |
| 17 | `alembic` `c3bd1e7a0001` inchangé ; attendu tenu sur ses 5 items vérifiables (le 6ᵉ, les bornes, repose sur des appuis déclarés) | `server/alembic_{before,after}.txt` |
| 17 | Défauts de ma part : au STOP 1, un premier passage de mutants avait 4 survivants, tous du côté des tests (monde de test trop court, candidat en premier bloc, données non discriminantes), corrigés, puis 35 rouges sur 35 ; le chemin de l'archive du lot 3 était faux dans le pilote, vu avant le lancement | `results/c3b_producteur/eval_f2_conformite/README.md` § 3, § 6 |

### Adoption du protocole C3 v2.2 (entrée 18, inscrite le 2026-09-29 — aucun run)

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 18 | 2026-09-29 | Amendement v2.2 du protocole C3 — chantier documentaire, **aucun run** | sans objet | aucune donnée lue ; aucune base, aucun serveur, aucun tunnel | branche `feat/c3-amendements-v2.2` depuis `dev` @ `8689636` ; `src/` et `scripts/audit/*.py` inchangés ; protocole v2.2 sha256 `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a` | sans objet | sans objet — aucune issue possible | outillage v2.2 (`results/c3_v2_2/outillage_v2_2.md`), puis manifeste de la première campagne, portant le sha256 v2.2 | `docs/amendements_c3_v2.2.md` (section « Adoption »), `results/c3_v2_2/report.md` |

- **Protocole** : `docs/protocole_c3.md` v2.2, amendé le 2026-09-29 — douze amendements (AM-00 à AM-12), adoptés par
  Bruno après lecture adverse de Claude sur AM-03, AM-06 et AM-08 (six retouches, C-1 à C-6) ; huit réserves
  d'application (R-15 à R-22). Le sha256 de v2.1 (`9300f4e5…4129`) reste celui des artefacts de C3b, historiques ;
  sous v2.2, `c3_anchor` refuse leur manifeste, comme celui du livrable C3a (v2.0).
- **Ce qui précède le manifeste** : l'outillage des réserves bloquantes pour le manifeste (R-15 recoupements § L.2,
  R-16 clés `_quote`, R-18 refus amont, R-19 évaluation sans exécution). Avant la première campagne comptée :
  R-17 (registre et critère d'arrêt), R-21 (D4 et CAGR), R-22 (sorties code 1 hors table).
- **Compteur du § 10.2** : inchangé (jalon : premier verdict grid avant le 2027-01-31).

### C3 outillage v2.2, lot 3 — conformité du producteur et de la chaîne sous v2.2 sur la fenêtre 2020 (entrée 19, inscrite le 2026-09-29, avant lancement — essai d'instrument, fenêtre hors campagne, aucune lecture économique, issue non lue)

Essai d'**instrument**, pas un essai de recherche : aucune sélection n'en sort, et il est hors quota. C'est un run
neuf, parce que la conformité du 28/09 (entrées 15-17, v2.1) n'a plus de valeur probante sous v2.2 : `c3_anchor`
refuse son manifeste. Les **quatre temps** sont rejoués (préfixe, chaîne 1-4, évaluation, chaîne complète),
**trois fois**, au code du chantier outillage v2.2. Attendu complet, item par item :
`results/c3_outillage_v2_2/conformite/attendu.md`, committé avec cette entrée. Le run se fait au SHA de ce commit.

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 19 | 2026-09-29 | C3 outillage v2.2, lot 3 — essai d'instrument : `c3b_prefix.py` → `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select` → `c3b_evaluate.py --selection` → `c3_verdict.py chain` (six étapes, neuf entrées dont `candles_eval.json`), **trois exécutions** (`--workers` 4 / 1 / 4 au préfixe, même `--now`, même chemin absolu), registre **neuf par exécution** ; `--campaign OUTILLAGE_V22_CONF`, étiquette d'instrument (dette 21 intacte) ; **aucune lecture économique, issue non lue** | `grok_grid_atr_adaptive_v4`, 4 paramétrages (classes C1, C2, C5, C6) × `BTC/USDT`, `ETH/USDT`, `SOL/USDT` = **12 candidats** ; famille de test `test-conformite-instrument-2020` (jamais une famille de campagne) ; provenance `unknown` : aucun `validé` atteignable ; chemin sélection seul, aucune identité, paire, métrique ni issue ne remonte au dépôt | `exchange='binance'`, exécution 5 m, séries 4 h / 1 j / 1 w ; fenêtre de conformité `2020-01-06 → 2020-12-28`, `T = 2020-09-11T21:36Z` ; lectures bornées à `≤ T` (préfixe) et `≤ fin` (évaluation), amorçage `≥ 400 j` avant ; **hors campagne** (garde-fou 6, `CAMPAIGN_UNLOCK` absent) | branche `feat/c3-outillage-v2.2`, exécuté au commit de cette entrée (code identique à `5f61ac9`, `interdits_S1.out`) ; métriques v2, `replay_version` 2 ; protocole v2.2 `1bed7696…292a` ; manifeste `c3769a6a…1ff7` | bybit maker 0,10 % / taker 0,25 % ; coûts de `config/pair_costs_b4.json` pour la paire de déploiement USDC (§ A.6) ; `min_order_quote 5.0` (valeur du rejeu, inerte sur le grid) | producteur préfixe 0 ×3 ; chaîne 1-4 autonome 0 ×4 ×3 ; producteur d'évaluation `0 evaluated` ×3 ; chaîne complète : six codes d'étape en 0, `chain.verified` vrai, violations vides, zéro violation au rejeu, ×3 ; **23 artefacts identiques au bit sur les trois exécutions** (booléens seulement, aucun sha d'artefact versionné) ; `alembic` `c3bd1e7a0001` inchangé ; service et collector inchangés ; `validé` et `réfuté` inatteignables par construction (provenance `unknown`) | aucune décision économique ; la conformité v2.2 est la porte du chantier outillage v2.2, avec la porte § L.5 option 1 ; merge sous décision humaine | `results/c3_outillage_v2_2/conformite/` (`attendu.md`, `manifest.json`, pilote, preuves au commit suivant) ; `results/c3_outillage_v2_2/report.md` |

- **Garde-fou 6, mécanique** : le producteur refuse (code 2) toute fenêtre qui finit après le 2021-03-01 tant que
  `results/c3b_producteur/CAMPAIGN_UNLOCK` n'existe pas. Ce fichier n'existe pas, et ce lot ne le crée pas.
- **Tout lancement est consigné** (`status.txt`). Un écart à l'attendu est un constat : STOP, sans relance ni lecture de
  diagnostic avant l'accord de Bruno. L'issue mesurée sera inscrite dans une section suivante, sans réécrire celle-ci.

### Issue de l'entrée 19 (inscrite après le run — aucune lecture économique, issue non lue)

- **Lancement** : un seul, au `08cba3d` (S1). Pilote `5a2cc18d…`, exécuté depuis le clone et consigné dans
  `status.txt`. Le 2026-09-30 de 07:10:19 à 07:14:28Z, sur le serveur, en lecture seule assertée par Postgres.
- **CI et relecture** : le run a eu lieu après la CI verte sur S1 (tentative 1), la relecture de l'attendu (STOP 1)
  et le GO de lancement de Bruno.
- **Archive** : `~/archive/c3_outillage_conf_20260930/` (sha256 `17a1e6e8…0211`, 139 fichiers), vérifiée par codes
  seulement avant le `rm -rf` du run (07:15:05Z).
- **Rien n'a été lu du chemin sélection** hors de `status.txt`.

| # | Issue mesurée | Source |
|---|---|---|
| 19 | Trois exécutions (workers 4 / 1 / 4) : producteur préfixe **0** ; `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select` autonomes **0** ; producteur d'évaluation **`0 event=evaluated`** ; `chain` **0**, avec les six codes d'étape en 0, **`chain.verified` vrai, violations vides, zéro violation au rejeu** — les trois fois. L'issue publiée **n'est pas lue** (`validé` et `réfuté` sont inatteignables par construction : provenance `unknown`) | `results/c3_outillage_v2_2/conformite/server/status.txt` |
| 19 | **23 artefacts identiques au bit** sur les trois exécutions (`compared=23 differing=0 absent=0`), liste attendue exacte ; aucun sha d'artefact versionné (booléens seulement) | `status.txt`, `verify_attendu.out` |
| 19 | `alembic` `c3bd1e7a0001` inchangé ; service `8689636`, collector actif, `NRestarts=0` inchangés ; `CAMPAIGN_UNLOCK` absent ; attendu **tenu sur ses 10 items vérifiables** (le 11ᵉ, les bornes, repose sur des appuis déclarés) | `conformite/server/verify_attendu.out` |
| 19 | Porte § L.5 option 1 au `4089fd5` (S2) : **24/24 `_full`** (agrégat JUnit `tests:24,failures:0,errors:0,skipped:0,missing:0`), le 2026-09-30 de 07:25:15 à 08:36:55Z. Ce ne sont pas des runs du producteur : backtests P6 comparés par hash, aucune métrique lue | `results/c3_outillage_v2_2/gate_L5/` |
| 19 | Défauts de ma part, tous trouvés **avant** le lancement : témoin de la preuve d'`interdits.sh` rouge sur mon propre harnais ; ordre de copie dans mon script de simulation ; deux fragilités portables du pilote (`wc -l`, lien symbolique), trouvées par la simulation locale | `results/c3_outillage_v2_2/report.md` § 6.2 |

### Adoption du protocole C3 v2.3 (entrée 20, inscrite le 2026-09-30 — aucun run)

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 20 | 2026-09-30 | Gel du protocole C3 v2.3 (mini-amendement « évaluation différée ») — chantier documentaire, **aucun run** | sans objet | aucune donnée lue ; aucune base, aucun serveur, aucun tunnel | branche `feat/c3-amendements-v2.3` depuis `dev` @ `662c104` ; `src/` et `scripts/` inchangés ; protocole v2.3 sha256 `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6` | sans objet | sans objet — aucune issue possible | outillage v2.3 (huit `xfail` strict X1 à X8), puis manifeste de la première campagne, portant le sha256 v2.3 et la clé `deferred_evaluation.date` | `docs/amendements_c3_v2.3.md` (section « Adoption »), `results/c3_v2_3_gel/report.md` |

- **Protocole** : `docs/protocole_c3.md` v2.3, amendé le 2026-09-30 — trois amendements (AM-00 à AM-02), approuvés par
  Bruno en conversation manifeste et adoptés au STOP du gel (décisions G-1 à G-11). AM-01 inscrit l'évaluation
  différée : date déclarée au manifeste (`deferred_evaluation.date`, au moins 365 jours après `window.end`), engagement
  par l'empreinte d'un descripteur `D`, au registre seul. AM-02 ajoute la ligne 10 ter au § I.1 (code de sortie du
  producteur, forme de refus). Le sha256 de v2.2 (`1bed7696…292a`) devient historique ; sous v2.3, `c3_anchor` refuse
  tout manifeste v2.2.
- **Ce qui précède le manifeste** : l'outillage v2.3 (`docs/amendements_c3_v2.3.md`, « Réserves d'application »).
- **Compteur du § 10.2** : inchangé.

### C3 outillage v2.3, lot 2 — conformité du producteur et de la chaîne sous v2.3 sur la fenêtre 2020 (entrée 21, inscrite le 2026-09-30, avant lancement — essai d'instrument, fenêtre hors campagne, aucune lecture économique, issue non lue)

Essai d'**instrument**, pas un essai de recherche : aucune sélection n'en sort, et il est hors quota. C'est un run
neuf, parce que la conformité du 30/09 (entrée 19, v2.2) n'a plus de valeur probante sous v2.3 : `c3_anchor` refuse son
manifeste (sha v2.2, pas de `deferred_evaluation.date`). Les **quatre temps** sont rejoués (préfixe, chaîne 1-4,
évaluation, chaîne complète), **trois fois**, au code du chantier outillage v2.3 (lot 1). Attendu complet, item par
item : `results/c3_outillage_v2_3/conformite/attendu.md`, committé avec cette entrée. Le run se fait au SHA de ce commit,
après la relecture de Bruno (STOP 1) et son GO de lancement.

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict attendu | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 21 | 2026-09-30 | C3 outillage v2.3, lot 2 — essai d'instrument : `c3b_prefix.py` → `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select` → `c3b_evaluate.py --selection` → `c3_verdict.py chain` (six étapes, neuf entrées), **trois exécutions** (`--workers` 4 / 1 / 4 au préfixe, même `--now`, même chemin absolu), registre **neuf par exécution** ; `--campaign OUTILLAGE_V23_CONF`, étiquette d'instrument (dette 21 intacte) ; **aucune lecture économique, issue non lue** | `grok_grid_atr_adaptive_v4`, 4 paramétrages (classes C1, C2, C5, C6) × `BTC/USDT`, `ETH/USDT`, `SOL/USDT` = **12 candidats** ; famille de test `test-conformite-instrument-2020` (jamais une famille de campagne) ; provenance `unknown` : aucun `validé` atteignable, et la voie du § 10.1 ne s'ouvre pas (aucune évaluation différée inscrite) ; chemin sélection seul, aucune identité, paire, métrique ni issue ne remonte au dépôt | `exchange='binance'`, exécution 5 m, séries 4 h / 1 j / 1 w ; fenêtre de conformité `2020-01-06 → 2020-12-28`, `T = 2020-09-11T21:36Z` ; lectures bornées à `≤ T` (préfixe) et `≤ fin` (évaluation), amorçage `≥ 400 j` avant ; `deferred_evaluation.date = 2021-12-28` (365 j exactement après la fin, une déclaration, jamais une fenêtre lue) ; **hors campagne** (garde-fou 6, `CAMPAIGN_UNLOCK` absent) | branche `feat/c3-outillage-v2.3`, exécuté au commit de cette entrée (code identique à `a30d62a`, `interdits_lot2_S1.out`) ; métriques v2, `replay_version` 2 ; protocole v2.3 `d030ab23…79e6` ; manifeste `24bde67d…565a` | bybit maker 0,10 % / taker 0,25 % ; coûts de `config/pair_costs_b4.json` pour la paire de déploiement USDC (§ A.6) ; `min_order_quote 5.0` (valeur du rejeu, inerte sur le grid) | producteur préfixe 0 ×3 ; chaîne 1-4 autonome 0 ×4 ×3 (l'ancrage admet la date) ; producteur d'évaluation `0 evaluated` ×3 ; chaîne complète : six codes d'étape en 0, `chain.verified` vrai, violations vides, zéro violation au rejeu, ×3 ; **23 artefacts identiques au bit sur les trois exécutions** (booléens seulement, aucun sha d'artefact versionné) ; `alembic` `c3bd1e7a0001` inchangé ; service et collector inchangés ; `validé` et `réfuté` inatteignables par construction (provenance `unknown`) | aucune décision économique ; la conformité v2.3 est, avec la porte § L.5 option 1, la porte du chantier outillage v2.3 ; merge sous décision humaine | `results/c3_outillage_v2_3/conformite/` (`attendu.md`, `manifest.json`, pilote, preuves au commit suivant) ; `results/c3_outillage_v2_3/report.md` |

- **Garde-fou 6, mécanique** : le producteur refuse (code 2) toute fenêtre qui finit après le 2021-03-01 tant que
  `results/c3b_producteur/CAMPAIGN_UNLOCK` n'existe pas. Ce fichier n'existe pas, et ce lot ne le crée pas.
- **Tout lancement est consigné** (`status.txt`). Un écart à l'attendu est un constat : STOP, sans relance ni lecture de
  diagnostic avant l'accord de Bruno. L'issue mesurée sera inscrite dans une section suivante, sans réécrire celle-ci.

### Essais à venir (à inscrire avant lancement)

_(prochain inscrit attendu : **première campagne sous la chaîne C3** — C3b, paquet 2 — après un producteur conforme
(paquet 1, contrat fixé par v2.1) et la décision de reconstruction 1 w. Manifeste gelé, portant le sha256 v2.1, et
inscription ici **avant** tout lancement. C3a est close : entrée 12 ci-dessus ; le rejeu diagnostic grid : entrée 11 ;
l'adoption de v2.1 : section précédente.)_

- **Préalable « producteur conforme (paquet 1) » levé par C3b**, le 28/09/2026.
  - Sources : entrées 15, 16 et 17 ; rapport `results/c3b_producteur/report.md`. Le merge sur `dev` se fait sous
    décision humaine.
  - L'autre préalable, la reconstruction 1 w, l'était déjà par l'entrée 13.
  - Restent avant la première campagne : l'amendement v2.2 et le manifeste gelé. `CAMPAIGN_UNLOCK` est créé à ce
    moment-là.
  - Le paragraphe ci-dessus n'est pas réécrit (ajout seul).
- **Protocole C3 v2.2 adopté le 29/09/2026** (entrée 18). Le manifeste de la première campagne porte le sha256 v2.2 ;
  il suit l'outillage v2.2 (réserves bloquantes pour le manifeste : R-15, R-16, R-18, R-19). Ajout seul.
- **Outillage v2.2 livré et conformité v2.2 prouvée le 30/09/2026** (entrée 19, avec son issue).
  - Les réserves bloquantes pour le manifeste (R-15, R-16, R-18, R-19) et pour la campagne (R-17, R-21, R-22) sont
    outillées.
  - Merge sur `dev` sous décision humaine.
  - Restent avant la première campagne : le manifeste gelé, portant le sha256 v2.2, et le candidat v2.3 de
    l'évaluation différée, à trancher en conversation manifeste (`results/c3_outillage_v2_2/report.md` § 5).
  - `CAMPAIGN_UNLOCK` est créé à ce moment-là, par Bruno. Ajout seul.
- **Protocole C3 v2.3 adopté le 30/09/2026** (entrée 20) : le candidat de l'évaluation différée est tranché (AM-01).
  - Le manifeste de la première campagne porte le sha256 v2.3 (et non plus v2.2) et la clé
    `deferred_evaluation.date`.
  - Il suit l'outillage v2.3 : huit `xfail` strict, X1 à X8.
  - Merge sur `dev` sous décision humaine. Ajout seul.
