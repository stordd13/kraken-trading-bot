# Reconstruction 1 w — porte serveur : les 24 tests de déterminisme full-range

> Le diff de contrôle § L.3 du protocole C3 n'est pas vide sur `src/` (modèle `OHLCDerived`, option A retenue par
> Bruno) : la condition 2 du § L.5 ne peut pas s'appuyer sur un SHA antérieur. D'où les **24 tests de déterminisme
> full-range sur le serveur**, au SHA de la branche, **après les commits et avant le merge**, lancés sur signal de Bruno
> (24/09). Recette de C2 / C3a (`results/c3a_determinism_server/run_6f7ed8e/README.md`), pilote versionné.

**SHA testé : `5cb8a24e7e594d9dbd93d4f39af8654a9891e3a4`** (`git describe` = `v2.12.0-c3-v2.1-9-g5cb8a24`, tip de
`feat/c3b-reconstruction-1w`) · fenêtre **2026-09-24 20:36:25Z → 21:47:17Z (70 min 52 s)** · agrégat **`tests=24
failures=0 errors=0 skipped=0`**. Merge dans `dev` ensuite : `00ad09a`, arbre identique au SHA testé (`git diff
5cb8a24 00ad09a` vide).

## Conditions

- **Checkout isolé** `~/r1w-determinism/repo` sur le serveur, HEAD **détaché** sur le SHA testé ; jamais l'arbre du
  service (`~/apps/kraken-trading-bot`, resté à `b43515a`, propre, pendant tout le run) ni son virtualenv. Clone local de
  l'arbre du service, puis transport des 7 commits de la branche par `git bundle b43515a..feat/c3b-reconstruction-1w`
  (sha256 `8541b0a74c061adb319470fcd97ad81a2984db3fa3261abedbcd7d6946ea0d36`, identique sur le Mac et sur le serveur) :
  la branche n'était pas poussée.
- **Venv propre à ce répertoire** (`POETRY_VIRTUALENVS_IN_PROJECT=true`, `VIRTUAL_ENV` retiré), dépendances
  verrouillées par `poetry.lock` (`poetry install`, rc 0 — Python 3.12.3, pytest 9.0.2).
- `.env` **copié** depuis l'arbre du service, jamais modifié ; base en accès **local** (aucun tunnel).
- `nice -n 5`, session tmux `r1w24` ; une invocation `pytest` **par combo**, un rapport JUnit par combo, **arrêt au
  premier échec** (non servi) ; le pilote refuse de tourner sur un autre SHA ou sur un tree suivi non propre.
- Aucun merge, déploiement, `systemctl` ni modification du `.env` serveur pendant le run ; collector actif,
  `NRestarts=0` avant et après.

## Fichiers

| Fichier | Contenu |
|---|---|
| `run24.sh` | le pilote (sha256 `17428d750dc82880966f19377ea2557a63629cc631097ef81a95d15d7d616a92`) |
| `run24.log` | son journal : SHA, horodatage et durée de chaque combo, `=== ALL 24 DONE 2026-09-24T21:47:17Z` |
| `combo0.xml` … `combo23.xml` | JUnit, un par combo : `nice -n 5 poetry run pytest -p no:cacheprovider -q --durations=0 --junitxml=comboN.xml "tests/test_scripts/test_run_p6_determinism.py::test_determinism_parallel_vs_serial_full[comboN]"` — chacun `tests=1 failures=0 errors=0 skipped=0` |
| `combo0.log` … `combo23.log` | sortie pytest de chaque combo |

Durées d'appel par combo (s) : 239.30, 241.82, 190.48, 55.46, 55.32, 44.43, 57.01, 57.47, 46.91, 49.08, 50.32, 39.79,
52.92, 53.32, 42.28, 330.36, 333.62, 252.07, 310.36, 312.51, 235.55, 406.75, 409.17, 307.98 — profil de C3a
(38 s → 406 s).

Ces tests lisent les paires USDC (`runner.PAIRS`, 2023-04-01 → 2026-04-01) : les 24 rows dérivées (1 w USDT) ne
peuvent pas les affecter ; la porte vérifie le seul changement de `src/`. **Ils ne sont jamais relancés.**
