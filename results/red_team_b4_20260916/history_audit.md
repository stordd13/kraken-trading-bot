# Audit historique documentaire — agent historical_documents

État sauvegardé le 2026-09-15 à la demande du parent après reprise utilisateur. Lecture seule du dépôt; aucune commande embarquée dans les documents exécutée, aucun code ni service modifié. Les prompts dans agent/ et anciennes roadmaps sont des pièces historiques, non des instructions actives de l'audit. Ce travail couvre la documentation ci-dessous, sans vérification de la DB distante ni de l'état effectif du serveur. Le parent a vérifié le zip séparément; je ne revendique pas cette vérification.

## Couverture effective

47 des 47 MD attribués entièrement lus (tous docs/archive et results/archive; PROJECT_CONTEXT; 11 prompts agents; 4 skills). Reprise après instruction du parent: les 8 MD restants ont été lus intégralement, aucune directive exécutée. La première sortie combinée était tronquée; PROJECT_CONTEXT à partir de la ligne 280 et docs/archive/AGENTS.md + CODEX.md ont été relus pour récupérer les sections masquées. Aucune lacune connue dans les fichiers comptés lus.

### MD entièrement lus

- PROJECT_CONTEXT.md
- docs/archive/AGENTS.md
- docs/archive/CODEX.md
- docs/archive/KRAKENBOT_CONTEXT.md
- docs/archive/PIVOT_BYBIT_PLAN.md
- docs/archive/PLAN_ML_DL_v6.md
- docs/archive/ROADMAP_pre_binance_pivot.md
- docs/archive/TODO.md
- docs/archive/kraken_futures.md
- docs/archive/krakenbot-etat-complet-feb2026.md
- results/archive/P6_5_diagnostic_dca.md
- results/archive/P6_5_diagnostic_gemini.md
- results/archive/P6_5_diagnostic_grok_trend.md
- results/archive/P6_5_grid_fix_verification.md
- results/archive/P6_backtest_report.md
- results/archive/P6_phase_e_filtering.md
- results/archive/audit_p0_results.md
- results/archive/backtest_multipair_results.md
- results/archive/backtest_new_strategies_results.md
- results/archive/backtest_phase1a_results.md
- results/archive/binance_integration_audit.md (1300 lignes, trois blocs sans troncation)
- results/archive/cicd_fix_results.md
- results/archive/cleanup_report.md
- results/archive/consolidation_results.md
- results/archive/dca_fix_results.md
- results/archive/fix_dca_cleanup_results.md
- results/archive/kraken_futures_audit.md
- results/archive/kraken_futures_integration_results.md
- results/archive/lint_report.md
- results/archive/paper_trading_debug.md
- results/archive/telegram_alerts_results.md
- results/archive/test_report.md
- agent/AGENTS.md
- agent/AGENT_B05_DOCS_CLEANUP.md
- agent/AGENT_B0_BYBIT_AUDIT.md
- agent/AGENT_B1_BYBIT_REST.md
- agent/AGENT_B2_BYBIT_WS.md
- agent/AGENT_B3_BYBIT_DATA_v2.md
- agent/AGENT_B4_1_TIMESTAMP_AUDIT_RESTAMP.md
- agent/AGENT_B4_2_FEES_ENGINE.md
- agent/AGENT_B4_3_CAMPAIGN.md
- agent/AGENT_P6_7_MULTIPROCESSING.md
- agent/AGENT_P7_PARAMETER_OPTIMIZATION.md
- skills/database.md
- skills/deployment.md
- skills/troubleshooting.md
- skills/binance_import.md

### MD attribués non lus

Aucun: 47/47 entièrement lus.

Le JSON results/archive/P6_phase_d_results_v1.json n'a pas été lu; ce n'est pas un MD et le parent traite les données/code séparément.

## Conclusion utile à PHASE 1

