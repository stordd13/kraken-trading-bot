# KrakenBot — Contraintes post-B4 pour toute nouvelle stratégie

> Produit du post-mortem B4 (septembre 2026). Ce document est le **filtre d'entrée** :
> toute idée de stratégie — humaine, IA, ou tirée d'un article — doit passer le
> ticket d'entrée (§ 6) sur le papier avant qu'une ligne de code soit écrite.
> Contexte complet : `PROJECT_CONTEXT.md` · verdict : `results/B4_bybit_backtest_report.md` (portée
> requalifiée par l'addendum du 16/09 en tête du rapport — audit
> `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md`) · journal des essais : `docs/RESEARCH_LOG.md`.
> Critère d'arrêt pré-enregistré (clôture de famille, alpha-stop projet, kill-switch live) : § 10, adopté le
> 2026-09-23 avec la révision v2.1 de `docs/protocole_c3.md`.

---

## 1. Le verdict B4 en trois phrases (portée requalifiée le 16/09)

24 combinaisons stratégie × paire (P6) puis 212 configurations en grid search
cross-validé et 280 fenêtres de walk-forward (P7) : **zéro configuration sélectionnée
sous ce protocole avec cet instrument**, sur données assainies (end-stamps, look-ahead
éliminé), comptabilité des fills réglée (liquidation terminale, fees maker/taker par
site de fill) et coûts mesurés par paire. L'audit red-team du 16/09 a invalidé
l'instrument de mesure — métriques (D1-D6, corrigées en C1), replay (corrigé en C2, mergé)
et walk-forward non chronologique (C3) : aucune comparaison chiffrée de Sharpe, MaxDD
ou PF n'est reprise ici. Le rejeu sous instrument réparé a eu lieu (20/09, `inconclusif`,
`results/rejeu_grid_report.md`) ; toute sélection relève du protocole C3
(`docs/protocole_c3.md`, gelé), dont l'outillage refuse aujourd'hui l'artefact du rejeu à
l'entrée (voir l'addendum en tête de `results/B4_bybit_backtest_report.md`). Ce qui reste établi :
aucune stratégie n'est validée pour le déploiement par cette campagne ; les fees et
coûts mesurés ; les comptes d'exécutions du simulateur, cités comme tels.

## 2. La structure de coûts (mesurée, non négociable)

Bybit EU spot, VIP0, vérifiée sur le compte ; spread/slippage mesurés sur 126 relevés de
carnet (42 par paire, du 14/09 10:46 au 15/09 06:47 UTC, dont 10 nocturnes 00–05 UTC,
`results/q3_orderbook.jsonl` ; règle GATE B : `max(p75 global, p75 nocturne)` arrondi au bp
supérieur, slippage ≥ 2 bps) :

| Poste | BTC/USDC | ETH/USDC | SOL/USDC |
|---|---|---|---|
| Entrée LIMIT PostOnly (maker) | 0.10 % | 0.10 % | 0.10 % |
| Sortie MARKET (taker + spread + slippage) | 0.29 % | 0.30 % | 0.38 % |
| **Round-trip limit/market** (stop, trailing, timeout) | **0.39 %** | **0.40 %** | **0.48 %** |
| Round-trip limit/limit (deux jambes maker, fees débitées par le moteur) | 0.20 % | 0.20 % | 0.20 % |

**Fees débitées par le moteur B4** (ce que le modèle facture réellement) : limit/limit =
0.10 % + 0.10 % = **0.20 %** sur les trois paires — les deux jambes maker sont facturées
**sans** spread/slippage explicite ; limit/market = 0.35 % de fees + frictions mesurées
(spread + slippage par paire) = 0.39 / 0.40 / 0.48 %. Les 0.24-0.33 % affichés ici
jusqu'au 16/09 pour le limit/limit incluaient une hypothèse de friction maker non
modélisée (audit § 8) ; les chiffres limit/market sont inchangés. Les totaux nominaux
maker/taker (BTC 0,39 % / ETH 0,40 % / SOL 0,48 %) sont des sommes de taux et de
paramètres de calibration (GATE B), pas un coût réel constant garanti par transaction.

