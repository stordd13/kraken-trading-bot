# B4.2 — Modèle de fees maker/taker du moteur de backtest — rapport

> Brief : `agent/AGENT_B4_2_FEES_ENGINE.md`. Branche `feat/b4-2-fees-engine` depuis `dev` @ `10a2df8`
> (tag `v2.6.0-b4-1-binance-restamp`). Plan GATE 1 approuvé par Bruno le 2026-09-14 (plan :
> `.claude/plans/impl-mente-agent-agent-b4-2-fees-engine-silly-tower.md`, 32 agents read-only :
> 5 auditeurs, 2 designs + juge, 8 affirmations × 3 réfutateurs).
> État : **CLÔTURÉ le 2026-09-14** — review Bruno OK, mergé dans `dev` (`3406a6c`, merge `--no-ff` local :
> `gh` non authentifié, comme B4.1), `docs/CODE_MAP.md` régénéré (`fea0e16`), tag `v2.7.0-b4-2-fees-engine`
> sur `fea0e16`, serveur en parité par `git pull --ff-only` **sans restart** (§ 12).

## 1. Résumé

- Le modèle de fees des deux moteurs de `scripts/backtest.py` était choisi sur `exchange` (la **source de
  données**) : `binance` → 0.075 % flat, sinon Kraken. B4.2 le découple : `--fees {bybit,binance,kraken}`
  **obligatoire** partout (CLI, runners P6/P7, walk-forward ; le dashboard passe `bybit`), résolu par le
  registre `ExchangeFees.from_name()` ; `exchange` ne sélectionne plus que les données.
- Le moteur signal appliquait déjà maker (limit) / taker + spread + slippage (market) par type d'ordre
  déclaré ; le `GridBacktester` facturait maker sur ses 6 sites. Les 4 fills de grille **sont** des limit
  reposants (maker, correct) ; les 2 liquidations forcées de fin de run passent en **taker** (sans
  spread/slippage, décision n1). Ces deux sites sont aujourd'hui **inatteignables en production** (§ 3.5).
- Invariant central tenu : à modèle de fees identique (`--fees binance`), métriques **et** liste de trades
  bit-exactes (§ 6).
- Dettes 2 et 9 résolues ; chemins morts supprimés avec preuves ; effet de bord `load_dotenv` à l'import
  supprimé ; suite de tests à 0 échec / 0 error dans trois ordres (§ 7).

## 2. Étape 0 — runs de référence sur HEAD intact (`10a2df8`)

Exécutés en local (tunnel SSH 5433, lecture seule) avec le harnais additif
`scripts/audit/b4_2_reference_capture.py` (commit 1, moteur intouché) :

| Run | Commande (`--exchange binance --interval 5 --capital 1000`) | Fichiers | Résultat |
|---|---|---|---|
| Signal A (= B4.1 invariant 6, run A) | `--strategy grok_supertrend_4h --pair BTC/USDC --start-date 2023-04-01 --end-date 2026-04-01` | `b4_2_ref_signal_A_head.txt`, `b4_2_ref_signal_A_head.json` | **+2.42 %, Sharpe 0.25, PF 1.56, MaxDD 2.17 %, 46 trades (92 fills), fees 3.47 USDC**. Log normalisé **identique** (5 576 lignes) à `b4_reference_backtest_A_p6period.txt` produit sur le **serveur** en B4.1 → déterminisme inter-machines |
| Grid rapide (fenêtre du gold hash) | `--strategy grok_grid_atr_adaptive_v4 --pair BTC/USDC --start-date 2025-03-01 --end-date 2025-03-15` | `b4_2_ref_grid_quick_head.txt`, `.json` | 37 paires, 45 BUY / 37 SELL (tous limit), 0 liquidation forcée, fees 1.55 USDC, +0.17 % |
| Grid période P6 | idem `--start-date 2023-04-01 --end-date 2026-04-01` | `b4_2_ref_grid_A_head.json`, `b4_2_ref_grid_A_head.report.txt` (+ sha256 du log normalisé `d8c8272d…`, log brut de 130 Mo non versionné) | 2 097 fills (1 065 BUY / 1 032 SELL, tous limit), 1 032 paires, +12.95 %, MaxDD 19.70 %, fees 39.60 USDC, 33 positions ouvertes en fin **non liquidées** (0 force-close, 1 032 gagnants / 0 perdant = biais de survie § 3.5) |

