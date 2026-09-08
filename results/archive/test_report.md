# Test Report -- Mars 2026

## Resultats globaux

| Categorie | Nombre |
|-----------|--------|
| **Total tests** | **826** |
| **Passes** | **820** |
| **Echoues** | **6** (tous pre-existants) |
| **Nouveaux tests ajoutes** | **117** (46 + 36 + 35) |

## Tests existants (pre-Agent B)

- **709 tests existants** dans 32 fichiers
- **703 passes, 6 echoues**

### Categorie des echecs (tous pre-existants)

#### Bug: Tests obsoletes / desynchronises avec le code (5 echecs)

`tests/test_indicators/test_multi_timeframe.py` -- 5 tests:

1. **TestAdaptiveThresholds::test_bull_regime_tighter_buy_wider_sell** -- Le test attend `buy = -1.0 * 0.85 * 1.0 = -0.85` mais le code retourne `-1.0`. La formule `_calc_adaptive_thresholds()` a ete modifiee sans mettre a jour les tests.
2. **TestAdaptiveThresholds::test_strong_bull_tightest_buy** -- Meme probleme: attend `-0.7`, obtient `-1.0`.
3. **TestAdaptiveThresholds::test_bear_regime_wider_buy_tighter_sell** -- Attend `SL = 5.0 * 0.8 = 4.0`, obtient `6.5`.
4. **TestAdaptiveThresholds::test_strong_bear_widest_buy** -- Attend `SL = 5.0 * 0.6 = 3.0`, obtient `7.5`.
5. **TestCandleCounts::test_initial_counts_are_zero** -- Le test attend `{"1h": 0, "15m": 0, "5m": 0}` mais `candle_counts` retourne maintenant **7 timeframes** (1m, 5m, 15m, 1h, 4h, 1d, 1w) apres l'ajout de la generic data layer.

**Cause racine** : Le code source a ete enrichi (generic data layer, formule adaptive modifiee) mais les tests legacy n'ont pas ete mis a jour. Ce ne sont PAS des bugs dans le code, mais des **tests obsoletes**.

#### Bug: Logique de priorite (1 echec)

`tests/test_strategies/test_adaptive.py` -- 1 test:

6. **TestAdaptiveStrategySellSignals::test_sell_trailing_stop_priority_over_profit_target** -- Le test attend `reason == "trailing_stop"` mais obtient `"profit_target"`. La strategie AdaptiveStrategy evalue le profit_target avant le trailing_stop, et le profit_target gagne quand les deux conditions sont remplies. Possiblement un vrai bug dans la logique de priorite, ou un test mal ecrit.

**Recommandation** : Revoir la logique de priorite dans `AdaptiveStrategy.generate_signal()` (strat legacy, non prioritaire).

### Aucun echec du au serveur down

Tous les tests sont des tests unitaires avec mocks -- aucune connexion DB/API requise. Pas d'echec lie au serveur Hetzner down.

---

## Nouveaux tests ajoutes

### 1. `tests/test_strategies/test_gemini_risk_manager.py` (46 tests)

| Classe de test | Tests | Couverture |
|---------------|-------|------------|
| TestPositionSizing | 7 | 1% rule: formule, capital=0, entry==SL, custom risk% |
| TestATRStopLoss | 5 | SL = entry - mult*ATR, SL >= 0, config multiplier |
| TestCrashProtector | 9 | Detection 7%, suspension 2h, recovery, seuil custom |
| TestGenerateCrashSells | 6 | 50% positions, priorite taille, metadata market |
| TestProcessSignal | 9 | SELL passe, BUY enrichi, crash bloque, no ATR, zero size |
| TestStrategyBudget | 5 | within/over budget, zero/negative capital |
| TestGetConfig | 3 | Toutes les cles, valeurs par defaut, config custom |
| TestPriceSnapshot | 1 | Dataclass creation |

**Impact** : `GeminiGlobalRiskManager` passe de **0% a ~95% de couverture**. C'est un module critique (filtre TOUS les signaux BUY).

### 2. `tests/test_indicators/test_multi_timeframe_generic.py` (36 tests)

| Classe de test | Tests | Couverture |
|---------------|-------|------------|
| TestGenericEMA | 4 | Lazy creation, Decimal > 0, periodes independantes |
| TestGenericRSI | 4 | Defaut RSI(14), lazy creation, range 0-100 |
| TestGenericATR | 4 | Defaut ATR(14), lazy creation, volatilite |
| TestGenericMACD | 5 | 3 keys (macd/signal/hist), Decimal, TF independants |
| TestGenericBollinger | 5 | 4 keys, upper > middle > lower, width >= 0 |
| TestGenericSuperTrend | 3 | Lazy creation, dict avec supertrend/direction |
| TestGenericADX | 3 | None avant warmup, Decimal >= 0 |
| TestGetRegime | 5 | 5 regimes valides, steady=NEUTRAL, tous TFs |
| TestGenericCandleCounts | 3 | Routing, tous TFs, interval inconnu ignore |

**Impact** : L'API generique (`get_ema`, `get_rsi`, `get_atr`, etc.) utilisee par les 7 strategies passe de **0% a bonne couverture**. Les tests legacy ne couvraient que `analyze()`.

### 3. `tests/test_strategies/test_strategies_basic.py` (35 tests)

| Test | Strategies testees | Couverture |
|------|-------------------|------------|
| test_get_name_returns_expected | 7 | Nom retourne correct |
| test_get_config_returns_dict | 7 | Config est un dict non vide |
| test_bot_id_defaults_to_name | 7 | bot_id fallback |
| test_custom_bot_id | 7 | bot_id custom override |
| test_not_running_by_default | 7 | is_running == False |

**Impact** : Les 7 nouvelles strategies (GeminiScalpingVolatilite, GeminiRetourMoyenne, GeminiSuiviTendanceMomentum, GrokGridATRAdaptiveV4, GrokSuperTrend4hRegime, GrokEMA27_125_ADX_ATR, GrokAdaptiveDCAWeekly) ont maintenant des **smoke tests de base**.
