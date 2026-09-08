# AGENT B0.5 — Refonte docs + cleanup repo (post-pivot Bybit EU)

> Mode : **Plan mode**. Propose d'abord un plan détaillé (liste exacte des fichiers créés /
> modifiés / supprimés, par commit), attends la validation humaine, puis exécute.
> Branche : créer `feat/b05-docs-cleanup` depuis `dev` à jour.
> Ne JAMAIS toucher : `MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine`.

---

## 1. Contexte (lire avant tout)

Lire dans cet ordre :
1. `PROJECT_CONTEXT.md` (état avril 2026, à refondre — c'est un des livrables)
2. `results/bybit_integration_audit.md` (rapport B0, verdict GO)
3. `ROADMAP.md` + `CODE_MAP.md`

État réel au 7 septembre 2026 (fait foi sur les docs existantes) :

- **Binance a suspendu ses services UE le 1er juillet 2026** (retrait demande MiCA).
  Pivot décidé : **Bybit EU** (Bybit EU GmbH, MiCA via FMA Autriche).
  Fees vérifiées sur le compte : **maker 0.10 %, taker 0.25 %** (spot).
  Instance séparée : `api.bybit.eu` / `stream.bybit.eu`, filtres de lot propres,
  ~15 mois d'historique. Quote conservée : USDC.
- **Décision backtest** : données Binance existantes (8.7M rows, 2021→2026-06) + modèle
  de fees Bybit. Justifié par B0 : corrélation prix 0.999999, zéro biais. Spread 0.02 %,
  slippage 0.02 %.
- **P6 terminé** (sélection 24 combos, fees Binance). **P7 phase 1 terminée** le 30 mai
  (212 jobs de grid search cross-validé, fees Binance, `results/P7_phase1_cross_validate.json`).
  Verdict : machinerie réutilisable, **classements non transposables** aux fees Bybit
  (maker/taker asymétriques vs 0.075 % flat) → tout est rejoué en B4.
- **Serveur Hetzner** : services `krakenbot` / `krakenbot-collector` stoppés ET désactivés
  (systemd). DB backupée le 7 sept (203 Mo, rapatriée). Le serveur redémarrera en B2/B3
  avec le connecteur Bybit.
- **Phases à venir** : B1 (REST Bybit) → B2 (WS) → B3 (data/collector) → B4 (re-run
  P6 + P7 avec fees Bybit maker/taker) → B5 (paper 4+ sem) → P10 (live).

## 2. Objectif

Deux buts, dans cet ordre de priorité :

1. **Économie de tokens** : réduire drastiquement ce qu'un agent (ou Claude chat) doit
   charger pour travailler sur le projet. CLAUDE.md devient un routeur court ; le détail
   vit dans les skills, chargés à la demande.
2. **Cohérence** : un lecteur froid qui ouvre le repo comprend l'état Bybit sans lire
   l'historique Kraken→Binance. Plus aucune doc qui contredit une autre.

**Interdit** : tout changement de code fonctionnel. Les dettes techniques identifiées
(section 6) sont **documentées**, pas fixées — elles appartiennent à B1/B4.
Seule exception : les **suppressions** de la section 4 (code mort).

## 3. Livrables docs

### 3.1 `CLAUDE.md` — refonte en routeur court

Cible : **< 120 lignes**. Contenu :
- Le projet en 2 phrases (bot multi-pair BTC/ETH/SOL sur USDC, **Bybit EU**, Hetzner)
- Table de routage : type de tâche → skill à lire (`skills/*.md`)
- Les ~10 règles d'or absolues (Decimal, structlog, filtre exchange via
  `settings.exchange_name`, batch SQL 1000, paper avant live, fichiers protégés,
  jamais de commit `.env`, lire le code avant d'écrire)
- Commandes essentielles (pytest, ruff, backtest, lancement bot/collector) — bloc court
- Pointeur : « état du projet → `PROJECT_CONTEXT.md` ; où est quoi → `CODE_MAP.md` »

Tout le reste (conventions détaillées, patterns stratégies, leçons opérationnelles,
accès DB/SSH) **migre dans les skills**. Zéro duplication entre CLAUDE.md et les skills.

### 3.2 `PROJECT_CONTEXT.md` — mise à jour Bybit

Réécrire avec l'état de la section 1. Structure conservée. Points obligatoires :
- Section fees : tableau Bybit EU maker 0.10 / taker 0.25, round-trip limit/limit 0.20 %,
  limit/market 0.35 %. **Supprimer** les fees Binance comme référence courante (les garder
  une ligne, contexte historique des backtests).
- DB : ajouter `exchange='bybit'` comme valeur cible, noter que les 8.7M rows Binance
  restent la base de backtest. Noter le backup du 7 sept et la procédure de restore
  TimescaleDB (section 6.3).
- Historique du projet : condenser Kraken→Binance→Bybit en un paragraphe. Le détail
  du pivot vit dans `PIVOT_BYBIT_PLAN.md` et le rapport B0.

### 3.3 `ROADMAP.md` — phases B

- Archiver P0–P7 en tableau compact (une ligne par phase, tag, verdict).
- Phases B0 (✅) → B0.5 (cette tâche) → B1–B5 → P10, avec livrables et critères.
- Reporter les décisions tranchées de `PIVOT_BYBIT_PLAN.md` (données Binance + fees
  Bybit, USDC, PostOnly en entrée, B4 prérequis absolu avant paper).
- Items non bloquants : ajouter « backup DB récurrent (cron + rotation, storage box) »
  et « OKX Europe = option au palier 20k ».
- `PIVOT_BYBIT_PLAN.md` : déplacer vers `docs/archive/` une fois son contenu absorbé.

### 3.4 `skills/` — refonte

- Passer chaque skill existant : virer les références Kraken/Binance obsolètes,
  pointer vers `settings.exchange_name`.
- `skills/database.md` : ajouter la procédure de **restore TimescaleDB**
  (`timescaledb_pre_restore()` / `pg_restore --no-owner` / `timescaledb_post_restore()`,
  même version majeure d'extension) et la localisation des backups.
- `skills/deployment.md` : état systemd actuel (services désactivés), SSH, procédure
  de réactivation prévue en B2/B3.
- Créer `skills/bybit.md` : constantes B0 (endpoints `.eu`, `load_markets()` obligatoire
  sur ce host, filtres de lot, `priceLimitRatioX` à lever en B1, PostOnly), pointeur
  vers le rapport B0.

### 3.5 `results/` — index + archivage (liste explicite, validée par l'humain)

Créer `results/archive/` et `results/INDEX.md` (une ligne par fichier conservé : date,
phase, verdict, pourquoi il est encore là). Ne **supprimer** aucun fichier — archiver.

**Restent dans `results/`** :
`bybit_integration_audit.md`, `P7_phase1_cross_validate.json`, `P6_backtest_report_v2.md`,
`P6_phase_d_results.json` (données brutes, baseline de comparaison fees en B4),
`P6_benchmarks.json`, `P6_data_coverage.md`, `P6_7_multiprocessing_benchmark.md`
(tuning runner pour B4), `P6_phase_e_survivors.json` et `P6_phase_f_walkforward.json`.

Note obligatoire dans INDEX.md : les deux derniers contiennent `{}` — c'est **normal**,
0 combinaison sur 24 a passé les critères P6 (cf. rapport v2), donc zéro survivant et
pas de walk-forward. Ce ne sont pas des fichiers corrompus.

**Partent dans `results/archive/`** (tout le reste) :
`P6_backtest_report.md` (v1), `P6_phase_d_results_v1.json`, `P6_5_diagnostic_dca.md`,
`P6_5_diagnostic_gemini.md`, `P6_5_diagnostic_grok_trend.md`, `P6_5_grid_fix_verification.md`,
`P6_phase_e_filtering.md`, `cicd_fix_results.md`, `dca_fix_results.md`,
`fix_dca_cleanup_results.md`, `lint_report.md`, `cleanup_report.md`,
`consolidation_results.md`, `test_report.md`, `telegram_alerts_results.md`,
`paper_trading_debug.md`, `backtest_phase1a_results.md`, `backtest_multipair_results.md`,
`backtest_new_strategies_results.md`, `audit_p0_results.md`, `kraken_futures_audit.md`,
`kraken_futures_integration_results.md`, `binance_integration_audit.md`
(pivot Binance obsolète — le garder en archive, il documente pourquoi on a les 8.7M rows).

`docs/archive/` et `notebooks/` : ne pas toucher (déjà propres).

## 4. Cleanup code — suppressions uniquement

À supprimer (stratégies legacy top-level, toutes `enabled: false`, hardcodent XBT/USDC,
listées dans CODE_MAP) :

- `src/krakenbot/strategies/threshold_rolling.py`
- `src/krakenbot/strategies/adaptive.py`
- `src/krakenbot/strategies/capitulation.py`
- `src/krakenbot/strategies/bear_short.py`
- `src/krakenbot/strategies/trend_following.py`
- `src/krakenbot/strategies/grid_spot.py`
- `src/krakenbot/strategies/grid_adaptive.py`
- `src/krakenbot/strategies/grok_supertrend_short_4h.py` (dépend de Kraken Futures, jamais validé)
- `src/krakenbot/connectors/kraken/futures.py` + `src/krakenbot/connectors/base_perps.py`
  (seul consommateur : la stratégie ci-dessus — vérifier par grep qu'aucun autre import
  n'existe avant de supprimer)

Nettoyer toutes les références : `main.py` (`STRATEGY_REGISTRY:75-85` + imports),
`strategies.yaml`, tests associés, `scripts/test_kraken_futures_demo.py`.

**À proposer dans le plan, décision humaine avant suppression** :
- `grok_ichimoku_cloud_4h.py` et `grok_vwap_trend_4h.py` (KILL 1B, hors registre router)
- `scripts/fetch_ohlc.py` et `scripts/backfill_historical_data.py` (Kraken legacy)

**À NE PAS supprimer** : `gemini_scalping_volatilite.py` et `gemini_retour_moyenne.py`
(KILL 1A mais réévaluation planifiée en P12 avec fees réelles), `connectors/kraken/rest.py`
et `ws.py` (référence paper mode + `normalize_asset_*` importés par `execution/`),
les données `exchange='kraken'` en DB.

### `.gitignore`

Vérifier/ajouter : `.env*` (sauf `.env.example`), `logs/`, `*.dump`, `results/archive/`
exclu ou non selon choix humain (proposer dans le plan), caches Python/pytest/ruff/mypy.

## 5. CODE_MAP

Régénérer `CODE_MAP.md` **après** les suppressions (même méthode que l'en-tête actuel :
`wc -l` + grep des symboles). Mettre à jour l'en-tête (date, tag, branche).

## 6. Dettes techniques à documenter (PAS fixer)

À consigner dans `PROJECT_CONTEXT.md` (section « Dettes connues ») et/ou la roadmap :

1. **`settings.exchange_name` default `"kraken"`** (`config/settings.py:687`).
   Incident du 7 sept : au reboot du serveur, les services ont redémarré sur Kraken
   (le `.env` serveur ne fixait pas la variable). À fixer en B1 : default → erreur
   explicite si non défini, ou default `bybit`.
2. **`scripts/backtest.py` : fees flat** (:227, :1837). B4 exige maker et taker
   **distincts** (sorties SL/trailing/timeout = MARKET = taker 0.25 %). Prérequis B4,
   à faire en B1 ou en ouverture de B4.
3. **`TaskScheduler` hardcode `KrakenRestClient`** (:84). À généraliser via factory en B3.
4. **Restore TimescaleDB** non trivial (voir 3.4) — documenté dans `skills/database.md`.
5. **Backup DB récurrent** absent — item roadmap, requis avant B5 (paper).
6. **~97 erreurs mypy `union-attr`** dans `main.py` — devraient mécaniquement baisser
   avec la suppression des imports legacy ; noter le nouveau compte.

## 7. Validation et critères de fin

- `poetry run pytest -q` vert (le compte de tests baissera avec les suppressions — normal,
  mais **zéro test cassé** sur le code conservé)
- `poetry run ruff check .` propre
- `poetry run python -m krakenbot --help` (ou import de `main.py`) ne crashe pas
  post-suppressions
- `grep -ri "threshold_rolling\|grid_spot\|bear_short\|capitulation\|KrakenFuturesClient"
  src/ scripts/ strategies.yaml` → zéro résultat (hors docs/archive)
- CLAUDE.md < 120 lignes, aucune info dupliquée entre CLAUDE.md et skills
- CODE_MAP régénéré et cohérent avec l'arbre réel

## 8. Commits attendus (atomiques, dans cet ordre)

1. `refactor(strategies): remove legacy Kraken-era strategies and futures connector`
2. `docs(claude): rewrite CLAUDE.md as short router to skills`
3. `docs(skills): update skills for Bybit EU, add bybit.md and TimescaleDB restore`
4. `docs(context): update PROJECT_CONTEXT and ROADMAP for Bybit pivot, archive PIVOT plan`
5. `docs(results): add INDEX.md, archive stale reports`
6. `chore(gitignore): tighten ignores (env, dumps, logs, caches)`
7. `docs(codemap): regenerate CODE_MAP post-cleanup`

Merge : PR `feat/b05-docs-cleanup` → `dev`. Pas de merge direct sur `main`.
