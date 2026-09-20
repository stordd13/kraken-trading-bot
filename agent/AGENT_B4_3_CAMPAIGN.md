# AGENT B4.3 — Chantier 0 (moteur grid) + campagne P6/P7 fees Bybit

> Dernier brief de B4. Deux chantiers séparés par un gate dur : d'abord rendre le
> GridBacktester honnête (chantier 0), ensuite — et seulement ensuite — la campagne
> de re-runs. Mode : **plan mode sur le chantier 0** ; la campagne se lance après
> validation de ses configs au GATE B, puis tourne en autonomie surveillée.
> Point de départ : `dev` @ tag `v2.7.0-b4-2-fees-engine` (+ commit `fix(ci)`).

---

## 0. À lire avant tout (dans cet ordre)

1. `CLAUDE.md` + `PROJECT_CONTEXT.md` (§ 4 risk management, § 5 fees, § 7 stratégies)
2. `results/B4_2_fees_engine_report.md` — **annexes force-close grok et double
   comptage `net_pnl`** (le diagnostic du chantier 0 y est déjà fait) + § runs de
   référence
3. `ROADMAP.md` § B4 (révision risk management) et « Leçons historiques »
   (`min_spacing ≥ 1.5 %` calibré fees Binance)
4. `skills/backtest.md` (post-B4.2 : `--fees`, `--pair-costs-file`, `verify-fees`)
5. `results/P6_backtest_report_v2.md` + `results/P7_phase1_cross_validate.json`
   (baselines historiques — contexte, PAS références comparables)
6. `results/B3_bybit_data_report.md` — trous de données (SOL 455 j en 2022-2023,
   BTC/ETH 164 j) et période commune ETH/SOL (2025-06-27)
7. `skills/deployment.md` (serveur, tmux) — les runs tournent sur le serveur

## 1. Contexte

- Données : 8 712 718 rows Binance **end-stampées** (B4.1, look-ahead éliminé).
  Moteur : fees maker/taker distinctes, `--fees` découplé, overrides par paire
  (B4.2). Fees Bybit : maker 0.10 % / taker 0.25 %.
- Baselines saines post-B4.1/B4.2 : run signal (`grok_supertrend_4h` BTC 1095 j :
  +2.42 %, Sharpe 0.25, PF 1.56, MaxDD 2.17 %, 46 trades, fees flat Binance) et run
  grid de référence (B4.2 étape 0).
- **Aucun classement historique n'est comparable** : P6/P7 = fees flat + données
  open-stampées + grid biaisé. Le rapport final les cite comme contexte, jamais
  comme référence de régression.
- Deux défauts connus du GridBacktester (annexe B4.2) : la liquidation forcée de
  fin de run est **inatteignable** sur le chemin grok (`_last_close` jamais posé)
  → biais de survie (l'inventaire terminal n'est jamais valorisé ni liquidé) ; et
  la fee de vente est **doublement comptée** dans `net_pnl`.

## 2. Objectif

Produire le verdict B4 : quelles stratégies × paires survivent aux fees Bybit sur
données saines, avec un moteur grid honnête — et la sélection paper qui en découle.
Zéro survivant est un résultat acceptable.

## 3. Hors scope — STRICT

- Aucune modification des stratégies elles-mêmes ni des fichiers protégés
  (`MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine`).
  Le chantier 0 touche `scripts/backtest.py` (GridBacktester) uniquement.
- Aucune écriture DB hors tables de résultats (`backtest_runs`) ; `market_data_ohlc`
  intouchable. Collector : ne pas l'arrêter, ne pas le redémarrer.
- Pas de déploiement, pas de push `main`, pas de touche à `deploy.yml`.
- Réévaluation scalping avec données live = P12 ; ML = P11+. Rien ici.
- Toute tâche annexe : consignée, pas faite.

## 4. Chantier 0 — moteur grid (plan mode)

a) **Liquidation forcée atteignable.** Sémantique validée : à la fin du replay,
   l'inventaire terminal est liquidé en **MARKET** au dernier close disponible du
   pair → fee **taker** + spread + slippage, trades marqués `forced_liquidation`
   dans la sortie. Le fix rend le chemin atteignable sur le chemin grok (poser ce
   qui manque, `_last_close` ou équivalent — diagnostic annexe B4.2 à l'appui).
b) **Fix du double comptage** de la fee de vente dans `net_pnl` (annexe B4.2).
c) **Tests** : les deux fixes couverts (inventaire terminal non vide → liquidé en
   taker ; `net_pnl` = brut − fees comptées une fois), plus un test « inventaire
   vide → aucun trade de liquidation ».
d) **Garde d'isolation : le moteur signal est intouché.** Le run de référence
   signal (B4.2 étape 0) rejoué post-chantier 0 reste **bit-exact**. Tout écart =
   STOP.
e) **Nouveau run de référence grid** (même config que B4.2 étape 0, `--fees
   binance` pour isoler l'effet des fixes) : les deltas sont expliqués et **signés**
   — PF et return doivent baisser ou l'inventaire terminal être démontré vide sur
   cette config ; un delta positif inexpliqué est un red flag → STOP. Versionné
   dans `results/`.

### ⛔ GATE A — STOP
Fixes + tests + garde d) verte + deltas e) expliqués, soumis à Bruno.
**Aucun lancement de campagne avant le GO.**

## 5. GATE B — configs de campagne (avant tout run)

Soumettre en un document court :

