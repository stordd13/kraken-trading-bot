# Phase 3 — CI/CD Fix Results

**Branche** : `fix/cicd-pipeline`
**Date** : 2026-04-10

## Changements

### 1. CI — Tests bloquants (`ci.yml`)
- Retiré `continue-on-error: true` sur `pytest`
- Les tests doivent passer pour que CI soit vert
- `mypy` reste non-bloquant (continue-on-error conservé)

### 2. CD — Deploy fiable (`deploy.yml`)
- **`.env` complet** : Kraken Spot + DB + Trading + Telegram + Kraken Futures
- **7 secrets** passés via `envs:` (plus aucune valeur manquante)
- **`set -e`** : le script SSH fail-fast sur toute erreur
- **Commit SHA** : capture `OLD_COMMIT` et `NEW_COMMIT` dans les logs
- **Health check réel** : `systemctl is-active --quiet` + `exit 1` si inactif
- **Telegram notifications** : curl-based, success + failure

### 3. Documentation (`docs/cicd_secrets.md`)
- Liste des 10 secrets GitHub requis
- Instructions pour ajouter un secret

## Checklist MUST HAVE

- [x] `continue-on-error: true` retiré des tests dans `ci.yml`
- [x] Le `.env` généré contient TOUTES les variables (Kraken Spot, Telegram, Kraken Futures)
- [x] Toutes les valeurs sensibles viennent de GitHub Secrets
- [x] `set -e` au début du script SSH
- [x] Health check qui fail le deploy si le service ne redémarre pas
- [x] Notification Telegram en succès et en échec
- [x] Documentation des secrets requis
- [x] Le commit SHA est loggé dans la sortie du workflow

## Checklist NICE TO HAVE

- [x] Capture du commit pre/post deploy pour rollback rapide
- [x] Health check qui vérifie aussi `krakenbot_started` dans les logs (warning)
- [x] `workflow_dispatch` pour relancer manuellement (déjà présent)

## Etapes de test manuel

1. **Ajouter les 4 nouveaux secrets sur GitHub** :
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `KRAKEN_FUTURES_API_KEY`
   - `KRAKEN_FUTURES_API_SECRET`

2. **Merger** : `fix/cicd-pipeline` → `dev` → `main`

3. **Surveiller** :
   - GitHub Actions : le workflow CI doit passer, puis Deploy se déclenche
   - Telegram : notification de succès ou d'échec

4. **Vérifier sur le serveur** :
   ```bash
   ssh -p 41922 bruno@77.42.90.102
   cat ~/apps/kraken-trading-bot/.env | head -5  # vérifier que les vars sont là
   sudo systemctl status krakenbot
   sudo systemctl status krakenbot-collector
   ```
