# B4.1 — Audit des conventions de timestamp et re-stamp des données Binance

> Généré le 2026-09-13, branche `feat/b4-1-binance-restamp` (base `dev` @ `08e8e1f`, tag de départ
> `v2.5.0-b3-bybit-data`). Spec : `agent/AGENT_B4_1_TIMESTAMP_AUDIT_RESTAMP.md`. Plan validé par Bruno le
> 2026-09-13 (plan mode). Collector Bybit **actif** pendant l'audit (lecture seule, via tunnel).
>
> État : **GATE 1 donné (GO, 2026-09-13) → backup frais, collector arrêté, dry-run serveur MATCH →
> ⛔ GATE 2 en attente du GO `--execute`.** Aucune écriture DB n'a eu lieu à ce stade (lectures seules,
> `EXPLAIN`, tables temporaires de session). **Le collector `krakenbot-collector` est arrêté depuis
> 2026-09-13 17:46:59 UTC** (séquence GATE 2 de Bruno) ; le trou Bybit grandit jusqu'à la reprise
> (backfill nocturne : fenêtre de 3 jours).

## Résumé exécutif

- **Les 8 712 718 rows `exchange='binance'` sont open-stamped, sans exception** : sur les 21 séries
  (3 paires × 7 TF), l'hypothèse *open* gagne 100 % des fenêtres hebdomadaires décisives du recouvrement
  Bybit (juin 2025 → mars 2026), la majorité par row est *open* partout, aucune bascule open→end.
