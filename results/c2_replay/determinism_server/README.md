# C2 — preuves de la porte pré-merge (rejeux de déterminisme sur serveur)

> Pourquoi sur le serveur : via le tunnel SSH, les 24 tests `-m slow` full-range n'ont jamais pu aller au bout —
> **chaque échec portait une erreur de connexion, aucun ne portait de comparaison de hash** (détail et mesures dans
> `results/C2_replay_report.md` § 8). Sur le serveur la base est locale : le premier combo passe en 238 s là où il
> tournait 41 min puis échouait via le tunnel.

## Conditions communes aux deux rejeux

- **Checkout isolé** `~/c2-determinism/repo` sur le serveur, en HEAD **détaché** sur le SHA testé ; jamais l'arbre du
  service (`~/apps/kraken-trading-bot`) ni son virtualenv.
- **Venv propre à ce répertoire** (`POETRY_VIRTUALENVS_IN_PROJECT=true`, `.venv` local), dépendances **verrouillées**
  par `poetry.lock` (`poetry install`).
- `.env` **copié** depuis l'arbre du service, jamais modifié ; base en accès **local** (aucun tunnel, aucun port 5433).
- Parallélisme laissé à ce que le test impose (`--workers 2`, dans le plafond convenu), processus en `nice -n 5`,
  machine à 4 cœurs.
- **Aucun** merge, déploiement, `systemctl`, modification du `.env` serveur ni `workflow_dispatch`.
- Une invocation `pytest` **par combo**, un rapport JUnit par combo, **arrêt immédiat prévu au premier échec** — un
  écart de hash est un bug de déterminisme à instruire, jamais une relance jusqu'à ce que ça passe. L'arrêt n'a
  servi dans aucun des deux rejeux.

## `run1_835ffe2/` — rejeu au SHA figé après corrections documentaires

**SHA testé : `835ffe21f031834a0a168daf409c4d6d09bc08d8`** · fenêtre 2026-09-19 10:39:50Z → 11:50:04Z (70 min).

| Fichier | Commande exacte | Résultat |
|---|---|---|
| `combo0.xml` … `combo23.xml` (+ `comboN.log`) | `nice -n 5 poetry run pytest -p no:cacheprovider -q --durations=0 --junitxml=combo$N.xml "tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[combo$N]"` pour `N` de 0 à 23 | agrégat **tests=24 failures=0 errors=0 skipped=0** |
| `run24.log` | journal du pilote `run24.sh` (boucle sur les 24 combos, horodatage et durée de chacun) | `ALL 24 DONE` |
| `suite_run1_teardown_incident.xml` | `nice -n 5 poetry run pytest -q -p no:cacheprovider --junitxml=suite.xml --ignore=tests/test_scripts/test_run_p6_determinism.py` | **tests=1521 failures=0 errors=3 skipped=6** — voir l'incident ci-dessous (le nom du fichier est une étiquette posée avant analyse : une seule des trois erreurs est au teardown) |
| `rest_suite.log` | journal du même passage, avec `ruff check`, `ruff format --check` et `mypy src/` | ruff propre, mypy 65 (64 avec `--ignore-missing-imports`) |

**L'incident, conservé et décrit tel que le XML le montre.** Ce tout premier passage serveur de la suite a rendu 3
erreurs de **nettoyage asynchrone**, aucune n'étant un échec de test — mais la répartition n'est pas celle que le nom du
fichier laisse croire, et elle est consignée ici telle qu'elle est :

| Test (`tests/test_main.py`) | Phase | Signal porté par le XML |
|---|---|---|
| `TestKrakenBotStart::test_start_subscribes_1m_when_router_crash_protector_is_configured` | **teardown** | callback `_addrinfo_cb` de `pycares` / `aiodns` retombant sur une boucle fermée (`RuntimeError: Event loop is closed`) |
| `TestKrakenBotStop::test_stop_handles_component_errors` | **setup** | `ResourceWarning: Unclosed client session` (`aiohttp`) remontée en `PytestUnraisableExceptionWarning` |
| `TestKrakenBotStats::test_log_stats_collects_all_component_stats` | **setup** | `ExceptionGroup` de plusieurs avertissements non levables |