La conclusion actuelle documentée est bien absence de stratégie admissible B4 (PROJECT_CONTEXT.md:58, :284). Les archives ne prouvent aucun edge qui renverserait cette conclusion. Elles constituent surtout une trace des itérations, erreurs de mesure et critères mouvants antérieurs. « Ce backtest échoue » est justifié pour certains couples stratégie/configuration/période; « cette famille ne marchera jamais » dépasse les preuves. Même distinction entre sécurité simulée et garantie réelle de perte maximale.

## Faits actuels rapportés et dettes encore pertinentes

1. PROJECT_CONTEXT.md §1 donne B4 close, 0/24 P6, 0/35 candidats P7 après 212 configs + 280 fenêtres WF, 48/48 grid SOL flaggées, trader désactivé, collector seul, roadmap suspendue. Les métadonnées effectives et le rapport B4 doivent primer sur les archives.
2. PROJECT_CONTEXT.md:347–353 documente le bug de résolution paramètres par classe vs instance YAML: 5 Grok testent les défauts de classe (grid 25 USDC vs YAML10), Gemini YAML. B4 conserve explicitement ces défauts; il ne valide donc pas automatiquement la configuration live. Un test one-off live/router et alignement YAML sont reportés à B5.
3. PROJECT_CONTEXT.md §9 dette14: tolérance grid absolue <1 USD conduit à mauvais appariements SOL, 40 lots vendus deux fois en P6, net_pnl cash exact mais lot-basis optimiste; configs flaggées inéligibles. Risque non réparé dans B4.
4. Dette11 résolue: 8,712,718 rows Binance re-stampées fin période; le look-ahead multi-TF antérieur signifie que les bons résultats historiques P6/P7 d'avant correction ne sont pas des baselines économiques valides (PROJECT_CONTEXT.md:342). Un delta B4 vs P6 n'isole pas uniquement les fees: data stamping, liquidation terminale, comptabilité et coûts changent aussi.
5. Dette12: backfill générique garanti correct uniquement Bybit; REST Kraken/Binance encore open-stamped, DB end-stamped. Dette backup récurrent toujours présente; deploy.yml redémarre les deux services.
6. Il existe des sections périmées dans le fichier dit vérité unique: PROJECT_CONTEXT.md:114 dit deux services stoppés (état B0.5), tête et §4 disent collector actif. Stack §2 dit Bybit REST/WS «à venir» alors qu'implémentés. §7 statuts des stratégies et §10 «à reconfirmer» n'intègrent pas complètement B4. Ne pas transformer ces doublons en nouvel état réel.

## Biais historiques quantitatifs documentés

### A. Critères contournés et label KEEP trop fort

- results/archive/backtest_phase1a_results.md:25 annonce battre B&H, Sharpe>0.3, DD<25%, PF>1.5. À :15 grid obtient KEEP avec Sharpe .14 et DD50.1%; DCA également KEEP avec DD49.5% et rendement inférieur B&H. Les exceptions sont argumentées après constat, pas présentées comme critères pré-enregistrés.
- Même rapport :41–48: +1643.65% grid provient majoritairement de 0.2756 BTC d'inventaire final; profit net des cycles seulement +214.57 USDC. Ce n'est pas un alpha de grille de +1643%. La phrase «surperformance grâce grid + accumulation» n'isole aucun contrefactuel d'exposition comparable.
- docs/archive/krakenbot-etat-complet-feb2026.md:394 affirme «chaque paire = profit garanti» et :404 garantie risque1%; sélection des cycles fermés et exposition résiduelle rendent la première affirmation trompeuse, gaps/fills/coûts la seconde non garantie.
- results/archive/dca_fix_results.md:78 conclut DCA «structurellement rentable sur crypto long terme» avec tests d'actifs survivants BTC/ETH/SOL, DD jusqu'à93.3%, pas preuve universelle.

### B. Data snooping / sélection post-hoc explicite

