# Skill: Risk Management

> Comment fonctionne le risk management, les règles de sizing, et les pièges courants.

## Architecture risk — 3 niveaux

### Niveau 1 : GlobalRiskManager (`execution/risk.py`)

Checks **avant chaque ordre** (toutes stratégies confondues) :
- Max positions ouvertes global (actuellement 25, cible P7 : ~100)
- Perte journalière max (actuellement 50 EUR fixe, cible P7 : 5% du capital)
- Exposition max portfolio (90%)
- Intervalle min entre trades (60 secondes, anti rapid-fire)

### Niveau 2 : StrategyBudget (`execution/risk.py`)

Checks **par stratégie** (via le `bot_id`) :
- `max_allocation_pct` : % max du capital pour cette stratégie
- `max_open_positions` : positions simultanées max pour cette stratégie

Configuré dans `strategies.yaml` pour chaque stratégie.

### Niveau 3 : GeminiGlobalRiskManager (`strategies/gemini_global_risk_manager.py`)

Overlay appliqué sur **chaque signal BUY** dans le router :

**Position sizing** :
```
position_size = (capital × risk_pct × confidence) / |entry - stop_loss|
```
- `risk_pct` : 1% actuellement (cible P7 : 2% pour capital < 5k)
- `confidence` : vient du signal (0.3 à 1.0)
- `stop_loss` : calculé par ATR

**Stop-loss ATR** :
```
SL = entry_price - atr_multiplier × ATR(14, "4h")
```
- `atr_multiplier` : 3.0 par défaut
- L'ATR est calculé sur **le pair du signal** (pas un ATR global)

**Crash Protector** :
- Détecte une chute ≥ 7% en 30 minutes (rolling window sur candles 1m du primary pair)
- Action : ferme 50% des positions longues (les plus grosses d'abord)
- Suspension : bloque toute nouvelle entrée pendant 2 heures

## Confidence modulation (P5)

Le champ `confidence` du `TradingSignal` module directement la taille de position.

```python
# Dans le signal
TradingSignal(
    confidence=0.8,  # Haute conviction → 80% de la taille max
    ...
)
```

Bornes : clamp entre 0.3 et 1.0.
- `confidence=1.0` → position pleine (1% risk)
- `confidence=0.5` → moitié de position (0.5% risk)
- `confidence=0.3` → position minimale (0.3% risk)

Si une stratégie ne set pas `confidence`, default 1.0 (backward compat).

## Piège du sizing avec petit capital

Avec 1000 USDC et la règle 1% :
- Risk par trade = 10 USDC
- Si SL ATR est large (ex: 3000 USDC de distance sur BTC) → position = 10/3000 = 0.0033 BTC ≈ 28 USDC

C'est fonctionnel mais les returns absolus seront très bas. Un Sharpe de 0.3 avec 1k USDC peut devenir 0.6 avec 20k USDC et 2% risk (positions 4× plus grosses).

**Conséquence pour les backtests** : ne pas rejeter une stratégie uniquement sur son Sharpe ou son return. Regarder le **Profit Factor** et le **ratio avg_win/avg_loss** qui sont indépendants du sizing.

## Binance MIN_NOTIONAL

Binance rejette les ordres en dessous de 10 USDC (MIN_NOTIONAL). Avec la règle 1% à 1000 USDC et un SL large, la position peut tomber en dessous.

**Solution prévue P7** : ajouter un plancher de 10 USDC sur la position size.

## Types d'ordres et fees

| Signal | Type d'ordre | Fee | Raison |
|---|---|---|---|
| BUY | LIMIT | 0.075% maker | Économie fees |
| SELL profit target | LIMIT | 0.075% maker | Pas pressé |
| SELL stop-loss | MARKET | 0.075% taker | Exécution garantie |
| SELL trailing stop | MARKET | 0.075% taker | Exécution garantie |

**Règle critique** : quand un stop-loss se déclenche, **toujours annuler le limit sell profit target existant** avant d'émettre le market sell. Sinon double vente.

## Paramètres actuels (à revoir en P7)

```yaml
risk:
  risk_per_trade_pct: 1.0       # → 2.0 pour capital < 5k en P7
  atr_sl_multiplier: 3.0
  atr_sl_timeframe: "4h"
  atr_sl_period: 14
  crash_threshold_pct: 7.0
  crash_window_min: 30
  crash_close_pct: 0.5
  crash_suspend_hours: 2
  max_total_exposure_pct: 90.0
  max_daily_loss_eur: 50.0      # → 5% du capital en P7
```

## Ce qu'il ne faut JAMAIS faire

1. Bypasser le GlobalRiskManager pour placer un ordre directement
2. Émettre un stop-loss en limit order (toujours market pour l'exécution garantie)
3. Augmenter `risk_per_trade_pct` au-dessus de 3% (ruine rapide)
4. Oublier d'annuler le profit target limit quand le stop-loss se déclenche
5. Ignorer le crash protector (il est là pour une raison)
