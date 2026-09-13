# B4.1 — Audit des conventions de timestamp et re-stamp des données Binance

> Généré le 2026-09-13, branche `feat/b4-1-binance-restamp` (base `dev` @ `08e8e1f`, tag de départ
> `v2.5.0-b3-bybit-data`). Spec : `agent/AGENT_B4_1_TIMESTAMP_AUDIT_RESTAMP.md`. Plan validé par Bruno le
> 2026-09-13 (plan mode). Collector Bybit **actif** pendant l'audit (lecture seule, via tunnel).
>
> État : **étape 1 (audit) terminée → ⛔ GATE 1 en attente du GO.** Aucune écriture DB n'a eu lieu.

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
- **Dry-run via tunnel (lecture seule, 2026-09-13 16:27–16:35 UTC)** : 2 511 fenêtres, `staged=8 712 718`,
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

### 2.b Classification open/end par contenu

- Recouvrement Bybit : BTC dès `2025-06-11 09:21`, ETH/SOL dès `2025-06-27` ; 40 semaines votées par série
  (1m : ~437 k rows votées par paire).
- **Open gagne 100 % des fenêtres décisives des 21 séries ; majorité par row *open* partout.** Trois fenêtres 1w
  d'une seule row votent *end* (non décisives) — closes hebdo consécutifs quasi égaux, l'écart inter-exchange tranche :

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

`poetry run python scripts/audit/b4_restamp_binance.py --dry-run --allow-tunnel` (16:27 → 16:35 UTC) :
2 511 fenêtres (690 par série 1m, 138 au 5m, 46 au 15m, 12 au 1h, 3 au 4h, 1 au 1d/1w), `staged = audit`
sur les 21 séries, `collisions = 0 = audit` → **MATCH** (`results/b4_restamp_dryrun_tunnel.txt`).

## ⛔ GATE 1 — décision Bruno

À trancher : re-stamp **GO / NO-GO** ; policy collisions « WS fait foi » confirmée (sans objet : 0 collision) ;
périmètre = 100 % des rows binance (21 séries, `last_open_stamped_ts = MAX(timestamp)`) validé.

Après le GO : sur le serveur, `git fetch && git checkout feat/b4-1-binance-restamp`, backup frais `pg_dump -Fc`
(taille + horodatage ci-dessous), `sudo -n systemctl stop krakenbot-collector`, tmux `b4-restamp`,
`--dry-run` serveur (doit reproduire § 2.f) → **GATE 2**.

## 3. Migration (étape 2, serveur) — à compléter après GATE 2

- Backup frais : _à consigner (fichier, taille, horodatage)_.
- Arrêt collector : _heure UTC_. Dry-run serveur : _sortie_. GO GATE 2 : _heure_.
- `--execute --i-have-a-fresh-backup --ledger ~/b4_restamp_ledger.jsonl` : _durée, tableau final, VACUUM ANALYZE_.
- Reprise collector : _heure UTC, `active (running)`, logs WS propres_.

## 4. Invariants post-migration (étape 3) — à compléter

1. `b4_timestamp_audit.py --post-migration` : end gagne 100 % des fenêtres décisives, 21 séries — _résultat_.
2. Comptabilité `rows_after == rows_before − collisions` (8 712 718 − 0) — _résultat_.
3. Trous = liste de l'audit décalée de +interval, signature de doublon inchangée — _résultat_.
4. Spot-checks : BTC 1d à `2024-01-02 00:00` open 42274.27 / close 44185.08 ; 1w lundi 00:00 ; contrôle
   1d/1w de `bybit_b3_crosscheck` matchant au **même** timestamp — _résultat_.
5. `MAX(timestamp)` 1m = `2026-04-01 00:00` (et `boundary + i` par série) — _résultat_.
6. Backtest de référence `grok_supertrend_4h BTC/USDC --exchange binance --days 1095 --capital 1000` vs
   baseline P6 (`results/P6_phase_d_results.json`, clé `grok_supertrend_4h_BTC_USDC.all` : return +3.29 %,
   Sharpe 0.336, PF 1.82, MaxDD 1.76 %, 46 trades) — _delta brut, sans analyse_.
7. Lendemain (Bruno) : `gap_backfill` 03:30 UTC vert, trou Bybit de la fenêtre de migration comblé.

## 5. Tâches annexes consignées (non faites, hors scope B4.1)

1. **`scripts/binance_vision_import.py` écrit toujours l'open time** (`row[0]`, aucun décalage) et
   `tests/test_scripts/test_binance_vision_import.py::test_timestamp_is_utc` verrouille ce comportement :
   tout ré-import Vision réintroduirait des rows open-stamped. À corriger (+ test) avant tout nouvel import.
2. Rows `exchange='kraken'` `XBT/USDC` de 2025-02 → 2026-05 = données WS de l'ancien connecteur ; à traiter avec
   la suppression prévue du legacy kraken (PROJECT_CONTEXT § 6).
3. Dette 11 / `PROJECT_CONTEXT.md` § 9 et `skills/binance_import.md` (« toutes finissent en juin 2026 ») :
   la fenêtre avril–juin 2026 n'a jamais existé sous `binance` ; docs à corriger (commit docs, après GATE 3).
4. Trous Vision 1w d'une semaine (2022-05-30, 06-27, 08-29, 2025-01-27, 02-24) et micro-trous 2021 : données
   absentes de Binance Vision, pas comblables sans source ; à documenter dans `P6_data_coverage.md` si besoin.
5. `ruff format --check` : `scripts/backtest.py`, `scripts/p6_5_diagnose_*.py` non formatés (pré-existant, dette 10).

## 6. Tests et qualité

- Nouveaux : `tests/test_scripts/test_b4_stamp_lib.py` (19 : votes, bascule, raffinement de frontière,
  fenêtres décroissantes ancrées lundi, manifeste JSON aller-retour, ledger, comptabilité) et
  `tests/test_scripts/test_b4_restamp_binance.py` (11 : refus tunnel / backup / batch > 5000, sélection de
  séries, dry-run = manifeste, écart → rc 1, reprise via ledger, collisions comptées, VACUUM en fin d'exécution).
- Aucun test ne touche la DB en local ; les tests DB (`--post-migration`, dry-run serveur) se jouent sur le serveur.
