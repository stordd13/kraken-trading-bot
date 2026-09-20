# Chore — Mise à jour documentaire post-audit B4

> Brief agent. Mode : **review / ask-for-edit** — proposer les diffs, attendre validation avant application.
> Branche : `chore/docs-post-audit` depuis `dev`. Documentation uniquement, **aucun fichier code**.
> Les formulations fournies ici (addendum, résumés, dettes) sont **normatives** : les insérer telles
> quelles, ne pas les réécrire. Le travail de l'agent est mécanique : insertion, mise à jour de
> tables, cohérence.

## À lire avant de commencer

1. `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` (l'audit — contexte de tout ce chore)
2. `PROJECT_CONTEXT.md`, `ROADMAP.md`, `CLAUDE.md`, `docs/CONTRAINTES_POST_B4.md`, `results/INDEX.md`
3. `results/B4_bybit_backtest_report.md` (le rapport qui reçoit l'addendum)
4. `agent/chantier1_metriques.md` (référencé, ne pas modifier)

## Contexte (résumé)

L'audit red-team du 16/09 a invalidé l'instrument de mesure des backtests (défauts D1-D6 : unités de
Sharpe, MaxDD, PF, agrégation, equity non persistée, benchmark DCA) et le statut OOS du walk-forward.
Les constats ont été vérifiés indépendamment (code du tag + reproduction des JSON de campagne) et un
consensus à trois (Bruno, audit externe, revue interne) a fixé les décisions. Le chantier C1
(métriques) est en cours sur `feat/c1-metrics`. Ce chore met la documentation en cohérence **avant**
que C1 n'atteigne sa propre étape docs.

## Périmètre — 6 fichiers modifiés, 1 créé

### 1. `results/B4_bybit_backtest_report.md` — insérer l'addendum

Insérer le bloc suivant **verbatim**, immédiatement après le titre du rapport. Ne toucher à rien
d'autre dans le fichier : le corps reste une pièce historique.

```markdown
## ⚠️ Addendum du 16 septembre 2026 — portée des conclusions après audit de l'instrument

Un audit adversarial externe (`results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md`), dont les
constats principaux ont été vérifiés indépendamment sur le code du tag `v2.8.0-b4-3-campaign` et
reproduits depuis les JSON de cette campagne, a établi que l'instrument de mesure utilisé par ce
rapport comporte des défauts matériels : annualisation des Sharpe/Sortino sur des pas de temps
hétérogènes (√365 appliqué à des rendements 5 m / 4 h / 1 j selon la famille), MaxDD rapporté au pic
global final au lieu du pic courant, profit factor sans imputation de la fee d'achat, agrégation P7
transformant les PF infinis en 0 puis moyennant des ratios, walk-forward dont les candidats sont
sélectionnés sur une période chevauchant les fenêtres dites OOS, benchmark DCA comptant les dépôts
comme des rendements. Le replay grid a par ailleurs alimenté les indicateurs 4 h avec des bougies
5 m. La branche de renforcement « oversold » du DCA était inactive pendant les tests trimestriels,
faute d'EMA200 prête ; par ailleurs, les configurations retenues (`bull_reduction=0.3`) réduisent
l'achat de 15 USDC à 4,50 USDC en régime strong_bull, provoquant son rejet sous le minimum de
5 USDC — la contribution exacte de ces rejets aux fenêtres sans achat n'est pas établie par les
résultats archivés.

**Ce qui reste établi** : les fees Bybit mesurées sur le compte ; les coûts par paire du GATE B en
tant que calibration ; les comptes d'exécutions enregistrées par le simulateur, avec leurs anomalies
documentées (dette 14 : doubles ventes de lots grid × SOL) ; l'identité comptable
`net_pnl == ending − capital` sur les rejeux de référence terminant sans inventaire et sans flux
externes ; la reproductibilité de la sélection vide sous les critères codés (P6 0/24, P7 0/35).

**Ce qui doit être recalculé ou requalifié avant toute utilisation comme preuve de validation
économique** : les mesures affectées par les défauts identifiés (Sharpe/Sortino, MaxDD %, PF) et
toute comparaison les utilisant — dont l'application du seuil 0,4 et les comparaisons aux
benchmarks, la règle de décision elle-même n'étant pas en cause, ni le Sharpe B&H calculé
quotidiennement — ainsi que l'expression « dix fois sous le seuil » (§4.2-4.3) ; le statut de
validation chronologique indépendante du walk-forward ; les interprétations causales par régime ou
par les seuls frais (« les fees Bybit ont tué les stratégies »). Les observations descriptives
(comptes d'exécutions, rendements comptables, lectures trimestrielles) restent citables comme
telles, en tant que sorties du simulateur.

**Corroboration C1** : les comparaisons A/B du chantier C1 sur les rejeux de référence corroborent
les défauts de mesure sans modification des exécutions, soldes ou trajectoires d'equity — le PF du
signal A passe notamment de 1,4420 à 1,3832 après imputation des frais d'achat
(`results/C1_metrics_report.md`). Ces vérifications ne constituent pas un nouveau verdict de
campagne ni une validation après correction du replay et du protocole de sélection.

**Formulation qui remplace le verdict** : zéro configuration sélectionnée sous ce protocole avec cet
instrument. Cela justifie le non-déploiement — aucune stratégie n'est validée pour le déploiement
par cette campagne. Cela n'établit ni que les 212 configurations échoueraient sous un instrument
correct (35 seulement ont vu le walk-forward), ni l'absence d'edge économique des familles testées.

**Suites** : réparation de l'instrument de mesure (chantier C1, mergé, tag `v2.9.0-c1-metrics`),
fidélité du replay (C2), rejeu diagnostic du grid (96 configs BTC/SOL, périmètre pré-spécifié,
verdict « inconclusif » possible), validation chronologique (C3) avant toute sélection. Les runs de
nouvelles familles sont gelés jusqu'au merge de C2 ; les tickets d'entrée sur papier continuent
(`docs/CONTRAINTES_POST_B4.md`).

Le corps du rapport ci-dessous est conservé tel quel comme pièce historique.
```

### 2. `PROJECT_CONTEXT.md`

- **En-tête + §1 (état actuel)** : ajouter après le bloc B4 : audit red-team du 16/09 vérifié et
  consensuel ; instrument de mesure invalidé (métriques + replay + WF non chronologique) ;
  **chantiers en cours** : C1 métriques (`feat/c1-metrics`, plan validé), puis C2 fidélité replay,
  rejeu diagnostic grid (96 configs BTC/SOL), C3 validation chronologique ; **gel des runs R&D**
  jusqu'à C1-C2 mergés, tickets papier autorisés ; prérequis B5 avancés dès maintenant : backup DB
  récurrent (avec test de restauration), découplage `deploy.yml`, test dette 13.
- **Requalifier** toute occurrence du type « aucune stratégie ne survit aux fees Bybit » en :
  « zéro sélection sous les critères codés avec un instrument depuis invalidé (voir addendum B4) ».
  Ne pas toucher au « rien à trader » — il reste vrai.
- **§9 dettes — ajouter** (numérotation à la suite) :
  - **Dette 15** : déjà écrite par C1 (étape 8, mergée dans dev) — vérifier sa présence,
    **ne pas la dupliquer ni la reformuler**.
  - **Dette 16 — Fidélité du replay** : grid backtesté avec indicateurs 4 h nourris de bougies 5 m ;
    EMA200 1d du DCA jamais préenregistrée (boost oversold inopérant en fenêtre trimestrielle) ;
    interaction `bull_reduction × 15 USDC = 4.50 < plancher 5` (achats rejetés en strong_bull) ;
    comptage des rejets absent des résultats. **Résolution : C2**.
  - **Note WF** : la sélection top-5 de P7 phase 2 utilise le Sharpe du test global (période
    chevauchant les fenêtres) — le walk-forward actuel n'est pas une validation chronologique.
    **Résolution : C3**.
- **Ne PAS toucher au §5** (fees/mécanisme) ni créer d'entrées INDEX pour C1 : c'est le périmètre de
  l'étape 8 de C1.

### 3. `ROADMAP.md`

- **Vue d'ensemble** : insérer avant B5 :

| Phase | Quoi | Durée | Livrable / done | Statut |
|---|---|---|---|---|
| **C1** | Métriques fiables (module partagé, dual MaxDD, PF net, equity export, A/B vs tag) | 3-5 j | `results/C1_metrics_report.md`, gold hashes re-baselinés sur tableau A/B approuvé | ▶️ en cours (`feat/c1-metrics`) |
| **C2** | Fidélité replay (grid 4h réels, préenregistrement EMA200 DCA, compteurs de rejets, dette 14 avec review) | 2-4 j | Rapport C2, re-baseline expliqué | 📋 après C1 |
| **Rejeu grid** | Diagnostic pré-spécifié : 96 configs (48 × BTC/SOL) sous instrument réparé, analyse écrite avant lancement, « inconclusif » possible | 1-2 j | Rapport de rejeu ; décision candidat / dépriorisation | 📋 après C2 |
| **C3** | Validation chronologique (sélection sur le passé seul, equity continue, benchmark d'exposition, issue « inconclusif ») | 3-5 j | Protocole v2 documenté + outillé | 📋 avant toute sélection |

- **B5** : conditions de démarrage mises à jour — « un candidat validé sous le protocole C3 » remplace
  « B4 concluant ».
- **Phases terminées** : sur les lignes P6, P7 phase 1 et B4, ajouter la mention « métriques
  invalidées par l'audit du 16/09 (addendum B4) ; verdicts de sélection (vides) inchangés ».
- **Décisions tranchées — ajouter** : 14. Instrument réparé (C1-C2) avant tout run de backtest.
  15. Rejeu grid = diagnostic pré-spécifié, hors quota des 2 familles/cycle mais inscrit au journal
  des essais. 16. Protocole basse rotation (voir CONTRAINTES) : repères de couverture nécessaires
  jamais suffisants, « inconclusif = pas de déploiement ». 17. Tout run de backtest est inscrit à
  `docs/RESEARCH_LOG.md` avant son lancement.
- **Items non bloquants — mettre à jour** : backup DB récurrent → « **maintenant** » (plus « requis
  avant B5 ») + « avec test de restauration » ; ajouter : découplage `deploy.yml` (le workflow active
  et redémarre `krakenbot` puis exige qu'il tourne — à neutraliser tant que le trader est off) ; test
  dette 13 (résolution par instance sur le chemin live/router) ; cron de collecte orderbook élargie
  (bid + ask, plusieurs profondeurs, week-ends et heures US inclus) ; chore cleanup repo post-C1
  (archiver le kraken-era de `results/` vers `results/archive/`, retirer la dépendance `streamlit`
  de `pyproject.toml`, code Kraken conditionné à la dette 7).

### 4. `CLAUDE.md`

- **« Le projet en deux phrases »** : remplacer la fin par : « B4 est close (15 sept, tag
  `v2.8.0-b4-3-campaign`) : zéro sélection sous les critères codés — et l'audit red-team du 16/09 a
  invalidé l'instrument de mesure (addendum B4). Phase courante : chantiers C1 (métriques, en cours)
  → C2 (replay) → rejeu grid → C3 (validation chronologique) ; runs R&D gelés jusqu'à C1-C2, tickets
  papier sous `docs/CONTRAINTES_POST_B4.md`. »
- **Table de routage — ajouter** : « Audit red-team B4 / portée des conclusions →
  `results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` » ; « Briefs de chantier en cours →
  `agent/` » ; « Journal des essais (obligatoire avant tout run) → `docs/RESEARCH_LOG.md` ».

### 5. `docs/CONTRAINTES_POST_B4.md`

- **§2 — corriger la ligne round-trip limit/limit** : le modèle B4 exécuté facture les deux jambes
  maker à 0.10 % chacune **sans** spread/slippage explicite (round-trip 0.20 %) ; les 0.24-0.33 %
  affichés incluaient une hypothèse de friction maker non modélisée. Réécrire : séparer « fees
  débitées par le moteur » (0.20 % limit/limit, 0.35 % limit/market + frictions mesurées) de
  « frictions non reproduites par le modèle : la file d'attente, les non-exécutions, les
  remplissages partiels et la sélection adverse ne sont pas reproduits par le remplissage complet
  au toucher ; leur effet sur ces stratégies et son amplitude ne sont pas quantifiés par B4
  (audit §7-8) ». Préciser que les totaux nominaux maker/taker (BTC 0,39 % / ETH 0,40 % /
  SOL 0,48 %) sont des sommes de taux et paramètres de calibration, pas un coût réel constant
  garanti par transaction. Les chiffres limit/market restent inchangés.
- **Nouvelle section — Protocole basse rotation** : repères de couverture (~25-30 round-trips sur
  l'ensemble de la période OU ~3 ans d'equity quotidienne avec exposition non triviale) =
  **filtres internes de couverture retenus par le projet, non seuils statistiques universels** :
  leur franchissement ne suffit pas à valider une stratégie ; en dessous, le projet ne prononce
  pas d'acceptation pour déploiement — verdict « inconclusif », et **inconclusif = pas de
  déploiement** ; au-dessus, l'acceptation exige un effet
  économique minimum, un benchmark d'exposition (B&H/cash à budget de risque et coûts comparables)
  et une borne d'incertitude **écrits dans le ticket avant les résultats** ; les simulations
  trimestrielles réinitialisées ne suffisent pas à valider un comportement destiné à porter ses
  positions continûment entre les trimestres (le grid paie une liquidation lorsqu'un inventaire
  reste ouvert en fin de segment ; le moteur signal ne transmet pas sa position au segment
  suivant) — la validation relève du
  protocole C3 (equity continue, sélection chronologique, bootstrap par blocs). Un mécanisme
  économique plausible soutient l'hypothèse ; il ne remplace pas la validation empirique.
- **Nouvelle mention en tête de §6 (ticket d'entrée)** : « ⚠️ Gel des runs : aucun backtest de
  nouvelle famille avant le merge de C1-C2 — le pipeline actuel est déclaré non fiable pour juger un
  ticket. Les tickets sur papier continuent ; cap de 2 familles par cycle inchangé. »

- **§1 — aligner sur l'état post-audit** : supprimer ou requalifier la mention « moteur
  certifié » (l'instrument de mesure a été invalidé par l'audit puis corrigé en C1 ; le replay
  reste à corriger en C2) et la comparaison 0,04 / 0,84 présentée comme verdict — remplacer par
  un renvoi à l'addendum B4, **sans planter de nouveau chiffre de Sharpe** : aucune comparaison
  chiffrée n'est reprise tant que le rejeu sous instrument réparé n'a pas eu lieu.

### 6. `results/INDEX.md`

- Ajouter l'entrée `red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md` (audit adversarial, verdicts).
- Sur les entrées B4 (rapport, checkpoints, sélection) : flag « métriques invalidées — voir addendum
  du rapport B4 ». Ne pas créer d'entrées pour les artefacts C1 (étape 8 de C1).

### 7. `docs/RESEARCH_LOG.md` — créer

Journal **append-only** de tous les essais de recherche. En-tête expliquant la règle : toute
campagne ou run exploratoire est inscrit **avant lancement** ; les modifications guidées par des
résultats sont de nouveaux essais tracés ; rien n'est supprimé.

Format par entrée : `date | phase/campagne | famille + périmètre (configs × paires) | données +
période | version code (tag/commit) + version métriques | modèle de fees | verdict | décision
consécutive | source (rapport)`.

Reconstruction rétroactive (dates depuis les rapports sources ; granularité campagne, le détail
par config vit dans les JSON référencés) :
1. P6 — 24 combos (8 stratégies × 3 paires), données Binance, fees binance 0.075 % flat,
   `v2.0.0-p6-validated`, métriques v1 (invalidées D1-D6) → 0/24 → grid search P7.
2. P7 phase 1 — 212 configs cross-validées (4 stratégies), fees binance flat, mai 2026, métriques
   v1 → classements non transposables → re-run B4.
3. B4 P6 re-run — 24 combos, fees bybit + coûts GATE B, `v2.8.0-b4-3-campaign`, métriques v1 →
   0 survivant.
4. B4 P7 phases 1-2 — 212 configs + 35 × 8 fenêtres WF, fees bybit, métriques v1 → 0/35, sélection
   vide ; 48/48 grid × SOL flaggées (dette 14).
5. B4 benchmarks — B&H + DCA fixed, métriques v1 (DCA contaminé D6).
6. Ligne unique : « campagnes kraken-era antérieures — non reconstruites au détail, voir
   `docs/archive/` ».

## Interdits

- Aucun fichier code, aucun test, aucun JSON de résultats.
- Ne pas toucher : `skills/backtest.md`, §5 de `PROJECT_CONTEXT.md`, entrées INDEX des artefacts C1,
  `agent/chantier1_metriques.md`, corps du rapport B4 (addendum seulement), fichiers de
  `results/red_team_b4_20260916/`.
- Ne pas reformuler les blocs normatifs de ce brief ; signaler toute incohérence rencontrée au lieu
  de la résoudre soi-même.

## Critère de fin (done)

- [ ] Addendum inséré verbatim en tête du rapport B4, corps intact
- [ ] PROJECT_CONTEXT : état actuel, requalifications, dettes 15-16 + note WF ; §5 intact
- [ ] ROADMAP : table C1/C2/rejeu/C3, B5 reconditionné, flags phases terminées, décisions 14-17,
      items mis à jour
- [ ] CLAUDE.md : résumé + 3 lignes de routage
- [ ] CONTRAINTES : §1 aligné (sans nouveau chiffre), §2 corrigé, protocole basse rotation, gel des runs en tête du ticket d'entrée
- [ ] INDEX : entrée red-team + flags B4
- [ ] RESEARCH_LOG créé avec les 6 entrées rétroactives
- [ ] Aucun diff hors de la liste ; cohérence croisée des renvois (chemins de fichiers valides)

## Commits attendus

- `docs(b4): addendum scoping conclusions after red-team audit`
- `docs(context): post-audit status, debts 15-16, C1-C3 pipeline`
- `docs(roadmap+claude): C1-C3 phases, updated decisions and items, routing`
- `docs(contraintes): fee-model coherence, low-rotation protocol, run freeze`
- `docs(research-log): create append-only trial journal with retroactive entries`

---

## Amendements du 16/09 (post-runbook ops — prévalent sur le corps du brief en cas de divergence)

**A. Section 2 (PROJECT_CONTEXT, état actuel)** — les prérequis B5 ne sont plus « à avancer » mais :
backup DB récurrent **fait et testé** le 16/09 (cron 04:15 daily / 04:45 weekly, restore prouvé sur
container jetable) ; `deploy.yml` **découplé** du trader (16/09, marqueurs `# B5: re-enable trader`) ;
**trader masqué** sur le serveur (`systemctl mask`, 16/09) ; reste ouvert : test dette 13.

**B. Section 3 (ROADMAP, items)** — marquer faits : backup récurrent + test de restauration
[x 16/09] ; découplage `deploy.yml` [x 16/09] ; cron orderbook élargi [x 16/09 — horaire, bid + ask,
2 profondeurs, 24/7]. Restent ouverts : test dette 13 ; chore cleanup post-C1 (y ajouter : trier les
3 stashes git anciens ; aligner `scripts/restore_db.sh` sur `skills/database.md`).

**C. Section 4 (CLAUDE.md, conventions git)** — ajouter trois règles :
1. Pendant qu'un chantier agent est actif, toute intervention humaine passe par un worktree séparé
   (`git worktree add ~/wt-human dev`) — jamais de checkout/commit humain dans le tree d'un agent.
2. Tout agent : assert `git branch --show-current == <branche du chantier>` avant chaque commit.
3. Un bloc GO contenant des écritures git part vers exactement une session, nommée.

**D. Fichier ajouté au périmètre : `skills/database.md` (section restore)** — exiger la version
d'extension TimescaleDB **exacte** (test du 16/09 : « même version majeure » insuffisant, catalogue
interne incompatible → COPY en échec) ; image épinglée `timescale/timescaledb:<version>-pg16` ; les
rôles ne sont pas dans le dump → `CREATE ROLE claude_readonly;` avant restore ou `pg_restore
--no-acl` (sinon ~126 erreurs GRANT cosmétiques) ; noter que `scripts/restore_db.sh` n'applique pas
`timescaledb_pre_restore()/post_restore()` (alignement au chore cleanup). Consigner : « restore
testé le 16/09/2026, dump daily 13:42, counts binance 8 712 718 / kraken 1 181 469 / bybit
2 572 097, MAX(bybit) = heure du dump ».

**E. Done et décompte** — le périmètre devient **7 fichiers modifiés, 1 créé** ; ajouter au done :
[ ] `skills/database.md` (D) ; [ ] conventions git dans CLAUDE.md (C).

**F. Coordination C1** — le chore peut tourner avant ou après le merge de `feat/c1-metrics` ; dans
tous les cas, les sections réservées C1 (Interdits du brief : `skills/backtest.md`, §5
PROJECT_CONTEXT, lignes dette 15, entrées INDEX des artefacts C1) restent hors périmètre.

**G. Statuts au moment de l'exécution (le chore tourne APRÈS le merge C1)** — remplacer partout les
statuts « en cours » de C1 par l'état réel constaté au lancement : C1 **✅ mergé dans `dev`**
(12 commits, tag `v2.9.0-c1-metrics`, `results/C1_metrics_report.md`) ; ligne C1 de la table
ROADMAP (section 3) → statut ✅ avec le tag ; section 2 (PROJECT_CONTEXT) → « C1 mergé, C2 = prochain
chantier » ; phrase de contexte du brief (« Ce chore met la documentation en cohérence avant que C1
n'atteigne sa propre étape docs ») caduque — C1 a fait son étape 8, ses sections restent interdites.
**Seule dérogation au verbatim de l'addendum (section 1)** : dans le paragraphe « Suites », ajuster
le statut de C1 — « (chantier C1, mergé, tag `v2.9.0-c1-metrics`) » au lieu de « en cours » — sans
toucher un seul autre mot. Le gel des runs reste formulé « jusqu'au merge de C1-C2 » (C2 restant).
Vérifier ces statuts contre `git log`/tags réels au lancement, pas contre ce brief.

**H. Revue Astra du 16/09 intégrée** — la section 1 (addendum v2 : DCA scindé fait/attribution,
« invalidé » → « à recalculer/requalifier », comptes d'exécutions qualifiés, identité comptable
conditionnée, paragraphe Corroboration C1, « aucune stratégie validée pour le déploiement ») et la
section 5 (frictions maker reformulées, totaux 0,39/0,40/0,48 = calibration, filtres internes,
fenêtres trimestrielles reformulées, alignement §1) sont la version normative finale.
