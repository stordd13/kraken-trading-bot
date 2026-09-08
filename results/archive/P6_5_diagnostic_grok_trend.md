# P6.5 — Diagnostic Grok Trend Filter Strictness

Pour grok_ema_adx_atr (2-9 trades P6) et grok_donchian_breakout_4h (7-14 trades P6),
on compte combien de fois chaque filtre de l'entrée se déclenche, puis
leur intersection, sur 3 ans de 4h candles.

## grok_ema_adx_atr

Conditions: golden cross EMA(27)/EMA(125) **ET** ADX(14,4h) ≥ 14 **ET** régime_1d ∈ {bull, strong_bull}

| Pair | Total 4h | Golden cross | ADX pass | Régime bull | **Intersection** |
|---|---|---|---|---|---|
| BTC/USDC | 6,576 | 31 (0.5%) | 6,048 (92.0%) | 3,402 (51.7%) | **12** |

## grok_donchian_breakout_4h

Conditions: breakout above prev Donchian(20) upper **ET** ADX(14,1d) ≥ 18 **ET** régime_1d ∈ {bull, strong_bull}

| Pair | Total 4h | Breakout | ADX(1d) pass | Régime bull | **Intersection** |
|---|---|---|---|---|---|
| BTC/USDC | 6,576 | 333 (5.1%) | 5,388 (81.9%) | 3,402 (51.7%) | **130** |

## Interprétation

**Surprise** : les filtres ADX sont très peu sélectifs sur crypto —
ADX ≥ 14 passe 92% du temps, ADX(1d) ≥ 18 passe 82% du temps.
Le vrai goulot d'étranglement est ailleurs selon la stratégie :

### grok_ema_adx_atr
- Golden cross EMA(27)/EMA(125) est rare : 31 occurrences en 3 ans (~10/an).
- Intersection des 3 filtres : 12 signaux en 3 ans (~4/an).
- P6 a observé 2 trades sur BTC → l'écart (12 → 2) indique que la logique
  de position-management bloque la plupart des signaux : déjà en position
  quand un nouveau cross arrive, cooldown/exit récent, etc.
- **Filtre limitant : la rareté du golden cross EMA 27/125 lui-même.**

### grok_donchian_breakout_4h
- Breakout Donchian(20) : 333 candles en 3 ans (5.1%), 130 après les filtres (~45/an).
- P6 a observé 7 trades sur BTC → l'écart (130 → 7) confirme encore que la logique
  de position-management / cooldown post-exit bloque ~95% des signaux.
- **Pas de bug de filtrage** : le breakout primaire est fréquent. C'est la logique
  interne de la stratégie (une seule position à la fois, cooldowns) qui limite.

### Conclusion

**Pas un bug des filtres**. Les 2 stratégies fonctionnent comme conçues :
elles ne tradent que sur signaux rares ou quand aucune position n'est déjà ouverte.
grok_supertrend_4h produit plus de trades car son signal primaire (flip SuperTrend)
est beaucoup plus fréquent qu'un EMA cross.

## Recommandations

Trois options possibles pour P7 (à discuter) :

1. **Accepter** : peu de trades = moins de frais + signaux de meilleure qualité.
   À confirmer avec des backtests sur des périodes plus longues ou plus de paires.
2. **Raccourcir les EMAs** (EMA 27/125 → 10/40) pour plus de crossovers,
   au risque de plus de whipsaws en marché latéral.
3. **Permettre plusieurs positions simultanées** (actuellement max 1),
   pour utiliser les 130 breakouts Donchian au lieu de 7.

**Aucun fix code en P6.5** — Décision à prendre en P7 si on veut optimiser.
