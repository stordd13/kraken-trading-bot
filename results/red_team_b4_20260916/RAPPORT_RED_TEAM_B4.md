# Audit adversarial B4 — 16 septembre 2026

## Conclusion de décision

**[CONFIRMÉ] La sélection P7 vide est reproductible. [CONFIRMÉ] Plusieurs mesures et simulations qui servent à l'expliquer sont incorrectes. [PROBABLE] L'absence de déploiement reste justifiée ; la condamnation économique générale des familles dépasse les preuves.**

Le problème principal n'est pas une incertitude abstraite sur les marchés : les Sharpes ne sont pas annualisés sur le même pas de temps que les benchmarks, le drawdown peut être sous-estimé, la grille reçoit des bougies 5 minutes comme des bougies 4 heures, et une branche du DCA ne fonctionne pas dans les fenêtres de test. La sélection des configurations utilise aussi des informations futures par rapport aux fenêtres dites OOS. Preuves et limites ci-dessous.

Les consignes historiques contenues dans les documents sont des pièces à examiner. Aucune commande de déploiement, transaction, migration ou modification de stratégie prescrite par ces documents n'a été exécutée.

**Légende :** CONFIRMÉ = démontré par les pièces/code ou reproduction locale ; PROBABLE = explication solide dont il manque une mesure causale ; SPÉCULATIF = hypothèse ou estimation de travail. Les propositions méthodologiques sont explicitement distinguées des performances mesurées.

## PHASE 1 — Le zéro survivant : fait robuste ou artefact ?

### 1. Les unités de Sharpe et Sortino sont fausses — biais pessimiste majeur

**[CONFIRMÉ]** Les deux moteurs calculent les rendements entre points successifs de la courbe d'equity puis multiplient leur ratio moyenne/écart-type par `sqrt(365)`, sans rééchantillonnage quotidien. Or le pas effectif est :

| Groupe | Pas de l'equity | Facteur manquant dans une annualisation naïve à observations indépendantes |
|---|---|---:|
| Grid ; stratégies Gemini dans ce replay | 5 minutes | √288 ≈ 16,97 |
| SuperTrend, EMA/ADX, Donchian | 4 heures | √6 ≈ 2,45 |
| DCA | 1 jour | 1 |