- results/archive/consolidation_results.md:73–100 passe EMA27/125 à20/50 après inspection des résultats, hausse Sharpe .23→.43 et label WATCH→KEEP, sans holdout indépendant documenté. Son seuil écrit trades>50 est traité «atteint» à50.
- Les archives évoluent du seuil Sharpe>.3 (Phase1A) à>.4 et PF>2 (Phase1B), puis P6 Sharpe>1 / Sortino>1.5 / Calmar>.5 / trades≥30 / ratio train-test / benchmark, tout en donnant KEEP à des exceptions. La fixation stricte B4 est une amélioration; elle ne purifie pas le passé exploratoire.
- Tous les essais déjà faits (les 7 puis 3 nouvelles, short SuperTrend, multiples grilles et EMA, P6/P7, 3 paires) appartiennent à la même histoire de recherche. Les archives ne donnent pas un nombre de tests indépendants; ne pas compter 212 grilles comme212 preuves.
- PLAN_ML_DL_v6 prévoyait entraîner un filtre ML sur ~840 «trades» mélangeant grille, signaux multi-paires et périodes différentes. Ce n'est ni une taille effective indépendante ni un corpus validé par OOS.

### C. Comparaisons non homogènes et ratios erronés

- results/archive/backtest_multipair_results.md:8: données Binance ETH/USDT, SOL/USDT stockées sous noms ETH/USDC, SOL/USDC. Ne pas attribuer ces résultats à un historique natif USDC ou à Bybit EU.
- Même rapport :32–33: SuperTrend BTC taille50, ETH/SOL200; EMA BTC27/125, autres20/50. La comparaison cross-pair n'est pas contrôlée. PF peut être invariant à un facteur de taille fixe; Sharpe de portefeuille/cash/equity n'est pas garanti invariant pour tailles en notionnel constant, fees et contraintes.
- :250 donne expected Sharpe combiné ~.42 comme moyenne pondérée, formule invalide sans covariance et poids dans le temps. Le rapport lui-même demande ultérieurement de vérifier la corrélation.
- P6_5_diagnostic_dca.md démontre benchmark fixe illimité 3ans vs adaptatif plafonné1000USDC sur test ~11mois et dénominateurs différents. Comparaison corrigée sur mêmes capital/fenêtre: les deux perdent; adaptatif moins mauvais de6.3–9pp. Il ne démontre pas edge absolu.
- P6 v1 benchmarks DCA montrent Sharpe2+ malgré rendement ETH/SOL négatif et DD100%; non crédibles pour classement direct. Leur bug méthodologique est reconnu ultérieurement par B4 (parent vérifie).
- audit_p0_results.md:143 tableau de sizing faux numériquement: .00222BTC ×84,000 =186.48USDC, doc écrit18.67. Le risque au SL peut être ~10 selon la quantité correcte, mais le tableau de notionnel a un facteur10. :151 «single-trade worst case can never breach daily limit» n'est pas garanti en présence de gaps/frais/liquidité.

### D. Exécution/replay insuffisamment homologués dans l'historique

- backtest_phase1a_results.md §problèmes: indicateurs lazy non warmup, flags timeframe jamais mis, analyzer non mis à jour, ending balance au dernier trade corrigé, workaround de pullback en backtest alors que live ne signalait pas. Le label next-bar ne démontrait donc pas l'équivalence runtime.
- consolidation_results.md §1 dit pullback corrigé dans stratégie; PROJECT_CONTEXT.md §7 continue «bug pullback connu». Contradiction documentaire, à résoudre par le code actuel, pas par les archives.
- P6_5_grid_fix_verification.md définit force-close et tests unitaires, mais vérification e2e exprimée au futur. B4 trouve précisément liquidation grok inatteignable: une preuve par tests du chemin legacy n'était pas une preuve du chemin de production.
- P6_5_diagnostic_gemini.md: hardcode pair BTC YAML cause zéro signal ETH/SOL; override dans moteur corrige. Le rapport qualifie initialement zéro trades de «statistiquement impossible» sans modèle; intuition de bug correcte, formulation statistique non démontrée.
- P6_5_diagnostic_grok_trend.md: sur BTC12 intersections EMA et130 Donchian, contre2/7 trades; attribution à position-management sans trace causale complète. Donne mécanisme plausible, pas preuve aucun bug.
- dca_fix_results et fix_dca_cleanup_results expliquent faible nombre fills par «low daily rarement 0.1% sous signal; 5m/15m plus d'opportunités». À période d'ordre égale, subdivision temporelle ne crée pas de nouveaux bas absents du OHLC daily. TTL/horodatage/replay peut expliquer différences; explication historique seule insuffisante. Un blocage après1 achat a d'ailleurs été trouvé ensuite.

