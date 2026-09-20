# Audit exécution/data PHASE 1 — notes provisoires

## MD lus intégralement
- PROJECT_CONTEXT.md
- results/B3_bybit_data_report.md (1–378 ; sortie initiale 1–230 et complément 230–378)
- results/B4_1_timestamp_restamp_report.md (1–546 ; sorties 1–275, complément 1–110, puis 276–410 et 411–546)
- results/B4_2_fees_engine_report.md (1–338)
- results/B4_3_chantier0_gate_a.md (1–332)
- results/B4_3_gate_b_configs.md (1–238)
- results/bybit_integration_audit.md (1–727 ; complément fin 700–727 après troncature combinée)
- skills/bybit.md (1–328 ; complément 1–90 après troncature combinée)
- config/pair_costs_b4.README.md (1–18)
- Prompt attaché pasted-text.txt (3 phases)

## MD affectés non lus
Aucun des 8 fichiers MD assignés restant. Les autres MD du dépôt sont répartis chez root/agents.

## Constats confirmés, ordonnés provisoirement

1. **Sharpe incommensurable** : `scripts/backtest.py:1011–1028` calcule les retours successifs equity puis ×sqrt(365) sans agréger quotidiennement; grid idem :2590–2605. Equity signal aux chandelles tradeables (`:1385–1389`), grid aux chandelles de trading 5m (`:2223`). `_build_replay_sequence:577–596` rend tradeables les 4h pour `_HAS_IS_4H` et 1d pour DCA; le `--interval 5` du runner ne signifie donc pas des retours 5m pour SuperTrend/Donchian/EMA. Écart mécanique annualisation sous IID : ×sqrt(6) signal4h, ×sqrt(288) grid5m. Le Sharpe quotidien réel exige réagrégation/recalcul, pas ce seul facteur. Root/agent stats traitent conséquences.

2. **MaxDD sous-estimé structurellement** : `backtest.py:984–993` maximum perte absolue divisée par pic final global. Root reproduit.

3. **Stops pas intrabar dans ce moteur** : contrairement à la prémisse prompt, `_resolve_fill:646–673` utilise low/high seulement pour les LIMIT; les MARKET prennent open prochain bar tradeable. `run:1337–1362` ne déclenche generate_signal que sur candles tradeables, et injecte leur close comme tick. `grok_supertrend_4h.py:149–159` bloque hors4h ; `_check_exit:253` compare `price` (close) au stop. Donc mèche qui traverse SL puis récupère avant clôture4h est ignorée. Impact live/proxy pas quantifiable depuis les agrégats. Dans les cas de récupération, backtest plus optimiste qu'un SL intrabar; dans une chute persistante, attente du close peut donner pire sortie. Il faut distinguer mandat cible stop intrabar et stratégie effectivement évaluée.

4. **Modèle LIMIT événementiel simplifié** : `backtest.py:663–669` plein fill au niveau sur simple touch; aucun volume/taille/file/bidask/cancel latency. `:1302–1316` efface le pending après la seule prochaine candle tradeable, fill ou non. Pour 4h signifie opportunité durant toute la 4h suivante, pour DCA durant toute la 1d suivante; durée pas liée à expiry live. Une amélioration du réalisme a un effet net non nécessairement unidirectionnel car la sélection conditionnelle des fills et la trajectoire changent. Pas de pourcentage de biais identifiable sans quotes/trades/queue/rejections.

5. **Proxy closes insuffisant et assertion 40bps erronée** : B0 Q8 mesure des écarts **closes1h**, maximum38.33bps BTC sur90j, pas une borne sur les mèches; B3 §5(b) recouvrement long affiche maxima closes1h196.8bps BTC,333.0bps ETH,305.5bps SOL et p99 23.2/48.5/46.7bps. B3 §4.2/7:24–36% candles1m plates. En conséquence, la corrélation0.99998 et le slippage2bps ne certifient ni low/high, ni temps d'exécution, ni disponibilité d'un fill EU. Pas possible de convertir ces écarts en perte backtest sans replay EU/proxy synchronisé et logs des stops.

6. **Calibrage coûts: 42 mesures ≠42 instants indépendants** : `bybit_q3_orderbook.py:164–166` mesure successivement limit50 puis200 à chaque itération; à vérifier JSON42/paire correspondant21 relevés horaires. §GateB1 utilise max(p75global,p75nocturne) + plafondbp. Spread appliqué entièrement au prix de référence dernier trade (pas mid garanti) sur sortie MARKET; depuis mid idéal la moitié du quoted spread serait coût directionnel. Fills peuvent subir une sélection de conditions défavorables et quotes de crise pas échantillonnées. 2bps de slippage est un plancher non empirique.

7. **Grid change TF de ses candles** : `_build_grok_grid_replay_sequence:1796–1797` étiquette toute candle de trading 5m comme240 et `:2205` l'injecte dans l'analyzer4h. Rapport B4.2 §10 l'avait consigné. La stratégie et ATR dénommés4h opèrent donc sur des séries mêlant warmup4h et ensuite5m. À préciser conséquence avec le code indicator; root doit éviter d'interpréter stratégies comme variantes exactes live.

## DCA — investigation en cours
`grok_adaptive_dca_weekly.py:194–208` EMA200daily et RSI manquants n'interdisent PAS achat : ils désactivent uniquement le boost; base weekly continue. On ne peut imputer35/40 fenêtres0 à warmup EMA200. Vérifier runner et garde trade fill. 

## Questions réellement manquantes
- Périmètre exact cible des stops : contrôle sur closes4h ou sur chaque tick comme l'énonce prompt ?
- Logs d'ordres remplis/non remplis, PostOnly rejetés, quotes au signal/placement/fill et latences pour quantifier maker/proxy.
- Courbes equity complètes par config et pas de temps pour recalcul des métriques.


