# AGENT P6.7 — Parallélisation du backtest engine

> À exécuter APRÈS P6.5 (diagnostic + fix des bugs du backtester).
> Durée estimée : 1-2 jours.

---

## Contexte

Les backtests P6 prennent 45 minutes en sérial. Pour P7 (grid search avec 100+ backtests), il faut paralléliser. Cette tâche est à faire APRÈS P6.5 sur une branche dédiée pour ne pas mélanger fix de bugs et refactor d'infrastructure.

## Branche

Créer `feat/p6-7-backtest-multiprocessing` depuis `dev` (ou depuis la branche où P6.5 a été mergé, à confirmer avant de commencer).

## Objectif

Paralléliser les runs de backtest au niveau job (1 backtest = 1 combinaison stratégie × paire × période). Objectif : 24 backtests doivent tourner en ≤ 10 minutes sur une machine 16 cœurs (vs 45 min en sérial, soit 4.5× de speedup minimum).

---

## Spécifications techniques

### Scope

Parallélisation au niveau combo (stratégie × paire), PAS à l'intérieur d'un backtest individuel. Chaque backtest reste single-threaded.

### Librairie

`multiprocessing.Pool` avec contexte spawn explicite.

```python
import multiprocessing as mp

ctx = mp.get_context("spawn")
with ctx.Pool(n_workers) as pool:
    results = pool.imap_unordered(run_single_backtest, jobs)
```

**Pas d'asyncio** : les backtests sont CPU-bound, asyncio n'apporte rien.
**Pas de fork** : unsafe sur macOS avec des ressources ouvertes (DB connections, file handles).

### Paramétrage workers

Par défaut, cap à 8 workers pour respecter la contrainte RAM (chaque worker charge ~1 GB en pandas).

```python
DEFAULT_WORKERS = min(mp.cpu_count() - 2, 8)
```

Configurable via :
- CLI : `--workers N`
- ENV : `P6_N_WORKERS=N`

**Détection automatique de la RAM** : si `available_ram_gb < 16`, cap à `max(1, available_ram_gb // 2)`. Ça évite de faire exploser le serveur Hetzner 8 GB si jamais on lance en parallèle dessus.

### Ordre des jobs (critique pour le speedup)

Les grids sont ~50× plus lents que les signal-based strats (5min interval vs 4h). Si on lance naïvement en ordre alphabétique, les derniers workers seront bloqués sur les grids pendant que les autres ont fini.

Solution : trier les jobs par durée estimée décroissante avant de les passer au pool.

```python
def estimated_duration(job: dict) -> int:
    """Return estimated duration in seconds."""
    if "grid" in job["strategy"].lower():
        return 300  # ~5 min for grid backtests on 5min data
    return 30  # ~30 sec for signal-based on 4h data
```

Trier décroissant + utiliser `imap_unordered` → les gros jobs démarrent en premier, les petits remplissent les gaps entre.

### DB connections

Chaque worker initialise sa propre `DatabaseManager` dans son process. Pas de connection partagée entre workers.

Contraintes :
- Initialisation lazy au premier usage dans le worker
- Fermeture propre en fin de worker (avant exit) pour éviter les fuites
- Vérifier que `max_connections` de Postgres n'explose pas : 8 workers × N connexions par worker doit rester < 50

### Save progressif avec atomic rename

Le script sauvegarde chaque résultat dans `results/P6_phase_d_results.json` dès qu'un worker termine son job. Utiliser un lock + atomic rename pour éviter la corruption.

```python
import json
import os
import tempfile
from threading import Lock

_save_lock = Lock()

def save_result_atomic(results_dict: dict, path: str) -> None:
    """Atomic write to avoid corruption on crash/interrupt."""
    with _save_lock:
        dir_ = os.path.dirname(path)
        with tempfile.NamedTemporaryFile(
            mode='w', dir=dir_, delete=False, suffix='.tmp'
        ) as f:
            json.dump(results_dict, f, indent=2, default=str)
            temp_path = f.name
        os.replace(temp_path, path)  # atomic on POSIX
```

### Resume logic

Avant de lancer les jobs, charger le JSON existant et skipper les combos déjà présentes.

```python
def filter_pending_jobs(all_jobs: list, existing_results: dict) -> list:
    """Skip jobs that already have results in the JSON."""
    pending = []
    for job in all_jobs:
        key = f"{job['strategy']}_{job['pair'].replace('/', '_')}"
        if key not in existing_results:
            pending.append(job)
        else:
            logger.info("skip_completed", key=key)
    return pending
```

Ajouter un flag CLI `--force` pour rerun tout même si déjà fait.

### Logging

Chaque worker écrit dans son propre fichier :
- Path : `logs/p6_worker_{pid}.log`
- Format : structlog JSON
- Agrégation optionnelle en fin de run dans `logs/p6_aggregate.log`

Le process parent log uniquement les événements de haut niveau (worker started, worker finished, job N/24 done).

### Monitoring en temps réel

Fichier `logs/p6_status.json` mis à jour toutes les 5 secondes par le process parent.

```json
{
    "started_at": "2026-04-16T14:30:00Z",
    "total_jobs": 24,
    "completed_jobs": 7,
    "running_jobs": [
        "grok_grid_atr_v4_BTC/USDC",
        "grok_grid_atr_v4_ETH/USDC"
    ],
    "failed_jobs": [],
    "estimated_remaining_seconds": 420
}
```