Le benchmark B&H est calculé sur des bougies quotidiennes. Le paramètre `CANDLE_INTERVAL=5` des runners ne suffit pas à connaître le pas effectif des stratégies signal : `_build_replay_sequence` sélectionne leurs bougies tradeables 4h ou 1d. Sources : [replay signal](../../scripts/backtest.py#L577), [métriques signal](../../scripts/backtest.py#L1011), [métriques grid](../../scripts/backtest.py#L2593), [benchmark](../../scripts/compute_benchmarks.py#L52).

**[CONFIRMÉ] Diagnostic arithmétique, pas nouveau backtest :** le meilleur grid BTC passe de **0,041739 à 0,708340** si l'on change seulement ce facteur. L'affirmation « dix fois sous le seuil 0,4 » du [rapport B4 §4.2–4.3](../B4_bybit_backtest_report.md#L187) ne tient donc pas avec des unités cohérentes.

**Ce 0,708 n'est pas le Sharpe quotidien corrigé.** Il faut reconstruire les rendements quotidiens, traiter leur dépendance temporelle et recalculer les agrégats. L'annualisation par racine du temps dépend d'hypothèses ; elle ne remplace pas cette opération. Référence méthodologique : [Lo, The Statistics of Sharpe Ratios](https://alo.mit.edu/research-page/the-statistics-of-sharpe-ratios/).

**[CONFIRMÉ] La seule correction de facteur ne crée aucun survivant.** Reproduction exacte des 35 verdicts depuis les JSON, puis scénario avec les facteurs par famille :

| Critère P7 | Configurations qui passent avant | Après correction indicative du facteur |
|---|---:|---:|
| Sharpe > 0,4 | 0 | 10 |
| PF > 1,3 | 11 | 11 |
| MaxDD < 30 % | 35 | 35 |
| Nombre moyen de trades | 6 | 6 |
| Cohérence ≥ 5/8 | 10 | 10 |
| Ratio OOS/train > 0,5 | 0 | 0 |
| Benchmark | 0 | 5 |
| **Tous les critères** | **0** | **0** |

Le ratio OOS/train reste inchangé lorsque les deux termes sont multipliés par le même facteur. Les autres erreurs ne sont pas corrigées dans ce scénario. Sources : [reproduction](stats_reproduction.json), [script](reproduce_stats.py), [critères](../../scripts/p7_report.py#L287).

### 2. L'instrument de mesure sous-estime aussi certains risques

**[CONFIRMÉ] MaxDD erroné dans les deux moteurs.** Le code cherche la plus grande perte en monnaie puis la divise par le plus haut niveau d'equity atteint sur l'ensemble du run. Le drawdown relatif correct doit utiliser le sommet antérieur à chaque creux. Sur une courbe synthétique **1 000 → 700 → 2 000 → 1 900**, les méthodes originales donnent **15 %**, contre **30 %** réellement subis. Le benchmark, lui, utilise la bonne formule relative. Biais : MaxDD trop faible et Calmar trop élevé lorsque cette erreur intervient. Ce contre-exemple ne signifie pas que tous les MaxDD B4 sont faux de moitié. Sources : [signal](../../scripts/backtest.py#L980), [grid](../../scripts/backtest.py#L2579), [reproduction des méthodes originales](reproduce_metrics.py), [sortie](metrics_evidence.json).

**[CONFIRMÉ] Profit factor incomplet.** Les P&L de vente utilisés pour PF et gains/pertes incluent la fee de vente mais pas celle d'achat ; cette dernière est déduite plus tard du `net_pnl` global. Un P&L final réconcilié ne certifie donc pas un PF net de tous frais. Sur le dump de référence Bybit BTC, **46 allers-retours**, le PF publié **1,44196** devient **1,38318** après imputation des frais d'entrée aux trades correspondants. Il s'agit de ce run de référence, pas d'un recalcul de toute la campagne. Sources : [calcul](../../scripts/backtest.py#L940), [dump](../b4_3_bybit_signal_A_post.json), [preuve](metrics_evidence.json).

**[CONFIRMÉ] Agrégation PF pessimiste dans l'autre sens.** P7 remplace les PF infinis par zéro avant de moyenner les PF trimestriels. **9 fenêtres test grid** sont concernées ; le chiffre de 27 du rapport inclut aussi des segments train. Un trimestre profitable sans perte devient PF=0. Il faut agréger les gains et pertes nets puis calculer leur rapport ; une moyenne de PF n'est pas ce rapport. Sources : [agrégateur](../../scripts/p7_report.py#L112), [B4 §4.2](../B4_bybit_backtest_report.md#L187), [calcul détaillé](stats_reproduction.json).

### 3. Des stratégies différentes de celles annoncées sont évaluées

**[CONFIRMÉ] Grid : données 5m injectées dans les indicateurs 4h.** Le replay associe `interval=240` à toutes les bougies de trading, même lorsqu'elles proviennent de la série 5m. L'analyzer met à jour ATR/EMA/ADX « 4h » avec ces observations, sans les agréger. Cela change l'algorithme, pas seulement son score. Ce point était déjà consigné parmi les annexes non traitées de B4.2. Son effet économique doit être mesuré par rejeu ; son signe n'est pas déductible a priori. Sources : [replay grid](../../scripts/backtest.py#L1769), [injection](../../scripts/backtest.py#L2205), [routage indicateurs](../../src/krakenbot/indicators/multi_timeframe.py#L338), [B4.2 §10](../B4_2_fees_engine_report.md#L284).

**[CONFIRMÉ] DCA : le boost « oversold » est inactif pendant les tests trimestriels.** L'EMA200 quotidienne est créée paresseusement au premier appel de `generate_signal`, après le warmup. DCA manque dans les EMA préenregistrées ; les données de warmup déjà passées ne sont pas rejouées dans cette EMA. Une fenêtre de 90–92 jours n'atteint donc pas les 200 observations nécessaires. `oversold_multiplier` et `rsi_oversold` ne peuvent pas modifier ces tests. La reproduction avec le véritable analyzer confirme ce défaut ; il ne bloque pas les achats de base. Sources : [préenregistrement](../../scripts/backtest.py#L1255), [EMA lazy](../../src/krakenbot/indicators/multi_timeframe.py#L628), [condition DCA](../../src/krakenbot/strategies/grok_adaptive_dca_weekly.py#L194), [notes de reproduction](execution_audit.md).

**[CONFIRMÉ] DCA : interaction ignorée avec le minimum d'ordre.** Les cinq configurations retenues ont `bull_reduction=0.3`. En régime `strong_bull`, l'achat de base de **15 USDC** devient **4,50 USDC**, puis le moteur le rejette sous **5 USDC**. Cela contredit l'hypothèse du GATE B selon laquelle ce plancher n'affecte que les résidus de cash. Sources : [DCA](../../src/krakenbot/strategies/grok_adaptive_dca_weekly.py#L213), [rejet](../../scripts/backtest.py#L754), [GATE B §2.3](../B4_3_gate_b_configs.md#L92).

**[PROBABLE]** Cette interaction contribue aux **35/40 tests DCA sans trade** : les cinq configurations sont toutes à zéro sur les sept premiers trimestres, puis chacune fait 12 achats au dernier. Les logs de régime et de rejets manquent pour attribuer exactement chaque absence. L'explication « stratégie naturellement trop lente » n'est pas établie.

**[CONFIRMÉ] B4 ne valide pas le portefeuille live.** Le router, le sizing central, le crash protector, les budgets multi-stratégies et plusieurs limites de risque ne sont pas simulés. Les paramètres par défaut de classe diffèrent aussi des instances YAML. Ces limites sont reconnues dans [B4 §8](../B4_bybit_backtest_report.md#L312) et [PROJECT_CONTEXT, dettes 13–14](../../PROJECT_CONTEXT.md#L345). Leur impact peut aller dans les deux sens.

### 4. Le « walk-forward » utilise le futur pour choisir ses candidats

**[CONFIRMÉ]** Les top-5 sont choisis sur le Sharpe du test global **2025-05-07 → 2026-04-01**, puis rejoués sur les trimestres **2024-04 → 2026-04**. Les quatre premières fenêtres précèdent cette période de sélection, la cinquième la chevauche, les trois dernières y sont incluses. Les trains de douze mois n'effectuent aucune nouvelle sélection locale. Ce sont des tests rétrospectifs de stabilité de configurations sélectionnées avec le futur ; aucune fenêtre n'est vierge au niveau de la procédure de sélection. Sources : [sélection top-K](../../scripts/run_p7_grid_search.py#L279), [construction phase 2](../../scripts/run_p7_grid_search.py#L323), [B4 §2 et §4](../B4_bybit_backtest_report.md#L47).

**[PROBABLE]** Le biais de sélection favorise les configurations qui ont réussi sur la période utilisée pour les choisir. Il ne rend pas leurs scores faibles plus convaincants et empêche de donner aux 280 runs le statut de 280 validations indépendantes. Son amplitude n'est pas chiffrable à partir des seuls résumés.

**[CONFIRMÉ] Benchmarks et agrégats désalignés.** P7 compare la moyenne de huit Sharpes trimestriels à un Sharpe B&H global de trois ans. P6 compare également son test d'environ onze mois à ce benchmark trois ans. Une moyenne de ratios n'est pas le ratio d'une série continue. `max_drawdown_global` est seulement le maximum des drawdowns de huit comptes réinitialisés : il ne mesure pas le drawdown d'un portefeuille continu. Les resets et liquidations trimestriels changent particulièrement le grid et le DCA. Sources : [agrégation](../../scripts/p7_report.py#L165), [moteur neuf par segment](../../scripts/run_p7_grid_search.py#L632), [B4 §5](../B4_bybit_backtest_report.md#L235).

### 5. Tests multiples : aucun taux de faux positifs B4 n'est identifiable

**[CONFIRMÉ]** Il y a 212 configurations × paire, puis 35 configurations × 8 périodes communes, avec recouvrement des trains et variantes parfois identiques en pratique. Les 24 combos P6 et l'historique des recherches ajoutent des essais, sans former un ensemble d'expériences indépendantes. Aucun contrôle formel du taux d'erreur n'apparaît dans les critères. Sources : [B4 §4](../B4_bybit_backtest_report.md#L151), [grilles](../../scripts/p7_grids.py), [historique documentaire](history_audit.md).

**Exemple mathématique conditionnel, pas estimation B4 :** si 212 hypothèses nulles étaient testées indépendamment à 5 %, on attendrait **10,6 faux positifs**, et la probabilité d'en avoir au moins un serait `1 − 0.95^212`, soit **environ 99,998 %**. Ici, les sept portes ne constituent pas un test à 5 %, leur dépendance est inconnue et les stratégies lentes échouent parfois par construction. Appliquer ce calcul à B4 serait inventer un modèle nul.

**[PROBABLE]** Des critères écrits d'avance limitent les exceptions opportunistes ; ils ne corrigent ni la sélection sur le test ni les recherches multiples. DSR peut contrôler certaines formes d'inflation liées aux essais et à la non-normalité ; il exige les séries de rendements et une représentation crédible de la recherche effectuée. Référence : [Bailey et López de Prado, Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Le bon diagnostic manque dans les deux directions : combien de pipelines sans edge passeraient, et combien de pipelines ayant un edge économiquement utile seraient rejetés ? Zéro sélection prouve zéro acceptation par ces portes ; cela ne fournit pas une probabilité d'absence d'edge.

### 6. Le protocole rejette structurellement certaines stratégies lentes

**[CONFIRMÉ]** Le critère réellement codé est **20 trades par trimestre en moyenne**, soit environ **80 par an** ; DCA bénéficie d'une exception à 5. Ce n'est ni « au moins 20 dans chaque fenêtre », ni un calcul de puissance statistique. Une stratégie à quelques allers-retours par an est exclue même si son comportement économique correspond à l'objectif. Le PF sur ventes ne convient pas non plus à une accumulation sans ventes. Sources : [critères P7](../../scripts/p7_report.py#L287), [contraintes §3](../../docs/CONTRAINTES_POST_B4.md#L40).

**[CONFIRMÉ]** Les « 66 fenêtres sans trade » sont en réalité **66 segments train ou test**, dont **58 tests sur 280** : 35 DCA, 17 SuperTrend, 6 Donchian. Les paramètres et périodes se répètent : ces absences ne représentent pas 66 expériences indépendantes. Source : [comptage](stats_reproduction.json).

**Changement proposé avant toute nouvelle famille lente :** jugement sur une equity quotidienne continue, positions conservées entre segments, historique couvrant plusieurs épisodes économiques, contrôles de risque et de turnover, intervalle d'incertitude tenant compte de la dépendance. Fixer un effet économique minimum et mesurer la capacité du protocole à le détecter. L'issue « données insuffisantes » doit exister à côté d'acceptation/rejet. Davantage de bougies ou de variantes ne crée pas davantage d'épisodes indépendants.

La même incompatibilité réapparaît en paper : quatre semaines et un P&L positif sur trois semaines ne démontrent pas un edge de détention en mois. Cette période peut vérifier l'intégration technique ; la preuve économique demande une durée adaptée. Source : [ROADMAP, B5](../../ROADMAP.md#L106).

### 7. Maker et stops : les hypothèses d'exécution biaisent les deux sens

**[CONFIRMÉ]** Le fill maker est complet dès le toucher, sans file, volume disponible, fill partiel, délai ni rejet PostOnly. Un ordre signal est effacé après la prochaine bougie tradeable, rempli ou non ; cette opportunité peut durer 4h ou 1d, sans reproduire le cycle de vie réel. Sources : [résolution fill](../../scripts/backtest.py#L646), [pending](../../scripts/backtest.py#L1295), [limites B4.2 §10](../B4_2_fees_engine_report.md#L284).

**[PROBABLE] Biais optimiste dominant pour la qualité des fills maker marginaux :** le simulateur accorde le toucher suivi d'un rebond, alors que le véritable ordre derrière la file peut n'être exécuté que lors d'une traversée défavorable. **Amplitude inconnue.** Retirer uniformément 10 % ou 30 % des trades ne mesure pas cette sélection adverse ; la séquence d'inventaire et les opportunités suivantes changent aussi. Un remplissage plus réaliste ne garantit donc pas une baisse monotone du P&L pour chaque stratégie.

**[CONFIRMÉ] Contre-biais grid :** les listes de BUY et SELL à remplir sont fixées avant traitement ; une cible créée par un achat ne peut pas être revendue dans la même bougie. Un aller-retour réellement réalisable pendant ces cinq minutes peut ainsi être manqué. Source : [boucle grid](../../scripts/backtest.py#L2189). Les OHLC seuls ne permettent pas de savoir dans quel ordre les niveaux ont été atteints.

**[CONFIRMÉ] La prémisse des stops intrabar est fausse pour les stratégies 4h concernées.** Le replay transmet le close 4h ; la stratégie compare ce prix au stop, puis le MARKET est exécuté à l'open de la bougie tradeable suivante. Le low intervient dans les LIMIT, pas comme déclencheur général de stop. Une mèche qui traverse le stop puis récupère avant la clôture peut être ignorée ; une chute persistante peut au contraire donner une sortie retardée plus mauvaise. Il faut spécifier le comportement cible avant de quantifier le biais. Sources : [replay](../../scripts/backtest.py#L1337), [SuperTrend](../../src/krakenbot/strategies/grok_supertrend_4h.py#L149), [stop](../../src/krakenbot/strategies/grok_supertrend_4h.py#L253).

### 8. Les coûts sont un scénario de calibration, pas une estimation de coût conditionnel fiable

**[CONFIRMÉ]** Les 126 lignes de carnet correspondent à 3 paires × **21 relevés horaires** × 2 profondeurs presque successives ; pas 42 instants indépendants par paire. La période du 14 au 15 septembre 2026 est lundi–mardi. Le slippage de carnet est estimé sur les **asks pour un BUY**, alors que les sorties des stratégies sont des SELL ; les 2 bps retenus sont un plancher. Sources : [GATE B §1](../B4_3_gate_b_configs.md#L27), [calibration](../../config/pair_costs_b4.README.md), [script Q3](../../scripts/audit/bybit_q3_orderbook.py#L68), [données](../q3_orderbook.jsonl).

**[PROBABLE]** Déduire tout le spread d'un prix de référence égal au mid est pessimiste par rapport à un demi-spread. Ici le prix de référence est un prix OHLC, pas un mid garanti ; on ne peut pas diviser mécaniquement par deux et appeler cela une correction exacte. À l'inverse, l'échantillon ne caractérise pas les spreads conditionnels aux stops, les sauts de prix ou le délai d'exécution. Le GATE B constate déjà **12,4 bps sur ETH** pendant une impulsion, contre 3 bps retenus. Le sens net du biais doit être mesuré.

**[CONFIRMÉ] Sensibilité arithmétique à ±50 % des seuls spread + slippage**, fees maker/taker inchangées :

| Aller-retour limit/market | −50 % frictions | Calibration B4 | +50 % frictions |
|---|---:|---:|---:|
| BTC | 0,370 % | 0,390 % | 0,410 % |
| ETH | 0,375 % | 0,400 % | 0,425 % |
| SOL | 0,415 % | 0,480 % | 0,545 % |

Valeurs additives en points de base, avant petits termes multiplicatifs de fees. Réduire les frictions de moitié ne divise pas par deux la facture : les **35 bps de fees** limit/market demeurent. Source : [configuration](../../config/pair_costs_b4.json).

**[CONFIRMÉ] Contrôle partiel effectué :** à trades et quantités inchangés, le dump Bybit SuperTrend BTC de référence passe de **19,314 USDC** nets à **19,778** avec −50 % de frictions, et à **18,850** avec +50 %. Pour 1 000 USDC : **1,978 % / 1,931 % / 1,885 %** de rendement. Ce contrôle ne recalcule ni le Sharpe ni toute la campagne, et ne modélise pas les changements de trajectoire. Source : [preuve chiffrée](metrics_evidence.json).

**[SPÉCULATIF]** Affirmer que le verdict complet resterait identique sous ces scénarios dépasserait ce calcul. Il faut rejouer les configurations avec leurs contraintes et positions. Pour ce run de référence, l'écart est petit ; rien ne permet d'en tirer une borne générale.

**[CONFIRMÉ] Contradiction documentaire supplémentaire :** les round-trips maker/maker 0,24/0,25/0,33 % de [CONTRAINTES §2](../../docs/CONTRAINTES_POST_B4.md#L21) ne correspondent pas au modèle B4 exécuté : les deux fills maker supportent 0,10 % chacun et aucun spread/slippage explicite. Le GATE B §3 utilise bien environ 0,20 %. Cela ne prouve pas une exécution maker réelle gratuite en frictions ; cela impose de séparer frais débités, prix des limites et sélection adverse.

### 9. Régimes et proxy : ni « bull partout », ni équivalence économique prouvée

**[CONFIRMÉ]** Sur la période, le B&H fait **+137,5 % BTC, +12,5 % ETH et −20,4 % SOL**, cette dernière série étant plus courte. « Marché haussier » ne résume pas les trois séries ni leurs sous-périodes. La campagne commence en avril 2023 : **2022 n'y est pas testé**. SOL ne fournit que **825 jours**, avec des trains w1–w3 couverts à **25,9 / 50,7 / 75,9 %**. Une portion test sans trou ne restaure pas l'historique nécessaire à l'état initial et aux indicateurs. Sources : [B4 §2](../B4_bybit_backtest_report.md#L47), [§5](../B4_bybit_backtest_report.md#L235).

**[CONFIRMÉ] Lecture des fenêtres disponible :** la médiane des cinq configurations grid BTC donne **+0,61 % en 2025-T1**, puis **−1,02 % en 2025-T4** et **−2,13 % en 2026-T1**. SuperTrend ETH concentre son gain en **2025-T3, environ +2,90 %** ; ses autres trimestres sont médiocres ou vides. Ce sont des observations descriptives après présélection, pas une validation par régime. Le rapport ne fournit pas un B&H synchronisé pour chaque trimestre ; attribuer un régime à partir du seul P&L de la stratégie serait circulaire. Source : [table complète et périodes](stats_audit.md).

**[CONFIRMÉ] La corrélation des closes ne valide pas l'exécution EU.** B3 §5(b) rapporte des écarts absolus **p99 de 23,2 / 48,5 / 46,7 bps** et des maxima **196,8 / 333,0 / 305,5 bps** BTC/ETH/SOL. Ces chiffres concernent les closes 1h, pas les mèches ni des coûts de transaction. Ils invalident néanmoins une garantie d'équivalence fondée sur la seule corrélation 0,99998. La valeur d'environ 40 bps de B0 n'est pas une borne générale sur les mèches ; l'étude Q8 portait aussi sur les closes. Sources : [B3 §5(b)](../B3_bybit_data_report.md#L264), [audit B0, Q8](../bybit_integration_audit.md).

**[PROBABLE]** Des mèches propres à EU peuvent augmenter les stops intrabar et l'adverse selection des entrées. L'ATR élargit les stops mais ne démontre pas leur immunité à ces queues de distribution. La taille de cet effet exige un rejeu Binance/Bybit synchronisé et une mesure des déclenchements divergents ; une simple conversion « écart de close = coût » serait fausse.

### 10. Long-only, sizing et conclusion sur les familles

**[CONFIRMÉ]** L'univers exclut short, dérivés, funding et basis ; les conclusions ne portent donc pas sur l'ensemble du trading crypto. Cela ne constitue toutefois aucune preuve que les outils exclus produiraient un edge exploitable avec ce capital. Sources : [CONTRAINTES §7](../../docs/CONTRAINTES_POST_B4.md#L93), [univers P7](../../scripts/p7_grids.py#L31).

**[CONFIRMÉ]** Le texte promet une alternative « Sharpe supérieur OU drawdown fortement amélioré à rendement comparable », mais le sélecteur P7 exige le benchmark Sharpe : cette branche économique alternative n'est pas codée. Une faible exposition cash peut expliquer un faible rendement absolu ; elle n'invalide pas automatiquement le Sharpe. Dans le modèle idéal à cash non rémunéré, exposition proportionnelle et frais proportionnels, multiplier tous les rendements par une constante positive conserve le Sharpe. Les affirmations des skills associant mécaniquement petit capital et faible Sharpe sont donc injustifiées. Les tailles fixes, planchers et changements d'exposition peuvent casser cette invariance ; ils doivent être mesurés. Sources : [CONTRAINTES §4](../../docs/CONTRAINTES_POST_B4.md#L54), [critère 7](../../scripts/p7_report.py#L312), [skill backtest](../../skills/backtest.md#L337).

**[CONFIRMÉ]** Le vrai défaut du benchmark DCA est le mélange dépôts/rendements et l'absence de cash du portefeuille, ainsi que **2 355 USDC d'apports BTC/ETH** face à 1 000 USDC initiaux pour la stratégie. Détenir du cash n'est pas en soi une erreur de Sharpe. Un Sharpe arithmétique positif avec un rendement composé négatif n'est pas non plus mathématiquement impossible. Le « pire P&L/investi » du rapport n'est pas le drawdown pic-à-creux d'une valeur de part. Sources : [B4 §5](../B4_bybit_backtest_report.md#L235), [benchmark DCA](../../scripts/compute_benchmarks.py#L181).

**[PROBABLE]** La phrase « les fees Bybit ont tué les stratégies » confond plusieurs interventions simultanées : re-stamp, liquidation, comptabilité, paramètres et coûts. B4 §1 les reconnaît. Une attribution causale aux seuls frais exige une comparaison contrôlée à moteur/données/paramètres identiques.

### Classement final de la phase 1 — impact décroissant

1. **Validité des simulations et métriques :** annualisation, grid 5m/4h, DCA lazy, MaxDD et PF. Les chiffres servent à décider mais certains ne mesurent pas ce qui est annoncé.
2. **Validité hors échantillon :** sélection avec le futur, benchmark désaligné et comptes réinitialisés. Aucune preuve indépendante de la procédure globale.
3. **Biais contre la basse rotation :** nombre de trades arbitraire, PF impropre au DCA, absence d'état « inconclusif » ; ordre minimum expliquant probablement une partie des zéros.
4. **Transfert vers l'exécution EU :** touch, PostOnly, stops réellement simulés, proxy et coûts conditionnels non validés.
5. **Portée des conclusions :** insuffisance de régimes indépendants, recherches multiples, portefeuille live non évalué et généralisation des implémentations aux familles.

**Fin de phase 1 :** aucune nouvelle stratégie validée n'a été découverte. L'audit démontre des raisons de rouvrir la validation technique et statistique ; il ne démontre pas un droit au passage en paper ou en live. Les amplitudes exigeant des données absentes restent ouvertes, plutôt que remplacées par des estimations inventées.

## PHASE 2 — Corrections prioritaires du dispositif

Les charges ci-dessous sont **[SPÉCULATIF]**, estimations en journées de travail concentré pour une personne connaissant le dépôt, hors temps de collecte et de calcul. Les effets sur B4 distinguent ce qui est prouvé de ce qui demande un rejeu.

| Priorité | Livrable concret et condition de vérification | Charge estimée | Ce que cela aurait changé dans B4 |
|---|---|---:|---|
| **1. Mesure commune** | Exporter equity/cash/inventaire/flux externes horodatés ; un seul calcul de rendements quotidiens pour stratégie et benchmarks ; MaxDD relatif ; PF net des deux jambes ; coûts terminaux comparables ; tests avec trajectoires synthétiques dont les résultats sont connus. | 2–3 j | **CONFIRMÉ :** détecte les erreurs démontrées, retire l'argument du grid « dix fois trop faible ». Le facteur seul laisse 0/35. Le verdict avec toutes les métriques corrigées est inconnu. |
| **2. Fidélité de la stratégie simulée** | Séparer bougies de contrôle des fills et bougies alimentant les indicateurs ; préenregistrer tous les indicateurs ; tracer signaux, refus, minimum d'ordre et fills ; comparer les mêmes événements dans replay et chemin runtime ; corriger la dette d'appariement SOL avant tout usage. | 3–5 j | **CONFIRMÉ :** grid et boost DCA auraient nécessité correction avant interprétation. **PROBABLE :** les tests vides DCA auraient reçu une explication d'exécution. Nombre final de survivants inconnu. |
| **3. Validation chronologique et objectif adapté** | Pour chaque fenêtre externe, choix des paramètres seulement avec le passé ; inventaire/equity continus ; benchmark exactement synchronisé, incluant B&H à exposition comparable ; retenir un bloc final non consulté ; protocole spécifique accumulation/basse rotation, sans minimum de trades universel. | 3–5 j | **CONFIRMÉ :** le « WF OOS » actuel n'aurait pas été accepté comme preuve indépendante. **PROBABLE :** évite certains faux négatifs de protocole et réduit les performances favorisées par sélection ; pas de résultat chiffré avant exécution. |
| **4. Coût d'exécution et proxy falsifiables** | Scénarios spread/slippage ×0,5/1/1,5, puis stress par régime et sortie ; coûts en bps du notionnel ; rejets PostOnly/TTL/fills partiels ; journal quote-signal-ordre-fill ; rejeu EU/Binance sur période commune, comparaison déclenchements/MAE/fills ; courbe du coût maximum supportable. | 2–4 j de code + 2–4 semaines initiales d'observation | **CONFIRMÉ :** remplace les 21 relevés et le touch par des hypothèses testables. La sensibilité partielle BTC est petite ; le verdict campagne sous modèles conditionnels reste inconnu. Quelques semaines ne certifient pas les crises rares. |
| **5. Puissance, recherche multiple et régimes** | Journal de tous les essais, y compris abandonnés ; matrice quotidienne des rendements ; bootstrap par blocs préservant dépendances temporelles et cross-paires ; distribution du meilleur score sous absence d'edge ; edge artificiel injecté pour mesurer les faux négatifs ; DSR en complément, PBO si matrice/configurations suffisantes ; attribution avec régimes définis avant analyse et sorties « insuffisant ». | 3–5 j | **CONFIRMÉ :** aurait empêché d'assimiler 212 configs/280 runs à des preuves indépendantes. **PROBABLE :** aurait quantifié la fragilité du meilleur ETH et l'impuissance du protocole pour certaines stratégies lentes. Taux de faux positifs B4 actuellement inconnu. |

Précisions qui conditionnent ces livrables :

- **[PROBABLE]** DSR ou PBO ajoutés aux métriques actuelles donneraient une précision trompeuse. Ils arrivent après correction des rendements et de la sélection. Ils ne rendent pas de nouveau vierge un historique déjà exploré. [Référence DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).
- **Proposition normative :** pré-écrire l'effet minimum acceptable, les pertes maximales et les conditions de rejet. Pour une stratégie lente, retirer le seuil de rotation ne suffit pas : si l'historique ne permet pas de distinguer cet effet du bruit, conclure « inconclusif ». Le budget de deux familles par cycle n'efface pas les essais des cycles précédents. [CONTRAINTES §7](../../docs/CONTRAINTES_POST_B4.md#L93).
- **[CONFIRMÉ]** Les données existantes permettent d'envisager une étude de 2022 pour BTC/ETH, mais pas de prétendre à une année native USDC complète : les trous 164/455 jours demeurent. Une série proxy supplémentaire doit être identifiée comme telle, avec son risque de base, et ne peut être déclarée holdout vierge parce qu'elle a une autre quote. [B4 §2](../B4_bybit_backtest_report.md#L47).
- **Proposition normative :** benchmark d'exposition indispensable à un overlay de risque. Réduire le MaxDD en gardant du cash ne démontre aucune compétence de timing. Comparer à une allocation B&H/cash passive soumise au même budget de risque, aux mêmes cash-flows et aux mêmes coûts.

### Classement final de la phase 2

**Mesures et replay fiables → sélection chronologique et benchmark commun → exécution/coûts/proxy → puissance et contrôle des essais.** La collecte nécessaire aux coûts peut commencer en parallèle. Aucune de ces étapes n'exige d'ajouter une nouvelle famille de stratégie.

## PHASE 3 — Familles proposées

**Je ne soumets aucune famille comme satisfaisant honnêtement le ticket d'entrée sur la base des éléments disponibles.** Cela ne signifie pas qu'aucune stratégie long-only rentable ne peut exister ; cela signifie qu'aucune proposition étayée ne ressort de ces preuves avec les sept réponses exigées.

1. **[CONFIRMÉ] Les reparamétrages techniques sont hors filtre.** Rallonger SuperTrend/Donchian ou espacer davantage une grille ne fournit pas à lui seul un mécanisme nouveau. Les corrections du simulateur sont nécessaires pour juger ce qui a été testé ; elles ne constituent pas un nouveau mécanisme de profit. [CONTRAINTES §5–6](../../docs/CONTRAINTES_POST_B4.md#L67).
2. **[SPÉCULATIF] Acheter après des ventes forcées peut être une hypothèse de recherche, pas une proposition admissible ici.** Les OHLC seuls ne démontrent ni la présence de vendeurs forcés, ni une pression temporaire destinée à se résorber, ni le mouvement moyen récupérable après coûts. La base documentée ne contient pas l'orderflow, le funding ou les liquidations nécessaires pour vérifier cette histoire. [CONTRAINTES §6–7](../../docs/CONTRAINTES_POST_B4.md#L79).
3. **[SPÉCULATIF] Un overlay lent BTC/cash peut améliorer un compromis rendement/drawdown.** Mais sa basse rotation ne prouve ni un mécanisme de timing ni un mouvement capturé moyen de 20–50 %. Avant d'en faire une famille, il faut montrer ce que la règle apporterait face à un B&H/cash de risque comparable, et d'où viendraient les épisodes indépendants permettant de la falsifier. Les documents autorisent ce changement d'objectif ; ils n'en démontrent pas l'efficacité. [CONTRAINTES §3–4](../../docs/CONTRAINTES_POST_B4.md#L40).

**[PROBABLE] Le filtre « qui perd structurellement ? » gagne à distinguer alpha et gestion du risque.** Il est utile pour démasquer une histoire de trading sans contrepartie économique ; une allocation de risque n'exige pas nécessairement un participant identifiable qui perd à chaque trade. Pour un overlay, le mécanisme à exiger est une relation testable entre risque prévu, rendement futur et coût d'ajustement. Relâcher cette formulation ne constitue pas une preuve d'edge.

### Classement final de la phase 3

1. **Aucune famille admise maintenant.** Réparer la capacité à accepter ou réfuter une hypothèse est prioritaire.
2. **Si l'objectif devient la maîtrise du drawdown**, préciser d'abord le benchmark et les concessions de rendement ; l'overlay demeure une hypothèse, pas une sélection.
3. **Ne pas contourner le manque de preuve** en proposant short, funding, basis ou ML : ils sortent du mandat, et rien dans B4 ne prouve leur rentabilité dans un autre cadre.

## Informations manquantes à demander

1. Où sont les courbes d'equity horodatées et les journaux complets des trades/signaux/rejets de la campagne B4, s'ils ont été conservés au-delà des JSON agrégés ? Ils permettraient des recalculs exacts ; à défaut, un rejeu est nécessaire.
2. Quelle règle de stop faut-il réellement valider : contrôle sur clôture 4h, sur chaque tick, ou ordre conditionnel natif de l'exchange ? Le prompt et le comportement du backtest diffèrent.
3. Quels historiques n'ont jamais servi à choisir une stratégie, ses paramètres ou le protocole ? La simple présence de données plus anciennes ou plus récentes ne garantit pas un holdout intact.

Ces absences empêchent de chiffrer un verdict entièrement corrigé, le biais maker et le coût conditionnel des stops. Elles n'empêchent pas de démontrer les défauts ci-dessus.

## Périmètre et preuves de lecture

- **76 Markdown de projet**, plus le README technique de `.pytest_cache`, lus dans le dépôt initial ; fichiers historiques inclus. Couverture répartie, inventaire consolidé sans fichier manquant : [inventory.json](inventory.json).
- ZIP : **364 fichiers**, dont **66 Markdown**, tous identiques octet par octet aux fichiers locaux correspondants. Archive inventoriée et extraite dans un répertoire temporaire ; SHA-256 conservé dans l'inventaire. Son commentaire Git est `8e327b000a2813b93070dd26506d4df9b1bfc257` : les versions exécutées des campagnes restent celles inscrites dans leurs rapports.
- Code inspecté sur les chemins pertinents ; aucune affirmation de lecture ligne à ligne de tous les fichiers Python, ni de certification totale du système.
- JSON P7 réagrégés avec le code de reporting réel : 35 verdicts et sélection vide reproduits exactement, 204 flags retrouvés. Méthodes de calcul des moteurs exécutées isolément sur une courbe synthétique ; PF et sensibilité partielle recomputés sur un dump de trades existant. Aucun nouveau backtest OHLC complet ni accès à la DB distante.
- Notes de travail : [statistiques](stats_audit.md), [exécution](execution_audit.md), [historique](history_audit.md). Les notes intermédiaires sont conservées pour traçabilité ; les conclusions de ce rapport prennent en compte leurs compléments.
- Artefacts de reproduction : [reproduce_stats.py](reproduce_stats.py), [stats_reproduction.json](stats_reproduction.json), [reproduce_metrics.py](reproduce_metrics.py), [metrics_evidence.json](metrics_evidence.json).

**Décision proposée : conserver la sélection paper vide, rouvrir la validation du moteur et du protocole, et suspendre les conclusions générales sur la mort économique des familles jusqu'à leur réévaluation correcte.**
