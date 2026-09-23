# Import des paires USDT Binance — BTC/ETH/SOL × 6 TF, 2021-01 → 2026-08 (2026-09-23)

> **Ce rapport décrit un import de données et sa vérification. Il ne valide rien** : aucun backtest, aucun manifeste,
> aucune comparabilité USDC ↔ USDT mesurée, aucune sélection, aucune modification du protocole C3 ni de la transposition
> USDT → USDC (gate d'amendement). Chantier `chore/data-binance-usdt` depuis `dev` @ `8fdaa2a` ; brief « import des paires
> USDT Binance » (Bruno, 23/09) ; artefacts dans `results/binance_usdt_import_20260923/` (empreintes : `SHA256SUMS.txt`) et
> `results/data_inventory_usdt_20260923/`.

## 1. Pourquoi et quoi

L'inventaire du 22/09 (`results/data_inventory_20260923/inventory.md`) établit que les paires USDC Binance ne cotaient pas
du `2022-09-29T03:00Z` au `2023-03-12` (BTC/ETH, 164 j) et au `2023-12-28` (SOL, 455 j) — Binance Vision répond 404, rien
n'est backfillable en USDC — alors que `BTCUSDT`, `ETHUSDT`, `SOLUSDT` répondent 200 sur tous les mois. Décision Bruno
(23/09) : importer les trois paires USDT sous `exchange='binance'` (`pair` = `BTC/USDT`, `ETH/USDT`, `SOL/USDT`) pour
disposer d'une base **contiguë** 2021-01 → 2026-08.

Deux choix tranchés (Bruno, 23/09), à ne pas rouvrir : **pas de 1m** (aucun moteur ne le lit, 80 % du volume, ajoutable plus
tard) ; **borne de fin = dernier mois Vision complet** (`--end-date 2026-08-31`), pas 2026-04 (le gel de la base USDC venait
de la suspension EU, pas d'un principe).

Décisions au STOP 1 (Bruno, 23/09) : inventaire post-import avec **l'outil de `dev` tel qu'il est sur le serveur, sans
`--pairs`, sur toutes les séries binance** (option 2 : pas d'archive, pas de symlink `.env`, pas de code non poussé sur le
serveur), les comptes USDC re-mesurés servant de preuve qu'aucune row USDC n'a été touchée ; **six `file_not_found`
attendus** (1w 2026-07 et 2026-08 × 3 symboles, 404 constatés à l'état avant), tout autre `download_failed` /
`month_failed` = STOP ; **écart de fin de série 1w** consigné avec sa reprise, hors chantier.

## 2. Chronologie (UTC, 2026-09-23)

| Heure | Étape | Sortie |
|---|---|---|
| 06:47:53 | État avant (lecture seule) | `state_before.txt` : 21 séries `*/USDC` = 8 712 718 rows, **0 row `*/USDT`**, hypertable 3 584 Mo (112 chunks, 0 compressé), 53 G libres |
| 06:44 – 06:56 | Sondes `HEAD` Vision depuis le serveur | 200 sur 2021-01 et 2026-08 pour 5m/15m/1h/4h/1d ; **1w 404 sur 2026-07 et 2026-08** (3 symboles), 200 de 2021-01 à 2026-06 |
| 07:05:11 → 07:06:12 | Backup (tmux `usdt_backup`) | `krakenbot_20260923_pre_usdt.dump`, rc 0 |
| 07:06:51 → 07:06:54 | Canari (tmux `usdt_canari`) | 1 fichier, 31 rows, exit 0 |
| 07:07:23 | Vérification du canari (lecture seule) | 31 rows `BTC/USDT` 1440, `2021-01-02T00:00Z → 2021-02-01T00:00Z`, USDC 8 712 718 |
| **07:09:44 → 07:42:56** | **Import complet (tmux `usdt_import`)** | 1 224 fichiers, `import_complete failed_files=0 processed_files=1224 total_rows=2575851`, exit 0 |
| 07:43:24 | Comptage du journal | `import_usdt_log_counts.txt` |
| 07:43:30 | État après (lecture seule) | `state_after.txt` : 39 séries, binance 11 288 569 |
| 07:43:44 | Contrôle du collector (lecture seule) | `collector_check_output.txt` |
| 07:43:50 → 07:45:06 | Inventaire post-import (tmux `usdt_inventory`) | `data_inventory_usdt_20260923/inventory.{json,md}`, exit 0 |

Serveur : `~/apps/kraken-trading-bot` sur `dev` @ `8fdaa2a` (= `dev` local) pendant toute l'opération ; collector actif
(`krakenbot-collector` active, `krakenbot` inactive), aucun `systemctl`, `.env` serveur intact, aucun tunnel, aucune
écriture en base hors l'import, aucun `DELETE` / `UPDATE`, script `scripts/binance_vision_import.py` **non modifié**.

## 3. Commandes exactes

Chaque commande d'écriture a été affichée mot pour mot au STOP 1 avant le GO et lancée par un script en tmux
(`tmux new -d -s <session> "bash -lc /home/bruno/<script>"`), le journal capturé par `exec > >(tee <log>) 2>&1` ; les scripts
sont archivés dans `results/binance_usdt_import_20260923/server_scripts/` et leur sha256 a été vérifié identique des deux
côtés avant chaque lancement. Environnement de shell : `unset SCHEDULER_PAIRS SCHEDULER_INTERVALS` (quirk `.bashrc:119`,
B3) et `NO_COLOR=1` — pas une modification du script.

```bash
# backup (usdt_backup_20260923.sh)
sudo -n docker exec krakenbot-db pg_dump -U krakenbot -Fc --no-owner --no-acl krakenbot > /home/bruno/backups/krakenbot/krakenbot_20260923_pre_usdt.dump
# canari (usdt_canari_20260923.sh), arbre du service
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT --intervals 1d --start-date 2021-01-01 --end-date 2021-01-31
# import complet (usdt_import_20260923.sh), arbre du service
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --intervals 5m,15m,1h,4h,1d,1w --start-date 2021-01-01 --end-date 2026-08-31
# inventaire post-import (usdt_inventory_20260923.sh), arbre du service, outil de dev @ 8fdaa2a, sortie hors de l'arbre
poetry run python scripts/audit/data_inventory.py --now 2026-09-23T07:43:00Z --output /home/bruno/usdt_inventory_out/inventory.json --markdown /home/bruno/usdt_inventory_out/inventory.md
```

Vérifications en lecture seule : `state_query.sql` (état avant / après), `canari_check.sql`, `collector_check.sql`
(fenêtre `2026-09-23 07:09:44+00 → 07:42:56+00`).

## 4. Backup pré-import

`/home/bruno/backups/krakenbot/krakenbot_20260923_pre_usdt.dump` — `pg_dump -Fc --no-owner --no-acl`, **255 301 183
octets**, sha256 `c9449cae724212e9f87617c3f26153dcbfc4fd93d849795691ba938ccd0dbfee`, **1 188 entrées** `pg_restore -l`,
`.status` = `done 0 2026-09-23T07:06:12Z`. Le `.err` contient les trois avertissements TimescaleDB « circular foreign-key
constraints » (hypertable, chunk, continuous_agg), identiques au dump `b4pre` du 13/09. Restauration : procédure
`skills/database.md` (extension `2.24.0`, `timescaledb_pre_restore` / `post_restore`).

## 5. Comptes avant / après

### 5.1 Séries `*/USDT` (18, créées par l'import) — identiques sur BTC, ETH, SOL

| TF | Count par paire | Attendu grille (2 069 j, 2021-01-01 → 2026-08-31) | Manquantes | Premier stamp | Dernier stamp | Fichiers |
|---|---|---|---|---|---|---|
| 5m | 595 659 | 595 872 | 213 | 2021-01-01T00:05Z | 2026-09-01T00:00Z | 68/68 |
| 15m | 198 554 | 198 624 | 70 | 2021-01-01T00:15Z | 2026-09-01T00:00Z | 68/68 |
| 1h | 49 642 | 49 656 | 14 | 2021-01-01T01:00Z | 2026-09-01T00:00Z | 68/68 |
| 4h | 12 414 | 12 414 | 0 | 2021-01-01T04:00Z | 2026-09-01T00:00Z | 68/68 |
| 1d | 2 069 | 2 069 | 0 | 2021-01-02T00:00Z | 2026-09-01T00:00Z | 68/68 |
| 1w | 279 | 287 (296 lundis sur la grille ; 287 couverts par les fichiers 2021-01 → 2026-06) | 8 | 2021-01-11T00:00Z | **2026-07-06T00:00Z** | 66/68 |
| **Par paire** | **858 617** | | | | | 406/408 |
| **Total** | **2 575 851** | | | | | 1 218/1 224 |

Comptes **= attendu − manquantes** pour les 18 séries, manquantes = somme des trous mesurés (§ 6). Le `total_rows` du
journal (2 575 851, rows lues dans les fichiers) est égal au delta de la base (11 288 569 − 8 712 718) : aucune row
dupliquée, aucune perdue ; les 31 rows du canari sont incluses (recouvertes par `ON CONFLICT DO NOTHING`).

### 5.2 Séries `*/USDC` (21) — inchangées

`usdc_before_after_diff.txt` : `diff -u` **vide** entre `state_before.txt` (06:47:53) et `state_after.txt` (07:43:30) sur
`pair | interval | count | min | max` des 21 séries, somme 8 712 718 des deux côtés. L'inventaire post-import (§ 8) re-mesure
en plus premier / dernier stamp, attendu, manquantes et **la liste des trous** des 21 séries USDC : **0 différence** avec
l'inventaire du 22/09.

### 5.3 Table entière

| | Avant (06:47) | Après (07:43) |
|---|---|---|
| `binance` | 8 712 718 (21 séries) | **11 288 569 (39 séries)** |
| `bybit` | 2 609 458 | 2 609 671 (collector actif) |
| `kraken` | 1 181 469 | 1 181 469 |
| Rows `*/USDT` hors `binance` | 0 | 0 |
| Hypertable | 3 584 Mo, 112 chunks, 0 compressé | 3 853 Mo, 112 chunks, 0 compressé (+269 Mo ≈ 105 o/row) |
| Disque `/` | 53 G libres | 53 G libres |

## 6. Trous (mesurés par `data_inventory.py`, `LAG` SQL, estampilles fin de période)

Attendu du brief : **zéro trou ≥ 2 bougies sur 5m / 4h / 1d hors trous listés et datés**, trous 1w consignés et pas corrigés,
STOP si un trou dépasse 1 jour hors liste. **Constat : zéro trou inattendu sur les 18 séries ; aucun trou sur 4h et 1d.**
Les trous 5m / 15m / 1h sont **identiques sur les trois paires** et **identiques à ceux de la base USDC** (six fenêtres de
maintenance Binance 2021 listées dans le brief + la panne du 2023-03-24, présente dans la base USDC et absente de la liste du
brief, annoncée au STOP 1) :

| Fenêtre (dernier stamp présent → premier suivant, 5m) | Durée | Manquantes 5m | 15m | 1h | Dans le brief |
|---|---|---|---|---|---|
| 2021-02-11T03:45Z → 05:05Z | 1 h 15 | 15 | 5 | 1 | oui |
| 2021-03-06T02:00Z → 03:35Z | 1 h 30 | 18 | 6 | 1 | oui |
| 2021-04-20T02:00Z → 04:35Z | 2 h 30 | 30 | 10 | 2 | oui |
| 2021-04-25T04:05Z → 08:50Z | 4 h 40 | 56 | 18 | 3 | oui |
| 2021-08-13T02:00Z → 06:35Z | 4 h 30 | 54 | 18 | 4 | oui |
| 2021-09-29T07:00Z → 09:05Z | 2 h 00 | 24 | 8 | 2 | oui |
| 2023-03-24T12:40Z → 14:05Z | 1 h 20 | 16 | 5 | 1 | **non** (présente dans la base USDC) |
| **Total** | | **213** | **70** | **14** | |

**1w** : 8 bougies isolées manquantes par paire (trous d'une bougie, `on_grid`), stamps `2022-06-06`, `2022-07-04`,
`2022-09-05`, `2022-10-10`, `2022-11-14`, `2022-12-12`, `2025-02-03`, `2025-03-03` — les cinq premières et les deux
dernières existent à l'identique dans la base USDC (les trois d'octobre–décembre 2022 tombent dans le trou USDC, où elles
n'étaient pas observables). Toutes ouvrent un lundi et se ferment le mois suivant : **artefact Vision probable, consigné, pas
corrigé** (toléré par D1/D2 : un trou d'une bougie ne casse pas un amorçage, règle C2).

Sections 2 et 5 de l'inventaire (« trou USDC », amorçage) pour les paires USDT : aucun trou ≥ 2 bougies sur 4h, 1d, 1w ;
sur 5m les trous bloquants sont les sept fenêtres ci-dessus (≤ 56 bougies, début admissible dans la journée).

## 7. Journal de l'import (`import_usdt.log`, 3 697 lignes, sans séquence ANSI)

| Événement | Compte | Attendu |
|---|---|---|
| `downloading` | 1 224 | 1 224 (68 mois × 6 TF × 3) |
| `imported` (= `imported_batch` final) | 1 218 | 1 218 |
| `file_not_found` (404, debug) | **6** | **6** : `BTCUSDT`, `ETHUSDT`, `SOLUSDT` × 1w × 2026-07, 2026-08 |
| `download_failed` (exception réseau) | **0** | 0 |
| `month_failed` | **0** | 0 |
| `parse_error` / `zip_extract_error` | 0 | 0 |
| `progress` | 24 | — |

`import_complete failed_files=0 processed_files=1224 total_rows=2575851`, `import exit=0`, disque 53 G libres avant et
après. Durée 33 min 12 s (07:09:44 → 07:42:56).

## 8. Inventaire post-import (`results/data_inventory_usdt_20260923/`)

Outil : `scripts/audit/data_inventory.py` de `dev` @ **`8fdaa2a`**, tel qu'il est sur le serveur (sha256
`3f9ebdde586eba6e6a6f6b12af2a16b35c7798c4822f840a525868459c508708`, égal à `git show 8fdaa2a:scripts/audit/data_inventory.py`),
**sans `--pairs`**, `--now 2026-09-23T07:43:00Z` (borne d'observation = fin de l'import arrondie à la minute supérieure),
session `transaction_read_only = on`, `statement_timeout = 5min`, 74 séries agrégées (39 binance + 14 kraken + 21 bybit),
sondes `HEAD` Vision incluses (mêmes codes que le 22/09 : `*USDC` 404 sur 2022-10 → 2023-02, `*USDT` 200 partout).
`inventory.json` sha256 `c6c420147d50d20b59e049b7b8d6d11dff40a29b480d76e33b1385b513109cf8`, `inventory.md` sha256
`831e51d0d66d61ecad57514f3637443e24ee566738f735b56c3d76ae6f25bd2e`. Le titre de l'outil (« trous USDC 2022-2023 ») est
celui du 22/09 ; ses tables couvrent désormais les 39 séries binance.

## 9. Collector Bybit pendant et après l'import

`collector_check_output.txt` (07:43:44) : dernière bougie 1m Bybit `2026-09-23 07:43:00+00` pour les trois paires (**âge 44 s**,
attendu < 3 min) ; sur la fenêtre de l'import `07:09:44 → 07:42:56`, **33 rows 1m par paire et 0 trou > 1 min** (`LAG`).
`journalctl -u krakenbot-collector` sur la fenêtre : `bybit_ws_data_flow_ok` toutes les 5 min, `collector_periodic_stats`
avec `errors: 0, reconnections: 0, resubscribes: 0` (les 14 lignes retenues par le filtre `error|warning|reconnect|resubscribe`
sont ces statistiques à zéro, pas des erreurs). Service `active` avant et après, aucun restart.

## 10. Écarts consignés et reprises (hors chantier)

1. **Fin de série 1w = `2026-07-06`** (bougie ouverte le 2026-06-29) contre `2026-09-01` pour les cinq autres TF : Vision
   n'avait pas publié les fichiers mensuels 1w de 2026-07 et 2026-08 au 23/09 (404 à l'état avant, six `file_not_found`
   au journal). Reprise, quand ces fichiers répondront 200 (idempotent, `ON CONFLICT DO NOTHING`) :
   `poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --intervals 1w --start-date 2026-07-01 --end-date 2026-08-31`.
   Consigné dans `PROJECT_CONTEXT.md` § 6 et `skills/binance_import.md`.
2. **`--pairs` de `data_inventory.py`** : implémenté sur la branche en commit séparé `feat(audit): data_inventory --pairs`
   (`4d0638f`, 9 tests adverses constatés rouges contre `8fdaa2a` — `pairs_tests_red_before_8fdaa2a.txt` — puis 39/39 verts),
   **après l'import, hors chemin critique ; il n'a pas servi au livrable** (décision STOP 1).
3. Trou du 2023-03-24 (panne Binance, ≤ 1 h 20) : absent de la liste du brief, présent à l'identique dans la base USDC,
   consigné.
4. Découvertes annexes signalées au STOP 1, non traitées ici : `ruff format --check` non vert sur `dev` (12 fichiers
   `rejeu_*` / `p6_5_*` préexistants) ; tunnel 5433 actif localement (non utilisé) ; le script d'import n'a pas de retry
   (un `download_failed` transitoire laisserait un mois manquant sans compter d'échec — il n'y en a eu aucun).

## 11. Empreintes des artefacts

`results/binance_usdt_import_20260923/SHA256SUMS.txt` liste les 26 fichiers. Principales :

| Fichier | sha256 |
|---|---|
| `state_before.txt` | `15f328841e6ccf314fd391b4d96e9d112f92e071c6180fc70a04aeb373f43fa9` |
| `state_after.txt` | `c4a82e6f239e24989849b67a714bb4d7c1824e604e491d39c51313d184dd94b7` |
| `usdc_before_after_diff.txt` | `2062c80700f766d593dd4902fab805f4f56c8f2a73a9e8bb2c685595598f7839` |
| `import_usdt.log` | `b057ec3beee89ea16bb0e7f8cd0579565a38ef20a2ded4154076baf0af73ec8d` |
| `import_usdt_log_counts.txt` | `b259a3fe2b97a6de8a67010c144eaff4af40c1e3399f4f9ff67e191f2c51944c` |
| `import_usdt_canari.log` | `61a641bf94e48c6b38aba60a765cd0a931b08fab9911254a17fac36db7db6110` |
| `collector_check_output.txt` | `783c03592f54437b86abdf994de05b7445afdf30e6a5dbbbb4563c46ad16bb81` |
| `backup_20260923.log` | `945783c6c360ed5383f3733a226e5a081d42a639d7e16d59e72fb9698d938a70` |
| `server_scripts/usdt_import_20260923.sh` | `25ec113390f9633d0c25733621a9e0e9d3c83604d2ceb502acdbae84a49694a7` |
| `server_scripts/usdt_canari_20260923.sh` | `bfef3a63229b74dfe5695c17e3a56bca1f7043415271b522f929a493df1740b1` |
| `server_scripts/usdt_backup_20260923.sh` | `aa704c1d7d89057e2deda2ce570e67e28eec7b7b0bee61db203664b69f967987` |
| `server_scripts/usdt_inventory_20260923.filled.sh` | `c99ac60f87e2f7153da57e810dc90b183fc40baf16c13416116ec4ba6091c891` |
| `../data_inventory_usdt_20260923/inventory.json` | `c6c420147d50d20b59e049b7b8d6d11dff40a29b480d76e33b1385b513109cf8` |
| `../data_inventory_usdt_20260923/inventory.md` | `831e51d0d66d61ecad57514f3637443e24ee566738f735b56c3d76ae6f25bd2e` |
| backup serveur `krakenbot_20260923_pre_usdt.dump` | `c9449cae724212e9f87617c3f26153dcbfc4fd93d849795691ba938ccd0dbfee` |

Fichiers laissés sur le serveur (provenance, hors arbre du service) : `~/usdt_{backup,canari,import,inventory}_20260923.sh`,
`~/usdt_backup_20260923.log`, `~/import_usdt_canari.{log,status}`, `~/import_usdt.{log,status}`,
`~/usdt_inventory_20260923.{log,status}`, `~/usdt_inventory_out/`, `~/canari_check.sql`, `~/collector_check.sql`, et le dump
dans `~/backups/krakenbot/` (hors rotation du cron : pas de suffixe `_daily` / `_weekly`).

## 12. Ce que ce rapport ne dit pas

- **Aucune validation** : rien n'a été backtesté, aucun manifeste C3 n'a été créé, aucune configuration n'a été évaluée.
- **Aucune comparabilité USDC ↔ USDT mesurée** : ni écart de prix, ni écart de volume, ni corrélation ; que les séries USDT
  soient un proxy acceptable des séries USDC est une décision du gate d'amendement du protocole C3, pas une donnée de ce
  rapport.
- Rien sur la qualité intrinsèque des bougies (cohérence OHLC, volumes) au-delà de la grille temporelle : l'inventaire mesure
  des estampilles et des comptes.
- Le mois 2026-08 est le dernier mois Vision complet au 23/09 ; toute extension au-delà est une nouvelle décision.
