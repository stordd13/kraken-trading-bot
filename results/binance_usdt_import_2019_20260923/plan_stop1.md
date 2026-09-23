# Plan d'écriture — import complémentaire USDT Binance 2019-2020 (STOP 1, 2026-09-23)

Branche `chore/data-binance-usdt-2019` (depuis `dev` @ `373da3f`) ; serveur `~/apps/kraken-trading-bot` sur `dev` @ `373da3f`
(= local), collector actif, trader inactif, aucun `systemctl`, `.env` serveur intact, aucun tunnel. Modèle : import du 23/09
(`results/binance_usdt_import_report.md`), reproduit à l'identique (mêmes scripts, seuls `--start-date` / `--end-date` et les noms
changent). Décision Bruno du **2026-09-23** (le « 24/09 » du brief est une coquille, corrigée au GO du STOP 1) ; exécution le 2026-09-23 — artefacts et dump datés `20260923`.

## État avant (lecture seule, `state_before.txt`, 12:17:16Z)
- 39 séries `exchange='binance'` = **11 288 569 rows** : 21 `*/USDC` = 8 712 718, 18 `*/USDT` = 2 575 851, identiques au
  `state_after.txt` du 23/09 (07:43:30Z) ; bybit 2 610 736 (collector), kraken 1 181 469 ; hypertable 3 853 Mo, 112 chunks, 0
  compressé ; 53 G libres, 7,6 G RAM, 0 swap ; `krakenbot-collector` active, `krakenbot` inactive.
- **0 row `*/USDT` stampée ≤ `2021-01-01T00:00Z`** ; les 18 séries USDT commencent à `2021-01-01T00:05Z` (5m), `00:15Z`, `01:00Z`,
  `04:00Z`, `2021-01-02T00:00Z` (1d), `2021-01-11T00:00Z` (1w). Empreinte des rows du 23/09 (count, min, max, `sum(close)`,
  `sum(volume)`) relevée par série, restreinte à `timestamp > 2021-01-01T00:00Z` (5m → 1d) et `> 2021-01-04T00:00Z` (1w).
- **Sondes `HEAD` Vision depuis le serveur** (`vision_head_before.txt`, 432 URLs = 3 symboles × 6 TF × 24 mois) : **318 × 200,
  114 × 404**. Les 114 404 sont exactement `SOLUSDT` × {5m, 15m, 1h, 4h, 1d, 1w} × {2019-01 … 2020-07} (19 mois) ; `BTCUSDT`
  et `ETHUSDT` répondent 200 sur les 24 mois × 6 TF, `SOLUSDT` 200 de 2020-08 à 2020-12.
- Bords lus localement (6 fichiers Vision dans le scratchpad, hors dépôt, aucune écriture en base) : `SOLUSDT-5m-2020-08` ouvre
  au `2020-08-11T06:00Z` (5 976 rows = grille pleine) ; `SOLUSDT-1w-2020-08` ouvre au lundi `2020-08-10` ; `BTCUSDT-1w-2019-01`
  ouvre au lundi `2019-01-07` (4 rows) ; `BTCUSDT-1w-2020-12` finit au lundi `2020-12-28` (4 rows) ; `BTCUSDT-5m-2020-12` finit à
  l'ouverture `2020-12-31T23:55Z` et compte **8 870 rows sur 8 928** (58 bougies 5m manquantes en décembre 2020, ≈ 4 h 50 au
  total : trou(s) de maintenance à mesurer par l'inventaire, < 1 jour).

## Écriture
- Commande (verbatim, arbre du service, script `scripts/binance_vision_import.py` **non modifié**, sha256
  `63575e0f…` identique local / serveur) :
  `poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --intervals 5m,15m,1h,4h,1d,1w --start-date 2019-01-01 --end-date 2020-12-31`
- 24 mois × 6 TF × 3 = **432 fichiers** ; 318 importés, **114 `file_not_found` attendus** (liste ci-dessus) ; tout autre
  `file_not_found`, tout `download_failed` / `month_failed` = STOP. Idempotent (`ON CONFLICT DO NOTHING`) : aucune row 2021+ ni
  USDC touchée.
- Durée estimée ≈ 12 min (23/09 : 1 224 fichiers en 33 min) ; ≈ 0,67 M rows ≈ 70 Mo de table ; backup ≈ 260 Mo ; 53 G libres.

### Attendus sur la grille (avant trous mesurés)
| TF | BTC, ETH (731 j, 2019-01-01 → 2020-12-31) | premier stamp | SOL (2020-08-11T06:00Z → 2020-12-31) | premier stamp SOL |
|---|---|---|---|---|
| 5m | 210 528 | 2019-01-01T00:05Z | 41 112 | 2020-08-11T06:05Z |
| 15m | 70 176 | 2019-01-01T00:15Z | 13 704 | 2020-08-11T06:15Z |
| 1h | 17 544 | 2019-01-01T01:00Z | 3 426 | 2020-08-11T07:00Z |
| 4h | 4 386 | 2019-01-01T04:00Z | 857 | 2020-08-11T08:00Z |
| 1d | 731 | 2019-01-02T00:00Z | 143 | 2020-08-12T00:00Z |
| 1w | 104 (lundis 2019-01-07 → 2020-12-28) | 2019-01-14T00:00Z | 21 (lundis 2020-08-10 → 2020-12-28) | 2020-08-17T00:00Z |
| **par paire** | **303 469** | | **59 263** | |

