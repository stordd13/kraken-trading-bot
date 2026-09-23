# Plan d'écriture — import USDT Binance (STOP 1, 2026-09-23)

Branche `chore/data-binance-usdt` (depuis `dev` @ `8fdaa2a`) ; serveur `~/apps/kraken-trading-bot` sur `dev` @ `8fdaa2a`
(= local), collector actif, trader inactif, aucun `systemctl`, `.env` serveur intact, aucun tunnel.

## État avant (lecture seule, `state_before.txt`)
- 21 séries `*/USDC` `exchange='binance'` = 8 712 718 rows, inchangées ; **0 row `*/USDT`** (tous exchanges) ;
  bybit 2 609 458, kraken 1 181 469 ; hypertable 3 584 Mo, 112 chunks, 0 compressé (≈ 300 o/row) ; 53 G libres, 7,6 G RAM, 0 swap.
- Vision depuis le serveur : 200 sur 2021-01 et 2026-08 pour 5m/15m/1h/4h/1d (3 symboles) ; **1w 404 pour 2026-07, 2026-08**
  (et 2026-09) sur les 3 symboles — les 1w 2021-01 → 2026-06 répondent 200.

## Écriture
- Symboles Vision : `BTCUSDT`, `ETHUSDT`, `SOLUSDT` → `pair` en base `BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `exchange='binance'`.
- TF : `5m,15m,1h,4h,1d,1w` (pas de 1m — choix tranché). Mois 2021-01 → 2026-08 : 68 mois × 6 TF × 3 = **1 224 fichiers**
  (1w : 66 fichiers effectifs, 2026-07/08 absents).
- Grille 2021-01-01 → 2026-08-31 = 2 069 jours. Attendu **sur la grille** par série : 5m 595 872 · 15m 198 624 · 1h 49 656 ·
  4h 12 414 · 1d 2 069 · 1w 296 (lundis 2021-01-04 → 2026-08-31 ; 287 atteignables avec les fichiers 1w jusqu'à 2026-06).
  Stamps (fin de période) : premiers 2021-01-01T00:05 / 00:15 / 01:00 / 04:00, 2021-01-02T00:00 (1d), 2021-01-11T00:00 (1w) ;
  derniers 2026-09-01T00:00 (5m→1d), 2026-07-06T00:00 (1w, si aucun artefact au bord).
- Attendu **si le profil de trous USDT = profil USDC** (6 fenêtres de maintenance 2021 + panne 2023-03-24 12:40→14:05, présente
  dans la base USDC mais absente de la liste du brief) : 5m 595 659 (−213) · 15m 198 554 (−70) · 1h 49 642 (−14) · 4h 12 414 ·
  1d 2 069 · 1w ≤ 287 (artefacts Vision consignés). ≈ 858 400 rows/paire, **≈ 2,575 M rows** au total.
- Disque : ≈ 0,8 Go de table + backup ≈ 260 Mo ; 53 G libres.
- Backup : `~/backups/krakenbot/krakenbot_20260923_pre_usdt.dump` (`pg_dump -Fc --no-owner --no-acl`, taille, sha256,
  `pg_restore -l | wc -l` archivés, `.status`).

## Commandes (verbatim) — scripts dans `results/binance_usdt_import_20260923/server_scripts/`
Envoi : `scp -P 41922 <script> bruno@77.42.90.102:/home/bruno/<script>` puis lancement `tmux new -d -s <session> "bash -lc /home/bruno/<script>"`,
attente `while tmux has-session -t <session> 2>/dev/null; do sleep 30; done`, lecture du `.status` et du journal.
1. backup : `usdt_backup_20260923.sh` (session `usdt_backup`).
2. canari : `usdt_canari_20260923.sh` (session `usdt_canari`) → `canari_check.sql` → STOP 2.
3. plein : `usdt_import_20260923.sh` (session `usdt_import`), journal `~/import_usdt.log`.
4. vérifications lecture seule : `state_query.sql` (state_after), `collector_check.sql` (fenêtre = début/fin de l'import),
   inventaire `usdt_inventory_20260923.sh` sur une archive git du tip de la branche hors de l'arbre du service (`--pairs` à ajouter,
   9 tests adverses déjà rouges contre `8fdaa2a` : `pairs_tests_red_before_8fdaa2a.txt`).

## Sorties inattendues = STOP
`download_failed` / `month_failed` dans le journal, un trou > 1 jour hors liste, un count hors [grille − trous mesurés], toute
modification nécessaire de `binance_vision_import.py`, tout écart entre la commande affichée et celle à lancer.

## Décisions Bruno au STOP 1 (2026-09-23) — GO backup + canari
1. **Inventaire : option 2** — l'outil de `dev` sur le serveur (`scripts/audit/data_inventory.py` @ `8fdaa2a`), sans `--pairs`,
   toutes les séries binance ; pas d'archive tar, pas de symlink `.env`, pas de code non poussé exécuté sur le serveur. Les
   comptes USDC re-mesurés après l'import, comparés à `state_before.txt`, prouvent qu'aucune row USDC n'a été touchée
   (comparaison dans le rapport). `--pairs` : implémenté sur la branche en commit séparé `feat(audit): data_inventory --pairs`
   (+ 9 tests adverses), **après l'import, hors chemin critique, ne sert pas au livrable**.
2. **`download_failed` attendus : exactement six fichiers** (BTCUSDT, ETHUSDT, SOLUSDT × 1w × 2026-07, 2026-08 — 404 constatés à
   l'état avant) ; ils ne déclenchent pas de STOP. Tout autre `download_failed` ou `month_failed` en déclenche un. Comptés dans
   le journal, cités dans le rapport. (Le script journalise un 404 en `file_not_found` (debug) et une exception en
   `download_failed` (error) : les deux événements sont comptés.)
3. **Écart de fin de série 1w** (2026-07-06 contre 2026-09-01 pour les cinq autres TF) : consigné dans le rapport et dans
   `PROJECT_CONTEXT.md` § 6, avec la reprise à faire — relancer `--intervals 1w --start-date 2026-07-01 --end-date 2026-08-31`
   quand Vision publiera les deux fichiers (idempotent, `ON CONFLICT DO NOTHING`). Pas dans ce chantier.
