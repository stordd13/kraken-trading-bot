# KrakenBot — Contraintes post-B4 pour toute nouvelle stratégie

> Produit du post-mortem B4 (septembre 2026). Ce document est le **filtre d'entrée** :
> toute idée de stratégie — humaine, IA, ou tirée d'un article — doit passer le
> ticket d'entrée (§ 6) sur le papier avant qu'une ligne de code soit écrite.
> Contexte complet : `PROJECT_CONTEXT.md` · verdict : `results/B4_bybit_backtest_report.md`.

---

## 1. Le verdict B4 en trois phrases

24 combinaisons stratégie × paire (P6) puis 212 configurations en grid search
cross-validé et 280 fenêtres de walk-forward (P7) : **zéro survivant** aux critères,
sur données assainies (end-stamps, look-ahead éliminé), moteur certifié (liquidation
terminale, fees maker/taker exactes) et coûts mesurés par paire. La meilleure config
out-of-sample de toute la campagne fait Sharpe 0.04 (grid BTC, espacement 3 %) contre
un buy-and-hold à 0.84. La seule config brillante en cross-validation (SuperTrend ETH
×2.0 : Sharpe 0.78, PF 3.01) tombe à −0.10 en walk-forward — tout son score venait
d'une seule fenêtre.

## 2. La structure de coûts (mesurée, non négociable)

Bybit EU spot, VIP0, vérifiée sur le compte ; spread/slippage mesurés sur 21 relevés
horaires couvrant nuit et jour (`results/q3_orderbook.jsonl`) :

| Poste | BTC/USDC | ETH/USDC | SOL/USDC |
|---|---|---|---|
| Entrée LIMIT PostOnly (maker) | 0.10 % | 0.10 % | 0.10 % |
| Sortie MARKET (taker + spread + slippage) | 0.29 % | 0.30 % | 0.38 % |
| **Round-trip limit/market** (stop, trailing, timeout) | **0.39 %** | **0.40 %** | **0.48 %** |
| Round-trip limit/limit (deux jambes maker) | 0.24 % | 0.25 % | 0.33 % |

Conséquence arithmétique : un trade moyen doit capturer un mouvement nettement
supérieur à ~0.4 % pour exister. Les mèches nocturnes EU atteignent 40 bps et le
spread s'élargit précisément pendant les mouvements (mesuré : ETH à 0.124 % en
pleine impulsion) — un stop paie le spread du moment où il se déclenche.

## 3. La tension centrale mise en évidence par B4

- **Significativité** : les stratégies signal 4h génèrent 2 à 5 trades par fenêtre
  de walk-forward. À ce rythme, distinguer un edge du bruit est impossible — le
  meilleur combo P6 (Sharpe test 0.29) reposait sur 13 trades.
- **Coûts** : multiplier les trades multiplie les round-trips à 0.24–0.48 %.

Il faut plus de trades pour prouver et moins de trades pour payer. Toute proposition
doit dire explicitement comment elle résout cette tension. Les deux issues connues :
(a) très basse rotation avec des mouvements capturés énormes devant les coûts
(détention en semaines/mois, mouvements 20-50 %) ; (b) changer d'objectif — améliorer
le B&H (accumulation systématique + overlay de risque) plutôt que chercher de l'alpha
de rotation.

## 4. Le benchmark à battre

Sur 2023-04 → 2026-04, fees Bybit, données saines :

| | BTC | ETH | SOL |
|---|---|---|---|
| Buy & Hold — Sharpe | 0.84 | 0.38 | 0.30 |

Toute stratégie long-only spot se juge contre le B&H de son actif : Sharpe supérieur,
ou MaxDD drastiquement inférieur à return comparable. Le DCA benchmark se compare en
**return/MaxDD uniquement** (son Sharpe 2+ est un artefact de courbe majoritairement
cash). « Positif dans l'absolu » ne suffit pas : le B&H est gratuit.

## 5. Ce qui est déjà mort (ne pas re-proposer sans mécanisme nouveau)

