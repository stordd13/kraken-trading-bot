# KrakenBot -- Rapport Nettoyage Code (Mars 2026)

## Resume executif

| Metrique | Valeur |
|----------|--------|
| Erreurs ruff corrigees | 4 (manuelles) |
| Erreurs ruff restantes | 19 (13 UP042 unsafe + 6 E402 attendus) |
| Fichiers reformates | 0 (deja conforme) |
| Erreurs mypy | 85 dans 18 fichiers (strict mode) |
| Tests total | **826** (709 existants + **117 nouveaux**) |
| Tests passes | **820** |
| Tests echoues | 6 (pre-existants, non lies au cleanup) |
| Scripts backup crees | 2 (backup_db.sh + restore_db.sh) |

---

## 1. Lint & Format

### Corrections appliquees
1. `tests/test_core/test_database.py` : 3x F841 -- `session` -> `_session` (variable inutilisee dans context manager)
2. `scripts/fetch_ohlc.py` : 1x C408 -- `dict()` -> literal `{}`

### Erreurs restantes (non corrigees volontairement)
- **13 UP042** (`str, Enum` -> `StrEnum`) : Migration semantiquement risquee. Peut casser serialisation JSON, comparaisons DB, et `auto()`. A faire en tache separee avec tests complets.
- **6 E402** (imports pas en haut) : Attendu dans `alembic/env.py` (sys.path requis) et `tests/test_backtest.py` (sys.path.insert requis). Pas de fix necessaire.

### Ruff format
Zero fichier reformate -- le code etait deja conforme (line-length=100, py311 target).

### MyPy (strict mode) -- 85 erreurs
Voir `results/lint_report.md` pour le detail complet. Points cles :
- **12 erreurs critiques** : Decimal/float confusion dans indicators (rsi, bollinger, adx, supertrend)
- **25 erreurs importantes** : `Optional[X]` utilise sans `None` check dans main.py et collector.py
- **48 erreurs mineures** : `no-any-return`, `union-attr`, `arg-type` (bruit strict mode)
- **Bug potentiel** : `main.py:613-624` utilise un `Decimal` la ou un objet `Position` est attendu (`.status`, `.closed_at`, `.pnl` sur un Decimal)

---

## 2. Tests

### Resultats
- **820 passes / 6 echoues** sur 826 tests
- **117 nouveaux tests** ecrits dans 3 fichiers
- Tous les echecs sont **pre-existants** (desynchronisation tests/code)

### Nouveaux fichiers de test

| Fichier | Tests | Priorite | Module couvert |
|---------|-------|----------|---------------|
| `tests/test_strategies/test_gemini_risk_manager.py` | 46 | Haute | GeminiGlobalRiskManager (0% -> ~95%) |
| `tests/test_indicators/test_multi_timeframe_generic.py` | 36 | Haute | API generique MTF (get_ema, get_rsi, etc.) |
| `tests/test_strategies/test_strategies_basic.py` | 35 | Basse | Smoke tests 7 nouvelles strategies |

### Echecs pre-existants (6)
1-4. `test_multi_timeframe.py::TestAdaptiveThresholds` (4 tests) : Formule `_calc_adaptive_thresholds()` modifiee, tests pas mis a jour
5. `test_multi_timeframe.py::TestCandleCounts` : `candle_counts` retourne 7 TFs maintenant (avant: 3)
6. `test_adaptive.py::test_sell_trailing_stop_priority_over_profit_target` : Bug potentiel de priorite profit_target vs trailing_stop

---

## 3. Backup

### Scripts crees

| Script | Description |
|--------|-------------|
| `scripts/backup_db.sh` | Backup automatique PostgreSQL (daily/weekly) |
| `scripts/restore_db.sh` | Restauration depuis un backup |

### Deploiement sur le serveur Hetzner (quand il revient)

