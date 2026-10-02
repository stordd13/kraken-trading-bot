# Audit trader — chemin paper/live (Astra, 2026-10-02)

> Audit externe du repo au commit `ff5d18b` (dev, post-merge campagne + docs), conduit par Astra à la demande de
> Bruno : architecture, collecte, indicateurs, stratégies, exécution, backtests, C1-C3. Consigné le 2026-10-02 ;
> relecture croisée Claude le même jour (les huit sites cités relus au tip — constats cohérents avec les
> reproductions annoncées ; dettes 31 et 32 confirmées par le code seul). Suivi : dettes **26-32**,
> `ROADMAP.md` § « Dettes ajoutées le 02/10/2026 » ; `PROJECT_CONTEXT.md` § 9.
>
> **Portée** : ces défauts concernent le chemin paper/live du trader, **masqué** (`systemctl mask` depuis le
> 16/09). Ils ne démontrent **aucune** invalidité supplémentaire du verdict C3 grid. Correction : chantier
> dédié, préalable au premier paper utilisant ces chemins (prérequis B5) ; si une future campagne réutilise
> l'un de ces chemins, la correction devient un préalable à cette campagne.

## Contexte vérifié par l'auditeur

Campagne grid v2 inconclusive pour provenance (`P_PROVENANCE`), fermeture distincte de la famille grid, deux
familles restantes. Les producteurs C3 actuels prennent uniquement en charge la grid : les autres familles
demanderont une adaptation.

## Sept défauts confirmés (reproductions locales par l'auditeur)

1. **Un ordre market accepté est considéré comme entièrement exécuté.** Une réponse contenant seulement
   l'identifiant devient un trade `FILLED`, à la quantité demandée, au prix du signal et avec zéro frais, sans
   confirmation d'exécution. — `src/krakenbot/connectors/bybit/rest.py:928` (dette 26)
2. **Une annulation échouée est déclarée réussie.** `cancel_profit_target()` retire le suivi avant
   confirmation, appelle Bybit sans la paire requise, puis marque l'ordre annulé malgré l'erreur. L'ordre peut
   rester actif sur l'exchange. — `src/krakenbot/execution/order_manager.py:587` (dette 27)
3. **Les exécutions partielles suivies d'une annulation sont perdues.** Reproduction : l'exchange annonce
   `filled=0.4`, mais le gestionnaire conserve zéro exécuté et supprime l'ordre du suivi. —
   `src/krakenbot/execution/order_manager.py:483` (dette 28)
4. **Les mises à jour d'une bougie ouverte alimentent les indicateurs comme des bougies supplémentaires.**
   Vingt mises à jour d'une seule bougie non clôturée suffisent à rendre une EMA20 disponible. Cela fausse les
   indicateurs et la comparaison avec les backtests. — `src/krakenbot/strategies/multi_strategy_router.py:308`
   (dette 29)
5. **La limite de perte quotidienne bloque aussi les ventes de sortie.** Reproduction : avec une limite de 10
   et un P&L de −11, un SELL disposant du solde nécessaire est refusé. Un stop-loss peut donc être empêché par
   le contrôle de risque. — `src/krakenbot/execution/risk.py:218` (dette 30)
6. **Le crash protector peut vendre la mauvaise paire.** Avec une position ETH, un signal BTC/USDC est émis :
   la paire globale est appliquée à toutes les positions. La quantité du lot manque également. —
   `src/krakenbot/strategies/multi_strategy_router.py:473` (dette 31)
7. **Le warmup charge les bougies les plus anciennes.** Le `ORDER BY ASC LIMIT` sélectionne le début de
   l'historique. Sur 200 bougies synthétiques, l'initialisation utilise les 100 anciennes et ignore les 100
   récentes. — `src/krakenbot/indicators/multi_timeframe.py:269` (dette 32)

## Vérification locale de l'auditeur

3 326 tests réussis, un échec attendu ; tests nécessitant la base ou Bybit exclus. Lint du périmètre contrôlé
passé. Dettes déjà documentées retrouvées, notamment la liquidation terminale absente du moteur signal
(dette 19) et la double alimentation des indicateurs Gemini (dette 18).
