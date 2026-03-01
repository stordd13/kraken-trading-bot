# AGENT — Implémenter & Backtester 3 Nouvelles Stratégies (Track A)

> **Tu es un agent Claude Code travaillant sur KrakenBot.**
> Lis d'abord `KRAKENBOT_CONTEXT.md` pour comprendre le projet.
> Ta mission : implémenter 3 nouvelles stratégies trend-following 4h, les backtester sur 9 ans, et produire un rapport de résultats.

---

## CONTEXTE

On vient de backtester 7 stratégies. Résultats :
- **SuperTrend 4h** : Sharpe 0.49, PF 2.81, MaxDD 2.4% → STAR du portfolio
- **Grid ATR** : +1643% sur 9 ans, surperforme buy-and-hold
- **DCA Weekly** : Sharpe 0.74, accumulation disciplinée
- **EMA Cross** : PF 2.68 mais seulement 27 trades en 9 ans
- **3 strats Gemini (scalping 5m, mean-reversion 15m, trend momentum)** : toutes perdantes → KILL

**Le pattern gagnant est clair :**
- Timeframe 4h + filtre régime 1d
- Trend-following mécanique (pas de mean-reversion)
- Stops ATR adaptatifs (3.0-3.5×)
- Indicateur robuste et simple (≤ 3 conditions d'entrée)

On veut 3 nouvelles strats **décorrélées du SuperTrend** pour diversifier le portfolio.

---

## PRÉ-REQUIS

- Le container Docker `krakenbot-db` doit tourner (`docker ps`)
- La DB contient 9 ans de données 4h/1d (2017-08 → 2026-03)
- Le backtest engine (`scripts/backtest.py`) fonctionne (testé lors de la Phase -1A)
- Les corrections de la Phase -1A sont en place (lazy indicators, _is_4h flags, etc.)

---

## ÉTAPE 1 — Ajouter les indicateurs manquants au MultiTimeframeAnalyzer

**Fichier : `src/krakenbot/indicators/multi_timeframe.py`**

Avant d'implémenter les stratégies, il faut ajouter 2 nouveaux indicateurs au MultiTimeframeAnalyzer. Lire le code existant de `multi_timeframe.py` pour comprendre le pattern (lazy creation, Decimal, etc.).

### 1.1 Ichimoku Cloud

Créer `src/krakenbot/indicators/ichimoku.py` et exposer via `get_ichimoku(tf)` dans MultiTimeframeAnalyzer.

```python
# Paramètres Ichimoku (standards)
TENKAN_PERIOD = 9      # Conversion line : (highest_high + lowest_low) / 2 sur 9 périodes
KIJUN_PERIOD = 26      # Base line : (highest_high + lowest_low) / 2 sur 26 périodes
SENKOU_B_PERIOD = 52   # Leading Span B : (highest_high + lowest_low) / 2 sur 52 périodes
DISPLACEMENT = 26      # Projection des Senkou Spans

# Output dict :
{
    'tenkan': Decimal,           # Tenkan-sen (conversion line)
    'kijun': Decimal,            # Kijun-sen (base line)
    'senkou_a': Decimal,         # Senkou Span A = (tenkan + kijun) / 2 (projeté)
    'senkou_b': Decimal,         # Senkou Span B = (high52 + low52) / 2 (projeté)
    'chikou': Decimal,           # Chikou Span = close actuel (comparé au close -26)
    'cloud_top': Decimal,        # max(senkou_a, senkou_b)
    'cloud_bottom': Decimal,     # min(senkou_a, senkou_b)
}
```

**Note** : Les Senkou Spans sont normalement projetés 26 périodes dans le futur. Pour le trading en temps réel, on utilise les valeurs ACTUELLES du cloud (calculées il y a 26 périodes). Implémenter simplement : `senkou_a` = moyenne de tenkan et kijun d'il y a 26 périodes, `senkou_b` = mid-range d'il y a 52 périodes projeté 26 périodes.

### 1.2 Donchian Channel

Créer `src/krakenbot/indicators/donchian.py` et exposer via `get_donchian(tf, period_upper=20, period_lower=10)`.

```python
# Output dict :
{
    'upper': Decimal,    # Highest high sur period_upper périodes
    'lower': Decimal,    # Lowest low sur period_lower périodes
    'middle': Decimal,   # (upper + lower) / 2
    'width': Decimal,    # (upper - lower) / price (normalisé)
}
```

### Pattern à suivre

Regarde comment `supertrend.py`, `bollinger.py`, etc. sont implémentés :
- Classe avec `update(candle)` et propriétés
- Lazy creation dans MultiTimeframeAnalyzer (créé au premier appel)
- Tous les calculs en **Decimal** (jamais float)
- Warmup period avant de retourner des valeurs valides

---

## ÉTAPE 2 — Implémenter les 3 stratégies

Chaque stratégie hérite de `BaseStrategy`, suit le même pattern que `grok_supertrend_4h.py`.
**Lire `grok_supertrend_4h.py` EN ENTIER comme référence** — c'est le modèle à suivre.

### 2.1 GrokIchimokuCloudBreakoutV1

**Fichier** : `src/krakenbot/strategies/grok_ichimoku_cloud_4h.py`
**bot_id** : `ichimoku_cloud_4h`

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 4h (trigger) + 1d (filtre régime) |
| **Macro filtre** | Régime 1d = bull/strong_bull + ADX(14, 1d) > 20 |
| **Entrée BUY** | Close > cloud_top (Kumo upper) ET close_prev ≤ cloud_top_prev (breakout, pas déjà au-dessus) |
| **Exit** | Close < cloud_bottom → MARKET |
| **Exit régime** | Régime 1d → bear/strong_bear → MARKET |
| **Stop initial** | -3.0 × ATR(14, 4h) sous entry |
| **Trailing** | Après +1.5×ATR profit → trail au cloud_bottom (dynamique, mis à jour chaque 4h) |
| **Taille** | 50 USDC, max 1 position, max 15% capital |
| **Confidence** | ADX(14, 4h) / 100.0 |

**Note simplification** : On enlève la condition "Chikou Span > close" pour ne pas trop filtrer (risque de 27-trades-en-9-ans comme EMA cross). Seulement 2 conditions d'entrée : breakout cloud + régime bull.

### 2.2 GrokDonchianChannelBreakoutV1

**Fichier** : `src/krakenbot/strategies/grok_donchian_breakout_4h.py`
**bot_id** : `donchian_breakout_4h`

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 4h (trigger) + 1d (filtre régime) |
| **Macro filtre** | Régime 1d = bull/strong_bull + ADX(14, 1d) > 18 |
| **Entrée BUY** | Close > Donchian upper(20) ET close_prev ≤ donchian_upper_prev (breakout frais) |
| **Exit** | Close < Donchian lower(10) → MARKET (trailing naturel, comme SuperTrend) |
| **Exit régime** | Régime 1d → bear/strong_bear → MARKET |
| **Stop initial** | -3.5 × ATR(14, 4h) sous entry |
| **Trailing** | Donchian lower(10) sert de trailing stop naturel (mis à jour chaque 4h) |
| **Taille** | 50 USDC, max 1 position, max 15% capital |
| **Confidence** | (close - donchian_upper) / ATR(14, 4h) clampé à [0.3, 1.0] |

**Note** : On retire la condition volume > 1.5× MA (pas fiable sur 4h, ajoute de la complexité). Entrée pure breakout + régime.

### 2.3 GrokVWAPTrendV1

**Fichier** : `src/krakenbot/strategies/grok_vwap_trend_4h.py`
**bot_id** : `vwap_trend_4h`

| Aspect | Détail |
|--------|--------|
| **Timeframe** | 4h (trigger) + 1d (filtre régime) |
| **Macro filtre** | Régime 1d = bull/strong_bull |
| **Entrée BUY** | Close croise au-dessus de VWAP(20, 4h) ET close_prev ≤ vwap_prev (crossover) |
| **Exit** | Close croise sous VWAP(20, 4h) → MARKET |
| **Exit régime** | Régime 1d → bear/strong_bear → MARKET |
| **Stop initial** | -3.0 × ATR(14, 4h) sous entry |
| **Trailing** | Après +2.0×ATR → trail au VWAP (dynamique) |
| **Taille** | 50 USDC, max 1 position, max 15% capital |
| **Confidence** | RSI(14, 4h) / 100.0 |

**Note VWAP** : On n'a pas de "vrai" VWAP intraday. Implémenter comme une EMA pondérée par le volume sur 20 candles 4h :
```python
# VWAP rolling = sum(close * volume, 20) / sum(volume, 20)
# C'est un proxy raisonnable pour du 4h
```
Si l'implémentation est trop complexe ou que le VWAP se comporte comme une simple EMA, **noter l'observation** — c'est une info utile.

---

## ÉTAPE 3 — Backtester les 3 stratégies

Lancer chaque stratégie sur **9 ans** (2017-08 → 2026-03) avec :
- Capital : 1000 USDC
- Fees : maker 0.16%, taker 0.26%, spread 0.02%, slippage 0.01%
- Utiliser le SignalBacktester (comme SuperTrend)

### Commandes (adapter selon les arguments exacts de backtest.py)

```bash
# 1. Ichimoku Cloud Breakout
poetry run python scripts/backtest.py --strategy ichimoku_cloud_4h --days 3100 --interval 4h --capital 1000 --save

# 2. Donchian Channel Breakout
poetry run python scripts/backtest.py --strategy donchian_breakout_4h --days 3100 --interval 4h --capital 1000 --save

# 3. VWAP Trend
poetry run python scripts/backtest.py --strategy vwap_trend_4h --days 3100 --interval 4h --capital 1000 --save
```

### Métriques à collecter (même format que Phase -1A)

```
═══════════════════════════════════════════════════
BACKTEST: [NomStratégie] ([bot_id])
Période: [start] → [end] ([N] jours)
Capital: 1000 USDC
═══════════════════════════════════════════════════

Return total          : XX.XX %
Sharpe ratio          : X.XX
Sortino ratio         : X.XX
Profit Factor         : X.XX
Max Drawdown          : -XX.XX %
Win Rate              : XX.X %
Nombre de trades      : XXXX
Avg Win               : +X.XX %
Avg Loss              : -X.XX %
Avg Win/Avg Loss      : X.XX

Performance par régime de marché :
  STRONG_BULL : XX.XX %  (N trades)
  BULL        : XX.XX %  (N trades)
  NEUTRAL     : XX.XX %  (N trades)
  BEAR        : XX.XX %  (N trades)
  STRONG_BEAR : XX.XX %  (N trades)

vs Buy-and-Hold : +XXX.XX %
vs SuperTrend 4h : Sharpe X.XX, PF X.XX

VERDICT : ✅ KEEP / ❌ KILL / ⚠️ WATCH
```

---

## ÉTAPE 4 — Analyse de corrélation

**C'est l'étape la plus importante après les métriques brutes.**

Pour chaque nouvelle stratégie qui survit (Sharpe > 0.4, PF > 1.5) :

Comparer les signaux BUY avec ceux du SuperTrend 4h :
- Sur la même période, combien de signaux BUY de la nouvelle strat coïncident (même candle ±2) avec un signal BUY SuperTrend ?
- Un ratio < 30% = bonne décorrélation (stratégies complémentaires)
- Un ratio > 60% = trop corrélé (même signal déguisé, peu de valeur ajoutée)

**Si tu ne peux pas facilement extraire les signaux pour comparaison** (le backtest engine ne le permet peut-être pas), note-le et passe à la suite. On fera l'analyse manuellement.

---

## LIVRABLE FINAL

Créer **`results/backtest_new_strategies_results.md`** contenant :

1. **Tableau récapitulatif** des 3 nouvelles strats + SuperTrend (référence)
2. **Bloc détaillé** de chaque strat (métriques complètes)
3. **Analyse de corrélation** avec SuperTrend (si possible)
4. **Problèmes rencontrés** (indicateurs manquants, bugs, etc.)
5. **Recommandation finale** : quelles strats intégrer au portfolio

### Critères de survie
- Sharpe > 0.4
- Max DD < 15% (plus strict que Phase -1A — on veut de la qualité)
- PF > 2.0
- Nombre de trades > 50 sur 9 ans (pas de strat quasi-inactive)
- Corrélation signaux avec SuperTrend < 50%

---

## RAPPELS

- **Lire `grok_supertrend_4h.py`** comme modèle pour les 3 strats
- **Decimal** pour tous les prix/montants
- **structlog** pour le logging
- **Ne PAS modifier** les stratégies existantes ni le backtest engine
- **Indicateurs Ichimoku et Donchian** : les créer dans `src/krakenbot/indicators/` en suivant le pattern existant
- **Simplifier les conditions d'entrée** : max 2-3 critères. Pas de sur-sélectivité.
- **Si une strat ne marche pas** : noter pourquoi, ne pas essayer de l'optimiser
- **Le VWAP 4h est un proxy** — si ça se comporte comme une EMA, c'est une info utile à noter
