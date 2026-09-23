# C3a — preuves de la porte pré-merge § L.5 (rejeu de déterminisme sur serveur au SHA livré)

> `docs/protocole_c3.md` § L.5 exige l'une de deux conditions. L'option 2 (diff de contrôle vide sur les chemins que
> les tests exercent) n'est pas disponible : `git diff --stat f585e8b 6f7ed8e -- <chemins § L.3>` = `pyproject.toml`
> seul (bloc `extend-exclude` de Ruff). D'où l'option 1 : les **24 tests de déterminisme full-range sur le serveur**,
> au SHA livré, recette de C2 (`results/c2_replay/determinism_server/README.md`) reproduite à l'identique — avec,
> cette fois, les **pilotes versionnés** à côté de leurs journaux (`run24.sh`, `checks.sh`, `suite_rerun.sh`,
> `ast_bytecode_check.py`), trou de reproductibilité de C2 relevé par Bruno.

## Conditions (identiques à C2)

- **Checkout isolé** `~/c3a-determinism/repo` sur le serveur, HEAD **détaché** sur le SHA testé ; jamais l'arbre du
  service (`~/apps/kraken-trading-bot`) ni son virtualenv. Transport des 59 commits de la branche par `git bundle`
  (`v2.10.0-c2-replay..feat/c3a-protocole`, sha256 `0203330ab54bc35a…`) fetché dans un clone GitHub :
  `origin/feat/c3a-protocole` était resté à `5e056e0`, et rien ne devait être écrit sur `origin` avant le GO de merge.
- **Venv propre à ce répertoire** (`POETRY_VIRTUALENVS_IN_PROJECT=true`, `.venv` local), dépendances **verrouillées**
  par `poetry.lock` (`poetry install`, rc 0 — Python 3.12.3, pytest 9.0.2, ruff 0.14.13, mypy 1.19.1).
- `.env` **copié** depuis l'arbre du service, jamais modifié ; base en accès **local** (aucun tunnel, aucun port 5433).
- Parallélisme laissé à ce que le test impose (`--workers 2`), processus en `nice -n 5`, machine à 4 cœurs.
- **Aucun** merge, déploiement, `systemctl`, modification du `.env` serveur ni `workflow_dispatch`.
- Une invocation `pytest` **par combo**, un rapport JUnit par combo, **arrêt immédiat au premier échec** (`run24.sh`
  sort en 2 et `checks.sh` ne démarre pas) ; chaque pilote refuse de tourner sur un autre SHA que celui attendu.
  L'arrêt n'a pas servi. **Les 24 tests de déterminisme ne sont jamais relancés** ; la suite hors déterminisme l'a été
  une fois, pour l'incident de nettoyage asynchrone décrit plus bas, comme en C2.

## `run_6f7ed8e/` — rejeu au SHA livré

**SHA testé : `6f7ed8e99191a795a42ca3a8ce253407d963e546`** (`git describe` = `v2.10.0-c2-replay-59-g6f7ed8e`, tip de
`feat/c3a-protocole`, 59 commits après `v2.10.0-c2-replay` ; `sha256sum docs/protocole_c3.md` =
`9b62915069e59e9b0f35120c60a77f48a72b278aa9102b3096dfcb8dc25e23c2`, gel `d931293`) · fenêtre des 24 combos
**2026-09-22 20:54:39Z → 22:04:23Z** (69 min 44 s) · checks 22:04:23Z → 22:16:34Z · relance de la suite
22:18:49Z → 22:25:40Z (`suite_rerun.sh`).

