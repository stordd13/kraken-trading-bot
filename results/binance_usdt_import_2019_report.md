# Import complémentaire USDT Binance 2019-2020 — BTC/ETH/SOL × 6 TF, profondeur d'amorçage (2026-09-23)

> **Ce rapport décrit un import de données et sa vérification. Il ne valide rien** : aucun backtest, aucun manifeste,
> aucune comparabilité USDC ↔ USDT mesurée, aucune sélection, aucune modification du protocole C3 ni de la transposition
> USDT → USDC (gate d'amendement). Chantier `chore/data-binance-usdt-2019` depuis `dev` @ `373da3f` ; brief « import
> complémentaire USDT Binance 2019-2020 » (Bruno, 23/09 — le « 24/09 » du brief est une coquille, corrigée au STOP 1) ;
> modèle reproduit à l'identique : l'import du même jour (`results/binance_usdt_import_report.md`). Artefacts dans
> `results/binance_usdt_import_2019_20260923/` (empreintes : `SHA256SUMS.txt`) et `results/data_inventory_usdt_2019_20260923/`.

## 1. Pourquoi et quoi

Décision Bruno (23/09) : une porte 1w avec EMA 50 exige 50 semaines d'amorçage ; avec des séries USDT qui commencent au
2021-01-01, aucune fenêtre ne peut débuter avant ~2021-12. Vision publie `BTCUSDT` / `ETHUSDT` depuis 2017 et `SOLUSDT` depuis
2020-08. Les 18 séries `*/USDT` (`exchange='binance'`, 6 TF : 5m, 15m, 1h, 4h, 1d, 1w) sont **prolongées vers l'arrière**,
`2019-01-01 → 2020-12-31`, avec le même script, non modifié, idempotent (`ON CONFLICT DO NOTHING`). Les mois antérieurs à
2019-01 (BTC/ETH) ne sont pas importés : toute extension est une nouvelle décision.

Décisions au STOP 1 (Bruno, 23/09) : artefacts et dump datés `20260923` ; répertoires `binance_usdt_import_2019_20260923/` et
`data_inventory_usdt_2019_20260923/` (le nom du brief, `data_inventory_usdt_<date>/`, est déjà pris par le premier import) ;
diff des rows existantes borné à `timestamp > 2021-01-01T00:00Z` (5m → 1d) et `> 2021-01-04T00:00Z` (1w), **empreinte à cinq
champs** (count, min, max, `sum(close)`, `sum(volume)`) ; inventaire avec l'outil de `dev` tel qu'il est sur le serveur.

## 2. Chronologie (UTC, 2026-09-23)

| Heure | Étape | Sortie |
|---|---|---|
| 12:14:35 | Contrôle serveur (lecture seule) | `dev` @ `373da3f` (= local), collector active, trader inactive, 53 G libres, dump du premier import présent |
| 12:17:16 | État avant (lecture seule) | `state_before.txt` : 39 séries binance = 11 288 569 rows (21 USDC 8 712 718, 18 USDT 2 575 851), **0 row USDT ≤ `2021-01-01T00:00Z`**, empreinte à cinq champs des rows 2021+, hypertable 3 853 Mo (112 chunks, 0 compressé) |
| 12:17 – 12:19 | 432 sondes `HEAD` Vision depuis le serveur | `vision_head_before.txt` : **318 × 200, 114 × 404** = `SOLUSDT` × 6 TF × 2019-01 → 2020-07 ; BTC/ETH 200 sur 24 × 6 |
| 12:24:41 → 12:25:56 | Backup (tmux `usdt2019_backup`) | `krakenbot_20260923_pre_usdt2019.dump`, rc 0 |
| 12:26:12 → 12:26:14 | Canari (tmux `usdt2019_canari`) | 1 fichier, 31 rows, exit 0 |
| 12:26:17 | Vérification du canari (lecture seule) | 31 rows `BTC/USDT` 1440, `2019-01-02T00:00Z → 2019-02-01T00:00Z`, série 1d = 2 100, USDC 8 712 718, USDT 2021+ 2 575 851 |
| **12:32:48 → 12:42:46** | **Import complet (tmux `usdt2019_import`)** | 432 fichiers, `import_complete failed_files=0 processed_files=432 total_rows=664403`, exit 0 |
| 12:43:35 | Comptage du journal | `import_usdt2019_log_counts.txt` |
| 12:43:42 | État après (lecture seule) | `state_after.txt` : 39 séries, binance **11 952 972** |
| 12:43:58 | Contrôle du collector (lecture seule) | `collector_check_output.txt` |
| 12:44:05 → 12:45:00 | Inventaire post-import (tmux `usdt2019_inventory`) | `data_inventory_usdt_2019_20260923/inventory.{json,md}`, exit 0 |

Serveur : `~/apps/kraken-trading-bot` sur `dev` @ `373da3f` (= `dev` local) pendant toute l'opération ; collector actif
(`krakenbot-collector` active, `krakenbot` inactive), aucun `systemctl`, `.env` serveur intact, aucun tunnel, aucune écriture
en base hors l'import, aucun `DELETE` / `UPDATE`, script `scripts/binance_vision_import.py` **non modifié** (sha256
`63575e0f…`, identique local / serveur). Six fichiers Vision de bord (`SOLUSDT` 5m/1d/1w 2020-08, `BTCUSDT` 1w 2019-01 et
2020-12, 5m 2020-12) ont été lus localement dans le scratchpad, hors dépôt, pour fixer les attendus du STOP 1.

