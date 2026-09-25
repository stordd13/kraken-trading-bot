# Skill: Données historiques Binance (base de backtest)

> Les 8.7M rows `exchange='binance'` (BTC/ETH/SOL-USDC × 7 TF, 2021-01 → 2026-03-31) sont la **base de
> backtest** du projet (décision B0 : prix quasi identiques à Bybit, zéro biais). Elles sont figées :
> Binance a suspendu ses services UE le 1er juillet 2026, aucune mise à jour n'est prévue. Ce skill
> documente comment elles ont été importées, pour référence et pour le futur import Bybit (B3,
> `scripts/bybit_kline_import.py`, même modèle mais REST paginé — voir `skills/bybit.md`).
> **Depuis le 2026-09-23, la même table porte aussi 18 séries `*/USDT`** (3,24 M rows, 6 TF, **2019-01 → 2026-08** pour
> BTC/ETH, 2020-08 → 2026-08 pour SOL, contiguës, en deux passes le même jour) — section « Séries USDT » ci-dessous. Total
> `binance` : **11 952 972 rows importées, 39 séries** — **11 952 996** en base depuis le 2026-09-24 (+ 24 rows 1 w USDT
> **dérivées**, listées dans `ohlc_derived`, voir « Séries USDT »).

## Avant tout : vérifier ce qui est en DB

Les données sont déjà là. **Ne pas relancer l'import.** Script de vérification dans
`skills/database.md` (attendu `binance: 11 952 996` depuis le 2026-09-24 — 8 712 718 `*/USDC` + 3 240 254 `*/USDT` importées +
24 rows 1 w USDT dérivées, `ohlc_derived`).

## Le script

```bash
poetry run python scripts/binance_vision_import.py \
    --pairs BTC/USDC,ETH/USDC,SOL/USDC \
    --intervals 1m,5m,15m,1h,4h,1d,1w \
    --start-date 2021-01-01 \
    --end-date 2026-04-01
```

### Paramètres

- `--pairs` : liste de paires séparées par des virgules
- `--intervals` : timeframes à importer
- `--start-date` / `--end-date` : période (le script télécharge mois par mois)

### Ce que fait le script

1. Pour chaque combinaison (pair, interval, mois), télécharge le ZIP depuis `data.binance.vision`
2. Parse le CSV contenu dans le ZIP
3. Insère les candles en DB par batches de 1000 rows
4. `ON CONFLICT DO NOTHING` assure l'idempotence (relancer 2 fois ne duplique pas)

## Volumes et timing attendus

| TF | Rows/mois/paire | Total 5 ans × 3 paires (estimation) |
|---|---|---|
| 1m | ~43,200 | ~7.8M |
| 5m | ~8,640 | ~1.5M |
| 15m | ~2,880 | ~520k |
| 1h | ~720 | ~130k |
| 4h | ~180 | ~32k |
| 1d | ~30 | ~5.4k |
| 1w | ~4 | ~720 |

**Réalisé : ~8.7M rows (SOL démarre en sept. 2021), 1-3 heures selon la bande passante.**

## Précautions

### Toujours lancer sur le serveur via tmux

L'import prend des heures. Si la connexion SSH coupe, le process meurt. (Historique — l'accès à
`data.binance.vision` depuis l'UE n'est plus garanti.)

```bash
ssh bruno@77.42.90.102 -p 41922
tmux new -s import
cd ~/apps/kraken-trading-bot
poetry run python scripts/binance_vision_import.py \
    --pairs BTC/USDC,ETH/USDC,SOL/USDC \
    --intervals 1m,5m,15m,1h,4h,1d,1w \
    --start-date 2021-01-01 \
    --end-date 2026-04-01
# Ctrl+B puis D pour détacher
```

### Ne JAMAIS réimporter si les données sont déjà en DB

Avant de lancer un import, vérifier ce qui existe :
```sql
SELECT pair, interval, COUNT(*), MIN(timestamp)::date, MAX(timestamp)::date
FROM market_data_ohlc WHERE exchange = 'binance'
GROUP BY pair, interval ORDER BY pair, interval;
```

Si tu vois 39 séries et 11 952 996 rows (21 séries `*/USDC` = 8 712 718, 18 séries `*/USDT` = 3 240 254 importées + 24 rows
1 w dérivées le 2026-09-24), l'import
est déjà fait. Le script est idempotent mais re-télécharger 1260 fichiers ZIP prend inutilement 1-3h. (L'accès à
`data.binance.vision` depuis le serveur Hetzner a été **vérifié le 2026-09-23** : 1 218 + 318 fichiers téléchargés sans échec.)

