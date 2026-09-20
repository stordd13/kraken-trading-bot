# AGENT B4.1 — Audit conventions de timestamp + re-stamp des données Binance

> Ouverture de B4. Prérequis de **validité** : tant que ce brief n'est pas clôturé, aucun
> re-run de backtest n'a de sens (look-ahead multi-TF prouvé dans P6/P7).
> Mode : **plan mode** — proposer le plan complet (dont la mécanique de migration) avant
> tout code. Trois gates STOP humains. Ne jamais franchir un gate sans GO explicite.

---

## 0. À lire avant tout (dans cet ordre)

1. `CLAUDE.md` (routeur + règles d'or)
2. `PROJECT_CONTEXT.md` — § 6 (DB), § 9 dettes **11** et **12**
3. `results/B3_bybit_data_report.md` — § 6 (constat sourcé), § (b) contrôle prix 1h (méthode de
   comparaison décalée déjà validée), § 5 (contrôles 1d/1w)
4. `skills/database.md` (tunnel, migrations lourdes, backup/restore TimescaleDB)
5. `skills/deployment.md` (SSH serveur, systemd, tmux)
6. `skills/binance_import.md`
7. `docs/CODE_MAP.md` (repérage)

Code à lire (**lecture seule**, aucun de ces fichiers ne doit être modifié) :
- `scripts/binance_vision_import.py:104-155` — stamp = `row[0]` = **open time**
- `src/krakenbot/connectors/binance/ws.py:421-424` — stamp WS = `k["T"] + 1` = **fin de période**
- `src/krakenbot/models/market_data.py` — PK `(timestamp, pair, interval, exchange)`, `interval` en minutes
- `scripts/backtest.py:354` (`_build_replay_sequence`) — tri chronologique, TF haut d'abord sur
  égalité de timestamp : toute la sémantique du replay suppose des **end-stamps**

## 1. Contexte (résumé — le détail est dans les docs ci-dessus)

- **Standard DB du projet** : `timestamp` = fin de période (`start + interval` ; Bybit `end + 1 ms`).
  Les rows WS (Binance et Bybit) et l'import B3 le respectent.
- **Dette 11** : les rows Binance issues de l'import Vision sont **open-stamped**. Preuve en DB :
  BTC 1d `2024-01-01` open 42274.27 / close 44185.08 (= candle du 1ᵉʳ janvier stampée à l'open) ;
  1m Vision : `MAX(timestamp) = 2026-03-31 23:59`.
- **Fenêtre avril–juin 2026** : contient des rows Binance écrites par le WS de l'époque, déjà
  **end-stamped**. La frontière Vision/WS n'est **pas la même par pair × TF** et n'est pas connue
  précisément. Des collisions PK silencieuses (`ON CONFLICT DO NOTHING`) ont pu se produire.
- **Volumes** (2026-09-11) : `binance` 8 712 718 rows · `kraken` 1 181 469 (**ne pas toucher**) ·
  `bybit` 2 543 347 + WS en continu (**ne pas toucher**).
- **Référence de classification** : recouvrement Bybit/Binance — BTC dès `2025-06-11`, ETH/SOL dès
  `2025-06-27` ; corrélation des closes 1h ≥ 0.99998 (rapport B3).
- **Décision actée (hypothèse de travail, confirmée au GATE 1 avec les chiffres)** : re-stamp des
  rows open-stamped (`timestamp := timestamp + interval minutes`), policy collisions **« WS fait
  foi »** (les rows end-stamped existantes gagnent, les rows Vision en collision sont supprimées
  et comptabilisées).

## 2. Objectif

Rendre **100 % des rows `exchange='binance'` end-stamped**, avec preuve par invariants, sans
toucher aux rows `bybit`/`kraken`, afin que B4.2 (fees) et B4.3 (re-runs P6/P7) travaillent sur
des données sans look-ahead.

## 3. Hors scope — STRICT

- Aucune modification de `scripts/backtest.py`, des fees, des stratégies, ni des fichiers
  protégés (`MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine`).
- Aucune écriture sur `exchange != 'binance'`.
- Pas de fix des 4 tests ordre-dépendants connus (scope B4.2), pas de re-run P6/P7 (B4.3) —
  un **seul** backtest de référence, comme invariant (§ 6.6).
- Dette 12 (backfill générique non-Bybit) : rien de plus que l'existant.
- Toute tâche annexe découverte en route : la **consigner dans le rapport**, ne pas la faire.

## 4. Étape 1 — Audit et classification (READ-ONLY)

Scripts read-only dans `scripts/audit/` (préfixe `b4_`). Lectures DB via tunnel autorisées.
Livrable : section « Audit » de `results/B4_1_timestamp_restamp_report.md`.

a) **Cartographie** des 21 séries (3 paires × 7 TF) : `MIN`/`MAX(timestamp)`, counts, trous
   internes (LAG), pour `exchange='binance'`.

b) **Classification open/end par contenu** :
   - Sur le recouvrement Bybit : pour chaque série, corrélation des closes
     `binance(T) vs bybit(T)` (hypothèse end) contre `binance(T) vs bybit(T + interval)`
     (hypothèse open), par fenêtre glissante (p. ex. hebdomadaire). La bascule de l'hypothèse
     gagnante localise la **frontière**. Méthode déjà validée au 1h en B3 (§ b du rapport).
   - Avant le recouvrement (2021 → 2025-06) : pas de référence Bybit. Ne **pas** s'appuyer sur
     la continuité `close(N) == open(N+1)` (vraie sous les deux conventions). S'appuyer sur la
     provenance (tout est Vision avant avril 2026 → open-stamped) + spot-checks documentés
     (BTC 1d 2024-01-01) + cohérence du raccord à la frontière trouvée en aval.
   - **Signature de doublon** : rows consécutives `(T, T + interval)` à OHLCV identiques =
     même candle physique présente deux fois (Vision + WS) → délimite la zone de chevauchement.