Commande utile pendant l'exécution : `watch -n 2 cat logs/p6_status.json`.

### Timeout par job

Chaque job a un timeout hard de 30 minutes. Si un backtest dépasse (bug boucle infinie par exemple), il est killé et loggé comme failed.

```python
TIMEOUT_PER_JOB = 1800  # 30 minutes

result = pool.apply_async(
    run_single_backtest, args=(job,)
).get(timeout=TIMEOUT_PER_JOB)
```

### Safety

**Crash d'un worker** : ne doit PAS tuer le pool. Utiliser try/except dans chaque worker, retourner un dict d'erreur au lieu de raise.

```python
def run_single_backtest(job: dict) -> dict:
    try:
        # ... backtest logic
        return {"status": "success", "result": result, "job": job}
    except Exception as e:
        logger.error("worker_crashed", job=job, error=str(e))
        return {"status": "failed", "error": str(e), "job": job}
```

**KeyboardInterrupt (Ctrl+C)** : clean shutdown via signal handler dans le parent. Les workers en cours terminent leur job actuel, les pending sont abandonnés, résultats partiels sauvegardés.

**Détection zombies** : si un worker est silencieux depuis > timeout, le killer explicitement.

**Isolation des imports** : les imports lourds (pandas, numpy, connecteurs DB) sont faits dans le worker, pas dans le parent. Évite de dupliquer la mémoire entre process.

---

## Architecture cible

Créer `scripts/run_p6_backtests.py` (nouveau fichier, ou refactor de `scripts/backtest.py` si plus propre).

Structure :

```
scripts/run_p6_backtests.py
├── parse_args()
├── load_existing_results(path)
├── build_job_list(strategies, pairs)
├── filter_pending_jobs(jobs, existing)
├── sort_jobs_by_duration(jobs)
├── run_parallel(jobs, n_workers)
│   ├── init_worker()              # per-worker DB, logger
│   ├── run_single_backtest(job)   # wrapper autour du backtester existant
│   └── save_result_atomic(result)
└── generate_final_report(results)
```

---

## Validation — Définition de "done"

1. **Tests unitaires** : `pytest -q` vert. Nouveaux tests pour :
   - Le parallel runner avec mock workers
   - L'atomic save sous concurrence
   - Le resume support (relancer après interrupt)
   - Le tri des jobs par durée

2. **Déterminisme** : lancer les mêmes 3 combos en sérial puis en parallèle. Les résultats doivent être **identiques** (mêmes trades, mêmes dates, même P&L net, même nombre de trades). Écart acceptable : 0.

3. **Speedup** : `time poetry run python scripts/run_p6_backtests.py --workers 8` doit être au moins **5× plus rapide** que le mode sérial sur les 24 combos.

4. **Pas de nouvelle dépendance** : `multiprocessing` est dans la stdlib. Pas de dask, pas de ray, pas de joblib. Garder la stack minimale.

5. **Resume fonctionnel** : tuer le script au milieu (Ctrl+C ou kill -9), le relancer. Il doit reprendre là où il s'était arrêté, sans refaire les combos déjà sauvegardées.

---

## Commits atomiques

Séquencer les commits pour faciliter le review :

1. `feat(backtest): add parallel runner skeleton with multiprocessing Pool`
2. `feat(backtest): add atomic save with lock and temp file rename`
3. `feat(backtest): add resume support via existing results check`
4. `feat(backtest): add job sorting by estimated duration`
5. `feat(backtest): add worker logging and status monitoring`
6. `feat(backtest): add timeout per job and safe shutdown on signals`
7. `test(backtest): add parallel runner tests and determinism check`
8. `docs: update CLAUDE.md and skills/backtest.md with parallel runner`

---

## Livrables finaux

1. Script `scripts/run_p6_backtests.py` fonctionnel
2. Tests unitaires (pytest vert, minimum 15 nouveaux tests)
3. Benchmark documenté : `results/P6_7_multiprocessing_benchmark.md` avec :
   - Temps sérial vs parallèle sur 24 combos
   - Speedup observé
   - Utilisation CPU et RAM pendant le run (screenshots ou logs)
   - Comparaison bit-à-bit des résultats sérial vs parallèle
4. Mise à jour `skills/backtest.md` avec la nouvelle commande pour lancer en parallèle
5. Mise à jour `CLAUDE.md` pour mentionner le parallel runner et la commande par défaut

---

## Contexte projet

Avant de commencer, lire :
- `PROJECT_CONTEXT.md` : état global du projet
- `CLAUDE.md` : conventions de code et patterns
- `skills/backtest.md` : méthodologie de backtest actuelle
- `skills/troubleshooting.md` : pièges connus du backtester

---

## Règles

1. Pas de modification de la logique métier du backtester. Uniquement ajout d'une couche de parallélisation au-dessus.
2. Si un bug du backtester est découvert pendant le refactor, documenter dans un fichier séparé et créer une branche dédiée pour le fix — ne pas mélanger avec le multiprocessing.
3. Commits atomiques, messages descriptifs.
4. Tests avant chaque commit : `pytest -q | tail -5`.
5. Lint avant chaque commit : `ruff check . --fix && ruff format .`.
