# Skill: Nouvelle Stratégie

> Checklist complète pour implémenter, tester, et activer une nouvelle stratégie.
> Lire d'abord `docs/architecture.md` (flux d'un trade, multi-pair, conventions de code).

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
        # Accéder aux indicateurs via l'analyzer du pair (registry), jamais un analyzer créé à la main
        analyzer = self._analyzer_registry.get(self.pair) if self._analyzer_registry else self.analyzer
        if analyzer is None:
            return None

        rsi = analyzer.get_rsi(14, "4h")
        regime = analyzer.get_regime("1d")

        if rsi is not None and rsi < 30 and regime in ("bull", "strong_bull"):
            logger.info(
                "signal_generated",
                pair=self.pair,
                strategy=self.bot_id,
                regime=regime,
                rsi=rsi,
                reason="rsi_oversold_bull",
            )
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

- [ ] Hérite de `BaseStrategy`, accepte `pair: str` dans le constructeur
- [ ] Utilise `self.pair` partout (jamais de hardcode `BTC/USDC`, encore moins `XBT/USDC`)
- [ ] `Decimal` (via string) pour tous les prix et montants ; `UTC` pour les timestamps
- [ ] `structlog` pour tous les logs, chaque signal loggé avec metadata (régime, seuils, raison, pair)
- [ ] `order_type` ("limit" / "market") et `position_size_multiplier` dans `signal.metadata`
- [ ] `confidence` entre 0.3 et 1.0, `reason` descriptive
- [ ] Accède à l'analyzer via le registry, pas directement ; jamais de `MultiTimeframeAnalyzer()` manuel
- [ ] Persiste ses positions dans `open_positions` (pas en mémoire seule)
- [ ] Indicateurs lazy (EMA, SuperTrend, Donchian, VWAP, Ichimoku) pré-enregistrés avant le warmup,
      sinon le premier `get_*()` renvoie `None`
- [ ] Ne dépend d'aucun exchange (ni `binance`, ni `bybit` en dur) : les filtres de lot et les fees
      sont l'affaire du connecteur et du risk manager

### Choix du type d'ordre (fees Bybit EU)

Maker 0.10 % / taker 0.25 % : une sortie MARKET coûte 2.5× une entrée LIMIT. Entrées en LIMIT
(PostOnly côté connecteur) ; profit target en LIMIT ; stop-loss / trailing / timeout en MARKET
(exécution garantie, coût accepté). Une stratégie dont l'edge par trade est < 0.5 % ne survit pas
au round-trip limit/market de 0.35 % — le vérifier en backtest avec les fees Bybit (B4).

## Étape 2 — Enregistrer dans le router

Fichier : `src/krakenbot/strategies/__init__.py` — ajouter l'import.

Fichier : `src/krakenbot/strategies/multi_strategy_router.py` — ajouter le mapping dans le dict de
classes (le router est un fichier protégé : cet ajout de mapping est la seule modification attendue) :
```python
STRATEGY_CLASSES = {
    "ma_strategie": MaStrategie,
    # ...
}
```

## Étape 3 — Configurer dans strategies.yaml

Sous `multi_strategy_router.params.strategies` :
```yaml
ma_strategie_btc:
  active: false  # Toujours commencer inactive
  class: ma_strategie
  pair: BTC/USDC
  bot_id: ma_strategie_btc
  max_allocation_pct: 10.0
  order_size_usdc: 25
  params:
    some_param: 14
```

Chaque instance a son `bot_id` unique (une même classe peut tourner sur BTC, ETH et SOL).

## Étape 4 — Tests unitaires

Fichier : `tests/test_strategies/test_ma_strategie.py`

Tests minimum :
1. Instanciation avec pair BTC et pair ETH (vérifie multi-pair)
2. Signal BUY quand conditions remplies
3. Signal HOLD quand conditions pas remplies
4. Signal contient le bon pair, metadata complète
5. Pas de crash quand l'analyzer n'a pas de données

## Étape 5 — Backtest (voir `skills/backtest.md`)

Ajouter la stratégie au dispatch de `scripts/backtest.py` (`_NEEDS_4H`/`_NEEDS_1D`/…, instanciation,
`_LAZY_EMAS`, `needs_mtf`), puis :

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
- Profit Factor > 1.5 **avec les fees Bybit** (maker 0.10 / taker 0.25)
- Cross-validate cohérent (test/train > 0.5)
- Min 30 trades sur 3 ans
- Bat Buy & Hold ou DCA fixe en Sharpe

## Étape 6 — Activer en paper

Dans `strategies.yaml` : `active: true`. Le bot la charge automatiquement au prochain restart. 4+
semaines de paper avant tout live (voir `ROADMAP.md`).

## À NE JAMAIS FAIRE

- Créer un `MultiTimeframeAnalyzer` manuellement (utiliser le registry)
- Hardcoder une paire ou un exchange
- Bypasser le `GeminiGlobalRiskManager` / `GlobalRiskManager`
- Persister les positions uniquement en mémoire (utiliser la table `open_positions`)
- Oublier de cancel le limit sell profit target avant d'émettre un stop-loss market (double vente)
- Modifier `MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine` au-delà du mapping
  de classes sans review humain