Total grille **666 201** rows ; comptes finaux = grille − trous mesurés. Dernier stamp apporté : `2021-01-01T00:00Z` (5m → 1d),
`2021-01-04T00:00Z` (1w). **Jointure sans trou attendu** : les séries existantes reprennent à `00:05Z` / `00:15Z` / `01:00Z` /
`04:00Z` / `2021-01-02` / `2021-01-11`. Après import : `count = avant + nouveau`, `max` inchangé, `min` = premier stamp ci-dessus.

### Vérification des rows existantes (étape 5)
`diff -u` avant / après sur (a) les 21 séries USDC (`pair|interval|count|min|max`) et (b) les 18 séries USDT restreintes aux rows du
23/09 — `timestamp > 2021-01-01T00:00Z` pour 5m → 1d, **`> 2021-01-04T00:00Z` pour 1w** (le fichier 2020-12 apporte
légitimement le stamp `2021-01-04T00:00Z` ; sans cette borne le diff 1w montrerait +1 row) — avec `sum(close)` et `sum(volume)`
en plus de count/min/max (empreinte de contenu). Attendu : les deux diffs vides.

### Trous 2019-2020
Consignés (dates, durée, bougies manquantes par TF) depuis l'inventaire, jamais comblés ; **STOP si un trou > 1 jour**.

## Séquence et commandes (scripts dans `results/binance_usdt_import_2019_20260923/server_scripts/`)
Envoi : `scp -P 41922 <script> bruno@77.42.90.102:/home/bruno/<script>`, sha256 vérifié identique, lancement
`tmux new -d -s <session> "bash -lc /home/bruno/<script>"`, attente `while tmux has-session -t <session>; do sleep 30; done`,
lecture du `.status` et du journal. Environnement : `unset SCHEDULER_PAIRS SCHEDULER_INTERVALS` (quirk `.bashrc:119`), `NO_COLOR=1`.
1. **Backup** `usdt2019_backup_20260923.sh` (session `usdt2019_backup`) →
   `sudo -n docker exec krakenbot-db pg_dump -U krakenbot -Fc --no-owner --no-acl krakenbot > /home/bruno/backups/krakenbot/krakenbot_20260923_pre_usdt2019.dump`
   (taille, sha256, `pg_restore -l | wc -l`, `.status`).
2. **Canari** `usdt2019_canari_20260923.sh` (session `usdt2019_canari`) →
   `poetry run python scripts/binance_vision_import.py --pairs BTC/USDT --intervals 1d --start-date 2019-01-01 --end-date 2019-01-31`
   attendu 1 fichier, 31 rows, `2019-01-02T00:00Z → 2019-02-01T00:00Z` ; `canari_check.sql` (série 1d BTC = 2 100, USDC 8 712 718,
   USDT 2021+ = 2 575 851). **STOP 2.**
3. **Import complet** `usdt2019_import_20260923.sh` (session `usdt2019_import`), journal `~/import_usdt2019.log`.
4. Lecture seule : `state_query.sql` → `state_after.txt` ; `collector_check.sql` (fenêtre = début / fin de l'import) ;
   inventaire `usdt2019_inventory_20260923.sh` = outil de `dev` @ `373da3f` **tel qu'il est sur le serveur** (sha256 `1b3b87f0…`
   = local, `--pairs` présent) : `data_inventory.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --skip-vision --now <fin import arrondie à la
   minute sup.>`, sortie `~/usdt2019_inventory_out/` → `results/data_inventory_usdt_2019_20260923/`. L'outil dérive l'attendu de
   `[premier, dernier]` stamp (les séries 2019 sont mesurées correctement) ; l'étiquette « vue complète 2021-01 → 2026-04 » de
   ses métadonnées est cosmétique.
5. Rapport `results/binance_usdt_import_2019_report.md`, `PROJECT_CONTEXT.md` § 6, `skills/binance_import.md`, `results/INDEX.md`,
   `SHA256SUMS.txt`, scan de secrets, `git add -f` des logs. **STOP 3**, puis deux commits (`data(binance): …`, `docs(data): …`).

## Noms (le brief laisse `<date>` ; le 23/09 occupe déjà `data_inventory_usdt_20260923/`)
`results/binance_usdt_import_2019_20260923/` (artefacts), `results/data_inventory_usdt_2019_20260923/` (inventaire),
`results/binance_usdt_import_2019_report.md` (rapport), dump `krakenbot_20260923_pre_usdt2019.dump`.

## Sorties inattendues = STOP
`download_failed` / `month_failed`, un `file_not_found` hors des 114 listés, un trou > 1 jour, un count hors [grille − trous
mesurés], un diff non vide sur les rows existantes, toute modification nécessaire de `binance_vision_import.py`, tout écart entre
la commande affichée et celle lancée. Rappel 23/09 : le script n'a pas de retry — un `download_failed` transitoire laisserait un
mois manquant sans compter d'échec (0 sur 1 224 le 23/09).

## Décisions Bruno au STOP 1 (2026-09-23) — GO backup + canari
1. **Date** : la décision est du 23/09 (le « 24/09 » du brief est une erreur de rédaction) ; artefacts et dump datés `20260923`.
2. **Noms** acceptés : `results/binance_usdt_import_2019_20260923/`, `results/data_inventory_usdt_2019_20260923/`.
3. **Bornes du diff** acceptées : `> 2021-01-04T00:00Z` pour la 1w, `> 2021-01-01T00:00Z` pour les cinq autres TF ; empreinte à
   **cinq champs** (count, min, max, `sum(close)`, `sum(volume)`) conservée — plus forte que le diff du 23/09.
4. **Inventaire** : l'outil de `dev` tel qu'il est sur le serveur (`data_inventory.py` @ `373da3f`, `--pairs`, `--skip-vision`).