### Timestamps : millisecondes vs microsecondes (leçon apprise dans la douleur)

Les fichiers Binance Vision utilisent :
- **Millisecondes** (13 chiffres, ex: `1704067200000`) pour les anciens fichiers
- **Microsecondes** (16 chiffres, ex: `1704067200000000`) pour les fichiers 2025+

Le script gère les deux automatiquement via auto-détection (`if raw_ts > 10**14: raw_ts / 1_000_000`).
Le `timestamp` stocké en DB est la **fin de période** (`open_time + interval`, convention du projet) :
`parse_klines_csv` ajoute l'intervalle depuis B4.1 (2026-09-13). Historique : jusqu'à B4.1 le script stockait
`row[0]` (open time) tel quel, et les 8.7 M rows importées étaient open-stamped (constat B3) ; elles ont été
re-stampées en DB par `scripts/audit/b4_restamp_binance.py` (`results/B4_1_timestamp_restamp_report.md`).
Ne jamais ré-importer avec une version antérieure du script.

### Inserts par batch de 1000

Un mois de 1m = 43,200 candles × 11 colonnes = 475k paramètres SQL, bien au-dessus de la limite
PostgreSQL de ~65k. Le script batch à 1000 rows. Tout nouveau script d'import doit faire pareil.

### SOL/USDC commence en septembre 2021

SOL/USDC n'existait pas en début 2021 sur Binance. Le script log un `file_not_found` pour les mois avant septembre 2021 — c'est normal, pas une erreur.

### Fichiers manquants pour le mois en cours

Binance Vision publie les données mensuelles avec un délai. Le mois en cours n'est généralement pas disponible. Le script log un `file_not_found` pour ces fichiers — c'est normal.

## Vérification post-import

```bash
poetry run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv
load_dotenv()
import os

async def check():
    engine = create_async_engine(os.getenv('DATABASE_URL'))
    async with engine.connect() as conn:
        r = await conn.execute(text('''
            SELECT pair, interval, COUNT(*), MIN(timestamp)::date, MAX(timestamp)::date
            FROM market_data_ohlc WHERE exchange = \\'binance\\'
            GROUP BY pair, interval ORDER BY pair, interval
        '''))
        total = 0
        for row in r:
            print(row)
            total += row[2]
        print(f'Total: {total:,}')
    await engine.dispose()

asyncio.run(check())
"
```

Vérifier :
- 39 lignes = 21 `*/USDC` (3 paires × 7 intervals) + 18 `*/USDT` (3 paires × 6 intervals, pas de 1m)
- USDC : BTC et ETH commencent le 2021-01-01, SOL le 2021-09-24 ; toutes finissent le 2026-04-01 00:00 (fin de période de la
  dernière candle de mars 2026 ; 1w : 2026-04-06) ; 8 712 718 rows
- USDT : BTC et ETH commencent le 2019-01-01 00:05 (1w : 2019-01-14), SOL le 2020-08-11 06:05 (1w : 2020-08-17, premier
  fichier Vision 2020-08) ; toutes finissent le 2026-09-01 00:00 (1w : 2026-07-06, voir « Séries USDT ») ; 3 240 254 rows
- Total 11 952 996 rows = 11 952 972 importées + 24 rows 1 w USDT dérivées (`SELECT count(*) FROM ohlc_derived` = 24)

Inventaire complet (trous, attendus, séries) : `scripts/audit/data_inventory.py` (lecture seule, `--now` = borne
d'observation ; `--pairs` pour restreindre) — artefacts de référence `results/data_inventory_20260923/` (22/09, USDC) et
`results/data_inventory_usdt_20260923/` (23/09, post-import, toutes séries) et `results/data_inventory_usdt_2019_20260923/`
(23/09, après la seconde passe, `--pairs BTC/USDT,ETH/USDT,SOL/USDT --skip-vision`).

## Séries USDT (import du 2026-09-23)

**Pourquoi** : les paires USDC Binance ne cotaient pas du `2022-09-29T03:00Z` au `2023-03-12` (BTC/ETH) et au
`2023-12-28` (SOL) — Vision répond 404, rien n'est backfillable en USDC (`results/data_inventory_20260923/inventory.md`
§ 4) — alors que `BTCUSDT`, `ETHUSDT`, `SOLUSDT` sont contigus. Décision Bruno (23/09) : importer les trois paires USDT sous
`exchange='binance'`, `pair` = `BTC/USDT`, `ETH/USDT`, `SOL/USDT`. **Ce n'est pas une validation** : aucune comparabilité
USDC ↔ USDT n'a été mesurée, aucune sélection, la transposition USDT → USDC relève du gate d'amendement du protocole C3.
Rapport : `results/binance_usdt_import_report.md`.

