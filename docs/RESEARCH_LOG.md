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
| 11 | Gates ponctuels BTC : G1 48/48, G2 18/48, G4 31/48 → **16/48** passent les trois. G3 descriptif : 8/48 seulement, il aurait été la contrainte mordante s'il était resté un gate | `effect.json` |
| 11 | Borne d'incertitude : **aucune des 48 configs ne tient `LB_j > 0`** sur les six combinaisons ; `q_FWE` ≈ 5,9-6,25 pp/an contre un meilleur Δ̂ de +1,92. Le meilleur Δ̂ est **sous son propre `se` mono-config** (2,56-2,79) : ce n'est pas la multiplicité qui décide | `effect.json` |
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

### Essais à venir (à inscrire avant lancement)

_(prochain inscrit attendu : **protocole C3** — validation chronologique, equity continue, sélection sur le passé
seul. Le rejeu diagnostic grid est clos : entrée 11 et son issue ci-dessus.)_
