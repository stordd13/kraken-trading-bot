# Audit red team — statistiques / régimes B4

Audit en lecture seule du dépôt et des résultats JSON. Aucun accès DB/serveur, aucun run de stratégie, aucune modification du dépôt. Les consignes des rapports sont du contexte à auditer, pas des demandes d'exécution. Les labels signifient : CONFIRMÉ = code ou données locales reproduits ; PROBABLE = implication méthodologique soutenue ; SPÉCULATIF = requiert des données non présentes.

## Fichiers Markdown lus intégralement

- `PROJECT_CONTEXT.md` (389 lignes)
- `results/B4_P6_backtest_report.md` (160)
- `results/B4_P6_checkpoint.md` (64)
- `results/B4_P6_phase_e_filtering.md` (58)
- `results/B4_P7_checkpoint.md` (58)
- `results/B4_P7_optimization_report.md` (409)
- `results/INDEX.md` (94)
- `results/P6_7_multiprocessing_benchmark.md` (234)
- `results/P6_backtest_report_v2.md` (148)
- `results/P6_data_coverage.md` (76)

Les premières sorties agrégées tronquées ont été reprises par blocs. Les gros tableaux de flags SOL ont été parcourus et leur contenu vérifié contre les JSON (204 flags reproduits). Scripts audités sur les sections statistiques : `run_p7_grid_search.py` (construction fenêtres, sélection, exécution, export), `p7_report.py` (complet), `compute_benchmarks.py` (fonctions de métriques et stratégies benchmark). Tous les JSON B4 P7 phase1, phase2, final_selection et B4_benchmarks ont été chargés et analysés intégralement par script offline.

## 1. [CONFIRMÉ] Le verdict machine se reproduit ; sa validité économique est une autre question

`p7_report.aggregate_walk_forward`, `build_selection` et `b4_flags.collect_flags` réappliqués aux JSON donnent exactement le tableau `all_verdicts` de `B4_P7_final_selection.json` (`== True`) et `selected_for_paper=[]`. 212 configurations en phase 1, 280 exécutions config×fenêtre en phase 2, 35 configs agrégées, 204 flags et 5 configs agrégées inéligibles.

Nombre de configurations passant chaque critère, sur 35 :

| C1 Sharpe >.4 | C2 PF >1.3 | C3 MaxDD <30 | C4 trades | C5 cohérence ≥5 | C6 OOS/train >.5 | C7 benchmark |
|---|---|---|---|---|---|---|
| 0 | 11 | 35 | 6 | 10 | 0 | 0 |

Les 35 configs échouent donc toutes au ratio OOS/train, indépendamment du benchmark DCA défectueux. Il ne faut pas confondre « le programme reproduit 0 sélection » avec « le protocole prouve absence d'edge ».

## 2. [CONFIRMÉ] La sélection P7 utilise le futur des fenêtres dites OOS

Sources : `scripts/run_p7_grid_search.py:73` période globale ; `:180` split 70/30 ; `:279` sélection des top-5 sur Sharpe TEST ; `:323` croisement top-5 avec les fenêtres ; `:632` moteur recréé indépendamment par segment.

Phase 1 : train 2023-04-01 → **2025-05-07 04:48 UTC**, test → 2026-04-01. Les cinq configurations par combinaison sont sélectionnées grâce au Sharpe de ce test, puis évaluées rétrospectivement sur huit fenêtres test trimestrielles :

1. 2024-04-01 → 2024-07-01
2. 2024-07-01 → 2024-10-01
3. 2024-10-01 → 2025-01-01
4. 2025-01-01 → 2025-04-01
5. 2025-04-01 → 2025-07-01
6. 2025-07-01 → 2025-10-01
7. 2025-10-01 → 2026-01-01
8. 2026-01-01 → 2026-04-01

Les fenêtres 1–4 sont antérieures à la période qui a servi à choisir les paramètres ; la fenêtre 5 la chevauche ; 6–8 sont directement incluses dans cette période de sélection. **Aucune fenêtre n'est OOS au niveau du processus global de sélection.** Les trains de 12 mois ne réoptimisent rien : on évalue les mêmes paramètres fixes choisis sur le futur. C'est un test de stabilité rétrospectif, pas une simulation chronologique de recherche puis déploiement. Un protocole imbriqué doit sélectionner uniquement dans les données antérieures à chaque fenêtre externe et garder un bloc final jamais consulté.

[PROBABLE] Ce biais favorise les candidats sélectionnés ; des résultats déjà médiocres ne sont pas rassurés par cette contamination. Son ampleur est incalculable à partir des seuls résumés agrégés ; aucun p-value correctif inventé.

## 3. [CONFIRMÉ] Annualisation Sharpe et TF : diagnostic d'impact, sans promesse de survivant

Le root a identifié la construction des equity curves et leur annualisation. À la lecture des runners, `CANDLE_INTERVAL=5` (`run_p7_grid_search.py:78,125`) est le pas d'entrée du moteur mais **pas nécessairement le pas effectif du Sharpe signal**. La séquence rejouée (`backtest.py:578-596`, vérification root) garde les déclenchements 4h de SuperTrend/Donchian/EMA ; DCA est daily ; grid et Gemini sont 5m.