**Frictions non reproduites par le modèle** : la file d'attente, les non-exécutions,
les remplissages partiels et la sélection adverse ne sont pas reproduits par le
remplissage complet au toucher ; leur effet sur ces stratégies et son amplitude ne
sont pas quantifiés par B4 (audit § 7-8).

Conséquence arithmétique : un trade moyen doit capturer un mouvement nettement
supérieur à ~0.4 % pour exister. Les mèches nocturnes EU atteignent 40 bps et le
spread s'élargit précisément pendant les mouvements (mesuré : ETH à 0.124 % en
pleine impulsion) — un stop paie le spread du moment où il se déclenche.

## 3. La tension centrale mise en évidence par B4

- **Significativité** : les stratégies signal 4h génèrent 2 à 5 trades par fenêtre
  de walk-forward. À ce rythme, distinguer un edge du bruit est impossible — le
  meilleur combo P6 (Sharpe test 0.29, instrument v1) reposait sur 13 trades.
- **Coûts** : multiplier les trades multiplie les round-trips à 0.20–0.48 %.

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

> ⚠️ Liste établie sous l'instrument v1 (addendum B4) : mémoire des essais et des
> verdicts de sélection (vides), pas une preuve d'absence d'edge économique des
> familles ; elles y restent tant qu'un rejeu sous instrument réparé n'a pas tranché.

- **Scalping 5m/15m et mean reversion court terme** : morts sur Kraken, Binance et
  Bybit (P6 ×2, coûts ×5 vs Binance BNB) ; 24-36 % de candles 1m plates sur Bybit EU.