c) **Quantification pour la migration**, par série : rows à re-stamper, collisions PK
   post-re-stamp (cible `T + interval` déjà occupée), et pour chaque collision : contenu
   identique ou divergent. Si divergent → lister, décision au gate.

d) **Frontières exactes** : timestamp de la dernière row open-stamped par série, exportées dans
   un **fichier JSON versionné** (source de vérité du périmètre de migration — pas de valeurs
   approximatives en dur dans le script).

e) **Bord amont du WS** : vérifier à la frontière qu'aucune row open-stamped n'a été bloquée ou
   masquée par `ON CONFLICT` d'une manière qui laisserait un contenu incohérent au raccord.

### ⛔ GATE 1 — STOP
Présenter le rapport d'audit. **Aucune écriture DB avant ce point ni sans le GO.** Bruno tranche :
re-stamp GO/NO-GO, policy collisions confirmée, périmètre exact par série validé.

## 5. Étape 2 — Migration re-stamp (SERVEUR UNIQUEMENT)

Script de migration (emplacement proposé au plan, p. ex. `scripts/audit/b4_restamp_binance.py`) :
- Modes `--dry-run` (défaut) et `--execute`. Périmètre piloté par le JSON de frontières (§ 4d).
- `WHERE exchange='binance'` **et** périmètre de frontières sur chaque requête d'écriture.
- Batchs 1000–5000 rows, transaction par batch, reprise possible.
- Collisions : « WS fait foi » → row Vision supprimée, comptée.

**Mécanique à proposer au plan** — contrainte TimescaleDB : modifier `timestamp` déplace les rows
entre chunks (mensuels). Options attendues au plan : UPDATE batché par mois/chunk vs
`INSERT … SELECT` + `DELETE` par mois ; réglage `maintenance_work_mem` ; estimation de durée.
Choisir la plus simple qui tient sur le CX33 (4 vCPU, 8 GB + swap 2 GB).

**Protocole serveur (non négociable, `skills/database.md`)** :
1. Backup **frais** `pg_dump -Fc` avant toute écriture (celui du 7 sept est antérieur à l'import
   Bybit — il ne compte pas). Vérifier taille et horodatage.
2. `sudo systemctl stop krakenbot-collector`. Le trou Bybit créé pendant l'arrêt sera réparé par
   le backfill nocturne — c'est vérifié à l'étape 3.
3. Exécution **sur le serveur** (session tmux), jamais via le tunnel SSH.
4. `--dry-run` d'abord : counts par série (re-stamps, collisions, suppressions) qui doivent
   **matcher exactement** les chiffres de l'audit. Tout écart = STOP + remontée.

### ⛔ GATE 2 — STOP
Présenter la sortie du dry-run + preuve du backup frais. **`--execute` uniquement après le GO.**

Après `--execute` : relancer le collector (`systemctl start` + statut `active (running)` + logs WS
propres), consigner l'heure d'arrêt/reprise dans le rapport.

## 6. Étape 3 — Invariants post-migration (tous obligatoires)

1. **Zéro résidu open-stamped** : re-jouer la classification (§ 4b) sur tout le recouvrement →
   l'hypothèse end gagne 100 % des fenêtres, pour les 21 séries.
2. **Comptabilité exacte** : `rows_after == rows_before − collisions_supprimées`, par série et au
   total. Aucune autre perte.