## 3. Commandes exactes

Chaque commande d'écriture a été affichée mot pour mot au STOP 1 avant le GO et lancée par un script en tmux
(`tmux new -d -s <session> "bash -lc /home/bruno/<script>"`), le journal capturé par `exec > >(tee <log>) 2>&1` ; les scripts
sont archivés dans `results/binance_usdt_import_2019_20260923/server_scripts/` et leur sha256 a été vérifié identique des deux
côtés avant chaque lancement. Environnement de shell : `unset SCHEDULER_PAIRS SCHEDULER_INTERVALS` (quirk `.bashrc:119`, B3)
et `NO_COLOR=1`.

```bash
# backup (usdt2019_backup_20260923.sh)
sudo -n docker exec krakenbot-db pg_dump -U krakenbot -Fc --no-owner --no-acl krakenbot > /home/bruno/backups/krakenbot/krakenbot_20260923_pre_usdt2019.dump
# canari (usdt2019_canari_20260923.sh), arbre du service
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT --intervals 1d --start-date 2019-01-01 --end-date 2019-01-31
# import complet (usdt2019_import_20260923.sh), arbre du service
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --intervals 5m,15m,1h,4h,1d,1w --start-date 2019-01-01 --end-date 2020-12-31
# inventaire post-import (usdt2019_inventory_20260923.filled.sh), arbre du service, outil de dev @ 373da3f, sortie hors de l'arbre
poetry run python scripts/audit/data_inventory.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --skip-vision --now 2026-09-23T12:43:00Z --output /home/bruno/usdt2019_inventory_out/inventory.json --markdown /home/bruno/usdt2019_inventory_out/inventory.md
```