- **Scalping 5m/15m et mean reversion court terme** : morts sur Kraken, Binance et
  Bybit (P6 ×2, coûts ×5 vs Binance BNB) ; 24-36 % de candles 1m plates sur Bybit EU.
- **Grid trading sur ces fees** : 0/48 configs SOL (bug de comptabilité en prime,
  dette 14), meilleur grid BTC à Sharpe OOS 0.04 — dix fois sous le seuil.
- **Stratégies signal 4h fine-tunées** (SuperTrend, Donchian, EMA/ADX, momentum) :
  0/35 en walk-forward ; le tuning ne sauve pas un edge inexistant.
- **HFT, trailing < 5 %, grid sans biais directionnel en bear** : leçons historiques.
- Doctrine : une famille tuée deux fois ne revient qu'avec un **mécanisme**
  nouveau, pas un paramétrage nouveau.

## 6. Ticket d'entrée (obligatoire, sur le papier, avant tout code)

Toute proposition fournit ces sept réponses :

1. **Mécanisme** : pourquoi cet edge existe-t-il ? Qui est le perdant structurel de
   l'autre côté du trade, et pourquoi persiste-t-il ?
2. **Fréquence attendue** : trades par mois, durée de détention.
3. **Mouvement capturé attendu par trade**, comparé au round-trip § 2 de la paire.
4. **Résolution de la tension § 3** : d'où vient la significativité statistique ?
5. **Comportement en bear market** (2022 est dans les données : que fait-elle ?).
6. **Données nécessaires** : couvertes par l'existant (§ 7) ou non.
7. **Critère de falsification** : quel résultat de backtest tuerait l'idée ?
   (S'il n'y en a pas, l'idée n'est pas testable.)

## 7. Contraintes d'environnement

- **Spot long-only, USDC**, Bybit EU. Pas de short, pas de margin, pas de dérivés.
- Capital : 1k USDC au départ, scaling 5k → 20k sur preuve. Plancher de position
  5 USDC (viser ≥ 10 pour que les fees ne mangent pas le trade).
- **Données** : Binance 2021-01 → 2026-04 (7 TF, end-stamped ; trou SOL de 455 j
  en 2022-23, BTC/ETH 164 j) ; Bybit EU depuis 2025-06 (ETH/SOL depuis 2025-06-27),
  collecte continue. Pas de données de sentiment, d'orderflow ou de funding en base.
- **Protocole non négociable** : 3+ ans de backtest → cross-validation →
  walk-forward → 4+ semaines de paper → live progressif. Critères écrits avant les
  runs, appliqués tels quels.
- **Pas de ML** avant profit live confirmé (P11+). Un filtre ML sur du bruit reste
  du bruit.
- **Cap : deux familles maximum** entrent en backtest par cycle de R&D. Le pipeline
  rend le test presque gratuit (24 combos en 22 min) — c'est précisément le risque :
  tester cinquante idées, c'est du data mining, et la cinquantième qui « marche »
  est fausse par construction.

## 8. Annexe — prompts pour une IA externe

**Passe 1 (adversariale, à faire digérer avant toute génération) :**
« Voici le rapport final d'une campagne de backtests (B4), le contexte projet et ce
document de contraintes. Attaque les conclusions : où le raisonnement est-il
faible ? Quelles explications alternatives au zéro survivant n'avons-nous pas
éliminées (design des fenêtres de walk-forward, espace de configs exploré, modèle
de coûts trop pessimiste ou trop optimiste, période de marché) ? Qu'aurions-nous dû
mesurer et n'avons pas mesuré ? Sois spécifique et réfère-toi aux chiffres. »

**Passe 2 (générative, seulement après la passe 1) :**
« Sous les contraintes du document (coûts § 2, tension § 3, benchmark § 4, morts
§ 5, environnement § 7), propose au maximum 3 familles de stratégies. Chacune au
format du ticket d'entrée § 6, les sept points remplis. Toute proposition sans
mécanisme explicite (§ 6.1) ou sans critère de falsification (§ 6.7) sera rejetée
sans lecture du reste. Les recombinations d'indicateurs techniques sans mécanisme
sont exclues d'office. »