- Le grid P6 a été exécuté **deux fois** (déterminisme du chemin grid sur 3 ans, jamais prouvé avant) : les deux
  logs normalisés (326 400 lignes) sont **identiques** (`cmp`), et identiques au run local de la veille du GO.
- ⚠️ La commande littérale du brief (`--days 1095`) couvre une autre période que le baseline ; le run de
  référence officiel est le run A (B4.1 § 4.6).
- Baselines qualité dans ce venv (Python 3.12, poetry) : `mypy src/ --ignore-missing-imports` = **64 erreurs
  / 18 fichiers** (= B4.1 ; le « 35 » du brief est le chiffre B3/CI) ; `ruff check` propre ;
  `ruff format --check scripts/backtest.py` **échouait déjà sur HEAD** (dette préexistante → commit `style`).
- Suite pré-fix (`pytest -q -p no:cacheprovider --ignore=tests/test_scripts/test_run_p6_determinism.py`,
  ordre par défaut, `.env` présent, tunnel ouvert) : **4 failed, 1 189 passed, 6 skipped, 1 error** = les
  3 tests credentials + le gold hash (dérive attendue `32c157cd…` → `abb3a6d8…`) + l'ERROR au teardown.

## 3. Table de classification des sites de fill (GATE 1 a)

### 3.1 Moteur signal (`BacktestEngine`) — 7 stratégies instanciées (:1158-1270)

| Site (dev @ 10a2df8) | Type d'ordre simulé (mécanisme) | Fee correcte | Appliquée avant | Écart | Hypothèse de modèle |
|---|---|---|---|---|---|
| `execute_signal` :557-561 (`is_limit_fill=True`) | LIMIT reposant : `_resolve_fill` :516-527 remplit au `limit_price` si `candle.low <= prix` (BUY) / `candle.high >= prix` (SELL) sur N+1 | maker, spread = slippage = 0 | `fees.maker`, 0, 0 | aucun (seule la **source** du modèle change) | l'ordre n'était pas marketable à la pose (n10) |
| `execute_signal` :562-565 (market) | MARKET à l'open de N+1 (:529-530), prix × (1 ± spread ± slippage) (:628, :698) | taker + spread + slippage | `fees.taker` + `fees.spread` + `fees.slippage` | aucun | — |
| `_execute_short_signal` :839-846 | chemin short/margin | — | — | **mort**, supprimé (§ 4) | — |

