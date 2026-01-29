# KrakenBot - État du Projet

> Dernière mise à jour: 2026-01-29

## Résumé Exécutif

**Le bot est LIVE et fonctionnel sur Hetzner VPS.**

| Composant | Statut | Détails |
|-----------|--------|---------|
| Data Collector | ✅ Live 24/7 | WebSocket + REST backfill |
| Trading Bot | ✅ Live | Mode live activé |
| Dashboard | ✅ Fonctionnel | Dash sur localhost:8050 |
| Database | ✅ Opérationnel | PostgreSQL + TimescaleDB |
| CI/CD | ✅ Automatisé | GitHub Actions → Hetzner |

---

## Configuration Actuelle

```yaml
Pair: XBT/USDC
Candle interval: 15 min
Lookback: 50 périodes (12h30)
Buy threshold: -1.0%
Sell threshold: +2.0%
Order amount: 100 USDC
Max open positions: 10
Daily loss limit: 50 USDC
Min trade interval: 60 sec
```

---

## Architecture

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│   krakenbot-collector       │    │      krakenbot              │
│   (Toujours actif 24/7)     │    │   (Start/Stop flexible)     │
│                             │    │                             │
│  - WebSocket real-time      │    │  - ThresholdRollingStrategy │
│  - REST API backfill        │    │  - ExecutionEngine          │
│  - TaskScheduler            │    │  - Paper/Live trading       │
└──────────────┬──────────────┘    └──────────────┬──────────────┘
               └────────────┬──────────────────────┘
                            ▼
               ┌─────────────────────────┐
               │  PostgreSQL/TimescaleDB │
               │     (Hetzner VPS)       │
               └─────────────────────────┘
```

---

## Stratégie Active: ThresholdRollingStrategy

**Principe**: Mean reversion sur rolling window

1. Calcule le prix moyen des N dernières bougies (lookback)
2. Compare le prix actuel au prix moyen
3. **BUY** si prix < moyenne - buy_threshold%
4. **SELL** si prix > prix_achat + sell_threshold%

**Forces**:
- Simple et compréhensible
- Backtesté avec grid search
- Risk management intégré

**Faiblesses**:
- Pas de stop-loss dynamique
- Pas d'adaptation à la volatilité
- Tracking positions ouvertes limité dans le dashboard

---

## Ce Qui Fonctionne Bien

1. **Infrastructure solide**
   - Deux services séparés (découplage collector/bot)
   - Reconnexion automatique WebSocket
   - Backfill REST en cas de gap

2. **Risk Management**
   - 5 checks avant chaque trade
   - Limite de perte journalière
   - Limite de position max

3. **Backtesting**
   - Grid search pour optimiser les paramètres
   - Support des candles 5min et 15min
   - Lookbacks de 1h à 7 jours testés

4. **Déploiement**
   - CI/CD automatique
   - Services systemd supervisés
   - Logs accessibles via journalctl

---

## Points d'Amélioration Identifiés

### Haute Priorité

| Problème | Impact | Solution |
|----------|--------|----------|
| Pas de visibilité positions ouvertes | Impossible de voir P&L non réalisé | Ajouter tab "Positions" au dashboard |
| Pas d'alertes | Découverte tardive des problèmes | Notifications Telegram/Discord |
| Frais non comptés dans backtest | Résultats optimistes | Intégrer frais Kraken (0.26%) |

### Moyenne Priorité

| Problème | Impact | Solution |
|----------|--------|----------|
| Mono-pair | Diversification limitée | Support multi-pair |
| Paramètres fixes | Pas d'adaptation au marché | Régime detection |
| Métriques basiques | Analyse incomplète | Sortino, Calmar, drawdowns |

---

## Données Collectées

- **Depuis**: ~Janvier 2026
- **Paires**: XBT/USDC
- **Intervalles**: 1m, 5m, 15m
- **Volume estimé**: ~50k+ bougies

---

## Fichiers Clés

| Fichier | Description |
|---------|-------------|
| `src/krakenbot/collector.py` | Service de collecte 24/7 |
| `src/krakenbot/main.py` | Trading bot principal |
| `src/krakenbot/strategies/threshold_rolling.py` | Stratégie active |
| `src/krakenbot/execution/engine.py` | Exécution des ordres |
| `src/krakenbot/execution/risk_manager.py` | Gestion des risques |
| `scripts/dashboard.py` | Dashboard Dash |
| `scripts/backtest.py` | Backtesting + grid search |

---

## Vision Long Terme

1. **Court terme** (actuel): Bot fonctionnel avec stratégie simple ✅
2. **Moyen terme**: Multi-stratégies + alertes + métriques avancées
3. **Long terme**: ML (Transformers) + RL pour optimisation continue

---

## Liens Utiles

- [ROADMAP.md](./ROADMAP.md) - Prochaines étapes détaillées
- [CLAUDE.md](./CLAUDE.md) - Instructions pour Claude Code
- [README.md](./README.md) - Documentation générale