- **Grid trading sur ces fees** : 0/48 configs SOL (bug de comptabilité en prime,
  dette 14) ; meilleur grid BTC sous le seuil et sous le B&H **sous l'instrument v1**
  (l'expression « dix fois sous le seuil » est retirée, addendum B4) — le rejeu
  diagnostic grid (96 configs BTC/SOL, ROADMAP) tranche candidat / dépriorisation.
- **Stratégies signal 4h fine-tunées** (SuperTrend, Donchian, EMA/ADX, momentum) :
  0/35 en walk-forward (instrument v1) ; le tuning n'a franchi aucun critère codé.
- **HFT, trailing < 5 %, grid sans biais directionnel en bear** : leçons historiques.
- Doctrine : une famille tuée deux fois ne revient qu'avec un **mécanisme**
  nouveau, pas un paramétrage nouveau.

## 6. Ticket d'entrée (obligatoire, sur le papier, avant tout code)

> ⚠️ **Gel des runs levé (C1-C2 mergés)** : un backtest de nouvelle famille exige un ticket
> complet ci-dessous et une inscription à `docs/RESEARCH_LOG.md` **avant** lancement ; le
> pipeline P6/P7 `--fees bybit` est l'outil de test, pas de sélection — **toute sélection
> relève du protocole C3** (`docs/protocole_c3.md`). Cap de 2 familles par cycle inchangé.

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
- **Protocole non négociable** : 3+ ans de backtest → **validation chronologique sous
  le protocole C3** (`docs/protocole_c3.md` : sélection sur le passé seul, equity
  continue, issue « inconclusif » possible ; la cross-validation et le walk-forward P7
  restent des diagnostics, pas une validation) → 4+ semaines de paper → live progressif.
  Critères écrits avant les runs, appliqués tels quels.
- **Pas de ML** avant profit live confirmé (P11+). Un filtre ML sur du bruit reste
  du bruit.
- **Cap : deux familles maximum** entrent en backtest par cycle de R&D. Le pipeline
  rend le test presque gratuit (24 combos en 22 min) — c'est précisément le risque :
  tester cinquante idées, c'est du data mining, et la cinquantième qui « marche »
  est fausse par construction.

## 8. Protocole basse rotation (décision 16 du `ROADMAP.md`)

Repères de couverture (~25-30 round-trips sur l'ensemble de la période OU ~3 ans
d'equity quotidienne avec exposition non triviale) = **filtres internes de couverture
retenus par le projet, non seuils statistiques universels** : leur franchissement ne
suffit pas à valider une stratégie ; en dessous, le projet ne prononce pas
d'acceptation pour déploiement — verdict « inconclusif », et **inconclusif = pas de
déploiement** ; au-dessus, l'acceptation exige un effet économique minimum, un
benchmark d'exposition (B&H/cash à budget de risque et coûts comparables) et une borne
d'incertitude **écrits dans le ticket avant les résultats** ; les simulations
trimestrielles réinitialisées ne suffisent pas à valider un comportement destiné à
porter ses positions continûment entre les trimestres (le grid paie une liquidation
lorsqu'un inventaire reste ouvert en fin de segment ; le moteur signal ne transmet pas
sa position au segment suivant) — la validation relève du protocole C3 (equity
continue, sélection chronologique, bootstrap par blocs). Un mécanisme économique
plausible soutient l'hypothèse ; il ne remplace pas la validation empirique.

## 9. Annexe — prompts pour une IA externe

**Passe 1 (adversariale, à faire digérer avant toute génération) :**
« Voici le rapport final d'une campagne de backtests (B4), le contexte projet et ce
document de contraintes. Attaque les conclusions : où le raisonnement est-il
faible ? Quelles explications alternatives au zéro survivant n'avons-nous pas
éliminées (design des fenêtres de walk-forward, espace de configs exploré, modèle
de coûts trop pessimiste ou trop optimiste, période de marché) ? Qu'aurions-nous dû
mesurer et n'avons pas mesuré ? Sois spécifique et réfère-toi aux chiffres. »

**Passe 2 (générative, seulement après la passe 1) :**
« Sous les contraintes du document (coûts § 2, tension § 3, benchmark § 4, morts
§ 5, environnement § 7, protocole basse rotation § 8), propose au maximum 3 familles de stratégies. Chacune au
format du ticket d'entrée § 6, les sept points remplis. Toute proposition sans
mécanisme explicite (§ 6.1) ou sans critère de falsification (§ 6.7) sera rejetée
sans lecture du reste. Les recombinations d'indicateurs techniques sans mécanisme
sont exclues d'office. »

## 10. Critère d'arrêt — pré-enregistré le 2026-09-23

Ce paragraphe dit d'avance ce qui fait s'arrêter une famille, ce qui fait s'arrêter la recherche d'alpha du
projet, et ce qui doit exister avant tout ordre live. Il lit les événements que produit la chaîne C3
(`docs/protocole_c3.md`, § H, § I.1) et **ne les réinterprète pas**. Il est appliqué par les deux revues
(Astra, Claude) et par Bruno ; il ne se renégocie pas au vu d'un résultat. Auteur : Bruno, sur proposition
Claude du 22/09 et 23/09 ; adopté le 2026-09-23 avec la révision v2.1 du protocole C3.

### 10.1 Clôture de famille — un verdict compté, zéro retry

**Une famille est un mécanisme** (§ 6.1). Un autre paramétrage, une autre fenêtre, une autre paire, une
recombinaison d'indicateurs sont la même famille.

**Un verdict compte** quand la chaîne est allée jusqu'à l'économie :

| Issue C3 | Compte pour la famille |
|---|---|
| `validé`, `réfuté` | oui |
| `inconclusif` — `A_BELOW_FLOOR`, `F_NOT_ESTIMABLE`, `F_CANNOT_SEPARATE` ; `A_NO_ADMISSIBLE_CANDIDATE` quand **aucun** candidat n'a été retiré par D1, D2 ou D6 | **oui** : le périmètre ou l'effet est le résultat (protocole § A.11) |
| `inconclusif` — `A_NO_ADMISSIBLE_CANDIDATE` quand **au moins un** candidat a été retiré par D1, D2 ou D6 | **non** : l'ensemble a été vidé, au moins en partie, par un défaut de données ou d'instrument ; l'unique relance ci-dessous s'applique |
| `inconclusif` — `R0_INVALID_RUN`, `P_PROVENANCE`, `D_WARMUP_PREFIX`, `D_WARMUP_ANCHOR`, `R1_NOT_NORMALISED`, `E_NO_BENCHMARK`, `E_STAMP_MISMATCH` ; sorties code 1 et 2 | **non** : défaut d'instrument, de données ou de manifeste |

**Une seule relance** après correction d'instrument, par famille. Un second verdict non compté sur la même
famille la déclare *non testable sous cet instrument* ; elle est alors **comptée dans le budget du § 10.2**,
parce que ne pas savoir tester une famille est une information sur le projet.

**Zéro retry-tuning.** Aucune seconde campagne comptée sur la même famille avec d'autres paramètres, une autre
fenêtre ou un autre univers. Réouverture uniquement sur **hypothèse de mécanisme nouvelle**, documentée, passée
au ticket § 6 — ce qui en fait, par définition, une autre famille.

**Une seule voie de sortie, prospective.** Si l'issue est `inconclusif (F_CANNOT_SEPARATE)` **et** `Q1 ∧ Q2 ∧ Q3`
passent **et** `Δ̂ > 0` dans les six combinaisons — seule la borne manque —, la configuration retenue, et elle
seule, est inscrite à une **évaluation différée** au sens du protocole § D.1 (échantillon jamais consulté) :
fenêtre `[fin du manifeste, date déclarée]`, sur données gelées après le verdict, **au moins 12 mois de
données neuves**, mêmes paramètres, même procédure § F.2, une fois. La date et le manifeste sont écrits au
moment du verdict, pas après. Elle ne consomme pas de budget de familles ; elle est la seule chose qui survit
au cap temporel du § 10.2, parce que c'est une date à attendre, pas un chantier.

### 10.2 Alpha-stop projet — trois familles ou le 2027-09-30

- **Budget familles : trois**, à mécanisme distinct — grid (cycle en cours) + un cycle complet du cap § 7. Au
  delà, la multiplicité que le protocole déclare ne pas corriger (§ F.3) cesse d'être négligeable.
- **Budget temps : 12 mois à compter du gel de v2.1**, échéance **2027-09-30**. Le compteur démarre au gel et
  non au premier verdict, pour que la construction d'instrument entre dans le budget qu'elle a déjà consommé.
- **Jalon : premier verdict réel (grid) avant le 2027-01-31.** Manqué → **gel de l'instrument en l'état** :
  plus aucun amendement, plus aucune exigence producteur, la campagne grid part dans les 30 jours avec ce qui
  existe, et son verdict compte.
- **Déclencheur** : trois familles comptées sans `validé`, **ou** le 2027-09-30 — le premier atteint.
  Conséquence : le trader reste éteint définitivement sous ce dispositif ; le projet est requalifié
  (plateforme de données, instrument de recherche, pièce de portfolio). Réouverture uniquement par décision
  écrite, avec son auteur et son motif — jamais déduite d'un verdict.
- **`validé`** suspend le compteur temps pendant le paper (règles B5, `ROADMAP.md`) et la décision qui le suit.
  Un paper qui échoue à ses critères pré-enregistrés vaut verdict de la famille : comptée, close, compteur
  relancé. Un `validé` ne rouvre pas le budget familles.

### 10.3 Kill-switch live — structure exigée, chiffres dérivés

Avant le premier ordre live, le ticket de déploiement fixe trois seuils, **dérivés de l'artefact de la campagne
validée et d'aucune autre source** : (i) drawdown live rapporté au `max_drawdown_pct_daily` de la fenêtre
d'évaluation ; (ii) rendement réalisé annualisé rapporté à la borne basse `LB` du § F.2 ; (iii) durée maximale
sans cycle achevé rapportée à la cadence observée sur le préfixe. Les multiplicateurs et horizons sont écrits,
gelés, et ne se renégocient pas. Aucun nombre n'est fixé ici : chacun sort des chiffres que la chaîne aura
publiés.
