# Lint & Format Report -- Mars 2026

## Ruff Check

### Avant corrections manuelles
- **23 erreurs** au total
- Aucune auto-fixable (`--fix` n'a rien corrige)
- 17 erreurs "unsafe-fixes" uniquement

| Regle | Nb | Description | Action |
|-------|-----|-------------|--------|
| UP042 | 13 | `str, Enum` -> `StrEnum` | NON corrige (unsafe, risque de casser serialisation) |
| E402 | 6 | Import pas en haut du fichier | NON corrige (attendu dans scripts/ et alembic/) |
| F841 | 3 | Variable locale non utilisee | Corrige manuellement (`session` -> `_session`) |
| C408 | 1 | `dict()` inutile | Corrige manuellement (rewrite as literal) |

### Apres corrections manuelles
- **19 erreurs restantes** (13 UP042 + 6 E402)
- Toutes sont soit intentionnelles (E402 dans scripts) soit unsafe (UP042)

### Fichiers corriges
1. `tests/test_core/test_database.py` : 3x F841 (`session` -> `_session` dans context managers)
2. `scripts/fetch_ohlc.py` : 1x C408 (`dict()` -> `{}` literal)

### UP042 : Pourquoi ne pas corriger
Les 13 enums `(str, Enum)` -> `StrEnum` sont un changement semantique :
- `StrEnum` a un comportement different pour `auto()`, `_generate_next_value_`, etc.
- Risque de casser la serialisation JSON et les comparaisons DB
- Fichiers concernes : `settings.py`, `event_bus.py`, `multi_timeframe.py`, `base.py` (models)
- **Recommandation** : migration `StrEnum` en tache separee avec tests complets

### E402 : Pourquoi ne pas corriger
- `alembic/env.py` : import apres `sys.path` setup (obligatoire pour Alembic)
- `tests/test_backtest.py` : import apres `sys.path.insert()` (obligatoire pour importer scripts/)
- Configuration `per-file-ignores` existe deja pour `scripts/*.py` mais pas pour `alembic/` ni `tests/`

## Ruff Format

- **0 fichiers reformates** -- le code etait deja conforme
- Configuration : line-length=100, target py311

## MyPy (strict mode)

### Resultat global
- **85 erreurs** dans **18 fichiers** (sur 55 verifies)

### Categorisation

#### Critique (Decimal/float confusion) -- 12 erreurs
| Fichier | Erreur |
|---------|--------|
| `indicators/rsi.py:62-67` | Decimal/float type mismatch dans calcul RSI |
| `indicators/bollinger.py:75-93` | Decimal/float operations + BollingerBandsResult arg-type |
| `indicators/adx.py:101-136` | Operations sur `Decimal \| None` sans guard |
| `indicators/supertrend.py:113-118` | Comparaison Decimal vs None |

#### Important (None safety) -- 25 erreurs
| Fichier | Type |
|---------|------|
| `main.py` (15 erreurs) | `Optional[X]` utilise sans `None` check (event_bus, db_manager, ws_client, execution_engine) |
| `collector.py` (4 erreurs) | `Optional[KrakenWebSocketClient]` utilise sans guard |
| `scheduler/task_scheduler.py` (3 erreurs) | Optional args + EventType attrs manquants |
| `main.py:613-624` (6 erreurs) | `Decimal` utilise la ou un objet Position est attendu |

#### Mineur (style strict) -- 48 erreurs
| Type | Nb | Fichiers |
|------|-----|---------|
| `no-any-return` | 5 | logger.py, risk.py, execution/engine.py, fetch_ohlc.py |
| `no-untyped-def` | 3 | fetch_ohlc.py |
| `union-attr` | 20 | main.py, collector.py, strategies |
| `arg-type` | 10 | main.py, scheduler, strategies |
| `assignment` | 5 | settings.py, indicators |
| `misc` (lambda inference) | 3 | main.py, collector.py |
| `attr-defined` | 2 | scheduler/task_scheduler.py |

### Recommandations MyPy
1. **Priorite haute** : Ajouter des `None` guards dans `main.py` et `collector.py` (15+ erreurs simples a corriger)
2. **Priorite moyenne** : Clarifier types Decimal/float dans indicators (rsi, bollinger, adx)
3. **Priorite basse** : Ajouter annotations manquantes dans scripts/fetch_ohlc.py
4. **A ne pas toucher** : Les 6 erreurs `.status`, `.closed_at`, `.pnl` dans main.py:613-624 suggerent un bug (Decimal la ou un objet est attendu)

## Verification post-lint

- **703 tests passes, 6 echoues**
- Les 6 echecs sont **pre-existants** (pas causes par les corrections lint)
- Voir `results/test_report.md` pour le detail des echecs