| Fichier | Commande exacte | Résultat |
|---|---|---|
| `run24.sh` | le pilote, versionné : boucle sur les 24 combos, horodatage et durée de chacun, arrêt au premier échec, SHA attendu asserté | — |
| `combo0.xml` … `combo23.xml` (+ `comboN.log`) | `nice -n 5 poetry run pytest -p no:cacheprovider -q --durations=0 --junitxml=combo$N.xml "tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[combo$N]"` pour `N` de 0 à 23 | agrégat **tests=24 failures=0 errors=0 skipped=0** |
| `run24.log` | journal du pilote `run24.sh` | `ALL 24 DONE` ; durées 38 s → 406 s par combo, profil identique à C2 (`run2_f585e8b/run24b.log`) |
| `checks.sh` | le script des vérifications, versionné : chaque commande imprimée avant son bloc | — |
| `ast_bytecode_check.py` | preuve d'équivalence exécutable d'un module à deux révisions (AST puis bytecode, docstrings retirés) | — |
| `checks_6f7ed8e.log` | journal horodaté de `checks.sh` au SHA livré : `git status`, sha256 du protocole, diffs de contrôle (`2b62530..HEAD` sur `src tests config pyproject.toml poetry.lock` **vide** ; sur `scripts` = `c3_verdict.py` seul ; `f585e8b..HEAD` § L.3 = `pyproject.toml` seul), preuve AST/bytecode, **première passe de la suite (l'incident, sortie complète)**, 6 tests courts, gold hashes, 806 tests C3, `ruff check`, `ruff format --check` (`.` puis fichiers suivis `--force-exclude`), `mypy src/` avec et sans `--ignore-missing-imports`, innocuité | voir ci-dessous |
| `suite_run1_async_cleanup_incident.xml` | `nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml=suite.xml --ignore=tests/test_scripts/test_run_p6_determinism.py` (première passe, 22:04:29Z, renommée) | **tests=2621 failures=2 errors=1 skipped=6** — l'incident ci-dessous |
| `suite_rerun.sh` | le pilote de la relance, versionné : même commande que `checks.sh`, puis les deux fichiers victimes seuls | — |
| `suite.xml` | même commande, relance unique (`suite_rerun.sh`) | **tests=2621 failures=4 errors=1 skipped=6 — **non verte**, même classe (incident ci-dessous)** |
| `suite_rerun.log` | journal de `suite_rerun.sh` : relance de la suite, puis `tests/test_main.py` seul (1 failed / 15 passed / 2 errors) et `tests/test_scripts/test_b4_campaign_configs.py` seul (30 passed) | relance **non verte** ; incident **reproductible seul** (contrairement à C2) ; cause identifiée ci-dessous |
| `short.xml` | `nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml=short.xml -k "not full" tests/test_scripts/test_run_p6_determinism.py` | **tests=6 failures=0 errors=0 skipped=0** (les 6 de la fenêtre courte, 24,5 s) |

Au même SHA (journal `checks_6f7ed8e.log`) : `test_grid_atr_v4_backward_compat.py` **2 passés**, 806 tests C3
**806 passés** (226,8 s), `ruff check` propre, `ruff format --check` **12 fichiers à reformater / 262 formatés** (même
liste avec `.` et avec les fichiers suivis `--force-exclude` ; aucun fichier C3a — les 12 sont la dette 10 élargie par
le rejeu grid mergé dans `dev` le 20/09, préexistants à l'identique sur `dev`, `scripts/audit/rejeu_*.py`,
`tests/test_scripts/test_rejeu_*.py`, `scripts/p6_5_diagnose_*.py`), `mypy src/` **65** puis **64** avec
`--ignore-missing-imports` (la 65e est `src/krakenbot/ml/features/feature_store.py:32 — Library stubs not installed
for "pandas" [import-untyped]`, exactement le delta).

**Preuve AST/bytecode (`ast_bytecode_check.py`, sortie dans `checks_6f7ed8e.log`).** `acaeaf6`, dernier commit qui
touche `scripts/`, modifie `scripts/audit/c3_verdict.py` (+20/−6) : docstring de module, docstring de `decide()`, un
commentaire de `run_verdict`. AST hors docstrings et bytecode de module **identiques** entre `2b62530` (archive
`48-g2b62530` des reproductions Fin) et `6f7ed8e` (`AST without docstrings identical : True`, `module bytecode
(co_code) identical : True`, rc 0 ; sha256 des AST `d204fb994f133f4f` des deux côtés). C'est la ligne corrigée de la
décision humaine (rapport § 14.1).

## L'incident de la première passe de la suite, conservé et décrit tel que le XML le montre

La première passe de la suite hors déterminisme (dans `checks.sh`, sortie complète dans `checks_6f7ed8e.log`) a rendu
**2 failed, 2 612 passed, 6 skipped, 1 error** en 414 s. Les trois sont la classe d'incident déjà consignée en C2
(`run1_835ffe2/suite_run1_teardown_incident.xml`) : des objets asynchrones (`aiohttp.ClientSession`, résolveur DNS
`pycares`/`aiodns`) survivant à la fin du test qui les a créés, ramassés par le GC pendant un autre test et remontés
par le hook `unraisableexception` de pytest. Aucun des trois ne porte d'`AssertionError` :

| Test | Phase | Signal porté par le XML |
|---|---|---|
| `tests/test_main.py::TestKrakenBotStop::test_stop_handles_component_errors` | **setup** (erreur ; le corps n'a pas tourné) | `ResourceWarning: Unclosed client session` (`aiohttp`) → `PytestUnraisableExceptionWarning` — **même test, même phase, même signal qu'en C2** |
| `tests/test_main.py::TestKrakenBotStart::test_start_subscribes_1m_when_router_crash_protector_is_configured` | call (failed) | callback `_addrinfo_cb` de `pycares`/`aiodns` sur une boucle fermée (`RuntimeError: Event loop is closed`) — même test qu'en C2, au teardown là-bas |
| `tests/test_scripts/test_b4_campaign_configs.py::TestEngineMinOrder::test_order_below_floor_is_skipped_and_default_keeps_it` | call (failed) | `ExceptionGroup: multiple unraisable exception warnings (5 sub-exceptions)`, les cinq étant des `ClientSession` non fermées venues de `test_main.py` ; le journal capturé montre le corps allé au bout (achat sauté sous le plancher, puis exécuté au plancher par défaut) — victime de passage, comme `TestKrakenBotStats` en C2 |

Chemin de bibliothèque que C3a ne touche pas : `src/` est identique à `f585e8b` (§ L.3), SHA auquel la même suite
avait rendu 1 514 passés / 0 erreur (`run2_f585e8b/suite.xml`). Traitement identique à C2 : le XML de la première
passe est conservé sous un nom qui l'annonce, la suite est relancée **une fois** (`suite_rerun.sh`, jamais les 24
combos), et les deux fichiers victimes sont rejoués seuls. **La relance (`suite_rerun.sh`, 22:18:49Z → 22:25:40Z) n'a pas rendu vert — elle a rendu pire**, et c'est ce qui la
distingue de C2 : **4 failed, 2 610 passed, 6 skipped, 1 error** (396 s), puis `tests/test_main.py` seul **1 failed, 15
passed, 2 errors** (3,7 s — reproductible seul, là où C2 le voyait passer seul), `tests/test_scripts/test_b4_campaign_configs.py`
seul **30 passed**. Les cinq non-verts de la relance, tous de la même classe, aucun `AssertionError` :

| Test | Phase | Signal |
|---|---|---|
| `tests/test_main.py::TestKrakenBotStart::test_start_routes_runtime_1m_ohlc_to_router_crash_protector` | setup (erreur) | callback `_addrinfo_cb` `pycares` sur boucle fermée |
| `tests/test_main.py::TestKrakenBotStart::test_start_subscribes_1m_when_router_crash_protector_is_configured` | call | idem (le même test qu'à la première passe) |
| `tests/test_main.py::TestKrakenBotStop::test_stop_handles_component_errors` | call | `ExceptionGroup` de 4 `ClientSession` non fermées |
| `tests/test_main.py::TestKrakenBotStats::test_log_stats_collects_all_component_stats` | call | `ClientSession.__del__` non fermée (la victime C2) |
| `tests/test_scripts/test_c2_replay_fidelity.py::test_order_created_at_T_does_not_fill_on_the_candle_ending_at_T` | call | `ClientSession.__del__` — victime de passage |

Aucune troisième relance : la règle « jamais une relance jusqu'à ce que ça passe » vaut ici aussi, et le mécanisme est
établi.

**Cause identifiée (lecture du code, aucune modification).** `tests/conftest.py::mock_settings` (l. 93) construit `Settings(environment="testing", kraken=…, database=…, risk=…, trading=…)` sans fixer `telegram` ; `TelegramSettings` (`env_prefix="TELEGRAM_"`) se remplit donc depuis l'environnement. Sur le serveur, le `.env` copié de l'arbre du service (recette C2) et l'export du `~/.bashrc` (l. 119, `set -a && source .env`) fournissent `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` **réels** ; `KrakenBot._init_telegram_notifier()` (`main.py` l. 443) construit un vrai `TelegramNotifier` — jamais patché dans `tests/test_main.py` — et `start()` lance `send_bot_started` en tâche détachée (`asyncio.create_task`, `main.py` l. 577) : une **vraie requête HTTPS vers `api.telegram.org`** (résolution `aiodns`/`pycares`, `aiohttp.ClientSession`) part des tests unitaires et survit à la fermeture de la boucle du test — callback `_addrinfo_cb` sur boucle fermée, session jamais fermée, ramassée pendant un test voisin. En local, le `.env` n'a **aucune** variable `TELEGRAM_` : notifier désactivé, `tests/test_main.py` 18 passés (×3), suite locale **2 615 passés / 6 skippés**, 196 s (22/09 22:27:46Z → 22:31:04Z, rc 0, même commande, `-p no:cacheprovider`). C2 avait le même défaut latent (son incident, « non reproductible » après trois relances vertes) ; ce soir la course est perdue à chaque passage. Ni `src/`, ni `tests/test_main.py`, ni `tests/conftest.py` n'ont changé depuis `f585e8b` ; les deux venvs (C2, C3a) sont identiques (75 paquets). **Ce n'est pas une régression C3a**, c'est un défaut d'hermétisme de la suite révélé par la recette (un `.env` de service avec des identifiants réels). Conséquence possible, à vérifier par Bruno : des messages Telegram « bot started (paper) » reçus pendant chaque suite serveur (19/09 en C2 ; 22/09 vers 22:05Z, 22:19Z et 22:25Z). Correctif hors périmètre de ce chantier (aucune ligne de code) : `telegram=TelegramSettings(enabled=False)` dans la fixture, ou patcher `TelegramNotifier` dans `tests/test_main.py` — item de dette de suite.

## Innocuité, vérifiée après le rejeu

- `krakenbot-collector` **actif**, `NRestarts=0` (sans interruption depuis le 13 sept 19:54 UTC) ; `krakenbot` (trader)
  inactif, inchangé ; **aucun zombie**, aucun processus résiduel.
- Continuité des bougies 1 m Bybit sur la fenêtre 20:54:39Z → 22:16:34Z, par paire (BTC, ETH, SOL) : **82 lignes /
  0 trou** chacune, plus grand écart exactement 1 min.

## Note de versionnement

Exception `.gitignore` `!results/c3a_determinism_server/**/*.log` (même convention que C2 : la règle `*.log` écarterait
silencieusement les journaux), vérifiée par `git check-ignore -v` puis `git ls-files`. Les quatre pilotes sont suivis.

Empreinte reproductible du lot (sha256 de la concaténation des fichiers du répertoire triés par nom, `README.md`
exclu) : `run_6f7ed8e/` (58 fichiers) `4a0c802505ad3fce`.