**Deux choix tranchés (Bruno, 23/09), à ne pas rouvrir :**
- **Pas de 1m** : aucun moteur de backtest ne le lit (analyzer 5m → 1w), c'est 80 % du volume ; ajoutable plus tard.
- **Borne de fin = dernier mois Vision complet** (`--end-date 2026-08-31`), pas 2026-04 : le gel de la base USDC venait
  de la suspension EU, pas d'un principe.

**Commande exacte lancée** (serveur, tmux, arbre du service sur `dev` @ `8fdaa2a`, script non modifié, 07:09:44 → 07:42:56 UTC) :

```bash
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT \
    --intervals 5m,15m,1h,4h,1d,1w --start-date 2021-01-01 --end-date 2026-08-31
```

Précédée d'un backup `pg_dump -Fc` (`~/backups/krakenbot/krakenbot_20260923_pre_usdt.dump`) et d'un **canari** (un seul
fichier : `--pairs BTC/USDT --intervals 1d --start-date 2021-01-01 --end-date 2021-01-31` → 31 rows,
`2021-01-02T00:00Z → 2021-02-01T00:00Z`) — le canari est idempotent, le plein le recouvre.

**Résultat** (identique sur les trois paires) : 1 224 fichiers traités, 1 218 importés, 0 `download_failed`, 0 `month_failed`,
6 `file_not_found` attendus (1w 2026-07 et 2026-08 × 3 symboles, absents de Vision au 23/09).

| TF | Count par paire | Attendu grille (2 069 j) | Manquantes | Premier stamp | Dernier stamp |
|---|---|---|---|---|---|
| 5m | 595 659 | 595 872 | 213 | 2021-01-01T00:05Z | 2026-09-01T00:00Z |
| 15m | 198 554 | 198 624 | 70 | 2021-01-01T00:15Z | 2026-09-01T00:00Z |
| 1h | 49 642 | 49 656 | 14 | 2021-01-01T01:00Z | 2026-09-01T00:00Z |
| 4h | 12 414 | 12 414 | 0 | 2021-01-01T04:00Z | 2026-09-01T00:00Z |
| 1d | 2 069 | 2 069 | 0 | 2021-01-02T00:00Z | 2026-09-01T00:00Z |
| 1w | 279 | 287 (fichiers → 2026-06) | 8 | 2021-01-11T00:00Z | **2026-07-06T00:00Z** |

Trous 5m / 15m / 1h = les six fenêtres de maintenance Binance 2021 (02-11, 03-06, 04-20, 04-25, 08-13, 09-29) + la panne du
2023-03-24 12:40 → 14:05, **à l'identique de la base USDC** ; 4h et 1d sans aucun trou ; 1w : 8 bougies isolées manquantes
(2022-06-06, 07-04, 09-05, 10-03, 11-07, 12-05, 2025-02-03, 2025-03-03 — consignées à l'import ; **reconstruites le
2026-09-24** depuis le 1 d, rows marquées dans `ohlc_derived`, `results/reconstruction_1w_2022_2025/report.md`). Cause :
les fichiers mensuels 1 w de 2022 et de 2025-01/02 omettent la semaine à cheval qui finit le 2 du mois suivant ou plus
tard ; le fichier 2025-03, régénéré le 08/10/2025, la sert — règle de génération de Vision changée, fichiers 2022 non
régénérés. *(Une version précédente de ce paragraphe écrivait 10-10, 11-14, 12-12 : ce sont les estampilles présentes
qui suivent les trous.)*