Lecture seule : `state_query.sql` (état avant / après, avec l'empreinte à cinq champs des rows 2021+), `vision_head_probe.sh`
(432 `HEAD`), `canari_check.sql`, `collector_check.sql` (fenêtre `2026-09-23 12:32:48+00 → 12:42:46+00`).

## 4. Backup pré-import

`/home/bruno/backups/krakenbot/krakenbot_20260923_pre_usdt2019.dump` — `pg_dump -Fc --no-owner --no-acl`, **319 059 235
octets**, sha256 `2c94e92fac53ed72f84f721e26bd713f58801374f28c4e6fb28d4b31601eb2ec`, **1 188 entrées** `pg_restore -l`,
`.status` = `done 0 2026-09-23T12:25:56Z`. Le `.err` contient les trois avertissements TimescaleDB « circular foreign-key
constraints » (hypertable, chunk, continuous_agg), identiques aux dumps précédents. Restauration : `skills/database.md`.
Le dump du premier import (`krakenbot_20260923_pre_usdt`, 255 301 183 octets) est conservé.

## 5. Comptes avant / après

### 5.1 Rows importées (2019-01 → 2020-12) — BTC et ETH identiques

| TF | BTC, ETH importées | Grille (731 j) | Manquantes | Premier stamp | SOL importées | Grille SOL (2020-08-11T06:00Z →) | Manquantes | Premier stamp SOL |
|---|---|---|---|---|---|---|---|---|
| 5m | 209 927 | 210 528 | 601 | 2019-01-01T00:05Z | 41 042 | 41 112 | 70 | 2020-08-11T06:05Z |
| 15m | 69 977 | 70 176 | 199 | 2019-01-01T00:15Z | 13 681 | 13 704 | 23 | 2020-08-11T06:15Z |
| 1h | 17 499 | 17 544 | 45 | 2019-01-01T01:00Z | 3 421 | 3 426 | 5 | 2020-08-11T07:00Z |
| 4h | 4 381 | 4 386 | 5 | 2019-01-01T04:00Z | 857 | 857 | 0 | 2020-08-11T08:00Z |
| 1d | 731 | 731 | 0 | 2019-01-02T00:00Z | 143 | 143 | 0 | 2020-08-12T00:00Z |
| 1w | 104 | 104 | 0 | 2019-01-14T00:00Z | 21 | 21 | 0 | 2020-08-17T00:00Z |
| **Par paire** | **302 619** | 303 469 | 850 | | **59 165** | 59 263 | 98 | |

Total **664 403** = 2 × 302 619 + 59 165 = `total_rows` du journal = delta de la base (11 952 972 − 11 288 569) : aucune row
dupliquée, aucune perdue ; les 31 rows du canari sont incluses (recouvertes par `ON CONFLICT DO NOTHING`). Manquantes = somme
des trous mesurés (§ 6) ; les premiers stamps sont ceux annoncés au STOP 1 (grille alignée, cotation SOL au `2020-08-11T06:00Z`).

### 5.2 Les 18 séries après import (`state_after.txt`) = count du 23/09 + rows importées, `max` inchangé

| TF | BTC, ETH | = 2021+ | + 2019-2020 | SOL | = 2021+ | + 2020 | Premier stamp BTC/ETH | Premier stamp SOL | Dernier stamp |
|---|---|---|---|---|---|---|---|---|---|
| 5m | 805 586 | 595 659 | 209 927 | 636 701 | 595 659 | 41 042 | 2019-01-01T00:05Z | 2020-08-11T06:05Z | 2026-09-01T00:00Z |
| 15m | 268 531 | 198 554 | 69 977 | 212 235 | 198 554 | 13 681 | 2019-01-01T00:15Z | 2020-08-11T06:15Z | 2026-09-01T00:00Z |
| 1h | 67 141 | 49 642 | 17 499 | 53 063 | 49 642 | 3 421 | 2019-01-01T01:00Z | 2020-08-11T07:00Z | 2026-09-01T00:00Z |
| 4h | 16 795 | 12 414 | 4 381 | 13 271 | 12 414 | 857 | 2019-01-01T04:00Z | 2020-08-11T08:00Z | 2026-09-01T00:00Z |
| 1d | 2 800 | 2 069 | 731 | 2 212 | 2 069 | 143 | 2019-01-02T00:00Z | 2020-08-12T00:00Z | 2026-09-01T00:00Z |
| 1w | 383 | 279 | 104 | 300 | 279 | 21 | 2019-01-14T00:00Z | 2020-08-17T00:00Z | 2026-07-06T00:00Z |
| **Par paire** | **1 161 236** | 858 617 | 302 619 | **917 782** | 858 617 | 59 165 | | | |

Total `*/USDT` : **3 240 254** rows (2 × 1 161 236 + 917 782).

### 5.3 Rows existantes — deux diffs vides

- **21 séries `*/USDC`** (`usdc_before_after_diff.txt`) : `diff -u` **vide** entre `state_before.txt` (12:17:16) et
  `state_after.txt` (12:43:42) sur `pair|interval|count|min|max`, somme 8 712 718 des deux côtés.
- **18 séries `*/USDT` restreintes aux rows du premier import** (`usdt_2021plus_before_after_diff.txt`) : `timestamp >
  2021-01-01T00:00Z` (5m → 1d), `> 2021-01-04T00:00Z` (1w) ; `diff -u` **vide** sur `pair|interval|count|min|max|sum(close)|
  sum(volume)`, somme 2 575 851 des deux côtés. Aucune row du 23/09 n'a été ni ajoutée, ni retirée, ni modifiée en contenu.

### 5.4 Jointure au 2021-01-01

Le fichier 2020-12 apporte le stamp `2021-01-01T00:00Z` (5m, 15m, 1h, 4h, 1d) et `2021-01-04T00:00Z` (1w) ; les rows du premier
import reprennent à `00:05Z` / `00:15Z` / `01:00Z` / `04:00Z` / `2021-01-02T00:00Z` / `2021-01-11T00:00Z`. L'inventaire (§ 8) ne
mesure **aucun trou traversant la jointure** sur les 18 séries (vérifié programmatiquement dans `inventory.json` : aucun trou
avec `début < 2021-01-12` et `fin > 2020-12-31`) ; les trous 5m les plus proches sont le 2020-12-25 et le 2021-02-11.

### 5.5 Table entière

| | Avant (12:17) | Après (12:43) |
|---|---|---|
| `binance` | 11 288 569 (39 séries) | **11 952 972 (39 séries)** |
| `bybit` | 2 610 736 | 2 610 832 (collector actif) |
| `kraken` | 1 181 469 | 1 181 469 |
| Rows `*/USDT` hors `binance` | 0 | 0 |
| Hypertable | 3 853 Mo, 112 chunks, 0 compressé | 4 019 Mo, 112 chunks, 0 compressé (+166 Mo) |
| Disque `/` | 53 G libres | 52 G libres (dump 319 Mo) |

## 6. Trous 2019-2020 (mesurés par `data_inventory.py`, `LAG` SQL, estampilles fin de période)

Attendu du brief : trous de maintenance consignés (dates, durée), jamais comblés, **STOP si > 1 jour**. **Constat : 14 fenêtres
sur BTC et ETH, identiques bougie pour bougie ; la plus longue dure 10 h (2019-05-15) ; aucun trou sur 1d ni 1w ; SOL (coté
depuis 2020-08-11) partage les trois fenêtres de novembre–décembre 2020.** Aucun STOP.

| Fenêtre (dernier stamp présent → premier suivant, 5m) | Durée | 5m | 15m | 1h | 4h | SOL |
|---|---|---|---|---|---|---|
| 2019-03-12T02:00Z → 08:05Z | 6 h 00 | 72 | 24 | 6 | 1 | — |
| **2019-05-15T03:00Z → 13:05Z** | **10 h 00** | 120 | 40 | 10 | **2** | — |
| 2019-06-07T21:15Z → 22:20Z | 1 h 00 | 12 | 4 | 0 | 0 | — |
| 2019-08-15T02:00Z → 10:05Z | 8 h 00 | 96 | 32 | 8 | 1 | — |
| 2019-11-13T02:00Z → 04:25Z | 2 h 20 | 28 | 9 | 2 | 0 | — |
| 2019-11-25T02:00Z → 04:05Z | 2 h 00 | 24 | 8 | 2 | 0 | — |
| 2020-02-09T02:00Z → 03:05Z | 1 h 00 | 12 | 4 | 1 | 0 | — |
| 2020-02-19T11:40Z → 17:35Z | 5 h 50 | 70 | 23 | 5 | 1 | — |
| 2020-03-04T09:25Z → 11:35Z | 2 h 05 | 25 | 8 | 1 | 0 | — |
| 2020-04-25T02:00Z → 04:35Z | 2 h 30 | 30 | 10 | 2 | 0 | — |
| 2020-06-28T02:00Z → 05:35Z | 3 h 30 | 42 | 14 | 3 | 0 | — |
| 2020-11-30T06:00Z → 07:05Z | 1 h 00 | 12 | 4 | 1 | 0 | oui |
| 2020-12-21T14:10Z → 18:05Z | 3 h 50 | 46 | 15 | 3 | 0 | oui |
| 2020-12-25T02:00Z → 03:05Z | 1 h 00 | 12 | 4 | 1 | 0 | oui |
| **Total BTC / ETH** | | **601** | **199** | **45** | **5** | |
| **Total SOL (trois dernières)** | | **70** | **23** | **5** | 0 | |

Les fenêtres 2019-2020 ont la signature des maintenances Binance (début à 02:00 UTC pour neuf d'entre elles) ; celles de
décembre 2020 expliquent les 58 rows manquantes du fichier `BTCUSDT-5m-2020-12` constatées au STOP 1 (46 + 12). **Sur 4h**, la
base USDT porte désormais 5 bougies manquantes (aucune avant sur 2021+) dont **2 consécutives le 2019-05-15** : par la règle C2
(`largest_gap_candles ≤ 1`), un amorçage 4h qui traverserait ce trou serait cassé — l'inventaire (fait 5) calcule les débuts
admissibles qui le suivent (`S(14)` = `2019-05-17T20:00Z`, `S(50)` = `2019-05-23T20:00Z`, `S(200)` = `2019-06-17T20:00Z`). Ce
n'est qu'un fait de grille, pas une clause d'admissibilité. Les 8 bougies 1w isolées (2022, 2025) et les trous 2021+ sont ceux du
premier import, inchangés.

## 7. Journal de l'import (`import_usdt2019.log`, 1 197 lignes, sans séquence ANSI)

| Événement | Compte | Attendu |
|---|---|---|
| `downloading` | 432 | 432 (24 mois × 6 TF × 3) |
| `imported` (= `imported_batch` final) | 318 | 318 |
| `file_not_found` (404, debug) | **114** | **114** : `SOLUSDT` × {5m, 15m, 1h, 4h, 1d, 1w} × 2019-01 → 2020-07, **0 hors SOL** |
| `download_failed` (exception réseau) | **0** | 0 |
| `month_failed` | **0** | 0 |
| `parse_error` / `zip_extract_error` | 0 | 0 |
| `progress` | 8 | — |

`import_complete failed_files=0 processed_files=432 total_rows=664403`, `import exit=0`, disque 52 G libres avant et après.
Durée 9 min 58 s (12:32:48 → 12:42:46). Le contrôle ANSI a été recompté localement (0) : le `grep` du serveur a refusé la regex
(`import_usdt2019_log_counts.txt`, ligne annotée).

## 8. Inventaire post-import (`results/data_inventory_usdt_2019_20260923/`)

Outil : `scripts/audit/data_inventory.py` de `dev` @ **`373da3f`**, tel qu'il est sur le serveur (sha256
`1b3b87f02c7a37dd3422a1fe13c670fc0fc4301d928fb0255c7e07f47f040c63`, égal au local), `--pairs BTC/USDT,ETH/USDT,SOL/USDT`
(**18 séries** retenues sur 74 agrégées), `--skip-vision` (les 432 `HEAD` sont dans `vision_head_before.txt`), `--now
2026-09-23T12:43:00Z` (fin de l'import arrondie à la minute supérieure), session `transaction_read_only = on`,
`statement_timeout = 5min`. `inventory.json` sha256 `cd5ad866c9e34e2633348c8e36b7b3399119e24e012972ee2eff11d9d634c23f`, `inventory.md` sha256
`00be1e5bd30503a3a853def8c46b9996c5423a639f8ceb2705839122f5ef26aa`. L'attendu d'une série y est dérivé de `[premier, dernier]` stamp : les séries 2019 sont
mesurées sans hypothèse de date ; l'étiquette « vue complète 2021-01 → 2026-04 » de ses métadonnées est cosmétique, et sa
section 5 (amorçage 1w) ne voit aucun trou ≥ 2 bougies sur la 1w des trois paires.

## 9. Collector Bybit pendant et après l'import

`collector_check_output.txt` (12:43:58) : dernière bougie 1m Bybit `2026-09-23 12:43:00+00` pour les trois paires (**âge 59 s**,
attendu < 3 min) ; sur la fenêtre `12:32:48 → 12:42:46`, **10 rows 1m par paire et 0 trou > 1 min** (`LAG`).
`journalctl -u krakenbot-collector` sur la fenêtre : `bybit_ws_data_flow_ok` toutes les 5 min, `collector_periodic_stats` avec
`errors: 0, reconnections: 0, resubscribes: 0` (les 6 lignes retenues par le filtre `error|warning|reconnect|resubscribe` sont
ces statistiques à zéro). Service `active` avant et après, aucun restart.

## 10. Écarts consignés et reprises (hors chantier)

1. **Fin de série 1w = `2026-07-06`** (inchangée) : reprise à faire quand Vision publiera les fichiers 1w 2026-07 et 2026-08
   (`--intervals 1w --start-date 2026-07-01 --end-date 2026-08-31`, idempotent). Déjà consignée le 23/09.
2. **Bornes de début** : BTC/ETH `2019-01-01` par décision, alors que Vision remonte à 2017-08 ; SOL `2020-08` (premier fichier
   Vision). Consignées dans `skills/binance_import.md` § « Prolongation 2019-2020 ».
3. **Trou 4h de 2 bougies le 2019-05-15** (§ 6) : premier trou ≥ 2 bougies sur 4h dans la base USDT ; consigné, pas comblé.
4. Découvertes annexes : le `grep` du serveur refuse la regex `\x1b[` (recompté localement) ; le script d'import n'a toujours
   pas de retry (0 `download_failed` sur 432).

## 11. Empreintes des artefacts

`results/binance_usdt_import_2019_20260923/SHA256SUMS.txt` liste les 28 fichiers (`shasum -c` : 0 écart). Principales :

| Fichier | sha256 |
|---|---|
| `state_before.txt` | `9e1af1f088d19d28ef969c39db0861ef1774ee60ac3a69e6f1d423b8232e182f` |
| `vision_head_before.txt` | `9795e50f4a0a66a88a59a35d54f747c155f7f534271c6b72d173b8e64e585e4b` |
| `state_after.txt` | `d2a3d28de1c2fb15996b30c813bb695d987de6ed68b946fd1f3633f1809548e2` |
| `usdc_before_after_diff.txt` | `e74240f561e5858d02643e7a6249f5ff5259e094bd65504fe3b109952b5ebe4f` |
| `usdt_2021plus_before_after_diff.txt` | `b778b84f0ba7e633269f21cc1add4018014942422dd36b8881dba766161d26ed` |
| `import_usdt2019.log` | `ca9961b2d7227073c496a5159dd403ef7f31c8aee0a67261703580238ddb320c` |
| `import_usdt2019_log_counts.txt` | `6dc758ed33d862d28de6def3eb68df9d27ec864553bda72b30d3a9dbe667e98a` |
| `import_usdt2019_canari.log` | `b503bfd9b97ce310c41bd4a7c2c6fff8d8c2e8eb2fc81be01ca193a52c339d4b` |
| `canari_check_output.txt` | `6fb4800c7815b5481d7bf3db2db759fef4a78e5f9ab00f53b275f943a0cd93d1` |
| `collector_check_output.txt` | `a4a10e72e743a6490fa245ef5ccd0460eeb0dbb0a40d582719c14e19c46d0112` |
| `backup_20260923.log` | `8e990c5c313303c06cb12baf17dde81864b8bc830bb9aa34fb51f76b5faa1bda` |
| `server_scripts/usdt2019_import_20260923.sh` | `49e451ef3a9fa262862d0783a68cab8436b3fbc5417bad9d7bddb2c982b8b235` |
| `server_scripts/usdt2019_canari_20260923.sh` | `5e53fa34d4b5115ceffd2fcfc71c931d768ccb61ea3c5374421b9a9189d8421d` |
| `server_scripts/usdt2019_backup_20260923.sh` | `5c71a45062ba71c6725e84492b8379111456915d910315e13f8573d0ea00dcc1` |
| `server_scripts/usdt2019_inventory_20260923.filled.sh` | `dc18b6dc9fbf8589de07d387a65ef85c9cdf7d2d8f7aaea55bbce38f34cb3819` |
| `server_scripts/state_query.sql` | `f6f3c8bc166136d383e55d7e68ef3cd7e237aa3bf2db9ada670f19aa8a823a5e` |
| `../data_inventory_usdt_2019_20260923/inventory.json` | `cd5ad866c9e34e2633348c8e36b7b3399119e24e012972ee2eff11d9d634c23f` |
| `../data_inventory_usdt_2019_20260923/inventory.md` | `00be1e5bd30503a3a853def8c46b9996c5423a639f8ceb2705839122f5ef26aa` |
| backup serveur `krakenbot_20260923_pre_usdt2019.dump` | `2c94e92fac53ed72f84f721e26bd713f58801374f28c4e6fb28d4b31601eb2ec` |

Fichiers laissés sur le serveur (provenance, hors arbre du service) : `~/usdt2019_{backup,canari,import,inventory}_20260923.sh`,
`~/state_query.sql`, `~/vision_head_probe.sh`, `~/canari_check.sql` (version de ce chantier ; celle du premier import est
archivée dans `results/binance_usdt_import_20260923/server_scripts/`), `~/collector_check.sql` (identique), `~/usdt2019_backup_20260923.log`,
`~/import_usdt2019_canari.{log,status}`, `~/import_usdt2019.{log,status}`, `~/usdt2019_inventory_20260923.{log,status}`,
`~/usdt2019_inventory_out/`, `~/state_before_usdt2019.txt`, `~/state_after_usdt2019.txt`, `~/vision_head_before_usdt2019.txt`,
et le dump dans `~/backups/krakenbot/` (hors rotation du cron : pas de suffixe `_daily` / `_weekly`).

## 12. Ce que ce rapport ne dit pas

- **Aucune validation** : rien n'a été backtesté, aucun manifeste C3 n'a été créé, aucune configuration n'a été évaluée.
- **Aucune comparabilité USDC ↔ USDT mesurée** ; que les séries USDT soient un proxy acceptable des séries USDC est une
  décision du gate d'amendement du protocole C3, pas une donnée de ce rapport.
- Rien sur la qualité intrinsèque des bougies 2019-2020 (cohérence OHLC, volumes) au-delà de la grille temporelle.
- Que 50 semaines d'amorçage 1w soient désormais disponibles avant 2021 est une arithmétique de grille (50e stamp 1w :
  `2019-12-23` pour BTC/ETH, `2021-07-26` pour SOL), pas une fenêtre choisie.