Conséquence à ne pas masquer : une erreur **au setup** signifie que le corps du test **n'a pas tourné**. Sur ce passage,
deux tests n'ont donc pas été exécutés — ils l'ont été dans les passages suivants. Cause commune : des objets asynchrones
(`aiohttp`, résolveur DNS) survivant à la fin du test qui les a créés, chemin de bibliothèque que C2 ne touche pas.
**Non reproductible** : trois relances immédiates de la même suite ont rendu `1 514 passés, 6 skippés, 0 erreur`, et le
fichier incriminé passe seul (18 tests). Le fichier n'est pas effacé — son nom reste tel qu'il a été posé, cette table
dit ce qu'il contient réellement ; le passage vert au SHA livré est archivé dans `run2_f585e8b/suite.xml`.

## `run2_f585e8b/` — rejeu au SHA livré

**SHA testé : `f585e8bb676ad194753305da86db953d425de97c`** (= le SHA mergé, aux artefacts près : voir la vérification
d'invariance de `results/C2_replay_report.md` § 8) · fenêtre 2026-09-19 12:11:42Z → 13:24:43Z.

| Fichier | Commande exacte | Résultat |
|---|---|---|
| `combo0.xml` … `combo23.xml` (+ `comboN.log`) | identique à `run1`, pilote `run24b.sh` | agrégat **tests=24 failures=0 errors=0 skipped=0** |
| `run24b.log` | journal du pilote | `ALL 24 DONE` |
| `suite.xml` | `poetry run pytest -q -p no:cacheprovider --junitxml=suite.xml --ignore=tests/test_scripts/test_run_p6_determinism.py` | **tests=1520 failures=0 errors=0 skipped=6** (1 514 passés) |
| `short.xml` | `poetry run pytest -q -p no:cacheprovider --junitxml=short.xml -k "not full" tests/test_scripts/test_run_p6_determinism.py` | **tests=6 failures=0 errors=0 skipped=0** (les 6 de la fenêtre courte) |
| `checks_f585e8b.log` | journal horodaté des vérifications au SHA livré, **chaque commande imprimée avant son bloc** : suite hors déterminisme, 6 tests courts, gold hashes, `ruff check` + `format --check`, `mypy src/` avec et sans `--ignore-missing-imports` | 1 514 passés / 6 skippés · 6 passés · 2 passés · ruff propre · mypy 65 puis 64 |

Au même SHA (journal `checks_f585e8b.log`) : `test_grid_atr_v4_backward_compat.py` **2 passés**, `ruff check` propre
(les 2 fichiers non formatés sont la dette 10, préexistante et intacte sur la branche), `mypy src/` **65** dont la 65e
est `src/krakenbot/ml/features/feature_store.py:32 — Library stubs not installed for "pandas" [import-untyped]`,
c'est-à-dire exactement le delta avec `--ignore-missing-imports` (64).

## Innocuité, vérifiée après **chacun** des deux rejeux

- `krakenbot-collector` **actif**, `NRestarts=0` (sans interruption depuis le 13 sept), **aucun zombie**, aucun
  processus résiduel.
- Continuité des bougies 1 m sur la fenêtre du rejeu, par paire (BTC, ETH, SOL) : **73 lignes / 0 trou** après le
  premier, **72 lignes / 0 trou** après le second, plus grand écart exactement 1.0 min dans les deux cas.

## Note de versionnement

La règle `*.log` du `.gitignore` avait **silencieusement écarté** ces journaux d'un premier commit d'artefacts : seuls
les XML étaient suivis. Une exception ciblée
(`!results/c2_replay/determinism_server/**/*.log`) les rend suivis, vérifiée par `git check-ignore -v` sur chaque
fichier puis par `git ls-files`. Rien ici n'est laissé hors versionnement.

Empreintes reproductibles, par lot (sha256 de la concaténation des fichiers du répertoire, triés par nom) :
`run1_835ffe2/` (51 fichiers) `6b1125c3d11c3ff4` · `run2_f585e8b/` (52 fichiers) `bcc5a18cb2b7f105`.
