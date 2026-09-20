# Chantier 1 — Métriques de backtest fiables (post-audit B4) — v2

> Brief agent. Mode : **plan mode** — proposer un plan détaillé, attendre validation humaine, puis exécuter.
> Branche : `feat/c1-metrics` depuis `dev`. Une tâche, un livrable. Toute découverte annexe → la signaler, ne pas la traiter.

## À lire avant toute ligne de code

1. `CLAUDE.md` (règles d'or, conventions git)
2. `PROJECT_CONTEXT.md` — §5 (fees, mécanisme B4.2), §9 (dettes 2, 13, 14)
3. `skills/backtest.md` (fonctionnement des moteurs, gold runs)
4. `results/B4_2_fees_engine_report.md` (identités comptables établies) et `results/B4_3_chantier0_gate_a.md` (précédent re-baseline de gold hashes)
5. `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` — phase 1, sections 1-2 (défauts de mesure)

## Contexte

B4 est close (tag `v2.8.0-b4-3-campaign`), sélection paper vide — maintenue. Un audit adversarial du
16/09, vérifié indépendamment sur le code et reproduit depuis les JSON de campagne, a établi des défauts
de **mesure**. Ce chantier répare l'instrument, sans toucher à la simulation. C'est le premier de trois
(1 métriques, 2 fidélité du replay, 3 validation chronologique) qui conditionnent toute reprise des runs R&D.

Défauts à corriger (localisations vérifiées sur le tag) :

| # | Défaut | Localisation |
|---|---|---|
| D1 | Sharpe/Sortino = `mean/std × √365` sur des rendements dont le pas varie (5m grid, 4h/1d signal, 1d benchmark) → unités incohérentes entre stratégies et vs benchmarks | `scripts/backtest.py:1028,1037,2605,2613` ; `scripts/compute_benchmarks.py:80,91` |
| D2 | MaxDD% = perte monétaire max ÷ **peak global final** au lieu du peak courant au moment du creux (1000→700→2000→1900 → 15 % au lieu de 30 %) | `scripts/backtest.py:990-993, 2580-2590` |
| D3 | PF calculé sur des P&L de vente qui n'imputent pas la fee d'achat (cost basis = `order_amount − buy_fee`) → PF surestimé. `net_pnl = total_pnl − buy_fees` (L960) corrige déjà globalement : **tout fix du PF qui muterait `t.pnl` déduirait la fee deux fois** | `scripts/backtest.py:940-960` |
| D4 | Agrégation P7 : PF de fenêtre `inf` → coercé à 0 par `_safe_float` (qui coerce aussi `None` → 0), puis moyenne de PF (une moyenne de ratios n'est pas un ratio) | `scripts/p7_report.py:112-122,167,183` |
| D5 | Aucune equity persistée : les dumps contiennent `trades` + `metrics`, pas la courbe → aucun recalcul post-hoc | vérifié sur `results/b4_3_bybit_signal_A_post.json` |
| D6 | Benchmark `dca_fixed` : chaque achat hebdomadaire ajoute des coins à l'equity **sans décompte de cash** — les dépôts sont comptés comme des rendements par `compute_risk_metrics`. Les Sharpes `BENCHMARK_SHARPE` dca (2.37 / 2.10 / 1.93) sont contaminés par construction | `scripts/compute_benchmarks.py:191-215` |

## Objectif

Un **système de mesure unique**, partagé entre les deux moteurs et les benchmarks, spécifié par écrit,
testé sur des trajectoires synthétiques à résultats connus, avec l'equity exportée — et la preuve que la
**simulation est inchangée au centime** (trades, prix, quantités, fees, soldes, equity brute).

## Spec technique

### 1. Export de l'equity

- État actuel (ne pas le changer dans ce chantier) : moteur signal → un point au close de chaque bougie
  **tradeable** (résolution = TF de trading, 4h ou 1d) ; moteur grid → un point par bougie 5m
  (`_record_equity`).
- Nouveau : sidecar par run (JSONL ou Parquet, décision au plan) : `timestamp, cash, inventaire_qty,
  prix_valorisation, equity, flux_externe` (0 pour les moteurs ; champ prévu pour les benchmarks).
  Jamais dans le JSON de résultats de campagne (~26k points par fenêtre grid). Pour la campagne :
  equity **rééchantillonnée quotidienne** embarquée dans le résultat — format exact au plan.
- Documenter la convention de valorisation : mark-to-market au close des bougies traitées.
  **Limitation à écrire noir sur blanc** : cette equity ne capture pas les excursions intrabar (mèches) ;
  un MaxDD « vrai intrabar » est impossible à reconstruire depuis ces données. Extension future
  (borne pessimiste valorisée au low) : **hors scope**, une ligne dans la doc suffit.

### 2. Module de métriques partagé

- Nouveau module dans `src/krakenbot/` (proposition : `src/krakenbot/backtest_metrics.py` — importable
  par `scripts/backtest.py`, `compute_benchmarks.py`, `p7_report.py` sans violer la règle B3
  « pas d'import de `scripts/` depuis `src/` »).
- Entrée : série d'equity horodatée + `starting_balance` + **série de flux externes horodatée**
  (défaut : vide).
- **Rendements ajustés des flux** : `r_t = (E_t − E_{t−1} − F_t) / E_{t−1}`. Implémenté et testé dans ce
  chantier (test synthétique 8). Pour le benchmark `dca_fixed` (D6), **décision au plan** : soit brancher
  ses flux réels dans le module (si l'intégration est triviale), soit conserver le calcul actuel en
  marquant explicitement ses métriques `non_comparable: true` et en dépréciant les constantes
  `BENCHMARK_SHARPE` dca en attendant le chantier 3 (benchmarks synchronisés + benchmark d'exposition).
  **Le statu quo silencieux est interdit.**
- **Rééchantillonnage quotidien** (UTC) → rendements quotidiens → base de : `sharpe_ratio`
  (`mean/std × √365`, `std == 0` ou < 2 points → `None`, jamais un faux 0), `sortino_ratio`,
  `calmar_ratio` (rendement annualisé / `max_drawdown_pct_daily`).
- **MaxDD — deux mesures, toutes deux en drawdown relatif au running peak** :
  - `max_drawdown_pct_daily` : sur l'equity quotidienne. **Celle des critères de sélection et des
    comparaisons benchmark** (seule comparable entre familles dont la résolution moteur diffère).
  - `max_drawdown_pct_engine` : sur l'equity à la résolution du moteur. **Diagnostic dans ce chantier** ;
    jamais critère de sélection inter-familles tant que les résolutions diffèrent ; usage éventuel dans
    le protocole de risque à définir hors chantier.
- **PF net des deux jambes, sans double comptage (D3)** : construire une série **dérivée**
  `pnl_net_trade` (fee d'achat imputée au P&L de la vente correspondante) utilisée **uniquement** par le
  PF et les sommes exportées. `t.pnl`, `net_pnl`, `win_rate`, `average_win/loss` restent sur leur
  convention actuelle, documentée comme telle. À spécifier au plan : allocation de la buy fee au pro-rata
  des quantités clôturées (fermetures partielles), et lots au coût inconnu (liquidation grid,
  `entry_price=None`) → fee imputée 0, documenté.
- **Contrat de sortie** : exporter `gross_profit_net` et `gross_loss_net` (sommes des gains/pertes nets)
  par run et par fenêtre — P7 ne peut pas reconstruire un ratio global depuis des PF. `profit_factor` =
  ratio si pertes > 0, sinon `null`, **désambiguïsé par les sommes** : gains > 0 et pertes = 0 → PF
  infini ; gains = 0 et pertes = 0 → indéfini (0/0). Pas de flag redondant.
- **Contrat consommateur (p7_report)** : `_safe_float` ne coerce plus `None` → 0 pour Sharpe et PF ;
  agrégation None-aware (moyenne sur les fenêtres disponibles avec `n` rapporté ; toutes `None` →
  agrégat `None`) ; PF agrégé = `Σ gross_profit_net / Σ gross_loss_net` toutes fenêtres. Chaque résultat
  porte un champ `metrics_version` ; le mélange ancien/nouveau format est **refusé** (même pattern que la
  clé `fees` de B4.2, `--force` seule échappatoire). Les seuils des critères ne changent pas dans ce
  chantier ; leur ré-interprétation relève du chantier 3.
- Les autres métriques (`total_return_pct`, `win_rate`, `net_pnl`, fees…) sont **inchangées**.

### 3. Conventions exactes — à figer dans le plan avant implémentation

1. Jour du capital initial, journées partielles (bords de fenêtre), jours sans observation →
   proposition : forward-fill de la dernière NAV connue entre premier et dernier point ; à confirmer.
2. Ordre des points à timestamp identique — le point post-liquidation terminale du grid partage le
   timestamp de la dernière bougie : c'est **lui** qui doit compter (les frais de liquidation restent
   dans l'equity finale).
3. Écart-type : population vs échantillon (l'existant mélange : `/n` dans les moteurs, `/(n−1)` dans
   `p7_report._stdev`). En choisir un, partout.
4. Formule Sortino exacte (dénominateur : N total vs N downside ; l'existant utilise N total).
5. Annualisation du Calmar : linéaire (existant) vs géométrique. Trancher et documenter.
6. **Extraction de l'equity de l'ancien moteur pour l'A/B** : harnais de lecture ou instrumentation
   minimale du tag `v2.8.0` (dump de `self.equity_curve` en fin de run), avec démonstration qu'elle ne
   modifie pas le calcul historique. Aucune correction de l'ancien code.

### 4. Tests synthétiques (résultats calculés à la main, dans le test)

1. Trajectoire quotidienne `1000→700→2000→1900` : `max_drawdown_pct_daily == 30.0`, pas 15.
2. **Chute-récupération intra-journée** : equity résolution moteur `100→75→100` dans la même journée
   UTC, closes quotidiens plats → `max_drawdown_pct_daily ≈ 0` et `max_drawdown_pct_engine == 25.0`.
3. Rendements constants → `std == 0` → Sharpe `None` (et l'agrégation None-aware le propage sans le
   transformer en 0).
4. Série courte alternée à Sharpe/Sortino connus, vérifiés à la main (selon les conventions §3.3-3.4).
5. Rééchantillonnage : série 5m sur 3 jours → exactement 3 points quotidiens, bords UTC corrects.
6. PF : trades nets `+10, +10, −5` → `PF == 4.0` ; cas avec buy fees non nulles prouvant l'imputation
   (l'ancien calcul donnerait un autre PF, l'écart est asserté) ; **anti-double-comptage** : sur un run
   synthétique entièrement clôturé, `Σ pnl_net_trade == net_pnl` ; cas 0 perte → `null` + sommes
   désambiguïsantes.
7. Agrégation : fenêtres `[PF fini, PF infini, PF fini]` → l'agrégat par sommes est correct, l'infini ne
   devient jamais 0 ; fenêtres `[Sharpe, None, Sharpe]` → moyenne sur 2 avec `n=2`.
8. **Flux externes** : prix plats + dépôts hebdomadaires → rendements ajustés tous nuls, Sharpe `None`
   (jamais positif). C'est le test qui verrouille D6.

### 5. Rejeux de référence A/B (le cœur de la validation)

- Deux runs déterministes, mêmes données, mêmes commandes que les gold runs : un **signal**
  (référence `b4_3_bybit_signal_A`) et un **grid** (référence grid B4.3).
- Ancien code (tag `v2.8.0-b4-3-campaign`, via le harnais §3.6) vs nouveau, données identiques.
- **Identité stricte exigée** : liste des trades (side, timestamp, prix, quantité, fees), soldes finaux,
  courbe d'equity brute point à point. Le moindre écart ici = bug du chantier, stop et investigation.
- **Partition des métriques dans le tableau avant/après** :
  - doivent rester **identiques** : `net_pnl`, `ending_balance`, `total_return_pct`, `win_rate`,
    comptes de trades, fees totales/achat/vente ;
  - attendues **en mouvement** : Sharpe, Sortino, les deux MaxDD, PF, Calmar — **sens non
    prédéterminé** (la formule relative et le passage au quotidien ont des effets opposés possibles) ;
    chaque écart expliqué par référence à D1-D6.
- Les nouvelles valeurs de référence / gold hashes ne sont approuvées **qu'en review humaine, sur la base
  de ce tableau**. Interdit de recaler un hash sans explication ligne à ligne.

## Interdits / hors scope (explicites)

- Aucune modification de : logique de fill, stratégies, `_build_replay_sequence` /
  `_build_grok_grid_replay_sequence`, seuils des critères P7, fichiers protégés
  (`MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine`).
- Pas de correction du replay grid 5m/4h ni du préenregistrement EMA200 DCA (chantier 2).
- Pas de flag de scénarios de frictions (variantes de `pair_costs_file`, hors chantier).
- Pas de re-run de campagne, pas de modification des JSON de résultats B4 existants.
- Pas de refonte du walk-forward, des fenêtres, ni des benchmarks au-delà du traitement D6 décidé au plan.

## Critère de fin (done)

- [ ] `poetry run pytest -q` vert (suite complète)
- [ ] `poetry run ruff check .` et `poetry run ruff format --check .` verts
- [ ] Les 8 tests synthétiques ci-dessus verts
- [ ] Les 2 rejeux A/B : identité comptable prouvée (script ou test reproduisant la comparaison) +
      tableau métriques partitionné (identiques / en mouvement) avec explication par défaut corrigé
- [ ] Spec des métriques documentée dans `skills/backtest.md` (définitions, conventions §3 tranchées,
      résolutions, limitation intrabar, rôle des deux MaxDD, statut du benchmark dca_fixed)
- [ ] Rapport `results/C1_metrics_report.md` : méthodo A/B, tableau, valeurs de référence approuvées

## Commits attendus (indicatif — l'agent propose au plan)

- `feat(metrics): shared flow-aware metrics module, daily resampling, dual MaxDD`
- `feat(backtest): equity export sidecar + daily equity in results`
- `fix(metrics): derived net-of-fees PF + summed-gains/losses aggregation, None-aware p7_report`
- `test(metrics): synthetic trajectories with hand-computed expectations`
- `docs(backtest): metrics spec + C1 A/B report`