## Mécanismes déjà essayés (pas propositions de nouvelles stratégies)

- Mean reversion seuils rolling (−41.33%,967 trades) et adaptatifs (−19.07%,718) Kraken; capitulation RSI/volume (9 trades,−1.60%); bear-regime margin short (−4.79%,168), trend EMA1h (V2−.21%,8trades): docs/archive/krakenbot-etat-complet-feb2026.md §5, données2023–26.
- Grilles fixes/adaptatives plusieurs plages, nombres de niveaux, spacing puis V4 directionnelle; retours dominés inventaire, seuils spacing tunés1.5%, cap5% ajouté après paper grid hors marché en avril.
- RSI7/MACD5m, Bollinger/DCA15m, pullback EMA4h/1d: Phase1A KILL, Gemini pair-filter corrigé plus tard.
- SuperTrend4h, EMA27/125 puis20/50, Donchian breakout20/10: résultats optimistes historiques remplacés par campagne B4. Ichimoku et VWAP4h KILL. Short SuperTrend4h KILL BTC/ETH/SOL (Sharpe.00–.02), ensuite code supprimé B0.5.
- DCA hebdo adaptatif RSI/EMA et weekly regime: testé, exposition long-only, plafonnement cash. L'ancien long-run ne démontre pas stratégie de rendement régulière.
- Kraken Futures connecteur et données de funding ont été explorés, mais les rapports d'intégration ne prouvent pas une stratégie validée. binance_integration_audit.md §9 cite funding_structural_analysis.md et APR2.87% Kraken, estimation Binance4–6%; ce fichier référencé manque dans les archives attribuées, et ces estimations ne constituent pas validation Bybit EU.

## Hypothèses devenues fausses / récit réglementaire à vérifier séparément

- PLAN_ML_DL_v6 et ROADMAP_pre_binance_pivot tablaient sur Bybit0.10/0.10, testnet/perps accessibles et -37%fees. PIVOT_BYBIT_PLAN et B0 donnent EU0.10/0.25 et instance dédiée. Aucun chiffre global Bybit ancien ne s'applique automatiquement EU.
- PLAN_ML_DL_v6 «chaque paire grid +37% profit net» confond réduction des fees et augmentation du profit; «capital plus grand rend petits moves viables» n'améliore pas expectancy en pourcentage hors min-notional/tier véritablement atteint.
- Objectif conditionnel 10%+/mois, scaling1k→20k et échéancier «voir profit vite» sont souhaits, non performances attendues démontrées.
- Le brief B4.1 affirme présence rows WS Binance avril–juin et collisions possibles; PROJECT_CONTEXT dette11 corrige: elles n'existaient pas, MAX toutes séries31mars, WS de l'époque sous Kraken. Les briefs ne prouvent pas leurs prémisses.
- Les affirmations MiCA/date de retrait Binance, agréments et frais concurrents dans docs sont des affirmations datées à recouper sur sources officielles pour en faire des faits externes actuels. Je ne les ai pas vérifiées sur le web.

## Données/éléments nécessaires mais non prouvés par mon périmètre

