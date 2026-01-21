# KrakenBot - TODO

> Dernière mise à jour: 2026-01-21

## Statut Actuel

- **Data Collector**: En production sur Hetzner (24/7)
- **Trading Bot**: Paper trading fonctionnel
- **Dashboard**: Dash disponible (localhost:8050)

---

## Priorité Haute

### Alerting
- [ ] Notifications Telegram/Discord sur trades exécutés
- [ ] Alertes sur erreurs critiques
- [ ] Alertes limites de risque atteintes

### Validation Stratégie
- [ ] Backtest sur vraies données collectées
- [ ] Analyse des trades paper trading
- [ ] Ajuster paramètres (buy_threshold, sell_threshold, rolling_window)

---

## Priorité Moyenne

### Tests & Robustesse
- [ ] Tests unitaires composants critiques
- [ ] Gestion reconnexions WebSocket/DB
- [ ] Health checks endpoint (`/health`)

### Monitoring
- [ ] Métriques Prometheus
- [ ] Dashboard Grafana (optionnel)

---

## Priorité Basse (Long terme)

### Production Live
- [ ] Passage en live avec petit capital (50-100€)
- [ ] Surveillance active premiers jours

### Évolutions
- [ ] Multi-stratégies en parallèle
- [ ] ML/RL avec données accumulées
- [ ] Support multi-paires (ETH, etc.)

---

## Complété

- [x] Architecture 2 services (collector + trading bot)
- [x] CI/CD GitHub Actions → Hetzner
- [x] Dashboard Dash temps réel
- [x] Systemd services
- [x] Data collection 24/7
- [x] Paper trading fonctionnel
- [x] Risk management (5 checks)
- [x] 284 tests (100% pass)
