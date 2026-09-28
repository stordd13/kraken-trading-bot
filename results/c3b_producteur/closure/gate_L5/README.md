# C3b — porte pré-merge § L.5, option 1 : les 24 `_full` au serveur, au SHA livré

`src/` est touché par le lot 1 (`10ed8d8`), donc l'option 2 du § L.5 (diff de contrôle vide sur les chemins exercés)
est indisponible. Les **24 tests de déterminisme full-range** ont tourné **sur le serveur**, au SHA livré, après les
docs de clôture et avant le merge (plan de clôture validé le 2026-09-28).

- **SHA testé** : `fe82fe57f087c58cfc7292ff351976725e735169`, tip de `feat/c3b-producteur` après les six commits de
  docs de clôture (commit f corrigé avant le push, à la demande de Bruno).
- **CI verte sur ce SHA** dès la tentative 1 :
  [run 36449912466](https://github.com/stordd13/kraken-trading-bot/actions/runs/36449912466)
  (`../tests/ci_status_S.out`).
- **Fenêtre** : **2026-09-28, 16:25:08Z → 17:36:25Z (71 min 17 s)**. `pilot_exit=0`.
- **Résultat** : `full=0`. Les 24 combos sortent en `rc=0` et leur JUnit porte `1/0/0/0` ; agrégat
  `junit_total=tests:24,failures:0,errors:0,skipped:0,missing:0`.

## Conditions

- **Clone isolé** `~/runs/c3b_gate/repo`
  - Clone GitHub, `git fetch origin feat/c3b-producteur`, `git checkout --detach fe82fe5` (transport par push, jamais
    de bundle).
  - `.env` copié du service.
  - L'arbre du service (`~/apps/kraken-trading-bot`, à `e9c8faf`, propre) et son `.env` ne sont pas touchés.
- **Environnement unique**
  - L'interpréteur du venv du service : Python 3.12.3, pytest 9.0.2.
  - `env PYTHONPATH="$REPO/src"` sur chaque invocation Python ; jamais sur `alembic`, lancé depuis l'arbre du service.
  - `poetry.lock` et `pyproject.toml` identiques au service ; `krakenbot` résolu vers le clone, par la garde puis
    par `interpreter_check=0`.
  - Base en accès **local**, sans tunnel.
- **Gardes (refus = 2)** : SHA, arbre suivi propre, environnement, `krakenbot`, `.env`, pytest, **port Postgres 5432
  joignable**.
  - Sans base, le module de test est **skippé** (`pytestmark`, `test_run_p6_determinism.py:60-64`) et pytest sort en
    0 : ce serait un faux vert de porte.
  - D'où la règle : un combo ne passe que si `rc=0` **et** JUnit `tests=1 failures=0 errors=0 skipped=0`.
- **Commande par combo** : `nice -n 5 env PYTHONPATH="$REPO/src" "$PY" -m pytest -p no:cacheprovider -q
  --durations=0 --junitxml=comboN.xml "tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[comboN]"`.
  - Une invocation par combo.
  - Les 24 tournent même après un échec (aucun ici).
  - Aucune relance, aucun `kill`.
- **Non-lecture.** `addopts` porte `--showlocals`, donc un journal de combo en échec contiendrait les métriques P6
  des deux exécutions.
  - Les journaux et les JUnit restent en fichiers : **archivés, jamais affichés**.
  - Remontent les codes, les comptes JUnit (attributs seuls) et `pytest_summary.txt` : par combo, la ligne de durée
    `call` et la ligne de résumé.
  - Ces 24 tests sont des backtests P6 (USDC, défauts de classe, 2023-04 → 2026-04) comparés par hash : **pas des
    runs du producteur**. Les JSON des runners sont restés dans les répertoires temporaires de pytest sur le serveur,
    ni lus, ni archivés.
- **Innocuité**
  - Collector `active`, `NRestarts=0`, avant et après.
  - Arbre suivi du clone propre après le run (`tree_after=0`).
  - `alembic current` `c3bd1e7a0001 (head)` avant et après.

## Durées

Durées d'appel par combo (s) :

242.42, 242.45, 192.14, 55.24, 55.57, 43.54, 58.29, 58.33, 47.34, 50.04, 49.14, 39.93, 53.66, 52.66, 42.95, 330.95,
331.16, 253.48, 313.06, 328.17, 239.29, 409.60, 414.03, 314.53

C'est le profil des portes précédentes : 1 w le 24/09 (70 min 52 s), SOL/D2 le 25/09 (71 min 51 s).

## Archive et nettoyage

- **Archive** `~/archive/c3b_gate_20260928/c3b_gate_server_20260928.tgz`, sha256
  `fc029d55065379c184c137aee8bf6a9a675c180b479a9fdb784d0e095f3f1f5b`.
  - Contenu : 56 fichiers, soit `out/` (status, journal du pilote, alembic, extrait, `pilot_exit.txt`, 24 journaux et
    24 JUnit) et le pilote.
  - **Ni `repo/` ni `.env`** : 0 entrée interdite.
- **Vérifiée sur le serveur** : liste de l'archive égale à la liste des fichiers ; `sha256sum -c` ; extraction et
  `diff -rq` ; `cmp` du pilote ; `sha256sum -c` des fichiers extraits. Tous les codes sont à 0
  (`../tests/archive_gate.out`).
- `files_all.sha256` et `files_expected.txt` restent au serveur.
- **`rm -rf ~/runs/c3b_gate` le 2026-09-28 à 17:41:31Z**, après ces vérifications. Le `.env` copié est parti avec le
  clone.

## Invariance du commit de porte

Le commit qui porte ce répertoire ne touche que `results/c3b_producteur/closure/` : aucun code, et c'est vérifié par
`../tests/controle_diff.out`, clé `gate_commit_closure_only`. La porte jouée à `fe82fe5` vaut donc pour le tip, sans
rejeu. C'est le précédent C2 (`docs/RESEARCH_LOG.md`, « Porte pré-merge C2 »).

## Fichiers

| Fichier | Contenu |
|---|---|
| `run_c3b_gate.sh` | le pilote, sha256 `be071fff4f6b78532ee002a81bf0b3662c49ae47f0a17c143c706b0fd0d30c9c`. Ce sha est consigné par le pilote lui-même, et il est égal au sha local avant lancement (`../tests/launch_gate.out`) |
| `status.txt` | un code par étape : gardes, alembic, `combo0…23` avec leurs comptes JUnit, `full`, agrégat, extrait, arbre, interpréteur, collector, bornes |
| `pilot_exit.txt` | code du pilote : `0` |
| `alembic_before.txt`, `alembic_after.txt` | `alembic current` : `c3bd1e7a0001 (head)` |
| `pytest_summary.txt` | extrait du journal pytest, par combo : la ligne `call` et la ligne de résumé, rien d'autre |
| `c3b_gate_server_20260928.tgz.sha256` | sha256 de l'archive |

Scripts de mise en place et de contrôle, chacun committé avec sa sortie, sous `../tests/` :
- `preflight_server` : lecture seule ;
- `launch_gate` ;
- `wait_gate` ;
- `fetch_gate` ;
- `archive_gate` ;
- `ci_status` ;
- `suite_locale` ;
- `mypy_gold` ;
- `controle_diff`.
