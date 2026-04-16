# Skill: Nouvelle Stratégie

> Checklist complète pour implémenter, tester, et activer une nouvelle stratégie.

## Étape 1 — Créer la classe

Fichier : `src/krakenbot/strategies/<nom_snake_case>.py`

```python
from decimal import Decimal
import structlog
from krakenbot.strategies.base import BaseStrategy, TradingSignal

logger = structlog.get_logger(__name__)

class MaStrategie(BaseStrategy):
    """Description courte de la stratégie."""
    
    def __init__(self, bot_id: str, strategy_params: dict, pair: str = "BTC/USDC", **kwargs):
        super().__init__(bot_id=bot_id, strategy_params=strategy_params, pair=pair, **kwargs)
        # Params spécifiques
        self.some_param = strategy_params.get("some_param", 14)
    
    def get_name(self) -> str:
        return "ma_strategie"
    
    def get_config(self) -> dict:
        return {
            "bot_id": self.bot_id,
            "pair": self.pair,
            "some_param": self.some_param,
        }
    
    async def on_ohlc(self, candle_data: dict, interval: int) -> None:
        """Reçoit chaque candle du bon pair (filtré par le router)."""
        # Mettre à jour l'état interne si nécessaire
        pass
    
    async def generate_signal(self) -> TradingSignal | None:
        """Générer un signal BUY/SELL/HOLD."""
        # Accéder aux indicateurs via l'analyzer
        analyzer = self._analyzer_registry.get(self.pair) if self._analyzer_registry else self.analyzer
        if analyzer is None:
            return None
        
        rsi = analyzer.get_rsi(14, "4h")
        regime = analyzer.get_regime("1d")
        
        if rsi is not None and rsi < 30 and regime in ("bull", "strong_bull"):
            return TradingSignal(
                signal_type="BUY",
                pair=self.pair,
                price=Decimal(str(analyzer.get_close("4h"))),
                confidence=0.8,
                reason="RSI oversold in bull regime",
                strategy=self.bot_id,
                metadata={
                    "order_type": "limit",
                    "position_size_multiplier": 1.0,
                    "limit_price": Decimal(str(analyzer.get_close("4h") * 0.999)),
                    "regime": regime,
                    "rsi": rsi,
                },
            )
        return None
```

### Checklist obligatoire

- [ ] Hérite de `BaseStrategy`
- [ ] Accepte `pair: str` dans le constructeur
- [ ] Utilise `self.pair` partout (jamais de hardcode)
- [ ] `Decimal` pour tous les prix et montants
- [ ] `structlog` pour tous les logs
- [ ] `order_type` dans `signal.metadata` ("limit" ou "market")
- [ ] `position_size_multiplier` dans `signal.metadata`
- [ ] `confidence` entre 0.3 et 1.0 dans le signal
- [ ] `reason` descriptive dans le signal
- [ ] Accède à l'analyzer via le registry, pas directement

## Étape 2 — Enregistrer dans le router

Fichier : `src/krakenbot/strategies/__init__.py` — ajouter l'import.

Fichier : `src/krakenbot/strategies/multi_strategy_router.py` — ajouter le mapping dans le dict de classes :
```python
STRATEGY_CLASSES = {
    "ma_strategie": MaStrategie,
    # ...
}
```

## Étape 3 — Configurer dans strategies.yaml

```yaml
ma_strategie_btc:
  active: false  # Toujours commencer inactive
  class: ma_strategie
  pair: BTC/USDC
  max_allocation_pct: 10.0
  order_size_usdc: 25
  params:
    some_param: 14
```

## Étape 4 — Tests unitaires

Fichier : `tests/test_strategies/test_ma_strategie.py`

Tests minimum :
1. Instanciation avec pair BTC et pair ETH (vérifie multi-pair)
2. Signal BUY quand conditions remplies
3. Signal HOLD quand conditions pas remplies
4. Signal contient le bon pair, metadata complète
5. Pas de crash quand l'analyzer n'a pas de données

## Étape 5 — Backtest (voir skill backtest.md)

```bash
poetry run python scripts/backtest.py \
    --strategy ma_strategie \
    --pair BTC/USDC \
    --exchange binance \
    --days 1095 \
    --capital 1000 \
    --cross-validate
```

Critères minimum pour activer :
- Profit Factor > 1.5
- Cross-validate cohérent (test/train > 0.5)
- Min 30 trades sur 3 ans

## Étape 6 — Activer en paper

Dans `strategies.yaml` : `active: true`. Le bot la charge automatiquement au prochain restart.

## À NE JAMAIS FAIRE

- Ne pas créer de MultiTimeframeAnalyzer manuellement
- Ne pas hardcoder de paire
- Ne pas bypasser le GeminiGlobalRiskManager
- Ne pas persister les positions uniquement en mémoire (utiliser la table `open_positions`)
- Ne pas oublier de cancel le limit sell avant d'émettre un stop-loss market