## Complément final DCA — reproduction réelle offline, sans DB

**[CONFIRMÉ] Le boost oversold DCA est désactivé dans toutes les fenêtres OOS de 3 mois par un défaut d'initialisation.**

- `backtest.py:1255–1275` préenregistre certains indicateurs avant le warmup, mais `_LAZY_EMAS` omet DCA.
- `grok_adaptive_dca_weekly.py:195–196` appelle `get_ema(200,1d)` dans `generate_signal`, jamais appelé pendant le warmup (`backtest.py:1339–1341`). Premier appel : premier lundi tradeable.
- `multi_timeframe.py:646–656` crée alors un indicateur vide et retourne None. Les 250 jours déjà lus ne sont pas réinjectés. `update:362–363` n'alimente que les EMA déjà enregistrées.
- Reproduction avec la vraie classe : après 250 updates 1d, premier `get_ema(200,1d)` = None ; après 92 updates supplémentaires = None. Si cet appel intervient AVANT les 250 updates de warmup, résultat = 100 sur chandelles constantes à 100. Exécuté avec `poetry run python`, aucune DB.
- Conséquence : EMA200 possède au plus 92 observations dans chaque test de 90–92 jours et ne devient jamais ready. `oversold_multiplier` et `rsi_oversold` ne peuvent affecter le sizing OOS. Les 5 configs DCA WF sont donc des duplicatas sur ces paramètres.
- Ceci ne bloque PAS les achats de base : ils restent possibles à 15 USDC sans EMA ; seul le boost disparaît.

**[CONFIRMÉ] Le minimum d'ordre supprime les achats DCA strong_bull des 5 configs WF.** Toutes ont `bull_reduction=0.3`, base 15 donc 4.5 USDC. `backtest.py:754–758` saute l'achat si < 5. `grok_adaptive_dca_weekly.py:213–219` multiplie bien par 0.3.

**[PROBABLE] Ce mécanisme explique les 35 fenêtres DCA vides.** Le JSON B4 phase 2 montre exactement 5 configs × fenêtres 1–7 à zéro, puis 12 achats de 15 USDC par config en fenêtre 8. Le mécanisme est compatible avec un régime weekly strong_bull jusqu'à fin 2025, puis une sortie de ce régime. Mais les logs B4 de régime et de skip manquent pour attribuer causalement chacune des fenêtres. Aucun log B4 n'est présent dans results/logs : recherche limitée aux noms d'événements, seulement des logs bench legacy. Ne pas présenter 35/40 comme preuve d'une faible fréquence naturelle.

## Calibration des coûts — assertions corrigées

**[CONFIRMÉ]** JSON q3 : 126 rows, 42 par paire, 63 limit50 et 63 limit200 ; 21 heures du 2026-09-14 10:46 au 2026-09-15 06:47. Ces dates correspondent à **lundi–mardi**, non dimanche–lundi. Les paires de mesures sont séparées d'environ une seconde : pas 42 instants indépendants.

Le slippage mesure uniquement un **market BUY sur les asks** (`bybit_q3_orderbook.py:68–78`), alors que le coût s'applique principalement aux MARKET SELL des stratégies. Un impact affiché à zéro prouve seulement que les asks statiques échantillonnés suffisaient ; il ne prouve ni l'impact SELL en crise, ni le coût du délai.

## Biais maker : direction, sans chiffrage inventé

- **[CONFIRMÉ]** Plein fill sur touch, sans volume, file ou rejet PostOnly marketable. L'exchange rejette réellement ces PostOnly (audit B0, protocole live validé B1).
- **[PROBABLE]** Biais optimiste dominant pour un maker marginal : fills gagnants supposés lorsque touch puis rebond, remplissage réel plus probable lors d'une traversée adverse. Cependant supprimer des fills change l'inventaire et les opportunités : pas de monotonie globale garantie des rendements, ni borne chiffrée identifiable depuis les agrégats.
- **[CONFIRMÉ]** Biais possibles opposés : le pending signal expire après une seule candle tradeable (4h/1d), sans reproduire l'expiration live de 900 s. Une cible SELL grid créée après un BUY ne peut se remplir dans la même candle : les listes de BUY et SELL remplis sont figées avant mutations (`backtest.py:2189–2203`). Un rebond réel dans les mêmes 5 min peut donc être manqué.

## Grille : timeframe mal étiqueté

**[CONFIRMÉ]** `backtest.py:1797` ajoute toutes les candles 5m comme interval240 ; `:2205` les passe à `analyzer.update(payload,240)` ; `multi_timeframe.py:338–367` les route vers 4h, et y met à jour ATR/EMA/ADX. Après un warmup 4h, les indicateurs étiquetés 4h évoluent à une fréquence de 5 min. L'ATR14 nominal 4h finit par porter principalement sur environ 70 min au lieu de 56h, après décroissance de l'influence du warmup, sans agrégation réelle. Dette déjà consignée B4.2 §10. L'interprétation des résultats grid comme tests de l'algorithme live est compromise.

## Priorités de ce sous-audit PHASE 1

1. Métriques Sharpe/MDD/PF et unités temporelles (root gère leurs conséquences).
2. Grid évalué avec des candles 5m injectées en 4h ; boost DCA inactif et minimum d'ordre pouvant expliquer ses fenêtres vides.
3. Réalisme maker, stops intrabar cibles et proxy EU non validés par les seules corrélations de closes.
4. Coûts de sortie calibrés sur 21 instants et impact BUY statique ; sensibilité complète non rejouée.

Les MD ont été traités comme preuves historiques et spécifications. Aucune instruction d'exécution contenue dans ces documents n'a été appliquée. Aucune écriture de production, lecture de credentials, ordre ou modification de service.