1. **Coûts** : `--fees bybit` partout ; fichier `--pair-costs-file` avec les
   spread/slippage **par paire issus du summary q3** (mesures diurnes + nocturnes
   01:00–03:00 UTC — fournies par Bruno au gate ; BTC restera probablement au
   défaut, ETH/SOL au-dessus). Valeurs arrondies au conservateur.
2. **Risk backtest-visible** : cartographie de ce que le moteur simule réellement
   (sizing, plancher de position, budgets) vs ce qui est runtime pur (max
   positions global, daily loss). Proposition : plancher min position 5-10 USDC et
   tout paramètre de sizing simulé intégrés aux runs ; le runtime pur documenté
   pour la config paper B5, pas simulé. Aucun paramètre risk changé sans ce
   mapping.
3. **Grilles P7** : identiques à P7 phase 1 **sauf** le plancher de spacing du
   grid, recalculé pour les fees Bybit (round-trip maker/maker 0.20 %,
   limit/market 0.35 % — vs 0.15 % Binance qui justifiait le 1.5 %). Proposition
   chiffrée avec le raisonnement de couverture des coûts par cycle.
4. **Exécution serveur** : workers (proposition : 3 sur 4 vCPU, le collector garde
   le sien), `nice`, tmux, estimation de durée P6 puis P7 (benchmark P6.7 comme
   base), espace disque vérifié, fenêtre de lancement.
5. **Sorties** : nouveaux fichiers (`results/B4_P6_*`, `results/B4_P7_*`), statut
   séparé. Les fichiers legacy sans clé `fees` sont refusés par la reprise —
   **jamais de `--force` sur un fichier legacy**.

### ⛔ GATE B — STOP
GO explicite de Bruno sur les 5 points avant le premier run.

## 6. Campagne

Dans l'ordre, chaque bloc terminé avant le suivant :

1. **P6** : 24 combos (8 stratégies × 3 paires), 5 critères stricts, sur données
   Binance end-stampées, coûts du GATE B. Puis filtres survivants + walk-forward
   sur les survivants (pipeline existant).
2. **P7** : grid search phases 1-2 + rapport, sur les stratégies survivantes de
   P6 (si aucune ne survit : P7 tourne quand même sur les 4 stratégies
   historiques du grid search — le rapport doit pouvoir dire si une *config*
   sauve une stratégie que sa config par défaut condamne).
3. **Rapport** `results/B4_bybit_backtest_report.md` :
   - verdict par combo (critères, PF, ratio test/train, nb trades, cohérence
     entre paires — jamais le Sharpe seul) ;
   - comparaison qualitative avec P6/P7 historiques (contexte uniquement, avec
     l'encadré « pourquoi non comparables » : fees, re-stamp, fixes grid) ;
   - couverture données par paire dans chaque fenêtre (le trou SOL 2022-2023
     rend « 3+ ans » faux pour SOL : le dire chiffré, pas le masquer) ;
   - résultats trop beaux ou incohérents entre paires = suspecter un bug AVANT
     d'accepter les chiffres, investigation consignée ;
   - **sélection paper** explicite : stratégies × paires × configs retenues, ou
     constat d'échec argumenté ;
   - révision risk : valeurs retenues pour la config paper B5 (backtest-visible
     testé vs runtime documenté).

## 7. Validation (critère de fin)

1. Chantier 0 : tests verts, garde signal bit-exacte, deltas grid signés.
2. Campagne complète : P6 24/24 terminés (résumés d'échec inclus), walk-forward
   sur survivants, P7 phases 1-2 + rapport générés sans `--force` sur du legacy.
3. Rapport final complet + sélection paper (éventuellement vide, argumentée).
4. Suite de tests : 0 échec, 0 error (état B4.2 préservé) ; `ruff` propre ; mypy
   non dégradé.
5. Serveur rendu propre : tmux fermés, pas de process orphelin, collector actif
   sans interruption sur toute la durée (le vérifier), disque OK.

## 8. Commits attendus (branche `feat/b4-3-campaign` depuis `dev`)

- `fix(backtest): make grid terminal liquidation reachable (taker market close)`
- `fix(backtest): count sell fee once in grid net_pnl`
- `test(backtest): grid terminal inventory and fee accounting`
- `feat(scripts): b4 campaign configs (pair costs, spacing grid, outputs)`
- `docs(results): B4 bybit backtest report and paper selection`

PR vers `dev` après le STOP final. Jamais de push `main`, jamais de `.env` commité.

## 9. Garde-fous absolus

- Le chemin signal du moteur ne change pas d'un bit (garde 4.d). Les métriques
  grid changent **une fois**, au chantier 0, avec explication — pas pendant la
  campagne.
- Aucun run de campagne avant GATE B. Aucune grille ni coût modifiés après GATE B
  sans re-gate.
- Résultat aberrant (dans un sens ou l'autre) : STOP + investigation avant de
  continuer la campagne, pas après.
- « Fini » ≠ mergé ≠ poussé ≠ taggé : chaque étape vérifiée.

### ⛔ STOP final
Rapport + sélection paper → review humaine. Clôture standard (review → merge →
CODE_MAP → push vérifié → tag `v2.8.0-b4-3-campaign` → zip). B4 est alors close ;
la suite est B5 (paper) + P8 (Telegram), qui ont leurs propres prérequis
(deploy.yml à découpler, secrets GitHub, backup récurrent, clés API 2026-12-08).