```bash
# 1. Copier les scripts
scp scripts/backup_db.sh scripts/restore_db.sh bruno@<IP>:/home/bruno/apps/kraken-trading-bot/scripts/

# 2. Rendre executables
ssh bruno@<IP> 'chmod +x /home/bruno/apps/kraken-trading-bot/scripts/backup_db.sh /home/bruno/apps/kraken-trading-bot/scripts/restore_db.sh'

# 3. Creer le dossier de backup
ssh bruno@<IP> 'mkdir -p /home/bruno/backups/krakenbot'

# 4. Ajouter au cron (crontab -e)
# Daily a 03:00 UTC :
0 3 * * * /home/bruno/apps/kraken-trading-bot/scripts/backup_db.sh daily
# Weekly dimanche a 04:00 UTC :
0 4 * * 0 /home/bruno/apps/kraken-trading-bot/scripts/backup_db.sh weekly

# 5. Verifier
tail -f /home/bruno/backups/krakenbot/backup.log

# 6. Restaurer (si necessaire)
./scripts/restore_db.sh /home/bruno/backups/krakenbot/krakenbot_2026-03-15_03-00_daily.dump.gz
```

### Caracteristiques du backup
- `pg_dump -Fc` (format custom, compact, restauration selective possible)
- Compression gzip
- Retention configurable (defaut: 7j daily, 28j weekly)
- Config overridable via variables d'environnement
- Logging dans `/home/bruno/backups/krakenbot/backup.log`
- Section rsync commentee (pret pour sync distant)
- Script idempotent et safe (`set -euo pipefail`)

---

## 4. Recommandations

### Priorite haute
1. **Mettre a jour les 5 tests legacy obsoletes** dans `test_multi_timeframe.py` pour refleter les nouveaux seuils adaptatifs et les 7 timeframes
2. **Activer le backup** des le retour du serveur Hetzner
3. **Ajouter `alembic/` et `tests/test_backtest.py`** aux `per-file-ignores` dans pyproject.toml pour eliminer les 6 E402 restants

### Priorite moyenne
4. **Corriger les 12 erreurs mypy critiques** dans indicators/ (Decimal/float confusion)
5. **Ajouter `None` guards** dans main.py et collector.py (25 erreurs mypy simples)
6. **Investiguer le bug de priorite** trailing_stop vs profit_target dans AdaptiveStrategy

### Priorite basse
7. **Migrer `(str, Enum)` vers `StrEnum`** (13 UP042) en tache separee avec tests de serialisation
8. **Ajouter annotations de type** dans `scripts/fetch_ohlc.py` (3 erreurs mypy)
9. **Configurer rsync distant** pour les backups (stockage offsite)

### Code smells identifies
- `main.py:613-624` : Un `Decimal` est utilise comme objet Position (appels `.status`, `.closed_at`, `.pnl` sur un Decimal) -- probablement un bug de typage
- `scheduler/task_scheduler.py:196,225` : Reference a `EventType.SCHEDULER_TASK_SUCCESS/FAILED` qui n'existent pas dans l'enum
- Les 7 nouvelles strategies n'ont aucun test de logique de trading (c'est volontaire -- le backtester s'en charge)

---

## Livrables

| Fichier | Description | Status |
|---------|-------------|--------|
| `results/lint_report.md` | Rapport lint ruff + mypy | OK |
| `results/test_report.md` | Rapport tests + nouveaux tests | OK |
| `results/cleanup_report.md` | Rapport final consolide (ce fichier) | OK |
| `scripts/backup_db.sh` | Backup automatique PostgreSQL | OK |
| `scripts/restore_db.sh` | Restore depuis backup | OK |
| `tests/test_strategies/test_gemini_risk_manager.py` | 46 tests GeminiGlobalRiskManager | OK |
| `tests/test_indicators/test_multi_timeframe_generic.py` | 36 tests API generique MTF | OK |
| `tests/test_strategies/test_strategies_basic.py` | 35 smoke tests 7 strategies | OK |