Émissions des 7 stratégies (inventaire complet de l'auditeur A2) : toutes les entrées `order_type: limit` à
`prix × 0.999` (non marketables à l'émission) ; sorties SL / trailing / timeout / `regime_shift_bear` /
`supertrend_flip` / `death_cross` / `donchian_lower_break` `order_type: market` ; `grok_adaptive_dca_weekly`
n'a **aucune sortie** ; deux sorties limit : `gemini_scalping_volatilite` TP (:205-213) et
`gemini_retour_moyenne` TP `bb_middle` (:200-208), **émises après que le prix a franchi le niveau** → ordres
limit marketables (taker sur Bybit, ou rejet PostOnly en live) facturés maker par le moteur : hypothèse
conservée en B4.2 (décision n10), consignée pour B4.3. `GeminiGlobalRiskManager` (crash sell market :300)
n'est pas instancié par le backtest. Le moteur signal n'a pas de liquidation de fin de run (position ouverte
valorisée au dernier close sans fee, :1428-1431) → annexe.

### 3.2 `GridBacktester` — 6 sites `fees.maker`, aucun spread/slippage dans ce moteur

| Site | Fonction | Type d'ordre simulé (mécanisme) | Fee correcte | Avant | Après B4.2 | Atteignable |
|---|---|---|---|---|---|---|
| :1882 | `_process_grok_grid_buy_fill` | LIMIT reposant : niveau BUY pending rempli si `candle.low <= price` au prix du niveau (:2180-2184, :1877) | maker | maker | maker ✓ | prod (chemin grok) |
| :1925 | `_process_grok_grid_sell_fill` | LIMIT reposant : cible `position.sell_level` si `candle.high >= price` (:2185-2189) | maker | maker | maker ✓ | prod (chemin grok) |
| :2016 | `_process_buy_fill` | LIMIT, chemin legacy non-grok (:2227-2238) | maker | maker | maker ✓ | **aucun** appelant de prod (`GRID_STRATEGIES = {"grok_grid_atr_adaptive_v4"}` :1638) |
| :2064 | `_process_sell_fill` | LIMIT, legacy (:2240-2251) | maker | maker | maker ✓ | idem |
| :2313 | `_force_close_open_positions` (liste legacy) | **liquidation forcée** de fin de run au dernier close (valorisation, docstring :2295-2302) | **taker** | maker ✗ | **taker** (sans spread/slippage) | tests seulement (`test_grid_metrics.py` pose `_last_close`) |
| :2347 | `_force_close_open_positions` (positions internes grok) | idem | **taker** | maker ✗ | **taker** | **jamais** : `_last_close` n'est écrit qu'au chemin legacy (:2260-2261), le chemin grok fait `continue` à :2215 → `return` (:2305-2306) — § 3.5 |

Mécanisme de la stratégie (`grok_grid_atr_adaptive_v4.py`) : `_emit_grid_signal` :523-557 est l'unique site
d'émission, `order_type: limit` en dur (:543) ; `generate_signal` renvoie `None` ; `_skip_db_sync = True`
(:1818) → le moteur ne consomme aucun signal, les fills dérivent de l'état ; STRONG_BEAR 1w/1d (:364-401)
fait `return` avant la reconstruction de grille — il ne suspend que la (re)construction, **pas les fills**
(les niveaux BUY pending continuent de se remplir et chaque fill pose une cible SELL) ; aucune sortie SL /
crash / market. Preuves complémentaires : `test_grid_atr_v4_bear_protection_mode.py` (pas de vente panique),
636/636 entrées grid de `P7_phase1_cross_validate.json` et 72/72 métriques P6 à `unrealized_pnl: 0.0`.

Réserves de modélisation consignées (réfutateurs C4, rien à changer en B4.2) : ordres appariés pricés sur le
prix de fill (`sell_level = price × (1+spacing)` :586) → après un retournement intrabar > spacing l'ordre
repose du mauvais côté (taker en réel) ; niveaux SELL « nus » de `_build_grid` (:269-280) jamais simulés ;
`_process_grok_grid_sell_fill` facture et mute les soldes avant la recherche de position (:1924-1938) ;
`net_pnl` compte deux fois la fee de vente dans les deux moteurs (`pnl` déjà net :1941/:774, puis
`net_pnl = total_pnl − total_fees` :2380/:998). Toutes en annexe (§ 10).

### 3.3 Conséquences chiffrées

- `--fees binance` : `binance_defaults(use_bnb=True)` lie maker et taker au **même** `Decimal("0.00075")`
  (settings.py:595-598) → maker→taker à :2313/:2347 est bit-exact jusqu'à l'exposant ; ajouter
  spread/slippage à un site grid ne le serait pas (`binance_defaults` garde spread 0.0002 / slippage 0.0001).
- `--fees kraken` : `kraken_defaults()` ≡ `ExchangeFees()` champ à champ (0.0016/0.0026/0.0002/0.0001).
- `--fees bybit` : fills de grille 0.10 %, liquidations forcées 0.25 % (sans effet sur les runs grok tant
  que § 3.5 n'est pas corrigé).

## 4. Chemins morts supprimés (GATE 1 d, f) — preuves

- **Short / rollover** (`_execute_short_signal` :829-965 dont rollover 0.0001/4h :921-925 ; `_is_short_signal`
  :532-538 ; route :552-556 ; branche :1344-1351) : atteint seulement si `metadata["mode"] == "margin"` ou
  `is_short_open`/`is_short_close`. Aucun producteur dans `src/` (lecteurs seulement : `strategies/base.py:423-424`,
  `execution/engine.py:432-648`, chemin live) ; aucune construction de métadonnées par splat ; `strategies.yaml`
  sans `mode`/`margin`. Le commit **`183aba0` (B0.5, 2026-09-08)** a supprimé `bear_short.py`, seul émetteur
  de ces clés et seule classe définissant `add_position`/`close_position` → le chemin aurait levé
  AttributeError (:868/:907). **Rollover mort en spot → supprimé, pas de champ `ExchangeFees` (décision d).**
- **`is_multi`** : littéral `False` :569 (liste repliée par `183aba0`) → terme mort à :598/:695, blocs morts
  :641-648, :683-684, :701-736, :786-787 ; `else`/`elif uses_otf:` promus ; `_entry_regimes` :243 (≠
  `_entry_regime` :244, vivant) supprimé avec le short. Pliage de constante : aucune arithmétique touchée.
- **`_check_directional_pause`** :2113-2128 : zéro appelant, aucun dispatch dynamique ; `_grid_paused` jamais
  `True`, `_hourly_prices` jamais alimenté, `directional_pause_pct` lu seulement par la méthode (absent de
  `strategies.yaml`). Origine `aaaaa55` (grid_adaptive), appelant et feeder supprimés par `183aba0`.
  Les deux gardes `_grid_paused` (:2222-2223, :2253-2255) repliées.
- **Attributs write-only** `atr_multiplier` / `min_spacing_pct` / `max_spacing_pct` :1710-1712 (décision n7).
- Conservés (hors brief) : le chemin grid legacy non-grok (`test_grid_metrics.py` en dépend) → B4.3.
- Vérification contradictoire : C1, C2, C3 soumises chacune à 3 réfutateurs (call graph, entrées dynamiques,
  numérique/historique) → **0 réfutation**.

## 5. dotenv, tests ordre-dépendants, ResourceWarning (GATE 1 g)

### 5.1 Cause racine des 3 échecs credentials

pytest trie les entrées de `tests/` par nom (fichiers et dossiers mêlés) → `tests/test_backtest.py` est le
premier module importé ; son `from backtest import …` exécutait `scripts/backtest.py:22`
`load_dotenv(<repo>/.env)` **à la collecte**, injectant les 29 variables du `.env` local (dont
`BYBIT_API_KEY/SECRET` et `BYBIT_TRADE_API_KEY/SECRET`, non vides) dans `os.environ` pour toute la session.
`_env_file=None` ne désactive que la source DotEnv de pydantic-settings, jamais `EnvSettingsSource` →
`test_settings.py:147` DID NOT RAISE, `:160` échoue (le tuple contient la vraie clé — sortie caviardée ici),
`test_bybit_rest.py:191` DID NOT RAISE. `EXCHANGE_NAME` n'y est pour rien (épinglé par le conftest, exchange
passé en kwarg). Vert en CI faute de `.env` → le fix se prouve en local. Même mécanisme via
`run_p6_backtests.py:35`, `run_p7_grid_search.py:50`, `run_p6_walkforward.py:23` et
`binance_vision_import.py:44` (importé sans bouclier par `test_binance_vision_import.py`).

Prémisses du brief corrigées : `load_dotenv()` nu n'est pas basé sur le CWD (`find_dotenv()` remonte depuis
le fichier du module appelant ; sous install éditable il résout `<repo>/.env` de partout, et ne retombe sur
`os.getcwd()` que sous debugger / `pytest --cov`) ; les workers `spawn` héritent d'`os.environ` du parent
(le `Pool` est créé dans `main()` après le chargement) ; aucune unité systemd ne lance ces scripts.

### 5.2 Fix

- `load_dotenv(Path(__file__).parent.parent / ".env")` déplacé en **première instruction de `main()`** dans
  `backtest.py`, `run_p6_backtests.py`, `run_p7_grid_search.py`, `run_p6_walkforward.py`,
  `binance_vision_import.py` (chemin explicite conservé) ; `dashboard.py` garde l'appel à l'import (il lit
  `get_settings()` et `DATABASE_URL` au niveau module) mais avec le chemin explicite ; `settings.py:931`
  intouché ; commentaire `pyproject.toml` (`E402`) mis à jour.
- Déplacer l'appel est **nécessaire mais pas suffisant** : `runner.main()` est invoqué à l'exécution par
  `test_run_p6_backtests.py`, `test_run_p6_determinism.py` et le gold hash → ré-injection que `monkeypatch`
  ne défait pas ; les victimes ne seraient vertes que par accident d'ordre. **Bouclier autouse
  `monkeypatch.delenv`** dans `tests/conftest.py` pour les 10 credentials (`BYBIT_*`, `BYBIT_TRADE_*`,
  `KRAKEN_*`, `KRAKEN_FUTURES_*`, `BINANCE_*` ; jamais `DATABASE_URL*` ni `EXCHANGE_NAME`) — il rend aussi
  les tests hermétiques à un shell exportant les clés. `test_bybit_rest.py:65-70` : `_env_file=None`.
- Garde de non-régression : `tests/test_scripts/test_scripts_env_purity.py` importe chaque script dans un
  **sous-processus** (seule façon d'observer un import de collecte) et vérifie qu'`os.environ` est inchangé.

### 5.3 `ERROR at teardown` du gold hash — cause racine (caractérisée, différente de l'hypothèse du plan)

Texte littéral (suite complète, pré-fix) :

```
ExceptionGroup: multiple unraisable exception warnings (3 sub-exceptions)
ResourceWarning: unclosed <socket.socket fd=13, family=1, type=1, proto=0>
ResourceWarning: unclosed <socket.socket fd=12, family=1, type=1, proto=0>
ResourceWarning: unclosed event loop <_UnixSelectorEventLoop running=False closed=False debug=False>
```

Ce ne sont pas des transports asyncpg : `family=1` = AF_UNIX = le self-pipe d'une boucle d'événements
**jamais fermée**. `PYTHONTRACEMALLOC=25` localise l'allocation dans **pytest-asyncio 1.3.0**
(`plugin.py:618`, `_temporary_event_loop_policy` → `asyncio.get_event_loop()`) : sans boucle courante,
Python 3.12 en crée une implicitement (`asyncio/events.py:699`) que le plugin garde comme `old_loop` sans
jamais la fermer. Quand le test gold hash (synchrone) appelle `asyncio.run()` (`run_p6_backtests.py:294`),
la boucle courante est remplacée puis mise à `None` ; l'orpheline perd sa dernière référence, est collectée
pendant le test et son `__del__` émet le `ResourceWarning`, converti en ERROR par `filterwarnings = error`
et attribué au test en cours par le plugin unraisable. C'est pourquoi le test « échoue après
`tests/test_backtest.py` (premiers tests async) et passe seul ».

Fix : fixture de session autouse `_session_event_loop` dans `tests/conftest.py` qui crée la boucle courante
du thread principal et la ferme à la fin de la session — plus aucune création implicite, fermeture
déterministe. Preuve : `pytest tests/test_backtest.py tests/test_strategies/test_grid_atr_v4_backward_compat.py
-W error::ResourceWarning` → `1 failed (dérive du hash attendue), 10 passed`, **0 error**. Aucun changement
dans `src/krakenbot/core/database.py` (le `fix(core)` prévu au plan n'était pas justifié).

## 6. Régression iso-fees (validation 7.1) — ✅ bit-exact

Protocole : rejeu des 3 runs de l'étape 0 avec `--fees binance --trades-out`, puis (a) `normalise-log` (retrait du
préfixe horodaté, des codes ANSI et des lignes imprimées par `main()` seulement) et `cmp` byte à byte contre le log
HEAD intact ; (b) `compare` = projection des deux JSON sur les clés du schéma 1 (métriques, `regime_breakdown`,
bloc grid, tous les trades en Decimal pleine précision) et égalité canonique ; (c) `verify-fees --fees binance`
(`fee == fee_base × fee_rate` exact, Σ fee == `metrics.total_fees`). Sorties brutes : `b4_2_validation_outputs.txt`.

| Run | Log normalisé (HEAD vs rejeu) | JSON (schéma 1) | Trades vérifiés |
|---|---|---|---|
| Signal A | **identique**, 5 576 lignes | **identique** | 46 maker + 46 taker-market |
| Grid rapide | **identique**, 4 309 lignes | **identique** | 45 + 37 maker |
| Grid P6 | **identique**, 326 400 lignes | **identique** (2 097 trades) | 1 065 + 1 032 maker |

Le rejeu a été fait après **chaque** commit touchant le moteur : commit 7 (les 3 runs), commits 8 et 9
(signal + grid rapide depuis un `git worktree` de chaque commit), commit 10 (les 3 runs, moteur final) — tous
identiques. Le gold hash `abb3a6d8…` (fenêtre grid 2025-03) est resté identique à H0 dans les trois ordres de la
suite finale. `--fees kraken` est prouvé par égalité champ à champ `from_name("kraken") == ExchangeFees()`
(`.as_tuple()`, tests) — un run HEAD `--exchange kraken` chargerait d'autres données.

## 7. Validations 3 à 6 — ✅

- **7.3 absence de `--fees`** : tests dédiés (`test_backtest_cli.py`, `test_run_p6_backtests.py::TestParseArgs`,
  `test_run_p7_grid_search.py::TestFeeModelPlumbing` (phases 1, 2, report), `test_run_p6_walkforward.py`) +
  invocation manuelle des 4 scripts sans `--fees` → `error: the following arguments are required: --fees`,
  exit 2 (`b4_2_validation_outputs.txt`).
- **7.4 suite complète** (`pytest -q -p no:cacheprovider -W error::ResourceWarning`, `.env` présent, tunnel
  ouvert, gold hash inclus) en **trois ordres** — A défaut, B fichiers inversés, C « victimes d'abord »
  (`test_config/test_settings.py`, `test_connectors/test_bybit_rest.py`, `test_backtest.py`, `test_scripts`,
  `test_strategies`, puis le reste) : **1 300 passés, 6 skipped (intégration Bybit), 0 échec, 0 error** dans les
  trois ; lane déterminisme rapide (`test_run_p6_determinism.py -m "not slow"`, tunnel) : 6 passés. Après le
  seul commit dotenv (avant re-baseline) : 1 214 passés + 1 échec = la dérive attendue du gold hash, 0 error.
- **7.5** `ruff check` et `ruff format --check` propres sur les 28 fichiers `.py` modifiés ; `mypy src/
  --ignore-missing-imports` : 64 erreurs / 18 fichiers = baseline de ce venv (aucune nouvelle ; le « 35 » du
  brief est le chiffre B3/CI d'un autre environnement).
- **7.6** grep de `scripts/backtest.py` vide pour `is_multi`, `_entry_regimes`, `_is_short_signal`,
  `_execute_short_signal`, `rollover`, `is_short_open`, `is_short_close`, `mode.*margin`,
  `_check_directional_pause`, `_grid_paused`, `_hourly_prices`, `directional_pause_pct`,
  `binance_defaults(use_bnb=True)`, `exchange == "binance"`, `add_position`, `close_position` ; repo entier :
  seuls restent les lecteurs live des fichiers protégés (`execution/engine.py`, `strategies/base.py`), les docs
  historiques et `docs/CODE_MAP.md` (régénéré au merge).

## 8. `--fees bybit` trade par trade (validation 7.2) — ✅

Mêmes commandes avec `--fees bybit --trades-out` (moteur final), puis `verify-fees --fees bybit` : chaque entrée
limit est facturée `fee_rate = 0.0010` (maker, `price == reference_price`, spread = slippage = 0), chaque sortie
market `0.0025` (taker) avec `price == reference_price × (1 − 0.0002 − 0.0002)`, `fee == fee_base_usdc × fee_rate`
exact et Σ fee == `metrics.total_fees`. Dumps versionnés : `b4_2_bybit_signal_A.json`, `b4_2_bybit_grid_quick.json`,
`b4_2_bybit_grid_A.json`.

Signal A sous Bybit : **+1.93 %, Sharpe 0.20, PF 1.44, MaxDD 2.30 %, 46 trades, fees 8.11 USDC** (vs +2.42 % /
PF 1.56 / 3.47 USDC sous Binance flat — les sorties market à 0.25 % sont le premier poste de coût, cf. § 5 de
`PROJECT_CONTEXT.md` ; chiffres bruts pour B4.3, sans analyse). Extrait (5 premières entrées et 5 premières sorties,
Decimal exact) :

```
  n side liq    reference_price                  price                fee_base_usdc    rate                          fee  spread    slip
  1 buy  maker      28444.01751            28444.01751                        50.00  0.0010                     0.050000       0       0
  3 buy  maker      30363.34626            30363.34626                        50.00  0.0010                     0.050000       0       0
  5 buy  maker      29792.58759            29792.58759                        50.00  0.0010                     0.050000       0       0
  7 buy  maker      29345.01561            29345.01561                        50.00  0.0010                     0.050000       0       0
  9 buy  maker      30679.41987            30679.41987                        50.00  0.0010                     0.050000       0       0
  2 sell taker   29591.94000000     29580.103224000000 51.94505858813191259352448626  0.0025 0.1298626464703297814838112156  0.0002  0.0002
  4 sell taker   29283.46000000     29271.746616000000 48.15423606308404296411037273  0.0025 0.1203855901577101074102759318  0.0002  0.0002
  6 sell taker   27900.36000000     27889.199856000000 46.75879624751990197975281006  0.0025 0.1168969906187997549493820252  0.0002  0.0002
  8 sell taker   28231.09000000     28219.797564000000 48.03469546771864879577073770  0.0025 0.1200867386692966219894268442  0.0002  0.0002
 10 sell taker   29904.40000000     29892.438240000000 48.66869375023811361267438465  0.0025 0.1216717343755952840316859616  0.0002  0.0002
```

Table side × liquidité (`verify-fees`) : signal A `buy/maker 46`, `sell/taker-market 46` ; grid rapide
`buy/maker 45`, `sell/maker 37` ; grid P6 : `buy/maker 1064` `sell/maker 1031`. Grid P6 sous Bybit : 1 031 paires, +11.59 %, MaxDD 19.99 %, fees 52.74 USDC (vs 1 032 paires,
+12.95 %, 39.60 USDC sous Binance flat : le maker à 0.10 % modifie le net de chaque fill, donc la trajectoire —
chiffre brut pour B4.3). Les runs grid ne contiennent **que** des fills
maker à 0.0010 et **zéro** liquidation forcée (no-op documenté § 3.5) ; le taux taker de ces deux sites est
prouvé par `tests/test_scripts/test_grid_fee_sites.py` (branche legacy et branche grok, première couverture).

## 9. Décisions de gate appliquées

| # | Décision | Appliquée |
|---|---|---|
| d | Rollover / short : supprimés, pas de champ `ExchangeFees` | ✅ commit 10 |
| e | `settings.exchange_fees` = live/paper, documenté, non câblé ; test `test_engines_ignore_settings_exchange_fees` | ✅ commit 7 |
| n1 | Force-close :2313/:2347 → taker, sans spread/slippage | ✅ commit 8 |
| n2 | Bug `_last_close` du chemin grok non corrigé, consigné (les baselines grid B4.2 ont 0 force-close) | ✅ (§ 3.5, § 10) |
| n3 | Gold hash re-baseliné sur `--fees binance` (H0 = `abb3a6d8…`), supersède le report B4.1 | ✅ commit 5, identique après 7-10 |
| n4 | `fee_model` keyword-only requis ; tests → `"kraken"` | ✅ commit 7 (19 constructions) |
| n5 | Chemin grid legacy conservé | ✅ |
| n6 | Reprise : erreur explicite si `fees` absent/différent, `--force` seule échappatoire | ✅ commit 7 (`FeeModelMismatchError`, P6/P7/walk-forward/report) |
| n7 | Attributs write-only supprimés | ✅ commit 10 |
| n8 | `--fees` requis aussi en `--phase report`, validé contre les fichiers | ✅ commit 7 |
| n9 | `delenv` large dans `conftest.py` | ✅ |
| n10 | Sorties limit marketables : maker conservé, hypothèse documentée | ✅ (§ 3.1) |
| n11 | Harnais avant l'étape 0 | ✅ (commit 1) |
| n12 | `--pair-costs-file` JSON, `GridBacktester` refuse `pair_costs` | ✅ commit 9 |
| n13 | 11 commits atomiques | ✅ (12 avec le split docs / artefacts ; le `fix(core)` prévu est devenu `test(conftest)`, § 5.3) |
| n14 | mypy : aucune nouvelle erreur vs 64 dans ce venv | ✅ 64 |

## 10. Annexes consignées (non faites)

- `_force_close_open_positions` inopérant sur le chemin grok (`_last_close` posé seulement au chemin legacy
  :2260-2261) → B4.3 avec le re-baseline ; étendre le gold hash à la liste de trades.
- `net_pnl` double-compte la fee de vente dans les deux moteurs → B4.3 (change les métriques).
- Moteur signal sans liquidation de fin de run (positions ouvertes valorisées sans fee, 100 % du stock DCA).
- Ordres limit marketables facturés maker (n10) ; ordres appariés pricés sur le fill ; niveaux SELL nus jamais
  simulés ; `_process_grok_grid_sell_fill` facture sans trade si position non trouvée.
- `min_profitable = prix × 1.0064` (stratégie :589-592, legacy :2041) calibré Kraken.
- Chemin grid legacy non-grok → nettoyage B4.3 (réécrire `test_grid_metrics`).
- `dashboard.py` : `exchange="kraken"` (:904-909), grid routée vers `BacktestEngine` (:895), `close_db()` hors
  `finally` (:931), `DATABASE_URL` fallback silencieux (:124-125), aucun test.
- `backtest.py --strategy` : défaut `"threshold"` (supprimée), pas de `choices` ; `--exchange` défaut kraken.
- `_build_grok_grid_replay_sequence` :1798-1799 tague les candles de trading `240` quel que soit l'intervalle.
- `load_dotenv` à l'import dans ~11 autres scripts + 3 boucliers `_ENV_BEFORE` à retirer ensuite ;
  `test_bybit_rest_integration.py:49` re-fuit sous `BYBIT_INTEGRATION=1` ; `DatabaseSettings` sans `env_file`.
- `fees` non enregistré dans `backtest_runs` (DB) ; `p7_report` sans modèle (propagation optionnelle).
- `tests/test_config/` sans `__init__.py` ; deux copies divergentes de `_build_grid_settings` ;
  `run_p6_walkforward` sans reprise/sauvegarde atomique ; ancres `CODE_MAP` périmées (+20 lignes sur le bloc
  `GridBacktester`) ; venv 3.12 vs CI 3.11 ; pytest-asyncio 1.3.0 crée une boucle implicite non fermée
  (`plugin.py:618`) — contourné par la fixture de session, à signaler upstream.

## 11. Commits (`feat/b4-2-fees-engine` depuis `dev` @ `10a2df8`)

| # | Commit | Contenu |
|---|---|---|
| 1 | `test(audit): add B4.2 reference capture/compare/verify harness` | `scripts/audit/b4_2_reference_capture.py` + 16 tests purs |
| 2 | `chore(results): B4.2 step-0 reference runs on HEAD-intact engines` | captures § 2, baselines |
| 3 | `fix(scripts): remove import-time dotenv side effect from backtest` | 5 scripts + dashboard, conftest `delenv`, test de pureté |
| 4 | `test(conftest): own the session event loop (ResourceWarning ERROR at teardown)` | cause racine pytest-asyncio, § 5.3 |
| 5 | `test(strategies): re-baseline grid_atr_v4 gold hash on re-stamped data` | H0 = `abb3a6d8…` |
| 6 | `style(backtest): ruff format` | dette de formatage préexistante |
| 7 | `feat(backtest): decouple fee model from data-source exchange (--fees)` | registre, `fee_model` requis, champs d'audit, CLI, runners, dashboard, tests |
| 8 | `fix(backtest): apply taker fees to market exits in GridBacktester` | :2313/:2347 → taker + tests |
| 9 | `feat(backtest): per-pair spread/slippage overrides` | `PairCosts`, `--pair-costs-file`, tests |
| 10 | `refactor(backtest): remove dead is_multi and short/rollover paths` | −255 lignes, grep propre |
| 11 | `docs(project): resolve debts 2 and 9, update backtest skill` | `CLAUDE.md`, `PROJECT_CONTEXT.md`, `ROADMAP.md`, `skills/backtest.md` |
| 12 | `chore(results): B4.2 validation artifacts and report` | ce rapport, `b4_2_validation_outputs.txt`, dumps bybit, `INDEX.md` |

## 12. Clôture (2026-09-14)

| Étape | Résultat |
|---|---|
| Review | OK (Bruno), 12 commits de `feat/b4-2-fees-engine` (§ 11) |
| PR → merge `dev` | `gh auth status` non connecté → merge local `git merge --no-ff feat/b4-2-fees-engine` = **`3406a6c`** (même procédure que B4.1) ; branche poussée sur `origin` pour trace |
| CODE_MAP | régénéré selon la méthode de son en-tête (7 modules touchés + ligne du harnais, totaux src 28 884 / scripts 13 603, point d'attention 5 → ✅ B4.2) : **`fea0e16`** |
| Push | `origin/dev` = `fea0e16` vérifié par `git fetch` + `git rev-parse` ; `feat/b4-2-fees-engine` = `3d0bda5` contenue dans `origin/dev` |
| Tag | `v2.7.0-b4-2-fees-engine` (annoté) → `fea0e16`, poussé, `git ls-remote --tags` le renvoie (objet `b6f94cd`) |
| Zip | `~/Desktop/krakenbot-src-v2.7.0-b4-2-fees-engine.zip` = `git archive HEAD` (374 fichiers, 1.9 Mo, sans `.env`) |
| Serveur | `~/apps/kraken-trading-bot` : `d3d3423` → `fea0e16` par `git pull --ff-only origin dev` ; **aucun restart** : `krakenbot-collector` `active` depuis 2026-09-13 19:54 UTC (inchangé), `krakenbot` `inactive` (attendu jusqu'à B4/B5) |
| CI | pas de run sur `dev` (workflow ciblé `main`, comme noté en B4.1) ; validations locales § 7 font foi |

Aucun code du serveur n'est exécuté par les scripts modifiés (backtests lancés depuis le poste local via le
tunnel) : le pull ne sert qu'à la parité du clone. Prochaine phase : B4.3 (§ 10, nouveaux fichiers de sortie
`--fees bybit`, force-close grok, double comptage `net_pnl`).