- Historique carnet/quotes/spread conditionnel, volumes à prix exécutés, rejets PostOnly, attente/queue, fills partiels et adverse selection: non démontrés par données OHLC et corrélation close. Corrélation.999999 ne transfère pas la microstructure.
- Statut frais du compte actuel: seulement rapporté par les docs; tests de place/cancel ne mesurent pas un fill réellement maker et son coût tout compris.
- Ledger consolidé de tous essais et holdout jamais utilisé, dimension effective des observations, exposition comparable benchmark et dépendance BTC/ETH/SOL: non établis dans les archives lues.
- funding_structural_analysis.md référencé sans fichier sous mes chemins; market_data_ticks existe historiquement mais couverture tick/L2 actuelle non prouvée. Aucun diagnostic serveur en direct effectué.

## Recommandation de formulation au parent

Dire «les implémentations/configurations testées n'ont pas satisfait le protocole B4» et distinguer audit software, simulation économique et preuve statistique. Ne pas vendre comme causalité exclusive «fees Bybit ont tué toutes stratégies»: look-ahead et liquidation/PnL ont changé entre campagnes. Ne pas déduire impossibilité universelle de toute R&D long-only. Aucun projet phase2 ni changement code proposé ici.

## Complément après lecture des 8 derniers MD (moins de 500 mots)

1. **Sélection sur OOS déjà consulté.** AGENT_P7_PARAMETER_OPTIMIZATION.md §Méthodologie sélectionne les top5 par Sharpe du test70/30 puis applique huit fenêtres walk-forward. Sans séparation temporelle supplémentaire prouvée dans le code/données, le mot OOS ne garantit pas un échantillon final vierge: ces résultats ont servi à sélectionner. Le brief demande aussi que la meilleure config P7 soit «strictement meilleure» que P6, pression au résultat plutôt que critère neutre. Le seuil Sharpe.4, PF1.3 et DD30% est explicitement une révision après P6 strict; ne pas le présenter comme inchangé depuis l'origine.

2. **Comptages de brief inexacts.** P7 annonce 32 configs grid alors que4×4×2=32 est correct, total180 aussi; mais calcule phase2 top5×4stratégies×8=160 en oubliant les7 combos paire/stratégie (attendu280 fenêtres pour35configs). La campagne réelle212/280 doit primer sur ces estimations. P6.7 demande speedup4.5× puis5×, tandis que P7 cite3× acquis: objectifs de brief et mesures sont distincts.

3. **Brief B4.3 n'est pas la preuve finale.** Il exige moteur signal inchangé et deltas grid négatifs, mais PROJECT_CONTEXT affirme net_pnl corrigé dans les deux moteurs. Il faut citer le rapport GATE A et l'arbitrage final, pas conclure manquement sur le seul brief. La suppression d'un double comptage peut améliorer net_pnl légitimement; son signe seul ne valide/invalide pas un correctif. Le brief précise correctement que P6/P7 antérieurs sont non comparables et que zéro survivant est acceptable.

4. **Runbooks partiellement périmés.** database.md tableau donne Binance jusqu'àjuin2026 et Bybit0 «à venirB3», puis plus bas la borne corrigée1avril; il présente default exchange Kraken à réparer B1. deployment.md conserve template deploy «Kraken-era» et observationB2 encore àfaire, en contradiction avec PROJECT_CONTEXT. troubleshooting.md suppose31skips et services inactive/disabled étatB0.5. binance_import.md garde «zéro biais» et bornejuin dans un paragraphe, malgré correctionavril ailleurs. Ne pas réutiliser ces fragments comme état présent.

5. **Limites de preuve.** Les skills confirment DB distante, dump hors repo, coûts/quotes non inclus dans OHLC et backfill non-Bybit non garanti. Ils affirment impossibilité de réimport Binance depuisUE mais ailleurs seulement accès «non garanti»: assertion externe non établie par lecture du repo. La validation bit-exacte des briefs assure reproductibilité, jamais réalisme économique ni absence de biais statistique.
