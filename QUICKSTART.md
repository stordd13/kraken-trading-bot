# 🚀 Guide de Démarrage Rapide - KrakenBot

Ce guide te permet de tester toutes les fonctionnalités du bot en 5 minutes.

## ✅ Prérequis

Vérifie que tout fonctionne avec le script de test:

```bash
python -m scripts.test_all
```

Ce script vérifie:
- ✅ Docker database (PostgreSQL + TimescaleDB)
- ✅ Connexion base de données
- ✅ Données OHLC
- ✅ Tables (backtest_runs, bot_state)
- ✅ Streamlit et Plotly

## 📋 Étape 1: Démarrer la base de données

```bash
# Démarrer PostgreSQL avec TimescaleDB
docker compose up -d db

# Vérifier que ça tourne
docker compose ps
```

Tu devrais voir:
```
NAME           STATUS
krakenbot-db   Up X hours (healthy)
```

## 📊 Étape 2: Générer des données de test

```bash
# Générer 30 jours de données OHLC fictives
python -m scripts.seed_test_data --days 30
```

Sortie attendue:
```
✅ Created 2880 OHLC candles
   Period: 2025-12-18 06:00 to 2026-01-17 06:00
   Price range: $98260.17 - $139118.86
```

## 🧪 Étape 3: Lancer un backtest

```bash
# Backtest sur 7 jours ET sauvegarder en DB pour visualisation
python -m scripts.backtest --pair XBT/USDC --days 7 --save
```

Sortie attendue:
```
================================================================================
                              BACKTEST REPORT
================================================================================

Strategy:                      threshold
Period:                        2026-01-10 to 2026-01-17
Duration:                      7.0 days

--------------------------------------------------------------------------------
PERFORMANCE SUMMARY
--------------------------------------------------------------------------------
Starting Balance:              1000.00 USDC
Ending Balance:                1000.00 USDC
Total Return:                  +0.00%
Net P&L:                       +0.00 USDC
Total Fees Paid:               0.00 USDC

✅ Backtest results saved to database with ID: 446e38d9-...
   Run name: threshold_XBT/USDC_2026-01-10_7d
   View in dashboard: streamlit run scripts/dashboard.py
```

**Note:** Avec des données aléatoires, il est normal de n'avoir aucun trade (stratégie threshold trop conservatrice).

## 📈 Étape 4: Lancer le dashboard

```bash
streamlit run scripts/dashboard.py
```

Le dashboard s'ouvre automatiquement dans ton navigateur à: **http://localhost:8501**

### Dans le dashboard:

**Mode 1: Live Bot** (par défaut)
- Affiche l'état du bot en temps réel
- Métriques: P&L, Position, Trades
- Graphique avec signaux d'achat/vente
- ⚠️ Vide pour l'instant (bot pas lancé)

**Mode 2: Backtest Results**
1. Dans la sidebar (à gauche), sélectionne **"Backtest Results"**
2. Un dropdown apparaît avec tes backtests
3. Sélectionne le backtest créé à l'étape 3
4. Tu verras:
   - Net P&L, Win Rate, Sharpe Ratio, Max Drawdown
   - Détails de la stratégie et période
   - Graphique OHLC de la période testée

## 🔄 Étape 5: Comparer plusieurs backtests

Lance plusieurs backtests avec différentes périodes:

```bash
# Backtest 7 jours
python -m scripts.backtest --pair XBT/USDC --days 7 --save --name "Test 7j"

# Backtest 14 jours
python -m scripts.backtest --pair XBT/USDC --days 14 --save --name "Test 14j"

# Backtest 30 jours
python -m scripts.backtest --pair XBT/USDC --days 30 --save --name "Test 30j"
```

Ensuite dans le dashboard:
1. Mode "Backtest Results"
2. Dropdown → Sélectionne différents backtests
3. Compare les métriques!

## 🤖 Étape 6 (Optionnel): Lancer le bot en mode Paper Trading

```bash
# Vérifie que .env est configuré avec TRADING_MODE=paper
cat .env | grep TRADING_MODE

# Lance le bot
python -m krakenbot
```

Le bot va:
1. Se connecter au WebSocket Kraken
2. Recevoir des données OHLC toutes les 15 minutes
3. Les sauvegarder en DB
4. Analyser avec la stratégie Threshold
5. Simuler des trades en mode paper

**Pendant que le bot tourne**, ouvre le dashboard et sélectionne "Live Bot" pour voir les trades en temps réel!

## 🐛 Troubleshooting

### Problème: "No OHLC data found"
**Solution:** Lance `python -m scripts.seed_test_data --days 30`

### Problème: "Database connection failed"
**Solution:** Lance `docker compose up -d db`

### Problème: "streamlit: command not found"
**Solution:** Lance `pip install -e ".[monitoring]"`

### Problème: "No backtests found"
**Solution:** Lance `python -m scripts.backtest --pair XBT/USDC --days 7 --save`

### Problème: Dashboard montre une erreur
**Solution:**
1. Stop le dashboard (Ctrl+C)
2. Lance `python -m scripts.test_all` pour diagnostiquer
3. Relance le dashboard

## 📚 Commandes Utiles

```bash
# Vérifier tout fonctionne
python -m scripts.test_all

# Générer des données
python -m scripts.seed_test_data --days 30

# Lancer un backtest
python -m scripts.backtest --pair XBT/USDC --days 7 --save

# Lancer le dashboard
streamlit run scripts/dashboard.py

# Lancer le bot (paper mode)
python -m krakenbot

# Voir les logs de la DB
docker compose logs -f db

# Stopper tout
docker compose down
pkill -f streamlit
pkill -f krakenbot
```

## 🎯 Prochaines Étapes

Une fois que tu as testé tout ça:

1. **Optimiser la stratégie**: Modifie les paramètres dans `.env`
   ```env
   STRATEGY_BUY_THRESHOLD_PCT=-2.0  # Acheter si prix baisse de 2%
   STRATEGY_SELL_THRESHOLD_PCT=1.5  # Vendre si prix monte de 1.5%
   ```

2. **Tester avec vraies données**: Lance le bot en paper mode pendant quelques jours

3. **Analyser les performances**: Utilise le dashboard et les backtests

4. **Créer une nouvelle stratégie**: Duplique `src/krakenbot/strategies/threshold.py`

5. **Mode Live** (⚠️ DANGER): Quand tu es sûr, configure `TRADING_MODE=live`

## ✨ Résumé

Tu as maintenant:
- ✅ Un bot de trading fonctionnel
- ✅ Un système de backtest complet
- ✅ Un dashboard de monitoring
- ✅ Des données de test pour jouer
- ✅ Tous les outils pour optimiser ta stratégie

**Bon trading! 🚀**
