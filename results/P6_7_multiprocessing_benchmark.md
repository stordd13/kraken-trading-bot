# P6.7 — Multiprocessing Benchmark

Mesure du speedup apporté par la parallélisation de
[scripts/run_p6_backtests.py](../scripts/run_p6_backtests.py) via
`multiprocessing.Pool` (contexte `spawn`) sur la campagne P6 (24 combos =
8 stratégies × 3 paires).

## État actuel

- ✅ **Déterminisme validé** bit-à-bit serial-vs-serial ET parallel-vs-serial sur 1 combo
  (`gemini_retour_moyenne` SOL/USDC, fenêtre 1 semaine). SHA256 identiques.
- ✅ **Worker réel** testé : 1 combo en mode parallèle (2 workers, spawn) termine en 29.5s
  vs ~30s en serial → parallélisation n'introduit pas d'overhead significatif pour ce cas.
- ✅ **Mini-benchmark partiel mesuré** (6 combos signal-based, fenêtre 3 mois, serial) :
  **13.1 min** (787-792s sur 4 exécutions consécutives). Détails ci-dessous.
- ⏳ **Benchmark parallèle sur ce même sous-ensemble** : à relancer (le harnais de test
  `/tmp/p6_mini_bench.py` manquait du guard `if __name__ == "__main__"`, ce qui provoquait
  une récursion spawn → crash du parallel run. Ce n'est PAS un bug du runner
  `scripts/run_p6_backtests.py` qui a bien le guard line 665).
- ⏳ **Benchmark 24 combos full range 3 ans** : à lancer pre-merge (voir procédure ci-dessous).

## Mini-benchmark mesuré

Sous-ensemble : 6 combos = `grok_supertrend_4h` + `grok_ema_adx_atr` × (BTC, ETH, SOL) USDC.
Fenêtre : 2025-01-01 → 2025-04-01 (3 mois).

| Mode | Wall-clock | Speedup |
|---|---|---|
| Serial | **787-792s** (13.1-13.2 min, 4 runs consécutifs) | baseline |
| Parallel (6 workers) | _à mesurer proprement_ | _attendu ~3-5×_ |

Le serial consistent à ~790s sur 4 runs démontre indirectement le déterminisme de la phase
de chargement + exécution (variance < 1%).

## Pourquoi le benchmark full n'est pas dans ce commit

La stratégie `grok_grid_atr_adaptive_v4` itère sur des bougies 5min sur 3 ans de données
(~315k candles) et a pris **~23 minutes** en serial sur la seule combo mesurée
(`grok_grid_atr_adaptive_v4_BTC_USDC`) avant que le run soit interrompu. Extrapolation :

| Sous-ensemble | Serial estimé | Parallèle 8w estimé |
|---|---|---|
| 3 combos grid (toutes les paires) | ~70 min | ~25 min (3 jobs grid → 3 workers) |
| 21 combos signal-based | ~15-20 min | ~3-5 min |
| **Total 24 combos** | **~85-90 min** | **~25-30 min** |

Le goulot d'étranglement du parallélisme est le nombre de combos grid (3 = nombre de
paires), car le grid est ~50× plus lent qu'un signal-based. Speedup théorique sur 24 combos :
**~3-3.5×**.

> Note : le spec P6.7 visait ≥ 5×. Cette cible n'est atteignable que si les grids sont
> exclus ou optimisés séparément — à discuter en P7.

## Méthodologie (à lancer pre-merge)

```bash
rm -f results/bench_serial.json results/bench_parallel.json

time poetry run python scripts/run_p6_backtests.py \
    --serial --force --output results/bench_serial.json

time poetry run python scripts/run_p6_backtests.py \
    --workers 8 --force --output results/bench_parallel.json

# Comparaison bit-à-bit
poetry run python -c "
import json, hashlib
def h(p):
    d = json.load(open(p))
    payload = {k: {kk: d[k].get(kk) for kk in ('strategy','pair','train','test','all')}
               for k in sorted(d)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
hs, hp = h('results/bench_serial.json'), h('results/bench_parallel.json')
print('serial:  ', hs)
print('parallel:', hp)
print('MATCH:', hs == hp)
"
```

**Prérequis** : tunnel SSH stable (`nc -zv 127.0.0.1 5433`). Une coupure silencieuse du
tunnel pendant une run bloque les workers sur l'attente DB (observé pendant la tentative
initiale : 1h36 bloqué à 0% CPU).

## Validation manuelle déjà effectuée

### 1 combo serial (1-week window, `gemini_retour_moyenne` SOL/USDC)

Wall-clock : ~30s. Trades : 0 (régime strong_bear filtre tous les signaux — comportement
attendu du filtre). Termine avec `status: success`, `duration_sec: 30`.

### Même combo en parallèle (workers=2)

Wall-clock : 29.5s. Résultat `status: success`, combo identique.

### Comparaison SHA256 (train + test + all)

```
s1 (serial run 1): 004f3fe2f6646bb6…
s2 (serial run 2): 004f3fe2f6646bb6…
p  (parallel):     004f3fe2f6646bb6…

serial-vs-serial match:   True   ← GATE : backtester est déterministe
parallel-vs-serial match: True   ← Pool spawn n'introduit pas de drift
```

### 1 combo grid full range (3 ans, `grok_grid_atr_adaptive_v4` BTC/USDC)

Wall-clock serial : ~23 min. Résultat écrit en entier dans
`results/P6_phase_d_results_bench_serial.json` (1011 trades, 14.35% return 3 ans, MaxDD
17.2%). Mêmes métriques que l'entrée `grok_grid_atr_adaptive_v4_BTC_USDC` dans le
`results/P6_phase_d_results.json` authoritative → preuve indirecte supplémentaire de
déterminisme (2 runs indépendants produisent le même résultat).

## Tests automatisés

Voir [tests/test_scripts/test_run_p6_determinism.py](../tests/test_scripts/test_run_p6_determinism.py) :

- `test_determinism_serial_vs_serial` (gate, 3 combos, fenêtre 1 semaine) — auto-skip si
  DB inaccessible.
- `test_determinism_parallel_vs_serial` (même 3 combos) — idem.
- `test_determinism_parallel_vs_serial_full` (`@pytest.mark.slow`, 24 combos, fenêtre 3 ans)
  → `pytest -m slow tests/test_scripts/test_run_p6_determinism.py`.

## TODO pre-merge P6.7 → dev

1. [ ] Lancer le benchmark 24 combos serial (expected ~85-90 min — utiliser tmux pour
       survivre aux déconnexions SSH).
2. [ ] Lancer le benchmark 24 combos parallel 8 workers (expected ~25-30 min).
3. [ ] Calculer SHA256 aggregate et confirmer match bit-à-bit.
4. [ ] Remplir les sections "Results" et "Notes" ci-dessous.
5. [ ] Lancer `pytest -m slow tests/test_scripts/test_run_p6_determinism.py` (24 combos ×
       2 runs = ~85 min de compute additionnel).
6. [ ] Snapshot `top -l 1` pendant le run parallèle pour CPU/RAM peak.

## Results (à compléter)

| Metric | Serial | Parallel (8 workers) | Speedup |
|---|---|---|---|
| Wall-clock | _à remplir_ | _à remplir_ | _à remplir_ |
| Combos OK | 24 | 24 | — |

## Notes (à compléter)

_À remplir après le run complet._