**Écart de fin de série 1w** : la 1w s'arrête au `2026-07-06` (bougie ouverte le 2026-06-29) alors que les cinq autres TF
vont au `2026-09-01`, parce que Vision n'avait pas publié les fichiers mensuels 1w de 2026-07 et 2026-08 au 23/09. **Reprise
à faire** (pas dans le chantier d'import) quand ces deux fichiers répondront 200 :

```bash
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT \
    --intervals 1w --start-date 2026-07-01 --end-date 2026-08-31    # idempotent, ON CONFLICT DO NOTHING
```

Après la reprise, **vérifier les estampilles 1 w reprises** (aucune semaine à cheval manquante : `2026-08-03`, et
`2026-09-07` si le fichier 2026-08 la sert) : la règle de génération actuelle de Vision sert les semaines à cheval (constat
du 24/09, RESEARCH_LOG entrée 13 — la dernière estampille en base, `2026-07-06`, est déjà une semaine à cheval servie par
le fichier 2026-06), une reconstruction ne devrait donc pas être nécessaire — à constater, pas à supposer.

Le mois d'août 2026 est aussi le dernier mois complet pour les autres TF : toute extension au-delà de 2026-08 est une nouvelle
décision (même commande, `--start-date 2026-09-01`).

### Prolongation 2019-2020 (seconde passe du 2026-09-23) — borne de début

Décision Bruno (23/09) : une porte 1w avec EMA 50 exige 50 semaines d'amorçage ; avec des séries qui commencent au 2021-01-01,
aucune fenêtre ne peut débuter avant ~2021-12. Les 18 séries `*/USDT` ont été **prolongées vers l'arrière** avec le même script,
non modifié, idempotent (rapport `results/binance_usdt_import_2019_report.md`, artefacts
`results/binance_usdt_import_2019_20260923/`, backup `~/backups/krakenbot/krakenbot_20260923_pre_usdt2019.dump`) :

```bash
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT \
    --intervals 5m,15m,1h,4h,1d,1w --start-date 2019-01-01 --end-date 2020-12-31
```

**Bornes de début des séries USDT** (à ne pas confondre avec ce que Vision propose) :
- **BTC/USDT, ETH/USDT : `2019-01-01`** (`--start-date 2019-01-01`, premier stamp `2019-01-01T00:05Z`, 1w `2019-01-14T00:00Z`).
  Vision publie `BTCUSDT` / `ETHUSDT` depuis 2017-08 : **les mois antérieurs à 2019-01 ne sont pas importés** ; toute extension
  est une nouvelle décision (même commande, `--end-date 2018-12-31`).
- **SOL/USDT : premier fichier Vision existant, `2020-08`** (cotation `2020-08-11T06:00Z`, premier stamp 5m `2020-08-11T06:05Z`,
  1w `2020-08-17T00:00Z`). Les 19 mois 2019-01 → 2020-07 répondent 404 : **114 `file_not_found` attendus** (19 × 6 TF), constatés
  par `HEAD` avant l'import et comptés dans le journal — ce n'est pas une erreur.

**Résultat** : 432 fichiers traités, 318 importés, 0 `download_failed`, 0 `month_failed`, 664 403 rows (BTC = ETH = 302 619,
SOL = 59 165) ; chaque série = count du 23/09 (2021+) + rows importées, rows 2021+ intactes (diff vide à cinq champs : count, min,
max, `sum(close)`, `sum(volume)`), USDC intactes ; **jointure au 2021-01-01 sans trou** (le fichier 2020-12 apporte les stamps
`2021-01-01T00:00Z` et `2021-01-04T00:00Z` pour la 1w).

| TF | BTC, ETH importées (grille 731 j) | manquantes | SOL importées (grille depuis 2020-08-11T06:00Z) | manquantes |
|---|---|---|---|---|
| 5m | 209 927 (210 528) | 601 | 41 042 (41 112) | 70 |
| 15m | 69 977 (70 176) | 199 | 13 681 (13 704) | 23 |
| 1h | 17 499 (17 544) | 45 | 3 421 (3 426) | 5 |
| 4h | 4 381 (4 386) | 5 | 857 (857) | 0 |
| 1d | 731 (731) | 0 | 143 (143) | 0 |
| 1w | 104 (104) | 0 | 21 (21) | 0 |

Trous 2019-2020 (maintenances Binance, mesurées par `data_inventory.py`, identiques sur BTC/ETH, SOL partage les trois de
nov.–déc. 2020) : 2019-03-12 (6 h), **2019-05-15 (10 h, la plus longue)**, 2019-06-07 (1 h), 2019-08-15 (8 h), 2019-11-13 (2 h 20),
2019-11-25 (2 h), 2020-02-09 (1 h), 2020-02-19 (5 h 50), 2020-03-04 (2 h 05), 2020-04-25 (2 h 30), 2020-06-28 (3 h 30), 2020-11-30
(1 h), 2020-12-21 (3 h 50), 2020-12-25 (1 h) — **consignés, jamais comblés** ; aucun sur 1d / 1w ; sur 4h, 5 bougies manquantes
(2019-03-12, 2019-05-15 × 2 consécutives, 2019-08-15, 2020-02-19). Ce n'est pas une validation : rien de backtesté, aucune
comparabilité USDC ↔ USDT mesurée.

## Trous récents (backfill)

`scripts/backfill_binance_gap.py` (P7) a été supprimé en B3, remplacé par le générique
`scripts/backfill_gap.py` (module `krakenbot.data.backfill`, exchange = `settings.exchange_name`).
Il n'est **pas** garanti correct pour Binance (le REST ccxt renvoie l'open time alors que la DB est
end-stamped depuis B4.1) — la source live est Bybit depuis B2, les données Binance sont figées.