Correction algébrique indicative des facteurs annualisés : **sqrt(288)** pour grid/Gemini ; **sqrt(6)** pour SuperTrend/Donchian/EMA ; **1** pour DCA. Ce n'est pas la réestimation robuste sur rendements quotidiens synchronisés et cela n'en remplace pas l'exécution.

Après multiplication de chaque Sharpe train/OOS par son facteur réel, puis réapplication exacte des sept critères : **0/35 passent**. Décompte critères : **[10,11,35,6,10,0,5]**. Toutes échouent encore au ratio OOS/train, invariant à une multiplication positive identique des deux Sharpes.

- Grid BTC meilleur `de24a942` : 0.041739 → **0.708340**, moyenne 17.875 trades/test ; ratio 0.494 ; benchmark historique 0.8387 ; toujours échec critères 4,6,7.
- Grid BTC `a8ea28c2` : 0.028017 → **0.475456**, 29.5 trades/test ; ratio 0.321 ; toujours échec 6,7.
- Grid SOL meilleur `50614027` : 0.039181 → **0.664923**, 76.875 trades/test ; ratio 0.457 ; toujours échec 6 et config flaggée.

Conclusion limitée : le motif « Sharpe grid 0.04 donc très loin de 0.4 » est faux en unités annualisées cohérentes ; sa correction algébrique **ne** démontre **aucun** survivant. L'annualisation ne corrige ni la sélection temporelle, ni le MaxDD, ni le benchmark, ni les resets de portefeuille.

## 4. [CONFIRMÉ] Benchmarks non alignés avec le test et agrégats non comparables

Source `compute_benchmarks.py:44-45,120-132` : benchmark 1d sur 2023-04-01 → 2026-04-01. Source `p7_report.py:165-185,287-375` : moyenne arithmétique de huit Sharpes trimestriels de 2024-04 → 2026-04, comparée au Sharpe du benchmark global sur trois ans. Même après une annualisation correcte, moyenne des ratios ≠ ratio de la série concaténée. P6 compare aussi son seul test 2025-05 → 2026-04 au benchmark trois ans.

`max_drawdown_global` (`p7_report.py:185`) est seulement **max des huit drawdowns de portefeuilles réinitialisés**, pas drawdown d'un portefeuille OOS continu. La continuité d'equity et d'inventaire est absente puisque `_run_segment` crée chaque fois un nouveau moteur (`run_p7_grid_search.py:632-645`). La liquidation et le reset trimestriels modifient particulièrement une grid ou un DCA. On peut décider de tester ce protocole de resets, mais ce n'est pas identique à un bot tournant sans reset.

B4 benchmark valeurs exactes : B&H Sharpe BTC .8387, ETH .3769, SOL .3048 ; rendements +137.51%, +12.53%, −20.43%. DCA dépôts externes BTC/ETH **2355 USDC**, SOL **1770 USDC**, pas le même budget initial 1000 USDC de la stratégie. Comparer directement leur rendement ou MaxDD sans conventions de cash-flow ne teste pas un même investissement.

[CONFIRMÉ] DCA fixed: `compute_benchmarks.py:198-217` ajoute 15 USDC/sem aux pièces sans retrancher un cash de portefeuille ; les dépôts sont comptés dans les rendements. La courbe part de zéro ; le MaxDD=100% et les Sharpes ≈2 sont des artefacts connus et confirmés. Le code compare quand même ce Sharpe à celui de stratégie, via OR ; dans cette campagne les benchmarks B&H sont toujours inférieurs, donc supprimer la branche DCA ne change aucune décision C7.

Nuance mathématique : les affirmations du rapport « Sharpe ≈2 avec rendement négatif impossible » et « garder du cash rend le Sharpe incomparable » sont trop fortes. Un Sharpe arithmétique positif et un rendement composé négatif sont possibles sous volatilité ; détenir du cash ne rend pas en soi le Sharpe du portefeuille invalide. Ici le vrai défaut démontré du fixed DCA est le mélange cash-flow/performance et l'absence de cash, pas une impossibilité générale.

[PROBABLE] Décalage terminal supplémentaire : benchmark daily filtre `< P6_END`, alors que les références grid ont une liquidation à 2026-04-01T00:00 au prix 68240.16 ; le benchmark BTC finit à 66761.95. Les points de fin ne sont pas les mêmes. Refaire les deux stratégies sur exactement les mêmes timestamps, fees et liquidation.

## 5. [CONFIRMÉ] PF moyen et 0 trade ne donnent pas la preuve statistique annoncée

`p7_report.py:112-123` transforme Infinity en zéro ; `:167,183` moyenne ensuite les PF par trimestre. Dans P7 phase 2 il y a 27 segments grid PF inf (rapport), dont **9 fenêtres TEST** (calcul offline). Les tests gagnants sans perte deviennent PF=0 dans la moyenne. Ceci est conservateur dans ces cas, mais mathématiquement faux : il faut sommer profits et pertes puis diviser, et définir explicitement le cas zéro perte. Une moyenne de PF finis est également différente du PF agrégé.