- **La fenêtre avril–juin 2026 n'existe pas en DB** : `MAX(timestamp)` des 21 séries = `2026-03-31`
  (fin de l'import Vision, `--end-date 2026-04-01`). Les rows WS Binance de l'époque ont été écrites sous
  `exchange='kraken'` (`XBT/USDC`, jusqu'au `2026-05-30`, cf. § 2.e) — hors périmètre, non touchées.
  La prémisse « rows WS end-stamped mélangées » du brief et de la dette 11 est donc **fausse en DB** ; le
  périmètre de migration est **100 % des rows binance** et le nombre de **collisions PK attendu est 0**.
- **Frontières** exportées dans `results/b4_binance_stamp_boundaries.json` (source de vérité du périmètre :
  `last_open_stamped_ts` = `MAX(timestamp)` de chaque série, `expected_restamps` = `rows`, `expected_collisions` = 0).
- **Mécanique de migration** (script prêt, `scripts/audit/b4_restamp_binance.py`) : staging par fenêtre
  ≤ 4 000 rows en ordre **décroissant**, une transaction par fenêtre (`CREATE TEMP TABLE … / DELETE / INSERT …
  ON CONFLICT DO NOTHING`), ledger JSONL pour la reprise. Un `UPDATE timestamp = timestamp + interval` direct
  est impossible : la PK `(timestamp, pair, interval, exchange)` n'est pas déferrable (violation transitoire).
- **Dry-run via tunnel (lecture seule, 2026-09-13 16:27–16:35 UTC)** : 2 550 fenêtres, `staged=8 712 718`,
  `collisions=0`, **MATCH exact** avec le manifeste sur les 21 séries (`results/b4_restamp_dryrun_tunnel.txt`).
  Le dry-run **serveur** exigé par le brief (§ 5.4) sera rejoué après GATE 1, avant GATE 2.
- Tests : `pytest -q --ignore=tests/test_scripts/test_run_p6_determinism.py` → **1170 passés, 6 skipped,
  4 échecs** = exactement les 4 ordre-dépendants connus (B3, § résumé), 30 nouveaux tests verts ;
  `ruff check` propre (`ruff format --check` : 3 fichiers pré-existants hors scope, dette 10).

## 1. Décisions (plan validé) et faits DB qui les fondent

| # | Décision | Pourquoi |
|---|---|---|
| 1 | Re-stamp `timestamp := timestamp + interval` des rows binance, policy collisions « WS fait foi » | brief § 1 ; audit : 0 collision attendue |
| 2 | Périmètre piloté par le JSON de frontières, jamais de date en dur | brief § 4d ; `last_open_stamped_ts` par série |
| 3 | Mécanique **staging par fenêtre, ordre décroissant**, ≤ 4 000 rows / transaction | PK non déferrable → `UPDATE` batché échoue ; `INSERT…SELECT + DELETE` par mois en ordre croissant collisionne avec le mois suivant encore en place ; l'ordre décroissant libère la cible avant usage ; chunks TimescaleDB de **30 jours** (112 chunks, pas de compression) traversés par l'INSERT |
| 4 | Pas de réglage `maintenance_work_mem` ; `VACUUM ANALYZE` (jamais `FULL`) après exécution | ≤ 4 000 rows par tx ; bloat temporaire réclamé par autovacuum |
| 5 | Classification par **vote par row** (close Bybit le plus proche : `T` = end, `T+i` = open), agrégé par semaine ISO ; frontière = dernière row *open* ; fenêtres < 3 rows non décisives | méthode B3 § 5(b) généralisée aux 7 TF ; au 1w chaque fenêtre = 1 row et bascule sur l'écart inter-exchange quand deux closes hebdo consécutifs sont quasi égaux (3 cas, § 2.b) |
| 6 | Signature de doublon `(T, T+i)` OHLCV identiques **avec `volume > 0`**, datée | les candles plates (`volume = 0`, 2021–2022) donnent des dizaines de milliers de faux positifs au 1m |
| 7 | Commentaire de colonne `timestamp` : modèle + **mini-révision Alembic** `b4c0ffee0001` (`COMMENT ON COLUMN` seul) | validé par Bruno ; aucun commentaire de colonne n'existe en DB aujourd'hui (`col_description` NULL) |
| 8 | Refus d'`--execute` via le tunnel (port 5433) et sans `--i-have-a-fresh-backup` | brief § 5, § 11 |
| 9 | **GATE 1 (Bruno, 2026-09-13)** : re-stamp GO ; policy « WS fait foi » confirmée, le chemin `ON CONFLICT` reste mais **toute collision non prévue par l'audit = mismatch → STOP** (fenêtre annulée) ; périmètre 100 % des rows binance validé | décisions 1–3 du GATE 1 |
| 10 | Invariant § 6.1 durci (GATE 1 a) : post-migration, **chaque** fenêtre vote *end* (mode strict, une seule fenêtre *open* résiduelle = STOP) et les rows ambiguës pré-migration sont revérifiées une à une à `T + interval` | `assess_votes(strict=True)`, `unexpected_rows` du manifeste |
| 11 | Scope ajouté (GATE 1 b) : `scripts/binance_vision_import.py` écrit désormais `open_time + interval` (+ tests dédiés), commit `fix(scripts)` séparé | un ré-import ne réintroduira plus d'open-stamps |
| 12 | Invariant ajouté (GATE 1 c) : la dernière candle 1w de chaque paire est une **semaine complète** (open = 1ᵉʳ 1d open même source ; close/high/low vs les 7 jours 1d Bybit, tolérance 50 bps ; signature de troncature = close égal au dernier 1d Binance) | § 2.g |
| 13 | **Vote hybride** : le close tranche, sauf si les deux closes Bybit candidats sont à < 0,1 % l'un de l'autre (ambigu) → distance OHLC complète. Remplace le vote « close seul » | la distance OHLC seule bascule sur les premières semaines Bybit EU (marché illiquide, SOL 2025-06-30) ; le close seul bascule sur deux closes hebdo quasi égaux (3 cas) ; l'hybride donne 0 fenêtre ambiguë sur les 21 séries |
| 14 | **Reprise atomique** (revue adversariale, § 2.h) : progression enregistrée **dans la transaction de chaque fenêtre** (table `b4_restamp_progress`, PK fenêtre + identité du plan : `max_rows`, frontière, stamp du manifeste), ledger JSONL = miroir. Pré-vol par série avant toute écriture : fenêtres faites = préfixe du plan, même identité, et `COUNT` des originales restantes = `expected_restamps − déjà stagées`. Garde in-transaction : slot `w_end` libre, `deleted == staged`, collisions ≤ autorisées | sans cela, une reprise après crash entre COMMIT et écriture du ledger (ou avec un autre `--max-rows-per-tx`) redécalait des rows déjà décalées |
| 15 | Table `b4_restamp_progress` = **seule écriture hors `exchange='binance'`** (table auxiliaire, 2 550 rows, à supprimer à la clôture) — dérogation à soumettre au GATE 2 | brief § 11 |

Faits DB (lecture seule, 2026-09-13) : TimescaleDB 2.24.0 / PostgreSQL 16.11, hypertable 3 002 MB,
`chunk_time_interval = 30 days`, compression désactivée, `max_locks_per_transaction = 512`,
`maintenance_work_mem ≈ 478 MB`, `alembic_version = f7a8b9c0d1e2`. Volumes : binance 8 712 718 ·
kraken 1 181 469 · bybit 2 556 036 (en croissance WS).

## 2. Audit (étape 1, read-only) — `scripts/audit/b4_timestamp_audit.py`

Sortie brute complète : `results/b4_timestamp_audit_pre_migration.txt` (run `generated_at=2026-09-13T16:26:52Z`,
exit code 0, « all series consistent with 'open' convention — no problem »). Reproduire :

```bash
poetry run python scripts/audit/b4_timestamp_audit.py \
    --out-json results/b4_binance_stamp_boundaries.json --out-md /tmp/b4_audit.md
```

### 2.a Cartographie des 21 séries

```
  Series              rows min                        boundary (last open ts)     restamps collisions  win open/end/tie
  BTC/USDC 1m      2521597 2021-01-01T00:00:00+00:00  2026-03-31T23:59:00+00:00    2521597          0    40/0/0
  BTC/USDC 5m       504321 2021-01-01T00:00:00+00:00  2026-03-31T23:55:00+00:00     504321          0    40/0/0
  BTC/USDC 15m      168108 2021-01-01T00:00:00+00:00  2026-03-31T23:45:00+00:00     168108          0    40/0/0
  BTC/USDC 1h        42031 2021-01-01T00:00:00+00:00  2026-03-31T23:00:00+00:00      42031          0    40/0/0
  BTC/USDC 4h        10512 2021-01-01T00:00:00+00:00  2026-03-31T20:00:00+00:00      10512          0    40/0/0
  BTC/USDC 1d         1753 2021-01-01T00:00:00+00:00  2026-03-31T00:00:00+00:00       1753          0    40/0/0
  BTC/USDC 1w          246 2021-01-04T00:00:00+00:00  2026-03-30T00:00:00+00:00        246          0    37/2/0
  ETH/USDC 1m      2521597 2021-01-01T00:00:00+00:00  2026-03-31T23:59:00+00:00    2521597          0    40/0/0
  ETH/USDC 5m       504321 2021-01-01T00:00:00+00:00  2026-03-31T23:55:00+00:00     504321          0    40/0/0
  ETH/USDC 15m      168108 2021-01-01T00:00:00+00:00  2026-03-31T23:45:00+00:00     168108          0    40/0/0
  ETH/USDC 1h        42031 2021-01-01T00:00:00+00:00  2026-03-31T23:00:00+00:00      42031          0    40/0/0
  ETH/USDC 4h        10512 2021-01-01T00:00:00+00:00  2026-03-31T20:00:00+00:00      10512          0    40/0/0
  ETH/USDC 1d         1753 2021-01-01T00:00:00+00:00  2026-03-31T00:00:00+00:00       1753          0    40/0/0
  ETH/USDC 1w          246 2021-01-04T00:00:00+00:00  2026-03-30T00:00:00+00:00        246          0    39/1/0
  SOL/USDC 1m      1719780 2021-09-24T10:00:00+00:00  2026-03-31T23:59:00+00:00    1719780          0    40/0/0
  SOL/USDC 5m       343956 2021-09-24T10:00:00+00:00  2026-03-31T23:55:00+00:00     343956          0    40/0/0
  SOL/USDC 15m      114652 2021-09-24T10:00:00+00:00  2026-03-31T23:45:00+00:00     114652          0    40/0/0
  SOL/USDC 1h        28663 2021-09-24T10:00:00+00:00  2026-03-31T23:00:00+00:00      28663          0    40/0/0
  SOL/USDC 4h         7167 2021-09-24T08:00:00+00:00  2026-03-31T20:00:00+00:00       7167          0    40/0/0
  SOL/USDC 1d         1196 2021-09-24T00:00:00+00:00  2026-03-31T00:00:00+00:00       1196          0    40/0/0
  SOL/USDC 1w          168 2021-09-20T00:00:00+00:00  2026-03-30T00:00:00+00:00        168          0    40/0/0
  total rows=8712718 restamps=8712718 collisions=0 series=21
```
(`win open/end/tie` = fenêtres hebdomadaires du recouvrement Bybit ; `boundary` = `last_open_stamped_ts`.)

- Alignement grille : **0 row désalignée** sur les 21 séries (grille 1w ancrée lundi, `MIN`/`MAX` alignés).
- Trous internes (LAG), identiques sur les 4 TF ≤ 1h de BTC et ETH (8 trous) : 6 micro-trous Binance en 2021
  (79 à 284 min), un trou de **164 jours `2022-09-29 03:00 → 2023-03-12 06:30`** (BTC, ETH ; SOL : 455 jours,
  `2022-09-29 → 2023-12-28`) = retrait des paires USDC par Binance (conversion BUSD, sept. 2022) — **trou de
  marché, pas un défaut d'import** ; 1 micro-trou le 2023-03-24. 1w : 6 trous d'une semaine (2022, 2025) +
  le trou de 2022–2023. Ces trous sont conservés tels quels ; l'invariant post-migration est « même liste,
  décalée de +interval ».

### 2.b Classification open/end par contenu (vote hybride, décision 13)

- Recouvrement Bybit : BTC dès `2025-06-11 09:21`, ETH/SOL dès `2025-06-27` ; 40 semaines votées par série
  (1m : ~437 k rows votées par paire).
- **Open gagne 100 % des fenêtres des 21 séries ; majorité par row *open* partout ; 0 fenêtre ambiguë.**
  Avec le vote « close seul » (première version de l'audit, run 16:26 UTC), trois fenêtres 1w d'une seule row
  votaient *end* — closes hebdo consécutifs quasi égaux, l'écart inter-exchange tranchait ; le vote hybride les
  classe *open* franchement (distance OHLC) et elles restent listées dans le manifeste (`unexpected_rows`) pour
  la revérification post-migration exigée au GATE 1 (a) :

```
BTC/USDC 1w 2025-09-15 binance close=115314.26 | bybit close at T=115329.60 at T+1w=115337.20
BTC/USDC 1w 2025-12-01 binance close=90412.00  | bybit close at T=90400.80  at T+1w=90466.50
ETH/USDC 1w 2025-12-08 binance close=3064.38   | bybit close at T=3062.83   at T+1w=3060.53
```
- Avant le recouvrement (2021 → juin 2025) : provenance 100 % Vision (`scripts/binance_vision_import.py`,
  `timestamp = row[0]` = open time), spot-check BTC 1d (§ 2.e), continuité `close(N) = open(N+1)` non utilisée
  (vraie sous les deux conventions). Aucune bascule détectée en aval → tout est open-stamped.
- **Signature de doublon** `(T, T+i)` OHLCV identiques, `volume > 0` : 1m BTC 38 (2023-04 → 2024-06), ETH 50
  (2021-03 → 2024-06), SOL 347 (2021-10 → 2024-09) ; 5m SOL 2 (2022-09-04) ; **0 au-delà**. Toutes en marché
  peu liquide 2021–2024, aucune en 2026 → **aucune zone de chevauchement Vision/WS**. (Candles plates
  `volume = 0` : 11 537 / 29 339 / 78 576 au 1m, non significatives.)

### 2.c Quantification pour la migration

Par série : `rows_to_restamp = COUNT(*) WHERE timestamp <= last_open_stamped_ts` = **toutes les rows** ;
collisions (cible `T + i` déjà occupée par une row hors périmètre) = **0 sur les 21 séries** ; total
**8 712 718 re-stamps, 0 collision, 0 suppression** → `rows_after == rows_before` attendu.

### 2.d Frontières exactes

`results/b4_binance_stamp_boundaries.json` (versionné) : `last_open_stamped_ts` = `MAX(timestamp)` de chaque
série (`2026-03-31 23:59` au 1m, `23:55` 5m, `23:45` 15m, `23:00` 1h, `20:00` 4h, `2026-03-31 00:00` 1d,
`2026-03-30 00:00` 1w), `first_end_stamped_ts = null`, plus `gaps` et `dup_signature_volume_gt0` de référence
pour l'invariant 3. Le script de migration et le mode `--post-migration` de l'audit ne lisent que ce fichier.

### 2.e Bord amont, autres exchanges, spot-check

- Pour chaque série : la row à `boundary + i` est **absente**, aucune row binance après la frontière
  (ex. BTC 1m : `23:58` c=68254.77, `23:59` o=68256.48 c=68240.16, rien à `2026-04-01 00:00`).
- `exchange='kraken'` (non touché) : `XBT/USDC` 1m 581 759 rows `2025-02-15 → 2026-05-30 02:00`, 5m
  `2023-02-16 → 2026-05-30`, … : ce sont les rows WS de l'époque (collector redémarré sur Kraken faute
  d'`EXCHANGE_NAME`, cf. `settings.py`) — explique l'absence de rows binance avril–juin 2026. Hors scope B4.1.
- Spot-check BTC 1d : `2024-01-01 00:00` open 42274.27 / close 44185.08 (candle du 1ᵉʳ janvier stampée à l'open)
  → **OK** ; attendu à `2024-01-02 00:00` après migration.

### 2.f Dry-run de la migration via tunnel (lecture seule, hors protocole serveur)

Premier dry-run (16:27 → 16:35 UTC, manifeste 16:25) : **2 550 fenêtres** (BTC et ETH : 690 au 1m, 138 au
5m, 46 au 15m, 12 au 1h, 3 au 4h, 1 au 1d et 1w = 891 chacune ; SOL : 594 + 119 + 40 + 10 + 3 + 1 + 1 = 768),
`staged = audit` sur les 21 séries, `collisions = 0 = audit` → MATCH. (Une version antérieure de ce rapport
écrivait « 2 511 » : erreur d'addition, les tallies par série n'ont jamais changé.)
Rejoué après la revue adversariale contre le manifeste **versionné** (`--dry-run --allow-tunnel --explain`,
plans `EXPLAIN` des trois statements du chemin `--execute` validés sur le schéma réel, table temporaire de
session vide, aucune écriture) : voir `results/b4_restamp_dryrun_tunnel.txt` (stamp du manifeste en en-tête).

### 2.g Complétude de la dernière 1w (GATE 1 c)

La dernière candle 1w Binance (`2026-03-30`, semaine 30/03 → 05/04) est **COMPLETE** sur les 3 paires : les
1d Binance s'arrêtant au 31/03, la vérification croise les 7 jours 1d **Bybit** (end-stamped 31/03 → 06/04) :

```
BTC/USDC 1w o=65977.66 h=69297.69 l=65705.71 c=69019.18 | close diff=2.4 bps high diff=4.6 bps low diff=1.6 bps
ETH/USDC 1w o=1983.56  h=2167.77  l=1979.08  c=2109.66  | close diff=3.9 bps high diff=1.9 bps low diff=15.5 bps
SOL/USDC 1w o=81.40    h=86.65    l=76.68    c=81.86    | close diff=21.9 bps high diff=6.9 bps low diff=2.6 bps
```
(open = open 1d Binance du 30/03, exact ; tolérance 50 bps ; signature de troncature absente : le close 1w ≠
close 1d Binance du 31/03.) Post-migration cette 1w sera stampée `2026-04-06 00:00`, cohérente avec sa fin réelle.

### 2.h Revue adversariale avant contact serveur (workflow multi-agents, 2026-09-13)

4 lentilles (SQL/TimescaleDB, fenêtres/reprise, invariants d'audit + importer, sécurité opérationnelle) →
24 findings uniques → 3 réfutateurs indépendants chacun (majorité) → **11 confirmés, 13 réfutés**. Corrigés :

| Finding confirmé | Correction |
|---|---|
| **Critique** — COMMIT et écriture du ledger non atomiques ; clé de fenêtre sans taille de batch : une reprise (crash entre COMMIT et append, autre `--max-rows-per-tx`, autre `--ledger`/HOME) redécalait des rows déjà décalées et en perdait une par fenêtre | décision 14 : table de progression transactionnelle + identité du plan + pré-vol (préfixe, `COUNT` des originales restantes) + garde slot `w_end` + verrou advisory ; tests de reprise après crash simulé, batch différent, progression non-préfixe, état DB ≠ manifeste |
| `--pairs`/`--intervals` inconnus → 0 série et `MATCH` rc 0 | refus rc 2 (valeurs validées contre le manifeste, sélection vide refusée), `MATCH` exige ≥ 1 série |
| Vote « close seul » strict post-migration : ~2–3 fenêtres 1w basculeraient par bruit → faux STOP | décision 13 (vote hybride), 0 fenêtre ambiguë pré-migration |
| `bybit_b3_crosscheck.py` code en dur l'ancien décalage : inutilisable comme invariant 4 | invariant 4 = vote au **même** timestamp du script d'audit (`--post-migration`) ; le script B3 reste un artefact historique non modifié (annexe § 5) |
| Docstrings `src/krakenbot/data/backfill.py`, `connectors/exchange.py`, `skills/bybit.md`, `README.md`, `CODE_MAP.md` disent encore « Binance mixte/open-stamped » | ajoutés à la liste § 7 (commit docs après GATE 3) |
| Traçabilité : le dry-run cité pointait un manifeste non versionné ; § 5.1 contredisait le diff (importer) | dry-run rejoué contre le manifeste versionné (2.f) ; § 5.1 mis à jour |
| Collisions imprévues absorbées silencieusement (réfuté 0/3 mais aligné sur la décision GATE 1-2) | toute collision > `expected_collisions` → `RestampStop`, fenêtre annulée, rc 3 |

Réfutés (non corrigés, consignés) : pré-vol contre `db_totals` (le pré-vol par série le remplace), garde tunnel
« heuristique » (protocole serveur), VACUUM avant le tableau final (désormais chronométré, tableau imprimé même
en cas d'erreur), bloat/WAL (59 GB libres), SQL du chemin execute jamais exécuté sur PG (couvert par `--explain`
et le dry-run serveur), `refine_boundary` sur run initial (sans objet : aucune bascule).

## ⛔ GATE 1 — décision Bruno (2026-09-13) : **GO**

1. Re-stamp : GO. 2. Policy « WS fait foi » confirmée ; le chemin `ON CONFLICT` reste ; toute collision au
dry-run serveur = mismatch → STOP. 3. Périmètre 100 % des rows `exchange='binance'` validé. Ajouts a/b/c →
décisions 10–12. Séquence GATE 2 rappelée : checkout serveur, backup frais (le dump du 7 sept ne compte pas),
`stop krakenbot-collector` (heure notée), dry-run serveur en tmux = **exactement 2 550 fenêtres / 8 712 718
rows / 0 collision**, estimation de durée du `--execute` à fournir, **STOP au GATE 2**.

## 3. Migration (étape 2, serveur) — à compléter après GATE 2

- Backup frais (avant toute écriture, collector encore actif) : `~/backups/krakenbot/krakenbot_20260913_b4pre.dump`,
  `pg_dump -Fc --no-owner --no-acl` dans le container, **254 100 825 octets**, créé `2026-09-13 17:34:29 UTC`,
  terminé `17:35:29 UTC`, exit 0, sha256 `89639d98172c64fcd46c654d63bcea6ead313045dcb5129984096fbc9f7166b3`,
  `pg_restore -l` : 1 172 entrées TOC (144 TABLE DATA, `market_data_ohlc` + chunks `_hyper_2_*`). Le dump du
  7 sept (211 MB, antérieur à l'import Bybit) est ignoré. Disque serveur : 59 GB libres.
- Serveur : `git checkout feat/b4-1-binance-restamp` @ `f71cf6a`, manifeste identique au dépôt (sha256
  `eb62eab6…`). Arrêt collector : **2026-09-13 17:46:59 UTC** (`systemctl stop`, `inactive`, journal propre :
  « Deactivated successfully »).
- Dry-run serveur (tmux `b4-dryrun`, `--dry-run --explain`, DB locale port 5432) : **17:47:05 → 17:49:07 UTC**,
  **2 550 fenêtres, staged = 8 712 718 = audit, collisions = 0 = audit, 21/21 séries → MATCH**, exit 0 ;
  plans `EXPLAIN` du chemin `--execute` OK sur chaque première fenêtre (Bitmap/Index Scan sur le chunk,
  `ModifyHypertable` pour DELETE et INSERT `ON CONFLICT DO NOTHING`). Sortie : `results/b4_restamp_dryrun_server.txt`.
  Cadence des requêtes de comptage : ~42 fenêtres/s (2 min pour 8,7 M rows).
- **Estimation `--execute`** (à confirmer par les lignes ETA imprimées toutes les 50 fenêtres) : par fenêtre,
  staging 4 000 rows + DELETE + INSERT avec 4 index btree + COMMIT ≈ 0,3–0,6 s sur le CX33 → **2 550 fenêtres ≈
  13–25 min**, + `VACUUM ANALYZE` 2–5 min, + audit `--post-migration` sur le serveur ≈ 3 min, + relance collector
  → **fenêtre d'arrêt du collector ≈ 45 min après le GO** (arrêt déjà effectif depuis 17:46:59 UTC ; backfill
  nocturne 03:30 UTC avec fenêtre de 3 jours pour le trou Bybit).
- Écriture hors `exchange='binance'` à autoriser au GO : table auxiliaire `b4_restamp_progress` (≈ 2 550 rows,
  progression transactionnelle, supprimée à la clôture) — décision 15.
- **GO GATE 2 (Bruno)** : dérogation `b4_restamp_progress` accordée (table à supprimer à la clôture, création et
  suppression consignées), correction 2 511 → 2 550 acceptée (comptabilité qui fait foi : rows + tallies par
  série + sha256 du manifeste `eb62eab641babd7b12cb44209fac27096d452a9139fc7c86b94610b2f7f01e5a`), fix de reprise
  transactionnelle validé.
- Pré-vol `--execute` (17:56:53 UTC) : serveur @ `f71cf6a`, collector et trader `inactive`, **`df -h /` : 75 G
  total, 14 G utilisés, 59 G libres (19 %)** (même volume pour le container DB), RAM disponible 5,9 G, table
  `b4_restamp_progress` absente, 8 712 718 rows binance, DB 3 156 MB.
- **`--execute --i-have-a-fresh-backup --ledger ~/b4_restamp_ledger.jsonl`** (tmux `b4-execute`) : début
  **17:56:57 UTC**, fin **18:07:40 UTC** (10 min 43 s ; 575 s cumulés de transactions, 0,24 s par fenêtre en
  moyenne), **2 550 fenêtres, staged = deleted = inserted = 8 712 718, collisions = 0, 21/21 séries → MATCH,
  exit 0**, aucune garde déclenchée, aucune reprise. `VACUUM ANALYZE market_data_ohlc` : **22 s**. Table
  `b4_restamp_progress` **créée** par le script (`CREATE TABLE IF NOT EXISTS`, 2 550 rows, `done_at` 17:56:59 →
  18:07:16 UTC, à supprimer à la clôture) ; ledger miroir `~/b4_restamp_ledger.jsonl` 2 550 lignes. Sorties :
  `results/b4_restamp_execute_server.txt`, `results/b4_restamp_ledger_server.jsonl`. Disque après : 58 G libres
  (hypertable 3 572 MB, DB 3 726 MB — bloat temporaire réclamé par autovacuum).
- Contrôles immédiats (psql) : `binance` 8 712 718 / `kraken` 1 181 469 inchangés, `bybit` 2 556 345 (dernières
  candles WS écrites avant l'arrêt) ; BTC 1m `2021-01-01 00:01 → 2026-04-01 00:00`, 1d `2021-01-02 → 2026-04-01`,
  1w `2021-01-11 → 2026-04-06` ; BTC 1d `2024-01-02 00:00` open 42274.27 / close 44185.08.
- Audit post-migration strict (tmux `b4-postaudit`, 18:08:19 → ~18:12 UTC) : **exit 1 — 6 fenêtres résiduelles**
  (§ 4.1, STOP remonté à Bruno). Sortie : `results/b4_timestamp_audit_post_migration.txt`.
- **Reprise collector : 2026-09-13 18:13:23 UTC**, `active (running)`, abonnements WS Bybit (kline 7 TF + tickers
  × 3 paires) et scheduler `gap_backfill` (`30 3 * * *`) démarrés, aucune erreur dans le journal. Relancé avant la
  décision de Bruno sur le STOP de l'audit (§ 4.1) pour ne pas laisser grandir le trou Bybit pendant l'attente :
  l'exécution est comptablement exacte et le collector n'écrit que des rows `bybit` (réversible). Arrêt total :
  17:46:59 → 18:13:23 UTC (26 min 24 s).

## 4. Invariants post-migration (étape 3)

### 4.1 ⛔ STOP audit strict — état des lieux pour décision Bruno

Le script d'audit en mode strict sort en exit 1 (6 fenêtres résiduelles, tableau au point 1 ci-dessous). Aucune
intervention n'a été faite en DB après ce STOP. Diagnostic (lecture seule, `results/b4_timestamp_audit_post_migration.txt`
et requête de couverture Bybit par semaine) : couverture Bybit 1m par semaine (minutes avec volume / votantes /
end / open) — BTC 06-23 : 0 ; **06-30 : 1 000 / 300 / 120 / 170** ; 07-07 : 2 610 / 1 208 / 719 / 483 ;
07-14 : 2 073 / 788 / 448 / 327 ; ETH 06-30 : 626 / 150 / 46 / 97 ; 07-07 : 1 873 / 671 / 401 / 263 ; SOL
06-30 : 368 / 64 / 18 / 38 ; 07-07 : 1 197 / 316 / 167 / 142. Options soumises (aucune n'a été appliquée) :
(a) accepter le résultat en documentant les 6 résidus comme limites de la référence (première semaine Bybit EU,
première 1w partielle, seuil d'ambiguïté) ; (b) durcir l'audit — exclure les fenêtres dont la couverture de
référence est < N % ou la première semaine du recouvrement, passer le seuil d'ambiguïté 1w à ≥ 0,5 % ou au vote
OHLC pour les 1d/1w — et le rejouer (lecture seule) ; (c) NO-GO → restauration du dump 17:34 UTC.

1. `b4_timestamp_audit.py --post-migration` (strict) : **15/21 séries à 100 % *end*** (40/40 fenêtres) ;
   majorité par row *end* sur les 21 séries ; **les 36 rows ambiguës revérifiées une à une votent toutes *end***
   (dont BTC 1w 2025-09-15 et 2025-12-01, ETH 1w 2025-12-08). **⛔ 6 fenêtres résiduelles → exit 1 → STOP**
   (règle GATE 1 a) :

   | Série | Fenêtre | open/end/tie | Cause identifiée (lecture seule, § 4.1) |
   |---|---|---|---|
   | BTC 1m | 2025-06-30 | 170/120/10 | 1ʳᵉ semaine de liquidité Bybit EU : 1 000 minutes avec volume sur 10 080, 300 rows votantes, volume moyen 0,014 BTC/min |
   | BTC 5m | 2025-06-30 | 168/166/5 | idem, pile ou face |
   | ETH 1m | 2025-06-30 | 97/46/7 | idem (626 minutes avec volume, 150 votantes) |
   | SOL 1m | 2025-06-30 | 38/18/8 | idem (368 minutes avec volume, 64 votantes) |
   | ETH 1w, SOL 1w | 2025-06-30 | 1/0/0 | 1ʳᵉ candle 1w Bybit **partielle** (3 jours 27→29/06, spikes de lancement : ETH H 2785.93) comparée à la semaine Binance complète 23→29/06 |
   | ETH 1w | 2026-03-02 | 1/0/0 | closes Bybit candidats à 0,21 % (> seuil d'ambiguïté 0,1 %) et écart Binance/Bybit de 0,32 % au close : le close seul tranche à tort ; distance OHLC : same 9.84 vs next 188.68 (*end* ×19) |

   Explication du signe post-migration sur la semaine 06-30 : avec des candles Bybit à 1 trade, le prix Bybit
   **retarde d'environ une minute** sur Binance ; pré-migration ce retard éloignait le mauvais candidat (candle
   précédente, −2 min) et confortait *open* ; post-migration il rapproche le mauvais candidat (candle suivante,
   ≈ 0 min) → *open* par bruit. Dès la semaine du 07-07 (2 610 minutes Bybit avec volume) *end* gagne 719/483,
   puis partout. Les comptages par série sont exacts (invariant 2) : ce n'est pas un défaut de migration mais une
   limite de la référence Bybit sur sa première semaine. **Décision Bruno requise** (cf. § 4.1).
2. Comptabilité : **21/21 séries exactes** (`rows_after == rows_before − 0`), total 8 712 718 ; tallies du script
   (staged = deleted = inserted par série) = manifeste ; `kraken` inchangé. ✅
3. Trous : **21/21 listes identiques à l'audit décalées de +interval** ; signature de doublon (`volume > 0`)
   inchangée (38/50/347 au 1m, 2 au 5m SOL). ✅
4. Spot-check BTC 1d `2024-01-02 00:00` open 42274.27 / close 44185.08 : **OK** ; 1w binance en lundi 00:00
   (`2021-01-11 → 2026-04-06`) ; 1d/1w Bybit au **même** timestamp : fenêtres 1d 40/40 *end* sur les 3 paires,
   1w 40/40 (BTC), 38/40 (ETH), 39/40 (SOL) — résidus expliqués au point 1. ✅ (sous réserve du point 1)
5. `MAX(timestamp)` : 1m `2026-04-01 00:00`, 5m/15m/1h/4h/1d `2026-04-01 00:00`, 1w `2026-04-06 00:00` = frontière
   + intervalle sur les 21 séries ; `MIN` décalé de +intervalle sur les 21 séries. ✅
6. Backtest de référence `grok_supertrend_4h BTC/USDC --exchange binance --days 1095 --capital 1000` vs
   baseline P6 (`results/P6_phase_d_results.json`, clé `grok_supertrend_4h_BTC_USDC.all` : return +3.29 %,
   Sharpe 0.336, PF 1.82, MaxDD 1.76 %, 46 trades) — _delta brut, sans analyse_.
7. Dernière 1w de chaque paire = semaine complète, stampée `2026-04-06 00:00`, close/high/low à 2–22 bps des
   7 jours 1d Bybit (BTC 2.4/4.6/1.6, ETH 3.9/1.9/15.5, SOL 21.9/6.9/2.6 bps). ✅
8. Lendemain (Bruno) : `gap_backfill` 03:30 UTC vert, trou Bybit de la fenêtre de migration comblé.

## 5. Tâches annexes consignées (non faites, hors scope B4.1)

1. ~~`scripts/binance_vision_import.py` écrit toujours l'open time~~ → **corrigé dans cette branche** (GATE 1 b) :
   `parse_klines_csv` renvoie `open_time + interval`, tests `test_timestamp_is_utc_period_end` et
   `test_timestamp_period_end_per_interval` (7 TF, ms et µs). Le fichier était « lecture seule » dans le brief ;
   dérogation explicite de Bruno au GATE 1.
2. Rows `exchange='kraken'` `XBT/USDC` de 2025-02 → 2026-05 = données WS de l'ancien connecteur ; à traiter avec
   la suppression prévue du legacy kraken (PROJECT_CONTEXT § 6).
3. Dette 11 / `PROJECT_CONTEXT.md` § 9 et `skills/binance_import.md` (« toutes finissent en juin 2026 ») :
   la fenêtre avril–juin 2026 n'a jamais existé sous `binance` ; docs à corriger (commit docs, après GATE 3).
4. Trous Vision 1w d'une semaine (2022-05-30, 06-27, 08-29, 2025-01-27, 02-24) et micro-trous 2021 : données
   absentes de Binance Vision, pas comblables sans source ; à documenter dans `P6_data_coverage.md` si besoin.
5. `ruff format --check` : `scripts/backtest.py`, `scripts/p6_5_diagnose_*.py` non formatés (pré-existant, dette 10).
6. `scripts/audit/bybit_b3_crosscheck.py` (B3) code en dur le décalage d'un intervalle Binance/Bybit : après B4.1 son
   contrôle (a) affichera « STOP » à tort. Artefact historique, non modifié ; à paramétrer ou archiver si réutilisé.
7. Docstrings à réaligner au commit docs (§ 7, revue 2.h) : `src/krakenbot/data/backfill.py` (module),
   `src/krakenbot/connectors/exchange.py` (`fetch_ohlcv`), `skills/bybit.md`, `README.md` (« 2026-06 »),
   `docs/CODE_MAP.md` — la garantie « Bybit seulement » reste vraie (les clients REST Binance/Kraken renvoient
   l'open time ccxt), mais plus « parce que la DB Binance est mixte ».
8. Table auxiliaire `b4_restamp_progress` à supprimer après GATE 3 (`DROP TABLE b4_restamp_progress`).

## 6. Tests et qualité

- Nouveaux : `tests/test_scripts/test_b4_stamp_lib.py` (23 : votes, mode strict, bascule, raffinement de
  frontière, fenêtres décroissantes ancrées lundi, manifeste JSON aller-retour, ledger, comptabilité, plan de
  reprise) et `tests/test_scripts/test_b4_restamp_binance.py` (20 : refus tunnel / backup / batch > 5000 /
  identifiant de table / filtres inconnus, dry-run = manifeste ou rc 1/2, `--explain`, exécution complète,
  reprise depuis la table DB sans double décalage après crash simulé post-COMMIT, refus batch différent /
  progression non-préfixe / état DB ≠ manifeste, collision imprévue → rollback rc 3, collision autorisée
  comptée, garde slot occupé, VACUUM en fin d'exécution) ; `test_binance_vision_import.py` (+2, end-stamps).
- Aucun test ne touche la DB en local ; les tests DB (`--post-migration`, dry-run serveur) se jouent sur le serveur.