3. **Grille continue** : aucun trou introduit, aucun doublon logique `(T, T+interval)` résiduel.
4. **Spot-checks** : la candle BTC 1d du 1ᵉʳ janvier 2024 est désormais stampée
   `2024-01-02 00:00` (open 42274.27 / close 44185.08) ; les 1w Binance end-stamped tombent le
   lundi 00:00 et le décalage d'un intervalle vs Bybit observé en B3 (§ 5) a **disparu** (mêmes
   candles, mêmes stamps sur le recouvrement).
5. **Bornes** : `MAX(timestamp)` 1m Binance = frontière auditée + 1 minute (attendu
   `2026-04-01 00:00` si la frontière 1m est bien la fin Vision).
6. **Backtest de référence** :
   `poetry run python scripts/backtest.py --strategy grok_supertrend_4h --pair BTC/USDC --exchange binance --days 1095 --capital 1000`
   Les métriques **doivent différer** du baseline P6 (`results/P6_backtest_report_v2.md`) — des
   résultats identiques signifient que le re-stamp n'a pas eu l'effet attendu : **red flag, STOP,
   investiguer**. Consigner le delta brut (chiffres, sans analyse — l'analyse est B4.3).
7. **Lendemain** (vérification Bruno, hors agent) : run `gap_backfill` de 03:30 UTC vert, trou
   Bybit de la fenêtre de migration comblé (`task_execution_logs`).

### ⛔ GATE 3 — STOP
Rapport final complet → validation humaine. Merge/tag = workflow de clôture de phase, **hors de
ce brief** (review → merge `dev` → push vérifié → serveur → observation → tag).

## 7. Docs à mettre à jour (même branche, après GATE 3 donné)

- `PROJECT_CONTEXT.md` : dette 11 → résolue (renvoi au rapport) ; § 6 volumes et convention
  (« binance end-stamped depuis B4.1 ») ; note sur les counts mis à jour.
- `skills/database.md` + `skills/binance_import.md` : la convention Binance en DB devient
  end-stamped ; les mentions open-stamped passent en note historique.
- `src/krakenbot/models/market_data.py` : le commentaire de colonne
  `comment="Candle open timestamp (UTC)"` est faux — corriger vers la convention réelle
  (fin de période). Modèle + éventuel `COMMENT ON COLUMN` léger, à proposer au plan ;
  **pas** de migration Alembic lourde pour ça.
- `docs/CODE_MAP.md` : uniquement si du code `src/` change (a priori seulement le commentaire).

## 8. Tests et qualité

- Logique pure (classification, calcul de frontières, génération de batchs) → tests unitaires
  locaux.
- Tests touchant la DB : **sur le serveur**, Python 3.12, jamais via tunnel.
- `poetry run pytest -q` et `ruff check` verts avant chaque commit. Les 4 échecs
  ordre-dépendants connus (B3, § résumé exécutif) sont attendus en run complet : ne pas y
  toucher, ne pas en introduire de nouveaux.

## 9. Livrables (critère de fin)

1. `results/B4_1_timestamp_restamp_report.md` — audit, décisions de gate, dry-run, exécution,
   invariants 1–6 verts, heures d'arrêt/reprise du collector.
2. Scripts `scripts/audit/b4_*.py` (classification read-only) + script de migration
   `--dry-run`/`--execute`.
3. JSON de frontières versionné.
4. Docs § 7 à jour.
5. DB serveur : rows `binance` 100 % end-stamped, collector relancé et sain.

## 10. Commits attendus (atomiques, branche `feat/b4-1-binance-restamp` depuis `dev`)

- `feat(audit): b4 timestamp classification and boundary detection`
- `feat(scripts): binance restamp migration with dry-run and boundary manifest`
- `fix(models): correct market_data_ohlc timestamp column comment`
- `docs(project): resolve debt 11, unify end-stamp convention`

PR vers `dev` uniquement, après GATE 3. **Jamais de push sur `main`** (`deploy.yml` redémarre le
trader). Jamais de commit de `.env`/credentials.

## 11. Garde-fous absolus

- Aucune écriture DB avant le GO du GATE 2 ; aucune écriture hors
  `exchange='binance'` + périmètre de frontières.
- `bybit` et `kraken` : intouchables. `backtest.py` : lecture seule dans ce brief.
- Écart entre audit et dry-run, collision à contenu divergent, invariant qui échoue,
  comportement inattendu de TimescaleDB : **STOP et remonter**, ne pas improviser.
- « Fini » ≠ mergé ≠ sur origin ≠ déployé : chaque étape est vérifiée explicitement.