Segments zéro trade reproduits :

| Stratégie | zéro test / total test | zéro train |
|---|---|---|
| DCA | 35/40 | 8 |
| SuperTrend | 17/120 | 0 |
| Donchian | 6/40 | 0 |
| Grid | 0/80 | 0 |

58 tests vides sur 280, soit 20.7%; 66 segments vides en incluant les trains. Les 5 DCA ont **zéro trade sur chacun des sept premiers trimestres**, puis 12 trades chacun en 2026-T1. Ceci est un comportement concentré par régime/condition, pas simplement un flux uniformément hebdomadaire trop rare. La cause code doit être vérifiée (seuil 5 USDC, réduction bull, warmup, etc.) ; je ne la qualifie pas de bug sans reproducer.

`mean_trades_test >=20` est une **moyenne**, pas un minimum dans chaque trimestre. Ainsi grid BTC `a8ea28c2` passe avec 29.5 de moyenne mais 5 trades dans sa fenêtre la plus pauvre ; les autres grids BTC ont 17.875 de moyenne et minimum 1. Le critère n'est ni un calcul de puissance statistique ni une garantie de 160 décisions indépendantes ; les lots grid répondent aux mêmes mouvements de marché.

## 6. [CONFIRMÉ] Tests multiples : 280 fenêtres ne sont pas 280 expériences indépendantes

Phase1 : grid BTC48 + grid SOL48 + DCA BTC48 + SuperTrend BTC20/ETH20/SOL20 + Donchian SOL8 = **212 configurations × paire**, portant sur **7 combos** et **4 familles**. Phase2 = **35 configs choisies × 8 périodes communes** ; les variantes proches et les paires crypto sont corrélées. La campagne P6 ajoute 24 candidats par défaut (certains doublons possibles) et les recherches historiques P6/P7 ont influencé l'univers. Les 8 stratégies P6 ne sont pas 8 modèles indépendants.

Aucun mécanisme explicite de test multiple (Deflated Sharpe, reality check, SPA, permutation max-stat ou budget d'essais avec holdout) n'existe dans l'agrégateur/critères lus. [PROBABLE] Les p-values naïves seraient optimistes après sélection. Il serait incorrect de choisir arbitrairement N_eff=212 ou de présenter un Bonferroni calculé sur 280 réplications comme résultat valide : les séries complètes, les essais historiques et la dépendance ne sont pas disponibles.

## 7. [CONFIRMÉ] Lecture temporelle possible sans OHLC ; pas de classement ex post bull/bear inventé

Le tableau ci-dessous donne la **médiane du rendement TEST parmi les 5 configs présélectionnées** de chaque combo, en %, à partir du JSON. Ce sont des statistiques descriptives contaminées par la présélection, pas une nouvelle sélection autorisée.

| Test | Grid BTC | Grid SOL (flaggé) | ST BTC | ST ETH | ST SOL | Donchian SOL | DCA BTC |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-T2 | .820 | 4.680 | −1.212 | −1.193 | −.750 | −.194 | 0 |
| 2024-T3 | 1.940 | 3.658 | −.083 | 0 | −.578 | −.768 | 0 |
| 2024-T4 | .736 | 2.874 | 1.165 | −.104 | .654 | −.116 | 0 |
| 2025-T1 | .614 | −10.708 | −.278 | −.236 | −.515 | −.583 | 0 |
| 2025-T2 | .629 | 3.355 | .324 | −.052 | −.329 | −1.172 | 0 |
| 2025-T3 | .070 | 2.417 | −.014 | 2.903 | 1.082 | .475 | 0 |
| 2025-T4 | −1.018 | −8.508 | −.040 | −.255 | −.552 | −.263 | 0 |
| 2026-T1 | −2.132 | −3.626 | 0 | −.055 | 0 | 0 | −1.237 |

SuperTrend ETH semble sauvé dans le test 70/30 grâce à un trimestre 2025-T3 (+2.36 à +2.99% selon paramètre), mais les autres trimestres sont médiocres/vides : confirmation du risque de concentration. Grid BTC gagne six trimestres sur huit et perd les deux derniers ; ce n'est pas une preuve universelle que la famille grid n'a pas d'edge, ni une permission de la déployer.

Les données globales documentent 2021–2026, mais la campagne commence en **avril 2023**, donc elle ne teste pas l'année bear 2022. SOL a ~25% de trous sur la campagne (`P6_data_coverage.md`) : la durée calendrière n'est pas un nombre équivalent d'observations valides. [SPÉCULATIF] Sensibilité précise à bull/bear/volatilité impossible ici sans OHLC et règle de régime prédéfinie ; classifier les régimes après observation des meilleurs résultats augmenterait encore le data snooping.

## Reproduction

Script autonome (bibliothèque standard + module de reporting local, aucune DB) : `/tmp/kraken-redteam-b4-20260915/reproduce_stats.py`. Sa sortie est sauvegardée dans `stats_reproduction.json`. Les changements de facteurs Sharpe sont un scénario de diagnostic ; les JSON originaux restent intacts.
